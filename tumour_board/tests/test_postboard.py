"""After the board (V1 Phase 7): the decision record and its adjudication. Model calls are replaced by fakes.

7.1 PM-JAY board composition: HBP 2.2 asks for a Surgical, a Radiation and a Medical Oncologist on the tumour board; the check reads
the session's attendance, the members typed with their departments, or the participants text, and an AI support agent never counts."""
import asyncio
import json
import re
from pathlib import Path

import pytest

from tumour_board import llm, postboard

REPO = Path(__file__).resolve().parents[2]


def _no_claims(monkeypatch):
    async def fake_chat(role, msgs, **kw):
        return {"claims": []}
    monkeypatch.setattr(llm, "chat", fake_chat)


def _composition_flags(adj):
    return [f for f in adj["flags"] if f["kind"] == "composition"]


# ---- 7.1 PM-JAY board composition -----------------------------------------------------------------------------------
@pytest.mark.parametrize("text,missing", [
    ("Dr A (Med Onc), Dr B (Surg Onc), Dr C (Radiology), Dr D (Pathology)", ["radiation_oncology"]),
    ("Dr A (Rad Onc), Dr B (Medical Oncologist), Dr C (Oncosurgeon)", []),
    ("Dr. A. Rao (Medical Oncology), Surgical Oncology, Radiation Oncology; absent: Radio-diagnosis", []),
    ("Dr A (Medical Oncology), Dr B (Surgical Oncology); absent: Radiation Oncology", ["radiation_oncology"]),
    ("Dr X (Oncology), Dr Y (Surgical Oncology)", ["radiation_oncology", "medical_oncology"]),  # a bare "Oncology" says no specialty
    ("Radiation Oncology (AI support agent), Dr A (Med Onc), Dr B (Surg Onc)", ["radiation_oncology"]),  # an agent never counts
    ("Dr. P. Iyer (Radiotherapy), Dr A (Med. Onc.), Dr B (Surgical Oncologist)", []),
])
def test_composition_from_the_participants_text(text, missing):
    c = postboard.composition({"participants": text})
    assert c["checked"] and c["how"] == "participants text"
    assert c["missing"] == missing


def test_composition_not_checked_when_no_specialty_is_named():
    c = postboard.composition({"participants": "Dr A, Dr B"})
    assert not c["checked"] and c["missing"] == []
    f = postboard._composition_flag(c)
    assert f["severity"] == "review" and f["text"].startswith("PM-JAY board composition not checked")


def test_composition_from_the_session_attendance_ignores_the_agent_of_an_absent_specialty():
    att = {"present": ["Medical Oncology", "Pathology"], "absent": ["Radiation Oncology", "Radio-diagnosis"],
           "members": [{"name": "Dr. B. Shah", "department": "surgical_oncology", "department_name": "Surgical Oncology"}]}
    # the participants text names Radiation Oncology too, but the structured attendance wins: it was absent (its agent stood in)
    c = postboard.composition({"attendance": att, "participants": "Dr. B. Shah (Surgical Oncology), Medical Oncology, Radiation Oncology agent"})
    assert c["how"] == "attendance" and c["present"] == ["surgical_oncology", "medical_oncology"] and c["missing"] == ["radiation_oncology"]
    f = postboard._composition_flag(c)
    assert "no Radiation Oncologist recorded as present" in f["text"] and "does not count as a member" in f["text"]
    assert f["reference"]["region"] == "India" and f["reference"]["page"] == 27


def test_members_typed_on_the_board_tab_become_the_attendance():
    att = postboard.attendance_from_members([{"name": "Dr. A. Rao", "department": "Medical Oncology"}, {"name": "Dr. B", "department": "Radiotherapy"},
                                             {"name": " ", "department": "Pathology"}, {"name": "Dr. C", "department": "Oncosurgery"}])
    assert [m["department"] for m in att["members"]] == ["medical_oncology", "radiation_oncology", "surgical_oncology"]
    assert att["present"] == ["Medical Oncology", "Radiation Oncology", "Surgical Oncology"]
    assert postboard.composition({"attendance": att})["missing"] == []


def test_missing_radiation_oncologist_is_flagged_in_the_adjudication(unit_case, monkeypatch):
    _no_claims(monkeypatch)
    rec = {"decision_text": "Plan agreed.", "recorded_by": "Dr. Coordinator", "actions": [],
           "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Radiology)"}
    adj = asyncio.run(postboard.adjudicate(unit_case, rec))
    f = _composition_flags(adj)
    assert len(f) == 1 and f[0]["missing"] == ["radiation_oncology"] and adj["status"] == "flag_for_expert_review"
    assert adj["composition"]["present"] == ["surgical_oncology", "medical_oncology"]
    assert "participants" not in f[0]["text"].lower()  # the e2e's "participants recorded" check reads flag texts for that word


def test_full_pmjay_board_adds_no_composition_flag(unit_case, monkeypatch):
    _no_claims(monkeypatch)
    rec = {"decision_text": "Plan agreed.", "recorded_by": "Dr. Coordinator", "actions": [],
           "members": [{"name": "Dr. A", "department": "Surgical Oncology"}, {"name": "Dr. B", "department": "Radiation Oncology"},
                       {"name": "Dr. C", "department": "Medical Oncology"}]}
    out = asyncio.run(postboard.record_decision(unit_case, rec, "coordinator"))
    assert not _composition_flags(out["adjudication"]) and out["adjudication"]["composition"]["missing"] == []
    assert out["participants"] == "Dr. A (Surgical Oncology), Dr. B (Radiation Oncology), Dr. C (Medical Oncology)"
    assert "members" not in out and out["attendance"]["present"] == ["Surgical Oncology", "Radiation Oncology", "Medical Oncology"]


def test_typed_participants_are_kept_when_members_are_given(unit_case, monkeypatch):
    _no_claims(monkeypatch)
    rec = {"decision_text": "Plan agreed.", "participants": "As listed in the register", "members": [{"name": "Dr. A", "department": "Medical Oncology"}]}
    out = asyncio.run(postboard.record_decision(unit_case, rec, "coordinator"))
    assert out["participants"] == "As listed in the register"
    assert _composition_flags(out["adjudication"])[0]["missing"] == ["surgical_oncology", "radiation_oncology"]


def test_pmjay_reference_quote_is_on_its_page_of_the_hbp_manual():
    f = REPO / "data" / "tumour_board" / "embed_cache" / "guidelines_index.json"  # the real cache, read-only (tests run on a temporary root)
    if not f.exists():
        pytest.skip("guideline index cache not built")
    ref = postboard.PMJAY_REFERENCE
    norm = lambda t: re.sub(r"\s+", " ", t)
    pages = [c for c in json.loads(f.read_text())["chunks"] if c["file"] == ref["file"] and c["page"] == ref["page"]]
    assert any(norm(ref["quote"]) in norm(c["text"]) for c in pages)


# ---- 7.4 board actions go to department inboxes; a new matching document suggests closing --------------------------
def test_board_actions_reach_the_department_and_a_new_mri_suggests_closing(unit_case, monkeypatch):
    from tumour_board import notify, service, store
    from tumour_board.tests.util import add, make_doc
    _no_claims(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {"decision_text": "Plan agreed.", "participants": "Dr A (Med Onc)",
                                                            "actions": [{"department": "Radiology", "task": "MRI pelvis after neoadjuvant chemoradiation", "due": "2026-12-01"},
                                                                        {"department": "Medical Oncology", "task": "Counsel the patient"}]}, "coordinator"))
    acts = [a for a in store.get_state(unit_case)["actions"] if a.get("source") == "board" and not a.get("communication")]  # the typed actions (12 Oct: plus one 'inform the patient' follow-up)
    assert [(a["department_id"], a["board_record"]) for a in acts] == [("radiology", rec["id"]), ("medical_oncology", rec["id"])]
    sent = [n for n in notify._load() if n["kind"] == "board_action" and "Inform the patient" not in n["title"]]
    assert sorted(n["to"]["department"] for n in sent) == ["medical_oncology", "radiology"]
    d = make_doc("Dmri00001", "mri", title="MRI PELVIS (SYNTHETIC)")
    d["added"] = "2999-01-01T00:00:00"  # arrived after the actions were created
    add(unit_case, d)
    service.recheck(unit_case, "tester")
    mri, counsel = [a for a in store.get_state(unit_case)["actions"] if a.get("source") == "board" and not a.get("communication")]
    assert mri["suggested_close"]["doc_id"] == "Dmri00001" and mri["status"] != "completed" and "suggested_close" not in counsel
    au = [e for e in store.read_audit(unit_case) if e["kind"] == "board_action_suggested"]
    assert len(au) == 1 and au[0]["action_id"] == mri["id"] and au[0]["by"] == "tester"
    service.recheck(unit_case, "tester")  # the same suggestion found again: no new audit event or notification
    assert len([e for e in store.read_audit(unit_case) if e["kind"] == "board_action_suggested"]) == 1
    assert len([n for n in notify._load() if n["kind"] == "board_action_suggestion"]) == 1


# ---- 7.2 guideline checks in the adjudication: doses vs the cancer's references, stage vs the signed report -------------
TB005 = ("Neoadjuvant chemotherapy: 4 cycles of AC (Inj. Doxorubicin 6 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV, every 21 days), "
         "followed by Inj. Paclitaxel 80 mg/m2 IV weekly for 12 weeks. Clinical stage IIIA.")


def _breast_case(monkeypatch, stage_docs=()):
    from tumour_board import store
    from tumour_board.tests.util import add, fact, make_doc
    store.create_case("TB-BR7", {"name": "SYNTHETIC, Breast Patient", "mrn": "SYN-777", "agesex": "52 Y / F"}, "breast", created_by="test")
    for doc_id, doc_type, value, status in stage_docs:
        add("TB-BR7", make_doc(doc_id, doc_type, status=status, facts={"recorded_stage": fact(value)}))
    _no_claims(monkeypatch)
    return "TB-BR7"


def test_adjudication_flags_the_tenfold_dose_slip_with_its_indian_source(monkeypatch):
    cid = _breast_case(monkeypatch, [("Dnote0001", "clinical_note", "cT2 N1 M0, Stage IIB", "FINAL")])
    adj = asyncio.run(postboard.adjudicate(cid, {"decision_text": TB005, "recorded_by": "Dr. C", "actions": [],
                                                 "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"}))
    g = [f for f in adj["flags"] if f["kind"] == "guideline"]
    dose = [f for f in g if f["check"] == "dose"]
    assert len(dose) == 1 and dose[0]["severity"] == "expert_review" and "Doxorubicin" in dose[0]["text"]
    assert dose[0]["reference"]["region"] == "India" and dose[0]["reference"]["page"] and "60 mg/m2" in dose[0]["reference"]["quote"]
    assert dose[0]["span"] in TB005 and dose[0]["recorded"] == "6 mg/m2"
    ok = {c["drug"]: c["result"] for c in adj["guideline_checks"]["checks"] if c["kind"] == "drug"}
    assert ok == {"doxorubicin": "possible_transcription_error", "cyclophosphamide": "consistent", "paclitaxel": "consistent"}
    stage = [f for f in g if f["check"] == "stage"]
    assert len(stage) == 1 and stage[0]["severity"] == "review" and stage[0]["source"]["doc_id"] == "Dnote0001"
    assert adj["guideline_checks"]["ran"] is True and adj["status"] == "flag_for_expert_review"


def test_stage_comes_from_signed_reports_never_from_an_earlier_board_record(monkeypatch):
    from tumour_board import rules, store
    cid = _breast_case(monkeypatch, [("Dnote0001", "clinical_note", "Stage IIB", "DRAFT"), ("Dtbr0001", "tumour_board_record", "Stage IIIA", "FINAL")])
    facts = rules.resolve_facts(rules.case_docs(cid), {})
    assert postboard.recorded_stage(facts) is None  # a draft note and an earlier board record are not signed reports of the stage
    adj = asyncio.run(postboard.adjudicate(cid, {"decision_text": "Clinical stage IIIA. Plan agreed.", "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"}))
    assert not any(f.get("check") == "stage" for f in adj["flags"])
    assert [c["result"] for c in adj["guideline_checks"]["checks"] if c["kind"] == "stage"] == ["stage_not_compared"]


def test_information_only_items_do_not_flag_the_record(monkeypatch):
    cid = _breast_case(monkeypatch)
    adj = asyncio.run(postboard.adjudicate(cid, {"decision_text": "Inj. Paclitaxel 80 mg/m2 weekly; Inj. Pemetrexed 500 mg/m2.", "recorded_by": "Dr. C",
                                                 "actions": [{"department": "Medical Oncology", "task": "Counsel", "due": "2026-12-01"}],
                                                 "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"}))
    info = [f for f in adj["flags"] if f["kind"] == "guideline"]
    assert len(info) == 1 and info[0]["severity"] == "info" and "No guideline reference found: Pemetrexed" in info[0]["text"]  # a lung drug: no breast reference
    assert not any(f["severity"] in ("review", "expert_review") for f in adj["flags"]) and adj["status"] == "consistent"


def test_a_failing_guideline_check_never_stops_the_adjudication(monkeypatch):
    from tumour_board import dosecheck
    cid = _breast_case(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("references unreadable")
    monkeypatch.setattr(dosecheck, "check_decision", boom)
    adj = asyncio.run(postboard.adjudicate(cid, {"decision_text": TB005, "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"}))
    assert any(f["kind"] == "system" and "Guideline checks unavailable" in f["text"] for f in adj["flags"])
    assert adj["guideline_checks"]["ran"] is False and adj["status"] == "flag_for_expert_review"


# ---- 7.3 flag resolution: corrected (amended decision, versions kept) / intentional deviation / false alarm -------------
def _record_with_slip(unit_case, monkeypatch):
    """A board record whose PD-L1 is written as 6% where the signed report says 60%: one transcription flag, plus the composition
    flag (no oncologist named) and the missing 'recorded by' field."""
    from tumour_board import protocol
    from tumour_board.tests import util
    from tumour_board.tests.util import add, fact, make_doc
    unit = {**util.unit_protocol(), "post_board": {"required_record_fields": ["decision_text", "recorded_by", "participants", "actions"]}}
    real = protocol.get
    monkeypatch.setattr(protocol, "get", lambda pid: unit if pid == "unit" else real(pid))
    add(unit_case, make_doc("Dihc00000", "ihc", date="2026-09-05", facts={"pdl1": fact("TPS 60%", quote="PD-L1 (22C3) TPS 60%")},
                            text="SYNTHETIC\nIHC REPORT\nPD-L1 (22C3) TPS 60%\nReport status: FINAL"))

    async def fake_chat(role, msgs, **kw):
        return {"claims": [{"fact": "pdl1", "value_as_written": "TPS 6%", "span": "PD-L1 TPS 6%"}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    rec = asyncio.run(postboard.record_decision(unit_case, {"decision_text": "PD-L1 TPS 6% noted. Plan as discussed.", "participants": "Dr A, Dr B",
                                                            "actions": [{"department": "Medical Oncology", "task": "Counsel", "due": "2026-12-01"}]}, "coordinator"))
    flags = {f["kind"] if f["kind"] != "documentation" else f["field"]: f for f in rec["adjudication"]["flags"]}
    return rec, flags


def _rec(unit_case, rid):
    from tumour_board import store
    return next(b for b in store.get_state(unit_case)["board_records"] if b["id"] == rid)


def test_flags_have_ids_and_the_decision_is_not_final_until_resolved(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    assert [f["id"] for f in rec["adjudication"]["flags"]] == [f"F{i + 1}" for i in range(len(rec["adjudication"]["flags"]))]
    assert set(flags) >= {"transcription", "composition", "recorded_by"}
    need = [f for f in rec["adjudication"]["flags"] if postboard.needs_resolution(f)]  # information flags (patient-facing items, 12 Oct) need no resolution
    assert rec["resolution"]["final"] is False and rec["resolution"]["open"] == rec["resolution"]["total"] == len(need)
    assert rec["version"] == 1 and rec["versions"][0]["decision_text"] == rec["decision_text"]


def test_corrected_flag_amends_the_decision_as_version_2_with_history(unit_case, monkeypatch):
    from tumour_board import confirm, store
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    t = flags["transcription"]
    out = postboard.resolve_flag(unit_case, rec["id"], t["id"], "corrected", "TPS 60%", "", "Dr. Rao")
    assert out["decision_text"] == "PD-L1 TPS 60% noted. Plan as discussed." and out["version"] == 2
    assert [v["version"] for v in out["versions"]] == [1, 2] and out["versions"][0]["decision_text"] == "PD-L1 TPS 6% noted. Plan as discussed."
    assert out["versions"][1]["by"] == "Dr. Rao" and out["versions"][1]["change"] == {"flag": t["id"], "field": "decision_text", "at": 6, "from": "TPS 6%", "to": "TPS 60%"}
    f = next(x for x in out["adjudication"]["flags"] if x["id"] == t["id"])
    assert f["resolution"]["resolution"] == "corrected" and f["resolution"]["version"] == 2
    assert _rec(unit_case, rec["id"])["decision_text"] == out["decision_text"]  # saved
    c = confirm.latest(unit_case, "resolve_flag", f"{rec['id']}:{t['id']}")
    assert c and c["fields"] == {"resolution": "corrected", "value": "TPS 60%"} and c["by"] == "Dr. Rao"
    assert any(e["kind"] == "board_flag_resolved" and e["version"] == 2 for e in store.read_audit(unit_case))


def test_intentional_deviation_needs_a_reason_and_all_resolved_makes_the_decision_final(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    with pytest.raises(ValueError, match="reason"):
        postboard.resolve_flag(unit_case, rec["id"], flags["composition"]["id"], "intentional_deviation", "", "", "Dr. Rao")
    postboard.resolve_flag(unit_case, rec["id"], flags["composition"]["id"], "intentional_deviation", "", "Radiation Oncology reviewed the case file separately", "Dr. Rao")
    postboard.resolve_flag(unit_case, rec["id"], flags["transcription"]["id"], "false_alarm", "", "", "Dr. Rao")
    left = [f for f in _rec(unit_case, rec["id"])["adjudication"]["flags"] if postboard.needs_resolution(f) and not f.get("resolution")]
    for f in left:
        postboard.resolve_flag(unit_case, rec["id"], f["id"], "false_alarm", "", "", "Dr. Rao")
    r = _rec(unit_case, rec["id"])
    assert r["resolution"]["final"] is True and r["resolution"]["open"] == 0 and r["version"] == 1  # nothing corrected: same version


def test_undo_takes_the_correction_back_as_a_new_version(unit_case, monkeypatch):
    from tumour_board import confirm
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    t = flags["transcription"]
    out = postboard.resolve_flag(unit_case, rec["id"], t["id"], "corrected", "TPS 60%", "", "Dr. Rao")
    conf = next(x for x in out["adjudication"]["flags"] if x["id"] == t["id"])["resolution"]["confirmation"]
    back = postboard.undo_resolution(unit_case, conf, "Dr. Rao")
    assert back["decision_text"] == "PD-L1 TPS 6% noted. Plan as discussed." and back["version"] == 3 and len(back["versions"]) == 3
    f = next(x for x in back["adjudication"]["flags"] if x["id"] == t["id"])
    assert "resolution" not in f and f["resolution_history"][0]["undone_by"] == "Dr. Rao"
    assert confirm.latest(unit_case, "resolve_flag", f"{rec['id']}:{t['id']}") is None and back["resolution"]["final"] is False


def test_a_new_resolution_supersedes_and_takes_a_correction_back_first(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    t = flags["transcription"]
    postboard.resolve_flag(unit_case, rec["id"], t["id"], "corrected", "TPS 60%", "", "Dr. Rao")
    out = postboard.resolve_flag(unit_case, rec["id"], t["id"], "false_alarm", "", "6% is the value the board discussed", "Dr. Iyer")
    assert out["decision_text"] == "PD-L1 TPS 6% noted. Plan as discussed." and out["version"] == 3
    f = next(x for x in out["adjudication"]["flags"] if x["id"] == t["id"])
    assert f["resolution"]["resolution"] == "false_alarm" and f["resolution_history"][0]["resolution"] == "corrected"


def test_a_later_correction_survives_undoing_an_earlier_one(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    c1 = postboard.resolve_flag(unit_case, rec["id"], flags["transcription"]["id"], "corrected", "TPS 60%", "", "Dr. Rao")
    postboard.resolve_flag(unit_case, rec["id"], flags["recorded_by"]["id"], "corrected", "Dr. K. Menon, coordinator", "", "Dr. Rao")
    conf = next(x for x in c1["adjudication"]["flags"] if x["id"] == flags["transcription"]["id"])["resolution"]["confirmation"]
    back = postboard.undo_resolution(unit_case, conf, "Dr. Rao")
    assert back["decision_text"] == "PD-L1 TPS 6% noted. Plan as discussed." and back["recorded_by"] == "Dr. K. Menon, coordinator"


def test_composition_and_missing_field_corrections_amend_those_fields(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    out = postboard.resolve_flag(unit_case, rec["id"], flags["composition"]["id"], "corrected", "Dr. P. Iyer (Radiation Oncology)", "", "Dr. Rao")
    assert out["participants"] == "Dr A, Dr B; Dr. P. Iyer (Radiation Oncology)" and out["decision_text"] == rec["decision_text"] and out["version"] == 2
    out = postboard.resolve_flag(unit_case, rec["id"], flags["recorded_by"]["id"], "corrected", "Dr. K. Menon", "", "Dr. Rao")
    assert out["recorded_by"] == "Dr. K. Menon" and out["version"] == 3 and out["versions"][2]["recorded_by"] == "Dr. K. Menon"


def test_information_only_items_and_unknown_flags_are_refused(unit_case, monkeypatch):
    from tumour_board import store
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    st = store.get_state(unit_case)
    b = next(x for x in st["board_records"] if x["id"] == rec["id"])
    b["adjudication"]["flags"].append({"id": "F99", "kind": "guideline", "severity": "info", "text": "No guideline reference found"})
    store.save_state(unit_case, st)
    with pytest.raises(ValueError, match="information only"):
        postboard.resolve_flag(unit_case, rec["id"], "F99", "false_alarm", "", "", "Dr. Rao")
    with pytest.raises(KeyError):
        postboard.resolve_flag(unit_case, rec["id"], "F42", "false_alarm", "", "", "Dr. Rao")
    with pytest.raises(KeyError):
        postboard.resolve_flag(unit_case, "Bnope", "F1", "false_alarm", "", "", "Dr. Rao")
    with pytest.raises(ValueError, match="corrected value"):
        postboard.resolve_flag(unit_case, rec["id"], flags["transcription"]["id"], "corrected", "", "", "Dr. Rao")


def test_records_from_before_7_3_get_flag_ids_in_order(unit_case, monkeypatch):
    old = {"id": "Bold000", "decision_text": "x", "adjudication": {"flags": [{"kind": "documentation", "severity": "review", "text": "a"},
                                                                          {"kind": "system", "severity": "info", "text": "b"}]}}
    s = postboard.resolution_status(old)
    assert [f["id"] for f in old["adjudication"]["flags"]] == ["F1", "F2"] and s == {"final": False, "open": 1, "resolved": 0, "total": 1, "open_flags": ["F1"], "checks_complete": False}


# ---- review fixes (Phase 7): composition read from free text, amendments by position, safe undo, checks that did not run --------
@pytest.mark.parametrize("text", [
    "Dr A (Med Onc), Dr B (Surg Onc), absent: Dr C (Rad Onc)",
    "Present: Dr A (Med Onc), Dr B (Surg Onc). Absent: Dr C (Rad Onc)",
    "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc) - on leave",
    "Dr A (Med Onc), Dr B (Surg Onc), Rad Onc not present",
    "Dr A (Med Onc), Dr B (Surg Onc), Rad Onc (Agent)",
    "Dr A (Med Onc), Dr B (Surg Onc), Radiation Oncology Agent",
    "Absent: Dr C (Rad Onc); present: Dr A (Med Onc), Dr B (Surg Onc), Dr E (Radiotherapy)",  # both: a person checks it
])
def test_an_absent_or_agent_radiation_oncologist_is_never_read_as_present(text):
    assert postboard.composition({"participants": text})["missing"] == ["radiation_oncology"]


def test_a_member_named_as_an_agent_never_counts():
    att = {"present": ["Medical Oncology", "Surgical Oncology"], "members": [{"name": "Radiation Oncology Agent", "department": "radiation_oncology"}]}
    assert postboard.composition({"attendance": att})["missing"] == ["radiation_oncology"]


def test_present_heading_with_all_three_passes():
    assert postboard.composition({"participants": "Present: Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"})["missing"] == []


def _flag(fid, recorded, span=""):
    return {"id": fid, "kind": "guideline", "severity": "expert_review", "recorded": recorded, "span": span, "text": "x"}


def test_correction_replaces_only_the_whole_value_never_inside_a_longer_number():
    rec = {"decision_text": "Paclitaxel 140 mg/m2 then Docetaxel 40 mg/m2."}
    ch = postboard._amend(rec, _flag("F1", "40 mg/m2", "Docetaxel 40 mg/m2"), "75 mg/m2")
    assert rec["decision_text"] == "Paclitaxel 140 mg/m2 then Docetaxel 75 mg/m2." and ch["from"] == "40 mg/m2"


def test_correction_never_replaces_a_whole_span_when_the_value_is_not_in_it():
    rec = {"decision_text": "PD-L1 TPS 6% noted. Plan as discussed."}
    postboard._amend(rec, _flag("F1", "6 %", "PD-L1 TPS 6% noted"), "60%")
    assert rec["decision_text"] == "PD-L1 TPS 6% noted. Plan as discussed.\nAmendment (F1): 60%"


def test_overlapping_corrections_undo_in_any_order_or_refuse(unit_case, monkeypatch):
    from tumour_board import store
    text = "Inj. Trastuzumab 8 mg/kg loading followed by 60 mg/kg q 3 weekly."
    st = store.get_state(unit_case)
    st["board_records"] = [{"id": "Btz0001", "decision_text": text, "recorded_at": "2026-10-11T10:00:00", "entered_by": "c", "adjudication": {"flags": [
        _flag("F1", "8 mg/kg", "Trastuzumab 8 mg/kg"), _flag("F2", "60 mg/kg", "Trastuzumab 8 mg/kg loading followed by 60 mg/kg")]}}]
    store.save_state(unit_case, st)
    r = postboard.resolve_flag(unit_case, "Btz0001", "F2", "corrected", "6 mg/kg", "", "Dr. Rao")
    r = postboard.resolve_flag(unit_case, "Btz0001", "F1", "corrected", "8.0 mg/kg", "", "Dr. Rao")
    assert r["decision_text"] == "Inj. Trastuzumab 8.0 mg/kg loading followed by 6 mg/kg q 3 weekly."
    c2 = next(f for f in r["adjudication"]["flags"] if f["id"] == "F2")["resolution"]["confirmation"]
    back = postboard.undo_resolution(unit_case, c2, "Dr. Rao")  # the earlier correction, after a later one moved its position
    assert back["decision_text"] == "Inj. Trastuzumab 8.0 mg/kg loading followed by 60 mg/kg q 3 weekly." and "Amendment" not in back["decision_text"]


def test_undo_is_refused_when_a_later_correction_changed_the_same_words(unit_case, monkeypatch):
    from tumour_board import confirm, store
    st = store.get_state(unit_case)
    st["board_records"] = [{"id": "Bsame01", "decision_text": "Doxorubicin 6 mg/m2 IV.", "recorded_at": "2026-10-11T10:00:00", "entered_by": "c",
                            "adjudication": {"flags": [_flag("F1", "6 mg/m2", "Doxorubicin 6 mg/m2"), {**_flag("F2", "60 mg/m2"), "kind": "transcription"}]}}]
    store.save_state(unit_case, st)
    r = postboard.resolve_flag(unit_case, "Bsame01", "F1", "corrected", "60 mg/m2", "", "Dr. Rao")
    r = postboard.resolve_flag(unit_case, "Bsame01", "F2", "corrected", "50 mg/m2", "", "Dr. Rao")
    c1 = next(f for f in r["adjudication"]["flags"] if f["id"] == "F1")["resolution"]["confirmation"]
    with pytest.raises(ValueError, match="undo that one first"):
        postboard.undo_resolution(unit_case, c1, "Dr. Rao")
    assert confirm.latest(unit_case, "resolve_flag", "Bsame01:F1")["id"] == c1  # nothing was marked undone
    assert next(b for b in store.get_state(unit_case)["board_records"])["decision_text"] == "Doxorubicin 50 mg/m2 IV."


def test_a_correction_with_the_recorded_value_unchanged_is_refused(unit_case, monkeypatch):
    rec, flags = _record_with_slip(unit_case, monkeypatch)
    with pytest.raises(ValueError, match="same as the recorded one"):
        postboard.resolve_flag(unit_case, rec["id"], flags["transcription"]["id"], "corrected", "TPS 6%", "", "Dr. Rao")


def test_a_record_whose_check_did_not_run_is_never_final():
    rec = {"adjudication": {"flags": [{"kind": "system", "severity": "info", "text": "Guideline checks unavailable: timeout"}]}}
    s = postboard.resolution_status(rec)
    assert s["final"] is False and s["checks_complete"] is False and s["open"] == 0


def test_a_failing_closing_suggestion_never_breaks_the_recheck(unit_case, monkeypatch):
    from tumour_board import followup, service, store
    st = store.get_state(unit_case)
    st["actions"] = [{"id": "A1", "source": "board", "status": "pending", "what": "MRI pelvis", "created": "2026-10-01T10:00:00", "due": "2026-12-01", "history": []}]
    store.save_state(unit_case, st)

    def boom(*a, **k):
        raise RuntimeError("disk")
    monkeypatch.setattr(followup, "suggest_closures", boom)
    assert service.suggest_followups(unit_case, "tester") == []
    service.recheck(unit_case, "tester")  # does not raise
    assert any(e["kind"] == "error" and e["where"] == "board_action_suggestions" for e in store.read_audit(unit_case))


def test_recorded_stage_reads_the_figo_stage_too():
    """V1 item 9.2: the FIGO stage as recorded (cervix) is a stage as recorded for the guideline check; newest by date across both fields,
    never from a board record or an unverified value."""
    e = lambda v, date, **k: {"value": v, "quote": v, "doc_id": "D" + date, "doc_title": "t", "verification": "verified", "doc_final": True,
                              "state": "present", "doc_type": k.get("doc_type", "mri"), "date": date, "report_date": date}
    figo = {"figo_stage": {"history": [e("FIGO 2018 Stage IIB", "2026-09-15", doc_type="clinical_note"), e("IIB", "2026-09-17")]}}
    assert postboard.recorded_stage(figo)["value"] == "IIB"
    both = {**figo, "recorded_stage": {"history": [e("cT3 N0", "2026-09-10")]}}
    assert postboard.recorded_stage(both)["value"] == "IIB"
    later = {**figo, "recorded_stage": {"history": [e("Stage IIIB", "2026-09-20")]}}
    assert postboard.recorded_stage(later)["value"] == "Stage IIIB"
    board = {"figo_stage": {"history": [e("IIB", "2026-09-15"), e("IIIA", "2026-09-26", doc_type="tumour_board_record")]}}
    assert postboard.recorded_stage(board)["value"] == "IIB"
    assert postboard.recorded_stage({"recorded_stage": {"history": [e("cT2 N1", "2026-09-01")]}})["value"] == "cT2 N1"  # other cancers unchanged


# ---- night-v3 item 3.1: decision record v2 -----------------------------------------------------------------------------------
from tumour_board.tests.test_nik_meetings import As, app, owned, tc  # noqa: E402,F401  (the hermetic app and its logins)

DECISION = {"outcome": "decision", "decision_text": "Upfront surgery, then adjuvant chemotherapy.", "intent": "curative", "responsible_doctor": "Dr Priya Nair",
            "recorded_by": "Anil Kumar", "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)"}


def _comm(rec):
    return {f.get("field") for f in rec["adjudication"]["flags"] if f.get("kind") == "communication"}


def test_noted_raises_no_communication_flag_and_is_not_counted_as_a_decision(unit_case, monkeypatch):
    from tumour_board import metrics, store
    _no_claims(monkeypatch)
    n = asyncio.run(postboard.record_decision(unit_case, {"outcome": "noted", "decision_text": "Noted for information.", "board_date": "2026-10-27"}, "coord"))
    assert n["outcome_type"] == "noted" and _comm(n) == set() and not n.get("inform_by_date")
    assert not [a for a in store.get_state(unit_case)["actions"] if a.get("communication")]  # nobody has to tell the patient a noted case
    d = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "board_date": "2026-10-27"}, "coord"))
    after = metrics.dashboard()["kpis"]["after"]
    assert after["records"] == 2 and after["decisions"] == 1 and after["outcomes"] == {"noted": 1, "decision": 1}
    assert "intent_as_recorded" not in _comm(d)  # the intent choice clears the intent flag
    assert d["intent"] == d["intent_as_recorded"] == "curative"


def test_the_intent_choice_and_communication_fields_clear_their_flags(unit_case, monkeypatch):
    _no_claims(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "intent": "", "board_date": "2026-10-27"}, "coord"))
    assert "intent_as_recorded" in _comm(rec)
    out = postboard.update_communication(unit_case, rec["id"], {"intent": "palliative", "key_worker": "Sr Meena, 98450 00000", "trial_considered": "no",
                                                                 "consent_recorded": "yes", "gp_informed_date": "29/10/2026", "trial_name": ""}, user="coord")
    assert out["intent"] == out["intent_as_recorded"] == "palliative" and out["gp_informed_date"] == "2026-10-29" and out.get("version", 1) == 1
    assert _comm(out) == {"patient_informed_date"}
    # a date the patient was told before the board date is refused unless a reason is given
    with pytest.raises(ValueError, match="earlier than the board date"):
        postboard.update_communication(unit_case, rec["id"], {"patient_informed_date": "20/10/2026"}, user="coord")
    out = postboard.update_communication(unit_case, rec["id"], {"patient_informed_date": "20/10/2026", "reason": "Told in the clinic before the meeting"}, user="coord")
    assert out["patient_informed_date"] == "2026-10-20" and _comm(out) == set() and out["communication_history"][-1]["reason"].startswith("Told in the clinic")


def test_investigations_and_referrals_become_actions_in_the_department_inbox(unit_case, monkeypatch):
    from tumour_board import notify, store
    _no_claims(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "board_date": "2026-10-27",
        "investigations": [{"item": "PET-CT whole body", "department": "Nuclear Medicine", "due": "05/11/2026"}, {"item": "Echocardiogram", "department": ""}],
        "referrals": [{"kind": "genetics", "department": "Medical Genetics", "note": "BRCA testing and counselling"}, {"kind": "nutrition", "department": ""}]}, "coord"))
    acts = [a for a in store.get_state(unit_case)["actions"] if a.get("board_record") == rec["id"] and not a.get("communication")]
    assert [(a["kind"], a["label"], a["due"]) for a in acts][:1] == [("investigation", "PET-CT whole body", "2026-11-05")]
    assert [a["kind"] for a in acts] == ["investigation", "investigation", "referral"]  # a referral without a department is no action
    assert acts[1]["due"] and acts[1]["department_id"] is None  # the protocol's default due date; no Responsible Department
    assert acts[0]["department_id"] == "nuclear_medicine" and acts[2]["label"] == "Referral: Genetics and counselling, BRCA testing and counselling"
    sent = [n for n in notify._load() if n["kind"] == "board_action" and n.get("board_record") == rec["id"] and "Inform the patient" not in n["title"]]
    assert {n["to"].get("department") for n in sent} == {"nuclear_medicine", acts[2]["department_id"]} - {None}
    assert any(f["text"] == "Action 2 has no Responsible Department" for f in rec["adjudication"]["flags"])
    assert [x["kind"] for x in rec["actions"]] == ["investigation", "investigation", "referral"]


def test_who_tells_the_patient_and_by_when_default_at_save(unit_case, monkeypatch):
    _no_claims(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "board_date": "2026-10-31"}, "coord"))  # a Saturday
    assert rec["informed_by"] == "Dr Priya Nair" and rec["inform_by_date"] == "2026-11-03"  # Monday, Tuesday: the Sunday is skipped
    rec = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "board_date": "2026-10-31", "informed_by": "Dr Dev", "inform_by_date": "01/11/2026"}, "coord"))
    assert rec["informed_by"] == "Dr Dev" and rec["inform_by_date"] == "2026-11-01"  # what the board said is kept
    v1 = rec["versions"][0]
    assert v1["version"] == 1 and v1["fields"]["intent"] == "curative" and list(v1["fields"])[0] == "outcome"


def test_missing_actions_flag_only_for_a_decision_saying_nothing_about_what_happens_next(demo_cases, monkeypatch):
    _no_claims(monkeypatch)
    missing = lambda rec: [f for f in rec["adjudication"]["flags"] if f.get("text") == postboard.MISSING_ACTIONS]
    bare = asyncio.run(postboard.record_decision("TB-002", dict(DECISION), "coord"))
    assert len(missing(bare)) == 1
    nxt = asyncio.run(postboard.record_decision("TB-002", {**DECISION, "next_step": "Surgical Oncology OPD for consent"}, "coord"))
    noted = asyncio.run(postboard.record_decision("TB-002", {"outcome": "noted", "decision_text": "Noted.", "recorded_by": "Anil Kumar", "participants": "Dr A"}, "coord"))
    assert not missing(nxt) and not missing(noted)
    # a correction that adds an investigation clears the flag
    from tumour_board import store
    c = store.get_case("TB-002"); c["department"] = "breast_surgery"; store.save_case(c)
    out = postboard.correct_record("TB-002", bare["id"], {"investigations": [{"item": "MRI breast", "department": "Radiology"}]}, "priya", "Dr Priya Nair")
    assert not missing(out) and out["version"] == 2


def test_correct_record_keeps_every_version_and_tells_the_owner(demo_cases, monkeypatch):
    from tumour_board import notify, store
    _no_claims(monkeypatch)
    c = store.get_case("TB-002"); c["department"] = "breast_surgery"; store.save_case(c)
    rec = asyncio.run(postboard.record_decision("TB-002", {**DECISION, "board_date": "2026-10-27", "concerns": [{"by": "Dr Dev", "text": "Cardiac fitness"}]}, "anil"))
    with pytest.raises(ValueError, match="Give the reason for correcting decision, in the board's words"):
        postboard.correct_record("TB-002", rec["id"], {"decision_text": "Neoadjuvant chemotherapy, then surgery."}, "priya", "Dr Priya Nair")
    with pytest.raises(ValueError, match="Nothing changed"):
        postboard.correct_record("TB-002", rec["id"], {"decision_text": rec["decision_text"], "foo": "bar"}, "priya", "Dr Priya Nair", "x")
    with pytest.raises(ValueError, match="The outcome cannot be changed"):
        postboard.correct_record("TB-002", rec["id"], {"outcome": "deferred"}, "priya", "Dr Priya Nair", "x")
    with pytest.raises(ValueError, match="Choose the treatment intent"):  # the merged record must pass the meeting form's rule
        postboard.correct_record("TB-002", rec["id"], {"intent": ""}, "priya", "Dr Priya Nair", "cleared")
    out = postboard.correct_record("TB-002", rec["id"], {"key_worker": "Sr Meena, 98450 00000"}, "priya", "Dr Priya Nair")  # no reason needed
    assert out["version"] == 2 and out["key_worker"] == "Sr Meena, 98450 00000" and "key_worker" not in _comm(out)
    out = postboard.correct_record("TB-002", rec["id"], {"decision_text": "Neoadjuvant chemotherapy, then surgery.", "intent": "palliative",
                                                        "investigations": [{"item": "PET-CT", "department": "Nuclear Medicine", "due": "2026-11-10"}]},
                                   "priya", "Dr Priya Nair", "Dictation corrected after the meeting")
    assert out["version"] == 3 and out["decision_text"] == "Neoadjuvant chemotherapy, then surgery." and out["intent_as_recorded"] == "palliative"
    v1, v2, v3 = out["versions"]
    assert v1["decision_text"] == DECISION["decision_text"] and v1["fields"]["intent"] == "curative" and v1["fields"]["key_worker"] == ""  # never overwritten
    assert v2["change"] == "correction" and v2["changed"] == [{"key": "key_worker", "old": "", "new": "Sr Meena, 98450 00000"}] and v2["reason"]
    assert [x["key"] for x in v3["changed"]] == ["decision_text", "intent", "investigations"] and v3["changed"][1] == {"key": "intent", "old": "curative", "new": "palliative"}
    assert v3["fields"]["decision_text"] == out["decision_text"] and v3["by"] == "priya" and v3["by_name"] == "Dr Priya Nair"
    assert out["corrected"] == {"by": "priya", "by_name": "Dr Priya Nair", "at": v3["at"], "reason": "Dictation corrected after the meeting", "version": 3}
    acts = [a for a in store.get_state("TB-002")["actions"] if a.get("board_record") == rec["id"] and a.get("kind") == "investigation"]
    assert [(a["label"], a["department_id"], a["due"]) for a in acts] == [("PET-CT", "nuclear_medicine", "2026-11-10")]
    au = [e for e in store.read_audit("TB-002") if e["kind"] == "board_record_corrected"]
    assert [e["version"] for e in au] == [2, 3] and au[-1]["changed"] == ["decision_text", "intent", "investigations"] and au[-1]["reason"].startswith("Dictation")
    told = [n for n in notify._load() if n["kind"] == "outcome" and n["title"].startswith("Board record corrected for")]
    assert told and told[-1]["to"] == {"department": "breast_surgery"} and told[-1]["version"] == 3
    # the same investigation again is no new action
    out = postboard.correct_record("TB-002", rec["id"], {"investigations": out["investigations"] + [{"item": "Echo", "department": "Cardiology"}]}, "priya", "Dr Priya Nair")
    assert [a["label"] for a in store.get_state("TB-002")["actions"] if a.get("board_record") == rec["id"] and a.get("kind") == "investigation"] == ["PET-CT", "Echo"]


def test_correct_route_who_may_correct(tc):
    from datetime import date, timedelta
    from tumour_board import store
    owned("TB-002")
    today = date.today().isoformat()
    rec = asyncio.run(postboard.record_decision("TB-002", {**DECISION, "board_date": today}, "anil"))
    url = f"/cases/TB-002/board-records/{rec['id']}/correct"
    body = {"changes": {"key_worker": "Sr Meena"}}
    r = As(tc, "asha").post(url, json=body)  # a resident of the team
    assert r.status_code == 403 and "Only the owning department's consultants can correct a board record" in r.text
    assert As(tc, "ravi").post(url, json=body).status_code == 403  # a consultant of another department
    r = As(tc, "priya").post(url, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["record"]["version"] == 2 and r.json()["record"]["corrected"]["by_name"] == "Dr Priya Nair"
    r = As(tc, "anil").post(url, json={"changes": {"key_worker": "Sr Meena, 98450 00000"}})  # the MDT Coordinator on the meeting day
    assert r.status_code == 200, r.text
    assert As(tc, "priya").post(url, json={"changes": {"decision_text": "Surgery alone."}}).status_code == 400  # a reason is needed
    assert As(tc, "priya").post(url, json={"key_worker": "x"}).status_code == 400
    assert As(tc, "priya").post(f"/cases/TB-002/board-records/Bnope/correct", json=body).status_code == 404
    st = store.get_state("TB-002")
    next(b for b in st["board_records"] if b["id"] == rec["id"])["board_date"] = (date.today() - timedelta(days=1)).isoformat()
    store.save_state("TB-002", st)
    r = As(tc, "anil").post(url, json={"changes": {"key_worker": "Sr Lata"}})  # the day after
    assert r.status_code == 403 and "on the meeting day only" in r.text
    r = As(tc, "priya").post(url, json={"changes": {"key_worker": "Sr Lata"}})
    assert r.status_code == 200 and r.json()["record"]["version"] == 4


def test_decision_fields_route_returns_the_spec(tc):
    from tumour_board import decision_record
    r = As(tc, "priya").get("/meetings/decision-fields")
    assert r.status_code == 200 and r.json() == decision_record.spec()
    tc.cookies.clear()
    assert tc.get("/api/tb/meetings/decision-fields").status_code in (401, 403)


def test_fhir_care_plan_notes_carry_the_new_fields(unit_case, monkeypatch):
    from tumour_board import fhir_export
    _no_claims(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {**DECISION, "board_date": "2026-10-31", "modalities": ["surgery", "chemotherapy"], "sequence": "Surgery then adjuvant chemotherapy",
                                                            "alternatives_discussed": "Neoadjuvant chemotherapy", "stage_as_agreed": "pT2 N1", "stage_source": "board",
                                                            "trial_considered": "yes", "trial_name": "CTRI/2026/01/000001", "referrals": [{"kind": "fertility", "department": "Gynaecology"}],
                                                            "pmjay_plan_approval": "yes", "pmjay_plan_note": "PA-77", "key_worker": "Sr Meena"}, "coord"))
    deferred = asyncio.run(postboard.record_decision(unit_case, {"outcome": "deferred", "awaited": "IHC", "awaited_from": "Pathology", "decision_text": "Deferred."}, "coord"))
    plans = {r["resource"]["id"]: r["resource"] for r in fhir_export.bundle(unit_case)["entry"] if r["resource"]["resourceType"] == "CarePlan"}
    plan = next(p for p in plans.values() if p["description"] == DECISION["decision_text"])
    notes = [n["text"] for n in plan["note"]]
    for line in ("Treatment intent: Curative", "Modalities: Surgery, Chemotherapy", "Sequence: Surgery then adjuvant chemotherapy", "Alternatives discussed: Neoadjuvant chemotherapy",
                 "Stage as agreed by the board: pT2 N1 (The board's own)", "Clinical trial considered: Yes (CTRI/2026/01/000001)", "Referrals: Fertility preservation (Gynaecology)",
                 "PM-JAY treatment plan approval: Yes (PA-77)", "Responsible clinician: Dr Priya Nair", "Key worker: Sr Meena",
                 "Who tells the patient: Dr Priya Nair (by 03/11/2026)"):
        assert line in notes, (line, notes)
    assert plan["status"] == "active" and "Decision recorded" in plan["title"]
    other = next(p for p in plans.values() if p["description"] == "Deferred.")
    assert other["status"] == "draft" and "Deferred: information awaited" in other["title"] and deferred["deferred_reason"] == "IHC (from Pathology)"


def test_the_old_routes_stay_lenient_and_take_the_new_keys(tc):
    owned("TB-002")
    r = As(tc, "anil").post("/cases/TB-002/board-records", json={"decision_text": "Plan agreed.", "modalities": ["Surgery"], "investigations": [{"item": "MRI breast", "department": "Radiology"}]})
    assert r.status_code == 200, r.text
    assert r.json()["outcome_type"] == "decision" and r.json()["intent"] == "" and r.json()["modalities"] == ["surgery"] and r.json()["actions"][0]["kind"] == "investigation"
    r = As(tc, "anil").post("/cases/TB-002/board-records", json={"decision_text": "Plan agreed.", "sequence": "x" * 301})
    assert r.status_code == 400 and "Sequence: at most 300 characters" in r.text


def test_case_file_view_says_who_may_correct_each_board_record(tc):
    """night-v3 item 3.2: permissions.correct_board_record follows the correct route's rule (one helper for both)."""
    from datetime import date, timedelta
    from tumour_board import store
    owned("TB-002")
    rec = asyncio.run(postboard.record_decision("TB-002", {**DECISION, "board_date": date.today().isoformat()}, "anil"))
    may = lambda user: As(tc, user).get("/cases/TB-002").json()["permissions"]["correct_board_record"][rec["id"]]
    assert may("priya") is True and may("anil") is True  # the owner's consultant; the MDT Coordinator on the meeting day
    assert may("asha") is False  # a resident of the team
    st = store.get_state("TB-002")
    next(b for b in st["board_records"] if b["id"] == rec["id"])["board_date"] = (date.today() - timedelta(days=1)).isoformat()
    store.save_state("TB-002", st)
    assert may("anil") is False and may("priya") is True  # the day after: only the owner's consultant
    assert As(tc, "anil").post(f"/cases/TB-002/board-records/{rec['id']}/correct", json={"changes": {"key_worker": "Sr Lata"}}).status_code == 403  # the route agrees
