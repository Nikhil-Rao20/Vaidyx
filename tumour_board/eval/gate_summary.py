"""Summarise one regression-gate run (written by eval/gate.sh) and compare it with the baseline (item 0.2).
Usage: python -m tumour_board.eval.gate_summary <label> [--baseline baseline]   -> prints and writes <run>/gate_summary.md"""
import argparse, json, re, statistics
from pathlib import Path

from tumour_board import config

RUNS = config.DATA_ROOT / "eval" / "v1"


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
        j = json.loads(qa.read_text()); secs = [r["seconds"] for r in j["rows"] if r.get("seconds")]
        n.update(qa_pass=j["pass"], qa_n=j["n"], qa_fabrication=j["fabrication"], qa_median_seconds=round(statistics.median(secs), 1) if secs else None)
    sm = next(d.glob("summary_eval_v1-*.json"), None)
    if sm:
        j = json.loads(sm.read_text()); cs = j["cases"].values()
        n.update(sum_hit=sum(c["in_either"] for c in cs), sum_total=sum(c["expected_fields"] for c in cs),
                 sum_mean_seconds=round(statistics.mean([c["summary_seconds"] for c in cs if c.get("summary_seconds")] or [0]), 1))
    return n


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
    ]
    lines = [f"# Gate run `{label}` vs baseline `{baseline}`", "", "| Check | This run | Baseline | Rule | OK |", "|---|---|---|---|---|"]
    lines += [f"| {c} | {r if r is not None else 'skipped'} | {b} | {rule} | {'skipped' if ok is None else ('yes' if ok else 'NO')} |" for c, r, b, rule, ok in rows]
    verdict = "GREEN" if all(ok for _, r, _, _, ok in rows if ok is not None) else "RED"
    lines += ["", f"**Gate: {verdict}** (unit tests and the end-to-end API are never optional; the other checks may be skipped when their code did not change, and a skipped check is never counted as a pass).", "",
              "Timings note: the Q&A eval sends all 33 questions at once, so its median includes queueing; compare like with like."]
    out = "\n".join(lines) + "\n"; (RUNS / label / "gate_summary.md").write_text(out); print(out)
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("label"); ap.add_argument("--baseline", default="baseline")
    a = ap.parse_args(); raise SystemExit(main(a.label, a.baseline))
