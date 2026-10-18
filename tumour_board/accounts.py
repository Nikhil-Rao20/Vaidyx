"""Tumour Board accounts (V2 item 2.2; email logins, generated passwords and resets from 18 Oct 2026): department admins create, disable
and remove the doctor logins of their own departments; the root admin creates coordinator, department-admin, doctor, resident and
auditor logins and names root admins.

Every login is a plain Vaidyx account, created only through the Vaidyx login system's create_user(..., is_admin=False): it gets the default
privileges (no server shell, no Vaidyx admin), and a freshly created account is checked for both before it is placed. No Tumour Board
action can create or grant a Vaidyx admin; an existing Vaidyx admin is never placed through these screens. A disable sets the Tumour
Board flag `disabled` in org.json (every Tumour Board action refused; the Vaidyx login itself is untouched). A remove takes the placement
away; the Vaidyx account stays (the Vaidyx admin deletes accounts).

Login names: an email address (lower case; the new interface invites people by email) or the old short name. A new login gets a random
14-character password (secrets) that is set with must_change_password, so the person chooses their own at first sign-in; the password
travels only inside a mailto: link the admin opens in their own mail program (the server sends no email and never logs or audits a
password). A forgotten password is reset the same way (reset_password): the department admin for the people of their departments, the
root admin for anyone. Every change is audited in org_audit.jsonl (never a password).

The AuthManager is passed in (duck-typed: users, is_admin, create_user, get_privileges, reset_password) so this module is unit-tested
with a fake.
"""
import copy, re, secrets, string, urllib.parse

from . import org

PASSWORD_MIN = 8  # src.constants.PASSWORD_MIN_LENGTH; the route passes the live value
PASSWORD_CHARS = 14  # the generated first password
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")
EMAIL = re.compile(r"^[a-z0-9][a-z0-9._+\-]{0,63}@[a-z0-9][a-z0-9\-]*(\.[a-z0-9\-]+)+$")
LOGIN_URL = "/tb-nik"
MAIL_SUBJECT = "Your Vaidyx-TB login"
RESET_NOTE = ("Password reset: a department admin (for the people of their departments) or the root admin (for anyone) resets a password "
              "from the People screen; the person gets a mail draft with a new first password and must choose their own at the next sign-in. "
              "A Vaidyx admin account (the server administrator) is never reset here: the Vaidyx admin manages it in the main app.")
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0OIl1")


class AccountError(Exception):
    """A refused account action: `status` is the HTTP status the route answers with, the message is plain text."""
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def clean_username(username) -> str:
    u = str(username or "").strip().lower()
    if not (USERNAME.match(u) or EMAIL.match(u)):
        raise AccountError(400, "The login name is an email address, or 2 to 63 characters: lower-case letters, digits, dots, hyphens or underscores.")
    return u


def is_email(username) -> bool:
    return bool(EMAIL.match(str(username or "").strip().lower()))


def generate_password(n: int = PASSWORD_CHARS) -> str:
    """A random first password: letters and digits without the look-alikes, at least one of each (secrets)."""
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(max(n, PASSWORD_MIN)))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def mailto_for(email: str, username: str, password: str, url: str = LOGIN_URL, hospital: str = "") -> str:
    """The mail draft the admin opens in their own mail program: the login name, the first password and where to sign in. The server
    sends nothing; the password exists only in this link (and in the admin's mail program)."""
    body = "\r\n".join([
        f"Your Vaidyx-TB login{(' at ' + hospital) if hospital else ''} is ready.", "",
        f"Login name: {username}", f"First password: {password}", f"Sign in: {url}", "",
        "You will be asked to choose your own password at the first sign-in. Do not forward this message."])
    q = urllib.parse.urlencode({"subject": MAIL_SUBJECT, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{email or ''}?{q}"


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


def must_change(mgr, username: str) -> bool:
    try:
        return bool(mgr.must_change_password(username))
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


def _first_password(mgr, username: str, password: str, by: str) -> bool:
    """Set the generated first password with must_change_password (core.auth.reset_password); True when the flag is set. Never logged."""
    fn = getattr(mgr, "reset_password", None)
    if not callable(fn):
        org.audit("first_password_not_flagged", by, username=username, reason="the login system has no reset_password")
        return False
    try:
        ok = bool(fn(username, password, must_change=True))
    except TypeError:
        ok = bool(fn(username, password))
    org.audit("first_password_set", by, username=username, must_change=ok)
    return ok


def _dept(dept) -> str:
    did = org.department_id(dept)
    if not did:
        raise AccountError(404, f"Unknown department '{dept}'.")
    return did


def _blank_user(display_name: str = "") -> dict:
    return {"departments": {}, "admin_of": [], "coordinator": False, "display_name": str(display_name or "").strip(), "disabled": False,
            "auditor": False, "outside_expert": False, "end_date": ""}


def _check_end_date(end_date) -> str:
    s = str(end_date or "").strip()[:10]
    if s:
        from datetime import date
        try:
            date.fromisoformat(s)
        except ValueError:
            raise AccountError(400, "The end date must be a date (YYYY-MM-DD).")
    return s


def department_doctors(dept, mgr=None) -> list[dict]:
    """Everyone placed in the department: doctors (member / head), residents and its department admins, with their other placements (what a
    department admin cannot touch), the Tumour Board flags, the end date and whether the Vaidyx account exists (None when unknown)."""
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
        rl = org.roles(uname)
        out.append({"username": uname, "display_name": u.get("display_name") or "", "role": role, "admin": admin,
                    "coordinator": bool(u.get("coordinator")), "disabled": bool(u.get("disabled")), "root_admin": uname in (o.get("admins") or []),
                    "auditor": bool(u.get("auditor")), "end_date": str(u.get("end_date") or ""), "expired": bool(rl.get("expired")),
                    "other_departments": [{"id": d, "name": org.department_name(d)} for d in others],
                    "admin_of_others": sorted(d for d in (u.get("admin_of") or []) if d != did),
                    "account": (account_exists(mgr, uname) if mgr is not None else None),
                    "must_change_password": must_change(mgr, uname) if mgr is not None else False,
                    "vaidyx_admin": is_vaidyx_admin(mgr, uname) if mgr is not None else False})
    return out


def check_placement(dept, role) -> tuple[str, str]:
    """(department id, role) for a placement, or AccountError: checked before a login is created so no orphan account is left behind."""
    did = _dept(dept)
    role = org.ROLE_SYNONYMS.get(role, role or "member")
    if role not in org.PLACEMENTS:
        raise AccountError(400, "The role must be doctor, head or resident.")
    return did, role


def place_doctor(by: str, dept, username: str, role: str = "member", display_name: str | None = None, caller: dict | None = None, created: bool = True,
                 end_date: str | None = None) -> dict:
    """Place a plain account as a doctor (member), head or resident of the department; audited by org.save. A department admin may place an
    existing account only when it is placed nowhere outside their own departments (a coordinator, a root admin, another department's
    doctor: 409, the root admin decides; review M4); the display name of such an account is left alone. `end_date` (residents: the
    end of the rotation) is set when given."""
    did, role = check_placement(dept, role)
    u = clean_username(username)
    ed = _check_end_date(end_date) if end_date is not None else None
    o = copy.deepcopy(org.load())
    if not created and caller is not None:
        reasons = _outside_reach(o, caller, u, did)
        if reasons:
            raise AccountError(409, f"'{u}' is already {', '.join(reasons)}: the root admin places this login.")
    user = o["users"].get(u) or _blank_user()
    user["departments"] = {**(user.get("departments") or {}), did: role}
    if display_name is not None and str(display_name).strip() and (created or not user.get("display_name")):
        user["display_name"] = str(display_name).strip()
    if ed is not None:
        user["end_date"] = ed
    o["users"][u] = user
    saved = org.save(o, by)
    return {"username": u, **saved["users"][u]}


def _outside_reach(o: dict, caller: dict, u: str, did: str) -> list[str]:
    """What a department admin cannot touch about this user: placements in departments they do not administer, the coordinator flag, a
    department-admin, auditor or root-admin role. Empty for admins."""
    if (caller or {}).get("admin") or (caller or {}).get("root_admin"):
        return []
    user = o["users"].get(u) or {}
    mine = set((caller or {}).get("admin_of") or [])
    reasons = [f"doctor of {org.department_name(d)}" for d in (user.get("departments") or {}) if d != did and d not in mine]
    if user.get("coordinator"):
        reasons.append("MDT Coordinator")
    if user.get("auditor"):
        reasons.append("auditor")
    if user.get("admin_of"):
        reasons.append("department admin of " + ", ".join(org.department_name(d) for d in user["admin_of"]))
    if u in (o.get("admins") or []):
        reasons.append("root admin")
    return reasons


def update_doctor(by: str, caller: dict, dept, username: str, role: str | None = None, disabled: bool | None = None, mgr=None,
                  end_date: str | None = None) -> dict:
    """Change the role in this department (doctor, head, resident), the end date or the Tumour Board disabled flag. The flag blocks every
    Tumour Board action, so a department admin may set it only for someone placed nowhere outside their own departments (else 409: ask
    the root admin); a root admin is disabled only after being removed from the root admins; a Vaidyx admin is never disabled here (review M3)."""
    did = _dept(dept)
    u = clean_username(username)
    if disabled is not None and mgr is not None and is_vaidyx_admin(mgr, u):
        raise AccountError(409, f"'{u}' is a Vaidyx admin (server administrator); the Tumour Board flag does not apply.")
    o = copy.deepcopy(org.load())
    user = o["users"].get(u)
    if not user or (did not in (user.get("departments") or {}) and did not in (user.get("admin_of") or [])):
        raise AccountError(404, f"'{u}' is not placed in {org.department_name(did)}.")
    if role is not None:
        role = org.ROLE_SYNONYMS.get(role, role)
        if role not in org.PLACEMENTS:
            raise AccountError(400, "The role must be doctor, head or resident.")
        if did not in (user.get("departments") or {}):
            raise AccountError(409, f"'{u}' is a department admin here, not a doctor; place them as a doctor first.")
        user["departments"][did] = role
    if end_date is not None:
        user["end_date"] = _check_end_date(end_date)
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
    coordinator / auditor flag is dropped from org.json."""
    did = _dept(dept)
    u = clean_username(username)
    o = copy.deepcopy(org.load())
    user = o["users"].get(u)
    if not user or did not in (user.get("departments") or {}):
        raise AccountError(404, f"'{u}' is not a doctor of {org.department_name(did)}.")
    del user["departments"][did]
    if not user["departments"] and not user.get("admin_of") and not user.get("coordinator") and not user.get("auditor") and u not in (o.get("admins") or []):
        del o["users"][u]
    else:
        o["users"][u] = user
    org.save(o, by)
    return {"username": u, "removed_from": did, "kept": u in o["users"]}


def create_account(mgr, by: str, username: str, password: str | None = None, display_name: str = "", coordinator: bool = False, admin_of=(),
                   departments: dict | None = None, root_admin: bool = False, reserved=(), min_length: int = PASSWORD_MIN,
                   auditor: bool = False, outside_expert: bool = False, end_date: str = "", email: str = "", hospital: str = "", url: str = LOGIN_URL) -> dict:
    """Root admin: create (or find) a plain Vaidyx account and give it Tumour Board roles in one step. Never a Vaidyx admin.

    Without a password a new login gets a generated 14-character one, set with must_change_password; the answer carries a mailto: link
    (to `email`, else to the login name when it is an address) holding the login name and that password. The password is in the link
    only: not in the audit log, not in the server log, not elsewhere in the answer."""
    for flag, name in ((coordinator, "coordinator"), (root_admin, "root_admin"), (auditor, "auditor"), (outside_expert, "outside_expert")):
        if not isinstance(flag, bool):
            raise AccountError(400, f"{name} must be true or false.")
    depts = {}
    for d, role in (departments or {}).items():
        role = org.ROLE_SYNONYMS.get(role, role)
        if role not in org.PLACEMENTS:
            raise AccountError(400, "Each department role must be doctor, head or resident.")
        depts[_dept(d)] = role
    adm = [_dept(d) for d in (admin_of or [])]
    ed = _check_end_date(end_date)
    if not (coordinator or root_admin or depts or adm or auditor or outside_expert):
        raise AccountError(400, "Give the login at least one role: coordinator, root admin, department admin, doctor, resident, auditor or outside expert.")
    generated = ""
    if not str(password or "") and mgr is not None and not account_exists(mgr, clean_username(username)):
        generated = generate_password()
    made = ensure_account(mgr, username, password or generated, by, reserved=reserved, min_length=min_length)
    u = made["username"]
    flagged = False
    if made["created"] and generated:
        flagged = _first_password(mgr, u, generated, by)
    o = copy.deepcopy(org.load())
    user = o["users"].get(u) or _blank_user()
    user["departments"] = {**(user.get("departments") or {}), **depts}
    user["admin_of"] = list(dict.fromkeys([*(user.get("admin_of") or []), *adm]))
    user["coordinator"] = bool(user.get("coordinator")) or coordinator
    user["auditor"] = bool(user.get("auditor")) or auditor
    user["outside_expert"] = bool(user.get("outside_expert")) or outside_expert
    if ed:
        user["end_date"] = ed
    if str(display_name or "").strip():
        user["display_name"] = str(display_name).strip()
    o["users"][u] = user
    if root_admin and u not in o["admins"]:
        o["admins"].append(u)
    saved = org.save(o, by)
    to = str(email or "").strip().lower() or (u if is_email(u) else "")
    out = {"username": u, "created": made["created"], "root_admin": u in saved["admins"], **saved["users"][u],
           "mailto": mailto_for(to, u, generated, url=url or LOGIN_URL, hospital=hospital) if generated and made["created"] else "", "must_change_password": flagged, "email": to}
    return out


def reset_password(mgr, by: str, caller: dict, username: str, email: str = "", hospital: str = "", url: str = LOGIN_URL) -> dict:
    """A new first password for an existing login (must_change set, every session of that login revoked by the login system): the
    department admin for the people placed in (or administering) their departments only, the root admin and the Vaidyx admin for anyone
    placed in the Tumour Board. Never for a Vaidyx admin account. Audited (password_reset) without the password, which travels in the
    mailto: link only."""
    if mgr is None:
        raise AccountError(503, "The Vaidyx login system is not available; accounts cannot be managed right now.")
    u = clean_username(username)
    o = org.load()
    user = (o.get("users") or {}).get(u)
    if not isinstance(user, dict):
        raise AccountError(404, f"'{u}' is not placed in the Tumour Board.")
    if not account_exists(mgr, u):
        raise AccountError(404, f"'{u}' has no Vaidyx login yet; create it first.")
    if is_vaidyx_admin(mgr, u):
        raise AccountError(409, f"'{u}' is a Vaidyx admin (server administrator); its password is managed in the main app.")
    if not ((caller or {}).get("admin") or (caller or {}).get("root_admin")):
        mine = set((caller or {}).get("admin_of") or [])
        placed = set(user.get("departments") or {}) | set(user.get("admin_of") or [])
        if not mine or not (placed & mine):
            raise AccountError(403, "You reset the passwords of the people placed in the departments you administer.")
        reasons = _outside_reach(o, caller, u, next(iter(placed & mine)))
        if reasons:
            raise AccountError(409, f"'{u}' is also {', '.join(reasons)}: the root admin resets this login.")
    fn = getattr(mgr, "reset_password", None)
    if not callable(fn):
        raise AccountError(503, "The Vaidyx login system cannot reset passwords; ask the Vaidyx admin.")
    pw = generate_password()
    try:
        ok = bool(fn(u, pw, must_change=True))
    except TypeError:
        ok = bool(fn(u, pw))
    if not ok:
        raise AccountError(500, f"The password of '{u}' could not be reset; ask the Vaidyx admin.")
    org.audit("password_reset", by, username=u, must_change=True)
    to = str(email or "").strip().lower() or (u if is_email(u) else "")
    return {"username": u, "mailto": mailto_for(to, u, pw, url=url or LOGIN_URL, hospital=hospital), "must_change_password": True, "email": to}


UPDATABLE = ("disabled", "end_date", "coordinator", "auditor", "outside_expert", "root_admin", "admin_of", "departments", "display_name")


def update_account(mgr, by: str, caller: dict, username: str, fields: dict) -> dict:
    """Root admin (or Vaidyx admin): change the flags and roles of a placed login in one step: disabled, end_date, coordinator, auditor,
    outside_expert, root_admin, admin_of (replaces), departments (replaces: {dept: doctor | head | resident}), display_name. Never a
    Vaidyx admin account; a root admin cannot disable itself or drop the last root admin. Audited by org.save."""
    if not ((caller or {}).get("admin") or (caller or {}).get("root_admin")):
        raise AccountError(403, "Only the root admin changes the roles of a login.")
    u = clean_username(username)
    if mgr is not None and is_vaidyx_admin(mgr, u):
        raise AccountError(409, f"'{u}' is a Vaidyx admin (server administrator) and is not managed through the Tumour Board screens.")
    if not isinstance(fields, dict):
        raise AccountError(400, "Send the fields to change as an object.")
    unknown = sorted(k for k in fields if k not in UPDATABLE)
    if unknown:
        raise AccountError(400, f"Unknown field(s): {', '.join(unknown)}. Changeable: {', '.join(UPDATABLE)}.")
    o = copy.deepcopy(org.load())
    user = o["users"].get(u)
    if not isinstance(user, dict):
        raise AccountError(404, f"'{u}' is not placed in the Tumour Board.")
    for flag in ("disabled", "coordinator", "auditor", "outside_expert"):
        if flag in fields:
            if not isinstance(fields[flag], bool):
                raise AccountError(400, f"{flag} must be true or false.")
            if flag == "disabled" and fields[flag] and u == (caller or {}).get("user"):
                raise AccountError(409, "You cannot disable your own login.")
            user[flag] = fields[flag]
    if "end_date" in fields:
        user["end_date"] = _check_end_date(fields["end_date"])
    if "display_name" in fields:
        user["display_name"] = " ".join(str(fields["display_name"] or "").split())[:80]
    if "admin_of" in fields:
        if not isinstance(fields["admin_of"], list):
            raise AccountError(400, "admin_of must be a list of departments.")
        user["admin_of"] = list(dict.fromkeys(_dept(d) for d in fields["admin_of"]))
    if "departments" in fields:
        if not isinstance(fields["departments"], dict):
            raise AccountError(400, "departments must map a department to doctor, head or resident.")
        user["departments"] = {did: role for d, r in fields["departments"].items() for did, role in [check_placement(d, r)]}
    if "root_admin" in fields:
        if not isinstance(fields["root_admin"], bool):
            raise AccountError(400, "root_admin must be true or false.")
        if fields["root_admin"] and u not in o["admins"]:
            o["admins"].append(u)
        elif not fields["root_admin"] and u in o["admins"]:
            if len(o["admins"]) == 1:
                raise AccountError(409, "This is the last root admin; name another one first.")
            o["admins"].remove(u)
    if user.get("disabled") and u in o["admins"]:
        raise AccountError(409, f"'{u}' is a root admin; remove the root admin role before disabling the login.")
    o["users"][u] = user
    saved = org.save(o, by)
    return {"username": u, "root_admin": u in saved["admins"], **saved["users"][u]}
