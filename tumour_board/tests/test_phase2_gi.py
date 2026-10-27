"""Phase 2 checklists, items 2.2 and 2.3 (night-v3): colorectal_colon, stomach, oesophagus, liver_hcc and gallbladder.

Draft checklists transcribed from the NCG GI and thoracic books, labelled "needs a clinician's check" (owner decision D6). The quote-on-page
check is the shared test of item 2.1; the structure checks here copy test_tiers.py."""
import json

import pytest

from tumour_board import config, org, protocol, rules, store
from tumour_board.tests import util

PIDS = ("colorectal_colon", "stomach", "oesophagus", "liver_hcc", "gallbladder")
COLON_FILE = "ncg_india/management-of-colorectal-cancer.pdf"
STOMACH_FILE = "ncg_india/ncg-gi-draft-2021-gastric-cancer.pdf"
THORACIC_FILE = "ncg_india/ncg-guidelines-for-thoracic-cancer-2019.pdf"
LIVER_FILE = "ncg_india/ncg-gi-hepatocellular-carcinoma.docx"
GB_FILE = "ncg_india/ncg-gi-draft-2021-gall-bladder-cancer.pdf"
GB_SYNOPTIC = "ncg_india/ncg-gi-draft-2021-gallbladder-cancer-radiology-synoptic.pdf"
BOOKS = {"colorectal_colon": {COLON_FILE}, "stomach": {STOMACH_FILE}, "oesophagus": {THORACIC_FILE}, "liver_hcc": {LIVER_FILE}, "gallbladder": {GB_FILE, GB_SYNOPTIC}}
SETTINGS = {
    "colorectal_colon": ["non_metastatic", "metastatic"],
    "stomach": ["early_localized", "locally_advanced", "metastatic"],
    "oesophagus": ["early_localized", "locally_advanced", "metastatic"],
    "liver_hcc": ["resectable", "locoregional", "extrahepatic"],
    "gallbladder": ["per_primum", "incidental", "locally_advanced", "metastatic"],
}
LABELS = {"colorectal_colon": "Colon cancer", "stomach": "Stomach cancer", "oesophagus": "Oesophageal cancer",
          "liver_hcc": "Liver cancer (hepatocellular carcinoma)", "gallbladder": "Gallbladder cancer"}
SITES = {"colorectal_colon": "colon|caec|ascending|transverse|descending|sigmoid|hemicolect|colect|colorectal|bowel|intestin",
         "stomach": "stomach|gastr|antr|pylor|fund", "oesophagus": "oesophag|esophag|siewert", "liver_hcc": "liver|hepat|hcc",
         "gallbladder": "gallbladder|gall bladder|cholecyst|biliary"}
COUNTS = {"colorectal_colon": 11, "stomach": 11, "oesophagus": 10, "liver_hcc": 16, "gallbladder": 13}
OWNER_DEPT = {"colorectal_colon": "Colorectal Surgery", "stomach": "Gastrointestinal Surgery", "oesophagus": "Gastrointestinal Surgery",
              "liver_hcc": "Hepatobiliary and Pancreatic Surgery", "gallbladder": "Hepatobiliary and Pancreatic Surgery"}
POST_BOARD = {"colorectal_colon", "stomach", "oesophagus"}  # the cancers whose resection histopathology is a post-board optional record


def _raw(pid):
    return json.loads((config.PROTOCOL_DIR / f"{pid}.json").read_text())


def _rec(pid, rid):
    return next(r for r in protocol.records(pid) if r["id"] == rid)


def _tiers(pid, rid):
    return [protocol.tier_for(_rec(pid, rid), s) for s in SETTINGS[pid]]


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
            assert src["file"] in BOOKS[pid], r["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), r["id"]
            assert (src["page"] == "n/a") == src["file"].endswith(".docx"), r["id"]  # only the Word book has no page numbers
        assert all(f in cat for f in r.get("required_facts", [])), r["id"]
        assert set(r.get("doc_types", [])) <= doc_types and set(r.get("fact_doc_types", [])) <= doc_types, r["id"]
        assert r.get("doc_types") or (r.get("facts_only") and r.get("fact_doc_types")), r["id"]
        assert org.department_id(r["department"]) or org.is_owner_alias(r["department"]) or org.is_coordinator_name(r["department"]), (r["id"], r["department"])
        assert isinstance(r.get("sla_days"), int) and r["sla_days"] > 0, r["id"]
        assert r.get("tier_basis"), r["id"]
        for k in ("tier_basis", "note"):
            assert "—" not in r.get(k, ""), r["id"]
        if r.get("condition"):  # NCG's own tier under a condition the system never judges: the record itself is shown only
            assert r["condition"]["ncg_tier"] in protocol.TIERS and r["condition"]["text"] and "—" not in r["condition"]["text"], r["id"]
            assert "c" in {r["tier"], *(r.get("tiers") or {}).values()}, r["id"]
    for o in p["optional"]:  # optional entries: breast.json's shape; a post-board record also carries its quote
        assert o["id"] and o["label"] and o["doc_types"] and set(o["doc_types"]) <= doc_types and (org.department_id(o["department"]) or org.is_coordinator_name(o["department"])), o["id"]
        for src in o.get("sources", []):
            assert src["guideline"].startswith("NCG") and src["quote"].strip() and src["file"] in BOOKS[pid], o["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), o["id"]


@pytest.mark.parametrize("pid", PIDS)
def test_protocol_loads_and_is_listed_with_its_settings(pid):
    assert protocol.exists(pid)
    p = protocol.get(pid)
    assert p["id"] == pid and p["label"] == LABELS[pid] and p["site"] == SITES[pid]
    assert [s["id"] for s in p["settings"]] == SETTINGS[pid]
    assert all(s["label"].endswith(("as recorded", "(as recorded)")) for s in p["settings"])
    listed = {x["id"]: x for x in protocol.list_protocols()}
    assert pid in listed and [s["id"] for s in listed[pid]["settings"]] == SETTINGS[pid]
    assert listed[pid]["label"] == LABELS[pid] and listed[pid]["version"] == "0.1-draft"
    assert len(p["records"]) == COUNTS[pid]
    assert p["records"] is p["mandatory"]
    assert protocol.settings(pid) == p["settings"]
    assert protocol.setting_label(pid, SETTINGS[pid][0]) == p["settings"][0]["label"]


def test_site_notes():
    breast_site_note = json.loads((config.PROTOCOL_DIR / "breast.json").read_text())["site_note"]
    assert all(protocol.get(pid)["site_note"] == breast_site_note for pid in PIDS if pid != "colorectal_colon")
    colon = protocol.get("colorectal_colon")["site_note"]
    assert colon.startswith(breast_site_note) and "rectal checklist shares the colorectal words" in colon and "two linked primaries" in colon


@pytest.mark.parametrize("pid", PIDS)
def test_every_record_has_tier_source_and_valid_fields(pid):
    _check_structure(pid)


@pytest.mark.parametrize("pid", PIDS)
def test_draft_status_and_provenance(pid):
    p = protocol.get(pid)
    assert list(p)[:6] == ["id", "label", "version", "approval", "site", "site_note"]
    assert p["version"] == "0.1-draft"
    assert p["approval"]["status"] == "draft"
    assert "needs a clinician's check" in p["approval"]["note"] and "needs a clinician's check" in p["note"] and "needs a clinician's check" in p["settings_note"]
    assert "hospital Tumour Board" in p["note"] and "National Cancer Grid" in p["note"]
    assert {g["file"] for g in p["guideline_sources"]} == BOOKS[pid]
    assert all(g["guideline"].startswith("NCG") and g["pages"] for g in p["guideline_sources"])
    cited = {s["file"] for r in p["records"] + p["optional"] for s in r.get("sources", [])}
    assert cited == BOOKS[pid]
    for key in ("extract_facts", "core_data", "core_data_source", "post_board", "policy_basis"):
        assert p[key], key
    breast = json.loads((config.PROTOCOL_DIR / "breast.json").read_text())
    assert p["post_board"] == breast["post_board"] and p["core_data_source"] == breast["core_data_source"]
    # the four files whose NCG flow names the multidisciplinary meeting keep that line after breast's policy basis (orchestrator, Phase 2)
    assert p["policy_basis"].startswith(breast["policy_basis"]) and (pid == "oesophagus") == (p["policy_basis"] == breast["policy_basis"])


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
    assert "nodes_examined" in protocol.facts_for_doc("colorectal_colon", "histopathology") and "nodes_examined" in protocol.facts_for_doc("stomach", "histopathology")
    assert {"siewert_type", "trg"} <= set(protocol.get("oesophagus")["extract_facts"])


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
    assert _tiers(pid, "clinical_history") == ["a"] * len(SETTINGS[pid]) and "tiers" not in ch
    name, did, kind = rules.routed(p, ch)
    assert kind == "owner" and did == org.department_id(OWNER_DEPT[pid]) and org.department_group(did) == "treating"
    name, did, kind = rules.routed(p, ch, {"department": "medical_oncology"})
    assert (name, did, kind) == ("Medical Oncology", "medical_oncology", "owner")


@pytest.mark.parametrize("pid", [p for p in PIDS if p != "oesophagus"])  # the oesophagus flow has no multidisciplinary box
def test_the_board_itself_is_not_a_record(pid):
    """The research note proposes the board's own discussion as an Essential record; the Tumour Board Case File is that discussion, so no
    record asks for it (it could never exist before the board) and NCG's line is kept in the policy basis (orchestrator, Phase 2)."""
    p = protocol.get(pid)
    assert not any(r["id"] == "mdt_discussion" for r in p["records"])
    assert "asks for the board" in p["policy_basis"] and "no separate record is required" in p["policy_basis"]


# --- tiers that differ by setting --------------------------------------------------------------------------------------------------

def test_colon_tiers_by_setting():
    assert _tiers("colorectal_colon", "mmr") == ["b", "a"] and protocol.tier_for(_rec("colorectal_colon", "mmr"), None) == "a"  # differs from the rectum (c / a)
    assert _tiers("colorectal_colon", "ras_braf") == ["none", "a"] and _tiers("colorectal_colon", "her2") == ["none", "b"]
    assert _tiers("colorectal_colon", "pet_ct") == ["c", "c"] and _tiers("colorectal_colon", "mri_liver") == ["c", "c"]
    assert _tiers("colorectal_colon", "restaging_ct") == ["none", "c"]
    for setting in ("non_metastatic", "metastatic", None):
        req = {r["id"] for r in protocol.records("colorectal_colon") if protocol.required(r, setting, "essential")}
        assert {"clinical_history", "colonoscopy", "histopathology", "cea", "cect_abdomen_pelvis_chest"} <= req, setting
        assert not req & {"pet_ct", "mri_liver", "her2", "restaging_ct"}, setting
    met = {r["id"] for r in protocol.records("colorectal_colon") if protocol.required(r, "metastatic", "essential")}
    assert {"mmr", "ras_braf"} <= met
    nonmet = {r["id"] for r in protocol.records("colorectal_colon") if protocol.required(r, "non_metastatic", "essential")}
    assert not nonmet & {"mmr", "ras_braf"}
    assert protocol.required(_rec("colorectal_colon", "mmr"), "non_metastatic", "optimal")
    assert _rec("colorectal_colon", "colonoscopy")["required_facts"] == ["tumour_site_colon"] and _rec("colorectal_colon", "colonoscopy")["department"] == "Gastrointestinal Surgery"


def test_stomach_tiers_by_setting():
    assert _tiers("stomach", "eus") == ["b", "b", "none"] and _tiers("stomach", "her2") == ["none", "c", "b"] and _tiers("stomach", "pdl1") == ["none", "none", "c"]
    assert _tiers("stomach", "pre_anaesthetic") == ["b", "b", "none"] and _tiers("stomach", "nutrition") == ["b", "b", "b"]
    cdh1 = _rec("stomach", "cdh1_testing")  # NCG: essential only in selected patients: shown, never counted
    assert _tiers("stomach", "cdh1_testing") == ["c", "c", "c"] and cdh1["condition"]["ncg_tier"] == "a" and cdh1["department"] == "Medical Genetics" and cdh1["sla_days"] == 10
    lap = _rec("stomach", "staging_laparoscopy")
    assert _tiers("stomach", "staging_laparoscopy") == ["none", "c", "none"] and lap["condition"]["ncg_tier"] == "b" and lap["department"] == "Surgical Oncology"
    pre = _rec("stomach", "pre_anaesthetic")
    assert pre["department"] == "Anaesthesiology" and pre["route"] == "owner" and org.is_owner_alias("Anaesthesiology")
    assert rules.routed(protocol.get("stomach"), pre, {"department": "gastrointestinal_surgery"})[1:] == ("gastrointestinal_surgery", "owner")
    assert _rec("stomach", "nutrition")["department"] == "Palliative Medicine"
    for setting in ("early_localized", "locally_advanced", "metastatic"):
        req = {r["id"] for r in protocol.records("stomach") if protocol.required(r, setting, "essential")}
        assert req == {"clinical_history", "upper_gi_endoscopy", "histopathology", "cect_tap"}, setting
    assert "pet_ct" not in {r["id"] for r in protocol.records("stomach")} and "PET scan should NOT be performed in gastric cancer" in protocol.get("stomach")["note"]


def test_oesophagus_tiers_by_setting():
    assert _tiers("oesophagus", "pet_cect") == ["b", "b", "b"] and _tiers("oesophagus", "eus") == ["c", "c", "none"] and _tiers("oesophagus", "her2") == ["none", "none", "c"]
    assert _tiers("oesophagus", "restaging_ct") == ["none", "a", "none"]
    br = _rec("oesophagus", "bronchoscopy")  # (b) on the page, but only for the upper or middle third or a voice history: shown, never counted
    assert _tiers("oesophagus", "bronchoscopy") == ["c", "c", "none"] and br["condition"]["ncg_tier"] == "b" and br["department"] == "Pulmonology"
    lap = _rec("oesophagus", "staging_laparoscopy")
    assert _tiers("oesophagus", "staging_laparoscopy") == ["none", "c", "none"] and lap["condition"]["ncg_tier"] == "b"
    assert not any(protocol.required(r, s, "optimal") for r in (br, lap) for s in (*SETTINGS["oesophagus"], None))
    for setting in ("early_localized", "locally_advanced", "metastatic", None):
        req = {r["id"] for r in protocol.records("oesophagus") if protocol.required(r, setting, "essential")}
        assert {"clinical_history", "histopathology", "upper_gi_endoscopy", "cect_staging"} <= req, setting
    assert protocol.required(_rec("oesophagus", "restaging_ct"), "locally_advanced", "essential")
    assert protocol.required(_rec("oesophagus", "pet_cect"), "metastatic", "optimal") and not protocol.required(_rec("oesophagus", "pet_cect"), "metastatic", "essential")
    assert _rec("oesophagus", "upper_gi_endoscopy")["required_facts"] == ["tumour_location_oesophagus"]
    assert any(o["id"] == "palliative_care_referral" and o["department"] == "Palliative Medicine" for o in protocol.get("oesophagus")["optional"])


def test_liver_tiers_by_setting():
    assert _tiers("liver_hcc", "chest_ct") == ["a", "c", "a"] and _tiers("liver_hcc", "flr_measurement") == ["a", "b", "none"] and _tiers("liver_hcc", "hvpg") == ["c", "none", "none"]
    assert protocol.tier_for(_rec("liver_hcc", "chest_ct"), None) == "a" and protocol.tier_for(_rec("liver_hcc", "hvpg"), None) == "c"
    assert _tiers("liver_hcc", "mri_liver") == ["b", "b", "b"] and _tiers("liver_hcc", "hbv_core_antibody") == ["c", "c", "c"] and _tiers("liver_hcc", "pivka") == ["c", "c", "c"]
    bx = _rec("liver_hcc", "biopsy")  # NCG (a) only for LI-RADS 4 and AFP below 400: shown, never counted
    assert _tiers("liver_hcc", "biopsy") == ["c", "c", "c"] and bx["condition"]["ncg_tier"] == "a"
    for setting in ("resectable", "locoregional", "extrahepatic"):
        req = {r["id"] for r in protocol.records("liver_hcc") if protocol.required(r, setting, "essential")}
        assert {"clinical_history", "triphasic_cect", "cbc", "liver_function_inr", "hepatitis_serology", "afp", "child_bclc_recorded", "varices_endoscopy"} <= req, setting
        assert not req & {"mri_liver", "hbv_core_antibody", "pivka", "biopsy", "hvpg"}, setting
    assert "flr_measurement" in {r["id"] for r in protocol.records("liver_hcc") if protocol.required(r, "resectable", "essential")}
    assert "chest_ct" not in {r["id"] for r in protocol.records("liver_hcc") if protocol.required(r, "locoregional", "essential")}
    assert "PET" in protocol.get("liver_hcc")["note"] and "pet_ct" not in {r["id"] for r in protocol.records("liver_hcc")}
    assert all(s["page"] == "n/a" and s.get("where") for r in protocol.records("liver_hcc") for s in r["sources"])


def test_liver_blood_tests_are_split_by_test():
    cbc, lft = _rec("liver_hcc", "cbc"), _rec("liver_hcc", "liver_function_inr")
    assert cbc["department"] == "Pathology" and cbc["required_facts"] == ["haemoglobin", "platelets"] and cbc["doc_types"] == ["lab"]
    assert lft["department"] == "Biochemistry" and lft["required_facts"] == ["bilirubin", "inr"] and lft["doc_types"] == ["lab"]
    assert cbc["sources"] == lft["sources"] and _rec("liver_hcc", "hepatitis_serology")["department"] == "Microbiology"
    assert _rec("liver_hcc", "hepatitis_serology")["required_facts"] == ["hbsag", "anti_hcv"] and _rec("liver_hcc", "afp")["department"] == "Biochemistry"
    assert _rec("liver_hcc", "child_bclc_recorded")["route"] == "owner" and _rec("liver_hcc", "nutrition_supportive")["department"] == "Palliative Medicine"


def test_gallbladder_tiers_by_setting():
    assert _tiers("gallbladder", "ultrasonography") == ["a", "b", "a", "a"] and _tiers("gallbladder", "pet_cect") == ["c", "b", "a", "c"]
    assert _tiers("gallbladder", "histopathology") == ["b", "a", "a", "a"] and _tiers("gallbladder", "cystic_duct_margin") == ["none", "a", "none", "none"]
    assert _tiers("gallbladder", "staging_laparoscopy") == ["b", "b", "b", "none"] and _tiers("gallbladder", "ihc_if_not_adenocarcinoma") == ["none", "none", "none", "c"]
    mrcp = _rec("gallbladder", "mri_mrcp")  # Optimal only for a patient with obstructive jaundice: shown, never counted
    assert _tiers("gallbladder", "mri_mrcp") == ["c", "none", "c", "none"] and mrcp["condition"]["ncg_tier"] == "b"
    for rid in ("cbc", "creatinine"):
        assert _tiers("gallbladder", rid) == ["none", "a", "a", "none"], rid
    assert _rec("gallbladder", "cbc")["department"] == "Pathology" and _rec("gallbladder", "creatinine")["department"] == "Biochemistry"
    assert _tiers("gallbladder", "ca19_9") == ["a"] * 4 and _tiers("gallbladder", "cect_cap") == ["a"] * 4
    locally = {r["id"] for r in protocol.records("gallbladder") if protocol.required(r, "locally_advanced", "essential")}
    assert locally == {"clinical_history", "ultrasonography", "liver_function", "ca19_9", "cbc", "creatinine", "cect_cap", "histopathology", "pet_cect"}
    assert {r["id"] for r in protocol.records("gallbladder") if protocol.required(r, "per_primum", "optimal")} == {
        "clinical_history", "ultrasonography", "liver_function", "ca19_9", "cect_cap", "histopathology", "staging_laparoscopy"}
    cect = _rec("gallbladder", "cect_cap")  # the radiology synoptic gives the elements the report should state
    assert any(src["file"] == GB_SYNOPTIC for src in cect["sources"]) and set(cect["required_facts"]) >= {"vessel_involvement", "bile_duct_involvement"}
    assert cect["sources"][0]["page"] == 1 and cect["sources"][0]["file"] == GB_FILE


def test_the_note_records_are_conditional_where_the_book_gives_a_tier_only_under_a_condition():
    expected = {("stomach", "cdh1_testing"): "a", ("stomach", "staging_laparoscopy"): "b", ("oesophagus", "bronchoscopy"): "b", ("oesophagus", "staging_laparoscopy"): "b",
                ("liver_hcc", "biopsy"): "a", ("gallbladder", "mri_mrcp"): "b"}
    for (pid, rid), nt in expected.items():
        r = _rec(pid, rid)
        assert r["condition"]["ncg_tier"] == nt and r["tier"] == "c", (pid, rid)
        assert {protocol.tier_for(r, s) for s in SETTINGS[pid]} <= {"c", "none"}, (pid, rid)


# --- post-board and restaging records --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", sorted(POST_BOARD))
def test_resection_histopathology_is_a_post_board_optional_record(pid):
    assert "resection_histopathology" not in {r["id"] for r in protocol.records(pid)}
    o = next(x for x in protocol.get(pid)["optional"] if x["id"] == "resection_histopathology")
    assert o["doc_types"] == ["histopathology"] and o["department"] == "Pathology" and o["sources"] and "post-board" in o["note"]
    assert {"margins"} <= set(protocol.get(pid)["extract_facts"])


@pytest.mark.parametrize("pid,rid", [("colorectal_colon", "restaging_ct"), ("oesophagus", "restaging_ct")])
def test_restaging_ct_waits_for_a_treatment_summary(pid, rid):
    r = _rec(pid, rid)
    assert r["must_postdate_doc_type"] == "treatment_summary" and r["applies_if_doc_type_present"] == "treatment_summary" and r["doc_types"] == ["ct"]


# --- the gate reads the new checklists --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", PIDS)
def test_the_gate_lists_every_record_for_every_setting(pid):
    for setting in (*SETTINGS[pid], ""):
        store.create_case(f"TB-GI-{pid}-{setting or 'none'}", util.PATIENT, pid, created_by="test", setting=setting)
        g = rules.evaluate(f"TB-GI-{pid}-{setting or 'none'}")
        ids = {r["id"] for r in g["requirements"] + g["shown"]}
        assert ids == {r["id"] for r in protocol.records(pid)}, (pid, setting)
        counted = {r["id"] for r in g["requirements"]}
        assert counted == {r["id"] for r in protocol.records(pid) if protocol.required(r, setting or None, "essential")}, (pid, setting)
        assert "mdt_discussion" not in ids


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
        elif r["route_kind"] == org.OWNER_ID and r["department_id"] is None:  # a pre-anaesthetic check is the owner's own work until a Case File records its owner
            assert org.is_owner_alias(r["default_department"]) and r["department"] in (org.OWNER_NAME, r["default_department"]), r
        else:
            assert r["department_id"] and org.department(r["department_id"]), r


@pytest.mark.parametrize("pid,rec,dept", [
    ("colorectal_colon", "colonoscopy", "gastrointestinal_surgery"), ("colorectal_colon", "cea", "biochemistry"), ("colorectal_colon", "mmr", "pathology"),
    ("colorectal_colon", "ras_braf", "pathology"), ("colorectal_colon", "her2", "pathology"), ("colorectal_colon", "pet_ct", "nuclear_medicine"),
    ("colorectal_colon", "cect_abdomen_pelvis_chest", "radiology"),
    ("stomach", "upper_gi_endoscopy", "gastrointestinal_surgery"), ("stomach", "cdh1_testing", "medical_genetics"), ("stomach", "staging_laparoscopy", "surgical_oncology"),
    ("stomach", "nutrition", "palliative_medicine"), ("stomach", "her2", "pathology"), ("stomach", "cect_tap", "radiology"),
    ("oesophagus", "bronchoscopy", "pulmonology"), ("oesophagus", "pet_cect", "nuclear_medicine"), ("oesophagus", "eus", "gastrointestinal_surgery"),
    ("oesophagus", "histopathology", "pathology"), ("oesophagus", "restaging_ct", "radiology"),
    ("liver_hcc", "cbc", "pathology"), ("liver_hcc", "liver_function_inr", "biochemistry"), ("liver_hcc", "hepatitis_serology", "microbiology"),
    ("liver_hcc", "afp", "biochemistry"), ("liver_hcc", "varices_endoscopy", "gastrointestinal_surgery"), ("liver_hcc", "hvpg", "hepatobiliary_pancreatic_surgery"),
    ("liver_hcc", "triphasic_cect", "radiology"), ("liver_hcc", "biopsy", "pathology"),
    ("gallbladder", "ca19_9", "biochemistry"), ("gallbladder", "cbc", "pathology"), ("gallbladder", "creatinine", "biochemistry"),
    ("gallbladder", "pet_cect", "nuclear_medicine"), ("gallbladder", "staging_laparoscopy", "hepatobiliary_pancreatic_surgery"),
    ("gallbladder", "cystic_duct_margin", "pathology"), ("gallbladder", "ultrasonography", "radiology"),
])
def test_supporting_records_route_to_the_department_that_produces_them(data_root, pid, rec, dept):
    p = protocol.get(pid)
    assert rules.routed(p, _rec(pid, rec))[1] == dept
