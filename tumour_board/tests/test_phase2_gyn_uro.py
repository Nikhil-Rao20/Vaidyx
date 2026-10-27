"""Phase 2 checklists, items 2.4 and 2.5 (night-v3): ovary, corpus_uteri, prostate, kidney (adult RCC) and germ_cell.

Draft checklists transcribed from the NCG Gynaecological Cancers and Urological Malignancies books (2019), labelled "needs a clinician's check"
(owner decision D6). The quote-on-page check is the shared test of item 2.1; the structure checks here copy test_tiers.py."""
import json
import re
from pathlib import Path

import pytest

from tumour_board import config, org, protocol, rules

PIDS = ("ovary", "corpus_uteri", "prostate", "kidney", "germ_cell")
GYN_FILE = "ncg_india/ncg-guidelines-for-gynecological-cancer-2019.docx"
URO_FILE = "ncg_india/ncg-guidelines-for-urological-malignancies-2019.pdf"
BOOK = {"ovary": GYN_FILE, "corpus_uteri": GYN_FILE, "prostate": URO_FILE, "kidney": URO_FILE, "germ_cell": URO_FILE}
SETTINGS = {
    "ovary": ["early", "advanced", "recurrent"],
    "corpus_uteri": ["early", "advanced"],
    "prostate": ["localised", "locally_extensive", "metastatic_hspc", "metastatic_crpc"],
    "kidney": ["localised", "metastatic"],
    "germ_cell": ["stage_i", "stage_ii_iii", "relapsed"],
}
COUNTS = {"ovary": 14, "corpus_uteri": 10, "prostate": 11, "kidney": 9, "germ_cell": 11}
OWNER_DEPT = {"ovary": "Gynaecologic Oncology", "corpus_uteri": "Gynaecologic Oncology", "prostate": "Urology", "kidney": "Urology", "germ_cell": "Urology"}


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
            assert src["guideline"].startswith("NCG") and src["quote"].strip(), r["id"]
            assert src["file"] == BOOK[pid], r["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), r["id"]
            assert (src["page"] == "n/a") == (pid in ("ovary", "corpus_uteri")), r["id"]  # the two Word books have no page numbers
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
    assert protocol.settings(pid) == p["settings"]
    assert protocol.setting_label(pid, SETTINGS[pid][0]) == p["settings"][0]["label"]


def test_the_labels_and_site_words_are_the_orchestrators():
    labels = {pid: protocol.get(pid)["label"] for pid in PIDS}
    assert labels == {"ovary": "Ovarian cancer (epithelial)", "corpus_uteri": "Cancer of the corpus uteri (endometrium)", "prostate": "Prostate cancer",
                      "kidney": "Kidney cancer (adult renal cell carcinoma)", "germ_cell": "Germ cell tumour of the testis"}
    assert protocol.get("ovary")["site"] == "ovar|adnex|tubo-ovarian|fallopian"  # omentum and peritoneum are regions many cancers image: never site words
    assert protocol.get("corpus_uteri")["site"] == "endometri|uterus|uterine|corpus uteri|myometri"  # not the stem "uter": it is inside "computerised"
    assert protocol.get("prostate")["site"] == "prostat|psa"
    assert protocol.get("kidney")["site"] == "kidney|renal|nephr"
    assert protocol.get("germ_cell")["site"] == "testis|testic|scrot|orchidect|germ cell|seminoma"
    breast_site_note = json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["site_note"]
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
    assert "hospital Tumour Board" in p["note"] and "National Cancer Grid" in p["note"]
    assert p["settings_note"]
    assert [g["file"] for g in p["guideline_sources"]] == [BOOK[pid]]
    assert all(g["guideline"].startswith("NCG") and g["pages"] for g in p["guideline_sources"])
    cited = {s["file"] for r in p["records"] for s in r["sources"]}
    assert cited == {BOOK[pid]}
    for key in ("extract_facts", "core_data", "core_data_source", "post_board", "policy_basis"):
        assert p[key], key
    assert p["post_board"] == json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["post_board"]


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
    assert ("figo_stage" in ef) == (pid in ("ovary", "corpus_uteri"))
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
    name, did, kind = rules.routed(p, ch)
    assert kind == "owner" and did == org.department_id(OWNER_DEPT[pid]) and org.department_group(did) == "treating"
    name, did, kind = rules.routed(p, ch, {"department": "medical_oncology"})
    assert (name, did, kind) == ("Medical Oncology", "medical_oncology", "owner")


# --- tiers that differ by setting -------------------------------------------------------------------------------------------------

def test_ovary_tiers_by_setting():
    asc = _rec("ovary", "ascitic_cytology")
    assert [protocol.tier_for(asc, s) for s in ("early", "advanced", "recurrent")] == ["none", "a", "none"]
    assert protocol.tier_for(asc, None) == "a"  # the strictest while the setting is unrecorded
    gi = _rec("ovary", "gi_endoscopy")
    assert [protocol.tier_for(gi, s) for s in ("early", "advanced", "recurrent")] == ["c", "c", "none"]
    bx = _rec("ovary", "image_guided_biopsy")
    assert protocol.tier_for(bx, "advanced") == "c" and protocol.tier_for(bx, "early") == "none" and bx["condition"]["ncg_tier"] == "a"
    assert protocol.tier_for(_rec("ovary", "ca125_cea"), "recurrent") == "a" and protocol.tier_for(_rec("ovary", "he4"), "early") == "c"
    gm = _rec("ovary", "germ_cell_markers")  # NCG (a) only for patients under 40 or if indicated: shown, never counted
    assert protocol.tier_for(gm, "early") == "c" and gm["condition"] == {"ncg_tier": "a", "text": "in patients under 40 years, or if indicated"}
    assert not protocol.required(gm, "early", "optimal")


def test_corpus_uteri_tiers_by_setting():
    her2 = _rec("corpus_uteri", "her2")
    assert protocol.tier_for(her2, "early") == "none" and protocol.tier_for(her2, "advanced") == "c"
    mol = _rec("corpus_uteri", "molecular_ihc")
    assert protocol.tier_for(mol, "early") == "b" and protocol.required(mol, "early", "optimal") and not protocol.required(mol, "early", "essential")
    fert = _rec("corpus_uteri", "mri_fertility")
    assert protocol.tier_for(fert, "early") == "c" and protocol.tier_for(fert, "advanced") == "none" and fert["condition"]["ncg_tier"] == "c"
    essential = {r["id"] for r in protocol.records("corpus_uteri") if protocol.required(r, "early", "essential")}
    assert essential == {"clinical_history", "endometrial_biopsy", "blood_counts_org", "chest_xray", "pelvic_imaging", "pathology_report"}
    assert "margins" not in _rec("corpus_uteri", "pathology_report")["required_facts"]


def test_prostate_tiers_by_setting():
    ct = _rec("prostate", "ct_abdomen_pelvis")
    assert [protocol.tier_for(ct, s) for s in SETTINGS["prostate"]] == ["none", "b", "b", "none"]
    bone = _rec("prostate", "bone_scan")
    assert [protocol.tier_for(bone, s) for s in SETTINGS["prostate"]] == ["none", "a", "a", "none"] and protocol.tier_for(bone, None) == "a"
    hrd = _rec("prostate", "genetic_hrd")
    assert protocol.tier_for(hrd, "metastatic_crpc") == "c" and protocol.tier_for(hrd, "localised") == "none" and hrd["department"] == "Medical Genetics"
    assert protocol.tier_for(_rec("prostate", "renal_dental_bone_agent"), "metastatic_crpc") == "a"
    assert protocol.tier_for(_rec("prostate", "life_expectancy_g8"), "localised") == "b"
    assert protocol.tier_for(_rec("prostate", "histopathology"), "metastatic_crpc") == "none"
    assert protocol.tier_for(_rec("prostate", "psa"), "metastatic_hspc") == "a"


def test_prostate_gleason_record_is_facts_only_and_psa_is_a_lab_record():
    g = _rec("prostate", "histopathology")
    assert g["facts_only"] is True and g["fact_doc_types"] == ["histopathology"] and "doc_types" not in g
    assert "gleason_isup" in g["required_facts"] and g["department"] == "Pathology"
    psa = _rec("prostate", "psa")
    assert psa["doc_types"] == ["lab"] and psa["required_facts"] == ["psa"] and psa["department"] == "Biochemistry"
    assert _rec("prostate", "biopsy_technique")["department"] == "Urology" and "route" not in _rec("prostate", "biopsy_technique")


def test_kidney_tiers_by_setting():
    bx = _rec("kidney", "renal_mass_biopsy")
    assert protocol.tier_for(bx, "metastatic") == "a" and protocol.tier_for(bx, "localised") == "c" and bx["condition"]["ncg_tier"] == "b"
    assert protocol.tier_for(_rec("kidney", "mskcc_indices"), "metastatic") == "b" and protocol.tier_for(_rec("kidney", "mskcc_indices"), "localised") == "none"
    assert protocol.tier_for(_rec("kidney", "dmsa_scan"), "metastatic") == "none" and protocol.tier_for(_rec("kidney", "dmsa_scan"), "localised") == "c"
    for rid, nt in (("bone_scan", "b"), ("mri_brain", "c")):  # NCG gives these only under a condition: shown, never counted
        r = _rec("kidney", rid)
        assert {protocol.tier_for(r, s) for s in SETTINGS["kidney"]} == {"c"} and r["condition"]["ncg_tier"] == nt
    essential = {r["id"] for r in protocol.records("kidney") if protocol.required(r, "localised", "essential")}
    assert essential == {"clinical_history", "ultrasound", "cect_kidney", "chest_imaging"}


def test_germ_cell_tiers_and_the_single_markers_record():
    ids = [r["id"] for r in protocol.records("germ_cell")]
    assert "tumour_markers" in ids and "post_orchidectomy_markers" not in ids
    m = _rec("germ_cell", "tumour_markers")
    assert m["doc_types"] == ["lab"] and m["required_facts"] == ["afp", "beta_hcg", "ldh"] and m["department"] == "Biochemistry"
    assert "orchidectomy" in m["note"] and len(m["sources"]) == 2 and all(protocol.tier_for(m, s) == "a" for s in SETTINGS["germ_cell"])
    usg = _rec("germ_cell", "usg_scrotum")
    assert [protocol.tier_for(usg, s) for s in SETTINGS["germ_cell"]] == ["a", "a", "none"]
    fp = _rec("germ_cell", "fertility_preservation")
    assert [protocol.tier_for(fp, s) for s in SETTINGS["germ_cell"]] == ["b", "b", "none"] and fp["route"] == "owner"
    pet = _rec("germ_cell", "pet_ct_post_chemo")
    assert protocol.tier_for(pet, "stage_ii_iii") == "c" and pet["condition"]["ncg_tier"] == "a" and protocol.tier_for(pet, "relapsed") == "none"
    brain = _rec("germ_cell", "brain_imaging")
    assert protocol.tier_for(brain, "stage_i") == "c" and brain["condition"]["ncg_tier"] == "b"
    assert protocol.tier_for(_rec("germ_cell", "ct_tap"), "relapsed") == "a"
    assert _rec("germ_cell", "risk_stratification")["department"] == "Medical Oncology" and _rec("germ_cell", "risk_stratification")["route"] == "owner"


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
        else:
            assert r["department_id"] and org.department(r["department_id"]), r


@pytest.mark.parametrize("pid,rec,dept", [
    ("ovary", "ca125_cea", "biochemistry"), ("ovary", "histopathology", "pathology"), ("ovary", "genetic_testing", "medical_genetics"),
    ("ovary", "gi_endoscopy", "gastrointestinal_surgery"), ("ovary", "imaging_cect", "radiology"), ("ovary", "image_guided_biopsy", "radiology"),
    ("corpus_uteri", "molecular_ihc", "pathology"), ("corpus_uteri", "blood_counts_org", "biochemistry"), ("corpus_uteri", "pelvic_imaging", "radiology"),
    ("prostate", "psa", "biochemistry"), ("prostate", "bone_scan", "nuclear_medicine"), ("prostate", "biopsy_technique", "urology"),
    ("prostate", "genetic_hrd", "medical_genetics"), ("prostate", "histopathology", "pathology"),
    ("kidney", "mskcc_indices", "biochemistry"), ("kidney", "dmsa_scan", "nuclear_medicine"), ("kidney", "renal_mass_biopsy", "pathology"),
    ("germ_cell", "tumour_markers", "biochemistry"), ("germ_cell", "fertility_hormones", "biochemistry"), ("germ_cell", "usg_scrotum", "radiology"),
    ("germ_cell", "pet_ct_post_chemo", "nuclear_medicine"),
])
def test_supporting_records_route_to_the_department_that_produces_them(data_root, pid, rec, dept):
    p = protocol.get(pid)
    assert rules.routed(p, _rec(pid, rec))[1] == dept


@pytest.mark.parametrize("pid,rec,default", [
    ("germ_cell", "fertility_preservation", "urology"), ("germ_cell", "risk_stratification", "medical_oncology"),
    ("prostate", "life_expectancy_g8", "urology"), ("prostate", "renal_dental_bone_agent", "urology"),
])
def test_clinical_records_route_to_the_owner(data_root, pid, rec, default):
    p, r = protocol.get(pid), _rec(pid, rec)
    assert r["route"] == "owner" and rules.routed(p, r)[1] == default and rules.routed(p, r)[2] == "owner"
    assert rules.routed(p, r, {"department": "surgical_oncology"})[1] == "surgical_oncology"


def test_owner_aliases_used_by_this_group_resolve():
    """These checklists use no owner alias (Ophthalmology, Cardiology, Anaesthesiology, Dental surgery): every department is a real one."""
    for pid in PIDS:
        for r in protocol.records(pid):
            assert org.department_id(r["department"]), (pid, r["id"], r["department"])


# --- conditions and regions -------------------------------------------------------------------------------------------------------

def test_conditional_records_have_system_tier_c_so_they_are_shown_never_counted():
    """A record NCG gives only under a condition the system never judges has system tier c in that setting (rules.py shows NCG's own tier)."""
    for pid in PIDS:
        for r in protocol.records(pid):
            if r.get("condition"):
                assert "c" in {protocol.tier_for(r, s) for s in SETTINGS[pid]}, (pid, r["id"])
                for s in SETTINGS[pid]:
                    if protocol.tier_for(r, s) == "c":
                        assert not protocol.required(r, s, "optimal"), (pid, r["id"], s)
    row = _rec("kidney", "bone_scan")
    assert protocol.tier_for(row, "metastatic") == "c" and not protocol.required(row, "metastatic", "optimal")
    assert row["condition"] == {"ncg_tier": "b", "text": "in raised alkaline phosphatase or bony pain"}


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
    for f in (GYN_FILE, URO_FILE):
        assert (root / f).is_file(), f
