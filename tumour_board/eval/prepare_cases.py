"""Import and process the synthetic demo cases headlessly (same pipeline as the UI). Prints timing and gate status."""
import asyncio, sys, time

from tumour_board import service, store


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
    asyncio.run(main(sys.argv[1:] or ["TB-001", "TB-002", "TB-003"]))
