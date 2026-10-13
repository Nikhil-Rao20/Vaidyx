"""The mock hospital's web app (plan items V2-1.3, 1.5, 1.6): FastAPI on 127.0.0.1:7130, localhost only, never tunnelled.

    his_mock/serve.sh start|stop|status|restart     (uvicorn --factory his_mock.app:create_app, app venv)

One process holds one Store (data/his_mock/store.json or $TB_HIS_MOCK_DATA) behind a lock; every writer (the reporting
desk, the HIS screens) changes it through the Store transitions and calls Hospital.save(). Routers, each in its own module
and mounted only when the module exists:

    /fhir   the FHIR R4 read API in NRCeS v6.5.0 shapes (1.3), bearer token from data/his_mock/token
    /desk   the RIS / LIS reporting desk of the supporting departments (1.5), a human UI
    /his    the HIS screens: registration search, OP / IP timeline, referral and transfer (1.6), a human UI

The human UIs carry no login of their own: the port is bound to localhost and the demo reaches them through the Vaidyx-TB
app's logged-in routes (plan 6.3 / 8.1). Vaidyx-TB never imports this package. SYNTHETIC data only.
"""
import os
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import model, paths

NAME = "Vaidyx Demo Hospital HIS (SYNTHETIC)"
VERSION = "0.1"
DEFAULT_PORT = int(os.environ.get("TB_HIS_MOCK_PORT", "7130"))
ROUTERS = (("fhir", "/fhir"), ("desk", "/desk"), ("screens", "/his"))


class Hospital:
    """The app's state: the store, its files, a write lock and the API token."""

    def __init__(self, data_dir=None):
        self.files = paths.layout(data_dir)
        if not self.files["store"].exists():
            raise FileNotFoundError(f"{self.files['store']} missing: run python -m his_mock.build first")
        self.store = model.Store.load(self.files["store"])
        self.lock = threading.RLock()
        self.token = self.files["token"].read_text(encoding="utf-8").strip() if self.files["token"].exists() else None

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


def get_hospital(request: Request) -> Hospital:
    return request.app.state.hospital


def require_token(request: Request, hospital: Hospital = Depends(get_hospital)) -> Hospital:
    """Bearer token of the FHIR API (data/his_mock/token, mode 600). Constant-time comparison."""
    auth = request.headers.get("authorization") or ""
    given = auth[7:].strip() if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    if not hospital.token or not given or not secrets.compare_digest(given, hospital.token):
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


def create_app(data_dir=None) -> FastAPI:
    app = FastAPI(title=NAME, version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hospital = Hospital(data_dir)
    modules = []
    for name, prefix in mounted():
        module = __import__(f"his_mock.{name}", fromlist=["router"])
        app.include_router(module.router, prefix=prefix)
        modules.append({"module": name, "path": prefix})

    @app.get("/")
    def root():
        h = app.state.hospital
        return {"name": NAME, "version": VERSION, "synthetic": True, "hospital": h.store.hospital["name"],
                "fixture_version": h.store.meta.get("fixture_version"), "modules": modules,
                "note": "Mock Indian hospital for the Vaidyx-TB demo. Every patient, doctor and number is invented."}

    @app.get("/health")
    def health():
        h = app.state.hospital
        return {"ok": True, "patients": len(h.store.patients), "reports": len(h.store.reports),
                "events": len(h.store.events)}

    @app.get("/documents/{relative:path}")
    def document(relative: str, hospital: Hospital = Depends(require_token)):
        """A report PDF (or an outside report file) by its store path, token-protected."""
        p = hospital.document_path(relative)
        media = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}.get(p.suffix.lower(),
                                                                                          "application/octet-stream")
        return FileResponse(p, media_type=media, filename=p.name)

    @app.get("/view/reports/{report_id}/{version}")
    def view_report(report_id: str, version: int):
        """A report version's PDF inline for the human screens (desk, HIS screens) on localhost; no token (the port
        is bound to 127.0.0.1 and the demo reaches these screens through the Vaidyx-TB app's logged-in routes)."""
        h = app.state.hospital
        r = h.store.report(report_id)
        v = next((v for v in (r or {}).get("versions", []) if v["version"] == version), None)
        path = ((v or {}).get("document") or {}).get("path")
        if not path:
            raise HTTPException(404, "no PDF for this report version (not rendered yet)")
        return FileResponse(h.document_path(path), media_type="application/pdf",
                            content_disposition_type="inline", filename=f"{report_id}-v{version}.pdf")

    @app.exception_handler(AuthError)
    def auth_error(request, exc):
        return JSONResponse(operation_outcome("error", "login", str(exc)), status_code=401,
                            headers={"WWW-Authenticate": "Bearer"}, media_type="application/fhir+json")

    @app.exception_handler(model.LifecycleError)
    def lifecycle_error(request, exc):
        return JSONResponse({"error": "lifecycle", "detail": str(exc)}, status_code=409)

    return app
