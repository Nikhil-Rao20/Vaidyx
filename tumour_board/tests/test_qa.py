"""qa.verify_statements: every statement needs a quote found in the cited document, and every number in it must be in that quote."""
from tumour_board import confirm, qa
from tumour_board.tests.util import add, make_doc


def _one(text, doc_id, quote):
    return {"text": text, "citations": [{"doc_id": doc_id, "quote": quote}]}


def test_verified_statement_kept_with_location(demo_cases):
    out = qa.verify_statements("TB-001", [_one("Haemoglobin is 11.8 g/dL.", "Dedaf7100", "Haemoglobin 11.8 g/dL")])
    assert len(out) == 1
    c = out[0]["citations"][0]
    assert (c["doc_id"], c["quote"], c["page"], c["date"], c["status"]) == ("Dedaf7100", "Haemoglobin 11.8 g/dL", 0, "2026-09-04", "FINAL")


def test_number_not_in_quote_is_dropped(demo_cases):
    assert qa.verify_statements("TB-001", [_one("Haemoglobin is 12.8 g/dL.", "Dedaf7100", "Haemoglobin 11.8 g/dL")]) == []


def test_quote_not_in_document_or_unknown_doc_is_dropped(demo_cases):
    assert qa.verify_statements("TB-001", [_one("EGFR exon 19 deletion.", "Dedaf7100", "EGFR exon 19 deletion detected")]) == []
    assert qa.verify_statements("TB-001", [_one("Haemoglobin is 11.8 g/dL.", "Dnope", "Haemoglobin 11.8 g/dL")]) == []


def test_elided_quote_verified_segment_by_segment(demo_cases):
    out = qa.verify_statements("TB-001", [_one("PD-L1 is pending; the report is a draft.", "D67977cf8",
                                                "PD-L1 (22C3) TPS Pending ... Report status: DRAFT")])
    assert len(out) == 1 and out[0]["citations"][0]["quote"] == "PD-L1 (22C3) TPS Pending ... Report status: DRAFT"


def test_date_number_allowed_from_cited_document_date(demo_cases):
    out = qa.verify_statements("TB-001", [_one("On 2026-09-04 haemoglobin was 11.8 g/dL.", "Dedaf7100", "Haemoglobin 11.8 g/dL")])
    assert len(out) == 1


def test_number_guard_accepts_the_same_quantity_in_indian_units(unit_case):
    """V1 item 3.5: a statement may restate a quoted value in other units; the quote is what is shown, the statement keeps its wording."""
    add(unit_case, make_doc("Dcbc00000", "lab", text="SYNTHETIC\nHAEMATOLOGY REPORT\nHb 11.8 gm%\nTLC 7,200/cumm\nPlatelets 2.45 lakhs/cumm\nReport status: FINAL"))
    for text, quote in [("Platelets are 2,45,000/µL.", "Platelets 2.45 lakhs/cumm"), ("Platelets are 245 x10^3/µL.", "Platelets 2.45 lakhs/cumm"),
                        ("WBC is 7.2.", "TLC 7,200/cumm"), ("WBC is 7.2 x10^3/µL.", "TLC 7,200/cumm"), ("Haemoglobin is 11.8 g/dL.", "Hb 11.8 gm%")]:
        out = qa.verify_statements(unit_case, [_one(text, "Dcbc00000", quote)])
        assert len(out) == 1 and out[0]["text"] == text and out[0]["citations"][0]["quote"] == quote, text


def test_number_guard_still_drops_a_different_number_in_other_units(unit_case):
    add(unit_case, make_doc("Dcbc00000", "lab", text="SYNTHETIC\nHAEMATOLOGY REPORT\nHb 11.8 gm%\nTLC 7,200/cumm\nPlatelets 2.45 lakhs/cumm\nReport status: FINAL"))
    for text, quote in [("Platelets are 2,54,000/µL.", "Platelets 2.45 lakhs/cumm"), ("Platelets are 2.54 lakhs/cumm.", "Platelets 2.45 lakhs/cumm"),
                        ("WBC is 72.", "TLC 7,200/cumm"), ("Haemoglobin is 7.2.", "TLC 7,200/cumm"), ("Haemoglobin is 118 g/dL.", "Hb 11.8 gm%"),
                        ("Haemoglobin is 11.85 g/dL.", "Hb 11.8 gm%")]:
        assert qa.verify_statements(unit_case, [_one(text, "Dcbc00000", quote)]) == [], text


def test_polarity_flag_on_statement(demo_cases):
    out = qa.verify_statements("TB-001", [_one("p40 result is recorded.", "D67977cf8", "p40 Negative")])
    assert out[0]["flags"] == ["check negation against the source"]


def test_citations_carry_the_confirmed_date_and_type(unit_case):
    """Review of 2.2 (M7): the citation shows the clinician-confirmed report date, and a number from that date is allowed."""
    add(unit_case, make_doc("Dlab00000", "lab", date="2026-09-01", text="SYNTHETIC\nHAEMATOLOGY REPORT\nHaemoglobin 11.8 g/dL\nReport status: FINAL"))
    confirm.record(unit_case, "confirm_dates", "Dlab00000", {"report_date": "2026-09-14"}, by="Dr. Rao")
    out = qa.verify_statements(unit_case, [_one("On 2026-09-14 haemoglobin was 11.8 g/dL.", "Dlab00000", "Haemoglobin 11.8 g/dL")])
    assert len(out) == 1 and out[0]["citations"][0]["date"] == "2026-09-14"
