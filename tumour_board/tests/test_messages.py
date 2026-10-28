"""Messages between logins (night-v3 item 8.1, contract docs/night-v3/research/06_messages.md section 9): who may use them, direct,
department and MDT Coordinator conversations, unread per person and the badge, edit and delete within 10 minutes, resolve and reopen,
a Case File link grants nothing, the bell and push texts carry no message text and no patient detail, limits, storage, retention, and
no account is ever changed. Synthetic logins and Case Files only; the clock is messages._now."""
import copy, json, os, stat, threading
from datetime import datetime, timedelta

import pytest

from tumour_board import access, config, live, messages, notify, org, push, store
from tumour_board.api import common
from tumour_board.api import messages as api_messages
from tumour_board.tests import test_nik_meetings as tnm
from tumour_board.tests.test_nik_meetings import As, app, tc, new_meeting, owned  # noqa: F401  (fixtures and helpers)
from tumour_board.tests.test_nik_push import SUB, sent  # noqa: F401  (the push fixture)

T0 = datetime(2026, 10, 28, 10, 0, 0)
NAME = "SYNTHETIC, Lakshmi Iyer"  # the fixture patient of TB-002
UHID = "VXH/2026/004217"
TEXT = "Please see the MRI of Lakshmi Iyer, UHID VXH/2026/004217, before Friday."


class P(As):
    def patch(self, path, json=None, **kw):
        self._c(); return self.tc.patch("/api/tb" + path, json=json if json is not None else {}, **kw)


@pytest.fixture(autouse=True)
def _fresh():
    for n in api_messages.LIMITS:
        getattr(api_messages, n)._hits.clear()
    live.messages_hub.clear()
    messages._PUSHED.clear()
    messages._DENIED.clear()
    messages._cache.clear()
    from tumour_board.api import messages_ws
    messages_ws.clear()
    yield
    live.messages_hub.clear()


@pytest.fixture
def clock(monkeypatch):
    t = {"now": T0}
    monkeypatch.setattr(messages, "_now", lambda: t["now"])
    return t


def change_org(fn):
    o = copy.deepcopy(org.load())
    fn(o)
    org.save(o, by="test")


def add_user(monkeypatch, login, rec):
    monkeypatch.setitem(tnm.TOKENS, f"tok-{login}", login)
    change_org(lambda o: o["users"].__setitem__(login, rec))


def start(tc, by, to, text="Please see the report.", **kw):
    r = As(tc, by).post("/messages/conversations", json={"to": to, "text": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def audit_lines(data_root):
    p = data_root / "org_audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


# ---- who may use Messages ---------------------------------------------------------------------------------------------------------

def test_placed_logins_may_message_a_person_a_department_and_the_coordinator(tc):
    d = start(tc, "priya", {"user": "ravi"})
    assert d["conversation"]["kind"] == "direct" and d["conversation"]["title"] == "Dr Ravi" and d["message"]["by_name"] == "Dr Priya Nair"
    assert d["conversation"]["with"]["user"] == "ravi" and "Radiology" in d["conversation"]["subtitle"]
    assert d["message"]["text"] == "Please see the report." and d["message"]["can_edit_until"]
    dep = start(tc, "priya", {"department": "radiology"})
    assert dep["conversation"]["kind"] == "department" and dep["conversation"]["title"] == "Radiology"
    assert dep["conversation"]["subtitle"] == "Reaches 2 people" and dep["conversation"]["department"]["members"] == 2
    co = start(tc, "priya", {"role": "coordinator"})
    assert co["conversation"]["title"] == "MDT Coordinator" and co["conversation"]["subtitle"] == "Reaches 1 coordinator"
    assert As(tc, "anil").get(f"/messages/conversations/{co['conversation']['id']}").status_code == 200  # the coordinator reads it
    assert As(tc, "anil").get("/messages/conversations").json()["conversations"][0]["subtitle"] == "From Dr Priya Nair"
    # the same target again adds to the existing conversation
    again = start(tc, "priya", {"user": "ravi"}, text="One more thing.")
    assert again["conversation"]["id"] == d["conversation"]["id"]
    assert start(tc, "ravi", {"user": "priya"})["conversation"]["id"] == d["conversation"]["id"]  # the pair in any order


@pytest.mark.parametrize("login", ["tbroot", "guest", "admin", "audrey"])
def test_unplaced_logins_get_403_not_placed(tc, monkeypatch, login):
    add_user(monkeypatch, "audrey", {"auditor": True, "display_name": "Audrey Auditor"})
    for call in (lambda a: a.get("/messages/conversations"), lambda a: a.get("/messages/unread"),
                 lambda a: a.post("/messages/conversations", json={"to": {"user": "priya"}, "text": "Hello"})):
        r = call(As(tc, login))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "not_placed", (login, r.text)
        assert r.json()["detail"]["message"] == "Messages are for placed hospital staff."


def test_disabled_and_expired_logins_get_403(tc):
    change_org(lambda o: (o["users"]["ravi"].__setitem__("disabled", True), o["users"]["asha"].__setitem__("end_date", "2020-01-01")))
    for login in ("ravi", "asha"):
        assert As(tc, login).get("/messages/conversations").status_code == 403
    r = As(tc, "priya").post("/messages/conversations", json={"to": {"user": "ravi"}, "text": "Hello"})  # cannot be reached either
    assert r.status_code == 400 and r.json()["detail"] == {"message": "That person cannot be reached.", "code": "cannot_reach"}


def test_refusals_for_targets(tc):
    def post(by, to):
        return As(tc, by).post("/messages/conversations", json={"to": to, "text": "Hello"})
    assert post("priya", {"user": "priya"}).json()["detail"]["code"] == "self_message"
    assert post("anil", {"role": "coordinator"}).json()["detail"]["code"] == "self_message"
    unknown, root = post("priya", {"user": "nobody"}), post("priya", {"user": "tbroot"})
    assert unknown.status_code == root.status_code == 400 and unknown.json() == root.json()  # the same words for an unknown login
    assert post("priya", {"user": "guest"}).json()["detail"]["code"] == "cannot_reach"
    assert post("priya", {"department": "no_such_department"}).json()["detail"]["code"] == "cannot_reach"
    assert post("priya", {"department": "nuclear_medicine"}).json()["detail"]["code"] == "cannot_reach"  # nobody placed there
    assert post("priya", {"role": "head"}).json()["detail"]["code"] == "cannot_reach"
    assert As(tc, "priya").get("/messages/conversations").json()["conversations"] == []  # nothing was created


def test_a_direct_conversation_is_only_for_its_two_people(tc, data_root):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    for login in ("anil", "meena", "suresh"):  # the coordinator has no reading right; nor another radiologist
        r = As(tc, login).get(f"/messages/conversations/{cid}")
        assert r.status_code == 404 and r.json()["detail"] == {"message": "No such conversation.", "code": "not_found"}
        assert As(tc, login).post(f"/messages/conversations/{cid}/messages", json={"text": "Me too"}).status_code == 404
        assert As(tc, login).get("/messages/conversations").json()["conversations"] == []
    unknown = As(tc, "meena").get("/messages/conversations/C0123456789")
    assert unknown.status_code == 404 and unknown.json() == As(tc, "meena").get(f"/messages/conversations/{cid}").json()
    assert As(tc, "meena").get("/messages/conversations/c_x.jsonl").json() == unknown.json()  # a malformed id: the same 404
    a, b = As(tc, "tbroot").get(f"/messages/conversations/{cid}"), As(tc, "tbroot").get("/messages/conversations/C0123456789")
    assert a.status_code == b.status_code == 403 and a.json() == b.json()  # the root admin is not placed: nothing to tell apart
    denied = [e for e in audit_lines(data_root) if e["kind"] == "message_denied"]
    assert {e["by"] for e in denied} == {"anil", "meena", "suresh", "tbroot"}
    assert len([e for e in denied if e["by"] == "meena"]) == 1  # at most once a minute per login


# ---- departments --------------------------------------------------------------------------------------------------------------------

def test_a_department_conversation_is_a_shared_mailbox(tc, monkeypatch):
    cid = start(tc, "priya", {"department": "radiology"}, text="Can someone review the staging CT?")["conversation"]["id"]
    for login in ("ravi", "suresh"):
        rows = As(tc, login).get("/messages/conversations").json()["conversations"]
        assert [x["id"] for x in rows] == [cid] and rows[0]["unread"] == 1 and rows[0]["subtitle"] == "From Dr Priya Nair"
    assert As(tc, "meena").get(f"/messages/conversations/{cid}").status_code == 404
    r = As(tc, "ravi").post(f"/messages/conversations/{cid}/messages", json={"text": "I will look at it today."})
    assert r.status_code == 200
    for login in ("priya", "suresh"):
        msgs = As(tc, login).get(f"/messages/conversations/{cid}").json()["messages"]
        assert [m["by"] for m in msgs] == ["priya", "ravi"]
    # a member added later sees the history
    add_user(monkeypatch, "nisha", {"departments": {"radiology": "resident"}, "display_name": "Dr Nisha"})
    view = As(tc, "nisha").get(f"/messages/conversations/{cid}").json()
    assert len(view["messages"]) == 2 and {x["user"] for x in view["readers"]} == {"priya", "ravi", "suresh", "nisha"}
    # a member who leaves loses it; an expired one may not use Messages at all
    change_org(lambda o: o["users"]["ravi"].__setitem__("departments", {"pathology": "member"}))
    assert As(tc, "ravi").get(f"/messages/conversations/{cid}").status_code == 404
    change_org(lambda o: o["users"]["suresh"].__setitem__("end_date", "2020-01-01"))
    assert As(tc, "suresh").get(f"/messages/conversations/{cid}").status_code == 403
    assert {x["user"] for x in As(tc, "priya").get(f"/messages/conversations/{cid}").json()["readers"]} == {"priya", "nisha"}


# ---- unread, the badge, the bell, mute --------------------------------------------------------------------------------------------

def bell(login):
    return [n for n in notify.for_roles(org.roles(login), limit=None) if n.get("kind") == "message"]


def test_unread_per_person_badge_and_one_bell_item(tc):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "Second note."})
    assert As(tc, "ravi").get("/me").json()["counts"]["messages_unread"] == 2
    assert As(tc, "ravi").get("/messages/unread").json() == {"unread_total": 2}
    assert As(tc, "priya").get("/messages/unread").json() == {"unread_total": 0}  # your own messages never count
    items = bell("ravi")
    assert len(items) == 1 and items[0]["title"] == "New message from Dr Priya Nair" and items[0]["text"] == "" and items[0]["case_id"] == ""
    assert items[0]["conversation"] == cid and items[0]["read"] is False
    assert bell("priya") == [] and bell("anil") == []
    view = As(tc, "ravi").get(f"/messages/conversations/{cid}").json()
    assert view["conversation"]["unread"] == 2  # opening does not mark read
    last = view["messages"][-1]["seq"]
    r = As(tc, "ravi").post(f"/messages/conversations/{cid}/read", json={"seq": last + 50})
    assert r.json() == {"unread_total": 0} and bell("ravi")[0]["read"] is True
    assert As(tc, "priya").get(f"/messages/conversations/{cid}").json()["seen_seq"] == last  # never past the last message
    # mute: the count still grows, no new bell item
    assert As(tc, "ravi").post(f"/messages/conversations/{cid}/mute", json={"muted": True}).json()["conversation"]["muted"] is True
    As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "Third."})
    assert As(tc, "ravi").get("/messages/unread").json() == {"unread_total": 1}
    assert [n["read"] for n in bell("ravi")] == [True]
    assert As(tc, "ravi").get("/messages/conversations?filter=unread").json()["conversations"][0]["id"] == cid


def test_unread_is_per_person_in_a_department(tc):
    cid = start(tc, "priya", {"department": "radiology"})["conversation"]["id"]
    As(tc, "ravi").post(f"/messages/conversations/{cid}/read", json={"seq": 1})
    assert As(tc, "ravi").get("/messages/unread").json()["unread_total"] == 0
    assert As(tc, "suresh").get("/messages/unread").json()["unread_total"] == 1
    assert len(bell("suresh")) == 1 and len(bell("ravi")) == 1 and bell("ravi")[0]["read"] is True
    assert bell("meena") == [] and bell("tbroot") == []  # never addressed to a department (admins would see it)


# ---- edit and delete ----------------------------------------------------------------------------------------------------------------

def test_edit_and_delete_within_ten_minutes(tc, clock, data_root):
    d = start(tc, "priya", {"user": "ravi"}, text="Report at 10")
    cid, mid = d["conversation"]["id"], d["message"]["id"]
    assert d["message"]["can_edit_until"] == "2026-10-28T10:10:00"
    clock["now"] = T0 + timedelta(minutes=9, seconds=59)
    r = P(tc, "priya").patch(f"/messages/conversations/{cid}/messages/{mid}", json={"text": "Report at 11"})
    assert r.status_code == 200 and r.json()["message"]["text"] == "Report at 11" and r.json()["message"]["edited"] is True
    r = P(tc, "ravi").patch(f"/messages/conversations/{cid}/messages/{mid}", json={"text": "Changed"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_own"
    assert As(tc, "ravi").delete(f"/messages/conversations/{cid}/messages/{mid}").status_code == 403
    clock["now"] = T0 + timedelta(minutes=10, seconds=1)
    r = P(tc, "priya").patch(f"/messages/conversations/{cid}/messages/{mid}", json={"text": "Report at 12"})
    assert r.status_code == 403 and r.json()["detail"] == {"message": "You can only edit a message for 10 minutes.", "code": "edit_window_over"}
    assert As(tc, "priya").delete(f"/messages/conversations/{cid}/messages/{mid}").json()["detail"]["code"] == "edit_window_over"
    lines = [json.loads(x) for x in (data_root / "messages" / f"c_{cid}.jsonl").read_text().splitlines()]
    assert any(e["t"] == "edit" and e["old"] == "Report at 10" and e["text"] == "Report at 11" for e in lines)  # history kept
    # a delete inside the window leaves a tombstone; the text stays in the file until retention
    clock["now"] = T0 + timedelta(minutes=20)
    m2 = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "Wrong patient"}).json()["message"]
    clock["now"] += timedelta(minutes=9, seconds=59)
    r = As(tc, "priya").delete(f"/messages/conversations/{cid}/messages/{m2['id']}")
    assert r.status_code == 200 and r.json()["message"]["deleted"] is True and r.json()["message"]["text"] == ""
    seen = As(tc, "ravi").get(f"/messages/conversations/{cid}").json()
    gone = next(m for m in seen["messages"] if m["id"] == m2["id"])
    assert gone["deleted"] is True and gone["text"] == "" and gone["can_edit_until"] is None
    assert seen["conversation"]["last"]["preview"] == ""
    assert "Wrong patient" in (data_root / "messages" / f"c_{cid}.jsonl").read_text()
    assert P(tc, "priya").patch(f"/messages/conversations/{cid}/messages/{m2['id']}", json={"text": "x"}).json()["detail"]["code"] == "deleted"
    assert As(tc, "priya").delete(f"/messages/conversations/{cid}/messages/M0123456789").status_code == 404


def test_reactions(tc):
    d = start(tc, "priya", {"department": "radiology"})
    cid, mid = d["conversation"]["id"], d["message"]["id"]
    path = f"/messages/conversations/{cid}/messages/{mid}/react"
    assert As(tc, "ravi").post(path, json={"emoji": "thumbs_up"}).json()["message"]["reactions"] == {"thumbs_up": ["ravi"]}
    As(tc, "ravi").post(path, json={"emoji": "thumbs_up"})  # once per person per kind
    As(tc, "suresh").post(path, json={"emoji": "thumbs_up"})
    r = As(tc, "ravi").post(path, json={"emoji": "will_do"})
    assert r.json()["message"]["reactions"] == {"thumbs_up": ["ravi", "suresh"], "will_do": ["ravi"]}
    assert As(tc, "ravi").post(path, json={"emoji": "party"}).json()["detail"]["code"] == "bad_reaction"
    assert As(tc, "ravi").post(path, json={"emoji": None}).json()["message"]["reactions"] == {"thumbs_up": ["suresh"]}
    assert As(tc, "meena").post(path, json={"emoji": "tick"}).status_code == 404


# ---- resolve --------------------------------------------------------------------------------------------------------------------------

def test_resolve_by_any_member_and_a_new_message_reopens(tc, clock, data_root):
    cid = start(tc, "priya", {"department": "radiology"})["conversation"]["id"]
    clock["now"] = T0 + timedelta(minutes=5)
    r = As(tc, "suresh").post(f"/messages/conversations/{cid}/resolve", json={"resolved": True})
    assert r.status_code == 200
    res = r.json()["conversation"]["resolved"]
    assert res == {"by": "suresh", "by_name": "Dr Suresh", "ts": "2026-10-28T10:05:00"}
    assert As(tc, "priya").get("/messages/conversations?filter=resolved").json()["conversations"][0]["resolved"]["by"] == "suresh"
    assert As(tc, "priya").get("/messages/conversations?filter=open").json()["conversations"] == []
    assert As(tc, "ravi").post(f"/messages/conversations/{cid}/resolve", json={"resolved": "yes"}).status_code == 400
    As(tc, "ravi").post(f"/messages/conversations/{cid}/messages", json={"text": "One more finding."})
    assert As(tc, "priya").get(f"/messages/conversations/{cid}").json()["conversation"]["resolved"] is None
    kinds = [e["kind"] for e in audit_lines(data_root) if e.get("conversation") == cid]
    assert kinds == ["conversation_started", "message_sent", "conversation_resolved", "message_sent", "conversation_reopened"]
    ev = [json.loads(x) for x in (data_root / "messages" / f"c_{cid}.jsonl").read_text().splitlines()]
    assert ev[-1]["t"] == "resolve" and ev[-1]["resolved"] is False and ev[-1]["reopened_by_message"] is True
    assert As(tc, "meena").post(f"/messages/conversations/{cid}/resolve", json={"resolved": True}).status_code == 404


# ---- a link grants nothing -----------------------------------------------------------------------------------------------------------

def test_a_case_link_grants_nothing(tc, monkeypatch, data_root):
    case = owned("TB-002", department="breast_surgery", owner="priya", residents=())
    team = copy.deepcopy(case.get("team"))
    rv = org.roles("ravi")
    assert access.scope(rv, case) is None and access.scope(org.roles("priya"), case) == access.FULL
    d = start(tc, "priya", {"user": "ravi"}, text="See this file", link={"type": "case", "id": "TB-002"})
    cid = d["conversation"]["id"]
    own = d["message"]["link"]
    assert own["can_open"] is True and own["label"].startswith("TB-002, ") and NAME not in own["label"] and "SYN-200417" not in own["label"]
    chip = As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["messages"][0]["link"]
    assert chip == {"type": "case", "id": "TB-002", "label": None, "can_open": False, "offer": True}
    after = store.get_case("TB-002")
    assert access.scope(org.roles("ravi"), after) is None and after.get("team") == team
    r = As(tc, "ravi").get("/cases/TB-002")
    assert r.status_code == 403  # the normal refusal (with the open-with-a-reason offer of item 1.9)
    # a sender with no scope cannot attach it, nor an unknown, a missing or a protected Case File
    for link in ({"type": "case", "id": "TB-002"}, {"type": "case", "id": "TB-404"}, {"type": "case", "id": "../TB-002"}, {"type": "meeting", "id": "S1"},
                 {"type": "patient", "id": "TB-002"}, "TB-002"):
        r = As(tc, "ravi").post(f"/messages/conversations/{cid}/messages", json={"text": "x", "link": link})
        assert r.status_code == 400 and r.json()["detail"] == {"message": "You can only attach a Case File you can open.", "code": "link_not_allowed"}
    monkeypatch.setattr(config, "PROTECTED_CASES", set(config.PROTECTED_CASES) | {"TB-002"})
    r = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "x", "link": {"type": "case", "id": "TB-002"}})
    assert r.status_code == 400
    for reader in ("priya", "ravi"):  # a protected Case File never gets a name, even for the sender
        chip = As(tc, reader).get(f"/messages/conversations/{cid}").json()["messages"][0]["link"]
        assert chip["label"] is None and chip["can_open"] is False and chip["offer"] is False
    assert messages.link_view("priya", {"type": "case", "id": "TB-404"}) == {"type": "case", "id": "TB-404", "label": None, "can_open": False, "offer": False}


def test_a_meeting_link_and_the_attach_list(tc):
    owned("TB-002", department="breast_surgery", owner="priya", residents=())
    mid = new_meeting(tc)
    d = start(tc, "anil", {"user": "priya"}, text="Agenda", link={"type": "meeting", "id": mid})
    assert d["message"]["link"]["label"].startswith("Tumour Board ") and d["message"]["link"]["can_open"] is True
    links = As(tc, "priya").get("/messages/links").json()
    assert any(c["id"] == "TB-002" and c["label"].startswith("TB-002, ") for c in links["cases"])
    assert all(NAME not in c["label"] for c in links["cases"])
    assert "TB-002" not in [c["id"] for c in As(tc, "ravi").get("/messages/links").json()["cases"]]
    assert As(tc, "priya").get("/messages/links?q=zzzz").json()["cases"] == []
    assert any(m["id"] == mid for m in As(tc, "anil").get("/messages/links").json()["meetings"])


# ---- no message text or patient detail in the bell, the push or the audit -------------------------------------------------------------

def test_push_bell_and_audit_carry_no_text(tc, sent, data_root):
    owned("TB-002", department="breast_surgery", owner="priya", residents=())
    push.keys(create=True)
    push.subscribe("ravi", SUB)
    d = start(tc, "priya", {"user": "ravi"}, text=TEXT, link={"type": "case", "id": "TB-002"})
    cid = d["conversation"]["id"]
    assert [c["data"]["body"] for c in sent] == ["Vaidyx-TB: New message from Dr Priya Nair"]
    assert sent[0]["data"] == {"title": "Vaidyx-TB", "body": "Vaidyx-TB: New message from Dr Priya Nair", "kind": "message", "url": "/tb-nik"}
    As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": TEXT})
    assert len(sent) == 1  # at most one push per reader per conversation in five minutes
    blobs = [json.dumps(sent), (data_root / "notifications.jsonl").read_text(), (data_root / "org_audit.jsonl").read_text()]
    for blob in blobs:
        for secret in ("Lakshmi", UHID, "TB-002", "MRI", d["message"]["id"], "SYN-200417"):
            assert secret not in blob, secret
    sent_lines = [e for e in audit_lines(data_root) if e["kind"] == "message_sent"]
    assert sent_lines[0] == {"ts": sent_lines[0]["ts"], "by": "priya", "kind": "message_sent", "conversation": cid, "type": "direct", "to": "ravi"}
    # a muted reader gets no push and no bell item
    messages._PUSHED.clear()
    As(tc, "ravi").post(f"/messages/conversations/{cid}/mute", json={"muted": True})
    As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "Again"})
    assert len(sent) == 1


# ---- limits ----------------------------------------------------------------------------------------------------------------------------

def test_text_limits_and_rate_limits(tc, monkeypatch):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    r = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "x" * 2001})
    assert r.status_code == 400 and r.json()["detail"] == {"message": "A message can have at most 2000 characters.", "code": "too_long"}
    assert As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "x" * 2000}).status_code == 200
    r = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "   "})
    assert r.json()["detail"] == {"message": "Write a message first.", "code": "empty"}
    r = As(tc, "priya").post("/messages/conversations", json={"to": {"user": "suresh"}, "text": "x" * 2001})
    assert r.status_code == 400 and As(tc, "suresh").get("/messages/conversations").json()["conversations"] == []  # nothing created
    monkeypatch.setattr(api_messages, "SEND_LIMIT", common.RateLimit(2, 600))
    for _ in range(2):
        assert As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "ok"}).status_code == 200
    r = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "ok"})
    assert r.status_code == 429 and r.json()["detail"] == {"message": "Too many messages. Please wait a moment.", "code": "rate_limited"}
    assert As(tc, "ravi").post(f"/messages/conversations/{cid}/messages", json={"text": "ok"}).status_code == 200  # per login
    monkeypatch.setattr(api_messages, "NEW_LIMIT", common.RateLimit(1, 600))
    assert As(tc, "ravi").post("/messages/conversations", json={"to": {"user": "suresh"}, "text": "Hello"}).status_code == 201
    r = As(tc, "ravi").post("/messages/conversations", json={"to": {"user": "meena"}, "text": "Hello"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


# ---- search, mentions, the notice ---------------------------------------------------------------------------------------------------

def test_search_mentions_and_notice(tc):
    cid = start(tc, "priya", {"department": "radiology"}, text="@ravi @meena please check the margins", mentions=["suresh", "tbroot"])["conversation"]["id"]
    start(tc, "meena", {"user": "dev"}, text="Margins are clear")
    msg = As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["messages"][0]
    assert msg["mentions"] == ["suresh", "ravi"]  # only readers; meena and tbroot are not
    hits = As(tc, "ravi").get("/messages/search?q=MARGINS").json()["hits"]
    assert [h["conversation_id"] for h in hits] == [cid] and hits[0]["title"] == "Radiology"
    assert len(As(tc, "ravi").get("/messages/search?q=Priya").json()["hits"]) == 1  # the sender's name
    assert As(tc, "ravi").get("/messages/search?q=m").json()["hits"] == []
    assert As(tc, "anil").get("/messages/search?q=margins").json()["hits"] == []
    assert As(tc, "ravi").get("/messages/conversations?q=radio").json()["conversations"][0]["id"] == cid
    assert As(tc, "ravi").get("/messages/conversations?q=zzz").json()["conversations"] == []
    assert As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["notice_seen"] is False
    assert As(tc, "ravi").post("/messages/notice").json() == {"notice_seen": True}
    assert As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["notice_seen"] is True and messages.notice_seen("ravi") is True


def test_paging(tc):
    cid = start(tc, "priya", {"user": "ravi"}, text="m1")["conversation"]["id"]
    for i in range(2, 6):
        As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": f"m{i}"})
    v = As(tc, "ravi").get(f"/messages/conversations/{cid}?limit=2").json()
    assert [m["text"] for m in v["messages"]] == ["m4", "m5"] and v["has_more"] is True
    v = As(tc, "ravi").get(f"/messages/conversations/{cid}?limit=2&before={v['messages'][0]['seq']}").json()
    assert [m["text"] for m in v["messages"]] == ["m2", "m3"] and v["has_more"] is True


# ---- storage ---------------------------------------------------------------------------------------------------------------------------

def test_storage_modes_malformed_lines_and_atomic_index(tc, data_root, monkeypatch):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    d = data_root / "messages"
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    for name in ("index.json", "reads.json", f"c_{cid}.jsonl"):
        assert stat.S_IMODE(os.stat(d / name).st_mode) == 0o600, name
    with open(d / f"c_{cid}.jsonl", "a") as f:
        f.write("{not json\n\n[1, 2]\n")
    r = As(tc, "priya").post(f"/messages/conversations/{cid}/messages", json={"text": "After the bad line"})
    assert r.status_code == 200 and r.json()["message"]["seq"] == 2
    assert [m["text"] for m in As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["messages"]] == ["Please see the report.", "After the bad line"]
    before = (d / "index.json").read_bytes()

    def crash(a, b):
        raise OSError("disk gone")
    with monkeypatch.context() as m:  # a crash between the .tmp and the replace leaves the old index whole
        m.setattr(messages.os, "replace", crash)
        with pytest.raises(OSError):
            messages._save_index({"conversations": {}})
    assert (d / "index.json").read_bytes() == before and cid in messages._index()["conversations"]


def test_two_threads_get_distinct_numbers(tc):
    cid = start(tc, "priya", {"user": "ravi"})["conversation"]["id"]
    errors = []

    def run(who):
        try:
            for i in range(8):
                messages.send(who, cid, f"{who} {i}")
        except Exception as e:  # pragma: no cover
            errors.append(e)
    ts = [threading.Thread(target=run, args=(u,)) for u in ("priya", "ravi")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    seqs = [ev["seq"] for ev in messages._events(cid)]
    assert len(seqs) == 17 and len(set(seqs)) == 17
    assert len(As(tc, "priya").get(f"/messages/conversations/{cid}").json()["messages"]) == 17


def test_retention_removes_text_only_after_the_period(tc, clock, data_root):
    d = start(tc, "priya", {"user": "ravi"}, text="Old note")
    cid, mid = d["conversation"]["id"], d["message"]["id"]
    P(tc, "priya").patch(f"/messages/conversations/{cid}/messages/{mid}", json={"text": "Old note, edited"})
    assert messages.retention(now=T0 + timedelta(days=364)) == 0
    assert messages.retention(days=0, now=T0 + timedelta(days=4000)) == 0  # 0 keeps everything
    assert messages.job(T0 + timedelta(days=366)) == {"conversations": 1}
    raw = (data_root / "messages" / f"c_{cid}.jsonl").read_text()
    assert "Old note" not in raw and stat.S_IMODE(os.stat(data_root / "messages" / f"c_{cid}.jsonl").st_mode) == 0o600
    ev = [json.loads(x) for x in raw.splitlines()]
    assert all(e["removed"] for e in ev if e["t"] in ("msg", "edit"))
    m = As(tc, "ravi").get(f"/messages/conversations/{cid}").json()["messages"][0]
    assert m["removed"] is True and m["text"] == "" and m["id"] == mid
    assert messages.retention(now=T0 + timedelta(days=400)) == 0  # nothing left to remove
    change_org(lambda o: o["hospital"].__setitem__("message_retention_days", 30))
    cid2 = start(tc, "priya", {"user": "suresh"}, text="Short lived")["conversation"]["id"]
    assert messages.retention(now=T0 + timedelta(days=31)) == 1 and "Short lived" not in (data_root / "messages" / f"c_{cid2}.jsonl").read_text()


# ---- no account changed --------------------------------------------------------------------------------------------------------------

def test_no_account_is_created_or_changed(tc, data_root, monkeypatch):
    before = (data_root / "org.json").read_bytes()
    prof = (data_root / "profiles.json").read_bytes() if (data_root / "profiles.json").exists() else None
    d = start(tc, "priya", {"department": "radiology"})
    cid, mid = d["conversation"]["id"], d["message"]["id"]
    As(tc, "ravi").post(f"/messages/conversations/{cid}/messages", json={"text": "Seen"})
    As(tc, "suresh").post(f"/messages/conversations/{cid}/resolve", json={"resolved": True})
    As(tc, "ravi").post(f"/messages/conversations/{cid}/read", json={"seq": 9})
    As(tc, "ravi").post(f"/messages/conversations/{cid}/mute", json={"muted": True})
    As(tc, "ravi").post(f"/messages/conversations/{cid}/messages/{mid}/react", json={"emoji": "tick"})
    As(tc, "priya").delete(f"/messages/conversations/{cid}/messages/{mid}")
    start(tc, "priya", {"role": "coordinator"})
    As(tc, "tbroot").post("/messages/conversations", json={"to": {"user": "priya"}, "text": "x"})
    As(tc, "priya").post("/messages/conversations", json={"to": {"user": "newperson"}, "text": "x"})
    As(tc, "ravi").post("/messages/notice")
    assert (data_root / "org.json").read_bytes() == before
    assert ((data_root / "profiles.json").read_bytes() if (data_root / "profiles.json").exists() else None) == prof
    assert "newperson" not in org.load()["users"]


def test_listeners_never_break_a_send(tc, monkeypatch):
    def boom(reader, event):
        raise RuntimeError("socket down")
    monkeypatch.setattr(messages, "LISTENERS", [boom])
    monkeypatch.setattr(messages, "INTERESTED", lambda u: True)
    d = start(tc, "priya", {"user": "ravi"}, text="Still stored")
    assert As(tc, "ravi").get(f"/messages/conversations/{d['conversation']['id']}").json()["messages"][0]["text"] == "Still stored"
