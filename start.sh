#!/usr/bin/env bash
# Starts the agent service (8000) and the web UI (3001).
# Logs: /tmp/jobagent-{agent,web}.log
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

"$ROOT/stop.sh" >/dev/null 2>&1 || true

if [ ! -f agent/.env ]; then
  cp agent/.env.example agent/.env
  echo "Created agent/.env from the example. Edit it to pick your model provider:"
  echo "  LLM_PROVIDER=claude_cli | anthropic | openai"
  echo
fi

# Starts a service in its own process group and writes the group id to a PID file.
#
# The group matters: `npm run dev` spawns a grandchild (next-server); killing only
# the parent orphans the grandchild that holds the port.
# The child writes the id itself: because `setsid` forks, the `$!` the shell sees
# is NOT the group leader — killing that value stops nothing.
start_service() {
  local name="$1" dir="$2"; shift 2
  rm -f "/tmp/jobagent-$name.pid"
  setsid bash -c '
    cd "$1" || exit 1
    echo $$ > "/tmp/jobagent-$2.pid"
    shift 2
    exec "$@"
  ' _ "$dir" "$name" "$@" > "/tmp/jobagent-$name.log" 2>&1 < /dev/null &
}

echo "agent  -> http://localhost:8000"
start_service agent agent ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo "web    -> http://localhost:3001"
start_service web web npm run dev

read_pid() { cat "/tmp/jobagent-$1.pid" 2>/dev/null | tr -dc '0-9'; }

# A responding port is not enough: is the response coming from the process WE
# started? If a stale process holds the port the user cannot tell why their
# changes are not showing up — so we verify our processes are alive too.
for _ in $(seq 1 40); do
  sleep 1
  agent_pid="$(read_pid agent)"; web_pid="$(read_pid web)"
  [ -n "$agent_pid" ] && [ -n "$web_pid" ] || continue   # not written yet

  kill -0 "$agent_pid" 2>/dev/null || { echo "Agent process died — tail -30 /tmp/jobagent-agent.log"; exit 1; }
  kill -0 "$web_pid" 2>/dev/null || { echo "Web process died — tail -30 /tmp/jobagent-web.log"; exit 1; }

  agent_ok="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:8000/api/health 2>/dev/null || echo 000)"
  web_ok="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:3001/ 2>/dev/null || echo 000)"
  if [ "$agent_ok" = "200" ] && [ "$web_ok" = "200" ]; then
    echo
    echo "Ready. Open in your browser: http://localhost:3001"

    # Is the selected provider ready? The user should learn that now, not after
    # uploading a CV and waiting 30 seconds.
    llm_line="$(curl -s -m 3 http://127.0.0.1:8000/api/health \
      | agent/.venv/bin/python -c '
import json, sys
try:
    d = json.load(sys.stdin)["llm"]
except Exception:
    raise SystemExit(0)
print("\t".join([str(d["ready"]), d["provider"], d["model"], d["detail"]]))
' 2>/dev/null)"
    IFS=$'\t' read -r llm_ready llm_provider llm_model llm_detail <<< "$llm_line"

    if [ -n "$llm_provider" ]; then
      echo "model  -> $llm_provider · $llm_model"
    fi
    if [ "$llm_ready" != "True" ]; then
      echo
      echo "WARNING: the LLM steps (CV analysis + matching) will not work."
      echo "       ${llm_detail:-Provider not ready; check agent/.env.}"
    fi
    exit 0
  fi
done

echo "Services did not respond within 40 seconds. Check the logs:"
echo "  tail -30 /tmp/jobagent-agent.log"
echo "  tail -30 /tmp/jobagent-web.log"
exit 1
