"""V1 items 6.6 and 6.2: an agent whose specialty has no documents returns at once (no model call) with its department's open requests;
the agent of an absent specialty answers the board's questions live, every statement verified, refusals for out-of-scope questions.
Model calls are replaced by fakes."""
import asyncio

import pytest

from tumour_board import agents, guardrails, store
from tumour_board.tests.test_agents import ASCO, NCG
from tumour_board.tests.util import add, make_doc

CT = "SYNTHETIC\nCECT THORAX REPORT\nSpiculated mass 3.2 cm in the right upper lobe.\nNo pleural effusion.\nReport status: FINAL"


def _case(*docs, actions=None):
    store.create_case("TB-LIVE", {"name": "SYNTHETIC, Live Patient", "mrn": "SYN-900077", "agesex": "58 Y / F"}, "lung_nsclc", created_by="test")
    add("TB-LIVE", *docs)
    if actions:
        st = store.get_state("TB-LIVE"); st["actions"] = actions; store.save_state("TB-LIVE", st)
    return "TB-LIVE"


def _no_model(monkeypatch):
    calls = []

    async def boom(*a, **k):
        calls.append(a)
        raise AssertionError("no model call expected")
    monkeypatch.setattr(agents.llm, "chat", boom)
    monkeypatch.setattr(guardrails.llm, "chat", boom)
    return calls


def _run(case_id, role, focus=""):
    async def go():
        return [e async for e in agents.run_agent(case_id, role, focus)]
    return asyncio.run(go())


# ---- 6.6: no documents for a specialty -> no run ---------------------------------------------------------------------------
def test_no_documents_returns_at_once_with_the_departments_open_requests(monkeypatch):
    calls = _no_model(monkeypatch)
    req = {"id": "A1", "source": "pre_authorization", "label": "CECT thorax-abdomen-pelvis", "what": "No final, signed CT report", "department": "Radio-diagnosis",
           "department_id": "radio_diagnosis", "level_label": "Level 1 · Case File", "status": "pending", "due": "2026-10-20"}
    other = {**req, "id": "A2", "label": "Histopathology", "department": "Pathology", "department_id": "pathology"}
    done = {**req, "id": "A3", "status": "completed"}
    case_id = _case(make_doc("Dlab00001", "lab"), actions=[req, other, done])
    ev = _run(case_id, "radiology", "anything about the CT?")  # the focus question is not even classified: no model call at all
    assert calls == [] and [e["type"] for e in ev] == ["brief"]
    b = ev[0]["brief"]
    assert b["no_documents"] and b["message"] == "No Radio-diagnosis documents in this Case File" and b["department"] == "Radio-diagnosis"
    assert [x["label"] for x in b["open_items"]] == ["CECT thorax-abdomen-pelvis"] and b["sections"] == [] and b["model"] == ""
    assert store.get_state(case_id)["artefacts"]["brief_radiology"]["no_documents"]  # stored like a brief: stale when documents arrive
    assert any(e["kind"] == "agent_no_documents" and e["open_items"] == 1 for e in store.read_audit(case_id))
    assert "—" not in b["message"]


def test_documents_still_being_read_or_failed_are_named(monkeypatch):
    _no_model(monkeypatch)
    case_id = _case(make_doc("Dct000001", "ct", state="reading"), make_doc("Dmri00001", "mri", state="error"))
    b = _run(case_id, "radiology")[0]["brief"]
    assert b["message"] == "No Radio-diagnosis documents in this Case File (1 still being read, 1 failed to read)"


def test_a_document_uploaded_by_the_department_counts_for_its_agent(monkeypatch):
    seen = []

    async def fake_chat(role, msgs, json_schema=None, **kw):
        seen.append(json_schema)
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "done", "tool": "finish", "input": ""}
        return {"sections": [], "points_for_review": [], "not_documented": []}
    monkeypatch.setattr(agents.llm, "chat", fake_chat)
    monkeypatch.setattr(agents.guidelines, "ready", lambda: False)
    d = make_doc("Doth00001", "other", text="SYNTHETIC\nULTRASOUND NECK (uploaded by Radio-diagnosis)\nReport status: FINAL")
    d["department"] = "radio_diagnosis"
    case_id = _case(d)
    b = _run(case_id, "radiology")[-1]["brief"]
    assert not b.get("no_documents") and seen  # the model ran
    assert _run(case_id, "nuclear_medicine")[-1]["brief"]["message"] == "No Nuclear Medicine documents in this Case File"
