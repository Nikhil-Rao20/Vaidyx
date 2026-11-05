"""The meeting window and the follow state (meetings-v2 item 2.2, docs/meetings-v2/research/05_phase2_spec.md "T2 refined" and "T1").

The window: a login admitted to a running meeting reads the Case File on its floor (scope READ) through the Case File's own read routes,
only while it is on the floor; never another Case File on the agenda, never after Next or the end, never while waiting, never an outside
expert, never a protected Case File; REQUESTS becomes READ only inside the window; the coordinator and the owner keep FULL.
The follow state: `view` in the meeting record, set by the coordinator or the presenter of the Case File on the floor through
POST /meetings/{mid}/view, reset by Next, sent over the socket, audited without the quote; images reuse open_item's viewing grant.
Hermetic: the fixtures of test_nik_meetings (fake logins, synthetic Case Files TB-001..003, no model, no hospital system)."""
import json
from datetime import datetime, timedelta

import pytest

from tumour_board import access, board, config, his_client, live, meetings, org, pacs, store
from tumour_board.api import common
from tumour_board.api import meetings as api_meetings
from tumour_board.tests.test_nik_meetings import UID, As, app, join_and_admit, new_meeting, owned, started, tc  # noqa: F401


def roles(user):
    return org.roles(user)


def sc(user, cid):
    access.meeting_window_reset()
    return access.scope(roles(user), store.get_case(cid))


def steps_status(user, cid):
    return As(TC[0], user).get(f"/cases/{cid}/steps").status_code


TC = [None]


@pytest.fixture(autouse=True)
def _tc(tc):  # noqa: F811
    TC[0] = tc
    api_meetings.VIEW_LIMIT._hits.clear()
    yield
    TC[0] = None


def ask_radiology(cid):
    """A sent Pre-Authorization request to Radiology: its doctors see the items asked about (scope REQUESTS)."""
    st = store.get_state(cid)
    st["actions"].append({"id": "A9", "source": "pre_authorization", "requirement": "ct_thorax", "label": "CT thorax", "department": "Radiology",
                          "department_id": "radiology", "status": "pending", "created": store.now_iso(), "history": []})
    store.save_state(cid, st)


def imaging_doc(cid="TB-001", study=True):
    doc = store.add_document_file(cid, "ct_thorax.pdf", b"synthetic " + cid.encode())
    doc["classification"] = {"title": "CT THORAX", "doc_type": "ct"}
    doc["his"] = {"imaging_study_ref": "ImagingStudy/img-1"}
    if study:
        doc["his"]["study"] = {"available": True, "study_uid": UID, "modality": "CT", "checked": store.now_iso()}
    store.save_doc(cid, doc)
    return doc


# ---- the meeting window ------------------------------------------------------------------------------------------------------------

def test_an_admitted_member_reads_the_case_on_the_floor_only_while_it_is_there(tc):  # noqa: F811
    owned("TB-002")  # Breast Surgery owns TB-002; TB-001 and TB-003 have no owner (the coordinator and their creator only)
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=("TB-003",))  # TB-001 on the floor
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    assert As(tc, "ravi").post("/meetings/join", json={"code": code}).json()["status"] == "waiting"
    assert sc("ravi", "TB-001") is None and steps_status("ravi", "TB-001") == 403  # waiting: no window
    assert As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "ravi"}).status_code == 200
    assert sc("ravi", "TB-001") == access.READ and access.meeting_window(roles("ravi"), store.get_case("TB-001")) == mid
    assert steps_status("ravi", "TB-001") == 200
    assert As(tc, "ravi").get("/cases/TB-001/staging").status_code == 200
    assert As(tc, "ravi").get("/cases/TB-001").status_code == 200
    # read only: no change through the Case File routes, no clinical action
    r = As(tc, "ravi").put("/cases/TB-001/reason", json={"value": "staging"})
    assert r.status_code == 403
    assert access.may(roles("ravi"), "view", store.get_case("TB-001")) and not access.may(roles("ravi"), "confirm", store.get_case("TB-001"))
    with pytest.raises(PermissionError, match="on the floor of the meeting"):
        access.require(roles("ravi"), "set_urgency", store.get_case("TB-001"))
    assert access.visible(roles("ravi"), [store.get_case("TB-001")]) == []  # a window is never listed among the doctor's own
    # not another Case File on the agenda
    for cid in ("TB-002", "TB-003"):
        assert sc("ravi", cid) is None and steps_status("ravi", cid) == 403
    # Next: the window follows the floor
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"}).status_code == 200
    assert steps_status("ravi", "TB-001") == 403 and sc("ravi", "TB-001") is None
    assert steps_status("ravi", "TB-002") == 200 and As(tc, "ravi").get("/cases/TB-002/staging").status_code == 200
    # the end of the meeting closes it
    assert As(tc, "anil").post(f"/meetings/{mid}/end").status_code == 200
    assert steps_status("ravi", "TB-002") == 403 and sc("ravi", "TB-002") is None


def test_no_window_for_an_outside_expert_a_protected_case_or_a_meeting_left_running(tc, monkeypatch):  # noqa: F811
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    join_and_admit(tc, mid, "guest")
    join_and_admit(tc, mid, "meena")
    assert sc("guest", "TB-001") is None
    assert As(tc, "guest").get("/cases/TB-001/steps").status_code == 403
    placed_guest = {**roles("meena"), "outside_expert": True}  # an outside expert with a placement: still no window
    assert access.scope(placed_guest, store.get_case("TB-001")) is None
    assert sc("meena", "TB-001") == access.READ
    old = config.PROTECTED_CASES
    monkeypatch.setattr(config, "PROTECTED_CASES", old | {"TB-001"})
    assert sc("meena", "TB-001") is None  # a protected Case File: its creator only
    monkeypatch.setattr(config, "PROTECTED_CASES", old)
    s = board.get(mid)
    s["started_at"] = (datetime.now() - timedelta(hours=board.LIVE_HOURS + 1)).isoformat(timespec="seconds")
    board.save_session(s)
    assert sc("meena", "TB-001") is None  # in session for longer than a meeting runs: not running now (board.running_now)
    o = org.load(); o["users"]["meena"]["disabled"] = True; org.save(o, by="test")
    s["started_at"] = datetime.now().isoformat(timespec="seconds"); board.save_session(s)
    assert sc("meena", "TB-001") is None  # a disabled login


def test_requests_become_read_only_inside_the_window_and_the_owner_and_coordinator_keep_full(tc):  # noqa: F811
    owned("TB-002")
    ask_radiology("TB-002")
    assert sc("suresh", "TB-002") == access.REQUESTS
    assert steps_status("suresh", "TB-002") == 403
    mid = started(tc, discussion=("TB-002", "TB-001"), noting=())  # TB-002 on the floor
    assert sc("suresh", "TB-002") == access.REQUESTS  # not joined yet
    join_and_admit(tc, mid, "suresh")
    join_and_admit(tc, mid, "priya")
    assert sc("suresh", "TB-002") == access.READ and steps_status("suresh", "TB-002") == 200
    assert access.visible(roles("suresh"), [store.get_case("TB-002")])  # still listed: the department was asked
    assert sc("priya", "TB-002") == access.FULL and access.may(roles("priya"), "confirm", store.get_case("TB-002"))
    assert sc("anil", "TB-002") == access.FULL and sc("anil", "TB-001") == access.FULL
    assert sc("priya", "TB-001") is None  # not on the floor yet
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    assert sc("suresh", "TB-002") == access.REQUESTS and steps_status("suresh", "TB-002") == 403
    assert sc("priya", "TB-001") == access.READ and sc("suresh", "TB-001") == access.READ  # the next Case File on the floor
    assert sc("priya", "TB-002") == access.FULL and sc("anil", "TB-002") == access.FULL
    As(tc, "anil").post(f"/meetings/{mid}/end")
    assert sc("suresh", "TB-002") == access.REQUESTS and sc("priya", "TB-001") is None


def test_the_running_meetings_are_cached_and_a_meeting_change_clears_the_cache(tc, monkeypatch):  # noqa: F811
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    join_and_admit(tc, mid, "ravi")
    calls = []
    real = board.running_sessions
    monkeypatch.setattr(board, "running_sessions", lambda *a, **k: calls.append(1) or real(*a, **k))
    access.meeting_window_reset()
    c1, r = store.get_case("TB-001"), roles("ravi")
    assert all(access.scope(r, c1) == access.READ for _ in range(20)) and len(calls) == 1
    meetings.set_current(mid, "anil", "TB-002")  # meetings._save clears the cache: the change counts at once
    assert access.scope(r, c1) is None and len(calls) == 2


# ---- the follow state ------------------------------------------------------------------------------------------------------------------

def test_who_may_move_the_view_and_what_it_checks(tc, monkeypatch):  # noqa: F811
    owned("TB-002")  # priya is the team's owner of TB-002: its presenter
    planned = new_meeting(tc)
    assert As(tc, "anil").post(f"/meetings/{planned}/view", json={"tab": "summary"}).json()["detail"]["code"] == "not_in_session"
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "ravi")
    v = As(tc, "priya").get(f"/meetings/{mid}").json()["view"]
    assert v["case_id"] == "TB-001" and v["tab"] == "summary" and v["doc_id"] is None and v["opened"] is None and v["by"] == "anil"
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "ravi").post(f"/meetings/{mid}/view", json={"tab": "reports"}).json()["detail"]["code"] == "forbidden"
    assert As(tc, "priya").post(f"/meetings/{mid}/view", json={"tab": "reports"}).status_code == 403  # not the presenter of TB-001
    assert As(tc, "meena").post(f"/meetings/{mid}/view", json={"tab": "reports"}).json()["detail"]["code"] == "not_member"
    assert events == []
    doc = store.add_document_file("TB-001", "histopathology.pdf", b"synthetic report")
    other = store.add_document_file("TB-002", "mammogram.pdf", b"synthetic other")
    bad = [({"tab": "slides"}, 400, "bad_tab"), ({"tab": ""}, 400, "bad_tab"), ({"tab": "reports", "doc_id": "Dnope0000"}, 404, "no_record"),
           ({"tab": "reports", "doc_id": "../case.json"}, 400, "bad_record"), ({"tab": "reports", "doc_id": other["doc_id"]}, 404, "no_record"),
           ({"tab": "reports", "doc_id": doc["doc_id"], "page": -1}, 400, "bad_page"), ({"tab": "reports", "doc_id": doc["doc_id"], "page": "two"}, 400, "bad_page"),
           ({"tab": "reports", "doc_id": doc["doc_id"], "page": True}, 400, "bad_page"), ({"tab": "reports", "doc_id": doc["doc_id"], "page": 1.5}, 400, "bad_page"),
           ({"tab": "reports", "doc_id": doc["doc_id"], "quote": "x" * 301}, 400, "bad_quote"), ({"tab": "reports", "quote": 5}, 400, "bad_quote")]
    for body, status, code in bad:
        r = As(tc, "anil").post(f"/meetings/{mid}/view", json=body)
        assert (r.status_code, r.json()["detail"]["code"]) == (status, code), body
    quote = "Invasive ductal carcinoma, grade 2 (synthetic)."
    r = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "reports", "doc_id": doc["doc_id"], "page": 2, "quote": quote})
    assert r.status_code == 200, r.text
    v = r.json()["view"]
    assert {k: v[k] for k in ("case_id", "tab", "doc_id", "page", "quote", "by", "by_name")} == {
        "case_id": "TB-001", "tab": "reports", "doc_id": doc["doc_id"], "page": 2, "quote": quote, "by": "anil", "by_name": "Anil Kumar"}
    assert v["opened"]["kind"] == "record" and v["opened"]["url"] == f"/api/tb/cases/TB-001/documents/{doc['doc_id']}/file"
    assert events[-1] == {"type": "view", "view": v}
    assert As(tc, "ravi").get(f"/meetings/{mid}").json()["view"] == v  # every member follows the same view
    assert board.get(mid)["view"] == v
    audit = [e for e in board.read_audit() if e["session"] == mid and e.get("kind") == "view"]
    assert audit[-1]["tab"] == "reports" and audit[-1]["doc_id"] == doc["doc_id"] and audit[-1]["case_id"] == "TB-001" and quote not in str(audit)
    # another page of the same report keeps the record open (no new opening in the Case File's audit)
    opened_before = sum(1 for e in store.read_audit("TB-001") if e["kind"] == "record_opened_in_meeting")
    v2 = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "reports", "doc_id": doc["doc_id"], "page": "3", "quote": "x" * 300}).json()["view"]
    assert v2["page"] == 3 and v2["opened"] == v["opened"]
    assert sum(1 for e in store.read_audit("TB-001") if e["kind"] == "record_opened_in_meeting") == opened_before
    # a page without a record is not kept; the summary tab clears the record
    v3 = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "summary", "page": 4}).json()["view"]
    assert v3["page"] is None and v3["doc_id"] is None and v3["opened"] is None and v3["quote"] == ""
    # a viewer who is not admitted gets no follow state and no view event
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "meena").post("/meetings/join", json={"code": code})
    assert As(tc, "meena").get(f"/meetings/{mid}").json()["view"] is None
    assert meetings._shape(board.get(mid))("meena", roles("meena"), {"type": "view", "view": v}) is None
    # Next resets the view to the Summary of the new Case File (the view event first, then the current event)
    events.clear()
    r = As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    assert r.json()["view"]["case_id"] == "TB-002" and r.json()["view"]["tab"] == "summary"
    assert [e["type"] for e in events] == ["view", "current"] and events[0]["view"]["case_id"] == "TB-002" and events[0]["view"]["doc_id"] is None
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["view"]["tab"] == "summary"
    # the presenter of the Case File on the floor leads while admitted; the slide alone does not reset the view
    r = As(tc, "priya").post(f"/meetings/{mid}/view", json={"tab": "stage"})
    assert r.status_code == 200 and r.json()["view"]["by"] == "priya" and r.json()["view"]["by_name"] == "Dr Priya Nair"
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"slide": 2})
    assert As(tc, "ravi").get(f"/meetings/{mid}").json()["view"]["tab"] == "stage"
    assert As(tc, "ravi").post(f"/meetings/{mid}/view", json={"tab": "summary"}).status_code == 403
    As(tc, "anil").post(f"/meetings/{mid}/end")
    r = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "summary"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_in_session"


def test_view_is_rate_limited(tc, monkeypatch):  # noqa: F811
    mid = started(tc, discussion=("TB-001",), noting=())
    monkeypatch.setattr(api_meetings, "VIEW_LIMIT", common.RateLimit(2, 60))
    assert [As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": t}).status_code for t in ("reports", "images", "stage")] == [200, 200, 429]


def test_view_images_grants_every_admitted_member_through_the_open_path(tc, monkeypatch):  # noqa: F811
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "suresh"); join_and_admit(tc, mid, "guest")
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "ravi").post("/meetings/join", json={"code": code})  # waiting: no grant
    doc = imaging_doc()
    grants = []
    real = pacs.grant
    monkeypatch.setattr(pacs, "grant", lambda user, uid, cid, doc_id, **kw: grants.append((user, uid, cid, doc_id, kw.get("session"))) or real(user, uid, cid, doc_id, **kw))
    r = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 200, r.text
    o = r.json()["view"]["opened"]
    assert o["kind"] == "images" and o["url"] == f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}" and o["study_uid"] == UID and o["title"] == "CT THORAX"
    assert o["granted"] == ["anil", "priya", "suresh"]  # no outside expert without the patient's consent, nobody waiting
    assert sorted(g[0] for g in grants) == ["anil", "priya", "suresh"] and all(g[1:] == (UID, "TB-001", doc["doc_id"], mid) for g in grants)
    assert pacs.granted("ravi", UID) is None and pacs.granted("guest", UID) is None
    ev = [e for e in store.read_audit("TB-001") if e["kind"] == "images_opened"]
    assert ev and ev[-1]["granted_to"] == ["anil", "priya", "suresh"] and ev[-1]["session"] == mid
    assert board.get(mid)["view"]["opened"] == o and not (board.get(mid).get("live") or {}).get("opened")  # the old shared screen is not touched
    lab = store.add_document_file("TB-001", "cbc.pdf", b"synthetic cbc")
    r = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "images", "doc_id": lab["doc_id"]})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_images"
    assert board.get(mid)["view"]["opened"] == o  # a refused move leaves the view as it was
    # the images tab without a record: the list, nothing opened
    assert As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "images"}).json()["view"]["opened"] is None


def test_view_images_keeps_a_next_pressed_while_the_hospital_system_answered(tc, monkeypatch):  # noqa: F811
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    doc = imaging_doc(study=False)
    monkeypatch.setattr(his_client, "client", lambda: object())

    async def slow_study(cid, d, client):
        meetings.set_current(mid, "anil", "TB-002")  # the coordinator moves on while the hospital system answers
        return {"available": True, "study_uid": UID, "modality": "CT"}
    monkeypatch.setattr(pacs, "study_for_doc", slow_study)
    r = As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "moved_on"
    s = board.get(mid)
    assert s["current"] == "TB-002" and s["view"]["case_id"] == "TB-002" and s["view"]["tab"] == "summary" and s["view"]["opened"] is None


def test_an_outside_expert_follows_with_the_identity_withheld(tc):  # noqa: F811
    mid = started(tc, discussion=("TB-001",), noting=())
    join_and_admit(tc, mid, "guest")
    name = store.get_case("TB-001")["patient"]["name"]
    doc = store.add_document_file("TB-001", "report.pdf", b"synthetic report")
    line = f"Patient {name} reviewed (synthetic)."
    assert As(tc, "anil").post(f"/meetings/{mid}/view", json={"tab": "reports", "doc_id": doc["doc_id"], "quote": line}).status_code == 200
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["view"]["quote"] == line
    g = As(tc, "guest").get(f"/meetings/{mid}").json()["view"]
    assert name not in g["quote"] and meetings.WITHHELD in g["quote"] and g["doc_id"] == doc["doc_id"]
    assert meetings.shows_record(roles("guest"), "TB-001", doc["doc_id"]) is None  # no report page without the patient's consent
    c = store.get_case("TB-001"); c["consent"] = {"outside_discussion": True}; store.save_case(c)
    assert As(tc, "guest").get(f"/meetings/{mid}").json()["view"]["quote"] == line
    assert meetings.shows_record(roles("guest"), "TB-001", doc["doc_id"]) == mid  # the report the view shows, as the old shared screen did


# ---- a guest reviewer's private Case File on the board (Eswar, 5 Nov 2026, "Allow the board") ----------------------------------------

def _private(cid, sent):
    (store.case_dir(cid) / config.PRIVATE_MARKER).write_text("")
    c = store.get_case(cid)
    c["board_ready_history"] = [{"ready": True, "by": "guest", "at": store.now_iso(), "note": ""}] if sent else []
    store.save_case(c)


def test_a_private_case_file_is_kept_off_the_board_until_it_is_sent(tc):  # noqa: F811
    _private("TB-001", sent=False)
    assert "TB-001" in config.BOARD_HIDDEN and "TB-001" in config.HIDDEN_CASES
    _private("TB-001", sent=True)
    assert "TB-001" not in config.BOARD_HIDDEN and "TB-001" in config.HIDDEN_CASES   # on the board, still hidden everywhere else
    c = store.get_case("TB-001"); c["board_ready_history"].append({"ready": False, "by": "guest", "at": store.now_iso(), "note": "taken back"})
    store.save_case(c)
    assert "TB-001" in config.BOARD_HIDDEN                                            # taken back: off the board again


def test_people_in_the_meeting_read_a_sent_private_case_file_only_while_it_is_on_the_floor(tc):  # noqa: F811
    _private("TB-001", sent=True)
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())                    # TB-001 on the floor
    assert sc("ravi", "TB-001") is None                                               # not in the meeting: nothing
    join_and_admit(tc, mid, "ravi")
    assert sc("ravi", "TB-001") == access.READ and steps_status("ravi", "TB-001") == 200
    assert As(tc, "ravi").put("/cases/TB-001/reason", json={"value": "staging"}).status_code == 403   # read only
    assert access.visible(roles("ravi"), [store.get_case("TB-001")]) == []          # never listed among the doctor's own
    assert "TB-001" in As(tc, "anil").get(f"/meetings/{mid}").text                    # on the coordinator's agenda
    c = store.get_case("TB-001"); c["board_ready_history"].append({"ready": False, "by": "guest", "at": store.now_iso(), "note": ""})
    store.save_case(c)
    assert sc("ravi", "TB-001") is None                                               # taken back: the window closes


def test_a_private_case_file_not_sent_gives_no_meeting_window(tc):  # noqa: F811
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    join_and_admit(tc, mid, "ravi")
    _private("TB-001", sent=False)                                                    # made private and never sent
    assert sc("ravi", "TB-001") is None and steps_status("ravi", "TB-001") in (403, 404)


def test_the_guest_sends_a_private_case_file_onto_a_planned_meeting(tc):  # noqa: F811
    """The send checks the agenda before it marks the send: a private Case File being sent passes that check, the real case never."""
    owned("TB-001")
    _private("TB-001", sent=False)
    mid = new_meeting(tc)
    with pytest.raises(ValueError):
        board._check_cases(["TB-001"])                                             # not sent: not on any agenda
    assert board._check_cases(["TB-001"], sending=("TB-001",)) == ["TB-001"]       # the send itself may put it there
    assert "TB-001" in config.BOARD_HIDDEN
    config.PROTECTED_CASES.add("TB-001") if isinstance(config.PROTECTED_CASES, set) else None
    try:
        if "TB-001" in config.PROTECTED_CASES:
            with pytest.raises(ValueError):
                board._check_cases(["TB-001"], sending=("TB-001",))                # the real case: never
    finally:
        config.PROTECTED_CASES.discard("TB-001") if isinstance(config.PROTECTED_CASES, set) else None
    assert mid


def test_questions_about_a_deleted_case_file_leave_the_meeting_screens(tc):  # noqa: F811
    """5 Nov 2026: a guest reviewer's private Case File deleted after its meeting: the agents' answers about it (which quote its records)
    and its outcome are no longer shown; the stored meeting record and its audit are not edited."""
    import shutil
    mid = started(tc, discussion=("TB-001", "TB-002"), noting=())
    s = meetings.get(mid)
    s.setdefault("questions", []).append({"id": "Q1", "case_id": "TB-001", "text": "What does the biopsy say?", "role": "pathology",
                                          "answer": {"text": "SYNTHETIC answer quoting TB-001", "statements": []}, "at": store.now_iso()})
    s.setdefault("outcomes", {})["TB-001"] = {"outcome": "discussed", "decision_text": "SYNTHETIC decision for TB-001"}
    meetings._save(s)
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert any(q.get("id") == "Q1" for q in v["questions"]) and "TB-001" in v["outcomes"]
    shutil.rmtree(store.case_dir("TB-001"))
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert not any(q.get("id") == "Q1" for q in v["questions"]) and "TB-001" not in v["outcomes"]
    assert "SYNTHETIC answer quoting TB-001" not in json.dumps(v)
    assert any(q.get("id") == "Q1" for q in meetings.get(mid)["questions"])          # the stored record is unchanged
