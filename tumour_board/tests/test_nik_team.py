"""The Case File team of the new interface (18 Oct 2026): residents refused on every signing route, the proposal flow end to end (propose,
notify, approve runs the very action), the join code (right, wrong, rate limited), urgency (set or proposed), archive, consent and
break-glass. The whole Tumour Board API (old routes plus the new routers) runs behind a fake login; synthetic Case Files only (the TB-002
fixture and empty ones), the conftest temporary data root, no model call."""
import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import access, confirm, notify, org, proposals, published, service, slots, store, team
from tumour_board.tests.test_nik_me import (ANIL, ASHA, AUDIT, DEEPAK, GUEST, MEHTA, OLD, RAO, RAVI, ROOT, VIJAY, VX, Api, FakeAuth,  # noqa: F401
                                            audit_text, auth, make_case, people)

CASE = "TB-002"  # the synthetic breast Case File (SYNTHETIC, Lakshmi Iyer), owned here by Breast Surgery (Dr Rao)


@pytest.fixture
def full(auth, monkeypatch):
    """The whole Tumour Board API under /api/tb (old routes and the new routers, the live route class) with a switchable fake login."""
    import routes.tumour_board_routes as R
    from tumour_board.api import me
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    from tumour_board.api import team as team_api
    app = FastAPI()
    who = {"user": RAO}

    @app.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)

    app.include_router(R.setup_tumour_board_routes())
    app.state.auth_manager = auth
    team_api.JOIN_LIMIT._hits.clear()
    me.PASSWORD_LIMIT._hits.clear()
    with TestClient(app) as tc:
        yield Api(tc, who)


@pytest.fixture
def tb002(demo_cases, people):
    c = store.get_case(CASE)
    c["department"] = "breast_surgery"
    c["created_by"] = RAO
    store.save_case(c)
    service.recheck(CASE, "test")
    return CASE


def notes_for(user, kind=None):
    return [n for n in notify.for_roles(org.roles(user), limit=None) if kind is None or n["kind"] == kind]


def kinds(case_id):
    return [e.get("kind") for e in store.read_audit(case_id)]


# ---- residents never sign -------------------------------------------------------------------------------------------------------

def test_resident_reads_the_whole_case_file_but_is_refused_on_every_signing_route(full, tb002):
    api = full.as_(ASHA)
    assert api.get(f"/cases/{CASE}").status_code == 200  # a resident of the owning department: full read scope
    refused = [
        api.post(f"/cases/{CASE}/confirmations", {"type": "waive", "key": "bone_scan", "reason": "not needed (synthetic)"}),
        api.post(f"/cases/{CASE}/ready", {"ready": True}),
        api.post(f"/cases/{CASE}/requests", {"department": "pathology", "label": "IHC", "message": "synthetic"}),
        api.post(f"/cases/{CASE}/referrals", {"to": "medical_oncology", "reason": "synthetic"}),
        api.put(f"/cases/{CASE}/participants", {"add": ["medical_oncology"]}),
        api.post(f"/cases/{CASE}/slots/fact:ecog/value", {"value": "1"}),
        api.post(f"/cases/{CASE}/team/code"),
        api.put(f"/cases/{CASE}/consent", {"outside_discussion": True}),
    ]
    for r in refused:
        assert r.status_code == 403, r.text
    assert "sign off" in str(refused[0].json()["detail"])  # the message tells the resident what to do instead
    assert not confirm.latest(CASE, "waive", "bone_scan") and "board_ready" not in store.get_case(CASE)
    perms = api.get(f"/cases/{CASE}").json().get("permissions") or {}
    assert perms.get("mark_ready") is False and perms.get("send_request") is False
    for user in (OLD, GUEST, AUDIT, DEEPAK, ROOT):  # expired resident, outside expert, auditor, department admin, root admin: no Case File
        assert full.as_(user).get(f"/cases/{CASE}").status_code == 403, user


def test_org_and_access_rules_for_residents(people):
    asha, vijay, old = people[ASHA], people[VIJAY], people[OLD]
    c = make_case("TB-NIK-R")
    assert asha["resident"] == {"breast_surgery": "resident"} and asha["known"] and not asha["treating"]
    assert old["expired"] and old["departments"] == {} and not old["known"] and access.scope(old, c) is None
    for action in ("waive", "confirm", "dismiss_failed", "send_request", "create_request", "close_request", "refer", "manage_participants", "mark_ready",
                   "delete_document", "approve_proposal", "set_urgency", "manage_team", "set_consent", "archive", "review"):
        assert not access.may(asha, action, c), action
    for action in ("view", "read_case", "ask", "upload_to_case", "propose"):
        assert access.may(asha, action, c), action
    assert access.scope(vijay, c) is None and not access.may(vijay, "propose", c)  # another department's resident: not on the team
    assert access.can_see_chats(asha, c) and access.can_see_chats(people[RAO], c) and not access.can_see_chats(people[MEHTA], c)
    assert org.can(people[AUDIT], "read_audit") and org.can(people[ANIL], "read_audit") and org.can(people[ROOT], "read_audit") and not org.can(people[RAO], "read_audit")


def test_a_supporting_doctor_asked_for_a_record_never_sees_the_chats(people):
    c = make_case("TB-NIK-S")
    st = store.get_state("TB-NIK-S")
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "breast_imaging", "department": "Radiology", "department_id": "radiology",
                      "status": "pending", "created": store.now_iso(), "history": []}]
    store.save_state("TB-NIK-S", st)
    assert access.scope(people[RAVI], c) == access.REQUESTS and not access.can_see_chats(people[RAVI], c)


# ---- proposals --------------------------------------------------------------------------------------------------------------------

def test_proposal_flow_end_to_end_runs_the_waive_in_the_consultants_name(full, tb002):
    r = full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "waive", "payload": {"key": "bone_scan", "reason": "no bone symptoms, synthetic"},
                                                         "note": "please sign off"})
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["status"] == "pending" and p["by"] == ASHA and p["by_name"] == "Dr Asha (synthetic)"
    assert not confirm.latest(CASE, "waive", "bone_scan")  # nothing changes before the consultant signs
    n = notes_for(RAO, "sign_off")
    assert n and n[0]["title"] == "Dr Asha (synthetic) asks you to sign off: waive a requirement (SYNTHETIC, Lakshmi Iyer, 48 Y / F, UHID SYN-200417)"
    w = full.as_(RAO).get("/waiting").json()["items"]
    assert [x["id"] for x in w if x["kind"] == "proposal"] == [p["id"]]
    assert full.as_(ASHA).get("/waiting").json()["mine"][0]["status"] == "pending"
    assert full.as_(MEHTA).post(f"/cases/{CASE}/proposals/{p['id']}/approve").status_code == 403  # another department's consultant
    assert full.as_(ASHA).post(f"/cases/{CASE}/proposals/{p['id']}/approve").status_code == 403  # never the resident itself
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve", {"note": "agreed"})
    assert r.status_code == 200, r.text
    assert r.json()["proposal"]["status"] == "approved" and r.json()["result"]["status"] == "done"
    w = confirm.latest(CASE, "waive", "bone_scan")
    assert w and w["by"] == RAO  # the consultant is the actor
    gate = store.get_state(CASE)["gate"]
    assert next(q for q in gate["requirements"] if q["id"] == "bone_scan")["status"] == "waived"
    k = kinds(CASE)
    assert k.index("proposal_created") < k.index("proposal_approved")
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "proposal_approved")
    assert ev["by"] == RAO and ev["proposed_by"] == ASHA and ev["proposal"] == p["id"]
    assert any(x["title"].startswith("Approved: waive a requirement") for x in notes_for(ASHA, "sign_off"))
    assert full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve").status_code == 409  # once only
    assert full.as_(RAO).get("/waiting").json()["items"] == [x for x in full.as_(RAO).get("/waiting").json()["items"] if x["kind"] != "proposal"]


def test_a_returned_proposal_needs_a_note_and_changes_nothing(full, tb002):
    p = full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "mark_ready", "payload": {"ready": True}}).json()["proposal"]
    assert full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/return", {"note": ""}).status_code == 400
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/return", {"note": "type the board question first"})
    assert r.status_code == 200 and r.json()["proposal"]["status"] == "returned"
    assert "board_ready" not in store.get_case(CASE)
    mine = full.as_(ASHA).get("/waiting").json()["mine"]
    assert mine[0]["status"] == "returned" and "type the board question first" in mine[0]["title"]
    assert any(x["title"].startswith("Returned:") for x in notes_for(ASHA, "sign_off"))


def test_bad_proposals_are_refused_before_they_are_stored(full, tb002):
    api = full.as_(ASHA)
    assert api.post(f"/cases/{CASE}/proposals", {"action": "delete_case", "payload": {}}).status_code == 400
    assert api.post(f"/cases/{CASE}/proposals", {"action": "waive", "payload": {"key": "bone_scan"}}).status_code == 400  # no reason
    assert api.post(f"/cases/{CASE}/proposals", {"action": "waive", "payload": {"key": "no_such", "reason": "x"}}).status_code == 400
    assert api.post(f"/cases/{CASE}/proposals", {"action": "typed_value", "payload": {"slot": "fact:ecog", "value": "7"}}).status_code == 400
    assert full.as_(RAO).post(f"/cases/{CASE}/proposals", {"action": "urgency", "payload": {"level": 3}}).status_code == 403  # a consultant acts itself
    assert proposals.list_(store.get_case(CASE)) == []


def test_typed_value_not_needed_and_published_case_proposals_run_their_modules(full, tb002):
    api = full.as_(ASHA)
    tv = api.post(f"/cases/{CASE}/proposals", {"action": "typed_value", "payload": {"slot": "fact:ecog", "value": "ECOG 1"}}).json()["proposal"]
    nn = api.post(f"/cases/{CASE}/proposals", {"action": "not_needed", "payload": {"slot": "record:pet_ct", "reason": "bone scan planned instead, synthetic"}}).json()["proposal"]
    pc = api.post(f"/cases/{CASE}/proposals", {"action": "published_case", "payload": {
        "result": {"title": "A synthetic case report", "authors": "Test A", "journal": "Synthetic J", "year": "2024", "url": "https://example.org/p1", "source": "local"},
        "quotes": [{"text": "The procedure was done.", "where": "Methods"}]}}).json()["proposal"]
    assert tv["payload"]["value"] == "1"  # validated when proposed
    for p in (tv, nn, pc):
        r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve")
        assert r.status_code == 200, (p["action"], r.text)
        assert r.json()["result"]["status"] == "done", p["action"]
    assert store.get_case(CASE)["typed_values"]["ecog"]["by"] == RAO
    assert confirm.latest(CASE, "waive", "pet_ct")["by"] == RAO
    items = published.view(CASE)["items"]
    assert len(items) == 1 and items[0]["added_by"] == RAO and items[0]["title"] == "A synthetic case report"
    assert set(proposals.PROPOSAL_EXECUTORS) == set(proposals.ACTIONS)


def test_request_and_referral_proposals_run_as_the_consultant(full, tb002):
    api = full.as_(ASHA)
    rq = api.post(f"/cases/{CASE}/proposals", {"action": "send_request", "payload": {"department": "Pathology", "label": "IHC panel (synthetic)",
                                                                                     "message": "Please add ER, PR, HER2."}}).json()["proposal"]
    rf = api.post(f"/cases/{CASE}/proposals", {"action": "refer", "payload": {"to": "Medical Oncology", "reason": "systemic therapy first (synthetic)"}}).json()["proposal"]
    assert rq["payload"]["department"] == "pathology" and rf["payload"]["to"] == "medical_oncology"
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{rq['id']}/approve")
    assert r.status_code == 200, r.text
    a = next(x for x in store.get_state(CASE)["actions"] if x["id"] == r.json()["result"]["action"])
    assert a["status"] in ("pending", "overdue") and (a.get("sent") or {}).get("by", RAO) == RAO
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{rf['id']}/approve")
    assert r.status_code == 200, r.text
    ref = access.open_referral(store.get_case(CASE))
    assert ref and ref["to"] == "medical_oncology" and ref.get("by", RAO) == RAO


def test_an_approval_that_cannot_run_keeps_the_proposal_pending(full, tb002):
    p = full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "send_request", "payload": {"action_id": "NO-SUCH"}}).json()["proposal"]
    r = full.as_(RAO).post(f"/cases/{CASE}/proposals/{p['id']}/approve")
    assert r.status_code in (400, 404, 409) and r.json()["detail"]["message"]
    assert proposals.find(store.get_case(CASE), p["id"])["status"] == "pending"


def test_a_registered_executor_replaces_the_default(tb002, people, monkeypatch):
    seen = []
    monkeypatch.setitem(proposals.PROPOSAL_EXECUTORS, "urgency", lambda cid, payload, user, roles, note: seen.append((cid, payload["level"], user)) or {"ok": 1})
    p = proposals.propose(CASE, "urgency", {"level": 2}, "", ASHA, people[ASHA])
    _, result = proposals.approve(CASE, p["id"], RAO, people[RAO])
    assert seen == [(CASE, 2, RAO)] and result == {"status": "done", "ok": 1}
    with pytest.raises(ValueError):
        proposals.register("no_such_action", lambda *a: {})


# ---- join code ----------------------------------------------------------------------------------------------------------------------

def test_join_code_right_wrong_approval_and_removal(full, tb002):
    r = full.as_(RAO).post(f"/cases/{CASE}/team/code")
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit() and r.json()["expires_at"] > store.now_iso()
    assert code not in audit_text(CASE)  # never in the audit log
    assert full.as_(RAO).get(f"/cases/{CASE}/team").json()["join_code"]["code"] == code
    assert full.as_(ASHA).get(f"/cases/{CASE}/team").json()["join_code"]["code"] == ""  # only the owner sees the digits
    wrong = "000000" if code != "000000" else "111111"
    r = full.as_(VIJAY).post("/case-join", {"code": wrong})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_such_code"
    assert full.as_(VIJAY).get(f"/cases/{CASE}").status_code == 403
    r = full.as_(VIJAY).post("/case-join", {"code": code})
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["case_id"] == CASE and "UHID SYN-200417" in r.json()["patient_line"]
    assert full.as_(VIJAY).get(f"/cases/{CASE}").status_code == 403  # waits for the owner
    assert any(n["kind"] == "join_request" for n in notes_for(RAO))
    assert any(x["kind"] == "join" for x in full.as_(RAO).get("/waiting").json()["items"])
    assert full.as_(ASHA).post(f"/cases/{CASE}/team/pending/{VIJAY}/approve").status_code == 403
    r = full.as_(RAO).post(f"/cases/{CASE}/team/pending/{VIJAY}/approve", {"note": "welcome"})
    assert r.status_code == 200 and [x["user"] for x in r.json()["team"]["residents"]] == [VIJAY]
    assert full.as_(VIJAY).get(f"/cases/{CASE}").status_code == 200 and access.may(org.roles(VIJAY), "propose", store.get_case(CASE))
    r = full.as_(ASHA).post("/case-join", {"code": code})  # the owning department's resident joins at once
    assert r.status_code == 200 and r.json()["status"] == "joined"
    assert {x["user"] for x in full.as_(RAO).get(f"/cases/{CASE}/team").json()["residents"]} == {VIJAY, ASHA}
    assert full.as_(RAVI).post("/case-join", {"code": code}).status_code == 403  # a consultant does not join with a code
    assert full.as_(OLD).post("/case-join", {"code": code}).status_code == 403  # past the end date
    assert full.as_(RAO).delete(f"/cases/{CASE}/team/residents/{VIJAY}").status_code == 200
    assert full.as_(VIJAY).get(f"/cases/{CASE}").status_code == 403  # a removed resident loses access
    assert full.as_(VIJAY).post("/case-join", {"code": code}).json()["status"] == "pending"  # and must be approved again
    assert full.as_(ASHA).delete(f"/cases/{CASE}/team/residents/{ASHA}").status_code == 200  # the resident leaves itself
    assert full.as_(ASHA).get(f"/cases/{CASE}").status_code == 403
    assert full.as_(RAO).delete(f"/cases/{CASE}/team/code").status_code == 200
    assert full.as_(RAO).get(f"/cases/{CASE}/team").json()["join_code"] is None
    k = kinds(CASE)
    assert {"join_code_created", "join_requested", "resident_approved", "resident_joined", "resident_removed", "join_code_cleared"} <= set(k)


def test_join_attempts_are_rate_limited_per_login(full, tb002):
    code = full.as_(RAO).post(f"/cases/{CASE}/team/code").json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert full.as_(VIJAY).post("/case-join", {"code": wrong}).status_code == 404
    r = full.as_(VIJAY).post("/case-join", {"code": code})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert full.as_(ASHA).post("/case-join", {"code": code}).status_code == 200  # another login keeps its own count
    assert full.as_(VIJAY).post("/case-join", {"code": "12"}).status_code == 429


def test_an_expired_code_is_no_code(full, tb002):
    code = full.as_(RAO).post(f"/cases/{CASE}/team/code").json()["code"]
    c = store.get_case(CASE)
    c["team"]["join_code"]["expires"] = "2020-01-01T00:00:00"
    store.save_case(c)
    assert full.as_(VIJAY).post("/case-join", {"code": code}).status_code == 404


# ---- urgency -------------------------------------------------------------------------------------------------------------------------

def test_urgency_is_set_by_the_consultant_and_proposed_by_the_resident(full, tb002):
    r = full.as_(RAO).put(f"/cases/{CASE}/urgency", {"level": 4, "note": "synthetic"})
    assert r.status_code == 200 and r.json()["urgency"]["level"] == 4 and r.json()["urgency"]["set_by"] == RAO
    assert full.as_(RAO).put(f"/cases/{CASE}/urgency", {"level": 7}).status_code == 400
    assert full.as_(MEHTA).put(f"/cases/{CASE}/urgency", {"level": 1}).status_code == 403
    assert full.as_(ANIL).put(f"/cases/{CASE}/urgency", {"level": 1}).status_code == 403  # the coordinator never sets urgency
    r = full.as_(ASHA).put(f"/cases/{CASE}/urgency", {"level": 5})
    assert r.status_code == 200 and r.json()["proposal"]["action"] == "urgency"
    u = team.urgency_view(store.get_case(CASE))
    assert u["level"] == 4 and u["proposed"]["level"] == 5 and u["proposed"]["by"] == ASHA
    pid = r.json()["proposal"]["id"]
    assert full.as_(RAO).post(f"/cases/{CASE}/proposals/{pid}/approve").status_code == 200
    u = team.urgency_view(store.get_case(CASE))
    assert u["level"] == 5 and u["set_by"] == RAO and u["proposed"] is None and u["label"] == "Most urgent"
    assert [e["level"] for e in store.read_audit(CASE) if e.get("kind") == "urgency_set"] == [4, 5]


# ---- archive, consent ----------------------------------------------------------------------------------------------------------------

def test_archive_refuses_every_change_until_it_is_taken_back(full, tb002):
    assert full.as_(MEHTA).post(f"/cases/{CASE}/archive", {"reason": "x"}).status_code == 403
    assert full.as_(ASHA).post(f"/cases/{CASE}/archive", {"reason": "x"}).status_code == 403
    assert full.as_(RAO).post(f"/cases/{CASE}/archive", {"reason": ""}).status_code == 400
    r = full.as_(RAO).post(f"/cases/{CASE}/archive", {"reason": "duplicate Case File (synthetic)"})
    assert r.status_code == 200 and r.json()["archived"]["by"] == RAO
    assert full.as_(RAO).get(f"/cases/{CASE}").status_code == 200  # readers keep reading
    changes = [full.as_(RAO).post(f"/cases/{CASE}/confirmations", {"type": "waive", "key": "bone_scan", "reason": "x"}),
               full.as_(RAO).put(f"/cases/{CASE}/urgency", {"level": 3}),
               full.as_(RAO).post(f"/cases/{CASE}/ready", {"ready": True}),
               full.as_(RAO).post(f"/cases/{CASE}/requests", {"department": "pathology", "label": "IHC"}),
               full.as_(RAO).post(f"/cases/{CASE}/team/code"),
               full.as_(RAO).put(f"/cases/{CASE}/consent", {"outside_discussion": True}),
               full.as_(ASHA).post(f"/cases/{CASE}/proposals", {"action": "urgency", "payload": {"level": 2}})]
    for x in changes:
        assert x.status_code in (403, 409), x.text
        assert "This Case File is archived" in str(x.json()["detail"]), x.text
    assert full.as_(RAO).post(f"/cases/{CASE}/archive", {"reason": "again"}).status_code == 409
    assert full.as_(ANIL).post(f"/cases/{CASE}/unarchive", {"note": "archived by mistake"}).status_code == 200  # the coordinator may take it back
    assert not access.is_archived(store.get_case(CASE))
    assert full.as_(RAO).put(f"/cases/{CASE}/urgency", {"level": 3}).status_code == 200
    k = kinds(CASE)
    assert "case_archived" in k and "case_unarchived" in k


def test_consent_is_recorded_by_the_owner(full, tb002):
    assert full.as_(RAO).put(f"/cases/{CASE}/consent", {"outside_discussion": "yes"}).status_code == 400
    r = full.as_(RAO).put(f"/cases/{CASE}/consent", {"outside_discussion": True, "note": "patient agreed (synthetic)"})
    assert r.status_code == 200 and r.json()["consent"]["outside_discussion"] is True and r.json()["consent"]["by"] == RAO
    assert store.get_case(CASE)["consent"]["outside_discussion"] is True
    assert full.as_(MEHTA).put(f"/cases/{CASE}/consent", {"outside_discussion": False}).status_code == 403
    assert "consent_set" in kinds(CASE)


# ---- break-glass ----------------------------------------------------------------------------------------------------------------------

def test_break_glass_opens_one_case_file_for_the_vaidyx_admin_with_a_reason(full, tb002):
    r = full.as_(VX).get(f"/cases/{CASE}")
    assert r.status_code == 403 and "break-glass" in r.json()["detail"]["message"] and r.json()["detail"]["break_glass"] is False
    assert CASE not in {c["case_id"] for c in full.as_(VX).get("/cases").json().get("cases", [])}
    assert full.as_(VX).post("/break-glass", {"case_id": CASE, "reason": ""}).status_code == 400
    assert full.as_(RAO).post("/break-glass", {"case_id": CASE, "reason": "x"}).status_code == 409  # the owner opens it already (item 1.9)
    assert full.as_(ROOT).post("/break-glass", {"case_id": CASE, "reason": "x"}).status_code == 403
    assert full.as_(VX).post("/break-glass", {"case_id": "TB-NONE", "reason": "x"}).status_code == 404
    r = full.as_(VX).post("/break-glass", {"case_id": CASE, "reason": "support ticket 42 (synthetic)"})
    assert r.status_code == 200 and r.json()["until"] > store.now_iso()
    assert full.as_(VX).get(f"/cases/{CASE}").status_code == 200
    assert full.as_(VX).get("/cases/TB-001").status_code == 403  # one Case File per window
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "break_glass")
    assert ev["by"] == VX and ev["reason"] == "support ticket 42 (synthetic)"
    assert any(n["kind"] == "break_glass" for n in notes_for(RAO))  # the owner is told
    assert full.as_(AUDIT).get("/break-glass").json()["windows"][VX]["case_id"] == CASE
    assert full.as_(VX).delete("/break-glass").status_code == 200
    assert full.as_(VX).get(f"/cases/{CASE}").status_code == 403
    assert "break_glass_closed" in kinds(CASE)
