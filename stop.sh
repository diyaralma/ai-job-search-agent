#!/usr/bin/env bash
# Stops the services started by start.sh.
#
# Only kills the process GROUPS recorded in our own PID files — it never touches
other Next.js/uvicorn apps on the machine.
set -uo pipefail

for name in agent web; do
  pidfile="/tmp/jobagent-$name.pid"
  [ -f "$pidfile" ] || continue
  pgid="$(tr -dc '0-9' < "$pidfile" 2>/dev/null)"
  rm -f "$pidfile"
  [ -n "${pgid:-}" ] || continue

  # The PID file may be stale and that number may now belong to another process.
  # Since we kill a whole group, check that it really is our service first.
  leader_cmd="$(ps -o args= -p "$pgid" 2>/dev/null || true)"
  case "$leader_cmd" in
    *uvicorn*|*next*|*npm*) ;;
    "") continue ;;   # process is already gone
    *)
      echo "$name: stale PID file (pid $pgid belongs to another process), skipping"
      continue
      ;;
  esac

  if kill -TERM -- "-$pgid" 2>/dev/null; then
    for _ in $(seq 1 15); do
      sleep 0.3
      kill -0 -- "-$pgid" 2>/dev/null || break
    done
    kill -KILL -- "-$pgid" 2>/dev/null || true
    echo "$name stopped (group $pgid)"
  fi
done
