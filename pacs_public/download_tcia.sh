#!/usr/bin/env bash
# TCIA series download for the Vaidyx-TB demo PACS public-image library (Phase 1).
#
# Usage: bash pacs_public/download_tcia.sh [LIST_TSV] [DEST_ROOT]
#   LIST_TSV  default pacs_public/series_list.tsv (columns: collection, series_uid, expected, slot, patient, modality;
#             written by `python -m pacs_public.manifest --series-list` from picks.json)
#   DEST_ROOT default /data/vaidyx/tb_resources/dicom_public
#   TCIA_JOBS parallel downloads (default 3)
#
# Each series lands as DEST_ROOT/raw/<Collection>/<SeriesInstanceUID>.zip (kept as the provenance record) and is
# unzipped flat into DEST_ROOT/raw/<Collection>/<SeriesInstanceUID>/ (one .dcm per instance). The .dcm count is
# checked against the expected image count. A series whose curl or zip test fails is retried twice (three attempts).
# A finished series carries an empty marker file .complete, so re-running the script skips it.
# The NBIA server ignores HTTP Range headers, so there is no resume: a broken zip is deleted and fetched again.
# Everything is logged to DEST_ROOT/download.log. Downloaded files are untrusted data: nothing here executes them.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LIST="${1:-$HERE/series_list.tsv}"
ROOT="${2:-/data/vaidyx/tb_resources/dicom_public}"
export RAW="$ROOT/raw"
export LOG="$ROOT/download.log"
export B="https://services.cancerimagingarchive.net/nbia-api/services/v1"
JOBS="${TCIA_JOBS:-3}"
mkdir -p "$RAW"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }
export -f log

one() { # collection series_uid expected slot patient modality
  local col="$1" uid="$2" expect="$3" slot="$4" pat="$5" mod="$6"
  local dir="$RAW/$col" zip="$RAW/$col/$uid.zip" out="$RAW/$col/$uid"
  mkdir -p "$dir"
  if [ -f "$out/.complete" ]; then log "have $slot $col $mod $uid"; return 0; fi
  local attempt n bytes
  for attempt in 1 2 3; do
    if [ ! -s "$zip" ]; then
      log "GET $slot $col $pat $mod $uid attempt $attempt (expect $expect)"
      if ! curl -sS -L -m 3600 --retry 2 --retry-delay 20 -o "$zip" "$B/getImage?SeriesInstanceUID=$uid" 2>>"$LOG"; then
        log "FAIL curl $slot $uid attempt $attempt"; rm -f "$zip"; sleep 30; continue
      fi
    fi
    if ! unzip -tqq "$zip" >/dev/null 2>&1; then
      log "FAIL zip-test $slot $uid attempt $attempt"; rm -f "$zip"; sleep 30; continue
    fi
    rm -rf "$out"; mkdir -p "$out"
    if ! unzip -qq -o -j "$zip" -d "$out" >/dev/null 2>&1; then
      log "FAIL unzip $slot $uid attempt $attempt"; rm -rf "$out"; rm -f "$zip"; sleep 30; continue
    fi
    n=$(find "$out" -maxdepth 1 -type f -name '*.dcm' | wc -l)
    bytes=$(stat -c %s "$zip")
    if [ "$n" -eq 0 ]; then
      log "FAIL no-dcm $slot $uid attempt $attempt"; rm -rf "$out"; rm -f "$zip"; sleep 30; continue
    fi
    if [ "$n" -ne "$expect" ]; then
      log "MISMATCH $slot $col $mod $uid: $n dcm files, expected $expect (zip $bytes bytes)"
    else
      log "OK $slot $col $mod $uid: $n dcm files (zip $bytes bytes)"
    fi
    : > "$out/.complete"
    return 0
  done
  log "GAVE-UP $slot $col $mod $uid after 3 attempts"
  return 1
}
export -f one

log "START list=$LIST root=$ROOT jobs=$JOBS"
tail -n +2 "$LIST" | grep -v '^\s*$' | xargs -P "$JOBS" -L 1 bash -c 'one "$@"' _
total=$(tail -n +2 "$LIST" | grep -c .)
done_n=0
while IFS=$'\t' read -r col uid expect slot pat mod; do
  [ -f "$RAW/$col/$uid/.complete" ] && done_n=$((done_n + 1))
done < <(tail -n +2 "$LIST")
log "DONE $done_n of $total series complete"
echo "DONE $done_n of $total series complete"
