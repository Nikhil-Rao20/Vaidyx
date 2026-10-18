"""WebSocket /api/tb/meetings/{mid}/ws (B3): the live channel of a meeting. No middleware runs for a WebSocket, so the socket
authenticates itself from the vaidyx_session cookie, checks the Origin against the Host and that the user may open the meeting; then it
sends {"type": "state", ...GET /meetings/{mid}} and keeps the socket in the hub; {"type": "ping"} is answered with pong."""
import logging, time

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


@router.websocket("/meetings/{mid}/ws")
async def meeting_socket(websocket: WebSocket, mid: str):
    user = live.authenticate(websocket)
    if not user or not live.origin_ok(websocket):
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
    await websocket.accept()
    live.hub.connect(mid, websocket, user, rl)
    try:
        await websocket.send_json({"type": "state", **meetings.view(mid, rl)})
        live.broadcast(mid, {"type": "presence", "attendance": meetings.attendance_rows(s), "online": live.online(mid), "joined": user})
        while True:
            msg = await websocket.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "t": time.time()})
            elif isinstance(msg, dict) and msg.get("type") == "state":  # a client asks for the state again (after a reconnect)
                await websocket.send_json({"type": "state", **meetings.view(mid, rl)})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("meeting socket closed (%s)", e)
    finally:
        live.hub.disconnect(mid, websocket)
        try:
            s = meetings.get(mid)
            if s:
                live.broadcast(mid, {"type": "presence", "attendance": meetings.attendance_rows(s), "online": live.online(mid), "left": user})
        except Exception:
            pass
