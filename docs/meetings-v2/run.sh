#!/bin/bash
# Owner controls for the unattended meetings-v2 run (independent of VS Code).
#   docs/meetings-v2/run.sh start     start the supervisor (branch the-ui)
#   docs/meetings-v2/run.sh pause     ask for a pause: the running session finishes its current item, commits, logs and ends;
#                                        no new session starts until "resume"
#   docs/meetings-v2/run.sh resume    clear the pause and start the supervisor again; it continues from the next unfinished item
#   docs/meetings-v2/run.sh stop      stop at once (supervisor and session); the next start recovers an interrupted item
#   docs/meetings-v2/run.sh status    what is running, the plan's progress, the last log lines
# Watch: tail -f docs/meetings-v2/LOG.md and /data/vaidyx/meetings-v2/supervisor.log
cd /home/bharath.tangella/vaidyx/Vaidyx || exit 1
S=/data/vaidyx/meetings-v2; mkdir -p "$S"
running() { [ -f "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null; }
case "${1:-status}" in
  start|resume)
    [ "$(git rev-parse --abbrev-ref HEAD)" = "the-ui" ] || { echo "switch to branch the-ui first"; exit 1; }
    running && { echo "already running (pid $(cat "$S/supervisor.pid"))"; exit 0; }
    rm -f "$S/PAUSE"
    setsid nohup bash docs/meetings-v2/supervisor.sh >> "$S/supervisor.log" 2>&1 < /dev/null &
    echo $! > "$S/supervisor.pid"
    echo "supervisor started, pid $(cat "$S/supervisor.pid")" ;;
  pause)
    echo "owner asked for a pause at $(date '+%F %T')" > "$S/PAUSE"
    echo "pause requested: the current session finishes its item and ends; nothing new starts until: $0 resume" ;;
  stop)
    if running; then kill -- -"$(cat "$S/supervisor.pid")" 2>/dev/null; echo "stopped"; else echo "not running"; fi
    echo "owner stopped the run at $(date '+%F %T')" > "$S/PAUSE" ;;
  status)
    if running; then echo "supervisor: running (pid $(cat "$S/supervisor.pid"))"; else echo "supervisor: not running"; fi
    [ -f "$S/PAUSE" ] && echo "pause: $(cat "$S/PAUSE")"
    [ -f "$S/RUN_COMPLETE" ] && echo "plan: complete"
    echo "plan items: $(grep -cE '\| (done|blocked)' docs/meetings-v2/PLAN.md) finished of $(grep -cE '^\| [0-9]+\.[0-9]+\+? \|' docs/meetings-v2/PLAN.md)"
    echo "last commit: $(git log --oneline -1)"
    echo "--- supervisor"; tail -3 "$S/supervisor.log" 2>/dev/null
    echo "--- log"; tail -5 docs/meetings-v2/LOG.md ;;
  *) echo "usage: $0 start|pause|resume|stop|status"; exit 2 ;;
esac
