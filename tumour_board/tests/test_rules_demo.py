"""rules.evaluate on the synthetic demo Case Files TB-001 (lung), TB-002 (breast), TB-003 (rectum): today's gate results."""
from tumour_board import rules, store
from tumour_board.tests.util import req


def _statuses(g):
    return {r["id"]: r["status"] for r in g["requirements"]}


def test_tb001_lung_gate(demo_cases):
    """Essential-level hospital, NCG setting not recorded: the five NCG Essential records count; PET-CT, MRI brain, PD-L1, MET,
    bronchoscopy and mediastinal staging (Optimal) are shown, not required (V1 item 4.1)."""
    g = rules.evaluate("TB-001")
    assert _statuses(g) == {"clinical_history": "satisfied", "cect_tap": "satisfied", "histopathology": "not_final", "driver_mutations": "missing_field",
                            "baseline_labs": "missing_field"}
    assert {r["id"]: (r["tier"], r["status"]) for r in g["shown"]} == {
        "pdl1": ("b", "missing_field"), "met": ("b", "missing_field"), "pet_ct": ("b", "satisfied"), "brain_mri": ("b", "missing_record"),
        "bronchoscopy": ("b", "missing_record"), "mediastinal_staging": ("b", "missing_record"), "mri_thorax_superior_sulcus": ("c", "missing_record")}
    assert all(r["required"] for r in g["requirements"]) and not any(r["required"] for r in g["shown"])
    assert not g["passed"] and g["readiness"] == 40 and (g["satisfied"], g["total"]) == (2, 5)
    assert g["hospital_level"] == "essential" and g["setting"] == "" and g["protocol_version"] == "0.6"
    assert req(g, "histopathology")["problems"][0] == "HISTOPATHOLOGY REPORT is DRAFT and unsigned: a final, signed version is required"
    assert req(g, "baseline_labs")["problems"] == ['Pending: WBC count: "Not reported" in HAEMATOLOGY REPORT (CBC)']
    assert req(g, "cect_tap")["source"]["quote"] == "CECT Thorax, abdomen and Pelvis(a)" and req(g, "cect_tap")["source"]["page"] == 4
    assert next(r for r in g["shown"] if r["id"] == "brain_mri")["problems"] == ["No mri brain in the Case File"]
    # levels (V1 item 4.2): the draft histopathology and the molecular results with no final carrier are Level 1; the pending WBC is Level 2
    assert {r["id"]: r["level"] for r in g["requirements"]} == {"clinical_history": None, "cect_tap": None, "histopathology": 1, "driver_mutations": 1, "baseline_labs": 2}
    assert g["levels"] == {"1": {"label": "Level 1: Case File", "what": rules.LEVEL_WHAT[1], "open": 2}, "2": {"label": "Level 2: Records", "what": rules.LEVEL_WHAT[2], "open": 1}}
    assert req(g, "baseline_labs")["source_doc_id"] == "Dedaf7100" and req(g, "baseline_labs")["level2"]["status"] == "missing_field"
    assert req(g, "driver_mutations")["level1"]["problems"][0].startswith("No final, signed histopathology / ihc / molecular report in the Case File to carry: EGFR, ALK, ROS1")
    assert g["blockers"] == []
    assert g["documents"] == {"total": 8, "ready": 8, "processing": 0, "errors": 0, "failed": [], "dismissed": [], "non_final": ["D67977cf8"], "unconfirmed": [], "date_unconfirmed": [],
                              "date_flags": {}, "type_disagreements": [], "identity_flags": []}


def test_tb001_optimal_hospital_requires_the_optimal_records(demo_cases):
    c = store.get_case("TB-001"); c["hospital_level"] = "optimal"; store.save_case(c)
    g = rules.evaluate("TB-001")
    assert set(_statuses(g)) == {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "baseline_labs", "pdl1", "met", "pet_ct", "brain_mri", "bronchoscopy", "mediastinal_staging"}
    assert [r["id"] for r in g["shown"]] == ["mri_thorax_superior_sulcus"] and g["total"] == 11
    c["setting"] = "metastatic"; store.save_case(c)
    g = rules.evaluate("TB-001")  # metastatic: brain imaging is Optional (c), bronchoscopy not applicable, mediastinal staging Optional
    assert set(_statuses(g)) == {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "baseline_labs", "pdl1", "met", "pet_ct"}
    assert {r["id"]: r["tier"] for r in g["shown"]} == {"brain_mri": "c", "bronchoscopy": "none", "mediastinal_staging": "c", "mri_thorax_superior_sulcus": "c"}
    assert next(r for r in g["shown"] if r["id"] == "bronchoscopy")["status"] == "not_applicable"


def test_tb001_ct_evidence_is_the_newer_ct(demo_cases):
    """Two CT thorax reports (2025-11-10 prior, 2026-08-28): the newer one is the evidence."""
    r = req(rules.evaluate("TB-001"), "cect_tap")
    assert r["evidence"][0]["doc_id"] == "D41f9d46c"
    assert [e["doc_id"] for e in r["evidence"] if e.get("fact") == "lesion_size"] == ["D41f9d46c"]


def test_tb002_breast_gate_passes(demo_cases):
    g = rules.evaluate("TB-002")
    assert set(_statuses(g).values()) == {"satisfied"} and g["passed"] and g["readiness"] == 100 and g["total"] == 8  # setting not recorded: strictest tiers
    assert {r["id"]: (r["tier"], r["status"]) for r in g["shown"]} == {"grade": ("b", "satisfied"), "ki67": ("c", "satisfied"), "pet_ct": ("c", "missing_record"),
                                                                      "mri_breast": ("c", "satisfied"), "usg_axilla": ("b", "satisfied")}
    c = store.get_case("TB-002"); c["setting"] = "early"; store.save_case(c)
    g = rules.evaluate("TB-002")  # early breast cancer: no systemic staging (NCG B p6), labs Optimal
    assert set(_statuses(g)) == {"clinical_history", "breast_imaging", "histopathology", "receptor_status"} and g["passed"]
    assert {r["id"]: r["tier"] for r in g["shown"] if r["tier"] == "none"} == {"metastatic_workup": "none", "cect_chest_abdomen": "none", "bone_scan": "none"}
    assert g["documents"]["non_final"] == ["Db2c97640"]  # the preliminary IHC is superseded by the amended addendum


def test_tb002_receptor_values_come_from_the_amended_addendum(demo_cases):
    facts = rules.resolve_facts(store.list_docs("TB-002"))
    for fid in ("er", "pr", "her2", "ki67"):
        assert facts[fid]["current"]["doc_id"] == "D6ec09386", fid
        assert [h["doc_status"] for h in facts[fid]["history"]] == ["PRELIMINARY", "AMENDED"]


def test_tb003_rectum_gate_needs_restaging_mri(demo_cases):
    g = rules.evaluate("TB-003")
    s = _statuses(g)
    assert s.pop("restaging_mri") == "missing_record"
    assert s.pop("ras_braf") == "missing_field" and set(s.values()) == {"satisfied"}  # setting not recorded: RAS / BRAF counts (Essential in metastatic disease)
    r = req(g, "restaging_mri")
    assert r["postdate_reference"] == "2026-08-10" and r["level"] == 1
    assert r["problems"] == ["No restaging mri pelvis after neoadjuvant therapy in the Case File dated after 2026-08-10"]
    assert not g["passed"] and g["readiness"] == 78
    c = store.get_case("TB-003"); c["setting"] = "non_metastatic"; store.save_case(c)
    g = rules.evaluate("TB-003")  # non-metastatic: MMR / MSI and RAS / BRAF are Optional (colon flow), PET-CT and restaging CT Optional
    assert _statuses(g) == {"clinical_history": "satisfied", "endoscopy": "satisfied", "histopathology": "satisfied", "cea": "satisfied", "baseline_mri_pelvis": "satisfied",
                            "systemic_staging": "satisfied", "restaging_mri": "missing_record"}
    assert {r["id"]: r["tier"] for r in g["shown"]} == {"pet_ct": "c", "mmr": "c", "ras_braf": "c", "restaging_ct": "c"} and g["readiness"] == 86


def test_tb001_pending_values_are_current_from_the_draft(demo_cases):
    facts = rules.resolve_facts(store.list_docs("TB-001"))
    assert facts["pdl1"]["current"]["state"] == "pending" and facts["pdl1"]["current"]["doc_status"] == "DRAFT"
    assert facts["lesion_size"]["current"]["doc_id"] == "D4edcec61"  # PET/CT 2026-09-06 is the newest final value
    assert [h["date"] for h in facts["lesion_size"]["history"]] == sorted(h["date"] for h in facts["lesion_size"]["history"])


def test_tb001_actions_routed_by_department(demo_cases):
    st = rules.sync_actions("TB-001", rules.evaluate("TB-001"))
    assert {a["requirement"]: (a["department"], a["level"]) for a in st["actions"]} == {
        "histopathology": ("Pathology", 1), "driver_mutations": ("Molecular Pathology", 1), "baseline_labs": ("Laboratory Medicine", 2)}


def test_tb001_attesting_does_not_rescue_the_draft(demo_cases):
    rules.set_override("TB-001", "documents", "D67977cf8", {"attested_final": True}, by="Dr. Test")
    assert req(rules.evaluate("TB-001"), "histopathology")["status"] == "not_final"


def test_tb001_waivers_make_the_gate_pass(demo_cases):
    for rid in ("histopathology", "driver_mutations", "baseline_labs"):
        rules.set_override("TB-001", "requirements", rid, {"waived": True, "reason": "unit test"}, by="Dr. Test")
    g = rules.evaluate("TB-001")
    assert g["passed"] and (g["satisfied"], g["total"]) == (2, 2)
