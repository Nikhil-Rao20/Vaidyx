"""Tumour Board accounts (V2 item 2.2): department admins create, disable and remove the doctor logins of their own departments; the root
admin creates coordinator, department-admin and doctor logins and names root admins.

Every login is a plain Vaidyx account, created only through the Vaidyx login system's create_user(..., is_admin=False): it gets the default
privileges (no server shell, no Vaidyx admin), and a freshly created account is checked for both before it is placed. No Tumour Board
action can create or grant a Vaidyx admin; an existing Vaidyx admin is never placed through these screens. A disable sets the Tumour
Board flag `disabled` in org.json (every Tumour Board action refused; the Vaidyx login itself is untouched). A remove takes the placement
away; the Vaidyx account stays (the Vaidyx admin deletes accounts). Password reset: the Vaidyx login system has no reset path without
Vaidyx admin rights (change_password needs the current password), so a reset is asked from the Vaidyx admin (RESET_NOTE); nothing here
changes the main app. Every change is audited in org_audit.jsonl (never a password).

The AuthManager is passed in (duck-typed: users, is_admin, create_user, get_privileges) so this module is unit-tested with a fake.
"""
import copy, re

from . import org

PASSWORD_MIN = 8  # src.constants.PASSWORD_MIN_LENGTH; the route passes the live value
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")
RESET_NOTE = ("Password reset: the Vaidyx login system allows a change only with the current password. A forgotten password is reset "
              "by the Vaidyx admin in the main app's Settings (delete and re-create the login, or set a new one there); the Tumour Board "
              "placement is kept.")


class AccountError(Exception):
    """A refused account action: `status` is the HTTP status the route answers with, the message is plain text."""
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def clean_username(username) -> str:
    u = str(username or "").strip().lower()
    if not USERNAME.match(u):
        raise AccountError(400, "The login name must be 2 to 63 characters: lower-case letters, digits, dots, hyphens or underscores.")
    return u


def account_exists(mgr, username: str) -> bool:
    return bool(mgr) and username in (getattr(mgr, "users", None) or {})


def is_vaidyx_admin(mgr, username: str) -> bool:
    try:
        return bool(mgr) and bool(mgr.is_admin(username))
    except Exception:
        return False


def has_shell(mgr, username: str) -> bool:
    try:
        return bool((mgr.get_privileges(username) or {}).get("can_use_bash"))
    except Exception:
        return False


def ensure_account(mgr, username: str, password: str | None, by: str, reserved=(), min_length: int = PASSWORD_MIN) -> dict:
    """The Vaidyx account `username` exists as a plain user when this returns: created now (a password is then required) or found.
    Refused: a reserved name, a Vaidyx admin, a short password, an account that came back with admin or shell privileges."""
    if mgr is None:
        raise AccountError(503, "The Vaidyx login system is not available; accounts cannot be managed right now.")
    u = clean_username(username)
    if u in set(reserved or ()):
        raise AccountError(400, f"'{u}' is a reserved name.")
    if account_exists(mgr, u):
        if is_vaidyx_admin(mgr, u):
            raise AccountError(409, f"'{u}' is a Vaidyx admin (server administrator) and is not placed through the Tumour Board screens.")
        return {"username": u, "created": False}
    pw = str(password or "")
    if len(pw) < min_length:
        raise AccountError(400, f"A new login needs a password of at least {min_length} characters.")
    if not mgr.create_user(u, pw, is_admin=False):
        raise AccountError(409, f"The login '{u}' could not be created (it may already exist).")
    if is_vaidyx_admin(mgr, u) or has_shell(mgr, u):  # never expected: the default privileges have neither
        org.audit("account_refused", by, username=u, reason="the new login came back with admin or shell privileges")
        raise AccountError(500, f"The login '{u}' was created with privileges it must not have; ask the Vaidyx admin.")
    org.audit("account_created", by, username=u, vaidyx_admin=False, shell=False)
    return {"username": u, "created": True}


def _dept(dept) -> str:
    did = org.department_id(dept)
    if not did:
        raise AccountError(404, f"Unknown department '{dept}'.")
    return did


def _blank_user(display_name: str = "") -> dict:
    return {"departments": {}, "admin_of": [], "coordinator": False, "display_name": str(display_name or "").strip(), "disabled": False}


def department_doctors(dept, mgr=None) -> list[dict]:
    """Everyone placed in the department: doctors (member / head) and its department admins, with their other placements (what a
    department admin cannot touch), the Tumour Board flags and whether the Vaidyx account exists (None when unknown)."""
    did = _dept(dept)
    o = org.load()
    out = []
    for uname, u in sorted((o.get("users") or {}).items()):
        if not isinstance(u, dict):
            continue
        role = (u.get("departments") or {}).get(did)
        admin = did in (u.get("admin_of") or [])
        if not role and not admin:
            continue
        others = sorted(d for d in (u.get("departments") or {}) if d != did)
        out.append({"username": uname, "display_name": u.get("display_name") or "", "role": role, "admin": admin,
                    "coordinator": bool(u.get("coordinator")), "disabled": bool(u.get("disabled")), "root_admin": uname in (o.get("admins") or []),
                    "other_departments": [{"id": d, "name": org.department_name(d)} for d in others],
                    "admin_of_others": sorted(d for d in (u.get("admin_of") or []) if d != did),
                    "account": (account_exists(mgr, uname) if mgr is not None else None),
                    "vaidyx_admin": is_vaidyx_admin(mgr, uname) if mgr is not None else False})
    return out


def place_doctor(by: str, dept, username: str, role: str = "member", display_name: str | None = None) -> dict:
    """Place an existing plain account as a doctor (member) or head of the department; audited by org.save."""
    did = _dept(dept)
    u = clean_username(username)
    role = org.ROLE_SYNONYMS.get(role, role or "member")
    if role not in org.DEPT_ROLES:
        raise AccountError(400, "The role must be doctor or head.")
    o = copy.deepcopy(org.load())
    user = o["users"].get(u) or _blank_user()
    user["departments"] = {**(user.get("departments") or {}), did: role}
    if display_name is not None and str(display_name).strip():
        user["display_name"] = str(display_name).strip()
    o["users"][u] = user
    saved = org.save(o, by)
    return {"username": u, **saved["users"][u]}


def _outside_reach(o: dict, caller: dict, u: str, did: str) -> list[str]:
    """What a department admin cannot touch about this user: placements in departments they do not administer, the coordinator flag, a
    department-admin or root-admin role. Empty for admins."""
    if (caller or {}).get("admin"):
        return []
    user = o["users"].get(u) or {}
    mine = set((caller or {}).get("admin_of") or [])
    reasons = [f"doctor of {org.department_name(d)}" for d in (user.get("departments") or {}) if d != did and d not in mine]
    if user.get("coordinator"):
        reasons.append("MDT Coordinator")
    if user.get("admin_of"):
        reasons.append("department admin of " + ", ".join(org.department_name(d) for d in user["admin_of"]))
    if u in (o.get("admins") or []):
        reasons.append("root admin")
    return reasons


def update_doctor(by: str, caller: dict, dept, username: str, role: str | None = None, disabled: bool | None = None) -> dict:
    """Change the role in this department or the Tumour Board disabled flag. The flag blocks every Tumour Board action, so a
    department admin may set it only for someone placed nowhere outside their own departments (else 409: ask the root admin); a
    root admin is disabled only after being removed from the root admins."""
    did = _dept(dept)
    u = clean_username(username)
    o = copy.deepcopy(org.load())
    user = o["users"].get(u)
    if not user or (did not in (user.get("departments") or {}) and did not in (user.get("admin_of") or [])):
        raise AccountError(404, f"'{u}' is not placed in {org.department_name(did)}.")
    if role is not None:
        role = org.ROLE_SYNONYMS.get(role, role)
        if role not in org.DEPT_ROLES:
            raise AccountError(400, "The role must be doctor or head.")
        if did not in (user.get("departments") or {}):
            raise AccountError(409, f"'{u}' is a department admin here, not a doctor; place them as a doctor first.")
        user["departments"][did] = role
    if disabled is not None:
        if not isinstance(disabled, bool):
            raise AccountError(400, "disabled must be true or false.")
        reasons = _outside_reach(o, caller, u, did)
        if reasons:
            raise AccountError(409, f"'{u}' is also {', '.join(reasons)}: the root admin decides whether to {'disable' if disabled else 'enable'} this login.")
        if disabled and u in (o.get("admins") or []):
            raise AccountError(409, f"'{u}' is a root admin; remove the root admin role first.")
        user["disabled"] = disabled
    o["users"][u] = user
    saved = org.save(o, by)
    return {"username": u, **saved["users"][u]}


def remove_doctor(by: str, caller: dict, dept, username: str) -> dict:
    """Take the doctor placement in this department away (the Vaidyx account stays). A user left with no placement, no admin role and no
    coordinator flag is dropped from org.json."""
    did = _dept(dept)
    u = clean_username(username)
    o = copy.deepcopy(org.load())
    user = o["users"].get(u)
    if not user or did not in (user.get("departments") or {}):
        raise AccountError(404, f"'{u}' is not a doctor of {org.department_name(did)}.")
    del user["departments"][did]
    if not user["departments"] and not user.get("admin_of") and not user.get("coordinator") and u not in (o.get("admins") or []):
        del o["users"][u]
    else:
        o["users"][u] = user
    org.save(o, by)
    return {"username": u, "removed_from": did, "kept": u in o["users"]}


def create_account(mgr, by: str, username: str, password: str | None, display_name: str = "", coordinator: bool = False, admin_of=(),
                   departments: dict | None = None, root_admin: bool = False, reserved=(), min_length: int = PASSWORD_MIN) -> dict:
    """Root admin: create (or find) a plain Vaidyx account and give it Tumour Board roles in one step. Never a Vaidyx admin."""
    for flag, name in ((coordinator, "coordinator"), (root_admin, "root_admin")):
        if not isinstance(flag, bool):
            raise AccountError(400, f"{name} must be true or false.")
    depts = {}
    for d, role in (departments or {}).items():
        role = org.ROLE_SYNONYMS.get(role, role)
        if role not in org.DEPT_ROLES:
            raise AccountError(400, "Each department role must be doctor or head.")
        depts[_dept(d)] = role
    adm = [_dept(d) for d in (admin_of or [])]
    if not (coordinator or root_admin or depts or adm):
        raise AccountError(400, "Give the login at least one role: coordinator, root admin, department admin or doctor.")
    made = ensure_account(mgr, username, password, by, reserved=reserved, min_length=min_length)
    u = made["username"]
    o = copy.deepcopy(org.load())
    user = o["users"].get(u) or _blank_user()
    user["departments"] = {**(user.get("departments") or {}), **depts}
    user["admin_of"] = list(dict.fromkeys([*(user.get("admin_of") or []), *adm]))
    user["coordinator"] = bool(user.get("coordinator")) or coordinator
    if str(display_name or "").strip():
        user["display_name"] = str(display_name).strip()
    o["users"][u] = user
    if root_admin and u not in o["admins"]:
        o["admins"].append(u)
    saved = org.save(o, by)
    return {"username": u, "created": made["created"], "root_admin": u in saved["admins"], **saved["users"][u]}
