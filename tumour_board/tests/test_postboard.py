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
