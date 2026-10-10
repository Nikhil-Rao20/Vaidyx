"""Known issues, written the way the fixed behaviour should look. Each is a strict xfail: when the fix lands the test
passes, strict mode turns that into a failure, and the fix removes the marker.

Items 3.1 / 3.3 / 3.4 / 4.3 are planned in docs_Eswar/changes_v1.md (from the doc 01 pain points). Tests marked
"found in 0.3" were found while writing these tests."""
import asyncio

import pytest

from tumour_board import agents, docstatus, extract, ingest, qa, rules, search
from tumour_board.tests.util import TEXT, add, fact, make_doc


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


# ---- 4.3 failed documents block the gate --------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 4.3")
def test_failed_document_blocks_the_gate(unit_case):
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")}),
        make_doc("Dct000001", "ct", region="chest", facts={"lesion_size": fact("3.2 cm")}), make_doc("Dbad00001", "other", state="error"))
    assert not rules.evaluate(unit_case)["passed"]


# ---- found while writing 0.3 (listed in the plan under "Found during the run") -------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, fixed alongside V1 item 3.5: council prefix after 'Reg. No.' (KMC 45678) is not read as a signature")
def test_reg_no_with_council_prefix_is_signed():
    assert docstatus.detect_signature("Dr. S. Rao, MD (Pathology)\nReg. No. KMC 45678")[0] == "yes"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="found in 0.3, fixed alongside V1 item 3.2: 'Final diagnosis pending' is read as FINAL")
def test_final_diagnosis_pending_is_not_final():
    assert docstatus.detect_status("FINAL DIAGNOSIS: pending IHC")[0] != "FINAL"
