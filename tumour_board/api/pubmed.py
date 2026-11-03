"""Ask PubMed routes (docs/pubmed-ask/DESIGN.md section 8): a question starts a job (202 {job_id}) and the screen polls it for PubMed's
steps and then the thread. Home: any clinical login, its own history. Case File: the team chat's readers, or an admitted member of a
running meeting while the Case File is on the floor; never a department that was only asked. Save to Published: the owning
department's consultants, as POST /cases/{id}/published. 12 questions per 10 minutes per login over both ask routes."""
from fastapi import Request

from tumour_board import access, published
from tumour_board import pubmed_threads as pt

from . import common
from .published import _owner_consultant

router = common.make_router()
ASK_LIMIT = common.RateLimit(12, 600)  # both ask routes together, per login
NO_JOB = "No such question. It may have finished more than 15 minutes ago."
NO_THREAD = "That PubMed answer is not in this Case File."


def _case_reader(request, case_id, write=False):
    """(user, roles, case) for whoever may read this Case File's PubMed threads; a 403 with the reason otherwise."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id)
    sc = common.scope(request)
    if sc == access.REQUESTS or not pt.may_read(rl, c, sc):
        common.fail(403, pt.NOT_READER, "pubmed_forbidden")
    if write and rl.get("vaidyx_admin"):  # a break-glass window reads; it never adds to the team's list
        common.fail(403, "A break-glass window is read only: the Vaidyx admin reads the Case File, the owning department acts on it.",
                    "break_glass_read_only")
    return u, rl, c


async def _question(request) -> tuple:
    """(question, years) from {question, years?}: 3 to 600 characters after trimming; years all (null), 5 or 10."""
    b = await common.body(request)
    q = b.get("question")
    q = " ".join(q.split()) if isinstance(q, str) else ""
    if not pt.MIN_QUESTION <= len(q) <= pt.MAX_QUESTION:
        common.fail(400, f"Type a question of {pt.MIN_QUESTION} to {pt.MAX_QUESTION} characters.", "bad_question")
    years = b.get("years")
    if isinstance(years, bool) or years not in pt.YEARS:
        common.fail(400, "Choose all years, the last 10 years or the last 5 years.", "bad_years")
    return q, years


def _start(u, q, years, case_id=None) -> dict:
    if pt.running(u) >= pt.MAX_RUNNING:  # checked before the rate limit, so a refused question does not use up the login's count
        common.fail(429, pt.BUSY, "too_many_running")
    ASK_LIMIT.check(u, "Too many PubMed questions in a short time (12 in 10 minutes). Please wait a few minutes.")
    try:
        job = pt.start(q, u, case_id=case_id, years=years)
    except pt.Busy:
        common.fail(429, pt.BUSY, "too_many_running")
    return {"job_id": job["id"]}


@router.post("/pubmed/ask", status_code=202)
async def ask_home(request: Request):
    """{question, years?} -> 202 {job_id}. Home: no patient context, labelled "not advice for any patient"."""
    u = common.user(request); rl = common.roles(request)
    if not pt.clinical(rl):
        common.fail(403, pt.NOT_CLINICAL, "not_clinical")
    q, years = await _question(request)
    return _start(u, q, years)


@router.get("/pubmed/history")
async def history(request: Request):
    """{threads[]}: the login's own Home questions, newest first (the last 100 kept)."""
    u = common.user(request)
    return {"threads": pt.home_threads(u)}


@router.get("/pubmed/jobs/{job_id}")
async def job(job_id: str, request: Request):
    """{job_id, status: running|done|failed, steps[{step, detail, seconds}], thread?, error?}; only for the login that started it."""
    u = common.user(request)
    v = pt.job_view(job_id, u) if pt.JOB_ID.match(job_id or "") else None
    if v is None:
        common.fail(404, NO_JOB, "no_job")
    return v


@router.post("/cases/{case_id}/pubmed/ask", status_code=202)
async def ask_case(case_id: str, request: Request):
    """{question, years?} -> 202 {job_id}. The search may use the cancer and the documented terms; the patient's name and numbers are
    refused in the question and never sent."""
    u, rl, c = _case_reader(request, case_id, write=True)
    q, years = await _question(request)
    return _start(u, q, years, case_id=str(c.get("case_id") or case_id))


@router.get("/cases/{case_id}/pubmed")
async def list_threads(case_id: str, request: Request):
    """{threads[]}: pinned first, newest first; the whole team sees them."""
    u, rl, c = _case_reader(request, case_id)
    return {"threads": pt.case_threads(str(c.get("case_id") or case_id))}


@router.post("/cases/{case_id}/pubmed/{thread_id}/pin")
async def pin(case_id: str, thread_id: str, request: Request):
    """{pinned} -> the thread."""
    u, rl, c = _case_reader(request, case_id, write=True)
    b = await common.body(request) if (await request.body()) else {}
    if not pt.THREAD_ID.match(thread_id or ""):
        common.fail(404, NO_THREAD, "no_thread")
    try:
        return pt.pin(str(c.get("case_id") or case_id), thread_id, bool(b.get("pinned", True)), u)
    except KeyError:
        common.fail(404, NO_THREAD, "no_thread")


@router.post("/cases/{case_id}/pubmed/{thread_id}/save")
async def save(case_id: str, thread_id: str, request: Request):
    """{pmid} -> the Published item (source pubmed, the thread's verified quotes of that paper), as POST /cases/{id}/published: the
    owning department's consultants."""
    u = common.user(request); rl = common.roles(request); c = common.case(case_id); _owner_consultant(rl, c)
    b = await common.body(request)
    pmid = str(b.get("pmid") or "").strip()
    if not pt.PMID.match(pmid):
        common.fail(400, "Say which paper to save (its PMID).", "bad_pmid")
    if not pt.THREAD_ID.match(thread_id or ""):
        common.fail(404, NO_THREAD, "no_thread")
    try:
        return pt.save_to_published(str(c.get("case_id") or case_id), thread_id, pmid, u)
    except KeyError:
        common.fail(404, NO_THREAD, "no_thread")
    except LookupError:
        common.fail(404, "That paper is not in this PubMed answer.", "no_paper")
    except published.PublishedError as e:
        common.fail(e.status, str(e), "published_" + str(e.status))
