"""Logins and security of the demo HIMS (Vaidyx Demo Hospital, product label DemoHIMS). SYNTHETIC accounts only.

    python -m his_mock.build            always ensures the 9 accounts (data/his_mock/accounts.json)
    python -m his_mock.auth --reset     recreates every password (and clears the sessions)

Accounts: 9 synthetic staff accounts (@vaidyx-demo.invalid) holding the roles reception, opd.doctor (who also does the
ward work: roles opd.doctor and ward.doctor), ward.doctor (a ward-round login of the same Breast Surgery consultant),
lab.tech, lab.doctor, rad.tech, radiologist, pathologist and admin. Every account that signs is mapped to a consultant of
the store (opd.doctor and ward.doctor = Breast Surgery, lab.doctor = Biochemistry, radiologist = Radiology, pathologist =
Pathology), so a signature carries a real Reg. No. Passwords: 12 random characters, bcrypt-hashed in accounts.json,
written once in clear to data/his_mock/logins.tsv (email, role, password; mode 600). Passwords are never logged or printed.

Sessions: the cookie "vxhis_session" (HttpOnly, SameSite=Lax, 12 hours) names a server-side session kept in memory and in
data/his_mock/sessions.json (so a restart keeps people signed in). Each session carries a CSRF token that every HTML form
sends in a hidden field (checked on POST next to the app's same-origin middleware). Five failed sign-ins on an account lock
it for 15 minutes, said plainly on the login page; more than 30 failed sign-ins from one address within 15 minutes pause
sign-ins from that address (password spraying across accounts). Every login, logout and screen action is one line of
his_audit.jsonl.

Role checks: PERMISSIONS maps an action to the roles allowed; `require()` raises Forbidden ("Your role cannot do this")
which app.py renders as a 403 page with a flash message.
"""
import argparse
import json
import os
import secrets
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import bcrypt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import ui
from .ids import IST, iso, parse_time

COOKIE = "vxhis_session"
SESSION_HOURS = 12
MAX_FAILURES = 5
LOCK_MINUTES = 15
MAX_FAILURES_PER_ADDRESS = 30     # within LOCK_MINUTES, across every account
DOMAIN = "vaidyx-demo.invalid"
ACCOUNTS_NAME = "accounts.json"
LOGINS_NAME = "logins.tsv"
SESSIONS_NAME = "sessions.json"
AUDIT_NAME = "his_audit.jsonl"
BCRYPT_ROUNDS = 10
PASSWORD_LENGTH = 12
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0 / O / 1 / l / I: typed by hand in a demo

ROLE_LABELS = {
    "reception": "Registration desk", "opd.doctor": "OPD consultant", "ward.doctor": "Ward doctor",
    "lab.tech": "Laboratory technician", "lab.doctor": "Laboratory consultant", "rad.tech": "Radiology technician",
    "radiologist": "Radiologist", "pathologist": "Pathologist", "admin": "Hospital IT admin",
}
ROLES = tuple(ROLE_LABELS)

# The 9 accounts. `practitioner` names the department whose first consultant the account signs as (None: cannot sign).
ACCOUNT_SPECS = [
    {"email": f"reception@{DOMAIN}", "roles": ["reception"], "label": "Registration desk", "practitioner": None},
    {"email": f"opd.doctor@{DOMAIN}", "roles": ["opd.doctor", "ward.doctor"], "label": "OPD and ward consultant",
     "practitioner": "Breast Surgery"},
    {"email": f"ward.doctor@{DOMAIN}", "roles": ["ward.doctor"], "label": "Ward doctor", "practitioner": "Breast Surgery"},
    {"email": f"lab.tech@{DOMAIN}", "roles": ["lab.tech"], "label": "Laboratory technician", "practitioner": None},
    {"email": f"lab.doctor@{DOMAIN}", "roles": ["lab.doctor"], "label": "Laboratory consultant", "practitioner": "Biochemistry"},
    {"email": f"rad.tech@{DOMAIN}", "roles": ["rad.tech"], "label": "Radiology technician", "practitioner": None},
    {"email": f"radiologist@{DOMAIN}", "roles": ["radiologist"], "label": "Radiologist", "practitioner": "Radiology"},
    {"email": f"pathologist@{DOMAIN}", "roles": ["pathologist"], "label": "Pathologist", "practitioner": "Pathology"},
    {"email": f"admin@{DOMAIN}", "roles": ["admin"], "label": "Hospital IT admin", "practitioner": None},
]

DOCTORS = {"opd.doctor", "ward.doctor"}
# action -> roles allowed. Everything not listed is open to every signed-in user (viewing the screens).
PERMISSIONS = {
    "register": {"reception"},
    "visit.open": {"reception", "opd.doctor", "ward.doctor"},
    "admit": {"reception", "opd.doctor", "ward.doctor"},
    "transfer": {"reception", "opd.doctor", "ward.doctor"},
    "discharge": DOCTORS,
    "refer": DOCTORS,
    "accept_referral": DOCTORS,
    "note": DOCTORS,              # OPD note, discharge summary, clinical and procedure reports signed by the treating unit
    "order": DOCTORS,
    "lab.collect": {"lab.tech", "lab.doctor"},
    "lab.result": {"lab.tech", "lab.doctor"},
    "lab.sign": {"lab.doctor"},
    "lab.cancel": {"lab.tech", "lab.doctor"},
    "rad.schedule": {"rad.tech", "radiologist"},
    "rad.report": {"rad.tech", "radiologist"},
    "rad.sign": {"radiologist"},
    "rad.cancel": {"rad.tech", "radiologist"},
    "path.receive": {"pathologist", "lab.tech"},
    "path.report": {"pathologist"},
    "path.sign": {"pathologist"},
    "path.addon": {"pathologist"},
    "path.cancel": {"pathologist"},
    "admin": {"admin"},
}
PERMISSION_LABELS = {
    "register": "register a patient", "visit.open": "open an OP visit", "admit": "admit a patient",
    "transfer": "transfer a ward", "discharge": "discharge a patient", "refer": "refer to a department",
    "accept_referral": "accept a referral", "note": "write a clinical note or report", "order": "place orders",
    "lab.collect": "collect a sample", "lab.result": "enter laboratory results", "lab.sign": "verify and sign a laboratory report",
    "lab.cancel": "cancel a laboratory order", "rad.schedule": "schedule a study", "rad.report": "enter a radiology report",
    "rad.sign": "sign a radiology report", "rad.cancel": "cancel a radiology order", "path.receive": "receive a specimen",
    "path.report": "enter a pathology report", "path.sign": "sign a pathology report", "path.addon": "place an add-on order",
    "path.cancel": "cancel a pathology order", "admin": "use the Admin module",
}

# The JSON write APIs for a signed-in staff session (security review #3): the permission the same action needs on the screens. A
# path not listed is refused for a session (the write token is for machine callers).
_API_WRITES = (
    (r"^/his/api/registrations$", "register"),
    (r"^/his/api/patients/[^/]+/visits$", "visit.open"),
    (r"^/his/api/patients/[^/]+/admissions$", "admit"),
    (r"^/his/api/encounters/[^/]+/refer$", "refer"),
    (r"^/his/api/encounters/[^/]+/accept$", "accept_referral"),
    (r"^/his/api/encounters/[^/]+/transfer$", "transfer"),
    (r"^/his/api/encounters/[^/]+/discharge$", "discharge"),
    (r"^/his/api/encounters/[^/]+/orders$", "order"),
)
_DESK_WRITE = r"^/desk/api/[^/]+/(orders|reports)/([^/]+)/(schedule|collect|preliminary|sign|addendum|cancel)$"
_DESK_PERMISSIONS = {
    "lab": {"schedule": "lab.collect", "collect": "lab.collect", "preliminary": "lab.result", "sign": "lab.sign", "addendum": "lab.sign", "cancel": "lab.cancel"},
    "radiology": {"schedule": "rad.schedule", "collect": "rad.schedule", "preliminary": "rad.report", "sign": "rad.sign", "addendum": "rad.sign", "cancel": "rad.cancel"},
    "pathology": {"schedule": "path.receive", "collect": "path.receive", "preliminary": "path.report", "sign": "path.sign", "addendum": "path.sign", "cancel": "path.cancel"},
}


def api_permission(path, store=None):
    """The screen permission a JSON write on `path` needs from a staff session, or None (not open to sessions)."""
    import re as _re
    from . import common
    p = path.rstrip("/")
    for rx, perm in _API_WRITES:
        if _re.match(rx, p):
            return perm
    m = _re.match(_DESK_WRITE, p)
    if m and store is not None:
        kind, ident, action = m.groups()
        o = None
        if kind == "orders":
            o = store.orders.get(ident)
        else:
            r = store.reports.get(ident)
            o = store.orders.get(r.get("order_id")) if r else None
        if o:
            return _DESK_PERMISSIONS.get(common.module_of(o), {}).get(action)
    return None


REFUSED = "Your role cannot do this"
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(BCRYPT_ROUNDS))


class Forbidden(Exception):
    """A signed-in user asked for something their role cannot do (403, shown as a flash message)."""


class LoginError(Exception):
    """A refused sign-in (wrong password, locked account), with a plain message for the login page."""


def new_password():
    return "".join(secrets.choice(ALPHABET) for _ in range(PASSWORD_LENGTH))


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def check_password(password, hashed):
    try:
        return bcrypt.checkpw(str(password or "").encode("utf-8"), str(hashed or "").encode("ascii"))
    except (ValueError, TypeError):
        return False


def allowed(roles, permission):
    """True when any of `roles` may do `permission` (unknown permissions are open to every signed-in user)."""
    need = PERMISSIONS.get(permission)
    if need is None:
        return True
    return bool(set(roles or []) & need)


def who_can(permission):
    """The roles of a permission in plain words: "the Registration desk, OPD consultant or Ward doctor"."""
    names = [ROLE_LABELS.get(r, r) for r in ROLES if r in PERMISSIONS.get(permission, ())]
    if not names:
        return "nobody"
    return "the " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1])


def refusal(permission):
    """The plain refusal of a permission: "Your role cannot do this: only the Laboratory consultant can verify and sign
    a laboratory report." """
    return f"{REFUSED}: only {who_can(permission)} can {PERMISSION_LABELS.get(permission, permission)}."


def require(session, permission):
    """Raise Forbidden with a plain message unless the session's roles allow the permission."""
    if not session:
        raise Forbidden("Please sign in first.")
    if not allowed(session.get("roles"), permission):
        raise Forbidden(refusal(permission))


def _now():
    return datetime.now(IST)


def _write_private(path, text):
    """Write a file readable by its owner only (mode 600), replacing any earlier one."""
    path = Path(path)
    if path.exists():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _atomic_json(path, data):
    """Write JSON atomically, readable by the owner only (the hashes, session ids and CSRF tokens are secrets)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def audit(data_dir, action, outcome, *, user=None, roles=None, detail=None, path=None):
    """One line of his_audit.jsonl: logins and screen actions (never a password, never the token)."""
    line = {"time": iso(_now()), "user": user or "", "roles": list(roles or []), "action": action, "outcome": outcome}
    if path:
        line["path"] = path
    if detail:
        line["detail"] = detail
    p = Path(data_dir) / AUDIT_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def read_audit(data_dir, n=100):
    p = Path(data_dir) / AUDIT_NAME
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for x in lines[-n:]:
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


class Accounts:
    """The accounts, the sessions and the lock-outs of one data directory. Thread-safe behind one lock."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.lock = threading.RLock()
        self.accounts = {}
        self.sessions = {}
        self.failures = {}
        self.address_failures = {}   # client address -> [failure times]; memory only (a restart forgets them)
        self._load()

    # ------------------------------------------------------------------ files
    @property
    def accounts_path(self):
        return self.data_dir / ACCOUNTS_NAME

    @property
    def logins_path(self):
        return self.data_dir / LOGINS_NAME

    @property
    def sessions_path(self):
        return self.data_dir / SESSIONS_NAME

    def _load(self):
        if self.accounts_path.exists():
            try:
                data = json.loads(self.accounts_path.read_text(encoding="utf-8"))
                self.accounts = {a["email"]: a for a in data.get("accounts", []) if a.get("email")}
            except (ValueError, OSError, KeyError, TypeError):
                self.accounts = {}
        if self.sessions_path.exists():
            try:
                data = json.loads(self.sessions_path.read_text(encoding="utf-8"))
                self.sessions = {k: v for k, v in (data.get("sessions") or {}).items()}
                self.failures = dict(data.get("failures") or {})
            except (ValueError, OSError, TypeError):
                self.sessions, self.failures = {}, {}
        self._prune()

    def _save_accounts(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.accounts_path, {"version": 1, "synthetic": True, "accounts": list(self.accounts.values())})

    def _save_sessions(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.sessions_path, {"sessions": self.sessions, "failures": self.failures})

    def _prune(self):
        now = _now()
        gone = [k for k, s in self.sessions.items() if parse_time(s.get("expires") or "2000-01-01") <= now]
        for k in gone:
            self.sessions.pop(k, None)
        for email in list(self.failures):
            f = self.failures[email]
            if f.get("locked_until") and parse_time(f["locked_until"]) <= now:
                self.failures.pop(email, None)

    # ------------------------------------------------------------------ accounts
    @staticmethod
    def _practitioner_for(store, department):
        if not store or not department:
            return None
        people = sorted((p for p in store.practitioners.values()
                         if p["department"] == department and p["role"] == "consultant"), key=lambda p: p["reg_no"])
        return people[0] if people else None

    def ensure(self, store=None):
        """Create every missing account of ACCOUNT_SPECS with a fresh password; the new passwords are appended to
        logins.tsv (created with mode 600). Returns the emails created. Existing accounts (and their passwords) are kept;
        their practitioner mapping is refreshed from the store when it was empty."""
        with self.lock:
            created, lines = [], []
            for spec in ACCOUNT_SPECS:
                prac = self._practitioner_for(store, spec["practitioner"])
                acc = self.accounts.get(spec["email"])
                if acc:
                    if prac and not acc.get("practitioner_id"):
                        acc["practitioner_id"], acc["practitioner_name"] = prac["id"], prac["name"]
                    continue
                password = new_password()
                self.accounts[spec["email"]] = {
                    "email": spec["email"], "roles": list(spec["roles"]), "label": spec["label"],
                    "practitioner_id": prac["id"] if prac else None, "practitioner_name": prac["name"] if prac else None,
                    "password_hash": hash_password(password), "created": iso(_now()), "password_changed": iso(_now()),
                    "synthetic": True,
                }
                created.append(spec["email"])
                lines.append(f"{spec['email']}\t{','.join(spec['roles'])}\t{password}\n")
            if created or not self.accounts_path.exists():
                self._save_accounts()
            if lines:
                self._append_logins(lines)
            return created

    def _append_logins(self, lines):
        header = "email\trole\tpassword\n"
        if self.logins_path.exists():
            text = self.logins_path.read_text(encoding="utf-8")
            _write_private(self.logins_path, text + "".join(lines))
        else:
            _write_private(self.logins_path, header + "".join(lines))

    def reset_all(self, store=None):
        """New passwords for every account (missing ones are created), logins.tsv rewritten, every session ended."""
        with self.lock:
            self.ensure(store)
            lines = []
            for spec in ACCOUNT_SPECS:
                acc = self.accounts[spec["email"]]
                password = new_password()
                acc["password_hash"] = hash_password(password)
                acc["password_changed"] = iso(_now())
                lines.append(f"{spec['email']}\t{','.join(acc['roles'])}\t{password}\n")
            self._save_accounts()
            _write_private(self.logins_path, "email\trole\tpassword\n" + "".join(lines))
            self.sessions, self.failures = {}, {}
            self._save_sessions()
            return [s["email"] for s in ACCOUNT_SPECS]

    def reset_password(self, email):
        """A new password for one account (the Admin module shows it once on screen, never logs it). Ends its sessions."""
        with self.lock:
            acc = self.accounts.get(email)
            if not acc:
                raise KeyError(email)
            password = new_password()
            acc["password_hash"] = hash_password(password)
            acc["password_changed"] = iso(_now())
            self._save_accounts()
            for k in [k for k, s in self.sessions.items() if s.get("email") == email]:
                self.sessions.pop(k, None)
            self.failures.pop(email, None)
            self._save_sessions()
            self._mark_reset(email)
            return password

    def _mark_reset(self, email):
        """logins.tsv no longer holds a password that stopped working: the account's line says it was reset (the new
        password is never written anywhere; the admin saw it once)."""
        if not self.logins_path.exists():
            return
        when = _now().strftime("%d/%m/%Y %H:%M")
        out = []
        for line in self.logins_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0] == email:
                line = f"{parts[0]}\t{parts[1]}\t(reset by the admin on {when}; the new password was shown once on screen)"
            out.append(line)
        _write_private(self.logins_path, "\n".join(out) + "\n")

    def account(self, email):
        return self.accounts.get(str(email or "").strip().lower())

    def public(self, acc):
        """An account without its hash (the Admin module's table)."""
        return {k: v for k, v in acc.items() if k != "password_hash"}

    # ------------------------------------------------------------------ sign in / out
    def lock_state(self, email):
        """(locked: bool, minutes left) of an account."""
        f = self.failures.get(email) or {}
        until = f.get("locked_until")
        if until and parse_time(until) > _now():
            left = parse_time(until) - _now()
            return True, max(1, int(left.total_seconds() // 60) + (1 if left.total_seconds() % 60 else 0))
        return False, 0

    def _address_paused(self, address):
        """(paused: bool, minutes left) for a client address with too many failed sign-ins in the window."""
        if not address:
            return False, 0
        now = _now()
        window = timedelta(minutes=LOCK_MINUTES)
        times = [t for t in self.address_failures.get(address, []) if now - t < window]
        self.address_failures[address] = times
        if len(times) >= MAX_FAILURES_PER_ADDRESS:
            left = window - (now - times[0])
            return True, max(1, int(left.total_seconds() // 60) + 1)
        return False, 0

    def login(self, email, password, address=None):
        """Check the password; on success a new session dict (with its id and CSRF token). LoginError otherwise.
        `address` is the client's address (a pause after many failures from one address, across accounts)."""
        email = str(email or "").strip().lower()
        with self.lock:
            self._prune()
            paused, minutes = self._address_paused(address)
            if paused:
                raise LoginError(f"Too many failed sign-ins from this computer. Try again in {minutes} minute(s).")
            locked, minutes = self.lock_state(email)
            if locked:
                raise LoginError(f"This account is locked after {MAX_FAILURES} failed sign-ins. Try again in "
                                 f"{minutes} minute(s).")
            acc = self.accounts.get(email)
            ok = check_password(password, acc["password_hash"]) if acc else check_password(password, _DUMMY_HASH) and False
            if not ok:
                if address:
                    self.address_failures.setdefault(address, []).append(_now())
                f = self.failures.setdefault(email, {"count": 0, "locked_until": None})
                f["count"] = int(f.get("count") or 0) + 1
                if f["count"] >= MAX_FAILURES:
                    f["locked_until"] = iso(_now() + timedelta(minutes=LOCK_MINUTES))
                    f["count"] = 0
                    self._save_sessions()
                    raise LoginError(f"Wrong email or password. The account is now locked for {LOCK_MINUTES} minutes "
                                     f"after {MAX_FAILURES} failed sign-ins.")
                left = MAX_FAILURES - f["count"]
                self._save_sessions()
                raise LoginError(f"Wrong email or password. {left} attempt(s) left before a {LOCK_MINUTES}-minute lock.")
            self.failures.pop(email, None)
            now = _now()
            sid = secrets.token_urlsafe(32)
            session = {"id": sid, "email": acc["email"], "roles": list(acc["roles"]), "label": acc["label"],
                       "practitioner_id": acc.get("practitioner_id"), "practitioner_name": acc.get("practitioner_name"),
                       "csrf": secrets.token_urlsafe(24), "created": iso(now),
                       "expires": iso(now + timedelta(hours=SESSION_HOURS)), "last_seen": iso(now)}
            self.sessions[sid] = session
            self._save_sessions()
            return dict(session)

    def session(self, sid):
        """The live session for a cookie value, or None."""
        if not sid:
            return None
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                return None
            if parse_time(s["expires"]) <= _now():
                self.sessions.pop(sid, None)
                self._save_sessions()
                return None
            return dict(s)

    def logout(self, sid):
        with self.lock:
            s = self.sessions.pop(sid, None)
            if s:
                self._save_sessions()
            return s

    def session_for(self, request):
        return self.session(request.cookies.get(COOKIE))


# ---------------------------------------------------------------------- what needs a login (app.py middleware)
def protection(path):
    """None (open), "screen" (session cookie), "view" and "api" (session cookie or the integration bearer token), "pacs" (session
    cookie). The JSON APIs under /his/api and /desk/api need a login or the token (18 Oct); a test app may open them
    (create_app(open_api=True) or TB_HIS_MOCK_OPEN_API=1). The FHIR API keeps its own bearer token; / and /health stay login-free."""
    p = path.rstrip("/") or "/"
    if p in ("/his/login", "/his/logout"):
        return None
    if p == "/his" or p.startswith("/his/"):
        return "api" if p.startswith("/his/api/") or p == "/his/api" else "screen"
    if p == "/desk" or p.startswith("/desk/"):
        return "api" if p.startswith("/desk/api/") or p == "/desk/api" else "screen"
    if p.startswith("/view/reports"):
        return "view"
    if p == "/api/tb/pacs" or p.startswith("/api/tb/pacs/"):
        return "pacs"
    return None


def safe_next(value):
    """A local path to return to after the login (never another host)."""
    v = str(value or "").strip()
    if not v.startswith("/") or v.startswith("//") or "\\" in v or v.startswith("/his/login") or v.startswith("/his/logout"):
        return "/his"
    return v


# ---------------------------------------------------------------------- routes: /his/login, /his/logout
router = APIRouter()


def _login_page(request, *, email="", error=None, flash=None, nxt="/his"):
    body = ('<div class="panel login"><p class=muted>Sign in with one of the demo hospital accounts (synthetic staff '
            'logins of the Vaidyx Demo Hospital). The passwords are in the login file the build wrote on the server.</p>'
            '<form method=post action="/his/login">'
            + ui.hidden("next", nxt)
            + ui.field("email", "Email", ui.text_input("email", email, required=True, placeholder=f"role@{DOMAIN}",
                                                       extra=" autocomplete=username"), error)
            + ui.field("password", "Password", ui.text_input("password", "", required=True, kind="password",
                                                             extra=" autocomplete=current-password"))
            + '<p><button type=submit class=primary>Sign in</button></p></form>'
            f'<p class=small>{MAX_FAILURES} failed sign-ins lock an account for {LOCK_MINUTES} minutes. '
            f'Sessions end after {SESSION_HOURS} hours.</p></div>')
    return ui.page("Sign in", body, active=None, flash=flash, user=None)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    flash = request.query_params.get("flash")
    level = request.query_params.get("level")
    return HTMLResponse(_login_page(request, nxt=safe_next(request.query_params.get("next")),
                                    flash=((level or "ok"), flash) if flash else None))


def client_address(request):
    """The real peer address of the connection (security review #20): X-Forwarded-For and the like are never read, and serve.sh
    starts uvicorn with --no-proxy-headers so they cannot rewrite it either."""
    return request.client.host if request.client else None


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    hospital = request.app.state.hospital
    email = str(form.get("email") or "").strip().lower()
    password = str(form.get("password") or "")
    nxt = safe_next(form.get("next"))
    old = request.cookies.get(COOKIE)
    if old:  # a sign-in ends the session this browser had (security review #20)
        gone = hospital.accounts.logout(old)
        if gone:
            audit(hospital.files["data_dir"], "logout", "replaced", user=gone.get("email"), roles=gone.get("roles"))
    try:
        session = hospital.accounts.login(email, password, address=client_address(request))
    except LoginError as e:
        audit(hospital.files["data_dir"], "login", "refused", user=email, detail=str(e))
        return HTMLResponse(_login_page(request, email=email, error=str(e), nxt=nxt), status_code=401)
    audit(hospital.files["data_dir"], "login", "ok", user=session["email"], roles=session["roles"])
    resp = RedirectResponse(f"{nxt}{'&' if '?' in nxt else '?'}flash={quote('Signed in as ' + session['label'] + '.')}",
                            status_code=303)
    resp.set_cookie(COOKIE, session["id"], max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax", path="/")
    return resp


@router.get("/logout", response_class=HTMLResponse)
def logout_page(request: Request):
    """A page with the Sign out button: signing out is a POST with the form token, so a link on another site cannot sign anyone out
    (security review #20)."""
    hospital = request.app.state.hospital
    s = hospital.accounts.session_for(request)
    if not s:
        return RedirectResponse("/his/login?flash=" + quote("You are signed out."), status_code=303)
    body = ('<div class="panel login"><p>Sign out of the demo hospital system on this computer?</p>'
            '<form method=post action="/his/logout">' + ui.hidden("csrf", s.get("csrf") or "")
            + '<p><button type=submit class=primary>Sign out</button> <a href="/his">Back</a></p></form></div>')
    return HTMLResponse(ui.page("Sign out", body, active=None, user=s))


@router.post("/logout")
async def logout(request: Request):
    hospital = request.app.state.hospital
    sid = request.cookies.get(COOKIE)
    s = hospital.accounts.session(sid) if sid else None
    if s:
        form = await request.form()
        token = str(form.get("csrf") or "")
        if not token or not secrets.compare_digest(token, str(s.get("csrf") or "")):
            return RedirectResponse("/his/logout", status_code=303)  # a stale form: the page asks again
        hospital.accounts.logout(sid)
        audit(hospital.files["data_dir"], "logout", "ok", user=s.get("email"), roles=s.get("roles"))
    resp = RedirectResponse("/his/login?flash=" + quote("Signed out."), status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


# ---------------------------------------------------------------------- CLI
def main(argv=None):
    from . import model, paths

    ap = argparse.ArgumentParser(prog="python -m his_mock.auth", description="Accounts of the demo HIMS (SYNTHETIC)")
    ap.add_argument("--data", help="data directory (default data/his_mock or $TB_HIS_MOCK_DATA)")
    ap.add_argument("--reset", action="store_true", help="recreate every password (logins.tsv rewritten, sessions ended)")
    ap.add_argument("--ensure", action="store_true", help="create the missing accounts only (the default)")
    args = ap.parse_args(argv)
    files = paths.layout(args.data)
    store = model.Store.load(files["store"]) if files["store"].exists() else None
    acc = Accounts(files["data_dir"])
    if args.reset:
        emails = acc.reset_all(store)
        print(f"{len(emails)} passwords reset; logins in {acc.logins_path} (mode 600)")
    else:
        created = acc.ensure(store)
        print(f"{len(created)} account(s) created, {len(acc.accounts)} in {acc.accounts_path}; logins in "
              f"{acc.logins_path} (mode 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
