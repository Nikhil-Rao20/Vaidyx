"""Import and process the synthetic demo cases headlessly (same pipeline as the UI). Prints timing and gate status.
With no arguments: TB-001..003 and the Phase 9 cases (TB-007 oral cavity; later TB-008 cervix), so the gate leaves every demo Case File
fresh; a Phase 9 case not in the demo corpus yet is skipped with a note."""
import asyncio, sys, time

from tumour_board import config, service, store
from tumour_board.eval.summary_eval import CASES, CASES_V9


def default_cases():
    have = [c for c in CASES_V9 if (config.DEMO_CORPUS / "cases" / c / "case.json").exists()]
    for c in CASES_V9:
        if c not in have:
            print(f"SKIP {c}: not in the demo corpus {config.DEMO_CORPUS}")
    return list(CASES) + have


async def main(cases):
    t0 = time.time()
    jobs = [service.import_demo(c, "eval") for c in cases]
    await asyncio.gather(*[j["task"] for j in jobs])
    for c, j in zip(cases, jobs):
        g = store.get_state(c)["gate"]
        errs = [d["filename"] + ": " + d.get("error", "") for d in store.list_docs(c) if d.get("state") == "error"]
        print(f"{c}: {j['total']} docs in {j['seconds']}s | gate {g['satisfied']}/{g['total']} passed={g['passed']} | errors {errs}")
        for r in g["requirements"]:
            if r["status"] != "satisfied":
                print(f"    {r['status']:15s} {r['label']} ({r['department']}): {'; '.join(r['problems'])}")
    print(f"total {time.time() - t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or default_cases()))
