"""The adapter registry (his_adapters.registry), the presets file and the set-up API: make() for every kind, validation with plain
errors, the host rule on every URL (the OAuth2 token endpoint too), folders inside the allowed roots, secrets in owner-only files and
never in an answer, the defaults unchanged with no his.json, honest presets, and GET /his/kinds for those who may save the connection.
SYNTHETIC data only, a fake login system, no network."""
import asyncio
import json
import stat

import httpx
import pytest

from tumour_board import config, his_client, org
from tumour_board.his_adapters import _common, fhir_generic, registry
from tumour_board.his_adapters.abdm_bundle import ABDMBundleClient
from tumour_board.his_adapters.folder_bridge import FolderBridgeClient
from tumour_board.his_adapters.hl7v2 import HL7v2FolderClient
from tumour_board.tests.test_his_adapters_fhir_generic import ACCESS, BASE, PATH, PID, SECRET, SYSTEM, Server
from tumour_board.tests.test_his_adapters_hl7v2 import UHID, oru
from tumour_board.tests.test_nik_me import ANIL, AUDIT, DEEPAK, RAO, ROOT, VX, api, auth, people  # noqa: F401

PASSWORD = "pass-word"
KEY = "key-123"


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    f = tmp_path / "his_token_synthetic"
    f.write_text("synthetic-file-token\n")
    monkeypatch.setenv("TB_HIS_TOKEN_FILE", str(f))
    for k in ("TB_HIS_URL", "TB_HIS_TOKEN", "TB_HIS_ALLOW_HOSTS", "TB_HIS_FOLDER_ROOTS"):
        monkeypatch.delenv(k, raising=False)
    _common._CACHE.clear()
    fhir_generic._TOKENS.clear()


def mode(p) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def stored(root) -> str:
    return "\n".join(p.read_text(errors="replace") for p in root.rglob("*") if p.is_file() and "his_secrets" not in p.parts)


# ---- defaults and make() ------------------------------------------------------------------------------------------------------
def test_defaults_are_unchanged_without_his_json(data_root, monkeypatch):
    monkeypatch.delenv("TB_HIS_TOKEN_FILE")
    d = his_client.settings()
    assert d == {"kind": "fhir", "label": "Vaidyx Demo Hospital HIS (SYNTHETIC)", "url": "http://127.0.0.1:7130", "token": "",
                 "token_file": str(config.REPO / "data" / "his_mock" / "token"), "connector": "", "enabled": True, "pacs_url": "http://127.0.0.1:8042"}
    assert his_client.KINDS == ("fhir", "mcp", "none") and registry.KINDS == ("fhir", "mcp", "none", "fhir_generic", "hl7v2_folder", "folder_bridge", "abdm_bundles")
    c = his_client.client()
    assert type(c) is his_client.FHIRClient and c.fhir_base == "http://127.0.0.1:7130/fhir" and c.kind == "fhir"
    assert set(his_client.public(d)) == set(d) - {"token"} | {"has_token"}                    # no new key appears for the old kinds
    m = registry.make(d)
    assert type(m) is his_client.FHIRClient and m.fhir_base == c.fhir_base and m.label == c.label
    assert registry.make({**d, "enabled": False}) is None and registry.make({**d, "kind": "none"}) is None and registry.make({**d, "kind": "mcp", "connector": "nope"}) is None
    assert not (data_root / "his.json").exists() and not (data_root / "his_secrets").exists()


def test_make_builds_the_client_of_every_kind(data_root):
    inbox = data_root / "his_inbox"
    base = {"enabled": True, "label": "X (SYNTHETIC)", "url": "", "token": "", "token_file": ""}
    for kind, cls in (("hl7v2_folder", HL7v2FolderClient), ("folder_bridge", FolderBridgeClient), ("abdm_bundles", ABDMBundleClient)):
        c = his_client.client({**base, "kind": kind, "adapter": {"folder": str(inbox / kind)}})
        assert type(c) is cls and c.kind == kind and c.label == "X (SYNTHETIC)" and c.folder == str(inbox / kind)
        assert his_client.client({**base, "kind": kind, "enabled": False, "adapter": {"folder": str(inbox)}}) is None
    c = his_client.client({**base, "kind": "fhir_generic", "url": BASE, "token": "static-token",
                           "adapter": {"auth": "bearer", "base_path": PATH, "identifier_systems": [SYSTEM]}}, transport=httpx.MockTransport(Server()))
    assert type(c) is fhir_generic.GenericFHIRClient and c.kind == "fhir_generic" and c.fhir_base == BASE + PATH and c.identifier_systems == [SYSTEM]
    assert asyncio.run(c.find_patient(UHID))["uhid"] == UHID
    assert all(k["kind"] in registry.KINDS for k in registry.describe()) and {k["kind"] for k in registry.describe()} == set(registry.KINDS)


# ---- validation ---------------------------------------------------------------------------------------------------------------
def test_validation_errors_are_plain_and_urls_follow_the_host_rule(data_root, monkeypatch):
    ok = {"kind": "fhir_generic", "url": BASE, "auth": "bearer", "token": "static-token"}
    for bad, word in (({**ok, "url": "ftp://x"}, "http"), ({**ok, "url": "http://user:pw@127.0.0.1:1/fhir"}, "no user name"), ({**ok, "url": "http://10.0.0.5:8080/fhir"}, "Vaidyx admin"),
                      ({**ok, "token": ""}, "token"), ({**ok, "auth": "kerberos"}, "sign-in"), ({**ok, "base_path": "/a/../b"}, "base path"), ({**ok, "base_path": "/fhir?x=1"}, "base path"),
                      ({**ok, "identifier_systems": ["a|b"]}, "identifier system"), ({**ok, "identifier_systems": [f"s{i}" for i in range(11)]}, "at most 10"),
                      ({**ok, "auth": "basic"}, "user name"), ({**ok, "auth": "basic", "username": "a:b", "password": "x"}, "':'"), ({**ok, "auth": "basic", "username": "reader"}, "password"),
                      ({**ok, "auth": "api_key", "api_key": "k", "api_key_header": "Host"}, "header"), ({**ok, "auth": "api_key", "api_key": "k", "api_key_header": "X Bad"}, "header"),
                      ({**ok, "auth": "api_key"}, "api key"), ({**ok, "auth": "oauth2", "client_id": "c", "client_secret": "s"}, "token endpoint"),
                      ({**ok, "auth": "oauth2", "token_url": "https://login.elsewhere.example/token", "client_id": "c", "client_secret": "s"}, "token endpoint"),
                      ({**ok, "auth": "oauth2", "token_url": BASE + "/oauth/token", "client_secret": "s"}, "client id"),
                      ({**ok, "auth": "oauth2", "token_url": BASE + "/oauth/token", "client_id": "c"}, "client secret"),
                      ({**ok, "preset": "no_such_system"}, "not a hospital system"), ({**ok, "preset": "generic_folder"}, "folder_bridge"),
                      ({"kind": "hl7v2_folder"}, "folder"), ({"kind": "hl7v2_folder", "folder": "relative"}, "full path"), ({"kind": "folder_bridge", "folder": "/etc"}, "allowed folder root"),
                      ({"kind": "abdm_bundles", "folder": str(data_root / "his_inbox" / ".." / "cases")}, "'..'"), ({"kind": "hl7v2_folder", "folder": str(data_root / "cases")}, "allowed folder root"),
                      ({"kind": "hl7", "url": "http://x"}, "kind"), ({"kind": "fhir_generic", "url": BASE, "pacs_url": "http://10.0.0.7:8042", "token": "t"}, "PACS")):
        with pytest.raises(ValueError, match=word):
            his_client.validate_settings(bad)
        with pytest.raises(ValueError):
            his_client.save_settings(bad, by="root")
    assert not (data_root / "his.json").exists() and not (data_root / "his_secrets").exists()   # nothing is written by a refused save
    with pytest.raises(ValueError, match="kind must be one of"):
        registry.validate({"kind": "fhir"})
    # a Vaidyx admin may name another host; TB_HIS_ALLOW_HOSTS lets the root admin name a listed one (the token endpoint too)
    assert his_client.validate_settings({**ok, "url": "http://10.0.0.5:8080/fhir"}, allow_remote=True)["url"] == "http://10.0.0.5:8080/fhir"
    monkeypatch.setenv("TB_HIS_ALLOW_HOSTS", "fhir.hospital.example,login.hospital.example")
    v = his_client.validate_settings({"kind": "fhir_generic", "url": "https://fhir.hospital.example/r4/", "auth": "oauth2", "token_url": "https://login.hospital.example/token",
                                      "client_id": "vaidyx-tb", "client_secret": SECRET, "scope": "system/*.read", "identifier_systems": f"{SYSTEM}, urn:x:mrn\n{SYSTEM}"})
    assert v["url"] == "https://fhir.hospital.example/r4" and v["adapter"]["token_url"] == "https://login.hospital.example/token" and v["adapter"]["identifier_systems"] == [SYSTEM, "urn:x:mrn"]
    assert v["token"] == "" and v["token_file"] == "" and v["_secrets"] == {"client_secret": SECRET} and SECRET not in json.dumps(v["adapter"])


def test_secrets_go_to_owner_only_files_and_never_come_back(data_root):
    pub = his_client.save_settings({"kind": "fhir_generic", "preset": "bahmni_openmrs", "url": BASE, "username": "reader", "password": PASSWORD}, by="root")
    assert pub["kind"] == "fhir_generic" and pub["label"] == "Bahmni / OpenMRS (FHIR2 module)" and pub["has_token"] is False
    assert pub["adapter"] == {"preset": "bahmni_openmrs", "base_path": "/openmrs/ws/fhir2/R4", "identifier_systems": [], "auth": "basic", "username": "reader",
                              "secrets": {"password": "set"}}                                  # the preset's defaults filled in; the secret only as a word
    secret_file = data_root / "his_secrets" / "password"
    assert secret_file.read_text().strip() == PASSWORD and mode(secret_file) == 0o600 and mode(data_root / "his_secrets") == 0o700 and mode(data_root / "his.json") == 0o600
    saved = json.loads((data_root / "his.json").read_text())
    assert saved["adapter"]["password_file"] == str(secret_file) and PASSWORD not in stored(data_root) and PASSWORD not in json.dumps(pub)
    ev = json.loads((data_root / "org_audit.jsonl").read_text().splitlines()[-1])
    assert ev["kind"] == "his_settings_saved" and ev["his_kind"] == "fhir_generic" and ev["adapter"]["auth"] == "basic" and "password_file" not in json.dumps(ev)
    assert his_client.settings()["adapter"]["auth"] == "basic" and "password_file" not in json.dumps(his_client.public(his_client.settings()))
    assert his_client.public(his_client.settings(), manager=False)["adapter"] == {"preset": "bahmni_openmrs"}       # no account name for the others
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return Server(auth="basic")(request)
    c = his_client.client(transport=httpx.MockTransport(handler))
    assert asyncio.run(c.find_patient(UHID))["uhid"] == UHID and seen[0].startswith("Basic ")   # the saved password is the one sent
    # an edit that does not retype the password keeps it (same server, same sign-in); the words "set" / "not set" are never taken as a secret
    his_client.save_settings({"kind": "fhir_generic", "url": BASE, "auth": "basic", "username": "reader2", "password": "set", "base_path": PATH}, by="root")
    assert secret_file.read_text().strip() == PASSWORD and his_client.settings()["adapter"]["username"] == "reader2"
    with pytest.raises(ValueError, match="password"):                                         # a saved secret never follows a change of host
        his_client.save_settings({"kind": "fhir_generic", "url": "http://127.0.0.1:9999/fhir", "auth": "basic", "username": "reader"}, by="root")
    with pytest.raises(ValueError, match="token"):                                            # nor a change of sign-in
        his_client.save_settings({"kind": "fhir_generic", "url": BASE, "auth": "bearer"}, by="root")
    # another sign-in: the old secret file is removed, the new one written
    pub = his_client.save_settings({"kind": "fhir_generic", "url": BASE, "auth": "api_key", "api_key_header": "X-Hospital-Key", "api_key": KEY}, by="root")
    assert pub["adapter"]["secrets"] == {"api_key": "set"} and not secret_file.exists() and (data_root / "his_secrets" / "api_key").read_text().strip() == KEY
    pub = his_client.save_settings({"kind": "fhir_generic", "url": BASE, "base_path": PATH, "auth": "oauth2", "token_url": BASE + "/oauth/token", "client_id": "vaidyx-tb",
                                    "client_secret": SECRET}, by="root")
    assert pub["adapter"]["secrets"] == {"client_secret": "set"} and sorted(p.name for p in (data_root / "his_secrets").iterdir()) == ["client_secret"]
    s = Server(auth="oauth2")
    assert asyncio.run(his_client.client(transport=httpx.MockTransport(s)).encounters(PID)) and s.token_calls == 1
    pub = his_client.save_settings({"kind": "fhir_generic", "url": BASE, "auth": "bearer", "token": "static-token"}, by="root")
    assert pub["has_token"] is True and pub["adapter"]["secrets"] == {"token": "set"} and "token" not in pub and list((data_root / "his_secrets").iterdir()) == []
    for secret in (PASSWORD, KEY, SECRET, ACCESS):
        assert secret not in stored(data_root)
    assert "static-token" not in (data_root / "org_audit.jsonl").read_text()
    his_client.save_settings({"kind": "fhir", "url": "http://127.0.0.1:7130", "token": "t"}, by="root")   # back to the demo kind: no adapter block, as before
    assert "adapter" not in json.loads((data_root / "his.json").read_text()) and "adapter" not in his_client.settings() and type(his_client.client()) is his_client.FHIRClient


def test_folder_kinds_save_the_resolved_folder_and_hide_it_from_non_managers(data_root):
    inbox = data_root / "his_inbox" / "lab"
    inbox.mkdir(parents=True)
    (inbox / "a.hl7").write_text(oru(), newline="")
    pub = his_client.save_settings({"kind": "hl7v2_folder", "preset": "generic_hl7v2", "folder": str(inbox) + "/"}, by="root")
    assert pub["adapter"] == {"preset": "generic_hl7v2", "folder": str(inbox.resolve())} and pub["label"] == "LIS / RIS with HL7 v2 results" and pub["url"] == ""
    assert his_client.public(his_client.settings(), manager=False)["adapter"] == {"preset": "generic_hl7v2", "folder": True}   # no server path for the others
    c = his_client.client()
    assert type(c) is HL7v2FolderClient and asyncio.run(c.find_patient(UHID))["uhid"] == UHID
    (data_root / "his_inbox" / "out").symlink_to(data_root / "cases", target_is_directory=True)
    with pytest.raises(ValueError, match="allowed folder root"):
        his_client.save_settings({"kind": "folder_bridge", "folder": str(data_root / "his_inbox" / "out")}, by="root")
    assert his_client.settings()["kind"] == "hl7v2_folder"                                    # the refused save changed nothing


# ---- presets ------------------------------------------------------------------------------------------------------------------
def test_presets_are_honest():
    raw = json.loads((config.PROTOCOL_DIR / "his_presets.json").read_text())
    ps = registry.presets()
    ids = [p["id"] for p in ps]
    assert len(ids) == len(set(ids)) and {"vaidyx_demo", "abdm_nrces_fhir", "bahmni_openmrs", "hapi_fhir", "international_fhir", "nic_ehospital", "cdac_esushrut", "insta_hms",
                                          "karexpert", "mocdoc", "napier", "akhil_miracle", "generic_hl7v2", "generic_folder", "abdm_bundles"} <= set(ids)
    kinds = {k["kind"]: k for k in registry.describe()}
    for p in ps:
        assert set(p) >= {"id", "name", "vendor", "sector", "kind", "defaults", "status", "interface", "notes"}, p["id"]
        assert p["kind"] in registry.KINDS and p["kind"] in kinds and p["kind"] not in ("none", "mcp"), p["id"]
        assert p["sector"] in raw["sectors"] and p["status"] in raw["statuses"] and p["interface"] in raw["interfaces"], p["id"]
        assert (p["status"] == "tested with the demo hospital") == (p["id"] == "vaidyx_demo"), p["id"]   # only the demo claims a test
        assert "supported" not in (p["notes"] + p["status"]).lower() and chr(8212) not in json.dumps(p, ensure_ascii=False) and "aadhaar" not in json.dumps(p).lower()
        fields = {f["name"] for f in kinds[p["kind"]]["fields"]}
        assert set(p["defaults"]) <= fields, p["id"]                                           # a default names a real field of its method
        if p["defaults"].get("auth"):
            assert p["defaults"]["auth"] in fhir_generic.AUTHS
    by = {p["id"]: p for p in ps}
    assert by["bahmni_openmrs"]["defaults"] == {"base_path": "/openmrs/ws/fhir2/R4", "auth": "basic", "identifier_systems": []}
    for pid in ("nic_ehospital", "cdac_esushrut"):                                             # government SaaS: nothing claimed
        assert by[pid]["interface"] == "no public API found" and "No public API found; needs" in by[pid]["notes"] and by[pid]["kind"] in ("folder_bridge", "hl7v2_folder")
    for pid in ("nic_ehospital", "cdac_esushrut", "insta_hms", "karexpert", "mocdoc", "napier", "akhil_miracle"):
        assert by[pid]["kind"] in ("hl7v2_folder", "folder_bridge") and "ask the vendor for fhir r4 or hl7 v2 export" in by[pid]["notes"].lower(), pid
    assert by["napier"]["interface"] == "interface not known" and "signed JWT" in by["international_fhir"]["notes"]
    for k in registry.describe():
        assert set(k) >= {"kind", "label", "description", "fields", "cannot"} and chr(8212) not in json.dumps(k, ensure_ascii=False)
        for f in k["fields"]:
            assert set(f) >= {"name", "label", "type", "required", "help"} and f["type"] in ("text", "url", "secret", "folder", "select")
    assert any("signature" in x for x in kinds["hl7v2_folder"]["cannot"]) and any("open orders" in x for x in kinds["folder_bridge"]["cannot"])
    assert any("images" in x for x in kinds["fhir_generic"]["cannot"]) and any("signature" in x for x in kinds["fhir_generic"]["cannot"])


# ---- the API ------------------------------------------------------------------------------------------------------------------
def test_his_kinds_is_for_those_who_may_save_the_connection_and_holds_no_secret(api, data_root):
    for who in (RAO, DEEPAK, ANIL, AUDIT):
        assert api.as_(who).get("/his/kinds").status_code == 403
        assert api.as_(who).post("/setup/his", {"kind": "hl7v2_folder", "folder": str(data_root / "his_inbox")}).status_code == 403
    r = api.as_(ROOT).get("/his/kinds")
    assert r.status_code == 200, r.text
    v = r.json()
    assert [k["kind"] for k in v["kinds"]] == ["fhir", "fhir_generic", "hl7v2_folder", "folder_bridge", "abdm_bundles", "mcp", "none"]
    assert len(v["presets"]) >= 15 and v["current"]["kind"] == "fhir" and v["current"]["preset"] == "" and v["folder_roots"] == [str(data_root / "his_inbox")]
    assert v["remote_allowed"] is False and api.as_(VX).get("/his/kinds").json()["remote_allowed"] is True
    assert "token" not in v["current"]["settings"] and "synthetic-file-token" not in r.text


def test_setup_his_saves_the_new_kinds_tests_them_and_never_returns_a_secret(api, data_root, monkeypatch):
    inbox = data_root / "his_inbox" / "lab"
    inbox.mkdir(parents=True)
    (inbox / "a.hl7").write_text(oru(), newline="")
    api.as_(ROOT)
    assert api.post("/setup/his", {"preset": "no_such"}).status_code == 400
    assert api.post("/setup/his", {"kind": "telepathy", "folder": str(inbox)}).status_code == 400
    r = api.post("/setup/his", {"kind": "hl7v2_folder", "folder": "/etc"})
    assert r.status_code == 400 and "allowed folder root" in r.text and not (data_root / "his.json").exists()
    r = api.post("/setup/his", {"preset": "generic_hl7v2", "folder": str(inbox)})              # the preset alone names the method
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["step"] == "his" and out["test"]["ok"] is True and out["test"]["patients"] == 1 and out["test"]["reports"] == 1
    assert next(s for s in out["steps"] if s["id"] == "his")["done"] is True and his_client.settings()["kind"] == "hl7v2_folder"
    cur = api.get("/his/kinds").json()["current"]
    assert cur["kind"] == "hl7v2_folder" and cur["preset"] == "generic_hl7v2" and cur["settings"]["adapter"]["folder"] == str(inbox.resolve())
    # a plain FHIR server with a password: saved, tested, and the password is in no answer and no stored file but its own
    r = api.post("/setup/his", {"preset": "bahmni_openmrs", "url": BASE, "username": "reader", "password": PASSWORD})
    assert r.status_code == 200 and PASSWORD not in r.text and r.json()["test"]["ok"] is False   # nothing listens there in a unit test: the test says so, the save stays
    assert (data_root / "his_secrets" / "password").read_text().strip() == PASSWORD and mode(data_root / "his_secrets" / "password") == 0o600
    kinds = api.get("/his/kinds")
    assert PASSWORD not in kinds.text and "password_file" not in kinds.text and kinds.json()["current"]["settings"]["adapter"]["secrets"] == {"password": "set"}
    assert PASSWORD not in stored(data_root) and PASSWORD not in json.dumps(org.read_audit())
    r = api.post("/setup/his", {"kind": "fhir_generic", "url": "http://10.0.0.5:8080/fhir", "auth": "bearer", "token": "tok-" + "t" * 8})
    assert r.status_code == 400 and "Vaidyx admin" in r.text                                   # the host rule holds for the root admin
    r = api.post("/setup/his", {"kind": "fhir_generic", "url": BASE, "auth": "oauth2", "token_url": "http://10.0.0.9/token", "client_id": "c", "client_secret": SECRET})
    assert r.status_code == 400 and "token endpoint" in r.text and SECRET not in r.text
    # the old body still works exactly as before
    monkeypatch.setattr(his_client, "client", lambda *a, **k: None)
    r = api.post("/setup/his", {"url": "http://127.0.0.1:7130", "token": "synthetic-his-token"})
    assert r.status_code == 200 and "synthetic-his-token" not in r.text and his_client.settings()["kind"] == "fhir" and "adapter" not in his_client.settings()
    assert api.post("/setup/his", {}).status_code == 400
    r = api.post("/setup/his", {"preset": "vaidyx_demo", "token": "synthetic-his-token"})      # the demo preset fills the demo address
    assert r.status_code == 200 and his_client.settings()["url"] == "http://127.0.0.1:7130"
