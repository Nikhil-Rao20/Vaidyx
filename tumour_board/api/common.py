"""Helpers shared by the routers in tumour_board/api/*. They reuse the guards of routes/tumour_board_routes.py (imported lazily, so
there is no import cycle: that module includes these routers inside setup_tumour_board_routes(), after it is fully loaded).

Rules every new route follows:
- who is asking: roles(request) (the Vaidyx login plus the Tumour Board roles from org.json);
- every change is checked with need() / need_case() and audited with audit();
- errors are plain JSON {"detail": message, "code": short_code}; the interface shows the message as it is;
- heavy or repeated calls go through RateLimit.
"""
import threading, time

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
    from tumour_board import store
    store.audit(case_id, kind, by=by, **fields)


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
