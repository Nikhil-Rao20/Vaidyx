"""dept_requests (V2 items 4.2 / 4.3): the gate suggests, the treating doctor sends (in-app, mail draft), the department acknowledges and
answers, a gap request closes itself when the record arrives, a free request closes on "done" or by the owner. Small test protocol
`unit`, synthetic Case File, no model, no network."""
import copy
import json
import urllib.parse
from datetime import date, timedelta

import pytest

from tumour_board import dept_requests, metrics, notify, org, rules, store
from tumour_board.tests.test_rules import ct, hist
from tumour_board.tests.util import add, fact


@pytest.fixture
def people(data_root):
    """A Breast Surgery doctor (treating), a Radiology doctor and head (supporting), an Anaesthesiology doctor, a coordinator, a root admin and a Vaidyx admin."""
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"meera": {"departments": {"breast_surgery": "member"}}, "ravi": {"departments": {"radiology": "member"}},
                  "suresh": {"departments": {"radiology": "head"}}, "arun": {"departments": {"anaesthesiology": "member"}},
                  "anil": {"coordinator": True}, "root": {}}
    o["admins"] = ["root"]
    org.save(o, by="test")
    return {k: org.roles(k) for k in ("meera", "ravi", "suresh", "arun", "anil", "root")} | {"admin": org.roles("tbadmin", vaidyx_admin=True)}


def _notes(kind=None):
    p = notify.path()
    recs = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    return [x for x in recs if kind is None or x["kind"] == kind]


def _sync(case_id):
    return rules.sync_actions(case_id, rules.evaluate(case_id))


def _own(case_id, dept="breast_surgery", ids=True, his=False):
    c = store.get_case(case_id)
    c["department"] = dept
    if ids:
        c["patient"]["ids"] = [{"kind": "ip_no", "value": "IP/26/00001"}, {"kind": "op_no", "value": "OP/26/000001"}]
    if his:
        c["his"] = {"uhid": c["patient"].get("mrn"), "label": "mock"}
    store.save_case(c)
    return c


def _first(case_id):
    return _sync(case_id)["actions"][0]


# ---- suggested, not sent ------------------------------------------------------------------------------------------

def test_the_gate_suggests_a_request_and_sends_nothing(unit_case, people):
    add(unit_case, hist())
    a = _first(unit_case)
    assert (a["requirement"], a["department"], a["status"], a["due"], a["sla_days"]) == ("ct_thorax", "Radiology", "suggested", None, 3)
    assert a["history"][0]["event"].endswith("request to Radiology suggested (not sent)")
    assert _notes("request") == []
    assert [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]] == []  # a suggestion is in no inbox
    assert dept_requests.summary(store.get_state(unit_case)) == {"suggested": 1, "sent": 0, "done": 0, "closed": 0}
    assert any(e["kind"] == "action_created" and e["status"] == "suggested" for e in store.read_audit(unit_case))


def test_an_unsent_request_closes_silently_when_the_record_arrives(unit_case, people):
    add(unit_case, hist())
    _first(unit_case)
    add(unit_case, ct())
    a = _first(unit_case)
    assert a["status"] == "completed" and _notes("request_closed") == []


def test_draft_carries_the_patient_identifiers_the_accession_and_the_due_date(unit_case, people):
    c = _own(unit_case)
    add(unit_case, hist())
    st = _sync(unit_case); a = st["actions"][0]
    a["accession"] = "RAD/26/00001"; a["pending_order"] = {"stage": "scheduled"}; store.save_state(unit_case, st)
    d = dept_requests.draft(c, a, "meera")
    due = (date.today() + timedelta(days=3)).isoformat()
    assert d["to"] == {"department": "radiology", "name": "Radiology", "email": org.department_email("radiology"), "role": None}
    assert d["due"] == due and d["uhid"] == c["patient"]["mrn"] and d["encounter"] == {"ip_no": "IP/26/00001", "op_no": "OP/26/000001"} and d["accession"] == "RAD/26/00001"
    body = d["body"]
    assert body.startswith("To: Radiology\nTumour Board Case File TB-UNIT\nPatient: ")
    assert f"UHID {c['patient']['mrn']}" in body and "IP No. IP/26/00001" in body and "OP No. OP/26/000001" in body and "Treating department: Breast Surgery" in body
    assert "Required record: Diagnostic CT thorax report (Level 1: Case File)" in body and "Accession / order No.: RAD/26/00001 (scheduled in the hospital system)" in body
    assert f"Needed by: {date.fromisoformat(due).strftime('%d/%m/%Y')}" in body and "final, signed report" in body
    assert d["subject"].startswith("Tumour Board Case File TB-UNIT: Diagnostic CT thorax report for ")
    assert d["mailto"].startswith(f"mailto:{org.department_email('radiology')}?subject=") and "body=" in d["mailto"]
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(d["mailto"]).query)
    assert q["subject"] == [d["subject"]] and q["body"] == [body]
    assert d["free"] is False and d["sent"] is None and d["status"] == "suggested"


def test_no_mailto_without_a_department_address(unit_case, people):
    assert dept_requests.mailto({"department": "radiology", "name": "Radiology", "email": ""}, "s", "b") == ""


# ---- sending ---------------------------------------------------------------------------------------------------------

def test_send_opens_the_request_notifies_the_department_and_audits(unit_case, people):
    c = _own(unit_case)
    add(unit_case, hist())
    a0 = _first(unit_case)
    a = dept_requests.send(unit_case, a0["id"], "meera", people["meera"], message="", due="")
    today = date.today()
    assert a["status"] == "pending" and a["due"] == (today + timedelta(days=3)).isoformat()
    assert a["sent"]["by"] == "meera" and a["sent"]["to"] == "radiology" and a["sent"]["count"] == 1 and a["sent"]["channel"] == "in_app"
    assert a["sent"]["message"].rstrip().endswith("Sent by meera (Breast Surgery) through the Tumour Board.")
    assert a["history"][-1]["event"].startswith("Sent to Radiology by meera, due ")
    n = _notes("request")
    assert len(n) == 1 and n[0]["to"] == {"department": "radiology"} and n[0]["action_id"] == a["id"] and n[0]["uhid"] == c["patient"]["mrn"]
    assert n[0]["message"] == a["sent"]["message"] and n[0]["sent_by"] == "meera" and n[0]["reminder"] is False and n[0]["encounter"]["ip_no"] == "IP/26/00001"
    assert a["sent"]["notification_id"] == n[0]["id"]
    au = [e for e in store.read_audit(unit_case) if e["kind"] == "request_sent"]
    assert len(au) == 1 and au[0]["department"] == "Radiology" and au[0]["by"] == "meera" and au[0]["reminder"] is False
    rows = [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]]
    assert len(rows) == 1 and rows[0]["status"] == "pending" and rows[0]["uhid"] == c["patient"]["mrn"] and rows[0]["sent"]["by"] == "meera" and rows[0]["acknowledged"] is None
    assert rows[0]["encounter"] == {"ip_no": "IP/26/00001", "op_no": "OP/26/000001"} and rows[0]["free"] is False
    assert dept_requests.summary(store.get_state(unit_case)) == {"suggested": 0, "sent": 1, "done": 0, "closed": 0}
    # the draft of a sent request keeps its due date; sending again is a reminder
    assert dept_requests.draft(c, a, "meera")["due"] == a["due"]
    a2 = dept_requests.send(unit_case, a["id"], "meera", people["meera"], message="Please expedite.\n", due="")
    assert a2["sent"]["count"] == 2 and a2["sent"]["message"].startswith("Please expedite.") and "Sent by meera" in a2["sent"]["message"]
    assert a2["history"][-1]["event"].startswith("Sent again to Radiology by meera")
    n = _notes("request")
    assert len(n) == 2 and n[1]["reminder"] is True and n[1]["title"].endswith("(reminder)")


def test_send_with_an_edited_message_due_date_and_subject(unit_case, people):
    _own(unit_case)
    add(unit_case, hist())
    a0 = _first(unit_case)
    far = (date.today() + timedelta(days=10)).isoformat()
    a = dept_requests.send(unit_case, a0["id"], "meera", people["meera"], message="CT thorax needed before the board, please.", due=far, subject_text="CT for TB-UNIT")
    assert a["due"] == far and a["status"] == "pending" and a["sent"]["subject"] == "CT for TB-UNIT"
    with pytest.raises(dept_requests.RequestError):
        dept_requests.send(unit_case, a0["id"], "meera", people["meera"], due="31/12/2026")
    past = (date.today() - timedelta(days=1)).isoformat()
    assert dept_requests.send(unit_case, a0["id"], "meera", people["meera"], due=past)["status"] == "overdue"


def test_send_refuses_a_closed_request_a_board_action_and_an_unknown_one(unit_case, people):
    add(unit_case, hist())
    a0 = _first(unit_case)
    st = store.get_state(unit_case)
    st["actions"].append({"id": "B1", "source": "board", "status": "pending", "label": "MRI", "department": "Radiology", "history": []})
    store.save_state(unit_case, st)
    with pytest.raises(dept_requests.RequestError) as e:
        dept_requests.send(unit_case, "B1", "meera", people["meera"])
    assert e.value.status == 409
    with pytest.raises(dept_requests.RequestError) as e:
        dept_requests.send(unit_case, "nope", "meera", people["meera"])
    assert e.value.status == 404
    add(unit_case, ct()); _sync(unit_case)
    with pytest.raises(dept_requests.RequestError) as e:
        dept_requests.send(unit_case, a0["id"], "meera", people["meera"])
    assert e.value.status == 409 and "closed" in str(e.value)


def test_a_sent_request_closes_itself_and_the_department_is_told(unit_case, people):
    _own(unit_case)
    add(unit_case, hist())
    a = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    add(unit_case, ct())
    st = _sync(unit_case)
    assert st["actions"][0]["status"] == "completed" and st["gate"]["passed"]
    closed = _notes("request_closed")
    assert len(closed) == 1 and closed[0]["to"] == {"department": "radiology"} and closed[0]["action_id"] == a["id"]
    rows = [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]]
    assert len(rows) == 1 and rows[0]["status"] == "completed"


def test_a_sent_request_that_moves_becomes_a_suggestion_again(unit_case, people):
    """The CT arrives from Nuclear Medicine without the lesion size: the Level 2 gap goes to that department. The sent Level 1 request
    is not forwarded by itself: Radiology is told it moved, the sending is kept under `earlier`, the doctor sends the new one."""
    _own(unit_case)
    add(unit_case, hist())
    a = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    add(unit_case, {**ct(facts={}), "department": "nuclear_medicine"})
    a = _first(unit_case)
    assert (a["level"], a["department_id"], a["status"], a["due"]) == (2, "nuclear_medicine", "suggested", None)
    assert "sent" not in a and a["earlier"][0]["department_id"] == "radiology" and a["earlier"][0]["sent"]["by"] == "meera"
    assert a["history"][-1]["event"] == "Re-check: Level 2: Records routed to Nuclear Medicine (sent to Radiology earlier: send it again)"
    assert [x["to"] for x in _notes("request")] == [{"department": "radiology"}]  # nothing went to Nuclear Medicine by itself
    moved = _notes("request_closed")
    assert len(moved) == 1 and moved[0]["to"] == {"department": "radiology"} and "moved to Nuclear Medicine" in moved[0]["title"]
    assert [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]] == []  # not shown to Radiology any more (suggested)


def test_an_unsent_request_that_moves_tells_nobody(unit_case, people):
    add(unit_case, hist())
    _first(unit_case)
    add(unit_case, {**ct(facts={}), "department": "nuclear_medicine"})
    a = _first(unit_case)
    assert a["status"] == "suggested" and "earlier" not in a and _notes() == []
    assert a["history"][-1]["event"].endswith("routed to Nuclear Medicine (suggested, not sent)")


def test_a_v1_pending_request_counts_as_sent(unit_case, people):
    """A request opened before 4.2 (status pending, no `sent`) was notified at once: it still closes with a notice and moves as sent."""
    add(unit_case, hist())
    st = _sync(unit_case); st["actions"][0]["status"] = "pending"; st["actions"][0]["due"] = date.today().isoformat(); store.save_state(unit_case, st)
    rows = [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]]
    assert len(rows) == 1 and rows[0]["sent"] is None
    add(unit_case, ct()); _sync(unit_case)
    assert len(_notes("request_closed")) == 1


# ---- free requests ----------------------------------------------------------------------------------------------------

def test_a_free_request_is_created_and_sent_in_one_step_and_closes_on_done(unit_case, people):
    _own(unit_case)
    a = dept_requests.create_free(unit_case, "Anaesthesiology", "Pre-anaesthetic check-up", "meera", people["meera"], what="Planned for surgery next week")
    assert a["origin"] == "doctor" and a["requirement"] is None and a["status"] == "pending" and a["department_id"] == "anaesthesiology" and dept_requests.is_free(a)
    assert a["due"] == (date.today() + timedelta(days=3)).isoformat() and a["sent"]["by"] == "meera"
    assert "Request: Pre-anaesthetic check-up" in a["sent"]["message"] and "Details: Planned for surgery next week" in a["sent"]["message"]
    assert [e["kind"] for e in store.read_audit(unit_case) if e["kind"].startswith("request_")] == ["request_created", "request_sent"]
    rows = [q for d in notify.inbox(people["arun"])["departments"] for q in d["requests"]]
    assert len(rows) == 1 and rows[0]["free"] is True and rows[0]["requirement"] is None
    d = dept_requests.done(unit_case, a["id"], "arun", note="PAC done, fit for surgery")
    assert d["status"] == "completed" and d["done"]["note"] == "PAC done, fit for surgery" and d["acknowledged"]["implied"] is True and d["closed_by"] == "arun"
    told = _notes("request_done")
    assert len(told) == 1 and told[0]["to"] == {"department": "breast_surgery"} and told[0]["closed"] is True and "The request is closed." in told[0]["text"]
    with pytest.raises(dept_requests.RequestError):
        dept_requests.create_free(unit_case, "No Such Department", "x", "meera", people["meera"])
    with pytest.raises(dept_requests.RequestError):
        dept_requests.create_free(unit_case, "Radiology", "   ", "meera", people["meera"])


def test_the_owner_closes_a_free_request_but_never_a_gap_request(unit_case, people):
    _own(unit_case)
    add(unit_case, hist())
    gap = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    with pytest.raises(dept_requests.RequestError) as e:
        dept_requests.close_free(unit_case, gap["id"], "meera")
    assert e.value.status == 409 and "waive" in str(e.value)
    free = dept_requests.create_free(unit_case, "Clinical Pharmacology", "Medication review", "meera", people["meera"])
    a = dept_requests.close_free(unit_case, free["id"], "meera", note="not needed after all")
    assert a["status"] == "completed" and a["closed_by"] == "meera"
    assert any(e["kind"] == "request_closed_by_owner" for e in store.read_audit(unit_case))
    assert _notes("request_closed")[-1]["to"] == {"department": "clinical_pharmacology"}


# ---- acknowledge and done (4.3) ------------------------------------------------------------------------------------------

def test_acknowledge_and_done_on_a_gap_request_keep_it_open_until_the_record_arrives(unit_case, people):
    _own(unit_case, his=True)
    add(unit_case, hist())
    a0 = _first(unit_case)
    with pytest.raises(dept_requests.RequestError) as e:
        dept_requests.acknowledge(unit_case, a0["id"], "ravi")
    assert e.value.status == 409 and "not been sent" in str(e.value)
    a = dept_requests.send(unit_case, a0["id"], "meera", people["meera"])
    assert "Re-fetch" not in a["sent"]["message"] and "re-fetched from the hospital system" in a["sent"]["message"]
    a = dept_requests.acknowledge(unit_case, a["id"], "ravi")
    assert a["acknowledged"]["by"] == "ravi" and a["status"] == "pending"
    told = _notes("request_acknowledged")
    assert len(told) == 1 and told[0]["to"] == {"department": "breast_surgery"} and told[0]["action_id"] == a["id"]
    with pytest.raises(dept_requests.RequestError):
        dept_requests.acknowledge(unit_case, a["id"], "suresh")
    a = dept_requests.done(unit_case, a["id"], "suresh", note="Signed in the RIS")
    assert a["status"] == "pending" and a["done"] == {"by": "suresh", "at": a["done"]["at"], "note": "Signed in the RIS"}
    told = _notes("request_done")
    assert len(told) == 1 and told[0]["refetch_offer"] is True and told[0]["closed"] is False and "Re-fetch from the hospital system" in told[0]["text"]
    rows = [q for d in notify.inbox(people["ravi"])["departments"] for q in d["requests"]]
    assert rows[0]["done"]["by"] == "suresh" and rows[0]["acknowledged"]["by"] == "ravi"
    assert dept_requests.summary(store.get_state(unit_case)) == {"suggested": 0, "sent": 1, "done": 1, "closed": 0}
    with pytest.raises(dept_requests.RequestError):
        dept_requests.done(unit_case, a["id"], "ravi")
    assert [e["kind"] for e in store.read_audit(unit_case) if e["kind"] in ("request_acknowledged", "request_done")] == ["request_acknowledged", "request_done"]
    add(unit_case, ct())
    assert _first(unit_case)["status"] == "completed"  # the re-check closes it (V1 rule; on a re-fetch the same path runs)


def test_done_without_a_his_connection_says_the_request_closes_when_the_record_reaches_the_case_file(unit_case, people):
    _own(unit_case)
    add(unit_case, hist())
    a = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    dept_requests.done(unit_case, a["id"], "ravi")
    told = _notes("request_done")[0]
    assert told["refetch_offer"] is False and "closes when the record reaches the Case File" in told["text"]


def test_the_owner_is_the_sender_when_the_case_file_has_no_department(unit_case, people):
    add(unit_case, hist())
    a = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    dept_requests.acknowledge(unit_case, a["id"], "ravi")
    assert _notes("request_acknowledged")[0]["to"] == {"user": "meera"}


# ---- permissions and metrics --------------------------------------------------------------------------------------------

def test_permissions_follow_the_v2_roles(people):
    t, s, h, an, co, ro, ad = (people[k] for k in ("meera", "ravi", "suresh", "arun", "anil", "root", "admin"))
    assert org.can(t, "send_request") and org.can(t, "create_request") and org.can(t, "close_request")
    assert not any(org.can(r, "send_request") for r in (s, h, an, co, ro))
    assert not any(org.can(r, "create_request") for r in (s, h, an, co, ro))
    assert org.can(s, "answer_request", "Radiology") and org.can(h, "answer_request", "radiology") and not org.can(s, "answer_request", "Pathology")
    assert not org.can(t, "answer_request", "Radiology") and not org.can(co, "answer_request", "Radiology") and not org.can(ro, "answer_request", "Radiology")
    assert not org.can(s, "answer_request", None) and not org.can(s, "answer_request", "MDT Coordinator")
    assert all(org.can(ad, x, "Radiology") for x in ("send_request", "create_request", "answer_request", "close_request"))


def test_readiness_counts_suggested_requests_as_unsent(unit_case, people):
    _own(unit_case)
    c = store.get_case(unit_case); c["board_date"] = (date.today() + timedelta(days=14)).isoformat(); store.save_case(c)
    add(unit_case, hist())
    a = _first(unit_case)
    row = metrics._case_readiness(c, store.get_state(unit_case), date.today(), date.fromisoformat(c["board_date"]))
    assert (row["open_requests"], row["unsent_requests"], row["overdue"], row["forecast"]) == (1, 1, 0, "on_track") and row["why"] == "1 suggested request(s) not sent yet"
    ag = metrics.agenda(c["board_date"])
    assert ag["requests_open"] == 1 and ag["requests_unsent"] == 1 and ag["chase"][0]["items"][0]["unsent"] is True and ag["chase"][0]["items"][0]["due"] is None
    dept_requests.send(unit_case, a["id"], "meera", people["meera"])
    row = metrics._case_readiness(c, store.get_state(unit_case), date.today(), date.fromisoformat(c["board_date"]))
    assert (row["unsent_requests"], row["forecast"], row["why"]) == (0, "on_track", "1 request(s) open, all due before the board")
    c["board_date"] = (date.today() + timedelta(days=2)).isoformat(); store.save_case(c)
    add(unit_case, {**ct(facts={}), "department": "nuclear_medicine"}); _first(unit_case)  # moved: suggested again, the board is in two days
    row = metrics._case_readiness(c, store.get_state(unit_case), date.today(), date.fromisoformat(c["board_date"]))
    assert row["forecast"] == "at_risk" and row["unsent_requests"] == 1


# ---- closures of unsent requests and the re-fetch notice (4.3 / 4.4) -----------------------------------------------------

def test_a_request_closed_while_still_suggested_never_shows_in_an_inbox(unit_case, people):
    add(unit_case, hist())
    _first(unit_case)
    add(unit_case, ct())
    a = _first(unit_case)
    assert a["status"] == "completed" and a["never_sent"] is True
    assert [q for d in notify.inbox(people["admin"])["departments"] for q in d["requests"] if q["case_id"] == unit_case] == []


def test_after_refetch_reports_requests_closed_and_a_stale_summary(unit_case, people):
    from tumour_board import his_case
    _own(unit_case, his=True)
    add(unit_case, hist())
    a = dept_requests.send(unit_case, _first(unit_case)["id"], "meera", people["meera"])
    st = store.get_state(unit_case)
    st["artefacts"] = {"summary": {"paragraphs": [], "signature": rules.case_signature(unit_case, st)}}  # compiled before the re-fetch
    store.save_state(unit_case, st)
    add(unit_case, ct()); _sync(unit_case)  # what a re-fetch does: the record arrives, the gate re-runs
    job = {"id": "J1", "open_before": [a["id"]], "his": {"added": 1}}
    his_case.after_refetch(unit_case, job)
    res = job["refetch_result"]
    assert res["closed"] == [a["id"]] and res["opened"] == [] and res["summary_stale"].startswith("The Case File changed since this was generated: 1 document added")
    told = [n for n in _notes("request_closed") if n.get("refetch")]
    assert len(told) == 1 and told[0]["to"] == {"department": "breast_surgery"} and told[0]["summary_stale"] == res["summary_stale"]
    assert "1 request(s) closed: Diagnostic CT thorax report" in told[0]["title"] and "the Case File is ready" in told[0]["text"] and "summary compiled earlier is stale" in told[0]["text"]
    assert any(e["kind"] == "his_refetch_checked" and e["closed"][0]["id"] == a["id"] for e in store.read_audit(unit_case))


def test_after_refetch_says_nothing_when_nothing_changed(unit_case, people):
    from tumour_board import his_case
    _own(unit_case, his=True)
    add(unit_case, hist()); a = _first(unit_case)
    job = {"id": "J2", "open_before": [a["id"]], "his": {"added": 0}}
    his_case.after_refetch(unit_case, job)
    assert job["refetch_result"] == {"closed": [], "opened": [], "summary_stale": ""} and _notes("request_closed") == []
    job = {"id": "J3", "open_before": [], "his": {"added": 0}}  # a suggestion that appeared with this re-fetch counts as opened
    his_case.after_refetch(unit_case, job)
    assert job["refetch_result"]["opened"] == [a["id"]] and _notes("request_closed") == []
