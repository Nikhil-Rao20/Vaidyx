"""The demo HIMS of the Vaidyx Demo Hospital (product label DemoHIMS): FastAPI on 127.0.0.1:7130, localhost only, never
tunnelled. SYNTHETIC data only.

    his_mock/serve.sh start|stop|status|restart     (uvicorn --factory his_mock.app:create_app, app venv)

One process holds one Store (data/his_mock/store.json or $TB_HIS_MOCK_DATA) behind a lock; every writer changes it through
the Store transitions and calls Hospital.save(). Routers, each in its own module and mounted only when the module exists:

    /fhir           the FHIR R4 read API in NRCeS v6.5.0 shapes (bearer token from data/his_mock/token)
    /desk           the reporting engine's JSON API (login-free, for tests and the demo script) and the old desk links
    /his            the human screens: login (auth), Registration (screens), OPD, IPD, Laboratory (lab), Radiology,
                    Pathology, Exchange, Admin; the JSON API under /his/api stays login-free
    /api/tb/pacs    the PACS viewer proxy (pacs_proxy), same prefix the Vaidyx app uses, login required

Logins: every human screen needs the session cookie (auth.py); /view/reports/... accepts the cookie or the FHIR bearer
token (the Vaidyx app fetches documents through /documents/... with the token, unchanged). Failures on the screens are
plain pages with a flash message (403 "Your role cannot do this", 404, 409, 422), never a stack trace. Vaidyx-TB never
imports this package.
"""
import os
import secrets
import threading
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, model, paths, ui

NAME = "Vaidyx Demo Hospital HIS (SYNTHETIC)"
VERSION = "0.3"
DEFAULT_PORT = int(os.environ.get("TB_HIS_MOCK_PORT", "7130"))
ROUTERS = (("fhir", "/fhir"), ("desk", "/desk"), ("auth", "/his"), ("screens", "/his"), ("opd", "/his"), ("ipd", "/his"),
           ("lab", "/his"), ("radiology", "/his"), ("pathology", "/his"), ("exchange", "/his"), ("admin", "/his"),
           ("pacs_proxy", "/api/tb/pacs"))


class Hospital:
    """The app's state: the store, its files, a write lock, the API token and the accounts (sessions)."""

    def __init__(self, data_dir=None):
        self.files = paths.layout(data_dir)
        if not self.files["store"].exists():
            raise FileNotFoundError(f"{self.files['store']} missing: run python -m his_mock.build first")
        self.store = model.Store.load(self.files["store"])
        self.lock = threading.RLock()
        self.token = self.files["token"].read_text(encoding="utf-8").strip() if self.files["token"].exists() else None
        self.write_token = _ensure_write_token(self.files["write_token"])
        self.accounts = auth.Accounts(self.files["data_dir"])
        self.accounts.ensure(self.store)   # the 9 demo logins always exist (passwords in logins.tsv, mode 600)

    def save(self):
        """Write the store (and events.jsonl) after a change; callers hold self.lock."""
        with self.lock:
            self.store.save(self.files["store"], self.files["events"])

    def reload(self):
        with self.lock:
            self.store = model.Store.load(self.files["store"])

    def document_path(self, relative):
        """A file under documents/ (report PDFs, outside reports) by its store path (`documents/<name>`); refuses
        anything else (the token, the store, DICOM files)."""
        base = self.files["documents"].resolve()
        rel = str(relative).lstrip("/")
        if rel.startswith(paths.DOCUMENTS_NAME + "/"):
            rel = rel[len(paths.DOCUMENTS_NAME) + 1:]
        p = (base / rel).resolve()
        if base not in p.parents or not p.is_file():
            raise HTTPException(404, "no such document")
        return p


def _ensure_write_token(path):
    """The JSON write APIs' token (data/his_mock/write_token, mode 600): created when missing (an older data directory), never
    printed. Separate from the FHIR read token, which can change nothing (security review #13)."""
    path = Path(path)
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(16) + "\n")
        except FileExistsError:
            pass
        except OSError:
            return None
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path.read_text(encoding="utf-8").strip() or None


def get_hospital(request: Request) -> Hospital:
    return request.app.state.hospital


def _bearer(request):
    auth_header = request.headers.get("authorization") or ""
    return auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""


def bearer_ok(request, hospital):
    """True when the request carries the FHIR read token (header only; constant-time comparison)."""
    given = _bearer(request)
    return bool(hospital.token and given and secrets.compare_digest(given, hospital.token))


def write_bearer_ok(request, hospital):
    """True when the request carries the write token of the JSON APIs (header only; constant-time comparison)."""
    given = _bearer(request)
    return bool(getattr(hospital, "write_token", None) and given and secrets.compare_digest(given, hospital.write_token))


WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def require_token(request: Request, hospital: Hospital = Depends(get_hospital)) -> Hospital:
    """Bearer token of the FHIR API (data/his_mock/token, mode 600). Constant-time comparison."""
    if not bearer_ok(request, hospital):
        raise AuthError("a bearer token is required (data/his_mock/token)")
    return hospital


class AuthError(Exception):
    """A missing or wrong bearer token (answered as a FHIR OperationOutcome, 401)."""


def operation_outcome(severity, code, text):
    return {"resourceType": "OperationOutcome",
            "issue": [{"severity": severity, "code": code, "diagnostics": text}]}


def mounted():
    """The routers whose modules exist."""
    here = Path(__file__).parent
    return [(name, prefix) for name, prefix in ROUTERS if (here / f"{name}.py").exists()]


def is_screen(path):
    """A human screen (HTML answers): under /his or /desk, not the JSON APIs."""
    p = path.rstrip("/") or "/"
    if p.startswith("/his/api") or p.startswith("/desk/api"):
        return False
    return p == "/his" or p.startswith("/his/") or p == "/desk" or p.startswith("/desk/")


def _login_redirect(request):
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/his/login?next={quote(target, safe='')}&flash={quote('Please sign in.')}&level=warn",
                            status_code=303)


def create_app(data_dir=None, open_api=None) -> FastAPI:
    """open_api: the JSON APIs (/his/api, /desk/api) without a login or token, for unit tests and throw-away e2e copies only;
    default from TB_HIS_MOCK_OPEN_API=1, otherwise closed."""
    app = FastAPI(title=NAME, version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hospital = Hospital(data_dir)
    app.state.open_api = (os.environ.get("TB_HIS_MOCK_OPEN_API") == "1") if open_api is None else bool(open_api)

    @app.middleware("http")
    async def security_headers(request, call_next):
        """Plain hardening headers on every answer of the HIMS itself; the PACS viewer keeps Orthanc's own answer."""
        response = await call_next(request)
        if not request.url.path.startswith("/api/tb/pacs"):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            if auth.protection(request.url.path) in ("screen", "view") or request.url.path.startswith("/his/login"):
                response.headers.setdefault("Cache-Control", "no-store")
            if (response.headers.get("content-type") or "").startswith("text/html"):
                response.headers.setdefault("Content-Security-Policy", ui.CSP)  # security review #20
        return response

    @app.middleware("http")
    async def same_origin_writes(request, call_next):
        """A browser page from another origin cannot post to the screens or the JSON APIs. curl and tests send no Origin."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin") or ""
            if origin and urlparse(origin).netloc.lower() != (request.headers.get("host") or "").lower():
                return JSONResponse(operation_outcome("error", "forbidden", "cross-origin writes are refused"),
                                    status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def require_login(request, call_next):
        """Every human screen needs the session cookie (auth.protection); /view/reports also takes the read token. The JSON APIs
        (security review #3, #13): reads take the read or the write token or a staff session; writes take the write token (a machine
        caller) or a staff session whose roles allow the same action on the screens (auth.api_permission). The FHIR read token
        never changes anything."""
        kind = auth.protection(request.url.path)
        if kind == "api" and request.app.state.open_api:
            kind = None
        if kind == "api":
            hospital = request.app.state.hospital
            write = request.method in WRITE_METHODS
            if write_bearer_ok(request, hospital) or (not write and bearer_ok(request, hospital)):
                request.state.api_token = "write" if write else "read"
                return await call_next(request)
            session = hospital.accounts.session_for(request)
            if session:
                if write:
                    perm = auth.api_permission(request.url.path, hospital.store)
                    if not perm or not auth.allowed(session.get("roles"), perm):
                        return JSONResponse({"error": "forbidden", "detail": auth.refusal(perm) if perm else
                                             f"{auth.REFUSED}: this change is made on the screens."}, status_code=403)
                request.state.session = session
                return await call_next(request)
            if write and bearer_ok(request, hospital):
                return JSONResponse({"error": "forbidden", "detail": "The read token changes nothing: send the write token (data/his_mock/write_token)."},
                                    status_code=403)
            return JSONResponse({"error": "login or integration token required"}, status_code=401)
        if kind:
            hospital = request.app.state.hospital
            session = hospital.accounts.session_for(request)
            if session:
                request.state.session = session
            elif kind == "view" and (bearer_ok(request, hospital) or write_bearer_ok(request, hospital)):
                pass
            else:
                return _login_redirect(request)
        return await call_next(request)

    modules = []
    for name, prefix in mounted():
        module = __import__(f"his_mock.{name}", fromlist=["router"])
        app.include_router(module.router, prefix=prefix)
        modules.append({"module": name, "path": prefix})

    @app.get("/")
    def root():
        h = app.state.hospital
        return {"name": NAME, "version": VERSION, "synthetic": True, "hospital": h.store.hospital["name"],
                "product": ui.PRODUCT, "fixture_version": h.store.meta.get("fixture_version"), "modules": modules,
                "login": "/his/login", "screens": [m[1] for m in ui.MODULES],
                "note": "Mock Indian hospital for the Vaidyx-TB demo. Every patient, doctor and number is invented."}

    @app.get("/health")
    def health():
        h = app.state.hospital
        return {"ok": True, "patients": len(h.store.patients), "reports": len(h.store.reports),
                "events": len(h.store.events), "accounts": len(h.accounts.accounts)}

    @app.get("/documents/{relative:path}")
    def document(relative: str, hospital: Hospital = Depends(require_token)):
        """A report PDF (or an outside report file) by its store path, token-protected (the Vaidyx app's path)."""
        p = hospital.document_path(relative)
        media = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}.get(p.suffix.lower(),
                                                                                          "application/octet-stream")
        return FileResponse(p, media_type=media, filename=p.name)

    @app.get("/view/reports/{report_id}/{version}")
    def view_report(report_id: str, version: int):
        """A report version's PDF inline for the human screens (session cookie) or a bearer-token client."""
        h = app.state.hospital
        r = h.store.report(report_id)
        v = next((v for v in (r or {}).get("versions", []) if v["version"] == version), None)
        path = ((v or {}).get("document") or {}).get("path")
        if not path:
            raise HTTPException(404, "no PDF for this report version (not rendered yet)")
        return FileResponse(h.document_path(path), media_type="application/pdf",
                            content_disposition_type="inline", filename=f"{report_id}-v{version}.pdf")

    def _screen_page(request, status, title, message):
        session = getattr(request.state, "session", None)
        back = auth.safe_next(urlparse(request.headers.get("referer") or "").path) if request.headers.get("referer") else "/his"
        body = f'<p><a href="{ui.esc(back)}">Back</a> | <a href="/his">Registration</a></p>'  # no javascript: link (the CSP refuses it)
        return _html(ui.page(title, body, active=None, user=session, flash=("bad", message)), status)

    def _html(text, status):
        from fastapi.responses import HTMLResponse

        return HTMLResponse(text, status_code=status)

    @app.exception_handler(AuthError)
    def auth_error(request, exc):
        return JSONResponse(operation_outcome("error", "login", str(exc)), status_code=401,
                            headers={"WWW-Authenticate": "Bearer"}, media_type="application/fhir+json")

    @app.exception_handler(auth.Forbidden)
    def forbidden(request, exc):
        if is_screen(request.url.path):
            return _screen_page(request, 403, "Not allowed", str(exc))
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

    @app.exception_handler(model.LifecycleError)
    def lifecycle_error(request, exc):
        if is_screen(request.url.path):
            return _screen_page(request, 409, "Not possible now", f"The hospital system refused this: {exc}")
        return JSONResponse({"error": "lifecycle", "detail": str(exc)}, status_code=409)

    @app.exception_handler(StarletteHTTPException)
    def http_error(request, exc):
        if is_screen(request.url.path) and exc.status_code in (403, 404, 405, 409, 422):
            titles = {403: "Not allowed", 404: "Not found", 405: "Not allowed", 409: "Not possible now", 422: "Check the form"}
            return _screen_page(request, exc.status_code, titles[exc.status_code], str(exc.detail))
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    def validation_error(request, exc):
        if is_screen(request.url.path):
            return _screen_page(request, 422, "Check the form", "A value in the request is not valid; open the page again.")
        return JSONResponse({"detail": exc.errors()}, status_code=422)

    return app
