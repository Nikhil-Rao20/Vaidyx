"""The specialty agents in the meeting (night-v3 Phase 6, owner decision D2): every head not present and every specialty marked absent
stands in as an agent tile; the coordinator adds or removes any of the six (kept with the meeting, audited); the states are true (ready,
preparing, listening with the asker's name and an expiry, thinking, answering, speaking only while a device reports playing, error);
agents never count for the quorum and never appear among the people; a viewer who is not admitted gets no record quotes. Hermetic: the
fixtures of test_nik_meetings (a fake login system, synthetic Case Files, no model)."""
import asyncio, time
from datetime import datetime, timedelta

import pytest

from tumour_board import agents, board, live, meetings, rules, service, store
from tumour_board.tests.test_nik_meetings import As, app, join_and_admit, started, tc, wait_for, with_agenda  # noqa: F401

STATE_WORDS = {"ready", "preparing", "listening", "thinking", "answering", "speaking", "error"}


@pytest.fixture(autouse=True)
def _fresh_agent_limits():
    """The per-login limits of the agent routes are module-wide: each test starts with none used."""
    from tumour_board.api import meetings as api_meetings
    for lim in (api_meetings.AGENT_ASK_LIMIT, api_meetings.AGENT_LIMIT):
        lim._hits.clear()
    yield


def _agents(tc, mid, user="priya"):
    return {a["role"]: a for a in As(tc, user).get(f"/meetings/{mid}").json()["agents"]}


CT_LINE = "Spiculated mass in the right upper lobe measuring 5.2 x 4.1 cm"   # TB-001's CECT thorax report (D41f9d46c), synthetic
PDL1_LINE = "PD-L1 (22C3) TPS Pending"                                         # TB-001's histopathology report (D67977cf8), synthetic
REAL_POINTS = [("The CECT thorax reports a spiculated right upper lobe mass of 5.2 x 4.1 cm.", "D41f9d46c", CT_LINE),
               ("PD-L1 (22C3) TPS is pending.", "D67977cf8", PDL1_LINE)]


def _brief_real(case_id, role, points, **extra):
    """A brief whose points cite lines that are in the Case File's records ((text, doc_id, quote) each)."""
    _brief(case_id, role, [])
    st = store.get_state(case_id)
    art = st["artefacts"][f"brief_{role}"]
    art["points_for_review"] = [{"text": x, "citations": [{"doc_id": d, "doc_title": "", "date": None, "page": 0, "quote": q}], "references": []} for x, d, q in points]
    art.update(extra)
    store.save_state(case_id, st)


def _brief(case_id, role, points):
    st = store.get_state(case_id)
    st.setdefault("artefacts", {})[f"brief_{role}"] = {
        "role": role, "label": agents.ROLES[role]["label"], "generated": "2026-10-27T10:00:00", "model": "fake", "seconds": 0.1, "version": agents.BRIEF_VERSION,
        "focus": "", "near_match": False, "sections": [], "not_documented": ["ECOG performance status"], "review": {"status": "ai_draft"},
        "signature": rules.case_signature(case_id),  # fresh for the current records
        "points_for_review": [{"text": t, "citations": [{"doc_id": "D1", "doc_title": "CT chest", "date": "2026-03-12", "page": 0, "quote": t}], "references": []} for t in points]}
    store.save_state(case_id, st)


def test_every_absent_head_and_marked_absent_specialty_is_an_agent_with_its_reason(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    ag = _agents(tc, mid)
    for role in ("radiology", "pathology", "medical_oncology", "radiation_oncology"):
        a = ag[role]
        assert a["standing_in"] is True and a["added"] is False and a["reason"] == "Head absent" and a["state"] == "ready"
        assert a["title"] == f"{a['department_name']}, AI agent standing in" and a["note"].startswith("AI agent, support only") and a["voice"]
        assert a["brief"]["status"] in ("none", "ready", "stale") and a["points"] == [] and a["points_count"] == 0 and a["can_remove"] is True
    assert "nuclear_medicine" not in ag  # on demand: not marked, not added
    assert list(ag) == [r for r in meetings.AGENT_ORDER if r in ag]  # the roles' order
    # a specialty marked absent on the attendance sheet stands in too (the old room's rule), with its reason
    board.set_attendance(mid, "nuclear_medicine", "absent", "anil")
    a = _agents(tc, mid)["nuclear_medicine"]
    assert a["standing_in"] is True and a["reason"] == "Marked absent" and a["title"] == "Nuclear Medicine, AI agent standing in"
    # the head who joins is no longer stood in for
    join_and_admit(tc, mid, "suresh")
    assert "radiology" not in _agents(tc, mid)


def test_the_coordinator_adds_and_removes_agents_kept_with_the_meeting(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "suresh")  # Radiology's head is here
    prepared = []
    monkeypatch.setattr(service, "prepare_session_agents", lambda sid, user, roles=None, case_ids=None, refresh=False: prepared.append((roles, case_ids)) or [])
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "priya").post(f"/meetings/{mid}/agents", json={"role": "radiology", "on": True}).status_code == 403  # members never add
    assert As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "cardiology", "on": True}).status_code == 404
    q0 = As(tc, "priya").get(f"/meetings/{mid}").json()["quorum"]
    r = As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "radiology", "on": True})
    assert r.status_code == 200, r.text
    a = {x["role"]: x for x in r.json()["agents"]}["radiology"]
    assert a["added"] is True and a["standing_in"] is False and a["added_by"] == "anil" and a["reason"] == "Added by Anil Kumar"
    assert a["title"] == "Radiology, AI agent, called by Anil Kumar"
    assert prepared == [(["radiology"], ["TB-001"])]  # its brief starts
    assert events[-1]["type"] == "agents" and "radiology" in [x["role"] for x in events[-1]["agents"]] and events[-1]["members_ask"] is True
    # nuclear medicine on demand, then pathology removed
    assert As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "nuclear_medicine", "on": True}).status_code == 200
    meetings._set_agent(mid, "pathology", "answering", by="priya", question="Qx")
    r = As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "pathology", "on": False})
    assert r.status_code == 200 and "pathology" not in [x["role"] for x in r.json()["agents"]]
    assert any(e["type"] == "agent_stop" and e["role"] == "pathology" and e["question"] == "Qx" for e in events)  # its voice stops everywhere
    assert "pathology" not in (meetings.AGENT_STATE.get(mid) or {})
    ag = _agents(tc, mid)
    assert "radiology" in ag and "nuclear_medicine" in ag and "pathology" not in ag and ag["nuclear_medicine"]["reason"] == "Added by Anil Kumar"
    # kept with the meeting: the map survives a reload from the file; the live memory is empty after a restart and the state is ready
    s = board.get(mid)
    assert s["agents_active"]["TB-001"]["radiology"]["on"] is True and s["agents_active"]["TB-001"]["pathology"]["on"] is False
    assert s["agents_active"]["TB-001"]["pathology"]["by"] == "anil"
    meetings.AGENT_STATE.clear(); meetings.AGENT_AUDIO.clear()
    assert all(a["state"] == "ready" for a in _agents(tc, mid).values())
    # audited by ids
    kinds = [(e["kind"], e.get("role")) for e in board.read_audit() if e["session"] == mid and e["kind"] in ("agent_added", "agent_removed")]
    assert kinds == [("agent_added", "radiology"), ("agent_added", "nuclear_medicine"), ("agent_removed", "pathology")]
    # the quorum never counts an agent: the heads present and the counts are the same, only the names standing in differ
    q1 = As(tc, "priya").get(f"/meetings/{mid}").json()["quorum"]
    assert (q0["present"], q0["total"], [h["present"] for h in q0["heads"]]) == (q1["present"], q1["total"], [h["present"] for h in q1["heads"]])
    assert "Pathology" not in q1["agents"] and "Radiology" not in q1["agents"]  # added agents are not "standing in"
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert not any(x["user"] in ("radiology", "nuclear_medicine") for x in v["attendance"])
    assert set(board.get(mid).get("people") or {}) == {"priya", "suresh"}
    # the next case clears the live state, not the map; a second case has its own default
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"}).status_code == 200
    ag2 = _agents(tc, mid)
    assert "pathology" in ag2 and "radiology" not in ag2  # Radiology's head is here; the additions were for TB-001


def test_members_can_ask_the_agents_switch_and_the_inactive_agent(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")

    async def fake_ask(case_id, role, question, history=None, user="", **kw):
        return {"role": role, "label": "x", "status": "not_documented", "statements": [], "references": [], "removed": [], "model": "m", "seconds": 0.1, "message": "Not documented in the Case File."}
    monkeypatch.setattr(agents, "ask", fake_ask)
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "What is the SUV?", "role": "nuclear_medicine"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agent_not_in_meeting", r.text
    assert As(tc, "priya").put(f"/meetings/{mid}/agents/settings", json={"members_ask": False}).status_code == 403
    r = As(tc, "anil").put(f"/meetings/{mid}/agents/settings", json={"members_ask": False})
    assert r.status_code == 200 and r.json() == {"members_ask": False}
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert v["can"]["ask_agents"] is False and v["can"]["members_ask"] is False and v["can"]["ask"] is True
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "What is the SUV?", "role": "radiology"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "agents_ask_off"
    assert As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "A question for the board"}).status_code == 200
    r = As(tc, "anil").post(f"/meetings/{mid}/questions", json={"text": "What is the SUV?", "role": "radiology"})  # the coordinator always may
    assert r.status_code == 200, r.text
    qid = r.json()["question"]["id"]
    wait_for(lambda: isinstance(meetings._question(board.get(mid), qid).get("answer"), dict) and meetings._question(board.get(mid), qid)["answer"]["status"] != "answering")
    a = meetings._question(board.get(mid), qid)["answer"]
    assert a["status"] == "not_documented" and a["speech"] == ["AI agent, Radiology.", meetings.NOT_DOCUMENTED_SPOKEN]
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["can"]["ask_agents"] is True


def test_listening_is_true_only_while_the_askers_device_records(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "ravi").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True}).status_code == 403  # not admitted
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/nuclear_medicine/listening", json={"on": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agent_not_in_meeting"
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    assert r.status_code == 200 and r.json()["state"] == "listening" and r.json()["by_name"] == "Dr Priya Nair" and r.json()["accepted"] is True, r.text
    assert events[-1]["type"] == "agent_state" and events[-1]["role"] == "radiology" and events[-1]["state"] == "listening" and events[-1]["by_name"] == "Dr Priya Nair"
    a = _agents(tc, mid)["radiology"]
    assert a["state"] == "listening" and a["by"] == "priya" and a["by_name"] == "Dr Priya Nair"
    assert _agents(tc, mid)["medical_oncology"]["state"] == "ready"  # per agent, never per meeting
    # someone else's device: the tile keeps the first asker's word; their own stop does nothing to it
    r = As(tc, "meena").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    assert r.status_code == 200 and r.json()["accepted"] is False and r.json()["by"] == "priya"
    As(tc, "meena").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": False})
    assert _agents(tc, mid)["radiology"]["state"] == "listening"
    # the asker stops: ready, audited as seconds only
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": False})
    assert r.status_code == 200 and r.json()["state"] == "ready"
    au = [e for e in board.read_audit() if e["session"] == mid and e["kind"] == "agent_listening"]
    assert [(x["by"], x["on"]) for x in au] == [("priya", True), ("meena", True), ("meena", False), ("priya", False)]  # every device's on and off
    assert "seconds" in au[3] and not any(k in au[3] for k in ("text", "audio", "question"))
    # a closed tab: the entry expires by itself
    As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    meetings.AGENT_LISTEN[mid]["radiology"]["priya"]["expires"] = time.time() - 1
    assert _agents(tc, mid)["radiology"]["state"] == "ready"
    # while the agent thinks, listening is not shown
    meetings._set_agent(mid, "radiology", "thinking", by="meena", question="Q1")
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    assert r.json()["accepted"] is False and r.json()["state"] == "thinking"
    assert set(a["state"] for a in _agents(tc, mid).values()) <= STATE_WORDS


def test_preparing_comes_from_the_saved_brief_status_and_error_clears(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    board.set_agent(mid, "TB-001", "pathology", "queued")
    a = _agents(tc, mid)["pathology"]
    assert a["state"] == "preparing" and a["brief"]["status"] == "preparing"
    board.set_agent(mid, "TB-001", "pathology", "running")
    assert _agents(tc, mid)["pathology"]["state"] == "preparing"
    board.set_agent(mid, "TB-001", "pathology", "ready")
    assert _agents(tc, mid)["pathology"]["state"] == "ready"
    board.set_agent(mid, "TB-001", "radiology", "no_documents")
    assert _agents(tc, mid)["radiology"]["state"] == "ready"
    meetings._set_agent(mid, "radiology", "error", by="priya", question="Q9", ttl=meetings.ERROR_TTL)
    assert _agents(tc, mid)["radiology"]["state"] == "error"
    meetings.AGENT_STATE[mid]["radiology"]["expires"] = time.time() - 1
    assert _agents(tc, mid)["radiology"]["state"] == "ready"


def test_speaking_is_true_only_while_a_device_reports_playing_and_stop_is_for_everyone(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)

    async def fake_ask(case_id, role, question, history=None, user="", **kw):
        return {"role": role, "label": "Radiology support", "status": "answered", "statements": [{"text": "Lesion 3.2 cm", "citations": [{"doc_id": "D1", "quote": "Lesion 3.2 cm"}]}],
                "references": [], "removed": [], "model": "reasoner", "seconds": 0.2}
    monkeypatch.setattr(agents, "ask", fake_ask)
    qid = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "What size?", "role": "radiology"}).json()["question"]["id"]
    wait_for(lambda: any(e["type"] == "agent_state" and e["state"] == "ready" for e in events))
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/audio", json={"question": "Qnone", "playing": True}).status_code == 404
    r = As(tc, "meena").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": True})
    assert r.status_code == 200 and r.json()["state"] == "speaking" and r.json()["question"] == qid, (r.text, meetings.AGENT_AUDIO, meetings.AGENT_STATE)
    assert events[-1]["type"] == "agent_state" and events[-1]["state"] == "speaking" and events[-1]["role"] == "radiology"
    assert _agents(tc, mid)["radiology"]["state"] == "speaking"
    n = len(events)
    As(tc, "priya").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": True})
    assert len(events) == n  # a second device: the word did not change, no event
    As(tc, "meena").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": False})
    assert _agents(tc, mid)["radiology"]["state"] == "speaking"  # priya's device still plays
    meetings.AGENT_AUDIO[mid][qid]["devices"]["priya"] = time.time() - 1  # its report expired (a closed tab)
    assert _agents(tc, mid)["radiology"]["state"] == "ready"
    # Stop for everyone: the asker or the coordinator; the text stays
    As(tc, "priya").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": True})
    r = As(tc, "meena").post(f"/meetings/{mid}/agents/radiology/stop", json={"question": qid})
    assert r.status_code == 403
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/stop", json={"question": qid})
    assert r.status_code == 200 and r.json()["question"] == qid, r.text
    assert events[-2]["type"] == "agent_stop" and events[-2]["question"] == qid and events[-1]["type"] == "agent_state" and events[-1]["state"] == "ready"
    q = meetings._question(board.get(mid), qid)
    assert q["answer"]["stopped_by"] == "priya" and q["answer"]["text"] == "Lesion 3.2 cm"
    assert As(tc, "anil").post(f"/meetings/{mid}/agents/radiology/stop", json={}).status_code == 200
    assert any(e["kind"] == "agent_stop" for e in board.read_audit() if e["session"] == mid)


def test_one_answer_at_a_time_per_agent_the_later_question_waits(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    gate = asyncio.Event()
    order, loops = [], []

    async def slow_ask(case_id, role, question, history=None, user="", **kw):
        loops.append(asyncio.get_running_loop())
        order.append(("start", question))
        if question == "first":
            await gate.wait()
        order.append(("end", question))
        return {"role": role, "label": "x", "status": "answered", "statements": [{"text": question, "citations": [{"doc_id": "D1", "quote": question}]}],
                "references": [], "removed": [], "model": "m", "seconds": 0.1}
    monkeypatch.setattr(agents, "ask", slow_ask)
    q1 = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "first", "role": "radiology"}).json()["question"]
    wait_for(lambda: order == [("start", "first")])
    r = As(tc, "meena").post(f"/meetings/{mid}/questions", json={"text": "second", "role": "radiology"})
    assert r.status_code == 200, r.text
    q2 = r.json()["question"]
    assert q2["queued"] is True and q2["queue_note"] == "Radiology is answering Dr Priya Nair. Yours is next."
    # another agent is free
    r = As(tc, "meena").post(f"/meetings/{mid}/questions", json={"text": "third", "role": "medical_oncology"})
    assert r.status_code == 200 and r.json()["question"]["queued"] is False, r.text
    wait_for(lambda: ("end", "third") in order)
    assert _agents(tc, mid)["radiology"]["state"] == "thinking" and _agents(tc, mid)["radiology"]["by_name"] == "Dr Priya Nair"
    assert ("start", "second") not in order
    loops[0].call_soon_threadsafe(gate.set)
    wait_for(lambda: ("end", "second") in order, 10)
    wait_for(lambda: isinstance(meetings._question(board.get(mid), q2["id"]).get("answer"), dict) and meetings._question(board.get(mid), q2["id"])["answer"]["status"] == "answered", 10)
    assert order == [("start", "first"), ("start", "third"), ("end", "third"), ("end", "first"), ("start", "second"), ("end", "second")]
    s = board.get(mid)
    assert meetings._question(s, q1["id"])["answer"]["text"] == "first" and meetings._question(s, q2["id"])["queued"] is False and "queue_note" not in meetings._question(s, q2["id"])
    assert [e["question"] for e in s["log"] if e["kind"] == "answer"] == ["third", "first", "second"]


def test_a_viewer_who_is_not_admitted_sees_the_agents_without_record_quotes(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    _brief("TB-001", "pathology", ["Grade is reported as 2.", "ER status is pending.", "p3", "p4", "p5", "p6"])
    a = _agents(tc, mid)["pathology"]
    assert a["points_count"] == 6 and len(a["points"]) == 5 and a["points"][0]["text"] == "Grade is reported as 2."
    assert a["points"][0]["citations"][0] == {"doc_id": "D1", "doc_title": "CT chest", "date": "2026-03-12", "page": 0, "quote": "Grade is reported as 2."}
    assert a["not_documented_count"] == 1 and a["brief"]["status"] in ("ready", "stale") and a["brief"]["label"] == "AI draft, not reviewed"
    r = As(tc, "ravi").get(f"/meetings/{mid}")  # Radiology is on the attendance sheet: ravi may view, is not admitted
    assert r.status_code == 200, r.text
    v = r.json()
    p = {x["role"]: x for x in v["agents"]}["pathology"]
    assert "points" not in p and p["points_count"] == 6 and p["state"] == "ready"
    # the per-socket shape strips them from the events too
    shape = meetings._shape(board.get(mid))
    ev = {"type": "current", "agents": As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]}
    assert "points" not in shape("ravi", {"user": "ravi"}, ev)["agents"][0] and "points" in shape("priya", {"user": "priya"}, ev)["agents"][0]
    assert shape("ravi", {"user": "ravi"}, {"type": "agent_speech", "role": "pathology", "question": "Q1", "index": 0}) is None


def test_present_your_points_speaks_the_brief_by_code(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    called = []

    async def never(*a, **k):
        called.append(a)
    monkeypatch.setattr(agents, "ask", never)
    assert As(tc, "ravi").post(f"/meetings/{mid}/agents/pathology/present").status_code == 403  # not admitted
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/nuclear_medicine/present").json()["detail"]["code"] == "agent_not_in_meeting"
    # no brief yet: a plain answer, nothing invented
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 200, r.text
    q = r.json()["question"]
    assert q["text"] == "Present your points" and q["kind"] == "present_points" and q["role"] == "pathology" and q["by_name"] == "Dr Priya Nair"
    assert q["answer"]["status"] == "not_documented" and q["answer"]["statements"] == [] and q["answer"]["speech"] == ["AI agent, Pathology.", "No brief has been prepared from the records yet."]
    # while the brief prepares: wait
    board.set_agent(mid, "TB-001", "pathology", "running")
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["detail"]["code"] == "brief_preparing"
    board.set_agent(mid, "TB-001", "pathology", "ready")
    # the brief's points, each with its records, by code: no model call; the not documented items are counted, never read as facts
    _brief_real("TB-001", "pathology", REAL_POINTS)
    events.clear()
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 200, r.text
    a = r.json()["question"]["answer"]
    texts = [x for x, _, _ in REAL_POINTS]
    assert a["status"] == "answered" and [x["text"] for x in a["statements"]] == texts
    assert a["statements"][0]["citations"][0]["quote"] == CT_LINE and a["statements"][0]["citations"][0]["doc_title"] == "CECT THORAX REPORT"  # located now
    assert a["speech"] == ["AI agent, Pathology.", *texts, "1 item is listed as not documented; the list is on the screen.", "Sources are on the screen."]
    assert a["not_documented"] == ["ECOG performance status"] and a["kind"] == "present_points" and a["brief_label"] == "AI draft, not reviewed"
    assert a["brief_model"] == "fake" and a["dropped_unverified"] == 0 and a["dropped_note"] == ""
    assert called == []
    # answering while its speech is announced (review 9 D, I6), then ready: speaking only while a device plays
    assert [e["type"] for e in events] == ["question", "agent_state"] + ["agent_speech"] * 5 + ["agent_state"]
    assert events[1]["state"] == "answering" and events[1]["by_name"] == "Dr Priya Nair" and events[-1]["state"] == "ready"
    sp = [e for e in events if e["type"] == "agent_speech"]
    assert sp[-1]["final"] is True and sp[0]["final"] is False
    assert all(e.get("question") == r.json()["question"]["id"] for e in events[1:-1])
    # kept with the meeting: the question list, the session's agent log, the audit; the state stays ready (speaking only while a device plays)
    s = board.get(mid)
    assert [x["kind"] for x in s["log"] if x.get("kind") == "answer"] and s["log"][-1]["question"] == "Present your points" and len(s["log"][-1]["statements"]) == 2
    assert any(e["kind"] == "present_points" and e.get("statements") == 2 for e in board.read_audit() if e["session"] == mid)
    assert _agents(tc, mid)["pathology"]["state"] == "ready"
    assert [x["text"] for x in As(tc, "priya").get(f"/meetings/{mid}").json()["questions"]] == ["Present your points", "Present your points"]
    # a brief with no documents of the specialty
    st = store.get_state("TB-001"); st["artefacts"]["brief_radiology"] = {**st["artefacts"]["brief_pathology"], "role": "radiology", "points_for_review": [], "not_documented": [], "no_documents": True, "message": "No Radiology reports in this Case File."}
    store.save_state("TB-001", st)
    a = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/present").json()["question"]["answer"]
    assert a["status"] == "not_documented" and a["speech"] == ["AI agent, Radiology.", "No Radiology reports in this Case File."]


def test_the_context_is_pre_loaded_when_a_case_comes_on_the_floor_and_when_an_agent_is_added(tc, monkeypatch):
    warmed = []

    async def fake_warm(case_id, role):
        warmed.append((case_id, role))
        return 0.5
    monkeypatch.setattr(agents, "warm", fake_warm)
    mid = started(tc)
    wait_for(lambda: len(warmed) >= 4)
    assert all(c == "TB-001" for c, _ in warmed) and {r for _, r in warmed} == set(meetings.active_roles(board.get(mid), "TB-001"))
    n = len(warmed)
    join_and_admit(tc, mid, "priya")
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"}).status_code == 200
    wait_for(lambda: len(warmed) > n and all(c == "TB-002" for c, _ in warmed[n:]))
    n = len(warmed)
    assert As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "nuclear_medicine", "on": True}).status_code == 200
    wait_for(lambda: warmed[n:] == [("TB-002", "nuclear_medicine")])
    assert any(e["kind"] == "meeting_started" and e.get("warming", 0) >= 4 for e in board.read_audit() if e["session"] == mid)


def _two_statement_ask(between):
    """A fake agents.ask that streams two statements and calls `between` after the first (to stop, remove or move the case meanwhile)."""
    async def fake_ask(case_id, role, question, history=None, user="", on_statement=None, **kw):
        s1 = {"text": "Lesion 3.2 cm", "citations": [{"doc_id": "D1", "quote": "Lesion 3.2 cm"}]}
        s2 = {"text": "Nodes clear", "citations": [{"doc_id": "D1", "quote": "Nodes clear"}]}
        await on_statement(s1, 0)
        between()
        await on_statement(s2, 1)
        return {"role": role, "label": "x", "status": "answered", "statements": [s1, s2], "references": [], "removed": [], "model": "m", "seconds": 0.3}
    return fake_ask


def test_a_stop_for_everyone_during_the_stream_holds(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    box = {}
    # the fake answer runs on the app's loop as soon as the question is posted: the stop (by the asker) comes from inside it
    monkeypatch.setattr(agents, "ask", _two_statement_ask(lambda: meetings.stop_agent(mid, "priya", "radiology", meetings.need(mid)["questions"][-1]["id"])))
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "What size?", "role": "radiology"})
    box["qid"] = r.json()["question"]["id"]
    wait_for(lambda: isinstance(meetings._question(board.get(mid), box["qid"]).get("answer"), dict) and meetings._question(board.get(mid), box["qid"])["answer"]["status"] == "answered")
    a = meetings._question(board.get(mid), box["qid"])["answer"]
    assert a["stopped_by"] == "priya" and len(a["statements"]) == 2  # the text stays, the voice stopped
    idx = [i for i, e in enumerate(events) if e["type"] == "agent_stop"][0]
    assert not any(e["type"] == "agent_speech" for e in events[idx:])  # no sentence announced after the stop


def test_a_removed_agent_stops_answering_and_its_queued_question_is_closed(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    # the coordinator removes the agent while it answers (from inside the loop: the route's call would block the loop's thread)
    monkeypatch.setattr(agents, "ask", _two_statement_ask(lambda: meetings.set_agent(mid, "anil", "radiology", False)))
    q1 = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "first", "role": "radiology"}).json()["question"]
    wait_for(lambda: isinstance(meetings._question(board.get(mid), q1["id"]).get("answer"), dict) and meetings._question(board.get(mid), q1["id"])["answer"]["status"] in ("not_listed", "answered", "error"))
    a = meetings._question(board.get(mid), q1["id"])["answer"]
    assert a["status"] == "not_listed" and a["message"] == meetings.AGENT_LEFT and len(a["statements"]) == 1  # the first statement stands
    idx = [i for i, e in enumerate(events) if e["type"] == "agent_stop"][0]
    assert not any(e["type"] == "agent_speech" for e in events[idx:])
    assert "radiology" not in _agents(tc, mid)
    # a question that waited for the removed agent is closed the same way, without a model call
    called = []

    async def never(*a, **k):
        called.append(a)
    monkeypatch.setattr(agents, "ask", never)
    s = board.get(mid)
    s["questions"].append({"id": "Qwait", "by": "meena", "by_name": "Dr Meena", "text": "second", "at": meetings._now(), "case_id": "TB-001", "answer": None, "role": "radiology", "queued": True})
    board.save_session(s)
    out = asyncio.run(meetings.answer(mid, "Qwait", "meena"))
    assert out["status"] == "not_listed" and called == []


def test_an_answer_interrupted_by_a_restart_is_marked_not_left_thinking(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    s = board.get(mid)
    old = (datetime.now() - timedelta(seconds=meetings.STUCK_AFTER + 5)).isoformat(timespec="seconds")
    s["questions"] += [{"id": "Qold", "by": "priya", "by_name": "Dr Priya Nair", "text": "old", "at": old, "case_id": "TB-001", "answer": None, "role": "pathology", "queued": True},
                       {"id": "Qpart", "by": "priya", "by_name": "Dr Priya Nair", "text": "part", "at": old, "case_id": "TB-001", "role": "pathology",
                        "answer": {"status": "answering", "text": "Grade 2", "statements": [{"text": "Grade 2", "citations": []}], "references": [], "role": "pathology", "label": "x", "speech": ["AI agent, Pathology.", "Grade 2"], "note": ""}},
                       {"id": "Qnew", "by": "priya", "by_name": "Dr Priya Nair", "text": "new", "at": meetings._now(), "case_id": "TB-001", "answer": None, "role": "pathology", "queued": False},
                       {"id": "Qboard", "by": "priya", "by_name": "Dr Priya Nair", "text": "to the board", "at": old, "case_id": "TB-001", "answer": None, "role": None}]
    board.save_session(s)
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    q = {x["id"]: x for x in v["questions"]}
    assert q["Qold"]["answer"]["status"] == "error" and q["Qold"]["answer"]["message"] == meetings.INTERRUPTED and q["Qold"]["queued"] is False
    assert q["Qpart"]["answer"]["status"] == "error" and q["Qpart"]["answer"]["text"] == "Grade 2" and q["Qpart"]["answer"]["statements"]
    assert q["Qnew"]["answer"] is None and q["Qboard"]["answer"] is None  # a fresh one and a question to the board are left alone


def test_the_members_switch_covers_present_and_listening_and_a_called_agent_steps_back(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    _brief("TB-001", "pathology", ["Grade is reported as 2."])
    assert As(tc, "anil").put(f"/meetings/{mid}/agents/settings", json={"members_ask": "false"}).json() == {"members_ask": False}  # a string is read as a word
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["detail"]["code"] == "agents_ask_off"
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/listening", json={"on": True}).json()["detail"]["code"] == "agents_ask_off"
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/listening", json={"on": False}).status_code == 200  # a stop never fails
    assert As(tc, "anil").post(f"/meetings/{mid}/agents/pathology/present").status_code == 200  # the coordinator always may
    assert As(tc, "anil").put(f"/meetings/{mid}/agents/settings", json={"members_ask": True}).json() == {"members_ask": True}
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").status_code == 200
    # switching on an agent that already stands in writes no override: it steps back when its head arrives (N9)
    assert As(tc, "anil").post(f"/meetings/{mid}/agents", json={"role": "pathology", "on": True}).status_code == 200
    assert "pathology" not in (board.get(mid).get("agents_active") or {}).get("TB-001", {})
    join_and_admit(tc, mid, "meena")
    assert "pathology" not in _agents(tc, mid)
    # a stale brief is said first when the points are presented
    st = store.get_state("TB-001"); st["artefacts"]["brief_radiology"] = {**st["artefacts"]["brief_pathology"], "role": "radiology", "signature": {"hash": "old", "docs": []}}
    store.save_state("TB-001", st)
    a = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/present").json()["question"]["answer"]
    assert a["stale"] is True and a["speech"][1] == meetings.STALE_BRIEF
    # playback reports are keyed by login and device: the control view and the room screen of one login do not cancel each other
    qid = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/present").json()["question"]["id"]
    As(tc, "anil").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": True, "device": "tab1"})
    As(tc, "anil").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": True, "device": "tab2"})
    As(tc, "anil").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": "false", "device": "tab1"})
    assert _agents(tc, mid)["radiology"]["state"] == "speaking"
    As(tc, "anil").post(f"/meetings/{mid}/agents/audio", json={"question": qid, "playing": False, "device": "tab2"})
    assert _agents(tc, mid)["radiology"]["state"] == "ready"


# ---- the whole-run review, area D (night-v3 item 9.2) ------------------------------------------------------------------------------

def _admit_guest(tc, mid):
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    assert As(tc, "guest").post("/meetings/join", json={"code": code}).status_code == 200
    assert As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "guest"}).status_code == 200


def _named_question(mid):
    """An agent answer whose statement and quote carry TB-001's synthetic patient name and UHID (a plausible citation for an identity
    question), saved on the meeting."""
    s = board.get(mid)
    stmt = {"text": "The CECT thorax is for Ramesh Kumar, UHID SYN-100231.", "citations": [{"doc_id": "D41f9d46c", "quote": "Patient SYNTHETIC, Ramesh Kumar\nUHID SYN-100231"}]}
    q = {"id": "Qname", "by": "priya", "by_name": "Dr Priya Nair", "text": "Whose scan is SYN-100231?", "at": meetings._now(), "case_id": "TB-001", "role": "radiology",
         "queued": False, "answer": {"status": "answered", "text": stmt["text"], "statements": [stmt], "references": [], "role": "radiology", "label": "x",
                                     "speech": ["AI agent, Radiology.", stmt["text"], "Sources are on the screen."], "message": ""}}
    s.setdefault("questions", []).append(q)
    board.save_session(s)
    return q


def _no_identity(obj):
    text = str(obj)
    return "Ramesh" not in text and "Kumar" not in text and "SYN-100231" not in text


def test_an_outside_expert_without_consent_gets_answers_and_points_without_the_identity(tc, monkeypatch):
    """Review 9 D, S2: the questions, the streamed answers (statements, quotes, speech) and the agents' points reach an admitted
    outside expert with [withheld] for the patient's name and numbers, unless the owner recorded consent; members are unaffected."""
    from tumour_board import audio_proxy, org
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    _admit_guest(tc, mid)
    _brief_real("TB-001", "pathology", [("The CECT thorax report names Ramesh Kumar.", "D41f9d46c", "Patient SYNTHETIC, Ramesh Kumar")])
    q = _named_question(mid)
    # the view (GET and the socket's first message)
    g = As(tc, "guest").get(f"/meetings/{mid}").json()
    gq = next(x for x in g["questions"] if x["id"] == "Qname")
    gp = {a["role"]: a for a in g["agents"]}["pathology"]["points"]
    assert _no_identity(gq) and _no_identity(gp) and "[withheld]" in gq["answer"]["statements"][0]["citations"][0]["quote"]
    assert "[withheld]" in gq["text"] and "[withheld]" in gq["answer"]["speech"][1] and "[withheld]" in gp[0]["citations"][0]["quote"]
    assert gq["by_name"] == "Dr Priya Nair" and gq["answer"]["speech"][0] == "AI agent, Radiology."  # only the patient's identity goes
    p = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert "SYN-100231" in str(next(x for x in p["questions"] if x["id"] == "Qname")) and "Ramesh Kumar" in str({a["role"]: a for a in p["agents"]}["pathology"]["points"])
    # the events: a streamed statement and the agents list, per socket
    shape = meetings._shape(board.get(mid))
    ev_q = {"type": "question", "question": q}
    ev_a = {"type": "agents", "agents": p["agents"]}
    assert _no_identity(shape("guest", org.roles("guest"), ev_q)) and _no_identity(shape("guest", org.roles("guest"), ev_a))
    assert shape("priya", org.roles("priya"), ev_q) == ev_q and shape("priya", org.roles("priya"), ev_a) == ev_a
    assert shape("anil", org.roles("anil"), ev_q) == ev_q
    # read aloud by reference: the sentence the outside expert's device fetches carries no identity either
    ref = {"kind": "meeting_answer", "meeting_id": mid, "id": "Qname", "index": 1}
    assert "[withheld]" in audio_proxy.resolve(org.roles("guest"), ref) and "Ramesh" in audio_proxy.resolve(org.roles("priya"), ref)
    # with the owner's consent for an outside discussion, the expert reads it as the members do
    c = store.get_case("TB-001"); c["consent"] = {"outside_discussion": True}; store.save_case(c)
    g = As(tc, "guest").get(f"/meetings/{mid}").json()
    assert "SYN-100231" in str(next(x for x in g["questions"] if x["id"] == "Qname")) and "Ramesh Kumar" in str({a["role"]: a for a in g["agents"]}["pathology"]["points"])
    assert meetings._shape(board.get(mid))("guest", org.roles("guest"), ev_q) == ev_q


def _gated_ask(loops, started_, gate_name="gate"):
    """A fake agents.ask that waits for a gate before streaming two verified statements; `loops` gets the app's loop and the gate."""
    async def fake_ask(case_id, role, question, history=None, user="", on_statement=None, **kw):
        gate = asyncio.Event()
        loops.append((asyncio.get_running_loop(), gate))
        started_.append(question)
        try:
            await gate.wait()
        except asyncio.CancelledError:
            started_.append("cancelled")
            raise
        s1 = {"text": "Lesion 3.2 cm", "citations": [{"doc_id": "D1", "quote": "Lesion 3.2 cm"}]}
        s2 = {"text": "Nodes clear", "citations": [{"doc_id": "D1", "quote": "Nodes clear"}]}
        await on_statement(s1, 0)
        await on_statement(s2, 1)
        return {"role": role, "label": "x", "status": "answered", "statements": [s1, s2], "references": [], "removed": [], "model": "m", "seconds": 0.3}
    return fake_ask


def test_a_stop_while_the_agent_thinks_holds_for_the_whole_answer(tc, monkeypatch):
    """Review 9 D, I2: Stop for everyone before the first statement is kept on the question; no sentence is announced afterwards and
    the saved answer shows who stopped it (a device that reloads or joins later plays nothing)."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    loops, started_ = [], []
    monkeypatch.setattr(agents, "ask", _gated_ask(loops, started_))
    qid = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "What size?", "role": "radiology"}).json()["question"]["id"]
    wait_for(lambda: started_ == ["What size?"])
    assert _agents(tc, mid)["radiology"]["state"] == "thinking"
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/stop", json={"question": qid})
    assert r.status_code == 200, r.text
    sr = meetings._question(board.get(mid), qid)["stop_requested"]
    assert sr["by"] == "priya" and sr["at"]
    loop, gate = loops[0]
    loop.call_soon_threadsafe(gate.set)
    wait_for(lambda: (meetings._question(board.get(mid), qid).get("answer") or {}).get("status") == "answered")
    a = meetings._question(board.get(mid), qid)["answer"]
    assert a["stopped_by"] == "priya" and [x["text"] for x in a["statements"]] == ["Lesion 3.2 cm", "Nodes clear"]  # the text stays
    idx = [i for i, e in enumerate(events) if e["type"] == "agent_stop"][0]
    assert not any(e["type"] == "agent_speech" for e in events[idx:])
    assert not any(e["type"] == "agent_speech" for e in events)  # nothing was spoken at all


def test_ending_the_meeting_stops_the_agents(tc, monkeypatch):
    """Review 9 D, I3: the end cancels the answer in flight and the question waiting behind it (no model call after the close), no
    sentence is announced after `ended`, and no live state comes back."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    loops, started_ = [], []
    monkeypatch.setattr(agents, "ask", _gated_ask(loops, started_))
    q1 = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "first", "role": "radiology"}).json()["question"]["id"]
    wait_for(lambda: started_ == ["first"])
    q2 = As(tc, "meena").post(f"/meetings/{mid}/questions", json={"text": "second", "role": "radiology"}).json()["question"]
    assert q2["queued"] is True
    assert meetings._TASKS_BY_MID.get(mid)
    r = As(tc, "anil").post(f"/meetings/{mid}/end")
    assert r.status_code == 200, r.text

    def closed(qid):
        a = meetings._question(board.get(mid), qid).get("answer")
        return isinstance(a, dict) and a.get("status") == "not_listed"
    wait_for(lambda: closed(q1) and closed(q2["id"]))
    s = board.get(mid)
    for qid in (q1, q2["id"]):
        a = meetings._question(s, qid)["answer"]
        assert a["message"] == meetings.MEETING_ENDED and a["statements"] == []
    assert started_ == ["first", "cancelled"]  # the waiting question never reached the model
    idx = [i for i, e in enumerate(events) if e["type"] == "ended"][0]
    assert not any(e["type"] in ("agent_speech", "agent_state") for e in events[idx:])
    wait_for(lambda: not meetings._TASKS_BY_MID.get(mid))
    assert mid not in meetings.AGENT_STATE and s["status"] == "closed"
    assert any(e["kind"] == "meeting_ended" and e.get("agent_tasks_stopped") == 2 for e in board.read_audit() if e["session"] == mid)
    # an answer asked of a closed meeting (a restart, a late call) ends at once without the model
    s["questions"].append({"id": "Qlate", "by": "priya", "by_name": "Dr Priya Nair", "text": "late", "at": meetings._now(), "case_id": "TB-001", "answer": None, "role": "radiology", "queued": False})
    board.save_session(s)
    out = asyncio.run(meetings.answer(mid, "Qlate", "priya"))
    assert out["status"] == "not_listed" and out["message"] == meetings.MEETING_ENDED and started_ == ["first", "cancelled"]
    assert meetings._set_agent(mid, "radiology", "thinking", by="priya") == {} and mid not in meetings.AGENT_STATE


def test_listening_goes_when_the_askers_last_socket_closes_and_when_it_expires(tc, monkeypatch):
    """Review 9 D, I4: the asker's tab closes, every screen hears ready at once; an entry left alone is announced when it expires; and
    an answer never erases another member's listening."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "meena")
    events = []
    real = live.broadcast
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or real(m, ev, **kw))
    tc.cookies.set("vaidyx_session", "tok-priya")
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as ws:
        assert ws.receive_json()["type"] == "state"
        r = As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
        assert r.json()["state"] == "listening" and r.json()["accepted"] is True
        tc.cookies.set("vaidyx_session", "tok-priya")
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as ws2:  # a second tab: closing one keeps the word
            assert ws2.receive_json()["type"] == "state"
        assert _agents(tc, mid)["radiology"]["state"] == "listening"
        events.clear()
    wait_for(lambda: any(e["type"] == "agent_state" and e["role"] == "radiology" and e["state"] == "ready" for e in events))
    assert "priya" not in (meetings.AGENT_LISTEN.get(mid) or {}).get("radiology", {})
    # an entry left alone: announced when it expires, without anyone reading the state
    monkeypatch.setattr(meetings, "LISTEN_TTL", 0.2)
    r = As(tc, "meena").post(f"/meetings/{mid}/agents/medical_oncology/listening", json={"on": True})
    assert r.json()["state"] == "listening", r.text
    events.clear()
    wait_for(lambda: any(e["type"] == "agent_state" and e["role"] == "medical_oncology" and e["state"] == "ready" for e in events), 3)
    # kept per (role, user): an answer to someone else shows thinking, then the member still recording is shown again
    monkeypatch.setattr(meetings, "LISTEN_TTL", 65.0)
    As(tc, "meena").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    meetings._set_agent(mid, "radiology", "thinking", by="priya", question="Q1")
    assert _agents(tc, mid)["radiology"]["state"] == "thinking"
    meetings._set_agent(mid, "radiology", "ready")
    a = _agents(tc, mid)["radiology"]
    assert a["state"] == "listening" and a["by"] == "meena"


def test_present_your_points_speaks_only_points_that_match_the_records_now(tc, monkeypatch):
    """Review 9 D, I5: a stale brief whose quoted line is no longer in the records is not spoken, a point kept on an approximate
    quote is never spoken, and the answer counts what was left out."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    removed = ("The CECT thorax reports a 7.4 cm mass.", "D41f9d46c", "Spiculated mass measuring 7.4 cm")  # the line is not in the records now
    _brief_real("TB-001", "pathology", [REAL_POINTS[0], removed], signature={"hash": "old", "docs": []})
    st = store.get_state("TB-001")
    pts = st["artefacts"]["brief_pathology"]["points_for_review"]
    pts.append({"text": "PD-L1 (22C3) TPS is pending.", "citations": [{"doc_id": "D67977cf8", "quote": PDL1_LINE, "approximate": True}], "references": [], "approximate": True})
    store.save_state("TB-001", st)
    a = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["question"]["answer"]
    assert a["stale"] is True and a["status"] == "answered"
    assert [x["text"] for x in a["statements"]] == [REAL_POINTS[0][0]]
    note = "2 points no longer match the records and were left out."
    assert a["dropped_unverified"] == 2 and a["dropped_note"] == note
    assert a["speech"] == ["AI agent, Pathology.", meetings.STALE_BRIEF, REAL_POINTS[0][0], note,
                           "1 item is listed as not documented; the list is on the screen.", "Sources are on the screen."]
    assert "7.4" not in " ".join(a["speech"]) and "PD-L1" not in " ".join(a["speech"])
    assert any(e["kind"] == "present_points" and e.get("dropped") == 2 for e in board.read_audit() if e["session"] == mid)
    # nothing left that matches: nothing is read as fact, the count is said
    _brief_real("TB-001", "pathology", [removed])
    a = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["question"]["answer"]
    assert a["status"] == "not_documented" and a["statements"] == [] and a["message"] == "1 point no longer matches the records and was left out."
    assert a["speech"] == ["AI agent, Pathology.", "1 point no longer matches the records and was left out."]


def test_present_your_points_waits_for_the_agent_to_finish(tc, monkeypatch):
    """Review 9 D, I6: one answer at a time per agent; Present your points is refused while the agent thinks or answers."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    _brief_real("TB-001", "pathology", REAL_POINTS)
    for word in ("thinking", "answering"):
        meetings._set_agent(mid, "pathology", word, by="meena", question="Q1")
        r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
        assert r.status_code == 409 and r.json()["detail"] == {"message": "Pathology is answering Dr Meena. Try again when it finishes.", "code": "agent_busy"}, r.text
    meetings._set_agent(mid, "pathology", "ready")

    class Held:
        def locked(self):
            return True
    meetings.AGENT_LOCKS[(mid, "pathology")] = Held()  # an answer holds the agent's lock (waiting to start)
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 409 and r.json()["detail"]["message"] == "Pathology is answering someone. Try again when it finishes."
    meetings.AGENT_LOCKS.pop((mid, "pathology"))
    assert As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").status_code == 200
    assert not any(q.get("kind") == "present_points" and q.get("answer", {}).get("status") != "answered" for q in board.get(mid)["questions"])
    assert sum(1 for q in board.get(mid)["questions"] if q.get("kind") == "present_points") == 1  # the refusals saved nothing


def test_the_brief_names_its_model_and_its_review(tc):
    """Review 9 C, S1 (the backend half): the agent's brief carries the model that wrote it; a Present your points answer carries
    brief_model and brief_label."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    _brief_real("TB-001", "pathology", REAL_POINTS, model="Gemma-4-31B")
    a = _agents(tc, mid)["pathology"]
    assert a["brief"]["model"] == "Gemma-4-31B" and a["brief"]["label"] == "AI draft, not reviewed"
    ans = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["question"]["answer"]
    assert ans["brief_model"] == "Gemma-4-31B" and ans["brief_label"] == "AI draft, not reviewed"
    st = store.get_state("TB-001"); st["artefacts"]["brief_pathology"]["review"] = {"status": "reviewed", "by": "meena"}; store.save_state("TB-001", st)
    ans = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present").json()["question"]["answer"]
    assert ans["brief_label"] == "Reviewed by Dr Meena"
    st["artefacts"]["brief_pathology"]["review"] = {"status": "reviewed", "by": "anil"}; store.save_state("TB-001", st)
    assert meetings._brief_label(st["artefacts"]["brief_pathology"]) == "Reviewed by Dr Anil Kumar"


def test_the_agent_error_names_no_python_class(tc, monkeypatch):
    """Review 9 D, M5: a failed answer says "The agent could not answer. Try again."; the class name is in the audit only."""
    mid = started(tc)
    join_and_admit(tc, mid, "priya")

    async def boom(*a, **k):
        raise TimeoutError("model slow")
    monkeypatch.setattr(agents, "ask", boom)
    qid = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Lesion size?", "role": "radiology"}).json()["question"]["id"]
    wait_for(lambda: (meetings._question(board.get(mid), qid).get("answer") or {}).get("status") == "error")
    a = meetings._question(board.get(mid), qid)["answer"]
    assert a["text"] == "The agent could not answer. Try again." and a["message"] == a["text"] and "TimeoutError" not in str(a) and "error" not in a
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert "TimeoutError" not in str(v)
    au = [e for e in board.read_audit() if e["session"] == mid and e["kind"] == "question_answered"]
    assert au[-1]["status"] == "error" and au[-1]["error"] == "TimeoutError"
