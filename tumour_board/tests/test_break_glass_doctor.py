"""A doctor opens a Case File read-only with a reason (owner decision D8, night-v3 item 1.9): the 403 of the Case File guard says the
doctor may, POST /break-glass opens a 24 hour read-only window (scope READ), audited in the Case File and the organisation log, the
owner's consultants told, listed in GET /me, renewed by a second opening, closed by DELETE /break-glass, gone after its end; residents
may, outside experts, the coordinator, the auditor and the root admin may not; a protected Case File never opens this way. The whole
Tumour Board API behind a fake login; synthetic Case Files only (the TB-002 fixture, empty ones), the conftest temporary data root."""
import json
import re
from datetime import datetime, timedelta

from tumour_board import access, config, org, store
from tumour_board.tests.test_nik_me import ANIL, AUDIT, GUEST, MEHTA, OLD, RAO, RAVI, ROOT, VIJAY, VX, auth, make_case, people  # noqa: F401
from tumour_board.tests.test_nik_team import CASE, full, kinds, notes_for, tb002  # noqa: F401

REASON = "Second opinion on the systemic plan (synthetic)"


def detail(r):
    return r.json()["detail"]


def test_a_consultant_without_access_opens_the_case_file_read_only_with_a_reason(full, tb002):
    api = full.as_(MEHTA)  # head of Medical Oncology: not the owner, not taking part
    r = api.get(f"/cases/{CASE}")
    assert r.status_code == 403 and detail(r)["code"] == "no_access" and detail(r)["break_glass"] is True
    assert "belongs to" in detail(r)["message"]  # the refusal text is unchanged
    assert api.post("/break-glass", {"case_id": CASE, "reason": "  "}).status_code == 400
    r = api.post("/break-glass", {"case_id": CASE, "reason": "ok"})
    assert r.status_code == 400 and detail(r)["code"] == "bad_reason"
    assert api.post("/break-glass", {"case_id": CASE, "reason": "x" * 501}).status_code == 400
    assert api.post("/break-glass", {"case_id": "TB-NONE", "reason": REASON}).status_code == 404
    assert access.doctor_windows(MEHTA) == []

    r = api.post("/break-glass", {"case_id": CASE, "reason": "  Second opinion on the   systemic plan (synthetic) "})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["scope"] == access.READ == "read" and b["case_id"] == CASE and b["reason"] == REASON and b["renewed"] is False
    w = access.doctor_window(MEHTA, CASE)
    opened, until = datetime.fromisoformat(w["opened"]), datetime.fromisoformat(w["until"])
    assert until - opened == timedelta(hours=24) and w["until"] == b["until"]
    assert access.scope(org.roles(MEHTA), store.get_case(CASE)) == access.READ

    # read-only: the Case File and the guided steps open in reader mode, every change is refused
    assert api.get(f"/cases/{CASE}").status_code == 200
    s = api.get(f"/cases/{CASE}/steps")
    assert s.status_code == 200 and s.json()["mode"] == "read", s.text
    r = api.put(f"/cases/{CASE}/reason", {"value": "after_surgery"})
    assert r.status_code == 403 and detail(r)["code"] == "break_glass_read_only" and "opened with a reason" in detail(r)["message"]
    for r in (api.post(f"/cases/{CASE}/confirmations", {"type": "waive", "key": "bone_scan", "reason": "synthetic"}),
              api.post(f"/cases/{CASE}/ready", {"ready": True}), api.post(f"/cases/{CASE}/chats", {"text": "hello"})):
        assert r.status_code == 403 and detail(r)["code"] == "break_glass_read_only", r.text
    assert api.get(f"/cases/{CASE}/chats").status_code == 403  # the team chat stays closed inside a window
    perms = api.get(f"/cases/{CASE}").json().get("permissions") or {}
    assert perms.get("mark_ready") is False and perms.get("send_request") is False

    # audited in the Case File and the organisation log; the owner's consultants are told
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "break_glass_doctor")
    assert ev["by"] == MEHTA and ev["reason"] == REASON and ev["until"] == b["until"] and ev["via"] == ""
    assert any(e.get("kind") == "break_glass_doctor" and e.get("case_id") == CASE for e in org.read_audit())
    n = notes_for(RAO, "break_glass")
    assert n and n[0]["title"].startswith("Opened with a reason: Dr Mehta (synthetic) opened the Case File of ") and n[0]["title"].endswith(f"({CASE})")
    assert re.search(r"read-only until \d{2}/\d{2}/\d{4} \d{2}:\d{2}\. Reason: " + re.escape(REASON), n[0]["text"])

    # GET /me lists the window; the doctor's own lists do not
    me = api.get("/me").json()
    assert me["break_glass"] == [{"case_id": CASE, "until": b["until"], "reason": REASON, "via": ""}]
    assert CASE not in {c["case_id"] for c in access.visible(org.roles(MEHTA), store.list_cases())}
    assert full.as_(RAO).get("/me").json()["break_glass"] == []

    # a second opening renews the one window; closing it shuts the Case File again
    r = full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": "Board tomorrow (synthetic)", "via": "similar to TB-001"})
    assert r.status_code == 200 and r.json()["renewed"] is True and r.json()["via"] == "similar to TB-001"
    ws = access.doctor_windows(MEHTA)
    assert len(ws) == 1 and ws[0]["id"] == w["id"] and ws[0]["reason"] == "Board tomorrow (synthetic)"
    assert kinds(CASE).count("break_glass_doctor") == 2
    r = full.tc.request("DELETE", "/api/tb/break-glass", json={"case_id": CASE})
    assert r.status_code == 200 and r.json()["closed"]["case_id"] == CASE
    assert "break_glass_doctor_closed" in kinds(CASE)
    assert full.as_(MEHTA).get(f"/cases/{CASE}").status_code == 403
    assert full.tc.request("DELETE", "/api/tb/break-glass", json={"case_id": CASE}).status_code == 404
    assert full.as_(MEHTA).get("/me").json()["break_glass"] == []


def test_an_expired_window_closes_the_case_file_again(full, tb002):
    assert full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": REASON}).status_code == 200
    p = access.doctor_windows_path()
    d = json.loads(p.read_text())
    d[MEHTA][0]["until"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    p.write_text(json.dumps(d))
    r = full.get(f"/cases/{CASE}")
    assert r.status_code == 403 and detail(r)["break_glass"] is True
    assert full.get("/me").json()["break_glass"] == []
    assert access.expire_break_glass() == 1 and json.loads(p.read_text()) == {}
    assert oct(p.stat().st_mode & 0o777) == "0o600"


def test_a_resident_of_another_department_may_open_with_a_reason(full, tb002):
    api = full.as_(VIJAY)  # a Medical Oncology resident
    r = api.get(f"/cases/{CASE}")
    assert r.status_code == 403 and detail(r)["break_glass"] is True
    assert api.post("/break-glass", {"case_id": CASE, "reason": REASON}).status_code == 200
    assert api.get(f"/cases/{CASE}").status_code == 200
    assert api.get(f"/cases/{CASE}/steps").json()["mode"] == "read"
    r = api.post(f"/cases/{CASE}/proposals", {"action": "waive", "payload": {"key": "bone_scan", "reason": "synthetic"}})
    assert r.status_code == 403 and detail(r)["code"] == "break_glass_read_only"


def test_who_may_not_open_with_a_reason(full, tb002):
    for user in (GUEST, ROOT, AUDIT, OLD):  # an outside expert, the root admin, the auditor, a resident past its end date
        r = full.as_(user).post("/break-glass", {"case_id": CASE, "reason": REASON})
        assert r.status_code == 403 and detail(r)["code"] == "not_placed", user
    for user in (ANIL, RAO):  # the MDT Coordinator and the owner open it already
        r = full.as_(user).post("/break-glass", {"case_id": CASE, "reason": REASON})
        assert r.status_code == 409 and detail(r)["code"] == "can_open", user
    r = full.as_(GUEST).get(f"/cases/{CASE}")  # not placed: refused before the Case File guard, never offered a window
    assert r.status_code == 403 and "break_glass" not in r.text
    assert not any(e.get("kind") == "break_glass_doctor" for e in store.read_audit(CASE))
    assert full.as_(RAVI).post("/break-glass", {"case_id": CASE, "reason": REASON}).status_code == 200  # a supporting consultant may


def test_a_protected_case_file_never_opens_with_a_reason(full, people, monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-NIK-P"})
    make_case("TB-NIK-P")
    r = full.as_(MEHTA).get("/cases/TB-NIK-P")
    assert r.status_code == 403 and detail(r)["break_glass"] is False
    r = full.post("/break-glass", {"case_id": "TB-NIK-P", "reason": REASON})
    assert r.status_code == 404 and "TB-NIK-P" not in r.text
    # even a window written into the store by hand does not open it
    access._write_windows({MEHTA: [{"id": "BG-X", "case_id": "TB-NIK-P", "reason": REASON, "via": "", "opened": "2026-01-01T00:00:00",
                                    "until": (datetime.now() + timedelta(hours=1)).isoformat()}]}, access.doctor_windows_path())
    assert access.scope(org.roles(MEHTA), store.get_case("TB-NIK-P")) is None
    assert full.get("/cases/TB-NIK-P").status_code == 403


def test_the_read_scope_reads_only(people):
    mehta = people[MEHTA]
    c = make_case("TB-NIK-W")
    bare = make_case("TB-NIK-B", owner=None)  # no owning department: the coordinator and the creator only, or a window
    assert access.scope(mehta, c) is None and access.may_open_with_reason(mehta, c)
    for case in (c, bare):
        access.open_doctor_window(MEHTA, case["case_id"], REASON)
        assert access.scope(mehta, case) == access.READ
    for action in ("view", "read_case", "read_audit", "ask"):
        assert access.may(mehta, action, c), action
    for action in ("confirm", "waive", "upload_to_case", "upload", "send_request", "mark_ready", "set_urgency", "propose", "comment"):
        assert not access.may(mehta, action, c), action
    try:
        access.require(mehta, "confirm", c)
        raise AssertionError("require passed")
    except PermissionError as e:
        assert str(e) == access.READ_ONLY_MESSAGE
    assert not access.can_see_chats(mehta, c) and not access.is_owner_doctor(mehta, c)
    assert access.visible(mehta, [c, bare]) == []
    assert access.may_open_with_reason(mehta, c)  # its own window: a new opening renews it
    assert not access.may_open_with_reason(people[VX], c) and not access.may_open_with_reason(people[ANIL], c)
    assert access.scope(people[VX], c) is None  # the Vaidyx admin keeps its own store and route
