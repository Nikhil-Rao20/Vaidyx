"""Ask PubMed on the platform (docs/pubmed-ask/DESIGN.md section 8, owner "go ahead" of 3 Nov 2026): a question runs as a job, so
the screen can show PubMed's steps live (start, then poll), and every answer is kept as a thread.

Jobs live in memory only: one asyncio task on the running loop each, at most MAX_RUNNING running per login, forgotten JOB_TTL after
they started; only the login that started a job may read it. A job runs pubmed_ask.ask (the only way a paper enters an answer) and
saves the result as a thread:
- in a Case File: cases/<id>/pubmed_threads.json (MAX_CASE threads), shared with whoever may read it (may_read: the team chat's readers,
  or an admitted member of a running meeting while the Case File is on the floor); the search may use the cancer and the documented
  terms (histology, stage as written, biomarkers), never an identifier; the patient's name and numbers are refused in the question;
- on Home: data/tumour_board/pubmed_home/<login>.json (MAX_HOME threads, file mode 600), the login's own history, no patient context.
The screen never gets a provenance URL; the stored thread keeps each PubMed call's SHA-256 (what PubMed sent can be traced). Any
exception in a job becomes a thread with status "unavailable" and a short reason, never a server error. Audited "pubmed_asked" (the
Case File's log, or the organisation log for Home): who, the question, the words sent, the status and the counts. No model call here."""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
import uuid

from . import config, org, published, pubmed_ask, store

FILE = "pubmed_threads.json"
HOME_DIR = "pubmed_home"
MAX_CASE = 300
MAX_HOME = 100
JOB_TTL = 15 * 60
JOB_TIMEOUT = 5 * 60  # a job that hangs (PubMed and the model have their own time-outs) still ends and frees its place
MAX_RUNNING = 2
MIN_QUESTION, MAX_QUESTION = 3, pubmed_ask.MAX_QUESTION
YEARS = (None, 5, 10)
STATUSES = ("answered", "not_found", "no_papers", "refused", "unavailable")
THREAD_ID = re.compile(r"^PM[0-9a-f]{8}$")
JOB_ID = re.compile(r"^J[0-9a-f]{32}$")
PMID = re.compile(r"^\d{1,12}$")

CRASHED = "Ask PubMed could not finish this question ({reason}). Try again in a minute."
TIMED_OUT = "Ask PubMed took longer than 5 minutes. Try again in a minute."
BUSY = "Two of your PubMed questions are still running. Wait for one to finish, then ask again."
NOT_CLINICAL = ("Ask PubMed is for doctors, residents, the MDT Coordinator and outside experts. "
                "An admin, auditor or department admin login does not ask it.")
NOT_READER = ("Ask PubMed in a Case File is for its treating team and the MDT Coordinator, and for the members of a running meeting "
              "while the Case File is on the floor.")

THREAD_KEYS = ("id", "kind", "by", "by_name", "at", "question", "status", "message", "label", "search", "statements", "papers", "counts",
               "model", "seconds", "dropped", "invented_pmids", "pinned", "saved_pmids")
PAPER_KEYS = ("pmid", "title", "journal", "journal_abbr", "year", "authors_line", "study_type", "tier", "preprint", "retracted",
              "retraction_notice", "concern", "india", "doi", "pmcid", "url", "has_abstract", "read", "why_not_read", "cited", "rank")
CALL_KEYS = ("what", "at", "status", "bytes", "sha256", "tries", "seconds", "cached")  # never the request URL

# documented terms a Case File question may add to the search words (first value of each, as the record writes it)
TERM_FACTS = (("histologic_type", "histology"), ("recorded_stage", "stage"), ("figo_stage", "FIGO stage"), ("er", "ER"), ("pr", "PR"),
              ("her2", "HER2"), ("grade", "grade"), ("ki67", "Ki-67"), ("egfr", "EGFR"), ("alk", "ALK"), ("ros1", "ROS1"),
              ("pdl1", "PD-L1"), ("kras", "KRAS"), ("mmr", "MMR"))
MAX_TERM = 80

_lock = threading.Lock()       # the thread files
_jobs_lock = threading.Lock()  # the job registry
_jobs: dict = {}


class Busy(Exception):
    """The login already has MAX_RUNNING questions running."""


# ---- who may ask ------------------------------------------------------------------------------------------------------------------

def clinical(roles) -> bool:
    """A clinical login asks on Home: a doctor or resident placed in a department, the MDT Coordinator or an outside expert; never a
    login that only administers (Vaidyx admin, root admin, department admin) or audits, never a disabled or expired one."""
    if not isinstance(roles, dict) or roles.get("disabled") or roles.get("expired"):
        return False
    return bool(roles.get("departments") or roles.get("coordinator") or roles.get("outside_expert"))


def may_read(roles, case, scope=None) -> bool:
    """A Case File's PubMed threads: whoever may read its team chat (chats.may_read), or a login admitted to a running meeting while
    this Case File is on the floor (access.meeting_window); never a department that was only asked (REQUESTS)."""
    from . import access, chats
    if not isinstance(case, dict):
        return False
    sc = access.scope(roles, case) if scope is None else scope
    if sc not in (access.FULL, access.READ):
        return False
    if chats.may_read(roles, sc):
        return True
    return access.meeting_window(roles, case) is not None


# ---- the Case File's context (never an identifier) -----------------------------------------------------------------------------------

def _clean_term(v, identifiers) -> str:
    t = " ".join(str(v or "").split())[:MAX_TERM]
    if not t or pubmed_ask.IDENT_RX.search(t) or any(pubmed_ask._has_identifier(t.lower(), i) for i in identifiers):
        return ""
    return t


def case_context(case, state=None) -> dict:
    """{"cancer", "terms"} for the search words: the Case File's cancer (its checklist's label, or the name a doctor typed under the
    generic checklist) and the first documented value of a few facts the gate already holds. A term with a date, a long number or an
    identifier of this patient is left out."""
    from . import protocol
    case = case if isinstance(case, dict) else {}
    idents = published._identifiers(case)
    pid = str(case.get("protocol") or "")
    cancer = ""
    if pid in protocol.GENERIC_IDS:
        cancer = case.get("cancer_name") or ""
    elif pid:
        try:
            cancer = protocol.get(pid).get("label") or ""
        except Exception:  # an unknown checklist: no cancer named, the question's own words still search
            cancer = ""
    st = state if isinstance(state, dict) else store.get_state(case.get("case_id")) if case.get("case_id") else {}
    gate = (st or {}).get("gate") if isinstance((st or {}).get("gate"), dict) else {}
    found: dict = {}
    for row in list(gate.get("core_data") or []) + list(gate.get("requirements") or []):
        for e in (row.get("evidence") or []) if isinstance(row, dict) else []:
            if isinstance(e, dict) and e.get("fact") and e.get("fact") not in found:
                t = _clean_term(e.get("value"), idents)
                if t:
                    found[e["fact"]] = t
    terms = [f"{label}: {found[f]}" for f, label in TERM_FACTS if f in found]
    return {"cancer": _clean_term(cancer, idents), "terms": terms}


# ---- the thread -------------------------------------------------------------------------------------------------------------------

def _citation(c) -> dict:
    out = {"pmid": str(c.get("pmid") or ""), "quote": str(c.get("quote") or ""), "where": str(c.get("where") or "")}
    for k in ("whole_sentence", "added_for_numbers"):
        if c.get(k):
            out[k] = True
    return out


def _paper(p) -> dict:
    """A paper as stored: the screen's fields plus the SHA-256 of the PubMed answer it came from (no URL of the call)."""
    prov = p.get("provenance") if isinstance(p.get("provenance"), dict) else {}
    out = {k: p.get(k) for k in PAPER_KEYS}
    out["cited"] = bool(p.get("cited"))
    out["sha256"] = str(prov.get("sha256") or "")
    out["cached"] = bool(prov.get("cached"))
    return out


def build(res: dict, user: str, years=None) -> dict:
    """The stored thread from pubmed_ask.ask's result."""
    from . import chats
    res = res if isinstance(res, dict) else {}
    s = res.get("search") if isinstance(res.get("search"), dict) else {}
    counts = res.get("counts") if isinstance(res.get("counts"), dict) else {}
    counts = {k: int(counts.get(k) or 0) for k in ("found", "fetched", "read")}
    status = res.get("status") if res.get("status") in STATUSES else "unavailable"
    return {
        "id": "PM" + uuid.uuid4().hex[:8], "kind": "pubmed", "by": user, "by_name": chats.display_name(user), "at": store.now_iso(),
        "question": str(res.get("question") or ""), "status": status, "message": str(res.get("message") or ""), "label": str(res.get("label") or ""),
        "search": {"used": str(s.get("used") or ""), "years": s.get("years", years) if s else years, "by": str(s.get("by") or ""),
                   "count": counts["found"],
                   "attempts": [{"term": str(a.get("term") or ""), "years": a.get("years"), "count": int(a.get("count") or 0)}
                                for a in s.get("attempts") or [] if isinstance(a, dict)]},
        "statements": [{"text": str(x.get("text") or ""), "citations": [_citation(c) for c in x.get("citations") or [] if isinstance(c, dict)]}
                       for x in res.get("statements") or [] if isinstance(x, dict)],
        "papers": [_paper(p) for p in res.get("papers") or [] if isinstance(p, dict)],
        "counts": counts, "model": str(res.get("model") or ""), "seconds": res.get("seconds"),
        "dropped": len(res.get("removed") or []), "invented_pmids": int(res.get("invented_pmids") or 0), "pinned": False, "saved_pmids": [],
        # kept on disk only: what PubMed sent (SHA-256 per call) and why lines were dropped
        "calls": [{k: c.get(k) for k in CALL_KEYS if k in c} for c in res.get("calls") or [] if isinstance(c, dict)],
        "dropped_reasons": [str(x.get("reason") or "")[:200] for x in res.get("removed") or [] if isinstance(x, dict)],
    }


def public(t: dict) -> dict:
    """The thread as the screen gets it: the contract's fields only (no call provenance, no hashes)."""
    out = {k: t.get(k) for k in THREAD_KEYS}
    out["papers"] = [{k: p.get(k) for k in PAPER_KEYS} for p in t.get("papers") or [] if isinstance(p, dict)]
    out["pinned"] = bool(t.get("pinned"))
    out["saved_pmids"] = list(t.get("saved_pmids") or [])
    return out


def _failed(question: str, in_case_file: bool, message: str, seconds: float) -> dict:
    try:
        model = pubmed_ask.model_line()
    except Exception:
        model = ""
    return {"question": question, "label": pubmed_ask.LABEL if in_case_file else pubmed_ask.LABEL_HOME, "status": "unavailable",
            "message": message, "search": {}, "statements": [], "removed": [], "invented_pmids": 0, "papers": [],
            "counts": {"found": 0, "fetched": 0, "read": 0}, "calls": [], "model": model, "seconds": round(seconds, 2)}


# ---- storage ----------------------------------------------------------------------------------------------------------------------

def _case_path(case_id):
    return store.case_dir(case_id) / FILE


def _load(path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("threads"), list):
        data = {"threads": []}
    return data


def home_path(user: str):
    """One file per login; a login with other characters gets a hashed name (never a path from the login itself)."""
    u = str(user or "")
    name = u if re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,63}", u) else "h-" + hashlib.sha256(u.encode("utf-8")).hexdigest()[:40]
    return config.DATA_ROOT / HOME_DIR / f"{name}.json"


def _write_private(path, data) -> None:
    """Mode 600 from the first byte (the folder 700): a doctor's own questions are read by that login's routes only."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _trim(threads: list, cap: int) -> list:
    """The newest `cap` threads; the oldest unpinned go first."""
    if len(threads) <= cap:
        return threads
    keep = [x for x in threads if x.get("pinned")]
    rest = [x for x in threads if not x.get("pinned")]
    return sorted(keep + rest[-max(0, cap - len(keep)):], key=lambda x: x.get("at") or "")[-cap:]


def save_thread(t: dict, case_id: str | None, user: str) -> bool:
    """Append the thread to the Case File's list or the login's Home history. False when the Case File was deleted meanwhile."""
    with _lock:
        if case_id:
            if store._dropped(case_id, FILE):
                return False
            data = _load(_case_path(case_id))
            data["threads"] = _trim(data["threads"] + [t], MAX_CASE)
            store._write_json(_case_path(case_id), data)
        else:
            p = home_path(user)
            data = _load(p)
            data["threads"] = _trim(data["threads"] + [t], MAX_HOME)
            _write_private(p, data)
    return True


def _ordered(rows: list, pinned_first: bool) -> list:
    rows = [(i, t) for i, t in enumerate(rows) if isinstance(t, dict)]  # the file order breaks ties within one second
    rows.sort(key=lambda x: ((bool(x[1].get("pinned")) if pinned_first else False), x[1].get("at") or "", x[0]), reverse=True)
    return [public(t) for _, t in rows]


def case_threads(case_id) -> list:
    """Pinned first, newest first."""
    return _ordered(_load(_case_path(case_id))["threads"], True)


def home_threads(user) -> list:
    """Newest first."""
    return _ordered(_load(home_path(user))["threads"], False)


def case_thread(case_id, thread_id) -> dict | None:
    return next((t for t in _load(_case_path(case_id))["threads"] if isinstance(t, dict) and t.get("id") == thread_id), None)


def home_thread(user, thread_id) -> dict | None:
    return next((t for t in _load(home_path(user))["threads"] if isinstance(t, dict) and t.get("id") == thread_id), None)


def pin(case_id, thread_id, pinned, user) -> dict:
    """KeyError when the thread is not in this Case File."""
    with _lock:
        data = _load(_case_path(case_id))
        t = next((x for x in data["threads"] if isinstance(x, dict) and x.get("id") == thread_id), None)
        if not t:
            raise KeyError(thread_id)
        t["pinned"] = bool(pinned)
        t["pinned_by"] = user if pinned else None
        store._write_json(_case_path(case_id), data)
    store.audit(case_id, {"kind": "pubmed_pinned" if pinned else "pubmed_unpinned", "by": user, "thread": thread_id})
    return public(t)


def _kind(study_type: str) -> str:
    return {"Preprint": "preprint", "Book chapter": "book", "Guideline": "guideline"}.get(str(study_type or ""), "paper")


def _where(where: str) -> str:
    w = str(where or "")
    return w if w in ("Title", "Abstract") else f"Abstract, {w}" if w else "Abstract"


def save_to_published(case_id, thread_id, pmid, user) -> dict:
    """The paper of this thread into the Case File's Published list (published.add: source "pubmed", the kind from its study type, the
    thread's verified quotes of that PMID as its quotes). KeyError: no such thread; LookupError: the paper is not in it;
    published.PublishedError: the Published list refused it (already there, full)."""
    t = case_thread(case_id, thread_id)
    if not t:
        raise KeyError(thread_id)
    p = next((x for x in t.get("papers") or [] if isinstance(x, dict) and x.get("pmid") == pmid), None)
    if not p:
        raise LookupError(pmid)
    quotes, seen = [], set()
    for s in t.get("statements") or []:
        for c in s.get("citations") or []:
            if c.get("pmid") == pmid and c.get("quote") and c["quote"] not in seen:
                seen.add(c["quote"])
                quotes.append({"text": c["quote"], "where": _where(c.get("where"))})
    kind = _kind(p.get("study_type"))
    doi = str(p.get("doi") or "").strip()
    result = {"title": p.get("title") or "", "authors": p.get("authors_line") or "", "journal": p.get("journal") or p.get("journal_abbr") or "",
              "year": p.get("year") or "", "doi": doi if published._DOI.match(doi) else "",  # an odd DOI in PubMed's record: the PMID link stays
              "url": p.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
              "source": "pubmed", "source_id": pmid, "pmid": pmid, "peer_reviewed": kind not in ("preprint", "book"), "kind": kind,
              "note": "Saved from Ask PubMed: the quotes are the abstract's own words, checked word for word."}
    item = published.add(case_id, result, quotes[:published.MAX_QUOTES], user)
    with _lock:
        data = _load(_case_path(case_id))
        x = next((y for y in data["threads"] if isinstance(y, dict) and y.get("id") == thread_id), None)
        if x is not None and pmid not in (x.get("saved_pmids") or []):
            x["saved_pmids"] = list(x.get("saved_pmids") or []) + [pmid]
            store._write_json(_case_path(case_id), data)
    return item


# ---- what voice reads -------------------------------------------------------------------------------------------------------------

def _first_author(p) -> str:
    return str((p or {}).get("authors_line") or "").split(", ")[0].strip()


def _journal(p) -> str:
    j = str((p or {}).get("journal") or "").split(" : ")[0].strip()  # the subtitle of a journal's name is not read
    return j or str((p or {}).get("journal_abbr") or "").strip()


def speech(t: dict) -> str:
    """"From PubMed." then each line followed by the first author, journal and year of its first cited paper; a thread without lines
    reads its message as the screen shows it."""
    papers = {p.get("pmid"): p for p in t.get("papers") or [] if isinstance(p, dict)}
    lines = []
    for s in t.get("statements") or []:
        text = " ".join(str((s or {}).get("text") or "").split()).rstrip(" .")
        if not text:
            continue
        c = next((x for x in s.get("citations") or [] if isinstance(x, dict) and x.get("pmid") in papers), None)
        p = papers.get(c["pmid"]) if c else None
        who = ", ".join(x for x in (_first_author(p), _journal(p), str((p or {}).get("year") or "")) if x)
        lines.append(f"{text} ({who})." if who else f"{text}.")
    if lines:
        return "From PubMed. " + " ".join(lines)
    msg = str(t.get("message") or "").strip()
    if t.get("status") in ("not_found", "no_papers"):
        return "From PubMed. " + (msg or pubmed_ask.NOT_FOUND)
    return msg


# ---- jobs -------------------------------------------------------------------------------------------------------------------------

def _prune(now: float) -> None:
    for k in [k for k, j in _jobs.items() if j["status"] != "running" and now - j["started"] > JOB_TTL]:
        _jobs.pop(k, None)


def running(user) -> int:
    with _jobs_lock:
        return sum(1 for j in _jobs.values() if j["user"] == user and j["status"] == "running")


def start(question: str, user: str, *, case_id: str | None = None, years=None) -> dict:
    """Start one question as a task on the running loop. Busy when the login already has MAX_RUNNING running. The caller checked
    who may ask and the input."""
    case = store.get_case(case_id) if case_id else None
    context = case_context(case) if case else None  # read before the job counts, so a failure here never holds a place
    identifiers = published._identifiers(case) if case else ()
    loop = asyncio.get_running_loop()
    now = time.time()
    with _jobs_lock:
        _prune(now)
        if sum(1 for j in _jobs.values() if j["user"] == user and j["status"] == "running") >= MAX_RUNNING:
            raise Busy(BUSY)
        job = {"id": "J" + uuid.uuid4().hex, "user": user, "case_id": case_id or None, "status": "running", "steps": [], "thread": None,
               "error": None, "started": now, "task": None}
        _jobs[job["id"]] = job
        job["task"] = loop.create_task(_run(job, question, context, identifiers, years))  # kept here so the task is never collected
    return job


async def _run(job: dict, question: str, context, identifiers, years) -> None:
    t0 = time.time()
    case_id, user = job["case_id"], job["user"]
    model_calls = [0]

    def on_step(step, detail=""):
        with _jobs_lock:
            job["steps"].append({"step": str(step), "detail": str(detail), "seconds": round(time.time() - t0, 2)})

    def audit(ev):  # the model calls go to the Case File's log like every other question; the pipeline's own line is pubmed_asked below
        if not isinstance(ev, dict) or ev.get("kind") == "pubmed_ask":
            return
        model_calls[0] += ev.get("kind") == "llm_call"
        if case_id:
            store.audit(case_id, {**ev, "by": user})

    failed = ""
    try:
        res = await asyncio.wait_for(pubmed_ask.ask(question, context=context, identifiers=identifiers, in_case_file=bool(case_id),
                                                    years=years, on_step=on_step, audit=audit), JOB_TIMEOUT)
        if not isinstance(res, dict):
            raise TypeError("no answer")
    except asyncio.TimeoutError:
        failed = TIMED_OUT
    except Exception as e:  # never a server error: the doctor sees why and may ask again
        failed = CRASHED.format(reason=e.__class__.__name__)
    if failed:
        res = _failed(question, bool(case_id), failed, time.time() - t0)
    try:
        t = build(res, user, years)
        saved = save_thread(t, case_id, user)
        _audit(t, case_id, user, model_calls[0])
        with _jobs_lock:
            job.update(thread=public(t), status="failed" if failed else "done", error=failed or None)
            if not saved:
                job.update(status="failed", error="The Case File was deleted while PubMed was searched.")
    except Exception as e:
        with _jobs_lock:
            job.update(status="failed", error=CRASHED.format(reason=e.__class__.__name__))
    finally:
        with _jobs_lock:
            if job["status"] == "running":
                job.update(status="failed", error=CRASHED.format(reason="stopped"))
            job["task"] = None


def _audit(t: dict, case_id, user, model_calls: int) -> None:
    fields = {"thread": t["id"], "question": t["question"][:300], "words": t["search"]["used"], "years": t["search"]["years"],
              "status": t["status"], "found": t["counts"]["found"], "read": t["counts"]["read"], "statements": len(t["statements"]),
              "dropped": t["dropped"], "seconds": t["seconds"], "model_calls": model_calls}
    if case_id:
        store.audit(case_id, {"kind": "pubmed_asked", "by": user, **fields})
    else:
        org.audit("pubmed_asked", user, **fields)


def job_view(job_id, user) -> dict | None:
    """The job for the login that started it; None for anyone else, an unknown id or a job past JOB_TTL."""
    with _jobs_lock:
        _prune(time.time())
        j = _jobs.get(str(job_id or ""))
        if not j or j["user"] != user:
            return None
        out = {"job_id": j["id"], "status": j["status"], "steps": [dict(s) for s in j["steps"]]}
        if j["thread"] is not None:
            out["thread"] = j["thread"]
        if j["error"]:
            out["error"] = j["error"]
        return out


def reset() -> None:
    """Tests: forget every job."""
    with _jobs_lock:
        _jobs.clear()
