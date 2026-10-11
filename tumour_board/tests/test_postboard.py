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
    acts = [a for a in store.get_state(unit_case)["actions"] if a.get("source") == "board"]
    assert [(a["department_id"], a["board_record"]) for a in acts] == [("radio_diagnosis", rec["id"]), ("medical_oncology", rec["id"])]
    sent = [n for n in notify._load() if n["kind"] == "board_action"]
    assert sorted(n["to"]["department"] for n in sent) == ["medical_oncology", "radio_diagnosis"]
    d = make_doc("Dmri00001", "mri", title="MRI PELVIS (SYNTHETIC)")
    d["added"] = "2999-01-01T00:00:00"  # arrived after the actions were created
    add(unit_case, d)
    service.recheck(unit_case, "tester")
    mri, counsel = [a for a in store.get_state(unit_case)["actions"] if a.get("source") == "board"]
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
    assert rec["resolution"]["final"] is False and rec["resolution"]["open"] == rec["resolution"]["total"] == len(rec["adjudication"]["flags"])
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
