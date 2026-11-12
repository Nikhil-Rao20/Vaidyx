"""Plain FHIR R4 servers (his_adapters.fhir_generic) against an in-process server (httpx.MockTransport): identifier search with
systems, an OpenMRS-style base path, the fallbacks (no $everything, no DocumentReference: presentedForm inline or a Binary URL, no
file at all: a text-only report, no Provenance: signature unknown), paging on the same server only, and the sign-in options (bearer,
HTTP basic, API key header, OAuth2 client credentials with the token fetched once and never in a log or an error). SYNTHETIC only."""
import asyncio
import base64
import hashlib
import logging
from urllib.parse import parse_qs, unquote

import httpx
import pytest

from tumour_board import his_case, his_client, store
from tumour_board.his_adapters import fhir_generic
from tumour_board.his_adapters.fhir_generic import GenericFHIRClient
from tumour_board.tests.test_his_case import ROLES_DOC, fakes  # noqa: F401
from tumour_board.tests.test_his_adapters_hl7v2 import NAME, PDF, PDF2, UHID

BASE = "http://127.0.0.1:8085"
PATH = "/openmrs/ws/fhir2/R4"
SYSTEM = "http://hospital.example/ids/hospital-no"
SECRET = "client-secret-" + "s" * 12
ACCESS = "access-token-" + "a" * 12
PID = "8f3a-uuid-0001"


def bundle(resources, next_url=None):
    b = {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": r} for r in resources]}
    if next_url:
        b["link"] = [{"relation": "next", "url": next_url}]
    return b


def b64(data):
    return base64.b64encode(data).decode()


class Server:
    """A small FHIR R4 server that is not in NRCeS shapes. Flags switch features off, as real servers differ."""

    def __init__(self, auth="bearer", everything=False, bare_identifier=True, base=PATH):
        self.auth, self.everything, self.bare_identifier, self.base = auth, everything, bare_identifier, base
        self.seen, self.token_calls, self.valid_tokens = [], 0, {ACCESS}
        self.patient = {"resourceType": "Patient", "id": PID, "identifier": [{"use": "official", "system": SYSTEM, "value": UHID}, {"system": "http://hospital.example/ids/old", "value": "OLD-77"}],
                        "name": [{"given": ["Anitha"], "family": "Reddy (SYNTHETIC)"}], "gender": "female", "birthDate": "1980-01-18"}
        self.encounter = {"resourceType": "Encounter", "id": "enc-1", "status": "finished", "class": {"code": "AMB"}, "subject": {"reference": f"Patient/{PID}"},
                          "identifier": [{"system": "http://hospital.example/ids/visit", "value": "OP/26/118701"}], "period": {"start": "2026-09-01T09:00:00+05:30"},
                          "serviceProvider": {"display": "Breast Surgery"}}
        self.obs = {"resourceType": "Observation", "id": "obs-1", "status": "final", "code": {"coding": [{"system": "http://loinc.org", "code": "718-7"}], "text": "Haemoglobin"},
                    "valueQuantity": {"value": 12.1, "unit": "g/dL"}, "referenceRange": [{"low": {"value": 12}, "high": {"value": 15}}]}
        self.reports = {
            "dr-inline": self.dr("dr-inline", "final", "Histopathology report", "11526-1", [{"contentType": "application/pdf", "data": b64(PDF), "title": "HPE"}], "3"),
            "dr-binary": self.dr("dr-binary", "preliminary", "CECT thorax abdomen pelvis", "18748-4", [{"contentType": "application/pdf", "url": "Binary/bin-1"}], None, "2026-09-02T15:10:00+05:30"),
            "dr-values": self.dr("dr-values", "final", "Complete blood count", "58410-2", [], "1", "2026-09-03T10:00:00+05:30", conclusion="Mild anaemia excluded."),
            "dr-empty": {"resourceType": "DiagnosticReport", "id": "dr-empty", "status": "registered", "subject": {"reference": f"Patient/{PID}"}, "code": {"text": "Ordered test"}}}
        self.binaries = {"bin-1": PDF2}
        self.docrefs, self.orders = [], []

    def dr(self, rid, status, title, loinc, forms, version, issued="2026-09-05T11:00:00+05:30", conclusion=""):
        d = {"resourceType": "DiagnosticReport", "id": rid, "status": status, "subject": {"reference": f"Patient/{PID}", "display": NAME},
             "encounter": {"reference": "Encounter/enc-1"}, "code": {"coding": [{"system": "http://loinc.org", "code": loinc}], "text": title}, "issued": issued,
             "result": [{"reference": "Observation/obs-1"}], "presentedForm": forms, "meta": {"lastUpdated": issued}}
        if version:
            d["meta"]["versionId"] = version
        if conclusion:
            d["conclusion"] = conclusion
        return d

    def _authorised(self, request) -> bool:
        h = request.headers
        if self.auth == "bearer":
            return h.get("authorization") == "Bearer static-token"
        if self.auth == "basic":
            return h.get("authorization") == "Basic " + base64.b64encode(b"reader:pass-word").decode()
        if self.auth == "api_key":
            return h.get("x-hospital-key") == "key-123" and "authorization" not in h
        if self.auth == "oauth2":
            return (h.get("authorization") or "")[7:] in self.valid_tokens and (h.get("authorization") or "").startswith("Bearer ")
        return True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path, q = unquote(request.url.path), parse_qs(request.url.query.decode())
        for secret in (SECRET, ACCESS, "static-token", "pass-word", "key-123"):
            assert secret not in str(request.url)                       # a secret never rides in a URL
        if path == "/oauth/token":
            self.token_calls += 1
            ok = request.method == "POST" and request.headers.get("authorization") == "Basic " + base64.b64encode(f"vaidyx-tb:{SECRET}".encode()).decode() \
                and parse_qs(request.content.decode()).get("grant_type") == ["client_credentials"]
            return httpx.Response(200, json={"access_token": ACCESS, "token_type": "Bearer", "expires_in": 3600}) if ok else httpx.Response(401, json={"error": "invalid_client"})
        if not path.startswith(self.base + "/"):
            return httpx.Response(404, text="not here")
        rest = path[len(self.base) + 1:]
        if rest == "metadata":
            return httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1", "software": {"name": "Plain FHIR (SYNTHETIC)"}})
        if not self._authorised(request):
            return httpx.Response(401, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "sign in"}]})
        parts = rest.split("/")
        if rest == "Patient":
            ident = (q.get("identifier") or [""])[0]
            if not ident:
                return httpx.Response(400, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "a search needs a parameter"}]})
            if "|" not in ident and not self.bare_identifier:
                return httpx.Response(200, json=bundle([]))
            hit = ident.split("|")[-1] in (UHID, "OLD-77") and ("|" not in ident or ident.split("|")[0] == SYSTEM)
            return httpx.Response(200, json=bundle([self.patient] if hit else []))
        if parts[0] == "Patient" and len(parts) == 2:
            return httpx.Response(200, json=self.patient) if parts[1] == PID else httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
        if parts[0] == "Patient" and parts[-1] == "$everything":
            if parts[1] != PID:
                return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
            if not self.everything:
                return httpx.Response(400, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "unknown operation $everything"}]})
            first = [self.patient, self.encounter] + list(self.reports.values())[:2]
            if q.get("page") == ["2"]:
                return httpx.Response(200, json=bundle(list(self.reports.values())[2:] + self.docrefs + self.orders + [self.obs]))
            return httpx.Response(200, json=bundle(first, f"{BASE}{self.base}/Patient/{PID}/$everything?page=2"))
        if parts[0] == "Patient":                                       # $similar and the rest: not served
            return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
        if rest == "Encounter":
            if q.get("identifier"):
                return httpx.Response(200, json=bundle([self.encounter] if q["identifier"][0].split("|")[-1] == "OP/26/118701" else []))
            return httpx.Response(200, json=bundle([self.encounter]))
        if rest == "DiagnosticReport":
            return httpx.Response(200, json=bundle(list(self.reports.values())))
        if parts[0] == "DiagnosticReport" and len(parts) == 2:
            return httpx.Response(200, json=self.reports[parts[1]]) if parts[1] in self.reports else httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
        if parts[0] == "DiagnosticReport":                              # no _history on this server
            return httpx.Response(501, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "history is not kept"}]})
        if rest == "Observation/obs-1":
            return httpx.Response(200, json=self.obs)
        if parts[0] == "Binary" and parts[1] in self.binaries:
            return httpx.Response(200, json={"resourceType": "Binary", "id": parts[1], "contentType": "application/pdf", "data": b64(self.binaries[parts[1]])},
                                  headers={"content-type": "application/fhir+json"})
        if rest == "DocumentReference":
            return httpx.Response(200, json=bundle(self.docrefs))
        if parts[0] == "DocumentReference" and len(parts) == 2:
            d = next((x for x in self.docrefs if x["id"] == parts[1]), None)
            return httpx.Response(200, json=d) if d else httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
        if rest == "ServiceRequest":
            return httpx.Response(200, json=bundle(self.orders))
        if rest in ("Specimen", "ImagingStudy", "Provenance", "Organization"):   # resource types this server does not have
            return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": f"unknown resource type {rest}"}]})
        return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})


AUTHS = {"bearer": {"type": "bearer", "token": "static-token"}, "basic": {"type": "basic", "username": "reader", "password": "pass-word"},
         "api_key": {"type": "api_key", "header": "X-Hospital-Key", "key": "key-123"},
         "oauth2": {"type": "oauth2", "token_url": BASE + "/oauth/token", "client_id": "vaidyx-tb", "client_secret": SECRET}}


def client(server, auth="bearer", systems=(SYSTEM,), **kw):
    return GenericFHIRClient(BASE, AUTHS[auth], label="Plain FHIR (SYNTHETIC)", base_path=server.base, identifier_systems=systems, transport=httpx.MockTransport(server), **kw)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def no_cached_tokens():
    fhir_generic._TOKENS.clear()
    yield
    fhir_generic._TOKENS.clear()


# ---- identity -----------------------------------------------------------------------------------------------------------------
def test_base_path_identifier_search_with_systems_and_visit_number():
    s = Server()
    c = client(s)
    assert c.fhir_base == BASE + PATH and "static-token" not in repr(c)
    p = run(c.find_patient(UHID))
    assert p["id"] == PID and p["uhid"] == UHID and p["name"] == NAME and p["sex"] == "F" and p["matched_on"] == {"kind": "uhid", "value": UHID} and p["similar"] == []
    s2 = Server(bare_identifier=False)                                  # a server that wants system|value
    c2 = client(s2)
    assert run(c2.find_patient(UHID))["uhid"] == UHID
    asked = [parse_qs(r.url.query.decode())["identifier"][0] for r in s2.seen if r.url.path.endswith("/Patient") and b"identifier" in r.url.query]
    assert asked == [UHID, f"{SYSTEM}|{UHID}"]
    assert run(client(Server(bare_identifier=False), systems=()).find_patient(UHID)) is None     # no system configured: not found, not a guess
    by_visit = run(c.find_patient("OP/26/118701"))
    assert by_visit["uhid"] == UHID and by_visit["matched_on"] == {"kind": "op_no", "value": "OP/26/118701"}
    assert run(c.find_patient("NOBODY-1")) is None and run(c.find_patient(" ")) is None
    assert run(client(Server(), systems=()).find_patient("OLD-77"))["uhid"] == UHID            # the official identifier is the UHID, whichever matched
    encs = run(c.encounters(PID))
    assert [(e["kind"], e["number"], e["department"]) for e in encs] == [("OP", "OP/26/118701", "Breast Surgery")]


# ---- fallbacks ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("everything", [False, True])
def test_reports_without_documentreference_provenance_or_everything(everything):
    s = Server(everything=everything)
    c = client(s)
    reps = {r["id"]: r for r in run(c.reports(PID))}
    assert sorted(reps) == ["dr-binary", "dr-inline", "dr-values"]      # a report with no file and nothing written is not delivered
    inline, binary, values = reps["dr-inline"], reps["dr-binary"], reps["dr-values"]
    assert inline["status"] == "final" and inline["version"] == 3 and inline["current"] is True and inline["doc_type"] == "histopathology" and inline["kind"] == "diagnostic"
    assert binary["status"] == "preliminary" and binary["version"] == 1 and binary["doc_type"] == "ct" and binary["encounter_number"] == "OP/26/118701"
    assert all(r["signature"] is None for r in reps.values())           # no Provenance: unknown, never "yes"
    assert inline["observations"][0]["value"] == "12.1 g/dL" and inline["observations"][0]["fact"] == his_client.fact_for("718-7", "Haemoglobin")
    assert set(his_case._HIS_KEYS) <= set(inline) and "data" not in str(inline["document"])
    d = run(c.document(inline["document_ref"]))
    assert d["content"] == PDF and d["sha256"] == hashlib.sha256(PDF).hexdigest() and d["filename"].endswith(".pdf")
    assert run(c.document(binary["document_ref"]))["content"] == PDF2   # a Binary resource behind the url, on the same server
    assert values["document"]["text_only"] is True and values["observations"] == [] and "text only" in values["doc_type_basis"]
    t = run(c.document(values["document_ref"]))
    text = t["content"].decode()
    assert t["filename"].endswith(".txt") and "COMPLETE BLOOD COUNT" in text and "Haemoglobin: 12.1 g/dL   (reference range 12 to 15)" in text
    assert "Conclusion: Mild anaemia excluded." in text and f"Patient name : {NAME}   UHID : {UHID}" in text and "Report status: FINAL" in text
    paths = [r.url.path for r in s.seen]
    assert any(p.endswith("/$everything") for p in paths) and (everything or any(p.endswith("/DiagnosticReport") for p in paths))
    assert [r["id"] for r in run(c.reports(PID, "2026-09-04"))] == ["dr-inline"]
    assert run(c.open_orders(PID)) == [] and run(c.referrals(PID)) == [] and run(c.hospital()) == {"name": "Plain FHIR (SYNTHETIC)", "departments": []}
    with pytest.raises(his_client.HISError, match="no registration"):
        run(c.reports("someone-else"))


def test_a_real_documentreference_is_joined_to_its_report_and_orders_are_listed():
    s = Server()
    s.reports = {"dr-inline": s.reports["dr-inline"]}
    s.reports["dr-inline"]["presentedForm"] = []
    s.docrefs = [{"resourceType": "DocumentReference", "id": "doc-9", "status": "current", "meta": {"versionId": "7", "lastUpdated": "2026-09-05T11:05:00+05:30"},
                  "subject": {"reference": f"Patient/{PID}"}, "content": [{"attachment": {"contentType": "application/pdf", "url": f"{BASE}{PATH}/Binary/bin-1", "title": "HPE"}}],
                  "context": {"related": [{"reference": "DiagnosticReport/dr-inline"}]}},
                 {"resourceType": "DocumentReference", "id": "note-1", "status": "current", "docStatus": "final", "date": "2026-09-24T10:00:00+05:30", "description": "Discharge summary",
                  "subject": {"reference": f"Patient/{PID}"}, "content": [{"attachment": {"contentType": "application/pdf", "data": b64(PDF)}}]}]
    s.orders = [{"resourceType": "ServiceRequest", "id": "sr-1", "status": "active", "subject": {"reference": f"Patient/{PID}"}, "code": {"text": "PET-CT whole body"},
                 "authoredOn": "2026-09-25T09:00:00+05:30", "encounter": {"reference": "Encounter/enc-1"}}]
    c = client(s)
    reps = {r["id"]: r for r in run(c.reports(PID))}
    assert reps["dr-inline"]["document_ref"] == "DocumentReference/doc-9" and reps["dr-inline"]["status"] == "final" and reps["dr-inline"]["version"] == 3
    assert reps["dr-inline"]["observations"] and run(c.document("DocumentReference/doc-9"))["content"] == PDF2
    note = next(r for r in reps.values() if r["kind"] == "note")
    assert note["status"] == "final" and note["title"] == "Discharge summary" and run(c.document(note["document_ref"]))["content"] == PDF
    (o,) = run(c.open_orders(PID))
    assert o["test"] == "PET-CT whole body" and o["stage"] == "ordered" and o["encounter_number"] == "OP/26/118701"


def test_paging_and_files_stay_on_the_configured_server():
    s = Server(everything=True)
    c = client(s)
    assert len(run(c.reports(PID))) == 3 and any(r.url.query == b"page=2" for r in s.seen)      # link[next] followed on the same origin
    evil = Server(everything=True)
    real_call = evil.__call__

    def handler(request):
        if request.url.path.endswith("/$everything"):
            return httpx.Response(200, json=bundle([evil.patient], "http://evil.example/steal?page=2"))
        return real_call(request)
    c2 = GenericFHIRClient(BASE, AUTHS["bearer"], base_path=PATH, transport=httpx.MockTransport(handler))
    with pytest.raises(his_client.HISError, match="another server"):    # a link to another server is refused, never followed and never papered over
        run(c2.reports(PID))
    assert not any(r.url.host == "evil.example" for r in evil.seen)
    s.reports["dr-binary"]["presentedForm"] = [{"contentType": "application/pdf", "url": "http://evil.example/file.pdf"}]
    ref = next(r["document_ref"] for r in run(c.reports(PID)) if r["id"] == "dr-binary")
    with pytest.raises(his_client.HISError, match="another server"):
        run(c.document(ref))


# ---- sign-in ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("auth", ["bearer", "basic", "api_key", "oauth2"])
def test_each_sign_in_reaches_the_server_and_a_wrong_one_is_a_plain_error(auth, caplog):
    caplog.set_level(logging.DEBUG)
    s = Server(auth=auth)
    c = client(s, auth)
    ping = run(c.ping())
    assert ping["ok"] and ping["token_ok"] is True and ping["fhir_version"] == "4.0.1" and ping["name"] == "Plain FHIR (SYNTHETIC)"
    assert run(c.find_patient(UHID))["uhid"] == UHID
    wrong = Server(auth={"bearer": "basic", "basic": "api_key", "api_key": "oauth2", "oauth2": "bearer"}[auth])
    bad = run(client(wrong, auth).ping())
    assert bad["ok"] is False and bad["token_ok"] is False and "refused" in bad["error"]
    with pytest.raises(his_client.HISError) as e:
        run(client(wrong, auth).find_patient(UHID))
    for secret in (SECRET, ACCESS, "static-token", "pass-word", "key-123"):
        assert secret not in caplog.text and secret not in bad["error"] and secret not in str(e.value) and secret not in repr(c)


def test_oauth2_token_is_fetched_once_reused_and_renewed_when_refused(caplog):
    caplog.set_level(logging.DEBUG)
    s = Server(auth="oauth2")
    c = client(s, "oauth2")
    assert run(c.find_patient(UHID))["uhid"] == UHID and len(run(c.reports(PID))) == 3 and run(c.ping())["ok"]
    assert run(client(s, "oauth2").encounters(PID))                     # another client object (his_client.client() makes one per call): the same token
    assert s.token_calls == 1
    s.valid_tokens.clear()                                              # the server withdrew the token early
    with pytest.raises(his_client.HISError, match="refused the token"):
        run(c.encounters(PID))
    assert s.token_calls == 2                                           # one fresh token, one retry, then a plain error
    s.valid_tokens.add(ACCESS)
    (key,) = fhir_generic._TOKENS
    fhir_generic._TOKENS[key] = (ACCESS, 0.0)                           # expired
    assert run(c.encounters(PID)) and s.token_calls == 3
    bad = GenericFHIRClient(BASE, {**AUTHS["oauth2"], "client_secret": "wrong-" + "w" * 10}, base_path=PATH, transport=httpx.MockTransport(s))
    out = run(bad.ping())
    assert out["ok"] is False and "token endpoint" in out["error"] and "wrong-" not in out["error"]
    for secret in (SECRET, ACCESS, "wrong-wwwwwwwwww"):
        assert secret not in caplog.text
    assert all(ACCESS not in str(r.url) and SECRET not in str(r.url) for r in s.seen)


def test_server_down_and_bad_settings_are_plain_errors():
    def down(request):
        raise httpx.ConnectError("refused")
    c = GenericFHIRClient(BASE, AUTHS["bearer"], base_path=PATH, transport=httpx.MockTransport(down))
    assert "cannot reach" in run(c.ping())["error"]
    with pytest.raises(his_client.HISError, match="cannot reach"):
        run(c.reports(PID))
    with pytest.raises(his_client.HISError):
        GenericFHIRClient("ftp://x", AUTHS["bearer"])
    with pytest.raises(his_client.HISError):
        GenericFHIRClient(BASE, {"type": "kerberos"})


# ---- through the Case File ----------------------------------------------------------------------------------------------------
def test_create_a_case_file_from_a_plain_fhir_server(fakes, monkeypatch):
    s = Server(auth="basic")
    c = client(s, "basic")
    monkeypatch.setattr(his_client, "client", lambda *a, **k: c)
    look = run(his_case.lookup(UHID, {"all": True}))
    assert look["found"] and look["patient"]["uhid"] == UHID and look["reports"] == 3

    async def go():
        out = await his_case.create(UHID, "breast", "early", "optimal", "", {"all": True}, "dr.breast", ROLES_DOC)
        await out["job"]["task"]
        return out
    out = run(go())
    case = out["case"]
    assert case["patient"]["mrn"] == UHID and case["his"]["kind"] == "fhir_generic" and out["job"]["his"]["added"] == 3 and out["job"]["his"]["errors"] == []
    docs = {d["his"]["id"]: d for d in store.list_docs(case["case_id"])}
    hpe, ct, cbc = docs["dr-inline"], docs["dr-binary"], docs["dr-values"]
    assert hpe["ext"] == ".pdf" and hpe["classification"]["status"] == "FINAL" and hpe["classification"]["signed"] != "yes" and hpe["his"]["signature"] is None
    assert ct["classification"]["status"] == "PRELIMINARY" and cbc["ext"] == ".txt" and cbc["his"]["observations"] == [] and cbc["state"] == "ready"
    s.reports["dr-binary"] = s.dr("dr-binary", "final", "CECT thorax abdomen pelvis", "18748-4", [{"contentType": "application/pdf", "url": "Binary/bin-2"}], "2", "2026-09-08T10:00:00+05:30")
    s.binaries["bin-2"] = PDF2 + b"Verified by the consultant\n"

    async def again():
        job = await his_case.refetch(case["case_id"], "dr.breast")
        await job["task"]
        return job
    job = run(again())
    assert job["his"]["added"] == 1                                    # the amended report is a new version
    versions = sorted((d["his"]["version"], bool(d.get("superseded"))) for d in store.list_docs(case["case_id"]) if d["his"]["id"] == "dr-binary")
    assert versions == [(1, True), (2, False)]                          # the earlier one is kept as history


def test_against_the_demo_hospitals_captured_answers_it_agrees_with_the_nrces_client():
    """Pointed at the demo FHIR server (NRCeS shapes, captured answers), the generic adapter returns the same report versions, statuses,
    signatures and documents as the tested client; only the values of a superseded version are not read (it asks for no history)."""
    from tumour_board.tests.test_his_client import BASE as DEMO, TOKEN, Mock
    g = GenericFHIRClient(DEMO, {"type": "bearer", "token": TOKEN}, base_path="/fhir", transport=httpx.MockTransport(Mock()))
    f = his_client.FHIRClient(DEMO, TOKEN, transport=httpx.MockTransport(Mock()))
    assert run(g.ping())["ok"] and run(g.find_patient("VXH/26/004201"))["uhid"] == "VXH/26/004201" and run(g.find_patient("IP/26/01875"))["matched_on"]["kind"] == "ip_no"
    a = {(r["id"], r["version"]): r for r in run(f.reports("vxh-26-004202"))}
    b = {(r["id"], r["version"]): r for r in run(g.reports("vxh-26-004202"))}
    assert set(a) == set(b) and len(b) == 11
    differing = {(k, field) for k in a for field in a[k] if a[k][field] != b[k][field]}
    assert differing <= {(("p02-r05", 1), "observations"), (("p02-r05", 1), "conclusion")}
    assert b[("p02-r05", 2)]["signature"] == a[("p02-r05", 2)]["signature"] and [b[("p02-r05", v)]["current"] for v in (1, 2)] == [False, True]
    assert run(g.document("DocumentReference/doc-p02-r05-v2"))["sha256"] == run(f.document("DocumentReference/doc-p02-r05-v2"))["sha256"]
    assert run(g.open_orders("vxh-26-004202")) == run(f.open_orders("vxh-26-004202"))
