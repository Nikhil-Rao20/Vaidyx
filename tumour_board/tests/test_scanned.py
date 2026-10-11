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


# ---- V1 item 8.2: critical values from scans need one confirmation against the image ----

from tumour_board import confirm, protocol  # noqa: E402


def _ct():
    return util.make_doc("Dct000001", "ct", region="chest", facts={"lesion_size": util.fact("3.2 cm")})


def _hist(doc_id="Dhist0001", pdl1="TPS 60%", method=SCAN, date="2026-09-01"):
    d = util.make_doc(doc_id, "histopathology", date=date, facts={"histologic_type": util.fact("Adenocarcinoma"), "pdl1": util.fact(pdl1)})
    d["pages"][0]["method"] = method
    return d


def test_the_proposed_fields_are_critical():
    crit = sorted(k for k, v in protocol.facts().items() if v.get("critical"))
    assert crit == sorted(["recorded_stage", "pdl1", "egfr", "alk", "ros1", "er", "pr", "her2", "ki67", "mmr", "ras_braf"])


def test_needs_scan_confirmation_rule():
    spec = {"critical": True}
    assert scanned.needs_scan_confirmation({"verification": "verified", "source_method": SCAN}, spec)
    assert not scanned.needs_scan_confirmation({"verification": "confirmed", "source_method": SCAN}, spec)
    assert not scanned.needs_scan_confirmation({"verification": "verified", "source_method": "text-layer"}, spec)
    assert not scanned.needs_scan_confirmation({"verification": "verified", "source_method": SCAN}, {})
    assert not scanned.needs_scan_confirmation({"verification": "needs_review", "source_method": SCAN}, spec)


def test_scanned_pdl1_needs_confirmation_then_confirm_satisfies(unit_case):
    util.add(unit_case, _hist(), _ct())
    g = rules.evaluate(unit_case)
    r = util.req(g, "pdl1")
    assert r["status"] == "needs_confirmation" and r["level"] == 2 and not g["passed"]
    assert r["level2"]["status"] == "needs_confirmation"
    need = [n for n in r["needs"] if n["type"] == "confirm_value"]
    assert need == [{"type": "confirm_value", "doc_id": "Dhist0001", "fact": "pdl1", "value": "TPS 60%", "page": 0, "start": 0, "end": 7}]
    assert any(p.startswith('Confirm PD-L1 against the scan image: "TPS 60%"') for p in r["problems"])
    assert r["source_doc_id"] == "Dhist0001"  # the request goes to the department that uploaded the scan
    assert util.req(g, "histopathology")["status"] == "satisfied"  # histologic type is not a critical field
    confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 60%"}, "", by="Dr. Rao")
    g = rules.evaluate(unit_case)
    r = util.req(g, "pdl1")
    assert r["status"] == "satisfied" and g["passed"]
    assert r["evidence"] == [{"doc_id": "Dhist0001", "fact": "pdl1", "value": "TPS 60%", "quote": ""}]


def test_confirmation_survives_reprocess(unit_case):
    util.add(unit_case, _hist(), _ct())
    confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 60%"}, "", by="Dr. Rao")
    util.add(unit_case, _hist())  # the document written again, as a re-process does
    assert util.req(rules.evaluate(unit_case), "pdl1")["status"] == "satisfied"


def test_text_layer_pdl1_needs_no_confirmation(unit_case):
    util.add(unit_case, _hist(method="text-layer"), _ct())
    r = util.req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "satisfied" and not [n for n in r.get("needs") or [] if n["type"] == "confirm_value"]


def test_same_value_in_a_digital_record_corroborates_the_scan(unit_case):
    util.add(unit_case, _hist(), _ct(), _hist("Dihc00001", method="text-layer", date="2026-08-30"))
    r = util.req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "satisfied"
    assert [e["doc_id"] for e in r["evidence"] if e.get("fact") == "pdl1"] == ["Dihc00001"]


def test_a_newer_different_scanned_value_still_needs_confirmation(unit_case):
    util.add(unit_case, _hist(pdl1="TPS 80%", date="2026-09-05"), _ct(), _hist("Dihc00001", method="text-layer", date="2026-08-30"))
    r = util.req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "needs_confirmation"
    assert [n["value"] for n in r["needs"] if n["type"] == "confirm_value"] == ["TPS 80%"]
