"""notify: in-app notifications and the department inbox (plan item 4.4). Synthetic usernames and Case Files only."""
import copy, json
from datetime import date

import pytest

from tumour_board import config, notify, org, store

TODAY = date(2026, 10, 11)


@pytest.fixture
def people():
    """A radiology member, a pathology member, a radiology head, a coordinator (no department) and an admin."""
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {
        "ravi": {"departments": {"radiology": "member"}},
        "kavya": {"departments": {"pathology": "member"}},
        "suresh": {"departments": {"radiology": "head"}},
        "anil": {"coordinator": True},
    }
    o["admins"] = ["tbadmin"]
    org.save(o, by="test")
    return {"radio": org.roles("ravi"), "path": org.roles("kavya"), "head": org.roles("suresh"),
            "coord": org.roles("anil"), "admin": org.roles("tbadmin")}


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(notify, "_today", lambda: TODAY)
    return TODAY


def _ids(items):
    return [n["id"] for n in items]


# --- notify: validation and storage ----------------------------------------------------------------------------------

def test_notify_stores_and_returns_record(people, data_root):
    n = notify.notify({"department": "radiology"}, "request", "TB-SYN-1", "CT thorax needed",
                      "The Tumour Board Case File needs a final CT report.", action_id="A1", requirement="ct", due="2026-10-14", level=1)
    assert n["id"].startswith("N") and len(n["id"]) == 9
    assert n["to"] == {"department": "radiology"} and n["kind"] == "request" and n["read_by"] == {}
    assert n["action_id"] == "A1" and n["level"] == 1 and n["due"] == "2026-10-14"
    lines = (data_root / "notifications.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["id"] == n["id"]


def test_notify_resolves_department_alias(people):
    n = notify.notify({"department": "Radiology"}, "request", "TB-SYN-1", "t")
    assert n["to"] == {"department": "radiology"}


def test_notify_extra_cannot_override_core_fields(people):
    n = notify.notify({"user": "ravi"}, "case_ready", "TB-SYN-1", "t", read_by={"ravi": "x"}, id="Nevil0000", ts="2000-01-01")
    assert n["read_by"] == {} and n["id"] != "Nevil0000" and n["ts"] != "2000-01-01"


@pytest.mark.parametrize("to", [
    {"department": "cardiology"}, {"department": ""}, {"role": "head"}, {"user": ""}, {"group": "x"},
    {}, {"user": "a", "role": "coordinator"}, "radiology", None,
])
def test_notify_rejects_bad_address(people, to):
    with pytest.raises(ValueError):
        notify.notify(to, "request", "TB-SYN-1", "t")


def test_notify_rejects_unknown_kind(people, data_root):
    with pytest.raises(ValueError):
        notify.notify({"role": "coordinator"}, "reminder", "TB-SYN-1", "t")
    assert not (data_root / "notifications.jsonl").exists()


def test_no_file_means_no_notifications(people):
    assert notify.for_roles(people["admin"]) == [] and notify.unread_count(people["radio"]) == 0
    assert notify.mark_read(people["radio"]) == 0


# --- for_roles -------------------------------------------------------------------------------------------------------

@pytest.fixture
def sent(people):
    return {
        "radio": notify.notify({"department": "radiology"}, "request", "TB-SYN-1", "CT needed")["id"],
        "path": notify.notify({"department": "pathology"}, "request", "TB-SYN-1", "Biopsy report needed")["id"],
        "coord": notify.notify({"role": "coordinator"}, "case_ready", "TB-SYN-1", "Case File ready")["id"],
        "ravi": notify.notify({"user": "ravi"}, "request_closed", "TB-SYN-1", "Request closed")["id"],
    }


def test_member_sees_own_department_not_others(people, sent):
    radio = _ids(notify.for_roles(people["radio"]))
    assert radio == [sent["ravi"], sent["radio"]]  # newest first; addressed to him plus his department
    assert _ids(notify.for_roles(people["path"])) == [sent["path"]]
    assert _ids(notify.for_roles(people["head"])) == [sent["radio"]]


def test_coordinator_sees_role_notifications(people, sent):
    assert _ids(notify.for_roles(people["coord"])) == [sent["coord"]]


def test_admin_sees_every_department_and_role(people, sent):
    got = set(_ids(notify.for_roles(people["admin"])))
    assert got == {sent["radio"], sent["path"], sent["coord"]}  # not another user's personal notification


def test_items_have_read_flag_and_no_read_by(people, sent):
    items = notify.for_roles(people["radio"])
    assert all(i["read"] is False and "read_by" not in i for i in items)


def test_limit_and_unread_only(people, sent):
    assert len(notify.for_roles(people["radio"], limit=1)) == 1
    notify.mark_read(people["radio"], [sent["radio"]])
    assert _ids(notify.for_roles(people["radio"], unread_only=True)) == [sent["ravi"]]


# --- unread_count / mark_read ----------------------------------------------------------------------------------------

def test_mark_read_all(people, sent):
    assert notify.unread_count(people["radio"]) == 2
    assert notify.mark_read(people["radio"]) == 2
    assert notify.unread_count(people["radio"]) == 0
    assert all(i["read"] for i in notify.for_roles(people["radio"]))
    # read is per user: the radiology head still has the department notification unread
    assert notify.unread_count(people["head"]) == 1


def test_mark_read_some(people, sent):
    assert notify.mark_read(people["radio"], [sent["radio"]]) == 1
    assert notify.unread_count(people["radio"]) == 1


def test_mark_read_not_mine_is_ignored(people, sent):
    assert notify.mark_read(people["radio"], [sent["path"], sent["coord"]]) == 0
    assert notify.unread_count(people["path"]) == 1 and notify.unread_count(people["coord"]) == 1


def test_mark_read_idempotent_and_records_user(people, sent, data_root):
    assert notify.mark_read(people["radio"], [sent["radio"]]) == 1
    assert notify.mark_read(people["radio"], [sent["radio"]]) == 0
    assert notify.mark_read(people["radio"], []) == 0
    recs = [json.loads(l) for l in (data_root / "notifications.jsonl").read_text().splitlines()]
    rec = next(r for r in recs if r["id"] == sent["radio"])
    assert set(rec["read_by"]) == {"ravi"}


def test_malformed_line_skipped(people, sent, data_root):
    p = data_root / "notifications.jsonl"
    with open(p, "a") as f:
        f.write("{not json\n\n[1, 2]\n" + json.dumps({"id": "Nbad", "to": "x"}) + "\n")
    n = notify.notify({"department": "radiology"}, "request", "TB-SYN-2", "MRI needed")
    assert _ids(notify.for_roles(people["radio"]))[0] == n["id"]
    assert notify.unread_count(people["radio"]) == 3
    assert notify.mark_read(people["radio"]) == 3


# --- prune -----------------------------------------------------------------------------------------------------------

def test_prune_keeps_newest(people, data_root):
    ids = [notify.notify({"role": "coordinator"}, "case_ready", f"TB-SYN-{i}", "ready")["id"] for i in range(6)]
    assert notify.prune(keep=3) == 3
    assert _ids(notify.for_roles(people["coord"])) == ids[::-1][:3]


def test_prune_drops_old(people, data_root):
    p = data_root / "notifications.jsonl"
    old = {"id": "Nold00001", "ts": "2020-01-01T10:00:00", "to": {"role": "coordinator"}, "kind": "case_ready",
           "case_id": "TB-SYN-0", "title": "old", "text": "", "read_by": {}}
    p.write_text(json.dumps(old) + "\nnot json\n")
    new = notify.notify({"role": "coordinator"}, "case_ready", "TB-SYN-1", "new")
    assert notify.prune() == 1
    assert _ids(notify.for_roles(people["coord"])) == [new["id"]]
    assert len(p.read_text().splitlines()) == 1  # the malformed line is gone too


def test_notify_prunes_occasionally(people, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "prune", lambda *a, **k: calls.append(1) or 0)
    monkeypatch.setattr(notify, "_writes", 0)
    monkeypatch.setattr(notify, "PRUNE_EVERY", 3)
    for _ in range(7):
        notify.notify({"role": "coordinator"}, "case_ready", "TB-SYN-1", "t")
    assert len(calls) == 2


# --- purge_case ------------------------------------------------------------------------------------------------------

def _stored(data_root):
    return [json.loads(l) for l in (data_root / "notifications.jsonl").read_text().splitlines()]


def test_purge_case_removes_only_that_case(people, data_root):
    a = notify.notify({"department": "radiology"}, "request", "TB-1", "CT needed")["id"]
    b = notify.notify({"role": "coordinator"}, "case_ready", "TB-1", "ready")["id"]
    c = notify.notify({"department": "radiology"}, "request", "TB-10", "MRI needed")["id"]  # TB-1 is a prefix
    d = notify.notify({"user": "ravi"}, "request_closed", "TB-SYN-1", "closed")["id"]
    assert notify.purge_case("TB-1") == 2
    assert {r["id"] for r in _stored(data_root)} == {c, d}
    assert a not in _ids(notify.for_roles(people["admin"])) and b not in _ids(notify.for_roles(people["coord"]))


def test_purge_case_idempotent_and_no_rewrite_when_nothing_matches(people, data_root):
    notify.notify({"role": "coordinator"}, "case_ready", "TB-1", "ready")
    notify.notify({"role": "coordinator"}, "case_ready", "TB-2", "ready")
    assert notify.purge_case("TB-1") == 1
    p = data_root / "notifications.jsonl"
    before = (p.read_text(), p.stat().st_mtime_ns)
    assert notify.purge_case("TB-1") == 0
    assert notify.purge_case("tb-2") == 0 and notify.purge_case("") == 0  # exact match only
    assert (p.read_text(), p.stat().st_mtime_ns) == before


def test_purge_case_missing_file(people, data_root):
    assert notify.purge_case("TB-1") == 0
    assert not (data_root / "notifications.jsonl").exists()


def test_purge_case_keeps_read_marks(people, data_root):
    keep = notify.notify({"department": "radiology"}, "request", "TB-2", "CT needed")["id"]
    notify.notify({"department": "radiology"}, "request", "TB-1", "MRI needed")
    assert notify.mark_read(people["radio"], [keep]) == 1
    assert notify.purge_case("TB-1") == 1
    items = notify.for_roles(people["radio"])
    assert _ids(items) == [keep] and items[0]["read"] is True
    assert notify.unread_count(people["head"]) == 1  # read is still per user
    assert set(_stored(data_root)[0]["read_by"]) == {"ravi"}


def test_purge_case_drops_malformed_lines_on_rewrite(people, data_root):
    keep = notify.notify({"role": "coordinator"}, "case_ready", "TB-2", "ready")["id"]
    p = data_root / "notifications.jsonl"
    with open(p, "a") as f:
        f.write("{not json\n")
    notify.notify({"role": "coordinator"}, "case_ready", "TB-1", "ready")
    assert notify.purge_case("TB-1") == 1
    assert [r["id"] for r in _stored(data_root)] == [keep]


# --- inbox -----------------------------------------------------------------------------------------------------------

def _action(aid, dept, due, status="pending", created="2026-10-05T10:00:00", completed=None, **kw):
    return {"id": aid, "source": "pre_authorization", "requirement": "req_" + aid, "label": "Label " + aid,
            "department": dept, "what": "Missing " + aid, "status": status, "created": created, "due": due,
            "completed": completed, "history": [{"ts": created, "event": "Gap detected, routed to " + str(dept)}], **kw}


@pytest.fixture
def cases(people):
    store.create_case("TB-SYN-A", {"name": "SYNTHETIC, Asha Rao", "mrn": "SYN-100001", "agesex": "54 Y / F"}, "lung_nsclc",
                      board_date="2026-10-20", created_by="test")
    store.create_case("TB-SYN-B", {"name": "SYNTHETIC, Prakash Nair", "mrn": "SYN-100002", "agesex": "61 Y / M"}, "rectum",
                      created_by="test")
    st = store.get_state("TB-SYN-A")
    st["actions"] = [
        _action("A1", "Radiology", "2026-10-15", created="2026-10-08T09:00:00", level=1, level_label="Level 1 · Case File"),
        _action("A2", "Pathology", "2026-10-09", created="2026-10-06T09:00:00", level=2, level_label="Level 2 · Records"),
        _action("A3", "Radiology", "2026-10-01", status="completed", completed="2026-10-02T12:00:00"),  # closed 9 days ago
        _action("A4", "Cardiology", "2026-10-01"),  # does not resolve
        {**_action("A5", "Radiology", "2026-10-01"), "source": "other"},  # neither a Pre-Authorization request nor a board action
    ]
    store.save_state("TB-SYN-A", st)
    st = store.get_state("TB-SYN-B")
    st["actions"] = [
        _action("B1", "Radio-diagnosis", "2026-10-10", status="overdue", created="2026-10-07T09:00:00"),
        _action("B2", "", "2026-10-30", created="2026-10-09T09:00:00", department_id="radiology"),
        _action("B3", "Radiology", "2026-10-08", status="completed", created="2026-10-01T09:00:00", completed="2026-10-06T08:00:00"),
        _action("B4", "Radiology", "2026-10-09", status="overdue", created="2026-10-02T09:00:00"),
    ]
    st["actions"][3]["due"] = "2026-10-12"  # stored overdue, due moved later: pending today
    store.save_state("TB-SYN-B", st)
    return ["TB-SYN-A", "TB-SYN-B"]


def _dept(box, did):
    return next(d for d in box["departments"] if d["id"] == did)


def test_inbox_groups_per_visible_department(cases, people, today):
    box = notify.inbox(people["radio"])
    assert [d["id"] for d in box["departments"]] == ["radiology"]
    radio = box["departments"][0]
    assert radio["name"] == "Radiology" and radio["group"] == "supporting"
    assert [q["action_id"] for q in radio["requests"]] == ["B2", "A1", "B1", "B4", "B3"]  # newest first by created
    assert radio["open"] == 4 and radio["overdue"] == 1
    assert box["open"] == 4 and box["overdue"] == 1 and box["generated"]


def test_inbox_request_fields(cases, people, today):
    reqs = {q["action_id"]: q for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    a1 = reqs["A1"]
    assert a1["case_id"] == "TB-SYN-A" and a1["patient"] == {"name": "SYNTHETIC, Asha Rao", "mrn": "SYN-100001", "agesex": "54 Y / F"}
    assert a1["protocol"] == "lung_nsclc" and a1["board_date"] == "2026-10-20"
    assert a1["requirement"] == "req_A1" and a1["label"] == "Label A1" and a1["what"] == "Missing A1"
    assert a1["level"] == 1 and a1["level_label"] == "Level 1 · Case File"
    assert a1["status"] == "pending" and a1["overdue"] is False and a1["days_overdue"] == 0 and a1["due"] == "2026-10-15"
    assert a1["history"] and a1["created"] == "2026-10-08T09:00:00" and a1["completed"] is None
    assert reqs["B2"]["level"] is None and reqs["B2"]["level_label"] == ""  # level fields read with .get()


def test_inbox_overdue_computed_on_display(cases, people, today):
    reqs = {q["action_id"]: q for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    assert reqs["B1"]["status"] == "overdue" and reqs["B1"]["overdue"] and reqs["B1"]["days_overdue"] == 1
    assert reqs["B4"]["status"] == "pending" and not reqs["B4"]["overdue"]
    path = {q["action_id"]: q for q in _dept(notify.inbox(people["path"]), "pathology")["requests"]}
    assert path["A2"]["status"] == "overdue" and path["A2"]["days_overdue"] == 2  # stored pending, due 9 Oct


def test_inbox_overdue_follows_today(cases, people, monkeypatch):
    monkeypatch.setattr(notify, "_today", lambda: date(2026, 10, 20))
    reqs = {q["action_id"]: q for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    assert reqs["A1"]["status"] == "overdue" and reqs["A1"]["days_overdue"] == 5
    assert "B3" not in reqs  # completed 6 Oct: older than 7 days by 20 Oct


def test_inbox_completed_window(cases, people, today):
    reqs = {q["action_id"]: q for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    assert reqs["B3"]["status"] == "completed" and not reqs["B3"]["overdue"]  # closed 5 days ago: shown
    assert "A3" not in reqs  # closed 9 days ago: left out


def test_inbox_unresolved_and_other_sources_left_out(cases, people, today):
    box = notify.inbox(people["admin"])
    all_ids = {q["action_id"] for d in box["departments"] for q in d["requests"]}
    assert "A4" not in all_ids and "A5" not in all_ids


def test_inbox_department_id_on_action(cases, people, today):
    reqs = {q["action_id"] for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    assert "B2" in reqs


def test_inbox_pathology_member(cases, people, today):
    box = notify.inbox(people["path"])
    assert [d["id"] for d in box["departments"]] == ["pathology"]
    assert [q["action_id"] for q in box["departments"][0]["requests"]] == ["A2"]
    assert box["open"] == 1 and box["overdue"] == 1


def test_inbox_coordinator_without_department_sees_only_the_coordinator_row(cases, people, today):
    """V2 item 2.1: the MDT Coordinator is a role; its inbox row holds the actions addressed to the coordinator (none here)."""
    box = notify.inbox(people["coord"])
    assert [(d["id"], d["name"], d["group"], d["requests"]) for d in box["departments"]] == [("coordinator", "MDT Coordinator", None, [])]
    assert box["open"] == 0 and box["overdue"] == 0


def test_inbox_coordinator_row_holds_actions_for_the_coordinator(cases, people, today):
    st = store.get_state("TB-SYN-A")
    st["actions"] += [{**_action("A6", "MDT Coordinator", "2026-10-20", created="2026-10-09T09:00:00"), "role": "coordinator", "department_id": None, "source": "board"},
                      _action("A7", "Tumour Board coordination", "2026-10-21", created="2026-10-09T10:00:00", department_id="tumour_board")]  # stored before the migration
    store.save_state("TB-SYN-A", st)
    row = notify.inbox(people["coord"])["departments"][0]
    assert [q["action_id"] for q in row["requests"]] == ["A7", "A6"] and row["open"] == 2
    assert "coordinator" not in [d["id"] for d in notify.inbox(people["radio"])["departments"]]


def test_inbox_admin_sees_every_department(cases, people, today):
    box = notify.inbox(people["admin"])
    assert [d["id"] for d in box["departments"]] == [d["id"] for d in org.departments()] + ["coordinator"]
    assert box["open"] == 5 and box["overdue"] == 2
    assert _dept(box, "medical_oncology")["requests"] == []


def test_inbox_no_cases(people, today):
    box = notify.inbox(people["radio"])
    assert box["departments"][0]["requests"] == [] and box["open"] == 0


def test_inbox_skips_unreadable_case(cases, people, today, data_root):
    bad = data_root / "cases" / "TB-SYN-BAD"
    bad.mkdir()
    (bad / "case.json").write_text("{broken")
    (data_root / "cases" / "stray.txt").write_text("x")
    assert _dept(notify.inbox(people["radio"]), "radiology")["open"] == 4


def test_inbox_rows_carry_source(cases, people, today):
    reqs = _dept(notify.inbox(people["radio"]), "radiology")["requests"]
    assert all(q["source"] == "pre_authorization" and q["source_label"] == "Pre-Authorization request" for q in reqs)
    assert all("board_record" not in q and "suggested_close" not in q for q in reqs)


# --- inbox: Tumour Board follow-up actions (item 7.4) ----------------------------------------------------------------

def _board(aid, dept, due, status="pending", created="2026-10-09T18:00:00", **kw):
    return {"id": aid, "source": "board", "board_record": "B1a2b3c", "label": "MRI pelvis after neoadjuvant chemoradiation",
            "department": dept, "department_id": org.department_id(dept), "requirement": None,
            "what": "MRI pelvis after neoadjuvant chemoradiation", "status": status, "created": created, "due": due,
            "history": [{"ts": created, "event": "Created from Tumour Board record B1a2b3c"}], **kw}


def test_inbox_lists_board_actions(cases, people, today):
    st = store.get_state("TB-SYN-B")
    st["actions"] += [_board("C1", "Radiology", "2026-10-08"),  # overdue on display, stored pending
                      _board("C2", "Medical Oncology", "2026-10-25", created="2026-10-09T18:01:00"),
                      _board("C3", "Radiology", "2026-10-20", created="2026-10-09T18:02:00",
                             suggested_close={"doc_id": "Dx", "title": "MRI PELVIS", "doc_type": "mri", "at": "2026-10-10T09:00:00",
                                              "reason": "MRI PELVIS (mri) added on 10/10/2026 after the action was created"})]
    store.save_state("TB-SYN-B", st)
    box = notify.inbox(people["admin"])
    radio = {q["action_id"]: q for q in _dept(box, "radiology")["requests"]}
    c1 = radio["C1"]
    assert c1["source"] == "board" and c1["source_label"] == "Tumour Board action" and c1["board_record"] == "B1a2b3c"
    assert c1["status"] == "overdue" and c1["overdue"] and c1["days_overdue"] == 3 and c1["requirement"] is None
    assert c1["suggested_close"] is None
    assert radio["C3"]["suggested_close"]["doc_id"] == "Dx" and radio["C3"]["status"] == "pending"
    assert [q["action_id"] for q in _dept(box, "medical_oncology")["requests"]] == ["C2"]
    assert _dept(box, "radiology")["open"] == 6 and _dept(box, "radiology")["overdue"] == 2
    # Pre-Authorization rows are unchanged next to them
    assert radio["A1"]["source"] == "pre_authorization" and radio["A1"]["status"] == "pending"
    # the radiology member sees the radiology board actions, the pathology member none
    assert {"C1", "C3"} <= {q["action_id"] for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}
    assert not any(q["source"] == "board" for q in _dept(notify.inbox(people["path"]), "pathology")["requests"])


def test_inbox_board_action_completed_window_and_unknown_department(cases, people, today):
    st = store.get_state("TB-SYN-B")
    st["actions"] += [_board("C4", "Radiology", "2026-10-08", status="completed", completed="2026-10-10T10:00:00",
                             suggested_close={"doc_id": "Dx"}),
                      _board("C5", "Radiology", "2026-10-08", status="completed"),  # closed at an unknown time
                      _board("C6", "Cardiology", "2026-10-08")]
    store.save_state("TB-SYN-B", st)
    box = notify.inbox(people["admin"])
    ids = {q["action_id"]: q for d in box["departments"] for q in d["requests"]}
    assert ids["C4"]["status"] == "completed" and ids["C4"]["suggested_close"] is None
    assert "C5" not in ids and "C6" not in ids


def test_inbox_board_action_by_department_name_alias(cases, people, today):
    st = store.get_state("TB-SYN-B")
    st["actions"].append({**_board("C7", "Imaging", "2026-10-30"), "department_id": None})
    store.save_state("TB-SYN-B", st)
    assert "C7" in {q["action_id"] for q in _dept(notify.inbox(people["radio"]), "radiology")["requests"]}


def test_notify_board_kinds(people):
    assert notify.notify({"department": "Medical Oncology"}, "board_action", "TB-SYN-1", "t", board_record="B1")["to"] == {"department": "medical_oncology"}
    assert notify.notify({"department": "radiology"}, "board_action_suggestion", "TB-SYN-1", "t")["kind"] == "board_action_suggestion"
