"""The Registration module and the shared patient / encounter pages (his_mock/screens.py): registration search, the OP / IP
timeline, referral, transfer, discharge, new registration (with the duplicate warning) / visit / admission, the role
checks and the JSON API. SYNTHETIC data only (a temporary build)."""
import re

import pytest
from fastapi.testclient import TestClient

from his_mock import app as app_module
from his_mock import generator, hl7, paths, screens
from his_mock.scenarios import AADHAAR_LIKE
from his_mock.tests import helpers
from his_mock.tests.helpers import EM_DASH, location, post, text_of


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("his_screens")
    generator.build(d, documents=False, hl7=False, dicom=False)
    return d


@pytest.fixture(scope="module")
def app(data_dir):
    return app_module.create_app(data_dir)


@pytest.fixture(scope="module")
def client(app):
    """The registration desk."""
    return helpers.login(app, "reception")


@pytest.fixture(scope="module")
def doctor(app):
    return helpers.login(app, "opd.doctor")


@pytest.fixture
def store(client):
    return client.app.state.hospital.store


def feed(data_dir):
    return hl7.read_feed(paths.layout(data_dir)["hl7"])


def panels(html):
    """encounter id -> the HTML of its timeline panel, in page order."""
    parts = re.split(r'<div class=panel data-encounter="', html)[1:]
    return [(p.split('"', 1)[0], p) for p in parts]


# -------------------------------------------------------------------- search
def test_home_renders_with_banner_recent_and_form(client):
    r = client.get("/his")
    assert r.status_code == 200
    assert "SYNTHETIC DATA" in r.text and "Registration search" in r.text
    for href in ("/his/opd", "/his/ipd", "/his/lab", "/his/radiology", "/his/pathology", "/his/exchange", "/his/admin"):
        assert f'href="{href}"' in r.text
    assert "Recent registrations" in r.text and "New registration" in r.text and 'name="csrf"' in r.text
    assert "Signed in: <b>Registration desk</b>" in r.text and 'href="/his/logout"' in r.text
    recent = r.text.split('id=recent>', 1)[1].split("</table>", 1)[0]
    assert recent.count("<tr>") == 1 + screens.RECENT  # header row + the last 10


def test_without_login_the_screens_redirect_to_the_login_page(app):
    c = TestClient(app)
    for u in ("/his", "/his/patients/vxh-26-004201", "/his/encounters/ip-26-01872", "/his/opd", "/desk"):
        r = c.get(u, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/his/login?next="), u
    assert c.get("/his/api/search", params={"q": "x"}).status_code == 200   # the JSON API stays login-free


@pytest.mark.parametrize("q,pid", [
    ("VXH/26/004201", "vxh-26-004201"),        # permanent UHID
    ("vxh/26/004201", "vxh-26-004201"),        # case-insensitive
    ("VXH/T/26/00412", "vxh-t-26-00412"),      # temporary UHID
    ("OP/26/118701", "vxh-26-004201"),         # OP No.
    ("IP/26/01872", "vxh-26-004203"),          # IP No.
    ("99-2600-0000-0101", "vxh-26-004201"),    # ABHA number
    ("ANITHA.REDDY@SBX", "vxh-26-004201"),     # ABHA address
    ("RAD/26/00986", "vxh-26-004203"),         # accession / Lab No.
])
def test_identifier_search_redirects_to_the_patient(client, q, pid):
    path, _ = location(client.get("/his", params={"q": q}, follow_redirects=False))
    assert path == f"/his/patients/{pid}"


def test_shared_name_lists_two_unrelated_registrations(client):
    r = client.get("/his", params={"q": "Sunita Devi"})
    assert r.status_code == 200
    res = r.text.split("id=results>", 1)[1].split("id=recent>", 1)[0]
    assert "VXH/26/004204" in res and "VXH/26/004210" in res
    assert "similar registration(s)" not in res


def test_temporary_registration_name_search_notes_similar(client):
    res = client.get("/his", params={"q": "parvathi"}).text.split("id=results>", 1)[1].split("id=recent>", 1)[0]
    assert "VXH/T/26/00412" in res and "VXH/26/004209" in res
    assert res.count("1 similar registration(s)") == 2


def test_no_match_says_so(client):
    r = client.get("/his", params={"q": "VXH/99/999999"})
    assert r.status_code == 200 and "No registration matches" in r.text


# -------------------------------------------------------------------- patient page
def test_temporary_uhid_page_shows_permanent_twin(client):
    html = client.get("/his/patients/vxh-t-26-00412").text
    sim = html.split("id=similar>", 1)[1].split("</div>", 1)[0]
    assert "Similar registrations" in sim and screens.SIMILAR_NOTE in sim
    assert 'href="/his/patients/vxh-26-004209"' in sim and "VXH/26/004209" in sim
    assert "temporary" in html.split("id=demographics>", 1)[1].split("</div>", 1)[0]
    twin = client.get("/his/patients/vxh-26-004209").text
    assert 'href="/his/patients/vxh-t-26-00412"' in twin.split("id=similar>", 1)[1]
    assert "id=similar>" not in client.get("/his/patients/vxh-26-004204").text  # Sunita Devi: different age, no note


def test_patient_demographics_and_banner(client):
    html = client.get("/his/patients/vxh-26-004201").text
    demo = text_of(html.split("id=demographics>", 1)[1].split("</div>", 1)[0])
    for s in ("VXH/26/004201", "permanent", "Anitha Reddy (SYNTHETIC)", "46 Y / F", "18/01/1980", "99-2600-0000-0101",
              "anitha.reddy@sbx", "PMJAY-VX-26000101", "+91 55500 00100", "PIN 556225"):
        assert s in demo, s
    banner = text_of(html.split("<div class=banner>", 1)[1].split("</div>", 1)[0])
    for s in ("Name:", "Anitha Reddy (SYNTHETIC)", "UHID:", "VXH/26/004201", "Age / Sex:", "46 Y / F", "Consultant:"):
        assert s in banner, s


def test_timeline_grouped_by_encounter_newest_first(client, store):
    html = client.get("/his/patients/vxh-26-004203").text
    ps = panels(html)
    assert [p[0] for p in ps] == ["ip-26-01872", "op-26-118705"]
    ip, op = ps[0][1], ps[1][1]
    assert "Admission IP/26/01872, Breast Surgery Unit II, Dr Kavitha Raghunathan, admitted 27/08/2026, discharged 03/09/2026" in ip
    assert "Ward / bed at discharge: Surgical Ward 2, 2-09" in ip and "2 ward transfer(s)" in ip
    assert "PM-JAY Pre-Authorization: not requested" in ip
    assert "OP visit OP/26/118705, Breast Surgery Unit II, Dr Kavitha Raghunathan, 18/08/2026, new" in op
    assert 'data-kind="IP"' in html and 'data-kind="OP"' in html
    assert "RAD/26/00986" in op and "RAD/26/00986" not in ip
    assert "PATH/26/00417" in ip and "PATH/26/00417" not in op
    p01 = dict(panels(client.get("/his/patients/vxh-26-004201").text))
    assert "PM-JAY Pre-Authorization: approved (19/09/2026)" in p01["ip-26-01871"]


def test_order_states_and_report_versions(client, store):
    states = {o["status"]: o for o in store.orders.values()}
    sch, smp, can = states["scheduled"], states["sample_collected"], states["cancelled"]
    for o, want in ((sch, f"scheduled for {screens._d(sch['scheduled_for'])}"),
                    (smp, f"sample collected {store.specimens[smp['specimen_id']]['barcode']}"),
                    (can, "cancelled")):
        html = client.get(f"/his/encounters/{o['encounter_id']}").text
        row = next(r for r in html.split("<tr>") if (o["accession"] or o["label"]) in r)
        assert want in row, (want, row)
    amended = next(r for r in store.reports.values() if r["status"] == "amended")
    html = client.get(f"/his/encounters/{amended['encounter_id']}").text
    assert "v1 (final) not rendered" in html and "v2 (amended) not rendered" in html
    v = amended["versions"][1]
    v["document"] = {"path": "documents/x.pdf", "sha256": "0" * 64}
    try:
        html = client.get(f"/his/encounters/{amended['encounter_id']}").text
        assert f'href="/view/reports/{amended["id"]}/2"' in html and ">v2 (amended)</a>" in html
    finally:
        v["document"] = {"path": None, "sha256": None}


def test_order_rows_link_to_their_module_pages(client, store):
    html = client.get("/his/encounters/ip-26-01872").text
    o = next(o for o in store.orders.values() if o["encounter_id"] == "ip-26-01872" and o["doc_type"] == "histopathology")
    assert f'href="/his/pathology/orders/{o["id"]}"' in html


# -------------------------------------------------------------------- encounter page and transitions
def test_admission_page_shows_ward_history_with_two_transfers(doctor):
    html = doctor.get("/his/encounters/ip-26-01872").text
    wards = html.split("id=wards>", 1)[1].split("</div>", 1)[0]
    assert wards.count("<tr>") == 4  # header + admission + two transfers
    assert "High Dependency Unit" in wards and "Observation after a hypotensive episode" in wards
    assert "id=transfer>" not in html and "id=discharge>" not in html  # discharged: no transfer or discharge form
    assert "id=refer>" in html and "id=order-entry>" in html and "id=summary>" in html


def test_referral_then_accept(doctor, store, data_dir):
    n, m = len(store.events), len(feed(data_dir))
    path, q = location(post(doctor, "/his/encounters/ip-26-01877/refer",
                            {"to": "Thoracic Surgery", "reason": "Opinion on the lung lesion (SYNTHETIC test)"}))
    assert path == "/his/encounters/ip-26-01877" and "level" not in q and "requested" in q["flash"]
    ref = store.encounters["ip-26-01877"]["referrals"][-1]
    assert (ref["from"], ref["to"], ref["status"]) == ("Pulmonology", "Thoracic Surgery", "requested")
    assert len(store.events) == n + 1 and (store.events[-1]["kind"], store.events[-1]["trigger"]) == ("REF", "I12")
    msgs = feed(data_dir)
    assert len(msgs) == m + 1 and msgs[-1].split("|", 9)[8] == "REF^I12"
    html = doctor.get("/his/encounters/ip-26-01877").text
    assert "Accepted by Thoracic Surgery" in html
    path, q = location(post(doctor, "/his/encounters/ip-26-01877/accept", {"to": "Thoracic Surgery"}))
    assert "level" not in q and ref["status"] == "accepted" and ref["accepted_on"]
    assert store.events[-1]["trigger"] == "I13" and feed(data_dir)[-1].split("|", 9)[8] == "REF^I13"
    assert "Accepted by Thoracic Surgery" not in doctor.get("/his/encounters/ip-26-01877").text
    from his_mock import model
    disk = model.Store.load(paths.layout(data_dir)["store"])
    assert disk.encounters["ip-26-01877"]["referrals"][-1]["status"] == "accepted"


def test_refused_referrals_are_red_flashes(doctor, store, data_dir):
    n, m = len(store.events), len(feed(data_dir))
    _, q = location(post(doctor, "/his/encounters/ip-26-01877/refer", {"to": "Pulmonology", "reason": "x"}))
    assert q["level"] == "bad" and "another department" in q["flash"]
    _, q = location(post(doctor, "/his/encounters/ip-26-01877/refer", {"to": "Thoracic Surgery", "reason": " "}))
    assert q["level"] == "bad" and "reason" in q["flash"]
    _, q = location(post(doctor, "/his/encounters/ip-26-01877/accept", {"to": "Urology"}))
    assert q["level"] == "bad" and "no open referral" in q["flash"]
    assert len(store.events) == n and len(feed(data_dir)) == m
    html = doctor.get("/his/encounters/ip-26-01877", params={"flash": "nope", "level": "bad"}).text
    assert '<div class="flash bad">nope</div>' in html


def test_reception_cannot_refer(client, store):
    n = len(store.events)
    r = post(client, "/his/encounters/ip-26-01877/refer", {"to": "Thoracic Surgery", "reason": "x"})
    assert r.status_code == 403 and "Your role cannot do this" in r.text and len(store.events) == n
    html = client.get("/his/encounters/ip-26-01877").text
    assert "id=refer>" in html and "Your role cannot do this" in html.split("id=refer>", 1)[1].split("</div>", 1)[0]


def test_transfer_ward(client, store, data_dir):
    e = store.encounters["ip-26-01873"]
    h = len(e["ward_history"])
    path, q = location(post(client, "/his/encounters/ip-26-01873/transfer",
                            {"ward": "High Dependency Unit", "bed": "HDU-02", "reason": "Closer monitoring"}))
    assert "level" not in q and "transferred to High Dependency Unit, bed HDU-02" in q["flash"]
    assert (e["ward"], e["bed"]) == ("High Dependency Unit", "HDU-02") and len(e["ward_history"]) == h + 1
    assert e["ward_history"][-1]["reason"] == "Closer monitoring"
    assert store.events[-1]["trigger"] == "A02" and feed(data_dir)[-1].split("|", 9)[8] == "ADT^A02"
    _, q = location(post(client, "/his/encounters/op-26-118701/transfer", {"ward": "X", "bed": "1"}))
    assert q["level"] == "bad" and "not a current admission" in q["flash"]


def test_discharge(doctor, client, store, data_dir):
    html = doctor.get("/his/encounters/ip-26-01879").text
    assert "id=transfer>" in html and "id=discharge>" in html
    assert post(client, "/his/encounters/ip-26-01879/discharge").status_code == 403   # the desk does not discharge
    _, q = location(post(doctor, "/his/encounters/ip-26-01879/discharge"))
    e = store.encounters["ip-26-01879"]
    assert "level" not in q and e["status"] == "finished" and e["discharged"]
    assert store.events[-1]["trigger"] == "A03" and feed(data_dir)[-1].split("|", 9)[8] == "ADT^A03"
    _, q = location(post(doctor, "/his/encounters/ip-26-01879/discharge"))
    assert q["level"] == "bad"
    assert "id=discharge>" not in doctor.get("/his/encounters/ip-26-01879").text


def test_registration_validation_errors_sit_next_to_the_field(client, store):
    n = len(store.patients)
    r = post(client, "/his/registrations", {"name": "Test Person", "sex": "F", "age": "40"})
    assert r.status_code == 422 and "(SYNTHETIC)" in r.text and len(store.patients) == n
    assert 'class="row has-error"' in r.text and 'value="Test Person"' in r.text   # re-rendered with the typed value
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40",
                                            "kind": "temporary", "abha_number": "99-2600-0000-0999"})
    assert r.status_code == 422 and "permanent" in r.text
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40",
                                            "abha_number": "1234 5678 9012"})
    assert r.status_code == 422 and len(store.patients) == n
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "", "dob": "31/02/1986"})
    assert r.status_code == 422 and "DD/MM/YYYY" in r.text
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40", "phone": "12345"})
    assert r.status_code == 422 and "mobile" in r.text
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40", "pin": "12"})
    assert r.status_code == 422 and "6 digits" in r.text and len(store.patients) == n


def test_registration_then_duplicate_warning(client, store):
    path, q = location(post(client, "/his/registrations", {
        "name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40", "abha_number": "99-2600-0000-0999",
        "phone": "+91 98765 43210", "line": "12 Demo Street", "town": "Kalpitpur", "district": "Kalpitpur",
        "state": "Karnataka", "pin": "560001", "pmjay_id": "pmjay-vx-26009999"}))
    p = store.patients[path.rsplit("/", 1)[1]]
    assert "level" not in q and p["uhid"] > "VXH/26/004317" and p["abha"]["number"] == "99-2600-0000-0999"
    assert p["pmjay_id"] == "PMJAY-VX-26009999" and p["address"]["pin"] == "560001" and p["phone"] == "+91 98765 43210"
    assert store.events[-1]["trigger"] == "A28"
    # the same name, sex and age again: the duplicate warning, then "register anyway" as a temporary UHID
    r = post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "41", "kind": "temporary"})
    assert r.status_code == 409 and "Register anyway" in r.text and p["uhid"] in r.text
    path, q = location(post(client, "/his/registrations", {"name": "Asha Kiran (SYNTHETIC)", "sex": "F", "age": "40",
                                                           "kind": "temporary", "confirm_duplicate": "1"}))
    temp = store.patients[path.rsplit("/", 1)[1]]
    assert q["level"] == "warn" and "similar registration" in q["flash"]
    assert temp["uhid"].startswith("VXH/T/") and temp["uhid"] > "VXH/T/26/00412"
    assert [x["id"] for x in store.similar_registrations(temp["id"])] == [p["id"]]


def test_dob_gives_the_age(client, store):
    path, q = location(post(client, "/his/registrations", {"name": "Ravi Kumar (SYNTHETIC)", "sex": "M", "age": "",
                                                           "dob": "15/08/1970", "confirm_duplicate": "1"}))
    p = store.patients[path.rsplit("/", 1)[1]]
    assert p["dob"] == "15/08/1970" and p["dob_iso"] == "1970-08-15" and 55 <= p["age"] <= 57


def test_doctors_cannot_register(doctor, store):
    n = len(store.patients)
    r = post(doctor, "/his/registrations", {"name": "Someone Else (SYNTHETIC)", "sex": "M", "age": "30"})
    assert r.status_code == 403 and "Your role cannot do this" in r.text and len(store.patients) == n
    assert "Your role cannot do this" in doctor.get("/his").text.split("id=register>", 1)[1]


def test_new_visit_and_admission_numbers_above_fixtures(client, store, data_dir):
    pid = "vxh-26-004206"  # no PM-JAY ID, no admission
    path, q = location(post(client, f"/his/patients/{pid}/visits",
                            {"department": "Surgical Oncology", "unit": "Unit II",
                             "consultant_id": "prac-vxreg-20101", "visit_type": "follow_up"}))
    assert "level" not in q
    op = store.encounters_for(pid)[-1]
    assert path == f"/his/encounters/{op['id']}"
    assert op["kind"] == "OP" and op["number"].startswith("OP/") and int(op["number"].rsplit("/", 1)[1]) > 118724
    assert (op["department"], op["unit"], op["consultant_id"], op["visit_type"]) == \
        ("Surgical Oncology", "Unit II", "prac-vxreg-20101", "follow_up")
    assert feed(data_dir)[-1].split("|", 9)[8] == "ADT^A04"
    _, q = location(post(client, f"/his/patients/{pid}/visits",
                         {"department": "Surgical Oncology", "consultant_id": "prac-vxreg-20104"}))
    assert q["level"] == "bad" and "not a consultant of Surgical Oncology" in q["flash"]
    _, q = location(post(client, f"/his/patients/{pid}/admissions",
                         {"department": "Surgical Oncology", "ward": "Surgical Ward 2", "bed": "2-20",
                          "pmjay_preauth": "pending"}))
    assert q["level"] == "bad" and "PM-JAY" in q["flash"]
    path, q = location(post(client, f"/his/patients/{pid}/admissions",
                            {"department": "Surgical Oncology", "unit": "Unit II", "consultant_id": "prac-vxreg-20101",
                             "ward": "Surgical Ward 2", "bed": "2-20"}))
    ip = store.encounters_for(pid)[-1]
    assert "level" not in q and path == f"/his/encounters/{ip['id']}"
    assert ip["kind"] == "IP" and int(ip["number"].rsplit("/", 1)[1]) > 1879 and ip["status"] == "in-progress"
    assert feed(data_dir)[-1].split("|", 9)[8] == "ADT^A01"
    _, q = location(post(client, f"/his/patients/{pid}/admissions",
                         {"department": "Surgical Oncology", "ward": "W", "bed": "1"}))
    assert q["level"] == "bad" and "already admitted" in q["flash"]
    assert [p[0] for p in panels(client.get(f"/his/patients/{pid}").text)][:2] == [ip["id"], op["id"]]
    banner = text_of(client.get(f"/his/encounters/{ip['id']}").text.split("<div class=banner>", 1)[1].split("</div>", 1)[0])
    assert "Ward / Bed: Surgical Ward 2, 2-20" in banner and "Dr Arvind Menon" in banner


def test_pmjay_preauth_on_admission(client, store):
    pid = "vxh-26-004205"  # has a PM-JAY ID
    path, q = location(post(client, f"/his/patients/{pid}/admissions",
                            {"department": "ENT / Head and Neck Surgery", "ward": "Head and Neck Ward",
                             "bed": "HN-07", "pmjay_preauth": "pending"}))
    assert "level" not in q
    e = store.encounters[path.rsplit("/", 1)[1]]
    assert e["pmjay_preauth"] == {"status": "pending", "date": None}
    assert "PM-JAY Pre-Authorization" in client.get(path).text
    assert "PMJAY-VX" in client.get("/his/ipd").text.split("id=census>", 1)[1]


# -------------------------------------------------------------------- every page
def test_every_page_has_banner_no_em_dash_no_aadhaar(client, store):
    urls = ["/his", "/his?q=Sunita+Devi", "/his?q=parvathi", "/his/opd", "/his/ipd", "/his/lab", "/his/radiology",
            "/his/pathology", "/his/exchange", "/desk"]
    urls += [f"/his/patients/{p}" for p in store.patients]
    urls += [f"/his/encounters/{e}" for e in store.encounters]
    for u in urls:
        r = client.get(u)
        assert r.status_code == 200, u
        assert "SYNTHETIC DATA" in r.text, u
        assert EM_DASH not in r.text, u
        assert "aadhaar" not in r.text.lower(), u
        assert not AADHAAR_LIKE.search(text_of(r.text)), (u, AADHAAR_LIKE.search(text_of(r.text)).group(0))


def test_screen_strings_have_no_em_dash():
    from his_mock import admin, common, exchange, ipd, lab, opd, pathology, radiology, ui
    for m in (screens, ui, common, opd, ipd, lab, radiology, pathology, exchange, admin):
        assert EM_DASH not in open(m.__file__, encoding="utf-8").read(), m.__name__


def test_unknown_ids_give_404_pages(client):
    for u in ("/his/patients/nope", "/his/encounters/nope", "/his/lab/orders/nope", "/his/radiology/orders/nope",
              "/his/pathology/orders/nope", "/his/opd/orders/nope"):
        r = client.get(u)
        assert r.status_code == 404 and "No such" in r.text and "SYNTHETIC DATA" in r.text, u
    for u in ("/his/api/patients/nope", "/his/api/encounters/nope"):
        assert client.get(u).status_code == 404, u
    for u in ("/his/encounters/nope/refer", "/his/encounters/nope/discharge", "/his/patients/nope/visits",
              "/his/patients/nope/admissions", "/his/api/encounters/nope/transfer", "/his/api/patients/nope/visits"):
        assert client.post(u, data={}).status_code == 404, u


# -------------------------------------------------------------------- JSON API
def test_api_search_and_patient(client):
    r = client.get("/his/api/search", params={"q": "IP/26/01872"}).json()
    assert r["match"] == "identifier" and [p["id"] for p in r["patients"]] == ["vxh-26-004203"]
    r = client.get("/his/api/search", params={"q": "Sunita Devi"}).json()
    assert r["match"] == "name" and sorted(p["uhid"] for p in r["patients"]) == ["VXH/26/004204", "VXH/26/004210"]
    assert all(p["similar"] == [] for p in r["patients"])
    assert client.get("/his/api/search", params={"q": "zzzz"}).json() == {"q": "zzzz", "match": "none", "patients": []}
    d = client.get("/his/api/patients/vxh-t-26-00412").json()
    assert d["patient"]["uhid"] == "VXH/T/26/00412" and [s["id"] for s in d["similar"]] == ["vxh-26-004209"]
    d = client.get("/his/api/patients/vxh-26-004203").json()
    assert [e["number"] for e in d["encounters"]] == ["IP/26/01872", "OP/26/118705"]
    ip = d["encounters"][0]
    assert len(ip["ward_history"]) == 3 and ip["consultant"] == "Dr Kavitha Raghunathan"
    o = next(o for o in d["encounters"][1]["orders"] if o["accession"] == "RAD/26/00986")
    assert o["status"] == "completed" and o["report"]["status"] == "final" and o["report"]["versions"][0]["signed"]
    assert o["report"]["versions"][0]["pdf"] is None  # documents=False
    assert "aadhaar" not in str(d).lower()


def test_api_transitions(app, store, data_dir):
    client = TestClient(app)   # no login: the JSON API is for the tests and the demo script
    m = len(feed(data_dir))
    r = client.post("/his/api/registrations", json={"name": "Kiran Rao (SYNTHETIC)", "sex": "M", "age": 50})
    assert r.status_code == 200
    pid = r.json()["patient"]["id"]
    assert client.post("/his/api/registrations", json={"name": "Kiran Rao", "sex": "M", "age": 50}).status_code == 422
    dup = client.post("/his/api/registrations", json={"name": "Kiran Rao (SYNTHETIC)", "sex": "M", "age": 50})
    assert dup.status_code == 409 and dup.json()["error"] == "duplicate" and dup.json()["similar"] == [pid]
    r = client.post(f"/his/api/patients/{pid}/visits", json={"department": "Medical Oncology"})
    assert r.status_code == 200 and r.json()["encounter"]["kind"] == "OP"
    op = r.json()["encounter"]["id"]
    r = client.post(f"/his/api/encounters/{op}/refer", json={"to": "Radiation Oncology", "reason": "RT opinion"})
    assert r.status_code == 200 and r.json()["referral"]["status"] == "requested"
    assert client.post(f"/his/api/encounters/{op}/refer", json={"to": "Medical Oncology", "reason": "x"}).status_code == 409
    r = client.post(f"/his/api/encounters/{op}/accept", json={"to": "Radiation Oncology"})
    assert r.status_code == 200 and r.json()["referral"]["status"] == "accepted"
    assert client.post(f"/his/api/encounters/{op}/discharge").status_code == 409  # an OP visit is not an admission
    r = client.post(f"/his/api/encounters/{op}/orders", json={"tests": ["cbc", "chest_xray"]})
    assert r.status_code == 200 and [o["test"] for o in r.json()["orders"]] == ["cbc", "chest_xray"]
    assert r.json()["orders"][0]["accession"].startswith("PATH/") and r.json()["orders"][1]["accession"].startswith("RAD/")
    assert client.post(f"/his/api/encounters/{op}/orders", json={"tests": ["opd_note"]}).status_code == 422
    r = client.post(f"/his/api/patients/{pid}/admissions", json={"department": "Medical Oncology",
                                                                  "ward": "Medical Oncology Ward", "bed": "MO-11"})
    assert r.status_code == 200
    ip = r.json()["encounter"]["id"]
    r = client.post(f"/his/api/encounters/{ip}/transfer", json={"ward": "Medical Oncology Ward", "bed": "MO-12"})
    assert r.status_code == 200 and r.json()["encounter"]["bed"] == "MO-12"
    assert client.post(f"/his/api/encounters/{ip}/transfer", json={"ward": "", "bed": ""}).status_code == 422
    r = client.post(f"/his/api/encounters/{ip}/discharge")
    assert r.status_code == 200 and r.json()["encounter"]["status"] == "finished"
    assert [m.split("|", 9)[8] for m in feed(data_dir)[m:]] == \
        ["ADT^A28", "ADT^A04", "REF^I12", "REF^I13", "ORM^O01", "ORM^O01", "ADT^A01", "ADT^A02", "ADT^A03"]
    open_ip = client.get("/his/api/encounters", params={"kind": "IP", "status": "in-progress"}).json()["encounters"]
    assert all(e["kind"] == "IP" and e["status"] == "in-progress" for e in open_ip) and ip not in [e["id"] for e in open_ip]
