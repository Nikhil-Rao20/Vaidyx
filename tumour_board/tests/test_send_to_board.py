"""Send to the board, multi-step (night-v3 item 1.4, design B7): the server requires the question and, with items open, a reason; it stores
the list, the presenter and the meeting, puts the Case File on that meeting's list and tells the coordinator with the meeting date, the
list and the presenter. "Not scheduled yet" marks it ready with no meeting. A resident's send is a proposal the consultant approves, run
in the consultant's name. Synthetic Case Files only (the TB-002 fixture), the conftest temporary data root, no model call."""
from datetime import date, timedelta

import pytest

from tumour_board import board, meetings, notify, ready_hook, steps, store
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
    """TB-002 with the question written and Dr Asha on the Case File team; the ready hook off (no background work)."""
    monkeypatch.setattr(ready_hook, "on_ready", lambda case_id, user: {"scheduled": False, "how": "off"})
    c = store.get_case(CASE)
    c["board_question"] = QUESTION
    c["team"] = {"owner": RAO, "residents": [{"user": ASHA, "added_by": RAO}]}
    store.save_case(c)
    return CASE


@pytest.fixture
def meeting(data_root):
    return meetings.create(ANIL, _future(), "16:00")


def _open(monkeypatch, n):
    monkeypatch.setattr(steps, "open_count", lambda case_id: n)


def _list_of(mid, case_id):
    s = meetings.get(mid)
    return next((k for k in meetings.LISTS for it in s["agenda_lists"].get(k) or [] if it.get("case_id") == case_id), None)


# ---- what the server requires ------------------------------------------------------------------------------------------------------

def test_the_question_is_required(full, people):
    make_case("TB-NIK-Q")  # an empty synthetic Case File: no question typed, none in a report
    r = full.as_(RAO).post("/cases/TB-NIK-Q/ready", {"ready": True, "reason": "synthetic"})
    assert r.status_code == 400 and r.json()["detail"] == {"message": "Write the question for the board first", "code": "send_400"}
    assert "board_ready" not in store.get_case("TB-NIK-Q") and "board_send" not in store.get_case("TB-NIK-Q")
    c = store.get_case("TB-NIK-Q"); c["typed_values"] = {"clinical_question": {"value": QUESTION}}; store.save_case(c)  # typed on its line
    assert full.as_(RAO).post("/cases/TB-NIK-Q/ready", {"ready": True, "reason": "synthetic"}).status_code == 200


def test_the_reason_is_required_when_items_are_open_and_not_when_none(full, ready_case, monkeypatch):
    _open(monkeypatch, 3)
    r = full.as_(RAO).post(f"/cases/{CASE}/ready", {"ready": True})
    assert r.status_code == 400 and r.json()["detail"]["message"] == "Say why the board should see it with 3 items open"
    assert "board_ready" not in store.get_case(CASE)
    _open(monkeypatch, 1)
    with pytest.raises(ValueError, match="with 1 item open"):
        board.send_to_board(CASE, RAO)
    _open(monkeypatch, 0)
    r = full.as_(RAO).post(f"/cases/{CASE}/ready", {"ready": True})
    assert r.status_code == 200, r.text
    send = r.json()["send"]
    assert send["list"] == "discussion" and send["meeting_id"] == "" and send["presenter"] == RAO and send["reason"] == "" and send["open_items"] == 0


def test_a_bad_list_is_refused(ready_case, monkeypatch):
    _open(monkeypatch, 0)
    with pytest.raises(ValueError, match="for discussion or for noting"):
        board.send_to_board(CASE, RAO, list="not_ready")


# ---- what it stores, audits and tells -----------------------------------------------------------------------------------------------

def test_send_stores_audits_lands_on_the_meeting_list_and_tells_the_coordinator(full, ready_case, meeting, monkeypatch):
    _open(monkeypatch, 2)
    body = {"ready": True, "list": "noting", "meeting_id": meeting["id"], "presenter": ASHA, "note": "Slides attached (synthetic)",
            "reason": "Surgery date is close (synthetic)"}
    r = full.as_(RAO).post(f"/cases/{CASE}/ready", body)
    assert r.status_code == 200, r.text
    assert r.json()["board_ready"]["by"] == RAO and r.json()["send"]["list"] == "noting"
    c = store.get_case(CASE)
    assert c["board_send"]["meeting_id"] == meeting["id"] and c["board_send"]["presenter"] == ASHA and c["board_send"]["open_items"] == 2
    assert c["board_send"]["reason"] == "Surgery date is close (synthetic)" and c["board_send_history"][-1] == c["board_send"]
    assert c["presenter"]["user"] == ASHA and c["presenter"]["name"] == "Dr Asha (synthetic)" and c["presenter"]["set_by"] == RAO
    assert c["meeting_id"] == meeting["id"] and c["board_date"] == meeting["date"]
    assert _list_of(meeting["id"], CASE) == "noting"
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "board_send")
    assert ev["by"] == RAO and ev["list"] == "noting" and ev["meeting_id"] == meeting["id"] and ev["presenter"] == ASHA and ev["open_items"] == 2
    assert ev["reason"] == "Surgery date is close (synthetic)"
    k = kinds(CASE)
    assert k.index("board_send") < k.index("board_ready")
    n = notes_for(ANIL, "board_ready")
    assert n and n[0]["to"] == {"role": "coordinator"}
    assert f"Meeting {_dmy(meeting['date'])} 16:00" in n[0]["text"] and "for noting" in n[0]["text"] and "presenter Dr Asha (synthetic)" in n[0]["text"]
    assert "Note: Slides attached (synthetic)" in n[0]["text"] and "Sent with 2 open: Surgery date is close (synthetic)" in n[0]["text"]
    row = meetings.row(meetings.get(meeting["id"]), {"case_id": CASE}, 1)
    assert row["presenter"] == {"user": ASHA, "name": "Dr Asha (synthetic)"} and row["presenter_name"] == "Dr Asha (synthetic)"
    assert meetings.presenter_of(c) == ASHA  # the presenter may open records on the shared screen (api/meetings.py)


def test_for_discussion_by_default_and_presenter_defaults_to_the_sender(ready_case, meeting, monkeypatch):
    _open(monkeypatch, 0)
    board.send_to_board(CASE, RAO, meeting_id=meeting["id"])
    assert _list_of(meeting["id"], CASE) == "discussion"
    assert store.get_case(CASE)["presenter"]["user"] == RAO
    n = [x for x in notes_for(ANIL, "board_ready")]
    assert "for discussion, presenter" in n[0]["text"]


def test_not_scheduled_yet_marks_ready_with_no_meeting(ready_case, meeting, monkeypatch):
    _open(monkeypatch, 0)
    c = board.send_to_board(CASE, RAO, list="discussion")
    assert c["board_ready"]["by"] == RAO and c["board_send"]["meeting_id"] == ""
    assert _list_of(meeting["id"], CASE) is None and not c.get("meeting_id")
    n = notes_for(ANIL, "board_ready")
    assert "Meeting not scheduled yet: pick a meeting" in n[0]["text"]


# ---- what it refuses ------------------------------------------------------------------------------------------------------------------

def test_a_wrong_presenter_is_refused(ready_case, meeting, monkeypatch):
    _open(monkeypatch, 0)
    with pytest.raises(ValueError, match="you or a resident on the Case File team"):
        board.send_to_board(CASE, RAO, meeting_id=meeting["id"], presenter=MEHTA)
    c = store.get_case(CASE)
    c["team"]["residents"][0]["removed"] = True; store.save_case(c)  # a resident taken off the team no longer presents
    with pytest.raises(ValueError, match="you or a resident"):
        board.send_to_board(CASE, RAO, presenter=ASHA)
    assert "board_ready" not in store.get_case(CASE) and "board_send" not in store.get_case(CASE)


@pytest.mark.parametrize("state", ["in_session", "closed", "cancelled"])
def test_a_meeting_in_session_closed_or_cancelled_is_refused(ready_case, meeting, monkeypatch, state):
    _open(monkeypatch, 0)
    s = meetings.get(meeting["id"])
    s["status"] = state
    if state == "cancelled":
        s["cancelled"] = {"by": ANIL, "at": store.now_iso(), "reason": "synthetic"}
    board.save_session(s)
    with pytest.raises(ValueError, match="That meeting is not open"):
        board.send_to_board(CASE, RAO, meeting_id=meeting["id"])
    assert "board_ready" not in store.get_case(CASE) and _list_of(meeting["id"], CASE) is None


def test_a_past_or_unknown_meeting_is_refused(ready_case, meeting, monkeypatch):
    _open(monkeypatch, 0)
    s = meetings.get(meeting["id"]); s["date"] = (date.today() - timedelta(days=1)).isoformat(); board.save_session(s)
    with pytest.raises(ValueError, match="has passed"):
        board.send_to_board(CASE, RAO, meeting_id=meeting["id"])
    with pytest.raises(ValueError, match="Meeting not found"):
        board.send_to_board(CASE, RAO, meeting_id="S-NOPE")


def test_open_meetings_are_planned_not_cancelled_and_not_past(data_root):
    a = meetings.create(ANIL, _future(3)); b = meetings.create(ANIL, _future(10)); x = meetings.create(ANIL, _future(5))
    meetings.cancel(x["id"], ANIL, "synthetic")
    old = meetings.create(ANIL, _future(1)); s = meetings.get(old["id"]); s["date"] = "2020-01-01"; board.save_session(s)
    assert [m["id"] for m in meetings.open_meetings()] == [a["id"], b["id"]]


# ---- the resident's send: a proposal the consultant approves -------------------------------------------------------------------------

def test_a_residents_send_becomes_a_proposal_the_consultant_approves(full, ready_case, meeting, monkeypatch):
    _open(monkeypatch, 1)
    body = {"ready": True, "list": "discussion", "meeting_id": meeting["id"], "presenter": ASHA, "note": "please", "reason": "Pathology is due tomorrow (synthetic)"}
    assert full.as_(ASHA).post(f"/cases/{CASE}/ready", body).status_code == 403  # a resident never sends herself
    r = full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "mark_ready", "payload": body, "note": "send to the board"})
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["payload"]["list"] == "discussion" and p["payload"]["meeting_id"] == meeting["id"] and p["payload"]["presenter"] == ASHA
    assert p["payload"]["meeting_date"] == meeting["date"] and p["payload"]["presenter_name"] == "Dr Asha (synthetic)"
    assert p["payload"]["reason"] == "Pathology is due tomorrow (synthetic)"
    assert "board_ready" not in store.get_case(CASE) and _list_of(meeting["id"], CASE) is None  # nothing happens before the sign-off
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve")
    assert r.status_code == 200, r.text
    c = store.get_case(CASE)
    assert c["board_ready"]["by"] == RAO and c["board_send"]["by"] == RAO and c["presenter"]["user"] == ASHA
    assert _list_of(meeting["id"], CASE) == "discussion"
    entry = meetings.get(meeting["id"])["agenda_lists"]["discussion"][0]
    assert entry["added_by"] == RAO  # on the agenda in the consultant's name
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "board_send")
    assert ev["by"] == RAO


def test_a_residents_send_without_the_reason_fails_on_approval_and_changes_nothing(full, ready_case, monkeypatch):
    _open(monkeypatch, 2)
    p = full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "mark_ready", "payload": {"ready": True}}).json()["proposal"]
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve")
    assert r.status_code >= 400 and "with 2 items open" in r.text
    assert "board_ready" not in store.get_case(CASE)


def test_a_residents_proposal_with_a_bad_list_or_meeting_is_refused(full, ready_case):
    api = full.as_(ASHA)
    assert api.post(f"/cases/{CASE}/proposals", {"action": "mark_ready", "payload": {"ready": True, "list": "maybe"}}).status_code == 400
    assert api.post(f"/cases/{CASE}/proposals", {"action": "mark_ready", "payload": {"ready": True, "meeting_id": "S-NOPE"}}).status_code == 400


# ---- the old direct call is unchanged -------------------------------------------------------------------------------------------------

def test_mark_ready_direct_calls_work_as_before(ready_case):
    c = store.get_case(CASE); c.pop("board_question"); store.save_case(c)  # no question, items open: the direct call never checked them
    c = board.mark_ready(CASE, RAO, note="Summary compiled")
    assert c["board_ready"]["note"] == "Summary compiled" and "board_send" not in c
    n = notes_for(ANIL, "board_ready")
    assert n and n[0]["text"].endswith("Note: Summary compiled")
    c = board.mark_ready(CASE, RAO, ready=False)
    assert "board_ready" not in c and "board_ready_withdrawn" in kinds(CASE)
    assert notify.KINDS  # the coordinator's notice kind is unchanged (board_ready)
