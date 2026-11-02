"""followup: Tumour Board actions to department inboxes, closing suggestions (plan item 7.4). Synthetic Case Files only."""
import copy, json
from datetime import date

import pytest

from tumour_board import followup, notify, org, protocol, store
from tumour_board.tests import util

TODAY = date(2026, 10, 11)


@pytest.fixture
def people():
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"ravi": {"departments": {"radiology": "member"}}, "meera": {"departments": {"medical_oncology": "member"}},
                  "anil": {"coordinator": True}}
    org.save(o, by="test")
    return {"radio": org.roles("ravi"), "onco": org.roles("meera"), "coord": org.roles("anil")}


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(followup, "_today", lambda: TODAY)
    monkeypatch.setattr(notify, "_today", lambda: TODAY)
    return TODAY


@pytest.fixture
def case(people):
    store.create_case("TB-SYN-F", {"name": "SYNTHETIC, Lakshmi Iyer", "mrn": "SYN-200001", "agesex": "58 Y / F"}, "colorectal_rectum",
                      board_date="2026-10-09", created_by="test")
    return "TB-SYN-F"


def _sent(data_root):
    p = data_root / "notifications.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


RECORD = {"id": "B1a2b3c", "actions": [
    {"task": "MRI pelvis after neoadjuvant chemoradiation", "department": "Radiology", "due": "2026-12-15"},
    {"task": "Start short-course chemotherapy", "department": "Medical Oncology", "due": ""},
    {"task": "Cardiology review", "department": "Cardiology"},
    {"task": "", "department": ""},
]}


# --- board_actions ---------------------------------------------------------------------------------------------------

def test_board_actions_fields_and_department_mapping(case, today, data_root):
    acts = followup.board_actions(case, RECORD, by="anil")
    assert len(acts) == 4
    mri, chemo, cardio, blank = acts
    assert mri["source"] == "board" and mri["board_record"] == "B1a2b3c" and mri["requirement"] is None
    assert mri["label"] == mri["what"] == "MRI pelvis after neoadjuvant chemoradiation"
    assert mri["department"] == "Radiology" and mri["department_id"] == "radiology"  # through the alias
    assert mri["status"] == "pending" and mri["due"] == "2026-12-15" and mri["created"]
    assert mri["history"][0]["event"] == "Created from Tumour Board record B1a2b3c"
    assert chemo["department_id"] == "medical_oncology"
    assert cardio["department_id"] is None and blank["department_id"] is None
    assert blank["label"] == "Board action" and blank["what"] == ""
    assert len({a["id"] for a in acts}) == 4 and all(a["id"].startswith("A") for a in acts)
    assert [a["kind"] for a in acts] == ["action"] * 4  # night-v3 item 3.1: a typed action; the decision form's rows say investigation or referral
    kinds = followup.board_actions(case, {"id": "B9", "actions": [{"task": "PET-CT", "department": "Radiology", "kind": "investigation"},
                                                                  {"task": "Referral: Palliative care", "department": "Medical Oncology", "kind": "referral"}]})
    assert [a["kind"] for a in kinds] == ["investigation", "referral"]


def test_board_actions_default_due_from_protocol(case, today, monkeypatch):
    acts = followup.board_actions(case, RECORD)
    assert acts[1]["due"] == "2026-10-25" and acts[2]["due"] == "2026-10-25"  # colorectal_rectum protocol: 14 days
    real = protocol.get
    monkeypatch.setattr(protocol, "get", lambda pid: {**real(pid), "post_board": {"follow_up_default_days": 21}})
    assert followup.board_actions(case, RECORD)[1]["due"] == "2026-11-01"


def test_board_actions_unlisted_case_defaults_to_14_days(people, today):
    store.create_case("TB-SYN-U", util.PATIENT, "", created_by="test")
    assert followup.board_actions("TB-SYN-U", RECORD)[1]["due"] == "2026-10-25"


def test_board_actions_notify_known_departments_only(case, today, data_root):
    acts = followup.board_actions(case, RECORD, by="anil")
    sent = _sent(data_root)
    assert [n["to"] for n in sent] == [{"department": "radiology"}, {"department": "medical_oncology"}]
    n = sent[0]
    assert n["kind"] == "board_action" and n["case_id"] == case and n["action_id"] == acts[0]["id"]
    assert n["due"] == "2026-12-15" and n["board_record"] == "B1a2b3c"
    assert "SYNTHETIC, Lakshmi Iyer" in n["title"] and "15/12/2026" in n["text"]


def test_unknown_department_sends_nothing(case, today, data_root):
    followup.board_actions(case, {"id": "B2", "actions": [{"task": "ECHO", "department": "Cardiology"}]})
    assert _sent(data_root) == []


def test_notification_failure_never_breaks_recording(case, today, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(notify, "notify", boom)
    acts = followup.board_actions(case, RECORD)
    assert len(acts) == 4 and acts[0]["department_id"] == "radiology"


# --- task words -> document types ------------------------------------------------------------------------------------

@pytest.mark.parametrize("task,want", [
    ("MRI pelvis after neoadjuvant chemoradiation", {"mri"}),
    ("Repeat MRI pelvis after chemotherapy", {"mri"}),
    ("PET-CT for staging", {"pet_ct"}),
    ("Whole body PET CT", {"pet_ct"}),
    ("CECT thorax and abdomen", {"ct"}),
    ("Repeat biopsy", {"histopathology"}),
    ("CT guided biopsy of the lung lesion", {"histopathology"}),
    ("Histopathology review of outside slides", {"histopathology"}),
    ("IHC for ER, PR, HER2", {"ihc"}),
    ("PD-L1 testing", {"ihc"}),
    ("EGFR mutation testing", {"molecular"}),
    ("Colonoscopy to complete the evaluation", {"endoscopy"}),
    ("Repeat CEA and CBC", {"lab"}),
    ("Bone scan", {"bone_scan"}),
    ("Start short-course chemotherapy", set()),
    ("Follow up in OPD after 3 months", set()),
    ("Refer to Radiation Oncology", set()),
    ("Surgery: APR", set()),
    ("", set()),
])
def test_task_doc_types(task, want):
    assert followup.task_doc_types(task) == want


def test_task_doc_types_exist_in_facts_catalogue():
    assert set(followup._task_table()) <= set(protocol.doc_types())


# --- closing suggestions ---------------------------------------------------------------------------------------------

def _act(aid="A1", what="MRI pelvis after neoadjuvant chemoradiation", dept="Radiology", created="2026-10-09T18:00:00", **kw):
    return {"id": aid, "source": "board", "board_record": "B1a2b3c", "label": what, "department": dept,
            "department_id": org.department_id(dept), "requirement": None, "what": what, "status": "pending",
            "created": created, "due": "2026-10-20", "history": [{"ts": created, "event": "Created from Tumour Board record B1a2b3c"}], **kw}


def _doc(doc_id, doc_type, added, state="ready", title=None, **kw):
    d = util.make_doc(doc_id, doc_type, state=state, title=title or f"{doc_type.upper()} PELVIS")
    d["added"] = added
    d.update(kw)
    return d


def test_suggestion_for_later_mri(case, today, data_root):
    st = {"actions": [_act()]}
    docs = [_doc("D1", "mri", "2026-10-12T09:30:00", title="MRI PELVIS")]
    out = followup.suggest_closures(case, st, docs, by="system")
    a = st["actions"][0]
    assert a["status"] == "pending"  # never closed by itself
    sug = a["suggested_close"]
    assert sug == {"doc_id": "D1", "title": "MRI PELVIS", "doc_type": "mri", "at": "2026-10-12T09:30:00",
                   "reason": "MRI PELVIS (mri) added on 12/10/2026 after the action was created"}
    assert out == [{"event": "suggested", "action_id": "A1", **sug}]
    assert a["history"][-1]["event"].startswith("Closing suggested: MRI PELVIS (mri)") and a["history"][-1]["doc_id"] == "D1"
    sent = _sent(data_root)
    assert len(sent) == 1 and sent[0]["kind"] == "board_action_suggestion" and sent[0]["to"] == {"department": "radiology"}
    assert sent[0]["action_id"] == "A1" and sent[0]["doc_id"] == "D1"
    # the same suggestion found again: nothing new, nobody notified twice
    assert followup.suggest_closures(case, st, docs) == [] and len(_sent(data_root)) == 1


def test_no_suggestion_for_older_document(case, today, data_root):
    st = {"actions": [_act()]}
    assert followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-01T09:00:00")]) == []
    assert "suggested_close" not in st["actions"][0] and _sent(data_root) == []


def test_document_filed_from_intake_counts_when_filed(case, today):
    st = {"actions": [_act()]}
    d = _doc("D1", "mri", "2026-10-01T09:00:00", filed={"case_id": case, "at": "2026-10-10T08:00:00", "how": "confirmed"})
    assert [c["doc_id"] for c in followup.suggest_closures(case, st, [d])] == ["D1"]
    assert st["actions"][0]["suggested_close"]["at"] == "2026-10-10T08:00:00"


def test_no_suggestion_for_other_type_or_document_being_read(case, today):
    st = {"actions": [_act()]}
    docs = [_doc("D1", "ct", "2026-10-12T09:00:00"), _doc("D2", "mri", "2026-10-12T09:00:00", state="queued"),
            _doc("D3", "mri", "2026-10-12T09:00:00", state="processing"), _doc("D4", "mri", "2026-10-12T09:00:00", state="error")]
    assert followup.suggest_closures(case, st, docs) == []
    assert "suggested_close" not in st["actions"][0]


def test_no_suggestion_without_arrival_time(case, today):
    d = _doc("D1", "mri", "")
    d.pop("added")
    assert followup.suggest_closures(case, {"actions": [_act()]}, [d]) == []


def test_no_suggestion_when_task_names_no_document(case, today):
    st = {"actions": [_act(what="Start short-course chemotherapy", dept="Medical Oncology")]}
    assert followup.suggest_closures(case, st, [_doc("D1", "treatment_summary", "2026-10-12T09:00:00")]) == []


def test_confirmed_type_is_what_counts(case, today):
    # callers pass documents through rules.case_docs: the confirmed type sits in classification.doc_type
    d = _doc("D1", "mri", "2026-10-12T09:00:00")
    d["classification"].update(model_doc_type="ct", doc_type_confirmed_by="ravi")
    assert [c["doc_id"] for c in followup.suggest_closures(case, {"actions": [_act()]}, [d])] == ["D1"]


def test_newest_matching_document_wins_and_replaces(case, today, data_root):
    st = {"actions": [_act()]}
    followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-10T09:00:00")])
    docs = [_doc("D1", "mri", "2026-10-10T09:00:00"), _doc("D2", "mri", "2026-10-11T07:00:00")]
    out = followup.suggest_closures(case, st, docs)
    assert [c["doc_id"] for c in out] == ["D2"] and st["actions"][0]["suggested_close"]["doc_id"] == "D2"
    assert len(_sent(data_root)) == 2


def test_only_open_board_actions(case, today):
    st = {"actions": [_act("A1", status="completed"), {**_act("A2"), "source": "pre_authorization", "requirement": "restaging_mri"},
                      _act("A3", status="overdue")]}
    out = followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-12T09:00:00")])
    assert [c["action_id"] for c in out] == ["A3"]
    assert "suggested_close" not in st["actions"][0] and "suggested_close" not in st["actions"][1]


def test_suggestion_withdrawn_when_document_goes(case, today):
    st = {"actions": [_act()]}
    followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-12T09:00:00")])
    out = followup.suggest_closures(case, st, [])
    assert out[0]["event"] == "withdrawn" and out[0]["doc_id"] == "D1"
    assert "suggested_close" not in st["actions"][0] and "withdrawn" in st["actions"][0]["history"][-1]["event"]


def test_unknown_department_suggests_without_notification(case, today, data_root):
    st = {"actions": [_act(dept="Cardiology")]}
    assert len(followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-12T09:00:00")])) == 1
    assert _sent(data_root) == []


def test_suggestion_notification_failure_ignored(case, today, monkeypatch):
    monkeypatch.setattr(notify, "notify", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    st = {"actions": [_act()]}
    assert len(followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-12T09:00:00")])) == 1


# --- dismiss / close -------------------------------------------------------------------------------------------------

def test_dismissed_document_never_suggested_again(case, today):
    st = {"actions": [_act()]}
    docs = [_doc("D1", "mri", "2026-10-12T09:00:00")]
    followup.suggest_closures(case, st, docs)
    ev = followup.dismiss_suggestion(st, "A1", "ravi")
    a = st["actions"][0]
    assert ev == {"kind": "board_action_suggestion_dismissed", "action": "A1", "by": "ravi", "doc_id": "D1"}
    assert a["suggestion_dismissed"] == ["D1"] and "suggested_close" not in a
    assert "Suggestion dismissed by ravi" in a["history"][-1]["event"]
    assert followup.suggest_closures(case, st, docs) == []
    # an older matching document (still after the action) can be suggested next; never the dismissed one
    docs.append(_doc("D0", "mri", "2026-10-10T09:00:00"))
    assert [c["doc_id"] for c in followup.suggest_closures(case, st, docs)] == ["D0"]


def test_dismiss_without_suggestion_or_unknown_action(case):
    st = {"actions": [_act()]}
    with pytest.raises(ValueError):
        followup.dismiss_suggestion(st, "A1", "ravi")
    with pytest.raises(KeyError):
        followup.dismiss_suggestion(st, "A9", "ravi")


def test_close_action_with_suggested_document(case, today):
    st = {"actions": [_act()]}
    followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-12T09:00:00", title="MRI PELVIS")])
    ev = followup.close_action(st, "A1", "ravi", doc_id="D1", note="Restaging MRI received")
    a = st["actions"][0]
    assert a["status"] == "completed" and a["completed"] and a["closed_by"] == "ravi" and a["closed_doc_id"] == "D1"
    assert "suggested_close" not in a
    assert a["history"][-1]["event"] == "Closed by ravi with MRI PELVIS (D1): Restaging MRI received"
    assert ev == {"kind": "board_action_closed", "action": "A1", "by": "ravi", "doc_id": "D1", "note": "Restaging MRI received", "suggested": True}
    with pytest.raises(ValueError):
        followup.close_action(st, "A1", "ravi")


def test_close_action_without_document(case):
    st = {"actions": [_act()]}
    ev = followup.close_action(st, "A1", "anil")
    assert st["actions"][0]["history"][-1]["event"] == "Closed by anil" and ev["doc_id"] is None and ev["suggested"] is False


def test_close_action_refuses_pre_authorization_request(case):
    st = {"actions": [{**_act(), "source": "pre_authorization"}]}
    with pytest.raises(ValueError):
        followup.close_action(st, "A1", "anil")
    with pytest.raises(KeyError):
        followup.close_action(st, "A9", "anil")


# --- end to end through the inbox ------------------------------------------------------------------------------------

def test_inbox_shows_board_action_with_suggestion_then_closed(case, people, today, data_root, monkeypatch):
    monkeypatch.setattr(store, "now_iso", lambda: "2026-10-09T18:00:00")
    st = store.get_state(case)
    st["actions"] = followup.board_actions(case, {"id": "B1a2b3c", "actions": [
        {"task": "MRI pelvis after neoadjuvant chemoradiation", "department": "Radiology", "due": "2026-10-10"}]})
    aid = st["actions"][0]["id"]
    store.save_state(case, st)
    row = notify.inbox(people["radio"])["departments"][0]["requests"][0]
    assert row["action_id"] == aid and row["source"] == "board" and row["source_label"] == "Tumour Board action"
    assert row["board_record"] == "B1a2b3c" and row["overdue"] and row["days_overdue"] == 1 and row["suggested_close"] is None

    st = store.get_state(case)
    followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-10T11:00:00", title="MRI PELVIS")])
    store.save_state(case, st)
    row = notify.inbox(people["radio"])["departments"][0]["requests"][0]
    assert row["suggested_close"]["doc_id"] == "D1" and row["status"] == "overdue"  # suggested, still open until a person closes it

    monkeypatch.setattr(store, "now_iso", lambda: "2026-10-11T10:00:00")
    st = store.get_state(case)
    followup.close_action(st, aid, "ravi", doc_id="D1")
    store.save_state(case, st)
    box = notify.inbox(people["radio"])
    row = box["departments"][0]["requests"][0]
    assert row["status"] == "completed" and row["completed"] == "2026-10-11T10:00:00" and row["suggested_close"] is None
    assert box["open"] == 0
    assert notify.inbox(people["onco"])["departments"][0]["requests"] == []


def test_document_added_in_the_same_second_as_the_action_is_suggested(case, today, data_root):
    # timestamps have one-second resolution: a report filed in the same second as the board record is not "before" it (e2e, 7.4)
    st = {"actions": [_act(created="2026-10-09T18:00:00")]}
    followup.suggest_closures(case, st, [_doc("D1", "mri", "2026-10-09T18:00:00", title="MRI BREAST")])
    assert st["actions"][0]["suggested_close"]["doc_id"] == "D1"
    st = {"actions": [_act(created="2026-10-09T18:00:00")]}
    followup.suggest_closures(case, st, [_doc("D2", "mri", "2026-10-09T17:59:59", title="MRI BREAST")])
    assert "suggested_close" not in st["actions"][0]


def test_board_action_typed_for_the_coordinator_goes_to_the_role(case, today, data_root):
    """Review minor 4: an action typed "MDT Coordinator" (or the V1 "Tumour Board coordination") sits in the coordinator's inbox row."""
    acts = followup.board_actions(case, {"id": "R9", "actions": [{"task": "Send the minutes", "department": "MDT Coordinator"}, {"task": "Old style", "department": "Tumour Board coordination"}]}, by="coord")
    assert all(a["role"] == "coordinator" and a["department_id"] is None and a["department"] == org.COORDINATOR_NAME for a in acts)
    sent = [n for n in notify._load() if n["kind"] == "board_action" and n["to"] == {"role": "coordinator"}]
    assert {n["action_id"] for n in sent} == {a["id"] for a in acts}
