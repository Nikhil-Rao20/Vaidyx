"""Case File access (V2 item 5.1): the owning department, the participating departments, the departments asked, linked Case Files
and the open referral decide who reads a Case File (and how much) and who acts on it. Synthetic names and Case Files only; no model."""
import copy
from datetime import date, timedelta

import pytest

from tumour_board import access, notify, org, store
from tumour_board.tests.util import PATIENT


@pytest.fixture
def people(data_root):
    """Doctors of Pulmonology (treating), Colorectal Surgery (treating), Breast Surgery (treating), Radiology (supporting), Pathology
    (supporting), a two-department doctor (Radiology + Pulmonology), the MDT Coordinator, a root admin and the Vaidyx admin."""
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"pulmo": {"departments": {"pulmonology": "member"}}, "colo": {"departments": {"colorectal_surgery": "head"}},
                  "breast": {"departments": {"breast_surgery": "member"}}, "ravi": {"departments": {"radiology": "member"}},
                  "kavya": {"departments": {"pathology": "head"}}, "both": {"departments": {"radiology": "member", "pulmonology": "member"}},
                  "anil": {"coordinator": True}, "root": {}, "off": {"departments": {"pulmonology": "member"}, "disabled": True}}
    o["admins"] = ["root"]
    org.save(o, by="test")
    return {k: org.roles(k) for k in ("pulmo", "colo", "breast", "ravi", "kavya", "both", "anil", "root", "off")} | {"admin": org.roles("tbadmin", vaidyx_admin=True),
                                                                                                                      "stranger": org.roles("stranger")}


def _case(case_id="TB-A1", owner="pulmonology", **extra):
    c = store.create_case(case_id, dict(PATIENT), "lung_nsclc", created_by="test")
    if owner:
        c["department"] = owner
    c.update(extra)
    store.save_case(c)
    return c


def _action(case_id, dept, status="pending", source="pre_authorization", **extra):
    st = store.get_state(case_id)
    a = {"id": f"A{len(st['actions']) + 1}", "source": source, "requirement": "ct_thorax" if source == "pre_authorization" else None, "label": "CT thorax",
         "department": org.department_name(dept), "department_id": dept, "status": status, "created": store.now_iso(), "history": [], **extra}
    st["actions"].append(a)
    store.save_state(case_id, st)
    return a


# ---- reading --------------------------------------------------------------------------------------------------------------

def test_owner_participants_coordinator_and_admin_read_the_whole_case_file(people):
    c = _case(participants=[{"department": "breast_surgery", "since": "2026-10-14T08:00:00", "by": "pulmo"}])
    assert access.scope(people["pulmo"], c) == access.FULL
    assert access.scope(people["breast"], c) == access.FULL
    assert access.scope(people["anil"], c) == access.FULL
    assert access.scope(people["admin"], c) == access.FULL
    assert access.scope(people["both"], c) == access.FULL  # a Radiology doctor who is also placed in Pulmonology
    for who in ("colo", "ravi", "kavya", "root", "stranger", "off"):
        assert access.scope(people[who], c) is None, who
    assert "Pulmonology" in access.refusal(people["colo"], c)


def test_a_case_file_without_an_owner_stays_open_to_every_placed_account(people):
    c = _case(owner=None)
    for who in ("pulmo", "colo", "ravi", "kavya", "anil", "admin"):
        assert access.scope(people[who], c) == access.FULL, who
    for who in ("root", "stranger", "off"):
        assert access.scope(people[who], c) is None, who


def test_a_department_that_received_a_request_sees_only_the_items_it_was_asked_about(people):
    c = _case()
    assert access.scope(people["ravi"], c) is None
    a = _action("TB-A1", "radiology", status="suggested")
    assert access.scope(people["ravi"], c) is None, "a suggestion nobody sent opens nothing"
    st = store.get_state("TB-A1"); st["actions"][0]["status"] = "pending"; st["actions"][0]["sent"] = {"by": "pulmo", "at": store.now_iso()}; store.save_state("TB-A1", st)
    assert access.scope(people["ravi"], c) == access.REQUESTS
    assert access.scope(people["kavya"], c) is None
    assert [x["id"] for x in access.my_actions(people["ravi"], "TB-A1")] == [a["id"]]
    lim = access.limited_state(people["ravi"], c, store.get_state("TB-A1"))
    assert lim["limited"] is True and lim["gate"] is None and lim["board_records"] == [] and [x["id"] for x in lim["actions"]] == [a["id"]]
    # the records in scope: the department's own, and the one the request names
    docs = [{"doc_id": "D1", "department": "radiology"}, {"doc_id": "D2", "department": "pathology"}, {"doc_id": "D3"}, {"doc_id": "D4", "department": "Radiology"}]
    assert [d["doc_id"] for d in access.limited_docs(people["ravi"], c, docs)] == ["D1", "D4"]
    st = store.get_state("TB-A1"); st["actions"][0]["source_doc_id"] = "D3"; store.save_state("TB-A1", st)
    assert [d["doc_id"] for d in access.limited_docs(people["ravi"], c, docs)] == ["D1", "D3", "D4"]


def test_a_closed_request_keeps_the_limited_view_for_seven_days_and_a_board_action_counts_too(people):
    c = _case()
    recent = (date.today() - timedelta(days=3)).isoformat() + "T10:00:00"
    old = (date.today() - timedelta(days=9)).isoformat() + "T10:00:00"
    _action("TB-A1", "radiology", status="completed", completed=recent, sent={"by": "pulmo", "at": recent})
    assert access.scope(people["ravi"], c) == access.REQUESTS
    st = store.get_state("TB-A1"); st["actions"][0]["completed"] = old; store.save_state("TB-A1", st)
    assert access.scope(people["ravi"], c) is None
    st["actions"][0]["completed"] = recent; st["actions"][0]["never_sent"] = True; store.save_state("TB-A1", st)
    assert access.scope(people["ravi"], c) is None, "closed as a suggestion: no inbox ever listed it"
    _action("TB-A1", "pathology", status="pending", source="board")
    assert access.scope(people["kavya"], c) == access.REQUESTS


def test_an_open_referral_and_a_linked_case_file_open_the_whole_case_file(people):
    c = _case(referrals=[{"id": "R1", "from": "pulmonology", "to": "colorectal_surgery", "status": "requested"}])
    assert access.scope(people["colo"], c) == access.FULL and access.scope(people["breast"], c) is None
    c["referrals"][0]["status"] = "declined"
    assert access.scope(people["colo"], c) is None
    c = _case("TB-A2", linked_cases=[{"case_id": "TB-A3", "protocol": "breast", "department": "breast_surgery"}])
    assert access.scope(people["breast"], c) == access.FULL and access.scope(people["colo"], c) is None
    assert access.linked_owners(c) == ["breast_surgery"], "the linked Case File does not exist: the department recorded with the link"
    # the linked Case File exists and was referred since: its current owner reads this one, the recorded department no longer does
    _case("TB-A3", owner="colorectal_surgery")
    assert access.linked_owners(c) == ["colorectal_surgery"] and access.scope(people["colo"], c) == access.FULL and access.scope(people["breast"], c) is None
    assert access.public(c)["linked_cases"][0]["department_name"] == "Colorectal Surgery"


def test_visible_filters_the_case_list(people):
    a = _case("TB-A1", owner="pulmonology"); b = _case("TB-A2", owner="colorectal_surgery"); n = _case("TB-A3", owner=None)
    assert [c["case_id"] for c in access.visible(people["pulmo"], [a, b, n])] == ["TB-A1", "TB-A3"]
    assert [c["case_id"] for c in access.visible(people["anil"], [a, b, n])] == ["TB-A1", "TB-A2", "TB-A3"]
    assert access.visible(people["ravi"], [a, b, n]) == [n]


# ---- acting ----------------------------------------------------------------------------------------------------------------

def test_clinical_actions_belong_to_the_owning_department(people):
    c = _case(participants=[{"department": "breast_surgery", "since": "x", "by": "pulmo"}])
    for action in sorted(access.OWNER_ACTIONS - {"waive", "confirm", "dismiss_failed", "delete_document"}):
        assert access.may(people["pulmo"], action, c), action
        assert access.may(people["admin"], action, c), action
        assert not access.may(people["breast"], action, c), (action, "a participant reads and comments, never acts")
        assert not access.may(people["colo"], action, c), action
        assert not access.may(people["anil"], action, c), (action, "the coordinator does no clinical action on an owned Case File")
        assert not access.may(people["ravi"], action, c), action
    assert access.may(people["pulmo"], "waive", c, "Radiology") and not access.may(people["breast"], "waive", c, "Radiology") and not access.may(people["anil"], "waive", c, "Radiology")
    assert access.may(people["pulmo"], "confirm", c, None) and not access.may(people["colo"], "confirm", c, None)
    with pytest.raises(PermissionError, match="Pulmonology"):
        access.require(people["colo"], "waive", c, "Radiology")
    with pytest.raises(PermissionError, match="takes part"):
        access.require(people["breast"], "send_request", c)
    with pytest.raises(PermissionError, match="permission"):
        access.require(people["ravi"], "refer", c)  # refused by the role, not by the owner rule
    access.require(people["pulmo"], "refer", c)


def test_a_department_still_confirms_and_its_head_deletes_its_own_upload(people):
    c = _case()
    assert access.may(people["ravi"], "confirm", c, "radiology") and access.may(people["ravi"], "dismiss_failed", c, "Radiology")
    assert not access.may(people["ravi"], "confirm", c, "pathology") and not access.may(people["ravi"], "confirm", c, None)
    assert access.may(people["kavya"], "delete_document", c, "pathology") and not access.may(people["kavya"], "delete_document", c, "radiology")
    assert not access.may(people["anil"], "delete_document", c, "pathology"), "the coordinator's V1 delete right stops at an owned Case File"
    assert access.may(people["anil"], "delete_document", _case("TB-A9", owner=None), "pathology"), "and stays on a Case File without an owner"
    assert access.may(people["pulmo"], "delete_document", c, "pathology") and not access.may(people["colo"], "delete_document", c, "pathology")
    assert org.can_as_member(people["ravi"], "confirm", "radiology") and not org.can_as_member(people["pulmo"], "confirm", "radiology")
    assert not org.can_as_member(people["anil"], "delete_document", "pathology") and not org.can_as_member(people["ravi"], "waive", "radiology")
    assert not org.can_as_member(people["ravi"], "confirm", None) and not org.can_as_member(people["ravi"], "send_request", "radiology")


def test_without_an_owner_any_treating_doctor_acts_as_before(people):
    c = _case(owner=None)
    assert access.may(people["pulmo"], "waive", c, "Radiology") and access.may(people["colo"], "send_request", c) and access.may(people["anil"], "upload_to_case", c)
    assert not access.may(people["ravi"], "waive", c, "Radiology")
    assert access.is_owner_doctor(people["pulmo"], c) and access.is_owner_doctor(people["colo"], c) and not access.is_owner_doctor(people["ravi"], c) and not access.is_owner_doctor(people["anil"], c)


def test_the_listing_is_changed_by_the_coordinator_or_the_owner(people):
    c = _case()
    assert access.may_list(people["anil"], c) and access.may_list(people["pulmo"], c) and access.may_list(people["admin"], c)
    assert not access.may_list(people["colo"], c) and not access.may_list(people["ravi"], c)
    assert not access.may_list(people["pulmo"], _case("TB-A2", owner=None)), "a Case File without an owner is listed by the coordinator (V1)"


def test_actions_without_the_owner_rule_follow_org_can(people):
    c = _case()
    assert access.may(people["anil"], "board_record", c) and not access.may(people["pulmo"], "board_record", c)
    assert access.may(people["ravi"], "answer_request", c, "radiology") and not access.may(people["ravi"], "answer_request", c, "pathology")
    assert not access.may(people["off"], "upload_to_case", c) and not access.may(people["root"], "upload_to_case", c)


# ---- the owner and the participants ----------------------------------------------------------------------------------------

def test_set_owner_records_a_treating_department_once_and_is_audited(people):
    _case(owner=None)
    with pytest.raises(access.AccessError, match="supporting"):
        access.set_owner("TB-A1", "Radiology", "anil")
    with pytest.raises(access.AccessError, match="Unknown"):
        access.set_owner("TB-A1", "Cardiology", "anil")
    with pytest.raises(access.AccessError, match="not placed") as e:
        access.set_owner("TB-A1", "Colorectal Surgery", "pulmo", roles=people["pulmo"])
    assert e.value.status == 403
    c = access.set_owner("TB-A1", "Pulmonology", "pulmo", roles=people["pulmo"], reason="my patient")
    assert c["department"] == "pulmonology" and access.owner(c) == "pulmonology"
    ev = next(e for e in store.read_audit("TB-A1") if e["kind"] == "owner_set")
    assert ev["department"] == "pulmonology" and ev["before"] is None and ev["by"] == "pulmo" and ev["reason"] == "my patient"
    c = access.set_owner("TB-A1", "colorectal_surgery", "anil", roles=people["anil"])  # the coordinator may name one on a Case File without an owner
    assert c["department"] == "colorectal_surgery"


def test_participants_are_added_and_removed_by_the_owner_told_and_audited(people):
    _case()
    with pytest.raises(access.AccessError, match="owns"):
        access.add_participant("TB-A1", "Pulmonology", "pulmo")
    with pytest.raises(access.AccessError, match="Unknown"):
        access.add_participant("TB-A1", "Cardiology", "pulmo")
    c = access.add_participant("TB-A1", "Radiation Oncology", "pulmo", reason="radiotherapy opinion")
    assert access.participants(c) == ["radiation_oncology"] and c["participants"][0]["by"] == "pulmo" and c["participants"][0]["reason"] == "radiotherapy opinion"
    with pytest.raises(access.AccessError, match="already"):
        access.add_participant("TB-A1", "radiation_oncology", "pulmo")
    n = [x for x in notify.for_roles(org.roles("pulmo"), limit=50)]
    assert n == []
    o = org.load(); o["users"]["rt"] = {"departments": {"radiation_oncology": "member"}}; org.save(o, by="test")
    n = notify.for_roles(org.roles("rt"), limit=50)
    assert len(n) == 1 and n[0]["kind"] == "case_shared" and "Pulmonology" in n[0]["text"] and "radiotherapy opinion" in n[0]["text"]
    assert access.scope(org.roles("rt"), store.get_case("TB-A1")) == access.FULL
    pub = access.public(store.get_case("TB-A1"))
    assert pub["owner"] == {"id": "pulmonology", "name": "Pulmonology"} and pub["participants"][0]["name"] == "Radiation Oncology"
    c = access.remove_participant("TB-A1", "Radiation Oncology", "pulmo", reason="opinion given")
    assert access.participants(c) == [] and access.scope(org.roles("rt"), c) is None
    with pytest.raises(access.AccessError, match="does not take part"):
        access.remove_participant("TB-A1", "radiation_oncology", "pulmo")
    kinds = [e["kind"] for e in store.read_audit("TB-A1")]
    assert kinds.count("participant_added") == 1 and kinds.count("participant_removed") == 1


def test_no_em_dashes_in_module():
    import pathlib
    assert "—" not in pathlib.Path(access.__file__).read_text(encoding="utf-8")
