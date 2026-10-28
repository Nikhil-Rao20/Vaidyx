"""WebSocket /api/tb/messages/ws (night-v3 item 8.2, contract docs/night-v3/research/06_messages.md section 9.5): the live channel of
Messages. The pattern of api/live.py: no middleware runs for a socket, so it authenticates itself from the vaidyx_session cookie, checks
the Origin against the Host, refuses a first password, an idle session and anyone Messages is not for (close 1008), and checks again on
every client message and every minute. One room per login ("u:<login>") in live.messages_hub, at most MAX_SOCKETS_PER_USER sockets.

At import this module registers its sender in messages.LISTENERS and its presence in messages.PRESENCE. Presence: online = a socket and
activity (connect, "active", "typing") in the last 10 minutes; away = a socket but no activity; offline = no socket. A change is sent
only to the people who share a conversation with the person. Typing: at most one event per 3 seconds per login, only to the other
readers of a conversation the person reads."""
import asyncio, logging, threading, time

from fastapi import WebSocket, WebSocketDisconnect

from . import common
from .live import _must_change, _roles, _send
from .. import live, messages

log = logging.getLogger(__name__)
router = common.make_router(["tumour-board-messages"])
POLICY = 1008
TYPING_EVERY = 3.0
LAST_ACTIVE: dict = {}  # login -> monotonic time of the last activity
_TYPED: dict = {}  # login -> monotonic time of the last typing event passed on
_ANNOUNCED: dict = {}  # login -> the presence state last sent to the contacts
_state_lock = threading.Lock()


def room(user: str) -> str:
    return f"u:{user}"


def presence_of(user: str) -> str:
    if not user or live.messages_hub.user_count(room(user), user) == 0:
        return "offline"
    t = LAST_ACTIVE.get(user)
    if t is None or time.monotonic() - t > messages.PRESENCE_AWAY_SECONDS:
        return "away"
    return "online"


def _shape(user, info, event):
    """A socket whose login lost Messages since it connected (roles re-checked every minute) gets nothing."""
    return event if messages.may_use(info) else None


def deliver(reader: str, event: dict) -> None:
    live.broadcast(room(reader), event, shape=_shape, hub_=live.messages_hub)


def interested(reader: str) -> bool:
    return live.messages_hub.count(room(reader)) > 0


def announce(user: str) -> None:
    """Send the person's presence to their contacts when it changed since the last announcement."""
    state = presence_of(user)
    with _state_lock:
        if _ANNOUNCED.get(user, "offline") == state:
            return
        if state == "offline":
            _ANNOUNCED.pop(user, None)
        else:
            _ANNOUNCED[user] = state
    ev = {"type": "presence", "user": user, "state": state}
    for c in messages.contacts(user):
        try:
            deliver(c, ev)
        except Exception:
            pass


def clear() -> None:
    """Tests: forget the in-memory state."""
    LAST_ACTIVE.clear()
    _TYPED.clear()
    _ANNOUNCED.clear()


def _install() -> None:
    messages.PRESENCE = presence_of
    messages.INTERESTED = interested
    messages.LISTENERS[:] = [f for f in messages.LISTENERS if not (getattr(f, "__module__", "") == __name__ and getattr(f, "__name__", "") == "deliver")]
    messages.LISTENERS.append(deliver)


_install()


def _still_allowed(websocket: WebSocket, user: str):
    """The roles when the socket may stay open: the same session names the same login, the first password was changed, the session is
    not idle and the login may still use Messages. None when the socket must close."""
    try:
        if live.authenticate(websocket) != user or _must_change(websocket, user) or common.idle_expired(websocket.cookies.get(live.COOKIE), touch=False):
            return None
        rl = _roles(websocket, user)
        return rl if messages.may_use(rl) else None
    except Exception as e:
        log.warning("messages socket re-check failed (%s)", e.__class__.__name__)
        return None


@router.websocket("/messages/ws")
async def messages_socket(websocket: WebSocket):
    user = live.authenticate(websocket)
    if not user or not live.origin_ok(websocket) or _must_change(websocket, user) or common.idle_expired(websocket.cookies.get(live.COOKIE), touch=False):
        await websocket.close(code=POLICY)
        return
    try:
        rl = _roles(websocket, user)
    except Exception as e:
        log.warning("messages socket refused (%s)", e.__class__.__name__)
        await websocket.close(code=POLICY)
        return
    if not messages.may_use(rl):
        await websocket.close(code=POLICY)
        return
    if live.messages_hub.user_count(room(user), user) >= live.MAX_SOCKETS_PER_USER:
        await websocket.close(code=POLICY)
        return
    await websocket.accept()
    live.messages_hub.connect(room(user), websocket, user, rl)
    LAST_ACTIVE[user] = time.monotonic()
    checked = time.monotonic()
    try:
        if not await _send(websocket, {"type": "unread", "total": messages.unread_total(user, r=rl)}):
            return
        announce(user)
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=live.RECHECK_SECONDS)
            except asyncio.TimeoutError:
                msg = None
            if msg is not None or time.monotonic() - checked >= live.RECHECK_SECONDS:
                rl = _still_allowed(websocket, user)
                if rl is None:
                    await websocket.close(code=POLICY)
                    return
                live.messages_hub.update(websocket, rl)
                checked = time.monotonic()
            if not isinstance(msg, dict):
                announce(user)  # a quiet minute may have turned online into away
                continue
            kind = msg.get("type")
            if kind == "ping":
                if not await _send(websocket, {"type": "pong"}):
                    return
            elif kind == "active":
                LAST_ACTIVE[user] = time.monotonic()
                announce(user)
            elif kind == "typing":
                now = time.monotonic()
                LAST_ACTIVE[user] = now
                announce(user)
                if now - _TYPED.get(user, -1e9) < TYPING_EVERY:
                    continue
                _TYPED[user] = now
                messages.typing(user, str(msg.get("conversation_id") or ""), r=rl)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("messages socket closed (%s)", e.__class__.__name__)
    finally:
        live.messages_hub.disconnect(room(user), websocket)
        try:
            announce(user)
        except Exception:
            pass
