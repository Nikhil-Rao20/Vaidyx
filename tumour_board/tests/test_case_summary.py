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


def fake(monkeypatch, pres=(), since=(), fail=()):
    """llm.chat replaced: the Case summary calls answer with the given sentences; the adjudication calls find no claims."""
    calls = []

    async def chat(role, msgs, **kw):
        p = kw.get("purpose") or ""
        calls.append(p)
        if p.startswith("case summary"):
            sec = p.split()[-1]
            if sec in fail:
                raise llm.LLMError("the model server is down")
            return {"sentences": copy.deepcopy(list(pres if sec == "presentation" else since))}
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
    assert by[f"r{rec['id']}-decision_text"]["text"] == 'Decision as recorded: "Upfront surgery, then adjuvant chemotherapy.".'
    c = by[f"r{rec['id']}-decision_text"]["citations"][0]
    assert c == {"kind": "board", "board_record": rec["id"], "version": 1, "field": "decision_text", "quote": DECISION["decision_text"], "board_date": "2026-09-10"}
    assert by[f"r{rec['id']}-intent"]["text"] == "Treatment intent as recorded: Curative."
    assert by[f"r{rec['id']}-concerns-1"]["text"] == 'Dr Dev recorded a view: "Cardiac fitness first".'
    assert by[f"r{rec['id']}-question"]["citations"][0]["doc_id"] == "Da0000002"
    actions = [s for s in block["sentences"] if s["id"].startswith(f"r{rec['id']}-action-")]
    assert any(s["text"] == 'Action raised: "CT brain" for Radiology, due 20/09/2026.' for s in actions)
    status = texts(v, "status")
    assert 'Open: "CT brain", Radiology, due 20/09/2026.' in status
    assert any(t.startswith("Not yet recorded: Patient not yet recorded as informed") for t in status)
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
    assert b1["decision_text"]["text"] == 'Decision as recorded: "Upfront lobectomy, then adjuvant chemotherapy.".'
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
    assert s["text"].endswith('...".') and len(s["text"]) < 650 and s["citations"][0]["quote"] == " ".join(long.split())


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
    n = [x for x in notify._load() if x["title"].startswith("Case summary updated")]
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
                                                 "status": {"status": "none", "version": None, "built_at": None, "stale_reason": ""}}
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


def test_get_refreshes_overdue_after_a_day(decided, monkeypatch, app):
    case_id, _ = decided
    tc, who = app
    fake(monkeypatch)
    build(case_id)
    monkeypatch.setattr(followup, "_today", lambda: date(2026, 9, 25))
    j = tc.get(f"/api/tb/cases/{case_id}/case-summary").json()
    assert 'Open: "CT brain", Radiology, due 20/09/2026, overdue.' in texts(j["version"], "status") and j["version"]["refreshed_at"]
    assert len(j["versions"]) == 1
