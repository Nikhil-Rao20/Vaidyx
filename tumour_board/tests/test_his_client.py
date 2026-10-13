"""HIS adapter (V2 item 3.1): the FHIR client against answers captured from the mock hospital (SYNTHETIC), the MCP transport
against the in-process demo HIS, the code tables and the settings.

Hermetic: fixtures/his/ holds trimmed answers of the live mock (re-capture with fixtures/his/_capture.py), served through
httpx.MockTransport keyed by path + query. One live test runs only when the mock answers on 127.0.0.1:7130."""
import asyncio
import base64
import hashlib
import json
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from tumour_board import config, his_client
from tumour_board.his_client import FHIRClient, HISError, MCPHISClient, doc_type_for, fact_for

FIX = Path(__file__).resolve().parent / "fixtures" / "his"
INDEX = json.loads((FIX / "index.json").read_text())
TOKEN = "unit-token"
BASE = "http://127.0.0.1:7130"


def key_of(url: httpx.URL) -> str:
    q = url.query.decode() if isinstance(url.query, bytes) else str(url.query)
    return unquote(url.raw_path.decode().split("?")[0]) + (("?" + unquote(q)) if q else "")


def fixture(key: str):
    return json.loads((FIX / INDEX[key]).read_text())


def bundle(resources):
    return {"resourceType": "Bundle", "type": "searchset", "total": len(resources),
            "entry": [{"resource": r} for r in resources]}


class Mock:
    """The captured mock hospital. `overrides`: {key: callable(request) -> httpx.Response | dict}. Records every request."""

    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.seen = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = key_of(request.url)
        self.seen.append(request)
        assert TOKEN not in str(request.url)                       # the token never rides in a URL
        if not key.endswith("/metadata"):
            assert request.headers.get("authorization") == f"Bearer {TOKEN}"
        if key in self.overrides:
            got = self.overrides[key](request)
            return got if isinstance(got, httpx.Response) else httpx.Response(200, json=got)
        name = INDEX.get(key)
        if not name:
            return httpx.Response(404, json={"resourceType": "OperationOutcome",
                                             "issue": [{"severity": "error", "code": "not-found", "diagnostics": key}]})
        if name.endswith(".pdf"):
            return httpx.Response(200, content=(FIX / name).read_bytes(), headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=(FIX / name).read_bytes(), headers={"content-type": "application/fhir+json"})

    def keys(self):
        return [key_of(r.url) for r in self.seen]


def fhir(overrides=None):
    m = Mock(overrides)
    return FHIRClient(BASE, TOKEN, transport=httpx.MockTransport(m)), m


def run(coro):
    return asyncio.run(coro)


def _age(dob):
    b, t = date.fromisoformat(dob), date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


# ------------------------------------------------------------------------------------------------ patients
def test_find_patient_by_uhid_abha_and_pmjay():
    c, m = fhir()
    p = run(c.find_patient("VXH/26/004201"))
    assert p["id"] == "vxh-26-004201" and p["ref"] == "Patient/vxh-26-004201" and p["uhid"] == "VXH/26/004201"
    assert p["registration_kind"] == "permanent" and p["name"] == "Anitha Reddy (SYNTHETIC)" and p["sex"] == "F"
    assert p["dob"] == "1980-01-18" and p["age"] == _age("1980-01-18")
    assert p["abha"] == "99-2600-0000-0101" and p["abha_address"] == "anitha.reddy@sbx" and p["pmjay_id"] == "PMJAY-VX-26000101"
    assert {i["kind"] for i in p["identifiers"]} == {"uhid", "abha", "abha_address", "pmjay"}
    assert p["phone"].startswith("+91") and p["registered_on"] == "2026-09-01"
    assert p["matched_on"] == {"kind": "uhid", "value": "VXH/26/004201"} and p["similar"] == []
    assert "aadhaar" not in json.dumps(p).lower()
    assert run(c.find_patient("99-2600-0000-0101"))["matched_on"] == {"kind": "abha", "value": "99-2600-0000-0101"}
    assert run(c.find_patient(" anitha.reddy@sbx "))["matched_on"] == {"kind": "abha_address", "value": "anitha.reddy@sbx"}
    assert all(TOKEN not in str(r.url) for r in m.seen)


def test_find_patient_by_ip_and_op_number_through_the_encounter():
    c, m = fhir()
    p = run(c.find_patient("IP/26/01875"))
    assert p["id"] == "vxh-26-004212" and p["matched_on"] == {"kind": "ip_no", "value": "IP/26/01875"}
    assert m.keys()[:3] == ["/fhir/Patient?identifier=IP/26/01875", "/fhir/Encounter?identifier=IP/26/01875",
                            "/fhir/Patient/vxh-26-004212"]
    p = run(c.find_patient("OP/26/118701"))
    assert p["id"] == "vxh-26-004201" and p["matched_on"]["kind"] == "op_no"


def test_find_patient_unknown_and_empty_return_none():
    empty = lambda r: bundle([])
    c, m = fhir({"/fhir/Patient?identifier=Anitha Reddy": empty, "/fhir/Encounter?identifier=Anitha Reddy": empty})
    assert run(c.find_patient("VXH/26/999999")) is None
    assert run(c.find_patient("  ")) is None
    # no name search: a name is only ever tried as an exact identifier
    assert run(c.find_patient("Anitha Reddy")) is None
    assert all("name=" not in k for k in m.keys())


def test_temporary_registration_and_similar_registrations_are_listed_never_merged():
    c, _ = fhir()
    t = run(c.find_patient("VXH/T/26/00412"))
    assert t["id"] == "vxh-t-26-00412" and t["registration_kind"] == "temporary" and t["uhid"] == "VXH/T/26/00412"
    assert [s["id"] for s in t["similar"]] == ["vxh-26-004209"]
    p = run(c.find_patient("VXH/26/004209"))
    assert p["id"] == "vxh-26-004209" and p["registration_kind"] == "permanent"
    assert [(s["id"], s["registration_kind"]) for s in p["similar"]] == [("vxh-t-26-00412", "temporary")]
    assert "similar" not in p["similar"][0] and "matched_on" not in p["similar"][0]
    assert p["uhid"] == "VXH/26/004209" and p["similar"][0]["uhid"] == "VXH/T/26/00412"   # two registrations, kept apart
    assert [s["id"] for s in run(c.similar("vxh-26-004209"))] == ["vxh-t-26-00412"]


def test_one_identifier_on_two_registrations_is_an_error():
    pats = fixture("/fhir/Patient?identifier=VXH/26/004209")["entry"] + fixture("/fhir/Patient?identifier=VXH/T/26/00412")["entry"]
    c, _ = fhir({"/fhir/Patient?identifier=VXH/26/004209": lambda r: bundle([e["resource"] for e in pats])})
    with pytest.raises(HISError, match="more than one registration"):
        run(c.find_patient("VXH/26/004209"))


# ------------------------------------------------------------------------------------------------ encounters
def test_encounters_with_ward_history_and_preauth():
    c, _ = fhir()
    encs = run(c.encounters("vxh-26-004203"))
    assert [e["kind"] for e in encs][0] == "OP" and encs == sorted(encs, key=lambda e: e["start"])
    ip = next(e for e in encs if e["number"] == "IP/26/01872")
    assert ip["kind"] == "IP" and ip["department"] == "Breast Surgery" and ip["unit"] == "Unit II"
    assert ip["consultant"]["name"].startswith("Dr ") and ip["end"]
    assert [(w["ward"], w["bed"]) for w in ip["ward_history"]] == [("Surgical Ward 2", "2-14"), ("High Dependency Unit", "HDU-04"),
                                                                  ("Surgical Ward 2", "2-09")]
    assert ip["ward_history"][1]["reason"] == "Observation after a hypotensive episode"
    assert ip["ward_history"][0]["to"] == ip["ward_history"][1]["from"]
    p01 = run(c.encounters("vxh-26-004201"))
    adm = next(e for e in p01 if e["kind"] == "IP")
    assert adm["pmjay_preauth"] == {"status": "approved", "date": "2026-09-19"}
    assert next(e for e in p01 if e["kind"] == "OP")["pmjay_preauth"] is None


# ------------------------------------------------------------------------------------------------ reports
def test_reports_every_version_with_status_signature_and_observations():
    c, m = fhir()
    reps = run(c.reports("vxh-26-004202"))
    assert len(reps) == 11 and len({(r["id"], r["version"]) for r in reps}) == 11
    ihc = [r for r in reps if r["id"] == "p02-r05"]
    assert [(r["version"], r["status"], r["current"]) for r in ihc] == [(1, "final", False), (2, "amended", True)]
    v1, v2 = ihc
    assert v1["document_ref"] == "DocumentReference/doc-p02-r05-v1" and v2["document_ref"] == "DocumentReference/doc-p02-r05-v2"
    assert v1["ref"] == v2["ref"] == "DiagnosticReport/p02-r05" and v2["kind"] == "diagnostic"
    assert v1["doc_type"] == "ihc" and "11526-1" in v1["doc_type_basis"]
    her2 = lambda r: next(o for o in r["observations"] if o["fact"] == "her2")
    assert her2(v1)["value"] == "2+ (Equivocal)" and her2(v2)["value"] == "3+ (Positive)"   # superseded Observations read by id
    assert {o["fact"] for o in v2["observations"]} == {"er", "pr", "her2", "ki67"}
    assert "HER2 re-scored" in v2["amendment_note"] and v1["amendment_note"] == ""
    assert v2["accession"] == "PATH/26/00415" and v2["order_ref"] == "ServiceRequest/path-26-00415"
    assert v2["encounter_number"] == "OP/26/118703" and v2["encounter_kind"] == "OP"
    assert v2["performer_department"] == "Pathology" and v2["reported_by"]["name"].startswith("Dr ")
    s1, s2 = v1["signature"], v2["signature"]
    assert s1["ref"] == "Provenance/sig-p02-r05-v1" and s2["ref"] == "Provenance/sig-p02-r05-v2"
    assert s2["verification_status"] == "verified" and s2["ca"] == "Vaidyx Demo CA" and s2["serial"]
    assert s2["block"].startswith("Digitally signed by") and s2["signed_at"] == "2026-09-16T11:30:00+05:30"
    assert s2["document_hash"] == v2["document"]["sha256"] and s2["hash_matches"] is True
    assert len(v2["document"]["sha256"]) == 64 and v2["document"]["sha1_b64"] and v2["document"]["content_type"] == "application/pdf"
    assert v2["document"]["url"].endswith("/p02-r05-v2.pdf")
    assert m.keys().count("/fhir/DiagnosticReport/p02-r05/_history") == 1
    # one $everything, one _history, the superseded version's Observations
    assert m.keys()[0] == "/fhir/Patient/vxh-26-004202/$everything"
    # oldest version first within a report
    assert reps.index(v1) < reps.index(v2)
    cbc = next(r for r in reps if r["id"] == "p02-r08")
    assert cbc["doc_type"] == "lab" and {o["fact"]: o["value"] for o in cbc["observations"]}["haemoglobin"] == "11.2 gm%"
    note = next(r for r in reps if r["id"] == "p02-r01")
    assert note["kind"] == "note" and note["ref"] is None and note["doc_type"] == "clinical_note" and note["observations"] == []
    assert note["signature"]["verification_status"] == "verified"


def test_report_doc_types_and_facts_for_a_breast_work_up():
    c, _ = fhir()
    reps = run(c.reports("vxh-26-004201"))
    by = {r["id"]: r for r in reps}
    assert {r["doc_type"] for r in reps} == {"lab", "clinical_note", "mammogram", "ultrasound", "histopathology", "ihc"}
    assert by["p01-r02"]["doc_type"] == "mammogram" and by["p01-r02"]["imaging_study_ref"].startswith("ImagingStudy/")
    assert by["p01-r06"]["observations"][0] == {"id": "obs-p01-r06-v1-haemoglobin",
                                                 "code": {"system": "http://loinc.org", "code": "718-7",
                                                          "display": "Hemoglobin [Mass/volume] in Blood"},
                                                 "label": "Haemoglobin (Hb)", "fact": "haemoglobin", "value": "12.1 gm%",
                                                 "status": "final"}
    hpe = by["p01-r04"]
    assert {o["fact"] for o in hpe["observations"]} >= {"histologic_type", "grade"}
    assert all(r["current"] and r["version"] == 1 and r["status"] == "final" for r in reps)
    assert "base64" not in json.dumps(reps)


def test_failed_signature_verification_is_reported():
    c, _ = fhir()
    r10 = next(r for r in run(c.reports("vxh-26-004203")) if r["id"] == "p03-r10")
    assert r10["doc_type"] == "discharge_summary" and r10["kind"] == "note" and r10["encounter_number"] == "IP/26/01872"
    assert r10["signature"]["verification_status"] == "failed" and r10["signature"]["hash_matches"] is False


def test_preliminary_ct_with_its_imaging_study():
    c, _ = fhir()
    ct = next(r for r in run(c.reports("vxh-26-004212")) if r["id"] == "p12-r02")
    assert ct["status"] == "preliminary" and ct["signature"] is None and ct["doc_type"] == "ct"
    assert ct["reported_by"]["name"].startswith("Dr ") and ct["encounter_kind"]
    assert ct["imaging_study_ref"] == "ImagingStudy/img-rad-26-01004"
    s = run(c.imaging_study(ct["imaging_study_ref"]))
    assert s["study_uid"].startswith("2.25.") and not s["study_uid"].startswith("urn:oid:")
    assert s["accession"] == "RAD/26/01004" and s["modality"] == "CT" and s["status"] == "available"
    assert s["viewer_url"].endswith(s["study_uid"]) and s["dicomweb_url"] == f"/dicom-web/studies/{s['study_uid']}"
    assert s["series"] == 1 and s["instances"] == 8 and s["description"]
    assert run(c.imaging_study("ImagingStudy/img-nope")) is None


def test_delta_reports_since_a_watermark():
    c, m = fhir()
    reps = run(c.reports("vxh-26-004202", since="2026-09-10T00:00:00+05:30"))
    assert [(r["id"], r["version"], r["status"], r["current"]) for r in reps] == [("p02-r05", 1, "final", False),
                                                                              ("p02-r05", 2, "amended", True)]
    assert "/fhir/DiagnosticReport?patient=vxh-26-004202&_lastUpdated=ge2026-09-10T00:00:00+05:30" in m.keys()
    assert all("$everything" not in k for k in m.keys())
    assert all("%2B05:30" in str(r.url) or "_lastUpdated" not in str(r.url) for r in m.seen)   # '+' encoded
    v1, v2 = reps
    assert v2["encounter_number"] == "OP/26/118703" and v2["accession"] == "PATH/26/00415" and v2["signature"]["hash_matches"]
    assert {o["fact"]: o["value"] for o in v1["observations"]}["her2"] == "2+ (Equivocal)"
    # nothing changed since a later watermark: two searches, no reads
    empty = lambda r: bundle([])
    c2, m2 = fhir({"/fhir/DiagnosticReport?patient=vxh-26-004202&_lastUpdated=ge2026-10-01T00:00:00+05:30": empty,
                   "/fhir/DocumentReference?patient=vxh-26-004202&_lastUpdated=ge2026-10-01T00:00:00+05:30": empty})
    assert run(c2.reports("vxh-26-004202", since="2026-10-01")) == [] and len(m2.seen) == 2


# ------------------------------------------------------------------------------------------------ orders and referrals
def test_open_orders_by_stage():
    c, _ = fhir()
    (o15,) = run(c.open_orders("vxh-26-004215"))
    assert o15["stage"] == "sample_collected" and o15["status"] == "active" and o15["doc_type"] == "molecular"
    assert o15["specimen"]["barcode"] == "VXS26000170" and o15["specimen"]["block_no"] == "PATH/26/00451-A1"
    assert o15["specimen"]["collected"] and o15["accession"] == "PATH/26/00451" and o15["encounter_number"] == "IP/26/01878"
    assert o15["performer_department"] == "Pathology" and o15["requester_department"] == "Medical Oncology"
    (o04,) = run(c.open_orders("vxh-26-004204"))
    assert o04["stage"] == "scheduled" and o04["scheduled_for"] == "2026-09-10" and o04["doc_type"] == "bone_scan"
    (o10,) = run(c.open_orders("vxh-26-004210"))
    assert o10["stage"] == "cancelled" and o10["status"] == "revoked" and o10["doc_type"] == "ct"
    assert o10["note"] == "Cancelled: Patient did not report on the scheduled date" and o10["test"] == "CECT abdomen and pelvis"
    (o08,) = run(c.open_orders("vxh-26-004208"))
    assert o08["stage"] == "ordered" and o08["doc_type"] == "lab" and o08["specimen"] is None
    assert run(c.open_orders("vxh-26-004214")) == []          # a referral is never an order


def test_referrals():
    c, _ = fhir()
    (r,) = run(c.referrals("vxh-26-004214"))
    assert r["ref"] == "ServiceRequest/ref-ip-26-01877-1" and r["encounter_number"] == "IP/26/01877"
    assert (r["from_department"], r["to_department"], r["status"]) == ("Pulmonology", "Colorectal Surgery", "accepted")
    assert r["requested"] == "2026-09-04" and r["accepted"] == "2026-09-04" and "colorectal origin" in r["reason"]
    assert run(c.referrals("vxh-26-004215")) == []


# ------------------------------------------------------------------------------------------------ documents
PDF = (FIX / INDEX["/documents/documents/p02-r05-v2.pdf"]).read_bytes()


def test_document_bytes_by_url_with_the_checksum():
    c, m = fhir()
    d = run(c.document("DocumentReference/doc-p02-r05-v2"))
    assert d["content"] == PDF and d["content"].startswith(b"%PDF") and d["size"] == len(PDF)
    assert d["sha256"] == hashlib.sha256(PDF).hexdigest() == fixture("/fhir/DocumentReference/doc-p02-r05-v2")["extension"][0]["valueString"]
    assert d["content_type"] == "application/pdf" and d["status"] == "current" and d["doc_status"] == "amended"
    assert d["filename"].endswith(".pdf") and "/" not in d["filename"] and " " not in d["filename"] and "doc_p02_r05_v2" in d["filename"]
    assert m.keys() == ["/fhir/DocumentReference/doc-p02-r05-v2", "/documents/documents/p02-r05-v2.pdf"]
    assert m.seen[1].headers["authorization"] == f"Bearer {TOKEN}"


def test_document_inline_base64_and_checksum_mismatch():
    doc = fixture("/fhir/DocumentReference/doc-p02-r05-v2")
    inline = json.loads(json.dumps(doc))
    inline["content"][0]["attachment"]["data"] = base64.b64encode(PDF).decode()
    c, m = fhir({"/fhir/DocumentReference/doc-p02-r05-v2": lambda r: inline})
    assert run(c.document("doc-p02-r05-v2"))["content"] == PDF and len(m.seen) == 1     # no second request
    bad = json.loads(json.dumps(doc))
    bad["extension"][0]["valueString"] = "0" * 64
    c, _ = fhir({"/fhir/DocumentReference/doc-p02-r05-v2": lambda r: bad})
    with pytest.raises(HISError, match="checksum mismatch"):
        run(c.document("DocumentReference/doc-p02-r05-v2"))
    c, _ = fhir({"/documents/documents/p02-r05-v2.pdf": lambda r: httpx.Response(200, content=PDF[:-1] + b"X")})
    with pytest.raises(HISError, match="checksum mismatch"):
        run(c.document("DocumentReference/doc-p02-r05-v2"))
    with pytest.raises(HISError, match="no document"):
        run(fhir()[0].document("DocumentReference/doc-nope"))


def test_document_url_on_another_server_is_refused():
    doc = fixture("/fhir/DocumentReference/doc-p02-r05-v2")
    doc["content"][0]["attachment"]["url"] = "http://elsewhere.invalid/x.pdf"
    c, m = fhir({"/fhir/DocumentReference/doc-p02-r05-v2": lambda r: doc})
    with pytest.raises(HISError, match="another server"):
        run(c.document("DocumentReference/doc-p02-r05-v2"))
    assert len(m.seen) == 1


def test_hospital_departments():
    c, _ = fhir()
    h = run(c.hospital())
    assert h["name"] == "Vaidyx Demo Hospital (SYNTHETIC)"
    by = {d["name"]: d for d in h["departments"]}
    assert by["Pathology"] == {"name": "Pathology", "group": "supporting", "email": "path@vaidyx-demo.invalid"}
    assert by["Breast Surgery"]["group"] == "treating" and len(h["departments"]) >= 20


# ------------------------------------------------------------------------------------------------ errors and ping
def test_ping_and_token_errors():
    c, _ = fhir()
    assert run(c.ping()) == {"ok": True, "name": "Vaidyx Demo Hospital HIS (SYNTHETIC)", "fhir_version": "4.0.1", "token_ok": True,
                             "error": ""}
    refuse = lambda r: httpx.Response(401, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "bad token"}]})
    c, _ = fhir({"/fhir/Patient?_count=0": refuse, "/fhir/Patient?identifier=VXH/26/004201": refuse})
    p = run(c.ping())
    assert p["ok"] is False and p["token_ok"] is False and "token" in p["error"] and TOKEN not in p["error"]
    with pytest.raises(HISError, match="refused the token") as e:
        run(c.find_patient("VXH/26/004201"))
    assert TOKEN not in str(e.value)


def test_connection_error_and_bad_answers():
    def down(request):
        raise httpx.ConnectError("connection refused", request=request)
    c = FHIRClient(BASE, TOKEN, transport=httpx.MockTransport(down))
    with pytest.raises(HISError, match="cannot reach the HIS"):
        run(c.reports("vxh-26-004201"))
    p = run(c.ping())
    assert p["ok"] is False and "cannot reach" in p["error"] and p["token_ok"] is None
    c, _ = fhir({"/fhir/Patient/vxh-26-004201/$everything": lambda r: httpx.Response(200, content=b"<html>")})
    with pytest.raises(HISError, match="not JSON"):
        run(c.reports("vxh-26-004201"))
    c, _ = fhir({"/fhir/Patient/vxh-26-004201/$everything": lambda r: httpx.Response(500)})
    with pytest.raises(HISError, match="HTTP 500"):
        run(c.open_orders("vxh-26-004201"))
    with pytest.raises(HISError, match="no registration"):
        run(fhir()[0].reports("vxh-nope"))
    with pytest.raises(HISError):
        FHIRClient("ftp://x", TOKEN)


# ------------------------------------------------------------------------------------------------ code tables
@pytest.mark.parametrize("args,expected", [
    (("11488-4", [], "OPD consultation note"), "clinical_note"),
    (("57133-1", [], "Referral letter"), "referral"),
    (("18842-5", [], "Discharge summary"), "discharge_summary"),
    (("18751-8", [], "Colonoscopy"), "endoscopy"),
    (("58410-2", [], "Complete blood count"), "lab"),
    (("24325-3", [], "Liver function tests"), "lab"),
    (("2039-6", [], "CEA"), "lab"),
    (("11526-1", [], "IHC: ER, PR, HER2, Ki-67"), "ihc"),
    (("11526-1", [], "Histopathology report (biopsy)"), "histopathology"),
    (("11526-1", [], "Molecular: EGFR, ALK, ROS1, MET"), "molecular"),
    (("11526-1", [], "FNAC cytology report"), "cytology"),
    (("11526-1", [], "Pathology study"), "histopathology"),
    (("18748-4", ["310128004"], "CECT thorax, abdomen and pelvis"), "ct"),
    (("18748-4", ["394914008"], "Bilateral mammogram"), "mammogram"),
    (("18748-4", ["394914008"], "USG both breasts and axillae"), "ultrasound"),
    (("18748-4", ["394914008"], "MRI pelvis"), "mri"),
    (("18748-4", ["394914008"], "Chest X-ray PA view"), "xray"),
    (("18748-4", ["394914008"], "Whole-body bone scan (Tc-99m MDP)"), "bone_scan"),
    (("", [], "Histopathology report"), "histopathology"),
    (("", [], "Unlabelled scan"), ""),
])
def test_doc_type_for(args, expected):
    assert doc_type_for(*args)[0] == expected


def test_doc_type_for_basis_and_modality():
    assert doc_type_for({"system": "http://loinc.org", "code": "11488-4"}) == ("clinical_note", "LOINC 11488-4")
    assert doc_type_for("18748-4", [], "Imaging study", modality="PT")[0] == "pet_ct"
    t, basis = doc_type_for("18748-4", [{"code": "310128004"}], "Anything")
    assert t == "ct" and "310128004" in basis
    assert "no narrower keyword" in doc_type_for("11526-1", [], "Pathology study")[1]


def test_fact_for_codes_and_labels():
    assert fact_for({"system": "http://loinc.org", "code": "718-7"}, "Hb") == "haemoglobin"
    assert fact_for("48676-1", "") == "her2"
    labels = {
        "Haemoglobin (Hb)": "haemoglobin", "Total leucocyte count (TLC)": "wbc", "Platelet count": "platelets",
        "Serum creatinine": "creatinine", "Serum bilirubin (total)": "bilirubin", "Carcinoembryonic antigen (CEA)": "cea",
        "Oestrogen receptor (ER)": "er", "Progesterone receptor (PR)": "pr", "HER2/neu (IHC score)": "her2",
        "Ki-67 labelling index": "ki67", "Ki67": "ki67", "PD-L1 (22C3), tumour proportion score": "pdl1",
        "EGFR mutation analysis": "egfr", "ALK rearrangement": "alk", "ROS1 rearrangement": "ros1",
        "MET exon 14 skipping": "met", "KRAS mutation analysis": "kras", "MMR proteins": "mmr", "MSI status": "mmr",
        "BRAF V600E": "ras_braf", "HIV 1 and 2 antibodies": "hiv_status", "ECOG performance status": "ecog",
        "FIGO stage": "figo_stage", "Staging": "recorded_stage", "Histological type": "histologic_type", "Grade": "grade",
        "Lymphovascular invasion": "lvi", "Perineural invasion": "pni", "Resection margins": "margins",
        "Lesion size": "lesion_size", "Distance from the anal verge": "distance_from_anal_verge",
        "Mesorectal fascia (MRF)": "mrf_status", "Extramural venous invasion (EMVI)": "emvi", "SUV (maximum)": "suv_max",
        "Depth of invasion": "depth_of_invasion", "Parametria": "parametrial_involvement", "Extranodal extension": "ene",
        "Lymph nodes": "nodal_findings", "Distant sites": "distant_findings", "Menopausal status": "menopausal_status",
        "Comorbidities": "comorbidities", "Smoking history": "smoking_history", "Tobacco use": "tobacco_use",
        "Dental evaluation": "dental_evaluation", "Presenting complaint": "presenting_complaint",
        "Clinical question": "clinical_question",
        # printed by the mock, no fact
        "BI-RADS category": "", "Blood urea": "", "SGOT (AST)": "", "SGPT (ALT)": "", "HBsAg": "", "Anti-HCV antibodies": "",
        "Bladder": "", "Rectum": "", "Kidneys and ureters": "", "Tracheobronchial tree": "",
    }
    got = {k: fact_for(None, k) for k in labels}
    assert got == labels
    facts = set(json.loads((config.PROTOCOL_DIR / "facts.json").read_text())["facts"])
    t = his_client.codes()
    assert set(t["fact_by_loinc"].values()) <= facts and {f for _, f in t["fact_by_label"]} <= facts
    assert "vendor-extensible" in t["_note"].lower() or "vendor" in t["_note"].lower()


def test_every_observation_label_of_the_mock_maps_or_is_known_unmapped():
    """Every label in the captured answers either maps to a fact or is one of the mock's non-fact values."""
    no_fact = {"BI-RADS category", "Blood urea", "SGOT (AST)", "SGPT (ALT)", "HBsAg", "Anti-HCV antibodies", "Bladder", "Rectum",
               "Kidneys and ureters", "Tracheobronchial tree"}
    seen = set()
    for name in INDEX.values():
        if not name.endswith(".json"):
            continue
        d = json.loads((FIX / name).read_text())
        for e in d.get("entry") or [{"resource": d}]:
            r = e.get("resource") or {}
            if r.get("resourceType") == "Observation":
                seen.add(((r["code"].get("coding") or [{}])[0].get("code"), r["code"].get("text")))
    assert len(seen) > 15
    for code, label in seen:
        assert fact_for(code, label) or label in no_fact, label


# ------------------------------------------------------------------------------------------------ settings
def test_settings_default_env_and_client(monkeypatch):
    for k in ("TB_HIS_URL", "TB_HIS_TOKEN", "TB_HIS_TOKEN_FILE"):
        monkeypatch.delenv(k, raising=False)
    d = his_client.settings()
    assert d["kind"] == "fhir" and d["url"] == "http://127.0.0.1:7130" and d["enabled"] is True
    assert d["label"] == "Vaidyx Demo Hospital HIS (SYNTHETIC)" and d["token_file"].endswith("data/his_mock/token")
    assert isinstance(his_client.client(), FHIRClient)
    monkeypatch.setenv("TB_HIS_URL", "https://his.example.invalid/fhir")
    monkeypatch.setenv("TB_HIS_TOKEN", "env-secret")
    d = his_client.settings()
    assert d["url"] == "https://his.example.invalid/fhir" and his_client.token(d) == "env-secret"
    c = his_client.client()
    assert c.fhir_base == "https://his.example.invalid/fhir" and c.origin == "https://his.example.invalid"
    assert "env-secret" not in repr(c)
    assert his_client.client({**d, "enabled": False}) is None and his_client.client({**d, "kind": "none"}) is None


def test_save_settings_validates_and_never_audits_the_token(data_root, monkeypatch):
    for k in ("TB_HIS_URL", "TB_HIS_TOKEN", "TB_HIS_TOKEN_FILE"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match="url"):
        his_client.save_settings({"kind": "fhir", "url": "ftp://x", "token": "t"}, by="root")
    with pytest.raises(ValueError, match="token"):
        his_client.save_settings({"kind": "fhir", "url": "http://127.0.0.1:7999/fhir"}, by="root")  # a new host on this server: the demo token file never follows
    with pytest.raises(ValueError, match="kind"):
        his_client.save_settings({"kind": "hl7", "url": "http://x"}, by="root")
    with pytest.raises(ValueError, match="connector"):
        his_client.save_settings({"kind": "mcp", "connector": "nope"}, by="root")
    # review S2: a root admin cannot point the connection outside this server; a Vaidyx admin can
    with pytest.raises(ValueError, match="Vaidyx admin"):
        his_client.save_settings({"kind": "fhir", "url": "http://10.0.0.5:8080/fhir", "token": "s3cret-token"}, by="root")
    pub = his_client.save_settings({"kind": "fhir", "label": "City HIS", "url": "http://10.0.0.5:8080/fhir",
                                    "token": "s3cret-token", "enabled": True}, by="root", allow_remote=True)
    assert "token" not in pub and pub["has_token"] is True and pub["url"] == "http://10.0.0.5:8080/fhir"
    saved = json.loads((data_root / "his.json").read_text())
    assert saved["token"] == "s3cret-token"
    ev = json.loads((data_root / "org_audit.jsonl").read_text().splitlines()[-1])
    assert ev["kind"] == "his_settings_saved" and ev["by"] == "root" and ev["has_token"] is True
    assert "s3cret-token" not in (data_root / "org_audit.jsonl").read_text()
    assert his_client.settings()["label"] == "City HIS" and his_client.token() == "s3cret-token"
    # an edit without retyping the token keeps it (same host)
    his_client.save_settings({"kind": "fhir", "label": "City HIS 2", "url": "http://10.0.0.5:8080/fhir"}, by="root", allow_remote=True)
    assert his_client.token() == "s3cret-token" and his_client.settings()["label"] == "City HIS 2"
    # review S2: a change of host never carries the saved token or token file along; the request's token_file is never used
    with pytest.raises(ValueError, match="token"):
        his_client.save_settings({"kind": "fhir", "label": "Other", "url": "http://10.0.0.6:8080/fhir", "token_file": "/etc/passwd"}, by="root", allow_remote=True)
    his_client.save_settings({"kind": "fhir", "label": "Other", "url": "http://10.0.0.6:8080/fhir", "token": "new-token", "token_file": "/etc/passwd"}, by="root", allow_remote=True)
    saved = json.loads((data_root / "his.json").read_text())
    assert saved["token"] == "new-token" and saved["token_file"] == "" and his_client.token() == "new-token"
    his_client.save_settings({"kind": "fhir", "url": "http://10.0.0.6:8080/fhir", "token_file": "/etc/passwd"}, by="root", allow_remote=True)
    assert json.loads((data_root / "his.json").read_text())["token_file"] == ""  # never taken from the request
    # TB_HIS_ALLOW_HOSTS lets a root admin name a listed host
    monkeypatch.setenv("TB_HIS_ALLOW_HOSTS", "his.hospital.example:8443")
    his_client.save_settings({"kind": "fhir", "url": "https://his.hospital.example:8443/fhir", "token": "t2"}, by="root")
    assert his_client.settings()["url"] == "https://his.hospital.example:8443/fhir"
    # the token file's server path is shown to a manager only
    assert his_client.public(his_client._default_settings(), manager=False)["token_file"] is True
    assert his_client.public(his_client._default_settings())["token_file"].endswith("token")
    tf = data_root / "tok"
    tf.write_text("file-token\n")
    assert his_client.token({"token": "", "token_file": str(tf)}) == "file-token"
    assert his_client.public({"token": "", "token_file": str(data_root / "missing")})["has_token"] is False
    his_client.save_settings({"kind": "none"}, by="root")
    assert his_client.client() is None


# ------------------------------------------------------------------------------------------------ MCP transport
def test_mcp_transport_against_the_demo_his(tmp_path, monkeypatch):
    from tumour_board import connectors
    from tumour_board.demo_data import demo_his_mcp
    from tumour_board.tests.test_connectors import CONN, INPROC, TOKEN as MCP_TOKEN, _client_for, _index
    index = _index(tmp_path)
    monkeypatch.setattr(demo_his_mcp, "_index", lambda corpus=None: index)
    factory = lambda: _client_for(demo_his_mcp.http_app(demo_his_mcp.build(**INPROC), expected=MCP_TOKEN))
    c = MCPHISClient(CONN, client_factory=factory)
    assert c.kind == "mcp" and c.label == "Demo HIS"
    assert run(c.ping())["ok"] is True
    p = run(c.find_patient("SYN-900001"))
    assert p["id"] == "SYN-900001" and p["sex"] == "M" and p["age"] == 60 and p["matched_on"]["kind"] == "uhid"
    assert run(c.find_patient("Test Patient")) is None          # exact identifiers only, no name search
    reps = run(c.reports("SYN-900001"))
    assert {r["doc_type"] for r in reps} == {"mri", "lab"} and all(r["kind"] == "note" and r["version"] == 1 for r in reps)
    mri = next(r for r in reps if r["doc_type"] == "mri")
    d = run(c.document(mri["document_ref"]))
    assert b"MRI BRAIN REPORT" in d["content"] and d["sha256"] == hashlib.sha256(d["content"]).hexdigest()
    assert d["filename"] == "mri_brain_2026_09_14.txt"
    assert len(run(c.reports("SYN-900001", since="2026-10-01"))) == len(run(c.reports("SYN-900001")))  # no change feed on the MCP transport: `since` is ignored, the Case File de-duplicates (review)
    assert run(c.encounters("SYN-900001")) == [] and run(c.open_orders("SYN-900001")) == [] and run(c.referrals("SYN-900001")) == []
    assert run(c.imaging_study("x")) is None and run(c.hospital()) == {"name": "Demo HIS", "departments": []}
    with pytest.raises(HISError):
        run(c.document("DocumentReference/doc-1"))
    bad = MCPHISClient({**CONN, "token": "wrong"}, client_factory=lambda: _client_for(
        demo_his_mcp.http_app(demo_his_mcp.build(**INPROC), expected=MCP_TOKEN), "wrong"))
    with pytest.raises(HISError, match="MCP connector"):
        run(bad.find_patient("SYN-900001"))
    # settings: kind mcp resolves the saved connector
    connectors.save([CONN], by="admin")
    his_client.save_settings({"kind": "mcp", "connector": "demo_his", "label": "Demo HIS"}, by="root")
    assert isinstance(his_client.client(), MCPHISClient)


# ------------------------------------------------------------------------------------------------ live mock (optional)
def _mock_up() -> bool:
    try:
        return httpx.get(BASE + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _mock_up(), reason="the mock hospital is not running on 127.0.0.1:7130")
def test_live_mock_full_reports_and_a_document_under_30_seconds(monkeypatch):
    for k in ("TB_HIS_URL", "TB_HIS_TOKEN", "TB_HIS_TOKEN_FILE"):
        monkeypatch.delenv(k, raising=False)
    c = his_client.client()
    t0 = time.monotonic()

    async def go():
        p = await c.find_patient("VXH/26/004201")
        reps = await c.reports(p["id"])
        doc = await c.document(reps[-1]["document_ref"])
        return p, reps, doc
    p, reps, doc = run(go())
    assert time.monotonic() - t0 < 30
    assert p["id"] == "vxh-26-004201" and len(reps) >= 8
    assert doc["content"].startswith(b"%PDF") and doc["sha256"] == reps[-1]["document"]["sha256"]
