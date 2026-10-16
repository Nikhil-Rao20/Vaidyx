"""units: Indian units and report conventions (V1 item 3.5). Used only to compare numbers; the value is always shown as written."""
import glob
import json

import pytest

from tumour_board import units
from tumour_board.tests.conftest import FIXTURES


@pytest.mark.parametrize("a,b", [
    ("2.45 lakhs/cumm", "245000/µL"),
    ("2.45 lakhs/cumm", "2,45,000/cumm"),
    ("2.45 lakhs/cumm", "2.45 x 10^5/µL"),
    ("2.45 lacs per cumm", "245 x10^3/uL"),
    ("2.45 lakh/cu.mm", "245 x10³/µL"),
    ("11.8 gm%", "11.8 g/dL"),
    ("11.8 gm%", "118 g/L"),
    ("11.8 g%", "11.8 gm/dl"),
    ("7,200/cumm", "7.2 x10^3/µL"),
    ("7,200/cmm", "7.2 x 10^9/L"),
    ("7200 cells/cumm", "7.2 K/µL"),
    ("4.5 million/cumm", "4.5 x10^6/µL"),
    ("60 mm", "6 cm"),


    ("2.45", "2.45"),  # unitless numbers compare as today
])
def test_same_quantity(a, b):
    assert units.same_quantity(a, b) and units.same_quantity(b, a)


@pytest.mark.parametrize("a,b", [
    ("2.45", "2.54"),
    ("2.45 lakhs/cumm", "2.54 lakhs/cumm"),
    ("2.45 lakhs/cumm", "254000/µL"),
    ("2.45 lakhs/cumm", "2,46,000/cumm"),  # exact conversions allow float noise only
    ("11.85 g/dL", "11.8 g/dL"),
    ("60 cm", "6 cm"),
    ("60", "6"),
    ("6", "6 cm"),  # a bare number is not a quantity
    ("1.1 mg/dL", "97 µmol/L"),  # analyte conversion needs the analyte label
    ("S. creatinine 1.1 mg/dL", "97 µmol/L"),  # a rounded conversion (1.1 x 88.4 = 97.2) is never equal by default (review: 1.22 mg/dL would pass against 106 µmol/L)
    ("Serum creatinine 97 umol/L", "1.1 mg/dL"),
    ("T. bilirubin 1.0 mg/dL", "17 µmol/L"),
    ("Blood sugar 5.5 mmol/L", "99 mg/dL"),
    ("S. creatinine 1.3 mg/dL", "97 µmol/L"),
    ("T. bilirubin 1.1 mg/dL", "97 µmol/L"),  # creatinine factor does not apply to bilirubin
    ("Hb 11.8 g/dL", "Platelets 11.8 g/dL"),  # different analytes
])
def test_not_same_quantity(a, b):
    assert not units.same_quantity(a, b)


def test_parse_quantity_keeps_the_value_and_unit_as_written():
    q = units.parse_quantity("TLC 7,200/cumm, Platelets 2.45 lakhs/cumm, Hb 11.8 gm%")
    assert [(x["value"], x["unit"], x["family"], x["label"]) for x in q] == [
        (7200.0, "/cumm", "count_per_volume", "wbc"), (2.45, "lakhs/cumm", "count_per_volume", "platelets"), (11.8, "gm%", "mass_per_volume", "haemoglobin")]
    assert q[1]["base"] == pytest.approx(245000) and q[2]["base"] == pytest.approx(11800)


def test_parse_quantity_dimensions_exponents_and_headers():
    assert [(x["value"], x["base"], x["family"]) for x in units.parse_quantity("mass 5.2 x 4.1 cm")] == [(5.2, 52.0, "length"), (4.1, 41.0, "length")]
    (q,) = units.parse_quantity("2.45 x 10^5/µL")
    assert (q["value"], q["unit"], q["base"]) == (2.45, "x 10^5/µL", pytest.approx(245000))
    # a column header 'x10^3/uL' with no number before it is not a quantity
    assert [(x["value"], x["family"]) for x in units.parse_quantity("WBC count Not reported x10^3/uL 4.0 - 11.0")] == [(4.0, None), (11.0, None)]
    assert units.parse_quantity("5 mg once daily")[0]["family"] is None  # a dose is not a lab unit
    assert units.parse_quantity("Rs 5 lakh")[0]["family"] is None  # a bare lakh is a rupee amount, not a count


@pytest.mark.parametrize("a,b,ok", [
    ("Platelets 2,45,000/µL", "Platelet count 2.45 lakhs/cumm", True),
    ("Platelets 245", "Platelet count 2.45 lakhs/cumm", True),  # labelled, no unit: 245 x10^3/µL is customary for platelets
    ("WBC 7.2", "TLC 7,200/cumm", True),
    ("Total leucocyte count 7.2 x10^3/µL", "WBC 7,200/cumm", True),
    ("Hb 118 g/L", "Haemoglobin 11.8 gm%", True),
    ("haemoglobin 11.8", "Hb 11.8 gm%", True),  # as today
    ("On 2026-09-04 Hb 11.8 g/dL", "Hb 11.8 gm%", False),  # the date numbers are not in the quote (the guard allows them from the document)
    ("WBC 72", "TLC 7,200/cumm", False),
    ("Hb 7.2", "TLC 7,200/cumm", False),  # a different analyte
    ("7.2", "TLC 7,200/cumm", False),  # neither unit nor label
    ("60", "6 cm", False),
    ("60 cm", "6 cm", False),
    ("60 mm", "6 cm", True),
    ("2.45", "2.54 lakhs/cumm", False),
    ("Hb 11.85 g/dL", "Hb 11.8 gm%", False),
])
def test_numbers_equivalent(a, b, ok):
    assert units.numbers_equivalent(a, b) is ok


def test_unmatched_numbers_lists_what_is_missing():
    assert units.unmatched_numbers("Platelets 2,45,000/µL on 04-09-2026", "Platelets 2.45 lakhs/cumm") == ["04", "09", "2026"]


def test_equivalent_numbers():
    eq = units.equivalent_numbers("Platelets 2.45 lakhs/cumm")
    assert {"2.45", "245000", "245"} <= eq
    assert "2.54" not in eq and "254" not in eq and "24.5" not in eq
    assert units.equivalent_numbers("TLC 7,200/cumm") >= {"7.2", "7200"}
    assert units.equivalent_numbers("Hb 11.8 gm%") >= {"11.8", "118"}
    assert "60" not in units.equivalent_numbers("6")
    assert units.equivalent_numbers("ECOG 1, Ki-67 25") == {"1", "67", "25"}  # bare numbers: as today


def _verified_facts():
    out = []
    for f in sorted(glob.glob(str(FIXTURES / "cases" / "*" / "docs" / "*" / "doc.json"))):
        for fid, fx in (json.loads(open(f).read()).get("facts") or {}).items():
            if isinstance(fx, dict) and fx.get("verification") == "verified" and fx.get("quote"):
                out.append((fid, fx["value"], fx["quote"]))
    return out


def test_no_false_drops_on_fixture_facts():
    """Every verified fact value is quoted from its document, so its numbers must be supported by its own quote."""
    facts = _verified_facts()
    assert len(facts) > 50
    bad = [(fid, v, q) for fid, v, q in facts if not units.numbers_equivalent(v, q)]
    assert bad == []


@pytest.mark.parametrize("value,quote", [("60", "6"), ("2.45", "2.54"), ("60 cm", "lower edge 6 cm from the anal verge"),
                                         ("12.9 g/dL", "Haemoglobin 11.8 g/dL 13.0 - 17.0"), ("254 x10^3/uL", "Platelet count 245 x10^3/uL 150 - 410")])
def test_a_different_number_never_passes(value, quote):
    assert not units.numbers_equivalent(value, quote)


@pytest.mark.parametrize("value,quote", [("60", "6"), ("2.45", "2.54"), ("2.45", "2.54 lakhs/cumm"), ("12.9", "Haemoglobin 11.8 g/dL")])
def test_equivalent_numbers_never_adds_a_different_number(value, quote):
    assert value not in units.equivalent_numbers(quote)


def test_equivalent_numbers_is_unit_blind_so_guards_use_numbers_equivalent():
    """'6 cm' is also 60 (mm): equivalent_numbers lists 60, numbers_equivalent still rejects '60 cm' because it keeps the unit."""
    assert "60" in units.equivalent_numbers("6 cm")
    assert not units.numbers_equivalent("60 cm", "6 cm") and units.numbers_equivalent("60 mm", "6 cm")


def test_rounded_analyte_conversion_only_on_request():
    """The creatinine / bilirubin / glucose factors are rounded: off by default (the guards), on only when a caller passes a tolerance."""
    assert not units.same_quantity("S. creatinine 1.1 mg/dL", "97 µmol/L")
    assert units.same_quantity("S. creatinine 1.1 mg/dL", "97 µmol/L", tol=0.02)
    assert not units.same_quantity("S. creatinine 1.22 mg/dL", "106 µmol/L")
    assert not units.numbers_equivalent("Creatinine 1.22 mg/dL", "S. creatinine 106 µmol/L")
