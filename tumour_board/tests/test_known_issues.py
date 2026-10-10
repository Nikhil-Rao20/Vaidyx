"""Known issues, written the way the fixed behaviour should look. Each is a strict xfail: when the fix lands the test
passes, strict mode turns that into a failure, and the fix removes the marker.

Items 3.1 / 3.3 / 3.4 / 4.3 are planned in docs_Eswar/changes_v1.md (from the doc 01 pain points). Tests marked
"found in 0.3" were found while writing these tests."""
import asyncio

import pytest

from tumour_board import agents, docstatus, extract, ingest, qa, rules, search
from tumour_board.tests.util import TEXT, add, fact, make_doc


# ---- 4.3 failed documents block the gate --------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="fixed in V1 item 4.3")
def test_failed_document_blocks_the_gate(unit_case):
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")}),
        make_doc("Dct000001", "ct", region="chest", facts={"lesion_size": fact("3.2 cm")}), make_doc("Dbad00001", "other", state="error"))
    assert not rules.evaluate(unit_case)["passed"]

