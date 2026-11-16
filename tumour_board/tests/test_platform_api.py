"""The Vaidyx console API (admin consoles Phase B, 16 Nov 2026, docs/admin-console/DESIGN.md 5.3, API_FIELDS.md) through the real routes with
a fake login system: only the Vaidyx admin; a hospital made end to end (folder, registry, org.json, first hospital admin with a first
password shown once, audit lines, never a password in a file or a log); the demo hospital system option; suspend and reactivate; the
last-admin rule; logins of another hospital refused; the logins list and its filters; activity texts; the exact answer shapes; no patient
name or UHID in any answer; an unknown X-TB-Hospital refused. Synthetic data only."""
import copy, json, logging, shutil
from urllib.parse import unquote

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tumour_board import accounts, config, his_client, hospitals, org, platform_admin, store
from tumour_board.tests.conftest import FIXTURES

PATIENT, UHID = "SYNTHETIC, Platform Patientname", "SYN-PLAT-774411"


class FakeAuth:
    is_configured = True

    def __init__(self):
        self.users = {"vx": {"is_admin": True}, "root": {}, "doc": {}, "mdt": {}}
        self.must = set()
        self.passwords = {}

    def is_admin(self, u):
        return bool(self.users.get(u, {}).get("is_admin"))

    def get_username_for_token(self, token):
        return token[4:] if token and token.startswith("tok-") and token[4:] in self.users else None

    def get_privileges(self, u):
        return {"can_use_bash": bool(self.users.get(u, {}).get("is_admin"))}

    def create_user(self, u, pw, is_admin=False):
        if u in self.users:
            return False
        self.users[u] = {"is_admin": is_admin}
        self.passwords[u] = pw
        return True

    def reset_password(self, u, pw, must_change=True):
        if u not in self.users:
            return False
        self.passwords[u] = pw
        (self.must.add if must_change else self.must.discard)(u)
        return True

    def must_change_password(self, u):
        return u in self.must

    def list_users(self):
        return [{"username": u, "is_admin": bool(d.get("is_admin"))} for u, d in self.users.items()]


def make_app(auth):
    from routes.tumour_board_routes import setup_tumour_board_routes
    app = FastAPI()
    app.state.auth_manager = auth

    @app.middleware("http")
    async def session_cookie(request: Request, call_next):
        tok = request.cookies.get("vaidyx_session")
        request.state.current_user = auth.get_username_for_token(tok) if tok else None
        return await call_next(request)
    app.include_router(setup_tumour_board_routes())
    return app


@pytest.fixture
def world(data_root, monkeypatch):
    """The default hospital: root (hospital admin), doc (a doctor), mdt (coordinator); TB-001 (a known synthetic patient, open) and
    TB-002 (decided: a board record after its listing)."""
    monkeypatch.setenv("TB_SCHEDULER", "0")
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["hospital"]["name"] = "Vaidyx Demo Hospital"
    o["admins"] = ["root"]
    o["users"] = {"root": {"display_name": "Hospital IT"}, "doc": {"display_name": "Dr Anil", "departments": {"radiology": "member"}},
                  "mdt": {"display_name": "Priya Nair", "coordinator": True}}
    org.save(o, by="test")
    for cid in ("TB-001", "TB-002"):
        shutil.copytree(FIXTURES / "cases" / cid, config.CASES_DIR / cid)
    c = store.get_case("TB-001"); c["patient"]["name"] = PATIENT; c["patient"]["mrn"] = UHID; store.save_case(c)
    p = config.CASES_DIR / "TB-002" / "state.json"
    st = json.loads(p.read_text()); st["board_records"] = [{"recorded_at": "2026-11-01T10:00:00", "decision_text": "synthetic"}]
    p.write_text(json.dumps(st))
    store._docs_cache.clear()
    auth = FakeAuth()
    with TestClient(make_app(auth)) as tc:
        yield tc, auth


def call(tc, user, method, path, json_body=None, **headers):
    tc.cookies.set("vaidyx_session", f"tok-{user}")
    return tc.request(method, "/api/tb" + path, json=json_body, headers=headers)


NEW = {"name": "Lotus Cancer Centre", "city": "Nellore", "state": "Andhra Pradesh", "type": "private", "level": "optimal",
       "pmjay_empanelled": False, "admin": {"display_name": "Ravi Teja", "email": "it.admin@lotus.example"}}


def make_hospital(tc, **over):
    r = call(tc, "vx", "POST", "/platform/hospitals", {**NEW, **over})
    assert r.status_code == 200, r.text
    return r.json()


def _files_text(*roots) -> str:
    out = []
    for root in roots:
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    out.append(p.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass
    return "\n".join(out)


# ---- who may ----------------------------------------------------------------------------------------------------------------------

GETS = ("/platform/overview", "/platform/hospitals", "/platform/hospitals/default", "/platform/logins", "/platform/activity")


def test_only_the_vaidyx_admin(world):
    tc, _ = world
    for path in GETS:
        assert call(tc, "vx", "GET", path).status_code == 200, path
        for who in ("root", "doc"):
            r = call(tc, who, "GET", path)
            assert r.status_code == 403 and r.json()["detail"] == {"message": "Only the Vaidyx admin opens the Vaidyx console.", "code": "forbidden"}
    for who in ("root", "doc"):
        assert call(tc, who, "POST", "/platform/hospitals", NEW).status_code == 403
        assert call(tc, who, "POST", "/platform/logins/doc/reset-password", {}).status_code == 403
        assert call(tc, who, "POST", "/platform/logins/doc/disable", {}).status_code == 403
    assert not [h for h in hospitals.ids() if h not in ("default", "strict-probe")]  # nothing was made (strict-probe: the strict-mode run's)


# ---- a hospital end to end ----------------------------------------------------------------------------------------------------------

def test_create_a_hospital_end_to_end(world, caplog):
    tc, auth = world
    caplog.set_level(logging.DEBUG)
    out = make_hospital(tc)
    h, a = out["hospital"], out["admin"]
    hid = h["id"]
    assert hid == "lotus-cancer-centre" and h["name"] == "Lotus Cancer Centre" and h["status"] == "active" and h["city"] == "Nellore"
    assert h["type"] == "private" and h["level"] == "optimal" and h["pmjay_empanelled"] is False and h["admins"] == 1 and h["people"] == 1
    assert h["case_files"] == {"open": 0, "decided": 0, "total": 0} and h["his"]["state"] == "not_set" and h["his"]["demo"] is False
    pw = a["password_once"]
    assert a["username"] == "it.admin@lotus.example" and len(pw) == accounts.PASSWORD_CHARS
    assert a["mailto"].startswith("mailto:it.admin@lotus.example?") and pw in unquote(a["mailto"]) and "Lotus Cancer Centre" in unquote(a["mailto"])
    # folder, registry, org.json, the login (plain, first password must be changed), registered to the hospital
    folder = config.root_for(hid)
    assert folder.is_dir() and (folder / "org.json").exists()
    assert hospitals.get(hid)["name"] == "Lotus Cancer Centre" and hospitals.hospital_of("it.admin@lotus.example") == hid
    with config.use_hospital(hid):
        o = org.load()
        assert o["hospital"]["name"] == "Lotus Cancer Centre" and o["hospital"]["type"] == "private" and o["hospital"]["level"] == "optimal"
        assert o["hospital"]["pmjay_empanelled"] is False and o["admins"] == ["it.admin@lotus.example"]
        assert o["users"]["it.admin@lotus.example"]["display_name"] == "Ravi Teja"
        assert his_client.settings()["kind"] == "none" and his_client.client() is None  # never the demo by accident
        kinds = [e["kind"] for e in org.read_audit(100)]
    assert {"hospital_created", "admin_added", "account_created", "first_password_set"} <= set(kinds)
    assert not auth.is_admin("it.admin@lotus.example") and not auth.get_privileges("it.admin@lotus.example")["can_use_bash"]
    assert auth.must_change_password("it.admin@lotus.example") and auth.passwords["it.admin@lotus.example"] == pw
    pkinds = [e["kind"] for e in hospitals.read_audit(100, hospital=hid)]
    assert "hospital_created" in pkinds and "admin_added" in pkinds
    # the default hospital is untouched; the password is in no file and no log line
    assert "it.admin@lotus.example" not in org.load()["users"]
    assert pw not in _files_text(config.BASE_ROOT, config.HOSPITALS_ROOT)
    assert pw not in caplog.text
    # in the list, the overview and the detail
    assert hid in [x["id"] for x in call(tc, "vx", "GET", "/platform/hospitals").json()["hospitals"]]
    d = call(tc, "vx", "GET", f"/platform/hospitals/{hid}").json()
    assert d["admins"][0]["username"] == "it.admin@lotus.example" and d["admins"][0]["must_change_password"] is True
    assert d["people_by_role"]["hospital_admins"] == 1 and d["people_by_role"]["never_signed_in"] == 1
    assert pw not in json.dumps(d)


def test_create_is_validated_and_never_reuses_a_login(world):
    tc, _ = world
    for over, word in (({"name": "AB"}, "at least 3"), ({"name": "x" * 121}, "too long"), ({"city": "y" * 61}, "too long"),
                       ({"type": "trust"}, "public or private"), ({"level": "tertiary"}, "NCG level"), ({"pmjay_empanelled": "yes"}, "true or false"),
                       ({"admin": {"display_name": "A", "email": "not-an-email"}}, "email"), ({"admin": {"display_name": "", "email": "a@b.example"}}, "name")):
        r = call(tc, "vx", "POST", "/platform/hospitals", {**NEW, **over})
        assert r.status_code == 400 and word in r.json()["detail"]["message"], (over, r.text)
    r = call(tc, "vx", "POST", "/platform/hospitals", {**NEW, "admin": {"display_name": "Doc", "email": "doc@x.example"}})
    assert r.status_code == 200  # a new email is fine
    tc_auth_users = call(tc, "vx", "GET", "/platform/logins").json()["logins"]
    assert any(x["username"] == "doc@x.example" for x in tc_auth_users)
    r = call(tc, "vx", "POST", "/platform/hospitals", {**NEW, "name": "Second Hospital", "admin": {"display_name": "Doc", "email": "doc@x.example"}})
    assert r.status_code == 409 and "another hospital" in r.json()["detail"]["message"]
    r = call(tc, "vx", "POST", "/platform/hospitals", {**NEW, "name": "Third Hospital", "admin": {"display_name": "Vx", "email": "vx@x.example"}})
    assert r.status_code == 200
    assert "second-hospital" not in hospitals.ids()  # refused before anything was made


def test_demo_his_option(world, tmp_path):
    tc, _ = world
    token_file = tmp_path / "demo_token"
    token_file.write_text("synthetic-demo-token-77\n")
    his_client.settings_path().write_text(json.dumps({"kind": "fhir", "label": "Demo HIS (SYNTHETIC)", "url": "http://127.0.0.1:7130",
                                                      "token_file": str(token_file), "enabled": True, "pacs_url": "http://127.0.0.1:8042"}))
    out = make_hospital(tc, demo_his=True)
    hid = out["hospital"]["id"]
    assert out["hospital"]["his"] == {"state": "not_tested", "url_set": True, "tested_at": None, "ok": None, "demo": True}
    with config.use_hospital(hid):
        cfg = his_client.settings()
        saved = json.loads(his_client.settings_path().read_text())
    assert cfg["url"] == "http://127.0.0.1:7130" and cfg["token_file"] == str(token_file) and cfg["kind"] == "fhir" and cfg["enabled"]
    assert saved["token"] == "" and (config.root_for(hid) / "his.json").stat().st_mode & 0o777 == 0o600
    assert "synthetic-demo-token-77" not in json.dumps(out) and "synthetic-demo-token-77" not in _files_text(config.HOSPITALS_ROOT)
    # a default hospital on a real hospital system is never copied: the new hospital gets the built-in demo
    his_client.settings_path().write_text(json.dumps({"kind": "fhir", "url": "https://his.real-hospital.example", "token": "real-secret",
                                                      "enabled": True}))
    hid2 = make_hospital(tc, name="Second Demo Hospital", demo_his=True, admin={"display_name": "B", "email": "b@second.example"})["hospital"]["id"]
    with config.use_hospital(hid2):
        cfg = his_client.settings()
    assert cfg["url"] == his_client.DEFAULT_URL and "real-secret" not in (config.root_for(hid2) / "his.json").read_text()


# ---- status, admins, logins -----------------------------------------------------------------------------------------------------------

def test_suspend_and_reactivate(world):
    tc, auth = world
    hid = make_hospital(tc)["hospital"]["id"]
    r = call(tc, "vx", "POST", "/platform/hospitals/default/status", {"status": "suspended", "reason": "Testing"})
    assert r.status_code == 409 and "default hospital cannot be suspended" in r.json()["detail"]["message"]
    assert call(tc, "vx", "POST", f"/platform/hospitals/{hid}/status", {"status": "suspended", "reason": "ab"}).status_code == 400
    assert call(tc, "vx", "POST", f"/platform/hospitals/{hid}/status", {"status": "closed", "reason": "abcd"}).status_code == 400
    assert call(tc, "vx", "POST", "/platform/hospitals/no-such/status", {"status": "suspended", "reason": "abcd"}).status_code == 404
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/status", {"status": "suspended", "reason": "Contract paused (test)"})
    assert r.status_code == 200 and r.json()["hospital"]["status"] == "suspended" and r.json()["hospital"]["status_reason"] == "Contract paused (test)"
    r = call(tc, "it.admin@lotus.example", "GET", "/me")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "hospital_suspended"
    assert call(tc, "root", "GET", "/me").status_code == 200  # the others carry on
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/status", {"status": "active", "reason": ""})
    assert r.status_code == 200 and r.json()["hospital"]["status"] == "active" and r.json()["hospital"]["status_reason"] == ""
    auth.must.discard("it.admin@lotus.example")
    assert call(tc, "it.admin@lotus.example", "GET", "/me").status_code == 200
    texts = [e["text"] for e in call(tc, "vx", "GET", f"/platform/activity?hospital={hid}").json()["events"]]
    assert "Hospital suspended: Lotus Cancer Centre. Reason: Contract paused (test)" in texts and "Hospital reactivated: Lotus Cancer Centre" in texts


def test_admins_last_admin_rule_and_other_hospitals(world):
    tc, auth = world
    hid = make_hospital(tc)["hospital"]["id"]
    first = "it.admin@lotus.example"
    r = call(tc, "vx", "DELETE", f"/platform/hospitals/{hid}/admins/{first}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "last_admin"
    # a login of another hospital, a Vaidyx admin, an unknown login: refused
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"username": "doc"})
    assert r.status_code == 403 and r.json()["detail"]["message"] == accounts.OTHER_HOSPITAL
    assert call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"username": "vx"}).status_code == 409
    assert call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"username": "nobody.here"}).status_code == 404
    assert call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"username": first}).status_code == 409  # already one
    # a new email: a new login with a first password once
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"display_name": "Second Admin", "email": "second@lotus.example"})
    assert r.status_code == 200 and r.json()["created"] is True and r.json()["password_once"] and r.json()["mailto"].startswith("mailto:")
    assert hospitals.hospital_of("second@lotus.example") == hid and auth.must_change_password("second@lotus.example")
    # an existing login of this hospital is promoted (no password)
    with config.use_hospital(hid):
        accounts.ensure_account(auth, "plain@lotus.example", "Passw0rd-x1", "test")
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"username": "plain@lotus.example"})
    assert r.status_code == 200 and r.json()["created"] is False and "password_once" not in r.json() and "mailto" not in r.json()
    with config.use_hospital(hid):
        assert set(org.load()["admins"]) == {first, "second@lotus.example", "plain@lotus.example"}
    assert call(tc, "vx", "DELETE", f"/platform/hospitals/{hid}/admins/{first}").status_code == 200
    assert call(tc, "vx", "DELETE", f"/platform/hospitals/{hid}/admins/plain@lotus.example").status_code == 200
    assert call(tc, "vx", "DELETE", f"/platform/hospitals/{hid}/admins/second@lotus.example").status_code == 409
    # a suspended hospital may lose its last admin
    call(tc, "vx", "POST", f"/platform/hospitals/{hid}/status", {"status": "suspended", "reason": "Closing down (test)"})
    assert call(tc, "vx", "DELETE", f"/platform/hospitals/{hid}/admins/second@lotus.example").status_code == 200
    # the default hospital's admin cannot be added to Lotus by email either (one login, one hospital)
    r = call(tc, "vx", "POST", f"/platform/hospitals/{hid}/admins", {"display_name": "Root", "email": "root"})
    assert r.status_code == 400
    texts = [e["text"] for e in call(tc, "vx", "GET", "/platform/activity?kind=admin_removed").json()["events"]]
    assert "Hospital admin role removed from Ravi Teja" in texts


def test_reset_disable_and_cross_hospital(world):
    tc, auth = world
    hid = make_hospital(tc)["hospital"]["id"]
    r = call(tc, "vx", "POST", "/platform/logins/it.admin@lotus.example/reset-password", {})
    assert r.status_code == 200 and r.json()["password_once"] and r.json()["password_once"] in unquote(r.json()["mailto"])
    assert auth.passwords["it.admin@lotus.example"] == r.json()["password_once"] and auth.must_change_password("it.admin@lotus.example")
    assert r.json()["password_once"] not in _files_text(config.BASE_ROOT, config.HOSPITALS_ROOT)
    r = call(tc, "vx", "POST", "/platform/logins/doc/reset-password", {})  # a login of the default hospital, reset inside it
    assert r.status_code == 200 and auth.passwords["doc"] == r.json()["password_once"]
    r = call(tc, "vx", "POST", "/platform/logins/vx/reset-password", {})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "vaidyx_admin"
    assert call(tc, "vx", "POST", "/platform/logins/vx/disable", {}).status_code == 409
    assert call(tc, "vx", "POST", "/platform/logins/ghost/reset-password", {}).status_code == 404
    r = call(tc, "vx", "POST", "/platform/logins/doc/disable", {})
    assert r.status_code == 200 and org.load()["users"]["doc"]["disabled"] is True
    assert call(tc, "doc", "GET", "/me").status_code == 403
    assert call(tc, "vx", "POST", "/platform/logins/doc/enable", {}).status_code == 200 and org.load()["users"]["doc"]["disabled"] is False
    r = call(tc, "vx", "POST", "/platform/logins/root/disable", {})  # a hospital admin loses that role first
    assert r.status_code == 409 and "hospital admin" in r.json()["detail"]["message"]
    # a hospital admin of one hospital cannot reset or change a login of another through the existing routes
    auth.must.discard("it.admin@lotus.example")
    assert call(tc, "it.admin@lotus.example", "POST", "/accounts/doc/reset-password", {}).status_code in (403, 404)
    assert call(tc, "it.admin@lotus.example", "PUT", "/accounts/doc", {"disabled": True}).status_code in (403, 404)
    assert org.load()["users"]["doc"].get("disabled") is False
    kinds = [e["kind"] for e in call(tc, "vx", "GET", "/platform/activity").json()["events"]]
    assert {"password_reset", "login_disabled", "login_enabled"} <= set(kinds)


def test_logins_list_and_filters(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    rows = call(tc, "vx", "GET", "/platform/logins").json()["logins"]
    by = {x["username"]: x for x in rows}
    assert set(by) >= {"vx", "root", "doc", "mdt", "it.admin@lotus.example"}
    for x in rows:
        assert set(x) == {"username", "display_name", "hospital", "hospital_name", "roles", "disabled", "must_change_password", "vaidyx_admin"}
    assert by["vx"]["roles"] == ["vaidyx_admin"] and by["vx"]["vaidyx_admin"] is True and by["vx"]["hospital"] == "default"
    assert by["root"]["roles"] == ["hospital_admin"] and by["doc"]["roles"] == ["doctor"] and by["mdt"]["roles"] == ["coordinator"]
    assert by["it.admin@lotus.example"]["hospital"] == hid and by["it.admin@lotus.example"]["hospital_name"] == "Lotus Cancer Centre"
    assert by["it.admin@lotus.example"]["must_change_password"] is True and by["doc"]["display_name"] == "Dr Anil"
    only = call(tc, "vx", "GET", f"/platform/logins?hospital={hid}").json()["logins"]
    assert [x["username"] for x in only] == ["it.admin@lotus.example"]
    admins = call(tc, "vx", "GET", "/platform/logins?role=hospital_admin").json()["logins"]
    assert {x["username"] for x in admins} == {"root", "it.admin@lotus.example"}
    assert [x["username"] for x in call(tc, "vx", "GET", "/platform/logins?q=priya").json()["logins"]] == ["mdt"]
    assert [x["username"] for x in call(tc, "vx", "GET", "/platform/logins?role=vaidyx_admin").json()["logins"]] == ["vx"]


# ---- activity, shapes, privacy, the header ------------------------------------------------------------------------------------------

def test_activity_texts(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    call(tc, "vx", "PUT", f"/platform/hospitals/{hid}", {"name": "Lotus Cancer Centre", "city": "Tirupati", "state": "Andhra Pradesh"})
    call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": hid})
    evs = call(tc, "vx", "GET", "/platform/activity").json()["events"]
    for e in evs:
        assert set(e) == {"ts", "by", "by_name", "hospital", "hospital_name", "kind", "text"} and e["text"]
    texts = {e["kind"]: e["text"] for e in evs}
    assert texts["hospital_created"] == "Hospital added: Lotus Cancer Centre"
    assert texts["admin_added"] == "Hospital admin added: Ravi Teja (new login)"
    assert texts["hospital_updated"] == "Details changed for Lotus Cancer Centre: city"
    assert texts["acting_in"] == "Worked inside Lotus Cancer Centre"
    assert all(e["hospital_name"] == "Lotus Cancer Centre" for e in evs if e["hospital"] == hid)
    assert [e["kind"] for e in call(tc, "vx", "GET", "/platform/activity?kind=acting_in").json()["events"]] == ["acting_in"]
    assert call(tc, "vx", "GET", "/platform/activity?hospital=default").json()["events"] == []
    assert len(call(tc, "vx", "GET", "/platform/activity?limit=1").json()["events"]) == 1


ROW_KEYS = {"id", "name", "city", "state", "status", "status_reason", "created", "type", "level", "pmjay_empanelled", "admins", "people",
            "case_files", "setup", "his", "last_activity"}


def test_overview_and_detail_shapes(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    ov = call(tc, "vx", "GET", "/platform/overview").json()
    assert set(ov) == {"tiles", "hospitals", "attention"}
    assert set(ov["tiles"]) == {"hospitals_active", "hospitals_suspended", "logins", "hospital_admins", "case_files", "meetings_next_7_days",
                                "setup_complete", "his_connected"}
    rows = {r["id"]: r for r in ov["hospitals"]}
    for r in rows.values():
        assert ROW_KEYS <= set(r)
        assert set(r["case_files"]) == {"open", "decided", "total"} and set(r["setup"]) == {"done", "total"}
        assert set(r["his"]) == {"state", "url_set", "tested_at", "ok", "demo"} and r["his"]["state"] in ("connected", "failing", "not_tested", "not_set")
    d = rows["default"]
    assert d["name"] == "Vaidyx Demo Hospital" and d["case_files"] == {"open": 1, "decided": 1, "total": 2} and d["admins"] == 1 and d["people"] == 3
    assert d["last_activity"] and rows[hid]["case_files"]["total"] == 0
    t = ov["tiles"]
    assert t["case_files"] >= 2 and t["hospital_admins"] >= 2 and t["hospitals_active"] >= 2 and t["hospitals_suspended"] == 0
    assert t["logins"] >= 5  # 3 + 1 placed logins and the Vaidyx admin
    for a in ov["attention"]:
        assert set(a) == {"hospital", "hospital_name", "kind", "text"} and a["kind"] in ("no_admin", "setup_unfinished", "his_failing", "admin_never_signed_in")
    att = {(a["hospital"], a["kind"]): a["text"] for a in ov["attention"]}
    assert att[(hid, "admin_never_signed_in")] == "Ravi Teja has not signed in yet" and (hid, "setup_unfinished") in att
    det = call(tc, "vx", "GET", f"/platform/hospitals/{hid}").json()
    assert set(det) == {"hospital", "counts", "admins", "people_by_role", "setup", "his", "recent"}
    assert set(det["counts"]) == {"people", "case_files_open", "case_files_decided", "case_files_total", "meetings_next_7_days", "open_requests"}
    assert set(det["people_by_role"]) == {"doctors", "heads", "residents", "coordinators", "dept_admins", "hospital_admins", "auditors", "guests",
                                          "disabled", "never_signed_in"}
    assert set(det["admins"][0]) == {"username", "display_name", "disabled", "must_change_password", "last_sign_in"}
    assert [s["id"] for s in det["setup"]["steps"]] == ["hospital", "departments", "people", "his", "board"]
    assert all(set(s) == {"id", "label", "done", "summary"} for s in det["setup"]["steps"])
    assert all({"ts", "by", "kind", "text"} <= set(e) for e in det["recent"]) and det["recent"]
    assert call(tc, "vx", "GET", "/platform/hospitals/no-such").status_code == 404


def test_no_patient_data_in_any_console_answer(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    org.audit("break_glass", "vx", case_id="TB-001", patient=PATIENT, mrn=UHID, reason="synthetic test")  # a clinical event: never shown
    pages = [call(tc, "vx", "GET", p).text for p in (*GETS, f"/platform/hospitals/{hid}")]
    pages += [call(tc, who, "GET", p).text for who in ("root", "vx") for p in ("/hospital/overview", "/hospital/departments")]
    for text in pages:
        assert PATIENT not in text and UHID not in text and "Ramesh" not in text and "Lakshmi" not in text and "SYN-200417" not in text


def test_unknown_hospital_header_and_platform_ignores_the_header(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    r = call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": "gone-hospital"})
    assert r.status_code == 404 and r.json()["detail"] == {"message": "That hospital does not exist (any more). Choose another in the Vaidyx console.",
                                                          "code": "hospital_unknown"}
    assert call(tc, "vx", "GET", "/cases", **{"X-TB-Hospital": "../etc"}).status_code == 404
    assert call(tc, "vx", "GET", "/platform/overview", **{"X-TB-Hospital": "gone-hospital"}).status_code == 200
    me = call(tc, "vx", "GET", "/me", **{"X-TB-Hospital": "gone-hospital"})
    assert me.status_code == 200 and me.json()["acting_hospital"] is None and me.json()["hospital"]["id"] == "default"
    assert call(tc, "doc", "GET", "/org", **{"X-TB-Hospital": "gone-hospital"}).status_code == 200  # anyone else's header is ignored
    a = call(tc, "vx", "GET", "/platform/overview").json()
    b = call(tc, "vx", "GET", "/platform/overview", **{"X-TB-Hospital": hid}).json()
    strip = lambda ov: [{k: v for k, v in r.items() if k != "last_activity"} for r in ov["hospitals"]]
    assert strip(a) == strip(b) and a["tiles"] == b["tiles"]


def test_acting_in_is_recorded_once_per_entry(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    platform_admin._ACTING.clear()
    n = lambda: len(hospitals.read_audit(100, kind="acting_in"))
    call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": hid})
    call(tc, "vx", "GET", "/me", **{"X-TB-Hospital": hid})
    assert n() == 1
    call(tc, "vx", "GET", "/org")  # back in the Vaidyx console (no header)
    call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": hid})
    assert n() == 2
    call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": "default"})
    assert n() == 3 and hospitals.read_audit(1, kind="acting_in")[0]["hospital"] == "default"
    call(tc, "doc", "GET", "/org", **{"X-TB-Hospital": hid})  # never for anyone else
    assert n() == 3


def test_me_hospital_fields(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    m = call(tc, "vx", "GET", "/me").json()
    assert m["platform_admin"] is True and m["roles"]["vaidyx_admin"] is True and m["acting_hospital"] is None
    assert m["hospital"]["id"] == "default" and m["hospital"]["status"] == "active" and m["hospital"]["name"] == "Vaidyx Demo Hospital"
    m = call(tc, "vx", "GET", "/me", **{"X-TB-Hospital": hid}).json()
    assert m["acting_hospital"] == {"id": hid, "name": "Lotus Cancer Centre", "status": "active"} and m["hospital"]["id"] == hid
    m = call(tc, "root", "GET", "/me", **{"X-TB-Hospital": hid}).json()
    assert m["platform_admin"] is False and m["roles"]["vaidyx_admin"] is False and m["acting_hospital"] is None and m["hospital"]["id"] == "default"


def test_edit_details(world):
    tc, _ = world
    hid = make_hospital(tc)["hospital"]["id"]
    r = call(tc, "vx", "PUT", f"/platform/hospitals/{hid}", {"name": "Lotus Cancer Hospital", "city": "Tirupati", "state": "AP"})
    assert r.status_code == 200 and r.json()["hospital"]["name"] == "Lotus Cancer Hospital" and r.json()["hospital"]["city"] == "Tirupati"
    with config.use_hospital(hid):
        assert org.load()["hospital"]["name"] == "Lotus Cancer Hospital"  # the mail drafts and its pages use it
    assert call(tc, "vx", "PUT", f"/platform/hospitals/{hid}", {"name": "AB"}).status_code == 400
    assert call(tc, "vx", "PUT", f"/platform/hospitals/{hid}", {"level": "optimal"}).status_code == 400
    r = call(tc, "vx", "PUT", "/platform/hospitals/default", {"name": "Vaidyx Demo Hospital", "city": "Hyderabad", "state": "Telangana"})
    assert r.status_code == 200 and r.json()["hospital"]["city"] == "Hyderabad"  # the unchanged name of the default hospital is fine
    assert call(tc, "vx", "PUT", "/platform/hospitals/default", {"name": "Another Name"}).status_code == 409
