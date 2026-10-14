"""A home per role (V2 item 7.1): the sections each login holds, what each section sums up, and the root admin's first set-up
(the PM-JAY empanelled question of plan section 11, answered once and audited). Synthetic names only."""
import copy
import datetime as dt

import pytest

from tumour_board import board, home, notify, org, referral, store
from tumour_board.tests import util

TODAY = dt.date.today()
D_NEXT = (TODAY + dt.timedelta(days=5)).isoformat()
D_LATER = (TODAY + dt.timedelta(days=12)).isoformat()


@pytest.fixture
def people():
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {
        "priya": {"departments": {"breast_surgery": "member"}, "display_name": "Dr Priya (synthetic)"},   # treating doctor
        "ravi": {"departments": {"radiology": "member"}},                                             # supporting doctor
        "meena": {"departments": {"radiology": "head"}, "admin_of": ["radiology"]},                   # a head who also administers her department
        "anil": {"coordinator": True},                                                                 # MDT Coordinator
        "deepak": {"admin_of": ["radiology", "pathology"]},                                            # department admin only
        "suresh": {"departments": {"medical_oncology": "member"}},                                     # another treating doctor
        "gone": {"departments": {"radiology": "member"}, "disabled": True},
    }
    o["admins"] = ["tbroot"]
    org.save(o, by="test")
    return {k: org.roles(k) for k in ("priya", "ravi", "meena", "anil", "deepak", "suresh", "gone", "tbroot", "stranger")} | {"admin": org.roles("vx", vaidyx_admin=True)}


def _action(aid, dept, due, status="pending", **kw):
    return {"id": aid, "source": "pre_authorization", "requirement": "req_" + aid, "label": "Label " + aid, "department": dept, "what": "Missing " + aid,
            "status": status, "created": "2026-10-05T10:00:00", "due": due, "completed": None, "history": [], **kw}


@pytest.fixture
def cases(people):
    """Three Case Files: breast (owned by Breast Surgery, marked ready, a request to Radiology sent, one suggested), lung (Medical Oncology,
    referred to Breast Surgery), and one asked of Radiology only; plus a planned session."""
    a = store.create_case("TB-H-A", {**util.PATIENT, "name": "SYNTHETIC, Anitha Reddy", "mrn": "VXH/26/900001"}, "breast", board_date=D_NEXT, created_by="priya")
    a["department"] = "breast_surgery"; store.save_case(a)
    st = store.get_state("TB-H-A")
    st["actions"] = [_action("A1", "Radiology", D_LATER, sent={"by": "priya", "at": "2026-10-06T10:00:00", "count": 1}, level_label="Level 1 · Case File"),
                     _action("A2", "Pathology", D_LATER, status="suggested")]
    st["gate"] = {"passed": False, "readiness": 60}
    store.save_state("TB-H-A", st)
    board.mark_ready("TB-H-A", "priya", True, "Summary to follow")
    b = store.create_case("TB-H-B", {**util.PATIENT, "name": "SYNTHETIC, Ramesh Babu", "mrn": "VXH/26/900002"}, "lung_nsclc", board_date=D_NEXT, created_by="suresh")
    b["department"] = "medical_oncology"; store.save_case(b)
    referral.request("TB-H-B", "breast_surgery", "Breast primary suspected on the biopsy", "suresh")
    c = store.create_case("TB-H-C", {**util.PATIENT, "name": "SYNTHETIC, Kavitha Nair", "mrn": "VXH/26/900003"}, "cervix", board_date=D_LATER, created_by="suresh")
    c["department"] = "gynaecologic_oncology"; store.save_case(c)
    st = store.get_state("TB-H-C")
    st["actions"] = [_action("C1", "Radiology", (TODAY - dt.timedelta(days=2)).isoformat(), sent={"by": "suresh", "at": "2026-10-06T10:00:00", "count": 1})]
    store.save_state("TB-H-C", st)
    s = board.create(D_NEXT, "anil", case_ids=["TB-H-A"])
    return {"session": s["id"]}


# ---- sections per role ------------------------------------------------------------------------------------------------------

def test_sections_follow_the_roles(people):
    assert home.sections_for(people["priya"]) == ["treating"]
    assert home.sections_for(people["ravi"]) == ["supporting"]
    assert home.sections_for(people["meena"]) == ["supporting", "dept_admin"]  # the clinical section first
    assert home.sections_for(people["anil"]) == ["coordinator"]
    assert home.sections_for(people["deepak"]) == ["dept_admin"]
    assert home.sections_for(people["tbroot"]) == ["root_admin"]
    assert home.sections_for(people["admin"]) == ["treating", "coordinator", "root_admin"]
    assert home.sections_for(people["gone"]) == [] and home.sections_for(people["stranger"]) == []
    assert home.sections_for(None) == [] and home.sections_for({}) == []


def test_build_carries_only_the_sections_held(people, cases):
    h = home.build(people["priya"])
    assert h["sections"] == ["treating"] and h["primary"] == "treating" and "treating" in h
    assert not any(k in h for k in ("supporting", "coordinator", "dept_admin", "root_admin"))
    assert h["user"] == "priya" and h["display_name"] == "Dr Priya (synthetic)" and h["today"] == TODAY.isoformat()
    assert [d["id"] for d in h["departments"]] == ["breast_surgery"]
    none = home.build(people["stranger"])
    assert none["sections"] == [] and none["primary"] == "none" and none["notifications"] == [] and none["unread"] == 0


# ---- treating doctor ----------------------------------------------------------------------------------------------------------

def test_treating_home_lists_the_departments_case_files_owned_first(people, cases):
    t = home.build(people["priya"])["treating"]
    ids = [c["case_id"] for c in t["cases"]]
    assert ids[0] == "TB-H-A" and "TB-H-B" in ids and "TB-H-C" not in ids  # the referred one is open to the receiving department; the cervix one is not
    a = t["cases"][0]
    assert a["relation"] == "owner" and a["owner_name"] == "Breast Surgery" and a["ready"]["by"] == "priya" and a["ready"]["note"] == "Summary to follow"
    assert a["uhid"] == "VXH/26/900001" and a["board_date"] == D_NEXT and a["readiness"] == 60 and a["gate_passed"] is False
    assert a["suggested_unsent"] == 1 and a["open_actions"] == 2
    b = next(c for c in t["cases"] if c["case_id"] == "TB-H-B")
    assert b["relation"] == "referred" and b["referral"] == "Breast Surgery"
    assert t["counts"] == {"visible": 2, "mine": 1, "participating": 1, "asked": 0, "awaiting_listing": 0, "gate_passed": 0, "ready_marked": 1,
                           "referral_waiting": 0, "suggested_unsent": 1}
    assert t["referrals_to_answer"] == 1 and t["referrals"][0]["case_id"] == "TB-H-B" and t["referrals"][0]["can_answer"] is True
    assert t["can_create"] is True and [d["id"] for d in t["departments"]] == ["breast_surgery"]
    assert t["inbox"] == {"departments": [{"id": "breast_surgery", "name": "Breast Surgery", "open": 0, "overdue": 0}], "open": 0, "overdue": 0}  # no request is addressed to Breast Surgery


def test_treating_home_of_the_referring_department(people, cases):
    t = home.build(people["suresh"])["treating"]
    b = next(c for c in t["cases"] if c["case_id"] == "TB-H-B")
    assert b["relation"] == "owner" and b["referral"] == "Breast Surgery"
    assert t["counts"]["referral_waiting"] == 1 and t["referrals_to_answer"] == 0
    assert t["referrals"][0]["direction"] == "from" and t["referrals"][0]["can_withdraw"] is True


def test_treating_home_shows_the_suggested_requests_only_for_owned_case_files(people, cases):
    t = home.build(people["priya"])["treating"]
    assert "suggested_unsent" not in next(c for c in t["cases"] if c["case_id"] == "TB-H-B")


# ---- supporting doctor ---------------------------------------------------------------------------------------------------------

def test_supporting_home_is_the_inbox_of_the_supporting_departments(people, cases):
    s = home.build(people["ravi"])["supporting"]
    assert [d["id"] for d in s["departments"]] == ["radiology"]
    d = s["departments"][0]
    assert d["open"] == 2 and d["overdue"] == 1 and s["open"] == 2 and s["overdue"] == 1
    assert [q["case_id"] for q in d["requests"]] == ["TB-H-C", "TB-H-A"]  # the overdue one first
    assert d["requests"][0]["overdue"] is True and d["requests"][0]["uhid"] == "VXH/26/900003"
    assert d["acknowledged"] == 0 and d["done"] == 0 and d["more"] == 0
    assert "A2" not in [q["action_id"] for q in d["requests"]]  # a suggested request nobody sent is not in any inbox


def test_supporting_home_leaves_out_the_treating_rows_of_a_mixed_login(people, cases):
    o = org.load(); o["users"]["ravi"]["departments"]["pulmonology"] = "member"; org.save(o, by="test")
    r = org.roles("ravi")
    assert home.sections_for(r) == ["treating", "supporting"]
    h = home.build(r)
    assert [d["id"] for d in h["supporting"]["departments"]] == ["radiology"]
    assert [d["id"] for d in h["treating"]["departments"]] == ["pulmonology"]


# ---- MDT Coordinator ----------------------------------------------------------------------------------------------------------

def test_coordinator_home_has_the_next_board_its_readiness_and_the_sessions(people, cases):
    c = home.build(people["anil"])["coordinator"]
    assert c["next_board_date"] == D_NEXT and c["today"] == TODAY.isoformat()
    ag = c["agenda"]
    assert ag["board_date"] == D_NEXT and {x["case_id"] for x in ag["cases"]} == {"TB-H-A", "TB-H-B"} and ag["days_to_board"] == 5
    assert ag["requests_open"] == 2 and ag["requests_unsent"] == 1  # TB-H-A's sent request and the suggested one
    assert c["sessions"]["planned"] == 1 and c["sessions"]["open"][0]["id"] == cases["session"] and c["sessions"]["closed_n"] == 0
    assert c["ready_marked"] == 1 and c["listed_total"] == 3 and c["awaiting_listing"] == 0 and c["can_manage"] is True


def test_coordinator_home_without_a_listed_case_file(people):
    c = home.build(people["anil"])["coordinator"]
    assert c["next_board_date"] == "" and c["agenda"] is None and c["sessions"]["open"] == [] and c["ready_marked"] == 0


def test_next_board_date_prefers_the_coming_one_then_the_latest_past():
    today = "2026-10-14"
    assert home._next_board_date([{"board_date": "2026-10-01"}, {"board_date": "2026-10-20"}, {"board_date": "2026-10-16"}], today) == "2026-10-16"
    assert home._next_board_date([{"board_date": "2026-10-01"}, {"board_date": "2026-09-20"}], today) == "2026-10-01"
    assert home._next_board_date([{"board_date": ""}, {}], today) == ""


# ---- department admin ---------------------------------------------------------------------------------------------------------

def test_dept_admin_home_lists_its_doctors(people, cases):
    d = home.build(people["deepak"])["dept_admin"]
    assert [x["id"] for x in d["departments"]] == ["pathology", "radiology"] or [x["id"] for x in d["departments"]] == ["radiology", "pathology"]
    rad = next(x for x in d["departments"] if x["id"] == "radiology")
    assert rad["doctors"] == 3 and rad["heads"] == 1 and rad["disabled"] == 1 and rad["admins"] == 2 and rad["group"] == "supporting"
    assert {x["username"] for x in rad["list"]} == {"ravi", "meena", "gone"} and next(x for x in rad["list"] if x["username"] == "gone")["disabled"] is True
    assert rad["no_login"] == 0  # no auth manager given: unknown, never counted as missing
    path = next(x for x in d["departments"] if x["id"] == "pathology")
    assert path["doctors"] == 0 and path["list"] == []


def test_dept_admin_home_counts_missing_logins_with_the_auth_manager(people):
    class Mgr:  # the main app's AuthManager keeps its accounts in `users`; is_admin answers False for everyone here
        users = {"ravi": {}, "meena": {}}

        def is_admin(self, u):
            return False
    rad = home.build(people["deepak"], mgr=Mgr())["dept_admin"]["departments"]
    rad = next(x for x in rad if x["id"] == "radiology")
    assert rad["no_login"] == 1 and next(x for x in rad["list"] if x["username"] == "gone")["account"] is False


# ---- root admin and the first set-up -------------------------------------------------------------------------------------------

def test_root_admin_home_sums_up_the_organisation(people, cases):
    r = home.build(people["tbroot"])["root_admin"]
    assert r["hospital"]["pmjay_empanelled"] is True and r["hospital"]["level"] == "essential" and r["setup_needed"] is True and r["first_setup"] is None
    assert r["departments"]["treating"] == 22 and r["departments"]["supporting"] == 8 and r["departments"]["placeholder_emails"] == 30
    assert r["accounts"] == {"placed": 7, "doctors": 5, "dept_admins": 2, "coordinators": 1, "root_admins": 1, "disabled": 1, "no_login": 0}
    assert r["board_heads"] == ["Radiology", "Medical Oncology", "Surgical Oncology", "Pathology"] and r["routes_overridden"] == 0
    assert set(r["his"]) == {"enabled", "label", "kind", "url", "pacs_url"} and "token" not in str(r["his"])


def test_first_setup_answers_once_and_is_audited(people):
    h = org.first_setup("tbroot", False, name="Vaidyx Demo Hospital (SYNTHETIC)", level="optimal")
    assert h["pmjay_empanelled"] is False and h["name"] == "Vaidyx Demo Hospital (SYNTHETIC)" and h["level"] == "optimal"
    assert h["first_setup"]["by"] == "tbroot" and h["first_setup"]["at"][:10] == TODAY.isoformat()
    assert org.hospital()["first_setup"]["by"] == "tbroot" and home.setup_needed() is False
    r = home.build(people["tbroot"])["root_admin"]
    assert r["setup_needed"] is False and r["first_setup"]["by"] == "tbroot" and r["hospital"]["pmjay_empanelled"] is False
    kinds = [e["kind"] for e in org.read_audit(50)]
    assert "first_setup" in kinds
    ev = next(e for e in org.read_audit(50) if e["kind"] == "first_setup")
    assert ev["by"] == "tbroot" and ev["pmjay_empanelled"] is False and ev["level"] == "optimal"
    with pytest.raises(org.SetupDone):
        org.first_setup("tbroot", True)
    assert org.hospital()["pmjay_empanelled"] is False  # the refused second answer changed nothing


def test_first_setup_needs_a_yes_or_no_and_a_known_level(people):
    with pytest.raises(ValueError):
        org.first_setup("tbroot", "yes")
    with pytest.raises(ValueError):
        org.first_setup("tbroot", None)
    with pytest.raises(ValueError):
        org.first_setup("tbroot", True, level="tertiary")
    assert home.setup_needed() is True


def test_first_setup_keeps_the_other_hospital_settings(people):
    o = org.load(); o["hospital"]["fetch_window_months"] = 24; o["hospital"]["board_attendance"] = ["dermatology"]; org.save(o, by="test")
    h = org.first_setup("tbroot", True)
    assert h["fetch_window_months"] == 24 and h["board_attendance"] == ["dermatology"] and h["name"] == "" and h["level"] == "essential"


def test_validate_keeps_or_clears_the_stamp():
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["hospital"] = {**o["hospital"], "first_setup": {"at": "2026-10-14T10:00:00", "by": "tbroot", "extra": 1}}
    assert org.validate(o)["hospital"]["first_setup"] == {"at": "2026-10-14T10:00:00", "by": "tbroot"}
    o["hospital"]["first_setup"] = None
    assert "first_setup" not in org.validate(o)["hospital"]
    o["hospital"]["first_setup"] = "done"
    with pytest.raises(ValueError):
        org.validate(o)


def test_a_hospital_save_from_the_organisation_screen_keeps_the_stamp(people):
    org.first_setup("tbroot", True)
    o = org.load(); o["hospital"] = {**o["hospital"], "name": "Renamed (SYNTHETIC)"}; org.save(o, by="tbroot")
    assert org.hospital()["first_setup"]["by"] == "tbroot" and org.hospital()["name"] == "Renamed (SYNTHETIC)"


# ---- a Vaidyx admin, a disabled login -------------------------------------------------------------------------------------------

def test_vaidyx_admin_sees_every_case_file_the_board_and_the_organisation(people, cases):
    h = home.build(people["admin"])
    assert h["sections"] == ["treating", "coordinator", "root_admin"]
    assert {c["case_id"] for c in h["treating"]["cases"]} == {"TB-H-A", "TB-H-B", "TB-H-C"}
    assert all(c["relation"] in ("all",) for c in h["treating"]["cases"]) and h["treating"]["counts"]["mine"] == 0
    assert h["treating"]["counts"]["suggested_unsent"] == 1 and h["coordinator"]["can_manage"] is True and h["root_admin"]["setup_needed"] is True


def test_notifications_on_the_home(people, cases):
    h = home.build(people["anil"])
    assert h["unread"] >= 1 and any(n["kind"] == "board_ready" and n["case_id"] == "TB-H-A" for n in h["notifications"])  # the ready mark told the coordinator
    assert len(h["notifications"]) <= home.MAX_NOTIFICATIONS
