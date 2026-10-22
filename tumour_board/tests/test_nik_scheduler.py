"""The scheduler (B3): the tick runs the due jobs with fakes: automatic reminders (one per request per day, by "Vaidyx (automatic)"),
digests at the person's digest time (once a day), code expiry, the meeting_starting notice, the re-fetch (on the app's event loop,
skipped while a meeting is in session or before the loop is known), the jobs on the app's loop, the state file, start() / stop() and
the guards."""
import asyncio, json, os, threading, time
from datetime import date, datetime, timedelta

import pytest

from tumour_board import board, config, dept_requests, his_case, meetings, notify, org, push, scheduler, store
from tumour_board.tests import util
from tumour_board.tests.test_nik_meetings import hospital_org


@pytest.fixture(autouse=True)
def clean(data_root, monkeypatch):
    monkeypatch.setenv("TB_SCHEDULER", "0")
    monkeypatch.setattr(push, "ASYNC", False)
    scheduler.stop()
    scheduler._state.clear(); scheduler._state.update({"last_tick": None, "last_jobs": {}, "started": None, "ticks": 0})
    scheduler._refetch.update({"future": None, "started": None, "collected": True})
    monkeypatch.setattr(scheduler, "_LOOP", None)
    from tumour_board import live
    monkeypatch.setattr(live.hub, "loop", None)
    org.save(hospital_org(), by="test")
    yield
    scheduler.stop()


def _request(case_id="TB-R1", due=None, done=False, sent=True):
    if not store.get_case(case_id):
        store.create_case(case_id, util.PATIENT, "lung_nsclc", created_by="priya")
        c = store.get_case(case_id); c["department"] = "breast_surgery"; store.save_case(c)
    st = store.get_state(case_id)
    a = {"id": "A" + str(len(st["actions"]) + 1), "source": "pre_authorization", "requirement": "ct_thorax", "label": "CT thorax report", "department": "Radiology",
         "department_id": "radiology", "level": 1, "level_label": "", "what": "Diagnostic CT thorax report", "status": "pending", "created": store.now_iso(),
         "due": (due or date.today() - timedelta(days=1)).isoformat(), "sla_days": 3, "history": []}
    if sent:
        a["sent"] = {"by": "priya", "at": "2026-10-10T09:00:00", "to": "radiology", "count": 1}
    if done:
        a["done"] = {"by": "ravi", "at": store.now_iso(), "note": "signed"}
    st["actions"].append(a)
    store.save_state(case_id, st)
    return a["id"]


def _kinds(user):
    return [n["kind"] for n in notify.for_roles(org.roles(user), limit=None)]


def test_automatic_reminders_once_per_request_per_day():
    due = _request()                       # due yesterday, unanswered: reminded
    today = _request(due=date.today())     # due today: reminded
    future = _request(due=date.today() + timedelta(days=2))  # not yet
    answered = _request(done=True)         # answered with "done": not reminded
    unsent = _request(sent=False)          # a V1-style pending request without a sent record counts as sent (is_sent); fine, reminded
    out = scheduler.tick(force=True, only={"reminders"})
    sent = out["reminders"]["sent"]
    assert f"TB-R1:{due}" in sent and f"TB-R1:{today}" in sent and f"TB-R1:{future}" not in sent and f"TB-R1:{answered}" not in sent and f"TB-R1:{unsent}" in sent
    ns = [n for n in notify.for_roles(org.roles("ravi"), limit=None) if n["kind"] == "reminder_automatic"]
    assert len(ns) == 3 and all(n["sent_by"] == "Vaidyx (automatic)" and n["automatic"] is True for n in ns) and "was due" in ns[0]["text"]
    st = store.get_state("TB-R1")
    a = next(x for x in st["actions"] if x["id"] == due)
    assert a["reminders"][0]["by"] == "Vaidyx (automatic)" and a["reminders"][0]["automatic"] is True and "Automatic reminder" in a["history"][-1]["event"]
    ev = [e for e in store.read_audit("TB-R1") if e["kind"] == "request_reminded"]
    assert len(ev) == 3 and all(e["by"] == "Vaidyx (automatic)" and e["automatic"] for e in ev)
    # the same day again: nothing more; the next day: again
    assert scheduler.tick(force=True, only={"reminders"})["reminders"]["sent"] == []
    later = datetime.now() + timedelta(days=2)
    assert len(scheduler.tick(now=later, force=True, only={"reminders"})["reminders"]["sent"]) == 4  # the future one is due by then
    assert dept_requests.remind_automatic("TB-R1", "Anope") is None and dept_requests.remind_automatic("TB-nope", "A1") is None
    # a reminder sent by a person today does not stop the automatic one (it is its own record), but a closed request is never reminded
    a["status"] = "completed"; store.save_state("TB-R1", st)
    assert dept_requests.remind_automatic("TB-R1", due, today=date.today() + timedelta(days=3)) is None
    # the reminders job is paced: not due again within ten minutes unless forced
    assert "reminders" not in scheduler.tick(only={"reminders"})


def test_digests_once_a_day_at_the_digest_time():
    notify.notify({"department": "radiology"}, "request", "TB-001", "CT needed", "")
    notify.notify({"department": "radiology"}, "request_reminder", "TB-001", "Reminder", "")
    notify.notify({"user": "priya"}, "outcome", "TB-002", "Outcome", "")
    push.set_prefs("priya", {"digest_time": "09:30"})
    out = scheduler.tick(now=datetime(2026, 10, 18, 8, 5), force=True, only={"digests"})
    assert sorted(out["digests"]["sent"]) == ["ravi", "suresh"]  # priya's digest is at 09:30; anil has nothing unread
    d = [n for n in notify.for_roles(org.roles("ravi"), limit=None) if n["kind"] == "digest"]
    assert len(d) == 1 and d[0]["title"] == "Your digest: 2 unread notification(s)" and "1 request reminder" in d[0]["text"] and d[0]["by"] == "Vaidyx (automatic)"
    assert scheduler.tick(now=datetime(2026, 10, 18, 8, 6), force=True, only={"digests"})["digests"]["sent"] == []  # once a day
    assert scheduler.tick(now=datetime(2026, 10, 18, 9, 30), force=True, only={"digests"})["digests"]["sent"] == ["priya"]
    assert scheduler.tick(now=datetime(2026, 10, 19, 7, 0), force=True, only={"digests"})["digests"]["sent"] == []  # before the time
    notify.mark_read(org.roles("ravi"))
    assert scheduler.tick(now=datetime(2026, 10, 19, 8, 0), force=True, only={"digests"})["digests"]["sent"] == ["suresh"]  # nothing unread for ravi
    state = json.loads((config.DATA_ROOT / "scheduler.json").read_text())
    done = state["last_jobs"]["digests"]["result"]["done_on"]  # everyone looked at on the 19th (from their digest time on), digest or not
    assert done["suresh"] == done["ravi"] == "2026-10-19" and "priya" not in done and state["last_tick"].startswith("2026-10-19T08:00")
    assert scheduler.tick(now=datetime(2026, 10, 19, 8, 30), force=True, only={"digests"})["digests"]["sent"] == []  # looked at once a day


def test_codes_expire_and_meetings_are_announced():
    s = board.new_session("2026-10-18", "anil", time="10:30", room="Room 2")
    s["code"] = {"value": "123456", "expires_at": "2026-10-18T09:00:00", "attempts": 0}
    board.save_session(s)
    s2 = board.new_session("2026-10-18", "anil", time="14:00")
    s2["code"] = {"value": "654321", "expires_at": "2026-10-18T23:00:00", "attempts": 0}
    board.save_session(s2)
    s3 = board.new_session("2026-10-18", "anil", time="10:40")
    s3["status"] = "cancelled"; board.save_session(s3)
    out = scheduler.tick(now=datetime(2026, 10, 18, 10, 20), force=True, only={"codes", "meeting_starting"})
    assert out["codes"]["expired"] == [s["id"]] and board.get(s["id"])["code"] is None and board.get(s2["id"])["code"]["value"] == "654321"
    assert out["meeting_starting"]["announced"] == [s["id"]]  # 10:30 is within 15 minutes; 14:00 is not; the cancelled one never
    ns = [n for n in notify.for_roles(org.roles("ravi"), limit=None) if n["kind"] == "meeting_starting"]
    assert len(ns) == 1 and ns[0]["title"] == "Tumour Board starts at 10:30 in Room 2" and ns[0]["meeting_id"] == s["id"]
    assert "meeting_starting" in _kinds("anil")
    assert scheduler.tick(now=datetime(2026, 10, 18, 10, 25), force=True, only={"meeting_starting"})["meeting_starting"]["announced"] == []  # once
    assert "code_expired" in [e["kind"] for e in board.read_audit() if e["session"] == s["id"]]
    assert scheduler.tick(now=datetime(2026, 10, 18, 13, 50), force=True, only={"meeting_starting"})["meeting_starting"]["announced"] == [s2["id"]]


def test_refetch_runs_on_the_app_loop_and_skips_during_a_meeting(monkeypatch):
    calls = []

    async def fake_all(user, skip=(), wait=True):
        calls.append({"user": user, "skip": set(skip), "wait": wait, "loop": asyncio.get_running_loop()})
        return {"TB-H1": {"job": "J1", "added": 1, "updated": 0}}
    monkeypatch.setattr(his_case, "refetch_all_active", fake_all)
    # before the app's loop is known nothing starts (the model client belongs to that loop) and the next tick tries again
    assert scheduler.tick(force=True, only={"refetch"})["refetch"]["skipped"].startswith("waiting") and "refetch" not in scheduler.status()["last_jobs"]
    assert scheduler.status()["app_loop"] is False
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True, name="fake-app-loop")
    t.start()

    async def attach():
        scheduler.attach_loop()
    try:
        asyncio.run_coroutine_threadsafe(attach(), loop).result(2)  # what a route or the bell does on the app's loop
        assert scheduler.app_loop() is loop and scheduler.status()["app_loop"] is True
        from tumour_board import service
        service.JOBS["Jx"] = {"id": "Jx", "case_id": "TB-H2", "state": "running"}
        try:
            out = scheduler.tick(force=True, only={"refetch"})
            assert "started" in out["refetch"]
            scheduler._refetch["future"].result(2)
        finally:
            service.JOBS.pop("Jx", None)
        assert calls[0]["user"] == "Vaidyx (automatic)" and calls[0]["skip"] == {"TB-H2"} and calls[0]["wait"] is True and calls[0]["loop"] is loop
        scheduler.tick(only=set())  # the next tick collects the finished run
        assert scheduler.status()["last_jobs"]["refetch_done"]["result"]["cases"] == {"TB-H1": {"job": "J1", "added": 1, "updated": 0}}
        s = board.new_session("2026-10-18", "anil"); board.start(s["id"], "anil")
        assert scheduler.tick(force=True, only={"refetch"})["refetch"] == {"skipped": "a meeting is in session"} and len(calls) == 1
        board.close(s["id"], "anil")
        assert "refetch" not in scheduler.tick(only={"refetch"})  # paced: every 30 minutes
        assert "refetch" not in scheduler.tick(force=True, only={"refetch"}, refetch=False)
        scheduler.tick(force=True, only={"refetch"})
        scheduler._refetch["future"].result(2)
        assert len(calls) == 2
        # the quick jobs run on the app's loop as well (the stores are changed there only)
        seen = []
        monkeypatch.setattr(scheduler, "JOBS", (("codes", lambda now: seen.append(threading.current_thread().name) or {"expired": []}, 0),))
        assert scheduler.tick(force=True) == {"codes": {"expired": []}} and seen == ["fake-app-loop"]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(2)
        loop.close()
    assert scheduler.app_loop() is None  # a stopped loop is never used


def test_active_his_cases_and_refetch_all_active(monkeypatch):
    store.create_case("TB-H1", util.PATIENT, "lung_nsclc", created_by="priya")
    store.create_case("TB-H2", util.PATIENT, "lung_nsclc", created_by="priya")
    store.create_case("TB-H3", util.PATIENT, "lung_nsclc", created_by="priya")
    store.create_case("TB-H4", util.PATIENT, "lung_nsclc", created_by="priya")
    store.create_case("TB-M1", util.PATIENT, "lung_nsclc", created_by="priya")  # manual: no HIS
    for cid in ("TB-H1", "TB-H2", "TB-H3", "TB-H4"):
        c = store.get_case(cid); c["his"] = {"patient_id": "p1", "uhid": "VXH/1", "watermark": ""}; store.save_case(c)
    c = store.get_case("TB-H2"); c["archived"] = {"by": "priya", "at": "x"}; store.save_case(c)
    st = store.get_state("TB-H3"); st["board_records"] = [{"id": "B1", "outcome_type": "decision"}]; store.save_state("TB-H3", st)
    st = store.get_state("TB-H4"); st["board_records"] = [{"id": "B2", "outcome_type": "deferred"}]; store.save_state("TB-H4", st)
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-H4"})
    assert his_case.active_his_cases() == ["TB-H1"]
    monkeypatch.setattr(config, "PROTECTED_CASES", set())
    assert his_case.active_his_cases() == ["TB-H1", "TB-H4"]  # a deferred Case File stays active; a decided one does not
    fetched = []

    async def fake_refetch(cid, user):
        fetched.append((cid, user))
        if cid == "TB-H4":
            raise his_case.HISCaseError("The hospital system did not answer", 502)
        fut = asyncio.get_running_loop().create_future(); fut.set_result(None)
        return {"id": "J9", "task": fut, "his": {"added": 2, "updated": 1}}
    monkeypatch.setattr(his_case, "refetch", fake_refetch)
    out = asyncio.run(his_case.refetch_all_active(skip=()))
    assert fetched == [("TB-H1", "Vaidyx (automatic)"), ("TB-H4", "Vaidyx (automatic)")]
    assert out == {"TB-H1": {"job": "J9", "added": 2, "updated": 1}, "TB-H4": {"error": "The hospital system did not answer"}}
    assert asyncio.run(his_case.refetch_all_active(skip=("TB-H1",)))["TB-H1"] == {"skipped": "job running"}

    async def no_his(cid, user):
        raise his_case.HISCaseError("No hospital information system is configured (Organisation: HIS connection)", 409)
    monkeypatch.setattr(his_case, "refetch", no_his)
    assert list(asyncio.run(his_case.refetch_all_active())) == ["TB-H1"]  # stops after the first: nothing to fetch from


def test_tick_never_raises_and_prune_is_daily(monkeypatch):
    def boom(now):
        raise RuntimeError("disk full")
    monkeypatch.setattr(scheduler, "JOBS", (("codes", boom, 0), ("prune", scheduler.job_prune, scheduler.PRUNE_EVERY)))
    out = scheduler.tick(force=True)
    assert out["codes"] == {"error": "RuntimeError: disk full"} and out["prune"] == {"dropped": 0}
    assert scheduler.tick() == {"codes": {"error": "RuntimeError: disk full"}}  # prune waits a day; codes every tick
    st = scheduler.status()
    assert st["running"] is False and st["ticks"] == 2 and st["last_jobs"]["prune"]["result"] == {"dropped": 0} and st["by"] == "Vaidyx (automatic)"


def test_start_and_stop_the_thread(monkeypatch):
    assert scheduler.start() is False  # TB_SCHEDULER=0
    monkeypatch.setenv("TB_SCHEDULER", "1")
    monkeypatch.setenv("TB_SCHEDULER_INTERVAL", "0.05")
    ticks = []
    monkeypatch.setattr(scheduler, "tick", lambda *a, **k: ticks.append(time.time()) or {})
    assert scheduler.start() is True and scheduler.start() is True and scheduler.running()
    for _ in range(100):
        if len(ticks) >= 2:
            break
        time.sleep(0.02)
    assert len(ticks) >= 2 and scheduler.status()["running"] is True and scheduler.status()["interval_seconds"] == 0.05
    scheduler.stop()
    assert scheduler.running() is False
    n = len(ticks); time.sleep(0.12)
    assert len(ticks) == n
    monkeypatch.delenv("TB_SCHEDULER")  # under pytest without TB_SCHEDULER=1 the thread never starts
    assert scheduler.start() is False and scheduler.running() is False


def test_route_setup_does_not_start_the_scheduler_in_tests(monkeypatch):
    monkeypatch.setenv("TB_SCHEDULER", "0")
    from routes.tumour_board_routes import setup_tumour_board_routes
    setup_tumour_board_routes()
    assert scheduler.running() is False
