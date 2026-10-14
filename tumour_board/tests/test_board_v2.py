"""V2 Phase 6: the MDT Coordinator and during the board. 6.1 the four heads and the hospital's attendance sheet, "mark ready" by the owner,
the agenda from the ready Case Files, reminders on the owner's behalf, who may open the Board room, follow-up and minutes; 6.2 the agent
of a head not recorded present, the surgical seat per Case File (the service side is in test_phase6_agents.py). Synthetic Case Files in
the temporary data root; no model calls, no network."""
import asyncio, copy, json

import pytest

from tumour_board import access, agents, board, dept_requests, his_case, metrics, notify, org, postboard, rules, service, store
from tumour_board.tests import util

DATE = "2026-10-22"
ROLES = {"user": "x", "admin": False, "vaidyx_admin": False, "root_admin": False, "coordinator": False, "departments": {}, "admin_of": [],
         "treating": {}, "supporting": {}, "disabled": False, "known": True}


def _r(user, **kw):
    r = {**ROLES, "user": user, **kw}
    deps = r["departments"]
    r["treating"] = {k: v for k, v in deps.items() if org.department_group(k) == "treating"}
    r["supporting"] = {k: v for k, v in deps.items() if org.department_group(k) == "supporting"}
    return r


COORD = _r("anil", coordinator=True)
BREAST = _r("meera", departments={"breast_surgery": "member"})
MEDONC = _r("dev", departments={"medical_oncology": "member"})
RAD = _r("ravi", departments={"radiology": "member"})
GYN = _r("gita", departments={"gynaecologic_oncology": "member"})
ADMIN = _r("tbadmin", admin=True)
UNPLACED = _r("nobody", known=False)


def _case(cid, owner=None, protocol="breast", board_date=DATE, name="SYNTHETIC, Board Patient"):
    c = store.create_case(cid, {**util.PATIENT, "name": name}, protocol, board_date=board_date, created_by="test")
    if owner:
        c["department"] = owner; store.save_case(c)
    return c


def _hospital(**kw):
    o = copy.deepcopy(org.load())
    o["hospital"] = {**o["hospital"], **kw}
    org.save(o, by="test")


def _notes():
    p = notify.path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def cases(data_root):
    _case("TB-BR", owner="breast_surgery")
    _case("TB-MO", owner="medical_oncology", protocol="lung_nsclc")
    _case("TB-NO")  # no owner (a V1-style Case File)
    return ["TB-BR", "TB-MO", "TB-NO"]


# ---- 6.1 / 6.2: heads and the attendance sheet ---------------------------------------------------------------------------------------

def test_heads_default_and_hospital_setting(data_root):
    assert [h["id"] for h in board.heads()] == ["radiology", "medical_oncology", "surgical_oncology", "pathology"]
    assert all(h["role"] == h["id"] for h in board.heads()) and board.heads()[0]["name"] == "Radiology"
    _hospital(board_heads=["pathology", "radiology", "pulmonology"])  # a hospital may name its own heads; Pulmonology has no agent
    assert [(h["id"], h["role"]) for h in board.heads()] == [("pathology", "pathology"), ("radiology", "radiology"), ("pulmonology", None)]
    with pytest.raises(ValueError, match="unknown department"):
        _hospital(board_heads=["cardiology"])
    with pytest.raises(ValueError, match="at least one head"):
        _hospital(board_heads=[])
    with pytest.raises(ValueError, match="list of department ids"):
        _hospital(surgical_departments="breast_surgery")


def test_attendance_sheet_heads_first_then_on_demand_hospital_list_and_owners(cases):
    _hospital(board_attendance=["palliative_medicine"])
    s = board.create(DATE, "anil")
    sheet = board.attendance_list(s)
    ids = [d["id"] for d in sheet]
    assert ids[:4] == ["radiology", "medical_oncology", "surgical_oncology", "pathology"] and all(d["head"] for d in sheet[:4])
    assert ids[4:6] == ["radiation_oncology", "nuclear_medicine"] and all(d["on_demand"] for d in sheet[4:6])
    assert ids[6:] == ["palliative_medicine", "breast_surgery"]  # the hospital's list, then the owners of the agenda (Medical Oncology is a head already)
    assert next(d for d in sheet if d["id"] == "breast_surgery")["why"] == "owner: TB-BR"
    assert set(s["attendance"]) == set(ids) and "biochemistry" not in s["attendance"]  # not all 30 departments
    board.add_member(s["id"], "Dr Shah", "urology", "anil")  # a member of another department brings it onto the sheet
    assert [d["id"] for d in board.attendance_list(board.get(s["id"]))][-1] == "urology"


# ---- 6.1: mark ready, the agenda from the ready Case Files -------------------------------------------------------------------------

def test_mark_ready_audits_notifies_the_coordinator_and_builds_the_agenda(cases):
    rows = {r["case_id"]: r for r in board.listed_for_date(DATE)}
    assert rows["TB-BR"]["ready"] is None and rows["TB-BR"]["owner_name"] == "Breast Surgery" and rows["TB-BR"]["summary"] == "none" and rows["TB-BR"]["gate_passed"] is False
    c = board.mark_ready("TB-BR", "meera", note="Summary compiled")
    assert c["board_ready"]["by"] == "meera" and c["board_ready"]["note"] == "Summary compiled"
    kinds = [e["kind"] for e in store.read_audit("TB-BR")]
    assert "board_ready" in kinds
    n = [x for x in _notes() if x["kind"] == "board_ready"]
    assert n and n[0]["to"] == {"role": "coordinator"} and "Ready for the board" in n[0]["title"] and "Breast Surgery" in n[0]["text"]
    assert notify.for_roles(COORD) and not notify.for_roles(RAD)
    s = board.create(DATE, "anil")  # the default agenda: the ready Case Files only
    assert [a["case_id"] for a in s["agenda"]] == ["TB-BR"] and s["agenda"][0]["owner_ready"] is True and s["agenda"][0]["ready_by"] == "meera"
    s2 = board.create(DATE, "anil", case_ids=["TB-BR", "TB-MO"])  # the coordinator may add one the owner has not marked: recorded as such
    assert [(a["case_id"], a["owner_ready"]) for a in s2["agenda"]] == [("TB-BR", True), ("TB-MO", False)]
    ev = [json.loads(l) for l in (board.sessions_dir() / "audit.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "created" and e["session"] == s2["id"] and e["not_marked_ready"] == ["TB-MO"] for e in ev)
    c = board.mark_ready("TB-BR", "meera", ready=False, note="A report came back amended")
    assert "board_ready" not in c and c["board_ready_history"][-1] == {"ready": False, "by": "meera", "at": c["board_ready_history"][-1]["at"], "note": "A report came back amended"}
    assert "board_ready_withdrawn" in [e["kind"] for e in store.read_audit("TB-BR")]
    with pytest.raises(ValueError, match="List the Case File"):
        board.mark_ready(store.create_case("TB-UNL", util.PATIENT, "", created_by="t")["case_id"], "meera")


def test_without_ready_marks_every_listed_case_file_is_the_agenda(cases):
    s = board.create(DATE, "anil")
    assert [a["case_id"] for a in s["agenda"]] == ["TB-BR", "TB-MO", "TB-NO"] and not any(a["owner_ready"] for a in s["agenda"])


def test_mark_ready_is_the_owners_action(cases):
    br, mo = store.get_case("TB-BR"), store.get_case("TB-MO")
    assert access.may(BREAST, "mark_ready", br) and not access.may(BREAST, "mark_ready", mo) and not access.may(COORD, "mark_ready", br) and not access.may(RAD, "mark_ready", br)
    assert access.may(ADMIN, "mark_ready", mo) and access.may(BREAST, "mark_ready", store.get_case("TB-NO"))  # any treating doctor on a Case File without an owner


# ---- 6.2: agents for a head not recorded present, the surgical seat per Case File, on demand ---------------------------------------

def test_a_head_not_recorded_present_has_its_agent_active_on_demand_roles_only_when_absent(cases):
    s = board.create(DATE, "anil")
    assert board.absent_roles(s) == ["radiology", "pathology", "medical_oncology", "surgical_oncology"]  # nothing recorded yet
    for d in ("radiology", "pathology", "medical_oncology"):
        board.set_attendance(s["id"], d, "present", "anil")
    s = board.get(s["id"])
    assert board.absent_roles(s) == ["surgical_oncology"]
    board.set_attendance(s["id"], "nuclear_medicine", "absent", "anil")  # an on-demand specialty marked absent: its agent is active as in V1
    assert board.absent_roles(board.get(s["id"])) == ["surgical_oncology", "nuclear_medicine"]
    board.set_attendance(s["id"], "surgical_oncology", "present", "anil")
    assert board.absent_roles(board.get(s["id"])) == ["nuclear_medicine"]


def test_surgical_seat_filled_per_case_file_by_the_case_files_own_surgeon(cases):
    s = board.create(DATE, "anil")
    for d in ("radiology", "pathology", "medical_oncology"):
        board.set_attendance(s["id"], d, "present", "anil")
    s = board.add_member(s["id"], "Dr Meera Nair", "breast_surgery", "anil")  # a breast surgeon present: fills the seat for the breast Case File only
    br, mo, no = (store.get_case(x) for x in ("TB-BR", "TB-MO", "TB-NO"))
    st = board.seat(s, br)
    assert st == {"filled": True, "filled_by": ["breast_surgery"], "filled_by_names": ["Breast Surgery"], "members": ["Dr Meera Nair"], "agent": False,
                  "check_pmjay": True, "own_surgical": ["breast_surgery"], "own_surgical_names": ["Breast Surgery"]}
    assert board.seat(s, mo)["filled"] is False and board.seat(s, mo)["agent"] is True and board.seat(s, mo)["own_surgical"] == []
    assert board.seat(s, no)["filled"] is True  # no owner: the breast protocol's clinical department is Breast Surgery
    assert board.absent_roles(s, "TB-BR") == [] and board.absent_roles(s, "TB-MO") == ["surgical_oncology"] and board.absent_roles(s) == ["surgical_oncology"]
    assert board.absent_roles_by_case(s) == {"TB-BR": [], "TB-MO": ["surgical_oncology"], "TB-NO": []}
    s = board.add_member(s["id"], "Dr Vikram Shah", "surgical_oncology", "anil")  # a surgical oncologist fills every seat
    assert board.absent_roles_by_case(s) == {"TB-BR": [], "TB-MO": [], "TB-NO": []} and board.seat(s, br)["check_pmjay"] is False
    assert board.seat(s, br)["filled_by"] == ["surgical_oncology", "breast_surgery"]


def test_gynaecologic_oncology_fills_the_seat_without_a_pmjay_note(data_root):
    _case("TB-GY", owner="gynaecologic_oncology", protocol="cervix")
    s = board.create(DATE, "anil")
    s = board.add_member(s["id"], "Dr Gita Rao", "gynaecologic_oncology", "anil")
    st = board.seat(s, store.get_case("TB-GY"))
    assert st["filled"] and st["check_pmjay"] is False
    _hospital(pmjay_surgical_oncology=["surgical_oncology"])  # the root admin narrows the list: now it is a "check"
    assert board.seat(board.get(s["id"]), store.get_case("TB-GY"))["check_pmjay"] is True


# ---- 6.1: who opens the Board room ----------------------------------------------------------------------------------------------------

def test_who_may_open_the_board_room(cases):
    s = board.create(DATE, "anil", case_ids=["TB-BR"])
    assert board.may_open(COORD, s) and board.may_open(ADMIN, s)
    assert board.may_open(RAD, s)  # Radiology is a head: on the sheet
    assert board.may_open(BREAST, s)  # the owner of a Case File on the agenda
    assert not board.may_open(GYN, s) and not board.may_open(UNPLACED, s) and not board.may_open({**COORD, "disabled": True, "known": False}, s)
    assert board.may_open(MEDONC, s)  # a head too
    _hospital(board_heads=["radiology"], board_attendance=["gynaecologic_oncology"])
    assert board.may_open(GYN, board.get(s["id"])) and not board.may_open(MEDONC, board.get(s["id"]))


# ---- 6.1: follow-up and minutes ------------------------------------------------------------------------------------------------------

def _decide(sid, cid, text="Plan as dictated.", actions=()):
    rec = {"id": "B" + cid[-2:], "decision_text": text, "recorded_by": "Dr Chair (synthetic)", "recorded_at": "2026-10-22T11:00:00", "board_date": DATE, "outcome_type": "decision",
           "actions": list(actions), "adjudication": {"flags": [], "status": "consistent", "composition": postboard.composition({"attendance": {"present": ["Radiology", "Medical Oncology", "Surgical Oncology", "Pathology", "Radiation Oncology"], "members": []}})},
           "resolution": {"final": True}, "intent_as_recorded": "curative", "next_review": "2026-11-22"}
    st = store.get_state(cid); st.setdefault("board_records", []).append(rec)
    for i, a in enumerate(actions):
        st.setdefault("actions", []).append({"id": f"X{cid[-2:]}{i}", "source": "board", "board_record": rec["id"], "department": a["department"], "what": a["task"],
                                             "label": a["task"], "due": a["due"], "status": "completed" if a.get("done") else "pending", "completed": "2026-10-23T09:00:00" if a.get("done") else None})
    store.save_state(cid, st)
    board.link_decision(sid, cid, rec, "anil")
    return rec


def test_followup_lists_the_sessions_board_actions_with_their_state(cases):
    s = board.create(DATE, "anil", case_ids=["TB-BR", "TB-MO"])
    board.start(s["id"], "anil")
    _decide(s["id"], "TB-BR", actions=[{"department": "Radiology", "task": "MRI breast", "due": "2026-10-01"}, {"department": "Pathology", "task": "IHC repeat", "due": "2026-12-01", "done": True}])
    fu = board.followup(board.get(s["id"]))
    assert fu["open"] == 1 and fu["overdue"] == 1 and fu["closed"] == 1
    assert [(a["case_id"], a["department"], a["status"], a["overdue"]) for a in fu["actions"]] == [("TB-BR", "Radiology", "pending", True), ("TB-BR", "Pathology", "completed", False)]


def test_minutes_hold_attendance_decisions_seat_and_followup(cases):
    _hospital(name="Vaidyx Demo Cancer Centre (SYNTHETIC)")
    s = board.create(DATE, "anil", case_ids=["TB-BR", "TB-MO"], title="Breast and thoracic board")
    for d in ("radiology", "medical_oncology"):
        board.set_attendance(s["id"], d, "present", "anil")
    board.set_attendance(s["id"], "pathology", "absent", "anil")
    board.add_member(s["id"], "Dr Meera Nair", "breast_surgery", "anil")
    board.add_member(s["id"], "Anil Kumar", "coordinator", "anil")
    board.mark_ready("TB-BR", "meera")
    board.start(s["id"], "anil")
    for cid, role in (("TB-BR", "pathology"), ("TB-MO", "pathology"), ("TB-MO", "surgical_oncology")):  # the briefs the session recorded (no model here)
        board.set_agent(s["id"], cid, role, "ready", generated="2026-10-22T10:00:00")
    _decide(s["id"], "TB-BR", text="Surgery first; discuss adjuvant plan after HPE <b>x</b>.", actions=[{"department": "Radiology", "task": "MRI breast", "due": "2026-10-30"}])
    m = board.minutes(s["id"])
    assert m["hospital"] == "Vaidyx Demo Cancer Centre (SYNTHETIC)" and m["session"]["title"] == "Breast and thoracic board" and m["coordinators_present"] == ["Anil Kumar"]
    sheet = {a["id"]: a for a in m["attendance"]}
    assert sheet["pathology"]["status_label"] == "Absent" and sheet["pathology"]["agent_stood_in"] == ["TB-BR", "TB-MO"]
    assert sheet["surgical_oncology"]["status_label"] == "Not recorded" and sheet["surgical_oncology"]["agent_stood_in"] == ["TB-MO"]  # the breast surgeon fills TB-BR's seat
    board.set_attendance(s["id"], "pathology", "present", "anil")  # the pathologist arrives later: the minutes keep that the agent stood in
    assert {a["id"]: a for a in board.minutes(s["id"])["attendance"]}["pathology"]["agent_stood_in"] == ["TB-BR", "TB-MO"]
    assert sheet["breast_surgery"]["members"] == ["Dr Meera Nair"] and sheet["radiology"]["head"] is True
    br = next(c for c in m["cases"] if c["case_id"] == "TB-BR")
    assert br["owner_name"] == "Breast Surgery" and br["ready"]["by"] == "meera" and br["seat"]["filled_by"] == ["breast_surgery"] and br["agents"] == ["pathology"]
    assert br["decision"]["outcome_label"] == "Decision recorded" and br["decision"]["actions"] == [{"department": "Radiology", "task": "MRI breast", "due": "2026-10-30"}]
    assert br["decision"]["intent"] == "curative" and br["decision"]["final"] is True
    mo = next(c for c in m["cases"] if c["case_id"] == "TB-MO")
    assert mo["decision"] is None and mo["seat"]["agent"] is True and set(mo["agents"]) == {"pathology", "surgical_oncology"}
    assert m["followup"]["open"] == 1 and "never a member" in m["note"]
    h = board.minutes_html(s["id"])
    assert "Tumour Board minutes: 22/10/2026, Breast and thoracic board" in h and "Vaidyx Demo Cancer Centre (SYNTHETIC)" in h
    assert "Surgery first; discuss adjuvant plan after HPE &lt;b&gt;x&lt;/b&gt;." in h and "<b>x</b>" not in h
    assert "Surgical seat: Breast Surgery (Dr Meera Nair) ; check PM-JAY requirement" in h  # a breast surgeon outside the PM-JAY list (6.4)
    assert "the Surgical Oncology AI support agent stood in" in h and "No board decision recorded" in h
    assert "Marked ready by meera" in h and "MRI breast" in h and "Follow-up" in h and "—" not in h
    ev = [json.loads(l) for l in (board.sessions_dir() / "audit.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "decision_linked" for e in ev)


# ---- 6.1: reminders on the owner's behalf --------------------------------------------------------------------------------------------

def _requests(cid):
    st = store.get_state(cid)
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "cect", "label": "CECT thorax", "department": "Radiology", "department_id": "radiology",
                      "status": "pending", "created": "2026-10-10T09:00:00", "due": "2026-10-20", "what": "CECT thorax, abdomen and pelvis", "accession": "RAD/26/00990",
                      "sent": {"by": "meera", "at": "2026-10-10T09:05:00", "count": 1}, "history": []},
                     {"id": "A2", "source": "pre_authorization", "requirement": "ihc", "label": "IHC panel", "department": "Pathology", "department_id": "pathology",
                      "status": "suggested", "created": "2026-10-10T09:00:00", "what": "ER, PR, HER2 and Ki-67", "history": []},
                     {"id": "A3", "source": "pre_authorization", "requirement": "cbc", "label": "CBC", "department": "Pathology", "department_id": "pathology",
                      "status": "completed", "completed": "2026-10-11T09:00:00", "history": []}]
    store.save_state(cid, st)


def test_reminders_reach_the_department_or_the_owner_and_are_audited(cases):
    _requests("TB-BR")
    a = dept_requests.remind("TB-BR", "A1", "anil", COORD, note="The board is on Thursday")
    assert a["reminders"][0]["to"] == "Radiology" and a["reminders"][0]["sent"] is True and a["status"] == "pending" and a["due"] == "2026-10-20"  # the due date is kept
    n = [x for x in _notes() if x["kind"] == "request_reminder"]
    assert n[0]["to"] == {"department": "radiology"} and n[0]["action_id"] == "A1" and "anil (MDT Coordinator, on behalf of Breast Surgery)" in n[0]["text"]
    assert "The board is on Thursday" in n[0]["text"] and n[0]["accession"] == "RAD/26/00990" and "Due 20/10/2026" in n[0]["text"]
    assert notify.for_roles(RAD)[0]["kind"] == "request_reminder" and not notify.for_roles(BREAST)
    a = dept_requests.remind("TB-BR", "A2", "anil", COORD)  # a suggestion nobody sent: the owner is reminded, Pathology hears nothing
    assert a["status"] == "suggested" and a["reminders"][0]["to"] == "Breast Surgery" and a["reminders"][0]["sent"] is False
    n = [x for x in _notes() if x["kind"] == "owner_reminder"]
    assert n[0]["to"] == {"department": "breast_surgery"} and "nobody has sent yet" in n[0]["text"] and "22/10/2026" in n[0]["text"]
    assert [x["kind"] for x in notify.for_roles(BREAST)] == ["owner_reminder"] and not [x for x in notify.for_roles(_r("p", departments={"pathology": "member"}))]
    a = dept_requests.remind("TB-BR", "A1", "meera", BREAST)  # the owner's own doctor reminds in its own name
    assert "meera (Breast Surgery)" in [x for x in _notes() if x["kind"] == "request_reminder"][-1]["text"] and len(a["reminders"]) == 2
    kinds = [e["kind"] for e in store.read_audit("TB-BR")]
    assert kinds.count("request_reminded") == 2 and kinds.count("owner_reminded") == 1
    with pytest.raises(dept_requests.RequestError, match="closed"):
        dept_requests.remind("TB-BR", "A3", "anil", COORD)
    with pytest.raises(dept_requests.RequestError, match="not found"):
        dept_requests.remind("TB-BR", "A9", "anil", COORD)


def test_owner_reminder_sums_up_the_case_file_before_the_board(cases):
    _requests("TB-BR")
    st = store.get_state("TB-BR"); st["actions"][0]["due"] = "2026-01-01"; store.save_state("TB-BR", st)  # overdue
    out = dept_requests.remind_owner("TB-BR", "anil", COORD, note="Please send the IHC request")
    assert out["to"] == "Breast Surgery" and out["unsent"] == 1 and out["overdue"] == 1
    t = out["text"]
    assert "1 suggested request(s) not sent: IHC panel (Pathology)" in t and "1 request(s) overdue: CECT thorax (Radiology, due 01/01/2026)" in t
    assert "no Case File summary compiled yet" in t and "not marked ready for the board" in t and "Please send the IHC request" in t
    assert store.get_case("TB-BR")["reminders"][0]["by"] == "anil" and "owner_reminded" in [e["kind"] for e in store.read_audit("TB-BR")]
    assert metrics.agenda(DATE)["cases"][0]["reminders"] >= 0
    with pytest.raises(dept_requests.RequestError, match="no owning department"):
        dept_requests.remind_owner("TB-NO", "anil", COORD)


def test_who_may_remind(cases):
    br = store.get_case("TB-BR")
    assert access.may_remind(COORD, br) and access.may_remind(ADMIN, br) and access.may_remind(BREAST, br)
    assert not access.may_remind(MEDONC, br) and not access.may_remind(RAD, br) and not access.may_remind(UNPLACED, br)
    assert access.may_remind(MEDONC, store.get_case("TB-NO"))  # any treating doctor on a Case File without an owner


# ---- 6.3: a hospital-system record's file fetched live when missing --------------------------------------------------------------------
