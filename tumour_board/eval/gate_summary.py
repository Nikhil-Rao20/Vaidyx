"""Summarise one regression-gate run (written by eval/gate.sh) and compare it with the baseline (item 0.2).
Usage: python -m tumour_board.eval.gate_summary <label> [--baseline baseline]   -> prints and writes <run>/gate_summary.md"""
import argparse, json, re, statistics
from pathlib import Path

from tumour_board import config

RUNS = config.DATA_ROOT / "eval" / "v1"
ORIGINAL_CASES = ("TB-001", "TB-002", "TB-003")  # the existing rules and the timing comparison use these cases only (like with like)
# V1 Phase 9 (oral cavity TB-007, cervix TB-008): minimum passes of their Q&A probes and minimum key fields found by the summary eval.
# None = rule "0 fabrications, recorded" until the first measurement; the orchestrator then sets the numbers.
V9_CASES = ("TB-007", "TB-008")  # the Phase 9 demo Case Files (same list as summary_eval.CASES_V9 and qa_eval.PROBES_V9; a test keeps them equal)
V9_QA_MIN = 23  # TB-007 + TB-008: 24 probes, measured 24/24 (session 11; one miss allowed for model variance); 0 fabrications always
V9_SUM_MIN = 36  # TB-007 18/19 (miss: ENE "no perinodal extension", a negated imaging finding) + TB-008 18/18, measured twice for TB-007


def numbers(d):
    """Read every number the gate rules need from a run folder. A step counts only if gate.sh recorded it as finished
    (exit code in run_timings.txt) and its log has the final tally; anything else is a failure, never a pass."""
    n = {}
    rc = {m.group(1): int(m.group(2)) for m in re.finditer(r"=== (\w+) finished rc=(-?\d+)", (d / "run_timings.txt").read_text() if (d / "run_timings.txt").exists() else "")}
    n["rc"] = rc
    f = d / "unit.log"
    if f.exists() or "unit" in rc:
        t = f.read_text() if f.exists() else ""; m = re.search(r"(\d+) passed", t); fl = re.search(r"(\d+) failed", t); er = re.search(r"(\d+) errors?", t)
        n["unit_passed"] = int(m.group(1)) if m else 0; n["unit_failed"] = (int(fl.group(1)) if fl else 0) + (int(er.group(1)) if er else 0)
        if rc.get("unit", 1) != 0 or not m:  # pytest missing, no tests collected, crashed: a failure, not a pass
            n["unit_failed"] = max(n["unit_failed"], 1)
        m = re.search(r"in ([\d.]+)s", t); n["unit_seconds"] = float(m.group(1)) if m else None
    f = d / "e2e_api.log"
    if f.exists() or "e2e_api" in rc:
        t = f.read_text() if f.exists() else ""; m = re.search(r"(\d+) passed, (\d+) failed", t)
        if m and rc.get("e2e_api", 1) == 0:
            n["e2e_passed"], n["e2e_failed"] = int(m.group(1)), int(m.group(2))
        else:  # a non-zero exit is never green: the printed failure count when there is one, else at least 1
            n["e2e_passed"], n["e2e_failed"] = (int(m.group(1)) if m else 0), max(int(m.group(2)) if m else 0, 1)
        m = re.search(r"ingest \+ gate.*?\[(\d+) docs in ([\d.]+)s", t); n["ingest_seconds"] = float(m.group(2)) if m else None
        m = re.search(r"ask answered with citation\s+\[([\d.]+) s", t); n["ask_single_seconds"] = float(m.group(1)) if m else None
    f = d / "ui_test.log"
    if f.exists():
        m = re.search(r"JS errors: (.*)", f.read_text(), re.S)
        n["ui_errors"] = 0 if m and m.group(1).strip().startswith("none") and rc.get("ui_test", 1) == 0 else (len(re.findall(r"console: |pageerror: |re-check toast|summary does not", m.group(1))) or -1 if m else -1)
    qa = next(d.glob("qa_v1-*.json"), None)
    if qa:
        j = json.loads(qa.read_text())  # top level = the original wave (TB-001..003); the Phase 9 wave is the `phase9` block
        secs = [r["seconds"] for r in j["rows"] if r.get("seconds") and r.get("case", ORIGINAL_CASES[0]) in ORIGINAL_CASES]
        n.update(qa_pass=j["pass"], qa_n=j["n"], qa_fabrication=j["fabrication"], qa_median_seconds=round(statistics.median(secs), 1) if secs else None)
        p9 = j.get("phase9")
        n["qa9_ran"] = p9 is not None
        if p9 is not None:
            secs = [r["seconds"] for r in p9.get("rows") or [] if r.get("seconds")]
            n.update(qa9_pass=p9["pass"], qa9_n=p9["n"], qa9_fabrication=p9["fabrication"], qa9_cases=p9.get("cases") or sorted({r["case"] for r in p9.get("rows") or []}),
                     qa9_median_seconds=round(statistics.median(secs), 1) if secs else None)
    sm = next(d.glob("summary_eval_v1-*.json"), None)
    if sm:
        j = json.loads(sm.read_text())
        cs = [c for cid, c in j["cases"].items() if cid in ORIGINAL_CASES]
        n.update(sum_hit=sum(c["in_either"] for c in cs), sum_total=sum(c["expected_fields"] for c in cs),
                 sum_mean_seconds=round(statistics.mean([c["summary_seconds"] for c in cs if c.get("summary_seconds")] or [0]), 1))
        v9 = {cid: c for cid, c in j["cases"].items() if cid not in ORIGINAL_CASES}
        n["sum9_ran"] = bool(v9)
        if v9:
            n.update(sum9_hit=sum(c["in_either"] for c in v9.values()), sum9_total=sum(c["expected_fields"] for c in v9.values()), sum9_cases=sorted(v9),
                     sum9_misses=[f"{cid}: {m['field']}" for cid, c in sorted(v9.items()) for m in c.get("misses") or []],
                     sum9_mean_seconds=round(statistics.mean([c["summary_seconds"] for c in v9.values() if c.get("summary_seconds")] or [0]), 1))
    return n


def v9_in_corpus():
    """The Phase 9 Case Files the demo corpus holds: the evals must report on every one of them (review M9)."""
    return [c for c in V9_CASES if (config.DEMO_CORPUS / "cases" / c / "case.json").exists()]


def phase9_rows(run, base):
    """The two Phase 9 rows (oral cavity / cervix Case Files): never mixed into the original rules. Fabrications make the gate RED. When the
    evals ran but did not report on every Phase 9 Case File the demo corpus holds, the row fails (a broken case list or corpus path must not
    pass silently); a run from before Phase 9 (no such Case File in the corpus) shows "not run" and the row is skipped, never a pass."""
    want = v9_in_corpus()
    qa_rule = "0 fabrications, recorded" if V9_QA_MIN is None else f"0 fabrications, >= {V9_QA_MIN} pass"
    if "qa9_pass" in run:
        miss = [c for c in want if c not in run["qa9_cases"]]
        qa_this = f"{run['qa9_pass']}/{run['qa9_n']} pass, {run['qa9_fabrication']} fabrications ({', '.join(run['qa9_cases'])})" + (
            f"; no probes run for {', '.join(miss)}" if miss else "")
        qa_ok = run["qa9_fabrication"] == 0 and (V9_QA_MIN is None or run["qa9_pass"] >= V9_QA_MIN) and not miss
    elif "qa_pass" in run and want:
        qa_this, qa_ok = f"missing: the demo corpus holds {', '.join(want)} but the Q&A eval wrote no Phase 9 block", False
    else:
        qa_this, qa_ok = ("not run (no Phase 9 block)" if "qa_pass" in run else None), None
    sum_rule = "recorded" if V9_SUM_MIN is None else f">= {V9_SUM_MIN} key fields"
    if "sum9_hit" in run:
        miss = [c for c in want if c not in run["sum9_cases"]]
        sum_this = f"{run['sum9_hit']}/{run['sum9_total']} key fields ({', '.join(run['sum9_cases'])})" + (f"; not evaluated: {', '.join(miss)}" if miss else "")
        sum_ok = (V9_SUM_MIN is None or run["sum9_hit"] >= V9_SUM_MIN) and not miss
    elif "sum_hit" in run and want:
        sum_this, sum_ok = f"missing: the demo corpus holds {', '.join(want)} but the summary eval did not evaluate them", False
    else:
        sum_this, sum_ok = ("not run (no Phase 9 cases)" if "sum_hit" in run else None), None
    return [("Ask the Case File, oral cavity / cervix (Phase 9)", qa_this,
             f"{base.get('qa9_pass')}/{base.get('qa9_n')}, {base.get('qa9_fabrication')} fabrications" if "qa9_pass" in base else "n/a", qa_rule, qa_ok),
            ("Summary omission, Phase 9 cases", sum_this, f"{base.get('sum9_hit')}/{base.get('sum9_total')}" if "sum9_hit" in base else "n/a", sum_rule, sum_ok)]


def fmt(v):
    return "n/a" if v is None else str(v)


def main(label, baseline):
    run, base = numbers(RUNS / label), numbers(RUNS / baseline) if (RUNS / baseline).exists() else {}
    slower = lambda k: run.get(k) is not None and base.get(k) and run[k] > 1.2 * base[k]
    rows = [  # (check, this run, baseline, rule, ok or None when the step was skipped)
        ("Unit tests", f"{run.get('unit_passed')} passed, {run.get('unit_failed')} failed in {fmt(run.get('unit_seconds'))} s" if "unit_passed" in run else "not run",
         f"{base.get('unit_passed')} passed" if "unit_passed" in base else "n/a", "100 % pass, under 30 s (never optional)",
         "unit_passed" in run and run["unit_passed"] > 0 and run["unit_failed"] == 0 and (run.get("unit_seconds") or 99) < 30),
        ("End-to-end API", f"{run.get('e2e_passed')} passed, {run.get('e2e_failed')} failed" if "e2e_passed" in run else "not run",
         f"{base.get('e2e_passed')}/{base.get('e2e_passed', 0) + base.get('e2e_failed', 0)}" if "e2e_passed" in base else "n/a", "all pass (never optional)",
         "e2e_passed" in run and run["e2e_passed"] > 0 and run["e2e_failed"] == 0),
        ("Ask the Case File", f"{run.get('qa_pass')}/{run.get('qa_n')} pass, {run.get('qa_fabrication')} fabrications" if "qa_pass" in run else None,
         f"{base.get('qa_pass')}/{base.get('qa_n')}, {base.get('qa_fabrication')} fabrications" if "qa_pass" in base else "n/a", "no drop, 0 fabrications",
         (run.get("qa_pass", 0) >= base.get("qa_pass", 33) and run.get("qa_fabrication") == 0) if "qa_pass" in run else None),
        ("Summary omission", f"{run.get('sum_hit')}/{run.get('sum_total')} key fields" if "sum_hit" in run else None,
         f"{base.get('sum_hit')}/{base.get('sum_total')}" if "sum_hit" in base else "n/a", ">= 47/48 (>= baseline)",
         run.get("sum_hit", 0) >= max(47, base.get("sum_hit", 0)) if "sum_hit" in run else None),
        ("Independent OCR engine (8.3)", (((d := RUNS / label / "ocr_engine.log").exists() and d.read_text().strip()[:60]) or "not found") if "ocr_engine" in run["rc"] else None,
         "n/a", "installed, or TB_OCR_ENGINE=off", run["rc"]["ocr_engine"] == 0 if "ocr_engine" in run["rc"] else None),
        ("Browser UI", f"{run.get('ui_errors')} errors recorded" if "ui_errors" in run else None, f"{base.get('ui_errors')} errors recorded" if "ui_errors" in base else "n/a",
         "no JS errors on /tb", run.get("ui_errors") == 0 if "ui_errors" in run else None),
        ("Timings", ", ".join(f"{k.replace('_seconds', '')} {fmt(run.get(k))} s" for k in ("ingest_seconds", "ask_single_seconds", "qa_median_seconds", "sum_mean_seconds") if run.get(k) is not None) or None,
         ", ".join(f"{k.replace('_seconds', '')} {fmt(base.get(k))} s" for k in ("ingest_seconds", "ask_single_seconds", "qa_median_seconds", "sum_mean_seconds") if base.get(k) is not None) or "n/a",
         "no more than 20 % slower", (not any(slower(k) for k in ("ingest_seconds", "qa_median_seconds", "sum_mean_seconds"))) if any(run.get(k) is not None for k in ("ingest_seconds", "qa_median_seconds", "sum_mean_seconds")) else None),
    ] + phase9_rows(run, base)
    lines = [f"# Gate run `{label}` vs baseline `{baseline}`", "", "| Check | This run | Baseline | Rule | OK |", "|---|---|---|---|---|"]
    lines += [f"| {c} | {r if r is not None else 'skipped'} | {b} | {rule} | {'skipped' if ok is None else ('yes' if ok else 'NO')} |" for c, r, b, rule, ok in rows]
    verdict = "GREEN" if all(ok for _, r, _, _, ok in rows if ok is not None) else "RED"
    t9 = ", ".join(f"{k.replace('9_', ' ').replace('_seconds', '')} {run[k]} s" for k in ("qa9_median_seconds", "sum9_mean_seconds") if run.get(k) is not None)
    if t9:
        lines += ["", f"Phase 9 timings (oral cavity / cervix Case Files; recorded, not in the 20 % rule): {t9}"]
    if run.get("sum9_misses"):
        lines += ["", "Phase 9 summary misses: " + "; ".join(run["sum9_misses"])]
    lines += ["", f"**Gate: {verdict}** (unit tests and the end-to-end API are never optional; the other checks may be skipped when their code did not change, and a skipped check is never counted as a pass).", "",
              f"Timings note: the Q&A eval sends the {run.get('qa_n') or 33} questions of TB-001..003 at once, so its median includes queueing; the Phase 9 questions run "
              "afterwards as a second wave and are timed separately. The Q&A median and the summary mean in the 20 % rule are TB-001..003 only; compare like with like."]
    out = "\n".join(lines) + "\n"; (RUNS / label / "gate_summary.md").write_text(out); print(out)
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("label"); ap.add_argument("--baseline", default="baseline")
    a = ap.parse_args(); raise SystemExit(main(a.label, a.baseline))
