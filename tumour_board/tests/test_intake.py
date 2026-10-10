"""Department uploads before patient matching (V1 item 2.3): intake storage, processing with the model calls replaced by fakes,
filing into a Case File (department and uploader kept, fields extracted from the stored pages, gate re-checked), new unlisted
Case Files, duplicates, "not this patient", discard, the queue per role, and jobs."""
import asyncio

import pytest

from tumour_board import config, extract, ingest, intake, org, rules, search, service, store
from tumour_board.tests import util

LFT = ("Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Laboratory Medicine\nLIVER FUNCTION TESTS\nPatient name Hospital No. Age / Sex\n"
       "Md. Irfan Shaikh SYN-600744 61 Y / M\nTotal bilirubin 0.6 mg/dl\nReport status: FINAL\nReported by: Dr. R. Pillai, MD (Biochemistry)")
CLS = {"title": "LIVER FUNCTION TESTS", "department": "Laboratory Medicine", "doc_type": "lab", "body_region": "", "report_date": "23/09/2026",
       "status_quote": "", "signature_quote": "", "signer": "", "patient_name": "Md. Irfan Shaikh", "patient_id": "SYN-600744"}


@pytest.fixture
def fakes(monkeypatch):
    """ingest / classify / extract_facts replaced by fakes; the text comes from the stored file."""
    async def fake_pages(path, audit=None):
        return [{"text": path.read_bytes().decode(errors="replace"), "method": "plain-text"}]

    async def fake_classify(t, audit=None):
        return dict(CLS)

    async def fake_facts(t, fids, audit=None):
        return {"histologic_type": {"found": True, "value": "Adenocarcinoma", "quote": "Diagnosis: Adenocarcinoma"}} if "histologic_type" in fids else {}
    monkeypatch.setattr(ingest, "extract_pages", fake_pages)
    monkeypatch.setattr(extract, "classify", fake_classify)
    monkeypatch.setattr(extract, "extract_facts", fake_facts)
    monkeypatch.setattr(search, "index", lambda case_id: None)  # the embedding model is not loaded in the unit suite


def _upload(files, dept="laboratory_medicine", user="lab.user"):
    async def go():
        job = service.add_intake_files(files, dept, user)
        await job["task"]
        return job
    return asyncio.run(go())


def _file(doc_id, case_id, user="coord", how="confirmed", reason="", patient=None):
    async def go():
        job = service.file_intake(doc_id, case_id, user, how, reason, patient)
        if job.get("task"):
            await job["task"]
        return job
    return asyncio.run(go())


def test_upload_lands_in_intake_tagged_with_department_user_and_time(fakes):
    job = _upload([("lft.txt", LFT.encode()), ("notes/old.doc", b"x"), ("lft_copy.txt", LFT.encode())])
    docs = store.list_intake()
    assert job["total"] == 1 and len(docs) == 1
    d = docs[0]
    assert d["department"] == "laboratory_medicine" and d["uploaded_by"] == "lab.user" and d["added"] and d["intake"] is True
    assert d["state"] == "needs_matching" and d["classification"]["doc_type"] == "lab" and d["classification"]["status"] == "FINAL"
    assert d["identity_read"]["name"]["value"] == "Md. Irfan Shaikh" and d["match"]["decision"] == "needs_matching"
    assert job["unsupported"] == [{"file": "notes/old.doc", "reason": "Save as PDF or DOCX and upload again"}]
    assert job["skipped_duplicates"] == [{"file": "lft_copy.txt", "same_as": d["doc_id"]}]
    assert job["state"] == "finished" and job["needs_matching"] == [d["doc_id"]] and job["filed"] == {} and job["gate"] is None
    kinds = [e["kind"] for e in store.read_intake_audit()]
    assert kinds[:3] == ["document_added", "document_rejected", "document_duplicate_skipped"] and "matching_decision" in kinds and kinds[-1] == "intake_finished"


def test_unreadable_file_ends_in_error_and_can_be_reprocessed(fakes, monkeypatch):
    job = _upload([("empty.txt", b"   ")])
    d = store.list_intake()[0]
    assert d["state"] == "error" and d["error"] == "no readable text" and job["errors"] == [d["doc_id"]]
    (store.intake_doc_dir(d["doc_id"]) / "original.txt").write_bytes(LFT.encode())

    async def go():
        j = service.reprocess_intake([d["doc_id"]], "lab.user"); await j["task"]; return j
    j = asyncio.run(go())
    assert store.get_intake(d["doc_id"])["state"] == "needs_matching" and j["needs_matching"] == [d["doc_id"]]


HPE = LFT.replace("LIVER FUNCTION TESTS", "HISTOPATHOLOGY REPORT").replace("Total bilirubin 0.6 mg/dl", "Diagnosis: Adenocarcinoma")


def test_file_into_a_listed_case_extracts_fields_and_rechecks_the_gate(fakes, unit_case, monkeypatch):
    async def fake_classify(t, audit=None):
        return {**CLS, "title": "HISTOPATHOLOGY REPORT", "doc_type": "histopathology"}
    monkeypatch.setattr(extract, "classify", fake_classify)
    _upload([("hpe.txt", HPE.encode())], dept="pathology", user="path.user")
    d = store.list_intake()[0]
    job = _file(d["doc_id"], unit_case, user="coord", reason="UHID checked with the lab")
    assert store.get_intake(d["doc_id"]) is None and job["state"] == "finished" and job["case_id"] == unit_case
    moved = store.get_doc(unit_case, d["doc_id"])
    assert moved["state"] == "ready" and moved["department"] == "pathology" and moved["uploaded_by"] == "path.user"
    assert moved["filed"]["case_id"] == unit_case and moved["filed"]["by"] == "coord" and moved["filed"]["how"] == "confirmed"
    assert moved["classification"]["title"] == "HISTOPATHOLOGY REPORT" and moved["pages"][0]["text"] == HPE  # stored pages reused: no re-read
    assert moved["facts"]["histologic_type"]["verification"] == "verified" and moved["identity"] == "mismatch_or_missing"  # not TB-UNIT's patient
    st = store.get_state(unit_case)
    assert st["gate"]["documents"]["ready"] == 1
    r = util.req(st["gate"], "histopathology")
    assert r["status"] == "needs_review" and "Patient identifier not found" in r["problems"][0]  # filed, extracted, gate re-checked
    assert [c["type"] for c in st["confirmations"]] == ["confirm_match"] and st["confirmations"][0]["fields"] == {"case_id": unit_case}
    kinds = {e["kind"] for e in store.read_audit(unit_case)}
    assert {"document_filed_from_intake", "confirmation", "ingestion_finished"} <= kinds
    assert [e for e in store.read_intake_audit() if e["kind"] == "filed"][0]["case_id"] == unit_case


def test_classify_is_not_called_again_when_filing(fakes, unit_case, monkeypatch):
    _upload([("lft.txt", LFT.encode())])
    d = store.list_intake()[0]

    async def boom(t, audit=None):
        raise AssertionError("classify must not run again for a document filed from intake")
    monkeypatch.setattr(extract, "classify", boom)
    assert _file(d["doc_id"], unit_case)["state"] == "finished" and store.get_doc(unit_case, d["doc_id"])["state"] == "ready"


def test_new_case_from_intake_waits_for_listing_and_has_no_gate(fakes):
    _upload([("lft.txt", LFT.encode())])
    d = store.list_intake()[0]
    job = _file(d["doc_id"], None, user="coord", how="new_case")
    cid = job["case_id"]
    assert cid.startswith("TB-") and cid.endswith("-0001")
    c = store.get_case(cid)
    assert c["protocol"] == "" and c["listing"] == {"status": "awaiting_listing"} and c["patient"]["name"] == "Md. Irfan Shaikh" and c["patient"]["mrn"] == "SYN-600744"
    moved = store.get_doc(cid, d["doc_id"])
    assert moved["state"] == "ready" and moved["facts"] == {}  # nothing extracted until the Case File is listed (2.5)
    assert store.get_state(cid)["gate"] is None and rules.evaluate(cid) is None
    assert any(e["kind"] == "case_created" and e.get("from_intake") == d["doc_id"] for e in store.read_audit(cid))
    assert intake.next_case_id() == cid[:-4] + "0002"


def test_duplicate_of_a_case_document_stays_in_the_queue(fakes, unit_case):
    store.add_document_file(unit_case, "lft.txt", LFT.encode())
    _upload([("lft_again.txt", LFT.encode())])
    d = store.list_intake()[0]
    job = _file(d["doc_id"], unit_case)
    rec = store.get_intake(d["doc_id"])
    assert rec["state"] == "duplicate" and rec["filed"]["case_id"] == unit_case and job["total"] == 0 and job["duplicate"]["same_as"]
    assert len(store.list_docs(unit_case)) == 1


def test_not_this_patient_is_a_confirmation_in_that_case(fakes, unit_case):
    _upload([("lft.txt", LFT.encode())])
    d = store.list_intake()[0]
    d["match"] = {"decision": "suggest", "case_id": unit_case, "candidates": [{"case_id": unit_case}], "reason": "name fits"}; store.save_intake(d)
    out = intake.not_this_patient(d["doc_id"], unit_case, "coord", "different person")
    assert out["rejected_cases"] == [unit_case] and out["match"]["decision"] == "needs_matching" and out["match"]["candidates"] == []
    rec = store.get_state(unit_case)["confirmations"][0]
    assert rec["type"] == "confirm_match" and rec["key"] == d["doc_id"] and rec["fields"] == {"case_id": ""} and rec["reason"] == "different person"


def test_discard_removes_the_file_and_is_audited(fakes):
    _upload([("lft.txt", LFT.encode())])
    d = store.list_intake()[0]
    intake.discard(d["doc_id"], "head.lab", "wrong hospital")
    assert store.list_intake() == [] and not store.intake_doc_dir(d["doc_id"]).exists()
    ev = [e for e in store.read_intake_audit() if e["kind"] == "discarded"][0]
    assert ev["by"] == "head.lab" and ev["reason"] == "wrong hospital" and ev["department"] == "laboratory_medicine"


def test_queue_is_filtered_by_department_for_members(fakes):
    _upload([("lft.txt", LFT.encode())], dept="laboratory_medicine")
    _upload([("xray.txt", LFT.replace("LIVER", "X-RAY").encode())], dept="radio_diagnosis", user="rad.user")
    o = org.load()
    org.save({**o, "users": {"lab.user": {"departments": {"laboratory_medicine": "member"}, "coordinator": False},
                             "coord": {"departments": {}, "coordinator": True}}}, by="test")
    assert [d["department"] for d in intake.queue(org.roles("lab.user"))] == ["laboratory_medicine"]
    assert len(intake.queue(org.roles("coord"))) == 2 and len(intake.queue(org.roles("admin", vaidyx_admin=True))) == 2
    assert intake.queue(org.roles("nobody")) == []
    row = intake.queue(org.roles("coord"))[0]
    assert "pages" in row and isinstance(row["pages"], int) and "identity_read" in row and "match" in row


def test_patient_from_identity_prefers_a_hospital_id():
    doc = {"identity_read": {"name": {"value": "Sunita Devi"}, "ids": [{"kind": "ip_no", "value": "IP/26/1"}, {"kind": "uhid", "value": "SYN-500911"}],
                             "age": 67, "sex": "F", "dob": "1959-07-11", "relation": {"kind": "W/o", "name": "Late Ram Prakash"}, "abha": None}}
    p = intake.patient_from_identity(doc)
    assert (p["name"], p["mrn"], p["agesex"], p["dob"], p["relation"]) == ("Sunita Devi", "SYN-500911", "67 Y / F", "1959-07-11", "Late Ram Prakash")
    assert p["ids"] == [{"kind": "ip_no", "value": "IP/26/1"}, {"kind": "uhid", "value": "SYN-500911"}]


def test_case_without_protocol_processes_documents_without_extraction(fakes):
    store.create_case("TB-NEW", {"name": "Md. Irfan Shaikh", "mrn": "SYN-600744"}, "", created_by="t")
    d = store.add_document_file("TB-NEW", "lft.txt", LFT.encode())
    out = asyncio.run(extract.process_document("TB-NEW", d["doc_id"], "", {"name": "Md. Irfan Shaikh", "mrn": "SYN-600744"}))
    assert out["state"] == "ready" and out["facts"] == {} and out["identity"] == "match" and out["classification"]["doc_type"] == "lab"
    assert rules.evaluate("TB-NEW") is None and rules.sync_actions("TB-NEW", None)["gate"] is None
    assert store.list_cases()[0]["listing"]["status"] == "awaiting_listing"
