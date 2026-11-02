"""FHIR R4 read API of the mock hospital (plan item V2-1.3), in NRCeS (ABDM) FHIR IG v6.5.0 shapes. SYNTHETIC data only.

Pure builders turn store records into FHIR R4 resources (no HTTP needed; the conformance check and the Vaidyx-TB tests call
them), a small search engine answers the R4 search parameters below, and `router` (mounted by app.py at /fhir) serves them
read-only with the bearer token of app.require_token.

    patient(store, p)            encounter(store, e)           service_request(store, o)      specimen(store, s)
    diagnostic_report(store, r, version=None)                  observations(store, r, version=None)
    document_reference(store, r, version=None, files=None)     provenance(store, r, version=None)
    imaging_study(store, s)      media(store, s)               practitioner(store, p)
    organization(store)          department(store, d)          referral_request(store, e, i)
    composition(store, r, version)                             document_bundle(store, r, version=None, files=None)
    everything(store, files=None)                              every resource the API serves

Ids are the store ids (`vxh-26-004201`, `op-26-118701`, `rad-26-00981`, report ids as they are). Derived resources:
Observation `obs-<report>-v<n>-<key>`, DocumentReference `doc-<report>-v<n>` (one per report version: `current` for the
latest, `superseded` for earlier ones), Provenance = the signature id `sig-<report>-v<n>`, Media `media-<imaging study id>`,
referral ServiceRequest `ref-<encounter id>-<n>`, Composition `comp-<report>-v<n>`, DocumentBundle `docbundle-<report>-v<n>`.
DiagnosticReport is versioned: `meta.versionId` = the report version number, `/_history` lists every version.

Clinical notes, referral notes and discharge summaries are not DiagnosticReports: they are served as DocumentReference only
and their DocumentBundle's Composition section holds only the DocumentReference.

The invariant (project rules): structured values here (Observations, conclusions) are candidates; Vaidyx-TB checks them against
the report text, and the PDF wins. Identifier systems are synthetic (`https://his.vaidyx-demo.invalid/...`); the only real
ABDM URI is the ABHA number system, with sandbox numbers. Never an Aadhaar number.
"""
import base64
import copy
import hashlib
import re
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from . import documents, hl7, ids
from .app import NAME, VERSION, Hospital, require_token
from .dicom_studies import viewer_url
from .ids import iso, parse_time
from .model import IMAGING_MODALITY

# ------------------------------------------------------------------------ systems and codes
FHIR_VERSION = "4.0.1"
NRCES = "https://nrces.in/ndhm/fhir/r4/StructureDefinition/"
DEMO = "https://his.vaidyx-demo.invalid"
SYS = {
    "uhid": DEMO + "/identifier/uhid",
    "ip_no": DEMO + "/identifier/ip-no",
    "op_no": DEMO + "/identifier/op-no",
    "accession": DEMO + "/identifier/accession",
    "sample_barcode": DEMO + "/identifier/sample-barcode",
    "block_no": DEMO + "/identifier/block-no",
    "reg_no": DEMO + "/identifier/reg-no",
    "facility": DEMO + "/identifier/facility",
    "department": DEMO + "/identifier/department",
    "pmjay": DEMO + "/identifier/pmjay-id",
    "document": DEMO + "/identifier/document",
    "bundle": DEMO + "/bundle",
    # ABHA: the real ABDM system URI with SANDBOX values only (99-2600-..., addresses ending @sbx)
    "abha": "https://healthid.ndhm.gov.in",
    "abha_address": DEMO + "/identifier/abha-address",   # invented path: never under the real ABDM domain
    "dicom_uid": "urn:dicom:uid",
}
EXT = {
    "pmjay_preauth": DEMO + "/StructureDefinition/pmjay-preauth",
    "document_sha256": DEMO + "/StructureDefinition/document-sha256",
    "signature_ca": DEMO + "/StructureDefinition/signature-ca",
    "signature_serial": DEMO + "/StructureDefinition/signature-certificate-serial",
    "signature_hash": DEMO + "/StructureDefinition/signature-document-hash",
    "signature_status": DEMO + "/StructureDefinition/signature-verification-status",
    "viewer_url": DEMO + "/StructureDefinition/viewer-url",
    "dicomweb_url": DEMO + "/StructureDefinition/dicomweb-study-url",
}
SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"
NDHM_ID_TYPE = "https://nrces.in/ndhm/fhir/r4/CodeSystem/ndhm-identifier-type-code"
ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
PARTICIPATION = "http://terminology.hl7.org/CodeSystem/v3-ParticipationType"
PROVENANCE_TYPE = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"
SIGNATURE_TYPE = "urn:iso-astm:E1762-95:2013"
OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
DCM = "http://dicom.nema.org/resources/ontology/DCM"
MEDIA_TYPE = "http://terminology.hl7.org/CodeSystem/media-type"
ACT_REASON = "http://terminology.hl7.org/CodeSystem/v3-ActReason"
# every resource is tagged as test data (HL7 v3 ActReason HTEST), on top of the SYNTHETIC markers in names
SYNTHETIC_TAG = {"system": ACT_REASON, "code": "HTEST", "display": "test health data"}
ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "fhir.his-mock.vaidyx-demo.invalid")

ID_TYPES = {
    "MR": (V2_0203, "Medical record number"),
    "VN": (V2_0203, "Visit number"),
    "ACSN": (V2_0203, "Accession ID"),
    "MD": (V2_0203, "Medical License number"),
    "PRN": (V2_0203, "Provider number"),
    "XX": (V2_0203, "Organization identifier"),
    "ABHA": (NDHM_ID_TYPE, "Ayushman Bharat Health Account (ABHA) ID"),
    # display not verified against the NRCeS CodeSystem page (research/prep_v2/nrces_profiles.md lists the code only)
    "PMJAY": (NDHM_ID_TYPE, "Pradhan Mantri Jan Arogya Yojana (PMJAY) ID"),
}

# NRCeS profile name per resource type (Provenance and Media have none: base R4)
PROFILED = {"Patient", "Encounter", "ServiceRequest", "Specimen", "Observation", "DocumentReference", "ImagingStudy",
            "Practitioner", "Organization"}

LAB_DOC_TYPES = {"lab", "histopathology", "ihc", "molecular", "cytology", "microbiology"}
IMAGING_DOC_TYPES = set(IMAGING_MODALITY) | {"endoscopy"}
NOTE_DOC_TYPES = {"clinical_note", "referral", "discharge_summary"}
PATHOLOGY_DOC_TYPES = {"histopathology", "ihc", "molecular", "cytology"}

# DiagnosticReport.code (LOINC). Generic codes where a specific one is not certain; displays are LOINC's.
REPORT_LOINC = {
    "cbc": ("58410-2", "CBC panel - Blood by Automated count"),
    "lft": ("24325-3", "Hepatic function 2000 panel - Serum or Plasma"),
    "rft": ("24362-6", "Renal function 2000 panel - Serum or Plasma"),
    "cea": ("2039-6", "Carcinoembryonic Ag [Mass/volume] in Serum or Plasma"),
    "viral_markers": ("18725-2", "Microbiology studies (set)"),
    # night-v3 item 2.11: the tumour markers carry the marker's own code; Vaidyx-TB's code tables do not map these to a document
    # type, so the report title ("Serum PSA (total)") decides there, as doc_type_keywords.json reads it
    "psa": ("2857-1", "Prostate specific Ag [Mass/volume] in Serum or Plasma"),
    "ca125_cea": ("10334-1", "Cancer Ag 125 [Units/volume] in Serum or Plasma"),
    "ldh": ("2532-0", "Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma"),
}
DOC_TYPE_LOINC = {
    "lab": ("18725-2", "Microbiology studies (set)"),            # only reached by an unknown lab test (see _report_code)
    "microbiology": ("18725-2", "Microbiology studies (set)"),
    "histopathology": ("11526-1", "Pathology study"),
    "ihc": ("11526-1", "Pathology study"),
    "molecular": ("11526-1", "Pathology study"),
    "cytology": ("11526-1", "Pathology study"),
    "endoscopy": ("18751-8", "Endoscopy study"),
    "clinical_note": ("11488-4", "Consult note"),
    "referral": ("57133-1", "Referral note"),
    "discharge_summary": ("18842-5", "Discharge summary"),
    **{t: ("18748-4", "Diagnostic imaging study") for t in IMAGING_MODALITY},
    # night-v3 item 2.11: without these the two fell back to "Pathology study", which Vaidyx-TB reads as histopathology; these
    # codes are not in its tables, so the report title decides ("2D echocardiography", "Pulmonary function test")
    "echocardiogram": ("34552-0", "Cardiac 2D echo panel"),
    "pulmonary_function": ("18759-1", "Spirometry study"),
}
PROCEDURE_DOC_TYPES = {"endoscopy", "echocardiogram", "pulmonary_function"}   # no SNOMED service category; Observations "procedure"
# DiagnosticReport.category (SNOMED service / specialty)
CAT_HAEMATOLOGY = ("708196005", "Hematology service")
CAT_CT = ("310128004", "Computerized tomography service")
CAT_RADIOLOGY = ("394914008", "Radiology")
CAT_PATHOLOGY = ("394595002", "Pathology")
# Composition section codes from the NRCeS ValueSet ndhm-diagnostic-report-type (research note, section 2)
SECTION_CODES = {
    "cbc": ("4321000179101", "Hematology report"),
    "lft": ("4311000179106", "Chemical pathology report"),
    "rft": ("4311000179106", "Chemical pathology report"),
    "cea": ("4311000179106", "Chemical pathology report"),
    "viral_markers": ("4341000179107", "Microbiology report"),
}
SECTION_BY_DOC_TYPE = {
    "lab": ("4241000179101", "Laboratory report"),
    "microbiology": ("4341000179107", "Microbiology report"),
    "histopathology": ("371528001", "Pathology report"), "ihc": ("371528001", "Pathology report"),
    "molecular": ("371528001", "Pathology report"), "cytology": ("371528001", "Pathology report"),
    "ct": ("4261000179100", "Computed tomography imaging report"),
    "mri": ("4251000179103", "Magnetic resonance imaging report"),
    "mammogram": ("4231000179109", "Mammography report"),
    "ultrasound": ("4221000179107", "Ultrasound imaging report"),
    "pet_ct": ("4271000179106", "Nuclear medicine report"), "bone_scan": ("4271000179106", "Nuclear medicine report"),
    "xray": ("371527006", "Radiology report"),
}
# ServiceRequest.code: SNOMED only where the code is certain; otherwise code.text alone
ORDER_SNOMED = {
    "cbc": ("26604007", "Complete blood count"),
    "lft": ("26958001", "Hepatic function panel"),
    "chest_xray": ("399208008", "Plain chest X-ray"),
    "mammogram": ("71651007", "Mammography"),
    "colonoscopy": ("73761001", "Colonoscopy"),
    "bronchoscopy": ("10847001", "Bronchoscopy"),
}
ORDER_SNOMED_BY_DOC_TYPE = {
    "ct": ("77477000", "Computerized axial tomography"),
    "mri": ("113091000", "Magnetic resonance imaging"),
    "ultrasound": ("16310003", "Ultrasonography"),
    "mammogram": ("71651007", "Mammography"),
}
ORDER_CATEGORY = {"lab": ("108252007", "Laboratory procedure"), "imaging": ("363679005", "Imaging")}
REFERRAL_CATEGORY = ("3457005", "Patient referral")
# Observation.code (LOINC) where the key is certain; otherwise code.text = the printed label, no coding
OBS_LOINC = {
    "haemoglobin": ("718-7", "Hemoglobin [Mass/volume] in Blood"),
    "wbc": ("6690-2", "Leukocytes [#/volume] in Blood by Automated count"),
    "platelets": ("777-3", "Platelets [#/volume] in Blood by Automated count"),
    "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma"),
    "bilirubin": ("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma"),
    "sgot": ("1920-8", "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
    "sgpt": ("1742-6", "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
    "cea": ("2039-6", "Carcinoembryonic Ag [Mass/volume] in Serum or Plasma"),
    "er": ("16112-5", "Estrogen receptor [Interpretation] in Tissue"),
    "pr": ("16113-3", "Progesterone receptor [Interpretation] in Tissue"),
    "her2": ("48676-1", "HER2 [Interpretation] in Tissue"),
    "psa": ("2857-1", "Prostate specific Ag [Mass/volume] in Serum or Plasma"),
    "ca125": ("10334-1", "Cancer Ag 125 [Units/volume] in Serum or Plasma"),
    "ldh": ("2532-0", "Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma"),
}
UCUM_UNITS = {"mg/dL", "ng/mL"}       # printed units that are certainly UCUM; others carry no system
SPECIMEN_TYPES = {"blood": ("119297000", "Blood specimen"), "tissue": ("119376003", "Tissue specimen")}

DR_STATUS = {"preliminary": "preliminary", "final": "final", "amended": "amended", "cancelled": "cancelled"}
COMPOSITION_STATUS = {"preliminary": "preliminary", "final": "final", "amended": "amended",
                      "cancelled": "entered-in-error"}
ORDER_STATUS = {"ordered": "active", "scheduled": "active", "sample_collected": "active", "completed": "completed",
                "cancelled": "revoked"}
IMAGING_STATUS = {"registered": "registered", "available": "available", "cancelled": "cancelled"}
MEDIA_STATUS = {"registered": "preparation", "available": "completed", "cancelled": "not-done"}

# Bundle entry order after the Composition (NRCeS example 01, extended)
BUNDLE_ORDER = ("Composition", "Patient", "Practitioner", "Organization", "DiagnosticReport", "Observation", "Specimen",
                "ServiceRequest", "ImagingStudy", "Media", "DocumentReference", "Provenance", "Encounter")
TYPES = ("Patient", "Encounter", "ServiceRequest", "Specimen", "DiagnosticReport", "Observation", "DocumentReference",
         "Provenance", "ImagingStudy", "Media", "Practitioner", "Organization")


# ------------------------------------------------------------------------ small helpers
def ref(rtype, rid, display=None):
    r = {"reference": f"{rtype}/{rid}"}
    if display:
        r["display"] = display
    return r


def coding(system, code, display):
    return {"system": system, "code": code, "display": display}


def concept(system, code, display, text=None):
    c = {"coding": [coding(system, code, display)]}
    if text:
        c["text"] = text
    return c


def id_type(code):
    system, display = ID_TYPES[code]
    return {"coding": [coding(system, code, display)]}


def identifier(system_key, value, type_code=None, use=None, text=None):
    i = {}
    if use:
        i["use"] = use
    if type_code:
        i["type"] = id_type(type_code)
        if text:
            i["type"]["text"] = text
    elif text:
        i["type"] = {"text": text}
    i["system"] = SYS[system_key]
    i["value"] = value
    return i


def meta(last_updated, profile=None, version_id=None):
    m = {}
    if version_id is not None:
        m["versionId"] = str(version_id)
    m["lastUpdated"] = iso(last_updated)
    if profile:
        m["profile"] = [NRCES + profile]
    m["tag"] = [dict(SYNTHETIC_TAG)]
    return m


def fhir_id(value):
    """A FHIR id ([A-Za-z0-9-.]{1,64}) from a store key: underscores and spaces become hyphens."""
    return re.sub(r"[^A-Za-z0-9.\-]+", "-", str(value)).strip("-").lower()[:64]


def _built_at(store):
    return store.meta.get("built_at") or store.now()


def is_note(report):
    return report["doc_type"] in NOTE_DOC_TYPES


def is_diagnostic(report):
    return not is_note(report)


def report_profile(report):
    return "DiagnosticReportImaging" if report["doc_type"] in IMAGING_DOC_TYPES else "DiagnosticReportLab"


def _version(report, version=None):
    """A version dict from None (current), a number or a version dict."""
    if version is None:
        n = report["current_version"]
    elif isinstance(version, dict):
        return version
    else:
        n = int(version)
    v = next((v for v in report["versions"] if v["version"] == n), None)
    if v is None:
        raise KeyError(f"report {report['id']} has no version {n}")
    return v


def _is_current(report, v):
    return v["version"] == report["current_version"]


def _version_status(report, v):
    """preliminary / final / amended, or cancelled for the current version of a cancelled report."""
    if report.get("status") == "cancelled" and _is_current(report, v):
        return "cancelled"
    return v["status"]


def version_last_updated(report, v):
    """meta.lastUpdated of a report version: the report's for the current version, the version's own report time for
    earlier ones (when that version was written)."""
    if _is_current(report, v):
        return report["meta"]["lastUpdated"]
    return v["reported_on"]


def _superseded_at(report, v):
    """When an earlier version was replaced: the next version's report time."""
    nxt = next((x for x in report["versions"] if x["version"] == v["version"] + 1), None)
    return nxt["reported_on"] if nxt else version_last_updated(report, v)


def _signature(store, v):
    sid = v.get("signature_id")
    return store.signatures.get(sid) if sid else None


def _signer_id(store, v):
    sig = _signature(store, v)
    return sig["signer_id"] if sig else None


def _prac_ref(store, pid):
    p = store.practitioners.get(pid) if pid else None
    return ref("Practitioner", p["id"], p["name"]) if p else None


def _dept_ref(store, name):
    d = store.department(name)
    return ref("Organization", d["id"], d["name"]) if d else None


def _patient_ref(store, pid):
    p = store.patients.get(pid)
    return ref("Patient", pid, p["name"] if p else None)


def _encounter_ref(store, eid):
    e = store.encounters.get(eid)
    return ref("Encounter", eid, f"{e['kind']} {e['number']}" if e else None) if eid else None


def _hospital_ref(store):
    return ref("Organization", store.hospital["id"], store.hospital["name"])


def _set(d, key, value):
    if value not in (None, [], {}, ""):
        d[key] = value
    return d


def _b64(data):
    return base64.b64encode(data).decode("ascii")


@lru_cache(maxsize=256)
def _read_cached(path, mtime_ns, size):
    return Path(path).read_bytes()


def _document_bytes(files, v):
    """The PDF bytes of a version (None without files or a rendered document)."""
    path = ((v.get("document") or {}).get("path"))
    if not files or not path:
        return None
    p = Path(files["data_dir"]) / path
    try:
        st = p.stat()
    except OSError:
        return None
    return _read_cached(str(p), st.st_mtime_ns, st.st_size)


def _document_path(report, v):
    return (v.get("document") or {}).get("path") or f"documents/{report['id']}-v{v['version']}.pdf"


def label(key):
    return documents.label(key)


# ------------------------------------------------------------------------ Patient, Practitioner, Organization
def patient(store, p):
    """NRCeS Patient. UHID type MR (temporary registration: use temp; duplicate: use official, never linked), ABHA number
    and ABHA address (sandbox), PM-JAY ID. Never an Aadhaar number."""
    ident = [identifier("uhid", p["uhid"], "MR", use="temp" if p["registration_kind"] == "temporary" else "official")]
    abha = p.get("abha") or {}
    if abha.get("number"):
        ident.append(identifier("abha", abha["number"], "ABHA"))
    if abha.get("address"):
        # the ABHA address (PHR address); sandbox values end in @sbx
        ident.append(identifier("abha_address", abha["address"], "ABHA", text="ABHA address"))
    if p.get("pmjay_id"):
        ident.append(identifier("pmjay", p["pmjay_id"], "PMJAY"))
    res = {"resourceType": "Patient", "id": p["id"],
           "meta": meta(p["meta"]["lastUpdated"], "Patient"),
           "identifier": ident, "active": True,
           "name": [{"use": "official", "text": p["name"]}],
           "gender": {"F": "female", "M": "male"}.get(p["sex"], "unknown")}
    _set(res, "birthDate", p.get("dob_iso"))
    if p.get("phone"):
        res["telecom"] = [{"system": "phone", "value": p["phone"], "use": "mobile"}]
    a = p.get("address")
    if a:
        addr = {"use": "home", "type": "physical"}
        if a.get("line"):
            addr["line"] = [a["line"]]
        for src, dst in (("town", "city"), ("district", "district"), ("state", "state"), ("pin", "postalCode")):
            _set(addr, dst, a.get(src))
        addr["country"] = "IN"
        res["address"] = [addr]
    res["managingOrganization"] = _hospital_ref(store)
    ext = []
    if p.get("registration_kind") != "permanent":
        ext.append({"url": DEMO + "/StructureDefinition/registration-kind", "valueString": p["registration_kind"]})
    _set(res, "extension", ext)
    return res


def practitioner(store, p):
    """NRCeS Practitioner: the demo registration No. (VXREG-...) with type MD in a synthetic system (never the HPR)."""
    return {"resourceType": "Practitioner", "id": p["id"],
            "meta": meta(_built_at(store), "Practitioner"),
            "identifier": [identifier("reg_no", p["reg_no"], "MD")],
            "active": True,
            "name": [{"text": p["name"]}],
            "qualification": [{"code": {"text": p["qualification"]}}]}


def organization(store):
    """The hospital: NRCeS Organization, identifier type PRN, synthetic facility id VXDEMO."""
    h = store.hospital
    return {"resourceType": "Organization", "id": h["id"],
            "meta": meta(_built_at(store), "Organization"),
            "identifier": [identifier("facility", "VXDEMO", "PRN")],
            "active": True,
            "type": [{"text": "Hospital"}],
            "name": h["name"]}


def department(store, d):
    """A department: an Organization that is partOf the hospital; type.text treating / supporting."""
    res = {"resourceType": "Organization", "id": d["id"],
           "meta": meta(_built_at(store), "Organization"),
           "identifier": [identifier("department", d["code"], "XX")],
           "active": True,
           "type": [{"text": f"{d['group']} department"}],
           "name": d["name"],
           "partOf": _hospital_ref(store)}
    if d.get("email"):
        res["telecom"] = [{"system": "email", "value": d["email"], "use": "work"}]
    return res


# ------------------------------------------------------------------------ Encounter and referrals
def encounter(store, e):
    """NRCeS Encounter: OP visit (AMB) or IP admission (IMP) with IP / OP No. (type VN), ward / bed history as location[],
    the department as serviceProvider, the consultant as participant, PM-JAY pre-authorisation as an extension."""
    ip = e["kind"] == "IP"
    res = {"resourceType": "Encounter", "id": e["id"],
           "meta": meta(e["meta"]["lastUpdated"], "Encounter"),
           "identifier": [identifier("ip_no" if ip else "op_no", e["number"], "VN")],
           "status": e["status"],
           "class": coding(ACT_CODE, "IMP", "inpatient encounter") if ip else coding(ACT_CODE, "AMB", "ambulatory"),
           "serviceType": {"text": f"{e['department']}, {e['unit']}" if e.get("unit") else e["department"]},
           "subject": _patient_ref(store, e["patient_id"])}
    prac = _prac_ref(store, e.get("consultant_id"))
    if prac:
        res["participant"] = [{"type": [concept(PARTICIPATION, "ATND", "attender")], "individual": prac}]
    discharged = _discharge_time(store, e) if ip else None
    if ip:
        period = {"start": e["ward_history"][0]["from"] if e["ward_history"] else e["admitted"]}
        _set(period, "end", discharged)
    else:
        period = {"start": e["date"]}
    res["period"] = period
    if ip and e["ward_history"]:
        locs = []
        rows = e["ward_history"]
        for i, row in enumerate(rows):
            last = i == len(rows) - 1
            per = {"start": row["from"]}
            if not last:
                per["end"] = rows[i + 1]["from"]
            elif discharged:
                per["end"] = discharged
            loc = {"location": {"display": f"{row['ward']}, bed {row['bed']}"},
                   "status": "active" if last and e["status"] == "in-progress" else "completed",
                   "period": per}
            if row.get("reason"):
                loc["extension"] = [{"url": DEMO + "/StructureDefinition/transfer-reason", "valueString": row["reason"]}]
            locs.append(loc)
        res["location"] = locs
    _set(res, "serviceProvider", _dept_ref(store, e["department"]))
    pre = e.get("pmjay_preauth")
    if pre:
        sub = [{"url": "status", "valueCodeableConcept": {"text": pre["status"]}}]
        if pre.get("date"):
            sub.append({"url": "date", "valueDate": pre["date"]})
        res["extension"] = [{"url": EXT["pmjay_preauth"], "extension": sub}]
    return res


def _discharge_time(store, e):
    """The discharge instant (the ADT A03 event), else the discharge date; None while admitted."""
    if not e.get("discharged"):
        return None
    t = next((ev["time"] for ev in reversed(store.events)
              if ev["trigger"] == "A03" and ev["refs"].get("encounter_id") == e["id"]), None)
    return t or e["discharged"]


def referral_id(e, i):
    return f"ref-{e['id']}-{i + 1}"


def referral_request(store, e, i):
    """Entry i of encounter['referrals'] as a ServiceRequest: category SNOMED 3457005 Patient referral, requester the
    referring department, performer the department referred to; active while requested, completed once accepted."""
    r = e["referrals"][i]
    res = {"resourceType": "ServiceRequest", "id": referral_id(e, i),
           "meta": meta(e["meta"]["lastUpdated"], "ServiceRequest"),
           "status": "completed" if r["status"] == "accepted" else "active",
           "intent": "order",
           "category": [concept(SNOMED, *REFERRAL_CATEGORY)],
           "code": {"text": f"Referral to {r['to']}"},
           "subject": _patient_ref(store, e["patient_id"]),
           "encounter": _encounter_ref(store, e["id"]),
           "authoredOn": r["on"],
           "requester": _dept_ref(store, r["from"]),
           "performer": [_dept_ref(store, r["to"])],
           "reasonCode": [{"text": r["reason"]}]}
    if r.get("accepted_on"):
        res["extension"] = [{"url": DEMO + "/StructureDefinition/referral-accepted-on", "valueDate": r["accepted_on"]}]
    return res


def referrals(store, e):
    return [referral_request(store, e, i) for i in range(len(e.get("referrals") or []))]


# ------------------------------------------------------------------------ orders and specimens
def _order_kind(o):
    if o["doc_type"] in IMAGING_MODALITY:
        return "imaging"
    if o["doc_type"] in LAB_DOC_TYPES:
        return "lab"
    return None


def service_request(store, o):
    """NRCeS ServiceRequest: an order with its accession No. (type ACSN), requester the ordering department, performer
    the performing department; active while ordered / scheduled / sample collected, completed, revoked when cancelled."""
    res = {"resourceType": "ServiceRequest", "id": o["id"],
           "meta": meta(o["meta"]["lastUpdated"], "ServiceRequest")}
    if o.get("accession"):
        res["identifier"] = [identifier("accession", o["accession"], "ACSN")]
    res["status"] = ORDER_STATUS[o["status"]]
    rep = store.report_for_order(o["id"])
    if res["status"] == "completed" and rep and rep["status"] == "preliminary":
        res["status"] = "active"   # results in progress: the order completes with the signed report
    res["intent"] = "order"
    kind = _order_kind(o)
    if kind:
        res["category"] = [concept(SNOMED, *ORDER_CATEGORY[kind])]
    code = ORDER_SNOMED.get(o["test"]) or ORDER_SNOMED_BY_DOC_TYPE.get(o["doc_type"])
    res["code"] = concept(SNOMED, *code, text=o["label"]) if code else {"text": o["label"]}
    res["subject"] = _patient_ref(store, o["patient_id"])
    res["encounter"] = _encounter_ref(store, o["encounter_id"])
    res["occurrenceDateTime"] = o.get("scheduled_for")
    res["authoredOn"] = o["ordered_on"]
    res["requester"] = _dept_ref(store, o["ordering_department"])
    res["performer"] = [_dept_ref(store, o["performing_department"])]
    if o.get("specimen_id"):
        res["specimen"] = [ref("Specimen", o["specimen_id"])]
    if o["status"] == "cancelled" and o.get("cancel_reason"):
        res["note"] = [{"text": f"Cancelled: {o['cancel_reason']}"}]
    return {k: v for k, v in res.items() if v is not None}


def specimen(store, s):
    """NRCeS Specimen: barcode as accessionIdentifier, block No. as identifier, SNOMED type, received and collected times."""
    o = store.orders.get(s["order_id"]) or {}
    res = {"resourceType": "Specimen", "id": s["id"],
           "meta": meta(s["meta"]["lastUpdated"], "Specimen")}
    if s.get("block_no"):
        res["identifier"] = [identifier("block_no", s["block_no"], text="Block No.")]
    res["accessionIdentifier"] = identifier("sample_barcode", s["barcode"], text="Sample barcode")
    res["status"] = s.get("status") or "available"
    res["type"] = concept(SNOMED, *SPECIMEN_TYPES[s["type"]])
    res["subject"] = _patient_ref(store, s["patient_id"])
    res["receivedTime"] = s["received_on"]
    res["request"] = [ref("ServiceRequest", s["order_id"], o.get("label"))]
    res["collection"] = {"collectedDateTime": s["collected_on"]}
    return res


# ------------------------------------------------------------------------ imaging
def dicomweb_url(study_uid):
    """DICOMweb study URL relative to the PACS (Orthanc); Vaidyx-TB proxies it (plan 6.3)."""
    return f"/dicom-web/studies/{study_uid}"


def imaging_study(store, s):
    """NRCeS ImagingStudy: Study UID (urn:dicom:uid) and accession, series and instances as Orthanc holds them, and the
    OHIF viewer / DICOMweb URLs as extensions (humans view the images; no model reads them)."""
    o = store.orders.get(s["order_id"]) or {}
    ident = [{"system": SYS["dicom_uid"], "value": "urn:oid:" + s["study_uid"]}]
    if s.get("accession"):
        ident.append(identifier("accession", s["accession"], "ACSN"))
    res = {"resourceType": "ImagingStudy", "id": s["id"],
           "meta": meta(s["meta"]["lastUpdated"], "ImagingStudy"),
           "identifier": ident,
           "status": IMAGING_STATUS.get(s["status"], "unknown"),
           "modality": [coding(DCM, s["modality"], s["modality"])],
           "subject": _patient_ref(store, s["patient_id"])}
    _set(res, "encounter", _encounter_ref(store, o.get("encounter_id")))
    _set(res, "started", s.get("started"))
    res["basedOn"] = [ref("ServiceRequest", s["order_id"], o.get("label"))]
    res["numberOfSeries"] = int(s.get("number_of_series") or 0)
    res["numberOfInstances"] = int(s.get("number_of_instances") or 0)
    _set(res, "description", s.get("description"))
    series = []
    for se in s.get("series") or []:
        series.append({"uid": se["uid"], "number": se["number"], "modality": coding(DCM, se["modality"], se["modality"]),
                       "numberOfInstances": len(se.get("instances") or []),
                       "instance": [{"uid": i["uid"], "sopClass": {"system": "urn:ietf:rfc:3986",
                                                                   "code": "urn:oid:" + i["sop_class"]},
                                     "number": i["number"]} for i in se.get("instances") or []]})
    _set(res, "series", series)
    ext = []
    if s["status"] == "available":        # in the PACS: the viewer opens it
        ext.append({"url": EXT["viewer_url"], "valueUrl": viewer_url(s["study_uid"])})
    if has_images(s):                     # images exist (built; uploaded when available)
        ext.append({"url": EXT["dicomweb_url"], "valueUrl": dicomweb_url(s["study_uid"])})
    _set(res, "extension", ext or None)
    return res


def has_images(study):
    """True when the study's synthetic images exist (series built), whether or not they are in the PACS yet."""
    return bool(study.get("series")) and study.get("status") != "cancelled"


def media_id(s):
    return "media-" + s["id"]


def media(store, s):
    """Media (base R4; NRCeS has no Media profile of its own): the study's images as one DICOMweb link, so that
    DiagnosticReportImaging.media (1..*) points at something real."""
    o = store.orders.get(s["order_id"]) or {}
    res = {"resourceType": "Media", "id": media_id(s),
           "meta": meta(s["meta"]["lastUpdated"]),
           "basedOn": [ref("ServiceRequest", s["order_id"], o.get("label"))],
           "status": MEDIA_STATUS.get(s["status"], "unknown"),
           "type": concept(MEDIA_TYPE, "image", "Image"),
           "modality": {"coding": [coding(DCM, s["modality"], s["modality"])]},
           "subject": _patient_ref(store, s["patient_id"])}
    _set(res, "encounter", _encounter_ref(store, o.get("encounter_id")))
    res["content"] = {"contentType": "application/dicom", "url": dicomweb_url(s["study_uid"]),
                      "title": s.get("description") or "Imaging study"}
    return res


# ------------------------------------------------------------------------ reports
def _report_code(report):
    c = REPORT_LOINC.get(report["test"]) or DOC_TYPE_LOINC.get(report["doc_type"]) or ("11526-1", "Pathology study")
    return concept(LOINC, *c, text=report["title"])


def _report_category(report):
    t = report["doc_type"]
    if report["test"] == "cbc":
        c = CAT_HAEMATOLOGY
    elif t == "ct":
        c = CAT_CT
    elif t in IMAGING_MODALITY:
        c = CAT_RADIOLOGY
    elif t in PROCEDURE_DOC_TYPES:
        c = None
    else:
        c = CAT_PATHOLOGY
    return [concept(SNOMED, *c)] if c else []


def _observation_category(report):
    t = report["doc_type"]
    if t in IMAGING_MODALITY:
        return concept(OBS_CATEGORY, "imaging", "Imaging")
    if t in PROCEDURE_DOC_TYPES:
        return concept(OBS_CATEGORY, "procedure", "Procedure")
    return concept(OBS_CATEGORY, "laboratory", "Laboratory")


def _effective(store, report):
    o = store.orders.get(report["order_id"]) or {}
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    if spec:
        return spec["collected_on"]
    study = store.imaging_study_for(o["id"]) if o else None
    if study and study.get("started"):
        return study["started"]
    return o.get("scheduled_for") or o.get("ordered_on")


def conclusion(report, v):
    """The Impression / Diagnosis values of the version as printed (keys the PDF prints under Impression or Diagnosis), else
    the report title."""
    vals = documents.printed_values(report, v)
    keys = [k for k in vals if documents.IMPRESSION_KEY.search(k)]
    if not keys and report["doc_type"] in PATHOLOGY_DOC_TYPES:
        keys = [k for k in vals if k in documents.HPE_DIAGNOSIS_KEYS]
    return "; ".join(str(vals[k]) for k in keys) if keys else "See report"


def observation_id(report, v, key):
    return fhir_id(f"obs-{report['id']}-v{v['version']}-{key}")


_QUANTITY = re.compile(r"^([<>]=?)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*([^\s\d][^\s]*))?$")


def quantity(text):
    """A printed `number unit` string as a FHIR Quantity (unit kept as printed; UCUM system only for units certain to be
    UCUM), or None when it is not a plain number with at most one unit token."""
    m = _QUANTITY.match(str(text).strip())
    if not m:
        return None
    comparator, number, unit = m.groups()
    raw = number.replace(",", "")
    q = {"value": float(raw) if "." in raw else int(raw)}
    if comparator:
        q["comparator"] = comparator
    if unit:
        q["unit"] = unit
        if unit in UCUM_UNITS:
            q["system"], q["code"] = UCUM, unit
    return q


def observations(store, r, version=None):
    """One NRCeS Observation per printed value of the version (omitted values get none). `observation_values` override
    the printed value in the Observation only (the HIS disagrees with its own PDF). Candidates: the PDF text wins."""
    if is_note(r):
        return []
    v = _version(r, version)
    status = {"cancelled": "cancelled"}.get(_version_status(r, v), v["status"])
    o = store.orders.get(r["order_id"]) or {}
    spec = o.get("specimen_id")
    vals = documents.printed_values(r, v)
    over = r.get("observation_values") or {}
    out = []
    for key, printed in vals.items():
        value = over.get(key, printed)
        code = {"coding": [coding(LOINC, *OBS_LOINC[key])], "text": label(key)} if key in OBS_LOINC else {"text": label(key)}
        res = {"resourceType": "Observation", "id": observation_id(r, v, key),
               "meta": meta(version_last_updated(r, v), "Observation", version_id=v["version"]),
               "status": status,
               "category": [_observation_category(r)],
               "code": code,
               "subject": _patient_ref(store, r["patient_id"]),
               "encounter": _encounter_ref(store, r["encounter_id"]),
               "effectiveDateTime": _effective(store, r),
               "issued": v["reported_on"],
               "performer": [x for x in (_prac_ref(store, v.get("reported_by")),
                                         _dept_ref(store, o.get("performing_department"))) if x]}
        q = quantity(value)
        if q:
            res["valueQuantity"] = q
        else:
            res["valueString"] = str(value)
        if spec:
            res["specimen"] = ref("Specimen", spec)
        out.append({k: x for k, x in res.items() if x is not None})
    return out


def diagnostic_report(store, r, version=None, files=None):
    """NRCeS DiagnosticReportLab / DiagnosticReportImaging for one version (default: the current one). Notes are not
    DiagnosticReports (None). `presentedForm` carries the PDF when it is rendered and `files` is given."""
    if is_note(r):
        return None
    v = _version(r, version)
    o = store.orders.get(r["order_id"]) or {}
    res = {"resourceType": "DiagnosticReport", "id": r["id"],
           "meta": meta(version_last_updated(r, v), report_profile(r), version_id=v["version"])}
    if o.get("accession"):
        res["identifier"] = [identifier("accession", o["accession"], "ACSN")]
    res["basedOn"] = [ref("ServiceRequest", o["id"], o.get("label"))] if o else None
    res["status"] = DR_STATUS[_version_status(r, v)]
    res["category"] = _report_category(r) or None
    res["code"] = _report_code(r)
    res["subject"] = _patient_ref(store, r["patient_id"])
    res["encounter"] = _encounter_ref(store, r["encounter_id"])
    res["effectiveDateTime"] = _effective(store, r)
    res["issued"] = iso(v["reported_on"])
    res["performer"] = [_dept_ref(store, o.get("performing_department"))] if o else None
    interp = _prac_ref(store, _signer_id(store, v) or v.get("reported_by"))
    res["resultsInterpreter"] = [interp] if interp else None
    if o.get("specimen_id"):
        res["specimen"] = [ref("Specimen", o["specimen_id"])]
    res["result"] = [ref("Observation", x["id"]) for x in observations(store, r, v)] or None
    study = store.imaging_study_for(o["id"]) if o else None
    if study:
        res["imagingStudy"] = [ref("ImagingStudy", study["id"])]
        if has_images(study):
            res["media"] = [{"link": ref("Media", media_id(study))}]
    res["conclusion"] = conclusion(r, v)
    data = _document_bytes(files, v)
    if data is not None:
        res["presentedForm"] = [{"contentType": "application/pdf", "data": _b64(data),
                                 "title": f"{r['title']} (version {v['version']})", "creation": iso(v["reported_on"])}]
    if v.get("amendment_note"):
        res["extension"] = [{"url": DEMO + "/StructureDefinition/amendment-note", "valueString": v["amendment_note"]}]
    return {k: x for k, x in res.items() if x is not None}


def document_reference_id(r, v):
    return f"doc-{r['id']}-v{v['version']}"


def document_reference(store, r, version=None, files=None):
    """NRCeS DocumentReference: the PDF of one report version. `status` current / superseded, `docStatus` from the version
    (cancelled: entered-in-error). The attachment always has `url` (/documents/<path>, token-protected); `data` (base64) and
    `hash` (base64 SHA-1, the R4 rule) only when the PDF is rendered and `files` is given. The store's sha256 rides in an
    extension."""
    v = _version(r, version)
    current = _is_current(r, v)
    o = store.orders.get(r["order_id"]) or {}
    path = _document_path(r, v)
    att = {"contentType": "application/pdf", "language": "en-IN"}
    data = _document_bytes(files, v)
    if data is not None:
        att["data"] = _b64(data)
    att["url"] = "/documents/" + path
    if data is not None:
        att["size"] = len(data)
        att["hash"] = _b64(hashlib.sha1(data).digest())
    att["title"] = f"{r['title']} (version {v['version']})"
    att["creation"] = iso(v["reported_on"])
    status = _version_status(r, v)
    res = {"resourceType": "DocumentReference", "id": document_reference_id(r, v),
           "meta": meta(version_last_updated(r, v) if current else _superseded_at(r, v), "DocumentReference",
                        version_id=v["version"])}
    sha = (v.get("document") or {}).get("sha256")
    if sha:
        res["extension"] = [{"url": EXT["document_sha256"], "valueString": sha}]
    res["masterIdentifier"] = {"system": SYS["document"], "value": f"{r['id']}-v{v['version']}"}
    if o.get("accession"):
        res["identifier"] = [identifier("accession", o["accession"], "ACSN")]
    res["status"] = "entered-in-error" if v["status"] == "cancelled" else ("current" if current else "superseded")
    res["docStatus"] = COMPOSITION_STATUS[status]
    res["type"] = _report_code(r)
    res["subject"] = _patient_ref(store, r["patient_id"])
    res["date"] = iso(v["reported_on"])
    author = _prac_ref(store, v.get("reported_by"))
    res["author"] = [x for x in (author, _dept_ref(store, o.get("performing_department"))) if x]
    sig = _signature(store, v)
    if sig:
        res["authenticator"] = _prac_ref(store, sig["signer_id"])
    res["description"] = r["title"]
    res["content"] = [{"attachment": att}]
    ctx = {"encounter": [_encounter_ref(store, r["encounter_id"])]}
    if is_diagnostic(r):
        ctx["related"] = [ref("DiagnosticReport", r["id"])]
    res["context"] = ctx
    return res


def provenance(store, r, version=None):
    """Provenance (base R4: NRCeS v6.5.0 has no Provenance profile, so none is claimed) of a signed report version: the
    digital signature (block text, signer, time) with the demo CA, certificate serial, signed document hash and
    verification status as extensions. None for a version without a signature (preliminary, final never signed)."""
    v = _version(r, version)
    sig = _signature(store, v)
    if not sig:
        return None
    signer = _prac_ref(store, sig["signer_id"])
    o = store.orders.get(r["order_id"]) or {}
    targets = []
    if is_diagnostic(r):
        targets.append({"reference": f"DiagnosticReport/{r['id']}/_history/{v['version']}"})
    targets.append(ref("DocumentReference", document_reference_id(r, v)))
    ext = [{"url": EXT["signature_ca"], "valueString": sig["ca"]},
           {"url": EXT["signature_serial"], "valueString": sig["certificate_serial"]}]
    if sig.get("document_hash"):
        ext.append({"url": EXT["signature_hash"], "valueString": sig["document_hash"]})
    ext.append({"url": EXT["signature_status"], "valueCode": sig["verification_status"]})
    agent = {"type": concept(PROVENANCE_TYPE, "author", "Author"), "who": signer}
    dept = _dept_ref(store, o.get("performing_department"))
    if dept:
        agent["onBehalfOf"] = dept
    return {"resourceType": "Provenance", "id": sig["id"],
            "meta": meta(sig["signed_at"], version_id=v["version"]),
            "extension": ext,
            "target": targets,
            "recorded": iso(sig["signed_at"]),
            "agent": [agent],
            "signature": [{"type": [coding(SIGNATURE_TYPE, "1.2.840.10065.1.12.1.1", "Author's Signature")],
                           "when": iso(sig["signed_at"]), "who": signer, "sigFormat": "text/plain",
                           "data": _b64(sig["block"].encode("utf-8"))}]}


# ------------------------------------------------------------------------ Composition and DocumentBundle
def _section_code(report):
    c = SECTION_CODES.get(report["test"]) or SECTION_BY_DOC_TYPE.get(report["doc_type"])
    return concept(SNOMED, *c) if c else None


def composition(store, r, version=None):
    """NRCeS DiagnosticReportRecord: one section holding the DiagnosticReport and the DocumentReference (notes: only the
    DocumentReference)."""
    v = _version(r, version)
    status = _version_status(r, v)
    sig = _signature(store, v)
    entries = []
    if is_diagnostic(r):
        entries.append(ref("DiagnosticReport", r["id"]))
    entries.append(ref("DocumentReference", document_reference_id(r, v)))
    section = {"title": r["title"]}
    _set(section, "code", _section_code(r))
    section["entry"] = entries
    author = _prac_ref(store, v.get("reported_by")) or _dept_ref(store, (store.orders.get(r["order_id"]) or {})
                                                                  .get("performing_department"))
    res = {"resourceType": "Composition", "id": f"comp-{r['id']}-v{v['version']}",
           "meta": meta(version_last_updated(r, v), "DiagnosticReportRecord", version_id=v["version"]),
           "status": COMPOSITION_STATUS[status],
           "type": concept(SNOMED, "721981007", "Diagnostic studies report"),
           "subject": _patient_ref(store, r["patient_id"]),
           "encounter": _encounter_ref(store, r["encounter_id"]),
           "date": iso(v["reported_on"]),
           "author": [author],
           "title": r["title"]}
    if sig:
        res["attester"] = [{"mode": "legal", "time": iso(sig["signed_at"]), "party": _prac_ref(store, sig["signer_id"])}]
    res["custodian"] = _hospital_ref(store)
    res["section"] = [section]
    return res


def references(obj):
    """Every Reference.reference string inside a resource (recursively)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "reference" and isinstance(v, str):
                out.append(v)
            else:
                out.extend(references(v))
    elif isinstance(obj, list):
        for x in obj:
            out.extend(references(x))
    return out


_REF = re.compile(r"^([A-Z][A-Za-z]+)/([A-Za-z0-9.\-]{1,64})(?:/_history/([A-Za-z0-9.\-]+))?$")


def parse_reference(s):
    """'Type/id' or 'Type/id/_history/v' -> (type, id, version or None); None otherwise."""
    m = _REF.match(str(s))
    return m.groups() if m else None


BUNDLE_FULLURL_BASE = "https://his.vaidyx-demo.invalid/fhir"  # synthetic base of the entries' fullUrl


def document_bundle(store, r, version=None, files=None):
    """NRCeS DocumentBundle of one report version: Composition first, then every resource it references (directly or
    through other entries) in the NRCeS example order. References are `Type/id` and each one resolves to an entry."""
    v = _version(r, version)
    o = store.orders.get(r["order_id"]) or {}
    main = [composition(store, r, v)]
    dr = diagnostic_report(store, r, v, files)
    if dr:
        main.append(dr)
        main.extend(observations(store, r, v))
    if o.get("specimen_id") and o["specimen_id"] in store.specimens:
        main.append(specimen(store, store.specimens[o["specimen_id"]]))
    if o:
        main.append(service_request(store, o))
    study = store.imaging_study_for(o["id"]) if o else None
    if study:
        main.append(imaging_study(store, study))
        if has_images(study):
            main.append(media(store, study))
    main.append(document_reference(store, r, v, files))
    prov = provenance(store, r, v)
    if prov:
        main.append(prov)
    have = {(x["resourceType"], x["id"]): x for x in main}
    queue = list(main)
    while queue:
        res = queue.pop(0)
        for s in references(res):
            p = parse_reference(s)
            if not p or (p[0], p[1]) in have:
                continue
            got = read(store, p[0], p[1], files)
            if got is None:
                continue
            have[(p[0], p[1])] = got
            queue.append(got)
    order = {t: i for i, t in enumerate(BUNDLE_ORDER)}
    resources = sorted(have.values(), key=lambda x: order.get(x["resourceType"], len(order)))
    key = f"{r['id']}:{v['version']}"
    return {"resourceType": "Bundle", "id": f"docbundle-{r['id']}-v{v['version']}",
            "meta": meta(version_last_updated(r, v), "DocumentBundle", version_id=v["version"]),
            "identifier": {"system": SYS["bundle"], "value": str(uuid.uuid5(ID_NAMESPACE, key))},
            "type": "document",
            "timestamp": iso(v["reported_on"]),
            # absolute RESTful fullUrls (synthetic base), so the relative Type/id references inside the entries resolve
            # by the FHIR bundle resolution rules (a urn:uuid fullUrl would leave them unresolvable)
            "entry": [{"fullUrl": f"{BUNDLE_FULLURL_BASE}/{x['resourceType']}/{x['id']}", "resource": x}
                      for x in resources]}


# ------------------------------------------------------------------------ read and enumerate
def _find_version_resource(store, prefix, rid):
    """(report, version) for an id `<prefix>-<report id>-v<n>`."""
    if not rid.startswith(prefix + "-"):
        return None, None
    m = re.match(r"^(.+)-v(\d+)$", rid[len(prefix) + 1:])
    if not m:
        return None, None
    r = store.reports.get(m.group(1))
    if not r:
        return None, None
    v = next((x for x in r["versions"] if x["version"] == int(m.group(2))), None)
    return (r, v) if v else (None, None)


def read(store, rtype, rid, files=None):
    """One resource by type and id (DiagnosticReport: the current version), None when unknown."""
    if rtype == "Patient":
        p = store.patients.get(rid)
        return patient(store, p) if p else None
    if rtype == "Encounter":
        e = store.encounters.get(rid)
        return encounter(store, e) if e else None
    if rtype == "ServiceRequest":
        o = store.orders.get(rid)
        if o:
            return service_request(store, o)
        m = re.match(r"^ref-(.+)-(\d+)$", rid)
        e = store.encounters.get(m.group(1)) if m else None
        if e and 1 <= int(m.group(2)) <= len(e["referrals"]):
            return referral_request(store, e, int(m.group(2)) - 1)
        return None
    if rtype == "Specimen":
        s = store.specimens.get(rid)
        return specimen(store, s) if s else None
    if rtype == "ImagingStudy":
        s = store.imaging_studies.get(rid)
        return imaging_study(store, s) if s else None
    if rtype == "Media":
        s = store.imaging_studies.get(rid[len("media-"):]) if rid.startswith("media-") else None
        return media(store, s) if s else None
    if rtype == "Practitioner":
        p = store.practitioners.get(rid)
        return practitioner(store, p) if p else None
    if rtype == "Organization":
        if rid == store.hospital["id"]:
            return organization(store)
        d = store.departments.get(rid)
        return department(store, d) if d else None
    if rtype == "DiagnosticReport":
        r = store.reports.get(rid)
        return diagnostic_report(store, r, None, files) if r and is_diagnostic(r) else None
    if rtype == "DocumentReference":
        r, v = _find_version_resource(store, "doc", rid)
        return document_reference(store, r, v, files) if r else None
    if rtype == "Provenance":
        r, v = _find_version_resource(store, "sig", rid)
        return provenance(store, r, v) if r else None
    if rtype == "Observation":
        for r in store.reports.values():
            if not rid.startswith(fhir_id(f"obs-{r['id']}-v")) or is_note(r):
                continue
            for v in r["versions"]:
                for x in observations(store, r, v):
                    if x["id"] == rid:
                        return x
        return None
    return None


def report_versions(r):
    """Every version of a report, newest first."""
    return sorted(r["versions"], key=lambda v: -v["version"])


def _resources(store, rtype, files=None, patient_id=None, encounter_id=None):
    """Every resource of a type the API serves, as (resource, patient id, encounter id), optionally pre-filtered by
    registration and encounter (cheap; avoids building documents of other patients)."""
    def keep(pid, eid):
        return (not patient_id or pid == patient_id) and (not encounter_id or eid == encounter_id)

    if rtype == "Patient":
        for p in store.patients.values():
            if keep(p["id"], None) and not encounter_id:
                yield patient(store, p), p["id"], None
    elif rtype == "Encounter":
        for e in store.encounters.values():
            if keep(e["patient_id"], e["id"]):
                yield encounter(store, e), e["patient_id"], e["id"]
    elif rtype == "ServiceRequest":
        for o in store.orders.values():
            if keep(o["patient_id"], o["encounter_id"]):
                yield service_request(store, o), o["patient_id"], o["encounter_id"]
        for e in store.encounters.values():
            if keep(e["patient_id"], e["id"]):
                for x in referrals(store, e):
                    yield x, e["patient_id"], e["id"]
    elif rtype == "Specimen":
        for s in store.specimens.values():
            eid = (store.orders.get(s["order_id"]) or {}).get("encounter_id")
            if keep(s["patient_id"], eid):
                yield specimen(store, s), s["patient_id"], eid
    elif rtype in ("ImagingStudy", "Media"):
        for s in store.imaging_studies.values():
            eid = (store.orders.get(s["order_id"]) or {}).get("encounter_id")
            if keep(s["patient_id"], eid):
                yield (imaging_study if rtype == "ImagingStudy" else media)(store, s), s["patient_id"], eid
    elif rtype in ("DiagnosticReport", "Observation", "DocumentReference", "Provenance"):
        for r in store.reports.values():
            if not keep(r["patient_id"], r["encounter_id"]):
                continue
            if rtype == "DiagnosticReport" and is_diagnostic(r):
                yield diagnostic_report(store, r, None, files), r["patient_id"], r["encounter_id"]
            elif rtype == "Observation":
                for x in observations(store, r):
                    yield x, r["patient_id"], r["encounter_id"]
            elif rtype == "DocumentReference":
                for v in report_versions(r):
                    yield document_reference(store, r, v, files), r["patient_id"], r["encounter_id"]
            elif rtype == "Provenance":
                for v in report_versions(r):
                    x = provenance(store, r, v)
                    if x:
                        yield x, r["patient_id"], r["encounter_id"]
    elif rtype == "Practitioner":
        if not patient_id and not encounter_id:
            for p in store.practitioners.values():
                yield practitioner(store, p), None, None
    elif rtype == "Organization":
        if not patient_id and not encounter_id:
            yield organization(store), None, None
            for d in store.departments.values():
                yield department(store, d), None, None


def everything(store, files=None):
    """Every resource the API serves (current DiagnosticReport versions; every DocumentReference and Provenance version),
    in TYPES order. Used by the conformance check."""
    for t in TYPES:
        for res, _, _ in _resources(store, t, files):
            yield res


# ------------------------------------------------------------------------ search
SEARCH_PARAMS = {
    "Patient": {"identifier": "token", "name": "string", "gender": "token", "birthdate": "date"},
    "Encounter": {"patient": "reference", "identifier": "token", "status": "token", "class": "token"},
    "ServiceRequest": {"patient": "reference", "encounter": "reference", "identifier": "token", "status": "token",
                       "category": "token"},
    "Specimen": {"patient": "reference", "identifier": "token"},
    "DiagnosticReport": {"patient": "reference", "encounter": "reference", "identifier": "token", "status": "token",
                         "category": "token"},
    "Observation": {"patient": "reference", "encounter": "reference", "code": "token"},
    "DocumentReference": {"patient": "reference", "encounter": "reference", "status": "token"},
    "Provenance": {"patient": "reference", "target": "reference"},
    "ImagingStudy": {"patient": "reference", "identifier": "token", "status": "token"},
    "Media": {"patient": "reference", "encounter": "reference"},
    "Practitioner": {"identifier": "token", "name": "string"},
    "Organization": {"name": "string", "identifier": "token"},
}
COMMON_PARAMS = {"_id": "token", "_lastUpdated": "date", "_sort": "special", "_count": "number", "_offset": "number"}
IGNORED_PARAMS = {"token", "_format"}
DEFAULT_COUNT = 200


class SearchError(ValueError):
    """A search the API does not support (unknown parameter, bad value): HTTP 400 with an OperationOutcome."""


def _ref_id(value, rtype):
    v = str(value).strip()
    return v[len(rtype) + 1:] if v.startswith(rtype + "/") else v


def _identifiers(res):
    out = list(res.get("identifier") or [])
    if isinstance(res.get("identifier"), dict):
        out = [res["identifier"]]
    if res.get("accessionIdentifier"):
        out.append(res["accessionIdentifier"])
    return out


def _match_token_identifier(res, value):
    if "|" in value:
        system, val = value.split("|", 1)
    else:
        system, val = None, value
    for i in _identifiers(res):
        if (system is None or system == "" or i.get("system") == system) and i.get("value") == val:
            return True
    return False


def _match_concept(c, value):
    if not c:
        return False
    system, code = value.split("|", 1) if "|" in value else (None, value)
    for cd in c.get("coding") or []:
        if (system in (None, "") or cd.get("system") == system) and cd.get("code") == code:
            return True
    return system is None and (c.get("text") or "").strip().lower() == code.strip().lower()


def _name_text(res):
    if isinstance(res.get("name"), str):
        return res["name"]
    return " ".join(n.get("text") or "" for n in res.get("name") or [])


def _plain(s):
    return " ".join(re.sub(r"\(\s*synthetic\s*\)", " ", str(s or ""), flags=re.I).lower().split())


_PREFIXES = ("gt", "ge", "lt", "le", "eq")


def _date_filter(value):
    """`_lastUpdated` value -> (prefix, aware datetime, date-only?)."""
    v = str(value).strip().replace(" ", "+")          # a '+' sent unencoded arrives as a space
    prefix = "eq"
    if v[:2] in _PREFIXES and not v[:2].isdigit():
        prefix, v = v[:2], v[2:]
    elif v[:2].isalpha():
        raise SearchError(f"unsupported date prefix in {value!r} (use gt, ge, lt, le or eq)")
    try:
        return prefix, parse_time(v), len(v) == 10
    except ValueError as exc:
        raise SearchError(f"bad date {value!r}: {exc}") from None


def _date_ok(instant, flt):
    prefix, t, day = flt
    x = parse_time(instant)
    if prefix == "eq":
        return x.date() == t.date() if day else x == t
    return {"gt": x > t, "ge": x >= t, "lt": x < t, "le": x <= t}[prefix]


def search(store, rtype, params, files=None):
    """Run an R4 search. `params` is a list of (name, value) pairs. Returns the matching resources (all of them; paging is
    the caller's). Raises SearchError for an unsupported parameter."""
    if rtype not in SEARCH_PARAMS:
        raise SearchError(f"unknown resource type {rtype!r}")
    allowed = dict(COMMON_PARAMS, **SEARCH_PARAMS[rtype])
    by = {}
    for name, value in params:
        if name in IGNORED_PARAMS:
            continue
        base = name.split(":", 1)[0]
        if base not in allowed:
            raise SearchError(f"search parameter {name!r} is not supported on {rtype} "
                              f"(supported: {', '.join(sorted(allowed))})")
        by.setdefault(base, []).append(value)
    patient_id = _ref_id(by["patient"][-1], "Patient") if "patient" in by else None
    encounter_id = _ref_id(by["encounter"][-1], "Encounter") if "encounter" in by else None
    dates = [_date_filter(x) for x in by.get("_lastUpdated", [])]

    if rtype == "DiagnosticReport" and any(f[0] == "gt" for f in dates):
        # the re-fetch delta: exactly the reports hl7.changed_since gives for the watermark
        cut = max((f for f in dates if f[0] == "gt"), key=lambda f: f[1])
        changed = {r["id"] for r in hl7.changed_since(store, iso(cut[1]), patient_id=patient_id)}
        rows = []
        for rid in sorted(changed):
            r = store.reports[rid]
            if is_diagnostic(r) and (not encounter_id or r["encounter_id"] == encounter_id):
                rows.append((diagnostic_report(store, r, None, files), r["patient_id"], r["encounter_id"]))
    else:
        rows = _resources(store, rtype, files, patient_id, encounter_id)

    out = []
    for res, pid, eid in rows:
        if "_id" in by and res["id"] not in ",".join(by["_id"]).split(","):
            continue
        if any(not _date_ok(res["meta"]["lastUpdated"], f) for f in dates):
            continue
        if "identifier" in by and not all(any(_match_token_identifier(res, v) for v in val.split(","))
                                          for val in by["identifier"]):
            continue
        if "status" in by and not all(res.get("status") in val.split(",") for val in by["status"]):
            continue
        if "class" in by and not all((res.get("class") or {}).get("code") in [x.split("|")[-1] for x in val.split(",")]
                                     for val in by["class"]):
            continue
        if "category" in by and not all(any(_match_concept(c, x) for c in res.get("category") or []
                                            for x in val.split(",")) for val in by["category"]):
            continue
        if "code" in by and not all(any(_match_concept(res.get("code"), x) for x in val.split(","))
                                    for val in by["code"]):
            continue
        if "name" in by and not all(_plain(val) in _plain(_name_text(res)) for val in by["name"]):
            continue
        if "gender" in by and not all(res.get("gender") == val for val in by["gender"]):
            continue
        if "birthdate" in by and not (res.get("birthDate") and all(_date_ok(res["birthDate"], _date_filter(val))
                                                                   for val in by["birthdate"])):
            continue
        if "target" in by:
            tg = [t.get("reference", "") for t in res.get("target") or []]
            tg += [t.split("/_history/")[0] for t in tg]
            if not all(val in tg for val in by["target"]):
                continue
        out.append(res)

    for s in by.get("_sort", []):
        for key in reversed(s.split(",")):
            if key.lstrip("-") != "_lastUpdated":
                raise SearchError(f"_sort={key!r} is not supported (use _lastUpdated or -_lastUpdated)")
            out.sort(key=lambda x: parse_time(x["meta"]["lastUpdated"]), reverse=key.startswith("-"))
    return out


def searchset(resources, base, self_url, total=None, offset=0, count=None, next_url=None):
    """A searchset Bundle (fullUrl = <base>/fhir/Type/id)."""
    b = {"resourceType": "Bundle", "id": str(uuid.uuid4()), "meta": meta(datetime.now(ids.IST)),
         "type": "searchset", "total": len(resources) if total is None else total,
         "link": [{"relation": "self", "url": self_url}]}
    if next_url:
        b["link"].append({"relation": "next", "url": next_url})
    b["entry"] = [{"fullUrl": f"{base}/fhir/{r['resourceType']}/{r['id']}", "resource": r, "search": {"mode": "match"}}
                  for r in resources]
    return b


def history_bundle(store, r, base, self_url, files=None):
    """`_history` of a DiagnosticReport: every version, newest first."""
    entries = []
    for v in report_versions(r):
        res = diagnostic_report(store, r, v, files)
        entries.append({"fullUrl": f"{base}/fhir/DiagnosticReport/{r['id']}/_history/{v['version']}", "resource": res,
                        "request": {"method": "POST" if v["version"] == 1 else "PUT",
                                    "url": "DiagnosticReport" if v["version"] == 1 else f"DiagnosticReport/{r['id']}"},
                        "response": {"status": "201 Created" if v["version"] == 1 else "200 OK",
                                     "lastModified": res["meta"]["lastUpdated"]}})
    return {"resourceType": "Bundle", "id": str(uuid.uuid4()), "meta": meta(datetime.now(ids.IST)), "type": "history",
            "total": len(entries), "link": [{"relation": "self", "url": self_url}], "entry": entries}


def patient_everything(store, pid, files=None):
    """Every resource of one registration (and the practitioners and organisations they reference)."""
    out = [patient(store, store.patients[pid])]
    for t in ("Encounter", "ServiceRequest", "Specimen", "DiagnosticReport", "Observation", "ImagingStudy", "Media",
              "DocumentReference", "Provenance"):
        out.extend(res for res, _, _ in _resources(store, t, files, patient_id=pid))
    have = {(x["resourceType"], x["id"]) for x in out}
    extra = []
    for s in references(out):
        p = parse_reference(s)
        if p and p[0] in ("Practitioner", "Organization") and (p[0], p[1]) not in have:
            got = read(store, p[0], p[1])
            if got:
                have.add((p[0], p[1]))
                extra.append(got)
    return out + sorted(extra, key=lambda x: (x["resourceType"], x["id"]))


def capability_statement(store):
    resources = []
    for t in TYPES:
        params = dict(COMMON_PARAMS, **SEARCH_PARAMS[t])
        entry = {"type": t}
        if t in PROFILED:
            entry["supportedProfile"] = [NRCES + t]
        elif t == "Provenance":
            entry["documentation"] = "Base R4 (NRCeS v6.5.0 has no Provenance profile): the digital signature of a report."
        elif t == "Media":
            entry["documentation"] = "Base R4 (no NRCeS profile): the DICOMweb link of an imaging study."
        if t == "DiagnosticReport":
            entry["supportedProfile"] = [NRCES + "DiagnosticReportLab", NRCES + "DiagnosticReportImaging"]
        inter = [{"code": "read"}, {"code": "search-type"}]
        if t == "DiagnosticReport":
            inter += [{"code": "vread"}, {"code": "history-instance"}]
        entry["interaction"] = inter
        entry["versioning"] = "versioned" if t in ("DiagnosticReport", "DocumentReference", "Provenance") else "no-version"
        entry["readHistory"] = t == "DiagnosticReport"
        entry["searchParam"] = [{"name": n, "type": ty} for n, ty in sorted(params.items()) if ty != "special"] + \
                               [{"name": "_sort", "type": "special", "documentation": "_lastUpdated or -_lastUpdated"}]
        ops = []
        if t == "Patient":
            ops = [{"name": "everything", "definition": "http://hl7.org/fhir/OperationDefinition/Patient-everything"},
                   {"name": "similar", "definition": DEMO + "/OperationDefinition/Patient-similar",
                    "documentation": "Other registrations with the same name, sex and age, for a person to link "
                                     "(never merged)."}]
        if t in ("DiagnosticReport", "DocumentReference"):
            ops = [{"name": "document", "definition": "http://hl7.org/fhir/OperationDefinition/Composition-document",
                    "documentation": "The NRCeS DocumentBundle of the report version."}]
        _set(entry, "operation", ops)
        resources.append(entry)
    return {"resourceType": "CapabilityStatement", "id": "vaidyx-demo-his",
            "meta": meta(_built_at(store)),
            "name": "VaidyxDemoHisFhir", "title": f"{NAME} FHIR API",
            "status": "active", "experimental": True, "date": iso(_built_at(store)),
            "publisher": "Vaidyx demo (SYNTHETIC)",
            "description": "Read-only FHIR R4 API of a SYNTHETIC mock Indian hospital, in NRCeS (ABDM) FHIR IG v6.5.0 "
                           "shapes. Every patient, doctor and number is invented.",
            "kind": "instance",
            "software": {"name": NAME, "version": VERSION},
            "implementation": {"description": "SYNTHETIC mock"},
            "fhirVersion": FHIR_VERSION, "format": ["json"],
            "rest": [{"mode": "server",
                      "documentation": "Read only (no create, update or delete). Bearer token from data/his_mock/token.",
                      "security": {"description": "HTTP bearer token (Authorization: Bearer <token>); localhost only."},
                      "resource": resources}]}


def operation_outcome(code, diagnostics, severity="error"):
    return {"resourceType": "OperationOutcome",
            "issue": [{"severity": severity, "code": code, "diagnostics": diagnostics}]}


# ------------------------------------------------------------------------ router
router = APIRouter()
FHIR_JSON = "application/fhir+json"


def _json(obj, status=200):
    return JSONResponse(obj, status_code=status, media_type=FHIR_JSON)


def _not_found(what):
    return _json(operation_outcome("not-found", f"{what} not found"), 404)


def _base(request):
    return str(request.base_url).rstrip("/")


def _self_url(request):
    """The request URL without a `token` query parameter (never echo the token into a Bundle link)."""
    q = [(k, v) for k, v in request.query_params.multi_items() if k != "token"]
    return str(request.url.replace(query=urlencode(q)))


@router.get("/metadata")
def metadata(request: Request):
    """CapabilityStatement (no token, as R4 allows)."""
    h = request.app.state.hospital
    with h.lock:
        return _json(capability_statement(h.store))


@router.get("/Patient/{pid}/$everything")
def op_everything(pid: str, request: Request, hospital: Hospital = Depends(require_token)):
    with hospital.lock:
        if pid not in hospital.store.patients:
            return _not_found(f"Patient/{pid}")
        res = patient_everything(hospital.store, pid, hospital.files)
        return _json(searchset(res, _base(request), _self_url(request)))


@router.get("/Patient/{pid}/$similar")
def op_similar(pid: str, request: Request, hospital: Hospital = Depends(require_token)):
    """Other registrations with the same name, sex and age (store.similar_registrations): shown for a person to link,
    never merged."""
    with hospital.lock:
        s = hospital.store
        if pid not in s.patients:
            return _not_found(f"Patient/{pid}")
        res = [patient(s, p) for p in s.similar_registrations(pid)]
        return _json(searchset(res, _base(request), _self_url(request)))


@router.get("/DiagnosticReport/{rid}/_history")
def dr_history(rid: str, request: Request, hospital: Hospital = Depends(require_token)):
    with hospital.lock:
        r = hospital.store.reports.get(rid)
        if not r or not is_diagnostic(r):
            return _not_found(f"DiagnosticReport/{rid}")
        return _json(history_bundle(hospital.store, r, _base(request), _self_url(request), hospital.files))


@router.get("/DiagnosticReport/{rid}/_history/{vid}")
def dr_vread(rid: str, vid: str, hospital: Hospital = Depends(require_token)):
    with hospital.lock:
        r = hospital.store.reports.get(rid)
        if not r or not is_diagnostic(r) or not vid.isdigit():
            return _not_found(f"DiagnosticReport/{rid}/_history/{vid}")
        v = next((x for x in r["versions"] if x["version"] == int(vid)), None)
        if not v:
            return _not_found(f"DiagnosticReport/{rid}/_history/{vid}")
        return _json(diagnostic_report(hospital.store, r, v, hospital.files))


@router.get("/DiagnosticReport/{rid}/$document")
def dr_document(rid: str, hospital: Hospital = Depends(require_token)):
    """The DocumentBundle of the report's current version."""
    with hospital.lock:
        r = hospital.store.reports.get(rid)
        if not r or not is_diagnostic(r):
            return _not_found(f"DiagnosticReport/{rid} (notes are served as DocumentReference: use "
                              f"DocumentReference/doc-{rid}-v<n>/$document)")
        return _json(document_bundle(hospital.store, r, None, hospital.files))


@router.get("/DocumentReference/{did}/$document")
def doc_document(did: str, hospital: Hospital = Depends(require_token)):
    """The DocumentBundle of that report version (any report, notes included)."""
    with hospital.lock:
        r, v = _find_version_resource(hospital.store, "doc", did)
        if not r:
            return _not_found(f"DocumentReference/{did}")
        return _json(document_bundle(hospital.store, r, v, hospital.files))


@router.get("/{rtype}/{rid}")
def read_resource(rtype: str, rid: str, hospital: Hospital = Depends(require_token)):
    if rtype not in SEARCH_PARAMS:
        return _json(operation_outcome("not-supported", f"resource type {rtype!r} is not served"), 404)
    with hospital.lock:
        res = read(hospital.store, rtype, rid, hospital.files)
    return _json(res) if res else _not_found(f"{rtype}/{rid}")


@router.get("/{rtype}")
def search_type(rtype: str, request: Request, hospital: Hospital = Depends(require_token)):
    if rtype not in SEARCH_PARAMS:
        return _json(operation_outcome("not-supported", f"resource type {rtype!r} is not served"), 404)
    params = list(request.query_params.multi_items())
    try:
        count = int(request.query_params.get("_count", DEFAULT_COUNT))
        offset = int(request.query_params.get("_offset", 0))
        if count < 0 or offset < 0:
            raise ValueError
    except ValueError:
        return _json(operation_outcome("invalid", "_count and _offset must be non-negative integers"), 400)
    try:
        with hospital.lock:
            found = search(hospital.store, rtype, [(k, v) for k, v in params if k not in ("_count", "_offset")],
                           hospital.files)
    except SearchError as exc:
        return _json(operation_outcome("not-supported", str(exc)), 400)
    page = found[offset:offset + count]
    next_url = None
    if offset + count < len(found) and count > 0:
        q = [(k, v) for k, v in params if k not in ("_offset", "token")] + [("_offset", str(offset + count))]
        next_url = f"{_base(request)}/fhir/{rtype}?{urlencode(q)}"
    return _json(searchset(page, _base(request), _self_url(request), total=len(found), next_url=next_url))
