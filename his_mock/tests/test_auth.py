"""Logins and security of the demo HIMS (his_mock/auth.py): the 9 accounts, the login file, bcrypt, the session cookie,
the lock-out after 5 failed sign-ins, CSRF on every form, the role matrix, the audit trail, /view/reports with a cookie
or the bearer token, the reset CLI. SYNTHETIC accounts only (a temporary build)."""
import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import auth, generator, paths
from his_mock.tests import helpers
from his_mock.tests.helpers import post


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_auth")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def app(data_dir):
    return app_module.create_app(data_dir)


@pytest.fixture(scope="module")
def logins(data_dir, app):
    return helpers.logins(data_dir)


def audit(data_dir):
    p = Path(data_dir) / auth.AUDIT_NAME
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# -------------------------------------------------------------------- accounts and files
def test_nine_accounts_with_bcrypt_hashes_and_a_private_login_file(data_dir, app, logins):
    acc = json.loads((Path(data_dir) / auth.ACCOUNTS_NAME).read_text())
    emails = sorted(a["email"] for a in acc["accounts"])
    assert emails == sorted(s["email"] for s in auth.ACCOUNT_SPECS) and len(emails) == 9
    assert all(a["email"].endswith("@vaidyx-demo.invalid") for a in acc["accounts"])
    assert all(a["password_hash"].startswith("$2") for a in acc["accounts"])
    assert set(logins) == {"reception", "opd.doctor", "ward.doctor", "lab.tech", "lab.doctor", "rad.tech", "radiologist",
                           "pathologist", "admin"}
    assert all(len(pw) == auth.PASSWORD_LENGTH for _, pw in logins.values())
    text = (Path(data_dir) / auth.ACCOUNTS_NAME).read_text()
    assert not any(pw in text for _, pw in logins.values())            # never in clear next to the hashes
    for name in (auth.LOGINS_NAME, auth.ACCOUNTS_NAME):
        assert stat.S_IMODE((Path(data_dir) / name).stat().st_mode) == 0o600, name
    # the signing accounts map to real consultants of the store
    by = {a["email"]: a for a in acc["accounts"]}
    s = app.state.hospital.store
    for role, dept in (("opd.doctor", "Breast Surgery"), ("ward.doctor", "Breast Surgery"), ("lab.doctor", "Biochemistry"),
                       ("radiologist", "Radiology"), ("pathologist", "Pathology")):
        a = by[logins[role][0]]
        p = s.practitioners[a["practitioner_id"]]
        assert p["department"] == dept and p["role"] == "consultant" and p["reg_no"].startswith("VXREG-")
    for role in ("reception", "lab.tech", "rad.tech", "admin"):
        assert by[logins[role][0]]["practitioner_id"] is None
    assert by[logins["opd.doctor"][0]]["roles"] == ["opd.doctor", "ward.doctor"]     # the OPD doctor does the ward work
    assert by[logins["ward.doctor"][0]]["practitioner_id"] == by[logins["opd.doctor"][0]]["practitioner_id"]


def test_ensure_is_idempotent_and_keeps_passwords(data_dir, app, logins):
    before = (Path(data_dir) / auth.LOGINS_NAME).read_text()
    created = app.state.hospital.accounts.ensure(app.state.hospital.store)
    assert created == [] and (Path(data_dir) / auth.LOGINS_NAME).read_text() == before
    again = auth.Accounts(data_dir)
    assert again.ensure(app.state.hospital.store) == []
    assert helpers.login(app, "reception").get("/his").status_code == 200


# -------------------------------------------------------------------- sign in, sign out, lock-out
def test_login_page_and_cookie_flags(app, logins):
    c = TestClient(app)
    r = c.get("/his/login")
    assert r.status_code == 200 and 'name="password"' in r.text and "SYNTHETIC DATA" in r.text
    email, pw = logins["reception"]
    r = c.post("/his/login", data={"email": email, "password": pw, "next": "/his/opd"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/his/opd?flash=")
    cookie = r.headers["set-cookie"].lower()
    assert "vxhis_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert f"max-age={auth.SESSION_HOURS * 3600}" in cookie
    html = c.get("/his").text
    assert "Signed in: <b>Registration desk</b> (reception)" in html


def test_next_only_goes_to_a_local_path(app, logins):
    assert auth.safe_next("//evil.example/x") == "/his"
    assert auth.safe_next("http://evil.example") == "/his"
    assert auth.safe_next("/his/login") == "/his"
    assert auth.safe_next("/his/lab?tab=entered") == "/his/lab?tab=entered"
    c = TestClient(app)
    r = c.get("/his/lab?tab=entered", follow_redirects=False)
    assert r.status_code == 303 and "next=%2Fhis%2Flab%3Ftab%3Dentered" in r.headers["location"]


def test_wrong_password_counts_and_five_failures_lock_for_15_minutes(app, logins, data_dir):
    email, pw = logins["rad.tech"]
    c = TestClient(app)
    for left in (4, 3, 2, 1):
        r = c.post("/his/login", data={"email": email, "password": "wrong"})
        assert r.status_code == 401 and f"{left} attempt(s) left" in r.text, r.text[:300]
    r = c.post("/his/login", data={"email": email, "password": "wrong"})
    assert r.status_code == 401 and "locked for 15 minutes" in r.text
    r = c.post("/his/login", data={"email": email, "password": pw})
    assert r.status_code == 401 and "locked" in r.text and "minute(s)" in r.text
    lines = [x for x in audit(data_dir) if x["action"] == "login" and x["user"] == email]
    assert lines and all(x["outcome"] == "refused" for x in lines[-6:])
    assert not any(pw in json.dumps(x) for x in lines)
    # the lock ends: the account signs in again
    app.state.hospital.accounts.failures.pop(email, None)
    r = c.post("/his/login", data={"email": email, "password": pw}, follow_redirects=False)
    assert r.status_code == 303


def test_many_failures_from_one_address_pause_sign_ins(data_dir, logins):
    """Password spraying across accounts: after 30 failures from one address its sign-ins pause (others are not hit)."""
    acc = auth.Accounts(data_dir)          # a second instance: its address counters are its own
    emails = [e for e, _ in logins.values()]
    for i in range(auth.MAX_FAILURES_PER_ADDRESS):
        with pytest.raises(auth.LoginError):
            acc.login(f"nobody{i}@vaidyx-demo.invalid", "wrong", address="10.9.9.9")
    email, pw = logins["pathologist"]
    with pytest.raises(auth.LoginError) as e:
        acc.login(email, pw, address="10.9.9.9")
    assert "Too many failed sign-ins from this computer" in str(e.value)
    assert acc.login(email, pw, address="10.9.9.8")["email"] == email
    assert email in emails


def test_unknown_email_gets_the_same_message(app):
    r = TestClient(app).post("/his/login", data={"email": "nobody@vaidyx-demo.invalid", "password": "x"})
    assert r.status_code == 401 and "Wrong email or password" in r.text


def test_logout_ends_the_session_and_sessions_survive_a_restart(app, data_dir, logins):
    c = helpers.login(app, "lab.tech")
    sid = c.cookies.get(auth.COOKIE)
    assert stat.S_IMODE((Path(data_dir) / auth.SESSIONS_NAME).stat().st_mode) == 0o600
    saved = json.loads((Path(data_dir) / auth.SESSIONS_NAME).read_text())
    assert sid in saved["sessions"] and saved["sessions"][sid]["email"] == logins["lab.tech"][0]
    fresh = auth.Accounts(data_dir)          # a restart loads sessions.json
    assert fresh.session(sid)["email"] == logins["lab.tech"][0]
    r = c.get("/his/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/his/login?flash=")
    assert c.get("/his", follow_redirects=False).status_code == 303
    assert app.state.hospital.accounts.session(sid) is None
    assert audit(data_dir)[-1]["action"] == "logout"


def test_expired_session_is_dropped(app, data_dir):
    c = helpers.login(app, "admin")
    sid = c.cookies.get(auth.COOKIE)
    app.state.hospital.accounts.sessions[sid]["expires"] = "2020-01-01T00:00:00+05:30"
    assert c.get("/his/admin", follow_redirects=False).status_code == 303


# -------------------------------------------------------------------- CSRF
def test_forms_carry_the_session_token_and_posts_without_it_are_refused(app):
    c = helpers.login(app, "reception")
    html = c.get("/his").text
    token = helpers.csrf(c)
    assert f'<input type=hidden name="csrf" value="{token}">' in html
    r = c.post("/his/registrations", data={"name": "No Token (SYNTHETIC)", "sex": "F", "age": "30"}, follow_redirects=False)
    assert r.status_code == 403 and "form token" in r.text and "SYNTHETIC DATA" in r.text
    r = c.post("/his/registrations", data={"csrf": "stale", "name": "No Token (SYNTHETIC)", "sex": "F", "age": "30"},
               follow_redirects=False)
    assert r.status_code == 403
    assert not any(p["name"] == "No Token (SYNTHETIC)" for p in app.state.hospital.store.patients.values())
    other = helpers.login(app, "reception")       # another session's token does not fit
    r = c.post("/his/registrations", data={"csrf": helpers.csrf(other), "name": "No Token (SYNTHETIC)", "sex": "F", "age": "30"},
               follow_redirects=False)
    assert r.status_code == 403


# -------------------------------------------------------------------- roles
def test_permission_matrix():
    assert auth.allowed(["reception"], "register") and not auth.allowed(["opd.doctor"], "register")
    assert auth.allowed(["opd.doctor", "ward.doctor"], "note") and not auth.allowed(["reception"], "note")
    assert auth.allowed(["lab.doctor"], "lab.sign") and not auth.allowed(["lab.tech"], "lab.sign")
    assert auth.allowed(["radiologist"], "rad.sign") and not auth.allowed(["rad.tech"], "rad.sign")
    assert auth.allowed(["pathologist"], "path.sign") and not auth.allowed(["lab.tech"], "path.sign")
    assert auth.allowed(["admin"], "admin") and not auth.allowed(["opd.doctor"], "admin")
    assert auth.allowed(["reception"], "look-around")   # unlisted actions are open to every signed-in user
    with pytest.raises(auth.Forbidden) as e:
        auth.require({"roles": ["reception"]}, "lab.sign")
    assert str(e.value) == "Your role cannot do this: only the Laboratory consultant can verify and sign a laboratory report."
    assert auth.who_can("visit.open") == "the Registration desk, OPD consultant or Ward doctor"


@pytest.fixture(scope="module")
def open_orders(app):
    """One open laboratory, imaging and histopathology order on P01's OP visit (the fixtures have few open orders)."""
    h = app.state.hospital
    with h.lock:
        s = h.store
        enc = s.encounters["op-26-118701"]
        out = {key: s.place_order(enc["patient_id"], enc["id"], test, enc["department"])["id"]
               for key, test in (("lab", "cbc"), ("rad", "mammogram"), ("path", "hpe_biopsy"))}
        h.save()
    return out


@pytest.mark.parametrize("role,url,data", [
    ("reception", "/his/lab/orders/{lab}/verify", {}),
    ("lab.tech", "/his/lab/orders/{lab}/verify", {}),
    ("rad.tech", "/his/radiology/orders/{rad}/sign", {"v_findings": "x", "v_impression": "y"}),
    ("reception", "/his/radiology/orders/{rad}/schedule", {"date": "2026-10-20"}),
    ("lab.tech", "/his/pathology/orders/{path}/report", {"v_diagnosis": "x"}),
    ("opd.doctor", "/his/registrations", {"name": "X (SYNTHETIC)", "sex": "F", "age": "1"}),
    ("reception", "/his/encounters/op-26-118701/notes", {"v_presenting_complaint": "x"}),
    ("reception", "/his/encounters/op-26-118701/orders", {"tests": ["cbc"]}),
    ("radiologist", "/his/admin/practitioners", {"name": "Dr X"}),
    ("pathologist", "/his/lab/orders/{lab}/collect", {}),
])
def test_role_refusals_are_plain_403_pages(app, open_orders, role, url, data):
    s = app.state.hospital.store
    ids = open_orders
    c = helpers.login(app, role)
    n = len(s.events)
    r = post(c, url.format(**ids), data)
    assert r.status_code == 403, (role, url, r.status_code)
    assert "Your role cannot do this" in r.text and "Traceback" not in r.text and "SYNTHETIC DATA" in r.text
    assert len(s.events) == n


def test_admin_module_is_admin_only(app):
    for role in ("reception", "opd.doctor", "lab.doctor", "radiologist", "pathologist"):
        r = helpers.login(app, role).get("/his/admin")
        assert r.status_code == 403 and "Your role cannot do this" in r.text, role
    assert helpers.login(app, "admin").get("/his/admin").status_code == 200


# -------------------------------------------------------------------- what needs a login
def test_protection_map():
    assert auth.protection("/his") == "screen" and auth.protection("/his/patients/x") == "screen"
    assert auth.protection("/his/login") is None and auth.protection("/his/logout") is None
    assert auth.protection("/his/api/search") is None and auth.protection("/desk/api/RAD/pending") is None
    assert auth.protection("/desk") == "screen" and auth.protection("/desk/RAD") == "screen"
    assert auth.protection("/view/reports/x/1") == "view"
    assert auth.protection("/api/tb/pacs/ohif/viewer") == "pacs"
    for open_path in ("/", "/health", "/fhir/metadata", "/fhir/Patient", "/documents/x.pdf"):
        assert auth.protection(open_path) is None, open_path


def test_view_reports_takes_the_cookie_or_the_bearer_token(app, data_dir):
    h = app.state.hospital
    r = next(iter(h.store.reports.values()))
    v = h.store.current_version(r)
    (Path(data_dir) / paths.DOCUMENTS_NAME / "x.pdf").write_bytes(b"%PDF-1.4 x")
    v["document"] = {"path": "documents/x.pdf", "sha256": "0" * 64}
    try:
        anon = TestClient(app)
        assert anon.get(f"/view/reports/{r['id']}/{v['version']}", follow_redirects=False).status_code == 303
        token = (Path(data_dir) / paths.TOKEN_NAME).read_text().strip()
        ok = anon.get(f"/view/reports/{r['id']}/{v['version']}", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200 and "inline" in ok.headers["content-disposition"]
        assert anon.get(f"/view/reports/{r['id']}/{v['version']}", headers={"Authorization": "Bearer wrong"},
                        follow_redirects=False).status_code == 303
        assert helpers.login(app, "lab.tech").get(f"/view/reports/{r['id']}/{v['version']}").status_code == 200
        # the Vaidyx path keeps its token rule
        assert anon.get("/documents/x.pdf").status_code == 401
        assert anon.get("/documents/x.pdf", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    finally:
        v["document"] = {"path": None, "sha256": None}


# -------------------------------------------------------------------- reset
def test_reset_cli_recreates_every_password_and_ends_sessions(tmp_path):
    generator.build(tmp_path, documents=False, hl7=False, dicom=False)
    app = app_module.create_app(tmp_path)
    old = helpers.logins(tmp_path)
    c = helpers.login(app, "admin")
    assert auth.main(["--data", str(tmp_path), "--reset"]) == 0
    new = helpers.logins(tmp_path)
    assert set(new) == set(old) and all(new[r][1] != old[r][1] for r in old)
    assert stat.S_IMODE((tmp_path / auth.LOGINS_NAME).stat().st_mode) == 0o600
    app.state.hospital.accounts = auth.Accounts(tmp_path)   # as after a restart
    assert c.get("/his/admin", follow_redirects=False).status_code == 303   # the old session is gone
    email, pw = old["admin"]
    assert TestClient(app).post("/his/login", data={"email": email, "password": pw}).status_code == 401
    assert helpers.login(app, "admin").get("/his/admin").status_code == 200
    assert auth.main(["--data", str(tmp_path)]) == 0   # ensure only: nothing changes
    assert helpers.logins(tmp_path) == new


def test_admin_reset_shows_the_password_once_and_never_logs_it(app, data_dir, logins):
    c = helpers.login(app, "admin")
    email = logins["rad.tech"][0]
    r = post(c, f"/his/admin/accounts/{email}/reset")
    assert r.status_code == 200 and f"New password for {email}: " in r.text
    pw = r.text.split(f"New password for {email}: ", 1)[1].split(" ", 1)[0]
    assert len(pw) == auth.PASSWORD_LENGTH
    assert pw not in (Path(data_dir) / auth.AUDIT_NAME).read_text()
    assert pw not in (Path(data_dir) / auth.ACCOUNTS_NAME).read_text()
    assert audit(data_dir)[-1]["action"] == "admin.reset_password" and audit(data_dir)[-1]["detail"] == email
    r = TestClient(app).post("/his/login", data={"email": email, "password": pw}, follow_redirects=False)
    assert r.status_code == 303
    assert post(c, "/his/admin/accounts/nobody@vaidyx-demo.invalid/reset").status_code == 303
    # the login file no longer holds the stopped password, never the new one
    line = next(x for x in (Path(data_dir) / auth.LOGINS_NAME).read_text().splitlines() if x.startswith(email + "\t"))
    assert "reset by the admin" in line and pw not in line and logins["rad.tech"][1] not in line
    assert stat.S_IMODE((Path(data_dir) / auth.LOGINS_NAME).stat().st_mode) == 0o600
