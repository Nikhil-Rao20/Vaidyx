"""Weekly series (meetings-v2 item 3.1, T6): the MDT Coordinator plans a Tumour Board every week; the series makes the next four weeks of
meetings (today when its time has not passed) on create, edit and resume and every day from the scheduler, never twice for one date and
never again for a date skipped (cancelled) or moved by hand; an edit changes the future planned meetings except what was changed by hand
on one; pause and stop (empty future meetings cancelled, those with Case Files kept and listed); a one-off meeting stays as it is.
Hermetic: the meeting test app (fake logins, synthetic TB-001..003), no model call."""
from datetime import date, datetime, timedelta

import pytest

from tumour_board import board, meetings, org, ready_hook, scheduler, steps, store
from tumour_board.tests.test_nik_meetings import As, app, new_meeting, owned, tc  # noqa: F401

TOMORROW = date.today() + timedelta(days=1)
WD = TOMORROW.weekday()  # a weekday whose first date is tomorrow: no edge at today's time


def _plus(d: date, n: int) -> str:
    return (d + timedelta(days=n)).isoformat()


def make(tc, **body):
    r = As(tc, "anil").post("/meeting-series", json={"weekday": WD, "time": "10:00", "room": "Seminar hall (synthetic)", **body})
    assert r.status_code == 200, r.text
    return r.json()


def mine(sid, status=None):
    return [s for s in meetings.series_meetings(sid) if status is None or s.get("status") == status]


def audit_kinds(sid):
    return [e["kind"] for e in board.read_audit() if e.get("session") == sid]


# ---- create ---------------------------------------------------------------------------------------------------------------------------

def test_create_makes_the_next_four_weeks(tc):
    j = make(tc, title="Weekly Tumour Board", video=True, minutes_per_case=12)
    ser = j["series"]
    assert ser["weekday"] == WD and ser["time"] == "10:00" and ser["status"] == "active" and ser["active"] is True
    assert ser["label"] == f"Every week on {meetings.WEEKDAY_NAMES[WD]} at 10:00" and ser["weekday_name"] == meetings.WEEKDAY_NAMES[WD]
    assert ser["id"].startswith("W") and ser["created_by"] == "anil" and ser["created_at"] and ser["updated_at"]
    assert len(j["made"]) == 4 and [m["id"] for m in ser["meetings"]] == j["made"]
    assert [m["date"] for m in ser["meetings"]] == [_plus(TOMORROW, 7 * i) for i in range(4)]
    for m in ser["meetings"]:
        assert m["series_id"] == ser["id"] and m["series_date"] == m["date"] and m["time"] == "10:00" and m["room"] == "Seminar hall (synthetic)"
        assert m["video"] is True and m["minutes_per_case"] == 12 and m["title"] == "Weekly Tumour Board" and m["status"] == "planned"
        assert audit_kinds(m["id"]) == ["created", "series_meeting_made"]
    assert audit_kinds(ser["id"]) == ["series_created"]
    r = As(tc, "anil").get("/meeting-series")
    assert r.status_code == 200 and [x["id"] for x in r.json()["series"]] == [ser["id"]] and r.json()["weekdays"][0] == "Monday"
    one_off = new_meeting(tc, date_=_plus(TOMORROW, 2))  # an extra meeting stays one-off
    row = next(x for x in As(tc, "anil").get("/meetings").json()["meetings"] if x["id"] == one_off)
    assert row["series_id"] == "" and row["series_date"] == ""


def test_today_counts_only_when_its_time_has_not_passed():
    fri = datetime(2026, 11, 6, 9, 30)  # a Friday (synthetic clock)
    assert meetings._slot_dates(4, "10:00", fri) == ["2026-11-06", "2026-11-13", "2026-11-20", "2026-11-27"]
    assert meetings._slot_dates(4, "09:30", fri)[0] == "2026-11-13" and meetings._slot_dates(4, "08:00", fri)[0] == "2026-11-13"
    assert meetings._slot_dates(0, "10:00", fri) == ["2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30"]


def test_today_with_its_time_passed_is_not_made(tc):
    j = make(tc, weekday=date.today().weekday(), time="00:00")
    assert [m["date"] for m in j["series"]["meetings"]] == [_plus(date.today(), 7 * i) for i in range(1, 5)]


def test_only_the_coordinator(tc):
    sid = make(tc)["series"]["id"]
    for user in ("priya", "suresh"):
        a = As(tc, user)
        assert a.get("/meeting-series").status_code == 403
        assert a.post("/meeting-series", json={"weekday": 1, "time": "09:00"}).status_code == 403
        assert a.put(f"/meeting-series/{sid}", json={"time": "09:00"}).status_code == 403
        for act in ("pause", "resume", "stop"):
            assert a.post(f"/meeting-series/{sid}/{act}").status_code == 403
    assert meetings.get_series(sid)["active"] is True


@pytest.mark.parametrize("body,code", [({"weekday": 7}, "bad_weekday"), ({"weekday": "someday"}, "bad_weekday"), ({"weekday": True}, "bad_weekday"),
                                       ({"time": "9am"}, "bad_time"), ({"minutes_per_case": 0}, "bad_minutes"), ({"title": "x" * 201}, "bad_title")])
def test_bad_fields_are_refused(tc, body, code):
    r = As(tc, "anil").post("/meeting-series", json={"weekday": WD, "time": "10:00", **body})
    assert r.status_code == 400 and r.json()["detail"]["code"] == code
    assert meetings.list_series() == []


def test_the_weekday_by_name_the_time_from_the_defaults_and_a_missing_time(tc):
    r = As(tc, "anil").post("/meeting-series", json={"weekday": "Friday"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "time_needed"  # no time given, none in the hospital settings
    o = org.load(); o["hospital"]["meeting_defaults"] = {"time": "14:00", "room": "Oncology seminar room", "minutes_per_case": 15}; org.save(o, by="test")
    r = As(tc, "anil").post("/meeting-series", json={"weekday": "Friday"})
    assert r.status_code == 200, r.text
    ser = r.json()["series"]
    assert ser["weekday"] == 4 and ser["time"] == "14:00" and ser["room"] == "Oncology seminar room" and ser["minutes_per_case"] == 15
    assert As(tc, "anil").post("/meeting-series", json=["Friday"]).status_code == 400


def test_a_duplicate_series_is_refused(tc):
    make(tc)
    r = As(tc, "anil").post("/meeting-series", json={"weekday": WD, "time": "10:00", "room": "Seminar hall (synthetic)"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "duplicate"
    assert As(tc, "anil").post("/meeting-series", json={"weekday": WD, "time": "10:00", "room": "Room 2"}).status_code == 200  # another room


def test_an_unknown_series_is_404(tc):
    for path in ("/meeting-series/W00000000/pause", "/meeting-series/nope/stop"):
        assert As(tc, "anil").post(path).status_code == 404
    assert As(tc, "anil").put("/meeting-series/W00000000", json={"time": "09:00"}).status_code == 404


# ---- the daily job ------------------------------------------------------------------------------------------------------------------

def test_the_job_never_makes_a_date_twice_and_keeps_four_weeks_ahead(tc, monkeypatch):
    monkeypatch.setattr(scheduler, "_state", {"last_tick": None, "last_jobs": {}, "started": None, "ticks": 0})  # this test's own tick state
    sid = make(tc)["series"]["id"]
    assert "series" in scheduler.QUICK and any(n == "series" and e == scheduler.SERIES_EVERY for n, _, e in scheduler.JOBS)
    out = scheduler.tick(force=True, only={"series"})
    assert out["series"] == {"made": {}} and len(mine(sid)) == 4
    a_week_on = datetime.now() + timedelta(days=7)
    out = meetings.series_job(a_week_on)  # a week later the window has moved on by one date
    assert list(out["made"]) == [sid] and len(out["made"][sid]) == 1
    assert sorted(s["date"] for s in mine(sid)) == [_plus(TOMORROW, 7 * i) for i in range(5)]
    made = meetings.get(out["made"][sid][0])
    assert made["created_by"] == meetings.AUTOMATIC and audit_kinds(made["id"]) == ["created", "series_meeting_made"]
    assert meetings.series_job(a_week_on) == {"made": {}}


def test_a_skipped_or_moved_date_is_never_made_again(tc):
    j = make(tc)
    sid, ms = j["series"]["id"], j["series"]["meetings"]
    assert As(tc, "anil").post(f"/meetings/{ms[0]['id']}/cancel", json={"reason": "Holiday (synthetic)"}).status_code == 200  # skip one date
    r = As(tc, "anil").put(f"/meetings/{ms[1]['id']}", json={"date": _plus(TOMORROW, 8)})  # move one date
    assert r.status_code == 200 and r.json()["meeting"]["series_date"] == ms[1]["date"]
    assert meetings.get(ms[1]["id"])["series_hand"] == ["date"]
    assert meetings.series_job() == {"made": {}} and len(mine(sid)) == 4
    assert [s["date"] for s in mine(sid, "planned")] == [_plus(TOMORROW, 8), ms[2]["date"], ms[3]["date"]]


def test_a_case_file_waiting_for_a_meeting_joins_the_first_meeting_the_series_makes(tc, monkeypatch):
    monkeypatch.setattr(steps, "open_count", lambda case_id: 0)
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: {"scheduled": False, "how": "off"})
    owned("TB-002")
    c = store.get_case("TB-002"); c["board_question"] = "Surgery first? (synthetic)"; store.save_case(c)
    r = As(tc, "priya").post("/cases/TB-002/ready", json={"ready": True})
    assert r.status_code == 200 and r.json()["send"]["meeting_id"] == "" and "board_waiting" in store.get_case("TB-002")
    ms = make(tc)["series"]["meetings"]
    assert ms[0]["counts"]["discussion"] == 1 and all(m["counts"]["discussion"] == 0 for m in ms[1:])
    assert store.get_case("TB-002")["meeting_id"] == ms[0]["id"] and "board_waiting" not in store.get_case("TB-002")


# ---- edit ----------------------------------------------------------------------------------------------------------------------------

def test_an_edit_changes_the_future_meetings_except_what_was_changed_by_hand(tc):
    j = make(tc)
    sid, ms = j["series"]["id"], j["series"]["meetings"]
    As(tc, "anil").put(f"/meetings/{ms[1]['id']}", json={"room": "Room 9 (synthetic)"})  # one meeting's room changed by hand
    As(tc, "anil").post(f"/meetings/{ms[2]['id']}/cancel")
    r = As(tc, "anil").put(f"/meeting-series/{sid}", json={"time": "11:30", "room": "Board room 1", "minutes_per_case": 9, "title": "MDT"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["series"]["time"] == "11:30" and j["series"]["room"] == "Board room 1" and j["made"] == [] and j["cancelled"] == []
    assert sorted(j["changed"]) == sorted([ms[0]["id"], ms[1]["id"], ms[3]["id"]])
    m0, m1, m2 = meetings.get(ms[0]["id"]), meetings.get(ms[1]["id"]), meetings.get(ms[2]["id"])
    assert (m0["time"], m0["room"], m0["minutes_per_case"], m0["title"]) == ("11:30", "Board room 1", 9, "MDT")
    assert (m1["time"], m1["room"]) == ("11:30", "Room 9 (synthetic)")  # the room changed by hand stays
    assert m2["status"] == "cancelled" and m2["time"] == "10:00"  # a skipped date is left alone
    assert m0["series_hand"] == [] and m1["series_hand"] == ["room"]  # the series edit is not a change by hand
    ev = [e for e in board.read_audit() if e.get("session") == ms[0]["id"] and e["kind"] == "meeting_updated"]
    assert ev[-1]["by_series"] == sid and ev[-1]["time"] == "11:30"
    se = [e for e in board.read_audit() if e.get("session") == sid and e["kind"] == "series_updated"]
    assert se and se[-1]["time"] == "11:30" and se[-1]["minutes_per_case"] == 9
    assert As(tc, "anil").put(f"/meeting-series/{sid}", json={"time": "11:30"}).json()["changed"] == []  # nothing new: no change, no audit
    assert len([e for e in board.read_audit() if e.get("session") == sid and e["kind"] == "series_updated"]) == 1
    assert As(tc, "anil").put(f"/meeting-series/{sid}", json={"time": "noon"}).json()["detail"]["code"] == "bad_time"


def test_a_new_weekday_moves_the_future_meetings_in_order_and_their_case_files_follow(tc):
    j = make(tc)
    sid, ms = j["series"]["id"], j["series"]["meetings"]
    As(tc, "anil").put(f"/meetings/{ms[0]['id']}/agenda", json={"discussion": ["TB-001"], "noting": []})
    As(tc, "anil").put(f"/meetings/{ms[3]['id']}", json={"date": _plus(TOMORROW, 22)})  # moved by hand: stays where it is
    new_wd = (WD + 2) % 7
    r = As(tc, "anil").put(f"/meeting-series/{sid}", json={"weekday": new_wd})
    assert r.status_code == 200, r.text
    j = r.json()
    slots = meetings._slot_dates(new_wd, "10:00")
    after = {s["id"]: s for s in mine(sid)}
    assert [after[m["id"]]["date"] for m in ms[:3]] == slots[:3]
    assert all(after[m["id"]]["series_date"] == after[m["id"]]["date"] for m in ms[:3])
    assert after[ms[3]["id"]]["date"] == _plus(TOMORROW, 22)
    assert sorted(j["changed"]) == sorted(m["id"] for m in ms[:3]) and j["cancelled"] == []
    assert len(j["made"]) == 1 and meetings.get(j["made"][0])["date"] == slots[3]
    assert store.get_case("TB-001")["board_date"] == slots[0]  # the Case File on the first meeting follows it
    assert meetings.series_job() == {"made": {}}


# ---- pause, resume, stop --------------------------------------------------------------------------------------------------------------

def test_pause_makes_nothing_and_resume_catches_up(tc):
    sid = make(tc)["series"]["id"]
    r = As(tc, "anil").post(f"/meeting-series/{sid}/pause")
    assert r.status_code == 200 and r.json()["series"]["status"] == "paused" and r.json()["series"]["paused"]["by"] == "anil"
    assert As(tc, "anil").post(f"/meeting-series/{sid}/pause").status_code == 200  # a second pause changes nothing
    later = datetime.now() + timedelta(days=14)
    assert meetings.series_job(later) == {"made": {}} and len(mine(sid)) == 4
    r = As(tc, "anil").put(f"/meeting-series/{sid}", json={"room": "Room 3"})  # a paused series can be edited
    assert r.status_code == 200 and r.json()["made"] == []
    r = As(tc, "anil").post(f"/meeting-series/{sid}/resume")
    assert r.status_code == 200 and r.json()["series"]["status"] == "active" and r.json()["series"]["paused"] is None and r.json()["made"] == []
    assert len(meetings.series_job(later)["made"][sid]) == 2
    assert audit_kinds(sid) == ["series_created", "series_paused", "series_updated", "series_resumed"]


def test_stop_cancels_the_empty_future_meetings_and_keeps_those_with_case_files(tc):
    j = make(tc)
    sid, ms = j["series"]["id"], j["series"]["meetings"]
    As(tc, "anil").put(f"/meetings/{ms[1]['id']}/agenda", json={"discussion": ["TB-002"], "noting": []})
    r = As(tc, "anil").post(f"/meeting-series/{sid}/stop")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["series"]["status"] == "stopped" and j["series"]["active"] is False and j["series"]["stopped"]["by"] == "anil"
    assert sorted(j["cancelled"]) == sorted([ms[0]["id"], ms[2]["id"], ms[3]["id"]]) and [x["id"] for x in j["kept"]] == [ms[1]["id"]]
    assert j["kept"][0]["counts"]["discussion"] == 1 and meetings.get(ms[1]["id"])["status"] == "planned"
    assert all(meetings.get(m)["cancelled"]["reason"] == "series stopped" for m in j["cancelled"])
    ev = [e for e in board.read_audit() if e.get("session") == sid and e["kind"] == "series_stopped"]
    assert ev and ev[0]["kept"] == [ms[1]["id"]]
    for act in ("resume", "pause", "stop"):
        r = As(tc, "anil").post(f"/meeting-series/{sid}/{act}")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "stopped"
    assert As(tc, "anil").put(f"/meeting-series/{sid}", json={"time": "09:00"}).json()["detail"]["code"] == "stopped"
    assert meetings.series_job(datetime.now() + timedelta(days=14)) == {"made": {}}
    j2 = make(tc)  # a stopped series does not block a new one at the same time
    assert j2["series"]["status"] == "active"
