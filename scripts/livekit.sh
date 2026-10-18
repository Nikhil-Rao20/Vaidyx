#!/usr/bin/env bash
# LiveKit for Vaidyx-TB meetings: start | stop | status | restart (localhost only, no sudo).
#
# - data/tumour_board/livekit.json {api_key, api_secret, url}: written once with a random key and secret (mode 600).
# - /data/vaidyx/tools/livekit/config.yaml: written from scripts/livekit-config.yaml.example with the keys filled in
#   (port 7880, bind 127.0.0.1, UDP 50000 to 50200, no external IP, logging warn).
# - The server: /data/vaidyx/tools/livekit/v1.13.10/livekit-server --config <config.yaml>, detached with setsid + nohup;
#   log ~/vaidyx/logs/livekit.log, pid file /data/vaidyx/tools/livekit/livekit.pid.
# Secrets are never printed.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${TB_DATA_ROOT:-$REPO/data/tumour_board}"
KEYS_JSON="$DATA_ROOT/livekit.json"
TOOLS="${LIVEKIT_TOOLS:-/data/vaidyx/tools/livekit}"
BIN="${LIVEKIT_BIN:-$TOOLS/v1.13.10/livekit-server}"
CONFIG="$TOOLS/config.yaml"
EXAMPLE="$REPO/scripts/livekit-config.yaml.example"
PIDFILE="$TOOLS/livekit.pid"
LOGDIR="${LIVEKIT_LOG_DIR:-$HOME/vaidyx/logs}"
LOG="$LOGDIR/livekit.log"
PORT="${LIVEKIT_PORT:-7880}"
URL="ws://127.0.0.1:$PORT"

random_token() {  # hex, length $1
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$(( $1 / 2 ))"; else head -c "$(( $1 / 2 ))" /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}

ensure_keys() {
  mkdir -p "$DATA_ROOT"
  if [ ! -s "$KEYS_JSON" ]; then
    local key secret
    key="API$(random_token 16)"
    secret="$(random_token 48)"
    umask 077
    printf '{"api_key": "%s", "api_secret": "%s", "url": "%s"}\n' "$key" "$secret" "$URL" > "$KEYS_JSON"
    chmod 600 "$KEYS_JSON"
    echo "wrote $KEYS_JSON (new random key and secret)"
  fi
  chmod 600 "$KEYS_JSON" 2>/dev/null || true
}

# The tools folder is writable by its owner only (the server binary and its config live there), the config is private.
lock_down() {
  chmod 755 "$TOOLS" 2>/dev/null || true
  chmod -R go-w "$TOOLS" 2>/dev/null || true
  [ -f "$CONFIG" ] && chmod 600 "$CONFIG"
  return 0
}

# The config is written by Python reading the keys file itself: the secret never appears on a command line (ps, /proc), in a
# shell variable or in the log (security review #21).
write_config() {
  mkdir -p "$TOOLS"
  [ -f "$EXAMPLE" ] || { echo "missing $EXAMPLE" >&2; exit 1; }
  umask 077
  python3 - "$KEYS_JSON" "$EXAMPLE" "$CONFIG" <<'PY'
import json, os, sys
keys_path, example, config = sys.argv[1:4]
with open(keys_path, encoding="utf-8") as f:
    keys = json.load(f)
with open(example, encoding="utf-8") as f:
    text = f.read().replace("__API_KEY__", str(keys["api_key"])).replace("__API_SECRET__", str(keys["api_secret"]))
tmp = config + ".tmp"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(text)
os.chmod(tmp, 0o600)
os.replace(tmp, config)
PY
  lock_down
  echo "wrote $CONFIG"
}

running_pid() {
  if [ -f "$PIDFILE" ]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
  fi
  return 1
}

answers() { curl -s --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null | grep -q "OK"; }

start() {
  [ -x "$BIN" ] || { echo "livekit-server not found or not executable: $BIN" >&2; exit 1; }
  ensure_keys
  write_config
  if pid="$(running_pid)"; then echo "already running (pid $pid)"; answers && echo "http://127.0.0.1:$PORT answers OK"; return 0; fi
  mkdir -p "$LOGDIR"
  setsid nohup "$BIN" --config "$CONFIG" >> "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
  sleep 2
  if pid="$(running_pid)"; then
    echo "started livekit-server (pid $pid), log $LOG"
    if answers; then echo "http://127.0.0.1:$PORT answers OK"; else echo "warning: http://127.0.0.1:$PORT did not answer yet (see $LOG)"; fi
  else
    echo "livekit-server did not stay up; last log lines:" >&2
    tail -n 20 "$LOG" >&2 || true
    exit 1
  fi
}

stop() {
  if pid="$(running_pid)"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "stopped (pid $pid)"
  else
    rm -f "$PIDFILE"
    echo "not running"
  fi
}

status() {
  lock_down
  if pid="$(running_pid)"; then echo "running (pid $pid)"; else echo "not running"; fi
  if answers; then echo "http://127.0.0.1:$PORT answers OK"; else echo "http://127.0.0.1:$PORT does not answer"; fi
  [ -s "$KEYS_JSON" ] && echo "keys: $KEYS_JSON (present)" || echo "keys: $KEYS_JSON (missing)"
  [ -f "$CONFIG" ] && echo "config: $CONFIG" || echo "config: $CONFIG (missing)"
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
