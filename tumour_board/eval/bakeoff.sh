#!/bin/bash
# Serve each candidate model in turn on :8100 (bf16) and run the reader/extractor bake-off. Logs: data/tumour_board/eval/
cd "$(dirname "$0")/../.."
source /home/bharath.tangella/vaidyx/env.sh
export VLLM_CACHE_ROOT=/data/vaidyx/vllm_cache_tb
LOG=data/tumour_board/eval; mkdir -p $LOG
run() {  # key path vision(1/0) chat_kwargs_json
  key=$1; path=$2; vis=$3; kw=$4
  mm=(); [ "$vis" = 1 ] && mm=(--limit-mm-per-prompt '{"image":1}')
  setsid vllm serve /data/vaidyx/models/$path --served-model-name candidate --dtype bfloat16 --max-model-len 16384 \
      --gpu-memory-utilization 0.88 "${mm[@]}" --host 127.0.0.1 --port 8100 > $LOG/serve_$key.log 2>&1 &
  spid=$!
  for i in $(seq 1 180); do curl -s localhost:8100/v1/models >/dev/null && break; kill -0 $spid 2>/dev/null || break; sleep 5; done
  if curl -s localhost:8100/v1/models >/dev/null; then
    BAKEOFF_VISION=$vis BAKEOFF_CHAT_KWARGS="$kw" /data/vaidyx/venv/app/bin/python -m tumour_board.eval.bakeoff --model $key 2>&1 | tail -4 | tee -a $LOG/bakeoff_summary.txt
  else echo "[$key] server failed to start" | tee -a $LOG/bakeoff_summary.txt; fi
  kill -TERM -- -$spid 2>/dev/null; for i in $(seq 1 60); do [ $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) -lt 1000 ] && break; sleep 2; done
}
for spec in "$@"; do IFS=, read -r key path vis kw <<< "$spec"; run "$key" "$path" "$vis" "${kw:-null}"; done
