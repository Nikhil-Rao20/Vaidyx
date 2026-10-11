"""Case File listing (V1 item 2.5): a Case File started without a protocol shows its records but has no gate; the coordinator lists it
(protocol, NCG setting, board date, hospital level) and the Pre-Authorization check starts: fields extracted from the stored pages, gate
evaluated. Model calls replaced by fakes."""
import asyncio

import pytest

from tumour_board import extract, ingest, org, protocol, rules, search, service, store

HPE = ("Sahyadri Cancer Institute (SYNTHETIC)\nHISTOPATHOLOGY REPORT\nPatient name Mr. Ramesh Kumar\nUHID SYN-400118\nAge / Sex 58 Y / M\n"
       "Diagnosis: Adenocarcinoma\nReport status: FINAL\nReported by: Dr. Fatima Begum, MD (Pathology)")


@pytest.fixture
def fakes(monkeypatch):
    calls = {"classify": 0, "extract": 0}

    async def fake_pages(path, audit=None):
        return [{"text": path.read_bytes().decode(errors="replace"), "method": "plain-text"}]

    async def fake_classify(t, audit=None):
        calls["classify"] += 1
        return {"title": "HISTOPATHOLOGY REPORT", "department": "Pathology", "doc_type": "histopathology", "body_region": "", "report_date": "11/09/2026",
                "status_quote": "", "signature_quote": "", "signer": "", "patient_name": "Mr. Ramesh Kumar", "patient_id": "SYN-400118"}

    async def fake_facts(t, fids, audit=None):
        calls["extract"] += 1
        return {"histologic_type": {"found": True, "value": "Adenocarcinoma", "quote": "Diagnosis: Adenocarcinoma"}} if "histologic_type" in fids else {}
    monkeypatch.setattr(ingest, "extract_pages", fake_pages)
    monkeypatch.setattr(extract, "classify", fake_classify)
    monkeypatch.setattr(extract, "extract_facts", fake_facts)
    monkeypatch.setattr(search, "index", lambda case_id: None)
    return calls


def _run(coro):
    return asyncio.run(coro)


def _unlisted(fakes):
    store.create_case("TB-2026-0001", {"name": "Ramesh Kumar", "mrn": "SYN-400118", "agesex": "58 Y / M"}, "", created_by="coord")
    d = store.add_document_file("TB-2026-0001", "hpe.txt", HPE.encode())
    _run(extract.process_document("TB-2026-0001", d["doc_id"], "", store.get_case("TB-2026-0001")["patient"]))
    return d["doc_id"]


def test_unlisted_case_shows_records_but_no_gate(fakes):
    did = _unlisted(fakes)
    d = store.get_doc("TB-2026-0001", did)
    assert d["state"] == "ready" and d["classification"]["doc_type"] == "histopathology" and d["facts"] == {} and fakes["extract"] == 0
    assert store.get_case("TB-2026-0001")["listing"]["status"] == "awaiting_listing"
    assert rules.evaluate("TB-2026-0001") is None and service.recheck("TB-2026-0001", "coord")["gate"] is None
    assert store.list_cases()[0]["readiness"] is None and store.list_cases()[0]["gate_passed"] is None


def test_listing_triggers_extraction_from_stored_pages_and_the_gate(fakes):
    did = _unlisted(fakes)
    async def go():
        job = service.list_case("TB-2026-0001", "lung_nsclc", "non_metastatic", "18/10/2026", "", "coord")
        await job["task"]
        return job
    job = _run(go())
    c = store.get_case("TB-2026-0001")
    assert c["protocol"] == "lung_nsclc" and c["setting"] == "non_metastatic" and c["board_date"] == "2026-10-18" and c["hospital_level"] == "essential"
    assert c["listing"]["status"] == "listed" and c["listing"]["listed_by"] == "coord" and c["listing"]["previous"] == {"status": "awaiting_listing"}
    assert job["state"] == "finished" and job["listed"] is True and job["total"] == 1 and job["gate"]["total"] == 5  # lung Essential records (V1 item 4.1)
    d = store.get_doc("TB-2026-0001", did)
    assert d["facts"]["histologic_type"]["verification"] == "verified" and fakes["classify"] == 1 and fakes["extract"] == 1  # stored pages and classification reused
    g = store.get_state("TB-2026-0001")["gate"]
    assert g["setting"] == "non_metastatic" and g["hospital_level"] == "essential" and g["protocol"] == "lung_nsclc"
    assert next(r for r in g["requirements"] if r["id"] == "histopathology")["status"] == "satisfied"
    assert any(e["kind"] == "case_listed" and e["by"] == "coord" and e["before"]["protocol"] == "" for e in store.read_audit("TB-2026-0001"))
    assert store.list_cases()[0]["listing"]["status"] == "listed" and store.list_cases()[0]["readiness"] is not None


def test_listing_validates_protocol_setting_level_and_date(fakes):
    _unlisted(fakes)
    with pytest.raises(ValueError):
        service.list_case("TB-2026-0001", "cervix", "", "", "", "coord")
    with pytest.raises(ValueError):
        service.list_case("TB-2026-0001", "lung_nsclc", "early", "", "", "coord")  # a breast setting on a lung protocol
    with pytest.raises(ValueError):
        service.list_case("TB-2026-0001", "lung_nsclc", "", "", "premium", "coord")
    with pytest.raises(ValueError):
        service.list_case("TB-2026-0001", "lung_nsclc", "", "next tuesday", "", "coord")
    with pytest.raises(KeyError):
        service.list_case("TB-NONE", "lung_nsclc", "", "", "", "coord")
    assert store.get_case("TB-2026-0001")["listing"]["status"] == "awaiting_listing"


def test_hospital_level_defaults_from_org(fakes):
    o = org.load(); org.save({**o, "hospital": {**o["hospital"], "level": "optimal"}}, by="t")
    _unlisted(fakes)
    async def go():
        job = service.list_case("TB-2026-0001", "lung_nsclc", "", "", "", "coord"); await job["task"]
    _run(go())
    assert store.get_case("TB-2026-0001")["hospital_level"] == "optimal" and store.get_state("TB-2026-0001")["gate"]["hospital_level"] == "optimal"


def test_changing_only_setting_or_date_rechecks_without_extracting_again(fakes):
    _unlisted(fakes)
    async def go(*a):
        job = service.list_case("TB-2026-0001", *a); 
        if job.get("task"):
            await job["task"]
        return job
    _run(go("lung_nsclc", "non_metastatic", "", "", "coord"))
    n = fakes["extract"]
    job = _run(go("lung_nsclc", "metastatic", "2026-10-25", "optimal", "coord"))
    c = store.get_case("TB-2026-0001")
    assert fakes["extract"] == n and job["total"] == 0 and job["gate"]["total"] == 8 and c["setting"] == "metastatic" and c["board_date"] == "2026-10-25"  # Optimal hospital: + PD-L1, MET, PET-CT
    job = _run(go("breast", "", "", "", "coord"))  # another protocol: fields extracted again under it
    assert job["total"] == 1 and fakes["extract"] == n + 1 and store.get_state("TB-2026-0001")["gate"]["protocol"] == "breast"


def test_every_protocol_has_ncg_settings():
    for p in protocol.list_protocols():
        assert p["settings"] and all(s["id"] and s["label"] for s in p["settings"]), p["id"]
        assert protocol.settings(p["id"]) == p["settings"] and protocol.exists(p["id"])
    assert not protocol.exists("facts") and not protocol.exists("") and not protocol.exists("cervix")


def test_create_case_listed_or_awaiting():
    c = store.create_case("TB-A", {"name": "X"}, "lung_nsclc", "2026-10-18", "coord", "metastatic", "optimal")
    assert c["listing"]["status"] == "listed" and c["setting"] == "metastatic" and c["hospital_level"] == "optimal"
    u = store.create_case("TB-B", {"name": "Y"}, "", created_by="coord")
    assert u["listing"] == {"status": "awaiting_listing"} and u["protocol"] == "" and u["setting"] == ""
