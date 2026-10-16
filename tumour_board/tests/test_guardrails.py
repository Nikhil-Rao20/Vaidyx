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
    "The previous tumour board recommended chemoradiotherapy.",
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
