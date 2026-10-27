"""night-v3 item 3.1, decision record v2: the one table of outcomes, steps, fields, choices and limits (decision_record.py). The web
form's JSON equals spec(); clean() refuses over-limit text naming the field, checks choices and dates, cleans list rows and applies the
required-by-outcome rule in strict mode; reason_needed() for the fields whose correction needs a reason. No model, no data."""
import json

import pytest

from tumour_board import decision_record as dr


def test_the_web_form_json_equals_the_spec():
    """The frontend reads web/tb-nik/src/features/meetings/decision_fields.json; regenerate it with
    `python -m tumour_board.decision_record --write` after changing the table."""
    assert dr.SPEC_PATH.exists(), "run python -m tumour_board.decision_record --write"
    assert json.loads(dr.SPEC_PATH.read_text(encoding="utf-8")) == dr.spec()
    assert dr.SPEC_PATH.read_text(encoding="utf-8") == dr.spec_json()  # indent 2, sorted keys, trailing newline


def test_spec_shape_steps_and_fields():
    sp = dr.spec()
    assert sorted(sp) == ["choices", "fields", "limits", "outcomes", "steps", "yn"]
    assert [o["id"] for o in sp["outcomes"]] == ["decision", "deferred", "referred", "not_discussed", "noted"]
    assert sp["outcomes"][3] == {"id": "not_discussed", "label": "Not discussed", "hint": "Moves to the next meeting"}
    steps = [s["id"] for s in sp["steps"]]
    assert steps == ["outcome", "recommendation", "considered", "next", "responsibility", "pmjay"]
    keys = [f["key"] for f in sp["fields"]]
    assert len(keys) == len(set(keys)) == 39 and keys[0] == "outcome"
    assert [steps.index(f["step"]) for f in sp["fields"]] == sorted(steps.index(f["step"]) for f in sp["fields"])  # in step order
    for f in sp["fields"]:
        assert set(f) <= {"key", "label", "kind", "step", "limit", "choices", "required", "after", "reason", "hint", "source"}
        assert "—" not in f["label"] + f.get("hint", "")  # no em dashes
        if f.get("choices"):
            assert f["choices"] in sp["choices"]
    assert sp["limits"] == {"name": 120, "short": 300, "long": 2000, "decision": 4000, "rationale": 4000, "note": 2000}
    assert dr.BY_KEY["decision_text"]["limit"] == 4000 and dr.BY_KEY["key_worker"]["limit"] == 120 and dr.BY_KEY["concerns"]["limit"] == {"by": 120, "text": 2000}


def test_over_limit_text_is_refused_naming_the_field_never_cut():
    with pytest.raises(ValueError, match=r"Sequence: at most 300 characters \(301 written\)"):
        dr.clean({"outcome": "noted", "sequence": "x" * 301}, strict=False)
    with pytest.raises(ValueError, match="Key worker: at most 120 characters"):
        dr.clean({"outcome": "noted", "key_worker": "k" * 121}, strict=True)
    with pytest.raises(ValueError, match="Decision, in the board's words: at most 4000"):
        dr.clean({"outcome": "decision", "decision_text": "d" * 4001}, strict=False)
    with pytest.raises(ValueError, match="Further investigations, row 1: at most 300"):
        dr.clean({"investigations": [{"item": "i" * 301, "department": "Radiology"}]}, strict=False)
    ok = dr.clean({"outcome": "noted", "sequence": "s" * 300}, strict=False)
    assert ok["sequence"] == "s" * 300


def test_enums_and_labels():
    out = dr.clean({"outcome": "Decision recorded", "intent": "Palliative", "modalities": ["radiotherapy", "Supportive or palliative care", "radiotherapy"],
                    "trial_considered": "not stated", "consent_recorded": "pending", "stage_source": "confirmed_draft", "pmjay_plan_approval": "Not applicable"}, strict=False)
    assert out["outcome"] == "decision" and out["intent"] == "palliative" and out["modalities"] == ["radiotherapy", "supportive"]
    assert out["trial_considered"] == "not_stated" and out["consent_recorded"] == "pending" and out["pmjay_plan_approval"] == "not_applicable"
    assert out["intent_as_recorded"] == "palliative"  # the compatibility key for metrics, minutes and FHIR
    with pytest.raises(ValueError, match="Treatment intent: choose one of Curative, Palliative, Not stated by the board"):
        dr.clean({"intent": "aggressive"}, strict=False)
    with pytest.raises(ValueError, match="Modalities: wishful is not one of the choices"):
        dr.clean({"modalities": ["surgery", "wishful"]}, strict=False)
    with pytest.raises(ValueError, match="The outcome must be one of"):
        dr.clean({"outcome": "maybe"}, strict=False)
    assert dr.choice_label("intent", "not_stated") == "Not stated by the board" and dr.choice_label("modalities", ["surgery", "endocrine"]) == "Surgery, Endocrine therapy"
    assert dr.choice_label("outcome", "deferred") == "Deferred: information awaited" and dr.label("stage_as_agreed") == "Stage as agreed by the board"
    # the old free-text intent counts only when the words are a choice (research 02, rule 4); nothing is guessed
    assert dr.clean({"intent_as_stated": "Curative"}, strict=False)["intent"] == "curative"
    assert dr.clean({"intent_as_stated": "curative intent, if fit"}, strict=False)["intent"] == ""
    assert dr.clean({"intent_as_recorded": "palliative"}, strict=False)["intent"] == "palliative"


@pytest.mark.parametrize("body,message", [
    ({"outcome": "decision", "decision_text": "Plan", "intent": "curative", "responsible_doctor": "Dr A"}, "Write the board's decision (at least 5 characters)."),
    ({"outcome": "decision", "decision_text": "Surgery first.", "responsible_doctor": "Dr A"}, "Choose the treatment intent"),
    ({"outcome": "decision", "decision_text": "Surgery first.", "intent": "not_stated"}, "Name the responsible clinician."),
    ({"outcome": "deferred", "awaited_from": "Pathology"}, "Say what is awaited."),
    ({"outcome": "deferred", "awaited": "IHC report"}, "Say which department it is awaited from."),
    ({"outcome": "referred"}, "Say where the Case File is referred to."),
    ({"outcome": "not_discussed"}, "Say why the Case File was not discussed."),
    ({}, "Choose the outcome."),
])
def test_required_by_outcome_in_strict_mode(body, message):
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)").replace(".", r"\.")):
        dr.clean(body, strict=True)
    dr.clean(body, strict=False)  # the old routes are not strict


def test_each_outcome_passes_with_its_required_fields():
    ok = {"decision": {"decision_text": "Surgery first.", "intent": "not_stated", "responsible_doctor": "Dr A"},
          "deferred": {"awaited": "IHC report", "awaited_from": "Pathology"}, "referred": {"referred_to": "State cancer centre"},
          "not_discussed": {"not_discussed_reason": "time"}, "noted": {}}
    for oc, body in ok.items():
        out = dr.clean({"outcome": oc, **body}, strict=True)
        assert out["outcome"] == oc and dr.missing_required(out) == []
    assert dr.clean({"outcome": "deferred", "awaited": "IHC report", "awaited_from": "Pathology"}, strict=True)["deferred_reason"] == "IHC report (from Pathology)"
    assert dr.missing_required({"outcome_type": "decision", "decision_text": "ok"}) == ["decision_text", "intent", "responsible_doctor"]
    assert dr.missing_required({"outcome": "noted"}) == []


def test_dates_are_iso_and_a_bad_date_is_refused():
    out = dr.clean({"next_review": "19/11/2026", "inform_by_date": "2026-11-02", "patient_informed_date": ""}, strict=False)
    assert out["next_review"] == "2026-11-19" and out["inform_by_date"] == "2026-11-02" and out["patient_informed_date"] == ""
    with pytest.raises(ValueError, match=r"Next review: not a valid date \(next week\)"):
        dr.clean({"next_review": "next week"}, strict=False)
    assert dr.add_working_days("2026-10-31", 2) == "2026-11-03"  # a Saturday meeting: Monday, then Tuesday (Sunday skipped)
    assert dr.add_working_days("2026-10-30", 2) == "2026-11-02"  # Friday: Saturday is a working day, Sunday skipped, Monday
    assert dr.dmy("2026-11-03") == "03/11/2026"


def test_list_rows_are_cleaned():
    out = dr.clean({"concerns": [{"by": "  Dr  Dev ", "text": "Cardiac   fitness"}, {"by": "", "text": ""}, "Unnamed worry"],
                    "investigations": [{"item": "PET-CT", "department": "Nuclear Medicine", "due": "05/11/2026"}, {"item": "", "department": "", "due": ""}],
                    "referrals": [{"kind": "Palliative care", "department": "Palliative Medicine", "note": "pain"}, {"kind": "", "department": "Dental"}],
                    "members_present": ["Dr A", " Dr A ", "", "Dr B"]}, strict=False)
    assert out["concerns"] == [{"by": "Dr Dev", "text": "Cardiac fitness"}, {"by": "", "text": "Unnamed worry"}]
    assert out["divergent_opinions"] == "Dr Dev: Cardiac fitness; Unnamed worry"
    assert out["investigations"] == [{"item": "PET-CT", "department": "Nuclear Medicine", "due": "2026-11-05"}]
    assert out["referrals"] == [{"kind": "palliative", "department": "Palliative Medicine", "note": "pain"}, {"kind": "other", "department": "Dental", "note": ""}]
    assert out["members_present"] == ["Dr A", "Dr B"]
    # strict (the meeting form): each concern needs a name, each investigation its words, each referral its kind
    with pytest.raises(ValueError, match="row 1: name who raised it"):
        dr.clean({"outcome": "noted", "concerns": [{"text": "Unnamed worry"}]}, strict=True)
    with pytest.raises(ValueError, match="Further investigations, row 1: write the investigation"):
        dr.clean({"outcome": "noted", "investigations": [{"department": "Radiology"}]}, strict=True)
    with pytest.raises(ValueError, match="Referrals, row 1: choose the kind of referral"):
        dr.clean({"outcome": "noted", "referrals": [{"department": "Dental"}]}, strict=True)
    with pytest.raises(ValueError, match="the due date is not a valid date"):
        dr.clean({"investigations": [{"item": "MRI", "due": "soon"}]}, strict=False)
    assert dr.value_text("investigations", out["investigations"]) == "PET-CT (Nuclear Medicine, due 05/11/2026)"
    assert dr.value_text("referrals", out["referrals"]) == "Palliative care (Palliative Medicine, pain); Other (Dental)"


def test_yes_no_fields():
    out = dr.clean({"patient_preference": "Yes", "fitness_considered": "not_applicable", "genomic_considered": ""}, strict=False)
    assert (out["patient_preference"], out["fitness_considered"], out["genomic_considered"]) == ("yes", "not_applicable", "")
    with pytest.raises(ValueError, match="Patient preference considered: choose one of Yes, No, Not applicable, Not stated"):
        dr.clean({"patient_preference": "maybe"}, strict=False)
    assert [x["id"] for x in dr.spec()["yn"]] == ["yes", "no", "not_applicable", "not_stated"]


def test_absent_fields_are_empty_and_the_snapshot_has_every_key():
    out = dr.clean({}, strict=False)
    assert out["outcome"] == "decision" and out["sequence"] == "" and out["modalities"] == [] and out["investigations"] == []
    snap = dr.form_fields({"outcome_type": "deferred", "awaited": "IHC"})
    assert list(snap) == dr.KEYS and snap["outcome"] == "deferred" and snap["referrals"] == []


def test_reason_needed_for_the_decision_intent_concerns_and_stage_only():
    assert dr.reason_needed(["decision_text"]) and dr.reason_needed(["key_worker", "intent"]) and dr.reason_needed(["concerns"]) and dr.reason_needed(["stage_as_agreed"])
    assert not dr.reason_needed(["key_worker"]) and not dr.reason_needed(["patient_informed_date", "trial_considered", "investigations"]) and not dr.reason_needed([])


def test_display_lines_follow_the_step_order_and_carry_the_correction():
    rec = {"outcome_type": "decision", "decision_text": "Surgery first.", "intent": "curative", "next_review": "2026-12-01", "key_worker": "Sr Meena",
           "corrected": {"by": "priya", "by_name": "Dr Priya Nair", "at": "2026-10-28T09:00:00", "reason": "Intent misheard", "version": 2}}
    lines = dr.display_lines(rec, skip=("outcome",))
    assert [x["key"] for x in lines] == ["decision_text", "intent", "next_review", "key_worker", "corrected"]
    assert lines[2]["text"] == "01/12/2026" and lines[-1]["text"] == "Corrected by Dr Priya Nair on 28/10/2026: Intent misheard"
    old = {"outcome_type": "decision", "intent_as_recorded": "palliative", "divergent_opinions": "Dr X: wait for PET"}  # a record from before 3.1
    assert {x["key"]: x["text"] for x in dr.display_lines(old)} == {"outcome": "Decision recorded", "intent": "Palliative", "concerns": "Dr X: wait for PET"}


def test_the_write_command_writes_the_spec(tmp_path, monkeypatch):
    target = tmp_path / "decision_fields.json"
    monkeypatch.setattr(dr, "SPEC_PATH", target)
    assert dr.main(["--write"]) == 0
    assert target.read_text(encoding="utf-8") == dr.spec_json() and json.loads(target.read_text()) == dr.spec()
