"""The board summary opens with who the patient is (Eswar, 5 Nov 2026): age and sex from the Case File's patient record (said where
they come from, no quote), unless the model's own verified presentation already gives the age; the model is asked for comorbidities
and earlier cancer treatment too, cited, only if documented. Synthetic only; no model is called."""
import asyncio

from tumour_board import llm, store, summary


def test_age_and_sex_are_read_from_either_form():
    assert summary.age_sex({"agesex": "48 Y / F"}) == (48, "F")
    assert summary.age_sex({"age": 48, "sex": "F"}) == (48, "F")       # a manual or private Case File
    assert summary.age_sex({"agesex": "62/M"}) == (62, "M")
    assert summary.age_sex({"agesex": "45 Y/Female"}) == (45, "F")
    assert summary.age_sex({}) == (None, None) and summary.age_sex({"age": "x"}) == (None, None) and summary.age_sex({"age": 400}) == (None, None)


def test_the_introduction_names_its_source_and_steps_aside_for_a_cited_one():
    assert summary.introduction({"patient": {"age": 48, "sex": "F"}}, [])["text"] == "Patient: 48-year-old woman (age and sex as entered in the Case File)."
    his = summary.introduction({"patient": {"agesex": "54 Y / F"}, "his": {"uhid": "VXH/26/000001"}}, [])
    assert his["text"].endswith("(age and sex as registered in the hospital system).") and his["citations"] == []
    assert summary.introduction({"patient": {"agesex": "7 Y / M"}}, [])["text"].startswith("Patient: 7-year-old boy")
    cited = [{"text": "A 48-year-old woman presented with a left breast lump.", "citations": [{"quote": "48 years"}]}]
    assert summary.introduction({"patient": {"age": 48, "sex": "F"}}, cited) is None
    assert summary.introduction({"patient": {}}, []) is None


def test_the_built_summary_starts_with_the_patient_and_asks_for_the_context(unit_case, monkeypatch):
    c = store.get_case(unit_case); c["patient"] = {**(c.get("patient") or {}), "agesex": "", "age": 48, "sex": "F"}; store.save_case(c)
    seen = {}

    async def fake_chat(role, msgs, **kw):
        seen["prompt"] = msgs[-1]["content"]
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(summary.llm, "chat", fake_chat)
    out = asyncio.run(summary.build(unit_case, force=True))
    first = out["sections"][0]
    assert first["id"] == "presentation" and first["sentences"][0]["text"].startswith("Patient: 48-year-old woman")
    assert "48 years, female" in seen["prompt"] and "comorbidities and any previous cancer treatment" in seen["prompt"]
