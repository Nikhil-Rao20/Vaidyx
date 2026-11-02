"""The agenda fills itself (meetings-v2 item 3.2, D8) and the API check's leftovers (notes 8 and 9): a Case File sent to the board without
a meeting goes on the next open meeting (planned, not cancelled, not past its time), else it waits and joins the first meeting made later;
a list is in urgency order (5 first), then by the time sent, until the coordinator arranges it by hand (then new Case Files go at its end,
marked new); a cancelled meeting's Case Files go to the next meeting after it, else back to waiting, each owner told; a Case File moved by
"Not discussed" keeps a ready mark. Hermetic: the meeting test app (fake logins, synthetic TB-001..003), no model call."""
from datetime import date, datetime, timedelta

import pytest

from tumour_board import board, meetings, notify, org, ready_hook, steps, store
from tumour_board.tests.test_nik_meetings import As, app, new_meeting, owned, started, tc, with_agenda  # noqa: F401

QUESTION = "Which treatment pathway should the board consider? (synthetic)"


def _day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


@pytest.fixture
def docs(app, monkeypatch):
    """TB-001..003 owned by Breast Surgery (Dr Priya Nair), each with its question for the board; nothing open; the ready hook off."""
    monkeypatch.setattr(steps, "open_count", lambda case_id: 0)
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: {"scheduled": False, "how": "off"})
    for cid in ("TB-001", "TB-002", "TB-003"):
        owned(cid)
        c = store.get_case(cid)
        c["board_question"] = QUESTION
        store.save_case(c)
    return ("TB-001", "TB-002", "TB-003")


@pytest.fixture
def clock(monkeypatch):
    """store.now_iso one second further on each call, so two sends never share a second (the order rule's tie-break is the send time)."""
    t = {"n": 0}
    base = datetime.now().replace(microsecond=0)

    def now_iso():
        t["n"] += 1
        return (base + timedelta(seconds=t["n"])).isoformat(timespec="seconds")
    monkeypatch.setattr(store, "now_iso", now_iso)


def send(tc, cid, **body):
    r = As(tc, "priya").post(f"/cases/{cid}/ready", json={"ready": True, **body})
    assert r.status_code == 200, r.text
    return r.json()


def urgency(cid, level):
    c = store.get_case(cid)
    c["urgency"] = {"level": level, "set_by": "priya", "at": store.now_iso(), "note": ""}
    store.save_case(c)


def ids(tc, mid, lst="discussion"):
    return [x["case_id"] for x in As(tc, "anil").get(f"/meetings/{mid}").json()["agenda"][lst]]


def notes(user, kind, cid=None):
    return [n for n in notify.for_roles(org.roles(user), limit=None) if n["kind"] == kind and (cid is None or n["case_id"] == cid)]


# ---- a send without a meeting --------------------------------------------------------------------------------------------------------

def test_a_send_without_a_meeting_goes_on_the_next_open_meeting(tc, docs):
    later = new_meeting(tc, date_=_day(8), time_="09:00")
    first = new_meeting(tc, date_=_day(1), time_="10:30")
    j = send(tc, "TB-002", list="noting")
    assert j["send"]["meeting_id"] == first and j["send"]["auto"] is True  # the doctor's answer says which meeting
    assert ids(tc, first, "noting") == ["TB-002"] and ids(tc, later, "noting") == []
    c = store.get_case("TB-002")
    assert c["meeting_id"] == first and c["board_date"] == _day(1) and "board_waiting" not in c
    n = notes("anil", "board_ready", "TB-002")  # the coordinator is told as before, with the meeting
    assert n and f"{_day(1)[8:10]}/{_day(1)[5:7]}/{_day(1)[:4]} 10:30 (the next planned meeting, chosen by itself)" in n[0]["text"]
    ev = next(e for e in store.read_audit("TB-002") if e.get("kind") == "board_send")
    assert ev["auto"] is True and ev["meeting_id"] == first


def test_a_cancelled_a_past_time_and_a_running_meeting_are_skipped(tc, docs):
    gone = new_meeting(tc, date_=_day(1), time_="08:00")
    As(tc, "anil").post(f"/meetings/{gone}/cancel", json={"reason": "synthetic"})
    past_time = new_meeting(tc, date_=_day(0), time_="00:00")  # today, its time passed: not open
    running = new_meeting(tc, date_=_day(0), time_="")
    assert As(tc, "anil").post(f"/meetings/{running}/start").status_code == 200
    target = new_meeting(tc, date_=_day(3), time_="11:00")
    assert send(tc, "TB-001")["send"]["meeting_id"] == target
    assert meetings.is_open(meetings.get(target)) and not meetings.is_open(meetings.get(past_time)) and not meetings.is_open(meetings.get(running))
    no_time = new_meeting(tc, date_=_day(0), time_="")  # a meeting today with no time counts as open all day
    assert meetings.is_open(meetings.get(no_time))
    assert meetings.next_open_meeting()["id"] == no_time


def test_a_send_again_without_a_meeting_keeps_the_meeting_it_is_on(tc, docs):
    first = new_meeting(tc, date_=_day(1))
    later = new_meeting(tc, date_=_day(8))
    send(tc, "TB-002", meeting_id=later)
    j = send(tc, "TB-002")  # the presenter or the note changed: no meeting chosen
    assert j["send"]["meeting_id"] == later and ids(tc, later) == ["TB-002"] and ids(tc, first) == []


def test_with_no_meeting_it_waits_and_joins_the_first_meeting_made(tc, docs):
    j = send(tc, "TB-002", list="noting")
    assert j["send"]["meeting_id"] == "" and "auto" not in j["send"]
    c = store.get_case("TB-002")
    assert c["board_waiting"]["list"] == "noting" and c["board_waiting"]["why"] == "sent"
    assert "No meeting is planned yet" in notes("anil", "board_ready", "TB-002")[0]["text"]
    stale = new_meeting(tc, date_=_day(0), time_="00:00")  # made for a time already passed: not open, takes nothing
    assert ids(tc, stale, "noting") == [] and "board_waiting" in store.get_case("TB-002")
    mid = new_meeting(tc, date_=_day(2), time_="15:00")
    assert ids(tc, mid, "noting") == ["TB-002"]
    c = store.get_case("TB-002")
    assert "board_waiting" not in c and c["meeting_id"] == mid and c["board_date"] == _day(2) and c["board_send"]["meeting_id"] == mid
    assert c["board_send_history"][-1]["joined"] == mid
    assert any(e.get("kind") == "agenda_joined" and e["meeting_id"] == mid for e in store.read_audit("TB-002"))
    assert [e for e in board.read_audit() if e.get("session") == mid and e["kind"] == "agenda_waiting_joined"]
    told = notes("priya", "agenda", "TB-002")
    assert told and told[0]["title"].startswith("On the meeting of") and "for noting" in told[0]["text"]
    later = new_meeting(tc, date_=_day(5))  # only the first meeting made takes it
    assert ids(tc, later, "noting") == []


def test_a_waiting_case_file_can_be_taken_off_and_then_joins_nothing(tc, docs):
    send(tc, "TB-002")
    r = As(tc, "priya").post("/cases/TB-002/meeting/withdraw", json={"reason": "Biopsy repeat (synthetic)"})
    assert r.status_code == 200, r.text
    assert "board_waiting" not in store.get_case("TB-002")
    mid = new_meeting(tc, date_=_day(2))
    assert ids(tc, mid) == []


def test_taking_the_ready_mark_back_stops_the_wait(tc, docs):
    send(tc, "TB-003")
    r = As(tc, "priya").post("/cases/TB-003/ready", json={"ready": False})
    assert r.status_code == 200 and "board_waiting" not in store.get_case("TB-003")
    assert ids(tc, new_meeting(tc, date_=_day(2))) == []


# ---- the order of a list ---------------------------------------------------------------------------------------------------------------

def test_a_list_is_in_urgency_order_then_by_the_time_sent(tc, docs, clock):
    mid = new_meeting(tc, date_=_day(2))
    urgency("TB-002", 5); urgency("TB-003", 3)
    send(tc, "TB-001"); send(tc, "TB-003"); send(tc, "TB-002")
    assert ids(tc, mid) == ["TB-002", "TB-003", "TB-001"]  # 5 first, no urgency last
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["agenda_order"] == {"discussion": "urgency", "noting": "urgency"}
    assert all(x["new"] is False for x in v["agenda"]["discussion"])
    urgency("TB-001", 3)  # the same urgency as TB-003, sent before it: the earlier send goes first at the next change
    meetings.add_to_agenda(mid, "anil", "TB-002", "noting")
    meetings.add_to_agenda(mid, "anil", "TB-002", "discussion")
    assert ids(tc, mid) == ["TB-002", "TB-001", "TB-003"]


def test_the_time_sent_counts_not_the_time_added(tc, docs):
    mid = new_meeting(tc, date_=_day(2))
    send(tc, "TB-003")
    c = store.get_case("TB-001")  # sent long ago (synthetic), put on the agenda by the coordinator now
    c["board_ready"] = {"by": "priya", "at": "2026-01-05T09:00:00", "note": ""}
    store.save_case(c)
    r = As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-001", "list": "discussion"})
    assert r.status_code == 200
    assert [x["case_id"] for x in r.json()["agenda"]["discussion"]] == ["TB-001", "TB-003"]
    assert r.json()["agenda"]["discussion"][0]["sent_at"] == "2026-01-05T09:00:00"


def test_a_list_arranged_by_hand_keeps_its_order_and_new_ones_go_at_the_end_marked_new(tc, docs, clock):
    mid = new_meeting(tc, date_=_day(2))
    urgency("TB-001", 5)
    send(tc, "TB-001"); send(tc, "TB-002")
    assert ids(tc, mid) == ["TB-001", "TB-002"]
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-002", "TB-001"], "noting": []})
    assert r.status_code == 200 and r.json()["agenda_order"]["discussion"] == "hand" and r.json()["agenda_order"]["noting"] == "urgency"
    ev = [e for e in board.read_audit() if e.get("session") == mid and e["kind"] == "agenda_lists"]
    assert ev[-1]["arranged_by_hand"] == ["discussion"]
    urgency("TB-003", 5)
    send(tc, "TB-003")  # urgent, but the coordinator's order stays: it goes at the end, marked new
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert [x["case_id"] for x in v["agenda"]["discussion"]] == ["TB-002", "TB-001", "TB-003"]
    assert [x["new"] for x in v["agenda"]["discussion"]] == [False, False, True]
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-003", "TB-002", "TB-001"], "noting": []})
    assert [x["new"] for x in r.json()["agenda"]["discussion"]] == [False, False, False]  # the coordinator saw it
    assert [x["case_id"] for x in r.json()["agenda"]["discussion"]] == ["TB-003", "TB-002", "TB-001"]
    r = As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-002", "list": "discussion", "reason": "again"})
    assert [x["case_id"] for x in r.json()["agenda"]["discussion"]] == ["TB-003", "TB-002", "TB-001"]  # already there: keeps its place
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-003", "TB-002", "TB-001"], "noting": [], "by_urgency": ["discussion"]})
    assert r.json()["agenda_order"]["discussion"] == "urgency"
    assert [x["case_id"] for x in r.json()["agenda"]["discussion"]] == ["TB-001", "TB-003", "TB-002"]  # 5 (sent first), 5, none
    assert As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": [], "noting": [], "by_urgency": ["not_ready"]}).status_code == 400
    assert As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": [], "noting": [], "by_urgency": "discussion"}).status_code == 400


def test_a_removal_or_the_same_order_keeps_the_urgency_order(tc, docs, clock):
    mid = new_meeting(tc, date_=_day(2))
    urgency("TB-003", 4)
    for cid in docs:
        send(tc, cid)
    assert ids(tc, mid) == ["TB-003", "TB-001", "TB-002"]
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-003", "TB-002"], "noting": []})
    assert r.json()["agenda_order"]["discussion"] == "urgency"
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-003", "TB-002"], "noting": ["TB-001"]})
    assert r.json()["agenda_order"] == {"discussion": "urgency", "noting": "urgency"}


# ---- a cancelled meeting (API check note 8) ------------------------------------------------------------------------------------------

def test_cancelling_moves_the_case_files_to_the_next_meeting_after_it_and_tells_each_owner(tc, docs):
    early = new_meeting(tc, date_=_day(1))
    mid = new_meeting(tc, date_=_day(4), time_="10:00")
    nxt = new_meeting(tc, date_=_day(11), time_="10:00")
    send(tc, "TB-002", meeting_id=mid)
    send(tc, "TB-003", meeting_id=mid, list="noting")
    As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-001", "list": "discussion"})  # by the coordinator: no ready mark
    assert "board_ready" not in store.get_case("TB-001")
    r = As(tc, "anil").post(f"/meetings/{mid}/cancel", json={"reason": "Holiday (synthetic)"})
    assert r.status_code == 200, r.text
    m = r.json()["meeting"]
    assert m["counts"]["discussion"] == 0 and m["counts"]["noting"] == 0
    assert sorted((x["case_id"], x["list"], x["to"]) for x in m["cancelled"]["moved"]) == [("TB-001", "discussion", nxt), ("TB-002", "discussion", nxt), ("TB-003", "noting", nxt)]
    assert sorted(ids(tc, nxt)) == ["TB-001", "TB-002"] and ids(tc, nxt, "noting") == ["TB-003"] and ids(tc, early) == []  # after it, not before
    assert board.get(mid)["agenda"] == []
    for cid in docs:
        c = store.get_case(cid)
        assert c["meeting_id"] == nxt and c["board_date"] == _day(11) and isinstance(c["board_ready"], dict)
        assert c["board_send_history"][-1]["moved_to"] == nxt and c["board_send_history"][-1]["reason"] == "meeting cancelled"
        assert any(e.get("kind") == "agenda_moved" and e.get("why") == "meeting_cancelled" for e in store.read_audit(cid))
        told = notes("priya", "agenda", cid)
        assert told and told[0]["title"].startswith("Moved to the meeting of") and "Holiday (synthetic)" in told[0]["text"]
    assert store.get_case("TB-002")["board_send"]["meeting_id"] == nxt
    assert store.get_case("TB-001")["board_ready"]["kept"] is True  # note 9: the owner can now move it
    r = As(tc, "priya").post("/cases/TB-001/meeting/move", json={"meeting_id": early})
    assert r.status_code == 200, r.text


def test_cancelling_with_no_later_meeting_sends_them_back_to_waiting(tc, docs):
    mid = new_meeting(tc, date_=_day(4))
    send(tc, "TB-002", meeting_id=mid, list="noting")
    As(tc, "anil").post(f"/meetings/{mid}/cancel")
    c = store.get_case("TB-002")
    assert "meeting_id" not in c and c["board_waiting"]["why"] == "meeting_cancelled" and c["board_waiting"]["list"] == "noting"
    assert c["board_send"]["meeting_id"] == "" and meetings.get(mid)["cancelled"]["waiting"] == ["TB-002"]
    assert any(n["title"].startswith("Waiting for a meeting") for n in notes("priya", "agenda", "TB-002"))
    later = new_meeting(tc, date_=_day(6))
    assert ids(tc, later, "noting") == ["TB-002"]


def test_cancelling_an_empty_meeting_moves_nothing(tc, docs):
    mid = new_meeting(tc, date_=_day(4))
    As(tc, "anil").post(f"/meetings/{mid}/cancel")
    assert [e["kind"] for e in board.read_audit() if e.get("session") == mid] == ["created", "meeting_cancelled"]


# ---- Not discussed keeps a ready mark (API check note 9) ------------------------------------------------------------------------------

def test_not_discussed_keeps_a_ready_mark_so_the_owner_and_the_coordinator_can_move_it(tc, docs):
    mid = started(tc)  # TB-001, TB-002 for discussion, put there by the coordinator: no ready mark
    nxt = new_meeting(tc, date_=_day(8), time_="09:00")
    other = new_meeting(tc, date_=_day(15), time_="09:00")
    assert "board_ready" not in store.get_case("TB-002")
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    assert r.status_code == 200 and r.json()["outcome"]["moved_to"] == nxt
    c = store.get_case("TB-002")
    assert c["board_ready"]["kept"] is True and c["board_ready"]["note"].startswith("Kept for the board: not discussed on")
    assert any(e.get("kind") == "board_ready" and e.get("why") == "not_discussed" for e in store.read_audit("TB-002"))
    r = As(tc, "priya").post("/cases/TB-002/meeting/move", json={"meeting_id": other, "reason": "PET-CT due (synthetic)"})
    assert r.status_code == 200, r.text
    assert ids(tc, other) == ["TB-002"] and ids(tc, nxt) == []
    r = As(tc, "anil").post("/cases/TB-002/meeting/withdraw", json={"reason": "Treated elsewhere (synthetic)"})
    assert r.status_code == 200, r.text
    # an agenda change in the running meeting never links the Case File moved on back to it
    As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-003", "list": "noting"})
    assert store.get_case("TB-002").get("meeting_id") is None


def test_not_discussed_goes_to_the_end_of_a_list_arranged_by_hand_marked_new(tc, docs):
    mid = started(tc)
    nxt = new_meeting(tc, date_=_day(8), time_="09:00")
    urgency("TB-003", 2)
    As(tc, "anil").put(f"/meetings/{nxt}/agenda", json={"discussion": ["TB-003"], "noting": []})
    meetings.add_to_agenda(nxt, "anil", "TB-003", "discussion")
    s = meetings.get(nxt); s["agenda_hand"] = {"discussion": {"by": "anil", "at": store.now_iso()}}; board.save_session(s)
    urgency("TB-001", 5)
    As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    v = As(tc, "anil").get(f"/meetings/{nxt}").json()
    assert [(x["case_id"], x["new"]) for x in v["agenda"]["discussion"]] == [("TB-003", False), ("TB-001", True)]


def test_not_discussed_with_no_later_meeting_waits_and_joins_the_next_meeting_made(tc, docs):
    mid = started(tc)
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    assert r.json()["outcome"]["flagged"] is True
    c = store.get_case("TB-001")
    assert c["board_waiting"]["why"] == "not_discussed" and c["board_waiting"]["from"] == mid and c["board_ready"]["kept"] is True
    assert "joins the first meeting made" in notes("priya", "outcome", "TB-001")[0]["text"]
    later = new_meeting(tc, date_=_day(9))
    v = As(tc, "anil").get(f"/meetings/{later}").json()
    assert [x["case_id"] for x in v["agenda"]["discussion"]] == ["TB-001"] and v["agenda"]["discussion"][0]["reason"].startswith("Not discussed on")
    assert store.get_case("TB-001")["meeting_id"] == later
