"""Ask this Case File (18 Oct): the shared team chat behind qa.ask (replaced by a fake: no model), saved per Case File, visible to the
treating team and the coordinator only, pinned, stale when the records change, rate limited."""
import pytest

from tumour_board import chats, qa, store
from tumour_board.api import chats as chats_api
from tumour_board.api import common
from tumour_board.tests.test_nik_slots import CASE, OWNER, audit_kinds, nik_app, people, tb001  # noqa: F401 (fixtures)

ANSWER = {"status": "answered", "statements": [{"text": "ECOG performance status 1 is recorded in the OPD note.",
                                                "citations": [{"doc_id": "Dbae880db", "quote": "ECOG performance status: 1", "page": 0, "start": 398, "end": 424,
                                                               "doc_title": "MEDICAL ONCOLOGY OPD NOTE", "date": "2026-09-02", "status": "FINAL"}]}],
          "dropped_unverified": 1, "removed": [{"text": "x", "reason": "quote_not_found"}], "message": "", "value_hits": [], "mode": "full", "seconds": 3.2}


@pytest.fixture
def fake_qa(monkeypatch):
    asked = []

    async def ask(case_id, question, history=None):
        asked.append((case_id, question, history))
        if "nothing" in question:
            return {"status": "not_documented", "statements": [], "message": "Not documented in the Case File.", "seconds": 1.0, "dropped_unverified": 0}
        return dict(ANSWER)
    monkeypatch.setattr(qa, "ask", ask)
    return asked


def test_ask_saves_a_thread_with_verified_citations(nik_app, tb001, fake_qa):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "  What is the ECOG? "})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["id"].startswith("T") and t["by"] == "dr.rao" and t["by_name"] == "Dr Rao" and t["question"] == "What is the ECOG?" and t["status"] == "answered"
    c = t["statements"][0]["citations"][0]
    assert c["doc_id"] == "Dbae880db" and c["doc_title"] == "MEDICAL ONCOLOGY OPD NOTE" and c["page"] == 0 and c["quote"] == "ECOG performance status: 1"
    assert t["stale"] is False and t["pinned"] is False and t["seconds"] == 3.2 and t["dropped_unverified"] == 1 and t["signature"]
    assert fake_qa == [(CASE, "What is the ECOG?", None)]
    assert "removed" not in t and "value_hits" not in t  # the thread keeps what the team reads: statements and quotes
    v = tc.get(f"/api/tb/cases/{CASE}/chats").json()
    assert [x["id"] for x in v["threads"]] == [t["id"]]
    saved = store._read_json(store.case_dir(CASE) / "chats.json")
    assert saved["threads"][0]["signature"]["hash"] == t["signature"] and saved["threads"][0]["shared"] is True
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "chat_asked"]
    assert ev[-1]["by"] == "dr.rao" and ev[-1]["thread"] == t["id"] and ev[-1]["statements"] == 1
    assert store.verify_audit(CASE)["ok"]
    # an abstained answer is a thread too
    t2 = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Is there nothing about this?", "history": [{"role": "user", "content": "earlier"}]}).json()
    assert t2["status"] == "not_documented" and t2["statements"] == [] and "Not documented" in t2["message"]
    assert fake_qa[-1][2] == [{"role": "user", "content": "earlier"}]
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "   "}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json=[1]).status_code == 400


def test_visibility_treating_team_and_coordinator_only(nik_app, tb001, fake_qa):
    tc, who = nik_app
    tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "What is the ECOG?"})
    who["user"] = "dr.ravi"  # Radiology: not asked, not a participant
    assert tc.get(f"/api/tb/cases/{CASE}/chats").status_code == 403
    c = store.get_case(CASE)
    c["participants"] = [{"department": "radiology", "since": store.now_iso(), "by": "dr.rao"}, {"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]
    store.save_case(c)
    r = tc.get(f"/api/tb/cases/{CASE}/chats")  # a supporting department that takes part reads the Case File, never the team chat
    assert r.status_code == 403 and "supporting department" in r.json()["detail"]["message"]
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "x?"}).status_code == 403
    who["user"] = "dr.nair"  # a treating department that takes part
    assert tc.get(f"/api/tb/cases/{CASE}/chats").status_code == 200
    who["user"] = "res.asha"  # a resident of the owning department
    assert tc.get(f"/api/tb/cases/{CASE}/chats").status_code == 200
    who["user"] = "anil"
    assert len(tc.get(f"/api/tb/cases/{CASE}/chats").json()["threads"]) == 1
    # a department that was only asked (REQUESTS scope) is refused by the Case File guard
    c["participants"] = []; store.save_case(c)
    st = store.get_state(CASE)
    st["actions"].append({"id": "A1", "source": "pre_authorization", "requirement": "cect_tap", "label": "CT", "department": "Radiology", "department_id": "radiology",
                         "status": "pending", "created": store.now_iso(), "history": [], "sent": {"by": "dr.rao", "at": store.now_iso()}})
    store.save_state(CASE, st)
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}").status_code == 200 and tc.get(f"/api/tb/cases/{CASE}/chats").status_code == 403


def test_pin_and_stale_after_a_document_changes(nik_app, tb001, fake_qa):
    tc, who = nik_app
    a = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "First question?"}).json()
    b = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Second question?"}).json()
    assert [x["id"] for x in tc.get(f"/api/tb/cases/{CASE}/chats").json()["threads"]] == [b["id"], a["id"]]  # newest first
    r = tc.post(f"/api/tb/cases/{CASE}/chats/{a['id']}/pin", json={"pinned": True})
    assert r.status_code == 200 and r.json()["pinned"] is True
    assert [x["id"] for x in tc.get(f"/api/tb/cases/{CASE}/chats").json()["threads"]] == [a["id"], b["id"]]  # pinned first
    assert tc.post(f"/api/tb/cases/{CASE}/chats/Tnope/pin", json={"pinned": True}).status_code == 404
    assert "chat_pinned" in audit_kinds(CASE)
    assert all(not x["stale"] for x in tc.get(f"/api/tb/cases/{CASE}/chats").json()["threads"])
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")  # the records changed since the answers
    v = tc.get(f"/api/tb/cases/{CASE}/chats").json()
    assert all(x["stale"] and "changed since" in x["stale_reason"] for x in v["threads"])
    c = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Third?"}).json()
    assert c["stale"] is False
    assert tc.post(f"/api/tb/cases/{CASE}/chats/{a['id']}/pin", json={"pinned": False}).json()["pinned"] is False


def test_rate_limit_per_user(nik_app, tb001, fake_qa, monkeypatch):
    tc, who = nik_app
    monkeypatch.setattr(chats_api, "ASK_LIMIT", common.RateLimit(2, 600))
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "One?"}).status_code == 200
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Two?"}).status_code == 200
    r = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Three?"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    who["user"] = "anil"  # another user has their own allowance
    assert tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "Four?"}).status_code == 200
    assert len(fake_qa) == 3


def test_may_read_rule():
    full, req = "full", "requests"
    assert chats.may_read({"treating": {OWNER: "member"}, "known": True}, full)
    assert chats.may_read({"coordinator": True, "known": True}, full)
    assert chats.may_read({"resident_treating": {OWNER: "resident"}, "resident": {OWNER: "resident"}, "known": True}, full)
    assert not chats.may_read({"supporting": {"radiology": "member"}, "known": True}, full)
    assert not chats.may_read({"treating": {OWNER: "member"}, "known": True}, req)
    assert not chats.may_read({"treating": {OWNER: "member"}, "known": True, "disabled": True}, full)
    assert not chats.may_read(None, full)
    assert "supporting department" in chats.refusal({"supporting": {"radiology": "member"}})


def test_thread_names_the_model_that_wrote_it(nik_app, tb001, fake_qa, monkeypatch):
    """Review 9 C, S3: an answer carries the model that wrote it (the answer's own, else the reasoner's label), kept on the thread and
    sent with it; a request refused before any model call names none; an older thread without the field sends None."""
    from tumour_board import chats as chats_mod, config
    tc, who = nik_app
    cfg = config.models()
    cfg["reasoner"]["label"] = "Gemma-4-31B"
    monkeypatch.setattr(config, "models", lambda: cfg)
    t = tc.post(f"/api/tb/cases/{CASE}/chats", json={"question": "What is the ECOG?"}).json()
    assert t["model"] == "Gemma-4-31B"
    assert store._read_json(store.case_dir(CASE) / "chats.json")["threads"][-1]["model"] == "Gemma-4-31B"
    assert tc.get(f"/api/tb/cases/{CASE}/chats").json()["threads"][0]["model"] == "Gemma-4-31B"
    assert chats_mod._model({"status": "answered", "model": "Qwen3.5-4B"}) == "Qwen3.5-4B"
    assert chats_mod._model({"status": "out_of_scope"}) == ""
    cfg["reasoner"]["label"] = ""
    assert chats_mod._model({"status": "not_documented"}) == "reasoner"
    assert chats_mod.public({"id": "Told", "question": "q"}, "h")["model"] is None
