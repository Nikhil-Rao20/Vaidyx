"""The doctor moves or withdraws a case (night-v3 item 1.6, design B8): the owner's consultant (or the MDT Coordinator) moves a Case File
sent to the board to another open meeting, or takes it off the agenda with a reason; the Case File sits on one agenda only, the coordinator
is told, every step is audited in the Case File and on the meetings. Synthetic Case Files only (the TB-002 fixture), the conftest
temporary data root, no model call."""
from datetime import date, timedelta

import pytest

from tumour_board import board, meetings, ready_hook, steps, store
from tumour_board.tests.test_nik_me import ANIL, ASHA, MEHTA, RAO, auth, make_case, people  # noqa: F401
from tumour_board.tests.test_nik_team import CASE, full, kinds, notes_for, tb002  # noqa: F401

QUESTION = "Is she fit for breast conservation surgery? (synthetic)"


def _future(days=7) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _dmy(iso) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


@pytest.fixture
def ready_case(tb002, monkeypatch):
    """TB-002 with the question written, nothing open, Dr Asha on the team; the ready hook off (no background work)."""
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: {"scheduled": False, "how": "off"})
    monkeypatch.setattr(steps, "open_count", lambda case_id: 0)
    c = store.get_case(CASE)
    c["board_question"] = QUESTION
    c["team"] = {"owner": RAO, "residents": [{"user": ASHA, "added_by": RAO}]}
    store.save_case(c)
    return CASE


@pytest.fixture
def two(data_root):
    """Two open meetings: A in a week, B in two weeks."""
    return meetings.create(ANIL, _future(7), "16:00", room="Seminar Hall 1"), meetings.create(ANIL, _future(14), "15:30")


@pytest.fixture
def sent(ready_case, two):
    """TB-002 sent to meeting A for noting."""
    a, b = two
    board.send_to_board(CASE, RAO, list="noting", meeting_id=a["id"])
    return a, b


def _list_of(mid, case_id):
    s = meetings.get(mid)
    return next((k for k in meetings.LISTS for it in s["agenda_lists"].get(k) or [] if it.get("case_id") == case_id), None)


def _on_old_agenda(mid, case_id):
    return case_id in [a["case_id"] for a in meetings.get(mid).get("agenda") or []]


def _meeting_audit(mid, kind):
    return [e for e in board.read_audit() if e.get("session") == mid and e.get("kind") == kind]


# ---- move -------------------------------------------------------------------------------------------------------------------------

def test_the_owner_moves_a_sent_case_file_to_another_open_meeting(full, sent):
    a, b = sent
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/move", {"meeting_id": b["id"], "reason": "Waiting for the PET-CT (synthetic)"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["meeting_id"] == b["id"] and j["board_date"] == b["date"] and j["meeting"]["id"] == b["id"]
    assert _list_of(a["id"], CASE) is None and not _on_old_agenda(a["id"], CASE)
    assert _list_of(b["id"], CASE) == "noting" and _on_old_agenda(b["id"], CASE)  # the same list it was sent to
    c = store.get_case(CASE)
    assert c["meeting_id"] == b["id"] and c["board_date"] == b["date"] and c["board_send"]["meeting_id"] == b["id"]
    h = c["board_send_history"][-1]
    assert h["moved_to"] == b["id"] and h["from"] == a["id"] and h["reason"] == "Waiting for the PET-CT (synthetic)" and h["by"] == RAO and h["at"]
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "agenda_moved")
    assert ev["by"] == RAO and ev["from"] == a["id"] and ev["to"] == b["id"] and ev["reason"] == "Waiting for the PET-CT (synthetic)"
    assert _meeting_audit(a["id"], "agenda_removed_by_owner") and _meeting_audit(a["id"], "agenda_moved")
    assert _meeting_audit(b["id"], "agenda_moved")[0]["from"] == a["id"]
    n = [x for x in notes_for(ANIL, "agenda") if x["case_id"] == CASE]
    assert n and n[0]["to"] == {"role": "coordinator"}
    assert n[0]["title"].startswith(f"Moved to the meeting of {_dmy(b['date'])}: ") and n[0]["title"].endswith(f"({CASE})")
    assert f"Moved from the meeting of {_dmy(a['date'])} 16:00 by Dr Rao (synthetic). Reason: Waiting for the PET-CT (synthetic)" == n[0]["text"]


def test_a_discussion_case_file_moves_to_the_discussion_list_and_the_reason_is_optional(ready_case, two):
    a, b = two
    board.send_to_board(CASE, RAO, meeting_id=a["id"])
    meetings.move_case(CASE, RAO, b["id"])
    assert _list_of(b["id"], CASE) == "discussion" and _list_of(a["id"], CASE) is None
    assert store.get_case(CASE)["board_send_history"][-1]["reason"] == ""


@pytest.mark.parametrize("state", ["in_session", "closed", "cancelled", "past"])
def test_a_target_that_is_not_open_is_refused(ready_case, two, state):
    a, b = two
    board.send_to_board(CASE, RAO, meeting_id=a["id"])
    s = meetings.get(b["id"])
    if state == "past":
        s["date"] = (date.today() - timedelta(days=1)).isoformat()
    else:
        s["status"] = state
    if state == "cancelled":
        s["cancelled"] = {"by": ANIL, "at": store.now_iso(), "reason": "synthetic"}
    board.save_session(s)
    with pytest.raises(meetings.MeetingError, match="has passed" if state == "past" else "That meeting is not open"):
        meetings.move_case(CASE, RAO, b["id"])
    assert _list_of(a["id"], CASE) == "discussion" and store.get_case(CASE)["meeting_id"] == a["id"]


def test_the_same_or_an_unknown_meeting_is_refused(full, sent):
    a, b = sent
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/move", {"meeting_id": a["id"]})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "same_meeting"
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/move", {"meeting_id": "S-NOPE"})
    assert r.status_code == 400 and r.json()["detail"] == {"message": "Meeting not found.", "code": "not_found"}
    assert _list_of(a["id"], CASE) == "noting"


def test_a_case_file_not_sent_yet_cannot_be_moved_or_withdrawn(full, ready_case, two):
    a, b = two
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/move", {"meeting_id": b["id"]})
    assert r.status_code == 400 and r.json()["detail"] == {"message": "Send it to the board first.", "code": "not_sent"}
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/withdraw", {"reason": "synthetic reason"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_sent"
    assert _list_of(b["id"], CASE) is None


def test_a_running_or_closed_current_meeting_refuses_both(sent):
    a, b = sent
    for state in ("in_session", "closed"):
        s = meetings.get(a["id"]); s["status"] = state; board.save_session(s)
        with pytest.raises(meetings.MeetingError, match="That meeting is not open"):
            meetings.move_case(CASE, RAO, b["id"])
        with pytest.raises(meetings.MeetingError, match="That meeting is not open"):
            meetings.withdraw_case(CASE, RAO, "synthetic reason")
    assert _list_of(b["id"], CASE) is None and store.get_case(CASE)["meeting_id"] == a["id"]


# ---- withdraw ---------------------------------------------------------------------------------------------------------------------

def test_the_owner_takes_it_off_the_agenda_with_a_reason(full, sent):
    a, b = sent
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/withdraw", {"reason": "Patient chose surgery elsewhere (synthetic)"})
    assert r.status_code == 200, r.text
    assert r.json()["meeting_id"] == "" and r.json()["meeting"] is None
    assert _list_of(a["id"], CASE) is None and not _on_old_agenda(a["id"], CASE)
    c = store.get_case(CASE)
    assert "meeting_id" not in c and c["board_date"] == a["date"]  # the board date is kept
    assert c["board_send"]["withdrawn"]["by"] == RAO and c["board_send"]["withdrawn"]["reason"] == "Patient chose surgery elsewhere (synthetic)"
    assert c["board_ready"]["by"] == RAO  # the ready mark stays: Send to the board can pick a meeting again
    assert c["board_send_history"][-1]["withdrawn_from"] == a["id"]
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "agenda_withdrawn")
    assert ev["by"] == RAO and ev["reason"] == "Patient chose surgery elsewhere (synthetic)" and ev["meeting_id"] == a["id"]
    assert _meeting_audit(a["id"], "agenda_withdrawn") and _meeting_audit(a["id"], "agenda_removed_by_owner")
    n = [x for x in notes_for(ANIL, "agenda") if x["case_id"] == CASE]
    assert n and n[0]["to"] == {"role": "coordinator"}
    assert n[0]["title"].startswith(f"Taken off the agenda of {_dmy(a['date'])}: ")
    assert n[0]["text"] == "Taken off by Dr Rao (synthetic). Reason: Patient chose surgery elsewhere (synthetic)"


@pytest.mark.parametrize("reason", ["", "  ", "ok", "x" * 501])
def test_withdraw_needs_a_reason_of_3_to_500_characters(full, sent, reason):
    a, b = sent
    r = full.as_(RAO).post(f"/cases/{CASE}/meeting/withdraw", {"reason": reason})
    assert r.status_code == 400 and r.json()["detail"]["code"] in ("reason_needed", "reason_too_long")
    assert _list_of(a["id"], CASE) == "noting" and store.get_case(CASE)["meeting_id"] == a["id"]


def test_withdraw_twice_is_refused(sent):
    meetings.withdraw_case(CASE, RAO, "synthetic reason")
    with pytest.raises(meetings.MeetingError, match="not on a meeting's agenda"):
        meetings.withdraw_case(CASE, RAO, "synthetic reason")


# ---- who ---------------------------------------------------------------------------------------------------------------------------

def test_another_departments_consultant_and_a_resident_get_403(full, sent):
    a, b = sent
    c = store.get_case(CASE); c["participants"] = [{"department": "medical_oncology"}]; store.save_case(c)  # Dr Mehta reads it in full
    assert full.as_(MEHTA).get(f"/cases/{CASE}").status_code == 200
    for who in (MEHTA, ASHA):
        r = full.as_(who).post(f"/cases/{CASE}/meeting/move", {"meeting_id": b["id"]})
        assert r.status_code == 403, (who, r.text)
        r = full.as_(who).post(f"/cases/{CASE}/meeting/withdraw", {"reason": "synthetic reason"})
        assert r.status_code == 403, (who, r.text)
    assert _list_of(a["id"], CASE) == "noting"


def test_the_coordinator_may_move_and_withdraw(full, sent):
    a, b = sent
    r = full.as_(ANIL).post(f"/cases/{CASE}/meeting/move", {"meeting_id": b["id"], "reason": "Agenda A is full (synthetic)"})
    assert r.status_code == 200, r.text
    assert _list_of(b["id"], CASE) == "noting"
    r = full.as_(ANIL).post(f"/cases/{CASE}/meeting/withdraw", {"reason": "Owner asked by phone (synthetic)"})
    assert r.status_code == 200, r.text
    assert _list_of(b["id"], CASE) is None and store.get_case(CASE)["board_send"]["withdrawn"]["by"] == ANIL
    assert "Taken off by Anil (synthetic)" in [x for x in notes_for(ANIL, "agenda") if x["case_id"] == CASE][0]["text"]


# ---- sending again -----------------------------------------------------------------------------------------------------------------

def test_sending_again_after_a_withdraw_clears_it_and_lands_on_one_agenda(sent):
    a, b = sent
    meetings.withdraw_case(CASE, RAO, "synthetic reason")
    c = board.send_to_board(CASE, RAO, list="discussion", meeting_id=b["id"])
    assert "withdrawn" not in c["board_send"] and c["meeting_id"] == b["id"]
    assert _list_of(b["id"], CASE) == "discussion" and _list_of(a["id"], CASE) is None


def test_a_send_to_another_meeting_takes_it_off_the_first(sent):
    a, b = sent
    board.send_to_board(CASE, RAO, list="discussion", meeting_id=b["id"])
    assert _list_of(a["id"], CASE) is None and not _on_old_agenda(a["id"], CASE)
    assert _list_of(b["id"], CASE) == "discussion"
    assert _meeting_audit(a["id"], "agenda_removed_by_owner")[0]["why"] == "sent"
    assert store.get_case(CASE)["meeting_id"] == b["id"]


def test_a_move_after_a_withdraw_puts_it_back_and_clears_the_withdraw(sent):
    a, b = sent
    meetings.withdraw_case(CASE, RAO, "synthetic reason")
    c = meetings.move_case(CASE, RAO, b["id"])
    assert "withdrawn" not in c["board_send"] and c["meeting_id"] == b["id"] and _list_of(b["id"], CASE) == "noting"
    n = [x for x in notes_for(ANIL, "agenda") if x["case_id"] == CASE and x["title"].startswith("Moved")]
    assert n and n[0]["text"].startswith("Put on this meeting by Dr Rao (synthetic).")


# ---- the open meetings for a doctor --------------------------------------------------------------------------------------------------

def test_open_meetings_route_lists_planned_meetings_for_a_treating_doctor(full, two):
    a, b = two
    x = meetings.create(ANIL, _future(3)); meetings.cancel(x["id"], ANIL, "synthetic")
    r = full.as_(RAO).get("/meetings/open")
    assert r.status_code == 200, r.text
    assert [m["id"] for m in r.json()["meetings"]] == [a["id"], b["id"]]
    assert r.json()["meetings"][0]["label"] == f"Tumour Board {_dmy(a['date'])} 16:00" and r.json()["meetings"][0]["room"] == "Seminar Hall 1"


# ---- the coordinator adds it to a meeting (review fix: one agenda, the withdraw cleared) ----------------------------------------------

def test_the_coordinator_adding_it_to_a_second_meeting_takes_it_off_the_first(sent):
    a, b = sent
    meetings.add_to_agenda(b["id"], ANIL, CASE, "discussion")
    assert _list_of(a["id"], CASE) is None and not _on_old_agenda(a["id"], CASE)
    assert _list_of(b["id"], CASE) == "discussion" and store.get_case(CASE)["meeting_id"] == b["id"]
    assert _meeting_audit(a["id"], "agenda_removed_by_owner")[0]["why"] == "coordinator"


def test_the_coordinator_setting_a_second_agenda_takes_it_off_the_first(sent):
    a, b = sent
    meetings.set_agenda(b["id"], ANIL, [], [CASE])
    assert _list_of(a["id"], CASE) is None and _list_of(b["id"], CASE) == "noting"
    assert _meeting_audit(a["id"], "agenda_removed_by_owner")[0]["why"] == "coordinator"
    meetings.set_agenda(b["id"], ANIL, [CASE], [])  # a reorder on the same meeting: nothing more is taken off anywhere
    assert len(_meeting_audit(a["id"], "agenda_removed_by_owner")) == 1


def test_a_not_ready_add_leaves_the_other_agenda_alone(sent):
    a, b = sent
    meetings.add_to_agenda(b["id"], ANIL, CASE, "not_ready", "Histopathology awaited (synthetic)")
    assert _list_of(a["id"], CASE) == "noting" and _list_of(b["id"], CASE) == "not_ready"


@pytest.mark.parametrize("how", ["add", "set"])
def test_the_coordinator_putting_it_back_after_a_withdraw_clears_the_withdraw(sent, how):
    from tumour_board import after_send
    a, b = sent
    meetings.withdraw_case(CASE, RAO, "synthetic reason")
    assert not after_send.is_sent(store.get_case(CASE))
    if how == "add":
        meetings.add_to_agenda(b["id"], ANIL, CASE, "noting")
    else:
        meetings.set_agenda(b["id"], ANIL, [CASE], [])
    c = store.get_case(CASE)
    assert "withdrawn" not in c["board_send"] and c["board_send"]["meeting_id"] == b["id"] and c["meeting_id"] == b["id"]
    assert after_send.is_sent(c)  # sent again: the chip no longer says Taken off
    h = c["board_send_history"]
    assert h[-2]["withdrawn_from"] == a["id"] and h[-2]["reason"] == "synthetic reason"  # the history keeps the withdraw
    assert h[-1]["put_back_on"] == b["id"] and h[-1]["by"] == ANIL
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "agenda_withdraw_cleared")
    assert ev["by"] == ANIL and ev["meeting_id"] == b["id"]


def test_the_agenda_add_route_puts_it_back_after_a_withdraw(full, sent):
    a, b = sent
    meetings.withdraw_case(CASE, RAO, "synthetic reason")
    r = full.as_(ANIL).post(f"/meetings/{b['id']}/agenda/add", {"case_id": CASE, "list": "discussion"})
    assert r.status_code == 200, r.text
    assert "withdrawn" not in store.get_case(CASE)["board_send"] and _list_of(b["id"], CASE) == "discussion"


# ---- locks and the open meetings audit (review fix) -----------------------------------------------------------------------------------

def test_move_withdraw_and_ready_routes_lock_the_case_file(full, ready_case, two, monkeypatch):
    a, b = two
    seen, real = [], store.lock

    def spy(case_id):
        seen.append(case_id)
        return real(case_id)
    monkeypatch.setattr(store, "lock", spy)
    assert full.as_(RAO).post(f"/cases/{CASE}/ready", {"ready": True, "meeting_id": a["id"]}).status_code == 200
    assert seen == [CASE]
    assert full.as_(RAO).post(f"/cases/{CASE}/meeting/move", {"meeting_id": b["id"]}).status_code == 200
    assert full.as_(RAO).post(f"/cases/{CASE}/meeting/withdraw", {"reason": "synthetic reason"}).status_code == 200
    assert seen == [CASE, CASE, CASE]


def test_open_meetings_route_is_audited(full, two):
    from tumour_board import org
    assert full.as_(RAO).get("/meetings/open").status_code == 200
    ev = next(e for e in org.read_audit() if e.get("kind") == "meetings_open_listed")
    assert ev["by"] == RAO and ev["count"] == 2
