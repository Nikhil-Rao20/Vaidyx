"""HTTP API for Vaidyx-TB (AI agent for the Tumour Board). All routes require a logged-in Vaidyx user; actions that change a Case File
are checked against the hospital's departments and roles in org.json through org.can() (V1 item 2.1)."""
import asyncio, json, logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.auth_helpers import get_current_user, require_user
from tumour_board import agents, config, guidelines, llm, notify, org, postboard, protocol, qa, rules, search, service, store, summary
from tumour_board import steps  # final_status of a report (2 Nov 2026)
from tumour_board import confirm  # clinician confirmations (V1 item 2.2)
from tumour_board import intake  # department uploads and patient matching (V1 items 2.3, 2.4)
from tumour_board import board  # board sessions, attendance, agent log (V1 items 6.1 to 6.3)
from tumour_board import followup  # Tumour Board actions in department inboxes, closing suggestions (V1 item 7.4)
from tumour_board import dept_requests  # requests suggested by the gate, sent by the treating doctor, answered by the department (V2 items 4.2 / 4.3)
from tumour_board import scanned  # values and citations read from scans (V1 items 8.1, 8.2)
from tumour_board import skills  # agent role definitions as editable SKILL.md files (12 Oct)
from tumour_board import connectors, mcp_server  # MCP: hospital-system connectors (client) and the read-only server (12 Oct)
from tumour_board import discord  # discordances between reports, decision watch (12 Oct)
from tumour_board import fhir_export  # FHIR R4 document bundle and the HBCR registry abstract (12 Oct)
from tumour_board import home  # a home per role (V2 item 7.1)
from tumour_board import metrics  # agenda readiness, chase list, quality dashboard (12 Oct)
from tumour_board import accounts  # department admins create / disable / remove doctor logins; root admin accounts (V2 item 2.2)
from tumour_board import his_case, his_client  # HIS-connected Case Files: create from a UHID, re-fetch, link registrations, outside reports (V2 items 3.1 to 3.6)
from tumour_board import access  # who may open a Case File and act on it: owner, participants, the departments asked (V2 item 5.1)
from tumour_board import referral  # refer a Case File to another treating department: request, accept (ownership moves, new protocol), decline (V2 item 5.2)
from tumour_board import decision_record  # the decision record fields, choices and limits (night-v3 item 3.1)
from tumour_board import pacs  # the image viewer (OHIF) and DICOMweb reached through the app only: logged in, granted per study, audited (V2 item 6.3)
from tumour_board.api import common as _common
from tumour_board import case_summary as _case_summary  # the summary line only for readers of the whole Case File (item 3.4)  # the idle timeout and the JSON body cap (security review #11, #19)

log = logging.getLogger("tumour_board")


from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse


import re as _re
_READ_CASE = _re.compile(r"^/api/tb/(cases|sessions|intake|metrics)(/|$)")  # routes that show patient data: a placed account only
_CASE_PATH = _re.compile(r"^/api/tb/cases/([^/]+)(/.*)?$")  # one Case File: its owner, participants, the coordinator and the departments asked (V2 item 5.1)
_LIMITED_OK = ((("GET",), _re.compile(r"^$")), (("GET",), _re.compile(r"^/documents/[^/]+(/file|/quote)?$")),  # read only: a delete is never in scope (review Phase 5 S1); /quote = highlight boxes on a record in scope
               (("POST",), _re.compile(r"^/documents/[^/]+/images$")),  # Open images on a record in its scope (V2 item 6.3, Phase 6 review M2)
               (("POST",), _re.compile(r"^/requests/[^/]+/(acknowledge|done)$")), (("POST",), _re.compile(r"^/actions/[^/]+(/close|/dismiss-suggestion)?$")))  # what a department that was only asked may call


# What an account that still carries its first (or reset) password may call: who am I, and change the password.
_PASSWORD_FIRST_OK = _re.compile(r"^/api/tb/(me|me/password|health)$")
# Guest reviewers (org.json real_data, 5 Nov 2026) work with anonymized real files: two-factor sign-in first (TB_REAL_DATA_2FA=0
# turns the rule off for tests), and on a site with TB_UPLOAD_POLICY=private_only only they upload, into their own private Case Files.
_TWO_FACTOR_FIRST_OK = _re.compile(r"^/api/tb/(me|me/password|me/profile|health)$")
# What a guest reviewer never reaches: intake (department uploads and new Case Files from them), demo imports, referrals and the
# hospital system of a Case File (5 Nov 2026 review: these made ordinary, visible Case Files or showed a private one to others).
_GUEST_NEVER = _re.compile(r"^/api/tb/(intake|demo|his)(/|$)|^/api/tb/cases/[^/]+/(referrals|his)(/|$)")
_CASE_ID_OK = _re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")


def _upload_policy() -> str:
    return "private_only" if __import__("os").getenv("TB_UPLOAD_POLICY", "all").strip().lower() == "private_only" else "all"


def _upload_allowed(rl, c) -> bool:
    """A guest reviewer uploads only into a private Case File it created, on every site; under private_only that is the only upload there is.
    Otherwise no extra rule (the route's own checks apply)."""
    if _upload_policy() != "private_only" and not rl.get("real_data"):
        return True
    return bool(rl.get("real_data")) and config.is_private((c or {}).get("case_id")) and access.is_creator(rl, c or {})


def _needs_two_factor(rl, mgr, u) -> bool:
    if not rl.get("real_data") or __import__("os").getenv("TB_REAL_DATA_2FA", "1").strip() == "0":
        return False
    fn = getattr(mgr, "totp_enabled", None) if mgr is not None else None
    try:
        return not (callable(fn) and fn(u))
    except Exception:  # unknown: closed
        return True

# What a Vaidyx admin, or a doctor who opened the Case File with a reason (scope READ, night-v3 item 1.9), may send inside a window
# besides reading (security review #6): questions that change nothing and opening the images of a record (viewing). Everything else
# that writes is refused: the window is read only.
_BREAK_GLASS_OK = _re.compile(r"^/(ask|search|published/search|documents/[^/]+/images|pubmed/ask|pubmed/PM[0-9a-f]{8}/pin)$")  # Ask PubMed: the meeting window's members ask (its route refuses the other windows)

# What an archived Case File still accepts besides reading: taking it out of the archive, and questions that change nothing.
_ARCHIVE_OK = _re.compile(r"^/(unarchive|archive|ask|search|chats|published/search|helpers/[^/]+/chat|documents/[^/]+/images|pubmed/ask)$")  # Ask PubMed like the records chat


MEETING_SCOPE = "meeting"  # one record open on the shared screen of a running meeting, for its admitted members (read only, that record only)
_MEETING_FILE = _re.compile(r"^/documents/([^/]+)/file$")


def _meeting_record(rl, case_id, rest):
    """The meeting that shows this record on its shared screen to this admitted member (meetings.shows_record), else None."""
    m = _MEETING_FILE.match(rest or "")
    if not m:
        return None
    try:
        from tumour_board import meetings
        return meetings.shows_record(rl, case_id, m.group(1))
    except Exception:
        return None


def _case_guard(rl, case_id, rest, method="GET"):
    """The Case File scope of this user (access.FULL / access.REQUESTS / access.READ), or a 403 response. A Case File that does not exist is left to
    the route (404). A department that was only asked may read the Case File view (reduced by the route), open the records in its
    scope and answer its requests and actions; nothing else."""
    try:
        c = store.get_case(case_id)
    except (ValueError, OSError):
        return None
    if not c:
        return None
    sc = access.scope(rl, c)
    if sc is None and method == "GET" and _meeting_record(rl, case_id, rest):  # the record on a meeting's shared screen, for its admitted members
        return MEETING_SCOPE
    if sc is None and config.is_private(c.get("case_id")):  # a guest reviewer's private Case File does not exist for anyone else
        return JSONResponse({"detail": "Case not found"}, status_code=404)
    if sc is None:  # break_glass: this doctor may open the Case File read-only with a reason (night-v3 item 1.9, POST /break-glass)
        return JSONResponse({"detail": {"message": access.refusal(rl, c), "code": "no_access", "break_glass": access.may_open_with_reason(rl, c)}},
                            status_code=403)
    if sc == access.REQUESTS and not any(method in ms and p.match(rest or "") for ms, p in _LIMITED_OK):
        return JSONResponse({"detail": "Your department sees only the items it was asked about in this Case File."}, status_code=403)
    return sc


_SESSION_COOKIE = "vaidyx_session"  # the main app's session cookie (core/auth.py)


async def _json_too_big(request):
    """A 413 for a JSON (or other non-upload) body over 1 MB on a Tumour Board route (security review #19); uploads (multipart) keep
    their own limit. The body is read once here and kept for the route."""
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/"):
        return None
    message = {"detail": {"message": "The request is too large (over 1 MB).", "code": "too_large"}}
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _common.MAX_JSON_BYTES:
                return JSONResponse(message, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "The request has a bad Content-Length."}, status_code=400)
        return None
    chunks, n = [], 0
    async for chunk in request.stream():  # no length given (chunked): read up to the cap only
        n += len(chunk)
        if n > _common.MAX_JSON_BYTES:
            return JSONResponse(message, status_code=413)
        chunks.append(chunk)
    request._body = b"".join(chunks)
    return None


class _ModelErrorRoute(APIRoute):
    """Model-server problems become a clear 502 for the UI instead of a 500 stack trace. A login whose Tumour Board access is disabled
    (org.json `disabled`, V2 item 2.2) is refused on every Tumour Board route, whatever the route checks itself."""
    def get_route_handler(self):
        h = super().get_route_handler()

        async def handler(request):
            # Cross-site request forgery: a browser always sends Origin on a cross-site POST; when it is present it must be this
            # app's own origin (host and port). Non-browser clients (tests, scripts) send no Origin and are not affected.
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                origin = request.headers.get("origin")
                if origin:
                    host = request.headers.get("host", "")
                    if origin.split("://", 1)[-1].rstrip("/") != host:
                        return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
                too_big = await _json_too_big(request)
                if too_big:
                    return too_big
            try:
                u = get_current_user(request)
                if u and _common.idle_expired(request.cookies.get(_SESSION_COOKIE), touch=request.headers.get(_common.BACKGROUND_HEADER) != "1"):
                    return JSONResponse({"detail": {"message": "You were away for more than 8 hours, so you were signed out of the Tumour Board. Please sign in again.",
                                                    "code": "idle_timeout"}}, status_code=401)  # security review #11
                if u:
                    rl = _roles(request)
                    if rl.get("disabled"):
                        return JSONResponse({"detail": "Your Tumour Board access is disabled. Ask your department admin or the root admin."}, status_code=403)
                    mgr = getattr(request.app.state, "auth_manager", None)
                    if (mgr is not None and callable(getattr(mgr, "must_change_password", None)) and mgr.must_change_password(u)
                            and not _PASSWORD_FIRST_OK.match(request.url.path)):  # a first or reset password works only to choose a new one
                        return JSONResponse({"detail": {"message": "Choose your own password first.", "code": "password_change_required"}}, status_code=409)
                    if rl.get("real_data") and _GUEST_NEVER.match(request.url.path):
                        return JSONResponse({"detail": {"message": "A guest reviewer works only in their own private Case Files.", "code": "guest_scope"}}, status_code=403)
                    if _needs_two_factor(rl, mgr, u) and not _TWO_FACTOR_FIRST_OK.match(request.url.path):
                        return JSONResponse({"detail": {"message": "Turn on two-factor sign-in first (Settings, Security): this account works with real, anonymized files.",
                                                        "code": "two_factor_required"}}, status_code=409)
                    if _READ_CASE.match(request.url.path) and not org.can(rl, "read_case"):  # patient data only for placed accounts (review M6)
                        return JSONResponse({"detail": "Your account is not placed in any department yet, so it cannot open Case Files. Ask a Tumour Board admin."}, status_code=403)
                    m = _CASE_PATH.match(request.url.path)
                    if m and not _CASE_ID_OK.match(m.group(1)):
                        return JSONResponse({"detail": "Case not found"}, status_code=404)
                    if m and m.group(1) != "from-his":  # one Case File: owner, participants, coordinator, the departments asked (V2 item 5.1)
                        sc = _case_guard(rl, m.group(1), m.group(2), request.method)
                        if isinstance(sc, JSONResponse):
                            return sc
                        request.state.tb_scope = sc
                        if ((rl.get("vaidyx_admin") or sc == access.READ) and request.method in ("POST", "PUT", "PATCH", "DELETE")
                                and not _BREAK_GLASS_OK.match(m.group(2) or "")):  # a window (the admin's, or a doctor's opened with a reason) only reads
                            msg = ("A break-glass window is read only: the Vaidyx admin reads the Case File, the owning department acts on it."
                                   if rl.get("vaidyx_admin") else access.READ_ONLY_MESSAGE
                                   if access._doctor_open(rl, store.get_case(m.group(1)) or {}) else access.MEETING_READ_MESSAGE)  # the meeting window (meetings-v2 2.2)
                            return JSONResponse({"detail": {"message": msg, "code": "break_glass_read_only"}}, status_code=403)
                        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _ARCHIVE_OK.match(m.group(2) or ""):
                            try:
                                archived = access.is_archived(store.get_case(m.group(1)))
                            except (ValueError, OSError):
                                archived = False
                            if archived:  # archived instead of deleted (18 Oct): readers keep reading, nothing changes until unarchived
                                return JSONResponse({"detail": {"message": access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", "code": "archived"}}, status_code=403)
            except Exception as e:  # the organisation file is unreadable: a Case File path is refused (never open), the other routes keep their own checks
                log.warning("tumour board route guard failed (%s)", e)
                if _CASE_PATH.match(request.url.path):
                    return JSONResponse({"detail": "The organisation file could not be read; try again or ask the Vaidyx admin."}, status_code=503)
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


def _need_case(r, action, c, department=None):
    """One permission check on a Case File: org.can() plus the owner rule (V2 item 5.1); a refusal is a 403 with a plain message."""
    try:
        access.require(r, action, c, department)
    except PermissionError as e:
        raise HTTPException(403, str(e))


def _scope(request):
    return getattr(request.state, "tb_scope", None) or access.FULL


def _need_known(r):
    """Model calls and re-checks are for users the hospital set-up knows (a department member, head, coordinator or admin)."""
    if r.get("disabled"):
        raise HTTPException(403, "Your Tumour Board access is disabled. Ask your department admin or the root admin.")
    if not (r.get("admin") or r.get("known")):
        raise HTTPException(403, "Your account is not placed in any department yet. Ask a Tumour Board admin.")


def _auth_manager(request):
    mgr = getattr(request.app.state, "auth_manager", None)
    if mgr is None:
        raise HTTPException(503, "The Vaidyx login system is not available; accounts cannot be managed right now.")
    return mgr


def _account_limits():
    """The main app's password rule and reserved names (read here, never changed)."""
    try:
        from src.constants import PASSWORD_MIN_LENGTH
        from core.auth import RESERVED_USERNAMES
        return {"reserved": RESERVED_USERNAMES, "min_length": PASSWORD_MIN_LENGTH}
    except Exception:
        return {"reserved": ("api", "demo", "system", "internal-tool"), "min_length": accounts.PASSWORD_MIN}


def _account_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except accounts.AccountError as e:
        raise HTTPException(e.status, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# Originals shown in the browser as they are: PDFs and the raster images the viewer draws. Anything else (an uploaded .xml, .html, .svg,
# .txt, an office file) is sent as a download with a neutral type and a sandbox policy, so it never runs on this origin (security
# review #10). The main app's CSP stays as it is (its pages load scripts from cdn.jsdelivr.net).
_INLINE_ORIGINALS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
_SAFE_NAME = _re.compile(r"[^A-Za-z0-9._ -]+")


def _original_response(p, filename=""):
    from pathlib import Path as _P
    p = _P(p)
    ext = p.suffix.lower()
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
    if ext in _INLINE_ORIGINALS:
        return FileResponse(p, media_type=_INLINE_ORIGINALS[ext], headers=headers)
    name = _SAFE_NAME.sub("_", _P(str(filename or "")).name or p.name).strip(" .") or ("original" + ext)
    headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return FileResponse(p, media_type="application/octet-stream", filename=name, content_disposition_type="attachment", headers=headers)


def _doc_department(d):
    """The department whose member may confirm or delete this document as its own upload (department uploads, V1 item 2.3): None for
    coordinator uploads and for hospital-system records, whose `department` is the department that performed the test and gives it no
    right on the Case File (review Phase 5 S1)."""
    d = d or {}
    return None if d.get("his") else d.get("department")


def _private_upload_check(case_id, data, user, anonymized, confirm, reason):
    """(cleaned data, per-file upload record, None) or (.., .., JSONResponse refusal) for an upload into a private Case File.
    The uploader confirms the files are anonymized; refused types and dangerous files stop the whole upload; likely identifiers
    stop it until the uploader chooses "upload anyway" with a reason (both audited, the values never: masked samples only)."""
    from tumour_board import upload_safety
    if str(anonymized).strip() != "1":
        return data, None, JSONResponse({"detail": {"message": "Confirm that these files are anonymized (no name, phone, Aadhaar, address or hospital id).",
                                                    "code": "confirm_anonymized"}}, status_code=400)
    checked = [upload_safety.check(rel, b) for rel, b in data]
    refused = [{"file": c.name, "reason": c.refused} for c in checked if c.refused]
    if refused:  # the uploader sees the names; the audit keeps the position and the type only (a file name can carry a name)
        store.audit(case_id, {"kind": "private_upload_refused", "by": user,
                              "files": [{"n": i + 1, "type": c.ext, "reason": c.refused} for i, c in enumerate(checked) if c.refused]})
        return data, None, JSONResponse({"detail": {"message": "Some files cannot be uploaded.", "code": "upload_refused", "files": refused}}, status_code=415)
    findings = [{"file": c.name, **f} for c in checked for f in c.findings]
    why = str(reason or "").strip()[:500]
    if findings and str(confirm).strip() != "1":
        store.audit(case_id, {"kind": "private_upload_identifiers", "by": user,
                              "found": [{"n": next(i + 1 for i, c in enumerate(checked) if c.name == x["file"]), "kind": x["kind"], "where": x["where"]} for x in findings]})
        return data, None, JSONResponse({"detail": {"message": "These files may still identify the patient.", "code": "possible_identifiers",
                                                    "findings": findings}}, status_code=409)
    if findings and len(why) < 5:
        return data, None, JSONResponse({"detail": {"message": "Give a short reason for uploading anyway.", "code": "reason_required"}}, status_code=400)
    now = store.now_iso()
    start = len(store.list_docs(case_id))
    stored = [f"record-{start + i + 1}{c.ext}" for i, c in enumerate(checked)]  # neutral names: the uploaded name may carry a name
    meta = {stored[i]: {"uploaded": {"by": user, "at": now, "anonymized_by_uploader": True, "cleaned": c.notes,
                                  "text_checked": c.text_checked,
                                  "identifiers_at_upload": [{"kind": f["kind"], "where": f["where"]} for f in c.findings],
                                  **({"upload_anyway_reason": why} if c.findings else {})}} for i, c in enumerate(checked)}
    store.audit(case_id, {"kind": "private_upload", "by": user, "files": len(checked), "anonymized_confirmed": True,
                          **({"upload_anyway": True, "reason": why, "kinds": sorted({x["kind"] for x in findings})} if findings else {})})
    return [(stored[i], c.data) for i, c in enumerate(checked)], meta, None


def _case_permissions(r, c, st, docs):
    """What this user may do on this Case File, so the UI can hide forbidden actions (the routes still enforce them)."""
    prot = protocol.get(c["protocol"]) if c.get("protocol") else {"mandatory": []}
    own = access.may(r, "upload_to_case", c)  # the owner's doctors (any treating doctor on a Case File without an owner), V2 item 5.1
    mine_private = config.is_private(c.get("case_id")) and access.is_creator(r, c)  # a guest reviewer's own private Case File
    return {"upload": own and _upload_allowed(r, c), "reprocess": own, "delete_case": org.can(r, "delete_case") or mine_private,
            "refetch": bool(c.get("his")) and own, "link_registration": bool(c.get("his")) and own,  # V2 items 3.2 / 3.5
            "board_record": org.can(r, "board_record"), "review": org.can(r, "review"), "list_case": access.may_list(r, c),
            "waive": {q["id"]: access.may(r, "waive", c, q.get("department") or None) for q in prot.get("mandatory", [])},
            "confirm": {d["doc_id"]: access.may(r, "confirm", c, _doc_department(d)) for d in docs},
            "delete_document": {d["doc_id"]: access.may(r, "delete_document", c, _doc_department(d)) for d in docs},
            "unfile": {d["doc_id"]: bool(d.get("intake")) and org.can(r, "match") for d in docs},
            "update_action": {a["id"]: org.can(r, "update_action", a.get("department") or None) for a in st.get("actions", [])},
            "send_request": access.may(r, "send_request", c), "create_request": access.may(r, "create_request", c), "close_request": access.may(r, "close_request", c),  # V2 item 4.2
            "refer": access.may(r, "refer", c) and not access.open_referral(c), "manage_participants": access.may(r, "manage_participants", c),  # V2 items 5.1 / 5.2
            "answer_referral": bool(access.open_referral(c)) and org.can(r, "answer_referral", (access.open_referral(c) or {}).get("to")),
            "withdraw_referral": bool(access.open_referral(c)) and access.may(r, "refer", c),
            "set_owner": not access.owner(c) and org.can(r, "create_case"),
            "mark_ready": access.may(r, "mark_ready", c), "remind": access.may_remind(r, c),  # V2 item 6.1
            "answer_request": {a["id"]: _can_answer(r, a) for a in st.get("actions", []) if a.get("source") == "pre_authorization"},  # V2 item 4.3
            "undo_confirmation": {x["id"]: _can_confirm(r, c, st, x["type"], x["key"]) for x in st.get("confirmations", []) if not x.get("undone")},
            "correct_board_record": {b["id"]: _may_correct_record(r, c, b) for b in st.get("board_records", []) if isinstance(b, dict) and b.get("id")}}  # night-v3 item 3.2


def _correct_refusal(r, c, rec) -> str:
    """Why this user may not correct this board record ("" when allowed; night-v3 items 3.1 / 3.2): the owning department's consultants,
    or the MDT Coordinator on the record's board date only; nobody on an archived Case File. The correct route and the Case File
    permissions both read this, so the two cannot drift."""
    if access.is_archived(c):
        return access.ARCHIVED_MESSAGE + ". Take it out of the archive first."
    if access.is_owner_doctor(r, c):
        return ""
    if not r.get("coordinator") or r.get("disabled"):
        return "Only the owning department's consultants can correct a board record"
    import datetime as _dt
    if str((rec or {}).get("board_date") or "")[:10] != _dt.date.today().isoformat():
        return "The MDT Coordinator can correct a record on the meeting day only; afterwards the owning consultant corrects it"
    return ""


def _may_correct_record(r, c, rec) -> bool:
    return not _correct_refusal(r, c, rec)


def _can_answer(r, a):
    """Acknowledge / "done" on a request: the doctors of the department it went to; the coordinator for a request addressed to the
    MDT Coordinator role (V2 item 4.3)."""
    if a.get("role") == "coordinator" or org.is_coordinator_name(a.get("department_id")) or (not a.get("department_id") and org.is_coordinator_name(a.get("department"))):
        return org.can(r, "answer_request", None)  # no department: the coordinator's row (ACTIONS no_dept)
    return org.can(r, "answer_request", a.get("department_id") or a.get("department") or None)


def _can_confirm(r, c, st, ctype, key):
    """May this user record / undo a confirmation of this type on this key (same rule as the route, as a boolean)."""
    spec = confirm.TYPES.get(ctype)
    if not spec:
        return False
    if ctype == "waive":
        dept = next((q.get("department") for q in protocol.get(c["protocol"]).get("mandatory", []) if q["id"] == key), "") if c.get("protocol") else ""
        return access.may(r, "waive", c, dept or None)
    if spec["target"] in ("document", "fact"):
        doc_id = key.partition(":")[0] if spec["target"] == "fact" else key
        d = store.get_doc(c["case_id"], doc_id) if doc_id else None
        if ctype == "confirm_match":
            return access.may(r, "confirm", c, _doc_department(d)) if (d or {}).get("outside") else org.can(r, "match")  # an outside report: the treating doctor confirms the patient (V2 item 3.6)
        return access.may(r, spec["action"], c, _doc_department(d))
    if ctype == "resolve_flag":
        return org.can(r, "board_record")
    return access.may(r, spec["action"], c)


def _case(case_id):
    try:
        c = store.get_case(case_id)
    except ValueError:
        raise HTTPException(404, "Case not found")
    if not c:
        raise HTTPException(404, "Case not found")
    return c


def _reader_case(request, c):
    """The case record as this reader may see it: the summary line (clinical text, night-v3 item 3.4) only for a reader of the whole Case
    File or a break-glass reader of it (Phase 3 follow-up review S2)."""
    from tumour_board import case_summary as _cs
    if not isinstance(c, dict) or "summary_line" not in c:
        return c
    try:
        sc = access.scope(_roles(request), c)
    except Exception:
        sc = None
    return _cs.case_for(c, sc, also=(access.READ,))


def _state_view(st):
    """The state as the Case File view sends it (Phase 3 review N4): the Case summary as {current, case_id, versions (the list of versions),
    version (the current one)} and the pre-board summary history as {generated, archived_at, review} per version; the full versions stay
    on disk and come through GET /cases/{id}/case-summary?n=K and the steps view."""
    arts = st.get("artefacts") if isinstance(st.get("artefacts"), dict) else None
    if not arts or not (isinstance(arts.get("case_summary"), dict) or isinstance(arts.get("summary_history"), list)):
        return st
    from tumour_board import case_summary as _cs
    arts = dict(arts)
    if isinstance(arts.get("case_summary"), dict):
        a = arts["case_summary"]
        arts["case_summary"] = {"current": a.get("current"), "case_id": a.get("case_id"), "versions": _cs.history(st), "version": _cs.current(st)}
    if isinstance(arts.get("summary_history"), list):
        arts["summary_history"] = [{"generated": h.get("generated"), "archived_at": h.get("archived_at"), "review": h.get("review")}
                                   for h in arts["summary_history"] if isinstance(h, dict)]
    return {**st, "artefacts": arts}


def _history(h):
    """Earlier turns sent with a question: a list of {"role": user | assistant, "content": text}; anything else is ignored."""
    return [x for x in h if isinstance(x, dict) and x.get("role") in ("user", "assistant") and isinstance(x.get("content"), str)][-4:] if isinstance(h, list) else None


def _warm():
    import logging, threading
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    threading.Thread(target=lambda: guidelines.index(), daemon=True, name="tb-guideline-warmup").start()


def _include_nik_routers(r):
    """The routers of the new interface (tumour_board/api/*): each module exports `router`; a module that fails to import is logged
    and skipped so one broken area never takes the whole API down."""
    import importlib
    for name in ("me", "cases_list", "team", "patients", "setup", "slots", "steps", "staging", "chats", "helpers", "published", "meetings", "live", "video", "push", "deck", "meeting_pdf", "case_summary", "audio", "similar",
                 "messages", "messages_ws", "directory", "meeting_notes", "pubmed"):  # Phase 8: messages, their socket, the people directory; meetings-v2 5.1 / 5.3: the recorder and the notes; Ask PubMed
        try:
            mod = importlib.import_module(f"tumour_board.api.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"tumour_board.api.{name}":
                continue  # not built yet
            log.warning("tumour_board.api.%s not loaded: %s", name, e)
            continue
        except Exception as e:
            log.warning("tumour_board.api.%s not loaded: %s", name, e)
            continue
        sub = getattr(mod, "router", None)
        if sub is not None:
            r.include_router(sub)


def setup_tumour_board_routes():
    _warm()
    try:
        from tumour_board import access_log
        access_log.install()  # Phase 8 review: no search words in the access log
    except Exception as e:
        log.warning("access log filter not installed: %s", e.__class__.__name__)
    r = APIRouter(prefix="/api/tb", tags=["tumour-board"], route_class=_ModelErrorRoute)
    _include_nik_routers(r)

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
        _need_case(rl, "upload_to_case", _case(case_id))  # records enter a Case File through its owning department's doctors (V2 item 5.1, review Phase 5 M5)
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
        out = metrics.agenda(iso or store.now_iso()[:10])
        if not org.board_wide(rl):  # a doctor (and the Vaidyx admin, review #2) sees the readiness of the Case Files it may open (V2 item 5.1, review Phase 5 M1)
            vis = {c["case_id"] for c in access.visible(rl, store.list_cases())}
            out["cases"] = [x for x in out["cases"] if x.get("case_id") in vis]
            out["counts"] = {k: sum(1 for x in out["cases"] if x.get("forecast") == k) for k in (out.get("counts") or {})}
            chase = []
            for d in out.get("chase") or []:
                items = [x for x in (d.get("items") or []) if x.get("case_id") in vis]
                if items:
                    chase.append({**d, "items": items, "overdue": sum(1 for x in items if x.get("overdue"))})
            out["chase"] = chase
        return out

    @r.get("/metrics/dashboard")
    async def metrics_dashboard(request: Request, start: str = "", end: str = "", format: str = "json"):
        """The hospital's Tumour Board quality dashboard: before, during and after the board, with reference lines (12 Oct)."""
        rl = _roles(request); _need(rl, "list_case")
        d = metrics.dashboard(start or None, end or None)
        if format == "csv":
            skills._audit({"kind": "dashboard_export", "by": rl["user"], "start": start, "end": end})  # org-level audit (Phase 0 review)
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
        if rl.get("disabled"):
            raise HTTPException(403, "Your Tumour Board access is disabled. Ask your department admin or the root admin.")
        o = org.load()
        out = {"hospital": o["hospital"], "departments": o["departments"], "me": rl, "my_departments": org.my_departments(rl),
               "inbox_departments": org.visible_departments_for_inbox(rl),  # whose department inbox this user may open (V1 item 4.4)
               "admin_departments": org.admin_departments(rl) if (rl["admin"] or rl.get("admin_of")) else [],  # V2 item 2.2
               "can": {k: org.can(rl, k) for k in ("create_case", "list_case", "session", "upload_to_case", "match", "manage_org", "board_record", "read_case")},
               "reset_note": accounts.RESET_NOTE, "version": org.version()}
        if rl["admin"] or rl.get("root_admin"):
            mgr = getattr(request.app.state, "auth_manager", None)
            out["users"], out["admins"], out["routes"] = o["users"], o["admins"], o["routes"]
            try:
                out["vaidyx_users"] = [{"username": x["username"], "is_admin": bool(x.get("is_admin"))} for x in mgr.list_users()] if mgr else []
            except Exception:
                out["vaidyx_users"] = []
        return out

    @r.get("/home")
    async def home_(request: Request):
        """The home of this login (V2 item 7.1): its sections by role (treating doctor, supporting doctor, MDT Coordinator, department
        admin, root admin) with what each needs first; nothing a role may not open elsewhere."""
        rl = _roles(request)
        if rl.get("disabled"):
            raise HTTPException(403, "Your Tumour Board access is disabled. Ask your department admin or the root admin.")
        return home.build(rl, mgr=getattr(request.app.state, "auth_manager", None))

    @r.post("/org/setup")
    async def org_setup(request: Request):
        """{"pmjay_empanelled": bool, "name"?, "level"?}: the root admin's first set-up, answered once (V2 item 7.1; plan section 11).
        409 once answered: the settings are then changed under Organisation. Audited."""
        rl = _roles(request); _need(rl, "manage_org")
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(400, 'Send {"pmjay_empanelled": true or false, "name"?, "level"?}')
        b = b if isinstance(b, dict) else {}
        try:
            h = org.first_setup(rl["user"], b.get("pmjay_empanelled"), name=b.get("name"), level=b.get("level") or None)
        except org.SetupDone as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "hospital": h, "version": org.version()}

    @r.delete("/org/setup")
    async def org_setup_clear(request: Request):
        """Root admin: re-open the first set-up (the home asks again). Audited. The stamp cannot be removed through PUT /org."""
        rl = _roles(request); _need(rl, "manage_org")
        return {"ok": True, "hospital": org.clear_first_setup(rl["user"]), "version": org.version()}

    @r.put("/org")
    async def put_org(request: Request):
        """Save the organisation. A key left out of the body (hospital, departments, users, admins, routes) keeps its current value, so a
        screen saves only what it edited and an older client never wipes the routes; `expected_version` (from GET /org) answers 409 when
        the file changed since it was read (review M2)."""
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        if not isinstance(b, dict):
            raise HTTPException(400, "The organisation must be an object.")
        want = b.pop("expected_version", None)
        if want and str(want) != org.version():
            raise HTTPException(409, "The organisation changed since this screen was loaded. Reload and apply your change again.")
        cur = org.load()
        body = {k: (b[k] if k in b else cur.get(k)) for k in ("hospital", "departments", "users", "admins", "routes")}
        body.update({k: v for k, v in b.items() if k not in body})
        try:
            mixed = accounts.mixed_logins(body) - accounts.mixed_logins(cur)
        except (AttributeError, TypeError):
            mixed = set()
        if mixed:  # a root admin never takes a clinical role, nor a clinical login the root admin role (security review #5)
            raise HTTPException(409, f"{accounts.SEPARATE_LOGINS}: {', '.join(sorted(mixed))}.")
        try:
            o = org.save(body, by=rl["user"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "hospital": o["hospital"], "departments": o["departments"], "users": o["users"], "admins": o["admins"], "routes": o["routes"], "version": org.version()}

    # ---- accounts (V2 item 2.2): plain Vaidyx logins placed in Tumour Board roles; never a Vaidyx admin ----
    @r.get("/org/audit")
    async def org_audit(request: Request, limit: int = 200):
        rl = _roles(request); _need(rl, "manage_org")
        return {"events": org.read_audit(max(1, min(limit, 1000)))}

    @r.get("/org/routes")
    async def org_routes(request: Request):
        """Root admin: every protocol record with the department it is requested from (the protocol default, the override, the effective
        department), for the routing table of the Organisation screen (V2 item 2.4). Overrides are saved through PUT /org (routes)."""
        rl = _roles(request); _need(rl, "manage_org")
        return {"routes": rules.routes_table(), "overrides": org.load().get("routes") or {},
                "targets": [{"id": d["id"], "name": d["name"], "group": d.get("group")} for d in org.departments()]
                           + [{"id": org.OWNER_ID, "name": org.OWNER_NAME + " (the Case File's treating department)", "group": None},
                              {"id": org.COORDINATOR_ID, "name": org.COORDINATOR_NAME, "group": None}]}

    @r.get("/org/accounts")
    async def org_accounts(request: Request):
        """Root admin: every Tumour Board placement with whether its Vaidyx account exists; Vaidyx admins listed as such, never placeable."""
        rl = _roles(request); _need(rl, "manage_org")
        mgr = getattr(request.app.state, "auth_manager", None)
        o = org.load()
        rows = []
        for u, v in sorted(o["users"].items()):
            rows.append({"username": u, **v, "root_admin": u in o["admins"], "account": accounts.account_exists(mgr, u) if mgr else None,
                         "vaidyx_admin": accounts.is_vaidyx_admin(mgr, u)})
        try:
            vaidyx = [{"username": x["username"], "is_admin": bool(x.get("is_admin")), "placed": x["username"] in o["users"]} for x in mgr.list_users()] if mgr else []
        except Exception:
            vaidyx = []
        return {"accounts": rows, "vaidyx_users": vaidyx, "admins": o["admins"], "reset_note": accounts.RESET_NOTE}

    @r.post("/org/accounts")
    async def create_account(request: Request):
        """Root admin: create (or find) a plain login and give it roles: coordinator, root admin, department admin, doctor."""
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        mgr = _auth_manager(request)
        out = _account_call(accounts.create_account, mgr, rl["user"], b.get("username"), b.get("password"), display_name=b.get("display_name") or "",
                            coordinator=b.get("coordinator", False), admin_of=b.get("admin_of") or [], departments=b.get("departments") or {},
                            root_admin=b.get("root_admin", False), **_account_limits())
        return {"ok": True, **out}

    @r.get("/org/departments/{dept}/doctors")
    async def department_doctors(dept: str, request: Request):
        rl = _roles(request)
        did = org.department_id(dept)
        if not did:
            raise HTTPException(404, "Unknown department")
        _need(rl, "manage_department", did)
        mgr = getattr(request.app.state, "auth_manager", None)
        return {"department": org.department(did), "doctors": accounts.department_doctors(did, mgr), "can_reset": False, "reset_note": accounts.RESET_NOTE}

    @r.post("/org/departments/{dept}/doctors")
    async def create_doctor(dept: str, request: Request):
        """Department admin: a new doctor login of this department (or an existing plain account placed here). Never a Vaidyx admin."""
        rl = _roles(request); b = await request.json()
        did = org.department_id(dept)
        if not did:
            raise HTTPException(404, "Unknown department")
        _need(rl, "manage_department", did)
        mgr = _auth_manager(request)
        _account_call(accounts.check_placement, did, b.get("role") or "member")  # before any login is created: no orphan account on a bad role
        made = _account_call(accounts.ensure_account, mgr, b.get("username"), b.get("password"), rl["user"], **_account_limits())
        placed = _account_call(accounts.place_doctor, rl["user"], did, made["username"], role=b.get("role") or "member", display_name=b.get("display_name"),
                               caller=rl, created=made["created"])
        return {"ok": True, "created": made["created"], **placed}

    @r.put("/org/departments/{dept}/doctors/{username}")
    async def update_doctor(dept: str, username: str, request: Request):
        rl = _roles(request); b = await request.json()
        did = org.department_id(dept)
        if not did:
            raise HTTPException(404, "Unknown department")
        _need(rl, "manage_department", did)
        out = _account_call(accounts.update_doctor, rl["user"], rl, did, username, role=b.get("role"), disabled=b.get("disabled"),
                            mgr=getattr(request.app.state, "auth_manager", None))
        return {"ok": True, **out}

    @r.delete("/org/departments/{dept}/doctors/{username}")
    async def remove_doctor(dept: str, username: str, request: Request):
        rl = _roles(request)
        did = org.department_id(dept)
        if not did:
            raise HTTPException(404, "Unknown department")
        _need(rl, "manage_department", did)
        return {"ok": True, **_account_call(accounts.remove_doctor, rl["user"], rl, did, username)}

    def _his_brief(c):
        h = c.get("his")
        if not h:
            return c
        return {**c, "his": {"label": h.get("label"), "uhid": h.get("uhid"), "registration_kind": h.get("registration_kind"), "fetched_at": h.get("fetched_at"),
                             "window_label": his_case.window_label(h.get("window") or {}), "unlinked": sum(1 for x in h.get("similar") or [] if not x.get("linked"))}}

    @r.get("/cases")
    async def cases(request: Request):
        rl = _roles(request)
        out = []
        for c in store.list_cases():  # only the Case Files this user may open (V2 item 5.1)
            sc = access.scope(rl, c)
            if sc and sc != access.READ:  # a Case File opened with a reason is never listed (item 1.9)
                out.append({**_his_brief(_case_summary.case_for(c, sc)), "scope": sc, "owner_name": org.department_name(access.owner(c)) if access.owner(c) else "",
                            "participants": access.participants(c), "linked": len(c.get("linked_cases") or []), "referral": (access.open_referral(c) or {}).get("to")})
        return {"cases": out, "demo": service.list_demo()}

    @r.post("/cases/{case_id}/owner")
    async def set_owner(case_id: str, request: Request):
        """{"department", "reason"?}: record the owning treating department of a Case File that has none (a manual or demo Case File).
        Once owned, ownership moves only through a referral (V2 item 5.2)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need(rl, "create_case")
        if access.owner(c):
            raise HTTPException(409, f"This Case File is owned by {org.department_name(access.owner(c))}; ownership moves through a referral.")
        b = await request.json() if (await request.body()) else {}
        try:
            c = access.set_owner(case_id, str((b or {}).get("department") or ""), u, reason=str((b or {}).get("reason") or ""), roles=rl)
        except access.AccessError as e:
            raise HTTPException(e.status, str(e))
        return {"case": _reader_case(request, c), "access": access.public(c)}

    @r.put("/cases/{case_id}/participants")
    async def participants(case_id: str, request: Request):
        """{"add": [departments], "remove": [departments], "reason"?}: the owning department's doctors choose who takes part (read and
        comment). Audited; an added department is told."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "manage_participants", c)
        b = await request.json() if (await request.body()) else {}
        b = b if isinstance(b, dict) else {}
        reason = str(b.get("reason") or "")
        try:
            async with store.lock(case_id):
                for d in b.get("add") or []:
                    c = access.add_participant(case_id, str(d), u, reason)
                for d in b.get("remove") or []:
                    c = access.remove_participant(case_id, str(d), u, reason)
        except access.AccessError as e:
            raise HTTPException(e.status, str(e))
        return {"case": _reader_case(request, store.get_case(case_id)), "access": access.public(store.get_case(case_id))}

    # ---- HIS-connected Case Files (V2 items 3.1, 3.2, 3.5): the hospital information system, lookup, create from a UHID, re-fetch ----
    def _his_call(coro):
        async def run():
            try:
                return await coro
            except his_case.DuplicateCaseFile:  # the route answers its structured body (night-v3 item 1.1)
                raise
            except his_case.HISCaseError as e:
                raise HTTPException(e.status, str(e))
            except his_client.HISError as e:
                raise HTTPException(502, f"The hospital system did not answer: {e}")
        return run()

    @r.get("/his")
    async def his_info(request: Request):
        """The configured hospital information system (never its token) and whether it answers; settings for root admins."""
        rl = _roles(request); _need_known(rl) if not org.can(rl, "manage_org") else None
        cfg = his_client.settings()
        out = {"settings": his_client.public(cfg, manager=org.can(rl, "manage_org")), "can_manage": org.can(rl, "manage_org"), "can_create": org.can(rl, "create_case"),
               "remote_allowed": bool(rl.get("admin")) or bool(his_client.allowed_hosts()),
               "treating_departments": [{"id": d["id"], "name": d["name"]} for d in org.departments("treating") if rl.get("admin") or d["id"] in (rl.get("treating") or {})],
               "window_months": list(his_case.WINDOW_MONTHS), "default_window": his_case.default_window()}
        c = his_client.client()
        if c is None:
            out["status"] = {"ok": False, "error": "No hospital information system is configured or it is disabled"}
        else:
            try:
                out["status"] = await c.ping()
            except Exception as e:
                out["status"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
        return out

    @r.put("/his")
    async def his_save(request: Request):
        rl = _roles(request); _need(rl, "manage_org"); b = await request.json()
        try:  # only a Vaidyx admin may point the connection outside this server; the token file is never taken from the request (review S2)
            return {"ok": True, "settings": his_client.save_settings(b if isinstance(b, dict) else {}, by=rl["user"], allow_remote=bool(rl.get("admin")))}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.get("/his/lookup")
    async def his_lookup(request: Request, identifier: str = "", months: str = "", all: int = 0, from_date: str = ""):
        """Before creating: the registration a UHID, IP No. or OP No. resolves to, its encounters, how many records fall inside the
        window, and the registrations that may be the same person (for a person to link, never merged)."""
        rl = _roles(request); _need(rl, "create_case")
        window = {"all": True} if all else ({"from": from_date} if from_date else ({"months": months} if months else None))
        out = await _his_call(his_case.lookup(identifier, window))
        org.audit("his_lookup", rl["user"], identifier=str(identifier or "")[:60], found=bool(out.get("found")), uhid=(out.get("patient") or {}).get("uhid"))  # a patient lookup is a user action (review M11)
        return out

    @r.post("/cases/from-his")
    async def create_from_his(request: Request):
        """A treating doctor creates a Case File from a UHID (or an IP / OP No.): {"identifier", "protocol", "setting"?, "hospital_level"?,
        "board_date"?, "window"?: {"months" | "all" | "from"}, "department"? (the owning treating department when the doctor has several
        or the caller is an admin), "case_id"?, "cancer_name"? (the cancer as picked or typed, 2 to 80 characters; required with protocol
        "generic", the four core records of a cancer with no checklist yet)}. The first fetch runs as a job."""
        u = _user(request); rl = _roles(request); _need(rl, "create_case"); b = await request.json()
        if rl.get("real_data"):
            raise HTTPException(403, "A guest reviewer creates a Case File from their own files (New Case File, without the hospital system).")
        if not isinstance(b, dict):
            raise HTTPException(400, "Send the identifier and the protocol")
        try:
            out = await _his_call(his_case.create(str(b.get("identifier") or ""), str(b.get("protocol") or ""), str(b.get("setting") or ""), str(b.get("hospital_level") or ""),
                                                  str(b.get("board_date") or ""), b.get("window"), u, rl, department=b.get("department"), case_id=str(b.get("case_id") or ""),
                                                  cancer_name=b.get("cancer_name")))
        except his_case.DuplicateCaseFile as e:  # one Case File per patient and cancer: 409 with the existing file's owner (night-v3 item 1.1)
            return JSONResponse(e.body(), status_code=409)
        job = out["job"]
        return {"case": out["case"], "job": job["id"], "total": job["total"], "his": job.get("his")}

    @r.post("/cases/{case_id}/his/refetch")
    async def his_refetch(case_id: str, request: Request):
        """Re-fetch from the HIS (V2 item 3.5): only records new or changed since the last fetch; the gate re-checks and requests whose
        record arrived final and signed close themselves."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "upload_to_case", c)
        job = await _his_call(his_case.refetch(case_id, u))
        return {"job": job["id"], "total": job["total"], "his": job.get("his")}

    @r.post("/cases/{case_id}/his/link")
    async def his_link(case_id: str, request: Request):
        """A person links a possible duplicate or temporary registration ({"uhid", "reason"?}); its records join the Case File labelled
        with that registration. Never automatic (plan 3.2)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "upload_to_case", c); b = await request.json()
        job = await _his_call(his_case.link_registration(case_id, str((b or {}).get("uhid") or ""), u, str((b or {}).get("reason") or "")))
        return {"job": job["id"], "total": job["total"], "his": job.get("his"), "case": _reader_case(request, store.get_case(case_id))}

    @r.post("/cases/{case_id}/his/unlink")
    async def his_unlink(case_id: str, request: Request):
        """Undo a link ({"uhid", "reason"}): the registration's records leave the Case File and the identifiers learned from it are forgotten (audited)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "upload_to_case", c); b = await request.json()
        async with store.lock(case_id):
            try:
                out = his_case.unlink_registration(case_id, str((b or {}).get("uhid") or ""), u, str((b or {}).get("reason") or ""))
            except his_case.HISCaseError as e:
                raise HTTPException(e.status, str(e))
            st = service.recheck(case_id, u)
        return {"ok": True, **out, "state": st, "case": _reader_case(request, store.get_case(case_id))}

    @r.post("/cases/{case_id}/his/fetch-older")
    async def his_fetch_older(case_id: str, request: Request):
        """Widen the fetch window ({"months" | "all" | "from"}) without starting over (plan 3.2)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "upload_to_case", c); b = await request.json() if (await request.body()) else {}
        job = await _his_call(his_case.fetch_older(case_id, b if isinstance(b, dict) else {}, u))
        return {"job": job["id"], "total": job["total"], "his": job.get("his"), "case": _reader_case(request, store.get_case(case_id))}

    @r.post("/cases")
    async def create(request: Request):
        u = _user(request); rl = _roles(request); _need(rl, "create_case"); b = await request.json()
        if not isinstance(b, dict):
            raise HTTPException(400, "Send the Case File details")
        private = bool(rl.get("real_data"))  # a guest reviewer: always a new private Case File with an id the server picks
        if private:
            b["case_id"] = "PRV-" + __import__("secrets").token_hex(4).upper()
        prot = b.get("protocol") or ""
        owner_dept = None  # the owning treating department (V2 item 5.1): named in the request, else the creator's own; the coordinator may leave it open (V1 path)
        if b.get("department") or (rl.get("treating") and not rl.get("admin") and not rl.get("coordinator")):
            try:
                owner_dept = his_case._owner_department(rl, b.get("department"))
            except his_case.HISCaseError as e:
                raise HTTPException(e.status, str(e))
        if prot and not protocol.exists(prot):
            raise HTTPException(400, f"Unknown protocol: {prot}")
        if b.get("setting") and (not prot or b["setting"] not in {x["id"] for x in protocol.settings(prot)}):
            raise HTTPException(400, f"Unknown NCG setting: {b['setting']}")
        level = b.get("hospital_level") or ((org.load().get("hospital") or {}).get("level") if prot else "")
        if level and level not in org.LEVELS:
            raise HTTPException(400, "Hospital level must be essential or optimal")
        try:  # the cancer as picked or typed; required with protocol "generic" (a cancer with no checklist yet, owner decision R05-Q04)
            cancer_name = his_case.clean_cancer_name(b.get("cancer_name"), prot)
        except his_case.HISCaseError as e:
            raise HTTPException(e.status, str(e))
        pat = b.get("patient") if isinstance(b.get("patient"), dict) else {}
        try:  # one Case File per patient and cancer (night-v3 item 1.1): the UHID given, and any UHID among the identifiers
            his_case.refuse_duplicate(his_case.case_uhids({"patient": pat}), prot, cancer_name, u, rl, via="manual")
        except his_case.DuplicateCaseFile as e:
            return JSONResponse(e.body(), status_code=409)
        if private:  # the marker goes in before case.json, so there is no moment in which the Case File is visible to others
            d = store.case_dir(b["case_id"])
            if d.exists():
                raise HTTPException(409, "Please try again.")
            d.mkdir(parents=True)
            (d / config.PRIVATE_MARKER).write_text(json.dumps({"by": u, "at": store.now_iso()}))
        try:
            c = store.create_case(store.safe_id(b["case_id"]), b.get("patient", {}), prot, b.get("board_date", ""), u, b.get("setting", ""), level or "")
        except FileExistsError:
            raise HTTPException(409, "Case already exists")
        if owner_dept or cancer_name or private:
            if owner_dept:
                c["department"] = owner_dept
            if cancer_name:
                c["cancer_name"] = cancer_name
            if private:
                c["private"] = True
            store.save_case(c)
        store.audit(c["case_id"], {"kind": "case_created", "by": u, "listing": c["listing"]["status"], "protocol": prot, "setting": c.get("setting"), "owner": owner_dept,
                                   **({"private": True} if private else {}),
                                   **({"cancer_name": cancer_name} if cancer_name else {})})
        return c

    @r.post("/cases/{case_id}/listing")
    async def list_case(case_id: str, request: Request):
        """The coordinator lists the Case File for the board (V1 item 2.5): {"protocol", "setting", "board_date", "hospital_level"}.
        Pre-Authorization starts when listed (fields extracted from the stored pages, gate evaluated)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); b = await request.json()
        if not access.may_list(rl, c):  # the MDT Coordinator, or the owning department's doctors (the new owner picks the protocol after a referral, V2 item 5.2)
            raise HTTPException(403, "Only the MDT Coordinator or the doctors of the owning department change the listing of this Case File.")
        try:  # one Case File per patient and cancer (night-v3 item 1.1): listing after intake is where the cancer is chosen
            system = (c["his"].get("kind"), c["his"].get("label")) if isinstance(c.get("his"), dict) else None
            his_case.refuse_duplicate(his_case.case_uhids(c), str(b.get("protocol", "")), str(c.get("cancer_name") or ""), u, rl, his=system, via="listing", exclude=case_id)
        except his_case.DuplicateCaseFile as e:
            return JSONResponse(e.body(), status_code=409)
        try:
            job = service.list_case(case_id, str(b.get("protocol", "")), str(b.get("setting", "") or ""), str(b.get("board_date", "") or ""), str(b.get("hospital_level", "") or ""), u)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"job": job["id"], "total": job["total"], "case": _reader_case(request, store.get_case(case_id))}

    @r.delete("/cases/{case_id}")
    async def delete(case_id: str, request: Request):
        u = _user(request); rl = _roles(request); c = _case(case_id)
        private = config.is_private(c["case_id"])
        if not (private and access.is_creator(rl, c)):  # a guest reviewer deletes their own private Case File; others need delete_case
            _need(rl, "delete_case")
        n = notify.purge_case(case_id)  # its notifications carry the patient's name: they go with the Case File (V1 item 4.4)
        linked = his_case.unlink_cases(case_id, u)  # the same patient's other Case Files forget the link (V2 item 5.3)
        grants = pacs.revoke(case_id)  # the image viewer grants opened from it end with it (V2 item 6.3)
        store.audit(case_id, {"kind": "case_deleted", "by": u, "notifications_removed": n, "unlinked": linked, "image_grants_revoked": grants}); store.delete_case(case_id)
        if private:  # the Case File's own audit goes with it: a receipt without patient details stays (who, when, how many records)
            store.private_receipt({"kind": "private_case_deleted", "case_id": case_id, "by": u, "how": "by the creator"})
        log.info("case %s deleted by %s; %d notification(s) removed", case_id, u, n)
        return {"ok": True, "notifications_removed": n}

    @r.post("/demo/{case_id}")
    async def demo(case_id: str, request: Request):
        u = _user(request); _need(_roles(request), "create_case")
        job = service.import_demo(store.safe_id(case_id), u)
        return {"job": job["id"], "total": job["total"]}

    @r.post("/cases/{case_id}/demo-arrivals")
    async def arrivals(case_id: str, request: Request):
        u = _user(request); c = _case(case_id); _need_case(_roles(request), "upload_to_case", c)
        job = service.demo_arrivals(case_id, u)
        if not job:
            raise HTTPException(404, "No demo arrivals for this case")
        return {"job": job["id"], "total": job["total"]}

    @r.get("/cases/{case_id}")
    async def get_case(case_id: str, request: Request):
        rl = _roles(request); c = _case(case_id)
        st = store.get_state(case_id)
        all_docs = store.list_docs(case_id)
        if _scope(request) == access.REQUESTS:  # a department that was only asked: its requests and the records in their scope (V2 item 5.1)
            st = access.limited_state(rl, c, st)
            mine = access.limited_docs(rl, c, rules.case_docs(case_id, store.get_state(case_id)), store.get_state(case_id))
            docs = [{k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "state", "error", "classification", "added", "department", "uploaded_by")}
                    | {"facts": {}, "pages": len(d.get("pages") or []), "methods": [], "scan_pages": [], "page_flags": []} | his_case.doc_view(d)
                    | {"final": steps.final_status(d)} for d in mine]  # final and signed, for the "not signed" mark on a source chip (2 Nov 2026)
            p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
            case_view = {k: c.get(k) for k in ("case_id", "protocol", "setting", "board_date", "department", "listing", "hospital_level", "created_at")} | {"patient": {k: p.get(k) for k in ("name", "mrn", "agesex")}}
            return {"case": case_view, "state": st, "documents": docs, "facts": {}, "timeline": [], "signature": None, "stale": {},  # no referrals, participants, links or encounters without records (review Phase 5 M2)
                    "permissions": {"answer_request": {a["id"]: _can_answer(rl, a) for a in st["actions"] if a.get("source") == "pre_authorization"},
                                    "update_action": {a["id"]: org.can(rl, "update_action", a.get("department") or None) for a in st["actions"]}},
                    "discordances": None, "trends": None, "outcomes": postboard.OUTCOMES, "his": None, "his_flags": [], "requests": dept_requests.summary(st),
                    "groups": [g for g in his_case.encounter_groups(c, mine) if g.get("docs")],
                    "access": {"owner": access.public(c)["owner"], "participants": [], "owner_history": [], "linked_cases": [], "scope": access.REQUESTS}}
        docs = []
        confirmed_docs = rules.case_docs(case_id, st)
        for d in confirmed_docs:  # as the clinicians confirmed them (type, dates, values; V1 items 2.2, 3.1, 3.2)
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "state", "error", "dismissed", "classification", "identity", "identity_read", "added", "department", "uploaded_by")} |
                        {"facts": d.get("facts", {}), "pages": len(d.get("pages") or []), "methods": sorted({p["method"] for p in d.get("pages") or []}),
                         "scan_pages": scanned.scan_pages(d.get("pages")),  # pages read from an image: "from scan (OCR)" (V1 item 8.1)
                         "page_flags": sorted({f for p in d.get("pages") or [] for f in p.get("flags") or []})}  # Hindi / regional text, illegible parts (V1 item 3.6)
                        | his_case.doc_view(d)  # HIS status, signature, encounter, accession, version history; outside reports (V2 items 3.3 to 3.6)
                        | {"final": steps.final_status(d)})  # final and signed: a source chip of a report not final and signed says so (owner, 2 Nov 2026)
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))  # confirmations overlaid (V1 item 2.2)
        cat = protocol.facts()
        sig = rules.case_signature(case_id, st)  # what a summary or brief would be generated from now (V1 item 4.5)
        stale = {name: (rules.stale_reason(a["signature"], sig) if a.get("signature") else
                        "Compiled before the Case File signature was kept, so changes since then cannot be checked")  # pre-4.5 artefacts (review)
                 for name, a in (st.get("artefacts") or {}).items() if isinstance(a, dict) and (name == "summary" or name.startswith("brief_"))}
        return {"case": _reader_case(request, c), "state": _state_view(st), "documents": docs, "facts": {k: {"label": cat.get(k, {}).get("label", k), **v} for k, v in facts.items()},
                "timeline": postboard.timeline(case_id), "permissions": _case_permissions(rl, c, st, all_docs), "signature": sig, "stale": stale,
                "discordances": discord.summary(case_id, st),  # reports that disagree, values a decision cited that later reports changed (12 Oct)
                "trends": postboard.trends(case_id, st), "outcomes": postboard.OUTCOMES,  # values over time (12 Oct)
                "his": his_case.public(c), "his_flags": his_case.flags(case_id, confirmed_docs),  # the hospital system, its registrations and orders; HIS values the text does not carry (V2 item 3.3)
                "requests": dept_requests.summary(st),  # suggested / sent / done / closed counts (V2 item 4.2)
                "groups": his_case.encounter_groups(c, confirmed_docs),  # records grouped by OP visit and IP admission (V2 item 3.4)
                "access": {**access.public(c), "scope": _scope(request)},  # owner, participants, linked Case Files (V2 items 5.1 / 5.3); READ for a window (review 9 M5)
                "referral": referral.public(c)}  # the open referral, the history, the hospital system's suggestions (V2 item 5.2)

    @r.post("/cases/{case_id}/documents")
    async def upload(case_id: str, request: Request, files: list[UploadFile] = File(...), paths: str = Form("[]"), outside: str = Form(""),
                     anonymized: str = Form(""), confirm: str = Form(""), reason: str = Form("")):
        """Upload into a Case File. Into an HIS-connected Case File every upload is an outside report (another hospital, a private
        laboratory; V2 item 3.6) unless `outside` is "0"; elsewhere `outside=1` labels it so."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "upload_to_case", c)
        if not _upload_allowed(rl, c):
            return JSONResponse({"detail": {"message": "On this site, uploading is for guest reviewers, into their own private Case Files.", "code": "upload_private_only"}}, status_code=403)
        rels = json.loads(paths or "[]")
        data = []
        for i, f in enumerate(files):
            b = await f.read()
            if len(b) > 60 * 1024 * 1024:
                raise HTTPException(413, f"{f.filename} is larger than 60 MB")
            data.append((rels[i] if i < len(rels) and rels[i] else f.filename, b))
        is_outside = (str(outside).strip().lower() in ("1", "true", "yes")) or (bool(c.get("his")) and str(outside).strip().lower() not in ("0", "false", "no"))
        meta = None
        if config.is_private(c["case_id"]):  # a guest reviewer's anonymized real files (upload_safety): checked, cleaned, scanned first
            data, meta, refusal = await asyncio.to_thread(_private_upload_check, case_id, data, u, anonymized, confirm, reason)
            if refusal is not None:
                return refusal
        job = service.add_files(case_id, data, u, warn=False, outside=is_outside, meta=meta)
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
        if _upload_policy() == "private_only":
            return JSONResponse({"detail": {"message": "On this site, uploading is for guest reviewers, into their own private Case Files.", "code": "upload_private_only"}}, status_code=403)
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
        cases = [{"case_id": c["case_id"], "patient": c.get("patient") or {}, "protocol": c.get("protocol"), "listing": c.get("listing")} for c in access.visible(rl, store.list_cases())]  # only what the user may open (review Phase 5 M1)
        return {"documents": docs, "cases": cases, "can_match": org.can(rl, "match"), "can_create": org.can(rl, "create_case"),
                "departments": org.my_departments(rl), "audit": store.read_intake_audit(200) if org.board_wide(rl) else []}

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
        return _original_response(p, (store.get_intake(doc_id) or {}).get("filename") or "")

    @r.post("/intake/{doc_id}/file-to-case")
    async def intake_file_to_case(doc_id: str, request: Request):
        """A person files the document into a Case File ({"case_id": ..., "reason": ...}); recorded as a confirm_match in that Case File."""
        u = _user(request); rl = _roles(request); _need(rl, "match"); _intake(doc_id, rl, actionable=True); b = await request.json()
        case_id = store.safe_id(str(b.get("case_id", "")))
        c = store.get_case(case_id)
        if not c or access.hidden(rl, c):  # a protected Case File is not named to anyone else (finding 0)
            raise HTTPException(404, "Case not found")
        if access.is_archived(c):  # security review #8
            raise HTTPException(409, {"message": access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", "code": "archived"})
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
        return {**notify.inbox(rl), "referrals": referral.inbox(rl)}  # plus the referrals to and from the user's departments (V2 item 5.2)

    @r.get("/referrals")
    async def referrals_mine(request: Request):
        """The referrals addressed to the user's departments (to accept or decline) and the ones they sent (V2 item 5.2)."""
        rl = _roles(request); _need_known(rl)
        return {"referrals": referral.inbox(rl)}

    # ---- referral to another treating department (V2 item 5.2) ----
    def _ref_call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except referral.ReferralError as e:
            raise HTTPException(e.status, str(e))

    @r.post("/cases/{case_id}/referrals")
    async def referral_request(case_id: str, request: Request):
        """{"to": department, "reason", "his_ref"?}: the owning department refers the Case File; the receiving department is told."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "refer", c)
        b = await request.json() if (await request.body()) else {}
        b = b if isinstance(b, dict) else {}
        async with store.lock(case_id):
            rec = _ref_call(referral.request, case_id, str(b.get("to") or ""), str(b.get("reason") or ""), u, his_ref=str(b.get("his_ref") or ""))
        return {"referral": rec, "case": _reader_case(request, store.get_case(case_id)), "referrals": referral.public(store.get_case(case_id))}

    @r.post("/cases/{case_id}/referrals/{referral_id}/withdraw")
    async def referral_withdraw(case_id: str, referral_id: str, request: Request):
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "refer", c)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            if (access.open_referral(c) or {}).get("id") != referral_id:
                raise HTTPException(409, "That referral is not waiting for an answer")
            rec = _ref_call(referral.withdraw, case_id, u, note=str((b or {}).get("note") or "") if isinstance(b, dict) else "", referral_id=referral_id)
        return {"referral": rec, "case": _reader_case(request, store.get_case(case_id)), "referrals": referral.public(store.get_case(case_id))}

    def _answer_referral(rl, c, referral_id):
        rec = access.open_referral(c)
        if not rec or rec.get("id") != referral_id:
            raise HTTPException(409, "That referral is not waiting for an answer")
        _need(rl, "answer_referral", rec.get("to"))
        return rec

    @r.post("/cases/{case_id}/referrals/{referral_id}/decline")
    async def referral_decline(case_id: str, referral_id: str, request: Request):
        """{"note"?}: the receiving department declines; the Case File stays with its owner."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _answer_referral(rl, c, referral_id)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            rec = _ref_call(referral.decline, case_id, u, note=str((b or {}).get("note") or "") if isinstance(b, dict) else "", referral_id=referral_id)
        return {"referral": rec, "case": _reader_case(request, store.get_case(case_id)), "referrals": referral.public(store.get_case(case_id))}

    @r.post("/cases/{case_id}/referrals/{referral_id}/accept")
    async def referral_accept(case_id: str, referral_id: str, request: Request):
        """{"note"?, "protocol"?, "setting"?, "hospital_level"?}: the receiving department accepts. Ownership moves, the referring department
        stays as a participant, the earlier gate is archived; with a protocol the Case File is listed under it at once (a job re-runs
        the Pre-Authorization on the same records), otherwise the new owner picks it on the listing form."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _answer_referral(rl, c, referral_id)
        b = await request.json() if (await request.body()) else {}
        b = b if isinstance(b, dict) else {}
        async with store.lock(case_id):
            out = _ref_call(referral.accept, case_id, u, note=str(b.get("note") or ""), protocol_id=str(b.get("protocol") or ""), setting=str(b.get("setting") or ""),
                            hospital_level=str(b.get("hospital_level") or ""), referral_id=referral_id)
        job = out.get("job")
        return {"referral": out["referral"], "case": _reader_case(request, out["case"]), "job": job["id"] if job else None, "total": job["total"] if job else 0,
                "referrals": referral.public(out["case"]), "access": access.public(out["case"])}

    @r.post("/cases/{case_id}/referrals/suggestions/{his_ref}/dismiss")
    async def referral_dismiss_suggestion(case_id: str, his_ref: str, request: Request):
        """{"note"?}: the owner decides not to follow the hospital system's referral (audited)."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "refer", c)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            c = _ref_call(referral.dismiss_suggestion, case_id, his_ref, u, note=str((b or {}).get("note") or "") if isinstance(b, dict) else "")
        return {"case": _reader_case(request, c), "referrals": referral.public(c)}

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

    def _no_export_in_window(request, rl, c):
        """A window reads the Case File on screen only (access.no_export_in_window, also used by the deck): 403 break_glass_read_only."""
        try:
            access.no_export_in_window(rl, c, _scope(request))
        except access.AccessError as e:
            raise HTTPException(e.status, {"message": str(e), "code": e.code})

    @r.get("/cases/{case_id}/export/vtb")
    async def export_vtb(case_id: str, request: Request):
        """The NCG Virtual Tumour Board case template filled from the verified Case File summary (V1 item 4.6), for referral to a
        Regional Cancer Centre or the NCG VTB. Refused (409) without a current summary. Audited."""
        u = _user(request); rl = _roles(request); _need_known(rl); _no_export_in_window(request, rl, _case(case_id))
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
        """FHIR R4 document bundle of the Case File (mCODE-informed, not profile-validated; values as recorded) (12 Oct). Audited (Phase 0 review)."""
        u = _user(request); rl = _roles(request); _need_known(rl); _no_export_in_window(request, rl, _case(case_id))
        b = fhir_export.bundle(case_id)
        store.audit(case_id, {"kind": "export_fhir", "by": u, "entries": len(b.get("entry") or [])})
        return JSONResponse(b, headers={"Content-Disposition": f'attachment; filename="{case_id}_fhir_bundle.json"'})

    @r.get("/cases/{case_id}/export/registry")
    async def export_registry(case_id: str, request: Request, format: str = "json"):
        """The HBCR (ICMR-NCDIR 2025) registry items as the records state them, with sources (12 Oct). Audited (Phase 0 review)."""
        u = _user(request); rl = _roles(request); _need_known(rl); _no_export_in_window(request, rl, _case(case_id))
        store.audit(case_id, {"kind": "export_registry", "by": u, "format": format})
        if format == "csv":
            from fastapi.responses import Response
            return Response(fhir_export.registry_csv(case_id), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{case_id}_registry_abstract.csv"'})
        return fhir_export.registry_abstract(case_id)

    @r.get("/cases/{case_id}/export")
    async def export(case_id: str, request: Request):
        """Portable record of the Case File (state, documents' extracted data, audit) for the hospital record system. Audited (Phase 0 review)."""
        u = _user(request); rl = _roles(request); _need_known(rl); c = _case(case_id); _no_export_in_window(request, rl, c)
        store.audit(case_id, {"kind": "export_case_file", "by": u})
        docs = []
        for d in store.list_docs(case_id):
            docs.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "sha256", "classification", "identity", "facts", "state", "processed")})
        return JSONResponse({"case": c, "state": store.get_state(case_id), "documents": docs, "audit": store.read_audit(case_id, 5000)},
                            headers={"Content-Disposition": f'attachment; filename="{c["case_id"]}_case_file.json"'})

    def _in_scope(request, c, doc_id):
        """A department that was only asked opens only the records in its scope (V2 item 5.1); a meeting member only the record on the
        shared screen (the guard checked it)."""
        sc = _scope(request)
        if sc == MEETING_SCOPE:
            if not _meeting_record(_roles(request), c["case_id"], f"/documents/{doc_id}/file"):
                raise HTTPException(403, "Only the record shown on the meeting's shared screen is open to you.")
            return
        if sc == access.REQUESTS and not any(x["doc_id"] == doc_id for x in access.limited_docs(_roles(request), c, store.list_docs(c["case_id"]))):
            if request.method == "GET" and _meeting_record(_roles(request), c["case_id"], f"/documents/{doc_id}/file") and request.url.path.endswith("/file"):
                return  # the record on the shared screen of a meeting this member was admitted to
            raise HTTPException(403, "Your department sees only the records it produced or was asked about in this Case File.")

    @r.get("/cases/{case_id}/documents/{doc_id}")
    async def doc(case_id: str, doc_id: str, request: Request):
        _user(request); c = _case(case_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        _in_scope(request, c, doc_id)
        # as the clinicians confirmed it (V1 item 2.2; review M1: a confirmed value no longer shows as the model's reading), facts saying
        # whether they were read from a scan (V1 item 8.1)
        return scanned.with_source_methods(confirm.apply_to_doc(d, store.get_state(case_id), case_id))

    @r.get("/cases/{case_id}/documents/{doc_id}/file")
    async def doc_file(case_id: str, doc_id: str, request: Request, render: int = 0, page: int = 0):
        u = _user(request); c = _case(case_id); _in_scope(request, c, doc_id)
        try:
            p = store.original_path(case_id, doc_id)
        except StopIteration:  # a hospital-system record whose file is not on disk: fetched live from the HIS (V2 item 6.3)
            d = store.get_doc(case_id, doc_id)
            if not d:
                raise HTTPException(404, "document not found")
            try:
                p = await his_case.fetch_file(case_id, d, u)
            except his_case.HISCaseError as e:
                raise HTTPException(e.status, str(e))
            except his_client.HISError as e:
                raise HTTPException(502, f"The hospital system did not give the file: {str(e)[:160]}")
        # page preview as PNG (keeps the strict CSP: no PDF iframes needed); Aadhaar groups read by the OCR engine blacked out (V1 item 8.4)
        out = scanned.preview_bytes(p, store.get_doc(case_id, doc_id) or {}, bool(render), page)
        if out:
            from fastapi.responses import Response
            return Response(out[0], media_type=out[1])
        return _original_response(p, (store.get_doc(case_id, doc_id) or {}).get("filename") or "")

    @r.post("/cases/{case_id}/documents/{doc_id}/images")
    async def doc_images(case_id: str, doc_id: str, request: Request):
        """The images behind an imaging report from the hospital system (V2 item 6.3): the study is looked up (cached on the record), the
        user is granted the viewer on that study for 12 hours, the open is audited, and the app's viewer URL is returned. Humans view;
        no model ever reads the images. A POST: it grants, writes the record's cache and audits (Phase 6 review)."""
        rl = _roles(request); u = _user(request); c = _case(case_id); _in_scope(request, c, doc_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        if not (d.get("his") or {}).get("imaging_study_ref"):
            raise HTTPException(404, "This record has no imaging study in the hospital system")
        try:
            study = await pacs.study_for_doc(case_id, d, his_client.client())
        except Exception as e:
            raise HTTPException(502, f"The hospital system did not answer about the study: {type(e).__name__}: {str(e)[:160]}")
        if not study:
            raise HTTPException(404, "This record has no imaging study in the hospital system")
        if study.get("available"):
            pacs.grant(rl.get("user") or u, study["study_uid"], case_id, doc_id)
        store.audit(case_id, {"kind": "images_opened", "by": u, "doc_id": doc_id, "study_uid": study.get("study_uid") or "", "accession": study.get("accession") or "",
                              "available": bool(study.get("available")), "reason": study.get("reason") or ""})
        return {"doc_id": doc_id, **study, "note": "Images open in the hospital's image viewer through this app; they are viewed by people and never read by a model."}

    @r.api_route("/pacs/{path:path}", methods=["GET", "HEAD"])
    async def pacs_proxy(path: str, request: Request):
        """The image viewer (OHIF) and the DICOMweb study it was opened on, forwarded to the PACS for a logged-in user holding a grant from
        "Open images" on the report (V2 item 6.3). Orthanc's own API and explorer are never reached through here."""
        return await pacs.proxy(request, path, _roles(request))

    @r.post("/cases/{case_id}/ready")
    async def case_ready(case_id: str, request: Request):
        """{"ready": true, "list"?: discussion | noting, "meeting_id"?, "presenter"?, "note"?, "reason"?}: Send to the board (night-v3 item
        1.4, board.send_to_board): the question is required and, with items open, the reason; the Case File goes on that meeting's list and
        the MDT Coordinator is told. {"ready": false, "note"?} takes the mark back (V2 item 6.1)."""
        u = _user(request); c = _case(case_id); _need_case(_roles(request), "mark_ready", c); b = await request.json() if (await request.body()) else {}
        if not isinstance(b, dict):
            b = {}
        try:
            async with store.lock(case_id):  # case.json changes: never alongside another change to the same Case File
                if bool(b.get("ready", True)):
                    c = board.send_to_board(case_id, u, list=str(b.get("list") or "discussion"), meeting_id=str(b.get("meeting_id") or ""),
                                            presenter=str(b.get("presenter") or ""), note=str(b.get("note") or ""), reason=str(b.get("reason") or ""))
                else:
                    c = board.mark_ready(case_id, u, ready=False, note=str(b.get("note") or ""))
        except ValueError as e:
            raise HTTPException(400, {"message": str(e), "code": "send_400"})
        if bool(b.get("ready", True)):  # the summary prose and the heads' briefs are prepared in the background (18 Oct, tumour_board/ready_hook.py)
            try:
                from tumour_board import ready_hook
                ready_hook.on_ready(case_id, u)
            except Exception as e:
                log.warning("ready hook failed for %s (%s: %s)", case_id, e.__class__.__name__, e)
        return {"case_id": case_id, "board_ready": c.get("board_ready") or None, "history": c.get("board_ready_history") or [],
                "send": c.get("board_send") if c.get("board_ready") else None}

    @r.post("/cases/{case_id}/requests/{action_id}/remind")
    async def request_remind(case_id: str, action_id: str, request: Request):
        """A reminder about one request (V2 item 6.1): the MDT Coordinator on the owner's behalf, or the owner's doctors. A sent request
        reaches its department again; a suggested one reminds the owning department to send it."""
        u = _user(request); rl = _roles(request); c = _case(case_id)
        if not access.may_remind(rl, c):
            raise HTTPException(403, "Reminders are sent by the MDT Coordinator on the owner's behalf or by the owning department's doctors.")
        b = await request.json() if (await request.body()) else {}
        try:
            return dept_requests.remind(case_id, action_id, u, rl, note=str(b.get("note") or ""))
        except dept_requests.RequestError as e:
            raise HTTPException(e.status, str(e))

    @r.post("/cases/{case_id}/remind-owner")
    async def remind_owner(case_id: str, request: Request):
        """One reminder to the owning department about the Case File before the board: unsent suggestions, overdue requests, the
        summary, the ready mark (V2 item 6.1). The MDT Coordinator, or the owner's own doctors."""
        u = _user(request); rl = _roles(request); c = _case(case_id)
        if not access.may_remind(rl, c):
            raise HTTPException(403, "Reminders are sent by the MDT Coordinator on the owner's behalf or by the owning department's doctors.")
        b = await request.json() if (await request.body()) else {}
        try:
            return dept_requests.remind_owner(case_id, u, rl, note=str(b.get("note") or ""))
        except dept_requests.RequestError as e:
            raise HTTPException(e.status, str(e))

    @r.post("/cases/{case_id}/recheck")
    async def recheck(case_id: str, request: Request):
        u = _user(request); _need_known(_roles(request)); _case(case_id)
        async with store.lock(case_id):  # never interleave with an ingestion job writing the same state
            return service.recheck(case_id, u)

    @r.post("/cases/{case_id}/reprocess")
    async def reprocess(case_id: str, request: Request):
        u = _user(request); c = _case(case_id); _need_case(_roles(request), "upload_to_case", c)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):  # withdraws dismissals: never alongside a confirmation being recorded
            job = service.reprocess(case_id, (b if isinstance(b, dict) else {}).get("which", "errors"), u)
        return {"job": job["id"], "total": job["total"]}

    @r.delete("/cases/{case_id}/documents/{doc_id}")
    async def delete_doc(case_id: str, doc_id: str, request: Request):
        u = _user(request); c = _case(case_id)
        d = store.get_doc(case_id, doc_id)
        if not d:
            raise HTTPException(404, "document not found")
        _need_case(_roles(request), "delete_document", c, _doc_department(d))
        async with store.lock(case_id):
            return service.delete_document(case_id, doc_id, u)

    def _confirmation_permission(rl, case_id, c, ctype, key):
        """The permission each confirmation type needs (plan 2.2: permission goes through can()). Document-level types are
        checked against the department that uploaded the document; a waiver against the requirement's Responsible Department."""
        action = confirm.TYPES[ctype]["action"]
        if ctype == "waive":
            dept = next((q.get("department") for q in protocol.get(c["protocol"]).get("mandatory", []) if q["id"] == key), "") if c.get("protocol") else ""
            _need_case(rl, "waive", c, dept or None)
        elif ctype == "confirm_match":
            d = store.get_doc(case_id, key) if key else None
            if d and d.get("outside"):  # an outside report matched by name only: the treating doctor confirms the patient (V2 item 3.6)
                _need_case(rl, "confirm", c, _doc_department(d))
            else:
                _need(rl, "match")
        elif confirm.TYPES[ctype]["target"] in ("document", "fact"):
            doc_id = key.partition(":")[0] if confirm.TYPES[ctype]["target"] == "fact" else key
            _need_case(rl, action, c, _doc_department(store.get_doc(case_id, doc_id) if doc_id else None))
        elif ctype == "resolve_flag":
            _need(rl, "board_record")
        else:
            _need_case(rl, action, c)

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
        if ctype == "confirm_match" and store.get_doc(case_id, key) and (b.get("fields") or {}).get("case_id") not in ("", case_id):
            raise HTTPException(400, "A patient confirmation on a document of this Case File names this Case File (or an empty id for not this patient)")  # review M6
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
            d_match = store.get_doc(case_id, rec["key"]) if rec["type"] == "confirm_match" and (rec.get("fields") or {}).get("case_id") else None
            if d_match and d_match.get("intake"):
                # undoing a match (a person's or the matcher's) moves the document back to the Needs matching queue
                out = service.unfile_document(case_id, rec["key"], u, "match undone")
                return {"confirmation": next((x for x in store.get_state(case_id).get("confirmations", []) if x["id"] == conf_id), rec), "state": out["state"], "unfiled": True}
            # an outside report (V2 item 3.6) or a document uploaded straight into the Case File: the confirmation is undone, the record stays (review M5)
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

    # ---- requests to departments: suggested by the gate, sent by the treating doctor, answered by the department (V2 items 4.2 / 4.3)
    def _request(case_id, action_id):
        try:
            return dept_requests.find(store.get_state(case_id), action_id)
        except dept_requests.RequestError as e:
            raise HTTPException(e.status, str(e))

    @r.get("/cases/{case_id}/requests/{action_id}/draft")
    async def request_draft(case_id: str, action_id: str, request: Request):
        """The Notify dialog: the address, the subject, the editable message, the proposed due date and the mailto: link. Nothing is sent."""
        rl = _roles(request); _need_known(rl); c = _case(case_id)
        return dept_requests.draft(c, _request(case_id, action_id), rl.get("user") or "")

    @r.post("/cases/{case_id}/requests/{action_id}/send")
    async def request_send(case_id: str, action_id: str, request: Request):
        """{"message"?, "due"?, "subject"?}: the treating doctor sends the suggested request in-app (edited or as drafted); sending a sent
        request again is a reminder. The department is notified; audited."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "send_request", c)
        b = await request.json() if (await request.body()) else {}
        b = b if isinstance(b, dict) else {}
        async with store.lock(case_id):
            try:
                a = dept_requests.send(case_id, action_id, u, rl, message=str(b.get("message") or ""), due=str(b.get("due") or ""), subject_text=str(b.get("subject") or ""))
            except dept_requests.RequestError as e:
                raise HTTPException(e.status, str(e))
        return {"action": a, "requests": dept_requests.summary(store.get_state(case_id))}

    @r.post("/cases/{case_id}/requests")
    async def request_create(case_id: str, request: Request):
        """{"department", "label", "what"?, "message"?, "due"?}: a request with no protocol record behind it (a pre-anaesthetic check, a
        medication review), written by the treating doctor and sent in one step."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "create_request", c)
        b = await request.json() if (await request.body()) else {}
        b = b if isinstance(b, dict) else {}
        async with store.lock(case_id):
            try:
                a = dept_requests.create_free(case_id, str(b.get("department") or ""), str(b.get("label") or ""), u, rl, message=str(b.get("message") or ""),
                                              due=str(b.get("due") or ""), what=str(b.get("what") or ""))
            except dept_requests.RequestError as e:
                raise HTTPException(e.status, str(e))
        return {"action": a, "requests": dept_requests.summary(store.get_state(case_id))}

    def _answerable(case_id, action_id, request):
        a = _request(case_id, action_id)
        if not _can_answer(_roles(request), a):
            raise HTTPException(403, f"Only the doctors of {a.get('department') or 'that department'} answer this request.")
        return a

    @r.post("/cases/{case_id}/requests/{action_id}/acknowledge")
    async def request_acknowledge(case_id: str, action_id: str, request: Request):
        """The department has read the request and is working on it; the owning department is told."""
        u = _user(request); _case(case_id); _answerable(case_id, action_id, request)
        async with store.lock(case_id):
            try:
                a = dept_requests.acknowledge(case_id, action_id, u)
            except dept_requests.RequestError as e:
                raise HTTPException(e.status, str(e))
        return {"action": a}

    @r.post("/cases/{case_id}/requests/{action_id}/done")
    async def request_done(case_id: str, action_id: str, request: Request):
        """{"note"?}: "done" back from the department. A gap request stays open until the re-fetch (or upload) brings the record; a free
        request closes here. The owning department is told."""
        u = _user(request); _case(case_id); _answerable(case_id, action_id, request)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            try:
                a = dept_requests.done(case_id, action_id, u, note=str((b or {}).get("note") or "") if isinstance(b, dict) else "")
            except dept_requests.RequestError as e:
                raise HTTPException(e.status, str(e))
        return {"action": a}

    @r.post("/cases/{case_id}/requests/{action_id}/close")
    async def request_close(case_id: str, action_id: str, request: Request):
        """{"note"?}: the treating doctor closes a request that has no protocol record behind it."""
        u = _user(request); rl = _roles(request); c = _case(case_id); _need_case(rl, "close_request", c)
        b = await request.json() if (await request.body()) else {}
        async with store.lock(case_id):
            try:
                a = dept_requests.close_free(case_id, action_id, u, note=str((b or {}).get("note") or "") if isinstance(b, dict) else "")
            except dept_requests.RequestError as e:
                raise HTTPException(e.status, str(e))
        return {"action": a}

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
        rl = _roles(request); c = _case(case_id); _need_known(rl)
        if not (org.can(rl, "list_case") or access.may(rl, "upload_to_case", c)):  # the owning department's doctors or the MDT Coordinator (plan section 4, review Phase 5 M5)
            raise HTTPException(403, "Only the doctors of the owning department or the MDT Coordinator compile the Case File summary")
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
        except ValueError as e:  # the Case summary has its own review route (Phase 3 review M7)
            raise HTTPException(400, str(e))

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

    @r.post("/cases/{case_id}/board-records/{record_id}/correct")
    async def correct_board_record(case_id: str, record_id: str, request: Request):
        """A later correction of a saved board record (night-v3 item 3.1): {"changes": {field: value}, "reason"}. The owning department's
        consultants; the MDT Coordinator on the meeting day only. A new version (who, when, why, the changed fields, a snapshot); version 1
        is never overwritten. Audited; the owner is told."""
        from tumour_board import meetings as _meetings
        rl = _roles(request); u = _user(request); c = _case(case_id)
        try:  # a body that is not JSON, or a record id store.safe_id refuses ("."): 400, never 500 (whole-run review 9, M10)
            b = await request.json()
            rid = store.safe_id(record_id)
        except ValueError:
            raise HTTPException(400, {"message": "Send a valid board record id and a JSON body.", "code": "bad_request"})
        b = b if isinstance(b, dict) else {}
        rec = next((x for x in store.get_state(case_id).get("board_records") or [] if x.get("id") == rid), None)
        if not rec:
            raise HTTPException(404, "No such Tumour Board record")
        if access.is_archived(c):
            raise HTTPException(409, {"message": access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", "code": "archived"})
        refusal = _correct_refusal(rl, c, rec)  # the same rule as permissions.correct_board_record on the Case File view
        if refusal:
            raise HTTPException(403, refusal)
        if not isinstance(b.get("changes"), dict):
            raise HTTPException(400, "Send the fields to correct under \"changes\"")
        async with store.lock(case_id):
            try:
                rec = postboard.correct_record(case_id, rid, b["changes"], u, _meetings.display_name(u), str(b.get("reason") or ""))
            except KeyError:
                raise HTTPException(404, "No such Tumour Board record")
            except ValueError as e:
                raise HTTPException(400, str(e))
        if rec.get("session"):  # the meeting and the session export show the current version
            try:
                board.decision_amended(rec["session"], case_id, rec, u)
            except ValueError as e:
                log.warning("session %s: corrected record not shown (%s)", rec["session"], e)
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

    def _need_open(rl, s):
        """Who may open a session (V2 item 6.1): the MDT Coordinator, the Vaidyx admin, a doctor on the attendance sheet or of a department
        that may read a Case File on the agenda."""
        if not board.may_open(rl, s):
            raise HTTPException(403, "This board session is open to the MDT Coordinator, the departments on its attendance sheet and the departments of the Case Files on its agenda.")

    def _records(cid, st):
        """The Case File's records for the Board room (V2 item 6.3): title, type, date, status, the hospital-system status and signature,
        and whether an imaging report has images to open. Open and Open images go through the document routes (scope-checked, audited)."""
        out = []
        for d in rules.case_docs(cid, st):
            if d.get("state") != "ready":
                continue
            cl = d.get("classification") or {}; h = d.get("his") or {}
            out.append({"doc_id": d["doc_id"], "title": cl.get("title") or d.get("filename"), "doc_type": cl.get("doc_type"), "date": cl.get("report_date_iso") or cl.get("event_date_iso") or "",
                        "status": cl.get("status"), "signed": cl.get("signed"), "department": d.get("department"), "superseded": bool(d.get("superseded")),
                        "outside": bool(d.get("outside")), "his": {"status": h.get("status"), "signed": bool(h.get("signed")), "accession": h.get("accession"),
                                                                  "encounter_number": h.get("encounter_number"), "version": h.get("version")} if h else None,
                        "images": bool(h.get("imaging_study_ref")), "study": {k: v for k, v in (h.get("study") or {}).items() if k in ("available", "modality", "series", "instances", "reason")} or None})
        return out

    def _room(s, rl):
        """Everything the Board room shows: the session, the attendance sheet (heads first), and for each Case File on the agenda its gate,
        its summary, the briefs of the agents active for it (a head not recorded present, the surgical seat rule; V2 item 6.2), its
        records (6.3), its decision and the follow-up (6.1). A doctor sees the Case Files it may read; the others are restricted."""
        by_case = board.absent_roles_by_case(s)
        absent = board.absent_roles(s)
        full = org.board_wide(rl)  # never the Vaidyx admin (review #2)
        cases = {}
        for a in s["agenda"]:
            cid = a["case_id"]; c = store.get_case(cid)
            if not c:
                cases[cid] = {"missing": True}; continue
            if not full and access.scope(rl, c) != access.FULL:  # a department that may not read this Case File (V2 item 5.1)
                cases[cid] = {"restricted": True, "protocol": c.get("protocol"), "owner_name": org.department_name(c["department"]) if c.get("department") else "",
                              "agents": by_case.get(cid, []), "seat": board.seat(s, c)}; continue
            st = store.get_state(cid); g = st.get("gate") or {}
            sig = rules.case_signature(cid, st)
            arts = st.get("artefacts") or {}
            roles_ = by_case.get(cid, [])
            stale = lambda x: (rules.stale_reason(x["signature"], sig) if x.get("signature") else "Compiled before the Case File signature was kept") if x else ""
            cases[cid] = {"patient": c.get("patient") or {}, "protocol": c.get("protocol"), "setting": c.get("setting"), "board_date": c.get("board_date"),
                          "owner": c.get("department") or None, "owner_name": org.department_name(c["department"]) if c.get("department") else "",
                          "ready": c.get("board_ready") or None, "linked_cases": [l.get("case_id") for l in c.get("linked_cases") or [] if isinstance(l, dict)],
                          "gate": {"passed": g.get("passed"), "satisfied": g.get("satisfied"), "total": g.get("total"), "readiness": g.get("readiness")},
                          "summary": arts.get("summary"), "summary_stale": stale(arts.get("summary")),
                          "agents": roles_, "seat": board.seat(s, c),  # the agents active for this Case File and the surgical seat (V2 item 6.2)
                          "briefs": {r_: arts.get(f"brief_{r_}") for r_ in agents.ROLES if arts.get(f"brief_{r_}") and (r_ in roles_ or r_ in board.ON_DEMAND)},
                          "briefs_stale": {r_: stale(arts.get(f"brief_{r_}")) for r_ in agents.ROLES if arts.get(f"brief_{r_}") and (r_ in roles_ or r_ in board.ON_DEMAND)},
                          "records": _records(cid, st),  # HIS records and images opened during the board (V2 item 6.3)
                          "board_records": [{"id": b_["id"], "board_date": b_.get("board_date"), "session": b_.get("session"), "status": b_["adjudication"]["status"],
                                             "flags": len(b_["adjudication"]["flags"]), "composition": b_["adjudication"].get("composition"),
                                             "resolution": b_.get("resolution"), "version": b_.get("version", 1)} for b_ in st.get("board_records", [])]}
        allowed = None if full else {cid for cid, v in cases.items() if not v.get("restricted") and not v.get("missing")}
        # a doctor sees the log, the decisions, the agent records and the follow-up of the Case Files it may read only (Phase 6 review S2)
        return {"session": board.session_view(s, allowed), "specialties": board.specialties(), "attendance_list": board.attendance_list(s), "heads": board.heads(), "on_demand": list(board.ON_DEMAND),
                "absent_roles": absent, "absent_roles_by_case": by_case, "participants": board.participants(s),
                "roles": {k: {"label": agents.spec(k)["label"], "department": agents.department_of(k)} for k in agents.ROLES},
                "cases": cases, "can_manage": org.can(rl, "session"), "can_ask": bool(rl.get("admin") or rl.get("known")), "can_review": org.can(rl, "review"),
                "can_record": org.can(rl, "board_record"), "marks": board.MARKS,
                "followup": board.followup(s, allowed) if s.get("decisions") else None,  # the board's actions after the session (V2 item 6.1)
                "pmjay_empanelled": bool(org.hospital().get("pmjay_empanelled", True))}

    @r.get("/sessions")
    async def sessions(request: Request):
        rl = _roles(request)
        rows = board.list_sessions()
        if not org.board_wide(rl):  # a doctor (and the Vaidyx admin, review #2) sees the sessions it may open (V2 item 6.1)
            rows = [x for x in rows if board.may_open(rl, board.get(x["id"]))]
        return {"sessions": rows, "can_manage": org.can(rl, "session"), "heads": board.heads()}

    @r.get("/sessions/candidates")
    async def session_candidates(request: Request, date: str = ""):
        """The Case Files listed for the board on that date (V1 item 6.1), in agenda order."""
        rl = _roles(request)
        rows = _session_call(board.listed_for_date, date)
        if not org.can(rl, "session"):  # a doctor sees the listed Case Files it may open (review Phase 5 M1)
            vis = {c["case_id"] for c in access.visible(rl, store.list_cases())}
            rows = [x for x in rows if x.get("case_id") in vis]
        return {"date": date, "cases": rows}

    @r.post("/sessions")
    async def session_create(request: Request):
        u = _user(request); _need(_roles(request), "session"); b = await request.json()
        ids = _ids(b["case_ids"]) if isinstance(b.get("case_ids"), list) else None
        return _session_call(board.create, str(b.get("date", "")), u, ids, str(b.get("title", ""))[:120])

    @r.get("/sessions/{sid}")
    async def session_get(sid: str, request: Request):
        rl = _roles(request); s = _session(sid); sid = s["id"]; _need_open(rl, s)
        return _room(service.session_interrupted(sid), rl)

    @r.get("/sessions/{sid}/minutes")
    async def session_minutes(sid: str, request: Request, format: str = "html"):
        """The minutes of the session (V2 item 6.1): attendance, the decisions as dictated, the actions and their follow-up. Audited."""
        u = _user(request); rl = _roles(request); s = _session(sid); sid = s["id"]; _need_open(rl, s)
        allowed = board.allowed_cases(rl, s)  # None for the coordinator and the admin; a doctor gets its own Case Files, the others as restricted (Phase 6 review S2)
        board.audit_session(sid, {"kind": "minutes_export", "by": u, "format": format, "restricted": sorted(set(a["case_id"] for a in s["agenda"]) - allowed) if allowed is not None else []})
        if format == "json":
            return JSONResponse(board.minutes(sid, allowed), headers={"Content-Disposition": f'attachment; filename="{sid}_minutes.json"'})
        from fastapi.responses import HTMLResponse
        return HTMLResponse(board.minutes_html(sid, allowed), headers={"Content-Disposition": f'attachment; filename="{sid}_minutes.html"'})

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
        if roles and roles[0] not in board.ON_DEMAND and roles[0] not in board.absent_roles(s, b.get("case_id") or None):
            # agents stand in for a head not recorded present or a specialty marked absent; Radiation Oncology and Nuclear Medicine on demand (V2 item 6.2)
            raise HTTPException(400, "That specialty is recorded as present in this session" if not b.get("case_id") else "That specialty is recorded as present, or its seat is filled for this Case File")
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
        u = _user(request); rl = _roles(request); _need_known(rl); s = _session(sid); sid = s["id"]; _on_agenda(s, case_id); c = _case(case_id); _need_open(rl, s)
        if not org.board_wide(rl) and access.scope(rl, c) != access.FULL:  # a doctor asks about the Case Files it may read (V2 item 5.1)
            raise HTTPException(403, access.refusal(rl, c))
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
        u = _user(request); _need(_roles(request), "board_record"); s = _session(sid); sid = s["id"]; _on_agenda(s, case_id); c = _case(case_id); b = await request.json()
        if access.is_archived(c):  # security review #8
            raise HTTPException(409, {"message": access.ARCHIVED_MESSAGE + ". Take it out of the archive first.", "code": "archived"})
        if not str(b.get("decision_text", "")).strip():
            raise HTTPException(400, "Write the board's decision")
        part = board.participants(s)
        rec = {k: b.get(k) for k in ("decision_text", "recorded_by", "report_corrections_raised", "divergent_opinions", "actions", "next_review", "outcome_type", "deferred_reason",
                                     "referred_to", "intent_as_recorded", "trial_considered", "consent_recorded", "key_worker", *decision_record.KEYS) if b.get(k) is not None}
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
        u = _user(request); rl = _roles(request); s = _session(sid); sid = s["id"]; _need_open(rl, s)
        allowed = board.allowed_cases(rl, s)  # as for the minutes (Phase 6 review S2)
        board.audit_session(sid, {"kind": "export", "by": u, "format": format, "restricted": sorted(set(a["case_id"] for a in s["agenda"]) - allowed) if allowed is not None else []})
        if format == "json":
            return JSONResponse(board.export(sid, allowed), headers={"Content-Disposition": f'attachment; filename="{sid}_agent_log_and_decisions.json"'})
        from fastapi.responses import HTMLResponse
        return HTMLResponse(board.export_html(sid, allowed), headers={"Content-Disposition": f'attachment; filename="{sid}_agent_log_and_decisions.html"'})

    @r.get("/models")
    async def model_cards(request: Request):
        _user(request)
        f = config.DATA_ROOT / "model_cards.json"
        cards = json.loads(f.read_text()) if f.exists() else []
        return {"health": await llm.health(), "cards": cards, "embedder": search.EMBED_MODEL}

    try:  # the in-process scheduler (re-fetch, reminders, digests, meeting codes; 18 Oct); TB_SCHEDULER=0 keeps it off
        import os as _os
        if _os.getenv("TB_SCHEDULER", "1") != "0":
            from tumour_board import scheduler as _scheduler
            _scheduler.start()
    except Exception as e:
        log.warning("tumour board scheduler not started: %s", e)
    return _with_site(r)


def _with_site(r):
    """The API router plus the website's public router (tumour_board/api/site.py, paths under /tb-nik/api which the auth
    middleware leaves open): both under one router so app.py keeps its single include. A site router that fails to import
    is logged and skipped."""
    root = APIRouter()
    root.include_router(r)
    try:
        from tumour_board.api import site as _site
        root.include_router(_site.router)
    except Exception as e:
        log.warning("tumour_board.api.site not loaded: %s", e)
    return root
