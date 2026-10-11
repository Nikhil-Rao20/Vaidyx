"""V1-9.2: synthetic cervix demo case TB-008 in the demo corpus generator (no GPU, no model calls).

Same checks as the TB-007 tests (test_demo_v9.py, whose helpers are reused): every answer-key value printed in its document,
protocol cervix, names as planned, board decision, the cystoscopy / proctoscopy record only as a later arrival, the --only
build, and, when the generated corpus is present, TB-008 in it matching the generator and passing check_corpus."""
import json
from pathlib import Path

import pytest

from tumour_board import protocol
from tumour_board.demo_data import check_corpus, india_corpus as ic
from tumour_board.tests.test_demo_v9 import CORPUS, _dmy, _fake_build, _norm, source_text

CID = "TB-008"
CASE = next(c for c in ic.V1_CASES if c[0] == CID)
DOCS, ARRIVALS = CASE[3], CASE[4]
ALL = DOCS + ARRIVALS


def _doc(path):
    return next(d for d in ALL if d["path"] == path)


def test_case_registration_and_protocol():
    cid, prot, pat, _, _ = CASE
    assert prot == "cervix"
    assert pat == {"name": "Parvathi Naik", "mrn": "SYN-800415", "agesex": "46 Y / F"}
    assert ic.V1_PATIENTS[CID] is ic.P8 and ic.P8["abha"] == "91-7283-5519-0634" and ic.P8["relation"] == "W/o Ramesh Naik"
    assert "aadhaar" not in ic.P8
    assert len(DOCS) == 6 and len(ARRIVALS) == 2
    assert len({d["path"] for d in ALL}) == len(ALL)


@pytest.mark.parametrize("d", ALL, ids=[d["path"] for d in ALL])
def test_every_truth_value_is_printed(d):
    t, flat = d["truth"], _norm(source_text(d))
    assert "synthetic" in flat
    assert t["doc_type"] in protocol.doc_types()
    want = [v for v in list(t.get("fields", {}).values()) + list(t.get("other_values", {}).values()) if v]
    want += list(t["identity"].values()) + [_dmy(t[k]) for k in ("report_date", "event_date") if t.get(k)]
    want += [x.split(": ", 1)[1] for x in t.get("negated", []) + t.get("not_negations", [])]
    missing = [w for w in want if _norm(w) not in flat]
    assert not missing, missing


def test_names_printed_as_planned():
    """Only the lab report prints the title Smt.; every other document prints the registered name."""
    for d in ALL:
        name = d["truth"]["identity"]["name"]
        assert name == ("Smt. Parvathi Naik" if d["path"].startswith("laboratory_medicine/") else "Parvathi Naik"), d["path"]


def test_key_values():
    opd = _doc("surgical_oncology/gynae_onc_opd_2026-09-15.pdf")
    flat = _norm(source_text(opd))
    assert "ecog performance status: 1" in flat and "figo 2018 stage iib" in flat
    assert opd["truth"]["identity"]["relation"] == "W/o Ramesh Naik"
    hp = _doc("pathology/cervical_biopsy_2026-09-12.pdf")["truth"]
    assert hp["fields"]["lvi"] == "Not identified" and hp["negated"] == ["Lymphovascular space invasion (LVSI): Not identified"]
    assert "abha" in hp["identity"]
    lab = _doc("laboratory_medicine/cbc_lft_rft_hiv_2026-09-15.pdf")["truth"]
    assert lab["fields"]["hiv_status"] == "Non-reactive" and "HIV I and II antibodies: Non-reactive" in lab["not_negations"]
    photo = _doc("radio_diagnosis/xray_chest_pa_2026-09-16_phone_photo.png")
    assert photo["fmt"] == "photo" and photo["truth"]["doc_type"] == "xray"
    figo = [d["path"] for d in ALL if "figo_stage" in d["truth"].get("fields", {})]
    assert figo == ["surgical_oncology/gynae_onc_opd_2026-09-15.pdf", "radio_diagnosis/mri_pelvis_2026-09-17.pdf"]


def test_cystoscopy_only_arrives_later():
    """The cystoscopy / proctoscopy record is the later arrival that closes the gap; no initial document holds it."""
    paths = [d["path"] for d in ARRIVALS]
    assert paths == ["surgical_oncology/cystoscopy_proctoscopy_2026-09-22.pdf", "tumour_board/tumour_board_record_2026-09-26.pdf"]
    cy = ARRIVALS[0]
    assert cy["truth"]["doc_type"] == "endoscopy" and cy["truth"]["fields"] == {}
    assert not [d["path"] for d in DOCS if "cystoscop" in _norm(source_text(d)) or "proctoscop" in _norm(source_text(d))]


def test_board_decision():
    rec = ARRIVALS[1]
    bd = ic.BOARD_DECISION_8
    assert rec["truth"]["board_decision"] is bd and ic.BOARD_DECISIONS[CID] is bd
    assert set(ic.BOARD_DECISIONS) == {"TB-005", "TB-007", "TB-008"}
    assert bd["text"] == ic.DECISION_TEXT_8 and bd["document"] == rec["path"] and bd["board_date"] == rec["truth"]["event_date"] == "2026-09-26"
    assert set(ic.BOARD_DECISION) <= set(bd) and bd["dose_slips"] == [] and bd["absent_specialties"] == []
    for w in ("50 Gy in 25 fractions", "Cisplatin 40 mg/m2 IV weekly", "7 Gy x 3 fractions to point A", "FIGO 2018 Stage IIB as recorded"):
        assert w in bd["text"]
    flat = _norm(source_text(rec))
    assert _norm(ic.DECISION_TEXT_8) in flat
    for w in ("radiation oncology", "medical oncology", "surgical oncology", "gynaecologic oncology"):
        assert w in flat


def test_no_em_or_en_dash_in_tb008():
    blob = json.dumps([ic.P8, ic.BOARD_DECISION_8, ALL], ensure_ascii=False, default=str)
    assert "\u2014" not in blob and "\u2013" not in blob


def test_fact_ids_in_catalogue_when_protocol_present():
    if not (Path(protocol.__file__).parent / "protocols" / "cervix.json").exists():
        pytest.skip("protocols/cervix.json not written yet")
    cat = protocol.facts()
    ids = {f for d in ALL for f in d["truth"].get("fields", {})}
    assert not ids - set(cat), sorted(ids - set(cat))


def test_only_builds_just_tb008(tmp_path, monkeypatch):
    out = tmp_path / "corpus"
    keep = {out / "cases" / "TB-007" / "x.pdf": "a", out / "truth" / "TB-007.json": "{}", out / "truth" / "intake.json": '{"files": {}}'}
    for p, s in keep.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
    _fake_build(out, monkeypatch, {CID})
    for p, s in keep.items():
        assert p.read_text() == s, p
    truth = json.loads((out / "truth" / f"{CID}.json").read_text())
    assert truth["protocol"] == "cervix" and truth["board_decision"]["text"] == ic.DECISION_TEXT_8
    assert truth["registered_identity"]["uhid"] == "SYN-800415"
    assert set(truth["documents"]) == {d["path"] for d in DOCS} and set(truth["arrivals"]) == {d["path"] for d in ARRIVALS}
    assert (out / "truth" / "reference_text" / CID / "radio_diagnosis" / "xray_chest_pa_2026-09-16_phone_photo.png.txt").exists()


def test_full_build_lists_tb008_in_intake(tmp_path, monkeypatch):
    out = tmp_path / "corpus"
    _fake_build(out, monkeypatch, None)
    assert json.loads((out / "truth" / "intake.json").read_text())["patients"]["TB-008"]["uhid"] == "SYN-800415"
    assert json.loads((out / "truth" / "TB-008.json").read_text())["board_decision"]["text"] == ic.DECISION_TEXT_8


needs_corpus = pytest.mark.skipif(not (CORPUS / "truth" / f"{CID}.json").exists(), reason="demo corpus with TB-008 not generated here")


@needs_corpus
def test_corpus_tb008_matches_generator():
    truth = json.loads((CORPUS / "truth" / f"{CID}.json").read_text())
    assert truth["documents"] == json.loads(json.dumps({d["path"]: d["truth"] for d in DOCS}, ensure_ascii=False))
    assert truth["arrivals"] == json.loads(json.dumps({d["path"]: d["truth"] for d in ARRIVALS}, ensure_ascii=False))
    assert truth["protocol"] == "cervix" and truth["board_decision"] == json.loads(json.dumps(ic.BOARD_DECISION_8))
    for grp, items in (("cases", DOCS), ("arrivals", ARRIVALS)):
        for d in items:
            assert (CORPUS / grp / CID / d["path"]).stat().st_size > 0
    intake = json.loads((CORPUS / "truth" / "intake.json").read_text())
    assert intake["patients"].get(CID, {}).get("uhid") == "SYN-800415"


@needs_corpus
def test_corpus_tb008_passes_check_corpus():
    _, problems = check_corpus.check(CORPUS)
    assert not [p for p in problems if p.startswith(CID)], problems
