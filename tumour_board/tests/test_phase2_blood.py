"""Phase 2 checklists, item 2.7 (night-v3): lymphoma and leukaemia, adult and child.

Draft checklists transcribed from the NCG Adult Hematolymphoid book and the NCG Pediatric Haematolymphoid and Solid Tumours book (2019),
labelled "needs a clinician's check" (owner decision D6). The adult flow charts are pictures with no text layer: their quotes carry
`"ocr": true` and the shared test (test_protocol_schema.py) checks them against the project's OCR engine's reading of the page. The
structure checks here copy test_tiers.py."""
import json
import re
from pathlib import Path

import pytest

from tumour_board import config, org, protocol, rules

PIDS = ("lymphoma", "leukaemia")
ADULT = "ncg_india/ncg-guidelines-for-adult-hematolymphoid-2019.pdf"
CHILD = "ncg_india/ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf"
ADULT_NAME = "NCG Guidelines for Adult Hematolymphoid Malignancies (2019)"
CHILD_NAME = "NCG Guidelines for Pediatric Haematolymphoid and Solid Tumours (2019)"
SETTINGS = {
    "lymphoma": ["adult_hodgkin", "adult_nhl", "child_hodgkin", "child_nhl"],
    "leukaemia": ["adult_acute", "adult_chronic", "child_acute", "child_chronic"],
}
COUNTS = {"lymphoma": 17, "leukaemia": 15}


def _raw(pid):
    return json.loads((config.PROTOCOL_DIR / f"{pid}.json").read_text())


def _rec(pid, rid):
    return next(r for r in protocol.records(pid) if r["id"] == rid)


def _tiers(pid, rid):
    r = _rec(pid, rid)
    return [protocol.tier_for(r, s) for s in SETTINGS[pid]]


def _strip_quotes(obj):
    """The file's text without the verbatim book quotes (a quote may hold a dash the book prints)."""
    if isinstance(obj, dict):
        return {k: _strip_quotes(v) for k, v in obj.items() if k != "quote"}
    if isinstance(obj, list):
        return [_strip_quotes(x) for x in obj]
    return obj


def _check_structure(pid):
    """The structure checks of test_tiers.py::test_every_record_has_tier_source_and_valid_fields, plus the Phase 2 source convention."""
    p = protocol.get(pid)
    raw = _raw(pid)
    assert "records" in raw and "mandatory" not in raw
    setting_ids = {s["id"] for s in p["settings"]}
    cat, doc_types = protocol.facts(), set(protocol.doc_types())
    ids = [r["id"] for r in p["records"]]
    assert len(ids) == len(set(ids))
    for r in p["records"]:
        assert r["tier"] in protocol.TIERS, r["id"]
        assert set(r["tiers"]) == setting_ids, r["id"]  # every record names its tier in all four settings (orchestrator decision 4)
        assert all(t in (*protocol.TIERS, "none") for t in r["tiers"].values()), r["id"]
        assert r["tier"] == max(r["tiers"].values(), key=lambda t: protocol.STRICTNESS[t]), r["id"]
        raw_rec = next(x for x in raw["records"] if x["id"] == r["id"])
        assert raw_rec.get("sources") and "source" not in raw_rec, r["id"]
        assert r["source"] == r["sources"][0]
        for src in r["sources"]:
            assert src["guideline"].startswith("NCG") and src["quote"].strip(), r["id"]
            assert (src["file"], src["guideline"]) in ((ADULT, ADULT_NAME), (CHILD, CHILD_NAME)), r["id"]
            assert isinstance(src["page"], int) and not isinstance(src["page"], bool) and src["page"] >= 1, r["id"]
            if "ocr" in src:  # only the adult book's flow chart pictures are read by OCR
                assert src["ocr"] is True and src["file"] == ADULT, r["id"]
        assert all(f in cat for f in r.get("required_facts", [])), r["id"]
        assert set(r.get("doc_types", [])) <= doc_types, r["id"]
        assert r.get("doc_types"), r["id"]
        assert org.department_id(r["department"]) or org.is_owner_alias(r["department"]), (r["id"], r["department"])
        assert isinstance(r.get("sla_days"), int) and r["sla_days"] > 0, r["id"]
        assert r.get("tier_basis"), r["id"]
        if r.get("condition"):  # NCG's own tier under a condition the system never judges: the record itself is shown only
            assert r["condition"]["ncg_tier"] in protocol.TIERS and r["condition"]["text"], r["id"]
            assert "c" in r["tiers"].values(), r["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_protocol_loads_and_is_listed_with_its_settings(pid):
    assert protocol.exists(pid)
    p = protocol.get(pid)
    assert p["id"] == pid and p["label"] and p["site"]
    assert [s["id"] for s in p["settings"]] == SETTINGS[pid]
    assert all(s["label"].endswith("(as recorded)") for s in p["settings"])
    listed = {x["id"]: x for x in protocol.list_protocols()}
    assert pid in listed and [s["id"] for s in listed[pid]["settings"]] == SETTINGS[pid]
    assert listed[pid]["label"] == p["label"] and listed[pid]["version"] == "0.1-draft"
    assert len(p["records"]) == COUNTS[pid]
    assert p["records"] is p["mandatory"]
    assert protocol.settings(pid) == p["settings"]
    assert protocol.setting_label(pid, SETTINGS[pid][0]) == p["settings"][0]["label"]


def test_the_labels_and_site_words_are_the_orchestrators():
    assert protocol.get("lymphoma")["label"] == "Lymphoma (Hodgkin and non-Hodgkin)"
    assert protocol.get("leukaemia")["label"] == "Leukaemia (acute and chronic)"
    assert protocol.get("lymphoma")["site"] == "lymphoma|hodgkin|lymphoid"  # organ words only: "lymph node" and "nodal" would make a neck node report of another cancer step aside
    assert protocol.get("leukaemia")["site"] == "leukaemia|leukemia|marrow"  # not "blast": retinoblastoma, nephroblastoma, medulloblastoma (review)
    breast_site_note = _raw("breast")["site_note"]
    assert all(protocol.get(pid)["site_note"] == breast_site_note for pid in PIDS)


@pytest.mark.parametrize("pid", PIDS)
def test_every_record_has_tier_source_and_valid_fields(pid):
    _check_structure(pid)


@pytest.mark.parametrize("pid", PIDS)
def test_draft_status_and_provenance(pid):
    p = protocol.get(pid)
    assert p["version"] == "0.1-draft"
    assert p["approval"]["status"] == "draft"
    assert "needs a clinician's check" in p["approval"]["note"] and "needs a clinician's check" in p["note"]
    assert "hospital Tumour Board" in p["note"] and "National Cancer Grid" in p["note"] and "OCR" in p["note"]
    assert p["settings_note"]
    assert [g["file"] for g in p["guideline_sources"]] == [ADULT, CHILD]
    assert all(g["guideline"].startswith("NCG") and g["pages"] for g in p["guideline_sources"])
    assert {s["file"] for r in p["records"] for s in r["sources"]} == {ADULT, CHILD}
    for key in ("extract_facts", "core_data", "core_data_source", "post_board", "policy_basis"):
        assert p[key], key
    assert p["post_board"] == _raw("breast")["post_board"]
    stage = next(c for c in p["core_data"] if c["id"] == "stage")
    assert stage["facts"] == ["recorded_stage"] and stage["label"].startswith("Stage or risk group as recorded")


@pytest.mark.parametrize("pid", PIDS)
def test_adult_flow_chart_quotes_are_marked_ocr_and_child_quotes_are_text(pid):
    srcs = [s for r in protocol.records(pid) for s in r["sources"]]
    ocr = [s for s in srcs if s.get("ocr")]
    assert ocr and all(s["file"] == ADULT for s in ocr)
    assert all(not s.get("ocr") for s in srcs if s["file"] == CHILD)
    flow_pages = {"lymphoma": {17, 24, 61}, "leukaemia": {5, 8, 11, 13, 16}}[pid]
    assert {s["page"] for s in ocr} <= flow_pages  # only the flow chart pictures; the annexures have a text layer
    assert all(s["page"] >= 79 for s in srcs if s["file"] == ADULT and not s.get("ocr"))


@pytest.mark.parametrize("pid", PIDS)
def test_scope_words_stay_out_of_the_file(pid):
    """No licensed US guideline network, no stage computation, no accuracy claim."""
    text = (config.PROTOCOL_DIR / f"{pid}.json").read_text().lower()
    assert "nccn" not in text and "national comprehensive" not in text
    assert "accuracy" not in text and "validated" not in text
    assert "computes the stage" not in text


@pytest.mark.parametrize("pid", PIDS)
def test_no_em_or_en_dash_apart_from_inside_quotes(pid):
    assert "—" not in json.dumps(_strip_quotes(_raw(pid)), ensure_ascii=False)
    assert "–" not in json.dumps(_strip_quotes(_raw(pid)), ensure_ascii=False)


@pytest.mark.parametrize("pid", PIDS)
def test_required_facts_can_come_from_the_record_document_types(pid):
    """A required value no document of the record's types can carry would be a gap that never closes (facts.json lists where each fact is read)."""
    cat = protocol.facts()
    for r in protocol.records(pid):
        for f in r["required_facts"]:
            assert set(r["doc_types"]) & set(cat[f]["doc_types"]), (pid, r["id"], f)


@pytest.mark.parametrize("pid", PIDS)
def test_extract_facts_cover_every_required_fact_and_the_general_ones(pid):
    p = protocol.get(pid)
    cat = protocol.facts()
    ef = p["extract_facts"]
    assert len(ef) == len(set(ef)) and all(f in cat for f in ef)
    for r in p["records"]:
        assert set(r["required_facts"]) <= set(ef), r["id"]
    general = {"presenting_complaint", "ecog", "comorbidities", "clinical_question", "recorded_stage", "nodal_findings", "distant_findings",
               "histologic_type", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "patient_preference", "clinical_trial_note",
               "diagnosis_date_mode", "treatment_received"}
    assert general <= set(ef)
    for c in p["core_data"]:
        assert c["facts"] and all(f in cat for f in c["facts"]), c["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_previous_board_is_an_optional_coordinator_record(pid):
    pb = next(x for x in protocol.get(pid)["optional"] if x["id"] == "previous_board")
    assert pb["department"] == "MDT Coordinator" and pb["route"] == "coordinator" and pb["doc_types"] == ["tumour_board_record"]
    assert rules.routed(protocol.get(pid), pb) == (org.COORDINATOR_NAME, None, "coordinator")


# --- tiers that differ by setting -------------------------------------------------------------------------------------------------

def test_lymphoma_tiers_by_setting():
    assert _tiers("lymphoma", "pet_ct_lymphoma") == ["a", "b", "a", "b"]
    assert _tiers("lymphoma", "lymphoma_molecular") == ["none", "b", "none", "b"]
    assert _tiers("lymphoma", "chest_xray_lymphoma") == ["none", "none", "a", "a"]
    assert _tiers("lymphoma", "viral_markers_lymphoma") == ["a", "a", "b", "b"]
    assert _tiers("lymphoma", "pft_lymphoma") == ["b", "none", "none", "none"]
    assert _tiers("lymphoma", "fertility_semen_lymphoma") == ["c", "c", "none", "none"]
    assert protocol.tier_for(_rec("lymphoma", "pet_ct_lymphoma"), None) == "a"  # the strictest while the setting is unrecorded
    essential = {r["id"] for r in protocol.records("lymphoma") if protocol.required(r, "child_nhl", "essential")}
    assert essential == {"clinical_history", "lymph_node_histopathology", "lymphoma_ihc", "bone_marrow_lymphoma", "cbc_lymphoma",
                         "biochemistry_lymphoma", "staging_ct_lymphoma", "chest_xray_lymphoma", "echo_ecg_lymphoma", "csf_lymphoma",
                         "stage_as_recorded_lymphoma"}


def test_leukaemia_tiers_by_setting():
    assert _tiers("leukaemia", "coagulation_leukaemia") == ["a", "none", "a", "none"]
    assert _tiers("leukaemia", "viral_markers_leukaemia") == ["a", "a", "b", "none"]
    assert _tiers("leukaemia", "bone_marrow_leukaemia") == ["a", "b", "a", "a"]
    assert _tiers("leukaemia", "molecular_markers_leukaemia") == ["a", "a", "b", "a"]
    assert _tiers("leukaemia", "hla_typing_leukaemia") == ["b", "c", "b", "none"]
    assert not any(r["id"] == "mrd_leukaemia" for r in protocol.records("leukaemia"))  # after induction: an optional (after-board) record
    assert next(o for o in protocol.get("leukaemia")["optional"] if o["id"] == "mrd_leukaemia")["tiers_in_the_book"] == {"adult_acute": "b", "adult_chronic": "c", "child_acute": "a", "child_chronic": "none"}
    assert _tiers("leukaemia", "cll_special_labs") == ["none", "b", "none", "none"]
    essential = {r["id"] for r in protocol.records("leukaemia") if protocol.required(r, "child_chronic", "essential")}
    assert essential == {"clinical_history", "cbc_smear", "biochemistry_ldh_leukaemia", "bone_marrow_leukaemia", "cytogenetics_fish",
                         "molecular_markers_leukaemia"}


def test_conditional_records_have_system_tier_c_so_they_are_shown_never_counted():
    """A record NCG gives only under a condition the system never judges has system tier c in that setting (rules.py shows NCG's own tier)."""
    expected = {("lymphoma", "bone_marrow_lymphoma"): ("a", {"adult_hodgkin", "child_hodgkin"}),
                ("lymphoma", "csf_lymphoma"): ("a", {"adult_nhl", "child_hodgkin"}),
                ("lymphoma", "flow_cytometry_lymphoma"): ("a", {"adult_nhl"}),
                ("leukaemia", "chest_imaging_leukaemia"): ("a", {"adult_chronic"}),
                ("leukaemia", "testicular_assessment"): ("b", {"child_acute"})}
    found = {}
    for pid in PIDS:
        for r in protocol.records(pid):
            if r.get("condition"):
                found[(pid, r["id"])] = (r["condition"]["ncg_tier"], {s for s in SETTINGS[pid] if protocol.tier_for(r, s) == "c"})
                for s in SETTINGS[pid]:
                    if protocol.tier_for(r, s) == "c":
                        assert not protocol.required(r, s, "optimal"), (pid, r["id"], s)
    assert found == expected
    assert protocol.tier_for(_rec("lymphoma", "bone_marrow_lymphoma"), "child_nhl") == "a"
    assert protocol.tier_for(_rec("lymphoma", "csf_lymphoma"), "child_nhl") == "a"


# --- routing ---------------------------------------------------------------------------------------------------------------------

def test_routes_table_lists_every_record_of_the_two_protocols(data_root):
    rows = [r for r in rules.routes_table() if r["protocol"] in PIDS]
    expected = {(pid, r["id"], kind) for pid in PIDS for kind, recs in (("required", protocol.records(pid)), ("optional", protocol.get(pid)["optional"])) for r in recs}
    assert {(r["protocol"], r["record"], r["kind"]) for r in rows} == expected and len(rows) == len(expected)
    for r in rows:
        assert r["department"] and r["default_department"], r
        assert r["route_kind"] in org.ROUTE_KINDS, r
        if r["route_kind"] == org.COORDINATOR_ID:
            assert r["department_id"] is None and r["department"] == org.COORDINATOR_NAME


@pytest.mark.parametrize("pid,rec,dept", [
    ("lymphoma", "lymph_node_histopathology", "pathology"), ("lymphoma", "lymphoma_ihc", "pathology"), ("lymphoma", "bone_marrow_lymphoma", "pathology"),
    ("lymphoma", "cbc_lymphoma", "pathology"), ("lymphoma", "biochemistry_lymphoma", "biochemistry"), ("lymphoma", "viral_markers_lymphoma", "microbiology"),
    ("lymphoma", "pet_ct_lymphoma", "nuclear_medicine"), ("lymphoma", "staging_ct_lymphoma", "radiology"), ("lymphoma", "pft_lymphoma", "pulmonology"),
    ("lymphoma", "csf_lymphoma", "pathology"), ("lymphoma", "flow_cytometry_lymphoma", "pathology"),
    ("leukaemia", "cbc_smear", "pathology"), ("leukaemia", "coagulation_leukaemia", "pathology"), ("leukaemia", "biochemistry_ldh_leukaemia", "biochemistry"),
    ("leukaemia", "viral_markers_leukaemia", "microbiology"), ("leukaemia", "bone_marrow_leukaemia", "pathology"),
    ("leukaemia", "flow_cytometry_acute", "pathology"), ("leukaemia", "cytogenetics_fish", "pathology"), ("leukaemia", "molecular_markers_leukaemia", "pathology"),
    ("leukaemia", "csf_leukaemia", "pathology"), ("leukaemia", "chest_imaging_leukaemia", "radiology"), ("leukaemia", "cll_special_labs", "biochemistry"),
])
def test_supporting_records_route_to_the_department_that_produces_them(data_root, pid, rec, dept):
    assert rules.routed(protocol.get(pid), _rec(pid, rec))[1] == dept


@pytest.mark.parametrize("pid,rec", [
    ("lymphoma", "clinical_history"), ("lymphoma", "fertility_semen_lymphoma"),
    ("leukaemia", "clinical_history"), ("leukaemia", "hla_typing_leukaemia"),
])
def test_clinical_records_route_to_the_owner(data_root, pid, rec):
    p, r = protocol.get(pid), _rec(pid, rec)
    assert r["route"] == "owner" and r["department"] == "Haematology"
    assert rules.routed(p, r)[1] == "haematology" and rules.routed(p, r)[2] == "owner"
    assert rules.routed(p, r, {"department": "paediatric_oncology"})[1] == "paediatric_oncology"


@pytest.mark.parametrize("pid,rec", [("lymphoma", "echo_ecg_lymphoma"), ("leukaemia", "echo_leukaemia")])
def test_echocardiogram_goes_to_the_owning_team(pid, rec):
    r = _rec(pid, rec)
    assert r["department"] == "Cardiology" and r["route"] == "owner" and r["doc_types"] == ["echocardiogram"]
    assert org.is_owner_alias("Cardiology")


# --- regions and quotes -----------------------------------------------------------------------------------------------------------

def test_regions_are_valid_lowercase_regexes():
    for pid in PIDS:
        for r in protocol.records(pid):
            if r.get("region"):
                assert r["region"] == r["region"].lower() and re.compile(r["region"]), (pid, r["id"])


def test_lab_records_tell_their_reports_apart_by_region():
    """Several lab records share the document type "lab": each names the words of its own report (as breast's CBC and LFT records)."""
    for pid in PIDS:
        labs = [r for r in protocol.records(pid) if r["doc_types"] == ["lab"]]
        assert labs and all(r.get("region") for r in labs), (pid, [r["id"] for r in labs if not r.get("region")])
    assert re.search(r"\b(?:" + _rec("leukaemia", "coagulation_leukaemia")["region"] + ")", "coagulation profile pt aptt")
    assert not re.search(r"\b(?:" + _rec("leukaemia", "cll_special_labs")["region"] + ")", "report date 01/11/2026 cbc")


def test_quotes_are_present_and_unique_per_record():
    for pid in PIDS:
        for r in protocol.records(pid):
            quotes = [s["quote"] for s in r["sources"]]
            assert quotes and len(quotes) == len(set(quotes)), (pid, r["id"])


def test_source_files_exist_in_the_guideline_library():
    root = Path("/data/vaidyx/tb_resources/guidelines")
    if not root.exists():
        pytest.skip("guideline library not on this machine")
    for f in (ADULT, CHILD):
        assert (root / f).is_file(), f
