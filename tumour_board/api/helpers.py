"""Specialty helper routes (B2, SPEC-API helpers.py): the six cards, prepare a brief in the background (poll GET /jobs/{id}), and the
chat thread per role (agents.ask). Rate limits: 10 preparations and 20 questions per 10 minutes per user."""
from fastapi import Request

from tumour_board import chats, helpers

from . import common

router = common.make_router()
PREPARE_LIMIT = common.RateLimit(10, 600)
ASK_LIMIT = common.RateLimit(20, 600)


def _role(role):
    if role not in helpers.ROLES:
        common.fail(404, "Unknown helper role.", "no_role")
    return role


@router.get("/cases/{case_id}/helpers")
async def list_helpers(case_id: str, request: Request):
    """{helpers[{role, label, title, department, brief{status: none|preparing|ready|stale, at, sections, points_for_review, reviewed_by?}, thread_count,
    points_count, not_documented_count, meeting_exchanges, prepared_at, prepare_allowed}]}."""
    rl = common.roles(request); common.case(case_id)
    return {"helpers": helpers.list_helpers(case_id, rl), "heads": list(helpers.HEADS)}


@router.post("/cases/{case_id}/helpers/{role}/prepare")
async def prepare(case_id: str, role: str, request: Request):
    """{refresh?} -> {job, status: preparing|ready, reused}: the brief is written in the background by the role's agent; poll GET /jobs/{id}
    or GET /cases/{id}/helpers for the status. A brief that still stands for the Case File is reused unless refresh is true."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_known(rl); _role(role)
    if not next((h["prepare_allowed"] for h in helpers.list_helpers(case_id, rl) if h["role"] == role), False):
        common.fail(403, "A helper brief is prepared by the owning department's doctors or the MDT Coordinator.", "prepare_forbidden")
    b = await common.body(request) if (await request.body()) else {}
    PREPARE_LIMIT.check(common.client_key(request), "Too many preparations in a short time; please wait a few minutes.")
    if not c.get("protocol"):
        common.fail(409, "The Case File is not listed yet: list it before preparing a brief.", "not_listed")
    return helpers.prepare(case_id, role, u, refresh=bool(b.get("refresh")))


@router.post("/cases/{case_id}/helpers/prepare-all")
async def prepare_all(case_id: str, request: Request):
    """-> {helpers[{role, status: preparing|ready|queued, job}], started}: "Prepare all" on the Case File (night-v3 item 6.5). Every role
    without a brief standing for the Case File is prepared in the background, one after the other; poll GET /cases/{id}/helpers. The same
    permission as one preparation."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_known(rl)
    if not any(h["prepare_allowed"] for h in helpers.list_helpers(case_id, rl)):
        common.fail(403, "A helper brief is prepared by the owning department's doctors or the MDT Coordinator.", "prepare_forbidden")
    PREPARE_LIMIT.check(common.client_key(request), "Too many preparations in a short time; please wait a few minutes.")
    if not c.get("protocol"):
        common.fail(409, "The Case File is not listed yet: list it before preparing a brief.", "not_listed")
    return helpers.prepare_all(case_id, u)


def _chat_reader(request, rl):
    """The helper threads follow the team chat's rule: the treating team and the MDT Coordinator, in FULL scope; never a supporting-only
    doctor (security review #15)."""
    if not chats.may_read(rl, common.scope(request)):
        common.fail(403, chats.refusal(rl), "chat_forbidden")


@router.get("/cases/{case_id}/helpers/{role}/chat")
async def chat(case_id: str, role: str, request: Request):
    rl = common.roles(request); common.case(case_id); _role(role); _chat_reader(request, rl)
    return {"messages": helpers.messages(case_id, role), "role": role, "label": helpers.label(role)}


@router.post("/cases/{case_id}/helpers/{role}/chat")
async def ask(case_id: str, role: str, request: Request):
    """{question} -> the message (agents.ask: from the records and the specialty's guideline pack; never an opinion)."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_known(rl); _role(role); _chat_reader(request, rl)
    b = await common.body(request)
    q = " ".join(str(b.get("question") or "").split())
    if not q:
        common.fail(400, "Ask a question.", "empty_question")
    if not c.get("protocol"):
        common.fail(409, "The Case File is not listed yet: list it before asking a helper.", "not_listed")
    ASK_LIMIT.check(common.client_key(request), "Too many questions in a short time; please wait a few minutes.")
    try:
        return await helpers.ask(case_id, role, q, u)
    except ValueError as e:
        common.fail(400, str(e), "bad_question")
