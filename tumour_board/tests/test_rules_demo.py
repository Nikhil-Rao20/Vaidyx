"""rules.evaluate on the synthetic demo Case Files TB-001 (lung), TB-002 (breast), TB-003 (rectum): today's gate results."""
from tumour_board import rules, store
from tumour_board.tests.util import req


def _statuses(g):
    return {r["id"]: r["status"] for r in g["requirements"]}


def test_tb001_lung_gate(demo_cases):
    g = rules.evaluate("TB-001")
    assert _statuses(g) == {"clinical_history": "satisfied", "ct_thorax": "satisfied", "pet_ct": "satisfied", "brain_mri": "missing_record",
                            "histopathology": "not_final", "pdl1": "missing_field", "driver_mutations": "missing_field", "baseline_labs": "missing_field"}
    assert not g["passed"] and g["readiness"] == 38 and (g["satisfied"], g["total"]) == (3, 8)
    assert req(g, "histopathology")["problems"][0] == "HISTOPATHOLOGY REPORT is DRAFT and unsigned: a final, signed version is required"
    assert req(g, "pdl1")["problems"] == ['Pending: PD-L1: "Pending" in HISTOPATHOLOGY REPORT']
    assert req(g, "baseline_labs")["problems"] == ['Pending: WBC count: "Not reported" in HAEMATOLOGY REPORT (CBC)']
    assert req(g, "brain_mri")["problems"] == ["No brain mri (staging) in the Case File"]
    assert g["documents"] == {"total": 8, "ready": 8, "processing": 0, "errors": 0, "non_final": ["D67977cf8"], "unconfirmed": [], "date_unconfirmed": [], "date_flags": {}, "identity_flags": []}


def test_tb001_ct_evidence_is_the_newer_ct(demo_cases):
    """Two CT thorax reports (2025-11-10 prior, 2026-08-28): the newer one is the evidence."""
    r = req(rules.evaluate("TB-001"), "ct_thorax")
    assert r["evidence"][0]["doc_id"] == "D41f9d46c"
    assert [e["doc_id"] for e in r["evidence"] if e.get("fact") == "lesion_size"] == ["D41f9d46c"]


def test_tb002_breast_gate_passes(demo_cases):
    g = rules.evaluate("TB-002")
    assert set(_statuses(g).values()) == {"satisfied"} and g["passed"] and g["readiness"] == 100 and g["total"] == 6
    assert g["documents"]["non_final"] == ["Db2c97640"]  # the preliminary IHC is superseded by the amended addendum


def test_tb002_receptor_values_come_from_the_amended_addendum(demo_cases):
    facts = rules.resolve_facts(store.list_docs("TB-002"))
    for fid in ("er", "pr", "her2", "ki67"):
        assert facts[fid]["current"]["doc_id"] == "D6ec09386", fid
        assert [h["doc_status"] for h in facts[fid]["history"]] == ["PRELIMINARY", "AMENDED"]


def test_tb003_rectum_gate_needs_restaging_mri(demo_cases):
    g = rules.evaluate("TB-003")
    s = _statuses(g)
    assert s.pop("restaging_mri") == "missing_record" and set(s.values()) == {"satisfied"}
    r = req(g, "restaging_mri")
    assert r["postdate_reference"] == "2026-08-10"
    assert r["problems"] == ["No restaging mri pelvis after neoadjuvant therapy in the Case File dated after 2026-08-10"]
    assert not g["passed"] and g["readiness"] == 88


def test_tb001_pending_values_are_current_from_the_draft(demo_cases):
    facts = rules.resolve_facts(store.list_docs("TB-001"))
    assert facts["pdl1"]["current"]["state"] == "pending" and facts["pdl1"]["current"]["doc_status"] == "DRAFT"
    assert facts["lesion_size"]["current"]["doc_id"] == "D4edcec61"  # PET/CT 2026-09-06 is the newest final value
    assert [h["date"] for h in facts["lesion_size"]["history"]] == sorted(h["date"] for h in facts["lesion_size"]["history"])


def test_tb001_actions_routed_by_department(demo_cases):
    st = rules.sync_actions("TB-001", rules.evaluate("TB-001"))
    assert {a["requirement"]: a["department"] for a in st["actions"]} == {
        "brain_mri": "Radiology", "histopathology": "Pathology", "pdl1": "Pathology", "driver_mutations": "Molecular Pathology",
        "baseline_labs": "Laboratory Medicine"}


def test_tb001_attesting_does_not_rescue_the_draft(demo_cases):
    rules.set_override("TB-001", "documents", "D67977cf8", {"attested_final": True}, by="Dr. Test")
    assert req(rules.evaluate("TB-001"), "histopathology")["status"] == "not_final"


def test_tb001_waivers_make_the_gate_pass(demo_cases):
    for rid in ("brain_mri", "histopathology", "pdl1", "driver_mutations", "baseline_labs"):
        rules.set_override("TB-001", "requirements", rid, {"waived": True, "reason": "unit test"}, by="Dr. Test")
    g = rules.evaluate("TB-001")
    assert g["passed"] and (g["satisfied"], g["total"]) == (3, 3)
