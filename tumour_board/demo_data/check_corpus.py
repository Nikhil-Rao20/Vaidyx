"""Self-check of a generated SYNTHETIC corpus against its answer key (no model calls, no GPU).

For TB-004 onwards and the intake batches it checks that:
  - every identity value, field value, report / event date and ignore-date in the answer key is printed in the document
  - docstatus reads the status and signature the way the answer key says
  - every readable document carries the SYNTHETIC marker, and the corrupted file really cannot be opened
For TB-001..003 it checks status and signature only (their answer keys are older).

Run with the app environment (needs pypdf and the tumour_board package):
  PYTHONPATH=<repo> /data/vaidyx/venv/app/bin/python tumour_board/demo_data/check_corpus.py --corpus <out>
"""
import argparse, json, logging, re, sys, zipfile
from pathlib import Path

logging.getLogger("pypdf").setLevel(logging.ERROR)  # the corrupted fixture makes pypdf log "EOF marker not found"

# Known differences in the original answer keys, kept unchanged by V1-0.5 (reported, not counted as problems).
KNOWN = {("TB-002", "pathology/her2_fish_addendum_2026-08-25.pdf"):
         "answer key says FINAL; the report prints 'Report status: FINAL (AMENDED)', which docstatus reads as AMENDED (also counts as final)"}


def doc_text(p, ref):
    """Text of one document: reference text for image documents, else what the file holds; None if it cannot be read."""
    if ref.exists():
        return ref.read_text()
    if p.suffix == ".pdf":
        from pypdf import PdfReader
        try:
            return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
        except Exception:
            return None
    if p.suffix == ".docx":
        from tumour_board import ingest
        return ingest._docx_text(p)
    if p.suffix == ".xlsx":
        z = zipfile.ZipFile(p)
        return "\n".join(re.sub(r"<[^>]+>", " ", z.read(n).decode()) for n in z.namelist() if n.startswith("xl/worksheets/"))
    if p.suffix == ".txt":
        return p.read_text()
    return None  # an image without reference text (TB-001..003 scans keep theirs in the live corpus)


def _dmy(iso):
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _norm(s):
    return " ".join(str(s).split()).lower()


def check(out):
    from tumour_board import docstatus
    out, problems, n = Path(out), [], 0
    for tf in sorted((out / "truth").glob("*.json")):
        t = json.loads(tf.read_text())
        if tf.stem == "intake":
            items = [("intake", out / "intake" / rel, rel, tr, True) for rel, tr in t["files"].items()]
        else:
            new = t["case_id"] not in ("TB-001", "TB-002", "TB-003")
            items = [(t["case_id"], out / grp / t["case_id"] / rel, rel, tr, new)
                     for grp, key in (("cases", "documents"), ("arrivals", "arrivals")) for rel, tr in t[key].items()]
        for cid, path, rel, tr, full in items:
            n += 1
            txt = doc_text(path, out / "truth" / "reference_text" / cid / (rel + ".txt"))
            if tr.get("expected") == "failed":
                if txt is not None:
                    problems.append(f"{cid} {rel}: should not open, but it did")
                continue
            if txt is None:
                if full:
                    problems.append(f"{cid} {rel}: no text to check")
                continue
            st, _, _ = docstatus.detect_status(txt)
            sg, _ = docstatus.detect_signature(txt)
            if st != tr["status"] and (cid, rel) in KNOWN:
                print(f"note: {cid} {rel}: {KNOWN[(cid, rel)]}")
            elif st != tr["status"]:
                problems.append(f"{cid} {rel}: docstatus reads {st}, answer key says {tr['status']}")
            if (sg == "yes") != bool(tr["signed"]):
                problems.append(f"{cid} {rel}: docstatus signature {sg}, answer key signed={tr['signed']}")
            if not full:
                continue
            flat = _norm(txt)
            want = list(tr.get("identity", {}).values()) + [v for v in tr.get("fields", {}).values() if v] + list(tr.get("other_values", {}).values())
            want += [_dmy(tr[k]) for k in ("report_date", "event_date", "event_end") if tr.get(k)] + [_dmy(k) for k in tr.get("ignore_dates", {})]
            miss = [w for w in want if _norm(w) not in flat]
            if miss:
                problems.append(f"{cid} {rel}: not printed {miss}")
            if "synthetic" not in flat:
                problems.append(f"{cid} {rel}: no SYNTHETIC marker")
    return n, problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--corpus", required=True)
    n, problems = check(ap.parse_args().corpus)
    print("\n".join(problems) or "no problems", f"\n{n} documents checked, {len(problems)} problems")
    sys.exit(1 if problems else 0)
