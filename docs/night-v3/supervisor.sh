#!/bin/bash
# The night-v3 supervisor: runs one fresh headless Claude session per phase of docs/night-v3/PLAN.md until the plan is finished, blocked
# or stuck (adapted from Eswar's docs_Eswar/overnight_supervisor.sh, which ran V1 and V2). Usage-limit hits are waited out and retried;
# they never count as "stuck". Started by run_night.sh. Round output in /data/vaidyx/night-v3/runs (outside the repo).
cd /home/bharath.tangella/vaidyx/Vaidyx || exit 1
B=${CLAUDE_BIN:-$(ls -d ~/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude | sort -V | tail -1)}
PROMPT=${PROMPT:-docs/night-v3/PROMPT.md}
LOG=${LOG:-docs/night-v3/LOG.md}
DONE=${DONE:-/data/vaidyx/night-v3/RUN_COMPLETE}
RUNS=/data/vaidyx/night-v3/runs
MAX_PRODUCTIVE=${MAX_PRODUCTIVE:-30}    # productive rounds (sessions that actually worked)
MAX_WAIT=${MAX_WAIT:-28800}             # give up after 8 h of continuous fast failures (e.g. a weekly limit)
SLEEP_WAIT=${SLEEP_WAIT:-1200}          # retry every 20 min while waiting for a limit reset
SLEEP_OK=${SLEEP_OK:-60}
PRIMARY=${MODEL:-fable}                 # orchestrator model; falls back to FALLBACK_MODEL when it fails fast
FALLBACK_MODEL=${FALLBACK_MODEL:-opus}
MODEL=$PRIMARY
ts() { date '+%F %T'; }
mkdir -p "$RUNS"
rm -f "$DONE"
[ "$(git rev-parse --abbrev-ref HEAD)" = "night-v3" ] || { echo "$(ts) not on branch night-v3: stopping"; exit 1; }
productive=0; stalls=0; waiting_since=0; r=0
while [ "$productive" -lt "$MAX_PRODUCTIVE" ]; do
  [ -f "$DONE" ] && { echo "$(ts) plan complete"; break; }
  r=$((r+1)); head_before=$(git rev-parse HEAD); start=$(date +%s); TS=$(date +%Y%m%d_%H%M%S)
  out="$RUNS/round_${r}_$TS"
  echo "$(ts) round $r start (HEAD ${head_before:0:7}, model $MODEL)"
  "$B" -p "$(cat "$PROMPT")" \
    --model "$MODEL" --effort xhigh --permission-mode auto \
    --output-format stream-json --verbose > "$out.jsonl" 2> "$out.err" < /dev/null
  rc=$?; now=$(date +%s); dur=$((now - start)); head_after=$(git rev-parse HEAD)
  echo "$(ts) round $r exit=$rc duration=${dur}s HEAD ${head_after:0:7}"
  [ -f "$DONE" ] && { echo "$(ts) plan complete"; break; }
  if [ "$dur" -lt 300 ] && [ "$head_after" = "$head_before" ]; then
    # fast failure: most likely a usage limit (or a transient error); wait and retry, don't count it
    reason=$(grep -hoiE "usage limit[^\"]{0,80}|rate limit[^\"]{0,80}|limit reached[^\"]{0,80}" "$out.jsonl" "$out.err" 2>/dev/null | head -1)
    if [ "$MODEL" != "$FALLBACK_MODEL" ]; then
      echo "$(ts) $MODEL failing fast (${reason:-unknown}): switching to $FALLBACK_MODEL"
      printf '\n- `[DECISION]` %s %s limit or error (%s): switched the run to %s (xhigh)\n' "$(ts)" "$MODEL" "${reason:-see $RUNS}" "$FALLBACK_MODEL" >> "$LOG"
      MODEL=$FALLBACK_MODEL; continue
    fi
    [ "$waiting_since" -eq 0 ] && waiting_since=$now
    waited=$((now - waiting_since))
    if [ "$waited" -ge "$MAX_WAIT" ]; then
      echo "$(ts) still failing after ${waited}s: stopping (${reason:-unknown reason})"
      printf '\n- `[BLOCKED]` %s supervisor stopped: sessions kept failing for %s s (%s). Restart with docs/night-v3/run_night.sh\n' "$(ts)" "$waited" "${reason:-see $RUNS}" >> "$LOG"
      break
    fi
    echo "$(ts) waiting for reset (${reason:-fast failure}), retry in ${SLEEP_WAIT}s"
    sleep "$SLEEP_WAIT"
    MODEL=$PRIMARY   # after a wait, try the primary model first again (falls back at once if still limited)
    continue
  fi
  waiting_since=0; productive=$((productive+1))
  if [ "$head_after" = "$head_before" ]; then stalls=$((stalls+1)); else stalls=0; fi
  if [ "$stalls" -ge 3 ]; then
    echo "$(ts) no new commit in 3 working rounds: stopping"
    printf '\n- `[BLOCKED]` %s supervisor stopped: no new commit in 3 working rounds (see %s)\n' "$(ts)" "$RUNS" >> "$LOG"
    break
  fi
  sleep "$SLEEP_OK"
done
echo "$(ts) supervisor finished"
