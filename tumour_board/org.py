"""Hospital organisation and permissions: one hospital, its departments and the users mapped to them (plan item 2.1).

data/tumour_board/org.json (edited by the admin):
  {"hospital": {"name": "", "level": "essential" | "optimal", "type": "" | "public" | "private"},
   "departments": [{"id": "radio_diagnosis", "name": "Radio-diagnosis", "aliases": ["Radiology", ...]}, ...],
   "users": {"<username>": {"departments": {"<dept_id>": "member" | "head"}, "coordinator": false, "display_name": ""}},
   "admins": ["<username>", ...]}

Logins stay the existing Vaidyx accounts; this file only maps a username to Tumour Board roles. Vaidyx admins are always
Tumour Board admins; `admins` lists extra TB admins. hospital.level is the NCG resource tier (default essential);
hospital.type decides the PM-JAY paperwork. Department names are Indian defaults; aliases map the protocols'
"Responsible Department" names (Radiology, GI Oncology, Pulmonology, Tumour Board coordinator, ...) and common variants
onto a department.

Permissions: every route asks one question, can(roles(user), action, department), and require() turns a "no" into
PermissionError (the route answers 403 and the UI hides the control). Unknown actions are refused (fail closed).
Every change to the organisation is appended to org_audit.jsonl.
"""
import copy, json, logging, re
from pathlib import Path

from . import config
from .store import _read_json, _write_json, now_iso

log = logging.getLogger(__name__)

DEFAULT_DEPARTMENTS = [
    {"id": "radio_diagnosis", "name": "Radio-diagnosis", "aliases": ["Radiology", "Radiodiagnosis", "Imaging"]},
    {"id": "pathology", "name": "Pathology", "aliases": ["Histopathology", "Cytology"]},
    {"id": "molecular_pathology", "name": "Molecular Pathology", "aliases": ["Molecular"]},
    {"id": "nuclear_medicine", "name": "Nuclear Medicine", "aliases": ["Nuclear"]},
    {"id": "medical_oncology", "name": "Medical Oncology", "aliases": ["Oncology", "GI Oncology"]},
    {"id": "surgical_oncology", "name": "Surgical Oncology", "aliases": ["Surgery", "Oncosurgery"]},
    {"id": "radiation_oncology", "name": "Radiation Oncology", "aliases": ["Radiotherapy"]},
    {"id": "laboratory_medicine", "name": "Laboratory Medicine", "aliases": ["Laboratory", "Lab", "Biochemistry", "Haematology"]},
    {"id": "gastroenterology", "name": "Gastroenterology", "aliases": ["GI", "Endoscopy"]},
    {"id": "pulmonary_medicine", "name": "Pulmonary Medicine", "aliases": ["Pulmonology", "Chest Medicine", "Respiratory Medicine"]},
    {"id": "general_medicine", "name": "General Medicine", "aliases": ["Medicine"]},
    {"id": "tumour_board", "name": "Tumour Board coordination", "aliases": ["Tumour Board coordinator", "Coordinator", "MDT coordinator"]},
]
DEFAULT_ORG = {"hospital": {"name": "", "level": "essential", "type": ""}, "departments": DEFAULT_DEPARTMENTS, "users": {}, "admins": []}
LEVELS = ("essential", "optimal")
TYPES = ("", "public", "private")
DEPT_ROLES = ("member", "head")

# Who may do what. "who" lists the roles allowed: "member" / "head" mean of the department named in the call (for a
# department-scoped action), "coordinator" is the hospital-level flag, "known" is anyone mapped in org.json, "any" is
# any logged-in user. Admins may do everything that is listed here.
# A department-scoped action called without a department (a document uploaded straight into a Case File by the
# coordinator, a document from before departments existed, an action with no Responsible Department) is decided by
# "no_dept" alone: such an item belongs to the coordinator, never to a member / head of some other department. Every
# department-scoped action declares "no_dept"; a missing one means admin only (fail closed). A department name that
# does not resolve (e.g. "Cardiology") matches no membership: "who" applies with no department role, so only the
# coordinator (where "who" lists it) and admins qualify.
ACTIONS = {
    "view": {"who": ("any",), "dept": False, "doc": "Open the Tumour Board pages (any logged-in user)"},
    "upload": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
               "doc": "Upload a document for a department (no department: coordinator)"},
    "upload_to_case": {"who": ("coordinator",), "dept": False, "doc": "Upload straight into a Case File"},
    "inbox": {"who": ("member", "head"), "dept": True, "no_dept": (),
              "doc": "See a department's inbox (no department: admin; an inbox always has a department)"},
    "confirm": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
                "doc": "Confirm a department's document (no department: coordinator)"},
    "waive": {"who": ("head",), "dept": True, "no_dept": (), "doc": "Waive a requirement for a department (no department: admin)"},
    "dismiss_failed": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
                       "doc": "Dismiss a failed document (same as confirm)"},
    "list_case": {"who": ("coordinator",), "dept": False, "doc": "List Case Files"},
    "match": {"who": ("coordinator",), "dept": False, "doc": "Run the matching queue"},
    "session": {"who": ("coordinator",), "dept": False, "doc": "Run board sessions"},
    "create_case": {"who": ("coordinator",), "dept": False, "doc": "Create a Case File"},
    "delete_case": {"who": ("coordinator",), "dept": False, "doc": "Delete a Case File"},
    "board_record": {"who": ("coordinator",), "dept": False, "doc": "Record the board discussion"},
    "delete_document": {"who": ("head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
                        "doc": "Delete a department's document (no department: coordinator)"},
    "update_action": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
                      "doc": "Update a pending action for a department (no department: coordinator)"},
    "review": {"who": ("known",), "dept": False, "doc": "Expert review of an AI artefact (human oversight)"},
    "manage_org": {"who": (), "dept": False, "doc": "Edit the hospital, departments and users (admin only)"},
}

_SLUG = re.compile(r"^[a-z0-9_]+$")
_UNKNOWN = object()  # a department name that does not resolve: matches no membership
_cache: dict = {}


def path() -> Path:
    return Path(config.DATA_ROOT) / "org.json"


def _audit_path() -> Path:
    return Path(config.DATA_ROOT) / "org_audit.jsonl"


def _filled(org) -> dict:
    """A copy of `org` with every missing top-level and hospital key taken from DEFAULT_ORG."""
    out = copy.deepcopy(org) if isinstance(org, dict) else {}
    for k, v in DEFAULT_ORG.items():
        if k not in out or out[k] is None:
            out[k] = copy.deepcopy(v)
    if isinstance(out["hospital"], dict):
        out["hospital"] = {**DEFAULT_ORG["hospital"], **out["hospital"]}
    return out


def _stat_key(p: Path):
    st = p.stat()
    return (str(p), st.st_mtime_ns, st.st_size)


def load() -> dict:
    """The organisation. Created with the defaults on first use; a partly filled file gets the missing keys.

    Cached by file mtime: the same object is returned until org.json changes, so treat it as read-only (change a deep
    copy and save() it). A file that fails validation is still used as read (logged), and a file that cannot be parsed
    falls back to the defaults without overwriting it; roles() only honours known departments and roles either way."""
    p = path()
    if not p.exists():
        _write_json(p, copy.deepcopy(DEFAULT_ORG))
    try:
        key = _stat_key(p)
    except FileNotFoundError:
        return _filled(DEFAULT_ORG)
    if _cache.get("key") == key:
        return _cache["org"]
    try:
        raw = _read_json(p, {})
    except (ValueError, OSError) as e:
        log.warning("org.json could not be read (%s); using the default departments", e)
        return _filled(DEFAULT_ORG)
    org = _filled(raw)
    try:
        org = validate(org)
    except ValueError as e:
        log.warning("org.json does not validate (%s); using it as read", e)
    _cache.update(key=key, org=org)
    return org


def save(org: dict, by: str) -> dict:
    """Validate, write org.json atomically and append an org_saved entry to org_audit.jsonl."""
    clean = validate(org)
    p = path()
    _write_json(p, clean)
    ev = {"ts": now_iso(), "by": by or "", "kind": "org_saved", "departments": len(clean["departments"]), "users": len(clean["users"])}
    a = _audit_path()
    a.parent.mkdir(parents=True, exist_ok=True)
    with open(a, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    _cache.update(key=_stat_key(p), org=clean)
    return clean


def _norm(s: str) -> str:
    """Matching key: lower case, hyphens / underscores / runs of spaces as one space ("radio_diagnosis" == "Radio-diagnosis")."""
    return re.sub(r"[\s_\-]+", " ", str(s or "")).strip().lower()


def validate(org: dict) -> dict:
    """A cleaned copy of `org`, or ValueError with a plain message. Unknown keys are kept (forward compatible).

    Rules: department ids are unique slugs ([a-z0-9_]+); names are non-empty and unique; aliases are a list of text and
    no id, name or alias may point at two departments (routing must be unambiguous); users map existing department ids to
    member / head; coordinator is true / false; hospital level and type are from the allowed sets; admins is a list of text."""
    if not isinstance(org, dict):
        raise ValueError("The organisation must be an object.")
    out = _filled(org)
    h = out["hospital"]
    if not isinstance(h, dict):
        raise ValueError("Hospital must be an object.")
    h["name"] = str(h.get("name") or "").strip()
    if h.get("level") not in LEVELS:
        raise ValueError(f"Hospital level must be one of: {', '.join(LEVELS)}.")
    if (h.get("type") or "") not in TYPES:
        raise ValueError("Hospital type must be public, private or empty.")
    h["type"] = h.get("type") or ""

    if not isinstance(out["departments"], list):
        raise ValueError("Departments must be a list.")
    depts, ids, names, keys = [], set(), set(), {}
    for d in out["departments"]:
        if not isinstance(d, dict):
            raise ValueError("Each department must be an object.")
        d = dict(d)
        did = d.get("id")
        if not isinstance(did, str) or not _SLUG.match(did):
            raise ValueError(f"Department id {did!r} must use only lower-case letters, digits and underscores.")
        if did in ids:
            raise ValueError(f"Department id {did!r} is used twice.")
        name = str(d.get("name") or "").strip()
        if not name:
            raise ValueError(f"Department {did!r} needs a name.")
        if name.lower() in names:
            raise ValueError(f"Department name {name!r} is used twice.")
        aliases = d.get("aliases") or []
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ValueError(f"Aliases of department {name!r} must be a list of text.")
        d["name"], d["aliases"] = name, [a.strip() for a in aliases if a.strip()]
        for k in {_norm(did), _norm(name), *(_norm(a) for a in d["aliases"])}:
            if keys.get(k, did) != did:
                raise ValueError(f"{k!r} would route to both {keys[k]!r} and {did!r}.")
            keys[k] = did
        ids.add(did)
        names.add(name.lower())
        depts.append(d)
    out["departments"] = depts

    if not isinstance(out["users"], dict):
        raise ValueError("Users must be an object keyed by username.")
    users = {}
    for uname, u in out["users"].items():
        if not isinstance(uname, str) or not uname.strip():
            raise ValueError("Every user needs a username.")
        if not isinstance(u, dict):
            raise ValueError(f"User {uname!r} must be an object.")
        u = dict(u)
        dmap = u.get("departments") or {}
        if not isinstance(dmap, dict):
            raise ValueError(f"Departments of user {uname!r} must map department id to role.")
        for did, role in dmap.items():
            if did not in ids:
                raise ValueError(f"User {uname!r} is mapped to unknown department {did!r}.")
            if role not in DEPT_ROLES:
                raise ValueError(f"User {uname!r} has role {role!r} in {did!r}; the role must be member or head.")
        if not isinstance(u.get("coordinator", False), bool):
            raise ValueError(f"Coordinator for user {uname!r} must be true or false.")
        u["departments"], u["coordinator"] = dict(dmap), u.get("coordinator", False)
        u["display_name"] = str(u.get("display_name") or "").strip()
        users[uname.strip()] = u
    out["users"] = users

    admins = out["admins"]
    if not isinstance(admins, list) or not all(isinstance(a, str) for a in admins):
        raise ValueError("Admins must be a list of usernames.")
    out["admins"] = list(dict.fromkeys(a.strip() for a in admins if a.strip()))
    return out


def departments() -> list[dict]:
    return [d for d in load()["departments"] if isinstance(d, dict)]


def department(dept_id) -> dict | None:
    return next((d for d in departments() if d.get("id") == dept_id), None)


_PREFIX = re.compile(r"^(?:the\s+)?(?:department|dept\.?)\s+of\s+", re.I)
_SUFFIX = re.compile(r"\s+(?:department|dept\.?)$", re.I)


def department_id(name_or_alias: str) -> str | None:
    """The department id for an id, name or alias (protocol "Responsible Department" names), case-insensitive.

    "Department of Radio-diagnosis", "Dept. of Pathology" and "Pathology Department" resolve like the bare name.
    None when nothing matches: the caller routes it to the coordinator rather than guessing."""
    s = str(name_or_alias or "").strip()
    if not s:
        return None
    s = _SUFFIX.sub("", _PREFIX.sub("", s)).strip()
    want = _norm(s)
    for d in departments():
        if want in {_norm(d.get("id")), _norm(d.get("name")), *(_norm(a) for a in d.get("aliases") or [])}:
            return d.get("id")
    return None


def department_name(dept_id) -> str:
    d = department(dept_id)
    return d["name"] if d else str(dept_id or "")


def roles(username: str, vaidyx_admin: bool = False) -> dict:
    """The Tumour Board roles of a Vaidyx login.

    admin: a Vaidyx admin or listed in org.json admins. An empty username means authentication is off (single-user
    mode): there is no login to tie a role to, so that user is treated as admin. This only happens when the main app
    runs with AUTH_ENABLED=false or through its localhost bypass; ~/vaidyx/start_vaidyx_app.sh sets neither, so a
    normal deployment always has a username. Only existing departments and the
    roles member / head are honoured, even if org.json was edited by hand. known: admin, coordinator or a member of at
    least one department."""
    username = str(username or "").strip()
    org = load()
    ids = {d.get("id") for d in departments()}
    u = (org.get("users") or {}).get(username) if username else None
    u = u if isinstance(u, dict) else {}
    dmap = u.get("departments") if isinstance(u.get("departments"), dict) else {}
    depts = {k: v for k, v in dmap.items() if k in ids and v in DEPT_ROLES}
    admin = (not username) or bool(vaidyx_admin) or username in (org.get("admins") or [])
    coordinator = u.get("coordinator") is True
    return {"user": username, "admin": admin, "coordinator": coordinator, "departments": depts,
            "known": admin or coordinator or bool(depts)}


def _allowed(r: dict, who, department) -> bool:
    if "any" in who:
        return True
    if "known" in who and r.get("known"):
        return True
    if "coordinator" in who and r.get("coordinator"):
        return True
    want = {x for x in who if x in DEPT_ROLES}  # a head is also a member: rules open to members list both
    if department is None:  # no department named: no department role counts (can() passes None only for that case)
        return False
    return (r.get("departments") or {}).get(department) in want


def can(r: dict, action: str, department: str | None = None) -> bool:
    """True if the user with roles `r` may do `action` (for `department`: an id, name or alias, passed raw; it is
    resolved here, so "Radiology" and "radio_diagnosis" are the same). See ACTIONS.

    Admins may do every listed action; an unknown action is refused for everyone. A department-scoped action with no
    (or an empty) department follows its "no_dept" rule (admin only if none is declared): a member / head of some
    department never qualifies through it. A department that does not resolve matches no membership (coordinators and
    admins keep their hospital-wide rights where "who" lists them)."""
    rule = ACTIONS.get(action)
    if rule is None or not isinstance(r, dict):
        return False
    if r.get("admin"):
        return True
    who = rule["who"]
    dept = None
    if rule["dept"]:
        if department is not None and str(department).strip():
            dept = department_id(department) or _UNKNOWN
        else:
            who = rule.get("no_dept", ())
    return _allowed(r, who, dept)


def require(r: dict, action: str, department: str | None = None) -> None:
    """PermissionError (the route answers 403) unless can(r, action, department)."""
    if can(r, action, department):
        return
    where = f" for {department_name(department_id(department) or department)}" if department else ""
    raise PermissionError(f"You do not have permission for '{action}'{where}. Ask a Tumour Board admin if you need it.")


def my_departments(r: dict) -> list[dict]:
    """The departments the user belongs to (every department for an admin), each with the user's "role" added."""
    mine = (r or {}).get("departments") or {}
    return [{**d, "role": mine.get(d.get("id"))} for d in departments() if (r or {}).get("admin") or d.get("id") in mine]


def visible_departments_for_inbox(r: dict) -> list[str]:
    """Department ids whose inbox the user may see: members and heads their own, admins all, coordinators none (unless
    they are also a member somewhere)."""
    return [d["id"] for d in departments() if can(r, "inbox", d["id"])]
