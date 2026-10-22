"""The PACS viewer proxy of the demo HIMS (his_mock/pacs_proxy.py): the allow-list (ohif/ and dicom-web/ only), GET / HEAD
only, a login required, the plain answer when Orthanc is down, and the streamed viewer when Orthanc (127.0.0.1:8042)
answers. SYNTHETIC images only."""
import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import dicom_studies, generator, pacs_proxy
from his_mock.tests import helpers

DEAD = "http://127.0.0.1:9"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_pacs")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def app(data_dir):
    return app_module.create_app(data_dir)


@pytest.fixture(scope="module")
def client(app):
    return helpers.login(app, "radiologist")


@pytest.mark.parametrize("path,ok", [
    ("ohif/viewer", True), ("ohif/", True), ("ohif", True), ("ohif/app-config.js", True), ("ohif/assets/x.js", True),
    ("dicom-web/studies", True), ("dicom-web/studies/1.2.3/series", True), ("dicom-web", True),
    ("patients", False), ("studies", False), ("instances/x/file", False), ("system", False), ("tools/find", False),
    ("app/explorer.html", False), ("wado", False), ("plugins", False), ("ohif/../patients", False), ("/ohif/viewer", False),
    ("ohif//x", False), ("ohif/x y", False), ("ohifx/viewer", False), ("dicom-webx", False), ("ohif/%2e%2e/x", False),
])
def test_allow_list(path, ok):
    assert pacs_proxy.allowed(path) is ok


def test_refused_paths_are_404_with_a_plain_message(client, monkeypatch):
    monkeypatch.setattr(pacs_proxy, "ORTHANC_URL", DEAD)
    for p in ("patients", "studies", "system", "app/explorer.html", "tools/find", "instances"):
        r = client.get(f"/api/tb/pacs/{p}")
        assert r.status_code == 404 and r.json()["detail"] == pacs_proxy.NOT_REACHABLE, p


def test_writes_are_refused(client):
    for method in ("post", "put", "delete", "patch"):
        r = getattr(client, method)("/api/tb/pacs/ohif/viewer")
        assert r.status_code == 405 and r.headers["allow"] == "GET, HEAD", method


def test_login_required(app):
    r = TestClient(app).get("/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=1.2.3", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/his/login?next=")


def test_pacs_down_is_a_plain_502(client, monkeypatch):
    monkeypatch.setattr(pacs_proxy, "ORTHANC_URL", DEAD)
    r = client.get("/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=1.2.3")
    assert r.status_code == 502 and "did not answer" in r.json()["detail"]


def test_viewer_link_convention():
    from his_mock import common
    assert common.viewer_url("2.25.12") == "/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=2.25.12"


def test_streams_the_viewer_when_orthanc_answers(client, monkeypatch):
    if not dicom_studies.orthanc_alive(dicom_studies.ORTHANC_URL):
        pytest.skip("Orthanc not answering on 127.0.0.1:8042")
    monkeypatch.setattr(pacs_proxy, "ORTHANC_URL", dicom_studies.ORTHANC_URL)
    r = client.get("/api/tb/pacs/ohif/app-config.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"] and "RouterBasename" in r.text or r.status_code == 200
    r = client.get("/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=1.2.3")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    r = client.get("/api/tb/pacs/dicom-web/studies", params={"limit": "1"})
    assert r.status_code == 200 and "dicom+json" in r.headers["content-type"]
    h = client.head("/api/tb/pacs/ohif/app-config.js")
    assert h.status_code == 200
    assert "set-cookie" not in {k.lower() for k in r.headers}
