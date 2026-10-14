"""Hospital organisation and permissions: one hospital, its treating and supporting departments and the users mapped to them
(V1 item 2.1; V2 items 2.1, 2.2 and 2.4).

data/tumour_board/org.json (edited by the root admin through the Organisation screen):
  {"version": 2,
   "hospital": {"name": "", "level": "essential" | "optimal", "type": "" | "public" | "private",
                "pmjay_empanelled": true, "fetch_window_months": 12},
   "departments": [{"id": "radiology", "name": "Radiology", "group": "supporting", "aliases": ["Radio-diagnosis", ...],
                    "email": "radiology@hospital.example"}, ...],
   "users": {"<username>": {"departments": {"<dept_id>": "member" | "head"}, "admin_of": ["<dept_id>", ...],
                            "coordinator": false, "display_name": "", "disabled": false}},
   "admins": ["<username>", ...],
   "routes": {"<protocol>.<record>": "<dept_id>" | "owner" | "coordinator"}}

Logins stay the existing Vaidyx accounts; this file only maps a username to Tumour Board roles (V2 plan section 4):
  root admin        `admins`: the Tumour Board super-admins (plain Vaidyx accounts named by the Vaidyx admin). Vaidyx admins are
                    Tumour Board admins as well, so the first root admin can be named. No Tumour Board action grants Vaidyx admin.
  department admin  `admin_of`: manages the doctor logins of those departments (and may also be a doctor somewhere).
  doctor            `departments`: member or head of a department; a treating or a supporting doctor by the department's group.
  MDT Coordinator   `coordinator`: board sessions, agendas, readiness, reminders, minutes. Not a department any more (V1 had
                    "Tumour Board coordination" as one); actions and notifications for the coordinator use the role.
  disabled          `disabled`: a Tumour Board flag that blocks every Tumour Board action (the Vaidyx login itself is untouched).

Departments: the 22 treating and 8 supporting departments of the plan (section 4) are the defaults; the root admin adds, renames or
moves them. hospital.level is the NCG resource tier (default essential); hospital.type decides the PM-JAY paperwork;
pmjay_empanelled turns the PM-JAY board-composition flag on (V2 item 6.4); fetch_window_months is the hospital default for the
HIS fetch window (V2 item 3.2). Aliases map the protocols' "Responsible Department" names (Radiology, GI Oncology, Pulmonology,
Laboratory Medicine, ...) and common variants onto a department. The V1 department ids and names stay as aliases, so documents,
actions, sessions and notifications stored with a V1 id ("radio_diagnosis") still resolve. A V1 file is migrated on first load
(migrate_v1), audited as org_migrated.

Permissions: every route asks one question, can(roles(user), action, department), and require() turns a "no" into
PermissionError (the route answers 403 and the UI hides the control). Unknown actions are refused (fail closed); a disabled user
can do nothing. Every change to the organisation and to accounts is appended to org_audit.jsonl.
"""
import copy, json, logging, re
from pathlib import Path

from . import config
from .store import _read_json, _write_json, now_iso

log = logging.getLogger(__name__)

VERSION = 2
GROUPS = ("treating", "supporting")
PLACEHOLDER_DOMAIN = "hospital.example"  # reserved name (RFC 2606): a placeholder until the hospital gives its addresses (plan section 11)


def _d(id_, name, group, aliases=()):
    return {"id": id_, "name": name, "group": group, "aliases": list(aliases), "email": f"{id_}@{PLACEHOLDER_DOMAIN}"}


# The plan's section 4: 22 treating departments (20 from the hospital's list + 2 added) and 8 supporting (6 + 2). Aliases carry
# the protocols' Responsible Department names, the V1 department names (whose ids normalise to the same key: "radio_diagnosis"
# == "Radio-diagnosis") and common Indian variants. No alias may point at two departments (validate()).
DEFAULT_DEPARTMENTS = [
    _d("general_surgery", "General Surgery", "treating", ["Gen Surgery"]),
    _d("surgical_oncology", "Surgical Oncology", "treating", ["Surgery", "Oncosurgery", "Surgical Oncology Unit"]),
    _d("medical_oncology", "Medical Oncology", "treating", ["Oncology", "GI Oncology", "Medical Oncology Unit"]),
    _d("radiation_oncology", "Radiation Oncology", "treating", ["Radiotherapy"]),
    _d("breast_surgery", "Breast Surgery", "treating", ["Breast Surgical Oncology", "Breast Unit"]),
    _d("gynaecologic_oncology", "Gynaecologic Oncology", "treating", ["Gynae Oncology", "Gynaecological Oncology", "Gyn Onc"]),
    _d("ent_head_neck_surgery", "ENT / Head and Neck Surgery", "treating", ["ENT", "Head and Neck Surgery", "Head and Neck Oncology", "Otorhinolaryngology"]),
    _d("urology", "Urology", "treating", ["Uro-oncology"]),
    _d("gastrointestinal_surgery", "Gastrointestinal Surgery", "treating", ["GI Surgery", "Surgical Gastroenterology"]),
    _d("pulmonology", "Pulmonology", "treating", ["Pulmonary Medicine", "Chest Medicine", "Respiratory Medicine"]),
    _d("thoracic_surgery", "Thoracic Surgery", "treating", ["Cardiothoracic Surgery", "CTVS"]),
    _d("neurosurgery", "Neurosurgery", "treating", ["Neurosurgical Oncology"]),
    _d("orthopaedic_oncology", "Orthopaedic Oncology", "treating", ["Orthopaedics", "Bone and Soft Tissue"]),
    _d("paediatric_oncology", "Paediatric Oncology", "treating", ["Pediatric Oncology"]),
    _d("haematology", "Haematology", "treating", ["Hematology", "Clinical Haematology", "Haemato-oncology"]),
    _d("gynaecology", "Gynaecology", "treating", ["Obstetrics and Gynaecology", "OBG"]),
    _d("hepatobiliary_pancreatic_surgery", "Hepatobiliary and Pancreatic Surgery", "treating", ["HPB Surgery", "HPB"]),
    _d("colorectal_surgery", "Colorectal Surgery", "treating", ["Colorectal"]),
    _d("plastic_reconstructive_surgery", "Plastic and Reconstructive Surgery", "treating", ["Plastic Surgery"]),
    _d("dermatology", "Dermatology", "treating", ["Skin"]),
    _d("medical_gastroenterology", "Medical Gastroenterology", "treating", ["Gastroenterology", "GI", "Endoscopy", "Gastro"]),
    _d("palliative_medicine", "Palliative Medicine", "treating", ["Palliative Care", "Pain and Palliative Medicine"]),
    _d("radiology", "Radiology", "supporting", ["Radio-diagnosis", "Radiodiagnosis", "Imaging"]),
    _d("pathology", "Pathology", "supporting", ["Histopathology", "Cytology", "Molecular Pathology", "Molecular", "Haematopathology", "Clinical Pathology"]),
    _d("microbiology", "Microbiology", "supporting", ["Virology", "Serology"]),
    _d("biochemistry", "Biochemistry", "supporting", ["Laboratory Medicine", "Laboratory", "Lab", "Clinical Biochemistry"]),
    _d("nuclear_medicine", "Nuclear Medicine", "supporting", ["Nuclear", "PET Centre"]),
    _d("clinical_pharmacology", "Clinical Pharmacology", "supporting", ["Pharmacology"]),
    _d("dental_surgery", "Dental Surgery / Oral and Maxillofacial Surgery", "supporting", ["Dental Surgery", "Dental", "Oral and Maxillofacial Surgery", "OMFS", "Dentistry"]),
    _d("anaesthesiology", "Anaesthesiology", "supporting", ["Anaesthesia", "Anesthesiology", "Pre-anaesthetic check-up", "PAC"]),
]
# The board (V2 item 6.1 / 6.2 / 6.4): the four heads (each must have a specialty agent: board.ROLE_DEPARTMENT), the departments the
# hospital's attendance sheet lists besides them and the owners of the Case Files on the agenda, the departments whose surgeon fills the
# surgical seat for a Case File of its own, and the departments PM-JAY HBP 2.2 accepts as the surgical oncologist (plan section 8, 6.4).
BOARD_HEADS = ["radiology", "medical_oncology", "surgical_oncology", "pathology"]
SURGICAL_DEPARTMENTS = ["surgical_oncology", "general_surgery", "breast_surgery", "gynaecologic_oncology", "ent_head_neck_surgery", "urology",
                        "gastrointestinal_surgery", "thoracic_surgery", "neurosurgery", "orthopaedic_oncology", "hepatobiliary_pancreatic_surgery",
                        "colorectal_surgery", "plastic_reconstructive_surgery"]
PMJAY_SURGICAL_ONCOLOGY = ["surgical_oncology", "gynaecologic_oncology", "orthopaedic_oncology"]
DEFAULT_HOSPITAL = {"name": "", "level": "essential", "type": "", "pmjay_empanelled": True, "fetch_window_months": 12,
                    "board_heads": list(BOARD_HEADS), "board_attendance": [], "surgical_departments": list(SURGICAL_DEPARTMENTS),
                    "pmjay_surgical_oncology": list(PMJAY_SURGICAL_ONCOLOGY)}
BOARD_LISTS = ("board_heads", "board_attendance", "surgical_departments", "pmjay_surgical_oncology")  # hospital keys that list department ids
DEFAULT_ORG = {"version": VERSION, "hospital": DEFAULT_HOSPITAL, "departments": DEFAULT_DEPARTMENTS, "users": {}, "admins": [], "routes": {}}
LEVELS = ("essential", "optimal")
TYPES = ("", "public", "private")
DEPT_ROLES = ("member", "head")
ROLE_SYNONYMS = {"doctor": "member"}  # the UI says "doctor"; the stored role stays "member" (V1 files)
FETCH_WINDOW_RANGE = (1, 120)  # months

# V1 (12 departments) -> V2: where each V1 department's users and stored ids go (plan 2.1 migration table). An empty list means the
# department is removed: General Medicine's records go to the owning department (V2 item 2.4); Tumour Board coordination became the
# MDT Coordinator role (its users get coordinator = true).
V1_MIGRATION = {
    "radio_diagnosis": ["radiology"], "pathology": ["pathology"], "molecular_pathology": ["pathology"], "nuclear_medicine": ["nuclear_medicine"],
    "medical_oncology": ["medical_oncology"], "surgical_oncology": ["surgical_oncology"], "radiation_oncology": ["radiation_oncology"],
    "laboratory_medicine": ["biochemistry", "pathology"], "gastroenterology": ["medical_gastroenterology"], "pulmonary_medicine": ["pulmonology"],
    "general_medicine": [], "tumour_board": [],
}
COORDINATOR_ID = "coordinator"  # the MDT Coordinator as an inbox / routing target (a role, not a department)
COORDINATOR_NAME = "MDT Coordinator"
_COORDINATOR_NAMES = {"coordinator", "mdt coordinator", "mdt coordination", "tumour board coordinator", "tumour board coordination", "tumour board"}
OWNER_ID = "owner"  # routing target: the Case File's owning treating department (V2 items 2.4 / 5.1)
OWNER_NAME = "Owning department"

# Who may do what. "who" lists the roles allowed: "member" / "head" mean of the department named in the call (for a
# department-scoped action), "dept_admin" is a department admin of the department named in the call, "root_admin" the Tumour Board
# super-admin (organisation and accounts, never a clinical action: plan section 4), "treating" / "supporting" is a member or head of
# any department of that group, "coordinator" is the hospital-level flag, "known" is anyone placed (a doctor, coordinator or admin),
# "any" is any logged-in user. Vaidyx admins (`admin`) may do everything listed.
# A department-scoped action called without a department (a document uploaded straight into a Case File by the
# coordinator, a document from before departments existed, an action with no Responsible Department) is decided by
# "no_dept" alone: such an item belongs to the coordinator, never to a member / head of some other department. Every
# department-scoped action declares "no_dept"; a missing one means admin only (fail closed). A department name that
# does not resolve (e.g. "Cardiology") matches no membership: "who" applies with no department role, so only the
# coordinator (where "who" lists it) and admins qualify.
ACTIONS = {
    "view": {"who": ("any",), "dept": False, "doc": "Open the Tumour Board pages (any logged-in user)"},
    "upload": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
               "doc": "Upload a document for a department (no department: coordinator); the V1 path, kept for tests and outside-report intake (V2 item 3.7)"},
    "upload_to_case": {"who": ("coordinator", "treating"), "dept": False, "doc": "Upload straight into a Case File (outside reports: treating doctors)"},
    "inbox": {"who": ("member", "head"), "dept": True, "no_dept": (),
              "doc": "See a department's inbox (no department: admin; an inbox always has a department)"},
    "confirm": {"who": ("member", "head", "treating"), "dept": True, "no_dept": ("treating",),
                "doc": "Confirm a document: a treating doctor, or the department that uploaded it (no department: treating doctors)"},
    "waive": {"who": ("treating",), "dept": True, "no_dept": ("treating",),
              "doc": "Waive a requirement: treating doctors (the owning department from V2 item 5.1); never a supporting department or the coordinator"},
    "dismiss_failed": {"who": ("member", "head", "treating"), "dept": True, "no_dept": ("treating",),
                       "doc": "Dismiss a failed document (same as confirm)"},
    "list_case": {"who": ("coordinator",), "dept": False, "doc": "List Case Files for the board"},
    "match": {"who": ("coordinator",), "dept": False, "doc": "Run the matching queue"},
    "session": {"who": ("coordinator",), "dept": False, "doc": "Run board sessions"},
    "create_case": {"who": ("coordinator", "treating"), "dept": False, "doc": "Create a Case File (treating doctors; the coordinator for the V1 path)"},
    "delete_case": {"who": ("coordinator",), "dept": False, "doc": "Delete a Case File"},
    "board_record": {"who": ("coordinator",), "dept": False, "doc": "Record the board discussion"},
    "delete_document": {"who": ("head", "coordinator", "treating"), "dept": True, "no_dept": ("coordinator", "treating"),
                        "doc": "Delete a document: a treating doctor, the uploading department's head or the coordinator"},
    "send_request": {"who": ("treating",), "dept": False,
                     "doc": "Send (or send again as a reminder) a Pre-Authorization request the gate suggested, in-app or as a mail draft (treating doctors; V2 item 4.2)"},
    "create_request": {"who": ("treating",), "dept": False,
                       "doc": "Write a request to a department with no protocol record behind it, for example a pre-anaesthetic check (treating doctors; V2 item 4.2)"},
    "answer_request": {"who": ("member", "head"), "dept": True, "no_dept": ("coordinator",),
                       "doc": "Acknowledge a request sent to a department and send \"done\" back: the doctors of that department (no department: a request addressed to the MDT Coordinator, answered by the coordinator; V2 item 4.3)"},
    "close_request": {"who": ("treating",), "dept": False,
                      "doc": "Close a request that has no protocol record behind it (treating doctors; a gap request closes by itself when the record arrives)"},
    "update_action": {"who": ("member", "head", "coordinator"), "dept": True, "no_dept": ("coordinator",),
                      "doc": "Update a pending action for a department (no department: coordinator)"},
    "review": {"who": ("known",), "dept": False, "doc": "Expert review of an AI artefact (human oversight)"},
    "manage_org": {"who": ("root_admin",), "dept": False, "doc": "Edit the hospital, departments, routes, root admins, coordinators and department admins (root admin)"},
    "manage_department": {"who": ("dept_admin", "root_admin"), "dept": True, "no_dept": ("root_admin",),
                          "doc": "Create, disable and remove the doctor logins of a department (its department admins and the root admin)"},
    "read_case": {"who": ("known",), "dept": False, "doc": "Read Case Files, board sessions, the intake queue and the dashboard (anyone placed: doctors, the coordinator, admins; not a department admin or root admin). Per Case File, access.scope() narrows this to the owner, the participants, the coordinator and the departments asked (V2 item 5.1)"},
    "refer": {"who": ("treating",), "dept": False,
              "doc": "Refer the Case File to another treating department (the owning department's doctors; V2 item 5.2)"},
    "answer_referral": {"who": ("member", "head"), "dept": True, "no_dept": (),
                        "doc": "Accept or decline a referral addressed to a department: the doctors of that department (V2 item 5.2)"},
    "manage_participants": {"who": ("treating",), "dept": False,
                            "doc": "Add or remove the departments that take part in a Case File, read and comment (the owning department's doctors; V2 item 5.1)"},
    "mark_ready": {"who": ("treating",), "dept": False,
                   "doc": "Mark a Case File ready for the board, or take the mark back (the owning department's doctors; the MDT Coordinator builds the agenda from these; V2 item 6.1)"},
    "remind": {"who": ("coordinator", "treating"), "dept": False,
               "doc": "Send a reminder about an open request to the department holding it, or about unsent suggestions to the owning department: the MDT Coordinator on the owner's behalf, or the owner's doctors (access.may_remind; V2 item 6.1)"},
}

_SLUG = re.compile(r"^[a-z0-9_]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UNKNOWN = object()  # a department name that does not resolve: matches no membership
_cache: dict = {}


def path() -> Path:
    return Path(config.DATA_ROOT) / "org.json"


def _audit_path() -> Path:
    return Path(config.DATA_ROOT) / "org_audit.jsonl"


def audit(kind: str, by: str, **fields) -> dict:
    """Append one organisation / account event to org_audit.jsonl (never a password) and return it."""
    ev = {"ts": now_iso(), "by": by or "", "kind": kind, **{k: v for k, v in fields.items() if k != "password"}}
    a = _audit_path()
    a.parent.mkdir(parents=True, exist_ok=True)
    with open(a, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    return ev


def read_audit(limit: int = 200) -> list[dict]:
    """The newest `limit` organisation / account events, newest first; a malformed line is skipped."""
    p = _audit_path()
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= max(1, limit):
            break
    return out


def _filled(org) -> dict:
    """A copy of `org` with every missing top-level and hospital key taken from DEFAULT_ORG."""
    out = copy.deepcopy(org) if isinstance(org, dict) else {}
    for k, v in DEFAULT_ORG.items():
        if k not in out or out[k] is None:
            out[k] = copy.deepcopy(v)
    if isinstance(out["hospital"], dict):
        out["hospital"] = {**DEFAULT_HOSPITAL, **out["hospital"]}
    return out


def _stat_key(p: Path):
    st = p.stat()
    return (str(p), st.st_mtime_ns, st.st_size)


def is_v1(org) -> bool:
    """A V1 file: no version (or an older one) and departments without a group."""
    if not isinstance(org, dict):
        return False
    try:
        ver = int(org.get("version") or 1)
    except (TypeError, ValueError):
        ver = 1
    return ver < VERSION


def migrate_v1(org: dict) -> tuple[dict, dict]:
    """The V2 organisation built from a V1 file: the plan's section 4 departments, the V1 departments' users re-placed by the
    migration table (Laboratory Medicine users land in Biochemistry and Pathology; Tumour Board coordination users become
    coordinators; General Medicine users lose that placement), custom V1 aliases merged where they stay unambiguous, unknown
    (hospital-added) V1 departments kept as supporting departments. Returns (org, report) without saving."""
    old = _filled(org)
    new = copy.deepcopy(DEFAULT_ORG)
    new["hospital"] = {**DEFAULT_HOSPITAL, **{k: v for k, v in (old.get("hospital") or {}).items() if k in DEFAULT_HOSPITAL}}
    by_id = {d["id"]: d for d in new["departments"]}
    report = {"departments": {}, "users": {}, "kept": [], "dropped_aliases": []}
    migration = dict(V1_MIGRATION)  # plus the hospital-added departments merged below

    def _taken():
        keys = {}
        for d in new["departments"]:
            for k in {_norm(d["id"]), _norm(d["name"]), *(_norm(a) for a in d.get("aliases") or [])}:
                keys[k] = d["id"]
        return keys

    for d in old.get("departments") or []:
        if not isinstance(d, dict) or not isinstance(d.get("id"), str):
            continue
        targets = migration.get(d["id"])
        if targets is None:  # a department the hospital added in V1: kept, as a supporting department (the safer group)
            taken = _taken()
            name = str(d.get("name") or d["id"])
            if d["id"] in by_id or _norm(name) in taken or _norm(d["id"]) in taken:  # its name or id already names a V2 department: merged into it
                report["departments"][d["id"]] = [taken.get(_norm(name)) or taken.get(_norm(d["id"])) or d["id"]]
                migration[d["id"]] = report["departments"][d["id"]]
                continue
            kept = {"id": d["id"], "name": name, "group": "supporting",
                    "aliases": [a.strip() for a in (d.get("aliases") or []) if isinstance(a, str) and a.strip() and _norm(a) not in taken and _norm(a) != _norm(name)],
                    "email": f"{d['id']}@{PLACEHOLDER_DOMAIN}"}
            report["dropped_aliases"] += [a for a in (d.get("aliases") or []) if isinstance(a, str) and a.strip() and _norm(a) in taken]
            new["departments"].append(kept)
            by_id[kept["id"]] = kept
            report["kept"].append(d["id"])
            continue
        report["departments"][d["id"]] = list(targets)
        if targets:
            taken = _taken()
            for a in d.get("aliases") or []:
                if not isinstance(a, str) or not a.strip():
                    continue
                k = _norm(a)
                if k in taken:
                    if taken[k] != targets[0]:
                        report["dropped_aliases"].append(a)
                    continue
                by_id[targets[0]]["aliases"].append(a.strip())
                taken[k] = targets[0]

    for uname, u in (old.get("users") or {}).items():
        if not isinstance(u, dict):
            continue
        nu = {"departments": {}, "admin_of": [], "coordinator": u.get("coordinator") is True,
              "display_name": str(u.get("display_name") or "").strip(), "disabled": False}
        for did, role in (u.get("departments") or {}).items():
            if did == "tumour_board":
                nu["coordinator"] = True
                continue
            for t in migration.get(did, [did] if did in by_id else []):
                if t in by_id and role in DEPT_ROLES:
                    nu["departments"][t] = role if nu["departments"].get(t) != "head" else "head"
        new["users"][uname] = nu
        report["users"][uname] = nu["departments"]
    new["admins"] = [a for a in (old.get("admins") or []) if isinstance(a, str)]
    for k, v in old.items():  # unknown keys are kept (forward compatible), as validate() does
        if k not in new and k != "version":
            new[k] = v
    return validate(new), report


def load() -> dict:
    """The organisation. Created with the defaults on first use; a partly filled file gets the missing keys; a V1 file is migrated,
    saved and audited.

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
    if is_v1(raw):
        try:
            org, report = migrate_v1(raw)
        except ValueError as e:
            log.warning("org.json (V1) could not be migrated (%s); using the default departments", e)
            return _filled(DEFAULT_ORG)
        _write_json(p, org)
        audit("org_migrated", "system", from_version=1, to_version=VERSION, departments=report["departments"], users=report["users"],
              kept=report["kept"], dropped_aliases=report["dropped_aliases"])
        log.info("org.json migrated from V1 to V%s", VERSION)
        _cache.update(key=_stat_key(p), org=org)
        return org
    org = _filled(raw)
    try:
        org = validate(org)
    except ValueError as e:
        log.warning("org.json does not validate (%s); using it as read", e)
    _cache.update(key=key, org=org)
    return org


def save(org: dict, by: str) -> dict:
    """Validate, write org.json atomically and append an org_saved entry to org_audit.jsonl, plus one entry per account whose roles
    changed (account_placed / account_roles_changed / account_unplaced), one when the root admins change and one when the routes change:
    every account change is audited whichever screen made it (V2 item 2.2)."""
    clean = validate(org)
    p = path()
    before = load() if p.exists() else _filled(DEFAULT_ORG)
    _write_json(p, clean)
    _cache.update(key=_stat_key(p), org=clean)
    audit("org_saved", by, departments=len(clean["departments"]), users=len(clean["users"]))
    old_users, new_users = before.get("users") or {}, clean["users"]
    for u in sorted(set(old_users) | set(new_users)):
        a, b = old_users.get(u), new_users.get(u)
        if a == b:
            continue
        if a is None:
            audit("account_placed", by, username=u, roles=b)
        elif b is None:
            audit("account_unplaced", by, username=u, roles_before=a)
        else:
            audit("account_roles_changed", by, username=u, roles_before=a, roles=b)
    if (before.get("admins") or []) != clean["admins"]:
        audit("root_admins_changed", by, before=before.get("admins") or [], after=clean["admins"])
    if (before.get("routes") or {}) != clean["routes"]:
        audit("routes_changed", by, before=before.get("routes") or {}, after=clean["routes"])
    return clean


def _norm(s: str) -> str:
    """Matching key: lower case, hyphens / underscores / runs of spaces as one space ("radio_diagnosis" == "Radio-diagnosis")."""
    return re.sub(r"[\s_\-]+", " ", str(s or "")).strip().lower()


def is_coordinator_name(s) -> bool:
    """True for the MDT Coordinator under any of its names (incl. the V1 department "Tumour Board coordination" and its id)."""
    return _norm(s) in _COORDINATOR_NAMES


def validate(org: dict) -> dict:
    """A cleaned copy of `org`, or ValueError with a plain message. Unknown keys are kept (forward compatible).

    Rules: department ids are unique slugs ([a-z0-9_]+); names are non-empty and unique; the group is treating or supporting; aliases
    are a list of text and no id, name or alias may point at two departments (routing must be unambiguous) or at the coordinator;
    an email, when given, looks like an address; users map existing department ids to member / head (doctor = member), admin_of
    lists existing department ids, coordinator and disabled are true / false; hospital level and type are from the allowed sets,
    pmjay_empanelled is true / false, fetch_window_months is 1 to 120; admins is a list of text; routes map "<protocol>.<record>"
    to a department id, "owner" or "coordinator"."""
    if not isinstance(org, dict):
        raise ValueError("The organisation must be an object.")
    out = _filled(org)
    out["version"] = VERSION
    h = out["hospital"]
    if not isinstance(h, dict):
        raise ValueError("Hospital must be an object.")
    h["name"] = str(h.get("name") or "").strip()
    if h.get("level") not in LEVELS:
        raise ValueError(f"Hospital level must be one of: {', '.join(LEVELS)}.")
    if (h.get("type") or "") not in TYPES:
        raise ValueError("Hospital type must be public, private or empty.")
    h["type"] = h.get("type") or ""
    if not isinstance(h.get("pmjay_empanelled", True), bool):
        raise ValueError("PM-JAY empanelled must be true or false.")
    h["pmjay_empanelled"] = h.get("pmjay_empanelled", True)
    try:
        fw = int(h.get("fetch_window_months", 12))
    except (TypeError, ValueError):
        raise ValueError("The fetch window must be a number of months.")
    if not FETCH_WINDOW_RANGE[0] <= fw <= FETCH_WINDOW_RANGE[1]:
        raise ValueError(f"The fetch window must be {FETCH_WINDOW_RANGE[0]} to {FETCH_WINDOW_RANGE[1]} months.")
    h["fetch_window_months"] = fw
    fs = h.get("first_setup")  # the stamp of the answered first set-up (V2 item 7.1); absent until the root admin answers it once
    if fs is None:
        h.pop("first_setup", None)
    elif isinstance(fs, dict):
        h["first_setup"] = {"at": str(fs.get("at") or ""), "by": str(fs.get("by") or "")}
    else:
        raise ValueError("first_setup must be an object with at and by.")

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
        if did in (COORDINATOR_ID, OWNER_ID):
            raise ValueError(f"{did!r} is reserved (the MDT Coordinator role / the owning department) and cannot be a department id.")
        name = str(d.get("name") or "").strip()
        if not name:
            raise ValueError(f"Department {did!r} needs a name.")
        if name.lower() in names:
            raise ValueError(f"Department name {name!r} is used twice.")
        group = d.get("group")
        if group not in GROUPS:
            raise ValueError(f"Department {name!r} needs a group: treating or supporting.")
        aliases = d.get("aliases") or []
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ValueError(f"Aliases of department {name!r} must be a list of text.")
        email = str(d.get("email") or "").strip()
        if email and not _EMAIL.match(email):
            raise ValueError(f"The email of department {name!r} does not look like an address.")
        d["name"], d["group"], d["aliases"], d["email"] = name, group, [a.strip() for a in aliases if a.strip()], email
        for k in {_norm(did), _norm(name), *(_norm(a) for a in d["aliases"])}:
            if k in _COORDINATOR_NAMES:
                raise ValueError(f"{k!r} names the MDT Coordinator (a role) and cannot be a department.")
            if keys.get(k, did) != did:
                raise ValueError(f"{k!r} would route to both {keys[k]!r} and {did!r}.")
            keys[k] = did
        ids.add(did)
        names.add(name.lower())
        depts.append(d)
    out["departments"] = depts
    for key in BOARD_LISTS:  # the board lists name existing departments, each once (V2 items 6.1 / 6.2 / 6.4)
        lst = h.get(key, DEFAULT_HOSPITAL[key])
        if lst is None:
            lst = []
        if not isinstance(lst, list) or not all(isinstance(x, str) for x in lst):
            raise ValueError(f"Hospital setting {key} must be a list of department ids.")
        clean = []
        for x in lst:
            x = x.strip()
            if x and x not in ids:
                raise ValueError(f"Hospital setting {key} names an unknown department {x!r}.")
            if x and x not in clean:
                clean.append(x)
        if key == "board_heads" and not clean:
            raise ValueError("The board needs at least one head (hospital setting board_heads).")
        h[key] = clean

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
        clean_map = {}
        for did, role in dmap.items():
            cid = did if did in ids else keys.get(_norm(did))  # a V1 id or an alias resolves to its department
            if not cid:
                raise ValueError(f"User {uname!r} is mapped to unknown department {did!r}.")
            role = ROLE_SYNONYMS.get(role, role)
            if role not in DEPT_ROLES:
                raise ValueError(f"User {uname!r} has role {role!r} in {did!r}; the role must be member (doctor) or head.")
            clean_map[cid] = "head" if "head" in (role, clean_map.get(cid)) else role
        adm = u.get("admin_of") or []
        if not isinstance(adm, list) or not all(isinstance(a, str) for a in adm):
            raise ValueError(f"admin_of for user {uname!r} must be a list of department ids.")
        clean_adm = []
        for did in adm:
            cid = did if did in ids else keys.get(_norm(did))
            if not cid:
                raise ValueError(f"User {uname!r} is department admin of unknown department {did!r}.")
            clean_adm.append(cid)
        for flag in ("coordinator", "disabled"):
            if not isinstance(u.get(flag, False), bool):
                raise ValueError(f"{flag} for user {uname!r} must be true or false.")
        u["departments"], u["admin_of"] = clean_map, list(dict.fromkeys(clean_adm))
        u["coordinator"], u["disabled"] = u.get("coordinator", False), u.get("disabled", False)
        u["display_name"] = str(u.get("display_name") or "").strip()
        users[uname.strip()] = u
    out["users"] = users

    admins = out["admins"]
    if not isinstance(admins, list) or not all(isinstance(a, str) for a in admins):
        raise ValueError("Admins must be a list of usernames.")
    out["admins"] = list(dict.fromkeys(a.strip() for a in admins if a.strip()))

    routes = out.get("routes") or {}
    if not isinstance(routes, dict):
        raise ValueError("Routes must map '<protocol>.<record>' to a department.")
    clean_routes = {}
    for key, target in routes.items():
        if not isinstance(key, str) or key.count(".") != 1 or not all(key.split(".")):
            raise ValueError(f"Route key {key!r} must be '<protocol>.<record>'.")
        if not isinstance(target, str) or not target.strip():
            raise ValueError(f"Route {key!r} needs a department.")
        t = target.strip()
        if t in (OWNER_ID, COORDINATOR_ID):
            clean_routes[key] = t
            continue
        did = keys.get(_norm(t))
        if not did:
            raise ValueError(f"Route {key!r} points at unknown department {target!r}.")
        clean_routes[key] = did
    out["routes"] = clean_routes
    return out


def hospital() -> dict:
    """The hospital settings (name, NCG level, type, PM-JAY empanelled, fetch window, the board lists), defaults filled."""
    return {**DEFAULT_HOSPITAL, **(load().get("hospital") or {})}


class SetupDone(Exception):
    """The first set-up was answered already; the setting is changed under Organisation."""


def first_setup(by: str, pmjay_empanelled, name=None, level=None) -> dict:
    """The root admin's first set-up (V2 item 7.1, plan section 11): the PM-JAY empanelled question (default yes), with the hospital name
    and NCG level, answered once; the stamp (who, when) is kept in hospital.first_setup and the answer audited (first_setup). Later
    changes go through the Organisation screen; a second answer is refused (SetupDone)."""
    o = load()
    h = o.get("hospital") if isinstance(o.get("hospital"), dict) else {}
    if isinstance(h.get("first_setup"), dict):
        raise SetupDone(f"The first set-up was recorded on {str(h['first_setup'].get('at') or '')[:10]} by {h['first_setup'].get('by') or 'an admin'}. "
                        "Change the settings under Organisation.")
    if not isinstance(pmjay_empanelled, bool):
        raise ValueError("Answer whether the hospital is PM-JAY empanelled (true or false).")
    h = {**DEFAULT_HOSPITAL, **h, "pmjay_empanelled": pmjay_empanelled}
    if name is not None:
        h["name"] = str(name).strip()
    if level:
        if level not in LEVELS:
            raise ValueError(f"Hospital level must be one of: {', '.join(LEVELS)}.")
        h["level"] = level
    h["first_setup"] = {"at": now_iso(), "by": str(by or "")}
    o["hospital"] = h
    saved = save(o, by)
    audit("first_setup", by, pmjay_empanelled=pmjay_empanelled, name=h["name"], level=h["level"])
    return saved["hospital"]


def departments(group: str | None = None) -> list[dict]:
    ds = [d for d in load()["departments"] if isinstance(d, dict)]
    return [d for d in ds if d.get("group") == group] if group else ds


def department(dept_id) -> dict | None:
    """The department with this id, or the one a V1 id / name / alias resolves to (stored data keeps resolving after a rename)."""
    ds = departments()
    d = next((d for d in ds if d.get("id") == dept_id), None)
    if d is None and dept_id:
        did = department_id(dept_id)
        d = next((d for d in ds if d.get("id") == did), None) if did else None
    return d


def department_group(dept_id) -> str:
    """"treating" or "supporting"; a department without a group (hand-edited file) counts as supporting (the safer group)."""
    d = department(dept_id)
    return d.get("group") if d and d.get("group") in GROUPS else "supporting"


_PREFIX = re.compile(r"^(?:the\s+)?(?:department|dept\.?)\s+of\s+", re.I)
_SUFFIX = re.compile(r"\s+(?:department|dept\.?)$", re.I)


def department_id(name_or_alias: str) -> str | None:
    """The department id for an id, name or alias (protocol "Responsible Department" names, V1 ids), case-insensitive.

    "Department of Radio-diagnosis", "Dept. of Pathology" and "Pathology Department" resolve like the bare name.
    None when nothing matches (the MDT Coordinator's names included): the caller routes it to the coordinator rather than
    guessing."""
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
    if is_coordinator_name(dept_id):
        return COORDINATOR_NAME
    if dept_id == OWNER_ID:
        return OWNER_NAME
    d = department(dept_id)
    return d["name"] if d else str(dept_id or "")


def department_email(dept_id) -> str:
    d = department(dept_id)
    return str(d.get("email") or "") if d else ""


def roles(username: str, vaidyx_admin: bool = False) -> dict:
    """The Tumour Board roles of a Vaidyx login.

    admin: a Vaidyx admin (everything). root_admin: listed in org.json admins (organisation and accounts, no clinical action: plan
    section 4). An empty username means authentication is off (single-user
    mode): there is no login to tie a role to, so that user is treated as admin. This only happens when the main app
    runs with AUTH_ENABLED=false or through its localhost bypass; ~/vaidyx/start_vaidyx_app.sh sets neither, so a
    normal deployment always has a username. Only existing departments and the roles member / head are honoured, even if
    org.json was edited by hand. treating / supporting: the user's departments of that group. admin_of: the departments the
    user administers. known: admin, coordinator or a doctor of at least one department. disabled: the Tumour Board flag; a
    disabled user is known to nobody and can() refuses everything."""
    username = str(username or "").strip()
    org = load()
    ds = departments()
    ids = {d.get("id") for d in ds}
    groups = {d.get("id"): d.get("group") for d in ds}
    u = (org.get("users") or {}).get(username) if username else None
    u = u if isinstance(u, dict) else {}
    dmap = u.get("departments") if isinstance(u.get("departments"), dict) else {}
    depts = {k: ROLE_SYNONYMS.get(v, v) for k, v in dmap.items() if k in ids and ROLE_SYNONYMS.get(v, v) in DEPT_ROLES}
    admin_of = [a for a in (u.get("admin_of") if isinstance(u.get("admin_of"), list) else []) if a in ids]
    root_admin = bool(username) and username in (org.get("admins") or [])
    admin = (not username) or bool(vaidyx_admin)  # everything: the Vaidyx admin (or no login at all); a root admin manages, never treats
    coordinator = u.get("coordinator") is True
    disabled = u.get("disabled") is True and not admin  # the Tumour Board flag never locks out the Vaidyx admin (review M3)
    r = {"user": username, "admin": admin, "vaidyx_admin": bool(vaidyx_admin), "root_admin": root_admin, "coordinator": coordinator,
         "departments": depts, "admin_of": admin_of,
         "treating": {k: v for k, v in depts.items() if groups.get(k) == "treating"},
         "supporting": {k: v for k, v in depts.items() if groups.get(k) == "supporting"},
         "disabled": disabled, "known": (admin or coordinator or bool(depts)) and not disabled}
    return r


def _allowed(r: dict, who, department) -> bool:
    if "any" in who:
        return True
    if "known" in who and r.get("known"):
        return True
    if "coordinator" in who and r.get("coordinator"):
        return True
    if "root_admin" in who and r.get("root_admin"):
        return True
    if "treating" in who and r.get("treating"):
        return True
    if "supporting" in who and r.get("supporting"):
        return True
    if department is None:  # no department named: no department role counts (can() passes None only for that case)
        return False
    if "dept_admin" in who and department in (r.get("admin_of") or []):
        return True
    want = {x for x in who if x in DEPT_ROLES}  # a head is also a member: rules open to members list both
    return (r.get("departments") or {}).get(department) in want


def can(r: dict, action: str, department: str | None = None) -> bool:
    """True if the user with roles `r` may do `action` (for `department`: an id, name or alias, passed raw; it is
    resolved here, so "Radiology" and "radio_diagnosis" are the same). See ACTIONS.

    A disabled user may do nothing. Vaidyx admins may do every listed action; a root admin only what lists "root_admin" (and
    "any"); an unknown action is refused for everyone. A
    department-scoped action with no (or an empty) department follows its "no_dept" rule (admin only if none is declared): a
    member / head of some department never qualifies through it. A department that does not resolve matches no membership
    (coordinators and admins keep their hospital-wide rights where "who" lists them)."""
    rule = ACTIONS.get(action)
    if rule is None or not isinstance(r, dict) or r.get("disabled"):
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


def can_as_member(r: dict, action: str, department) -> bool:
    """True if the user qualifies for a department-scoped action through a membership (member / head) of the department named, not
    through a hospital-wide role: the uploading department confirms its own upload, its head deletes it (V2 item 5.1 owner rule)."""
    rule = ACTIONS.get(action)
    if rule is None or not rule.get("dept") or not isinstance(r, dict) or r.get("disabled") or not department:
        return False
    dept = department_id(department)
    if not dept:
        return False
    return _allowed(r, tuple(x for x in rule["who"] if x in DEPT_ROLES), dept)


def require(r: dict, action: str, department: str | None = None) -> None:
    """PermissionError (the route answers 403) unless can(r, action, department)."""
    if can(r, action, department):
        return
    if isinstance(r, dict) and r.get("disabled"):
        raise PermissionError("Your Tumour Board access is disabled. Ask your department admin or the root admin.")
    where = f" for {department_name(department_id(department) or department)}" if department else ""
    raise PermissionError(f"You do not have permission for '{action}'{where}. Ask a Tumour Board admin if you need it.")


def my_departments(r: dict) -> list[dict]:
    """The departments the user belongs to as a doctor (every department for an admin), each with the user's "role" added."""
    mine = (r or {}).get("departments") or {}
    return [{**d, "role": mine.get(d.get("id"))} for d in departments() if (r or {}).get("admin") or d.get("id") in mine]


def admin_departments(r: dict) -> list[dict]:
    """The departments the user administers (every department for a Vaidyx admin or a root admin)."""
    adm = set((r or {}).get("admin_of") or [])
    return [dict(d) for d in departments() if (r or {}).get("admin") or (r or {}).get("root_admin") or d.get("id") in adm]


def version() -> str:
    """A token for the current org.json (its mtime and size): PUT /org may send it back as expected_version for a 409 on a stale edit."""
    try:
        st = path().stat()
        return f"{st.st_mtime_ns}-{st.st_size}"
    except OSError:
        return ""


ROUTE_KINDS = ("department", OWNER_ID, COORDINATOR_ID)


def route_for(protocol_id: str, record_id: str) -> str | None:
    """The root admin's routing override for a protocol record (V2 item 2.4): a department id, "owner" (the Case File's owning
    treating department) or "coordinator" (the MDT Coordinator); None when the protocol's own department applies."""
    return (load().get("routes") or {}).get(f"{protocol_id}.{record_id}")


def resolve_route(target: str | None, fallback_name: str, owner_dept: str | None = None) -> tuple[str, str | None, str]:
    """(display name, department id or None, kind) for a routing target: a department (id, name or alias), "owner" (owner_dept when the
    Case File has one, else the protocol's fallback department) or "coordinator". An unresolvable target falls back to the
    protocol's department name; a name that resolves nowhere is returned with id None (the coordinator handles it, as in V1)."""
    t = str(target or "").strip()
    if t == COORDINATOR_ID or (t and is_coordinator_name(t)) or (not t and is_coordinator_name(fallback_name)):
        return COORDINATOR_NAME, None, COORDINATOR_ID
    if t == OWNER_ID:
        did = department_id(owner_dept) if owner_dept else None
        if did:
            return department_name(did), did, OWNER_ID
        did = department_id(fallback_name)
        return (department_name(did) if did else str(fallback_name or "")), did, OWNER_ID
    did = department_id(t) if t else None
    if did:
        return department_name(did), did, "department"
    did = department_id(fallback_name)
    return (department_name(did) if did else str(fallback_name or "")), did, "department"


def visible_departments_for_inbox(r: dict) -> list[str]:
    """Department ids whose inbox the user may see: members and heads their own, admins all, coordinators none (unless
    they are also a member somewhere; the coordinator's own inbox row is added by notify.inbox)."""
    return [d["id"] for d in departments() if can(r, "inbox", d["id"])]
