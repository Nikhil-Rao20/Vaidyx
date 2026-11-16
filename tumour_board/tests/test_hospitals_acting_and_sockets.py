"""Admin consoles Phase B, review additions (16 Nov 2026): the account lists of /org and /org/accounts show only the current hospital's
logins (Vaidyx admins only to a Vaidyx admin); the acting-hospital cookie of POST /platform/acting for what the browser loads without
fetch (header wins, Vaidyx admin only, unknown hospital refused); and the strict-mode gap: a login of a hospital other than "default" is
served its own hospital on the HTTP routes and on the meeting and messages sockets (the test thread sits in "default", so a route or
socket that never set the hospital would answer from the wrong folder). Synthetic data only."""
import copy, shutil

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tumour_board import board, config, hospitals, live, org, platform_admin, store
from tumour_board.api import messages_ws
from tumour_board.tests.conftest import FIXTURES
from tumour_board.tests.test_platform_api import FakeAuth, make_app, call

ORIGIN = {"Origin": "http://testserver"}
LOTUS_PATIENT = "SYNTHETIC, Lotus Onlypatient"


@pytest.fixture
def world(data_root, monkeypatch):
    """Default: root (hospital admin), doc (doctor), mdt (coordinator), TB-001, a meeting "Default weekly board". Lotus: bina
    (coordinator), lotdoc (doctor), lroot (hospital admin), its own TB-001 (another patient), a meeting "Lotus weekly board"."""
    monkeypatch.setenv("TB_SCHEDULER", "0")
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["admins"] = ["root"]
    o["users"] = {"root": {}, "doc": {"departments": {"radiology": "member"}}, "mdt": {"coordinator": True}}
    org.save(o, by="test")
    shutil.copytree(FIXTURES / "cases" / "TB-001", config.CASES_DIR / "TB-001")
    dmid = board.new_session("2099-12-30", "mdt", title="Default weekly board")["id"]
    hid = hospitals.create("Lotus Cancer Centre", by="vx")["id"]
    auth = FakeAuth()
    for u in ("bina", "lotdoc", "lroot"):
        auth.users[u] = {}
        hospitals.assign(u, hid, by="vx")
    with config.use_hospital(hid):
        o = copy.deepcopy(org.load())
        o["admins"] = ["lroot"]
        o["users"] = {"lroot": {}, "bina": {"coordinator": True}, "lotdoc": {"departments": {"radiology": "member"}}}
        org.save(o, by="test")
        shutil.copytree(FIXTURES / "cases" / "TB-001", config.CASES_DIR / "TB-001")
        c = store.get_case("TB-001"); c["patient"]["name"] = LOTUS_PATIENT; store.save_case(c)
        lmid = board.new_session("2099-12-30", "bina", title="Lotus weekly board")["id"]
    store._docs_cache.clear()
    platform_admin._ACTING.clear()
    live.messages_hub.clear()
    messages_ws.clear()
    with TestClient(make_app(auth)) as tc:
        yield tc, auth, hid, dmid, lmid
    live.messages_hub.clear()
    messages_ws.clear()


# ---- 1. account lists of one hospital ---------------------------------------------------------------------------------------------

def test_account_lists_show_only_this_hospitals_logins(world):
    tc, auth, hid, _, _ = world
    for path, key in (("/org", "vaidyx_users"), ("/org/accounts", "vaidyx_users")):
        names = {x["username"] for x in call(tc, "root", "GET", path).json()[key]}
        assert {"root", "doc", "mdt"} <= names and not names & {"bina", "lotdoc", "lroot", "vx"}, (path, names)
        names = {x["username"] for x in call(tc, "lroot", "GET", path).json()[key]}
        assert names == {"bina", "lotdoc", "lroot"}, (path, names)
        names = {x["username"] for x in call(tc, "vx", "GET", path).json()[key]}
        assert "vx" in names and "root" in names and "bina" not in names  # the Vaidyx admin sees the Vaidyx admins
        names = {x["username"] for x in call(tc, "vx", "GET", path, **{"X-TB-Hospital": hid}).json()[key]}
        assert {"bina", "lotdoc", "lroot", "vx"} == names


# ---- 2. the acting-hospital cookie ------------------------------------------------------------------------------------------------

def test_acting_cookie(world):
    tc, _, hid, _, _ = world
    assert call(tc, "root", "POST", "/platform/acting", {"hospital": hid}).status_code == 403
    r = call(tc, "vx", "POST", "/platform/acting", {"hospital": "gone-hospital"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "hospital_unknown"
    r = call(tc, "vx", "POST", "/platform/acting", {"hospital": hid})
    assert r.status_code == 200 and r.json()["acting_hospital"]["name"] == "Lotus Cancer Centre"
    sc = r.headers["set-cookie"].lower()
    assert f"tb_acting_hospital={hid}" in sc and "httponly" in sc and "samesite=strict" in sc and "path=/" in sc
    assert tc.cookies.get("tb_acting_hospital") == hid
    # without the header the cookie names the hospital (links, images, the viewer); the header wins; nobody else's cookie counts
    assert set(call(tc, "vx", "GET", "/org").json()["users"]) == {"lroot", "bina", "lotdoc"}
    assert call(tc, "vx", "GET", "/me").json()["acting_hospital"]["id"] == hid
    assert set(call(tc, "vx", "GET", "/org", **{"X-TB-Hospital": "default"}).json()["users"]) == {"root", "doc", "mdt"}
    assert set(call(tc, "doc", "GET", "/org").json()["my_departments"][0]) and call(tc, "doc", "GET", "/me").json()["hospital"]["id"] == "default"
    assert len(hospitals.read_audit(50, kind="acting_in")) == 2  # Lotus (POST, then no new line for its requests), then default (header)
    # /platform ignores it; an unknown hospital in the cookie is refused elsewhere
    assert call(tc, "vx", "GET", "/platform/overview").status_code == 200
    tc.cookies.delete("tb_acting_hospital")
    tc.cookies.set("tb_acting_hospital", "gone-hospital")
    assert call(tc, "vx", "GET", "/org").status_code == 404
    assert call(tc, "vx", "GET", "/platform/hospitals").status_code == 200 and call(tc, "vx", "GET", "/me").status_code == 200
    r = call(tc, "vx", "DELETE", "/platform/acting")
    sc = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "tb_acting_hospital=" in sc and ("max-age=0" in sc or "expires=thu, 01 jan 1970" in sc)
    tc.cookies.delete("tb_acting_hospital")  # the test's own hand-set cookie (the browser drops the server's on that answer)
    assert set(call(tc, "vx", "GET", "/org").json()["users"]) == {"root", "doc", "mdt"}


# ---- 3. a hospital other than default, end to end ---------------------------------------------------------------------------------

def test_a_lotus_login_lists_its_own_case_file_with_the_same_id(world):
    tc, _, _, _, _ = world
    r = call(tc, "bina", "GET", "/cases")
    assert r.status_code == 200 and [c["case_id"] for c in r.json()["cases"]] == ["TB-001"] and LOTUS_PATIENT in r.text
    assert LOTUS_PATIENT in call(tc, "bina", "GET", "/cases/TB-001").text
    r = call(tc, "mdt", "GET", "/cases")
    assert [c["case_id"] for c in r.json()["cases"]] == ["TB-001"] and LOTUS_PATIENT not in r.text
    assert LOTUS_PATIENT not in call(tc, "mdt", "GET", "/cases/TB-001").text
    r = call(tc, "bina", "GET", "/case-list")
    assert [c["case_id"] for c in r.json()["cases"]] == ["TB-001"] and r.json()["cases"][0]["patient"]["name"] == LOTUS_PATIENT


def _state(tc, user, mid, cookie=None):
    tc.cookies.set("vaidyx_session", f"tok-{user}")
    if cookie:
        tc.cookies.delete("tb_acting_hospital")
        tc.cookies.set("tb_acting_hospital", cookie)
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws", headers=ORIGIN) as ws:
        m = ws.receive_json()
    assert m["type"] == "state"
    return m


def test_sockets_serve_the_logins_own_hospital(world):
    tc, _, hid, dmid, lmid = world
    assert _state(tc, "bina", lmid)["meeting"]["title"] == "Lotus weekly board"
    assert _state(tc, "mdt", dmid)["meeting"]["title"] == "Default weekly board"
    tc.cookies.set("vaidyx_session", "tok-bina")
    if dmid != lmid:
        with pytest.raises(WebSocketDisconnect):  # the default hospital's meeting does not exist for Lotus
            with tc.websocket_connect(f"/api/tb/meetings/{dmid}/ws", headers=ORIGIN) as ws:
                ws.receive_json()
    # the messages socket: bina and lotdoc are placed only in Lotus, so a socket answered from "default" would refuse them
    for user in ("bina", "lotdoc"):
        tc.cookies.set("vaidyx_session", f"tok-{user}")
        with tc.websocket_connect("/api/tb/messages/ws", headers=ORIGIN) as ws:
            assert ws.receive_json()["type"] == "unread"
    # never for anyone else: mdt with a Lotus cookie stays in default
    assert _state(tc, "mdt", dmid, cookie=hid)["meeting"]["title"] == "Default weekly board"


class _Sock:
    """What live._socket_hospital reads of a WebSocket."""
    def __init__(self, auth, headers=None, query=None, cookies=None):
        self.headers, self.query_params, self.cookies = headers or {}, query or {}, cookies or {}
        self.app = type("A", (), {"state": type("S", (), {"auth_manager": auth})()})()


def test_socket_hospital_rule_for_a_vaidyx_admin(world):
    from tumour_board.api import live as live_api
    _, auth, hid, _, _ = world
    f = live_api._socket_hospital
    assert f(_Sock(auth), "vx") == ("default", None)
    assert f(_Sock(auth, cookies={"tb_acting_hospital": hid}), "vx") == (hid, None)              # the cookie
    assert f(_Sock(auth, headers={"x-tb-hospital": "default"}, cookies={"tb_acting_hospital": hid}), "vx") == ("default", None)  # header wins
    assert f(_Sock(auth, query={"hospital": hid}), "vx") == (hid, None)
    assert f(_Sock(auth, cookies={"tb_acting_hospital": "gone-hospital"}), "vx")[1] == "hospital_unknown"  # refused, never a fall-back
    assert f(_Sock(auth, cookies={"tb_acting_hospital": hid}), "mdt") == ("default", None)        # nobody else
    assert f(_Sock(auth, cookies={"tb_acting_hospital": "default"}), "bina") == (hid, None)
