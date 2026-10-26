"""Tumour Board sessions: the board meeting itself (V1 items 6.1 and 6.3).

V1 item 6.1: a board session is created for a date from the Case Files listed for that date (agenda order); each specialty is
marked present or absent and members present are recorded by name. The "Board room" screen works on one session: current
Case File, summary, active agents, decision entry.
V1 item 6.3: the session keeps every agent point (brief items, points for review, live answers). Once the board's decision is
recorded and linked, each point can be marked discussed / accepted / not relevant: "what the agent said vs what the board
decided". Reporting only; nothing here measures accuracy.
V2 item 6.1: the four board heads and the hospital's attendance list come from the hospital settings (org.json); the owners mark
their Case Files ready and the MDT Coordinator builds the agenda from them; the session exports the minutes and tracks the follow-up of
its decisions. V2 item 6.2: the agent of a head not recorded as present is active; the surgical seat is Surgical Oncology or a surgeon
of the Case File's own surgical department, else the Surgical Oncology agent stands in for that Case File; Radiation Oncology and
Nuclear Medicine agents stay on demand.

Storage: data/tumour_board/sessions/<sid>.json (atomic writes) and sessions/audit.jsonl (every change). Changes about one Case
File are also written to that Case File's audit.jsonl. A protected Case File (config.PROTECTED_CASES, real patient data) never
joins a session.

All functions are synchronous read-modify-write with no awaits: in the app's single event loop each call is atomic relative to
other coroutines. Never call them from threads.
"""
import html, json, re, uuid
from datetime import datetime
from pathlib import Path

from . import config, org, store

ROLE_DEPARTMENT = {"radiology": "radiology", "pathology": "pathology", "medical_oncology": "medical_oncology",
                   "surgical_oncology": "surgical_oncology", "radiation_oncology": "radiation_oncology", "nuclear_medicine": "nuclear_medicine"}
DEPARTMENT_ROLE = {d: r for r, d in ROLE_DEPARTMENT.items()}
ON_DEMAND = ("radiation_oncology", "nuclear_medicine")  # agents the board may call on; active by themselves only when marked absent (V2 item 6.2)
SURGICAL_ROLE = "surgical_oncology"
MARKS = {"discussed": "Discussed", "accepted": "Accepted", "not_relevant": "Not relevant"}
STATUSES = ("planned", "in_session", "closed")
ATTENDANCE = ("present", "absent", "not_marked")
AGENT_STATUSES = ("queued", "running", "ready", "no_documents", "error")
KIND_LABELS = {"brief_item": "Brief item", "point_for_review": "Point for review", "no_documents": "No documents", "not_documented": "Not documented",
               "answer": "Answer to the board's question"}
ANSWER_STATUS_LABELS = {"out_of_scope": "Outside the agent's scope (refused)", "not_documented": "Not documented in the Case File"}
NOT_PRINTED = "Approximate source match: not printed until an expert reviews the brief."
CLOSED_EARLY = "The session was closed before the brief was ready"
NOTE = "Reporting only: what the AI support agents said and what the board decided. It does not measure accuracy."
MAX_NAME, MAX_TITLE, MAX_NOTE = 120, 200, 2000
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# the five board heads of the new interface, used when the hospital settings carry no board_heads key (org.json written before 18 Oct)
DEFAULT_HEADS = ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"]
MEETING_LISTS = ("discussion", "noting", "not_ready")  # the meeting's agenda lists (18 Oct); the old agenda[] follows discussion + noting


def sessions_dir() -> Path:
    return Path(config.DATA_ROOT) / "sessions"


def _path(sid) -> Path:
    return sessions_dir() / f"{store.safe_id(sid)}.json"


def _ddmmyyyy(iso) -> str:
    """'2026-10-11' -> '11/10/2026'; '2026-10-11T09:30:00' -> '11/10/2026 09:30'; anything else as given."""
    s = str(iso or "")
    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
        return datetime.fromisoformat(s).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return s


def _check_date(date) -> str:
    d = str(date or "").strip()
    try:
        if not _DATE.match(d):
            raise ValueError
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Board date must be a date as YYYY-MM-DD, not {date!r}") from None
    return d


# ---- audit ------------------------------------------------------------------------------------------------------------

def audit_session(sid: str, event: dict) -> None:
    """Append {"ts", "session": sid, **event} to sessions/audit.jsonl (also used by the service, e.g. "agents_prepare" events)."""
    ev = {"ts": store.now_iso(), "session": sid, **{k: v for k, v in (event or {}).items() if k not in ("ts", "session")}}
    p = sessions_dir() / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")


def _audit(sid, kind, by, case_id=None, case_kind=None, **extra):
    """sessions/audit.jsonl always; the Case File's audit.jsonl too when the change is about one Case File (case_kind given)."""
    audit_session(sid, {"kind": kind, "by": by or "", **({"case_id": case_id} if case_id else {}), **extra})
    if case_id and case_kind and case_id not in config.PROTECTED_CASES:
        store.audit(case_id, {"kind": f"board_session_{case_kind}", "session": sid, "by": by or "", **extra})


def read_audit(limit=500) -> list[dict]:
    p = sessions_dir() / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()[-limit:] if l.strip()]


# ---- listing and validation -------------------------------------------------------------------------------------------

def specialties() -> list[dict]:
    """Every org department (the MDT Coordinator is a role, not a department), with the agent role that speaks for it: the member
    dropdown and the dashboard use this; the session's attendance sheet is attendance_list() (V2 item 6.1)."""
    return [{"id": d["id"], "name": d.get("name") or d["id"], "group": d.get("group"), "role": DEPARTMENT_ROLE.get(d["id"])}
            for d in org.departments() if d.get("id")]


def heads() -> list[dict]:
    """The board's heads (hospital setting board_heads; when the setting is missing the five of the new interface: Radiology, Medical
    Oncology, Surgical Oncology, Pathology, Radiation Oncology; V2 item 6.2), each with the agent role that stands in for it (None when
    no agent exists for that department)."""
    out = []
    for raw in org.hospital().get("board_heads") or getattr(org, "BOARD_HEADS", None) or DEFAULT_HEADS:
        did = org.department_id(raw)
        if did and did not in [h["id"] for h in out]:
            out.append({"id": did, "name": org.department_name(did), "role": DEPARTMENT_ROLE.get(did)})
    return out


def head_ids() -> list[str]:
    return [h["id"] for h in heads()]


def _case_departments(case) -> list[str]:
    """The owning department and the participating departments of a Case File (5.1), as ids."""
    from . import access
    own = access.owner(case)
    return ([own] if own else []) + [d for d in access.participants(case) if d != own]


def attendance_list(session) -> list[dict]:
    """The session's attendance sheet (V2 item 6.1), in order: the heads, the on-demand specialties (Radiation Oncology, Nuclear
    Medicine), the hospital's own list (board_attendance), the owners and participants of the Case Files on the agenda, then any
    department already marked or recorded with a member. Each row: id, name, group, role, head, on_demand, why."""
    rows, seen = [], set()

    def add(did, why, head=False, on_demand=False):
        did = org.department_id(did) if did else None
        if not did or did in seen:
            return
        seen.add(did)
        rows.append({"id": did, "name": org.department_name(did), "group": org.department_group(did), "role": DEPARTMENT_ROLE.get(did),
                     "head": head, "on_demand": on_demand, "why": why})
    for h in heads():
        add(h["id"], "board head", head=True)
    for role in ON_DEMAND:
        add(ROLE_DEPARTMENT[role], "AI support on demand", on_demand=True)
    for did in org.hospital().get("board_attendance") or []:
        add(did, "hospital attendance list")
    for a in (session or {}).get("agenda") or []:
        c = store.get_case(a["case_id"]) if a.get("case_id") not in config.PROTECTED_CASES else None
        for i, did in enumerate(_case_departments(c)):
            add(did, f"{'owner' if i == 0 else 'participant'}: {a['case_id']}")
    for did, v in attendance(session).items():
        if v in ("present", "absent"):
            add(did, "marked")
    for m in (session or {}).get("members") or []:
        if m.get("department") != org.COORDINATOR_ID:
            add(m.get("department"), "member recorded")
    return rows


def _listed(case) -> bool:
    """Listed for the board: a protocol and listing status 'listed' (older Case Files without a listing record count as listed)."""
    return bool(case and case.get("protocol")) and (case.get("listing") or {"status": "listed"}).get("status") == "listed"


def _summary_state(case_id, st) -> str:
    from . import rules
    summ = (st.get("artefacts") or {}).get("summary")
    if not summ:
        return "none"
    return "stale" if summ.get("signature") and rules.stale_reason(summ["signature"], rules.case_signature(case_id, st)) else "ready"


def listed_for_date(date: str) -> list[dict]:
    """The Case Files listed for a board date, in listing order, each with what the coordinator needs to build the agenda (V2 item 6.1):
    the owner, whether the owner marked it ready, the Pre-Authorization result and the summary state."""
    date = _check_date(date)
    rows = [c for c in store.list_cases() if c.get("case_id") not in config.PROTECTED_CASES and _listed(c) and c.get("board_date") == date
            and not (isinstance(c.get("archived"), dict) and c["archived"].get("at"))]  # an archived Case File is never a candidate (review #8)
    rows.sort(key=lambda c: ((c.get("listing") or {}).get("listed_at") or "", c["case_id"]))
    out = []
    for c in rows:
        st = store.get_state(c["case_id"]); g = st.get("gate") or {}
        own = org.department_id(c.get("department") or "") if c.get("department") else None
        out.append({"case_id": c["case_id"], "patient": c.get("patient") or {}, "protocol": c.get("protocol"), "setting": c.get("setting", ""),
                    "board_date": c.get("board_date"), "owner": own, "owner_name": org.department_name(own) if own else "",
                    "ready": c.get("board_ready") or None, "gate_passed": bool(g.get("passed")), "gate": {"satisfied": g.get("satisfied"), "total": g.get("total")},
                    "summary": _summary_state(c["case_id"], st)})
    return out


def mark_ready(case_id: str, user: str, ready: bool = True, note: str = "", *, extra_text: str = "") -> dict:
    """The owning department marks its Case File ready for the board (or takes the mark back); the MDT Coordinator is told and builds
    the agenda from the ready Case Files (V2 item 6.1). Audited. A Case File must be listed to be marked ready. `extra_text` is added to
    the coordinator's notice (send_to_board: the meeting, the list and the presenter)."""
    from . import notify
    if case_id in config.PROTECTED_CASES:
        raise ValueError("That Case File is protected")
    c = store.get_case(case_id)
    if not c:
        raise ValueError(f"Case File {case_id} not found")
    if ready and not _listed(c):
        raise ValueError("List the Case File for the board first (protocol and board date)")
    note = " ".join(str(note or "").split())[:MAX_NOTE]
    now = store.now_iso()
    before = c.get("board_ready") or None
    if ready:
        c["board_ready"] = {"by": user or "", "at": now, "note": note}
    else:
        c.pop("board_ready", None)
    c.setdefault("board_ready_history", []).append({"ready": bool(ready), "by": user or "", "at": now, "note": note})
    store.save_case(c)
    store.audit(case_id, {"kind": "board_ready" if ready else "board_ready_withdrawn", "by": user or "", "note": note, "before": before})
    if ready:
        patient = (c.get("patient") or {}).get("name") or case_id
        try:
            notify.notify({"role": "coordinator"}, "board_ready", case_id, f"Ready for the board: {patient} ({case_id})",
                          f"{org.department_name(c['department']) if c.get('department') else user} marked this Case File ready for the board"
                          + (f" on {_ddmmyyyy(c.get('board_date'))}" if c.get("board_date") else "") + (f". Note: {note}" if note else ".")
                          + (f" {extra_text.strip()}" if str(extra_text or "").strip() else ""), by=user)
        except Exception:  # a notice never fails the mark
            pass
    return c


SEND_LISTS = {"discussion": "for discussion", "noting": "for noting"}


def send_to_board(case_id: str, user: str, *, list: str = "discussion", meeting_id: str = "", presenter: str = "", note: str = "",
                  reason: str = "") -> dict:
    """Send to the board (night-v3 item 1.4, design B7): the treating consultant picks the meeting (or none yet: the coordinator picks),
    for discussion or for noting, the presenter (the consultant or a resident on the team), a note for the coordinator and, when items
    are still open, the reason the board should see it anyway. The server requires the question for the board and that reason. Stores
    the choices on case.json ("presenter", "board_send", "board_send_history"), marks the Case File ready (mark_ready: audited, the
    coordinator told with the meeting, list and presenter), puts it on that meeting's list (the coordinator may still move it) and
    audits board_send. ValueError with a plain message. A resident's send is a proposal that runs this in the consultant's name."""
    from . import access, meetings, profiles, steps
    if case_id in config.PROTECTED_CASES:
        raise ValueError("That Case File is protected")
    c = store.get_case(case_id)
    if not c:
        raise ValueError(f"Case File {case_id} not found")
    if access.is_archived(c):
        raise ValueError(access.ARCHIVED_MESSAGE)
    if not _listed(c):
        raise ValueError("List the Case File for the board first (protocol and board date)")
    if not str(meetings._board_question(c, store.get_state(case_id)) or "").strip():
        raise ValueError("Write the question for the board first")
    if list not in SEND_LISTS:
        raise ValueError("Choose for discussion or for noting")
    reason = " ".join(str(reason or "").split())[:MAX_NOTE]
    note = " ".join(str(note or "").split())[:MAX_NOTE]
    open_items = steps.open_count(case_id) or 0
    if open_items > 0 and not reason:
        raise ValueError(f"Say why the board should see it with {open_items} {'item' if open_items == 1 else 'items'} open")
    presenter = str(presenter or "").strip() or user
    if presenter != user and presenter not in {x["user"] for x in access.team_residents(c)}:
        raise ValueError("The presenter must be you or a resident on the Case File team")
    s = None
    meeting_id = str(meeting_id or "").strip()
    if meeting_id:
        s = meetings.get(meeting_id)
        if not s:
            raise ValueError("Meeting not found")
        if s.get("status") != "planned" or s.get("cancelled"):
            raise ValueError("That meeting is not open")
        if str(s.get("date") or "") < datetime.now().date().isoformat():
            raise ValueError("That meeting date has passed: pick another meeting")
    now = store.now_iso()
    pname = profiles.display_name(presenter)
    send = {"list": list, "meeting_id": meeting_id, "presenter": presenter, "note": note, "reason": reason, "open_items": open_items, "by": user or "", "at": now}
    c["presenter"] = {"user": presenter, "name": pname, "set_by": user or "", "at": now}
    c["board_send"] = send
    c.setdefault("board_send_history", []).append(send)
    store.save_case(c)
    store.audit(case_id, {"kind": "board_send", "by": user or "", "list": list, "meeting_id": meeting_id, "presenter": presenter,
                          "open_items": open_items, "reason": reason})
    where = (f"Meeting {_ddmmyyyy(s.get('date'))}" + (f" {s['time']}" if s.get("time") else "")) if s else "Meeting not scheduled yet: pick a meeting"
    extra = f"{where}, {SEND_LISTS[list]}, presenter {pname}." + (f" Sent with {open_items} open: {reason}" if open_items and reason else "")
    c = mark_ready(case_id, user, True, note, extra_text=extra)
    if s:
        try:
            meetings.add_to_agenda(meeting_id, user, case_id, list, reason)
        except meetings.MeetingError as e:
            raise ValueError(str(e))
        c = store.get_case(case_id) or c
    return c


def _check_cases(case_ids, listed=True, keep=()) -> list[str]:
    """Explicit agenda: order kept, duplicates dropped; each Case File must exist, be listed (unless listed=False: the meeting's not-ready
    list takes a Case File that is not listed yet), not be protected and not be archived (security review #8; `keep`: the ids already
    on this agenda, which stay even when archived since)."""
    if not isinstance(case_ids, (list, tuple)):
        raise ValueError("The agenda must be a list of Case File ids")
    out = []
    for raw in case_ids:
        raw = str(raw or "").strip()
        try:
            cid = store.safe_id(raw)  # the id as stored on disk: the protected check below cannot be dodged by spelling
        except ValueError:
            raise ValueError(f"Invalid Case File id {raw!r}") from None
        if cid in config.PROTECTED_CASES:  # checked before anything is read from it
            raise ValueError(f"Case File {cid} holds real patient data and cannot join a board session")
        if cid != raw:
            raise ValueError(f"Invalid Case File id {raw!r}")
        c = store.get_case(cid)
        if not c:
            raise ValueError(f"Case File {cid} not found")
        if listed and not _listed(c):
            raise ValueError(f"Case File {cid} is not listed for the board")
        if cid not in keep and isinstance(c.get("archived"), dict) and c["archived"].get("at"):
            raise ValueError(f"Case File {cid} is archived. Take it out of the archive first.")
        if cid not in out:
            out.append(cid)
    return out


# ---- sessions -----------------------------------------------------------------------------------------------------------

def get(sid: str) -> dict | None:
    try:
        return store._read_json(_path(sid))
    except ValueError:
        return None


def _need(sid) -> dict:
    s = get(sid)
    if not s:
        raise ValueError(f"Board session {sid} not found")
    return s


def _open(s) -> None:
    if s.get("status") == "closed":
        raise ValueError("The board session is closed")


def _save(s) -> dict:
    store._write_json(_path(s["id"]), s)
    return s


def _item(s, case_id) -> dict:
    it = next((a for a in s["agenda"] if a["case_id"] == case_id), None)
    if not it:
        raise ValueError(f"Case File {case_id} is not on the agenda of this board session")
    return it


def create(date: str, by: str, case_ids: list[str] | None = None, title: str = "") -> dict:
    date = _check_date(date)
    if case_ids is None:  # the agenda is built from the Case Files the owners marked ready (V2 item 6.1); every listed one when none is marked
        listed = listed_for_date(date)
        ready = [c["case_id"] for c in listed if c.get("ready")]
        ids = ready or [c["case_id"] for c in listed]
        if not ids:
            raise ValueError(f"No Case File is listed for the board on {_ddmmyyyy(date)}")
    else:
        ids = _check_cases(case_ids)
        if not ids:
            raise ValueError("Choose at least one Case File for the agenda")
    title = str(title or "").strip()
    if len(title) > MAX_TITLE:
        raise ValueError(f"Session title is too long (at most {MAX_TITLE} characters)")
    sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    while _path(sid).exists():
        sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    now = store.now_iso()
    s = {"id": sid, "date": date, "title": title, "status": "planned", "created": now, "created_by": by or "",
         "started_at": None, "started_by": None, "closed_at": None, "closed_by": None, "current": None,
         "agenda": [_agenda_item(c, now, by) for c in ids],
         "attendance": {}, "members": [],
         "agents": {}, "log": [], "decisions": {}}
    s["attendance"] = {d["id"]: "not_marked" for d in attendance_list(s)}  # the hospital's sheet: heads first (V2 item 6.1)
    _save(s)
    _audit(sid, "created", by, date=date, cases=ids, not_marked_ready=[a["case_id"] for a in s["agenda"] if not a.get("owner_ready")])
    for a in s["agenda"]:
        _audit(sid, "agenda_added", by, a["case_id"], "agenda_added", date=date, owner_ready=a.get("owner_ready"))
    return s


def _agenda_item(case_id, now, by) -> dict:
    """An agenda item records whether the owner had marked the Case File ready when it was added (V2 item 6.1)."""
    c = store.get_case(case_id) or {}
    r = c.get("board_ready") or None
    return {"case_id": case_id, "status": "waiting", "added_at": now, "added_by": by or "", "owner_ready": bool(r), "ready_by": (r or {}).get("by"),
            "ready_at": (r or {}).get("at")}


def list_sessions() -> list[dict]:
    base = sessions_dir()
    rows = [s for s in (store._read_json(p) for p in base.glob("S*.json")) if s] if base.exists() else []
    rows.sort(key=lambda s: (s.get("date") or "", s.get("created") or ""), reverse=True)
    return [{"id": s["id"], "date": s.get("date"), "title": s.get("title", ""), "status": s.get("status"), "cases": len(s.get("agenda") or []),
             "created": s.get("created"), "created_by": s.get("created_by")} for s in rows]


# ---- meetings of the new interface (18 Oct): the same session files, a few more fields ------------------------------------------

def all_sessions() -> list[dict]:
    """Every session file as stored, newest date first (meetings.py reads the meeting fields from them)."""
    base = sessions_dir()
    rows = [s for s in (store._read_json(p) for p in base.glob("S*.json")) if s] if base.exists() else []
    rows.sort(key=lambda s: (s.get("date") or "", s.get("time") or "", s.get("created") or ""), reverse=True)
    return rows


def ensure_meeting_fields(s) -> dict:
    """A session written before the meetings existed gets the meeting fields in memory (saved by the next change): the lists are
    derived from its agenda (every Case File for discussion). In place; returns the session (None stays None)."""
    if not isinstance(s, dict):
        return s
    for k, v in (("time", ""), ("room", ""), ("video", False), ("minutes_per_case", None), ("code", None), ("agenda_sent_at", None)):
        s.setdefault(k, v)
    for k in ("agenda_sent_cases", "questions", "hands"):
        if not isinstance(s.get(k), list):
            s[k] = []
    for k in ("people", "cards", "outcomes", "ended"):
        if not isinstance(s.get(k), dict):
            s[k] = {}
    if not isinstance(s.get("agenda_lists"), dict):
        s["agenda_lists"] = {"discussion": [{"case_id": a["case_id"], "reason": ""} for a in s.get("agenda") or [] if a.get("case_id")],
                             "noting": [], "not_ready": []}
    for k in MEETING_LISTS:
        if not isinstance(s["agenda_lists"].get(k), list):
            s["agenda_lists"][k] = []
    if not isinstance(s.get("live"), dict):
        s["live"] = {"slide": 0, "opened": None, "timer": None}
    return s


def new_session(date: str, by: str, title: str = "", **fields) -> dict:
    """A session with an empty agenda (the MDT Coordinator fills the lists later): the meeting of the new interface. Same file, same
    shape as create(), plus the meeting fields given (time, room, video, minutes_per_case)."""
    date = _check_date(date)
    title = str(title or "").strip()
    if len(title) > MAX_TITLE:
        raise ValueError(f"Session title is too long (at most {MAX_TITLE} characters)")
    sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    while _path(sid).exists():
        sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    now = store.now_iso()
    s = {"id": sid, "date": date, "title": title, "status": "planned", "created": now, "created_by": by or "",
         "started_at": None, "started_by": None, "closed_at": None, "closed_by": None, "current": None,
         "agenda": [], "attendance": {}, "members": [], "agents": {}, "log": [], "decisions": {}, **fields}
    ensure_meeting_fields(s)
    s["attendance"] = {d["id"]: "not_marked" for d in attendance_list(s)}
    _save(s)
    _audit(sid, "created", by, date=date, cases=[], meeting=True, time=s.get("time") or "", room=s.get("room") or "", video=bool(s.get("video")))
    return s


def sync_agenda_lists(s, by) -> list[str]:
    """The old agenda[] (what the old /tb room, the minutes and the exports read) follows the meeting's lists: the Case Files for
    discussion, then for noting, in order; a Case File only in the not-ready list is not on the old agenda. Existing items keep their
    status; the attendance sheet gains the owners of new Case Files; a current Case File taken off the agenda is cleared. Audits every
    addition and removal. Returns the ids now on the agenda. The caller saves."""
    lists = s.get("agenda_lists") or {}
    ids = []
    for k in ("discussion", "noting"):
        for it in lists.get(k) or []:
            cid = (it or {}).get("case_id")
            if cid and cid not in ids and cid not in config.PROTECTED_CASES:
                ids.append(cid)
    old = {a["case_id"]: a for a in s.get("agenda") or []}
    now = store.now_iso()
    s["agenda"] = [old.get(c) or _agenda_item(c, now, by) for c in ids]
    for d in attendance_list(s):
        s.setdefault("attendance", {}).setdefault(d["id"], "not_marked")
    if s.get("current") and s["current"] not in ids:
        s["current"] = None
    for a in s["agenda"]:
        if a["case_id"] not in old:
            _audit(s["id"], "agenda_added", by, a["case_id"], "agenda_added", owner_ready=a.get("owner_ready"))
    for c in old:
        if c not in ids:
            _audit(s["id"], "agenda_removed", by, c, "agenda_removed")
    return ids


LIVE_HOURS = 12  # a session still "in_session" this long after it started was left open (nobody closed it): it no longer counts as running


def running_now(s, now: datetime | None = None, hours: float = LIVE_HOURS) -> bool:
    """True when the session is in session and was started within the last `hours` (a session without a start time counts on its own
    date only). A session left in session from an earlier day must not hold back the background work (the ready hook, the scheduler)
    for ever; it stays in session for the coordinator to close."""
    if not isinstance(s, dict) or s.get("status") != "in_session":
        return False
    now = now or datetime.now()
    started = str(s.get("started_at") or "")
    if started:
        try:
            t = datetime.fromisoformat(started)
        except ValueError:
            t = None
        if t is not None:
            if t.tzinfo is not None:
                t = t.astimezone().replace(tzinfo=None)
            return (now - t).total_seconds() < hours * 3600
    return str(s.get("date") or "") == now.date().isoformat()


def running_sessions(now: datetime | None = None) -> list[dict]:
    """The sessions running now (running_now), from the stored files."""
    return [s for s in all_sessions() if running_now(s, now)]


def planned_sessions() -> list[dict]:
    """The planned sessions (meetings not started, not closed, not cancelled), earliest first by date and time."""
    rows = [s for s in all_sessions() if s.get("status") == "planned"]
    rows.sort(key=lambda s: (s.get("date") or "", s.get("time") or "", s.get("created") or ""))
    return rows


def next_planned_after(s) -> dict | None:
    """The next planned session after this one (by date, then time): where a Case File not discussed moves to; None when none is planned."""
    key = (str((s or {}).get("date") or ""), str((s or {}).get("time") or ""))
    for cand in planned_sessions():
        if cand.get("id") == (s or {}).get("id"):
            continue
        if (str(cand.get("date") or ""), str(cand.get("time") or "")) > key:
            return cand
    return None


def audit_event(sid, kind, by, case_id=None, case_kind=None, **extra) -> None:
    """sessions/audit.jsonl, and the Case File's audit.jsonl when case_kind is given (as board_session_<case_kind>): for meetings.py."""
    _audit(sid, kind, by, case_id, case_kind, **extra)


def save_session(s) -> dict:
    """Write a session changed outside this module (meetings.py): the same atomic write as every function here."""
    return _save(s)


def set_agenda(sid, case_ids, by) -> dict:
    s = _need(sid); _open(s)
    ids = _check_cases(case_ids, keep={a.get("case_id") for a in s.get("agenda") or []})
    if not ids:
        raise ValueError("A board session needs at least one Case File")
    old = {a["case_id"]: a for a in s["agenda"]}
    now = store.now_iso()
    s["agenda"] = [old.get(c) or _agenda_item(c, now, by) for c in ids]
    for d in attendance_list(s):  # a new Case File brings its owner onto the sheet
        s["attendance"].setdefault(d["id"], "not_marked")
    if s.get("current") and s["current"] not in ids:  # the current Case File was removed: the next undecided one becomes current
        s["current"] = None
        if s["status"] == "in_session":
            nxt = next((a for a in s["agenda"] if a["status"] != "decided"), None)
            if nxt:
                nxt["status"], s["current"] = "current", nxt["case_id"]
    _save(s)
    _audit(sid, "agenda", by, cases=ids)
    for a in s["agenda"]:
        if a["case_id"] not in old:
            _audit(sid, "agenda_added", by, a["case_id"], "agenda_added", owner_ready=a.get("owner_ready"))
    for c in old:
        if c not in ids:
            _audit(sid, "agenda_removed", by, c, "agenda_removed")
    return s


# ---- attendance (V1 item 6.1) -------------------------------------------------------------------------------------------

def _dept(dept_id, attending=True) -> str:
    """A department id from an id, name or alias; attending=True restricts it to the specialties (the MDT Coordinator, a role, is
    accepted only as a member present)."""
    if not attending and org.is_coordinator_name(dept_id):
        return org.COORDINATOR_ID
    did = org.department_id(str(dept_id or ""))
    if not did:
        raise ValueError(f"Unknown department {dept_id!r}")
    return did


def set_attendance(sid, dept_id, status, by) -> dict:
    s = _need(sid); _open(s)
    did = _dept(dept_id)
    if status not in ATTENDANCE:
        raise ValueError(f"Attendance must be one of: {', '.join(ATTENDANCE)}")
    for k in [k for k in s["attendance"] if k != did and org.department_id(k) == did]:  # a V1 key for the same department
        del s["attendance"][k]
    s["attendance"][did] = status
    _save(s)
    _audit(sid, "attendance", by, department=did, status=status)
    return s


def add_member(sid, name, dept_id, by) -> dict:
    s = _need(sid); _open(s)
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        raise ValueError("Enter the member's name")
    if len(name) > MAX_NAME:
        raise ValueError(f"Name is too long (at most {MAX_NAME} characters)")
    did = _dept(dept_id, attending=False)  # a coordinator present at the board is recorded too
    m = {"id": "M" + uuid.uuid4().hex[:6], "name": name, "department": did, "added_by": by or "", "at": store.now_iso()}
    s["members"].append(m)
    if did != org.COORDINATOR_ID and s["attendance"].get(did, "not_marked") == "not_marked":
        s["attendance"][did] = "present"
    _save(s)
    _audit(sid, "member_added", by, member=m["id"], name=name, department=did)
    return s


def remove_member(sid, member_id, by) -> dict:
    s = _need(sid); _open(s)
    m = next((x for x in s["members"] if x["id"] == member_id), None)
    if not m:
        raise ValueError(f"Member {member_id} not found in this board session")
    s["members"].remove(m)
    _save(s)
    _audit(sid, "member_removed", by, member=m["id"], name=m["name"], department=m["department"])
    return s


def attendance(session) -> dict:
    """The session's attendance keyed by V2 department id: a V1 id stored before the 2.1 migration ("radio_diagnosis") resolves to its
    department; an explicit mark wins over "not_marked" when both keys exist; the V1 "tumour_board" key (a role now) is dropped."""
    out = {}
    for k, v in ((session or {}).get("attendance") or {}).items():
        did = org.department_id(k)
        if not did:
            continue
        if did not in out or out[did] == "not_marked":
            out[did] = v
    return out


def _case_surgical(case) -> list[str]:
    """The Case File's own surgical departments (its owner and participants that are in the hospital's surgical list; for a Case File
    without an owner, the protocol's default clinical department when surgical). A surgeon from one of them fills the surgical seat for
    this Case File (V2 item 6.2, plan section 11)."""
    surg = {org.department_id(x) for x in org.hospital().get("surgical_departments") or []} - {None}
    depts = _case_departments(case)
    if not depts and (case or {}).get("protocol"):
        try:
            from . import protocol
            ch = next((x for x in protocol.records(protocol.get(case["protocol"])) if x.get("id") == "clinical_history"), None)
            did = org.department_id((ch or {}).get("department") or "")
            depts = [did] if did else []
        except Exception:
            depts = []
    return [d for d in depts if d in surg]


def seat(session, case) -> dict:
    """The surgical seat for one Case File (V2 item 6.2): filled by Surgical Oncology when present, or by a surgeon recorded present
    from the Case File's own surgical department; otherwise the Surgical Oncology agent stands in. `check_pmjay`: filled only by
    departments outside the hospital's PM-JAY surgical oncology list (6.4: shown as "check PM-JAY requirement", never a block)."""
    att = attendance(session)
    own = _case_surgical(case)
    filled_by = [d for d in [ROLE_DEPARTMENT[SURGICAL_ROLE]] + own if att.get(d) == "present"]
    filled_by = list(dict.fromkeys(filled_by))
    pmj = {org.department_id(x) for x in org.hospital().get("pmjay_surgical_oncology") or []} - {None}
    names = [m["name"] for m in (session or {}).get("members") or [] if org.department_id(m.get("department") or "") in filled_by]
    return {"filled": bool(filled_by), "filled_by": filled_by, "filled_by_names": [org.department_name(d) for d in filled_by], "members": names,
            "agent": not filled_by, "check_pmjay": bool(filled_by) and not (set(filled_by) & pmj), "own_surgical": own,
            "own_surgical_names": [org.department_name(d) for d in own]}


def absent_roles(session, case_id=None) -> list[str]:
    """The agent roles active in this session (V2 item 6.2): a head not recorded as present (absent or not marked), any other specialty
    marked absent (Radiation Oncology and Nuclear Medicine are otherwise on demand), and, per Case File, the Surgical Oncology agent
    only when the surgical seat is not filled for that Case File (a surgeon of the Case File's own surgical department fills it)."""
    att = attendance(session)
    hs = set(head_ids())
    out = []
    for r, d in ROLE_DEPARTMENT.items():
        active = att.get(d) == "absent" or (d in hs and att.get(d, "not_marked") != "present")
        if r == SURGICAL_ROLE and case_id and active:
            c = store.get_case(case_id) if case_id not in config.PROTECTED_CASES else None
            active = not seat(session, c)["filled"]
        if active:
            out.append(r)
    return out


def absent_roles_by_case(session) -> dict:
    """{case_id: [roles]} for every Case File on the agenda."""
    return {a["case_id"]: absent_roles(session, a["case_id"]) for a in (session or {}).get("agenda") or []}


def may_open(r: dict, session) -> bool:
    """Who may open the Board room (V2 item 6.1, Phase 5 review decision): the MDT Coordinator; a doctor whose department is on the
    session's attendance sheet or who may read a Case File on the agenda (owner, participant, linked owner; the Vaidyx admin only through
    a break-glass window on one of them, security review #2)."""
    from . import access
    if not isinstance(r, dict) or r.get("disabled"):
        return False
    if (r.get("admin") and not r.get("vaidyx_admin")) or r.get("coordinator"):  # a Vaidyx admin: only the Case Files of its break-glass window (review #2)
        return True
    if not r.get("known"):
        return False
    mine = set(r.get("departments") or {})
    if mine & {d["id"] for d in attendance_list(session)}:
        return True
    for a in (session or {}).get("agenda") or []:
        c = store.get_case(a["case_id"]) if a.get("case_id") not in config.PROTECTED_CASES else None
        if c and access.scope(r, c) == access.FULL:
            return True
    return False


def allowed_cases(r: dict, session) -> set | None:
    """The Case Files of the agenda a user may read in full, or None for the MDT Coordinator (everything; the Vaidyx admin only its window). A
    doctor whose department is on the attendance sheet opens the room, but sees the log, decisions, minutes and export of its own
    Case Files only (Phase 6 review S2)."""
    from . import access
    if isinstance(r, dict) and ((r.get("admin") and not r.get("vaidyx_admin")) or r.get("coordinator")):
        return None
    out = set()
    for a in (session or {}).get("agenda") or []:
        cid = a.get("case_id")
        c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
        if c and isinstance(r, dict) and access.scope(r, c) == access.FULL:
            out.add(cid)
    return out


def session_view(session, allowed) -> dict:
    """The session as a doctor may see it: the log entries, the decisions and the agent records of the Case Files in `allowed` only
    (entries without a Case File, such as the start and close, stay). `allowed` None: the whole session."""
    if allowed is None:
        return session
    return {**session, "log": [e for e in session.get("log") or [] if not e.get("case_id") or e.get("case_id") in allowed],
            "decisions": {k: v for k, v in (session.get("decisions") or {}).items() if k in allowed},
            "agents": {k: v for k, v in (session.get("agents") or {}).items() if k in allowed}}


def session_surgical(session) -> set:
    """The surgical departments of the Case Files on the agenda (their owners and participants in the hospital's surgical list): for a
    session-level count such as the dashboard quorum, a surgeon from one of them fills the surgical seat (V2 items 6.2 / 6.4)."""
    out = set()
    for a in (session or {}).get("agenda") or []:
        cid = a.get("case_id")
        c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
        if c:
            out.update(_case_surgical(c))
    return out


def participants(session) -> dict:
    """Who took part, for the decision record (7.1 checks the PM-JAY composition from it)."""
    att = attendance(session)
    members = session.get("members") or []
    present = [org.department_name(d) for d, v in att.items() if v == "present"]
    absent = [org.department_name(d) for d, v in att.items() if v == "absent"]
    named = {m["department"] for m in members}
    parts = [f"{m['name']} ({org.department_name(m['department'])})" for m in members]
    parts += [org.department_name(d) for d, v in att.items() if v == "present" and d not in named]
    text = ", ".join(parts)
    if absent:
        text += ("; " if text else "") + "absent: " + ", ".join(absent)
    return {"text": text or "Attendance not recorded", "present": present, "absent": absent,
            "members": [{"name": m["name"], "department": m["department"], "department_name": org.department_name(m["department"])} for m in members]}


# ---- running the session ------------------------------------------------------------------------------------------------

def start(sid, by) -> dict:
    s = _need(sid)
    if s["status"] != "planned":
        raise ValueError("Only a planned board session can be started")
    s["status"], s["started_at"], s["started_by"] = "in_session", store.now_iso(), by or ""
    first = next((a for a in s["agenda"] if a["status"] != "decided"), None)
    if first:
        first["status"], s["current"] = "current", first["case_id"]
        s["current_since"] = store.now_iso()
    _save(s)
    _audit(sid, "started", by)
    if first:
        _audit(sid, "current", by, first["case_id"], "current")
    return s


def set_current(sid, case_id, by) -> dict:
    s = _need(sid); _open(s)
    if s["status"] != "in_session":
        raise ValueError("Start the board session first")
    it = _item(s, case_id)
    prev = next((a for a in s["agenda"] if a["case_id"] == s.get("current")), None)
    if prev and prev is not it:
        prev["status"] = "decided" if prev["case_id"] in s["decisions"] else "waiting"
    if it["status"] != "decided":
        it["status"] = "current"
    _tick_timing(s)  # time spent on the case leaving the floor (12 Oct)
    s["current"] = case_id
    s["current_since"] = store.now_iso()
    _save(s)
    _audit(sid, "current", by, case_id, "current")
    return s


def _tick_timing(s) -> None:
    """Add the time spent on the current case to s["timing"] (seconds per Case File), from current_since to now (12 Oct)."""
    cur, since = s.get("current"), s.get("current_since")
    if not cur or not since:
        return
    try:
        from datetime import datetime
        secs = max(0.0, (datetime.fromisoformat(store.now_iso()) - datetime.fromisoformat(since)).total_seconds())
    except Exception:
        return
    t = s.setdefault("timing", {})
    t[cur] = round(float(t.get(cur) or 0) + secs, 1)


def timing(s) -> dict:
    """{case_id: seconds} including the case on the floor now."""
    out = dict(s.get("timing") or {})
    cur, since = s.get("current"), s.get("current_since")
    if s.get("status") == "in_session" and cur and since:
        try:
            from datetime import datetime
            out[cur] = round(float(out.get(cur) or 0) + max(0.0, (datetime.fromisoformat(store.now_iso()) - datetime.fromisoformat(since)).total_seconds()), 1)
        except Exception:
            pass
    return out


def _fail_waiting(s, message) -> list[list[str]]:
    """Turn every agent still "queued" or "running" into an error with this message; returns the [case_id, role] pairs changed."""
    now, pairs = store.now_iso(), []
    for case_id, roles in (s.get("agents") or {}).items():
        for role, a in roles.items():
            if (a or {}).get("status") in ("queued", "running"):
                roles[role] = {"status": "error", "message": message, "at": now}
                pairs.append([case_id, role])
    return pairs


def fail_waiting(sid, message) -> dict:
    """Agents left queued / running (briefs still preparing when the session closed or the service stopped) become errors, so a
    later load never waits on them. Works on a closed session too."""
    s = _need(sid)
    pairs = _fail_waiting(s, str(message or ""))
    if pairs:
        _save(s)
        _audit(sid, "agents_failed", "system", pairs=pairs, message=str(message or "")[:300])
    return s


def close(sid, by) -> dict:
    s = _need(sid); _open(s)
    pairs = _fail_waiting(s, CLOSED_EARLY)
    if pairs:
        _save(s)
        _audit(sid, "agents_failed", "system", pairs=pairs, message=CLOSED_EARLY)
    _tick_timing(s)
    s["current_since"] = None
    s["status"], s["closed_at"], s["closed_by"] = "closed", store.now_iso(), by or ""
    _save(s)
    _audit(sid, "closed", by, timing=s.get("timing") or {})
    return s


# ---- agents and the agent log (V1 items 6.2 and 6.3) -------------------------------------------------------------------

def _role(role) -> str:
    if role not in ROLE_DEPARTMENT:
        raise ValueError(f"Unknown agent role {role!r}")
    return role


def set_agent(sid, case_id, role, status, **info) -> dict:
    s = _need(sid); _open(s)
    _item(s, case_id); _role(role)
    if status not in AGENT_STATUSES:
        raise ValueError(f"Agent status must be one of: {', '.join(AGENT_STATUSES)}")
    s["agents"].setdefault(case_id, {})[role] = {"status": status, "at": store.now_iso(), **info}
    _save(s)
    msg = {"message": str(info["message"])[:300]} if info.get("message") else {}
    _audit(sid, "agent", "system", case_id, "agent" if status in ("ready", "error", "no_documents") else None, role=role, status=status, **msg)
    return s


def _entry(s, case_id, role, label, kind, text, citations, source, model, **extra) -> dict:
    return {"id": f"P{len(s['log']) + 1}", "case_id": case_id, "role": role, "label": label, "kind": kind, "text": text,
            "citations": list(citations or []), **extra, "source": source, "model": model, "at": store.now_iso(),
            "mark": None, "mark_by": None, "mark_at": None, "note": ""}


def log_brief(sid, case_id, role, brief) -> int:
    """One entry per brief item, per point for review (with its references), or one 'no_documents' entry. Entries of an older brief for
    the same Case File and role are kept and flagged superseded. A brief already logged (same 'generated' time) is not logged twice."""
    s = _need(sid); _open(s)
    _item(s, case_id); _role(role)
    gen = brief.get("generated")
    old = [e for e in s["log"] if e["case_id"] == case_id and e["role"] == role and e["source"] == "brief" and not e.get("superseded")]
    if gen and old and all(e.get("brief_generated") == gen for e in old):
        return 0
    label, model = brief.get("label"), brief.get("model")
    common = {"source": "brief", "model": model}
    new = []

    def add(kind, text, citations=(), **extra):
        e = _entry(s, case_id, role, label, kind, text, citations, **common, **extra)
        e["brief_generated"] = gen
        s["log"].append(e); new.append(e)
    if brief.get("no_documents"):  # the department's open requests travel with the message (V1 item 6.6)
        items = [f"{x.get('label')}: {x.get('what')}" if x.get("what") else str(x.get("label") or "") for x in brief.get("open_items") or []]
        add("no_documents", str(brief.get("message") or "") + (". Open requests: " + "; ".join(items) if items else ""))
    else:
        for sec in brief.get("sections") or []:
            for it in sec.get("items") or []:
                add("brief_item", it.get("text", ""), it.get("citations"), heading=sec.get("heading", ""), flags=list(it.get("flags") or []),
                    approximate=bool(it.get("approximate")))
        for p in brief.get("points_for_review") or []:
            add("point_for_review", p.get("text", ""), p.get("citations"), references=list(p.get("references") or []), flags=list(p.get("flags") or []),
                approximate=bool(p.get("approximate")))
        for x in brief.get("not_documented") or []:  # gaps the agent names (checked against the Case File before they were kept)
            add("not_documented", str(x))
    for e in old:
        e["superseded"] = True
    _save(s)
    _audit(sid, "brief_logged", "system", case_id, role=role, entries=len(new), superseded=len(old), generated=gen)
    return len(new)


def log_answer(sid, case_id, role, question, answer, by="") -> dict:
    """One 'answer' entry for a live question to an agent: the verified statements joined, or the refusal / not documented message.
    by: who asked (kept on the entry and audited); the answer's removed statements (V1 item 6.4) are kept on the entry."""
    s = _need(sid); _open(s)
    _item(s, case_id); _role(role)
    stmts = list(answer.get("statements") or [])
    status = answer.get("status") or ("answered" if stmts else "not_documented")
    text = " ".join(x.get("text", "") for x in stmts) if stmts else str(answer.get("message") or "")
    e = _entry(s, case_id, role, answer.get("label"), "answer", text, [c for x in stmts for c in x.get("citations") or []],
               "live", answer.get("model"), question=str(question or ""), status=status, statements=stmts, references=list(answer.get("references") or []),
               asked_by=by or "", removed=list(answer.get("removed") or []))
    s["log"].append(e)
    _save(s)
    _audit(sid, "answer_logged", by or "system", case_id, "answer", role=role, entry=e["id"], status=status, question=str(question or "")[:300])
    return e


def entries(session, case_id) -> list[dict]:
    return [e for e in (session or {}).get("log") or [] if e["case_id"] == case_id]


def link_decision(sid, case_id, record, by) -> dict:
    """Link the board's recorded decision (postboard.record_decision) to the Case File's agenda item. Allowed after close: documenting."""
    s = _need(sid)
    it = _item(s, case_id)
    if not record or not record.get("id"):
        raise ValueError("The board decision record has no id")
    s["decisions"][case_id] = {"board_record": record["id"], "decision_text": record.get("decision_text"),
                               "recorded_by": record.get("recorded_by") or record.get("entered_by"), "recorded_at": record.get("recorded_at"),
                               "linked_by": by or "", "at": store.now_iso()}
    it["status"] = "decided"
    _save(s)
    _audit(sid, "decision_linked", by, case_id, "decision", record=record["id"])
    return s


def decision_amended(sid, case_id, record, by) -> dict | None:
    """The board's decision was amended after a flag was corrected (V1 item 7.3): the session shows the current version. None when the
    session no longer exists or the record is not the one linked to this agenda item."""
    s = get(sid)
    d = (s or {}).get("decisions", {}).get(case_id) if s else None
    if not d or d.get("board_record") != (record or {}).get("id"):
        return None
    d.update({"decision_text": record.get("decision_text"), "version": record.get("version", 1), "final": bool((record.get("resolution") or {}).get("final")),
              "amended_at": store.now_iso(), "amended_by": by or ""})
    _save(s)
    _audit(sid, "decision_amended", by, case_id, "decision", record=record["id"], version=record.get("version", 1))
    return s


def mark(sid, case_id, entry_id, mark, by, note="") -> dict:
    """Mark one agent point discussed / accepted / not relevant (None clears). Only once the board's decision is linked; allowed after
    close (documenting the meeting)."""
    s = _need(sid)
    _item(s, case_id)
    if mark is not None and mark not in MARKS:
        raise ValueError(f"Mark must be one of: {', '.join(MARKS)}")
    if case_id not in s["decisions"]:
        raise ValueError("Record the board decision first")
    e = next((x for x in s["log"] if x["id"] == entry_id and x["case_id"] == case_id), None)
    if not e:
        raise ValueError(f"Agent log entry {entry_id} not found for Case File {case_id}")
    note = str(note or "").strip()
    if len(note) > MAX_NOTE:
        raise ValueError(f"Note is too long (at most {MAX_NOTE} characters)")
    e["mark"], e["note"] = mark, note if mark else ""
    e["mark_by"], e["mark_at"] = (by or "", store.now_iso()) if mark else (None, None)
    _save(s)
    _audit(sid, "mark", by, case_id, "mark", entry=entry_id, mark=mark, note=note[:300] if mark else "")
    return s


# ---- export: what the agents said vs what the board decided (V1 item 6.3) ---------------------------------------------

def _patient(case_id) -> dict:
    p = (store.get_case(case_id) or {}).get("patient") or {}
    return {k: p[k] for k in ("name", "mrn", "uhid", "agesex") if p.get(k)}


def _marks(log) -> dict:
    """Counts over the current entries; a superseded entry counts only when it was marked."""
    out = {k: 0 for k in MARKS} | {"unmarked": 0}
    for e in log:
        if e.get("mark") in MARKS:
            out[e["mark"]] += 1
        elif not e.get("superseded"):
            out["unmarked"] += 1
    return out


def _printable_rule(case_id):
    """entry -> bool: an approximate (near-match) entry is printable only when the brief it came from is the Case File's current brief
    for that role and an expert has reviewed it (V1 item 6.5)."""
    arts = None

    def ok(e) -> bool:
        nonlocal arts
        if not e.get("approximate"):
            return True
        if arts is None:
            arts = (store.get_state(case_id) or {}).get("artefacts") or {}
        b = arts.get(f"brief_{e.get('role')}") or {}
        return bool(e.get("brief_generated")) and b.get("generated") == e.get("brief_generated") and (b.get("review") or {}).get("status") == "reviewed"
    return ok


def export(sid, allowed=None) -> dict:
    """`allowed`: the Case Files whose agent log and decision this reader may see (None: all; Phase 6 review S2)."""
    s = _need(sid)
    names = {d["id"]: d["name"] for d in specialties()}
    att = attendance(s)
    members = s.get("members") or []
    attendance_rows = [{"department": d, "name": names.get(d) or org.department_name(d), "status": v,
                        "members": [m["name"] for m in members if org.department_id(m["department"]) == d]} for d, v in att.items()]
    cases = []
    for a in s["agenda"]:
        if allowed is not None and a["case_id"] not in allowed:  # another department's Case File: nothing of it
            cases.append({"case_id": a["case_id"], "status": a["status"], "restricted": True, "patient": {}, "protocol": None, "agents": {},
                          "agent_log": [], "decision": None, "marks": _marks([])}); continue
        c = store.get_case(a["case_id"]) or {}
        printable = _printable_rule(a["case_id"])
        log = [{**e, "printable": printable(e)} for e in entries(s, a["case_id"])]
        cases.append({"case_id": a["case_id"], "status": a["status"], "patient": _patient(a["case_id"]), "protocol": c.get("protocol"),
                      "agents": (s.get("agents") or {}).get(a["case_id"], {}),
                      "agent_log": [e for e in log if not e.get("superseded")] + [e for e in log if e.get("superseded")],
                      "decision": (s.get("decisions") or {}).get(a["case_id"]), "marks": _marks(log)})
    return {"session": {k: s.get(k) for k in ("id", "date", "title", "status", "created", "created_by", "started_at", "started_by", "closed_at", "closed_by")},
            "attendance": attendance_rows, "participants": participants(s), "absent_roles": absent_roles(s), "cases": cases, "note": NOTE,
            "timing": timing(s)}  # seconds per Case File on the floor (12 Oct)


# ---- after the session: follow-up of the board's decisions and the minutes (V2 item 6.1) ------------------------------------------

def followup(session, allowed=None) -> dict:
    """The Tumour Board actions that came out of this session's decisions (postboard.record_decision turns them into follow-up
    requests in the Responsible Department's inbox, V1 item 7.4), with their state now: open, overdue, closed. `allowed`: only
    these Case Files (None: all)."""
    today = store.now_iso()[:10]
    rows = []
    for cid, d in ((session or {}).get("decisions") or {}).items():
        if cid in config.PROTECTED_CASES or (allowed is not None and cid not in allowed):
            continue
        st = store.get_state(cid)
        for a in st.get("actions") or []:
            if a.get("source") != "board" or a.get("board_record") != d.get("board_record"):
                continue
            done = a.get("status") == "completed"
            due = str(a.get("due") or "")[:10]
            rows.append({"case_id": cid, "patient": _patient(cid).get("name") or cid, "action_id": a.get("id"), "department": a.get("department") or "",
                         "task": a.get("what") or a.get("label") or "", "due": due, "status": a.get("status") or "", "completed": a.get("completed"),
                         "overdue": bool(due) and not done and due < today, "kind": a.get("kind") or ""})
    rows.sort(key=lambda x: (x["status"] == "completed", x["due"] or "9999", x["case_id"]))
    return {"actions": rows, "open": sum(1 for x in rows if x["status"] != "completed"), "overdue": sum(1 for x in rows if x["overdue"]),
            "closed": sum(1 for x in rows if x["status"] == "completed")}


def _att_label(v) -> str:
    return {"present": "Present", "absent": "Absent", "not_marked": "Not recorded"}.get(v, v or "Not recorded")


def minutes(sid, allowed=None) -> dict:
    """The minutes of a board session (V2 item 6.1): the hospital, the session, the attendance sheet (heads first) with the members by
    name and the AI support agents that stood in, then per Case File the patient, the protocol, the owner, who marked it ready, the
    decision as dictated (outcome, text, intention, trial, corrections, divergent opinions, actions, next review), the surgical seat and
    the PM-JAY composition result, then the follow-up of every action. Nothing here is a model output: the agents' points are in the
    agent log export (6.3). `allowed`: the Case Files this reader may see in full (None: all); the others print as restricted,
    with no patient data, decision or seat (Phase 6 review S2)."""
    from . import postboard, protocol
    s = _need(sid)
    att = attendance(s)
    members = s.get("members") or []
    by_case = absent_roles_by_case(s)
    agent_rec = s.get("agents") or {}  # the session's own record of which agents prepared a brief (a head who arrived later does not erase it)

    def stood_in(role):
        return [cid for cid, by in agent_rec.items() if ((by or {}).get(role) or {}).get("status") in ("ready", "no_documents")]

    def agents_of(cid):
        done = [r for r, x in (agent_rec.get(cid) or {}).items() if (x or {}).get("status") in ("ready", "no_documents")]
        return done or (by_case.get(cid, []) if s.get("status") == "planned" else [])  # before the start: who would stand in
    sheet = []
    for d in attendance_list(s):
        sheet.append({**d, "status": att.get(d["id"], "not_marked"), "status_label": _att_label(att.get(d["id"], "not_marked")),
                      "members": [m["name"] for m in members if org.department_id(m.get("department") or "") == d["id"]],
                      "agent_stood_in": stood_in(d["role"]) if d.get("role") else []})
    coord = [m["name"] for m in members if m.get("department") == org.COORDINATOR_ID]
    cases = []
    for i, a in enumerate(s["agenda"]):
        cid = a["case_id"]
        if allowed is not None and cid not in allowed:
            cases.append({"n": i + 1, "case_id": cid, "restricted": True}); continue
        c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
        if not c:
            cases.append({"n": i + 1, "case_id": cid, "missing": True}); continue
        st = store.get_state(cid)
        d = (s.get("decisions") or {}).get(cid)
        rec = next((b for b in st.get("board_records") or [] if d and b.get("id") == d.get("board_record")), None)
        own = org.department_id(c.get("department") or "") if c.get("department") else None
        g = st.get("gate") or {}
        try:
            plabel = protocol.get(c["protocol"]).get("label") if c.get("protocol") else ""
        except Exception:
            plabel = c.get("protocol") or ""
        comp = ((rec or {}).get("adjudication") or {}).get("composition") if rec else None
        cases.append({"n": i + 1, "case_id": cid, "patient": _patient(cid), "protocol": c.get("protocol"), "protocol_label": plabel or c.get("protocol") or "",
                      "setting": c.get("setting") or "", "owner": own, "owner_name": org.department_name(own) if own else "",
                      "ready": c.get("board_ready") or None, "owner_ready_at_listing": a.get("owner_ready"),
                      "gate": {"passed": g.get("passed"), "satisfied": g.get("satisfied"), "total": g.get("total")},
                      "seat": seat(s, c), "agents": agents_of(cid), "agenda_status": a.get("status"), "minutes_on_floor": round((timing(s).get(cid) or 0) / 60, 1),
                      "decision": None if not rec else {
                          "record": rec["id"], "recorded_by": rec.get("recorded_by") or rec.get("entered_by"), "recorded_at": rec.get("recorded_at"),
                          "outcome": rec.get("outcome_type") or "decision", "outcome_label": postboard.OUTCOMES.get(rec.get("outcome_type") or "decision", "Decision recorded"),
                          "text": d.get("decision_text") if d else rec.get("decision_text"), "version": rec.get("version", 1),
                          "intent": rec.get("intent_as_recorded") or "", "trial_considered": rec.get("trial_considered") or "", "key_worker": rec.get("key_worker") or "",
                          "deferred_reason": rec.get("deferred_reason") or "", "referred_to": rec.get("referred_to") or "",
                          "report_corrections_raised": rec.get("report_corrections_raised") or "", "divergent_opinions": rec.get("divergent_opinions") or "",
                          "next_review": rec.get("next_review") or "", "participants": rec.get("participants") or "",
                          "actions": [{"department": x.get("department") or "", "task": x.get("task") or "", "due": x.get("due") or ""} for x in rec.get("actions") or []],
                          "composition": comp, "flags_open": sum(1 for f in (rec.get("adjudication") or {}).get("flags") or [] if postboard.needs_resolution(f) and not f.get("resolution")),
                          "final": bool((rec.get("resolution") or {}).get("final"))}})
    return {"hospital": org.hospital().get("name") or "", "pmjay_empanelled": bool(org.hospital().get("pmjay_empanelled", True)),
            "session": {k: s.get(k) for k in ("id", "date", "title", "status", "created", "created_by", "started_at", "started_by", "closed_at", "closed_by")},
            "attendance": sheet, "coordinators_present": coord, "participants": participants(s), "cases": cases, "followup": followup(s, allowed),
            "generated": store.now_iso(),
            "note": "Minutes as dictated by the board and entered by the MDT Coordinator. The AI support agents' points and the board's marks on them are "
                    "in the agent log export; an agent is never a member of the board."}


def minutes_html(sid, allowed=None) -> str:
    """Printable minutes (inline CSS, no scripts, no em dashes). Verified quotes do not appear here: the minutes hold what people recorded."""
    x = minutes(sid, allowed)
    se = x["session"]
    title = f"Tumour Board minutes: {_ddmmyyyy(se['date'])}" + (f", {se['title']}" if se.get("title") else "")
    status = {"planned": "Planned", "in_session": "In session", "closed": "Closed"}.get(se.get("status"), se.get("status"))
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_h(title)}</title><style>{CSS}</style></head><body>",
           f"<h1>{_h(title)}</h1>", f"<div class='meta'>{_h(x['hospital'] or 'Hospital')} | Session {_h(se['id'])} | Status: {_h(status)}"
           + (f" | Started {_h(_ddmmyyyy(se['started_at']))}" if se.get("started_at") else "") + (f" | Closed {_h(_ddmmyyyy(se['closed_at']))}" if se.get("closed_at") else "")
           + f" | Created by {_h(se.get('created_by') or '')}</div>"]
    out.append("<h2>Attendance</h2><table><tr><th>Department</th><th>Seat</th><th>Attendance</th><th>Members present</th><th>AI support stood in</th></tr>")
    for a in x["attendance"]:
        why = "Head" if a.get("head") else ("On demand" if a.get("on_demand") else _h(a.get("why") or ""))
        out.append(f"<tr><td>{_h(a['name'])}</td><td>{why}</td><td>{_h(a['status_label'])}</td><td>{_h(', '.join(a['members']))}</td>"
                   f"<td>{_h('for ' + ', '.join(a['agent_stood_in'])) if a.get('agent_stood_in') else ''}</td></tr>")
    out.append("</table>")
    if x["coordinators_present"]:
        out.append(f"<div class='meta'>MDT Coordinator present: {_h(', '.join(x['coordinators_present']))}</div>")
    for c in x["cases"]:
        if c.get("missing"):
            out.append(f"<h2>{c['n']}. {_h(c['case_id'])}</h2><div><i>This Case File no longer exists.</i></div>"); continue
        if c.get("restricted"):
            out.append(f"<h2>{c['n']}. {_h(c['case_id'])}</h2><div><i>Restricted: another department's Case File. Its patient, decision and follow-up are not shown to your department.</i></div>"); continue
        p = c["patient"]
        ident = ", ".join(v for v in (p.get("name"), (f"UHID/MRN {p.get('mrn') or p.get('uhid')}" if p.get("mrn") or p.get("uhid") else ""), p.get("agesex")) if v)
        out.append(f"<h2>{c['n']}. {_h(ident or c['case_id'])}</h2>")
        line = [f"Case File {c['case_id']}", c["protocol_label"] + (f" ({c['setting']})" if c.get("setting") else "")]
        if c.get("owner_name"):
            line.append(f"Responsible Department: {c['owner_name']}")
        r = c.get("ready")
        line.append(f"Marked ready by {r['by']} on {_ddmmyyyy(r['at'])}" if r else "Not marked ready by the owner")
        g = c["gate"]
        line.append("Pre-Authorization met" if g.get("passed") else (f"Pre-Authorization {g.get('satisfied')}/{g.get('total')} at export" if g.get("total") else "Pre-Authorization not evaluated"))
        if c.get("minutes_on_floor"):
            line.append(f"{c['minutes_on_floor']} min on the floor")
        out.append(f"<div class='meta'>{_h(' | '.join(line))}</div>")
        st_ = c["seat"]
        seat_text = ("Surgical seat: " + ", ".join(st_["filled_by_names"]) + (f" ({', '.join(st_['members'])})" if st_["members"] else "")
                     + (" ; check PM-JAY requirement (a surgical oncologist)" if st_["check_pmjay"] and x["pmjay_empanelled"] else "")
                     + (" ; the Surgical Oncology AI support agent had prepared a brief before the seat was filled" if SURGICAL_ROLE in (c.get("agents") or []) else "")) if st_["filled"]             else "Surgical seat: no surgeon recorded present; the Surgical Oncology AI support agent stood in (role-specific support, never a member)"
        agents_ = [org.department_name(ROLE_DEPARTMENT[r_]) for r_ in c.get("agents") or [] if r_ != SURGICAL_ROLE]
        out.append(f"<div class='meta'>{_h(seat_text)}" + (f" | AI support stood in for: {_h(', '.join(agents_))}" if agents_ else "") + "</div>")
        d = c.get("decision")
        if not d:
            out.append("<div><i>No board decision recorded for this Case File.</i></div>"); continue
        out.append(f"<div><b>{_h(d['outcome_label'])}</b></div><div style='white-space:pre-wrap'>{_h(d['text'])}</div>")
        meta = [f"Record {d['record']}" + (f", version {d['version']}" if (d.get('version') or 1) > 1 else ""), f"recorded by {d.get('recorded_by') or ''}", _ddmmyyyy(d.get("recorded_at"))]
        for k, lbl in (("intent", "Intention to treat"), ("trial_considered", "Clinical trial considered"), ("key_worker", "Key worker"), ("deferred_reason", "Awaited"),
                       ("referred_to", "Referred to"), ("report_corrections_raised", "Report corrections raised"), ("divergent_opinions", "Divergent opinions"), ("next_review", "Next review")):
            if d.get(k):
                meta.append(f"{lbl}: {_ddmmyyyy(d[k]) if k == 'next_review' else d[k]}")
        out.append(f"<div class='meta'>{_h(' | '.join(m for m in meta if m))}</div>")
        if d.get("participants"):
            out.append(f"<div class='meta'>Participants: {_h(d['participants'])}</div>")
        if d["actions"]:
            out.append("<table><tr><th>Responsible Department</th><th>Action</th><th>Due</th></tr>"
                       + "".join(f"<tr><td>{_h(a['department'])}</td><td>{_h(a['task'])}</td><td>{_h(_ddmmyyyy(a['due']))}</td></tr>" for a in d["actions"]) + "</table>")
        comp = d.get("composition") or {}
        if comp.get("not_applicable"):
            out.append(f"<div class='meta'>PM-JAY board composition: not applicable ({_h(comp.get('reason') or 'the hospital is not PM-JAY empanelled')})</div>")
        elif comp.get("checked"):
            out.append("<div class='meta'>PM-JAY board composition (HBP 2.2): " + ("surgical, radiation and medical oncologist recorded present" if not comp.get("missing")
                       else "not recorded as present: " + _h(", ".join(comp["missing"]))) + (f". {_h(comp['seat_note'])}" if comp.get("seat_note") else "") + "</div>")
        if d.get("flags_open"):
            out.append(f"<div class='meta'>{d['flags_open']} adjudication flag(s) still awaiting resolution on the Case File.</div>")
    fu = x["followup"]
    out.append(f"<h2>Follow-up</h2><div class='meta'>{fu['open']} open, {fu['overdue']} overdue, {fu['closed']} closed</div>")
    if fu["actions"]:
        out.append("<table><tr><th>Case File</th><th>Responsible Department</th><th>Action</th><th>Due</th><th>Status</th></tr>"
                   + "".join(f"<tr><td>{_h(a['case_id'])}</td><td>{_h(a['department'])}</td><td>{_h(a['task'])}</td><td>{_h(_ddmmyyyy(a['due']))}</td>"
                             f"<td>{'Closed ' + _h(_ddmmyyyy(a['completed'])) if a['status'] == 'completed' else ('Overdue' if a['overdue'] else _h(a['status'] or 'open'))}</td></tr>" for a in fu["actions"])
                   + "</table>")
    out.append(f"<footer><p>{_h(x['note'])}</p><p>Exported {_h(_ddmmyyyy(x['generated']))}</p></footer></body></html>")
    return "".join(out)


def _verbatim(x) -> str:
    """A verified quote (citation or guideline reference): escaped, otherwise exactly as stored."""
    return html.escape(str(x if x is not None else ""), quote=True)


def _h(x) -> str:
    """Any other text: escaped, an em dash printed as '-' (no em dashes in reports)."""
    return _verbatim(str(x if x is not None else "").replace("\u2014", "-"))


def model_words(label) -> str:
    """How a model is named in a report: always with "(non-medical)" (project model-labelling rule)."""
    label = str(label or "").strip()
    if not label or label == "reasoner":
        return "the reasoner model (non-medical)"
    return label if "non-medical" in label.lower() else f"{label} (non-medical)"


def _uses_model(e) -> bool:
    return e.get("kind") != "no_documents"  # a no-documents entry involved no model call


def _cite(c) -> str:
    scan = ", from scan (OCR)" if c.get("source_method") == "vision-transcription" else ""  # V1 item 8.1
    return f"[{_h(c.get('doc_title') or c.get('doc_id'))}, {_verbatim(c.get('quote'))}{scan}]"


def _ref(r) -> str:
    page = r.get("page")
    page = f"page {page}" if page not in (None, "") else ""
    parts = [_h(x) for x in (r.get("org"), r.get("title"), page) if x] + ([_verbatim(r["quote"])] if r.get("quote") else [])
    return "Reference: " + ", ".join(parts)


def _said(e) -> str:
    kind = _h(KIND_LABELS.get(e["kind"], e["kind"])) + (f" ({_h(e['heading'])})" if e.get("heading") else "")
    if e["kind"] == "answer" and e.get("status") in ANSWER_STATUS_LABELS:
        kind += " &middot; " + _h(ANSWER_STATUS_LABELS[e["status"]])
    model = f" &middot; {_h(model_words(e.get('model')))}" if _uses_model(e) else ""
    out = [f"<div class='meta'><b>{_h(e.get('label') or e['role'])}</b> &middot; {kind}{model}"
           f" &middot; {_h(e['id'])}{' &middot; superseded by a newer brief' if e.get('superseded') else ''}</div>"]
    if e["kind"] == "answer":
        out.append(f"<div class='q'>Question: {_h(e.get('question'))}</div>")
    if not e.get("printable", True):  # near-match item of a brief no expert has reviewed (V1 item 6.5)
        out.append(f"<div><i>{_h(NOT_PRINTED)}</i></div>")
        return "".join(out)
    out.append(f"<div>{_h(e.get('text'))}</div>")
    if e.get("flags"):  # approximate source match, negation check (V1 items 6.5, 1.1)
        out.append("<div class='meta'>Check: " + "; ".join(_h(f) for f in e["flags"]) + "</div>")
    if e.get("citations"):
        out.append("<div class='cite'>" + " ".join(_cite(c) for c in e["citations"]) + "</div>")
    for r in e.get("references") or []:
        out.append(f"<div class='ref'>{_ref(r)}</div>")
    return "".join(out)


def _decided(e) -> str:
    out = f"<b>{_h(MARKS.get(e.get('mark'), 'Not marked'))}</b>"
    if e.get("note"):
        out += f"<div>{_h(e['note'])}</div>"
    if e.get("mark_by"):
        out += f"<div class='meta'>{_h(e['mark_by'])}, {_h(_ddmmyyyy(e.get('mark_at')))}</div>"
    return out


CSS = """body{font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#1a1a1a;background:#fff;margin:24px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:14px;margin:22px 0 6px}.meta{color:#555;font-size:11px}
table{border-collapse:collapse;width:100%;margin:6px 0}th,td{border:1px solid #bbb;padding:5px 7px;vertical-align:top;text-align:left}
th{background:#eef2f5}td.said{width:62%}.cite{color:#2c4a6b;font-size:11px;margin-top:3px}.ref{color:#4b4b4b;font-size:11px;margin-top:3px}
.q{font-style:italic;margin-bottom:2px}.decision{background:#f7f7ef}.super{color:#777}footer{margin-top:24px;font-size:11px;color:#444}
@media print{body{margin:10mm}tr{page-break-inside:avoid}}"""


def export_html(sid, allowed=None) -> str:
    """Printable page: attendance, then per Case File the agent log beside the board's decision and marks. Inline CSS, no scripts."""
    x = export(sid, allowed)
    se = x["session"]
    title = f"Board session {_ddmmyyyy(se['date'])}: agent log and board decision"
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_h(title)}</title><style>{CSS}</style></head><body>",
           f"<h1>{_h(title)}</h1>"]
    status = {"planned": "Planned", "in_session": "In session", "closed": "Closed"}.get(se.get("status"), se.get("status"))
    info = [f"Session {se['id']}"] + ([se["title"]] if se.get("title") else []) + [f"Status: {status}"]
    if se.get("started_at"):
        info.append(f"Started {_ddmmyyyy(se['started_at'])}")
    if se.get("closed_at"):
        info.append(f"Closed {_ddmmyyyy(se['closed_at'])}")
    out.append(f"<div class='meta'>{_h(' | '.join(info))}</div>")
    out.append("<h2>Attendance</h2><table><tr><th>Department</th><th>Attendance</th><th>Members present</th></tr>")
    att_label = {"present": "Present", "absent": "Absent", "not_marked": "Not marked"}
    for a in x["attendance"]:
        out.append(f"<tr><td>{_h(a['name'])}</td><td>{_h(att_label.get(a['status'], a['status']))}</td><td>{_h(', '.join(a['members']))}</td></tr>")
    out.append("</table>")
    if x["absent_roles"]:
        out.append(f"<div class='meta'>AI support agents prepared briefs for the absent specialties: {_h(', '.join(org.department_name(ROLE_DEPARTMENT[r]) for r in x['absent_roles']))}</div>")
    models = []
    for c in x["cases"]:
        if c.get("restricted"):
            out.append(f"<h2>{_h(c['case_id'])}: restricted</h2><div class='meta'>Another department's Case File: its agent log and decision are not shown to your department.</div>"); continue
        p = c["patient"]
        ident = ", ".join(v for v in (p.get("name"), (f"UHID/MRN {p.get('mrn') or p.get('uhid')}" if p.get("mrn") or p.get("uhid") else ""),
                                       p.get("agesex"), c.get("protocol")) if v)
        out.append(f"<h2>{_h(c['case_id'])}: {_h(ident)}</h2>")
        out.append("<table><tr><th>What the AI support agents said (role-specific, AI draft)</th><th>What the board decided</th></tr>")
        d = c["decision"]
        dec = (f"<b>Board decision</b><div>{_h(d.get('decision_text'))}</div><div class='meta'>Record {_h(d.get('board_record'))}"
               f"{', recorded by ' + _h(d['recorded_by']) if d.get('recorded_by') else ''}"
               f"{', ' + _h(_ddmmyyyy(d['recorded_at'])) if d.get('recorded_at') else ''}"
               f"{', amended: version ' + _h(d['version']) + ' (' + _h(_ddmmyyyy(d.get('amended_at'))) + ')' if (d.get('version') or 1) > 1 else ''}</div>") if d else "<i>No board decision linked yet</i>"
        m = c["marks"]
        out.append(f"<tr class='decision'><td class='said'><span class='meta'>{len(c['agent_log'])} agent log entries. Discussed {m['discussed']}, "
                   f"accepted {m['accepted']}, not relevant {m['not_relevant']}, not marked {m['unmarked']}.</span></td><td>{dec}</td></tr>")
        if not c["agent_log"]:
            out.append("<tr><td class='said'><i>No agent points logged</i></td><td></td></tr>")
        for e in c["agent_log"]:
            if _uses_model(e) and model_words(e.get("model")) not in models:
                models.append(model_words(e.get("model")))
            out.append(f"<tr{' class=super' if e.get('superseded') else ''}><td class='said'>{_said(e)}</td><td>{_decided(e)}</td></tr>")
        out.append("</table>")
    out.append(f"<footer><p>{_h(x['note'])}</p>"
               + (f"<p>AI support agents' model: {_h(', '.join(models))}</p>" if models else "")
               + f"<p>Exported {_h(_ddmmyyyy(store.now_iso()))}</p></footer></body></html>")
    return "".join(out)  # em dashes are replaced in _h; verified quotes (_verbatim) stay exactly as stored
