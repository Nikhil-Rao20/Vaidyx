"""The guided Case File routes (21 Oct 2026, docs/ui/casefile-steps/DESIGN.md): the six sections with their status and the next action,
the reason for discussion, the key-value checks and setting aside the cancer warning. Logic in tumour_board/steps.py; no model call."""
from fastapi import Request

from tumour_board import access, steps, store

from . import common

router = common.make_router()


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except steps.StepError as e:
        common.fail(e.status, str(e), "step_" + str(e.status))


def _full(request, case_id):
    """The guided Case File is for whoever reads the whole Case File; a department that was only asked keeps its request view."""
    c = common.case(case_id)
    if common.scope(request) == access.REQUESTS:
        common.fail(403, "Your department sees only what it was asked for in this Case File.", "requests_only")
    return c


@router.get("/cases/{case_id}/steps")
async def get_steps(case_id: str, request: Request):
    """{mode, role, sections[{id, label, status, detail, count}], next, todo[], waiting[], warnings[], question, glance[], documents[], check,
    pre_authorization, summary, left, permissions}."""
    rl = common.roles(request); _full(request, case_id)
    return _call(steps.build, case_id, rl)


@router.put("/cases/{case_id}/reason")
async def put_reason(case_id: str, request: Request):
    """{value}: the reason for discussion, one of steps.REASONS; the owner's doctors."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); b = await common.body(request)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(steps.set_reason, case_id, b.get("value"), u)


@router.post("/cases/{case_id}/key-checks")
async def post_key_check(case_id: str, request: Request):
    """{fact_id, value, doc_id}: the doctor read a key value against its report line; kept while the same value from the same report stands."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); b = await common.body(request)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(steps.confirm_key, case_id, b.get("fact_id"), b.get("value"), b.get("doc_id"), u)


@router.delete("/cases/{case_id}/key-checks/{fact_id}")
async def delete_key_check(case_id: str, fact_id: str, request: Request):
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        _call(steps.undo_key, case_id, fact_id, u)
    return {"ok": True}


@router.post("/cases/{case_id}/warnings/{key}/dismiss")
async def dismiss(case_id: str, key: str, request: Request):
    """The cancer chosen is right although the report titles name another site: the warning is set aside, audited."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(steps.dismiss_warning, case_id, key, u)
