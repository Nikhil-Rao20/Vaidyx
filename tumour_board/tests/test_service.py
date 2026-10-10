"""service.add_files: files that cannot be read are refused with a clear message, audited and never stored (V1 item 1.4)."""
import asyncio

from tumour_board import ingest, service, store


def _add(case_id, files):
    async def go():
        job = service.add_files(case_id, files, user="tester")
        await job["task"]
        return job
    return asyncio.run(go())


def test_doc_without_libreoffice_is_refused_with_the_message(unit_case, monkeypatch):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    job = _add(unit_case, [("notes/old_summary.doc", b"synthetic"), ("x.rtf", b"synthetic"), ("x.odt", b"synthetic")])
    assert job["total"] == 0 and store.list_docs(unit_case) == []
    assert job["unsupported"] == [{"file": f, "reason": "Save as PDF or DOCX and upload again"} for f in ("notes/old_summary.doc", "x.rtf", "x.odt")]
    rejected = [e for e in store.read_audit(unit_case) if e["kind"] == "document_rejected"]
    assert [e["file"] for e in rejected] == ["notes/old_summary.doc", "x.rtf", "x.odt"] and rejected[0]["by"] == "tester"


def test_unknown_extension_and_hidden_files_are_refused_plainly(unit_case):
    job = _add(unit_case, [("scan.exe", b"synthetic"), (".DS_Store", b"synthetic")])
    assert job["total"] == 0 and [u["reason"] for u in job["unsupported"]] == ["Unsupported file type"] * 2


def test_readable_office_files_are_stored(unit_case, monkeypatch):
    async def fake_process(case_id, doc_id, protocol_id, patient=None, progress=None):
        d = store.get_doc(case_id, doc_id); d["state"] = "ready"; store.save_doc(case_id, d); progress and progress(doc_id, "ready")
    monkeypatch.setattr(service.extract, "process_document", fake_process)
    job = _add(unit_case, [("lab.xlsx", b"synthetic-1"), ("deck.pptx", b"synthetic-2"), ("report.docx", b"synthetic-3")])
    assert job["total"] == 3 and job["unsupported"] == [] and len(store.list_docs(unit_case)) == 3
