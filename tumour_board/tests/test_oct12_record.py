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
