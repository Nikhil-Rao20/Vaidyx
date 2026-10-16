"""Near-match items in briefs and the summary (V1 item 6.5), measured on the same model output both ways. A measurement, not a gate.

Every statement the agents and the summary write is verified twice: exact only (today's rule, what is stored) and with near-match on
(TB_NEAR_MATCH=1: a quote that matches its source only approximately, score >= 92, same numbers, >= 12 characters, is kept and flagged).
The report lists, per brief and summary, what each rule keeps, the briefs left empty by the exact rule, and every approximate item with
the model's quote beside the source text it matched, for a person to judge whether the item says what the source says.

    python -m tumour_board.eval.near_match_eval [--cases TB-001,...,TB-006] [--roles radiology,...] [--out DIR]

Runs in-process on the demo Case Files only (never a real one; config.PROTECTED_CASES are refused); needs both model servers. The
stored briefs and summaries are the exact-only ones (the default).
"""
import argparse, asyncio, json, sys, time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import agents, config, qa, store, summary  # noqa: E402

ROLES = list(agents.ROLES)
_orig = qa.verify


def _paired(log, where):
    """qa.verify replaced by one that verifies both ways, records the difference and returns the exact-only result."""
    def verify(case_id, statements, near_match=False):
        off = _orig(case_id, statements, near_match=False)
        on = _orig(case_id, statements, near_match=True)
        raw = {}  # the model's statement by its text, also as shown (document ids taken out by qa.verify)
        for s in statements or []:
            raw[s.get("text")] = raw[qa._ID_GROUP.sub("", s.get("text") or "").strip()] = s
        approx = [{"text": k["text"], "model_quotes": [c.get("quote") for c in (raw.get(k["text"]) or {}).get("citations") or []],
                   "matched_source": [{"doc_id": c["doc_id"], "quote": c["quote"], "score": c.get("score")} for c in k["citations"] if c.get("approximate")]}
                  for k in on[0] if k.get("approximate")]
        log.append({"where": where(), "case_id": case_id, "statements": len(statements or []), "kept_exact": len(off[0]), "kept_near_match": len(on[0]),
                    "approximate": approx, "dropped_exact_by_reason": {r: sum(d["reason"] == r for d in off[1]) for r in sorted({d["reason"] for d in off[1]})}})
        return off
    return verify


async def run(cases, roles, out):
    for cid in cases:
        if cid in config.PROTECTED_CASES:
            raise SystemExit(f"{cid} holds real patient data: not measured")
    rows, current = [], {"where": ""}
    qa.verify = _paired(rows, lambda: current["where"])
    t0 = time.time()
    try:
        for cid in cases:
            for role in roles:
                current["where"] = f"{cid} brief {role}"
                n0 = len(rows); brief = None
                async for ev in agents.run_agent(cid, role):
                    if ev["type"] == "brief":
                        brief = ev["brief"]
                part = rows[n0:]
                print(f"{cid} {role}: {'no documents' if (brief or {}).get('no_documents') else ''} exact {sum(r['kept_exact'] for r in part)} / "
                      f"near-match {sum(r['kept_near_match'] for r in part)} of {sum(r['statements'] for r in part)}", flush=True)
            current["where"] = f"{cid} summary"
            await summary.build(cid, force=True)
    finally:
        qa.verify = _orig
    artefacts = {}
    for r in rows:
        a = artefacts.setdefault(r["where"], {"statements": 0, "kept_exact": 0, "kept_near_match": 0, "approximate": [], "dropped_exact_by_reason": {}})
        for k in ("statements", "kept_exact", "kept_near_match"):
            a[k] += r[k]
        a["approximate"] += r["approximate"]
        for k, v in r["dropped_exact_by_reason"].items():
            a["dropped_exact_by_reason"][k] = a["dropped_exact_by_reason"].get(k, 0) + v
    briefs = {k: v for k, v in artefacts.items() if " brief " in k and v["statements"]}
    res = {"cases": cases, "roles": roles, "seconds": round(time.time() - t0, 1), "artefacts": artefacts,
           "totals": {"briefs_with_statements": len(briefs), "briefs_empty_exact": sum(v["kept_exact"] == 0 for v in briefs.values()),
                      "briefs_empty_near_match": sum(v["kept_near_match"] == 0 for v in briefs.values()),
                      "kept_exact": sum(v["kept_exact"] for v in artefacts.values()), "kept_near_match": sum(v["kept_near_match"] for v in artefacts.values()),
                      "approximate_items": sum(len(v["approximate"]) for v in artefacts.values())}}
    out.mkdir(parents=True, exist_ok=True)
    (out / "near_match.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    lines = ["# Near-match items (V1 item 6.5): the same model output verified exact-only and with near-match", "",
             f"Cases {', '.join(cases)}; roles {', '.join(roles)}; {res['seconds']} s. Measurement only: judge every approximate item below.", "",
             "| Totals | |", "|---|---|"] + [f"| {k.replace('_', ' ')} | {v} |" for k, v in res["totals"].items()] + ["",
             "| Artefact | Statements | Kept exact | Kept near-match | Approximate | Dropped exact (reason: n) |", "|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['statements']} | {v['kept_exact']} | {v['kept_near_match']} | {len(v['approximate'])} | "
              f"{', '.join(f'{r}: {n}' for r, n in v['dropped_exact_by_reason'].items())} |" for k, v in artefacts.items()]
    lines += ["", "## Approximate items (judge: does the item say what the source says?)", ""]
    for k, v in artefacts.items():
        for a in v["approximate"]:
            lines += [f"- **{k}**: {a['text']}", f"  - model quote: \"{' / '.join(q or '' for q in a['model_quotes'])}\"",
                      *[f"  - source ({m['doc_id']}, score {m['score']}): \"{m['quote']}\"" for m in a["matched_source"]], "  - judgement: "]
    (out / "near_match.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(res["totals"]), "\nreport:", out / "near_match.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="TB-001,TB-002,TB-003,TB-004,TB-005,TB-006"); ap.add_argument("--roles", default=",".join(ROLES))
    ap.add_argument("--out", default=str(config.DATA_ROOT / "eval" / "v1" / "phase6" / "near_match"))
    a = ap.parse_args()
    asyncio.run(run([x.strip() for x in a.cases.split(",") if x.strip()], [x.strip() for x in a.roles.split(",") if x.strip()], Path(a.out)))
