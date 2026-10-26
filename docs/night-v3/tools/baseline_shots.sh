#!/usr/bin/env bash
# The night-v3 baseline screenshots: every main screen per role (root admin, department admin, treating doctor, resident, supporting
# doctor, coordinator, member view, room screen), laptop and phone, light and dark, from the running app on :7000.
#
#   docs/night-v3/tools/baseline_shots.sh [label]        label defaults to today's date (e.g. 2026-10-27)
#
# Pictures and the log go to /data/vaidyx/night-v3/baseline/<label>/ (outside the repo). The journeys are web/tb-nik/e2e/shots/real.spec.ts
# (demo logins, synthetic Case Files, the real case filtered out). The resident login is made or checked by ensure_resident.py and read
# from /data/vaidyx/night-v3/.resident_login; no password is ever printed. TBNIK_REAL_ROLES=resident (or a list) runs a subset.
set -u

LABEL="${1:-$(date +%F)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
PY=/data/vaidyx/venv/app/bin/python
OUT="/data/vaidyx/night-v3/baseline/$LABEL"
LOGIN_FILE=/data/vaidyx/night-v3/.resident_login

case "$LABEL" in
  */*|.*|"") echo "baseline_shots: the label must be a plain name (no slash, not starting with a dot)" >&2; exit 2 ;;
esac

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:7000/api/health || true)"
if [ "$code" != "200" ]; then
  echo "baseline_shots: the app does not answer on 127.0.0.1:7000 (HTTP ${code:-none}); start it with ~/vaidyx/start_vaidyx_app.sh" >&2
  exit 1
fi

if ! "$PY" "$HERE/ensure_resident.py"; then
  echo "baseline_shots: the resident login could not be made or checked (see above)" >&2
  exit 1
fi
if [ ! -r "$LOGIN_FILE" ]; then
  echo "baseline_shots: $LOGIN_FILE is missing" >&2
  exit 1
fi
read -r TBNIK_RESIDENT_USER TBNIK_RESIDENT_PASSWORD _ < "$LOGIN_FILE"
export TBNIK_RESIDENT_USER TBNIK_RESIDENT_PASSWORD

mkdir -p "$OUT"
export TBNIK_SHOTS="$OUT"
# A subset run (TBNIK_REAL_ROLES) keeps its own log and result, so the full run's files stay as they were.
SUFFIX=""
if [ -n "${TBNIK_REAL_ROLES:-}" ]; then SUFFIX="-$(printf '%s' "$TBNIK_REAL_ROLES" | tr -c 'A-Za-z0-9-' '_')"; fi
export TBNIK_REAL_LOG="$OUT/real-log$SUFFIX.jsonl"
export PATH="/data/vaidyx/tools/node/current/bin:$PATH"
: > "$TBNIK_REAL_LOG"
: > "${TBNIK_REAL_LOG%.jsonl}-axe.jsonl"
RESULT="$OUT/playwright$SUFFIX.txt"

echo "baseline_shots: label $LABEL, pictures in $OUT${TBNIK_REAL_ROLES:+, roles $TBNIK_REAL_ROLES}"
started=$(date +%s)
( cd "$REPO/web/tb-nik" && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib npx playwright test -c e2e/playwright.config.ts real ) 2>&1 | tee "$RESULT"
status=${PIPESTATUS[0]}
unset TBNIK_RESIDENT_PASSWORD

echo
echo "==== summary ($LABEL, $(( ($(date +%s) - started) / 60 )) min, playwright exit $status) ===="
echo "PNGs per role:"
for role in treating resident supporting supporting-head coordinator dept-admin root-admin; do
  n=$(find "$OUT" -maxdepth 1 -name "real-$role-*.png" | wc -l)
  printf '  %-16s %s\n' "$role" "$n"
done
printf '  %-16s %s\n' "total" "$(find "$OUT" -maxdepth 1 -name '*.png' | wc -l)"
echo "Failed tests:"
# The list reporter marks a failed test with a cross and repeats the failures at the end; the numbered lines carry the names.
failed=$(grep -E '^\s+[0-9]+\) ' "$RESULT" | sed -E 's/\x1b\[[0-9;]*m//g' | sort -u)
if [ -n "$failed" ]; then echo "$failed" | sed 's/^/  /'; else echo "  none"; fi
echo "Page errors in the log ($TBNIK_REAL_LOG):"
for kind in pageerror console http failed overflow; do
  printf '  %-10s %s\n' "$kind" "$(grep -c "\"kind\":\"$kind\"" "$TBNIK_REAL_LOG" 2>/dev/null || true)"
done
axe_log="${TBNIK_REAL_LOG%.jsonl}-axe.jsonl"
[ -f "$axe_log" ] && printf '  %-10s %s\n' "axe" "$(wc -l < "$axe_log") serious or critical findings ($axe_log)"
exit "$status"
