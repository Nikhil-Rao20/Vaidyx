"""PACS images opened during the board (plan item V2-6.3): the image viewer (OHIF) and the study it was opened on, reached only
through the Vaidyx-TB app (logged in, audited), never directly.

Scope (project rules): humans view the images; no model ever reads them. Nothing here reads pixel data, downloads instances or
hands an image to any agent; the app only forwards the viewer's own requests to the PACS (Orthanc, 127.0.0.1:8042 in the demo).

    viewer_url(study_uid)                       the app path that opens OHIF on one study
    grant(user, study_uid, case_id, doc_id)     the route calls this after checking the user may read the Case File document; the
                                                viewer and DICOMweb requests of that study are then forwarded for that user only
    classify(path, query) / check(...)          which requests are forwarded at all: the OHIF app, the viewer page of a granted study
                                                and DICOMweb under that study; never Orthanc's REST API, explorer, plugins or a
                                                study list
    proxy(request, path, roles)                 GET / HEAD only, a short header allow-list both ways (never cookies or the app's
                                                Authorization), the body streamed; the viewer page open is audited on the Case
                                                File (`viewer_opened`), the hundreds of image requests of a study are not
    study_for_doc(case_id, doc, client)         the imaging report's study from the hospital system, cached on the document

Grants live in memory (a restart asks the user to open the images from the report again). A Vaidyx admin needs a grant like
everyone, so every study viewed has an "opened from this report" entry behind it.
"""
import re
import time
from urllib.parse import parse_qsl, quote

import httpx
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse, Response, StreamingResponse

from . import his_client, store

PREFIX = "/api/tb/pacs"
DEFAULT_PACS_URL = his_client.DEFAULT_PACS_URL
_UID = re.compile(r"^[0-9][0-9.]{0,63}$")
_PATH_BAD = re.compile(r"[%\\\s?#\x00-\x1f\x7f]")
REQ_HEADERS = ("accept", "accept-encoding", "range", "if-none-match", "if-modified-since", "if-range")
RESP_HEADERS = ("content-type", "content-length", "content-encoding", "content-range", "accept-ranges", "cache-control", "etag",
                "last-modified", "content-disposition", "vary")
NOT_PLACED = "Your account is not placed in any department."
NOT_REACHABLE = "Only the image viewer and the study it was opened on are reached through this route."
NO_GRANT = "Open the images from the imaging report in the Case File first."


def base_url() -> str:
    """The PACS root the viewer's requests go to (HIS settings `pacs_url`, default the demo's Orthanc)."""
    return str(his_client.settings().get("pacs_url") or DEFAULT_PACS_URL).strip().rstrip("/") or DEFAULT_PACS_URL


def valid_uid(uid) -> bool:
    """A DICOM UID: digits and dots only, at most 64 characters, no empty component."""
    uid = str(uid or "")
    return bool(_UID.match(uid)) and ".." not in uid and not uid.endswith(".")


def viewer_url(study_uid: str) -> str:
    return PREFIX + "/ohif/viewer?StudyInstanceUIDs=" + quote(str(study_uid), safe=".")


# ---------------------------------------------------------------------------------------------------- grants
_grants: dict[tuple, dict] = {}


def grant(user: str, study_uid: str, case_id: str, doc_id: str, ttl_hours: float = 12, now: float | None = None) -> dict:
    """Let `user` view `study_uid` for `ttl_hours` (opened from document `doc_id` of Case File `case_id`). ValueError on a bad UID."""
    if not valid_uid(study_uid):
        raise ValueError("not a valid study UID")
    now = time.time() if now is None else now
    for k in [k for k, g in _grants.items() if g["expires"] <= now]:
        _grants.pop(k, None)
    g = {"user": str(user or ""), "study_uid": study_uid, "case_id": case_id, "doc_id": doc_id, "granted": now,
         "expires": now + ttl_hours * 3600}
    _grants[(g["user"], study_uid)] = g
    return dict(g)


def granted(user: str, study_uid: str, now: float | None = None) -> dict | None:
    """The live grant of `user` on `study_uid`, or None (an expired grant is dropped)."""
    key = (str(user or ""), str(study_uid or ""))
    g = _grants.get(key)
    if g is None:
        return None
    if g["expires"] <= (time.time() if now is None else now):
        _grants.pop(key, None)
        return None
    return dict(g)


def clear():
    _grants.clear()


# ---------------------------------------------------------------------------------------------------- what is forwarded
def _uids(query: str, names: tuple) -> list[str]:
    """Every value of the query keys `names` (case-insensitive), comma lists split, blanks dropped, duplicates kept once."""
    out = []
    for k, v in parse_qsl(query or "", keep_blank_values=True):
        if k.lower() in names:
            for u in v.split(","):
                u = u.strip()
                if u and u not in out:
                    out.append(u)
    return out


def classify(path: str, query: str = "") -> tuple:
    """(kind, study_uid) of a request under the prefix: `path` without the leading slash, `query` the raw query string.

    ohif_static   the OHIF app (index, scripts, styles, app-config.js), uid ""
    ohif_viewer   the viewer page ohif/viewer?StudyInstanceUIDs=<one uid> (any OHIF page naming a study counts as a viewer page)
    dicomweb      dicom-web/studies/<uid>[/...], or the study search dicom-web/studies?StudyInstanceUID=<uid> (or 0020000D=)
    None          everything else: Orthanc's REST API and explorer, plugins, WADO-URI, dicom-web/servers or info, a study list
                  without a uid, more than one study, a malformed uid, path traversal. uid "" when there is none."""
    path = str(path or "")
    if path.startswith("/") or _PATH_BAD.search(path) or any(s in (".", "..") for s in path.split("/")) or "//" in path:
        return None, ""
    if path.startswith("ohif/"):
        rest = path[len("ohif/"):].rstrip("/")
        uids = _uids(query, ("studyinstanceuids",))
        if rest == "viewer" or rest.startswith("viewer/") or uids:
            if len(uids) != 1 or not valid_uid(uids[0]):
                return (None, "") if uids else ("ohif_viewer", "")  # several studies or a malformed uid: refused
            return "ohif_viewer", uids[0]
        return "ohif_static", ""
    if path.rstrip("/") == "dicom-web/studies":  # the study search: only when it names exactly one study
        uids = _uids(query, ("studyinstanceuid", "0020000d"))
        return ("dicomweb", uids[0]) if len(uids) == 1 and valid_uid(uids[0]) else (None, "")
    if path.startswith("dicom-web/studies/"):
        uid = path[len("dicom-web/studies/"):].split("/", 1)[0]
        q = _uids(query, ("studyinstanceuid", "0020000d"))
        if not valid_uid(uid) or (q and q != [uid]):  # a malformed uid, or a filter naming another study
            return None, ""
        return "dicomweb", uid
    return None, ""


def check(path: str, query: str, roles: dict) -> tuple | None:
    """None when the request may be forwarded for `roles` (org.roles()), else (status, plain message)."""
    if not isinstance(roles, dict) or roles.get("disabled") or (not roles.get("admin") and not roles.get("known")):
        return 403, NOT_PLACED
    kind, uid = classify(path, query)
    if kind is None:
        return 404, NOT_REACHABLE
    if kind == "ohif_static":
        return None
    if not uid or not granted(roles.get("user") or "", uid):
        return 403, NO_GRANT
    return None


# ---------------------------------------------------------------------------------------------------- the proxy
_CLIENT: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    """One shared client to the PACS (created on first use): 60 s timeout, redirects never followed."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), follow_redirects=False,
                                    limits=httpx.Limits(max_connections=64))
    return _CLIENT


def _query(request) -> str:
    q = request.url.query
    return q.decode() if isinstance(q, bytes) else str(q or "")


async def proxy(request, path: str, roles: dict) -> Response:
    """Forward one viewer request to the PACS for the logged-in user `roles` (org.roles()). Runs check() itself, so a route can never
    forward a refused request. GET and HEAD only."""
    if request.method not in ("GET", "HEAD"):
        return JSONResponse({"detail": "The image viewer only reads."}, status_code=405, headers={"Allow": "GET, HEAD"})
    query = _query(request)
    refused = check(path, query, roles)
    if refused:
        return JSONResponse({"detail": refused[1]}, status_code=refused[0])
    kind, uid = classify(path, query)
    user = roles.get("user") or ""
    if kind == "ohif_viewer":  # once per study opened; the static and DICOMweb requests (hundreds per study) are not audited
        g = granted(user, uid) or {}
        if g.get("case_id"):
            store.audit(g["case_id"], {"kind": "viewer_opened", "by": user, "doc_id": g.get("doc_id") or "", "study_uid": uid})
    url = base_url() + "/" + quote(path, safe="/:@!$&'()*+,;=-._~") + ("?" + query if query else "")
    host = request.headers.get("host") or ""
    scheme = request.url.scheme or "http"
    headers = {k: v for k, v in request.headers.items() if k.lower() in REQ_HEADERS}
    headers |= {"X-Forwarded-Host": host, "X-Forwarded-Proto": scheme, "X-Forwarded-Prefix": PREFIX,
                "Forwarded": f"host={host};proto={scheme}"}
    c = _client()
    try:
        up = await c.send(c.build_request(request.method, url, headers=headers), stream=True)
    except httpx.TransportError as e:  # connect, timeout, network
        return JSONResponse({"detail": f"The PACS did not answer: {type(e).__name__}"}, status_code=502)
    out = {k: v for k, v in up.headers.items() if k.lower() in RESP_HEADERS}
    return StreamingResponse(up.aiter_raw(), status_code=up.status_code, headers=out, background=BackgroundTask(up.aclose))


# ---------------------------------------------------------------------------------------------------- the report's study
def _study_view(cached: dict) -> dict:
    out = {k: v for k, v in cached.items() if k != "checked"}
    if out.get("available") and valid_uid(out.get("study_uid")):
        out["viewer_url"] = viewer_url(out["study_uid"])
    return out


async def study_for_doc(case_id: str, doc: dict, client) -> dict | None:
    """The imaging study behind an imaging report pulled from the hospital system (doc["his"]["imaging_study_ref"]), or None when
    the report names none. {"available": True, study fields, "viewer_url"} or {"available": False, "reason", study fields}. Only
    the study's description (UIDs, counts, status) is read; never pixel data, never an instance. The answer is cached on the
    document (doc["his"]["study"], with "checked"); when the hospital system cannot be reached, the cached answer is returned."""
    ref = (doc.get("his") or {}).get("imaging_study_ref")
    if not ref:
        return None
    try:
        s = await client.imaging_study(ref) if client is not None else None
    except (his_client.HISError, httpx.HTTPError):
        cached = (doc.get("his") or {}).get("study")
        if cached:
            return _study_view(cached)
        raise
    if not s:
        res = {"available": False, "reason": "The hospital system holds no imaging study for this report"}
    else:
        fields = {k: s.get(k) for k in ("study_uid", "accession", "modality", "status", "series", "instances", "started", "description")}
        status = s.get("status") or "unknown"
        if status != "available":
            res = {"available": False, "reason": f"Images not in the PACS yet (study {status})", **fields}
        elif not valid_uid(s.get("study_uid")):
            res = {"available": False, "reason": "The hospital system gave no valid study UID for this report", **fields}
        else:
            res = {"available": True, **fields}
    cached = {**res, "checked": store.now_iso()}
    doc.setdefault("his", {})["study"] = cached
    fresh = store.get_doc(case_id, doc["doc_id"]) if doc.get("doc_id") else None
    if isinstance(fresh, dict):  # write onto the stored document, not over edits made since `doc` was read
        fresh.setdefault("his", {})["study"] = cached
        store.save_doc(case_id, fresh)
    elif doc.get("doc_id"):
        store.save_doc(case_id, doc)
    return _study_view(cached)
