"""V1 item 6.2: when the board session starts, the agents of the absent specialties prepare their briefs for every Case File on the
agenda in parallel; a brief still current for the Case File is reused; an error or a restart is shown and can be prepared again.
The agent run is replaced by a fake (no model)."""
import asyncio

from tumour_board import agents, board, rules, service, store
from tumour_board.tests.util import add, make_doc


def _session():
    for cid in ("TB-S1", "TB-S2"):
        store.create_case(cid, {"name": f"SYNTHETIC, {cid}", "mrn": cid}, "lung_nsclc", board_date="2026-12-04", created_by="test")
        add(cid, make_doc(f"Dct{cid[-1]}00000", "ct"))
    s = board.create("2026-12-04", "coord")
    board.set_attendance(s["id"], "radiology", "absent", "coord")
    board.set_attendance(s["id"], "pathology", "absent", "coord")
    return s["id"]


def _fake_agent(monkeypatch, fail=()):
    runs = []

    async def fake(case_id, role, focus="", max_steps=5):
        runs.append((case_id, role))
        if (case_id, role) in fail:
            yield {"type": "error", "message": "model server unreachable"}; return
        brief = {"role": role, "label": agents.ROLES[role]["label"], "generated": f"2026-12-04T09:00:{len(runs):02d}", "model": "fake", "seconds": 0.1,
                 "version": agents.BRIEF_VERSION, "focus": focus, "near_match": False,
                 "sections": [{"heading": "Imaging", "items": [{"text": "CT done.", "citations": []}]}], "points_for_review": [], "not_documented": [],
                 "signature": rules.case_signature(case_id)}
        st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
        yield {"type": "brief", "brief": brief}
    monkeypatch.setattr(agents, "run_agent", fake)
    return runs


def _start(sid, **kw):
    async def go():
        pairs = service.prepare_session_agents(sid, "coord", **kw)
        while service.SESSION_TASKS.get(sid):
            await asyncio.sleep(0.01)
        return pairs
    return asyncio.run(go())


def test_start_prepares_every_absent_specialty_for_every_case_in_parallel(monkeypatch):
    sid = _session(); runs = _fake_agent(monkeypatch, fail={("TB-S2", "pathology")})
    board.start(sid, "coord")
    pairs = _start(sid)
    assert sorted(pairs) == sorted(runs) == [("TB-S1", "pathology"), ("TB-S1", "radiology"), ("TB-S2", "pathology"), ("TB-S2", "radiology")]
    ag = board.get(sid)["agents"]
    assert ag["TB-S1"]["radiology"]["status"] == "ready" and ag["TB-S2"]["pathology"]["status"] == "error"
    assert ag["TB-S2"]["pathology"]["message"] == "model server unreachable"
    assert sum(e["kind"] == "brief_item" for e in board.get(sid)["log"]) == 3


def test_a_current_brief_is_reused_and_refresh_runs_again(monkeypatch):
    sid = _session(); runs = _fake_agent(monkeypatch)
    board.start(sid, "coord")
    _start(sid)
    n = len(runs)
    _start(sid, roles=["radiology"], case_ids=["TB-S1"])  # the brief is still current: reused, not logged twice
    assert len(runs) == n and board.get(sid)["agents"]["TB-S1"]["radiology"]["reused"] is True
    assert sum(e["kind"] == "brief_item" and e["role"] == "radiology" and e["case_id"] == "TB-S1" for e in board.get(sid)["log"]) == 1
    _start(sid, roles=["radiology"], case_ids=["TB-S1"], refresh=True)
    assert runs[-1] == ("TB-S1", "radiology") and board.get(sid)["agents"]["TB-S1"]["radiology"]["reused"] is False
    add("TB-S1", make_doc("Dmri000001", "mri"))  # the Case File changed: the brief is stale and runs again
    _start(sid, roles=["radiology"], case_ids=["TB-S1"])
    assert runs[-1] == ("TB-S1", "radiology") and len(runs) == n + 2


def test_agents_left_waiting_by_a_restart_are_shown_as_interrupted(monkeypatch):
    sid = _session()
    board.start(sid, "coord")
    board.set_agent(sid, "TB-S1", "radiology", "running")
    s = service.session_interrupted(sid)
    assert s["agents"]["TB-S1"]["radiology"]["status"] == "error" and "server restart" in s["agents"]["TB-S1"]["radiology"]["message"]


def test_protected_case_never_prepared(monkeypatch):
    sid = _session(); runs = _fake_agent(monkeypatch)
    monkeypatch.setattr(service.config, "PROTECTED_CASES", {"TB-S2"})
    board.start(sid, "coord")
    _start(sid)
    assert {c for c, _ in runs} == {"TB-S1"}


def test_only_a_brief_the_agent_would_write_now_is_reused(monkeypatch):
    """Phase 6 review: a brief written with a focus question, with near-match on, or in an older format is prepared again."""
    sid = _session(); runs = _fake_agent(monkeypatch)
    board.start(sid, "coord")
    _start(sid, roles=["radiology"], case_ids=["TB-S1"])
    n = len(runs)
    for change in ({"focus": "only the nodes"}, {"near_match": True}, {"version": 1}):
        st = store.get_state("TB-S1"); st["artefacts"]["brief_radiology"].update(change); store.save_state("TB-S1", st)
        _start(sid, roles=["radiology"], case_ids=["TB-S1"])
        assert len(runs) == n + 1, change
        n = len(runs)


def test_closing_while_briefs_are_prepared_cancels_them_and_the_room_still_loads(monkeypatch):
    """Phase 6 review S3: close during preparation -> the waiting agents show an error, no task keeps running, and loading the session
    (session_interrupted) never raises."""
    sid = _session()
    started = []

    async def slow(case_id, role, focus="", max_steps=5):
        started.append((case_id, role))
        await asyncio.sleep(30)
        yield {"type": "brief", "brief": {}}
    monkeypatch.setattr(agents, "run_agent", slow)
    board.start(sid, "coord")

    async def go():
        service.prepare_session_agents(sid, "coord")
        await asyncio.sleep(0.05)
        service.close_session(sid, "coord")
        await asyncio.sleep(0.05)
    asyncio.run(go())
    s = service.session_interrupted(sid)
    assert started and s["status"] == "closed" and not service.SESSION_TASKS.get(sid)
    assert {x["status"] for by in s["agents"].values() for x in by.values()} == {"error"}


def test_live_prompt_says_the_agent_answers_questions():
    p = agents._live_system("radiology")
    assert "prepare a specialty-specific brief" not in p and "answer the multidisciplinary team's questions" in p
