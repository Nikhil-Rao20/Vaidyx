"""The mock hospital's web app skeleton (his_mock/app.py): state, token, document serving."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import generator, paths


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_app")
    generator.build(d, documents=False, dicom=False, hl7=False)
    files = paths.layout(d)
    (files["documents"] / "sub").mkdir(parents=True, exist_ok=True)
    (files["documents"] / "sub" / "demo.pdf").write_bytes(b"%PDF-1.4 synthetic test file")
    return d


@pytest.fixture(scope="module")
def client(data_dir):
    return TestClient(app_module.create_app(data_dir))


def token(data_dir):
    return (Path(data_dir) / paths.TOKEN_NAME).read_text().strip()


def test_root_and_health(client):
    r = client.get("/").json()
    assert r["synthetic"] is True and "SYNTHETIC" in r["hospital"] and r["fixture_version"]
    assert isinstance(r["modules"], list)
    h = client.get("/health").json()
    assert h["ok"] and h["patients"] > 0 and h["reports"] > 0 and h["events"] > 0


def test_document_needs_token(client, data_dir):
    assert client.get("/documents/sub/demo.pdf").status_code == 401
    assert client.get("/documents/sub/demo.pdf", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/documents/sub/demo.pdf", headers={"Authorization": f"Bearer {token(data_dir)}"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    # the store path form `documents/<name>` works too; a token in the query string is never accepted
    assert client.get("/documents/documents/sub/demo.pdf", headers={"Authorization": f"Bearer {token(data_dir)}"}).status_code == 200
    assert client.get(f"/documents/sub/demo.pdf?token={token(data_dir)}").status_code == 401


def test_cross_origin_writes_are_refused(client):
    r = client.post("/his/api/registrations", json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["resourceType"] == "OperationOutcome"
    same = client.post("/his/api/registrations", json={}, headers={"Origin": "http://testserver"})
    assert same.status_code != 403


def test_document_never_leaves_documents_dir(client, data_dir):
    h = {"Authorization": f"Bearer {token(data_dir)}"}
    for bad in ("token", "store.json", "../token", "../../etc/passwd", "sub/../../store.json", "dicom/x.dcm"):
        assert client.get(f"/documents/{bad}", headers=h).status_code == 404, bad


def test_missing_store_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        app_module.create_app(tmp_path)


def test_mounted_routers_are_only_existing_modules():
    for name, prefix in app_module.mounted():
        assert (Path(app_module.__file__).with_name(name + ".py")).exists()
        assert prefix.startswith("/")


def test_save_round_trips(data_dir):
    h = app_module.Hospital(data_dir)
    n = len(h.store.events)
    with h.lock:
        p = next(iter(h.store.patients.values()))
        h.store.open_visit(p["id"], "Medical Oncology", when="2026-10-13T10:00:00+05:30")
        h.save()
    h.reload()
    assert len(h.store.events) == n + 1
    assert json.loads((Path(data_dir) / paths.STORE_NAME).read_text())["meta"]["marker"] == "SYNTHETIC"


def test_view_report_serves_the_rendered_pdf_inline(client, data_dir):
    h = app_module.Hospital(data_dir)
    r = next(iter(h.store.reports.values()))
    assert client.get(f"/view/reports/{r['id']}/1").status_code == 404  # documents=False: nothing rendered
    v = h.store.current_version(r)
    (Path(data_dir) / paths.DOCUMENTS_NAME / "x.pdf").write_bytes(b"%PDF-1.4 x")
    v["document"] = {"path": "documents/x.pdf", "sha256": "0" * 64}
    h.save()
    client.app.state.hospital.reload()
    resp = client.get(f"/view/reports/{r['id']}/{v['version']}")
    assert resp.status_code == 200 and "inline" in resp.headers["content-disposition"]
    assert client.get(f"/view/reports/{r['id']}/99").status_code == 404
    assert client.get("/view/reports/nope/1").status_code == 404
