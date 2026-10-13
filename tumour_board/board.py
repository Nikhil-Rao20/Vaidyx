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

ROLE_DEPARTMENT = {"radiology": "radiology", "pathology": "pathology", "medical_oncology": "medical_oncology",
                   "surgical_oncology": "surgical_oncology", "radiation_oncology": "radiation_oncology", "nuclear_medicine": "nuclear_medicine"}
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
    """Org departments that attend the board (the MDT Coordinator is a role, not a department), with the agent role that speaks for each."""
    roles = {d: r for r, d in ROLE_DEPARTMENT.items()}
    return [{"id": d["id"], "name": d.get("name") or d["id"], "group": d.get("group"), "role": roles.get(d["id"])}
            for d in org.departments() if d.get("id")]


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
    if case_ids is None:
        ids = [c["case_id"] for c in listed_for_date(date)]
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


def absent_roles(session) -> list[str]:
    att = attendance(session)
    return [r for r, d in ROLE_DEPARTMENT.items() if att.get(d) == "absent"]


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


def export(sid) -> dict:
    s = _need(sid)
    names = {d["id"]: d["name"] for d in specialties()}
    att = attendance(s)
    members = s.get("members") or []
    attendance_rows = [{"department": d, "name": names.get(d) or org.department_name(d), "status": v,
                        "members": [m["name"] for m in members if org.department_id(m["department"]) == d]} for d, v in att.items()]
    cases = []
    for a in s["agenda"]:
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


def _verbatim(x) -> str:
    """A verified quote (citation or guideline reference): escaped, otherwise exactly as stored."""
    return html.escape(str(x if x is not None else ""), quote=True)


def _h(x) -> str:
    """Any other text: escaped, an em dash printed as '-' (no em dashes in reports)."""
    return _verbatim(str(x if x is not None else "").replace("\u2014", "-"))


def model_words(label) -> str:
    """How a model is named in a report: always with "(non-medical)" (CLAUDE.md model labels)."""
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


def export_html(sid) -> str:
    """Printable page: attendance, then per Case File the agent log beside the board's decision and marks. Inline CSS, no scripts."""
    x = export(sid)
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
