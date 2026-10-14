"""V2 item 4.1, live check ("Done when: scenario outcomes match"): the gate on HIS records, run on every fixture patient of
his_mock/scenarios.json, against the scenarios' first-fetch expectations.

For each Case File of the fixture (one per patients[].case_files[] entry: 18 patients, P14 and P18 with two), the Case File is
created in-process from the live mock hospital (127.0.0.1:7130, read-only: patient lookup, encounters, reports, document downloads;
the RIS / LIS desk is never called), the fetched documents go through the normal pipeline (service.process_docs, the reader model on
:8101), and the gate and the open Pre-Authorization requests are compared with the fixture:

  gate      result (pass / gaps); every protocol record open or met as expected, at the expected level (1 or 2), with the
            expected accession No. when the fixture names one (case_files[].first_fetch.gaps, which the scenarios' first_fetch
            gate entries repeat; tests/test_scenarios_fixture.py keeps the two in agreement); no record open that the fixture does
            not list.
  requests  every `suggested_from_gap` request of the scenarios for that Case File's gaps: an open Pre-Authorization action
            (source pre_authorization, status not completed; the status itself is never compared) for that requirement, routed to
            that department (display name), at that level, naming that accession No. (when the fixture names one); no other open
            Pre-Authorization action. `doctor_initiated` requests are not made by the gate and are skipped.

Only first-fetch outcomes are checked: after_refetch / after_link / after_referral / after_outside_upload need desk or doctor actions
and belong to the e2e (eval/e2e_api.py). P14's colorectal Case File is created directly under colorectal_rectum: its expectation is the
fixture's case_files[].first_fetch for that protocol (the after_referral gate entry: the same records, the same gaps).

Everything runs against a temporary data root (the live Case Files, notifications and org are never touched); only models.json is
copied in so the pipeline uses the same model roles as the app. The Case File search index warm-up at the end of each job is skipped
(it loads an embedding model and plays no part in the gate). SYNTHETIC data only.

    /data/vaidyx/venv/app/bin/python -m tumour_board.eval.his_scenarios [--only P12,P15] [--out DIR] [--parallel 4] [--keep]

Prints one line per Case File (OK / MISMATCH with the differences), then `SCENARIOS OK: <n> Case Files checked` (exit 0) or
`SCENARIOS FAILED: <k> of <n>` (exit 1). Writes report.json to --out (default data/tumour_board/eval/his_scenarios/<timestamp>/)."""
import argparse, asyncio, json, shutil, sys, tempfile, time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIXTURE_PATH = REPO / "his_mock" / "scenarios.json"
LIVE_DATA_ROOT = REPO / "data" / "tumour_board"
DEFAULT_OUT = LIVE_DATA_ROOT / "eval" / "his_scenarios"
LEVEL = "optimal"  # every mock Case File (scenarios.json hospital.ncg_level)
CLOSED = ("satisfied", "not_applicable", "waived")  # a gate requirement that is not a gap
USER = "scenario-check"
ROLES = {"user": USER, "admin": True, "known": True, "coordinator": False, "departments": {}, "treating": {}, "supporting": {}}


# ---- expectations (pure) -------------------------------------------------------------------------------------------------

def load_fixture(path=FIXTURE_PATH) -> dict:
    return json.loads(Path(path).read_text())


def case_id_for(slot: str, protocol_id: str) -> str:
    return f"TB-SCN-{slot}-{protocol_id}".replace("_", "-")[:64]


def expectations(fixture: dict, only=None) -> list:
    """One expectation per Case File of the fixture: who and what to create, the gate outcome on the first fetch, the requests the gate
    should suggest, and the scenarios that state it. `only`: patient slots to keep (None: all)."""
    only = {s.strip().upper() for s in only} if only else None
    first = {}  # (patient, protocol) -> [(scenario id, gate entry)] for the first_fetch entries
    for s in fixture.get("scenarios") or []:
        for g in (s.get("expected") or {}).get("gate") or []:
            if g.get("when") == "first_fetch":
                first.setdefault((g["patient"], g["protocol"]), []).append((s["id"], g))
    requests = {}  # (patient, requirement) -> request (the every-department scenario repeats them: keep one)
    for s in fixture.get("scenarios") or []:
        for r in (s.get("expected") or {}).get("requests") or []:
            if r.get("origin") == "suggested_from_gap" and r.get("requirement"):
                requests.setdefault((r["patient"], r["requirement"]), {**r, "scenario": s["id"]})
    out = []
    for p in fixture.get("patients") or []:
        if only and p["slot"].upper() not in only:
            continue
        for cf in p.get("case_files") or []:
            prot = cf["protocol"]
            ff = cf.get("first_fetch") or {}
            entries = first.get((p["slot"], prot)) or []
            gaps = {}
            for x in ff.get("gaps") or []:
                gaps[x["requirement"]] = {"level": x["level"], "accession": x.get("accession"), "department": x.get("department"), "reason": x.get("reason")}
            for _sid, g in entries:  # the scenarios' first_fetch entries list the same records (the fixture test keeps them in agreement)
                for lvl in (1, 2):
                    for rid in g.get(f"level{lvl}") or []:
                        gaps.setdefault(rid, {"level": lvl, "accession": None, "department": None, "reason": None})
            result = ff.get("result") or (entries[0][1]["result"] if entries else ("gaps" if gaps else "pass"))
            reqs = [{k: r.get(k) for k in ("requirement", "department", "level", "accession", "scenario")}
                    for (slot, rid), r in sorted(requests.items()) if slot == p["slot"] and rid in gaps]
            out.append({"slot": p["slot"], "uhid": p["uhid"], "protocol": prot, "setting": cf.get("ncg_setting") or (entries[0][1].get("ncg_setting") if entries else ""),
                        "owner": cf.get("owner") or p.get("treating_department"), "case_id": case_id_for(p["slot"], prot),
                        "result": result, "gaps": gaps, "requests": reqs,
                        "scenarios": sorted({sid for sid, _g in entries}),
                        "basis": "first_fetch" if entries else "case_files.first_fetch"})
    return out


# ---- comparison (pure) ---------------------------------------------------------------------------------------------------

def _lvl(n) -> str:
    return f"Level {n}" if n else "met"


def compare(exp: dict, gate, actions) -> dict:
    """Compare one Case File's gate and actions with its expectation. Returns {"ok", "differences", "notes", "actual"}."""
    diffs, notes = [], []
    if not gate:
        return {"ok": False, "differences": ["no gate (the Case File is not listed or the job failed)"], "notes": [], "actual": None}
    reqs = {r["id"]: r for r in gate.get("requirements") or [] if isinstance(r, dict) and r.get("id")}
    want_pass = exp["result"] == "pass"
    if bool(gate.get("passed")) != want_pass:
        diffs.append(f"gate {'passed' if gate.get('passed') else 'has gaps'}, expected {'pass' if want_pass else 'gaps'}")
    actual = {}
    for rid, r in reqs.items():
        is_open = r.get("status") not in CLOSED
        actual[rid] = {"status": r.get("status"), "level": r.get("level") if is_open else None, "accession": r.get("accession"),
                       "department": r.get("department")}
    for rid, g in sorted(exp["gaps"].items()):
        a = actual.get(rid)
        if a is None:
            diffs.append(f"{rid}: expected a {_lvl(g['level'])} gap, not a required record in this gate")
            continue
        if a["level"] is None:
            diffs.append(f"{rid}: expected a {_lvl(g['level'])} gap, got met ({a['status']})")
            continue
        if a["level"] != g["level"]:
            diffs.append(f"{rid}: expected a {_lvl(g['level'])} gap, got {_lvl(a['level'])} ({a['status']})")
        if g.get("accession") and a["accession"] != g["accession"]:
            diffs.append(f"{rid}: expected accession {g['accession']}, got {a['accession'] or 'none'}")
        elif not g.get("accession") and a["accession"]:
            notes.append(f"{rid}: the fixture names no accession No., the gate names {a['accession']}")
    for rid, a in sorted(actual.items()):
        if a["level"] is not None and rid not in exp["gaps"]:
            diffs.append(f"{rid}: unexpected {_lvl(a['level'])} gap ({a['status']})")
    open_pa = {}
    for a in actions or []:
        if isinstance(a, dict) and a.get("source") == "pre_authorization" and a.get("status") != "completed" and a.get("requirement"):
            open_pa.setdefault(a["requirement"], a)
    for r in exp["requests"]:
        a = open_pa.get(r["requirement"])
        if not a:
            diffs.append(f"request {r['requirement']}: no open Pre-Authorization request (expected to {r['department']})")
            continue
        if a.get("department") != r["department"]:
            diffs.append(f"request {r['requirement']}: routed to {a.get('department') or 'nobody'}, expected {r['department']}")
        if a.get("level") != r["level"]:
            diffs.append(f"request {r['requirement']}: {_lvl(a.get('level'))}, expected {_lvl(r['level'])}")
        if r.get("accession") and a.get("accession") != r["accession"]:
            diffs.append(f"request {r['requirement']}: accession {a.get('accession') or 'none'}, expected {r['accession']}")
        elif not r.get("accession") and a.get("accession"):
            notes.append(f"request {r['requirement']}: the fixture names no accession No., the request names {a['accession']}")
    for rid, a in sorted(open_pa.items()):
        if rid not in exp["gaps"]:
            diffs.append(f"request {rid}: unexpected open Pre-Authorization request to {a.get('department')}")
    return {"ok": not diffs, "differences": diffs, "notes": notes,
            "actual": {"passed": bool(gate.get("passed")), "requirements": actual,
                       "open_requests": {k: {x: v.get(x) for x in ("department", "level", "accession", "status", "what")} for k, v in sorted(open_pa.items())}}}


def line(exp: dict, res: dict) -> str:
    head = f"{'OK' if res['ok'] else 'MISMATCH'}  {exp['slot']} {exp['protocol']} ({exp['setting']}) {exp['case_id']}"
    if res["ok"]:
        gaps = ", ".join(f"{k} L{v['level']}" for k, v in sorted(exp["gaps"].items())) or "passes"
        return f"{head}: {gaps}; {len(exp['requests'])} request(s)"
    return f"{head}: " + "; ".join(res["differences"])


def summary(results: list) -> tuple[str, int]:
    bad = sum(1 for r in results if not r["ok"])
    if bad:
        return f"SCENARIOS FAILED: {bad} of {len(results)}", 1
    return f"SCENARIOS OK: {len(results)} Case Files checked", 0


# ---- live run ------------------------------------------------------------------------------------------------------------

def _use_data_root(tmp: Path):
    """Point Vaidyx-TB storage at a temporary data root (as tests/conftest.py does); copy models.json so the pipeline uses the
    app's model roles (the reader as extractor)."""
    from tumour_board import config, store
    tmp.mkdir(parents=True, exist_ok=True)
    live_models = LIVE_DATA_ROOT / "models.json"
    if live_models.exists():
        shutil.copyfile(live_models, tmp / "models.json")
    config.DATA_ROOT = tmp
    config.CASES_DIR = tmp / "cases"
    store._docs_cache.clear()
    from tumour_board import search

    class _NoIndex:
        def search(self, q, k=60):
            return []
    search.index = lambda case_id: _NoIndex()  # the search warm-up after each job: not part of the gate


async def _one(exp: dict, sem: asyncio.Semaphore) -> dict:
    from tumour_board import his_case, store
    async with sem:
        t0 = time.time()
        rec = {"expected": exp, "error": None, "job": None}
        try:
            out = await his_case.create(exp["uhid"], exp["protocol"], exp["setting"], LEVEL, "", None, USER, ROLES,
                                        department=exp["owner"], case_id=exp["case_id"])
            job = out["job"]
            if job.get("task"):
                await job["task"]
            rec["job"] = {k: job.get(k) for k in ("state", "error", "total", "done", "his", "seconds")}
            st = store.get_state(exp["case_id"])
            docs = store.list_docs(exp["case_id"])
            rec["documents"] = [{"doc_id": d["doc_id"], "state": d.get("state"), "title": (d.get("his") or {}).get("title"),
                                 "status": (d.get("his") or {}).get("status"), "accession": (d.get("his") or {}).get("accession")} for d in docs]
            res = compare(exp, st.get("gate"), st.get("actions"))
            if job.get("state") == "failed":
                res["ok"] = False
                res["differences"].insert(0, f"processing job failed: {job.get('error')}")
            errs = (job.get("his") or {}).get("errors") or []
            if errs:
                res["notes"].append(f"{len(errs)} HIS download error(s)")
        except Exception as e:  # one Case File failing never stops the others
            res = {"ok": False, "differences": [f"{e.__class__.__name__}: {e}"], "notes": [], "actual": None}
            rec["error"] = f"{e.__class__.__name__}: {e}"
        rec.update(res)
        rec["seconds"] = round(time.time() - t0, 1)
        print(line(exp, res) + f"  [{rec['seconds']} s]", flush=True)
        return rec


async def run(exps: list, parallel: int):
    """The results, or a plain message when the mock hospital does not answer."""
    from tumour_board import his_client
    c = his_client.client()
    if c is None:
        return "No hospital information system is configured"
    ping = await c.ping()
    if not ping.get("ok") or ping.get("token_ok") is False:
        return f"The mock hospital does not answer: {ping.get('error') or 'token refused'}"
    sem = asyncio.Semaphore(max(1, parallel))
    return await asyncio.gather(*[_one(e, sem) for e in exps])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default="", help="patient slots, comma-separated (P12,P15)")
    ap.add_argument("--out", default="", help="report folder (default data/tumour_board/eval/his_scenarios/<timestamp>/)")
    ap.add_argument("--parallel", type=int, default=4, help="Case Files processed at once (default 4)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data root (its path is printed)")
    args = ap.parse_args(argv)
    only = [s for s in args.only.split(",") if s.strip()] or None
    exps = expectations(load_fixture(), only)
    if not exps:
        print("No Case File matches --only", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="tb-scenarios-"))
    t0 = time.time()
    try:
        _use_data_root(tmp)
        results = asyncio.run(run(exps, args.parallel))
        if isinstance(results, str):
            print(results, file=sys.stderr)
            return 2
    finally:
        if args.keep:
            print(f"temporary data root kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    text, code = summary(results)
    out = Path(args.out) if args.out else DEFAULT_OUT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({"item": "V2-4.1", "fixture": str(FIXTURE_PATH.relative_to(REPO)), "hospital_level": LEVEL,
                                                 "seconds": round(time.time() - t0, 1), "result": text, "case_files": results}, indent=1, default=str))
    print(text)
    print(f"report: {out / 'report.json'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
