"""Review of V1 Phase 9 (oral cavity, cervix): region false matches, conditional NCG tiers in the gate, FIGO stage forms, radiotherapy
fraction ranges written per fraction, value-search synonyms that must not take over other queries, and the NCG quotes checked against the
guideline files themselves (not only against the research note)."""
import html
import json
import re
import zipfile

import pytest

from tumour_board import config, dosecheck, protocol, rules, search, store
from tumour_board.tests import util


def _doc(title):
    return {"classification": {"title": title}, "filename": "x.pdf", "pages": []}


@pytest.mark.parametrize("title,ok", [("CECT FACE AND NECK", True), ("MRI ORAL CAVITY", True), ("USG NECK", True), ("MRI TONGUE", True),
                                      ("CT LIP", True), ("OPG MANDIBLE", True), ("CECT ABDOMEN AND PELVIS WITH ORAL CONTRAST", False),
                                      ("CT NECK OF FEMUR", False), ("USG LIPOMA BACK", False), ("CT CHEST", False)])
def test_oral_imaging_region(title, ok):
    region = next(r for r in protocol.records("oral_cavity") if r["id"] == "primary_neck_imaging")["region"]
    assert rules._region_ok(_doc(title), region) is ok


def test_conditional_record_in_the_gate_shows_the_ncg_tier():
    store.create_case("TB-COND", util.PATIENT, "cervix", created_by="test")
    g = rules.evaluate("TB-COND")
    shown = {r["id"]: r for r in g["shown"]}
    ct = shown["ct_thorax"]
    assert ct["tier"] == "c" and ct["ncg_tier"] == "a" and not ct["required"]
    assert ct["tier_note"].startswith("NCG Essential for patients with para-aortic nodes (FIGO IIIC2): shown, not counted")
    assert shown["pet_ct"].get("ncg_tier") is None and shown["pet_ct"]["tier_note"] == "NCG Optional: shown only"  # NCG (c) as printed
    assert "ct_thorax" not in {r["id"] for r in g["requirements"]}


@pytest.mark.parametrize("decision,recorded,result", [
    ("Ca Cx FIGO IIIB: concurrent chemoradiation.", "FIGO stage IIB", "stage_differs"),
    ("FIGO 2018: IIB.", "IIB", "stage_consistent"),
    ("FIGO 2018 Stage IIB as recorded.", "IIB", "stage_consistent"),
    ("Stage IIIC1r.", "FIGO (2018) stage IIIC1p", "stage_consistent"),  # the r / p suffix is written, never compared
    ("Clinical stage IIIA.", "Stage IIIA", "stage_consistent"),
])
def test_figo_stage_forms(decision, recorded, result):
    s, e = dosecheck._stage_scan(decision)[0]
    w = dosecheck.parse_stage(decision[s:e], before=decision[max(0, s - 40):s])
    assert dosecheck.compare_stage(w, dosecheck.parse_stage(recorded, bare=True))[0] == result


def test_plan_steps_and_years_are_not_stages():
    assert dosecheck._stage_scan("Stage 1: surgery, then chemoradiation") == []
    assert dosecheck.parse_stage("FIGO 2018", bare=True) is None


@pytest.mark.parametrize("text", ["SBRT 8 Gy x 5 - 12/10/2026", "4 Gy x 5 - 2026", "2 Gy x 5-6 weeks", "9 Gy x 2 - 3 weeks apart",
                                  "10 Gy x 5 - 7 days apart", "8 Gy x 1-30 fractions", "2 Gy x 5 a week"])
def test_no_fraction_range_from_dates_weeks_or_days(text):
    assert dosecheck.parse_rt(text) == []


def test_fraction_ranges_and_dose_per_fraction():
    r = dosecheck.parse_rt("BT dose of 7 Gy * 2-3 Fr high dose rate.")[0]
    assert (r["total_gy"], r["total_gy_max"], r["fractions"], r["fractions_max"], r["gy_per_fraction"]) == (14, 21, 2, 3, 7)
    assert [(x["total_gy"], x["fractions_max"]) for x in dosecheck.parse_rt("7 Gy x 2-3#")] == [(14, 3)]
    assert dosecheck.fmt_rt(r) == "7 Gy x 2-3 fractions (14-21 Gy)"
    assert [(x["total_gy"], x["fractions"]) for x in dosecheck.parse_rt("25 Gy/5 Fr and 400 cGy x 5")] == [(25, 5), (20, 5)]


@pytest.mark.parametrize("query,word", [("any incidental findings?", "findings"), ("incidental nodule", "nodule"), ("Japanese restaurant", "japanese")])
def test_new_synonyms_do_not_take_over_other_queries(query, word):
    pats = search._patterns(query)
    assert any(word in p for p in pats) and not any("opg" in p or "paan" in p for p in pats), pats


def test_new_synonyms_still_find_their_terms():
    assert any("orthopantomogram" in p for p in search._patterns("dental evaluation"))
    assert any("gutka" in p for p in search._patterns("tobacco habit")) and any("lvsi" in p for p in search._patterns("What is the LVSI?"))


def _hn_pages():
    f = config.GUIDELINE_DIR / "ncg_india" / "ncg-guidelines-for-head-neck-cancer-2019.pdf"
    if not f.exists():
        pytest.skip("guideline library not on this machine")
    from pypdf import PdfReader
    return {i + 1: re.sub(r"\s+", " ", p.extract_text() or "") for i, p in enumerate(PdfReader(str(f)).pages) if i + 1 in (2, 4, 5, 6, 7)}


def _gy_paragraphs():
    f = config.GUIDELINE_DIR / "ncg_india" / "ncg-guidelines-for-gynecological-cancer-2019.docx"
    if not f.exists():
        pytest.skip("guideline library not on this machine")
    xml = zipfile.ZipFile(f).read("word/document.xml").decode("utf8", "replace")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", p))).strip() for p in paras]


def test_oral_cavity_quotes_are_on_their_pages_in_the_guideline_file():
    pages = _hn_pages()
    for r in protocol.records("oral_cavity"):
        for src in r["sources"]:
            assert src["quote"] in pages[src["page"]], (r["id"], src["quote"])


def test_cervix_quotes_are_paragraphs_of_the_guideline_file():
    paras = _gy_paragraphs()
    for r in protocol.records("cervix"):
        for src in r["sources"]:
            assert any(src["quote"] in p for p in paras), (r["id"], src["quote"])


def test_no_em_dash_in_any_reference_quote_or_protocol_text():
    """Project rule: no em dashes in UI or reports. Dose reference quotes are shown in board-record flags (NCG prints 'PC weekly—Paclitaxel')."""
    refs = dosecheck.table()["references"]
    assert not [r["id"] for r in refs if "—" in r["quote"]]
    for pid in ("oral_cavity", "cervix"):
        assert "—" not in (config.PROTOCOL_DIR / f"{pid}.json").read_text()
    oc = {(r["drug"], r["dose"]): r["quote"] for r in dosecheck.references("oral_cavity", "drug")}
    assert oc[("paclitaxel", 60)].startswith("Paclitaxel") and "60-80 mg/m2" in oc[("paclitaxel", 60)]
