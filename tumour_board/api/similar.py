"""Similar Case Files routes (night-v3 item 7.2; contract docs/night-v3/research/07_similar_cases.md section 8.3): whether a search is
possible here, the search itself (the reasoner's order, the quoted lines, the cards) and how one result may be opened. A search needs a
known login with full access to this Case File (never a Vaidyx admin, a supporting department or a window opened with a reason) and is
limited to 10 per 10 minutes per login. Every result is labelled "Past Case File, not advice for this patient"."""
from fastapi import Request

from tumour_board import access, llm, org, published, similar, store

from . import common

router = common.make_router(["tumour-board-similar"])
SEARCH_LIMIT = common.RateLimit(10, 600)
NOT_FOUND = "That Case File is not available here any more."


def _searcher(request: Request, case_id: str):
    """(login, roles, Case File) for a search or an opening from this Case File, or the refusal."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); common.need_known(rl)
    if rl.get("vaidyx_admin"):
        common.fail(403, similar.ADMIN_REASON, "vaidyx_admin")
    if similar._protected(case_id) or access.is_protected(c):
        common.fail(403, similar.PROTECTED_REASON, "protected")
    if access.scope(rl, c) != access.FULL:
        common.fail(403, similar.SCOPE_REASON, "full_scope_only")
    return u, rl, c


@router.get("/cases/{case_id}/similar")
async def similar_info(case_id: str, request: Request):
    """{available, reason, label, order_note, model_line, cancer_group, group_label, searches[{words, at, by_name}]}."""
    rl = common.roles(request); common.case(case_id)
    try:
        return similar.info(case_id, rl)
    except ValueError:
        common.fail(404, "Case not found", "not_found")


@router.post("/cases/{case_id}/similar/search")
async def similar_search(case_id: str, request: Request):
    """{words?} -> SimilarResponse (contract 8.4): the past Case Files in order, each with its quoted lines; no score."""
    u, rl, c = _searcher(request, case_id)
    b = await common.body(request) if (await request.body()) else {}
    words = b.get("words")
    if words is not None and not isinstance(words, str):
        common.fail(400, "The search words must be text.", "bad_words")
    SEARCH_LIMIT.check(u or common.client_key(request), "Too many searches in a short time; please wait a few minutes.")
    try:
        return await similar.search(case_id, words or "", u, rl)
    except published.PublishedError as e:
        common.fail(400, str(e), "bad_words")
    except ValueError as e:
        if str(e) == "protected":
            common.fail(403, similar.PROTECTED_REASON, "protected")
        common.fail(404, "Case not found", "not_found")
    except llm.LLMError:
        common.fail(502, "The search could not be ordered: neither the model order nor the text order was available.", "model_unavailable")


@router.post("/cases/{case_id}/similar/open")
async def similar_open(case_id: str, request: Request):
    """{past_case_id} -> {how: normal | with_reason | refused, scope, reason, via, label}. "normal" is audited here in both Case Files and
    the organisation log; "with_reason" audits nothing here (the break-glass route audits the opening with its via)."""
    u, rl, c = _searcher(request, case_id)
    b = await common.body(request)
    past = str(b.get("past_case_id") or "").strip()
    try:
        out = similar.open_info(rl, past, case_id)
    except ValueError:
        common.fail(404, NOT_FOUND, "not_found")
    if out["how"] == "normal":
        store.audit(case_id, {"kind": "similar_opened", "by": u, "past": past, "how": "normal"})
        store.audit(past, {"kind": "similar_opened", "by": u, "from": case_id, "how": "normal"})
        org.audit("similar_opened", u, case_id=case_id, past=past, how="normal")
    return out
