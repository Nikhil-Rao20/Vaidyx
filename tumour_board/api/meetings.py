"""Meeting routes (B3): the contract in docs/ui/build/SPEC-API.md (meetings.py). The MDT Coordinator manages (org action "session"),
the members are the people the coordinator admitted, the owner's team of a Case File reads its cards; every change is audited by
meetings.py. Also GET /scheduler/status for the root admin and the Vaidyx admin."""
from fastapi import Request

from . import common
from .. import access, board, config, decision_record, meetings, org, scheduler, store

router = common.make_router(["tumour-board-meetings"])
JOIN_LIMIT = common.RateLimit(5, 15 * 60)


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except meetings.MeetingError as e:
        common.fail(e.status, str(e), e.code)
    except ValueError as e:
        common.fail(400, str(e), "invalid")


async def _acall(coro):
    try:
        return await coro
    except meetings.MeetingError as e:
        common.fail(e.status, str(e), e.code)
    except ValueError as e:
        common.fail(400, str(e), "invalid")


def _who(request: Request, guest: bool = False):
    """The user and its roles; a placed account, the coordinator or the admin (need_known). With guest=True an outside expert (a guest
    of a board meeting, no placement, org.py) passes too: the list, join, the meeting page, the slides, presence and the raised hand."""
    scheduler.attach_loop()  # the scheduler runs its jobs on this loop
    rl = common.roles(request)
    if not (guest and rl.get("outside_expert") and not rl.get("disabled")):
        common.need_known(rl)
    return common.user(request), rl


def _meeting(mid: str) -> dict:
    s = meetings.get(mid)
    if not s:
        common.fail(404, "Meeting not found.", "not_found")
    return s


def _member(rl, s):
    if not meetings.is_member(rl, s):
        common.fail(403, "Only members admitted to this meeting can do that.", "not_member")


def _viewer(rl, s):
    if not meetings.may_view(rl, s):
        common.fail(403, "This meeting is open to the MDT Coordinator, the people who joined with its code and the departments on its agenda.", "forbidden")


def _case_id(x) -> str:
    try:
        return store.safe_id(str(x or ""))
    except ValueError:
        common.fail(400, "A Case File id is not valid.", "bad_case")


# ---- list, create, update --------------------------------------------------------------------------------------------------------------

@router.get("/meetings")
async def meetings_list(request: Request):
    u, rl = _who(request, guest=True)
    return meetings.list_meetings(rl)


@router.get("/meetings/open")
async def meetings_open_list(request: Request):
    """The meetings a Case File may still go to (planned, not cancelled, today or later, earliest first) for any placed account: a
    treating doctor sees an empty planned meeting here even when GET /meetings does not list it (night-v3 item 1.6, Move)."""
    u, rl = _who(request)
    rows = [meetings.summary_row(board.ensure_meeting_fields(s)) for s in meetings.open_meetings()]
    org.audit("meetings_open_listed", u, count=len(rows))
    return {"meetings": rows}


@router.get("/meetings/decision-fields")
async def meetings_decision_fields(request: Request):
    """The decision record table (night-v3 item 3.1): outcomes, steps, fields, choices and limits, the same as decision_fields.json."""
    _who(request)
    return decision_record.spec()


@router.post("/meetings/join")
async def meetings_join(request: Request):
    """{"code"}: 404 no_such_code, 410 code_expired; rate limited 5 tries per 15 minutes per user (a code that is not 6 digits cannot
    match any meeting, so it is refused before it counts as a try)."""
    u, rl = _who(request, guest=True); b = await common.body(request)
    if len("".join(ch for ch in str(b.get("code") or "") if ch.isdigit())) != 6:
        common.fail(404, "Enter the 6-digit meeting code.", "no_such_code")
    JOIN_LIMIT.check(common.client_key(request), "Too many join attempts. Wait 15 minutes and try again.")
    return _call(meetings.join, b.get("code"), u, rl)


@router.post("/meetings")
async def meetings_create(request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request)
    s = _call(meetings.create, u, str(b.get("date") or ""), str(b.get("time") or ""), b.get("room"), bool(b.get("video")), b.get("minutes_per_case"), str(b.get("title") or ""))
    return {"meeting": meetings.summary_row(s)}


@router.put("/meetings/{mid}")
async def meetings_update(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request)
    s = _call(meetings.update, _meeting(mid)["id"], u, b)
    return {"meeting": meetings.summary_row(s)}


@router.post("/meetings/{mid}/cancel")
async def meetings_cancel(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session")
    b = {}
    try:
        b = await common.body(request)
    except Exception:
        pass
    s = _call(meetings.cancel, _meeting(mid)["id"], u, str(b.get("reason") or ""))
    return {"meeting": meetings.summary_row(s)}


@router.get("/meetings/{mid}")
async def meetings_get(mid: str, request: Request):
    u, rl = _who(request, guest=True); s = _meeting(mid); _viewer(rl, s)
    return meetings.view(s["id"], rl)


# ---- agenda --------------------------------------------------------------------------------------------------------------------------------

@router.put("/meetings/{mid}/agenda")
async def meetings_agenda(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    disc = [_case_id(x) for x in (b.get("discussion") or [])]
    note = [_case_id(x) for x in (b.get("noting") or [])]
    nr = [_case_id(x) for x in b["not_ready"]] if isinstance(b.get("not_ready"), list) else None
    s = _call(meetings.set_agenda, s["id"], u, disc, note, nr)
    return meetings.view(s["id"], rl)


@router.post("/meetings/{mid}/agenda/add")
async def meetings_agenda_add(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    cid = _case_id(b.get("case_id"))
    async with store.lock(cid):  # it may clear a withdraw on the Case File (meetings._one_agenda)
        s = _call(meetings.add_to_agenda, s["id"], u, cid, str(b.get("list") or "discussion"), str(b.get("reason") or ""))
    return meetings.view(s["id"], rl)


# ---- the owner moves or withdraws its Case File (night-v3 item 1.6) ------------------------------------------------------------------

def _may_move(rl, c):
    """The owning department's consultants (the right to send it to the board) and the MDT Coordinator."""
    if not (access.may(rl, "mark_ready", c) or rl.get("coordinator")):
        common.fail(403, "Only the owning department's consultants or the MDT Coordinator can move this Case File or take it off the agenda.", "forbidden")


def _moved(c: dict) -> dict:
    s = meetings.get(c.get("meeting_id")) if c.get("meeting_id") else None
    return {"case_id": c["case_id"], "meeting_id": c.get("meeting_id") or "", "board_date": c.get("board_date") or "",
            "board_send": c.get("board_send"), "meeting": meetings.summary_row(s) if s else None}


@router.post("/cases/{case_id}/meeting/move")
async def case_meeting_move(case_id: str, request: Request):
    """{meeting_id, reason?}: move a Case File sent to the board to another open meeting (meetings.move_case); the coordinator is told."""
    u, rl = _who(request); c = common.case(_case_id(case_id)); _may_move(rl, c); b = await common.body(request)
    async with store.lock(c["case_id"]):
        return _moved(_call(meetings.move_case, c["case_id"], u, str(b.get("meeting_id") or ""), str(b.get("reason") or "")))


@router.post("/cases/{case_id}/meeting/withdraw")
async def case_meeting_withdraw(case_id: str, request: Request):
    """{reason}: take a Case File off the agenda (meetings.withdraw_case); the ready mark stays; the coordinator is told."""
    u, rl = _who(request); c = common.case(_case_id(case_id)); _may_move(rl, c); b = await common.body(request)
    async with store.lock(c["case_id"]):
        return _moved(_call(meetings.withdraw_case, c["case_id"], u, str(b.get("reason") or "")))


@router.post("/meetings/{mid}/send-agenda")
async def meetings_send_agenda(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); s = _meeting(mid)
    return _call(meetings.send_agenda, s["id"], u)


@router.post("/meetings/{mid}/remind")
async def meetings_remind(mid: str, request: Request):
    """{case_id}: one reminder to the owning department of a Case File on the agenda: whoever may open the meeting and may remind on that
    Case File (the coordinator, the owner's consultants); never on an archived Case File (security review #7)."""
    u, rl = _who(request); common.need(rl, "remind"); b = await common.body(request); s = _meeting(mid); _viewer(rl, s)
    cid = _case_id(b.get("case_id"))
    c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
    if c and access.is_archived(c):
        common.fail(409, access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", "archived")
    if c and not access.may_remind(rl, c):
        common.fail(403, "Reminders are sent by the MDT Coordinator on the owner's behalf or by the owning department's doctors.", "forbidden")
    return _call(meetings.remind, s["id"], u, rl, cid)


# ---- code, waiting room ------------------------------------------------------------------------------------------------------------------

@router.post("/meetings/{mid}/code")
async def meetings_code(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); s = _meeting(mid)
    return _call(meetings.new_code, s["id"], u)


@router.post("/meetings/{mid}/admit")
async def meetings_admit(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return _call(meetings.admit, s["id"], u, str(b.get("user") or "").strip())


@router.post("/meetings/{mid}/present")
async def meetings_present(mid: str, request: Request):
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid)
    return _call(meetings.present, s["id"], u, rl, str(b.get("mode") or ""))


# ---- running the meeting ---------------------------------------------------------------------------------------------------------------

@router.post("/meetings/{mid}/start")
async def meetings_start(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); s = _meeting(mid)
    return _call(meetings.start, s["id"], u)


@router.post("/meetings/{mid}/end")
async def meetings_end(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); s = _meeting(mid)
    return _call(meetings.end, s["id"], u)


@router.post("/meetings/{mid}/current")
async def meetings_current(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    cid = _case_id(b.get("case_id")) if b.get("case_id") else ""
    return _call(meetings.set_current, s["id"], u, cid, b.get("slide"))


def _may_open(rl, s, user):
    """The coordinator, or the presenter of the Case File on the floor."""
    if meetings.manage(rl):
        return
    cur = s.get("current")
    c = store.get_case(cur) if cur else None
    if c and meetings.presenter_of(c) == user and meetings.is_member(rl, s):
        return
    common.fail(403, "Only the MDT Coordinator or the presenter of the current Case File can open a record or images on the shared screen.", "forbidden")


@router.post("/meetings/{mid}/open")
async def meetings_open(mid: str, request: Request):
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _may_open(rl, s, u)
    doc_id = str(b.get("doc_id") or "").strip()
    if doc_id:
        try:
            doc_id = store.safe_id(doc_id)
        except ValueError:
            common.fail(400, "A record id is not valid.", "bad_record")
    return {"opened": await _acall(meetings.open_item(s["id"], u, str(b.get("kind") or "none"), doc_id))}


VIEW_LIMIT = common.RateLimit(120, 60)  # Board view moves per login per minute (each click of the driver posts one)


@router.post("/meetings/{mid}/view")
async def meetings_view_set(mid: str, request: Request):
    """{tab, doc_id?, page?, quote?}: the driver (the coordinator, or the presenter of the Case File on the floor while admitted) moves the
    Board view every follower renders (meetings-v2 item 2.2, meetings.set_view). Answers {"view": {case_id, tab, doc_id, page, quote, opened,
    by, by_name, at}}."""
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    VIEW_LIMIT.check(u, "Too many Board view changes in a minute. Wait a moment.")
    return {"view": await _acall(meetings.set_view(s["id"], u, rl, str(b.get("tab") or ""), str(b.get("doc_id") or ""), b.get("page"), b.get("quote")))}


@router.post("/meetings/{mid}/timer")
async def meetings_timer(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return {"timer": _call(meetings.timer, s["id"], u, str(b.get("action") or ""), b.get("minutes"))}


@router.post("/meetings/{mid}/questions")
async def meetings_question(mid: str, request: Request):
    """A member types a question; when a stand-in agent is active for the current Case File it answers in the background (text only)."""
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    if b.get("role"):
        AGENT_ASK_LIMIT.check(u, "Too many questions to the agents in a minute. Wait a moment.")
    q = _call(meetings.ask, s["id"], u, str(b.get("text") or ""), b.get("role"), manager=meetings.manage(rl))
    if q.get("role"):
        meetings.answer_in_background(s["id"], q["id"], u)
    return {"question": q, "agent": meetings.agent_state(meetings.get(s["id"]))}


# ---- the specialty agents of the meeting (night-v3 Phase 6, owner decision D2) -------------------------------------------------------------
AGENT_LIMIT = common.RateLimit(120, 60)  # listening and playback reports per login per minute
AGENT_ASK_LIMIT = common.RateLimit(20, 60)  # questions to the agents and Present your points per login per minute (each is a model call)


def _flag(v, default=False) -> bool:
    """A JSON boolean, or the words true, false, on, off, 1, 0 (a string "false" is False)."""
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "on", "yes")


@router.post("/meetings/{mid}/agents")
async def meetings_agents_set(mid: str, request: Request):
    """The coordinator adds an agent to the meeting for the Case File on the floor, or removes one (any of the six roles)."""
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return {"agents": _call(meetings.set_agent, s["id"], u, str(b.get("role") or ""), _flag(b.get("on")))}


@router.put("/meetings/{mid}/agents/settings")
async def meetings_agents_settings(mid: str, request: Request):
    """The coordinator's switch: members can ask the agents (the coordinator always may)."""
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return _call(meetings.set_agents_settings, s["id"], u, _flag(b.get("members_ask"), True))


@router.post("/meetings/{mid}/agents/{role}/listening")
async def meetings_agent_listening(mid: str, role: str, request: Request):
    """An admitted member's device records a question for this agent (on) or stopped (off): the "listening" state, with an expiry."""
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    AGENT_LIMIT.check(u)
    return _call(meetings.set_listening, s["id"], u, role, _flag(b.get("on")), manager=meetings.manage(rl))


@router.post("/meetings/{mid}/agents/{role}/present")
async def meetings_agent_present(mid: str, role: str, request: Request):
    """"Present your points": the agent presents the points of its brief (code, no model call), spoken where agent voices are on."""
    u, rl = _who(request); s = _meeting(mid); _member(rl, s)
    AGENT_ASK_LIMIT.check(u, "Too many questions to the agents in a minute. Wait a moment.")
    return {"question": _call(meetings.present_points, s["id"], u, role, manager=meetings.manage(rl))}


@router.post("/meetings/{mid}/agents/{role}/stop")
async def meetings_agent_stop(mid: str, role: str, request: Request):
    """Stops the agent's voice for everyone: the coordinator, or the person who asked."""
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return _call(meetings.stop_agent, s["id"], u, role, b.get("question"), manager=meetings.manage(rl))


@router.post("/meetings/{mid}/agents/audio")
async def meetings_agent_audio(mid: str, request: Request):
    """A device (a member's, or the room screen's) reports that it plays or stopped playing an answer: drives "speaking"."""
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    AGENT_LIMIT.check(u)
    return _call(meetings.agent_audio, s["id"], u, str(b.get("question") or ""), _flag(b.get("playing")), str(b.get("device") or ""))


@router.post("/meetings/{mid}/hand")
async def meetings_hand(mid: str, request: Request):
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return {"hands": _call(meetings.hand, s["id"], u, bool(b.get("raised", True)))}


@router.post("/meetings/{mid}/spotlight")
async def meetings_spotlight(mid: str, request: Request):
    """The coordinator spotlights up to three admitted people for everyone (night-v3 5.1); an empty list removes the spotlight."""
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    users = b.get("users")
    if users is not None and not isinstance(users, list):  # it cleared the spotlight (the API check, meetings-v2 1.2)
        common.fail(400, "Send the people to spotlight as a list.", "bad_users")
    users = [str(x) for x in users][:10] if isinstance(users, list) else []
    return {"spotlight": _call(meetings.spotlight, s["id"], u, users)}


@router.post("/meetings/{mid}/reaction")
async def meetings_reaction(mid: str, request: Request):
    """A short reaction from an admitted member (agree, thanks, applause, question): broadcast, never stored (night-v3 5.1)."""
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return _call(meetings.react, s["id"], u, str(b.get("kind") or ""))


@router.post("/meetings/{mid}/present-allow")
async def meetings_present_allow(mid: str, request: Request):
    """The coordinator allows or withdraws a member's right to present a screen (night-v3 5.2)."""
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return {"present_allowed": _call(meetings.present_allow, s["id"], u, str(b.get("user") or ""), bool(b.get("allowed", True)))}


@router.post("/meetings/{mid}/presenting")
async def meetings_presenting(mid: str, request: Request):
    """A member starts or stops a screen share (night-v3 5.2): the coordinator, the presenter of the Case File on the floor, or an allowed
    member; the coordinator may stop anyone's."""
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return _call(meetings.set_presenting, s["id"], u, rl, bool(b.get("on", True)))


@router.post("/meetings/{mid}/chat")
async def meetings_chat(mid: str, request: Request):
    """A meeting chat line from an admitted member (night-v3 5.3): kept with the meeting record, apart from the questions."""
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return {"message": _call(meetings.chat, s["id"], u, str(b.get("text") or ""))}


@router.put("/meetings/{mid}/decision-live")
async def meetings_decision_live(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return _call(meetings.decision_live, s["id"], u, str(b.get("text") or ""))


# ---- decisions, cards, slides ----------------------------------------------------------------------------------------------------------

@router.post("/meetings/{mid}/cases/{cid}/decision")
async def meetings_decision(mid: str, cid: str, request: Request):
    u, rl = _who(request); common.need(rl, "board_record"); b = await common.body(request); s = _meeting(mid)
    return await _acall(meetings.record_decision(s["id"], _case_id(cid), b, u))


@router.post("/meetings/{mid}/cases/{cid}/end")
async def meetings_end_case(mid: str, cid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); s = _meeting(mid)
    return _call(meetings.end_case, s["id"], _case_id(cid), u)


@router.post("/meetings/{mid}/cases/{cid}/card")
async def meetings_card(mid: str, cid: str, request: Request):
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    async with store.lock(_case_id(cid)):  # a late concern corrects the board record (review finding 5)
        return {"card": _call(meetings.card, s["id"], _case_id(cid), u, b.get("agree"), str(b.get("note") or ""))}


@router.get("/meetings/{mid}/cards")
async def meetings_cards(mid: str, request: Request):
    u, rl = _who(request); s = _meeting(mid); _viewer(rl, s)
    return _call(meetings.cards, s["id"], rl)


@router.get("/meetings/{mid}/cases/{cid}/slides")
async def meetings_slides(mid: str, cid: str, request: Request):
    u, rl = _who(request, guest=True); s = _meeting(mid); _member(rl, s)
    cid = _case_id(cid)
    if not meetings._on_lists(s, cid) and cid not in {a.get("case_id") for a in s.get("agenda") or []}:
        common.fail(404, "This Case File is not on the meeting's agenda.", "not_on_agenda")
    if rl.get("outside_expert") and not meetings.manage(rl):  # an outside expert follows the shared screen only (security review #9)
        c = store.get_case(cid) if cid not in config.PROTECTED_CASES else None
        if not (c and access.scope(rl, c) == access.FULL) and (s.get("status") != "in_session" or s.get("current") != cid):
            common.fail(403, "An outside expert sees the slides of the Case File on the floor, while the meeting is in session.", "not_current")
    from .. import board
    board.audit_event(s["id"], "slides_read", u, case_id=cid)
    return {"case_id": cid, "slides": _call(meetings.slides, cid, rl)}


# ---- the scheduler -------------------------------------------------------------------------------------------------------------------------

@router.get("/scheduler/status")
async def scheduler_status(request: Request):
    rl = common.roles(request)
    if not (rl.get("admin") or rl.get("root_admin")):
        common.fail(403, "The scheduler status is for the root admin and the Vaidyx admin.", "forbidden")
    return scheduler.status()
