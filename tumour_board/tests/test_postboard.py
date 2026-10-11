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
