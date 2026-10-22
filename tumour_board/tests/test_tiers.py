"""NCG tiers on the protocol records (V1 item 4.1): every required record names its NCG tier (a = Essential, b = Optimal,
c = Optional), per setting where NCG differs, with the verbatim NCG quote and page; the helpers decide what is required."""
import json

import pytest

from tumour_board import config, org, protocol

PIDS = ("lung_nsclc", "breast", "colorectal_rectum", "oral_cavity", "cervix")
# research notes holding every quoted NCG line: 4.1 (lung, breast, rectum), 9.1 / 9.2 (oral cavity, cervix)
NOTES = {"ncg_tiers_4.1.md": ("lung_nsclc", "breast", "colorectal_rectum"), "ncg_tiers_9.md": ("oral_cavity", "cervix")}


def _rec(pid, rid):
    return next(r for r in protocol.records(pid) if r["id"] == rid)


@pytest.mark.parametrize("pid", PIDS)
def test_every_record_has_tier_source_and_valid_fields(pid):
    p = protocol.get(pid)
    raw = json.loads((config.PROTOCOL_DIR / f"{pid}.json").read_text())
    assert "records" in raw and "mandatory" not in raw
    setting_ids = {s["id"] for s in p["settings"]}
    cat, doc_types = protocol.facts(), set(protocol.doc_types())
    ids = [r["id"] for r in p["records"]]
    assert len(ids) == len(set(ids))
    for r in p["records"]:
        assert r["tier"] in protocol.TIERS, r["id"]
        for s, t in (r.get("tiers") or {}).items():
            assert s in setting_ids and t in (*protocol.TIERS, "none"), (r["id"], s, t)
        raw_rec = next(x for x in raw["records"] if x["id"] == r["id"])
        assert raw_rec.get("source") or raw_rec.get("sources"), r["id"]
        assert r["source"] == r["sources"][0]
        for src in r["sources"]:
            assert src["guideline"].startswith("NCG") and src["quote"].strip(), r["id"]
            assert isinstance(src["page"], int) or (src["page"] == "n/a" and src.get("where")), r["id"]
        assert all(f in cat for f in r.get("required_facts", [])), r["id"]
        assert set(r.get("doc_types", [])) <= doc_types and set(r.get("fact_doc_types", [])) <= doc_types, r["id"]
        assert r.get("doc_types") or (r.get("facts_only") and r.get("fact_doc_types")), r["id"]
        assert org.department_id(r["department"]) or org.is_owner_alias(r["department"]), (r["id"], r["department"])  # a dental evaluation goes to the owner (18 Oct)
        for k in ("tier_basis", "note"):
            assert "—" not in r.get(k, ""), r["id"]
        if r.get("condition"):  # NCG's own tier under a condition the system never judges: the record itself is shown only
            assert r["condition"]["ncg_tier"] in protocol.TIERS and r["condition"]["text"] and "—" not in r["condition"]["text"], r["id"]
            assert "c" in {r["tier"], *(r.get("tiers") or {}).values()}, r["id"]


@pytest.mark.parametrize("name", sorted(NOTES))
def test_quotes_are_verbatim_from_the_research_note(name):
    note = config.PROTOCOL_DIR.parents[1] / "docs_Eswar" / "research" / name
    if not note.exists():
        pytest.skip("research note not in this checkout")
    text = note.read_text()
    for pid in NOTES[name]:
        for r in protocol.records(pid):
            for src in r["sources"]:
                assert src["quote"] in text, (pid, r["id"], src["quote"])


def test_every_protocol_is_covered_by_a_research_note():
    assert set(PIDS) == {p for pids in NOTES.values() for p in pids}


def test_records_and_mandatory_are_the_same_list():
    p = protocol.get("lung_nsclc")
    assert p["records"] is p["mandatory"] and protocol.records(p) is p["records"]
    assert [r["id"] for r in protocol.records("lung_nsclc")] == [r["id"] for r in p["records"]]


def test_tier_for_with_and_without_a_setting():
    brain = _rec("lung_nsclc", "brain_mri")
    assert protocol.tier_for(brain, "non_metastatic") == "b"
    assert protocol.tier_for(brain, "metastatic") == "c"
    assert protocol.tier_for(brain, "") == "b" and protocol.tier_for(brain, None) == "b"  # strictest of b / c
    assert protocol.tier_for(_rec("lung_nsclc", "bronchoscopy"), "metastatic") == "none"
    assert protocol.tier_for(_rec("lung_nsclc", "bronchoscopy"), None) == "b"
    mmr = _rec("colorectal_rectum", "mmr")
    assert protocol.tier_for(mmr, None) == "a"  # Essential in the metastatic setting: never dropped while the setting is unrecorded
    assert protocol.tier_for(mmr, "non_metastatic") == "c"
    assert protocol.tier_for(_rec("lung_nsclc", "pdl1"), "metastatic") == "b"  # no per-setting tiers: the record's tier
    assert protocol.tier_for({"id": "x"}, "metastatic") == "a"
    assert protocol.tier_for({"tier": "c", "tiers": {"early": "b"}}, "unknown") == "b"  # an unknown setting id is treated like an unrecorded one (review)
    assert protocol.tier_for({"tiers": {"x": "none", "y": "c"}}, None) == "c"


def test_required_at_essential_and_optimal_levels():
    assert protocol.required({"tier": "a"}, None, "essential") and protocol.required({"tier": "a"}, None, "optimal")
    assert not protocol.required({"tier": "b"}, None, "essential") and protocol.required({"tier": "b"}, None, "optimal")
    assert not protocol.required({"tier": "c"}, None, "optimal")
    brain = _rec("lung_nsclc", "brain_mri")
    assert protocol.required(brain, "non_metastatic", "optimal") and not protocol.required(brain, "metastatic", "optimal")
    assert not protocol.required(_rec("lung_nsclc", "bronchoscopy"), "metastatic", "optimal")


def test_lung_essential_non_metastatic():
    req = {r["id"] for r in protocol.records("lung_nsclc") if protocol.required(r, "non_metastatic", "essential")}
    assert {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "cbc", "liver_renal_function"} <= req
    assert not req & {"pet_ct", "brain_mri", "pdl1", "met"}
    opt = {r["id"] for r in protocol.records("lung_nsclc") if protocol.required(r, "non_metastatic", "optimal")}
    assert {"pet_ct", "brain_mri", "pdl1", "met", "bronchoscopy", "mediastinal_staging"} <= opt
    assert "mri_thorax_superior_sulcus" not in opt
    assert protocol.tier_for(_rec("lung_nsclc", "brain_mri"), "metastatic") == "c"
    assert protocol.tier_for(_rec("lung_nsclc", "bronchoscopy"), "metastatic") == "none"
    assert "ct_thorax" not in {r["id"] for r in protocol.records("lung_nsclc")}


def test_breast_early_and_rectum_metastatic():
    assert protocol.tier_for(_rec("breast", "metastatic_workup"), "early") == "none"
    assert protocol.tier_for(_rec("breast", "cbc"), "early") == "b" and protocol.tier_for(_rec("breast", "liver_renal_function"), "early") == "b"
    assert protocol.tier_for(_rec("breast", "cbc"), "locally_advanced") == "a"
    early = {r["id"] for r in protocol.records("breast") if protocol.required(r, "early", "essential")}
    assert early == {"clinical_history", "breast_imaging", "histopathology", "receptor_status"}
    met = {r["id"] for r in protocol.records("colorectal_rectum") if protocol.required(r, "metastatic", "essential")}
    assert {"mmr", "ras_braf", "systemic_staging"} <= met and "pet_ct" not in met
    nonmet = {r["id"] for r in protocol.records("colorectal_rectum") if protocol.required(r, "non_metastatic", "essential")}
    assert not nonmet & {"mmr", "ras_braf", "pet_ct", "restaging_ct"}
    assert "pet_ct" not in _rec("colorectal_rectum", "systemic_staging")["doc_types"]


def test_setting_label():
    assert protocol.setting_label("breast", "early") == "Early (operable), as recorded"
    assert protocol.setting_label("breast", "nope") == "" and protocol.setting_label("breast", None) == ""
    assert protocol.setting_label("no_such_protocol", "early") == ""


def test_tier_labels():
    assert [protocol.TIER_LABEL[t] for t in (*protocol.TIERS, "none")] == ["Essential", "Optimal", "Optional", "Not applicable"]
    assert protocol.STRICTNESS["a"] > protocol.STRICTNESS["b"] > protocol.STRICTNESS["c"] > protocol.STRICTNESS["none"]


def test_legacy_mandatory_key_still_read(tmp_path, monkeypatch):
    d = tmp_path / "protocols"; d.mkdir()
    (d / "facts.json").write_text((config.PROTOCOL_DIR / "facts.json").read_text())
    (d / "legacy.json").write_text(json.dumps({"id": "legacy", "label": "Legacy", "version": "0.1", "optional": [], "extract_facts": [],
                                               "mandatory": [{"id": "labs", "label": "Labs", "doc_types": ["lab"], "department": "Laboratory Medicine",
                                                              "required_facts": ["haemoglobin"]}]}))
    monkeypatch.setattr(config, "PROTOCOL_DIR", d)
    p = protocol.get("legacy")
    assert p["records"] is p["mandatory"] and p["records"][0]["tier"] == "a"
    assert protocol.required(p["records"][0], None, "essential")
    assert protocol.exists("legacy") and [x["id"] for x in protocol.list_protocols()] == ["legacy"]
    assert protocol.facts_for_doc("legacy", "lab") == ["haemoglobin"]


def test_list_protocols_and_met_fact():
    ids = {p["id"] for p in protocol.list_protocols()}
    assert set(PIDS) <= ids
    assert "met" in protocol.facts_for_doc("lung_nsclc", "molecular")
    assert "met" in protocol.get("lung_nsclc")["extract_facts"]
    assert {"xray", "ultrasound"} <= set(protocol.facts()["distant_findings"]["doc_types"])
    assert "distant_findings" in protocol.facts_for_doc("breast", "xray")
    assert "pdl1" in protocol.facts_for_doc("lung_nsclc", "ihc")  # Optimal records' fields are still extracted


def test_oral_cavity_tiers_by_setting():
    """V1 item 9.1: NCG head and neck 2019, oral cancer work-up (p 4). Listed records without a letter are Essential; the imaging of the
    primary and neck relaxes to Optimal in early disease; PET-CT / CECT thorax (high-risk patients only) are shown, never counted."""
    for setting in ("early", "locally_advanced", "metastatic", None):
        req = {r["id"] for r in protocol.records("oral_cavity") if protocol.required(r, setting, "essential")}
        assert {"clinical_history", "histopathology", "chest_imaging", "dental_evaluation"} <= req, setting
        assert not req & {"pet_ct", "cect_thorax"}, setting
        assert ("primary_neck_imaging" in req) == (setting != "early"), setting
    assert protocol.required(_rec("oral_cavity", "primary_neck_imaging"), "early", "optimal")
    assert protocol.tier_for(_rec("oral_cavity", "primary_neck_imaging"), None) == "a"  # setting not recorded: the strictest
    assert not any(protocol.required(_rec("oral_cavity", r), s, "optimal") for r in ("pet_ct", "cect_thorax") for s in ("early", "locally_advanced", None))
    dental = _rec("oral_cavity", "dental_evaluation")
    assert "facts_only" not in dental and dental["required_facts"] == ["dental_evaluation"] and dental["doc_types"] == ["clinical_note", "referral"]  # V2 2.4: its own record
    assert dental["department"].startswith("Dental Surgery") and dental["region"]
    assert all(s["guideline"] == "NCG Guidelines for Head and Neck Cancer (2019)" and s["page"] == 4 for s in _rec("oral_cavity", "chest_imaging")["sources"])


def test_oral_cavity_fields_and_extraction():
    cat = protocol.facts()
    for f in ("tobacco_use", "depth_of_invasion", "pni", "ene", "dental_evaluation"):
        assert f in cat and cat[f]["label"] and "—" not in cat[f]["desc"], f
    assert "dental_evaluation" in protocol.facts_for_doc("oral_cavity", "clinical_note")
    assert "dental_evaluation" in protocol.facts_for_doc("oral_cavity", "other")  # a required field is asked of an unclassified document (3.2)
    assert {"depth_of_invasion", "pni", "histologic_type"} <= set(protocol.facts_for_doc("oral_cavity", "histopathology"))
    assert {"depth_of_invasion", "lesion_size", "nodal_findings", "ene"} <= set(protocol.facts_for_doc("oral_cavity", "ct"))
    assert "dental_evaluation" not in protocol.facts_for_doc("breast", "clinical_note")  # other protocols unchanged
    assert protocol.setting_label("oral_cavity", "locally_advanced") == "Locally advanced (Stage III to IVB), as recorded"


def test_cervix_tiers_by_setting():
    """V1 item 9.2: NCG gynaecological 2019, cervix summary table ((a) / (b) / (c) columns for early and locally advanced disease, FIGO 2018);
    conditional items (CT thorax for IIIC2, IHC as indicated, PET-CT) are shown, never counted."""
    req = lambda setting, level="essential": {r["id"] for r in protocol.records("cervix") if protocol.required(r, setting, level)}
    base = {"clinical_history", "histopathology", "cbc", "liver_renal_function", "viral_markers"}  # V2 2.4: blood tests by test
    assert req("early") == base | {"abdomen_pelvis_imaging", "chest_xray"}
    assert req("early", "optimal") == base | {"abdomen_pelvis_imaging", "chest_xray", "mri_pelvis"}
    assert req("locally_advanced") == base | {"cect_abdomen_pelvis", "cystoscopy_proctoscopy"}
    assert req("locally_advanced", "optimal") == base | {"cect_abdomen_pelvis", "cystoscopy_proctoscopy", "chest_xray"}  # MRI: "MRI OR CECT", CECT already required
    assert req("metastatic") == req("locally_advanced")  # IVB has no NCG work-up row: the locally advanced row applies
    assert req(None) == base | {"abdomen_pelvis_imaging", "cect_abdomen_pelvis", "chest_xray", "cystoscopy_proctoscopy"}  # not recorded: the strictest
    for s in ("early", "locally_advanced", "metastatic", None):
        assert not req(s, "optimal") & {"ct_thorax", "ihc", "pet_ct"}, s
    hp = _rec("cervix", "histopathology")
    assert hp["required_facts"] == ["histologic_type", "grade", "depth_of_invasion", "lvi"]
    assert "figo_stage" in _rec("cervix", "clinical_history")["required_facts"] and "hiv_status" in _rec("cervix", "viral_markers")["required_facts"]
    for r in protocol.records("cervix"):
        for src in r["sources"]:
            assert src["guideline"] == "NCG Guidelines for Gynaecological Cancers (2019)" and src["page"] == "n/a" and src["where"], r["id"]


def test_cervix_fields_and_extraction():
    cat = protocol.facts()
    assert cat["figo_stage"]["critical"] is True and "never derive" in cat["figo_stage"]["desc"]
    for f in ("figo_stage", "parametrial_involvement", "hiv_status"):
        assert f in cat and "—" not in cat[f]["desc"], f
    assert {"figo_stage", "parametrial_involvement"} <= set(protocol.facts_for_doc("cervix", "mri"))
    assert "hiv_status" in protocol.facts_for_doc("cervix", "lab") and "hiv_status" not in protocol.facts_for_doc("breast", "lab")
    assert protocol.setting_label("cervix", "early") == "Early (FIGO 2018 IA1 to IIA1), as recorded"


def test_conditional_records_show_the_ncg_tier(tmp_path):
    """Review of Phase 9: a record NCG tiers under a condition (CT thorax Essential for FIGO IIIC2, IHC Optimal as indicated, PET-CT Optimal for
    high-risk oral cancer, superior sulcus MRI) is shown with NCG's tier and the condition, never counted, never labelled Optional."""
    from tumour_board import rules
    conds = {(pid, r["id"]): r["condition"]["ncg_tier"] for pid in PIDS for r in protocol.records(pid) if r.get("condition")}
    assert conds == {("lung_nsclc", "mri_thorax_superior_sulcus"): "b", ("oral_cavity", "pet_ct"): "b", ("cervix", "ct_thorax"): "a",
                     ("cervix", "ihc"): "b", ("cervix", "mri_pelvis"): "b"}
    for pid, rid in conds:
        for setting in [None] + [s["id"] for s in protocol.settings(pid)]:
            for level in ("essential", "optimal"):
                rec = _rec(pid, rid)
                if protocol.tier_for(rec, setting) == "c":
                    assert not protocol.required(rec, setting, level), (pid, rid, setting, level)
