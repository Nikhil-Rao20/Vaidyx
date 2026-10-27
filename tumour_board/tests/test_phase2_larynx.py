"""Phase 2 checklist, item 2.6 (night-v3): larynx (NCG Guidelines for Head and Neck Cancer, 2019).

Draft checklist transcribed from the NCG head and neck book, labelled "needs a clinician's check" (owner decision D6). The quote-on-page check is
the shared test of item 2.1 (test_protocol_schema.py); the structure checks here copy test_tiers.py."""
import json
import re
from pathlib import Path

import pytest

from tumour_board import config, org, protocol, rules

PIDS = ("larynx",)
NCG_FILE = "ncg_india/ncg-guidelines-for-head-neck-cancer-2019.pdf"
NCG_NAME = "NCG Guidelines for Head and Neck Cancer (2019)"
SETTINGS = {"larynx": ["early", "locally_advanced", "metastatic"]}
COUNTS = {"larynx": 11}
OPTIONAL = {"larynx": ["surgical_pathology", "previous_board"]}
ENT = "ENT / Head and Neck Surgery"
ALLOWED_BOOKS = {"larynx": {(NCG_NAME, NCG_FILE)}}


def _raw(pid):
    return json.loads((config.PROTOCOL_DIR / f"{pid}.json").read_text())


def _rec(pid, rid):
    return next(r for r in protocol.records(pid) if r["id"] == rid)


def _opt(pid, rid):
    return next(r for r in protocol.get(pid)["optional"] if r["id"] == rid)


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
    ids = [r["id"] for r in p["records"]] + [r["id"] for r in p["optional"]]
    assert len(ids) == len(set(ids))
    for r in p["records"]:
        assert r["tier"] in protocol.TIERS, r["id"]
        for s, t in (r.get("tiers") or {}).items():
            assert s in setting_ids and t in (*protocol.TIERS, "none"), (r["id"], s, t)
        if r.get("tiers"):  # one entry per setting, and the record's tier is the strictest of them
            assert set(r["tiers"]) == setting_ids, r["id"]
            assert r["tier"] == max(r["tiers"].values(), key=lambda t: protocol.STRICTNESS[t]), r["id"]
        raw_rec = next(x for x in raw["records"] if x["id"] == r["id"])
        assert raw_rec.get("source") or raw_rec.get("sources"), r["id"]
        assert r["source"] == r["sources"][0]
        for src in r["sources"]:
            assert src["quote"].strip(), r["id"]
            assert (src["guideline"], src["file"]) in ALLOWED_BOOKS[pid], (r["id"], src["guideline"], src["file"])
            assert src["guideline"].startswith("NCG"), r["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), r["id"]
        assert all(f in cat for f in r.get("required_facts", [])), r["id"]
        assert set(r.get("doc_types", [])) <= doc_types and set(r.get("fact_doc_types", [])) <= doc_types, r["id"]
        assert r.get("doc_types") or (r.get("facts_only") and r.get("fact_doc_types")), r["id"]
        assert org.department_id(r["department"]) or org.is_owner_alias(r["department"]), (r["id"], r["department"])
        assert isinstance(r.get("sla_days"), int) and r["sla_days"] > 0, r["id"]
        assert r.get("tier_basis"), r["id"]
        for k in ("tier_basis", "note"):
            assert "—" not in r.get(k, ""), r["id"]
        if r.get("condition"):  # NCG's own tier under a condition the system never judges: the record itself is shown only
            assert r["condition"]["ncg_tier"] in protocol.TIERS and r["condition"]["text"] and "—" not in r["condition"]["text"], r["id"]
            assert "c" in {r["tier"], *(r.get("tiers") or {}).values()}, r["id"]
    for o in p["optional"]:  # optional records: a department that resolves, and a source (if any) in the same form
        assert o["doc_types"] and set(o["doc_types"]) <= doc_types, o["id"]
        assert org.department_id(o["department"]) or org.is_owner_alias(o["department"]) or org.is_coordinator_name(o["department"]), o["id"]
        for src in o.get("sources") or []:
            assert (src["guideline"], src["file"]) in ALLOWED_BOOKS[pid] and isinstance(src["page"], int), o["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_protocol_loads_and_is_listed_with_its_settings(pid):
    assert protocol.exists(pid)
    p = protocol.get(pid)
    assert p["id"] == pid and p["label"] and p["site"]
    assert [s["id"] for s in p["settings"]] == SETTINGS[pid]
    assert all(s["label"].endswith("as recorded") for s in p["settings"])
    listed = {x["id"]: x for x in protocol.list_protocols()}
    assert pid in listed and [s["id"] for s in listed[pid]["settings"]] == SETTINGS[pid]
    assert listed[pid]["label"] == p["label"] and listed[pid]["version"] == "0.1-draft"
    assert len(p["records"]) == COUNTS[pid]
    assert p["records"] is p["mandatory"]
    assert [o["id"] for o in p["optional"]] == OPTIONAL[pid]
    assert protocol.settings(pid) == p["settings"]
    assert protocol.setting_label(pid, SETTINGS[pid][0]) == p["settings"][0]["label"]


def test_the_labels_and_site_words():
    assert protocol.get("larynx")["label"] == "Cancer of the larynx (head and neck)"
    assert protocol.get("larynx")["site"] == "larynx|laryng|glott|vocal cord|supraglott|subglott|hypopharyn"
    breast_site_note = json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["site_note"]
    assert all(protocol.get(pid)["site_note"] == breast_site_note for pid in PIDS)
    assert [s["label"] for s in protocol.get("larynx")["settings"]] == [
        "Early (T1 to T2, N0), as recorded", "Locally advanced (T1 to T2 with nodes, T3, T4, or inoperable neck nodes), as recorded", "Metastatic or recurrent, as recorded"]


@pytest.mark.parametrize("pid", PIDS)
def test_every_record_has_tier_source_and_valid_fields(pid):
    _check_structure(pid)


@pytest.mark.parametrize("pid", PIDS)
def test_draft_status_and_provenance(pid):
    p = protocol.get(pid)
    assert p["version"] == "0.1-draft"
    assert p["approval"]["status"] == "draft"
    assert "needs a clinician's check" in p["approval"]["note"] and "needs a clinician's check" in p["note"]
    assert "hospital Tumour Board" in p["note"] and p["settings_note"]
    assert {(g["guideline"], g["file"]) for g in p["guideline_sources"]} == ALLOWED_BOOKS[pid]
    assert all(g["pages"] for g in p["guideline_sources"])
    cited = {(s["guideline"], s["file"]) for r in p["records"] for s in r["sources"]}
    assert cited == ALLOWED_BOOKS[pid]
    for key in ("extract_facts", "core_data", "core_data_source", "post_board", "policy_basis"):
        assert p[key], key
    assert p["post_board"] == json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["post_board"]
    assert list(p)[:5] == ["id", "label", "version", "approval", "site"]


def test_larynx_note_names_the_book_and_the_hpv_exclusion():
    assert "National Cancer Grid" in protocol.get("larynx")["note"] and "HPV" in protocol.get("larynx")["note"]


@pytest.mark.parametrize("pid", PIDS)
def test_scope_words_stay_out_of_the_file(pid):
    """No licensed US guideline network, no stage computation, no accuracy claim."""
    text = (config.PROTOCOL_DIR / f"{pid}.json").read_text().lower()
    assert "nccn" not in text and "national comprehensive" not in text
    assert "accuracy" not in text and "validated" not in text
    assert "computes the stage" not in text


@pytest.mark.parametrize("pid", PIDS)
def test_no_em_or_en_dash_apart_from_inside_quotes(pid):
    text = json.dumps(_strip_quotes(_raw(pid)), ensure_ascii=False)
    assert "—" not in text and "–" not in text


@pytest.mark.parametrize("pid", PIDS)
def test_required_facts_can_come_from_the_record_document_types(pid):
    """A required value no document of the record's types can carry would be a gap that never closes (facts.json lists where each fact is read)."""
    cat = protocol.facts()
    for r in protocol.records(pid):
        allowed = set(r.get("fact_doc_types") or r.get("doc_types"))
        for f in r["required_facts"]:
            assert allowed & set(cat[f]["doc_types"]) or "other" in allowed, (pid, r["id"], f)


@pytest.mark.parametrize("pid", PIDS)
def test_extract_facts_cover_every_required_fact_and_the_general_ones(pid):
    p = protocol.get(pid)
    cat = protocol.facts()
    ef = p["extract_facts"]
    assert len(ef) == len(set(ef)) and all(f in cat for f in ef)
    for r in p["records"]:
        assert set(r["required_facts"]) <= set(ef), r["id"]
    general = {"presenting_complaint", "ecog", "comorbidities", "clinical_question", "recorded_stage", "lesion_size", "nodal_findings", "distant_findings",
               "histologic_type", "grade", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "patient_preference", "clinical_trial_note",
               "diagnosis_date_mode", "treatment_received"}
    assert general <= set(ef)
    for c in p["core_data"]:
        assert c["facts"] and all(f in cat for f in c["facts"]) and set(c["facts"]) <= set(ef), c["id"]
    assert {"laryngeal_subsite", "cord_mobility", "laryngeal_function", "tobacco_use", "smoking_history", "dental_evaluation"} <= set(ef)


@pytest.mark.parametrize("pid", PIDS)
def test_previous_board_is_an_optional_coordinator_record(pid):
    pb = _opt(pid, "previous_board")
    assert pb["department"] == "MDT Coordinator" and pb["route"] == "coordinator" and pb["doc_types"] == ["tumour_board_record"]
    assert rules.routed(protocol.get(pid), pb) == (org.COORDINATOR_NAME, None, "coordinator")


@pytest.mark.parametrize("pid", PIDS)
def test_clinical_history_routes_to_the_owner(pid):
    p = protocol.get(pid)
    ch = _rec(pid, "clinical_history")
    assert ch["route"] == "owner" and ch["department"] == ENT and ch["doc_types"] == ["clinical_note", "referral"]
    name, did, kind = rules.routed(p, ch)
    assert kind == "owner" and did == org.department_id(ENT) and org.department_group(did) == "treating"
    name, did, kind = rules.routed(p, ch, {"department": "medical_oncology"})
    assert (name, did, kind) == ("Medical Oncology", "medical_oncology", "owner")


# --- larynx ------------------------------------------------------------------------------------------------------------------------

def test_larynx_tiers_by_setting():
    L = SETTINGS["larynx"]
    lar = _rec("larynx", "laryngoscopy")
    assert [protocol.tier_for(lar, s) for s in L] == ["a", "a", "none"] and protocol.tier_for(lar, None) == "a"
    sw = _rec("larynx", "speech_swallowing")
    assert [protocol.tier_for(sw, s) for s in L] == ["b", "b", "none"] and protocol.tier_for(sw, None) == "b"
    pf = _rec("larynx", "performance_cisplatin_fitness")
    assert [protocol.tier_for(pf, s) for s in L] == ["none", "a", "a"] and pf["department"] == "Medical Oncology" and "route" not in pf
    ct = _rec("larynx", "cect_thorax_pet")  # NCG: CECT thorax (b) and PET-CT (c) only for high risk of distant metastasis: shown, never counted
    assert [protocol.tier_for(ct, s) for s in L] == ["none", "c", "c"] and ct["condition"]["ncg_tier"] == "b"
    assert not any(protocol.required(ct, s, "optimal") for s in L)
    for rid, t in (("imaging_primary_neck", "b"), ("clinical_history", "a"), ("histopathology", "a"), ("chest_xray", "a")):
        r = _rec("larynx", rid)
        assert "tiers" not in r and all(protocol.tier_for(r, s) == t for s in (*L, None)), rid


def test_larynx_essential_records_by_setting():
    req = lambda s, level="essential": {r["id"] for r in protocol.records("larynx") if protocol.required(r, s, level)}
    early = {"clinical_history", "laryngoscopy", "laryngeal_function", "histopathology", "chest_xray", "dental_evaluation", "nutrition_assessment"}
    assert req("early") == early
    assert req("locally_advanced") == early | {"performance_cisplatin_fitness"}
    assert req("metastatic") == {"clinical_history", "histopathology", "chest_xray", "performance_cisplatin_fitness"}
    assert req("early", "optimal") == early | {"imaging_primary_neck", "speech_swallowing"}
    assert req(None) == early | {"performance_cisplatin_fitness"}  # not recorded: the strictest tier of each record


def test_larynx_records_follow_the_oral_cavity_head_and_neck_structure():
    ids = [r["id"] for r in protocol.records("larynx")]
    assert ids == ["clinical_history", "laryngoscopy", "laryngeal_function", "histopathology", "imaging_primary_neck", "chest_xray", "cect_thorax_pet",
                   "dental_evaluation", "nutrition_assessment", "speech_swallowing", "performance_cisplatin_fitness"]
    d = _rec("larynx", "dental_evaluation")  # copied from oral_cavity.json, as an owner alias with route owner
    oc = _rec("oral_cavity", "dental_evaluation")
    assert d["department"] == "Dental surgery" and org.is_owner_alias("Dental surgery") and d["route"] == "owner"
    assert d["region"] == oc["region"] and d["doc_types"] == oc["doc_types"] and d["required_facts"] == oc["required_facts"] == ["dental_evaluation"]
    assert all(s["guideline"] == "NCG Guidelines for Head and Neck Cancer (2019)" for r in protocol.records("larynx") for s in r["sources"])
    assert "hpv" not in " ".join(r["id"] for r in protocol.records("larynx"))  # HPV / p16 testing is for the oropharynx only
    assert _rec("larynx", "chest_xray")["sources"][0]["page"] == 11 and _rec("larynx", "histopathology")["sources"][0]["page"] == 56


def test_larynx_laryngeal_facts_and_departments():
    assert _rec("larynx", "laryngoscopy")["required_facts"] == ["cord_mobility", "laryngeal_function"]
    assert _rec("larynx", "laryngeal_function")["required_facts"] == ["laryngeal_function"]
    assert _rec("larynx", "clinical_history")["required_facts"] == ["ecog", "tobacco_use", "smoking_history", "comorbidities", "presenting_complaint", "clinical_question"]
    for rid, dept in (("laryngoscopy", ENT), ("laryngeal_function", ENT), ("histopathology", "Pathology"), ("imaging_primary_neck", "Radiology"),
                      ("chest_xray", "Radiology"), ("cect_thorax_pet", "Radiology"), ("nutrition_assessment", ENT), ("speech_swallowing", ENT)):
        assert _rec("larynx", rid)["department"] == dept, rid
    for rid in ("nutrition_assessment", "speech_swallowing"):
        assert _rec("larynx", rid)["route"] == "owner" and _rec("larynx", rid)["region"] and _rec("larynx", rid)["required_facts"] == []
    assert "route" not in _rec("larynx", "laryngoscopy")
    sp = _opt("larynx", "surgical_pathology")  # a post-board record: optional, never counted
    assert sp["doc_types"] == ["histopathology"] and sp["department"] == "Pathology" and sp["sources"][0]["page"] == 56


# --- routing ---------------------------------------------------------------------------------------------------------------------

def test_routes_table_lists_every_record_of_the_protocol(data_root):
    rows = [r for r in rules.routes_table() if r["protocol"] in PIDS]
    expected = {(pid, r["id"], kind) for pid in PIDS for kind, recs in (("required", protocol.records(pid)), ("optional", protocol.get(pid)["optional"])) for r in recs}
    assert {(r["protocol"], r["record"], r["kind"]) for r in rows} == expected and len(rows) == len(expected)
    for r in rows:
        assert r["department"] and r["default_department"], r
        assert r["route_kind"] in org.ROUTE_KINDS, r
        if r["route_kind"] == org.COORDINATOR_ID:
            assert r["department_id"] is None and r["department"] == org.COORDINATOR_NAME
        elif r["route_kind"] == org.OWNER_ID and r["department_id"] is None:  # an owner alias: the owning team's own work
            assert org.is_owner_alias(r["default_department"]), r
        else:
            assert r["department_id"] and org.department(r["department_id"]), r


@pytest.mark.parametrize("pid,rec,dept", [
    ("larynx", "laryngoscopy", "ent_head_neck_surgery"), ("larynx", "histopathology", "pathology"), ("larynx", "imaging_primary_neck", "radiology"),
    ("larynx", "chest_xray", "radiology"), ("larynx", "performance_cisplatin_fitness", "medical_oncology"), ("larynx", "laryngeal_function", "ent_head_neck_surgery"),
])
def test_supporting_records_route_to_the_department_that_produces_them(data_root, pid, rec, dept):
    p = protocol.get(pid)
    assert rules.routed(p, _rec(pid, rec))[1] == dept


@pytest.mark.parametrize("rid", ["dental_evaluation", "nutrition_assessment", "speech_swallowing"])
def test_larynx_owner_records_route_to_the_owner(data_root, rid):
    p, r = protocol.get("larynx"), _rec("larynx", rid)
    assert r["route"] == "owner"
    name, did, kind = rules.routed(p, r)
    assert kind == "owner"
    if org.is_owner_alias(r["department"]):  # a dental evaluation is the owning team's own work (18 Oct)
        assert did is None and name == org.OWNER_NAME
    else:
        assert did == org.department_id(ENT)
    assert rules.routed(p, r, {"department": "surgical_oncology"})[1] in (None, "surgical_oncology")


def test_owner_aliases_used_by_this_group_resolve():
    """Only the larynx dental evaluation uses an owner alias (Dental surgery, added in item 2.1); every other department is a real one."""
    for r in protocol.records("larynx"):
        assert org.department_id(r["department"]) or (r["id"] == "dental_evaluation" and org.is_owner_alias(r["department"])), r["id"]


# --- conditions and regions -------------------------------------------------------------------------------------------------------

def test_conditional_records_have_system_tier_c_so_they_are_shown_never_counted():
    for pid in PIDS:
        for r in protocol.records(pid):
            if r.get("condition"):
                assert "c" in {protocol.tier_for(r, s) for s in SETTINGS[pid]}, (pid, r["id"])
                for s in SETTINGS[pid]:
                    if protocol.tier_for(r, s) == "c":
                        assert not protocol.required(r, s, "optimal"), (pid, r["id"], s)


def test_regions_are_valid_lowercase_regexes():
    for pid in PIDS:
        for r in protocol.records(pid):
            if r.get("region"):
                assert r["region"] == r["region"].lower() and re.compile(r["region"]), (pid, r["id"])


def test_quotes_are_present_and_unique_per_record():
    for pid in PIDS:
        for r in protocol.records(pid):
            quotes = [s["quote"] for s in r["sources"]]
            assert quotes and len(quotes) == len(set(quotes)), (pid, r["id"])


def test_source_files_exist_in_the_guideline_library():
    root = Path("/data/vaidyx/tb_resources/guidelines")
    if not root.exists():
        pytest.skip("guideline library not on this machine")
    assert (root / NCG_FILE).is_file(), NCG_FILE
