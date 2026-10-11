"""V1 Phase 9 evals and gate (item 9.1): the original rules stay on TB-001..003, the Phase 9 cases (oral cavity TB-007, later cervix
TB-008) get their own rows and timings, a run without them is skipped (never a pass), and the first Q&A wave is the 33 old probes."""
import asyncio, json

import pytest

from tumour_board import config, protocol
from tumour_board.eval import e2e_api, gate_summary, prepare_cases, qa_eval, summary_eval

OLD = ("TB-001", "TB-002", "TB-003")

# the original 33 probes, copied here on purpose: the first wave must never change (its numbers and timing are compared with the baseline)
OLD_PROBES = {
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

TB007_FIELDS = ["ecog", "clinical_question", "recorded_stage", "tobacco_use", "presenting_complaint", "histologic_type", "grade", "pni", "lesion_size",
                "nodal_findings", "depth_of_invasion", "ene", "distant_findings", "dental_evaluation", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin"]


# ---- synthetic gate run folders ----------------------------------------------------------------------------------
def _rows(case, n, verdicts=None, seconds=5.0):
    verdicts = verdicts or ["pass"] * n
    return [{"case": case, "q": f"q{i}", "kind": "ans", "verdict": v, "status": "answered", "seconds": seconds, "answer": [], "dropped_unverified": 0}
            for i, v in enumerate(verdicts)]


def _block(rows):
    return {"n": len(rows), "pass": sum(r["verdict"] == "pass" for r in rows), "fabrication": sum(r["verdict"] == "fabrication" for r in rows),
            "wrong": sum(r["verdict"] == "wrong" for r in rows), "missed": sum(r["verdict"] == "missed" for r in rows), "fail": 0,
            "dropped_unverified": 0, "wall_seconds": 1.0, "mean_seconds": 1.0, "rows": rows}


def _qa(old_pass=33, old_fab=0, p9=None, old_seconds=5.0):
    """A qa JSON: 33 original probes (old_pass passes, old_fab fabrications) and, unless p9 is None, a Phase 9 block of TB-007 rows."""
    verdicts = ["pass"] * old_pass + ["fabrication"] * old_fab
    verdicts += ["missed"] * (33 - len(verdicts))
    rows = [r for i, c in enumerate(OLD) for r in _rows(c, 11, verdicts[i * 11:(i + 1) * 11], old_seconds)]
    out = {"model": "v1-test", **_block(rows)}
    if p9 is not None:
        out["phase9"] = {"cases": ["TB-007"], **_block(_rows("TB-007", len(p9), p9, seconds=60.0))}
    return out


def _summary(old_hits=(16, 16, 15), v9=(17, 19), old_seconds=20.0):
    cases = {c: {"expected_fields": 16, "in_either": h, "summary_seconds": old_seconds, "misses": []} for c, h in zip(OLD, old_hits)}
    if v9:
        cases["TB-007"] = {"expected_fields": v9[1], "in_either": v9[0], "summary_seconds": 300.0, "misses": [{"field": "pni", "values": ["Not identified"]}] * (v9[1] - v9[0])}
    return {"label": "v1-test", "cases": cases, "groups": {"original": list(OLD), "phase9": ["TB-007"] if v9 else []}}


def _run(root, label, qa=None, sm=None):
    d = root / label
    d.mkdir(parents=True)
    steps = ["ocr_engine", "unit", "e2e_api"] + (["qa_eval"] if qa else []) + (["summary_eval"] if sm else [])
    (d / "run_timings.txt").write_text("".join(f"=== {s} started x\n=== {s} finished rc=0 in 10 s\n" for s in steps))
    (d / "ocr_engine.log").write_text("tesseract 5.3\n")
    (d / "unit.log").write_text("700 passed in 12.30s\n")
    (d / "e2e_api.log").write_text("PASS TB-001 ingest + gate  [12 docs in 40.0s, gate 2/5]\nPASS ask answered with citation  [6.1 s]\n\n150 passed, 0 failed: []\n")
    if qa:
        (d / f"qa_v1-{label}.json").write_text(json.dumps(qa))
    if sm:
        (d / f"summary_eval_v1-{label}.json").write_text(json.dumps(sm))
    return d


@pytest.fixture
def runs(tmp_path, monkeypatch):
    root = tmp_path / "v1"
    root.mkdir()
    monkeypatch.setattr(gate_summary, "RUNS", root)
    monkeypatch.setattr(gate_summary, "V9_QA_MIN", None)
    monkeypatch.setattr(gate_summary, "V9_SUM_MIN", None)
    _run(root, "baseline", _qa(), _summary(v9=None))
    return root


def _table(root, label):
    md = (root / label / "gate_summary.md").read_text()
    return md, {ln.split("|")[1].strip(): [x.strip() for x in ln.split("|")[2:-1]] for ln in md.splitlines() if ln.startswith("| ") and "---" not in ln}


def test_numbers_split_original_and_phase9(runs):
    d = _run(runs, "r1", _qa(p9=["pass"] * 11 + ["missed"]), _summary())
    n = gate_summary.numbers(d)
    assert (n["qa_pass"], n["qa_n"], n["qa_fabrication"]) == (33, 33, 0)
    assert (n["qa9_pass"], n["qa9_n"], n["qa9_fabrication"], n["qa9_cases"]) == (11, 12, 0, ["TB-007"])
    assert (n["sum_hit"], n["sum_total"]) == (47, 48)  # TB-001..003 only
    assert (n["sum9_hit"], n["sum9_total"], n["sum9_cases"]) == (17, 19, ["TB-007"])
    assert n["qa_median_seconds"] == 5.0 and n["qa9_median_seconds"] == 60.0  # like with like: the Phase 9 rows never enter the old median
    assert n["sum_mean_seconds"] == 20.0 and n["sum9_mean_seconds"] == 300.0


def test_green_with_phase9_recorded(runs):
    _run(runs, "r2", _qa(p9=["pass"] * 10 + ["missed"] * 2), _summary())
    assert gate_summary.main("r2", "baseline") == 0
    md, rows = _table(runs, "r2")
    assert rows["Ask the Case File"][-1] == "yes" and rows["Summary omission"][-1] == "yes"
    p9 = rows["Ask the Case File, oral cavity / cervix (Phase 9)"]
    assert p9[0].startswith("10/12 pass, 0 fabrications") and p9[2] == "0 fabrications, recorded" and p9[3] == "yes"
    assert rows["Summary omission, Phase 9 cases"][0].startswith("17/19") and rows["Summary omission, Phase 9 cases"][3] == "yes"
    assert rows["Timings"][-1] == "yes"  # Phase 9 rows at 60 s and a 300 s summary are not in the 20 % rule
    assert "Phase 9 timings" in md and "qa median 60.0 s" in md and "sum mean 300.0 s" in md
    assert "33 questions of TB-001..003" in md and "—" not in md


def test_old_rules_unchanged_when_phase9_fails(runs, monkeypatch):
    monkeypatch.setattr(gate_summary, "V9_QA_MIN", 12)
    monkeypatch.setattr(gate_summary, "V9_SUM_MIN", 19)
    _run(runs, "r3", _qa(p9=["pass"] * 3 + ["missed"] * 9), _summary(v9=(5, 19)))
    assert gate_summary.main("r3", "baseline") == 1
    _, rows = _table(runs, "r3")
    assert rows["Ask the Case File"][0].startswith("33/33") and rows["Ask the Case File"][-1] == "yes"
    assert rows["Summary omission"][0].startswith("47/48") and rows["Summary omission"][-1] == "yes"
    assert rows["Ask the Case File, oral cavity / cervix (Phase 9)"][-1] == "NO" and rows["Ask the Case File, oral cavity / cervix (Phase 9)"][2] == "0 fabrications, >= 12 pass"
    assert rows["Summary omission, Phase 9 cases"][-1] == "NO" and rows["Summary omission, Phase 9 cases"][2] == ">= 19 key fields"


def test_old_rules_still_bite_with_phase9_perfect(runs):
    _run(runs, "r4", _qa(old_pass=32, p9=["pass"] * 12), _summary(old_hits=(16, 15, 15)))
    assert gate_summary.main("r4", "baseline") == 1
    _, rows = _table(runs, "r4")
    assert rows["Ask the Case File"][-1] == "NO" and rows["Summary omission"][-1] == "NO"  # 32/33 and 46/48: the Phase 9 cases never top them up
    assert rows["Ask the Case File, oral cavity / cervix (Phase 9)"][-1] == "yes"


def test_missing_phase9_block_is_skipped(runs):
    _run(runs, "r5", _qa(p9=None), _summary(v9=None))
    assert gate_summary.main("r5", "baseline") == 0  # an older run without Phase 9 numbers keeps its verdict
    md, rows = _table(runs, "r5")
    assert rows["Ask the Case File, oral cavity / cervix (Phase 9)"][0] == "not run (no Phase 9 block)"
    assert rows["Ask the Case File, oral cavity / cervix (Phase 9)"][-1] == "skipped"
    assert rows["Summary omission, Phase 9 cases"][-1] == "skipped" and "Phase 9 timings" not in md
    n = gate_summary.numbers(runs / "r5")
    assert n["qa9_ran"] is False and "qa9_pass" not in n and "sum9_hit" not in n


def test_evals_not_run_phase9_skipped(runs):
    _run(runs, "r6")
    gate_summary.main("r6", "baseline")
    _, rows = _table(runs, "r6")
    assert rows["Ask the Case File, oral cavity / cervix (Phase 9)"][0] == "skipped" and rows["Ask the Case File, oral cavity / cervix (Phase 9)"][-1] == "skipped"


def test_phase9_fabrication_makes_the_run_red(runs):
    _run(runs, "r7", _qa(p9=["pass"] * 11 + ["fabrication"]), _summary())
    assert gate_summary.main("r7", "baseline") == 1
    _, rows = _table(runs, "r7")
    assert rows["Ask the Case File"][-1] == "yes" and rows["Ask the Case File, oral cavity / cervix (Phase 9)"][-1] == "NO"
    assert "1 fabrications" in rows["Ask the Case File, oral cavity / cervix (Phase 9)"][0]


# ---- qa_eval: two waves ----------------------------------------------------------------------------------------
def test_first_wave_is_exactly_the_33_old_probes():
    assert qa_eval.PROBES == OLD_PROBES
    assert sum(len(v) for v in qa_eval.PROBES.values()) == 33
    assert "TB-007" in qa_eval.PROBES_V9 and not set(qa_eval.PROBES_V9) & set(qa_eval.PROBES)
    p7 = qa_eval.PROBES_V9["TB-007"]
    assert len(p7) == 12 and [k for _, k, _ in p7].count("absent") == 3 and [k for _, k, _ in p7].count("scope") == 2


def _fake_corpus(tmp_path, monkeypatch, cases):
    corpus = tmp_path / "corpus"
    for c in cases:
        (corpus / "cases" / c).mkdir(parents=True)
        (corpus / "cases" / c / "case.json").write_text(json.dumps({"case_id": c}))
    monkeypatch.setattr(config, "DEMO_CORPUS", corpus)
    return corpus


@pytest.mark.parametrize("with_v9", [True, False])
def test_qa_eval_two_waves(tmp_path, monkeypatch, with_v9):
    _fake_corpus(tmp_path, monkeypatch, ["TB-007"] if with_v9 else [])
    asked = []

    async def fake_ask(case, q, history=None):
        asked.append(case)
        await asyncio.sleep(0)
        if case == "TB-007" and "HPV" in q:  # a fabrication in the Phase 9 wave only
            return {"status": "answered", "statements": [{"text": "p16 positive", "citations": [{"quote": "p16 positive"}]}], "seconds": 2.0}
        return {"status": "not_documented", "statements": [], "seconds": 1.0}
    monkeypatch.setattr(qa_eval.qa, "ask", fake_ask)
    s = asyncio.run(qa_eval.run("unit"))
    out = json.loads((config.DATA_ROOT / "eval" / "qa_unit.json").read_text())
    assert out["n"] == 33 and {r["case"] for r in out["rows"]} == set(OLD) and out["fabrication"] == 0
    if with_v9:
        p9 = out["phase9"]
        assert p9["n"] == 12 and p9["cases"] == ["TB-007"] and {r["case"] for r in p9["rows"]} == {"TB-007"} and p9["fabrication"] == 1
        assert asked[:33] == [c for c in OLD for _ in OLD_PROBES[c]] and asked[33:] == ["TB-007"] * 12  # the second wave starts after the first
    else:
        assert "phase9" not in out and len(asked) == 33
    assert s["n"] == 33


# ---- summary_eval / prepare_cases --------------------------------------------------------------------------------
def test_summary_eval_cases_and_tb007_fields_are_catalogue_ids():
    assert summary_eval.CASES == list(OLD) and summary_eval.CASES_V9[0] == "TB-007"
    cat = protocol.facts()
    missing = [f for f in TB007_FIELDS if summary_eval.KEYMAP.get(f, f) not in cat]
    assert not missing, missing
    assert not set(TB007_FIELDS) & summary_eval.NOT_FACTS


def test_prepare_cases_default_includes_phase9_when_in_corpus(tmp_path, monkeypatch, capsys):
    _fake_corpus(tmp_path, monkeypatch, [])
    assert prepare_cases.default_cases() == list(OLD) and "SKIP TB-007" in capsys.readouterr().out
    _fake_corpus(tmp_path / "b", monkeypatch, ["TB-007"])
    assert prepare_cases.default_cases() == list(OLD) + ["TB-007"]


# ---- e2e_api: the Phase 9 spec ---------------------------------------------------------------------------------
def test_e2e_phase9_spec():
    sp = e2e_api.V9_CASES["TB-007"]
    assert sp["protocol"] == "oral_cavity" and sp["listing"]["protocol"] == "oral_cavity" and sp["listing"]["setting"] == "locally_advanced"
    assert sp["decision"].count(sp["dose"]) == 1 and sp["decision"].replace(sp["dose"], sp["slip"], 1) != sp["decision"]
    assert "Inj. Cisplatin 40 mg/m2 IV weekly" in sp["decision"] and "cT4a N1 M0" in sp["decision"]
    assert "UHID: SYN-700352" in sp["intake"]["text"] and "FINAL" in sp["intake"]["text"] and "Sd/-" in sp["intake"]["text"]
    assert {m["department"] for m in sp["members"]} == {"Surgical Oncology", "Radiation Oncology", "Medical Oncology"}
    assert all("(synthetic)" in m["name"] for m in sp["members"])
    assert "—" not in json.dumps(e2e_api.V9_CASES, ensure_ascii=False)
