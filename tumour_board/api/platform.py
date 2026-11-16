"""The Vaidyx console's API (admin consoles, 16 Nov 2026, docs/admin-console/DESIGN.md 5.3, API_FIELDS.md): GET/POST /platform/*.

The Vaidyx admin only (403 for anyone else, a hospital admin included). These routes work across hospitals and ignore the hospital the
Vaidyx admin is acting in (X-TB-Hospital): the service (tumour_board/platform_admin.py) enters each hospital itself. Counts and names of
people only, never patient data (D5). A first password comes back once as `password_once` (and inside a mail draft) and is never
logged or audited (D10). Every change is audited in the platform audit (D11).

POST /platform/acting {hospital} and DELETE /platform/acting: the Vaidyx admin starts (or stops) working inside a hospital. Every fetch
names it in the X-TB-Hospital header; what the browser loads without fetch (links to originals and PDFs, image previews, the image
viewer, event streams) cannot, so the choice is also kept in the httpOnly, SameSite=Strict cookie tb_acting_hospital, which the request
hook and the sockets honour for a Vaidyx admin only (the header wins). Starting is audited once as `acting_in`."""
from fastapi import Request, Response

from tumour_board import platform_admin as svc
from tumour_board.api.common import body, fail, make_router, roles

router = make_router()
NOT_YOURS = "Only the Vaidyx admin opens the Vaidyx console."


def _admin(request: Request) -> dict:
    r = roles(request)
    if not r.get("vaidyx_admin"):
        fail(403, NOT_YOURS, "forbidden")
    return r


def _mgr(request: Request):
    return getattr(request.app.state, "auth_manager", None)


def _url(request: Request) -> str:
    from tumour_board.api.setup import login_url
    return login_url(request)


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except svc.PlatformError as e:
        fail(e.status, str(e), e.code)


@router.get("/platform/overview")
async def overview(request: Request):
    _admin(request)
    return svc.overview(_mgr(request))


@router.get("/platform/hospitals")
async def hospitals_list(request: Request):
    _admin(request)
    return svc.list_rows(_mgr(request))


@router.post("/platform/hospitals")
async def hospital_create(request: Request):
    """{name, city?, state?, type?, level?, pmjay_empanelled?, demo_his?, admin{display_name, email}} ->
    {hospital, admin{username, password_once, mailto}}."""
    r = _admin(request); b = await body(request)
    return _run(svc.create_hospital, b, r["user"], _mgr(request), _url(request))


@router.get("/platform/hospitals/{hid}")
async def hospital_detail(hid: str, request: Request):
    _admin(request)
    return _run(svc.detail, hid, _mgr(request))


@router.put("/platform/hospitals/{hid}")
async def hospital_update(hid: str, request: Request):
    """{name?, city?, state?}"""
    r = _admin(request); b = await body(request)
    return {"ok": True, **_run(svc.update_hospital, hid, b, r["user"], _mgr(request))}


@router.post("/platform/hospitals/{hid}/status")
async def hospital_status(hid: str, request: Request):
    """{status: active | suspended, reason} (a suspension needs a reason of 3 to 300 characters; never the default hospital)."""
    r = _admin(request); b = await body(request)
    return {"ok": True, **_run(svc.set_status, hid, b, r["user"], _mgr(request))}


@router.post("/platform/hospitals/{hid}/admins")
async def admin_add(hid: str, request: Request):
    """{display_name, email} or {username} -> {username, created, password_once?, mailto?}"""
    r = _admin(request); b = await body(request)
    return {"ok": True, **_run(svc.add_admin, hid, b, r["user"], _mgr(request), _url(request))}


@router.delete("/platform/hospitals/{hid}/admins/{username}")
async def admin_remove(hid: str, username: str, request: Request):
    r = _admin(request)
    return _run(svc.remove_admin, hid, username, r["user"], _mgr(request))


@router.get("/platform/logins")
async def logins(request: Request, hospital: str = "", role: str = "", q: str = ""):
    _admin(request)
    return svc.logins(_mgr(request), hospital=hospital, role=role, q=q)


@router.post("/platform/logins/{username}/reset-password")
async def login_reset(username: str, request: Request):
    """-> {username, password_once, mailto}: a new first password, to be changed at the next sign-in."""
    r = _admin(request)
    return {"ok": True, **_run(svc.reset_password, username, r["user"], _mgr(request), _url(request))}


@router.post("/platform/logins/{username}/disable")
async def login_disable(username: str, request: Request):
    r = _admin(request)
    return _run(svc.set_disabled, username, True, r["user"], _mgr(request))


@router.post("/platform/logins/{username}/enable")
async def login_enable(username: str, request: Request):
    r = _admin(request)
    return _run(svc.set_disabled, username, False, r["user"], _mgr(request))


@router.get("/platform/activity")
async def activity(request: Request, hospital: str = "", kind: str = "", limit: int = 200):
    _admin(request)
    return svc.activity(hospital=hospital, kind=kind, limit=limit)


def _session_key(request: Request, user: str) -> str:
    from tumour_board.api.common import _token_key
    tok = request.cookies.get("vaidyx_session")
    return _token_key(tok) if tok else user


@router.post("/platform/acting")
async def acting_start(request: Request, response: Response):
    """{hospital}: the Vaidyx admin works inside this hospital (the cookie for non-fetch requests; audited as acting_in)."""
    from tumour_board import hospitals
    r = _admin(request); b = await body(request)
    hid = str(b.get("hospital") or "").strip().lower()
    if not hospitals.known(hid):
        fail(404, "That hospital does not exist (any more). Choose another in the Vaidyx console.", "hospital_unknown")
    svc.note_acting(_session_key(request, r["user"]), r["user"], hid)
    response.set_cookie(hospitals.ACTING_COOKIE, hid, httponly=True, samesite="strict", path="/", secure=request.url.scheme == "https")
    h = hospitals.get(hid)
    return {"ok": True, "acting_hospital": {"id": hid, "name": h["name"], "status": h["status"]}}


@router.delete("/platform/acting")
async def acting_stop(request: Request, response: Response):
    """Back to the Vaidyx console: the cookie is cleared (nothing to audit: no hospital is entered)."""
    from tumour_board import hospitals
    r = _admin(request)
    svc.note_acting(_session_key(request, r["user"]), r["user"], None)
    response.delete_cookie(hospitals.ACTING_COOKIE, path="/", httponly=True, samesite="strict", secure=request.url.scheme == "https")
    return {"ok": True, "acting_hospital": None}
