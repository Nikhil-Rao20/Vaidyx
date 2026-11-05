"""night-v3 item 3.5: versions of the pre-board summary. A rebuild keeps the earlier version in artefacts.summary_history (oldest first,
with archived_at and its own review), artefacts.summary stays the live version (review ai_draft again), and every review carries the
generated time of the version it judged. Synthetic data only; the reasoner is a fake (no model call)."""
import asyncio, itertools

import pytest

from tumour_board import llm, rules, service, store, summary
from tumour_board.tests.util import add, make_doc

IHC = "SYNTHETIC\nIHC REPORT\nPD-L1 (22C3) tumour proportion score 60 percent\nHER2 negative (IHC 1+)\nReport status: FINAL"
GOOD = {"section": "investigations", "text": "The IHC report records a PD-L1 tumour proportion score of 60 percent.",
        "citations": [{"doc_id": "Dihc00000", "quote": "PD-L1 (22C3) tumour proportion score 60 percent"}]}
HER2 = {"section": "investigations", "text": "The IHC report records HER2 negative (IHC 1+).",
        "citations": [{"doc_id": "Dihc00000", "quote": "HER2 negative (IHC 1+)"}]}


@pytest.fixture
def ihc_case(unit_case, monkeypatch):
    add(unit_case, make_doc("Dihc00000", "ihc", date="2026-09-05", text=IHC))
    rules.evaluate(unit_case)
    tick = itertools.count(1)  # distinct times per call (store.now_iso has one-second resolution)
    monkeypatch.setattr(store, "now_iso", lambda: f"2026-10-27T10:{next(tick):02d}:00")
    return unit_case


def _fake(monkeypatch, sentences):
    async def fake_chat(role, msgs, **kw):
        return {"sentences": sentences, "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat)


def _arts(case_id):
    return store.get_state(case_id)["artefacts"]


def test_first_build_has_no_history(ihc_case, monkeypatch):
    _fake(monkeypatch, [GOOD])
    asyncio.run(summary.build(ihc_case, force=True))
    a = _arts(ihc_case)
    assert "summary_history" not in a and a["summary"]["review"] == {"status": "ai_draft"}
    assert [v["archived_at"] for v in summary.history(store.get_state(ihc_case))] == [None]


def test_rebuild_archives_the_earlier_version_with_its_review(ihc_case, monkeypatch):
    _fake(monkeypatch, [GOOD])
    first = asyncio.run(summary.build(ihc_case, force=True))
    rv = service.review(ihc_case, "summary", "reviewed", "Checked against the IHC report", "dr.rao")
    assert rv["generated"] == first["generated"] and rv["status"] == "reviewed"
    _fake(monkeypatch, [GOOD, HER2])
    second = asyncio.run(summary.build(ihc_case, force=True))
    assert second["generated"] != first["generated"]
    a = _arts(ihc_case)
    assert len(a["summary_history"]) == 1
    old = a["summary_history"][0]
    assert old["archived_reason"] == "rebuilt" and old["archived_at"] and old["archived_at"] > first["generated"]
    assert old["generated"] == first["generated"] and old["signature"] == first["signature"]
    assert [s["text"] for sec in old["sections"] for s in sec["sentences"] if not s.get("from_case_record")] == [GOOD["text"]]
    assert old["review"] == {"status": "reviewed", "comment": "Checked against the IHC report", "by": "dr.rao", "at": rv["at"],
                             "generated": first["generated"]}
    live = a["summary"]
    assert live["generated"] == second["generated"] and live["review"] == {"status": "ai_draft"} and "archived_at" not in live
    assert [s["text"] for sec in live["sections"] for s in sec["sentences"] if not s.get("from_case_record")] == [GOOD["text"], HER2["text"]]


def test_history_is_oldest_first_and_never_trimmed(ihc_case, monkeypatch):
    _fake(monkeypatch, [GOOD])
    gens = []
    for i in range(4):
        gens.append(asyncio.run(summary.build(ihc_case, force=True))["generated"])
        if i == 1:
            service.review(ihc_case, "summary", "flagged", "HER2 line missing", "dr.rao")
    st = store.get_state(ihc_case)
    assert len(st["artefacts"]["summary_history"]) == 3
    h = summary.history(st)
    assert [v["generated"] for v in h] == gens
    assert [v["archived_at"] is None for v in h] == [False, False, False, True]
    assert [v["review"]["status"] for v in h] == ["ai_draft", "flagged", "ai_draft", "ai_draft"]
    assert h[1]["review"]["generated"] == gens[1]
    assert [v["archived_at"] for v in h[:3]] == sorted(v["archived_at"] for v in h[:3])


def test_reviews_log_entry_carries_the_generated_time(ihc_case, monkeypatch):
    _fake(monkeypatch, [GOOD])
    first = asyncio.run(summary.build(ihc_case, force=True))
    service.review(ihc_case, "summary", "reviewed", "", "dr.rao")
    second = asyncio.run(summary.build(ihc_case, force=True))
    service.review(ihc_case, "summary", "flagged", "Recheck", "dr.iyer")
    log = store.get_state(ihc_case)["reviews"]
    assert [(r["artefact"], r["status"], r["generated"]) for r in log] == [("summary", "reviewed", first["generated"]),
                                                                           ("summary", "flagged", second["generated"])]


def test_history_without_a_summary_is_empty():
    assert summary.history({}) == [] and summary.history({"artefacts": {}}) == []


def test_the_history_list_itself_cannot_be_reviewed(ihc_case, monkeypatch):
    _fake(monkeypatch, [GOOD])
    asyncio.run(summary.build(ihc_case, force=True)); asyncio.run(summary.build(ihc_case, force=True))
    with pytest.raises(ValueError, match="each version keeps the review it had"):  # refused in plain words (Phase 3 review M7)
        service.review(ihc_case, "summary_history", "reviewed", "", "dr.rao")
    assert store.get_state(ihc_case).get("reviews") == []
