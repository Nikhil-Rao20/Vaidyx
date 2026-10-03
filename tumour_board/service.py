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

    await asyncio.gather(*[extract.process_document(case_id, d, case["protocol"], case.get("patient"), progress) for d in doc_ids])
    async with store.lock(case_id):
        gate = rules.evaluate(case_id)
        rules.sync_actions(case_id, gate)
    try:  # warm the search index (chunk embeddings) so the first search is instant
        from . import search
        await asyncio.to_thread(search.index, case_id)
    except Exception:
        pass
    job["state"] = "finished"; job["seconds"] = round(time.time() - job["started"], 1); job["gate"] = {k: gate[k] for k in ("passed", "readiness", "satisfied", "total")}
    store.audit(case_id, {"kind": "ingestion_finished", "documents": len(doc_ids), "seconds": job["seconds"], "gate_passed": gate["passed"], "readiness": gate["readiness"]})


def add_files(case_id, files, user=""):
    """files: list of (relative_path, bytes). Returns a job (processing runs in the background)."""
    ids = []
    for rel, data in files:
        if Path(rel).suffix.lower() not in ingest.SUPPORTED or Path(rel).name.startswith("."):
            continue
        d = store.add_document_file(case_id, Path(rel).name, data, rel)
        ids.append(d["doc_id"])
        store.audit(case_id, {"kind": "document_added", "doc_id": d["doc_id"], "file": rel, "by": user})
    job = _job(case_id, len(ids))
    job["task"] = asyncio.get_event_loop().create_task(process_docs(case_id, ids, job))
    return job


def recheck(case_id, user=""):
    gate = rules.evaluate(case_id)
    st = rules.sync_actions(case_id, gate, by=user)
    store.audit(case_id, {"kind": "recheck", "by": user, "passed": gate["passed"], "readiness": gate["readiness"]})
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
