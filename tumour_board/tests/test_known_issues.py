"""Known issues, written the way the fixed behaviour should look. Each is a strict xfail: when the fix lands the test
passes, strict mode turns that into a failure, and the fix removes the marker.

Items 1.1 / 1.2 / 3.1 / 3.3 / 3.4 / 4.3 are planned in docs_Eswar/changes_v1.md (from the doc 01 pain points). Tests marked
"found in 0.3" were found while writing these tests."""
import asyncio

import pytest

from tumour_board import agents, docstatus, extract, ingest, qa, rules, search
from tumour_board.tests.util import TEXT, add, fact, make_doc


# ---- 1.1 negation: words starting with "non-" ---------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 1.1")
def test_non_small_cell_is_not_negated_in_extract():
    assert not extract.NEGATED_RE.search("Non-small cell carcinoma, adenocarcinoma type")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 1.1")
def test_non_small_cell_is_not_negated_in_qa():
    assert not qa.NEGATION.search("Non-small cell carcinoma, adenocarcinoma type")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 1.1")
def test_nsclc_answer_gets_no_negation_flag():
    assert not qa.polarity_flag("The histopathology records NSCLC.", ["Non-small cell carcinoma of lung"])


# ---- 1.2 agents see attestations ----------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 1.2")
def test_agent_document_list_shows_attestation(unit_case):
    add(unit_case, make_doc("Dhist0001", "histopathology", status="UNSTATED", signed="unknown", facts={"histologic_type": fact("Adenocarcinoma")}))
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    assert "attested final by Dr. Rao" in agents._doc_list(unit_case)


# ---- 3.1 dates ----------------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 3.1")
def test_report_date_is_not_taken_from_dob(run):
    text = TEXT.replace("Test Patient\n", "Test Patient\nDOB 12/03/1995\n")
    assert run(text=text, cls={"report_date": ""})["classification"]["report_date_iso"] == "2026-09-04"  # today: 1995-03-12


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 3.1")
def test_model_date_used_only_if_found_in_text(run):
    assert run(cls={"report_date": "01-Jan-2026"})["classification"]["report_date_iso"] == "2026-09-04"  # today: 2026-01-01


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, to be covered by V1 item 3.1: 'number word number' (Age 62 Years 02/...) swallows the date that follows")
def test_date_after_number_and_word_is_found():
    assert docstatus.find_dates("Age 62 Years 02/09/2026") == ["2026-09-02"]


# ---- 3.3 two-read OCR check ignores single digits -----------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 3.3")
def test_ocr_single_digit_slip_is_flagged(monkeypatch):
    async def fake(png, audit=None, max_side=None):
        return "PD-L1 TPS 8%\nECOG 2" if max_side else "PD-L1 TPS 6%\nECOG 1"
    monkeypatch.setattr(ingest, "ocr_image", fake)
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert {"6", "8"} <= set(p.get("ocr_uncertain_numbers", []))


# ---- 3.4 long documents are truncated before extraction -----------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 3.4")
def test_extraction_sees_text_after_14000_chars(monkeypatch):
    sent = []

    async def fake_chat(role, msgs, **kw):
        sent.append(" ".join(m["content"] for m in msgs if isinstance(m["content"], str)))
        return {"haemoglobin": {"found": False, "value": "", "quote": ""}}
    monkeypatch.setattr(extract.llm, "chat", fake_chat)
    long_text = "SYNTHETIC discharge summary\n" + "Day-wise course: stable, afebrile.\n" * 500 + "Haemoglobin 11.8 g/dL\n"
    asyncio.run(extract.extract_facts(long_text, ["haemoglobin"]))
    assert any("Haemoglobin 11.8 g/dL" in s for s in sent)


# ---- 4.3 failed documents block the gate --------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 4.3")
def test_failed_document_blocks_the_gate(unit_case):
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")}),
        make_doc("Dct000001", "ct", region="chest", facts={"lesion_size": fact("3.2 cm")}), make_doc("Dbad00001", "other", state="error"))
    assert not rules.evaluate(unit_case)["passed"]


# ---- found while writing 0.3 (listed in the plan under "Found during the run") -------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, fixed alongside V1 item 1.1: the key 'er' is matched as a substring of 'her2'")
def test_her2_query_does_not_pull_er_lines():
    assert r"\ber\b" not in search._patterns("HER2")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, fixed alongside V1 item 3.5: council prefix after 'Reg. No.' (KMC 45678) is not read as a signature")
def test_reg_no_with_council_prefix_is_signed():
    assert docstatus.detect_signature("Dr. S. Rao, MD (Pathology)\nReg. No. KMC 45678")[0] == "yes"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, fixed alongside V1 item 3.2: 'Final diagnosis pending' is read as FINAL")
def test_final_diagnosis_pending_is_not_final():
    assert docstatus.detect_status("FINAL DIAGNOSIS: pending IHC")[0] != "FINAL"
