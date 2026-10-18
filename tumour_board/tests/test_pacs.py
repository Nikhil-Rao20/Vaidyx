"""PACS images opened during the board (V2 item 6.3): what the app forwards to the PACS (classify / check), the per-user grants,
the proxy (headers both ways, streaming, errors, the viewer_opened audit) and the report's study from the hospital system.

Hermetic: the PACS is an httpx.MockTransport, the hospital system a fake client. No image is ever read (humans view them)."""
import asyncio
import base64
import gzip
import hashlib
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tumour_board import his_client, pacs, store
from tumour_board.tests import util

UID = "1.2.826.0.1.3680043.8.498.1001"
OTHER = "1.2.826.0.1.3680043.8.498.2002"
DOCTOR = {"user": "dr.rao", "admin": False, "known": True, "disabled": False}  # creates the ownerless test Case Files: an ownerless Case File is open to its creator and the coordinator only (security review finding 0)


@pytest.fixture(autouse=True)
def no_grants():
    pacs.clear()
    yield
    pacs.clear()


# ------------------------------------------------------------------------------------------------ classify / check
@pytest.mark.parametrize("path,query,expected", [
    ("ohif/", "", ("ohif_static", "")),
    ("ohif/app-config.js", "", ("ohif_static", "")),
    ("ohif/assets/favicon.ico", "", ("ohif_static", "")),
    ("ohif/viewer", f"StudyInstanceUIDs={UID}", ("ohif_viewer", UID)),
    ("ohif/viewer/", f"studyinstanceuids={UID}&SeriesInstanceUIDs=1.2", ("ohif_viewer", UID)),
    ("ohif/viewer", f"StudyInstanceUIDs={UID},{UID}", ("ohif_viewer", UID)),  # the same study twice is one study
    ("ohif/viewer", "", ("ohif_viewer", "")),
    ("ohif/segmentation", f"StudyInstanceUIDs={UID}", ("ohif_viewer", UID)),  # any OHIF page naming a study is a viewer page
    ("dicom-web/studies/" + UID, "", ("dicomweb", UID)),
    (f"dicom-web/studies/{UID}/series", "", ("dicomweb", UID)),
    (f"dicom-web/studies/{UID}/series/1.2.3/instances/1.2.4/frames/1", "", ("dicomweb", UID)),
    (f"dicom-web/studies/{UID}/series/1.2.3/metadata", f"StudyInstanceUID={UID}", ("dicomweb", UID)),
    ("dicom-web/studies", f"StudyInstanceUID={UID}&limit=1", ("dicomweb", UID)),
    ("dicom-web/studies", f"0020000D={UID}", ("dicomweb", UID)),
    ("dicom-web/studies/", f"0020000d={UID}", ("dicomweb", UID)),
    ("dicom-web/studies", f"includefield=all&0020000D={UID}&offset=0&fuzzymatching=false", ("dicomweb", UID)),
    (f"dicom-web/studies/{UID}/series", "includefield=all&SeriesInstanceUID=1.2.3", ("dicomweb", UID)),
])
def test_classify_forwarded(path, query, expected):
    assert pacs.classify(path, query) == expected


@pytest.mark.parametrize("path,query", [
    ("studies", ""), (f"studies/{UID}", ""), ("instances", ""), ("patients", ""), ("series", ""),
    ("tools/find", ""), ("tools/execute-script", ""), ("system", ""), ("app/explorer.html", ""), ("ui/app/", ""),
    ("plugins", ""), ("plugins/ohif", ""), ("wado", f"requestType=WADO&studyUID={UID}"), ("ohif", ""),
    ("dicom-web/servers", ""), ("dicom-web/info", ""), ("dicom-web/studies", ""), ("dicom-web/studies", "limit=100"),
    ("dicom-web/series", ""), ("dicom-web/studies", f"StudyInstanceUID={UID}&StudyInstanceUID={OTHER}"),
    ("dicom-web/studies", f"StudyInstanceUID={UID},{OTHER}"), ("dicom-web/studies", f"StudyInstanceUID={UID}&0020000D={OTHER}"),
    ("dicom-web/studies", "StudyInstanceUID=1.2.*"), ("dicom-web/studies", "StudyInstanceUID=1.2\\3.4"),
    (f"dicom-web/studies/{UID}/series", f"StudyInstanceUID={OTHER}"),
    ("dicom-web/studies/1.2.abc", ""), ("dicom-web/studies/1.2..3", ""), ("dicom-web/studies/" + "1." * 40 + "1", ""),
    ("dicom-web/studies/*", ""), ("ohif/viewer", f"StudyInstanceUIDs={UID},{OTHER}"),
    ("ohif/viewer", f"StudyInstanceUIDs={UID}&StudyInstanceUIDs={OTHER}"), ("ohif/viewer", "StudyInstanceUIDs=1.2;3"),
    ("ohif/../tools/find", ""), (f"dicom-web/studies/{UID}/../../../patients", ""), ("ohif/%2e%2e/system", ""),
    ("ohif//system", ""), ("/system", ""), ("ohif/a\\..\\system", ""), ("", ""),
    # the study tag in another spelling, a key cut at a NUL, a second (blank) study key, a wider filter: Orthanc would read these as a
    # study list (Phase 6 review S1)
    ("dicom-web/studies", f"StudyInstanceUID={UID}&0020,000D="), ("dicom-web/studies", f"StudyInstanceUID={UID}&StudyInstanceUID%00="),
    ("dicom-web/studies", f"StudyInstanceUID={UID}&0020,000d={OTHER}"), ("dicom-web/studies", f"StudyInstanceUID={UID}&(0020,000D)={OTHER}"),
    ("dicom-web/studies", f"StudyInstanceUID={UID}&PatientName="), ("dicom-web/studies", f"StudyInstanceUID={UID}&StudyInstanceUID="),
    ("dicom-web/studies", f"StudyInstanceUID={UID}&ModalitiesInStudy=MG"), (f"dicom-web/studies/{UID}/series", f"0020,000D={OTHER}"),
    (f"dicom-web/studies/{UID}/series", f"StudyInstanceUID%00={OTHER}"), ("ohif/viewer", f"StudyInstanceUIDs={UID}&x%00y=1"),
    (f"dicom-web/studies/{UID}/metadata", "SeriesInstanceUID=1.2%003"),
])
def test_classify_refused(path, query):
    assert pacs.classify(path, query) == (None, "")


def test_check_roles_grants_and_kinds():
    q = f"StudyInstanceUIDs={UID}"
    for roles in ({"user": "x", "admin": False, "known": False}, {**DOCTOR, "disabled": True}, None):
        assert pacs.check("ohif/app-config.js", "", roles) == (403, "Your account is not placed in any department.")
    assert pacs.check("tools/find", "", DOCTOR) == (404, pacs.NOT_REACHABLE)
    assert "Only the image viewer" in pacs.NOT_REACHABLE
    assert pacs.check("ohif/app-config.js", "", DOCTOR) is None
    no = (403, "Open the images from the imaging report in the Case File first.")
    assert pacs.check("ohif/viewer", q, DOCTOR) == no and pacs.check("ohif/viewer", "", DOCTOR) == no
    assert pacs.check(f"dicom-web/studies/{UID}/series", "", DOCTOR) == no
    # a Vaidyx admin needs a grant like everyone (the audit trail stays honest)
    admin = {"user": "vx.admin", "admin": True, "known": True}
    assert pacs.check("ohif/viewer", q, admin) == no
    store.create_case("TB-PACS", util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-PACS", "d1")
    assert pacs.check("ohif/viewer", q, DOCTOR) is None
    assert pacs.check(f"dicom-web/studies/{UID}/series", "", DOCTOR) is None
    assert pacs.check("dicom-web/studies", f"StudyInstanceUID={UID}", DOCTOR) is None
    assert pacs.check(f"dicom-web/studies/{OTHER}/series", "", DOCTOR) == no  # another study
    assert pacs.check("ohif/viewer", q, admin) == no  # another user's grant does not count
    assert pacs.check("tools/find", "", admin) == (404, pacs.NOT_REACHABLE)


def test_check_follows_the_case_file_scope():
    """A grant is re-checked against the Case File's scope (owner, participants, the department asked): a referral accepted elsewhere
    or a participant removed ends the viewing within a minute; a grant on a Case File that no longer exists never forwards."""
    q = f"StudyInstanceUIDs={UID}"
    c = store.create_case("TB-OWNED", util.PATIENT, "breast", created_by="test"); c["department"] = "breast_surgery"; store.save_case(c)
    breast = {"user": "dr.nair", "admin": False, "known": True, "departments": {"breast_surgery": "doctor"}}
    rad = {"user": "dr.rao", "admin": False, "known": True, "departments": {"radiology": "doctor"}}
    pacs.grant("dr.nair", UID, "TB-OWNED", "d1"); pacs.grant("dr.rao", UID, "TB-OWNED", "d1")
    assert pacs.check("ohif/viewer", q, breast) is None
    assert pacs.check("ohif/viewer", q, rad) == (403, pacs.NO_GRANT)  # not the owner, no part in the Case File
    c["department"] = "medical_oncology"; store.save_case(c)  # the Case File moved (a referral accepted elsewhere)
    assert pacs.check("ohif/viewer", q, breast) is None  # within the minute the answer is cached
    pacs._access_cache.clear()
    assert pacs.check("ohif/viewer", q, breast) == (403, pacs.NO_GRANT)
    pacs.grant("dr.rao", UID, "TB-GONE", "d1"); pacs._access_cache.clear()
    assert pacs.check("ohif/viewer", q, rad) == (403, pacs.NO_GRANT)


def test_revoke_ends_the_grants_of_a_deleted_case_file():
    q = f"StudyInstanceUIDs={UID}"
    for cid in ("TB-A", "TB-B"):
        store.create_case(cid, util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-A", "d1"); pacs.grant("dr.mehta", UID, "TB-A", "d1"); pacs.grant("dr.rao", OTHER, "TB-B", "d2")
    assert pacs.check("ohif/viewer", q, DOCTOR) is None
    assert pacs.revoke("TB-A") == 2 and pacs.revoke("TB-A") == 0
    assert pacs.check("ohif/viewer", q, DOCTOR) == (403, pacs.NO_GRANT) and pacs.granted("dr.mehta", UID) is None
    assert pacs.granted("dr.rao", OTHER)["case_id"] == "TB-B"  # another Case File's grant stays
    store.create_case("TB-A", util.PATIENT, "lung_nsclc", created_by="dr.rao") if not store.get_case("TB-A") else None
    assert pacs.check("ohif/viewer", q, DOCTOR) == (403, pacs.NO_GRANT)  # a Case File re-created under the same id starts without grants


def test_forward_query_rebuilds_the_study_search():
    assert pacs.forward_query("dicom-web/studies", f"includefield=all&0020000D={UID}&limit=2&offset=0") == f"StudyInstanceUID={UID}&includefield=all&limit=2&offset=0"
    assert pacs.forward_query("dicom-web/studies/", f"StudyInstanceUID={UID}") == f"StudyInstanceUID={UID}"
    assert pacs.forward_query(f"dicom-web/studies/{UID}/series", "includefield=all&SeriesInstanceUID=1.2.3") == "includefield=all&SeriesInstanceUID=1.2.3"
    assert pacs.forward_query("ohif/viewer", f"StudyInstanceUIDs={UID}") == f"StudyInstanceUIDs={UID}"
    assert pacs.forward_query("ohif/app-config.js", "") == ""


def test_grants_expire_and_are_per_user():
    g = pacs.grant("dr.rao", UID, "TB-PACS", "d1", ttl_hours=1, now=1000.0)
    assert g["case_id"] == "TB-PACS" and g["doc_id"] == "d1" and g["expires"] == 1000.0 + 3600
    assert pacs.granted("dr.rao", UID, now=1000.0 + 3599)["doc_id"] == "d1"
    assert pacs.granted("dr.mehta", UID, now=1001.0) is None
    assert pacs.granted("dr.rao", OTHER, now=1001.0) is None
    assert pacs.granted("dr.rao", UID, now=1000.0 + 3600) is None
    assert pacs.granted("dr.rao", UID, now=1000.0) is None  # dropped once expired
    pacs.grant("dr.rao", UID, "TB-PACS", "d2")  # the default 12 hours, from now
    assert pacs.granted("dr.rao", UID)["doc_id"] == "d2"
    with pytest.raises(ValueError):
        pacs.grant("dr.rao", "1.2.*", "TB-PACS", "d1")
    pacs.clear()
    assert pacs.granted("dr.rao", UID) is None


def test_viewer_url_and_base_url(data_root, monkeypatch):
    assert pacs.viewer_url(UID) == f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}"
    assert pacs.classify(pacs.viewer_url(UID)[len(pacs.PREFIX) + 1:].split("?")[0], f"StudyInstanceUIDs={UID}") == ("ohif_viewer", UID)
    assert pacs.base_url() == "http://127.0.0.1:8042"
    (data_root / "his.json").write_text(json.dumps({"pacs_url": "http://127.0.0.1:9042/orthanc/"}))
    assert pacs.base_url() == "http://127.0.0.1:9042/orthanc"


# ------------------------------------------------------------------------------------------------ the proxy
class Body(httpx.AsyncByteStream):
    """A body streamed like a network answer (httpx.Response(content=...) is read up front, which the proxy never sees)."""

    def __init__(self, data: bytes):
        self.data = data

    async def __aiter__(self):
        yield self.data


def answer(status, headers, data):
    return httpx.Response(status, headers={**headers, "Content-Length": str(len(data))}, stream=Body(data))


class PACS:
    """A fake PACS: records every request it gets and answers by path."""

    def __init__(self):
        self.seen = []
        self.fail = None
        self.page = b""

    def handler(self, request: httpx.Request):
        if self.fail:
            raise self.fail("down", request=request)
        self.seen.append(request)
        h = {"Set-Cookie": "orthanc=1", "X-Orthanc-Secret": "s", "Server": "Orthanc", "ETag": '"e1"', "Cache-Control": "no-cache"}
        if request.headers.get("range"):
            return answer(206, {**h, "Content-Type": "application/octet-stream", "Content-Range": "bytes 0-3/10",
                                "Accept-Ranges": "bytes"}, b"DICM")
        if request.url.path.endswith("/viewer"):
            return answer(200, {**h, "Content-Type": "text/html"}, b"<html>OHIF</html>")
        if request.url.path.endswith(".html"):  # an OHIF page with inline scripts, gzipped like Orthanc may send it
            return answer(200, {**h, "Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"}, gzip.compress(self.page))
        return answer(200, {**h, "Content-Type": "application/dicom+json"}, b'[{"study": 1}]')


@pytest.fixture
def pacs_app(monkeypatch):
    fake = PACS()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(pacs, "_client", lambda: client)
    app = FastAPI()
    who = {"roles": DOCTOR}

    @app.api_route("/api/tb/pacs/{path:path}", methods=["GET", "HEAD", "POST"])
    async def route(request: Request, path: str):
        return await pacs.proxy(request, path, who["roles"])
    with TestClient(app) as tc:
        yield tc, fake, who


def test_proxy_forwards_the_granted_study_only(pacs_app):
    tc, fake, who = pacs_app
    tc.cookies.set("session", "app-session-cookie")
    r = tc.get(f"/api/tb/pacs/dicom-web/studies/{UID}/series", headers={"Authorization": "Bearer app"})
    assert r.status_code == 403 and r.json()["detail"].startswith("Open the images") and not fake.seen
    assert tc.get("/api/tb/pacs/tools/find").status_code == 404 and not fake.seen
    store.create_case("TB-PACS", util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-PACS", "d1")
    r = tc.get(f"/api/tb/pacs/dicom-web/studies/{UID}/series?includefield=all&limit=5",
               headers={"Authorization": "Bearer app", "Accept": "application/dicom+json", "X-Custom": "no",
                        "If-None-Match": '"e0"', "Host": "tb.hospital.example:7000"})
    assert r.status_code == 200 and r.json() == [{"study": 1}]
    up = fake.seen[-1]
    assert str(up.url) == f"http://127.0.0.1:8042/dicom-web/studies/{UID}/series?includefield=all&limit=5"
    assert up.method == "GET"
    assert "cookie" not in up.headers and "authorization" not in up.headers and "x-custom" not in up.headers
    assert up.headers["accept"] == "application/dicom+json" and up.headers["if-none-match"] == '"e0"'
    assert up.headers["x-forwarded-host"] == "tb.hospital.example:7000" and up.headers["x-forwarded-proto"] == "http"
    assert up.headers["x-forwarded-prefix"] == "/api/tb/pacs"
    assert up.headers["forwarded"] == "host=tb.hospital.example:7000;proto=http"
    # only the allow-listed response headers come back: never Set-Cookie
    assert "set-cookie" not in r.headers and "x-orthanc-secret" not in r.headers and r.headers.get("server") != "Orthanc"
    assert r.headers["etag"] == '"e1"' and r.headers["cache-control"] == "no-cache"
    assert r.headers["content-type"] == "application/dicom+json" and r.headers["content-length"] == "14"
    assert "orthanc" not in tc.cookies
    # the QIDO study search naming the granted study
    assert tc.get(f"/api/tb/pacs/dicom-web/studies?StudyInstanceUID={UID}").status_code == 200
    assert str(fake.seen[-1].url).endswith(f"/dicom-web/studies?StudyInstanceUID={UID}")
    # the study search is rebuilt: the one study first, then the search parameters only (review S1)
    assert tc.get(f"/api/tb/pacs/dicom-web/studies?includefield=all&0020000D={UID}&limit=2").status_code == 200
    assert str(fake.seen[-1].url).endswith(f"/dicom-web/studies?StudyInstanceUID={UID}&includefield=all&limit=2")
    n = len(fake.seen)
    for q in (f"StudyInstanceUID={UID}&0020,000D=", f"StudyInstanceUID={UID}&StudyInstanceUID%00=", f"StudyInstanceUID={UID}&PatientName=",
              f"StudyInstanceUID={UID}&StudyInstanceUID="):
        assert tc.get(f"/api/tb/pacs/dicom-web/studies?{q}").status_code == 404, q
    assert len(fake.seen) == n
    # the OHIF app is forwarded without a grant check (no study in it), still only for a placed user
    assert tc.get("/api/tb/pacs/ohif/app-config.js").status_code == 200
    who["roles"] = {"user": "nobody", "admin": False, "known": False}
    n = len(fake.seen)
    assert tc.get("/api/tb/pacs/ohif/app-config.js").status_code == 403 and len(fake.seen) == n


def test_proxy_gives_the_viewer_its_own_policy(pacs_app):
    """The OHIF files carry the viewer's own policy (the app's would stop its inline start-up scripts and the room screen's frame):
    the inline scripts of its page by hash only, WebAssembly decoders, workers, framed by this app only. DICOMweb answers get none."""
    tc, fake, who = pacs_app
    fake.page = b"<html><script>var a=1;</script><script src='./app.js'></script><script type=module>b()</script></html>"
    r = tc.get("/api/tb/pacs/ohif/start.html")
    assert r.status_code == 200 and r.content == fake.page and "content-encoding" not in r.headers
    assert r.headers["content-length"] == str(len(fake.page))
    csp = r.headers["content-security-policy"]
    for js in (b"var a=1;", b"b()"):
        assert f"'sha256-{base64.b64encode(hashlib.sha256(js).digest()).decode()}'" in csp
    script = csp.split("script-src")[1].split(";")[0]
    assert csp.count("'sha256-") == 2 and "unsafe-inline" not in script and "'unsafe-eval'" not in csp and "'wasm-unsafe-eval'" in script
    assert "frame-ancestors 'self'" in csp and "worker-src 'self' blob:" in csp and "object-src 'none'" in csp
    assert tc.get("/api/tb/pacs/ohif/app-config.js").headers["content-security-policy"] == pacs.viewer_csp()
    assert "'sha256-" not in pacs.viewer_csp()
    store.create_case("TB-PACS", util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-PACS", "d1")
    r = tc.get(f"/api/tb/pacs/dicom-web/studies/{UID}/series")
    assert r.status_code == 200 and "content-security-policy" not in r.headers
    r = tc.head("/api/tb/pacs/ohif/app-config.js")
    assert r.status_code == 200 and r.headers["content-security-policy"] == pacs.viewer_csp()


def test_app_headers_keep_the_viewer_policy_and_let_this_app_frame_it(monkeypatch):
    """core/middleware.py (owner's go, 18 Oct): under /api/tb/pacs/ the proxy's viewer policy is kept and only this app may frame
    it (the meeting room screen); every other answer keeps nonce-only scripts and no framing at all."""
    from core.middleware import SecurityHeadersMiddleware
    fake = PACS()
    fake.page = b"<html><script>start()</script></html>"
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(pacs, "_client", lambda: client)
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.api_route("/api/tb/pacs/{path:path}", methods=["GET", "HEAD"])
    async def route(request: Request, path: str):
        return await pacs.proxy(request, path, DOCTOR)

    @app.get("/tb-nik/x")
    def page():
        return {"ok": True}
    with TestClient(app) as tc:
        r = tc.get("/api/tb/pacs/ohif/start.html")
        assert r.status_code == 200 and r.headers["x-frame-options"] == "SAMEORIGIN"
        assert r.headers["content-security-policy"] == pacs.viewer_csp(fake.page)
        r = tc.get(f"/api/tb/pacs/dicom-web/studies/{UID}/series")  # refused (no grant): still framed by this app only
        assert r.status_code == 403 and r.headers["x-frame-options"] == "SAMEORIGIN"
        assert r.headers["content-security-policy"] == "default-src 'self'; frame-ancestors 'self'"
        r = tc.get("/tb-nik/x")
        assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert "'nonce-" in r.headers["content-security-policy"] and "'wasm-unsafe-eval'" not in r.headers["content-security-policy"]


def test_proxy_range_head_post_and_errors(pacs_app):
    tc, fake, who = pacs_app
    store.create_case("TB-PACS", util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-PACS", "d1")
    frame = f"/api/tb/pacs/dicom-web/studies/{UID}/series/1.2.3/instances/1.2.4/frames/1"
    r = tc.get(frame, headers={"Range": "bytes=0-3"})
    assert r.status_code == 206 and r.content == b"DICM"
    assert r.headers["content-range"] == "bytes 0-3/10" and r.headers["accept-ranges"] == "bytes"
    assert fake.seen[-1].headers["range"] == "bytes=0-3"
    assert tc.head(frame).status_code == 200 and fake.seen[-1].method == "GET"  # Orthanc answers HEAD with 404: asked with GET, headers only (18 Oct)
    n = len(fake.seen)
    r = tc.post(frame, content=b"x")
    assert r.status_code == 405 and len(fake.seen) == n
    fake.fail = httpx.ConnectError
    r = tc.get(frame)
    assert r.status_code == 502 and r.json() == {"detail": "The PACS did not answer: ConnectError"}
    fake.fail = httpx.ReadTimeout
    assert tc.get(frame).json() == {"detail": "The PACS did not answer: ReadTimeout"}


def test_proxy_viewer_open_is_audited_once_per_page(pacs_app):
    tc, fake, who = pacs_app
    store.create_case("TB-PACS", util.PATIENT, "lung_nsclc", created_by="dr.rao")
    pacs.grant("dr.rao", UID, "TB-PACS", "d1")
    r = tc.get(f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}")
    assert r.status_code == 200 and b"OHIF" in r.content
    assert str(fake.seen[-1].url) == f"http://127.0.0.1:8042/ohif/viewer?StudyInstanceUIDs={UID}"
    tc.get(f"/api/tb/pacs/dicom-web/studies/{UID}/series")
    tc.get("/api/tb/pacs/ohif/app-config.js")
    ev = [e for e in store.read_audit("TB-PACS") if e.get("kind") == "viewer_opened"]
    assert len(ev) == 1
    assert ev[0]["by"] == "dr.rao" and ev[0]["doc_id"] == "d1" and ev[0]["study_uid"] == UID
    assert store.verify_audit("TB-PACS")["ok"]
    # a refused viewer open is neither forwarded nor audited
    who["roles"] = {**DOCTOR, "user": "dr.mehta"}
    n = len(fake.seen)
    assert tc.get(f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}").status_code == 403 and len(fake.seen) == n
    assert len([e for e in store.read_audit("TB-PACS") if e.get("kind") == "viewer_opened"]) == 1


# ------------------------------------------------------------------------------------------------ the report's study
STUDY = {"id": "img-1", "ref": "ImagingStudy/img-1", "study_uid": UID, "accession": "VXH-ACC-0001", "modality": "CT",
         "status": "available", "viewer_url": "http://127.0.0.1:8042/ohif/viewer?StudyInstanceUIDs=" + UID,
         "dicomweb_url": "http://127.0.0.1:8042/dicom-web/studies/" + UID, "series": 3, "instances": 240,
         "started": "2026-10-01T10:00:00+05:30", "description": "CT THORAX CONTRAST (SYNTHETIC)"}


class FakeHIS:
    def __init__(self, study=None, error=None):
        self.study, self.error, self.asked = study, error, []

    async def imaging_study(self, ref):
        self.asked.append(ref)
        if self.error:
            raise self.error
        return self.study


def _report(case_id="TB-PACS", ref="ImagingStudy/img-1"):
    store.create_case(case_id, util.PATIENT, "lung_nsclc", created_by="dr.rao")
    doc = store.add_document_file(case_id, "ct_thorax_report.pdf", b"synthetic")
    if ref:
        doc["his"] = {"imaging_study_ref": ref}
        store.save_doc(case_id, doc)
    return doc


def test_study_for_doc_available_and_cached():
    doc = _report()
    his = FakeHIS(STUDY)
    s = asyncio.run(pacs.study_for_doc("TB-PACS", doc, his))
    assert his.asked == ["ImagingStudy/img-1"]
    assert s["available"] is True and s["study_uid"] == UID and s["modality"] == "CT" and s["series"] == 3
    assert s["viewer_url"] == f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={UID}"  # the app's route, never the PACS directly
    assert "127.0.0.1:8042" not in json.dumps(s)
    saved = store.get_doc("TB-PACS", doc["doc_id"])["his"]
    assert saved["imaging_study_ref"] == "ImagingStudy/img-1"
    assert saved["study"]["available"] is True and saved["study"]["checked"] and "viewer_url" not in saved["study"]
    # the hospital system is down: the cached answer, with the viewer url rebuilt
    fresh = store.get_doc("TB-PACS", doc["doc_id"])
    s2 = asyncio.run(pacs.study_for_doc("TB-PACS", fresh, FakeHIS(error=his_client.HISError("the HIS did not answer"))))
    assert s2["available"] is True and s2["viewer_url"] == s["viewer_url"] and "checked" not in s2
    s3 = asyncio.run(pacs.study_for_doc("TB-PACS", fresh, FakeHIS(error=httpx.ConnectError("down"))))
    assert s3["study_uid"] == UID


def test_study_for_doc_not_ready_missing_and_errors():
    doc = _report()
    s = asyncio.run(pacs.study_for_doc("TB-PACS", doc, FakeHIS({**STUDY, "status": "registered"})))
    assert s["available"] is False and s["reason"] == "Images not in the PACS yet (study registered)"
    assert "viewer_url" not in s and s["accession"] == "VXH-ACC-0001"
    assert store.get_doc("TB-PACS", doc["doc_id"])["his"]["study"]["available"] is False
    s = asyncio.run(pacs.study_for_doc("TB-PACS", doc, FakeHIS(None)))
    assert s == {"available": False, "reason": "The hospital system holds no imaging study for this report"}
    s = asyncio.run(pacs.study_for_doc("TB-PACS", doc, FakeHIS({**STUDY, "study_uid": "1.2.*"})))
    assert s["available"] is False and "viewer_url" not in s
    # no ref: not an imaging report from the hospital system
    other = store.add_document_file("TB-PACS", "cbc_report.pdf", b"synthetic 2")
    assert asyncio.run(pacs.study_for_doc("TB-PACS", other, FakeHIS(STUDY))) is None
    # an HIS error without a cached answer is raised
    plain = store.add_document_file("TB-PACS", "mri_report.pdf", b"synthetic 3")
    plain["his"] = {"imaging_study_ref": "ImagingStudy/img-2"}
    with pytest.raises(his_client.HISError):
        asyncio.run(pacs.study_for_doc("TB-PACS", plain, FakeHIS(error=his_client.HISError("the HIS did not answer"))))
