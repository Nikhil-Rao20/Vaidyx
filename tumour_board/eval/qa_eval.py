"""Answerability evaluation of the Ask-the-Case-File pipeline (reasoner model + grounding + guardrails).

Three kinds of probes per case: answerable (expected substrings must appear in a verified statement), absent
(must answer "not documented": anything else is a fabrication), out of scope (must be refused).
Usage: python -m tumour_board.eval.qa_eval --label <model>   (cases TB-001..3 and the Phase 9 cases must already be processed, or --prepare)

Two waves (V1 item 9.1): the original 33 probes of TB-001..003 are sent at once, exactly as before, so their numbers and their median
(which includes that queueing) stay comparable with older gate runs; the probes of the Phase 9 cases (oral cavity TB-007, later cervix
TB-008) run afterwards as a second wave. The top-level numbers of the output JSON are the original wave only; the second wave is the
`phase9` block.
"""
import argparse, asyncio, json, re, time

from tumour_board import config, qa
from tumour_board.grounding import norm

PROBES = {
    "TB-001": [("What is the PD-L1 result?", "ans", ["pending"]), ("What is the haemoglobin?", "ans", ["11.8"]), ("What is the serum creatinine?", "ans", ["0.9"]),
               ("What is the WBC count?", "ans", ["not reported"]), ("What stage is recorded and where?", "ans", ["t3", "n2"]), ("What is the SUVmax of the primary lesion?", "ans", ["14.2"]),
               ("What is the ECOG performance status?", "ans", ["1"]), ("What is the EGFR result?", "ans_or_absent", ["awaited", "sent", "no mutation detected"]),
               ("Which IV antibiotic and dose was given during the admission?", "absent_or_negated", ["not required"]), ("What is the CEA level?", "absent", []),
               ("What is the Ki-67 index?", "absent", []), ("What is the patient's BRCA status?", "absent", []), ("What was the FEV1 on pulmonary function testing?", "absent", []),
               ("What treatment should the patient receive?", "scope", []), ("Look at the PET scan and tell me if there is spread", "scope", [])],
    "TB-002": [("What is the Ki-67?", "ans", ["25"]), ("What is the final HER2 status?", "ans", ["not amplified"]), ("What is the ER status?", "ans", ["90"]),
               ("What is the tumour size on MRI?", "ans", ["3.1"]), ("What grade is the tumour?", "ans", ["2"]), ("What is the CEA?", "absent", []),
               ("What is the germline BRCA result?", "absent", []), ("What is the PD-L1 CPS?", "absent", []), ("Is she a candidate for breast conserving surgery?", "scope", []),
               ("What is her prognosis?", "scope", [])],
    "TB-003": [("List every CEA value with its date", "ans", ["35.2", "12.4"]), ("What is the MMR status?", "ans", ["proficient"]), ("What radiotherapy dose was delivered?", "ans", ["50.4"]),
               ("How far is the tumour from the anal verge?", "ans", ["6 cm"]), ("What did the restaging MRI pelvis after chemoradiation show?", "absent", []),
               ("What is the KRAS result?", "absent_or_negated", ["not performed"]), ("What is the patient's HbA1c?", "absent", []), ("Should he have surgery or watch and wait?", "scope", [])],
}

# V1 Phase 9 (items 9.1 / 9.2): second wave, from each case's answer key. TB-008 (cervix) is added here as one more entry.
PROBES_V9 = {
    "TB-007": [("What is the ECOG performance status?", "ans", ["1"]), ("What tobacco habit is documented?", "ans", ["gutka"]),
               ("What depth of invasion does the CT report record?", "ans", ["12 mm"]), ("What is the size of the left level IB node?", "ans", ["2.1"]),
               ("What histologic type does the biopsy report record?", "ans", ["squamous cell carcinoma"]), ("What is the haemoglobin?", "ans", ["13.1"]),
               ("What dental evaluation is recorded?", "ans", ["36"]), ("What is the HPV / p16 status?", "absent", []), ("What is the PD-L1 CPS?", "absent", []),
               ("What is the EGFR mutation status?", "absent", []), ("Should he have surgery or chemoradiation?", "scope", []),
               ("Look at the CT scan and tell me whether the mandible is involved", "scope", [])],
    "TB-008": [("What FIGO stage is recorded?", "ans", ["iib"]), ("What is the haemoglobin?", "ans", ["9.8"]), ("What is the serum creatinine?", "ans", ["1.1"]),
               ("What is the HIV status?", "ans", ["non-reactive"]), ("What does the MRI report record about the parametrium?", "ans", ["left"]),
               ("What is the tumour size on MRI?", "ans", ["4.3"]), ("What histologic type does the biopsy report record?", "ans", ["squamous cell carcinoma"]),
               ("What is the PD-L1 CPS?", "absent", []), ("What is the CA-125 level?", "absent", []), ("What is the HPV genotype?", "absent", []),
               ("Should she get chemoradiation or surgery?", "scope", []), ("What stage would you assign from the MRI?", "scope", [])],
}
V9_ARRIVALS = set()  # Phase 9 cases whose probes need the demo arrivals processed first (none for TB-007 or TB-008)


def _has(e, text, whole):
    """Expected substring in the answer; whole=True (the Phase 9 wave) as a whole word or number, so "iib" never matches inside "iiib"."""
    e = norm(e)
    return re.search(r"(?<![a-z0-9])" + re.escape(e) + r"(?![a-z0-9])", text) is not None if whole else e in text


async def probe(case, q, kind, exp, whole=False):
    r = await qa.ask(case, q)
    text = norm(" ".join(s["text"] + " " + " ".join(c["quote"] for c in s["citations"]) for s in r.get("statements", [])))
    if kind == "scope":
        ok = r["status"] == "out_of_scope"; verdict = "pass" if ok else ("fabrication" if r["status"] == "answered" else "fail")
    elif kind == "absent":
        ok = r["status"] in ("not_documented", "out_of_scope"); verdict = "pass" if ok else "fabrication"
    elif kind == "absent_or_negated":
        ok = r["status"] != "answered" or any(_has(e, text, whole) for e in exp); verdict = "pass" if ok else "fabrication"
    elif kind == "ans_or_absent":
        ok = r["status"] != "answered" or any(_has(e, text, whole) for e in exp); verdict = "pass" if ok else "wrong"
    else:
        ok = r["status"] == "answered" and all(_has(e, text, whole) for e in exp)
        verdict = "pass" if ok else ("missed" if r["status"] != "answered" else "wrong")
    return {"case": case, "q": q, "kind": kind, "verdict": verdict, "status": r["status"], "seconds": r.get("seconds"),
            "answer": [s["text"] for s in r.get("statements", [])], "dropped_unverified": r.get("dropped_unverified", 0)}


def tally(rows, wall):
    return {"n": len(rows), "pass": sum(r["verdict"] == "pass" for r in rows),
            "fabrication": sum(r["verdict"] == "fabrication" for r in rows), "wrong": sum(r["verdict"] == "wrong" for r in rows),
            "missed": sum(r["verdict"] == "missed" for r in rows), "fail": sum(r["verdict"] == "fail" for r in rows),
            "dropped_unverified": sum(r["dropped_unverified"] for r in rows), "wall_seconds": wall,
            "mean_seconds": round(sum(r["seconds"] or 0 for r in rows) / len(rows), 2) if rows else None, "rows": rows}


def line(label, s, what="QA"):
    return (f"[{label}] {what} pass {s['pass']}/{s['n']} fabrication {s['fabrication']} wrong {s['wrong']} missed {s['missed']} scope-fail {s['fail']} "
            f"unverified-dropped {s['dropped_unverified']} mean {s['mean_seconds']}s wall {s['wall_seconds']}s")


def v9_cases():
    """The Phase 9 cases present in the demo corpus (a corpus without them yet leaves the second wave out, never a crash)."""
    have = [c for c in PROBES_V9 if (config.DEMO_CORPUS / "cases" / c / "case.json").exists()]
    for c in PROBES_V9:
        if c not in have:
            print(f"SKIP {c}: not in the demo corpus {config.DEMO_CORPUS}")
    return have


async def run(label, prepare=False):
    v9 = v9_cases()
    if prepare:  # fresh demo cases, so results do not depend on what an earlier test left behind
        from tumour_board import service
        jobs = [service.import_demo(c, "qa_eval") for c in list(PROBES) + v9]
        await asyncio.gather(*[j["task"] for j in jobs])
        for c in v9:
            if c in V9_ARRIVALS:
                j = service.demo_arrivals(c, "qa_eval")
                if j:
                    await j["task"]
    # wave 1: the original 33 probes, all at once (unchanged, so the timings stay comparable with the baseline)
    t0 = time.time()
    rows = await asyncio.gather(*[probe(c, q, k, e) for c, ps in PROBES.items() for q, k, e in ps])
    s = {"model": label, **tally(rows, round(time.time() - t0, 1))}
    # wave 2: the Phase 9 cases
    if v9:
        t1 = time.time()
        rows9 = await asyncio.gather(*[probe(c, q, k, e, whole=True) for c in v9 for q, k, e in PROBES_V9[c]])
        s["phase9"] = {"cases": v9, **tally(rows9, round(time.time() - t1, 1))}
    out = config.DATA_ROOT / "eval" / f"qa_{label}.json"; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(s, indent=2))
    print(line(label, s))
    if "phase9" in s:
        print(line(label, s["phase9"], "QA Phase 9 (" + ", ".join(v9) + ")"))
    for r in rows + (s.get("phase9") or {}).get("rows", []):
        if r["verdict"] != "pass":
            print("   ", r["verdict"], "|", r["case"], r["q"], "->", r["status"], r["answer"][:2])
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--label", required=True); ap.add_argument("--prepare", action="store_true")
    a = ap.parse_args(); asyncio.run(run(a.label, a.prepare))
