"""HTTP API for Vaidyx-TB (AI agent for the Tumour Board). All routes require a logged-in Vaidyx user."""
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.auth_helpers import require_user
from tumour_board import agents, config, guidelines, llm, postboard, protocol, qa, rules, search, service, store, summary


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

    @r.get("/cases")
    async def cases(request: Request):
        _user(request)
        return {"cases": store.list_cases(), "demo": service.list_demo()}

    @r.post("/cases")
    async def create(request: Request):
        u = _user(request); b = await request.json()
        try:
            c = store.create_case(store.safe_id(b["case_id"]), b.get("patient", {}), b["protocol"], b.get("board_date", ""), u)
        except FileExistsError:
            raise HTTPException(409, "Case already exists")
        store.audit(c["case_id"], {"kind": "case_created", "by": u})
        return c

    @r.delete("/cases/{case_id}")
    async def delete(case_id: str, request: Request):
        _user(request); _case(case_id); store.delete_case(case_id); return {"ok": True}

    @r.post("/demo/{case_id}")
    async def demo(case_id: str, request: Request):
        u = _user(request)
        job = service.import_demo(store.safe_id(case_id), u)
        return {"job": job["id"], "total": job["total"]}

    @r.post("/cases/{case_id}/demo-arrivals")
    async def arrivals(case_id: str, request: Request):
        u = _user(request); _case(case_id)
        job = service.demo_arrivals(case_id, u)
        if not job:
            raise HTTPException(404, "No demo arrivals for this case")
        return {"job": job["id"], "total": job["total"]}

    @r.get("/cases/{case_id}")
    async def get_case(case_id: str, request: Request):
        _user(request); c = _case(case_id)
        st = store.get_state(case_id)
        docs = []
        for d in store.list_docs(case_id):
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "state", "error", "classification", "identity", "added")} |
                        {"facts": d.get("facts", {}), "pages": len(d.get("pages") or []), "methods": sorted({p["method"] for p in d.get("pages") or []})})
        facts = rules.resolve_facts(store.list_docs(case_id), st.get("overrides"))
        cat = protocol.facts()
        return {"case": c, "state": st, "documents": docs, "facts": {k: {"label": cat.get(k, {}).get("label", k), **v} for k, v in facts.items()},
                "timeline": postboard.timeline(case_id)}

    @r.post("/cases/{case_id}/documents")
    async def upload(case_id: str, request: Request, files: list[UploadFile] = File(...), paths: str = Form("[]")):
        u = _user(request); _case(case_id)
        rels = json.loads(paths or "[]")
        data = []
        for i, f in enumerate(files):
            b = await f.read()
            if len(b) > 60 * 1024 * 1024:
                raise HTTPException(413, f"{f.filename} is larger than 60 MB")
            data.append((rels[i] if i < len(rels) and rels[i] else f.filename, b))
        job = service.add_files(case_id, data, u)
        return {"job": job["id"], "total": job["total"]}

    @r.get("/jobs/{job_id}")
    async def job(job_id: str, request: Request):
        _user(request)
        j = service.JOBS.get(job_id)
        if not j:
            raise HTTPException(404, "job not found")
        return {k: v for k, v in j.items() if k != "task"}

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
        u = _user(request); _case(case_id)
        async with store.lock(case_id):  # never interleave with an ingestion job writing the same state
            return service.recheck(case_id, u)

    @r.post("/cases/{case_id}/reprocess")
    async def reprocess(case_id: str, request: Request):
        u = _user(request); _case(case_id)
        b = await request.json() if (await request.body()) else {}
        job = service.reprocess(case_id, b.get("which", "errors"), u)
        return {"job": job["id"], "total": job["total"]}

    @r.delete("/cases/{case_id}/documents/{doc_id}")
    async def delete_doc(case_id: str, doc_id: str, request: Request):
        u = _user(request); _case(case_id)
        if not store.get_doc(case_id, doc_id):
            raise HTTPException(404, "document not found")
        async with store.lock(case_id):
            return service.delete_document(case_id, doc_id, u)

    @r.post("/cases/{case_id}/overrides")
    async def overrides(case_id: str, request: Request):
        """Clinical overrides for this Case File: {"kind": "requirements"|"documents", "key": id, "value": {...} | null}.
        requirements: {"waived": true, "reason": "..."}; documents: {"attested_final": true, "reason": "..."}."""
        u = _user(request); _case(case_id); b = await request.json()
        if b.get("kind") not in ("requirements", "documents"):
            raise HTTPException(400, "kind must be requirements or documents")
        async with store.lock(case_id):
            rules.set_override(case_id, b["kind"], str(b.get("key", "")), b.get("value"), u)
            return service.recheck(case_id, u)

    @r.post("/cases/{case_id}/actions/{action_id}")
    async def update_action(case_id: str, action_id: str, request: Request):
        u = _user(request); _case(case_id); b = await request.json()
        st = store.get_state(case_id)
        for a in st.get("actions", []):
            if a["id"] == action_id:
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
        _user(request); _case(case_id); b = await request.json()
        return await qa.ask(case_id, b.get("question", ""), b.get("history"))

    @r.post("/cases/{case_id}/agents/{role}")
    async def agent(case_id: str, role: str, request: Request):
        _user(request); _case(case_id)
        b = await request.json() if (await request.body()) else {}

        async def gen():
            async for ev in agents.run_agent(case_id, role, b.get("focus", "")):
                yield json.dumps(ev) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @r.post("/cases/{case_id}/summary")
    async def make_summary(case_id: str, request: Request):
        _user(request); _case(case_id)
        b = await request.json() if (await request.body()) else {}
        return await summary.build(case_id, force=bool(b.get("force")))

    @r.post("/cases/{case_id}/board-records")
    async def board(case_id: str, request: Request):
        u = _user(request); _case(case_id); b = await request.json()
        return await postboard.record_decision(case_id, b, u)

    @r.post("/cases/{case_id}/review")
    async def review(case_id: str, request: Request):
        u = _user(request); _case(case_id); b = await request.json()
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
