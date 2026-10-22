"""Helpers shared by the routers in tumour_board/api/*. They reuse the guards of routes/tumour_board_routes.py (imported lazily, so
there is no import cycle: that module includes these routers inside setup_tumour_board_routes(), after it is fully loaded).

Rules every new route follows:
- who is asking: roles(request) (the Vaidyx login plus the Tumour Board roles from org.json);
- every change is checked with need() / need_case() and audited with audit();
- errors are plain JSON {"detail": message, "code": short_code}; the interface shows the message as it is;
- heavy or repeated calls go through RateLimit.
"""
import hashlib, threading, time

from fastapi import APIRouter, HTTPException, Request


def route_class():
    from routes.tumour_board_routes import _ModelErrorRoute
    return _ModelErrorRoute


def make_router(tags=None):
    """An APIRouter that keeps the Tumour Board guards (disabled logins, placed accounts, Case File scope, model errors)."""
    return APIRouter(tags=tags or ["tumour-board-nik"], route_class=route_class())


def user(request: Request) -> str:
    from routes.tumour_board_routes import _user
    return _user(request)


def roles(request: Request) -> dict:
    from routes.tumour_board_routes import _roles
    return _roles(request)


def need(r, action, department=None):
    from routes.tumour_board_routes import _need
    _need(r, action, department)


def need_case(r, action, c, department=None):
    from routes.tumour_board_routes import _need_case
    _need_case(r, action, c, department)


def need_known(r):
    from routes.tumour_board_routes import _need_known
    _need_known(r)


def scope(request: Request):
    from routes.tumour_board_routes import _scope
    return _scope(request)


def case(case_id: str) -> dict:
    from routes.tumour_board_routes import _case
    return _case(case_id)


def auth_manager(request: Request):
    from routes.tumour_board_routes import _auth_manager
    return _auth_manager(request)


def fail(status: int, message: str, code: str = ""):
    """A refusal the interface can show as it is (message) and act on (code)."""
    raise HTTPException(status, {"message": message, "code": code} if code else message)


async def body(request: Request) -> dict:
    """The JSON body as a dict; anything else is a 400."""
    try:
        data = await request.json()
    except Exception:
        fail(400, "The request body must be JSON.", "bad_json")
    if not isinstance(data, dict):
        fail(400, "The request body must be a JSON object.", "bad_json")
    return data


def audit(case_id: str, kind: str, by: str, **fields):
    """One hash-chained event in the Case File's audit log (store.audit takes one event dict)."""
    from tumour_board import store
    store.audit(case_id, {"kind": kind, "by": by, **fields})


class RateLimit:
    """A small in-memory limiter: at most `limit` hits per `window` seconds per key (a login or a client host). One process only,
    which is what this app runs. Used on sign-in style routes (join codes, resets) and on model calls."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict = {}
        self._lock = threading.Lock()

    def check(self, key: str, message: str = "Too many attempts. Please wait a moment."):
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                raise HTTPException(429, {"message": message, "code": "rate_limited"})
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 5000:  # forget old keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    self._hits.pop(k, None)


def client_key(request: Request) -> str:
    u = ""
    try:
        u = user(request)
    except Exception:
        pass
    return u or (request.client.host if request.client else "unknown")


# ---- the Tumour Board idle timeout (security review #11) ----------------------------------------------------------------------------
# The sign-in keeps its "remember" cookie (7 days, the main app's rule); the Tumour Board routes refuse a session that has been idle
# for more than IDLE_SECONDS (401, code idle_timeout) so an unattended workstation does not stay signed in to patient data. Last-seen
# times live in memory per session token (kept as a hash, never the token itself); a restart forgets them (the next request starts a
# new clock). A request the interface marks as background (header X-TB-Background: 1: a poll while nobody touched the page) is
# checked but does not count as activity.
IDLE_SECONDS = 8 * 3600
BACKGROUND_HEADER = "x-tb-background"
_seen: dict = {}
_seen_lock = threading.Lock()
_FORGET_AFTER = 8 * 24 * 3600  # past the longest cookie (7 days) a token is dead anyway


def _token_key(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def idle_expired(token, touch: bool = True, now: float | None = None) -> bool:
    """True when this session token was last active more than IDLE_SECONDS ago (it stays refused); otherwise the activity is recorded
    (touch=False: only a first sighting is recorded). No token: never expired (the routes' own login checks apply)."""
    if not token:
        return False
    k = _token_key(token)
    now = time.time() if now is None else now
    with _seen_lock:
        last = _seen.get(k)
        if last is not None and now - last > IDLE_SECONDS:
            return True
        if touch or last is None:
            _seen[k] = now
        if len(_seen) > 20000:
            for x in [x for x, t in _seen.items() if now - t > _FORGET_AFTER]:
                _seen.pop(x, None)
    return False


def forget_sessions() -> None:
    """Tests: start every session's clock again."""
    with _seen_lock:
        _seen.clear()


# ---- the JSON body cap (security review #19) ----------------------------------------------------------------------------------------
MAX_JSON_BYTES = 1024 * 1024  # 1 MB; uploads (multipart) keep their own limit
