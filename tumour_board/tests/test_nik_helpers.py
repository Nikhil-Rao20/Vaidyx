"""Specialty helpers (18 Oct): six cards, the brief prepared in the background by the role's agent (agents.run_agent replaced by a fake:
no model), its status from the stored artefact and the Case File signature, and the chat per role (agents.ask replaced by a fake)."""
import time

import pytest

from tumour_board import agents, helpers, rules, store
from tumour_board.tests.test_nik_slots import CASE, OWNER, audit_kinds, nik_app, people, tb001  # noqa: F401 (fixtures)

LABELS = ["Radiology records check", "Pathology records check", "Medical Oncology records check", "Surgical Oncology records check",
          "Radiation Oncology records check", "Nuclear Medicine records check"]


@pytest.fixture
def fake_agents(monkeypatch):
    runs, asks = [], []

    async def run_agent(case_id, role, focus_question="", max_steps=5):
        runs.append((case_id, role, focus_question))
        st = store.get_state(case_id)
        b = {"role": role, "label": agents.ROLES[role]["label"], "sections": [{"heading": "Imaging", "items": [{"text": "CT: 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D41f9d46c", "quote": "5.2 x 4.1 cm"}]}]}],
             "points_for_review": [{"text": "Is the PET/CT stage line the one to quote?", "citations": [{"doc_id": "D4edcec61", "quote": "Stage IIIB"}], "references": []}],
             "not_documented": [], "removed": [], "dropped_unverified": 0, "generated": store.now_iso(), "model": "Gemma-4-31B", "review": {"status": "ai_draft"},
             "signature": rules.case_signature(case_id, st), "version": agents.BRIEF_VERSION, "focus": "", "near_match": False, "seconds": 0.1}
        st.setdefault("artefacts", {})[f"brief_{role}"] = b
        store.save_state(case_id, st)
        yield {"type": "start", "role": role, "label": b["label"]}
        yield {"type": "step", "tool": "finish", "input": "", "thought": "done"}
        yield {"type": "brief", "brief": b}

    async def ask(case_id, role, question, history=None, user=""):
        asks.append((case_id, role, question, history, user))
        return {"role": role, "label": agents.ROLES[role]["label"], "kind": agents.LIVE_LABEL, "question": question, "status": "answered",
                "statements": [{"text": "The CECT reports a 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D41f9d46c", "quote": "measuring 5.2 x 4.1 cm", "page": 0, "doc_title": "CECT THORAX REPORT"}]}],
                "references": [{"org": "ICRI / IRIA onco-imaging checklists, India", "title": "Lung checklist", "page": 2, "region": "India", "quote": "report the size", "file": "iria/x.pdf", "page_kind": "page", "page_end": 2, "by": "agent"}],
                "removed": [], "dropped_unverified": 0, "references_dropped": 0, "mode": "full", "answered_at": store.now_iso(), "message": "", "seconds": 2.0, "model": "Gemma-4-31B"}
    monkeypatch.setattr(agents, "run_agent", run_agent)
    monkeypatch.setattr(agents, "ask", ask)
    return runs, asks


def _poll(tc, job_id, tries=100):
    for _ in range(tries):
        j = tc.get(f"/api/tb/jobs/{job_id}").json()
        if j["state"] in ("finished", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_list_six_helpers(nik_app, tb001):
    tc, who = nik_app
    r = tc.get(f"/api/tb/cases/{CASE}/helpers")
    assert r.status_code == 200, r.text
    hs = r.json()["helpers"]
    assert [h["label"] for h in hs] == LABELS and [h["role"] for h in hs] == list(helpers.ROLES)
    assert all(h["brief"]["status"] == "none" and h["thread_count"] == 0 and h["prepare_allowed"] for h in hs)
    assert [h["role"] for h in hs if h["head"]] == list(helpers.HEADS) and r.json()["heads"] == list(helpers.HEADS)
    who["user"] = "anil"
    assert all(h["prepare_allowed"] for h in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"])
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}/helpers").status_code == 403


def test_prepare_runs_in_the_background_and_is_reused_until_stale(nik_app, tb001, fake_agents):
    tc, who = nik_app
    runs, _ = fake_agents
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/cardiology/prepare").status_code == 404
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "preparing" and out["reused"] is False and out["job"].startswith("J")
    j = _poll(tc, out["job"])
    assert j["state"] == "finished" and j["kind"] == "helper_brief" and j["role"] == "radiology" and j["brief"]["sections"] == 1 and j["by"] == "dr.rao"
    assert runs == [(CASE, "radiology", "")]
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["status"] == "ready" and h["brief"]["label"] == "AI draft, not reviewed" and h["brief"]["points_for_review"][0]["text"].startswith("Is the PET/CT")
    assert h["brief"]["sections"][0]["items"][0]["citations"][0]["doc_id"] == "D41f9d46c"
    assert "helper_prepare" in audit_kinds(CASE)
    # fresh: reused without a second run; refresh runs again
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare").json()
    assert r["status"] == "ready" and r["reused"] is True and len(runs) == 1 and _poll(tc, r["job"])["reused"] is True
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare", json={"refresh": True}).json()
    assert r["status"] == "preparing" and _poll(tc, r["job"])["state"] == "finished" and len(runs) == 2
    # the records change: stale, and the next prepare runs
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["status"] == "stale" and "document" in h["brief"]["stale_reason"]
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/prepare").json()
    assert r["status"] == "preparing" and _poll(tc, r["job"])["state"] == "finished" and len(runs) == 3
    # a reviewed brief says who reviewed it
    st = store.get_state(CASE); st["artefacts"]["brief_radiology"]["review"] = {"status": "reviewed", "by": "dr.rao"}; store.save_state(CASE, st)
    h = next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")
    assert h["brief"]["reviewed_by"] == "dr.rao" and h["brief"]["label"] == "Reviewed"


def test_prepare_is_for_the_owner_team_and_the_coordinator(nik_app, tb001, fake_agents):
    tc, who = nik_app
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    hs = tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"]
    assert all(not h["prepare_allowed"] for h in hs)
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").status_code == 403
    who["user"] = "res.asha"
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").status_code == 200
    who["user"] = "anil"
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/nuclear_medicine/prepare")
    assert r.status_code == 200 and _poll(tc, r.json()["job"])["state"] == "finished"
    # an unlisted Case File has no brief to prepare
    c2 = store.create_case("TB-NEW", {"name": "SYNTHETIC, Someone", "mrn": "SYN-1", "agesex": "50 Y / F"}, "", created_by="test"); c2["department"] = OWNER; store.save_case(c2)
    who["user"] = "dr.rao"
    assert tc.post("/api/tb/cases/TB-NEW/helpers/radiology/prepare").status_code == 409


def test_prepare_failure_reaches_the_job(nik_app, tb001, monkeypatch):
    tc, who = nik_app

    async def bad(case_id, role, focus_question="", max_steps=5):
        yield {"type": "error", "message": "unknown role"}
    monkeypatch.setattr(agents, "run_agent", bad)
    j = _poll(tc, tc.post(f"/api/tb/cases/{CASE}/helpers/pathology/prepare").json()["job"])
    assert j["state"] == "failed" and j["error"] == "unknown role"
    assert next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "pathology")["brief"]["status"] == "none"
    assert not helpers.PREPARING


def test_helper_chat_per_role(nik_app, tb001, fake_agents):
    tc, who = nik_app
    _, asks = fake_agents
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json() == {"messages": [], "role": "radiology", "label": "Radiology records check"}
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": " "}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/helpers/cardiology/chat", json={"question": "x?"}).status_code == 404
    r = tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "What size is the mass?"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["id"].startswith("H") and m["role"] == "radiology" and m["by"] == "dr.rao" and m["by_name"] == "Dr Rao" and m["status"] == "answered"
    assert m["statements"][0]["citations"][0]["doc_title"] == "CECT THORAX REPORT" and m["references"][0]["region"] == "India" and m["stale"] is False
    assert m["kind"] == agents.LIVE_LABEL
    assert asks == [(CASE, "radiology", "What size is the mass?", [], "dr.rao")]
    tc.post(f"/api/tb/cases/{CASE}/helpers/radiology/chat", json={"question": "And the nodes?"})
    assert asks[-1][3] == [{"role": "user", "content": "What size is the mass?"}, {"role": "assistant", "content": "The CECT reports a 5.2 x 4.1 cm mass."}]
    v = tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()
    assert [x["question"] for x in v["messages"]] == ["What size is the mass?", "And the nodes?"]
    assert next(x for x in tc.get(f"/api/tb/cases/{CASE}/helpers").json()["helpers"] if x["role"] == "radiology")["thread_count"] == 2
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/pathology/chat").json()["messages"] == []
    assert store._read_json(store.case_dir(CASE) / "helper_chats.json")["radiology"][0]["signature"]
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "helper_asked"]
    assert ev[-1]["role"] == "radiology" and ev[-1]["by"] == "dr.rao" and store.verify_audit(CASE)["ok"]
    store.add_document_file(CASE, "new_report.pdf", b"synthetic new")
    assert all(x["stale"] for x in tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"])
    who["user"] = "anil"  # the coordinator reads the shared thread
    assert len(tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").json()["messages"]) == 2
    who["user"] = "dr.ravi"
    assert tc.get(f"/api/tb/cases/{CASE}/helpers/radiology/chat").status_code == 403
