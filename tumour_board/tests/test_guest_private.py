"""Guest reviewers with anonymized real files (5 Nov 2026): a login with org.json real_data creates PRIVATE Case Files (only it sees
them, anywhere), uploads into them through upload_safety (type checked, dangerous files refused, metadata removed, likely
identifiers stop the upload until "upload anyway" with a reason), deletes them, and they go by themselves after the retention
period. On a site with TB_UPLOAD_POLICY=private_only only such logins upload. Two-factor sign-in comes first for them.
Synthetic data only; no model is called (reading is replaced by a no-op)."""
import datetime as dt
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import config, org, scheduler, service, store, upload_safety
from tumour_board.tests.test_nik_me import ANIL, MEHTA, RAO, VX, Api, FakeAuth, people  # noqa: F401 (fixture)

GR = "guest.reviewer@example.org"   # guest reviewer, Breast Surgery, real_data
CASE_A = {"name": "Case A", "age": 52, "sex": "F"}


@pytest.fixture
def guests(people):
    o = org.load()
    o["users"][GR] = {"departments": {"breast_surgery": "member"}, "display_name": "Guest reviewer (synthetic)", "real_data": True}
    org.save(o, by="test")
    return {**people, GR: org.roles(GR)}


@pytest.fixture
def app(guests, monkeypatch):
    import routes.tumour_board_routes as R
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    monkeypatch.setenv("TB_UPLOAD_POLICY", "private_only")

    async def no_reading(case_id, doc_ids, job, from_stored=False):
        job["state"] = "finished"
    monkeypatch.setattr(service, "process_docs", no_reading)
    auth = FakeAuth(list(guests) + [VX], admins=(VX,))
    auth.totp_enabled = lambda u: True
    a = FastAPI()
    who = {"user": GR}

    @a.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    a.include_router(R.setup_tumour_board_routes())
    a.state.auth_manager = auth
    with TestClient(a) as tc:
        api = Api(tc, who)
        api.auth = auth
        yield api


def create_private(api, **extra):
    r = api.as_(GR).post("/cases", json={"patient": CASE_A, "protocol": "breast", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def upload(api, case_id, files, **form):
    return api.tc.post(f"/api/tb/cases/{case_id}/documents", files=[("files", f) for f in files], data=form)


# ---- creation and visibility ----------------------------------------------------------------------------------------------------

def test_a_guest_creates_a_private_case_file_with_a_server_made_id(app):
    c = create_private(app, case_id="TB-CHOSEN")
    cid = c["case_id"]
    assert cid.startswith("PRV-") and cid != "TB-CHOSEN" and c.get("private") is True
    assert (store.case_dir(cid) / config.PRIVATE_MARKER).is_file() and config.is_private(cid) and cid in config.HIDDEN_CASES
    assert cid not in config.PROTECTED_CASES          # AI processing stays on for it
    assert not store.case_dir("TB-CHOSEN").exists()


def test_a_client_id_never_marks_someone_elses_case_file(app):
    other = store.create_case("TB-OTHER", {"name": "SYNTHETIC X"}, "breast", created_by=RAO)
    c = create_private(app, case_id="TB-OTHER")
    assert c["case_id"] != "TB-OTHER" and not config.is_private("TB-OTHER") and store.get_case("TB-OTHER") == other


def test_nobody_else_sees_or_opens_it(app):
    cid = create_private(app)["case_id"]
    assert cid in [x.get("case_id") or x.get("id") for x in _cases(app, GR)]
    assert app.as_(GR).get(f"/cases/{cid}").status_code == 200
    for who in (RAO, MEHTA, VX):                       # same department, another department, the Vaidyx admin (the coordinator reads it: below)
        assert cid not in [x.get("case_id") or x.get("id") for x in _cases(app, who)], who
        assert app.as_(who).get(f"/cases/{cid}").status_code in (403, 404), who
        assert cid not in app.as_(who).get(f"/cases/{cid}").text or who == VX


def _cases(api, who):
    r = api.as_(who).get("/cases")
    assert r.status_code == 200, r.text
    b = r.json()
    return b.get("cases", b) if isinstance(b, dict) else b


def test_a_guest_does_not_create_from_the_hospital_system(app):
    r = app.as_(GR).post("/cases/from-his", json={"identifier": "VXH/26/004201", "protocol": "breast"})
    assert r.status_code == 403 and "own files" in r.text


def test_the_real_data_flag_survives_an_organisation_save(guests):
    o = org.load()
    org.save(o, by="test")
    assert org.load()["users"][GR]["real_data"] is True and org.roles(GR)["real_data"] is True
    assert org.roles(RAO)["real_data"] is False


# ---- upload --------------------------------------------------------------------------------------------------------------------

CLEAN_TXT = ("report.txt", b"Histopathology: invasive ductal carcinoma, grade 2. ER positive 90%, PR positive 70%, HER2 negative.\n")
PLANTED_TXT = ("note.txt", b"Patient Name: Ramesh Kumar Age 52\nMobile 98450 12312\nAadhaar 4821 7733 9919\nUHID: VXH/26/004201\n")


def test_only_guests_upload_on_a_private_only_site(app):
    store.create_case("TB-RAO", {"name": "SYNTHETIC"}, "breast", created_by=RAO)
    c = store.get_case("TB-RAO"); c["department"] = "breast_surgery"; store.save_case(c)
    r = upload(app.as_(RAO), "TB-RAO", [CLEAN_TXT])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "upload_private_only"
    r = app.tc.post("/api/tb/intake/documents", files=[("files", CLEAN_TXT)], data={"department": "breast_surgery"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "upload_private_only"


def test_the_uploader_confirms_the_files_are_anonymized(app):
    cid = create_private(app)["case_id"]
    r = upload(app.as_(GR), cid, [CLEAN_TXT])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "confirm_anonymized"
    r = upload(app.as_(GR), cid, [CLEAN_TXT], anonymized="1")
    assert r.status_code == 200, r.text
    d = store.list_docs(cid)[0]
    assert d["uploaded"]["anonymized_by_uploader"] is True and d["uploaded"]["by"] == GR and d["uploaded"]["text_checked"] is True


def test_likely_identifiers_are_noted_not_blocking(app):
    """Eswar, 5 Nov 2026: finding identifiers is not strictly needed; the upload goes through and only the kinds are recorded."""
    cid = create_private(app)["case_id"]
    r = upload(app.as_(GR), cid, [PLANTED_TXT], anonymized="1")
    assert r.status_code == 200, r.text
    d = store.list_docs(cid)[0]
    kinds = {f["kind"] for f in d["uploaded"]["identifiers_at_upload"]}
    assert {"patient name", "mobile number", "12-digit number (Aadhaar-like)", "hospital id"} <= kinds
    assert "upload_anyway_reason" not in d["uploaded"]
    ev = [e for e in store.read_audit(cid) if e.get("kind") == "private_upload"][-1]
    assert ev["possible_identifiers"] and "Ramesh" not in json.dumps(ev) and "Ramesh" not in json.dumps(d["uploaded"])


@pytest.mark.parametrize("f,why", [(("scan.dcm", b"\x00" * 200), "not accepted"), (("report.pdf", b"MZ\x90\x00 not a pdf"), "does not match"),
                                   (("a.pdf", b"%PDF-1.4\n1 0 obj << /OpenAction << /S /JavaScript /JS (x) >> >>"), "scripts")])
def test_refused_files_stop_the_whole_upload(app, f, why):
    cid = create_private(app)["case_id"]
    r = upload(app.as_(GR), cid, [CLEAN_TXT, f], anonymized="1")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "upload_refused" and why in r.text
    assert store.list_docs(cid) == []


def test_the_stored_copy_is_the_cleaned_one(app):
    cid = create_private(app)["case_id"]
    r = upload(app.as_(GR), cid, [("scan.jpg", _jpeg_with_exif())], anonymized="1")
    assert r.status_code == 200, r.text
    d = store.list_docs(cid)[0]
    from PIL import Image
    im = Image.open(store.original_path(cid, d["doc_id"]))
    assert not im.info.get("exif") and any("image details" in n for n in d["uploaded"]["cleaned"])


# ---- delete and retention --------------------------------------------------------------------------------------------------------

def test_the_guest_deletes_their_own_private_case_file_and_a_receipt_stays(app):
    cid = create_private(app)["case_id"]
    assert upload(app.as_(GR), cid, [CLEAN_TXT], anonymized="1").status_code == 200   # leaves a job record
    assert app.as_(RAO).delete(f"/cases/{cid}").status_code in (403, 404)
    r = app.as_(GR).delete(f"/cases/{cid}")
    assert r.status_code == 200, r.text
    assert not store.case_dir(cid).exists()
    assert not any(cid in p.read_text() for p in (config.DATA_ROOT / "jobs").glob("*.json"))      # no job record left either
    rec = [json.loads(x) for x in (config.DATA_ROOT / "private_deletions.jsonl").read_text().splitlines()]
    assert rec[-1]["case_id"] == cid and rec[-1]["by"] == GR and "Case A" not in json.dumps(rec)


def test_private_case_files_go_after_the_retention_period(app, monkeypatch):
    old = create_private(app)["case_id"]
    new = create_private(app)["case_id"]
    c = store.get_case(old); c["created"] = (dt.datetime.now() - dt.timedelta(days=91)).isoformat(timespec="seconds"); store.save_case(c)
    plain = store.create_case("TB-PLAIN", {"name": "SYNTHETIC"}, "breast", created_by=RAO)
    plain["created"] = "2020-01-01T00:00:00"; store.save_case(plain)
    out = scheduler.private_retention_job(dt.datetime.now())
    assert out["deleted"] == [old] and store.get_case(new) and store.get_case("TB-PLAIN")
    monkeypatch.setenv("TB_PRIVATE_RETENTION_DAYS", "0")
    assert scheduler.private_retention_job(dt.datetime.now() + dt.timedelta(days=400)) == {"kept": "retention off"}


# ---- two-factor sign-in and the me payload --------------------------------------------------------------------------------------

def test_two_factor_sign_in_comes_first_for_a_guest(app):
    app.auth.totp_enabled = lambda u: False
    r = app.as_(GR).get("/cases")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "two_factor_required"
    me = app.as_(GR).get("/me").json()
    assert me["two_factor_required"] is True and me["real_data"] is True and me["upload_policy"] == "private_only"
    assert app.as_(RAO).get("/cases").status_code == 200          # others are not affected
    assert app.as_(RAO).get("/me").json()["two_factor_required"] is False


# ---- after reading -------------------------------------------------------------------------------------------------------------

def test_the_read_text_of_a_private_record_is_checked_too(app):
    cid = create_private(app)["case_id"]
    d = store.add_document_file(cid, "scan.png", b"x")
    d.update({"state": "ready", "pages": [{"text": "Discharge summary", "method": "ocr"}, {"text": "Contact 98450 12312", "method": "ocr"}]})
    store.save_doc(cid, d)
    service._identifiers_after_reading(cid, [d["doc_id"]])
    got = store.get_doc(cid, d["doc_id"])["identifiers_after_reading"]
    assert got and got[0]["kind"] == "mobile number" and got[0]["where"] == "page 2" and "98450" not in json.dumps(got)


# ---- upload_safety units -------------------------------------------------------------------------------------------------------

def _jpeg_with_exif() -> bytes:
    from PIL import Image
    im = Image.new("RGB", (40, 30), "white")
    exif = Image.Exif(); exif[0x013B] = "Dr Somebody"; exif[0x0131] = "PhoneCamera 1.0"
    b = io.BytesIO(); im.save(b, format="JPEG", exif=exif.tobytes()); return b.getvalue()


def test_pdf_document_details_are_removed():
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(); w.add_blank_page(200, 200); w.add_metadata({"/Author": "Dr Somebody", "/Title": "Ramesh Kumar CT"})
    b = io.BytesIO(); w.write(b)
    c = upload_safety.check("ct.pdf", b.getvalue())
    assert not c.refused
    meta = PdfReader(io.BytesIO(c.data)).metadata
    assert not meta or not (meta.get("/Author") or meta.get("/Title"))


def test_password_protected_pdfs_are_refused():
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(200, 200); w.encrypt("secret")
    b = io.BytesIO(); w.write(b)
    assert "password" in upload_safety.check("locked.pdf", b.getvalue()).refused


def test_office_author_is_removed_and_macros_are_refused():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Dr Somebody</dc:creator></cp:coreProperties>")
        z.writestr("word/document.xml", "<w:document><w:t>ER positive</w:t></w:document>")
    c = upload_safety.check("report.docx", b.getvalue())
    assert not c.refused and b"Dr Somebody" not in zipfile.ZipFile(io.BytesIO(c.data)).read("docProps/core.xml")
    m = io.BytesIO()
    with zipfile.ZipFile(m, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>"); z.writestr("word/vbaProject.bin", "x")
    assert "macros" in upload_safety.check("report.docm.docx", m.getvalue()).refused


@pytest.mark.parametrize("text,kind", [("Mobile: +91 98450 12312", "mobile number"), ("Aadhaar 4821 7733 9919", "12-digit number (Aadhaar-like)"),
                                       ("ABHA 91-2345-6789-0123", "ABHA number"), ("mail: a.b@example.com", "e-mail address"),
                                       ("MRN: AB12345", "hospital id"), ("DOB: 12/03/1972", "date of birth"), ("Bengaluru - 560041", "PIN code"),
                                       ("Patient Name: Lakshmi Iyer", "patient name")])
def test_identifier_kinds(text, kind):
    f = upload_safety.scan_text(text)
    assert f and f[0]["kind"] == kind


@pytest.mark.parametrize("text", ["Name: XXXX", "Name: Case A", "Patient Name: ****", "Hb 12.4 g/dL, platelets 250000, Ki-67 25%",
                                  "Tumour size 2.5 x 1.8 x 1.2 cm, 3 of 14 nodes", "Name: Anonymized"])
def test_blanks_and_clinical_numbers_are_not_identifiers(text):
    assert upload_safety.scan_text(text) == []


# ---- the 5 Nov independent review --------------------------------------------------------------------------------------------

def test_a_private_case_file_is_never_referred_nor_in_anyone_s_referral_inbox(app):
    from tumour_board import referral
    cid = create_private(app)["case_id"]
    r = app.as_(GR).post(f"/cases/{cid}/referrals", json={"to": "medical_oncology", "reason": "second opinion"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "guest_scope"
    c = store.get_case(cid)                      # even a referral written straight into the file stays invisible
    c["referrals"] = [{"to": "medical_oncology", "from": "breast_surgery", "status": "requested", "at": store.now_iso()}]
    store.save_case(c)
    for who in (RAO, MEHTA, ANIL):
        assert cid not in json.dumps(referral.inbox(org.roles(who))), who


def test_a_padded_id_is_not_a_case_file(app):
    cid = create_private(app)["case_id"]
    for path in (f"/cases/%20{cid}/documents", f"/cases/{cid}%20", f"/cases/%20{cid}"):
        r = app.tc.post("/api/tb" + path, files=[("files", PLANTED_TXT)], data={"anonymized": "1"}) if path.endswith("documents") else app.as_(GR).get(path)
        assert r.status_code == 404, (path, r.status_code)
    assert store.list_docs(cid) == []


@pytest.mark.parametrize("method,path", [("POST", "/intake/documents"), ("GET", "/intake"), ("POST", "/demo/TB-001"),
                                         ("GET", "/his/lookup?identifier=VXH/26/004201")])
def test_a_guest_stays_inside_their_private_case_files(app, method, path):
    r = app.as_(GR).tc.request(method, "/api/tb" + path)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "guest_scope", r.text


def test_a_guest_uploads_nowhere_else_even_where_everyone_may(app, monkeypatch):
    monkeypatch.setenv("TB_UPLOAD_POLICY", "all")
    o = org.load(); o["users"][GR]["departments"] = {"breast_surgery": "member"}; org.save(o, by="test")
    plain = store.create_case("TB-PLAIN2", {"name": "SYNTHETIC"}, "breast", created_by=RAO)
    plain["department"] = "breast_surgery"; store.save_case(plain)
    r = upload(app.as_(GR), "TB-PLAIN2", [CLEAN_TXT])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "upload_private_only"


def test_stored_names_are_neutral_and_the_audit_has_no_file_name(app):
    cid = create_private(app)["case_id"]
    r = upload(app.as_(GR), cid, [("Ramesh_Kumar_discharge.txt", CLEAN_TXT[1])], anonymized="1")   # a bare name is not detectable
    assert r.status_code == 200, r.text
    d = store.list_docs(cid)[0]
    assert d["filename"] == "record-1.txt" and "Ramesh" not in json.dumps(d)
    assert "Ramesh" not in json.dumps(store.read_audit(cid))


def test_others_get_404_for_a_private_case_file(app):
    cid = create_private(app)["case_id"]
    for who in (RAO, MEHTA):                     # the coordinator reads it (Eswar, 5 Nov 2026)
        assert app.as_(who).get(f"/cases/{cid}").status_code == 404, who


def test_a_hex_escaped_script_does_not_survive_the_pdf_rebuild():
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject
    w = PdfWriter(); w.add_blank_page(200, 200)
    w._root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert(1)")})
    b = io.BytesIO(); w.write(b)
    raw = b.getvalue().replace(b"/JavaScript", b"/J#61vaScript").replace(b"/JS ", b"/J#53 ")
    c = upload_safety.check("x.pdf", raw)
    if not c.refused:                                # rebuilt from the pages: no open action, no script left
        assert b"JavaScript" not in c.data and "/OpenAction" not in PdfReader(io.BytesIO(c.data)).trailer["/Root"]


def test_an_office_zip_bomb_is_refused():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:t>" + "A" * (210 * 1024 * 1024) + "</w:t>")
    c = upload_safety.check("big.docx", b.getvalue())
    assert c.refused and ("unpacked" in c.refused or "expands" in c.refused)


def test_short_values_are_masked_harder():
    f = upload_safety.scan_text("Bengaluru - 560041")
    assert f and f[0]["sample"] == "5••••1"


def test_office_company_and_comment_authors_are_removed():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/app.xml", "<Properties><Company>Sunrise Hospital</Company><Manager>Dr X</Manager></Properties>")
        z.writestr("word/comments.xml", '<w:comments><w:comment w:author="Dr Somebody" w:initials="DS"/></w:comments>')
        z.writestr("word/document.xml", "<w:document/>")
    c = upload_safety.check("r.docx", b.getvalue())
    z = zipfile.ZipFile(io.BytesIO(c.data))
    assert b"Sunrise" not in z.read("docProps/app.xml") and b"Dr Somebody" not in z.read("word/comments.xml")


@pytest.mark.parametrize("path", ["/requests", "/team/code"])
def test_a_private_case_file_brings_nobody_in(app, path):
    cid = create_private(app)["case_id"]
    r = app.as_(GR).post(f"/cases/{cid}{path}", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "guest_scope", (path, r.text)


def test_a_private_case_file_offers_no_sharing_actions(app):
    cid = create_private(app)["case_id"]
    p = app.as_(GR).get(f"/cases/{cid}").json()["permissions"]
    assert not any(p.get(k) for k in ("send_request", "create_request", "refer", "manage_participants", "remind"))
    assert p["upload"] is True and p["delete_case"] is True
    assert p["mark_ready"] is True              # Send to the board is allowed (Eswar, 5 Nov 2026, "Allow the board")


def test_the_guest_sends_a_private_case_file_to_the_board(app):
    """Eswar, 5 Nov 2026: Send to the board works for a private Case File; it then belongs on the board (not hidden from the meeting
    code), still hidden everywhere else; taking it back hides it from the board again."""
    from tumour_board import steps
    cid = create_private(app)["case_id"]
    c = store.get_case(cid); c["board_question"] = "Sequencing of treatment?"; store.save_case(c)
    st = store.get_state(cid); st["board_question"] = "Sequencing of treatment?"; store.save_state(cid, st)
    r = app.as_(GR).post(f"/cases/{cid}/ready", json={"list": "discussion", "reason": "test with items open"})
    assert r.status_code == 200, r.text
    assert config.sent_to_board(cid) and cid not in config.BOARD_HIDDEN and cid in config.HIDDEN_CASES
    assert cid not in [x.get("case_id") for x in _cases(app, RAO)]              # still not listed for other doctors
    r = app.as_(GR).post(f"/cases/{cid}/ready", json={"ready": False})
    assert r.status_code == 200 and cid in config.BOARD_HIDDEN


def test_the_coordinator_lists_and_reads_a_private_case_file_but_changes_nothing(app):
    """Eswar, 5 Nov 2026: the guest reviewer and the MDT Coordinator see a private Case File; the coordinator only reads it."""
    cid = create_private(app)["case_id"]
    assert upload(app.as_(GR), cid, [CLEAN_TXT], anonymized="1").status_code == 200
    assert cid in [x.get("case_id") or x.get("id") for x in _cases(app, ANIL)]
    r = app.as_(ANIL).get(f"/cases/{cid}")
    assert r.status_code == 200, r.text
    perms = r.json().get("permissions") or {}
    assert perms and not any(v for v in perms.values() if isinstance(v, bool)), perms
    assert not any(x for v in perms.values() if isinstance(v, dict) for x in v.values()), perms
    rows = app.as_(ANIL).get("/case-list").json()
    rows = rows.get("rows", rows.get("cases", rows)) if isinstance(rows, dict) else rows
    mine = [x for x in rows if x.get("case_id") == cid]
    assert mine and mine[0]["relation"] == "coordinator" and mine[0]["private"] is True
    assert upload(app.as_(ANIL), cid, [CLEAN_TXT], anonymized="1").status_code in (403, 404)
    assert app.as_(ANIL).delete(f"/cases/{cid}").status_code == 403
    assert app.as_(ANIL).post(f"/cases/{cid}/ready", json={}).status_code == 403
    assert store.case_dir(cid).exists() and len(store.list_docs(cid)) == 1
    hs = app.as_(ANIL).get(f"/cases/{cid}/helpers").json()["helpers"]
    assert hs and not any(h["prepare_allowed"] for h in hs)                   # no Prepare buttons for a reader
    assert app.as_(ANIL).post(f"/cases/{cid}/helpers/prepare-all", json={}).status_code == 403
    from tumour_board import access
    assert access.scope(org.roles(ANIL), store.get_case(cid)) == access.READ
    assert not access.coordinator_view(org.roles(GR), store.get_case(cid))      # a guest never gets the coordinator's view
    assert not access.coordinator_view(org.roles(ANIL), store.get_case("TB-2026-bharath") or {"case_id": "TB-2026-bharath"})  # never the real case


def test_a_guest_needs_no_registration_number(app):
    """Eswar, 5 Nov 2026: an outside reviewer may have no medical council number; a name is enough to finish the set-up."""
    from tumour_board import profiles
    assert not profiles.is_doctor(org.roles(GR)) and profiles.is_doctor(org.roles(RAO))
    r = app.as_(GR).put("/me/profile", json={"display_name": "Guest Reviewer"})
    assert r.status_code == 200, r.text
    assert r.json()["setup_needed"] is False


def test_a_private_case_file_has_no_patient_to_match(app):
    """Eswar, 5 Nov 2026: anonymized files on a labelled private Case File never show "name or number does not match"."""
    from tumour_board import rules, steps
    cid = create_private(app)["case_id"]
    c = store.get_case(cid)
    d = {"doc_id": "D1", "state": "ready", "identity": "mismatch_or_missing", "classification": {}, "fields": {}}
    assert not any("does not match" in x for x in steps.doc_check(d, c)["reasons"])
    plain = store.create_case("TB-PLAIN3", {"name": "SYNTHETIC P"}, "breast", created_by=RAO)
    assert any("does not match" in x for x in steps.doc_check(d, plain)["reasons"])       # an ordinary Case File keeps the check
    assert upload(app.as_(GR), cid, [CLEAN_TXT], anonymized="1").status_code == 200
    doc = store.list_docs(cid)[0]; doc.update(state="ready", identity="mismatch_or_missing"); store.save_doc(cid, doc)
    g = rules.evaluate(cid)
    assert not g or not (g.get("documents") or {}).get("identity_flags")


def test_the_next_step_on_a_private_case_file_is_adding_files_not_sending_requests():
    from tumour_board import steps
    nxt = steps._next(missing=[1], groups={"x": {}, "y": {}}, doc_todo=[], problems=[], unconfirmed=[], question_done=True, prose={}, sent=False,
                      warns=[], private=True)
    assert nxt == {"section": "reports", "label": "Add 2 missing files"}
    assert steps._next(missing=[1], groups={"x": {}}, doc_todo=[], problems=[], unconfirmed=[], question_done=True, prose={}, sent=False,
                       warns=[])["label"] == "Send 1 request"


def test_a_private_case_file_names_only_its_own_guest_as_the_doctor(app):
    """5 Nov 2026: two guest reviewers in one department: the Case File header and team notices name the creator, never the other guest."""
    from tumour_board import team
    o = org.load(); o["users"]["aaa.other.guest@example.org"] = {"departments": {"breast_surgery": "member"}, "display_name": "Other guest", "real_data": True}
    org.save(o, by="test")
    cid = create_private(app)["case_id"]
    assert team.owner_consultants(store.get_case(cid)) == [GR]
    assert team.owner_consultants({"case_id": "TB-X", "department": "breast_surgery"})[0] == "aaa.other.guest@example.org"   # ordinary rule elsewhere
