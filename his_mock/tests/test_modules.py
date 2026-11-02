"""The working modules of the demo HIMS through the logins, the way a demo is run: OPD (today's list, new OP visit, order
entry grouped by performing department, the OPD note as a signed opd_note record with its PDF and FHIR
DocumentReference), IPD (admission with the PM-JAY Pre-Authorization line, census, discharge summary, discharge),
Laboratory (work list tabs, sample collection with a barcode, result entry per template with Indian units and reference
intervals, verification and signature by the laboratory consultant only, amendment, cancel), Radiology (schedule with the
ImagingStudy and Study UID, preliminary report, sign by the radiologist only, Open images, addendum), Pathology
(specimen receipt with block No., HPE, add-on IHC panels by template and as free lines, sign, addendum), Exchange (HL7
viewer, raw message, token presence) and Admin (practitioners, accounts, audit). SYNTHETIC data only (a temporary build;
the PACS is pointed at a dead address so nothing reaches the live Orthanc)."""
import re
from pathlib import Path

import pytest

from his_mock import app as app_module
from his_mock import auth, desk, documents, generator, hl7, paths
from his_mock.tests import helpers
from his_mock.tests.helpers import clean, location, post

DEAD_ORTHANC = "http://127.0.0.1:9"
P01 = "vxh-26-004201"          # Anitha Reddy (SYNTHETIC), 46 F, PM-JAY ID, Breast Surgery
PDF = Path(documents.PDF_PYTHON).exists()


@pytest.fixture(scope="module", autouse=True)
def no_pacs():
    old = desk.ORTHANC_URL
    desk.ORTHANC_URL = DEAD_ORTHANC
    yield
    desk.ORTHANC_URL = old


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_modules")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def app(data_dir):
    return app_module.create_app(data_dir)


@pytest.fixture(scope="module")
def users(app):
    cache = {}

    def get(role):
        if role not in cache:
            cache[role] = helpers.login(app, role)
        return cache[role]
    return get


@pytest.fixture
def store(app):
    return app.state.hospital.store


def token(data_dir):
    return (Path(data_dir) / paths.TOKEN_NAME).read_text().strip()


def feed(data_dir):
    return hl7.read_feed(paths.layout(data_dir)["hl7"])


def his_audit(data_dir):
    import json
    p = Path(data_dir) / auth.AUDIT_NAME
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def consultant(store, dept):
    return sorted((p for p in store.practitioners.values() if p["department"] == dept and p["role"] == "consultant"),
                  key=lambda p: p["reg_no"])[0]


# -------------------------------------------------------------------- OPD: visit, order entry, OPD note
@pytest.fixture(scope="module")
def visit(app, users):
    """Reception opens a new Breast Surgery OP visit for P01 with the OPD consultant."""
    s = app.state.hospital.store
    doc = consultant(s, "Breast Surgery")
    r = post(users("reception"), f"/his/patients/{P01}/visits",
             {"department": "Breast Surgery", "unit": "Unit II", "consultant_id": doc["id"], "visit_type": "follow_up"})
    path, q = location(r)
    eid = path.rsplit("/", 1)[-1]
    assert path == f"/his/encounters/{eid}" and "OP visit OP/26/" in q["flash"]
    return s.encounters[eid]


def test_opd_list_shows_todays_visit_by_department_and_unit(users, visit):
    c = users("opd.doctor")
    html = c.get("/his/opd").text
    clean(html)
    today = html.split("id=today>", 1)[1].split("</div>", 1)[0]
    assert visit["number"] in today and "Anitha Reddy (SYNTHETIC)" in today and "Breast Surgery, Unit II" in today
    assert 'href="/his/opd" class=active' in html
    other = c.get("/his/opd", params={"department": "Medical Oncology"}).text.split("id=today>", 1)[1].split("</div>", 1)[0]
    assert visit["number"] not in other and "No OP visit on this day." in other
    unit = c.get("/his/opd", params={"department": "Breast Surgery", "unit": "Unit I"}).text
    assert visit["number"] not in unit.split("id=today>", 1)[1].split("</div>", 1)[0]


def test_order_entry_form_groups_tests_by_performing_department(users, visit):
    html = users("opd.doctor").get(f"/his/encounters/{visit['id']}").text
    clean(html)
    entry = html.split("id=order-entry>", 1)[1].split("</form>", 1)[0]
    for dept in ("Radiology", "Pathology", "Biochemistry", "Microbiology", "Nuclear Medicine", "Anaesthesiology"):
        assert f"<h3>{dept}</h3>" in entry, dept
    for key in ("mammogram", "hpe_biopsy", "ihc_breast", "cbc", "lft", "pre_anaesthetic_check", "bronchoscopy"):
        assert f'value="{key}"' in entry, key
    for key in ("opd_note", "referral_note", "discharge_summary"):   # written on the visit page, never ordered
        assert f'value="{key}"' not in entry, key
    # supporting departments come before the treating ones
    assert entry.index("<h3>Radiology</h3>") < entry.index("<h3>Pulmonology</h3>")
    # the banner of the patient page: name, UHID, age / sex, OP No., consultant
    banner = html.split("class=banner>", 1)[1].split("</div>", 1)[0]
    for part in ("Anitha Reddy (SYNTHETIC)", "VXH/26/004201", "46 Y / F", visit["number"], "Dr Kavitha Raghunathan"):
        assert part in banner, part


@pytest.fixture(scope="module")
def placed(app, users, visit, data_dir):
    """The OPD consultant orders a mammogram, a core biopsy HPE, a CBC and an LFT in one go."""
    s = app.state.hospital.store
    n_orders, n_events, n_feed = len(s.orders), len(s.events), len(feed(data_dir))
    r = post(users("opd.doctor"), f"/his/encounters/{visit['id']}/orders",
             {"tests": ["mammogram", "hpe_biopsy", "cbc", "lft"]})
    path, q = location(r)
    assert path == f"/his/encounters/{visit['id']}" and q["flash"].startswith("Ordered: ") and "level" not in q
    new = [o for o in s.orders.values() if o["encounter_id"] == visit["id"]]
    assert len(s.orders) == n_orders + 4 and len(new) == 4
    assert len(s.events) == n_events + 4 and all(e["kind"] == "ORM" for e in s.events[n_events:])
    assert len(feed(data_dir)) == n_feed + 4
    by = {o["test"]: o for o in new}
    return {"visit": visit, **by, "events": n_events}


def test_order_entry_places_one_order_per_test_with_accessions(app, users, placed, data_dir):
    s = app.state.hospital.store
    assert re.match(r"^RAD/26/\d{5}$", placed["mammogram"]["accession"])
    assert re.match(r"^PATH/26/\d{5}$", placed["hpe_biopsy"]["accession"])
    assert placed["cbc"]["performing_department"] == "Pathology" and placed["lft"]["performing_department"] == "Biochemistry"
    for o in (placed[k] for k in ("mammogram", "hpe_biopsy", "cbc", "lft")):
        assert o["status"] == "ordered" and o["ordering_department"] == "Breast Surgery"
        assert o["encounter_id"] == placed["visit"]["id"] and o["patient_id"] == P01
    html = users("opd.doctor").get(f"/his/encounters/{placed['visit']['id']}").text
    orders = html.split("id=orders>", 1)[1].split("</table>", 1)[0]
    for k, mod in (("mammogram", "radiology"), ("hpe_biopsy", "pathology"), ("cbc", "lab"), ("lft", "lab")):
        assert f'href="/his/{mod}/orders/{placed[k]["id"]}"' in orders, k
    line = [x for x in his_audit(data_dir) if x["action"] == "order"][-1]
    assert line["outcome"] == "done" and line["user"].startswith("opd.doctor@")
    assert "ORM^O01" in feed(data_dir)[-1]


def test_order_entry_refusals_are_red_flashes(app, users, visit):
    s = app.state.hospital.store
    c = users("opd.doctor")
    n = len(s.events)
    for tests, words in (([], "Tick at least one test"), (["no_such_test"], "Unknown test"),
                         (["opd_note"], "written on the visit page")):
        path, q = location(post(c, f"/his/encounters/{visit['id']}/orders", {"tests": tests}))
        assert q.get("level") == "bad" and words in q["flash"], (tests, q)
    assert len(s.events) == n
    # the JSON order entry (tests and the demo script)
    r = c.post(f"/his/api/encounters/{visit['id']}/orders", json={"tests": "cbc"})
    assert r.status_code == 422


def test_opd_note_validation_sits_next_to_the_field(users, visit, store):
    n = len(store.events)
    r = post(users("opd.doctor"), f"/his/encounters/{visit['id']}/notes", {"v_examination": "Lump felt (SYNTHETIC)"})
    assert r.status_code == 422
    clean(r.text)
    assert 'class="row has-error"><label for="f-v_presenting_complaint">' in r.text
    assert "Presenting complaint is required." in r.text and "Lump felt (SYNTHETIC)" in r.text   # what was typed stays
    assert len(store.events) == n


def test_opd_note_is_a_signed_record_with_pdf_and_fhir(app, users, visit, store, data_dir):
    c = users("opd.doctor")
    r = post(c, f"/his/encounters/{visit['id']}/notes", {
        "v_presenting_complaint": "Follow-up after core biopsy of the right breast lump (SYNTHETIC)",
        "v_examination": "Right breast lump 3 cm, upper outer quadrant (SYNTHETIC)",
        "v_clinical_question": "Breast conserving surgery possible? (SYNTHETIC)",
        "v_plan": "Mammogram, core biopsy, CBC and LFT ordered (SYNTHETIC)"})
    path, q = location(r)
    assert path == f"/his/encounters/{visit['id']}" and "OPD note" in q["flash"] and "signed" in q["flash"]
    rep = next(x for x in store.reports.values() if x["encounter_id"] == visit["id"] and x["test"] == "opd_note")
    v = store.current_version(rep)
    assert rep["status"] == "final" and v["values"]["presenting_complaint"].startswith("Follow-up after core biopsy")
    sig = store.signatures[v["signature_id"]]
    doc = consultant(store, "Breast Surgery")
    assert sig["signer_id"] == doc["id"] and doc["reg_no"] in sig["block"] and "Vaidyx Demo CA" in sig["block"]
    assert any(e["kind"] == "ORU" and e["refs"].get("report_id") == rep["id"] for e in store.events)
    if PDF:
        assert (v.get("document") or {}).get("path"), q["flash"]
        pdf = c.get(f"/view/reports/{rep['id']}/{v['version']}")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    head = {"Authorization": f"Bearer {token(data_dir)}"}
    bundle = c.get("/fhir/DocumentReference", params={"patient": P01}, headers=head).json()
    ids_ = [e["resource"]["id"] for e in bundle.get("entry", [])]
    assert f"doc-{rep['id']}-v{v['version']}" in ids_
    # another department's visit: the note form says who writes it, a crafted post is refused
    other = next(e for e in store.encounters.values() if e["kind"] == "OP" and e["department"] != "Breast Surgery")
    html = c.get(f"/his/encounters/{other['id']}").text
    assert f"Only a consultant of {other['department']} writes and signs this" in html
    r = post(c, f"/his/encounters/{other['id']}/notes", {"v_presenting_complaint": "x"})
    assert r.status_code == 403 and "Your role cannot do this" in r.text


# -------------------------------------------------------------------- Laboratory
def test_lab_work_list_tabs(users, placed):
    c = users("lab.tech")
    html = c.get("/his/lab").text
    clean(html)
    for label in ("Ordered", "Sample collected", "Results entered", "Verified"):
        assert re.search(rf">{label} \(\d+\)</a>", html), label
    assert placed["cbc"]["accession"] in html.split("id=worklist>", 1)[1]
    biochem = c.get("/his/lab", params={"dept": "BIO"}).text.split("id=worklist>", 1)[1]
    assert placed["lft"]["accession"] in biochem and placed["cbc"]["accession"] not in biochem


def test_lab_collect_result_verify_amend(app, users, placed, store, data_dir):
    o = placed["cbc"]
    base = f"/his/lab/orders/{o['id']}"
    tech, labdoc = users("lab.tech"), users("lab.doctor")
    page = tech.get(base).text
    clean(page)
    assert f'action="{base}/collect"' in page and f'action="{base}/result"' in page
    assert "only the Laboratory consultant can verify and sign a laboratory report" in page   # the technician sees why
    # collect: the LIS allocates the barcode; the label prints
    path, q = location(post(tech, f"{base}/collect"))
    spec = store.specimens[store.orders[o["id"]]["specimen_id"]]
    assert re.match(r"^VXS\d{8}$", spec["barcode"]) and spec["barcode"] in q["flash"]
    assert spec["barcode"] in tech.get(f"{base}/label").text
    assert o["accession"] in tech.get("/his/lab", params={"tab": "collected"}).text.split("id=worklist>", 1)[1]
    # result entry per template: units and the sex-specific reference interval are on the form
    page = tech.get(base).text
    form = page.split("id=result>", 1)[1].split("</form>", 1)[0]
    for part in ('name="v_haemoglobin"', "gm%", "Reference interval: 12.0-15.0", 'name="v_wbc"', "/cumm",
                 'name="v_platelets"', "lakhs/cumm", "Reference interval: 1.5-4.5"):
        assert part in form, part
    n = len(store.events)
    r = post(tech, f"{base}/result", {"v_haemoglobin": "eleven", "v_wbc": "7,800"})
    assert r.status_code == 422 and "Enter a number" in r.text and 'value="eleven"' in r.text and len(store.events) == n
    path, q = location(post(tech, f"{base}/result", {"v_haemoglobin": "11.2", "v_wbc": "7,800", "v_platelets": "2.6"}))
    rep = store.report_for_order(o["id"])
    assert rep["status"] == "preliminary"
    assert rep["versions"][0]["values"] == {"haemoglobin": "11.2 gm%", "wbc": "7,800 /cumm", "platelets": "2.6 lakhs/cumm"}
    assert o["accession"] in tech.get("/his/lab", params={"tab": "entered"}).text.split("id=worklist>", 1)[1]
    # only the laboratory consultant verifies
    r = post(tech, f"{base}/verify", {"v_haemoglobin": "11.2"})
    assert r.status_code == 403 and "Your role cannot do this" in r.text
    page = labdoc.get(base).text
    verify = page.split("id=verify>", 1)[1].split("</form>", 1)[0]
    assert 'value="11.2"' in verify and "Dr Anil Saxena" in verify          # prefilled with the entered results
    path, q = location(post(labdoc, f"{base}/verify", {"v_haemoglobin": "11.2", "v_wbc": "7,800", "v_platelets": "2.6"}))
    assert "verified and signed" in q["flash"]
    v = store.current_version(rep)
    assert rep["status"] == "final" and v["version"] == 2 and v["values"]["platelets"] == "2.6 lakhs/cumm"
    sig = store.signatures[v["signature_id"]]
    assert sig["signer_id"] == consultant(store, "Biochemistry")["id"]
    verified = labdoc.get("/his/lab", params={"tab": "verified"}).text.split("id=worklist>", 1)[1]
    assert o["accession"] in verified
    if PDF:
        assert f"/view/reports/{rep['id']}/2" in verified
    # amendment: a note is required, then a new signed version
    amend = f"/his/lab/reports/{rep['id']}/amend"
    r = post(labdoc, amend, {"v_haemoglobin": "11.4", "v_wbc": "7,800", "v_platelets": "2.6"})
    assert r.status_code == 422 and "An amendment needs a note" in r.text
    path, q = location(post(labdoc, amend, {"v_haemoglobin": "11.4", "v_wbc": "7,800", "v_platelets": "2.6",
                                            "note": "Haemoglobin re-run on the same sample (SYNTHETIC)"}))
    assert rep["status"] == "amended" and store.current_version(rep)["values"]["haemoglobin"] == "11.4 gm%"
    assert (store.events[-1]["kind"], store.events[-1]["status"]) == ("ORU", "C")


def test_lab_cancel_needs_a_reason(users, placed, store):
    o = placed["lft"]
    base = f"/his/lab/orders/{o['id']}"
    tech = users("lab.tech")
    path, q = location(post(tech, f"{base}/cancel", {"reason": ""}))
    assert q.get("level") == "bad" and "reason" in q["flash"] and store.orders[o["id"]]["status"] == "ordered"
    path, q = location(post(tech, f"{base}/cancel", {"reason": "Ordered twice (SYNTHETIC)"}))
    assert store.orders[o["id"]]["status"] == "cancelled" and "cancelled" in q["flash"]
    assert "no action is open" in tech.get(base).text


def test_choice_results_of_viral_markers(app, users, visit, store):
    with app.state.hospital.lock:
        o = store.place_order(P01, visit["id"], "viral_markers", "Breast Surgery")
        app.state.hospital.save()
    base = f"/his/lab/orders/{o['id']}"
    labdoc = users("lab.doctor")
    form = labdoc.get(base).text.split("id=verify>", 1)[1].split("</form>", 1)[0]
    assert '<option value="Non-reactive">' in form and '<option value="Reactive">' in form
    r = post(labdoc, f"{base}/verify", {"v_hiv_status": "Maybe"})
    assert r.status_code == 422 and "Choose one of" in r.text
    location(post(labdoc, f"{base}/verify", {"v_hiv_status": "Non-reactive", "v_hbsag": "Non-reactive",
                                             "v_anti_hcv": "Non-reactive"}))
    assert store.report_for_order(o["id"])["status"] == "final"


# -------------------------------------------------------------------- Radiology
def test_radiology_schedule_report_sign_addendum(users, placed, store):
    o = placed["mammogram"]
    base = f"/his/radiology/orders/{o['id']}"
    tech, rad = users("rad.tech"), users("radiologist")
    html = tech.get("/his/radiology").text
    clean(html)
    for label in ("Ordered", "Scheduled", "Reported (preliminary)", "Signed"):
        assert re.search(rf">{re.escape(label)} \(\d+\)</a>", html), label
    assert o["accession"] in html.split("id=worklist>", 1)[1]
    # schedule: a bad date is shown next to the field; a good one registers the ImagingStudy with its Study UID
    r = post(tech, f"{base}/schedule", {"date": "20/10/2026", "time": "10:30"})
    assert r.status_code == 422 and "The date or time is not valid" in r.text
    path, q = location(post(tech, f"{base}/schedule", {"date": "2099-10-20", "time": "10:30", "room": "Mammography unit"}))
    study = store.imaging_study_for(o["id"])
    assert study and study["study_uid"].startswith("2.25.") and study["accession"] == o["accession"]
    assert "Study UID" in q["flash"] and store.orders[o["id"]]["room"] == "Mammography unit"
    scheduled = tech.get("/his/radiology", params={"tab": "scheduled"}).text.split("id=worklist>", 1)[1]
    assert o["accession"] in scheduled and "20/10/2099 10:30" in scheduled
    page = tech.get(base).text
    assert study["study_uid"] in page and "Open images" not in page          # booked, not acquired yet
    # a study booked for a later day has no report yet; rescheduling to today keeps the Study UID
    path, q = location(post(tech, f"{base}/report", {"v_findings": "x", "v_impression": "y"}))
    assert q.get("level") == "bad" and "Reschedule it to today" in q["flash"] and not store.report_for_order(o["id"])
    location(post(tech, f"{base}/schedule", {"date": store.now()[:10], "time": "08:00", "room": "Mammography unit"}))
    assert store.imaging_study_for(o["id"])["study_uid"] == study["study_uid"]
    assert study["started"].startswith(store.now()[:10] + "T08:00")      # the study moved with the booking
    # preliminary by the technician (technique / findings / impression); the radiologist signs
    fields = {"v_technique": "Digital mammography, CC and MLO views of both breasts (SYNTHETIC)",
              "v_findings": "Irregular spiculated mass 2.8 cm in the right upper outer quadrant (SYNTHETIC)",
              "v_impression": "BI-RADS 5 as reported (SYNTHETIC)"}
    r = post(tech, f"{base}/report", {"v_findings": "x"})
    assert r.status_code == 422 and "Impression is required." in r.text
    path, q = location(post(tech, f"{base}/report", fields))
    rep = store.report_for_order(o["id"])
    assert rep["status"] == "preliminary" and "Preliminary report saved" in q["flash"]
    assert "images built" in q["flash"] or "images not uploaded" in q["flash"] or "images" in q["flash"]
    page = tech.get(base).text
    assert f"/api/tb/pacs/ohif/viewer?StudyInstanceUIDs={study['study_uid']}" in page    # Open images
    assert o["accession"] in tech.get("/his/radiology", params={"tab": "reported"}).text.split("id=worklist>", 1)[1]
    r = post(tech, f"{base}/sign", fields)
    assert r.status_code == 403 and "only the Radiologist can sign a radiology report" in r.text
    path, q = location(post(rad, f"{base}/sign", fields))
    v = store.current_version(rep)
    assert rep["status"] == "final" and v["values"]["technique"].startswith("Digital mammography")
    assert store.signatures[v["signature_id"]]["signer_id"] == consultant(store, "Radiology")["id"]
    assert o["accession"] in rad.get("/his/radiology", params={"tab": "signed"}).text.split("id=worklist>", 1)[1]
    # addendum
    add = f"/his/radiology/reports/{rep['id']}/addendum"
    assert f'action="{add}"' in rad.get(base).text
    path, q = location(post(rad, add, {**fields, "v_impression": "BI-RADS 5; axilla clear as reported (SYNTHETIC)",
                                      "note": "Axilla described (SYNTHETIC)"}))
    assert rep["status"] == "amended" and store.current_version(rep)["amendment_note"] == "Axilla described (SYNTHETIC)"


# -------------------------------------------------------------------- Pathology
def test_pathology_receipt_hpe_addon_ihc(app, users, placed, store):
    o = placed["hpe_biopsy"]
    base = f"/his/pathology/orders/{o['id']}"
    path_c, tech = users("pathologist"), users("lab.tech")
    html = path_c.get("/his/pathology").text
    clean(html)
    assert o["accession"] in html.split("id=worklist>", 1)[1]
    suggested = o["accession"] + "-A1"
    assert f'value="{suggested}"' in path_c.get(base).text
    r = post(tech, f"{base}/receive", {"block_no": "00464-A1"})
    assert r.status_code == 422 and "for example PATH/26/00412-A1" in r.text and not store.orders[o["id"]].get("specimen_id")
    # specimen receipt (a laboratory technician may receive) with the block No.
    path, q = location(post(tech, f"{base}/receive", {"block_no": suggested}))
    spec = store.specimens[store.orders[o["id"]]["specimen_id"]]
    assert spec["block_no"] == suggested and spec["type"] == "tissue" and f"block No. {suggested}" in q["flash"]
    received = path_c.get("/his/pathology", params={"tab": "received"}).text.split("id=worklist>", 1)[1]
    assert o["accession"] in received and suggested in received
    # HPE entry: required fields next to the field, then signed final by the pathologist
    hpe = {"v_specimen": "Core biopsy, right breast, in 10% buffered formalin (SYNTHETIC)",
           "v_gross": "Three linear cores, 1.2 to 1.6 cm (SYNTHETIC)",
           "v_microscopy": "Infiltrating tumour cells in cords and nests (SYNTHETIC)",
           "v_histologic_type": "Invasive breast carcinoma of no special type (SYNTHETIC)",
           "v_grade": "Grade 2 (SYNTHETIC)", "action": "sign"}
    r = post(path_c, f"{base}/report", {k: v for k, v in hpe.items() if k != "v_microscopy"})
    assert r.status_code == 422 and "Microscopy is required." in r.text
    r = post(path_c, f"{base}/report", {**hpe, "v_diagnosis": ""})
    assert r.status_code == 422 and "Diagnosis is required." in r.text
    path, q = location(post(path_c, f"{base}/report", {**hpe, "v_diagnosis": "Invasive carcinoma, see IHC (SYNTHETIC)"}))
    rep = store.report_for_order(o["id"])
    v = store.current_version(rep)
    assert rep["status"] == "final" and v["values"]["histologic_type"].startswith("Invasive breast carcinoma")
    assert store.signatures[v["signature_id"]]["signer_id"] == consultant(store, "Pathology")["id"]
    # the pathologist adds an IHC breast panel on the same encounter, entered per template (ER, PR, HER2, Ki-67)
    n = len(store.orders)
    path, q = location(post(path_c, f"{base}/addon", {"test": "ihc_breast"}))
    assert len(store.orders) == n + 1 and "Add-on order" in q["flash"]
    ihc = store.orders[path.rsplit("/", 1)[-1]]
    assert ihc["test"] == "ihc_breast" and ihc["encounter_id"] == o["encounter_id"] and ihc["ordering_department"] == "Pathology"
    ib = f"/his/pathology/orders/{ihc['id']}"
    assert f'value="{suggested}"' in path_c.get(ib).text      # the add-on is cut from the block already received
    form = path_c.get(ib).text.split("id=report>", 1)[1].split("</form>", 1)[0]
    for name in ("v_er", "v_pr", "v_her2", "v_ki67"):
        assert f'name="{name}"' in form, name
    marks = {"v_er": "Positive (Allred score 7/8)", "v_pr": "Positive (Allred score 6/8)", "v_her2": "1+ (Negative)",
             "v_ki67": "20 %"}
    r = post(path_c, f"{ib}/report", {**{k: v for k, v in marks.items() if k != "v_her2"}, "action": "sign"})
    assert r.status_code == 422 and "HER2/neu (IHC score) is required." in r.text
    location(post(path_c, f"{ib}/report", {**marks, "action": "preliminary"}))
    assert store.report_for_order(ihc["id"])["status"] == "preliminary"
    assert ihc["accession"] in path_c.get("/his/pathology", params={"tab": "entered"}).text.split("id=worklist>", 1)[1]
    location(post(path_c, f"{ib}/sign", {**marks, "action": "sign"}))
    ir = store.report_for_order(ihc["id"])
    assert ir["status"] == "final" and store.current_version(ir)["values"]["ki67"] == "20 %"
    # a free IHC panel (marker: result lines)
    path, q = location(post(path_c, f"{base}/addon", {"test": "ihc_panel"}))
    panel = path.rsplit("/", 1)[-1]
    r = post(path_c, f"/his/pathology/orders/{panel}/report", {"values": "no colon here", "action": "sign"})
    assert r.status_code == 422
    location(post(path_c, f"/his/pathology/orders/{panel}/report", {"values": "CK7: Positive\nCK20: Negative", "action": "sign"}))
    assert store.current_version(store.report_for_order(panel))["values"] == {"ck7": "Positive", "ck20": "Negative"}
    # a technician cannot add on; addendum on the HPE by the pathologist
    r = post(tech, f"{base}/addon", {"test": "pdl1_ihc"})
    assert r.status_code == 403
    path, q = location(post(path_c, f"/his/pathology/reports/{rep['id']}/addendum",
                            {**hpe, "v_diagnosis": "Invasive carcinoma NST, grade 2 (SYNTHETIC)", "note": "Grade added (SYNTHETIC)"}))
    assert rep["status"] == "amended"


# -------------------------------------------------------------------- IPD
def test_ipd_admit_census_summary_discharge(app, users, store, data_dir):
    c, ward = users("opd.doctor"), users("ward.doctor")
    doc = consultant(store, "Breast Surgery")
    path, q = location(post(c, f"/his/patients/{P01}/admissions", {
        "department": "Breast Surgery", "unit": "Unit I", "consultant_id": doc["id"], "ward": "Surgical Ward 2",
        "bed": "2-11", "pmjay_preauth": "pending"}))
    e = store.encounters[path.rsplit("/", 1)[-1]]
    assert e["kind"] == "IP" and e["status"] == "in-progress" and e["pmjay_preauth"]["status"] == "pending"
    census = ward.get("/his/ipd").text
    clean(census)
    row = census.split("id=census>", 1)[1].split("</table>", 1)[0]
    assert e["number"] in row and "Surgical Ward 2" in row and "PMJAY-VX-26000101: pending" in row
    page = ward.get(f"/his/encounters/{e['id']}").text
    assert "id=order-entry>" in page and "id=summary>" in page and "Ward / Bed:" in page
    # the discharge summary: required fields, then signed once
    summary = f"/his/encounters/{e['id']}/discharge-summary"
    r = post(ward, summary, {"v_diagnosis": "Carcinoma right breast as reported (SYNTHETIC)"})
    assert r.status_code == 422 and "Course in the hospital is required." in r.text
    path, q = location(post(ward, summary, {"v_diagnosis": "Carcinoma right breast as reported (SYNTHETIC)",
                                            "v_course": "Admitted for surgery; uneventful stay (SYNTHETIC)",
                                            "v_advice": "Review in Breast Surgery OPD with reports (SYNTHETIC)"}))
    assert "Discharge summary" in q["flash"] and "signed" in q["flash"]
    rep = next(r_ for r_ in store.reports.values() if r_["encounter_id"] == e["id"] and r_["test"] == "discharge_summary")
    assert rep["status"] == "final"
    path, q = location(post(ward, summary, {"v_diagnosis": "x", "v_course": "x", "v_advice": "x"}))
    assert q.get("level") == "bad" and "already has a discharge summary" in q["flash"]
    # discharge
    path, q = location(post(ward, f"/his/encounters/{e['id']}/discharge"))
    assert store.encounters[e["id"]]["status"] == "finished" and "discharged" in q["flash"]
    census = ward.get("/his/ipd").text
    assert e["number"] not in census.split("id=census>", 1)[1].split("</table>", 1)[0]
    assert e["number"] in census.split("id=discharges>", 1)[1]
    # another department's admission: the summary form says who writes it
    other = next(x for x in store.encounters.values() if x["kind"] == "IP" and x["status"] == "in-progress")
    assert "writes and signs this" in ward.get(f"/his/encounters/{other['id']}").text


# -------------------------------------------------------------------- Exchange and Admin
def test_exchange_shows_the_hl7_feed_and_never_the_token(users, placed, data_dir):
    c = users("rad.tech")
    html = c.get("/his/exchange").text
    clean(html)
    assert "HL7 v2 messages" in html and "ORM^O01" in html and "API token file: <b>present</b>" in html
    assert token(data_dir) not in html
    oru = c.get("/his/exchange", params={"type": "ORU"}).text.split("id=hl7>", 1)[1].split("</table>", 1)[0]
    assert "ORU^R01" in oru and "ORM^O01" not in oru
    mine = c.get("/his/exchange", params={"patient": "VXH/26/004201"}).text.split("id=hl7>", 1)[1].split("</table>", 1)[0]
    assert "VXH/26/004201" in mine
    control = re.search(r'href="/his/exchange/hl7/([^"]+)"', html).group(1)
    raw = c.get(f"/his/exchange/hl7/{control}")
    assert raw.status_code == 200 and raw.text.startswith("MSH|") and "text/plain" in raw.headers["content-type"]
    assert c.get("/his/exchange/hl7/nope").status_code == 404
    assert 'href="/fhir/metadata"' in html and "id=events>" in html


def test_admin_practitioners_accounts_and_audit(users, store, data_dir):
    c = users("admin")
    html = c.get("/his/admin").text
    clean(html)
    deps = html.split("id=departments>", 1)[1].split("</table>", 1)[0]
    assert deps.count("<tr>") == 1 + len(store.departments) == 32
    accounts = html.split("id=accounts>", 1)[1].split("</table>", 1)[0]
    assert accounts.count("<tr>") == 1 + len(auth.ACCOUNT_SPECS) == 10 and "Dr Kavitha Raghunathan" in accounts
    assert "password_hash" not in html and "$2b$" not in html
    assert "id=audit>" in html and "id=desk-audit>" in html and "login" in html.split("id=audit>", 1)[1]
    r = post(c, "/his/admin/practitioners", {"name": "Dr Test Person (SYNTHETIC)", "qualification": "MD (Pathology)",
                                             "reg_no": "12345", "department": "Pathology", "role": "consultant"})
    assert r.status_code == 422 and "Reg. No. must be VXREG-" in r.text
    path, q = location(post(c, "/his/admin/practitioners", {"name": "Dr Test Person (SYNTHETIC)", "qualification": "MD (Pathology)",
                                                            "reg_no": "", "department": "Pathology", "role": "consultant"}))
    p = next(x for x in store.practitioners.values() if x["name"] == "Dr Test Person (SYNTHETIC)")
    assert p["reg_no"].startswith("VXREG-3") and p["department"] == "Pathology" and "Added Dr Test Person" in q["flash"]
    assert p["name"] in c.get("/his/admin").text
    assert any(x["action"] == "admin.add_practitioner" for x in his_audit(data_dir))


def test_every_module_page_has_the_classic_shell(users):
    c = users("opd.doctor")
    for label, href in (("Registration", "/his"), ("OPD", "/his/opd"), ("IPD", "/his/ipd"), ("Laboratory", "/his/lab"),
                        ("Radiology", "/his/radiology"), ("Pathology", "/his/pathology"), ("Exchange", "/his/exchange")):
        r = c.get(href)
        assert r.status_code == 200, href
        clean(r.text)
        assert f'<a href="{href}" class=active>{label}</a>' in r.text, href
        assert "Vaidyx Demo Hospital<span class=product>DemoHIMS</span>" in r.text
        assert "Signed in: <b>OPD and ward consultant</b> (opd.doctor, ward.doctor)" in r.text
        assert "#00c0b5" not in r.text.lower()          # clearly not Vaidyx: no teal
        assert r.headers["x-frame-options"] == "SAMEORIGIN" and r.headers["cache-control"] == "no-store"
    assert c.get("/his/admin").status_code == 403


def test_exam_done_sends_images_before_the_report(users, visit, store):
    """The technician's Exam done builds the study's images (and tries the PACS) before any report; the worklist then offers
    Write report, and the patient page shows Open images (18 Oct)."""
    doc = users("opd.doctor")
    location(post(doc, f"/his/encounters/{visit['id']}/orders", {"tests": ["chest_xray"]}))
    o = next(x for x in store.orders.values() if x["encounter_id"] == visit["id"] and x["test"] == "chest_xray")
    base = f"/his/radiology/orders/{o['id']}"
    tech = users("rad.tech")
    location(post(tech, f"{base}/schedule", {"date": store.now()[:10], "time": "08:00", "room": "X-ray room 1"}))
    sched = tech.get("/his/radiology", params={"tab": "scheduled"}).text.split("id=worklist>", 1)[1]
    row = next(r for r in sched.split("<tr>") if o["accession"] in r)
    assert "Exam done" in row and "#examdone" in row
    path, q = location(post(tech, f"{base}/exam-done"))
    study = store.imaging_study_for(o["id"])
    assert study.get("acquired_at") and study.get("series"), study
    assert "exam done" in q["flash"] and not store.report_for_order(o["id"])
    sched = tech.get("/his/radiology", params={"tab": "scheduled"}).text.split("id=worklist>", 1)[1]
    row = next(r for r in sched.split("<tr>") if o["accession"] in r)
    assert "Write report" in row
    assert "Open images" in tech.get(f"/his/encounters/{visit['id']}").text
