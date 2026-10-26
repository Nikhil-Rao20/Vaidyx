"""One Case File per patient and cancer (night-v3 item 1.1). Creating a Case File for a patient (the same UHID, or a registration linked
to a Case File) and the same cancer as a live Case File is refused with 409 on every creation path (POST /cases/from-his, POST /cases)
with the existing file's owner; archived and protected Case Files never count; another cancer is allowed and linked both ways. The New
Case File page lists the patient's Case Files (GET /patient-case-files) and a doctor who cannot open one asks to join it (POST
/case-join/ask): a resident joins the team as a resident, a consultant of another department as a team member who reads the whole Case
File but never takes the owner's rights. Synthetic data only; the hospital system is an in-memory fake and no model is called."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import access, config, his_case, his_client, notify, org, store, team
from tumour_board.tests import util
from tumour_board.tests.test_his_case import PAT, TEMP, UHID, FakeHIS, fakes  # noqa: F401 (fixture)
from tumour_board.tests.test_nik_me import (ANIL, ASHA, AUDIT, GUEST, MEHTA, RAO, RAVI, ROOT, VIJAY, VX, Api, FakeAuth, auth,  # noqa: F401
                                            make_case, people)

DUP_MESSAGE = "A Case File for this patient and this cancer exists (Breast Surgery, Dr Rao (synthetic))"


@pytest.fixture
def app(auth, fakes, monkeypatch):
    """The whole Tumour Board API (old routes and the new routers) behind a switchable login, with the fake hospital system."""
    import routes.tumour_board_routes as R
    from tumour_board.api import patients
    from tumour_board.api import team as team_api
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    monkeypatch.setattr(his_client, "client", lambda: FakeHIS([]))
    patients.CHECK_LIMIT._hits.clear()
    team_api.ASK_LIMIT._hits.clear()
    a = FastAPI()
    who = {"user": RAO}

    @a.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    a.include_router(R.setup_tumour_board_routes())
    a.state.auth_manager = auth
    with TestClient(a) as tc:
        yield Api(tc, who)


def from_his(api, user, identifier=UHID, protocol="breast", setting="early", **extra):
    return api.as_(user).post("/cases/from-his", json={"identifier": identifier, "protocol": protocol, "setting": setting, **extra})


def case_dirs():
    return sorted(c["case_id"] for c in store.list_cases())


def kinds(case_id):
    return [e.get("kind") for e in store.read_audit(case_id)]


# ---- the helper ----------------------------------------------------------------------------------------------------------------------

def test_case_uhids_reads_the_registration_the_uhid_and_linked_registrations(data_root):
    c = {"his": {"uhid": "VXH/26/004201"}, "patient": {"mrn": "VXH/26/004201", "ids": [{"kind": "uhid", "value": "VXH/T/26/00412", "from": "his_link"},
                                                                                     {"kind": "ip_no", "value": "IP/26/01871"}, {"kind": "abha", "value": "99-2600"}]}}
    assert his_case.case_uhids(c) == {"VXH26004201", "VXHT2600412"}  # IP / OP No. and ABHA are not UHIDs
    assert his_case.case_uhids({"patient": {"mrn": " vxh-26-004201 "}}) == {"VXH26004201"}
    assert his_case.case_uhids({}) == set() and his_case.same_patient_cases([""]) == []


# ---- the refusal on every path -----------------------------------------------------------------------------------------------------------

def test_from_his_refuses_the_same_cancer_with_the_existing_owner(app, people):
    r = from_his(app, RAO, case_id="TB-DUP-A")
    assert r.status_code == 200, r.text
    # another department, the same patient and cancer: refused, named, no Case File made
    r = from_his(app, MEHTA, case_id="TB-DUP-X")
    assert r.status_code == 409, r.text
    b = r.json()
    assert b["detail"] == DUP_MESSAGE and b["code"] == "duplicate_case_file"
    assert b["existing"] == {"case_id": "TB-DUP-A", "protocol": "breast", "cancer_name": "", "cancer_label": "Breast cancer", "department": "breast_surgery",
                             "department_name": "Breast Surgery", "owner": RAO, "owner_name": "Dr Rao (synthetic)", "can_open": False}
    assert case_dirs() == ["TB-DUP-A"]
    # the owner by another number of the same patient (an IP No.): refused too, and may open the existing one
    r = from_his(app, RAO, identifier="IP/26/01871")
    assert r.status_code == 409 and r.json()["existing"]["can_open"] is True and case_dirs() == ["TB-DUP-A"]
    refused = [e for e in store.read_audit("TB-DUP-A") if e["kind"] == "duplicate_refused"]
    assert [(e["by"], e["protocol"], e["via"]) for e in refused] == [(MEHTA, "breast", "from_his"), (RAO, "breast", "from_his")]
    assert all(set(e) <= {"ts", "kind", "by", "protocol", "cancer_name", "via", "prev", "hash"} for e in refused), refused  # no patient detail
    assert "same_uhid_case" not in store.get_case("TB-DUP-A")["his"]


def test_manual_post_cases_refuses_the_same_cancer_and_counts_manual_files(app, people):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    pat = {"name": "SYNTHETIC, Test Patient", "mrn": "vxh-26-004201", "agesex": "46 Y / F"}  # the same UHID, written another way
    r = app.as_(RAO).post("/cases", json={"case_id": "TB-DUP-M", "patient": pat, "protocol": "breast", "setting": "early"})
    assert r.status_code == 409 and r.json()["code"] == "duplicate_case_file" and r.json()["existing"]["case_id"] == "TB-DUP-A" and store.get_case("TB-DUP-M") is None
    assert [e["via"] for e in store.read_audit("TB-DUP-A") if e["kind"] == "duplicate_refused"] == ["manual"]
    # another cancer, and no cancer yet, are allowed by hand
    r = app.as_(RAO).post("/cases", json={"case_id": "TB-DUP-G", "patient": pat, "protocol": "generic", "setting": "as_recorded", "cancer_name": "Thyroid"})
    assert r.status_code == 200, r.text
    assert app.as_(RAO).post("/cases", json={"case_id": "TB-DUP-N", "patient": pat}).status_code == 200
    # a hand-made Case File counts for the hospital-system path: the same typed cancer under the generic rule is refused
    r = from_his(app, RAO, protocol="generic", setting="as_recorded", cancer_name="thyroid")
    assert r.status_code == 409 and r.json()["existing"]["case_id"] == "TB-DUP-G" and r.json()["existing"]["cancer_label"] == "Thyroid (no checklist yet)"
    r = from_his(app, RAO, protocol="generic", setting="as_recorded", cancer_name="Gallbladder", case_id="TB-DUP-GB")
    assert r.status_code == 200, r.text


def test_a_linked_registration_counts_as_the_same_patient(app, people):
    # a Case File made under the temporary registration, to which a person linked the permanent UHID
    make_case("TB-DUP-T", patient={"name": "Anitha Reddy (SYNTHETIC)", "mrn": TEMP["uhid"], "ids": [{"kind": "uhid", "value": TEMP["uhid"], "from": "his"},
                                                                                                    {"kind": "uhid", "value": UHID, "from": "his_link"}]})
    r = from_his(app, RAO)
    assert r.status_code == 409 and r.json()["existing"]["case_id"] == "TB-DUP-T"
    # another cancer is allowed and linked to it through the linked registration
    r = from_his(app, MEHTA, protocol="lung_nsclc", setting="non_metastatic", case_id="TB-DUP-L")
    assert r.status_code == 200, r.text
    assert [l["case_id"] for l in store.get_case("TB-DUP-L")["linked_cases"]] == ["TB-DUP-T"]
    assert [l["case_id"] for l in store.get_case("TB-DUP-T")["linked_cases"]] == ["TB-DUP-L"]


def test_archived_and_protected_case_files_never_count(app, people, monkeypatch):
    make_case("TB-DUP-OLD", patient={"name": "x", "mrn": UHID})
    team.archive("TB-DUP-OLD", RAO, "duplicate (synthetic)")
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-REAL-X"})
    make_case("TB-REAL-X", patient={"name": "x", "mrn": UHID})
    r = from_his(app, RAO, case_id="TB-DUP-NEW")
    assert r.status_code == 200, r.text
    c = store.get_case("TB-DUP-NEW")
    assert "linked_cases" not in c  # neither the archived nor the protected file is linked
    assert not any(e["kind"] == "duplicate_refused" for e in store.read_audit("TB-REAL-X"))
    rows = app.as_(RAO).get("/patient-case-files", params={"identifier": UHID}).json()["cases"]
    assert [x["case_id"] for x in rows] == ["TB-DUP-NEW"]


def test_another_cancer_is_allowed_and_linked_both_ways(app, people):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    r = from_his(app, MEHTA, protocol="lung_nsclc", setting="non_metastatic", case_id="TB-DUP-B")
    assert r.status_code == 200, r.text
    assert [l["case_id"] for l in store.get_case("TB-DUP-B")["linked_cases"]] == ["TB-DUP-A"]
    assert [l["case_id"] for l in store.get_case("TB-DUP-A")["linked_cases"]] == ["TB-DUP-B"]
    rows = app.as_(MEHTA).get("/patient-case-files", params={"identifier": "OP/26/118701"}).json()["cases"]
    assert [(x["case_id"], x["department_name"], x["can_open"]) for x in rows] == [("TB-DUP-A", "Breast Surgery", True), ("TB-DUP-B", "Medical Oncology", True)]


# ---- GET /patient-case-files ---------------------------------------------------------------------------------------------------------------

def test_patient_case_files_lists_briefs_for_placed_logins_only(app, people):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    r = app.as_(RAVI).get("/patient-case-files", params={"identifier": UHID})
    assert r.status_code == 200, r.text
    row = r.json()["cases"][0]
    assert set(row) == {"case_id", "protocol", "cancer_name", "cancer_label", "department", "department_name", "owner", "owner_name", "owner_words", "can_open",
                        "created_at", "status_label"}
    assert row["can_open"] is False and row["owner_words"] == "Breast Surgery, Dr Rao (synthetic)" and row["status_label"] == "Being prepared"
    assert PAT["name"] not in r.text and UHID not in r.text  # no patient name, no identifier back
    assert app.as_(ANIL).get("/patient-case-files", params={"identifier": UHID}).json()["cases"][0]["can_open"] is True  # the coordinator
    for who in (GUEST, VX, ROOT, AUDIT):
        assert app.as_(who).get("/patient-case-files", params={"identifier": UHID}).status_code == 403, who
    assert app.as_(RAO).get("/patient-case-files", params={"identifier": "VXH/26/999999"}).json() == {"cases": []}  # not in the hospital system
    assert app.as_(RAO).get("/patient-case-files").status_code == 400
    ev = [e for e in org.read_audit(50) if e["kind"] == "patient_case_files_checked"]
    assert ev and all("VXH" not in str(e) and "999999" not in str(e) for e in ev)  # audited without the identifier
    # the Overview's variant: the other Case Files of this Case File's patient, for a person who may open it
    assert from_his(app, MEHTA, protocol="lung_nsclc", setting="non_metastatic", case_id="TB-DUP-B").status_code == 200
    r = app.as_(RAO).get("/patient-case-files", params={"case_id": "TB-DUP-A"})
    assert [x["case_id"] for x in r.json()["cases"]] == ["TB-DUP-B"]
    assert app.as_(RAVI).get("/patient-case-files", params={"case_id": "TB-DUP-A"}).status_code == 404


# ---- Ask to join -----------------------------------------------------------------------------------------------------------------------

def test_ask_to_join_a_consultant_becomes_a_team_member_without_the_owners_rights(app, people):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    assert app.as_(MEHTA).get("/cases/TB-DUP-A").status_code == 403
    r = app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-DUP-A", "note": "  second opinion   on systemic therapy "})
    assert r.status_code == 200 and r.json() == {"status": "pending", "case_id": "TB-DUP-A"}, r.text
    assert app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-DUP-A"}).json()["already"] is True
    ev = next(e for e in store.read_audit("TB-DUP-A") if e["kind"] == "join_requested")
    assert ev["by"] == MEHTA and ev["department"] == "medical_oncology" and ev["role"] == "consultant" and ev["how"] == "ask"
    told = [n for n in notify.for_roles(org.roles(RAO)) if n["kind"] == "join_request" and n["case_id"] == "TB-DUP-A"]
    assert len(told) == 1 and "Dr Mehta (synthetic) asks to join" in told[0]["title"]
    pend = app.as_(RAO).get("/cases/TB-DUP-A/team").json()["pending"]
    assert pend == [{**pend[0], "user": MEHTA, "role": "consultant", "department": "medical_oncology", "department_label": "Medical Oncology",
                     "note": "second opinion on systemic therapy"}]
    r = app.as_(RAO).post(f"/cases/TB-DUP-A/team/pending/{MEHTA}/approve", json={})
    assert r.status_code == 200, r.text
    assert [m["user"] for m in r.json()["team"]["members"]] == [MEHTA] and r.json()["team"]["residents"] == []
    assert "member_approved" in kinds("TB-DUP-A")
    # the member reads the whole Case File, never the owner's rights
    assert app.as_(MEHTA).get("/cases/TB-DUP-A").status_code == 200
    c = store.get_case("TB-DUP-A")
    rm = org.roles(MEHTA)
    assert access.scope(rm, c) == access.FULL and access.is_team_member(rm, c)
    for action in ("mark_ready", "approve_proposal", "manage_team", "set_urgency", "send_request", "waive", "upload_to_case"):
        assert not access.may(rm, action, c), action
    assert not access.may_list(rm, c)
    assert app.as_(MEHTA).post("/cases/TB-DUP-A/archive", json={"reason": "x"}).status_code == 403
    assert app.as_(MEHTA).post("/cases/TB-DUP-A/team/code").status_code == 403
    assert app.as_(MEHTA).put("/cases/TB-DUP-A/urgency", json={"level": 3}).status_code == 403
    assert app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-DUP-A"}).status_code == 409  # can open it now
    # the member leaves the team and loses access
    assert app.as_(MEHTA).delete(f"/cases/TB-DUP-A/team/residents/{MEHTA}").status_code == 200
    assert app.as_(MEHTA).get("/cases/TB-DUP-A").status_code == 403 and "member_removed" in kinds("TB-DUP-A")


def test_ask_to_join_a_resident_joins_as_a_resident_and_refusals(app, people, monkeypatch):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    r = app.as_(VIJAY).post("/case-join/ask", json={"case_id": "TB-DUP-A"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert app.as_(RAO).get("/cases/TB-DUP-A/team").json()["pending"][0]["role"] == "resident"
    r = app.as_(RAO).post(f"/cases/TB-DUP-A/team/pending/{VIJAY}/approve", json={})
    assert r.status_code == 200 and [x["user"] for x in r.json()["team"]["residents"]] == [VIJAY] and r.json()["team"]["members"] == []
    assert "resident_approved" in kinds("TB-DUP-A") and app.as_(VIJAY).get("/cases/TB-DUP-A").status_code == 200
    # a person who can open it already
    r = app.as_(ASHA).post("/case-join/ask", json={"case_id": "TB-DUP-A"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "can_open" and r.json()["detail"]["message"] == "You can open this Case File."
    # rejection works as with the code
    assert app.as_(RAVI).post("/case-join/ask", json={"case_id": "TB-DUP-A"}).status_code == 200
    assert app.as_(RAO).post(f"/cases/TB-DUP-A/team/pending/{RAVI}/reject", json={}).status_code == 200
    assert "join_rejected" in kinds("TB-DUP-A") and app.as_(RAVI).get("/cases/TB-DUP-A").status_code == 403
    # not a placed doctor, no such Case File, a protected or an archived one
    for who in (GUEST, ANIL, ROOT):
        assert app.as_(who).post("/case-join/ask", json={"case_id": "TB-DUP-A"}).status_code in (403, 409), who
    assert app.as_(VX).post("/case-join/ask", json={"case_id": "TB-DUP-A"}).status_code == 403
    assert app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-NONE"}).status_code == 404
    assert app.as_(MEHTA).post("/case-join/ask", json={}).status_code == 400
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-REAL-X"})
    make_case("TB-REAL-X")
    r = app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-REAL-X"})
    assert r.status_code == 404 and "join_requested" not in kinds("TB-REAL-X")
    make_case("TB-DUP-OLD", patient=dict(util.PATIENT))
    team.archive("TB-DUP-OLD", RAO, "duplicate (synthetic)")
    r = app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-DUP-OLD"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "archived" and r.json()["detail"]["message"].startswith("This Case File is archived")


def test_ask_to_join_is_rate_limited(app, people):
    make_case("TB-DUP-R")
    codes = [app.as_(MEHTA).post("/case-join/ask", json={"case_id": "TB-NONE"}).status_code for _ in range(6)]
    assert codes[:5] == [404] * 5 and codes[5] == 429


def test_patient_case_files_look_up_is_rate_limited_but_the_overview_form_is_not(app, people):
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    codes = [app.as_(RAO).get("/patient-case-files", params={"identifier": UHID}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    assert app.as_(RAO).get("/patient-case-files", params={"case_id": "TB-DUP-A"}).status_code == 200  # opening an Overview never uses it up


def test_listing_after_intake_refuses_the_same_cancer_but_not_the_file_itself(app, people):
    """The cancer of a Case File started from intake is chosen at listing (POST /cases/{id}/listing): the same rule applies there."""
    assert from_his(app, RAO, case_id="TB-DUP-A").status_code == 200
    pat = {"name": "SYNTHETIC, Test Patient", "mrn": "VXH/26/004201", "agesex": "46 Y / F"}
    assert app.as_(RAO).post("/cases", json={"case_id": "TB-DUP-N", "patient": pat}).status_code == 200  # no cancer yet: allowed
    r = app.as_(ANIL).post("/cases/TB-DUP-N/listing", json={"protocol": "breast", "setting": "early"})
    assert r.status_code == 409 and r.json()["code"] == "duplicate_case_file" and r.json()["existing"]["case_id"] == "TB-DUP-A", r.text
    assert store.get_case("TB-DUP-N")["listing"]["status"] != "listed" and not store.get_case("TB-DUP-N").get("protocol")
    assert [e["via"] for e in store.read_audit("TB-DUP-A") if e["kind"] == "duplicate_refused"] == ["listing"]
    r = app.as_(ANIL).post("/cases/TB-DUP-N/listing", json={"protocol": "generic", "setting": "as_recorded"})  # another cancer: allowed
    assert r.status_code == 200, r.text
    r = app.as_(ANIL).post("/cases/TB-DUP-A/listing", json={"protocol": "breast", "setting": "locally_advanced"})  # the file itself is never its own duplicate
    assert r.status_code == 200, r.text
