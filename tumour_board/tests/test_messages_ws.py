"""The Messages socket (night-v3 item 8.2, contract docs/night-v3/research/06_messages.md section 9.5): refused without a session, from
a foreign origin or for a login Messages is not for (1008); a message reaches the reader's socket as it is sent; typing reaches only the
other readers, at most once per 3 seconds; presence goes online then offline to the people who share a conversation. Synthetic logins."""
import pytest
from starlette.websockets import WebSocketDisconnect

from tumour_board import live, messages
from tumour_board.api import messages as api_messages
from tumour_board.api import messages_ws
from tumour_board.tests.test_nik_meetings import As, app, tc  # noqa: F401  (fixtures and helpers)

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(autouse=True)
def _fresh():
    for n in api_messages.LIMITS:
        getattr(api_messages, n)._hits.clear()
    live.messages_hub.clear()
    messages._PUSHED.clear()
    messages._DENIED.clear()
    messages_ws.clear()
    yield
    live.messages_hub.clear()
    messages_ws.clear()


def connect(tc, login):
    tc.cookies.set("vaidyx_session", f"tok-{login}")
    return tc.websocket_connect("/api/tb/messages/ws", headers=ORIGIN)


def until(ws, kind, limit=12):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if m.get("type") == kind:
            return m, seen
    raise AssertionError(f"no {kind} event in {seen}")


def drain(ws):
    """Every event up to a pong (the socket handles messages in order, so earlier events arrive first)."""
    ws.send_json({"type": "ping"})
    return until(ws, "pong", limit=30)[1][:-1]


def start(tc, by, to, text="Please see the report."):
    r = As(tc, by).post("/messages/conversations", json={"to": to, "text": text})
    assert r.status_code == 201, r.text
    return r.json()


def test_listener_and_presence_are_installed():
    assert messages_ws.deliver in messages.LISTENERS and messages.PRESENCE is messages_ws.presence_of
    assert messages.presence("nobody") == "offline"


@pytest.mark.parametrize("login", [None, "nobody", "tbroot", "guest", "admin"])
def test_refused_without_a_session_or_for_an_unplaced_login(tc, login):
    tc.cookies.clear()
    if login:
        tc.cookies.set("vaidyx_session", f"tok-{login}")
    with pytest.raises(WebSocketDisconnect) as e:
        with tc.websocket_connect("/api/tb/messages/ws", headers=ORIGIN) as ws:
            ws.receive_json()
    assert e.value.code == 1008
    assert live.messages_hub.online_users() == []


def test_refused_from_a_foreign_origin(tc):
    tc.cookies.set("vaidyx_session", "tok-priya")
    with pytest.raises(WebSocketDisconnect) as e:
        with tc.websocket_connect("/api/tb/messages/ws", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_a_message_reaches_the_readers_socket_and_read_tells_the_sender(tc):
    cid = start(tc, "priya", {"user": "ravi"}, text="First")["conversation"]["id"]
    with connect(tc, "ravi") as ravi:
        assert ravi.receive_json() == {"type": "unread", "total": 1}
        As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "Second"})
        ev, _ = until(ravi, "message")
        assert ev["message"]["text"] == "Second" and ev["message"]["by"] == "priya" and ev["conversation"]["id"] == cid
        assert ev["conversation"]["title"] == "Dr Priya Nair" and ev["conversation"]["unread"] == 2  # built for the reader
        assert until(ravi, "unread")[0]["total"] == 2
        with connect(tc, "priya") as priya:
            until(priya, "unread")
            As(tc, "ravi").post(f"/messages/conversations/{cid}/read", json={"seq": 99})
            seen, _ = until(priya, "read")
            assert seen == {"type": "read", "conversation_id": cid, "by": "ravi", "seq": 2}
            assert until(ravi, "unread")[0]["total"] == 0
            As(tc, "priya").post(f"/messages/conversations/{cid}/resolve", json={"resolved": True})
            assert until(ravi, "resolve")[0]["resolved"]["by"] == "priya"


def test_typing_only_to_the_other_readers_and_throttled(tc, monkeypatch):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    with connect(tc, "ravi") as ravi, connect(tc, "priya") as priya, connect(tc, "meena") as meena:
        for ws in (ravi, priya, meena):
            drain(ws)
        priya.send_json({"type": "typing", "conversation_id": cid})
        priya.send_json({"type": "typing", "conversation_id": cid})
        meena.send_json({"type": "typing", "conversation_id": cid})  # not a participant: dropped
        drain(priya), drain(meena)
        typing = [e for e in drain(ravi) if e["type"] == "typing"]
        assert typing == [{"type": "typing", "conversation_id": cid, "by": "priya", "by_name": "Dr Priya Nair"}]
        assert not [e for e in drain(priya) if e["type"] == "typing"]
        monkeypatch.setattr(messages_ws, "TYPING_EVERY", 0.0)
        priya.send_json({"type": "typing", "conversation_id": cid})
        drain(priya)
        assert [e["by"] for e in drain(ravi) if e["type"] == "typing"] == ["priya"]


def test_presence_online_then_offline_to_contacts_only(tc):
    start(tc, "priya", {"user": "ravi"})
    with connect(tc, "ravi") as ravi, connect(tc, "meena") as meena:
        drain(ravi), drain(meena)
        assert messages.presence("ravi") == "online" and messages.presence("priya") == "offline"
        with connect(tc, "priya") as priya:
            drain(priya)
            ev, _ = until(ravi, "presence")
            assert ev == {"type": "presence", "user": "priya", "state": "online"}
            assert As(tc, "ravi").get("/messages/conversations").json()["conversations"][0]["with"]["online"] is True
        ev, _ = until(ravi, "presence")
        assert ev == {"type": "presence", "user": "priya", "state": "offline"}
        assert not [e for e in drain(meena) if e["type"] == "presence"]  # no shared conversation: nothing about priya
    assert messages.presence("ravi") == "offline"


def test_away_after_ten_minutes_without_activity(tc, monkeypatch):
    with connect(tc, "ravi") as ravi:
        drain(ravi)
        messages_ws.LAST_ACTIVE["ravi"] -= messages.PRESENCE_AWAY_SECONDS + 1
        assert messages.presence("ravi") == "away"
        ravi.send_json({"type": "active"})
        drain(ravi)
        assert messages.presence("ravi") == "online"


def test_shape_drops_a_socket_that_lost_messages():
    ev = {"type": "unread", "total": 1}
    assert messages_ws._shape("ravi", {"user": "ravi", "departments": {"radiology": "member"}}, ev) == ev
    assert messages_ws._shape("ravi", {"user": "ravi", "departments": {}, "expired": True}, ev) is None
    assert messages_ws._shape("ravi", None, ev) is None
