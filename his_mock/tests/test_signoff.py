"""The sign-off of a signed report (cursive name, printed name, qualification, designation, the stamp with the block verbatim) and
the Low / High flag of lab results (18 Oct 2026)."""
from his_mock import documents


def test_flag_low_high_and_text():
    assert documents._flag("11.6", "12.0-15.0") == "Low"
    assert documents._flag("16.1", "12.0-15.0") == "High"
    assert documents._flag("7,200", "4,000-11,000") == ""
    assert documents._flag("Non-reactive", "Non-reactive") == ""
    assert documents._flag("2.6", "Not applicable") == ""


def test_signature_font_is_shipped_with_its_licence():
    assert documents.SIGNATURE_FONT.exists()
    assert (documents.SIGNATURE_FONT.parent / "OFL-GreatVibes.txt").exists()
