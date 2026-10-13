"""HIS-connected Case Files (V2 items 3.2 to 3.6): the overlay of HIS status, signature, document type and candidate values on a
fetched document (his_overlay), the create / fetch / re-fetch / link / fetch-older flows against a fake HIS client (his_case), and
the gate over HIS records (pending orders with their accession No., superseded versions as history, outside reports matched by
name only). No model, no network: the model calls are replaced by fakes, the HIS by an in-memory client. SYNTHETIC data only."""
import asyncio
import copy

import pytest

from tumour_board import confirm, extract, his_case, his_client, his_overlay, ingest, notify, org, rules, search, service, store
from tumour_board.tests import util

UHID = "VXH/26/004201"
PAT = {"id": "vxh-26-004201", "ref": "Patient/vxh-26-004201", "uhid": UHID, "registration_kind": "permanent", "name": "Anitha Reddy (SYNTHETIC)", "sex": "F",
       "age": 46, "dob": "1980-01-18", "abha": "99-2600-0000-0101", "abha_address": "anitha.reddy@sbx", "pmjay_id": "PMJAY-VX-26000101",
       "identifiers": [{"kind": "uhid", "value": UHID}], "registered_on": "2026-09-01", "last_updated": "2026-09-01T08:30:00+05:30"}
TEMP = {"id": "vxh-t-26-00412", "ref": "Patient/vxh-t-26-00412", "uhid": "VXH/T/26/00412", "registration_kind": "temporary", "name": "Anitha Reddy (SYNTHETIC)",
        "sex": "F", "age": 46, "dob": "1980-01-18", "abha": "", "identifiers": [], "registered_on": "2026-08-22", "last_updated": "2026-08-22T08:30:00+05:30"}
ENCS = [{"id": "op-26-118701", "ref": "Encounter/op-26-118701", "kind": "OP", "number": "OP/26/118701", "status": "finished", "department": "Breast Surgery", "unit": "Unit I",
         "consultant": {"ref": "Practitioner/x", "name": "Dr Kavitha Raghunathan"}, "start": "2026-09-01", "end": "", "ward_history": [], "pmjay_preauth": None,
         "last_updated": "2026-09-01T09:00:00+05:30"},
        {"id": "ip-26-01871", "ref": "Encounter/ip-26-01871", "kind": "IP", "number": "IP/26/01871", "status": "finished", "department": "Breast Surgery", "unit": "Unit I",
         "consultant": None, "start": "2026-09-21", "end": "2026-09-24", "ward_history": [{"ward": "Surgical Ward 2", "bed": "2-07", "from": "2026-09-21", "to": "2026-09-24", "reason": ""}],
         "pmjay_preauth": {"status": "approved", "date": "2026-09-19"}, "last_updated": "2026-09-24T10:00:00+05:30"}]
SIG = {"ref": "Provenance/sig-p01-r04-v1", "signer": {"ref": "Practitioner/y", "name": "Dr Revathi Krishnan"}, "signed_at": "2026-09-05T11:00:00+05:30", "ca": "Vaidyx Demo CA",
       "serial": "VXDCA-00A1B204", "document_hash": "abc", "verification_status": "verified",
       "block": "Digitally signed by Dr Revathi Krishnan, MD (Pathology), Reg. No. VXREG-20204, 05/09/2026 11:00, Vaidyx Demo CA, certificate serial VXDCA-00A1B204"}
HPE_TEXT = ("Vaidyx Demo Hospital (SYNTHETIC)\nDepartment of Pathology\nHISTOPATHOLOGY REPORT\nPatient name : Anitha Reddy (SYNTHETIC) UHID : VXH/26/004201\n"
            "Age / Sex : 46 Y / F OP No. : OP/26/118701\nLab No. : PATH/26/00411\nDiagnosis: Invasive carcinoma of no special type\nReport status: FINAL\n" + SIG["block"] + "\n")
CT_TEXT = ("Vaidyx Demo Hospital (SYNTHETIC)\nDepartment of Radiology\nCECT THORAX ABDOMEN PELVIS\nPatient name : Anitha Reddy (SYNTHETIC) UHID : VXH/26/004201\n"
           "Age / Sex : 46 Y / F OP No. : OP/26/118701\nAccession No. : RAD/26/00981\nFindings: mass 3.4 x 2.8 cm\nImpression: as above\nReport status: PRELIMINARY\n"
           "Reported by: Dr Junior Resident (preliminary, verification awaited)\n")


def report(rid, version, title, doc_type, status, text, sig=None, current=True, encounter="OP/26/118701", kind="OP", accession="PATH/26/00411", observations=None,
           dept="Pathology", issued="2026-09-05T11:00:00+05:30", last_updated=None, code=("11526-1", "Pathology study")):
    return {"id": rid, "version": version, "kind": "diagnostic", "ref": f"DiagnosticReport/{rid}", "document_ref": f"DocumentReference/doc-{rid}-v{version}", "current": current,
            "title": title, "code": {"system": "http://loinc.org", "code": code[0], "display": code[1]}, "category": [], "doc_type": doc_type, "doc_type_basis": f"LOINC {code[0]}",
            "status": status, "issued": issued, "effective": issued, "encounter_ref": "Encounter/x", "encounter_number": encounter, "encounter_kind": kind, "accession": accession,
            "order_ref": "ServiceRequest/o", "performer_department": dept, "reported_by": {"ref": "Practitioner/y", "name": "Dr X"}, "signature": sig,
            "observations": observations or [], "imaging_study_ref": None, "conclusion": "", "amendment_note": "",
            "document": {"url": f"/documents/{rid}-v{version}.txt", "sha256": "", "content_type": "text/plain", "title": title, "creation": issued},
            "last_updated": last_updated or issued, "_text": text}


class FakeHIS:
    """An in-memory HIS with the his_client interface: one registration, its encounters, reports and open orders."""
    kind, label = "fhir", "Fake HIS (SYNTHETIC)"

    def __init__(self, reports, orders=(), similar=(), linked_reports=None, encounters=None):
        self.reports_by_patient = {PAT["id"]: list(reports)}
        if linked_reports:
            self.reports_by_patient.update(linked_reports)
        self.orders = list(orders)
        self.similar = list(similar)
        self.encs = encounters if encounters is not None else ENCS
        self.calls = []
        self.fail = False

    async def ping(self):
        return {"ok": True, "name": self.label, "fhir_version": "4.0.1", "token_ok": True, "error": ""}

    async def hospital(self):
        return {"name": self.label, "departments": []}

    async def find_patient(self, identifier):
        self.calls.append(("find_patient", identifier))
        if self.fail:
            raise his_client.HISError("connection refused")
        ids = {UHID, "IP/26/01871", "OP/26/118701", PAT["abha"]}
        if identifier.upper() not in {x.upper() for x in ids}:
            return None
        kind = "uhid" if identifier.upper() == UHID else ("ip_no" if identifier.startswith("IP") else ("op_no" if identifier.startswith("OP") else "abha"))
        return {**copy.deepcopy(PAT), "matched_on": {"kind": kind, "value": identifier}, "similar": copy.deepcopy(self.similar)}

    async def similar_registrations(self, patient_id):
        return copy.deepcopy(self.similar)

    async def encounters(self, patient_id):
        return copy.deepcopy(self.encs) if patient_id == PAT["id"] else []

    async def reports(self, patient_id, since=None):
        self.calls.append(("reports", patient_id, since))
        out = [copy.deepcopy(r) for r in self.reports_by_patient.get(patient_id, []) if not since or r["last_updated"] >= since]
        return out

    async def open_orders(self, patient_id):
        return copy.deepcopy(self.orders) if patient_id == PAT["id"] else []

    async def referrals(self, patient_id):
        return []

    async def document(self, ref):
        self.calls.append(("document", ref))
        for rs in self.reports_by_patient.values():
            for r in rs:
                if r["document_ref"] == ref:
                    data = r["_text"].encode()
                    import hashlib
                    return {"ref": ref, "content": data, "sha256": hashlib.sha256(data).hexdigest(), "content_type": "text/plain", "title": r["title"],
                            "filename": f"{r['id']}-v{r['version']}.txt", "size": len(data), "creation": r["issued"], "status": "current", "doc_status": r["status"]}
        raise his_client.HISError(f"no such document {ref}")

    async def imaging_study(self, ref):
        return None


ROLES_DOC = {"user": "dr.breast", "admin": False, "known": True, "coordinator": False, "departments": {"breast_surgery": "member"}, "treating": {"breast_surgery": "member"}, "supporting": {}}


@pytest.fixture
def fakes(monkeypatch):
    """Model calls replaced: the text comes from the stored file; classification from the title; facts from the text."""
    async def fake_pages(path, audit=None):
        return [{"text": path.read_bytes().decode(errors="replace"), "method": "text-layer"}]

    async def fake_classify(t, audit=None):
        title = next((l.strip() for l in t.splitlines() if l.isupper() and "REPORT" in l or l.startswith("CECT")), "REPORT")
        dt = "histopathology" if "HISTOPATHOLOGY" in t else ("ct" if "CECT" in t else ("lab" if "HAEMATOLOGY" in t or "CBC" in t else ("ihc" if "IMMUNO" in t else "other")))
        return {"title": title, "department": "", "doc_type": dt, "body_region": "", "report_date": "", "status_quote": "", "signature_quote": "", "signer": "",
                "patient_name": "Anitha Reddy", "patient_id": UHID}

    async def fake_facts(t, fids, audit=None):
        out = {}
        if "histologic_type" in fids and "Diagnosis:" in t:
            out["histologic_type"] = {"found": True, "value": t.split("Diagnosis:")[1].splitlines()[0].strip(), "quote": "Diagnosis:" + t.split("Diagnosis:")[1].splitlines()[0]}
        if "lesion_size" in fids and "mass" in t:
            out["lesion_size"] = {"found": True, "value": "3.4 x 2.8 cm", "quote": "mass 3.4 x 2.8 cm"}
        if "haemoglobin" in fids and "Haemoglobin" in t:
            line = next(l for l in t.splitlines() if "Haemoglobin" in l)
            out["haemoglobin"] = {"found": True, "value": line.split(")")[1].split("13.0")[0].strip() if ")" in line else "12.1 gm%", "quote": line}
        if "her2" in fids and "HER2" in t:
            line = next(l for l in t.splitlines() if "HER2" in l)
            out["her2"] = {"found": True, "value": line.split("score)")[1].strip(), "quote": line}
        return out
    monkeypatch.setattr(ingest, "extract_pages", fake_pages)
    monkeypatch.setattr(extract, "classify", fake_classify)
    monkeypatch.setattr(extract, "extract_facts", fake_facts)
    monkeypatch.setattr(search, "index", lambda case_id: None)


def _use(monkeypatch, fake):
    monkeypatch.setattr(his_client, "client", lambda: fake)
    return fake


def _create(identifier=UHID, protocol="breast", setting="early", level="optimal", window=None, roles=None, department=None, case_id=""):
    async def go():
        out = await his_case.create(identifier, protocol, setting, level, "", window, "dr.breast", roles or ROLES_DOC, department=department, case_id=case_id)
        await out["job"]["task"]
        return out
    return asyncio.run(go())


def _await(coro_fn):
    async def go():
        job = await coro_fn()
        if job.get("task"):
            await job["task"]
        return job
    return asyncio.run(go())


# ---- his_overlay --------------------------------------------------------------------------------------------------------------

def _doc(text, his, classification=None, facts=None):
    d = {"doc_id": "D1", "filename": "x.txt", "pages": [{"text": text, "method": "text-layer"}], "his": his, "facts": facts or {}}
    if classification is not None:
        d["classification"] = classification
    return d


def test_overlay_status_and_verified_signature_from_his():
    c = {"status": "FINAL", "signed": "yes", "status_quote": "Report status: FINAL", "signature_quote": "", "doc_type": "histopathology", "doc_type_keyword": "histopathology", "status_notes": []}
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "histopathology"}, c))
    c = d["classification"]
    assert c["status"] == "FINAL" and c["signed"] == "yes" and c["status_source"] == "his" and c["signed_source"] == "his"
    assert c["text_status"] == "FINAL" and c["text_signed"] == "yes" and c["signature_quote"] == SIG["block"]  # the block is printed in the PDF: a verified quote
    assert c["his_signature"]["verification_status"] == "verified" and c["status_notes"] == []
    his_overlay.apply(d)  # idempotent
    assert d["classification"]["text_status"] == "FINAL" and d["classification"]["status_notes"] == []


def test_overlay_preliminary_and_unsigned_and_failed_signature():
    c = {"status": "PRELIMINARY", "signed": "unknown", "status_quote": "", "signature_quote": "", "doc_type": "ct", "doc_type_keyword": "ct", "status_notes": []}
    d = his_overlay.apply(_doc(CT_TEXT, {"status": "preliminary", "signature": None, "doc_type": "ct"}, c))
    assert d["classification"]["status"] == "PRELIMINARY" and d["classification"]["signed"] == "no"
    # final in the LIS, no digital signature: not signed, with the reason
    c = {"status": "FINAL", "signed": "no", "status_quote": "Report status: FINAL", "signature_quote": "Signature pending", "doc_type": "histopathology", "doc_type_keyword": "histopathology", "status_notes": []}
    d = his_overlay.apply(_doc(HPE_TEXT.replace(SIG["block"], "Signature pending"), {"status": "final", "signature": None, "doc_type": "histopathology"}, c))
    assert d["classification"]["status"] == "FINAL" and d["classification"]["signed"] == "no" and any("no digital signature" in n for n in d["classification"]["status_notes"])
    # a signature that failed verification (tampered document) never counts as signed, even though the PDF prints the block
    c = {"status": "FINAL", "signed": "yes", "status_quote": "Report status: FINAL", "signature_quote": SIG["block"], "doc_type": "histopathology", "doc_type_keyword": "histopathology", "status_notes": []}
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": {**SIG, "verification_status": "failed"}, "doc_type": "histopathology"}, c))
    assert d["classification"]["signed"] == "no" and any("failed verification" in n for n in d["classification"]["status_notes"])
    assert not rules._is_final({"doc_id": "D1", "classification": d["classification"]})
    # cancelled in the HIS
    c = {"status": "FINAL", "signed": "yes", "status_quote": "", "signature_quote": "", "doc_type": "ct", "doc_type_keyword": "ct", "status_notes": []}
    d = his_overlay.apply(_doc(CT_TEXT, {"status": "cancelled", "signature": None, "doc_type": "ct"}, c))
    assert d["classification"]["status"] == "CANCELLED"


def test_overlay_stricter_side_wins_when_text_and_his_disagree():
    # the HIS says final, the PDF text says preliminary: not counted as final until they agree
    c = {"status": "PRELIMINARY", "signed": "unknown", "status_quote": "preliminary report", "signature_quote": "", "doc_type": "ct", "doc_type_keyword": "ct", "status_notes": []}
    d = his_overlay.apply(_doc(CT_TEXT, {"status": "final", "signature": SIG, "doc_type": "ct"}, c))
    assert d["classification"]["status"] == "PRELIMINARY" and any("not counted as final" in n for n in d["classification"]["status_notes"])
    # the HIS says preliminary, the text says FINAL: the system's status stands (preliminary)
    c = {"status": "FINAL", "signed": "yes", "status_quote": "Report status: FINAL", "signature_quote": "", "doc_type": "ct", "doc_type_keyword": "ct", "status_notes": []}
    d = his_overlay.apply(_doc(CT_TEXT, {"status": "preliminary", "signature": None, "doc_type": "ct"}, c))
    assert d["classification"]["status"] == "PRELIMINARY" and d["classification"]["signed"] == "no"


def test_overlay_document_type_opinions():
    base = {"status": "FINAL", "signed": "yes", "status_quote": "", "signature_quote": "", "status_notes": []}
    # HIS and model agree
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "histopathology"}, {**base, "doc_type": "histopathology", "doc_type_keyword": "histopathology"}))
    assert d["classification"]["doc_type"] == "histopathology" and "agree" in d["classification"]["doc_type_check"] and "doc_type_disagreement" not in d["classification"]
    # HIS and the title keywords agree against the model: the two independent readings settle it
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "histopathology"}, {**base, "doc_type": "cytology", "doc_type_keyword": "histopathology"}))
    assert d["classification"]["doc_type"] == "histopathology" and d["classification"]["model_doc_type_his"] == "cytology"
    # the model gave up: the HIS type stands
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "histopathology"}, {**base, "doc_type": "other", "doc_type_keyword": ""}))
    assert d["classification"]["doc_type"] == "histopathology"
    # model and keywords agree against the HIS: the document's own readings stand, noted
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "ihc"}, {**base, "doc_type": "histopathology", "doc_type_keyword": "histopathology"}))
    assert d["classification"]["doc_type"] == "histopathology" and "doc_type_disagreement" not in d["classification"] and "ihc" in d["classification"]["doc_type_check"]
    # three opinions: kept for a clinician (confirm_doc_type), the HIS type as the second possible type
    d = his_overlay.apply(_doc(HPE_TEXT, {"status": "final", "signature": SIG, "doc_type": "ihc"}, {**base, "doc_type": "histopathology", "doc_type_keyword": "cytology"}))
    dis = d["classification"]["doc_type_disagreement"]
    assert dis["keyword_type"] == "ihc" and dis["model_type"] == "histopathology" and dis["basis"] == "his"
    assert rules._doc_types({"doc_id": "D1", "classification": d["classification"]}) == {"histopathology", "ihc"}


CBC_TEXT = ("Vaidyx Demo Hospital (SYNTHETIC)\nHAEMATOLOGY REPORT: COMPLETE BLOOD COUNT\nUHID : VXH/26/004201\nInvestigation Result Units Biological reference interval\n"
            "Haemoglobin (Hb) 12.1 gm% 13.0-17.0\nTotal leucocyte count (TLC) 6,900 /cumm 4,000-11,000\nPlatelet count 2.4 lakhs/cumm 1.5-4.5\nReport status: FINAL\n")


def test_overlay_observations_are_candidates_checked_against_the_text():
    obs = [{"id": "o1", "code": None, "label": "Haemoglobin (Hb)", "fact": "haemoglobin", "value": "11.2 gm%", "status": "final"},   # the HIS disagrees with its own PDF
           {"id": "o2", "code": None, "label": "Total leucocyte count (TLC)", "fact": "wbc", "value": "6900 /cumm", "status": "final"},  # the PDF prints 6,900 (Indian comma)
           {"id": "o3", "code": None, "label": "Platelet count", "fact": "platelets", "value": "2.4 lakhs/cumm", "status": "final"}]   # verbatim, the model missed it
    d = _doc(CBC_TEXT, {"status": "final", "signature": SIG, "doc_type": "lab", "observations": obs},
             {"status": "FINAL", "signed": "yes", "doc_type": "lab", "doc_type_keyword": "lab", "status_notes": []},
             facts={"haemoglobin": util.fact("12.1 gm%", quote="Haemoglobin (Hb) 12.1 gm%")})
    his_overlay.check_observations(d)
    rows = {r["fact"]: r for r in d["his_checks"]}
    assert rows["haemoglobin"]["result"] == "differs" and rows["haemoglobin"]["text"] == "HIS value differs from the report text: haemoglobin 11.2 gm% vs 12.1 gm%"
    assert rows["wbc"]["result"] == "found" and "wbc" not in d["facts"]  # a number found only after dropping the comma is consistent, never a new fact
    assert rows["platelets"]["result"] == "found" and rows["platelets"]["added"] is True
    assert d["facts"]["platelets"]["value"] == "2.4 lakhs/cumm" and d["facts"]["platelets"]["verification"] == "verified" and d["facts"]["platelets"]["source"] == his_overlay.HIS_CANDIDATE
    assert d["facts"]["haemoglobin"]["value"] == "12.1 gm%"  # the PDF wins; the HIS value is never shown as a fact
    assert [f["fact"] for f in d["his_flags"]] == ["haemoglobin"]
    # an observation whose value is absent from the text and that the model did not read: flagged, not added
    d2 = _doc(CBC_TEXT, {"status": "final", "signature": SIG, "doc_type": "lab", "observations": [{"id": "o9", "label": "Serum creatinine", "fact": "creatinine", "value": "0.9 mg/dL"}]},
              {"status": "FINAL", "signed": "yes", "doc_type": "lab", "doc_type_keyword": "lab", "status_notes": []})
    his_overlay.check_observations(d2)
    assert d2["his_checks"][0]["result"] == "differs" and "creatinine" not in d2["facts"] and "not found in the report text" in d2["his_flags"][0]["text"]
    # no observations: nothing written
    d3 = _doc(CBC_TEXT, {"status": "final", "doc_type": "lab"}, {"status": "FINAL", "signed": "yes", "doc_type": "lab", "status_notes": []})
    his_overlay.check_observations(d3)
    assert "his_checks" not in d3 and "his_flags" not in d3


# ---- window, patient record -------------------------------------------------------------------------------------------------

def test_window_helpers():
    from datetime import date
    assert his_case.window_from(None) == {"months": 12}
    assert his_case.window_from({"months": "6"}) == {"months": 6}
    assert his_case.window_from({"all": True}) == {"all": True}
    assert his_case.window_from({"from": "15/03/2026"}) == {"from": "2026-03-15"}
    with pytest.raises(his_case.HISCaseError):
        his_case.window_from({"months": 0})
    with pytest.raises(his_case.HISCaseError):
        his_case.window_from({"from": "yesterday"})
    assert his_case.window_start({"months": 12}, date(2026, 10, 14)) == "2025-10-14"
    assert his_case.window_start({"months": 6}, date(2026, 3, 31)) == "2025-09-30"
    assert his_case.window_start({"all": True}) == "" and his_case.window_start({"from": "2026-01-01"}) == "2026-01-01"
    assert his_case.window_label({"months": 24}) == "last 24 months" and his_case.window_label({"all": True}) == "all records"


def test_patient_record_learns_every_encounter_number_and_never_an_aadhaar():
    p = his_case.patient_record(PAT, ENCS)
    assert p["mrn"] == UHID and p["agesex"] == "46 Y / F" and p["abha"] == PAT["abha"] and p["source"] == "his"
    kinds = {(x["kind"], x["value"]) for x in p["ids"]}
    assert kinds == {("uhid", UHID), ("abha", PAT["abha"]), ("pmjay", PAT["pmjay_id"]), ("op_no", "OP/26/118701"), ("ip_no", "IP/26/01871")}
    assert "aadhaar" not in str(p).lower()


# ---- create and the first fetch --------------------------------------------------------------------------------------------

def _two_reports():
    hpe = report("p01-r04", 1, "Histopathology report", "histopathology", "final", HPE_TEXT, sig=SIG)
    ct = report("p01-r02", 1, "CECT thorax abdomen pelvis", "ct", "preliminary", CT_TEXT, sig=None, accession="RAD/26/00981", dept="Radiology", issued="2026-09-02T15:10:00+05:30",
                code=("18748-4", "Diagnostic imaging study"))
    return [hpe, ct]


def test_create_from_uhid_fetches_every_record_with_its_his_metadata(fakes, monkeypatch):
    fake = _use(monkeypatch, FakeHIS(_two_reports(), similar=[TEMP]))
    out = _create()
    case = out["case"]
    assert case["case_id"].startswith("TB-") and case["protocol"] == "breast" and case["setting"] == "early" and case["hospital_level"] == "optimal"
    assert case["department"] == "breast_surgery" and case["patient"]["mrn"] == UHID and case["patient"]["agesex"] == "46 Y / F"
    h = case["his"]
    assert h["uhid"] == UHID and h["matched_on"] == {"kind": "uhid", "value": UHID} and h["window"] == {"months": 12} and h["window_start"]
    assert [s["uhid"] for s in h["similar"]] == ["VXH/T/26/00412"] and h["similar"][0]["linked"] is False and h["linked"] == []
    assert [e["number"] for e in h["encounters"]] == ["OP/26/118701", "IP/26/01871"] and h["watermark"] == "2026-09-24T10:00:00+05:30"
    assert out["job"]["state"] == "finished" and out["job"]["his"]["added"] == 2
    docs = {d["his"]["id"]: d for d in store.list_docs(case["case_id"])}
    hpe, ct = docs["p01-r04"], docs["p01-r02"]
    assert hpe["source"] == "his" and hpe["rel_path"] == "HIS/OP_26_118701/Histopathology_report_v1.txt" and hpe["department"] == "pathology"
    assert hpe["his"]["accession"] == "PATH/26/00411" and hpe["his"]["encounter_number"] == "OP/26/118701" and hpe["his"]["signature"]["verification_status"] == "verified"
    assert hpe["state"] == "ready" and hpe["classification"]["status"] == "FINAL" and hpe["classification"]["signed"] == "yes" and hpe["classification"]["signed_source"] == "his"
    assert hpe["identity"] == "match" and hpe["facts"]["histologic_type"]["verification"] == "verified"
    assert ct["department"] == "radiology" and ct["classification"]["status"] == "PRELIMINARY" and ct["classification"]["signed"] == "no" and "superseded" not in ct
    au = [e["kind"] for e in store.read_audit(case["case_id"])]
    assert "case_created" in au and "his_fetch" in au and au.count("document_added") == 2
    created = next(e for e in store.read_audit(case["case_id"]) if e["kind"] == "case_created")
    assert created["from_his"]["uhid"] == UHID and created["from_his"]["similar"] == ["VXH/T/26/00412"] and created["owner"] == "breast_surgery"
    g = store.get_state(case["case_id"])["gate"]
    st = {r["id"]: r for r in g["requirements"]}
    assert st["histopathology"]["status"] == "satisfied" and st["histopathology"]["accession"] == "PATH/26/00411"
    assert st["clinical_history"]["status"] == "missing_record" and st["clinical_history"]["department"] == "Breast Surgery"  # route: owner -> the owning department
    # the view
    pub = his_case.public(store.get_case(case["case_id"]))
    assert pub["window_label"] == "last 12 months" and pub["unlinked"][0]["uhid"] == "VXH/T/26/00412" and "token" not in str(pub)
    groups = his_case.encounter_groups(store.get_case(case["case_id"]), store.list_docs(case["case_id"]))
    assert [g["key"] for g in groups] == ["IP/26/01871", "OP/26/118701"] and groups[1]["pre_admission"] is True and len(groups[1]["docs"]) == 2 and groups[0]["docs"] == []
    assert his_case.doc_view(hpe)["his"]["signed"] is True and his_case.doc_view(ct)["his"]["signed"] is False


def test_create_by_ip_or_op_number_resolves_to_the_uhid_and_needs_a_treating_department(fakes, monkeypatch):
    _use(monkeypatch, FakeHIS(_two_reports()))
    out = _create("IP/26/01871", case_id="TB-HIS-IP")
    assert out["case"]["his"]["uhid"] == UHID and out["case"]["his"]["matched_on"] == {"kind": "ip_no", "value": "IP/26/01871"}
    assert out["case"]["case_id"] == "TB-HIS-IP"
    out = _create("OP/26/118701")
    assert out["case"]["his"]["matched_on"]["kind"] == "op_no"
    with pytest.raises(his_case.HISCaseError) as e:
        _create("VXH/26/999999")
    assert e.value.status == 404
    with pytest.raises(his_case.HISCaseError) as e:  # a supporting doctor cannot own a Case File
        _create(roles={**ROLES_DOC, "treating": {}, "departments": {"radiology": "member"}})
    assert e.value.status == 403
    with pytest.raises(his_case.HISCaseError) as e:  # a supporting department can never own one
        _create(roles={**ROLES_DOC, "admin": True}, department="Radiology")
    assert "supporting" in str(e.value)
    out = _create(roles={**ROLES_DOC, "admin": True, "treating": {}}, department="Medical Oncology")  # a Vaidyx admin names the owner
    assert out["case"]["department"] == "medical_oncology"
    with pytest.raises(his_case.HISCaseError):  # the coordinator must name one
        _create(roles={**ROLES_DOC, "coordinator": True, "treating": {}})
    with pytest.raises(his_case.HISCaseError) as e:  # placed in two treating departments: choose
        _create(roles={**ROLES_DOC, "treating": {"breast_surgery": "member", "surgical_oncology": "member"}})
    assert "choose" in str(e.value).lower()
    with pytest.raises(his_case.HISCaseError) as e:
        _create("")
    assert e.value.status == 400


def test_his_down_is_a_plain_error_and_no_case_is_left_behind(fakes, monkeypatch):
    fake = _use(monkeypatch, FakeHIS(_two_reports()))
    fake.fail = True
    with pytest.raises(his_case.HISCaseError) as e:
        _create()
    assert e.value.status == 502 and store.list_cases() == []
    monkeypatch.setattr(his_client, "client", lambda: None)
    with pytest.raises(his_case.HISCaseError) as e:
        _create()
    assert e.value.status == 409 and "configured" in str(e.value)


def test_fetch_window_leaves_older_records_and_fetch_older_brings_them(fakes, monkeypatch):
    old = report("p01-r09", 1, "OPD note of last year", "clinical_note", "final", "OPD NOTE\nUHID : VXH/26/004201\nReport status: FINAL\n" + SIG["block"], sig=SIG,
                 encounter="OP/25/104211", accession="", dept="Breast Surgery", issued="2025-07-14T10:00:00+05:30", code=("11488-4", "Consult note"))
    _use(monkeypatch, FakeHIS(_two_reports() + [old]))
    out = _create(window={"months": 12})
    cid = out["case"]["case_id"]
    assert out["job"]["his"]["outside_window"] == 1 and out["case"]["his"]["older_available"] == 1 and len(store.list_docs(cid)) == 2
    job = _await(lambda: his_case.fetch_older(cid, {"all": True}, "dr.breast"))
    assert job["his"]["added"] == 1 and len(store.list_docs(cid)) == 3
    case = store.get_case(cid)
    assert case["his"]["window"] == {"all": True} and case["his"]["window_start"] == "" and case["his"]["older_available"] == 0
    assert any(e["kind"] == "his_window_widened" for e in store.read_audit(cid))
    with pytest.raises(his_case.HISCaseError):  # nothing older than everything
        _await(lambda: his_case.fetch_older(cid, {"months": 6}, "dr.breast"))


# ---- re-fetch (3.5) ---------------------------------------------------------------------------------------------------------

def test_refetch_brings_only_changed_versions_keeps_history_and_closes_the_request(fakes, monkeypatch):
    fake = _use(monkeypatch, FakeHIS(_two_reports(), orders=[]))
    out = _create()
    cid = out["case"]["case_id"]
    st = store.get_state(cid)
    open_before = [a for a in st["actions"] if a["status"] != "completed"]
    assert any(a["requirement"] == "histopathology" for a in st["actions"]) is False  # satisfied from the start
    # the radiologist signs on the RIS desk: a new version of the CT arrives final and signed; the HPE is unchanged
    signed = report("p01-r02", 2, "CECT thorax abdomen pelvis", "ct", "final", CT_TEXT.replace("Report status: PRELIMINARY\nReported by: Dr Junior Resident (preliminary, verification awaited)\n",
                    "Report status: FINAL\n" + SIG["block"] + "\n"), sig=SIG, accession="RAD/26/00981", dept="Radiology", issued="2026-10-01T09:00:00+05:30",
                    code=("18748-4", "Diagnostic imaging study"))
    fake.reports_by_patient[PAT["id"]][1]["current"] = False
    fake.reports_by_patient[PAT["id"]].append(signed)
    calls_before = len(fake.calls)
    job = _await(lambda: his_case.refetch(cid, "dr.breast"))
    assert job["his"]["reports"] == 1 and job["his"]["added"] == 1  # the delta: only the changed report
    assert ("reports", PAT["id"], "2026-09-24T10:00:00+05:30") in fake.calls[calls_before:]
    docs = sorted((d for d in store.list_docs(cid) if d["his"]["id"] == "p01-r02"), key=lambda d: d["his"]["version"])
    assert len(docs) == 2 and docs[0]["superseded"]["by_doc"] == docs[1]["doc_id"] and "superseded" not in docs[1]
    assert docs[1]["classification"]["status"] == "FINAL" and docs[1]["classification"]["signed"] == "yes"
    case = store.get_case(cid)
    assert case["his"]["watermark"] == "2026-10-01T09:00:00+05:30" and case["his"]["fetches"][-1]["reason"] == "refetch"
    g = store.get_state(cid)["gate"]
    assert docs[0]["doc_id"] in g["documents"]["superseded"] and docs[0]["doc_id"] not in g["documents"]["non_final"]
    assert any(e["kind"] == "his_refetch_checked" for e in store.read_audit(cid)) and job.get("refetch_result") is not None
    # the owning department hears about the re-fetch
    mine = notify.for_roles({"user": "dr.breast", "departments": {"breast_surgery": "member"}})
    assert any(n.get("refetch") and n["case_id"] == cid for n in mine)
    # a second re-fetch with nothing new adds nothing
    job2 = _await(lambda: his_case.refetch(cid, "dr.breast"))
    assert job2["his"]["added"] == 0 and len(store.list_docs(cid)) == 3


def test_refetch_needs_an_his_case(fakes, monkeypatch):
    _use(monkeypatch, FakeHIS(_two_reports()))
    store.create_case("TB-PLAIN", util.PATIENT, "breast", created_by="t")
    with pytest.raises(his_case.HISCaseError) as e:
        _await(lambda: his_case.refetch("TB-PLAIN", "x"))
    assert e.value.status == 409
    with pytest.raises(his_case.HISCaseError) as e:
        _await(lambda: his_case.refetch("TB-NONE", "x"))
    assert e.value.status == 404


# ---- linking a temporary registration (3.2) --------------------------------------------------------------------------------

def test_link_registration_is_a_person_action_and_labels_the_records(fakes, monkeypatch):
    temp_ct = report("pt-r01", 1, "CECT abdomen pelvis", "ct", "final", CT_TEXT.replace("VXH/26/004201", "VXH/T/26/00412").replace("Report status: PRELIMINARY", "Report status: FINAL"),
                     sig=SIG, accession="RAD/26/00997", dept="Radiology", encounter="OP/26/118712", code=("18748-4", "Diagnostic imaging study"))
    fake = _use(monkeypatch, FakeHIS(_two_reports(), similar=[TEMP], linked_reports={TEMP["id"]: [temp_ct]}))
    out = _create()
    cid = out["case"]["case_id"]
    assert len(store.list_docs(cid)) == 2  # never fetched automatically
    with pytest.raises(his_case.HISCaseError) as e:
        _await(lambda: his_case.link_registration(cid, "VXH/26/000000", "dr.breast"))
    assert e.value.status == 404
    job = _await(lambda: his_case.link_registration(cid, "VXH/T/26/00412", "dr.breast", "casualty registration of the same person"))
    assert job["his"]["added"] == 1
    case = store.get_case(cid)
    assert case["his"]["similar"][0]["linked"] is True and case["his"]["linked"][0]["uhid"] == "VXH/T/26/00412"
    assert {("uhid", "VXH/T/26/00412")} <= {(x["kind"], x["value"]) for x in case["patient"]["ids"]}
    d = next(d for d in store.list_docs(cid) if d["his"]["id"] == "pt-r01")
    assert d["his"]["registration"] == "VXH/T/26/00412" and d["rel_path"].startswith("HIS/VXH_T_26_00412/") and d["identity"] == "match"
    assert any(e["kind"] == "registration_linked" and e["uhid"] == "VXH/T/26/00412" for e in store.read_audit(cid))
    with pytest.raises(his_case.HISCaseError) as e:
        _await(lambda: his_case.link_registration(cid, "VXH/T/26/00412", "dr.breast"))
    assert e.value.status == 409


# ---- the gate over HIS records (3.3) ---------------------------------------------------------------------------------------

def _case_with(docs, protocol="unit", orders=None, his=True):
    store.create_case("TB-G", util.PATIENT, protocol, created_by="t")
    c = store.get_case("TB-G")
    if his:
        c["his"] = {"label": "Fake HIS", "orders": orders or [], "encounters": []}
    store.save_case(c)
    for d in docs:
        store.save_doc("TB-G", d)
    return "TB-G"


@pytest.fixture
def unit(monkeypatch):
    from tumour_board import protocol
    real = protocol.get
    monkeypatch.setattr(protocol, "get", lambda pid: util.unit_protocol() if pid == "unit" else real(pid))


def test_open_order_names_the_accession_and_turns_missing_values_into_pending(unit):
    hpe = util.make_doc("D1", "histopathology", facts={"histologic_type": util.fact("Adenocarcinoma")})
    hpe["his"] = {"id": "r1", "version": 1, "accession": "PATH/26/00450", "status": "final"}
    order = {"id": "o1", "accession": "PATH/26/00451", "test": "Molecular panel (EGFR, ALK, ROS1, MET)", "doc_type": "molecular", "status": "active", "stage": "sample_collected",
             "scheduled_for": None, "authored_on": "2026-09-17", "specimen": {"collected": "2026-09-17T10:00:00+05:30", "barcode": "VXS1"}, "performer_department": "Pathology"}
    ct_order = {"id": "o2", "accession": "RAD/26/01000", "test": "CECT thorax", "doc_type": "ct", "status": "active", "stage": "scheduled", "scheduled_for": "2026-10-20", "performer_department": "Radiology"}
    cid = _case_with([hpe], orders=[order, ct_order])
    g = rules.evaluate(cid)
    r = {x["id"]: x for x in g["requirements"]}
    assert r["histopathology"]["status"] == "satisfied" and r["histopathology"]["accession"] == "PATH/26/00450"
    # pdl1 (facts only; the unit protocol allows histopathology / ihc carriers): the molecular order does not carry it, so it stays undocumented
    assert r["pdl1"]["status"] == "missing_field" and "pending_order" not in r["pdl1"]
    # the CT is missing and the HIS holds a scheduled order for it: Level 1 with the accession No.
    assert r["ct_thorax"]["status"] == "missing_record" and r["ct_thorax"]["level"] == 1 and r["ct_thorax"]["accession"] == "RAD/26/01000"
    assert r["ct_thorax"]["pending_order"]["stage"] == "scheduled" and r["ct_thorax"]["problems"][-1] == "Ordered in the HIS (RAD/26/01000): CECT thorax scheduled for 2026-10-20, no report yet"
    assert g["his"] == {"open_orders": 2, "source": "Fake HIS"}
    st = rules.sync_actions(cid, g)
    a = next(x for x in st["actions"] if x["requirement"] == "ct_thorax")
    assert a["accession"] == "RAD/26/01000" and a["pending_order"]["accession"] == "RAD/26/01000" and "RAD/26/01000" in a["what"]
    # a facts-only record whose carrier is final but whose values sit in a collected sample: pending at Level 2, not "not documented"
    prot = util.unit_protocol()
    prot["mandatory"].append({"id": "driver", "label": "Driver mutations", "facts_only": True, "fact_doc_types": ["molecular", "histopathology"], "department": "Pathology",
                              "required_facts": ["egfr", "alk"], "sla_days": 7})
    from tumour_board import protocol
    real = protocol.get
    protocol.get = lambda pid: prot if pid == "unit" else real(pid)
    try:
        g = rules.evaluate(cid)
    finally:
        protocol.get = real
    d = next(x for x in g["requirements"] if x["id"] == "driver")
    assert d["status"] == "missing_field" and d["level"] == 2 and d["accession"] == "PATH/26/00451" and d["pending_from_order"] is True
    assert d["problems"] == ["Pending: EGFR, ALK: sample collected on 2026-09-17 (PATH/26/00451): Molecular panel (EGFR, ALK, ROS1, MET), result awaited in the HIS"]
    assert d["level2"]["problems"] == d["problems"]


def test_cancelled_order_and_cancelled_report_are_level_one_gaps_with_the_accession(unit):
    ct = util.make_doc("D2", "ct", status="CANCELLED", signed="no", title="CECT THORAX")
    ct["his"] = {"id": "r2", "version": 1, "accession": "RAD/26/01000", "status": "cancelled"}
    cid = _case_with([ct], orders=[{"id": "o2", "accession": "RAD/26/01000", "test": "CECT thorax", "doc_type": "ct", "status": "revoked", "stage": "cancelled", "note": "Cancelled: patient did not attend"}])
    g = rules.evaluate(cid)
    r = next(x for x in g["requirements"] if x["id"] == "ct_thorax")
    assert r["status"] == "not_final" and r["level"] == 1 and r["accession"] == "RAD/26/01000"
    assert r["problems"][-1] == "Order cancelled in the HIS (RAD/26/01000): CECT thorax; Cancelled: patient did not attend"


def test_superseded_version_is_history_not_a_gate_document(unit):
    v1 = util.make_doc("D1", "histopathology", date="2026-09-03", facts={"histologic_type": util.fact("Carcinoma, favour adenocarcinoma")})
    v1["his"] = {"id": "r1", "version": 1, "status": "final"}; v1["superseded"] = {"by_doc": "D2", "version": 2, "at": "x"}
    v2 = util.make_doc("D2", "histopathology", status="AMENDED", date="2026-09-16", facts={"histologic_type": util.fact("Adenocarcinoma")})
    v2["his"] = {"id": "r1", "version": 2, "status": "amended"}
    cid = _case_with([v1, v2])
    g = rules.evaluate(cid)
    r = next(x for x in g["requirements"] if x["id"] == "histopathology")
    assert r["status"] == "satisfied" and r["evidence"][0]["doc_id"] == "D2" and g["documents"]["superseded"] == ["D1"]
    assert g["documents"]["total"] == 2 and g["documents"]["ready"] == 1  # the gate reads the current version only; the history stays in the Case File
    facts = rules.resolve_facts(rules.case_docs(cid))
    assert facts["histologic_type"]["current"]["doc_id"] == "D2" and [h["doc_id"] for h in facts["histologic_type"]["history"]] == ["D1", "D2"]  # history kept
    # a superseded version that was the only one would leave the record missing, never satisfied by history
    store.delete_document(cid, "D2")
    g = rules.evaluate(cid)
    assert next(x for x in g["requirements"] if x["id"] == "histopathology")["status"] == "missing_record"


def test_outside_report_matched_by_name_only_needs_the_doctor_to_confirm_the_patient(unit):
    out = util.make_doc("D1", "histopathology", identity="name_match", facts={"histologic_type": util.fact("Adenocarcinoma")})
    out["outside"] = {"by": "dr.breast", "at": "2026-10-14T10:00:00"}
    cid = _case_with([out], his=True)
    g = rules.evaluate(cid)
    r = next(x for x in g["requirements"] if x["id"] == "histopathology")
    assert r["status"] == "needs_confirmation" and r["level"] == 1 and {"type": "confirm_match", "doc_id": "D1"} in r["needs"]
    assert r["problems"][0].startswith("Confirm the patient of") and g["documents"]["outside_unconfirmed"] == ["D1"]
    # the same at Level 2 for a facts-only record carried by the outside report
    g2 = rules.evaluate(cid)
    p = next(x for x in g2["requirements"] if x["id"] == "pdl1")
    assert p["status"] in ("missing_field", "needs_confirmation")
    # the treating doctor confirms: the record counts, the confirmation is overlaid (survives a re-process) and audited
    confirm.record(cid, "confirm_match", "D1", {"case_id": cid}, "patient confirmed by name, age and sex", "dr.breast")
    g = rules.evaluate(cid)
    r = next(x for x in g["requirements"] if x["id"] == "histopathology")
    assert r["status"] == "satisfied" and g["documents"]["outside_unconfirmed"] == []
    d = rules.case_docs(cid)[0]
    assert d["identity"] == "match" and d["identity_confirmed_by"] == "dr.breast" and d["model_identity"] == "name_match"
    # a conflicting printed identifier keeps its warning even after a filing confirmation (V1 behaviour)
    bad = util.make_doc("D3", "ct", identity="id_differs", title="CECT THORAX")
    store.save_doc(cid, bad)
    confirm.record(cid, "confirm_match", "D3", {"case_id": cid}, "", "coord")
    assert next(d for d in rules.case_docs(cid) if d["doc_id"] == "D3")["identity"] == "id_differs"
    # a plain upload (not an outside report) matched by name only is not asked for a confirmation (V1 behaviour)
    plain = util.make_doc("D4", "histopathology", identity="name_match", facts={"histologic_type": util.fact("Adenocarcinoma")})
    store.delete_document(cid, "D1"); store.save_doc(cid, plain)
    g = rules.evaluate(cid)
    assert next(x for x in g["requirements"] if x["id"] == "histopathology")["status"] == "satisfied"


def test_outside_upload_is_labelled_and_filed_under_outside(fakes, monkeypatch):
    _use(monkeypatch, FakeHIS(_two_reports()))
    out = _create()
    cid = out["case"]["case_id"]
    cea = ("Vaidyx Demo Diagnostics (SYNTHETIC)\nPrivate laboratory\nCEA REPORT\nName: Anitha Reddy  46 Y / F\nCEA 3.1 ng/mL\nReport status: FINAL\nVerified by Dr P. Lab, MD\n").encode()

    async def go():
        job = service.add_files(cid, [("cea_private_lab.txt", cea)], "dr.breast", outside=True)
        await job["task"]
        return job
    job = asyncio.run(go())
    d = next(d for d in store.list_docs(cid) if d.get("outside"))
    assert d["rel_path"] == "outside/cea_private_lab.txt" and d["outside"]["by"] == "dr.breast" and "his" not in d
    assert d["identity"] == "name_match"  # no hospital identifier printed: matched by name, age and sex; a person confirms
    ev = next(e for e in store.read_audit(cid) if e["kind"] == "document_added" and e.get("outside"))
    assert ev["file"] == "outside/cea_private_lab.txt"
    groups = his_case.encounter_groups(store.get_case(cid), store.list_docs(cid))
    assert groups[-1]["key"] == "outside" and groups[-1]["docs"] == [d["doc_id"]]


def test_summary_encounter_lines_and_his_points(fakes, monkeypatch):
    from tumour_board import summary
    _use(monkeypatch, FakeHIS(_two_reports()))
    out = _create()
    cid = out["case"]["case_id"]
    lines = summary.encounter_lines(cid)
    assert len(lines) == 1 and lines[0]["number"] == "OP/26/118701" and lines[0]["pre_admission"] is True and "[pre-admission OPD]" in lines[0]["text"]
    assert sorted(lines[0]["records"]) == sorted(["CECT THORAX ABDOMEN PELVIS", "HISTOPATHOLOGY REPORT"])
    d = next(d for d in store.list_docs(cid) if d["his"]["id"] == "p01-r04")
    d["his_flags"] = [{"fact": "histologic_type", "label": "Histologic type", "his_value": "x", "text_value": "y", "text": "HIS value differs from the report text: histologic type x vs y"}]
    store.save_doc(cid, d)
    pts = his_case.points(cid)
    assert len(pts) == 1 and pts[0]["kind"] == "his_mismatch" and pts[0]["doc_id"] == d["doc_id"] and "not shown as a fact" in pts[0]["text"]
    assert his_case.flags(cid)[0]["doc_title"] == "HISTOPATHOLOGY REPORT"
    from tumour_board import postboard
    tl = postboard.timeline(cid)
    enc = [e for e in tl if e["kind"] == "encounter"]
    assert [e["number"] for e in enc] == ["OP/26/118701", "IP/26/01871"] and enc[1]["ward_history"][0]["ward"] == "Surgical Ward 2"


def test_refetch_refreshes_a_known_version_whose_signature_arrived_without_a_new_version(fakes, monkeypatch):
    """A real HIS may attach the signature to the same report version (same DocumentReference): the re-fetch refreshes the document's
    HIS metadata, re-downloads the file when its bytes changed, reads it again and the gate re-checks (V2 item 3.5)."""
    unsigned = report("p11-r02", 1, "Histopathology report", "histopathology", "final", HPE_TEXT.replace(SIG["block"], "Signature pending"), sig=None,
                      issued="2026-09-05T11:00:00+05:30", last_updated="2026-09-05T11:00:00+05:30")
    fake = _use(monkeypatch, FakeHIS([unsigned]))
    out = _create()
    cid = out["case"]["case_id"]
    d = store.list_docs(cid)[0]
    assert d["classification"]["status"] == "FINAL" and d["classification"]["signed"] == "no" and any("no digital signature" in n for n in d["classification"]["status_notes"])
    g = store.get_state(cid)["gate"]; r = next(x for x in g["requirements"] if x["id"] == "histopathology")
    assert r["status"] == "not_final" and "no digital signature" in r["problems"][0]
    # the pathologist signs: the same version now carries a signature and a re-rendered PDF (new sha256)
    signed = {**unsigned, "signature": dict(SIG), "last_updated": "2026-10-01T09:00:00+05:30", "_text": HPE_TEXT, "document": {**unsigned["document"], "sha256": "re-rendered"}}
    fake.reports_by_patient[PAT["id"]] = [signed]
    job = _await(lambda: his_case.refetch(cid, "dr.breast"))
    assert job["his"]["reports"] == 1 and job["his"]["added"] == 0 and job["his"]["updated"] == 1 and job["total"] == 1
    docs = store.list_docs(cid)
    assert len(docs) == 1 and docs[0]["doc_id"] == d["doc_id"]
    d2 = docs[0]
    assert d2["his"]["signature"]["verification_status"] == "verified" and d2["his"]["refreshed_at"] and d2["his_document_sha256_before"] is not None
    assert d2["classification"]["status"] == "FINAL" and d2["classification"]["signed"] == "yes" and SIG["block"] in d2["pages"][0]["text"]
    assert next(x for x in store.get_state(cid)["gate"]["requirements"] if x["id"] == "histopathology")["status"] == "satisfied"
    assert any(e["kind"] == "document_updated_from_his" and e["doc_id"] == d["doc_id"] for e in store.read_audit(cid))
    # nothing changed: nothing refreshed
    job2 = _await(lambda: his_case.refetch(cid, "dr.breast"))
    assert job2["his"]["updated"] == 0 and job2["his"]["skipped"] == 1
