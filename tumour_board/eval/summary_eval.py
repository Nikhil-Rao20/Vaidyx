"""Omission check for the Case File summary and the primary-fields table (TBFact-style recall).

Precision is 100% by construction (every sentence must carry a verified quote, every number must appear in it). What is
left to measure is what the system LEAVES OUT. The synthetic corpus has an answer key per document; after the full
Case File (base documents + arrivals) is processed, every key field with a value should appear either in the verified
primary-fields table (gate evidence) or in a summary sentence.

Usage: python -m tumour_board.eval.summary_eval [--label name]   (models must be running; cases are re-imported)
"""
import argparse, asyncio, json, time

from tumour_board import config, rules, service, store, summary
from tumour_board.grounding import norm

CORPUS = config.DEMO_CORPUS
KEYMAP = {"mrf": "mrf_status", "dose": "treatment_received", "emvi": "emvi"}  # answer-key names -> fact catalogue ids
NOT_FACTS = {"iv_antibiotics"}  # answer-key items that are not catalogue fields (checked in the summary text only)


def _present(value, haystacks):
    v = norm(str(value))
    nums = [n for n in v.replace(",", "").split() if any(ch.isdigit() for ch in n)]
    for h in haystacks:
        hn = norm(h)
        if v in hn:
            return True
        if nums and all(n.strip("%") in hn.replace(",", "") for n in nums):  # numeric values: same numbers present
            return True
    return False


async def run(label):
    out = {"label": label, "cases": {}}
    for cid in ["TB-001", "TB-002", "TB-003"]:
        j = service.import_demo(cid, "summary_eval"); await j["task"]
        j2 = service.demo_arrivals(cid, "summary_eval")
        if j2:
            await j2["task"]
        truth = json.load(open(CORPUS / "truth" / f"{cid}.json"))
        expected = {}
        for rel, tr in list(truth["documents"].items()) + list(truth["arrivals"].items()):
            for f, v in tr["fields"].items():
                if v is not None:
                    expected.setdefault(KEYMAP.get(f, f), set()).add(str(v))
        t0 = time.time()
        sm = await summary.build(cid, force=True)
        facts = rules.resolve_facts(store.list_docs(cid), store.get_state(cid).get("overrides"))
        sentences = [x["text"] + " " + " ".join(c["quote"] for c in x["citations"]) for p in sm.get("paragraphs", []) for x in p]
        fact_vals = {f: [h["value"] for h in facts.get(f, {}).get("history", [])] for f in expected}
        covered_facts = covered_summary = 0; misses = []
        for f, vals in expected.items():
            any_val = list(vals)
            in_facts = f not in NOT_FACTS and any(_present(v, fact_vals.get(f, [])) for v in any_val)
            in_sum = any(_present(v, sentences) for v in any_val)
            covered_facts += in_facts; covered_summary += in_sum
            if not in_facts and not in_sum:
                misses.append({"field": f, "values": any_val})
        out["cases"][cid] = {"expected_fields": len(expected), "in_primary_fields": covered_facts, "in_summary": covered_summary,
                             "in_either": len(expected) - len(misses), "summary_sentences": len(sentences), "summary_seconds": sm.get("seconds"),
                             "dropped_unverified": sm.get("dropped_unverified"), "context": sm.get("context"), "misses": misses}
        print(f"{cid}: {len(expected)} key fields | primary-fields table {covered_facts} | summary {covered_summary} | either {len(expected) - len(misses)} "
              f"| {len(sentences)} sentences in {sm.get('seconds')}s | misses: {[m['field'] for m in misses]}")
    f = config.DATA_ROOT / "eval" / f"summary_eval_{label}.json"; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--label", default="current"); asyncio.run(run(ap.parse_args().label))
