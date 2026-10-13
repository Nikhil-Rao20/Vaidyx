#!/bin/bash
# The mock PACS (V2 item 1.7): Orthanc 1.13.0 (official Linux Standard Base binary) with the DICOMweb 1.24 and OHIF 1.8 plugins,
# unpacked under /data/vaidyx/tools/orthanc/ (no Docker, no sudo, no install). Listens on 127.0.0.1:8042 only; never tunnelled.
#   his_mock/orthanc.sh start    # start if not already listening on 8042
#   his_mock/orthanc.sh stop     # stop by the PID that holds port 8042
#   his_mock/orthanc.sh status   # version, plugins, study count
#   his_mock/orthanc.sh reset    # delete every study (synthetic data only; the next his_mock build re-uploads them)
ORTHANC_HOME=${ORTHANC_HOME:-/data/vaidyx/tools/orthanc}
PORT=${ORTHANC_PORT:-8042}
URL="http://127.0.0.1:$PORT"
pid_on_port() { ss -ltnp 2>/dev/null | awk -v p="127.0.0.1:$PORT " '$0 ~ p {print $NF}' | grep -oE "pid=[0-9]+" | cut -d= -f2 | head -1; }
case "$1" in
  start)
    if [ -n "$(pid_on_port)" ]; then echo "orthanc already listening on $PORT (pid $(pid_on_port))"; exit 0; fi
    [ -x "$ORTHANC_HOME/bin/Orthanc" ] || { echo "Orthanc binary missing: $ORTHANC_HOME/bin/Orthanc (see docs_Eswar/research/prep_v2/orthanc_setup.md)"; exit 1; }
    mkdir -p "$ORTHANC_HOME/logs" "$ORTHANC_HOME/db/storage" "$ORTHANC_HOME/db/index"
    (cd "$ORTHANC_HOME" && setsid nohup ./bin/Orthanc config/orthanc.json > logs/orthanc.log 2>&1 < /dev/null &)
    for i in $(seq 1 30); do curl -s -m 2 -o /dev/null "$URL/system" && { echo "orthanc started on $PORT (pid $(pid_on_port))"; exit 0; }; sleep 1; done
    echo "orthanc did not answer on $PORT within 30 s; see $ORTHANC_HOME/logs/orthanc.log"; exit 1 ;;
  stop)
    P=$(pid_on_port); [ -n "$P" ] && kill "$P" && echo "stopped orthanc (pid $P)" || echo "orthanc not running" ;;
  status)
    curl -s -m 5 "$URL/system" | grep -E '"(Name|Version)"' || { echo "orthanc not running on $PORT"; exit 1; }
    printf "plugins: "; curl -s -m 5 "$URL/plugins"; echo
    printf "studies: "; curl -s -m 5 "$URL/studies" | grep -c '"'; exit 0 ;;
  reset)
    for s in $(curl -s -m 10 "$URL/studies" | tr -d '[]", ' ); do curl -s -m 30 -o /dev/null -X DELETE "$URL/studies/$s"; done
    echo "studies left: $(curl -s -m 5 "$URL/studies" | grep -c '"')" ;;
  *) echo "usage: his_mock/orthanc.sh start|stop|status|reset"; exit 2 ;;
esac
