"""The Hospital console API (admin consoles Phase B, 16 Nov 2026, DESIGN 5.3, API_FIELDS.md): GET /hospital/overview and
/hospital/departments. Who may (the hospital admin, a Vaidyx admin in the hospital it acts in; never a doctor), the exact answer shapes,
the counts, the attention items with their links, recent events without any clinical event, and no patient data. Synthetic data only."""
import copy, json, shutil
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tumour_board import config, hospitals, org, store
from tumour_board.tests.conftest import FIXTURES
from tumour_board.tests.test_platform_api import FakeAuth, make_app, call, NEW

PATIENT, UHID = "SYNTHETIC, Hospital Consolename", "SYN-HOSP-552211"


@pytest.fixture
def world(data_root, monkeypatch):
    monkeypatch.setenv("TB_SCHEDULER", "0")
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["hospital"]["name"] = "Vaidyx Demo Hospital"
    o["admins"] = ["root"]
    end = (date.today() + timedelta(days=10)).isoformat()
    o["users"] = {"root": {"display_name": "Hospital IT"},
                  "doc": {"display_name": "Dr Anil", "departments": {"radiology": "member"}},
                  "head": {"display_name": "Dr Shanthi", "departments": {"radiology": "head"}},
                  "res": {"display_name": "Kiran Shetty", "departments": {"radiology": "resident"}, "end_date": end},
                  "off": {"display_name": "Old Login", "departments": {"pathology": "member"}, "disabled": True},
                  "deptadm": {"display_name": "Suresh Babu", "admin_of": ["radiology"]},
                  "aud": {"display_name": "Meera Iyer", "auditor": True}}
    org.save(o, by="test")
    for cid in ("TB-001", "TB-002", "TB-003"):
        shutil.copytree(FIXTURES / "cases" / cid, config.CASES_DIR / cid)
    c = store.get_case("TB-001"); c["patient"]["name"] = PATIENT; c["patient"]["mrn"] = UHID; store.save_case(c)
    p = config.CASES_DIR / "TB-002" / "state.json"
    st = json.loads(p.read_text()); st["board_records"] = [{"recorded_at": "2026-11-01T10:00:00", "decision_text": "synthetic"}]
    p.write_text(json.dumps(st))
    c = store.get_case("TB-003"); c["archived"] = {"at": "2026-11-02T10:00:00", "by": "doc", "reason": "test"}; store.save_case(c)
    store._docs_cache.clear()
    auth = FakeAuth()
    auth.users.update({u: {} for u in ("head", "res", "off", "deptadm", "aud")})
    auth.must.add("res")
    with TestClient(make_app(auth)) as tc:
        yield tc, auth


def test_who_may(world):
    tc, _ = world
    for path in ("/hospital/overview", "/hospital/departments"):
        assert call(tc, "root", "GET", path).status_code == 200
        assert call(tc, "vx", "GET", path).status_code == 200
        for who in ("doc", "deptadm", "aud"):
            r = call(tc, who, "GET", path)
            assert r.status_code == 403 and r.json()["detail"] == {"message": "Only the hospital admin opens the Hospital console.", "code": "forbidden"}


OVERVIEW_KEYS = {"hospital", "people", "case_files", "meetings", "requests", "setup", "his", "attention", "recent"}
PEOPLE_KEYS = {"doctors", "heads", "residents", "coordinators", "dept_admins", "hospital_admins", "auditors", "guests", "disabled", "never_signed_in"}


def test_overview_shape_and_counts(world):
    tc, _ = world
    org.audit("break_glass", "vx", case_id="TB-001", patient=PATIENT, reason="synthetic test")  # clinical: never in recent
    org.audit("pubmed_asked", "doc", question="synthetic")
    d = call(tc, "root", "GET", "/hospital/overview").json()
    assert set(d) == OVERVIEW_KEYS
    assert {"id", "name", "city", "state", "status", "level"} <= set(d["hospital"])
    assert d["hospital"]["id"] == "default" and d["hospital"]["name"] == "Vaidyx Demo Hospital" and d["hospital"]["status"] == "active"
    assert set(d["people"]) == PEOPLE_KEYS
    assert d["people"] == {"doctors": 2, "heads": 1, "residents": 1, "coordinators": 0, "dept_admins": 1, "hospital_admins": 1, "auditors": 1,
                           "guests": 0, "disabled": 1, "never_signed_in": 1}
    assert set(d["case_files"]) == {"by_status", "total"}
    assert set(d["case_files"]["by_status"]) == {"draft", "needs_team", "waiting_department", "ready", "scheduled", "decided"}
    assert d["case_files"]["total"] == 2 and d["case_files"]["by_status"]["decided"] == 1  # the archived one is left out
    assert set(d["meetings"]) == {"next_7_days", "upcoming"} and d["meetings"]["next_7_days"] == 0
    assert d["requests"] == {"open": 0}
    assert set(d["setup"]) == {"steps", "done", "total"} and d["setup"]["total"] == 5 and len(d["setup"]["steps"]) == 5
    assert {"state", "url_set", "tested_at", "ok"} <= set(d["his"])
    kinds = {a["kind"]: a for a in d["attention"]}
    for a in d["attention"]:
        assert set(a) == {"kind", "text", "link"} and a["link"].startswith("/hospital")
    assert kinds["no_coordinator"]["link"] == "/hospital/people?role=coordinator"
    assert kinds["resident_ending"]["text"] == "Kiran Shetty's rotation ends within 30 days" and kinds["resident_ending"]["link"] == "/hospital/people?role=resident"
    assert kinds["never_signed_in"]["text"] == "1 person has not signed in yet" and kinds["never_signed_in"]["link"] == "/hospital/people?role=not_signed_in"
    assert kinds["disabled_logins"]["text"] == "1 login is disabled" and kinds["disabled_logins"]["link"] == "/hospital/people?role=disabled"
    assert kinds["setup_unfinished"]["link"] == "/hospital/setup"
    assert "department_no_head" in kinds  # pathology has a (disabled) doctor and no head
    assert d["recent"] and all({"ts", "by", "kind", "text"} <= set(e) for e in d["recent"])
    assert not {"break_glass", "pubmed_asked", "org_saved"} & {e["kind"] for e in d["recent"]}
    assert any(e["text"].startswith("Kiran Shetty added (Resident, ") for e in d["recent"])
    text = json.dumps(d)
    assert PATIENT not in text and UHID not in text and "SYN-200417" not in text and "Lakshmi" not in text


def test_meetings_and_requests_are_counted(world):
    tc, _ = world
    from tumour_board import board
    soon = (date.today() + timedelta(days=2)).isoformat()
    s = board.new_session(soon, "mdt", title="Weekly Tumour Board")
    if s is None:
        pytest.skip("board.create_session not available")
    p = config.CASES_DIR / "TB-001" / "state.json"
    st = json.loads(p.read_text())
    st["actions"] = [{"source": "pre_authorization", "status": "pending", "department": "Radiology"},
                     {"source": "pre_authorization", "status": "suggested"}, {"source": "board", "status": "completed"}]
    p.write_text(json.dumps(st))
    d = call(tc, "root", "GET", "/hospital/overview").json()
    assert d["meetings"]["next_7_days"] == 1 and d["meetings"]["upcoming"][0]["title"] == "Weekly Tumour Board"
    assert d["meetings"]["upcoming"][0]["date"] == soon and {"id", "title", "date"} <= set(d["meetings"]["upcoming"][0])
    assert d["requests"]["open"] == 1 and d["case_files"]["by_status"]["waiting_department"] == 1


def test_departments(world):
    tc, _ = world
    deps = {x["id"]: x for x in call(tc, "root", "GET", "/hospital/departments").json()["departments"]}
    assert len(deps) == len(org.DEFAULT_DEPARTMENTS)
    r = deps["radiology"]
    assert set(r) == {"id", "name", "group", "enabled", "heads", "people", "residents", "email", "phone", "receives_requests"}
    assert r["heads"] == [{"username": "head", "display_name": "Dr Shanthi"}] and r["people"] == 2 and r["residents"] == 1
    assert deps["pathology"]["heads"] == [] and deps["pathology"]["people"] == 1


def test_a_vaidyx_admin_acting_in_a_new_hospital_and_its_own_admin(world):
    tc, auth = world
    hid = call(tc, "vx", "POST", "/platform/hospitals", NEW).json()["hospital"]["id"]
    d = call(tc, "vx", "GET", "/hospital/overview", **{"X-TB-Hospital": hid}).json()
    assert d["hospital"]["id"] == hid and d["hospital"]["name"] == "Lotus Cancer Centre" and d["case_files"]["total"] == 0
    assert d["people"]["hospital_admins"] == 1 and d["his"]["state"] == "not_set"
    assert any(e["kind"] == "hospital_created" and e["text"] == "Hospital added: Lotus Cancer Centre" for e in d["recent"])
    auth.must.discard("it.admin@lotus.example")
    d2 = call(tc, "it.admin@lotus.example", "GET", "/hospital/overview").json()
    assert d2["hospital"]["id"] == hid and d2["people"] == d["people"] | {"never_signed_in": 0}
    deps = call(tc, "it.admin@lotus.example", "GET", "/hospital/departments").json()["departments"]
    assert all(x["people"] == 0 and x["heads"] == [] for x in deps)  # nothing of the default hospital
    # the default hospital's admin never sees Lotus, whatever header it sends
    assert call(tc, "root", "GET", "/hospital/overview", **{"X-TB-Hospital": hid}).json()["hospital"]["id"] == "default"
    assert hospitals.hospital_of("root") == "default"
