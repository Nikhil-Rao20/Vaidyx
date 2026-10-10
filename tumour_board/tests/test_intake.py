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
# no identifier printed: always waits for a person (plan 2.4: anything else -> needs matching)
NOID = ("Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Laboratory Medicine\nBLOOD SUGAR REPORT\nName Age / Sex Collected on\nRamesh Kumar 60 Y / M 16/09/2026\n"
        "Random blood sugar 132 mg/dl\nReport status: FINAL\nReported by: Dr. R. Pillai, MD (Biochemistry)")


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
    job = _upload([("rbs.txt", NOID.encode()), ("notes/old.doc", b"x"), ("rbs_copy.txt", NOID.encode())])
    docs = store.list_intake()
    assert job["total"] == 1 and len(docs) == 1
    d = docs[0]
    assert d["department"] == "laboratory_medicine" and d["uploaded_by"] == "lab.user" and d["added"] and d["intake"] is True
    assert d["state"] == "needs_matching" and d["classification"]["doc_type"] == "lab" and d["classification"]["status"] == "FINAL"
    assert d["identity_read"]["name"]["value"] == "Ramesh Kumar" and d["identity_read"]["ids"] == [] and (d["identity_read"]["age"], d["identity_read"]["sex"]) == (60, "M")
    assert d["match"]["decision"] == "needs_matching" and "no ID printed" in d["match"]["reason"]
    assert job["unsupported"] == [{"file": "notes/old.doc", "reason": "Save as PDF or DOCX and upload again"}]
    assert job["skipped_duplicates"] == [{"file": "rbs_copy.txt", "same_as": d["doc_id"]}]
    assert job["state"] == "finished" and job["needs_matching"] == [d["doc_id"]] and job["filed"] == {} and job["gate"] is None
    kinds = [e["kind"] for e in store.read_intake_audit()]
    assert kinds[:3] == ["document_added", "document_rejected", "document_duplicate_skipped"] and "matching_decision" in kinds and kinds[-1] == "intake_finished"


def test_unreadable_file_ends_in_error_and_can_be_reprocessed(fakes, monkeypatch):
    job = _upload([("empty.txt", b"   ")])
    d = store.list_intake()[0]
    assert d["state"] == "error" and d["error"] == "no readable text" and job["errors"] == [d["doc_id"]]
    (store.intake_doc_dir(d["doc_id"]) / "original.txt").write_bytes(NOID.encode())

    async def go():
        j = service.reprocess_intake([d["doc_id"]], "lab.user"); await j["task"]; return j
    j = asyncio.run(go())
    assert store.get_intake(d["doc_id"])["state"] == "needs_matching" and j["needs_matching"] == [d["doc_id"]]


HPE = NOID.replace("BLOOD SUGAR REPORT", "HISTOPATHOLOGY REPORT").replace("Random blood sugar 132 mg/dl", "Diagnosis: Adenocarcinoma")


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
    _upload([("rbs.txt", NOID.encode())])
    d = store.list_intake()[0]

    async def boom(t, audit=None):
        raise AssertionError("classify must not run again for a document filed from intake")
    monkeypatch.setattr(extract, "classify", boom)
    assert _file(d["doc_id"], unit_case)["state"] == "finished" and store.get_doc(unit_case, d["doc_id"])["state"] == "ready"


def test_new_case_from_intake_waits_for_listing_and_has_no_gate(fakes):
    _upload([("rbs.txt", NOID.encode())])
    d = store.list_intake()[0]
    job = _file(d["doc_id"], None, user="coord", how="new_case")
    cid = job["case_id"]
    assert cid.startswith("TB-") and cid.endswith("-0001")
    c = store.get_case(cid)
    assert c["protocol"] == "" and c["listing"] == {"status": "awaiting_listing"} and c["patient"]["name"] == "Ramesh Kumar" and c["patient"]["agesex"] == "60 Y / M"
    moved = store.get_doc(cid, d["doc_id"])
    assert moved["state"] == "ready" and moved["facts"] == {}  # nothing extracted until the Case File is listed (2.5)
    assert store.get_state(cid)["gate"] is None and rules.evaluate(cid) is None
    assert any(e["kind"] == "case_created" and e.get("from_intake") == d["doc_id"] for e in store.read_audit(cid))
    assert intake.next_case_id() == cid[:-4] + "0002"


def test_duplicate_of_a_case_document_stays_in_the_queue(fakes, unit_case):
    store.add_document_file(unit_case, "rbs.txt", NOID.encode())
    _upload([("rbs_again.txt", NOID.encode())])
    d = store.list_intake()[0]
    job = _file(d["doc_id"], unit_case)
    rec = store.get_intake(d["doc_id"])
    assert rec["state"] == "duplicate" and rec["filed"]["case_id"] == unit_case and job["total"] == 0 and job["duplicate"]["same_as"]
    assert len(store.list_docs(unit_case)) == 1


def test_not_this_patient_is_a_confirmation_in_that_case(fakes, unit_case):
    _upload([("rbs.txt", NOID.encode())])
    d = store.list_intake()[0]
    d["match"] = {"decision": "suggest", "case_id": unit_case, "candidates": [{"case_id": unit_case}], "reason": "name fits"}; store.save_intake(d)
    out = intake.not_this_patient(d["doc_id"], unit_case, "coord", "different person")
    assert out["rejected_cases"] == [unit_case] and out["match"]["decision"] == "needs_matching" and out["match"]["candidates"] == []
    rec = store.get_state(unit_case)["confirmations"][0]
    assert rec["type"] == "confirm_match" and rec["key"] == d["doc_id"] and rec["fields"] == {"case_id": ""} and rec["reason"] == "different person"


def test_discard_removes_the_file_and_is_audited(fakes):
    _upload([("rbs.txt", NOID.encode())])
    d = store.list_intake()[0]
    intake.discard(d["doc_id"], "head.lab", "wrong hospital")
    assert store.list_intake() == [] and not store.intake_doc_dir(d["doc_id"]).exists()
    ev = [e for e in store.read_intake_audit() if e["kind"] == "discarded"][0]
    assert ev["by"] == "head.lab" and ev["reason"] == "wrong hospital" and ev["department"] == "laboratory_medicine"


def test_queue_is_filtered_by_department_for_members(fakes):
    _upload([("rbs.txt", NOID.encode())], dept="laboratory_medicine")
    _upload([("xray.txt", NOID.replace("BLOOD SUGAR", "X-RAY").encode())], dept="radio_diagnosis", user="rad.user")
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


# --- V1 item 2.4: patient matching across departments (identity read by rules, decision per the plan's evidence table) ---

CBC = ("Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Laboratory Medicine\nHAEMATOLOGY REPORT\nName UHID Age / Sex\nSmt. Sunita Devi SYN-500911 67 Y / F\n"
       "Aadhaar No. Reg. date Collected on\n7395 8406 1180 15/09/2026 08:20 15/09/2026 08:30\nHaemoglobin 10.8 gm%\n*** End of report ***\nSd/-\nDr. Suresh Babu, MD (Pathology), KMC Reg. No. 69021")


def test_exact_id_with_compatible_name_auto_links_and_learns_other_ids(fakes):
    store.create_case("TB-006", {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    job = _upload([("lft.txt", LFT.encode())])
    assert job["filed"] == {next(iter(job["filed"]))[0:0] + list(job["filed"])[0]: "TB-006"} and job["needs_matching"] == [] and store.list_intake() == []
    doc_id = list(job["filed"])[0]
    d = store.get_doc("TB-006", doc_id)
    assert d["state"] == "ready" and d["filed"]["how"] == "auto" and d["filed"]["by"] == intake.MATCH_USER and d["identity"] == "match"
    assert d["match"]["decision"] == "auto_link" and d["match"]["matched_on"] == {"kind": "hospital_no", "value": "SYN-600744"} and "variant" in d["match"]["reason"]
    kinds = [e["kind"] for e in store.read_audit("TB-006")]
    assert "document_filed_from_intake" in kinds and "patient_ids_learned" in kinds
    assert {(x["kind"], x["value"]) for x in store.get_case("TB-006")["patient"]["ids"]} == {("hospital_no", "SYN-600744")}


def test_same_name_different_id_never_auto_links_and_opens_a_new_case(fakes, monkeypatch):
    async def fake_classify(t, audit=None):
        return {**CLS, "title": "HAEMATOLOGY REPORT", "patient_name": "Sunita Devi", "patient_id": "SYN-500911"}
    monkeypatch.setattr(extract, "classify", fake_classify)
    store.create_case("TB-005", {"name": "Sunita Devi", "mrn": "SYN-500263", "agesex": "52 Y / F"}, "breast", created_by="t")
    job = _upload([("cbc.txt", CBC.encode())])
    cid = list(job["filed"].values())[0]
    assert cid != "TB-005" and cid.endswith("-0001") and store.get_case(cid)["listing"]["status"] == "awaiting_listing"
    pat = store.get_case(cid)["patient"]
    assert pat["name"] == "Sunita Devi" and pat["mrn"] == "SYN-500911" and pat["agesex"] == "67 Y / F" and "1180" not in __import__("json").dumps(pat)
    d = store.get_doc(cid, list(job["filed"])[0])
    assert d["match"]["decision"] == "new_case" and "TB-005" in d["match"]["reason"] and d["identity_read"]["aadhaar_seen"] is True
    assert "7395 8406 1180" not in d["pages"][0]["text"] and "XXXX XXXX 1180" in d["pages"][0]["text"] and d["pages"][0]["aadhaar_masked"] == 1
    assert len(store.list_docs("TB-005")) == 0
    # the second record of the same new patient now auto-links to the new Case File
    job2 = _upload([("cbc2.txt", CBC.replace("10.8", "11.1").encode())])
    assert list(job2["filed"].values()) == [cid]


def test_id_matches_but_name_differs_is_a_conflict_for_a_person(fakes, monkeypatch):
    store.create_case("TB-006", {"name": "Suresh Pillai", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    job = _upload([("lft.txt", LFT.encode())])
    d = store.list_intake()[0]
    assert job["needs_matching"] == [d["doc_id"]] and d["match"]["decision"] == "id_conflict" and d["match"]["candidates"][0]["case_id"] == "TB-006"
    assert "possible wrong ID" in d["match"]["reason"] and len(store.list_docs("TB-006")) == 0


def test_not_this_patient_blocks_the_link_on_reprocess(fakes):
    store.create_case("TB-006", {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    d = store.add_intake_file("lft.txt", LFT.encode(), "lft.txt", "laboratory_medicine", "lab.user")
    d["rejected_cases"] = ["TB-006"]; store.save_intake(d)

    async def go():
        j = service.reprocess_intake([d["doc_id"]], "coord"); await j["task"]; return j
    j = asyncio.run(go())
    rec = store.get_intake(d["doc_id"])
    assert j["needs_matching"] == [d["doc_id"]] and rec["match"]["decision"] == "needs_matching" and "not TB-006" in rec["match"]["reason"]


def test_outside_hospital_number_does_not_open_a_case_when_the_hospital_is_named(fakes):
    o = org.load(); org.save({**o, "hospital": {**o["hospital"], "name": "Sahyadri Cancer Institute"}}, by="t")
    outside = LFT.replace("Sahyadri Cancer Institute (SYNTHETIC)", "District General Hospital, Mandya (SYNTHETIC)").replace("Hospital No.", "Hosp. No.").replace("SYN-600744", "DGH-26-071134")
    job = _upload([("outside_lft.txt", outside.encode())])
    d = store.list_intake()[0]
    assert job["needs_matching"] == [d["doc_id"]] and d["match"]["decision"] == "needs_matching" and "another hospital" in d["match"]["reason"]
    assert store.list_cases() == []


def test_model_identifier_is_used_only_when_it_equals_a_known_id(fakes, monkeypatch):
    text = "Sahyadri Cancer Institute (SYNTHETIC)\nCLINIC VISIT\nMd. Irfan Shaikh, 61 years, male, SYN-600744\nSeen today.\nSigned: Dr. A"
    async def fake_classify(t, audit=None):
        return {**CLS, "title": "CLINIC VISIT", "doc_type": "clinical_note", "patient_name": "Md. Irfan Shaikh", "patient_id": "SYN-600744"}
    monkeypatch.setattr(extract, "classify", fake_classify)
    job = _upload([("visit.txt", text.encode())])  # no Case File knows SYN-600744: the unlabelled model id is only a note
    d = store.list_intake()[0]
    assert d["match"]["decision"] == "needs_matching" and d["identity_read"]["ids"] == [] and any("Qwen3.5-4B reader" in n for n in d["identity_read"]["notes"])
    assert d["identity_read"]["name"]["value"] == "Md. Irfan Shaikh" and "quote checked" in d["identity_read"]["name"]["label"] and d["identity_read"]["model_read"] == ["name"]
    intake.discard(d["doc_id"], "t")
    store.create_case("TB-006", {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    job = _upload([("visit2.txt", text.encode())])
    d = store.list_intake()[0]  # both the name and the identifier came from the model: suggested for a person, never linked on its own
    assert job["filed"] == {} and d["match"]["decision"] == "suggest" and d["match"]["case_id"] == "TB-006" and d["identity_read"]["model_read"] == ["name", "id"]


def test_case_document_identity_uses_the_rules_and_learns_ids(fakes, monkeypatch):
    cect = ("Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Radio-diagnosis\nCECT THORAX\nPatient name CR No. Age / Sex\nR. Kumar CR/2026/04118 58Y/M\n"
            "Findings: mass.\nReport status: FINAL\nReported by: Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310")
    hpe = ("Sahyadri Cancer Institute (SYNTHETIC)\nHISTOPATHOLOGY REPORT\nPatient name Mr. Ramesh Kumar\nUHID SYN-400118\nCR No. CR/2026/04118\nAge / Sex 58 Y / M\n"
           "Diagnosis: Non-small cell carcinoma\nReport status: FINAL\nReported by: Dr. Fatima Begum, MD (Pathology)")
    store.create_case("TB-004", {"name": "Ramesh Kumar", "mrn": "SYN-400118", "agesex": "58 Y / M"}, "lung_nsclc", created_by="t")
    pat = store.get_case("TB-004")["patient"]
    async def cls_ct(t, audit=None):
        return {**CLS, "title": "CECT THORAX", "doc_type": "ct", "patient_name": "R. Kumar", "patient_id": "CR/2026/04118"}
    monkeypatch.setattr(extract, "classify", cls_ct)
    d1 = store.add_document_file("TB-004", "cect.txt", cect.encode())
    out = asyncio.run(extract.process_document("TB-004", d1["doc_id"], "lung_nsclc", pat))
    assert out["identity"] == "id_differs" and out["identity_read"]["ids"][0]["kind"] == "cr_no"  # CR No. not known yet: flagged until another record teaches it
    async def cls_hpe(t, audit=None):
        return {**CLS, "title": "HISTOPATHOLOGY REPORT", "doc_type": "histopathology", "patient_name": "Mr. Ramesh Kumar", "patient_id": "SYN-400118"}
    monkeypatch.setattr(extract, "classify", cls_hpe)
    d2 = store.add_document_file("TB-004", "hpe.txt", hpe.encode())
    out2 = asyncio.run(extract.process_document("TB-004", d2["doc_id"], "lung_nsclc", pat))
    assert out2["identity"] == "match"
    learned = store.get_case("TB-004")["patient"]["ids"]
    assert ("cr_no", "CR/2026/04118") in {(x["kind"], x["value"]) for x in learned}
    monkeypatch.setattr(extract, "classify", cls_ct)
    out3 = asyncio.run(extract.process_document("TB-004", d1["doc_id"], "lung_nsclc", store.get_case("TB-004")["patient"]))
    assert out3["identity"] == "match"  # the CR No. is known now
    other = asyncio.run(extract.process_document("TB-004", d1["doc_id"], "lung_nsclc", {"name": "Suresh Kumar", "mrn": "SYN-400118", "ids": [{"kind": "cr_no", "value": "CR/2026/04118"}]}))
    assert other["identity"] == "mismatch_or_missing"  # ID agrees, name does not: possible wrong patient


def test_registered_name_drops_titles_and_relation():
    assert intake.registered_name("Smt. Sunita Devi") == "Sunita Devi"
    assert intake.registered_name("Shri Ramesh Kumar S/o Mohan Lal") == "Ramesh Kumar"
    assert intake.registered_name("Mr. RAMESH KUMAR") == "RAMESH KUMAR" and intake.registered_name("") == ""


def test_unfile_reverses_a_link_and_forgets_learned_ids(fakes):
    store.create_case("TB-006", {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    job = _upload([("lft.txt", LFT.encode())])
    doc_id = list(job["filed"])[0]
    st = store.get_state("TB-006")
    cm = [c for c in st["confirmations"] if c["type"] == "confirm_match" and c["key"] == doc_id and not c.get("undone")]
    assert len(cm) == 1 and cm[0]["by"] == intake.MATCH_USER and cm[0]["fields"] == {"case_id": "TB-006"}  # the matcher's decision is on record, undoable
    assert store.get_case("TB-006")["patient"]["ids"] and store.get_state("TB-006")["gate"]["documents"]["ready"] == 1
    out = service.unfile_document("TB-006", doc_id, "coord", "wrong patient")
    rec = store.get_intake(doc_id)
    assert store.get_doc("TB-006", doc_id) is None and rec["state"] == "needs_matching" and rec["rejected_cases"] == ["TB-006"] and rec["unfiled"]["by"] == "coord"
    assert "facts" not in rec and "filed" not in rec and rec["pages"] and rec["classification"]  # read once, never re-read
    assert store.get_case("TB-006")["patient"].get("ids", []) == [] and out["state"]["gate"]["documents"]["ready"] == 0
    assert all(c.get("undone") for c in store.get_state("TB-006")["confirmations"] if c["type"] == "confirm_match")
    kinds = [e["kind"] for e in store.read_audit("TB-006")]
    assert "document_unfiled" in kinds and "patient_ids_unlearned" in kinds and "confirmation_undone" in kinds
    assert [e for e in store.read_intake_audit() if e["kind"] == "unfiled"][0]["case_id"] == "TB-006"
    # the record is not linked to TB-006 again on re-read, and a coordinator-uploaded document cannot be unfiled
    async def go():
        j = service.reprocess_intake([doc_id], "coord"); await j["task"]; return j
    j = asyncio.run(go())
    assert j["needs_matching"] == [doc_id] and "not TB-006" in store.get_intake(doc_id)["match"]["reason"]
    d = store.add_document_file("TB-006", "direct.txt", NOID.encode())
    with pytest.raises(ValueError):
        intake.unfile("TB-006", d["doc_id"], "coord")


def test_remove_forgets_learned_ids_and_protected_cases_are_never_matched_or_taught(fakes, monkeypatch):
    store.create_case("TB-006", {"name": "Mohammed Irfan Shaikh", "mrn": "SYN-600744", "agesex": "61 Y / M"}, "lung_nsclc", created_by="t")
    job = _upload([("lft.txt", LFT.encode())])
    doc_id = list(job["filed"])[0]
    assert store.get_case("TB-006")["patient"]["ids"]
    service.delete_document("TB-006", doc_id, "coord")
    assert store.get_case("TB-006")["patient"]["ids"] == [] and any(e["kind"] == "patient_ids_unlearned" for e in store.read_audit("TB-006"))
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-006"})
    job = _upload([("lft2.txt", LFT.replace("0.6", "0.7").encode())])
    cid = list(job["filed"].values())[0]
    assert cid != "TB-006" and cid.startswith("TB-")  # a protected Case File is invisible to the matcher: the record opens its own Case File
    idr = store.get_doc(cid, list(job["filed"])[0])["identity_read"]
    assert intake.learn_ids("TB-006", idr, "t", "Dx") == [] and store.get_case("TB-006")["patient"]["ids"] == []  # and is never taught


def test_intake_record_filed_during_processing_is_not_recreated(fakes, monkeypatch):
    d = store.add_intake_file("rbs.txt", NOID.encode(), "rbs.txt", "laboratory_medicine", "lab.user")

    async def slow_classify(t, audit=None):
        intake.discard(d["doc_id"], "coord", "while reading")  # a person acts while the record is being read
        return dict(CLS)
    monkeypatch.setattr(extract, "classify", slow_classify)
    asyncio.run(intake.process(d["doc_id"]))
    assert not store.intake_doc_dir(d["doc_id"]).exists() and store.list_intake() == []  # no ghost folder


def test_stale_protocol_documents_are_extracted_again_after_listing(fakes, monkeypatch):
    store.create_case("TB-2026-0001", {"name": "Ramesh Kumar", "mrn": "SYN-400118"}, "", created_by="coord")
    d = store.add_document_file("TB-2026-0001", "hpe.txt", LFT.replace("LIVER FUNCTION TESTS", "HISTOPATHOLOGY REPORT").encode())

    async def cls_hpe(t, audit=None):
        c = store.get_case("TB-2026-0001"); c["protocol"] = "lung_nsclc"; c["listing"] = {"status": "listed"}; store.save_case(c)  # listed while the document is in flight
        return {**CLS, "title": "HISTOPATHOLOGY REPORT", "doc_type": "histopathology"}
    monkeypatch.setattr(extract, "classify", cls_hpe)

    async def go():
        job = service._job("TB-2026-0001", 1, [d["doc_id"]]); await service.process_docs("TB-2026-0001", [d["doc_id"]], job); return job
    job = asyncio.run(go())
    doc = store.get_doc("TB-2026-0001", d["doc_id"])
    assert doc["extracted_under"] == "lung_nsclc" and doc["facts"].get("histologic_type") and job["gate"]["total"] == 8


def test_ocr_uncertain_numbers_never_carry_an_aadhaar(monkeypatch):
    reads = iter(["Aadhaar No. 6043 1187 2200\nHb 11.8", "Aadhaar No. 6043 1187 2200\nHb 11.6"])

    async def fake(png, audit=None, max_side=None):
        return next(reads)
    monkeypatch.setattr(ingest, "ocr_image", fake)
    events = []
    page = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert "2200" in page["text"] and "6043 1187 2200" not in page["text"] and page["aadhaar_masked"] == 1
    assert page["ocr_uncertain_numbers"] == ["11.6", "11.8"] and "6043" not in __import__("json").dumps(events)
