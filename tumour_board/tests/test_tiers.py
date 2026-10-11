"""NCG tiers on the protocol records (V1 item 4.1): every required record names its NCG tier (a = Essential, b = Optimal,
c = Optional), per setting where NCG differs, with the verbatim NCG quote and page; the helpers decide what is required."""
import json

import pytest

from tumour_board import config, org, protocol

PIDS = ("lung_nsclc", "breast", "colorectal_rectum")


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
        assert org.department_id(r["department"]), (r["id"], r["department"])
        for k in ("tier_basis", "note"):
            assert "—" not in r.get(k, ""), r["id"]


def test_quotes_are_verbatim_from_the_research_note():
    note = config.PROTOCOL_DIR.parents[1] / "docs_Eswar" / "research" / "ncg_tiers_4.1.md"
    if not note.exists():
        pytest.skip("research note not in this checkout")
    text = note.read_text()
    for pid in PIDS:
        for r in protocol.records(pid):
            for src in r["sources"]:
                assert src["quote"] in text, (pid, r["id"], src["quote"])


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
    assert {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "baseline_labs"} <= req
    assert not req & {"pet_ct", "brain_mri", "pdl1", "met"}
    opt = {r["id"] for r in protocol.records("lung_nsclc") if protocol.required(r, "non_metastatic", "optimal")}
    assert {"pet_ct", "brain_mri", "pdl1", "met", "bronchoscopy", "mediastinal_staging"} <= opt
    assert "mri_thorax_superior_sulcus" not in opt
    assert protocol.tier_for(_rec("lung_nsclc", "brain_mri"), "metastatic") == "c"
    assert protocol.tier_for(_rec("lung_nsclc", "bronchoscopy"), "metastatic") == "none"
    assert "ct_thorax" not in {r["id"] for r in protocol.records("lung_nsclc")}


def test_breast_early_and_rectum_metastatic():
    assert protocol.tier_for(_rec("breast", "metastatic_workup"), "early") == "none"
    assert protocol.tier_for(_rec("breast", "baseline_labs"), "early") == "b"
    assert protocol.tier_for(_rec("breast", "baseline_labs"), "locally_advanced") == "a"
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
