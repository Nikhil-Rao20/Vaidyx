"""HTTP API for Vaidyx-TB (AI agent for the Tumour Board). All routes require a logged-in Vaidyx user; actions that change a Case File
are checked against the hospital's departments and roles in org.json through org.can() (V1 item 2.1)."""
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.auth_helpers import require_user
from tumour_board import agents, config, guidelines, llm, org, postboard, protocol, qa, rules, search, service, store, summary
from tumour_board import confirm  # clinician confirmations (V1 item 2.2)
from tumour_board import intake  # department uploads and patient matching (V1 items 2.3, 2.4)


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
        return {k: {"label": v["label"], "department": v["department"], "focus": v["focus"]} for k, v in agents.ROLES.items()}

    @r.get("/org")
    async def get_org(request: Request):
        """The hospital, its departments and the caller's own roles. The user map and the Vaidyx account list are returned to admins only."""
        rl = _roles(request)
        o = org.load()
        out = {"hospital": o["hospital"], "departments": o["departments"], "me": rl, "my_departments": org.my_departments(rl)}
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
        store.audit(case_id, {"kind": "case_deleted", "by": u}); store.delete_case(case_id); return {"ok": True}

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
        for d in all_docs:
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "state", "error", "classification", "identity", "identity_read", "added", "department", "uploaded_by")} |
                        {"facts": d.get("facts", {}), "pages": len(d.get("pages") or []), "methods": sorted({p["method"] for p in d.get("pages") or []})})
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))  # confirmations overlaid (V1 item 2.2)
        cat = protocol.facts()
        return {"case": c, "state": st, "documents": docs, "facts": {k: {"label": cat.get(k, {}).get("label", k), **v} for k, v in facts.items()},
                "timeline": postboard.timeline(case_id), "permissions": _case_permissions(rl, c, st, all_docs)}

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
        job = service.add_files(case_id, data, u)
        return {"job": job["id"], "total": job["total"]}

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
        job = service.add_intake_files(data, dept, u)
        return {"job": job["id"], "total": job["total"], "department": dept}

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
        if render and p.suffix.lower() == ".pdf":
            import io
            import pypdfium2 as pdfium
            from fastapi.responses import Response
            pdf = pdfium.PdfDocument(str(p))
            im = pdf[max(0, min(page, len(pdf) - 1))].render(scale=1.6).to_pil()
            buf = io.BytesIO(); im.save(buf, "PNG")
            return Response(buf.getvalue(), media_type="image/png")
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
        return d

    @r.get("/cases/{case_id}/documents/{doc_id}/file")
    async def doc_file(case_id: str, doc_id: str, request: Request, render: int = 0, page: int = 0):
        _user(request); _case(case_id)
        p = store.original_path(case_id, doc_id)
        if render and p.suffix.lower() == ".pdf":  # page preview as PNG (keeps the strict CSP: no PDF iframes needed)
            import io
            import pypdfium2 as pdfium
            from fastapi.responses import Response
            pdf = pdfium.PdfDocument(str(p))
            im = pdf[max(0, min(page, len(pdf) - 1))].render(scale=1.6).to_pil()
            buf = io.BytesIO(); im.save(buf, "PNG")
            return Response(buf.getvalue(), media_type="image/png")
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
        job = service.reprocess(case_id, b.get("which", "errors"), u)
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
        async with store.lock(case_id):
            try:
                rec = confirm.record(case_id, ctype, key, b.get("fields") or {}, b.get("reason", ""), u)
            except ValueError as e:
                raise HTTPException(400, str(e))
            st = service.recheck(case_id, u) if c.get("protocol") else store.get_state(case_id)
        return {"confirmation": rec, "state": st}

    @r.post("/cases/{case_id}/confirmations/{conf_id}/undo")
    async def confirmation_undo(case_id: str, conf_id: str, request: Request):
        u = _user(request); c = _case(case_id)
        rec = next((x for x in store.get_state(case_id).get("confirmations", []) if x["id"] == conf_id), None)
        if not rec:
            raise HTTPException(404, "confirmation not found")
        _confirmation_permission(_roles(request), case_id, c, rec["type"], rec["key"])
        if rec.get("undone"):
            raise HTTPException(409, "already undone")
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
        return {"confirmation": rec, "state": st}

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
                    a["status"] = b["status"]
                if b.get("note"):
                    a["history"].append({"ts": store.now_iso(), "event": f"Note by {u}: {b['note']}"})
                if b.get("due"):
                    a["due"] = b["due"]
                a["history"].append({"ts": store.now_iso(), "event": f"Updated by {u}"})
                store.save_state(case_id, st); store.audit(case_id, {"kind": "action_updated", "action": action_id, "by": u, **b})
                return a
        raise HTTPException(404, "action not found")

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

    @r.post("/cases/{case_id}/summary")
    async def make_summary(case_id: str, request: Request):
        _need_known(_roles(request)); _case(case_id)
        b = await request.json() if (await request.body()) else {}
        return await summary.build(case_id, force=bool(b.get("force")))

    @r.post("/cases/{case_id}/board-records")
    async def board(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "board_record"); _case(case_id); b = await request.json()
        return await postboard.record_decision(case_id, b, u)

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
        return {"events": store.read_audit(case_id)}

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

    @r.get("/models")
    async def model_cards(request: Request):
        _user(request)
        f = config.DATA_ROOT / "model_cards.json"
        cards = json.loads(f.read_text()) if f.exists() else []
        return {"health": await llm.health(), "cards": cards, "embedder": search.EMBED_MODEL}

    return r
