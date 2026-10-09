"""Orchestration: ingestion jobs (parallel document processing with live progress), Pre-Authorization re-check,
demo case import, expert reviews."""
import asyncio, json, time, uuid
from pathlib import Path

from . import config, extract, ingest, rules, store

JOBS: dict[str, dict] = {}


def _job(case_id, total):
    jid = "J" + uuid.uuid4().hex[:8]
    JOBS[jid] = {"id": jid, "case_id": case_id, "total": total, "done": 0, "events": [], "state": "running", "started": time.time(), "doc_states": {}}
    return JOBS[jid]


async def process_docs(case_id, doc_ids, job):
    case = store.get_case(case_id)

    def progress(doc_id, state):
        job["doc_states"][doc_id] = state
        job["events"].append({"t": round(time.time() - job["started"], 2), "doc_id": doc_id, "state": state})
        if state in ("ready", "error"):
            job["done"] += 1

    try:
        await asyncio.gather(*[extract.process_document(case_id, d, case["protocol"], case.get("patient"), progress) for d in doc_ids])
        async with store.lock(case_id):
            gate = rules.evaluate(case_id)
            rules.sync_actions(case_id, gate)
    except Exception as e:  # the UI polls this job: it must reach a terminal state
        job["state"] = "failed"; job["error"] = f"{e.__class__.__name__}: {str(e)[:300]}"; job["seconds"] = round(time.time() - job["started"], 1)
        store.audit(case_id, {"kind": "error", "where": "ingestion", "error": job["error"]})
        return
    try:  # warm the search index (chunk embeddings) so the first search is instant
        from . import search
        await asyncio.to_thread(search.index, case_id)
    except Exception:
        pass
    job["state"] = "finished"; job["seconds"] = round(time.time() - job["started"], 1); job["gate"] = {k: gate[k] for k in ("passed", "readiness", "satisfied", "total")}
    store.audit(case_id, {"kind": "ingestion_finished", "documents": len(doc_ids), "seconds": job["seconds"], "gate_passed": gate["passed"], "readiness": gate["readiness"]})


def add_files(case_id, files, user=""):
    """files: list of (relative_path, bytes). Identical files already in the Case File are skipped (SHA-256).
    Returns a job (processing runs in the background)."""
    ids, skipped, unsupported = [], [], []
    for rel, data in files:
        if Path(rel).suffix.lower() not in ingest.SUPPORTED or Path(rel).name.startswith("."):
            unsupported.append(rel); continue
        dup = store.find_duplicate(case_id, data)
        if dup:
            skipped.append({"file": rel, "same_as": dup["doc_id"]})
            store.audit(case_id, {"kind": "document_duplicate_skipped", "file": rel, "same_as": dup["doc_id"], "by": user}); continue
        d = store.add_document_file(case_id, Path(rel).name, data, rel)
        ids.append(d["doc_id"])
        store.audit(case_id, {"kind": "document_added", "doc_id": d["doc_id"], "file": rel, "by": user})
    job = _job(case_id, len(ids))
    job["skipped_duplicates"], job["unsupported"] = skipped, unsupported
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
    job = _job(case_id, len(ids))
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job))
    return job


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
