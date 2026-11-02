"""The Case summary routes (night-v3 item 3.3): read the current version and the list of versions, build it on demand, and the owner's
consultant's review and edit. Logic in tumour_board/case_summary.py (it audits every build, review and edit). The route class checks
who may open the Case File (owner, participants, the MDT Coordinator, a break-glass window reads only)."""
from fastapi import Request

from tumour_board import access, case_summary, org, store

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


def _view(case_id, rl=None, n=None) -> dict:
    """{current, versions, version (version n in full, the current one by default; board citations carry their label), status, view}."""
    st = store.get_state(case_id)
    cur = case_summary.current(st)
    try:
        v = case_summary._version(st, n) if (cur and n is not None) else cur
    except KeyError as e:
        common.fail(404, str(e).strip("'\""), "no_version")
    return {"current": cur.get("n") if cur else None, "versions": case_summary.history(st), "version": case_summary.display(case_id, st, v) if v else None,
            "status": case_summary.status(st, case_id), "view": case_summary.view(case_id, st, rl, v.get("n")) if v else None}


@router.get("/cases/{case_id}/case-summary")
async def get_case_summary(case_id: str, request: Request, n: str = ""):
    """{current, versions[{n, built_at, trigger, review, edits, sentences}], version (version n in full with ?n=, else the current one),
    status, view (the CaseSummaryView of that version, as the steps view gives it)}. Nothing is written on a read: the current version's
    status section is worked out for display (case_summary.display), so "overdue" stays true."""
    rl = common.roles(request); _full(request, case_id)
    return _view(case_id, rl, _n(n) if str(n).strip() else None)


@router.post("/cases/{case_id}/case-summary")
async def post_case_summary(case_id: str, request: Request):
    """Build a new version now {"force"?}: the owning department's doctors or the MDT Coordinator. 409 no_decision without a board record."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id); common.need_known(rl)
    if not (org.can(rl, "list_case") or access.may(rl, "upload_to_case", c)):  # the same rule as POST /cases/{id}/summary
        common.fail(403, "Only the doctors of the owning department or the MDT Coordinator write the Case summary", "forbidden")
    b = await common.body(request) if (await request.body()) else {}
    try:  # no lock around the model calls: build reads again and writes without an await in between, as POST /summary does (review M6)
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


@router.post("/cases/{case_id}/summary-line")
async def post_summary_line(case_id: str, request: Request):
    """{text}: the summary line of the Case File (night-v3 item 3.4), the owning department's consultants only; at most 160 characters;
    an empty text goes back to the Vaidyx line. Audited (summary_line_edit). Returns {summary_line}."""
    u = common.user(request); rl = common.roles(request); c = _full(request, case_id)
    if not access.is_owner_doctor(rl, c):
        common.fail(403, "Only the owning department's consultants edit the summary line", "forbidden")
    b = await common.body(request)
    async with store.lock(case_id):
        try:
            from tumour_board.slots import display_name
            return {"summary_line": case_summary.edit_line(case_id, b.get("text") or "", u, display_name(u))}
        except LookupError as e:
            common.fail(409, str(e), "no_case_summary")
        except ValueError as e:
            common.fail(400, str(e), "invalid")
