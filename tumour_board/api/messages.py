"""Messages between logins (night-v3 item 8.1, contract docs/night-v3/research/06_messages.md section 9.3). Every route: the roles of
the login, messages.may_use (403 not_placed: "Messages are for placed hospital staff."), then the Tumour Board guard (need_known).
The client never sends the sender or a time. A conversation the person does not read is 404, the same as an unknown id. A refusal
(not placed, not a participant) is audited as message_denied at most once a minute per login; the text of a message is never logged."""
from fastapi import Request

from . import common
from .. import messages

router = common.make_router(["tumour-board-messages"])
TOO_MANY = "Too many messages. Please wait a moment."

# Per login; module globals so tests can replace them (common.RateLimit is in memory, one process).
LIST_LIMIT = common.RateLimit(120, 60)
NEW_LIMIT = common.RateLimit(10, 600)  # new conversations; a send into an existing one counts under SEND_LIMIT
OPEN_LIMIT = common.RateLimit(120, 60)
SEND_LIMIT = common.RateLimit(30, 60)
EDIT_LIMIT = common.RateLimit(20, 60)
DELETE_LIMIT = common.RateLimit(20, 60)
REACT_LIMIT = common.RateLimit(60, 60)
RESOLVE_LIMIT = common.RateLimit(30, 60)
READ_LIMIT = common.RateLimit(120, 60)
MUTE_LIMIT = common.RateLimit(30, 60)
SEARCH_LIMIT = common.RateLimit(30, 60)
UNREAD_LIMIT = common.RateLimit(120, 60)
LINKS_LIMIT = common.RateLimit(60, 60)
NOTICE_LIMIT = common.RateLimit(30, 60)
LIMITS = ("LIST_LIMIT", "NEW_LIMIT", "OPEN_LIMIT", "SEND_LIMIT", "EDIT_LIMIT", "DELETE_LIMIT", "REACT_LIMIT", "RESOLVE_LIMIT", "READ_LIMIT",
          "MUTE_LIMIT", "SEARCH_LIMIT", "UNREAD_LIMIT", "LINKS_LIMIT", "NOTICE_LIMIT")


def _who(request: Request, route: str, conv_id: str = "") -> tuple[str, dict]:
    r = common.roles(request)
    if not messages.may_use(r):  # before need_known, so every unplaced login gets the same coded refusal the screens act on
        messages.note_denied(r.get("user") or "", route, conv_id)
        common.fail(403, messages.NOT_PLACED, "not_placed")
    common.need_known(r)
    return r.get("user") or "", r


def _run(fn, user: str, route: str, conv_id: str = ""):
    try:
        return fn()
    except messages.Refused as e:
        if e.status in (403, 404) and e.code in ("not_found", "not_placed"):
            messages.note_denied(user, route, conv_id)
        common.fail(e.status, e.message, e.code)


@router.get("/messages/conversations")
async def list_conversations(request: Request, filter: str = "all", q: str = ""):  # noqa: A002
    user, r = _who(request, "list")
    LIST_LIMIT.check(user, TOO_MANY)
    rows = _run(lambda: messages.list_conversations(user, filter=filter, q=q, r=r), user, "list")
    return {"conversations": rows, "unread_total": messages.unread_total(user, r=r)}


@router.post("/messages/conversations", status_code=201)
async def start(request: Request):
    user, r = _who(request, "start")
    b = await common.body(request)
    existing = _run(lambda: messages.find(user, b.get("to"), r=r), user, "start")
    (SEND_LIMIT if existing else NEW_LIMIT).check(user, TOO_MANY)
    conv, msg = _run(lambda: messages.start(user, b.get("to"), b.get("text"), link=b.get("link"), mentions=b.get("mentions"), r=r), user, "start")
    return {"conversation": messages.conversation_row(user, conv["id"], r=r), "message": msg}


@router.get("/messages/conversations/{conv_id}")
async def open_conversation(conv_id: str, request: Request, before: int | None = None, limit: int = messages.PAGE_DEFAULT):
    user, r = _who(request, "open", conv_id)
    OPEN_LIMIT.check(user, TOO_MANY)
    return _run(lambda: messages.get_conversation(user, conv_id, before=before, limit=limit, r=r), user, "open", conv_id)


@router.post("/messages/conversations/{conv_id}/messages")
async def send(conv_id: str, request: Request):
    user, r = _who(request, "send", conv_id)
    SEND_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    msg = _run(lambda: messages.send(user, conv_id, b.get("text"), link=b.get("link"), mentions=b.get("mentions"), r=r), user, "send", conv_id)
    return {"message": msg}


@router.patch("/messages/conversations/{conv_id}/messages/{mid}")
async def edit(conv_id: str, mid: str, request: Request):
    user, r = _who(request, "edit", conv_id)
    EDIT_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    return {"message": _run(lambda: messages.edit(user, conv_id, mid, b.get("text"), r=r), user, "edit", conv_id)}


@router.delete("/messages/conversations/{conv_id}/messages/{mid}")
async def delete(conv_id: str, mid: str, request: Request):
    user, r = _who(request, "delete", conv_id)
    DELETE_LIMIT.check(user, TOO_MANY)
    return {"message": _run(lambda: messages.delete(user, conv_id, mid, r=r), user, "delete", conv_id)}


@router.post("/messages/conversations/{conv_id}/messages/{mid}/react")
async def react(conv_id: str, mid: str, request: Request):
    user, r = _who(request, "react", conv_id)
    REACT_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    return {"message": _run(lambda: messages.react(user, conv_id, mid, b.get("emoji"), r=r), user, "react", conv_id)}


@router.post("/messages/conversations/{conv_id}/resolve")
async def resolve(conv_id: str, request: Request):
    user, r = _who(request, "resolve", conv_id)
    RESOLVE_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    if not isinstance(b.get("resolved"), bool):
        common.fail(400, "Say whether the conversation is resolved.", "bad_request")
    return {"conversation": _run(lambda: messages.resolve(user, conv_id, b["resolved"], r=r), user, "resolve", conv_id)}


@router.post("/messages/conversations/{conv_id}/read")
async def read(conv_id: str, request: Request):
    user, r = _who(request, "read", conv_id)
    READ_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    return {"unread_total": _run(lambda: messages.mark_read(user, conv_id, b.get("seq"), r=r), user, "read", conv_id)}


@router.post("/messages/conversations/{conv_id}/mute")
async def mute(conv_id: str, request: Request):
    user, r = _who(request, "mute", conv_id)
    MUTE_LIMIT.check(user, TOO_MANY)
    b = await common.body(request)
    if not isinstance(b.get("muted"), bool):
        common.fail(400, "Say whether the conversation is muted.", "bad_request")
    return {"conversation": _run(lambda: messages.mute(user, conv_id, b["muted"], r=r), user, "mute", conv_id)}


@router.get("/messages/search")
async def search(request: Request, q: str = ""):
    user, r = _who(request, "search")
    SEARCH_LIMIT.check(user, TOO_MANY)
    return {"hits": _run(lambda: messages.search(user, q, r=r), user, "search")}


@router.get("/messages/unread")
async def unread(request: Request):
    user, r = _who(request, "unread")
    UNREAD_LIMIT.check(user, TOO_MANY)
    return {"unread_total": messages.unread_total(user, r=r)}


@router.get("/messages/links")
async def links(request: Request, q: str = ""):
    user, r = _who(request, "links")
    LINKS_LIMIT.check(user, TOO_MANY)
    return _run(lambda: messages.attachable(user, q, r=r), user, "links")


@router.post("/messages/notice")
async def notice(request: Request):
    user, r = _who(request, "notice")
    NOTICE_LIMIT.check(user, TOO_MANY)
    return {"notice_seen": messages.set_notice_seen(user)}
