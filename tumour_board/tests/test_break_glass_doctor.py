"""A doctor opens a Case File read-only with a reason (owner decision D8, night-v3 item 1.9): the 403 of the Case File guard says the
doctor may, POST /break-glass opens a 24 hour read-only window (scope READ), audited in the Case File and the organisation log, the
owner's consultants told, listed in GET /me, renewed by a second opening, closed by DELETE /break-glass, gone after its end; residents
may, outside experts, the coordinator, the auditor and the root admin may not; a protected Case File never opens this way. The whole
Tumour Board API behind a fake login; synthetic Case Files only (the TB-002 fixture, empty ones), the conftest temporary data root."""
import json
import re
from datetime import datetime, timedelta

import pytest

from tumour_board import access, config, org, store
from tumour_board.tests.test_nik_me import ANIL, AUDIT, GUEST, MEHTA, OLD, RAO, RAVI, ROOT, VIJAY, VX, auth, make_case, people  # noqa: F401
from tumour_board.tests.test_nik_team import CASE, full, kinds, notes_for, tb002  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_open_limit():
    """Five windows an hour per login (api/team.OPEN_LIMIT): each test starts with a clean count."""
    from tumour_board.api import team as team_api
    team_api.OPEN_LIMIT._hits.clear()
    yield
    team_api.OPEN_LIMIT._hits.clear()

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
    r = full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": "Board tomorrow (synthetic)", "via": "similar:TB-001"})
    assert r.status_code == 200 and r.json()["renewed"] is True and r.json()["via"] == "similar:TB-001"
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


# ---- whole-run review 9 (area A) --------------------------------------------------------------------------------------------------

READ_ONLY_EXPORT = "A Case File opened with a reason is read on screen only."


def test_a_window_never_exports_the_case_file(full, tb002):
    """I1: a doctor's window and the Vaidyx admin's break-glass read on screen only: the four exports answer 403. M5: the Case File view
    says the reader's real scope."""
    assert full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": REASON}).status_code == 200
    assert full.get(f"/cases/{CASE}").json()["access"]["scope"] == access.READ
    for path in ("/export", "/export/fhir", "/export/registry", "/export/registry?format=csv", "/export/vtb"):
        r = full.as_(MEHTA).get(f"/cases/{CASE}{path}")
        assert r.status_code == 403, (path, r.text)
        assert detail(r) == {"message": READ_ONLY_EXPORT, "code": "break_glass_read_only"}, path
    assert not any(str(k).startswith("export") for k in kinds(CASE))
    r = full.as_(VX).post("/break-glass", {"case_id": CASE, "reason": "Support check (synthetic)", "hours": 1})
    assert r.status_code == 200, r.text
    assert full.as_(VX).get(f"/cases/{CASE}").status_code == 200
    r = full.as_(VX).get(f"/cases/{CASE}/export")
    assert r.status_code == 403 and detail(r)["code"] == "break_glass_read_only"
    # the owner still exports, and is told it has full scope
    assert full.as_(RAO).get(f"/cases/{CASE}").json()["access"]["scope"] == access.FULL
    assert full.as_(RAO).get(f"/cases/{CASE}/export").status_code == 200
    assert full.as_(RAO).get(f"/cases/{CASE}/export/registry").status_code == 200
    assert "export_case_file" in kinds(CASE)


def test_an_opening_without_an_owner_tells_the_creator_and_the_coordinator(full, people):
    """I2: no owning department: the creator and the MDT Coordinator role are told (the role's notice names no patient)."""
    make_case("TB-NIK-B", owner=None)  # created by Dr Rao
    r = full.as_(MEHTA).post("/break-glass", {"case_id": "TB-NIK-B", "reason": REASON})
    assert r.status_code == 200, r.text
    rao = [n for n in notes_for(RAO, "break_glass") if n["case_id"] == "TB-NIK-B"]
    assert len(rao) == 1 and "SYNTHETIC, Test Patient" in rao[0]["title"]  # the creator opens it: the patient line
    assert "no owning department yet" in rao[0]["text"]
    coord = [n for n in notes_for(ANIL, "break_glass") if n["case_id"] == "TB-NIK-B"]
    assert len(coord) == 1 and coord[0]["to"] == {"role": "coordinator"}
    assert coord[0]["title"] == "Opened with a reason: Dr Mehta (synthetic) opened Case File TB-NIK-B (Breast cancer)"
    assert "SYNTHETIC, Test Patient" not in str(coord[0]) and "SYN-900001" not in str(coord[0])


def test_an_opening_nobody_would_hear_of_is_refused(full, people):
    """I2: no owner, no creator to tell and no MDT Coordinator: 409 no_owner and no window."""
    make_case("TB-NIK-N", owner=None, created_by="")
    o = org.load()
    o["users"][ANIL]["disabled"] = True
    org.save(o, by="test")
    r = full.as_(MEHTA).post("/break-glass", {"case_id": "TB-NIK-N", "reason": REASON})
    assert r.status_code == 409, r.text
    assert detail(r) == {"message": "This Case File has no owning department yet: ask the MDT Coordinator.", "code": "no_owner"}
    assert access.doctor_window(MEHTA, "TB-NIK-N") is None and "break_glass_doctor" not in kinds("TB-NIK-N")


def test_via_is_empty_or_a_similar_case_file_and_the_windows_are_listed(full, tb002):
    """M1: `via` is "" or "similar:<id>", else 400 bad_via and no window. M2: GET /break-glass lists the doctors' windows too."""
    for bad in ("similar to TB-001", "anything", "similar:", "similar:TB 001", "similar:" + "x" * 65, "<b>similar:TB-001</b>"):
        r = full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": REASON, "via": bad})
        assert r.status_code == 400 and detail(r)["code"] == "bad_via", bad
    assert access.doctor_windows(MEHTA) == []
    r = full.as_(MEHTA).post("/break-glass", {"case_id": CASE, "reason": REASON, "via": "similar:TB-001"})
    assert r.status_code == 200 and r.json()["via"] == "similar:TB-001"
    for who in (ROOT, AUDIT):
        b = full.as_(who).get("/break-glass").json()
        assert [(w["case_id"], w["user"], w["reason"], w["via"]) for w in b["doctors"]] == [(CASE, MEHTA, REASON, "similar:TB-001")], who
        assert b["doctors"][0]["until"]
    assert full.as_(MEHTA).get("/break-glass").status_code == 403


def test_a_bad_board_record_id_or_body_is_a_400_never_a_500(full, tb002):
    """M10 (the correct route sits next to the export routes in routes/tumour_board_routes.py): a record id store.safe_id refuses, or a
    body that is not JSON, answers 400 bad_request."""
    url = f"/api/tb/cases/{CASE}/board-records/.hidden/correct"
    r = full.as_(RAO).tc.post(url, json={"changes": {}})
    assert r.status_code == 400 and detail(r)["code"] == "bad_request", r.text
    r = full.tc.post(f"/api/tb/cases/{CASE}/board-records/B1/correct", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and detail(r)["code"] == "bad_request", r.text
    r = full.tc.post(f"/api/tb/cases/{CASE}/board-records/Bnope/correct", json={"changes": {}})
    assert r.status_code == 404  # a well-formed id that is not there stays a 404
