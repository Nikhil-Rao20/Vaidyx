"""ABDM health-record documents from a folder (kind "abdm_bundles"): FHIR R4 Bundles of type `document` in NRCeS shapes
(Composition first), one `.json` file each. This is how a hospital that is an ABDM Health Information Provider can hand over
records without a live API. Record types read: DiagnosticReportRecord, DischargeSummaryRecord, OPConsultRecord,
HealthDocumentRecord; any other record type is skipped and counted.

Each bundle becomes one report per DiagnosticReport (DiagnosticReportRecord) or one note (the other three). The patient
comes from the bundle's Patient resource (ABHA number / address and the hospital's own MR identifier); the file from
DiagnosticReport.presentedForm, a DocumentReference attachment or a Binary inside the bundle. A bundle with no file is a
"text only" record: the narrative of its sections is its text. Bundles with the same report identifier are versions in date
order. The bundle's own signature (a JWS) is not verified here: `signature` is None (unknown, never "yes").
A live ABDM gateway (consent, HIU callbacks) is out of scope (docs/his-adapters/DESIGN.md).
"""
import asyncio
import base64
import binascii
import hashlib
import html
import json
import re
from urllib.parse import quote

from .. import his_client
from ..his_client import HISClient, HISError
from . import _common as C

KIND = "abdm_bundles"
RECORD_TYPES = {"721981007": "DiagnosticReportRecord", "373942005": "DischargeSummaryRecord", "371530004": "OPConsultRecord",
                "419891008": "HealthDocumentRecord"}
_TAGS = re.compile(r"<[^>]+>")


class _Bundle:
    """The resources of one document bundle, found by fullUrl, `Type/id` or `urn:uuid:` reference."""

    def __init__(self, bundle: dict):
        self.by_ref, self.all = {}, []
        for e in bundle.get("entry") or []:
            r = e.get("resource") if isinstance(e, dict) else None
            if not isinstance(r, dict) or not r.get("resourceType"):
                continue
            self.all.append(r)
            for k in (e.get("fullUrl"), f"{r['resourceType']}/{r.get('id')}" if r.get("id") else None, f"urn:uuid:{r.get('id')}" if r.get("id") else None):
                if k:
                    self.by_ref.setdefault(str(k), r)

    def get(self, ref):
        r = his_client._ref(ref) if isinstance(ref, dict) else str(ref or "")
        if not r:
            return None
        return self.by_ref.get(r) or self.by_ref.get(r.split("/_history/")[0]) or next(
            (v for k, v in self.by_ref.items() if k.endswith("/" + r)), None)

    def of(self, rtype):
        return [r for r in self.all if r.get("resourceType") == rtype]


def record_type(comp: dict) -> str:
    """The NRCeS record type of a Composition: its SNOMED type code, else its profile name; "" when it is none we read."""
    for cd in (comp.get("type") or {}).get("coding") or []:
        if cd.get("code") in RECORD_TYPES:
            return RECORD_TYPES[cd["code"]]
    for p in (comp.get("meta") or {}).get("profile") or []:
        name = str(p).rsplit("/", 1)[-1]
        if name in RECORD_TYPES.values():
            return name
    return ""


def _attachment_bytes(att: dict, b: _Bundle):
    """The bytes of an attachment: inline `data`, else a Binary inside the bundle named by `url`; None when neither."""
    if not isinstance(att, dict):
        return None
    data = att.get("data")
    if not data and att.get("url"):
        binary = b.get(att["url"])
        if binary and binary.get("resourceType") == "Binary":
            data = binary.get("data")
    if not data:
        return None
    try:
        return base64.b64decode(re.sub(r"\s+", "", str(data)), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("an attachment with unreadable Base64") from None


def _section_entries(comp: dict, b: _Bundle) -> list:
    out = []
    def walk(sections):
        for s in sections or []:
            out.extend(x for x in (b.get(e) for e in s.get("entry") or []) if x)
            walk(s.get("section"))
    walk(comp.get("section"))
    return out


def _narrative(comp: dict, b: _Bundle, title: str, p: dict, status: str) -> str:
    """The text of a record with no file: the Composition's section titles and narratives, as the hospital wrote them."""
    lines = ["ABDM health record (text only: the bundle carried no file)", title.upper(), f"Patient name : {p.get('name') or ''}   UHID : {p.get('uhid') or ''}", ""]
    def walk(sections):
        for s in sections or []:
            if s.get("title"):
                lines.append(str(s["title"]))
            div = ((s.get("text") or {}).get("div")) or ""
            if div:
                lines.append(html.unescape(_TAGS.sub(" ", div)).strip())
            for e in s.get("entry") or []:
                r = b.get(e) or {}
                for k in ("conclusion", "description"):
                    if isinstance(r.get(k), str) and r[k].strip():
                        lines.append(r[k].strip())
                div = ((r.get("text") or {}).get("div")) or ""
                if div:
                    lines.append(html.unescape(_TAGS.sub(" ", div)).strip())
            walk(s.get("section"))
    walk(comp.get("section"))
    lines += ["", f"Report status: {status.upper()}"]
    return "\n".join(x for x in lines if x is not None) + "\n"


def read_bundle(bundle: dict, name: str) -> tuple:
    """(patient key, patient dict, encounter dict or None, [(report dict, bytes)]) of one document bundle; ValueError (plain
    reason) when it is not a record Vaidyx-TB reads."""
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise ValueError("not a FHIR Bundle")
    if bundle.get("type") != "document":
        raise ValueError("not a document bundle")
    b = _Bundle(bundle)
    comp = b.all[0] if b.all else {}
    if comp.get("resourceType") != "Composition":
        raise ValueError("the first entry is not a Composition")
    rtype = record_type(comp)
    if not rtype:
        raise ValueError("a record type Vaidyx-TB does not read")
    pat = b.get(comp.get("subject")) or next(iter(b.of("Patient")), None)
    if not pat or pat.get("resourceType") != "Patient":
        raise ValueError("no Patient resource")
    p = his_client.patient_dict(pat)
    uhid = abha = address = ""
    for i in pat.get("identifier") or []:          # the official NRCeS example types the ABHA number MR under the health-id system
        system, value, kind = str(i.get("system") or "").lower(), str(i.get("value") or ""), his_client.identifier_kind(i)
        if not value:
            continue
        if "healthid" in system or "abdm.gov.in" in system or kind in ("abha", "abha_address"):
            if "@" in value or kind == "abha_address":
                address = address or value
            else:
                abha = abha or value
        elif kind == "uhid":
            uhid = uhid or value
    p.update(uhid=uhid, abha=abha, abha_address=address)
    p["identifiers"] = [{"kind": k, "value": v} for k, v in (("uhid", uhid), ("abha", abha), ("abha_address", address), ("pmjay", p["pmjay_id"])) if v]
    key = p["uhid"] or p["abha"] or p["abha_address"]
    if not key:
        raise ValueError("the Patient has no MR identifier and no ABHA")
    p.update(id=key, ref=None, uhid=p["uhid"] or key)
    if not any(i["kind"] == "uhid" for i in p["identifiers"]):
        p["identifiers"].insert(0, {"kind": "uhid", "value": p["uhid"]})
    enc_res = b.get(comp.get("encounter"))
    enc = his_client.encounter_dict(enc_res) if enc_res and enc_res.get("resourceType") == "Encounter" else None
    if enc and not enc["number"]:
        enc = None
    when = comp.get("date") or bundle.get("timestamp") or ""
    stamp = (bundle.get("meta") or {}).get("lastUpdated") or bundle.get("timestamp") or when
    author = next((his_client._person({"reference": his_client._ref(a), "display": a.get("display") or _name(b.get(a))}) for a in comp.get("author") or []
                   if (b.get(a) or {}).get("resourceType") in ("Practitioner", "PractitionerRole") or a.get("display")), None)
    org = next((_name(b.get(a)) for a in comp.get("author") or [] if (b.get(a) or {}).get("resourceType") == "Organization"), "")
    base_id = (bundle.get("identifier") or {}).get("value") or (comp.get("identifier") or {}).get("value") or comp.get("id") or name
    entries = _section_entries(comp, b)
    docrefs = [r for r in entries if r.get("resourceType") == "DocumentReference"] or b.of("DocumentReference")
    out = []

    def make(rid, title, status, issued, effective, code, cats, kind, obs, conclusion, data, n, dept=""):
        text_only = data is None
        if text_only:
            data = _narrative(comp, b, title or rtype, p, status).encode("utf-8")
        doc_type, basis = his_client.doc_type_for(code, cats, title, "")
        rep = C.report_shape(rid, 1, f"abdm:{quote(name, safe='')}/{n}", title=title, status=status, issued=issued, effective=effective,
                             kind=kind, code=code, category=[c for c in cats if c], doc_type=doc_type,
                             doc_type_basis=(basis + "; " if basis else "") + f"ABDM {rtype}" + ("; text only (the bundle carried no file)" if text_only else ""),
                             encounter_number=(enc or {}).get("number") or "", encounter_kind=(enc or {}).get("kind") or "", performer_department=dept or org,
                             reported_by=author, observations=[] if text_only else obs, conclusion=conclusion, sha256=hashlib.sha256(data).hexdigest(),
                             size=len(data), content_type=C.sniff(data)[1], last_updated=C.stamp(stamp or issued), text_only=text_only)
        out.append((rep, data))

    drs = [r for r in entries if r.get("resourceType") == "DiagnosticReport"] if rtype == "DiagnosticReportRecord" else []
    if drs:
        for n, dr in enumerate(drs):
            data = next((x for x in (_attachment_bytes(a, b) for a in dr.get("presentedForm") or []) if x), None)
            if data is None:
                data = next((x for x in (_attachment_bytes(his_client._attachment(d), b) for d in docrefs) if x), None)
            obs = [his_client.observation_dict(o) for o in (b.get(r) for r in dr.get("result") or []) if o and o.get("resourceType") == "Observation"]
            cats = [cd.get("code") for c in dr.get("category") or [] for cd in c.get("coding") or []]
            rid = next((i.get("value") for i in dr.get("identifier") or [] if i.get("value")), "") or (f"{base_id}-{n + 1}" if len(drs) > 1 else base_id)
            make(rid, (dr.get("code") or {}).get("text") or comp.get("title") or "Diagnostic report", his_client._status(dr.get("status")),
                 dr.get("issued") or when, dr.get("effectiveDateTime") or "", his_client._loinc(dr.get("code")), cats, "diagnostic", obs,
                 dr.get("conclusion") or "", data, n, next((x.get("display") or "" for x in dr.get("performer") or [] if x.get("display")), ""))
    else:
        data = next((x for x in (_attachment_bytes(his_client._attachment(d), b) for d in docrefs) if x), None)
        if data is None:
            data = next((x for x in (_attachment_bytes({"data": r.get("data")}, b) for r in b.of("Binary")) if x), None)
        make(base_id, comp.get("title") or rtype, his_client._status(comp.get("status")), when, "", his_client._loinc(comp.get("type")), [],
             "diagnostic" if rtype == "DiagnosticReportRecord" else "note", [], "", data, 0)
    return key, p, enc, out


def _name(res) -> str:
    if not isinstance(res, dict):
        return ""
    n = res.get("name")
    if isinstance(n, str):
        return n
    for x in n or []:
        if isinstance(x, dict):
            return x.get("text") or " ".join((x.get("given") or []) + [x.get("family") or ""]).strip()
    return ""


def load(folder) -> dict:
    files, skipped = C.list_files(folder, (".json",))

    def build():
        idx = {"patients": {}, "ids": {}, "visits": {}, "reports": {}, "docs": {}, "skipped": dict(skipped), "files": len(files)}
        raw, seen = {}, set()
        for path, _, _ in files:
            try:
                key, p, enc, reps = read_bundle(json.loads(path.read_bytes().decode("utf-8-sig")), path.name)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                C._skip(idx["skipped"], "not readable JSON"); continue
            except (ValueError, TypeError, AttributeError, KeyError, IndexError) as e:
                C._skip(idx["skipped"], str(e) if isinstance(e, ValueError) else "a bundle in an unexpected shape"); continue
            old = idx["patients"].get(key)
            if not old or (p["last_updated"] or "") >= (old["last_updated"] or ""):
                idx["patients"][key] = p
            for i in p["identifiers"]:
                if i["kind"] in ("uhid", "abha", "abha_address"):
                    idx["ids"].setdefault(str(i["value"]).lower(), {})[key] = i["kind"]
            if enc:
                idx["ids"].setdefault(enc["number"].lower(), {})[key] = "ip_no" if enc["kind"] == "IP" else "op_no"
                idx["visits"].setdefault(key, {})[enc["number"]] = enc
            for rep, data in reps:
                if (key, rep["id"], rep["document"]["sha256"], rep["status"]) in seen:
                    C._skip(idx["skipped"], "the same record handed over twice"); continue
                seen.add((key, rep["id"], rep["document"]["sha256"], rep["status"]))
                raw.setdefault(key, []).append(rep)
                idx["docs"][rep["document_ref"]] = (path, key)
        for key, reps in raw.items():
            reps.sort(key=lambda r: (r["last_updated"] or "", C.stamp(r["issued"])))
            idx["reports"][key] = C.number_versions(reps)
        return idx
    return C.cached(KIND, folder, tuple((p.name, s, t) for p, s, t in files), build)


class ABDMBundleClient(HISClient):
    """ABDM document bundles read from a folder (see the module docstring)."""
    carries_signature = False  # no verifiable signature on this transport: the report text decides (his_overlay)
    kind = KIND

    def __init__(self, folder, label: str = ""):
        self.folder = str(folder or "")
        self.label = label or "ABDM record bundles"

    def __repr__(self):
        return f"ABDMBundleClient({self.folder!r})"

    async def _idx(self) -> dict:
        return await asyncio.to_thread(lambda: load(C.runtime_folder(self.folder)))

    async def ping(self) -> dict:
        out = {"ok": False, "name": self.label, "fhir_version": "4.0.1", "token_ok": None, "error": ""}
        try:
            idx = await self._idx()
            out["counts"] = {"files": idx["files"], "patients": len(idx["patients"]), "reports": sum(len(v) for v in idx["reports"].values()),
                             "skipped": idx["skipped"]}
            out["ok"] = True
        except HISError as e:
            out["error"] = str(e)
        return out

    async def find_patient(self, identifier: str) -> dict | None:
        value = str(identifier or "").strip()
        if not value:
            return None
        idx = await self._idx()
        hits = idx["ids"].get(value.lower()) or {}
        key = C.one_match(hits, value)
        if key is None:
            return None
        return {**idx["patients"][key], "matched_on": {"kind": hits[key], "value": value}, "similar": []}

    async def encounters(self, patient_id: str) -> list:
        idx = await self._idx()
        return sorted((dict(v) for v in (idx["visits"].get(patient_id) or {}).values()), key=lambda e: (e["start"] or "9999", e["number"]))

    async def reports(self, patient_id: str, since: str | None = None) -> list:
        idx = await self._idx()
        return [dict(r, document=dict(r["document"])) for r in idx["reports"].get(patient_id) or [] if C.after(r["last_updated"], since)]

    async def document(self, ref: str) -> dict:
        m = re.match(r"^abdm:([^/]+)/(\d+)$", str(ref or ""))
        if not m:
            raise HISError(f"not an ABDM bundle reference: {str(ref)[:80]}")
        idx = await self._idx()
        where = idx["docs"].get(ref)
        if not where:
            raise HISError("the ABDM folder no longer holds that record")
        path, key = where
        rep = next((r for r in idx["reports"].get(key) or [] if r["document_ref"] == ref), None)

        def read():
            try:
                reps = read_bundle(json.loads(path.read_bytes().decode("utf-8-sig")), path.name)[3]
                return next(data for r, data in reps if r["document_ref"] == ref)
            except (OSError, ValueError, StopIteration, TypeError, AttributeError, KeyError, IndexError):
                raise HISError("the ABDM bundle of that record changed or cannot be read") from None
        data = await asyncio.to_thread(read)
        if rep is None:
            raise HISError("the ABDM folder no longer holds that record")
        his_client._check_sha(data, rep["document"]["sha256"], "", f"record {rep['id']}")
        return C.document_shape(ref, data, rep["title"] or rep["id"], f"{rep['title'] or 'record'}_{rep['id']}_v{rep['version']}",
                                creation=rep["issued"], doc_status=rep["status"], text_only=rep["document"]["text_only"])
