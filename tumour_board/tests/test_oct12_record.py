"""12 Oct: tamper-evident audit chain, outcome type and patient-communication fields on the board record (with their flags and the
'inform the patient' follow-up), time per case in a board session, and values over time."""
import asyncio, json

import pytest

from tumour_board import board, config, followup, llm, postboard, rules, store
from tumour_board.tests.util import add, fact, make_doc


def test_audit_chain_links_events_and_detects_tampering(unit_case):
    for i in range(3):
        store.audit(unit_case, {"kind": "test", "n": i})
    v = store.verify_audit(unit_case)
    assert v["ok"] and v["chained"] >= 3 and v["first_broken"] is None and v["last_hash"]
    ev = store.read_audit(unit_case)
    assert ev[-1]["prev"] == ev[-2]["hash"] and len(ev[-1]["hash"]) == 64
    p = store.case_dir(unit_case) / "audit.jsonl"
    lines = p.read_text().splitlines()
    tampered = json.loads(lines[-2]); tampered["n"] = 99
    lines[-2] = json.dumps(tampered, ensure_ascii=False); p.write_text("\n".join(lines) + "\n")
    v2 = store.verify_audit(unit_case)
    assert not v2["ok"] and v2["first_broken"] == len(lines) - 2
    # events written before the chain existed are counted as unchained, the chain continues after them
    p.write_text('{"ts": "2026-10-01T00:00:00", "kind": "old"}\n' + "\n".join(lines[:-2]) + "\n")
    store._last_hash.pop(str(p), None)
    store.audit(unit_case, {"kind": "test", "n": 4})
    v3 = store.verify_audit(unit_case)
    assert v3["unchained"] == 1 and v3["chained"] >= 1


def _fake(monkeypatch):
    async def fake_chat(role, msgs, **kw):
        return {"claims": []}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(postboard.llm, "chat", fake_chat)


def test_outcome_type_and_communication_flags(unit_case, monkeypatch):
    _fake(monkeypatch)
    with pytest.raises(ValueError):
        postboard.clean_record_fields({"outcome_type": "maybe"})
    with pytest.raises(ValueError):
        postboard.clean_record_fields({"patient_informed_date": "yesterday"})
    rec = asyncio.run(postboard.record_decision(unit_case, {"board_date": "2026-09-10", "decision_text": "Plan agreed.", "recorded_by": "Dr A",
                                                            "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)", "actions": []}, user="coord"))
    kinds = {f.get("field") for f in rec["adjudication"]["flags"] if f.get("kind") == "communication"}
    assert kinds == {"patient_informed_date", "key_worker", "trial_considered", "intent_as_recorded", "consent_recorded"}
    assert all(f["severity"] == "info" for f in rec["adjudication"]["flags"] if f.get("kind") == "communication")
    assert rec["resolution"]["open"] == 0  # information only: no resolution needed
    acts = [a for a in store.get_state(unit_case)["actions"] if a.get("communication")]
    assert len(acts) == 1 and acts[0]["due"] == "2026-09-17" and acts[0]["status"] == "pending"
    # deferred without an action: review flag; referred without a destination: review flag
    d = asyncio.run(postboard.record_decision(unit_case, {"board_date": "2026-09-10", "decision_text": "Deferred.", "recorded_by": "Dr A", "participants": "Dr A (Med Onc)",
                                                          "outcome_type": "deferred", "actions": []}, user="coord"))
    assert any(f.get("field") == "actions" and f["severity"] == "review" for f in d["adjudication"]["flags"])
    assert not any(f.get("kind") == "communication" for f in d["adjudication"]["flags"])
    assert not [a for a in store.get_state(unit_case)["actions"] if a.get("communication") and a.get("board_record") == d["id"]]
    r = asyncio.run(postboard.record_decision(unit_case, {"board_date": "2026-09-10", "decision_text": "Referred.", "recorded_by": "Dr A", "participants": "Dr A (Med Onc)",
                                                          "outcome_type": "referred", "actions": [{"task": "Send records", "department": "Tumour Board coordination", "due": "2026-09-20"}]}, user="coord"))
    assert any(f.get("field") == "referred_to" for f in r["adjudication"]["flags"])


def test_update_communication_closes_the_inform_action_and_is_audited(unit_case, monkeypatch):
    _fake(monkeypatch)
    rec = asyncio.run(postboard.record_decision(unit_case, {"board_date": "2026-09-10", "decision_text": "Plan agreed.", "recorded_by": "Dr A",
                                                            "participants": "Dr A (Med Onc)", "actions": []}, user="coord"))
    out = postboard.update_communication(unit_case, rec["id"], {"patient_informed_date": "12/09/2026", "informed_by": "Dr A", "key_worker": "Sr. Meena, 98450 00000",
                                                                 "intent_as_recorded": "", "trial_considered": "yes", "consent_recorded": "yes", "decision_text": "HACK"}, user="coord")
    assert out["patient_informed_date"] == "2026-09-12" and out["decision_text"] == "Plan agreed." and out.get("version", 1) == 1
    # the intent is set by a correction with a reason, never by this form (the whole-run review, I4): only its flag is left
    assert {f.get("field") for f in out["adjudication"]["flags"] if f.get("kind") == "communication"} == {"intent_as_recorded"}
    out = postboard.correct_record(unit_case, rec["id"], {"intent": "curative"}, "coord", "Coord", "As the board said")
    assert out["version"] == 2 and not any(f.get("kind") == "communication" for f in out["adjudication"]["flags"])
    st = store.get_state(unit_case)
    a = [x for x in st["actions"] if x.get("communication")][0]
    assert a["status"] == "completed" and "informed on 2026-09-12" in a["history"][-1]["event"]
    kinds = [e["kind"] for e in store.read_audit(unit_case)]
    assert "board_record_communication" in kinds and kinds[-1] == "board_record_corrected"
    with pytest.raises(KeyError):
        postboard.update_communication(unit_case, "Bnope", {}, user="coord")


def test_session_timing_per_case(unit_case, monkeypatch):
    store.create_case("TB-UNIT2", {"name": "SYNTHETIC, Two", "mrn": "SYN-900002", "agesex": "50 Y / F"}, "unit", board_date="2026-09-20", created_by="t")
    c = store.get_case(unit_case); c["board_date"] = "2026-09-20"; store.save_case(c)
    s = board.create("2026-09-20", "coord")
    s = board.start(s["id"], "coord")
    assert s["current"] == unit_case and s.get("current_since")
    clock = {"t": "2026-09-20T10:00:00"}
    monkeypatch.setattr(store, "now_iso", lambda: clock["t"])  # every timestamp in board and store reads this clock
    s["current_since"] = "2026-09-20T10:00:00"; board._save(s)
    clock["t"] = "2026-09-20T10:05:30"
    s = board.set_current(s["id"], "TB-UNIT2", "coord")
    assert s["timing"][unit_case] == 330.0 and s["current_since"] == "2026-09-20T10:05:30"
    clock["t"] = "2026-09-20T10:12:00"
    s = board.close(s["id"], "coord")
    assert s["timing"]["TB-UNIT2"] == 390.0 and s["current_since"] is None
    assert board.export(s["id"])["timing"] == {unit_case: 330.0, "TB-UNIT2": 390.0}


def test_trends_list_numeric_values_over_time(unit_case):
    add(unit_case, make_doc("Dl1", "lab", date="2026-09-01", facts={"haemoglobin": fact("11.8 g/dL"), "cea": fact("12.4 ng/mL")}, text="SYNTHETIC\nLAB\nHaemoglobin 11.8 g/dL\nCEA 12.4 ng/mL\nReport status: FINAL"))
    add(unit_case, make_doc("Dl2", "lab", date="2026-09-29", facts={"haemoglobin": fact("12.1 g/dL"), "cea": fact("4.1 ng/mL")}, text="SYNTHETIC\nLAB\nHaemoglobin 12.1 g/dL\nCEA 4.1 ng/mL\nReport status: FINAL"))
    t = {x["field"]: x for x in postboard.trends(unit_case)}
    assert set(t) == {"haemoglobin", "cea"}
    assert [r["number"] for r in t["cea"]["rows"]] == [12.4, 4.1] and t["cea"]["max"] == 12.4 and t["cea"]["rows"][0]["doc_id"] == "Dl1" and t["cea"]["rows"][0]["quote"]
