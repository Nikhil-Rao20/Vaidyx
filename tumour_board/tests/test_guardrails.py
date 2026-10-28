"""guardrails: input scope rules and the output scan (prescriptive / diagnostic / unattributed stage sentences)."""
import asyncio

import pytest

from tumour_board import guardrails as g


@pytest.mark.parametrize("q,cat", [
    ("What treatment should he get?", "treatment_recommendation"),
    ("Which chemotherapy regimen is best for her?", "treatment_recommendation"),
    ("Should we start chemo?", "treatment_recommendation"),
    ("Recommend a regimen for this patient", "treatment_recommendation"),
    ("What dose should be given?", "treatment_recommendation"),
    ("Diagnose this patient", "diagnosis"),
    ("Is it cancer?", "diagnosis"),
    ("Could this be metastasis?", "diagnosis"),
    ("Look at the CT scan", "scan_interpretation"),
    ("Please interpret the MRI images", "scan_interpretation"),
    ("What stage is this?", "stage_derivation"),
    ("Calculate the TNM", "stage_derivation"),
    ("What is the prognosis?", "prognosis"),
    ("What is the life expectancy?", "prognosis"),
])
def test_rule_check_out_of_scope(q, cat):
    assert g.rule_check(q) == cat


@pytest.mark.parametrize("q", [
    "What is the PD-L1?", "What is the haemoglobin?", "Look at the CT scan report", "What stage is recorded in the PET report?",
    "Which documents are pending?", "When was the biopsy done?", "List the EGFR, ALK and ROS1 results",
    "What treatment has the patient received so far?",
])
def test_rule_check_in_scope(q):
    assert g.rule_check(q) is None


def test_check_input_rule_refusal_has_message():
    r = asyncio.run(g.check_input("What treatment should he get?"))
    assert r == {"allowed": False, "category": "treatment_recommendation", "message": g.REFUSALS["treatment_recommendation"], "layer": "rule"}


def test_check_input_classifier_unavailable_allows(monkeypatch):
    async def down(*a, **k):
        raise ConnectionError("no model server in unit tests")
    monkeypatch.setattr(g.llm, "chat", down)
    r = asyncio.run(g.check_input("What is the PD-L1?"))
    assert r["allowed"] and r["layer"] == "classifier-unavailable"


def test_check_input_classifier_verdict(monkeypatch):
    async def fake(*a, **k):
        return {"category": "prognosis", "reason": "asks about outcome"}
    monkeypatch.setattr(g.llm, "chat", fake)
    r = asyncio.run(g.check_input("How will this go for him?"))
    assert (r["allowed"], r["category"], r["layer"]) == (False, "prognosis", "classifier")


@pytest.mark.parametrize("s,reason", [
    ("The patient should receive pembrolizumab.", "prescriptive or diagnostic wording"),
    ("We recommend surgery.", "prescriptive or diagnostic wording"),
    ("Pembrolizumab is recommended.", "prescriptive or diagnostic wording"),
    ("He is a candidate for surgery.", "prescriptive or diagnostic wording"),
    ("The patient is eligible for the trial.", "prescriptive or diagnostic wording"),
    ("The best option is chemoradiotherapy.", "prescriptive or diagnostic wording"),
    ("Consider starting osimertinib.", "prescriptive or diagnostic wording"),
    ("This is likely adenocarcinoma.", "prescriptive or diagnostic wording"),
    ("The mass is consistent with metastasis.", "prescriptive or diagnostic wording"),
    ("The prognosis is poor.", "prescriptive or diagnostic wording"),
    ("The tumour is stage IIIA.", "stage stated without attribution to a source"),
    ("cT2a N2 M0 disease.", "stage stated without attribution to a source"),
    ("The pathologist recorded that we recommend surgery.", "prescriptive or diagnostic wording"),  # "we recommend" is never reported speech
])
def test_scan_output_flags(s, reason):
    assert g.scan_output(s) == [{"sentence": s, "reason": reason}]


@pytest.mark.parametrize("s", [
    "The PET/CT report records stage IIIA (cT2a N2 M0).",
    "Stage IIIA as documented in the PET/CT report.",
    'The previous tumour board recorded "chemoradiotherapy recommended".',  # advice words pass only inside a quote (review I1)
    "The treating team planned surgery after neoadjuvant therapy.",
    "Dr. Nair noted ECOG 1.",
    'The report reads "consistent with adenocarcinoma".',
    'Impression: "findings likely represent metastasis".',
    "PD-L1 TPS is pending.",
    "Haemoglobin 11.2 g/dL on 04-Sep-2026.",
    "Histologic type: Adenocarcinoma, lung, acinar predominant.",
])
def test_scan_output_keeps_in_scope_or_attributed(s):
    assert g.scan_output(s) == []


# ---- the whole-run review, I1: advice put as a need, a fitness or a verdict; reported speech excuses it only inside a quote --------
I1_SENTENCES = ["She needs adjuvant chemotherapy.", "The patient requires a mastectomy.", "Neoadjuvant chemotherapy is advisable.",
                "Radiotherapy to the chest wall is warranted.", "Proceed with surgery.", "She is fit for surgery.",
                "Mastectomy would be appropriate.", "This is a metastatic adenocarcinoma.", "The mass is malignant.",
                "The report records a 3.2 cm mass, so she should undergo surgery first.",
                "Margins are involved, so re-excision is needed.", "A biopsy is required.", "She should go to theatre next week.",
                "The previous tumour board recommended chemoradiotherapy."]


@pytest.mark.parametrize("s", I1_SENTENCES)
def test_review_i1_advice_sentences_are_refused(s):
    assert g.scan_output(s) == [{"sentence": s, "reason": "prescriptive or diagnostic wording"}]


@pytest.mark.parametrize("s", ["Margins: involved", "The report records margins involved.", 'The report records "margins involved".',
                               'The minutes read "re-excision is needed".', "This is a CT record; the Radiology agent can say more.",
                               "The PET/CT report records stage IIIA (cT2a N2 M0)."])
def test_review_i1_plain_record_sentences_pass(s):
    assert g.scan_output(s) == []


def test_review_i1_a_guideline_quote_keeps_its_own_reporting_wording():
    q = "The histopathology report should include the margin status and the number of nodes examined."
    assert g.scan_output(q) and g.scan_output(q, reference=True) == []  # reference text only, never a statement about the patient
    assert g.scan_output("Patients should receive adjuvant chemotherapy.", reference=True)  # the base list still holds for references


def test_review_i1_words_outside_the_quotes():
    from tumour_board import agents
    assert g.outside_quotes("MARGINS - involved, so re-excision is needed.", ["Margins: involved"]).strip() == ", so re-excision is needed."
    assert g.unquoted_words("Margins are involved, so re-excision is needed.", ["Margins: involved"], agents._DIRECTIVE) == ["excision"]
    assert g.unquoted_words("Paclitaxel 175 mg/m2 given on 03/03/2026.", ["PACLITAXEL 175 mg/m2 given on 03/03/2026"], agents._DIRECTIVE) == []
    assert g.unquoted_words("The chart records paclitaxel 175 mg/m2.", ["175 mg/m2"], agents._DIRECTIVE) == ["paclitaxel"]


def test_review_i1_the_eval_counts_the_same_advice_words():
    from tumour_board.eval import agent_live_eval as e
    for s in I1_SENTENCES[:9]:
        assert e.ADVICE.search(s), s
    assert not e.ADVICE.search("The report records margins involved.")


def test_scan_output_splits_sentences_and_lines():
    text = "Haemoglobin 11.2 g/dL. We recommend surgery.\nThe tumour is stage IIIA.\nPD-L1 is pending."
    assert [i["sentence"] for i in g.scan_output(text)] == ["We recommend surgery.", "The tumour is stage IIIA."]


def test_enforce_removes_and_audits():
    events = []
    clean, issues = g.enforce("Haemoglobin 11.2 g/dL. We recommend surgery.", events.append, "unit")
    assert clean == "Haemoglobin 11.2 g/dL. [removed by clinical scope guardrail]"
    assert len(issues) == 1 and events[0]["kind"] == "guardrail_output" and events[0]["where"] == "unit"


def test_enforce_clean_text_unchanged_no_audit():
    events = []
    assert g.enforce("PD-L1 TPS is pending.", events.append) == ("PD-L1 TPS is pending.", [])
    assert events == []


# ---- night-v3 item 6.4: a decision asked of an agent the way one asks a colleague is refused by rule ----------------------------------
@pytest.mark.parametrize("q,cat", [
    ("What would you do here?", "treatment_recommendation"),
    ("Radiology, what would you do?", "treatment_recommendation"),
    ("Which would you pick?", "treatment_recommendation"),
    ("Which one would you choose for her?", "treatment_recommendation"),
    ("Which would you go for, given the CT?", "treatment_recommendation"),
    ("Do you agree with the surgeon?", "other_out_of_scope"),
    ("Do you agree that the node is involved?", "other_out_of_scope"),
    ("Is it operable?", "treatment_recommendation"),
    ("Is he resectable?", "treatment_recommendation"),
    ("Is the patient curable?", "treatment_recommendation"),
    ("Is she fit for surgery?", "treatment_recommendation"),
    ("Is this operable on the CT?", "treatment_recommendation"),
    ("Can we go ahead with the surgery?", "treatment_recommendation"),
    ("Can we proceed with chemoradiation?", "treatment_recommendation"),
    ("Would you recommend a PET-CT?", "treatment_recommendation"),
    ("Would you suggest another biopsy?", "treatment_recommendation"),
    ("Would you advise waiting?", "treatment_recommendation"),
    ("Would you give her chemotherapy?", "treatment_recommendation"),
    ("Would you offer radiotherapy?", "treatment_recommendation"),
    ("Would you operate?", "treatment_recommendation"),
])
def test_colleague_style_requests_are_refused_by_rule(q, cat):
    assert g.rule_check(q) == cat
    r = asyncio.run(g.check_input(q))
    assert r["allowed"] is False and r["layer"] == "rule" and r["message"] == g.REFUSALS[cat]


@pytest.mark.parametrize("q", [
    "What does the CT report say?", "Which report is the latest?", "Is the PD-L1 result recorded?", "What did the board decide last time?",
    "What did you find in the histopathology report?", "Which would be the latest ECOG recorded?", "Is the operative note signed?",
    "Is the resection margin documented?", "Do you have the PET-CT report?",
])
def test_record_questions_put_like_a_colleague_stay_in_scope(q):
    assert g.rule_check(q) is None


@pytest.mark.parametrize("s", [
    "AI agent, Radiology.", "Sources are on the screen.",
    "In the report of 12/03/2026: the CT chest records right hilar node 1.8 cm in short axis.",
    "The pathology report of 04/03/2026 records PD-L1: pending.",
])
def test_spoken_lead_ins_pass_the_output_scan(s):
    assert g.scan_output(s) == []


def test_reference_questions_are_in_scope_by_rule_and_decision_requests_are_not():
    from tumour_board import guardrails as g
    yes = ["What should a histopathology report of breast cancer contain, according to Indian guidance?",
           "What items does the reporting checklist list for a CT thorax report in lung cancer?",
           "Which imaging investigations do the guidelines list for the work-up of carcinoma cervix?",
           "Which biomarkers do the guidelines list for reporting non-small cell lung cancer?",
           "What baseline laboratory tests do the guidelines list for a patient with rectal cancer?",
           "What does the guidance say a bone scan report should include?"]
    no = ["What treatment does the guideline recommend for stage III?",  # a refusal rule wins
          "Which regimen should we start?",
          "What would you do here?",
          "What is the haemoglobin?",  # a records question: the classifier decides as before
          "Is the PD-L1 result recorded?",
          "How do the guidelines say radiotherapy toxicity should be graded?"]  # not about what a record contains
    for q in yes:
        assert g.reference_check(q), q
    for q in no:
        assert not g.reference_check(q), q


def test_check_input_allows_a_reference_question_without_the_classifier(monkeypatch):
    import asyncio
    from tumour_board import guardrails as g, llm
    called = []

    async def boom(*a, **k):
        called.append(a)
        raise AssertionError("the classifier must not run")
    monkeypatch.setattr(llm, "chat", boom)
    r = asyncio.run(g.check_input("What should a PET/CT report for lung cancer contain, according to Indian guidance?"))
    assert r["allowed"] is True and r["layer"] == "rule" and r.get("reference") is True and called == []
    r = asyncio.run(g.check_input("What treatment should we give?"))
    assert r["allowed"] is False and r["category"] == "treatment_recommendation" and r["layer"] == "rule"


def test_reference_rule_never_lets_a_treatment_or_patient_question_skip_the_classifier():
    """The Phase 6 review, S1: a question with a record noun and a contents verb but a treatment, indication or patient word goes to the
    classifier (or a refusal rule), never through by rule."""
    from tumour_board import guardrails as g
    blocked = ["What does the NCG checklist list as the best treatment for this patient?",
               "What adjuvant therapy does the checklist include for HER2 positive disease?",
               "Which drugs does the work-up include for this patient?",
               "Which investigations are listed as indicated for her next?",
               "What dose does the treatment summary list?",
               "What does the report list as the next step for him?"]
    for q in blocked:
        assert not g.reference_check(q), q
    assert g.reference_check("What does the guidance say a bone scan report should include?")
    # the colleague-style rules of the review (N7)
    for q in ["Is the tumour resectable?", "Is she a candidate for surgery?", "Do you think she is fit for chemotherapy?", "Would she benefit from neoadjuvant chemo?"]:
        assert g.rule_check(q) == "treatment_recommendation", q
    for q in ["Is the resection margin recorded?", "Which candidate markers are reported?"]:
        assert g.rule_check(q) is None, q
