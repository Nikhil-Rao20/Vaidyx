#!/bin/bash
# Serve the Vaidyx-TB models on the H200 (bf16, exact Hugging Face weights). Usage:
#   tumour_board/serve_models.sh reader                 # Qwen3.5-4B reader/extractor on :8101
#   tumour_board/serve_models.sh reasoner <model-dir>   # reasoning model on :8100 (default gemma-4-31B-it)
source /home/bharath.tangella/vaidyx/env.sh
export VLLM_CACHE_ROOT=/data/vaidyx/vllm_cache_tb
LOG=/home/bharath.tangella/vaidyx/Vaidyx/data/tumour_board/logs; mkdir -p $LOG
case "$1" in
  reader)
    setsid nohup vllm serve /data/vaidyx/models/Qwen3.5-4B --served-model-name reader --dtype bfloat16 --max-model-len 16384 \
      --gpu-memory-utilization 0.17 --max-num-seqs 256 --limit-mm-per-prompt '{"image":1}' --host 127.0.0.1 --port 8101 > $LOG/reader.log 2>&1 < /dev/null & ;;
  reasoner)
    M=${2:-gemma-4-31B-it}
    setsid nohup vllm serve /data/vaidyx/models/$M --served-model-name reasoner --dtype bfloat16 --max-model-len 32768 \
      --gpu-memory-utilization ${3:-0.70} --max-num-seqs 256 --limit-mm-per-prompt '{"image":0}' ${TB_SPEC:+--speculative-config "$TB_SPEC"} --host 127.0.0.1 --port 8100 > $LOG/reasoner.log 2>&1 < /dev/null & ;;
esac
