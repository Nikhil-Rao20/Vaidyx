"""extract.process_document with the model calls replaced by fakes: status, signature, date fallbacks, identity,
grounding of extracted values, pending state, polarity and the two-read OCR downgrade. Also ingest.ocr_page and the
negation cues (the known non- bug is in test_known_issues.py)."""
import asyncio

import pytest

from tumour_board import extract, ingest, qa, store
from tumour_board.tests.util import TEXT


def test_status_signature_and_date(run):
    d = run()
    c = d["classification"]
    assert d["state"] == "ready" and d["processed"]
    assert (c["status"], c["status_quote"], c["signed"]) == ("FINAL", "Report status: FINAL", "yes")
    assert c["signature_quote"] == "Reported by: Dr. A. Menon, Consultant Pathologist"
    assert c["report_date_iso"] == "2026-09-04"


def test_date_falls_back_to_filename(run):
    assert run(cls={"report_date": ""}, filename="cbc_2026-09-03.txt")["classification"]["report_date_iso"] == "2026-09-03"


def test_date_falls_back_to_first_date_in_text(run):
    text = TEXT.replace("Reported on 04/09/2026", "Collected 02/09/2026\nReported on 04/09/2026")
    assert run(text=text, cls={"report_date": ""})["classification"]["report_date_iso"] == "2026-09-02"


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
    assert run(patient={"mrn": "SYN-111111", "name": "SYNTHETIC, Other Person"})["identity"] == "mismatch_or_missing"


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
    f = run(page_extra={"method": "vision-transcription", "ocr_uncertain_numbers": ["11.8"]})["facts"]
    assert f["haemoglobin"]["verification"] == "needs_review"
    assert f["haemoglobin"]["reason"] == "the two OCR reads of this page disagree on a number in this value"
    assert f["platelets"]["verification"] == "verified"


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


# ---- negation and pending cues (real negations; the non- false positive is a known issue) ------------------
@pytest.mark.parametrize("s", ["HIV non-reactive", "non-reactive", "EGFR mutation not detected", "Negative", "No evidence of metastasis",
                               "HER2 non-amplified", "absent"])
def test_negation_cues(s):
    assert extract.NEGATED_RE.search(s) and qa.NEGATION.search(s)


@pytest.mark.parametrize("s", ["Positive", "EGFR exon 19 deletion detected", "Adenocarcinoma, acinar predominant", "TPS 60%"])
def test_affirmed_values(s):
    assert not extract.NEGATED_RE.search(s) and not qa.NEGATION.search(s)


@pytest.mark.parametrize("s,pending", [("Pending", True), ("result awaited", True), ("Not reported", True), ("sent to reference laboratory", True),
                                       ("Will follow", True), ("60%", False), ("Negative", False)])
def test_pending_cue(s, pending):
    assert bool(extract.PENDING_RE.search(s)) == pending


def test_polarity_flag():
    assert qa.polarity_flag("Metastasis is present", ["No evidence of metastasis"])
    assert not qa.polarity_flag("No metastasis is documented", ["No evidence of metastasis"])
    assert not qa.polarity_flag("TPS 60%", [])
