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
        return [e async for e in agents.run_agent(unit_case, "medical_oncology", max_steps=2)]
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
    monkeypatch.setattr(agents.guidelines, "ready", lambda: True)
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
                       "page_kind": "page", "quote": "Molecular testing for EGFR(a) and ALK(a)", "by": "agent"}


def test_indian_reference_found_by_search_when_relevant(fake_pack):
    ref = agents._indian_reference("pathology", {"protocol": "lung_nsclc"}, "The EGFR and ALK molecular results are not documented on the biopsy.")
    assert ref["region"] == "India" and ref["by"] == "search"
    assert ref["quote"] == "Molecular testing for EGFR(a) and ALK(a) on the biopsy specimen before treatment planning." and ref["quote"] in NCG["text"]
    assert agents._indian_reference("pathology", {"protocol": "lung_nsclc"}, "Haemoglobin of 9.8 g/dL is pending signature.") is None


def _lung_case():
    store.create_case("TB-LUNG", {"name": "SYNTHETIC, Lung Patient", "mrn": "SYN-900009", "agesex": "61 Y / M"}, "lung_nsclc", created_by="test")
    add("TB-LUNG", make_doc("Dhist0009", "histopathology", text="SYNTHETIC\nHISTOPATHOLOGY REPORT\nEGFR mutation analysis: awaited\nReport status: FINAL"),
        make_doc("Dct000009", "ct", text="SYNTHETIC\nCECT THORAX REPORT\nSpiculated mass 3.2 cm in the right upper lobe\nReport status: FINAL"))  # radiology runs only with imaging (V1 item 6.6)
    return "TB-LUNG"


def test_brief_points_carry_verified_references_india_first(fake_pack, monkeypatch):
    case_id = _lung_case()
    prompts = []

    async def fake_chat(role, msgs, json_schema=None, **kw):
        prompts.append(msgs[-1]["content"])
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "done", "tool": "finish", "input": ""}
        return {"sections": [], "not_documented": [], "points_for_review": [
            {"text": "EGFR molecular testing on the biopsy specimen is awaited.",
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



# ---------------------------------------------------------------- Phase 5 review: scope of references and points, quote quality, fail-soft
@pytest.mark.parametrize("quote", [
    "They recommend that surgery should be offered to patients with stage IIIA NSCLC diagnosed as cT3 N1, cT1-2 N2 single-station disease",
    "Watch and wait (non-operative management) can be offered to low-lying locally-advanced rectal cancers that achieve clinical complete response",
    "In the absence of rectal MRI, ideally treatment for rectal cancer should not be offered.",
    "MRI brain is indicated in patients with neurological symptoms and stage IIIb and above",
    "Staging investigations not indicated in cT1-2, N0-1, M0",
    "N2 Lung resection with SMLND(a) followed by adjuvant chemotherapy",
    "Concurrent CTRT(a) with weekly cisplatin 40 mg/m2"])
def test_treatment_and_indication_quotes_are_not_references(quote):
    assert not agents._in_scope(quote)


@pytest.mark.parametrize("quote", ["Molecular tests for adenocarcinoma: EGFR, ALK, ROS-1",
                                   "PD-L1 status % age of tumour cells positive Antibody used Not assessed",
                                   "CECT Thorax, abdomen and Pelvis(a)", "Comparison to the previous study and date"])
def test_reporting_and_work_up_quotes_are_references(quote):
    assert agents._in_scope(quote)


def test_agent_reference_with_a_directive_is_dropped():
    esmo = {**ASCO, "file": "esmo/ESMO_2025_early_locally_advanced_NSCLC.pdf", "title": "ESMO 2025 early locally advanced NSCLC",
            "text": "They recommend that surgery should be offered to patients with stage IIIA NSCLC diagnosed as cT3 N1 disease."}
    kept, dropped = agents._verify_references([{"ref_id": "G1", "quote": "surgery should be offered to patients with stage IIIA NSCLC"}],
                                              {"G1": esmo}, "lung_nsclc")
    assert kept == [] and dropped == 1


@pytest.mark.parametrize("text", [
    "Is a brain MRI indicated given the recorded stage IIIB?",
    "Is a PET/CT indicated for this patient given the current staging and lack of metastatic work-up in the records?",
    "Confirmation of N2 status (single vs multi-station) to determine surgical approach/resectability.",
    "Clarify the treatment sequencing (NACT vs Surgery) for this patient."])
def test_points_asking_for_a_decision_are_out_of_scope(text):
    assert agents._POINT_SCOPE.search(text)


@pytest.mark.parametrize("text", ["EGFR mutation analysis is awaited on the histopathology report.",
                                  "The histopathology report is a draft and unsigned; is a final version available?",
                                  "The ECOG performance status differs between the OPD note (PS 1) and the discharge summary (PS 2)."])
def test_points_about_the_records_stay(text):
    assert not agents._POINT_SCOPE.search(text)


@pytest.mark.parametrize("quote", ["Surgery is recommended for every patient with N2 disease ... the", "Unrelated words ...\nfor",
                                   "Molecular ... EGFR"])
def test_short_or_partial_quote_segments_do_not_verify(quote):
    kept, dropped = agents._verify_references([{"ref_id": "G1", "quote": quote}], {"G1": NCG}, "lung_nsclc")
    assert kept == [] and dropped == 1


def test_search_reference_needs_a_whole_sentence(monkeypatch):
    frag = {**NCG, "file": "icmr/Breast_Cancer.pdf", "title": "Breast Cancer",
            "text": "^Not required if CT Thorax & Abdomen is being\nbreast cancer CECT thorax"}
    monkeypatch.setattr(agents.packs, "search", lambda role, q, cancer=None, india=3, intl=0: {"india": [frag], "international": []})
    assert agents._indian_reference("radiology", {"protocol": "breast"}, "Confirm the CECT thorax and abdomen report is final.") is None


def test_word_and_text_parts_are_not_pages():
    docx = {**NCG, "file": "ncg_india/ncg-rectal-cancer.docx", "title": "ncg rectal cancer", "page": 1, "page_end": 1}
    assert agents._page_kind(docx) == "part" and "| part 1 |" in agents._ref_label(docx)
    assert agents._page_kind(NCG) == "page" and "| p. 4 |" in agents._ref_label(NCG)
    assert agents._reference(docx, "x", "agent")["page_kind"] == "part"


def test_cancer_fit_word_starts_and_unmapped_protocols():
    direct = {**NCG, "file": "pmjay/direct-claims.pdf", "title": "direct claims"}
    assert agents._cancer_fit(direct, "colorectal_rectum") == ""  # 'rect' is not 'direct'
    assert agents._cancer_fit(HN, "head_neck") == ""  # a protocol with no cancer words yet never drops a guideline as another cancer's
    rectal = {**NCG, "file": "esmo/ESMO_2025_localised_rectal_cancer.pdf", "title": "ESMO 2025 localised rectal cancer"}
    assert agents._cancer_fit(rectal, "colorectal_rectum") == "same" and agents._cancer_fit(rectal, "lung_nsclc") == "other"


def test_brief_is_written_without_pack_or_index(monkeypatch):
    case_id = _lung_case()

    def broken(*a, **k):
        raise ValueError("pack radiology: unknown guideline folder 'xyz'")
    monkeypatch.setattr(agents.packs, "checklist_text", broken)
    monkeypatch.setattr(agents.packs, "pack", broken)
    monkeypatch.setattr(agents.guidelines, "ready", lambda: False)
    searched = []
    monkeypatch.setattr(agents.packs, "search", lambda *a, **k: searched.append(a) or {"india": [], "international": []})

    async def fake_chat(role, msgs, json_schema=None, **kw):
        if json_schema is agents.STEP_SCHEMA:
            return {"thought": "x", "tool": "search_guidelines", "input": "EGFR"}
        return {"sections": [], "not_documented": [], "points_for_review": [
            {"text": "EGFR mutation analysis is awaited.", "citations": [{"doc_id": "Dhist0009", "quote": "EGFR mutation analysis: awaited"}], "references": []},
            {"text": "Is a brain MRI indicated given the recorded stage IIIB?", "citations": [{"doc_id": "Dhist0009", "quote": "EGFR mutation analysis: awaited"}],
             "references": []}]}
    monkeypatch.setattr(agents.llm, "chat", fake_chat)

    async def go():
        return [e async for e in agents.run_agent(case_id, "radiology", max_steps=1)]
    ev = asyncio.run(go())
    brief = ev[-1]["brief"]
    assert brief["pack"] is None and searched == []  # no pack, no search while the index is loading
    assert any("still loading" in (e.get("observation") or "") for e in ev)
    assert [p["text"] for p in brief["points_for_review"]] == ["EGFR mutation analysis is awaited."] and brief["guardrail_removed"] == 1


# ---- night-v3 items 6.3 and 6.4: the streamed live answer, statement by statement -------------------------------------------
import json  # noqa: E402

from tumour_board import guardrails  # noqa: E402

CT_TEXT = "SYNTHETIC\nCECT THORAX REPORT\nSpiculated mass 3.2 cm in the right upper lobe.\nNo pleural effusion.\nReport status: FINAL"
HP_TEXT = "SYNTHETIC\nHISTOPATHOLOGY REPORT\nAdenocarcinoma, moderately differentiated.\nReport status: FINAL"
GOOD = {"text": "The CECT thorax records a spiculated mass of 3.2 cm in the right upper lobe.",
        "citations": [{"doc_id": "Dct000001", "quote": "Spiculated mass 3.2 cm in the right upper lobe"}]}
WRONG = {"text": "The CECT records a moderate pleural effusion.", "citations": [{"doc_id": "Dct000001", "quote": "Moderate pleural effusion"}]}
ADVICE = {"text": "Surgery is recommended because there is no pleural effusion.", "citations": [{"doc_id": "Dct000001", "quote": "No pleural effusion."}]}
END = {"end": True, "answer_found": True, "references": []}


def _stream_case():
    store.create_case("TB-STREAM", {"name": "SYNTHETIC, Stream Patient", "mrn": "SYN-900311", "agesex": "60 Y / M"}, "lung_nsclc", created_by="test")
    add("TB-STREAM", make_doc("Dct000001", "ct", text=CT_TEXT), make_doc("Dhist0001", "histopathology", text=HP_TEXT),
        make_doc("Doth00001", "other", text="SYNTHETIC\nLETTER\nPatient seen in OPD.\nReport status: FINAL"))
    return "TB-STREAM"


def _chunks(text, size=7):
    return [text[i:i + size] for i in range(0, len(text), size)]


class FakeModel:
    """llm.stream and llm.chat replaced: the stream yields the given chunks (and raises `fail` after them when set); chat answers the scope
    classifier with `category` and the one-shot call with `oneshot`. Records what was consumed, closed and asked."""

    def __init__(self, monkeypatch, chunks, category="in_scope", oneshot=None, fail=None):
        self.chunks, self.category, self.oneshot, self.fail = chunks, category, oneshot, fail
        self.consumed, self.closed, self.streams, self.chats = 0, False, [], []
        monkeypatch.setattr(agents.llm, "stream", self.stream)
        monkeypatch.setattr(agents.llm, "chat", self.chat)
        monkeypatch.setattr(agents.guidelines, "ready", lambda: False)

    async def stream(self, role, msgs, max_tokens=1024, temperature=0.0, audit=None):
        self.streams.append(msgs)
        try:
            for c in self.chunks:
                self.consumed += 1
                yield c
            if self.fail:
                raise self.fail
        finally:
            self.closed = True

    async def chat(self, role, msgs, json_schema=None, **kw):
        if json_schema is guardrails.CLASSIFIER_SCHEMA:
            await asyncio.sleep(0.01)  # the classifier answers after the stream has begun
            return {"category": self.category, "reason": "test"}
        self.chats.append((msgs, json_schema))
        return self.oneshot


def _lines(*objs, final_newline=True):
    text = "\n".join(json.dumps(o) for o in objs)
    return text + ("\n" if final_newline else "")


def _ask_streaming(case_id, question, role="radiology", history=None, callback=None):
    got = []

    def cb(stmt, i):
        got.append((i, stmt["text"]))
    res = asyncio.run(agents.ask(case_id, role, question, history, "dr.rao", on_statement=callback or cb))
    return res, got


@pytest.mark.parametrize("final_newline", [True, False])
def test_streamed_answer_passes_on_only_verified_statements(monkeypatch, final_newline):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD, WRONG, ADVICE, END, final_newline=final_newline)))
    a, got = _ask_streaming(case_id, "What does the CT record about the lung mass?")
    assert got == [(0, GOOD["text"])]
    assert a["status"] == "answered" and [s["text"] for s in a["statements"]] == [GOOD["text"]]
    assert a["statements"][0]["citations"][0]["doc_id"] == "Dct000001" and "note" not in a["statements"][0]
    assert [x["reason"] for x in a["removed"]] == ["quote_not_found", "guardrail"] and a["dropped_unverified"] == 1
    assert [x["text"] for x in a["removed"]] == [WRONG["text"], ADVICE["text"]]
    assert a["streamed"] is True and isinstance(a["first_seconds"], float) and a["first_seconds"] <= a["seconds"]
    assert a["kind"] == "AI agent, support only" and fm.closed and fm.chats == []  # no one-shot call
    sys_ = fm.streams[0][0]["content"]
    assert '{"end": true' in sys_ and "one JSON object on each line" in sys_ and "colleague" not in sys_
    assert fm.streams[0][-1]["content"].endswith("QUESTION FROM THE BOARD: What does the CT record about the lung mass?")
    ev = [e for e in store.read_audit(case_id) if e["kind"] == "agent_answer"]
    assert ev[-1]["streamed"] is True and ev[-1]["statements"] == 1 and ev[-1]["malformed"] == 0


def test_streamed_answer_stops_reading_after_the_end_line(monkeypatch):
    case_id = _stream_case()
    chunks = [_lines(GOOD), _lines({**END, "references": [{"ref_id": "G9", "quote": "x"}]}), "trailing words\n", _lines(WRONG)]
    fm = FakeModel(monkeypatch, chunks)
    a, got = _ask_streaming(case_id, "What does the CT record?")
    assert got == [(0, GOOD["text"])] and fm.consumed == 2 and fm.closed
    assert a["removed"] == [] and a["references"] == [] and a["references_dropped"] == 1  # an unknown passage id is never shown


def test_streamed_answer_refused_by_the_scope_check_passes_nothing_on(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD, GOOD, END)), category="prognosis")
    a, got = _ask_streaming(case_id, "Tell me about the outlook")
    assert got == [] and a["status"] == "out_of_scope" and a["category"] == "prognosis" and a["statements"] == []
    assert a["message"] == guardrails.REFUSALS["prognosis"] and fm.closed and fm.consumed < len(fm.chunks)
    assert any(e["kind"] == "guardrail_input" for e in store.read_audit(case_id))
    assert not any(e["kind"] == "agent_answer" for e in store.read_audit(case_id))


def test_rule_refusal_with_a_callback_starts_no_stream(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD, END)))
    a, got = _ask_streaming(case_id, "Which one would you pick for her?")
    assert a["status"] == "out_of_scope" and a["category"] == "treatment_recommendation" and fm.streams == [] and got == []


def test_malformed_stream_falls_back_to_the_one_shot_call_once(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, ["Here is the answer:\n```json\n", "not json at all\n", "```"],
                   oneshot={"answer_found": True, "statements": [GOOD, WRONG], "references": []})
    got = []

    async def cb(stmt, i):  # a coroutine callback is awaited
        await asyncio.sleep(0)
        got.append((i, stmt["text"]))
    a = asyncio.run(agents.ask(case_id, "radiology", "What does the CT record?", None, "dr.rao", on_statement=cb))
    assert got == [(0, GOOD["text"])] and len(fm.streams) == 1
    assert [s for _, s in fm.chats] == [agents.LIVE_SCHEMA]  # the one-shot call, once, with today's prompt
    assert "one JSON object on each line" not in fm.chats[0][0][0]["content"]
    assert [x["reason"] for x in a["removed"]] == ["malformed", "malformed", "quote_not_found"]
    assert [x["text"] for x in a["removed"][:2]] == ["Here is the answer:", "not json at all"]
    assert a["removed"][0]["reason_label"] == agents.REMOVED_REASONS["malformed"]
    assert a["status"] == "answered" and a["streamed"] is False and a["first_seconds"] is not None and a["dropped_unverified"] == 1


def test_malformed_lines_beside_good_ones_are_dropped_without_a_fallback(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD) + '{"text": "half a line\n' + _lines(END)))
    a, got = _ask_streaming(case_id, "What does the CT record?")
    assert got == [(0, GOOD["text"])] and fm.chats == [] and [x["reason"] for x in a["removed"]] == ["malformed"]
    assert a["removed"][0]["text"] == '{"text": "half a line'


def test_a_stream_that_fails_after_a_statement_is_not_restarted(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD)) + ['{"text": "The CECT'], fail=agents.llm.LLMError("reasoner unreachable"))
    got = []
    with pytest.raises(agents.llm.LLMError):
        asyncio.run(agents.ask(case_id, "radiology", "What does the CT record?", None, "dr.rao", on_statement=lambda s, i: got.append(s["text"])))
    assert got == [GOOD["text"]] and len(fm.streams) == 1 and fm.chats == [] and fm.closed
    ev = [e for e in store.read_audit(case_id) if e["kind"] == "agent_answer_failed"]
    assert ev and ev[-1]["statements"] == 1 and "reasoner unreachable" in ev[-1]["error"]


def test_a_stream_with_only_an_end_line_is_not_documented(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, [_lines({"end": True, "answer_found": False, "references": []}, final_newline=False)])
    a, got = _ask_streaming(case_id, "Is there a brain MRI report?")
    assert got == [] and fm.chats == [] and a["status"] == "not_documented" and a["first_seconds"] is None and a["streamed"] is True
    assert a["message"] == agents.NOT_DOCUMENTED


def test_without_a_callback_nothing_is_streamed(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, [], oneshot={"answer_found": True, "statements": [GOOD], "references": []})
    a = asyncio.run(agents.ask(case_id, "radiology", "What does the CT record?", None, "dr.rao"))
    assert fm.streams == [] and len(fm.chats) == 1 and a["status"] == "answered" and a["streamed"] is False
    assert a["first_seconds"] == a["seconds"]


def test_history_keeps_three_exchanges(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD, END)))
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(8)]
    _ask_streaming(case_id, "And its size?", history=hist)
    msgs = fm.streams[0]
    assert [m["content"] for m in msgs[2:-1]] == ["m2", "m3", "m4", "m5", "m6", "m7"] and msgs[0]["role"] == "system"
    assert msgs[1]["content"].startswith("DOCUMENTS:") and msgs[-1]["content"].endswith("QUESTION FROM THE BOARD: And its size?")  # the documents first (item 6.4)


def test_a_statement_from_another_specialtys_record_gets_the_note(monkeypatch):
    case_id = _stream_case()
    hp = {"text": "The histopathology records adenocarcinoma, moderately differentiated.",
          "citations": [{"doc_id": "Dhist0001", "quote": "Adenocarcinoma, moderately differentiated."}]}
    letter = {"text": "The letter records that the patient was seen in OPD.", "citations": [{"doc_id": "Doth00001", "quote": "Patient seen in OPD."}]}
    FakeModel(monkeypatch, _chunks(_lines(GOOD, hp, letter, END)))
    seen = []
    a, _ = _ask_streaming(case_id, "What do the reports record?", callback=lambda s, i: seen.append(s.get("note")))
    notes = [s.get("note") for s in a["statements"]]
    assert notes == [None, "This is a histopathology record; the Pathology agent can say more.", None]  # an unknown type gets no note
    assert seen == notes  # the callback gets the note too (shown, never spoken)
    a, _ = _ask_streaming(case_id, "What does the CT record?", role="pathology")
    assert a["statements"][0]["note"] == "This is a CT record; the Radiology agent can say more."
    note = agents._note_maker(case_id, "nuclear_medicine")
    assert note({"citations": [{"doc_id": "Dct000001"}]}) == "This is a CT record; the Radiology agent can say more."
    assert note({"citations": [{"doc_id": "Dnope0000"}]}) is None and note({"citations": []}) is None
    assert agents._type_phrase("mri") == "an MRI" and agents._type_phrase("bone_marrow") == "a bone marrow"


@pytest.mark.parametrize("line,kind", [
    ("", "skip"), ("```json", "skip"), ("[", "skip"),
    ('{"text": "x", "citations": []}', "statement"), ('{"text": "x", "citations": []},', "statement"),
    ('{"end": true, "answer_found": false, "references": []}', "end"),
    ('{"answer_found": true, "statements": [], "references": []}', "whole"),
    ('{"text": "", "citations": []}', "malformed"), ('{"text": "x"}', "malformed"), ("[1, 2]", "malformed"), ("The CT shows", "malformed"),
])
def test_line_protocol(line, kind):
    assert agents._parse_line(line)[0] == kind


def test_a_whole_answer_on_one_line_is_read(monkeypatch):
    case_id = _stream_case()
    fm = FakeModel(monkeypatch, [json.dumps({"answer_found": True, "statements": [GOOD, WRONG], "references": []})])
    a, got = _ask_streaming(case_id, "What does the CT record?")
    assert got == [(0, GOOD["text"])] and fm.chats == [] and a["streamed"] is True


def test_warm_sends_the_documents_block_once_per_signature_and_the_live_prompt_shares_it(monkeypatch):
    """Item 6.4: the warm call's documents message equals the first user message of a later streamed answer (the reasoner's prefix
    cache then holds it); a second warm for the same Case File signature is skipped; a failed warm is audited and never raises."""
    case_id = _stream_case()
    chats = []

    async def fake_chat(role, msgs, max_tokens=None, **kw):
        chats.append((msgs, max_tokens, kw.get("purpose")))
        return ""
    monkeypatch.setattr(agents.llm, "chat", fake_chat)
    agents._WARM.clear()
    secs = asyncio.run(agents.warm(case_id, "radiology"))
    assert secs is not None and len(chats) == 1
    msgs, max_tokens, purpose = chats[0]
    assert max_tokens == 1 and purpose == "agent warm" and msgs[0]["role"] == "system" and msgs[1]["content"].startswith("DOCUMENTS:")
    assert asyncio.run(agents.warm(case_id, "radiology")) is None and len(chats) == 1  # the same signature: skipped
    fm = FakeModel(monkeypatch, _chunks(_lines(GOOD, END)))
    _ask_streaming(case_id, "What size is the lesion?")
    live = fm.streams[0]
    assert live[0] == msgs[0] and live[1] == msgs[1]  # the same prefix, token for token
    assert "QUESTION FROM THE BOARD" in live[-1]["content"] and "DOCUMENTS:" not in live[-1]["content"]
    kinds = [e["kind"] for e in store.read_audit(case_id)]
    assert "agent_warm" in kinds

    async def down(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(agents.llm, "chat", down)
    agents._WARM.clear()
    assert asyncio.run(agents.warm(case_id, "pathology")) is None
    assert "agent_warm_failed" in [e["kind"] for e in store.read_audit(case_id)]
    with pytest.raises(ValueError):
        asyncio.run(agents.warm(case_id, "cardiology"))
