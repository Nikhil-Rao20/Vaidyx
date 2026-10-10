"""Orchestration: ingestion jobs (parallel document processing with live progress), Pre-Authorization re-check,
demo case import, expert reviews."""
import asyncio, json, logging, time, uuid
from pathlib import Path

from . import config, extract, ingest, rules, store

log = logging.getLogger("tumour_board")

JOBS: dict[str, dict] = {}  # in-memory fast path; every job is also saved to data/tumour_board/jobs/<id>.json (V1 item 1.8)
JOB_MAX_AGE = 24 * 3600  # seconds; older jobs are dropped from memory and from disk
STUCK_STATES = ("queued", "reading", "classifying", "extracting")  # a document in one of these after a restart was cut off mid-processing
RESTART_USER = "system:restart"


def _jobs_dir() -> Path:
    d = config.DATA_ROOT / "jobs"  # derived at call time: tests point config.DATA_ROOT at a temporary folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_job(job):
    """Write the job record (everything except the asyncio task) to jobs/<id>.json. Never raises: progress must not stop on a disk error."""
    try:
        store._write_json(_jobs_dir() / f"{store.safe_id(job['id'])}.json", {k: v for k, v in job.items() if k != "task"})
    except Exception:
        log.exception("could not save job %s", job.get("id"))


def _read_job_file(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def get_job(job_id):
    """The job record (without the task): in memory first, then on disk (after a restart), else None."""
    j = JOBS.get(job_id)
    if j is not None:
        return {k: v for k, v in j.items() if k != "task"}
    try:
        p = _jobs_dir() / f"{store.safe_id(job_id)}.json"
    except ValueError:
        return None
    return _read_job_file(p) if p.exists() else None


def _prune():
    """Drop in-memory jobs started more than 24 h ago and delete their files on disk, so neither grows without bound. Returns the count removed."""
    cutoff = time.time() - JOB_MAX_AGE
    removed = set()
    for jid in [k for k, j in JOBS.items() if j.get("started", 0) < cutoff]:
        JOBS.pop(jid, None); removed.add(jid)
    try:
        for p in _jobs_dir().glob("*.json"):
            rec = _read_job_file(p)
            try:
                started = float(rec["started"]) if isinstance(rec, dict) and "started" in rec else p.stat().st_mtime
            except (TypeError, ValueError, OSError):
                started = 0
            if started < cutoff:
                p.unlink(missing_ok=True); removed.add(p.stem)
    except Exception:
        log.exception("could not prune job files")
    return len(removed)


def _job(case_id, total, doc_ids=None):
    _prune()
    jid = "J" + uuid.uuid4().hex[:8]
    started = time.time()
    JOBS[jid] = {"id": jid, "case_id": case_id, "total": total, "done": 0, "events": [], "state": "running", "started": started, "doc_states": {},
                 "started_iso": store.now_iso(), "doc_ids": list(doc_ids or [])}
    _save_job(JOBS[jid])
    return JOBS[jid]


async def process_docs(case_id, doc_ids, job):
    case = store.get_case(case_id)

    def progress(doc_id, state):
        job["doc_states"][doc_id] = state
        job["events"].append({"t": round(time.time() - job["started"], 2), "doc_id": doc_id, "state": state})
        if state in ("ready", "error"):
            job["done"] += 1
        _save_job(job)

    try:
        await asyncio.gather(*[extract.process_document(case_id, d, case["protocol"], case.get("patient"), progress) for d in doc_ids])
        async with store.lock(case_id):
            gate = rules.evaluate(case_id)
            rules.sync_actions(case_id, gate)
    except Exception as e:  # the UI polls this job: it must reach a terminal state
        job["state"] = "failed"; job["error"] = f"{e.__class__.__name__}: {str(e)[:300]}"; job["seconds"] = round(time.time() - job["started"], 1)
        _save_job(job)
        store.audit(case_id, {"kind": "error", "where": "ingestion", "error": job["error"]})
        return
    try:  # warm the search index (chunk embeddings) so the first search is instant
        from . import search
        await asyncio.to_thread(search.index, case_id)
    except Exception:
        pass
    job["state"] = "finished"; job["seconds"] = round(time.time() - job["started"], 1); job["gate"] = {k: gate[k] for k in ("passed", "readiness", "satisfied", "total")}
    _save_job(job)
    store.audit(case_id, {"kind": "ingestion_finished", "documents": len(doc_ids), "seconds": job["seconds"], "gate_passed": gate["passed"], "readiness": gate["readiness"]})


def add_files(case_id, files, user=""):
    """files: list of (relative_path, bytes). Identical files already in the Case File are skipped (SHA-256); files that cannot be
    read are refused (job["unsupported"]: file + reason, audited) and never stored. Returns a job (processing runs in the background)."""
    ids, skipped, unsupported = [], [], []
    for rel, data in files:
        reason = ingest.reject_reason(rel)  # .doc / .rtf / .odt without LibreOffice: refused with a clear message (V1 item 1.4)
        if reason is None and (Path(rel).suffix.lower() not in ingest.SUPPORTED or Path(rel).name.startswith(".")):
            reason = "Unsupported file type"
        if reason:
            unsupported.append({"file": rel, "reason": reason})
            store.audit(case_id, {"kind": "document_rejected", "file": rel, "reason": reason, "by": user}); continue
        dup = store.find_duplicate(case_id, data)
        if dup:
            skipped.append({"file": rel, "same_as": dup["doc_id"]})
            store.audit(case_id, {"kind": "document_duplicate_skipped", "file": rel, "same_as": dup["doc_id"], "by": user}); continue
        d = store.add_document_file(case_id, Path(rel).name, data, rel)
        ids.append(d["doc_id"])
        store.audit(case_id, {"kind": "document_added", "doc_id": d["doc_id"], "file": rel, "by": user})
    job = _job(case_id, len(ids), ids)
    job["skipped_duplicates"], job["unsupported"] = skipped, unsupported
    _save_job(job)
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job))
    return job


def reprocess(case_id, which="errors", user=""):
    """Re-run reading / classification / extraction. which = 'errors' | 'all' | list of doc ids. Needed after a protocol
    or model change, or to retry documents that failed."""
    docs = store.list_docs(case_id)
    if which == "all":
        ids = [d["doc_id"] for d in docs]
    elif which == "errors":
        ids = [d["doc_id"] for d in docs if d.get("state") != "ready"]
    else:
        ids = [d for d in which if any(x["doc_id"] == d for x in docs)]
    for i in ids:
        d = store.get_doc(case_id, i); d["state"] = "queued"; d.pop("error", None); store.save_doc(case_id, d)
    store.audit(case_id, {"kind": "reprocess", "documents": ids, "by": user})
    job = _job(case_id, len(ids), ids)
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job))
    return job


def resume_after_restart():
    """Start-up hook (V1 item 1.8), called once from the app's async start-up while the event loop runs. Jobs that were running
    when the server stopped are marked interrupted; documents left mid-processing (queued / reading / classifying / extracting)
    are queued again, one job per case. Documents that are ready or in error are never touched. Never raises: a broken case
    folder is logged and skipped so the app still starts."""
    out = {"requeued": {}, "interrupted_jobs": [], "pruned": 0}
    try:
        out["pruned"] = _prune()
    except Exception:
        log.exception("resume_after_restart: prune failed")
    interrupted = {}  # case_id -> [job records]
    try:
        for p in sorted(_jobs_dir().glob("*.json")):
            rec = _read_job_file(p)
            if not isinstance(rec, dict) or rec.get("state") != "running" or rec.get("id") in JOBS:
                continue
            rec["state"] = "interrupted"; rec["error"] = "The server restarted; the documents were queued again automatically"
            rec["seconds"] = round(time.time() - float(rec.get("started") or time.time()), 1)
            _save_job(rec)
            out["interrupted_jobs"].append(rec["id"])
            interrupted.setdefault(rec.get("case_id"), []).append(rec)
    except Exception:
        log.exception("resume_after_restart: could not read job records")
    try:
        case_dirs = sorted(d for d in config.CASES_DIR.iterdir() if d.is_dir()) if config.CASES_DIR.exists() else []
    except Exception:
        log.exception("resume_after_restart: could not list case folders"); case_dirs = []
    for d in case_dirs:  # folder by folder (not store.list_cases()): one unreadable case.json must not hide the other cases
        try:
            c = store._read_json(d / "case.json")
            if not c:
                continue
            case_id = c["case_id"]
            stuck = [x["doc_id"] for x in store.list_docs(case_id) if x.get("state") in STUCK_STATES]
            if not stuck:
                continue
            job = reprocess(case_id, stuck, user=RESTART_USER)
            out["requeued"][case_id] = list(job["doc_ids"])
            store.audit(case_id, {"kind": "resume_after_restart", "documents": list(job["doc_ids"]), "by": RESTART_USER, "job": job["id"]})
            for rec in interrupted.get(case_id, []):
                rec["resumed_by"] = job["id"]; _save_job(rec)
            log.info("resume_after_restart: %s: queued %d document(s) again (job %s)", case_id, len(stuck), job["id"])
        except Exception:
            log.exception("resume_after_restart: skipped case folder %s", d.name)
    return out


def delete_document(case_id, doc_id, user=""):
    d = store.get_doc(case_id, doc_id)
    store.delete_document(case_id, doc_id)
    store.audit(case_id, {"kind": "document_deleted", "doc_id": doc_id, "file": (d or {}).get("rel_path"), "by": user})
    return recheck(case_id, user)


def recheck(case_id, user=""):
    """Re-evaluate the Pre-Authorization rules over the already-processed documents (deterministic, milliseconds) and
    re-sync the routed actions. Documents are NOT re-read here: use reprocess() for that."""
    before = store.get_state(case_id).get("gate") or {}
    gate = rules.evaluate(case_id)
    st = rules.sync_actions(case_id, gate, by=user)
    changed = [r["label"] for r in gate["requirements"] if {x["id"]: x["status"] for x in before.get("requirements", [])}.get(r["id"]) not in (None, r["status"])]
    st["recheck"] = {"documents_checked": gate["documents"]["ready"], "processing": gate["documents"]["processing"], "errors": gate["documents"]["errors"],
                     "satisfied": gate["satisfied"], "total": gate["total"], "passed": gate["passed"], "changed": changed,
                     "open_actions": sum(1 for a in st.get("actions", []) if a["status"] != "completed")}
    store.audit(case_id, {"kind": "recheck", "by": user, "passed": gate["passed"], "readiness": gate["readiness"], "changed": changed})
    return st


def import_demo(case_id, user=""):
    """Create a case from the synthetic demo corpus (documents are processed like any upload)."""
    src = config.DEMO_CORPUS / "cases" / case_id
    meta = json.loads((src / "case.json").read_text())
    if store.get_case(case_id):
        store.delete_case(case_id)
    store.create_case(case_id, meta["patient"], meta["protocol"], created_by=user)
    files = [(str(p.relative_to(src)), p.read_bytes()) for p in sorted(src.rglob("*")) if p.is_file() and p.name != "case.json"]
    return add_files(case_id, files, user)


def demo_arrivals(case_id, user=""):
    src = config.DEMO_CORPUS / "arrivals" / case_id
    if not src.exists():
        return None
    files = [(str(p.relative_to(src)), p.read_bytes()) for p in sorted(src.rglob("*")) if p.is_file()]
    return add_files(case_id, files, user)


def list_demo():
    base = config.DEMO_CORPUS / "cases"
    out = []
    for d in sorted(base.iterdir()) if base.exists() else []:
        if (d / "case.json").exists():
            m = json.loads((d / "case.json").read_text())
            out.append({**m, "files": len([p for p in d.rglob("*") if p.is_file()]) - 1, "has_arrivals": (config.DEMO_CORPUS / "arrivals" / d.name).exists()})
    return out


def review(case_id, artefact, status, comment, user):
    """Human oversight (expert-in-the-loop): mark an AI artefact reviewed, or flag it for correction."""
    st = store.get_state(case_id)
    a = st.get("artefacts", {}).get(artefact)
    if a is None:
        raise KeyError(artefact)
    a["review"] = {"status": status, "comment": comment, "by": user, "at": store.now_iso()}
    st.setdefault("reviews", []).append({"artefact": artefact, **a["review"]})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "expert_review", "artefact": artefact, "status": status, "by": user, "comment": comment})
    return a["review"]
