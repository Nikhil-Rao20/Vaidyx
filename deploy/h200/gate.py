r"""Gate for the doctors' instance of Vaidyx-TB (deployment Plan B, docs: deploy/README.md).

Sits on the H200 between the secure link (chisel, whose end is on the VM) and the doctors' instance:

    VM nginx --(link)--> gate 127.0.0.1:7301 --> doctors' instance 127.0.0.1:7300
                                             \-> demo hospital (HIS, desk, report views) 127.0.0.1:7130

Rules:
- Every request must carry the shared secret in X-Vaidyx-Gate (nginx on the VM adds it). Without it: 403. The header is
  never forwarded.
- Only the Tumour Board paths pass (allow-list below); every other path of the Vaidyx app (chat, agents, tools, admin,
  uploads, settings) answers 404.
- Every forwarded request carries X-Forwarded-For, so the app never mistakes a visitor for a trusted local call
  (app.py _is_trusted_loopback).
- WebSockets: only the two live channels (/api/tb/meetings/<id>/ws, /api/tb/messages/ws). The gate checks the browser's
  Origin against the public Host itself, then connects upstream without an Origin (the app accepts a missing Origin and
  still checks the session cookie).

Run: python -m uvicorn gate:app --host 127.0.0.1 --port 7301 --no-proxy-headers   (secret in VX_GATE_SECRET_FILE)
"""
import asyncio
import contextlib
import hmac
import http.cookiejar
import os
import re
from pathlib import Path

import httpx
import websockets
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

UPSTREAM = os.getenv("VX_UPSTREAM", "http://127.0.0.1:7300")
SECRET_HEADER = "x-vaidyx-gate"


def _load_secret() -> bytes:
    f = os.getenv("VX_GATE_SECRET_FILE", "")
    s = Path(f).read_text().strip() if f and Path(f).is_file() else os.getenv("VX_GATE_SECRET", "").strip()
    if len(s) < 32:
        raise SystemExit("gate: no gate secret (VX_GATE_SECRET_FILE), or it is shorter than 32 characters")
    return s.encode()


SECRET = _load_secret()

# The demo hospital (HIS, RIS / LIS desk, report views) is NOT public: the website never links to it, and the app reads it
# server-side (tumour_board/his_client.py). Security review 4 Nov.
ANY_METHOD = re.compile(r"^(/api/tb(/.*)?|/tb-nik/api/enquiry)$")
GET_ONLY = re.compile(r"^(/tb(/.*)?|/tb-nik(/.*)?|/static/.+|/login|/favicon\.ico|/api/version"
                      r"|/api/auth/(status|policy|features|settings|2fa/status)|/api/prefs/(theme|custom-themes))$")
POST_ONLY = {"/api/auth/login", "/api/auth/logout", "/api/auth/2fa/setup", "/api/auth/2fa/confirm",
             "/api/auth/2fa/disable"}  # the website's sign-in and two-factor set-up (password change is /api/tb/me/password)
WS_PATHS = re.compile(r"^/api/tb/(meetings/[A-Za-z0-9_-]{1,64}|messages)/ws$")
NOT_FORWARDED = {"/api/tb/admin"}  # never, even under /api/tb (none exists today; kept as a guard)

HOP_REQ = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
           "transfer-encoding", "upgrade", "content-length", SECRET_HEADER}
HOP_RESP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "trailer", "trailers"}

# One shared client for every visitor: it must never keep cookies (it would send one visitor's session with another's
# request). Each visitor's own Cookie header is forwarded as a plain header; Set-Cookie still reaches the browser.
_NO_COOKIES = http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
_TIMEOUT = httpx.Timeout(connect=10.0, read=900.0, write=900.0, pool=30.0)
client = httpx.AsyncClient(base_url=UPSTREAM, follow_redirects=False, cookies=_NO_COOKIES, timeout=_TIMEOUT)


def has_secret(headers) -> bool:
    got = (headers.get(SECRET_HEADER) or "").encode()
    return bool(got) and hmac.compare_digest(got, SECRET)


def path_safe(path: str) -> bool:
    low = path.lower()
    return not (".." in path or "//" in path or "\\" in path or "%2e" in low or "%2f" in low or "%5c" in low
                or "\x00" in path or any(path == p or path.startswith(p + "/") for p in NOT_FORWARDED))


def same_path(scope, path: str) -> bool:
    """The decoded path must be plain: no control characters (a TAB is kept by nginx's location match but dropped when Starlette
    re-parses the URL, so /api/auth/log%09in slipped past nginx's login limit), no '%' left after decoding (double encoding
    such as %2561), and the same string Starlette routes on. Security review 4 Nov."""
    raw = scope.get("path") or ""
    return raw == path and "%" not in raw and not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw)


def allowed(method: str, path: str) -> bool:
    if not path_safe(path):
        return False
    if ANY_METHOD.match(path):
        return True
    if method in ("GET", "HEAD") and GET_ONLY.match(path):
        return True
    return method == "POST" and path in POST_ONLY


def forwarded_for(request_headers, peer: str) -> str:
    xff = request_headers.get("x-forwarded-for")
    return f"{xff}, {peer}" if xff else peer


async def handle(request: Request):
    if not has_secret(request.headers):
        return PlainTextResponse("Forbidden.", status_code=403)
    path = request.url.path
    if not same_path(request.scope, path):
        return PlainTextResponse("Not available.", status_code=404)
    if path == "/_gate/health":
        try:
            r = await client.get("/login", timeout=5.0)
            ok = r.status_code < 500
        except httpx.HTTPError:
            ok = False
        return JSONResponse({"gate": "ok", "app": "ok" if ok else "down"}, status_code=200 if ok else 503)
    if path in ("/", "/index.html"):
        return RedirectResponse("/tb-nik", status_code=302)
    if not allowed(request.method, path):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not available."}, status_code=404)
        return PlainTextResponse("Not available.", status_code=404)

    peer = request.client.host if request.client else "unknown"
    headers = [(k, v) for k, v in request.headers.items() if k.lower() not in HOP_REQ and k.lower() != "x-forwarded-for"]
    headers.append(("x-forwarded-for", forwarded_for(request.headers, peer)))
    if not request.headers.get("x-forwarded-proto"):
        headers.append(("x-forwarded-proto", request.url.scheme))

    body = request.stream() if request.method not in ("GET", "HEAD", "OPTIONS") else None
    target = client
    upstream = target.build_request(request.method, path, params=request.url.query or None, headers=headers, content=body)
    try:
        r = await target.send(upstream, stream=True)
    except httpx.HTTPError:
        return PlainTextResponse("Vaidyx-TB is restarting. Try again in a minute.", status_code=502)
    resp = StreamingResponse(r.aiter_raw(), status_code=r.status_code, background=BackgroundTask(r.aclose))
    resp.raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1"))
                        for k, v in r.headers.multi_items() if k.lower() not in HOP_RESP]
    return resp


def origin_matches_host(headers) -> bool:
    """The browser's Origin must name the public host (cross-site WebSocket hijacking guard)."""
    origin = headers.get("origin") or ""
    host = headers.get("host") or ""
    return bool(origin) and bool(host) and origin.split("://", 1)[-1].rstrip("/").lower() == host.lower()


async def ws_handle(ws: WebSocket):
    path = ws.url.path
    if not has_secret(ws.headers) or not same_path(ws.scope, path) or not path_safe(path) or not WS_PATHS.match(path) or not origin_matches_host(ws.headers):
        await ws.close(code=1008)
        return
    peer = ws.client.host if ws.client else "unknown"
    extra = [("X-Forwarded-For", forwarded_for(ws.headers, peer)), ("X-Forwarded-Proto", "https")]
    if ws.headers.get("cookie"):
        extra.append(("Cookie", ws.headers["cookie"]))
    url = UPSTREAM.replace("http://", "ws://", 1) + path + (f"?{ws.url.query}" if ws.url.query else "")
    try:
        up = await websockets.connect(url, additional_headers=extra, open_timeout=10, ping_interval=None, max_size=2**22)
    except Exception:
        await ws.close(code=1011)
        return
    await ws.accept()

    async def browser_to_app():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("text") is not None:
                await up.send(msg["text"])
            elif msg.get("bytes") is not None:
                await up.send(msg["bytes"])

    async def app_to_browser():
        async for data in up:
            if isinstance(data, str):
                await ws.send_text(data)
            else:
                await ws.send_bytes(data)

    tasks = [asyncio.create_task(browser_to_app()), asyncio.create_task(app_to_browser())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        code = up.close_code or 1000
        with contextlib.suppress(Exception):
            await up.close()
        with contextlib.suppress(Exception, WebSocketDisconnect):
            await ws.close(code=code if 1000 <= code < 5000 and code not in (1005, 1006, 1015) else 1000)


METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@contextlib.asynccontextmanager
async def lifespan(_app):
    yield
    await client.aclose()


app = Starlette(routes=[WebSocketRoute("/{path:path}", ws_handle), Route("/{path:path}", handle, methods=METHODS)],
                lifespan=lifespan)
