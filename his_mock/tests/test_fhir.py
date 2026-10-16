"""The mock hospital's FHIR R4 API (plan item V2-1.3): NRCeS v6.5.0 shapes, search, history, $document, $everything,
$similar. SYNTHETIC data only; builds into a temporary directory (report PDFs included, ~15 s once per session)."""
import base64
import copy
import hashlib
import shutil
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import fhir, generator, hl7, ids, paths
from his_mock.model import Store

NRCES = "https://nrces.in/ndhm/fhir/r4/StructureDefinition/"
P01, P03, P09, P09_TEMP, P17, P17_DUP = ("vxh-26-004201", "vxh-26-004203", "vxh-26-004209", "vxh-t-26-00412",
                                         "vxh-26-004217", "vxh-26-004317")
SUNITAS = ("vxh-26-004204", "vxh-26-004210")
AMENDED, PRELIM, UNSIGNED_FINAL, TAMPERED, OPD_NOTE, OBS_DISAGREES, CBC = (
    "p02-r05", "p12-r02", "p11-r02", "p03-r10", "p12-r14", "p15-r03", "p13-r03")

_PRISTINE = {}


def full_build(tmp_path_factory):
    """A fresh copy of one full build (PDFs, HL7, DICOM metadata) per caller; the build itself runs once per session."""
    if "dir" not in _PRISTINE:
        d = tmp_path_factory.mktemp("his_fhir_pristine")
        generator.build(d, documents=True, hl7=True, dicom=True)
        _PRISTINE["dir"] = d
    out = tmp_path_factory.mktemp("his_fhir")
    shutil.copytree(_PRISTINE["dir"], out, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.dcm"))
    return out


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    return full_build(tmp_path_factory)


@pytest.fixture(scope="module")
def client(data_dir):
    return TestClient(app_module.create_app(data_dir))


@pytest.fixture(scope="module")
def auth(data_dir):
    return {"Authorization": "Bearer " + (Path(data_dir) / paths.TOKEN_NAME).read_text().strip()}


@pytest.fixture(scope="module")
def store(client):
    return client.app.state.hospital.store


def get(client, auth, url, status=200):
    r = client.get(url, headers=auth)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    return r.json()


def resources(bundle, rtype=None):
    return [e["resource"] for e in bundle.get("entry") or [] if not rtype or e["resource"]["resourceType"] == rtype]


def ident(res, system_key):
    return next((i["value"] for i in res.get("identifier") or [] if i["system"] == fhir.SYS[system_key]), None)


# ------------------------------------------------------------------ metadata and auth
def test_router_is_mounted():
    assert ("fhir", "/fhir") in app_module.mounted()


def test_metadata_without_token(client):
    r = client.get("/fhir/metadata")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/fhir+json")
    cs = r.json()
    assert cs["resourceType"] == "CapabilityStatement" and cs["status"] == "active" and cs["kind"] == "instance"
    assert cs["fhirVersion"] == "4.0.1" and cs["format"] == ["json"]
    assert cs["software"]["name"] == app_module.NAME and "SYNTHETIC" in cs["implementation"]["description"]
    types = {x["type"]: x for x in cs["rest"][0]["resource"]}
    for t in ("Patient", "Encounter", "ServiceRequest", "Specimen", "DiagnosticReport", "Observation",
              "DocumentReference", "Provenance", "ImagingStudy", "Practitioner", "Organization"):
        assert t in types and types[t]["searchParam"], t
    assert {p["name"] for p in types["DiagnosticReport"]["searchParam"]} >= {"patient", "encounter", "identifier",
                                                                               "status", "_lastUpdated", "category"}
    assert "supportedProfile" not in types["Provenance"]


def test_search_needs_the_token(client, auth):
    assert client.get("/fhir/Patient").status_code == 401
    assert client.get("/fhir/Patient", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/fhir/Patient/" + P01).status_code == 401
    assert client.get(f"/fhir/DiagnosticReport/{AMENDED}/$document").status_code == 401
    assert client.get("/fhir/Patient", headers=auth).status_code == 200


def test_read_only(client, auth):
    for method in ("post", "put", "delete"):
        assert getattr(client, method)("/fhir/Patient/" + P01, headers=auth).status_code == 405


def test_404_is_an_operation_outcome(client, auth):
    for url in ("/fhir/Patient/nope", f"/fhir/DiagnosticReport/{OPD_NOTE}", "/fhir/DiagnosticReport/nope/_history",
                f"/fhir/DiagnosticReport/{AMENDED}/_history/9", "/fhir/DocumentReference/doc-nope-v1/$document",
                "/fhir/Patient/nope/$everything", "/fhir/Basic/x"):
        r = client.get(url, headers=auth)
        assert r.status_code == 404, url
        assert r.json()["resourceType"] == "OperationOutcome" and r.json()["issue"][0]["severity"] == "error"


def test_unsupported_search_parameter_is_400(client, auth):
    r = client.get("/fhir/Patient?favourite_colour=blue", headers=auth)
    assert r.status_code == 400 and r.json()["resourceType"] == "OperationOutcome"
    assert client.get("/fhir/Patient?_count=-1", headers=auth).status_code == 400
    assert client.get("/fhir/DiagnosticReport?_sort=status", headers=auth).status_code == 400


# ------------------------------------------------------------------ Patient and identity
def test_patient_by_uhid(client, auth, store):
    p = store.patients[P01]
    b = get(client, auth, f"/fhir/Patient?identifier={fhir.SYS['uhid']}|{p['uhid']}")
    assert b["type"] == "searchset" and b["total"] == 1 and b["link"][0]["relation"] == "self"
    res = resources(b)[0]
    assert b["entry"][0]["fullUrl"].endswith(f"/fhir/Patient/{P01}")
    assert res["meta"]["profile"] == [NRCES + "Patient"] and "SYNTHETIC" in res["name"][0]["text"]
    mr = res["identifier"][0]
    assert mr["type"]["coding"][0]["code"] == "MR" and mr["use"] == "official" and mr["value"] == p["uhid"]
    assert ident(res, "pmjay") == p["pmjay_id"]
    # the bare value works too
    assert [x["id"] for x in resources(get(client, auth, f"/fhir/Patient?identifier={p['uhid']}"))] == [P01]


def test_patient_by_temporary_uhid(client, auth, store):
    t = store.patients[P09_TEMP]
    res = resources(get(client, auth, f"/fhir/Patient?identifier={t['uhid']}"))
    assert [x["id"] for x in res] == [P09_TEMP]
    assert res[0]["identifier"][0]["use"] == "temp"
    assert ident(res[0], "abha") is None


def test_patient_by_abha_number_and_address(client, auth, store):
    p = store.patients[P01]
    for system, value in ((fhir.SYS["abha"], p["abha"]["number"]), (fhir.SYS["abha_address"], p["abha"]["address"])):
        res = resources(get(client, auth, f"/fhir/Patient?identifier={system}|{value}"))
        assert [x["id"] for x in res] == [P01]
    abha = next(i for i in res[0]["identifier"] if i["system"] == fhir.SYS["abha"])
    assert abha["type"]["coding"][0] == {"system": fhir.NDHM_ID_TYPE, "code": "ABHA",
                                         "display": "Ayushman Bharat Health Account (ABHA) ID"}
    assert len(abha["value"].replace("-", "")) == 14
    assert p["abha"]["address"].endswith("@sbx")


def test_op_and_ip_numbers_lead_to_the_patient(client, auth, store):
    for eid in ("op-26-118701", "ip-26-01871"):
        e = store.encounters[eid]
        res = resources(get(client, auth, f"/fhir/Encounter?identifier={e['number']}"))
        assert [x["id"] for x in res] == [eid]
        assert res[0]["subject"]["reference"] == f"Patient/{P01}"
        assert res[0]["identifier"][0]["type"]["coding"][0]["code"] == "VN"
    assert resources(get(client, auth, "/fhir/Encounter?identifier=OP/99/999999")) == []


def test_similar_lists_temporary_and_duplicate_not_namesakes(client, auth):
    assert [x["id"] for x in resources(get(client, auth, f"/fhir/Patient/{P09}/$similar"))] == [P09_TEMP]
    assert [x["id"] for x in resources(get(client, auth, f"/fhir/Patient/{P09_TEMP}/$similar"))] == [P09]
    dup = resources(get(client, auth, f"/fhir/Patient/{P17}/$similar"))
    assert [x["id"] for x in dup] == [P17_DUP] and dup[0]["identifier"][0]["use"] == "official"
    for s in SUNITAS:
        assert resources(get(client, auth, f"/fhir/Patient/{s}/$similar")) == []
    names = resources(get(client, auth, "/fhir/Patient?name=Sunita Devi"))
    assert sorted(x["id"] for x in names) == sorted(SUNITAS)


def test_no_aadhaar_in_patients(client, auth):
    from his_mock.scenarios import AADHAAR_LIKE
    b = get(client, auth, "/fhir/Patient")
    assert b["total"] == 21
    for p in resources(b):
        codes = {c["code"] for i in p["identifier"] for c in i["type"]["coding"]}
        assert "ADN" not in codes and not AADHAAR_LIKE.search(str(p))


# ------------------------------------------------------------------ Encounter
def test_encounters_of_a_patient_with_class_and_location_history(client, auth, store):
    res = resources(get(client, auth, f"/fhir/Encounter?patient=Patient/{P03}"))
    assert {x["id"] for x in res} == {e["id"] for e in store.encounters_for(P03)}
    assert {x["class"]["code"] for x in res} == {"AMB", "IMP"}
    ip = next(x for x in res if x["id"] == "ip-26-01872")
    assert ip["meta"]["profile"] == [NRCES + "Encounter"] and ip["status"] == "finished"
    locs = ip["location"]
    assert [x["location"]["display"] for x in locs] == ["Surgical Ward 2, bed 2-14", "High Dependency Unit, bed HDU-04",
                                                        "Surgical Ward 2, bed 2-09"]
    assert all(x["status"] == "completed" for x in locs)       # discharged
    assert locs[0]["period"]["end"] == locs[1]["period"]["start"]
    assert ip["serviceProvider"]["reference"].startswith("Organization/dept-")
    assert ip["participant"][0]["individual"]["reference"].startswith("Practitioner/prac-vxreg-")
    # the current admission's bed is active; PM-JAY pre-authorisation as an extension
    cur = get(client, auth, "/fhir/Encounter/ip-26-01879")
    assert cur["status"] == "in-progress" and cur["location"][-1]["status"] == "active"
    pre = cur["extension"][0]
    assert pre["url"] == fhir.EXT["pmjay_preauth"]
    assert {x["url"]: x for x in pre["extension"]}["status"]["valueCodeableConcept"]["text"] == "approved"
    assert {x["id"] for x in resources(get(client, auth, f"/fhir/Encounter?patient={P03}&class=IMP"))} == {"ip-26-01872"}


def test_referral_service_request(client, auth):
    res = resources(get(client, auth, "/fhir/ServiceRequest?encounter=ip-26-01877&category=3457005"))
    assert len(res) == 1
    ref = res[0]
    assert ref["id"] == "ref-ip-26-01877-1" and ref["status"] == "completed" and ref["intent"] == "order"
    assert ref["category"][0]["coding"][0]["code"] == "3457005"
    assert ref["requester"]["display"] == "Pulmonology" and ref["performer"][0]["display"] == "Colorectal Surgery"
    assert ref["reasonCode"][0]["text"].startswith("Lung biopsy reported as metastatic adenocarcinoma")
    assert get(client, auth, "/fhir/ServiceRequest/ref-ip-26-01877-1") == ref


# ------------------------------------------------------------------ orders, specimens
def test_service_request_and_specimen(client, auth, store):
    o = store.orders["path-26-00426"]
    sr = get(client, auth, "/fhir/ServiceRequest/path-26-00426")
    assert sr["identifier"][0]["value"] == o["accession"] and sr["identifier"][0]["type"]["coding"][0]["code"] == "ACSN"
    assert sr["status"] == "completed" and sr["requester"]["reference"].startswith("Organization/")
    sp = get(client, auth, f"/fhir/Specimen/{o['specimen_id']}")
    assert sp["accessionIdentifier"]["value"] == store.specimens[o["specimen_id"]]["barcode"]
    assert sp["identifier"][0]["value"] == "PATH/26/00426-A1"
    assert sp["type"]["coding"][0]["code"] == "119376003" and sp["request"][0]["reference"] == "ServiceRequest/path-26-00426"
    statuses = {o["id"]: o["status"] for o in store.orders.values()}
    for oid, want in (("mic-26-00611", "active"), ("nm-26-00152", "active"), ("rad-26-01000", "revoked"),
                      ("path-26-00451", "active")):
        assert statuses[oid] in ("ordered", "scheduled", "cancelled", "sample_collected")
        assert get(client, auth, f"/fhir/ServiceRequest/{oid}")["status"] == want
    by_acc = resources(get(client, auth, f"/fhir/ServiceRequest?identifier={o['accession']}"))
    assert [x["id"] for x in by_acc] == ["path-26-00426"]


# ------------------------------------------------------------------ DiagnosticReport
def test_diagnostic_reports_of_a_patient_are_current_versions(client, auth, store):
    pid = store.reports[AMENDED]["patient_id"]
    res = resources(get(client, auth, f"/fhir/DiagnosticReport?patient={pid}"))
    want = {r["id"] for r in store.reports.values() if r["patient_id"] == pid and fhir.is_diagnostic(r)}
    assert {x["id"] for x in res} == want and len(res) == len(want)
    amended = next(x for x in res if x["id"] == AMENDED)
    assert amended["status"] == "amended" and amended["meta"]["versionId"] == "2"
    assert amended["meta"]["profile"] == [NRCES + "DiagnosticReportLab"]
    assert amended["code"]["coding"][0]["system"] == "http://loinc.org"
    assert amended["presentedForm"][0]["contentType"] == "application/pdf"
    assert base64.b64decode(amended["presentedForm"][0]["data"]).startswith(b"%PDF")
    # notes are DocumentReferences only
    assert not any(store.reports[x["id"]]["doc_type"] in fhir.NOTE_DOC_TYPES for x in res)
    assert {x["id"] for x in resources(get(client, auth, f"/fhir/DiagnosticReport?patient={pid}&status=amended"))} == {AMENDED}


def test_history_of_the_amended_report(client, auth):
    h = get(client, auth, f"/fhir/DiagnosticReport/{AMENDED}/_history")
    assert h["type"] == "history" and h["total"] == 2
    vs = resources(h)
    assert [v["meta"]["versionId"] for v in vs] == ["2", "1"]
    assert [v["status"] for v in vs] == ["amended", "final"]
    v1 = get(client, auth, f"/fhir/DiagnosticReport/{AMENDED}/_history/1")
    assert v1["meta"]["versionId"] == "1" and v1 == vs[1]
    her2 = {v["meta"]["versionId"]: get(client, auth, next(r["reference"] for r in v["result"] if r["reference"].endswith("her2"))
                                        .replace("Observation/", "/fhir/Observation/"))["valueString"] for v in vs}
    assert her2 == {"2": "3+ (Positive)", "1": "2+ (Equivocal)"}
    assert get(client, auth, f"/fhir/DiagnosticReport/{AMENDED}") == vs[0]


def test_observations_of_a_cbc_carry_the_printed_values(client, auth, store):
    obs = resources(get(client, auth, f"/fhir/Observation?encounter={store.reports[CBC]['encounter_id']}"))
    mine = {o["id"]: o for o in obs if o["id"].startswith(f"obs-{CBC}-")}
    hb = mine[f"obs-{CBC}-v1-haemoglobin"]
    assert hb["valueQuantity"] == {"value": 12.4, "unit": "gm%"}
    assert hb["code"]["coding"][0] == {"system": "http://loinc.org", "code": "718-7",
                                       "display": "Hemoglobin [Mass/volume] in Blood"}
    assert hb["status"] == "final" and hb["meta"]["profile"] == [NRCES + "Observation"]
    assert mine[f"obs-{CBC}-v1-platelets"]["valueQuantity"] == {"value": 2.6, "unit": "lakhs/cumm"}
    dr = get(client, auth, f"/fhir/DiagnosticReport/{CBC}")
    assert sorted(r["reference"] for r in dr["result"]) == sorted("Observation/" + i for i in mine)
    # a value with no certain code: code.text only, the printed string as valueString
    mol = resources(get(client, auth, f"/fhir/Observation?patient={store.reports['p13-r07']['patient_id']}"))
    egfr = next(o for o in mol if o["id"] == "obs-p13-r07-v1-egfr")
    assert "coding" not in egfr["code"] and egfr["code"]["text"] == "EGFR mutation analysis"
    assert egfr["valueString"] == "Exon 19 deletion detected"
    # UCUM only where certain
    cr = get(client, auth, "/fhir/Observation/obs-p13-r05-v1-creatinine")
    assert cr["valueQuantity"] == {"value": 0.8, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"}


def test_omitted_value_has_no_observation(client, auth, store):
    r = store.reports["p03-r05"]
    assert r["omitted_values"] == ["her2"]
    dr = get(client, auth, "/fhir/DiagnosticReport/p03-r05")
    assert not any(x["reference"].endswith("her2") for x in dr["result"])
    assert client.get("/fhir/Observation/obs-p03-r05-v1-her2", headers=auth).status_code == 404


def test_observation_values_disagree_with_the_pdf(client, auth, store, data_dir):
    from his_mock import documents
    r = store.reports[OBS_DISAGREES]
    v = store.current_version(r)
    hb = get(client, auth, f"/fhir/Observation/obs-{OBS_DISAGREES}-v1-haemoglobin")
    assert r["observation_values"]["haemoglobin"] == "11.2 gm%" and v["values"]["haemoglobin"] == "12.1 gm%"
    assert hb["valueQuantity"] == {"value": 11.2, "unit": "gm%"}
    text = documents.norm(documents.text_of(Path(data_dir) / v["document"]["path"]))
    assert "12.1" in text and "11.2" not in text
    assert get(client, auth, f"/fhir/Observation/obs-{OBS_DISAGREES}-v1-wbc")["valueQuantity"] == {"value": 6900,
                                                                                                    "unit": "/cumm"}


# ------------------------------------------------------------------ DocumentReference and Provenance
def test_document_reference_carries_the_pdf(client, auth, store):
    r = store.reports[AMENDED]
    docs = resources(get(client, auth, f"/fhir/DocumentReference?patient={r['patient_id']}"))
    mine = {d["id"]: d for d in docs if d["id"].startswith(f"doc-{AMENDED}-")}
    assert set(mine) == {f"doc-{AMENDED}-v1", f"doc-{AMENDED}-v2"}
    cur, old = mine[f"doc-{AMENDED}-v2"], mine[f"doc-{AMENDED}-v1"]
    assert (cur["status"], cur["docStatus"]) == ("current", "amended") and (old["status"], old["docStatus"]) == (
        "superseded", "final")
    att = cur["content"][0]["attachment"]
    data = base64.b64decode(att["data"])
    assert data.startswith(b"%PDF") and att["contentType"] == "application/pdf"
    assert base64.b64decode(att["hash"]) == hashlib.sha1(data).digest()
    assert cur["extension"][0]["valueString"] == hashlib.sha256(data).hexdigest() == r["versions"][1]["document"]["sha256"]
    served = client.get(att["url"], headers=auth)
    assert served.status_code == 200 and served.content == data
    assert cur["authenticator"]["reference"].startswith("Practitioner/")
    current_only = resources(get(client, auth, f"/fhir/DocumentReference?patient={r['patient_id']}&status=current"))
    assert {d["id"] for d in current_only if d["id"].startswith(f"doc-{AMENDED}-")} == {f"doc-{AMENDED}-v2"}


def test_provenance_of_signed_reports(client, auth, store):
    r = store.reports[AMENDED]
    sig = store.signatures[r["versions"][1]["signature_id"]]
    prov = get(client, auth, f"/fhir/Provenance/{sig['id']}")
    assert "profile" not in prov["meta"]
    assert prov["target"][0]["reference"] == f"DiagnosticReport/{AMENDED}/_history/2"
    s = prov["signature"][0]
    assert base64.b64decode(s["data"]).decode() == sig["block"] and "Vaidyx Demo CA" in sig["block"]
    assert s["type"][0]["code"] == "1.2.840.10065.1.12.1.1" and s["who"]["reference"] == f"Practitioner/{sig['signer_id']}"
    ext = {e["url"]: e for e in prov["extension"]}
    assert ext[fhir.EXT["signature_ca"]]["valueString"] == "Vaidyx Demo CA"
    assert ext[fhir.EXT["signature_serial"]]["valueString"] == sig["certificate_serial"]
    assert ext[fhir.EXT["signature_hash"]]["valueString"] == sig["document_hash"]
    assert ext[fhir.EXT["signature_status"]]["valueCode"] == "verified"
    by_patient = resources(get(client, auth, f"/fhir/Provenance?patient={r['patient_id']}"))
    assert sig["id"] in {p["id"] for p in by_patient}
    by_target = resources(get(client, auth, f"/fhir/Provenance?target=DiagnosticReport/{AMENDED}"))
    assert sorted(p["id"] for p in by_target) == [f"sig-{AMENDED}-v1", f"sig-{AMENDED}-v2"]


def test_tampered_signature_says_failed(client, auth):
    prov = get(client, auth, f"/fhir/Provenance/sig-{TAMPERED}-v1")
    ext = {e["url"]: e for e in prov["extension"]}
    assert ext[fhir.EXT["signature_status"]]["valueCode"] == "failed"
    assert prov["target"] == [{"reference": f"DocumentReference/doc-{TAMPERED}-v1"}]   # a discharge summary: no DR


def test_unsigned_versions_have_no_provenance(client, auth, store):
    for rid in (PRELIM, UNSIGNED_FINAL):
        r = store.reports[rid]
        assert not store.current_version(r)["signature_id"]
        assert client.get(f"/fhir/Provenance/sig-{rid}-v1", headers=auth).status_code == 404
        assert resources(get(client, auth, f"/fhir/Provenance?target=DiagnosticReport/{rid}")) == []
        doc = get(client, auth, f"/fhir/DocumentReference/doc-{rid}-v1")
        assert "authenticator" not in doc
    assert get(client, auth, f"/fhir/DiagnosticReport/{PRELIM}")["status"] == "preliminary"
    assert get(client, auth, f"/fhir/DiagnosticReport/{UNSIGNED_FINAL}")["status"] == "final"


def test_cancelled_report_is_cancelled_and_entered_in_error(store):
    s = Store(copy.deepcopy(store.data))
    r = s.reports[PRELIM]
    s.cancel_order(r["order_id"], "Patient unfit (SYNTHETIC test)", when="2026-10-13T12:00:00+05:30")
    assert fhir.diagnostic_report(s, r)["status"] == "cancelled"
    assert {o["status"] for o in fhir.observations(s, r)} == {"cancelled"}
    doc = fhir.document_reference(s, r)
    assert doc["docStatus"] == "entered-in-error" and doc["status"] == "entered-in-error"
    assert r["current_version"] == 2 and r["versions"][0]["status"] == "preliminary"   # history kept on cancel
    assert fhir.diagnostic_report(s, r)["meta"]["versionId"] == "2"
    assert fhir.composition(s, r)["status"] == "entered-in-error"
    assert fhir.service_request(s, s.orders[r["order_id"]])["status"] == "revoked"


# ------------------------------------------------------------------ imaging
def test_imaging_study_and_report_links(client, auth, store):
    study = next(x for x in store.imaging_studies.values() if fhir.has_images(x) and store.report_for_order(x["order_id"]))
    r = store.report_for_order(study["order_id"])
    res = resources(get(client, auth, f"/fhir/ImagingStudy?identifier={study['accession']}"))
    assert [x["id"] for x in res] == [study["id"]]
    im = res[0]
    assert im["meta"]["profile"] == [NRCES + "ImagingStudy"] and im["status"] == "registered"  # built, not uploaded
    assert {"system": "urn:dicom:uid", "value": "urn:oid:" + study["study_uid"]} in im["identifier"]
    assert im["numberOfSeries"] == study["number_of_series"] and im["series"][0]["uid"] == study["series"][0]["uid"]
    assert im["series"][0]["instance"][0]["sopClass"]["code"] == "urn:oid:" + study["series"][0]["instances"][0]["sop_class"]
    ext = {e["url"]: e["valueUrl"] for e in im["extension"]}
    assert fhir.EXT["viewer_url"] not in ext      # the viewer link appears once the study is in the PACS
    assert ext[fhir.EXT["dicomweb_url"]] == "/dicom-web/studies/" + study["study_uid"]
    study["status"], study["uploaded"] = "available", True   # as upload_all marks it
    im2 = fhir.imaging_study(store, study)
    assert {e["url"]: e["valueUrl"] for e in im2["extension"]}[fhir.EXT["viewer_url"]].endswith(
        "StudyInstanceUIDs=" + study["study_uid"])
    study["status"], study["uploaded"] = "registered", False
    dr = get(client, auth, f"/fhir/DiagnosticReport/{r['id']}")
    assert dr["meta"]["profile"] == [NRCES + "DiagnosticReportImaging"]
    assert dr["imagingStudy"] == [{"reference": f"ImagingStudy/{study['id']}"}]
    media = get(client, auth, "/fhir/" + dr["media"][0]["link"]["reference"])
    assert media["resourceType"] == "Media" and media["content"]["url"] == "/dicom-web/studies/" + study["study_uid"]
    assert "profile" not in media["meta"]
    by_uid = resources(get(client, auth, f"/fhir/ImagingStudy?identifier=urn:dicom:uid|urn:oid:{study['study_uid']}"))
    assert [x["id"] for x in by_uid] == [study["id"]]
    reg = get(client, auth, "/fhir/ImagingStudy/img-nm-26-00152")
    assert reg["status"] == "registered" and "extension" not in reg


# ------------------------------------------------------------------ $document
def _check_document(b):
    assert b["resourceType"] == "Bundle" and b["type"] == "document"
    assert b["meta"]["profile"] == [NRCES + "DocumentBundle"] and b["meta"]["versionId"]
    assert b["identifier"]["system"] and b["identifier"]["value"] and b["timestamp"]
    comp = b["entry"][0]["resource"]
    assert comp["resourceType"] == "Composition" and comp["meta"]["profile"] == [NRCES + "DiagnosticReportRecord"]
    assert comp["type"]["coding"][0] == {"system": "http://snomed.info/sct", "code": "721981007",
                                         "display": "Diagnostic studies report"}
    have = {(e["resource"]["resourceType"], e["resource"]["id"]) for e in b["entry"]}
    assert all(e["fullUrl"] == f"https://his.vaidyx-demo.invalid/fhir/{e['resource']['resourceType']}/{e['resource']['id']}"
               for e in b["entry"])
    for e in b["entry"]:
        for s in fhir.references(e["resource"]):
            p = fhir.parse_reference(s)
            assert p and (p[0], p[1]) in have, s
    return comp


def test_document_bundle_of_a_lab_report(client, auth, store):
    b = get(client, auth, f"/fhir/DiagnosticReport/{CBC}/$document")
    comp = _check_document(b)
    assert [e["reference"] for e in comp["section"][0]["entry"]] == [f"DiagnosticReport/{CBC}",
                                                                     f"DocumentReference/doc-{CBC}-v1"]
    assert comp["section"][0]["code"]["coding"][0]["code"] == "4321000179101"
    assert comp["attester"][0]["mode"] == "legal" and comp["custodian"]["reference"] == "Organization/org-vaidyx-demo-hospital"
    types = [e["resource"]["resourceType"] for e in b["entry"]]
    assert types[:2] == ["Composition", "Patient"] and types[-1] == "Encounter"
    for t in ("Practitioner", "Organization", "DiagnosticReport", "Observation", "Specimen", "ServiceRequest",
              "DocumentReference", "Provenance"):
        assert t in types, t
    assert types.index("DiagnosticReport") < types.index("Observation") < types.index("DocumentReference")


def test_document_bundle_of_an_older_version(client, auth):
    b = get(client, auth, f"/fhir/DocumentReference/doc-{AMENDED}-v1/$document")
    _check_document(b)
    assert b["meta"]["versionId"] == "1"
    dr = next(x for x in resources(b, "DiagnosticReport"))
    assert dr["meta"]["versionId"] == "1" and dr["status"] == "final"
    doc = resources(b, "DocumentReference")[0]
    assert doc["status"] == "superseded"
    b2 = get(client, auth, f"/fhir/DiagnosticReport/{AMENDED}/$document")
    assert b2["meta"]["versionId"] == "2" and b2["identifier"]["value"] != b["identifier"]["value"]


def test_document_bundle_of_an_opd_note(client, auth, store):
    b = get(client, auth, f"/fhir/DocumentReference/doc-{OPD_NOTE}-v1/$document")
    comp = _check_document(b)
    assert [e["reference"] for e in comp["section"][0]["entry"]] == [f"DocumentReference/doc-{OPD_NOTE}-v1"]
    assert resources(b, "DiagnosticReport") == [] and resources(b, "Observation") == []
    doc = resources(b, "DocumentReference")[0]
    assert doc["type"]["coding"][0]["code"] == "11488-4"


def test_everything_of_p01_lists_every_type(client, auth, store):
    b = get(client, auth, f"/fhir/Patient/{P01}/$everything")
    types = {e["resource"]["resourceType"] for e in b["entry"]}
    assert types >= {"Patient", "Encounter", "ServiceRequest", "Specimen", "DiagnosticReport", "Observation",
                     "DocumentReference", "Provenance", "ImagingStudy", "Media", "Practitioner", "Organization"}
    pats = resources(b, "Patient")
    assert [p["id"] for p in pats] == [P01]
    assert {r["id"] for r in resources(b, "DiagnosticReport")} == {
        r["id"] for r in store.reports.values() if r["patient_id"] == P01 and fhir.is_diagnostic(r)}
    assert b["total"] == len(b["entry"])


def test_paging(client, auth):
    b = get(client, auth, "/fhir/Observation?_count=5")
    assert len(b["entry"]) == 5 and b["total"] > 5
    nxt = next(l["url"] for l in b["link"] if l["relation"] == "next")
    assert "_offset=5" in nxt and "token" not in nxt
    b2 = get(client, auth, "/fhir/Observation?_count=5&_offset=5")
    assert {e["resource"]["id"] for e in b2["entry"]}.isdisjoint({e["resource"]["id"] for e in b["entry"]})
    assert client.get(f"/fhir/Patient?_count=1&token={auth['Authorization'][7:]}").status_code == 401  # header only
    q = client.get("/fhir/Patient?_count=1&token=x", headers=auth)
    assert q.status_code == 200 and "token=" not in q.json()["link"][0]["url"]


def test_thirty_records_fetch_quickly(client, auth, store):
    busiest = sorted({r["patient_id"] for r in store.reports.values()},
                     key=lambda p: -sum(1 for r in store.reports.values() if r["patient_id"] == p))[:3]
    t0 = time.time()
    n = 0
    for pid in busiest:
        docs = resources(get(client, auth, f"/fhir/DocumentReference?patient={pid}&status=current"))
        get(client, auth, f"/fhir/DiagnosticReport?patient={pid}")
        for d in docs:
            if n >= 30:
                break
            b = get(client, auth, f"/fhir/DocumentReference/{d['id']}/$document")
            assert b["entry"][0]["resource"]["resourceType"] == "Composition"
            n += 1
    assert n == 30 and time.time() - t0 < 5.0


# ------------------------------------------------------------------ deltas (last: changes the store)
def test_last_updated_delta_after_signing(client, auth, store):
    hospital = client.app.state.hospital
    mark = hl7.last_event_time(store)
    q = "/fhir/DiagnosticReport?_lastUpdated=gt" + mark.replace("+", "%2B")
    assert get(client, auth, q)["total"] == 0
    # an unencoded '+' (a space after URL decoding) is read as the offset too
    assert get(client, auth, "/fhir/DiagnosticReport?_lastUpdated=gt" + mark)["total"] == 0
    r = store.reports[PRELIM]
    dept = store.department(store.orders[r["order_id"]]["performing_department"])
    signer = next(p for p in dept["consultants"] if store.practitioners[p]["role"] == "consultant")
    later = ids.iso(ids.parse_time(mark).replace(microsecond=0) + timedelta(hours=1))
    with hospital.lock:
        store.sign_final(r["id"], signer, when=later)
        hospital.save()
    res = resources(get(client, auth, q))
    assert [x["id"] for x in res] == [PRELIM]
    assert res[0]["status"] == "final" and res[0]["meta"]["versionId"] == "2"
    assert [x["id"] for x in resources(get(client, auth, q + "&patient=" + r["patient_id"]))] == [PRELIM]
    assert get(client, auth, q + "&patient=" + P01)["total"] == 0
    assert resources(get(client, auth, f"/fhir/Provenance?target=DiagnosticReport/{PRELIM}"))[0]["id"] == f"sig-{PRELIM}-v2"
    docs = resources(get(client, auth, "/fhir/DocumentReference?_lastUpdated=gt" + mark.replace("+", "%2B")))
    assert {d["id"] for d in docs} == {f"doc-{PRELIM}-v1", f"doc-{PRELIM}-v2"}
    assert {d["id"]: d["status"] for d in docs} == {f"doc-{PRELIM}-v1": "superseded", f"doc-{PRELIM}-v2": "current"}
    ordered = resources(get(client, auth, "/fhir/DiagnosticReport?_sort=-_lastUpdated&_count=1"))
    assert ordered[0]["id"] == PRELIM
