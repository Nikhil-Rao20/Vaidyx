#!/bin/bash
# Run the regression gate (V1: docs_Eswar/changes_v1.md section 4; V2: changes_v2.md section 6) serially on the one GPU and keep every
# log and JSON under data/tumour_board/eval/<version>/<label>/ with a gate_summary.md that compares the numbers with that version's baseline.
#   tumour_board/eval/gate.sh <label> [--v2] [--skip-ui] [--skip-evals]
# --v2 (V2 item 0.2) keeps the run under eval/v2/<label>, labels the evals v2-<label>, compares with eval/v2/baseline and adds the
# mock-hospital checks once they exist (his_mock/tests, his_mock.eval.conformance); without it the V1 behaviour is unchanged (eval/v1).
# --skip-evals leaves out the Q&A and summary evals (only needed when extraction, search, Q&A, summary or agent code changed);
# --skip-ui leaves out the browser test (only needed when the UI changed); TB_GATE_VIEWPORTS=desktop narrows it to one width. Both model servers and the app must be running.
set -u
LABEL=${1:?usage: gate.sh <label> [--v2] [--skip-ui] [--skip-evals]}; shift
SKIP_UI=0; SKIP_EVALS=0; VER=v1
for a in "$@"; do case $a in --skip-ui) SKIP_UI=1 ;; --skip-evals) SKIP_EVALS=1 ;; --v2) VER=v2 ;; esac; done
REPO=$(cd "$(dirname "$0")/../.." && pwd)
PY=${TB_PYTHON:-/data/vaidyx/venv/app/bin/python}
OUT=${TB_DATA_ROOT:-$REPO/data/tumour_board}/eval/$VER/$LABEL   # same root as tumour_board.config
PW="$(awk '{print $NF}' ~/vaidyx/.vaidyx_admin_login)"   # never printed
cd "$REPO"
if [ -e "$OUT" ]; then echo "gate: '$OUT' exists; a run never mixes with an earlier one. Use a new label or remove that folder." >&2; exit 2; fi
mkdir -p "$OUT"
rm -f "data/tumour_board/eval/qa_$VER-$LABEL.json" "data/tumour_board/eval/summary_eval_$VER-$LABEL.json" "data/tumour_board/eval/audio_eval_$VER-$LABEL.json"   # no stale JSON can be copied
echo "gate '$LABEL' started $(date -Is)" > "$OUT/run_timings.txt"
step() {  # name, command...
  local name=$1; shift; local t0=$(date +%s)
  echo "=== $name started $(date -Is)" | tee -a "$OUT/run_timings.txt"
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  echo "=== $name finished rc=$rc in $(( $(date +%s) - t0 )) s" | tee -a "$OUT/run_timings.txt"
}
# V1 item 8.3: the Tesseract unit tests skip without the binary, so its presence is a check of its own (passes when TB_OCR_ENGINE=off)
step ocr_engine "$PY" -c "from tumour_board import ocr_engine as o; import sys; print(o.engine_info() or o.unavailable_note()); sys.exit(0 if o.available() or o.turned_off() else 1)"
[ -d tumour_board/tests ] && step unit "$PY" -m pytest tumour_board/tests -q
if [ $VER = v2 ]; then  # the mock Indian hospital (V2 Phase 1): its unit tests and the NRCeS conformance check, once they exist
  [ -d his_mock/tests ] && step unit_his_mock "$PY" -m pytest his_mock/tests -q
  [ -f his_mock/eval/conformance.py ] && step conformance "$PY" -m his_mock.eval.conformance   # prints "CONFORMANCE OK: <n> resources checked", non-zero exit on failure
fi
step e2e_api "$PY" -m tumour_board.eval.e2e_api --password "$PW"
[ $SKIP_UI = 1 ] || step ui_test env LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib "$PY" -m tumour_board.eval.ui_test --password "$PW" --viewports "${TB_GATE_VIEWPORTS:-desktop,tablet,phone}" --out "$OUT/ui_shots"
if [ $SKIP_EVALS = 0 ]; then
  step qa_eval "$PY" -m tumour_board.eval.qa_eval --label "$VER-$LABEL" --prepare
  step summary_eval "$PY" -m tumour_board.eval.summary_eval --label "$VER-$LABEL"
  step audio_eval "$PY" -m tumour_board.eval.audio_eval --label "$VER-$LABEL"   # night-v3 item 4.5: the voice check (needs the audio service on :7120)
  cp -f "data/tumour_board/eval/qa_$VER-$LABEL.json" "data/tumour_board/eval/summary_eval_$VER-$LABEL.json" "data/tumour_board/eval/audio_eval_$VER-$LABEL.json" "$OUT/" 2>/dev/null
fi
step prepare_fresh "$PY" -m tumour_board.eval.prepare_cases   # leave the demo Case Files fresh for the next user
echo "gate '$LABEL' finished $(date -Is)" >> "$OUT/run_timings.txt"
"$PY" -m tumour_board.eval.gate_summary "$LABEL" --version "$VER"
echo GATE_RUN_COMPLETE
