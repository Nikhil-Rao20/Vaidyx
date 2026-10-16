"""MCP connectors: Vaidyx-TB as an MCP client of hospital systems (12 Oct).

A connector is an outside MCP server that holds records (a HIS, LIS or RIS, a document archive, or the synthetic demo HIS in
demo_data/demo_his_mcp.py). The Case File never reads from it directly: a connector only tells the coordinator which records
the system holds for the Case File's patient and hands over the files the coordinator picks. Those files enter the normal
intake pipeline (department upload: reading, classification, identity matching, verification), so every value still needs a
verified quote in a stored document. Nothing is ever written back to the hospital system.

Fail closed: a connector is usable only when every tool it offers is annotated read-only (readOnlyHint) and it offers the
records protocol (find_patient, list_records, fetch_record; see demo_his_mcp.py). Configuration lives in
<data root>/connectors.json, edited by admins, audited in org_audit.jsonl; tokens are never returned to the UI.
"""
import base64, hashlib, json, logging, re
from contextlib import asynccontextmanager
from pathlib import Path

from . import config, org, store

for _n in ("mcp.client.streamable_http", "mcp.client", "httpx"):  # the SDK logs every request at INFO; the app's log is for events
    logging.getLogger(_n).setLevel(logging.WARNING)

REQUIRED_TOOLS = ("find_patient", "list_records", "fetch_record")
_URL = re.compile(r"^https?://[^\s/]+(/\S*)?$")


def path() -> Path:
    return Path(config.DATA_ROOT) / "connectors.json"


def load() -> list:
    p = path()
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
    except Exception:
        return []
    return [c for c in (d.get("connectors") or []) if isinstance(c, dict)]


def validate(c: dict, existing: list = ()) -> dict:
    """A cleaned connector, or ValueError with a plain message."""
    cid = str(c.get("id") or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,40}", cid):
        raise ValueError("id: letters, digits, hyphens or underscores (2 to 41 characters)")
    label = str(c.get("label") or "").strip()
    if not label:
        raise ValueError("label is required")
    url = str(c.get("url") or "").strip()
    if not _URL.match(url):
        raise ValueError("url must start with http:// or https://")
    dept = str(c.get("department") or "").strip()
    if not org.department_id(dept):
        raise ValueError(f"department '{dept}' is not a hospital department (fetched records are uploaded as that department)")
    token = str(c.get("token") or "")
    if token == "" and c.get("keep_token"):
        token = next((x.get("token") or "" for x in existing if x.get("id") == cid), "")
    return {"id": cid, "label": label[:80], "url": url, "token": token, "department": org.department_id(dept), "enabled": bool(c.get("enabled", True)),
            "kind": "records", "note": str(c.get("note") or "")[:300]}


def save(connectors: list, by: str = "") -> list:
    existing = load()
    clean, seen = [], set()
    for c in connectors or []:
        v = validate(c, existing)
        if v["id"] in seen:
            raise ValueError(f"duplicate connector id {v['id']}")
        seen.add(v["id"]); clean.append(v)
    p = path(); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps({"connectors": clean}, indent=1)); tmp.replace(p)
    a = Path(config.DATA_ROOT) / "org_audit.jsonl"
    with open(a, "a") as f:
        f.write(json.dumps({"ts": store.now_iso(), "by": by, "kind": "connectors_saved", "ids": [c["id"] for c in clean]}, ensure_ascii=False) + "\n")
    return clean


def public(c: dict) -> dict:
    """A connector without its token (the UI only learns whether one is set)."""
    return {k: v for k, v in c.items() if k != "token"} | {"has_token": bool(c.get("token"))}


def get(cid: str) -> dict | None:
    return next((c for c in load() if c["id"] == cid), None)


# ---- MCP client ------------------------------------------------------------------------------------------------------
def http_client(c: dict, transport=None):
    """The HTTP client for a connector: bearer token in the header, 20 s to connect, 5 minutes to read a streamed answer."""
    import httpx
    headers = {"Authorization": f"Bearer {c.get('token') or ''}"} if c.get("token") else {}
    kw = {"transport": transport} if transport else {}
    return httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(20, read=300), follow_redirects=True, **kw)


@asynccontextmanager
async def session(c: dict, client=None):
    """An initialised MCP ClientSession on the connector's Streamable HTTP endpoint (bearer token in the header). `client`: a
    ready httpx.AsyncClient (tests pass one bound to an in-process app)."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with (client or http_client(c)) as hc:
        async with streamable_http_client(c["url"], http_client=hc) as (read, write, _):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s


def _structured(res) -> dict:
    """The tool result as a dict: structuredContent when the server declared an output schema, else the JSON text block."""
    if getattr(res, "isError", False):
        txt = " ".join(getattr(x, "text", "") for x in (res.content or []))
        raise RuntimeError(f"the connector refused the call: {txt[:300]}")
    sc = getattr(res, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    for x in res.content or []:
        if getattr(x, "type", "") == "text":
            try:
                return json.loads(x.text)
            except Exception:
                return {"text": x.text}
    return {}


async def probe(c: dict, client=None) -> dict:
    """Connect, list the tools, and say whether the connector is usable: every tool read-only, the records protocol present."""
    try:
        async with session(c, client) as s:
            tools = (await s.list_tools()).tools
            name = ""
            try:
                name = f"{s._server_info.name if getattr(s, '_server_info', None) else ''}".strip()
            except Exception:
                pass
    except Exception as e:
        return {"ok": False, "usable": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "tools": []}
    ts = [{"name": t.name, "read_only": bool(t.annotations and t.annotations.readOnlyHint), "description": (t.description or "")[:160]} for t in tools]
    names = {t["name"] for t in ts}
    not_ro = [t["name"] for t in ts if not t["read_only"]]
    missing = [t for t in REQUIRED_TOOLS if t not in names]
    usable = not not_ro and not missing
    reason = ("" if usable else ("tools without a read-only annotation: " + ", ".join(not_ro) if not_ro else "records protocol incomplete, missing: " + ", ".join(missing)))
    return {"ok": True, "usable": usable, "reason": reason, "server": name, "tools": ts}


def _patient_queries(case: dict) -> list:
    pat = case.get("patient") or {}
    out = [pat.get("mrn") or ""]
    out += [x.get("value") or "" for x in (pat.get("ids") or []) if isinstance(x, dict)]
    out.append(pat.get("name") or "")
    return [q for q in dict.fromkeys(x.strip() for x in out) if q]


async def available_records(case_id: str, c: dict, client=None) -> dict:
    """The records the connector holds for the Case File's patient, marked when a file of the same name is already in the Case File.
    The patient is looked up by the Case File's hospital numbers first, then its learned identifiers, then the name."""
    case = store.get_case(case_id)
    have = {(d.get("rel_path") or d.get("filename") or "").split("/")[-1].lower() for d in store.list_docs(case_id)}
    shas = {d.get("sha256") for d in store.list_docs(case_id)}
    async with session(c, client) as s:
        patient, matched_on = None, ""
        for q in _patient_queries(case):
            r = _structured(await s.call_tool("find_patient", {"query": q}))
            ps = r.get("patients") or []
            if len(ps) == 1:
                patient, matched_on = ps[0], q; break
            if len(ps) > 1:
                return {"connector": c["id"], "patient": None, "ambiguous": ps, "records": [], "note": f"more than one patient matches '{q}'; a person must choose"}
        if not patient:
            return {"connector": c["id"], "patient": None, "records": [], "note": "no patient in the hospital system matches this Case File's identifiers"}
        recs = _structured(await s.call_tool("list_records", {"patient_id": patient["patient_id"]})).get("records") or []
    out = []
    for r in recs:
        fn = (r.get("filename") or "").split("/")[-1].lower()
        out.append({**r, "in_case_file": fn in have})
    store.audit(case_id, {"kind": "connector_records_listed", "connector": c["id"], "matched_on": matched_on, "records": len(out), "new": sum(not x["in_case_file"] for x in out)})
    return {"connector": c["id"], "patient": patient, "matched_on": matched_on, "records": out, "known_shas": len([x for x in shas if x])}


async def fetch(case_id: str, c: dict, record_ids: list, user: str = "", client=None) -> dict:
    """Fetch the chosen records and hand them to the intake pipeline as an upload by the connector's department (patient matching
    files them into the Case File on an exact identifier; otherwise they wait in Needs matching). Returns the intake job and what
    was fetched. Nothing is written to the hospital system."""
    from . import service
    case = store.get_case(case_id)
    files, fetched, errors = [], [], []
    async with session(c, client) as s:
        patient = None
        for q in _patient_queries(case):
            ps = _structured(await s.call_tool("find_patient", {"query": q})).get("patients") or []
            if len(ps) == 1:
                patient = ps[0]; break
        if not patient:
            raise ValueError("no single patient in the hospital system matches this Case File")
        for rid in record_ids:
            try:
                r = _structured(await s.call_tool("fetch_record", {"patient_id": patient["patient_id"], "record_id": rid}))
                data = base64.b64decode(r["content_base64"])
                sha = hashlib.sha256(data).hexdigest()
                if r.get("sha256") and r["sha256"] != sha:
                    raise ValueError("checksum mismatch")
                rel = f"{c['id']}/{r.get('filename') or rid}"
                files.append((rel, data)); fetched.append({"record_id": rid, "filename": r.get("filename"), "sha256": sha, "size": len(data)})
            except Exception as e:
                errors.append({"record_id": rid, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    job = service.add_intake_files(files, c["department"], user=f"{user or 'coordinator'} via connector {c['id']}") if files else None
    store.audit(case_id, {"kind": "connector_fetch", "connector": c["id"], "by": user, "fetched": fetched, "errors": errors, "job": job["id"] if job else None})
    return {"job": job["id"] if job else None, "fetched": fetched, "errors": errors, "department": org.department_name(c["department"])}
