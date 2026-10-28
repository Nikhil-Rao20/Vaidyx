"""Phase 9 review E, S1 (item 9.R): record wording must still pass the output guardrail. The advice check of guardrails.scan_output looks
only at what a statement says in its own words (outside its cited quotes), and a need word ("required", "needs") counts only next to a
treatment word, so a document title, a past treatment, a dose as recorded or a negative pathology line is never taken for advice.

The must-still-pass set: the 19 statements of the saved live evaluation (agent_live_eval over the synthetic demo Case Files TB-001 to
TB-008, run of 27/10/2026 under /data/vaidyx/night-v3/runs/evals/agent_live_full2) that the 9.2 rule dropped, the 3 points for review of
the synthetic demo Case Files TB-005, TB-2026-0001 and TB-DEMO-P18A it dropped, the HIST-13 Case summary sentence, and the examples of the
9.R decision. Copied here with their quotes; synthetic data only, never the real case."""
import asyncio

import pytest

from tumour_board import agents, guardrails as g, llm, qa
from tumour_board.tests.util import add, make_doc

# (eval question id, Case File, statement, cited quotes): agent_live_full2, every statement the 9.2 rule dropped
LIVE_EVAL = [
    ("med-008", "TB-003", "The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions.", ["50.4 Gy in 28 fractions to the pelvis (IMRT)"]),
    ("med-009", "TB-003", "The radiotherapy completion summary records Grade 1 proctitis and grade 1 skin reaction.", ["Grade 1 proctitis, grade 1 skin reaction."]),
    ("med-014", "TB-005", "The surgical oncology OPD note of 03/09/2026 records thyroxine 50 mcg once daily for hypothyroidism.", ["Hypothyroidism on thyroxine 50 mcg once daily."]),
    ("med-019", "TB-003", "Radiotherapy ended on 10-Aug-2026.", ["Treatment dates 30-Jun-2026 to 10-Aug-2026"]),
    ("sur-010", "TB-005", "On examination in the surgical oncology OPD note of 03/09/2026, the left breast lump is 3.5 x 3 cm.", ["Left breast: 3.5 x 3 cm hard lump, upper outer quadrant, not fixed to chest wall."]),
    ("sur-013", "TB-002", "The clinical stage recorded by the treating surgeon is cT2 N1 M0, Stage IIB (AJCC 8th edition, anatomic).", ["cT2 N1 M0, Stage IIB (AJCC 8th edition, anatomic)"]),
    ("sur-018", "TB-005", "In the surgical oncology OPD note of 03/09/2026, the left axilla has one mobile node, about 1.5 cm.", ["Left axilla: one mobile node, about 1.5 cm."]),
    ("rt-001", "TB-003", "The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions.", ["50.4 Gy in 28 fractions to the pelvis (IMRT)"]),
    ("rt-003", "TB-003", "The radiotherapy treatment dates are 30-Jun-2026 to 10-Aug-2026.", ["Treatment dates 30-Jun-2026 to 10-Aug-2026"]),
    ("rt-004", "TB-003", "The technique used for the pelvic radiotherapy was IMRT.", ["50.4 Gy in 28 fractions to the pelvis (IMRT)"]),
    ("rt-005", "TB-003", "The radiotherapy completion summary documents Grade 1 proctitis and grade 1 skin reaction as acute toxicity.", ["Acute toxicity\nGrade 1 proctitis, grade 1 skin reaction."]),
    ("rt-013", "TB-007", "The clinical stage recorded by the treating surgeon is cT4a N1 M0 (AJCC 8th edition), Stage IVA.", ["Clinical stage as recorded by the treating surgeon\ncT4a N1 M0 (AJCC 8th edition), Stage IVA"]),
    ("rt-017", "TB-003", "The concurrent drug was capecitabine 825 mg/m2 twice daily on radiotherapy days.", ["with concurrent capecitabine 825 mg/m2 twice\ndaily on radiotherapy days."]),
    ("rt-019", "TB-003", 'The Tumour Board of 12-Jun-2026 recorded a decision for "Long-course chemoradiation."', ["Decision recorded by the board\nLong-course chemoradiation."]),
    ("rt-019", "TB-003", 'A radiotherapy completion summary records the delivery of "50.4 Gy in 28 fractions to the pelvis (IMRT) with concurrent capecitabine 825 mg/m2 twice\ndaily on radiotherapy days."', ["50.4 Gy in 28 fractions to the pelvis (IMRT) with concurrent capecitabine 825 mg/m2 twice\ndaily on radiotherapy days."]),
    ("rt-020", "TB-003", "The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions.", ["50.4 Gy in 28 fractions to the pelvis (IMRT)"]),
    ("rt-020", "TB-003", "The follow-up note of 18-Sep-2026 records a dose of 50.4 Gy in 28 fractions.", ["Completed long-course chemoradiation (50.4 Gy in 28 fractions with capecitabine) on 10-Aug-2026."]),
    ("rt-021", "TB-003", "The radiotherapy completion summary records Grade 1 proctitis and grade 1 skin reaction.", ["Grade 1 proctitis, grade 1 skin reaction."]),
    ("rt-022", "TB-003", "The radiotherapy ended on 10-Aug-2026.", ["Treatment dates 30-Jun-2026 to 10-Aug-2026"]),
]

# (Case File, agent, point for review, cited quotes): the saved briefs of the demo Case Files, every point the 9.2 rule dropped
POINTS = [
    ("TB-005", "medical_oncology", "Confirmation required if the CECT Thorax and Abdomen report is the final signed version as the status is unstated.",
     ["CECT THORAX AND ABDOMEN (STAGING)"]),
    ("TB-2026-0001", "surgical_oncology", "The CECT Chest, Abdomen and Pelvis report is listed as cancelled and the preliminary report is unsigned; a final "
     "signed report is required for staging.", ["Report status: CANCELLED", "Report status: PRELIMINARY"]),
    ("TB-DEMO-P18A", "radiology", "The MRI Pelvis report lacks several specific data elements required for rectal cancer staging, including distance of "
     "lowest tumour margin from anal verge, longitudinal tumour size, and relation to the anterior peritoneal reflection.",
     ["Findings\nMesorectal fascia (MRF): Not involved\nExtramural venous invasion (EMVI): Negative"]),
]

# the HIST-13 Case summary sentence (presentation section) and the examples of the 9.R decision
OTHERS = [
    ("HIST-13 case summary", "Cytology of mediastinal lymph node aspirates from 14/09/2026 showed metastatic adenocarcinoma in station 7 and no malignant "
     "cells in station 4R.", ["Lymph nodes: Station 7: metastatic adenocarcinoma; station 4R: no malignant cells"]),
    ("document title", "The surgical oncology OPD note of 03/09/2026 records thyroxine 50 mcg once daily",
     ["The surgical oncology OPD note of 03/09/2026 records thyroxine 50 mcg once daily"]),
    ("past treatment", "Radiotherapy ended on 10/08/2026.", ["RT completed 10-Aug-2026"]),
    ("negative pathology", "The pathology report records no malignant cells in station 4R.", ["No malignant cells seen in station 4R"]),
    ("dose", "The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions.",
     ["The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions."]),
]

MUST_PASS = ([pytest.param(t, q, id=f"eval-{i}-{n}") for n, (i, _, t, q) in enumerate(LIVE_EVAL)]
             + [pytest.param(t, q, id=f"point-{c}") for c, _, t, q in POINTS]
             + [pytest.param(t, q, id=k) for k, t, q in OTHERS])


def test_the_must_pass_set_is_complete():
    assert (len(LIVE_EVAL), len(POINTS), len(MUST_PASS)) == (19, 3, 27)
    assert not any("TB-2026-bharath" in c for _, c, _, _ in LIVE_EVAL) and not any("bharath" in c for c, _, _, _ in POINTS)


@pytest.mark.parametrize("text,quotes", MUST_PASS)
def test_record_wording_passes_the_output_guardrail(text, quotes):
    assert g.scan_output(text, quotes=quotes) == []
    assert agents.directive_outside_quotes({"text": text, "citations": [{"doc_id": "D1", "quote": q} for q in quotes]}) == []


@pytest.mark.parametrize("text", [t for _, _, t, _ in POINTS] + ["Confirmation required if the CECT Thorax and Abdomen report is the final signed version."])
def test_points_for_review_pass_without_their_citations(text):
    """A point for review is checked as a whole sentence when it has no citation (quotes=None), and is not a treatment or work-up
    decision for this patient (agents._POINT_SCOPE)."""
    assert g.scan_output(text) == [] and not agents._POINT_SCOPE.search(text)


def test_a_quoted_guideline_reference_keeps_its_reporting_wording():
    assert g.scan_output("The report should include the margin status.", reference=True) == []
    assert agents._in_scope("The report should include the margin status.")


ADVICE = [
    ("Margins are involved, so re-excision is needed.", ["Margins: involved"]),
    ("She requires adjuvant chemotherapy.", []),
    ("Surgery is warranted.", []),
    ("The patient is fit for surgery.", []),
    ("Proceed with mastectomy.", []),
    ("Consider re-biopsy.", []),
    ("Adjuvant radiotherapy should be offered.", []),
    ("This is a triple-negative carcinoma.", []),
    ("The report records a mass, so she should undergo surgery.", ["Right upper lobe mass measuring 3.2 cm"]),
    ("The radiotherapy completion summary records 50.4 Gy in 28 fractions, so a boost should be considered.",
     ["50.4 Gy in 28 fractions to the pelvis (IMRT)"]),
]


@pytest.mark.parametrize("text,quotes", ADVICE)
def test_the_advice_examples_are_still_refused(text, quotes):
    assert [x["sentence"] for x in g.scan_output(text, quotes=quotes or None)] == [text]


# ---- the Ask path end to end: qa.ask keeps record wording and drops advice, each statement checked with its own quotes ----------------
RT = ("SYNTHETIC\nRADIOTHERAPY COMPLETION SUMMARY\n50.4 Gy in 28 fractions to the pelvis (IMRT)\nRT completed 10-Aug-2026\n"
      "Margins: involved\nReport status: FINAL")


def test_ask_keeps_record_wording_and_drops_advice(unit_case, monkeypatch):
    add(unit_case, make_doc("Drt000001", "rt_summary", date="2026-08-12", text=RT))
    keep = [{"text": "The radiotherapy completion summary records a dose of 50.4 Gy in 28 fractions.",
             "citations": [{"doc_id": "Drt000001", "quote": "50.4 Gy in 28 fractions to the pelvis (IMRT)"}]},
            {"text": "Radiotherapy was completed: RT completed 10-Aug-2026.",
             "citations": [{"doc_id": "Drt000001", "quote": "RT completed 10-Aug-2026"}]}]
    advice = {"text": "Margins are involved, so re-excision is needed.", "citations": [{"doc_id": "Drt000001", "quote": "Margins: involved"}]}

    async def fake_chat(role, msgs, purpose="", **kw):
        if purpose == "scope check":
            return {"category": "in_scope", "reason": ""}
        return {"answer_found": True, "statements": keep + [advice]}
    monkeypatch.setattr(llm, "chat", fake_chat)
    res = asyncio.run(qa.ask(unit_case, "What does the radiotherapy summary record?"))
    assert [s["text"] for s in res["statements"]] == [s["text"] for s in keep]
    assert [(x["text"], x["reason"]) for x in res["removed"]] == [(advice["text"], "guardrail")]
    assert res["removed"][0]["detail"] == "advice wording outside the quoted record text: needed"
    assert [i["sentence"] for i in res["guardrail_issues"]] == [advice["text"]]
