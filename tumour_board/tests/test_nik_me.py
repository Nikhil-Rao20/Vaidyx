"""The new interface's routers (18 Oct 2026): GET /me per role, the password change, the profile, the activity log; plus the shared
test app (the same route class as the live API, a fake Vaidyx login system, an organisation with one login of every role) the other
test_nik_* files reuse. Synthetic logins and Case Files only; every test runs in the conftest temporary data root."""
import copy, datetime as dt, json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from tumour_board import access, org, profiles, store
from tumour_board.tests import util

RAO = "dr.rao@hospital.example"      # consultant, Breast Surgery (treating): owns the Case Files
MEHTA = "dr.mehta@hospital.example"  # consultant, Medical Oncology (treating)
ASHA = "dr.asha@hospital.example"    # resident, Breast Surgery
VIJAY = "dr.vijay@hospital.example"  # resident, Medical Oncology (another department)
OLD = "dr.old@hospital.example"      # resident, Breast Surgery, past the end date
RAVI = "ravi"                        # supporting doctor, Radiology
ANIL = "anil"                        # MDT Coordinator
DEEPAK = "deepak"                    # department admin of Breast Surgery
ROOT = "tbroot"                      # root admin
AUDIT = "auditor1"                   # auditor
GUEST = "guest1"                     # outside expert
VX = "vx"                            # the Vaidyx admin (server administrator), not in org.json
NEXT_YEAR = (dt.date.today() + dt.timedelta(days=365)).isoformat()
LAST_YEAR = (dt.date.today() - dt.timedelta(days=30)).isoformat()


class FakeAuth:
    """The slice of core.auth.AuthManager the routers use: users, is_admin, get_privileges, create_user, reset_password, change_password,
    must_change_password, list_users. Passwords are kept in clear here (a fake), never written anywhere."""

    def __init__(self, users=None, admins=()):
        self.users = {u: {"is_admin": u in admins, "pw": "old-" + u, "privileges": {"can_use_bash": False}} for u in (users or [])}
        self.resets = []  # (username, must_change): never the password

    def is_admin(self, u):
        return bool(self.users.get(u, {}).get("is_admin"))

    def get_privileges(self, u):
        return self.users.get(u, {}).get("privileges", {"can_use_bash": False})

    def create_user(self, u, pw, is_admin=False):
        if u in self.users:
            return False
        self.users[u] = {"is_admin": is_admin, "pw": pw, "privileges": {"can_use_bash": False}}
        return True

    def reset_password(self, u, pw, must_change=True):
        if u not in self.users or not pw:
            return False
        self.users[u]["pw"] = pw
        self.users[u]["must_change"] = bool(must_change)
        self.resets.append((u, bool(must_change)))
        return True

    def change_password(self, u, cur, new):
        if self.users.get(u, {}).get("pw") != cur:
            return False
        self.users[u]["pw"] = new
        self.users[u].pop("must_change", None)
        return True

    def must_change_password(self, u):
        return bool(self.users.get(u, {}).get("must_change"))

    def list_users(self):
        return [{"username": u, "is_admin": d["is_admin"]} for u, d in self.users.items()]


@pytest.fixture
def people(data_root):
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {
        RAO: {"departments": {"breast_surgery": "member"}, "display_name": "Dr Rao (synthetic)"},
        MEHTA: {"departments": {"medical_oncology": "head"}, "display_name": "Dr Mehta (synthetic)"},
        ASHA: {"departments": {"breast_surgery": "resident"}, "display_name": "Dr Asha (synthetic)", "end_date": NEXT_YEAR},
        VIJAY: {"departments": {"medical_oncology": "resident"}, "display_name": "Dr Vijay (synthetic)", "end_date": NEXT_YEAR},
        OLD: {"departments": {"breast_surgery": "resident"}, "display_name": "Dr Old (synthetic)", "end_date": LAST_YEAR},
        RAVI: {"departments": {"radiology": "member"}, "display_name": "Dr Ravi (synthetic)"},
        ANIL: {"coordinator": True, "display_name": "Anil (synthetic)"},
        DEEPAK: {"admin_of": ["breast_surgery"]},
        ROOT: {},
        AUDIT: {"auditor": True},
        GUEST: {"outside_expert": True},
    }
    o["admins"] = [ROOT]
    org.save(o, by="test")
    return {k: org.roles(k) for k in o["users"]} | {VX: org.roles(VX, vaidyx_admin=True)}


@pytest.fixture
def auth(people):
    return FakeAuth(list(people) + [VX], admins=(VX,))


class Api:
    """The test client with a switchable login: api.as_(user).get("/me")."""

    def __init__(self, tc, who):
        self.tc, self.who = tc, who

    def as_(self, user):
        self.who["user"] = user
        return self

    def get(self, path, **kw):
        return self.tc.get("/api/tb" + path, **kw)

    def post(self, path, json=None, **kw):
        return self.tc.post("/api/tb" + path, json=json if json is not None else {}, **kw)

    def put(self, path, json=None, **kw):
        return self.tc.put("/api/tb" + path, json=json if json is not None else {}, **kw)

    def delete(self, path, **kw):
        return self.tc.delete("/api/tb" + path, **kw)


@pytest.fixture
def api(auth):
    """A small app holding the four routers under /api/tb with the live route class (the Case File guard, the disabled-login refusal), a
    middleware that signs the request in as `who`, and the fake login system."""
    from routes.tumour_board_routes import _ModelErrorRoute
    from tumour_board.api import cases_list, me, setup, team
    app = FastAPI()
    who = {"user": RAO}

    @app.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)

    r = APIRouter(prefix="/api/tb", route_class=_ModelErrorRoute)
    for m in (me, cases_list, team, setup):
        r.include_router(m.router)
    app.include_router(r)
    app.state.auth_manager = auth
    me.PASSWORD_LIMIT._hits.clear()
    team.JOIN_LIMIT._hits.clear()
    with TestClient(app) as tc:
        yield Api(tc, who)


def make_case(case_id="TB-NIK-1", owner="breast_surgery", protocol="breast", **extra):
    c = store.create_case(case_id, dict(util.PATIENT), protocol, created_by=RAO)
    if owner:
        c["department"] = owner
    c.update(extra)
    store.save_case(c)
    return c


def audit_text(case_id):
    return (store.case_dir(case_id) / "audit.jsonl").read_text() if (store.case_dir(case_id) / "audit.jsonl").exists() else ""


# ---- GET /me per role ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("user,primary,known", [
    (RAO, "treating", True), (MEHTA, "treating", True), (ASHA, "resident", True), (RAVI, "supporting", True), (ANIL, "coordinator", True),
    (DEEPAK, "dept_admin", False), (ROOT, "root_admin", False), (AUDIT, "auditor", False), (GUEST, "outside_expert", False), (VX, "root_admin", True),
])
def test_me_shape_per_role(api, user, primary, known):
    r = api.as_(user).get("/me")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["user"] == user and m["primary_role"] == primary and m["roles"]["known"] is known
    assert set(m) >= {"user", "display_name", "roles", "primary_role", "must_change_password", "profile", "setup_needed", "counts", "hospital", "features"}
    assert set(m["roles"]) >= {"admin", "root_admin", "coordinator", "auditor", "departments", "treating", "supporting", "resident", "admin_of", "outside_expert", "disabled"}
    assert set(m["counts"]) == {"unread", "waiting_for_me", "open_requests"} and all(isinstance(v, int) for v in m["counts"].values())
    assert m["features"] == {"video": False, "push": False} and m["hospital"]["level"] == "essential"
    assert m["must_change_password"] is False and set(m["profile"]) == set(profiles.FIELDS)
    assert "password" not in json.dumps(m["profile"]).lower()


def test_me_reports_the_expired_resident_and_the_vaidyx_admin(api):
    m = api.as_(OLD).get("/me").json()
    assert m["roles"]["expired"] is True and m["roles"]["known"] is False and m["roles"]["departments"] == {} and m["primary_role"] == "none"
    m = api.as_(VX).get("/me").json()
    assert m["roles"]["vaidyx_admin"] is True and m["roles"]["admin"] is True and m["departments"] == []


def test_me_counts_waiting_and_open_requests(api, people):
    c = make_case()
    st = store.get_state("TB-NIK-1")
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "breast_imaging", "label": "Mammogram", "department": "Radiology", "department_id": "radiology",
                      "status": "pending", "created": store.now_iso(), "due": NEXT_YEAR, "history": [], "sent": {"by": RAO, "at": store.now_iso(), "count": 1}}]
    store.save_state("TB-NIK-1", st)
    assert api.as_(RAVI).get("/me").json()["counts"]["open_requests"] == 1
    assert api.as_(RAO).get("/me").json()["counts"]["waiting_for_me"] == 0
    from tumour_board import proposals
    proposals.propose("TB-NIK-1", "urgency", {"level": 4}, "please", ASHA, people[ASHA])
    m = api.as_(RAO).get("/me").json()
    assert m["counts"]["waiting_for_me"] == 1 and m["counts"]["unread"] >= 1


def test_me_setup_needed_until_name_and_registration(api):
    assert api.as_(RAO).get("/me").json()["setup_needed"] is True  # a doctor: no registration number yet
    r = api.put("/me/profile", {"display_name": "Dr Rao (synthetic)", "registration_no": "TN/12345", "theme": "dark", "text_size": "large", "phone": "+91 98765 43210", "phone_visible": True})
    assert r.status_code == 200, r.text
    assert r.json()["setup_needed"] is False and r.json()["profile"]["theme"] == "dark" and r.json()["profile"]["registration_no"] == "TN/12345"
    assert api.get("/me").json()["setup_needed"] is False
    assert api.as_(ANIL).get("/me").json()["setup_needed"] is True  # the coordinator needs a display name only
    assert api.put("/me/profile", {"display_name": "Anil Kumar (synthetic)"}).json()["setup_needed"] is False


def test_profile_validation_and_mirroring(api):
    api.as_(RAO)
    assert api.put("/me/profile", {"theme": "neon"}).status_code == 400
    assert api.put("/me/profile", {"photo": "data:text/plain;base64,QUJD"}).status_code == 400
    big = "data:image/png;base64," + ("QUJD" * (70 * 1024))  # about 210 KB decoded
    r = api.put("/me/profile", {"photo": big})
    assert r.status_code == 400 and "200 KB" in r.json()["detail"]["message"]
    assert api.put("/me/profile", {"photo": "data:image/png;base64,iVBORw0KGgo="}).status_code == 200
    assert api.put("/me/profile", {"saved_filters": [{"name": "Mine", "query": {"mine": "1"}, "pinned": True}]}).json()["profile"]["saved_filters"][0]["pinned"] is True
    r = api.put("/me/profile", {"display_name": "Dr Rao Renamed (synthetic)"})
    assert r.status_code == 200
    assert org.load()["users"][RAO]["display_name"] == "Dr Rao Renamed (synthetic)" and profiles.display_name(RAO) == "Dr Rao Renamed (synthetic)"
    ev = [e for e in org.read_audit() if e["kind"] == "profile_updated"]
    assert ev and ev[0]["username"] == RAO and "display_name" in ev[0]["fields"] and "Renamed" not in json.dumps(ev)  # names of fields, never values
    assert not any("9876" in json.dumps(e) for e in org.read_audit())  # the phone never reaches the log


# ---- POST /me/password ------------------------------------------------------------------------------------------------------------------

def test_password_change_clears_the_flag_checks_the_current_one_and_is_rate_limited(api, auth):
    auth.reset_password(RAO, "first-pass-1234", must_change=True)
    assert api.as_(RAO).get("/me").json()["must_change_password"] is True
    r = api.post("/me/password", {"current_password": "wrong", "new_password": "a-new-password-9"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wrong_password"
    assert api.post("/me/password", {"current_password": "first-pass-1234", "new_password": "short"}).status_code == 400
    r = api.post("/me/password", {"current_password": "first-pass-1234", "new_password": "a-new-password-9"})
    assert r.status_code == 200 and r.json() == {"ok": True, "must_change_password": False}
    assert auth.users[RAO]["pw"] == "a-new-password-9" and api.get("/me").json()["must_change_password"] is False
    assert any(e["kind"] == "password_changed" and e["by"] == RAO for e in org.read_audit())
    assert "a-new-password-9" not in json.dumps(org.read_audit())
    for _ in range(3):
        api.post("/me/password", {"current_password": "x", "new_password": "a-new-password-9"})
    assert api.post("/me/password", {"current_password": "x", "new_password": "a-new-password-9"}).status_code == 429


# ---- activity -------------------------------------------------------------------------------------------------------------------------------

def test_my_activity_lists_my_own_actions_and_the_full_log_is_for_the_auditor(api, people):
    make_case()
    store.audit("TB-NIK-1", {"kind": "confirmation", "type": "waive", "key": "histopathology", "reason": "biopsy elsewhere", "by": RAO})
    store.audit("TB-NIK-1", {"kind": "request_sent", "action": "A1", "department": "Radiology", "by": MEHTA})
    api.as_(RAO).put("/me/profile", {"title": "Consultant"})
    r = api.as_(RAO).get("/me/activity")
    assert r.status_code == 200
    evs = r.json()["events"]
    assert evs and all(e["by"] == RAO for e in evs) and {e["kind"] for e in evs} >= {"confirmation", "profile_updated"}
    conf = next(e for e in evs if e["kind"] == "confirmation")
    assert conf["case_id"] == "TB-NIK-1" and conf["title"] == "Confirmation" and "histopathology" in conf["detail"] and "biopsy elsewhere" in conf["detail"]
    assert evs == sorted(evs, key=lambda e: e["ts"], reverse=True) and r.json()["total"] >= 2
    assert not any(e["by"] == MEHTA for e in evs)
    assert api.as_(RAO).get("/activity").status_code == 403
    assert api.as_(RAVI).get("/activity").status_code == 403
    for who in (AUDIT, ANIL, ROOT):
        r = api.as_(who).get("/activity?limit=50")
        assert r.status_code == 200, who
        assert {e["by"] for e in r.json()["events"]} >= {RAO, MEHTA}
    r = api.as_(AUDIT).get("/activity?user=" + MEHTA)
    assert [e["kind"] for e in r.json()["events"]] == ["request_sent"]
    r = api.as_(AUDIT).get("/activity?case_id=TB-NIK-1")
    assert all(e["case_id"] == "TB-NIK-1" for e in r.json()["events"]) and len(r.json()["events"]) >= 2
    assert any(e["kind"] == "activity_read" and e["by"] == AUDIT for e in org.read_audit())  # reading the log is itself recorded
    assert api.as_(AUDIT).get("/case-list").status_code == 403  # the auditor reads the log, never the Case Files


def test_disabled_login_is_refused_on_every_route(api):
    o = copy.deepcopy(org.load()); o["users"][RAVI]["disabled"] = True; org.save(o, by="test")
    assert api.as_(RAVI).get("/me").status_code == 403
    assert api.as_(RAVI).get("/case-list").status_code == 403
