"""Pick between two values (night-v3 item 1.7, design B5, owner decision D9): when two reports differ, the doctor picks the report whose value
the board uses. It is a `board_uses` confirmation (audited, undoable, kept in state.json so it survives a re-process); rules.resolve_facts
gives the picked value as the current one, so the slots, the steps, the summary and the slides agree; the difference stays listed and noted.
Synthetic Case Files only (the TB-001 fixture plus one hand-made CT report); no model is ever called."""
import asyncio

import pytest

from tumour_board import confirm, discord, llm, meetings, rules, service, slots, steps, store, summary
from tumour_board.tests import util
from tumour_board.tests.test_nik_slots import CASE, FakeAuth, nik_app, people, tb001  # noqa: F401

NEW_CT = "DCT0907"
NEW_VALUE = "4.6 cm"


def _add_second_ct():
    """A second final CT of the same day as the PET-CT (5.2 cm) that writes another size: two reports differ (review)."""
    util.add(CASE, util.make_doc(NEW_CT, "ct", date="2026-09-06", region="thorax", title="CECT THORAX (SYNTHETIC)",
                                 facts={"lesion_size": util.fact(NEW_VALUE, quote="Largest lesion measures 4.6 cm")}))
    service.recheck(CASE, "test")


def _facts():
    st = store.get_state(CASE)
    return rules.resolve_facts(rules.case_docs(CASE, st), st.get("overrides"))


def _sides():
    """(the report the newest-final rule uses, the other report of the difference) as (doc_id, value)."""
    cur = _facts()["lesion_size"]["current"]
    it = next(x for x in discord.items(CASE) if x["field"] == "lesion_size" and x["severity"] == "review")
    other = next(c for c in it["citations"] if c["doc_id"] != cur["doc_id"])
    return (cur["doc_id"], cur["value"]), (other["doc_id"], other["value"])


def _steps(tc):
    r = tc.get(f"/api/tb/cases/{CASE}/steps")
    assert r.status_code == 200, r.text
    return r.json()


def _problem(v):
    return next((p for p in v["check"]["problems"] if p["fact_id"] == "lesion_size"), None)


def _pick(tc, doc_id, value, reason=""):
    return tc.post(f"/api/tb/cases/{CASE}/confirmations", json={"type": "board_uses", "key": "lesion_size", "fields": {"doc_id": doc_id, "value": value}, "reason": reason})


@pytest.fixture
def two_cts(nik_app, tb001):
    _add_second_ct()
    return nik_app


# ---- the confirmation itself ----------------------------------------------------------------------------------------------------------

def test_board_uses_is_checked_before_it_is_stored():
    assert confirm.TYPES["board_uses"]["fields"] == ["doc_id", "value"]
    clean = confirm.validate("board_uses", "lesion_size", {"doc_id": "D1", "value": " 4.6 cm ", "other": "x"})
    assert clean == {"type": "board_uses", "key": "lesion_size", "fields": {"doc_id": "D1", "value": "4.6 cm"}, "reason": ""}
    for key, fields in (("lesion size!", {"doc_id": "D1", "value": "4.6 cm"}), ("lesion_size", {"value": "4.6 cm"}), ("lesion_size", {"doc_id": "D1", "value": ""})):
        with pytest.raises(ValueError):
            confirm.validate("board_uses", key, fields)


def test_a_value_the_report_does_not_give_is_refused(two_cts):
    tc, who = two_cts
    r = _pick(tc, NEW_CT, "4.5 cm")
    assert r.status_code == 400 and confirm.PICK_GONE in r.text
    assert _pick(tc, "DX0000", NEW_VALUE).status_code == 400  # not a report of this Case File
    assert not confirm.active(CASE, "board_uses")
    with pytest.raises(ValueError, match="no longer gives this value"):
        confirm.record(CASE, "board_uses", "lesion_size", {"doc_id": NEW_CT, "value": "4.6"}, by="dr.rao")


# ---- the pick, everywhere -------------------------------------------------------------------------------------------------------------

def test_the_consultant_picks_the_value_the_board_uses(two_cts, monkeypatch):
    tc, who = two_cts
    (cur_doc, cur_value), (pick_doc, pick_value) = _sides()
    assert cur_value != pick_value
    before = _steps(tc)
    p = _problem(before)
    assert p and not p.get("resolved") and p["why"] == "Two reports differ" and p["confirmation"]["type"] == "note_discordance"
    left = before["left"]
    assert left == steps.open_count(CASE)

    r = _pick(tc, pick_doc, pick_value, "the board reads the newer CT")
    assert r.status_code == 200, r.text
    rec = r.json()["confirmation"]
    assert rec["type"] == "board_uses" and rec["key"] == "lesion_size" and rec["fields"] == {"doc_id": pick_doc, "value": pick_value} and rec["by"] == "dr.rao"
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "confirmation" and e.get("type") == "board_uses"]
    assert len(ev) == 1 and ev[0]["by"] == "dr.rao" and ev[0]["fields"]["doc_id"] == pick_doc
    assert store.get_state(CASE)["overrides"]["picks"]["lesion_size"]["confirmation"] == rec["id"]

    # the value the board uses, with its own verified quote and who picked it
    cur = _facts()["lesion_size"]["current"]
    assert cur["doc_id"] == pick_doc and cur["value"] == pick_value and cur["quote"] and cur["verification"] == "verified"
    assert cur["picked"] == {"doc_id": pick_doc, "value": pick_value, "by": "dr.rao", "at": rec["at"], "confirmation": rec["id"]}
    # the difference stays listed, settled by the pick
    its = [x for x in discord.items(CASE) if x["field"] == "lesion_size" and x["severity"] == "review"]
    assert its and all(x["picked"]["value"] == pick_value and x["picked"]["by_name"] == "Dr Rao" for x in its)
    assert all(f'the board uses "{pick_value}"' in x["text"] and x["text_before_pick"] for x in its)  # never "the newer value counts" after a pick
    assert discord.summary(CASE)["picked"] >= 1
    pts = [x for x in discord.points(CASE) if x.get("picked")]
    assert pts and pts[0]["text"].startswith("Two reports differ on ") and f'the board uses "{pick_value}" (picked by Dr Rao)' in pts[0]["text"]
    assert cur_value in pts[0]["text"] and len(pts[0]["citations"]) == 2
    # the line and the Check step: the picked value, still listed with its pick, no longer left
    s = slots.one(CASE, "fact:lesion_size", None)
    assert s["status"] == "found" and s["value"] == pick_value and s["quote"]["doc_id"] == pick_doc and s["picked"]["confirmation"] == rec["id"]
    after = _steps(tc)
    p2 = _problem(after)
    assert p2["resolved"] is True and p2["picked"]["doc_id"] == pick_doc and p2["value"] == pick_value
    assert p2["why"].startswith(f"Picked: {pick_value} from ") and p2["why"].endswith("by Dr Rao")
    assert after["left"] == left - 1 == steps.open_count(CASE)
    assert not any(t["id"] == f"check:{p2['slot_id']}" for t in after["todo"])
    # the slides read live state
    vals = next(x for x in meetings.slides(CASE) if x["kind"] == "values")["content"]["values"]
    v = next(x for x in vals if x["id"] == "lesion_size")
    assert v["value"] == pick_value and v["doc_id"] == pick_doc and v["quote"]

    # the summary: the picked value among the facts and the difference kept as a point for review
    async def fake_chat(role, msgs, **kw):
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(summary.llm, "chat", fake_chat)
    out = asyncio.run(summary.build(CASE, force=True))
    imaging = " ".join(x["text"] for sec in out["sections"] if sec["id"] == "imaging" for x in sec["sentences"])
    assert f"lesion size: {pick_value}" in imaging.lower()
    assert any("the board uses" in x["text"] and pick_value in x["text"] for x in out["points_for_review"])


def test_a_second_pick_supersedes_the_first_and_undo_restores_the_rule(two_cts):
    tc, who = two_cts
    (cur_doc, cur_value), (pick_doc, pick_value) = _sides()
    left = _steps(tc)["left"]
    first = _pick(tc, pick_doc, pick_value).json()["confirmation"]
    second = _pick(tc, cur_doc, cur_value).json()["confirmation"]
    confs = {c["id"]: c for c in store.get_state(CASE)["confirmations"]}
    assert confs[first["id"]]["undone"]["superseded_by"] == second["id"] and not confs[second["id"]]["undone"]
    assert [c["id"] for c in confirm.active(CASE, "board_uses")] == [second["id"]]
    assert _facts()["lesion_size"]["current"]["picked"]["confirmation"] == second["id"]
    # undo: the newest-final rule again, and the difference is open again
    r = tc.post(f"/api/tb/cases/{CASE}/confirmations/{second['id']}/undo")
    assert r.status_code == 200, r.text
    assert "picks" not in store.get_state(CASE)["overrides"] or "lesion_size" not in store.get_state(CASE)["overrides"]["picks"]
    cur = _facts()["lesion_size"]["current"]
    assert cur["doc_id"] == cur_doc and "picked" not in cur and "pick_stale" not in cur
    assert not any(x.get("picked") for x in discord.items(CASE))
    v = _steps(tc)
    assert not _problem(v).get("resolved") and v["left"] == left
    assert "confirmation_undone" in [e.get("kind") for e in store.read_audit(CASE)]
    assert tc.post(f"/api/tb/cases/{CASE}/confirmations/{second['id']}/undo").status_code == 409


def test_a_pick_whose_report_is_gone_is_ignored_and_flagged(two_cts):
    tc, who = two_cts
    (cur_doc, cur_value), (pick_doc, pick_value) = _sides()
    assert _pick(tc, pick_doc, pick_value).status_code == 200
    left_picked = _steps(tc)["left"]
    # the picked report is replaced by a newer version of itself (superseded): the pick no longer counts
    d = store.get_doc(CASE, pick_doc); d["superseded"] = True; util.add(CASE, d)
    cur = _facts()["lesion_size"]["current"]
    assert "picked" not in cur and cur["pick_stale"] is True and cur["stale_pick"]["doc_id"] == pick_doc
    with pytest.raises(ValueError):
        confirm.check_pick(CASE, "lesion_size", pick_doc, pick_value)
    # a report that failed to read and was dismissed gives no value at all
    d["superseded"] = False; d["state"] = "error"; d["dismissed"] = {"by": "dr.rao", "at": "2026-10-27T09:00:00", "reason": "unreadable"}; util.add(CASE, d)
    assert _facts()["lesion_size"]["current"]["pick_stale"] is True
    d["state"] = "ready"; d.pop("dismissed")
    # the report reads another value after a re-read: the pick is ignored too, and the difference is open again
    d["superseded"] = False; d["facts"]["lesion_size"] = util.fact("4.4 cm", quote="Largest lesion measures 4.4 cm"); util.add(CASE, d)
    cur = _facts()["lesion_size"]["current"]
    assert cur["pick_stale"] is True and cur["value"] != pick_value
    v = _steps(tc)
    assert not _problem(v).get("resolved") and v["left"] == left_picked + 1


def test_re_processing_a_report_keeps_the_pick(two_cts):
    tc, who = two_cts
    (cur_doc, cur_value), (pick_doc, pick_value) = _sides()
    rec = _pick(tc, pick_doc, pick_value).json()["confirmation"]
    # a re-process rewrites doc.json only (the same line read again); the pick lives in state.json
    for doc_id in (pick_doc, cur_doc):
        d = store.get_doc(CASE, doc_id); d["processed"] = "2026-10-27T09:00:00"; util.add(CASE, d)
    service.recheck(CASE, "test")
    cur = _facts()["lesion_size"]["current"]
    assert cur["value"] == pick_value and cur["picked"]["confirmation"] == rec["id"]
    assert _problem(_steps(tc))["resolved"] is True


def test_a_residents_pick_is_signed_off_by_the_consultant(two_cts):
    tc, who = two_cts
    (cur_doc, cur_value), (pick_doc, pick_value) = _sides()
    who["user"] = "res.asha"
    assert _pick(tc, pick_doc, pick_value).status_code == 403  # a resident never confirms on its own
    body = {"type": "board_uses", "key": "lesion_size", "fields": {"doc_id": pick_doc, "value": pick_value}, "reason": ""}
    r = tc.post(f"/api/tb/cases/{CASE}/proposals", json={"action": "confirm", "payload": body, "note": "pick the value for the board"})
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["action"] == "confirm" and p["payload"]["type"] == "board_uses" and p["status"] == "pending"
    assert not confirm.active(CASE, "board_uses") and "picked" not in _facts()["lesion_size"]["current"]
    who["user"] = "dr.rao"
    r = tc.post(f"/api/tb/cases/{CASE}/proposals/{p['id']}/approve")
    assert r.status_code == 200, r.text
    rec = confirm.latest(CASE, "board_uses", "lesion_size")
    assert rec and rec["by"] == "dr.rao" and rec["fields"] == {"doc_id": pick_doc, "value": pick_value}
    assert _facts()["lesion_size"]["current"]["picked"]["by"] == "dr.rao"
