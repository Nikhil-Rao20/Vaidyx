"""HTTP API for Vaidyx-TB (AI agent for the Tumour Board). All routes require a logged-in Vaidyx user; actions that change a Case File
are checked against the hospital's departments and roles in org.json through org.can() (V1 item 2.1)."""
import asyncio, json, logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.auth_helpers import require_user
from tumour_board import agents, config, guidelines, llm, notify, org, postboard, protocol, qa, rules, search, service, store, summary
from tumour_board import confirm  # clinician confirmations (V1 item 2.2)
from tumour_board import intake  # department uploads and patient matching (V1 items 2.3, 2.4)
from tumour_board import board  # board sessions, attendance, agent log (V1 items 6.1 to 6.3)
from tumour_board import followup  # Tumour Board actions in department inboxes, closing suggestions (V1 item 7.4)
from tumour_board import scanned  # values and citations read from scans (V1 items 8.1, 8.2)
from tumour_board import skills  # agent role definitions as editable SKILL.md files (12 Oct)
from tumour_board import connectors, mcp_server  # MCP: hospital-system connectors (client) and the read-only server (12 Oct)
from tumour_board import discord  # discordances between reports, decision watch (12 Oct)
from tumour_board import fhir_export  # FHIR R4 document bundle and the HBCR registry abstract (12 Oct)
from tumour_board import metrics  # agenda readiness, chase list, quality dashboard (12 Oct)

log = logging.getLogger("tumour_board")


from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse


class _ModelErrorRoute(APIRoute):
    """Model-server problems become a clear 502 for the UI instead of a 500 stack trace."""
    def get_route_handler(self):
        h = super().get_route_handler()

        async def handler(request):
            try:
                return await h(request)
            except llm.LLMError as e:
                return JSONResponse({"detail": f"Model error: {e}"}, status_code=502)
        return handler


def _user(request):
    return require_user(request) or "local"


def _roles(request):
    """Who is asking: the Vaidyx login plus the Tumour Board roles from org.json (V1 item 2.1). Vaidyx admins are TB admins."""
    u = require_user(request)
    mgr = getattr(request.app.state, "auth_manager", None)
    admin = bool(u and mgr is not None and callable(getattr(mgr, "is_admin", None)) and mgr.is_admin(u))
    return org.roles(u or "", vaidyx_admin=admin)


def _need(r, action, department=None):
    """One permission check on every route that changes something: a forbidden action is a 403 with a plain message."""
    try:
        org.require(r, action, department)
    except PermissionError as e:
        raise HTTPException(403, str(e))


def _need_known(r):
    """Model calls and re-checks are for users the hospital set-up knows (a department member, head, coordinator or admin)."""
    if not (r.get("admin") or r.get("known")):
        raise HTTPException(403, "Your account is not placed in any department yet. Ask a Tumour Board admin.")


def _doc_department(d):
    return (d or {}).get("department")  # department id recorded at upload (department uploads, V1 item 2.3); None for coordinator uploads


def _case_permissions(r, c, st, docs):
    """What this user may do on this Case File, so the UI can hide forbidden actions (the routes still enforce them)."""
    prot = protocol.get(c["protocol"]) if c.get("protocol") else {"mandatory": []}
    return {"upload": org.can(r, "upload_to_case"), "reprocess": org.can(r, "upload_to_case"), "delete_case": org.can(r, "delete_case"),
            "board_record": org.can(r, "board_record"), "review": org.can(r, "review"), "list_case": org.can(r, "list_case"),
            "waive": {q["id"]: org.can(r, "waive", q.get("department") or None) for q in prot.get("mandatory", [])},
            "confirm": {d["doc_id"]: org.can(r, "confirm", _doc_department(d)) for d in docs},
            "delete_document": {d["doc_id"]: org.can(r, "delete_document", _doc_department(d)) for d in docs},
            "unfile": {d["doc_id"]: bool(d.get("intake")) and org.can(r, "match") for d in docs},
            "update_action": {a["id"]: org.can(r, "update_action", a.get("department") or None) for a in st.get("actions", [])},
            "undo_confirmation": {x["id"]: _can_confirm(r, c, st, x["type"], x["key"]) for x in st.get("confirmations", []) if not x.get("undone")}}


def _can_confirm(r, c, st, ctype, key):
    """May this user record / undo a confirmation of this type on this key (same rule as the route, as a boolean)."""
    spec = confirm.TYPES.get(ctype)
    if not spec:
        return False
    if ctype == "waive":
        dept = next((q.get("department") for q in protocol.get(c["protocol"]).get("mandatory", []) if q["id"] == key), "") if c.get("protocol") else ""
        return org.can(r, "waive", dept or None)
    if spec["target"] in ("document", "fact"):
        doc_id = key.partition(":")[0] if spec["target"] == "fact" else key
        d = store.get_doc(c["case_id"], doc_id) if doc_id else None
        if ctype == "confirm_match":
            return org.can(r, "match")
        return org.can(r, spec["action"], _doc_department(d))
    if ctype == "resolve_flag":
        return org.can(r, "board_record")
    return org.can(r, spec["action"])


def _case(case_id):
    try:
        c = store.get_case(case_id)
    except ValueError:
        raise HTTPException(404, "Case not found")
    if not c:
        raise HTTPException(404, "Case not found")
    return c


def _history(h):
    """Earlier turns sent with a question: a list of {"role": user | assistant, "content": text}; anything else is ignored."""
    return [x for x in h if isinstance(x, dict) and x.get("role") in ("user", "assistant") and isinstance(x.get("content"), str)][-4:] if isinstance(h, list) else None


def _warm():
    import logging, threading
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    threading.Thread(target=lambda: guidelines.index(), daemon=True, name="tb-guideline-warmup").start()


def setup_tumour_board_routes():
    _warm()
    r = APIRouter(prefix="/api/tb", tags=["tumour-board"], route_class=_ModelErrorRoute)

    @r.get("/health")
    async def health(request: Request):
        _user(request)
        return {"models": await llm.health()}

    @r.get("/protocols")
    async def protocols(request: Request):
        _user(request)
        return {"protocols": protocol.list_protocols(), "facts": protocol.facts()}

    @r.get("/protocols/{pid}")
    async def protocol_detail(pid: str, request: Request):
        _user(request)
        return protocol.get(store.safe_id(pid))

    @r.get("/roles")
    async def roles(request: Request):
        _user(request)
        return {k: {"label": v["label"], "department": v["department"], "focus": v["focus"], "skill_origin": v.get("skill_origin", "code")}
                for k, v in ((k, agents.spec(k)) for k in agents.ROLES)}

    # ---- agent skills: the role definitions as SKILL.md files; read by any account placed in a department, edited by admins ----
    @r.get("/skills")
    async def list_skills(request: Request):
        rl = _roles(request); _need_known(rl)
        return {"skills": skills.describe(), "can_edit": org.can(rl, "manage_org"), "hospital_dir": str(skills.hospital_dir()),
                "note": "A skill says who an agent is and what it looks for. The tools, the hard rules (every sentence needs a verified quote; "
                        "no diagnosis, staging, treatment or image interpretation) and the output checks are in code and apply to every skill."}

    @r.post("/skills/validate")
    async def validate_skill(request: Request):
        rl = _roles(request); _need_known(rl); b = await request.json()
        try:
            s = skills.parse(str(b.get("text") or ""))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "skill": {k: s[k] for k in ("name", "label", "department", "doc_types", "guideline_query", "focus", "version", "sha")},
                "guidance": [h for h, _ in s["guidance"]]}

    @r.put("/skills/{role}")
    async def put_skill(role: str, request: Request):
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        try:
            s = skills.save(store.safe_id(role), str(b.get("text") or ""), by=rl["user"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "skill": {k: s[k] for k in ("name", "label", "department", "doc_types", "focus", "version", "sha", "origin")}}

    # ---- MCP connectors (hospital systems) and the read-only MCP server (12 Oct) ------------------------------------------
    @r.get("/connectors")
    async def list_connectors(request: Request):
        rl = _roles(request); _need_known(rl)
        cs = [connectors.public(c) for c in connectors.load()]
        if not org.can(rl, "manage_org"):
            cs = [{k: c[k] for k in ("id", "label", "department", "enabled", "kind")} for c in cs if c.get("enabled")]
        return {"connectors": cs, "can_manage": org.can(rl, "manage_org"), "can_fetch": org.can(rl, "list_case"),
                "protocol": {"tools": list(connectors.REQUIRED_TOOLS), "note": "Every tool must be annotated read-only; fetched files enter the intake pipeline as the connector's department; nothing is written back."}}

    @r.put("/connectors")
    async def put_connectors(request: Request):
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        try:
            saved = connectors.save(b.get("connectors") or [], by=rl["user"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "connectors": [connectors.public(c) for c in saved]}

    @r.post("/connectors/{cid}/probe")
    async def probe_connector(cid: str, request: Request):
        rl = _roles(request); _need_known(rl)
        c = connectors.get(store.safe_id(cid))
        if not c:
            raise HTTPException(404, "No such connector")
        return await connectors.probe(c)

    @r.get("/cases/{case_id}/connectors/{cid}/records")
    async def connector_records(case_id: str, cid: str, request: Request):
        rl = _roles(request); _case(case_id)
        c = connectors.get(store.safe_id(cid))
        if not c or not c.get("enabled"):
            raise HTTPException(404, "No such connector")
        if not (org.can(rl, "list_case") or org.can(rl, "upload", c["department"])):
            raise HTTPException(403, "Only a coordinator, or a member of the connector's department, can look up records")
        pr = await connectors.probe(c)
        if not pr.get("usable"):
            raise HTTPException(409, f"Connector not usable: {pr.get('reason') or pr.get('error')}")
        try:
            return await connectors.available_records(case_id, c)
        except Exception as e:
            raise HTTPException(502, f"The hospital system did not answer: {type(e).__name__}: {str(e)[:160]}")

    @r.post("/cases/{case_id}/connectors/{cid}/fetch")
    async def connector_fetch(case_id: str, cid: str, request: Request):
        rl = _roles(request); _case(case_id); b = await request.json()
        c = connectors.get(store.safe_id(cid))
        if not c or not c.get("enabled"):
            raise HTTPException(404, "No such connector")
        if not (org.can(rl, "list_case") or org.can(rl, "upload", c["department"])):
            raise HTTPException(403, "Only a coordinator, or a member of the connector's department, can fetch records")
        ids = [str(x) for x in (b.get("record_ids") or []) if str(x).strip()][:50]
        if not ids:
            raise HTTPException(400, "Choose at least one record")
        pr = await connectors.probe(c)
        if not pr.get("usable"):
            raise HTTPException(409, f"Connector not usable: {pr.get('reason') or pr.get('error')}")
        try:
            return await connectors.fetch(case_id, c, ids, user=rl["user"])
        except ValueError as e:
            raise HTTPException(409, str(e))
        except Exception as e:
            raise HTTPException(502, f"The hospital system did not answer: {type(e).__name__}: {str(e)[:160]}")

    @r.get("/metrics/agenda")
    async def metrics_agenda(request: Request, date: str = ""):
        """Readiness of the Case Files listed for a board date and the chase list per department (12 Oct)."""
        rl = _roles(request); _need_known(rl)
        from tumour_board.docstatus import parse_date
        iso = parse_date(date) if date else ""
        if date and not iso:
            raise HTTPException(400, f"Not a valid date: {date}")
        return metrics.agenda(iso or store.now_iso()[:10])

    @r.get("/metrics/dashboard")
    async def metrics_dashboard(request: Request, start: str = "", end: str = "", format: str = "json"):
        """The hospital's Tumour Board quality dashboard: before, during and after the board, with reference lines (12 Oct)."""
        rl = _roles(request); _need(rl, "list_case")
        d = metrics.dashboard(start or None, end or None)
        if format == "csv":
            from fastapi.responses import Response
            return Response(metrics.csv_text(d), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="tumour_board_quality.csv"'})
        return d

    @r.get("/mcp-server")
    async def mcp_server_info(request: Request):
        """How to connect an outside agent to this Case File store (read-only); the token only for admins."""
        rl = _roles(request); _need_known(rl)
        cfg = mcp_server.client_config()
        import socket
        running = False
        try:
            with socket.create_connection(("127.0.0.1", mcp_server.DEFAULT_PORT), timeout=0.3):
                running = True
        except OSError:
            pass
        out = {**cfg, "running": running, "tools": [t.name for t in mcp_server.mcp._tool_manager.list_tools()], "scope": mcp_server.SCOPE,
               "include_protected": mcp_server.include_protected(), "start": "tumour_board/serve_mcp.sh server"}
        if org.can(rl, "manage_org"):
            out["token"] = mcp_server.token()
        return out

    @r.post("/mcp-server/regenerate-token")
    async def mcp_regenerate(request: Request):
        rl = _roles(request); _need(rl, "manage_org")
        t = mcp_server.regenerate_token()
        skills._audit({"kind": "mcp_token_regenerated", "by": rl["user"]})
        return {"ok": True, "token": t, "note": "Restart the MCP server (tumour_board/serve_mcp.sh stop; serve_mcp.sh server) so it reads the new token"}

    @r.post("/skills/{role}/reset")
    async def reset_skill(role: str, request: Request):
        rl = _roles(request); _need(rl, "manage_org")
        try:
            removed = skills.reset(store.safe_id(role), by=rl["user"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "removed": removed}

    @r.get("/org")
    async def get_org(request: Request):
        """The hospital, its departments and the caller's own roles. The user map and the Vaidyx account list are returned to admins only."""
        rl = _roles(request)
        o = org.load()
        out = {"hospital": o["hospital"], "departments": o["departments"], "me": rl, "my_departments": org.my_departments(rl),
               "inbox_departments": org.visible_departments_for_inbox(rl)}  # whose department inbox this user may open (V1 item 4.4)
        if rl["admin"]:
            mgr = getattr(request.app.state, "auth_manager", None)
            out["users"], out["admins"] = o["users"], o["admins"]
            try:
                out["vaidyx_users"] = [{"username": x["username"], "is_admin": bool(x.get("is_admin"))} for x in mgr.list_users()] if mgr else []
            except Exception:
                out["vaidyx_users"] = []
        return out

    @r.put("/org")
    async def put_org(request: Request):
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        try:
            o = org.save(b, by=rl["user"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "hospital": o["hospital"], "departments": o["departments"], "users": o["users"], "admins": o["admins"]}

    @r.get("/cases")
    async def cases(request: Request):
        _user(request)
        return {"cases": store.list_cases(), "demo": service.list_demo()}

    @r.post("/cases")
    async def create(request: Request):
        u = _user(request); _need(_roles(request), "create_case"); b = await request.json()
        prot = b.get("protocol") or ""
        if prot and not protocol.exists(prot):
            raise HTTPException(400, f"Unknown protocol: {prot}")
        if b.get("setting") and (not prot or b["setting"] not in {x["id"] for x in protocol.settings(prot)}):
            raise HTTPException(400, f"Unknown NCG setting: {b['setting']}")
        level = b.get("hospital_level") or ((org.load().get("hospital") or {}).get("level") if prot else "")
        if level and level not in org.LEVELS:
            raise HTTPException(400, "Hospital level must be essential or optimal")
        try:
            c = store.create_case(store.safe_id(b["case_id"]), b.get("patient", {}), prot, b.get("board_date", ""), u, b.get("setting", ""), level or "")
        except FileExistsError:
            raise HTTPException(409, "Case already exists")
        store.audit(c["case_id"], {"kind": "case_created", "by": u, "listing": c["listing"]["status"], "protocol": prot, "setting": c.get("setting")})
        return c

    @r.post("/cases/{case_id}/listing")
    async def list_case(case_id: str, request: Request):
        """The coordinator lists the Case File for the board (V1 item 2.5): {"protocol", "setting", "board_date", "hospital_level"}.
        Pre-Authorization starts when listed (fields extracted from the stored pages, gate evaluated)."""
        u = _user(request); _need(_roles(request), "list_case"); _case(case_id); b = await request.json()
        try:
            job = service.list_case(case_id, str(b.get("protocol", "")), str(b.get("setting", "") or ""), str(b.get("board_date", "") or ""), str(b.get("hospital_level", "") or ""), u)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"job": job["id"], "total": job["total"], "case": store.get_case(case_id)}

    @r.delete("/cases/{case_id}")
    async def delete(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "delete_case"); _case(case_id)
        n = notify.purge_case(case_id)  # its notifications carry the patient's name: they go with the Case File (V1 item 4.4)
        store.audit(case_id, {"kind": "case_deleted", "by": u, "notifications_removed": n}); store.delete_case(case_id)
        log.info("case %s deleted by %s; %d notification(s) removed", case_id, u, n)
        return {"ok": True, "notifications_removed": n}

    @r.post("/demo/{case_id}")
    async def demo(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "create_case")
        job = service.import_demo(store.safe_id(case_id), u)
        return {"job": job["id"], "total": job["total"]}

    @r.post("/cases/{case_id}/demo-arrivals")
    async def arrivals(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "upload_to_case"); _case(case_id)
        job = service.demo_arrivals(case_id, u)
        if not job:
            raise HTTPException(404, "No demo arrivals for this case")
        return {"job": job["id"], "total": job["total"]}

    @r.get("/cases/{case_id}")
    async def get_case(case_id: str, request: Request):
        rl = _roles(request); c = _case(case_id)
        st = store.get_state(case_id)
        all_docs = store.list_docs(case_id)
        docs = []
        for d in rules.case_docs(case_id, st):  # as the clinicians confirmed them (type, dates, values; V1 items 2.2, 3.1, 3.2)
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "state", "error", "dismissed", "classification", "identity", "identity_read", "added", "department", "uploaded_by")} |
                        {"facts": d.get("facts", {}), "pages": len(d.get("pages") or []), "methods": sorted({p["method"] for p in d.get("pages") or []}),
                         "scan_pages": scanned.scan_pages(d.get("pages")),  # pages read from an image: "from scan (OCR)" (V1 item 8.1)
                         "page_flags": sorted({f for p in d.get("pages") or [] for f in p.get("flags") or []})})  # Hindi / regional text, illegible parts (V1 item 3.6)
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))  # confirmations overlaid (V1 item 2.2)
        cat = protocol.facts()
        sig = rules.case_signature(case_id, st)  # what a summary or brief would be generated from now (V1 item 4.5)
        stale = {name: (rules.stale_reason(a["signature"], sig) if a.get("signature") else
                        "Compiled before the Case File signature was kept, so changes since then cannot be checked")  # pre-4.5 artefacts (review)
                 for name, a in (st.get("artefacts") or {}).items() if isinstance(a, dict) and (name == "summary" or name.startswith("brief_"))}
        return {"case": c, "state": st, "documents": docs, "facts": {k: {"label": cat.get(k, {}).get("label", k), **v} for k, v in facts.items()},
                "timeline": postboard.timeline(case_id), "permissions": _case_permissions(rl, c, st, all_docs), "signature": sig, "stale": stale,
                "discordances": discord.summary(case_id, st), "outcomes": postboard.OUTCOMES}

    @r.post("/cases/{case_id}/documents")
    async def upload(case_id: str, request: Request, files: list[UploadFile] = File(...), paths: str = Form("[]")):
        u = _user(request); _need(_roles(request), "upload_to_case"); _case(case_id)
        rels = json.loads(paths or "[]")
        data = []
        for i, f in enumerate(files):
            b = await f.read()
            if len(b) > 60 * 1024 * 1024:
                raise HTTPException(413, f"{f.filename} is larger than 60 MB")
            data.append((rels[i] if i < len(rels) and rels[i] else f.filename, b))
        job = service.add_files(case_id, data, u, warn=False)
        warnings = service.attach_warnings(job["id"], await asyncio.to_thread(service.scan_warnings, case_id, job["doc_ids"], u))  # page count off the event loop
        return {"job": job["id"], "total": job["total"], "warnings": warnings}

    # ---- intake: department uploads before patient matching (V1 item 2.3) ----------------------------------------------
    def _intake(doc_id, rl, actionable=False):
        try:
            d = store.get_intake(doc_id)
        except ValueError:
            raise HTTPException(404, "document not found")
        if not d:
            raise HTTPException(404, "document not found")
        if not (rl["admin"] or rl["coordinator"] or org.can(rl, "inbox", d.get("department"))):
            raise HTTPException(403, "This document was uploaded by another department")
        if actionable and d.get("state") not in intake.ACTIONABLE:
            raise HTTPException(409, f"This record is still being read ({d.get('state')}); try again in a moment")
        return d

    @r.post("/intake/documents")
    async def intake_upload(request: Request, files: list[UploadFile] = File(...), paths: str = Form("[]"), department: str = Form("")):
        """Upload for a department without choosing a Case File. The files are read, classified and identified in the intake area, then
        matched to a patient (filed automatically on an exact identifier, otherwise queued for a person)."""
        u = _user(request); rl = _roles(request)
        dept = org.department_id(department) if department else None
        if not dept:
            raise HTTPException(400, "Choose the department you are uploading for")
        _need(rl, "upload", dept)
        rels = json.loads(paths or "[]")
        data = []
        for i, f in enumerate(files):
            b = await f.read()
            if len(b) > 60 * 1024 * 1024:
                raise HTTPException(413, f"{f.filename} is larger than 60 MB")
            data.append((rels[i] if i < len(rels) and rels[i] else f.filename, b))
        job = service.add_intake_files(data, dept, u, warn=False)
        warnings = service.attach_warnings(job["id"], await asyncio.to_thread(service.scan_warnings, "intake", job["doc_ids"], u, True))
        return {"job": job["id"], "total": job["total"], "department": dept, "warnings": warnings}

    @r.get("/intake")
    async def intake_queue(request: Request):
        rl = _roles(request)
        docs = intake.queue(rl)
        cases = [{"case_id": c["case_id"], "patient": c.get("patient") or {}, "protocol": c.get("protocol"), "listing": c.get("listing")} for c in store.list_cases()]
        return {"documents": docs, "cases": cases, "can_match": org.can(rl, "match"), "can_create": org.can(rl, "create_case"),
                "departments": org.my_departments(rl), "audit": store.read_intake_audit(200) if (rl["admin"] or rl["coordinator"]) else []}

    @r.get("/intake/{doc_id}")
    async def intake_doc(doc_id: str, request: Request):
        return _intake(doc_id, _roles(request))

    @r.get("/intake/{doc_id}/file")
    async def intake_file(doc_id: str, request: Request, render: int = 0, page: int = 0):
        _intake(doc_id, _roles(request))
        p = store.intake_original_path(doc_id)
        out = scanned.preview_bytes(p, store.get_intake(doc_id) or {}, bool(render), page)  # Aadhaar blacked out on the preview (V1 item 8.4)
        if out:
            from fastapi.responses import Response
            return Response(out[0], media_type=out[1])
        return FileResponse(p)

    @r.post("/intake/{doc_id}/file-to-case")
    async def intake_file_to_case(doc_id: str, request: Request):
        """A person files the document into a Case File ({"case_id": ..., "reason": ...}); recorded as a confirm_match in that Case File."""
        u = _user(request); rl = _roles(request); _need(rl, "match"); _intake(doc_id, rl, actionable=True); b = await request.json()
        case_id = store.safe_id(str(b.get("case_id", "")))
        if not store.get_case(case_id):
            raise HTTPException(404, "Case not found")
        job = service.file_intake(doc_id, case_id, u, "confirmed", str(b.get("reason", "")))
        return {"job": job["id"], "case_id": case_id, "duplicate": job.get("duplicate")}

    @r.post("/intake/{doc_id}/new-case")
    async def intake_new_case(doc_id: str, request: Request):
        """Start a new Case File from the document's identity ({"case_id"?: ..., "patient"?: {...}}); it waits for listing (V1 item 2.5)."""
        u = _user(request); rl = _roles(request); _need(rl, "create_case"); d = _intake(doc_id, rl, actionable=True)
        b = await request.json() if (await request.body()) else {}
        cid = store.safe_id(str(b["case_id"])) if b.get("case_id") else None
        if cid and store.get_case(cid):
            raise HTTPException(409, "Case already exists")
        pat = b.get("patient") if isinstance(b.get("patient"), dict) else None
        if cid:
            pat = pat or intake.patient_from_identity(d)
            store.create_case(cid, pat, "", created_by=u)
            store.audit(cid, {"kind": "case_created", "by": u, "from_intake": doc_id, "listing": "awaiting_listing"})
            job = service.file_intake(doc_id, cid, u, "new_case", str(b.get("reason", "")))
        else:
            job = service.file_intake(doc_id, None, u, "new_case", str(b.get("reason", "")), patient=pat)
        return {"job": job["id"], "case_id": job["case_id"]}

    @r.post("/intake/{doc_id}/not-this-patient")
    async def intake_not_this_patient(doc_id: str, request: Request):
        u = _user(request); rl = _roles(request); _need(rl, "match"); _intake(doc_id, rl, actionable=True); b = await request.json()
        case_id = store.safe_id(str(b.get("case_id", "")))
        if not store.get_case(case_id):
            raise HTTPException(404, "Case not found")
        async with store.lock(case_id):
            try:
                return intake.not_this_patient(doc_id, case_id, u, str(b.get("reason", "")))
            except ValueError as e:
                raise HTTPException(400, str(e))

    @r.delete("/intake/{doc_id}")
    async def intake_discard(doc_id: str, request: Request):
        u = _user(request); rl = _roles(request); d = _intake(doc_id, rl, actionable=True)
        _need(rl, "delete_document", d.get("department"))
        reason = request.query_params.get("reason", "")
        intake.discard(doc_id, u, reason)
        return {"ok": True}

    @r.post("/intake/{doc_id}/reprocess")
    async def intake_reprocess(doc_id: str, request: Request):
        u = _user(request); rl = _roles(request); d = _intake(doc_id, rl, actionable=True); _need(rl, "upload", d.get("department"))
        job = service.reprocess_intake([doc_id], u)
        return {"job": job["id"], "total": job["total"]}

    @r.get("/jobs/{job_id}")
    async def job(job_id: str, request: Request):
        _user(request)
        j = service.get_job(job_id)  # in memory, or on disk after a restart (V1 item 1.8)
        if not j:
            raise HTTPException(404, "job not found")
        return j

    # ---- department inbox and in-app notifications (V1 item 4.4) -------------------------------------------------------
    @r.get("/inbox")
    async def inbox(request: Request):
        """Every open Pre-Authorization request across the Case Files for the departments this user may see (members and heads
        their own, admins all), with overdue worked out on display; requests closed in the last 7 days are listed too."""
        rl = _roles(request)
        return notify.inbox(rl)

    @r.get("/notifications")
    async def notifications(request: Request, unread: int = 0, limit: int = 100):
        rl = _roles(request)
        return {"notifications": notify.for_roles(rl, limit=max(1, min(limit, 500)), unread_only=bool(unread)), "unread": notify.unread_count(rl)}

    @r.post("/notifications/read")
    async def notifications_read(request: Request):
        """{"ids": [...]} marks those read for this user; {"all": true} marks every notification addressed to the user read."""
        rl = _roles(request); b = await request.json() if (await request.body()) else {}
        if not isinstance(b, dict) or not isinstance(b.get("ids") or [], list):
            raise HTTPException(400, 'Send {"ids": [...]} or {"all": true}')
        ids = None if b.get("all") else [str(x) for x in (b.get("ids") or [])]
        return {"changed": notify.mark_read(rl, ids), "unread": notify.unread_count(rl)}

    @r.get("/cases/{case_id}/export/vtb")
    async def export_vtb(case_id: str, request: Request):
        """The NCG Virtual Tumour Board case template filled from the verified Case File summary (V1 item 4.6), for referral to a
        Regional Cancer Centre or the NCG VTB. Refused (409) without a current summary. Audited."""
        u = _user(request); _need_known(_roles(request)); _case(case_id)
        from tumour_board import vtb_export
        try:
            data = await asyncio.to_thread(vtb_export.build, case_id)
        except vtb_export.ExportNotReady as e:
            raise HTTPException(409, str(e))
        store.audit(case_id, {"kind": "export_vtb", "by": u, "bytes": len(data), "template": "NCG Virtual Tumour Board case template"})
        from fastapi.responses import Response
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        headers={"Content-Disposition": f'attachment; filename="{vtb_export.filename(case_id)}"'})

    @r.get("/cases/{case_id}/export/fhir")
    async def export_fhir(case_id: str, request: Request):
        """FHIR R4 document bundle of the Case File (mCODE-informed, not profile-validated; values as recorded) (12 Oct)."""
        _user(request); _case(case_id)
        b = fhir_export.bundle(case_id)
        return JSONResponse(b, headers={"Content-Disposition": f'attachment; filename="{case_id}_fhir_bundle.json"'})

    @r.get("/cases/{case_id}/export/registry")
    async def export_registry(case_id: str, request: Request, format: str = "json"):
        """The HBCR (ICMR-NCDIR 2025) registry items as the records state them, with sources (12 Oct)."""
        _user(request); _case(case_id)
        if format == "csv":
            from fastapi.responses import Response
            return Response(fhir_export.registry_csv(case_id), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{case_id}_registry_abstract.csv"'})
        return fhir_export.registry_abstract(case_id)

    @r.get("/cases/{case_id}/export")
    async def export(case_id: str, request: Request):
        """Portable record of the Case File (state, documents' extracted data, audit) for the hospital record system."""
        _user(request); c = _case(case_id)
        docs = []
        for d in store.list_docs(case_id):
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "sha256", "classification", "identity", "facts", "state", "processed")})
        return JSONResponse({"case": c, "state": store.get_state(case_id), "documents": docs, "audit": store.read_audit(case_id, 5000)},
                            headers={"Content-Disposition": f'attachment; filename="{c["case_id"]}_case_file.json"'})

    @r.get("/cases/{case_id}/documents/{doc_id}")
    async def doc(case_id: str, doc_id: str, request: Request):
        _user(request); _case(case_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        # as the clinicians confirmed it (V1 item 2.2; review M1: a confirmed value no longer shows as the model's reading), facts saying
        # whether they were read from a scan (V1 item 8.1)
        return scanned.with_source_methods(confirm.apply_to_doc(d, store.get_state(case_id)))

    @r.get("/cases/{case_id}/documents/{doc_id}/file")
    async def doc_file(case_id: str, doc_id: str, request: Request, render: int = 0, page: int = 0):
        _user(request); _case(case_id)
        p = store.original_path(case_id, doc_id)
        # page preview as PNG (keeps the strict CSP: no PDF iframes needed); Aadhaar groups read by the OCR engine blacked out (V1 item 8.4)
        out = scanned.preview_bytes(p, store.get_doc(case_id, doc_id) or {}, bool(render), page)
        if out:
            from fastapi.responses import Response
            return Response(out[0], media_type=out[1])
        return FileResponse(p)

    @r.post("/cases/{case_id}/recheck")
    async def recheck(case_id: str, request: Request):
        u = _user(request); _need_known(_roles(request)); _case(case_id)
        async with store.lock(case_id):  # never interleave with an ingestion job writing the same state
            return service.recheck(case_id, u)

    @r.post("/cases/{case_id}/reprocess")
    async def reprocess(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "upload_to_case"); _case(case_id)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):  # withdraws dismissals: never alongside a confirmation being recorded
            job = service.reprocess(case_id, (b if isinstance(b, dict) else {}).get("which", "errors"), u)
        return {"job": job["id"], "total": job["total"]}

    @r.delete("/cases/{case_id}/documents/{doc_id}")
    async def delete_doc(case_id: str, doc_id: str, request: Request):
        u = _user(request); _case(case_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        _need(_roles(request), "delete_document", _doc_department(d))
        async with store.lock(case_id):
            return service.delete_document(case_id, doc_id, u)

    def _confirmation_permission(rl, case_id, c, ctype, key):
        """The permission each confirmation type needs (plan 2.2: permission goes through can()). Document-level types are
        checked against the department that uploaded the document; a waiver against the requirement's Responsible Department."""
        action = confirm.TYPES[ctype]["action"]
        if ctype == "waive":
            dept = next((q.get("department") for q in protocol.get(c["protocol"]).get("mandatory", []) if q["id"] == key), "") if c.get("protocol") else ""
            _need(rl, "waive", dept or None)
        elif ctype == "confirm_match":
            _need(rl, "match")
        elif confirm.TYPES[ctype]["target"] in ("document", "fact"):
            doc_id = key.partition(":")[0] if confirm.TYPES[ctype]["target"] == "fact" else key
            _need(rl, action, _doc_department(store.get_doc(case_id, doc_id) if doc_id else None))
        elif ctype == "resolve_flag":
            _need(rl, "board_record")
        else:
            _need(rl, action)

    @r.post("/cases/{case_id}/confirmations")
    async def confirmations(case_id: str, request: Request):
        """One clinician confirmation (V1 item 2.2): {"type": attest_final | waive | confirm_dates | confirm_doc_type | confirm_match |
        dismiss_failed | confirm_value | resolve_flag, "key": id, "fields": {...}, "reason": "..."}. Validated, audited, undoable;
        applied after the model so it wins and survives a re-process. Returns the record and the re-checked state."""
        u = _user(request); c = _case(case_id); b = await request.json()
        ctype, key = str(b.get("type", "")), str(b.get("key", ""))
        if ctype not in confirm.TYPES:
            raise HTTPException(400, f"Unknown confirmation type: {ctype}")
        _confirmation_permission(_roles(request), case_id, c, ctype, key)
        if ctype == "resolve_flag":  # a board record's flag (V1 item 7.3): "<record id>:<flag id>"; a correction amends the decision
            rid, _, fid = key.partition(":")
            out = await _resolve_flag(case_id, rid, fid, b.get("fields") or {}, b.get("reason", ""), u)
            return {"confirmation": confirm.latest(case_id, "resolve_flag", key), "state": store.get_state(case_id), "record": out["record"]}
        async with store.lock(case_id):
            if ctype == "dismiss_failed":  # only a document that failed to read can be dismissed (V1 item 4.3, review M9)
                d = store.get_doc(case_id, key)
                if not d or d.get("state") != "error":
                    raise HTTPException(409, "Only a document that failed to read can be dismissed" + (f" (this one is {d.get('state')})" if d else ""))
            try:
                rec = confirm.record(case_id, ctype, key, b.get("fields") or {}, b.get("reason", ""), u)
            except ValueError as e:
                raise HTTPException(400, str(e))
            st = service.recheck(case_id, u) if c.get("protocol") else store.get_state(case_id)
            job = service.reextract_document(case_id, key, u) if ctype == "confirm_doc_type" else None  # fields again under the confirmed type (V1 item 3.2)
        return {"confirmation": rec, "state": st, **({"job": job["id"]} if job else {})}

    @r.post("/cases/{case_id}/confirmations/{conf_id}/undo")
    async def confirmation_undo(case_id: str, conf_id: str, request: Request):
        u = _user(request); c = _case(case_id)
        rec = next((x for x in store.get_state(case_id).get("confirmations", []) if x["id"] == conf_id), None)
        if not rec:
            raise HTTPException(404, "confirmation not found")
        _confirmation_permission(_roles(request), case_id, c, rec["type"], rec["key"])
        if rec.get("undone"):
            raise HTTPException(409, "already undone")
        if rec["type"] == "resolve_flag":  # V1 item 7.3: a correction is taken back as a new version of the decision
            async with store.lock(case_id):
                try:
                    record = postboard.undo_resolution(case_id, conf_id, u)
                except KeyError:
                    raise HTTPException(409, "already undone")
                except ValueError as e:  # a later correction changed the same words: nothing was undone
                    raise HTTPException(409, str(e))
            if record and record.get("session"):
                _session_call(board.decision_amended, record["session"], case_id, record, u)
            return {"confirmation": next((x for x in store.get_state(case_id).get("confirmations", []) if x["id"] == conf_id), rec),
                    "state": store.get_state(case_id), "record": record}
        async with store.lock(case_id):
            if rec["type"] == "confirm_match" and (rec.get("fields") or {}).get("case_id") and store.get_doc(case_id, rec["key"]):
                # undoing a match (a person's or the matcher's) moves the document back to the Needs matching queue
                out = service.unfile_document(case_id, rec["key"], u, "match undone")
                return {"confirmation": next((x for x in store.get_state(case_id).get("confirmations", []) if x["id"] == conf_id), rec), "state": out["state"], "unfiled": True}
            try:
                rec = confirm.undo(case_id, conf_id, u)
            except KeyError:
                raise HTTPException(409, "already undone")
            if rec["type"] == "confirm_match" and not (rec.get("fields") or {}).get("case_id"):
                intake.clear_rejection(rec["key"], case_id)  # "not this patient" withdrawn: the Case File may be suggested again
            st = service.recheck(case_id, u) if c.get("protocol") else store.get_state(case_id)
            job = service.reextract_document(case_id, rec["key"], u) if rec["type"] == "confirm_doc_type" else None  # back to the model's type: fields again
        return {"confirmation": rec, "state": st, **({"job": job["id"]} if job else {})}

    @r.post("/cases/{case_id}/documents/{doc_id}/unfile")
    async def unfile_doc(case_id: str, doc_id: str, request: Request):
        """Reverse a patient match: the document goes back to the Needs matching queue; the Case File forgets what it learned from it."""
        u = _user(request); _need(_roles(request), "match"); _case(case_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            try:
                return service.unfile_document(case_id, doc_id, u, str(b.get("reason", "")))
            except ValueError as e:
                raise HTTPException(409, str(e))

    @r.post("/cases/{case_id}/overrides")
    async def overrides(case_id: str, request: Request):
        """Kept as an alias of /confirmations: {"kind": "requirements"|"documents", "key": id, "value": {...} | null}.
        requirements: {"waived": true, "reason": "..."} = waive; documents: {"attested_final": true, "reason": "..."} = attest_final; null undoes."""
        u = _user(request); c = _case(case_id); b = await request.json()
        if b.get("kind") not in ("requirements", "documents"):
            raise HTTPException(400, "kind must be requirements or documents")
        key = str(b.get("key", ""))
        _confirmation_permission(_roles(request), case_id, c, "waive" if b["kind"] == "requirements" else "attest_final", key)
        async with store.lock(case_id):
            try:
                confirm.legacy_override(case_id, b["kind"], key, b.get("value"), u)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return service.recheck(case_id, u)

    @r.post("/cases/{case_id}/actions/{action_id}")
    async def update_action(case_id: str, action_id: str, request: Request):
        u = _user(request); _case(case_id); b = await request.json()
        st = store.get_state(case_id)
        for a in st.get("actions", []):
            if a["id"] == action_id:
                _need(_roles(request), "update_action", a.get("department") or None)
                if b.get("status") in ("pending", "completed", "overdue"):
                    if b["status"] == "completed" and a.get("status") != "completed":  # the inbox shows a closed request for 7 days from this time
                        a["completed"], a["closed_by"] = store.now_iso(), u
                        a.pop("suggested_close", None)
                    elif b["status"] != "completed":
                        for k in ("completed", "closed_by", "closed_doc_id"):  # reopened
                            a.pop(k, None)
                    a["status"] = b["status"]
                if b.get("note"):
                    a["history"].append({"ts": store.now_iso(), "event": f"Note by {u}: {b['note']}"})
                if b.get("due"):
                    a["due"] = b["due"]
                a["history"].append({"ts": store.now_iso(), "event": f"Updated by {u}"})
                store.save_state(case_id, st); store.audit(case_id, {"kind": "action_updated", "action": action_id, "by": u, **b})
                return a
        raise HTTPException(404, "action not found")

    def _board_action(case_id, action_id, request):
        a = next((x for x in store.get_state(case_id).get("actions", []) if x.get("id") == action_id), None)
        if not a:
            raise HTTPException(404, "action not found")
        _need(_roles(request), "update_action", a.get("department") or None)
        return a

    @r.post("/cases/{case_id}/actions/{action_id}/close")
    async def close_action(case_id: str, action_id: str, request: Request):
        """A person closes a Tumour Board action, optionally with the document that answers it (V1 item 7.4): {"doc_id"?, "note"?}."""
        u = _user(request); _case(case_id); b = await request.json() if (await request.body()) else {}
        _board_action(case_id, action_id, request)
        async with store.lock(case_id):
            st = store.get_state(case_id)
            doc_id = str((b or {}).get("doc_id") or "")
            if doc_id and not store.get_doc(case_id, doc_id):
                raise HTTPException(404, "document not found")
            try:
                ev = followup.close_action(st, action_id, u, doc_id or None, str((b or {}).get("note") or "")[:500])
            except KeyError:
                raise HTTPException(404, "action not found")
            except ValueError as e:
                raise HTTPException(409, str(e))
            store.save_state(case_id, st); store.audit(case_id, ev)
        return next(x for x in st["actions"] if x["id"] == action_id)

    @r.post("/cases/{case_id}/actions/{action_id}/dismiss-suggestion")
    async def dismiss_suggestion(case_id: str, action_id: str, request: Request):
        """The suggested document does not answer the Tumour Board action (V1 item 7.4): it is never suggested again for it."""
        u = _user(request); _case(case_id)
        _board_action(case_id, action_id, request)
        async with store.lock(case_id):
            st = store.get_state(case_id)
            try:
                ev = followup.dismiss_suggestion(st, action_id, u)
            except KeyError:
                raise HTTPException(404, "action not found")
            except ValueError as e:
                raise HTTPException(409, str(e))
            store.save_state(case_id, st); store.audit(case_id, ev)
        return next(x for x in st["actions"] if x["id"] == action_id)

    @r.post("/cases/{case_id}/search")
    async def do_search(case_id: str, request: Request):
        _user(request); _case(case_id); b = await request.json()
        import asyncio, time
        t0 = time.time()
        values = search.find_values(case_id, b.get("query", ""))
        t1 = time.time()
        passages = await asyncio.to_thread(search.index(case_id).search, b.get("query", ""), 8)
        return {"values": values, "passages": passages, "ms_values": round((t1 - t0) * 1000, 1), "ms_total": round((time.time() - t0) * 1000, 1)}

    @r.post("/cases/{case_id}/ask")
    async def ask(case_id: str, request: Request):
        _need_known(_roles(request)); _case(case_id); b = await request.json()
        return await qa.ask(case_id, b.get("question", ""), b.get("history"))

    @r.post("/cases/{case_id}/agents/{role}")
    async def agent(case_id: str, role: str, request: Request):
        _need_known(_roles(request)); _case(case_id)
        b = await request.json() if (await request.body()) else {}

        async def gen():
            async for ev in agents.run_agent(case_id, role, b.get("focus", "")):
                yield json.dumps(ev) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @r.post("/cases/{case_id}/agents/{role}/ask")
    async def agent_ask(case_id: str, role: str, request: Request):
        """A question to one specialty's agent outside a board session (V1 item 6.2): {"question", "history"?}."""
        _need_known(_roles(request)); _case(case_id); b = await request.json()
        if role not in agents.ROLES:
            raise HTTPException(404, "unknown role")
        if not str(b.get("question", "")).strip():
            raise HTTPException(400, "Ask a question")
        return await agents.ask(case_id, role, str(b["question"])[:1000], _history(b.get("history")), _user(request))

    @r.post("/cases/{case_id}/summary")
    async def make_summary(case_id: str, request: Request):
        _need_known(_roles(request)); _case(case_id)
        b = await request.json() if (await request.body()) else {}
        return await summary.build(case_id, force=bool(b.get("force")))

    async def _resolve_flag(case_id, record_id, flag_id, fields, reason, u):
        async with store.lock(case_id):
            try:
                rec = postboard.resolve_flag(case_id, record_id, flag_id, str(fields.get("resolution", "")), str(fields.get("value", "") or ""), str(reason or ""), u)
            except KeyError as e:
                raise HTTPException(404, str(e).strip("'"))
            except ValueError as e:
                raise HTTPException(400, str(e))
        if rec.get("session"):  # the Board room and the session export show the current version
            _session_call(board.decision_amended, rec["session"], case_id, rec, u)
        return {"record": rec}

    @r.post("/cases/{case_id}/board-records/{record_id}/flags/{flag_id}/resolve")
    async def resolve_board_flag(case_id: str, record_id: str, flag_id: str, request: Request):
        """Human over the loop (V1 item 7.3): {"resolution": corrected | intentional_deviation | false_alarm, "value" (corrected), "reason"
        (required for an intentional deviation)}. A correction amends the decision (new version, history kept). Audited, undoable."""
        u = _user(request); _need(_roles(request), "board_record"); _case(case_id); b = await request.json()
        return await _resolve_flag(case_id, record_id, flag_id, b if isinstance(b, dict) else {}, (b or {}).get("reason", ""), u)

    @r.post("/cases/{case_id}/board-records")
    async def board_records(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "board_record"); _case(case_id); b = await request.json()
        try:
            return await postboard.record_decision(case_id, b, u)
        except ValueError as e:  # an outcome or communication field out of range (12 Oct)
            raise HTTPException(400, str(e))

    @r.post("/cases/{case_id}/review")
    async def review(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "review"); _case(case_id); b = await request.json()
        try:
            return service.review(case_id, b["artefact"], b.get("status", "reviewed"), b.get("comment", ""), u)
        except KeyError:
            raise HTTPException(404, "artefact not found")

    @r.get("/cases/{case_id}/audit")
    async def audit(case_id: str, request: Request):
        _user(request); _case(case_id)
        return {"events": store.read_audit(case_id), "chain": store.verify_audit(case_id)}  # tamper-evident chain (12 Oct)

    @r.get("/cases/{case_id}/audit/verify")
    async def audit_verify(case_id: str, request: Request):
        _user(request); _case(case_id)
        return store.verify_audit(case_id)

    @r.post("/cases/{case_id}/board-records/{record_id}/communication")
    async def record_communication(case_id: str, record_id: str, request: Request):
        """Who informed the patient and when, key worker, intent, trial, consent: set after the board (12 Oct); audited, no new version."""
        rl = _roles(request); _need(rl, "board_record"); _case(case_id); b = await request.json()
        try:
            rec = postboard.update_communication(case_id, store.safe_id(record_id), b, user=rl["user"])
        except KeyError:
            raise HTTPException(404, "No such Tumour Board record")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "record": rec, "state": store.get_state(case_id)}

    @r.post("/guidelines/search")
    async def gl_search(request: Request):
        _user(request); b = await request.json()
        import asyncio
        return await asyncio.to_thread(guidelines.search_grouped, b.get("query", ""), b.get("cancer"))

    @r.get("/cases/{case_id}/guidelines")
    async def gl_case(case_id: str, request: Request):
        _user(request); c = _case(case_id)
        import asyncio
        qs = guidelines.queries_for_case(case_id)
        res = await asyncio.gather(*[asyncio.to_thread(guidelines.search_grouped, q, c["protocol"], 2, 2) for q in qs])
        return {"queries": [{"query": q, **r} for q, r in zip(qs, res)]}

    @r.get("/guidelines/file")
    async def gl_file(path: str, request: Request):
        _user(request)
        root = config.GUIDELINE_DIR.resolve()
        p = (root / path).resolve()
        if root not in p.parents or not p.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(p)

    # ---- board sessions: agenda, attendance, agents for absent specialties, agent log vs decision (V1 items 6.1 to 6.3) ----------
    def _session(sid):
        """The session; callers use its stored id from here on (an id spelled another way never keys tasks or audit entries)."""
        try:
            s = board.get(sid)
        except ValueError:
            raise HTTPException(404, "Board session not found")
        if not s:
            raise HTTPException(404, "Board session not found")
        return s

    def _ids(xs):
        try:
            return [store.safe_id(str(x)) for x in xs]
        except ValueError:
            raise HTTPException(400, "A Case File id is not valid")

    def _session_call(fn, *a, **k):
        try:
            return fn(*a, **k)
        except ValueError as e:
            raise HTTPException(400, str(e))

    def _on_agenda(s, case_id):
        if case_id not in {a["case_id"] for a in s["agenda"]}:
            raise HTTPException(404, "This Case File is not on the session's agenda")

    def _room(s, rl):
        """Everything the Board room shows: the session, the specialties, and for each Case File on the agenda its gate, its summary and
        the briefs of the absent specialties' agents (with their stale state)."""
        absent = board.absent_roles(s)
        cases = {}
        for a in s["agenda"]:
            cid = a["case_id"]; c = store.get_case(cid)
            if not c:
                cases[cid] = {"missing": True}; continue
            st = store.get_state(cid); g = st.get("gate") or {}
            sig = rules.case_signature(cid, st)
            arts = st.get("artefacts") or {}
            stale = lambda x: (rules.stale_reason(x["signature"], sig) if x.get("signature") else "Compiled before the Case File signature was kept") if x else ""
            cases[cid] = {"patient": c.get("patient") or {}, "protocol": c.get("protocol"), "setting": c.get("setting"), "board_date": c.get("board_date"),
                          "gate": {"passed": g.get("passed"), "satisfied": g.get("satisfied"), "total": g.get("total"), "readiness": g.get("readiness")},
                          "summary": arts.get("summary"), "summary_stale": stale(arts.get("summary")),
                          "briefs": {r_: arts.get(f"brief_{r_}") for r_ in absent if arts.get(f"brief_{r_}")},
                          "briefs_stale": {r_: stale(arts.get(f"brief_{r_}")) for r_ in absent if arts.get(f"brief_{r_}")},
                          "board_records": [{"id": b_["id"], "board_date": b_.get("board_date"), "session": b_.get("session"), "status": b_["adjudication"]["status"],
                                             "flags": len(b_["adjudication"]["flags"]), "composition": b_["adjudication"].get("composition"),
                                             "resolution": b_.get("resolution"), "version": b_.get("version", 1)} for b_ in st.get("board_records", [])]}
        return {"session": s, "specialties": board.specialties(), "absent_roles": absent, "participants": board.participants(s),
                "roles": {k: {"label": agents.spec(k)["label"], "department": agents.department_of(k)} for k in agents.ROLES},
                "cases": cases, "can_manage": org.can(rl, "session"), "can_ask": bool(rl.get("admin") or rl.get("known")), "can_review": org.can(rl, "review"),
                "marks": board.MARKS}

    @r.get("/sessions")
    async def sessions(request: Request):
        rl = _roles(request)
        return {"sessions": board.list_sessions(), "can_manage": org.can(rl, "session")}

    @r.get("/sessions/candidates")
    async def session_candidates(request: Request, date: str = ""):
        """The Case Files listed for the board on that date (V1 item 6.1), in agenda order."""
        _user(request)
        return {"date": date, "cases": _session_call(board.listed_for_date, date)}

    @r.post("/sessions")
    async def session_create(request: Request):
        u = _user(request); _need(_roles(request), "session"); b = await request.json()
        ids = _ids(b["case_ids"]) if isinstance(b.get("case_ids"), list) else None
        return _session_call(board.create, str(b.get("date", "")), u, ids, str(b.get("title", ""))[:120])

    @r.get("/sessions/{sid}")
    async def session_get(sid: str, request: Request):
        rl = _roles(request); sid = _session(sid)["id"]
        return _room(service.session_interrupted(sid), rl)

    @r.put("/sessions/{sid}/agenda")
    async def session_agenda(sid: str, request: Request):
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]; b = await request.json()
        return _session_call(board.set_agenda, sid, _ids(b.get("case_ids") or []), u)

    @r.post("/sessions/{sid}/attendance")
    async def session_attendance(sid: str, request: Request):
        """{"department": id, "status": present | absent | not_marked}. Marking a specialty absent during the session starts its agent."""
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]; b = await request.json()
        s = _session_call(board.set_attendance, sid, str(b.get("department", "")), str(b.get("status", "")), u)
        dept = org.department_id(str(b.get("department", "")))  # an id, a name or an alias (Radio-diagnosis, Radiology)
        role = next((k for k, v in board.ROLE_DEPARTMENT.items() if v == dept), None)
        if s["status"] == "in_session" and role and b.get("status") == "absent":
            service.prepare_session_agents(sid, u, roles=[role])
        return board.get(sid)

    @r.post("/sessions/{sid}/members")
    async def session_member(sid: str, request: Request):
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]; b = await request.json()
        return _session_call(board.add_member, sid, str(b.get("name", "")), str(b.get("department", "")), u)

    @r.delete("/sessions/{sid}/members/{member_id}")
    async def session_member_remove(sid: str, member_id: str, request: Request):
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]
        return _session_call(board.remove_member, sid, member_id, u)

    @r.post("/sessions/{sid}/start")
    async def session_start(sid: str, request: Request):
        """The session starts: the agents of the absent specialties prepare their briefs for every Case File on the agenda, in parallel (V1 item 6.2)."""
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]
        _session_call(board.start, sid, u)
        pairs = service.prepare_session_agents(sid, u)
        return {**board.get(sid), "preparing": len(pairs)}

    @r.post("/sessions/{sid}/agents/prepare")
    async def session_prepare(sid: str, request: Request):
        """Prepare again: {"case_id"?, "role"?, "refresh"?: true}. Without refresh a brief still current for the Case File is reused."""
        u = _user(request); _need(_roles(request), "session"); s = _session(sid); sid = s["id"]; b = await request.json() if (await request.body()) else {}
        if s["status"] == "closed":
            raise HTTPException(409, "The session is closed")
        roles = [b["role"]] if b.get("role") else None
        if roles and roles[0] not in board.ROLE_DEPARTMENT:
            raise HTTPException(404, "unknown role")
        if roles and roles[0] not in board.absent_roles(s):  # agents stand in for absent specialties only
            raise HTTPException(400, "That specialty is not marked absent in this session")
        pairs = service.prepare_session_agents(sid, u, roles=roles, case_ids=[b["case_id"]] if b.get("case_id") else None, refresh=bool(b.get("refresh")))
        return {**board.get(sid), "preparing": len(pairs)}

    @r.post("/sessions/{sid}/current")
    async def session_current(sid: str, request: Request):
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]; b = await request.json()
        return _session_call(board.set_current, sid, str(b.get("case_id", "")), u)

    @r.post("/sessions/{sid}/close")
    async def session_close(sid: str, request: Request):
        u = _user(request); _need(_roles(request), "session"); sid = _session(sid)["id"]
        return _session_call(service.close_session, sid, u)  # briefs still being prepared are cancelled

    @r.post("/sessions/{sid}/cases/{case_id}/agents/{role}/ask")
    async def session_ask(sid: str, case_id: str, role: str, request: Request):
        """The board asks an absent specialty's agent (V1 item 6.2); the answer goes to the session's agent log (6.3)."""
        u = _user(request); rl = _roles(request); _need_known(rl); s = _session(sid); sid = s["id"]; _on_agenda(s, case_id); _case(case_id)
        b = await request.json()
        if role not in agents.ROLES:
            raise HTTPException(404, "unknown role")
        if s["status"] == "closed":
            raise HTTPException(409, "The session is closed")
        q = str(b.get("question", "")).strip()[:1000]
        if not q:
            raise HTTPException(400, "Ask a question")
        a = await agents.ask(case_id, role, q, _history(b.get("history")), u)
        try:  # the session may have been closed (or the Case File taken off the agenda) during the model call: the answer still returns
            entry = board.log_answer(sid, case_id, role, q, a, by=u)
        except ValueError as e:
            return {**a, "log_entry": None, "log_warning": f"Not kept in the session's agent log: {e}"}
        return {**a, "log_entry": entry["id"]}

    @r.post("/sessions/{sid}/cases/{case_id}/decision")
    async def session_decision(sid: str, case_id: str, request: Request):
        """The board's decision for a Case File on the agenda: recorded and checked like any board record (adjudication), with the session's
        attendance as participants, and linked to the session's agent log (V1 item 6.3)."""
        u = _user(request); _need(_roles(request), "board_record"); s = _session(sid); sid = s["id"]; _on_agenda(s, case_id); _case(case_id); b = await request.json()
        if not str(b.get("decision_text", "")).strip():
            raise HTTPException(400, "Write the board's decision")
        part = board.participants(s)
        rec = {k: b.get(k) for k in ("decision_text", "recorded_by", "report_corrections_raised", "divergent_opinions", "actions", "next_review", "outcome_type", "deferred_reason",
                                     "referred_to", "intent_as_recorded", "trial_considered", "consent_recorded", "key_worker") if b.get(k) is not None}
        rec.update({"board_date": s["date"], "session": sid, "participants": b.get("participants") or part["text"],
                    "attendance": {"present": part["present"], "absent": part["absent"], "members": part["members"]}})
        record = await postboard.record_decision(case_id, rec, u)
        _session_call(board.link_decision, sid, case_id, record, u)
        return {"record": record, "session": board.get(sid)}

    @r.post("/sessions/{sid}/cases/{case_id}/log/{entry_id}/mark")
    async def session_mark(sid: str, case_id: str, entry_id: str, request: Request):
        """{"mark": discussed | accepted | not_relevant | null, "note"?}: what the board made of an agent point, once the decision is recorded."""
        u = _user(request); _need(_roles(request), "board_record"); s = _session(sid); sid = s["id"]; _on_agenda(s, case_id); b = await request.json()
        return _session_call(board.mark, sid, case_id, entry_id, b.get("mark"), u, str(b.get("note", ""))[:500])

    @r.get("/sessions/{sid}/export")
    async def session_export(sid: str, request: Request, format: str = "html"):
        """What the agents said vs what the board decided, side by side (V1 item 6.3). Reporting only. Audited."""
        u = _user(request); sid = _session(sid)["id"]
        board.audit_session(sid, {"kind": "export", "by": u, "format": format})
        if format == "json":
            return JSONResponse(board.export(sid), headers={"Content-Disposition": f'attachment; filename="{sid}_agent_log_and_decisions.json"'})
        from fastapi.responses import HTMLResponse
        return HTMLResponse(board.export_html(sid), headers={"Content-Disposition": f'attachment; filename="{sid}_agent_log_and_decisions.html"'})

    @r.get("/models")
    async def model_cards(request: Request):
        _user(request)
        f = config.DATA_ROOT / "model_cards.json"
        cards = json.loads(f.read_text()) if f.exists() else []
        return {"health": await llm.health(), "cards": cards, "embedder": search.EMBED_MODEL}

    return r
