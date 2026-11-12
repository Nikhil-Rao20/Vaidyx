"""Plain FHIR R4 servers that are not in NRCeS shapes (kind "fhir_generic"): HAPI FHIR, OpenMRS FHIR2 (Bahmni), Epic / Oracle
Cerner style. A subclass of his_client.FHIRClient that adds what differs and reuses the rest:

  identifiers    Patient?identifier=<value>, then identifier=<system>|<value> for each configured system, then the same on
                 Encounter (visit numbers). A Patient with no identifier typed MR takes its UHID from the configured systems,
                 else its official identifier, else the one that matched.
  base path      an optional FHIR base path under the server (OpenMRS: /openmrs/ws/fhir2/R4).
  sign-in        bearer token, HTTP basic (user + password), a static API key header, or OAuth2 client credentials (the access
                 token is kept in memory until it expires; it is never logged and never put in a URL or an error).
  missing parts  no Provenance: the signature is unknown (None), never "yes". No DocumentReference (OpenMRS FHIR2 has none):
                 the report is built from DiagnosticReport.presentedForm (inline Base64 or a Binary URL on the same server),
                 else it is a "text only" report whose text is the report's conclusion and Observations, line by line.
                 No Patient/$everything: one search per resource type by patient. No `_history`: only the current version.
  paging         `link[next]` is followed only on the configured server (FHIRClient._send refuses any other origin).

A "text only" report carries no candidate values: a value checked against a text made from itself would prove nothing; the
normal reading of the text finds the values, with quotes. A DiagnosticReport with no file, no conclusion and no Observations
is not delivered. SMART backend services (a signed JWT) is not implemented: see DESIGN.md.
"""
import base64
import binascii
import copy
import hashlib
import time
from datetime import datetime
from urllib.parse import quote, urlsplit

import httpx

from .. import his_client
from ..his_client import FHIRClient, HISError, IST, _Index, _attachment, _doc_version, _first, _parse_time, _ref, _ref_id

KIND = "fhir_generic"
AUTHS = ("none", "bearer", "basic", "api_key", "oauth2")
PATIENT_TYPES = ("Encounter", "DiagnosticReport", "DocumentReference", "ServiceRequest", "Specimen", "ImagingStudy", "Provenance")
PF = "vxpf"          # the id prefix of a document made from DiagnosticReport.presentedForm: vxpf.<version>.<report id>
TX = "vxtx"          # the id prefix of a text-only report (no file on the server): vxtx.<version>.<report id>
TEXT_ONLY = "text only (the server holds no report file)"
_TOKENS: dict = {}   # OAuth2 access tokens in memory only: {(token url, client id, scope, secret digest): (token, expires at)}


def _hard(e: Exception) -> bool:
    """A connection or sign-in problem (never papered over by a fallback)."""
    s = str(e)
    return "refused the token" in s or "cannot reach" in s or "did not answer" in s or "token endpoint" in s or "another server" in s


def _form(dr: dict):
    """The first presentedForm of a DiagnosticReport that carries a file (inline data or a url), or None."""
    return next((f for f in dr.get("presentedForm") or [] if isinstance(f, dict) and (f.get("data") or f.get("url"))), None)


def _range(o: dict) -> str:
    rr = _first(o.get("referenceRange")) or {}
    if rr.get("text"):
        return str(rr["text"])
    lo, hi = (rr.get("low") or {}).get("value"), (rr.get("high") or {}).get("value")
    return f"{his_client._number(lo)} to {his_client._number(hi)}" if lo is not None and hi is not None else ""


def report_text(dr: dict, observations: list, p: dict, title: str) -> str:
    """The text of a "text only" report: what the server holds for it, line by line (label: value)."""
    lines = ["FHIR diagnostic report (text only: the hospital system holds no report file)", title.upper(),
             f"Patient name : {p.get('name') or (dr.get('subject') or {}).get('display') or ''}   UHID : {p.get('uhid') or ''}"]
    if p.get("age") is not None or p.get("sex"):
        lines.append(f"Age / Sex : {str(p['age']) + ' Y' if p.get('age') is not None else ''} / {p.get('sex') or ''}")
    if dr.get("issued") or dr.get("effectiveDateTime"):
        lines.append(f"Reported on : {dr.get('issued') or dr.get('effectiveDateTime')}")
    lines.append("")
    for o in observations:
        d = his_client.observation_dict(o)
        rng = _range(o)
        if d["value"] or not o.get("component"):
            lines.append(f"{d['label']}: {d['value']}" + (f"   (reference range {rng})" if rng else ""))
        for comp in o.get("component") or []:
            cd = his_client.observation_dict(comp)
            lines.append(f"{d['label']}, {cd['label']}: {cd['value']}")
    if str(dr.get("conclusion") or "").strip():
        lines += ["", "Conclusion: " + str(dr["conclusion"]).strip()]
    lines += ["", f"Report status: {his_client._status(dr.get('status')).upper()}"]
    who = (_first(dr.get("resultsInterpreter")) or {}).get("display")
    if who:
        lines.append(f"Reported by: {who}")
    return "\n".join(lines) + "\n"


class GenericFHIRClient(FHIRClient):
    """`auth`: {"type": none|bearer|basic|api_key|oauth2, "token", "username", "password", "header", "key", "token_url",
    "client_id", "client_secret", "scope"} (secrets already read from their files by the registry)."""
    carries_signature = False  # no verifiable signature on this transport: the report text decides (his_overlay)
    kind = KIND

    def __init__(self, url: str, auth: dict | None = None, label: str = "", base_path: str = "", identifier_systems=(), timeout: float = 30,
                 transport=None):
        auth = dict(auth or {})
        super().__init__(url, "", label=label or "FHIR R4 server", timeout=timeout, transport=transport)
        if base_path:
            self.fhir_base = self.origin + "/" + str(base_path).strip("/")
        self._auth = auth
        self._auth_type = auth.get("type") or ("bearer" if auth.get("token") else "none")
        if self._auth_type not in AUTHS:
            raise HISError("unknown sign-in type for the FHIR server")
        self.identifier_systems = [str(s).strip() for s in identifier_systems or [] if str(s).strip()]
        self._no_everything = False

    def __repr__(self):
        return f"GenericFHIRClient({self.fhir_base!r}, auth={self._auth_type})"   # never a secret

    # ---- sign-in
    async def _oauth_token(self, force: bool = False) -> str:
        a = self._auth
        url, cid, secret, scope = str(a.get("token_url") or ""), str(a.get("client_id") or ""), str(a.get("client_secret") or ""), str(a.get("scope") or "")
        key = (url, cid, scope, hashlib.sha256(secret.encode()).hexdigest())
        hit = _TOKENS.get(key)
        if hit and not force and hit[1] > time.monotonic():
            return hit[0]
        _TOKENS.pop(key, None)
        host = urlsplit(url).netloc
        form = {"grant_type": "client_credentials"} | ({"scope": scope} if scope else {})
        kw = {"transport": self._transport} if self._transport is not None else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, connect=min(10, self._timeout)), follow_redirects=False, **kw) as c:
                r = await c.post(url, data=form, auth=httpx.BasicAuth(cid, secret), headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise HISError(f"cannot reach the token endpoint at {host}: {type(e).__name__}") from None
        if r.status_code >= 400:
            raise HISError(f"the token endpoint at {host} refused the client id or secret (HTTP {r.status_code}); check the connection settings")
        try:
            d = r.json()
            tok = str(d["access_token"])
            life = float(d.get("expires_in") or 300)
        except (ValueError, KeyError, TypeError):
            raise HISError(f"the token endpoint at {host} did not return an access token") from None
        if not tok:
            raise HISError(f"the token endpoint at {host} did not return an access token")
        _TOKENS[key] = (tok, time.monotonic() + max(life - 30, 5))
        return tok

    async def _auth_headers(self, force: bool = False) -> dict:
        a, t = self._auth, self._auth_type
        if t == "bearer" and a.get("token"):
            return {"Authorization": f"Bearer {a['token']}"}
        if t == "basic":
            raw = f"{a.get('username') or ''}:{a.get('password') or ''}".encode("utf-8")
            return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
        if t == "api_key" and a.get("key"):
            return {str(a.get("header") or "X-API-Key"): str(a["key"])}
        if t == "oauth2":
            return {"Authorization": f"Bearer {await self._oauth_token(force)}"}
        return {}

    async def _send(self, c, url: str):
        """GET on the configured server only, with the sign-in headers (never sent to another origin)."""
        if not self._same_origin(url):
            raise HISError("the HIS pointed to another server; Vaidyx-TB only sends its token to the configured HIS")
        what = urlsplit(url).path
        for attempt in (0, 1):
            headers = await self._auth_headers(force=bool(attempt))
            try:
                r = await c.get(url, headers=headers)
            except httpx.TimeoutException:
                raise HISError(f"the HIS at {self.origin} did not answer in time ({what})") from None
            except httpx.HTTPError as e:
                raise HISError(f"cannot reach the HIS at {self.origin}: {type(e).__name__}") from None
            if r.status_code == 401 and self._auth_type == "oauth2" and attempt == 0:
                continue                       # the access token may have been withdrawn early: one fresh token, one retry
            if r.status_code in (401, 403):
                raise HISError(f"the HIS refused the token or sign-in (HTTP {r.status_code}); check the connection settings")
            return r

    # ---- tolerant searches
    async def _bundle(self, c, path: str, params=None, allow_404=False) -> list:
        try:
            return await super()._bundle(c, path, params, allow_404=allow_404)
        except HISError as e:
            if path.endswith("/_history") and not _hard(e):
                return []                      # a server that keeps no history: only the current version
            raise

    async def _everything(self, c, patient_id: str) -> list:
        """Patient/$everything, else one search per resource type by patient (a type the server does not serve is left out)."""
        pid = quote(patient_id, safe="")
        if not self._no_everything:
            try:
                res = await super()._bundle(c, f"Patient/{pid}/$everything", allow_404=True)
                if res:
                    return res
            except HISError as e:
                if _hard(e):
                    raise
            self._no_everything = True
        pat = await self._read(c, f"Patient/{pid}")
        if not pat or pat.get("resourceType") != "Patient":
            raise HISError(f"the HIS has no registration {patient_id}")
        out = [pat]
        for rtype in PATIENT_TYPES:
            try:
                out += await super()._bundle(c, rtype, [("patient", patient_id)], allow_404=True)
            except HISError as e:
                if _hard(e):
                    raise
        return out

    # ---- interface
    async def ping(self) -> dict:
        """The CapabilityStatement, then one signed-in read. A server that refuses a bare Patient search (HTTP 400) but accepted
        the sign-in still counts as answering."""
        out = {"ok": False, "name": "", "fhir_version": "", "token_ok": None, "error": ""}
        try:
            async with self._client() as c:
                cs = await self._get_json(c, "metadata")
                if cs.get("resourceType") != "CapabilityStatement":
                    raise HISError("the HIS metadata is not a CapabilityStatement")
                out["name"] = (cs.get("software") or {}).get("name") or cs.get("title") or cs.get("name") or ""
                out["fhir_version"] = cs.get("fhirVersion") or ""
                try:
                    await self._get_json(c, "Patient", [("_count", "1")])
                except HISError as e:
                    if _hard(e):
                        if "refused the token" in str(e):
                            out["token_ok"] = False
                        raise
                out["token_ok"] = True
            out["ok"] = True
        except HISError as e:
            out["error"] = str(e)
        return out

    async def _search_ids(self, c, rtype: str, value: str) -> list:
        """`rtype` resources carrying the identifier: the bare value first, then each configured system."""
        for q in [value] + [f"{s}|{value}" for s in self.identifier_systems]:
            try:
                res = [r for r in await self._bundle(c, rtype, [("identifier", q)]) if r.get("resourceType") == rtype]
            except HISError as e:
                if _hard(e):
                    raise
                res = []                       # a server that refuses one search form: try the next
            hits = [r for r in res if any(str(i.get("value") or "").lower() == value.lower() for i in r.get("identifier") or [])] or res
            if hits:
                return hits
        return []

    def _patient(self, pat: dict, matched: str = "") -> dict:
        """patient_dict, with the UHID of a server that does not type its identifiers MR."""
        out = his_client.patient_dict(pat)
        if not out["uhid"]:
            ids = [i for i in pat.get("identifier") or [] if i.get("value")]
            pick = next((i for s in self.identifier_systems for i in ids if i.get("system") == s), None) \
                or next((i for i in ids if i.get("use") == "official"), None) \
                or next((i for i in ids if matched and str(i["value"]).lower() == matched.lower() and not his_client.identifier_kind(i)), None) \
                or next((i for i in ids if not his_client.identifier_kind(i)), None)
            out["uhid"] = (pick or {}).get("value") or out["id"]
            out["identifiers"].insert(0, {"kind": "uhid", "value": out["uhid"]})
        return out

    async def find_patient(self, identifier: str) -> dict | None:
        value = str(identifier or "").strip()
        if not value:
            return None
        async with self._client() as c:
            pats = await self._search_ids(c, "Patient", value)
            if len({p.get("id") for p in pats}) > 1:
                raise HISError(f"more than one registration matches {value}; a person must choose")
            if pats:
                pat = pats[0]
                kind = next((his_client.identifier_kind(i) for i in pat.get("identifier") or [] if i.get("value") == value), "") or "uhid"
            else:
                encs = await self._search_ids(c, "Encounter", value)
                subjects = {_ref(e.get("subject")) for e in encs if _ref(e.get("subject"))}
                if not subjects:
                    return None
                if len(subjects) > 1:
                    raise HISError(f"more than one registration matches {value}; a person must choose")
                pat = await self._read(c, "Patient/" + quote(_ref_id(subjects.pop(), "Patient"), safe=""))
                if not pat or pat.get("resourceType") != "Patient":
                    raise HISError(f"the HIS encounter {value} points to a registration it cannot return")
                kind = "ip_no" if his_client.encounter_dict(encs[0])["kind"] == "IP" else "op_no"
            out = self._patient(pat, value)
            out["matched_on"] = {"kind": kind, "value": value}
            try:
                out["similar"] = await self._similar(c, out["id"])
            except HISError as e:
                if _hard(e):
                    raise
                out["similar"] = []
        return out

    async def reports(self, patient_id: str, since: str | None = None) -> list:
        """One dict per report: the current version of each DiagnosticReport with its DocumentReference (or a document made
        from presentedForm), and every DocumentReference that belongs to no report (a note). `since` is applied here, on
        `last_updated`: not every server searches by _lastUpdated."""
        cut = None
        if since is not None:
            cut = _parse_time(since)
            if cut is None:
                raise HISError(f"bad 'since' value {since!r}")
        async with self._client() as c:
            idx = _Index(copy.deepcopy(await self._everything(c, patient_id)))
            drs = {dr["id"]: dr for dr in idx.of("DiagnosticReport")}
            want = {_ref(x) for dr in drs.values() for x in dr.get("result") or []}
            want = {w for w in want if w and "/" in w and idx.get(w) is None}
            for got in await self._read_many(c, sorted(want)):
                idx.add(got)
        docs, covered, cur = [], set(), {}
        for dr in drs.values():
            cur[dr["id"]] = _doc_version(dr)
            idx.dr_versions.setdefault(dr["id"], {})[cur[dr["id"]]] = dr
        for d in sorted(idx.of("DocumentReference"), key=lambda d: d.get("status") == "superseded"):   # the current document of a report first
            _attachment(d).pop("data", None)
            rel = next((_ref(r) for r in ((d.get("context") or {}).get("related") or []) if _ref(r).startswith("DiagnosticReport/")), "")
            rid = _ref_id(rel, "DiagnosticReport") if rel else ""
            if rid in drs and d.get("status") == "superseded":
                if not _doc_version(d) < cur[rid]:
                    continue                   # an earlier document whose number cannot be placed before the current version
            elif rid in drs:
                d.setdefault("meta", {})["versionId"] = str(cur[rid])      # joined to the report as the server holds it now
                covered.add(rid)
            elif not rel:
                cur[his_client._doc_report_id(d)] = _doc_version(d)
            else:
                continue                       # a document of a report the server did not return: nothing to join it to
            docs.append(d)
        for rid, dr in drs.items():
            if rid in covered:
                continue
            form = _form(dr)
            if form is None and not (dr.get("result") or str(dr.get("conclusion") or "").strip()):
                continue                       # no file and nothing written: no report to read
            title = (dr.get("code") or {}).get("text") or (form or {}).get("title") or ""
            docs.append({"resourceType": "DocumentReference", "id": f"{PF if form else TX}.{cur[rid]}.{rid}", "status": "current",
                         "meta": {"versionId": str(cur[rid]), "lastUpdated": (dr.get("meta") or {}).get("lastUpdated")},
                         "type": dr.get("code"), "description": title, "date": dr.get("issued"),
                         "content": [{"attachment": {k: v for k, v in form.items() if k != "data"} if form else {"contentType": "text/plain", "title": title}}],
                         "context": {"related": [{"reference": f"DiagnosticReport/{rid}"}], "encounter": [dr["encounter"]] if dr.get("encounter") else []}})
        out, seen = [], set()
        for d in docs:
            rep = his_client.build_report(d, idx, cur)
            if (rep["id"], rep["version"]) in seen:
                continue
            if str(d.get("id") or "").startswith(TX + "."):
                rep["observations"] = []       # the text is made of these values: they are read from it, not checked against it
                rep["doc_type_basis"] = (rep["doc_type_basis"] + "; " if rep["doc_type_basis"] else "") + TEXT_ONLY
                rep["document"]["text_only"] = True
            if cut is not None:
                lu = _parse_time(rep["last_updated"])
                if lu is None or lu < cut:
                    continue
            seen.add((rep["id"], rep["version"]))
            out.append(rep)
        far = datetime.max.replace(tzinfo=IST)
        return sorted(out, key=lambda r: (_parse_time(r["issued"]) or far, r["id"], r["version"]))

    async def _binary(self, c, url: str, what: str) -> bytes:
        """The bytes behind an attachment url on the configured server: raw bytes, or a Binary resource's Base64 `data`."""
        resp = await self._send(c, self._url(url))
        if resp.status_code >= 400:
            raise HISError(f"the HIS answered HTTP {resp.status_code} for the file of {what}")
        if "json" in (resp.headers.get("content-type") or "").lower():
            try:
                d = resp.json()
            except ValueError:
                d = None
            if isinstance(d, dict) and d.get("resourceType") == "Binary":
                try:
                    return base64.b64decode(str(d.get("data") or ""), validate=True)
                except (binascii.Error, ValueError):
                    raise HISError(f"the HIS file of {what} carries unreadable base64") from None
        return resp.content

    async def _document_reference(self, did: str) -> dict:
        """FHIRClient.document for a real DocumentReference, also reading an attachment url that answers a Binary resource."""
        async with self._client() as c:
            doc = await self._read(c, f"DocumentReference/{quote(did, safe='')}")
            if not doc or doc.get("resourceType") != "DocumentReference":
                raise HISError(f"the HIS has no document {did}")
            att = _attachment(doc)
            if att.get("data"):
                try:
                    data = base64.b64decode(att["data"], validate=True)
                except (binascii.Error, ValueError, TypeError):
                    raise HISError(f"the HIS document {did} carries unreadable base64") from None
            elif att.get("url"):
                data = await self._binary(c, att["url"], f"document {did}")
            else:
                raise HISError(f"the HIS document {did} has neither data nor a url")
        his_client._check_sha(data, his_client._ext_value(doc, "document-sha256") or "", att.get("hash") or "", f"document {did}")
        title = att.get("title") or doc.get("description") or did
        ext = {"text/plain": ".txt", "image/jpeg": ".jpg", "image/png": ".png"}.get(str(att.get("contentType") or "").split(";")[0].strip().lower(), ".pdf")
        return {"ref": f"DocumentReference/{did}", "content": data, "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": att.get("contentType") or "application/octet-stream", "title": title,
                "filename": f"{his_client._slug(title, 60)}_{his_client._slug(did, 40)}{ext}", "size": len(data),
                "creation": att.get("creation") or "", "status": doc.get("status") or "", "doc_status": doc.get("docStatus") or ""}

    async def document(self, ref: str) -> dict:
        did = _ref_id(str(ref or "").strip(), "DocumentReference")
        if not did:
            raise HISError("no document reference given")
        if did.startswith(TX + "."):
            return await self._text_report(did)
        if not did.startswith(PF + "."):
            return await self._document_reference(did)
        try:
            _, version, rid = did.split(".", 2)
        except ValueError:
            raise HISError("not a report document reference") from None
        async with self._client() as c:
            dr = await self._report_version(c, rid, version)
            form = _form(dr) or {}
            if form.get("data"):
                try:
                    data = base64.b64decode(form["data"], validate=True)
                except (binascii.Error, ValueError, TypeError):
                    raise HISError(f"the HIS report {rid} carries unreadable base64") from None
            elif form.get("url"):
                data = await self._binary(c, form["url"], f"report {rid}")
            else:
                raise HISError(f"the HIS report {rid} has no document")
        his_client._check_sha(data, "", form.get("hash") or "", f"report {rid}")
        title = form.get("title") or (dr.get("code") or {}).get("text") or rid
        ext = {"application/pdf": ".pdf", "text/plain": ".txt", "image/jpeg": ".jpg", "image/png": ".png"}.get(str(form.get("contentType") or "").split(";")[0].strip().lower(), ".pdf")
        return {"ref": f"DocumentReference/{did}", "content": data, "sha256": hashlib.sha256(data).hexdigest(),
                "content_type": form.get("contentType") or "application/octet-stream", "title": title,
                "filename": f"{his_client._slug(title, 60)}_{his_client._slug(rid, 40)}{ext}", "size": len(data),
                "creation": form.get("creation") or "", "status": "current", "doc_status": dr.get("status") or ""}

    async def _report_version(self, c, rid: str, version: str) -> dict:
        dr = await self._read(c, f"DiagnosticReport/{quote(rid, safe='')}")
        if dr and str(_doc_version(dr)) != version:
            dr = await self._get_json(c, f"DiagnosticReport/{quote(rid, safe='')}/_history/{quote(version, safe='')}", allow_404=True)
        if not dr or dr.get("resourceType") != "DiagnosticReport":
            raise HISError(f"the HIS no longer serves that version of report {rid}")
        return dr

    async def _text_report(self, did: str) -> dict:
        """The .txt of a report the server holds only as data: its title, patient, conclusion and Observations, line by line."""
        try:
            _, version, rid = did.split(".", 2)
        except ValueError:
            raise HISError("not a report document reference") from None
        async with self._client() as c:
            dr = await self._report_version(c, rid, version)
            refs = [r for r in (_ref(x) for x in dr.get("result") or []) if r and "/" in r]
            obs = [o for o in await self._read_many(c, refs) if o and o.get("resourceType") == "Observation"]
            pat = None
            if _ref(dr.get("subject")).startswith("Patient/") or "/Patient/" in _ref(dr.get("subject")):
                pat = await self._read(c, "Patient/" + quote(_ref_id(_ref(dr.get("subject")), "Patient"), safe=""))
        p = self._patient(pat) if pat and pat.get("resourceType") == "Patient" else {}
        title = (dr.get("code") or {}).get("text") or ((_first((dr.get("code") or {}).get("coding")) or {}).get("display")) or "Diagnostic report"
        data = report_text(dr, obs, p, title).encode("utf-8")
        return {"ref": f"DocumentReference/{did}", "content": data, "sha256": hashlib.sha256(data).hexdigest(), "content_type": "text/plain",
                "title": title, "filename": f"{his_client._slug(title, 60)}_{his_client._slug(rid, 40)}.txt", "size": len(data),
                "creation": dr.get("issued") or "", "status": "current", "doc_status": dr.get("status") or "", "text_only": True}

    async def hospital(self) -> dict:
        try:
            return await super().hospital()
        except HISError as e:
            if _hard(e):
                raise
            return {"name": self.label, "departments": []}
