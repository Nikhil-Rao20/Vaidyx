"""night-v3 item 3.3: the Case summary. Built after each recorded decision (in the background) and on demand, in five sections; every
sentence cites a record line (checked word for word), a board-record field, an action, the stage confirmation or a member's card (the
exact stored text), or is code. Versions are kept; the owner's consultant reviews and edits. A synthetic Case File on the unit protocol;
the reasoner is a fake (no model call); never the real case."""
import asyncio
import copy
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import case_summary as cs
from tumour_board import config, followup, llm, notify, postboard, rules, staging, store
from tumour_board.tests.test_nik_slots import OWNER, FakeAuth, people  # noqa: F401
from tumour_board.tests.util import add, fact, make_doc

NOTE = ("SYNTHETIC\nOPD CLINICAL NOTE\nPresenting complaint: cough for three months\nQuestion for the board: surgery or chemoradiation?\n"
        "Report status: FINAL")
HPE = "SYNTHETIC\nHISTOPATHOLOGY REPORT\nDiagnosis: Adenocarcinoma, grade 2\nReport status: FINAL"
CT = "SYNTHETIC\nCT THORAX REPORT\nRight upper lobe mass measuring 3.2 cm\nImpression: stage as recorded cT2 N1 M0\nReport status: FINAL"
DIS = "SYNTHETIC\nDISCHARGE SUMMARY\nRight upper lobectomy done on 18/10/2026\nReport status: FINAL"

DECISION = {"outcome": "decision", "decision_text": "Upfront surgery, then adjuvant chemotherapy.", "intent": "curative", "responsible_doctor": "Dr Priya Nair",
            "recorded_by": "Anil Kumar", "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)", "board_date": "2026-09-10",
            "rationale": "Tumour size 3.2 cm with a node on imaging", "stage_as_agreed": "cT2 N1 M0", "stage_source": "report",
            "concerns": [{"by": "Dr Dev", "text": "Cardiac fitness first"}],
            "investigations": [{"item": "CT brain", "department": "Radiology", "due": "2026-09-20"}]}

P_OK = {"text": "The histopathology report records adenocarcinoma, grade 2.", "citations": [{"doc_id": "Da0000001", "quote": "Diagnosis: Adenocarcinoma, grade 2"}]}
P_OK2 = {"text": "The histopathology report records an adenocarcinoma of grade 2.", "citations": [{"doc_id": "Da0000001", "quote": "Diagnosis: Adenocarcinoma, grade 2"}]}
S_OK = {"text": "The discharge summary records a right upper lobectomy done on 18/10/2026.",
        "citations": [{"doc_id": "Da0000004", "quote": "Right upper lobectomy done on 18/10/2026"}]}
BAD_QUOTE = {"text": "The CT report records a pleural effusion.", "citations": [{"doc_id": "Da0000003", "quote": "small pleural effusion"}]}
BAD_NUMBER = {"text": "The CT report records a mass of 4.5 cm.", "citations": [{"doc_id": "Da0000003", "quote": "Right upper lobe mass measuring 3.2 cm"}]}
ADVICE = {"text": "Surgery is the best option for this patient.", "citations": [{"doc_id": "Da0000003", "quote": "Right upper lobe mass measuring 3.2 cm"}]}
RELATIVE = {"text": "The CT done last month records a mass of 3.2 cm.", "citations": [{"doc_id": "Da0000003", "quote": "Right upper lobe mass measuring 3.2 cm"}]}


def fake(monkeypatch, pres=(), since=(), fail=(), said=(), seen=None):
    """llm.chat replaced: the Case summary calls answer with the given sentences (`said` for what was said at the board); the
    adjudication calls find no claims. `seen` (a list) keeps every call's messages and keywords."""
    calls = []

    async def chat(role, msgs, **kw):
        p = kw.get("purpose") or ""
        calls.append(p)
        if seen is not None:
            seen.append({"purpose": p, "messages": msgs, **kw})
        if p.startswith("case summary"):
            sec = p.split()[-1]
            if sec in fail:
                raise llm.LLMError("the model server is down")
            return {"sentences": copy.deepcopy(list(pres if sec == "presentation" else said if sec == "discussion" else since))}
        return {"claims": []}
    monkeypatch.setattr(llm, "chat", chat)
    return calls


def docs_before(case_id):
    add(case_id,
        make_doc("Da0000002", "clinical_note", date="2026-09-01", text=NOTE, title="OPD CLINICAL NOTE",
                 facts={"presenting_complaint": fact("cough for three months", quote="Presenting complaint: cough for three months"),
                        "clinical_question": fact("surgery or chemoradiation?", quote="Question for the board: surgery or chemoradiation?")}),
        make_doc("Da0000001", "histopathology", date="2026-09-03", text=HPE, title="HISTOPATHOLOGY REPORT",
                 facts={"histologic_type": fact("Adenocarcinoma", quote="Diagnosis: Adenocarcinoma, grade 2")}),
        make_doc("Da0000003", "ct", date="2026-09-05", text=CT, title="CT THORAX REPORT", region="thorax",
                 facts={"recorded_stage": fact("cT2 N1 M0", quote="Impression: stage as recorded cT2 N1 M0"),
                        "lesion_size": fact("3.2 cm", quote="Right upper lobe mass measuring 3.2 cm")}))


def doc_after(case_id):
    add(case_id, make_doc("Da0000004", "discharge_summary", date="2026-10-20", text=DIS, title="DISCHARGE SUMMARY",
                          facts={"treatment_received": fact("Right upper lobectomy", quote="Right upper lobectomy done on 18/10/2026")}))


def decide(case_id, **over):
    return asyncio.run(postboard.record_decision(case_id, {**DECISION, **over}, "anil"))


def build(case_id, kind="on_demand", user="dr.rao"):
    return asyncio.run(cs.build(case_id, {"kind": kind}, user))


@pytest.fixture
def case(unit_case, monkeypatch):
    c = store.get_case(unit_case); c["department"] = OWNER; store.save_case(c)
    docs_before(unit_case)
    rules.evaluate(unit_case)
    monkeypatch.setattr(followup, "_today", lambda: date(2026, 9, 15))
    return unit_case


@pytest.fixture
def decided(case, monkeypatch):
    fake(monkeypatch)
    rec = decide(case)
    doc_after(case)
    return case, rec


def section(v, sid):
    return next(s for s in v["sections"] if s["id"] == sid)


def texts(v, sid):
    return [s["text"] for s in cs.all_sentences({"sections": [section(v, sid)]})]


def kinds(case_id):
    return [e.get("kind") for e in store.read_audit(case_id)]


# ---- 1. the five sections ----------------------------------------------------------------------------------------------------------

def test_a_decided_case_builds_the_five_sections_every_sentence_cited_or_code(decided, monkeypatch):
    case_id, rec = decided
    calls = fake(monkeypatch, pres=[P_OK], since=[S_OK])
    v = build(case_id)
    assert v["n"] == 1 and v["review"] == {"status": "ai_draft"} and v["label"] == "AI draft, not reviewed" and v["model_line"].endswith("(non-medical)")
    assert [s["id"] for s in v["sections"]] == ["presentation", "stage", "rounds", "since", "status"]
    assert [s["title"] for s in v["sections"]] == ["Presentation and diagnosis", "Stage", "Board rounds", "Treatment and follow-up since the board",
                                                  "Current status and open actions"]
    assert sorted(c for c in calls if c.startswith("case summary")) == ["case summary presentation", "case summary since"]
    sents = cs.all_sentences(v)
    assert sents and all(s.get("citations") or s.get("code") is True for s in sents)
    assert all("\u2014" not in s["text"] for s in sents)
    pres = texts(v, "presentation")
    assert P_OK["text"] in pres and any("cough for three months" in t for t in pres)  # the model's sentence, then the fact it did not carry
    assert section(v, "presentation")["sentences"][0]["id"] == "spresentation-1"
    assert texts(v, "since") == [S_OK["text"]]  # the lobectomy fact is carried by the sentence: not added twice
    st = texts(v, "stage")
    assert st[0] == 'The CT THORAX REPORT of 05/09/2026 records the stage as "cT2 N1 M0".'
    assert section(v, "stage")["sentences"][0]["citations"][0]["doc_id"] == "Da0000003"
    assert any(t.startswith("The board of 10/09/2026 recorded the stage as agreed") for t in st) and not any("differs" in t for t in st)
    block = section(v, "rounds")["blocks"][0]
    ids = [s["id"] for s in block["sentences"]]
    assert block["record"] == rec["id"] and block["date"] == "2026-09-10"
    for f in ("date", "question", "outcome", "decision_text", "rationale", "intent", "concerns-1", "stage_as_agreed", "responsible_doctor"):
        assert f"r{rec['id']}-{f}" in ids, f
    by = {s["id"]: s for s in block["sentences"]}
    assert by[f"r{rec['id']}-decision_text"]["text"] == 'Decision as recorded: "Upfront surgery, then adjuvant chemotherapy."'  # never '."."'
    c = by[f"r{rec['id']}-decision_text"]["citations"][0]
    assert c == {"kind": "board", "board_record": rec["id"], "version": 1, "field": "decision_text", "quote": DECISION["decision_text"], "board_date": "2026-09-10"}
    assert by[f"r{rec['id']}-intent"]["text"] == "Treatment intent as recorded: Curative."
    assert by[f"r{rec['id']}-concerns-1"]["text"] == 'Dr Dev recorded a view: "Cardiac fitness first".'
    assert by[f"r{rec['id']}-question"]["citations"][0]["doc_id"] == "Da0000002"
    actions = [s for s in block["sentences"] if s["id"].startswith(f"r{rec['id']}-action-")]
    assert any(s["text"] == 'Action raised: "CT brain" for Radiology, due 20/09/2026.' for s in actions)
    status = texts(v, "status")
    assert 'Open: "CT brain", Radiology, due 20/09/2026.' in status
    assert "Not yet recorded: the date the patient was told." in status and "Not yet recorded: the key worker." in status
    stored = store.get_state(case_id)["artefacts"]["case_summary"]
    assert stored["current"] == 1 and len(stored["versions"]) == 1 and stored["case_id"] == case_id
    ev = [e for e in store.read_audit(case_id) if e.get("kind") == "case_summary"][-1]
    assert ev["version"] == 1 and ev["sentences"] == len(sents) and ev["dropped"] == 0


def test_a_protected_case_is_refused(decided, monkeypatch):
    case_id, _ = decided
    monkeypatch.setattr(config, "PROTECTED_CASES", {case_id})
    with pytest.raises(ValueError, match="protected"):
        build(case_id)
    assert cs.schedule(case_id, {"kind": "decision"}, "anil")["how"] == "off"
    assert "case_summary" not in (store.get_state(case_id).get("artefacts") or {})


# ---- 2. the model's sentences are checked ------------------------------------------------------------------------------------------

def test_failing_model_sentences_are_removed_with_their_reason(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[P_OK, BAD_QUOTE, BAD_NUMBER, ADVICE, RELATIVE], since=[S_OK])
    v = build(case_id)
    assert texts(v, "presentation")[0] == P_OK["text"]
    by = {x["text"]: x for x in v["removed"]}
    assert by[BAD_QUOTE["text"]]["reason"] == "quote_not_found"
    assert by[BAD_NUMBER["text"]]["reason"] == "number_not_in_quote"
    assert by[ADVICE["text"]]["reason"] == "guardrail"
    assert by[RELATIVE["text"]]["reason"] == "relative_date" and "last month" in by[RELATIVE["text"]]["detail"]
    assert all(x["where"] == "presentation" for x in v["removed"])
    for t in (BAD_QUOTE, BAD_NUMBER, ADVICE, RELATIVE):
        assert t["text"] not in texts(v, "presentation")


def test_review_i1_advice_outside_the_quote_is_removed(decided, monkeypatch):
    """Advice in the sentence's own words is removed (the whole-run review I1, as narrowed by the Phase 9 review E, S1): an advice word
    outside the cited quote, or a need word next to a treatment word."""
    case_id, _ = decided
    outside = {"text": "The CT report records a 3.2 cm mass in the right upper lobe, so resection is warranted.",
               "citations": [{"doc_id": "Da0000003", "quote": "Right upper lobe mass measuring 3.2 cm"}]}
    needs = {"text": "Adenocarcinoma, grade 2 needs adjuvant treatment.", "citations": [{"doc_id": "Da0000001", "quote": "Diagnosis: Adenocarcinoma, grade 2"}]}
    fake(monkeypatch, pres=[P_OK, outside, needs], since=[S_OK])  # S_OK's "lobectomy" sits inside its quote
    v = build(case_id)
    assert texts(v, "presentation")[0] == P_OK["text"] and S_OK["text"] in texts(v, "since")
    by = {x["text"]: x for x in v["removed"]}
    assert by[outside["text"]]["reason"] == "guardrail" and "warranted" in by[outside["text"]]["detail"]
    assert by[needs["text"]]["reason"] == "guardrail" and "needs" in by[needs["text"]]["detail"]
    assert outside["text"] not in texts(v, "presentation") and needs["text"] not in texts(v, "presentation")


def test_review_e_s1_record_wording_with_a_treatment_word_is_kept(decided, monkeypatch):
    """The Phase 9 review E, S1: a document title or a past treatment named in the sentence's own words is not advice."""
    case_id, _ = decided
    title = {"text": "The surgical discharge summary records a right upper lobectomy done on 18/10/2026.",
             "citations": [{"doc_id": "Da0000004", "quote": "Right upper lobectomy done on 18/10/2026"}]}
    past = {"text": "Surgery was done on 18/10/2026: a right upper lobectomy.",
            "citations": [{"doc_id": "Da0000004", "quote": "Right upper lobectomy done on 18/10/2026"}]}
    fake(monkeypatch, pres=[P_OK], since=[title, past])
    v = build(case_id)
    assert title["text"] in texts(v, "since") and past["text"] in texts(v, "since")
    assert not [x for x in v["removed"] if x["reason"] == "guardrail"]


def test_a_sentence_citing_a_record_of_the_other_period_is_dropped(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[S_OK], since=[])  # the presentation is written from the records up to the board only
    v = build(case_id)
    assert S_OK["text"] not in texts(v, "presentation")
    assert [x["reason"] for x in v["removed"]] == ["not_given"]


def test_a_model_failure_leaves_the_fixed_sentence_and_the_build_completes(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[P_OK], fail=("since",))
    v = build(case_id)
    assert v["model_error"]["since"].startswith("LLMError") and "presentation" not in v["model_error"]
    # the treatment fact of the record after the board still fills the section, with its source and date
    assert texts(v, "since") == ["Treatment received: Right upper lobectomy (as recorded in the DISCHARGE SUMMARY, 20/10/2026)."]
    assert section(v, "since")["sentences"][0]["citations"][0]["doc_id"] == "Da0000004"
    assert "case_summary_model_error" in kinds(case_id)


# ---- 3. the board-field check ----------------------------------------------------------------------------------------------------

def test_verify_field():
    stored = "Upfront surgery, then adjuvant chemotherapy for 6 cycles."
    assert cs.verify_field("Upfront surgery, then adjuvant chemotherapy for 6 cycles.", stored)
    assert cs.verify_field("adjuvant  chemotherapy", stored)
    assert not cs.verify_field("Upfront surgery, then adjuvant radiotherapy", stored)  # one word changed
    assert not cs.verify_field("for 8 cycles", stored)  # a number not in the field
    assert not cs.verify_field("adjuvant chemotherapy", stored, sentence="Adjuvant chemotherapy for 6 cycles.")  # the sentence's 6 not in the quote
    assert cs.verify_field("chemotherapy for 6 cycles", stored, sentence="Adjuvant chemotherapy for 6 cycles.")
    assert not cs.verify_field("", stored)


# ---- 4. board rounds ---------------------------------------------------------------------------------------------------------------

def test_two_records_oldest_first_a_deferred_one_and_a_correction(decided, monkeypatch, people):
    case_id, first = decided
    fake(monkeypatch)
    second = asyncio.run(postboard.record_decision(case_id, {"outcome": "deferred", "awaited": "PET-CT report", "awaited_from": "Radiology",
                                                             "decision_text": "Deferred.", "board_date": "2026-10-25"}, "anil"))
    postboard.correct_record(case_id, first["id"], {"decision_text": "Upfront lobectomy, then adjuvant chemotherapy."}, "dr.rao", "Dr Rao", "Typo in the plan")
    v = build(case_id)
    blocks = section(v, "rounds")["blocks"]
    assert [b["record"] for b in blocks] == [first["id"], second["id"]] and [b["date"] for b in blocks] == ["2026-09-10", "2026-10-25"]
    assert [s["id"].split("-", 1)[1] for s in blocks[1]["sentences"]] == ["date", "outcome", "awaited"]
    assert blocks[1]["sentences"][2]["text"] == 'Awaited, as recorded: "PET-CT report" from Radiology.'
    b1 = {s["id"].split("-", 1)[1]: s for s in blocks[0]["sentences"]}
    assert b1["decision_text"]["text"] == 'Decision as recorded: "Upfront lobectomy, then adjuvant chemotherapy."'
    assert b1["decision_text"]["citations"][0]["version"] == 2 and blocks[0]["version"] == 2
    assert b1["corrected"]["text"].startswith("Corrected on ") and b1["corrected"]["text"].endswith("by Dr Rao: Typo in the plan.")
    assert b1["corrected"]["citations"][0]["field"] == "versions" and b1["corrected"]["citations"][0]["version"] == 2


def test_a_long_decision_is_shown_cut_and_quoted_whole(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch)
    long = "Upfront surgery " + "with a detailed plan of the board " * 30 + "end."
    rec = decide(case_id, decision_text=long, board_date="2026-10-26")
    v = build(case_id)
    s = next(x for b in section(v, "rounds")["blocks"] if b["record"] == rec["id"] for x in b["sentences"] if x["id"].endswith("-decision_text"))
    assert s["text"].endswith('..."') and len(s["text"]) < 650 and s["citations"][0]["quote"] == " ".join(long.split())


def test_members_cards_are_shown_by_name(decided, monkeypatch):
    case_id, rec = decided
    from tumour_board import meetings
    monkeypatch.setattr(meetings, "get", lambda mid: {"cards": {case_id: {"dr.ravi": {"agree": True, "note": "", "name": "Dr Ravi"},
                                                                          "dr.nair": {"agree": False, "note": "Wants a PET-CT first", "name": "Dr Nair"}}}}
                        if mid == "M1" else None)
    st = store.get_state(case_id)
    st["board_records"][0]["session"] = "M1"
    store.save_state(case_id, st)
    fake(monkeypatch)
    v = build(case_id)
    t = texts(v, "rounds")
    assert "Dr Ravi agreed." in t and 'Dr Nair recorded a concern: "Wants a PET-CT first".' in t
    s = next(x for b in section(v, "rounds")["blocks"] for x in b["sentences"] if x["text"].startswith("Dr Nair"))
    assert s["citations"][0] == {"kind": "card", "meeting": "M1", "user": "dr.nair", "board_date": "2026-09-10", "field": "note", "quote": "Wants a PET-CT first"}


# ---- 5. nothing to say ------------------------------------------------------------------------------------------------------------

def test_fixed_sentences_and_no_decision(case, monkeypatch, unit_case):
    fake(monkeypatch)
    out = build(case)
    assert out == {"status": "no_decision", "message": "No board decision has been recorded for this Case File."}
    assert "case_summary" not in (store.get_state(case).get("artefacts") or {})
    decide(case)
    v = build(case)  # no record dated after the board yet
    assert texts(v, "since") == ["No records dated after the board decision of 10/09/2026 have been added yet."]
    s = section(v, "since")["sentences"][0]
    assert s["code"] is True and s["citations"] == [] and s["id"] == "ssince-1"


def test_records_after_the_board_with_nothing_checked(decided, monkeypatch):
    case_id, _ = decided
    st = store.get_state(case_id)
    d = store.get_doc(case_id, "Da0000004"); d["facts"] = {}; store.save_doc(case_id, d); store._docs_cache.clear()
    fake(monkeypatch, since=[BAD_QUOTE])
    v = build(case_id)
    assert texts(v, "since") == ["Records dated after the board decision of 10/09/2026 are in the Case File, but no statement could be checked against them."]
    assert [x["reason"] for x in v["removed"]] == ["not_given"]  # the CT is a record of before the board


def test_nothing_documented_and_cannot_stage(unit_case, monkeypatch):
    c = store.get_case(unit_case); c["department"] = OWNER; store.save_case(c)
    add(unit_case, make_doc("Da0000009", "lab", date="2026-09-02", text="SYNTHETIC\nHAEMATOLOGY REPORT\nReport status: FINAL", title="HAEMATOLOGY REPORT"))
    fake(monkeypatch)
    decide(unit_case, stage_as_agreed="", stage_source="")
    v = build(unit_case)
    assert texts(v, "presentation") == ["Presenting complaint and diagnosis are not documented in the records of this Case File."]
    assert texts(v, "stage") == ["No stage is recorded in a signed report and none has been confirmed. Cannot stage."]
    assert all(s["code"] and not s["citations"] for s in section(v, "presentation")["sentences"] + section(v, "stage")["sentences"])


# ---- 6. stage ---------------------------------------------------------------------------------------------------------------------

def test_a_draft_stage_only_after_confirmation_and_a_differing_stage_is_shown(decided, monkeypatch, people):
    case_id, _ = decided
    fake(monkeypatch)
    st = store.get_state(case_id)
    st["staging"] = {"status": "staged", "stage": "IIB", "components": {"T": {"cat": "T2"}, "N": {"cat": "N1"}, "M": {"cat": "M0"}}, "rules": "unit",
                     "signature": rules.case_signature(case_id, st)["hash"], "confirmed": None, "rejected": None}
    store.save_state(case_id, st)
    v = build(case_id)
    assert not any(s.get("draft_stage") for s in section(v, "stage")["sentences"])
    staging.confirm(case_id, "dr.rao")
    v = build(case_id)
    d = [s for s in section(v, "stage")["sentences"] if s.get("draft_stage")]
    assert len(d) == 1 and d[0]["text"].startswith("Vaidyx draft stage, confirmed by Dr Rao on ") and d[0]["text"].endswith(": T2 N1 M0, stage IIB.")
    assert d[0]["citations"][0]["kind"] == "staging" and d[0]["citations"][0]["field"] == "confirmed"
    decide(case_id, board_date="2026-10-26", stage_as_agreed="cT3 N1 M0")
    v = build(case_id)
    diff = [s for s in section(v, "stage")["sentences"] if "differs" in s["text"]]
    assert len(diff) == 1 and diff[0]["flags"] == ["stage differs"]
    assert diff[0]["text"] == 'The stage recorded in the CT THORAX REPORT ("cT2 N1 M0") differs from the stage as agreed by the board on 26/10/2026.'
    assert texts(v, "stage")[0].endswith('records the stage as "cT2 N1 M0".')  # the report's stage is shown, never overridden


# ---- 7. open actions -------------------------------------------------------------------------------------------------------------

def test_open_actions_overdue_and_a_closure_with_a_record(decided, monkeypatch, people):
    case_id, rec = decided
    fake(monkeypatch)
    v = build(case_id)
    assert 'Open: "CT brain", Radiology, due 20/09/2026.' in texts(v, "status")
    monkeypatch.setattr(followup, "_today", lambda: date(2026, 9, 25))
    v = build(case_id)
    assert 'Open: "CT brain", Radiology, due 20/09/2026, overdue.' in texts(v, "status")
    before = json.dumps([s for s in v["sections"] if s["id"] != "status"], sort_keys=True)
    act = next(a for a in store.get_state(case_id)["actions"] if a.get("label") == "CT brain")
    add(case_id, make_doc("Da0000005", "ct", date="2026-09-22", text="SYNTHETIC\nCT BRAIN REPORT\nNo focal lesion.\nReport status: FINAL", title="CT BRAIN REPORT"))
    st = store.get_state(case_id)  # as the close route does: close in the state, then save it
    followup.close_action(st, act["id"], "dr.ravi", "Da0000005", "Seen")
    store.save_state(case_id, st)
    st = store.get_state(case_id)
    a = st["artefacts"]["case_summary"]
    assert len(a["versions"]) == 2 and a["current"] == 2  # no new version
    v2 = cs.current(st)
    assert v2.get("refreshed_at")
    t = texts(v2, "status")
    assert not any('"CT brain", Radiology' in x and x.startswith("Open") for x in t)
    closed = next(s for s in section(v2, "status")["sentences"] if s["text"].startswith("Closed") and "CT brain" in s["text"])
    assert " by Dr Ravi with the CT BRAIN REPORT" in closed["text"]
    doc = next(c for c in closed["citations"] if c.get("doc_id"))
    assert doc["doc_id"] == "Da0000005" and doc["doc_title"] == "CT BRAIN REPORT" and doc["quote"] == "CT BRAIN REPORT"
    assert json.dumps([s for s in v2["sections"] if s["id"] != "status"], sort_keys=True) == before
    assert cs.status(st, case_id)["status"] != "stale" or "Board actions" not in cs.status(st, case_id)["stale_reason"]


def test_refresh_status_changes_the_status_section_only(decided, monkeypatch):
    case_id, rec = decided
    fake(monkeypatch)
    build(case_id)
    st = store.get_state(case_id)
    old = copy.deepcopy(cs.current(st))
    postboard.update_communication(case_id, rec["id"], {"patient_informed_date": "12/09/2026", "informed_by": "Dr Priya Nair"}, user="anil")
    st = store.get_state(case_id)
    new = cs.current(st)
    assert len(st["artefacts"]["case_summary"]["versions"]) == 1
    assert "The patient was recorded as informed on 12/09/2026 by Dr Priya Nair." in texts(new, "status")
    for k in ("presentation", "stage", "rounds", "since"):
        assert section(new, k) == section(old, k)
    assert {k: v for k, v in new.items() if k not in ("sections", "refreshed_at", "inputs", "signature")} == \
        {k: v for k, v in old.items() if k not in ("sections", "refreshed_at", "inputs", "signature")}
    assert cs.refresh_status("TB-NONE") is None


# ---- 8. versions, review, edit -------------------------------------------------------------------------------------------------

@pytest.fixture
def app(case, people, monkeypatch):
    import routes.tumour_board_routes as R
    from tumour_board.api import case_summary as api
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    fa = FastAPI()
    who = {"user": "dr.rao"}

    @fa.middleware("http")
    async def auth(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    fa.include_router(R.setup_tumour_board_routes())
    if not any(getattr(r, "path", "") == "/api/tb/cases/{case_id}/case-summary" for r in fa.routes):  # until the routes file lists the router
        fa.include_router(api.router, prefix="/api/tb")
    fa.state.auth_manager = FakeAuth()
    with TestClient(fa) as tc:
        yield tc, who


def test_versions_reviews_and_edits(decided, monkeypatch, app):
    case_id, rec = decided
    tc, who = app
    fake(monkeypatch, pres=[P_OK], since=[S_OK])
    v1 = build(case_id)
    rv = cs.review(case_id, 1, "reviewed", "Read against the reports", "dr.rao")
    assert rv["generated"] == v1["built_at"] and rv["by_name"] == "Dr Rao"
    sid = "spresentation-1"
    s = cs.edit(case_id, 1, sid, "Adenocarcinoma, grade 2, as the histopathology report records.", "dr.rao", "Dr Rao")
    assert s["edited"]["by_name"] == "Dr Rao" and s["edited"]["checked"] is True and s["edited"]["vaidyx_text"] == P_OK["text"]
    s = cs.edit(case_id, 1, sid, "Adenocarcinoma, grade 4, as the histopathology report records.", "dr.rao", "Dr Rao")
    assert s["edited"]["checked"] is False  # 4 is in no quote (nor the title or date): "edited by Dr Rao, not checked against the record"
    s = cs.edit(case_id, 1, sid, "Adenocarcinoma, grade 2, as recorded by Dr Rao.", "dr.rao", "Dr Rao")
    assert s["edited"]["checked"] is False  # a name the quote does not carry
    s = cs.edit(case_id, 1, sid, "Adenocarcinoma, grade 2, as the histopathology report records.", "dr.rao", "Dr Rao")
    v = cs.current(store.get_state(case_id))
    assert [e["text"] for e in v["edits"]][-1] == s["text"] and len(v["edits"]) == 4 and v["edits"][0]["previous"] == P_OK["text"]
    assert v["edits"][0]["previous_citations"] and s["citations"] == v["edits"][0]["previous_citations"]
    with pytest.raises(ValueError, match="quotes the record itself"):
        cs.edit(case_id, 1, "sstage-1", "Stage IV.", "dr.rao", "Dr Rao")
    rid = section(v, "rounds")["blocks"][0]["sentences"][0]["id"]
    with pytest.raises(ValueError, match="quotes the record itself"):
        cs.edit(case_id, 1, rid, "Something else.", "dr.rao", "Dr Rao")
    with pytest.raises(ValueError):
        cs.edit(case_id, 1, sid, "   ", "dr.rao", "Dr Rao")
    v1_frozen = json.dumps(cs.current(store.get_state(case_id)), sort_keys=True)
    fake(monkeypatch, pres=[P_OK2], since=[S_OK])
    decide(case_id, board_date="2026-10-26")
    v2 = build(case_id, kind="decision")
    st = store.get_state(case_id)
    assert v2["n"] == 2 and st["artefacts"]["case_summary"]["current"] == 2
    assert json.dumps(st["artefacts"]["case_summary"]["versions"][0], sort_keys=True) == v1_frozen  # version 1 byte-identical
    assert st["artefacts"]["case_summary"]["versions"][0]["review"]["status"] == "reviewed" and v2["review"] == {"status": "ai_draft"}
    e = section(v2, "presentation")["sentences"][0]
    assert e["id"] == sid and e["text"] == "Adenocarcinoma, grade 2, as the histopathology report records."
    assert e["edited"]["by_name"] == "Dr Rao" and e["edited"]["carried_from"] == 1 and e["edited"]["records_changed"] is False
    assert e["edited"]["suggested"]["text"] == P_OK2["text"]  # the new model text beside the edit, never over it
    with pytest.raises(ValueError, match="current version"):
        cs.edit(case_id, 1, sid, "Old version edit.", "dr.rao", "Dr Rao")
    assert [h["n"] for h in cs.history(st)] == [1, 2] and cs.history(st)[0]["edits"] == 4
    # the routes: the resident and the coordinator may not review or edit
    for u in ("res.asha", "anil"):
        who["user"] = u
        r = tc.post(f"/api/tb/cases/{case_id}/case-summary/2/edit", json={"sentence_id": sid, "text": "Changed."})
        assert r.status_code == 403 and "Only the owning department's consultants edit the Case summary" in r.text, r.text
        r = tc.post(f"/api/tb/cases/{case_id}/case-summary/2/review", json={"status": "reviewed"})
        assert r.status_code == 403 and "Only the owning department's consultants review the Case summary" in r.text, r.text
    who["user"] = "dr.rao"
    r = tc.post(f"/api/tb/cases/{case_id}/case-summary/2/review", json={"status": "flagged", "comment": "The stage line needs a look"})
    assert r.status_code == 200 and r.json()["status"] == "flagged"
    r = tc.post(f"/api/tb/cases/{case_id}/case-summary/2/edit", json={"sentence_id": "sstage-1", "text": "Changed."})
    assert r.status_code == 400 and "quotes the record itself" in r.text
    r = tc.post(f"/api/tb/cases/{case_id}/case-summary/2/edit", json={"sentence_id": "ssince-1", "text": "Right upper lobectomy on 18/10/2026, as the discharge summary records."})
    assert r.status_code == 200 and r.json()["edited"]["by_name"] == "Dr Rao"
    st = store.get_state(case_id)
    revs = [x for x in st["reviews"] if x.get("artefact") == "case_summary"]
    assert [(x["version"], x["status"]) for x in revs] == [(1, "reviewed"), (2, "flagged")]
    ev = store.read_audit(case_id)
    assert sum(1 for x in ev if x.get("kind") == "case_summary_edit") == 5
    assert [(x.get("version"), x.get("status")) for x in ev if x.get("kind") == "expert_review" and x.get("artefact") == "case_summary"] == [(1, "reviewed"), (2, "flagged")]


def test_review_m6_an_edit_loses_the_en_dash_as_well_as_the_em_dash(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    s = cs.edit(case_id, 1, "spresentation-1", "Adenocarcinoma \u2013 grade 2 \u2014 in the histopathology report.", "dr.rao", "Dr Rao")
    assert s["text"] == "Adenocarcinoma - grade 2 - in the histopathology report."


def test_an_edit_whose_record_changed_is_marked(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    cs.edit(case_id, 1, "spresentation-1", "Adenocarcinoma, grade 2, in the histopathology report.", "dr.rao", "Dr Rao")
    d = store.get_doc(case_id, "Da0000001"); d["processed"] = "2026-10-26T09:00:00"; store.save_doc(case_id, d); store._docs_cache.clear()
    v = build(case_id)
    e = section(v, "presentation")["sentences"][0]
    assert e["text"] == "Adenocarcinoma, grade 2, in the histopathology report." and e["edited"]["records_changed"] is True
    assert "suggested" not in e["edited"]  # the model wrote the same sentence as before the edit: nothing new to suggest
    assert cs.status(store.get_state(case_id), case_id)["status"] == "ready"


def test_an_edit_back_to_the_vaidyx_text_clears_the_mark(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    cs.edit(case_id, 1, "spresentation-1", "Adenocarcinoma, grade 2.", "dr.rao", "Dr Rao")
    s = cs.edit(case_id, 1, "spresentation-1", P_OK["text"], "dr.rao", "Dr Rao")
    assert "edited" not in s and len(cs.current(store.get_state(case_id))["edits"]) == 2


# ---- 9. the background build --------------------------------------------------------------------------------------------------------

def test_schedule_one_build_then_one_more_queued(decided, monkeypatch):
    case_id, _ = decided
    from tumour_board import ready_hook
    fake(monkeypatch)
    monkeypatch.setenv("TB_SCHEDULER", "1")
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)
    calls = []

    async def main():
        gate = asyncio.Event()

        async def slow_build(cid, trigger, user=""):
            calls.append(trigger)
            await gate.wait()
            return {}
        monkeypatch.setattr(cs, "build", slow_build)
        await postboard.record_decision(case_id, {**DECISION, "board_date": "2026-10-26"}, "anil")
        await asyncio.sleep(0)
        assert cs.building(case_id) and cs.status(store.get_state(case_id), case_id)["status"] == "building"
        await postboard.record_decision(case_id, {**DECISION, "board_date": "2026-10-27"}, "anil")
        rec3 = await postboard.record_decision(case_id, {**DECISION, "board_date": "2026-10-28"}, "anil")
        gate.set()
        while cs.TASKS:
            await asyncio.gather(*list(cs.TASKS))
        return rec3
    rec3 = asyncio.run(main())
    assert len(calls) == 2 and calls[0]["kind"] == "decision" and calls[1]["record"] == rec3["id"]
    assert not cs.building(case_id)


def test_scheduled_build_writes_a_version_and_tells_the_owner(decided, monkeypatch):
    case_id, rec = decided
    from tumour_board import ready_hook
    fake(monkeypatch, pres=[P_OK])
    monkeypatch.setenv("TB_SCHEDULER", "1")
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)

    async def main():
        out = await postboard.record_decision(case_id, {**DECISION, "board_date": "2026-10-26"}, "anil")
        while cs.TASKS:
            await asyncio.gather(*list(cs.TASKS))
        return out
    asyncio.run(main())
    v = cs.current(store.get_state(case_id))
    assert v["n"] == 1 and v["trigger"]["kind"] == "decision"
    n = [x for x in notify._load() if x["title"].startswith("Summary after the board updated")]
    assert len(n) == 1 and "Version 1 after the board decision of 26/10/2026: AI draft, not reviewed." in n[0]["text"]


def test_a_failed_background_build_is_audited_and_the_old_version_stays(decided, monkeypatch):
    case_id, _ = decided
    from tumour_board import ready_hook
    fake(monkeypatch)
    build(case_id)
    monkeypatch.setenv("TB_SCHEDULER", "1")
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)

    async def broken(cid, trigger, user=""):
        raise RuntimeError("disk full")
    monkeypatch.setattr(cs, "build", broken)

    async def main():
        assert cs.schedule(case_id, {"kind": "correction", "record": "B1"}, "dr.rao")["scheduled"]
        while cs.TASKS:
            await asyncio.gather(*list(cs.TASKS))
    asyncio.run(main())
    ev = [e for e in store.read_audit(case_id) if e.get("kind") == "case_summary_failed"]
    assert len(ev) == 1 and "disk full" in ev[0]["why"]
    st = store.get_state(case_id)
    assert st["artefacts"]["case_summary"]["current"] == 1 and len(st["artefacts"]["case_summary"]["versions"]) == 1 and not cs.building(case_id)


def test_the_scheduler_is_off_in_the_unit_suite_by_default(decided, monkeypatch):
    case_id, _ = decided
    monkeypatch.delenv("TB_SCHEDULER", raising=False)
    assert cs.schedule(case_id, {"kind": "decision"}, "anil") == {"scheduled": False, "how": "off", "reason": "TB_SCHEDULER=0"}
    monkeypatch.setenv("TB_SCHEDULER", "0")
    assert not cs.enabled()


# ---- 10. the summary line ----------------------------------------------------------------------------------------------------------

def test_summary_line(decided, monkeypatch):
    case_id, rec = decided
    st = store.get_state(case_id)
    line = cs.summary_line(st, store.get_case(case_id))
    assert line.startswith("Adenocarcinoma") and "cT2 N1 M0" in line and "board 10/09/2026: Upfront surgery, then adjuvant chemotherapy." in line
    assert line.endswith("2 actions open") and len(line) <= 160 and "\u2014" not in line
    decide(case_id, board_date="2026-10-26", decision_text="Adjuvant chemotherapy " + "as discussed at length " * 10)
    line = cs.summary_line(store.get_state(case_id), store.get_case(case_id))
    assert len(line) <= 160 and "board 26/10/2026: Adjuvant chemotherapy as discussed" in line and "..." in line


# ---- 11. the routes -------------------------------------------------------------------------------------------------------------

def test_routes_read_build_and_no_decision(case, monkeypatch, app):
    tc, who = app
    fake(monkeypatch, pres=[P_OK])
    who["user"] = "anil"
    r = tc.post(f"/api/tb/cases/{case}/case-summary", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_decision"
    who["user"] = "dr.rao"
    r = tc.get(f"/api/tb/cases/{case}/case-summary")
    assert r.status_code == 200 and r.json() == {"current": None, "versions": [], "version": None,
                                                 "status": {"status": "none", "version": None, "built_at": None, "stale_reason": ""}, "view": None}
    decide(case)
    who["user"] = "anil"  # the MDT Coordinator builds on demand
    r = tc.post(f"/api/tb/cases/{case}/case-summary", json={"force": True})
    assert r.status_code == 200 and r.json()["n"] == 1 and r.json()["trigger"] == {"kind": "on_demand", "by": "anil", "force": True}
    who["user"] = "dr.ravi"  # a doctor of another department who is not on the Case File
    assert tc.post(f"/api/tb/cases/{case}/case-summary", json={}).status_code == 403
    who["user"] = "dr.rao"
    r = tc.get(f"/api/tb/cases/{case}/case-summary")
    j = r.json()
    assert r.status_code == 200 and j["current"] == 1 and j["version"]["n"] == 1 and [h["n"] for h in j["versions"]] == [1]
    assert j["status"]["status"] == "ready"
    r = tc.get(f"/api/tb/cases/{case}")
    assert r.status_code == 200 and r.json()["state"]["artefacts"]["case_summary"]["current"] == 1
    assert "case_summary" in kinds(case)


def test_a_read_shows_overdue_today_and_writes_nothing(decided, monkeypatch, app):
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch)
    build(case_id)
    before = json.dumps(store.get_state(case_id), sort_keys=True)
    monkeypatch.setattr(followup, "_today", lambda: date(2026, 9, 25))
    j = tc.get(f"/api/tb/cases/{case_id}/case-summary").json()
    assert 'Open: "CT brain", Radiology, due 20/09/2026, overdue.' in texts(j["version"], "status") and len(j["versions"]) == 1
    assert 'Open: "CT brain", Radiology, due 20/09/2026, overdue.' in texts(j["view"], "status")
    assert json.dumps(store.get_state(case_id), sort_keys=True) == before  # never a write on a read (review N3)
    st = store.get_state(case_id)
    assert 'Open: "CT brain", Radiology, due 20/09/2026.' in texts(cs.current(st), "status")  # the stored version as it was built


# ---- item 3.4: the summary line, the version picker, the view ---------------------------------------------------------------------

def test_the_summary_line_is_written_on_build_kept_when_edited_and_marked_stale(decided, monkeypatch, app):
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    line = store.get_case(case_id)["summary_line"]
    assert line["text"] == cs.summary_line(store.get_state(case_id), store.get_case(case_id)) and line["edited"] is False
    assert line["version"] == 1 and line["by"] == "vaidyx" and line["by_name"] == "Vaidyx" and line["text"].endswith("2 actions open")
    # the consultant writes it; a resident and the coordinator may not
    for u in ("res.asha", "anil"):
        who["user"] = u
        r = tc.post(f"/api/tb/cases/{case_id}/summary-line", json={"text": "Changed."})
        assert r.status_code == 403 and "Only the owning department's consultants edit the summary line" in r.text
    who["user"] = "dr.rao"
    r = tc.post(f"/api/tb/cases/{case_id}/summary-line", json={"text": "  Adenocarcinoma — right upper lobe;   surgery first  "})
    assert r.status_code == 200, r.text
    got = r.json()["summary_line"]
    assert got["text"] == "Adenocarcinoma - right upper lobe; surgery first" and got["edited"] is True and got["by_name"] == "Dr Rao" and got["stale"] is False
    assert got["vaidyx_text"] == line["text"]
    assert tc.post(f"/api/tb/cases/{case_id}/summary-line", json={"text": "x" * 161}).status_code == 400
    # a rebuild keeps the edited line; the Vaidyx line now differs (a new decision), so it is marked stale
    decide(case_id, board_date="2026-10-26", decision_text="Adjuvant chemotherapy after surgery.")
    build(case_id, kind="decision")
    kept = store.get_case(case_id)["summary_line"]
    assert kept["text"] == got["text"] and kept["edited"] is True and kept["stale"] is True
    assert "board 26/10/2026: Adjuvant chemotherapy after surgery." in kept["vaidyx_text"]
    # an empty text goes back to the Vaidyx line
    r = tc.post(f"/api/tb/cases/{case_id}/summary-line", json={"text": ""})
    back = r.json()["summary_line"]
    assert r.status_code == 200 and back["edited"] is False and back["text"] == kept["vaidyx_text"] and back["version"] == 2
    ev = [e for e in store.read_audit(case_id) if e.get("kind") == "summary_line_edit"]
    assert [e["edited"] for e in ev] == [True, False] and ev[0]["by"] == "dr.rao"
    # the Case File view carries the line in the case record
    assert tc.get(f"/api/tb/cases/{case_id}").json()["case"]["summary_line"]["text"] == back["text"]


def test_no_summary_line_before_a_case_summary(case, monkeypatch, app):
    tc, who = app
    r = tc.post(f"/api/tb/cases/{case}/summary-line", json={"text": "Something"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_case_summary"
    assert "summary_line" not in store.get_case(case)


def test_a_closure_updates_the_actions_count_of_the_line(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch)
    build(case_id)
    assert store.get_case(case_id)["summary_line"]["text"].endswith("2 actions open")
    act = next(a for a in store.get_state(case_id)["actions"] if a.get("label") == "CT brain")
    st = store.get_state(case_id)
    followup.close_action(st, act["id"], "dr.ravi")
    store.save_state(case_id, st)
    assert store.get_case(case_id)["summary_line"]["text"].endswith("1 action open")


def test_get_a_version_by_number_and_the_view(decided, monkeypatch, app):
    case_id, rec = decided
    tc, who = app
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    decide(case_id, board_date="2026-10-26")
    build(case_id, kind="decision")
    j = tc.get(f"/api/tb/cases/{case_id}/case-summary", params={"n": 1}).json()
    assert j["current"] == 2 and j["version"]["n"] == 1 and j["view"]["n"] == 1 and j["view"]["current"] == 2
    assert tc.get(f"/api/tb/cases/{case_id}/case-summary").json()["version"]["n"] == 2
    assert tc.get(f"/api/tb/cases/{case_id}/case-summary", params={"n": 9}).status_code == 404
    assert tc.get(f"/api/tb/cases/{case_id}/case-summary", params={"n": "x"}).status_code == 400
    c = next(c for b in section(j["version"], "rounds")["blocks"] for s in b["sentences"] if s["id"].endswith("-decision_text") for c in s["citations"])
    assert c["label"] == "Decision, in the board's words"
    assert "label" not in store.get_state(case_id)["artefacts"]["case_summary"]["versions"][0]["sections"][2]["blocks"][0]["sentences"][2]["citations"][0]
    v = cs.view(case_id, store.get_state(case_id), None)
    assert set(v) >= {"status", "current", "built_at", "trigger", "model_line", "label", "stale_reason", "review", "sections", "removed", "edits",
                      "first_board_date", "versions", "can"}
    assert v["status"] == "ready" and v["label"] == "AI draft, not reviewed" and v["can"] == {"build": False, "review": False, "edit": False}
    assert [x["n"] for x in v["versions"]] == [1, 2] and v["versions"][0]["trigger"] == {"kind": "on_demand"} and v["first_board_date"] == "2026-09-10"
    cs.review(case_id, 2, "reviewed", "", "dr.rao")
    v = cs.view(case_id, store.get_state(case_id), None)
    assert v["status"] == "reviewed" and v["label"] == "Reviewed by Dr Rao" and v["versions"][1]["review"] == {"status": "reviewed", "by_name": "Dr Rao"}


# ---- the Phase 3 review fixes ---------------------------------------------------------------------------------------------------

PAIN = {"text": "The OPD clinical note records cough for three months.", "citations": [{"doc_id": "Da0000002", "quote": "Presenting complaint: cough for three months"}]}
MASS = {"text": "The CT thorax report records a right upper lobe mass measuring 3.2 cm.",
        "citations": [{"doc_id": "Da0000003", "quote": "Right upper lobe mass measuring 3.2 cm"}]}
EDITED = "Adenocarcinoma, grade 2, as the histopathology report records."


def test_an_edit_follows_its_sentence_when_the_model_reorders(decided, monkeypatch):
    case_id, _ = decided
    fake(monkeypatch, pres=[PAIN, P_OK])
    build(case_id)
    cs.edit(case_id, 1, "spresentation-2", EDITED, "dr.rao", "Dr Rao")
    fake(monkeypatch, pres=[MASS, PAIN, P_OK])  # the same sentences in another order, one more in front
    v = build(case_id)
    sents = section(v, "presentation")["sentences"]
    t = [x["text"] for x in sents]
    assert t[:3] == [MASS["text"], PAIN["text"], EDITED] and P_OK["text"] not in t and t.count(EDITED) == 1
    e = sents[2]
    assert e["id"] == "spresentation-3" and e["edited"]["by_name"] == "Dr Rao" and "suggested" not in e["edited"]
    assert e["citations"][0]["doc_id"] == "Da0000001" and "edited" not in sents[1]
    cs.edit(case_id, 2, "spresentation-3", EDITED + " Signed.", "dr.rao", "Dr Rao")  # the carried edit is edited again on the new version
    fake(monkeypatch, pres=[MASS])  # the model no longer writes the histopathology sentence and no fact cites its line: the edit stays, at the end
    d = store.get_doc(case_id, "Da0000001"); d["facts"] = {}; store.save_doc(case_id, d); store._docs_cache.clear()
    v = build(case_id)
    sents = section(v, "presentation")["sentences"]
    assert sents[0]["text"] == MASS["text"] and "edited" not in sents[0]
    last = [x for x in sents if isinstance(x.get("edited"), dict)]
    assert len(last) == 1 and last[0]["text"] == EDITED + " Signed." and last[0]["edited"]["unmatched"] is True and last[0] is sents[-1]
    assert len({x["id"] for x in sents}) == len(sents)


def test_a_source_date_after_a_title_with_brackets_reads_dd_mm_yyyy():
    s = [{"text": "Histologic type: Adenocarcinoma (as recorded in the IMMUNOHISTOCHEMISTRY REPORT: HER2 (GASTRIC), 2026-09-03)."}]
    assert cs._SOURCE_DATE.sub(lambda m: ", " + cs.dmy(m.group(1)) + m.group(2), s[0]["text"]).endswith("HER2 (GASTRIC), 03/09/2026).")


@pytest.mark.parametrize("text", ["Two weeks later the CT was repeated.", "The following day she was discharged.", "A week after surgery the drain was removed.",
                                  "3 months later the CT was repeated.", "The CT was done 10 days earlier."])
def test_relative_dates_are_caught(text):
    assert cs.RELATIVE.search(text)


@pytest.mark.parametrize("text", ["She presented with cough for three months.", "Surgery on 18/10/2026.", "After surgery on 18/10/2026 the drain was removed."])
def test_dated_sentences_pass(text):
    assert not cs.RELATIVE.search(text)


def test_the_old_review_route_refuses_the_case_summary(decided, monkeypatch, app):
    from tumour_board import service
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch)
    build(case_id)
    with pytest.raises(ValueError, match="Case summary"):
        service.review(case_id, "case_summary", "reviewed", "", "res.asha")
    for art in ("case_summary", "summary_history"):
        who["user"] = "dr.rao"
        r = tc.post(f"/api/tb/cases/{case_id}/review", json={"artefact": art, "status": "reviewed"})
        assert r.status_code == 400, r.text
    assert cs.current(store.get_state(case_id))["review"] == {"status": "ai_draft"}


def test_the_case_file_view_sends_the_case_summary_short(decided, monkeypatch, app):
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch, pres=[P_OK])
    build(case_id)
    build(case_id)
    st = store.get_state(case_id)
    st["artefacts"]["summary_history"] = [{"generated": "2026-09-08T10:00:00", "archived_at": "2026-09-09T10:00:00", "review": {"status": "reviewed"},
                                           "sections": [{"id": "presentation", "sentences": [{"text": "x"}]}]}]
    store.save_state(case_id, st)
    a = tc.get(f"/api/tb/cases/{case_id}").json()["state"]["artefacts"]
    assert set(a["case_summary"]) == {"current", "case_id", "versions", "version"} and a["case_summary"]["current"] == 2
    assert [v["n"] for v in a["case_summary"]["versions"]] == [1, 2] and a["case_summary"]["version"]["n"] == 2 and "sections" not in a["case_summary"]["versions"][0]
    assert a["summary_history"] == [{"generated": "2026-09-08T10:00:00", "archived_at": "2026-09-09T10:00:00", "review": {"status": "reviewed"}}]
    assert len(store.get_state(case_id)["artefacts"]["summary_history"][0]["sections"]) == 1  # on disk in full


def test_the_wording_of_code_sentences(decided, monkeypatch):
    case_id, rec = decided
    fake(monkeypatch)
    st = store.get_state(case_id)
    st["staging"] = {"status": "staged", "stage": "IIB", "confirmed": {"by": "dr.rao", "at": "2026-09-09T10:00:00"}, "rejected": None,
                     "components": {"T": {"cat": "T2"}, "N": {"cat": "N1"}, "M": {"cat": "M0"}}}
    store.save_state(case_id, st)
    r2 = decide(case_id, board_date="2026-10-26", stage_source="confirmed_draft", referrals=[{"kind": "nutrition", "department": "Nutrition"}],
                decision_text="Adjuvant chemotherapy. Review in clinic!")
    v = build(case_id)
    t = texts(v, "rounds")
    assert 'Decision as recorded: "Adjuvant chemotherapy. Review in clinic!"' in t
    assert "Referrals as recorded: Nutrition." in t and not any("Nutrition (Nutrition)" in x for x in t)
    assert any(x.endswith("(a Vaidyx draft stage a doctor confirmed).") for x in texts(v, "stage"))
    bad = [x for s in ("rounds", "status", "stage") for x in texts(v, s) if x.endswith('".') and x[:-2].endswith((".", "!", "?"))]
    assert bad == []
    assert "In the order the board stated it" == __import__("tumour_board.decision_record", fromlist=["x"]).BY_KEY["sequence"]["hint"]


# ---- the Phase 3 follow-up review ----------------------------------------------------------------------------------------------

def test_the_summary_line_never_reaches_a_department_only_asked(decided, monkeypatch, app):
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch)
    build(case_id)
    st = store.get_state(case_id)
    st["actions"].append({"id": "AREQ1", "source": "pre_authorization", "requirement": "ct_thorax", "label": "CT thorax", "department": "Radiology",
                          "department_id": "radiology", "status": "pending", "created": store.now_iso(), "due": "2026-12-01", "history": [],
                          "sent": {"by": "dr.rao", "at": store.now_iso(), "count": 1}})
    store.save_state(case_id, st)
    assert store.get_case(case_id)["summary_line"]["text"]
    rows = {x["case_id"]: x for x in tc.get("/api/tb/cases").json()["cases"]}
    assert rows[case_id]["summary_line"]["text"] and rows[case_id]["scope"] == "full"  # the owner's consultant
    who["user"] = "dr.ravi"  # Radiology was only asked for the CT
    rows = {x["case_id"]: x for x in tc.get("/api/tb/cases").json()["cases"]}
    assert rows[case_id]["scope"] == "requests" and "summary_line" not in rows[case_id]
    assert "summary_line" not in tc.get(f"/api/tb/cases/{case_id}").json()["case"]
    assert tc.post(f"/api/tb/cases/{case_id}/archive", json={"reason": "x"}).status_code == 403
    who["user"] = "dr.rao"
    r = tc.post(f"/api/tb/cases/{case_id}/archive", json={"reason": "duplicate (synthetic)"})
    assert r.status_code == 200 and r.json()["case"]["summary_line"]["text"]
    assert cs.case_for(store.get_case(case_id), "requests").get("summary_line") is None and cs.case_for(store.get_case(case_id), "full")["summary_line"]
    assert cs.case_for(store.get_case(case_id), "meeting").get("summary_line") is None


def test_only_the_newest_three_archived_pre_board_summaries_come_in_full():
    sec = [{"id": "presentation", "title": "Presentation", "sentences": [{"text": "a"}, {"text": "b"}]}]
    hist = [{"generated": f"2026-09-0{i}T10:00:00", "archived_at": f"2026-09-0{i + 1}T10:00:00", "review": {"status": "ai_draft"}, "model": "m",
             "sections": sec} for i in range(1, 6)]
    st = {"artefacts": {"summary_history": hist, "summary": {"generated": "2026-09-07T10:00:00", "review": {"status": "reviewed", "by": "dr.rao"}, "model": "m", "sections": sec}}}
    h = cs.pre_board_history(st)
    assert [x["full"] for x in h] == [False, False, True, True, True, True] and h[-1]["live"] is True
    assert set(h[0]) == {"generated", "archived_at", "review", "model", "sentences", "live", "full"} and h[0]["sentences"] == 2
    assert h[2]["paragraphs"][0]["sentences"] == sec[0]["sentences"] and h[-1]["review"]["status"] == "reviewed"


# ---- 9. what was said at the board (meetings-v2 item 5.4, owner decision D14) ---------------------------------------------------------

SAID_LINES = [
    {"id": "n1", "text": "Dr Suresh noted the size of the mass in the CT thorax report.",
     "said": {"segment_id": "g1", "speaker": "dr.suresh", "speaker_name": "Dr Suresh", "department": "", "at": "2026-09-10T10:42:05",
              "quote": "The CT thorax report shows a 3.2 cm mass in the right upper lobe"}},
    {"id": "n2", "text": "In the room, someone asked whether pathology can confirm the EGFR status.",
     "said": {"segment_id": "g2", "speaker": "room", "speaker_name": "Board room", "department": "", "at": "2026-09-10T10:43:00",
              "quote": "Can pathology confirm the EGFR status before the next meeting?"}},
    {"id": "n3", "text": "Dr Lata gave their view on surgery.",
     "said": {"segment_id": "g3", "speaker": "dr.lata", "speaker_name": "Dr Lata", "department": "", "at": "2026-09-10T10:44:00",
              "quote": "I would recommend a lobectomy if the PET-CT shows no distant disease"}}]
SAID_OK = [  # given out of order: kept in the order spoken
    {"text": "At the board of 10/09/2026, someone in the room asked: \"Can pathology confirm the EGFR status before the next meeting?\"",
     "citations": [{"note_line": "n2", "quote": "Can pathology confirm the EGFR status before the next meeting?"}]},
    {"text": "At the board of 10/09/2026, Dr Suresh noted that the CT thorax report shows a 3.2 cm mass.",
     "citations": [{"note_line": "n1", "quote": "the CT thorax report shows a 3.2 cm mass"}]},
    {"text": "At the board of 10/09/2026, Dr Lata gave her view: \"I would recommend a lobectomy if the PET-CT shows no distant disease\".",
     "citations": [{"note_line": "n3", "quote": "I would recommend a lobectomy if the PET-CT shows no distant disease"}]}]
SAID_BAD = [
    ("said_as_decision", {"text": "At the board of 10/09/2026, the board agreed on a lobectomy as Dr Lata said.", "citations": [{"note_line": "n3", "quote": "I would recommend a lobectomy"}]}),
    ("guardrail", {"text": "At the board of 10/09/2026, Dr Lata said a lobectomy is the best option.", "citations": [{"note_line": "n3", "quote": "I would recommend a lobectomy"}]}),
    ("quote_not_found", {"text": "At the board of 10/09/2026, Dr Suresh noted a 4.5 cm mass.", "citations": [{"note_line": "n1", "quote": "a 4.5 cm mass"}]}),
    ("quote_not_found", {"text": "At the board of 10/09/2026, Dr Suresh noted a mass.", "citations": [{"note_line": "n1", "quote": "mass"}]}),  # too short
    ("not_attributed", {"text": "At the board of 10/09/2026, it was noted that the CT thorax report shows a 3.2 cm mass.",
                        "citations": [{"note_line": "n1", "quote": "the CT thorax report shows a 3.2 cm mass"}]}),
    ("names", {"text": "At the board of 10/09/2026, Dr Suresh told Pathology that the CT thorax report shows a 3.2 cm mass.",
               "citations": [{"note_line": "n1", "quote": "the CT thorax report shows a 3.2 cm mass"}]}),
    ("not_given", {"text": "At the board of 10/09/2026, Dr Suresh noted a mass.", "citations": [{"note_line": "n9", "quote": "the CT thorax report shows"}]}),
    ("number_not_in_quote", {"text": "At the board of 10/09/2026, Dr Suresh noted a 4 cm node and that the CT thorax report shows a 3.2 cm mass.",
                             "citations": [{"note_line": "n1", "quote": "the CT thorax report shows a 3.2 cm mass"}]}),
    ("relative_date", {"text": "Last month Dr Suresh noted that the CT thorax report shows a 3.2 cm mass.", "citations": [{"note_line": "n1", "quote": "the CT thorax report shows a 3.2 cm mass"}]}),
    ("no_citation", {"text": "Dr Suresh spoke about the mass.", "citations": []})]


def with_notes(case_id, monkeypatch, lines=None, mid="M1"):
    """The first board record came from meeting `mid`, which kept the AI discussion notes `lines` for this Case File."""
    from tumour_board import meetings
    m = {"id": mid, "date": "2026-09-10", "status": "closed", "notes": {case_id: {"lines": copy.deepcopy(SAID_LINES if lines is None else lines), "review": {"status": "draft"}}}}
    monkeypatch.setattr(meetings, "get", lambda x: m if x == mid else None)
    st = store.get_state(case_id)
    st["board_records"][0]["session"] = mid
    store.save_state(case_id, st)
    return m


def test_the_summary_after_the_board_cites_what_was_said(decided, monkeypatch):
    case_id, rec = decided
    m = with_notes(case_id, monkeypatch)
    seen = []
    fake(monkeypatch, pres=[P_OK], since=[S_OK], said=[x for _, x in SAID_BAD] + SAID_OK, seen=seen)
    v = build(case_id)
    assert v["title"] == cs.TITLE == "Summary after the board" and v["label"] == "AI draft, not reviewed" and v["last_board_date"] == "2026-09-10"
    assert [s["id"] for s in v["sections"]] == ["presentation", "stage", "rounds", "discussion", "since", "status"]
    disc = section(v, "discussion")
    assert disc["title"] == "What was said at the board" and disc["built_by"] == "model" and disc["context"]["lines"] == 3
    assert [s["text"] for s in disc["sentences"]] == [SAID_OK[1]["text"], SAID_OK[0]["text"], SAID_OK[2]["text"]]  # the order spoken
    assert [s["id"] for s in disc["sentences"]] == ["sdiscussion-1", "sdiscussion-2", "sdiscussion-3"]
    assert all(not s.get("code") and not s.get("fixed") for s in disc["sentences"])  # model sentences: the AI mark on screen
    c = disc["sentences"][0]["citations"][0]
    assert c == {"kind": "said", "meeting_id": "M1", "line_id": "n1", "speaker": "dr.suresh", "speaker_name": "Dr Suresh", "department": "",
                 "at": "2026-09-10T10:42:05", "board_date": "2026-09-10", "quote": "the CT thorax report shows a 3.2 cm mass"}
    assert disc["sentences"][1]["citations"][0]["speaker"] == "room"
    dropped = sorted(r["reason"] for r in v["removed"] if r["where"] == "discussion")
    assert dropped == sorted(r for r, _ in SAID_BAD)
    assert next(r for r in v["removed"] if r["reason"] == "not_given")["citations"][0]["note_line"] == "n9"
    assert all("—" not in s["text"] for s in disc["sentences"])
    assert v["inputs"]["notes"] == [{"meeting_id": "M1", "lines": 3}] and v["signature"]["parts"]["notes"]
    # the prompt: the notes as what was said at the board, attributed to the speakers; never the patient's name
    call = next(x for x in seen if x["purpose"] == "case summary discussion")
    assert call["json_schema"] == cs.DISCUSSION_SCHEMA
    sysm, user = call["messages"][0]["content"], call["messages"][1]["content"]
    assert user.startswith("WHAT WAS SAID AT THE BOARD (the discussion notes of this Case File, attributed to the speakers; not the board's decision)")
    assert "BOARD OF 10/09/2026 (meeting notes, AI draft, not reviewed):" in user
    assert ('[n1] 10:42 Dr Suresh. Note: Dr Suresh noted the size of the mass in the CT thorax report. Exact words: '
            '"The CT thorax report shows a 3.2 cm mass in the right upper lobe"') in user
    assert "[n2] 10:43 Board room microphone (speaker not known)." in user
    assert store.get_case(case_id)["patient"]["name"] not in user
    assert "never turn what someone said into a decision or a plan" in sysm and "never decide, advise, diagnose, stage" in sysm
    # verify_said: the line is still in the notes and the quote is word for word in what was said
    assert cs.verify_said(case_id, c) and cs.verify_said(case_id, {**c, "quote": "the ct THORAX report  shows a 3.2 cm mass"})
    for bad in ({"quote": "a 4.5 cm mass"}, {"quote": "mass"}, {"line_id": "n9"}, {"meeting_id": "M2"}, {"kind": "card"}):
        assert not cs.verify_said(case_id, {**c, **bad}), bad
    assert not cs.verify_said(case_id, c, sentence="Dr Suresh noted a 5 cm mass.")
    # the view: the title beside the pre-board summary's, and the latest board date
    view = cs.view(case_id, store.get_state(case_id))
    assert (view["title"], view["before_title"], view["last_board_date"], view["status"]) == ("Summary after the board", "Summary before the board", "2026-09-10", "ready")
    assert [s["id"] for s in view["sections"]][3] == "discussion"
    # the notes change: out of date, with the reason; a line rebuilt away no longer verifies
    m["notes"][case_id]["lines"][0]["text"] = "Dr Suresh read out the CT thorax report."
    stt = cs.status(store.get_state(case_id), case_id)
    assert stt["status"] == "stale" and stt["stale_reason"] == "The discussion notes of the board changed since this was built"
    m["notes"][case_id]["lines"] = m["notes"][case_id]["lines"][1:]
    assert not cs.verify_said(case_id, c)


def test_without_notes_the_summary_and_its_signature_are_as_before(decided, monkeypatch):
    case_id, _ = decided
    with_notes(case_id, monkeypatch, lines=[])
    calls = fake(monkeypatch, pres=[P_OK])
    v = build(case_id)
    assert [s["id"] for s in v["sections"]] == ["presentation", "stage", "rounds", "since", "status"]
    assert "case summary discussion" not in calls and v["inputs"]["notes"] == []
    assert set(v["signature"]["parts"]) == {"case", "board", "status", "staging"}  # the hash of a Case File without notes is unchanged
    assert cs.view(case_id, store.get_state(case_id))["status"] == "ready"
    # a version built before item 5.4 reads with the title too
    st = store.get_state(case_id)
    old = copy.deepcopy(cs.current(st)); old.pop("title"); old.pop("last_board_date")
    shown = cs.display(case_id, st, old)
    assert shown["title"] == "Summary after the board" and shown["last_board_date"] == "2026-09-10"


def test_the_model_down_for_what_was_said_leaves_the_fixed_sentence(decided, monkeypatch):
    case_id, _ = decided
    with_notes(case_id, monkeypatch)
    fake(monkeypatch, pres=[P_OK], fail=("discussion",))
    v = build(case_id)
    s = section(v, "discussion")["sentences"]
    assert [x["text"] for x in s] == [cs.NOTHING_DISCUSSION] and s[0]["fixed"] and "discussion" in v["model_error"]
    assert "—" not in cs.NOTHING_DISCUSSION
    with pytest.raises(ValueError, match="cannot be edited"):
        cs.edit(case_id, v["n"], s[0]["id"], "Something else.", "dr.rao")


def test_a_sentence_of_what_was_said_is_edited_and_kept_on_a_rebuild(decided, monkeypatch):
    case_id, _ = decided
    with_notes(case_id, monkeypatch)
    fake(monkeypatch, said=SAID_OK)
    v = build(case_id)
    sid = section(v, "discussion")["sentences"][0]["id"]
    s = cs.edit(case_id, v["n"], sid, "At the board of 10/09/2026, Dr Suresh read out that the CT thorax report shows a 3.2 cm mass.", "dr.rao")
    assert s["edited"]["checked"] is True and s["citations"][0]["kind"] == "said"  # the speaker's name and the quote hold every name and number
    s = cs.edit(case_id, v["n"], sid, "Dr Suresh noted a 5 cm mass.", "dr.rao")
    assert s["edited"]["checked"] is False
    v2 = build(case_id)
    first = section(v2, "discussion")["sentences"][0]
    assert first["text"] == "Dr Suresh noted a 5 cm mass." and first["edited"]["carried_from"] == v["n"]
    assert first["edited"]["vaidyx_text"] == SAID_OK[1]["text"] and "suggested" not in first["edited"]  # the same Vaidyx sentence: no new suggestion


def test_notes_built_or_edited_write_the_summary_after_the_board_again(decided, monkeypatch):
    case_id, _ = decided
    got = []
    monkeypatch.setattr(cs, "schedule", lambda cid, trigger, user="": got.append((cid, trigger, user)) or {"scheduled": True, "how": "loop"})
    assert cs.on_notes_changed("M1", case_id, "anil") == {"scheduled": False, "how": "no_board_record"}  # no board record of that meeting
    st = store.get_state(case_id)
    st["board_records"][0]["session"] = "M1"
    store.save_state(case_id, st)
    assert cs.on_notes_changed("M1", case_id, "anil", "notes_line_edited") == {"scheduled": True, "how": "loop"}
    assert got == [(case_id, {"kind": "notes", "meeting": "M1", "why": "notes_line_edited"}, "anil")]
    monkeypatch.setattr(cs, "records", lambda st: 1 / 0)
    assert cs.on_notes_changed("M1", case_id, "anil") == {"scheduled": False, "how": "error"}  # never raises
    monkeypatch.setattr(config, "PROTECTED_CASES", {case_id})
    assert cs.on_notes_changed("M1", case_id, "anil")["how"] == "off" and len(got) == 1
    assert cs.board_notes(case_id, [{"id": "B1", "session": "M1"}]) == []  # a protected Case File has no notes here


def test_the_owner_is_told_a_version_with_the_notes(decided, monkeypatch):
    case_id, rec = decided
    with_notes(case_id, monkeypatch)
    fake(monkeypatch, said=SAID_OK)
    v = asyncio.run(cs.build(case_id, {"kind": "notes", "meeting": "M1"}, "anil"))
    cs._notify_owner(case_id, v, "anil")
    n = [x for x in notify._load() if x["title"].startswith("Summary after the board updated")]
    assert n and n[-1]["text"].startswith(f"Version {v['n']} with the discussion notes of the board of 10/09/2026: AI draft, not reviewed.")
