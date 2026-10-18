"""Published cases routes (B2, SPEC-API published.py): search (local library, PubMed, Europe PMC; the doctor's words only, logged), add
with pasted verbatim quotes, delete. The doctor of the owning department adds and removes (may upload_to_case); residents are routed to
proposals by the interface. Search rate limit 10 per 10 minutes per user."""
from fastapi import Request

from tumour_board import published

from . import common

router = common.make_router()
SEARCH_LIMIT = common.RateLimit(10, 600)


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except published.PublishedError as e:
        common.fail(e.status, str(e), "published_" + str(e.status))


@router.get("/cases/{case_id}/published")
async def list_published(case_id: str, request: Request):
    common.roles(request); common.case(case_id)
    return published.view(case_id)


@router.post("/cases/{case_id}/published/search")
async def search(case_id: str, request: Request):
    """{terms} -> {results[{title, authors, journal, year, doi, url, source: local|pubmed|europepmc, peer_reviewed, kind, snippet}], counts, error}."""
    u = common.user(request); rl = common.roles(request); common.case(case_id); common.need_known(rl)
    b = await common.body(request)
    SEARCH_LIMIT.check(common.client_key(request), "Too many searches in a short time; please wait a few minutes.")
    try:
        return await published.search(case_id, b.get("terms"), u)
    except published.PublishedError as e:
        common.fail(e.status, str(e), "published_" + str(e.status))


@router.post("/cases/{case_id}/published")
async def add(case_id: str, request: Request):
    """{result, quotes?[{text, where}]} -> the item, labelled "Published case, not advice for this patient"."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_case(rl, "upload_to_case", c)
    b = await common.body(request)
    return _call(published.add, case_id, b.get("result") if isinstance(b.get("result"), dict) else b, b.get("quotes"), u)


@router.post("/cases/{case_id}/published/{item_id}/quotes")
async def add_quotes(case_id: str, item_id: str, request: Request):
    """{quotes[{text, where}]}: more verbatim quotes pasted from the paper."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_case(rl, "upload_to_case", c)
    b = await common.body(request)
    return _call(published.add_quotes, case_id, item_id, b.get("quotes"), u)


@router.delete("/cases/{case_id}/published/{item_id}")
async def remove(case_id: str, item_id: str, request: Request):
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_case(rl, "upload_to_case", c)
    return {"removed": _call(published.remove, case_id, item_id, u)}
