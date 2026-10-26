#!/bin/bash
# Starts the unattended night-v3 run on the server (independent of VS Code).
# Watch:  tail -f docs/night-v3/LOG.md                     (progress, Morning summary at the top)
#         tail -f /data/vaidyx/night-v3/supervisor.log     (rounds)
# Stop:   kill -- -$(cat /data/vaidyx/night-v3/supervisor.pid)
cd /home/bharath.tangella/vaidyx/Vaidyx || exit 1
[ "$(git rev-parse --abbrev-ref HEAD)" = "night-v3" ] || { echo "switch to branch night-v3 first"; exit 1; }
mkdir -p /data/vaidyx/night-v3
setsid nohup bash docs/night-v3/supervisor.sh >> /data/vaidyx/night-v3/supervisor.log 2>&1 < /dev/null &
echo $! > /data/vaidyx/night-v3/supervisor.pid
echo "supervisor started, pid $(cat /data/vaidyx/night-v3/supervisor.pid)"
