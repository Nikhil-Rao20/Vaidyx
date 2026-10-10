"""grounding: normalisation, quote location (exact and fuzzy) and value verification."""
import pytest

from tumour_board import grounding as g

PAGE = ("SYNTHETIC\nHAEMATOLOGY REPORT (CBC)\nHaemoglobin   11.8 g/dL   13.0 - 17.0\nPlatelets 2.4 lakhs/cumm\n"
        "PD-L1 (22C3) TPS: 60%\nDiagnosis: Adenocarcinoma, lung, acinar predominant.\nReport status: FINAL")


def test_norm_lowercases_and_collapses_whitespace():
    assert g.norm("  Haemoglobin \t 11.8\n g/dL  ") == "haemoglobin 11.8 g/dl"


def test_norm_unifies_punctuation():
    assert g.norm("13.0 – 17.0") == "13.0 - 17.0"
    assert g.norm("“Positive”") == '"positive"'
    assert g.norm("Patient’s") == "patient's"
    assert g.norm("5 µmol/L") == "5 umol/l"
    assert g.norm("a b") == "a b"


def test_norm_drops_markdown_and_table_bars():
    assert g.norm("**ER** | 90% | _positive_") == "er 90% positive"
    assert g.norm(None) == ""


def test_norm_with_map_points_back_into_source():
    s = "A  **B**\nc"
    n, idx = g.norm_with_map(s)
    assert n == "a b c" and len(idx) == len(n)
    assert [s[i] for i, ch in zip(idx, n) if ch != " "] == ["A", "B", "c"]


def test_numbers():
    assert g.numbers("Hb 11.8 g/dL, range 13.0 - 17.0, 2 lakhs") == ["11.8", "13.0", "17.0", "2"]
    assert g.numbers(None) == []


def test_locate_exact_returns_source_offsets():
    loc = g.locate("haemoglobin 11.8 g/dl", [PAGE])
    assert loc["page"] == 0 and loc["score"] == 100.0
    assert loc["matched"] == "Haemoglobin   11.8 g/dL"
    assert PAGE[loc["start"]:loc["end"]] == loc["matched"]


def test_locate_finds_the_right_page():
    loc = g.locate("Report status: FINAL", ["SYNTHETIC page one", PAGE])
    assert loc["page"] == 1 and loc["matched"] == "Report status: FINAL"


def test_locate_too_short_or_absent():
    assert g.locate("a", [PAGE]) is None
    assert g.locate("", [PAGE]) is None
    assert g.locate("EGFR exon 19 deletion detected", [PAGE]) is None


def test_locate_fuzzy_match_scores_below_100():
    loc = g.locate("Diagnosis: Adenocarcinoma, lung, acinar predominent.", [PAGE])  # one letter different
    assert loc is not None and 92 <= loc["score"] < 100


def test_locate_fuzzy_never_changes_a_number():
    assert g.locate("PD-L1 (22C3) TPS: 80%", [PAGE]) is None


def test_locate_short_quotes_are_exact_only():
    assert g.locate("TPS: 6O%", [PAGE]) is None  # under 12 characters: no fuzzy alignment


def test_value_supported():
    m = "PD-L1 (22C3) TPS: 60%"
    assert g.value_supported("60%", m)
    assert g.value_supported("TPS 60%", m)
    assert not g.value_supported("80%", m)
    assert not g.value_supported(None, m)
    assert not g.value_supported("", m)
    assert g.value_supported(60, m)


def test_verify_exact_is_verified():
    v = g.verify("11.8 g/dL", "Haemoglobin   11.8 g/dL", [PAGE])
    assert v["status"] == "verified" and v["location"]["score"] == 100.0


def test_verify_quote_not_found_is_unverified():
    v = g.verify("19", "EGFR exon 19 deletion detected", [PAGE])
    assert v == {"status": "unverified", "reason": "quote not found in document", "location": None}


def test_verify_value_number_not_in_quote_is_unverified():
    v = g.verify("12.8 g/dL", "Haemoglobin   11.8 g/dL", [PAGE])
    assert v["status"] == "unverified" and v["reason"] == "value not supported by quoted text" and v["location"]


def test_verify_fuzzy_match_with_same_numbers_needs_review():
    v = g.verify("Adenocarcinoma", "Diagnosis: Adenocarcinoma, lung, acinar predominent.", [PAGE])
    assert v["status"] == "needs_review" and v["reason"].startswith("quote matched approximately (")


def test_verify_value_none_checks_quote_only():
    assert g.verify(None, "Report status: FINAL", [PAGE])["status"] == "verified"


@pytest.mark.parametrize("quote", ["report status: final", "REPORT   STATUS:\nFINAL", "**Report status:** FINAL"])
def test_verify_tolerates_case_and_whitespace(quote):
    assert g.verify(None, quote, [PAGE])["status"] == "verified"
