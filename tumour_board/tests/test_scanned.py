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


# ---- V1 item 8.4: word boxes on the scan image ----

from tumour_board import extract  # noqa: E402

LINE = "PD-L1 (22C3) Tumour Proportion Score: 60%"


def _words(text, y0=0.40, y1=0.43, line=3):
    """Synthetic engine words for one line of text, laid out left to right (the 8.3 word format)."""
    out, x = [], 0.05
    for t in text.split():
        w = 0.012 * len(t)
        out.append([t, round(x, 4), y0, round(x + w, 4), y1, 95, line]); x += w + 0.01
    return out


def _engine_page(text=LINE, words=None):
    return {"text": text, "method": SCAN, "ocr_engine": {"engine": "tesseract", "version": "5", "lang": "eng", "size": [1700, 900], "text": text,
                                                          "words": _words(text) if words is None else words}}


def test_box_map_added_once_to_engine_pages_only():
    pages = [_engine_page(), {"text": "typed", "method": "text-layer"}]
    assert extract.add_box_maps(pages) is True
    assert pages[0]["box_map"] and "box_map" not in pages[1]
    assert extract.add_box_maps(pages) is False  # kept, not recomputed


def test_quote_boxes_cover_the_quote_line():
    pages = [_engine_page()]; extract.add_box_maps(pages)
    s = LINE.index("Score"); boxes = extract.quote_boxes(pages, {"page": 0, "start": s, "end": len(LINE)})
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert y0 < 0.40 < 0.43 < y1 and x0 < x1


def test_no_box_when_the_engine_read_another_number():
    pages = [_engine_page(words=_words(LINE.replace("60%", "80%")))]; extract.add_box_maps(pages)
    s = LINE.index("60%")
    assert extract.quote_boxes(pages, {"page": 0, "start": s, "end": s + 3}) == []


def test_no_box_without_engine_words_or_location():
    assert extract.quote_boxes([{"text": LINE, "method": SCAN}], {"page": 0, "start": 0, "end": 5}) == []
    assert extract.quote_boxes([], {"page": 0, "start": 0, "end": 5}) == []
    assert extract.quote_boxes([_engine_page()], None) == []


def test_extracted_scan_fact_stores_its_boxes(run):
    text = util.TEXT
    words = [w for i, line in enumerate(text.split("\n")) for w in _words(line, 0.05 + i * 0.05, 0.08 + i * 0.05, i)]
    doc = run(page_extra={"method": SCAN, "ocr_engine": {"engine": "tesseract", "words": words}})
    hb = doc["facts"]["haemoglobin"]
    assert hb["source_method"] == SCAN and len(hb["boxes"]) == 1
    assert store.get_doc("TB-UNIT", doc["doc_id"])["pages"][0]["box_map"]  # kept on the stored page for citations


def test_confirm_value_need_carries_the_boxes(unit_case):
    d = _hist()
    d["facts"]["pdl1"]["boxes"] = [[0.1, 0.4, 0.5, 0.43]]
    util.add(unit_case, d, _ct())
    need = next(n for n in util.req(rules.evaluate(unit_case), "pdl1")["needs"] if n["type"] == "confirm_value")
    assert need["boxes"] == [[0.1, 0.4, 0.5, 0.43]]


def test_aadhaar_boxes_and_masked_preview(tmp_path):
    from PIL import Image
    words = _words("Aadhaar: XXXX XXXX 2200")
    doc = {"pages": [_engine_page("Aadhaar: XXXX XXXX 2200", words)]}
    boxes = scanned.aadhaar_boxes(doc, 0)
    assert len(boxes) == 2  # the two masked groups; the last four digits stay visible, as in the text
    p = tmp_path / "scan.png"; Image.new("RGB", (1000, 500), "white").save(p)
    data, kind = scanned.preview_bytes(p, doc)
    assert kind == "image/png"
    im = Image.open(__import__("io").BytesIO(data))
    x0, y0, x1, y1 = boxes[0]
    assert im.getpixel((int((x0 + x1) / 2 * 1000), int((y0 + y1) / 2 * 500))) == (0, 0, 0)
    assert im.getpixel((5, 5)) == (255, 255, 255)
    assert scanned.preview_bytes(p, {"pages": [_engine_page()]}) is None  # nothing to mask: the file is served as stored
    assert scanned.aadhaar_boxes({"pages": [{"text": "x"}]}, 0) == [] and scanned.aadhaar_boxes({}, 3) == []


# ---- review fixes (Phase 8) ----

def test_undoing_the_confirmation_asks_again(unit_case):
    util.add(unit_case, _hist(), _ct())
    rec = confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 60%"}, "", by="Dr. Rao")
    assert util.req(rules.evaluate(unit_case), "pdl1")["status"] == "satisfied"
    confirm.undo(unit_case, rec["id"], "Dr. Rao")
    assert util.req(rules.evaluate(unit_case), "pdl1")["status"] == "needs_confirmation"


def test_a_waiver_beats_the_scan_request(unit_case):
    util.add(unit_case, _hist(), _ct())
    confirm.record(unit_case, "waive", "pdl1", {}, "e2e: not needed for this Case File", by="Dr. Rao")
    r = util.req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "waived" and not r.get("needs")


def test_no_scan_request_while_the_record_is_open_at_level_1(unit_case):
    d = util.make_doc("Dhist0001", "histopathology", facts={"histologic_type": util.fact("Adenocarcinoma"), "recorded_stage": util.fact("pT2 N1")})
    d["pages"][0]["method"] = SCAN
    d["identity"] = "mismatch_or_missing"  # Level 1: the record may not be this patient's
    util.add(unit_case, d, _ct())
    real = protocol.get
    p = util.unit_protocol(); p["mandatory"][0]["required_facts"] = ["histologic_type", "recorded_stage"]
    import pytest
    mp = pytest.MonkeyPatch(); mp.setattr(protocol, "get", lambda pid: p if pid == "unit" else real(pid))
    try:
        r = util.req(rules.evaluate(unit_case), "histopathology")
    finally:
        mp.undo()
    assert r["level"] == 1 and not [n for n in r.get("needs") or [] if n["type"] == "confirm_value"]


def _masked_doc(n_pages=1, page=0):
    words = _words("Aadhaar: XXXX-XXXX-2200 UHID SYN-1")
    pages = [{"text": "x", "method": SCAN} for _ in range(n_pages)]
    pages[page] = _engine_page("Aadhaar: XXXX-XXXX-2200 UHID SYN-1", words)
    pages[page]["ocr_engine"]["masked_words"] = [1]
    return {"pages": pages}, words[1]


def _pixel(data, box, frac=(0.5, 0.5)):
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    return im.getpixel((int((box[1] + (box[3] - box[1]) * frac[0]) * im.size[0]), int((box[2] + (box[4] - box[2]) * frac[1]) * im.size[1])))


def test_pdf_page_preview_is_masked(tmp_path):
    from PIL import Image
    p = tmp_path / "scan.pdf"
    Image.new("RGB", (800, 1100), "white").save(p, save_all=True, append_images=[Image.new("RGB", (800, 1100), "white")])
    doc, w = _masked_doc(2, page=1)
    data, kind = scanned.preview_bytes(p, doc, render=True, page=1)
    assert kind == "image/png" and _pixel(data, w) == (0, 0, 0)
    data, _ = scanned.preview_bytes(p, doc, render=True, page=0)  # the other page has nothing to mask
    assert _pixel(data, w) == (255, 255, 255)
    assert scanned.preview_bytes(p, doc, render=True, page="x")[1] == "image/png"  # a bad page number is page 1, never a crash


def test_tiff_frames_are_rendered_and_masked(tmp_path):
    from PIL import Image
    p = tmp_path / "scan.tif"
    Image.new("RGB", (800, 1100), "white").save(p, save_all=True, append_images=[Image.new("RGB", (800, 1100), "white")])
    doc, w = _masked_doc(2, page=1)
    data, kind = scanned.preview_bytes(p, doc, render=True, page=1)
    assert kind == "image/png" and _pixel(data, w) == (0, 0, 0)
    data, kind = scanned.preview_bytes(p, {"pages": []})  # a TIFF is always served as PNG (browsers cannot show TIFF)
    assert kind == "image/png"


def test_exif_rotated_photo_is_served_upright(tmp_path):
    import io
    from PIL import Image
    p = tmp_path / "photo.jpg"
    im = Image.new("RGB", (400, 300), "white"); ex = im.getexif(); ex[274] = 6
    im.save(p, exif=ex)
    data, kind = scanned.preview_bytes(p, {"pages": [{"text": "x", "method": SCAN}]})
    assert kind == "image/png" and Image.open(io.BytesIO(data)).size == (300, 400)


def test_a_pdf_with_no_pages_is_served_as_stored(tmp_path, monkeypatch):
    import pypdfium2 as pdfium

    class Empty:
        def __len__(self): return 0
        def close(self): pass
    monkeypatch.setattr(pdfium, "PdfDocument", lambda path: Empty())
    p = tmp_path / "empty.pdf"; p.write_bytes(b"%PDF-1.4")
    assert scanned.preview_bytes(p, {}, render=True) is None
