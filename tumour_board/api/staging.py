"""Draft stage routes (owner decision, 22 Oct 2026, docs/staging/DECISION.md): the Staging card's view, working the draft out (one reasoner
call; every quote checked), confirming or rejecting it, and the staging book's pages with the line highlighted. Logic in
tumour_board/staging/."""
from fastapi import Request
from fastapi.responses import Response

from tumour_board import access, staging, store
from tumour_board.staging import book

from . import common

router = common.make_router()


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except staging.StagingError as e:
        common.fail(e.status, str(e), "staging_" + str(e.status))


def _full(request, case_id):
    c = common.case(case_id)
    if common.scope(request) == access.REQUESTS:
        common.fail(403, "Your department sees only what it was asked for in this Case File.", "requests_only")
    return c


@router.get("/cases/{case_id}/staging")
async def get_staging(case_id: str, request: Request):
    """{switch, draft_label, written[], draft, comparison, stale, book, system, label, groups_note}."""
    common.roles(request); _full(request, case_id)
    return _call(staging.view, case_id)


_RUNS = common.RateLimit(6, 60)


@router.post("/cases/{case_id}/staging/run")
async def run_staging(case_id: str, request: Request):
    """Work the draft stage out from the reports (the owner's team: the same right as preparing the summary)."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    if not access.is_team_resident(rl, c):  # a resident on the team prepares too (R03-Q03); everyone else needs the owner's right
        common.need_case(rl, "confirm", c)
    _RUNS.check(u, "Please wait a minute before working the stage out again.")
    try:
        return await staging.run(case_id, u)
    except staging.StagingError as e:
        common.fail(e.status, str(e), "staging_" + str(e.status))


@router.post("/cases/{case_id}/staging/enter")
async def enter_part(case_id: str, request: Request):
    """{part: T|N|M, cat, reason}: the treating doctor fills a part no report states (shown "entered by Dr X, no report"); cat "" takes it back."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); b = await common.body(request)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(staging.enter, case_id, u, str(b.get("part") or ""), str(b.get("cat") or ""), b.get("reason"))


@router.post("/cases/{case_id}/staging/confirm")
async def confirm_staging(case_id: str, request: Request):
    """{note?, which?}: a consultant of the owning department confirms the draft for the board (guard 1); audited. which = "anatomic"
    (the default) or "prognostic" (the breast prognostic stage group)."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    b = await common.body(request) if (await request.body()) else {}
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(staging.confirm, case_id, u, b.get("note"), b.get("which") or "anatomic")


@router.post("/cases/{case_id}/staging/reject")
async def reject_staging(case_id: str, request: Request):
    """{reason, which?}: "This is wrong", with the reason; the draft stays visible, marked rejected; audited. which as for confirm."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); b = await common.body(request)
    common.need_case(rl, "confirm", c)
    async with store.lock(case_id):
        return _call(staging.reject, case_id, u, b.get("reason"), b.get("which") or "anatomic")


@router.get("/staging/books/{book_id}")
async def book_meta(book_id: str, request: Request):
    """{id, title, pages, printed[], first_page, last_page}: a staging book named by a rule file and present on this server."""
    common.user(request); common.need_known(common.roles(request))
    m = book.meta(book_id)
    if not m:
        common.fail(404, "This book is not on this server.", "no_book")
    return {k: m[k] for k in ("id", "title", "pages", "printed", "first_page", "last_page", "aspect")}


@router.get("/staging/books/{book_id}/pages/{page}")
async def book_page(book_id: str, page: int, request: Request, find: str = ""):
    """One printed page as JPEG, with the line of `find` (a phrase of the page's own text) highlighted."""
    common.user(request); common.need_known(common.roles(request))
    out = await book.page_image(book_id, int(page), (find or "")[:200])  # drawn in a worker process: pdfium is not thread-safe
    if not out:
        common.fail(404, "This page is not in the book on this server.", "no_page")
    img, hl = out
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600", "X-Highlights": str(len(hl))})
