"""The meeting WebSocket (B3): cookie authentication (no middleware runs for a socket), the Origin check, the state message on connect,
events broadcast after a change, ping / pong, presence, and the hub helper that is safe without a loop or clients."""
import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from tumour_board import live, meetings
from tumour_board.tests.test_nik_meetings import As, app, tc, owned, started, with_agenda, join_and_admit  # noqa: F401  (fixtures and helpers)


def recv_until(ws, kind, limit=10):
    for _ in range(limit):
        m = ws.receive_json()
        if m.get("type") == kind:
            return m
    raise AssertionError(f"no {kind} event")


def test_socket_refuses_without_a_cookie_or_with_a_foreign_origin(tc):
    for cid in ("TB-001", "TB-002", "TB-003"):  # owned Case Files: only their team, the sheet and the coordinator may open the meeting
        owned(cid)
    mid = with_agenda(tc)
    tc.cookies.clear()
    with pytest.raises(WebSocketDisconnect) as e:
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws"):
            pass
    assert e.value.code == 1008
    tc.cookies.set("vaidyx_session", "tok-anil")
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws", headers={"Origin": "https://evil.example"}):
            pass
    tc.cookies.set("vaidyx_session", "tok-nobody")  # an unknown token
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws"):
            pass
    tc.cookies.set("vaidyx_session", "tok-mohan")  # a placed user who did not join and whose department is not on the attendance sheet
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws"):
            pass
    tc.cookies.set("vaidyx_session", "tok-anil")
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect("/api/tb/meetings/S20991231-zzzz/ws"):
            pass
    assert live.hub.count(mid) == 0


def test_state_on_connect_then_events_ping_and_presence(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    tc.cookies.set("vaidyx_session", "tok-priya")
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws", headers={"Origin": "http://testserver"}) as ws:
        st = ws.receive_json()
        assert st["type"] == "state" and st["meeting"]["id"] == mid and st["current"]["case_id"] == "TB-001" and st["me"]["user"] == "priya"
        assert st["code"] is None  # a member never sees the code
        pres = recv_until(ws, "presence")
        assert "priya" in pres["online"] and pres["joined"] == "priya"
        assert As(tc, "anil").get(f"/meetings/{mid}").json()["online"] == ["priya"]  # an open socket is online
        assert live.online(mid) == ["priya"]
        ws.send_json({"type": "ping"})
        assert recv_until(ws, "pong")["type"] == "pong"
        r = As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002", "slide": 1})
        assert r.status_code == 200
        ev = recv_until(ws, "current")
        assert ev["case_id"] == "TB-002" and ev["slide"] == 1 and ev["agent"]["active"] is True
        As(tc, "anil").put(f"/meetings/{mid}/decision-live", json={"text": "typing"})
        assert recv_until(ws, "decision_live")["text"] == "typing"
        As(tc, "anil").post(f"/meetings/{mid}/timer", json={"action": "start", "minutes": 1})
        assert recv_until(ws, "timer")["timer"]["running"] is True
        As(tc, "priya").post(f"/meetings/{mid}/hand", json={"raised": True})
        assert recv_until(ws, "hand")["hands"][0]["user"] == "priya"
        As(tc, "priya").post(f"/meetings/{mid}/questions", json={"text": "Size?"})
        assert recv_until(ws, "question")["question"]["text"] == "Size?"
        ws.send_json({"type": "state"})
        assert recv_until(ws, "state")["current"]["case_id"] == "TB-002"
        As(tc, "anil").post(f"/meetings/{mid}/end")
        assert recv_until(ws, "ended")["meeting"]["status"] == "closed"
    assert live.hub.count(mid) == 0 and live.online(mid) == []


def test_two_sockets_and_the_admit_event(tc):
    mid = with_agenda(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "priya").post("/meetings/join", json={"code": code})
    tc.cookies.set("vaidyx_session", "tok-priya")
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as waiting:  # the waiting room keeps a socket to hear its admission
        assert waiting.receive_json()["me"]["status"] == "waiting"
        tc.cookies.set("vaidyx_session", "tok-anil")
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as coord:
            assert coord.receive_json()["type"] == "state"
            assert sorted(live.online(mid)) == ["anil", "priya"]
            As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "priya"})
            ev = recv_until(waiting, "admit")
            assert ev["user"] == "priya" and ev["status"] == "remote"
            assert recv_until(coord, "admit")["user"] == "priya"
        assert recv_until(waiting, "presence")["left"] == "anil"
    assert live.hub.count(mid) == 0


def until(ws, kind, limit=10):
    """Every message up to and including the first of `kind`."""
    seen = []
    for _ in range(limit):
        seen.append(ws.receive_json())
        if seen[-1].get("type") == kind:
            return seen
    raise AssertionError(f"no {kind} event")


def test_a_waiting_socket_gets_no_live_content_until_admitted(tc):
    mid = started(tc)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "priya").post("/meetings/join", json={"code": code})
    tc.cookies.set("vaidyx_session", "tok-priya")
    with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as waiting:
        st = waiting.receive_json()
        assert st["me"]["status"] == "waiting" and st["can"]["member"] is False and st["questions"] == [] and st["decision_live"]["text"] == ""
        tc.cookies.set("vaidyx_session", "tok-anil")
        with tc.websocket_connect(f"/api/tb/meetings/{mid}/ws") as coord:
            assert coord.receive_json()["can"]["member"] is True
            As(tc, "anil").put(f"/meetings/{mid}/decision-live", json={"text": "typing"})
            assert recv_until(coord, "decision_live")["text"] == "typing"
            As(tc, "anil").post(f"/meetings/{mid}/current", json={"slide": 2})
            assert recv_until(coord, "current")["slide"] == 2
            seen = until(waiting, "current")
            assert "decision_live" not in [m["type"] for m in seen] and seen[-1]["opened"] is None and seen[-1]["slide"] == 2
            As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "priya"})
            assert recv_until(waiting, "admit")["user"] == "priya"
            As(tc, "anil").put(f"/meetings/{mid}/decision-live", json={"text": "now a member"})
            assert recv_until(waiting, "decision_live")["text"] == "now a member"
    assert live.hub.count(mid) == 0


def test_broadcast_shapes_each_socket():
    live.hub.clear()

    class Sock:
        def __init__(self):
            self.got = []

        async def send_json(self, ev):
            self.got.append(ev)
    a, b = Sock(), Sock()
    live.hub.connect("M2", a, "anil", {"coordinator": True})
    live.hub.connect("M2", b, "priya", None)

    async def go():
        assert live.broadcast("M2", {"type": "open", "opened": {"url": "/x"}}, shape=lambda u, info, ev: ev if info else None) is True
        assert live.broadcast("M2", {"type": "x"}, shape=lambda u, info, ev: None) is False  # nobody gets it
        assert live.broadcast("M2", {"type": "y"}, shape=lambda u, info, ev: 1 / 0) is False  # a failing shape sends nothing
        await asyncio.sleep(0.01)
    asyncio.run(go())
    assert a.got == [{"type": "open", "opened": {"url": "/x"}}] and b.got == []
    live.hub.clear()


def test_broadcast_is_safe_without_clients_or_loop():
    live.hub.clear()
    assert live.broadcast("S20991231-abcd", {"type": "current"}) is False
    assert live.broadcast("S20991231-abcd", "not an event") is False

    class Dead:
        async def send_json(self, ev):
            raise RuntimeError("gone")

    class Alive:
        def __init__(self):
            self.got = []

        async def send_json(self, ev):
            self.got.append(ev)
    dead, alive = Dead(), Alive()
    live.hub.connect("M1", dead, "a")
    live.hub.connect("M1", alive, "b")
    assert live.online("M1") == ["a", "b"]

    async def go():
        assert live.broadcast("M1", {"type": "x"}) is True
        await asyncio.sleep(0.01)
    asyncio.run(go())
    assert alive.got == [{"type": "x"}] and live.online("M1") == ["b"]  # the dead socket is dropped
    live.hub.clear()
    assert live.hub.count("M1") == 0


def test_origin_and_cookie_helpers():
    class WS:
        def __init__(self, headers, cookies, mgr):
            self.headers, self.cookies = headers, cookies

            class App:
                pass
            self.app = App(); self.app.state = App(); self.app.state.auth_manager = mgr

    class Mgr:
        def get_username_for_token(self, t):
            return {"good": "anil"}.get(t)
    assert live.origin_ok(WS({"host": "127.0.0.1:7000"}, {}, None)) is True
    assert live.origin_ok(WS({"host": "127.0.0.1:7000", "origin": "http://127.0.0.1:7000"}, {}, None)) is True
    assert live.origin_ok(WS({"host": "127.0.0.1:7000", "origin": "http://127.0.0.1:7100"}, {}, None)) is False
    assert live.origin_ok(WS({"host": "127.0.0.1:7000", "origin": "https://evil.example"}, {}, None)) is False
    assert live.authenticate(WS({}, {"vaidyx_session": "good"}, Mgr())) == "anil"
    assert live.authenticate(WS({}, {"vaidyx_session": "bad"}, Mgr())) is None
    assert live.authenticate(WS({}, {}, Mgr())) is None
    assert live.authenticate(WS({}, {"vaidyx_session": "good"}, None)) is None
