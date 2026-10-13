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
