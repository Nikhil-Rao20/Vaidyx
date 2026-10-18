"""The fixes of the security review (docs/ui/build/SECURITY_REVIEW.md, 18 Oct 2026): one test or more per finding, each failing
before its fix and passing after. Hermetic: the shared meeting test app (a fake login system, the live route class), synthetic
Case Files in the conftest temporary data root, never the real case (a synthetic id stands in for it in config.PROTECTED_CASES),
no model call."""
import asyncio, json, os, stat, subprocess, time
from datetime import date, timedelta
from pathlib import Path

import pytest

from tumour_board import access, board, config, dept_requests, live, meetings, notify, org, profiles, push, store, team
from tumour_board.api import common
from tumour_board.tests import util
from tumour_board.tests.test_nik_meetings import TOKENS, As, app, owned, started, tc, with_agenda, join_and_admit  # noqa: F401  (fixtures)

PROT = "TB-PROT-SYN"        # stands in for the real Case File: a synthetic id put in config.PROTECTED_CASES
PROT_NAME = "PROTECTED, Synthetic Patient"
CREATOR = "owner1"          # the login that created it (a Breast Surgery doctor)
NEXT = (date.today() + timedelta(days=7)).isoformat()
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def people(app, monkeypatch):
    """The meeting test organisation plus the creator of the protected Case File; its session token for the fake login system."""
    o = org.load()
    o["users"][CREATOR] = {"departments": {"breast_surgery": "member"}, "display_name": "Dr Owner"}
    org.save(o, by="test")
    monkeypatch.setitem(TOKENS, f"tok-{CREATOR}", CREATOR)
    common.forget_sessions()
    yield
    common.forget_sessions()


@pytest.fixture
def protected(people, monkeypatch):
    """A protected Case File (synthetic) owned by Breast Surgery, listed for a board date, with a request to Radiology, a reading that
    waits for the owner's confirmation and notifications to Breast Surgery, Radiology and the coordinator; plus a second, ownerless one
    created by the Vaidyx admin (the shape of the real case)."""
    monkeypatch.setattr(config, "PROTECTED_CASES", {PROT, PROT + "-2"})
    c = store.create_case(PROT, {"name": PROT_NAME, "mrn": "SYN-PROT-01", "agesex": "50 Y / F"}, "breast", board_date=NEXT, created_by=CREATOR)
    c["department"] = "breast_surgery"
    c["proposals"] = [{"id": "P1", "status": "pending", "action": "urgency", "by": "asha", "at": store.now_iso(), "payload": {"level": 2}}]
    store.save_case(c)
    st = store.get_state(PROT)
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "breast_imaging", "label": "Mammogram", "department": "Radiology",
                      "department_id": "radiology", "status": "pending", "created": store.now_iso(), "due": NEXT, "history": [],
                      "sent": {"by": CREATOR, "at": store.now_iso(), "count": 1}}]
    st["gate"] = {"passed": False, "requirements": [{"id": "receptor_status", "label": "Receptor status", "status": "needs_confirmation"}], "evaluated": store.now_iso()}
    store.save_state(PROT, st)
    store.create_case(PROT + "-2", {"name": PROT_NAME, "mrn": "SYN-PROT-02"}, "breast", created_by="admin")
    for to in ({"department": "breast_surgery"}, {"department": "radiology"}, {"role": "coordinator"}, {"user": "priya"}):
        notify.notify(to, "board_ready", PROT, f"Ready for the board: {PROT_NAME} ({PROT})", "synthetic")
    return PROT


def _ids(obj) -> str:
    return json.dumps(obj)


# ---- finding 0: the protected Case File is never listed or opened for anyone else --------------------------------------------------

def test_finding0_protected_case_file_is_listed_for_nobody_else(tc, protected):
    for who in ("priya", "anil", "ravi", "asha", "guest", "tbroot", "mohan"):
        a = As(tc, who)
        for path in ("/cases", "/case-list", "/waiting", "/inbox", "/notifications", "/home", f"/sessions/candidates?date={NEXT}", f"/metrics/agenda?date={NEXT}"):
            r = a.get(path)
            assert PROT not in r.text and PROT_NAME not in r.text, (who, path, r.status_code)
        r = a.get(f"/cases/{PROT}")
        assert r.status_code == 403 and PROT_NAME not in r.text, (who, r.text)
        assert a.get(f"/cases/{PROT}/audit").status_code == 403 and a.get(f"/cases/{PROT}/slots").status_code == 403
    assert As(tc, "anil").get("/me").json()["counts"]["unread"] == 0  # the bell does not count it either
    # its creator sees it, as before
    mine = As(tc, CREATOR).get("/cases").json()["cases"]
    assert PROT in {c["case_id"] for c in mine} and PROT + "-2" not in {c["case_id"] for c in mine}
    assert As(tc, CREATOR).get(f"/cases/{PROT}").status_code == 200
    assert PROT in As(tc, CREATOR).get("/case-list").text
    # a meeting never takes it
    mid = with_agenda(tc)
    r = As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": PROT, "list": "discussion"})
    assert r.status_code in (400, 403, 404) and PROT_NAME not in r.text


def test_finding0_protected_case_file_opens_for_a_vaidyx_admin_only_inside_a_window(tc, protected):
    assert As(tc, "admin").get(f"/cases/{PROT}").status_code == 403
    access.open_break_glass("admin", PROT, "synthetic test window")
    assert As(tc, "admin").get(f"/cases/{PROT}").status_code == 200
    assert As(tc, "priya").get(f"/cases/{PROT}").status_code == 403
    assert As(tc, "admin").get(f"/cases/{PROT}-2").status_code == 200  # the ownerless one the admin created


def test_finding0_a_case_file_without_an_owner_is_for_the_coordinator_and_its_creator(tc, people):
    c = store.get_case("TB-001")
    assert not c.get("department") and c["created_by"] == "admin"
    assert As(tc, "priya").get("/cases/TB-001").status_code == 403
    assert "TB-001" not in {x["case_id"] for x in As(tc, "priya").get("/cases").json()["cases"]}
    assert As(tc, "anil").get("/cases/TB-001").status_code == 200
    c["created_by"] = "priya"; store.save_case(c)
    assert As(tc, "priya").get("/cases/TB-001").status_code == 200
    assert As(tc, "ravi").get("/cases/TB-001").status_code == 403


# ---- finding 1: /quote follows the record scope of a department that was only asked -------------------------------------------------

def test_finding1_quote_is_limited_to_the_records_in_scope(tc, people):
    owned("TB-002")
    st = store.get_state("TB-002")
    st["actions"] = [{"id": "A9", "source": "pre_authorization", "requirement": "x", "label": "Mammogram", "department": "Radiology", "department_id": "radiology",
                      "status": "pending", "created": store.now_iso(), "history": [], "sent": {"by": "priya", "at": store.now_iso()}}]
    store.save_state("TB-002", st)
    docs = store.list_docs("TB-002")
    other = next(d for d in docs if org.department_id(d.get("department") or "") != "radiology")
    assert access.scope(org.roles("ravi"), store.get_case("TB-002")) == access.REQUESTS
    r = As(tc, "ravi").get(f"/cases/TB-002/documents/{other['doc_id']}/quote?text=anything")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "out_of_scope"
    assert As(tc, "ravi").get(f"/cases/TB-002/documents/{other['doc_id']}").status_code == 403  # the same rule as the record itself
    assert As(tc, "priya").get(f"/cases/TB-002/documents/{other['doc_id']}/quote?text=anything").status_code == 200


# ---- findings 2 and 6: the Vaidyx admin runs no meeting; break-glass is read only ---------------------------------------------------

def test_finding2_the_vaidyx_admin_does_not_manage_meetings_or_read_the_whole_log(tc, people):
    mid = with_agenda(tc)
    a = As(tc, "admin")
    assert a.post("/meetings", json={"date": NEXT, "time": "10:00"}).status_code == 403
    assert a.post(f"/meetings/{mid}/code").status_code == 403
    assert a.post(f"/meetings/{mid}/start").status_code == 403
    assert a.post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "noted"}).status_code == 403
    assert a.get(f"/meetings/{mid}").status_code == 403  # no window: the meeting is not open to it
    assert mid not in {m["id"] for m in a.get("/meetings").json()["meetings"]}
    assert a.get("/activity").status_code == 403
    assert a.get("/activity?case_id=TB-001").status_code == 403
    access.open_break_glass("admin", "TB-001", "synthetic test window")
    assert a.get("/activity?case_id=TB-001").status_code == 200  # one Case File, inside its window
    assert a.get("/activity").status_code == 403 and a.get("/activity?case_id=TB-002").status_code == 403
    assert a.get(f"/meetings/{mid}").status_code == 200 and a.get(f"/meetings/{mid}").json()["can"]["manage"] is False
    assert As(tc, "anil").get("/activity").status_code == 200  # the coordinator keeps it


def test_finding6_a_break_glass_window_is_read_only(tc, people):
    c = owned("TB-002")
    rl = org.roles("admin", vaidyx_admin=True)
    access.open_break_glass("admin", "TB-002", "synthetic test window")
    assert access.scope(rl, c) == access.FULL
    for action in ("view", "read_case", "read_audit", "ask"):
        assert access.may(rl, action, c), action
    for action in sorted(access.OWNER_ACTIONS | {"upload", "archive", "board_record"}):
        assert not access.may(rl, action, c), action
    a = As(tc, "admin")
    assert a.get("/cases/TB-002").status_code == 200
    for path, body in (("/cases/TB-002/urgency", {"level": 2}), ("/cases/TB-002/archive", {"reason": "x"}), ("/cases/TB-002/ready", {"ready": True}),
                       ("/cases/TB-002/participants", {"add": ["radiology"]})):
        r = a.put(path, json=body) if path.endswith(("participants", "urgency")) else a.post(path, json=body)
        assert r.status_code == 403 and "read only" in r.text, (path, r.status_code, r.text[:200])


# ---- finding 4: a password change ends the other sessions; the socket needs a chosen password -------------------------------------------

def test_finding4_password_change_revokes_the_other_sessions(tc, people, monkeypatch):
    mgr = tc.app.state.auth_manager
    calls = []
    monkeypatch.setattr(mgr, "change_password", lambda u, cur, new: cur == "old-pass-123", raising=False)
    monkeypatch.setattr(mgr, "must_change_password", lambda u: False, raising=False)
    monkeypatch.setattr(mgr, "revoke_user_sessions", lambda u, except_token=None: calls.append((u, except_token)) or 2, raising=False)
    from tumour_board.api import me
    me.PASSWORD_LIMIT._hits.clear()
    r = As(tc, "priya").post("/me/password", json={"current_password": "old-pass-123", "new_password": "a-brand-new-pass-9"})
    assert r.status_code == 200 and r.json()["other_sessions_ended"] == 2
    assert calls == [("priya", "tok-priya")]  # every session but this one
    assert any(e["kind"] == "password_changed" and e.get("other_sessions_ended") == 2 for e in org.read_audit())


def test_finding4_the_socket_refuses_a_first_password(tc, people, monkeypatch):
    mid = with_agenda(tc)
    mgr = tc.app.state.auth_manager
    monkeypatch.setattr(mgr, "must_change_password", lambda u: u == "anil", raising=False)
    from starlette.websockets import WebSocketDisconnect
    tc.cookies.set("vaidyx_session", "tok-anil")
    with pytest.raises(WebSocketDisconnect) as e:
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws"):
            pass
    assert e.value.code == 1008


# ---- finding 5: the root admin and the clinical roles stay on separate logins ---------------------------------------------------------------

def test_finding5_root_admin_logins_take_no_clinical_role(tc, people):
    from tumour_board import accounts
    rl = org.roles("tbroot")
    with pytest.raises(accounts.AccountError) as e:
        accounts.update_account(None, "tbroot", rl, "tbroot", {"coordinator": True})
    assert e.value.status == 409 and "separate logins" in str(e.value)
    with pytest.raises(accounts.AccountError):
        accounts.update_account(None, "tbroot", rl, "tbroot", {"departments": {"breast_surgery": "member"}})
    with pytest.raises(accounts.AccountError):
        accounts.update_account(None, "tbroot", rl, "tbroot", {"auditor": True})
    with pytest.raises(accounts.AccountError):
        accounts.update_account(None, "tbroot", rl, "priya", {"root_admin": True})  # a placed clinical login never becomes a root admin
    with pytest.raises(accounts.AccountError):
        accounts.create_account(None, "tbroot", "newroot@hospital.example", "a-password-1234", root_admin=True, coordinator=True)
    with pytest.raises(accounts.AccountError):
        accounts.place_doctor("tbroot", "breast_surgery", "tbroot", caller=rl)
    assert not org.roles("tbroot")["coordinator"] and not org.roles("tbroot")["departments"] and "priya" not in org.load()["admins"]
    r = As(tc, "tbroot").post("/setup/board", json={"coordinators": ["tbroot"]})
    assert r.status_code == 409 and "separate logins" in r.text
    o = json.loads(json.dumps(org.load())); o["users"]["tbroot"]["coordinator"] = True  # a copy: org.load() is the cached organisation
    r = As(tc, "tbroot").put("/org", json={"users": o["users"]})
    assert r.status_code == 409 and not org.roles("tbroot")["coordinator"]


# ---- finding 7: the meeting reminder follows may_remind, the viewer rule and the archive -------------------------------------------------

def test_finding7_meeting_remind_checks_the_case_file(tc, people):
    owned("TB-002")
    mid = with_agenda(tc)
    sent = []
    import tumour_board.dept_requests as dr
    orig = dr.remind_owner
    dr.remind_owner = lambda case_id, by, roles, note="": sent.append((case_id, by)) or {"to": "breast_surgery"}
    try:
        assert As(tc, "mohan").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"}).status_code == 403  # not a viewer, not the owner
        assert As(tc, "dev").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"}).status_code == 403  # a treating head of another department
        assert As(tc, "priya").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"}).status_code == 200  # the owner's consultant
        assert As(tc, "anil").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"}).status_code == 200
        team.archive("TB-002", "priya", "synthetic archive")
        r = As(tc, "anil").post(f"/meetings/{mid}/remind", json={"case_id": "TB-002"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "archived"
    finally:
        dr.remind_owner = orig
    assert sent == [("TB-002", "priya"), ("TB-002", "anil")]


# ---- finding 8: an archived Case File changes through no agenda, decision or intake path --------------------------------------------------

def test_finding8_archived_case_files_join_no_agenda_and_get_no_decision(tc, people):
    owned("TB-002")
    mid = with_agenda(tc, discussion=("TB-001",), noting=())
    team.archive("TB-002", "priya", "synthetic archive")
    before = store.get_case("TB-002")
    r = As(tc, "anil").post(f"/meetings/{mid}/agenda/add", json={"case_id": "TB-002", "list": "discussion"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "archived"
    r = As(tc, "anil").put(f"/meetings/{mid}/agenda", json={"discussion": ["TB-001", "TB-002"], "noting": []})
    assert r.status_code == 409
    assert "TB-002" not in {x["case_id"] for x in board.listed_for_date(store.get_case("TB-002").get("board_date") or NEXT)} if store.get_case("TB-002").get("board_date") else True
    # a Case File archived after it joined the agenda: no decision, no change through the agenda link
    mid2 = with_agenda(tc, discussion=("TB-001", "TB-003"), noting=())
    team.archive("TB-003", "anil", "synthetic archive")
    r = As(tc, "anil").post(f"/meetings/{mid2}/cases/TB-003/decision", json={"outcome": "noted"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "archived"
    r = As(tc, "anil").put(f"/meetings/{mid2}/agenda", json={"discussion": ["TB-003", "TB-001"], "noting": []})  # kept, reordered
    assert r.status_code == 200
    assert store.get_case("TB-002").get("meeting_id") == before.get("meeting_id")
    with pytest.raises(ValueError):
        asyncio.run(__import__("tumour_board.postboard", fromlist=["x"]).record_decision("TB-003", {"decision_text": "x"}, "anil"))


def test_finding8_intake_never_files_into_an_archived_case_file(tc, people):
    from tumour_board import intake
    team.archive("TB-003", "anil", "synthetic archive")
    assert "TB-003" not in {p["case_id"] for p in intake.patients_for_matching()}
    store.save_intake({"doc_id": "I1", "filename": "x.txt", "rel_path": "x.txt", "state": "needs_matching", "sha256": "0" * 64})
    with pytest.raises(ValueError):
        intake.file_to_case("I1", "TB-003", "anil")


# ---- finding 9: an outside expert sees the current case only, in session, without identity ------------------------------------------------

def test_finding9_outside_expert_slides(tc, people):
    c = owned("TB-002")
    c["patient"]["dob"] = "1978-03-14"; c["patient"]["ids"] = [{"kind": "ip_no", "value": "IP/26/000777"}]; store.save_case(c)
    doc = store.add_document_file("TB-002", "Discharge summary SLIDE.txt", b"synthetic")
    doc["classification"] = {"title": f"Discharge summary of {c['patient']['name']}, UHID {c['patient']['mrn']}, IP/26/000777, DOB 14/03/1978", "doc_type": "mammogram"}
    doc["state"] = "ready"; store.save_doc("TB-002", doc)
    mid = with_agenda(tc)
    join_and_admit(tc, mid, "guest")
    g = As(tc, "guest")
    r = g.get(f"/meetings/{mid}/cases/TB-002/slides")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_current"  # planned, not in session
    As(tc, "anil").post(f"/meetings/{mid}/start")
    assert g.get(f"/meetings/{mid}/cases/TB-002/slides").status_code == 403  # TB-001 is on the floor
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    r = g.get(f"/meetings/{mid}/cases/TB-002/slides")
    assert r.status_code == 200
    text = json.dumps(r.json())
    for secret in (c["patient"]["name"], c["patient"]["mrn"], "IP/26/000777", "14/03/1978", "1978-03-14"):
        assert secret not in text, secret
    assert meetings.WITHHELD in text
    member = As(tc, "anil").get(f"/meetings/{mid}/cases/TB-002/slides").json()
    assert c["patient"]["mrn"] in json.dumps(member)  # the coordinator sees the record as it is
    c = store.get_case("TB-002"); c["consent"] = {"outside_discussion": True}; store.save_case(c)
    assert "IP/26/000777" in json.dumps(g.get(f"/meetings/{mid}/cases/TB-002/slides").json())  # with the owner's recorded consent


# ---- finding 10: an uploaded original that is not a PDF or an image is a sandboxed download -------------------------------------------------

def test_finding10_originals_other_than_pdf_and_images_are_downloads(tc, people):
    d = store.add_document_file("TB-001", "report.xml", b"<?xml version='1.0'?><html xmlns='http://www.w3.org/1999/xhtml'><script>alert(1)</script></html>")
    store.save_doc("TB-001", {**d, "state": "ready"})
    r = As(tc, "anil").get(f"/cases/TB-001/documents/{d['doc_id']}/file")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment") and r.headers["content-type"] == "application/octet-stream"
    assert "sandbox" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"
    p = store.add_document_file("TB-001", "scan.pdf", b"%PDF-1.4 synthetic")
    store.save_doc("TB-001", {**p, "state": "ready"})
    r = As(tc, "anil").get(f"/cases/TB-001/documents/{p['doc_id']}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and "attachment" not in r.headers.get("content-disposition", "")


# ---- finding 11: the Tumour Board idle timeout ---------------------------------------------------------------------------------------------

def test_finding11_an_idle_session_is_refused(tc, people, monkeypatch):
    a = As(tc, "anil")
    assert a.get("/me").status_code == 200
    real = time.time
    monkeypatch.setattr(common.time, "time", lambda: real() + common.IDLE_SECONDS - 60)
    assert a.get("/me", headers={"X-TB-Background": "1"}).status_code == 200  # a background poll counts nothing
    monkeypatch.setattr(common.time, "time", lambda: real() + common.IDLE_SECONDS + 60)
    r = a.get("/me")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "idle_timeout"
    assert a.get("/cases").status_code == 401  # it stays refused
    assert As(tc, "priya").get("/me").status_code == 200  # another session starts its own clock
    monkeypatch.setattr(common.time, "time", real)


def test_finding11_activity_keeps_the_session(tc, people, monkeypatch):
    a = As(tc, "anil")
    real = time.time
    for hours in (2, 5, 9, 15):  # active every few hours: never idle for 8
        monkeypatch.setattr(common.time, "time", lambda h=hours: real() + h * 3600)
        assert a.get("/me").status_code == 200, hours


def test_finding11_the_web_session_clears_its_caches_on_sign_out():
    src = (REPO / "web" / "tb-nik" / "src" / "lib" / "session.tsx").read_text(encoding="utf-8")
    sign_out = src.split("const signOut", 1)[1].split("}, [queryClient]);", 1)[0]
    assert "queryClient.clear()" in sign_out and "forgetLocal()" in sign_out and "unsubscribePush()" in sign_out
    assert '"tbnik.lastCase"' in src and "idle_timeout" in src
    assert "X-TB-Background" in (REPO / "web" / "tb-nik" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")


# ---- finding 14: published cases are a consultant's sign-off -----------------------------------------------------------------------------

def test_finding14_a_resident_cannot_add_or_remove_a_published_case(tc, people):
    owned("TB-002")
    body = {"result": {"title": "A synthetic case report", "authors": "Rao A", "journal": "J Synth", "year": 2024, "url": "https://example.org/x", "source": "local"},
            "quotes": []}
    r = As(tc, "asha").post("/cases/TB-002/published", json=body)
    assert r.status_code == 403 and ("consultant" in r.text or "resident" in r.text)
    assert As(tc, "asha").delete("/cases/TB-002/published/X1").status_code == 403
    assert As(tc, "priya").post("/cases/TB-002/published", json=body).status_code in (200, 400)  # the consultant passes the check


# ---- finding 15: helper chats follow the team chat's rule ---------------------------------------------------------------------------------

def test_finding15_helper_chat_is_for_the_treating_team(tc, people):
    owned("TB-002")
    c = store.get_case("TB-002"); c["participants"] = [{"department": "radiology", "since": store.now_iso(), "by": "priya"}]; store.save_case(c)
    assert access.scope(org.roles("ravi"), c) == access.FULL  # a supporting participant reads the Case File ...
    r = As(tc, "ravi").get("/cases/TB-002/helpers/radiology/chat")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "chat_forbidden"  # ... but never the helper threads
    assert As(tc, "ravi").post("/cases/TB-002/helpers/radiology/chat", json={"question": "x"}).status_code == 403
    assert As(tc, "priya").get("/cases/TB-002/helpers/radiology/chat").status_code == 200


# ---- finding 16: the live channel ---------------------------------------------------------------------------------------------------------

def test_finding16_socket_cap_and_state_throttle(tc, people):
    mid = with_agenda(tc)
    tc.cookies.set("vaidyx_session", "tok-anil")
    from contextlib import ExitStack
    from starlette.websockets import WebSocketDisconnect
    with ExitStack() as stack:
        socks = [stack.enter_context(tc.websocket_connect(f"/api/tb/meetings/{mid}/ws")) for _ in range(live.MAX_SOCKETS_PER_USER)]
        for s in socks:
            assert s.receive_json()["type"] == "state"
        with pytest.raises(WebSocketDisconnect) as e:
            with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as extra:
                extra.receive_json()
        assert e.value.code == 1008 and live.hub.user_count(mid, "anil") == live.MAX_SOCKETS_PER_USER
        ws = socks[0]
        ws.send_json({"type": "state"}); ws.send_json({"type": "state"}); ws.send_json({"type": "ping"})
        got = []
        while True:
            m = ws.receive_json()
            got.append(m["type"])
            if m["type"] == "pong":
                break
        assert got.count("state") == 1  # the second request within STATE_EVERY seconds is not answered


def test_finding16_a_disabled_user_loses_the_socket_on_its_next_message(tc, people):
    mid = with_agenda(tc)
    join_and_admit(tc, mid, "priya")
    tc.cookies.set("vaidyx_session", "tok-priya")
    from starlette.websockets import WebSocketDisconnect
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as ws:
        assert ws.receive_json()["type"] == "state"
        o = json.loads(json.dumps(org.load())); o["users"]["priya"]["disabled"] = True; org.save(o, by="test")
        ws.send_json({"type": "state"})
        with pytest.raises(WebSocketDisconnect) as e:
            for _ in range(10):
                assert ws.receive_json()["type"] != "state", "a disabled user still gets the meeting state"
        assert e.value.code == 1008


def test_finding16_a_slow_socket_is_dropped_and_never_holds_the_others():
    class Slow:
        closed = False

        async def send_json(self, ev):
            await asyncio.sleep(10)

        async def close(self, code=1000):
            self.closed = True

    class Fast:
        got = []

        async def send_json(self, ev):
            self.got.append(ev)

        async def close(self, code=1000):
            pass

    live.hub.clear()
    slow, fast = Slow(), Fast()
    live.hub.connect("M1", slow, "a"); live.hub.connect("M1", fast, "b")
    t0 = time.monotonic()
    n = asyncio.run(live.hub.send_all("M1", {"type": "x"}))
    assert n == 1 and fast.got == [{"type": "x"}] and slow.closed
    assert time.monotonic() - t0 < live.SEND_TIMEOUT + 2
    assert live.hub.clients("M1") == [fast]
    live.hub.clear()


# ---- finding 17: push endpoints on the known services only -------------------------------------------------------------------------------

def test_finding17_push_endpoints_are_allow_listed(tc, people):
    keys = {"p256dh": "BPdh-synthetic", "auth": "auth-synthetic"}
    for bad in ("https://attacker.example/x", "https://fcm.googleapis.com.evil.example/x", "http://fcm.googleapis.com/x", "https://user@fcm.googleapis.com/x",
                "https://fcm.googleapis.com:8443/x", "https://notify.windows.com/x", "https://127.0.0.1/x"):
        r = As(tc, "ravi").post("/push/subscribe", json={"endpoint": bad, "keys": keys})
        assert r.status_code == 400, bad
    for good in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/abc", "https://web.push.apple.com/abc",
                 "https://wns2-par02p.notify.windows.com/w/?token=abc"):
        assert push.endpoint_allowed(good), good
    assert As(tc, "ravi").post("/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": keys}).status_code == 200


# ---- finding 18: department emails and the mailto address ----------------------------------------------------------------------------------

def test_finding18_department_email_and_mailto(people):
    o = org.load()
    for bad in ("radiology@hospital.example?cc=x@evil.example", "a@b.example&body=x", "a@b%2Eexample", "a@b.example,c@d.example", "a@b.example;c@d.example", "a b@c.example"):
        o2 = json.loads(json.dumps(o))
        next(d for d in o2["departments"] if d["id"] == "radiology")["email"] = bad
        with pytest.raises(ValueError):
            org.save(o2, by="test")
    link = dept_requests.mailto({"email": "x@y.example?cc=evil@z.example"}, "S", "B")
    assert link.startswith("mailto:x@y.example%3Fcc%3Devil@z.example?") and link.count("?") == 1
    from tumour_board import accounts
    link = accounts.mailto_for("x@y.example?bcc=evil@z.example", "x", "pw-synthetic")
    assert link.count("?") == 1 and "bcc=" not in link.split("?", 1)[0]


# ---- finding 19: the JSON body cap ---------------------------------------------------------------------------------------------------------

def test_finding19_json_bodies_over_one_megabyte_are_refused(tc, people):
    big = {"display_name": "Dr Ravi", "title": "x" * (common.MAX_JSON_BYTES + 10)}
    r = As(tc, "ravi").put("/me/profile", json=big)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    def chunks():
        yield b'{"display_name": "Dr Ravi", "title": "'
        for _ in range(1100):
            yield b"x" * 1024
        yield b'"}'
    r = tc.put("/api/tb/me/profile", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert As(tc, "ravi").put("/me/profile", json={"display_name": "Dr Ravi"}).status_code == 200


# ---- finding 21: LiveKit config without the secret on a command line --------------------------------------------------------------------

def test_finding21_livekit_config_is_written_without_the_secret_on_a_command_line(tmp_path):
    script = (REPO / "scripts" / "livekit.sh").read_text(encoding="utf-8")
    assert "__API_SECRET__|$secret" not in script and "read_key" not in script
    data, tools, scripts = tmp_path / "data", tmp_path / "tools", tmp_path / "repo" / "scripts"
    data.mkdir(); tools.mkdir(); scripts.mkdir(parents=True); os.chmod(tools, 0o775)
    (data / "livekit.json").write_text(json.dumps({"api_key": "APIsynthetic", "api_secret": "s3cr3t-synthetic-value", "url": "ws://127.0.0.1:7880"}))
    (scripts / "livekit-config.yaml.example").write_text((REPO / "scripts" / "livekit-config.yaml.example").read_text(encoding="utf-8"))
    (scripts / "lk.sh").write_text(script.split('\ncase "${1:-status}" in', 1)[0] + "\nwrite_config\n")  # every function, then write_config only
    env = {**os.environ, "TB_DATA_ROOT": str(data), "LIVEKIT_TOOLS": str(tools)}
    out = subprocess.run(["bash", str(scripts / "lk.sh")], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "s3cr3t" not in out.stdout + out.stderr
    cfg = tools / "config.yaml"
    assert "s3cr3t-synthetic-value" in cfg.read_text() and "APIsynthetic" in cfg.read_text() and "__API_SECRET__" not in cfg.read_text()
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600 and stat.S_IMODE(tools.stat().st_mode) & 0o022 == 0
