"""Meetings of the new interface (18 Oct, B3): the board sessions of board.py (sessions/<sid>.json) extended for the meeting screens.

A meeting is a session with a time, a room, video on or off, minutes per case, a 6-digit join code, three agenda lists (for
discussion, for noting, not ready: each entry with its order and reason; the old agenda[] follows discussion + noting so the old /tb
room, the minutes and the exports keep working), the people who joined (per user: waiting until the MDT Coordinator admits, then
present in the room or remote; a user with an open WebSocket is online), what the shared screen shows (the current Case File, its
slide, the record or the images opened, the timer per case), the questions typed by members (answered in text by the stand-in agent
of an absent head, from the records only), the raised hands, the live decision strip (broadcast, never saved), the decision per
Case File (recorded through postboard.record_decision like the old route, so adjudication and the board record keep working), the
end-of-case cards of the board heads (agree or concern, with a note) and the outcome sent to the owner.

Product rules: the AI checks, routes, summarises and flags; the stand-in agent answers from the records only, never counts for the
quorum and never decides; text only; every action audited (sessions/audit.jsonl and the Case File's audit.jsonl). Nothing here calls
a model except the stand-in answer, which goes through agents.ask (verified quotes, guardrails) in a background task.

Storage keys added to the session file: time, room, video, minutes_per_case, code {value, expires_at, attempts}, agenda_lists
{discussion[], noting[], not_ready[]} (entries {case_id, reason, minutes, added_at, added_by}), people {user: {name, department,
status, mode, joined_at}}, live {slide, opened, timer}, questions[], hands[], cards {case_id: {user: {agree, note, at}}},
outcomes {case_id: {...}}, ended {case_id: {...}}, agenda_sent_at, agenda_sent_cases[]. The live decision and the agent state live in
memory only. All functions are synchronous read-modify-write (except the two that await the PACS lookup and the decision record):
call them from the app's event loop, never from threads (the scheduler calls expire_codes / notify_starting, which touch no case).
"""
import asyncio, logging, secrets, time, uuid
from datetime import date, datetime, timedelta

from . import access, after_send, board, config, dept_requests, discord, his_client, live, notify, org, pacs, postboard, protocol, rules, store

log = logging.getLogger(__name__)

OUTCOMES = {"decision": "Decision recorded", "deferred": "Deferred: information awaited", "referred": "Referred to another board or centre",
            "not_discussed": "Not discussed: moved to the next meeting", "noted": "Noted for information"}
LISTS = board.MEETING_LISTS
STATUSES = ("planned", "in_session", "closed", "cancelled")
ADMITTED = ("present", "remote")
MODES = ("room", "remote")
CODE_TTL_HOURS = 12
MAX_QUESTION, MAX_NOTE, MAX_TEXT, MAX_ROOM = 1000, 2000, 4000, 80
AGENT_STATES = ("ready", "reading_question", "thinking", "answering")
IMAGING_TYPES = ("ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan")
PATHOLOGY_TYPES = ("histopathology", "cytology", "ihc", "molecular")
AUTOMATIC = "Vaidyx (automatic)"

LIVE_DECISION: dict[str, dict] = {}  # mid -> {text, by, at, case_id}: what the coordinator types, shown "not saved" on the room screen
AGENT_STATE: dict[str, dict] = {}    # mid -> {state, role, question}: the stand-in agent's true state while it answers
_TASKS: set = set()                  # background answers (kept referenced until done)
_ANSWERING: set = set()              # (mid, question id) being answered now


class MeetingError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers, `code` what the interface can act on."""

    def __init__(self, message, status=400, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


# ---- helpers -----------------------------------------------------------------------------------------------------------------

def _now() -> str:
    return store.now_iso()


def _dmy(iso) -> str:
    return board._ddmmyyyy(iso)


def _defaults() -> dict:
    """The coordinator's meeting defaults from the hospital settings (org.json meeting_defaults)."""
    base = {"weekday": None, "time": "", "room": "", "minutes_per_case": 10}
    base.update(getattr(org, "DEFAULT_MEETING", {}) or {})
    md = org.hospital().get("meeting_defaults")
    if isinstance(md, dict):
        base.update({k: v for k, v in md.items() if v not in (None, "")})
    return base


def _check_time(t) -> str:
    t = str(t or "").strip()
    if not t:
        return ""
    try:
        return datetime.strptime(t, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise MeetingError("The time must be HH:MM (24-hour clock).", 400, "bad_time")


def _check_minutes(m):
    if m in (None, ""):
        return None
    try:
        n = int(m)
    except (TypeError, ValueError):
        raise MeetingError("Minutes per case must be a whole number.", 400, "bad_minutes")
    if not 1 <= n <= 120:
        raise MeetingError("Minutes per case must be between 1 and 120.", 400, "bad_minutes")
    return n


def _iso_date(s) -> str:
    """YYYY-MM-DD or DD/MM/YYYY -> ISO; anything else is dropped ('')."""
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _profiles() -> dict:
    try:
        p = config.DATA_ROOT / "profiles.json"
        d = store._read_json(p, {}) if p.exists() else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def display_name(user: str) -> str:
    """The person's name: the profile store (new interface), else org.json, else the login."""
    prof = _profiles().get(str(user or ""))
    name = str(prof.get("display_name") or "").strip() if isinstance(prof, dict) else ""
    return name or org.display_name(user)


def user_department(user: str) -> str:
    """The department a person speaks for in a meeting: the first treating placement, else the first placement of any group."""
    r = org.roles(user)
    for key in ("treating", "supporting", "departments"):
        d = r.get(key) or {}
        if d:
            return next(iter(d))
    return ""


def get(mid: str) -> dict | None:
    try:
        s = board.get(mid)
    except ValueError:
        return None
    return board.ensure_meeting_fields(s) if s else None


def need(mid: str) -> dict:
    s = get(mid)
    if not s:
        raise MeetingError("Meeting not found.", 404, "not_found")
    return s


def _active(s) -> None:
    if s.get("status") in ("closed", "cancelled"):
        raise MeetingError("This meeting is over.", 409, "meeting_over")


def _in_session(s) -> None:
    if s.get("status") != "in_session":
        raise MeetingError("Start the meeting first.", 409, "not_in_session")


def _save(s) -> dict:
    return board.save_session(s)


PRIVATE_EVENTS = ("open", "question", "decision_live", "decision", "card")  # live content: for the admitted members and the coordinator only


def _shape(s: dict):
    """Per socket: a member (admitted, or whoever manages the meeting) gets the event as it is; any other viewer (waiting, or a
    department on the attendance sheet that did not join) gets none of the live content: no private event, no opened record."""
    admitted = {u for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED}

    def shape(user, info, ev):
        if user in admitted or (isinstance(info, dict) and manage(info)):
            return ev
        if ev.get("type") in PRIVATE_EVENTS:
            return None
        return {**ev, "opened": None} if "opened" in ev else ev
    return shape


def _send(s: dict, event: dict) -> bool:
    """Broadcast a change of this meeting to its sockets (live.broadcast with the per-socket shape)."""
    return live.broadcast(s["id"], event, shape=_shape(s))


def _meeting_datetime(s) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{s.get('date')}T{s.get('time') or '00:00'}:00")
    except (TypeError, ValueError):
        return None


# ---- who may do what -----------------------------------------------------------------------------------------------------------

def manage(r: dict) -> bool:
    """The MDT Coordinator runs meetings: org action "session" (never the Vaidyx admin, security review #2)."""
    return org.can(r, "session")


def may_view(r: dict, s: dict) -> bool:
    """Who may open the meeting page and its WebSocket: whoever manages it, whoever joined with the code (waiting included, so the
    waiting room is told when it is admitted), and whoever may open the old board room (attendance sheet, a Case File on the agenda)."""
    if not isinstance(r, dict) or r.get("disabled"):
        return False
    if manage(r):
        return True
    if r.get("user") and r["user"] in (s.get("people") or {}):
        return True
    try:
        return board.may_open(r, s)
    except Exception:
        return False


def is_member(r: dict, s: dict) -> bool:
    """A member of the meeting: admitted by the coordinator (present in the room or remote), or the coordinator / admin."""
    if not isinstance(r, dict) or r.get("disabled"):
        return False
    if manage(r):
        return True
    p = (s.get("people") or {}).get(r.get("user") or "")
    return bool(p) and p.get("status") in ADMITTED


def presenter_of(case: dict) -> str:
    """The presenter's login: the one chosen when the Case File was sent to the board (case.json "presenter", {user, name, set_by, at}
    from night-v3 item 1.4; a plain login before), else the team's owner."""
    team = case.get("team") if isinstance(case.get("team"), dict) else {}
    p = case.get("presenter")
    if isinstance(p, dict):
        p = p.get("user")
    return str(p or team.get("owner") or "")


def chosen_presenter(case: dict) -> dict | None:
    """{user, name} when a presenter was chosen for this Case File (sending it to the board), else None (the owner presents)."""
    p = case.get("presenter")
    u = str((p.get("user") if isinstance(p, dict) else p) or "")
    return {"user": u, "name": display_name(u)} if u else None


def owner_user(case: dict) -> str:
    team = case.get("team") if isinstance(case.get("team"), dict) else {}
    return str(team.get("owner") or "")


def in_owner_team(r: dict, case: dict) -> bool:
    """The owner's team of a Case File: the owning department's doctors (access.is_owner_doctor), the team's owner and residents."""
    if not isinstance(r, dict) or not isinstance(case, dict):
        return False
    if access.is_owner_doctor(r, case):
        return True
    team = case.get("team") if isinstance(case.get("team"), dict) else {}
    u = r.get("user") or ""
    if u and u == team.get("owner"):
        return True
    return any(isinstance(x, dict) and x.get("user") == u for x in team.get("residents") or [])


def card_holders(s: dict) -> list[str]:
    """Who owes a card at the end of each case: for every board head department, its admitted people placed as "head"; when none of
    them is admitted, the admitted members of that department speak for it (a delegate). Sorted logins."""
    heads = set(board.head_ids())
    by_dept: dict[str, list[tuple[str, str]]] = {}
    for u, p in (s.get("people") or {}).items():
        did = p.get("department") or ""
        if p.get("status") not in ADMITTED or did not in heads or p.get("outside_expert"):
            continue
        placement = (org.roles(u).get("departments") or {}).get(did) or ""
        by_dept.setdefault(did, []).append((u, placement))
    out = []
    for people in by_dept.values():
        chiefs = [u for u, pl in people if pl == "head"]
        out += chiefs or [u for u, _ in people]
    return sorted(out)


# ---- rows and views --------------------------------------------------------------------------------------------------------------

def _initials_line(case: dict) -> str:
    p = case.get("patient") or {}
    initials = "".join(w[0] for w in str(p.get("name") or "").replace(",", " ").split() if w)[:3].upper()
    return ", ".join(x for x in ((initials + "." if initials else "Patient"), p.get("agesex")) if x)


def patient_line(case: dict, r: dict | None = None, restricted: bool = False) -> str:
    """Name, age / sex and UHID; initials, age and sex only for an outside expert without the owner's consent for outside discussion,
    and for a viewer who is not admitted to the meeting and may not read that Case File in full (restricted)."""
    p = case.get("patient") or {}
    if restricted or (r and r.get("outside_expert") and not (case.get("consent") or {}).get("outside_discussion")):
        return _initials_line(case)
    return ", ".join(x for x in (p.get("name"), p.get("agesex"), f"UHID {p['mrn']}" if p.get("mrn") else "") if x)


def _board_question(case: dict, st: dict | None = None) -> str:
    """The question for the board: as the treating doctor typed it on its line (case.json typed_values {fact: {value, ...}}, slots.py), else
    the verified value the gate rests on (a quote from a note), else "". (18 Oct, e2e: typed_values was read as a list, so a typed
    question never reached the agenda.)"""
    q = case.get("board_question")
    if isinstance(q, dict):
        q = q.get("text") or q.get("value")
    if q:
        return str(q)
    typed = case.get("typed_values")
    if isinstance(typed, dict):
        for k in ("clinical_question", "board_question"):
            v = typed.get(k)
            if isinstance(v, dict) and str(v.get("value") or "").strip():
                return str(v["value"])
    elif isinstance(typed, list):  # an older shape: [{id, value}]
        for v in typed:
            if isinstance(v, dict) and v.get("id") in ("clinical_question", "board_question") and v.get("value"):
                return str(v["value"])
    for r in ((st or {}).get("gate") or {}).get("requirements") or []:
        for e in (r.get("evidence") or []) if isinstance(r, dict) else []:
            if isinstance(e, dict) and e.get("fact") == "clinical_question" and str(e.get("value") or "").strip():
                return str(e["value"])
    return ""


def _left_of(cid, st: dict):
    """The one count of what is left before the board (steps.open_count, 21 Oct); the gate's own count only when that cannot be built."""
    from . import steps
    n = steps.open_count(cid)
    return n if n is not None else _left(st)


def _left(st: dict):
    g = st.get("gate") or {}
    if g.get("total") is None:
        return None
    return max(0, int(g.get("total") or 0) - int(g.get("satisfied") or 0))


def _minutes_for(s, it) -> int:
    try:
        return int(it.get("minutes") or s.get("minutes_per_case") or _defaults().get("minutes_per_case") or 10)
    except (TypeError, ValueError):
        return 10


def full_cases(r: dict, s: dict) -> set | None:
    """The Case Files on the meeting's lists this viewer may read in full; None for whoever manages the meeting (everything)."""
    if manage(r):
        return None
    out = set()
    for k in LISTS:
        for it in (s.get("agenda_lists") or {}).get(k) or []:
            cid = it.get("case_id")
            c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
            try:
                if c and access.scope(r, c) == access.FULL:
                    out.add(cid)
            except Exception:
                continue
    return out


def row(s: dict, it: dict, order: int, r: dict | None = None, restricted: bool = False) -> dict:
    """One agenda row for the meeting screens. Restricted (a viewer not admitted who may not read this Case File in full): initials, age
    and sex, no board question."""
    cid = it.get("case_id")
    c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
    if not c:
        return {"case_id": cid, "missing": True, "order": order, "reason": it.get("reason") or "", "patient_line": "", "owner_name": "", "presenter_name": "",
                "board_question": "", "left_before_board": None, "minutes": _minutes_for(s, it)}
    st = store.get_state(cid)
    own = access.owner(c)
    ou = owner_user(c)
    pres = presenter_of(c)
    item = next((a for a in s.get("agenda") or [] if a.get("case_id") == cid), None)
    oc = (s.get("outcomes") or {}).get(cid) or {}
    urg = c.get("urgency") if isinstance(c.get("urgency"), dict) else {}
    return {"case_id": cid, "patient_line": patient_line(c, r, restricted), "protocol": c.get("protocol"), "restricted": bool(restricted),
            "owner_name": display_name(ou) if ou else (org.department_name(own) if own else ""), "owner_department": own or "",
            "owner_department_name": org.department_name(own) if own else "", "presenter_name": display_name(pres) if pres else "",
            "board_question": "" if restricted else _board_question(c, st), "left_before_board": _left_of(cid, st), "minutes": _minutes_for(s, it), "order": order,
            "reason": it.get("reason") or "", "ready": bool(c.get("board_ready")), "status": (item or {}).get("status") or "waiting",
            "ended": cid in (s.get("ended") or {}), "outcome": oc.get("outcome"), "outcome_label": OUTCOMES.get(oc.get("outcome") or "", ""),
            "added_after_send": bool(s.get("agenda_sent_at")) and cid not in (s.get("agenda_sent_cases") or []), "urgency": urg.get("level"),
            "presenter": chosen_presenter(c), "waiting_on": after_send.waiting_on(c), "new_since_sent": after_send.new_since_sent(cid, c)}  # night-v3 item 1.5


def counts(s: dict) -> dict:
    lists = s.get("agenda_lists") or {}
    return {k: len(lists.get(k) or []) for k in LISTS}


def summary_row(s: dict) -> dict:
    return {"id": s["id"], "date": s.get("date"), "time": s.get("time") or "", "room": s.get("room") or "", "status": s.get("status"),
            "video": bool(s.get("video")), "minutes_per_case": s.get("minutes_per_case"), "counts": counts(s), "agenda_sent_at": s.get("agenda_sent_at"),
            "title": s.get("title") or "", "created_by": s.get("created_by"), "started_at": s.get("started_at"), "closed_at": s.get("closed_at"),
            "cancelled": s.get("cancelled"), "current": s.get("current"), "people": len(s.get("people") or {}),
            "label": f"Tumour Board {_dmy(s.get('date'))}" + (f" {s['time']}" if s.get("time") else "")}


def _timer_left(t: dict, now_ts: float | None = None) -> int:
    now_ts = time.time() if now_ts is None else now_ts
    left = int(t.get("left") or 0)
    if t.get("running") and t.get("started_at"):
        left -= int(now_ts - float(t["started_at"]))
    return max(0, left)


def timer_view(t) -> dict | None:
    if not isinstance(t, dict):
        return None
    return {"seconds_left": _timer_left(t), "running": bool(t.get("running")), "total": int(t.get("total") or 0)}


def current_view(s: dict) -> dict:
    lv = s.get("live") or {}
    return {"case_id": s.get("current"), "slide": int(lv.get("slide") or 0), "opened": lv.get("opened"), "timer": timer_view(lv.get("timer"))}


def attendance_rows(s: dict) -> list[dict]:
    online = set(live.online(s["id"]))
    heads = set(board.head_ids())
    holders = set(card_holders(s))
    out = []
    for u, p in (s.get("people") or {}).items():
        did = p.get("department") or ""
        out.append({"user": u, "name": p.get("name") or display_name(u), "department": did, "department_name": org.department_name(did) if did else "",
                    "status": p.get("status"), "mode": p.get("mode"), "joined_at": p.get("joined_at"), "online": u in online, "head": did in heads,
                    "card_holder": u in holders, "outside_expert": bool(p.get("outside_expert"))})
    out.sort(key=lambda x: ({"present": 0, "remote": 1, "waiting": 2, "absent": 3}.get(x["status"], 4), x["name"]))
    return out


def agent_state(s: dict) -> dict:
    """The stand-in agent tile: active only when a board head is not present for the Case File on the floor (board.absent_roles), with
    its true state (ready, reading the question, thinking, answering). Never a member, never a vote."""
    off = {"active": False, "role": None, "label": "", "state": "off", "roles": [], "question": None}
    cur = s.get("current")
    if s.get("status") != "in_session" or not cur or cur in config.PROTECTED_CASES:
        return off
    try:
        roles = board.absent_roles(s, cur)
    except Exception:
        roles = []
    head_roles = [x for x in roles if board.ROLE_DEPARTMENT.get(x) in set(board.head_ids())]
    if not head_roles:
        return {**off, "roles": roles}
    role = head_roles[0]
    st = AGENT_STATE.get(s["id"]) or {}
    try:
        from . import agents
        label = agents.spec(role)["label"]
    except Exception:
        label = org.department_name(board.ROLE_DEPARTMENT.get(role, role))
    return {"active": True, "role": role, "label": label, "state": st.get("state") or "ready", "roles": head_roles, "question": st.get("question"),
            "note": "AI support: answers from the records only; not a member of the board"}


def view(mid: str, r: dict) -> dict:
    """The GET /meetings/{mid} payload (also the first WebSocket message). A viewer who is not admitted (waiting, or a department on the
    attendance sheet that did not join) sees the agenda with initials for the Case Files it may not read in full, and none of the live
    content (the record or images opened, the questions, the live decision); the decision text of an outcome only for the Case Files
    it may read in full (as in the old room, Phase 6 review S2)."""
    s = need(mid)
    lists = s.get("agenda_lists") or {}
    member = is_member(r, s)
    full = full_cases(r, s)
    agenda = {k: [row(s, it, i + 1, r, restricted=not member and full is not None and it.get("case_id") not in full) for i, it in enumerate(lists.get(k) or [])]
              for k in LISTS}
    user = r.get("user") or ""
    me = (s.get("people") or {}).get(user) or {}
    cur = s.get("current")
    code = s.get("code") if manage(r) and isinstance(s.get("code"), dict) else None
    dl = LIVE_DECISION.get(mid) or {"text": "", "by": "", "at": None, "case_id": None}
    cards = {cid: sorted(v.keys()) for cid, v in (s.get("cards") or {}).items() if isinstance(v, dict)}
    cv = current_view(s)
    outcomes = {cid: (oc if full is None or cid in full else {k: v for k, v in oc.items() if k in ("outcome", "label", "at", "moved_to", "flagged")})
                for cid, oc in (s.get("outcomes") or {}).items() if isinstance(oc, dict)}
    if not member:
        cv = {**cv, "opened": None}
        dl = {"text": "", "by": "", "at": None, "case_id": None}
    return {"meeting": summary_row(s), "agenda": agenda,
            "code": {"value": code["value"], "expires_at": code.get("expires_at"), "attempts": code.get("attempts", 0)} if code else None,
            "attendance": attendance_rows(s), "current": cv, "decision_live": dl, "questions": list(s.get("questions") or []) if member else [],
            "hands": list(s.get("hands") or []), "agent": agent_state(s),
            "can": {"manage": manage(r), "record": org.can(r, "board_record"), "ask": member and bool(cur),
                    "card": member and bool(cur), "card_required": user in card_holders(s),
                    "video": bool(s.get("video")) and member, "member": member},
            "me": {"user": user, "status": me.get("status"), "mode": me.get("mode"), "department": me.get("department") or ""},
            "online": live.online(mid), "outcomes": outcomes, "ended": sorted((s.get("ended") or {}).keys()), "cards_given": cards,
            "heads": board.heads(), "absent_roles": board.absent_roles(s, cur) if cur else [], "status": s.get("status")}


# ---- create, update, list ------------------------------------------------------------------------------------------------------------

def create(by: str, date_: str, time_: str = "", room=None, video: bool = False, minutes_per_case=None, title: str = "") -> dict:
    """The MDT Coordinator creates a meeting by hand (date, time, room, video on or off; no cut-off). Defaults from the hospital settings."""
    d = _defaults()
    try:
        s = board.new_session(date_, by, title, time=_check_time(time_ or d.get("time") or ""), room=str(d.get("room") if room is None else room or "").strip()[:MAX_ROOM],
                              video=bool(video), minutes_per_case=_check_minutes(minutes_per_case) or int(d.get("minutes_per_case") or 10))
    except ValueError as e:
        raise MeetingError(str(e), 400, "bad_date")
    return s


def update(mid: str, by: str, fields: dict) -> dict:
    s = need(mid); _active(s)
    changed = {}
    if "date" in fields and fields["date"] is not None:
        if s.get("status") != "planned":
            raise MeetingError("The date of a meeting in session cannot change.", 409, "in_session")
        try:
            new = board._check_date(fields["date"])
        except ValueError as e:
            raise MeetingError(str(e), 400, "bad_date")
        if new != s.get("date"):
            s["date"] = changed["date"] = new
    if "time" in fields and fields["time"] is not None:
        new = _check_time(fields["time"])
        if new != (s.get("time") or ""):
            s["time"] = changed["time"] = new
    if "room" in fields and fields["room"] is not None:
        new = str(fields["room"] or "").strip()[:MAX_ROOM]
        if new != (s.get("room") or ""):
            s["room"] = changed["room"] = new
    if "video" in fields and fields["video"] is not None:
        new = bool(fields["video"])
        if new != bool(s.get("video")):
            s["video"] = changed["video"] = new
    if "minutes_per_case" in fields and fields["minutes_per_case"] is not None:
        new = _check_minutes(fields["minutes_per_case"])
        if new != s.get("minutes_per_case"):
            s["minutes_per_case"] = changed["minutes_per_case"] = new
    if "title" in fields and fields["title"] is not None:
        new = str(fields["title"] or "").strip()[:board.MAX_TITLE]
        if new != (s.get("title") or ""):
            s["title"] = changed["title"] = new
    if changed:
        _save(s)
        board.audit_event(mid, "meeting_updated", by, **changed)
        _send(s, {"type": "meeting", "meeting": summary_row(s)})
    return s


def cancel(mid: str, by: str, reason: str = "") -> dict:
    s = need(mid)
    if s.get("status") != "planned":
        raise MeetingError("Only a planned meeting can be cancelled.", 409, "not_planned")
    reason = " ".join(str(reason or "").split())[:MAX_NOTE]
    s["status"] = "cancelled"
    s["cancelled"] = {"by": by, "at": _now(), "reason": reason}
    s["code"] = None
    _save(s)
    board.audit_event(mid, "meeting_cancelled", by, reason=reason)
    title = f"Tumour Board on {_dmy(s.get('date'))}" + (f" {s['time']}" if s.get("time") else "") + " cancelled"
    for did in _member_departments(s):
        try:
            notify.notify({"department": did}, "agenda", "", title, (f"Cancelled by the MDT Coordinator: {reason}" if reason else "Cancelled by the MDT Coordinator."), meeting_id=mid)
        except Exception as e:
            log.warning("meeting %s: cancel notice to %s failed (%s)", mid, did, e)
    _send(s, {"type": "ended", "cancelled": True})
    return s


def list_meetings(r: dict) -> dict:
    rows = []
    for s in board.all_sessions():
        board.ensure_meeting_fields(s)
        if manage(r) or may_view(r, s):
            rows.append(summary_row(s))
    return {"meetings": rows, "can_manage": manage(r)}


def open_meetings(today: str | None = None) -> list[dict]:
    """The meetings a Case File may still be sent to (night-v3 item 1.4): planned, not cancelled, dated today or later, earliest first
    (the website's New Case File and Send to the board pick the same way)."""
    today = today or date.today().isoformat()
    return [s for s in board.planned_sessions() if not s.get("cancelled") and str(s.get("date") or "") >= today]


# ---- agenda ---------------------------------------------------------------------------------------------------------------------------

def _entry(old: dict, cid: str, by: str, reason=None) -> dict:
    o = old.get(cid) or {}
    return {"case_id": cid, "reason": (o.get("reason") or "") if reason is None else reason, "minutes": o.get("minutes"),
            "added_at": o.get("added_at") or _now(), "added_by": o.get("added_by") or by}


def _check(ids, listed=True, keep=()) -> list[str]:
    try:
        return board._check_cases(list(ids or []), listed=listed, keep=keep)
    except ValueError as e:
        raise MeetingError(str(e), 409 if "archived" in str(e) else 400, "archived" if "archived" in str(e) else "bad_case")


def _after_agenda_change(s, by, kind, **extra):
    board.sync_agenda_lists(s, by)
    _save(s)
    board.audit_event(s["id"], kind, by, **counts(s), **extra)
    for k in ("discussion", "noting"):  # the Case Files on the agenda remember their meeting and board date
        for it in (s.get("agenda_lists") or {}).get(k) or []:
            _link_case(it.get("case_id"), s, by)
    _send(s, {"type": "agenda", "counts": counts(s)})


def _link_case(cid, s, by) -> None:
    if not cid or cid in config.PROTECTED_CASES:
        return
    c = store.get_case(cid)
    if not c or access.is_archived(c):  # nothing changes in an archived Case File (security review #8)
        return
    changed = {}
    if c.get("meeting_id") != s["id"]:
        c["meeting_id"] = changed["meeting_id"] = s["id"]
    if s.get("date") and c.get("board_date") != s.get("date"):
        changed["board_date_before"] = c.get("board_date")
        c["board_date"] = changed["board_date"] = s["date"]
    if changed:
        store.save_case(c)
        store.audit(cid, {"kind": "meeting_listed", "by": by, "session": s["id"], **changed})


def set_agenda(mid: str, by: str, discussion, noting, not_ready=None) -> dict:
    """The lists in the coordinator's order (drag); a Case File in both goes to discussion; the not-ready list is kept unless given."""
    s = need(mid); _active(s)
    lists = s.get("agenda_lists") or {}
    old = {it["case_id"]: it for k in LISTS for it in lists.get(k) or [] if it.get("case_id")}
    disc = _check(discussion, keep=set(old))
    note = [c for c in _check(noting, keep=set(old)) if c not in disc]
    if not_ready is None:
        nr = [it["case_id"] for it in lists.get("not_ready") or [] if it.get("case_id") and it["case_id"] not in disc + note]
    else:
        nr = [c for c in _check(not_ready, listed=False, keep=set(old)) if c not in disc + note]
    listed_before = {it["case_id"] for k in ("discussion", "noting") for it in lists.get(k) or [] if it.get("case_id")}
    s["agenda_lists"] = {"discussion": [_entry(old, c, by) for c in disc], "noting": [_entry(old, c, by) for c in note], "not_ready": [_entry(old, c, by) for c in nr]}
    _after_agenda_change(s, by, "agenda_lists")
    for cid in disc + note:  # newly on this meeting's discussion or noting list: one planned agenda only, a withdraw cleared
        if cid not in listed_before:
            _one_agenda(cid, s, by)
    return s


def add_to_agenda(mid: str, by: str, case_id: str, lst: str, reason: str = "", *, one_agenda: bool = True) -> dict:
    """The coordinator puts a Case File on one of this meeting's lists. On the discussion or noting list it sits on this planned agenda
    only and a withdraw recorded earlier is cleared (_one_agenda); `one_agenda=False` for move_case and board.send_to_board, which take
    it off the other agendas themselves (audited "moved" or "sent") and write board_send themselves."""
    s = need(mid); _active(s)
    if lst not in LISTS:
        raise MeetingError(f"The list must be one of: {', '.join(LISTS)}.", 400, "bad_list")
    reason = " ".join(str(reason or "").split())[:MAX_NOTE]
    if lst == "not_ready" and not reason:
        raise MeetingError("Say why the Case File is not ready.", 400, "reason_needed")
    lists = s.get("agenda_lists") or {}
    old = {it["case_id"]: it for k in LISTS for it in lists.get(k) or [] if it.get("case_id")}
    cid = _check([case_id], listed=(lst != "not_ready"), keep=set(old))[0]
    for k in LISTS:
        lists[k] = [it for it in lists.get(k) or [] if it.get("case_id") != cid]
    lists.setdefault(lst, []).append(_entry(old, cid, by, reason))
    s["agenda_lists"] = lists
    _after_agenda_change(s, by, "agenda_added_to_list", case_id=cid, list=lst, reason=reason)
    if one_agenda and lst in ("discussion", "noting"):
        _one_agenda(cid, s, by)
    return s


def _one_agenda(cid: str, s: dict, by: str) -> None:
    """The coordinator put a Case File on meeting `s`'s discussion or noting list (night-v3 item 1.6, review fix): it leaves every other
    planned meeting's lists (take_off_agendas, audited why="coordinator") and a withdraw recorded on it is cleared (the history keeps the
    withdraw and gets a line for the put back), so it counts as sent again (after_send.is_sent) and the chip no longer says Taken off.
    Nothing changes in a protected or archived Case File."""
    if not cid or cid in config.PROTECTED_CASES:
        return
    c = store.get_case(cid)
    if not c or access.is_archived(c):
        return
    take_off_agendas(cid, by, keep=s["id"], why="coordinator")
    c = store.get_case(cid) or c
    send = c.get("board_send") if isinstance(c.get("board_send"), dict) else None
    if not (send and send.get("withdrawn")):
        return
    send.pop("withdrawn", None)
    send["meeting_id"] = s["id"]
    c.setdefault("board_send_history", []).append({"put_back_on": s["id"], "by": by or "", "at": _now()})
    store.save_case(c)
    store.audit(cid, {"kind": "agenda_withdraw_cleared", "by": by or "", "meeting_id": s["id"]})


# ---- the owner moves or withdraws its Case File (night-v3 item 1.6, design B8) ---------------------------------------------------------

MIN_WITHDRAW_REASON, MAX_WITHDRAW_REASON = 3, 500


def take_off_agendas(case_id: str, by: str, keep: str = "", **extra) -> list[str]:
    """Take a Case File off every list of every planned meeting except `keep` (a Case File sits on one agenda only). Each meeting left
    is synced (the old agenda[] follows), saved, audited "agenda_removed_by_owner" (with `extra`: why, the reason, where it went) and
    told to its sockets. Returns the ids of the meetings it left. A meeting in session or closed is never touched."""
    left = []
    for s in board.planned_sessions():
        if s.get("id") == keep:
            continue
        board.ensure_meeting_fields(s)
        if not _on_lists(s, case_id):
            continue
        lists = s.get("agenda_lists") or {}
        for k in LISTS:
            lists[k] = [it for it in lists.get(k) or [] if it.get("case_id") != case_id]
        s["agenda_lists"] = lists
        board.sync_agenda_lists(s, by)
        _save(s)
        board.audit_event(s["id"], "agenda_removed_by_owner", by, case_id=case_id, **counts(s), **extra)
        _send(s, {"type": "agenda", "counts": counts(s)})
        left.append(s["id"])
    return left


def _sent_case(case_id: str) -> dict:
    """The Case File the owner moves or withdraws: it exists, is not protected or archived, was sent to the board (the ready mark) and
    its current meeting is not running or over."""
    if case_id in config.PROTECTED_CASES:
        raise MeetingError("That Case File is protected.", 400, "protected")
    c = store.get_case(case_id)
    if not c:
        raise MeetingError(f"Case File {case_id} not found.", 404, "not_found")
    if access.is_archived(c):
        raise MeetingError(access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", 409, "archived")
    if not (isinstance(c.get("board_ready"), dict) and c["board_ready"].get("at")):
        raise MeetingError("Send it to the board first.", 400, "not_sent")
    cur = get(c.get("meeting_id")) if c.get("meeting_id") else None
    if cur and cur.get("status") in ("in_session", "closed"):
        raise MeetingError("That meeting is not open.", 400, "not_open")
    return c


def _when(s: dict | None) -> str:
    return (_dmy(s.get("date")) + (f" {s['time']}" if s.get("time") else "")) if s else ""


def _tell_coordinator(c: dict, title: str, text: str, **extra) -> None:
    try:
        notify.notify({"role": "coordinator"}, "agenda", c["case_id"], title, text, **extra)
    except Exception as e:  # a notice never fails the change
        log.warning("agenda notice for %s failed (%s)", c.get("case_id"), e)


def move_case(case_id: str, user: str, to_meeting_id: str, reason: str = "") -> dict:
    """The owner (or the MDT Coordinator) moves a Case File sent to the board to another open meeting (planned, not cancelled, today
    or later, not the one it is on): it joins that meeting's list of the same kind (board_send list, for discussion by default) and
    leaves every other planned meeting's lists; the Case File follows (meeting_id, board_date, board_send meeting_id, the move kept in
    board_send_history); audited in the Case File (agenda_moved) and on both meetings; the coordinator is told. Returns the Case File."""
    c = _sent_case(case_id)
    reason = " ".join(str(reason or "").split())[:MAX_WITHDRAW_REASON]
    to = str(to_meeting_id or "").strip()
    if not to:
        raise MeetingError("Choose the meeting to move it to.", 400, "meeting_needed")
    s = get(to)
    if not s:
        raise MeetingError("Meeting not found.", 400, "not_found")
    if s.get("status") != "planned" or s.get("cancelled"):
        raise MeetingError("That meeting is not open.", 400, "not_open")
    if str(s.get("date") or "") < date.today().isoformat():
        raise MeetingError("That meeting date has passed: pick another meeting.", 400, "past")
    frm = str(c.get("meeting_id") or "")
    if to == frm:
        raise MeetingError("It is already on that meeting. Choose another meeting.", 400, "same_meeting")
    send = c.get("board_send") if isinstance(c.get("board_send"), dict) else {}
    lst = send.get("list") if send.get("list") in board.SEND_LISTS else "discussion"
    _check([case_id])  # listed, not archived: checked before anything moves
    old = get(frm) if frm else None
    add_to_agenda(to, user, case_id, lst, str(send.get("reason") or ""), one_agenda=False)  # links the Case File: meeting_id, board_date (meeting_listed)
    left = take_off_agendas(case_id, user, keep=to, why="moved", moved_to=to, reason=reason)
    now = _now()
    c = store.get_case(case_id)
    send = c.get("board_send") if isinstance(c.get("board_send"), dict) else {"list": lst}
    send.pop("withdrawn", None)
    send["meeting_id"] = to
    c["board_send"] = send
    c.setdefault("board_send_history", []).append({"moved_to": to, "from": frm, "reason": reason, "by": user or "", "at": now})
    store.save_case(c)
    store.audit(case_id, {"kind": "agenda_moved", "by": user or "", "from": frm, "to": to, "from_date": (old or {}).get("date") or "",
                          "to_date": s.get("date") or "", "list": lst, "reason": reason, "left": left})
    for mid in dict.fromkeys([to] + ([frm] if frm and frm not in left and old else []) + left):
        board.audit_event(mid, "agenda_moved", user, case_id=case_id, reason=reason, **{"from": frm, "to": to})  # "from" is a keyword
    title = f"Moved to the meeting of {_dmy(s.get('date'))}: {patient_line(c) or case_id} ({case_id})"
    text = (f"Moved from the meeting of {_when(old)}" if old else "Put on this meeting") + f" by {display_name(user)}." + (f" Reason: {reason}" if reason else "")
    _tell_coordinator(c, title, text, meeting_id=to, by=user)
    return c


def withdraw_case(case_id: str, user: str, reason: str) -> dict:
    """The owner (or the MDT Coordinator) takes a Case File off the agenda with a reason (3 to 500 characters): it leaves every planned
    meeting's lists, meeting_id is cleared (board_date kept), board_send records withdrawn {by, at, reason} (the ready mark stays, so
    Send to the board can pick a meeting again); audited in the Case File (agenda_withdrawn) and on the meeting; the coordinator is
    told. Returns the Case File."""
    reason = " ".join(str(reason or "").split())
    if len(reason) < MIN_WITHDRAW_REASON:
        raise MeetingError("Say why it comes off the agenda.", 400, "reason_needed")
    if len(reason) > MAX_WITHDRAW_REASON:
        raise MeetingError(f"Keep the reason to {MAX_WITHDRAW_REASON} characters.", 400, "reason_too_long")
    c = _sent_case(case_id)
    frm = str(c.get("meeting_id") or "")
    old = get(frm) if frm else None
    left = take_off_agendas(case_id, user, why="withdrawn", reason=reason)
    if not left and not frm:
        raise MeetingError("It is not on a meeting's agenda.", 400, "not_on_agenda")
    if not old and left:
        old = get(left[0])
    now = _now()
    c = store.get_case(case_id)
    c.pop("meeting_id", None)
    send = c.get("board_send") if isinstance(c.get("board_send"), dict) else {"list": "discussion"}
    send["meeting_id"] = ""
    send["withdrawn"] = {"by": user or "", "at": now, "reason": reason}
    c["board_send"] = send
    c.setdefault("board_send_history", []).append({"withdrawn_from": frm or (left[0] if left else ""), "reason": reason, "by": user or "", "at": now})
    store.save_case(c)
    store.audit(case_id, {"kind": "agenda_withdrawn", "by": user or "", "meeting_id": frm, "left": left, "reason": reason})
    for mid in dict.fromkeys(([frm] if old and frm else []) + left):
        board.audit_event(mid, "agenda_withdrawn", user, case_id=case_id, reason=reason)
    when = _dmy((old or {}).get("date")) if old else ""
    title = (f"Taken off the agenda of {when}" if when else "Taken off the agenda") + f": {patient_line(c) or case_id} ({case_id})"
    _tell_coordinator(c, title, f"Taken off by {display_name(user)}. Reason: {reason}", meeting_id=(old or {}).get("id") or "", by=user)
    return c


def _member_departments(s) -> list[str]:
    """The departments an agenda goes to: the attendance sheet (heads, the hospital's list, owners and participants of the Case Files)."""
    try:
        return [d["id"] for d in board.attendance_list(s) if d.get("id") and d["id"] != org.COORDINATOR_ID]
    except Exception:
        return []


def send_agenda(mid: str, by: str) -> dict:
    """A message to the members (the departments on the attendance sheet) with the counts; a later addition is flagged on its row."""
    s = need(mid); _active(s)
    lists = s.get("agenda_lists") or {}
    ids = [it["case_id"] for k in ("discussion", "noting") for it in lists.get(k) or [] if it.get("case_id")]
    resent = bool(s.get("agenda_sent_at"))
    new = [c for c in ids if c not in (s.get("agenda_sent_cases") or [])] if resent else []
    when = _dmy(s.get("date")) + (f" at {s['time']}" if s.get("time") else "")
    title = f"Agenda for the Tumour Board on {when}" + (" (updated)" if resent else "")
    text = (f"{len(lists.get('discussion') or [])} Case File(s) for discussion, {len(lists.get('noting') or [])} for noting"
            + (f"; {len(new)} added since the last agenda" if resent and new else "") + (f". Room: {s['room']}" if s.get("room") else "")
            + (". Video link available." if s.get("video") else "") + " Open the meeting page for the list.")
    sent_to = []
    for did in _member_departments(s):
        try:
            notify.notify({"department": did}, "agenda", "", title, text, meeting_id=mid, cases=len(ids), by=by)
            sent_to.append(did)
        except Exception as e:
            log.warning("meeting %s: agenda to %s failed (%s)", mid, did, e)
    now = _now()
    s["agenda_sent_at"] = now
    s["agenda_sent_cases"] = ids
    s.setdefault("agenda_sends", []).append({"at": now, "by": by, "cases": ids, "to": sent_to, "new": new})
    _save(s)
    board.audit_event(mid, "agenda_sent", by, cases=len(ids), to=sent_to, new=new)
    _send(s, {"type": "agenda", "counts": counts(s), "sent_at": now})
    return {"sent_at": now, "sent_to": sent_to, "cases": len(ids), "new": new}


def _on_lists(s, case_id, lists=LISTS) -> bool:
    return any(it.get("case_id") == case_id for k in lists for it in (s.get("agenda_lists") or {}).get(k) or [])


def remind(mid: str, by: str, roles: dict, case_id: str) -> dict:
    """One reminder to the owning department of a Case File on the agenda (dept_requests.remind_owner: audited in the Case File)."""
    s = need(mid); _active(s)
    if not _on_lists(s, case_id):
        raise MeetingError("This Case File is not on the meeting's lists.", 404, "not_on_agenda")
    if access.is_archived(store.get_case(case_id)):  # security review #7
        raise MeetingError(access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", 409, "archived")
    try:
        res = dept_requests.remind_owner(case_id, by, roles)
    except dept_requests.RequestError as e:
        raise MeetingError(str(e), e.status, "remind_failed")
    board.audit_event(mid, "reminded", by, case_id=case_id, to=res.get("to"))
    return res


# ---- the join code and the waiting room -----------------------------------------------------------------------------------------------

def _expired(code: dict, now: datetime | None = None) -> bool:
    try:
        return datetime.fromisoformat(str(code.get("expires_at"))) <= (now or datetime.now())
    except (TypeError, ValueError):
        return True


def new_code(mid: str, by: str) -> dict:
    """A fresh 6-digit code (the old one stops working), valid 12 hours; never written to the audit log."""
    s = need(mid); _active(s)
    used = {(x.get("code") or {}).get("value") for x in board.all_sessions() if x.get("status") in ("planned", "in_session") and isinstance(x.get("code"), dict)}
    value = f"{secrets.randbelow(10 ** 6):06d}"
    while value in used:
        value = f"{secrets.randbelow(10 ** 6):06d}"
    expires = (datetime.now() + timedelta(hours=CODE_TTL_HOURS)).isoformat(timespec="seconds")
    s["code"] = {"value": value, "expires_at": expires, "attempts": 0, "created_at": _now(), "created_by": by}
    _save(s)
    board.audit_event(mid, "code_issued", by, expires_at=expires)
    return {"value": value, "expires_at": expires}


def expire_codes(now: datetime | None = None) -> list[str]:
    """Drop the codes past their expiry (the scheduler's job). Returns the meetings changed."""
    out = []
    for s in board.all_sessions():
        if s.get("status") not in ("planned", "in_session") or not isinstance(s.get("code"), dict):
            continue
        if _expired(s["code"], now):
            s["code"] = None
            board.save_session(s)
            board.audit_event(s["id"], "code_expired", AUTOMATIC)
            out.append(s["id"])
    return out


def _sync_department(s, user, by) -> None:
    """An admitted person marks its department present on the old attendance sheet and is recorded as a member by name (the minutes)."""
    p = (s.get("people") or {}).get(user) or {}
    did = p.get("department") or ""
    if not did or did == org.COORDINATOR_ID or p.get("outside_expert"):
        return
    att = s.setdefault("attendance", {})
    if att.get(did, "not_marked") != "present":
        att[did] = "present"
    if not any(m.get("user") == user for m in s.get("members") or []):
        s.setdefault("members", []).append({"id": "M" + uuid.uuid4().hex[:6], "name": p.get("name") or display_name(user), "department": did,
                                            "added_by": by or "", "at": _now(), "user": user})


def join(code: str, user: str, r: dict) -> dict:
    """Join by the 6-digit code: 404 no_such_code when no planned or running meeting has it, 410 code_expired when it expired. The
    coordinator is admitted at once; everyone else waits for the coordinator (status waiting). Audited (never the code)."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        raise MeetingError("Enter the 6-digit meeting code.", 404, "no_such_code")
    s = next((x for x in board.all_sessions() if x.get("status") in ("planned", "in_session") and isinstance(x.get("code"), dict) and x["code"].get("value") == code), None)
    if not s:
        raise MeetingError("No meeting has this code. Check the digits with the MDT Coordinator.", 404, "no_such_code")
    board.ensure_meeting_fields(s)
    if _expired(s["code"]):
        raise MeetingError("This meeting code has expired. Ask the MDT Coordinator for a new one.", 410, "code_expired")
    s["code"]["attempts"] = int(s["code"].get("attempts") or 0) + 1
    admitted = manage(r)
    p = (s.get("people") or {}).get(user) or {}
    if p.get("status") in ADMITTED:
        status = p["status"]
    else:
        status = "present" if admitted else "waiting"
    s["people"][user] = {**p, "name": display_name(user), "department": user_department(user), "status": status, "mode": p.get("mode") or ("room" if admitted else None),
                         "joined_at": p.get("joined_at") or _now(), "outside_expert": bool(r.get("outside_expert"))}
    if status in ADMITTED:
        _sync_department(s, user, user)
    _save(s)
    board.audit_event(s["id"], "joined", user, status=status)
    _send(s, {"type": "presence", "attendance": attendance_rows(s), "online": live.online(s["id"]), "joined": user})
    return {"meeting_id": s["id"], "status": "admitted" if status in ADMITTED else "waiting", "meeting": summary_row(s)}


def admit(mid: str, by: str, user: str) -> dict:
    s = need(mid); _active(s)
    people = s.get("people") or {}
    if user not in people:  # the login as typed or shown, in any case
        user = next((u for u in people if u.casefold() == str(user or "").casefold()), user)
    p = people.get(user)
    if not p:
        raise MeetingError("This person has not joined the meeting with its code.", 404, "not_joined")
    if p.get("status") not in ADMITTED:
        p["status"] = "present" if p.get("mode") == "room" else "remote"
        p["admitted_by"], p["admitted_at"] = by, _now()
    _sync_department(s, user, by)
    _save(s)
    board.audit_event(mid, "admitted", by, user=user, status=p["status"])
    rows = attendance_rows(s)
    _send(s, {"type": "admit", "user": user, "status": p["status"], "attendance": rows, "agent": agent_state(s)})
    return next((x for x in rows if x["user"] == user), {"user": user, "status": p["status"]})


def present(mid: str, user: str, r: dict, mode: str) -> dict:
    """'I am in the room' (mode room) or remote: sets how the person takes part; an admitted person's status follows."""
    if mode not in MODES:
        raise MeetingError("The mode must be room or remote.", 400, "bad_mode")
    s = need(mid); _active(s)
    p = (s.get("people") or {}).get(user)
    if not p:
        if not manage(r):
            raise MeetingError("Join the meeting with its code first.", 404, "not_joined")
        p = s["people"][user] = {"name": display_name(user), "department": user_department(user), "status": "present", "mode": mode, "joined_at": _now(),
                                 "outside_expert": False}
    p["mode"] = mode
    if p.get("status") in ADMITTED:
        p["status"] = "present" if mode == "room" else "remote"
        _sync_department(s, user, user)
    _save(s)
    board.audit_event(mid, "presence_mode", user, mode=mode, status=p["status"])
    rows = attendance_rows(s)
    _send(s, {"type": "presence", "attendance": rows, "online": live.online(mid)})
    return next((x for x in rows if x["user"] == user), {"user": user, "status": p["status"], "mode": mode})


# ---- running the meeting ---------------------------------------------------------------------------------------------------------------

def _fresh_timer(s, cid) -> dict:
    it = next((x for k in ("discussion", "noting") for x in (s.get("agenda_lists") or {}).get(k) or [] if x.get("case_id") == cid), {})
    total = _minutes_for(s, it) * 60
    return {"running": False, "total": total, "left": total, "started_at": None}


def start(mid: str, by: str) -> dict:
    """The meeting starts (board.start: the first Case File for discussion comes on the floor); the agents of the heads not present prepare
    their briefs as the old room does (service.prepare_session_agents; nothing when every head is present)."""
    s = need(mid)
    if s.get("status") != "planned":
        raise MeetingError("Only a planned meeting can be started.", 409, "not_planned")
    try:
        board.start(mid, by)
    except ValueError as e:
        raise MeetingError(str(e), 409, "not_planned")
    s = need(mid)
    s["live"] = {"slide": 0, "opened": None, "timer": _fresh_timer(s, s.get("current")) if s.get("current") else None}
    _save(s)
    pairs = []
    try:
        from . import service
        pairs = service.prepare_session_agents(mid, by) or []
    except Exception as e:  # the briefs are support; the meeting starts without them
        log.warning("meeting %s: briefs not prepared (%s)", mid, e)
    board.audit_event(mid, "meeting_started", by, preparing=len(pairs))
    _send(s, {"type": "current", **current_view(s), "agent": agent_state(s), "status": "in_session"})
    return {"meeting": summary_row(s), "preparing": len(pairs), "current": current_view(s)}


def end(mid: str, by: str) -> dict:
    s = need(mid); _active(s)
    try:
        from . import service
        service.close_session(mid, by)
    except ValueError as e:
        raise MeetingError(str(e), 409, "meeting_over")
    s = need(mid)
    for p in (s.get("people") or {}).values():
        if p.get("status") == "waiting":
            p["status"] = "absent"
    s["code"] = None
    if isinstance((s.get("live") or {}).get("timer"), dict) and s["live"]["timer"].get("running"):
        t = s["live"]["timer"]
        t["left"], t["running"], t["started_at"] = _timer_left(t), False, None
    _save(s)
    LIVE_DECISION.pop(mid, None)
    AGENT_STATE.pop(mid, None)
    pacs.end_session(mid)
    board.audit_event(mid, "meeting_ended", by, outcomes=len(s.get("outcomes") or {}), cards=sum(len(v) for v in (s.get("cards") or {}).values()))
    _send(s, {"type": "ended", "meeting": summary_row(s)})
    return {"meeting": summary_row(s)}


def set_current(mid: str, by: str, case_id: str = "", slide=None) -> dict:
    s = need(mid); _in_session(s)
    changed_case = False
    if case_id and case_id != s.get("current"):
        try:
            board.set_current(mid, case_id, by)
        except ValueError as e:
            raise MeetingError(str(e), 404, "not_on_agenda")
        s = need(mid)
        s["live"] = {"slide": 0, "opened": None, "timer": _fresh_timer(s, case_id)}
        LIVE_DECISION.pop(mid, None)
        AGENT_STATE.pop(mid, None)
        changed_case = True
    if slide is not None:
        try:
            s.setdefault("live", {})["slide"] = max(0, int(slide))
        except (TypeError, ValueError):
            raise MeetingError("The slide must be a number.", 400, "bad_slide")
    _save(s)
    if not changed_case:
        board.audit_event(mid, "slide", by, case_id=s.get("current"), slide=s.get("live", {}).get("slide"))
    cv = current_view(s)
    _send(s, {"type": "current", **cv, "agent": agent_state(s)})
    return {**cv, "agent": agent_state(s)}


async def open_item(mid: str, by: str, kind: str, doc_id: str = "") -> dict | None:
    """What the shared screen shows beside the slides: a record (its file url), the images of an imaging report (every admitted
    member is granted the viewer on that study and the viewer url is broadcast) or nothing. Humans view; no model reads images."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if not cid:
        raise MeetingError("No Case File is on the floor.", 409, "no_current")
    if kind not in ("record", "images", "none"):
        raise MeetingError("The kind must be record, images or none.", 400, "bad_kind")
    opened = None
    if kind != "none":
        try:
            d = store.get_doc(cid, doc_id) if doc_id else None
        except ValueError:
            d = None
        if not d:
            raise MeetingError("Record not found in this Case File.", 404, "no_record")
        title = (d.get("classification") or {}).get("title") or d.get("filename") or doc_id
        if kind == "record":
            opened = {"kind": "record", "doc_id": doc_id, "title": title, "url": f"/api/tb/cases/{cid}/documents/{doc_id}/file", "by": by, "at": _now()}
            store.audit(cid, {"kind": "record_opened_in_meeting", "by": by, "doc_id": doc_id, "session": mid})
        else:
            h = d.get("his") or {}
            if not h.get("imaging_study_ref"):
                raise MeetingError("This record has no imaging study in the hospital system.", 404, "no_images")
            study = None
            client = his_client.client()
            if client is None and h.get("study"):
                study = pacs._study_view(h["study"])
            else:
                try:
                    study = await pacs.study_for_doc(cid, d, client)
                except Exception as e:
                    if h.get("study"):
                        study = pacs._study_view(h["study"])
                    else:
                        raise MeetingError(f"The hospital system did not answer about the study: {type(e).__name__}.", 502, "his_down")
            if not study or not study.get("available"):
                raise MeetingError((study or {}).get("reason") or "Images not available in the PACS.", 409, "images_not_available")
            uid = study["study_uid"]
            consent = bool(((store.get_case(cid) or {}).get("consent") or {}).get("outside_discussion"))  # images carry the patient's identity
            users = sorted({u for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED and (consent or not p.get("outside_expert"))} | {by})
            for u in users:
                pacs.grant(u, uid, cid, doc_id, session=mid)
            opened = {"kind": "images", "doc_id": doc_id, "title": title, "study_uid": uid, "url": pacs.viewer_url(uid), "modality": study.get("modality"),
                      "granted": users, "by": by, "at": _now()}
            store.audit(cid, {"kind": "images_opened", "by": by, "doc_id": doc_id, "study_uid": uid, "accession": study.get("accession") or "", "available": True,
                              "session": mid, "granted_to": users})
    s.setdefault("live", {})["opened"] = opened
    _save(s)
    board.audit_event(mid, "opened", by, cid, what=kind, doc_id=doc_id)
    _send(s, {"type": "open", "case_id": cid, "opened": opened})
    return opened


def shows_record(r: dict, case_id: str, doc_id: str) -> str | None:
    """The meeting whose shared screen shows this record of this Case File now, when `r` is one of its admitted members (an outside
    expert only with the patient's consent to an outside discussion); else None. The room screen and the remote members follow the shared
    screen even when their own department has no scope on the Case File (18 Oct, e2e: such a member got 403 on the record)."""
    if not isinstance(r, dict) or r.get("disabled") or not case_id or not doc_id:
        return None
    for s in board.running_sessions():
        opened = (s.get("live") or {}).get("opened") or {}
        if s.get("current") != case_id or opened.get("kind") != "record" or opened.get("doc_id") != doc_id or not is_member(r, s):
            continue
        if r.get("outside_expert") and not bool(((store.get_case(case_id) or {}).get("consent") or {}).get("outside_discussion")):
            continue
        return s["id"]
    return None


def timer(mid: str, by: str, action: str, minutes=None) -> dict | None:
    s = need(mid); _in_session(s)
    t = (s.get("live") or {}).get("timer") or _fresh_timer(s, s.get("current"))
    mins = _check_minutes(minutes)
    now_ts = time.time()
    if action == "start":
        if mins:
            t["total"] = t["left"] = mins * 60
        if not t.get("running"):
            t["running"], t["started_at"] = True, now_ts
    elif action == "stop":
        if t.get("running"):
            t["left"], t["running"], t["started_at"] = _timer_left(t, now_ts), False, None
    elif action == "reset":
        total = (mins * 60) if mins else int(t.get("total") or 0)
        t = {"running": False, "total": total, "left": total, "started_at": None}
    else:
        raise MeetingError("The action must be start, stop or reset.", 400, "bad_action")
    s.setdefault("live", {})["timer"] = t
    _save(s)
    board.audit_event(mid, "timer", by, action=action, minutes=mins, case_id=s.get("current"))
    tv = timer_view(t)
    _send(s, {"type": "timer", "case_id": s.get("current"), "timer": tv})
    return tv


# ---- questions, the stand-in agent, hands, the live decision ------------------------------------------------------------------------------

def _set_agent(mid: str, state: str, role: str, question: str | None) -> None:
    AGENT_STATE[mid] = {"state": state, "role": role, "question": question, "at": _now()}
    live.broadcast(mid, {"type": "agent_state", "agent": {"active": True, "role": role, "state": state, "question": question}})


def ask(mid: str, user: str, text: str, role: str | None = None) -> dict:
    """A member types a question: it appears on the shared screen; when a stand-in agent is active for the Case File on the floor the
    question is marked for it (the route runs answer() in the background). Audited."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if not cid:
        raise MeetingError("No Case File is on the floor.", 409, "no_current")
    text = " ".join(str(text or "").split())[:MAX_QUESTION]
    if not text:
        raise MeetingError("Type a question.", 400, "empty")
    q = {"id": "Q" + uuid.uuid4().hex[:6], "by": user, "by_name": display_name(user), "text": text, "at": _now(), "case_id": cid, "answer": None, "role": None}
    ag = agent_state(s)
    if ag["active"]:
        q["role"] = role if role in (ag.get("roles") or []) else ag["role"]
        q["agent_label"] = ag.get("label") if q["role"] == ag["role"] else org.department_name(board.ROLE_DEPARTMENT.get(q["role"], q["role"]))
    s.setdefault("questions", []).append(q)
    _save(s)
    board.audit_event(mid, "question", user, case_id=cid, question=text[:300], role=q["role"])
    _send(s, {"type": "question", "question": q})
    return q


async def answer(mid: str, qid: str, user: str = "") -> dict | None:
    """The stand-in agent answers one question from the records (agents.ask: verified quotes only, guardrails), with its states broadcast
    (reading_question, thinking, answering); the answer joins the question on the shared screen and the session's agent log."""
    s = need(mid)
    q = next((x for x in s.get("questions") or [] if x.get("id") == qid), None)
    if not q or not q.get("role"):
        return None
    if q.get("answer") is not None or (mid, qid) in _ANSWERING:  # one answer per question, even when asked to answer twice
        return q.get("answer")
    _ANSWERING.add((mid, qid))
    role, cid, text = q["role"], q.get("case_id"), q.get("text") or ""
    out = None
    try:
        _set_agent(mid, "reading_question", role, qid)
        await asyncio.sleep(0)
        _set_agent(mid, "thinking", role, qid)
        from . import agents
        a = await agents.ask(cid, role, text, None, user or q.get("by") or "")
        _set_agent(mid, "answering", role, qid)
        stmts = list(a.get("statements") or [])
        out = {"status": a.get("status") or ("answered" if stmts else "not_documented"), "text": " ".join(x.get("text", "") for x in stmts) or str(a.get("message") or ""),
               "statements": stmts, "references": list(a.get("references") or []), "role": role, "label": a.get("label") or role, "model": a.get("model"),
               "at": _now(), "seconds": a.get("seconds"), "note": "From the records only; the agent is not a member of the board"}
        try:
            board.log_answer(mid, cid, role, text, a, by=user or q.get("by") or "")
        except ValueError as e:
            log.info("meeting %s: answer not logged (%s)", mid, e)
    except Exception as e:
        log.exception("meeting %s: stand-in answer failed", mid)
        out = {"status": "error", "text": f"The stand-in agent could not answer ({e.__class__.__name__}).", "statements": [], "references": [], "role": role, "at": _now()}
    finally:
        try:
            s = need(mid)
            q2 = next((x for x in s.get("questions") or [] if x.get("id") == qid), None)
            if q2 is not None and out is not None:
                q2["answer"] = out
                _save(s)
                board.audit_event(mid, "question_answered", "system", case_id=cid, question_id=qid, role=role, status=out.get("status"))
                _send(s, {"type": "question", "question": q2})
        except Exception:
            log.exception("meeting %s: could not store the answer", mid)
        _ANSWERING.discard((mid, qid))
        _set_agent(mid, "ready", role, None)
    return out


def answer_in_background(mid: str, qid: str, user: str = "") -> bool:
    """Schedule answer() on the running loop (the route's); False when there is no loop (tests call answer() directly)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    t = loop.create_task(answer(mid, qid, user))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return True


def hand(mid: str, user: str, raised: bool) -> list[dict]:
    s = need(mid); _in_session(s)
    hands = [h for h in s.get("hands") or [] if h.get("user") != user]
    if raised:
        hands.append({"user": user, "name": display_name(user), "at": _now()})
    s["hands"] = hands
    _save(s)
    board.audit_event(mid, "hand", user, raised=bool(raised))
    _send(s, {"type": "hand", "hands": hands})
    return hands


def decision_live(mid: str, by: str, text: str) -> dict:
    """The decision as the coordinator types it: broadcast to the room screen marked "not saved"; saved only through record_decision."""
    s = need(mid); _in_session(s)
    d = {"text": str(text or "")[:MAX_TEXT], "by": by, "at": _now(), "case_id": s.get("current"), "saved": False}
    LIVE_DECISION[mid] = d
    _send(s, {"type": "decision_live", **d})
    return d


# ---- the decision, the end of a case, the cards ------------------------------------------------------------------------------------------

def _card_concerns(s, cid) -> list[dict]:
    out = []
    for u, c in ((s.get("cards") or {}).get(cid) or {}).items():
        if isinstance(c, dict) and not c.get("agree"):
            out.append({"by": c.get("name") or display_name(u), "user": u, "text": c.get("note") or "Concern raised (no note)", "from_card": True})
    return out


async def record_decision(mid: str, cid: str, body: dict, user: str) -> dict:
    """The board's outcome for a Case File: decision, deferred (what is awaited, from whom), referred, not discussed (moves the Case File to
    the next planned meeting, else leaves it flagged) or noted. Written as a board record through postboard.record_decision (adjudication,
    follow-up actions, the old board tab) and linked to the session; the owner is told (kind outcome). Concerns from the cards always join
    the record."""
    s = need(mid)
    if s.get("status") == "cancelled":
        raise MeetingError("This meeting was cancelled.", 409, "meeting_over")
    if not _on_lists(s, cid, ("discussion", "noting")) and cid not in {a.get("case_id") for a in s.get("agenda") or []}:
        raise MeetingError("This Case File is not on the meeting's agenda.", 404, "not_on_agenda")
    c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
    if not c:
        raise MeetingError("Case File not found.", 404, "no_case")
    if access.is_archived(c):  # security review #8
        raise MeetingError(access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", 409, "archived")
    outcome = str(body.get("outcome") or "decision").strip()
    if outcome not in OUTCOMES:
        raise MeetingError(f"The outcome must be one of: {', '.join(OUTCOMES)}.", 400, "bad_outcome")
    text = " ".join(str(body.get("decision_text") or "").split())[:MAX_TEXT]
    awaited = " ".join(str(body.get("awaited") or "").split())[:300]
    awaited_from = " ".join(str(body.get("awaited_from") or "").split())[:120]
    referred_to = " ".join(str(body.get("referred_to") or "").split())[:300]
    if outcome == "decision" and not text:
        raise MeetingError("Write the board's decision.", 400, "empty")
    if outcome == "deferred" and not (awaited or text):
        raise MeetingError("Say what is awaited and from whom.", 400, "empty")
    if outcome == "referred" and not (referred_to or text):
        raise MeetingError("Say where the Case File is referred to.", 400, "empty")
    nxt = board.next_planned_after(s) if outcome == "not_discussed" else None
    if not text:
        text = {"deferred": f"Deferred: awaiting {awaited}" + (f" from {awaited_from}" if awaited_from else ""),
                "referred": f"Referred to {referred_to}", "noted": "Noted for information; no decision taken",
                "not_discussed": "Not discussed" + (f": moved to the meeting on {_dmy(nxt.get('date'))}" if nxt else "; no later meeting planned yet")}.get(outcome, text)
    concerns = [{"by": str(x.get("by") or "")[:120], "text": " ".join(str(x.get("text") or "").split())[:MAX_NOTE]} for x in body.get("concerns") or [] if isinstance(x, dict) and x.get("text")]
    have = {x["text"] for x in concerns}
    concerns += [x for x in _card_concerns(s, cid) if x["text"] not in have]
    members = [str(x)[:120] for x in body.get("members_present") or [] if str(x).strip()] or [p.get("name") or u for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED]
    part = board.participants(s)
    intent = str(body.get("intent_as_stated") or "").strip()
    next_date = _iso_date(body.get("next_step_date"))
    actions = []
    did = org.department_id(awaited_from) if awaited_from else None
    if outcome == "deferred" and awaited and did:
        actions.append({"task": f"Awaited by the board: {awaited}", "department": org.department_name(did), "due": next_date or (date.today() + timedelta(days=14)).isoformat()})
    rec = {"decision_text": text, "outcome_type": outcome if outcome in postboard.OUTCOMES else "decision", "meeting_outcome": outcome,
           "rationale": " ".join(str(body.get("rationale") or "").split())[:MAX_TEXT], "intent_as_stated": intent[:300],
           "intent_as_recorded": intent.lower() if intent.lower() in postboard.INTENTS else "", "responsible_doctor": str(body.get("responsible_doctor") or "")[:120],
           "next_step": " ".join(str(body.get("next_step") or "").split())[:MAX_NOTE], "next_step_date": next_date, "awaited": awaited, "awaited_from": awaited_from,
           "deferred_reason": (awaited + (f" (from {awaited_from})" if awaited_from else ""))[:300] if outcome == "deferred" else "", "referred_to": referred_to,
           "concerns": concerns, "divergent_opinions": "; ".join(f"{x['by']}: {x['text']}" if x.get("by") else x["text"] for x in concerns)[:MAX_TEXT],
           "members_present": members, "participants": ", ".join(members) or part["text"], "board_date": s.get("date"), "session": mid,
           "attendance": {"present": part["present"], "absent": part["absent"], "members": part["members"]}, "actions": actions, "recorded_by": display_name(user)}
    try:
        record = await postboard.record_decision(cid, rec, user)
    except ValueError as e:
        raise MeetingError(str(e), 400, "bad_record")
    try:
        board.link_decision(mid, cid, record, user)
    except ValueError as e:
        log.warning("meeting %s: decision not linked (%s)", mid, e)
    s = need(mid)
    oc = {"outcome": outcome, "label": OUTCOMES[outcome], "record": record["id"], "by": user, "at": _now(), "decision_text": text, "moved_to": None, "flagged": False}
    if outcome == "not_discussed":
        if nxt:
            board.ensure_meeting_fields(nxt)
            lists = nxt["agenda_lists"]
            if not _on_lists(nxt, cid):
                lists["discussion"].append({"case_id": cid, "reason": f"Not discussed on {_dmy(s.get('date'))}", "minutes": None, "added_at": _now(), "added_by": user})
                board.sync_agenda_lists(nxt, user)
                board.save_session(nxt)
                board.audit_event(nxt["id"], "agenda_added_to_list", user, case_id=cid, list="discussion", reason=f"not discussed in {mid}")
            oc["moved_to"] = nxt["id"]
            _link_case(cid, nxt, user)
        else:
            oc["flagged"] = True
            c = store.get_case(cid)
            c.setdefault("board_flags", []).append({"kind": "not_discussed", "session": mid, "at": _now(), "by": user})
            store.save_case(c)
    s.setdefault("outcomes", {})[cid] = oc
    LIVE_DECISION.pop(mid, None)
    _save(s)
    board.audit_event(mid, "outcome", user, cid, "outcome", outcome=outcome, record=record["id"], moved_to=oc["moved_to"], flagged=oc["flagged"],
                      concerns=len(concerns))
    _tell_owner(c, s, oc, text, user)
    _send(s, {"type": "decision", "case_id": cid, "outcome": oc, "record": record["id"]})
    return {"record": record, "outcome": oc}


def _tell_owner(c: dict, s: dict, oc: dict, text: str, by: str) -> None:
    cid = c.get("case_id")
    patient = (c.get("patient") or {}).get("name") or cid
    title = f"Board outcome for {patient} ({cid}): {oc['label']}"
    body_ = text[:600] + (f" Moved to the meeting on {_dmy((get(oc['moved_to']) or {}).get('date'))}." if oc.get("moved_to") else "") \
        + (" No later meeting is planned yet: the Case File is flagged for the MDT Coordinator." if oc.get("flagged") else "")
    sent = False
    own = access.owner(c)
    if own:
        try:
            notify.notify({"department": own}, "outcome", cid, title, body_, outcome=oc["outcome"], record=oc["record"], session=s["id"], by=by)
            sent = True
        except Exception as e:
            log.warning("outcome notice to %s failed (%s)", own, e)
    ou = owner_user(c)
    if ou and (not sent or ou not in (org.load().get("users") or {}) or own not in (org.roles(ou).get("departments") or {})):
        try:
            notify.notify({"user": ou}, "outcome", cid, title, body_, outcome=oc["outcome"], record=oc["record"], session=s["id"], by=by)
        except Exception as e:
            log.warning("outcome notice to %s failed (%s)", ou, e)


def end_case(mid: str, cid: str, by: str) -> dict:
    """The discussion of a Case File ends: each board head is asked for its card (notification kind card_requested); the room shows the
    card prompt (event end_case)."""
    s = need(mid); _in_session(s)
    if not _on_lists(s, cid, ("discussion", "noting")):
        raise MeetingError("This Case File is not on the meeting's agenda.", 404, "not_on_agenda")
    c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
    if not c:
        raise MeetingError("Case File not found.", 404, "no_case")
    s.setdefault("ended", {})[cid] = {"at": _now(), "by": by}
    if isinstance((s.get("live") or {}).get("timer"), dict) and s["live"]["timer"].get("running"):
        t = s["live"]["timer"]
        t["left"], t["running"], t["started_at"] = _timer_left(t), False, None
    _save(s)
    heads = board.heads()
    patient = (c.get("patient") or {}).get("name") or cid
    asked = []
    for h in heads:
        try:
            notify.notify({"department": h["id"]}, "card_requested", cid, f"Your card for {patient} ({cid})",
                          "The discussion has ended: record Agree or Concern with your note on the meeting page.", session=mid, by=by)
            asked.append(h["id"])
        except Exception as e:
            log.warning("meeting %s: card request to %s failed (%s)", mid, h["id"], e)
    board.audit_event(mid, "case_ended", by, cid, "case_ended", cards_requested=asked)
    _send(s, {"type": "end_case", "case_id": cid, "cards_requested": asked, "timer": timer_view((s.get("live") or {}).get("timer"))})
    return {"case_id": cid, "cards_requested": asked, "ended": s["ended"][cid]}


def card(mid: str, cid: str, user: str, agree, note: str = "") -> dict:
    """A member's card for a Case File (required for the board heads; the client asks for it): Agree or Concern with a note. A concern
    always reaches the record. Audited in the session and the Case File."""
    s = need(mid); _active(s)
    if not _on_lists(s, cid, ("discussion", "noting")) and cid not in {a.get("case_id") for a in s.get("agenda") or []}:
        raise MeetingError("This Case File is not on the meeting's agenda.", 404, "not_on_agenda")
    if not isinstance(agree, bool):
        raise MeetingError("Say whether you agree (true or false).", 400, "bad_card")
    note = " ".join(str(note or "").split())[:MAX_NOTE]
    if not agree and not note:
        raise MeetingError("Write your concern in a note.", 400, "note_needed")
    p = (s.get("people") or {}).get(user) or {}
    did = p.get("department") or user_department(user)
    rec = {"agree": agree, "note": note, "at": _now(), "name": p.get("name") or display_name(user), "department": did, "head": user in card_holders(s)}
    s.setdefault("cards", {}).setdefault(cid, {})[user] = rec
    _save(s)
    board.audit_event(mid, "card", user, cid, "card", agree=agree, note=note[:300], department=did)
    _send(s, {"type": "card", "case_id": cid, "user": user, "agree": agree, "cards_given": sorted(s["cards"][cid].keys())})
    return {"user": user, **rec}


def cards(mid: str, r: dict) -> dict:
    """The cards: every Case File for the coordinator; the Case Files of the owner's team for its members. Each with who is still expected
    (card_holders: the admitted heads of the board head departments, or their delegates)."""
    s = need(mid)
    expected = card_holders(s)
    out, visible = {}, []
    ids = [it["case_id"] for k in ("discussion", "noting") for it in (s.get("agenda_lists") or {}).get(k) or [] if it.get("case_id")]
    for cid in ids:
        c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
        if not c:
            continue
        if not (manage(r) or in_owner_team(r, c)):
            continue
        visible.append(cid)
        given = (s.get("cards") or {}).get(cid) or {}
        out[cid] = {"cards": [{"user": u, **v} for u, v in given.items()], "expected": expected, "missing": [u for u in expected if u not in given],
                    "concerns": sum(1 for v in given.values() if not v.get("agree"))}
    if not visible and not manage(r):
        raise MeetingError("The cards are for the MDT Coordinator and the teams that own the Case Files.", 403, "forbidden")
    return {"cards": out, "expected": expected}


# ---- slides for the room screen ------------------------------------------------------------------------------------------------------

WITHHELD = "[withheld]"
_NAME_STOP = {"patient", "test", "synthetic", "demo", "case", "file", "unknown", "baby", "master", "miss", "smt", "shri", "mrs", "kumari"}


def outside_view(r: dict | None, case: dict) -> bool:
    """An outside expert without the owner's recorded consent to an outside discussion: initials, age and sex, nothing that names the
    patient (security review #9)."""
    return bool(r and r.get("outside_expert") and not ((case or {}).get("consent") or {}).get("outside_discussion"))


def _identity_patterns(case: dict) -> list:
    """Regular expressions for what identifies the patient in slide text: the name (whole, and each longer name word), the UHID / MRN,
    ABHA, PM-JAY and IP / OP numbers, and the date of birth in ISO and DD/MM/YYYY spellings."""
    import re
    p = (case or {}).get("patient") or {}
    out, seen = [], set()

    def add(text, words=False):
        t = " ".join(str(text or "").split())
        if len(t) < 3 or t.lower() in seen:
            return
        seen.add(t.lower())
        body = re.escape(t).replace(r"\ ", r"\s+")
        out.append(re.compile((r"(?<!\w)" + body + r"(?!\w)") if words else body, re.IGNORECASE))
    name = str(p.get("name") or "")
    add(name, words=True)
    for w in re.split(r"[\s,.;:()/\-]+", name):
        if len(w) >= 4 and w.isalpha() and w.lower() not in _NAME_STOP:
            add(w, words=True)
    for k in ("mrn", "uhid", "abha", "pmjay_id", "ip_no", "op_no"):
        add(p.get(k))
    for x in p.get("ids") or []:
        if isinstance(x, dict):
            add(x.get("value"))
    his = (case or {}).get("his") or {}
    add(his.get("uhid") if isinstance(his, dict) else "")
    dob = str(p.get("dob") or "")[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
        y, mo, d = dob.split("-")
        for v in (dob, f"{d}/{mo}/{y}", f"{d}-{mo}-{y}", f"{d}.{mo}.{y}"):
            add(v)
    out.sort(key=lambda rx: len(rx.pattern), reverse=True)
    return out


def strip_identity(obj, case: dict):
    """A copy of the slide content with the patient's name, UHID, IP / OP numbers and date of birth replaced by [withheld]."""
    pats = _identity_patterns(case)

    def walk(x):
        if isinstance(x, str):
            for rx in pats:
                x = rx.sub(WITHHELD, x)
            return x
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(obj) if pats else obj

def _doc_row(d: dict) -> dict:
    cl = d.get("classification") or {}
    h = d.get("his") or {}
    study = h.get("study") if isinstance(h.get("study"), dict) else {}
    return {"doc_id": d["doc_id"], "title": cl.get("title") or d.get("filename"), "doc_type": cl.get("doc_type"), "date": cl.get("report_date_iso") or cl.get("event_date_iso") or "",
            "status": cl.get("status"), "signed": cl.get("signed"), "department": d.get("department"), "superseded": bool(d.get("superseded")), "outside": bool(d.get("outside")),
            "images": bool(h.get("imaging_study_ref")), "viewer_available": bool(study.get("available")), "modality": study.get("modality"),
            "url": f"/api/tb/cases/{d.get('case_id', '')}/documents/{d['doc_id']}/file"}


def slides(cid: str, r: dict | None = None) -> list[dict]:
    """Summary first, then the values with their sources, the gaps and waivers, the imaging records (with viewer availability), the pathology
    records, the points for review from the briefs and the summary, and the published cases when the doctor picked any. No model call.
    `r` the viewer: an outside expert without the owner's consent sees the patient as initials, age and sex."""
    c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
    if not c:
        raise MeetingError("Case File not found.", 404, "no_case")
    st = store.get_state(cid)
    arts = st.get("artefacts") or {}
    g = st.get("gate") or {}
    docs = rules.case_docs(cid, st)
    for d in docs:
        d["case_id"] = cid
    ready = [d for d in docs if d.get("state") == "ready" and not d.get("superseded")]
    out = []
    summ = arts.get("summary")
    if summ and summ.get("sections"):
        sig = rules.case_signature(cid, st)
        stale = rules.stale_reason(summ["signature"], sig) if summ.get("signature") else "Compiled before the Case File signature was kept"
        review = (summ.get("review") or {}).get("status")
        out.append({"id": "summary", "title": "Summary", "kind": "summary",
                    "content": {"from": "summary", "sections": [{"id": x.get("id"), "title": x.get("title"), "sentences": x.get("sentences") or []} for x in summ["sections"]],
                                "stage_as_recorded": summ.get("stage_as_recorded"), "stale": stale or "", "reviewed": review == "reviewed",
                                "label": "Reviewed" if review == "reviewed" else "AI draft, not reviewed", "model": summ.get("model"), "generated": summ.get("generated")}})
    else:
        out.append({"id": "summary", "title": "Summary", "kind": "summary",
                    "content": {"from": "gate", "patient_line": patient_line(c, r), "protocol": c.get("protocol"), "setting": c.get("setting"), "board_question": _board_question(c, st),
                                "readiness": g.get("readiness"), "satisfied": g.get("satisfied"), "total": g.get("total"), "passed": g.get("passed"),
                                "requirements": [{"id": q.get("id"), "label": q.get("label"), "department": q.get("department"), "status": q.get("status")} for q in g.get("requirements") or []],
                                "note": "No Case File summary compiled yet: the Pre-Authorization result is shown instead."}})
    cat = protocol.facts()
    facts = rules.resolve_facts(docs, st.get("overrides") or {})
    try:  # two reports differ and wait on the treating doctor's check: both values, each with its own quote (night-v3 item 1.5)
        diffs = discord.open_differences(cid, st)
    except Exception:
        diffs = {}
    values = []
    for fid, f in facts.items():
        cur = f.get("current") or {}
        if cur.get("state") not in (None, "present") or not cur.get("value"):
            continue
        if fid in diffs:
            values.extend(discord.slide_rows(fid, diffs[fid], len(f.get("history") or [])))
            continue
        values.append({"id": fid, "label": (cat.get(fid) or {}).get("label") or fid, "value": cur.get("value"), "quote": cur.get("quote") or "", "doc_id": cur.get("doc_id"),
                       "doc_title": cur.get("doc_title"), "date": cur.get("date") or cur.get("report_date"), "verification": cur.get("verification"), "final": bool(cur.get("doc_final")),
                       "page": (cur.get("location") or {}).get("page"), "source_method": cur.get("source_method"), "history": len(f.get("history") or [])})
    order = {k: i for i, k in enumerate(cat)}
    values.sort(key=lambda v: order.get(v.get("fact_id") or v["id"], len(order)))
    out.append({"id": "values", "title": "Key values with sources", "kind": "values", "content": {"values": values, "note": "Every value is a verbatim quote from the record named."}})
    gaps = [{"id": q.get("id"), "label": q.get("label"), "department": q.get("department"), "status": q.get("status"), "problems": list(q.get("problems") or []), "level": q.get("level")}
            for q in g.get("requirements") or [] if q.get("status") != "satisfied"]
    waivers = [{"requirement": x.get("key"), "by": x.get("by"), "at": x.get("at"), "reason": x.get("reason") or (x.get("fields") or {}).get("reason") or ""}
               for x in st.get("confirmations") or [] if isinstance(x, dict) and x.get("type") == "waive" and not x.get("undone")]
    out.append({"id": "gaps", "title": "Gaps and waivers", "kind": "gaps", "content": {"gaps": gaps, "waivers": waivers, "satisfied": g.get("satisfied"), "total": g.get("total")}})
    imaging = [_doc_row(d) for d in ready if (d.get("classification") or {}).get("doc_type") in IMAGING_TYPES or (d.get("his") or {}).get("imaging_study_ref")]
    out.append({"id": "imaging", "title": "Imaging", "kind": "imaging", "content": {"documents": imaging, "note": "Images open in the hospital's viewer for people; no model reads them."}})
    path_rows = []
    for d in ready:
        if (d.get("classification") or {}).get("doc_type") not in PATHOLOGY_TYPES:
            continue
        r_ = _doc_row(d)
        r_["facts"] = [{"id": fid, "label": (cat.get(fid) or {}).get("label") or fid, "value": f.get("value"), "quote": f.get("quote") or ""}
                       for fid, f in (d.get("facts") or {}).items() if isinstance(f, dict) and f.get("value") and f.get("verification") in rules.VERIFIED and f.get("state", "present") == "present"]
        path_rows.append(r_)
    out.append({"id": "pathology", "title": "Pathology", "kind": "pathology", "content": {"documents": path_rows}})
    points = []
    for p in (summ or {}).get("points_for_review") or []:
        points.append({"source": "summary", "role": None, "label": "Case File summary", "text": p.get("text"), "citations": p.get("citations") or [], "approximate": bool(p.get("approximate"))})
    for key, b in arts.items():
        if not key.startswith("brief_") or not isinstance(b, dict):
            continue
        for p in b.get("points_for_review") or []:
            points.append({"source": "brief", "role": key[6:], "label": b.get("label") or key[6:], "text": p.get("text"), "citations": p.get("citations") or [],
                           "references": p.get("references") or [], "approximate": bool(p.get("approximate")), "reviewed": (b.get("review") or {}).get("status") == "reviewed"})
    out.append({"id": "points", "title": "Points for review", "kind": "points", "content": {"points": points, "note": "AI drafts from the records and guideline points; never advice."}})
    try:
        pub = store.case_dir(cid) / "published.json"
        if pub.exists():
            data = store._read_json(pub, {}) or {}
            items = data.get("items") if isinstance(data, dict) else data
            if isinstance(items, list) and items:
                out.append({"id": "published", "title": "Published cases", "kind": "published",
                            "content": {"items": items, "note": "Published case, not advice for this patient"}})
    except Exception:
        pass
    if outside_view(r, c):  # an outside expert without consent: nothing that names the patient (security review #9)
        out = strip_identity(out, c)
    return out


# ---- for the scheduler ---------------------------------------------------------------------------------------------------------------

def starting_soon(now: datetime | None = None, minutes: int = 15) -> list[dict]:
    """Planned meetings starting within `minutes` that were not announced yet."""
    now = now or datetime.now()
    out = []
    for s in board.planned_sessions():
        if s.get("starting_notified_at") or not s.get("time"):
            continue
        at = _meeting_datetime(s)
        if at and now <= at <= now + timedelta(minutes=minutes):
            out.append(s)
    return out


def notify_starting(now: datetime | None = None, minutes: int = 15) -> list[str]:
    """Tell the members 15 minutes before a meeting (kind meeting_starting); once per meeting. Returns the meetings announced."""
    done = []
    for s in starting_soon(now, minutes):
        board.ensure_meeting_fields(s)
        title = f"Tumour Board starts at {s['time']}" + (f" in {s['room']}" if s.get("room") else "")
        text = f"{counts(s)['discussion']} Case File(s) for discussion, {counts(s)['noting']} for noting. Join with the meeting code" + (" or the video link." if s.get("video") else ".")
        for did in _member_departments(s):
            try:
                notify.notify({"department": did}, "meeting_starting", "", title, text, meeting_id=s["id"], by=AUTOMATIC)
            except Exception as e:
                log.warning("meeting %s: starting notice to %s failed (%s)", s["id"], did, e)
        try:
            notify.notify({"role": "coordinator"}, "meeting_starting", "", title, text, meeting_id=s["id"], by=AUTOMATIC)
        except Exception:
            pass
        s["starting_notified_at"] = _now()
        board.save_session(s)
        board.audit_event(s["id"], "starting_notified", AUTOMATIC)
        done.append(s["id"])
    return done


def any_in_session() -> bool:
    """A meeting is running now (board.running_now: a session left in session from an earlier day does not hold the scheduler back)."""
    return bool(board.running_sessions())
