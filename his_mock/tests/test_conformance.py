"""The NRCeS v6.5.0 light-schema conformance check of the mock hospital's FHIR API (plan item V2-1.3, gate row "Mock HIS
conformance"). SYNTHETIC data only; checks a temporary build."""
import copy
import io
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import fhir, paths
from his_mock.eval import conformance
from his_mock.model import Store

from .test_fhir import AMENDED, CBC, P01, full_build

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    return full_build(tmp_path_factory)


@pytest.fixture(scope="module")
def files(data_dir):
    return paths.layout(data_dir)


@pytest.fixture(scope="module")
def store(files):
    return Store.load(files["store"])


def test_the_whole_store_conforms(store, files):
    n, problems = conformance.check_store(store, files)
    assert problems == []
    # every served resource, plus one DocumentBundle per report version and the superseded DiagnosticReport versions
    assert n > len(store.reports) + len(store.patients) + len(store.encounters) > 0


def test_every_type_is_checked(store, files):
    seen = {r["resourceType"] for r in fhir.everything(store, files)}
    assert seen == set(fhir.TYPES)


def _patient(store):
    return fhir.patient(store, store.patients[P01])


@pytest.mark.parametrize("mutate, expect", [
    (lambda r: r.update(status="done"), "status 'done' not allowed"),
    (lambda r: r["meta"].pop("profile"), "meta.profile"),
    (lambda r: r["meta"].update(lastUpdated="2026-09-01T10:00:00Z"), "meta.lastUpdated"),
    (lambda r: r["identifier"][0].pop("system"), "identifier without system"),
    (lambda r: r["code"]["coding"][0].update(system="http://example.org/codes"), "coding system"),
    (lambda r: r.pop("conclusion"), "conclusion missing"),
    (lambda r: r.pop("resultsInterpreter"), "resultsInterpreter missing"),
    (lambda r: r.update(conclusion="Patient Aadhaar 2345 6789 0123 noted"), "Aadhaar-like"),
    (lambda r: r.update(conclusion="Normal \u2014 no change"), "em dash"),
])
def test_report_faults_are_found(store, files, mutate, expect):
    dr = fhir.diagnostic_report(store, store.reports[CBC], None, files)
    assert conformance.check_resource(dr) == []
    bad = copy.deepcopy(dr)
    mutate(bad)
    problems = conformance.check_resource(bad)
    assert any(expect in p for p in problems), problems


@pytest.mark.parametrize("mutate, expect", [
    (lambda r: r["identifier"].append({"type": {"coding": [{"system": fhir.NDHM_ID_TYPE, "code": "ADN",
                                                            "display": "Aadhaar number"}]},
                                       "system": "https://his.vaidyx-demo.invalid/identifier/x", "value": "XXXX"}),
     "type ADN"),
    (lambda r: r["identifier"].append({"type": fhir.id_type("MR"), "system": "https://his.vaidyx-demo.invalid/x",
                                       "value": "234567890123"}), "Aadhaar-like"),
    (lambda r: r["name"][0].update(text="Anitha Reddy"), "SYNTHETIC"),
    (lambda r: r["identifier"][0].update(value="UHID-1"), "synthetic pattern"),
    (lambda r: r["identifier"][0].pop("type"), "no type coding"),
    (lambda r: next(i for i in r["identifier"] if i["system"] == fhir.SYS["abha"]).update(value="99-2600-0000"),
     "not 14 digits"),
    (lambda r: r["identifier"].append({"type": fhir.id_type("MD"), "system": "https://doctor.ndhm.gov.in",
                                       "value": "VXREG-20101"}), "real ABDM registry"),
])
def test_patient_faults_are_found(store, mutate, expect):
    bad = copy.deepcopy(_patient(store))
    mutate(bad)
    problems = conformance.check_resource(bad)
    assert any(expect in p for p in problems), problems


def test_bundle_faults_are_found(store, files):
    b = fhir.document_bundle(store, store.reports[AMENDED], None, files)
    assert conformance.check_resource(b) == []
    rotated = copy.deepcopy(b)
    rotated["entry"] = rotated["entry"][1:] + rotated["entry"][:1]
    assert any("first entry is not a Composition" in p for p in conformance.check_resource(rotated))
    no_pat = copy.deepcopy(b)
    no_pat["entry"] = [e for e in no_pat["entry"] if e["resource"]["resourceType"] != "Patient"]
    assert any("does not resolve inside the bundle" in p for p in conformance.check_resource(no_pat))
    for key, expect in (("identifier", "identifier.system"), ("timestamp", "timestamp")):
        bad = copy.deepcopy(b)
        bad.pop(key)
        assert any(expect in p for p in conformance.check_resource(bad)), key
    bad = copy.deepcopy(b)
    bad["meta"].pop("versionId")
    assert any("meta.versionId" in p for p in conformance.check_resource(bad))
    bad = copy.deepcopy(b)
    bad["entry"][0]["resource"]["section"][0]["entry"].append({"reference": f"Patient/{P01}"})
    assert any("section.entry" in p for p in conformance.check_resource(bad))


def test_provenance_and_imaging_faults_are_found(store, files):
    prov = fhir.provenance(store, store.reports[AMENDED])
    assert conformance.check_resource(prov) == []
    bad = copy.deepcopy(prov)
    bad["extension"] = [e for e in bad["extension"] if e["url"] != fhir.EXT["signature_status"]]
    assert any("verification status" in p for p in conformance.check_resource(bad))
    bad = copy.deepcopy(prov)
    bad["meta"]["profile"] = [fhir.NRCES + "Provenance"]
    assert any("no Provenance" in p or "none for this type" in p for p in conformance.check_resource(bad))
    study = copy.deepcopy(next(s for s in store.imaging_studies.values() if fhir.has_images(s)))
    assert conformance.check_resource(fhir.imaging_study(store, study)) == []
    study["status"], study["uploaded"] = "available", True
    im = fhir.imaging_study(store, study)
    assert conformance.check_resource(im) == []
    im.pop("extension")
    assert any("viewer URL" in p for p in conformance.check_resource(im))


def test_document_reference_hash_must_match(store, files):
    doc = fhir.document_reference(store, store.reports[CBC], None, files)
    assert conformance.check_resource(doc) == []
    doc["content"][0]["attachment"]["hash"] = fhir._b64(b"\0" * 20)
    assert any("does not match the data" in p for p in conformance.check_resource(doc))


def test_cli_prints_ok_and_exits_0(data_dir):
    res = subprocess.run([PYTHON, "-m", "his_mock.eval.conformance", "--data", str(data_dir)], cwd=REPO,
                         capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stdout + res.stderr
    lines = res.stdout.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("CONFORMANCE OK: ") and lines[0].endswith(" resources checked")
    assert int(lines[0].split()[2]) > 0


def test_cli_lists_problems_and_exits_1(tmp_path, store):
    s = Store(copy.deepcopy(store.data))
    s.hospital["name"] = "Vaidyx Demo Hospital"            # no SYNTHETIC
    s.save(tmp_path / paths.STORE_NAME)
    out = io.StringIO()
    assert conformance.run(tmp_path, out=out) == 1
    lines = out.getvalue().strip().splitlines()
    assert lines[-1].startswith("CONFORMANCE FAILED: ") and lines[-1].endswith(" problems")
    assert any("SYNTHETIC" in line for line in lines[:-1]) and len(lines) <= 51


def test_cli_on_a_missing_store_fails_clearly(tmp_path):
    out = io.StringIO()
    assert conformance.run(tmp_path / "nowhere", out=out) == 1
    text = out.getvalue()
    assert "missing" in text and "his_mock.build" in text
    assert text.strip().splitlines()[-1] == "CONFORMANCE FAILED: 1 problems"


def test_cli_over_http(data_dir, monkeypatch):
    client = TestClient(app_module.create_app(data_dir))

    def fake_get(url, token=None):
        path = url.split("http://testserver", 1)[1]
        r = client.get(path, headers={"Authorization": f"Bearer {token}"} if token else {})
        assert r.status_code == 200, (path, r.text[:200])
        return r.json()

    monkeypatch.setattr(conformance, "_get", fake_get)
    out = io.StringIO()
    assert conformance.run(data_dir, url="http://testserver", out=out) == 0, out.getvalue()
    n_http, problems = conformance.check_http("http://testserver", (Path(data_dir) / paths.TOKEN_NAME).read_text().strip())
    assert problems == [] and n_http >= len(fhir.TYPES) + 3
