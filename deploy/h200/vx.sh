#!/bin/bash
# Doctors' instance on the H200 (deployment Plan B, see deploy/README.md): the app (:7300), the gate (:7301) and the secure
# link to the VM (chisel client). No sudo needed.
#
#   deploy/h200/vx.sh start | stop | restart-app | status | ensure
#
# ensure = start whatever is down (run by cron every 5 minutes and @reboot). Secrets come from ~/vaidyx/deploy_vm/secrets
# (mode 600) and are passed through the environment, never on a command line (other users of the H200 can read those).
set -u
ROOT=${VX_DEPLOY_ROOT:-/data/vaidyx/tb_deploy}
APP=$ROOT/app
SEC=${VX_SECRETS:-$HOME/vaidyx/deploy_vm/secrets}
LOG=$ROOT/logs
PY=/data/vaidyx/venv/app/bin/python
CHISEL=${VX_CHISEL:-/data/vaidyx/tools/chisel-1.13.0/chisel}
HOST=${VX_PUBLIC_HOST:-vaidyx-tb-8-231-83-210.sslip.io}
APP_PORT=7300; GATE_PORT=7301; LINK_REMOTE="R:127.0.0.1:17000:127.0.0.1:$GATE_PORT"
mkdir -p "$LOG"; chmod 700 "$ROOT" 2>/dev/null

pid_on() { ss -Hltnp "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2; }
up() { [ -n "$(pid_on "$1")" ]; }
link_pid() { pgrep -u "$(id -u)" -f "^$CHISEL client .*$HOST/vx-link" | head -1; }
gate_ok() { curl -s -m 5 -o /dev/null -w '%{http_code}' -H "X-Vaidyx-Gate: $(cat "$SEC/gate_secret")" "http://127.0.0.1:$GATE_PORT/_gate/health"; }

start_app() {
  up $APP_PORT && return 0
  [ -d "$APP" ] && [ -d "$ROOT/vaidyx_data" ] || { echo "app: run deploy_h200.sh / setup_instance.py first"; return 1; }
  ( cd "$APP" && APP_BIND=127.0.0.1 APP_PORT=$APP_PORT VAIDYX_DATA_DIR=$ROOT/vaidyx_data TB_DATA_ROOT=$ROOT/tumour_board \
      TB_GUIDELINE_DIR=$ROOT/guidelines TB_PROTECTED_CASES=TB-2026-bharath TB_STAGING=off CLEANUP_ENABLED=false \
      setsid nohup "$PY" app.py >> "$LOG/app.log" 2>&1 < /dev/null & )
  for _ in $(seq 1 90); do curl -s -o /dev/null -m 3 "http://127.0.0.1:$APP_PORT/login" && return 0; sleep 2; done
  echo "app: did not start, see $LOG/app.log"; return 1
}

start_gate() {
  up $GATE_PORT && return 0
  ( cd "$APP/deploy/h200" && VX_GATE_SECRET_FILE="$SEC/gate_secret" VX_UPSTREAM=http://127.0.0.1:$APP_PORT \
      setsid nohup "$PY" -m uvicorn gate:app --host 127.0.0.1 --port $GATE_PORT --no-proxy-headers --log-level warning \
      >> "$LOG/gate.log" 2>&1 < /dev/null & )
  for _ in $(seq 1 20); do up $GATE_PORT && return 0; sleep 1; done
  echo "gate: did not start, see $LOG/gate.log"; return 1
}

start_link() {
  [ -n "$(link_pid)" ] && return 0
  [ -s "$SEC/link_password" ] && [ -s "$SEC/chisel_fingerprint" ] || { echo "link: secrets missing in $SEC"; return 1; }
  AUTH="vxlink:$(cat "$SEC/link_password")" setsid nohup "$CHISEL" client --fingerprint "$(cat "$SEC/chisel_fingerprint")" \
    --keepalive 25s --max-retry-interval 30s "https://$HOST/vx-link" "$LINK_REMOTE" >> "$LOG/link.log" 2>&1 < /dev/null &
  sleep 2; [ -n "$(link_pid)" ] || { echo "link: did not start, see $LOG/link.log"; return 1; }
}

stop_all() {
  P=$(link_pid); [ -n "$P" ] && kill "$P"
  for port in $GATE_PORT $APP_PORT; do P=$(pid_on $port); [ -n "$P" ] && kill "$P"; done
  echo "stopped: link, gate, app (internal :7000, public demo and models untouched)"
}

status() {
  echo "app  :$APP_PORT  $(up $APP_PORT && echo up || echo DOWN)  code $(git -C "$APP" rev-parse --short HEAD 2>/dev/null)"
  echo "gate :$GATE_PORT  $(up $GATE_PORT && echo "up (health $(gate_ok))" || echo DOWN)"
  echo "link       $([ -n "$(link_pid)" ] && echo up || echo DOWN)  -> https://$HOST/vx-link"
  echo "public     $(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://$HOST/login")  https://$HOST/tb-nik"
}

case "${1:-}" in
  start|ensure) start_app && start_gate && start_link; [ "$1" = start ] && status ;;
  stop) stop_all ;;
  restart-app) P=$(pid_on $APP_PORT); [ -n "$P" ] && kill "$P"; for _ in $(seq 1 30); do up $APP_PORT || break; sleep 1; done; start_app ;;
  status) status ;;
  *) echo "usage: $0 start|stop|restart-app|status|ensure"; exit 2 ;;
esac
