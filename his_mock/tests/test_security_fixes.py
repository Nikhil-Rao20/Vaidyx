"""The HIMS fixes of the security review (docs/ui/build/SECURITY_REVIEW.md, 18 Oct 2026): #3 the JSON APIs for staff sessions go
through the screens' role checks and a desk signature carries the signed-in consultant; #12 a module form acts only on its own
orders and signs only for its department; #13 a separate write token, the FHIR read token changes nothing; #20 sign-out by POST, a
sign-in ends the old session, a CSP on the screens, no proxy headers. SYNTHETIC data only, built into a temporary directory."""
import base64, hashlib, re, stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import auth, desk, generator, paths, ui
from his_mock.tests import helpers
from his_mock.tests.helpers import post

DEAD_ORTHANC = "http://127.0.0.1:9"
P01 = "vxh-26-004201"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def no_pacs():
    old = desk.ORTHANC_URL
    desk.ORTHANC_URL = DEAD_ORTHANC
    yield
    desk.ORTHANC_URL = old


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_security")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def app(data_dir):
    return app_module.create_app(data_dir, open_api=False)  # the live HIMS: the JSON APIs closed


def tokens(data_dir):
    return (Path(data_dir) / paths.TOKEN_NAME).read_text().strip(), (Path(data_dir) / paths.WRITE_TOKEN_NAME).read_text().strip()


def bearer(t):
    return {"Authorization": "Bearer " + t}


def order_of(app, module, status=None):
    from his_mock import common
    s = app.state.hospital.store
    return next(o for o in s.orders.values() if common.module_of(o) == module and (status is None or o["status"] == status))


# ---- #13: the write token -----------------------------------------------------------------------------------------------------------

def test_13_the_build_writes_a_private_write_token_distinct_from_the_read_token(data_dir):
    read, write = tokens(data_dir)
    assert read and write and read != write
    assert stat.S_IMODE((Path(data_dir) / paths.WRITE_TOKEN_NAME).stat().st_mode) == 0o600


def test_13_the_read_token_reads_and_never_writes(app, data_dir):
    read, write = tokens(data_dir)
    c = TestClient(app)
    assert c.get("/his/api/search", params={"q": "VXH"}, headers=bearer(read)).status_code == 200
    r = c.post("/his/api/registrations", json={"name": "Never Registered (SYNTHETIC)"}, headers=bearer(read))
    assert r.status_code == 403 and "write token" in r.json()["detail"]
    o = order_of(app, "radiology")
    r = c.post(f"/desk/api/RAD/orders/{o['id']}/sign", json={"signer": "prac-vxreg-20201"}, headers=bearer(read))
    assert r.status_code == 403
    assert c.get("/his/api/search", params={"q": "VXH"}, headers=bearer(write)).status_code == 200  # the write token also reads
    assert c.get("/fhir/Patient", headers=bearer(write)).status_code == 401  # FHIR keeps its own read token
    assert c.post("/desk/api/RAD/orders/none/sign", json={}, headers=bearer(write)).status_code == 404  # the write token gets through to the route


def test_13_a_hospital_without_a_write_token_makes_one(tmp_path):
    d = tmp_path / "his"
    generator.build(d, documents=False, hl7=False, dicom=False)
    (d / paths.WRITE_TOKEN_NAME).unlink()
    h = app_module.Hospital(d)
    assert h.write_token and (d / paths.WRITE_TOKEN_NAME).read_text().strip() == h.write_token
    assert stat.S_IMODE((d / paths.WRITE_TOKEN_NAME).stat().st_mode) == 0o600


# ---- #3: staff sessions on the JSON APIs ----------------------------------------------------------------------------------------------

def test_3_a_session_writes_only_what_its_role_may_do_on_the_screens(app):
    tech = helpers.login(app, "lab.tech")
    r = tech.post("/his/api/registrations", json={"name": "Never Registered (SYNTHETIC)"})
    assert r.status_code == 403 and auth.REFUSED in r.json()["detail"]
    o = order_of(app, "radiology")
    r = tech.post(f"/desk/api/RAD/orders/{o['id']}/sign", json={"signer": "prac-vxreg-20201", "values": {"impression": "x"}})
    assert r.status_code == 403 and auth.REFUSED in r.json()["detail"]  # a laboratory technician never signs a radiology report
    rad_tech = helpers.login(app, "rad.tech")
    assert rad_tech.post(f"/desk/api/RAD/orders/{o['id']}/sign", json={"signer": "prac-vxreg-20201"}).status_code == 403
    assert tech.get("/his/api/search", params={"q": "VXH"}).status_code == 200  # reading is open to every signed-in user, as the screens


def test_3_a_desk_signature_by_a_session_carries_the_signed_in_consultant(app):
    s = app.state.hospital.store
    with app.state.hospital.lock:
        enc = next(e for e in s.encounters.values() if e["patient_id"] == P01)
        o = s.place_order(P01, enc["id"], "mammogram", enc["department"])
        app.state.hospital.save()
    rad = helpers.login(app, "radiologist")
    me = s.practitioner(helpers.session(rad)["practitioner_id"])
    other = next(p for p in s.practitioners.values() if p["department"] == "Radiology" and p["role"] == "consultant" and p["id"] != me["id"]) \
        if sum(1 for p in s.practitioners.values() if p["department"] == "Radiology" and p["role"] == "consultant") > 1 else None
    body = {"values": {"impression": "Synthetic impression"}, "signer": other["id"] if other else "prac-not-real"}
    r = rad.post(f"/desk/api/RAD/orders/{o['id']}/sign", json=body)
    assert r.status_code == 200, r.text
    sig = s.signatures[r.json()["signature_id"]]
    assert sig["signer_id"] == me["id"]  # never the signer named in the body


# ---- #12: module forms act on their own orders and sign for their department ------------------------------------------------------------

def test_12_a_module_form_never_acts_on_another_modules_order(app):
    lab = helpers.login(app, "lab.doctor")
    rad_order = order_of(app, "radiology")
    for path in (f"/his/lab/orders/{rad_order['id']}/collect", f"/his/lab/orders/{rad_order['id']}/result", f"/his/lab/orders/{rad_order['id']}/verify",
                 f"/his/lab/orders/{rad_order['id']}/cancel"):
        r = post(lab, path, {"reason": "x"})
        assert r.status_code == 404, (path, r.status_code)
    path_c = helpers.login(app, "pathologist")
    lab_order = order_of(app, "lab")
    for path in (f"/his/pathology/orders/{lab_order['id']}/receive", f"/his/pathology/orders/{lab_order['id']}/report", f"/his/pathology/orders/{lab_order['id']}/cancel"):
        assert post(path_c, path, {"reason": "x"}).status_code == 404, path
    rad = helpers.login(app, "radiologist")
    path_order = order_of(app, "pathology")
    for path in (f"/his/radiology/orders/{path_order['id']}/schedule", f"/his/radiology/orders/{path_order['id']}/sign", f"/his/radiology/orders/{path_order['id']}/cancel"):
        assert post(rad, path, {"reason": "x"}).status_code == 404, path
    opd = helpers.login(app, "opd.doctor")
    assert post(opd, f"/his/opd/orders/{rad_order['id']}/report", {}).status_code == 404


def test_12_signing_needs_a_consultant_of_the_orders_department(app):
    from his_mock import common
    s = app.state.hospital.store
    o = order_of(app, "radiology")

    class Req:
        class state:
            session = None
    req = Req()
    path_doc = next(p for p in s.practitioners.values() if p["department"] == "Pathology" and p["role"] == "consultant")
    req.state.session = {"practitioner_id": path_doc["id"], "roles": ["radiologist"]}
    with pytest.raises(auth.Forbidden) as e:
        common.module_signer(req, s, "radiology", o)
    assert "signs for Pathology" in str(e.value)
    rad_doc = next(p for p in s.practitioners.values() if p["department"] == "Radiology" and p["role"] == "consultant")
    req.state.session = {"practitioner_id": rad_doc["id"], "roles": ["radiologist"]}
    assert common.module_signer(req, s, "radiology", o)["id"] == rad_doc["id"]
    bio = next(p for p in s.practitioners.values() if p["department"] == "Biochemistry" and p["role"] == "consultant")
    req.state.session = {"practitioner_id": bio["id"], "roles": ["lab.doctor"]}
    lab_order = order_of(app, "lab")
    assert common.module_signer(req, s, "lab", lab_order)["id"] == bio["id"]  # the laboratory consultant signs for the laboratory
    with pytest.raises(auth.Forbidden):
        common.module_signer(req, s, "pathology", order_of(app, "pathology"))


# ---- #20: sign-in and sign-out, the CSP, the client address ---------------------------------------------------------------------------

def test_20_sign_out_is_a_post_and_a_sign_in_drops_the_old_session(app):
    c = helpers.login(app, "reception")
    old = c.cookies.get(auth.COOKIE)
    accounts = app.state.hospital.accounts
    page = c.get("/his/logout")
    assert page.status_code == 200 and accounts.session(old) is not None  # a link alone signs nobody out
    email, password = helpers.logins(app.state.hospital.files["data_dir"])["reception"]
    r = c.post("/his/login", data={"email": email, "password": password, "next": "/his"}, follow_redirects=False)
    assert r.status_code == 303 and accounts.session(old) is None and c.cookies.get(auth.COOKIE) != old
    assert c.post("/his/logout", data={}, follow_redirects=False).status_code == 303 and accounts.session(c.cookies.get(auth.COOKIE)) is not None
    assert post(c, "/his/logout").status_code == 303
    assert accounts.session(c.cookies.get(auth.COOKIE)) is None


def test_20_screens_carry_a_csp_that_admits_only_their_own_inline_blocks(app):
    c = helpers.login(app, "reception")
    r = c.get("/his")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'self'" in csp and "img-src 'self' data:" in csp and "'unsafe-inline'" not in csp
    for block, tag in ((ui.SCRIPT, "script"), (ui.CSS, "style")):
        h = "'sha256-" + base64.b64encode(hashlib.sha256(block.encode()).digest()).decode() + "'"
        assert h in csp and f"<{tag}>{block}</{tag}>" in r.text
    assert len(re.findall(r"<script>", r.text)) == 1 and "javascript:" not in r.text and " style=" not in r.text
    assert "content-security-policy" in TestClient(app).get("/his/login").headers
    assert "content-security-policy" in c.get("/his/patients/no-such-patient").headers


def test_20_x_forwarded_for_never_changes_the_address_that_is_counted(app):
    accounts = app.state.hospital.accounts
    accounts.address_failures.clear()
    c = TestClient(app)
    for i in range(3):
        c.post("/his/login", data={"email": f"nobody{i}@vaidyx-demo.invalid", "password": "x"}, headers={"X-Forwarded-For": f"10.0.0.{i}"})
    assert set(accounts.address_failures) == {"testclient"}  # the peer, never the header
    serve = (REPO / "his_mock" / "serve.sh").read_text()
    assert "--no-proxy-headers" in serve  # uvicorn would otherwise rewrite the peer from the header
    accounts.address_failures.clear()
