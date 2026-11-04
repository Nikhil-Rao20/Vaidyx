"""Tests for the deployment gate (deploy/h200/gate.py): secret, allow-list, path tricks, WebSocket origin."""
import importlib
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

GATE_DIR = Path(__file__).resolve().parents[1] / "h200"
SECRET = "s" * 40


@pytest.fixture(scope="module")
def gate(tmp_path_factory):
    f = tmp_path_factory.mktemp("gate") / "secret"
    f.write_text(SECRET + "\n")
    mp = pytest.MonkeyPatch()
    mp.setenv("VX_GATE_SECRET_FILE", str(f))
    mp.setenv("VX_UPSTREAM", "http://127.0.0.1:9")      # nothing listens: forwarded requests answer 502
    mp.setenv("VX_HIS_UPSTREAM", "http://127.0.0.1:9")
    sys.path.insert(0, str(GATE_DIR))
    sys.modules.pop("gate", None)
    mod = importlib.import_module("gate")
    yield mod
    sys.path.remove(str(GATE_DIR))
    mp.undo()


@pytest.fixture()
def client(gate):
    return TestClient(gate.app, raise_server_exceptions=False)


OK = {"x-vaidyx-gate": SECRET}


def test_no_or_wrong_secret_is_refused(client):
    assert client.get("/tb-nik").status_code == 403
    assert client.get("/tb-nik", headers={"x-vaidyx-gate": "wrong"}).status_code == 403
    assert client.get("/tb-nik", headers={"x-vaidyx-gate": SECRET[:-1]}).status_code == 403
    assert client.get("/_gate/health").status_code == 403


def test_secret_needed_even_for_health_and_root(client):
    assert client.get("/", follow_redirects=False).status_code == 403
    r = client.get("/", headers=OK, follow_redirects=False)
    assert r.status_code == 502  # the website's start page, forwarded to the (absent) upstream as /tb-nik


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/chat"), ("POST", "/api/chat"), ("GET", "/api/admin/users"), ("GET", "/api/tools"),
    ("POST", "/api/upload"), ("POST", "/settings"), ("GET", "/api/memory"), ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/setup"), ("GET", "/fhir/Patient"), ("POST", "/tb-nik"), ("DELETE", "/static/x.js"),
    ("GET", "/api/tb/../chat"), ("GET", "/api/tb/%2e%2e/chat"), ("GET", "/api/tb//x"), ("GET", "/api/tb/%2fx"),
    ("GET", "/api/tb\\..\\chat"), ("GET", "/api/tb/admin"), ("GET", "/api/tb/admin/x"),
])
def test_paths_outside_the_allow_list_are_refused(client, method, path):
    r = client.request(method, path, headers=OK)
    assert r.status_code in (403, 404), (method, path, r.status_code)


@pytest.mark.parametrize("method,path", [
    ("GET", "/"), ("GET", "/cases"), ("GET", "/cases/TB-002/records"), ("GET", "/sign-in"), ("GET", "/settings"), ("GET", "/static/tb-nik/assets/a.js"), ("GET", "/login"),
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/2fa/status"),
    ("POST", "/api/auth/2fa/setup"), ("GET", "/api/tb/cases"), ("POST", "/api/tb/cases/TB-001/ask"),
])
def test_allowed_paths_are_forwarded(client, method, path):
    r = client.request(method, path, headers=OK)
    assert r.status_code == 502, (method, path, r.status_code)  # forwarded to the (absent) upstream


def test_health_reports_app_down(client):
    r = client.get("/_gate/health", headers=OK)
    assert r.status_code == 503 and r.json()["app"] == "down"


def test_websocket_rules(gate):
    ok_headers = {"host": "vx.example", "origin": "https://vx.example", "x-vaidyx-gate": SECRET}
    assert gate.WS_PATHS.match("/api/tb/meetings/S20261102-6708/ws")
    assert gate.WS_PATHS.match("/api/tb/messages/ws")
    assert not gate.WS_PATHS.match("/api/tb/meetings/../ws")
    assert not gate.WS_PATHS.match("/api/chat/ws")
    assert gate.origin_matches_host(ok_headers)
    assert not gate.origin_matches_host({**ok_headers, "origin": "https://evil.example"})
    assert not gate.origin_matches_host({"host": "vx.example"})  # a browser always sends Origin
    assert gate.has_secret(ok_headers) and not gate.has_secret({"x-vaidyx-gate": "x"})


def test_websocket_without_secret_or_origin_is_closed(client):
    from starlette.websockets import WebSocketDisconnect
    for headers in ({"origin": "http://testserver"}, {**OK, "origin": "https://evil.example"}, OK):
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect("/api/tb/messages/ws", headers=headers) as ws:
                ws.receive_text()
        assert e.value.code == 1008


def test_forwarded_for_is_always_set(gate):
    assert gate.forwarded_for({}, "127.0.0.1") == "127.0.0.1"
    assert gate.forwarded_for({"x-forwarded-for": "1.2.3.4"}, "127.0.0.1") == "1.2.3.4, 127.0.0.1"


def test_secret_header_is_never_forwarded(gate):
    assert "x-vaidyx-gate" in gate.HOP_REQ


def test_short_secret_refuses_to_start(tmp_path, monkeypatch):
    f = tmp_path / "s"
    f.write_text("short")
    monkeypatch.setenv("VX_GATE_SECRET_FILE", str(f))
    sys.path.insert(0, str(GATE_DIR))
    sys.modules.pop("gate", None)
    try:
        with pytest.raises(SystemExit):
            importlib.import_module("gate")
    finally:
        sys.path.remove(str(GATE_DIR))
        sys.modules.pop("gate", None)


@pytest.mark.parametrize("method,path", [
    ("GET", "/his/patients"), ("GET", "/desk"), ("POST", "/his/login"), ("GET", "/view/reports/x"), ("GET", "/documents/x"),
])
def test_demo_hospital_is_not_public(client, method, path):
    r = client.request(method, path, headers=OK)
    assert r.status_code == 404, (method, path, r.status_code)


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/auth/log%09in"), ("GET", "/_ga%09te/health"), ("GET", "/tb-%0Anik"), ("GET", "/api/tb/%2561dmin/x"),
    ("GET", "/api/tb/cases%7f"), ("GET", "/static/tb-nik/a%00.js"),
])
def test_control_characters_and_double_encoding_are_refused(client, method, path):
    r = client.request(method, path, headers=OK)
    assert r.status_code == 404, (method, path, r.status_code)


def test_same_path_rules(gate):
    assert gate.same_path({"path": "/api/tb/cases"}, "/api/tb/cases")
    assert not gate.same_path({"path": "/api/auth/log\tin"}, "/api/auth/login")
    assert not gate.same_path({"path": "/api/tb/%61dmin"}, "/api/tb/%61dmin")


def test_website_at_the_root(gate):
    assert gate.site_upstream("/") == "/tb-nik"
    assert gate.site_upstream("/cases/TB-002") == "/tb-nik/cases/TB-002"
    assert gate.site_upstream("/meetings/S1/room") == "/tb-nik/meetings/S1/room"
    assert gate.site_upstream("/api/tb/cases") is None and gate.site_upstream("/static/x.js") is None
    assert gate.site_upstream("/casesX") is None and gate.site_upstream("/openapi.json") is None


@pytest.mark.parametrize("old,new", [("/tb-nik", "/"), ("/tb-nik/", "/"), ("/tb-nik/cases/TB-002", "/cases/TB-002"),
                                     ("/tb-nik/sign-in?next=x", "/sign-in?next=x")])
def test_old_tb_nik_links_redirect_to_the_plain_address(client, old, new):
    r = client.get(old, headers=OK, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == new, (old, r.status_code, r.headers.get("location"))


def test_enquiry_api_keeps_its_path(client):
    r = client.post("/tb-nik/api/enquiry", headers=OK, json={})
    assert r.status_code == 502  # forwarded unchanged (not redirected)
