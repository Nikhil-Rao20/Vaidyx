"""service.add_files: files that cannot be read are refused with a clear message, audited and never stored (V1 item 1.4)."""
import asyncio, json

from tumour_board import ingest, service, store


def _add(case_id, files):
    async def go():
        job = service.add_files(case_id, files, user="tester")
        await job["task"]
        return job
    return asyncio.run(go())


def test_doc_without_libreoffice_is_refused_with_the_message(unit_case, monkeypatch):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    job = _add(unit_case, [("notes/old_summary.doc", b"synthetic"), ("x.rtf", b"synthetic"), ("x.odt", b"synthetic"), ("old.xls", b"synthetic")])
    assert job["total"] == 0 and store.list_docs(unit_case) == []
    assert job["unsupported"] == [{"file": f, "reason": "Save as PDF or DOCX and upload again"} for f in ("notes/old_summary.doc", "x.rtf", "x.odt")] \
        + [{"file": "old.xls", "reason": "Save as XLSX or PDF and upload again"}]
    rejected = [e for e in store.read_audit(unit_case) if e["kind"] == "document_rejected"]
    assert [e["file"] for e in rejected] == ["notes/old_summary.doc", "x.rtf", "x.odt", "old.xls"] and rejected[0]["by"] == "tester"


def test_unknown_extension_and_hidden_files_are_refused_plainly(unit_case):
    job = _add(unit_case, [("scan.exe", b"synthetic"), (".DS_Store", b"synthetic")])
    assert job["total"] == 0 and [u["reason"] for u in job["unsupported"]] == ["Unsupported file type"] * 2


def test_readable_office_files_are_stored(unit_case, monkeypatch):
    async def fake_process(case_id, doc_id, protocol_id, patient=None, progress=None):
        d = store.get_doc(case_id, doc_id); d["state"] = "ready"; store.save_doc(case_id, d); progress and progress(doc_id, "ready")
    monkeypatch.setattr(service.extract, "process_document", fake_process)
    job = _add(unit_case, [("lab.xlsx", b"synthetic-1"), ("deck.pptx", b"synthetic-2"), ("report.docx", b"synthetic-3")])
    assert job["total"] == 3 and job["unsupported"] == [] and len(store.list_docs(unit_case)) == 3


# --- V1 item 1.8: jobs survive a restart -----------------------------------------------------------------------------

import json, time  # noqa: E402

from tumour_board import config  # noqa: E402


def _fake_ready(monkeypatch):
    """extract.process_document replaced by a fake that walks a document through reading -> ready (no models)."""
    async def fake_process(case_id, doc_id, protocol_id, patient=None, progress=None):
        d = store.get_doc(case_id, doc_id)
        for st in ("reading", "ready"):
            d["state"] = st; store.save_doc(case_id, d); progress and progress(doc_id, st)
    monkeypatch.setattr(service.extract, "process_document", fake_process)


def _job_file(jid):
    return config.DATA_ROOT / "jobs" / f"{jid}.json"


def _write_job(rec):
    p = config.DATA_ROOT / "jobs" / f"{rec['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec))
    return p


def test_job_record_is_saved_and_served_after_memory_is_cleared(unit_case, monkeypatch):
    _fake_ready(monkeypatch)
    service.JOBS.clear()
    job = _add(unit_case, [("cbc.txt", b"synthetic-a"), ("histo.txt", b"synthetic-b")])
    rec = json.loads(_job_file(job["id"]).read_text())
    assert "task" not in rec and rec["state"] == "finished" and rec["done"] == rec["total"] == 2
    assert sorted(rec["doc_ids"]) == sorted(d["doc_id"] for d in store.list_docs(unit_case)) and rec["started_iso"]
    for k in ("id", "case_id", "total", "done", "events", "state", "started", "doc_states", "skipped_duplicates", "unsupported", "seconds", "gate"):
        assert k in rec, k
    service.JOBS.clear()
    assert service.get_job(job["id"]) == rec
    assert service.get_job("Jmissing0") is None and service.get_job("../etc") is None


def test_get_job_prefers_memory_and_hides_the_task(unit_case, monkeypatch):
    _fake_ready(monkeypatch)
    job = _add(unit_case, [("cbc.txt", b"synthetic-c")])
    got = service.get_job(job["id"])
    assert "task" not in got and got["state"] == "finished" and got["id"] == job["id"]


def test_prune_drops_jobs_older_than_a_day(data_root):
    service.JOBS.clear()
    old, new = time.time() - 25 * 3600, time.time() - 3600
    service.JOBS["Jold00001"] = {"id": "Jold00001", "started": old, "state": "finished"}
    service.JOBS["Jnew00001"] = {"id": "Jnew00001", "started": new, "state": "finished"}
    p_old = _write_job({"id": "Jold00002", "case_id": "TB-X", "started": old, "state": "finished"})
    p_new = _write_job({"id": "Jnew00002", "case_id": "TB-X", "started": new, "state": "finished"})
    assert service._prune() == 2
    assert "Jold00001" not in service.JOBS and "Jnew00001" in service.JOBS
    assert not p_old.exists() and p_new.exists()
    service.JOBS.clear()


def _stuck_case(case_id):
    """Four documents: three cut off mid-processing (reading / extracting / queued) and one already ready."""
    ids = {}
    for i, st in enumerate(("reading", "extracting", "queued", "ready")):
        d = store.add_document_file(case_id, f"doc_{st}.txt", f"synthetic-{i}".encode())
        d["state"] = st
        if st == "ready":
            d["processed"] = "2026-10-10T09:00:00"
        store.save_doc(case_id, d); ids[st] = d["doc_id"]
    return ids


def test_restart_requeues_documents_left_mid_processing(unit_case, monkeypatch):
    """Done when (V1 1.8): a document set to `reading` + restart -> processed."""
    _fake_ready(monkeypatch)
    ids = _stuck_case(unit_case)
    ready_before = store.get_doc(unit_case, ids["ready"])
    stuck = sorted(ids[s] for s in ("reading", "extracting", "queued"))
    _write_job({"id": "Jdead0001", "case_id": unit_case, "total": 3, "done": 0, "events": [], "state": "running",
                "started": time.time() - 600, "doc_states": {}, "doc_ids": stuck})
    service.JOBS.clear()

    async def go():
        out = service.resume_after_restart()
        jid = next(j["id"] for j in service.JOBS.values() if j["case_id"] == unit_case)
        await service.JOBS[jid]["task"]
        return out, jid
    out, jid = asyncio.run(go())

    assert sorted(out["requeued"][unit_case]) == stuck and out["interrupted_jobs"] == ["Jdead0001"] and out["pruned"] == 0
    for i in stuck:
        assert store.get_doc(unit_case, i)["state"] == "ready"
    assert store.get_doc(unit_case, ids["ready"]) == ready_before  # never touched
    dead = json.loads(_job_file("Jdead0001").read_text())
    assert dead["state"] == "interrupted" and dead["resumed_by"] == jid and "restarted" in dead["error"]
    assert service.get_job(jid)["state"] == "finished" and service.get_job("Jdead0001")["resumed_by"] == jid
    audit = store.read_audit(unit_case)
    rp = [e for e in audit if e["kind"] == "reprocess"]
    assert rp and rp[-1]["by"] == "system:restart" and sorted(rp[-1]["documents"]) == stuck
    rs = [e for e in audit if e["kind"] == "resume_after_restart"]
    assert len(rs) == 1 and rs[0]["by"] == "system:restart" and sorted(rs[0]["documents"]) == stuck
    service.JOBS.clear()


def test_restart_with_nothing_stuck_creates_no_job(unit_case):
    d = store.add_document_file(unit_case, "done.txt", b"synthetic-z"); d["state"] = "ready"; store.save_doc(unit_case, d)
    e = store.add_document_file(unit_case, "bad.txt", b"synthetic-y"); e["state"] = "error"; e["error"] = "x"; store.save_doc(unit_case, e)
    service.JOBS.clear()

    async def go():
        return service.resume_after_restart()
    out = asyncio.run(go())
    assert out == {"requeued": {}, "interrupted_jobs": [], "pruned": 0} and service.JOBS == {}
    assert not any(ev["kind"] in ("reprocess", "resume_after_restart") for ev in store.read_audit(unit_case))
    assert store.get_doc(unit_case, e["doc_id"])["state"] == "error"


def test_restart_survives_a_broken_case_folder(unit_case, monkeypatch):
    _fake_ready(monkeypatch)
    broken = config.CASES_DIR / "TB-BROKEN"
    broken.mkdir(parents=True)
    (broken / "case.json").write_text("{not json")
    (config.DATA_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    (config.DATA_ROOT / "jobs" / "Jgarbage1.json").write_text("garbage")
    ids = _stuck_case(unit_case)
    service.JOBS.clear()

    async def go():
        out = service.resume_after_restart()
        for j in list(service.JOBS.values()):
            await j["task"]
        return out
    out = asyncio.run(go())
    assert list(out["requeued"]) == [unit_case] and store.get_doc(unit_case, ids["reading"])["state"] == "ready"
    service.JOBS.clear()


def test_restart_after_documents_were_done_only_rechecks(unit_case, monkeypatch):
    """A job cut off after its documents finished (during index warm-up or gate sync) is not re-queued; the gate is re-checked."""
    import time
    from tumour_board.tests.util import add, fact, make_doc
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma")}))
    jd = service._jobs_dir(); jd.mkdir(parents=True, exist_ok=True)
    (jd / "Jdead0001.json").write_text(json.dumps({"id": "Jdead0001", "case_id": unit_case, "total": 1, "done": 1, "events": [], "state": "running",
                                                  "started": time.time() - 60, "doc_states": {"Dhist0001": "ready"}, "doc_ids": ["Dhist0001"]}))
    service.JOBS.clear()

    async def go():
        return service.resume_after_restart()
    out = asyncio.run(go())
    assert out["requeued"] == {} and out["interrupted_jobs"] == ["Jdead0001"]
    rec = json.loads((jd / "Jdead0001.json").read_text())
    assert rec["state"] == "interrupted" and "Pre-Authorization check was run again" in rec["error"] and "resumed_by" not in rec
    kinds = [(e["kind"], e.get("by")) for e in store.read_audit(unit_case)]
    assert ("recheck", "system:restart") in kinds and not any(k == "reprocess" for k, _ in kinds)
    assert store.get_state(unit_case)["gate"]["requirements"]
