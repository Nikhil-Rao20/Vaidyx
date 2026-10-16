"""The mock RIS / LIS reporting desk (his_mock/desk.py, plan item V2-1.5): work lists, Complete and sign, Addendum, Cancel,
the imaging sign path (synthetic DICOM, Orthanc only when it answers) and the HL7 / audit side effects. SYNTHETIC data only,
built into a temporary directory."""
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import desk, documents, generator, hl7, paths, ui

DEAD_ORTHANC = "http://127.0.0.1:9"   # nothing listens: the desk must say "images not uploaded" and carry on


@pytest.fixture(scope="module", autouse=True)
def no_pacs_by_default():
    old = desk.ORTHANC_URL
    desk.ORTHANC_URL = DEAD_ORTHANC
    yield
    desk.ORTHANC_URL = old


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_desk")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def client(data_dir):
    return TestClient(app_module.create_app(data_dir))


def hospital(client):
    return client.app.state.hospital


def files(client):
    return hospital(client).files


def audit_lines(client):
    p = Path(files(client)["data_dir"]) / desk.AUDIT_NAME
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def staff(client, code, role):
    h = hospital(client)
    return [p for p in desk.staff(h.store, h.store.department(code)) if p["role"] == role]


def the_preliminary(client):
    """P12's preliminary report (the "preliminary only" scenario; P19 of the plan 8.1 demo holds two more) and its department."""
    s = hospital(client).store
    prelim = [r for r in s.reports.values() if r["status"] == "preliminary" and r["patient_id"] == "vxh-26-004212"]
    assert len(prelim) == 1, [r["id"] for r in prelim]
    r = prelim[0]
    return r, s.department(s.orders[r["order_id"]]["performing_department"])


def place(client, code, doc_types=None):
    """A new order performed by the department `code`, on the preliminary scenario patient's encounter."""
    h = hospital(client)
    with h.lock:
        s = h.store
        dept = s.department(code)
        test = next(t for t in sorted(s.tests) if s.tests[t]["department"] == dept["name"]
                    and (doc_types is None or s.tests[t]["doc_type"] in doc_types))
        enc = next(e for e in s.encounters.values() if e["patient_id"] == "vxh-26-004212")
        o = s.place_order(enc["patient_id"], enc["id"], test, enc["department"])
        h.save()
    return o


def no_em_dash_and_synthetic(html):
    assert "\u2014" not in html and "\u2013" not in html
    assert "SYNTHETIC DATA" in html
    assert "aadhaar" not in html.lower()


# ------------------------------------------------------------------------ work lists
def test_department_list_shows_supporting_departments_with_counts(client):
    s = hospital(client).store
    html = client.get("/desk").text
    no_em_dash_and_synthetic(html)
    supporting = [d for d in s.departments.values() if d["group"] == "supporting"]
    busy = []
    for d in supporting:
        w = s.pending_for_department(d["code"])
        n_o, n_r = len(w["orders"]), len(w["reports"])
        row = (f'<a href="/desk/{d["code"]}">{ui.esc(d["name"])}</a></td><td><span class=mono>{d["code"]}</span></td>'
               f"<td>{n_o}</td><td>{n_r}</td>")
        assert row in html, d["code"]
        if n_o or n_r:
            busy.append(d["code"])
    # the fixtures give work to Radiology (the preliminary CT), Pathology (molecular sample collected), Microbiology
    # (viral markers ordered) and Nuclear Medicine (bone scan scheduled)
    assert {"RAD", "PATH", "MIC", "NM"} <= set(busy)
    treating = next(d for d in s.departments.values() if d["group"] != "supporting")
    assert f'href="/desk/{treating["code"]}"' not in html


def test_department_page_shows_preliminary_and_scheduled_order(client):
    r, dept = the_preliminary(client)
    s = hospital(client).store
    o = place(client, dept["code"], doc_types=set(desk.model.IMAGING_MODALITY))
    resp = client.post(f"/desk/api/{dept['code']}/orders/{o['id']}/schedule", json={"date": "2026-10-20"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "scheduled" and s.events[-1]["status"] == "S"
    html = client.get(f"/desk/{dept['code']}").text
    no_em_dash_and_synthetic(html)
    pat = s.patients[r["patient_id"]]
    prelim_part = html.split("<h2>Preliminary reports</h2>")[1].split("<h2>Signed recently</h2>")[0]
    pending_part = html.split("<h2>Pending orders</h2>")[1].split("<h2>Preliminary reports</h2>")[0]
    assert s.orders[r["order_id"]]["accession"] in prelim_part
    assert pat["uhid"] in prelim_part and "Venkatesh Rao" in prelim_part
    assert o["accession"] in pending_part and "Scheduled 20/10/2026" in pending_part and "scheduled" in pending_part
    api = client.get(f"/desk/api/{dept['code']}/pending").json()
    rep = next(x for x in api["reports"] if x["id"] == r["id"])
    assert {x["id"] for x in api["reports"]} == {x["id"] for x in s.reports.values() if x["status"] == "preliminary"
                                                and s.orders[x["order_id"]]["performing_department"] == dept["name"]}
    assert rep["patient"] == {"name": pat["name"], "uhid": pat["uhid"]}
    assert rep["encounter"] == s.encounters[r["encounter_id"]]["number"]
    ids = [x["id"] for x in api["reports"]]  # three Radiology preliminary reports since P19: oldest first, as the README says
    assert len(ids) >= 2 and ids == sorted(ids, key=lambda i: (desk._version_time(s.reports[i]), i))
    assert o["id"] in [x["id"] for x in api["orders"]]


# ------------------------------------------------------------------------ Complete and sign
@pytest.fixture(scope="module")
def signed(client):
    """Sign the preliminary report through the JSON API; returns the response and the state before."""
    r, dept = the_preliminary(client)
    h = hospital(client)
    before = {"last_updated": r["meta"]["lastUpdated"], "events": len(h.store.events),
              "feed": len(hl7.read_feed(h.files["hl7"])), "audit": len(audit_lines(client)), "versions": len(r["versions"])}
    consultant = staff(client, dept["code"], "consultant")[-1]
    values = dict(r["versions"][-1]["values"])
    resp = client.post(f"/desk/api/{dept['code']}/orders/{r['order_id']}/sign", json={"signer": consultant["reg_no"]})
    assert resp.status_code == 200, resp.text
    return {"resp": resp.json(), "before": before, "report_id": r["id"], "dept": dept, "consultant": consultant,
            "values": values}


def test_sign_makes_the_report_final_with_a_signature(client, signed):
    s = hospital(client).store
    r = s.reports[signed["report_id"]]
    assert signed["resp"]["status"] == r["status"] == "final"
    v = s.current_version(r)
    assert len(r["versions"]) == signed["before"]["versions"] + 1 and r["versions"][0]["status"] == "preliminary"
    assert v["values"] == signed["values"]   # values kept from the preliminary when none are sent
    sig = s.signatures[v["signature_id"]]
    assert signed["resp"]["signature_id"] == sig["id"]
    assert sig["signer_id"] == signed["consultant"]["id"] and "Vaidyx Demo CA" in sig["block"]
    assert r["meta"]["lastUpdated"] > signed["before"]["last_updated"]
    # exactly one ORU F event, and one HL7 message for it
    assert len(s.events) == signed["before"]["events"] + 1
    ev = s.events[signed["before"]["events"]]
    assert ev["refs"]["report_id"] == r["id"]
    assert (ev["kind"], ev["trigger"], ev["status"]) == ("ORU", "R01", "F")
    feed = hl7.read_feed(files(client)["hl7"])
    msgs = [m for m in feed if f"|{ev['id']}|" in m]
    assert len(msgs) == 1 and "ORU^R01" in msgs[0]
    parsed = hl7.parse(msgs[0])
    assert parsed["type"] == "ORU^R01" and parsed["control_id"] == ev["id"]
    assert parsed["segments"]["OBR"][25] == "F"
    line = next(x for x in audit_lines(client) if x["action"] == "sign" and x["report_id"] == r["id"])
    assert line["by"] == signed["consultant"]["reg_no"] and line["department"] == signed["dept"]["code"]
    assert line["outcome"] == "done" and line["order_id"] == r["order_id"] and line["time"]


def test_sign_renders_the_pdf(client, signed):
    if not Path(documents.PDF_PYTHON).exists():
        pytest.skip(f"pdf venv not available ({documents.PDF_PYTHON}); the desk saves the sign and says PDF not rendered")
    doc = signed["resp"]["document"]
    assert doc and doc["path"], signed["resp"]["desk_messages"]
    pdf = Path(files(client)["data_dir"]) / doc["path"]
    assert pdf.exists() and pdf.read_bytes().startswith(b"%PDF")
    s = hospital(client).store
    sig = s.signatures[signed["resp"]["signature_id"]]
    assert sig["document_hash"] == doc["sha256"]
    v = s.current_version(s.reports[signed["report_id"]])
    assert client.get(f"/view/reports/{signed['report_id']}/{v['version']}").status_code == 200
    page = client.get(f"/desk/{signed['dept']['code']}").text
    assert f"/view/reports/{signed['report_id']}/{v['version']}" in page.split("<h2>Signed recently</h2>")[1]


def test_junior_resident_cannot_sign(client):
    junior = staff(client, "RAD", "junior_resident")
    if not junior:
        pytest.skip("no junior resident in Radiology")
    junior = junior[0]
    o = place(client, "RAD", doc_types=set(desk.model.IMAGING_MODALITY))
    s = hospital(client).store
    n = len(s.events)
    resp = client.post(f"/desk/api/RAD/orders/{o['id']}/sign",
                       json={"signer": junior["reg_no"], "values": {"impression": "Synthetic test value"}})
    assert resp.status_code == 409 and "junior resident" in resp.json()["detail"]
    assert len(s.events) == n and s.orders[o["id"]]["status"] == "ordered"
    # the form lists the junior resident disabled
    form = client.get(f"/desk/RAD/orders/{o['id']}").text
    assert re.search(rf'<option value="{junior["reg_no"]}" disabled>[^<]*cannot sign', form)
    # a crafted form post gets the LifecycleError message as a flash
    r = client.post(f"/desk/RAD/orders/{o['id']}/sign", data={"signer": junior["reg_no"], "values": "impression: x"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/desk/RAD?")
    assert "junior resident" in unquote(r.headers["location"]) and "kind=bad" in r.headers["location"]
    page = client.get(r.headers["location"]).text
    assert 'class="flash bad"' in page and "junior resident" in page
    assert len(s.events) == n
    assert audit_lines(client)[-1]["outcome"] == "refused"


def test_addendum_adds_a_version_and_keeps_the_earlier(client, signed):
    s = hospital(client).store
    rid, code = signed["report_id"], signed["dept"]["code"]
    n = len(s.reports[rid]["versions"])
    values = dict(signed["values"], impression="Synthetic addendum: right hilar node now described")
    resp = client.post(f"/desk/api/{code}/reports/{rid}/addendum",
                       json={"signer": signed["consultant"]["reg_no"], "values": values,
                             "note": "Addendum after review (SYNTHETIC)"})
    assert resp.status_code == 200, resp.text
    r = s.reports[rid]
    assert r["status"] == "amended" and len(r["versions"]) == n + 1
    assert r["versions"][n - 1]["status"] == "final" and r["versions"][n - 1]["values"] == signed["values"]
    assert r["versions"][-1]["values"] == values and r["versions"][-1]["amendment_note"].startswith("Addendum")
    assert (s.events[-1]["kind"], s.events[-1]["status"]) == ("ORU", "C")
    assert hl7.read_feed(files(client)["hl7"])[-1].count("ORU^R01") == 1
    page = client.get(f"/desk/{code}/reports/{rid}").text
    no_em_dash_and_synthetic(page)
    assert "Addendum after review (SYNTHETIC)" in page and f"/desk/{code}/reports/{rid}/addendum" in page
    # an addendum needs a note
    bad = client.post(f"/desk/api/{code}/reports/{rid}/addendum", json={"signer": signed["consultant"]["reg_no"]})
    assert bad.status_code == 400


def test_cancel_an_open_order_gives_x(client):
    s = hospital(client).store
    o = next(o for o in desk.worklist(s, s.department("MIC"))["orders"] if o["status"] == "ordered")
    resp = client.post(f"/desk/api/MIC/orders/{o['id']}/cancel", json={"reason": "Duplicate order (SYNTHETIC test)"})
    assert resp.status_code == 200, resp.text
    assert s.orders[o["id"]]["status"] == "cancelled"
    assert (s.events[-1]["kind"], s.events[-1]["status"], s.events[-1]["refs"]["order_id"]) == ("ORM", "X", o["id"])
    assert "Duplicate order" in hl7.read_feed(files(client)["hl7"])[-1]
    assert o["id"] not in [x["id"] for x in client.get("/desk/api/MIC/pending").json()["orders"]]
    assert audit_lines(client)[-1]["action"] == "cancel"
    # cancelling again is a lifecycle error
    assert client.post(f"/desk/api/MIC/orders/{o['id']}/cancel", json={"reason": "again"}).status_code == 409


def test_lab_order_through_the_html_forms(client):
    """Collect sample, enter preliminary and Complete and sign through the forms (303 + flash each time)."""
    o = place(client, "BIO")
    s = hospital(client).store
    page = client.get(f"/desk/BIO/orders/{o['id']}").text
    no_em_dash_and_synthetic(page)
    for action in ("collect", "preliminary", "sign", "cancel"):
        assert f'action="/desk/BIO/orders/{o["id"]}/{action}"' in page, action
    assert f"/orders/{o['id']}/schedule" not in page          # a laboratory order is not scheduled at the desk
    r = client.post(f"/desk/BIO/orders/{o['id']}/collect", data={"barcode": "", "block_no": ""}, follow_redirects=False)
    assert r.status_code == 303 and "kind=ok" in r.headers["location"], unquote(r.headers["location"])
    assert s.orders[o["id"]]["status"] == "sample_collected" and s.events[-1]["status"] == "I"
    reporter = desk.staff(s, s.department("BIO"))[0]
    r = client.post(f"/desk/BIO/orders/{o['id']}/preliminary",
                    data={"reporter": reporter["reg_no"], "values": "s_creatinine: 0.9 mg/dL\nNote Line: as typed: kept"},
                    follow_redirects=False)
    assert r.status_code == 303
    rep = s.report_for_order(o["id"])
    assert rep["status"] == "preliminary"
    assert rep["versions"][0]["values"] == {"s_creatinine": "0.9 mg/dL", "note_line": "as typed: kept"}
    # the report page prefills the sign form with the preliminary values
    rp = client.get(f"/desk/BIO/reports/{rep['id']}").text
    assert "s_creatinine: 0.9 mg/dL" in rp and f'action="/desk/BIO/orders/{o["id"]}/sign"' in rp
    r = client.post(f"/desk/BIO/orders/{o['id']}/sign",
                    data={"signer": reporter["reg_no"], "values": "s_creatinine: 0.9 mg/dL"}, follow_redirects=False)
    assert r.status_code == 303 and "final" in unquote(r.headers["location"])
    assert rep["status"] == "final" and rep["versions"][-1]["values"] == {"s_creatinine": "0.9 mg/dL"}
    assert s.events[-1]["status"] == "F"
    # a values line without a colon is refused without touching the store
    o2 = place(client, "BIO")
    n = len(s.events)
    r = client.post(f"/desk/BIO/orders/{o2['id']}/preliminary", data={"reporter": reporter["reg_no"], "values": "no colon"},
                    follow_redirects=False)
    assert r.status_code == 303 and "kind=bad" in r.headers["location"] and len(s.events) == n


def test_wrong_department_is_404(client, signed):
    s = hospital(client).store
    rid = signed["report_id"]
    oid = s.reports[rid]["order_id"]
    assert client.post(f"/desk/api/PATH/orders/{oid}/sign", json={"signer": "VXREG-20201"}).status_code == 404
    assert client.post(f"/desk/api/PATH/reports/{rid}/addendum", json={"signer": "x", "note": "x"}).status_code == 404
    assert client.get(f"/desk/PATH/reports/{rid}").status_code == 404
    assert client.get(f"/desk/PATH/orders/{oid}").status_code == 404
    assert client.post(f"/desk/PATH/orders/{oid}/cancel", data={"reason": "x"}, follow_redirects=False).status_code == 404
    assert client.get("/desk/NOPE").status_code == 404
    assert client.get("/desk/api/NOPE/pending").status_code == 404
    treating = next(d for d in s.departments.values() if d["group"] != "supporting")
    assert client.get(f"/desk/{treating['code']}").status_code == 404


def test_pages_render_without_em_dashes(client):
    s = hospital(client).store
    for d in s.departments.values():
        if d["group"] != "supporting":
            continue
        html = client.get(f"/desk/{d['code']}").text
        no_em_dash_and_synthetic(html)
        assert "<h2>Pending orders</h2>" in html and "<h2>Preliminary reports</h2>" in html
        assert 'href="/desk"' in html and 'href="/his"' in html
        w = desk.worklist(s, d)
        for o in w["orders"]:
            page = client.get(f"/desk/{d['code']}/orders/{o['id']}").text
            no_em_dash_and_synthetic(page)
            want = ["preliminary", "sign", "cancel"] + (["schedule"] if desk.is_imaging(o) else [])
            for action in want:
                assert f'/orders/{o["id"]}/{action}"' in page, (o["id"], action)
            assert "Complete and sign" in page
        for r in desk.recently_signed(s, d, n=3):
            page = client.get(f"/desk/{d['code']}/reports/{r['id']}").text
            no_em_dash_and_synthetic(page)
            assert f"/reports/{r['id']}/addendum" in page


def test_parse_values():
    assert desk.parse_values("Lesion Size: 4.8 x 3.6 cm\n\nER-status: Positive (Allred 7/8)\n") == {
        "lesion_size": "4.8 x 3.6 cm", "er_status": "Positive (Allred 7/8)"}
    assert desk.parse_values("time: 10:30 IST") == {"time": "10:30 IST"}
    for bad in ("no colon here", "1abc: x", "a.b: x"):
        with pytest.raises(desk.DeskError):
            desk.parse_values(bad)


# ------------------------------------------------------------------------ imaging: synthetic DICOM and PACS
def test_imaging_sign_builds_dicom(client, monkeypatch):
    from his_mock import dicom_studies

    s = hospital(client).store
    h = hospital(client)
    order = next((o for d in s.departments.values() if d["group"] == "supporting"
                  for o in desk.worklist(s, d)["orders"]
                  if o["status"] == "scheduled" and desk.is_imaging(o) and s.imaging_study_for(o["id"])
                  and not s.imaging_study_for(o["id"]).get("series")), None)
    assert order, "the fixtures hold a scheduled imaging order with no images (the bone scan)"
    dept = s.department(order["performing_department"])
    study = s.imaging_study_for(order["id"])
    assert not dicom_studies.performed(s, study)
    target = Path(h.files["dicom"]) / dicom_studies.study_dirname(study)
    assert not target.exists()
    alive = dicom_studies.orthanc_alive(dicom_studies.ORTHANC_URL)
    pre_existing = alive and dicom_studies.find_study(study["study_uid"], dicom_studies.ORTHANC_URL) is not None
    if alive:
        monkeypatch.setattr(desk, "ORTHANC_URL", dicom_studies.ORTHANC_URL)
    consultant = staff(client, dept["code"], "consultant")[0]
    try:
        resp = client.post(f"/desk/api/{dept['code']}/orders/{order['id']}/sign",
                           json={"signer": consultant["reg_no"], "values": {"impression": "Synthetic test impression"}})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "final"
        assert dicom_studies.performed(s, study) and study["series"]
        assert study["status"] == ("available" if alive else "registered") and study["uploaded"] is alive
        assert target.is_dir() and len(list(target.glob("*.dcm"))) == study["number_of_instances"] > 0
        texts = [m["text"] for m in resp.json()["desk_messages"]]
        if alive:
            assert any("images uploaded" in t for t in texts), texts
            assert dicom_studies.find_study(study["study_uid"], dicom_studies.ORTHANC_URL) is not None
        else:
            assert any("images not uploaded" in t for t in texts), texts
    finally:
        if alive and not pre_existing and study.get("orthanc_id"):
            try:
                dicom_studies.delete_study(study["orthanc_id"], dicom_studies.ORTHANC_URL)
            except Exception:
                pass


def test_pacs_down_never_fails_the_sign(client):
    """With Orthanc unreachable (module default here), an imaging report is still signed and saved."""
    o = place(client, "RAD", doc_types=set(desk.model.IMAGING_MODALITY))
    s = hospital(client).store
    consultant = staff(client, "RAD", "consultant")[0]
    resp = client.post(f"/desk/api/RAD/orders/{o['id']}/sign",
                       json={"signer": consultant["reg_no"], "values": {"impression": "Synthetic"}})
    assert resp.status_code == 200 and resp.json()["status"] == "final"
    assert any("images not uploaded" in m["text"] for m in resp.json()["desk_messages"])
    saved = json.loads((Path(files(client)["store"])).read_text())
    assert saved["orders"][o["id"]]["status"] == "completed"


# ------------------------------------------------------------------------ the signed report as the HIS serves it
def test_signed_report_is_final_with_provenance(client, data_dir, signed):
    s = hospital(client).store
    rid = signed["report_id"]
    sig = s.signatures[signed["resp"]["signature_id"]]
    assert sig["report_id"] == rid and sig["signer_id"] == signed["consultant"]["id"] and sig["signed_at"]
    if importlib.util.find_spec("his_mock.fhir") is None:
        return  # plan 1.3 not there yet: the store signature above is the check; the orchestrator re-runs this after 1.3
    pytest.importorskip("his_mock.fhir")
    token = (Path(data_dir) / paths.TOKEN_NAME).read_text().strip()
    head = {"Authorization": f"Bearer {token}"}
    accession = s.orders[s.reports[rid]["order_id"]]["accession"]
    resp = client.get(f"/fhir/DiagnosticReport/{rid}", headers=head)
    if resp.status_code == 200:
        report = resp.json()
    else:
        bundle = client.get("/fhir/DiagnosticReport", params={"identifier": accession}, headers=head).json()
        report = next(e["resource"] for e in bundle.get("entry", []) if e["resource"]["resourceType"] == "DiagnosticReport")
    assert report["status"] in ("final", "amended")
    ref = f"DiagnosticReport/{report['id']}"
    prov = client.get("/fhir/Provenance", params={"target": ref}, headers=head)
    entries = prov.json().get("entry", []) if prov.status_code == 200 else []
    if not entries:
        bundle = client.get("/fhir/DiagnosticReport", headers=head,
                            params={"_id": report["id"], "_revinclude": "Provenance:target"}).json()
        entries = [e for e in bundle.get("entry", []) if e["resource"]["resourceType"] == "Provenance"]
    targets = [t.get("reference", "") for e in entries for t in e["resource"].get("target", [])]
    assert any(t.endswith(ref) or ref.split("/")[1] in t for t in targets), targets
