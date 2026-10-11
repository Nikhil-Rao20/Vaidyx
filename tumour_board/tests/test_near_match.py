"""V1 item 6.5: a statement whose quote matches its source only approximately (score >= 92, same numbers, >= 12 characters) is kept in
the summary (and briefs) flagged "approximate source match: check source", only behind TB_NEAR_MATCH; Q&A stays exact-only; the print
view (NCG VTB export) leaves approximate items out unless the summary is expert-reviewed. Synthetic data only; model calls are fakes."""
import asyncio

import pytest

from tumour_board import config, grounding, llm, qa, rules, store, summary, vtb_export
from tumour_board.tests.util import add, make_doc

IHC = ("SYNTHETIC\nIHC REPORT\nPD-L1 (22C3) tumour proportion score 60 percent\nER negative\n"
       "Spiculated mass in the right upper lobe abutting the oblique fissure measuring 3.2 x 2 cm\nReport status: FINAL")
TYPO = {"text": "The IHC report records a PD-L1 tumour proportion score of 60 percent.",
        "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumuor proportion score 60 percent"}]}  # one transposition
SOURCE = "PD-L1 (22C3) tumour proportion score 60 percent"
FLAG = "approximate source match: check source"


@pytest.fixture
def ihc_case(unit_case):
    add(unit_case, make_doc("Dihc00000", "ihc", date="2026-09-05", text=IHC))
    return unit_case


def test_flag_reads_the_environment_on_every_call(monkeypatch):
    monkeypatch.delenv("TB_NEAR_MATCH", raising=False)
    assert config.near_match() is False
    for v, want in (("1", True), ("true", True), (" ON ", True), ("0", False), ("no", False)):
        monkeypatch.setenv("TB_NEAR_MATCH", v)
        assert config.near_match() is want, v


def test_approximate_quote_kept_and_flagged_only_with_near_match(ihc_case):
    kept, dropped = qa.verify(ihc_case, [TYPO])
    assert kept == [] and dropped[0]["reason"] == "quote_not_found"
    kept, dropped = qa.verify(ihc_case, [TYPO], near_match=True)
    assert dropped == [] and len(kept) == 1
    k = kept[0]
    assert k["approximate"] is True and k["flags"] == [FLAG] and k["text"] == TYPO["text"]
    c = k["citations"][0]
    assert c["quote"] == SOURCE and c["approximate"] is True and 92 <= c["score"] < 100  # the stored quote is the source text
    assert IHC[c["start"]:c["end"]] == SOURCE


def test_exact_support_is_never_approximate(ihc_case):
    st = {"text": TYPO["text"], "citations": TYPO["citations"] + [{"doc_id": "Dihc00000", "quote": SOURCE}]}
    kept, _ = qa.verify(ihc_case, [st], near_match=True)
    assert kept == qa.verify_statements(ihc_case, [st]) and "approximate" not in kept[0] and "flags" not in kept[0]


def test_a_different_number_is_never_approximate(ihc_case):
    six = {"text": "The PD-L1 tumour proportion score is 6 percent.", "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumuor proportion score 6 percent"}]}
    kept, dropped = qa.verify(ihc_case, [six], near_match=True)
    assert kept == [] and dropped[0]["reason"] == "quote_not_found"
    # a quote that leaves out a number of the matched source (grounding.locate accepts it: its numbers are a subset) is not the same numbers
    q = "Spiculated mass in the right upper lobe abutting the oblique fissure measuring 3.2 x cm"
    assert grounding.locate(q, [IHC])["score"] >= 92
    fewer = {"text": "A spiculated mass of 3.2 cm is recorded.", "citations": [{"doc_id": "Dihc00000", "quote": q}]}
    kept, dropped = qa.verify(ihc_case, [fewer], near_match=True)
    assert kept == [] and dropped[0]["reason"] == "quote_not_found"


def test_statement_number_guard_still_applies_to_approximate_quotes(ihc_case):
    st = {"text": "The PD-L1 tumour proportion score is 70 percent.", "citations": TYPO["citations"]}
    kept, dropped = qa.verify(ihc_case, [st], near_match=True)
    assert kept == [] and (dropped[0]["reason"], dropped[0]["detail"]) == ("number_not_in_quote", "number 70 not in the quoted source")


def test_short_quote_is_never_approximate(ihc_case):
    st = {"text": "ER is negative.", "citations": [{"doc_id": "Dihc00000", "quote": "ER negatve"}]}  # 10 characters
    kept, dropped = qa.verify(ihc_case, [st], near_match=True)
    assert kept == [] and dropped[0]["reason"] == "quote_not_found"


def test_ask_stays_exact_only_with_the_flag_on(ihc_case, monkeypatch):
    monkeypatch.setenv("TB_NEAR_MATCH", "1")

    async def fake_chat(role, msgs, purpose="", **kw):
        if purpose == "scope check":
            return {"category": "in_scope", "reason": ""}
        return {"answer_found": True, "statements": [TYPO]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    res = asyncio.run(qa.ask(ihc_case, "What is the PD-L1 score?"))
    assert res["status"] == "not_documented" and res["statements"] == []
    assert [x["reason"] for x in res["removed"]] == ["quote_not_found"] and res["dropped_unverified"] == 1


def _build(case_id, monkeypatch, near):
    if near:
        monkeypatch.setenv("TB_NEAR_MATCH", "1")
    else:
        monkeypatch.delenv("TB_NEAR_MATCH", raising=False)
    rules.evaluate(case_id)

    async def fake_chat(role, msgs, **kw):
        return {"sentences": [{**TYPO, "section": "investigations"}],
                "points_for_review": [{"text": "PD-L1 60 percent to be checked against the block.", "citations": TYPO["citations"]}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    return asyncio.run(summary.build(case_id, force=True))


def test_summary_keeps_approximate_items_flagged_only_with_the_flag(ihc_case, monkeypatch):
    off = _build(ihc_case, monkeypatch, False)
    assert off["near_match"] is False and off["approximate"] == 0 and off["dropped_unverified"] == 2
    on = _build(ihc_case, monkeypatch, True)
    inv = next(s for s in on["sections"] if s["id"] == "investigations")
    assert on["near_match"] is True and on["approximate"] == 2 and on["dropped_unverified"] == 0 and on["removed"] == []
    assert inv["sentences"][0]["approximate"] is True and FLAG in inv["sentences"][0]["flags"]
    assert on["points_for_review"][0]["approximate"] is True and on["points_for_review"][0]["citations"][0]["quote"] == SOURCE


def _export_texts(case_id):
    data = vtb_export.content(case_id)
    return [it for sl in data["slides"] for it in sl["items"]], data


def test_export_leaves_approximate_items_out_unless_reviewed(ihc_case, monkeypatch):
    _build(ihc_case, monkeypatch, True)
    items, data = _export_texts(ihc_case)
    assert not any("tumour proportion score" in it or "to be checked against the block" in it for it in items)
    assert data["slides"][5]["extra"]["points_for_review"] == []
    st = store.get_state(ihc_case)
    st["artefacts"]["summary"]["review"] = {"status": "reviewed", "by": "dr_rao"}
    store.save_state(ihc_case, st)
    items, data = _export_texts(ihc_case)
    assert any(it.startswith(TYPO["text"]) for it in items)
    assert data["slides"][5]["extra"]["points_for_review"][0].startswith("PD-L1 60 percent to be checked")


def test_fill_from_facts_adds_the_exact_sentence_beside_an_approximate_one():
    """An approximate sentence never stands in for a verified fact: the print view hides it until review (V1 item 6.5)."""
    from tumour_board import summary
    sec = [{"id": "fitness", "sentences": [{"text": "ECOG performance status 1.", "approximate": True,
                                           "citations": [{"doc_id": "D1", "quote": "ECOG perfomance status: 1"}]}]}]
    facts = {"ecog": {"current": {"value": "1", "verification": "verified", "state": "present", "doc_final": True, "quote": "ECOG performance status: 1",
                                  "location": {"page": 0, "start": 0, "end": 26}, "doc_id": "D1", "doc_title": "OPD NOTE", "date": "2026-09-01"}}}
    assert summary.fill_from_facts(sec, facts, {"ecog": {"label": "ECOG performance status"}}) == 1
    assert sec[0]["sentences"][-1]["from_fields"] and not sec[0]["sentences"][-1].get("approximate")
