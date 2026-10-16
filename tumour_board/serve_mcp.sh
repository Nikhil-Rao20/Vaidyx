#!/bin/bash
# Start or stop the MCP processes of Vaidyx-TB (12 Oct). Logs in data/tumour_board/logs.
#   tumour_board/serve_mcp.sh server          # Vaidyx-TB read-only MCP server on 127.0.0.1:7110 (token: data/tumour_board/mcp_token)
#   tumour_board/serve_mcp.sh demo-his        # synthetic hospital system on 127.0.0.1:7111 (token: data/tumour_board/demo_his_token)
#   tumour_board/serve_mcp.sh stop            # stop both
REPO=$(cd "$(dirname "$0")/.." && pwd); PY=${TB_PYTHON:-/data/vaidyx/venv/app/bin/python}
LOG=${TB_DATA_ROOT:-$REPO/data/tumour_board}/logs; mkdir -p "$LOG"
cd "$REPO"
case "$1" in
  server)
    ss -ltn 2>/dev/null | grep -q "127.0.0.1:${2:-7110} " && { echo "mcp server already listening on ${2:-7110}"; exit 0; }
    setsid nohup $PY -m tumour_board.mcp_server --transport http --port "${2:-7110}" > "$LOG/mcp_server.log" 2>&1 < /dev/null &
    sleep 2; tail -n 1 "$LOG/mcp_server.log" ;;
  demo-his)
    ss -ltn 2>/dev/null | grep -q "127.0.0.1:${2:-7111} " && { echo "demo-his already listening on ${2:-7111}"; exit 0; }
    setsid nohup $PY -m tumour_board.demo_data.demo_his_mcp --port "${2:-7111}" > "$LOG/demo_his.log" 2>&1 < /dev/null &
    sleep 2; tail -n 1 "$LOG/demo_his.log" ;;
  stop)
    for port in 7110 7111; do P=$(ss -ltnp 2>/dev/null | awk -v p=":$port " '$0 ~ p {print $NF}' | grep -oE "pid=[0-9]+" | cut -d= -f2 | head -1); [ -n "$P" ] && kill "$P" && echo "stopped $port"; done ;;
  *) echo "usage: $0 server|demo-his|stop [port]"; exit 1 ;;
esac
