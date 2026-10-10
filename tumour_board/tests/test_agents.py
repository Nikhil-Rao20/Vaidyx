"""Agents and adjudication see the Case File's clinician confirmations (V1 item 1.2): an attested document counts as final in the
document list, the facts text and the value checks of the board decision. Model calls are replaced by fakes."""
import asyncio

import pytest

from tumour_board import agents, llm, postboard, rules
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
