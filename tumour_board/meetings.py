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

from . import access, after_send, board, config, decision_record, dept_requests, discord, his_client, live, notify, org, pacs, postboard, protocol, rules, store

log = logging.getLogger(__name__)

OUTCOMES = decision_record.OUTCOMES  # one table for the meeting, the board record, the minutes and the deck (night-v3 item 3.1)
LISTS = board.MEETING_LISTS
STATUSES = ("planned", "in_session", "closed", "cancelled")
ADMITTED = ("present", "remote")
MODES = ("room", "remote")
CODE_TTL_HOURS = 12
MAX_QUESTION, MAX_NOTE, MAX_TEXT, MAX_ROOM = 1000, 2000, 4000, 80
SPOTLIGHT_MAX = 3                                   # people the coordinator may spotlight for everyone (night-v3 5.1)
REACTIONS = ("agree", "thanks", "applause", "question")  # the four plain reactions; shown for a moment, never stored
REACTION_GAP = 2.0                                  # seconds between two reactions of one person
_REACTED: dict[tuple, float] = {}                    # (mid, user) -> time of the last reaction
MAX_CHAT, CHAT_VIEW = 1000, 200                     # a chat line's length; lines sent with the state (the file keeps every line) (night-v3 5.3)
CHAT_PER_MINUTE = 20
_CHATTED: dict[tuple, list] = {}                     # (mid, user) -> times of the last lines
PMJAY_DEPARTMENTS = ("surgical_oncology", "radiation_oncology", "medical_oncology")  # NHA HBP 2.2 manual 2021, 3.9: "advised" (night-v3 5.4)
AGENT_STATES = ("ready", "preparing", "listening", "thinking", "answering", "speaking", "error")  # true states per agent (night-v3 6.1)
LISTEN_TTL, AUDIO_TTL, ERROR_TTL = 65.0, 30.0, 60.0  # seconds: a listening device, a playback report, an error word
IMAGING_TYPES = ("ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan")
PATHOLOGY_TYPES = ("histopathology", "cytology", "ihc", "molecular")
AUTOMATIC = "Vaidyx (automatic)"

LIVE_DECISION: dict[str, dict] = {}  # mid -> {text, by, at, case_id}: what the coordinator types, shown "not saved" on the room screen
AGENT_STATE: dict[str, dict] = {}    # mid -> {role: {state, by, by_name, question, at, since, expires}}: each agent's live entry (memory only)
AGENT_AUDIO: dict[str, dict] = {}    # mid -> {question id: {role, devices: {user: expires}}}: the devices that report playing an answer
AGENT_LOCKS: dict[tuple, asyncio.Lock] = {}  # (mid, role) -> one answer at a time per agent
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


PRIVATE_EVENTS = ("open", "question", "decision_live", "decision", "card", "chat", "agent_speech", "agent_stop")  # live content: for the admitted members and the coordinator only


def _shape(s: dict):
    """Per socket: a member (admitted, or whoever manages the meeting) gets the event as it is; any other viewer (waiting, or a
    department on the attendance sheet that did not join) gets none of the live content: no private event, no opened record."""
    admitted = {u for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED}

    def shape(user, info, ev):
        if user in admitted or (isinstance(info, dict) and manage(info)):
            if ev.get("type") == "chat" and isinstance(info, dict) and info.get("outside_expert") and isinstance(ev.get("message"), dict):
                return {**ev, "message": _chat_lines(s, info, [ev["message"]])[0]}
            return ev
        if ev.get("type") in PRIVATE_EVENTS:
            return None
        if isinstance(ev.get("agents"), list):
            ev = {**ev, "agents": agents_public(ev["agents"])}  # no record quotes for a viewer who is not admitted
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
    from night-v3 item 1.4; a plain login before), else the team's owner, else (night-v3 5.6) the doctor of the owning department who
    created the file (the demo files carry no team owner); "" when the file was created by the coordinator or another department."""
    team = case.get("team") if isinstance(case.get("team"), dict) else {}
    p = case.get("presenter")
    if isinstance(p, dict):
        p = p.get("user")
    p = str(p or team.get("owner") or "")
    if p:
        return p
    cb = str(case.get("created_by") or "")
    if not cb:
        return ""
    try:
        r = org.roles(cb)
    except Exception:
        return ""
    return cb if access.is_owner_doctor(r, case) and not r.get("admin") else ""


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
            "ended": cid in (s.get("ended") or {}), "elapsed_seconds": ((s.get("ended") or {}).get(cid) or {}).get("elapsed_seconds"),
            "outcome": oc.get("outcome"), "outcome_label": OUTCOMES.get(oc.get("outcome") or "", ""),
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


def _elapsed(lv) -> int:
    """Seconds since the case came on the floor (live.case_started_at, set by start() and set_current()), never capped by the planned
    minutes; for a session started before this field existed, the countdown's total minus what is left; 0 otherwise (review M2)."""
    lv = lv if isinstance(lv, dict) else {}
    started = lv.get("case_started_at")
    if started:
        try:
            return max(0, int(time.time() - float(started)))
        except (TypeError, ValueError):
            pass
    t = lv.get("timer")
    if not isinstance(t, dict):
        return 0
    return max(0, int(t.get("total") or 0) - _timer_left(t))


def presenter_view(s: dict) -> dict | None:
    """The presenter of the Case File on the floor (night-v3 5.4): the one chosen when it was sent to the board, else the owner."""
    cid = s.get("current")
    c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
    if not c:
        return None
    u = presenter_of(c)
    if not u:
        return None
    did = user_department(u)
    return {"user": u, "name": display_name(u), "department": did, "department_name": org.department_name(did) if did else ""}


def current_view(s: dict) -> dict:
    lv = s.get("live") or {}
    return {"case_id": s.get("current"), "slide": int(lv.get("slide") or 0), "opened": lv.get("opened"), "timer": timer_view(lv.get("timer")),
            "presenter": presenter_view(s), "elapsed_seconds": _elapsed(lv), "presenting": lv.get("presenting") or None}


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


AGENT_NOTE = "AI agent, support only: answers from the records and guidelines; never a decision; not a member of the board"
ANSWER_NOTE = "AI agent, support only. From the records and guidelines only. Check the source."
NOT_DOCUMENTED_SPOKEN = "This is not documented in the Case File. I could not find a record line that supports an answer."
AGENT_ORDER = tuple(board.ROLE_DEPARTMENT)   # the six roles in their order (agents.ROLES)
AGENT_VOICE = "af_heart"                      # one voice for every agent (Phase 4 decision 2); the department is named first
POINTS_SHOWN = 5                              # points of the brief shown on the tile and the panel card


def active_roles(s: dict, cid: str | None) -> list[str]:
    """The agents active for a Case File (owner decision D2, night-v3 6.1): by default every head not present and every specialty
    marked absent (board.absent_roles, the Surgical Oncology seat rule included), overridden by the coordinator's additions and
    removals kept in the session (agents_active[case][role] = {on, by, by_name, at}). In the roles' order. Never on a protected file."""
    if not cid or cid in config.PROTECTED_CASES:
        return []
    try:
        default = set(board.absent_roles(s, cid))
    except Exception:
        default = set()
    over = (s.get("agents_active") or {}).get(cid) or {}
    out = []
    for role in AGENT_ORDER:
        o = over.get(role)
        if (bool(o.get("on")) if isinstance(o, dict) else role in default):
            out.append(role)
    return out


def _agent_entry(mid: str, role: str) -> dict | None:
    """The live entry of one agent, or None when there is none or it expired (a closed tab never leaves a false state)."""
    e = (AGENT_STATE.get(mid) or {}).get(role)
    if not e:
        return None
    if e.get("expires") and e["expires"] < time.time():
        AGENT_STATE[mid].pop(role, None)
        return None
    return e


def _audio_playing(mid: str, role: str) -> str | None:
    """The question id of this role's answer that at least one device reports playing now (a report expires AUDIO_TTL after it was
    made; the device renews it while it plays)."""
    now = time.time()
    for qid, a in list((AGENT_AUDIO.get(mid) or {}).items()):
        devs = {u: t for u, t in (a.get("devices") or {}).items() if t > now}
        if devs:
            a["devices"] = devs
            if a.get("role") == role:
                return qid
        else:
            AGENT_AUDIO[mid].pop(qid, None)
    return None


def agent_live_state(s: dict, role: str) -> dict:
    """{state, by, by_name, question, at} of one active agent, true by construction: listening and thinking from the live entry,
    speaking while a device reports playing its answer, answering while its statements are on the screen and nobody plays them, error
    for a minute, preparing from the session's brief status, else ready. After a restart the entries are gone and the state comes
    from the saved session alone."""
    mid, cid = s["id"], s.get("current")
    e = _agent_entry(mid, role) or {}
    st = e.get("state")
    base = {"by": e.get("by"), "by_name": e.get("by_name"), "question": e.get("question"), "at": e.get("at")}
    if st in ("listening", "thinking"):
        return {"state": st, **base}
    playing = _audio_playing(mid, role)
    if playing:
        return {"state": "speaking", **base, "question": e.get("question") or playing}
    if st in ("answering", "error"):
        return {"state": st, **base}
    brief = ((s.get("agents") or {}).get(cid) or {}).get(role) or {}
    if brief.get("status") in ("queued", "running"):
        return {"state": "preparing", "by": None, "by_name": None, "question": None, "at": brief.get("at")}
    return {"state": "ready", "by": None, "by_name": None, "question": None, "at": None}


def _agent_brief(s: dict, cid: str, role: str) -> tuple:
    """The brief of this Case File and role as the tile shows it: ({status, label, at, reviewed_by, message}, the first POINTS_SHOWN
    points for review with their citations, the count of not documented items, the count of points). The session's status wins
    while the brief is being prepared."""
    from . import helpers
    status = (((s.get("agents") or {}).get(cid) or {}).get(role) or {}).get("status")
    try:
        st = store.get_state(cid)
        art = (st.get("artefacts") or {}).get(f"brief_{role}")
        bv = helpers.brief_view(art if isinstance(art, dict) else None, rules.case_signature(cid, st))
    except Exception:
        bv = {"status": "none", "label": "", "at": None, "points_for_review": [], "not_documented": [], "message": ""}
    out = {"status": bv.get("status") or "none", "label": bv.get("label") or "", "at": bv.get("at"), "reviewed_by": bv.get("reviewed_by"), "message": bv.get("message") or ""}
    if status in ("queued", "running"):
        out["status"] = "preparing"
    elif status == "error" and out["status"] == "none":
        out["status"] = "error"
    if bv.get("no_documents"):
        out["status"] = "no_documents"
    pts = []
    for p in (bv.get("points_for_review") or [])[:POINTS_SHOWN]:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        cites = [{"doc_id": c.get("doc_id"), "doc_title": c.get("doc_title"), "date": c.get("date"), "page": c.get("page"), "quote": (c.get("quote") or "")[:400]}
                 for c in (p.get("citations") or [])[:2] if isinstance(c, dict)]
        pts.append({"text": str(p["text"]), "citations": cites})
    return out, pts, len(bv.get("not_documented") or []), len(bv.get("points_for_review") or [])


def agents_view(s: dict) -> list[dict]:
    """Every agent active for the Case File on the floor (owner decision D2, night-v3 5.1 and 6.1): a tile and a panel row, never a
    member and never counted. Each with its true state, why it is here (standing in for a head not present, a specialty marked
    absent, or added by the coordinator), its brief and points, and the voice. Empty outside a session or on a protected Case File."""
    cur = s.get("current")
    if s.get("status") != "in_session" or not cur or cur in config.PROTECTED_CASES:
        return []
    try:
        default = set(board.absent_roles(s, cur))
    except Exception:
        default = set()
    att = board.attendance(s)
    heads = set(board.head_ids())
    over = (s.get("agents_active") or {}).get(cur) or {}
    out = []
    for role in active_roles(s, cur):
        did = board.ROLE_DEPARTMENT.get(role, role)
        dept = org.department_name(did)
        try:
            from . import agents
            label = agents.spec(role)["label"]
        except Exception:
            label = dept
        o = over.get(role) if isinstance(over.get(role), dict) else None
        standing = role in default
        who = (o.get("by_name") or display_name(o.get("by") or "")) if o else ""
        if standing:
            reason = "Head absent" if did in heads and att.get(did) != "absent" else "Marked absent"
            title = f"{dept}, AI agent standing in"
        else:
            reason = f"Added by {who}" if who else "Added by the MDT Coordinator"
            title = f"{dept}, AI agent, called by {who}" if who else f"{dept}, AI agent, called by the MDT Coordinator"
        brief, points, nd, npts = _agent_brief(s, cur, role)
        out.append({"role": role, "label": label, "department": did, "department_name": dept, **agent_live_state(s, role),
                    "standing_in": standing, "added": not standing, "added_by": (o or {}).get("by") if not standing else None,
                    "added_by_name": who if not standing else None, "reason": reason, "title": title, "brief": brief, "points": points,
                    "points_count": npts, "not_documented_count": nd, "voice": AGENT_VOICE, "can_remove": True, "note": AGENT_NOTE})
    return out


def agents_public(ag: list[dict]) -> list[dict]:
    """The agents list for a viewer who is not admitted: without the points (record quotes)."""
    return [{k: v for k, v in a.items() if k != "points"} for a in ag]


def agent_state(s: dict, ag: list[dict] | None = None) -> dict:
    """The single stand-in agent field kept for older readers: the first active agent, with every active role in `roles`."""
    off = {"active": False, "role": None, "label": "", "state": "off", "roles": [], "question": None}
    ag = agents_view(s) if ag is None else ag
    if not ag:
        return off
    a = ag[0]
    return {"active": True, "role": a["role"], "label": a["label"], "state": a["state"], "roles": [x["role"] for x in ag], "question": a.get("question"),
            "note": "AI support: answers from the records only; not a member of the board"}


def _agent_fields(s: dict) -> dict:
    """The two agent fields of an event or the state, computed once."""
    ag = agents_view(s)
    return {"agent": agent_state(s, ag), "agents": ag}


def spotlight_view(s: dict) -> list[str]:
    return [str(u) for u in ((s.get("live") or {}).get("spotlight") or []) if u]


def _chat_lines(s: dict, r: dict | None, lines) -> list[dict]:
    """The chat lines as this viewer may read them: an outside expert without the owner's consent gets the patient's name and numbers
    replaced by [withheld] (strip_identity against the line's Case File, or every Case File on the agenda when the line names none)."""
    if not (isinstance(r, dict) and r.get("outside_expert")):
        return list(lines)
    cases = {}
    for k in LISTS:
        for it in (s.get("agenda_lists") or {}).get(k) or []:
            cid = it.get("case_id")
            if cid and cid not in config.PROTECTED_CASES and cid not in cases:
                cases[cid] = store.get_case(cid)
    out = []
    for m in lines:
        text = m.get("text") or ""
        targets = [cases.get(m.get("case_id"))] if m.get("case_id") in cases else list(cases.values())
        for c in targets:
            if c and outside_view(r, c):
                text = strip_identity(text, c)
        out.append({**m, "text": text})
    return out


def quorum_view(s: dict) -> dict:
    """The quorum line (night-v3 5.4, research/04 section 6.14): each board head present as a person (an admitted member of that department,
    or the department marked present on the attendance sheet), the agents standing in (apart, never counted), and the PM-JAY composition
    (Surgical, Radiation and Medical Oncology present as people; the NHA manual says "advised", so it is information, not a gate)."""
    att = board.attendance(s)
    people = [(u, p) for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED]

    def present(did):
        who = [p.get("name") or display_name(u) for u, p in people if (p.get("department") or "") == did]
        return (True, who[0]) if who else (att.get(did) == "present", None)
    heads = []
    for h in board.heads():
        ok, by = present(h["id"])
        heads.append({"id": h["id"], "name": h["name"], "present": ok, "by": by, "role": h.get("role")})
    agents = []  # the agents standing in for a head or a specialty not here (an agent the coordinator called is not standing in)
    if s.get("status") == "in_session" and s.get("current") and s["current"] not in config.PROTECTED_CASES:
        try:
            absent = set(board.absent_roles(s, s["current"]))
        except Exception:
            absent = set()
        agents = [org.department_name(board.ROLE_DEPARTMENT.get(r, r)) for r in active_roles(s, s["current"]) if r in absent]
    depts = {(p.get("department") or "") for _, p in people} | {d for d, v in att.items() if v == "present"}
    if not org.hospital().get("pmjay_empanelled", True):
        pm = {"not_applicable": True, "present": 0, "total": len(PMJAY_DEPARTMENTS), "note": postboard.NOT_EMPANELLED}
    else:  # the same seat rule as the decision record's composition check (postboard.pmjay_seat: a listed surgeon, or one of the case's own)
        cur = s.get("current")
        c = store.get_case(cur) if cur and cur not in config.PROTECTED_CASES else None
        own = board._case_surgical(c) if c else None
        got = postboard.pmjay_present(depts, own)
        seat = postboard.pmjay_seat(depts, own)
        pm = {did.split("_")[0]: did in got for did in PMJAY_DEPARTMENTS}
        pm.update({"present": len(got), "total": len(PMJAY_DEPARTMENTS), "note": "PM-JAY advises Surgical, Radiation and Medical Oncology",
                   "seat_note": seat.get("note") or "", "seat_check": bool(seat.get("check"))})
    return {"heads": heads, "present": sum(1 for h in heads if h["present"]), "total": len(heads), "agents": agents, "pmjay": pm}


def present_allowed_view(s: dict) -> list[str]:
    return [str(u) for u in (s.get("present_allowed") or []) if u]


def may_present(s: dict, r: dict) -> bool:
    """Who may present a screen (night-v3 5.2): the coordinator, the presenter of the Case File on the floor, and anyone the coordinator
    allowed; always an admitted member."""
    user = r.get("user") or ""
    if manage(r):
        return True
    if not is_member(r, s):
        return False
    if user in present_allowed_view(s):
        return True
    cid = s.get("current")
    c = store.get_case(cid) if cid and cid not in config.PROTECTED_CASES else None
    return bool(c) and presenter_of(c) == user


def _repair_interrupted(s: dict) -> bool:
    """A question to an agent that has no answer task (a restart while it was answering, or waiting in the queue) is marked as
    interrupted once it is older than STUCK_AFTER seconds, so the screen never shows Thinking for ever. Returns True when it saved."""
    changed = False
    now = datetime.now()
    for q in s.get("questions") or []:
        if not q.get("role") or (s["id"], q.get("id")) in _ANSWERING:
            continue
        a = q.get("answer")
        if a is not None and not (isinstance(a, dict) and a.get("status") == "answering"):
            continue
        try:
            age = (now - datetime.fromisoformat(str(q.get("at") or ""))).total_seconds()
        except ValueError:
            age = STUCK_AFTER + 1
        if age < STUCK_AFTER:
            continue
        base = a if isinstance(a, dict) else {"statements": [], "references": [], "role": q["role"], "label": q.get("agent_label") or q["role"], "speech": [], "note": ANSWER_NOTE}
        q["answer"] = {**base, "status": "error", "text": base.get("text") or INTERRUPTED, "message": INTERRUPTED, "at": _now(), "error": "interrupted"}
        q["queued"] = False; q.pop("queue_note", None)
        changed = True
    if changed:
        _save(s)
    return changed


def view(mid: str, r: dict) -> dict:
    """The GET /meetings/{mid} payload (also the first WebSocket message). A viewer who is not admitted (waiting, or a department on the
    attendance sheet that did not join) sees the agenda with initials for the Case Files it may not read in full, and none of the live
    content (the record or images opened, the questions, the live decision); the decision text of an outcome only for the Case Files
    it may read in full (as in the old room, Phase 6 review S2)."""
    s = need(mid)
    _repair_interrupted(s)
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
    af = _agent_fields(s)
    if not member:
        af["agents"] = agents_public(af["agents"])  # no record quotes for a viewer who is not admitted
    return {"meeting": summary_row(s), "agenda": agenda,
            "code": {"value": code["value"], "expires_at": code.get("expires_at"), "attempts": code.get("attempts", 0)} if code else None,
            "attendance": attendance_rows(s), "current": cv, "decision_live": dl, "questions": list(s.get("questions") or []) if member else [],
            "hands": list(s.get("hands") or []), **af, "spotlight": spotlight_view(s),
            "quorum": quorum_view(s), "present_allowed": present_allowed_view(s), "presenting": (s.get("live") or {}).get("presenting") or None,
            "chat": _chat_lines(s, r, list(s.get("chat") or [])[-CHAT_VIEW:]) if member else [],
            "can": {"manage": manage(r), "record": org.can(r, "board_record"), "ask": member and bool(cur),
                    "ask_agents": member and bool(cur) and (manage(r) or bool(s.get("agents_ask", True))), "members_ask": bool(s.get("agents_ask", True)),
                    "card": member and bool(cur), "card_required": user in card_holders(s),
                    "video": bool(s.get("video")) and member, "member": member,
                    "present": member and s.get("status") == "in_session" and may_present(s, r), "chat": member and s.get("status") in ("planned", "in_session")},
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
    _send(s, {"type": "presence", "attendance": attendance_rows(s), "online": live.online(s["id"]), "joined": user, "quorum": quorum_view(s), "agents": agents_view(s)})
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
    _send(s, {"type": "admit", "user": user, "status": p["status"], "attendance": rows, **_agent_fields(s), "quorum": quorum_view(s)})
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
    _send(s, {"type": "presence", "attendance": rows, "online": live.online(mid), "quorum": quorum_view(s), "agents": agents_view(s)})
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
    s["live"] = {"slide": 0, "opened": None, "timer": _fresh_timer(s, s.get("current")) if s.get("current") else None, "case_started_at": time.time()}
    _save(s)
    pairs = []
    try:
        from . import service
        pairs = service.prepare_session_agents(mid, by) or []
    except Exception as e:  # the briefs are support; the meeting starts without them
        log.warning("meeting %s: briefs not prepared (%s)", mid, e)
    board.audit_event(mid, "meeting_started", by, preparing=len(pairs), warming=_warm_agents(s))
    _send(s, {"type": "current", **current_view(s), **_agent_fields(s), "quorum": quorum_view(s), "spotlight": [], "status": "in_session"})
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
    AGENT_AUDIO.pop(mid, None)
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
        s["live"] = {"slide": 0, "opened": None, "timer": _fresh_timer(s, case_id), "case_started_at": time.time()}
        LIVE_DECISION.pop(mid, None)
        AGENT_STATE.pop(mid, None)
        AGENT_AUDIO.pop(mid, None)
        changed_case = True
    if slide is not None:
        try:
            s.setdefault("live", {})["slide"] = max(0, int(slide))
        except (TypeError, ValueError):
            raise MeetingError("The slide must be a number.", 400, "bad_slide")
    _save(s)
    if changed_case:
        _warm_agents(s)
    else:
        board.audit_event(mid, "slide", by, case_id=s.get("current"), slide=s.get("live", {}).get("slide"))
    cv = current_view(s)
    ev = {"type": "current", **cv, **_agent_fields(s), "quorum": quorum_view(s)}
    if changed_case:
        ev["spotlight"] = []  # a spotlight is for one case: the next case clears it
    _send(s, ev)
    return {**cv, **_agent_fields(s)}


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
        if mins and mins * 60 != int(t.get("total") or 0):  # the coordinator changed the minutes; the same minutes resume a paused countdown
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


# ---- questions, the agents, hands, the live decision ----------------------------------------------------------------------------------------

def _question(s: dict, qid: str) -> dict | None:
    return next((x for x in s.get("questions") or [] if isinstance(x, dict) and x.get("id") == qid), None)


def _announce(mid: str, role: str) -> dict:
    """Broadcast one agent's true state (agent_live_state) as an agent_state event, per role."""
    s = get(mid)
    if not s:
        return {}
    st = agent_live_state(s, role)
    live.broadcast(mid, {"type": "agent_state", "role": role, **st, "agent": {"active": True, "role": role, **st}})
    return st


def _set_agent(mid: str, role: str, state: str, by: str | None = None, question: str | None = None, ttl: float | None = None) -> dict:
    """One agent's live entry (per role, never per meeting; `ready` clears it) and the agent_state event with the state as it is
    computed (speaking wins over ready while a device still plays)."""
    if state == "ready":
        (AGENT_STATE.get(mid) or {}).pop(role, None)
    else:
        AGENT_STATE.setdefault(mid, {})[role] = {"state": state, "by": by, "by_name": display_name(by) if by else None, "question": question,
                                                 "at": _now(), "since": time.time(), "expires": (time.time() + ttl) if ttl else None}
    return _announce(mid, role)


def _stop_audio(s: dict, role: str, qid: str | None, by: str) -> None:
    if qid:
        (AGENT_AUDIO.get(s["id"]) or {}).pop(qid, None)
    _send(s, {"type": "agent_stop", "role": role, "question": qid, "by": by})


def _warm_agents(s: dict, roles: list | None = None) -> int:
    """Pre-load each active agent's context when a Case File comes on the floor, or an agent is added (night-v3 6.4): background tasks
    on the running loop (agents.warm), never awaited, nothing when there is no loop (tests) or no Case File."""
    cid = s.get("current")
    if not cid or cid in config.PROTECTED_CASES:
        return 0
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return 0
    from . import agents
    n = 0
    for role in (roles if roles is not None else active_roles(s, cid)):
        t = loop.create_task(agents.warm(cid, role))
        _TASKS.add(t); t.add_done_callback(_TASKS.discard)
        n += 1
    return n


def set_agent(mid: str, by: str, role: str, on: bool) -> list[dict]:
    """The coordinator adds an agent to the meeting for the Case File on the floor or removes one (D2: any of the six; Radiation
    Oncology and Nuclear Medicine always on offer). Kept in the session (agents_active), audited by ids; adding starts the brief when
    none stands (service.prepare_session_agents); removing clears its live state and stops its voice everywhere. The quorum never
    counts an agent (quorum_view lists them apart)."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if not cid:
        raise MeetingError("No Case File is on the floor.", 409, "no_current")
    if role not in board.ROLE_DEPARTMENT:
        raise MeetingError("Unknown agent.", 404, "unknown_role")
    on = bool(on)
    was = role in active_roles(s, cid)
    try:
        default = set(board.absent_roles(s, cid))
    except Exception:
        default = set()
    if on and role in default and not isinstance((s.get("agents_active") or {}).get(cid, {}).get(role), dict):
        return agents_view(s)  # already standing in by itself: nothing to add, and it steps back when its head arrives
    s.setdefault("agents_active", {}).setdefault(cid, {})[role] = {"on": on, "by": by, "by_name": display_name(by), "at": _now()}
    if not on:
        for q in s.get("questions") or []:  # its answer in flight (or waiting) stops here; the task ends it as not_listed
            if q.get("role") == role and q.get("case_id") == cid and (q.get("answer") is None or (isinstance(q.get("answer"), dict) and q["answer"].get("status") == "answering")):
                if isinstance(q.get("answer"), dict):
                    q["answer"]["stopped_by"] = by
    _save(s)
    board.audit_event(mid, "agent_added" if on else "agent_removed", by, case_id=cid, role=role)
    if on and not was:
        try:
            from . import service
            service.prepare_session_agents(mid, by, roles=[role], case_ids=[cid])
        except Exception as e:  # the brief is support; the agent is in the meeting without it
            log.warning("meeting %s: brief for %s not prepared (%s)", mid, role, e)
        _warm_agents(s, [role])
    if not on:
        e = (AGENT_STATE.get(mid) or {}).pop(role, None) or {}
        _stop_audio(s, role, e.get("question") or _audio_playing(mid, role), by)
    s = need(mid)
    ag = agents_view(s)
    _send(s, {"type": "agents", "agents": ag, "members_ask": bool(s.get("agents_ask", True))})
    return ag


def set_agents_settings(mid: str, by: str, members_ask) -> dict:
    """The coordinator's switch "Members can ask the agents" (kept in the session; the coordinator always may)."""
    s = need(mid); _active(s)
    s["agents_ask"] = bool(members_ask)
    _save(s)
    board.audit_event(mid, "agents_settings", by, members_ask=s["agents_ask"])
    _send(s, {"type": "agents", "agents": agents_view(s), "members_ask": s["agents_ask"]})
    return {"members_ask": s["agents_ask"]}


def _members_may_ask(s: dict, manager: bool) -> None:
    if not manager and not s.get("agents_ask", True):
        raise MeetingError("The MDT Coordinator has closed questions to the agents for now.", 403, "agents_ask_off")


def set_listening(mid: str, user: str, role: str, on: bool, manager: bool = False) -> dict:
    """A member's device records a question for this agent (on), or stopped (off): the only trigger of "listening", shown with the
    asker's name and expiring after LISTEN_TTL so a closed tab never leaves it on. Not while the agent thinks or answers, nor while
    it listens to someone else (the device still records; the tile keeps its true word). Audited as seconds: never audio or words."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if role not in active_roles(s, cid):
        raise MeetingError("That agent is not in this meeting. The coordinator can add it.", 409, "agent_not_in_meeting")
    if on:
        _members_may_ask(s, manager)
    e = _agent_entry(mid, role) or {}
    if on:
        if e.get("state") in ("thinking", "answering") or (e.get("state") == "listening" and e.get("by") != user):
            return {"role": role, **agent_live_state(s, role), "accepted": False}
        st = _set_agent(mid, role, "listening", by=user, ttl=LISTEN_TTL)
        board.audit_event(mid, "agent_listening", user, case_id=cid, role=role, on=True)
        return {"role": role, **st, "accepted": True}
    if e.get("state") == "listening" and e.get("by") == user:
        st = _set_agent(mid, role, "ready")
        board.audit_event(mid, "agent_listening", user, case_id=cid, role=role, on=False, seconds=round(time.time() - (e.get("since") or time.time()), 1))
        return {"role": role, **st, "accepted": True}
    return {"role": role, **agent_live_state(s, role), "accepted": True}


def agent_audio(mid: str, user: str, qid: str, playing: bool, device: str = "") -> dict:
    """A device reports that it plays (or stopped playing) an answer: "speaking" is true only while at least one device reports it
    (a report expires after AUDIO_TTL; the device renews it while it plays). The state event goes out when the word changes."""
    s = need(mid); _active(s)
    q = _question(s, qid)
    if not q or not q.get("role"):
        raise MeetingError("Unknown question.", 404, "unknown_question")
    role = q["role"]
    before = agent_live_state(s, role)["state"]
    a = AGENT_AUDIO.setdefault(mid, {}).setdefault(qid, {"role": role, "devices": {}})
    key = f"{user}:{str(device)[:24]}" if device else user  # one login may run two screens (the control view and the room screen)
    if playing:
        a["devices"][key] = time.time() + AUDIO_TTL
    else:
        a["devices"].pop(key, None)
    after = agent_live_state(s, role)
    if after["state"] != before:
        _announce(mid, role)
    return {"role": role, **after}


def stop_agent(mid: str, user: str, role: str, qid: str | None = None, manager: bool = False) -> dict:
    """Stops the agent's voice for everyone (agent_stop): the coordinator, or the person who asked the question. The text stays; no
    further sentence event goes out for that answer."""
    s = need(mid); _in_session(s)
    e = _agent_entry(mid, role) or {}
    qid = qid or e.get("question") or _audio_playing(mid, role)
    q = _question(s, qid) if qid else None
    if not manager and not (q and q.get("by") == user):
        raise MeetingError("Only the MDT Coordinator or the person who asked can stop this answer for everyone.", 403, "not_allowed")
    if q and isinstance(q.get("answer"), dict):
        q["answer"]["stopped_by"] = user
        _save(s)
    _stop_audio(s, role, qid, user)
    board.audit_event(mid, "agent_stop", user, case_id=s.get("current"), role=role, question_id=qid)
    return {**_announce(mid, role), "role": role, "question": qid}


def ask(mid: str, user: str, text: str, role: str | None = None, manager: bool = False) -> dict:
    """A member or the coordinator types a question: to the board (no role: it appears on the shared screen for the people to answer),
    or to one agent of this meeting (`role`: an agent active for the Case File on the floor, else 409; members only while the
    coordinator's "Members can ask the agents" is on). One answer at a time per agent: a later question waits as `queued`. Audited."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if not cid:
        raise MeetingError("No Case File is on the floor.", 409, "no_current")
    text = " ".join(str(text or "").split())[:MAX_QUESTION]
    if not text:
        raise MeetingError("Type a question.", 400, "empty")
    role = str(role or "").strip() or None
    if role:
        if role not in active_roles(s, cid):
            raise MeetingError("That agent is not in this meeting. The coordinator can add it.", 409, "agent_not_in_meeting")
        if not manager and not s.get("agents_ask", True):
            raise MeetingError("The MDT Coordinator has closed questions to the agents for now.", 403, "agents_ask_off")
    q = {"id": "Q" + uuid.uuid4().hex[:6], "by": user, "by_name": display_name(user), "text": text, "at": _now(), "case_id": cid, "answer": None, "role": role, "queued": False}
    if role:
        dept = org.department_name(board.ROLE_DEPARTMENT.get(role, role))
        try:
            from . import agents
            q["agent_label"] = agents.spec(role)["label"]
        except Exception:
            q["agent_label"] = dept
        e = _agent_entry(mid, role) or {}
        lock = AGENT_LOCKS.get((mid, role))
        if (lock is not None and lock.locked()) or e.get("state") in ("thinking", "answering"):
            q["queued"] = True
            q["queue_note"] = f"{dept} is answering {e.get('by_name') or 'someone'}. Yours is next."
    s.setdefault("questions", []).append(q)
    _save(s)
    board.audit_event(mid, "question", user, case_id=cid, question=text[:300], role=role)
    _send(s, {"type": "question", "question": q})
    return q


def _thread_entry(s: dict, cid: str, role: str, asker: str, text: str, a: dict, status: str) -> dict:
    """The exchange as the Case File's shared thread keeps it (helpers.record_exchange), with the meeting as its source."""
    return {"id": "H" + uuid.uuid4().hex[:8], "role": role, "by": asker, "by_name": display_name(asker), "at": store.now_iso(), "question": text,
            "status": status, "statements": list(a.get("statements") or []), "references": list(a.get("references") or []), "message": a.get("message") or "",
            "seconds": a.get("seconds"), "dropped_unverified": a.get("dropped_unverified", 0), "category": a.get("category"),
            "signature": rules.case_signature(cid)["hash"], "model": a.get("model") or "", "source": f"meeting:{s['id']}", "meeting_date": s.get("date")}


def _record_exchange(s: dict, cid: str, role: str, asker: str, text: str, a: dict, status: str) -> None:
    try:
        from . import helpers
        if hasattr(helpers, "record_exchange"):
            helpers.record_exchange(cid, role, _thread_entry(s, cid, role, asker, text, a, status), source=f"meeting:{s['id']}")
    except Exception as e:
        log.info("meeting %s: exchange not kept on the Case File thread (%s)", s["id"], e)


def _speech_events(s: dict, role: str, qid: str, speech: list, sent: int, final: bool = False) -> int:
    """Sends agent_speech for the sentences not yet announced (the devices fetch each by reference); none once the answer was stopped;
    `final` marks the last sentence of a complete answer."""
    q = _question(s, qid)
    if q and isinstance(q.get("answer"), dict) and q["answer"].get("stopped_by"):
        return len(speech)
    for i in range(sent, len(speech)):
        _send(s, {"type": "agent_speech", "role": role, "question": qid, "index": i, "final": bool(final and i == len(speech) - 1)})
    return len(speech)


class _AgentLeft(Exception):
    """The agent was removed from the meeting, or the case moved on, while it was answering."""


AGENT_LEFT = "The agent left this meeting before answering."
STALE_BRIEF = "The records changed since this brief was prepared; prepare it again for the current records."
INTERRUPTED = "Interrupted (the app restarted while the agent was answering). Ask again."
STUCK_AFTER = 120  # seconds: an agent question with no answer task this old was interrupted by a restart


async def answer(mid: str, qid: str, user: str = "") -> dict | None:
    """One agent answers one question from the records (agents.ask: the scope check first, verified quotes only, the output guard),
    one question at a time per agent, its states true: thinking until the first verified statement, answering as the statements
    reach the screen (speaking while a device plays them), ready at the end. The answer fills statement by statement in the question
    record (saved, sent as `question`) and every sentence is announced as `agent_speech` for the devices to fetch by reference.
    Kept in the session's agent log (board.log_answer) and on the Case File's shared thread (helpers.record_exchange)."""
    s = need(mid)
    q = _question(s, qid)
    if not q or not q.get("role"):
        return None
    if q.get("answer") is not None or (mid, qid) in _ANSWERING:  # one answer per question, even when asked to answer twice
        return q.get("answer")
    _ANSWERING.add((mid, qid))
    role, cid, text, asker = q["role"], q.get("case_id"), q.get("text") or "", user or q.get("by") or ""
    dept = org.department_name(board.ROLE_DEPARTMENT.get(role, role))
    lock = AGENT_LOCKS.setdefault((mid, role), asyncio.Lock())
    partial = {"status": "answering", "text": "", "statements": [], "references": [], "role": role, "label": q.get("agent_label") or role, "model": None,
               "at": _now(), "speech": [], "note": ANSWER_NOTE}
    spoken = 0
    out = None
    t0 = time.time()
    try:
        async with lock:
            s = need(mid)
            q = _question(s, qid)
            if q is None or q.get("role") != role:
                return None
            if q.get("queued"):
                q["queued"] = False; q.pop("queue_note", None); _save(s); _send(s, {"type": "question", "question": q})
            _set_agent(mid, role, "thinking", by=asker, question=qid)
            from . import agents, helpers
            history = helpers.history_for(cid, role, 3) if hasattr(helpers, "history_for") else None

            async def on_statement(stmt, index=None):
                nonlocal spoken
                s2 = need(mid)
                q2 = _question(s2, qid)
                if q2 is None:
                    return
                if s2.get("current") != cid or role not in active_roles(s2, cid):
                    raise _AgentLeft()  # removed by the coordinator, or the case moved on: no more statements, no more speech
                prev = q2.get("answer") if isinstance(q2.get("answer"), dict) else {}
                if prev.get("stopped_by"):
                    partial["stopped_by"] = prev["stopped_by"]  # a Stop for everyone during the stream holds
                if not partial["statements"]:
                    partial["speech"].append(f"AI agent, {dept}.")
                    partial["first_seconds"] = round(time.time() - t0, 1)
                partial["statements"].append(stmt)
                partial["speech"].append(str(stmt.get("text") or ""))
                partial["text"] = " ".join(x.get("text", "") for x in partial["statements"])
                q2["answer"] = dict(partial)
                _save(s2)
                if len(partial["statements"]) == 1:
                    _set_agent(mid, role, "answering", by=asker, question=qid)
                _send(s2, {"type": "question", "question": q2})
                spoken = _speech_events(s2, role, qid, partial["speech"], spoken)

            if s.get("current") != cid or role not in active_roles(s, cid):
                raise _AgentLeft()  # queued behind an earlier answer and the agent left meanwhile
            a = await agents.ask(cid, role, text, history, asker, on_statement=on_statement)
            stmts = list(a.get("statements") or [])
            if stmts and not partial["statements"]:  # an answer that came whole (no stream): the same steps, at once
                for i, st_ in enumerate(stmts):
                    await on_statement(st_, i)
            status = a.get("status") or ("answered" if stmts else "not_documented")
            speech = list(partial["speech"])
            if not stmts:
                speech = [f"AI agent, {dept}.", NOT_DOCUMENTED_SPOKEN if status == "not_documented" else str(a.get("message") or "")]
            elif any(x.get("citations") for x in stmts) or a.get("references"):
                speech.append("Sources are on the screen.")
            out = {**partial, "status": status, "text": " ".join(x.get("text", "") for x in stmts) or str(a.get("message") or ""), "statements": stmts,
                   "references": list(a.get("references") or []), "label": a.get("label") or partial["label"], "model": a.get("model"), "at": _now(),
                   "seconds": a.get("seconds"), "first_seconds": partial["first_seconds"] if partial.get("first_seconds") is not None else a.get("first_seconds"), "speech": speech,
                   "message": a.get("message") or "", "category": a.get("category"), "kind": a.get("kind"), "note": ANSWER_NOTE}
            try:
                board.log_answer(mid, cid, role, text, a, by=asker)
            except ValueError as e:
                log.info("meeting %s: answer not logged (%s)", mid, e)
            _record_exchange(need(mid), cid, role, asker, text, a, status)
    except _AgentLeft:
        out = {**partial, "status": "not_listed", "text": partial["text"] or AGENT_LEFT, "message": AGENT_LEFT, "statements": list(partial["statements"]),
               "references": [], "at": _now(), "speech": list(partial["speech"]), "stopped_by": partial.get("stopped_by") or "system"}
    except Exception as e:
        log.exception("meeting %s: the %s agent could not answer", mid, role)
        out = {**partial, "status": "error", "text": partial["text"] or f"The agent could not answer ({e.__class__.__name__}). Try again.",
               "statements": list(partial["statements"]), "references": [], "at": _now(), "speech": list(partial["speech"]), "error": e.__class__.__name__}
    finally:
        try:
            s = need(mid)
            q2 = _question(s, qid)
            if q2 is not None and out is not None:
                if isinstance(q2.get("answer"), dict) and q2["answer"].get("stopped_by"):
                    out["stopped_by"] = q2["answer"]["stopped_by"]
                q2["answer"] = out
                _save(s)
                board.audit_event(mid, "question_answered", "system", case_id=cid, question_id=qid, role=role, status=out.get("status"),
                                  statements=len(out.get("statements") or []), seconds=out.get("seconds"), first_seconds=out.get("first_seconds"))
                _send(s, {"type": "question", "question": q2})
                if out.get("status") not in ("error", "not_listed"):
                    _speech_events(s, role, qid, out.get("speech") or [], spoken, final=True)
        except Exception:
            log.exception("meeting %s: could not store the answer", mid)
        _ANSWERING.discard((mid, qid))
        if out is not None and out.get("status") == "error":
            _set_agent(mid, role, "error", by=asker, question=qid, ttl=ERROR_TTL)
        else:
            _set_agent(mid, role, "ready")
    return out


def present_points(mid: str, user: str, role: str, manager: bool = False) -> dict:
    """"Present your points" (night-v3 6.2): the agent presents a short summary of its brief for the Case File on the floor: the brief's
    points for review as statements with their citations, built by code (no model call), saved as a question "Present your points"
    with its answer, logged and announced like any answer, spoken sentence by sentence on the devices with agent voices on."""
    s = need(mid); _in_session(s)
    cid = s.get("current")
    if role not in active_roles(s, cid):
        raise MeetingError("That agent is not in this meeting. The coordinator can add it.", 409, "agent_not_in_meeting")
    _members_may_ask(s, manager)
    brief, _pts, nd, npts = _agent_brief(s, cid, role)
    if brief["status"] == "preparing":
        raise MeetingError("The brief is still being prepared from the records. Try again in a moment.", 409, "brief_preparing")
    dept = org.department_name(board.ROLE_DEPARTMENT.get(role, role))
    try:
        from . import agents
        label = agents.spec(role)["label"]
    except Exception:
        label = dept
    art = (store.get_state(cid).get("artefacts") or {}).get(f"brief_{role}")
    art = art if isinstance(art, dict) else {}
    stmts = [{"text": str(p["text"]), "citations": list(p.get("citations") or []), "references": list(p.get("references") or [])}
             for p in (art.get("points_for_review") or []) if isinstance(p, dict) and p.get("text")]
    speech = [f"AI agent, {dept}."]
    stale = brief["status"] == "stale"
    if stale:
        speech.append(STALE_BRIEF)  # said first, on the screen as the answer's first line
    if stmts:
        status, message = "answered", ""
        speech += [x["text"] for x in stmts]
        if nd:
            speech.append(f"{nd} item{'s are' if nd != 1 else ' is'} listed as not documented; the list is on the screen.")
        speech.append("Sources are on the screen.")
    elif brief["status"] == "no_documents":
        status, message = "not_documented", brief.get("message") or f"No {dept} reports in this Case File."
        speech.append(message)
    elif brief["status"] in ("none", "error"):
        status, message = "not_documented", "No brief has been prepared from the records yet."
        speech.append(message)
    else:
        status, message = "not_documented", "The brief lists no points for review."
        speech.append(message)
    q = {"id": "Q" + uuid.uuid4().hex[:6], "by": user, "by_name": display_name(user), "text": "Present your points", "at": _now(), "case_id": cid, "role": role,
         "agent_label": label, "kind": "present_points", "queued": False}
    a = {"status": status, "statements": stmts, "references": [], "message": message, "label": label, "model": art.get("model") or "", "removed": [],
         "seconds": 0.0, "kind": "present_points", "not_documented": list(art.get("not_documented") or [])}
    q["answer"] = {"status": status, "text": " ".join(x["text"] for x in stmts) or message, "statements": stmts, "references": [], "role": role, "label": label,
                   "model": a["model"], "at": _now(), "seconds": 0.0, "first_seconds": 0.0, "speech": speech, "message": message, "kind": "present_points",
                   "not_documented": a["not_documented"], "brief_label": brief.get("label") or "", "note": ANSWER_NOTE, "stale": stale,
                   "stale_note": STALE_BRIEF if stale else ""}
    s.setdefault("questions", []).append(q)
    _save(s)
    board.audit_event(mid, "present_points", user, case_id=cid, role=role, question_id=q["id"], status=status, statements=len(stmts))
    try:
        board.log_answer(mid, cid, role, "Present your points", a, by=user)
    except ValueError as e:
        log.info("meeting %s: points not logged (%s)", mid, e)
    _record_exchange(s, cid, role, user, "Present your points", a, status)
    _send(s, {"type": "question", "question": q})
    _speech_events(s, role, q["id"], speech, 0, final=True)
    return q


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


def spotlight(mid: str, by: str, users) -> list[str]:
    """Spotlight for everyone (night-v3 5.1, like Zoom's and Teams' "Spotlight for everyone"): the coordinator puts up to SPOTLIGHT_MAX
    admitted people large on every screen; an empty list removes it. Kept on the meeting (live.spotlight) so a reload shows it; cleared
    when the case changes. Audited by user ids (no content). A person's own pin wins on their screen (client side)."""
    s = need(mid); _in_session(s)
    people = s.get("people") or {}
    out: list[str] = []
    for u in users or []:
        u = str(u or "").strip()
        if not u or u in out:
            continue
        if (people.get(u) or {}).get("status") not in ADMITTED:
            raise MeetingError(f"{display_name(u)} is not in the meeting.", 409, "not_in_meeting")
        out.append(u)
    if len(out) > SPOTLIGHT_MAX:
        raise MeetingError(f"At most {SPOTLIGHT_MAX} people can be in the spotlight.", 400, "too_many")
    s.setdefault("live", {})["spotlight"] = out
    _save(s)
    board.audit_event(mid, "spotlight", by, users=out)
    _send(s, {"type": "spotlight", "users": out, "by": by})
    return out


def react(mid: str, user: str, kind: str) -> dict:
    """A reaction (agree, thanks, applause, question) from an admitted member: broadcast for a moment on the person's tile, never stored in
    the meeting record; one every REACTION_GAP seconds per person; audited as who and when, not which."""
    s = need(mid); _in_session(s)
    kind = str(kind or "").strip().lower()
    if kind not in REACTIONS:
        raise MeetingError("Pick one of the four reactions.", 400, "bad_kind")
    now = time.time()
    if now - _REACTED.get((mid, user), 0.0) < REACTION_GAP:
        raise MeetingError("One reaction every 2 seconds.", 429, "too_fast")
    _REACTED[(mid, user)] = now
    board.audit_event(mid, "reaction", user)
    ev = {"type": "reaction", "user": user, "name": display_name(user), "kind": kind, "at": _now()}
    _send(s, ev)
    return {"user": user, "kind": kind, "at": ev["at"]}


def present_allow(mid: str, by: str, user: str, allowed: bool) -> list[str]:
    """The coordinator allows (or withdraws) a member's right to present a screen (night-v3 5.2); kept on the meeting for its length.
    Audited by ids."""
    s = need(mid); _active(s)
    user = str(user or "").strip()
    if ((s.get("people") or {}).get(user) or {}).get("status") not in ADMITTED:
        raise MeetingError(f"{display_name(user)} is not in the meeting.", 409, "not_in_meeting")
    cur = [u for u in present_allowed_view(s) if u != user]
    if allowed:
        cur.append(user)
    s["present_allowed"] = cur
    lv = s.get("live") or {}
    stopped = False
    if not allowed and lv.get("presenting") == user and not manage(org.roles(user)):
        lv["presenting"] = None  # a withdrawn right ends the share on every screen
        stopped = True
    _save(s)
    board.audit_event(mid, "present_allowed", by, user=user, allowed=bool(allowed))
    _send(s, {"type": "present_allowed", "users": cur, "by": by})
    if stopped:
        _send(s, {"type": "presenting", "user": user, "name": display_name(user), "on": False, "by": by})
    return cur


def set_presenting(mid: str, user: str, r: dict, on: bool) -> dict:
    """Who shares a screen now (night-v3 5.2): LiveKit carries the pixels, the app records who and whether it is allowed. Starting needs
    may_present; a new share replaces the earlier one (as Google Meet does); stopping is for the sharer or the coordinator. Audited."""
    s = need(mid); _in_session(s)
    lv = s.setdefault("live", {})
    before = lv.get("presenting") or None
    if on:
        if not may_present(s, r):
            raise MeetingError("Only the MDT Coordinator, the presenter of this Case File, or someone the coordinator allowed can present a screen.", 403, "not_allowed")
        lv["presenting"] = user
    else:
        if before and before != user and not manage(r):
            raise MeetingError("Only the person presenting or the MDT Coordinator can stop a share.", 403, "not_yours")
        lv["presenting"] = None
    _save(s)
    board.audit_event(mid, "presenting", user, on=bool(on), replaced=before if on and before and before != user else None)
    if on and before and before != user:
        _send(s, {"type": "presenting", "user": before, "name": display_name(before), "on": False, "by": user, "replaced": True})
    who = user if on else (before or user)
    _send(s, {"type": "presenting", "user": who, "name": display_name(who), "on": bool(on), "by": user})
    return {"presenting": lv.get("presenting"), "replaced": before if on and before and before != user else None}


def chat(mid: str, user: str, text: str) -> dict:
    """A meeting chat line from an admitted member (night-v3 5.3): kept with the meeting record (the session file), apart from the
    questions to the board and the agents; sent only to the admitted members; at most MAX_CHAT characters and CHAT_PER_MINUTE lines a
    minute per person; audited without the words (a line may carry patient details). Never pushed as a notification."""
    s = need(mid); _active(s)
    text = str(text or "").strip()
    if not text:
        raise MeetingError("Type a message.", 400, "empty")
    if len(text) > MAX_CHAT:
        raise MeetingError(f"A message can have at most {MAX_CHAT} characters.", 413, "too_long")
    now = time.time()
    recent = [x for x in _CHATTED.get((mid, user), []) if now - x < 60]
    if len(recent) >= CHAT_PER_MINUTE:
        raise MeetingError("Too many messages in a minute.", 429, "too_many")
    _CHATTED[(mid, user)] = recent + [now]
    m = {"id": "C" + uuid.uuid4().hex[:6], "by": user, "by_name": display_name(user), "text": text, "at": _now(), "case_id": s.get("current")}
    s.setdefault("chat", []).append(m)
    _save(s)
    board.audit_event(mid, "chat", user, chars=len(text))
    _send(s, {"type": "chat", "message": m})
    return m


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
    if cid in (s.get("outcomes") or {}) or (mid, cid) in _RECORDING:  # the form saved twice would make a second round (Phase 3 review S2)
        raise MeetingError(ALREADY_RECORDED, 409, "already_recorded")
    _RECORDING.add((mid, cid))
    try:
        return await _record_decision(s, mid, cid, c, body, user)
    finally:
        _RECORDING.discard((mid, cid))


ALREADY_RECORDED = ("The outcome of this Case File is recorded for this meeting. To change the fields, correct the record from the Case File's "
                    "Board decisions panel. A different outcome is recorded at the next meeting.")
_RECORDING: set = set()  # (meeting, Case File) whose outcome is being saved now: a second save waits for nothing and is refused


async def _record_decision(s, mid, cid, c, body, user) -> dict:
    outcome = str(body.get("outcome") or "decision").strip()
    if outcome not in OUTCOMES:
        raise MeetingError(f"The outcome must be one of: {', '.join(OUTCOMES)}.", 400, "bad_outcome")
    try:  # the coordinator's form (night-v3 item 3.1): every field checked, the required-by-outcome rule, over-limit text refused
        clean = decision_record.clean({**body, "outcome": outcome}, strict=True)
    except ValueError as e:
        raise MeetingError(str(e), 400, "bad_record")
    problem = postboard.informed_date_problem({**clean, "board_date": s.get("date")})
    if problem:
        raise MeetingError(problem, 400, "bad_record")
    text, awaited, awaited_from, referred_to = clean["decision_text"], clean["awaited"], clean["awaited_from"], clean["referred_to"]
    nxt = board.next_planned_after(s) if outcome == "not_discussed" else None
    if not text:
        text = {"deferred": f"Deferred: awaiting {awaited}" + (f" from {awaited_from}" if awaited_from else ""),
                "referred": f"Referred to {referred_to}", "noted": "Noted for information; no decision taken",
                "not_discussed": "Not discussed" + (f": moved to the meeting on {_dmy(nxt.get('date'))}" if nxt else "; no later meeting planned yet")
                + (f" ({decision_record.choice_label('not_discussed_reason', clean['not_discussed_reason']).lower()})" if clean["not_discussed_reason"] else "")}.get(outcome, text)
    concerns = list(clean["concerns"])
    have = {x["text"] for x in concerns}
    concerns += [x for x in _card_concerns(s, cid) if x["text"] not in have]
    members = clean["members_present"] or [p.get("name") or u for u, p in (s.get("people") or {}).items() if p.get("status") in ADMITTED]
    part = board.participants(s)
    actions = []
    did = org.department_id(awaited_from) if awaited_from else None
    if outcome == "deferred" and awaited and did:
        actions.append({"task": f"Awaited by the board: {awaited}", "department": org.department_name(did), "due": clean["next_step_date"] or (date.today() + timedelta(days=14)).isoformat()})
    rec = {**clean, "decision_text": text, "outcome_type": outcome, "meeting_outcome": outcome,
           "concerns": concerns, "divergent_opinions": decision_record.join_concerns(concerns),
           "members_present": members, "participants": ", ".join(members) or part["text"], "board_date": s.get("date"), "session": mid,
           "attendance": {"present": part["present"], "absent": part["absent"], "members": part["members"]}, "actions": actions, "recorded_by": display_name(user),
           "quorum": quorum_view(s)}  # heads present as people, agents standing in (apart), the PM-JAY composition (night-v3 5.4)
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
    lv = s.get("live") or {}
    s.setdefault("ended", {})[cid] = {"at": _now(), "by": by, "elapsed_seconds": _elapsed(lv) if s.get("current") == cid else None}
    if isinstance(lv.get("timer"), dict) and lv["timer"].get("running"):
        t = lv["timer"]
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
