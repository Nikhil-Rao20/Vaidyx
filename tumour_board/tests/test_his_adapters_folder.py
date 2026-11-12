"""The two file hand-over adapters: a report folder with index.csv (his_adapters.folder_bridge) and ABDM document bundles
(his_adapters.abdm_bundle): identity (UHID, visit number, ABHA), status mapping, versions, bad rows and bad bundles skipped with a
counted reason, path safety, and the happy path through his_case. SYNTHETIC data only, temporary folders, no network."""
import asyncio
import base64
import hashlib
import json

import pytest

from tumour_board import his_case, his_client, store
from tumour_board.his_adapters import _common, abdm_bundle
from tumour_board.his_adapters.abdm_bundle import ABDMBundleClient
from tumour_board.his_adapters.folder_bridge import FolderBridgeClient
from tumour_board.tests.test_his_case import ROLES_DOC, fakes  # noqa: F401
from tumour_board.tests.test_his_adapters_hl7v2 import NAME, PDF, PDF2, UHID

HEAD = "uhid,patient_name,sex,dob,age,visit_no,visit_type,report_id,report_type,report_date,status,signed_by,file\n"
CT = PDF.replace(b"HISTOPATHOLOGY REPORT", b"CECT THORAX ABDOMEN PELVIS").replace(b"Report status: FINAL", b"Report status: PRELIMINARY")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def folder(data_root, monkeypatch):
    monkeypatch.delenv("TB_HIS_FOLDER_ROOTS", raising=False)
    _common._CACHE.clear()
    d = data_root / "his_inbox" / "reports"
    (d / "2026").mkdir(parents=True)
    (d / "hpe_v1.pdf").write_bytes(PDF)
    (d / "hpe_v2.pdf").write_bytes(PDF2)
    (d / "2026" / "ct.pdf").write_bytes(CT)
    return d


def index(folder, rows):
    (folder / "index.csv").write_bytes(b"\xef\xbb\xbf" + (HEAD + "".join(r + "\n" for r in rows)).encode())


GOOD = [f'{UHID},"{NAME}",F,18/01/1980,,OP/26/118701,OP,PATH/26/00411,Histopathology report,05/09/2026,Provisional,Dr Revathi Krishnan,hpe_v1.pdf',
        f'{UHID},"{NAME}",F,1980-01-18,,OP/26/118701,OP,PATH/26/00411,Histopathology report,2026-09-07,Corrected,Dr Revathi Krishnan,hpe_v2.pdf',
        f'{UHID},"{NAME}",F,,46,IP/26/01871,IP,RAD/26/00981,CECT thorax abdomen pelvis,02/09/2026,final,,2026/ct.pdf']


# ---- folder_bridge ------------------------------------------------------------------------------------------------------------
def test_index_rows_become_patients_visits_and_report_versions(folder):
    index(folder, GOOD)
    c = FolderBridgeClient(str(folder), label="Small Hospital (SYNTHETIC)")
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"] == {"rows": 3, "patients": 1, "reports": 3, "skipped": {}}
    p = run(c.find_patient(UHID.lower()))
    assert p["uhid"] == UHID and p["name"] == NAME and p["sex"] == "F" and p["matched_on"]["kind"] == "uhid" and p["similar"] == []
    assert run(c.find_patient("IP/26/01871"))["matched_on"] == {"kind": "ip_no", "value": "IP/26/01871"} and run(c.find_patient("nobody")) is None
    assert [(e["kind"], e["number"], e["start"]) for e in run(c.encounters(UHID))] == [("IP", "IP/26/01871", "2026-09-02"), ("OP", "OP/26/118701", "2026-09-05")]
    reps = run(c.reports(UHID))
    assert [(r["id"], r["version"], r["status"], r["current"]) for r in reps] == [
        ("RAD/26/00981", 1, "final", True), ("PATH/26/00411", 1, "preliminary", False), ("PATH/26/00411", 2, "corrected", True)]
    ct, v1, v2 = reps
    assert ct["doc_type"] == "ct" and v2["doc_type"] == "histopathology" and v2["issued"] == "2026-09-07" and v2["encounter_number"] == "OP/26/118701"
    assert all(r["signature"] is None and r["observations"] == [] for r in reps)        # signed_by is a name, never a signature
    assert v2["reported_by"] == {"ref": "", "name": "Dr Revathi Krishnan"} and ct["reported_by"] is None and set(his_case._HIS_KEYS) <= set(v2)
    d = run(c.document(v2["document_ref"]))
    assert d["content"] == PDF2 and d["sha256"] == hashlib.sha256(PDF2).hexdigest() and d["filename"].endswith(".pdf")
    assert run(c.document(ct["document_ref"]))["content"] == CT and run(c.open_orders(UHID)) == []
    assert [r["id"] for r in run(c.reports(UHID, "2026-09-06"))] == ["PATH/26/00411"]


@pytest.mark.parametrize("word,status", [("Final", "final"), ("VERIFIED", "final"), ("provisional", "preliminary"), ("Draft", "preliminary"), ("revised", "corrected"),
                                         ("Amended", "amended"), ("Cancelled", "cancelled"), ("entered in error", "cancelled"), ("", "unknown"), ("printed", "unknown")])
def test_status_words(word, status):
    assert _common.status_word(word) == status


def test_bad_rows_are_skipped_with_a_counted_reason_and_never_stop_the_rest(folder, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere")
    (outside / "x.pdf").write_bytes(PDF)
    (folder / "out.pdf").symlink_to(outside / "x.pdf")
    (folder / "big.pdf").write_bytes(b"%PDF-1.4\n")
    (folder / "tool.exe").write_bytes(b"MZ")
    row = lambda **k: ",".join({**dict(uhid=UHID, patient_name=NAME, sex="F", dob="", age="46", visit_no="OP/26/118701", visit_type="OP", report_id="R1",
                                       report_type="Histopathology report", report_date="05/09/2026", status="final", signed_by="", file="hpe_v1.pdf"), **k}.values())
    index(folder, [row(), row(uhid=""), row(report_id=""), row(report_date="31/02/2026"), row(report_date="soon"), row(file="../../etc/passwd"),
                   row(file="/etc/passwd"), row(file="out.pdf"), row(file="missing.pdf"), row(file="tool.exe"), row(visit_type="ER"), row(age="old"),
                   row(dob="1980-13-40"), row(patient_name=""), row(report_id="R2", file="hpe_v1.pdf"), "only,three,cells", ""])
    c = FolderBridgeClient(str(folder))
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"]["rows"] == 16 and ping["counts"]["reports"] == 2
    assert ping["counts"]["skipped"] == {"no uhid": 1, "no report_id": 2, "report_date missing or not a date (DD/MM/YYYY or ISO)": 2, "file: the file path contains '..'": 1,
                                         "file: the file must be named relative to the folder": 1, "file: the file is outside the folder": 1, "file: the file is missing": 1,
                                         "file: not a PDF, text or image file": 1, "visit_type is not OP or IP": 1, "age is not a number of years": 1,
                                         "dob is not a date (DD/MM/YYYY or ISO)": 1, "no patient_name": 1}
    assert [r["id"] for r in run(c.reports(UHID))] == ["R1", "R2"]
    with pytest.raises(his_client.HISError):                        # only files the index lists are ever served
        run(c.document(f"folder:{UHID.replace('/', '%2F')}/R1/out.pdf"))
    with pytest.raises(his_client.HISError):
        run(c.document("folder:x/y/..%2F..%2Fetc%2Fpasswd"))


def test_index_problems_are_plain_errors(folder, data_root):
    c = FolderBridgeClient(str(folder))
    assert "index.csv" in run(c.ping())["error"]                    # no index yet
    (folder / "index.csv").write_text("uhid,file\nx,y\n")
    assert "missing the columns" in run(c.ping())["error"] and "report_id" in run(c.ping())["error"]
    (folder / "index.csv").write_bytes(b"\xff\xfe\x00bad")
    assert "UTF-8" in run(c.ping())["error"]
    with pytest.raises(his_client.HISError):
        run(c.find_patient(UHID))
    assert run(FolderBridgeClient(str(data_root / "cases")).ping())["ok"] is False and run(FolderBridgeClient("/etc").ping())["ok"] is False


def test_create_a_case_file_from_the_report_folder(folder, fakes, monkeypatch):
    index(folder, GOOD)
    client = FolderBridgeClient(str(folder), label="Small Hospital (SYNTHETIC)")
    monkeypatch.setattr(his_client, "client", lambda *a, **k: client)
    look = run(his_case.lookup(UHID, {"all": True}))
    assert look["found"] and look["reports"] == 2 and [e["number"] for e in look["encounters"]] == ["IP/26/01871", "OP/26/118701"]

    async def go():
        out = await his_case.create("IP/26/01871", "breast", "early", "optimal", "", {"all": True}, "dr.breast", ROLES_DOC)
        await out["job"]["task"]
        return out
    out = run(go())
    case = out["case"]
    assert case["patient"]["mrn"] == UHID and case["his"]["matched_on"]["kind"] == "ip_no" and out["job"]["his"]["added"] == 3 and out["job"]["his"]["errors"] == []
    docs = {(d["his"]["id"], d["his"]["version"]): d for d in store.list_docs(case["case_id"])}
    assert docs[("PATH/26/00411", 1)].get("superseded") and not docs[("PATH/26/00411", 2)].get("superseded")
    cur, ct = docs[("PATH/26/00411", 2)], docs[("RAD/26/00981", 1)]
    assert cur["state"] == "ready" and cur["classification"]["status"] == "CORRECTED" and cur["classification"]["signed"] != "yes" and cur["his"]["signature"] is None
    assert ct["classification"]["status"] == "PRELIMINARY"          # the index says final, the text says preliminary: the stricter side wins
    assert {i["value"] for i in case["patient"]["ids"]} >= {UHID, "OP/26/118701", "IP/26/01871"}


# ---- ABDM bundles -------------------------------------------------------------------------------------------------------------
def patient(mr=UHID, abha="91-1111-2222-3333"):
    ids = []
    if mr:
        ids.append({"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]}, "system": "https://vaidyx-demo.example/uhid", "value": mr})
    if abha:   # the official NRCeS example types the ABHA number MR under the health-id system
        ids.append({"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]}, "system": "https://healthid.ndhm.gov.in", "value": abha})
    return {"resourceType": "Patient", "id": "pat-1", "identifier": ids, "name": [{"text": NAME}], "gender": "female", "birthDate": "1980-01-18"}


def bundle(rtype_code, title, sections, resources, ident="REC-1", date="2026-09-05T11:00:00+05:30", status="final", pat=None):
    comp = {"resourceType": "Composition", "id": "comp-1", "status": status, "type": {"coding": [{"system": "http://snomed.info/sct", "code": rtype_code}]},
            "subject": {"reference": "Patient/pat-1"}, "encounter": {"reference": "urn:uuid:enc-1"}, "date": date, "title": title,
            "author": [{"reference": "Practitioner/pr-1", "display": "Dr Revathi Krishnan"}], "section": sections}
    enc = {"resourceType": "Encounter", "id": "enc-1", "status": "finished", "class": {"code": "AMB"},
           "identifier": [{"type": {"coding": [{"code": "VN"}]}, "value": "OP/26/118701"}], "period": {"start": "2026-09-01"}}
    res = [comp, pat or patient(), enc] + resources
    return {"resourceType": "Bundle", "type": "document", "identifier": {"system": "https://vaidyx-demo.example/bundle", "value": ident}, "timestamp": date,
            "entry": [{"fullUrl": ("urn:uuid:" + r["id"]) if r["resourceType"] == "Encounter" else f"{r['resourceType']}/{r['id']}", "resource": r} for r in res]}


def diagnostic(status="final", data=PDF, ident="REC-1", date="2026-09-05T11:00:00+05:30", binary=False):
    obs = {"resourceType": "Observation", "id": "obs-1", "status": "final", "code": {"coding": [{"system": "http://loinc.org", "code": "718-7"}], "text": "Haemoglobin"},
           "valueQuantity": {"value": 12.1, "unit": "g/dL"}}
    form = {"contentType": "application/pdf", "url": "Binary/bin-1"} if binary else {"contentType": "application/pdf", "data": base64.b64encode(data).decode()}
    dr = {"resourceType": "DiagnosticReport", "id": "dr-1", "status": status, "identifier": [{"value": "PATH/26/00411"}],
          "code": {"coding": [{"system": "http://loinc.org", "code": "11526-1"}], "text": "Histopathology report"}, "issued": date,
          "result": [{"reference": "Observation/obs-1"}], "conclusion": "Invasive carcinoma", "presentedForm": [form]}
    extra = [{"resourceType": "Binary", "id": "bin-1", "contentType": "application/pdf", "data": base64.b64encode(data).decode()}] if binary else []
    return bundle("721981007", "Diagnostic report", [{"title": "Pathology", "entry": [{"reference": "DiagnosticReport/dr-1"}]}], [dr, obs] + extra, ident=ident, date=date)


def discharge(with_file=True, data=PDF):
    doc = {"resourceType": "DocumentReference", "id": "doc-1", "status": "current",
           "content": [{"attachment": {"contentType": "application/pdf", "data": base64.b64encode(data).decode(), "title": "Discharge summary"}}]}
    sec = {"title": "Hospital course", "text": {"status": "generated", "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\"><p>Uneventful &amp; stable.</p></div>"},
           "entry": [{"reference": "DocumentReference/doc-1"}] if with_file else []}
    return bundle("373942005", "Discharge summary", [sec], [doc] if with_file else [], ident="DS-1", date="2026-09-24T10:00:00+05:30")


@pytest.fixture
def bundles(data_root, monkeypatch):
    monkeypatch.delenv("TB_HIS_FOLDER_ROOTS", raising=False)
    _common._CACHE.clear()
    d = data_root / "his_inbox" / "abdm"
    d.mkdir(parents=True)
    return d


def test_bundles_become_reports_with_identity_from_the_patient_resource(bundles):
    (bundles / "a.json").write_text(json.dumps(diagnostic("preliminary")))
    (bundles / "b.json").write_text(json.dumps(diagnostic("amended", PDF2, date="2026-09-07T10:00:00+05:30", binary=True)))
    (bundles / "c.json").write_text(json.dumps(discharge()))
    (bundles / "d.json").write_text(json.dumps(bundle("419891008", "Outside referral letter", [{"title": "Note", "text": {"div": "<div>Kindly review.</div>"}}], [], ident="HD-1")))
    c = ABDMBundleClient(str(bundles), label="ABDM hand-over (SYNTHETIC)")
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"] == {"files": 4, "patients": 1, "reports": 4, "skipped": {}}
    p = run(c.find_patient(UHID))
    assert p["uhid"] == UHID and p["abha"] == "91-1111-2222-3333" and p["name"] == NAME and p["sex"] == "F" and p["matched_on"]["kind"] == "uhid"
    assert run(c.find_patient("91-1111-2222-3333"))["matched_on"]["kind"] == "abha" and run(c.find_patient("OP/26/118701"))["matched_on"]["kind"] == "op_no"
    assert [(e["kind"], e["number"]) for e in run(c.encounters(UHID))] == [("OP", "OP/26/118701")]
    reps = {(r["id"], r["version"]): r for r in run(c.reports(UHID))}
    v1, v2, ds, hd = reps[("PATH/26/00411", 1)], reps[("PATH/26/00411", 2)], reps[("DS-1", 1)], reps[("HD-1", 1)]
    assert (v1["status"], v1["current"], v2["status"], v2["current"]) == ("preliminary", False, "amended", True)
    assert v2["kind"] == "diagnostic" and v2["doc_type"] == "histopathology" and v2["observations"][0]["value"] == "12.1 g/dL" and v2["conclusion"] == "Invasive carcinoma"
    assert v2["encounter_number"] == "OP/26/118701" and v2["reported_by"]["name"] == "Dr Revathi Krishnan" and "DiagnosticReportRecord" in v2["doc_type_basis"]
    assert all(r["signature"] is None for r in reps.values()) and set(his_case._HIS_KEYS) <= set(v2)
    assert run(c.document(v1["document_ref"]))["content"] == PDF and run(c.document(v2["document_ref"]))["content"] == PDF2   # inline data, then a Binary in the bundle
    assert ds["kind"] == "note" and ds["status"] == "final" and run(c.document(ds["document_ref"]))["content"] == PDF
    text = run(c.document(hd["document_ref"]))
    assert hd["document"]["text_only"] is True and hd["observations"] == [] and text["filename"].endswith(".txt") and "Kindly review." in text["content"].decode()
    assert [k for k in reps if run(c.reports(UHID, "2026-09-06")) and k in {(r["id"], r["version"]) for r in run(c.reports(UHID, "2026-09-06"))}] == [("PATH/26/00411", 2), ("DS-1", 1)]


def test_abha_only_patient_and_bundles_that_are_not_read(bundles):
    (bundles / "ok.json").write_text(json.dumps(bundle("371530004", "OP consultation", [{"title": "Advice", "text": {"div": "<div>Review in 2 weeks.</div>"}}], [],
                                                       ident="OP-1", pat=patient(mr="", abha="anitha.reddy@sbx"))))
    (bundles / "rx.json").write_text(json.dumps(bundle("440545006", "Prescription", [], [], ident="RX-1")))
    (bundles / "search.json").write_text(json.dumps({"resourceType": "Bundle", "type": "searchset", "entry": []}))
    (bundles / "nocomp.json").write_text(json.dumps({"resourceType": "Bundle", "type": "document", "entry": [{"resource": patient()}]}))
    (bundles / "broken.json").write_text("{not json")
    (bundles / "list.json").write_text("[1, 2]")
    (bundles / "nobody.json").write_text(json.dumps(bundle("419891008", "Letter", [], [], ident="L-1", pat=patient(mr="", abha=""))))
    c = ABDMBundleClient(str(bundles))
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"]["reports"] == 1 and ping["counts"]["skipped"] == {
        "a record type Vaidyx-TB does not read": 1, "not a document bundle": 1, "the first entry is not a Composition": 1, "not readable JSON": 1,
        "not a FHIR Bundle": 1, "the Patient has no MR identifier and no ABHA": 1}
    p = run(c.find_patient("anitha.reddy@sbx"))
    assert p["abha_address"] == "anitha.reddy@sbx" and p["uhid"] == "anitha.reddy@sbx" and p["matched_on"]["kind"] == "abha_address"
    assert abdm_bundle.record_type({"meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/DischargeSummaryRecord"]}}) == "DischargeSummaryRecord"


def test_create_a_case_file_from_abdm_bundles(bundles, fakes, monkeypatch):
    (bundles / "a.json").write_text(json.dumps(diagnostic("final")))
    (bundles / "c.json").write_text(json.dumps(discharge(data=CT)))
    (bundles / "dup.json").write_text(json.dumps(bundle("419891008", "Copy of the report", [], [{"resourceType": "Binary", "id": "b", "contentType": "application/pdf",
                                                                                                    "data": base64.b64encode(PDF).decode()}], ident="ZZ-9")))
    client = ABDMBundleClient(str(bundles), label="ABDM hand-over (SYNTHETIC)")
    monkeypatch.setattr(his_client, "client", lambda *a, **k: client)

    async def go():
        out = await his_case.create("91-1111-2222-3333", "breast", "early", "optimal", "", {"all": True}, "dr.breast", ROLES_DOC)
        await out["job"]["task"]
        return out
    out = run(go())
    case = out["case"]
    assert case["patient"]["mrn"] == UHID and case["patient"]["abha"] == "91-1111-2222-3333" and case["his"]["kind"] == "abdm_bundles"
    assert out["job"]["his"]["added"] == 2 and out["job"]["his"]["skipped"] == 1     # the same PDF bytes in two bundles: filed once
    docs = {x["his"]["id"]: x for x in store.list_docs(case["case_id"])}
    assert sorted(docs) == ["DS-1", "PATH/26/00411"] and docs["DS-1"]["his"]["kind"] == "note"
    d = docs["PATH/26/00411"]
    assert d["his"]["id"] == "PATH/26/00411" and d["classification"]["status"] == "FINAL" and d["classification"]["signed"] != "yes" and d["his"]["signature"] is None
    assert d["his"]["observations"][0]["label"] == "Haemoglobin"                    # a candidate: checked against the text by his_overlay, never a fact by itself
