"""Vaidyx-TB as an MCP server: the Tumour Board Case File, read-only, for outside agents and assistants.

Any MCP client (another hospital assistant, a desktop agent, a test harness) can list Case Files, read documents, search,
look up verified values and gaps, read the stored summary and briefs, and search the guideline library. Every tool is
annotated read-only (readOnlyHint, no destructiveHint); nothing here writes to a Case File. The same scope rules apply as
in the app: the server returns what the records say, with quotes; it never interprets, stages or recommends. Every call
is audited (per Case File audit.jsonl, plus mcp_audit.jsonl) with the client name the connection declared.

Transports: stdio (for a local agent that starts this process) or Streamable HTTP on 127.0.0.1 (port 7110) protected by a
bearer token (data/tumour_board/mcp_token, created on first start; admins see and regenerate it in the app). A static token
on a loopback-bound server is a custom scheme the protocol allows; exposing the server beyond this machine needs the
OAuth 2.1 resource-server path of the specification. Built on the mcp 1.x SDK the app pins (protocol revision 2025-11-25).

Run:  /data/vaidyx/venv/app/bin/python -m tumour_board.mcp_server --transport http [--port 7110]
      /data/vaidyx/venv/app/bin/python -m tumour_board.mcp_server --transport stdio
"""
import argparse, json, os, secrets
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import agents, config, dates, guidelines, org, protocol, rules, search, skills, store

NAME, VERSION = "vaidyx-tb", "0.1"
DEFAULT_PORT = int(os.getenv("TB_MCP_PORT", "7110"))
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SCOPE = ("Vaidyx-TB: AI support for a cancer Tumour Board (India first). This server is READ-ONLY. It returns what the signed records of "
         "a Tumour Board Case File document, with verbatim quotes and document ids, the Pre-Authorization gaps the rules found, the "
         "stored AI drafts (summary, specialty briefs; every sentence carries a verified quote) and reference passages from the guideline "
         "library. It never interprets images, diagnoses, derives a stage or recommends treatment; guideline text is reference only, "
         "never advice for a patient. Synthetic demo Case Files are marked SYNTHETIC.")


def token_path() -> Path:
    return Path(config.DATA_ROOT) / "mcp_token"


def token(create: bool = True) -> str:
    """The bearer token of the HTTP transport (mode 600); created on first use."""
    p = token_path()
    if p.exists():
        return p.read_text().strip()
    if not create:
        return ""
    t = secrets.token_urlsafe(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(t + "\n"); os.chmod(p, 0o600)
    return t


def regenerate_token() -> str:
    p = token_path()
    if p.exists():
        p.unlink()
    return token()


def include_protected() -> bool:
    return os.getenv("TB_MCP_INCLUDE_PROTECTED", "").strip().lower() in ("1", "true", "yes", "on")


def _visible(case_id: str) -> bool:
    return include_protected() or case_id not in config.HIDDEN_CASES


def _audit(tool: str, args: dict, client: str = ""):
    ev = {"kind": "mcp_call", "tool": tool, "args": {k: (v if isinstance(v, (int, float, bool)) else str(v)[:200]) for k, v in args.items()}, "client": client}
    cid = args.get("case_id")
    if cid and store.get_case(cid):
        store.audit(cid, ev)
    p = Path(config.DATA_ROOT) / "mcp_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps({"ts": store.now_iso(), **ev}, ensure_ascii=False, default=str) + "\n")


def _case(case_id: str) -> dict:
    c = store.get_case(store.safe_id(case_id))
    if not c or not _visible(c["case_id"]):
        raise ValueError(f"No Case File {case_id}")
    return c


def _client_name(ctx) -> str:
    try:
        ci = ctx.session.client_params.clientInfo  # declared by the client at initialize
        return f"{ci.name} {ci.version or ''}".strip()
    except Exception:
        return ""


def _facts(case_id: str) -> list:
    st = store.get_state(case_id)
    facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    cat = protocol.facts()
    out = []
    for fid, f in facts.items():
        cur = f.get("current")
        if not cur or cur.get("verification") not in rules.VERIFIED or cur.get("state", "present") != "present":
            continue
        out.append({"field": fid, "label": cat.get(fid, {}).get("label", fid), "value": cur["value"], "quote": cur.get("quote") or "",
                    "doc_id": cur["doc_id"], "doc_title": cur.get("doc_title"), "date": cur.get("date"), "doc_final": bool(cur.get("doc_final")),
                    "verification": cur["verification"], **({"confirmed_by": cur["confirmed_by"]} if cur.get("confirmed_by") else {})})
    return sorted(out, key=lambda x: x["label"])


def _gate(case_id: str):
    c = store.get_case(case_id)
    if not c.get("protocol"):
        return None
    g = store.get_state(case_id).get("gate") or rules.evaluate(case_id)
    return {"passed": g.get("passed"), "readiness": g.get("readiness"), "satisfied": g.get("satisfied"), "total": g.get("total"),
            "protocol": g.get("protocol"), "protocol_version": g.get("protocol_version"), "setting": g.get("setting_label") or g.get("setting"),
            "hospital_level": g.get("hospital_level"), "evaluated": g.get("evaluated"),
            "requirements": [{"id": r["id"], "label": r["label"], "department": r["department"], "status": r["status"], "level": r.get("level"),
                              "tier": r.get("tier_label"), "problems": r.get("problems", [])} for r in g.get("requirements", [])],
            "blockers": g.get("blockers", [])}


def build(**kw) -> FastMCP:
    """A server instance with every tool and resource registered (tests build a stateless, JSON-response one)."""
    m = FastMCP(NAME, instructions=SCOPE, host="127.0.0.1", port=kw.pop("port", DEFAULT_PORT), **kw)
    for fn, desc in TOOLS:
        m.tool(annotations=RO, description=desc)(fn)
    m.resource("tb://scope", name="scope", description="The scope declaration of Vaidyx-TB", mime_type="text/plain")(scope_resource)
    m.resource("tb://cases/{case_id}/documents/{doc_id}", name="document", description="The stored text of one Case File document", mime_type="text/plain")(document_resource)
    return m



def scope() -> dict:
    return {"name": NAME, "version": VERSION, "scope": SCOPE, "models": {k: {"label": v.get("label"), "origin": v.get("origin"), "medical": v.get("medical")}
                                                                   for k, v in config.models().items()}}


def list_cases(ctx=None) -> dict:
    _audit("list_cases", {}, _client_name(ctx))
    out = []
    for c in store.list_cases():
        if not _visible(c["case_id"]):
            continue
        out.append({"case_id": c["case_id"], "patient": {k: (c.get("patient") or {}).get(k) for k in ("name", "mrn", "agesex")}, "protocol": c.get("protocol"),
                    "board_date": c.get("board_date"), "readiness": c.get("readiness"), "gate_passed": c.get("gate_passed"), "documents": c.get("documents"),
                    "open_actions": c.get("open_actions")})
    return {"cases": out, "count": len(out)}


def get_case(case_id: str, ctx=None) -> dict:
    c = _case(case_id); _audit("get_case", {"case_id": c["case_id"]}, _client_name(ctx))
    facts = _facts(c["case_id"])
    stage = next((f for f in facts if f["field"] in ("recorded_stage", "figo_stage") and f["doc_final"]), None)
    return {"case": {k: c.get(k) for k in ("case_id", "patient", "protocol", "setting", "hospital_level", "board_date", "created", "listing")},
            "gate": _gate(c["case_id"]), "verified_fields": facts,
            "stage_as_recorded": ({"value": stage["value"], "quote": stage["quote"], "doc_id": stage["doc_id"], "doc_title": stage["doc_title"], "date": stage["date"]} if stage else None),
            "note": "Values are verbatim from signed records with their quotes; the stage is copied as recorded, never computed."}


def list_documents(case_id: str, ctx=None) -> dict:
    c = _case(case_id); _audit("list_documents", {"case_id": c["case_id"]}, _client_name(ctx))
    out = []
    for d in rules.case_docs(c["case_id"]):
        cl = d.get("classification") or {}
        dd = dates.doc_dates(d)
        out.append({"doc_id": d["doc_id"], "title": cl.get("title") or d.get("filename"), "filename": d.get("rel_path") or d.get("filename"), "doc_type": cl.get("doc_type"),
                    "department": cl.get("department"), "event_date": dd.get("event"), "report_date": dd.get("report"), "status": cl.get("status"), "signed": cl.get("signed"),
                    "state": d.get("state"), "pages": len(d.get("pages") or []), "identity": d.get("identity"),
                    "read_by": sorted({p.get("method") for p in (d.get("pages") or []) if p.get("method")})})
    return {"case_id": c["case_id"], "documents": out}


def read_document(case_id: str, doc_id: str, pages: str = "", ctx=None) -> dict:
    c = _case(case_id); _audit("read_document", {"case_id": c["case_id"], "doc_id": doc_id, "pages": pages}, _client_name(ctx))
    text = agents._read_document(c["case_id"], f"{store.safe_id(doc_id)} {pages}".strip())
    return {"case_id": c["case_id"], "doc_id": doc_id, "text": text}


def search_case(case_id: str, query: str, k: int = 6, ctx=None) -> dict:
    c = _case(case_id); _audit("search_case", {"case_id": c["case_id"], "query": query}, _client_name(ctx))
    hits = search.index(c["case_id"]).search(query, max(1, min(int(k), 20)))
    return {"case_id": c["case_id"], "hits": [{"doc_id": h["doc_id"], "doc_title": h.get("doc_title"), "date": h.get("date"), "text": h["text"]} for h in hits]}


def find_values(case_id: str, term: str, ctx=None) -> dict:
    c = _case(case_id); _audit("find_values", {"case_id": c["case_id"], "term": term}, _client_name(ctx))
    r = search.find_values(c["case_id"], term, 40)
    return {"case_id": c["case_id"], "term": term, "lines": [{"doc_id": h["doc_id"], "doc_title": h.get("doc_title"), "date": h.get("date"), "status": h.get("status"), "text": h["text"]}
                                                           for h in r["hits"]]}


def get_gaps(case_id: str, ctx=None) -> dict:
    c = _case(case_id); _audit("get_gaps", {"case_id": c["case_id"]}, _client_name(ctx))
    g = _gate(c["case_id"])
    acts = [a for a in (store.get_state(c["case_id"]).get("actions") or []) if a.get("status") != "completed"]
    return {"case_id": c["case_id"], "listed": g is not None,
            "gaps": [r for r in (g or {}).get("requirements", []) if r["status"] not in ("satisfied", "not_applicable", "waived")],
            "open_requests": [{"id": a["id"], "label": a.get("label"), "what": a.get("what"), "department": a.get("department"), "due": a.get("due"),
                               "status": a.get("status"), "source": a.get("source")} for a in acts]}


def _artefact_view(a: dict) -> dict:
    keys = ("status", "generated", "model", "seconds", "review", "stale", "structure", "sections", "paragraphs", "points_for_review", "not_documented",
            "stage_as_recorded", "dropped_unverified", "guardrail_removed", "removed", "label", "role", "no_documents", "message", "skill")
    return {k: a[k] for k in keys if k in a}


def get_summary(case_id: str, ctx=None) -> dict:
    c = _case(case_id); _audit("get_summary", {"case_id": c["case_id"]}, _client_name(ctx))
    a = (store.get_state(c["case_id"]).get("artefacts") or {}).get("summary")
    return {"case_id": c["case_id"], "summary": _artefact_view(a) if a else None,
            "note": "An AI draft until an expert marks it reviewed; see review.status. Sentences without a verified quote were removed."}


def get_brief(case_id: str, role: str, ctx=None) -> dict:
    c = _case(case_id)
    if role not in agents.ROLES:
        raise ValueError(f"unknown role {role}; one of {', '.join(agents.ROLES)}")
    _audit("get_brief", {"case_id": c["case_id"], "role": role}, _client_name(ctx))
    a = (store.get_state(c["case_id"]).get("artefacts") or {}).get(f"brief_{role}")
    return {"case_id": c["case_id"], "role": role, "brief": _artefact_view(a) if a else None, "note": "An AI draft until an expert marks it reviewed."}


def list_requests(case_id: str = "", ctx=None) -> dict:
    _audit("list_requests", {"case_id": case_id}, _client_name(ctx))
    cases = [_case(case_id)] if case_id else [c for c in store.list_cases() if _visible(c["case_id"])]
    out = []
    for c in cases:
        for a in store.get_state(c["case_id"]).get("actions") or []:
            if a.get("status") != "completed":
                out.append({"case_id": c["case_id"], "patient": (c.get("patient") or {}).get("name"), "id": a["id"], "label": a.get("label"), "what": a.get("what"),
                            "department": a.get("department"), "due": a.get("due"), "status": a.get("status"), "source": a.get("source")})
    return {"requests": sorted(out, key=lambda x: (x.get("due") or "", x["case_id"])), "count": len(out)}


def search_guidelines(query: str, cancer: str = "", ctx=None) -> dict:
    _audit("search_guidelines", {"query": query, "cancer": cancer}, _client_name(ctx))
    if not guidelines.ready():
        guidelines.index()
    r = guidelines.search_grouped(query, cancer or None)
    view = lambda h: {"org": h["org"], "region": h["region"], "title": h["title"], "file": h["file"], "page": h["page"], "text": h["text"]}
    return {"query": query, "india": [view(h) for h in r["india"]], "international": [view(h) for h in r["international"]],
            "note": "Passages are reference text for the board; the system never applies them to a patient."}


def list_skills(ctx=None) -> dict:
    _audit("list_skills", {}, _client_name(ctx))
    return {"skills": [{"role": s["role"], **(s["active"] or {})} for s in skills.describe()]}


def scope_resource() -> str:
    return SCOPE


def document_resource(case_id: str, doc_id: str) -> str:
    c = _case(case_id); _audit("resource", {"case_id": c["case_id"], "doc_id": doc_id})
    d = store.get_doc(c["case_id"], store.safe_id(doc_id))
    if not d:
        raise ValueError("No such document")
    return "\n\n".join(f"[page {i + 1}]\n{p.get('text') or ''}" for i, p in enumerate(d.get("pages") or []))


TOOLS = [
    (scope, "What this server is and is not: the scope declaration of Vaidyx-TB."),
    (list_cases, "List the Tumour Board Case Files: id, patient (name, hospital number), cancer protocol, readiness of the Pre-Authorization check, document count, board date."),
    (get_case, "One Case File: identity, listing, the Pre-Authorization check per required record, the verified primary fields (each with its quote and source document) and the stage exactly as recorded, never derived."),
    (list_documents, "The documents of a Case File: id, title, type, event and report dates, status (FINAL, DRAFT, UNSTATED ...), signed, pages, how it was read (text layer or scan)."),
    (read_document, "The text of one document (its stored pages), optionally a page range such as 'pages 2-4'. Up to 12,000 characters per call; the result says which pages are not shown."),
    (search_case, "Search the Case File (keyword and meaning): the most relevant passages with document id, title and date."),
    (find_values, "Every line in the Case File that mentions a term (oncology synonyms included: PD-L1 = TPS = 22C3), newest first, with document, date and status."),
    (get_gaps, "The open Pre-Authorization gaps of a Case File (record missing, not final, value missing or pending) with the Responsible Department, and the open requests routed to departments."),
    (get_summary, "The stored Case File summary (NCG Virtual Tumour Board structure; every sentence with verified quotes) and its expert-review status. Empty when none was compiled."),
    (get_brief, "The stored specialty support brief of one role (radiology, pathology, medical_oncology, surgical_oncology, radiation_oncology, nuclear_medicine): sections, points for review with guideline references, items not documented, review status."),
    (list_requests, "Open requests to departments across all Case Files (or one): Pre-Authorization gaps and Tumour Board actions with due dates."),
    (search_guidelines, "Reference passages from the guideline library (NCG, ICMR, PM-JAY, ICRI/IRIA first, then ESMO, CAP, ACR ...), optionally for one cancer: lung_nsclc, breast, colorectal_rectum, oral_cavity, cervix. Reference text only, never advice for a patient."),
    (list_skills, "The specialty support agents and their skills (what each one looks for), with the hospital's edits."),
]

mcp = build()


def http_app(m: FastMCP = None, expected: str = None):
    """The Streamable HTTP app with a bearer-token check in front (every request, header only)."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    inner = (m or mcp).streamable_http_app()
    expected = expected if expected is not None else token()

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            h = request.headers.get("authorization", "")
            if not h.startswith("Bearer ") or not secrets.compare_digest(h[7:].strip(), expected):
                return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await call_next(request)
    inner.add_middleware(Bearer)
    return inner


def client_config(port: int = DEFAULT_PORT) -> dict:
    """What a client needs: URL, header, and a stdio command (for agents that start the server themselves)."""
    return {"url": f"http://127.0.0.1:{port}/mcp", "header": "Authorization: Bearer <token>", "token_file": str(token_path()),
            "stdio_command": ["/data/vaidyx/venv/app/bin/python", "-m", "tumour_board.mcp_server", "--transport", "stdio"],
            "protocol": "MCP 2025-11-25 (mcp 1.x SDK); Streamable HTTP with sessions", "read_only": True}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vaidyx-TB read-only MCP server")
    ap.add_argument("--transport", choices=["stdio", "http"], default="http")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a = ap.parse_args(argv)
    if a.transport == "stdio":
        mcp.run(transport="stdio")
        return
    import uvicorn
    print(f"Vaidyx-TB MCP server (read-only) on http://127.0.0.1:{a.port}/mcp; token in {token_path()}", flush=True)
    uvicorn.run(http_app(), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
