#!/bin/bash
# Run the V1 regression gate (docs_Eswar/changes_v1.md section 4) serially on the one GPU and keep every log and JSON under
# data/tumour_board/eval/v1/<label>/ with a README.md that compares the numbers with the baseline.
#   tumour_board/eval/gate.sh <label> [--skip-ui] [--skip-evals]
# --skip-evals leaves out the Q&A and summary evals (only needed when extraction, search, Q&A, summary or agent code changed);
# --skip-ui leaves out the browser test (only needed when the UI changed). Both model servers and the app must be running.
set -u
LABEL=${1:?usage: gate.sh <label> [--skip-ui] [--skip-evals]}; shift
SKIP_UI=0; SKIP_EVALS=0
for a in "$@"; do case $a in --skip-ui) SKIP_UI=1 ;; --skip-evals) SKIP_EVALS=1 ;; esac; done
REPO=$(cd "$(dirname "$0")/../.." && pwd)
PY=${TB_PYTHON:-/data/vaidyx/venv/app/bin/python}
OUT=${TB_DATA_ROOT:-$REPO/data/tumour_board}/eval/v1/$LABEL   # same root as tumour_board.config
PW="$(awk '{print $NF}' ~/vaidyx/.vaidyx_admin_login)"   # never printed
cd "$REPO"
if [ -e "$OUT" ]; then echo "gate: '$OUT' exists; a run never mixes with an earlier one. Use a new label or remove that folder." >&2; exit 2; fi
mkdir -p "$OUT"
rm -f "data/tumour_board/eval/qa_v1-$LABEL.json" "data/tumour_board/eval/summary_eval_v1-$LABEL.json"   # no stale JSON can be copied
echo "gate '$LABEL' started $(date -Is)" > "$OUT/run_timings.txt"
step() {  # name, command...
  local name=$1; shift; local t0=$(date +%s)
  echo "=== $name started $(date -Is)" | tee -a "$OUT/run_timings.txt"
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  echo "=== $name finished rc=$rc in $(( $(date +%s) - t0 )) s" | tee -a "$OUT/run_timings.txt"
}
[ -d tumour_board/tests ] && step unit "$PY" -m pytest tumour_board/tests -q
step e2e_api "$PY" -m tumour_board.eval.e2e_api --password "$PW"
[ $SKIP_UI = 1 ] || step ui_test env LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib "$PY" -m tumour_board.eval.ui_test --password "$PW" --out "$OUT/ui_shots"
if [ $SKIP_EVALS = 0 ]; then
  step qa_eval "$PY" -m tumour_board.eval.qa_eval --label "v1-$LABEL" --prepare
  step summary_eval "$PY" -m tumour_board.eval.summary_eval --label "v1-$LABEL"
  cp -f "data/tumour_board/eval/qa_v1-$LABEL.json" "data/tumour_board/eval/summary_eval_v1-$LABEL.json" "$OUT/" 2>/dev/null
fi
step prepare_fresh "$PY" -m tumour_board.eval.prepare_cases   # leave the demo Case Files fresh for the next user
echo "gate '$LABEL' finished $(date -Is)" >> "$OUT/run_timings.txt"
"$PY" -m tumour_board.eval.gate_summary "$LABEL"
echo GATE_RUN_COMPLETE
