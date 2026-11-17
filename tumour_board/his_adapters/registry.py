"""The registry of hospital-system connection methods: KINDS, make(settings), validate(...), describe() for the set-up screen,
and the per-product presets (protocols/his_presets.json).

A hospital picks its system from the presets and gets the right method (kind) and defaults. "fhir", "mcp" and "none" behave
exactly as before (his_client keeps their code); the kinds added here:

    fhir_generic    his.json: url, token (bearer), adapter {base_path, identifier_systems, auth, username, api_key_header,
                    token_url, client_id, scope, password_file | api_key_file | client_secret_file}
    hl7v2_folder    his.json: adapter {folder}
    folder_bridge   his.json: adapter {folder}
    abdm_bundles    his.json: adapter {folder}

Secrets: the bearer token stays in his.json (owner-only, as for "fhir"); a password, API key or client secret is written to its
own owner-only file under <DATA_ROOT>/his_secrets and his.json keeps only the path. No secret is ever returned: public settings
say "set" or "not set". Every URL (the server and the OAuth2 token endpoint) follows the host rule of his_client (this server,
TB_HIS_ALLOW_HOSTS, or a Vaidyx admin); every folder must be inside an allowed root (TB_HIS_FOLDER_ROOTS).
"""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from .. import config, his_client
from . import _common as C
from . import fhir_generic

NEW_KINDS = ("fhir_generic", "hl7v2_folder", "folder_bridge", "abdm_bundles")
KINDS = tuple(his_client.KINDS) + NEW_KINDS
FOLDER_KINDS = ("hl7v2_folder", "folder_bridge", "abdm_bundles")
SECRETS = ("password", "api_key", "client_secret")          # each kept in <DATA_ROOT>/his_secrets/<name>
_SECRET_FOR = {"basic": "password", "api_key": "api_key", "oauth2": "client_secret"}
_HEADER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")
_BAD_HEADERS = {"host", "content-length", "content-type", "accept", "cookie", "connection", "transfer-encoding", "user-agent"}
_PLAIN = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
_HOST_RULE = "may point only at this server or at a host listed in TB_HIS_ALLOW_HOSTS; ask the Vaidyx admin for another host"


def is_adapter_kind(kind) -> bool:
    return kind in NEW_KINDS


# ---------------------------------------------------------------------------------------------------- what the UI shows
def _f(name, label, type_, required=False, help_="", **extra) -> dict:
    return {"name": name, "label": label, "type": type_, "required": required, "help": help_, **extra}


_LABEL = _f("label", "Name shown to doctors", "text", False, "For example the hospital's name for its system.")
_FOLDER_HELP = "A folder on this server, inside the allowed folder root. Vaidyx-TB only reads it."
_AUTH_OPTIONS = [{"value": "bearer", "label": "Bearer token"}, {"value": "basic", "label": "User name and password (HTTP basic)"},
                 {"value": "api_key", "label": "API key in a header"}, {"value": "oauth2", "label": "OAuth2 client credentials"},
                 {"value": "none", "label": "No sign-in"}]


def describe() -> list:
    """Per kind: a label, a one-line description, the fields it needs (name, label, type: text / url / secret / folder /
    select, required, help; `options` for a select, `when` for a field shown only with one sign-in type) and what it cannot do."""
    return [
        {"kind": "fhir", "label": "FHIR R4 in ABDM / NRCeS shapes", "tested": True,
         "description": "A hospital system that serves FHIR R4 in the Indian (NRCeS) profiles, as the demo hospital does.",
         "fields": [_f("url", "Server address", "url", True, "The hospital system's address, for example http://127.0.0.1:7130."),
                    _f("token", "Token", "secret", True, "The bearer token the hospital gave. It is never shown again."), _LABEL],
         "cannot": []},
        {"kind": "fhir_generic", "label": "Plain FHIR R4 server", "tested": False,
         "description": "Any FHIR R4 server that is not in NRCeS shapes: HAPI FHIR, Bahmni / OpenMRS (FHIR2), Epic or Oracle Cerner style.",
         "fields": [_f("url", "Server address", "url", True, "The server's address. Add the FHIR path here or in the next field."),
                    _f("base_path", "FHIR base path", "text", False, "Only if the FHIR API is under a path, for example /openmrs/ws/fhir2/R4."),
                    _f("identifier_systems", "Identifier systems for UHID / MRN", "text", False,
                       "One per line or comma separated. Used when the server needs system|value to find a patient."),
                    _f("auth", "Sign-in", "select", True, "How Vaidyx-TB signs in to the server.", options=_AUTH_OPTIONS),
                    _f("token", "Token", "secret", True, "The bearer token. It is never shown again.", when={"auth": ["bearer"]}),
                    _f("username", "User name", "text", True, "", when={"auth": ["basic"]}),
                    _f("password", "Password", "secret", True, "Kept in an owner-only file on this server.", when={"auth": ["basic"]}),
                    _f("api_key_header", "Header name", "text", False, "The header that carries the key (default X-API-Key).", when={"auth": ["api_key"]}),
                    _f("api_key", "API key", "secret", True, "Kept in an owner-only file on this server.", when={"auth": ["api_key"]}),
                    _f("token_url", "Token endpoint", "url", True, "Where the access token is asked for.", when={"auth": ["oauth2"]}),
                    _f("client_id", "Client id", "text", True, "", when={"auth": ["oauth2"]}),
                    _f("client_secret", "Client secret", "secret", True, "Kept in an owner-only file on this server.", when={"auth": ["oauth2"]}),
                    _f("scope", "Scope", "text", False, "Only if the hospital asks for one, for example system/*.read.", when={"auth": ["oauth2"]}),
                    _LABEL],
         "cannot": ["no signature check (the signature stays unknown and is never counted as signed)",
                    "no images (Bahmni / OpenMRS FHIR2 has no ImagingStudy)",
                    "a report with no file is read as text only (its conclusion and values, line by line)",
                    "no earlier versions of an amended report unless they were fetched before",
                    "no sign-in with a signed JWT (SMART backend services)"]},
        {"kind": "hl7v2_folder", "label": "HL7 v2 result messages in a folder", "tested": False,
         "description": "The hospital's lab, radiology or HIMS interface drops HL7 v2 result files (ORU^R01) into a folder on this server.",
         "fields": [_f("folder", "Folder", "folder", True, _FOLDER_HELP), _LABEL],
         "cannot": ["no signature check (HL7 v2 carries no signature that can be verified)", "no imaging links", "no referrals",
                    "no link between duplicate registrations", "open orders only if order messages (ORM^O01) are dropped too",
                    "no network listener (MLLP): files only"]},
        {"kind": "folder_bridge", "label": "Report folder with an index file", "tested": False,
         "description": "For a hospital with no API: report PDFs in a folder with an index.csv that lists them.",
         "fields": [_f("folder", "Folder", "folder", True, _FOLDER_HELP + " It holds index.csv and the report files."), _LABEL],
         "cannot": ["no open orders", "no signature check (the report text decides)", "no imaging links", "no referrals",
                    "no link between duplicate registrations", "no candidate values"]},
        {"kind": "abdm_bundles", "label": "ABDM record bundles in a folder", "tested": False,
         "description": "ABDM health-record documents (FHIR document bundles) that the hospital, as an ABDM provider, hands over as files.",
         "fields": [_f("folder", "Folder", "folder", True, _FOLDER_HELP + " One .json bundle per record."), _LABEL],
         "cannot": ["no open orders", "no signature check (the bundle's signature is not verified)", "no imaging links", "no referrals",
                    "no live ABDM gateway (consent requests)"]},
        {"kind": "mcp", "label": "MCP connector", "tested": True,
         "description": "A configured MCP connector that lists a patient's records and serves their files.",
         "fields": [_f("connector", "Connector", "text", True, "The id of a configured MCP connector."), _LABEL],
         "cannot": ["no visits", "no open orders", "no report status", "no signature check", "no imaging links", "no referrals"]},
        {"kind": "none", "label": "No hospital system", "tested": True,
         "description": "Case Files are made from uploaded files only.", "fields": [], "cannot": ["no lookup by UHID", "no re-fetch"]},
    ]


@lru_cache(maxsize=1)
def _presets() -> tuple:
    d = json.loads((config.PROTOCOL_DIR / "his_presets.json").read_text(encoding="utf-8"))
    return tuple(p for p in d.get("presets") or [] if isinstance(p, dict) and p.get("id"))


def presets() -> list:
    """The hospital systems a hospital can pick from (protocols/his_presets.json): id, name, vendor, sector, kind, defaults,
    status, notes. Data only: a preset never adds support the code does not have."""
    return [json.loads(json.dumps(p)) for p in _presets()]


def preset(pid: str):
    return next((p for p in presets() if p["id"] == pid), None)


# ---------------------------------------------------------------------------------------------------- secrets
def secrets_dir() -> Path:
    return Path(config.DATA_ROOT) / "his_secrets"


def _secret(adapter: dict, name: str) -> str:
    """The secret kept in <DATA_ROOT>/his_secrets/<name> ("" when not set). Only that folder is ever read."""
    f = str((adapter or {}).get(name + "_file") or "")
    if not f or Path(f).parent != secrets_dir() or Path(f).name != name:
        return ""
    try:
        return Path(f).read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def finalize(clean: dict) -> dict:
    """Before his.json is written: each new secret goes to its own owner-only file, his.json keeps the path, and the files of
    secrets no longer used are removed. For "fhir", "mcp" and "none" this only removes left-over secret files."""
    new = clean.pop("_secrets", None) or {}
    adapter = clean.get("adapter") if isinstance(clean.get("adapter"), dict) else {}
    d = secrets_dir()
    for name, value in new.items():
        if name not in SECRETS or not value:
            continue
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        tmp = d / f".{name}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(value) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(d / name)
        adapter[name + "_file"] = str(d / name)
    for name in SECRETS:
        if not adapter.get(name + "_file"):
            try:
                (d / name).unlink()
            except OSError:
                pass
    return clean


def public_adapter(d: dict, manager: bool = True) -> dict:
    """The adapter settings without any secret or secret path: `secrets` says "set" or "not set". Someone who may not manage
    the connection learns only which system was chosen and whether a folder is set (no server path, no account name)."""
    a = d.get("adapter") if isinstance(d.get("adapter"), dict) else {}
    if not manager:
        return {"preset": a.get("preset") or ""} | ({"folder": bool(a.get("folder"))} if "folder" in a else {})
    out = {k: v for k, v in a.items() if not k.endswith("_file")}
    if d.get("kind") == "fhir_generic":
        auth = a.get("auth") or "bearer"
        word = lambda ok: "set" if ok else "not set"
        out["secrets"] = {"token": word(bool(his_client.token(d)))} if auth == "bearer" else \
            {_SECRET_FOR[auth]: word(bool(_secret(a, _SECRET_FOR[auth])))} if auth in _SECRET_FOR else {}
    return out


def audit_fields(clean: dict) -> dict:
    """What the `his_settings_saved` audit line adds for the new kinds (never a secret or a secret's path)."""
    return {"adapter": public_adapter(clean)} if is_adapter_kind(clean.get("kind")) else {}


# ---------------------------------------------------------------------------------------------------- validation
def _text(v, what: str, required: bool = False) -> str:
    s = str(v or "").strip()
    if not s:
        if required:
            raise ValueError(f"give the {what}")
        return ""
    if not _PLAIN.match(s):
        raise ValueError(f"the {what} is too long or holds characters that are not allowed")
    return s


def _url(v, what: str, allow_remote: bool) -> str:
    url = str(v or "").strip().rstrip("/")
    if not his_client._URL.match(url) or "?" in url or "#" in url or "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        raise ValueError(f"the {what} must start with http:// or https:// and carry no query, no user name and no password")
    if not his_client._host_ok(url, allow_remote):
        raise ValueError(f"the {what} {_HOST_RULE}")
    return url


def _systems(v) -> list:
    items = v if isinstance(v, (list, tuple)) else re.split(r"[,\n]", str(v or ""))
    out = []
    for x in items:
        s = str(x or "").strip()
        if not s:
            continue
        if len(s) > 200 or "|" in s or re.search(r"[\s\x00-\x1f]", s):
            raise ValueError("an identifier system must be one address or name without spaces or '|'")
        if s not in out:
            out.append(s)
    if len(out) > 10:
        raise ValueError("at most 10 identifier systems")
    return out


def validate(d: dict, existing: dict | None = None, allow_remote: bool = False) -> dict:
    """Cleaned settings of a new kind, or ValueError with a plain message. Fields may come flat ({"kind", "url", "auth", ...})
    or under "adapter"; a `preset` id fills what is not given from the preset's defaults. A secret left empty keeps the saved
    one only while the kind and the server stay the same (a saved secret never follows a change of host). New secrets ride in
    "_secrets" until finalize() writes them to their files."""
    existing = existing or {}
    kind = str(d.get("kind") or "").strip().lower()
    if kind not in NEW_KINDS:
        raise ValueError("kind must be one of: " + ", ".join(KINDS))
    flat = {**(d["adapter"] if isinstance(d.get("adapter"), dict) else {}), **{k: v for k, v in d.items() if k != "adapter"}}
    pid = str(flat.get("preset") or "").strip()
    pre = preset(pid) if pid else None
    if pid and not pre:
        raise ValueError(f"'{pid[:40]}' is not a hospital system in the list")
    if pre and pre["kind"] != kind:
        raise ValueError(f"{pre['name']} connects by {pre['kind']}, not by {kind}")
    defaults = (pre or {}).get("defaults") or {}
    get = lambda k: flat.get(k) if flat.get(k) not in (None, "", []) else defaults.get(k)
    spec = next(k for k in describe() if k["kind"] == kind)
    label = str(flat.get("label") or "").strip()[:80] or ((pre or {}).get("name") or spec["label"])[:80]
    same_kind = existing.get("kind") == kind
    old = existing.get("adapter") if same_kind and isinstance(existing.get("adapter"), dict) else {}
    pacs_url = his_client.validate_settings({"kind": "none", "pacs_url": flat.get("pacs_url")}, existing, allow_remote=allow_remote)["pacs_url"]
    out = {"kind": kind, "label": label, "url": "", "token": "", "token_file": "", "connector": "", "enabled": bool(d.get("enabled", True)),
           "pacs_url": pacs_url, "adapter": {"preset": pid}, "_secrets": {}}
    a = out["adapter"]
    if kind in FOLDER_KINDS:
        a["folder"] = str(C.check_folder(get("folder")))
        return out
    url = _url(get("url"), "server address", allow_remote)
    base_path = str(get("base_path") or "").strip()
    if base_path:
        base_path = "/" + base_path.strip("/")
        if not re.fullmatch(r"(/[A-Za-z0-9._~-]+){1,12}", base_path) or ".." in base_path:
            raise ValueError("the FHIR base path must look like /openmrs/ws/fhir2/R4")
    auth = str(get("auth") or "bearer").strip().lower()
    if auth not in fhir_generic.AUTHS:
        raise ValueError("the sign-in must be one of: " + ", ".join(fhir_generic.AUTHS))
    same_host = same_kind and bool(existing.get("url")) and his_client._origin(url) == his_client._origin(existing.get("url"))
    out["url"] = url
    a.update(base_path=base_path, identifier_systems=_systems(get("identifier_systems")), auth=auth)
    if auth == "bearer":
        out["token"] = str(flat.get("token") or "").strip() or (str(existing.get("token") or "") if same_host else "")
        if not out["token"]:
            raise ValueError("a bearer sign-in needs a token (saved tokens never follow a change of host)")
    elif auth == "basic":
        a["username"] = _text(get("username"), "user name", True)
        if ":" in a["username"]:
            raise ValueError("the user name must not contain ':'")
    elif auth == "api_key":
        a["api_key_header"] = str(get("api_key_header") or "X-API-Key").strip()
        if not _HEADER.match(a["api_key_header"]) or a["api_key_header"].lower() in _BAD_HEADERS:
            raise ValueError("the header name for the API key is not valid (for example X-API-Key)")
    elif auth == "oauth2":
        a["token_url"] = _url(get("token_url"), "token endpoint", allow_remote)
        a["client_id"] = _text(get("client_id"), "client id", True)
        a["scope"] = _text(get("scope"), "scope")
        same_host = same_host and his_client._origin(a["token_url"]) == his_client._origin(old.get("token_url") or "")
    name = _SECRET_FOR.get(auth)
    if name:
        value = str(flat.get(name) or "").strip()
        if value in ("set", "not set"):
            value = ""                       # the words the settings screen was given back, not a secret
        if len(value) > 4000 or re.search(r"[\x00-\x1f]", value):
            raise ValueError(f"the {name.replace('_', ' ')} holds characters that are not allowed")
        kept = str(old.get(name + "_file") or "") if same_host and old.get("auth") == auth else ""
        if value:
            out["_secrets"][name] = value
        elif kept and _secret(old, name):
            a[name + "_file"] = kept
        else:
            raise ValueError(f"give the {name.replace('_', ' ')} (a saved one never follows a change of host or of sign-in)")
    return out


# ---------------------------------------------------------------------------------------------------- the client
def make(d: dict | None = None, transport=None):
    """The HIS client for these settings (None when disabled or kind none). his_client.client() delegates here for the new
    kinds; "fhir" and "mcp" are built exactly as his_client.client() builds them."""
    d = his_client.settings() if d is None else d
    kind = d.get("kind")
    if not d.get("enabled") or kind == "none":
        return None
    a = d.get("adapter") if isinstance(d.get("adapter"), dict) else {}
    label = d.get("label") or ""
    if kind == "fhir_generic":
        # settings tried before they are saved (his_client.trial_settings, POST /his/try) carry a newly typed secret in memory only
        typed = d.get("_secrets") if isinstance(d.get("_secrets"), dict) else {}
        sec = lambda name: str(typed.get(name) or "") or _secret(a, name)
        auth = {"type": a.get("auth") or "bearer", "token": his_client.token(d), "username": a.get("username") or "", "password": sec("password"),
                "header": a.get("api_key_header") or "X-API-Key", "key": sec("api_key"), "token_url": a.get("token_url") or "",
                "client_id": a.get("client_id") or "", "client_secret": sec("client_secret"), "scope": a.get("scope") or ""}
        return fhir_generic.GenericFHIRClient(d.get("url") or "", auth, label=label, base_path=a.get("base_path") or "",
                                              identifier_systems=a.get("identifier_systems") or [], transport=transport)
    if kind == "hl7v2_folder":
        from .hl7v2 import HL7v2FolderClient
        return HL7v2FolderClient(a.get("folder") or "", label=label)
    if kind == "folder_bridge":
        from .folder_bridge import FolderBridgeClient
        return FolderBridgeClient(a.get("folder") or "", label=label)
    if kind == "abdm_bundles":
        from .abdm_bundle import ABDMBundleClient
        return ABDMBundleClient(a.get("folder") or "", label=label)
    if kind == "mcp":
        from .. import connectors
        c = connectors.get(d.get("connector") or "")
        return his_client.MCPHISClient(c) if c else None
    return his_client.FHIRClient(d.get("url") or his_client.DEFAULT_URL, his_client.token(d), label=label, transport=transport)
