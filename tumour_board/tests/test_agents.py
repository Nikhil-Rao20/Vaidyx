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


# ---- read_document takes page ranges; tool results up to 12,000 characters (V1 item 3.4) -----------------------------
def _long_doc(unit_case, n=8, size=2900):
    d = make_doc("Dlong0001", "discharge_summary", title="DISCHARGE SUMMARY")
    d["pages"] = [{"text": f"SYNTHETIC page {i} marker\n" + (f"Day-wise course page {i}: afebrile, vitals stable.\n" * 60)[:size], "method": "text-layer"}
                  for i in range(1, n + 1)]
    add(unit_case, d)
    return d


def _read(unit_case, arg):
    return asyncio.run(agents._tool(unit_case, "read_document", arg))


@pytest.mark.parametrize("arg", ["Dlong0001 pages 3-5", "Dlong0001 p3-5", "Dlong0001 pages 3 to 5", "Dlong0001 Pages 3 - 5"])
def test_read_document_page_range(unit_case, arg):
    _long_doc(unit_case)
    obs = _read(unit_case, arg)
    assert [i for i in range(1, 9) if f"SYNTHETIC page {i} marker" in obs] == [3, 4, 5]
    assert obs.startswith("[page 3]\n") and "[page 5]\n" in obs and "document continues" not in obs


@pytest.mark.parametrize("arg", ["Dlong0001 page 2", "Dlong0001 pages 2", "Dlong0001 p2"])
def test_read_document_single_page(unit_case, arg):
    _long_doc(unit_case)
    obs = _read(unit_case, arg)
    assert [i for i in range(1, 9) if f"SYNTHETIC page {i} marker" in obs] == [2]


def test_read_document_without_range_is_cut_at_12000_with_a_continuation_line(unit_case):
    _long_doc(unit_case)
    obs = _read(unit_case, "Dlong0001")
    assert len(obs) <= 12000 and agents.READ_CAP == 12000
    shown = [i for i in range(1, 9) if f"SYNTHETIC page {i} marker" in obs]
    assert shown == [1, 2, 3, 4]
    assert obs.endswith("\n[... document continues: pages 5 to 8 not shown; ask for them with 'Dlong0001 pages 5-8']")
    assert "Day-wise course page 4" in _read(unit_case, "Dlong0001 pages 4-8")


def test_read_document_short_document_is_whole(unit_case):
    _long_doc(unit_case, n=2, size=500)
    obs = _read(unit_case, "Dlong0001")
    assert "SYNTHETIC page 1 marker" in obs and "SYNTHETIC page 2 marker" in obs and "document continues" not in obs


def test_read_document_oversized_page_is_cut(unit_case):
    d = _long_doc(unit_case, n=2)
    d["pages"][0]["text"] = "SYNTHETIC\n" + "x" * 20000
    add(unit_case, d)
    obs = _read(unit_case, "Dlong0001")
    assert len(obs) <= 12000 and obs.endswith("[... document continues: the rest of page 1 is not shown; page 2 not shown; ask for it with 'Dlong0001 page 2']")


@pytest.mark.parametrize("arg,msg", [("Dlong0001 pages 12-14", "Document Dlong0001 has 8 pages; pages 12 to 14 do not exist. Ask for pages 1 to 8."),
                                     ("Dlong0001 pages 5-3", "Document Dlong0001 has 8 pages; pages 5 to 3 do not exist. Ask for pages 1 to 8."),
                                     ("Dlong0001 pages 0", "Document Dlong0001 has 8 pages; pages 0 to 0 do not exist. Ask for pages 1 to 8."),
                                     ("Dlong0001 the end", "Could not read the page range 'the end'. Ask for pages like 'Dlong0001 pages 2-4' or 'Dlong0001 page 2'."),
                                     ("Dnope0001 pages 1-2", "No document with that id. Use list_documents.")])
def test_read_document_bad_range(unit_case, arg, msg):
    _long_doc(unit_case)
    assert _read(unit_case, arg) == msg


def test_read_document_range_past_the_end_is_clamped(unit_case):
    _long_doc(unit_case)
    obs = _read(unit_case, "Dlong0001 pages 7-20")
    assert [i for i in range(1, 9) if f"SYNTHETIC page {i} marker" in obs] == [7, 8] and "document continues" not in obs


def test_tools_doc_describes_page_ranges():
    line = next(ln for ln in agents.TOOLS_DOC.splitlines() if ln.startswith("- read_document"))
    assert "pages 3-5" in line and "\u2014" not in agents.TOOLS_DOC


def test_agent_scratchpad_keeps_12000_characters_of_a_tool_result(unit_case, monkeypatch):
    _long_doc(unit_case)
    seen = []

    async def fake_chat(role, msgs, json_schema=None, **kw):
        seen.append(msgs[-1]["content"])
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "read", "tool": "read_document", "input": "Dlong0001 pages 1-8"} if len(seen) == 1 else {"thought": "done", "tool": "finish", "input": ""}
        return {"sections": [], "points_for_review": [], "not_documented": []}
    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(agents.llm, "chat", fake_chat)

    async def go():
        return [e async for e in agents.run_agent(unit_case, "pathology", max_steps=2)]
    ev = asyncio.run(go())
    assert ev[-1]["type"] == "brief"
    obs = asyncio.run(agents._tool(unit_case, "read_document", "Dlong0001 pages 1-8"))
    assert len(obs) > 7000 and f"RESULT:\n{obs}" in seen[1]  # the whole result (over the old 6,000 cap) reaches the next step
