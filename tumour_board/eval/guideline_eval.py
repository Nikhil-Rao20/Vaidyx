"""Guideline search eval (V1 item 5.3): the gold query set against the guideline index. A measurement, not a gate.

    python -m tumour_board.eval.guideline_eval [--gold PATH] [--out DIR] [--chunking fixed|section] [--k 5] [--check-gold]

Gold set: tumour_board/eval/guideline_gold.json (India-first; expected files / pages found by reading the guideline text,
judged once by Eswar). For each query the ranking measured is what guidelines.search_grouped ranks: the index search
(60 candidates, India-first boost, cancer boost) with bibliography chunks dropped, cut to the first k.

Hit rule: a top-k result is a hit when its file equals an expected file and its page span [page, page_end or page]
overlaps the expected pages (a section chunk may span pages). Any one expected answer counts.

Metrics: hit@k (overall and per kind), MRR of the first hit, India share (Indian results in the top k / k, mean over
queries; overall and for the indian_expected queries) and India first (share of indian_expected queries whose rank-1
result is region India). Writes guideline_eval.json and guideline_eval.md into --out (default
<data root>/eval/v1/guideline/). Exit 0 (5.4 compares its hit@k with this baseline).

--check-gold: no index, no model. Checks the gold file (schema, every expected file exists, every evidence snippet is on
one of its listed pages as guidelines._read numbers them, whitespace-normalised). Prints problems, exit 1 if any.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import config, guidelines, protocol  # noqa: E402

GOLD = Path(__file__).resolve().parent / "guideline_gold.json"
KINDS = ("case", "board")
CANDIDATES = 60  # what search_grouped asks the index for before dropping bibliography chunks


def norm(t):
    return re.sub(r"\s+", " ", t or "").strip()


def load_gold(path=GOLD):
    return json.loads(Path(path).read_text())


def span(h):
    """Page span of a result: [page, page_end]; a missing page_end means the chunk sits on one page."""
    lo = int(h.get("page") or 0)
    return lo, int(h.get("page_end") or lo)


def is_hit(h, expected):
    lo, hi = span(h)
    return any(h.get("file") == e["file"] and any(lo <= int(p) <= hi for p in e["pages"]) for e in expected)


def first_hit_rank(top, expected):
    """1-based rank of the first hit in the ranked results, or None."""
    return next((i for i, h in enumerate(top, 1) if is_hit(h, expected)), None)


def india_share(top, k):
    return sum(1 for h in top[:k] if h.get("region") == "India") / k if k else 0.0


def ranked(idx, query, cancer, k):
    """The first k results as search_grouped ranks them (bibliography chunks dropped)."""
    return [h for h in idx.search(query, CANDIDATES, cancer) if not guidelines._is_reference_list(h["text"])][:k]


def score_query(entry, top, k):
    top = top[:k]
    rank = first_hit_rank(top, entry["expected"])
    return {"id": entry["id"], "query": entry["query"], "cancer": entry.get("cancer"), "kind": entry["kind"],
            "indian_expected": bool(entry.get("indian_expected")), "rank": rank, "hit": rank is not None,
            "rr": 1.0 / rank if rank else 0.0, "india_share": india_share(top, k),
            "rank1_india": bool(top) and top[0].get("region") == "India",
            "top": [{"file": h.get("file"), "page": h.get("page"), "page_end": h.get("page_end") or h.get("page"),
                     "region": h.get("region"), "score": h.get("score"), "hit": is_hit(h, entry["expected"])} for h in top]}


def _mean(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def summarise(rows, k):
    ind = [r for r in rows if r["indian_expected"]]
    return {"k": k, "n": len(rows), f"hit@{k}": _mean(r["hit"] for r in rows),
            f"hit@{k}_by_kind": {kd: _mean(r["hit"] for r in rows if r["kind"] == kd) for kd in KINDS if any(r["kind"] == kd for r in rows)},
            "mrr": _mean(r["rr"] for r in rows), "india_share": _mean(r["india_share"] for r in rows),
            "india_share_indian_expected": _mean(r["india_share"] for r in ind), "n_indian_expected": len(ind),
            "india_first": _mean(r["rank1_india"] for r in ind)}


def _pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def render_md(summary, rows, meta):
    k = summary["k"]
    lines = [f"# Guideline search eval ({meta.get('chunking') or 'default index'}, k = {k})", "",
             f"Gold: `{meta['gold']}` (version {meta.get('version')}, judged by {meta.get('judged_by') or 'not yet judged'}). "
             f"Run {meta['when']}, {meta.get('chunks', '?')} chunks.", "",
             "| Metric | Value |", "|---|---|",
             f"| hit@{k} | {_pct(summary[f'hit@{k}'])} ({sum(r['hit'] for r in rows)} / {summary['n']}) |"]
    for kd, v in summary[f"hit@{k}_by_kind"].items():
        lines.append(f"| hit@{k}, {kd} queries | {_pct(v)} |")
    lines += [f"| MRR | {summary['mrr'] if summary['mrr'] is not None else '-'} |",
              f"| India share of top {k} (all queries) | {_pct(summary['india_share'])} |",
              f"| India share of top {k} (India-expected queries) | {_pct(summary['india_share_indian_expected'])} |",
              f"| India first (rank 1 Indian, India-expected queries) | {_pct(summary['india_first'])} |", "",
              "| ID | Kind | India exp. | First hit | India share | Top results (file p.page, region) |", "|---|---|---|---|---|---|"]
    for r in rows:
        tops = "<br>".join(f"{'**' if t['hit'] else ''}{t['file']} p.{t['page']}{'-' + str(t['page_end']) if t['page_end'] != t['page'] else ''}"
                           f"{'**' if t['hit'] else ''} ({t['region']})" for t in r["top"]) or "-"
        lines.append(f"| {r['id']} | {r['kind']} | {'yes' if r['indian_expected'] else 'no'} | {r['rank'] or '-'} | "
                     f"{_pct(r['india_share'])} | {tops} |")
    lines += ["", "Hits in bold. Queries:", ""] + [f"- {r['id']}: {r['query']}" for r in rows]
    return "\n".join(lines) + "\n"


def validate_schema(gold):
    """Problems with the gold file's structure (no file access)."""
    probs = []
    qs = gold.get("queries") or []
    if not 20 <= len(qs) <= 30:
        probs.append(f"{len(qs)} queries (expected 20 to 30)")
    ids = [q.get("id") for q in qs]
    probs += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    cancers = {p["id"] for p in protocol.list_protocols()}
    for q in qs:
        qid = q.get("id")
        if not q.get("query"):
            probs.append(f"{qid}: empty query")
        if q.get("kind") not in KINDS:
            probs.append(f"{qid}: kind {q.get('kind')!r} not in {KINDS}")
        if q.get("cancer") is not None and q["cancer"] not in cancers:
            probs.append(f"{qid}: cancer {q['cancer']!r} is not a protocol id")
        if not isinstance(q.get("indian_expected"), bool):
            probs.append(f"{qid}: indian_expected must be true or false")
        if not q.get("expected"):
            probs.append(f"{qid}: no expected answers")
        for e in q.get("expected") or []:
            if not e.get("file") or not e.get("pages") or not all(isinstance(p, int) and p >= 1 for p in e["pages"]) or not e.get("evidence"):
                probs.append(f"{qid}: expected entry needs file, pages (1-based ints) and evidence: {e}")
    return probs


def check_evidence(gold, root=None, reader=None):
    """Problems with expected files / evidence snippets. reader(path) -> [(i, text)] as guidelines._read (page = i + 1)."""
    root = Path(root or config.GUIDELINE_DIR)
    reader = reader or guidelines._read
    cache, probs = {}, []
    for q in gold.get("queries") or []:
        for e in q.get("expected") or []:
            p = root / e["file"]
            if not p.is_file():
                probs.append(f"{q['id']}: missing file {e['file']}")
                continue
            if e["file"] not in cache:
                cache[e["file"]] = {i + 1: norm(t) for i, t in reader(p)}
            pages = cache[e["file"]]
            bad = [n for n in e["pages"] if n not in pages]
            if bad:
                probs.append(f"{q['id']}: {e['file']} has no page {bad} (has {len(pages)})")
            ev = norm(e["evidence"])
            if not any(ev in pages.get(n, "") for n in e["pages"]):
                probs.append(f"{q['id']}: evidence not on {e['file']} pages {e['pages']}: {e['evidence'][:80]!r}")
    return probs


def run(gold_path=GOLD, out=None, chunking=None, k=5, idx=None, verbose=True):
    gold = load_gold(gold_path)
    if idx is None:
        idx = guidelines.GuidelineIndex(chunking=chunking) if chunking else guidelines.index()
    t0 = time.time()
    rows = [score_query(q, ranked(idx, q["query"], q.get("cancer"), k), k) for q in gold["queries"]]
    summary = summarise(rows, k)
    meta = {"gold": str(gold_path), "version": gold.get("version"), "judged_by": gold.get("judged_by"), "chunking": chunking,
            "chunks": len(getattr(idx, "chunks", []) or []), "when": time.strftime("%Y-%m-%d %H:%M"), "seconds": round(time.time() - t0, 1)}
    if out:
        out = Path(out); out.mkdir(parents=True, exist_ok=True)
        (out / "guideline_eval.json").write_text(json.dumps({"meta": meta, "summary": summary, "queries": rows}, indent=2))
        (out / "guideline_eval.md").write_text(render_md(summary, rows, meta))
    if verbose:
        for r in rows:
            print(f"{'hit ' if r['hit'] else 'MISS'} {r['id']} [{r['kind']}{', India' if r['indian_expected'] else ''}] "
                  f"rank {r['rank'] or '-'} India {_pct(r['india_share'])}  {r['query'][:70]}")
        print(f"\nhit@{k} {_pct(summary[f'hit@{k}'])} ({' / '.join(f'{kd} {_pct(v)}' for kd, v in summary[f'hit@{k}_by_kind'].items())})"
              f"  MRR {summary['mrr']}  India share {_pct(summary['india_share'])} (India-expected {_pct(summary['india_share_indian_expected'])})"
              f"  India first {_pct(summary['india_first'])}")
        if out:
            print(f"written: {out / 'guideline_eval.json'}, {out / 'guideline_eval.md'}")
    return {"summary": summary, "queries": rows, "meta": meta}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", default=str(GOLD), help="gold query file")
    ap.add_argument("--out", default=None, help="output folder (default <data root>/eval/v1/guideline)")
    ap.add_argument("--chunking", choices=("fixed", "section"), default=None, help="build GuidelineIndex(chunking=...) instead of the default index")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--check-gold", action="store_true", help="only check the gold file against the guideline text (no index)")
    a = ap.parse_args()
    if a.check_gold:
        gold = load_gold(a.gold)
        probs = validate_schema(gold) + check_evidence(gold)
        n = len(gold.get("queries") or [])
        for p in probs:
            print("PROBLEM", p)
        print(f"{n} queries, {sum(len(q.get('expected') or []) for q in gold.get('queries') or [])} expected answers: "
              f"{'OK' if not probs else f'{len(probs)} problem(s)'}")
        sys.exit(1 if probs else 0)
    run(a.gold, a.out or config.DATA_ROOT / "eval" / "v1" / "guideline", a.chunking, a.k)
    sys.exit(0)


if __name__ == "__main__":
    main()
