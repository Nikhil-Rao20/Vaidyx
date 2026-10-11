"""Tumour Board sessions: the board meeting itself (V1 items 6.1 and 6.3).

V1 item 6.1: a board session is created for a date from the Case Files listed for that date (agenda order); each specialty is
marked present or absent and members present are recorded by name. The "Board room" screen works on one session: current
Case File, summary, active agents, decision entry.
V1 item 6.3: the session keeps every agent point (brief items, points for review, live answers). Once the board's decision is
recorded and linked, each point can be marked discussed / accepted / not relevant: "what the agent said vs what the board
decided". Reporting only; nothing here measures accuracy.

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

ROLE_DEPARTMENT = {"radiology": "radio_diagnosis", "pathology": "pathology", "medical_oncology": "medical_oncology",
                   "surgical_oncology": "surgical_oncology", "radiation_oncology": "radiation_oncology", "nuclear_medicine": "nuclear_medicine"}
MARKS = {"discussed": "Discussed", "accepted": "Accepted", "not_relevant": "Not relevant"}
STATUSES = ("planned", "in_session", "closed")
ATTENDANCE = ("present", "absent", "not_marked")
AGENT_STATUSES = ("queued", "running", "ready", "no_documents", "error")
KIND_LABELS = {"brief_item": "Brief item", "point_for_review": "Point for review", "no_documents": "No documents", "not_documented": "Not documented",
               "answer": "Answer to the board's question"}
NOTE = "Reporting only: what the AI support agents said and what the board decided. It does not measure accuracy."
MAX_NAME, MAX_TITLE, MAX_NOTE = 120, 200, 2000
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    """Org departments that attend the board (all but Tumour Board coordination), with the agent role that speaks for each."""
    roles = {d: r for r, d in ROLE_DEPARTMENT.items()}
    return [{"id": d["id"], "name": d.get("name") or d["id"], "role": roles.get(d["id"])}
            for d in org.departments() if d.get("id") and d.get("id") != "tumour_board"]


def _listed(case) -> bool:
    """Listed for the board: a protocol and listing status 'listed' (older Case Files without a listing record count as listed)."""
    return bool(case and case.get("protocol")) and (case.get("listing") or {"status": "listed"}).get("status") == "listed"


def listed_for_date(date: str) -> list[dict]:
    date = _check_date(date)
    rows = [c for c in store.list_cases() if c.get("case_id") not in config.PROTECTED_CASES and _listed(c) and c.get("board_date") == date]
    rows.sort(key=lambda c: ((c.get("listing") or {}).get("listed_at") or "", c["case_id"]))
    return [{"case_id": c["case_id"], "patient": c.get("patient") or {}, "protocol": c.get("protocol"), "setting": c.get("setting", ""),
             "board_date": c.get("board_date")} for c in rows]


def _check_cases(case_ids) -> list[str]:
    """Explicit agenda: order kept, duplicates dropped; each Case File must exist, be listed and not be protected."""
    if not isinstance(case_ids, (list, tuple)):
        raise ValueError("The agenda must be a list of Case File ids")
    out = []
    for cid in case_ids:
        cid = str(cid or "").strip()
        if cid in config.PROTECTED_CASES:  # checked before anything is read from it
            raise ValueError(f"Case File {cid} holds real patient data and cannot join a board session")
        try:
            store.safe_id(cid)
        except ValueError:
            raise ValueError(f"Invalid Case File id {cid!r}") from None
        c = store.get_case(cid)
        if not c:
            raise ValueError(f"Case File {cid} not found")
        if not _listed(c):
            raise ValueError(f"Case File {cid} is not listed for the board")
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
    ids = [c["case_id"] for c in listed_for_date(date)] if case_ids is None else _check_cases(case_ids)
    if not ids:
        raise ValueError(f"No Case File is listed for the board on {_ddmmyyyy(date)}")
    title = str(title or "").strip()
    if len(title) > MAX_TITLE:
        raise ValueError(f"Session title is too long (at most {MAX_TITLE} characters)")
    sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    while _path(sid).exists():
        sid = "S" + date.replace("-", "") + "-" + uuid.uuid4().hex[:4]
    now = store.now_iso()
    s = {"id": sid, "date": date, "title": title, "status": "planned", "created": now, "created_by": by or "",
         "started_at": None, "started_by": None, "closed_at": None, "closed_by": None, "current": None,
         "agenda": [{"case_id": c, "status": "waiting", "added_at": now, "added_by": by or ""} for c in ids],
         "attendance": {d["id"]: "not_marked" for d in specialties()}, "members": [],
         "agents": {}, "log": [], "decisions": {}}
    _save(s)
    _audit(sid, "created", by, date=date, cases=ids)
    for c in ids:
        _audit(sid, "agenda_added", by, c, "agenda_added", date=date)
    return s


def list_sessions() -> list[dict]:
    base = sessions_dir()
    rows = [s for s in (store._read_json(p) for p in base.glob("S*.json")) if s] if base.exists() else []
    rows.sort(key=lambda s: (s.get("date") or "", s.get("created") or ""), reverse=True)
    return [{"id": s["id"], "date": s.get("date"), "title": s.get("title", ""), "status": s.get("status"), "cases": len(s.get("agenda") or []),
             "created": s.get("created"), "created_by": s.get("created_by")} for s in rows]


def set_agenda(sid, case_ids, by) -> dict:
    s = _need(sid); _open(s)
    ids = _check_cases(case_ids)
    if not ids:
        raise ValueError("A board session needs at least one Case File")
    old = {a["case_id"]: a for a in s["agenda"]}
    now = store.now_iso()
    s["agenda"] = [old.get(c) or {"case_id": c, "status": "waiting", "added_at": now, "added_by": by or ""} for c in ids]
    if s.get("current") and s["current"] not in ids:  # the current Case File was removed: the next undecided one becomes current
        s["current"] = None
        if s["status"] == "in_session":
            nxt = next((a for a in s["agenda"] if a["status"] != "decided"), None)
            if nxt:
                nxt["status"], s["current"] = "current", nxt["case_id"]
    _save(s)
    _audit(sid, "agenda", by, cases=ids)
    for c in ids:
        if c not in old:
            _audit(sid, "agenda_added", by, c, "agenda_added")
    for c in old:
        if c not in ids:
            _audit(sid, "agenda_removed", by, c, "agenda_removed")
    return s


# ---- attendance (V1 item 6.1) -------------------------------------------------------------------------------------------

def _dept(dept_id, attending=True) -> str:
    """A department id from an id, name or alias; attending=True restricts it to the specialties."""
    did = org.department_id(str(dept_id or ""))
    if not did or (attending and did == "tumour_board"):
        raise ValueError(f"Unknown department {dept_id!r}")
    return did


def set_attendance(sid, dept_id, status, by) -> dict:
    s = _need(sid); _open(s)
    did = _dept(dept_id)
    if status not in ATTENDANCE:
        raise ValueError(f"Attendance must be one of: {', '.join(ATTENDANCE)}")
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
    if did != "tumour_board" and s["attendance"].get(did, "not_marked") == "not_marked":
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


def absent_roles(session) -> list[str]:
    att = (session or {}).get("attendance") or {}
    return [r for r, d in ROLE_DEPARTMENT.items() if att.get(d) == "absent"]


def participants(session) -> dict:
    """Who took part, for the decision record (7.1 checks the PM-JAY composition from it)."""
    att = session.get("attendance") or {}
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
    s["current"] = case_id
    _save(s)
    _audit(sid, "current", by, case_id, "current")
    return s


def close(sid, by) -> dict:
    s = _need(sid); _open(s)
    s["status"], s["closed_at"], s["closed_by"] = "closed", store.now_iso(), by or ""
    _save(s)
    _audit(sid, "closed", by)
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


