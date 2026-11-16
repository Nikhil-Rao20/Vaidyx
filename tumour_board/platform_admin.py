"""The Vaidyx console and the Hospital console, the service behind tumour_board/api/platform.py and api/hospital_admin.py (admin consoles,
16 Nov 2026, docs/admin-console/DESIGN.md 5.3 and API_FIELDS.md).

Plain functions, no request: the routes check who asks and hand in the login system (`mgr`). Every function that reads or changes one
hospital runs inside config.use_hospital(id), so the acting hospital of the request (X-TB-Hospital) never matters here.

Counts only (D5): no patient name, UHID, identifier or report text ever leaves these functions. How each count is made:
- Case Files (Vaidyx console): every case folder with a case.json; archived ones are left out; "decided" = a board record exists for the
  current listing (cases_list._decided, the rule of the Case File list); "open" = the others; total = open + decided.
- Case Files by status (Hospital console): the status word of the Case File list (cases_list.status_of) for a neutral reader, so
  "needs_me" reads needs_team; archived left out; keys draft, needs_team, waiting_department, ready, scheduled, decided.
- People: the logins placed in that hospital's org.json (users, plus hospital admins listed only in admins). A login holding several
  roles counts once in each role. Never signed in = the first password was not changed yet (the login system keeps no sign-in time).
- Meetings in the next 7 days: board sessions planned or running, not cancelled, dated today to today + 7.
- Open requests: Pre-Authorization requests and board actions (notify.SOURCES) that were sent and are not completed, in Case Files that
  are not archived.
- Set-up: the five steps of the set-up wizard (api/setup.py _done and _summaries).
- Hospital system: not_set (no connection, kind none, or switched off), not_tested (configured, never tested), connected (the last test
  answered), failing (the last test failed); `demo` when it points at the synthetic demo hospital system.
- Last activity: the newest time in the hospital's org_audit.jsonl (only its tail is read).

A hospital in the registry whose folder is missing (never expected) shows zero everywhere and is never written to by a read.
"""
import copy, json, os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from . import accounts, config, hospitals, org

STEPS_TOTAL = 5
NAME_RANGE = (3, 120)
PLACE_MAX = 60
REASON_RANGE = (3, 300)
DISPLAY_MAX = 80
HOSPITAL_TYPES = ("public", "private")
DEFAULT_SUSPEND = "The default hospital cannot be suspended: it holds the Vaidyx admin's own login and the demo."
LAST_ADMIN = "This is the last hospital admin of an active hospital. Add another hospital admin first, or suspend the hospital."
VAIDYX_ADMIN_HERE = "A Vaidyx admin (the server administrator) is not changed here; it is managed in the main app."
PLATFORM_KINDS = ("hospital_created", "hospital_updated", "hospital_suspended", "hospital_reactivated", "admin_added", "admin_removed",
                  "password_reset", "login_disabled", "login_enabled", "acting_in")
# the organisation events the consoles show (people, set-up, accounts, hospital system); never a clinical event
ORG_KINDS = ("hospital_created", "admin_added", "account_created", "password_reset", "password_changed", "account_placed", "account_roles_changed",
             "account_unplaced", "root_admins_changed", "setup_step", "his_test", "his_settings_saved", "hospital_changed", "first_setup",
             "first_setup_cleared", "hospital_logo", "hospital_logo_removed", "routes_changed")


class PlatformError(ValueError):
    """A refused console action: `status` is the HTTP status, the message is plain text, `code` a short word for the interface."""
    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


# ---- small helpers -------------------------------------------------------------------------------------------------------------

def _folder(hid) -> bool:
    try:
        return config.root_for(hid).is_dir()
    except ValueError:
        return False


def _text(v, field: str, lo: int = 0, hi: int = PLACE_MAX, label: str = "") -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise PlatformError(400, f"The {label or field} must be text.", "bad_value")
    v = " ".join(v.split())
    if lo and len(v) < lo:
        raise PlatformError(400, f"The {label or field} needs at least {lo} characters." if v else f"Give the {label or field}.", "bad_value")
    if len(v) > hi:
        raise PlatformError(400, f"The {label or field} is too long (at most {hi} characters).", "bad_value")
    return v


def _today() -> date:
    return date.today()


def _users(o: dict) -> dict:
    return {u: v for u, v in ((o or {}).get("users") or {}).items() if isinstance(v, dict)}


def _people_logins(o: dict) -> list[str]:
    """Every login placed in this hospital: the users of org.json and the hospital admins (who may be listed only in admins)."""
    return sorted(set(_users(o)) | {a for a in (o or {}).get("admins") or [] if isinstance(a, str)})


def _vaidyx_admins(mgr) -> list[str]:
    users = getattr(mgr, "users", None) or {}
    return sorted(u for u in users if accounts.is_vaidyx_admin(mgr, u))


def _name(u: str) -> str:
    """The display name of a login of the current hospital (profile, else org.json, else the login)."""
    try:
        from . import profiles
        return profiles.display_name(u)
    except Exception:
        return org.display_name(u)


def _tail_ts(p: Path, chunk: int = 8192) -> str | None:
    """The newest `ts` in a JSON-lines audit file, reading only its last few kilobytes."""
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - chunk))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    best = None
    for line in reversed(lines):
        try:
            ts = json.loads(line).get("ts")
        except (ValueError, AttributeError):
            continue
        if ts and (best is None or str(ts) > best):
            best = str(ts)
            break
    return best


# ---- one hospital (run inside config.use_hospital) -----------------------------------------------------------------------------

def _origin(url: str) -> str:
    sp = urlsplit(url or "")
    return f"{sp.scheme}://{sp.netloc}".lower()


def _builtin_demo() -> dict:
    """The built-in demo hospital system settings (his_client's defaults of the hospital "default")."""
    from . import his_client
    with config.use_hospital(config.DEFAULT_HOSPITAL):
        return his_client._default_settings()


def is_demo_his(cfg: dict) -> bool:
    """True when HIS settings point at the synthetic demo hospital system (his_mock): a FHIR connection on this server (loopback) at the
    demo's port."""
    from . import his_client
    if not isinstance(cfg, dict) or str(cfg.get("kind") or "fhir") != "fhir":
        return False
    demo_url = his_client.DEFAULT_URL
    url = str(cfg.get("url") or "")
    host = (urlsplit(url).hostname or "").lower()
    same = _origin(url) == _origin(demo_url) or (host in his_client.LOOPBACK and urlsplit(url).port == urlsplit(demo_url).port)
    return bool(url) and same


def his_state(o: dict | None = None) -> dict:
    """{state, url_set, tested_at, ok, demo} of the current hospital's hospital system (never a token or a server path)."""
    from . import his_client
    o = o if o is not None else org.load()
    try:
        cfg = his_client.settings()
    except Exception:
        cfg = {}
    kind = str(cfg.get("kind") or "none")
    configured = bool(cfg.get("enabled")) and kind != "none" and (kind != "fhir" or bool(str(cfg.get("url") or "").strip()))
    h = (o or {}).get("hospital") or {}
    test = h.get("his_test") if isinstance(h.get("his_test"), dict) else {}
    if not configured:
        state = "not_set"
    elif not test:
        state = "not_tested"
    else:
        state = "connected" if test.get("ok") else "failing"
    return {"state": state, "url_set": configured, "tested_at": test.get("at") or None, "ok": bool(test.get("ok")) if test else None,
            "demo": configured and is_demo_his(cfg)}


def _case_files():
    """(case.json, state.json) of every Case File of the current hospital (a broken file is skipped)."""
    from . import store
    root = Path(config.CASES_DIR)
    if not root.is_dir():
        return
    for d in sorted(root.iterdir()):
        try:
            c = store._read_json(d / "case.json")
            if not isinstance(c, dict) or not c.get("case_id"):
                continue
            st = store._read_json(d / "state.json", {}) or {}
        except (OSError, ValueError):
            continue
        yield c, (st if isinstance(st, dict) else {})


def case_counts() -> dict:
    """{open, decided, total} of the current hospital (archived left out; see the module docstring)."""
    from . import access
    from .api import cases_list
    opened = decided = 0
    for c, st in _case_files():
        if access.is_archived(c):
            continue
        try:
            done = cases_list._decided(c, st)
        except Exception:
            done = False
        decided += 1 if done else 0
        opened += 0 if done else 1
    return {"open": opened, "decided": decided, "total": opened + decided}


BY_STATUS = ("draft", "needs_team", "waiting_department", "ready", "scheduled", "decided")


def cases_by_status() -> dict:
    """{by_status{draft, needs_team, waiting_department, ready, scheduled, decided}, total} of the current hospital (archived left out)."""
    from . import access, store
    from .api import cases_list
    out = {k: 0 for k in BY_STATUS}
    try:
        sched = cases_list._scheduled()
    except Exception:
        sched = {}
    for c, st in _case_files():
        if access.is_archived(c):
            continue
        try:
            key = cases_list.status_of(c, st, store.list_docs(c["case_id"]), {}, sched)["key"]
        except Exception:
            key = "draft"
        key = "needs_team" if key == "needs_me" else key
        out[key if key in out else "draft"] += 1
    return {"by_status": out, "total": sum(out.values())}


def meetings_soon(days: int = 7) -> dict:
    """{next_7_days, upcoming[{id, title, date}]}: board sessions planned or running, not cancelled, dated today to today + `days`."""
    from . import board
    today = _today()
    lo, hi = today.isoformat(), (today + timedelta(days=days)).isoformat()
    try:
        rows = board.all_sessions()
    except Exception:
        rows = []
    soon = [s for s in rows if isinstance(s, dict) and s.get("status") in ("planned", "in_session") and not s.get("cancelled")
            and lo <= str(s.get("date") or "")[:10] <= hi]
    soon.sort(key=lambda s: (str(s.get("date") or ""), str(s.get("time") or "")))
    return {"next_7_days": len(soon), "upcoming": [{"id": s.get("id"), "title": str(s.get("title") or "Tumour Board"), "date": str(s.get("date") or "")[:10],
                                                   "time": str(s.get("time") or "")} for s in soon[:5]]}


def open_requests() -> int:
    """Requests sent and not completed (Pre-Authorization requests and board actions) in the Case Files that are not archived."""
    from . import access, notify
    n = 0
    for c, st in _case_files():
        if access.is_archived(c):
            continue
        for a in st.get("actions") or []:
            if isinstance(a, dict) and (a.get("source") or "pre_authorization") in notify.SOURCES \
                    and str(a.get("status") or "pending") not in ("completed", notify.UNSENT):
                n += 1
    return n


def setup_steps(o: dict | None = None, mgr=None) -> dict:
    """{steps[{id, label, done, summary}], done, total} of the set-up wizard of the current hospital."""
    from .api import setup
    o = o if o is not None else org.load()
    done, summ = setup._done(o), setup._summaries(o, mgr)
    steps = [{"id": s, "label": setup.STEP_LABELS[s], "done": bool(done[s]), "summary": summ[s]} for s in setup.STEPS]
    return {"steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps)}


def role_words(u: str, o: dict, vaidyx_admin: bool = False) -> list[str]:
    """The console's role words of one login: hospital_admin, doctor, head, resident, coordinator, dept_admin, auditor, guest."""
    if vaidyx_admin:
        return ["vaidyx_admin"]
    v = _users(o).get(u) or {}
    places = set((v.get("departments") or {}).values()) if isinstance(v.get("departments"), dict) else set()
    places = {org.ROLE_SYNONYMS.get(p, p) for p in places}
    out = []
    if u in ((o or {}).get("admins") or []):
        out.append("hospital_admin")
    if "member" in places:
        out.append("doctor")
    if "head" in places:
        out.append("head")
    if "resident" in places:
        out.append("resident")
    if v.get("coordinator"):
        out.append("coordinator")
    if v.get("admin_of"):
        out.append("dept_admin")
    if v.get("auditor"):
        out.append("auditor")
    if v.get("outside_expert") or v.get("real_data"):
        out.append("guest")
    return out


PEOPLE_KEYS = ("doctors", "heads", "residents", "coordinators", "dept_admins", "hospital_admins", "auditors", "guests", "disabled", "never_signed_in")
_WORD_KEY = {"doctor": "doctors", "head": "heads", "resident": "residents", "coordinator": "coordinators", "dept_admin": "dept_admins",
             "hospital_admin": "hospital_admins", "auditor": "auditors", "guest": "guests"}


def people_by_role(o: dict, mgr=None) -> dict:
    out = {k: 0 for k in PEOPLE_KEYS}
    users = _users(o)
    for u in _people_logins(o):
        for w in role_words(u, o):
            out[_WORD_KEY[w]] += 1
        if (users.get(u) or {}).get("disabled"):
            out["disabled"] += 1
        if mgr is not None and accounts.must_change(mgr, u):
            out["never_signed_in"] += 1
    return out


def last_activity() -> str | None:
    return _tail_ts(Path(config.DATA_ROOT) / "org_audit.jsonl")


def hospital_row(h: dict, mgr=None) -> dict:
    """One row of the Vaidyx console (API_FIELDS.md "Hospital row"): counts and names of people only."""
    row = {"id": h["id"], "name": h["name"], "city": h.get("city") or "", "state": h.get("state") or "", "status": h["status"],
           "status_reason": h.get("suspended_reason") or "", "created": h.get("created_at") or None, "default": bool(h.get("default")),
           "type": "", "level": "", "pmjay_empanelled": False, "admins": 0, "people": 0,
           "case_files": {"open": 0, "decided": 0, "total": 0}, "setup": {"done": 0, "total": STEPS_TOTAL},
           "his": {"state": "not_set", "url_set": False, "tested_at": None, "ok": None, "demo": False}, "last_activity": None,
           "meetings_next_7_days": 0, "admin_logins": [], "admins_never_signed_in": []}
    if not _folder(h["id"]):
        return row
    with config.use_hospital(h["id"]):
        o = org.load()
        hh = o.get("hospital") or {}
        st = setup_steps(o, mgr)
        admins = [a for a in o.get("admins") or [] if isinstance(a, str)]
        row.update({"type": hh.get("type") or "", "level": hh.get("level") or "", "pmjay_empanelled": bool(hh.get("pmjay_empanelled", True)),
                    "admins": len(admins), "people": len(_people_logins(o)), "case_files": case_counts(),
                    "setup": {"done": st["done"], "total": st["total"]}, "his": his_state(o), "last_activity": last_activity(),
                    "meetings_next_7_days": meetings_soon()["next_7_days"], "admin_logins": admins,
                    "admins_never_signed_in": [_name(a) for a in admins if mgr is not None and accounts.must_change(mgr, a)]})
    return row


def _public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("admin_logins", "admins_never_signed_in", "meetings_next_7_days")}


# ---- the Vaidyx console ---------------------------------------------------------------------------------------------------------

def hospital_rows(mgr=None) -> list[dict]:
    return [hospital_row(h, mgr) for h in hospitals.list_hospitals()]


def platform_attention(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["status"] != "active":
            continue
        base = {"hospital": r["id"], "hospital_name": r["name"]}
        if not r["admins"]:
            out.append({**base, "kind": "no_admin", "text": "No hospital admin yet"})
        if r["setup"]["done"] < r["setup"]["total"]:
            out.append({**base, "kind": "setup_unfinished", "text": f"Set-up {r['setup']['done']} of {r['setup']['total']} steps done"})
        if r["his"]["state"] == "failing":
            out.append({**base, "kind": "his_failing", "text": "Hospital system did not answer at the last test"})
        for n in r["admins_never_signed_in"]:
            out.append({**base, "kind": "admin_never_signed_in", "text": f"{n} has not signed in yet"})
    return out


def overview(mgr=None) -> dict:
    rows = hospital_rows(mgr)
    vx = _vaidyx_admins(mgr)
    tiles = {"hospitals_active": sum(1 for r in rows if r["status"] == "active"),
             "hospitals_suspended": sum(1 for r in rows if r["status"] == "suspended"),
             "logins": sum(r["people"] for r in rows) + len(vx), "hospital_admins": sum(r["admins"] for r in rows),
             "case_files": sum(r["case_files"]["total"] for r in rows), "meetings_next_7_days": sum(r["meetings_next_7_days"] for r in rows),
             "setup_complete": sum(1 for r in rows if r["setup"]["done"] >= r["setup"]["total"]),
             "his_connected": sum(1 for r in rows if r["his"]["state"] == "connected")}
    return {"tiles": tiles, "hospitals": [_public_row(r) for r in rows], "attention": platform_attention(rows)}


def list_rows(mgr=None) -> dict:
    return {"hospitals": [_public_row(r) for r in hospital_rows(mgr)]}


def _get(hid) -> dict:
    h = hospitals.get(str(hid or "").strip().lower())
    if h is None:
        raise PlatformError(404, "No such hospital.", "not_found")
    return h


def detail(hid, mgr=None) -> dict:
    h = _get(hid)
    row = hospital_row(h, mgr)
    out = {"hospital": _public_row(row), "admins": [], "people_by_role": {k: 0 for k in PEOPLE_KEYS},
           "setup": {"steps": [], "done": 0, "total": STEPS_TOTAL}, "his": row["his"], "recent": [],
           "counts": {"people": row["people"], "case_files_open": row["case_files"]["open"], "case_files_decided": row["case_files"]["decided"],
                      "case_files_total": row["case_files"]["total"], "meetings_next_7_days": row["meetings_next_7_days"], "open_requests": 0}}
    if not _folder(h["id"]):
        return out
    with config.use_hospital(h["id"]):
        o = org.load()
        users = _users(o)
        out["admins"] = [{"username": a, "display_name": _name(a), "disabled": bool((users.get(a) or {}).get("disabled")),
                          "must_change_password": accounts.must_change(mgr, a) if mgr is not None else False, "last_sign_in": None}
                         for a in row["admin_logins"]]
        out["people_by_role"] = people_by_role(o, mgr)
        out["setup"] = setup_steps(o, mgr)
        out["counts"]["open_requests"] = open_requests()
        org_events = org_recent(limit=15)
    pevs = [e for e in hospitals.read_audit(limit=50, hospital=h["id"])
            if e.get("kind") in ("hospital_updated", "hospital_suspended", "hospital_reactivated", "acting_in")]
    names = _by_names(pevs)
    plat = [platform_event(e, names) for e in pevs]
    out["recent"] = sorted(org_events + plat, key=lambda e: str(e.get("ts") or ""), reverse=True)[:15]
    return out


def _admin_body(a) -> tuple[str, str]:
    if not isinstance(a, dict):
        raise PlatformError(400, "Give the first hospital admin: {display_name, email}.", "bad_value")
    name = _text(a.get("display_name"), "display_name", lo=1, hi=DISPLAY_MAX, label="admin's name")
    email = str(a.get("email") or "").strip().lower()
    if not accounts.is_email(email):
        raise PlatformError(400, "Give the admin's email address; it is their login name.", "bad_email")
    return name, email


def _check_new_login(mgr, email: str) -> None:
    if mgr is None:
        raise PlatformError(503, "The Vaidyx login system is not available; logins cannot be made right now.", "no_login_system")
    if accounts.account_exists(mgr, email):
        if accounts.is_vaidyx_admin(mgr, email):
            raise PlatformError(409, "That login is a Vaidyx admin (server administrator); give another email for the hospital admin.", "vaidyx_admin")
        raise PlatformError(409, "That login already exists in another hospital. One login belongs to one hospital: give another email.", "login_taken")


def _limits() -> dict:
    from .api import setup
    return setup._limits()


def _make_admin(mgr, by: str, email: str, display_name: str, hospital_name: str, url: str) -> dict:
    """Inside the current hospital: a hospital admin from an email. A new login gets a generated first password (must change) shown
    once (`password_once`) and in a mail draft; an existing login of this hospital is promoted (no password). Never a Vaidyx admin."""
    if mgr is None:
        raise PlatformError(503, "The Vaidyx login system is not available; logins cannot be made right now.", "no_login_system")
    u = accounts.clean_username(email)
    pw, flagged = "", False
    if not accounts.account_exists(mgr, u):
        pw = accounts.generate_password()
        made = accounts.ensure_account(mgr, u, pw, by, **_limits())
        if made["created"]:
            flagged = accounts._first_password(mgr, u, pw, by)
        else:
            pw = ""
    out = accounts.create_account(mgr, by, u, None, display_name=display_name, root_admin=True, hospital=hospital_name, url=url, **_limits())
    res = {"username": out["username"], "created": bool(pw), "must_change_password": flagged if pw else accounts.must_change(mgr, u)}
    if pw:
        res["password_once"] = pw
        res["mailto"] = accounts.mailto_for(email, u, pw, url=url, hospital=hospital_name)
    return res


def create_hospital(body: dict, by: str, mgr=None, url: str = accounts.LOGIN_URL) -> dict:
    """POST /platform/hospitals: register the hospital (its folder, the default departments), set its details, make the first hospital
    admin (a plain login, first password once) and, when asked, point it at the synthetic demo hospital system. Audited in the platform
    audit and in the new hospital's organisation audit; the password is never logged or audited."""
    if not isinstance(body, dict):
        raise PlatformError(400, "The request body must be a JSON object.", "bad_json")
    name = _text(body.get("name"), "name", lo=NAME_RANGE[0], hi=NAME_RANGE[1], label="hospital's name")
    city = _text(body.get("city"), "city")
    state = _text(body.get("state"), "state")
    typ = str(body.get("type") or "").strip().lower()
    if typ and typ not in HOSPITAL_TYPES:
        raise PlatformError(400, "The type is public or private.", "bad_value")
    level = str(body.get("level") or "essential").strip().lower()
    if level not in org.LEVELS:
        raise PlatformError(400, f"The NCG level is one of: {', '.join(org.LEVELS)}.", "bad_value")
    pmjay = body.get("pmjay_empanelled", True)
    demo = body.get("demo_his", False)
    if not isinstance(pmjay, bool) or not isinstance(demo, bool):
        raise PlatformError(400, "PM-JAY empanelled and the demo hospital system option are true or false.", "bad_value")
    admin_name, email = _admin_body(body.get("admin"))
    _check_new_login(mgr, email)
    try:
        h = hospitals.create(name, by=by, city=city, state=state)
    except hospitals.HospitalError as e:
        raise PlatformError(e.status, str(e), "bad_value")
    hid = h["id"]
    with config.use_hospital(hid):
        o = copy.deepcopy(org.load())
        o["hospital"].update({"name": name, "type": typ, "level": level, "pmjay_empanelled": pmjay})
        org.save(o, by)
        org.audit("hospital_created", by, hospital=hid, name=name, city=city, state=state, demo_his=demo)
        _write_his(by, demo)
        try:
            admin = _make_admin(mgr, by, email, admin_name, name, url)
        except accounts.AccountError as e:
            raise PlatformError(e.status, f"The hospital was added, but its first admin could not be made: {e} Add the admin from the hospital's page.", "admin_failed")
        org.audit("admin_added", by, hospital=hid, username=admin["username"], display_name=admin_name, created=admin["created"])
    hospitals.audit("admin_added", by, hospital=hid, username=admin["username"], display_name=admin_name, created=admin["created"])
    out = {"username": admin["username"], "password_once": admin.get("password_once", ""), "mailto": admin.get("mailto", ""),
           "must_change_password": admin["must_change_password"]}
    return {"hospital": _public_row(hospital_row(_get(hid), mgr)), "admin": out}


def _write_his(by: str, demo: bool) -> None:
    """The new hospital's his.json (current hospital): the demo hospital system (synthetic), copied from the default hospital when that
    one points at the demo (else the built-in demo address), or none at all (never the demo by accident). Every key is written
    explicitly (a hospital other than "default" has no defaults). Owner-only file; a token value is never copied (only the token file's
    path) and never logged."""
    from . import his_client
    if demo:
        with config.use_hospital(config.DEFAULT_HOSPITAL):
            src = his_client.settings()
        if not is_demo_his(src):
            src = _builtin_demo()
        d = {"kind": "fhir", "label": str(src.get("label") or his_client.DEFAULT_LABEL), "url": str(src.get("url") or his_client.DEFAULT_URL),
             "token": "", "token_file": str(src.get("token_file") or ""), "connector": "", "enabled": True,
             "pacs_url": str(src.get("pacs_url") or his_client.DEFAULT_PACS_URL)}
    else:
        d = {"kind": "none", "label": "", "url": "", "token": "", "token_file": "", "connector": "", "enabled": False, "pacs_url": ""}
    p = his_client.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, indent=1))
    os.replace(tmp, p)
    org.audit("his_settings_saved", by, his_kind=d["kind"], label=d["label"], url=d["url"], pacs_url=d["pacs_url"], token_file=d["token_file"],
              connector="", enabled=d["enabled"], has_token=bool(d["token"] or d["token_file"]), demo=demo)


def update_hospital(hid, body: dict, by: str, mgr=None) -> dict:
    """PUT /platform/hospitals/{id}: {name?, city?, state?}. The name of a hospital other than "default" is also written into its own
    set-up (org.json hospital.name, used in mail drafts and on its pages)."""
    h = _get(hid)
    if not isinstance(body, dict):
        raise PlatformError(400, "The request body must be a JSON object.", "bad_json")
    unknown = sorted(k for k in body if k not in ("name", "city", "state"))
    if unknown:
        raise PlatformError(400, f"Unknown field(s): {', '.join(unknown)}. Changeable here: name, city, state.", "bad_value")
    fields = {}
    if "name" in body:
        fields["name"] = _text(body["name"], "name", lo=NAME_RANGE[0], hi=NAME_RANGE[1], label="hospital's name")
        if h.get("default") and fields["name"] == h["name"]:
            fields.pop("name")
    for k in ("city", "state"):
        if k in body:
            fields[k] = _text(body[k], k)
    try:
        hospitals.update(h["id"], by, **fields)
    except hospitals.HospitalError as e:
        raise PlatformError(e.status, str(e), "bad_value")
    if "name" in fields and not h.get("default") and _folder(h["id"]):
        with config.use_hospital(h["id"]):
            o = copy.deepcopy(org.load())
            if o["hospital"].get("name") != fields["name"]:
                o["hospital"]["name"] = fields["name"]
                org.save(o, by)
    return {"hospital": _public_row(hospital_row(_get(h["id"]), mgr))}


def set_status(hid, body: dict, by: str, mgr=None) -> dict:
    """POST /platform/hospitals/{id}/status: {status: active | suspended, reason}. Any hospital but "default" (DEFAULT_SUSPEND)."""
    h = _get(hid)
    if not isinstance(body, dict):
        raise PlatformError(400, "The request body must be a JSON object.", "bad_json")
    status = str(body.get("status") or "").strip().lower()
    if status not in hospitals.STATUSES:
        raise PlatformError(400, "The status is active or suspended.", "bad_value")
    if h.get("default"):
        raise PlatformError(409, DEFAULT_SUSPEND, "default_hospital")
    reason = _text(body.get("reason"), "reason", lo=REASON_RANGE[0] if status == "suspended" else 0, hi=REASON_RANGE[1])
    try:
        hospitals.set_status(h["id"], status, by, reason=reason)
    except hospitals.HospitalError as e:
        raise PlatformError(e.status, str(e), "bad_value")
    return {"hospital": _public_row(hospital_row(_get(h["id"]), mgr))}


def add_admin(hid, body: dict, by: str, mgr=None, url: str = accounts.LOGIN_URL) -> dict:
    """POST /platform/hospitals/{id}/admins: {display_name, email} (a new login with a first password once, or an existing login of this
    hospital promoted) or {username} (an existing login of this hospital). A login of another hospital or a Vaidyx admin is refused."""
    h = _get(hid)
    if not isinstance(body, dict):
        raise PlatformError(400, "The request body must be a JSON object.", "bad_json")
    if not _folder(h["id"]):
        raise PlatformError(404, "This hospital's folder is missing; ask the server administrator.", "not_found")
    if mgr is None:
        raise PlatformError(503, "The Vaidyx login system is not available; logins cannot be made right now.", "no_login_system")
    if str(body.get("email") or "").strip():
        display_name, login = _admin_body(body)
    else:
        try:
            login = accounts.clean_username(body.get("username"))
        except accounts.AccountError as e:
            raise PlatformError(e.status, str(e), "bad_value")
        display_name = _text(body.get("display_name"), "display_name", hi=DISPLAY_MAX, label="name")
        if not accounts.account_exists(mgr, login):
            raise PlatformError(404, f"There is no login '{login}'. Give a name and an email to make a new one.", "not_found")
    if accounts.is_vaidyx_admin(mgr, login):
        raise PlatformError(409, "That login is a Vaidyx admin (server administrator); it is never made a hospital admin here.", "vaidyx_admin")
    with config.use_hospital(h["id"]):
        try:
            accounts.check_hospital(login, exists=accounts.account_exists(mgr, login))
            if login in (org.load().get("admins") or []):
                raise PlatformError(409, f"{_name(login)} is already a hospital admin here.", "already_admin")
            res = _make_admin(mgr, by, login, display_name, h["name"], url)
        except accounts.AccountError as e:
            raise PlatformError(e.status, str(e), "account")
        org.audit("admin_added", by, hospital=h["id"], username=res["username"], display_name=display_name or _name(res["username"]), created=res["created"])
    hospitals.audit("admin_added", by, hospital=h["id"], username=res["username"], display_name=display_name, created=res["created"])
    return res


def remove_admin(hid, username: str, by: str, mgr=None) -> dict:
    """DELETE /platform/hospitals/{id}/admins/{username}: the hospital-admin role goes (the login stays); never the last admin of an
    active hospital."""
    h = _get(hid)
    u = str(username or "").strip().lower()
    if not _folder(h["id"]):
        raise PlatformError(404, "This hospital's folder is missing; ask the server administrator.", "not_found")
    with config.use_hospital(h["id"]):
        o = copy.deepcopy(org.load())
        if u not in (o.get("admins") or []):
            raise PlatformError(404, f"'{u}' is not a hospital admin of {h['name']}.", "not_found")
        if len(o["admins"]) == 1 and h["status"] == "active":
            raise PlatformError(409, LAST_ADMIN, "last_admin")
        o["admins"] = [a for a in o["admins"] if a != u]
        name = _name(u)
        org.save(o, by)
    hospitals.audit("admin_removed", by, hospital=h["id"], username=u, display_name=name)
    return {"ok": True, "username": u}


def logins(mgr=None, hospital: str = "", role: str = "", q: str = "") -> dict:
    """GET /platform/logins: every placed login of every hospital, and the Vaidyx admins (listed, never changed here)."""
    vx = set(_vaidyx_admins(mgr))
    rows = []
    want_h = str(hospital or "").strip().lower()
    for h in hospitals.list_hospitals():
        if (want_h and h["id"] != want_h) or not _folder(h["id"]):
            continue
        with config.use_hospital(h["id"]):
            o = org.load()
            users = _users(o)
            for u in _people_logins(o):
                if u in vx:
                    continue
                rows.append({"username": u, "display_name": _name(u), "hospital": h["id"], "hospital_name": h["name"], "roles": role_words(u, o),
                             "disabled": bool((users.get(u) or {}).get("disabled")),
                             "must_change_password": accounts.must_change(mgr, u) if mgr is not None else False, "vaidyx_admin": False})
    for u in sorted(vx):
        hid = hospitals.hospital_of(u)
        if not hospitals.exists(hid):
            hid = config.DEFAULT_HOSPITAL
        if want_h and hid != want_h:
            continue
        hh = hospitals.get(hid) or {}
        with config.use_hospital(hid):
            name = _name(u) if _folder(hid) else u
        rows.append({"username": u, "display_name": name, "hospital": hid, "hospital_name": hh.get("name") or hid, "roles": ["vaidyx_admin"],
                     "disabled": False, "must_change_password": accounts.must_change(mgr, u), "vaidyx_admin": True})
    r = str(role or "").strip().lower()
    if r:
        rows = [x for x in rows if r in x["roles"]]
    for t in str(q or "").lower().split():
        rows = [x for x in rows if t in x["username"].lower() or t in str(x["display_name"]).lower()]
    return {"logins": rows}


def _login_hospital(mgr, username: str) -> tuple[str, str]:
    """(login, its hospital) for a change from the Vaidyx console; a Vaidyx admin is refused."""
    try:
        u = accounts.clean_username(username)
    except accounts.AccountError as e:
        raise PlatformError(e.status, str(e), "bad_value")
    if mgr is not None and accounts.is_vaidyx_admin(mgr, u):
        raise PlatformError(409, VAIDYX_ADMIN_HERE, "vaidyx_admin")
    hid = hospitals.hospital_of(u)
    if not hospitals.exists(hid) or not _folder(hid):
        raise PlatformError(404, f"'{u}' belongs to a hospital that is no longer set up.", "not_found")
    return u, hid


def reset_password(username: str, by: str, mgr=None, url: str = accounts.LOGIN_URL) -> dict:
    """POST /platform/logins/{u}/reset-password: a new first password (must change), inside the login's own hospital."""
    u, hid = _login_hospital(mgr, username)
    with config.use_hospital(hid):
        try:
            out = accounts.reset_password(mgr, by, {"admin": True, "user": by}, u, hospital=(hospitals.get(hid) or {}).get("name") or "", url=url, reveal=True)
        except accounts.AccountError as e:
            raise PlatformError(e.status, str(e), "account")
        name = _name(u)
    hospitals.audit("password_reset", by, hospital=hid, username=u, display_name=name)
    return {"username": u, "password_once": out["password_once"], "mailto": out["mailto"], "must_change_password": True}


def set_disabled(username: str, disabled: bool, by: str, mgr=None) -> dict:
    """POST /platform/logins/{u}/disable | enable: the Tumour Board flag in the login's own hospital (never a Vaidyx admin; a hospital
    admin loses that role first)."""
    u, hid = _login_hospital(mgr, username)
    with config.use_hospital(hid):
        try:
            accounts.update_account(mgr, by, {"admin": True, "user": by}, u, {"disabled": bool(disabled)})
        except accounts.AccountError as e:
            raise PlatformError(e.status, str(e), "account")
        name = _name(u)
    hospitals.audit("login_disabled" if disabled else "login_enabled", by, hospital=hid, username=u, display_name=name)
    return {"ok": True, "username": u, "disabled": bool(disabled)}


# ---- event texts ----------------------------------------------------------------------------------------------------------------

def _who(ev: dict) -> str:
    return str(ev.get("display_name") or ev.get("username") or "someone")


def platform_text(ev: dict, hname: str) -> str:
    k = ev.get("kind")
    if k == "hospital_created":
        return f"Hospital added: {ev.get('name') or hname}"
    if k == "hospital_updated":
        ch = ev.get("changed") if isinstance(ev.get("changed"), dict) else {}
        return f"Details changed for {hname}" + (f": {', '.join(sorted(ch))}" if ch else "")
    if k == "hospital_suspended":
        return f"Hospital suspended: {hname}" + (f". Reason: {ev.get('reason')}" if ev.get("reason") else "")
    if k == "hospital_reactivated":
        return f"Hospital reactivated: {hname}"
    if k == "admin_added":
        return f"Hospital admin added: {_who(ev)}" + (" (new login)" if ev.get("created") else "")
    if k == "admin_removed":
        return f"Hospital admin role removed from {_who(ev)}"
    if k == "password_reset":
        return f"Password reset for {_who(ev)}"
    if k == "login_disabled":
        return f"Login disabled: {_who(ev)}"
    if k == "login_enabled":
        return f"Login enabled again: {_who(ev)}"
    if k == "acting_in":
        return f"Worked inside {hname}"
    if k == "login_assigned":
        return f"Login {ev.get('username') or ''} belongs to {hname}"
    if k == "login_unassigned":
        return f"Login {ev.get('username') or ''} taken out of {hname}"
    return str(k or "event").replace("_", " ").capitalize()


def _by_names(events: list[dict]) -> dict:
    names = {}
    for e in events:
        b = str(e.get("by") or "")
        if not b or b in names:
            continue
        hid = hospitals.hospital_of(b)
        if not hospitals.exists(hid) or not _folder(hid):
            names[b] = b
            continue
        with config.use_hospital(hid):
            names[b] = _name(b)
    return names


def platform_event(ev: dict, names: dict | None = None) -> dict:
    hid = str(ev.get("hospital") or "")
    h = hospitals.get(hid) if hid else None
    hname = (h or {}).get("name") or str(ev.get("name") or hid)
    out = {"ts": ev.get("ts"), "by": ev.get("by") or "", "kind": ev.get("kind") or "", "hospital": hid or None, "hospital_name": hname or None,
           "text": platform_text(ev, hname)}
    if names is not None:
        out["by_name"] = names.get(out["by"]) or out["by"]
    return out


def activity(hospital: str = "", kind: str = "", limit: int = 200) -> dict:
    try:
        n = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        n = 200
    evs = hospitals.read_audit(limit=n, hospital=str(hospital or "").strip().lower() or None, kind=str(kind or "").strip() or None)
    names = _by_names(evs)
    return {"events": [platform_event(e, names) for e in evs]}


_ROLE_LABEL = {"member": "Doctor", "head": "Head of department", "resident": "Resident"}


def _roles_text(roles) -> str:
    if not isinstance(roles, dict):
        return ""
    parts = [f"{_ROLE_LABEL.get(org.ROLE_SYNONYMS.get(r, r), 'Doctor')}, {org.department_name(d)}" for d, r in (roles.get("departments") or {}).items()]
    if roles.get("coordinator"):
        parts.append("MDT Coordinator")
    if roles.get("admin_of"):
        parts.append("Department admin, " + ", ".join(org.department_name(d) for d in roles["admin_of"]))
    if roles.get("auditor"):
        parts.append("Auditor")
    if roles.get("outside_expert") or roles.get("real_data"):
        parts.append("Guest reviewer")
    return "; ".join(parts)


def org_text(ev: dict) -> str:
    """Plain words for an organisation event (current hospital); people are named, patients never (no clinical kind is shown)."""
    k = ev.get("kind")
    who = _name(str(ev.get("username") or "")) if ev.get("username") else ""
    if k == "hospital_created":
        return f"Hospital added: {ev.get('name') or ''}".strip()
    if k == "admin_added":
        return f"Hospital admin added: {ev.get('display_name') or who}"
    if k == "account_created":
        return f"Login created for {who}"
    if k == "password_reset":
        return f"Password reset for {who}"
    if k == "password_changed":
        return f"{_name(str(ev.get('by') or ''))} chose a new password"
    if k == "account_placed":
        rt = _roles_text(ev.get("roles"))
        return f"{who} added" + (f" ({rt})" if rt else "")
    if k == "account_roles_changed":
        a, b = ev.get("roles_before") or {}, ev.get("roles") or {}
        if isinstance(a, dict) and isinstance(b, dict) and bool(a.get("disabled")) != bool(b.get("disabled")):
            return f"Login {'disabled' if b.get('disabled') else 'enabled again'}: {who}"
        rt = _roles_text(b)
        return f"Roles changed for {who}" + (f": {rt}" if rt else "")
    if k == "account_unplaced":
        return f"{who} removed from the Tumour Board"
    if k == "root_admins_changed":
        before, after = set(ev.get("before") or []), set(ev.get("after") or [])
        added, gone = sorted(after - before), sorted(before - after)
        bits = ([f"added {', '.join(_name(u) for u in added)}"] if added else []) + ([f"removed {', '.join(_name(u) for u in gone)}"] if gone else [])
        return "Hospital admins changed" + (f": {'; '.join(bits)}" if bits else "")
    if k == "setup_step":
        from .api import setup
        return f"Set-up saved: {setup.STEP_LABELS.get(str(ev.get('step') or ''), str(ev.get('step') or ''))}"
    if k == "his_test":
        return "Hospital system test: answered" if ev.get("ok") else "Hospital system test: did not answer"
    if k == "his_settings_saved":
        if ev.get("his_kind") == "none":
            return "Hospital system: none connected yet"
        return "Hospital system connection saved" + (" (demo hospital system, synthetic)" if ev.get("demo") else "")
    if k == "hospital_changed":
        ch = ev.get("changes") if isinstance(ev.get("changes"), dict) else {}
        return "Hospital details changed" + (f": {', '.join(sorted(x.replace('_', ' ') for x in ch))}" if ch else "")
    if k == "first_setup":
        return "First set-up answered"
    if k == "first_setup_cleared":
        return "First set-up opened again"
    if k == "hospital_logo":
        return "Hospital logo changed"
    if k == "hospital_logo_removed":
        return "Hospital logo removed"
    if k == "routes_changed":
        return "Routing of records changed"
    return str(k or "event").replace("_", " ").capitalize()


def org_recent(limit: int = 10) -> list[dict]:
    """The current hospital's people, set-up, account and hospital-system events, newest first, with plain text (no clinical event)."""
    out, names = [], {}
    for ev in org.read_audit(limit=600):
        if ev.get("kind") not in ORG_KINDS:
            continue
        b = str(ev.get("by") or "")
        if b not in names:
            names[b] = _name(b) if b and b != "system" else b
        out.append({"ts": ev.get("ts"), "by": b, "by_name": names[b], "kind": ev.get("kind"), "text": org_text(ev)})
        if len(out) >= limit:
            break
    return out


# ---- the Hospital console (current hospital) ------------------------------------------------------------------------------------

def _placeholder(email: str) -> bool:
    return str(email or "").strip().lower().endswith("@" + org.PLACEHOLDER_DOMAIN)


def departments_view() -> dict:
    o = org.load()
    users = _users(o)
    out = []
    for d in o.get("departments") or []:
        did = d.get("id")
        heads = [{"username": u, "display_name": _name(u)} for u, v in sorted(users.items())
                 if org.ROLE_SYNONYMS.get((v.get("departments") or {}).get(did), (v.get("departments") or {}).get(did)) == "head"]
        placed = [u for u, v in users.items() if did in (v.get("departments") or {})]
        residents = [u for u in placed if org.ROLE_SYNONYMS.get(users[u]["departments"][did], users[u]["departments"][did]) == "resident"]
        out.append({"id": did, "name": d.get("name") or did, "group": d.get("group") or "", "enabled": bool(d.get("enabled", True)),
                    "heads": heads, "people": len(placed) - len(residents), "residents": len(residents), "email": d.get("email") or "",
                    "phone": d.get("phone") or "", "receives_requests": bool(d.get("receives_requests"))})
    return {"departments": out}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def hospital_attention(o: dict, people: dict, setup: dict, his: dict, mgr=None) -> list[dict]:
    out = []
    users = _users(o)
    if not any(v.get("coordinator") for v in users.values()):
        out.append({"kind": "no_coordinator", "text": "No MDT Coordinator yet", "link": "/hospital/people?role=coordinator"})
    deps = departments_view()["departments"]
    enabled = [d for d in deps if d["enabled"]]
    no_head = [d for d in enabled if not d["heads"] and (d["people"] or d["residents"])]
    if len(no_head) <= 3:
        out += [{"kind": "department_no_head", "text": f"{d['name']} has no head yet", "link": "/hospital/departments"} for d in no_head]
    else:
        out.append({"kind": "department_no_head", "text": f"{len(no_head)} departments with people have no head yet", "link": "/hospital/departments"})
    no_contact = [d for d in enabled if d["receives_requests"] and not ((d["email"] and not _placeholder(d["email"])) or d["phone"])]
    if len(no_contact) <= 3:
        out += [{"kind": "department_no_contact", "text": f"{d['name']} receives requests but has no email or phone", "link": "/hospital/departments"}
                for d in no_contact]
    else:
        out.append({"kind": "department_no_contact", "text": f"{len(no_contact)} departments that receive requests have no email or phone",
                    "link": "/hospital/departments"})
    today = _today()
    soon = (today + timedelta(days=30)).isoformat()
    for u, v in sorted(users.items()):
        ed = str(v.get("end_date") or "")[:10]
        places = {org.ROLE_SYNONYMS.get(r, r) for r in (v.get("departments") or {}).values()}
        if ed and "resident" in places and today.isoformat() <= ed <= soon and not v.get("disabled"):
            out.append({"kind": "resident_ending", "text": f"{_name(u)}'s rotation ends within 30 days", "link": "/hospital/people?role=resident"})
    if people.get("never_signed_in"):
        n = people["never_signed_in"]
        out.append({"kind": "never_signed_in", "text": f"{_plural(n, 'person has', 'people have')} not signed in yet", "link": "/hospital/people?role=not_signed_in"})
    if people.get("disabled"):
        n = people["disabled"]
        out.append({"kind": "disabled_logins", "text": f"{_plural(n, 'login is', 'logins are')} disabled", "link": "/hospital/people?role=disabled"})
    if setup["done"] < setup["total"]:
        out.append({"kind": "setup_unfinished", "text": f"Set-up {setup['done']} of {setup['total']} steps done", "link": "/hospital/setup"})
    if his.get("state") == "failing":
        out.append({"kind": "his_failing", "text": "The hospital system did not answer at the last test", "link": "/hospital/system"})
    return out


def hospital_overview(mgr=None) -> dict:
    """GET /hospital/overview of the current hospital: counts and people only, never patient data."""
    hid = config.hospital_id()
    h = hospitals.get(hid) or {"id": hid, "name": "", "city": "", "state": "", "status": "active"}
    o = org.load()
    hh = o.get("hospital") or {}
    people = people_by_role(o, mgr)
    setup = setup_steps(o, mgr)
    his = his_state(o)
    return {"hospital": {"id": hid, "name": hh.get("name") or h.get("name") or "", "city": h.get("city") or "", "state": h.get("state") or "",
                         "status": h.get("status") or "active", "level": hh.get("level") or "", "type": hh.get("type") or "",
                         "pmjay_empanelled": bool(hh.get("pmjay_empanelled", True))},
            "people": people, "case_files": cases_by_status(), "meetings": meetings_soon(), "requests": {"open": open_requests()},
            "setup": setup, "his": his, "attention": hospital_attention(o, people, setup, his, mgr), "recent": org_recent(limit=10)}


# ---- acting in a hospital (the request hook) ------------------------------------------------------------------------------------

_ACTING: dict = {}  # session key -> the hospital the Vaidyx admin last acted in (in memory; a restart audits the next one again)
_ACTING_MAX = 2000


def note_acting(session_key: str, by: str, hid: str | None) -> bool:
    """Record `acting_in` in the platform audit when this session of a Vaidyx admin starts working inside hospital `hid` (the first
    request with that X-TB-Hospital); None (no header) forgets it, so coming back later is recorded again. True when an event was written."""
    k = str(session_key or by or "")
    if not k:
        return False
    if not hid:
        _ACTING.pop(k, None)
        return False
    if _ACTING.get(k) == hid:
        return False
    if len(_ACTING) >= _ACTING_MAX:
        _ACTING.clear()
    _ACTING[k] = hid
    hospitals.audit("acting_in", by, hospital=hid)
    return True
