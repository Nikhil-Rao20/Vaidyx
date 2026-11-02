"""Night-v3 item 1.3: a Case File owned by another department appears in a department's list only as linked ("Owned by Haematology",
read-only) and is never counted as its own or "Mine". GET /case-list carries `relation` on every row; the home's treating counts leave a
linked-only file out of mine and participating. Synthetic Case Files in the conftest temporary data root; no model."""
import pytest

from tumour_board import home, org, store
from tumour_board.api import cases_list
from tumour_board.tests.test_nik_me import ANIL, ASHA, MEHTA, RAO, Api, FakeAuth, api, auth, make_case, people  # noqa: F401

HAEM = "dr.iyer@hospital.example"  # consultant, Haematology (treating)


@pytest.fixture
def haem(people):
    o = org.load()
    o["users"][HAEM] = {"departments": {"haematology": "member"}, "display_name": "Dr Iyer (synthetic)"}
    org.save(o, by="test")
    people[HAEM] = org.roles(HAEM)
    return people


@pytest.fixture
def files(haem, auth):
    """Breast Surgery's file B (Dr Rao) and Haematology's file H of the same patient, linked both ways; H was created by Dr Rao (before a
    referral, say), so the creator rule must not make it "mine". P: a Haematology file Breast Surgery takes part in (also linked to B)."""
    auth.users[HAEM] = {"is_admin": False, "pw": "old-" + HAEM, "privileges": {"can_use_bash": False}}  # the fake login system knows Dr Iyer
    make_case("TB-LK-B", created="2026-10-20T09:00:00", linked_cases=[{"case_id": "TB-LK-H", "protocol": "", "department": "haematology"}])
    make_case("TB-LK-H", owner="haematology", protocol="", cancer_name="Chronic myeloid leukaemia", created="2026-10-21T09:00:00",
              linked_cases=[{"case_id": "TB-LK-B", "protocol": "breast", "department": "breast_surgery"}])
    make_case("TB-LK-P", owner="haematology", protocol="", created="2026-10-22T09:00:00", participants=[{"department": "breast_surgery"}],
              linked_cases=[{"case_id": "TB-LK-B", "protocol": "breast", "department": "breast_surgery"}])
    return haem


def by_id(rows):
    return {x["case_id"]: x for x in rows}


def test_breast_consultant_sees_the_haematology_file_only_as_linked(files):
    r = files[RAO]
    rows = {c["case_id"]: cases_list.row(c, r, {}, {}) for c in store.list_cases()}
    h = rows["TB-LK-H"]
    assert h["relation"] == "linked" and h["linked_only"] is True and h["read_only"] is True
    assert h["owned_by"] == {"department": "haematology", "label": "Haematology"}
    assert h["mine"] is False  # never "mine", even though Dr Rao created it
    assert h["owner"]["department_label"] == "Haematology"  # the owner text stays
    b = rows["TB-LK-B"]
    assert b["relation"] == "owner" and b["mine"] is True and "linked_only" not in b and "read_only" not in b
    p = rows["TB-LK-P"]
    assert p["relation"] == "participant" and p["mine"] is True and "linked_only" not in p  # taking part wins over the link; "mine" as before: Dr Rao created it


def test_case_list_counts_and_mine_leave_the_linked_file_out(api, files):
    body = api.as_(RAO).get("/case-list").json()
    rows = by_id(body["cases"])
    assert set(rows) == {"TB-LK-B", "TB-LK-H", "TB-LK-P"}  # still listed, to open read only
    assert body["total"] == 2 and body["linked"] == 1
    mine = [x["case_id"] for x in api.as_(RAO).get("/case-list?mine=1").json()["cases"]]
    assert set(mine) == {"TB-LK-B", "TB-LK-P"}  # the file Dr Rao created stays "mine" (as before); the linked one never


def test_the_owning_department_sees_its_own_file_as_owner(api, files):
    rows = by_id(api.as_(HAEM).get("/case-list").json()["cases"])
    assert rows["TB-LK-H"]["relation"] == "owner" and rows["TB-LK-H"]["mine"] is True and "linked_only" not in rows["TB-LK-H"]
    assert rows["TB-LK-B"]["relation"] == "linked" and rows["TB-LK-B"]["owned_by"]["label"] == "Breast Surgery" and rows["TB-LK-B"]["mine"] is False


def test_coordinator_resident_and_others(api, files):
    rows = by_id(api.as_(ANIL).get("/case-list").json()["cases"])
    assert {x["relation"] for x in rows.values()} == {"coordinator"} and not any(x.get("linked_only") for x in rows.values())
    assert api.as_(ANIL).get("/case-list").json()["linked"] == 0
    rows = by_id(api.as_(ASHA).get("/case-list").json()["cases"])  # the resident of Breast Surgery reads its department's file only
    assert set(rows) == {"TB-LK-B"} and rows["TB-LK-B"]["relation"] == "team" and rows["TB-LK-B"]["mine"] is True
    assert api.as_(MEHTA).get("/case-list").json()["cases"] == []  # Medical Oncology: no link, no access


def test_home_treating_counts_leave_the_linked_file_out(files):
    t = home.treating(files[RAO])
    rel = {x["case_id"]: x["relation"] for x in t["cases"]}
    assert rel == {"TB-LK-B": "owner", "TB-LK-P": "participant", "TB-LK-H": "linked"}
    assert t["counts"]["mine"] == 1 and t["counts"]["participating"] == 1 and t["counts"]["linked"] == 1
    assert [x["case_id"] for x in t["cases"]][-1] == "TB-LK-H"  # listed last
    assert "suggested_unsent" not in next(x for x in t["cases"] if x["case_id"] == "TB-LK-H")
    t = home.treating(files[HAEM])
    rel = {x["case_id"]: x["relation"] for x in t["cases"]}
    assert rel == {"TB-LK-H": "owner", "TB-LK-P": "owner", "TB-LK-B": "linked"} and t["counts"]["mine"] == 2 and t["counts"]["participating"] == 0
