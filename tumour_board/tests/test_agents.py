"""Agents, adjudication and the summary see the Case File's clinician confirmations (V1 items 1.2 and 2.2): an attested document
counts as final in the document list, the facts text and the value checks of the board decision, and a confirmed document type
or value wins over the model's reading. Model calls are replaced by fakes."""
import asyncio

import pytest

from tumour_board import agents, confirm, llm, postboard, rules, summary
from tumour_board.tests.util import add, fact, make_doc


def _two_histologies(unit_case):
    add(unit_case,
        make_doc("Dhist0000", "histopathology", date="2026-08-01", facts={"histologic_type": fact("Squamous cell carcinoma")}),
        make_doc("Dhist0001", "histopathology", date="2026-09-10", status="UNSTATED", signed="unknown",
                 facts={"histologic_type": fact("Adenocarcinoma")}))


def test_agent_document_list_shows_attestation(unit_case):
    _two_histologies(unit_case)
    assert "attested" not in agents._doc_list(unit_case)
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    rows = agents._doc_list(unit_case)
    assert "Dhist0001 | HISTOPATHOLOGY REPORT Dhist0001 | histopathology | 2026-09-10 | status not stated, attested final by Dr. Rao" in rows
    assert "Dhist0000 | HISTOPATHOLOGY REPORT Dhist0000 | histopathology | 2026-08-01 | FINAL" in rows


def test_agent_facts_text_marks_attested_values(unit_case):
    _two_histologies(unit_case)
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    txt = agents._facts_text(unit_case)
    assert "Adenocarcinoma  [Dhist0001 HISTOPATHOLOGY REPORT Dhist0001 2026-09-10 UNSTATED, attested final by Dr. Rao]" in txt
    assert "Squamous cell carcinoma  [Dhist0000 HISTOPATHOLOGY REPORT Dhist0000 2026-08-01 FINAL]" in txt


def _adjudicate(unit_case, monkeypatch, text):
    async def fake_chat(role, msgs, **kw):
        return {"claims": [{"fact": "histologic_type", "value_as_written": text, "span": text}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(postboard.llm, "chat", fake_chat)
    rec = {"decision_text": f"Histology {text}. Plan agreed.", "participants": "Dr. A, Dr. B"}
    return asyncio.run(postboard.adjudicate(unit_case, rec))


def test_adjudication_uses_the_attested_document_as_current(unit_case, monkeypatch):
    _two_histologies(unit_case)
    rules.evaluate(unit_case)
    before = _adjudicate(unit_case, monkeypatch, "Adenocarcinoma")
    assert [c["source"]["doc_id"] for c in before["value_checks"]] == ["Dhist0000"]  # the older FINAL report wins without the attestation
    assert any(f["kind"] == "transcription" for f in before["flags"])
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    after = _adjudicate(unit_case, monkeypatch, "Adenocarcinoma")
    assert [c["source"]["doc_id"] for c in after["value_checks"]] == ["Dhist0001"]
    assert not any(f["kind"] == "transcription" for f in after["flags"])


# ---- adjudication shares the negation cues (review of 1.1): a flip against "non-amplified" must be caught -------------
@pytest.mark.parametrize("written,source,expected", [
    ("HER2 amplified", "HER2 non-amplified", "discrepancy"),
    ("EGFR mutation detected", "EGFR non-detected", "discrepancy"),
    ("HBV DNA detectable", "HBV DNA non-detectable", "discrepancy"),
    ("HER2 not amplified", "HER2 non-amplified", "consistent"),
    ("HER2 negative", "HER2 negative (IHC 2+, FISH non-amplified)", "consistent"),
    ("Invasive carcinoma of no special type", "Invasive breast carcinoma of no special type (ductal).", "consistent"),
])
def test_adjudication_polarity_uses_the_shared_negation_cues(written, source, expected):
    a, b = postboard._polarity(written), postboard._polarity(source)
    assert bool(a and b and a != b) == (expected == "discrepancy"), (a, b)


def test_no_special_type_is_not_negative_in_adjudication():
    assert postboard._polarity("Invasive carcinoma of no special type") is None
    assert postboard._polarity("no evidence of metastasis") == "neg"


# ---- confirmations reach every reader (review of 2.2, finding M7) ---------------------------------------------------
def _pdl1_doc(unit_case):
    add(unit_case, make_doc("Dihc00000", "ihc", date="2026-09-05", facts={"pdl1": fact("TPS 6%", quote="PD-L1 (22C3) TPS 6%")},
                            text="SYNTHETIC\nIHC REPORT\nPD-L1 (22C3) TPS 6%\nReport status: FINAL"))


def _confirm_pdl1(unit_case):
    confirm.record(unit_case, "confirm_value", "Dihc00000:pdl1", {"value": "TPS 60%"}, by="Dr. Rao")


def test_agent_facts_text_shows_confirmed_value_without_quote(unit_case):
    _pdl1_doc(unit_case)
    assert "PD-L1: TPS 6%  [Dihc00000" in agents._facts_text(unit_case)
    _confirm_pdl1(unit_case)
    txt = agents._facts_text(unit_case)
    assert "PD-L1: TPS 60% (confirmed by Dr. Rao, no quote)  [Dihc00000 IHC REPORT Dihc00000 2026-09-05 FINAL]" in txt
    assert "TPS 6%" not in txt


def test_agent_document_list_and_relevant_docs_use_confirmed_type(unit_case):
    add(unit_case, make_doc("Dnote0000", "clinical_note", date="2026-09-02"))
    assert "| clinical_note |" in agents._doc_list(unit_case)
    confirm.record(unit_case, "confirm_doc_type", "Dnote0000", {"doc_type": "histopathology"}, by="Dr. Rao")
    assert "Dnote0000 | CLINICAL_NOTE REPORT Dnote0000 | histopathology | 2026-09-02 | FINAL" in agents._doc_list(unit_case)


def test_summary_facts_fallback_uses_confirmed_value(unit_case, monkeypatch):
    _pdl1_doc(unit_case)
    _confirm_pdl1(unit_case)
    rules.evaluate(unit_case)

    async def fake_chat(role, msgs, **kw):
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat)
    out = asyncio.run(summary.build(unit_case, force=True))
    inv = next(s for s in out["sections"] if s["id"] == "investigations")
    pd = [x for x in inv["sentences"] if x["text"].startswith("PD-L1:")]
    assert len(pd) == 1 and pd[0]["citations"] == [] and pd[0]["confirmed_by"] == "Dr. Rao"
    assert pd[0]["text"] == "PD-L1: TPS 60% (confirmed by Dr. Rao against the IHC REPORT Dihc00000, 2026-09-05; no quote)."
    assert "TPS 6%" not in str(out["sections"])


def _adjudicate_pdl1(unit_case, monkeypatch, written):
    async def fake_chat(role, msgs, **kw):
        return {"claims": [{"fact": "pdl1", "value_as_written": written, "span": written}]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    return asyncio.run(postboard.adjudicate(unit_case, {"decision_text": f"PD-L1 {written}. Plan agreed.", "participants": "Dr. A, Dr. B"}))


def test_adjudication_compares_against_the_confirmed_value(unit_case, monkeypatch):
    _pdl1_doc(unit_case)
    before = _adjudicate_pdl1(unit_case, monkeypatch, "TPS 60%")
    assert [c["result"] for c in before["value_checks"]] == ["discrepancy"]
    _confirm_pdl1(unit_case)
    after = _adjudicate_pdl1(unit_case, monkeypatch, "TPS 60%")
    assert [c["result"] for c in after["value_checks"]] == ["consistent"]
    assert after["value_checks"][0]["source"] == {"value": "TPS 60%", "doc_id": "Dihc00000", "quote": "", "confirmed_by": "Dr. Rao"}
    old = _adjudicate_pdl1(unit_case, monkeypatch, "TPS 6%")  # the model's value is no longer the source, even though its quote said 6%
    assert [c["result"] for c in old["value_checks"]] == ["discrepancy"]
    f = next(f for f in old["flags"] if f["kind"] == "transcription")
    assert (f["source_value"], f["source_quote"]) == ("TPS 60%", "")


def test_timeline_uses_confirmed_date(unit_case):
    _pdl1_doc(unit_case)
    confirm.record(unit_case, "confirm_dates", "Dihc00000", {"report_date": "07/09/2026"}, by="Dr. Rao")
    assert [(e["doc_id"], e["date"]) for e in postboard.timeline(unit_case) if e["kind"] == "document"] == [("Dihc00000", "2026-09-07")]
