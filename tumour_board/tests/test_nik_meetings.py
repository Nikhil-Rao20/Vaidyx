"""Meetings of the new interface (B3): create, agenda lists (the old agenda follows), send, code and join (right, wrong, expired, rate
limit), waiting room and admit, current and open (images: pacs.grant for every admitted member), timer, questions and the stand-in
agent (text, from the records, never a member), decisions with every outcome (not discussed moves to the next meeting), cards (required
for the heads), slides. Hermetic: a fake login system, synthetic Case Files, no model (llm.chat and agents.ask replaced)."""
import asyncio, copy, time
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tumour_board import access, agents, board, his_client, live, llm, meetings, notify, org, pacs, steps, store
from tumour_board.api import meetings as api_meetings

TOKENS = {f"tok-{u}": u for u in ("anil", "priya", "asha", "ravi", "suresh", "meena", "dev", "lata", "kiran", "mohan", "tbroot", "admin", "guest")}
UID = "1.2.826.0.1.3680043.8.498.1001"


class FakeAuth:
    """The slice of core.auth.AuthManager the routes and the WebSocket use."""
    is_configured = True

    def __init__(self):
        self.admins = {"admin"}

    def is_admin(self, u):
        return u in self.admins

    def get_username_for_token(self, token):
        return TOKENS.get(token)

    def get_privileges(self, u):
        return {"can_use_bash": False}


def hospital_org():
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["admins"] = ["tbroot"]
    o["users"] = {"anil": {"coordinator": True, "display_name": "Anil Kumar"},
                  "priya": {"departments": {"breast_surgery": "member"}, "display_name": "Dr Priya Nair"},
                  "asha": {"departments": {"breast_surgery": "resident"}, "display_name": "Dr Asha"},
                  "ravi": {"departments": {"radiology": "member"}, "display_name": "Dr Ravi"},
                  "suresh": {"departments": {"radiology": "head"}, "display_name": "Dr Suresh"},
                  "meena": {"departments": {"pathology": "head"}, "display_name": "Dr Meena"},
                  "dev": {"departments": {"medical_oncology": "head"}, "display_name": "Dr Dev"},
                  "lata": {"departments": {"surgical_oncology": "head"}, "display_name": "Dr Lata"},
                  "kiran": {"departments": {"radiation_oncology": "head"}, "display_name": "Dr Kiran"},
                  "mohan": {"departments": {"microbiology": "member"}, "display_name": "Dr Mohan"},  # a department not on the attendance sheet
                  "tbroot": {}, "guest": {"outside_expert": True, "display_name": "Dr Guest"}}
    return o


def make_app():
    from routes.tumour_board_routes import setup_tumour_board_routes
    app = FastAPI()
    auth = FakeAuth()
    app.state.auth_manager = auth

    @app.middleware("http")
    async def session_cookie(request: Request, call_next):
        tok = request.cookies.get("vaidyx_session")
        request.state.current_user = auth.get_username_for_token(tok) if tok else None
        return await call_next(request)
    app.include_router(setup_tumour_board_routes())
    return app


class As:
    """Calls as one user (the session cookie set before each call)."""

    def __init__(self, tc, user):
        self.tc, self.user = tc, user

    def _c(self):
        self.tc.cookies.set("vaidyx_session", f"tok-{self.user}")

    def get(self, path, **kw):
        self._c(); return self.tc.get("/api/tb" + path, **kw)

    def post(self, path, json=None, **kw):
        self._c(); return self.tc.post("/api/tb" + path, json=json if json is not None else {}, **kw)

    def put(self, path, json=None, **kw):
        self._c(); return self.tc.put("/api/tb" + path, json=json if json is not None else {}, **kw)

    def delete(self, path, **kw):
        self._c(); return self.tc.delete("/api/tb" + path, **kw)


@pytest.fixture
def app(data_root, demo_cases, monkeypatch):
    monkeypatch.setenv("TB_SCHEDULER", "0")
    org.save(hospital_org(), by="test")
    pacs.clear(); live.hub.clear(); meetings.LIVE_DECISION.clear(); meetings.AGENT_STATE.clear(); meetings.AGENT_AUDIO.clear(); meetings.AGENT_LOCKS.clear()
    api_meetings.JOIN_LIMIT._hits.clear()
    from tumour_board import service
    monkeypatch.setattr(service, "prepare_session_agents", lambda sid, user, roles=None, case_ids=None, refresh=False: [])

    async def no_warm(case_id, role):
        return None
    monkeypatch.setattr(agents, "warm", no_warm)  # the context pre-load is a model call (night-v3 6.4); tested on its own
    monkeypatch.setattr(his_client, "client", lambda d=None, transport=None: None)  # never the hospital system: cached studies only

    async def fake_chat(role, msgs, **kw):
        return {"claims": []}
    monkeypatch.setattr(llm, "chat", fake_chat)
    return make_app()


@pytest.fixture
def tc(app):
    with TestClient(app) as c:
        yield c


def owned(case_id="TB-002", department="breast_surgery", owner="priya", residents=("asha",)):
    c = store.get_case(case_id)
    c["department"] = department
    c["team"] = {"owner": owner, "residents": [{"user": r} for r in residents]}
    store.save_case(c)
    return c


def new_meeting(tc, date_=None, time_="10:30", room="Board room 2", video=True):
    r = As(tc, "anil").post("/meetings", json={"date": date_ or (date.today() + timedelta(days=1)).isoformat(), "time": time_, "room": room, "video": video})
    assert r.status_code == 200, r.text
    return r.json()["meeting"]["id"]


def with_agenda(tc, discussion=("TB-001", "TB-002"), noting=("TB-003",)):
    mid = new_meeting(tc)
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": list(discussion), "noting": list(noting)})
    assert r.status_code == 200, r.text
    return mid


def join_and_admit(tc, mid, user):
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    r = As(tc, user).post("/meetings/join", json={"code": code})
    assert r.status_code == 200 and r.json()["status"] == "waiting", r.text
    r = As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": user})
    assert r.status_code == 200, r.text
    return r.json()


def started(tc, **kw):
    mid = with_agenda(tc, **kw)
    r = As(tc, "anil").post(f"/meetings/{mid}/start")
    assert r.status_code == 200, r.text
    return mid


def kinds(dept=None, role=None, user=None):
    r = org.roles(user) if user else {"user": "x", "known": True, "coordinator": bool(role), "departments": {dept: "member"} if dept else {}}
    return [n["kind"] for n in notify.for_roles(r, limit=None)]


# ---- create, list, update, cancel -------------------------------------------------------------------------------------------------------

def test_create_update_list_and_cancel(tc):
    r = As(tc, "anil").post("/meetings", json={"date": "2026-11-05", "time": "09:00", "room": "Room 4", "video": True, "minutes_per_case": 8})
    assert r.status_code == 200
    m = r.json()["meeting"]
    assert m["status"] == "planned" and m["time"] == "09:00" and m["room"] == "Room 4" and m["video"] is True and m["minutes_per_case"] == 8
    assert m["counts"] == {"discussion": 0, "noting": 0, "not_ready": 0} and m["agenda_sent_at"] is None
    mid = m["id"]
    assert board.get(mid)["agenda"] == [] and board.get(mid)["status"] == "planned"  # the old session file, same shape
    assert As(tc, "priya").post("/meetings", json={"date": "2026-11-05"}).status_code == 403
    assert As(tc, "anil").post("/meetings", json={"date": "5/11/2026"}).status_code == 400
    assert As(tc, "anil").post("/meetings", json={"date": "2026-11-06", "time": "9am"}).json()["detail"]["code"] == "bad_time"
    r = As(tc, "anil").put(f"/meetings/{mid}", json={"time": "09:30", "room": "Room 5", "video": False})
    assert r.json()["meeting"]["time"] == "09:30" and r.json()["meeting"]["room"] == "Room 5" and r.json()["meeting"]["video"] is False
    listed = As(tc, "anil").get("/meetings").json()
    assert listed["can_manage"] is True and [x["id"] for x in listed["meetings"]] == [mid]
    assert As(tc, "priya").get("/meetings").json() == {"meetings": [], "can_manage": False}  # not joined, nothing of hers on the agenda
    r = As(tc, "anil").post(f"/meetings/{mid}/cancel", json={"reason": "Holiday"})
    assert r.json()["meeting"]["status"] == "cancelled"
    assert As(tc, "anil").post(f"/meetings/{mid}/start").status_code == 409
    assert "agenda" in kinds(dept="radiology")  # the attendance sheet's departments hear of the cancellation
    ev = [e for e in board.read_audit() if e["session"] == mid]
    assert [e["kind"] for e in ev] == ["created", "meeting_updated", "meeting_cancelled"] and ev[0]["meeting"] is True


def test_defaults_come_from_the_hospital_settings(tc):
    o = org.load(); o["hospital"]["meeting_defaults"] = {"weekday": 2, "time": "14:00", "room": "Oncology seminar room", "minutes_per_case": 12}
    org.save(o, by="test")
    m = As(tc, "anil").post("/meetings", json={"date": "2026-11-05"}).json()["meeting"]
    assert m["time"] == "14:00" and m["room"] == "Oncology seminar room" and m["minutes_per_case"] == 12


# ---- agenda -----------------------------------------------------------------------------------------------------------------------------

def test_agenda_lists_keep_the_old_agenda_in_sync(tc):
    mid = new_meeting(tc)
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-002", "TB-001"], "noting": ["TB-003", "TB-001"]})
    assert r.status_code == 200
    v = r.json()
    assert [x["case_id"] for x in v["agenda"]["discussion"]] == ["TB-002", "TB-001"] and [x["order"] for x in v["agenda"]["discussion"]] == [1, 2]
    assert [x["case_id"] for x in v["agenda"]["noting"]] == ["TB-003"]  # a Case File in both lists is for discussion
    row = v["agenda"]["discussion"][0]
    assert row["patient_line"].startswith("SYNTHETIC, Lakshmi Iyer") and "UHID SYN-200417" in row["patient_line"] and row["minutes"] == 10
    assert row["status"] == "waiting" and row["added_after_send"] is False and row["left_before_board"] == steps.open_count("TB-002")  # one count (21 Oct)
    s = board.get(mid)
    assert [a["case_id"] for a in s["agenda"]] == ["TB-002", "TB-001", "TB-003"]  # the old agenda: discussion then noting
    assert store.get_case("TB-002")["meeting_id"] == mid and store.get_case("TB-002")["board_date"] == s["date"]
    assert "breast_surgery" not in s["attendance"] and "radiology" in s["attendance"]  # the sheet: heads first; TB-002 has no owner yet
    # a Case File not listed cannot go on the agenda; the not-ready list needs a reason
    c = store.get_case("TB-003"); c["listing"] = {"status": "awaiting_listing"}; store.save_case(c)
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-003"], "noting": []})
    assert r.status_code == 400 and "not listed" in r.json()["detail"]["message"]
    assert As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-003", "list": "not_ready"}).json()["detail"]["code"] == "reason_needed"
    r = As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-003", "list": "not_ready", "reason": "Histopathology awaited"})
    assert r.status_code == 200
    v = r.json()
    assert [x["case_id"] for x in v["agenda"]["not_ready"]] == ["TB-003"] and v["agenda"]["not_ready"][0]["reason"] == "Histopathology awaited"
    assert [x["case_id"] for x in v["agenda"]["noting"]] == [] and [a["case_id"] for a in board.get(mid)["agenda"]] == ["TB-002", "TB-001"]
    assert As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-999", "list": "discussion"}).status_code == 400
    assert As(tc, "priya").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-001"]}).status_code == 403
    ev = [e["kind"] for e in store.read_audit("TB-002")]
    assert "board_session_agenda_added" in ev and "meeting_listed" in ev


def test_send_agenda_notifies_the_members_and_flags_later_additions(tc):
    mid = with_agenda(tc, discussion=("TB-001",), noting=())
    r = As(tc, "anil").post(f"/meetings/{mid}/send-agenda")
    assert r.status_code == 200 and r.json()["cases"] == 1 and "radiology" in r.json()["sent_to"] and "pathology" in r.json()["sent_to"]
    ns = [n for n in notify.for_roles(org.roles("ravi"), limit=None) if n["kind"] == "agenda"]
    assert len(ns) == 1 and "1 Case File(s) for discussion" in ns[0]["text"] and ns[0]["meeting_id"] == mid and "Board room 2" in ns[0]["text"]
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["meeting"]["agenda_sent_at"] and v["agenda"]["discussion"][0]["added_after_send"] is False
    As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-002", "list": "discussion"})
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert [(x["case_id"], x["added_after_send"]) for x in v["agenda"]["discussion"]] == [("TB-001", False), ("TB-002", True)]
    r = As(tc, "anil").post(f"/meetings/{mid}/send-agenda")
    assert r.json()["new"] == ["TB-002"]
    assert [n for n in notify.for_roles(org.roles("ravi"), limit=None) if n["kind"] == "agenda"][0]["title"].endswith("(updated)")


def test_remind_goes_to_the_owning_department(tc):
    owned("TB-002")
    mid = with_agenda(tc, discussion=("TB-002",), noting=())
    r = As(tc, "anil").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"})
    assert r.status_code == 200 and r.json()["to"] == "Breast Surgery"
    assert "owner_reminder" in kinds(user="priya")
    assert As(tc, "anil").post(f"/meetings/{mid}/remind", json={"case_id": "TB-001"}).status_code == 404  # not on the lists
    assert As(tc, "ravi").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"}).status_code == 403


# ---- code, join, waiting room ------------------------------------------------------------------------------------------------------------

def test_join_right_wrong_expired_and_rate_limited(tc):
    for cid in ("TB-001", "TB-002", "TB-003"):  # Breast Surgery's Case Files: Radiology may not read them in full
        owned(cid)
    mid = with_agenda(tc)
    r = As(tc, "anil").post(f"/meetings/{mid}/code")
    assert r.status_code == 200
    code = r.json()["value"]
    assert len(code) == 6 and code.isdigit() and r.json()["expires_at"] > store.now_iso()
    assert code not in "".join(str(e) for e in board.read_audit())  # never in the audit log
    assert As(tc, "priya").post(f"/meetings/{mid}/code").status_code == 403
    r = As(tc, "priya").post("/meetings/join", json={"code": code})
    assert r.status_code == 200 and r.json() == {**r.json(), "meeting_id": mid, "status": "waiting"}
    r = As(tc, "anil").post("/meetings/join", json={"code": code})  # the coordinator is admitted at once
    assert r.json()["status"] == "admitted"
    wrong = f"{(int(code) + 1) % 1000000:06d}"
    r = As(tc, "ravi").post("/meetings/join", json={"code": wrong})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_such_code"
    assert As(tc, "ravi").post("/meetings/join", json={"code": "12"}).status_code == 404
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["code"]["value"] == code and v["code"]["attempts"] == 2
    assert [(a["user"], a["status"]) for a in v["attendance"]] == [("anil", "present"), ("priya", "waiting")]
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["code"] is None  # only the coordinator sees the code
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["me"]["status"] == "waiting"
    # Radiology is a board head, so on the attendance sheet: it sees the agenda (initials for the Case Files it may not read in full) but
    # none of the live content until it joins and is admitted; a department not on the sheet sees nothing
    v = As(tc, "ravi").get(f"/meetings/{mid}").json()
    assert v["can"]["member"] is False and v["code"] is None and v["questions"] == [] and v["current"]["opened"] is None
    rows = v["agenda"]["discussion"] + v["agenda"]["noting"]
    for row in rows:
        full = access.scope(org.roles("ravi"), store.get_case(row["case_id"])) == access.FULL
        assert row["restricted"] is (not full)
        if not full:
            assert "UHID" not in row["patient_line"] and "SYNTHETIC" not in row["patient_line"] and row["board_question"] == ""
    assert any(row["restricted"] for row in rows)
    assert all(not row["restricted"] for row in As(tc, "anil").get(f"/meetings/{mid}").json()["agenda"]["discussion"])
    assert As(tc, "mohan").get(f"/meetings/{mid}").status_code == 403  # not joined, not on the sheet
    # expired
    s = board.get(mid); s["code"]["expires_at"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds"); board.save_session(s)
    r = As(tc, "ravi").post("/meetings/join", json={"code": code})
    assert r.status_code == 410 and r.json()["detail"]["code"] == "code_expired"
    # five tries per 15 minutes per user: the sixth is refused
    for i in range(3):
        assert As(tc, "ravi").post("/meetings/join", json={"code": wrong}).status_code == 404
    r = As(tc, "ravi").post("/meetings/join", json={"code": wrong})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert As(tc, "suresh").post("/meetings/join", json={"code": wrong}).status_code == 404  # another user is not limited


def test_admit_and_present_sync_the_old_attendance_sheet(tc):
    mid = with_agenda(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    assert As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "priya"}).status_code == 404  # not joined yet
    As(tc, "priya").post("/meetings/join", json={"code": code})
    As(tc, "suresh").post("/meetings/join", json={"code": code})
    assert As(tc, "priya").post(f"/meetings/{mid}/hand", json={"raised": True}).status_code == 403  # waiting: not a member yet
    r = As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "priya"})
    assert r.status_code == 200 and r.json()["status"] == "remote" and r.json()["name"] == "Dr Priya Nair"
    r = As(tc, "priya").post(f"/meetings/{mid}/present", json={"mode": "room"})
    assert r.json()["status"] == "present" and r.json()["mode"] == "room"
    As(tc, "suresh").post(f"/meetings/{mid}/present", json={"mode": "remote"})
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["attendance"][-1]["status"] == "waiting"  # a mode before admission keeps the person waiting
    assert As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "Suresh"}).json()["user"] == "suresh"  # the login in any case
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    att = {a["user"]: a for a in v["attendance"]}
    assert att["priya"]["status"] == "present" and att["suresh"]["status"] == "remote" and att["suresh"]["head"] is True and att["priya"]["head"] is False
    s = board.get(mid)
    assert s["attendance"]["radiology"] == "present" and s["attendance"]["breast_surgery"] == "present"  # the old sheet follows
    assert sorted((m["name"], m["department"]) for m in s["members"]) == [("Dr Priya Nair", "breast_surgery"), ("Dr Suresh", "radiology")]
    assert As(tc, "priya").post(f"/meetings/{mid}/present", json={"mode": "stage"}).status_code == 400
    assert As(tc, "ravi").post(f"/meetings/{mid}/present", json={"mode": "room"}).status_code == 404
    assert "radiology" not in board.absent_roles(s) and "pathology" in board.absent_roles(s)


# ---- running the meeting ---------------------------------------------------------------------------------------------------------------

def test_start_current_timer_and_end(tc):
    mid = with_agenda(tc)
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"}).status_code == 409  # not started
    r = As(tc, "anil").post(f"/meetings/{mid}/start")
    assert r.status_code == 200 and r.json()["meeting"]["status"] == "in_session" and r.json()["current"]["case_id"] == "TB-001"
    assert r.json()["current"]["timer"] == {"seconds_left": 600, "running": False, "total": 600}
    r = As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002", "slide": 2})
    assert r.status_code == 200 and r.json()["case_id"] == "TB-002" and r.json()["slide"] == 2 and r.json()["opened"] is None
    assert board.get(mid)["current"] == "TB-002" and [a["status"] for a in board.get(mid)["agenda"]] == ["waiting", "current", "waiting"]
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-999"}).status_code == 404
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"slide": 3}).json()["slide"] == 3
    r = As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "start", "minutes": 2})
    assert r.json()["timer"]["running"] is True and r.json()["timer"]["total"] == 120 and 118 <= r.json()["timer"]["seconds_left"] <= 120
    r = As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "stop"})
    assert r.json()["timer"]["running"] is False
    assert As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "reset"}).json()["timer"] == {"seconds_left": 120, "running": False, "total": 120}
    assert As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "pause"}).status_code == 400
    assert As(tc, "priya").post(f"/meetings/{mid}/timer", json={"action": "start"}).status_code == 403
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "ravi").post("/meetings/join", json={"code": code})
    r = As(tc, "anil").post(f"/meetings/{mid}/end")
    assert r.status_code == 200 and r.json()["meeting"]["status"] == "closed"
    s = board.get(mid)
    assert s["code"] is None and s["people"]["ravi"]["status"] == "absent" and s["closed_by"] == "anil"
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"}).status_code == 409
    assert As(tc, "anil").get("/meetings").json()["meetings"][0]["status"] == "closed"
    old = As(tc, "anil").get(f"/sessions/{mid}").json()  # the old room still reads the session
    assert old["session"]["status"] == "closed" and set(old["cases"]) == {"TB-001", "TB-002", "TB-003"}


def test_open_images_grants_every_admitted_member(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    join_and_admit(tc, mid, "suresh")
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "ravi").post("/meetings/join", json={"code": code})  # waiting: no grant
    doc = store.add_document_file("TB-001", "ct_thorax.pdf", b"synthetic")
    doc["classification"] = {"title": "CT THORAX", "doc_type": "ct"}
    doc["his"] = {"imaging_study_ref": "ImagingStudy/img-1", "study": {"available": True, "study_uid": UID, "modality": "CT", "checked": store.now_iso()}}
    store.save_doc("TB-001", doc)
    grants = []
    real = pacs.grant

    def spy(user, uid, cid, doc_id, **kw):
        grants.append((user, uid, cid, doc_id))
        return real(user, uid, cid, doc_id, **kw)
    monkeypatch.setattr(pacs, "grant", spy)
    r = As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 200, r.text
    o = r.json()["opened"]
    assert o["kind"] == "images" and o["url"] == f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}" and o["study_uid"] == UID and o["title"] == "CT THORAX"
    assert sorted(g[0] for g in grants) == ["anil", "priya", "suresh"] and all(g[1:] == (UID, "TB-001", doc["doc_id"]) for g in grants)
    assert o["granted"] == ["anil", "priya", "suresh"]
    assert pacs.granted("priya", UID)["case_id"] == "TB-001" and pacs.granted("ravi", UID) is None
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["opened"]["url"] == o["url"]
    ev = [e for e in store.read_audit("TB-001") if e["kind"] == "images_opened"]
    assert ev and ev[-1]["granted_to"] == ["anil", "priya", "suresh"] and ev[-1]["session"] == mid
    # a record: its file url; none: clears; a report without a study; the presenter may open, another member may not
    r = As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "record", "doc_id": doc["doc_id"]})
    assert r.json()["opened"]["url"] == f"/api/tb/cases/TB-001/documents/{doc['doc_id']}/file"
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "none"}).json()["opened"] is None
    lab = store.add_document_file("TB-001", "cbc.pdf", b"synthetic 2")
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": lab["doc_id"]}).status_code == 404
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": "Dnope"}).status_code == 404
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "record", "doc_id": "../case.json"}).status_code == 400
    assert As(tc, "priya").post(f"/meetings/{mid}/open", json={"kind": "record", "doc_id": doc["doc_id"]}).status_code == 403
    c = store.get_case("TB-001"); c["presenter"] = "priya"; store.save_case(c)
    assert As(tc, "priya").post(f"/meetings/{mid}/open", json={"kind": "record", "doc_id": doc["doc_id"]}).status_code == 200
    doc["his"]["study"] = {"available": False, "reason": "Images not in the PACS yet (study registered)"}; store.save_doc("TB-001", doc)
    r = As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "images_not_available"


# ---- questions, the stand-in agent, hands, the live decision --------------------------------------------------------------------------------

def wait_for(cond, seconds=5.0):
    """Wait for a background task on the app's loop (the TestClient runs it in its own thread)."""
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the background task")


def test_questions_are_answered_by_the_stand_in_agent_in_text(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    asked = []

    async def fake_ask(case_id, role, question, history=None, user="", **kw):
        asked.append((case_id, role, question, user))
        return {"role": role, "label": "Radiology", "status": "answered", "statements": [{"text": "Lesion 3.2 cm", "citations": [{"doc_id": "D1", "quote": "Lesion 3.2 cm"}]}],
                "references": [], "removed": [], "model": "reasoner", "seconds": 0.2}
    monkeypatch.setattr(agents, "ask", fake_ask)
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert v["agent"]["active"] is True and v["agent"]["role"] == "radiology" and v["agent"]["state"] == "ready"  # no radiology head present
    assert v["can"]["ask"] is True and v["can"]["ask_agents"] is True
    # a question with no role goes to the board (nobody answers it by itself); the role names the agent (night-v3 6.1)
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Who presents?"})
    assert r.status_code == 200 and r.json()["question"]["role"] is None and r.json()["question"]["answer"] is None, r.text
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "  What size is the lung lesion?  ", "role": "radiology"})
    assert r.status_code == 200, r.text
    q = r.json()["question"]
    assert q["text"] == "What size is the lung lesion?" and q["role"] == "radiology" and q["by_name"] == "Dr Priya Nair" and q["case_id"] == "TB-001"
    # the agent answers in a background task on the app's loop, its true states broadcast per role (no "reading the question")
    wait_for(lambda: any(e["type"] == "agent_state" and e["agent"]["state"] == "ready" for e in events))
    assert asked == [("TB-001", "radiology", "What size is the lung lesion?", "priya")]
    states = [e["agent"]["state"] for e in events if e["type"] == "agent_state"]
    assert states == ["thinking", "answering", "ready"]
    assert all(e["role"] == "radiology" for e in events if e["type"] == "agent_state")
    assert [e["type"] for e in events][-3:] == ["question", "agent_speech", "agent_state"]
    speech = [e for e in events if e["type"] == "agent_speech"]
    assert [x["index"] for x in speech] == [0, 1, 2] and speech[-1]["final"] is True and "text" not in speech[0]  # spoken by reference only
    out = asyncio.run(meetings.answer(mid, q["id"], "priya"))  # asked again: the stored answer, no second model call
    assert out["status"] == "answered" and out["text"] == "Lesion 3.2 cm" and out["role"] == "radiology" and len(asked) == 1
    assert out["speech"] == ["AI agent, Radiology.", "Lesion 3.2 cm", "Sources are on the screen."] and out["first_seconds"] is not None
    assert As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": " "}).status_code == 400
    assert As(tc, "ravi").post(f"/meetings/{mid}/questions", json={"text": "x"}).status_code == 403
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["questions"][1]["answer"]["text"] == "Lesion 3.2 cm" and v["questions"][1]["answer"]["statements"][0]["citations"] and v["agent"]["state"] == "ready"
    s = board.get(mid)
    assert [e["kind"] for e in s["log"]] == ["answer"] and s["log"][0]["question"] == "What size is the lung lesion?"  # the session's agent log, for the minutes
    assert [x["text"] for x in v["questions"]] == ["Who presents?", "What size is the lung lesion?"]
    assert "question_answered" in [e["kind"] for e in board.read_audit() if e["session"] == mid]
    # the head arrives: no stand-in for Radiology any more
    join_and_admit(tc, mid, "suresh")
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["agent"]["role"] == "pathology" and v["agent"]["active"] is True
    for u in ("meena", "dev", "lata", "kiran"):
        join_and_admit(tc, mid, u)
    v = As(tc, "anil").get(f"/meetings/{mid}").json()
    assert v["agent"]["active"] is False and v["agent"]["state"] == "off"
    r = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Any prior imaging?"})
    assert r.json()["question"]["role"] is None  # every head present: the question goes to the room only
    assert len(asked) == 1


def test_stand_in_failure_is_shown_not_hidden(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")

    async def boom(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(agents, "ask", boom)
    q = As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Lesion size?", "role": "radiology"}).json()["question"]
    wait_for(lambda: (board.get(mid)["questions"][0].get("answer") or {}).get("status") == "error" and meetings.AGENT_STATE.get(mid, {}).get("radiology", {}).get("state") == "error")
    out = asyncio.run(meetings.answer(mid, q["id"]))
    assert out["status"] == "error" and "could not answer" in out["text"]
    assert board.get(mid)["questions"][0]["answer"]["status"] == "error" and meetings.AGENT_STATE[mid]["radiology"]["state"] == "error"  # "Could not answer, try again" for a minute
    assert {a["role"]: a["state"] for a in As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]}["radiology"] == "error"


def test_hands_and_the_live_decision(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "priya").post(f"/meetings/{mid}/hand", json={"raised": True}).json()["hands"][0]["name"] == "Dr Priya Nair"
    assert As(tc, "priya").post(f"/meetings/{mid}/hand", json={"raised": True}).json()["hands"] and len(As(tc, "anil").get(f"/meetings/{mid}").json()["hands"]) == 1
    assert As(tc, "priya").post(f"/meetings/{mid}/hand", json={"raised": False}).json()["hands"] == []
    r = As(tc, "anil").put(f"/meetings/{mid}/decision-live", json={"text": "Neoadjuvant chemotherapy as per"})
    assert r.status_code == 200 and r.json()["saved"] is False
    assert events[-1]["type"] == "decision_live" and events[-1]["text"] == "Neoadjuvant chemotherapy as per"
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["decision_live"]["text"] == "Neoadjuvant chemotherapy as per"
    assert "decision_live" not in board.get(mid) and "Neoadjuvant" not in (board.sessions_dir() / f"{mid}.json").read_text()  # broadcast only
    assert As(tc, "priya").put(f"/meetings/{mid}/decision-live", json={"text": "x"}).status_code == 403


# ---- decisions ----------------------------------------------------------------------------------------------------------------------------

def test_decision_is_recorded_through_postboard_and_sent_to_the_owner(tc):
    owned("TB-002")
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    join_and_admit(tc, mid, "suresh")
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": False, "note": "Axillary ultrasound should be repeated"})
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "decision", "decision_text": ""}).status_code == 400
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "wished", "decision_text": "x"}).status_code == 400
    assert As(tc, "priya").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "decision", "decision_text": "x"}).status_code == 403
    body = {"outcome": "decision", "decision_text": "Neoadjuvant chemotherapy, then surgery.", "rationale": "As discussed: locally advanced disease.",
            "intent_as_stated": "Curative", "responsible_doctor": "Dr Priya Nair", "next_step": "Medical Oncology consult", "next_step_date": "25/10/2026",
            "members_present": ["Dr Priya Nair", "Dr Suresh"], "concerns": [{"by": "Dr Dev", "text": "Cardiac fitness to be checked"}]}
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json=body)
    assert r.status_code == 200, r.text
    rec, oc = r.json()["record"], r.json()["outcome"]
    assert rec["decision_text"] == body["decision_text"] and rec["outcome_type"] == "decision" and rec["meeting_outcome"] == "decision" and rec["session"] == mid
    assert rec["intent_as_recorded"] == "curative" and rec["next_step_date"] == "2026-10-25" and rec["responsible_doctor"] == "Dr Priya Nair"
    assert [c["text"] for c in rec["concerns"]] == ["Cardiac fitness to be checked", "Axillary ultrasound should be repeated"]  # the card's concern joins
    assert "Dr Suresh: Axillary ultrasound" in rec["divergent_opinions"] and rec["participants"] == "Dr Priya Nair, Dr Suresh"
    assert rec["adjudication"]["status"] in ("consistent", "flag_for_expert_review") and rec["recorded_by"] == "Anil Kumar"
    st = store.get_state("TB-002")
    assert [b["id"] for b in st["board_records"]] == [rec["id"]]  # the old board record, adjudicated
    s = board.get(mid)
    assert s["decisions"]["TB-002"]["board_record"] == rec["id"] and next(a for a in s["agenda"] if a["case_id"] == "TB-002")["status"] == "decided"
    assert oc["outcome"] == "decision" and s["outcomes"]["TB-002"]["record"] == rec["id"] and oc["moved_to"] is None
    ns = [n for n in notify.for_roles(org.roles("priya"), limit=None) if n["kind"] == "outcome"]
    assert len(ns) == 1 and ns[0]["case_id"] == "TB-002" and "Decision recorded" in ns[0]["title"] and ns[0]["record"] == rec["id"]
    assert [e for e in store.read_audit("TB-002") if e["kind"] == "board_session_outcome"][-1]["outcome"] == "decision"
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["agenda"]["discussion"][1]["outcome_label"] == "Decision recorded"
    # the old minutes carry it
    m = As(tc, "anil").get(f"/sessions/{mid}/minutes?format=json").json()
    assert next(c for c in m["cases"] if c["case_id"] == "TB-002")["decision"]["text"] == body["decision_text"]
    # saving the form again records nothing more: no second round, no second request (Phase 3 review S2)
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_recorded" and "Board decisions panel" in r.json()["detail"]["message"]
    assert [b["id"] for b in store.get_state("TB-002")["board_records"]] == [rec["id"]]


def test_not_discussed_moves_the_case_to_the_next_meeting_else_flags_it(tc):
    owned("TB-002")
    mid = started(tc)
    nxt = new_meeting(tc, date_=(date.today() + timedelta(days=8)).isoformat(), time_="09:00")
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    assert r.status_code == 200, r.text
    oc = r.json()["outcome"]
    assert oc["moved_to"] == nxt and oc["flagged"] is False and "moved to the meeting on" in r.json()["record"]["decision_text"]
    assert r.json()["record"]["outcome_type"] == "not_discussed"
    v = As(tc, "anil").get(f"/meetings/{nxt}").json()
    assert [x["case_id"] for x in v["agenda"]["discussion"]] == ["TB-001"] and v["agenda"]["discussion"][0]["reason"].startswith("Not discussed on")
    assert [a["case_id"] for a in board.get(nxt)["agenda"]] == ["TB-001"]
    c = store.get_case("TB-001")
    assert c["meeting_id"] == nxt and c["board_date"] == board.get(nxt)["date"] and "board_flags" not in c
    # no later meeting: flagged
    As(tc, "anil").post(f"/meetings/{nxt}/cancel")
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    assert r.json()["outcome"]["flagged"] is True and r.json()["outcome"]["moved_to"] is None
    assert store.get_case("TB-002")["board_flags"][0]["kind"] == "not_discussed"
    ns = [n for n in notify.for_roles(org.roles("priya"), limit=None) if n["kind"] == "outcome"]
    assert "flagged for the MDT Coordinator" in ns[0]["text"]


def test_deferred_referred_and_noted(tc):
    mid = started(tc)
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "deferred", "awaited": "PET-CT report", "awaited_from": "Nuclear Medicine", "next_step_date": "2026-11-01"})
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["outcome_type"] == "deferred" and rec["decision_text"] == "Deferred: awaiting PET-CT report from Nuclear Medicine" and rec["deferred_reason"].startswith("PET-CT report")
    acts = [a for a in store.get_state("TB-001")["actions"] if a.get("source") == "board"]
    assert any(a["department_id"] == "nuclear_medicine" and a["due"] == "2026-11-01" and "PET-CT report" in a["what"] for a in acts)  # the awaited item reaches the department
    assert "board_action" in kinds(dept="nuclear_medicine")
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "deferred"}).status_code == 400
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "referred", "referred_to": "State cancer centre sarcoma board"})
    assert r.json()["record"]["outcome_type"] == "referred" and r.json()["record"]["referred_to"] == "State cancer centre sarcoma board"
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-003/decision", json={"outcome": "noted"})
    assert r.json()["record"]["outcome_type"] == "noted" and r.json()["record"]["meeting_outcome"] == "noted" and r.json()["outcome"]["label"] == "Noted for information"  # night-v3 item 3.1: the real outcome
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-999/decision", json={"outcome": "noted"}).status_code == 404


def test_the_meeting_form_applies_the_required_by_outcome_rule(tc):
    """night-v3 item 3.1: the coordinator's form is strict (decision_record.clean); the message names what is missing."""
    owned("TB-002")
    mid = started(tc)
    url = f"/meetings/{mid}/cases/TB-002/decision"
    r = As(tc, "anil").post(url, json={"outcome": "decision", "decision_text": "Upfront surgery.", "responsible_doctor": "Dr Priya Nair"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_record" and "Choose the treatment intent" in r.json()["detail"]["message"]
    r = As(tc, "anil").post(url, json={"outcome": "decision", "decision_text": "Upfront surgery.", "intent": "curative", "responsible_doctor": "Dr Priya Nair", "sequence": "s" * 301})
    assert r.status_code == 400 and "Sequence: at most 300 characters" in r.json()["detail"]["message"]  # refused, never cut
    r = As(tc, "anil").post(url, json={"outcome": "deferred", "awaited": "IHC report"})
    assert r.status_code == 400 and "Say which department it is awaited from." in r.json()["detail"]["message"]
    r = As(tc, "anil").post(url, json={"outcome": "decision", "decision_text": "Upfront surgery.", "intent": "curative", "responsible_doctor": "Dr Priya Nair",
                                       "patient_informed_date": "01/01/2020"})
    assert r.status_code == 400 and "earlier than the board date" in r.json()["detail"]["message"]
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-003/decision", json={"outcome": "noted"})
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["outcome_type"] == "noted" and not [f for f in rec["adjudication"]["flags"] if f.get("kind") == "communication"]
    body = {"outcome": "decision", "decision_text": "Upfront surgery, then adjuvant chemotherapy.", "intent": "curative", "responsible_doctor": "Dr Priya Nair",
            "modalities": ["surgery", "chemotherapy"], "sequence": "Surgery then adjuvant chemotherapy", "stage_as_agreed": "cT2 N1 M0", "stage_source": "report",
            "investigations": [{"item": "MUGA scan", "department": "Nuclear Medicine"}], "referrals": [{"kind": "genetics", "department": "Medical Oncology", "note": "BRCA"}],
            "pmjay_plan_approval": "yes", "pmjay_plan_note": "PA-123"}
    r = As(tc, "anil").post(url, json=body)
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["modalities"] == ["surgery", "chemotherapy"] and rec["stage_source"] == "report" and rec["informed_by"] == "Dr Priya Nair" and rec["inform_by_date"]
    assert [a["kind"] for a in store.get_state("TB-002")["actions"] if a.get("board_record") == rec["id"] and not a.get("communication")] == ["investigation", "referral"]
    m = As(tc, "anil").get(f"/sessions/{mid}/minutes?format=json").json()
    d = next(c for c in m["cases"] if c["case_id"] == "TB-002")["decision"]
    lines = {x["label"]: x["text"] for x in d["fields"]}
    assert lines["Modalities"] == "Surgery, Chemotherapy" and lines["Further investigations"] == "MUGA scan (Nuclear Medicine)"  # the board gave no date: the action gets the default
    assert lines["Referrals"] == "Genetics and counselling (Medical Oncology, BRCA)" and lines["PM-JAY treatment plan approval"] == "Yes"
    # the owner's consultant corrects it later: a new version, the meeting shows it, the minutes carry the correction line
    r = As(tc, "priya").post(f"/cases/TB-002/board-records/{rec['id']}/correct", json={"changes": {"stage_as_agreed": "cT2 N0 M0"}, "reason": "N stage misread"})
    assert r.status_code == 200, r.text
    assert board.get(mid)["decisions"]["TB-002"]["version"] == 2
    html = As(tc, "anil").get(f"/sessions/{mid}/minutes").text
    assert "Stage as agreed by the board" in html and "cT2 N0 M0" in html and "Corrected by Dr Priya Nair on" in html and "N stage misread" in html
    assert "\u2014" not in html


# ---- end of a case and the cards ---------------------------------------------------------------------------------------------------------

def test_end_case_asks_the_heads_and_cards_are_required_for_them(tc, monkeypatch):
    owned("TB-002")
    mid = started(tc)
    for u in ("priya", "suresh", "ravi"):
        join_and_admit(tc, mid, u)
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "priya").post(f"/meetings/{mid}/cases/TB-002/end").status_code == 403
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/end")
    assert r.status_code == 200 and r.json()["cards_requested"] == board.head_ids() and len(r.json()["cards_requested"]) == 5
    assert "card_requested" in kinds(dept="radiology") and "card_requested" in kinds(dept="radiation_oncology") and "card_requested" not in kinds(dept="breast_surgery")
    assert events[-1]["type"] == "end_case" and events[-1]["case_id"] == "TB-002"
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-003/end").status_code == 200  # a Case File for noting can end too
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-999/end").status_code == 404
    v = As(tc, "suresh").get(f"/meetings/{mid}").json()
    assert v["can"]["card_required"] is True and v["ended"] == ["TB-002", "TB-003"]
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["can"]["card_required"] is False
    assert As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": False}).json()["detail"]["code"] == "note_needed"
    assert As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": "yes"}).status_code == 400
    r = As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": True, "note": "Fine"})
    assert r.status_code == 200 and r.json()["card"]["head"] is True and r.json()["card"]["department"] == "radiology"
    r = As(tc, "ravi").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": False, "note": "Repeat the ultrasound"})
    assert r.json()["card"]["head"] is False
    assert As(tc, "meena").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": True}).status_code == 403  # not admitted
    cards = As(tc, "anil").get(f"/meetings/{mid}/cards").json()
    assert cards["expected"] == ["suresh"] and set(cards["cards"]) == {"TB-001", "TB-002", "TB-003"}
    assert cards["cards"]["TB-002"]["missing"] == [] and cards["cards"]["TB-002"]["concerns"] == 1 and cards["cards"]["TB-001"]["missing"] == ["suresh"]
    assert sorted(c["user"] for c in cards["cards"]["TB-002"]["cards"]) == ["ravi", "suresh"]
    mine = As(tc, "priya").get(f"/meetings/{mid}/cards").json()  # the owner's team: its Case Files (TB-002, and the ownerless ones)
    assert "TB-002" in mine["cards"]
    assert "TB-002" in As(tc, "asha").get(f"/meetings/{mid}/cards").json()["cards"]  # the resident on the team
    assert As(tc, "ravi").get(f"/meetings/{mid}/cards").status_code == 403  # radiology owns nothing here
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["cards_given"] == {"TB-002": ["ravi", "suresh"]}
    assert [e for e in store.read_audit("TB-002") if e["kind"] == "board_session_card"][-1]["agree"] is False


# ---- slides -----------------------------------------------------------------------------------------------------------------------------------

def test_slides_summary_first_from_the_gate_then_from_the_summary(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    assert As(tc, "priya").get(f"/meetings/{mid}/cases/TB-999/slides").status_code == 404
    assert As(tc, "ravi").get(f"/meetings/{mid}/cases/TB-002/slides").status_code == 403
    # only the Case File on the floor, for anyone without the whole Case File (meetings-v2 2.6 and the API check)
    assert As(tc, "priya").get(f"/meetings/{mid}/cases/TB-002/slides").json()["detail"]["code"] == "not_current"
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    r = As(tc, "priya").get(f"/meetings/{mid}/cases/TB-002/slides")
    assert r.status_code == 200, r.text
    slides = r.json()["slides"]
    assert [s["id"] for s in slides] == ["summary", "values", "gaps", "imaging", "pathology", "points"]
    assert [s["kind"] for s in slides] == [s["id"] for s in slides]
    assert slides[0]["content"]["from"] == "gate" and slides[0]["content"]["patient_line"].startswith("SYNTHETIC, Lakshmi Iyer")
    assert isinstance(slides[1]["content"]["values"], list) and isinstance(slides[2]["content"]["gaps"], list) and isinstance(slides[2]["content"]["waivers"], list)
    for v in slides[1]["content"]["values"]:
        assert v["value"] and v["doc_id"] and "quote" in v and v["label"]
    assert isinstance(slides[3]["content"]["documents"], list) and isinstance(slides[4]["content"]["documents"], list) and slides[5]["content"]["points"] == []
    # with a summary artefact, a brief and published cases
    st = store.get_state("TB-002")
    st["artefacts"]["summary"] = {"sections": [{"id": "history", "title": "History", "sentences": [{"text": "A 48 year old woman.", "citations": []}]}],
                                  "points_for_review": [{"text": "Receptor status pending", "citations": []}], "review": {"status": "ai_draft"}, "model": "reasoner", "generated": "x"}
    st["artefacts"]["brief_radiology"] = {"label": "Radiology", "points_for_review": [{"text": "No prior CT", "citations": []}], "review": {"status": "reviewed"}}
    st["confirmations"] = [{"id": "C1", "type": "waive", "key": "bone_scan", "by": "priya", "at": "2026-10-01T10:00:00", "reason": "Not indicated at this stage"}]
    store.save_state("TB-002", st)
    store._write_json(store.case_dir("TB-002") / "published.json", {"items": [{"id": "P1", "title": "A case report", "journal": "IJC", "year": 2024, "peer_reviewed": True}]})
    doc = store.add_document_file("TB-002", "mammogram.pdf", b"synthetic")
    doc.update({"state": "ready", "classification": {"title": "MAMMOGRAM", "doc_type": "mammogram", "status": "FINAL", "signed": "yes", "report_date_iso": "2026-09-20"},
                "his": {"imaging_study_ref": "ImagingStudy/m1", "study": {"available": True, "study_uid": UID, "modality": "MG"}}})
    store.save_doc("TB-002", doc)
    slides = As(tc, "priya").get(f"/meetings/{mid}/cases/TB-002/slides").json()["slides"]
    assert [s["id"] for s in slides] == ["summary", "values", "gaps", "imaging", "pathology", "points", "published"]
    assert slides[0]["content"]["from"] == "summary" and slides[0]["content"]["label"] == "AI draft, not reviewed" and slides[0]["content"]["sections"][0]["sentences"][0]["text"] == "A 48 year old woman."
    assert slides[2]["content"]["waivers"] == [{"requirement": "bone_scan", "by": "priya", "at": "2026-10-01T10:00:00", "reason": "Not indicated at this stage"}]
    img = next(d for d in slides[3]["content"]["documents"] if d["doc_id"] == doc["doc_id"])
    assert img["images"] is True and img["viewer_available"] is True and img["modality"] == "MG" and img["url"].endswith(f"/documents/{doc['doc_id']}/file")
    pts = slides[5]["content"]["points"]
    assert [(p["source"], p["text"]) for p in pts] == [("summary", "Receptor status pending"), ("brief", "No prior CT")] and pts[1]["reviewed"] is True
    assert slides[6]["content"]["items"][0]["title"] == "A case report" and slides[6]["content"]["note"] == "Published case, not advice for this patient"
    assert "slides_read" in [e["kind"] for e in board.read_audit() if e["session"] == mid]


def test_outside_expert_sees_initials_without_consent(tc, monkeypatch):
    mid = started(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    r = As(tc, "guest").post("/meetings/join", json={"code": code})  # a guest of the meeting: no placement, waits for the coordinator
    assert r.status_code == 200 and r.json()["status"] == "waiting"
    assert As(tc, "guest").get("/cases").status_code == 403  # still no Case File at all
    assert As(tc, "guest").get(f"/meetings/{mid}/cases/TB-002/slides").status_code == 403  # waiting
    As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "guest"})
    v = As(tc, "guest").get(f"/meetings/{mid}").json()
    row = v["agenda"]["discussion"][1]
    assert row["patient_line"] == "SLI., 48 Y / F" and "SYN-200417" not in row["patient_line"] and v["can"]["member"] is True
    r = As(tc, "guest").get(f"/meetings/{mid}/cases/TB-002/slides")  # TB-001 is on the floor: a guest sees the current Case File only (review #9)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_current"
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    slides = As(tc, "guest").get(f"/meetings/{mid}/cases/TB-002/slides").json()["slides"]
    assert slides[0]["content"]["patient_line"] == "SLI., 48 Y / F"
    assert "SYN-200417" not in str(slides)  # the UHID is withheld from every slide without consent
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    assert As(tc, "guest").post(f"/meetings/{mid}/questions", json={"text": "x"}).status_code == 403  # the shared screen only
    assert As(tc, "guest").post(f"/meetings/{mid}/cases/TB-001/card", json={"agree": True}).status_code == 403
    assert As(tc, "guest").post(f"/meetings/{mid}/hand", json={"raised": True}).status_code == 200
    # images are not granted to a guest without the owner's consent (the viewer shows the patient's identity)
    doc = store.add_document_file("TB-001", "ct.pdf", b"synthetic")
    doc["classification"] = {"title": "CT THORAX", "doc_type": "ct"}
    doc["his"] = {"imaging_study_ref": "ImagingStudy/img-1", "study": {"available": True, "study_uid": UID, "modality": "CT"}}
    store.save_doc("TB-001", doc)
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]}).json()["opened"]["granted"] == ["anil"]
    c = store.get_case("TB-001"); c["consent"] = {"outside_discussion": True}; store.save_case(c)
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]}).json()["opened"]["granted"] == ["anil", "guest"]
    c = store.get_case("TB-002"); c["consent"] = {"outside_discussion": True}; store.save_case(c)
    assert "SYN-200417" in As(tc, "guest").get(f"/meetings/{mid}").json()["agenda"]["discussion"][1]["patient_line"]
    o = org.load(); o["users"]["guest"]["disabled"] = True; org.save(o, by="test")
    assert As(tc, "guest").get(f"/meetings/{mid}").status_code == 403


def test_scheduler_status_is_for_admins(tc):
    assert As(tc, "priya").get("/scheduler/status").status_code == 403
    r = As(tc, "tbroot").get("/scheduler/status")
    assert r.status_code == 200 and r.json()["running"] is False and r.json()["enabled"] is False and [j["name"] for j in r.json()["jobs"]][0] == "codes"
    assert As(tc, "admin").get("/scheduler/status").status_code == 200


def test_a_case_file_sits_on_one_planned_agenda_when_the_coordinator_lists_it_again(tc):
    """Review fix (night-v3 item 1.6): the coordinator putting a Case File on a second planned meeting's agenda takes it off the first."""
    first = with_agenda(tc, discussion=("TB-001", "TB-002"), noting=())
    second = new_meeting(tc, date_=(date.today() + timedelta(days=8)).isoformat())
    r = As(tc, "anil").put(f"/meetings/{second}/agenda", json={"discussion": ["TB-002"], "noting": []})
    assert r.status_code == 200, r.text
    assert [x["case_id"] for x in As(tc, "anil").get(f"/meetings/{first}").json()["agenda"]["discussion"]] == ["TB-001"]
    assert [a["case_id"] for a in board.get(first)["agenda"]] == ["TB-001"]
    assert store.get_case("TB-002")["meeting_id"] == second
    r = As(tc, "anil").post(f"/meetings/{first}/agenda/add", json={"case_id": "TB-002", "list": "noting"})
    assert r.status_code == 200 and [x["case_id"] for x in r.json()["agenda"]["noting"]] == ["TB-002"]
    assert As(tc, "anil").get(f"/meetings/{second}").json()["agenda"]["discussion"] == [] and store.get_case("TB-002")["meeting_id"] == first


# ---- the call shell (night-v3 5.1): the agents list, the spotlight, reactions ----------------------------------------------------------------

def test_every_absent_head_has_a_stand_in_agent_in_the_list(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    roles = [a["role"] for a in v["agents"]]
    assert "radiology" in roles and "pathology" in roles and "medical_oncology" in roles and "radiation_oncology" in roles
    first = v["agents"][0]
    assert first["standing_in"] is True and first["state"] == "ready" and first["question"] is None and "support only" in first["note"]
    assert first["department_name"] and first["label"]
    assert v["agent"]["role"] == roles[0]  # the single-agent field stays for older readers
    # the head who joins is no longer stood in for
    join_and_admit(tc, mid, "suresh")
    roles2 = [a["role"] for a in As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]]
    assert "radiology" not in roles2 and "pathology" in roles2
    # the shared state names the role it belongs to
    meetings._set_agent(mid, "pathology", "thinking", by="priya", question="Q1")
    ag = {a["role"]: a for a in As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]}
    assert ag["pathology"]["state"] == "thinking" and ag["pathology"]["question"] == "Q1" and ag["medical_oncology"]["state"] == "ready"
    # outside a session: nothing
    assert As(tc, "anil").get(f"/meetings/{with_agenda(tc)}").json()["agents"] == []


def test_spotlight_is_the_coordinators_and_clears_on_the_next_case(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "ravi")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "priya").post(f"/meetings/{mid}/spotlight", json={"users": ["ravi"]}).status_code == 403
    r = As(tc, "anil").post(f"/meetings/{mid}/spotlight", json={"users": ["ravi", "priya", "ravi"]})
    assert r.status_code == 200 and r.json()["spotlight"] == ["ravi", "priya"], r.text
    assert events[-1]["type"] == "spotlight" and events[-1]["users"] == ["ravi", "priya"]
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["spotlight"] == ["ravi", "priya"]
    # only admitted people; at most three
    assert As(tc, "anil").post(f"/meetings/{mid}/spotlight", json={"users": ["meena"]}).status_code == 409
    join_and_admit(tc, mid, "meena"); join_and_admit(tc, mid, "dev")
    assert As(tc, "anil").post(f"/meetings/{mid}/spotlight", json={"users": ["ravi", "priya", "meena", "dev"]}).status_code == 400
    # audited by ids, and the next case clears it
    assert any(e.get("kind") == "spotlight" and e.get("users") == ["ravi", "priya"] for e in board.read_audit() if e["session"] == mid)
    r = As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    assert r.status_code == 200
    assert events[-1]["type"] == "current" and events[-1]["spotlight"] == [] and isinstance(events[-1]["agents"], list)
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["spotlight"] == []
    assert As(tc, "anil").post(f"/meetings/{mid}/spotlight", json={"users": []}).json()["spotlight"] == []


def test_reactions_are_broadcast_never_stored_and_rate_limited(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    meetings._REACTED.clear()
    r = As(tc, "priya").post(f"/meetings/{mid}/reaction", json={"kind": "agree"})
    assert r.status_code == 200 and r.json()["kind"] == "agree", r.text
    assert events[-1]["type"] == "reaction" and events[-1]["user"] == "priya" and events[-1]["name"] == "Dr Priya Nair" and events[-1]["kind"] == "agree"
    assert As(tc, "priya").post(f"/meetings/{mid}/reaction", json={"kind": "thanks"}).status_code == 429
    meetings._REACTED.clear()
    assert As(tc, "priya").post(f"/meetings/{mid}/reaction", json={"kind": "wave"}).status_code == 400
    assert As(tc, "ravi").post(f"/meetings/{mid}/reaction", json={"kind": "agree"}).status_code == 403  # not admitted
    saved = (board.sessions_dir() / f"{mid}.json").read_text()
    assert "agree" not in saved and "reaction" not in saved
    audit = [e for e in board.read_audit() if e["session"] == mid and e.get("kind") == "reaction"]
    assert audit and audit[-1]["by"] == "priya" and "agree" not in str(audit[-1])


# ---- present a screen (night-v3 5.2) -------------------------------------------------------------------------------------------------------

def test_who_may_present_a_screen_and_a_new_share_replaces_the_old(tc, monkeypatch):
    mid = started(tc, discussion=("TB-002",), noting=())
    owned("TB-002", owner="priya")  # priya presents TB-002 (the owner)
    join_and_admit(tc, mid, "priya"); join_and_admit(tc, mid, "ravi")
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    v = As(tc, "ravi").get(f"/meetings/{mid}").json()
    assert v["can"]["present"] is False and v["present_allowed"] == [] and v["presenting"] is None and v["current"]["presenting"] is None
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["can"]["present"] is True   # the case's presenter
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["can"]["present"] is True    # the coordinator
    assert As(tc, "ravi").post(f"/meetings/{mid}/presenting", json={"on": True}).status_code == 403
    r = As(tc, "priya").post(f"/meetings/{mid}/presenting", json={"on": True})
    assert r.status_code == 200 and r.json()["presenting"] == "priya", r.text
    assert events[-1] == {**events[-1], "type": "presenting", "user": "priya", "on": True}
    assert As(tc, "ravi").get(f"/meetings/{mid}").json()["presenting"] == "priya"
    # ravi cannot stop priya's share; the coordinator allows ravi, whose share replaces priya's
    assert As(tc, "ravi").post(f"/meetings/{mid}/presenting", json={"on": False}).status_code == 403
    assert As(tc, "ravi").post(f"/meetings/{mid}/present-allow", json={"user": "ravi"}).status_code == 403
    assert As(tc, "anil").post(f"/meetings/{mid}/present-allow", json={"user": "meena"}).status_code == 409  # not admitted
    r = As(tc, "anil").post(f"/meetings/{mid}/present-allow", json={"user": "ravi", "allowed": True})
    assert r.status_code == 200 and r.json()["present_allowed"] == ["ravi"] and events[-1]["type"] == "present_allowed" and events[-1]["users"] == ["ravi"]
    assert As(tc, "ravi").get(f"/meetings/{mid}").json()["can"]["present"] is True
    r = As(tc, "ravi").post(f"/meetings/{mid}/presenting", json={"on": True})
    assert r.status_code == 200 and r.json() == {"presenting": "ravi", "replaced": "priya"}
    assert [e for e in events if e["type"] == "presenting"][-2:] == [{**events[-2], "user": "priya", "on": False, "replaced": True}, {**events[-1], "user": "ravi", "on": True}]
    # the coordinator stops it; withdrawing the right ends a share too; the next case clears the share
    assert As(tc, "anil").post(f"/meetings/{mid}/presenting", json={"on": False}).status_code == 200
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["presenting"] is None
    As(tc, "ravi").post(f"/meetings/{mid}/presenting", json={"on": True})
    r = As(tc, "anil").post(f"/meetings/{mid}/present-allow", json={"user": "ravi", "allowed": False})
    assert r.status_code == 200 and r.json()["present_allowed"] == [] and events[-1] == {**events[-1], "type": "presenting", "user": "ravi", "on": False}
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["presenting"] is None
    As(tc, "priya").post(f"/meetings/{mid}/presenting", json={"on": True})
    As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-002", "TB-001"], "noting": []})
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["presenting"] is None
    kinds = [e["kind"] for e in board.read_audit() if e["session"] == mid]
    assert "presenting" in kinds and "present_allowed" in kinds


# ---- the meeting chat (night-v3 5.3) --------------------------------------------------------------------------------------------------------

def test_chat_is_for_admitted_members_kept_with_the_record_and_never_in_the_audit(tc, monkeypatch):
    mid = with_agenda(tc)
    join_and_admit(tc, mid, "priya")
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "ravi").post("/meetings/join", json={"code": code})  # ravi waits
    sent = []
    shapes = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, shape=None: (sent.append(ev), shapes.append(shape)) and True)
    meetings._CHATTED.clear()
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["can"]["chat"] is True  # before the start too
    r = As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": "  The PET report for Kavitha is signed now.  "})
    assert r.status_code == 200, r.text
    m = r.json()["message"]
    assert m["by"] == "priya" and m["by_name"] == "Dr Priya Nair" and m["text"] == "The PET report for Kavitha is signed now." and m["id"].startswith("C")
    assert sent[-1]["type"] == "chat" and sent[-1]["message"]["id"] == m["id"]
    # the event is private: a waiting viewer's socket gets nothing, a member's gets it
    sh = shapes[-1]
    assert sh("ravi", {"user": "ravi"}, sent[-1]) is None and sh("priya", {"user": "priya"}, sent[-1]) is sent[-1]
    assert As(tc, "ravi").post(f"/meetings/{mid}/chat", json={"text": "hello"}).status_code == 403
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["chat"][-1]["text"] == "The PET report for Kavitha is signed now."
    assert As(tc, "ravi").get(f"/meetings/{mid}").json()["chat"] == []
    assert "The PET report for Kavitha" in (board.sessions_dir() / f"{mid}.json").read_text()  # kept with the meeting record
    audit = [e for e in board.read_audit() if e["session"] == mid and e.get("kind") == "chat"]
    assert audit and audit[-1]["chars"] == len("The PET report for Kavitha is signed now.") and "PET" not in str(audit[-1])
    assert As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": ""}).status_code == 400
    assert As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": "x" * 1001}).status_code == 413
    for i in range(meetings.CHAT_PER_MINUTE):
        As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": f"line {i}"})
    assert As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": "one more"}).status_code == 429
    # questions never land in the chat
    As(tc, "anil").post(f"/meetings/{mid}/start")
    As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Is the PET final?"})
    assert all("PET final" not in x["text"] for x in As(tc, "priya").get(f"/meetings/{mid}").json()["chat"])


# ---- the case flow: the quorum, the presenter, the elapsed time (night-v3 5.4) ------------------------------------------------------------

def test_quorum_presenter_and_elapsed_time(tc, monkeypatch):
    mid = started(tc, discussion=("TB-002", "TB-001"), noting=())
    owned("TB-002", owner="priya")
    join_and_admit(tc, mid, "priya")
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    q = v["quorum"]
    assert q["total"] == 5 and q["present"] == 0 and [h["id"] for h in q["heads"]][:2] == ["radiology", "medical_oncology"]
    # priya (Breast Surgery) fills the surgical seat for her own Case File, as the decision record's rule says (postboard.pmjay_seat)
    assert q["pmjay"]["surgical"] is True and q["pmjay"]["present"] == 1 and q["pmjay"]["total"] == 3 and "advises" in q["pmjay"]["note"] and q["pmjay"]["seat_check"] is True
    assert "Radiology" in q["agents"] and "Pathology" in q["agents"]
    assert v["current"]["presenter"] == {"user": "priya", "name": "Dr Priya Nair", "department": "breast_surgery", "department_name": "Breast Surgery"}
    assert v["current"]["elapsed_seconds"] == 0
    # a head joins: present as a person, no longer stood in for; PM-JAY counts Medical Oncology
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    join_and_admit(tc, mid, "dev")
    assert events[-1]["type"] == "admit" and events[-1]["quorum"]["present"] == 1
    q = As(tc, "priya").get(f"/meetings/{mid}").json()["quorum"]
    med = next(h for h in q["heads"] if h["id"] == "medical_oncology")
    assert med["present"] is True and med["by"] == "Dr Dev" and "Medical Oncology" not in q["agents"] and q["pmjay"]["medical"] is True and q["pmjay"]["present"] == 2
    # the elapsed time counts from the moment the case came on the floor (not the countdown), is kept when the case ends; the record keeps the quorum
    As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "start", "minutes": 10})
    s = meetings.need(mid); s["live"]["case_started_at"] -= 125; board.save_session(s)
    assert 124 <= As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["elapsed_seconds"] <= 127
    # Stop then Start with the same minutes resumes the countdown; other minutes reset it (review M2)
    s = meetings.need(mid); s["live"]["timer"]["started_at"] -= 100; board.save_session(s)
    As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "stop"})
    left = As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["timer"]["seconds_left"]
    assert 495 <= left <= 501
    assert As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "start", "minutes": 10}).json()["timer"]["seconds_left"] <= 501
    assert As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "start", "minutes": 5}).json()["timer"]["seconds_left"] == 300
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/end")
    assert r.status_code == 200
    row = As(tc, "priya").get(f"/meetings/{mid}").json()["agenda"]["discussion"][0]
    assert row["case_id"] == "TB-002" and 124 <= row["elapsed_seconds"] <= 128
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json={"outcome": "decision", "decision_text": "Surgery first", "intent": "curative", "responsible_doctor": "Dr Priya Nair"})
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["quorum"]["present"] == 1 and rec["quorum"]["agents"] and rec["quorum"]["pmjay"]["present"] == 2
    assert "quorum" in store.get_state("TB-002")["board_records"][-1]
    # the presenter changes with the case (TB-001 has no owner, no chosen presenter and was created by the coordinator: nobody); the event carries the quorum
    c = store.get_case("TB-001"); c["team"] = None; c.pop("presenter", None); c["created_by"] = "anil"; store.save_case(c)
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    assert events[-1]["type"] == "current" and events[-1]["presenter"] is None and events[-1]["quorum"]["total"] == 5 and events[-1]["elapsed_seconds"] <= 1


def test_the_creating_doctor_presents_when_the_file_has_no_team_owner(tc):
    mid = started(tc, discussion=("TB-002",), noting=())
    c = store.get_case("TB-002"); c["department"] = "breast_surgery"; c["team"] = {"residents": []}; c["created_by"] = "priya"; c.pop("presenter", None); store.save_case(c)
    join_and_admit(tc, mid, "priya")
    v = As(tc, "priya").get(f"/meetings/{mid}").json()
    assert v["current"]["presenter"]["user"] == "priya" and v["agenda"]["discussion"][0]["presenter_name"] == "Dr Priya Nair" and v["can"]["present"] is True
    # created by the coordinator, or by a doctor of another department: nobody presents by default
    c = store.get_case("TB-002"); c["created_by"] = "anil"; store.save_case(c)
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["presenter"] is None
    c = store.get_case("TB-002"); c["created_by"] = "ravi"; store.save_case(c)
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["presenter"] is None
    # a chosen presenter or a team owner still wins
    c = store.get_case("TB-002"); c["created_by"] = "priya"; c["team"] = {"owner": "asha", "residents": []}; store.save_case(c)
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["current"]["presenter"]["user"] == "asha"


def test_old_sessions_route_never_carries_the_chat_and_filters_the_questions(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    meetings._CHATTED.clear()
    assert As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": "The MRI for SYN-200417 is signed."}).status_code == 200
    As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Is the MRI final?"})
    for who in ("ravi", "anil", "priya"):  # a doctor never admitted (Radiology is on the attendance sheet), the coordinator, a member
        r = As(tc, who).get(f"/sessions/{mid}")
        assert r.status_code == 200, (who, r.text)
        assert "chat" not in r.json()["session"] and "SYN-200417 is signed" not in r.text, who
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["chat"][-1]["text"].endswith("is signed.")


def test_an_outside_expert_reads_the_chat_with_the_identity_withheld(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "guest").post("/meetings/join", json={"code": code})
    As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "guest"})
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    sent, shapes = [], []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, shape=None: (sent.append(ev), shapes.append(shape)) and True)
    meetings._CHATTED.clear()
    assert As(tc, "priya").post(f"/meetings/{mid}/chat", json={"text": "SYN-200417: the biopsy is final."}).status_code == 200
    assert As(tc, "priya").get(f"/meetings/{mid}").json()["chat"][-1]["text"].startswith("SYN-200417")
    g = As(tc, "guest").get(f"/meetings/{mid}").json()["chat"][-1]["text"]
    assert "SYN-200417" not in g and "[withheld]" in g
    shaped = shapes[-1]("guest", org.roles("guest"), sent[-1])
    assert "SYN-200417" not in shaped["message"]["text"] and "[withheld]" in shaped["message"]["text"]
    assert shapes[-1]("priya", org.roles("priya"), sent[-1])["message"]["text"].startswith("SYN-200417")


def test_quorum_counts_the_attendance_sheet_and_the_pmjay_seat(tc, monkeypatch):
    mid = started(tc, discussion=("TB-002",), noting=())
    # nobody admitted, but Radiology marked present on the old attendance sheet: a head present without a name
    s = meetings.need(mid); s.setdefault("attendance", {})["radiology"] = "present"; board.save_session(s)
    q = As(tc, "anil").get(f"/meetings/{mid}").json()["quorum"]
    rad = next(h for h in q["heads"] if h["id"] == "radiology")
    assert rad["present"] is True and rad["by"] is None and q["present"] == 1 and "Radiology" not in q["agents"]
    assert q["pmjay"]["present"] == 0 and q["pmjay"]["seat_check"] is False and "not_applicable" not in q["pmjay"]
    # the surgical seat follows postboard's rule: a surgeon of the Case File's own surgical department fills it with a check note
    monkeypatch.setattr(board, "_case_surgical", lambda c: ["breast_surgery"])
    base0 = org.hospital()
    monkeypatch.setattr(org, "hospital", lambda: {**base0, "surgical_departments": ["surgical_oncology", "breast_surgery"]})
    join_and_admit(tc, mid, "priya")
    q = As(tc, "anil").get(f"/meetings/{mid}").json()["quorum"]
    assert q["pmjay"]["surgical"] is True and q["pmjay"]["present"] == 1 and q["pmjay"]["seat_check"] is True and "check the PM-JAY requirement" in q["pmjay"]["seat_note"]
    # a hospital that is not empanelled: the line does not apply
    base = org.hospital()
    monkeypatch.setattr(org, "hospital", lambda: {**base, "pmjay_empanelled": False})
    q = As(tc, "anil").get(f"/meetings/{mid}").json()["quorum"]
    assert q["pmjay"]["not_applicable"] is True and "not PM-JAY empanelled" in q["pmjay"]["note"]


def test_withdrawing_a_presenting_coordinators_right_does_not_stop_the_share(tc, monkeypatch):
    mid = started(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "anil").post("/meetings/join", json={"code": code})  # the coordinator joins by code too (present at once)
    events = []
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: events.append(ev) or True)
    assert As(tc, "anil").post(f"/meetings/{mid}/presenting", json={"on": True}).json()["presenting"] == "anil"
    assert As(tc, "anil").post(f"/meetings/{mid}/present-allow", json={"user": "anil", "allowed": False}).status_code == 200
    assert As(tc, "anil").get(f"/meetings/{mid}").json()["presenting"] == "anil"  # the coordinator presents by right, not by permission
    assert events[-1]["type"] == "present_allowed"


# ---- meetings-v2 review fixes (2 Nov 2026, docs/meetings-v2/research/01_code_review.md) -------------------------------------------------

def test_opening_images_keeps_what_changed_while_the_hospital_system_answered(tc, monkeypatch):
    """Finding 1: the images lookup waits on the hospital system; a Next pressed meanwhile is kept, not undone by the late save."""
    mid = started(tc)
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    doc = store.add_document_file("TB-001", "ct_thorax.pdf", b"synthetic")
    doc["classification"] = {"title": "CT THORAX", "doc_type": "ct"}
    doc["his"] = {"imaging_study_ref": "ImagingStudy/img-1"}
    store.save_doc("TB-001", doc)
    monkeypatch.setattr(his_client, "client", lambda: object())

    async def slow_study(cid, d, client):
        meetings.set_current(mid, "anil", "TB-002")  # the coordinator moves on while the hospital system answers
        return {"available": True, "study_uid": UID, "modality": "CT"}
    monkeypatch.setattr(pacs, "study_for_doc", slow_study)
    r = As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "moved_on"
    s = board.get(mid)
    assert s["current"] == "TB-002" and not (s.get("live") or {}).get("opened")


def test_a_concern_given_after_the_outcome_reaches_the_board_record(tc):
    """Finding 5: a Concern card after the outcome was saved corrects the record (a new version with its reason) and the minutes."""
    owned("TB-002")
    mid = started(tc)
    join_and_admit(tc, mid, "suresh")
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    body = {"outcome": "decision", "decision_text": "Neoadjuvant chemotherapy, then surgery.", "intent_as_stated": "Curative",
            "responsible_doctor": "Dr Priya Nair", "next_step": "Medical Oncology consult", "next_step_date": "25/10/2026", "members_present": ["Dr Suresh"]}
    rec = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-002/decision", json=body).json()["record"]
    assert not rec.get("concerns")
    r = As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": False, "note": "Repeat the axillary ultrasound"})
    assert r.status_code == 200, r.text
    st = store.get_state("TB-002")
    now = next(b for b in st["board_records"] if b["id"] == rec["id"])
    assert [c["text"] for c in now["concerns"]] == ["Repeat the axillary ultrasound"] and "Repeat the axillary ultrasound" in now["divergent_opinions"]
    assert len(now["versions"]) == 2 and "after the outcome was recorded" in now["versions"][-1]["reason"]
    # the same card again changes nothing more
    As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-002/card", json={"agree": False, "note": "Repeat the axillary ultrasound"})
    assert len(next(b for b in store.get_state("TB-002")["board_records"] if b["id"] == rec["id"])["versions"]) == 2
    m = As(tc, "anil").get(f"/sessions/{mid}/minutes?format=json").json()
    assert "Repeat the axillary ultrasound" in str(next(c for c in m["cases"] if c["case_id"] == "TB-002"))


def test_an_outside_expert_gets_no_ask_or_card_buttons(tc):
    """Finding 8: those routes refuse a login that is not placed, so the view does not offer them."""
    mid = started(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "guest").post("/meetings/join", json={"code": code})
    As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "guest"})
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    can = As(tc, "guest").get(f"/meetings/{mid}").json()["can"]
    assert can["member"] is True and can["ask"] is False and can["ask_agents"] is False and can["card"] is False
    join_and_admit(tc, mid, "suresh")
    can = As(tc, "suresh").get(f"/meetings/{mid}").json()["can"]
    assert can["ask"] is True and can["card"] is True


def test_moving_a_meeting_moves_its_case_files_and_tells_the_members(tc):
    """Finding 10: a new date reaches the Case Files on the agenda (their board date), the 15-minute notice is sent again for the new time,
    and the member departments are told once the agenda was sent."""
    mid = with_agenda(tc)
    assert store.get_case("TB-001")["board_date"] == board.get(mid)["date"]
    As(tc, "anil").post(f"/meetings/{mid}/send-agenda")
    s = board.get(mid); s["starting_notified_at"] = store.now_iso(); board.save_session(s)
    new = (date.today() + timedelta(days=9)).isoformat()
    r = As(tc, "anil").put(f"/meetings/{mid}", json={"date": new, "time": "15:00"})
    assert r.status_code == 200, r.text
    assert store.get_case("TB-001")["board_date"] == new and store.get_case("TB-003")["board_date"] == new
    assert "starting_notified_at" not in board.get(mid)
    assert any(n["kind"] == "agenda" and "moved to" in n["title"] for n in notify.for_roles({"user": "x", "known": True, "departments": {"radiology": "member"}}, limit=None))


def test_not_discussed_keeps_an_agenda_change_made_while_the_record_was_saved(tc, monkeypatch):
    """Finding 13: the next meeting is read after the board record is saved (seconds), so a Case File added to it meanwhile stays."""
    mid = started(tc)
    nxt = new_meeting(tc, date_=(date.today() + timedelta(days=8)).isoformat(), time_="09:00")
    real = meetings.postboard.record_decision

    async def slow_record(cid, rec, user):
        meetings.add_to_agenda(nxt, "anil", "TB-003", "noting", "added meanwhile")
        return await real(cid, rec, user)
    monkeypatch.setattr(meetings.postboard, "record_decision", slow_record)
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "not_discussed", "not_discussed_reason": "information_missing"})
    assert r.status_code == 200, r.text
    v = As(tc, "anil").get(f"/meetings/{nxt}").json()
    assert [x["case_id"] for x in v["agenda"]["discussion"]] == ["TB-001"] and [x["case_id"] for x in v["agenda"]["noting"]] == ["TB-003"]


def test_a_join_code_lasts_through_the_meeting_it_was_made_for(tc):
    """Finding 2: a code made days before the meeting still works on the day (12 hours after the start at least)."""
    day = (date.today() + timedelta(days=3)).isoformat()
    mid = new_meeting(tc, date_=day, time_="14:00")
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()
    assert datetime.fromisoformat(code["expires_at"]) >= datetime.fromisoformat(f"{day}T14:00") + timedelta(hours=12)


def test_the_api_check_rules(tc, monkeypatch):
    """The meetings-v2 API check (1.2): no meeting in the past; a planned meeting is cancelled, not ended; no card or decision before the
    start; an over-long question is refused, not cut; a spotlight that is not a list is refused; a refusal says the action in words."""
    past = (date.today() - timedelta(days=1)).isoformat()
    r = As(tc, "anil").post("/meetings", json={"date": past, "time": "10:00"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "past"
    mid = with_agenda(tc)
    assert As(tc, "anil").put(f"/meetings/{mid}", json={"date": past}).json()["detail"]["code"] == "past"
    r = As(tc, "anil").post(f"/meetings/{mid}/end")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_started"
    join_and_admit(tc, mid, "suresh")
    assert As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-001/card", json={"agree": True}).json()["detail"]["code"] == "not_started"
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "noted"}).json()["detail"]["code"] == "not_started"
    assert As(tc, "anil").post(f"/meetings/{mid}/start").status_code == 200
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    monkeypatch.setattr(meetings, "answer_in_background", lambda *a, **k: None)
    r = As(tc, "suresh").post(f"/meetings/{mid}/questions", json={"text": "x" * 1001})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_long"
    r = As(tc, "anil").post(f"/meetings/{mid}/spotlight", json={"users": "suresh"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_users"
    r = As(tc, "suresh").post(f"/meetings/{mid}/start")
    msg = str(r.json()["detail"])
    assert r.status_code == 403 and "plan or run a meeting" in msg and "'session'" not in msg
