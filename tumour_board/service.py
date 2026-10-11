"""Orchestration: ingestion jobs (parallel document processing with live progress), Pre-Authorization re-check,
demo case import, expert reviews."""
import asyncio, json, logging, time, uuid
from pathlib import Path

from . import confirm, config, extract, ingest, intake, org, protocol, rules, store

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


async def process_docs(case_id, doc_ids, job, from_stored=False):
    case = store.get_case(case_id)

    def progress(doc_id, state):
        job["doc_states"][doc_id] = state
        job["events"].append({"t": round(time.time() - job["started"], 2), "doc_id": doc_id, "state": state})
        if state in ("ready", "error"):
            job["done"] += 1
        _save_job(job)

    try:
        kw = {"from_stored": True} if from_stored else {}  # documents filed from intake keep their stored pages and classification
        await asyncio.gather(*[extract.process_document(case_id, d, case.get("protocol"), case.get("patient"), progress, **kw) for d in doc_ids])
        case = store.get_case(case_id) or case  # the Case File may have been listed (or its patient record extended) meanwhile
        stale = [d["doc_id"] for d in store.list_docs(case_id) if d.get("state") == "ready" and d.get("pages") and "extracted_under" in d
                 and d["extracted_under"] != (case.get("protocol") or "")]
        if stale:  # extracted under a protocol that changed while they were in flight: once more from the stored pages
            await asyncio.gather(*[extract.process_document(case_id, d, case.get("protocol"), case.get("patient"), progress, from_stored=True) for d in stale])
        for d in store.list_docs(case_id):  # identifiers learned from other records may settle a document that printed only a CR No.
            if d.get("state") == "ready" and d.get("identity") in ("id_differs", "name_match"):
                extract.refresh_identity(case_id, d["doc_id"], (store.get_case(case_id) or case).get("patient"))
        async with store.lock(case_id):
            gate = rules.evaluate(case_id)  # None while the Case File is not listed (V1 item 2.5)
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
    job["state"] = "finished"; job["seconds"] = round(time.time() - job["started"], 1)
    job["gate"] = {k: gate[k] for k in ("passed", "readiness", "satisfied", "total")} if gate else None
    _save_job(job)
    store.audit(case_id, {"kind": "ingestion_finished", "documents": len(doc_ids), "seconds": job["seconds"], "gate_passed": gate["passed"] if gate else None,
                          "readiness": gate["readiness"] if gate else None})


def scan_warnings(case_id, doc_ids, user="", intake=False):
    """Big-scan warnings for stored documents (V1 item 3.7): counts the image-only pages without rendering. Pure file reading, so a
    route may run it in a thread (asyncio.to_thread) and attach the result with attach_warnings()."""
    out = []
    for doc_id in doc_ids:
        d = store.get_intake(doc_id) if intake else store.get_doc(case_id, doc_id)
        if not d:
            continue
        path = store.intake_original_path(doc_id) if intake else store.original_path(case_id, doc_id)
        w = ingest.scan_warning(path, d.get("rel_path") or d.get("filename"))
        if w:
            out.append({"doc_id": doc_id, "file": d.get("rel_path") or d.get("filename"), "message": w})
            ev = {"kind": "scan_warning", "doc_id": doc_id, "file": d.get("rel_path"), "message": w, "by": user}
            store.audit_intake({**ev, "department": d.get("department")}) if intake else store.audit(case_id, ev)
    return out


def attach_warnings(job_id, warnings):
    job = JOBS.get(job_id)
    if job is not None:
        job["warnings"] = warnings; _save_job(job)
    return warnings


def add_files(case_id, files, user="", warn=True):
    """files: list of (relative_path, bytes). Identical files already in the Case File are skipped (SHA-256); files that cannot be
    read are refused (job["unsupported"]: file + reason, audited) and never stored. Returns a job (processing runs in the background).
    warn=False leaves the big-scan warnings to the caller (scan_warnings in a thread, attach_warnings)."""
    ids, skipped, unsupported, warnings = [], [], [], []
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
    if warn:
        warnings = scan_warnings(case_id, ids, user)  # a big scan: the user knows the wait (V1 item 3.7)
    job = _job(case_id, len(ids), ids)
    job["skipped_duplicates"], job["unsupported"], job["warnings"] = skipped, unsupported, warnings
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
        for c in confirm.active(case_id, "dismiss_failed", i):  # a new attempt to read it withdraws the dismissal (V1 item 4.3): it must read, or be dismissed again
            confirm.undo(case_id, c["id"], user)
    store.audit(case_id, {"kind": "reprocess", "documents": ids, "by": user})
    job = _job(case_id, len(ids), ids)
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job))
    return job


def add_intake_files(files, department, user="", warn=True):
    """Department upload without a Case File (V1 item 2.3): files: list of (relative_path, bytes). Same refusal rules as add_files;
    identical bytes already waiting in the intake area are skipped. Returns a job (processing and matching run in the background)."""
    ids, skipped, unsupported, warnings = [], [], [], []
    waiting = {d.get("sha256"): d["doc_id"] for d in store.list_intake()}
    for rel, data in files:
        reason = ingest.reject_reason(rel)
        if reason is None and (Path(rel).suffix.lower() not in ingest.SUPPORTED or Path(rel).name.startswith(".")):
            reason = "Unsupported file type"
        if reason:
            unsupported.append({"file": rel, "reason": reason})
            store.audit_intake({"kind": "document_rejected", "file": rel, "reason": reason, "department": department, "by": user}); continue
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        if h in waiting:
            skipped.append({"file": rel, "same_as": waiting[h]})
            store.audit_intake({"kind": "document_duplicate_skipped", "file": rel, "same_as": waiting[h], "department": department, "by": user}); continue
        d = store.add_intake_file(Path(rel).name, data, rel, department, user)
        ids.append(d["doc_id"]); waiting[h] = d["doc_id"]
        store.audit_intake({"kind": "document_added", "doc_id": d["doc_id"], "file": rel, "department": department, "by": user})
    if warn:
        warnings = scan_warnings("intake", ids, user, intake=True)  # V1 item 3.7
    job = _job("intake", len(ids), ids)
    job["skipped_duplicates"], job["unsupported"], job["department"], job["warnings"] = skipped, unsupported, department, warnings
    _save_job(job)
    job["task"] = asyncio.get_event_loop().create_task(process_intake(ids, job))
    return job


async def process_intake(doc_ids, job):
    """Run intake.process on each document in parallel and summarise where each one went."""
    def progress(doc_id, state):
        job["doc_states"][doc_id] = state
        job["events"].append({"t": round(time.time() - job["started"], 2), "doc_id": doc_id, "state": state})
        if state in ("ready", "error", "needs_matching", "duplicate"):
            job["done"] += 1
        _save_job(job)
    try:
        await asyncio.gather(*[intake.process(d, progress) for d in doc_ids])
    except Exception as e:
        job["state"] = "failed"; job["error"] = f"{e.__class__.__name__}: {str(e)[:300]}"; job["seconds"] = round(time.time() - job["started"], 1)
        _save_job(job); store.audit_intake({"kind": "error", "where": "intake", "error": job["error"]}); return
    filed, needs, errors = {}, [], []
    for d in doc_ids:
        rec = store.get_intake(d)
        if rec is None:  # moved into a Case File
            case = next((c["case_id"] for c in store.list_cases() if any(x["doc_id"] == d for x in store.list_docs(c["case_id"]))), None)
            filed[d] = case
        elif rec.get("state") == "error":
            errors.append(d)
        else:
            needs.append(d)
    job.update(state="finished", seconds=round(time.time() - job["started"], 1), filed=filed, needs_matching=needs, errors=errors, gate=None)
    _save_job(job)
    store.audit_intake({"kind": "intake_finished", "documents": len(doc_ids), "filed": filed, "needs_matching": needs, "errors": errors, "seconds": job["seconds"]})


def list_case(case_id, protocol_id, setting="", board_date="", hospital_level="", user=""):
    """The coordinator lists a Case File for the board (V1 item 2.5): cancer protocol, NCG setting (chosen by the clinician), board date
    and the hospital level (Essential / Optimal; defaults to org.json). Pre-Authorization starts when listed: every processed document
    is extracted from its stored pages under the protocol (no second read) and the gate is evaluated. Re-listing with another protocol
    extracts again; changing only the setting, date or level re-checks. Returns a job on the Case File."""
    case = store.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if not protocol.exists(protocol_id):
        raise ValueError(f"Unknown protocol: {protocol_id}")
    ids = {x["id"] for x in protocol.settings(protocol_id)}
    if setting and setting not in ids:
        raise ValueError(f"Unknown NCG setting for {protocol_id}: {setting}")
    hospital_level = hospital_level or (org.load().get("hospital") or {}).get("level") or "essential"
    if hospital_level not in org.LEVELS:
        raise ValueError("Hospital level must be essential or optimal")
    if board_date:
        from .docstatus import parse_date
        iso = parse_date(board_date)
        if not iso:
            raise ValueError(f"Not a valid board date: {board_date}")
        board_date = iso
    before = {k: case.get(k) for k in ("protocol", "setting", "board_date", "hospital_level")}
    case.update(protocol=protocol_id, setting=setting, board_date=board_date, hospital_level=hospital_level,
                listing={"status": "listed", "listed_by": user, "listed_at": store.now_iso(), "previous": case.get("listing")})
    store.save_case(case)
    store.audit(case_id, {"kind": "case_listed", "by": user, "protocol": protocol_id, "setting": setting, "board_date": board_date, "hospital_level": hospital_level, "before": before})
    ids = [d["doc_id"] for d in store.list_docs(case_id) if d.get("state") == "ready" and d.get("pages")]
    if before["protocol"] == protocol_id or not ids:
        if not ids or before["protocol"] == protocol_id:
            recheck(case_id, user)
        job = _job(case_id, 0, []); job.update(state="finished", seconds=0.0, gate=None, listed=True)
        g = store.get_state(case_id).get("gate")
        job["gate"] = {k: g[k] for k in ("passed", "readiness", "satisfied", "total")} if g else None
        _save_job(job)
        return job
    for i in ids:
        d = store.get_doc(case_id, i); d["state"] = "queued"; store.save_doc(case_id, d)
    job = _job(case_id, len(ids), ids)
    job["listed"] = True
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job, from_stored=True))
    return job


def reextract_document(case_id, doc_id, user=""):
    """Extract one document's fields again from its stored pages (no second read or classification): after a clinician confirmed
    its document type (V1 item 3.2). Returns a job, or None when the Case File is not listed or the document has no stored pages."""
    case = store.get_case(case_id)
    d = store.get_doc(case_id, doc_id)
    if not case or not case.get("protocol") or not d or not d.get("pages") or not d.get("classification"):
        return None
    if d.get("state") in STUCK_STATES:  # another job is working on it: its run will read the confirmation (confirm.latest) itself
        store.audit(case_id, {"kind": "reextract_skipped", "doc_id": doc_id, "by": user, "state": d.get("state")})
        return None
    d["state"] = "queued"; d.pop("error", None); store.save_doc(case_id, d)
    store.audit(case_id, {"kind": "reextract", "doc_id": doc_id, "by": user})
    job = _job(case_id, 1, [doc_id])
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, [doc_id], job, from_stored=True))
    return job


def unfile_document(case_id, doc_id, user="", reason=""):
    """Move a document that came from the intake area back to the Needs matching queue (reverses an auto-link or a person's filing)."""
    moved = intake.unfile(case_id, doc_id, user, reason)
    st = recheck(case_id, user)
    return {"document": moved, "state": st}


def reprocess_intake(doc_ids, user=""):
    """Read, classify, identify and match intake documents again (after an error, or when new Case Files arrived)."""
    ids = [d for d in doc_ids if store.get_intake(d)]
    for i in ids:
        d = store.get_intake(i); d["state"] = "queued"; d.pop("error", None); store.save_intake(d)
    store.audit_intake({"kind": "reprocess", "documents": ids, "by": user})
    job = _job("intake", len(ids), ids)
    job["task"] = asyncio.get_event_loop().create_task(process_intake(ids, job))
    return job


def file_intake(doc_id, case_id, user="", how="confirmed", reason="", patient=None):
    """A person files an intake document into a Case File (or starts a new one with case_id None). Returns a job on the Case File."""
    moved = intake.file_to_case(doc_id, case_id, user, how, reason, patient)
    cid = moved["filed"]["case_id"]
    if moved.get("state") == "duplicate":
        job = _job(cid, 0, []); job.update(state="finished", seconds=0.0, gate=None, duplicate=moved["filed"]); _save_job(job)
        return job
    job = _job(cid, 1, [doc_id])
    job["task"] = asyncio.get_event_loop().create_task(process_docs(cid, [doc_id], job, from_stored=True))
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
            rec.setdefault("id", p.stem)
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
    for case_id, recs in interrupted.items():  # a job cut off after its documents were done (index warm-up or gate sync): re-check only
        if case_id in out["requeued"]:
            continue
        try:
            recheck(case_id, user=RESTART_USER)
            for rec in recs:
                rec["error"] = "The server restarted after the documents were processed; the Pre-Authorization check was run again"; _save_job(rec)
        except Exception:
            log.exception("resume_after_restart: re-check failed for %s", case_id)
    return out


def delete_document(case_id, doc_id, user=""):
    d = store.get_doc(case_id, doc_id)
    intake.unlearn_ids(case_id, doc_id, user)  # identifiers learned from this record go with it
    store.delete_document(case_id, doc_id)
    store.audit(case_id, {"kind": "document_deleted", "doc_id": doc_id, "file": (d or {}).get("rel_path"), "by": user})
    return recheck(case_id, user)


def recheck(case_id, user=""):
    """Re-evaluate the Pre-Authorization rules over the already-processed documents (deterministic, milliseconds) and
    re-sync the routed actions. Documents are NOT re-read here: use reprocess() for that."""
    before = store.get_state(case_id).get("gate") or {}
    gate = rules.evaluate(case_id)
    st = rules.sync_actions(case_id, gate, by=user)
    if gate is None:  # not listed yet (V1 item 2.5): nothing to check
        st["recheck"] = {"listed": False, "documents_checked": 0, "processing": 0, "errors": 0, "satisfied": 0, "total": 0, "passed": None, "changed": [], "open_actions": 0}
        store.audit(case_id, {"kind": "recheck", "by": user, "listed": False})
        return st
    changed = [r["label"] for r in gate["requirements"] if {x["id"]: x["status"] for x in before.get("requirements", [])}.get(r["id"]) not in (None, r["status"])]
    st["recheck"] = {"documents_checked": gate["documents"]["ready"], "processing": gate["documents"]["processing"], "errors": gate["documents"]["errors"],
                     "blockers": len(gate.get("blockers") or []), "level1_open": gate["levels"]["1"]["open"], "level2_open": gate["levels"]["2"]["open"],
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


# ---- board sessions (V1 items 6.1 to 6.3) -------------------------------------------------------------------------------
SESSION_TASKS: dict[str, set] = {}  # running brief preparations per session (kept referenced; a restart leaves "queued" / "running" behind)
AGENT_WAITING = ("queued", "running")


def _brief_status(brief):
    return "no_documents" if brief.get("no_documents") else "ready"


async def _prepare_one(sid, case_id, role, refresh, user):
    """One absent specialty's brief for one Case File on the agenda: a brief still current for the Case File (same signature) is reused
    unless refresh; otherwise the agent runs (no model call when the specialty has no documents, V1 item 6.6). The brief's items and
    points go to the session's agent log (V1 item 6.3)."""
    from . import agents, board
    try:
        st = store.get_state(case_id)
        art = (st.get("artefacts") or {}).get(f"brief_{role}")
        # reused only when it is what the agent would write now: same Case File, current format, no focus question, same near-match setting
        if art and not refresh and art.get("signature") and not rules.stale_reason(art["signature"], rules.case_signature(case_id, st)) \
                and art.get("version") == agents.BRIEF_VERSION and not art.get("focus") and bool(art.get("near_match")) == config.near_match():
            board.set_agent(sid, case_id, role, _brief_status(art), generated=art.get("generated"), reused=True, message=art.get("message") or "")
            board.log_brief(sid, case_id, role, art)
            return
        board.set_agent(sid, case_id, role, "running")
        brief, err = None, None
        async for ev in agents.run_agent(case_id, role):
            if ev["type"] == "brief":
                brief = ev["brief"]
            elif ev["type"] == "error":
                err = ev.get("message")
        if brief:
            board.set_agent(sid, case_id, role, _brief_status(brief), generated=brief.get("generated"), seconds=brief.get("seconds"), reused=False,
                            message=brief.get("message") or "")
            board.log_brief(sid, case_id, role, brief)
        else:
            board.set_agent(sid, case_id, role, "error", message=err or "The agent wrote no brief")
    except Exception as e:  # one failing brief never stops the others; the board sees the error and can prepare it again
        log.exception("session %s: %s brief for %s failed", sid, role, case_id)
        try:
            board.set_agent(sid, case_id, role, "error", message=f"{e.__class__.__name__}: {str(e)[:200]}")
        except Exception:
            pass


def prepare_session_agents(sid, user, roles=None, case_ids=None, refresh=False):
    """When the session starts (or a specialty is marked absent, or the board asks again), the agent of every absent specialty prepares
    its brief for every Case File on the agenda, all in parallel; the reasoner's queue spaces the model calls (V1 item 6.2).
    Returns the (case, role) pairs started."""
    from . import board
    s = board.get(sid)
    roles = [r for r in (roles or board.absent_roles(s)) if r in board.ROLE_DEPARTMENT]
    cases = [a["case_id"] for a in s["agenda"] if (case_ids is None or a["case_id"] in case_ids) and a["case_id"] not in config.PROTECTED_CASES]
    busy = {(c, r) for c, by_role in (s.get("agents") or {}).items() for r, x in by_role.items()
            if x.get("status") in AGENT_WAITING and SESSION_TASKS.get(sid)}
    pairs = [(c, r) for c in cases for r in roles if (c, r) not in busy]
    for c, r in pairs:
        board.set_agent(sid, c, r, "queued")
    if pairs:
        board.audit_session(sid, {"kind": "agents_prepare", "by": user, "pairs": [f"{c}:{r}" for c, r in pairs], "refresh": refresh})
        async def _all():
            await asyncio.gather(*[_prepare_one(sid, c, r, refresh, user) for c, r in pairs])
        task = asyncio.get_running_loop().create_task(_all())
        tasks = SESSION_TASKS.setdefault(sid, set()); tasks.add(task)
        task.add_done_callback(lambda t: (tasks.discard(t), SESSION_TASKS.pop(sid, None) if not tasks else None))
    return pairs


def session_interrupted(sid):
    """Agents left "queued" / "running" with no preparation running (a server restart): marked as errors the board can prepare again,
    also on a closed session (Phase 6 review: a session closed mid-preparation failed every later load)."""
    from . import board
    s = board.get(sid)
    if not s or SESSION_TASKS.get(sid):
        return s
    if any(x.get("status") in AGENT_WAITING for by_role in (s.get("agents") or {}).values() for x in by_role.values()):
        s = board.fail_waiting(sid, "Interrupted by a server restart: prepare it again")
    return s


def close_session(sid, user):
    """Close the session: briefs still being prepared are cancelled (no model work for a closed session) and shown as not ready."""
    from . import board
    for t in list(SESSION_TASKS.get(sid) or ()):
        t.cancel()
    SESSION_TASKS.pop(sid, None)
    return board.close(sid, user)
