#!/bin/bash
# The mock hospital's web app (V2 items 1.3 / 1.5 / 1.6): FastAPI + uvicorn on 127.0.0.1:7130 only; never tunnelled.
#   his_mock/serve.sh start | stop | status | restart
# Data: data/his_mock/ (or $TB_HIS_MOCK_DATA), built by `python -m his_mock.build`. Log: ~/vaidyx/logs/his_mock.log.
cd "$(dirname "$0")/.." || exit 1
PY=/data/vaidyx/venv/app/bin/python
PORT=${TB_HIS_MOCK_PORT:-7130}
LOG=${HOME}/vaidyx/logs; mkdir -p "$LOG"
pid_on_port() { ss -ltnp 2>/dev/null | awk -v p="127.0.0.1:$PORT " '$0 ~ p {print $NF}' | grep -oE "pid=[0-9]+" | cut -d= -f2 | head -1; }
start() {
  if [ -n "$(pid_on_port)" ]; then echo "his_mock already listening on $PORT (pid $(pid_on_port))"; return 0; fi
  [ -f "${TB_HIS_MOCK_DATA:-data/his_mock}/store.json" ] || { echo "no store: run $PY -m his_mock.build first"; return 1; }
  setsid nohup $PY -m uvicorn --factory his_mock.app:create_app --host 127.0.0.1 --port "$PORT" --log-level warning \
    > "$LOG/his_mock.log" 2>&1 < /dev/null &
  for i in $(seq 1 30); do curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health" && { echo "his_mock started on $PORT (pid $(pid_on_port))"; return 0; }; sleep 1; done
  echo "his_mock did not answer on $PORT within 30 s; see $LOG/his_mock.log"; return 1
}
stop() { P=$(pid_on_port); if [ -n "$P" ]; then kill "$P" && echo "stopped his_mock (pid $P)"; sleep 1; else echo "his_mock not running"; fi; }
case "$1" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) curl -s -m 5 "http://127.0.0.1:$PORT/" || { echo "his_mock not running on $PORT"; exit 1; }; echo ;;
  *) echo "usage: his_mock/serve.sh start|stop|status|restart"; exit 2 ;;
esac
