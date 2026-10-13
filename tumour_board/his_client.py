"""HIS adapter (plan item V2-3.1): how Vaidyx-TB reads a hospital information system. Read only; nothing is ever written back.

Two transports behind one async interface (HISClient):

  FHIRClient     FHIR R4 in NRCeS (ABDM) shapes: the mock hospital (his_mock, 127.0.0.1:7130/fhir) or a real HIS. Bearer token
                 in the Authorization header only (never in a URL, never logged); the token is only ever sent to the HIS's own
                 origin.
  MCPHISClient   the 12 Oct MCP connector (connectors.py, tools find_patient / list_records / fetch_record), thinner: patients,
                 records as notes and their files; no encounters, orders, imaging or referrals.

    ping()                         {"ok", "name", "fhir_version", "token_ok", "error"}; never raises
    find_patient(identifier)       UHID (permanent or temporary), IP No., OP No., ABHA number or address -> Patient dict or None
    similar(patient_id)            other registrations of the same person to link (never merged)
    encounters(patient_id)         OP visits and IP admissions, oldest first, with ward / bed history
    reports(patient_id, since)     one dict per report VERSION (DocumentReference), joined with its DiagnosticReport version,
                                   Provenance (signature), ServiceRequest, Specimen, ImagingStudy and Observations
    open_orders(patient_id)        orders without a report yet (ordered / scheduled / sample collected / cancelled)
    document(ref)                  the PDF bytes of a DocumentReference, checked against the HIS's sha256
    imaging_study(ref)             the study, its viewer and DICOMweb URLs (humans view the images; no model reads them)
    referrals(patient_id)          inter-department referrals
    hospital()                     the hospital and its departments

Every method except ping() raises HISError (a plain message, no stack, never the token) on a connection, HTTP, token or shape
problem; nothing partially trusted is returned. The invariant (project rules): structured HIS values (Observations, conclusions,
codes) are candidates only; Vaidyx-TB checks every one against the report text, and the PDF wins.

Settings: <DATA_ROOT>/his.json {"kind": "fhir"|"mcp"|"none", "label", "url", "token", "token_file", "connector", "enabled"},
environment overrides TB_HIS_URL, TB_HIS_TOKEN, TB_HIS_TOKEN_FILE; without the file the demo's mock hospital is used.
Code tables (document type, Observation -> fact): protocols/his_codes.json.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import httpx

from . import config

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_LABEL = "Vaidyx Demo Hospital HIS (SYNTHETIC)"
DEFAULT_URL = "http://127.0.0.1:7130"
KINDS = ("fhir", "mcp", "none")
REFERRAL_SNOMED = "3457005"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
MAX_PAGES = 50
READ_CONCURRENCY = 8
_URL = re.compile(r"^https?://[^\s/]+(/\S*)?$")


class HISError(Exception):
    """A plain-English problem talking to the HIS (connection, HTTP status, token, unexpected answer). Never carries the token."""


# ---------------------------------------------------------------------------------------------------- code tables
@lru_cache(maxsize=1)
def codes() -> dict:
    """protocols/his_codes.json with the label patterns compiled (loaded once)."""
    d = json.loads((config.PROTOCOL_DIR / "his_codes.json").read_text())
    d["_label_rx"] = [(re.compile(p, re.I), f) for p, f in d.get("fact_by_label") or []]
    return d


def _code_of(code) -> str:
    if isinstance(code, dict):
        return str(code.get("code") or "")
    return str(code or "")


def _family_pick(title: str, filename: str, family: list) -> tuple[str, str]:
    """The member of a document-type family named by the title / filename keywords (doctype.keyword_type), or ("", "")."""
    from . import doctype
    kw = doctype.keyword_type([title or ""], filename or "")
    scores = {t: s for t, s in (kw.get("scores") or {}).items() if t in family}
    if not scores:
        return "", ""
    top = max(scores.values())
    best = [t for t, s in scores.items() if s == top]
    if len(best) != 1:
        return "", ""
    ev = next((e for e in kw["evidence"] if e["type"] == best[0]), {})
    return best[0], f"keyword '{ev.get('keyword', best[0])}' in the {'filename' if ev.get('where') == 'filename' else 'title'}"


def doc_type_for(code, category=(), title: str = "", filename: str = "", modality: str = "") -> tuple[str, str]:
    """Our document type for a HIS report or document, and how it was decided.

    `code`: the report's LOINC (a code string or a {"system", "code"} dict); `category`: its category codes (strings or dicts);
    `title`: the report title; `filename`: the document's file name; `modality`: the DICOM modality of its ImagingStudy.
    LOINC first (a code naming one of our types), then the pathology family or imaging modality, then the title keywords."""
    t = codes()
    c = _code_of(code)
    cats = [_code_of(x) for x in category or []]
    if c in t["doc_type_by_loinc"]:
        return t["doc_type_by_loinc"][c], f"LOINC {c}"
    fam = t["pathology_family"]
    if c in fam["loinc"]:
        pick, why = _family_pick(title, filename, fam["types"])
        if pick:
            return pick, f"LOINC {c} (pathology) and {why}"
        return fam["default"], f"LOINC {c} (pathology); no narrower keyword, so {fam['default']}"
    img = t["imaging"]
    if c in img["loinc"]:
        for x in cats:
            if x in img["category_snomed"]:
                return img["category_snomed"][x], f"LOINC {c} (imaging) and SNOMED category {x}"
        if modality and modality.upper() in img["dicom_modality"]:
            return img["dicom_modality"][modality.upper()], f"LOINC {c} (imaging) and DICOM modality {modality.upper()}"
        pick, why = _family_pick(title, filename, img["types"])
        if pick:
            return pick, f"LOINC {c} (imaging) and {why}"
        return img["default"], f"LOINC {c} (imaging); modality not named"
    from . import doctype
    kw = doctype.keyword_type([title or ""], filename or "")
    if kw.get("type"):
        ev = next((e for e in kw["evidence"] if e["type"] == kw["type"]), {})
        return kw["type"], f"keyword '{ev.get('keyword', kw['type'])}' (no known code)"
    return "", "no known code and no keyword"


def fact_for(code, label: str = "") -> str:
    """The fact id (facts.json) an Observation carries: LOINC first, then the printed label patterns; "" for anything else."""
    t = codes()
    c = _code_of(code)
    if c and c in t["fact_by_loinc"]:
        return t["fact_by_loinc"][c]
    lab = (label or "").strip()
    if lab:
        for rx, f in t["_label_rx"]:
            if rx.search(lab):
                return f
    return ""


# ---------------------------------------------------------------------------------------------------- small helpers
def _parse_time(s):
    """An aware datetime from an ISO date or date-time (a date or a naive time is taken as IST); None when unparsable."""
    if not s:
        return None
    v = str(s).strip().replace("Z", "+00:00")
    if " " in v and "T" in v:
        v = v.replace(" ", "+")             # '+05:30' that arrived as a space
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=IST)


def _iso(dt) -> str:
    return dt.isoformat(timespec="seconds")


def _ref_id(reference: str, rtype: str = "") -> str:
    r = str(reference or "")
    if rtype and r.startswith(rtype + "/"):
        r = r[len(rtype) + 1:]
    return r.split("/_history/")[0].rsplit("/", 1)[-1]


def _ref(x) -> str:
    return (x or {}).get("reference") or "" if isinstance(x, dict) else ""


def _person(x):
    if not isinstance(x, dict) or not (x.get("reference") or x.get("display")):
        return None
    return {"ref": x.get("reference") or "", "name": x.get("display") or ""}


def _first(lst):
    return (lst or [None])[0]


def _ext(res, suffix):
    """The first extension of `res` whose url ends with `suffix`."""
    return next((e for e in res.get("extension") or [] if str(e.get("url", "")).endswith(suffix)), None)


def _ext_value(res, suffix):
    e = _ext(res, suffix)
    if not e:
        return None
    for k, v in e.items():
        if k.startswith("value"):
            return v.get("text") if isinstance(v, dict) and "text" in v else v
    return None


def _id_type(i) -> str:
    return next((c.get("code") or "" for c in ((i.get("type") or {}).get("coding") or [])), "")


def _accession(res) -> str:
    for i in res.get("identifier") or []:
        if _id_type(i) == "ACSN" or str(i.get("system", "")).endswith("/accession"):
            return i.get("value") or ""
    return ""


def _concept_code(c):
    """The first coding of a CodeableConcept as {"system", "code", "display"}, or None."""
    cd = _first((c or {}).get("coding"))
    if not cd:
        return None
    return {"system": cd.get("system") or "", "code": cd.get("code") or "", "display": cd.get("display") or ""}


def _loinc(c):
    """The LOINC coding of a CodeableConcept (else its first coding)."""
    for cd in (c or {}).get("coding") or []:
        if cd.get("system") == LOINC:
            return {"system": LOINC, "code": cd.get("code") or "", "display": cd.get("display") or ""}
    return _concept_code(c)


def _slug(s: str, n: int = 80) -> str:
    return (re.sub(r"[^A-Za-z0-9]+", "_", str(s or "")).strip("_").lower() or "document")[:n].rstrip("_")


def _number(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _value_text(o) -> str:
    q = o.get("valueQuantity")
    if isinstance(q, dict) and "value" in q:
        s = (q.get("comparator") or "") + _number(q["value"])
        unit = q.get("unit") or q.get("code") or ""
        return f"{s} {unit}".strip()
    for k in ("valueString", "valueBoolean", "valueInteger", "valueDateTime"):
        if k in o:
            return str(o[k])
    cc = o.get("valueCodeableConcept")
    if isinstance(cc, dict):
        return cc.get("text") or ((_first(cc.get("coding")) or {}).get("display") or "")
    return ""


def _status(s) -> str:
    s = str(s or "").strip()
    if s == "entered-in-error":
        return "cancelled"
    return s if s in ("preliminary", "final", "amended", "corrected", "cancelled", "registered", "partial") else "unknown"


def _date_part(s) -> str:
    return str(s or "")[:10]


def _age(dob: str):
    try:
        b = date.fromisoformat(dob)
    except (TypeError, ValueError):
        return None
    t = date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


# ---------------------------------------------------------------------------------------------------- resource -> dict
def identifier_kind(i: dict) -> str:
    """uhid | abha | abha_address | pmjay | ip_no | op_no | accession | "" for a FHIR identifier."""
    t = _id_type(i)
    system = str(i.get("system") or "")
    text = str((i.get("type") or {}).get("text") or "")
    if t == "MR" or system.endswith("/uhid"):
        return "uhid"
    if t == "ABHA" or "healthid" in system or system.endswith("/abha-address"):
        if "@" in str(i.get("value") or "") or "address" in text.lower() or system.endswith("/abha-address"):
            return "abha_address"
        return "abha"
    if t == "PMJAY" or "pmjay" in system:
        return "pmjay"
    if system.endswith("/ip-no"):
        return "ip_no"
    if system.endswith("/op-no"):
        return "op_no"
    if t == "ACSN":
        return "accession"
    return ""


def patient_dict(p: dict) -> dict:
    """A FHIR Patient as the Patient dict (no matched_on / similar)."""
    idents, uhid, kind = [], "", ""
    for i in p.get("identifier") or []:
        k = identifier_kind(i)
        if k in ("uhid", "abha", "abha_address", "pmjay") and i.get("value"):
            idents.append({"kind": k, "value": i["value"]})
            if k == "uhid" and not uhid:
                uhid = i["value"]
                if i.get("use") == "temp":
                    kind = "temporary"
    ext = _ext_value(p, "registration-kind")
    kind = ext if ext in ("permanent", "temporary", "duplicate") else (kind or "permanent")
    pick = lambda k: next((x["value"] for x in idents if x["kind"] == k), "")
    name = next((n.get("text") or " ".join((n.get("given") or []) + [n.get("family") or ""]).strip()
                 for n in p.get("name") or [] if n), "")
    dob = p.get("birthDate") or ""
    meta = p.get("meta") or {}
    return {"id": p.get("id") or "", "ref": f"Patient/{p.get('id')}", "uhid": uhid, "registration_kind": kind,
            "name": name, "sex": {"female": "F", "male": "M"}.get(p.get("gender"), ""), "dob": dob, "age": _age(dob),
            "abha": pick("abha"), "abha_address": pick("abha_address"), "pmjay_id": pick("pmjay"),
            "phone": next((t.get("value") or "" for t in p.get("telecom") or [] if t.get("system") == "phone"), ""),
            "identifiers": idents, "registered_on": _date_part(meta.get("lastUpdated")),
            "last_updated": meta.get("lastUpdated") or ""}


_WARD = re.compile(r"^(.*?),\s*bed\s+(.+)$", re.I)


def encounter_dict(e: dict) -> dict:
    cls = (e.get("class") or {}).get("code") or ""
    kind = "IP" if cls == "IMP" else "OP" if cls == "AMB" else ""
    number = next((i.get("value") or "" for i in e.get("identifier") or [] if _id_type(i) == "VN"),
                  (_first(e.get("identifier")) or {}).get("value") or "")
    if not kind:
        kind = "IP" if number.upper().startswith("IP") else "OP" if number.upper().startswith("OP") else ""
    st = ((e.get("serviceType") or {}).get("text") or "")
    dept = ((e.get("serviceProvider") or {}).get("display") or "") or st.split(",")[0].strip()
    unit = st.split(",", 1)[1].strip() if "," in st else ""
    consultant = next((_person(p.get("individual")) for p in e.get("participant") or [] if p.get("individual")), None)
    wards = []
    for loc in e.get("location") or []:
        disp = (loc.get("location") or {}).get("display") or ""
        m = _WARD.match(disp)
        per = loc.get("period") or {}
        wards.append({"ward": (m.group(1) if m else disp).strip(), "bed": (m.group(2) if m else "").strip(),
                      "from": per.get("start") or "", "to": per.get("end") or "",
                      "reason": _ext_value(loc, "transfer-reason") or ""})
    pre = None
    pe = _ext(e, "pmjay-preauth")
    if pe:
        sub = {x.get("url"): x for x in pe.get("extension") or []}
        st_ = (sub.get("status") or {}).get("valueCodeableConcept") or {}
        pre = {"status": st_.get("text") or (sub.get("status") or {}).get("valueString") or "",
               "date": (sub.get("date") or {}).get("valueDate") or ""}
    per = e.get("period") or {}
    return {"id": e.get("id") or "", "ref": f"Encounter/{e.get('id')}", "kind": kind, "number": number,
            "status": e.get("status") or "", "department": dept, "unit": unit, "consultant": consultant,
            "start": per.get("start") or "", "end": per.get("end") or "", "ward_history": wards, "pmjay_preauth": pre,
            "last_updated": (e.get("meta") or {}).get("lastUpdated") or ""}


def imaging_study_dict(s: dict) -> dict:
    uid = next((i.get("value") or "" for i in s.get("identifier") or [] if i.get("system") == "urn:dicom:uid"), "")
    if uid.startswith("urn:oid:"):
        uid = uid[len("urn:oid:"):]
    mod = _first(s.get("modality")) or {}
    return {"id": s.get("id") or "", "ref": f"ImagingStudy/{s.get('id')}", "study_uid": uid, "accession": _accession(s),
            "modality": mod.get("code") or "", "status": s.get("status") or "",
            "viewer_url": _ext_value(s, "viewer-url") or "", "dicomweb_url": _ext_value(s, "dicomweb-study-url") or "",
            "series": int(s.get("numberOfSeries") or len(s.get("series") or [])),
            "instances": int(s.get("numberOfInstances") or 0), "started": s.get("started") or "",
            "description": s.get("description") or "", "last_updated": (s.get("meta") or {}).get("lastUpdated") or ""}


def _is_referral(sr: dict) -> bool:
    return any(cd.get("code") == REFERRAL_SNOMED for c in sr.get("category") or [] for cd in c.get("coding") or [])


def _enc_fields(enc_ref: str, encs: dict) -> dict:
    e = encs.get(_ref_id(enc_ref, "Encounter")) if enc_ref else None
    ed = encounter_dict(e) if e else None
    return {"encounter_ref": enc_ref or "", "encounter_number": ed["number"] if ed else "",
            "encounter_kind": ed["kind"] if ed else ""}


def referral_dict(sr: dict, encs: dict) -> dict:
    enc = _ref((sr.get("encounter")))
    return {"id": sr.get("id") or "", "ref": f"ServiceRequest/{sr.get('id')}",
            "encounter_ref": enc, "encounter_number": _enc_fields(enc, encs)["encounter_number"],
            "from_department": (sr.get("requester") or {}).get("display") or "",
            "to_department": ((_first(sr.get("performer")) or {}).get("display") or ""),
            "status": {"active": "requested", "completed": "accepted"}.get(sr.get("status"), sr.get("status") or ""),
            "reason": ((_first(sr.get("reasonCode")) or {}).get("text") or ""),
            "requested": sr.get("authoredOn") or "", "accepted": _ext_value(sr, "referral-accepted-on") or "",
            "last_updated": (sr.get("meta") or {}).get("lastUpdated") or ""}


def specimen_dict(sp: dict | None):
    if not sp:
        return None
    block = next((i.get("value") or "" for i in sp.get("identifier") or [] if str(i.get("system", "")).endswith("/block-no")
                  or "block" in str((i.get("type") or {}).get("text", "")).lower()), "")
    return {"ref": f"Specimen/{sp.get('id')}", "collected": (sp.get("collection") or {}).get("collectedDateTime") or "",
            "received": sp.get("receivedTime") or "", "barcode": (sp.get("accessionIdentifier") or {}).get("value") or "",
            "block_no": block}


def order_dict(sr: dict, specimen: dict | None, encs: dict, study: dict | None = None) -> dict:
    status = sr.get("status") or ""
    if status == "revoked":
        stage = "cancelled"
    elif sr.get("specimen") or specimen:
        stage = "sample_collected"
    elif sr.get("occurrenceDateTime") or (study and study.get("status") == "registered"):
        stage = "scheduled"
    else:
        stage = "ordered"
    code = sr.get("code") or {}
    doc_type, _ = doc_type_for(_loinc(code), [], code.get("text") or "")
    if not doc_type and study:
        doc_type = codes()["imaging"]["dicom_modality"].get(((_first(study.get("modality")) or {}).get("code") or ""), "")
    if not doc_type:
        cats = [cd.get("code") for c in sr.get("category") or [] for cd in c.get("coding") or []]
        doc_type = next((codes()["order_category_snomed"][x] for x in cats if x in codes().get("order_category_snomed", {})), "")
    enc = _ref(sr.get("encounter"))
    return {"id": sr.get("id") or "", "ref": f"ServiceRequest/{sr.get('id')}", "accession": _accession(sr),
            "test": code.get("text") or "", "code": _concept_code(code), "doc_type": doc_type,
            "status": status, "stage": stage, "scheduled_for": sr.get("occurrenceDateTime") or "",
            "authored_on": sr.get("authoredOn") or "", "specimen": specimen_dict(specimen),
            "performer_department": ((_first(sr.get("performer")) or {}).get("display") or ""),
            "requester_department": (sr.get("requester") or {}).get("display") or "",
            **_enc_fields(enc, encs),
            "note": " ".join(n.get("text") or "" for n in sr.get("note") or []).strip(),
            "last_updated": (sr.get("meta") or {}).get("lastUpdated") or ""}


def observation_dict(o: dict) -> dict:
    code = o.get("code") or {}
    c = _loinc(code)
    label = code.get("text") or (c or {}).get("display") or ""
    return {"id": o.get("id") or "", "code": c, "label": label, "fact": fact_for(c, label), "value": _value_text(o),
            "status": o.get("status") or ""}


def signature_dict(prov: dict | None):
    if not prov:
        return None
    sig = _first(prov.get("signature")) or {}
    block = ""
    if sig.get("data"):
        try:
            block = base64.b64decode(sig["data"]).decode("utf-8", "replace")
        except (ValueError, TypeError):
            block = ""
    who = sig.get("who") or ((_first(prov.get("agent")) or {}).get("who"))
    return {"ref": f"Provenance/{prov.get('id')}", "signer": _person(who), "signed_at": sig.get("when") or prov.get("recorded") or "",
            "ca": _ext_value(prov, "signature-ca") or "", "serial": _ext_value(prov, "signature-certificate-serial") or "",
            "document_hash": _ext_value(prov, "signature-document-hash") or "",
            "verification_status": _ext_value(prov, "signature-verification-status") or "", "block": block}


def _hash_matches(sig: dict | None, sha256: str):
    """Whether the signed document hash equals the HIS's sha256 of the PDF (None when either is missing)."""
    if not sig or not sig.get("document_hash") or not sha256:
        return None
    return sig["document_hash"].lower() == sha256.lower()


def _doc_version(doc: dict) -> int:
    v = (doc.get("meta") or {}).get("versionId")
    if v and str(v).isdigit():
        return int(v)
    m = re.search(r"-v(\d+)$", ((doc.get("masterIdentifier") or {}).get("value") or doc.get("id") or ""))
    return int(m.group(1)) if m else 1


def _doc_report_id(doc: dict) -> str:
    rel = next((_ref(r) for r in ((doc.get("context") or {}).get("related") or []) if _ref(r).startswith("DiagnosticReport/")), "")
    if rel:
        return _ref_id(rel, "DiagnosticReport")
    mi = (doc.get("masterIdentifier") or {}).get("value") or ""
    if mi:
        return re.sub(r"-v\d+$", "", mi)
    return re.sub(r"^doc-|-v\d+$", "", doc.get("id") or "")


def _attachment(doc: dict) -> dict:
    return ((_first(doc.get("content")) or {}).get("attachment")) or {}


class _Index:
    """Resources by (type, id), plus DiagnosticReport versions and Provenance by target."""

    def __init__(self, resources=()):
        self.res, self.dr_versions, self.prov_by_target = {}, {}, {}
        for r in resources:
            self.add(r)

    def add(self, r):
        if not isinstance(r, dict) or not r.get("resourceType") or not r.get("id"):
            return
        t, i = r["resourceType"], r["id"]
        self.res[(t, i)] = r
        if t == "DiagnosticReport":
            v = (r.get("meta") or {}).get("versionId")
            if v and str(v).isdigit():
                self.dr_versions.setdefault(i, {})[int(v)] = r
        if t == "Provenance":
            for tg in r.get("target") or []:
                self.prov_by_target[_ref(tg)] = r

    def get(self, reference: str):
        if not reference or "/" not in reference:
            return None
        t, rest = reference.split("/", 1)
        return self.res.get((t, rest.split("/_history/")[0]))

    def of(self, rtype):
        return [r for (t, _), r in self.res.items() if t == rtype]

    def encounters(self):
        return {r["id"]: r for r in self.of("Encounter")}


def build_report(doc: dict, idx: _Index, current_version: dict) -> dict:
    """The report dict of one DocumentReference (one report version) from the resources in `idx`. `current_version`:
    {report id: highest version number}."""
    rid = _doc_report_id(doc)
    version = _doc_version(doc)
    related = next((_ref(r) for r in ((doc.get("context") or {}).get("related") or []) if _ref(r).startswith("DiagnosticReport/")), "")
    dr_cur = idx.get(related) if related else None
    dr = (idx.dr_versions.get(rid) or {}).get(version)
    if dr is None and dr_cur is not None and _doc_version(dr_cur) == version:
        dr = dr_cur
    kind = "diagnostic" if related else "note"
    att = _attachment(doc)
    title = doc.get("description") or ((dr or dr_cur or {}).get("code") or {}).get("text") or att.get("title") or ""
    code = _loinc(doc.get("type")) or _loinc((dr or dr_cur or {}).get("code"))
    cats = [cd.get("code") for c in (dr or dr_cur or {}).get("category") or [] for cd in c.get("coding") or []]
    basis_dr = dr or dr_cur or {}
    study = idx.get(_ref(_first(basis_dr.get("imagingStudy"))))
    modality = ((_first((study or {}).get("modality")) or {}).get("code") or "")
    url = att.get("url") or ""
    doc_type, basis = doc_type_for(code, cats, title, url.rsplit("/", 1)[-1] if url else "", modality)
    if dr is not None:
        status = _status(dr.get("status"))
    else:
        status = _status(doc.get("docStatus"))
    if doc.get("status") == "entered-in-error":
        status = "cancelled"
    enc_ref = _ref(_first((doc.get("context") or {}).get("encounter"))) or _ref(basis_dr.get("encounter"))
    order_ref = _ref(_first(basis_dr.get("basedOn")))
    prov = idx.prov_by_target.get(f"DocumentReference/{doc.get('id')}")
    if prov is None and related:
        prov = idx.prov_by_target.get(f"{related}/_history/{version}")
    author = next((_person(a) for a in doc.get("author") or [] if _ref(a).startswith("Practitioner/")), None)
    if author is None and dr is not None:
        author = _person(_first(dr.get("resultsInterpreter")))
    performer = next((a.get("display") or "" for a in (basis_dr.get("performer") or []) if _ref(a).startswith("Organization/")), "") \
        or next((a.get("display") or "" for a in doc.get("author") or [] if _ref(a).startswith("Organization/")), "")
    obs = []
    if dr is not None:
        for r in dr.get("result") or []:
            o = idx.get(_ref(r))
            if o:
                obs.append(observation_dict(o))
    signature = signature_dict(prov)
    if signature is not None:
        signature["hash_matches"] = _hash_matches(signature, _ext_value(doc, "document-sha256") or "")
    last = max((x for x in ((doc.get("meta") or {}).get("lastUpdated"), (dr or {}).get("meta", {}).get("lastUpdated")) if x),
               key=lambda x: _parse_time(x) or datetime.min.replace(tzinfo=IST), default="")
    return {"id": rid, "version": version, "kind": kind, "ref": related or None,
            "document_ref": f"DocumentReference/{doc.get('id')}",
            "current": doc.get("status") != "superseded" and version >= current_version.get(rid, version),
            "title": title, "code": code, "category": [c for c in cats if c], "doc_type": doc_type, "doc_type_basis": basis,
            "status": status, "issued": (dr or {}).get("issued") or doc.get("date") or att.get("creation") or "",
            "effective": basis_dr.get("effectiveDateTime") or "",
            **_enc_fields(enc_ref, idx.encounters()),
            "accession": _accession(basis_dr) or _accession(doc), "order_ref": order_ref or None,
            "performer_department": performer, "reported_by": author, "signature": signature,
            "observations": obs, "imaging_study_ref": _ref(_first(basis_dr.get("imagingStudy"))) or None,
            "conclusion": (dr or {}).get("conclusion") or "", "amendment_note": _ext_value(dr or {}, "amendment-note") or "",
            "document": {"url": url, "sha256": _ext_value(doc, "document-sha256") or "", "sha1_b64": att.get("hash") or "",
                         "size": att.get("size"), "content_type": att.get("contentType") or "", "title": att.get("title") or "",
                         "creation": att.get("creation") or ""},
            "last_updated": last}


# ---------------------------------------------------------------------------------------------------- the interface
class HISClient:
    """The HIS interface every transport implements (see the module docstring for the shapes)."""
    kind = ""
    label = ""

    async def ping(self) -> dict:
        raise NotImplementedError

    async def find_patient(self, identifier: str) -> dict | None:
        raise NotImplementedError

    async def similar(self, patient_id: str) -> list[dict]:
        return []

    async def encounters(self, patient_id: str) -> list[dict]:
        return []

    async def reports(self, patient_id: str, since: str | None = None) -> list[dict]:
        return []

    async def open_orders(self, patient_id: str) -> list[dict]:
        return []

    async def document(self, ref: str) -> dict:
        raise NotImplementedError

    async def imaging_study(self, ref: str) -> dict | None:
        return None

    async def referrals(self, patient_id: str) -> list[dict]:
        return []

    async def hospital(self) -> dict:
        return {"name": self.label, "departments": []}


def _check_sha(data: bytes, sha256: str, sha1_b64: str, what: str):
    if sha256 and hashlib.sha256(data).hexdigest() != sha256.lower():
        raise HISError(f"checksum mismatch for {what}: the bytes received do not match the HIS's sha256")
    if sha1_b64 and base64.b64encode(hashlib.sha1(data).digest()).decode("ascii") != sha1_b64:
        raise HISError(f"checksum mismatch for {what}: the bytes received do not match the attachment hash")


class FHIRClient(HISClient):
    """FHIR R4 transport. `url`: the HIS root (http://127.0.0.1:7130, FHIR at /fhir) or the FHIR base itself (a path other than
    "/"). `transport`: an httpx transport (tests pass httpx.MockTransport)."""
    kind = "fhir"

    def __init__(self, url: str, token: str, label: str = "", timeout: float = 30, transport=None):
        url = str(url or "").strip().rstrip("/")
        if not _URL.match(url):
            raise HISError("the HIS url must start with http:// or https://")
        sp = urlsplit(url)
        self.origin = f"{sp.scheme}://{sp.netloc}"
        self.fhir_base = url if sp.path not in ("", "/") else url + "/fhir"
        self.label = label or DEFAULT_LABEL
        self._token = token or ""
        self._timeout = timeout
        self._transport = transport

    def __repr__(self):
        return f"FHIRClient({self.fhir_base!r})"   # never the token

    # ---- HTTP
    def _client(self):
        headers = {"Accept": "application/fhir+json, application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        kw = {"transport": self._transport} if self._transport is not None else {}
        return httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(self._timeout, connect=min(10, self._timeout)),
                                 follow_redirects=False, **kw)

    def _url(self, path: str, params=None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            u = path
        elif path.startswith("/"):
            u = self.origin + path
        else:
            u = f"{self.fhir_base}/{path}"
        if params:
            q = "&".join(f"{quote(str(k), safe='_:')}={quote(str(v), safe='/:@,|-._~')}" for k, v in params)
            u += ("&" if "?" in u else "?") + q
        return u

    def _same_origin(self, url: str) -> bool:
        sp = urlsplit(url)
        return f"{sp.scheme}://{sp.netloc}" == self.origin

    async def _send(self, c, url: str):
        if not self._same_origin(url):
            raise HISError("the HIS pointed to another server; Vaidyx-TB only sends its token to the configured HIS")
        what = urlsplit(url).path
        try:
            r = await c.get(url)
        except httpx.TimeoutException:
            raise HISError(f"the HIS at {self.origin} did not answer in time ({what})") from None
        except httpx.HTTPError as e:
            raise HISError(f"cannot reach the HIS at {self.origin}: {type(e).__name__}") from None
        if r.status_code in (401, 403):
            raise HISError(f"the HIS refused the token (HTTP {r.status_code}); check the HIS token in the settings")
        return r

    async def _get_json(self, c, path: str, params=None, allow_404=False):
        url = self._url(path, params)
        what = urlsplit(url).path
        r = await self._send(c, url)
        if r.status_code == 404 and allow_404:
            return None
        if r.status_code >= 400:
            diag = ""
            try:
                diag = "; ".join(i.get("diagnostics") or "" for i in r.json().get("issue") or [])[:200]
            except Exception:
                pass
            raise HISError(f"the HIS answered HTTP {r.status_code} for {what}" + (f": {diag}" if diag else ""))
        try:
            d = r.json()
        except ValueError:
            raise HISError(f"the HIS answer for {what} is not JSON") from None
        if not isinstance(d, dict) or not d.get("resourceType"):
            raise HISError(f"the HIS answer for {what} is not a FHIR resource")
        return d

    async def _bundle(self, c, path: str, params=None, allow_404=False) -> list[dict]:
        """Every resource of a searchset (following `next` links on the same server)."""
        b = await self._get_json(c, path, params, allow_404=allow_404)
        if b is None:
            return []
        if b.get("resourceType") != "Bundle":
            raise HISError(f"the HIS answer for {path} is not a Bundle")
        out = [e.get("resource") for e in b.get("entry") or [] if isinstance(e.get("resource"), dict)]
        for _ in range(MAX_PAGES):
            nxt = next((link.get("url") for link in b.get("link") or [] if link.get("relation") == "next"), None)
            if not nxt:
                break
            b = await self._get_json(c, nxt)
            out += [e.get("resource") for e in b.get("entry") or [] if isinstance(e.get("resource"), dict)]
        return out

    async def _read(self, c, reference: str):
        """One resource by `Type/id`, None when the HIS does not know it."""
        return await self._get_json(c, reference, allow_404=True)

    async def _read_many(self, c, refs) -> list:
        sem = asyncio.Semaphore(READ_CONCURRENCY)

        async def one(r):
            async with sem:
                return await self._read(c, r)
        return await asyncio.gather(*(one(r) for r in refs))

    # ---- interface
    async def ping(self) -> dict:
        """Read the CapabilityStatement (no token needed), then one token-protected search (Patient?_count=0)."""
        out = {"ok": False, "name": "", "fhir_version": "", "token_ok": None, "error": ""}
        try:
            async with self._client() as c:
                cs = await self._get_json(c, "metadata")
                if cs.get("resourceType") != "CapabilityStatement":
                    raise HISError("the HIS metadata is not a CapabilityStatement")
                out["name"] = (cs.get("software") or {}).get("name") or cs.get("title") or cs.get("name") or ""
                out["fhir_version"] = cs.get("fhirVersion") or ""
                try:
                    await self._get_json(c, "Patient", [("_count", "0")])
                except HISError as e:
                    if "refused the token" in str(e):
                        out["token_ok"] = False
                    raise
                out["token_ok"] = True
            out["ok"] = True
        except HISError as e:
            out["error"] = str(e)
        return out

    async def find_patient(self, identifier: str) -> dict | None:
        """The registration an exact identifier names: Patient?identifier= first, then the subject of Encounter?identifier= (IP /
        OP No.). Two registrations under one identifier raise HISError; nothing (no name search) returns None."""
        value = str(identifier or "").strip()
        if not value:
            return None
        async with self._client() as c:
            pats = await self._bundle(c, "Patient", [("identifier", value)])
            pats = [p for p in pats if p.get("resourceType") == "Patient"]
            matched_kind = ""
            if len({p.get("id") for p in pats}) > 1:
                raise HISError(f"more than one registration matches {value}; a person must choose")
            if pats:
                pat = pats[0]
                matched_kind = next((identifier_kind(i) for i in pat.get("identifier") or [] if i.get("value") == value), "") or "uhid"
            else:
                encs = [e for e in await self._bundle(c, "Encounter", [("identifier", value)]) if e.get("resourceType") == "Encounter"]
                subjects = {_ref(e.get("subject")) for e in encs if _ref(e.get("subject"))}
                if not subjects:
                    return None
                if len(subjects) > 1:
                    raise HISError(f"more than one registration matches {value}; a person must choose")
                pat = await self._read(c, subjects.pop())
                if not pat or pat.get("resourceType") != "Patient":
                    raise HISError(f"the HIS encounter {value} points to a registration it cannot return")
                e = encs[0]
                matched_kind = next((identifier_kind(i) for i in e.get("identifier") or [] if i.get("value") == value), "")
                if matched_kind not in ("ip_no", "op_no"):
                    matched_kind = "ip_no" if encounter_dict(e)["kind"] == "IP" else "op_no"
            out = patient_dict(pat)
            out["matched_on"] = {"kind": matched_kind, "value": value}
            out["similar"] = await self._similar(c, out["id"])
        return out

    async def _similar(self, c, patient_id: str) -> list[dict]:
        try:
            res = await self._bundle(c, f"Patient/{quote(patient_id, safe='')}/$similar", allow_404=True)
        except HISError as e:
            if "refused the token" in str(e) or "cannot reach" in str(e) or "did not answer" in str(e):
                raise
            return []          # a HIS without the $similar operation: nothing to link
        return [patient_dict(p) for p in res if p.get("resourceType") == "Patient" and p.get("id") != patient_id]

    async def similar(self, patient_id: str) -> list[dict]:
        """Other registrations of the same person (same name, sex and age) for a person to link; never merged."""
        async with self._client() as c:
            return await self._similar(c, patient_id)

    async def encounters(self, patient_id: str) -> list[dict]:
        async with self._client() as c:
            res = await self._bundle(c, "Encounter", [("patient", patient_id)])
        out = [encounter_dict(e) for e in res if e.get("resourceType") == "Encounter"]
        return sorted(out, key=lambda e: (_parse_time(e["start"]) or datetime.max.replace(tzinfo=IST), e["id"]))

    async def _everything(self, c, patient_id: str) -> list[dict]:
        res = await self._bundle(c, f"Patient/{quote(patient_id, safe='')}/$everything", allow_404=True)
        if not res:
            raise HISError(f"the HIS has no registration {patient_id}")
        return res

    async def reports(self, patient_id: str, since: str | None = None) -> list[dict]:
        """One dict per report version. Without `since`: from Patient/$everything (one call), plus one `_history` call per
        DiagnosticReport that has superseded versions and the reads of those versions' Observations (the HIS serves only the
        current version's Observations in searches; superseded ones are read by id from the version's `result`). With `since`
        (an ISO date or date-time; a naive value is IST): the DocumentReference and DiagnosticReport delta searches
        (_lastUpdated=ge), then the joined resources read one by one; only versions changed at or after `since` are returned.
        The DocumentReference's base64 PDF is not kept: document() fetches and checks the bytes."""
        async with self._client() as c:
            if since is None:
                idx = _Index(await self._everything(c, patient_id))
                docs = idx.of("DocumentReference")
            else:
                cut = _parse_time(since)
                if cut is None:
                    raise HISError(f"bad 'since' value {since!r}")
                stamp = _iso(cut)
                drs, docs = await asyncio.gather(
                    self._bundle(c, "DiagnosticReport", [("patient", patient_id), ("_lastUpdated", "ge" + stamp)]),
                    self._bundle(c, "DocumentReference", [("patient", patient_id), ("_lastUpdated", "ge" + stamp)]))
                docs = [d for d in docs if d.get("resourceType") == "DocumentReference"]
                if not drs and not docs:
                    return []
                idx = _Index(drs + docs)
                covered = {_doc_report_id(d) for d in docs}
                if any(dr.get("id") not in covered for dr in drs):
                    # a report changed without a new document version: its current DocumentReference
                    cur = await self._bundle(c, "DocumentReference", [("patient", patient_id), ("status", "current")])
                    ids = {dr.get("id") for dr in drs} - covered
                    for d in cur:
                        if _doc_report_id(d) in ids:
                            docs.append(d)
                            idx.add(d)
                for p in await self._bundle(c, "Provenance", [("patient", patient_id)]):
                    idx.add(p)
                want = set()
                for d in docs:
                    for r in ((d.get("context") or {}).get("related") or []) + ((d.get("context") or {}).get("encounter") or []):
                        want.add(_ref(r))
                want = {w for w in want if w and idx.get(w) is None}
                for got in await self._read_many(c, sorted(want)):
                    idx.add(got)
                want = set()
                for dr in idx.of("DiagnosticReport"):
                    for k in ("basedOn", "specimen", "imagingStudy", "result"):
                        want.update(_ref(x) for x in dr.get(k) or [])
                    want.add(_ref(dr.get("encounter")))
                want = {w for w in want if w and idx.get(w) is None}
                for got in await self._read_many(c, sorted(want)):
                    idx.add(got)
            for d in docs:
                d_att = _attachment(d)
                d_att.pop("data", None)
            # superseded versions of DiagnosticReports: their own status, conclusion and Observations from _history
            need_hist = sorted({_doc_report_id(d) for d in docs
                                if any(_ref(r).startswith("DiagnosticReport/") for r in (d.get("context") or {}).get("related") or [])
                                and _doc_version(d) not in (idx.dr_versions.get(_doc_report_id(d)) or {})})
            for rid in need_hist:
                for h in await self._bundle(c, f"DiagnosticReport/{quote(rid, safe='')}/_history", allow_404=True):
                    if h.get("resourceType") == "DiagnosticReport":
                        v = (h.get("meta") or {}).get("versionId")
                        if v and str(v).isdigit() and int(v) not in idx.dr_versions.get(rid, {}):
                            idx.dr_versions.setdefault(rid, {})[int(v)] = h
            want = {_ref(x) for vs in idx.dr_versions.values() for dr in vs.values() for x in dr.get("result") or []}
            want = {w for w in want if w and idx.get(w) is None}
            for got in await self._read_many(c, sorted(want)):
                idx.add(got)
        cur = {}
        for d in docs:
            rid = _doc_report_id(d)
            cur[rid] = max(cur.get(rid, 0), _doc_version(d))
        out, seen = [], set()
        for d in docs:
            rep = build_report(d, idx, cur)
            key = (rep["id"], rep["version"])
            if key in seen:
                continue
            if since is not None:
                lu = _parse_time(rep["last_updated"])
                if lu is None or lu < _parse_time(since):
                    continue
            seen.add(key)
            out.append(rep)
        first = {}
        for r in out:
            t = _parse_time(r["issued"]) or datetime.max.replace(tzinfo=IST)
            first[r["id"]] = min(first.get(r["id"], t), t)
        return sorted(out, key=lambda r: (first[r["id"]], r["id"], r["version"]))

    async def open_orders(self, patient_id: str) -> list[dict]:
        """Orders with no report yet: active (ordered / scheduled / sample collected) or revoked (cancelled before a report).
        Referrals are never orders (referrals())."""
        async with self._client() as c:
            idx = _Index(await self._everything(c, patient_id))
        reported = {_ref(b) for dr in idx.of("DiagnosticReport") for b in dr.get("basedOn") or []}
        studies = {}
        for s in idx.of("ImagingStudy"):
            for b in s.get("basedOn") or []:
                studies[_ref(b)] = s
        specs = {}
        for sp in idx.of("Specimen"):
            for rq in sp.get("request") or []:
                specs[_ref(rq)] = sp
        encs = idx.encounters()
        out = []
        for sr in idx.of("ServiceRequest"):
            ref = f"ServiceRequest/{sr['id']}"
            if _is_referral(sr) or ref in reported or sr.get("status") not in ("active", "revoked", "on-hold", "draft"):
                continue
            sp = idx.get(_ref(_first(sr.get("specimen")))) or specs.get(ref)
            out.append(order_dict(sr, sp, encs, studies.get(ref)))
        return sorted(out, key=lambda o: (o["authored_on"], o["id"]))

    async def referrals(self, patient_id: str) -> list[dict]:
        async with self._client() as c:
            idx = _Index(await self._everything(c, patient_id))
        encs = idx.encounters()
        out = [referral_dict(sr, encs) for sr in idx.of("ServiceRequest") if _is_referral(sr)]
        return sorted(out, key=lambda r: (r["requested"], r["id"]))

    async def document(self, ref: str) -> dict:
        """The PDF of a DocumentReference: `attachment.data` when present, else GET `attachment.url` on the HIS (bearer header).
        A sha256 extension (or the attachment's SHA-1 hash) that does not match the bytes raises HISError."""
        r = str(ref or "").strip()
        did = _ref_id(r, "DocumentReference")
        if not did:
            raise HISError("no document reference given")
        async with self._client() as c:
            doc = await self._read(c, f"DocumentReference/{quote(did, safe='')}")
            if not doc or doc.get("resourceType") != "DocumentReference":
                raise HISError(f"the HIS has no document {did}")
            att = _attachment(doc)
            if att.get("data"):
                try:
                    data = base64.b64decode(att["data"], validate=True)
                except (ValueError, TypeError):
                    raise HISError(f"the HIS document {did} carries unreadable base64") from None
            elif att.get("url"):
                resp = await self._send(c, self._url(att["url"]))
                if resp.status_code >= 400:
                    raise HISError(f"the HIS answered HTTP {resp.status_code} for the file of document {did}")
                data = resp.content
            else:
                raise HISError(f"the HIS document {did} has neither data nor a url")
        sha = _ext_value(doc, "document-sha256") or ""
        _check_sha(data, sha, att.get("hash") or "", f"document {did}")
        title = att.get("title") or doc.get("description") or did
        return {"ref": f"DocumentReference/{did}", "content": data, "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": att.get("contentType") or "application/octet-stream", "title": title,
                "filename": f"{_slug(title, 60)}_{_slug(did, 40)}.pdf", "size": len(data),
                "creation": att.get("creation") or "", "status": doc.get("status") or "", "doc_status": doc.get("docStatus") or ""}

    async def imaging_study(self, ref: str) -> dict | None:
        sid = _ref_id(str(ref or "").strip(), "ImagingStudy")
        if not sid:
            return None
        async with self._client() as c:
            s = await self._read(c, f"ImagingStudy/{quote(sid, safe='')}")
        if not s:
            return None
        if s.get("resourceType") != "ImagingStudy":
            raise HISError(f"the HIS answer for ImagingStudy/{sid} is not an ImagingStudy")
        return imaging_study_dict(s)

    async def hospital(self) -> dict:
        async with self._client() as c:
            orgs = await self._bundle(c, "Organization")
        orgs = [o for o in orgs if o.get("resourceType") == "Organization"]
        top = next((o for o in orgs if not o.get("partOf")), None)
        depts = []
        for o in orgs:
            if not o.get("partOf"):
                continue
            ty = ((_first(o.get("type")) or {}).get("text") or "").strip()
            depts.append({"name": o.get("name") or "", "group": re.sub(r"\s*department$", "", ty, flags=re.I),
                          "email": next((t.get("value") or "" for t in o.get("telecom") or [] if t.get("system") == "email"), "")})
        return {"name": (top or {}).get("name") or self.label, "departments": sorted(depts, key=lambda d: d["name"])}


# ---------------------------------------------------------------------------------------------------- MCP transport
_AGE_SEX = re.compile(r"(\d{1,3})\s*Y\w*\s*/\s*([MF])", re.I)


class MCPHISClient(HISClient):
    """The 12 Oct MCP connector as a thin HIS: find_patient (tool find_patient, exact patient id only), reports (tool
    list_records: every record a "note" version 1, doc_type from the filename keywords), document (tool fetch_record). No
    encounters, orders, imaging or referrals ([] / None). `client_factory`: a callable returning an httpx client (or an async
    context manager yielding one) per session; tests pass one bound to an in-process MCP app."""
    kind = "mcp"

    def __init__(self, connector: dict, client_factory=None):
        self.connector = dict(connector or {})
        self.label = self.connector.get("label") or self.connector.get("id") or "MCP connector"
        self._factory = client_factory

    def __repr__(self):
        return f"MCPHISClient({self.connector.get('id')!r})"

    def _session(self):
        from . import connectors
        return connectors.session(self.connector, self._factory() if self._factory else None)

    async def _call(self, tool: str, args: dict) -> dict:
        from . import connectors
        try:
            async with self._session() as s:
                return connectors._structured(await s.call_tool(tool, args))
        except HISError:
            raise
        except Exception as e:
            raise HISError(f"the MCP connector {self.connector.get('id', '')} failed on {tool}: {type(e).__name__}") from None

    async def ping(self) -> dict:
        from . import connectors
        pr = await connectors.probe(self.connector, self._factory() if self._factory else None)
        return {"ok": bool(pr.get("ok") and pr.get("usable")), "name": pr.get("server") or self.label, "fhir_version": "",
                "token_ok": True if pr.get("ok") else None, "error": pr.get("error") or pr.get("reason") or ""}

    async def find_patient(self, identifier: str) -> dict | None:
        value = str(identifier or "").strip()
        if not value:
            return None
        hits = [p for p in (await self._call("find_patient", {"query": value})).get("patients") or []
                if str(p.get("patient_id") or "").lower() == value.lower()]
        if not hits:
            return None
        if len(hits) > 1:
            raise HISError(f"more than one registration matches {value}; a person must choose")
        p = hits[0]
        m = _AGE_SEX.search(p.get("age_sex") or "")
        pid = p["patient_id"]
        return {"id": pid, "ref": None, "uhid": pid, "registration_kind": "permanent", "name": p.get("name") or "",
                "sex": m.group(2).upper() if m else "", "dob": "", "age": int(m.group(1)) if m else None,
                "abha": "", "abha_address": "", "pmjay_id": "", "phone": "", "identifiers": [{"kind": "uhid", "value": pid}],
                "registered_on": "", "last_updated": "", "matched_on": {"kind": "uhid", "value": value}, "similar": []}

    async def reports(self, patient_id: str, since: str | None = None) -> list[dict]:
        recs = (await self._call("list_records", {"patient_id": patient_id})).get("records") or []
        out = []
        for r in recs:  # `since` is ignored: the demo HIS has no change feed (a record added late with an older date would be missed); the Case File de-duplicates by document_ref
            fn = r.get("filename") or ""
            doc_type, basis = doc_type_for("", [], "", fn)
            rid = str(r.get("record_id") or "")
            out.append({"id": rid, "version": 1, "kind": "note", "ref": None,
                        "document_ref": f"mcp:{quote(patient_id, safe='')}/{quote(rid, safe='')}", "current": True,
                        "title": fn.rsplit("/", 1)[-1], "code": None, "category": [x for x in [r.get("record_type")] if x],
                        "doc_type": doc_type, "doc_type_basis": basis.replace("(no known code)", "(filename)"),
                        "status": "unknown", "issued": r.get("record_date") or "", "effective": "",
                        "encounter_ref": "", "encounter_number": "", "encounter_kind": "", "accession": "", "order_ref": None,
                        "performer_department": r.get("department") or "", "reported_by": None, "signature": None,
                        "observations": [], "imaging_study_ref": None, "conclusion": "", "amendment_note": "",
                        "document": {"url": "", "sha256": "", "sha1_b64": "", "size": r.get("size"), "content_type": "",
                                     "title": fn.rsplit("/", 1)[-1], "creation": r.get("record_date") or ""},
                        "last_updated": r.get("record_date") or ""})
        return sorted(out, key=lambda x: (x["issued"], x["id"]))

    async def document(self, ref: str) -> dict:
        m = re.match(r"^mcp:([^/]+)/(.+)$", str(ref or ""))
        if not m:
            raise HISError(f"not an MCP record reference: {ref}")
        pid, rid = unquote(m.group(1)), unquote(m.group(2))
        r = await self._call("fetch_record", {"patient_id": pid, "record_id": rid})
        try:
            data = base64.b64decode(r.get("content_base64") or "", validate=True)
        except (ValueError, TypeError):
            raise HISError(f"the MCP record {rid} carries unreadable base64") from None
        _check_sha(data, r.get("sha256") or "", "", f"record {rid}")
        fn = (r.get("filename") or rid).rsplit("/", 1)[-1]
        stem, _, ext = fn.rpartition(".")
        safe = f"{_slug(stem or fn, 80)}.{_slug(ext, 8)}" if stem else _slug(fn, 80)
        return {"ref": ref, "content": data, "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": r.get("mime") or "application/octet-stream", "title": fn, "filename": safe,
                "size": len(data), "creation": r.get("record_date") or "", "status": "current", "doc_status": ""}

    async def hospital(self) -> dict:
        return {"name": self.label, "departments": []}


# ---------------------------------------------------------------------------------------------------- settings
def settings_path() -> Path:
    return Path(config.DATA_ROOT) / "his.json"


def _default_settings() -> dict:
    return {"kind": "fhir", "label": DEFAULT_LABEL, "url": DEFAULT_URL, "token": "",
            "token_file": str(config.REPO / "data" / "his_mock" / "token"), "connector": "", "enabled": True}


def settings() -> dict:
    """The HIS settings: <DATA_ROOT>/his.json over the defaults (the demo's mock hospital), then TB_HIS_URL / TB_HIS_TOKEN /
    TB_HIS_TOKEN_FILE. Holds the token: never return this to the UI (public())."""
    d = _default_settings()
    p = settings_path()
    if p.exists():
        try:
            saved = json.loads(p.read_text())
            if isinstance(saved, dict):
                d.update({k: v for k, v in saved.items() if k in d})
        except (OSError, ValueError):
            pass
    if os.getenv("TB_HIS_URL"):
        d["url"] = os.environ["TB_HIS_URL"].strip()
    if os.getenv("TB_HIS_TOKEN"):
        d["token"] = os.environ["TB_HIS_TOKEN"].strip()
    if os.getenv("TB_HIS_TOKEN_FILE"):
        d["token_file"] = os.environ["TB_HIS_TOKEN_FILE"].strip()
    d["enabled"] = bool(d.get("enabled"))
    return d


def token(d: dict | None = None) -> str:
    """The bearer token: `token`, else the first line of `token_file` ("" when neither)."""
    d = settings() if d is None else d
    if d.get("token"):
        return str(d["token"]).strip()
    f = d.get("token_file")
    if f:
        try:
            return Path(f).read_text().strip().splitlines()[0].strip()
        except (OSError, IndexError):
            return ""
    return ""


def public(d: dict, manager: bool = True) -> dict:
    """Settings without the token (the UI only learns whether one is available); the token file's server path only for a manager."""
    out = {k: v for k, v in d.items() if k != "token"} | {"has_token": bool(token(d))}
    if not manager:
        out["token_file"] = bool(out.get("token_file"))
    return out


LOOPBACK = ("127.0.0.1", "localhost", "::1", "[::1]")


def _origin(url: str) -> str:
    sp = urlsplit(url or "")
    return f"{sp.scheme}://{sp.netloc}".lower()


def allowed_hosts() -> set:
    """Hosts a root admin may point the HIS connection at beside this server: TB_HIS_ALLOW_HOSTS (comma separated host[:port])."""
    return {h.strip().lower() for h in os.getenv("TB_HIS_ALLOW_HOSTS", "").split(",") if h.strip()}


def validate_settings(d: dict, existing: dict | None = None, allow_remote: bool = False) -> dict:
    """Cleaned settings, or ValueError with a plain message. An empty token keeps the saved one, unless the url's origin changed
    (the saved token is never sent to a new host). The token file is never taken from the request: it stays what the server
    has (the environment, the saved file, or the demo default), so no Tumour Board role can make the app read and send an
    arbitrary server file (review S2). The url may name this server (loopback) or a host in TB_HIS_ALLOW_HOSTS; any other
    host needs a Vaidyx admin (`allow_remote`)."""
    existing = existing or {}
    kind = str(d.get("kind") or "fhir").strip().lower()
    if kind not in KINDS:
        raise ValueError("kind must be fhir, mcp or none")
    label = str(d.get("label") or "").strip()[:80] or (DEFAULT_LABEL if kind == "fhir" else "")
    url = str(d.get("url") or "").strip().rstrip("/")
    same_origin = bool(existing.get("url")) and _origin(url) == _origin(existing.get("url"))
    tok = str(d.get("token") or "").strip() or (str(existing.get("token") or "") if same_origin else "")
    token_file = str(existing.get("token_file") or "").strip() if existing else str(_default_settings().get("token_file") or "")
    if not same_origin:
        token_file = ""  # a new host: neither the saved token nor the saved token file follows it (the demo token file belongs to the demo mock)
    connector = str(d.get("connector") or "").strip()
    if kind == "fhir":
        if not _URL.match(url):
            raise ValueError("url must start with http:// or https://")
        host = (urlsplit(url).hostname or "").lower()
        hostport = (urlsplit(url).netloc or "").lower()
        if host not in LOOPBACK and host not in allowed_hosts() and hostport not in allowed_hosts() and not allow_remote:
            raise ValueError("the HIS connection may point only at this server or at a host listed in TB_HIS_ALLOW_HOSTS; ask the Vaidyx admin for another host")
        if not tok and not token_file:
            raise ValueError("a FHIR HIS needs a token (saved tokens never follow a change of host)")
    if kind == "mcp":
        from . import connectors
        if not connectors.get(connector):
            raise ValueError(f"connector '{connector}' is not a configured MCP connector")
    return {"kind": kind, "label": label, "url": url, "token": tok, "token_file": token_file, "connector": connector,
            "enabled": bool(d.get("enabled", True))}


def save_settings(d: dict, by: str = "", allow_remote: bool = False) -> dict:
    """Validate, write his.json atomically (owner-only), audit `his_settings_saved` without the token, return public()."""
    from . import org
    p = settings_path()
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except (OSError, ValueError):
            existing = {}
    if not existing:
        existing = {k: v for k, v in _default_settings().items()}  # the demo defaults are the saved state of a fresh server
    clean = validate_settings(d, existing, allow_remote=allow_remote)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=1))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(p)
    org.audit("his_settings_saved", by, his_kind=clean["kind"], label=clean["label"], url=clean["url"],
              token_file=clean["token_file"], connector=clean["connector"], enabled=clean["enabled"],
              has_token=bool(clean["token"] or clean["token_file"]))
    return public(clean)


def client(d: dict | None = None, transport=None) -> HISClient | None:
    """The configured HIS client; None when disabled or kind none (or an MCP connector that no longer exists)."""
    d = settings() if d is None else d
    if not d.get("enabled") or d.get("kind") == "none":
        return None
    if d.get("kind") == "mcp":
        from . import connectors
        c = connectors.get(d.get("connector") or "")
        return MCPHISClient(c) if c else None
    return FHIRClient(d.get("url") or DEFAULT_URL, token(d), label=d.get("label") or "", transport=transport)
