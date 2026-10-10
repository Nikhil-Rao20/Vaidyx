"""extract.process_document with the model calls replaced by fakes: status, signature, date fallbacks, identity,
grounding of extracted values, pending state, polarity and the two-read OCR downgrade. Also ingest.ocr_page and the
negation cues (the known non- bug is in test_known_issues.py)."""
import asyncio, re
from pathlib import Path

import pytest

from tumour_board import extract, ingest, qa, store
from tumour_board.tests import util
from tumour_board.tests.util import CLS, RAW, TEXT


def test_status_signature_and_date(run):
    d = run()
    c = d["classification"]
    assert d["state"] == "ready" and d["processed"]
    assert (c["status"], c["status_quote"], c["signed"]) == ("FINAL", "Report status: FINAL", "yes")
    assert c["signature_quote"] == "Reported by: Dr. A. Menon, Consultant Pathologist"
    assert c["report_date_iso"] == "2026-09-04"


def test_filename_date_is_a_suggestion_only(run):
    """V1 item 3.1: the filename never sets the date; a document with no labelled date is unconfirmed and the filename is offered to the dialog."""
    c = run(cls={"report_date": ""}, filename="cbc_2026-09-03.txt")["classification"]
    assert c["report_date_iso"] == "2026-09-04" and c["date_suggestion"] == "2026-09-03" and not c["date_unconfirmed"]  # "Reported on 04/09/2026" is in the text
    c = run(text=TEXT.replace("Reported on 04/09/2026", ""), cls={"report_date": ""}, filename="cbc_2026-09-03.txt")["classification"]
    assert c["date_unconfirmed"] and c["report_date_iso"] == "" and c["event_date_iso"] == "" and c["date_suggestion"] == "2026-09-03"


def test_labelled_event_and_report_dates(run):
    text = TEXT.replace("Reported on 04/09/2026", "Collected on 02/09/2026\nReported on 04/09/2026")
    c = run(text=text, cls={"report_date": ""})["classification"]
    assert (c["report_date_iso"], c["event_date_iso"]) == ("2026-09-04", "2026-09-02")
    assert not c["report_date_assumed"] and not c["event_date_assumed"]
    assert c["event_date_label"] == "Collected on" and c["event_date_quote"] == "Collected on 02/09/2026"


def test_report_only_stands_in_for_event_and_is_marked(run):
    c = run()["classification"]
    assert c["report_date_iso"] == c["event_date_iso"] == "2026-09-04" and c["event_date_assumed"] and not c["report_date_assumed"]


def test_report_date_is_not_taken_from_dob(run):  # was a 3.1 strict xfail in test_known_issues.py
    text = TEXT.replace("Test Patient\n", "Test Patient\nDOB 12/03/1995\n")
    c = run(text=text, cls={"report_date": ""})["classification"]
    assert c["report_date_iso"] == "2026-09-04"
    assert any(x["iso"] == "1995-03-12" and x["kind"] == "ignore" for x in c["dates"])


def test_model_date_used_only_if_found_in_text(run):  # was a 3.1 strict xfail in test_known_issues.py
    assert run(cls={"report_date": "01-Jan-2026"})["classification"]["report_date_iso"] == "2026-09-04"


def test_date_flags_and_dob_from_the_case_file(run):
    text = TEXT.replace("Reported on 04/09/2026", "Reported on 04/09/2099")
    c = run(text=text)["classification"]
    assert "report date is after today" in c["date_flags"]
    c = run(patient={"mrn": "SYN-900001", "name": "SYNTHETIC, Test Patient", "dob": "01/01/2030"})["classification"]
    assert any("before the date of birth" in f for f in c["date_flags"])


def test_model_status_quote_used_only_when_found(run):
    text = TEXT.replace("Report status: FINAL\n", "Status Final, copy 2\n")
    assert run(text=text, cls={"status_quote": "Status Final"})["classification"]["status"] == "FINAL"
    assert run(text=text, cls={"status_quote": "Report status: FINAL"})["classification"]["status"] == "UNSTATED"


def test_model_signature_quote_kept_only_when_found(run):
    text = "SYNTHETIC\nHAEMATOLOGY REPORT\nHaemoglobin 11.8 g/dL\nUHID SYN-900001"
    assert run(text=text, cls={"signature_quote": "Signed: Dr. X"})["classification"]["signature_quote"] == ""


def test_unverified_patient_id_is_moved_aside(run):
    c = run(cls={"patient_id": "SYN-123456"})["classification"]
    assert c["patient_id"] == "" and c["patient_id_unverified"] == "SYN-123456"


def test_identity(run):
    assert run()["identity"] == "match"
    assert run(text=TEXT.replace("SYN-900001", ""))["identity"] == "name_match"
    assert run(patient={"mrn": "SYN-111111", "name": "SYNTHETIC, Other Person"})["identity"] == "id_differs"  # the document prints a UHID this Case File does not know
    assert run(text=TEXT.replace("SYN-900001", "").replace("SYNTHETIC, Test Patient", "Some Other Name"), cls={"patient_name": "", "patient_id": ""})["identity"] == "mismatch_or_missing"


def test_facts_grounded(run):
    f = run()["facts"]
    assert set(f) == {"haemoglobin", "wbc", "platelets", "creatinine"}  # bilirubin not found: not stored
    hb = f["haemoglobin"]
    assert (hb["verification"], hb["state"], hb["polarity"], hb["quote"]) == ("verified", "present", "affirmed", "Haemoglobin 11.8 g/dL")
    assert TEXT[hb["location"]["start"]:hb["location"]["end"]] == hb["quote"]
    assert (f["wbc"]["verification"], f["wbc"]["state"], f["wbc"]["polarity"]) == ("verified", "pending", "negated")
    assert f["platelets"]["verification"] == "verified" and f["platelets"]["quote"] == "2.45 lakhs/cumm"  # value itself is the evidence
    assert f["platelets"]["model_quote"] == "Platelet count 2.45 lakhs/cumm"
    assert f["creatinine"]["verification"] == "unverified" and f["creatinine"]["reason"] == "quote not found in document"


def test_facts_audited(run, unit_case):
    run()
    ev = [e for e in store.read_audit(unit_case) if e["kind"] == "fact_verification"]
    assert {e["fact"]: e["result"] for e in ev} == {"haemoglobin": "verified", "wbc": "verified", "platelets": "verified", "creatinine": "unverified"}


def test_ocr_uncertain_number_needs_review(run):
    """A page read before the line check (V1 item 3.3) carries only the per-page number list: still honoured."""
    f = run(page_extra={"method": "vision-transcription", "ocr_uncertain_numbers": ["11.8"]})["facts"]
    assert f["haemoglobin"]["verification"] == "needs_review"
    assert f["haemoglobin"]["reason"] == "the two OCR reads of this page disagree on a number in this value"
    assert f["platelets"]["verification"] == "verified"


def test_ocr_uncertain_span_on_the_quoted_line_needs_review(run):
    """The two reads disagree on the haemoglobin line: that value needs review; the platelet line agrees (V1 item 3.3)."""
    s = util.TEXT.index("Haemoglobin 11.8 g/dL")
    spans = [{"start": s, "end": s + len("Haemoglobin 11.8 g/dL"), "line": "Haemoglobin 11.8 g/dL", "numbers": ["11.3", "11.8"], "reason": ingest.OCR_NUMBER_DISAGREES}]
    f = run(page_extra={"method": "vision-transcription", "ocr_uncertain_spans": spans, "ocr_uncertain_numbers": ["11.3", "11.8"]})["facts"]
    assert f["haemoglobin"]["verification"] == "needs_review" and f["haemoglobin"]["reason"] == "OCR check: " + ingest.OCR_NUMBER_DISAGREES
    assert f["platelets"]["verification"] == "verified"


def test_value_on_a_flagged_line_needs_review(run):
    """A value quoted from a line in Hindi / regional script or with illegible parts goes to a person (V1 item 3.6); the other lines are untouched."""
    text = util.TEXT.replace("Haemoglobin 11.8 g/dL", "Haemoglobin 11.8 g/dL (हीमोग्लोबिन)")
    pages = ingest.page_flags(text)
    assert pages["flags"] == ["contains Hindi / regional text (Devanagari)"]
    raw = {**util.RAW, "haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Haemoglobin 11.8 g/dL"}}
    f = run(text=text, raw=raw, page_extra=pages)["facts"]
    assert f["haemoglobin"]["verification"] == "needs_review"
    assert f["haemoglobin"]["reason"] == "the quoted line contains Hindi / regional text (Devanagari): verify against the source"
    assert f["platelets"]["verification"] == "verified"
    text2 = util.TEXT.replace("Platelets 2.45 lakhs/cumm", "Platelets 2.45 lakhs/cumm [illegible]")
    f2 = run(text=text2, raw={**util.RAW, "platelets": {"found": True, "value": "2.45 lakhs/cumm", "quote": "Platelets 2.45 lakhs/cumm"}}, page_extra=ingest.page_flags(text2))["facts"]
    assert f2["platelets"]["verification"] == "needs_review" and f2["platelets"]["reason"] == "the quoted line handwriting / illegible parts: verify against the source"
    assert f2["haemoglobin"]["verification"] == "verified"


def test_ocr_single_digit_elsewhere_on_the_page_does_not_touch_other_values(run):
    """Single digits now count in the OCR check, but only the line they sit on is uncertain: a list marker slip elsewhere leaves the lab values verified."""
    s = util.TEXT.index("Patient SYNTHETIC")
    spans = [{"start": s, "end": s + 7, "line": "Patient", "numbers": ["1"], "reason": ingest.OCR_ONE_READ_ONLY}]
    f = run(page_extra={"method": "vision-transcription", "ocr_uncertain_spans": spans, "ocr_uncertain_numbers": ["1"]})["facts"]
    assert f["haemoglobin"]["verification"] == "verified" and f["platelets"]["verification"] == "verified"


def test_no_readable_text_is_error(run):
    d = run(text="   ")
    assert d["state"] == "error" and d["error"] == "no readable text"


def test_model_failure_is_error(run, monkeypatch, unit_case):
    async def boom(t, audit=None):
        raise TimeoutError("reader timed out")
    monkeypatch.setattr(extract, "classify", boom)
    doc = store.add_document_file(unit_case, "x.txt", b"synthetic")
    d = asyncio.run(extract.process_document(unit_case, doc["doc_id"], "lung_nsclc"))
    assert d["state"] == "error" and d["error"] == "TimeoutError: reader timed out"
    assert store.get_doc(unit_case, doc["doc_id"])["state"] == "error"


# ---- two-read OCR check ------------------------------------------------------------------------------------
def _ocr(monkeypatch, full, second):
    async def fake(png, audit=None, max_side=None):
        return second if max_side else full
    monkeypatch.setattr(ingest, "ocr_image", fake)
    return asyncio.run(ingest.ocr_page(b"png"))


def test_ocr_page_flags_numbers_in_one_read_only(monkeypatch):
    p = _ocr(monkeypatch, "Hb 11.8 g/dL\nPlatelets 2,45,000", "Hb 11.3 g/dL\nPlatelets 245000")
    assert p["text"] == "Hb 11.8 g/dL\nPlatelets 2,45,000" and p["ocr_reads"] == 2
    assert p["ocr_uncertain_numbers"] == ["11.3", "11.8"]  # commas are ignored: 2,45,000 == 245000


def test_ocr_page_agreeing_reads_have_no_uncertain_numbers(monkeypatch):
    assert "ocr_uncertain_numbers" not in _ocr(monkeypatch, "Hb 11.8 g/dL", "Hb 11.8 g/dL")


# ---- negation and pending cues: only real result negations; "non-" alone is not one (V1 item 1.1) ----------
@pytest.mark.parametrize("s", ["HIV non-reactive", "non-reactive", "HBsAg nonreactive", "EGFR mutation not detected", "Negative",
                               "No evidence of metastasis", "HER2 non-amplified", "HER2 non amplified", "absent", "Fusion non-detected", "HBV DNA non-detectable"])
def test_negation_cues(s):
    assert extract.NEGATED_RE.search(s) and qa.NEGATION.search(s)


@pytest.mark.parametrize("s", ["Positive", "EGFR exon 19 deletion detected", "Adenocarcinoma, acinar predominant", "TPS 60%",
                               "Non-small cell carcinoma, adenocarcinoma type", "NSCLC, non-squamous", "Non-Hodgkin lymphoma",
                               "Nonspecific inflammation", "non-mucinous adenocarcinoma",
                               "Invasive breast carcinoma of no special type (ductal).", "Invasive carcinoma, no special type, grade 2"])
def test_affirmed_values(s):
    assert not extract.NEGATED_RE.search(s) and not qa.NEGATION.search(s)


def test_nsclc_answer_gets_no_negation_flag():
    assert not qa.polarity_flag("The histopathology records NSCLC.", ["Non-small cell carcinoma of lung"])


def test_real_negation_in_quote_still_flags_an_affirmed_answer():
    assert qa.polarity_flag("EGFR mutation detected.", ["EGFR mutation not detected"])
    assert qa.polarity_flag("HIV reactive.", ["HIV non-reactive"])


@pytest.mark.parametrize("s,pending", [("Pending", True), ("result awaited", True), ("Not reported", True), ("sent to reference laboratory", True),
                                       ("Will follow", True), ("60%", False), ("Negative", False)])
def test_pending_cue(s, pending):
    assert bool(extract.PENDING_RE.search(s)) == pending


def test_polarity_flag():
    assert qa.polarity_flag("Metastasis is present", ["No evidence of metastasis"])
    assert not qa.polarity_flag("No metastasis is documented", ["No evidence of metastasis"])
    assert not qa.polarity_flag("TPS 60%", [])


# ---- long documents: windowed extraction (V1 item 3.4) --------------------------------------------------------------
LONG = Path(__file__).resolve().parent / "fixtures" / "long_discharge_summary.txt"  # SYNTHETIC, about 25,000 characters, pages split by \f
PATTERNS = {"ecog": r"ECOG performance status: (\d)", "haemoglobin": r"Haemoglobin (\d+(?:\.\d+)? g/dL)"}
TODAY_PROMPT = ("Find these fields in the document.\n{spec}\n\nRules:\n"
                "1. value: copy the value exactly as written in the document (keep units, wording such as 'Pending' or 'Not reported').\n"
                "2. quote: copy the shortest complete line or phrase from the document that contains the value, character for character.\n"
                "3. If the field is not written in this document, set found=false and leave value and quote empty. Do not guess, infer or calculate.\n\n"
                "DOCUMENT:\n{text}")


def _window_chat(sent):
    """A fake extractor that answers only from the document text in the prompt it is given (first match of each field's pattern)."""
    async def chat(role, msgs, json_schema=None, purpose="", **kw):
        user = msgs[-1]["content"]
        body = re.search(r"\nDOCUMENT[^\n]*:\n(.*)\Z", user, re.S).group(1)
        sent.append({"prompt": user, "body": body, "purpose": purpose})
        out = {}
        for f in json_schema["required"]:
            m = re.search(PATTERNS.get(f, r"(?!)"), body)
            out[f] = {"found": True, "value": m.group(1), "quote": m.group(0)} if m else {"found": False, "value": "", "quote": ""}
        return out
    return chat


def _long_pages():
    return [{"text": t, "method": "text-layer"} for t in LONG.read_text().split("\f")]


def _filler(n, mark):
    return "\n".join(f"SYNTHETIC {mark} line {i}: afebrile, vitals stable, plan continued as per treating team." for i in range(n))


def _process_pages(unit_case, monkeypatch, pages, chat, doc_type="discharge_summary"):
    """process_document with the real extract_facts; ingest and classify faked, llm.chat replaced by `chat`."""
    doc = store.add_document_file(unit_case, "long_document.txt", b"synthetic")

    async def fake_pages(path, audit=None):
        return [dict(p) for p in pages]

    async def fake_classify(t, audit=None):
        return {**CLS, "title": "DISCHARGE SUMMARY", "doc_type": doc_type, "patient_name": "", "patient_id": ""}
    monkeypatch.setattr(ingest, "extract_pages", fake_pages)
    monkeypatch.setattr(extract, "classify", fake_classify)
    monkeypatch.setattr(extract.llm, "chat", chat)
    return asyncio.run(extract.process_document(unit_case, doc["doc_id"], "lung_nsclc", {"mrn": "SYN-480021", "name": "SYNTHETIC, Ramesh Kulkarni"}))


def test_long_fixture_shape():
    pages = _long_pages()
    full = extract._doc_text(pages)
    assert len(full) >= 25000 and len(pages) == 9 and "SYNTHETIC" in full
    assert "ECOG performance status: 1" in pages[-1]["text"] and "ECOG" not in full[:14000]  # beyond today's 14,000-character cut


def test_windows_follow_pages_with_one_page_overlap():
    full = extract._doc_text(_long_pages())
    wins = extract._windows(full)
    assert len(wins) > 1 and all(b - a <= extract.WINDOW for a, b, _ in wins)
    assert wins[0][0] == 0 and wins[-1][1] == len(full)
    for (a1, b1, _), (a2, b2, _) in zip(wins, wins[1:]):
        assert a2 < b1  # consecutive windows overlap ...
        assert full[a2:].startswith("[page ") and full[a2:b1] == full[a2:b1].strip()  # ... by whole pages
        assert full[a2:b1].count("[page ") == 1  # one page
    assert [w[2] for w in wins] == ["pages 1 to 4 of 9", "pages 4 to 7 of 9", "pages 7 to 9 of 9"]


def test_windows_split_an_oversized_page_at_line_boundaries():
    full = extract._doc_text([{"text": _filler(400, "huge")}, {"text": "Haemoglobin 11.8 g/dL"}])
    wins = extract._windows(full)
    assert all(b - a <= extract.WINDOW for a, b, _ in wins) and wins[-1][1] == len(full)
    for a, b, _ in wins[1:]:
        assert full[a - 1] == "\n" or full[a:].startswith("[page ")  # pieces start at a line start
    assert wins[0][2].startswith("page 1 (piece 1 of ")


def test_long_document_ecog_found_and_verified_on_its_page(unit_case, monkeypatch):
    sent = []
    pages = _long_pages()
    d = _process_pages(unit_case, monkeypatch, pages, _window_chat(sent))
    assert d["state"] == "ready", d.get("error")
    ecog = d["facts"]["ecog"]
    assert (ecog["value"], ecog["verification"], ecog["quote"]) == ("1", "verified", "ECOG performance status: 1")
    assert ecog["location"]["page"] == 8 and "alternatives" not in ecog  # page 9 of 9, global page index
    assert pages[8]["text"][ecog["location"]["start"]:ecog["location"]["end"]] == "ECOG performance status: 1"
    assert len(sent) == 3 and all(len(s["body"]) <= extract.WINDOW for s in sent)
    assert [s["purpose"] for s in sent] == [f"extract fields (window {i} of 3)" for i in (1, 2, 3)]
    assert "DOCUMENT, part 3 of 3 (pages 7 to 9 of 9); the other parts are read separately:\n" in sent[2]["prompt"]
    assert "not written in this part of the document" in sent[2]["prompt"]


def test_extraction_sees_text_after_14000_chars(monkeypatch):  # was the 3.4 strict xfail in test_known_issues.py
    sent = []

    async def fake_chat(role, msgs, **kw):
        sent.append(" ".join(m["content"] for m in msgs if isinstance(m["content"], str)))
        return {"haemoglobin": {"found": False, "value": "", "quote": ""}}
    monkeypatch.setattr(extract.llm, "chat", fake_chat)
    long_text = "SYNTHETIC discharge summary\n" + "Day-wise course: stable, afebrile.\n" * 500 + "Haemoglobin 11.8 g/dL\n"
    asyncio.run(extract.extract_facts(long_text, ["haemoglobin"]))
    assert any("Haemoglobin 11.8 g/dL" in s for s in sent)


def test_short_document_is_one_call_with_todays_prompt(monkeypatch):
    sent = []
    monkeypatch.setattr(extract.llm, "chat", _window_chat(sent))
    r = asyncio.run(extract.extract_facts(TEXT, ["haemoglobin", "ecog"]))
    assert len(sent) == 1 and sent[0]["purpose"] == "extract fields"
    cat = extract.protocol.facts()
    spec = "\n".join(f"- {f}: {cat[f]['label']} ({cat[f]['desc']})" for f in ["haemoglobin", "ecog"])
    assert sent[0]["prompt"] == TODAY_PROMPT.format(spec=spec, text=TEXT) and sent[0]["body"] == TEXT
    assert r == {"haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Haemoglobin 11.8 g/dL"},
                 "ecog": {"found": False, "value": "", "quote": ""}}


def test_two_windows_with_different_values_need_review(unit_case, monkeypatch):
    pages = [{"text": "SYNTHETIC lab sheet\nHaemoglobin 11.8 g/dL\n" + _filler(30, "a")}] + [{"text": _filler(30, f"p{i}")} for i in range(2, 7)] \
        + [{"text": _filler(20, "z") + "\nRepeat Haemoglobin 9.6 g/dL"}]
    sent = []
    d = _process_pages(unit_case, monkeypatch, pages, _window_chat(sent), doc_type="lab")
    assert len(sent) > 1
    hb = d["facts"]["haemoglobin"]
    assert (hb["value"], hb["verification"], hb["reason"]) == ("11.8 g/dL", "needs_review", "different values in different parts of the document")
    assert hb["location"]["page"] == 0
    assert [(a["value"], a["quote"], a["verification"], a["location"]["page"]) for a in hb["alternatives"]] == \
        [("9.6 g/dL", "Haemoglobin 9.6 g/dL", "verified", 6)]
    ev = [e for e in store.read_audit(unit_case) if e["kind"] == "fact_verification" and e["fact"] == "haemoglobin"]
    assert ev[-1]["result"] == "needs_review" and ev[-1]["alternatives"] == ["9.6 g/dL"]


def test_two_windows_with_the_same_value_stay_verified(unit_case, monkeypatch):
    pages = [{"text": "Haemoglobin 11.8 g/dL\n" + _filler(30, "a")}] + [{"text": _filler(30, f"p{i}")} for i in range(2, 7)] \
        + [{"text": _filler(20, "z") + "\nHaemoglobin 11.8 g/dL"}]
    sent = []
    d = _process_pages(unit_case, monkeypatch, pages, _window_chat(sent), doc_type="lab")
    assert len(sent) > 1
    hb = d["facts"]["haemoglobin"]
    assert hb["verification"] == "verified" and hb["reason"] is None and "alternatives" not in hb


def test_value_on_the_overlap_page_is_one_value(monkeypatch):
    pages = [{"text": _filler(30, f"p{i}")} for i in range(1, 4)] + [{"text": _filler(15, "p4") + "\nHaemoglobin 11.8 g/dL\n" + _filler(15, "p4b")}] \
        + [{"text": _filler(30, f"p{i}")} for i in range(5, 8)]
    full = extract._doc_text(pages)
    wins = extract._windows(full)
    assert sum("Haemoglobin 11.8 g/dL" in full[a:b] for a, b, _ in wins) == 2  # page 4 is in two windows
    sent = []
    monkeypatch.setattr(extract.llm, "chat", _window_chat(sent))
    r = asyncio.run(extract.extract_facts(full, ["haemoglobin"]))
    assert sum(s["body"].count("Haemoglobin 11.8 g/dL") for s in sent) == 2
    assert r == {"haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Haemoglobin 11.8 g/dL"}}


def test_windows_merge_keeps_first_value_and_different_alternatives(monkeypatch):
    answers = iter([{"haemoglobin": {"found": False, "value": "", "quote": ""}},
                    {"haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Hb 11.8 g/dL"}},
                    {"haemoglobin": {"found": True, "value": "11.8  G/DL", "quote": "Hb: 11.8 g/dL"}},  # the same value, written differently
                    {"haemoglobin": {"found": True, "value": "9.6 g/dL", "quote": "Hb 9.6 g/dL"}}])

    async def chat(role, msgs, **kw):
        return next(answers)
    monkeypatch.setattr(extract.llm, "chat", chat)
    full = extract._doc_text([{"text": _filler(110, f"p{i}")} for i in range(4)])
    assert len(extract._windows(full)) == 4
    r = asyncio.run(extract.extract_facts(full, ["haemoglobin"]))
    assert r == {"haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Hb 11.8 g/dL", "alternatives": [{"value": "9.6 g/dL", "quote": "Hb 9.6 g/dL"}]}}


def test_unverified_alternative_is_dropped(run):
    raw = {**RAW, "haemoglobin": {**RAW["haemoglobin"], "alternatives": [{"value": "12.9 g/dL", "quote": "Haemoglobin 12.9 g/dL"}]}}
    hb = run(raw=raw)["facts"]["haemoglobin"]
    assert (hb["value"], hb["verification"], hb["reason"]) == ("11.8 g/dL", "verified", None) and "alternatives" not in hb


def test_verified_alternative_replaces_an_unverified_first_value(run):
    raw = {**RAW, "haemoglobin": {"found": True, "value": "12.9 g/dL", "quote": "Haemoglobin 12.9 g/dL",
                                  "alternatives": [{"value": "11.8 g/dL", "quote": "Haemoglobin 11.8 g/dL"}]}}
    hb = run(raw=raw)["facts"]["haemoglobin"]
    assert (hb["value"], hb["verification"], hb["quote"]) == ("11.8 g/dL", "verified", "Haemoglobin 11.8 g/dL") and "alternatives" not in hb
