"""The fill-in summary routes (B2, SPEC-API slots.py): the slots of a Case File, typed values, not needed, ask the department, and
where a quote sits on a page. Logic in tumour_board/slots.py and tumour_board/quote_boxes.py; no model call anywhere here."""
from fastapi import Request

from tumour_board import access, quote_boxes, slots, store

from . import common

router = common.make_router()


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except slots.SlotError as e:
        common.fail(e.status, str(e), "slot_" + str(e.status))


@router.get("/cases/{case_id}/slots")
async def get_slots(case_id: str, request: Request):
    """{sections[{id, label, slots[...]}], left_before_board, blockers[], ready_allowed, prose{status, paragraphs, reviewed}, permissions}."""
    rl = common.roles(request); common.case(case_id)
    return _call(slots.build, case_id, rl)


@router.get("/cases/{case_id}/slots/{slot}")
async def get_slot(case_id: str, slot: str, request: Request):
    rl = common.roles(request); common.case(case_id)
    return _call(slots.one, case_id, slot, rl)


@router.post("/cases/{case_id}/slots/{slot}/value")
async def set_value(case_id: str, slot: str, request: Request):
    """{value, note?}: a typed value for a typable field (ECOG, menopausal status, weight, height, the board question, protocol facts flagged
    typable), validated, audited "typed_value", shown "entered by Dr X, no report"; the gate is re-checked. The owner's doctors."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); b = await common.body(request)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        _call(slots.set_value, case_id, slot, b.get("value"), b.get("note"), u)
    return _call(slots.one, case_id, slot, rl)


@router.delete("/cases/{case_id}/slots/{slot}/value")
async def clear_value(case_id: str, slot: str, request: Request):
    u = common.user(request); rl = common.roles(request); c = common.case(case_id)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        _call(slots.clear_value, case_id, slot, u)
    return _call(slots.one, case_id, slot, rl)


@router.post("/cases/{case_id}/slots/{slot}/not-needed")
async def not_needed(case_id: str, slot: str, request: Request):
    """{reason}: the record (or the one open value of a record) is not needed for this Case File: a waive confirmation, audited, undoable."""
    u = common.user(request); rl = common.roles(request); common.case(case_id); b = await common.body(request)
    async with store.lock(case_id):
        done = _call(slots.not_needed, case_id, slot, b.get("reason"), u, rl)
    return {**_call(slots.one, case_id, slot, rl), "confirmation": done["confirmation"], "waived_record": done["record"]}


@router.post("/cases/{case_id}/slots/{slot}/ask-department")
async def ask_department(case_id: str, slot: str, request: Request):
    """{message?, due?}: sends the request the gate suggested for the slot's record (the draft text from dept_requests.draft unless the
    doctor edited it); the department is notified in-app and the line turns "waiting on <department>"."""
    u = common.user(request); rl = common.roles(request); common.case(case_id)
    b = await common.body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        a = _call(slots.ask_department, case_id, slot, u, rl, str(b.get("message") or ""), str(b.get("due") or ""))
    return {"slot": _call(slots.one, case_id, slot, rl), "request": slots._request(a), "action": a}


@router.get("/cases/{case_id}/documents/{doc_id}/quote")
async def quote(case_id: str, doc_id: str, request: Request, fact: str = "", text: str = ""):
    """?fact=<id> or ?text=<quote> -> {page, boxes[[x0, y0, x1, y1] fractions of the page], found, ...}: the page the quote sits on and, for a
    scanned page the OCR engine read, the word boxes to highlight. Never fails for an unknown quote: found is False."""
    common.user(request); c = common.case(case_id)
    if not store.get_doc(case_id, doc_id):
        common.fail(404, "document not found", "no_document")
    if common.scope(request) == access.REQUESTS and not any(  # a department that was only asked: the records in its scope only (review #1)
            x.get("doc_id") == doc_id for x in access.limited_docs(common.roles(request), c, store.list_docs(case_id))):
        common.fail(403, "Your department sees only the records it produced or was asked about in this Case File.", "out_of_scope")
    if not (fact or text):
        return {"found": False, "page": None, "boxes": [], "reason": "give ?fact=<field id> or ?text=<quote>"}
    return quote_boxes.find(case_id, doc_id, fact_id=fact, text=text) or {"found": False, "page": None, "boxes": [], "reason": "document not found"}
