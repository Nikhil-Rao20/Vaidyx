"""The hospital of a request (admin consoles, 16 Nov 2026, DESIGN 5.2) and the accounts rule (D3), through the real Tumour Board routes
with a fake login system: a login of one hospital never reaches another hospital's Case Files; X-TB-Hospital counts only for a Vaidyx
admin; a suspended hospital's logins are refused; logins of another hospital are never placed, reset or changed. Synthetic data only."""
import copy, json, shutil

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tumour_board import accounts, config, hospitals, org, store
from tumour_board.tests.conftest import FIXTURES

TOKENS = {f"tok-{u}": u for u in ("anil", "bina", "admin", "nobody")}


class FakeAuth:
    is_configured = True

    def __init__(self):
        self.users = {"anil": {}, "bina": {}, "admin": {"is_admin": True}, "nobody": {}}

    def is_admin(self, u):
        return bool(self.users.get(u, {}).get("is_admin"))

    def get_username_for_token(self, token):
        return TOKENS.get(token)

    def get_privileges(self, u):
        return {"can_use_bash": False}

    def create_user(self, u, pw, is_admin=False):
        if u in self.users:
            return False
        self.users[u] = {"is_admin": is_admin}
        return True

    def reset_password(self, u, pw, must_change=False):
        return u in self.users


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
def lotus(data_root, monkeypatch):
    """Default hospital: coordinator anil, TB-001 and TB-002 (fixtures). Lotus: coordinator bina, its own TB-001 (another patient) and
    TB-LOTUS-1."""
    monkeypatch.setenv("TB_SCHEDULER", "0")
    hid = hospitals.create("Lotus Cancer Centre", by="admin")["id"]
    hospitals.assign("bina", hid, by="admin")
    o = copy.deepcopy(org.DEFAULT_ORG); o["admins"] = ["anil-root"]; o["users"] = {"anil": {"coordinator": True}, "anil-root": {}}
    org.save(o, by="test")
    for cid in ("TB-001", "TB-002"):
        shutil.copytree(FIXTURES / "cases" / cid, config.BASE_ROOT / "cases" / cid)
    with config.use_hospital(hid):
        o = copy.deepcopy(org.load()); o["users"] = {"bina": {"coordinator": True}}; o["hospital"]["name"] = "Lotus Cancer Centre"
        org.save(o, by="test")
        shutil.copytree(FIXTURES / "cases" / "TB-001", config.CASES_DIR / "TB-001")
        c = store.get_case("TB-001"); c["patient"]["name"] = "SYNTHETIC, Lotus Patient"; store.save_case(c)
        shutil.copytree(FIXTURES / "cases" / "TB-003", config.CASES_DIR / "TB-LOTUS-1")
        c = store.get_case("TB-LOTUS-1") or json.loads((config.CASES_DIR / "TB-LOTUS-1" / "case.json").read_text())
        c["case_id"] = "TB-LOTUS-1"; store.save_case(c)
    store._docs_cache.clear()
    return hid


@pytest.fixture
def tc(lotus):
    with TestClient(make_app(FakeAuth())) as c:
        yield c


def get(tc, user, path, **headers):
    tc.cookies.set("vaidyx_session", f"tok-{user}")
    return tc.get("/api/tb" + path, headers=headers)


def test_each_login_sees_its_own_hospital(tc, lotus):
    r = get(tc, "anil", "/cases")
    assert r.status_code == 200 and {c["case_id"] for c in r.json()["cases"]} == {"TB-001", "TB-002"}
    r = get(tc, "bina", "/cases")
    assert r.status_code == 200 and {c["case_id"] for c in r.json()["cases"]} == {"TB-001", "TB-LOTUS-1"}
    assert "Lotus Patient" in get(tc, "bina", "/cases/TB-001").text and "Lotus Patient" not in get(tc, "anil", "/cases/TB-001").text
    assert get(tc, "bina", "/cases/TB-002").status_code == 404      # the default hospital's Case File does not exist for Lotus
    assert get(tc, "anil", "/cases/TB-LOTUS-1").status_code == 404   # and the other way round
    assert get(tc, "bina", "/org").json()["hospital"]["name"] == "Lotus Cancer Centre"
    assert get(tc, "anil", "/org").json()["hospital"]["name"] == ""


def test_the_header_counts_only_for_a_vaidyx_admin(tc, lotus):
    r = get(tc, "anil", "/cases", **{"X-TB-Hospital": lotus})
    assert {c["case_id"] for c in r.json()["cases"]} == {"TB-001", "TB-002"}  # ignored
    assert get(tc, "anil", "/cases/TB-LOTUS-1", **{"X-TB-Hospital": lotus}).status_code == 404
    assert get(tc, "bina", "/org", **{"X-TB-Hospital": "default"}).json()["hospital"]["name"] == "Lotus Cancer Centre"
    assert get(tc, "admin", "/org").json()["hospital"]["name"] == ""
    assert get(tc, "admin", "/org", **{"X-TB-Hospital": lotus}).json()["hospital"]["name"] == "Lotus Cancer Centre"
    assert set(get(tc, "admin", "/org", **{"X-TB-Hospital": lotus}).json()["users"]) == {"bina"}
    r = get(tc, "admin", "/org", **{"X-TB-Hospital": "no-such"})  # unknown: refused, never a silent fall-back (Phase B)
    assert r.status_code == 404 and r.json()["detail"] == {"message": "That hospital does not exist (any more). Choose another in the Vaidyx console.",
                                                          "code": "hospital_unknown"}


def test_a_suspended_hospital_is_refused(tc, lotus):
    hospitals.set_status(lotus, "suspended", by="admin", reason="Contract paused")
    r = get(tc, "bina", "/cases")
    assert r.status_code == 403 and r.json()["detail"] == {"message": "Your hospital's access to Vaidyx is paused. Ask the Vaidyx admin.",
                                                          "code": "hospital_suspended"}
    assert get(tc, "bina", "/me").status_code == 403
    assert get(tc, "anil", "/cases").status_code == 200  # other hospitals carry on
    assert get(tc, "admin", "/org", **{"X-TB-Hospital": lotus}).status_code == 200  # the Vaidyx admin is exempt
    hospitals.set_status(lotus, "active", by="admin")
    assert get(tc, "bina", "/cases").status_code == 200


def test_an_unreadable_registry_refuses_never_guesses(tc, lotus):
    hospitals.registry_path().write_text("{not json")
    r = get(tc, "bina", "/cases")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "hospital_unavailable"


def test_no_login_means_the_default_hospital(tc, lotus):
    tc.cookies.clear()
    r = tc.get("/api/tb/org", headers={"X-TB-Hospital": lotus})
    assert r.status_code in (200, 401, 403) and "Lotus Cancer Centre" not in r.text


# ---- accounts (A5) ------------------------------------------------------------------------------------------------------------

def test_accounts_refuse_another_hospitals_login(lotus):
    mgr = FakeAuth()
    with config.use_hospital(lotus):
        for call in (lambda: accounts.ensure_account(mgr, "anil", None, "bina"),
                     lambda: accounts.place_doctor("bina", "radiology", "anil"),
                     lambda: accounts.reset_password(mgr, "bina", {"root_admin": True}, "anil"),
                     lambda: accounts.update_account(mgr, "bina", {"root_admin": True}, "anil", {"display_name": "X"})):
            with pytest.raises(accounts.AccountError) as e:
                call()
            assert e.value.status in (403, 404) and (e.value.status == 404 or str(e.value) == accounts.OTHER_HOSPITAL)
        with pytest.raises(accounts.AccountError) as e:
            accounts.ensure_account(mgr, "anil", None, "bina")
        assert e.value.status == 403 and str(e.value) == "This login belongs to another hospital."
        with pytest.raises(accounts.AccountError) as e:
            accounts.place_doctor("bina", "radiology", "anil")
        assert e.value.status == 403
        with pytest.raises(ValueError):  # the organisation file refuses it too (PUT /org)
            o = copy.deepcopy(org.load()); o["users"]["anil"] = {"departments": {"radiology": "member"}}; org.save(o, by="bina")
        # a new login made in Lotus is registered to Lotus at once and can be placed there
        made = accounts.ensure_account(mgr, "dr.new@lotus.in", "Passw0rd!x", "bina")
        assert made["created"] and hospitals.hospital_of("dr.new@lotus.in") == lotus
        assert accounts.place_doctor("bina", "radiology", "dr.new@lotus.in")["departments"] == {"radiology": "member"}
        assert accounts.ensure_account(mgr, "bina", None, "bina") == {"username": "bina", "created": False}
        assert accounts.reset_password(mgr, "admin2", {"root_admin": True}, "bina")["must_change_password"]
    # in the default hospital Lotus's logins are refused, its own work as before
    for call in (lambda: accounts.ensure_account(mgr, "bina", None, "anil-root"), lambda: accounts.place_doctor("anil-root", "radiology", "bina"),
                 lambda: accounts.update_account(mgr, "anil-root", {"root_admin": True}, "dr.new@lotus.in", {"display_name": "X"})):
        with pytest.raises(accounts.AccountError) as e:
            call()
        assert e.value.status == 403
    made = accounts.ensure_account(mgr, "dr.default@x.in", "Passw0rd!x", "anil-root")
    assert made["created"] and hospitals.registered("dr.default@x.in") is None  # default stays implicit
    assert accounts.place_doctor("anil-root", "radiology", "anil")["departments"] == {"radiology": "member"}


def test_create_account_in_a_new_hospital(lotus):
    mgr = FakeAuth()
    with config.use_hospital(lotus):
        out = accounts.create_account(mgr, "admin", "head@lotus.in", display_name="Dr Head", root_admin=True)
        assert out["created"] and out["root_admin"] and out["mailto"] and hospitals.hospital_of("head@lotus.in") == lotus
        assert "head@lotus.in" in org.load()["admins"]
        lines = (config.DATA_ROOT / "org_audit.jsonl").read_text().splitlines() + hospitals.audit_path().read_text().splitlines()
        assert lines and not any(k == "password" for x in lines for k in json.loads(x))  # never a password in an audit line
    assert "head@lotus.in" not in org.load()["users"]
