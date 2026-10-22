"""Meeting routes (B3): the contract in docs/ui/build/SPEC-API.md (meetings.py). The MDT Coordinator manages (org action "session"),
the members are the people the coordinator admitted, the owner's team of a Case File reads its cards; every change is audited by
meetings.py. Also GET /scheduler/status for the root admin and the Vaidyx admin."""
from fastapi import Request

from . import common
from .. import access, config, meetings, org, scheduler, store

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
    s = _call(meetings.add_to_agenda, s["id"], u, _case_id(b.get("case_id")), str(b.get("list") or "discussion"), str(b.get("reason") or ""))
    return meetings.view(s["id"], rl)


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


@router.post("/meetings/{mid}/timer")
async def meetings_timer(mid: str, request: Request):
    u, rl = _who(request); common.need(rl, "session"); b = await common.body(request); s = _meeting(mid)
    return {"timer": _call(meetings.timer, s["id"], u, str(b.get("action") or ""), b.get("minutes"))}


@router.post("/meetings/{mid}/questions")
async def meetings_question(mid: str, request: Request):
    """A member types a question; when a stand-in agent is active for the current Case File it answers in the background (text only)."""
    u, rl = _who(request); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    q = _call(meetings.ask, s["id"], u, str(b.get("text") or ""), b.get("role"))
    if q.get("role"):
        meetings.answer_in_background(s["id"], q["id"], u)
    return {"question": q, "agent": meetings.agent_state(meetings.get(s["id"]))}


@router.post("/meetings/{mid}/hand")
async def meetings_hand(mid: str, request: Request):
    u, rl = _who(request, guest=True); b = await common.body(request); s = _meeting(mid); _member(rl, s)
    return {"hands": _call(meetings.hand, s["id"], u, bool(b.get("raised", True)))}


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
