#!/usr/bin/env bash
# Agent servisini (8000) ve web arayüzünü (3001) başlatır.
# Loglar: /tmp/jobagent-{agent,web}.log
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

"$ROOT/stop.sh" >/dev/null 2>&1 || true

if [ ! -f agent/.env ]; then
  cp agent/.env.example agent/.env
  echo "agent/.env oluşturuldu (örnekten). Model sağlayıcını seçmek için düzenle:"
  echo "  LLM_PROVIDER=claude_cli | anthropic | openai"
  echo
fi

# Servisi kendi süreç grubunda başlatır ve grup kimliğini PID dosyasına yazar.
#
# Grup şart: `npm run dev` torun süreç (next-server) açıyor, sadece ebeveyni
# öldürmek portu tutan torunu sahipsiz bırakıyor.
# Kimliği çocuk kendisi yazıyor: `setsid` fork ettiği için kabuğun gördüğü `$!`
# grup lideri DEĞİL — o değere göre öldürmek hiçbir şeyi durdurmuyor.
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

# Portun yanıt vermesi yetmez: yanıtı BİZİM başlattığımız süreç mi veriyor?
# Eski bir süreç portu tutuyorsa kullanıcı değişikliklerinin neden görünmediğini
# anlayamaz — o yüzden süreçlerin canlı olduğunu da doğruluyoruz.
for _ in $(seq 1 40); do
  sleep 1
  agent_pid="$(read_pid agent)"; web_pid="$(read_pid web)"
  [ -n "$agent_pid" ] && [ -n "$web_pid" ] || continue   # henüz yazılmadı

  kill -0 "$agent_pid" 2>/dev/null || { echo "Agent süreci öldü — tail -30 /tmp/jobagent-agent.log"; exit 1; }
  kill -0 "$web_pid" 2>/dev/null || { echo "Web süreci öldü — tail -30 /tmp/jobagent-web.log"; exit 1; }

  agent_ok="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:8000/api/health 2>/dev/null || echo 000)"
  web_ok="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:3001/ 2>/dev/null || echo 000)"
  if [ "$agent_ok" = "200" ] && [ "$web_ok" = "200" ]; then
    echo
    echo "Hazır. Tarayıcıda aç: http://localhost:3001"

    # Seçili sağlayıcı hazır mı? Kullanıcı CV yükleyip 30 saniye bekledikten
    # sonra değil, şimdi öğrensin.
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
      echo "UYARI: LLM adımları (CV analizi + eşleştirme) çalışmaz."
      echo "       ${llm_detail:-Sağlayıcı hazır değil; agent/.env dosyasını kontrol et.}"
    fi
    exit 0
  fi
done

echo "Servisler 40 saniyede yanıt vermedi. Loglara bak:"
echo "  tail -30 /tmp/jobagent-agent.log"
echo "  tail -30 /tmp/jobagent-web.log"
exit 1
