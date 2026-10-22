"""Ask this Case File routes (B2, SPEC-API chats.py): the shared team chat, answered by qa.ask with verified quotes. Rate limit 20 per
10 minutes per user on questions. Never visible to a supporting-only doctor or in REQUESTS scope."""
from fastapi import Request

from tumour_board import chats

from . import common

router = common.make_router()
ASK_LIMIT = common.RateLimit(20, 600)


def _reader(request, case_id):
    rl = common.roles(request); common.case(case_id)
    if not chats.may_read(rl, common.scope(request)):
        common.fail(403, chats.refusal(rl), "chat_forbidden")
    return rl


@router.get("/cases/{case_id}/chats")
async def list_chats(case_id: str, request: Request):
    """{threads[{id, by, by_name, at, question, status, statements[{text, citations[{doc_id, doc_title, page, quote}]}], message, pinned, stale, seconds}]}
    pinned first, newest first."""
    _reader(request, case_id)
    return {"threads": chats.threads(case_id)}


@router.post("/cases/{case_id}/chats")
async def ask(case_id: str, request: Request):
    """{question, history?} -> the thread (qa.ask: answers only from the records, every statement with a verified quote, or "Not documented")."""
    u = common.user(request); rl = _reader(request, case_id); common.need_known(rl)
    b = await common.body(request)
    q = " ".join(str(b.get("question") or "").split())
    if not q:
        common.fail(400, "Ask a question.", "empty_question")
    ASK_LIMIT.check(common.client_key(request), "Too many questions in a short time; please wait a few minutes.")
    try:
        return await chats.ask(case_id, q, u, b.get("history"))
    except ValueError as e:
        common.fail(400, str(e), "bad_question")


@router.post("/cases/{case_id}/chats/{thread_id}/pin")
async def pin(case_id: str, thread_id: str, request: Request):
    u = common.user(request); _reader(request, case_id)
    b = await common.body(request) if (await request.body()) else {}
    try:
        return chats.pin(case_id, thread_id, bool(b.get("pinned", True)), u)
    except KeyError:
        common.fail(404, "Thread not found.", "no_thread")
