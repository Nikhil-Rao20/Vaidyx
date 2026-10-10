"""An unlisted Case File (V1 item 2.5: no protocol yet, gate None) gets a plain answer from every downstream module, never a
crash: summary and agents refuse without a model call, guideline look-ups are empty, the timeline and Q&A work, and a board
decision is stored with a not-listed flag. Model calls are replaced by fakes (or made to fail if called)."""
import asyncio

import pytest

from tumour_board import agents, guidelines, llm, postboard, qa, store, summary
from tumour_board.tests.util import PATIENT, add, fact, make_doc

CASE = "TB-U"


@pytest.fixture
def unlisted():
    store.create_case(CASE, {"name": "X", "mrn": "SYN-1"}, "", created_by="t")
    add(CASE, make_doc("Dhist0000", "histopathology", date="2026-09-01", facts={"histologic_type": fact("Adenocarcinoma")},
                       text="SYNTHETIC\nHISTOPATHOLOGY REPORT\nDiagnosis: Adenocarcinoma\nReport status: FINAL"))
    assert store.get_case(CASE)["listing"]["status"] == "awaiting_listing"
    return CASE


@pytest.fixture
def no_model(monkeypatch):
    async def boom(*a, **kw):
        raise AssertionError("no model call expected on an unlisted Case File")
    monkeypatch.setattr(llm, "chat", boom)


def test_summary_not_listed_without_model_call(unlisted, no_model):
    out = asyncio.run(summary.build(unlisted))
    assert out == {"status": "not_listed", "message": "This Case File is not listed yet: list it (cancer protocol, NCG setting, board date) before compiling the summary"}
    assert asyncio.run(summary.build(unlisted, force=True))["status"] == "not_listed"
    assert "summary" not in (store.get_state(unlisted).get("artefacts") or {})


def test_agent_yields_only_the_not_listed_error(unlisted, no_model):
    async def collect():
        return [e async for e in agents.run_agent(unlisted, "pathology")]
    assert asyncio.run(collect()) == [{"type": "error", "message": "This Case File is not listed yet: list it before preparing a brief"}]


def test_agent_tools_work_on_an_unlisted_case(unlisted):
    assert agents._gaps_text(unlisted) == "(not listed: no Pre-Authorization check yet)"
    assert "Adenocarcinoma" in agents._facts_text(unlisted)
    assert "Dhist0000" in agents._doc_list(unlisted)


def test_guideline_queries_empty_without_protocol(unlisted):
    assert guidelines.queries_for_case(unlisted) == []


def test_timeline_on_an_unlisted_case(unlisted):
    ev = postboard.timeline(unlisted)
    assert [(e["kind"], e["doc_id"]) for e in ev] == [("document", "Dhist0000")]


def test_board_decision_stored_with_not_listed_flag(unlisted, monkeypatch):
    async def fake_chat(role, msgs, **kw):
        return {"claims": [{"fact": "histologic_type", "value_as_written": "Adenocarcinoma", "span": "Adenocarcinoma"}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    rec = asyncio.run(postboard.record_decision(unlisted, {"decision_text": "Histology Adenocarcinoma. Plan agreed.", "participants": "Dr. A, Dr. B"}, user="t"))
    stored = store.get_state(unlisted)["board_records"]
    assert [r["id"] for r in stored] == [rec["id"]]
    adj = rec["adjudication"]
    assert {"kind": "consistency", "severity": "review", "text": "Case File not listed: no Pre-Authorization check to compare with"} in adj["flags"]
    assert not any("Pre-Authorization items were open" in f["text"] or f["text"].startswith("Decision record is missing") for f in adj["flags"])
    assert [c["result"] for c in adj["value_checks"]] == ["consistent"]  # the value check needs no protocol
    assert adj["status"] == "flag_for_expert_review"
    assert any(e["kind"] == "board" for e in postboard.timeline(unlisted))


def test_ask_answers_from_documents_on_an_unlisted_case(unlisted, monkeypatch):
    async def fake_chat(role, msgs, purpose="", **kw):
        if purpose == "scope check":
            return {"category": "in_scope", "reason": ""}
        return {"answer_found": True, "statements": [{"text": "The histopathology report records adenocarcinoma.",
                                                      "citations": [{"doc_id": "Dhist0000", "quote": "Diagnosis: Adenocarcinoma"}]}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    res = asyncio.run(qa.ask(unlisted, "What is the histology?"))
    assert res["status"] == "answered"
    assert res["statements"][0]["citations"][0]["doc_id"] == "Dhist0000"


def test_listed_case_still_compiles(unit_case, monkeypatch):
    """Guard: the not-listed path must not catch a listed Case File (gate not met is still reported as before)."""
    async def boom(*a, **kw):
        raise AssertionError("no model call while the gate is not met")
    monkeypatch.setattr(llm, "chat", boom)
    assert store.get_case(unit_case)["patient"] == PATIENT
    out = asyncio.run(summary.build(unit_case))
    assert out["status"] == "gate_not_met" and out["open"]
