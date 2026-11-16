"""The live channel of a meeting (18 Oct, B3): one hub per meeting in memory, WebSocket clients, events broadcast to all of them.

The route (tumour_board/api/live.py) authenticates the socket from the vaidyx_session cookie (no middleware runs for WebSockets),
checks the Origin against the Host and that the user may open the meeting, sends the meeting state, answers pings and keeps the
socket in the hub until it closes. meetings.py calls broadcast(mid, event, shape) after every change; `shape(user, info, event)` gives
each socket its own copy (or None: not for this socket), so a viewer who is not admitted never receives the live content. It is safe
anywhere: inside the app's event loop it schedules the sends, from a thread it hands them to the loop the sockets live on, and with no
loop or no clients it does nothing (unit tests). Presence: a user with an open socket is online. Dead sockets are dropped on the first
failed send.
Hospitals (admin consoles, 16 Nov 2026): a room is keyed by (hospital, meeting id), the hospital being the current one of the code that
calls (the socket's, the route's), so two hospitals' meetings never share a room even with the same id.
"""
import asyncio, logging, threading

from . import config

log = logging.getLogger(__name__)

COOKIE = "vaidyx_session"
MAX_SOCKETS_PER_USER = 5   # per meeting (security review #16)
STATE_EVERY = 2.0          # seconds between two state messages a client asks for
RECHECK_SECONDS = 60       # the session and roles are checked again this often on a quiet socket
SEND_TIMEOUT = 2.0         # a client that does not take a message within this is dropped


def _key(mid):
    """The room key: (hospital, meeting id); a key already made is kept as it is."""
    return mid if isinstance(mid, tuple) else config.scoped(mid)


class Hub:
    def __init__(self):
        self._rooms: dict[tuple, dict] = {}  # (hospital, mid) -> {websocket: user}
        self._info: dict = {}               # websocket -> what the route knows of the user (its Tumour Board roles)
        self._lock = threading.Lock()
        self.loop = None  # the loop the sockets were accepted on (for broadcasts from threads)
        self._tasks: set = set()

    def connect(self, mid: str, ws, user: str, info=None) -> None:
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        with self._lock:
            self._rooms.setdefault(_key(mid), {})[ws] = user
            self._info[ws] = info

    def update(self, ws, info) -> None:
        """The roles of a socket after its periodic re-check (the per-socket shape uses them)."""
        with self._lock:
            if ws in self._info:
                self._info[ws] = info

    def user_count(self, mid: str, user: str) -> int:
        with self._lock:
            return sum(1 for u in (self._rooms.get(_key(mid)) or {}).values() if u == user)

    def disconnect(self, mid: str, ws) -> None:
        k = _key(mid)
        with self._lock:
            room = self._rooms.get(k)
            if room is not None:
                room.pop(ws, None)
                if not room:
                    self._rooms.pop(k, None)
            self._info.pop(ws, None)

    def entries(self, mid: str) -> list[tuple]:
        """(websocket, user, info) for every socket of the meeting."""
        with self._lock:
            return [(ws, u, self._info.get(ws)) for ws, u in (self._rooms.get(_key(mid)) or {}).items()]

    def clients(self, mid: str) -> list:
        with self._lock:
            return list((self._rooms.get(_key(mid)) or {}).keys())

    def online(self, mid: str) -> list[str]:
        with self._lock:
            return sorted({u for u in (self._rooms.get(_key(mid)) or {}).values() if u})

    def online_users(self) -> list[str]:
        """Every login with a socket in any room of the current hospital (presence over the whole hub, Phase 8)."""
        h = config.hospital_id()
        with self._lock:
            return sorted({u for (hh, _m), room in self._rooms.items() if hh == h for u in room.values() if u})

    def count(self, mid: str) -> int:
        with self._lock:
            return len(self._rooms.get(_key(mid)) or {})

    async def send_all(self, mid: str, event: dict, targets=None) -> int:
        """Send one event to every socket of the meeting (or each of `targets`: [(websocket, its own event)]), all at once, each with
        SEND_TIMEOUT: a socket that fails or does not take the message in time is dropped and closed, so a slow client never holds
        the others up (security review #16). Returns how many received it."""
        mid = _key(mid)
        pairs = list(targets if targets is not None else [(w, event) for w in self.clients(mid)])

        async def one(ws, ev):
            try:
                await asyncio.wait_for(ws.send_json(ev), timeout=SEND_TIMEOUT)
                return True
            except Exception:
                self.disconnect(mid, ws)
                try:
                    await asyncio.wait_for(ws.close(code=1011), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                return False
        if not pairs:
            return 0
        return sum(1 for ok in await asyncio.gather(*(one(ws, ev) for ws, ev in pairs)) if ok)

    def clear(self) -> None:
        with self._lock:
            self._rooms.clear()
            self._info.clear()


hub = Hub()
messages_hub = Hub()  # night-v3 Phase 8: one room per login ("u:<login>") for the person-to-person messages


def online(mid: str) -> list[str]:
    return hub.online(mid)


def broadcast(mid: str, event: dict, shape=None, hub_=None) -> bool:
    """Queue `event` for every socket of the meeting; with `shape(user, info, event)` each socket gets the copy it returns (None: not
    sent to that socket). True when a send was scheduled (there were recipients and a loop). `hub_`: another Hub than the meetings' one
    (the messages hub of Phase 8)."""
    if not isinstance(event, dict):
        return False
    h = hub_ if hub_ is not None else hub
    entries = h.entries(mid)
    if not entries:
        return False
    targets = []
    for ws, user, info in entries:
        try:
            ev = shape(user, info, event) if shape else event
        except Exception:
            ev = None  # when in doubt a socket gets nothing
        if isinstance(ev, dict):
            targets.append((ws, ev))
    if not targets:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    mid = _key(mid)  # the room of the caller's hospital, fixed now (the send may run on another thread's loop)
    if loop is not None:
        t = loop.create_task(h.send_all(mid, event, targets))
        h._tasks.add(t)
        t.add_done_callback(h._tasks.discard)
        return True
    if h.loop is not None and not h.loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(h.send_all(mid, event, targets), h.loop)
            return True
        except RuntimeError:
            return False
    return False


def authenticate(websocket) -> str | None:
    """The username behind the session cookie (request.app.state.auth_manager.get_username_for_token), or None."""
    token = websocket.cookies.get(COOKIE)
    if not token:
        return None
    mgr = getattr(websocket.app.state, "auth_manager", None)
    fn = getattr(mgr, "get_username_for_token", None)
    if not callable(fn):
        return None
    try:
        user = fn(token)
    except Exception:
        return None
    return str(user) if user else None


def origin_ok(websocket) -> bool:
    """A browser always sends Origin on a WebSocket: when present it must name this host (and port). Absent (a script) it passes, as the
    HTTP routes do."""
    origin = websocket.headers.get("origin") or ""
    if not origin:
        return True
    host = websocket.headers.get("host") or ""
    return origin.split("://", 1)[-1].rstrip("/").lower() == host.lower()
