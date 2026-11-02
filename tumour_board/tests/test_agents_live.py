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
           "department_id": "radiology", "level_label": "Level 1 · Case File", "status": "pending", "due": "2026-10-20"}
    other = {**req, "id": "A2", "label": "Histopathology", "department": "Pathology", "department_id": "pathology"}
    done = {**req, "id": "A3", "status": "completed"}
    case_id = _case(make_doc("Dlab00001", "lab"), actions=[req, other, done])
    ev = _run(case_id, "radiology", "anything about the CT?")  # the focus question is not even classified: no model call at all
    assert calls == [] and [e["type"] for e in ev] == ["brief"]
    b = ev[0]["brief"]
    assert b["no_documents"] and b["message"] == "No Radiology documents in this Case File" and b["department"] == "Radiology"
    assert [x["label"] for x in b["open_items"]] == ["CECT thorax-abdomen-pelvis"] and b["sections"] == [] and b["model"] == ""
    assert store.get_state(case_id)["artefacts"]["brief_radiology"]["no_documents"]  # stored like a brief: stale when documents arrive
    assert any(e["kind"] == "agent_no_documents" and e["open_items"] == 1 for e in store.read_audit(case_id))
    assert "—" not in b["message"]


def test_documents_still_being_read_or_failed_are_named(monkeypatch):
    _no_model(monkeypatch)
    case_id = _case(make_doc("Dct000001", "ct", state="reading"), make_doc("Dmri00001", "mri", state="error"))
    b = _run(case_id, "radiology")[0]["brief"]
    assert b["message"] == "No Radiology documents in this Case File (1 still being read, 1 failed to read)"


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
    d["department"] = "radiology"
    case_id = _case(d)
    b = _run(case_id, "radiology")[-1]["brief"]
    assert not b.get("no_documents") and seen  # the model ran
    assert _run(case_id, "nuclear_medicine")[-1]["brief"]["message"] == "No Nuclear Medicine documents in this Case File"


# ---- 6.2: live answers ----------------------------------------------------------------------------------------------------
@pytest.fixture
def pack(monkeypatch):
    monkeypatch.setattr(agents.packs, "search", lambda role, q, cancer=None, india=3, intl=2: {"india": [NCG][:india], "international": [ASCO][:intl]})
    monkeypatch.setattr(agents.guidelines, "ready", lambda: True)


def _live(monkeypatch, answer, category="in_scope"):
    prompts = []

    async def fake_chat(role, msgs, json_schema=None, **kw):
        if json_schema is guardrails.CLASSIFIER_SCHEMA:
            return {"category": category, "reason": "test"}
        prompts.append(msgs)
        return answer
    monkeypatch.setattr(agents.llm, "chat", fake_chat)
    monkeypatch.setattr(guardrails.llm, "chat", fake_chat)
    return prompts


def test_live_answer_is_cited_and_unverified_statements_are_kept_aside(monkeypatch, pack):
    case_id = _case(make_doc("Dct000001", "ct", text=CT))
    prompts = _live(monkeypatch, {"answer_found": True, "statements": [
        {"text": "The CECT thorax records a spiculated mass of 3.2 cm in the right upper lobe.", "citations": [{"doc_id": "Dct000001", "quote": "Spiculated mass 3.2 cm in the right upper lobe"}]},
        {"text": "The mass measures 4.1 cm.", "citations": [{"doc_id": "Dct000001", "quote": "Spiculated mass 3.2 cm in the right upper lobe"}]},
        {"text": "A PET-CT was done.", "citations": [{"doc_id": "Dnope0000", "quote": "PET-CT"}]}],
        "references": [{"ref_id": "G1", "quote": "Molecular testing for EGFR(a) and ALK(a) on the biopsy specimen"}]})
    a = asyncio.run(agents.ask(case_id, "radiology", "What size is the lung mass on the CT?"))
    assert a["status"] == "answered" and a["kind"] == "AI agent, support only" and a["label"] == "Radiology support"
    assert [s["text"] for s in a["statements"]] == ["The CECT thorax records a spiculated mass of 3.2 cm in the right upper lobe."]
    assert a["statements"][0]["citations"][0]["doc_id"] == "Dct000001"
    assert sorted(x["reason"] for x in a["removed"]) == ["document_not_found", "number_not_in_quote"] and a["dropped_unverified"] == 2
    assert [r["region"] for r in a["references"]] == ["India"] and a["references"][0]["by"] == "agent"
    ctx = prompts[0][-1]["content"]
    assert "Spiculated mass" in ctx and "[G1 | National Cancer Grid (NCG), India" in ctx and "QUESTION FROM THE BOARD" in ctx
    assert "Radiology support agent" in prompts[0][0]["content"]
    ev = store.read_audit(case_id)
    assert any(e["kind"] == "agent_answer" and e["status"] == "answered" and e["statements"] == 1 for e in ev)


def test_out_of_scope_question_refused_by_rule_without_a_model_call(monkeypatch, pack):
    case_id = _case(make_doc("Dct000001", "ct", text=CT))
    calls = _no_model(monkeypatch)
    a = asyncio.run(agents.ask(case_id, "radiology", "Which chemotherapy regimen should we start?"))
    assert a["status"] == "out_of_scope" and a["category"] == "treatment_recommendation" and a["statements"] == [] and calls == []
    a = asyncio.run(agents.ask(case_id, "radiology", "Please look at the CT images and tell me what you see"))
    assert a["status"] == "out_of_scope" and a["category"] == "scan_interpretation"


def test_out_of_scope_question_refused_by_the_classifier(monkeypatch, pack):
    case_id = _case(make_doc("Dct000001", "ct", text=CT))
    _live(monkeypatch, {"answer_found": True, "statements": [{"text": "x", "citations": []}], "references": []}, category="prognosis")
    a = asyncio.run(agents.ask(case_id, "radiology", "Tell me about the outlook"))
    assert a["status"] == "out_of_scope" and a["category"] == "prognosis" and a["statements"] == []


def test_not_documented_answer_shows_no_guideline_text(monkeypatch, pack):
    case_id = _case(make_doc("Dct000001", "ct", text=CT))
    _live(monkeypatch, {"answer_found": False, "statements": [], "references": [{"ref_id": "G1", "quote": "Molecular testing for EGFR(a) and ALK(a)"}]})
    a = asyncio.run(agents.ask(case_id, "radiology", "Is there a brain MRI report?"))
    assert a["status"] == "not_documented" and a["references"] == [] and a["references_dropped"] == 1
    assert a["message"].startswith("Not documented in the Case File")


def test_live_answer_output_guardrail(monkeypatch, pack):
    case_id = _case(make_doc("Dct000001", "ct", text=CT))
    _live(monkeypatch, {"answer_found": True, "references": [], "statements": [
        {"text": "The patient should receive surgery for the 3.2 cm mass.", "citations": [{"doc_id": "Dct000001", "quote": "Spiculated mass 3.2 cm in the right upper lobe"}]},
        {"text": "The CECT records no pleural effusion.", "citations": [{"doc_id": "Dct000001", "quote": "No pleural effusion."}]}]})
    a = asyncio.run(agents.ask(case_id, "radiology", "Is there a pleural effusion?"))
    assert [s["text"] for s in a["statements"]] == ["The CECT records no pleural effusion."]
    assert [x["reason"] for x in a["removed"]] == ["guardrail"] and a["dropped_unverified"] == 0


HPE_I1 = ("SYNTHETIC\nHISTOPATHOLOGY REPORT\nMargins: involved\nPaclitaxel 175 mg/m2 given on 03/03/2026\nReport status: FINAL")


def test_review_i1_a_treatment_word_outside_the_quote_is_refused(monkeypatch, pack):
    """The review's margins example: the quote is found and has no number, so only the treatment word outside it can refuse it."""
    case_id = _case(make_doc("Dhpe00001", "histopathology", text=HPE_I1))
    cite = [{"doc_id": "Dhpe00001", "quote": "Margins: involved"}]
    drug = [{"doc_id": "Dhpe00001", "quote": "Paclitaxel 175 mg/m2 given on 03/03/2026"}]
    _live(monkeypatch, {"answer_found": True, "references": [], "statements": [
        {"text": "Margins are involved, so re-excision is needed.", "citations": cite},
        {"text": "Margins are involved; re-excision will follow.", "citations": cite},  # a treatment step put in the future in its own words
        {"text": "Margins: involved", "citations": cite},
        {"text": "The report records margins involved.", "citations": cite},
        {"text": "Paclitaxel 175 mg/m2 given on 03/03/2026.", "citations": drug}]})
    a = asyncio.run(agents.ask(case_id, "pathology", "What does the pathology report say about the margins?"))
    assert [s["text"] for s in a["statements"]] == ["Margins: involved", "The report records margins involved.",
                                                    "Paclitaxel 175 mg/m2 given on 03/03/2026."]
    by = {x["text"]: x for x in a["removed"]}
    assert by["Margins are involved, so re-excision is needed."]["reason"] == "guardrail"
    assert by["Margins are involved; re-excision will follow."]["reason"] == "guardrail"
    assert "advice wording outside the quoted record text: will" in by["Margins are involved; re-excision will follow."]["detail"]
    assert "—" not in by["Margins are involved; re-excision will follow."]["detail"]


def test_live_answer_on_an_unlisted_case_file(monkeypatch):
    calls = _no_model(monkeypatch)
    store.create_case("TB-UNL", {"name": "SYNTHETIC, X"}, "", created_by="test")
    a = asyncio.run(agents.ask("TB-UNL", "radiology", "What does the CT say?"))
    assert a["status"] == "not_listed" and calls == []
    with pytest.raises(ValueError):
        asyncio.run(agents.ask("TB-UNL", "cardiology", "x"))
