"""Document type cross-check eval (V1 item 3.2): the keyword type against the stored model type and the answer key.
No GPU, no model, read-only.

    python -m tumour_board.eval.doctype_eval --root data/tumour_board --truth /data/vaidyx/tb_demo_corpus/truth \
        --cases TB-001,TB-002,TB-003,TB-004,TB-005,TB-006

Only the cases named with --cases are opened (default: the synthetic TB-001..TB-006; other folders may hold real patient
data). For each stored cases/<id>/docs/<doc_id>/doc.json, prints the reader model's classification.doc_type, the keyword
type with its evidence (doctype.keyword_type over the stored page texts and the filename) and, when the case has an
answer key, the truth doc_type (matched by rel_path). A case without an answer key is still listed (model vs keyword).

Summary: keyword evidence found for N of M documents, keyword = truth for K of the documents with both, and every
disagreement with the model (a document where the keyword type and the model type differ) listed for review.
Exit 0 when there are no disagreements and the keyword type equals the truth wherever both exist.
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import doctype  # noqa: E402

CASES = ("TB-001", "TB-002", "TB-003", "TB-004", "TB-005", "TB-006")


def compare_case(case_dir: Path, truth: dict | None):
    """Rows for one case: dicts with rel_path, model, keyword (keyword_type result), note (cross_check), truth doc_type ('' if none)."""
    tdocs = (truth or {}).get("documents") or {}
    rows = []
    for p in sorted((case_dir / "docs").glob("*/doc.json")):
        d = json.loads(p.read_text())
        rel = d.get("rel_path") or d.get("filename") or p.parent.name
        texts = [pg.get("text") or "" for pg in d.get("pages") or []]
        fn = d.get("filename") or Path(rel).name
        model = (d.get("classification") or {}).get("doc_type") or ""
        cc = doctype.cross_check(model, texts, fn)
        rows.append({"rel_path": rel, "model": model, "keyword": doctype.keyword_type(texts, fn), "note": cc["note"], "agree": cc["agree"],
                     "truth": (tdocs.get(rel) or {}).get("doc_type") or ""})
    return rows


def summarise(rows):
    """Counts over rows from compare_case (any number of cases)."""
    with_kw = [r for r in rows if r["keyword"]["type"]]
    with_truth = [r for r in with_kw if r["truth"]]
    disagree = [r for r in with_kw if r["model"] and r["agree"] is False]  # what the gate will act on (cross_check's verdict)
    no_model = [r for r in with_kw if not r["model"]]
    wrong = [r for r in with_truth if r["keyword"]["type"] != r["truth"]]
    return {"docs": len(rows), "with_keyword": len(with_kw), "with_truth": len(with_truth),
            "keyword_eq_truth": len(with_truth) - len(wrong), "keyword_ne_truth": wrong,
            "disagreements": disagree, "no_model_type": no_model}


def _ev(kw):
    return "; ".join(f"{e['type']} '{e['keyword']}' ({e['where']}, {e['weight']:g})" for e in kw["evidence"]) or "none"


def run(root: Path, truth_dir: Path, cases=CASES, verbose=True):
    rows = []
    for cid in cases:
        cd = root / "cases" / cid
        if not cd.is_dir():
            if verbose:
                print(f"{cid}: skipped (no stored case)")
            continue
        tf = truth_dir / f"{cid}.json"
        truth = json.loads(tf.read_text()) if tf.exists() else None
        case_rows = compare_case(cd, truth)
        for r in case_rows:
            r["case"] = cid
            kt = r["keyword"]["type"]
            mark = ("DISAGREE" if kt and r["model"] and kt != r["model"] else
                    "TRUTH?  " if kt and r["truth"] and kt != r["truth"] else
                    "ok      " if kt else "-       ")
            if verbose:
                print(f"{mark} {cid} {r['rel_path']}\n"
                      f"     model {r['model'] or '-'} | keyword {kt or '-'} | truth {r['truth'] or ('-' if truth else 'no answer key')}\n"
                      f"     evidence: {_ev(r['keyword'])}")
        rows += case_rows
    s = summarise(rows)
    if verbose:
        print(f"\nkeyword evidence found for {s['with_keyword']} of {s['docs']} documents"
              f"\nkeyword = truth for {s['keyword_eq_truth']} of {s['with_truth']} documents with both"
              f"\ndisagreements with the model: {len(s['disagreements'])}")
        for r in s["disagreements"]:
            print(f"  {r['case']} {r['rel_path']}: {r['note']}\n     evidence: {_ev(r['keyword'])}")
        for r in s["keyword_ne_truth"]:
            print(f"  keyword differs from truth: {r['case']} {r['rel_path']}: keyword {r['keyword']['type']}, truth {r['truth']}")
        if s["no_model_type"]:
            print(f"documents with keyword evidence but no model type: {len(s['no_model_type'])}")
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data/tumour_board", help="data root holding cases/<id>")
    ap.add_argument("--truth", default="/data/vaidyx/tb_demo_corpus/truth", help="answer key folder (<id>.json)")
    ap.add_argument("--cases", default=",".join(CASES), help="comma-separated case ids (only these are opened)")
    a = ap.parse_args()
    cases = [c.strip() for c in a.cases.split(",") if c.strip()]
    s = run(Path(a.root), Path(a.truth), cases)
    sys.exit(0 if not s["disagreements"] and not s["keyword_ne_truth"] else 1)


if __name__ == "__main__":
    main()
