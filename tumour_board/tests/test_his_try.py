"""POST /his/try ("Choose your hospital system", docs/new-case/DESIGN.md N7): settings are tested WITHOUT being saved, by those who
may save them, under the same rules as saving (the host rule, the folder roots, a secret left empty keeps the saved one only for the
same kind and server); one UHID can be tried and shows counts only, no patient data to anyone (the Vaidyx admin and the hospital admin are not clinical
users); at most 20 tries per 10 minutes per login; a hospital system that is down or slow gives a plain error with what to check; the
fingerprint of a passing test must match what POST /setup/his then saves (old callers without it are unchanged); no secret is ever in
an answer or the audit. SYNTHETIC data only, a fake login system, the HIS mocked with httpx.MockTransport (no network, except one
connection refused on a closed loopback port)."""
import asyncio
import json
import socket

import httpx
import pytest

from tumour_board import his_client, org
from tumour_board.api import setup
from tumour_board.his_adapters import _common, fhir_generic
from tumour_board.tests.test_his_adapters_fhir_generic import BASE, NAME, PATH, Server
from tumour_board.tests.test_his_adapters_hl7v2 import UHID, oru
from tumour_board.tests.test_nik_me import ANIL, AUDIT, DEEPAK, RAO, ROOT, VX, api, auth, people  # noqa: F401

PASSWORD = "pass-word"            # what the mock Server accepts for HTTP basic (reader:pass-word)
FHIR_TOKEN = "nrces-token-" + "n" * 10
NRCES = "http://127.0.0.1:8091"


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for k in ("TB_HIS_URL", "TB_HIS_TOKEN", "TB_HIS_TOKEN_FILE", "TB_HIS_ALLOW_HOSTS", "TB_HIS_FOLDER_ROOTS"):
        monkeypatch.delenv(k, raising=False)
    _common._CACHE.clear()
    fhir_generic._TOKENS.clear()
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", None)
    setup.TRY_LIMIT._hits.clear()
    yield
    setup.TRY_LIMIT._hits.clear()


def audit_lines(kind="his_try") -> list:
    """The audit lines of one kind, oldest first."""
    return [e for e in reversed(org.read_audit(1000)) if e.get("kind") == kind]


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def lab_folder(data_root):
    inbox = data_root / "his_inbox" / "lab"
    inbox.mkdir(parents=True)
    (inbox / "a.hl7").write_text(oru(), newline="")
    return inbox


def nrces_server(seen: list):
    """The smallest NRCeS-shaped FHIR server: metadata without a token, a Patient search with the bearer token."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization") or "")
        if request.url.path == "/fhir/metadata":
            return httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1", "software": {"name": "NRCeS mock (SYNTHETIC)"}})
        if request.headers.get("authorization") != f"Bearer {FHIR_TOKEN}":
            return httpx.Response(401, json={"resourceType": "OperationOutcome", "issue": []})
        if request.url.path == "/fhir/Patient":
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 7, "entry": []})
        if request.url.path == "/fhir/DiagnosticReport":
            return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 31, "entry": []})
        return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": []})
    return handler


# ---- who may, and nothing is saved -----------------------------------------------------------------------------------------------
def test_try_tests_without_saving_and_only_for_those_who_may_save(api, data_root):
    inbox = lab_folder(data_root)
    body = {"preset": "generic_hl7v2", "folder": str(inbox)}
    for who in (RAO, DEEPAK, ANIL, AUDIT):
        assert api.as_(who).post("/his/try", body).status_code == 403
    r = api.as_(ROOT).post("/his/try", body | {"identifier": UHID})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["ok"] is True and v["kind"] == "hl7v2_folder" and v["preset"] == "generic_hl7v2" and v["counts"]["patients"] == 1 and v["counts"]["reports"] == 1
    assert v["error"] == "" and v["fingerprint"].startswith("fp1-") and v["checked_at"] and v["ping"]["ok"] is True
    assert v["sample"]["found"] is True and v["sample"]["reports"] == 1 and v["sample"]["newest_report_date"].startswith("2026-09-05")
    assert NAME not in r.text and "patient" not in v["sample"]
    # nothing was written: no his.json, no secret folder, no test record, no set-up stamp; the defaults still stand
    assert not (data_root / "his.json").exists() and not (data_root / "his_secrets").exists()
    assert "his_test" not in org.load()["hospital"] and "his" not in (org.load()["hospital"].get("setup_steps") or {})
    assert his_client.settings()["kind"] == "fhir"
    ev = audit_lines()
    assert len(ev) == 1 and ev[0]["by"] == ROOT and ev[0]["kind"] == "his_try" and ev[0]["ok"] is True and ev[0]["found"] is True and ev[0]["identifier"] == UHID
    assert not audit_lines("his_settings_saved") and not audit_lines("his_test")


def test_the_same_rules_as_saving_hold(api, data_root, monkeypatch):
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(Server()))
    remote = {"kind": "fhir_generic", "url": "http://10.0.0.5:8085", "base_path": PATH, "auth": "bearer", "token": "static-token"}
    r = api.as_(ROOT).post("/his/try", remote)
    assert r.status_code == 400 and "Vaidyx admin" in r.text and "static-token" not in r.text      # another host: not for a hospital admin
    r = api.as_(VX).post("/his/try", remote)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text                                  # the Vaidyx admin may
    r = api.as_(ROOT).post("/his/try", {"kind": "folder_bridge", "folder": "/etc"})
    assert r.status_code == 400 and "allowed folder root" in r.text
    r = api.as_(ROOT).post("/his/try", {"kind": "abdm_bundles", "folder": str(data_root / "his_inbox" / ".." / "cases")})
    assert r.status_code == 400 and "'..'" in r.text
    assert api.as_(ROOT).post("/his/try", {"preset": "no_such"}).status_code == 400
    assert api.as_(ROOT).post("/his/try", {"kind": "mcp", "connector": "x"}).status_code == 400
    assert api.as_(ROOT).post("/his/try", {}).status_code == 400
    refused = [e for e in audit_lines() if e.get("refused")]
    assert len(refused) >= 3 and all(e["ok"] is False for e in refused)
    assert not (data_root / "his.json").exists()


# ---- secrets ----------------------------------------------------------------------------------------------------------------------
def test_an_empty_secret_keeps_the_saved_one_for_the_same_server_only(api, data_root, monkeypatch):
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(Server(auth="basic")))
    his_client.save_settings({"kind": "fhir_generic", "url": BASE, "base_path": PATH, "auth": "basic", "username": "reader", "password": PASSWORD}, by=ROOT)
    api.as_(ROOT)
    r = api.post("/his/try", {"kind": "fhir_generic", "url": BASE, "base_path": PATH, "auth": "basic", "username": "reader", "password": ""})
    assert r.status_code == 200 and r.json()["ok"] is True, r.text                                  # re-tested without re-typing the password
    r = api.post("/his/try", {"kind": "fhir_generic", "url": BASE, "base_path": PATH, "auth": "basic", "username": "reader", "password": "set"})
    assert r.status_code == 200 and r.json()["ok"] is True                                          # the word the screen was given back is not a secret
    r = api.post("/his/try", {"kind": "fhir_generic", "url": "http://localhost:8085", "base_path": PATH, "auth": "basic", "username": "reader", "password": ""})
    assert r.status_code == 400 and "password" in r.text                                            # a saved secret never follows a change of host
    r = api.post("/his/try", {"kind": "fhir_generic", "url": BASE, "base_path": PATH, "auth": "basic", "username": "reader", "password": "wrong-one"})
    v = r.json()
    assert r.status_code == 200 and v["ok"] is False and v["fingerprint"] == "" and "sign-in" in v["hint"]   # a typed secret is used (and fails)
    assert (data_root / "his_secrets" / "password").read_text().strip() == PASSWORD                  # trying never replaced the saved secret
    # the "fhir" kind: an empty token keeps the saved token for the same address
    seen = []
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(nrces_server(seen)))
    his_client.save_settings({"kind": "fhir", "url": NRCES, "token": FHIR_TOKEN}, by=ROOT)
    r = api.post("/his/try", {"preset": "abdm_nrces_fhir", "url": NRCES, "token": ""})
    v = r.json()
    assert r.status_code == 200 and v["ok"] is True and v["counts"] == {"patients": 7, "reports": 31} and v["ping"]["token_ok"] is True, r.text
    assert f"Bearer {FHIR_TOKEN}" in seen
    for text in (r.text, json.dumps(org.read_audit(1000))):
        assert FHIR_TOKEN not in text and PASSWORD not in text and "wrong-one" not in text


def test_no_secret_in_the_answer_or_the_audit(api, data_root, monkeypatch):
    s = Server(auth="oauth2")
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(s))
    secret = "client-secret-" + "s" * 12
    r = api.as_(ROOT).post("/his/try", {"preset": "international_fhir", "url": BASE, "base_path": PATH, "token_url": BASE + "/oauth/token",
                                        "client_id": "vaidyx-tb", "client_secret": secret, "identifier": UHID})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["sample"]["found"] is True, r.text
    stored = "\n".join(p.read_text(errors="replace") for p in data_root.rglob("*") if p.is_file())
    for text in (r.text, json.dumps(org.read_audit(1000)), stored):
        assert secret not in text and "access-token-" not in text
    assert not (data_root / "his_secrets").exists()


# ---- one patient ---------------------------------------------------------------------------------------------------------------
def test_one_uhid_found_and_not_found(api, data_root, monkeypatch):
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(Server()))
    body = {"preset": "hapi_fhir", "url": BASE, "base_path": PATH, "token": "static-token"}
    r = api.as_(ROOT).post("/his/try", body | {"identifier": f"  {UHID} "})
    v = r.json()
    assert r.status_code == 200 and v["ok"] is True, r.text
    # counts only: no name, initials, age, sex or report title, for the hospital admin as for the Vaidyx admin (owner, 17 Nov 2026)
    assert v["sample"] == {"found": True, "identifier": UHID, "visits": 1, "reports": 3, "newest_report_date": "2026-09-05"}
    for text in (r.text, json.dumps(audit_lines())):
        assert NAME not in text and "A. R." not in text and "Histopathology report" not in text
    r = api.post("/his/try", body | {"identifier": "VXH/99/000000"})
    assert r.json()["ok"] is True and r.json()["sample"] == {"found": False, "identifier": "VXH/99/000000"}
    assert api.post("/his/try", body).json().get("sample") is None                                   # no identifier: no patient read
    r = api.as_(VX).post("/his/try", body | {"identifier": UHID})
    assert r.json()["sample"] == {"found": True, "identifier": UHID, "visits": 1, "reports": 3, "newest_report_date": "2026-09-05"}
    assert NAME not in r.text and "A. R." not in r.text
    ev = audit_lines()
    assert [e["found"] for e in ev] == [True, False, None, True] and ev[0]["identifier"] == UHID and not any("uhid" in e for e in ev)


def test_tries_are_limited_per_login(api, data_root, monkeypatch):
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(Server()))
    body = {"preset": "hapi_fhir", "url": BASE, "base_path": PATH, "token": "static-token"}
    for _ in range(20):
        assert api.as_(ROOT).post("/his/try", body).status_code == 200
    r = api.post("/his/try", body | {"identifier": UHID})
    assert r.status_code == 429 and r.json()["detail"]["message"].startswith("Too many tests") and "sample" not in r.text
    assert api.as_(VX).post("/his/try", body).status_code == 200                                      # per login: another login is not held up
    assert len(audit_lines()) == 21                                                                   # the refused try reached nothing


# ---- down or slow ----------------------------------------------------------------------------------------------------------------
def test_a_hospital_system_that_is_down_gives_a_plain_error(api, data_root):
    url = f"http://127.0.0.1:{closed_port()}"
    r = api.as_(ROOT).post("/his/try", {"kind": "fhir", "url": url, "token": "tok-" + "t" * 8, "identifier": UHID})
    v = r.json()
    assert r.status_code == 200 and v["ok"] is False and v["fingerprint"] == "" and "sample" not in v
    assert v["error"].startswith("Cannot reach the HIS at") and "Traceback" not in v["error"] and "tok-tttt" not in r.text
    assert "server address" in v["hint"]
    ev = audit_lines()[-1]
    assert ev["ok"] is False and "Cannot reach" in ev["error"] and "tok-tttt" not in json.dumps(ev)
    r = api.post("/his/try", {"kind": "hl7v2_folder", "folder": str(data_root / "his_inbox" / "not_made")})
    assert r.json()["ok"] is False and "does not exist" in r.json()["error"] and "folder" in r.json()["hint"]


def test_a_slow_hospital_system_is_cut_short(api, data_root, monkeypatch):
    async def slow(request):
        await asyncio.sleep(3)
        return httpx.Response(200, json={})
    monkeypatch.setattr(setup, "_TRY_TRANSPORT", httpx.MockTransport(slow))
    monkeypatch.setattr(setup, "TRY_SECONDS", 0.3)
    r = api.as_(ROOT).post("/his/try", {"kind": "fhir", "url": NRCES, "token": FHIR_TOKEN})
    v = r.json()
    assert v["ok"] is False and "longer than" in v["error"] and v["latency_ms"] < 2500 and "slow" in v["hint"]


# ---- the save must match the test --------------------------------------------------------------------------------------------------
def test_the_save_is_refused_when_it_differs_from_what_was_tested(api, data_root):
    inbox = lab_folder(data_root)
    api.as_(ROOT)
    body = {"preset": "generic_hl7v2", "folder": str(inbox), "label": "Lab results (SYNTHETIC)"}
    fp = api.post("/his/try", body).json()["fingerprint"]
    assert fp and api.post("/his/try", body).json()["fingerprint"] == fp                             # the same values: the same fingerprint
    for changed in (body | {"label": "Another name"}, body | {"folder": str(data_root / "his_inbox")}, {"kind": "folder_bridge", "folder": str(inbox)}):
        r = api.post("/setup/his", changed | {"tested_fingerprint": fp})
        assert r.status_code == 409 and "Test these settings again" in r.text
    assert api.post("/setup/his", body | {"tested_fingerprint": "fp1-" + "0" * 40}).status_code == 409
    assert not (data_root / "his.json").exists() and not audit_lines("his_settings_saved")
    r = api.post("/setup/his", body | {"tested_fingerprint": fp})
    assert r.status_code == 200 and r.json()["test"]["ok"] is True, r.text
    assert his_client.settings()["kind"] == "hl7v2_folder" and his_client.settings()["label"] == "Lab results (SYNTHETIC)"
    # a secret typed for the test and another one typed for the save: refused
    s = his_client.trial_settings({"kind": "fhir_generic", "url": BASE, "auth": "basic", "username": "reader", "password": "one"})
    t = his_client.trial_settings({"kind": "fhir_generic", "url": BASE, "auth": "basic", "username": "reader", "password": "two"})
    assert his_client.fingerprint(s) != his_client.fingerprint(t) and "one" not in his_client.fingerprint(s)
    r = api.post("/setup/his", {"kind": "fhir_generic", "url": BASE, "auth": "basic", "username": "reader", "password": "two", "tested_fingerprint": his_client.fingerprint(s)})
    assert r.status_code == 409 and not (data_root / "his_secrets").exists()


def test_old_callers_without_a_fingerprint_are_unchanged(api, data_root, monkeypatch):
    monkeypatch.setattr(his_client, "client", lambda *a, **k: None)
    api.as_(ROOT)
    r = api.post("/setup/his", {"url": "http://127.0.0.1:7130", "token": "synthetic-his-token"})
    assert r.status_code == 200 and r.json()["ok"] is False and "synthetic-his-token" not in r.text and his_client.settings()["kind"] == "fhir"
    assert api.post("/setup/his", {}).status_code == 400
    r = api.post("/setup/his", {"kind": "fhir", "url": "ftp://x"})
    assert r.status_code == 400 and r.json()["detail"]["message"] == "url must start with http:// or https://"     # the old wording, not capitalised
    r = api.post("/setup/his", {"kind": "hl7v2_folder", "folder": "/etc"})
    assert r.status_code == 400 and r.json()["detail"]["message"].startswith("The folder must be inside")
    r = api.post("/setup/his", {"url": "http://127.0.0.1:7130", "token": "synthetic-his-token", "tested_fingerprint": ""})
    assert r.status_code == 200                                                                      # an empty fingerprint is the old body
