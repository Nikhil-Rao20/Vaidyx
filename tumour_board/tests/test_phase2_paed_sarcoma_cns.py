"""Phase 2 checklists, item 2.8 (night-v3): wilms, retinoblastoma, bone_sarcoma, soft_tissue_sarcoma and brain_cns.

Draft checklists transcribed from the NCG Paediatric and the NCG Bone and Soft Tissue books (2019), and, for the adult brain records (NCG has no CNS file),
from the open-access EANO guideline on diffuse gliomas of adulthood (CC BY 4.0), labelled "needs a clinician's check" (owner decision D6). The
quote-on-page check is the shared test of item 2.1; the structure checks here copy test_tiers.py."""
import json

import pytest

from tumour_board import config, org, protocol, rules

PIDS = ("wilms", "retinoblastoma", "bone_sarcoma", "soft_tissue_sarcoma", "brain_cns")
PED = "ncg_india/ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf"
BONE = "ncg_india/ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf"
EANO = "eano/EANO_2021_diffuse_gliomas_Weller.pdf"
BOOKS = {"wilms": {PED}, "retinoblastoma": {PED}, "bone_sarcoma": {BONE}, "soft_tissue_sarcoma": {BONE, PED}, "brain_cns": {EANO}}
SETTINGS = {
    "wilms": ["unilateral", "bilateral"],
    "retinoblastoma": ["unilateral", "bilateral"],
    "bone_sarcoma": ["osteosarcoma", "ewing", "chondrosarcoma"],
    "soft_tissue_sarcoma": ["non_metastatic", "metastatic", "paediatric_rhabdomyosarcoma"],
    "brain_cns": ["adult_glioma", "adult_other", "child"],
}
COUNTS = {"wilms": 7, "retinoblastoma": 9, "bone_sarcoma": 15, "soft_tissue_sarcoma": 13, "brain_cns": 10}
OPTIONAL = {"wilms": ["nephrectomy_histopathology", "previous_board"], "retinoblastoma": ["previous_board"], "bone_sarcoma": ["resection_histopathology_bone", "previous_board"],
            "soft_tissue_sarcoma": ["previous_board"], "brain_cns": ["previous_board"]}
LABELS = {"wilms": "Wilms tumour (child)", "retinoblastoma": "Retinoblastoma (child)", "bone_sarcoma": "Bone sarcoma (osteosarcoma, Ewing sarcoma, chondrosarcoma)",
          "soft_tissue_sarcoma": "Soft tissue sarcoma", "brain_cns": "Brain and CNS tumours"}
SITES = {"wilms": "wilms|nephroblastoma|kidney|renal", "retinoblastoma": "retinoblastoma|eye|orbit|retina|globe",
         "bone_sarcoma": "osteosarcoma|ewing|bone|femur|tibia|humerus|pelvis bone", "soft_tissue_sarcoma": "sarcoma|soft tissue|rhabdomyosarcoma|thigh|extremity",
         "brain_cns": "brain|cerebr|glioma|astrocytoma|oligodendroglioma|glioblastoma|medulloblastoma|spinal cord|cranial"}
OWNER_DEPT = {"wilms": "Paediatric Oncology", "retinoblastoma": "Paediatric Oncology", "bone_sarcoma": "Orthopaedic Oncology",
              "soft_tissue_sarcoma": "Orthopaedic Oncology", "brain_cns": "Neurosurgery"}


def _raw(pid):
    return json.loads((config.PROTOCOL_DIR / f"{pid}.json").read_text())


def _rec(pid, rid):
    return next(r for r in protocol.records(pid) if r["id"] == rid)


def _strip_quotes(obj):
    """The file's text without the verbatim book quotes (a quote may hold a dash the book prints)."""
    if isinstance(obj, dict):
        return {k: _strip_quotes(v) for k, v in obj.items() if k != "quote"}
    if isinstance(obj, list):
        return [_strip_quotes(x) for x in obj]
    return obj


def _all_records(p):
    return list(p["records"]) + list(p.get("optional") or [])


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
        for s, t in (r.get("tiers") or {}).items():
            assert s in setting_ids and t in (*protocol.TIERS, "none"), (r["id"], s, t)
        if r.get("tiers"):  # one entry per setting, and the record's tier is the strictest of them
            assert set(r["tiers"]) == setting_ids, r["id"]
            assert r["tier"] == max(r["tiers"].values(), key=lambda t: protocol.STRICTNESS[t]), r["id"]
        raw_rec = next(x for x in raw["records"] if x["id"] == r["id"])
        assert raw_rec.get("source") or raw_rec.get("sources"), r["id"]
        assert r["source"] == r["sources"][0]
        for src in r["sources"]:
            assert src["guideline"].startswith("EANO" if pid == "brain_cns" else "NCG") and src["quote"].strip(), r["id"]
            assert src["file"] in BOOKS[pid], r["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), r["id"]
        assert all(f in cat for f in r.get("required_facts", [])), r["id"]
        assert set(r.get("doc_types", [])) <= doc_types and set(r.get("fact_doc_types", [])) <= doc_types, r["id"]
        assert r.get("doc_types") or (r.get("facts_only") and r.get("fact_doc_types")), r["id"]
        assert org.department_id(r["department"]) or org.is_owner_alias(r["department"]), (r["id"], r["department"])
        assert isinstance(r.get("sla_days"), int) and r["sla_days"] > 0, r["id"]
        assert r.get("tier_basis"), r["id"]
        for k in ("tier_basis", "note"):
            assert "—" not in r.get(k, ""), r["id"]
        if r.get("condition"):  # the guideline's own tier under a condition the system never judges: the record itself is shown only
            assert r["condition"]["ncg_tier"] in protocol.TIERS and r["condition"]["text"] and "—" not in r["condition"]["text"], r["id"]
            assert "c" in {r["tier"], *(r.get("tiers") or {}).values()}, r["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_protocol_loads_and_is_listed_with_its_settings(pid):
    assert protocol.exists(pid)
    p = protocol.get(pid)
    assert p["id"] == pid and p["label"] == LABELS[pid] and p["site"] == SITES[pid]
    assert [s["id"] for s in p["settings"]] == SETTINGS[pid]
    assert all(s["label"].endswith(("as recorded", "(as recorded)")) for s in p["settings"])
    listed = {x["id"]: x for x in protocol.list_protocols()}
    assert pid in listed and [s["id"] for s in listed[pid]["settings"]] == SETTINGS[pid]
    assert listed[pid]["label"] == p["label"] and listed[pid]["version"] == "0.1-draft"
    assert len(p["records"]) == COUNTS[pid]
    assert [r["id"] for r in p["optional"]] == OPTIONAL[pid]
    assert p["records"] is p["mandatory"]
    assert protocol.settings(pid) == p["settings"]
    assert protocol.setting_label(pid, SETTINGS[pid][0]) == p["settings"][0]["label"]


def test_site_note_is_breasts_and_the_ids_are_the_file_names():
    breast_site_note = json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["site_note"]
    assert all(protocol.get(pid)["site_note"] == breast_site_note for pid in PIDS)
    assert all(protocol.get(pid)["id"] == pid for pid in PIDS)


@pytest.mark.parametrize("pid", PIDS)
def test_every_record_has_tier_source_and_valid_fields(pid):
    _check_structure(pid)


@pytest.mark.parametrize("pid", PIDS)
def test_draft_status_and_provenance(pid):
    p = protocol.get(pid)
    assert p["version"] == "0.1-draft"
    assert p["approval"]["status"] == "draft"
    assert "needs a clinician's check" in p["approval"]["note"] and "needs a clinician's check" in p["note"]
    assert "hospital Tumour Board" in p["note"]
    assert p["settings_note"] and "needs a clinician's check" in p["settings_note"]
    assert {g["file"] for g in p["guideline_sources"]} == BOOKS[pid]
    assert all(g["guideline"] and g["pages"] for g in p["guideline_sources"])
    cited = {s["file"] for r in _all_records(p) for s in (r.get("sources") or [])}
    assert cited == BOOKS[pid]
    for key in ("extract_facts", "core_data", "core_data_source", "post_board", "policy_basis"):
        assert p[key], key
    assert p["post_board"] == json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["post_board"]
    assert "National Cancer Grid" in p["note"]


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
        assert c["facts"] and all(f in cat for f in c["facts"]), c["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_previous_board_is_an_optional_coordinator_record(pid):
    pb = next(x for x in protocol.get(pid)["optional"] if x["id"] == "previous_board")
    assert pb["department"] == "MDT Coordinator" and pb["route"] == "coordinator" and pb["doc_types"] == ["tumour_board_record"]
    assert rules.routed(protocol.get(pid), pb) == (org.COORDINATOR_NAME, None, "coordinator")


@pytest.mark.parametrize("pid", PIDS)
def test_clinical_history_routes_to_the_owner(pid):
    p = protocol.get(pid)
    ch = _rec(pid, "clinical_history")
    assert ch["route"] == "owner" and ch["department"] == OWNER_DEPT[pid] and ch["doc_types"] == ["clinical_note", "referral"]
    assert ch["tier"] == "a" and "tiers" not in ch
    name, did, kind = rules.routed(p, ch)
    assert kind == "owner" and did == org.department_id(OWNER_DEPT[pid]) and org.department_group(did) == "treating"
    name, did, kind = rules.routed(p, ch, {"department": "paediatric_oncology"})
    assert (name, did, kind) == ("Paediatric Oncology", "paediatric_oncology", "owner")


@pytest.mark.parametrize("pid", PIDS)
def test_every_draft_record_says_how_its_tier_was_chosen(pid):
    """A tier the book does not print is a proposal and says so; a printed one quotes its letter or its level."""
    for r in _all_records(protocol.get(pid)):
        if r["id"] == "previous_board":
            continue
        assert r.get("sources") and r.get("tier_basis"), r["id"]


# --- tiers that differ by setting -------------------------------------------------------------------------------------------------

def test_wilms_tiers_by_setting():
    mri = _rec("wilms", "mri_bilateral_wilms")
    assert [protocol.tier_for(mri, s) for s in SETTINGS["wilms"]] == ["none", "b"] and protocol.tier_for(mri, None) == "b"
    bx = _rec("wilms", "biopsy_wilms")
    assert [protocol.tier_for(bx, s) for s in SETTINGS["wilms"]] == ["c", "none"] and bx["condition"]["ncg_tier"] == "b"
    assert not protocol.required(bx, "unilateral", "optimal")
    assert protocol.tier_for(_rec("wilms", "usg_doppler_wilms"), "unilateral") == "b"
    assert protocol.tier_for(_rec("wilms", "loh_1p_16q"), "bilateral") == "c"
    essential = {r["id"] for r in protocol.records("wilms") if protocol.required(r, "unilateral", "essential")}
    assert essential == {"clinical_history", "usg_abdomen_wilms", "ct_thorax_abdomen_pelvis_wilms"}  # the nephrectomy histopathology is an optional (after-surgery) record
    nephrectomy = next(o for o in protocol.get("wilms")["optional"] if o["id"] == "nephrectomy_histopathology")
    assert "anaplasia" in nephrectomy["required_facts"] and nephrectomy["tiers_in_the_book"] == "a"


def test_retinoblastoma_tiers_and_the_eye_examination_routes_to_the_owner():
    bm = _rec("retinoblastoma", "bone_marrow_csf_rb")
    assert {protocol.tier_for(bm, s) for s in SETTINGS["retinoblastoma"]} == {"c"} and bm["condition"]["ncg_tier"] == "a"
    assert protocol.tier_for(_rec("retinoblastoma", "germline_ngs"), "bilateral") == "b"
    assert protocol.tier_for(_rec("retinoblastoma", "ct_orbit_rb"), "unilateral") == "c"
    eye = _rec("retinoblastoma", "eye_exam_eua")
    assert eye["doc_types"] == ["ophthalmology_note"] and eye["department"] == "Ophthalmology" and eye["route"] == "owner"
    assert org.is_owner_alias("Ophthalmology")
    assert eye["required_facts"] == ["ophthalmic_examination", "rb_group"]
    name, did, kind = rules.routed(protocol.get("retinoblastoma"), eye)
    assert (did, kind) == (None, "owner")
    essential = {r["id"] for r in protocol.records("retinoblastoma") if protocol.required(r, "bilateral", "essential")}
    assert essential == {"clinical_history", "eye_exam_eua", "b_scan_ultrasound", "mri_orbit_brain", "genetic_counselling_rb"}


def test_bone_sarcoma_tiers_by_setting():
    s = SETTINGS["bone_sarcoma"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "alp_ldh_bone"), x) for x in s] == ["a", "a", "none"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "ihc_bone"), x) for x in s] == ["c", "a", "none"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "molecular_ewing"), x) for x in s] == ["none", "c", "none"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "bone_scan_bone"), x) for x in s] == ["a", "a", "c"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "pet_ct_bone"), x) for x in s] == ["c", "a", "none"]
    assert [protocol.tier_for(_rec("bone_sarcoma", "bone_marrow_ewing"), x) for x in s] == ["none", "a", "none"]
    assert protocol.tier_for(_rec("bone_sarcoma", "bone_marrow_ewing"), None) == "a"  # the strictest while the setting is unrecorded
    assert _rec("bone_sarcoma", "mri_local_bone")["tier"] == "a" and "tiers" not in _rec("bone_sarcoma", "mri_local_bone")
    chondro = {r["id"] for r in protocol.records("bone_sarcoma") if protocol.required(r, "chondrosarcoma", "essential")}
    assert chondro == {"clinical_history", "radiographs_bone", "routine_blood_bone", "mri_local_bone", "biopsy_bone", "ct_chest_bone"}


def test_bone_sarcoma_baseline_organ_tests_are_split_by_the_team_that_does_them():
    ids = [r["id"] for r in protocol.records("bone_sarcoma")]
    assert "baseline_organ_function_bone" not in ids
    labs, echo, aud = (_rec("bone_sarcoma", i) for i in ("baseline_labs_bone", "echocardiogram_bone", "audiometry_bone"))
    assert labs["doc_types"] == ["lab"] and labs["department"] == "Biochemistry"
    assert echo["doc_types"] == ["echocardiogram"] and echo["department"] == "Cardiology" and echo["route"] == "owner" and org.is_owner_alias("Cardiology")
    assert aud["doc_types"] == ["audiometry"] and aud["department"] == "ENT / Head and Neck Surgery" and "route" not in aud
    assert labs["sources"] == echo["sources"] == aud["sources"] and len(labs["sources"]) == 1
    assert [protocol.tier_for(x, s) for x in (labs, echo, aud) for s in SETTINGS["bone_sarcoma"]] == ["a", "a", "none"] * 3
    assert rules.routed(protocol.get("bone_sarcoma"), aud)[1] == "ent_head_neck_surgery"


def test_bone_sarcoma_post_chemotherapy_resection_is_optional_and_not_counted():
    opt = next(x for x in protocol.get("bone_sarcoma")["optional"] if x["id"] == "resection_histopathology_bone")
    assert opt["doc_types"] == ["histopathology"] and opt["department"] == "Pathology" and opt["sources"][0]["page"] == 39
    assert "percent_necrosis" in protocol.get("bone_sarcoma")["extract_facts"]


def test_soft_tissue_sarcoma_tiers_and_both_books_are_cited_for_rhabdomyosarcoma():
    s = SETTINGS["soft_tissue_sarcoma"]
    assert [protocol.tier_for(_rec("soft_tissue_sarcoma", "bone_scan_marrow_rms"), x) for x in s] == ["none", "none", "a"]
    assert [protocol.tier_for(_rec("soft_tissue_sarcoma", "molecular_sts"), x) for x in s] == ["c", "c", "b"]
    assert [protocol.tier_for(_rec("soft_tissue_sarcoma", "pet_ct_sts"), x) for x in s] == ["c", "c", "b"]
    assert [protocol.tier_for(_rec("soft_tissue_sarcoma", "basic_imaging_sts"), x) for x in s] == ["a", "a", "none"]
    hs = _rec("soft_tissue_sarcoma", "histology_specific_imaging_sts")
    assert [protocol.tier_for(hs, x) for x in s] == ["c", "c", "none"] and hs["condition"]["ncg_tier"] == "a"
    assert protocol.tier_for(_rec("soft_tissue_sarcoma", "prior_excision_sts"), "paediatric_rhabdomyosarcoma") == "none"
    for rid in ("mri_contrast_sts", "biopsy_sts", "molecular_sts", "ct_chest_sts", "pet_ct_sts"):
        assert {x["file"] for x in _rec("soft_tissue_sarcoma", rid)["sources"]} == {BONE, PED}, rid
    assert {x["file"] for x in _rec("soft_tissue_sarcoma", "bone_scan_marrow_rms")["sources"]} == {PED}
    assert [x["page"] for x in _rec("soft_tissue_sarcoma", "bone_scan_marrow_rms")["sources"]] == [59]
    essential = {r["id"] for r in protocol.records("soft_tissue_sarcoma") if protocol.required(r, "paediatric_rhabdomyosarcoma", "essential")}
    assert essential == {"clinical_history", "routine_blood_sts", "mri_contrast_sts", "biopsy_sts", "histopathology_report_sts", "ct_chest_sts", "bone_scan_marrow_rms"}
    assert "tumour_depth" in _rec("soft_tissue_sarcoma", "histopathology_report_sts")["required_facts"]


def test_brain_cns_tiers_by_setting_and_the_mapping_of_the_guidelines_levels():
    s = SETTINGS["brain_cns"]
    assert [protocol.tier_for(_rec("brain_cns", "ihc_idh_atrx"), x) for x in s] == ["a", "none", "c"]
    for rid in ("idh_sequencing", "codeletion_1p19q", "mgmt_promoter"):  # level B, a only in a subgroup the system never judges
        r = _rec("brain_cns", rid)
        assert [protocol.tier_for(r, x) for x in s] == ["c", "none", "none"] and r["condition"]["ncg_tier"] == "a", rid
        assert not protocol.required(r, "adult_glioma", "optimal"), rid
    assert [protocol.tier_for(_rec("brain_cns", "other_glioma_markers"), x) for x in s] == ["c", "none", "c"]
    assert [protocol.tier_for(_rec("brain_cns", "post_op_mri_brain"), x) for x in s] == ["b", "none", "b"]
    for rid in ("clinical_history", "mri_brain_contrast", "neurosurgery_opinion", "histopathology_brain"):
        assert _rec("brain_cns", rid)["tier"] == "a" and "tiers" not in _rec("brain_cns", rid), rid
    other = {r["id"] for r in protocol.records("brain_cns") if protocol.required(r, "adult_other", "essential")}
    assert other == {"clinical_history", "mri_brain_contrast", "neurosurgery_opinion", "histopathology_brain"}
    assert "idh_status" in _rec("brain_cns", "ihc_idh_atrx")["required_facts"] and "kps" in _rec("brain_cns", "clinical_history")["required_facts"]


def test_brain_cns_note_says_the_adult_records_come_from_a_european_guideline_with_credit():
    p = protocol.get("brain_cns")
    note = p["note"]
    assert "National Cancer Grid has no brain or CNS guideline" in note and "European guideline" in note
    assert "Weller" in note and "https://doi.org/10.1038/s41571-020-00447-z" in note and "Creative Commons Attribution 4.0" in note
    assert "child" in note and "paediatric book has no brain tumour chapter" in note
    assert p["guideline_sources"][0]["file"] == EANO
    assert p["guideline_sources"][0]["guideline"].startswith("EANO guidelines on the diagnosis and treatment of diffuse gliomas of adulthood")
    pages = {s["page"] for r in p["records"] for s in r["sources"]}
    assert pages <= {2, 3, 6, 7} and all(isinstance(x, int) for x in pages)


def test_brain_cns_licence_is_logged_beside_the_pdf():
    d = config.GUIDELINE_DIR / "eano"
    if not (d / "LICENCE.txt").is_file():
        pytest.skip("guideline library not on this machine")
    text = (d / "LICENCE.txt").read_text()
    assert "Creative Commons Attribution 4.0 International License" in text and "10.1038/s41571-020-00447-z" in text and "PMC7904519" in text
    assert (d / "EANO_2021_diffuse_gliomas_Weller.pdf").is_file()


# --- routing ---------------------------------------------------------------------------------------------------------------------

def test_routes_table_lists_every_record_of_the_five_protocols(data_root):
    rows = [r for r in rules.routes_table() if r["protocol"] in PIDS]
    expected = {(pid, r["id"], kind) for pid in PIDS for kind, recs in (("required", protocol.records(pid)), ("optional", protocol.get(pid)["optional"])) for r in recs}
    assert {(r["protocol"], r["record"], r["kind"]) for r in rows} == expected and len(rows) == len(expected)
    for r in rows:
        assert r["department"] and r["default_department"], r
        assert r["route_kind"] in org.ROUTE_KINDS, r
        if r["route_kind"] == org.COORDINATOR_ID:
            assert r["department_id"] is None and r["department"] == org.COORDINATOR_NAME
        elif r["route_kind"] == org.OWNER_ID and r["department_id"] is None:  # the owning team's own work (an eye examination) before the Case File records its owner
            assert org.is_owner_alias(r["default_department"]) and r["department"] == org.OWNER_NAME, r
        else:
            assert r["department_id"] and org.department(r["department_id"]), r


@pytest.mark.parametrize("pid,rec,dept", [
    ("wilms", "usg_abdomen_wilms", "radiology"), ("wilms", "ct_thorax_abdomen_pelvis_wilms", "radiology"),
    ("wilms", "loh_1p_16q", "pathology"), ("wilms", "biopsy_wilms", "pathology"),
    ("retinoblastoma", "b_scan_ultrasound", "radiology"), ("retinoblastoma", "germline_ngs", "medical_genetics"),
    ("retinoblastoma", "genetic_counselling_rb", "medical_genetics"), ("retinoblastoma", "bone_marrow_csf_rb", "pathology"),
    ("bone_sarcoma", "routine_blood_bone", "biochemistry"), ("bone_sarcoma", "alp_ldh_bone", "biochemistry"), ("bone_sarcoma", "bone_scan_bone", "nuclear_medicine"),
    ("bone_sarcoma", "pet_ct_bone", "nuclear_medicine"), ("bone_sarcoma", "molecular_ewing", "pathology"), ("bone_sarcoma", "bone_marrow_ewing", "pathology"),
    ("soft_tissue_sarcoma", "routine_blood_sts", "biochemistry"), ("soft_tissue_sarcoma", "bone_scan_marrow_rms", "nuclear_medicine"),
    ("soft_tissue_sarcoma", "molecular_sts", "pathology"), ("soft_tissue_sarcoma", "usg_nodes_sts", "radiology"),
    ("soft_tissue_sarcoma", "prior_excision_sts", "orthopaedic_oncology"),
    ("brain_cns", "mri_brain_contrast", "radiology"), ("brain_cns", "histopathology_brain", "pathology"), ("brain_cns", "mgmt_promoter", "pathology"),
    ("brain_cns", "neurosurgery_opinion", "neurosurgery"),
])
def test_supporting_records_route_to_the_department_that_produces_them(data_root, pid, rec, dept):
    p = protocol.get(pid)
    assert rules.routed(p, _rec(pid, rec))[1] == dept
