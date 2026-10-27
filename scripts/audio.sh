#!/usr/bin/env bash
# The Vaidyx-TB audio service (speech to text and text to speech): start | stop | status | restart.
# Localhost only (127.0.0.1:7120), never tunnelled. Runs in /data/vaidyx/venv/audio; models from the local cache only.
# Log: ~/vaidyx/logs/audio.log (one line per request: time, route, status, seconds, engine, device, took_ms, bytes; never audio
# or text). The shared token: data/tumour_board/audio_token.json {"token": "..."}, written once with a random 48-hex token
# (mode 600); never printed, never on a command line, never in the environment of the service.
# Usage: scripts/audio.sh start|stop|status|restart [--device auto|cuda|cpu] [--port N]
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY=/data/vaidyx/venv/audio/bin/python
LOGS=~/vaidyx/logs
NV=/data/vaidyx/venv/audio/lib/python3.10/site-packages/nvidia
ESPEAK=/data/vaidyx/tools/espeak-ng
TOKEN_FILE="${TB_AUDIO_TOKEN_FILE:-$REPO/data/tumour_board/audio_token.json}"
PORT=7120
DEVICE=auto

cmd=${1:-status}; shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --device) DEVICE="${2:-auto}"; shift 2 ;;
    --port) PORT="${2:-7120}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
case "$DEVICE" in auto|cuda|cpu) ;; *) echo "--device must be auto, cuda or cpu" >&2; exit 2 ;; esac
case "$PORT" in ''|*[!0-9]*) echo "--port must be a number" >&2; exit 2 ;; esac

port_pid() { ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p"$" {print $NF}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

random_token() {  # hex, length $1
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$(( $1 / 2 ))"; else head -c "$(( $1 / 2 ))" /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}

ensure_token() {
  mkdir -p "$(dirname "$TOKEN_FILE")"
  if [ ! -s "$TOKEN_FILE" ]; then
    (umask 077; printf '{"token": "%s"}\n' "$(random_token 48)" > "$TOKEN_FILE")
    echo "audio: wrote $TOKEN_FILE (new random token)"
  fi
  chmod 600 "$TOKEN_FILE" 2>/dev/null || true
}

start() {
  if [ -n "$(port_pid "$PORT")" ]; then echo "audio: already on :$PORT"; return; fi
  [ -x "$PY" ] || { echo "audio: $PY not found" >&2; exit 1; }
  ensure_token
  mkdir -p "$LOGS"
  (cd "$REPO" && \
    LD_LIBRARY_PATH="$NV/cublas/lib:$NV/cudnn/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    PHONEMIZER_ESPEAK_LIBRARY="$ESPEAK/lib64/libespeak-ng.so" ESPEAK_DATA_PATH="$ESPEAK/share/espeak-ng-data" \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TB_AUDIO_TOKEN_FILE="$TOKEN_FILE" \
    setsid -f nohup "$PY" -m tumour_board.audio_service --host 127.0.0.1 --port "$PORT" --device "$DEVICE" \
      > "$LOGS/audio.log" 2>&1 < /dev/null)
  # setsid -f forks, so the service is never this shell's child: no subshell lingers holding the caller's output open.
  local waited=0
  until curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/health"; do
    sleep 1; waited=$((waited + 1))
    if [ "$waited" -ge 30 ]; then echo "audio: did not answer in 30 s (see $LOGS/audio.log)"; return 1; fi
  done
  # The first load of both engines takes a while; ?warm=1 answers once they are loaded.
  local health
  health="$(curl -s --max-time $((180 - waited)) "http://127.0.0.1:$PORT/health?warm=1")"
  if [ -z "$health" ]; then echo "audio: listening on :$PORT, engines still loading (see $LOGS/audio.log)"; return 0; fi
  printf '%s' "$health" | python3 -c 'import json,sys
h=json.load(sys.stdin); s,t=h["stt"],h["tts"]
print("audio: up on :'"$PORT"' (speech to text %s %s %s, text to speech %s %s, espeak-ng fallback %s)" % (
    s["engine"], s["state"], s["device"], t["state"], t["device"], t.get("espeak_fallback")))'
}

stop() {
  local p
  p="$(port_pid "$PORT")"
  if [ -z "$p" ]; then echo "audio: not running"; return; fi
  kill "$p" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
  kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
  echo "audio: stopped"
}

status() {
  if [ -n "$(port_pid "$PORT")" ]; then echo "audio: listening on :$PORT"; else echo "audio: not running (:$PORT)"; fi
}

case "$cmd" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "usage: $0 start|stop|status|restart [--device auto|cuda|cpu] [--port N]"; exit 2 ;;
esac
