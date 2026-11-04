"""WebSocket /api/tb/meetings/{mid}/ws (B3): the live channel of a meeting. No middleware runs for a WebSocket, so the socket
authenticates itself from the vaidyx_session cookie, checks the Origin against the Host and that the user may open the meeting; then it
sends {"type": "state", ...GET /meetings/{mid}} and keeps the socket in the hub; {"type": "ping"} is answered with pong.
Security review #16: the session and the roles are checked again on every client message and every minute (a signed-out, disabled,
idle or removed user loses the socket), at most MAX_SOCKETS_PER_USER sockets per user per meeting, a client asks for the state at most
once per STATE_EVERY seconds, and every send has a timeout (a client that does not read is dropped)."""
import asyncio, logging, time

from fastapi import WebSocket, WebSocketDisconnect

from . import common
from .. import live, meetings, org

log = logging.getLogger(__name__)
router = common.make_router(["tumour-board-live"])
POLICY = 1008  # the close code for a refused socket (policy violation)


def _roles(websocket: WebSocket, user: str) -> dict:
    mgr = getattr(websocket.app.state, "auth_manager", None)
    admin = bool(mgr is not None and callable(getattr(mgr, "is_admin", None)) and mgr.is_admin(user))
    return org.roles(user, vaidyx_admin=admin)


def _must_change(websocket: WebSocket, user: str) -> bool:
    """A first (or reset) password works only to choose a new one: no live channel until then (security review #4)."""
    mgr = getattr(websocket.app.state, "auth_manager", None)
    fn = getattr(mgr, "must_change_password", None)
    try:
        if callable(fn) and fn(user):
            return True
        # a guest reviewer (real_data) without two-step sign-in: no live channel either (5 Nov 2026 review)
        if org.roles(user).get("real_data") and __import__("os").getenv("TB_REAL_DATA_2FA", "1").strip() != "0":
            t = getattr(mgr, "totp_enabled", None)
            return not (callable(t) and t(user))
        return False
    except Exception:
        return True


def _still_allowed(websocket: WebSocket, mid: str, user: str):
    """The roles of the user when the socket may stay open (security review #16): the same session cookie still names the same user,
    the first password was changed, the session is not idle past the Tumour Board limit, the Tumour Board access is not disabled and
    the user may still open the meeting. None when the socket must close."""
    try:
        if live.authenticate(websocket) != user or _must_change(websocket, user) or common.idle_expired(websocket.cookies.get(live.COOKIE), touch=False):
            return None
        rl = _roles(websocket, user)
        s = meetings.get(mid)
        if not s or rl.get("disabled") or not meetings.may_view(rl, s):
            return None
        return rl
    except Exception as e:
        log.warning("meeting socket re-check failed (%s)", e)
        return None


async def _send(websocket: WebSocket, data: dict) -> bool:
    """One message with the hub's timeout; False when the client did not take it in time (the socket is then closed)."""
    try:
        await asyncio.wait_for(websocket.send_json(data), timeout=live.SEND_TIMEOUT)
        return True
    except Exception:
        return False


@router.websocket("/meetings/{mid}/ws")
async def meeting_socket(websocket: WebSocket, mid: str):
    user = live.authenticate(websocket)
    if not user or not live.origin_ok(websocket) or _must_change(websocket, user) or common.idle_expired(websocket.cookies.get(live.COOKIE), touch=False):
        await websocket.close(code=POLICY)
        return
    try:
        rl = _roles(websocket, user)
        s = meetings.get(mid)
    except Exception as e:
        log.warning("meeting socket refused (%s)", e)
        await websocket.close(code=POLICY)
        return
    if not s or rl.get("disabled") or not meetings.may_view(rl, s):
        await websocket.close(code=POLICY)
        return
    if live.hub.user_count(mid, user) >= live.MAX_SOCKETS_PER_USER:  # one person, a few tabs at most (security review #16)
        await websocket.close(code=POLICY)
        return
    await websocket.accept()
    live.hub.connect(mid, websocket, user, rl)
    last_state = 0.0
    checked = time.monotonic()
    try:
        if not await _send(websocket, {"type": "state", **meetings.view(mid, rl)}):
            return
        live.broadcast(mid, {"type": "presence", "attendance": meetings.attendance_rows(s), "online": live.online(mid), "joined": user})
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=live.RECHECK_SECONDS)
            except asyncio.TimeoutError:
                msg = None
            if msg is not None or time.monotonic() - checked >= live.RECHECK_SECONDS:  # each message, and every minute when quiet
                rl = _still_allowed(websocket, mid, user)
                if rl is None:
                    await websocket.close(code=POLICY)
                    return
                live.hub.update(websocket, rl)
                checked = time.monotonic()
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "ping":
                if not await _send(websocket, {"type": "pong", "t": time.time()}):
                    return
            elif msg.get("type") == "state":  # a client asks for the state again (after a reconnect); at most one per STATE_EVERY seconds
                now = time.monotonic()
                if now - last_state < live.STATE_EVERY:
                    continue
                last_state = now
                if not await _send(websocket, {"type": "state", **meetings.view(mid, rl)}):
                    return
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("meeting socket closed (%s)", e)
    finally:
        live.hub.disconnect(mid, websocket)
        try:
            if live.hub.user_count(mid, user) == 0:  # the user's last tab closed: no "Listening" or "Speaking" left behind (review 9 D, I4)
                meetings.user_left(mid, user)
        except Exception as e:
            log.info("meeting socket: live state not cleared (%s)", e.__class__.__name__)
        try:
            s = meetings.get(mid)
            if s:
                live.broadcast(mid, {"type": "presence", "attendance": meetings.attendance_rows(s), "online": live.online(mid), "left": user})
        except Exception:
            pass
