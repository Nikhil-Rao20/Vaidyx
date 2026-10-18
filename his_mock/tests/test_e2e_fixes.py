"""Fixes found by the live end-to-end scenario (tumour_board/eval/e2e_nik.py, 18 Oct 2026). SYNTHETIC data only."""
from his_mock import documents


def test_opd_note_without_a_clinical_question_has_a_plan_heading_only():
    """A plan alone printed under "Clinical question / Plan" was read as the question for the board."""
    html = documents._clinical_sections({"presenting_complaint": "Lump in the right breast for 3 months", "examination": "ECOG 1.",
                                         "plan": "Mammogram and core biopsy."})
    assert "Clinical question" not in html and ">Plan<" in html and "Mammogram and core biopsy." in html


def test_opd_note_with_a_clinical_question_keeps_the_combined_heading():
    html = documents._clinical_sections({"presenting_complaint": "Lump", "clinical_question": "Primary management plan", "plan": "Board."})
    assert "Clinical question / Plan" in html and "Primary management plan" in html
