#!/usr/bin/env bash
# start.sh ile başlatılan servisleri durdurur.
#
# Yalnızca kendi PID dosyalarımızdaki süreç GRUPLARINI durdurur — makinedeki
# başka Next.js/uvicorn uygulamalarına dokunmaz.
set -uo pipefail

for name in agent web; do
  pidfile="/tmp/jobagent-$name.pid"
  [ -f "$pidfile" ] || continue
  pgid="$(tr -dc '0-9' < "$pidfile" 2>/dev/null)"
  rm -f "$pidfile"
  [ -n "${pgid:-}" ] || continue

  # PID dosyası eskimiş olabilir ve o numara artık başka bir sürece ait olabilir.
  # Grup halinde öldürdüğümüz için önce gerçekten bizim servisimiz mi diye bak.
  leader_cmd="$(ps -o args= -p "$pgid" 2>/dev/null || true)"
  case "$leader_cmd" in
    *uvicorn*|*next*|*npm*) ;;
    "") continue ;;   # süreç zaten yok
    *)
      echo "$name: PID dosyası eskimiş (pid $pgid başka bir sürece ait), atlanıyor"
      continue
      ;;
  esac

  if kill -TERM -- "-$pgid" 2>/dev/null; then
    for _ in $(seq 1 15); do
      sleep 0.3
      kill -0 -- "-$pgid" 2>/dev/null || break
    done
    kill -KILL -- "-$pgid" 2>/dev/null || true
    echo "$name durduruldu (grup $pgid)"
  fi
done
