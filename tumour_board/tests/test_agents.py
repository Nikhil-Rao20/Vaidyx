"""Agents, adjudication and the summary see the Case File's clinician confirmations (V1 items 1.2 and 2.2): an attested document
counts as final in the document list, the facts text and the value checks of the board decision, and a confirmed document type
or value wins over the model's reading. Model calls are replaced by fakes."""
import asyncio

import pytest

from tumour_board import agents, confirm, llm, postboard, rules, store, summary
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


def test_summary_signature_is_taken_before_the_model_call(unit_case, monkeypatch):
    """V1 item 4.5 (review S2): a document that arrives while the model writes the summary is not in the text, so the stored
    signature must not include it: the summary shows as stale and the export refuses it."""
    _pdl1_doc(unit_case)
    rules.evaluate(unit_case)

    async def fake_chat(role, msgs, **kw):
        add(unit_case, make_doc("Dlate0001", "ct", region="chest", date="2026-09-20"))  # uploaded and processed during the call
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat)
    out = asyncio.run(summary.build(unit_case, force=True))
    assert out["signature"]["documents"] == 1
    assert rules.stale_reason(out["signature"], rules.case_signature(unit_case)).startswith("The Case File changed since this was generated: 1 document added")


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


# ---------------------------------------------------------------- guideline packs in the agents (V1 item 5.5)
NCG = {"file": "ncg_india/ncg-guidelines-for-thoracic-cancer-2019.pdf", "title": "ncg guidelines for thoracic cancer 2019",
       "org": "National Cancer Grid (NCG), India", "region": "India", "page": 4, "page_end": 4, "score": 0.05,
       "text": "WORK UP\nMolecular testing for EGFR(a) and ALK(a) on the biopsy specimen before treatment planning.\nPD-L1 testing (b)."}
ASCO = {"file": "asco_cap/2018-lung-update-summary.pdf", "title": "2018 lung update summary", "org": "ASCO / CAP", "region": "International",
        "page": 1, "page_end": 1, "score": 0.04, "text": "Laboratories should use EGFR mutation testing for lung adenocarcinoma in advanced stage disease."}


@pytest.fixture
def fake_pack(monkeypatch):
    calls = []

    def fake_search(role, q, cancer=None, india=3, intl=2):
        calls.append((role, q, cancer))
        return {"india": [NCG][:india], "international": [ASCO][:intl]}
    monkeypatch.setattr(agents.packs, "search", fake_search)
    return calls


def test_tools_doc_and_step_schema_offer_search_guidelines():
    assert "search_guidelines" in agents.STEP_SCHEMA["properties"]["tool"]["enum"]
    line = next(ln for ln in agents.TOOLS_DOC.splitlines() if ln.startswith("- search_guidelines"))
    assert "Indian sources" in line or "Indian sources" in agents.TOOLS_DOC
    assert "never a recommendation for this patient" in agents.TOOLS_DOC and "—" not in agents.TOOLS_DOC
    assert agents.BRIEF_SCHEMA["properties"]["points_for_review"]["items"]["required"] == ["text", "citations", "references"]


def test_search_guidelines_numbers_passages_india_first(fake_pack):
    refs = {}
    out = agents._search_guidelines("pathology", {"protocol": "lung_nsclc"}, "EGFR testing", refs)
    assert out.index("[G1 | National Cancer Grid (NCG), India") < out.index("[G2 | ASCO / CAP")
    assert refs["G1"] is NCG and refs["G2"] is ASCO and fake_pack[-1] == ("pathology", "EGFR testing", "lung_nsclc")
    agents._search_guidelines("pathology", {"protocol": "lung_nsclc"}, "EGFR again", refs)
    assert sorted(refs) == ["G1", "G2"]  # the same passage keeps its id


def test_references_need_a_verbatim_quote():
    refs = {"G1": NCG, "G2": ASCO}
    kept, dropped = agents._verify_references([
        {"ref_id": "G1", "quote": "Molecular testing for EGFR(a) and ALK(a)"},
        {"ref_id": "G2", "quote": "EGFR testing is mandatory for every patient"},  # not in the passage
        {"ref_id": "G9", "quote": "anything"}], refs)  # unknown id
    assert dropped == 2 and len(kept) == 1
    assert kept[0] == {"file": NCG["file"], "title": NCG["title"], "org": NCG["org"], "region": "India", "page": 4, "page_end": 4,
                       "quote": "Molecular testing for EGFR(a) and ALK(a)", "by": "agent"}


def test_indian_reference_found_by_search_when_relevant(fake_pack):
    ref = agents._indian_reference("pathology", {"protocol": "lung_nsclc"}, "The EGFR and ALK molecular results are not documented on the biopsy.")
    assert ref["region"] == "India" and ref["by"] == "search"
    assert ref["quote"] == "Molecular testing for EGFR(a) and ALK(a) on the biopsy specimen before treatment planning." and ref["quote"] in NCG["text"]
    assert agents._indian_reference("pathology", {"protocol": "lung_nsclc"}, "Haemoglobin of 9.8 g/dL is pending signature.") is None


def _lung_case():
    store.create_case("TB-LUNG", {"name": "SYNTHETIC, Lung Patient", "mrn": "SYN-900009", "agesex": "61 Y / M"}, "lung_nsclc", created_by="test")
    add("TB-LUNG", make_doc("Dhist0009", "histopathology", text="SYNTHETIC\nHISTOPATHOLOGY REPORT\nEGFR mutation analysis: awaited\nReport status: FINAL"))
    return "TB-LUNG"


def test_brief_points_carry_verified_references_india_first(fake_pack, monkeypatch):
    case_id = _lung_case()
    prompts = []

    async def fake_chat(role, msgs, json_schema=None, **kw):
        prompts.append(msgs[-1]["content"])
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "done", "tool": "finish", "input": ""}
        return {"sections": [], "not_documented": [], "points_for_review": [
            {"text": "EGFR mutation analysis is awaited on the histopathology report.",
             "citations": [{"doc_id": "Dhist0009", "quote": "EGFR mutation analysis: awaited"}],
             "references": [{"ref_id": "G2", "quote": "Laboratories should use EGFR mutation testing"},
                            {"ref_id": "G1", "quote": "not in the passage"}]}]}
    monkeypatch.setattr(agents.llm, "chat", fake_chat)

    async def go():
        return [e async for e in agents.run_agent(case_id, "radiology", max_steps=1)]
    ev = asyncio.run(go())
    brief = ev[-1]["brief"]
    assert any(e.get("tool") == "search_guidelines" and e.get("auto") for e in ev)
    assert "REPORTING CHECKLIST (reference: ICRI / IRIA synoptic reporting in lung cancer, India" in prompts[0]  # the radiology lung checklist
    assert "GUIDELINE REFERENCES" in prompts[0] and "[G1 | National Cancer Grid (NCG), India" in prompts[0]
    refs = brief["points_for_review"][0]["references"]
    assert [r["region"] for r in refs] == ["India", "International"]  # the Indian passage, found by search, comes first
    assert refs[0]["by"] == "search" and refs[1]["by"] == "agent" and brief["references_dropped"] == 1
    assert brief["pack"]["checklist"]["title"].startswith("ICRI / IRIA") and brief["pack"]["sources"][0]["region"] == "India"


def test_brief_without_guideline_index_still_written(monkeypatch):
    case_id = _lung_case()

    def broken(*a, **k):
        raise RuntimeError("index not built")
    monkeypatch.setattr(agents.packs, "search", broken)

    async def fake_chat(role, msgs, json_schema=None, **kw):
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "done", "tool": "finish", "input": ""}
        return {"sections": [], "not_documented": [], "points_for_review": [
            {"text": "EGFR mutation analysis is awaited.", "citations": [{"doc_id": "Dhist0009", "quote": "EGFR mutation analysis: awaited"}], "references": []}]}
    monkeypatch.setattr(agents.llm, "chat", fake_chat)

    async def go():
        return [e async for e in agents.run_agent(case_id, "pathology", max_steps=1)]
    brief = asyncio.run(go())[-1]["brief"]
    assert brief["points_for_review"][0]["references"] == []


GALL = {"file": "iria/ICRI-IRIA-onco-imaging-protocols-and-reporting-checklists-2020.pdf", "title": "ICRI IRIA onco imaging protocols and reporting checklists 2020",
        "org": "ICRI / IRIA onco-imaging checklists, India", "region": "India", "page": 77, "page_end": 77, "score": 0.05,
        "text": "CECT helps to determine the resectability of gall bladder carcinoma and provides a vascular road map for radical surgery."}
HN = {"file": "ncg_india/ncg-guidelines-for-head-neck-cancer-2019.pdf", "title": "ncg guidelines for head neck cancer 2019",
      "org": "National Cancer Grid (NCG), India", "region": "India", "page": 27, "page_end": 27, "score": 0.05,
      "text": "ECOG performance 0-1: concurrent chemoradiation. ECOG performance > 2: radiotherapy alone."}


def test_references_from_another_cancer_are_never_attached(monkeypatch):
    def fake_search(role, q, cancer=None, india=3, intl=2):
        return {"india": [GALL, HN], "international": []}
    monkeypatch.setattr(agents.packs, "search", fake_search)
    # a breast Case File: the multi-cancer ICRI passage does not name breast, the head & neck guideline is another cancer
    assert agents._indian_reference("radiology", {"protocol": "breast"}, "Confirm the CECT thorax and abdomen report is final and signed.") is None
    assert agents._indian_reference("medical_oncology", {"protocol": "lung_nsclc"}, "The ECOG performance status differs between the OPD note and discharge.") is None
    kept, dropped = agents._verify_references([{"ref_id": "G1", "quote": "ECOG performance 0-1"}], {"G1": HN}, "lung_nsclc")
    assert kept == [] and dropped == 1  # the agent cited a head & neck guideline on a lung Case File
    assert agents._cancer_fit(NCG, "lung_nsclc") == "same" and agents._cancer_fit(GALL, "breast") == "" and agents._cancer_fit(HN, "lung_nsclc") == "other"
