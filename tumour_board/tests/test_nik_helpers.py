"""Specialty helpers (18 Oct): six cards, the brief prepared in the background by the role's agent (agents.run_agent replaced by a fake:
no model), its status from the stored artefact and the Case File signature, and the chat per role (agents.ask replaced by a fake)."""
import time

import pytest

from tumour_board import agents, helpers, rules, store
from tumour_board.tests.test_nik_slots import CASE, OWNER, audit_kinds, nik_app, people, tb001  # noqa: F401 (fixtures)

LABELS = ["Radiology records check", "Pathology records check", "Medical Oncology records check", "Surgical Oncology records check",
          "Radiation Oncology records check", "Nuclear Medicine records check"]


@pytest.fixture
def fake_agents(monkeypatch):
    runs, asks = [], []

    async def run_agent(case_id, role, focus_question="", max_steps=5):
        runs.append((case_id, role, focus_question))
        st = store.get_state(case_id)
        b = {"role": role, "label": agents.ROLES[role]["label"], "sections": [{"heading": "Imaging", "items": [{"text": "CT: 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D41f9d46c", "quote": "5.2 x 4.1 cm"}]}]}],
             "points_for_review": [{"text": "Is the PET/CT stage line the one to quote?", "citations": [{"doc_id": "D4edcec61", "quote": "Stage IIIB"}], "references": []}],
             "not_documented": [], "removed": [], "dropped_unverified": 0, "generated": store.now_iso(), "model": "Gemma-4-31B", "review": {"status": "ai_draft"},
             "signature": rules.case_signature(case_id, st), "version": agents.BRIEF_VERSION, "focus": "", "near_match": False, "seconds": 0.1}
        st.setdefault("artefacts", {})[f"brief_{role}"] = b
        store.save_state(case_id, st)
        yield {"type": "start", "role": role, "label": b["label"]}
        yield {"type": "step", "tool": "finish", "input": "", "thought": "done"}
        yield {"type": "brief", "brief": b}

    async def ask(case_id, role, question, history=None, user=""):
        asks.append((case_id, role, question, history, user))
        return {"role": role, "label": agents.ROLES[role]["label"], "kind": agents.LIVE_LABEL, "question": question, "status": "answered",
                "statements": [{"text": "The CECT reports a 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D41f9d46c", "quote": "measuring 5.2 x 4.1 cm", "page": 0, "doc_title": "CECT THORAX REPORT"}]}],
                "references": [{"org": "ICRI / IRIA onco-imaging checklists, India", "title": "Lung checklist", "page": 2, "region": "India", "quote": "report the size", "file": "iria/x.pdf", "page_kind": "page", "page_end": 2, "by": "agent"}],
                "removed": [], "dropped_unverified": 0, "references_dropped": 0, "mode": "full", "answered_at": store.now_iso(), "message": "", "seconds": 2.0, "model": "Gemma-4-31B"}
    monkeypatch.setattr(agents, "run_agent", run_agent)
    monkeypatch.setattr(agents, "ask", ask)
    return runs, asks


def _poll(tc, job_id, tries=100):
    for _ in range(tries):
        j = tc.get(f"/api/tb/jobs/{job_id}").json()
        if j["state"] in ("finished", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_list_six_helpers(nik_app, tb001):
    tc, who = nik_app
    r = tc.get(f"/api/tb/cases/{CASE}/helpers")
    assert r.status_code == 200, r.text
    hs = r.json()["helpers"]
    assert [h["label"] for h in hs] == LABELS and [h["role"] for h in hs] == list(helpers.ROLES)
    assert all(h["brief"]["status"] == "none" and h["thread_count"] == 0 and h["prepare_allowed"] for h in hs)
    assert [h["role"] for h in hs if h["head"]] == list(helpers.HEADS) and r.json()["heads"] == list(helpers.HEADS)
    who["user"] = "anil"
    assert all(h["prepare_allowed"] for h in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"])
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}/helpers").status_code == 403


def test_prepare_runs_in_the_background_and_is_reused_until_stale(nik_app, tb001, fake_agents):
    tc, who = nik_app
    runs, _ = fake_agents
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/cardiology/prepare").status_code == 404
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "preparing" and out["reused"] is False and out["job"].startswith("J")
    j = _poll(tc, out["job"])
    assert j["state"] == "finished" and j["kind"] == "helper_brief" and j["role"] == "radiology" and j["brief"]["sections"] == 1 and j["by"] == "dr.rao"
    assert runs == [(CASE, "radiology", "")]
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["status"] == "ready" and h["brief"]["label"] == "AI draft, not reviewed" and h["brief"]["points_for_review"][0]["text"].startswith("Is the PET/CT")
    assert h["brief"]["sections"][0]["items"][0]["citations"][0]["doc_id"] == "D41f9d46c"
    assert "helper_prepare" in audit_kinds(CASE)
    # fresh: reused without a second run; refresh runs again
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare").json()
    assert r["status"] == "ready" and r["reused"] is True and len(runs) == 1 and _poll(tc, r["job"])["reused"] is True
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare", json={"refresh": True}).json()
    assert r["status"] == "preparing" and _poll(tc, r["job"])["state"] == "finished" and len(runs) == 2
    # the records change: stale, and the next prepare runs
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["status"] == "stale" and "document" in h["brief"]["stale_reason"]
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare").json()
    assert r["status"] == "preparing" and _poll(tc, r["job"])["state"] == "finished" and len(runs) == 3
    # a reviewed brief says who reviewed it
    st = store.get_state(CASE); st["artefacts"]["brief_radiology"]["review"] = {"status": "reviewed", "by": "dr.rao"}; store.save_state(CASE, st)
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["reviewed_by"] == "dr.rao" and h["brief"]["label"] == "Reviewed"
    assert h["brief"]["reviewed_by_name"] == "Dr Rao"  # a display name beside the login (review 9 C, M11)
    assert "reviewed_by_name" not in helpers.brief_view({"review": {"status": "ai_draft"}, "signature": None}, rules.case_signature(CASE))


def test_prepare_is_for_the_owner_team_and_the_coordinator(nik_app, tb001, fake_agents):
    tc, who = nik_app
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    hs = tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"]
    assert all(not h["prepare_allowed"] for h in hs)
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").status_code == 403
    who["user"] = "res.asha"
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").status_code == 200
    who["user"] = "anil"
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/nuclear_medicine/prepare")
    assert r.status_code == 200 and _poll(tc, r.json()["job"])["state"] == "finished"
    # an unlisted Case File has no brief to prepare
    c2 = store.create_case("TB-NEW", {"name": "SYNTHETIC, Someone", "mrn": "SYN-1", "agesex": "50 Y / F"}, "", created_by="test"); c2["department"] = OWNER; store.save_case(c2)
    who["user"] = "dr.rao"
    assert tc.post("/api/tb/cases/TB-NEW/helpers/radiology/prepare").status_code == 409


def test_prepare_failure_reaches_the_job(nik_app, tb001, monkeypatch):
    tc, who = nik_app

    async def bad(case_id, role, focus_question="", max_steps=5):
        yield {"type": "error", "message": "unknown role"}
    monkeypatch.setattr(agents, "run_agent", bad)
    j = _poll(tc, tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").json()["job"])
    assert j["state"] == "failed" and j["error"] == "unknown role"
    assert next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "pathology")["brief"]["status"] == "none"
    assert not helpers.PREPARING


def test_helper_chat_per_role(nik_app, tb001, fake_agents):
    tc, who = nik_app
    _, asks = fake_agents
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json() == {"messages": [], "role": "radiology", "label": "Radiology records check"}
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": " "}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/cardiology/chat", json={"question": "x?"}).status_code == 404
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "What size is the mass?"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["id"].startswith("H") and m["role"] == "radiology" and m["by"] == "dr.rao" and m["by_name"] == "Dr Rao" and m["status"] == "answered"
    assert m["statements"][0]["citations"][0]["doc_title"] == "CECT THORAX REPORT" and m["references"][0]["region"] == "India" and m["stale"] is False
    assert m["kind"] == agents.LIVE_LABEL
    assert asks == [(CASE, "radiology", "What size is the mass?", [], "dr.rao")]
    tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "And the nodes?"})
    assert asks[-1][3] == [{"role": "user", "content": "What size is the mass?"}, {"role": "assistant", "content": "The CECT reports a 5.2 x 4.1 cm mass."}]
    v = tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()
    assert [x["question"] for x in v["messages"]] == ["What size is the mass?", "And the nodes?"]
    assert next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")["thread_count"] == 2
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/pathology/chat").json()["messages"] == []
    assert store._read_json(store.case_dir(CASE) / "helper_chats.json")["radiology"][0]["signature"]
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "helper_asked"]
    assert ev[-1]["role"] == "radiology" and ev[-1]["by"] == "dr.rao" and store.verify_audit(CASE)["ok"]
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")
    assert all(x["stale"] for x in tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"])
    who["user"] = "anil"  # the coordinator reads the shared thread
    assert len(tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"]) == 2
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").status_code == 403


# ---- night-v3 item 6.3: one thread per Case File and role, shared by the Case File page and every meeting ------------------------------
MEETING_ANSWER = {"by": "dr.rao", "question": "What size is the mass?", "status": "answered", "model": "Gemma-4-31B", "meeting_date": "2026-10-27",
                  "statements": [{"text": "The CECT reports a 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D41f9d46c", "quote": "measuring 5.2 x 4.1 cm"}]}]}


def test_record_exchange_from_a_meeting_is_on_the_case_file_thread(nik_app, tb001, fake_agents):
    tc, who = nik_app
    _, asks = fake_agents
    m = helpers.record_exchange(CASE, "radiology", MEETING_ANSWER, source="meeting:S20261027-ab12")
    assert m["id"].startswith("H") and m["source"] == "meeting:S20261027-ab12" and m["by_name"] == "Dr Rao" and m["role"] == "radiology"
    assert m["signature"] == rules.case_signature(CASE)["hash"] and m["at"]
    for bad in ("elsewhere", "meeting:"):
        with pytest.raises(ValueError):
            helpers.record_exchange(CASE, "radiology", MEETING_ANSWER, source=bad)
    with pytest.raises(KeyError):
        helpers.record_exchange(CASE, "cardiology", MEETING_ANSWER)
    rows = tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"]
    assert len(rows) == 1 and rows[0]["source"] == "meeting:S20261027-ab12" and rows[0]["meeting_date"] == "2026-10-27"
    assert rows[0]["model"] == "Gemma-4-31B" and rows[0]["kind"] == "AI agent, support only" and rows[0]["stale"] is False
    # the Case File page asks on the same thread, with the meeting's exchange as history, and is saved with source "case"
    tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "And the nodes?"})
    assert asks[-1][3] == [{"role": "user", "content": "What size is the mass?"}, {"role": "assistant", "content": "The CECT reports a 5.2 x 4.1 cm mass."}]
    rows = tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"]
    assert [r["source"] for r in rows] == ["meeting:S20261027-ab12", "case"] and rows[1]["meeting_date"] is None and rows[1]["model"] == "Gemma-4-31B"
    assert helpers.record_exchange(CASE, "pathology", {"question": "x?"})["source"] == "case"  # the default


def test_history_for_drops_the_answer_of_a_changed_record(nik_app, tb001):
    helpers.record_exchange(CASE, "radiology", MEETING_ANSWER, source="meeting:S20261027-ab12")
    helpers.record_exchange(CASE, "radiology", {"question": "Is the PD-L1 recorded?", "status": "not_documented", "statements": [], "message": "Not documented."})
    h = helpers.history_for(CASE, "radiology")
    assert h == [{"role": "user", "content": "What size is the mass?"}, {"role": "assistant", "content": "The CECT reports a 5.2 x 4.1 cm mass."},
                 {"role": "user", "content": "Is the PD-L1 recorded?"}, {"role": "assistant", "content": "Not documented."}]
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")  # the records change: the old answers are not passed on
    h = helpers.history_for(CASE, "radiology")
    assert [x["content"] for x in h if x["role"] == "user"] == ["What size is the mass?", "Is the PD-L1 recorded?"]
    assert all(x["content"] == helpers.RECORDS_CHANGED for x in h if x["role"] == "assistant")
    helpers.record_exchange(CASE, "radiology", {"question": "And now?", "statements": [{"text": "The new report is filed.", "citations": []}]})
    assert helpers.history_for(CASE, "radiology", 2) == [{"role": "user", "content": "Is the PD-L1 recorded?"}, {"role": "assistant", "content": helpers.RECORDS_CHANGED},
                                                         {"role": "user", "content": "And now?"}, {"role": "assistant", "content": "The new report is filed."}]
    assert len(helpers.history_for(CASE, "radiology")) == 6 and helpers.history_for(CASE, "radiology", 0) == []
    assert helpers.history_for(CASE, "pathology") == []


def test_record_exchange_keeps_the_last_messages(nik_app, tb001, monkeypatch):
    monkeypatch.setattr(helpers, "MAX_MESSAGES", 3)
    for i in range(5):
        helpers.record_exchange(CASE, "radiology", {"question": f"Q{i}?"})
    assert [m["question"] for m in helpers.load_chats(CASE)["radiology"]] == ["Q2?", "Q3?", "Q4?"]


# ---- night-v3 item 6.5: the "Specialty agents" on the Case File (title, counts, meeting exchanges, Prepare all) --------------------------
@pytest.fixture
def fresh_limit():
    """The preparation limit is per process: the earlier tests of this file used it up."""
    from tumour_board.api import helpers as helper_routes
    helper_routes.PREPARE_LIMIT._hits.clear()
    yield
    helper_routes.PREPARE_LIMIT._hits.clear()


def test_list_has_the_agent_title_and_the_counts(nik_app, tb001, fake_agents, fresh_limit):
    tc, who = nik_app
    hs = tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"]
    assert [h["title"] for h in hs] == ["Radiology, AI agent", "Pathology, AI agent", "Medical Oncology, AI agent", "Surgical Oncology, AI agent",
                                        "Radiation Oncology, AI agent", "Nuclear Medicine, AI agent"]
    assert [h["label"] for h in hs] == LABELS  # the existing keys stay
    assert all(h["points_count"] == 0 and h["not_documented_count"] == 0 and h["meeting_exchanges"] == 0 and h["prepared_at"] is None for h in hs)
    _poll(tc, tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare").json()["job"])
    st = store.get_state(CASE); st["artefacts"]["brief_radiology"]["not_documented"] = ["PET-CT report", "Bone scan"]; store.save_state(CASE, st)
    helpers.record_exchange(CASE, "radiology", MEETING_ANSWER, source="meeting:S20261027-ab12")
    tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "And the nodes?"})
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["points_count"] == 1 and h["not_documented_count"] == 2 and h["thread_count"] == 2 and h["meeting_exchanges"] == 1
    assert h["prepared_at"] == h["brief"]["at"] and h["prepared_at"]
    # a stale brief keeps its counts and its time; a brief being prepared has none
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["status"] == "stale" and h["points_count"] == 1 and h["prepared_at"]
    helpers.PREPARING[(CASE, "radiology")] = "Jbusy"
    try:
        h = next(x for x in helpers.list_helpers(CASE, {"admin": True}) if x["role"] == "radiology")
        assert h["brief"]["status"] == "preparing" and h["points_count"] == 0 and h["prepared_at"] is None and h["job"] == "Jbusy"
    finally:
        helpers.PREPARING.pop((CASE, "radiology"), None)


def test_prepare_all_runs_one_after_the_other_and_skips_fresh_briefs(nik_app, tb001, fake_agents, fresh_limit):
    tc, who = nik_app
    runs, _ = fake_agents
    _poll(tc, tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").json()["job"])
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/prepare-all")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["started"] == 5 and [x["role"] for x in out["helpers"]] == list(helpers.ROLES)
    by = {x["role"]: x for x in out["helpers"]}
    assert by["pathology"] == {"role": "pathology", "status": "ready", "job": None}
    assert all(by[r]["status"] == "preparing" and by[r]["job"].startswith("J") for r in helpers.ROLES if r != "pathology")
    for role in helpers.ROLES:
        if role != "pathology":
            assert _poll(tc, by[role]["job"])["state"] == "finished"
    assert [x[1] for x in runs] == ["pathology", "radiology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"]
    hs = tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"]
    assert all(h["brief"]["status"] == "ready" and h["points_count"] == 1 for h in hs) and not helpers.PREPARING
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "helper_prepare" and e.get("all")]
    assert len(ev) == 5 and all(e["by"] == "dr.rao" for e in ev) and store.verify_audit(CASE)["ok"]
    # everything stands: nothing is started again
    again = tc.post(f"/api/tb/cases/{CASE}/helpers/prepare-all").json()
    assert again["started"] == 0 and all(x["status"] == "ready" for x in again["helpers"]) and len(runs) == 6


def test_prepare_all_leaves_a_running_preparation_and_follows_the_permission(nik_app, tb001, fake_agents, fresh_limit):
    tc, who = nik_app
    runs, _ = fake_agents
    helpers.PREPARING[(CASE, "radiology")] = "Jbusy"
    try:
        out = tc.post(f"/api/tb/cases/{CASE}/helpers/prepare-all").json()
        assert out["helpers"][0] == {"role": "radiology", "status": "preparing", "job": "Jbusy"} and out["started"] == 5
        for x in out["helpers"][1:]:
            _poll(tc, x["job"])
        assert "radiology" not in [r[1] for r in runs]
    finally:
        helpers.PREPARING.pop((CASE, "radiology"), None)
    # a doctor of a supporting department may not prepare; nor a Case File that is not listed
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/prepare-all").status_code == 403
    who["user"] = "dr.ravi"
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/prepare-all").status_code == 403
    c2 = store.create_case("TB-NEW", {"name": "SYNTHETIC, Someone", "mrn": "SYN-1", "agesex": "50 Y / F"}, "", created_by="test"); c2["department"] = OWNER; store.save_case(c2)
    who["user"] = "dr.rao"
    assert tc.post("/api/tb/cases/TB-NEW/helpers/prepare-all").status_code == 409
