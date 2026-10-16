"""V1 item 6.4: AI statements that fail verification are kept aside with the reason (document not found, quote not found, number not in
quote, guardrail), never shown as facts. qa.verify returns (kept, dropped); Q&A and the summary store the removed items. Synthetic data only;
model calls are replaced by fakes."""
import asyncio

import pytest

from tumour_board import llm, qa, rules, store, summary
from tumour_board.tests.util import add, make_doc

IHC = "SYNTHETIC\nIHC REPORT\nPD-L1 (22C3) tumour proportion score 60 percent\nHER2 negative (IHC 1+)\nReport status: FINAL"
GOOD = {"text": "The IHC report records a PD-L1 tumour proportion score of 60 percent.",
        "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumour proportion score 60 percent"}]}
NO_DOC = {"text": "EGFR exon 19 deletion is recorded.", "citations": [{"doc_id": "D1234", "quote": "EGFR exon 19 deletion detected"}]}
NO_CITE = {"text": "The patient has a cough.", "citations": []}
NO_QUOTE = {"text": "HER2 is negative.", "citations": [{"doc_id": "Dihc00000", "quote": ""}]}
WRONG_QUOTE = {"text": "ALK is negative.", "citations": [{"doc_id": "Dihc00000", "quote": "ALK (D5F3) negative"}]}
WRONG_NUM = {"text": "The PD-L1 tumour proportion score is 6 percent.", "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumour proportion score 60 percent"}]}
ADVICE = {"text": "The PD-L1 score is 60 percent so the patient should start immunotherapy.",
          "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumour proportion score 60 percent"}]}


@pytest.fixture
def ihc_case(unit_case):
    add(unit_case, make_doc("Dihc00000", "ihc", date="2026-09-05", text=IHC))
    return unit_case


def _reason(case_id, st):
    kept, dropped = qa.verify(case_id, [st])
    assert kept == [] and len(dropped) == 1, (kept, dropped)
    return dropped[0]


def test_verified_statement_kept_and_identical_to_verify_statements(ihc_case):
    stmts = [GOOD, NO_DOC, WRONG_NUM, {"text": "HER2 is negative.", "citations": [{"doc_id": "Dihc00000", "quote": "HER2 negative (IHC 1+)"}]}]
    kept, dropped = qa.verify(ihc_case, stmts)
    assert kept == qa.verify_statements(ihc_case, stmts)
    assert [k["text"] for k in kept] == [GOOD["text"], "HER2 is negative."] and len(dropped) == 2
    assert not any("approximate" in k or "approximate" in c for k in kept for c in k["citations"])


def test_document_not_found(ihc_case):
    d = _reason(ihc_case, NO_DOC)
    assert d == {"text": NO_DOC["text"], "reason": "document_not_found", "reason_label": "cited document not found",
                 "detail": "D1234 not in this Case File", "citations": [{"doc_id": "D1234", "quote": "EGFR exon 19 deletion detected"}]}


def test_quote_not_found_no_citation_no_quote_and_wrong_quote(ihc_case):
    for st in (NO_CITE, NO_QUOTE):
        d = _reason(ihc_case, st)
        assert (d["reason"], d["reason_label"], d["detail"]) == ("quote_not_found", "quote not found in the cited document", "no quote given"), st
    d = _reason(ihc_case, WRONG_QUOTE)
    assert (d["reason"], d["detail"]) == ("quote_not_found", "quote not found in Dihc00000")
    assert d["citations"] == [{"doc_id": "Dihc00000", "quote": "ALK (D5F3) negative"}]


def test_found_document_wins_over_a_missing_one(ihc_case):
    st = {"text": "ALK is negative.", "citations": [{"doc_id": "Dnope", "quote": "ALK negative"}, {"doc_id": "Dihc00000", "quote": "ALK (D5F3) negative"}]}
    assert _reason(ihc_case, st)["reason"] == "quote_not_found"


def test_number_not_in_quote_names_the_number(ihc_case):
    d = _reason(ihc_case, WRONG_NUM)
    assert (d["reason"], d["reason_label"], d["detail"]) == ("number_not_in_quote", "a number is not in the quoted source", "number 6 not in the quoted source")
    st = {"text": "Scores 6 and 7 percent.", "citations": GOOD["citations"]}
    assert _reason(ihc_case, st)["detail"] == "numbers 6, 7 not in the quoted source"


def test_quote_in_a_dropped_item_is_cut_at_400_characters(ihc_case):
    st = {"text": "Something.", "citations": [{"doc_id": "Dnope", "quote": "x" * 900}]}
    assert len(_reason(ihc_case, st)["citations"][0]["quote"]) == 400


def _fake_ask(monkeypatch, statements):
    async def fake_chat(role, msgs, purpose="", **kw):
        if purpose == "scope check":
            return {"category": "in_scope", "reason": ""}
        return {"answer_found": True, "statements": statements}
    monkeypatch.setattr(llm, "chat", fake_chat)


def test_ask_lists_removed_items_with_guardrail_and_counts_match(ihc_case, monkeypatch):
    _fake_ask(monkeypatch, [GOOD, NO_DOC, WRONG_NUM, ADVICE])
    res = asyncio.run(qa.ask(ihc_case, "What is the PD-L1 score?"))
    assert res["status"] == "answered" and [s["text"] for s in res["statements"]] == [GOOD["text"]]
    assert [x["reason"] for x in res["removed"]] == ["document_not_found", "number_not_in_quote", "guardrail"]
    g = res["removed"][-1]
    assert g["text"] == ADVICE["text"] and g["reason_label"] == "removed by the clinical scope guardrail"
    assert g["detail"] == "prescriptive or diagnostic wording" and g["citations"][0]["doc_id"] == "Dihc00000"
    assert res["dropped_unverified"] == 2 == len([x for x in res["removed"] if x["reason"] != "guardrail"])
    ev = [e for e in store.read_audit(ihc_case) if e["kind"] == "answer"][-1]
    assert ev["dropped_unverified"] == 2 and [x["reason"] for x in ev["removed"]] == ["document_not_found", "number_not_in_quote", "guardrail"]
    assert ev["removed"][0]["text"] == NO_DOC["text"]


def test_ask_with_nothing_removed_has_an_empty_list(ihc_case, monkeypatch):
    _fake_ask(monkeypatch, [GOOD])
    res = asyncio.run(qa.ask(ihc_case, "What is the PD-L1 score?"))
    assert res["removed"] == [] and res["dropped_unverified"] == 0


def _fake_summary(monkeypatch, sentences, points):
    async def fake_chat(role, msgs, **kw):
        return {"sentences": sentences, "points_for_review": points}
    monkeypatch.setattr(llm, "chat", fake_chat)


def test_summary_stores_removed_items_with_where_and_counts(ihc_case, monkeypatch):
    rules.evaluate(ihc_case)
    sents = [{**GOOD, "section": "investigations"}, {**NO_DOC, "section": "investigations"}, {**WRONG_NUM, "section": "fitness"},
             {**ADVICE, "section": "questions"}]
    pts = [{"text": "The ALK result is awaited.", "citations": [{"doc_id": "Dihc00000", "quote": "ALK pending"}]},
           {"text": "The patient should start immunotherapy given PD-L1 60 percent.", "citations": GOOD["citations"]}]
    _fake_summary(monkeypatch, sents, pts)
    out = asyncio.run(summary.build(ihc_case, force=True))
    got = [(x["where"], x["reason"]) for x in out["removed"]]
    assert got == [("investigations", "document_not_found"), ("fitness", "number_not_in_quote"), ("questions", "guardrail"),
                   ("points_for_review", "quote_not_found"), ("points_for_review", "guardrail")]
    assert out["dropped_unverified"] == 3  # sections and points for review
    assert out["guardrail_removed"] == 2 and out["approximate"] == 0 and out["near_match"] is False and out["points_for_review"] == []
    inv = next(s for s in out["sections"] if s["id"] == "investigations")
    assert [s["text"] for s in inv["sentences"]][:1] == [GOOD["text"]]
    assert store.get_state(ihc_case)["artefacts"]["summary"]["removed"] == out["removed"]
    ev = [e for e in store.read_audit(ihc_case) if e["kind"] == "summary"][-1]
    assert ev["removed"] == {"document_not_found": 1, "quote_not_found": 1, "number_not_in_quote": 1, "guardrail": 2}
    assert ev["dropped_unverified"] == 3


def test_document_ids_written_in_the_text_are_not_numbers(unit_case):
    """The model often writes the document id inline ("[D75dbac7c]"); its digits are not a value and must not fail the number guard,
    and the bracketed id is not shown (the citation chip names the document). Found through the removed items (V1 item 6.4)."""
    from tumour_board.tests.util import add, make_doc
    add(unit_case, make_doc("D75dbac7c", "ct", text="SYNTHETIC\nCT THORAX\nSolid nodule in the right upper lobe measuring 2.1 cm.\nReport status: FINAL"))
    kept, dropped = qa.verify(unit_case, [
        {"text": "CT thorax: solid nodule measuring 2.1 cm [D75dbac7c].", "citations": [{"doc_id": "D75dbac7c", "quote": "Solid nodule in the right upper lobe measuring 2.1 cm."}]},
        {"text": "The CT report (D75dbac7c) records a nodule of 2.1 cm.", "citations": [{"doc_id": "D75dbac7c", "quote": "measuring 2.1 cm"}]},
        {"text": "CT thorax: nodule measuring 3.1 cm [D75dbac7c].", "citations": [{"doc_id": "D75dbac7c", "quote": "measuring 2.1 cm"}]},
        {"text": "Reference D99999999 shows 2.1 cm.", "citations": [{"doc_id": "D75dbac7c", "quote": "measuring 2.1 cm"}]}])
    assert [k["text"] for k in kept] == ["CT thorax: solid nodule measuring 2.1 cm.", "The CT report records a nodule of 2.1 cm."]
    assert [(d["reason"], d["detail"]) for d in dropped] == [("number_not_in_quote", "number 3.1 not in the quoted source"),
                                                            ("number_not_in_quote", "number 99999999 not in the quoted source")]  # an id of no document here stays a number


def test_a_quote_cut_after_a_negation_is_flagged(unit_case):
    """Phase 6 review: "Metastatic deposits seen in the liver" verifies inside "No metastatic deposits seen in the liver"; the statement
    keeps its citation but carries the negation check flag, unless it states the negation itself."""
    add(unit_case, make_doc("Dct000077", "ct", text="SYNTHETIC\nCT ABDOMEN\nNo metastatic deposits seen in the liver.\nReport status: FINAL"))
    kept, _ = qa.verify(unit_case, [
        {"text": "Metastatic deposits are seen in the liver.", "citations": [{"doc_id": "Dct000077", "quote": "Metastatic deposits seen in the liver"}]},
        {"text": "No metastatic deposits are seen in the liver.", "citations": [{"doc_id": "Dct000077", "quote": "metastatic deposits seen in the liver"}]}])
    assert kept[0]["flags"] == ["check negation against the source"] and "flags" not in kept[1]
    assert "negated_before" not in kept[0]["citations"][0]


def test_shown_text_and_number_guard_agree(unit_case):
    """Phase 6 review: removing a document id changes nothing else in the text, so '3 .5' is never shown as '3.5'."""
    add(unit_case, make_doc("D75dbac7c", "ct", text="SYNTHETIC\nCT THORAX\n3 cm lesion in segment 5.\nReport status: FINAL"))
    kept, dropped = qa.verify(unit_case, [{"text": "Size 3 .5 cm [D75dbac7c].", "citations": [{"doc_id": "D75dbac7c", "quote": "3 cm lesion in segment 5"}]}])
    assert [k["text"] for k in kept] == ["Size 3 .5 cm."] and not dropped  # shown exactly as checked
