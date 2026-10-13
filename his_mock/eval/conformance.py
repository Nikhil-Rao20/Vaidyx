"""Conformance check of the mock hospital's FHIR API (plan item V2-1.3, gate row "Mock HIS conformance").

Our own light schema, built from the NRCeS (ABDM) FHIR IG v6.5.0 profile tables in docs_Eswar/research/prep_v2/
nrces_profiles.md (decision logged 13 Oct: `fhir.resources` is not used; its R4 releases need pydantic 1 and it checks base R4
shape only, not NRCeS cardinalities, fixed systems or slices). Checked on every resource: required elements, allowed
statuses, fixed code systems, identifiers (system, value and the type the profile needs; values match the synthetic id
patterns; ABHA 14 digits), `meta.profile` on every NRCeS-profiled type, `meta.lastUpdated` (+05:30) everywhere, no
Aadhaar (no identifier of type ADN, no Aadhaar-like number anywhere), SYNTHETIC in every Patient name and the hospital's
name, the Provenance signature fields, the viewer URL on every available ImagingStudy; on each DocumentBundle: meta.versionId,
identifier, type document, timestamp, the Composition first and every reference resolvable inside the bundle.

Known, deliberate deviations (logged, not flagged): Observation.code may carry only `text` when no LOINC / SNOMED code is
certain (NRCeS slices the coding closed); ServiceRequest.code likewise; DiagnosticReportImaging.media (1..*) is required
only when the report has an ImagingStudy (endoscopy reports have none); Provenance and Media are base R4 (no NRCeS profile).

    python -m his_mock.eval.conformance [--data DIR] [--url http://127.0.0.1:7130 --token-file DIR/token]

Prints exactly `CONFORMANCE OK: <n> resources checked` and exits 0, else up to 50 problems (one per line) and
`CONFORMANCE FAILED: <k> problems`, exit 1.
"""
import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .. import fhir, ids, paths, scenarios

NRCES = fhir.NRCES
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+05:30$")
DATE_OR_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?$")
FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REAL_ABDM_REGISTRIES = ("doctor.ndhm.gov.in", "facility.ndhm.gov.in", "hpr.abdm.gov.in", "facility.abdm.gov.in")

STATUSES = {
    "Encounter": {"planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled", "entered-in-error",
                  "unknown"},
    "ServiceRequest": {"draft", "active", "on-hold", "revoked", "completed", "entered-in-error", "unknown"},
    "Specimen": {"available", "unavailable", "unsatisfactory", "entered-in-error"},
    "DiagnosticReport": {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended", "cancelled",
                         "entered-in-error", "unknown"},
    "Observation": {"registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error",
                    "unknown"},
    "DocumentReference": {"current", "superseded", "entered-in-error"},
    "Composition": {"preliminary", "final", "amended", "entered-in-error"},
    "ImagingStudy": {"registered", "available", "cancelled", "entered-in-error", "unknown"},
    "Media": {"preparation", "in-progress", "not-done", "on-hold", "stopped", "completed", "entered-in-error", "unknown"},
}
DOC_STATUS = {"preliminary", "final", "amended", "entered-in-error"}
GENDERS = {"male", "female", "other", "unknown"}
ENCOUNTER_CLASSES = {"AMB", "IMP", "EMER", "ACUTE", "NONAC", "OBSENC", "PRENC", "SS", "VR", "HH", "FLD"}
ATTESTER_MODES = {"personal", "professional", "legal", "official"}
SIG_STATUSES = {"verified", "failed"}
EXPECTED_PROFILE = {t: NRCES + t for t in fhir.PROFILED}
EXPECTED_PROFILE["Composition"] = NRCES + "DiagnosticReportRecord"
UNPROFILED = {"Provenance", "Media", "CapabilityStatement", "OperationOutcome"}

_IP = scenarios.load()["identifier_patterns"]
SYSTEM_PATTERNS = {
    fhir.SYS["uhid"]: [ids.PATTERNS["uhid"], ids.PATTERNS["temporary_uhid"]],
    fhir.SYS["ip_no"]: [ids.PATTERNS["ip_no"]],
    fhir.SYS["op_no"]: [ids.PATTERNS["op_no"]],
    fhir.SYS["accession"]: [ids.PATTERNS["accession"]],
    fhir.SYS["sample_barcode"]: [ids.PATTERNS["sample_barcode"]],
    fhir.SYS["reg_no"]: [ids.PATTERNS["reg_no"]],
    fhir.SYS["block_no"]: [re.compile(_IP["block_no"]["regex"])],
    fhir.SYS["abha"]: [re.compile(_IP["abha_number"]["regex"])],
    fhir.SYS["abha_address"]: [re.compile(_IP["abha_address"]["regex"])],
    fhir.SYS["pmjay"]: [re.compile(_IP["pmjay_id"]["regex"])],
    fhir.SYS["facility"]: [re.compile(r"^VXDEMO$")],
}
# which identifier type a profile needs on its identifiers
TYPE_REQUIRED = {"Patient", "Practitioner", "Organization"}
BASE64_KEYS = {"data", "hash"}          # base64 payloads are not text: the Aadhaar scan skips them


# ------------------------------------------------------------------------ helpers
def _strip_base64(obj):
    if isinstance(obj, dict):
        return {k: ("<base64>" if k in BASE64_KEYS and isinstance(v, str) else _strip_base64(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_base64(x) for x in obj]
    return obj


def _all_identifiers(obj):
    """Every Identifier-shaped dict inside a resource (has system or value plus type / use / system)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("identifier", "accessionIdentifier", "masterIdentifier"):
                out.extend([v] if isinstance(v, dict) else list(v or []))
            out.extend(_all_identifiers(v))
    elif isinstance(obj, list):
        for x in obj:
            out.extend(_all_identifiers(x))
    return [i for i in out if isinstance(i, dict)]


def _codings(concept):
    return (concept or {}).get("coding") or []


def _ext(res, url):
    return next((e for e in res.get("extension") or [] if e.get("url") == url), None)


def _is_b64(s):
    try:
        base64.b64decode(s, validate=True)
        return True
    except (binascii.Error, ValueError, TypeError):
        return False


def _check_coding(where, c, add, system=None):
    if system and c.get("system") != system:
        add(f"{where}: coding system {c.get('system')!r}, expected {system}")
    for k in ("system", "code", "display"):
        if not c.get(k):
            add(f"{where}: coding without {k}")


def _check_reference(where, r, add, types=None):
    if not isinstance(r, dict) or not (r.get("reference") or r.get("display")):
        add(f"{where}: missing reference")
        return
    if r.get("reference") and types:
        p = fhir.parse_reference(r["reference"])
        if not p or p[0] not in types:
            add(f"{where}: reference {r['reference']!r} is not one of {sorted(types)}")


# ------------------------------------------------------------------------ one resource
def check_resource(res):
    """Problems of one resource (a Bundle's entries are checked too). Each problem starts with `Type/id`."""
    problems = []
    rtype = res.get("resourceType") if isinstance(res, dict) else None
    name = f"{rtype}/{res.get('id')}" if rtype else "<not a resource>"

    def add(msg):
        problems.append(f"{name}: {msg}")

    if not rtype:
        add("no resourceType")
        return problems
    if rtype not in ("OperationOutcome",) and not FHIR_ID.match(str(res.get("id") or "")):
        add(f"id {res.get('id')!r} is not a FHIR id")
    m = res.get("meta") or {}
    if rtype not in ("OperationOutcome",):
        if not INSTANT.match(str(m.get("lastUpdated") or "")):
            add(f"meta.lastUpdated {m.get('lastUpdated')!r} is not an instant with +05:30")
    expected = EXPECTED_PROFILE.get(rtype)
    if rtype == "DiagnosticReport":
        if not set(m.get("profile") or []) & {NRCES + "DiagnosticReportLab", NRCES + "DiagnosticReportImaging"}:
            add("meta.profile is not DiagnosticReportLab or DiagnosticReportImaging")
    elif rtype == "Bundle" and res.get("type") == "document":
        if NRCES + "DocumentBundle" not in (m.get("profile") or []):
            add("meta.profile is not DocumentBundle")
    elif expected and expected not in (m.get("profile") or []):
        add(f"meta.profile missing {expected}")
    elif rtype in UNPROFILED and any(str(p).startswith(NRCES) for p in m.get("profile") or []):
        add("claims an NRCeS profile, but NRCeS v6.5.0 has none for this type")

    # no Aadhaar: no ADN identifier type, no Aadhaar-like number in any text
    for i in _all_identifiers(res):
        if any(c.get("code") == "ADN" for c in _codings(i.get("type"))):
            add("identifier of type ADN (Aadhaar)")
        sysurl = str(i.get("system") or "")
        if any(x in sysurl for x in REAL_ABDM_REGISTRIES):
            add(f"identifier system {sysurl} is a real ABDM registry (use a synthetic system)")
    text = json.dumps(_strip_base64(res), ensure_ascii=False)
    for hit in scenarios.AADHAAR_LIKE.findall(text):
        add(f"Aadhaar-like number {hit!r}")
    if "\u2014" in text:
        add("em dash in a string")

    status = res.get("status")
    if rtype in STATUSES and status not in STATUSES[rtype]:
        add(f"status {status!r} not allowed (allowed: {', '.join(sorted(STATUSES[rtype]))})")

    if rtype not in ("Bundle",):
        _check_identifiers(rtype, res, add)
    fn = CHECKS.get(rtype)
    if fn:
        fn(res, add)
    if rtype == "Bundle":
        for i, e in enumerate(res.get("entry") or []):
            sub = e.get("resource")
            if not isinstance(sub, dict):
                add(f"entry {i} has no resource")
                continue
            problems.extend(check_resource(sub))
    return problems


def _check_identifiers(rtype, res, add):
    idents = res.get("identifier")
    idents = [idents] if isinstance(idents, dict) else list(idents or [])
    if rtype in TYPE_REQUIRED and not idents:
        add("no identifier (1..* in the NRCeS profile)")
    extra = [res["accessionIdentifier"]] if res.get("accessionIdentifier") else []
    for i in idents + extra:
        if not i.get("system") or not i.get("value"):
            add(f"identifier without system or value: {i}")
            continue
        if rtype in TYPE_REQUIRED:
            if not _codings(i.get("type")):
                add(f"identifier {i['value']!r} has no type coding")
            for c in _codings(i.get("type")):
                _check_coding(f"identifier {i['value']!r} type", c, add)
        pats = SYSTEM_PATTERNS.get(i["system"])
        if pats and not any(p.match(str(i["value"])) for p in pats):
            add(f"identifier {i['value']!r} does not match the synthetic pattern of {i['system']}")
        if i["system"] == fhir.SYS["abha"] and len(re.sub(r"\D", "", str(i["value"]))) != 14:
            add(f"ABHA number {i['value']!r} is not 14 digits")
        if i["system"] == fhir.SYS["dicom_uid"] and not str(i["value"]).startswith("urn:oid:"):
            add(f"Study UID identifier {i['value']!r} is not urn:oid:")


# ------------------------------------------------------------------------ per type
def _patient(res, add):
    names = res.get("name") or []
    if not names or not all(n.get("text") for n in names):
        add("name.text missing (1..1)")
    elif not all("SYNTHETIC" in n["text"] for n in names):
        add("name without SYNTHETIC")
    if res.get("gender") and res["gender"] not in GENDERS:
        add(f"gender {res['gender']!r}")
    types = [c.get("code") for i in res.get("identifier") or [] for c in _codings(i.get("type"))]
    if "MR" not in types:
        add("no UHID identifier (type MR)")
    if res.get("birthDate") and not re.match(r"^\d{4}-\d{2}-\d{2}$", res["birthDate"]):
        add(f"birthDate {res['birthDate']!r}")


def _encounter(res, add):
    c = res.get("class") or {}
    if c.get("system") != fhir.ACT_CODE or c.get("code") not in ENCOUNTER_CLASSES:
        add(f"class {c} is not a v3-ActCode encounter class")
    _check_reference("subject", res.get("subject"), add, {"Patient"})
    if not any(i.get("system") in (fhir.SYS["ip_no"], fhir.SYS["op_no"]) for i in res.get("identifier") or []):
        add("no IP / OP No. identifier")
    for i, loc in enumerate(res.get("location") or []):
        if loc.get("status") not in ("planned", "active", "reserved", "completed"):
            add(f"location[{i}].status {loc.get('status')!r}")


def _service_request(res, add):
    if res.get("intent") not in ("proposal", "plan", "directive", "order", "original-order", "reflex-order",
                                 "filler-order", "instance-order", "option"):
        add(f"intent {res.get('intent')!r}")
    _check_reference("subject", res.get("subject"), add, {"Patient"})
    _check_reference("requester", res.get("requester"), add)
    for c in _codings(res.get("code")):
        _check_coding("code", c, add, fhir.SNOMED)
    if not (res.get("code") or {}).get("text") and not _codings(res.get("code")):
        add("code without coding or text")
    for cat in res.get("category") or []:
        for c in _codings(cat):
            _check_coding("category", c, add, fhir.SNOMED)


def _specimen(res, add):
    if not res.get("receivedTime"):
        add("receivedTime missing (1..1)")
    if not (res.get("collection") or {}).get("collectedDateTime"):
        add("collection.collectedDateTime missing (1..1)")
    codings = _codings(res.get("type"))
    if not codings:
        add("type.coding missing")
    for c in codings:
        _check_coding("type", c, add, fhir.SNOMED)
    if not res.get("accessionIdentifier"):
        add("no accessionIdentifier (sample barcode)")


def _diagnostic_report(res, add):
    profiles = (res.get("meta") or {}).get("profile") or []
    imaging = NRCES + "DiagnosticReportImaging" in profiles
    codings = _codings(res.get("code"))
    if not codings:
        add("code.coding missing (LOINC 1..1)")
    for c in codings:
        _check_coding("code", c, add, fhir.LOINC)
    for cat in res.get("category") or []:
        for c in _codings(cat):
            _check_coding("category", c, add, fhir.SNOMED)
    if not res.get("resultsInterpreter"):
        add("resultsInterpreter missing (1..*)")
    if not res.get("conclusion"):
        add("conclusion missing (1..1)")
    if not INSTANT.match(str(res.get("issued") or "")):
        add(f"issued {res.get('issued')!r} is not an instant")
    if not imaging and not res.get("result"):
        add("result missing (1..* in DiagnosticReportLab)")
    if imaging and res.get("imagingStudy") and not res.get("media"):
        add("media missing (1..* in DiagnosticReportImaging)")
    for r in res.get("result") or []:
        _check_reference("result", r, add, {"Observation"})
    for f in res.get("presentedForm") or []:
        _check_attachment("presentedForm", f, add, need_data=True)
    _check_reference("subject", res.get("subject"), add, {"Patient"})


def _check_attachment(where, att, add, need_data=False):
    if not att.get("contentType"):
        add(f"{where}.contentType missing")
    if need_data and not att.get("data"):
        add(f"{where}.data missing")
    if att.get("data") and not _is_b64(att["data"]):
        add(f"{where}.data is not base64")
    if att.get("data") and not att.get("hash") and where.startswith("content"):
        add(f"{where}.hash missing next to data")
    if att.get("hash"):
        h = att["hash"]
        if not _is_b64(h) or len(base64.b64decode(h)) != 20:
            add(f"{where}.hash is not a base64 SHA-1")
        elif att.get("data") and base64.b64decode(h) != hashlib.sha1(base64.b64decode(att["data"])).digest():
            add(f"{where}.hash does not match the data")


def _observation(res, add):
    code = res.get("code") or {}
    if not code.get("coding") and not code.get("text"):
        add("code without coding or text")
    for c in _codings(code):
        if c.get("system") not in (fhir.LOINC, fhir.SNOMED):
            add(f"code.coding system {c.get('system')!r} (only LOINC or SNOMED CT)")
        _check_coding("code", c, add)
    values = [k for k in res if k.startswith("value")]
    if len(values) != 1:
        add(f"expected exactly one value[x], found {values}")
    q = res.get("valueQuantity")
    if q is not None and not isinstance(q.get("value"), (int, float)):
        add("valueQuantity.value is not a number")
    _check_reference("subject", res.get("subject"), add, {"Patient"})


def _document_reference(res, add):
    if res.get("docStatus") and res["docStatus"] not in DOC_STATUS:
        add(f"docStatus {res['docStatus']!r}")
    content = res.get("content") or []
    if not content:
        add("content missing (1..*)")
    for i, c in enumerate(content):
        att = c.get("attachment") or {}
        _check_attachment(f"content[{i}].attachment", att, add)
        if att.get("contentType") != "application/pdf":
            add(f"content[{i}].attachment.contentType {att.get('contentType')!r} (use application/pdf)")
        if not att.get("url"):
            add(f"content[{i}].attachment.url missing")
    for c in _codings(res.get("type")):
        _check_coding("type", c, add, fhir.LOINC)


def _provenance(res, add):
    if not res.get("target"):
        add("target missing (1..*)")
    if not INSTANT.match(str(res.get("recorded") or "")):
        add("recorded is not an instant")
    agents = res.get("agent") or []
    if not agents or not all(a.get("who") for a in agents):
        add("agent.who missing")
    sigs = res.get("signature") or []
    if not sigs:
        add("signature missing")
    for s in sigs:
        if not s.get("type"):
            add("signature.type missing (1..*)")
        for c in s.get("type") or []:
            _check_coding("signature.type", c, add, fhir.SIGNATURE_TYPE)
        if not INSTANT.match(str(s.get("when") or "")):
            add("signature.when is not an instant")
        _check_reference("signature.who", s.get("who"), add, {"Practitioner"})
        if not s.get("data") or not _is_b64(s["data"]):
            add("signature.data missing or not base64")
        elif "Digitally signed by" not in base64.b64decode(s["data"]).decode("utf-8", "replace"):
            add("signature.data does not hold a signature block")
    ca = _ext(res, fhir.EXT["signature_ca"])
    if not ca or ca.get("valueString") != _IP["ca"]["example"]:
        add("signature CA extension missing or not the demo CA")
    serial = _ext(res, fhir.EXT["signature_serial"])
    if not serial or not ids.PATTERNS["certificate_serial"].match(str(serial.get("valueString"))):
        add("certificate serial extension missing or not a VXDCA- serial")
    h = _ext(res, fhir.EXT["signature_hash"])
    if not h or not HEX64.match(str(h.get("valueString"))):
        add("signed document hash extension missing or not a sha256")
    st = _ext(res, fhir.EXT["signature_status"])
    if not st or st.get("valueCode") not in SIG_STATUSES:
        add("verification status extension missing or not verified / failed")


def _imaging_study(res, add):
    _check_reference("subject", res.get("subject"), add, {"Patient"})
    if not any(i.get("system") == fhir.SYS["dicom_uid"] for i in res.get("identifier") or []):
        add("no Study UID identifier (urn:dicom:uid)")
    n_inst = 0
    for i, se in enumerate(res.get("series") or []):
        if not se.get("uid") or not (se.get("modality") or {}).get("code"):
            add(f"series[{i}] without uid or modality")
        for j, ins in enumerate(se.get("instance") or []):
            n_inst += 1
            if not ins.get("uid") or not (ins.get("sopClass") or {}).get("code"):
                add(f"series[{i}].instance[{j}] without uid or sopClass")
    if res.get("status") == "available":
        if not _ext(res, fhir.EXT["viewer_url"]):
            add("available study without the viewer URL")
        if res.get("numberOfSeries") != len(res.get("series") or []) or res.get("numberOfInstances") != n_inst:
            add("numberOfSeries / numberOfInstances do not match the series")


def _media(res, add):
    _check_reference("subject", res.get("subject"), add, {"Patient"})
    c = res.get("content") or {}
    if not c.get("contentType"):
        add("content.contentType missing")


def _practitioner(res, add):
    if not any(n.get("text") for n in res.get("name") or []):
        add("name.text missing (1..1)")
    if not any(c.get("code") == "MD" for i in res.get("identifier") or [] for c in _codings(i.get("type"))):
        add("no registration No. identifier (type MD)")


def _organization(res, add):
    if not res.get("name"):
        add("name missing (1..1)")
    elif not res.get("partOf") and "SYNTHETIC" not in res["name"]:
        add("the hospital's name does not say SYNTHETIC")


def _composition(res, add):
    codings = _codings(res.get("type"))
    if not codings:
        add("type.coding missing")
    for c in codings:
        _check_coding("type", c, add, fhir.SNOMED)
    _check_reference("subject", res.get("subject"), add, {"Patient"})
    for k in ("date", "title"):
        if not res.get(k):
            add(f"{k} missing (1..1)")
    if not res.get("author"):
        add("author missing (1..*)")
    for a in res.get("attester") or []:
        if a.get("mode") not in ATTESTER_MODES:
            add(f"attester.mode {a.get('mode')!r}")
    sections = res.get("section") or []
    if len(sections) != 1:
        add(f"{len(sections)} sections (exactly one in DiagnosticReportRecord)")
    for s in sections:
        entries = s.get("entry") or []
        if not 1 <= len(entries) <= 2:
            add(f"section.entry has {len(entries)} entries (1..2)")
        kinds = [fhir.parse_reference(e.get("reference", "")) for e in entries]
        types = [k[0] if k else None for k in kinds]
        if any(t not in ("DiagnosticReport", "DocumentReference") for t in types) or len(set(types)) != len(types):
            add(f"section.entry types {types} (at most one DiagnosticReport and one DocumentReference)")
        for c in _codings(s.get("code")):
            _check_coding("section.code", c, add, fhir.SNOMED)


def _bundle(res, add):
    t = res.get("type")
    entries = res.get("entry") or []
    if t == "document":
        m = res.get("meta") or {}
        if not m.get("versionId"):
            add("meta.versionId missing (1..1 in DocumentBundle)")
        ident = res.get("identifier") or {}
        if not ident.get("system") or not ident.get("value"):
            add("identifier.system / value missing (bdl-9)")
        if not INSTANT.match(str(res.get("timestamp") or "")):
            add("timestamp missing or not an instant (bdl-10)")
        if not entries or (entries[0].get("resource") or {}).get("resourceType") != "Composition":
            add("the first entry is not a Composition (bdl-11)")
        have = {}
        for e in entries:
            r = e.get("resource") or {}
            if not e.get("fullUrl"):
                add(f"entry {r.get('resourceType')}/{r.get('id')} without fullUrl")
            key = (r.get("resourceType"), r.get("id"))
            if key in have:
                add(f"duplicate entry {key[0]}/{key[1]}")
            have[key] = r
        seen = set()
        for e in entries:
            for s in fhir.references(e.get("resource") or {}):
                if s in seen:
                    continue
                seen.add(s)
                p = fhir.parse_reference(s)
                if not p:
                    add(f"reference {s!r} is not Type/id")
                elif (p[0], p[1]) not in have:
                    add(f"reference {s!r} does not resolve inside the bundle")
                elif p[2] and str((have[(p[0], p[1])].get("meta") or {}).get("versionId")) != p[2]:
                    add(f"reference {s!r} names another version than the bundle holds")
    elif t == "searchset":
        if res.get("total") is None:
            add("searchset without total")
        if not any(l.get("relation") == "self" for l in res.get("link") or []):
            add("searchset without a self link")
    elif t == "history":
        pass
    else:
        add(f"bundle type {t!r} (document, searchset or history)")


def _capability(res, add):
    for k, want in (("status", "active"), ("kind", "instance"), ("fhirVersion", fhir.FHIR_VERSION)):
        if res.get(k) != want:
            add(f"{k} {res.get(k)!r}, expected {want!r}")
    if "json" not in (res.get("format") or []):
        add("format does not list json")
    if "SYNTHETIC" not in ((res.get("implementation") or {}).get("description") or ""):
        add("implementation.description does not say SYNTHETIC")


CHECKS = {"Patient": _patient, "Encounter": _encounter, "ServiceRequest": _service_request, "Specimen": _specimen,
          "DiagnosticReport": _diagnostic_report, "Observation": _observation, "DocumentReference": _document_reference,
          "Provenance": _provenance, "ImagingStudy": _imaging_study, "Media": _media, "Practitioner": _practitioner,
          "Organization": _organization, "Composition": _composition, "Bundle": _bundle,
          "CapabilityStatement": _capability}


# ------------------------------------------------------------------------ the store
def check_store(store, files=None):
    """Check every resource the API serves (fhir.everything) and the DocumentBundle of every version of every report, plus
    every DiagnosticReport version (_history). Returns (n resources checked, problems)."""
    n, problems = 0, []
    for res in fhir.everything(store, files):
        n += 1
        problems.extend(check_resource(res))
    for r in store.reports.values():
        for v in r["versions"]:
            b = fhir.document_bundle(store, r, v, files)
            n += 1
            problems.extend(check_resource(b))
            if fhir.is_diagnostic(r) and v["version"] != r["current_version"]:
                n += 1
                problems.extend(check_resource(fhir.diagnostic_report(store, r, v, files)))
    return n, problems


# ------------------------------------------------------------------------ over HTTP
def _get(url, token=None):
    req = urllib.request.Request(url, headers={"Accept": "application/fhir+json",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_http(url, token):
    """Fetch /fhir/metadata, one search per type, one $document and one _history and check them. (n, problems)."""
    base = url.rstrip("/") + "/fhir"
    n, problems = 0, []

    def check(where, fetch):
        nonlocal n
        try:
            res = fetch()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            problems.append(f"{where}: request failed: {exc}")
            return None
        n += 1
        problems.extend(f"{where}: {p}" for p in check_resource(res))
        return res

    check("GET /fhir/metadata", lambda: _get(base + "/metadata"))
    for t in fhir.TYPES:
        check(f"GET /fhir/{t}", lambda t=t: _get(f"{base}/{t}?_count=50", token))
    drs = check("GET /fhir/DiagnosticReport?status=amended", lambda: _get(base + "/DiagnosticReport?status=amended", token))
    rid = None
    for e in (drs or {}).get("entry") or []:
        rid = e["resource"]["id"]
        break
    if not rid:
        first = _get(base + "/DiagnosticReport?_count=1", token).get("entry") or []
        rid = first[0]["resource"]["id"] if first else None
    if rid:
        check(f"GET /fhir/DiagnosticReport/{rid}/$document", lambda: _get(f"{base}/DiagnosticReport/{rid}/$document", token))
        check(f"GET /fhir/DiagnosticReport/{rid}/_history", lambda: _get(f"{base}/DiagnosticReport/{rid}/_history", token))
    else:
        problems.append("no DiagnosticReport served")
    return n, problems


# ------------------------------------------------------------------------ CLI
def run(data_dir=None, url=None, token_file=None, out=sys.stdout):
    """The CLI's work; returns the exit code."""
    files = paths.layout(data_dir)
    if not files["store"].exists():
        print(f"{files['store']} missing: run python -m his_mock.build first", file=out)
        print("CONFORMANCE FAILED: 1 problems", file=out)
        return 1
    from ..model import Store
    store = Store.load(files["store"])
    n, problems = check_store(store, files)
    if url:
        tf = Path(token_file) if token_file else files["token"]
        token = tf.read_text(encoding="utf-8").strip() if tf.exists() else None
        if not token:
            problems.append(f"token file {tf} missing or empty")
        else:
            n2, p2 = check_http(url, token)
            n += n2
            problems.extend(p2)
    if n == 0:
        problems.append("no resources checked")
    if problems:
        for p in problems[:50]:
            print(p, file=out)
        print(f"CONFORMANCE FAILED: {len(problems)} problems", file=out)
        return 1
    print(f"CONFORMANCE OK: {n} resources checked", file=out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m his_mock.eval.conformance",
                                 description="NRCeS v6.5.0 light-schema conformance of the mock hospital's FHIR API")
    ap.add_argument("--data", help="data directory (default data/his_mock or $TB_HIS_MOCK_DATA)")
    ap.add_argument("--url", help="also check the running API, e.g. http://127.0.0.1:7130")
    ap.add_argument("--token-file", help="bearer token file (default <data>/token)")
    a = ap.parse_args(argv)
    return run(a.data, a.url, a.token_file)


if __name__ == "__main__":
    sys.exit(main())
