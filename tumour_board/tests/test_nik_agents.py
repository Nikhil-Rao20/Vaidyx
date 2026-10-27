"""The specialty agents in the meeting (night-v3 Phase 6, owner decision D2): every head not present and every specialty marked absent
stands in as an agent tile; the coordinator adds or removes any of the six (kept with the meeting, audited); the states are true (ready,
preparing, listening with the asker's name and an expiry, thinking, answering, speaking only while a device reports playing, error);
agents never count for the quorum and never appear among the people; a viewer who is not admitted gets no record quotes. Hermetic: the
fixtures of test_nik_meetings (a fake login system, synthetic Case Files, no model)."""
import asyncio, time

from tumour_board import agents, board, live, meetings, service, store
from tumour_board.tests.test_nik_meetings import As, app, join_and_admit, started, tc, wait_for, with_agenda  # noqa: F401

STATE_WORDS = {"ready", "preparing", "listening", "thinking", "answering", "speaking", "error"}


def _agents(tc, mid, user="priya"):
    return {a["role"]: a for a in As(tc, user).get(f"/meetings/{mid}").json()["agents"]}


def _brief(case_id, role, points):
    st = store.get_state(case_id)
    st.setdefault("artefacts", {})[f"brief_{role}"] = {
        "role": role, "label": agents.ROLES[role]["label"], "generated": "2026-10-27T10:00:00", "model": "fake", "seconds": 0.1, "version": agents.BRIEF_VERSION,
        "focus": "", "near_match": False, "sections": [], "not_documented": ["ECOG performance status"], "review": {"status": "ai_draft"},
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
    assert [x["on"] for x in au] == [True, False] and "seconds" in au[1] and not any(k in au[1] for k in ("text", "audio", "question"))
    # a closed tab: the entry expires by itself
    As(tc, "priya").post(f"/meetings/{mid}/agents/radiology/listening", json={"on": True})
    meetings.AGENT_STATE[mid]["radiology"]["expires"] = time.time() - 1
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
    _brief("TB-001", "pathology", ["The histopathology report of 10/03/2026 records grade 2.", "ER and PR results are pending in the IHC report."])
    events.clear()
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 200, r.text
    a = r.json()["question"]["answer"]
    assert a["status"] == "answered" and [x["text"] for x in a["statements"]] == ["The histopathology report of 10/03/2026 records grade 2.", "ER and PR results are pending in the IHC report."]
    assert a["statements"][0]["citations"][0]["quote"] == "The histopathology report of 10/03/2026 records grade 2." and a["statements"][0]["citations"][0]["doc_title"] == "CT chest"
    assert a["speech"] == ["AI agent, Pathology.", "The histopathology report of 10/03/2026 records grade 2.", "ER and PR results are pending in the IHC report.",
                           "1 item is listed as not documented; the list is on the screen.", "Sources are on the screen."]
    assert a["not_documented"] == ["ECOG performance status"] and a["kind"] == "present_points" and a["brief_label"] == "AI draft, not reviewed"
    assert called == []
    assert [e["type"] for e in events] == ["question"] + ["agent_speech"] * 5 and events[-1]["final"] is True and events[1]["final"] is False
    assert all(e.get("question") == r.json()["question"]["id"] for e in events[1:])
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
