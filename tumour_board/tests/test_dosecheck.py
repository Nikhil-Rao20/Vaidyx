"""Guideline checks on the board's decision (V1 item 7.2): doses, radiotherapy schedules and the stage as written.

No GPU: llm.chat is replaced by fakes. Done when: "6 mg" vs the reference "60 mg/m2" is flagged with its source; correct doses are
not flagged. The reference table (protocols/dose_references.json) is checked against the guideline index cache when it is present."""
import asyncio
import json
import re

import pytest

from tumour_board import config, dosecheck, llm

TB005 = ("Neoadjuvant chemotherapy: 4 cycles of AC (Inj. Doxorubicin 6 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV, every 21 days), "
         "followed by Inj. Paclitaxel 80 mg/m2 IV weekly for 12 weeks. Response assessment with MRI breast after chemotherapy, then surgery "
         "(breast conservation if response permits) and adjuvant radiotherapy. Endocrine therapy as per receptor status after surgery.")
NCG_BREAST = "ncg_india/ncg-guidelines-for-breast-cancer-2019.pdf"
INDEX = config.REPO / "data" / "tumour_board" / "embed_cache" / "guidelines_index.json"
UNITS = {"mg/m2", "mg/m2/day", "g/m2", "mg/kg", "mg", "mg/day", "AUC"}


def model(drugs=(), rt=(), stage=(), calls=None):
    async def fake(role, messages, **kw):
        if calls is not None:
            calls.append((role, messages, kw))
        return {"drugs": [{"drug": d, "dose_as_written": "", "frequency": "", "cycles": "", "span": s} for d, s in drugs],
                "radiotherapy": [{"as_written": s, "span": s} for s in rt], "stage": [{"as_written": s, "span": s} for s in stage]}
    return fake


def run(text, cancer="breast", recorded_stage=None):
    return asyncio.run(dosecheck.check_decision(text, cancer, recorded_stage))


def by_drug(out, drug):
    return [c for c in out["checks"] if c.get("drug") == drug]


@pytest.fixture
def no_items(monkeypatch):
    monkeypatch.setattr(llm, "chat", model())


# ---------------------------------------------------------------- parsing (Indian notations)

@pytest.mark.parametrize("text,dose,dose_max,unit,written", [
    ("Inj. Doxorubicin 6 mg/m2 IV", 6, None, "mg/m2", "6 mg/m2"),
    ("Doxorubicin 60mg/m²", 60, None, "mg/m2", "60mg/m²"),
    ("Paclitaxel 80 mg /m2 weekly", 80, None, "mg/m2", "80 mg /m2"),
    ("Docetaxel 75 mg/sqm", 75, None, "mg/m2", "75 mg/sqm"),
    ("Cisplatin 75 mg per m2", 75, None, "mg/m2", "75 mg per m2"),
    ("Gemcitabine 1000-1250 mg/m2 days 1 and 8", 1000, 1250, "mg/m2", "1000-1250 mg/m2"),
    ("Atezolizumab 1,200 mg", 1200, None, "mg", "1,200 mg"),
    ("Ifosfamide 1.2 g/m2", 1.2, None, "g/m2", "1.2 g/m2"),
    ("Trastuzumab 8 mg/kg loading", 8, None, "mg/kg", "8 mg/kg"),
    ("Topotecan 2.3 mg/m²/day", 2.3, None, "mg/m2/day", "2.3 mg/m²/day"),
    ("Carboplatin AUC 5", 5, None, "AUC", "AUC 5"),
    ("Carboplatin- @AUC5;", 5, None, "AUC", "AUC5"),
    ("Carboplatin AUC 5-6 day 1", 5, 6, "AUC", "AUC 5-6"),
])
def test_parse_doses_indian_notations(text, dose, dose_max, unit, written):
    d = dosecheck.parse_doses(text)
    assert len(d) == 1
    assert (d[0]["dose"], d[0]["dose_max"], d[0]["unit"], d[0]["written"]) == (dose, dose_max, unit, written)
    assert text[d[0]["start"]:d[0]["end"]] == written


def test_parse_doses_ignores_lab_units():
    d = dosecheck.parse_doses("Creatinine 1.2 mg/dL; carboplatin AUC 5 mg/mL.min")
    assert [(x["dose"], x["unit"], x["written"]) for x in d] == [(5.0, "AUC", "AUC 5")]


@pytest.mark.parametrize("text,expected", [
    ("50 Gy/25#", (50, None, 25, None)),
    ("25 Gy in 5 fractions", (25, None, 5, None)),
    ("45-50.4 Gy in 25-28 fractions", (45, 50.4, 25, 28)),
    ("5 x 5 Gy", (25, None, 5, None)),
    ("5 Gy x 5", (25, None, 5, None)),
    ("40Gy/15fractions/3weeks", (40, None, 15, None)),
    ("20 Gray /5#", (20, None, 5, None)),
    ("8 Gy single fraction", (8, None, 1, None)),
    ("25 Gy in five fractions", (25, None, 5, None)),
    ("5040 cGy in 28 fractions", (50.4, None, 28, None)),
    ("boost 10 Gy", (10, None, None, None)),
])
def test_parse_rt(text, expected):
    r = dosecheck.parse_rt(text)
    assert len(r) == 1
    got = (r[0]["total_gy"], r[0]["total_gy_max"], r[0]["fractions"], r[0]["fractions_max"])
    assert [g is None for g in got] == [e is None for e in expected]
    assert [g for g in got if g is not None] == pytest.approx([e for e in expected if e is not None])


def test_parse_rt_dose_per_fraction_is_not_a_total():
    for t in ("50.4 Gy in 28 fractions (1.8 Gy per fraction)", "50 Gy in 25 fractions of 2 Gy"):
        assert len(dosecheck.parse_rt(t)) == 1
    assert dosecheck.parse_rt("boost 10 Gy", require_fractions=True) == []


@pytest.mark.parametrize("text,group,prefix,t,n,m", [
    ("Stage IIIB", "IIIB", "", None, None, None),
    ("stage iia", "IIA", "", None, None, None),
    ("Stage 3A", "IIIA", "", None, None, None),
    ("cT2 N1 M0", None, "c", "T2", "N1", "M0"),
    ("pT2N1aM0", None, "p", "T2", "N1a", "M0"),
    ("ypT0 N0", None, "yp", "T0", "N0", None),
    ("Stage IIIA (cT2 N2 M0)", "IIIA", "c", "T2", "N2", "M0"),
])
def test_parse_stage(text, group, prefix, t, n, m):
    s = dosecheck.parse_stage(text)
    assert (s["group"], s["prefix"], s["t"], s["n"], s["m"]) == (group, prefix, t, n, m)


def test_parse_stage_needs_a_stage_not_a_sequence_name():
    assert dosecheck.parse_stage("MRI pelvis T2-weighted images") is None
    assert dosecheck.parse_stage("IIA") is None
    assert dosecheck.parse_stage("IIA", bare=True)["group"] == "IIA"


# ---------------------------------------------------------------- the reference table

def test_table_validates():
    t = dosecheck.table()
    assert "clinical review" in t["_note"] or "review by the clinical team" in t["_note"]
    assert "build_dose_references" in t["_note"]
    refs = t["references"]
    assert len({r["id"] for r in refs}) == len(refs)
    for r in refs:
        assert r["cancer"] in ("breast", "lung_nsclc", "colorectal_rectum")
        assert r["region"] in dosecheck.REGION_ORDER
        assert r["file"] and r["org"] and isinstance(r["page"], int) and r["quote"].strip()
        if r["kind"] == "drug":
            assert r["drug"] == r["drug"].lower() and r["as_written"]
            assert r["unit"] in UNITS
            assert r["dose"] > 0 and (r.get("dose_max") is None or r["dose_max"] > r["dose"])
            assert str(r["dose"]).rstrip("0").rstrip(".") in r["quote"].replace(",", "") or r["unit"] == "AUC"
        else:
            assert r["kind"] == "rt"
            assert r["total_gy"] > 0 and isinstance(r["fractions"], int) and r["fractions"] >= 1
    for cancer in ("breast", "lung_nsclc", "colorectal_rectum"):
        regions = [dosecheck.REGION_ORDER[r["region"]] for r in refs if r["cancer"] == cancer]
        assert regions == sorted(regions), f"{cancer}: Indian entries first"
        assert regions[0] == 0
        assert {r["kind"] for r in refs if r["cancer"] == cancer} == {"drug", "rt"}
    generics = {r["drug"] for r in refs if r["kind"] == "drug"}
    assert all(g in generics for g in t["aliases"].values())


def test_table_aliases_come_from_the_guideline_text():
    t = dosecheck.table()
    written = {r["as_written"].lower() for r in t["references"] if r["kind"] == "drug"}
    assert t["aliases"]["adriamycin"] == "doxorubicin"
    assert all(a in written or a == "5-fu" for a in t["aliases"])  # 5-FU: standard abbreviation, allowed


def _ws(s):
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.skipif(not INDEX.exists(), reason="guideline index cache not built on this machine")
def test_every_quote_is_verbatim_on_its_file_and_page():
    chunks = json.loads(INDEX.read_text())["chunks"]
    pages = {}
    for c in chunks:
        for p in range(c["page"], (c.get("page_end") or c["page"]) + 1):
            pages.setdefault((c["file"], p), []).append(_ws(c["text"]))
    missing = [r["id"] for r in dosecheck.table()["references"]
               if not any(_ws(r["quote"]) in t for t in pages.get((r["file"], r["page"]), []))]
    assert missing == []


@pytest.mark.skipif(not INDEX.exists(), reason="guideline index cache not built on this machine")
def test_ncg_breast_ac_line_in_table():
    r = next(r for r in dosecheck.references("breast", "drug") if r["drug"] == "doxorubicin" and r["dose"] == 60)
    assert (r["file"], r["page"], r["region"], r["as_written"]) == (NCG_BREAST, 11, "India", "Adriamycin")
    assert "Adriamycin – 60 mg/m2" in r["quote"]


def test_references_and_names():
    refs = dosecheck.references("breast")
    assert refs and refs[0]["region"] == "India"
    assert dosecheck.references("no_such_cancer") == []
    names = dosecheck.drug_names("breast")
    assert names["adriamycin"] == "doxorubicin" and names["doxorubicin"] == "doxorubicin" and names["5-fluorouracil"] == "fluorouracil"
    assert "pemetrexed" not in names and dosecheck.drug_names()["pemetrexed"] == "pemetrexed"


# ---------------------------------------------------------------- comparison and flags

def test_tb005_demo_decision_one_flag(no_items):
    out = run(TB005)
    assert len(out["flags"]) == 1
    f = out["flags"][0]
    assert (f["kind"], f["check"], f["severity"]) == ("guideline", "dose", "expert_review")
    assert f["recorded"] == "6 mg/m2" and "Doxorubicin 6 mg/m2" in f["span"]
    assert f["reference"]["file"] == NCG_BREAST and f["reference"]["page"] == 11 and f["reference"]["dose"] == 60
    assert "Adriamycin – 60 mg/m2" in f["reference"]["quote"]
    assert f["text"] == ("Possible transcription error: Doxorubicin recorded as \"6 mg/m2\"; the guideline reference states 60 mg/m2 "
                         "(National Cancer Grid (NCG), India, p 11). Expert review: the check flags the difference, it does not decide which dose is correct.")
    assert [c["result"] for c in by_drug(out, "doxorubicin")] == ["possible_transcription_error"]
    assert [c["result"] for c in by_drug(out, "cyclophosphamide")] == ["consistent"]
    assert [c["result"] for c in by_drug(out, "paclitaxel")] == ["consistent"]
    assert by_drug(out, "paclitaxel")[0]["references"][0]["region"] == "India"


def test_done_when_6_mg_vs_60_mg_m2_is_flagged_with_source(no_items):
    out = run("Inj. Doxorubicin 6 mg IV every 21 days")
    [f] = out["flags"]
    assert f["severity"] == "expert_review" and f["recorded"] == "6 mg"
    assert f["reference"]["file"] == NCG_BREAST and f["reference"]["page"] == 11 and f["reference"]["quote"]


def test_correct_doses_not_flagged(no_items):
    out = run("AC: Inj. Doxorubicin 60 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV every 21 days x 4, then Paclitaxel 175 mg/m2 "
              "every 3 weeks; Inj. Trastuzumab 8 mg/kg loading followed by 6 mg/kg; Carboplatin AUC 5; Tab. Tamoxifen 20 mg OD; "
              "Capecitabine 1 g/m2 BD")
    assert out["flags"] == []
    assert {c["result"] for c in out["checks"]} == {"consistent"}
    assert len(out["checks"]) == 8


def test_adriamycin_alias_and_differs(no_items):
    out = run("Inj. Adriamycin 60 mg/m2; Inj. Paclitaxel 100 mg/m2 weekly")
    assert by_drug(out, "doxorubicin")[0]["result"] == "consistent"
    [f] = out["flags"]
    assert by_drug(out, "paclitaxel")[0]["result"] == "differs_from_reference"
    assert f["severity"] == "review" and f["text"].startswith("Differs from guideline reference: Paclitaxel recorded as \"100 mg/m2\"")
    assert "80 mg/m2" in f["text"] and "(National Cancer Grid (NCG), India, p 11)" in f["text"]
    assert f["reference"]["region"] == "India"


def test_trastuzumab_wrong_unit_is_transcription_error(no_items):
    out = run("Inj. Trastuzumab 6 mg/m2 every 3 weeks")
    [f] = out["flags"]
    assert f["severity"] == "expert_review" and f["reference"]["unit"] == "mg/kg" and f["reference"]["dose"] == 6


def test_unknown_drug_is_info_not_a_pass(monkeypatch):
    text = "Inj. Zolbetuximab 800 mg/m2 loading dose"
    monkeypatch.setattr(llm, "chat", model(drugs=[("Inj. Zolbetuximab", "Zolbetuximab 800 mg/m2")]))
    out = run(text)
    [c] = out["checks"]
    assert (c["drug"], c["result"], c["references"]) == ("zolbetuximab", "no_reference", [])
    [f] = out["flags"]
    assert f["severity"] == "info" and f["reference"] is None and "Info only, not a pass" in f["text"]


def test_dose_never_tied_across_another_drug_name(monkeypatch):
    # Zolbetuximab is not in the table: its dose must not be read as a second cyclophosphamide dose, nor doxorubicin's first dose
    monkeypatch.setattr(llm, "chat", model(drugs=[("Zolbetuximab", "Inj. Zolbetuximab 800 mg/m2")]))
    out = run("Inj. Cyclophosphamide 600 mg/m2 and Inj. Zolbetuximab 800 mg/m2")
    assert [(c["drug"], c["recorded"], c["result"]) for c in out["checks"]] == [
        ("cyclophosphamide", "600 mg/m2", "consistent"), ("zolbetuximab", "800 mg/m2", "no_reference")]
    out = run("Doxorubicin and Inj. Zolbetuximab 800 mg/m2")
    assert [c["drug"] for c in out["checks"]] == ["zolbetuximab"]


def test_model_label_never_overrides_the_text(monkeypatch):
    monkeypatch.setattr(llm, "chat", model(drugs=[("Paclitaxel", "6 mg/m2")]))  # the model mislabels doxorubicin's dose
    out = run(TB005)
    assert [c["drug"] for c in out["checks"] if c["recorded"] == "6 mg/m2"] == ["doxorubicin"]


def test_drug_known_for_another_cancer_has_no_reference_here(no_items):
    out = run("Tab Gefitinib 250 mg OD")
    assert [c["result"] for c in out["checks"]] == ["no_reference"]
    assert run("Tab Gefitinib 250 mg OD", cancer="lung_nsclc")["flags"] == []


def test_model_span_not_in_text_is_dropped(monkeypatch):
    # the model 'corrects' the dose and invents a drug: neither span is in the decision, so neither is used
    monkeypatch.setattr(llm, "chat", model(drugs=[("Doxorubicin", "Inj. Doxorubicin 60 mg/m2 IV"), ("Zolbetuximab", "Zolbetuximab 800 mg/m2")]))
    out = run(TB005)
    assert not any(c.get("drug") == "zolbetuximab" for c in out["checks"])
    assert [c["recorded"] for c in by_drug(out, "doxorubicin")] == ["6 mg/m2"]
    assert len(out["flags"]) == 1


def test_model_numbers_never_trusted(monkeypatch):
    # dose_as_written says 60 but the span (found in the text) says 6: the code reads the span
    async def fake(role, messages, **kw):
        return {"drugs": [{"drug": "Doxorubicin", "dose_as_written": "60 mg/m2", "frequency": "", "cycles": "", "span": "Doxorubicin 6 mg/m2"}],
                "radiotherapy": [], "stage": []}
    monkeypatch.setattr(llm, "chat", fake)
    assert [c["dose"] for c in by_drug(run(TB005), "doxorubicin")] == [6]


def test_model_missing_item_code_scan_still_flags(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat", model(drugs=[("Cyclophosphamide", "Inj. Cyclophosphamide 600 mg/m2 IV")], calls=calls))
    out = run(TB005)
    [f] = out["flags"]
    assert f["recorded"] == "6 mg/m2" and f["severity"] == "expert_review"
    assert len(by_drug(out, "cyclophosphamide")) == 1  # model item and code scan item deduplicated
    role, messages, kw = calls[0]
    assert role == "reasoner" and kw["purpose"] == "adjudication: guideline checks" and kw["json_schema"] == dosecheck.SCHEMA
    assert "Do not judge" in messages[0]["content"] and TB005 in messages[1]["content"]


def test_model_failure_code_scan_still_runs(monkeypatch):
    async def boom(*a, **kw):
        raise llm.LLMError("reasoner unreachable")
    monkeypatch.setattr(llm, "chat", boom)
    out = run(TB005)
    info = [f for f in out["flags"] if f["kind"] == "system"]
    assert len(info) == 1 and info[0]["severity"] == "info" and "model listing was unavailable" in info[0]["text"]
    assert [f["recorded"] for f in out["flags"] if f["kind"] == "guideline"] == ["6 mg/m2"]


def test_formulary_brand_names(monkeypatch, data_root):
    (data_root / "formulary.json").write_text(json.dumps({"Doxoryl": "Doxorubicin"}))
    monkeypatch.setattr(llm, "chat", model())
    assert dosecheck.drug_names()["doxoryl"] == "doxorubicin"
    out = run("Inj. Doxoryl 6 mg/m2 IV")
    assert [c["drug"] for c in out["checks"]] == ["doxorubicin"] and out["flags"][0]["severity"] == "expert_review"


def test_no_formulary_means_no_brands():
    assert dosecheck.formulary() == {}


def test_auc_doses_lung(no_items):
    ok = run("Carboplatin AUC 5 day 1 + Pemetrexed 500 mg/m2 day 1 every 21 days", cancer="lung_nsclc")
    assert ok["flags"] == [] and len(ok["checks"]) == 2
    bad = run("Carboplatin @AUC50 day 1", cancer="lung_nsclc")
    assert bad["flags"][0]["severity"] == "expert_review" and bad["flags"][0]["reference"]["unit"] == "AUC"


# ---------------------------------------------------------------- radiotherapy

def test_rt_schedules(no_items):
    ok = run("Adjuvant radiotherapy 40 Gy/15# to the chest wall")
    assert ok["flags"] == [] and ok["checks"][0]["result"] == "consistent"
    slip = run("Adjuvant radiotherapy 4 Gy in 15 fractions")
    [f] = slip["flags"]
    assert (f["check"], f["severity"]) == ("rt", "expert_review") and "40 Gy in 15 fractions" in f["text"]
    differs = run("Adjuvant radiotherapy 60 Gy in 30 fractions")
    assert differs["flags"][0]["severity"] == "review" and differs["checks"][0]["result"] == "differs_from_reference"
    rectal = run("Short course RT 5 x 5 Gy followed by surgery", cancer="colorectal_rectum")
    assert rectal["flags"] == [] and rectal["checks"][0]["references"][0]["region"] == "India"


def test_rt_total_without_fractions_compares_total_only(no_items):
    assert run("Whole breast RT to 50 Gy")["flags"] == []
    assert run("Whole breast RT to 5 Gy")["flags"][0]["severity"] == "expert_review"


# ---------------------------------------------------------------- stage as recorded

REC = {"value": "Stage IIA", "quote": "Pathological stage: Stage IIA (pT2 N0 M0)", "doc_id": "Dhist0001", "doc_title": "Histopathology report"}


def test_stage_equal(no_items):
    out = run("Stage IIA carcinoma breast, for surgery", recorded_stage=REC)
    [c] = [c for c in out["checks"] if c["kind"] == "stage"]
    assert c["result"] == "stage_consistent" and out["flags"] == []


def test_stage_differs_cites_signed_report(monkeypatch):
    monkeypatch.setattr(llm, "chat", model(stage=["stage IIIB"]))
    out = run("Locally advanced, stage IIIB: neoadjuvant chemotherapy", recorded_stage=REC)
    [f] = out["flags"]
    assert (f["kind"], f["check"], f["severity"]) == ("guideline", "stage", "review")
    assert f["source"] == REC and f["recorded"] == "stage IIIB"
    assert "Histopathology report" in f["text"] and "does not compute a stage" in f["text"]
    assert len([c for c in out["checks"] if c["kind"] == "stage"]) == 1  # model span and code scan merged


def test_stage_tnm_prefix_difference_not_compared(no_items):
    rec = {"value": "pT2 N0 M0", "quote": "pT2 N0 M0", "doc_id": "D1", "doc_title": "Histopathology report"}
    out = run("cT3 N1 M0 on MRI; plan neoadjuvant therapy", recorded_stage=rec)
    assert [c["result"] for c in out["checks"] if c["kind"] == "stage"] == ["stage_not_compared"] and out["flags"] == []
    same = run("pT2 N1 M0 after surgery", recorded_stage=rec)
    assert same["flags"][0]["check"] == "stage"  # same prefix: N1 vs N0 differs


def test_stage_like_with_like_only(no_items):
    rec = {"value": "pT2 N0 M0", "quote": "", "doc_id": "D1", "doc_title": "Histopathology report"}
    out = run("Stage IIA: adjuvant chemotherapy", recorded_stage=rec)  # group vs TNM: never derived, not compared
    assert [c["result"] for c in out["checks"] if c["kind"] == "stage"] == ["stage_not_compared"]
    assert run("Stage IIIB disease")["checks"][0]["result"] == "stage_not_compared"  # no recorded stage
    assert run("Stage IIA (pT2a N0)", recorded_stage={**rec, "value": "pT2 N0 M0"})["flags"] == []  # T2a within T2


def test_flag_text_plain(no_items):
    out = run(TB005 + " Inj. Paclitaxel 100 mg/m2. Inj. Zolbetuximab 800 mg/m2. RT 4 Gy in 15 fractions.", recorded_stage=REC)
    for f in out["flags"]:
        assert "—" not in f["text"] and "–" not in f["text"]
