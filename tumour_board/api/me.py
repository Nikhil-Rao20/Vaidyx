"""The signed-in person (18 Oct 2026, new interface): GET /me, the password change, the profile, and the activity log.

GET /me tells the interface who is signed in and what it holds: the Tumour Board roles (org.roles), the primary role that picks the
start page, whether the first password must still be changed, the profile (profiles.py), the counts for the top bar (unread
notifications, what waits for the person, the open requests of its departments), the hospital, the features the server has
(video, push) and the Case Files the doctor opened read-only with a reason (break_glass, night-v3 item 1.9). POST /me/password
changes the password through the Vaidyx login system (which clears the must-change flag); PUT /me/profile saves the profile;
GET /me/activity lists the person's own audited actions across the Case Files, the organisation and the board sessions;
GET /activity is the whole log for the auditor, the MDT Coordinator and the root admin. No model calls."""
import importlib.util, os
from pathlib import Path

from fastapi import Request

from tumour_board import access, board, config, notify, org, profiles, proposals, store
from tumour_board.api.common import RateLimit, auth_manager, body, fail, make_router, need, roles

router = make_router()
SESSION_COOKIE = "vaidyx_session"  # the main app's session cookie (core/auth.py)
PASSWORD_LIMIT = RateLimit(5, 15 * 60)
ACTIVITY_CAP = 200
FULL_LOG_CAP = 1000
PRIMARY_ORDER = ("treating", "resident", "supporting", "coordinator", "dept_admin", "root_admin", "auditor", "outside_expert")


def primary_role(r: dict) -> str:
    """The role that picks the start page: treating (a consultant of a treating department), resident, supporting, coordinator,
    dept_admin, root_admin (the Vaidyx admin counts here: it manages, never treats), auditor, outside_expert, else none."""
    if not isinstance(r, dict) or r.get("disabled"):
        return "none"
    if r.get("treating"):
        return "treating"
    if r.get("resident"):
        return "resident"
    if r.get("supporting"):
        return "supporting"
    if r.get("coordinator"):
        return "coordinator"
    if r.get("admin_of"):
        return "dept_admin"
    if r.get("root_admin") or r.get("vaidyx_admin"):
        return "root_admin"
    if r.get("auditor"):
        return "auditor"
    if r.get("outside_expert"):
        return "outside_expert"
    return "none"


def features() -> dict:
    """What this server offers the interface: video when the LiveKit keys exist, push when pywebpush is installed and the VAPID keys exist."""
    root = Path(config.DATA_ROOT)
    return {"video": (root / "livekit.json").exists(),
            "push": importlib.util.find_spec("pywebpush") is not None and (root / "push_keys.json").exists()}


def _password_min() -> int:
    try:
        from src.constants import PASSWORD_MIN_LENGTH
        return int(PASSWORD_MIN_LENGTH)
    except Exception:
        return 8


def _must_change(mgr, user: str) -> bool:
    fn = getattr(mgr, "must_change_password", None)
    try:
        return bool(fn(user)) if callable(fn) else False
    except Exception:
        return False


def public_roles(r: dict) -> dict:
    return {"admin": bool(r.get("admin")), "vaidyx_admin": bool(r.get("vaidyx_admin")), "root_admin": bool(r.get("root_admin")), "coordinator": bool(r.get("coordinator")),
            "auditor": bool(r.get("auditor")), "departments": dict(r.get("departments") or {}), "treating": sorted(r.get("treating") or {}),
            "supporting": sorted(r.get("supporting") or {}), "resident": sorted(r.get("resident") or {}), "admin_of": list(r.get("admin_of") or []),
            "outside_expert": bool(r.get("outside_expert")), "disabled": bool(r.get("disabled")), "known": bool(r.get("known")),
            "expired": bool(r.get("expired")), "end_date": r.get("end_date") or ""}


def counts(r: dict) -> dict:
    """The top bar's numbers: unread notifications, what waits for this person (a consultant: residents' proposals, join requests and
    confirmations; a resident: its returned proposals), and the open requests of the person's departments."""
    waiting = 0
    if r.get("treating"):
        waiting = len(proposals.waiting_for(r))
    elif r.get("resident"):
        waiting = sum(1 for p in proposals.mine(r) if p.get("status") == proposals.RETURNED)
    open_requests = 0
    if r.get("departments") or r.get("coordinator"):
        try:
            open_requests = int(notify.inbox(r).get("open") or 0)
        except Exception:
            open_requests = 0
    return {"unread": notify.unread_count(r) if r.get("known") else 0, "waiting_for_me": waiting, "open_requests": open_requests}


@router.get("/me")
async def me(request: Request):
    r = roles(request)
    mgr = getattr(request.app.state, "auth_manager", None)
    u = r.get("user") or ""
    prof = profiles.get(u)
    doctor = profiles.is_doctor(r)
    h = org.hospital()
    return {"user": u, "display_name": prof.get("display_name") or org.display_name(u), "roles": public_roles(r), "primary_role": primary_role(r),
            "must_change_password": _must_change(mgr, u), "profile": {k: prof.get(k) for k in profiles.FIELDS},
            "setup_needed": not profiles.setup_complete(u, doctor), "counts": counts(r),
            "hospital": {"name": h.get("name") or "", "level": h.get("level") or "", "pmjay_empanelled": bool(h.get("pmjay_empanelled", True))},
            "features": features(), "departments": [{"id": d["id"], "name": d["name"], "group": d.get("group"), "role": d.get("role")} for d in org.my_departments(r)]
            if not r.get("admin") else [],
            "break_glass": break_glass_mine(r)}


def break_glass_mine(r: dict) -> list:
    """The doctor's open windows on Case Files opened with a reason (night-v3 item 1.9): the page shows "Read-only until ..." on them."""
    if not access.placed_doctor(r):
        return []
    return [{k: w.get(k) for k in ("case_id", "until", "reason", "via")} for w in access.doctor_windows(r.get("user") or "")]


@router.post("/me/password")
async def change_password(request: Request):
    """{current_password, new_password}: through the Vaidyx login system, which clears the must-change flag. Rate limited (5 per 15 min)."""
    r = roles(request)
    u = r.get("user") or ""
    if not u:
        fail(400, "No login to change the password of.", "no_login")
    PASSWORD_LIMIT.check(u, "Too many password attempts. Wait 15 minutes and try again.")
    b = await body(request)
    cur, new = str(b.get("current_password") or ""), str(b.get("new_password") or "")
    n = _password_min()
    if len(new) < n:
        fail(400, f"The new password needs at least {n} characters.", "weak_password")
    if new == cur:
        fail(400, "The new password must differ from the current one.", "weak_password")
    if new.lower() in (u.lower(), u.split("@")[0].lower()):
        fail(400, "The new password must not be your login name.", "weak_password")
    mgr = auth_manager(request)
    try:
        ok = bool(mgr.change_password(u, cur, new))
    except Exception:
        ok = False
    if not ok:
        fail(400, "The current password is not right.", "wrong_password")
    ended = 0
    revoke = getattr(mgr, "revoke_user_sessions", None)
    if callable(revoke):  # every other session of this login ends with the old password (security review #4); this one stays
        try:
            ended = int(revoke(u, except_token=request.cookies.get(SESSION_COOKIE)) or 0)
        except Exception:
            ended = 0
    org.audit("password_changed", u, username=u, other_sessions_ended=ended)
    return {"ok": True, "must_change_password": _must_change(mgr, u), "other_sessions_ended": ended}


@router.put("/me/profile")
async def put_profile(request: Request):
    """{display_name?, title?, registration_no?, phone?, phone_visible?, photo?, theme?, text_size?, start_page?, saved_filters?} -> profile."""
    r = roles(request)
    u = r.get("user") or ""
    if not u:
        fail(400, "No login to save the profile of.", "no_login")
    b = await body(request)
    try:
        prof = profiles.update(u, b, doctor=profiles.is_doctor(r), by=u)
    except ValueError as e:
        fail(400, str(e), "bad_profile")
    return {"profile": {k: prof.get(k) for k in profiles.FIELDS}, "setup_needed": not profiles.setup_complete(u, profiles.is_doctor(r)), "setup_complete": bool(prof.get("setup_complete"))}


@router.get("/me/profile")
async def get_profile(request: Request):
    r = roles(request)
    u = r.get("user") or ""
    prof = profiles.get(u)
    return {"profile": {k: prof.get(k) for k in profiles.FIELDS}, "setup_needed": not profiles.setup_complete(u, profiles.is_doctor(r))}


# ---- activity -------------------------------------------------------------------------------------------------------------------------

_DETAIL_KEYS = ("action", "requirement", "department", "type", "key", "reason", "note", "level", "to", "proposal", "username", "fields", "changes")
_SKIP_KINDS = {"org_saved"}


def _title(kind: str) -> str:
    return str(kind or "").replace("_", " ").strip().capitalize() or "Event"


def _detail(ev: dict) -> str:
    parts = []
    for k in _DETAIL_KEYS:
        v = ev.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (dict, list)):
            v = ", ".join(f"{a}: {b}" for a, b in v.items()) if isinstance(v, dict) else ", ".join(str(x) for x in v)
        parts.append(f"{k}: {str(v)[:120]}")
    return "; ".join(parts)[:400]


def _event(ev: dict, case_id: str | None, source: str) -> dict:
    return {"ts": ev.get("ts") or "", "kind": ev.get("kind") or "", "case_id": case_id or ev.get("case_id") or None, "by": ev.get("by") or "",
            "title": _title(ev.get("kind")), "detail": _detail(ev), "source": source}


def _events(user: str | None = None, case_id: str | None = None, per_file: int = 2000):
    """Every audited event the server holds (the Case Files, the organisation, the board sessions), newest first; the protected real
    Case File is never read. Filtered by user and Case File when given."""
    out = []
    base = Path(config.CASES_DIR)
    dirs = []
    if base.exists():
        dirs = [d for d in sorted(base.iterdir()) if d.is_dir() and d.name not in config.PROTECTED_CASES and (case_id is None or d.name == case_id)]
    for d in dirs:
        try:
            evs = store.read_audit(d.name, per_file)
        except (ValueError, OSError):
            continue
        for ev in evs:
            if isinstance(ev, dict) and (user is None or ev.get("by") == user):
                out.append(_event(ev, d.name, "case"))
    if case_id is None:
        for ev in org.read_audit(per_file):
            if ev.get("kind") in _SKIP_KINDS:
                continue
            if user is None or ev.get("by") == user:
                out.append(_event(ev, None, "organisation"))
    try:
        for ev in board.read_audit(per_file):
            if isinstance(ev, dict) and (user is None or ev.get("by") == user) and (case_id is None or ev.get("case_id") == case_id):
                out.append(_event(ev, ev.get("case_id"), "session"))
    except Exception:
        pass
    out.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)
    return out


@router.get("/me/activity")
async def my_activity(request: Request, limit: int = 100):
    """This person's own audited actions, newest first (at most 200)."""
    r = roles(request)
    u = r.get("user") or ""
    n = max(1, min(int(limit or 100), ACTIVITY_CAP))
    evs = _events(user=u) if u else []
    return {"events": evs[:n], "total": len(evs)}


@router.get("/activity")
async def activity(request: Request, case_id: str = "", user: str = "", limit: int = 100):
    """The whole log: the auditor, the MDT Coordinator and the root admin (read only). Reading it is itself recorded."""
    r = roles(request)
    try:
        cid = store.safe_id(case_id) if case_id else None
    except ValueError:
        fail(400, "That is not a Case File id.", "bad_case")
    if r.get("vaidyx_admin"):  # the Vaidyx admin: one Case File, inside its break-glass window only (security review #2)
        from tumour_board import access
        if not (cid and access.break_glass_window(r.get("user") or "", cid)):
            fail(403, "A Vaidyx admin reads the activity of one Case File, inside a break-glass window on it.", "forbidden")
    else:
        need(r, "read_audit")
    n = max(1, min(int(limit or 100), FULL_LOG_CAP))
    evs = _events(user=(user or None), case_id=cid)
    org.audit("activity_read", r.get("user") or "", case_id=cid or "", user=user or "", count=min(n, len(evs)))
    return {"events": evs[:n], "total": len(evs)}
