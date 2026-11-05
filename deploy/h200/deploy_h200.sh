#!/bin/bash
# Release a commit of main to the doctors' instance on the H200 (deployment Plan B, see deploy/README.md).
#
#   deploy/h200/deploy_h200.sh <commit>            the commit must be on origin/main and green in CI
#   deploy/h200/deploy_h200.sh <commit> --no-ci    only when CI cannot run (logged as such)
#
# The instance runs from its own pinned checkout (/data/vaidyx/tb_deploy/app, a detached git worktree), never from a
# working tree someone is editing. On a failed start the previous commit is put back and started again.
set -u
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
REPO=${VX_REPO:-$HOME/vaidyx/Vaidyx}
ROOT=${VX_DEPLOY_ROOT:-/data/vaidyx/tb_deploy}
APP=$ROOT/app
GH=${VX_GH:-/data/vaidyx/tools/gh/bin/gh}
GH_REPO=Nikhil-Rao20/Vaidyx
LOGF=$HOME/vaidyx/deploy_vm/DEPLOY_LOG.md
TARGET=${1:?usage: deploy_h200.sh <commit> [--no-ci]}
NOCI=${2:-}
note() { echo "- $(date '+%F %T') $*" >> "$LOGF"; echo "$*"; }

git -C "$REPO" fetch -q origin || { echo "fetch failed"; exit 1; }
SHA=$(git -C "$REPO" rev-parse --verify -q "$TARGET^{commit}") || { echo "unknown commit $TARGET"; exit 1; }
git -C "$REPO" merge-base --is-ancestor "$SHA" origin/main || { echo "refusing: $TARGET is not on origin/main"; exit 1; }

if [ "$NOCI" != "--no-ci" ]; then
  CI=$("$GH" api "repos/$GH_REPO/commits/$SHA/check-runs" --jq '[.check_runs[] | select(.name=="gate")] | if length==0 then "none" else (map(.conclusion) | if all(.=="success") then "success" else join(",") end) end' 2>/dev/null)
  [ "$CI" = "success" ] || { echo "refusing: CI gate for ${SHA:0:7} is '${CI:-unknown}' (wait for the green tick, or --no-ci)"; exit 1; }
fi

if [ ! -d "$APP" ]; then
  git -C "$REPO" worktree add -q --detach "$APP" "$SHA" || exit 1
  PREV=""
else
  PREV=$(git -C "$APP" rev-parse HEAD)
  [ "$PREV" = "$SHA" ] && { echo "already at ${SHA:0:7}"; exit 0; }
  [ -n "$(git -C "$APP" status --porcelain --untracked-files=no)" ] && { echo "refusing: the pinned checkout has local changes"; exit 1; }
  echo "deploying: $(git -C "$REPO" log --oneline "$PREV..$SHA" | wc -l) commits"
  git -C "$REPO" log --oneline "$PREV..$SHA" | head -20
  git -C "$APP" checkout -q --detach "$SHA" || exit 1
fi

# The tests CI cannot run (they need files kept only on the H200, deploy/ci/h200_only_tests.txt), on the new checkout.
PY=${VX_PY:-/data/vaidyx/venv/tb_deploy312/bin/python}   # the doctors' site's own environment (vx.sh)
H200_TESTS=$(grep -v '^#' "$APP/deploy/ci/h200_only_tests.txt" 2>/dev/null | grep .)
if [ -n "$H200_TESTS" ]; then
  if ! (cd "$APP" && "$PY" -m pytest -q -p no:cacheprovider $H200_TESTS > "$HOME/vaidyx/deploy_vm/logs/h200_tests.log" 2>&1); then
    echo "refusing: the H200-only tests failed (see ~/vaidyx/deploy_vm/logs/h200_tests.log)"
    if [ -n "$PREV" ]; then git -C "$APP" checkout -q --detach "$PREV"; else git -C "$REPO" worktree remove --force "$APP"; fi
    note "REFUSED ${SHA:0:7}: H200-only tests failed; checkout left at ${PREV:0:7}"
    exit 1
  fi
  echo "H200-only tests: $(tail -1 "$HOME/vaidyx/deploy_vm/logs/h200_tests.log")"
fi

# The gate and the link run from the pinned checkout too. A changed gate.py restarts the gate at once (its port is never left
# empty for the app's restart); a changed vx.sh (for example the link's port or the Python environment) restarts the gate, the
# demo hospital copy and the link, so every process runs what vx.sh now says.
VX="$APP/deploy/h200/vx.sh"
changed() { [ -n "$PREV" ] && ! git -C "$APP" diff --quiet "$PREV" "$SHA" -- "$1"; }
if changed deploy/h200/gate.py; then echo "gate.py changed: restarting the gate"; "$VX" restart-gate || echo "gate restart failed"; fi
if changed deploy/h200/vx.sh; then
  echo "vx.sh changed: restarting the gate, the demo hospital copy and the link"
  changed deploy/h200/gate.py || "$VX" restart-gate || echo "gate restart failed"
  "$VX" restart-his || echo "demo hospital restart failed"
  "$VX" restart-link || echo "link restart failed"
fi

if changed tumour_board/audio_service; then echo "speech service changed: restarting it"; "$VX" restart-audio || echo "speech service restart failed (voice off)"; fi

if "$VX" restart-app && "$VX" ensure; then
  note "deployed ${SHA:0:7} (from ${PREV:0:7}) ci=${CI:-skipped} · $("$VX" status | tr '\n' ' ')"
else
  echo "start failed: putting ${PREV:0:7} back"
  [ -n "$PREV" ] && git -C "$APP" checkout -q --detach "$PREV" && "$VX" restart-gate && "$VX" restart-app && "$VX" restart-link && "$VX" ensure
  note "FAILED ${SHA:0:7}, rolled back to ${PREV:0:7}"
  exit 1
fi
