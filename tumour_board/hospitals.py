"""The hospitals one running app serves (admin consoles, 16 Nov 2026, docs/admin-console/DESIGN.md D1 to D3, D8, D11).

Registry: <HOSPITALS_ROOT>/registry.json
  {"version": 1,
   "hospitals": {id: {"name", "city", "state", "status": "active" | "suspended", "created_at", "created_by", "suspended_reason"}},
   "users": {login: hospital id}}

Rules:
- The hospital "default" (today's folder, config.BASE_ROOT) is always there, never suspended, never in the "hospitals" map unless
  its city or state was set; its name is the one its own set-up wrote in org.json (hospital.name).
- One login belongs to one hospital. A login missing from "users" belongs to "default", so today's data needs no migration.
- A hospital is suspended, never deleted: its logins are refused (the Vaidyx admin is exempt), its data stays.
- A new hospital gets its own folder <HOSPITALS_ROOT>/<id>/ (mode 700) with an org.json of the default departments and its name, written
  by org.save inside that hospital; no hospital system (his.json) until its admin sets one up.
- Every change is a line in <HOSPITALS_ROOT>/platform_audit.jsonl (never a password, token or secret).
- Files are written atomically with mode 600 (folders 700), under one lock; the registry is read again when the file changes.
"""
import copy, json, logging, os, re, tempfile, threading, unicodedata
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

VERSION = 1
DEFAULT = config.DEFAULT_HOSPITAL
STATUSES = ("active", "suspended")
DEFAULT_NAME = "Default hospital"
LIMITS = {"name": 160, "city": 80, "state": 80, "reason": 500}
_SECRET_WORDS = ("password", "token", "secret", "api_key")
_lock = threading.RLock()
_cache: dict = {}  # registry path -> ((inode, mtime_ns, size), data)


class HospitalError(ValueError):
    """A refused registry change: `status` is the HTTP status a route answers with; the message is plain text."""
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# ---- files ----------------------------------------------------------------------------------------------------------------------

def root() -> Path:
    return Path(config.HOSPITALS_ROOT)


def registry_path() -> Path:
    return root() / "registry.json"


def audit_path() -> Path:
    return root() / "platform_audit.jsonl"


def _mkdir(p: Path) -> None:
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass


def _atomic_write(p: Path, text: str) -> None:
    _mkdir(p.parent)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _empty() -> dict:
    return {"version": VERSION, "hospitals": {}, "users": {}}


def _data() -> dict:
    """The registry as stored (cached on the file's modification time; read only: change a copy and _save it)."""
    p = registry_path()
    try:
        st = p.stat()
    except FileNotFoundError:
        return _empty()
    sig = (st.st_ino, st.st_mtime_ns, st.st_size)  # a new inode on every atomic write
    hit = _cache.get(str(p))
    if hit and hit[0] == sig:
        return hit[1]
    raw = json.loads(p.read_text(encoding="utf-8"))  # an unreadable registry raises: the request hook refuses (never a guess)
    d = _empty()
    if isinstance(raw, dict):
        d["hospitals"] = {k: v for k, v in (raw.get("hospitals") or {}).items() if isinstance(v, dict) and config.HOSPITAL_ID.match(str(k))}
        d["users"] = {str(k): str(v) for k, v in (raw.get("users") or {}).items() if isinstance(k, str) and isinstance(v, str)}
    if len(_cache) > 64:
        _cache.clear()
    _cache[str(p)] = (sig, d)
    return d


def load() -> dict:
    """A copy of the registry {"version", "hospitals", "users"} (the "default" hospital is implicit: see list_hospitals())."""
    with _lock:
        return copy.deepcopy(_data())


def _save(d: dict) -> None:
    out = {"version": VERSION, "hospitals": d.get("hospitals") or {}, "users": d.get("users") or {}}
    _atomic_write(registry_path(), json.dumps(out, indent=2, ensure_ascii=False))


# ---- reading --------------------------------------------------------------------------------------------------------------------

def _default_name() -> str:
    try:
        o = json.loads((config.root_for(DEFAULT) / "org.json").read_text(encoding="utf-8"))
        name = str(((o or {}).get("hospital") or {}).get("name") or "").strip()
    except (OSError, ValueError, AttributeError):
        name = ""
    return name or DEFAULT_NAME


def _row(hid: str, rec: dict | None) -> dict:
    rec = rec or {}
    if hid == DEFAULT:
        return {"id": DEFAULT, "name": _default_name(), "city": str(rec.get("city") or ""), "state": str(rec.get("state") or ""),
                "status": "active", "created_at": rec.get("created_at"), "created_by": rec.get("created_by"), "suspended_reason": "",
                "default": True}
    return {"id": hid, "name": str(rec.get("name") or hid), "city": str(rec.get("city") or ""), "state": str(rec.get("state") or ""),
            "status": rec.get("status") if rec.get("status") in STATUSES else "active", "created_at": rec.get("created_at"),
            "created_by": rec.get("created_by"), "suspended_reason": str(rec.get("suspended_reason") or ""), "default": False}


def list_hospitals() -> list[dict]:
    """Every hospital, "default" first, then the others by name."""
    with _lock:
        d = _data()
        others = [_row(h, r) for h, r in d["hospitals"].items() if h != DEFAULT]
        return [_row(DEFAULT, d["hospitals"].get(DEFAULT))] + sorted(others, key=lambda r: (r["name"].lower(), r["id"]))


def get(hid) -> dict | None:
    """The hospital `hid`, or None when there is no such hospital."""
    h = str(hid or "")
    if h == DEFAULT:
        return _row(DEFAULT, _data()["hospitals"].get(DEFAULT))
    rec = _data()["hospitals"].get(h)
    return _row(h, rec) if rec is not None else None


def exists(hid) -> bool:
    return get(hid) is not None


def ids(active_only: bool = False) -> list[str]:
    return [h["id"] for h in list_hospitals() if not active_only or h["status"] == "active"]


def active_ids() -> list[str]:
    return ids(active_only=True)


def multi() -> bool:
    """True when the app serves more than one hospital (a hospital besides "default" is registered)."""
    return config._has_other_hospitals()


def registered(username) -> str | None:
    """The hospital a login is registered to, or None when it is not in the registry (it then belongs to "default")."""
    return _data()["users"].get(str(username or "").strip().lower()) or None


def hospital_of(username) -> str:
    """The hospital of a login ("default" when the registry does not name one)."""
    return registered(username) or DEFAULT


def users_of(hid) -> list[str]:
    """The logins registered to `hid` (for "default": only those registered explicitly; its other logins are the unregistered ones)."""
    h = str(hid or "")
    return sorted(u for u, x in _data()["users"].items() if x == h)


ACTING_COOKIE = "tb_acting_hospital"  # set by POST /platform/acting for requests the browser makes without fetch (links, images, iframes)


def acting_request(vaidyx_admin: bool, header=None, cookie=None) -> str:
    """The hospital a Vaidyx admin's request names ("" when none): the X-TB-Hospital header wins, else the tb_acting_hospital cookie.
    Never anyone else's (always "")."""
    if not vaidyx_admin:
        return ""
    return str(header or "").strip().lower() or str(cookie or "").strip().lower()


def known(hid) -> bool:
    """A well-formed id of a hospital in the registry."""
    h = str(hid or "")
    return bool(config.HOSPITAL_ID.match(h)) and exists(h)


def resolve(username, vaidyx_admin: bool = False, requested=None) -> tuple[str, str | None]:
    """(hospital id, refusal code or None) for a request of `username`. No login: "default". A Vaidyx admin works in its own hospital or,
    when `requested` names an existing hospital, in that one (any status); anyone else's `requested` is ignored. A login of a suspended
    hospital: "hospital_suspended"; of a hospital no longer in the registry: "hospital_unknown"."""
    if not username:
        return DEFAULT, None
    hid = hospital_of(username)
    if vaidyx_admin:
        want = str(requested or "").strip().lower()
        if want and config.HOSPITAL_ID.match(want) and exists(want):
            return want, None
        return (hid if exists(hid) else DEFAULT), None
    h = get(hid)
    if h is None:
        return hid, "hospital_unknown"
    if h["status"] == "suspended":
        return hid, "hospital_suspended"
    return hid, None


# ---- the audit ------------------------------------------------------------------------------------------------------------------

def _clean(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if not any(w in str(k).lower() for w in _SECRET_WORDS)}


def audit(kind: str, by: str, **fields) -> dict:
    """Append one platform event to platform_audit.jsonl (a field named like a password, token or secret is never written)."""
    from .store import now_iso
    ev = {"ts": now_iso(), "by": str(by or ""), "kind": str(kind), **_clean(fields)}
    with _lock:
        p = audit_path()
        _mkdir(p.parent)
        fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    return ev


def read_audit(limit: int = 200, hospital=None, kind=None) -> list[dict]:
    """The newest `limit` platform events, newest first; `hospital` / `kind` filter on the event's fields. A malformed line is skipped."""
    try:
        lines = audit_path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or (hospital and ev.get("hospital") != hospital) or (kind and ev.get("kind") != kind):
            continue
        out.append(ev)
        if len(out) >= max(1, int(limit or 1)):
            break
    return out


# ---- changes --------------------------------------------------------------------------------------------------------------------

def _text(v, field: str, required: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise HospitalError(400, f"The {field} must be text.")
    v = " ".join(v.split())
    if required and not v:
        raise HospitalError(400, f"Give the hospital's {field}.")
    if len(v) > LIMITS[field]:
        raise HospitalError(400, f"The {field} is too long (at most {LIMITS[field]} characters).")
    return v


def slug(name: str) -> str:
    """A hospital id from its name: lower-case ASCII letters and digits joined by hyphens, at most 40 characters."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40].strip("-")
    if len(s) < 2:
        s = ("hospital-" + s).strip("-")
    return s


def create(name, by, city="", state="", hid=None) -> dict:
    """Register a new hospital and make its folder (mode 700) with a fresh org.json (the default departments, the hospital's name; no
    hospital system). The id comes from the name (made unique) unless `hid` is given. Audited (hospital_created)."""
    from . import org
    name = _text(name, "name", required=True)
    city, state = _text(city, "city"), _text(state, "state")
    with _lock:
        d = copy.deepcopy(_data())
        taken = set(d["hospitals"]) | {DEFAULT}
        if hid is not None:
            h = str(hid).strip().lower()
            if not config.HOSPITAL_ID.match(h):
                raise HospitalError(400, "A hospital id is 2 to 41 lower-case letters, digits or hyphens.")
            if h in taken:
                raise HospitalError(409, f"The hospital id '{h}' is taken.")
        else:
            base, h, n = slug(name), slug(name), 2
            while h in taken or (root() / h).exists():
                h = f"{base[:36]}-{n}"
                n += 1
        folder = config.root_for(h)
        if folder.exists():  # never adopt a folder this registry did not make
            raise HospitalError(409, f"A folder for '{h}' already exists; choose another id.")
        base_root = Path(config.BASE_ROOT).resolve()
        if base_root == folder.resolve().parent or base_root in folder.resolve().parents:
            raise HospitalError(500, "The hospitals folder must not be inside the default hospital's folder (TB_HOSPITALS_ROOT).")
        _mkdir(root())
        folder.mkdir(mode=0o700)
        try:
            with config.use_hospital(h):
                o = copy.deepcopy(org.DEFAULT_ORG)
                o["hospital"]["name"] = name
                org.save(o, by)
            from .store import now_iso
            d["hospitals"][h] = {"name": name, "city": city, "state": state, "status": "active", "created_at": now_iso(),
                                 "created_by": str(by or ""), "suspended_reason": ""}
            _save(d)
        except BaseException:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)
            raise
        audit("hospital_created", by, hospital=h, name=name, city=city, state=state)
        return get(h)


def update(hid, by, **fields) -> dict:
    """Change a hospital's name, city or state (the default hospital's name is changed in its own set-up). Audited (hospital_updated)."""
    h = str(hid or "")
    unknown = sorted(k for k in fields if k not in ("name", "city", "state"))
    if unknown:
        raise HospitalError(400, f"Unknown field(s): {', '.join(unknown)}. Changeable: name, city, state.")
    with _lock:
        if not exists(h):
            raise HospitalError(404, "No such hospital.")
        d = copy.deepcopy(_data())
        rec = d["hospitals"].setdefault(h, {}) if h == DEFAULT else d["hospitals"][h]
        changed = {}
        for k, v in fields.items():
            if k == "name" and h == DEFAULT:
                raise HospitalError(409, "The default hospital's name is changed in its own set-up (Hospital step).")
            v = _text(v, k, required=(k == "name"))
            if rec.get(k, "") != v:
                changed[k] = {"before": rec.get(k, ""), "after": v}
                rec[k] = v
        if changed:
            _save(d)
            audit("hospital_updated", by, hospital=h, changed=changed)
        return get(h)


def set_status(hid, status, by, reason="") -> dict:
    """Suspend or reactivate a hospital (never "default"; a suspension needs a reason). Audited (hospital_suspended / hospital_reactivated)."""
    h = str(hid or "")
    if status not in STATUSES:
        raise HospitalError(400, "The status is active or suspended.")
    reason = _text(reason, "reason")
    with _lock:
        if h == DEFAULT:
            raise HospitalError(409, "The default hospital cannot be suspended.")
        d = copy.deepcopy(_data())
        rec = d["hospitals"].get(h)
        if rec is None:
            raise HospitalError(404, "No such hospital.")
        if status == "suspended" and not reason:
            raise HospitalError(400, "Give a reason for the suspension.")
        if rec.get("status", "active") == status:
            return get(h)
        rec["status"] = status
        rec["suspended_reason"] = reason if status == "suspended" else ""
        _save(d)
        audit("hospital_suspended" if status == "suspended" else "hospital_reactivated", by, hospital=h, reason=reason)
        return get(h)


def assign(username, hid, by) -> str:
    """Register a login to hospital `hid` ("default" removes the entry: unregistered logins belong to it). Audited (login_assigned)."""
    u = str(username or "").strip().lower()
    h = str(hid or "")
    if not u:
        raise HospitalError(400, "Give the login.")
    with _lock:
        if not exists(h):
            raise HospitalError(404, "No such hospital.")
        d = copy.deepcopy(_data())
        before = d["users"].get(u) or DEFAULT
        if h == DEFAULT:
            d["users"].pop(u, None)
        else:
            d["users"][u] = h
        if d["users"] != _data()["users"]:
            _save(d)
            audit("login_assigned", by, username=u, hospital=h, before=before)
        return h


def unassign(username, by) -> bool:
    """Take a login out of the registry (it then belongs to "default"). True when it was registered. Audited (login_unassigned)."""
    u = str(username or "").strip().lower()
    with _lock:
        d = copy.deepcopy(_data())
        was = d["users"].pop(u, None)
        if was is None:
            return False
        _save(d)
        audit("login_unassigned", by, username=u, hospital=was)
        return True
