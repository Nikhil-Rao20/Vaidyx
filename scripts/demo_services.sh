#!/usr/bin/env bash
# Start, stop or show the four localhost services of the Vaidyx-TB demo:
#   Vaidyx app :7000 (/tb and /tb-nik), demo HIMS :7130, Orthanc + OHIF PACS :8042, LiveKit :7880.
# Models (:8100, :8101) are started separately with tumour_board/serve_models.sh.
# Usage: scripts/demo_services.sh start|stop|status|restart [app|his|pacs|video ...]
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY=/data/vaidyx/venv/app/bin/python
LOGS=~/vaidyx/logs
mkdir -p "$LOGS"

port_pid() { ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p"$" {print $NF}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

start_app() {
  if [ -n "$(port_pid 7000)" ]; then echo "app: already on :7000"; return; fi
  (cd "$REPO" && APP_BIND=127.0.0.1 APP_PORT=7000 setsid nohup "$PY" app.py > "$LOGS/vaidyx_app.log" 2>&1 &)
  for _ in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:7000/api/health && { echo "app: up on :7000"; return; }; sleep 1; done
  echo "app: did not answer in 60 s (see $LOGS/vaidyx_app.log)"
}
stop_app() { p=$(port_pid 7000); [ -n "$p" ] && kill "$p" && echo "app: stopped" || echo "app: not running"; }

start_his() { "$REPO/his_mock/serve.sh" start; }
stop_his() { "$REPO/his_mock/serve.sh" stop; }

start_pacs() { "$REPO/his_mock/orthanc.sh" start; }
stop_pacs() { "$REPO/his_mock/orthanc.sh" stop; }

start_video() { [ -x "$REPO/scripts/livekit.sh" ] && "$REPO/scripts/livekit.sh" start || echo "video: scripts/livekit.sh not present yet"; }
stop_video() { [ -x "$REPO/scripts/livekit.sh" ] && "$REPO/scripts/livekit.sh" stop || true; }

status() {
  for pair in "app:7000" "his:7130" "pacs:8042" "video:7880" "reasoner:8100" "reader:8101"; do
    n=${pair%%:*}; p=${pair##*:}
    if [ -n "$(port_pid "$p")" ]; then echo "$n: listening on :$p"; else echo "$n: not running (:$p)"; fi
  done
}

cmd=${1:-status}; shift || true
targets=${*:-"pacs his video app"}
case "$cmd" in
  start)   for t in $targets; do "start_$t"; done ;;
  stop)    for t in $targets; do "stop_$t"; done ;;
  restart) for t in $targets; do "stop_$t"; sleep 1; "start_$t"; done ;;
  status)  status ;;
  *) echo "usage: $0 start|stop|status|restart [app|his|pacs|video ...]"; exit 2 ;;
esac
