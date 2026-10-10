"""Document dates eval (V1 item 3.1): the date finder against the synthetic answer key. No GPU, no model, read-only.

    python -m tumour_board.eval.dates_eval --root data/tumour_board --truth /data/vaidyx/tb_demo_corpus/truth

For each synthetic case TB-001..TB-006 (never any other folder: other cases may hold real patient data), reads every
stored cases/<id>/docs/<doc_id>/doc.json (the pages as stored, scans included as their vision transcriptions), runs
dates.document_dates over the pages and compares with the truth's report_date / event_date (matched by rel_path).

Scoring per slot (report, event):
  truth has a date  -> exact match of the ISO date (found or assumed)
  truth is null     -> the document does not state it: the finder must not claim it found one (assumed or unconfirmed)
Also counts the dates taken from a truth `ignore_dates` entry (DOB, next review, ...): must be 0.
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import dates  # noqa: E402

CASES = ("TB-001", "TB-002", "TB-003", "TB-004", "TB-005", "TB-006")


def _slot(truth_iso, iso, assumed, unconfirmed):
    if truth_iso:
        return iso == truth_iso
    return assumed or unconfirmed or not iso


def compare_case(case_dir: Path, truth: dict, dob_iso: str = ""):
    """Rows for one case: (rel_path, doc_type, result, truth entry, report ok, event ok, from ignore)."""
    tdocs = truth.get("documents") or {}
    rows = []
    for p in sorted((case_dir / "docs").glob("*/doc.json")):
        d = json.loads(p.read_text())
        rel = d.get("rel_path") or ""
        t = tdocs.get(rel)
        if t is None:
            continue
        cls = d.get("classification") or {}
        texts = [pg.get("text") or "" for pg in d.get("pages") or []]
        doc_type = cls.get("doc_type") or t.get("doc_type") or ""
        r = dates.document_dates(texts, d.get("filename") or Path(rel).name, doc_type, model_date=cls.get("report_date") or "",
                                 dob_iso=dob_iso)
        rep_ok = _slot(t.get("report_date"), r["report_date_iso"], r["report_date_assumed"], r["date_unconfirmed"])
        # a span in the answer key (admitted / discharged, treatment dates): the plan's event date is its end (discharge, completion)
        ev_ok = _slot(t.get("event_date"), r["event_date_iso"], r["event_date_assumed"], r["date_unconfirmed"]) or \
            (bool(t.get("event_end")) and _slot(t["event_end"], r["event_date_iso"], r["event_date_assumed"], r["date_unconfirmed"]))
        ign = set((t.get("ignore_dates") or {}).keys())
        from_ign = sum(1 for k in ("report_date_iso", "event_date_iso") if r[k] and r[k] in ign)
        rows.append((rel, doc_type, r, t, rep_ok, ev_ok, from_ign))
    return rows


def _fmt(iso, assumed, unconfirmed):
    if unconfirmed:
        return "unconfirmed"
    return f"{iso}{' (assumed)' if assumed else ''}" if iso else "-"


def run(root: Path, truth_dir: Path, cases=CASES, verbose=True):
    total = ok = from_ign = 0
    misses = []
    for cid in cases:
        tf, cd = truth_dir / f"{cid}.json", root / "cases" / cid
        if not tf.exists() or not cd.is_dir():
            if verbose:
                print(f"{cid}: skipped (no truth or no stored case)")
            continue
        truth = json.loads(tf.read_text())
        for rel, dt, r, t, rok, eok, fi in compare_case(cd, truth):
            total += 2
            ok += rok + eok
            from_ign += fi
            if not (rok and eok):
                misses.append((cid, rel))
            if verbose:
                mark = "ok  " if rok and eok else "MISS"
                print(f"{mark} {cid} {rel} [{dt}]\n"
                      f"     report: found {_fmt(r['report_date_iso'], r['report_date_assumed'], r['date_unconfirmed'])}"
                      f" ({r['report_date_label'] or '-'}) expected {t.get('report_date') or 'not stated'}{'' if rok else '  <-'}\n"
                      f"     event:  found {_fmt(r['event_date_iso'], r['event_date_assumed'], r['date_unconfirmed'])}"
                      f" ({r['event_date_label'] or '-'}) expected {t.get('event_date') or 'not stated'}{'' if eok else '  <-'}")
    pct = 100.0 * ok / total if total else 0.0
    if verbose:
        print(f"\nexact: {ok}/{total} slots = {pct:.1f}%   dates taken from ignore_dates: {from_ign}")
    return {"total": total, "ok": ok, "pct": pct, "from_ignore": from_ign, "misses": misses}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data/tumour_board", help="data root holding cases/TB-00x")
    ap.add_argument("--truth", default="/data/vaidyx/tb_demo_corpus/truth", help="answer key folder (TB-00x.json)")
    a = ap.parse_args()
    res = run(Path(a.root), Path(a.truth))
    sys.exit(0 if res["pct"] >= 95.0 and res["from_ignore"] == 0 else 1)


if __name__ == "__main__":
    main()
