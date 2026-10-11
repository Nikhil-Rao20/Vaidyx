"""V1 item 8.1: facts and citations carry the method of the page their quote sits on ("from scan (OCR)" in the UI)."""
import copy

from tumour_board import board, qa, rules, scanned, store
from tumour_board.tests import util

SCAN = "vision-transcription"


def _scan_doc(doc_id="DSCAN1", doc_type="histopathology", text=None, facts=None, method=SCAN):
    d = util.make_doc(doc_id, doc_type, facts=facts or {}, text=text)
    d["pages"][0]["method"] = method
    return d


# ---- helpers ----

def test_fact_source_method_is_the_page_of_the_quote():
    pages = [{"text": "a", "method": "text-layer"}, {"text": "b", "method": SCAN}]
    assert scanned.fact_source_method(pages, {"location": {"page": 1, "start": 0, "end": 1}}) == SCAN
    assert scanned.fact_source_method(pages, {"location": {"page": 0, "start": 0, "end": 1}}) == "text-layer"


def test_confirmed_value_keeps_the_model_location_page():
    pages = [{"text": "a", "method": "text-layer"}, {"text": "b", "method": SCAN}]
    f = {"verification": "confirmed", "location": None, "model_location": {"page": 1, "start": 0, "end": 1}}
    assert scanned.fact_source_method(pages, f) == SCAN


def test_value_without_location_takes_the_single_document_method_only():
    assert scanned.fact_source_method([{"method": SCAN}, {"method": SCAN}], {"location": None}) == SCAN
    assert scanned.fact_source_method([{"method": SCAN}, {"method": "text-layer"}], {"location": None}) == ""
    assert scanned.fact_source_method([], {}) == ""


def test_location_outside_the_pages_falls_back_to_the_document():
    assert scanned.fact_source_method([{"method": SCAN}], {"location": {"page": 7}}) == SCAN
    assert scanned.fact_source_method([{"method": SCAN}], {"location": {"page": True}}) == SCAN  # never a bool as an index


def test_scan_pages_lists_only_vision_pages():
    assert scanned.scan_pages([{"method": "text-layer"}, {"method": SCAN}, {"method": SCAN}, "x"]) == [1, 2]
    assert scanned.scan_pages(None) == []


def test_with_source_methods_fills_old_documents_without_mutating():
    d = _scan_doc(facts={"pdl1": util.fact("TPS 60%")})
    d["facts"]["pdl1"]["alternatives"] = [{"value": "TPS 6%", "quote": "TPS 6%", "location": {"page": 0, "start": 0, "end": 6}}]
    before = copy.deepcopy(d)
    out = scanned.with_source_methods(d)
    assert d == before
    assert out["facts"]["pdl1"]["source_method"] == SCAN
    assert out["facts"]["pdl1"]["alternatives"][0]["source_method"] == SCAN


def test_with_source_methods_keeps_a_stored_method_and_returns_the_same_doc():
    d = _scan_doc(facts={"pdl1": {**util.fact("TPS 60%"), "source_method": "text-layer"}})
    assert scanned.with_source_methods(d) is d
    assert scanned.with_source_methods({"facts": {}}) == {"facts": {}}


# ---- extraction ----

def test_extracted_facts_carry_the_page_method(run):
    doc = run(page_extra={"method": SCAN})
    assert doc["facts"]["haemoglobin"]["source_method"] == SCAN
    doc = run()
    assert doc["facts"]["haemoglobin"]["source_method"] == "text-layer"


# ---- read side: gate, Q&A citations, session export ----

def test_case_docs_and_resolved_facts_say_from_scan(unit_case):
    util.add(unit_case, _scan_doc(facts={"histologic_type": util.fact("Adenocarcinoma")}))
    docs = rules.case_docs(unit_case)
    assert docs[0]["facts"]["histologic_type"]["source_method"] == SCAN
    assert rules.resolve_facts(docs)["histologic_type"]["current"]["source_method"] == SCAN
    assert "source_method" not in store.get_doc(unit_case, "DSCAN1")["facts"]["histologic_type"]  # nothing written back


def test_gate_evidence_carries_the_source_method(unit_case):
    util.add(unit_case, _scan_doc(facts={"histologic_type": util.fact("Adenocarcinoma")}))
    ev = [e for e in util.req(rules.evaluate(unit_case), "histopathology")["evidence"] if e.get("fact")]
    assert ev and ev[0]["source_method"] == SCAN


def test_qa_citations_on_a_scanned_page_say_so(unit_case):
    text = "SYNTHETIC\nHISTOPATHOLOGY REPORT\nDiagnosis: Adenocarcinoma, moderately differentiated\nReport status: FINAL"
    util.add(unit_case, _scan_doc(text=text), _scan_doc("DTEXT1", text=text.replace("HISTOPATHOLOGY", "BIOPSY"), method="text-layer"))
    kept, dropped = qa.verify(unit_case, [{"text": "Adenocarcinoma.", "citations": [{"doc_id": "DSCAN1", "quote": "Diagnosis: Adenocarcinoma"}]},
                                          {"text": "Adenocarcinoma.", "citations": [{"doc_id": "DTEXT1", "quote": "Diagnosis: Adenocarcinoma"}]}])
    assert not dropped
    assert kept[0]["citations"][0]["source_method"] == SCAN
    assert kept[1]["citations"][0]["source_method"] == "text-layer"


def test_session_export_citation_names_the_scan():
    assert "from scan (OCR)" in board._cite({"doc_title": "PET-CT", "quote": "SUVmax 8.2", "source_method": SCAN})
    assert "from scan" not in board._cite({"doc_title": "PET-CT", "quote": "SUVmax 8.2", "source_method": "text-layer"})
    assert "from scan" not in board._cite({"doc_title": "PET-CT", "quote": "SUVmax 8.2"})
