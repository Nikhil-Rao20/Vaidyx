"""V2 item 4.1: the comparison logic of the live scenario check (tumour_board/eval/his_scenarios.py). No network, no model: the
expectations come from the SYNTHETIC fixture his_mock/scenarios.json, the gates and actions are hand-made."""
import copy

from tumour_board.eval import his_scenarios as hs

FIXTURE = hs.load_fixture()
EXPS = hs.expectations(FIXTURE)


def _exp(slot, protocol):
    return copy.deepcopy(next(e for e in EXPS if e["slot"] == slot and e["protocol"] == protocol))


def _gate(exp, overrides=None, extra=None):
    """The gate the fixture expects: every expected gap open at its level with its accession, plus one met record."""
    reqs = [{"id": "clinical_history", "status": "satisfied", "level": None, "department": "X"}]
    for rid, g in exp["gaps"].items():
        reqs.append({"id": rid, "status": "missing_record" if g["level"] == 1 else "missing_field", "level": g["level"],
                     "accession": g.get("accession"), "department": g.get("department")})
    for r in reqs:
        r.update((overrides or {}).get(r["id"]) or {})
    return {"passed": not exp["gaps"], "requirements": reqs + (extra or [])}


def _actions(exp, status="pending"):
    return [{"id": f"A{i}", "source": "pre_authorization", "requirement": r["requirement"], "department": r["department"], "level": r["level"],
             "accession": r.get("accession"), "status": status} for i, r in enumerate(exp["requests"])]


def test_one_expectation_per_case_file_twenty_five_in_all():
    assert len(EXPS) == 25  # 21 before night-v3 item 2.11 added the four Phase 2 patients (P20 to P23)
    slots = [e["slot"] for e in EXPS]
    assert len(set(slots)) == 23 and slots.count("P14") == 2 and slots.count("P18") == 2
    assert len({e["case_id"] for e in EXPS}) == 25
    assert all(e["case_id"].startswith("TB-SCN-") and e["case_id"] != "TB-2026-bharath" for e in EXPS)


def test_expectations_carry_owner_setting_level_and_accession():
    e = _exp("P12", "lung_nsclc")
    assert (e["uhid"], e["setting"], e["owner"], e["result"]) == ("VXH/26/004212", "non_metastatic", "Medical Oncology", "gaps")
    assert e["gaps"] == {"cect_tap": {"level": 1, "accession": "RAD/26/01004", "department": "Radiology", "reason": "preliminary"}}
    assert e["requests"] == [{"requirement": "cect_tap", "department": "Radiology", "level": 1, "accession": "RAD/26/01004", "scenario": e["requests"][0]["scenario"]}]
    assert "radiology_preliminary_only" in e["scenarios"] and e["basis"] == "first_fetch"


def test_doctor_initiated_requests_are_not_expected_from_the_gate():
    assert all(r["requirement"] for e in EXPS for r in e["requests"])
    assert _exp("P07", "oral_cavity")["requests"] == [] and _exp("P07", "oral_cavity")["result"] == "pass"
    p15 = _exp("P15", "lung_nsclc")
    assert sorted(r["requirement"] for r in p15["requests"]) == ["driver_mutations", "met"]  # not the medication review


def test_requests_repeated_across_scenarios_are_expected_once():
    for e in EXPS:
        reqs = [r["requirement"] for r in e["requests"]]
        assert len(reqs) == len(set(reqs)), e["case_id"]


def test_p14_requests_belong_to_the_colorectal_case_file():
    lung, crc = _exp("P14", "lung_nsclc"), _exp("P14", "colorectal_rectum")
    assert lung["requests"] == [] and len(lung["gaps"]) == 5
    assert sorted(r["requirement"] for r in crc["requests"]) == ["baseline_mri_pelvis", "cea", "mmr", "ras_braf"]
    assert crc["basis"] == "case_files.first_fetch"  # the colorectal gate is an after_referral entry: the same records, the same gaps


def test_only_filters_by_patient_slot():
    got = hs.expectations(FIXTURE, ["p12", " P18"])
    assert [(e["slot"], e["protocol"]) for e in got] == [("P12", "lung_nsclc"), ("P18", "colorectal_rectum"), ("P18", "breast")]


def test_every_expectation_matches_itself():
    for e in EXPS:
        res = hs.compare(e, _gate(e), _actions(e))
        assert res["ok"], (e["case_id"], res["differences"])


def test_request_status_is_never_compared():
    e = _exp("P12", "lung_nsclc")
    for status in ("pending", "suggested", "overdue", "sent"):
        assert hs.compare(e, _gate(e), _actions(e, status))["ok"]


def test_completed_actions_are_not_open_requests():
    e = _exp("P12", "lung_nsclc")
    res = hs.compare(e, _gate(e), _actions(e, "completed"))
    assert not res["ok"] and res["differences"] == ["request cect_tap: no open Pre-Authorization request (expected to Radiology)"]


def test_gap_met_instead_of_open():
    e = _exp("P11", "cervix")
    res = hs.compare(e, _gate(e, {"histopathology": {"status": "satisfied", "level": None}}), _actions(e))
    assert not res["ok"]
    assert "histopathology: expected a Level 1 gap, got met (satisfied)" in res["differences"]
    assert "gate has gaps, expected gaps" not in res["differences"]


def test_gate_passed_when_gaps_were_expected():
    e = _exp("P11", "cervix")
    g = _gate(e); g["passed"] = True
    assert "gate passed, expected gaps" in hs.compare(e, g, _actions(e))["differences"]


def test_wrong_level_and_wrong_accession():
    e = _exp("P15", "lung_nsclc")
    res = hs.compare(e, _gate(e, {"met": {"level": 1, "status": "missing_record"}, "driver_mutations": {"accession": "PATH/26/99999"}}), _actions(e))
    assert "met: expected a Level 2 gap, got Level 1 (missing_record)" in res["differences"]
    assert "driver_mutations: expected accession PATH/26/00451, got PATH/26/99999" in res["differences"]


def test_unexpected_gap_and_unexpected_request():
    e = _exp("P01", "breast")
    extra = [{"id": "cbc", "status": "not_final", "level": 1, "accession": "PATH/26/00413"}]
    acts = [{"source": "pre_authorization", "requirement": "cbc", "department": "Pathology", "level": 1, "status": "pending"},
            {"source": "board", "requirement": None, "status": "pending"}]
    g = _gate(e, extra=extra); g["passed"] = False
    res = hs.compare(e, g, acts)
    assert res["differences"] == ["gate has gaps, expected pass", "cbc: unexpected Level 1 gap (not_final)",
                                  "request cbc: unexpected open Pre-Authorization request to Pathology"]


def test_expected_record_absent_from_the_gate():
    e = _exp("P13", "lung_nsclc")
    g = _gate(e); g["requirements"] = [r for r in g["requirements"] if r["id"] != "bronchoscopy"]
    assert "bronchoscopy: expected a Level 1 gap, not a required record in this gate" in hs.compare(e, g, _actions(e))["differences"]


def test_request_routing_level_and_accession():
    e = _exp("P04", "breast")
    acts = _actions(e)
    acts[0].update(department="Radiology", level=2, accession=None)
    d = hs.compare(e, _gate(e), acts)["differences"]
    assert d == ["request bone_scan: routed to Radiology, expected Nuclear Medicine", "request bone_scan: Level 2, expected Level 1",
                 "request bone_scan: accession none, expected NM/26/00152"]


def test_accession_the_fixture_does_not_name_is_a_note_not_a_mismatch():
    e = _exp("P13", "lung_nsclc")
    acts = _actions(e); acts[0]["accession"] = "PUL/26/00001"
    res = hs.compare(e, _gate(e, {"bronchoscopy": {"accession": "PUL/26/00001"}}), acts)
    assert res["ok"] and len(res["notes"]) == 2


def test_no_gate_is_a_mismatch():
    res = hs.compare(_exp("P01", "breast"), None, [])
    assert not res["ok"] and res["actual"] is None


def test_lines_and_summary():
    e = _exp("P12", "lung_nsclc")
    ok = hs.compare(e, _gate(e), _actions(e))
    assert hs.line(e, ok).startswith("OK  P12 lung_nsclc (non_metastatic) TB-SCN-P12-lung-nsclc: cect_tap L1; 1 request(s)")
    bad = hs.compare(e, _gate(e), [])
    assert hs.line(e, bad).startswith("MISMATCH  P12 ") and "no open Pre-Authorization request" in hs.line(e, bad)
    assert hs.summary([ok, ok]) == ("SCENARIOS OK: 2 Case Files checked", 0)
    assert hs.summary([ok, bad]) == ("SCENARIOS FAILED: 1 of 2", 1)


def test_unknown_slot_exits_before_touching_anything(capsys):
    assert hs.main(["--only", "P99"]) == 2
    assert "No Case File" in capsys.readouterr().err
