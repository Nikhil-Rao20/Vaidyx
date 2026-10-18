"""The PACS viewer behind the demo HIMS: GET / HEAD /api/tb/pacs/{path} streams to Orthanc (127.0.0.1:8042) for a
signed-in user. Mounted by app.py at /api/tb/pacs. SYNTHETIC images only; no model ever reads them.

Why the path looks like the Vaidyx one: the OHIF plugin of Orthanc is built with RouterBasename /api/tb/pacs/ohif/ and
the DICOMweb PublicRoot /api/tb/pacs/dicom-web/ (his_mock/orthanc.json), because the Vaidyx app proxies the viewer under
that prefix for its logged-in users. OHIF's routes and asset URLs are absolute under that base, so a second host that
wants to open the same viewer must serve the same prefix. The HIMS therefore proxies the SAME path prefix the viewer is
built for, and a link `/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=<study uid>` opens OHIF on :7130 as well.

Allowed: /ohif/... (the viewer app) and /dicom-web/... (QIDO / WADO-RS). Refused with a plain message: Orthanc's REST API
(/patients, /studies, /instances, /tools, /system ...), the explorer (/app), plugins, WADO-URI, path traversal, control
characters. The HIMS session cookie never leaves this server; only a short header allow-list is forwarded both ways.
"""
import asyncio
import os
import re
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

router = APIRouter()

PREFIX = "/api/tb/pacs"
ORTHANC_URL = os.environ.get("TB_HIS_MOCK_ORTHANC") or "http://127.0.0.1:8042"   # tests point it elsewhere
ALLOWED = ("ohif/", "dicom-web/")
_BAD = re.compile(r"[%\\\s?#\x00-\x1f\x7f]")
REQ_HEADERS = ("accept", "accept-encoding", "range", "if-none-match", "if-modified-since", "if-range")
RESP_HEADERS = ("content-type", "content-length", "content-encoding", "content-range", "accept-ranges", "cache-control",
                "etag", "last-modified", "content-disposition", "vary")
NOT_REACHABLE = "Only the image viewer (ohif) and DICOMweb (dicom-web) are reached through this route."
_CLIENT = None
_CLIENT_LOOP = None


def allowed(path):
    """True for a clean path under ohif/ or dicom-web/ (also the bare "ohif" and "dicom-web")."""
    p = str(path or "")
    if p.startswith("/") or _BAD.search(p) or "//" in p or any(s in (".", "..") for s in p.split("/")):
        return False
    if p in ("ohif", "dicom-web"):
        return True
    return p.startswith(ALLOWED)


def _client():
    """One pooled client per event loop (uvicorn runs one loop; the test client opens a new loop per request, and a
    client bound to a closed loop cannot be reused)."""
    global _CLIENT, _CLIENT_LOOP
    loop = asyncio.get_running_loop()
    if _CLIENT is None or _CLIENT.is_closed or _CLIENT_LOOP is not loop:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), follow_redirects=False,
                                    limits=httpx.Limits(max_connections=64))
        _CLIENT_LOOP = loop
    return _CLIENT


def upstream_url(path, query):
    return ORTHANC_URL.rstrip("/") + "/" + quote(path, safe="/:@!$&'()*+,;=-._~") + (f"?{query}" if query else "")


@router.api_route("/{path:path}", methods=["GET", "HEAD"])
async def pacs(path: str, request: Request):
    """Stream one viewer or DICOMweb request to Orthanc (the login is checked by the app middleware)."""
    if not allowed(path):
        return JSONResponse({"detail": NOT_REACHABLE}, status_code=404)
    q = request.url.query
    query = q.decode() if isinstance(q, bytes) else str(q or "")
    host = request.headers.get("host") or ""
    scheme = request.url.scheme or "http"
    headers = {k: v for k, v in request.headers.items() if k.lower() in REQ_HEADERS}
    headers.update({"X-Forwarded-Host": host, "X-Forwarded-Proto": scheme, "X-Forwarded-Prefix": PREFIX,
                    "Forwarded": f"host={host};proto={scheme}"})
    c = _client()
    try:
        # Orthanc's web server answers HEAD with 404, so a HEAD is sent upstream as a GET and only its headers are kept
        up = await c.send(c.build_request("GET", upstream_url(path, query), headers=headers), stream=True)
    except httpx.TransportError as e:
        return JSONResponse({"detail": f"The PACS did not answer: {type(e).__name__}. Start Orthanc (his_mock/orthanc.sh start)."},
                            status_code=502)
    out = {k: v for k, v in up.headers.items() if k.lower() in RESP_HEADERS}
    if request.method == "HEAD":
        await up.aclose()
        return Response(status_code=up.status_code, headers=out)
    return StreamingResponse(up.aiter_raw(), status_code=up.status_code, headers=out, background=BackgroundTask(up.aclose))


@router.api_route("/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
async def pacs_write(path: str, request: Request):
    return JSONResponse({"detail": "The image viewer only reads."}, status_code=405, headers={"Allow": "GET, HEAD"})
