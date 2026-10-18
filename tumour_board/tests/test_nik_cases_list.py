"""GET /case-list (18 Oct 2026, new interface): one row per Case File the person may open, with the status word the home shows (archived,
decided, scheduled, ready, waiting on a department, needs you, draft), the urgency tag, what is left before the board, imaging present,
the last change; newest first; the same visibility as GET /cases. Synthetic Case Files in the conftest temporary data root; no model."""
import pytest

from tumour_board import access, board, store, team
from tumour_board.tests import util
from tumour_board.tests.test_nik_me import (ANIL, ASHA, AUDIT, MEHTA, NEXT_YEAR, RAO, RAVI, VIJAY, VX, Api, FakeAuth, api, auth,  # noqa: F401
                                            make_case, people)


def _gate(case_id, passed, open_ids=(), confirm_ids=()):
    st = store.get_state(case_id)
    reqs = [{"id": i, "label": i, "status": "missing"} for i in open_ids] + [{"id": i, "label": i, "status": "needs_confirmation"} for i in confirm_ids]
    reqs.append({"id": "clinical_history", "label": "Clinical history", "status": "satisfied"})
    st["gate"] = {"passed": passed, "requirements": reqs, "evaluated": store.now_iso(), "protocol": "breast"}
    store.save_state(case_id, st)


@pytest.fixture
def cases(people):
    """Nine synthetic Case Files of Breast Surgery (Dr Rao), one per status, created a minute apart (TB-L1 oldest)."""
    out = {}
    for i, key in enumerate(("archived", "decided", "scheduled", "ready", "waiting", "proposal", "gaps", "draft", "met"), start=1):
        cid = f"TB-L{i}"
        c = make_case(cid, created=f"2026-10-{10 + i:02d}T09:00:00")
        out[key] = cid
        _gate(cid, True)
    # archived
    team.archive(out["archived"], RAO, "duplicate (synthetic)")
    # decided: a board record after the listing
    st = store.get_state(out["decided"]); st["board_records"] = [{"id": "BR1", "recorded_at": "2026-12-01T10:00:00"}]; store.save_state(out["decided"], st)
    # scheduled: on the agenda of a planned session
    s = board.create(NEXT_YEAR, ANIL, case_ids=[out["scheduled"]])
    # ready: the owner's mark
    board.mark_ready(out["ready"], RAO, ready=True)
    # waiting on a department: a sent request is open
    st = store.get_state(out["waiting"])
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "breast_imaging", "label": "Mammogram", "department": "Radiology", "department_id": "radiology",
                      "status": "pending", "created": store.now_iso(), "due": NEXT_YEAR, "history": [], "sent": {"by": RAO, "at": store.now_iso(), "count": 1}}]
    store.save_state(out["waiting"], st)
    _gate(out["waiting"], False, open_ids=["breast_imaging"])
    # a resident's proposal waits for the consultant
    from tumour_board import proposals
    proposals.propose(out["proposal"], "urgency", {"level": 3}, "", ASHA, people[ASHA])
    # required records open, nobody asked
    _gate(out["gaps"], False, open_ids=["histopathology", "receptor_status"])
    # records still being read
    store.save_doc(out["draft"], util.make_doc("D1", "histopathology", state="reading"))
    # every check met: a mammogram report present (imaging) and an urgency tag
    store.save_doc(out["met"], util.make_doc("D2", "mammogram", state="ready"))
    team.set_urgency(out["met"], 4, RAO)
    return out | {"session": s["id"]}


def by_id(rows):
    return {x["case_id"]: x for x in rows}


def test_case_list_statuses_for_the_owner(api, cases):
    r = api.as_(RAO).get("/case-list")
    assert r.status_code == 200, r.text
    rows = by_id(r.json()["cases"])
    assert cases["archived"] not in rows  # archived Case Files only with status=archived
    want = {"decided": "decided", "scheduled": "scheduled", "ready": "ready", "waiting": "waiting_department", "proposal": "needs_me", "gaps": "needs_me",
            "draft": "draft", "met": "needs_me"}
    assert {k: rows[cases[k]]["status"]["key"] for k in want} == want
    assert rows[cases["waiting"]]["status"]["label"] == "Waiting on Radiology"
    assert rows[cases["proposal"]]["status"]["label"] == "Needs you" and "proposal" in rows[cases["proposal"]]["status"]["detail"]
    assert "mark it ready" in rows[cases["met"]]["status"]["detail"]
    assert rows[cases["scheduled"]]["status"]["label"] == f"Scheduled {NEXT_YEAR}" and rows[cases["scheduled"]]["meeting_id"] == cases["session"]
    assert rows[cases["scheduled"]]["board_date"] == NEXT_YEAR
    assert rows[cases["gaps"]]["left_before_board"] == 2 and rows[cases["met"]]["left_before_board"] == 0
    assert rows[cases["met"]]["imaging_present"] is True and rows[cases["gaps"]]["imaging_present"] is False
    assert rows[cases["met"]]["urgency"]["level"] == 4 and rows[cases["met"]]["urgency"]["set_by_name"] == "Dr Rao (synthetic)"
    assert rows[cases["proposal"]]["urgency"]["level"] is None and rows[cases["proposal"]]["urgency"]["proposed"]["level"] == 3
    assert rows[cases["gaps"]]["urgency"] is None
    x = rows[cases["met"]]
    assert x["patient"] == {"name": util.PATIENT["name"], "agesex": util.PATIENT["agesex"], "uhid": util.PATIENT["mrn"]}
    assert x["owner"] == {"department": "breast_surgery", "department_label": "Breast Surgery", "doctor": RAO, "doctor_name": "Dr Rao (synthetic)"}
    assert x["protocol"] == "breast" and x["protocol_label"] and x["last_change"] and x["mine"] is True
    ids = [c["case_id"] for c in r.json()["cases"]]
    assert ids == sorted(ids, key=lambda cid: store.get_case(cid)["created"], reverse=True)  # newest first
    f = r.json()["filters"]
    assert {"id": "breast_surgery", "label": "Breast Surgery"} in f["departments"] and {s["key"] for s in f["statuses"]} >= {"needs_me", "archived", "draft"}


def test_archived_status_filter_and_simple_filters(api, cases):
    r = api.as_(RAO).get("/case-list?status=archived").json()["cases"]
    assert [x["case_id"] for x in r] == [cases["archived"]] and r[0]["status"]["detail"] == "duplicate (synthetic)"
    r = api.as_(RAO).get("/case-list?status=needs_me,draft").json()["cases"]
    assert {x["case_id"] for x in r} == {cases["proposal"], cases["gaps"], cases["met"], cases["draft"]}
    assert [x["case_id"] for x in api.get("/case-list?urgency=4").json()["cases"]] == [cases["met"]]
    assert [x["case_id"] for x in api.get("/case-list?imaging=1").json()["cases"]] == [cases["met"]]
    assert len(api.get("/case-list?q=synthetic%20test").json()["cases"]) == 8
    assert api.get("/case-list?q=nobody-like-this").json()["cases"] == []
    assert len(api.get("/case-list?department=Breast%20Surgery").json()["cases"]) == 8
    assert api.get("/case-list?department=medical_oncology").json()["cases"] == []
    assert len(api.get(f"/case-list?owner={RAO}&mine=1").json()["cases"]) == 8
    assert [x["case_id"] for x in api.get(f"/case-list?board_from={NEXT_YEAR}&board_to={NEXT_YEAR}").json()["cases"]] == [cases["scheduled"]]


def test_case_list_follows_get_cases_visibility(api, cases, people):
    assert len(api.as_(ASHA).get("/case-list").json()["cases"]) == 8  # the owning department's resident
    rows = by_id(api.as_(ASHA).get("/case-list").json()["cases"])
    assert rows[cases["gaps"]]["status"]["label"] == "Needs you"  # the resident fills it in
    assert api.as_(MEHTA).get("/case-list").json()["cases"] == []  # another treating department
    assert api.as_(VIJAY).get("/case-list").json()["cases"] == []  # another department's resident, not on a team
    rows = api.as_(RAVI).get("/case-list").json()["cases"]  # Radiology sees the Case File it was asked about only
    assert [x["case_id"] for x in rows] == [cases["waiting"]] and rows[0]["scope"] == access.REQUESTS
    rows = by_id(api.as_(ANIL).get("/case-list").json()["cases"])
    assert len(rows) == 8 and rows[cases["gaps"]]["status"]["label"] == "Needs the treating team"
    assert api.as_(AUDIT).get("/case-list").status_code == 403
    assert api.as_(VX).get("/case-list").json()["cases"] == []  # no clinical scope outside a break-glass window
    access.open_break_glass(VX, cases["gaps"], "support (synthetic)")
    assert [x["case_id"] for x in api.as_(VX).get("/case-list").json()["cases"]] == [cases["gaps"]]
