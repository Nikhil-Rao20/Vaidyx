#!/bin/bash
# Doctors' instance on the H200 (deployment Plan B, see deploy/README.md): the app (:7300), the gate (:7301) and the secure
# link to the VM (chisel client). No sudo needed.
#
#   deploy/h200/vx.sh start | stop | status | ensure | restart-app | restart-gate | restart-link | restart-his
#
# The public site's own copy of the synthetic demo hospital (HIMS) runs here too, on :7330 with its own data
# ($ROOT/his_mock, set up by setup_instance.py); the internal development HIMS (:7130) is never reached from outside.
#
# ensure = start whatever is down (run by cron every 5 minutes and @reboot). Secrets come from ~/vaidyx/deploy_vm/secrets
# (mode 600) and are passed through the environment or a file descriptor, never on a command line (other users of the H200
# can read command lines with ps).
#
# Ports held by someone else: the H200 is shared, and 7300 / 7301 / 7330 are ordinary ports. If either is listening but not owned
# by us (ss shows no pid for another user's socket), the link is stopped and stays stopped, so the VM never forwards doctors
# to a stranger's process (security review 4 Nov).
set -u
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH   # cron's PATH has no /usr/sbin (ss), so 'up' saw nothing
ROOT=${VX_DEPLOY_ROOT:-/data/vaidyx/tb_deploy}
APP=$ROOT/app
SEC=${VX_SECRETS:-$HOME/vaidyx/deploy_vm/secrets}
LOG=$ROOT/logs
# The doctors' site has its own environment (5 Nov 2026): requirements-ci.lock with the security upgrades, the same pins CI tests,
# on Python 3.12 since the evening of 5 Nov (pillow, filelock, dnspython fixes). The Python 3.10 one (/data/vaidyx/venv/tb_deploy) stays
# for a rollback (deploy an earlier commit). The shared /data/vaidyx/venv/app (internal app, public demo) is not touched by either.
PY=${VX_PY:-/data/vaidyx/venv/tb_deploy312/bin/python}
CHISEL=${VX_CHISEL:-/data/vaidyx/tools/chisel-1.13.0/chisel}
HOST=${VX_PUBLIC_HOST:-vaidyx-tb-8-231-83-210.sslip.io}
APP_PORT=7300; GATE_PORT=7301; HIS_PORT=7330; LINK_REMOTE="R:127.0.0.1:970:127.0.0.1:$GATE_PORT"   # 970: below 1024, so no other VM user can listen there
mkdir -p "$LOG"; chmod 700 "$ROOT" 2>/dev/null

pid_on() { ss -Hltnp "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2; }
up() { [ -n "$(pid_on "$1")" ]; }                                     # listening, and the process is ours
held_by_other() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q . && ! up "$1"; }
link_pid() { pgrep -u "$(id -u)" -f "^$CHISEL client .*$HOST/vx-link" | head -1; }
# the secret goes to curl through a file descriptor (printf is a shell builtin), never on its command line
gate_ok() { curl -s -m 5 -o /dev/null -w '%{http_code}' -H @<(printf 'X-Vaidyx-Gate: %s\n' "$(cat "$SEC/gate_secret")") \
              "http://127.0.0.1:$GATE_PORT/_gate/health"; }

stop_link() { P=$(link_pid); [ -n "$P" ] && kill "$P"; return 0; }

guard() {
  for port in $APP_PORT $GATE_PORT $HIS_PORT; do
    if held_by_other $port; then
      stop_link
      echo "ALERT $(date '+%F %T'): port $port is held by another user's process; the link is stopped until it is ours again" | tee -a "$LOG/alerts.log" >&2
      return 1
    fi
  done
}

start_app() {
  up $APP_PORT && return 0
  [ -d "$APP" ] && [ -d "$ROOT/vaidyx_data" ] || { echo "app: run deploy_h200.sh / setup_instance.py first"; return 1; }
  # exec: no shell stays behind holding the caller's output (a piped deploy_h200.sh looked hung).
  # LOCALHOST_BYPASS=false: set here so a stray .env file higher up the folder tree can never switch it on.
  # TB_REAL_DATA_2FA=0: guest reviewers sign in with the password only during the test period (Eswar, 5 Nov 2026); 1 brings two-step back.
  ( cd "$APP" || exit 1; APP_BIND=127.0.0.1 APP_PORT=$APP_PORT VAIDYX_DATA_DIR=$ROOT/vaidyx_data TB_DATA_ROOT=$ROOT/tumour_board \
      TB_GUIDELINE_DIR=$ROOT/guidelines TB_PROTECTED_CASES=TB-2026-bharath TB_STAGING=off CLEANUP_ENABLED=false LOCALHOST_BYPASS=false \
      TB_UPLOAD_POLICY=private_only TB_PRIVATE_RETENTION_DAYS=90 TB_REAL_DATA_2FA=0 \
      exec setsid nohup "$PY" app.py ) >> "$LOG/app.log" 2>&1 < /dev/null &
  for _ in $(seq 1 90); do up $APP_PORT && curl -s -o /dev/null -m 3 "http://127.0.0.1:$APP_PORT/login" && return 0; sleep 2; done
  echo "app: did not start, see $LOG/app.log"; return 1
}

start_his() {
  up $HIS_PORT && return 0
  [ -f "$ROOT/his_mock/store.json" ] || { echo "his: run setup_instance.py first (no $ROOT/his_mock)"; return 1; }
  # --no-proxy-headers: the HIMS counts sign-in failures by the real client address it sees (the gate)
  ( cd "$APP" || exit 1; TB_HIS_MOCK_DATA=$ROOT/his_mock TB_HIS_MOCK_PORT=$HIS_PORT \
      exec setsid nohup "$PY" -m uvicorn --factory his_mock.app:create_app --host 127.0.0.1 --port $HIS_PORT --log-level warning \
      --no-proxy-headers ) >> "$LOG/his.log" 2>&1 < /dev/null &
  for _ in $(seq 1 30); do up $HIS_PORT && curl -s -o /dev/null -m 2 "http://127.0.0.1:$HIS_PORT/health" && return 0; sleep 1; done
  echo "his: did not start, see $LOG/his.log"; return 1
}

start_gate() {
  up $GATE_PORT && return 0
  ( cd "$APP/deploy/h200" || exit 1; VX_GATE_SECRET_FILE="$SEC/gate_secret" VX_UPSTREAM=http://127.0.0.1:$APP_PORT \
      exec setsid nohup "$PY" -m uvicorn gate:app --host 127.0.0.1 --port $GATE_PORT --no-proxy-headers --log-level warning \
      ) >> "$LOG/gate.log" 2>&1 < /dev/null &
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

# stop one of our listeners; escalate to SIGKILL after 30 s, so a restart never "succeeds" with the old process still serving
stop_port() {
  P=$(pid_on "$1"); [ -n "$P" ] || return 0
  kill "$P"
  for _ in $(seq 1 30); do up "$1" || return 0; sleep 1; done
  P=$(pid_on "$1"); [ -n "$P" ] && kill -9 "$P"
  for _ in $(seq 1 5); do up "$1" || return 0; sleep 1; done
  echo "port $1 is still held after SIGKILL"; return 1
}

stop_all() {
  stop_link
  stop_port $GATE_PORT; stop_port $APP_PORT; stop_port $HIS_PORT
  echo "stopped: link, gate, app, demo hospital copy (internal :7000, :7130, public demo and models untouched)"
}

status() {
  echo "app  :$APP_PORT  $(up $APP_PORT && echo up || { held_by_other $APP_PORT && echo "HELD BY ANOTHER USER" || echo DOWN; })  code $(git -C "$APP" rev-parse --short HEAD 2>/dev/null)"
  echo "gate :$GATE_PORT  $(up $GATE_PORT && echo "up (health $(gate_ok))" || { held_by_other $GATE_PORT && echo "HELD BY ANOTHER USER" || echo DOWN; })"
  echo "his  :$HIS_PORT  $(up $HIS_PORT && echo up || { held_by_other $HIS_PORT && echo "HELD BY ANOTHER USER" || echo DOWN; })  (demo hospital copy)"
  echo "link       $([ -n "$(link_pid)" ] && echo up || echo DOWN)  -> https://$HOST/vx-link"
  echo "public     $(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://$HOST/sign-in")  https://$HOST/"
}

case "${1:-}" in
  start|ensure) guard && start_his && start_app && start_gate && guard && start_link; rc=$?; [ "$1" = start ] && status; exit $rc ;;
  stop) stop_all ;;
  restart-app) stop_port $APP_PORT && guard && start_app ;;
  restart-gate) stop_port $GATE_PORT && guard && start_gate ;;
  restart-link) stop_link; sleep 1; guard && start_link ;;
  restart-his) stop_port $HIS_PORT && guard && start_his ;;
  status) status ;;
  *) echo "usage: $0 start|stop|status|ensure|restart-app|restart-gate|restart-link|restart-his"; exit 2 ;;
esac
