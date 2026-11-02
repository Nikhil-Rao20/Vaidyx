"""The fill-in summary (18 Oct, new interface): slots built from the protocol and the gate, typed values, not needed, ask the department,
quote highlights and the ready hook. Synthetic Case Files only (the TB-001 fixture); no model is ever called: qa.ask, agents.run_agent and
summary.build are replaced by fakes where a test needs them. The routes run through FastAPI's TestClient with a fake login."""
import asyncio
import copy
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import agents, notify, org, ready_hook, rules, service, slots, store, summary
from tumour_board.tests import util

CASE = "TB-001"
OWNER = "medical_oncology"


class FakeAuth:
    is_configured = True

    def is_admin(self, user):
        return user == "vx.admin"


@pytest.fixture
def people(data_root):
    """A treating doctor of the owning department (dr.rao), a supporting doctor (dr.ravi, Radiology), a treating doctor of another department
    (dr.nair, Breast Surgery), a resident of the owning department (res.asha) and the MDT Coordinator (anil)."""
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"dr.rao": {"departments": {OWNER: "member"}, "display_name": "Dr Rao"},
                  "dr.ravi": {"departments": {"radiology": "member"}, "display_name": "Dr Ravi"},
                  "dr.nair": {"departments": {"breast_surgery": "member"}, "display_name": "Dr Nair"},
                  "res.asha": {"departments": {OWNER: "resident"}, "display_name": "Dr Asha"},
                  "anil": {"coordinator": True, "display_name": "Anil (MDT Coordinator)"}}
    org.save(o, by="test")
    return o


@pytest.fixture
def tb001(demo_cases, people):
    """The synthetic lung Case File owned by Medical Oncology, its gate evaluated (no model: deterministic rules over the stored documents)."""
    c = store.get_case(CASE); c["department"] = OWNER; store.save_case(c)
    service.recheck(CASE, "test")
    return CASE


@pytest.fixture
def nik_app(data_root, monkeypatch):
    """The whole Tumour Board API (old routes plus the new routers) behind a fake login: `who["user"]` is the logged-in user."""
    import routes.tumour_board_routes as R
    monkeypatch.setattr(R, "_warm", lambda: None)  # no guideline warm-up thread in the unit suite
    monkeypatch.setenv("TB_SCHEDULER", "0")
    app = FastAPI()
    who = {"user": "dr.rao"}

    @app.middleware("http")
    async def auth(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    app.include_router(R.setup_tumour_board_routes())
    app.state.auth_manager = FakeAuth()
    with TestClient(app) as tc:
        yield tc, who


def slot_of(view, sid):
    return next((s for s in slots._all_slots(view) if s["id"] == sid), None)


def audit_kinds(case_id):
    return [e.get("kind") for e in store.read_audit(case_id)]


def drop_fact(case_id, doc_type, fid):
    """Remove a verified fact from the fixture's document of that type (the gap the doctor then fills by hand)."""
    for d in store.list_docs(case_id):
        if (d.get("classification") or {}).get("doc_type") == doc_type and fid in (d.get("facts") or {}):
            d["facts"].pop(fid); store.save_doc(case_id, d)
    store._docs_cache.clear()


# ---- the shape ---------------------------------------------------------------------------------------------------------------------

def test_slots_shape_found_not_found_and_pending(nik_app, tb001):
    tc, who = nik_app
    r = tc.get(f"/api/tb/cases/{CASE}/slots")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["listed"] is True and v["protocol"] == "lung_nsclc"
    assert [s["id"] for s in v["sections"]] == ["presenting", "pathology", "imaging", "labs", "staging", "prior_treatment", "question", "other"]
    assert [s["id"] for s in v["sections"][-1]["slots"]] == ["record:bronchoscopy", "record:mediastinal_staging"]  # endoscopy records: other records
    # a verified value: the quote with its document and page
    ecog = slot_of(v, "fact:ecog")
    assert ecog["status"] == "found" and ecog["value"] == "1" and ecog["section"] == "presenting" and ecog["required"] is True
    assert ecog["quote"]["text"] == "ECOG performance status: 1" and ecog["quote"]["page"] == 0 and ecog["quote"]["doc_title"] == "MEDICAL ONCOLOGY OPD NOTE"
    assert ecog["actions"][0]["kind"] == "open_source" and ecog["typable"] is True
    # the board question in its own section
    q = slot_of(v, "fact:clinical_question")
    assert q["status"] == "found" and q["section"] == "question"
    # a draft report: the record line is blank with its actions in place
    hp = slot_of(v, "record:histopathology")
    assert hp["status"] == "not_found" and "DRAFT" in hp["note"] and hp["draft"]["doc_title"] == "HISTOPATHOLOGY REPORT"
    kinds = [a["kind"] for a in hp["actions"]]
    assert kinds == ["ask_department", "not_needed"] and hp["actions"][0]["department"] == "Pathology" and hp["actions"][0]["action_id"]
    ht = slot_of(v, "fact:histologic_type")
    assert ht["status"] == "not_found" and "non-final" in ht["note"] and ht["section"] == "pathology"
    # a pending value: not found, the pending statement quoted
    egfr = slot_of(v, "fact:egfr")
    assert egfr["status"] == "not_found" and egfr["pending"] is True and egfr["quote"]["doc_id"] and "awaited" in egfr["note"]
    assert "enter_value" not in [a["kind"] for a in egfr["actions"]]  # a molecular result is never typed by hand
    # shown-only records are lines too, not counted
    pet = slot_of(v, "record:pet_ct")
    assert pet is not None and pet["required"] is False and pet["status"] == "found"
    # extras: a verified fact the protocol extracts but no record requires
    smoke = slot_of(v, "fact:smoking_history")
    assert smoke["extra"] is True and smoke["status"] == "found" and smoke["required"] is False
    w = slot_of(v, "fact:weight")
    assert w["status"] == "not_found" and w["required"] is False and [a["kind"] for a in w["actions"]] == ["enter_value"]
    # the counter: unmet required lines; the prose waits for the ready mark
    assert v["left_before_board"] == sum(1 for s in slots._all_slots(v) if s["required"] and s["status"] in slots.OPEN) > 0
    # the question in the OPD note is shown, but the board question counts only when the doctor types it (owner, 21 Oct 2026, B3)
    assert [b["slot_id"] for b in v["blockers"]] == ["fact:clinical_question"] and v["ready_allowed"] is False
    assert v["prose"]["status"] == "none" and slot_of(v, "prose:history")["status"] == "pending_ready"
    assert v["permissions"]["enter_value"] and v["permissions"]["not_needed"] and v["permissions"]["ask_department"]
    assert v["gate"]["total"] == 6 and v["gate"]["satisfied"] == 3
    # one line on its own
    assert tc.get(f"/api/tb/cases/{CASE}/slots/ecog").json()["id"] == "fact:ecog"
    assert tc.get(f"/api/tb/cases/{CASE}/slots/nothing").status_code == 404


def test_unlisted_case_has_no_slots(nik_app, people):
    tc, who = nik_app
    c = store.create_case("TB-NEW", dict(util.PATIENT), "", created_by="test"); c["department"] = OWNER; store.save_case(c)
    v = tc.get("/api/tb/cases/TB-NEW/slots").json()
    assert v["listed"] is False and v["sections"] == [] and v["ready_allowed"] is False and "not listed" in v["blockers"][0]["why"]


def test_supporting_doctor_never_sees_the_summary(nik_app, tb001):
    tc, who = nik_app
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}/slots").status_code == 403


# ---- typed values -------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fid,raw,clean", [("ecog", "ECOG 2", "2"), ("ecog", " 0 ", "0"), ("menopausal_status", "Post-menopausal", "postmenopausal"),
                                           ("menopausal_status", "pre", "premenopausal"), ("weight", "72", "72 kg"), ("weight", "72.5 kg", "72.5 kg"),
                                           ("height", "1.62 m", "162 cm"), ("height", "158 cm", "158 cm"), ("clinical_question", "Fitness for surgery?", "Fitness for surgery?")])
def test_validate_value_accepts(fid, raw, clean):
    assert slots.validate_value(fid, raw) == clean


@pytest.mark.parametrize("fid,raw", [("ecog", "7"), ("ecog", "good"), ("ecog", ""), ("menopausal_status", "yes"), ("weight", "900"), ("weight", "heavy"),
                                     ("height", "30"), ("height", "3 m"), ("clinical_question", "ok")])
def test_validate_value_refuses(fid, raw):
    with pytest.raises(ValueError):
        slots.validate_value(fid, raw)


def test_typed_value_settles_the_gap_and_is_audited(nik_app, tb001):
    tc, who = nik_app
    drop_fact(CASE, "clinical_note", "ecog")
    service.recheck(CASE, "test")
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    before = v["left_before_board"]
    assert slot_of(v, "fact:ecog")["status"] == "not_found" and util.req(store.get_state(CASE)["gate"], "clinical_history")["status"] == "missing_field"
    assert "enter_value" in [a["kind"] for a in slot_of(v, "fact:ecog")["actions"]]
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:ecog/value", json={"value": "7"})
    assert r.status_code == 400 and "0 to 4" in r.json()["detail"]["message"]
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:ecog/value", json={"value": "ECOG 2", "note": "examined today"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "entered" and s["value"] == "2" and s["typed_by"] == "dr.rao" and s["typed_by_name"] == "Dr Rao"
    assert s["note"].startswith("entered by Dr Rao, no report") and s["quote"] is None
    assert s["left_before_board"] == before - 1
    assert store.get_case(CASE)["typed_values"]["ecog"]["value"] == "2"
    # the gate: the record is satisfied through the overlay, the evidence names the doctor and carries no quote
    row = util.req(store.get_state(CASE)["gate"], "clinical_history")
    assert row["status"] == "satisfied"
    ev = next(e for e in row["evidence"] if e.get("fact") == "ecog")
    assert ev["verification"] == rules.ENTERED and ev["entered_by"] == "dr.rao" and ev["quote"] == "" and ev["doc_id"] == ""
    # never a verified fact for the summary or the briefs
    cur = rules.resolve_facts(rules.case_docs(CASE)).get("ecog")
    assert cur is None
    ev2 = [e for e in store.read_audit(CASE) if e.get("kind") == "typed_value"]
    assert ev2 and ev2[-1]["fact"] == "ecog" and ev2[-1]["value"] == "2" and ev2[-1]["by"] == "dr.rao"
    assert store.verify_audit(CASE)["ok"]
    # removing it reopens the gap
    r = tc.delete(f"/api/tb/cases/{CASE}/slots/fact:ecog/value")
    assert r.status_code == 200 and r.json()["status"] == "not_found" and r.json()["left_before_board"] == before
    assert util.req(store.get_state(CASE)["gate"], "clinical_history")["status"] == "missing_field"
    assert tc.delete(f"/api/tb/cases/{CASE}/slots/fact:ecog/value").status_code == 404


def test_a_verified_value_always_wins_over_a_typed_one(nik_app, tb001):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:ecog/value", json={"value": "3"})
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "found" and s["value"] == "1" and s["quote"]["text"] == "ECOG performance status: 1" and s["typed"]["value"] == "3"
    row = util.req(store.get_state(CASE)["gate"], "clinical_history")
    assert next(e for e in row["evidence"] if e.get("fact") == "ecog")["quote"] == "ECOG performance status: 1"


def test_only_the_fixed_list_is_typed_and_only_by_the_owner(nik_app, tb001):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:histologic_type/value", json={"value": "Adenocarcinoma"})
    assert r.status_code == 409 and "signed report" in r.json()["detail"]["message"]
    assert tc.post(f"/api/tb/cases/{CASE}/slots/record:histopathology/value", json={"value": "x"}).status_code == 409
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:weight/value", json={"value": "80 kg"})
    assert r.status_code == 200 and r.json()["status"] == "entered" and r.json()["value"] == "80 kg"
    # a treating doctor of another department that takes part reads the Case File but types nothing on it
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    assert tc.get(f"/api/tb/cases/{CASE}/slots").status_code == 200
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:height/value", json={"value": "170"})
    assert r.status_code == 403 and "Medical Oncology" in r.json()["detail"]
    who["user"] = "dr.ravi"
    assert tc.post(f"/api/tb/cases/{CASE}/slots/fact:height/value", json={"value": "170"}).status_code == 403


# ---- not needed and ask the department ------------------------------------------------------------------------------------------------

def test_not_needed_waives_the_record(nik_app, tb001):
    tc, who = nik_app
    assert tc.post(f"/api/tb/cases/{CASE}/slots/record:driver_mutations/not-needed", json={"reason": ""}).status_code == 400
    r = tc.post(f"/api/tb/cases/{CASE}/slots/record:driver_mutations/not-needed", json={"reason": "Tissue exhausted; the board decides without it"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "not_needed" and s["waived_record"] == "driver_mutations" and s["confirmation"]["type"] == "waive"
    assert s["waiver"]["by"] == "dr.rao" and "Tissue exhausted" in s["note"] and s["actions"] == []
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    assert slot_of(v, "fact:egfr")["status"] == "not_needed" and slot_of(v, "fact:egfr")["required"] is False
    assert util.req(store.get_state(CASE)["gate"], "driver_mutations")["status"] == "waived"
    a = next(x for x in store.get_state(CASE)["actions"] if x["requirement"] == "driver_mutations")
    assert a["status"] == "completed"  # the suggested request closed with the waiver
    assert "confirmation" in audit_kinds(CASE)


def test_not_needed_on_a_value_line(nik_app, tb001):
    tc, who = nik_app
    # WBC is the only open value of the CBC record: the record is waived with the value named in the reason
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:wbc/not-needed", json={"reason": "differential not required"})
    assert r.status_code == 200, r.text
    assert r.json()["waived_record"] == "cbc" and r.json()["status"] == "not_needed"
    w = store.get_state(CASE)["overrides"]["requirements"]["cbc"]
    assert w["reason"].startswith("WBC count: differential not required")
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    hb = slot_of(v, "fact:haemoglobin")
    assert hb["status"] == "found" and hb["required"] is False  # a documented value stays shown
    # EGFR shares its record with ALK and ROS1, still open: the record is waived from its own row
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:egfr/not-needed", json={"reason": "not needed"})
    assert r.status_code == 409 and "ALK" in r.json()["detail"]["message"]
    # a value no record requires
    assert tc.post(f"/api/tb/cases/{CASE}/slots/fact:smoking_history/not-needed", json={"reason": "x"}).status_code == 409
    # the owner rule: a participating treating doctor may not waive
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    assert tc.post(f"/api/tb/cases/{CASE}/slots/record:histopathology/not-needed", json={"reason": "x"}).status_code == 403


def test_ask_department_sends_the_suggested_request(nik_app, tb001):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/slots/record:histopathology/ask-department", json={})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["request"]["department"] == "Pathology" and out["request"]["sent_at"] and out["request"]["due"] and out["request"]["status"] == "pending"
    assert out["slot"]["status"] == "waiting" and out["slot"]["request"]["action_id"] == out["request"]["action_id"]
    assert [a["kind"] for a in out["slot"]["actions"]] == ["remind", "not_needed"]
    assert "Required record: Histopathology report" in out["action"]["sent"]["message"] and out["action"]["sent"]["message"].rstrip().endswith("through the Tumour Board.")
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    assert slot_of(v, "fact:histologic_type")["status"] == "waiting" and slot_of(v, "fact:histologic_type")["request"]["department"] == "Pathology"
    recs = [json.loads(l) for l in notify.path().read_text().splitlines() if l.strip()]
    assert any(n["kind"] == "request" and n["to"] == {"department": "pathology"} and n["case_id"] == CASE for n in recs)
    assert "request_sent" in audit_kinds(CASE)
    # sending again is a reminder (the existing rule), a met record has nothing to ask
    assert tc.post(f"/api/tb/cases/{CASE}/slots/record:histopathology/ask-department", json={"message": "Please sign it today"}).json()["action"]["sent"]["count"] == 2
    r = tc.post(f"/api/tb/cases/{CASE}/slots/record:cect_tap/ask-department", json={})
    assert r.status_code == 409 and "Nothing to ask" in r.json()["detail"]["message"]
    assert tc.post(f"/api/tb/cases/{CASE}/slots/fact:smoking_history/ask-department", json={}).status_code == 409
    who["user"] = "anil"  # the coordinator reads every Case File but sends no request
    assert tc.post(f"/api/tb/cases/{CASE}/slots/record:driver_mutations/ask-department", json={}).status_code == 403


# ---- the prose block ----------------------------------------------------------------------------------------------------------------

def test_prose_none_pending_ready_stale(nik_app, tb001):
    tc, who = nik_app
    assert tc.get(f"/api/tb/cases/{CASE}/slots").json()["prose"]["status"] == "none"
    c = store.get_case(CASE); c["board_ready"] = {"by": "dr.rao", "at": store.now_iso(), "note": ""}; store.save_case(c)
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    assert v["prose"]["status"] == "pending" and slot_of(v, "prose:history")["status"] == "pending_ready"
    st = store.get_state(CASE)
    st["artefacts"]["summary"] = {"status": "ready", "sections": [{"id": "presentation", "title": "Presenting complaints and examination",
                                                                   "sentences": [{"text": "Haemoptysis for 6 weeks.", "citations": [{"doc_id": "Dbae880db", "quote": "Haemoptysis for 6 weeks", "page": 0}]}]}],
                                  "points_for_review": [], "review": {"status": "ai_draft"}, "generated": store.now_iso(), "model": "Gemma-4-31B",
                                  "signature": rules.case_signature(CASE, st)}
    store.save_state(CASE, st)
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    assert v["prose"]["status"] == "ready" and v["prose"]["reviewed"] is False and v["prose"]["label"] == "AI draft, not reviewed"
    assert v["prose"]["paragraphs"][0]["sentences"][0]["citations"][0]["doc_id"] == "Dbae880db" and slot_of(v, "prose:history") is None
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")  # the records changed since
    v = tc.get(f"/api/tb/cases/{CASE}/slots").json()
    assert v["prose"]["status"] == "stale" and "document" in v["prose"]["stale_reason"]


# ---- quote highlights ---------------------------------------------------------------------------------------------------------------

def test_quote_endpoint_text_layer_and_scanned_pages(nik_app, tb001):
    tc, who = nik_app
    note = next(d for d in store.list_docs(CASE) if (d.get("classification") or {}).get("doc_type") == "clinical_note")
    r = tc.get(f"/api/tb/cases/{CASE}/documents/{note['doc_id']}/quote", params={"fact": "ecog"})
    assert r.status_code == 200 and r.json()["found"] is True and r.json()["page"] == 0 and r.json()["boxes"] == [] and r.json()["method"] == "text-layer"
    r = tc.get(f"/api/tb/cases/{CASE}/documents/{note['doc_id']}/quote", params={"text": "ECOG performance status: 1"})
    assert r.json()["found"] is True and r.json()["start"] is not None and r.json()["how"] == "exact"
    r = tc.get(f"/api/tb/cases/{CASE}/documents/{note['doc_id']}/quote", params={"text": "this sentence is nowhere in the file"})
    assert r.status_code == 200 and r.json()["found"] is False and r.json()["boxes"] == []
    assert tc.get(f"/api/tb/cases/{CASE}/documents/{note['doc_id']}/quote", params={"fact": "her2"}).json()["found"] is False
    assert tc.get(f"/api/tb/cases/{CASE}/documents/{note['doc_id']}/quote").json()["found"] is False
    assert tc.get(f"/api/tb/cases/{CASE}/documents/Dnothing/quote", params={"fact": "ecog"}).status_code == 404
    # a scanned page with engine word boxes: rectangles come back as fractions of the page
    from tumour_board.tests.test_ocr_boxes import layout
    text = "Haemoglobin 11.2 g/dL\nPlatelets 2,45,000 /cumm"
    words = layout([["Haemoglobin", "11.2", "g/dL"], ["Platelets", "2,45,000", "/cumm"]])
    d = util.make_doc("Dscan0001", "lab", text=text, facts={"haemoglobin": util.fact("11.2 g/dL", quote="Haemoglobin 11.2 g/dL")})
    d["pages"][0]["method"] = "vision-transcription"; d["pages"][0]["ocr_engine"] = {"words": words}
    util.add(CASE, d)
    r = tc.get(f"/api/tb/cases/{CASE}/documents/Dscan0001/quote", params={"fact": "haemoglobin"})
    out = r.json()
    assert out["found"] is True and out["page"] == 0 and out["method"] == "vision-transcription" and len(out["boxes"]) == 1
    x0, y0, x1, y1 = out["boxes"][0]
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    out = tc.get(f"/api/tb/cases/{CASE}/documents/Dscan0001/quote", params={"text": "Platelets 2,45,000"}).json()
    assert out["found"] and out["boxes"] and out["boxes"][0][1] > y0  # the second line sits lower on the page


# ---- the ready hook -----------------------------------------------------------------------------------------------------------------

def test_ready_route_calls_the_hook_only_for_a_ready_mark(nik_app, tb001, monkeypatch):
    tc, who = nik_app
    calls = []
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: calls.append((case_id, user)) or {"scheduled": True})
    c = store.get_case(CASE); c["board_question"] = "Is the patient fit for surgery? (synthetic)"; store.save_case(c)  # the send needs the question (1.4)
    send = {"ready": True, "note": "question typed", "reason": "the board should see it now (synthetic)"}  # and, with items open, a reason
    r = tc.post(f"/api/tb/cases/{CASE}/ready", json=send)
    assert r.status_code == 200 and r.json()["board_ready"]["by"] == "dr.rao" and calls == [(CASE, "dr.rao")]
    assert tc.post(f"/api/tb/cases/{CASE}/ready", json={"ready": False}).status_code == 200 and len(calls) == 1
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: 1 / 0)  # a failing hook never fails the mark
    assert tc.post(f"/api/tb/cases/{CASE}/ready", json=send).status_code == 200


def test_ready_hook_schedules_nothing_when_off(tb001, monkeypatch):
    monkeypatch.setenv("TB_SCHEDULER", "0")
    assert ready_hook.on_ready(CASE, "dr.rao") == {"scheduled": False, "how": "off", "reason": "TB_SCHEDULER=0"}
    assert not ready_hook.TASKS and not ready_hook.running(CASE)
    monkeypatch.setenv("TB_SCHEDULER", "1")
    assert ready_hook.on_ready("TB-2026-bharath", "dr.rao")["reason"] == "protected Case File"


def test_ready_hook_prepares_summary_and_five_briefs_after_the_meeting(tb001, monkeypatch):
    calls = []

    async def fake_build(case_id, force=False):
        calls.append(("summary", force))
        st = store.get_state(case_id)
        st["artefacts"]["summary"] = {"status": "incomplete_gate", "sections": [], "points_for_review": [], "review": {"status": "ai_draft"},
                                      "generated": store.now_iso(), "signature": rules.case_signature(case_id, st)}
        store.save_state(case_id, st)
        return st["artefacts"]["summary"]

    async def fake_run(case_id, role, focus_question="", max_steps=5):
        calls.append((role, focus_question))
        st = store.get_state(case_id)
        b = {"role": role, "sections": [], "points_for_review": [], "not_documented": [], "generated": store.now_iso(), "review": {"status": "ai_draft"},
             "signature": rules.case_signature(case_id, st), "version": agents.BRIEF_VERSION, "focus": "", "near_match": False}
        st["artefacts"][f"brief_{role}"] = b; store.save_state(case_id, st)
        yield {"type": "start", "role": role}
        yield {"type": "brief", "brief": b}
    monkeypatch.setattr(summary, "build", fake_build)
    monkeypatch.setattr(agents, "run_agent", fake_run)
    monkeypatch.setattr(ready_hook, "MEETING_DELAY", 0.01)
    meeting = iter([True, True, False])
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: next(meeting, False))
    out = asyncio.run(ready_hook.run(CASE, "dr.rao"))
    assert out["waited"] == 2 and out["done"] == ["summary", "radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology"]
    assert out["failed"] == [] and out["notified"] is True
    assert calls[0] == ("summary", True) and [c[0] for c in calls[1:]] == list(ready_hook.HEADS)  # one after the other, no Nuclear Medicine
    recs = [json.loads(l) for l in notify.path().read_text().splitlines() if l.strip()]
    n = [x for x in recs if x["case_id"] == CASE and x["kind"] in ("summary_ready", "owner_reminder")]
    assert n and n[-1]["to"] == {"department": OWNER} and "prepared" in n[-1]["title"]
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "ready_hook"]
    assert ev[-1]["step"] == "finished" and ev[-1]["done"] == out["done"]
    # everything is fresh now: a second run touches nothing
    out2 = asyncio.run(ready_hook.run(CASE, "dr.rao"))
    assert out2["done"] == [] and out2["skipped"] == ["summary", *ready_hook.HEADS] and len(calls) == 6
    # the hook is scheduled on a running loop and on a thread alike
    monkeypatch.setenv("TB_SCHEDULER", "1")

    async def on_loop():
        r = ready_hook.on_ready(CASE, "dr.rao")
        await asyncio.gather(*ready_hook.TASKS)
        return r
    assert asyncio.run(on_loop())["how"] == "loop"
    r = ready_hook.on_ready(CASE, "dr.rao")
    assert r["how"] == "thread"
    for _ in range(100):
        if not ready_hook.running(CASE):
            break
        time.sleep(0.02)
    assert not ready_hook.running(CASE)


def test_ready_hook_a_failing_step_never_stops_the_next(tb001, monkeypatch):
    async def bad_build(case_id, force=False):
        raise RuntimeError("model down")

    async def fake_run(case_id, role, focus_question="", max_steps=5):
        if role == "pathology":
            yield {"type": "error", "message": "no brief"}
            return
        st = store.get_state(case_id)
        b = {"role": role, "sections": [], "points_for_review": [], "generated": store.now_iso(), "signature": rules.case_signature(case_id, st),
             "version": agents.BRIEF_VERSION, "focus": "", "near_match": False}
        st["artefacts"][f"brief_{role}"] = b; store.save_state(case_id, st)
        yield {"type": "brief", "brief": b}
    monkeypatch.setattr(summary, "build", bad_build)
    monkeypatch.setattr(agents, "run_agent", fake_run)
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)
    monkeypatch.setattr(ready_hook, "RUNNING", {})  # a run scheduled by an earlier test may still hold the case in its own thread
    out = asyncio.run(ready_hook.run(CASE, "dr.rao"))
    assert out["failed"] == ["summary", "pathology"] and out["done"] == ["radiology", "medical_oncology", "surgical_oncology", "radiation_oncology"]
    steps = [e["step"] for e in store.read_audit(CASE) if e.get("kind") == "ready_hook"]
    assert "summary_failed" in steps and "pathology_failed" in steps and steps[-1] == "finished"
