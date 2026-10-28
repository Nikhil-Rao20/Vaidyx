"""Who may open a Case File and who may act on it (V2 item 5.1; residents, break-glass and archives from 18 Oct 2026).

A Case File is one cancer episode of one patient (a UHID) owned by one treating department (`case["department"]`); other departments
may take part (`case["participants"]`: read and comment) and a second cancer of the same patient is a linked Case File (5.3). Reading:
the MDT Coordinator reads every Case File; the doctors of the owning department (its consultants and its residents), the residents added
to the Case File team (team.py), the doctors of a participating department, of a department with an open referral to it (5.2) and of the
owner of a linked Case File read the whole Case File (scope FULL); the doctors of a department that received a request (a sent
Pre-Authorization request, a Tumour Board action) see only the items they were asked about (scope REQUESTS: their requests and the
records their department produced or the request names); everyone else is refused. A Case File without an owning department (created by
hand before 5.1, the demo Case Files) is open to the MDT Coordinator and its creator only (owner decision 16 Oct: Case Files without an
owner should not exist). A protected Case File (config.PROTECTED_CASES, real patient data) is open to its creator and to a Vaidyx admin
inside a break-glass window on it, nobody else, and no listing names it to anyone else (security review finding 0).

The Vaidyx admin (the server administrator) has no clinical scope: it reads a Case File only inside an open break-glass window
(break_glass.json: one window per admin, with the Case File, a reason and an end time; the owner is told, everything is audited; the
route is in api/team.py). A resident past its end date, an auditor and an outside expert get no scope here (the meeting screens have
their own rule for outside experts).

A doctor without access (a consultant or a resident placed in a department) may open one Case File read-only with a reason (owner
decision D8, night-v3 item 1.9): a window of 24 hours in break_glass_doctors.json (several per doctor, one per Case File, renewed on a
new opening), scope READ: the read actions only (BREAK_GLASS_ACTIONS), never the board, the meetings, the deck or the chats (those check
FULL), never listed among the doctor's Case Files (visible), never on a protected Case File. The owner's consultants are told and it is
audited (team.break_glass_doctor, route POST /break-glass).

Acting: the clinical actions of a treating doctor (confirm, waive, dismiss, upload an outside report, re-fetch, link, send and close
requests, refer, manage the participants and the team, set the urgency, approve a resident's proposal, change the listing) belong to
the owning department's consultants; a resident of the team may upload and propose, never sign; a department still confirms or deletes
its own upload through its membership (the V1 rule), the coordinator keeps the board and session actions. An archived Case File keeps
its readers but refuses every change except taking it out of the archive ("This Case File is archived"). Every change here is audited in
the Case File. No model calls."""
import json, os, re, threading
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, org, store

FULL = "full"          # the whole Case File
REQUESTS = "requests"  # only the items the department was asked about (a supporting department)
READ = "read"          # the whole Case File, read only: a doctor's window opened with a reason (night-v3 item 1.9, owner decision D8)
SCOPES = (FULL, REQUESTS, READ)
# The clinical actions a treating doctor does on the Case Files its department owns (plan section 4). The other actions keep their
# org.ACTIONS rule (board and session actions for the coordinator, a department's own upload for its doctors, reading for everyone in scope).
OWNER_ACTIONS = frozenset({"waive", "confirm", "dismiss_failed", "upload_to_case", "send_request", "create_request", "close_request",
                           "delete_document", "refer", "manage_participants", "mark_ready",
                           "approve_proposal", "set_urgency", "manage_team", "set_consent"})  # 18 Oct: the owner's consultants only
RESIDENT_ACTIONS = frozenset({"upload_to_case", "propose", "upload", "ask", "view", "read_case"})  # what a resident may do on its own Case Files
ARCHIVE_ALLOWED = frozenset({"unarchive", "view", "read_case", "ask", "read_audit"})  # the only actions an archived Case File accepts
BREAK_GLASS_ACTIONS = frozenset({"view", "read_case", "read_audit", "ask"})  # what a Vaidyx admin may do inside its window: read (review #6)
ARCHIVED_MESSAGE = "This Case File is archived"
RECENT_DAYS = 7  # a department that received a request keeps its limited view this long after the request closed (as its inbox lists it)
REFERRAL_OPEN = "requested"
BREAK_GLASS_HOURS = 4  # a break-glass window's default length
BREAK_GLASS_MAX_HOURS = 24
DOCTOR_WINDOW_HOURS = 24  # a doctor's window opened with a reason lasts this long (owner decision D8)
REASON_MIN, REASON_MAX, VIA_MAX = 3, 500, 80
READ_ONLY_MESSAGE = "This Case File is open read-only (opened with a reason): the owning department acts on it."
_bg_lock = threading.Lock()


class AccessError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers."""

    def __init__(self, message, status=400, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


# ---- what the Case File records -------------------------------------------------------------------------------------------

def owner(case) -> str | None:
    """The owning treating department's id, or None for a Case File without one."""
    d = (case or {}).get("department") if isinstance(case, dict) else None
    return org.department_id(d) if d else None


def participants(case) -> list[str]:
    """The participating departments' ids (read and comment), in the order they joined."""
    out = []
    for p in (case or {}).get("participants") or []:
        did = org.department_id(p.get("department")) if isinstance(p, dict) else org.department_id(p)
        if did and did not in out:
            out.append(did)
    return out


def open_referral(case) -> dict | None:
    """The referral waiting for the receiving department's answer (5.2), or None."""
    for r in reversed((case or {}).get("referrals") or []):
        if isinstance(r, dict) and r.get("status") == REFERRAL_OPEN:
            return r
    return None


def linked_owners(case) -> list[str]:
    """The owning departments of the Case Files linked to this one (the same patient's other cancer, 5.3): the linked Case File's
    current owner (it may have been referred since the link was made), else the department recorded with the link."""
    out = []
    for l in (case or {}).get("linked_cases") or []:
        if not isinstance(l, dict):
            continue
        live = store.get_case(l.get("case_id")) if l.get("case_id") else None
        if not live:  # a link to a Case File that no longer exists gives nobody access (review Phase 5 minor 2)
            continue
        did = owner(live)
        if did and did not in out:
            out.append(did)
    return out


def is_protected(case) -> bool:
    """A Case File holding real patient data (config.PROTECTED_CASES): never listed or opened for anyone but the login that created it
    and a Vaidyx admin inside a break-glass window on it (security review finding 0)."""
    cid = case.get("case_id") if isinstance(case, dict) else case
    return bool(cid) and str(cid) in config.PROTECTED_CASES


def is_creator(r: dict, case: dict) -> bool:
    """The login that created this Case File (case.json created_by)."""
    u = str((r or {}).get("user") or "") if isinstance(r, dict) else ""
    return bool(u) and isinstance(case, dict) and u == str(case.get("created_by") or "")


def hidden(r: dict, case) -> bool:
    """True for a protected Case File this user may not open: listings (notifications, inboxes, waiting items) leave it out."""
    if not is_protected(case):
        return False
    c = case if isinstance(case, dict) and "created_by" in case else None
    if c is None:
        try:
            c = store.get_case(case.get("case_id") if isinstance(case, dict) else case)
        except (ValueError, OSError):
            c = None
    return not isinstance(c, dict) or scope(r, c) is None


def is_archived(case) -> bool:
    """Archived instead of deleted (18 Oct): case.json "archived" {by, at, reason}."""
    return isinstance(case, dict) and isinstance(case.get("archived"), dict) and bool(case["archived"].get("at"))


def team_residents(case) -> list[dict]:
    """The residents on the Case File team (team.py): the entries not removed and not past their end date."""
    out = []
    today = date.today().isoformat()
    for x in ((case or {}).get("team") or {}).get("residents") or []:
        if not isinstance(x, dict) or not x.get("user") or x.get("removed"):
            continue
        if str(x.get("end_date") or "")[:10] and str(x["end_date"])[:10] < today:
            continue
        out.append(x)
    return out


def removed_from_team(case, user: str) -> bool:
    """True when the person was taken off this Case File's team and not added back (team.py keeps one entry per person)."""
    entries = [x for x in ((case or {}).get("team") or {}).get("residents") or [] if isinstance(x, dict) and x.get("user") == user]
    return bool(entries) and bool(entries[-1].get("removed"))


def is_team_resident(r: dict, case: dict) -> bool:
    """A resident of the owning department, or a resident added to this Case File's team; never one past its end date, nor one the team
    took off this Case File (a removed resident loses access, SPEC section 4)."""
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired") or not r.get("resident"):
        return False
    if removed_from_team(case, r.get("user") or ""):
        return False
    own = owner(case)
    if own and own in (r.get("resident") or {}):
        return True
    return any(x.get("user") == r.get("user") for x in team_residents(case))


def team_members(case) -> list[dict]:
    """The consultants of other departments the owner let into this Case File's team (an approved "Ask to join", night-v3 item 1.1):
    the entries not removed. They read the whole Case File; the owner's rights stay with the owning department's consultants."""
    return [x for x in ((case or {}).get("team") or {}).get("members") or [] if isinstance(x, dict) and x.get("user") and not x.get("removed")]


def is_team_member(r: dict, case: dict) -> bool:
    """A consultant (member or head of a department, not only a resident) on this Case File's team (team_members)."""
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired") or not r.get("known"):
        return False
    if not (set(r.get("departments") or {}) - set(r.get("resident") or {})):
        return False
    return any(x.get("user") == r.get("user") for x in team_members(case))


def _action_department(a: dict) -> str | None:
    if a.get("role") == "coordinator":
        return org.COORDINATOR_ID
    for k in ("department_id", "department"):
        did = org.department_id(a.get(k) or "")
        if did:
            return did
    return None


def _received(a: dict, today=None) -> bool:
    """True when the department holds (or recently held) this action: a sent Pre-Authorization request (or a V1 one opened before
    4.2), a Tumour Board action; never a suggestion nobody sent, nor a request closed longer ago than its inbox shows it."""
    status = str(a.get("status") or "")
    if status == "suggested" or (status == "completed" and a.get("never_sent")):
        return False
    if status == "completed":
        done = str(a.get("completed") or "")[:10]
        return bool(done) and done >= ((today or date.today()) - timedelta(days=RECENT_DAYS)).isoformat()
    return True


def asked(case_id: str, state=None, today=None) -> dict:
    """{department id: [actions it received]} for the Case File's actions (Pre-Authorization requests and Tumour Board actions)."""
    st = store.get_state(case_id) if state is None else state
    out: dict[str, list] = {}
    for a in (st or {}).get("actions") or []:
        if not isinstance(a, dict) or a.get("source") not in ("pre_authorization", "board"):
            continue
        did = _action_department(a)
        if did and _received(a, today):
            out.setdefault(did, []).append(a)
    return out


# ---- break-glass (the Vaidyx admin) ------------------------------------------------------------------------------------------

def break_glass_path() -> Path:
    return Path(config.DATA_ROOT) / "break_glass.json"


def _read_windows() -> dict:
    try:
        d = json.loads(break_glass_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _write_windows(d: dict, path: Path | None = None) -> None:
    p = path or break_glass_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


def _active(w: dict, now: datetime | None = None) -> bool:
    try:
        return isinstance(w, dict) and bool(w.get("case_id")) and datetime.fromisoformat(str(w.get("until"))) > (now or datetime.now())
    except (TypeError, ValueError):
        return False


def break_glass_window(user: str, case_id: str | None = None) -> dict | None:
    """The open break-glass window of `user` (for `case_id` when given), or None."""
    w = _read_windows().get(str(user or ""))
    if not _active(w) or (case_id is not None and w.get("case_id") != case_id):
        return None
    return dict(w)


def break_glass_windows() -> dict:
    """Every open window, by user."""
    return {u: dict(w) for u, w in _read_windows().items() if _active(w)}


def open_break_glass(user: str, case_id: str, reason: str, hours: float | None = None) -> dict:
    """A Vaidyx admin opens a window on one Case File with a reason (the route checks the role; the owner is told there). One window
    per admin: a new one replaces the old. Audited in the Case File (break_glass) and in the organisation log."""
    reason = " ".join(str(reason or "").split())[:500]
    if not reason:
        raise AccessError("Give the reason for opening this Case File (it is recorded and the owner is told).")
    c = store.get_case(case_id)
    if not c:
        raise AccessError("Case not found", 404)
    try:
        h = float(hours) if hours is not None else float(BREAK_GLASS_HOURS)
    except (TypeError, ValueError):
        raise AccessError("Hours must be a number.")
    if not 0 < h <= BREAK_GLASS_MAX_HOURS:
        raise AccessError(f"A break-glass window lasts up to {BREAK_GLASS_MAX_HOURS} hours.")
    now = datetime.now()
    w = {"case_id": case_id, "until": (now + timedelta(hours=h)).isoformat(timespec="seconds"), "reason": reason, "opened": now.isoformat(timespec="seconds")}
    with _bg_lock:
        d = _read_windows()
        d[str(user)] = w
        _write_windows(d)
    store.audit(case_id, {"kind": "break_glass", "by": user, "reason": reason, "until": w["until"], "hours": h})
    org.audit("break_glass", user, case_id=case_id, reason=reason, until=w["until"])
    return dict(w)


def close_break_glass(user: str, by: str = "") -> dict | None:
    """Close the admin's window early (audited); None when there was none."""
    with _bg_lock:
        d = _read_windows()
        w = d.pop(str(user), None)
        if w is not None:
            _write_windows(d)
    if w and w.get("case_id"):
        store.audit(w["case_id"], {"kind": "break_glass_closed", "by": by or user, "user": user})
    return w


def expire_break_glass() -> int:
    """Drop windows past their end, the Vaidyx admin's and the doctors' (the scheduler's housekeeping); returns how many went."""
    with _bg_lock:
        d = _read_windows()
        keep = {u: w for u, w in d.items() if _active(w)}
        if len(keep) != len(d):
            _write_windows(keep)
        dd = _read_doctor_windows()
        gone = sum(len(ws) for ws in dd.values())
        kept = {u: [w for w in ws if _active(w)] for u, ws in dd.items()}
        kept = {u: ws for u, ws in kept.items() if ws}
        gone -= sum(len(ws) for ws in kept.values())
        if gone:
            _write_windows(kept, doctor_windows_path())
    return len(d) - len(keep) + gone


# ---- a doctor opens a Case File with a reason (night-v3 item 1.9, owner decision D8) ------------------------------------------

def doctor_windows_path() -> Path:
    return Path(config.DATA_ROOT) / "break_glass_doctors.json"


def _read_doctor_windows() -> dict:
    """{user: [{"id", "case_id", "reason", "via", "opened", "until"}]}; anything malformed is left out."""
    try:
        d = json.loads(doctor_windows_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {str(u): [w for w in ws if isinstance(w, dict)] for u, ws in d.items() if isinstance(ws, list)}


def doctor_window(user: str, case_id: str) -> dict | None:
    """The doctor's open window on this Case File, or None."""
    for w in _read_doctor_windows().get(str(user or ""), []):
        if w.get("case_id") == case_id and _active(w):
            return dict(w)
    return None


def doctor_windows(user: str) -> list[dict]:
    """The doctor's open windows, the newest first."""
    ws = [dict(w) for w in _read_doctor_windows().get(str(user or ""), []) if _active(w)]
    return sorted(ws, key=lambda w: str(w.get("opened") or ""), reverse=True)


def clean_reason(reason) -> str:
    """The reason as recorded (whitespace collapsed), or AccessError 400 `bad_reason`."""
    text = " ".join(str(reason or "").split())
    if len(text) < REASON_MIN:
        raise AccessError("Give the reason for opening this Case File (it is recorded and the owner's consultants are told).", 400, "bad_reason")
    if len(text) > REASON_MAX:
        raise AccessError(f"Keep the reason to {REASON_MAX} characters.", 400, "bad_reason")
    return text


_VIA = re.compile(r"similar:[A-Za-z0-9_.-]{1,64}")


def clean_via(via) -> str:
    """Where a doctor came from when opening with a reason: "" or "similar:<Case File id>" (Phase 7, D10), so every opening is
    attributable; anything else is AccessError 400 `bad_via` (whole-run review 9, M1)."""
    v = str(via or "").strip()
    if v and not _VIA.fullmatch(v):
        raise AccessError("Vaidyx cannot record where this opening came from. Open the Case File again from its page or from the similar list.", 400, "bad_via")
    return v


def doctor_windows_all() -> list[dict]:
    """Every open doctor window, for the root admin and the auditor (GET /break-glass, whole-run review 9 M2): case_id, user, until,
    reason, via, the newest first."""
    out = [{"case_id": w.get("case_id"), "user": u, "until": w.get("until"), "reason": w.get("reason") or "", "via": w.get("via") or "",
            "opened": w.get("opened") or ""} for u, ws in _read_doctor_windows().items() for w in ws if _active(w)]
    return sorted(out, key=lambda w: str(w.get("opened") or ""), reverse=True)


def open_doctor_window(user: str, case_id: str, reason: str, via: str = "") -> dict:
    """Write the doctor's read-only window on one Case File for DOCTOR_WINDOW_HOURS (a new opening of the same Case File renews the one
    window). Only the store: team.break_glass_doctor checks who may, audits and tells the owner's consultants. Returns the window and
    "renewed"."""
    reason = clean_reason(reason)
    via = clean_via(via)[:VIA_MAX]
    c = store.get_case(case_id)
    if not c or is_protected(c):  # a protected Case File never opens through a doctor's window, and is never named
        raise AccessError("Case not found", 404, "not_found")
    now = datetime.now()
    until = (now + timedelta(hours=DOCTOR_WINDOW_HOURS)).isoformat(timespec="seconds")
    with _bg_lock:
        d = _read_doctor_windows()
        ws = [w for w in d.get(str(user), []) if _active(w, now)]
        old = next((w for w in ws if w.get("case_id") == case_id), None)
        w = {"id": (old or {}).get("id") or "BG-" + now.strftime("%Y%m%d%H%M%S") + "-" + os.urandom(3).hex(), "case_id": case_id,
             "reason": reason, "via": via, "opened": now.isoformat(timespec="seconds"), "until": until}
        d[str(user)] = [x for x in ws if x.get("case_id") != case_id] + [w]
        _write_windows(d, doctor_windows_path())
    return {**w, "renewed": old is not None}


def close_doctor_window(user: str, case_id: str, by: str = "") -> dict | None:
    """Close the doctor's window on this Case File early (audited in the Case File and the organisation log); None when there was none."""
    with _bg_lock:
        d = _read_doctor_windows()
        ws = d.get(str(user), [])
        w = next((x for x in ws if x.get("case_id") == case_id and _active(x)), None)
        if w is not None:
            rest = [x for x in ws if x.get("case_id") != case_id and _active(x)]
            if rest:
                d[str(user)] = rest
            else:
                d.pop(str(user), None)
            _write_windows(d, doctor_windows_path())
    if w:
        store.audit(case_id, {"kind": "break_glass_doctor_closed", "by": by or user, "user": user, "window": w.get("id")})
        org.audit("break_glass_doctor_closed", by or user, case_id=case_id, user=user)
    return w


def placed_doctor(r: dict) -> bool:
    """A known, placed login with a consultant or resident placement, not disabled or past its end date; never the Vaidyx admin, the
    login of single-user mode or the MDT Coordinator (who opens every Case File anyway), never an outside expert without a placement."""
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired") or not r.get("known"):
        return False
    if r.get("admin") or r.get("vaidyx_admin") or r.get("coordinator"):
        return False
    return bool(r.get("departments"))


def _doctor_open(r: dict, case: dict) -> bool:
    return placed_doctor(r) and doctor_window(r.get("user") or "", (case or {}).get("case_id")) is not None


def may_open_with_reason(r: dict, case: dict) -> bool:
    """Decision 3 of item 1.9: a placed doctor (consultant or resident) with no other access to this Case File (or only its own window,
    which a new opening renews); never on a protected Case File."""
    if not isinstance(case, dict) or is_protected(case) or not placed_doctor(r):
        return False
    return scope(r, case) in (None, READ)


def _admin_open(r: dict, case: dict) -> bool:
    """The Vaidyx admin's clinical scope: only inside an open break-glass window on this Case File. No login at all (single-user mode,
    org.roles) keeps the old behaviour."""
    if not r.get("admin"):
        return False
    if not r.get("vaidyx_admin"):
        return True  # authentication is off: there is no person to open a window for
    return break_glass_window(r.get("user") or "", (case or {}).get("case_id")) is not None


# ---- reading ---------------------------------------------------------------------------------------------------------------

def _mine(r: dict) -> set:
    return set((r or {}).get("departments") or {})


def scope(r: dict, case: dict, state=None) -> str | None:
    """FULL, REQUESTS or None (refused) for the user with roles `r` on this Case File."""
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired") or not isinstance(case, dict):
        return None
    if is_protected(case):  # real patient data: its creator, and a Vaidyx admin inside a break-glass window on it; nobody else (finding 0)
        if is_creator(r, case) or (r.get("vaidyx_admin") and break_glass_window(r.get("user") or "", case.get("case_id")) is not None):
            return FULL
        return None
    if r.get("admin"):
        return FULL if _admin_open(r, case) else None
    if not r.get("known") or (r.get("outside_expert") and not r.get("departments") and not r.get("coordinator")):
        return None
    if r.get("coordinator"):
        return FULL
    own = owner(case)
    if not own:  # no owning department recorded (before 5.1, a manual Case File): the coordinator (above) and its creator only (owner, 16 Oct)
        if is_creator(r, case):
            return FULL
        return READ if _doctor_open(r, case) else None  # or a doctor's window opened with a reason (D8)
    mine = _mine(r) - set(r.get("resident") or {})  # the consultant placements; a resident reads through is_team_resident only
    if own in mine or (mine & set(participants(case))) or (mine & set(linked_owners(case))):
        return FULL
    if is_team_resident(r, case):  # a resident of the owning department or of this Case File's team
        return FULL
    if is_team_member(r, case):  # a consultant of another department the owner let into the team: reads, never the owner's rights (may)
        return FULL
    ref = open_referral(case)
    if ref and org.department_id(ref.get("to")) in mine:
        return FULL
    if mine & set(asked(case["case_id"], state)):  # a resident never answers requests
        return REQUESTS
    if _doctor_open(r, case):  # a doctor's window opened with a reason (night-v3 item 1.9, D8): read only
        return READ
    return None


def can_see_chats(r: dict, case: dict) -> bool:
    """The shared team chat (18 Oct): whoever reads the whole Case File as the treating side (the owner's consultants and residents, a
    participating treating department, the coordinator, an admin in a window); never a supporting doctor, who sees requests only."""
    if scope(r, case) != FULL:
        return False
    if r.get("admin") or r.get("coordinator") or r.get("treating") or r.get("resident_treating"):
        return True
    return is_team_resident(r, case)


def refusal(r: dict, case: dict) -> str:
    if is_protected(case):  # never the patient's name
        return "This Case File is restricted to the person who created it."
    if (r or {}).get("vaidyx_admin"):
        return "A Vaidyx admin opens a Case File only through break-glass: give a reason, the owner is told and it is recorded."
    if (r or {}).get("expired"):
        return "Your placement ended on " + str(r.get("end_date") or "")[:10] + ". Ask your department admin to extend it."
    own = owner(case)
    if not own:
        return "This Case File has no owning department yet: only the MDT Coordinator and the person who created it can open it."
    name = org.department_name(own)
    return (f"This Case File belongs to {name}. Its doctors, the participating departments and the MDT Coordinator can open it; a department "
            "that received a request sees the items it was asked about.")


def visible(r: dict, cases, states=None) -> list:
    """The Case Files the user may open (any scope but a doctor's window: a Case File opened with a reason is reached by its address or
    the notification, never listed among the doctor's own), each as given."""
    return [c for c in cases or [] if isinstance(c, dict) and scope(r, c, (states or {}).get(c.get("case_id"))) not in (None, READ)]


def my_actions(r: dict, case_id: str, state=None) -> list:
    """The actions a department-scoped reader may see: those its departments received."""
    mine = _mine(r)
    return [a for did, acts in asked(case_id, state).items() if did in mine for a in acts]


def limited_docs(r: dict, case: dict, docs: list, state=None) -> list:
    """The records a department-scoped reader may open: those its departments produced (uploaded or, from the HIS, reported) and the
    records its requests name."""
    mine = _mine(r)
    named = {a.get("source_doc_id") for a in my_actions(r, case["case_id"], state) if a.get("source_doc_id")}
    out = []
    for d in docs or []:
        dep = org.department_id(d.get("department") or "") if d.get("department") else None
        if (dep and dep in mine) or d.get("doc_id") in named:
            out.append(d)
    return out


def limited_state(r: dict, case: dict, state: dict) -> dict:
    """A department-scoped reader's view of the state: its own actions, nothing of the gate, the board or the artefacts."""
    return {"actions": my_actions(r, case["case_id"], state), "board_records": [], "reviews": [], "artefacts": {}, "gate": None, "confirmations": [],
            "limited": True}


# ---- acting ----------------------------------------------------------------------------------------------------------------

def is_owner_consultant(r: dict, case: dict) -> bool:
    """A consultant (member or head, never a resident) of the owning treating department; for a Case File without an owner, any
    treating consultant. The Vaidyx admin never counts here."""
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired"):
        return False
    own = owner(case)
    treating = r.get("treating") or {}
    return (own in treating) if own else bool(treating)


def is_owner_doctor(r: dict, case: dict) -> bool:
    """A doctor of the owning treating department (a consultant); for a Case File without an owner, any treating doctor. The Vaidyx
    admin never counts (a break-glass window is read only, security review #6); the admin of single-user mode does."""
    if not isinstance(r, dict) or r.get("disabled"):
        return False
    if r.get("admin"):
        return not r.get("vaidyx_admin") and _admin_open(r, case)  # a break-glass window is read only (review #6)
    return is_owner_consultant(r, case)


def may(r: dict, action: str, case: dict, department: str | None = None) -> bool:
    """org.can() plus the owner rule: on a Case File with an owning department, an OWNER_ACTION is for the owner's consultants (and the
    Vaidyx admin inside a break-glass window); a department-scoped one stays open to a member or head of the department named (its own
    upload). A resident does only RESIDENT_ACTIONS, and only on the Case Files of its team. An archived Case File refuses every change.
    A Vaidyx admin inside its break-glass window only reads (BREAK_GLASS_ACTIONS, security review #6)."""
    if isinstance(r, dict) and r.get("vaidyx_admin") and not r.get("disabled"):
        return action in BREAK_GLASS_ACTIONS and _admin_open(r, case)
    if isinstance(case, dict) and _doctor_open(r, case) and scope(r, case) == READ:  # a doctor's window opened with a reason: read only (D8)
        return action in BREAK_GLASS_ACTIONS
    if not org.can(r, action, department):
        return False
    if is_archived(case) and action not in ARCHIVE_ALLOWED:
        return False
    if r.get("admin"):
        return _admin_open(r, case)
    if r.get("expired"):
        return False
    resident_only = bool(r.get("resident")) and not (r.get("treating") or r.get("supporting") or r.get("coordinator"))
    if action == "propose":
        return is_team_resident(r, case)
    if resident_only:
        return action in RESIDENT_ACTIONS and (action not in OWNER_ACTIONS or is_team_resident(r, case))
    if action not in OWNER_ACTIONS:
        return True
    own = owner(case)
    if not own:
        return True
    rule = org.ACTIONS.get(action) or {}
    if rule.get("dept") and department and org.can_as_member(r, action, department):
        return True
    if own in (r.get("treating") or {}):
        return True
    return action == "upload_to_case" and is_team_resident(r, case)  # a consultant elsewhere who is a resident on this team


def require(r: dict, action: str, case: dict, department: str | None = None) -> None:
    """PermissionError (the route answers 403) unless may()."""
    if may(r, action, case, department):
        return
    if is_archived(case) and action not in ARCHIVE_ALLOWED and org.can(r, action, department):
        raise PermissionError(ARCHIVED_MESSAGE + ". Take it out of the archive first.")
    if isinstance(r, dict) and r.get("expired"):
        raise PermissionError("Your placement ended on " + str(r.get("end_date") or "")[:10] + ". Ask your department admin to extend it.")
    if isinstance(case, dict) and _doctor_open(r, case) and scope(r, case) == READ:
        raise PermissionError(READ_ONLY_MESSAGE)
    if isinstance(r, dict) and r.get("vaidyx_admin"):
        if _admin_open(r, case):
            raise PermissionError("A break-glass window is read only: a Vaidyx admin reads the Case File, the owning department acts on it.")
        raise PermissionError("A Vaidyx admin acts on a Case File only inside an open break-glass window.")
    if isinstance(r, dict) and r.get("resident") and not (r.get("treating") or r.get("supporting") or r.get("coordinator")):
        if action in RESIDENT_ACTIONS and org.can(r, action, department):
            raise PermissionError("You are not on this Case File's team. Join it with the code from the treating doctor.")
        if action not in RESIDENT_ACTIONS:
            raise PermissionError(f"A resident cannot do '{action}': ask the treating consultant to sign off (propose it from the Case File).")
    if org.can(r, action, department):  # refused by the owner rule alone
        own = owner(case)
        raise PermissionError(f"Only the doctors of {org.department_name(own)}, which owns this Case File, can do '{action}' on it"
                              + (" (your department takes part: read and comment)." if set(participants(case)) & _mine(r) else "."))
    org.require(r, action, department)


def may_remind(r: dict, case: dict) -> bool:
    """Send a reminder about a Case File's requests (V2 item 6.1): the MDT Coordinator on the owner's behalf and the owning department's
    consultants (any treating doctor on a Case File without an owner); never the Vaidyx admin (a break-glass window is read only)."""
    if not org.can(r, "remind") or is_archived(case):
        return False
    return bool(r.get("coordinator")) or is_owner_doctor(r, case)


def may_list(r: dict, case: dict) -> bool:
    """Change the listing (protocol, NCG setting, board date, hospital level): the MDT Coordinator and the owning department's
    consultants (the new owner picks the protocol after a referral, 5.2); never the Vaidyx admin (a break-glass window is read only)."""
    if is_archived(case):
        return False
    if (r or {}).get("admin"):
        return not r.get("vaidyx_admin") and _admin_open(r, case)  # a break-glass window is read only (review #6)
    return org.can(r, "list_case") or (bool(owner(case)) and is_owner_doctor(r, case))


def check_not_archived(case: dict) -> None:
    """AccessError 409 for a change on an archived Case File (the new routes call it before changing anything)."""
    if is_archived(case):
        raise AccessError(ARCHIVED_MESSAGE + ". Take it out of the archive first.", 409)


# ---- the owner and the participants ----------------------------------------------------------------------------------------

def set_owner(case_id: str, department, user: str, reason: str = "", roles: dict | None = None) -> dict:
    """Record the owning treating department of a Case File that has none yet (a manual creation by a treating doctor). Audited."""
    if case_id in config.PROTECTED_CASES:
        raise AccessError("That Case File is protected; its owner is not set here", 409)
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    check_not_archived(case)
    did = org.department_id(department) if department else None
    if not did:
        raise AccessError(f"Unknown department: {department}")
    if org.department_group(did) != "treating":
        raise AccessError(f"{org.department_name(did)} is a supporting department; a Case File is owned by a treating department")
    if roles is not None and not (roles.get("admin") or roles.get("coordinator") or did in (roles.get("treating") or {})):
        raise AccessError(f"You are not placed in {org.department_name(did)}", 403)
    before = case.get("department")
    case["department"] = did
    case["participants"] = [p for p in case.get("participants") or [] if org.department_id((p or {}).get("department")) != did]
    store.save_case(case)
    store.audit(case_id, {"kind": "owner_set", "by": user, "department": did, "before": before, "reason": reason})
    return case


def add_participant(case_id: str, department, user: str, reason: str = "") -> dict:
    """The owner invites a department to read and comment (treating or supporting). Audited; the department is told."""
    from . import notify
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    check_not_archived(case)
    did = org.department_id(department) if department else None
    if not did:
        raise AccessError(f"Unknown department: {department}")
    if did == owner(case):
        raise AccessError(f"{org.department_name(did)} owns this Case File", 409)
    if did in participants(case):
        raise AccessError(f"{org.department_name(did)} already takes part", 409)
    rec = {"department": did, "since": store.now_iso(), "by": user, "reason": str(reason or "")[:500]}
    case.setdefault("participants", []).append(rec)
    store.save_case(case)
    store.audit(case_id, {"kind": "participant_added", "by": user, "department": did, "reason": rec["reason"]})
    patient = (case.get("patient") or {}).get("name") or case_id
    try:
        notify.notify({"department": did}, "case_shared", case_id, f"{org.department_name(did)} takes part in the Case File of {patient} ({case_id})",
                      f"{org.department_name(owner(case))} invited your department to read and comment on this Tumour Board Case File."
                      + (f" Reason: {rec['reason']}" if rec["reason"] else ""), by=user)
    except Exception:  # the notice never fails the change
        pass
    return case


def remove_participant(case_id: str, department, user: str, reason: str = "") -> dict:
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    check_not_archived(case)
    did = org.department_id(department) if department else None
    if not did or did not in participants(case):
        raise AccessError(f"{department} does not take part in this Case File", 404)
    from . import notify
    case["participants"] = [p for p in case.get("participants") or [] if org.department_id((p or {}).get("department")) != did]
    store.save_case(case)
    store.audit(case_id, {"kind": "participant_removed", "by": user, "department": did, "reason": str(reason or "")[:500]})
    patient = (case.get("patient") or {}).get("name") or case_id
    try:  # the department hears that it no longer takes part (review Phase 5 minor 8); the notice never fails the change
        notify.notify({"department": did}, "case_unshared", case_id, f"{org.department_name(did)} no longer takes part in the Case File of {patient} ({case_id})",
                      f"{org.department_name(owner(case)) if owner(case) else 'The owning department'} ended your department's part in this Tumour Board Case File."
                      + (f" Reason: {str(reason or '')[:500]}" if reason else ""), by=user)
    except Exception:
        pass
    return case


def public(case: dict) -> dict:
    """The ownership block of a Case File for the UI."""
    own = owner(case)
    return {"owner": {"id": own, "name": org.department_name(own)} if own else None,
            "participants": [{"id": org.department_id(p.get("department")), "name": org.department_name(org.department_id(p.get("department"))),
                              "since": p.get("since"), "by": p.get("by"), "reason": p.get("reason")} for p in case.get("participants") or [] if isinstance(p, dict)],
            "owner_history": list(case.get("owner_history") or []),
            "linked_cases": [_linked_view(l) for l in case.get("linked_cases") or [] if isinstance(l, dict)],
            "archived": dict(case["archived"]) if is_archived(case) else None,
            "residents": [{"user": x.get("user"), "name": org.display_name(x.get("user")), "since": x.get("since"), "end_date": x.get("end_date") or ""}
                          for x in team_residents(case)]}


def _linked_view(l: dict) -> dict:
    """A linked Case File as the UI shows it: its current protocol and owner when it still exists (a referral may have moved it since
    the link was made), else what the link recorded."""
    live = store.get_case(l.get("case_id")) if l.get("case_id") else None
    if live:
        l = {**l, "protocol": live.get("protocol") or "", "department": owner(live) or l.get("department") or ""}
    return {**l, "exists": bool(live), "department_name": org.department_name(org.department_id(l.get("department"))) if l.get("department") else ""}
