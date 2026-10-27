"""The Case summary routes (night-v3 item 3.3): read the current version and the list of versions, build it on demand, and the owner's
consultant's review and edit. Logic in tumour_board/case_summary.py (it audits every build, review and edit). The route class checks
who may open the Case File (owner, participants, the MDT Coordinator, a break-glass window reads only)."""
from fastapi import Request

from tumour_board import access, case_summary, config, org, store

from . import common

router = common.make_router(["tumour-board-case-summary"])


def _full(request, case_id):
    """The Case summary is for whoever reads the whole Case File; a department that was only asked keeps its request view."""
    c = common.case(case_id)
    if common.scope(request) == access.REQUESTS:
        common.fail(403, "Your department sees only what it was asked for in this Case File.", "requests_only")
    return c


def _consultant(rl, c, what):
    if not access.is_owner_doctor(rl, c):
        common.fail(403, f"Only the owning department's consultants {what} the Case summary", "forbidden")


def _n(n) -> int:
    try:
        return int(n)
    except (TypeError, ValueError):
        common.fail(400, "The version must be a number.", "bad_version")


def _view(case_id) -> dict:
    st = store.get_state(case_id)
    v = case_summary.current(st)
    return {"current": v.get("n") if v else None, "versions": case_summary.history(st), "version": v, "status": case_summary.status(st, case_id)}


@router.get("/cases/{case_id}/case-summary")
async def get_case_summary(case_id: str, request: Request):
    """{current, versions[{n, built_at, trigger, review, edits, sentences}], version (the current one in full), status}. The status
    section is rewritten by code (no model, no new version) when the actions changed or a day passed since it was written, so "overdue"
    stays true."""
    rl = common.roles(request); _full(request, case_id)
    st = store.get_state(case_id)
    v = case_summary.current(st)
    if v and case_id not in config.PROTECTED_CASES:
        last = str(v.get("status_day") or "")
        part = case_summary.signature(case_id, st)["parts"]["status"]
        if part != ((v.get("signature") or {}).get("parts") or {}).get("status") or last != case_summary.today():
            async with store.lock(case_id):
                case_summary.refresh_status(case_id)
    return _view(case_id)


@router.post("/cases/{case_id}/case-summary")
async def post_case_summary(case_id: str, request: Request):
    """Build a new version now {"force"?}: the owning department's doctors or the MDT Coordinator. 409 no_decision without a board record."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); common.need_known(rl)
    if not (org.can(rl, "list_case") or access.may(rl, "upload_to_case", c)):  # the same rule as POST /cases/{id}/summary
        common.fail(403, "Only the doctors of the owning department or the MDT Coordinator write the Case summary", "forbidden")
    b = await common.body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        try:
            v = await case_summary.build(case_id, {"kind": "on_demand", "by": u, **({"force": True} if b.get("force") else {})}, u)
        except ValueError as e:
            common.fail(403, str(e), "protected")
    if v.get("status") == "no_decision":
        common.fail(409, v["message"], "no_decision")
    return v


@router.post("/cases/{case_id}/case-summary/{n}/review")
async def review_case_summary(case_id: str, n: str, request: Request):
    """{status: reviewed | flagged | ai_draft, comment}: the owning department's consultants only."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    _consultant(rl, c, "review")
    b = await common.body(request)
    async with store.lock(case_id):
        try:
            return case_summary.review(case_id, _n(n), str(b.get("status") or ""), str(b.get("comment") or ""), u)
        except KeyError as e:
            common.fail(404, str(e).strip("'\""), "no_version")
        except ValueError as e:
            common.fail(400, str(e), "invalid")


@router.post("/cases/{case_id}/case-summary/{n}/edit")
async def edit_case_summary(case_id: str, n: str, request: Request):
    """{sentence_id, text}: the owning department's consultants only; a sentence of the presentation or since section of the current
    version. Returns the sentence."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    _consultant(rl, c, "edit")
    b = await common.body(request)
    async with store.lock(case_id):
        try:
            from tumour_board.slots import display_name
            return case_summary.edit(case_id, _n(n), str(b.get("sentence_id") or ""), str(b.get("text") or ""), u, display_name(u))
        except KeyError as e:
            common.fail(404, str(e).strip("'\""), "not_found")
        except ValueError as e:
            common.fail(400, str(e), "invalid")
