"""After sending (night-v3 item 1.5, design B8, owner decision D9): a new or changed report after the ready mark runs the ready hook again
(never during a meeting) and tells the MDT Coordinator only; a new preliminary value that disagrees with the final one shows both values
with their quotes in the summary and the slides, gives the doctor a "Check 1 value" task and puts "waiting on Dr X" on the agenda row.
Synthetic Case Files only (the TB-001 fixture plus one hand-made preliminary CT report); no model is ever called."""
import asyncio
import json

import pytest

from tumour_board import after_send, agents, confirm, discord, llm, notify, org, ready_hook, rules, service, steps, store, summary
from tumour_board.tests import util
from tumour_board.tests.test_nik_slots import CASE, people, tb001  # noqa: F401

SENT_AT = "2026-10-20T10:00:00"
PRELIM = "DCTPRE01"
PRELIM_VALUE = "4.1 cm"
PRELIM_QUOTE = "Largest lesion measures 4.1 cm"


def _notes():
    p = notify.path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _send(presenter=None, owner=None, withdrawn=False):
    c = store.get_case(CASE)
    c["board_ready"] = {"by": "dr.rao", "at": SENT_AT, "note": ""}
    if presenter:
        c["presenter"] = {"user": presenter, "name": "", "set_by": "dr.rao", "at": SENT_AT}
    if owner:
        c["team"] = {"owner": owner, "residents": []}
    if withdrawn:
        c["board_send"] = {"withdrawn": {"by": "dr.rao", "at": SENT_AT}}
    store.save_case(c)
    return c


def _add_prelim(processed="2026-10-21T09:00:00"):
    """A preliminary CT read after the ready mark that writes another size than the final PET-CT: the difference waits on the doctor."""
    d = util.make_doc(PRELIM, "ct", status="PRELIMINARY", signed="no", date="2026-10-15", region="thorax", title="CECT THORAX PRELIMINARY (SYNTHETIC)",
                      facts={"lesion_size": util.fact(PRELIM_VALUE, quote=PRELIM_QUOTE)})
    d["processed"] = processed
    util.add(CASE, d)
    service.recheck(CASE, "test")


def _diff():
    return discord.open_differences(CASE).get("lesion_size")


@pytest.fixture
def sent(tb001):
    _send()
    _add_prelim()
    return CASE


# ---- the difference: both values, the task, waiting on ---------------------------------------------------------------------------------

def test_a_new_preliminary_value_that_disagrees_shows_both_values_with_their_quotes(sent):
    it = next(x for x in discord.items(CASE) if x["field"] == "lesion_size" and x["severity"] == "review")
    assert it["kind"] == "non_final_differs"  # the "only preliminary" case is the existing kind: nothing added for it
    vals = discord.both_values(CASE, "lesion_size")
    assert len(vals) == 2 and all(v["quote"] for v in vals)
    final, prelim = vals
    assert final["final"] and final["status"] == "final" and final["doc_id"] != PRELIM
    assert prelim["doc_id"] == PRELIM and prelim["value"] == PRELIM_VALUE and prelim["quote"] == PRELIM_QUOTE and prelim["status"] == "preliminary"
    line = _diff()["line"]
    assert f"\"{PRELIM_VALUE}\" (CECT THORAX PRELIMINARY (SYNTHETIC), preliminary)" in line and "(" in line and "final)" in line
    assert "two reports differ: waiting on the treating doctor's check" in line and "—" not in line
    assert discord.both_values(CASE, "pdl1") == []
    # the slides: one row per value, each with its own quote (meetings.slides calls discord.slide_rows for an open difference)
    rows = discord.slide_rows("lesion_size", _diff(), 3)
    assert [r["id"] for r in rows] == ["lesion_size", "lesion_size#2"] and all(r["quote"] and r["fact_id"] == "lesion_size" for r in rows)
    assert "waiting on the treating doctor's check" in rows[0]["label"] and rows[1]["value"] == f"{PRELIM_VALUE} (preliminary)"


def test_the_check_step_lists_it_and_the_doctor_gets_check_1_value(sent):
    v = steps.build(CASE, org.roles("dr.rao"))
    p = next(x for x in v["check"]["problems"] if x["fact_id"] == "lesion_size")
    assert p["why"] == "Two reports differ" and not p.get("resolved") and p.get("since_sent")
    first = v["todo"][0]
    assert first["id"] == "since_sent" and first["label"] == "Check 1 value" and first["since_sent"] is True and first["section"] == "check"
    assert first["action"] == {"kind": "check", "label": "Check", "slot_id": p["slot_id"]}
    assert not any(t["id"] == f"check:{p['slot_id']}" for t in v["todo"])  # one task, not two
    assert after_send.new_since_sent(CASE) == 1 and after_send.new_docs(CASE) == [PRELIM]


def test_a_difference_before_the_ready_mark_is_not_a_since_sent_task(tb001):
    _send()
    _add_prelim(processed="2026-10-19T09:00:00")  # read before it was sent: the doctor sent it knowing
    v = steps.build(CASE, org.roles("dr.rao"))
    assert any(p["fact_id"] == "lesion_size" for p in v["check"]["problems"])
    assert not any(t.get("since_sent") for t in v["todo"])
    assert after_send.waiting_on(store.get_case(CASE)) is None and after_send.new_since_sent(CASE) == 0


def test_waiting_on_names_the_presenter_else_the_owner_consultant(sent):
    w = after_send.waiting_on(store.get_case(CASE))
    assert w == {"user": "dr.rao", "name": "Dr Rao", "values": 1}  # no presenter, no team owner: the consultant who sent it
    _send(owner="dr.rao", presenter="res.asha")
    assert after_send.waiting_on(store.get_case(CASE))["name"] == "Dr Asha"
    c = store.get_case(CASE); c.pop("presenter"); store.save_case(c)
    assert after_send.waiting_on(store.get_case(CASE))["user"] == "dr.rao"


def test_not_sent_or_withdrawn_waits_on_nobody(tb001):
    _add_prelim()
    assert after_send.waiting_on(store.get_case(CASE)) is None and after_send.new_since_sent(CASE) == 0
    _send(withdrawn=True)
    assert after_send.waiting_on(store.get_case(CASE)) is None
    assert not any(t.get("since_sent") for t in steps.build(CASE, org.roles("dr.rao"))["todo"])


@pytest.mark.parametrize("how", ["pick", "note"])
def test_after_the_doctor_picks_or_notes_nothing_waits(sent, how):
    assert after_send.waiting_on(store.get_case(CASE))
    if how == "pick":
        confirm.record(CASE, "board_uses", "lesion_size", {"doc_id": PRELIM, "value": PRELIM_VALUE}, by="dr.rao")
    else:
        confirm.record(CASE, "note_discordance", _diff()["key"], {}, "read both", by="dr.rao")
    assert after_send.waiting_on(store.get_case(CASE)) is None
    assert not any(t.get("since_sent") for t in steps.build(CASE, org.roles("dr.rao"))["todo"])
    assert discord.both_values(CASE, "lesion_size") == []  # settled: the summary and the slides go back to one value


# ---- after sending: a value a newer final report changed, a value only a preliminary report gives (review fix of item 1.5) ----------------

NEW_CT = "DCTNEW01"
NEW_SIZE = "6.3 cm"
NEW_QUOTE = "Largest lesion now measures 6.3 cm"
MOL_PRE, MOL_FINAL = "DMOLPRE1", "DMOLFIN1"
MET_VALUE = "MET exon 14 skipping not detected"


def _add_new_ct(value=NEW_SIZE, quote=NEW_QUOTE, processed="2026-10-22T09:00:00"):
    """A final CT dated after the PET-CT (5.2 cm) that writes another size: a time-varying value changed after sending."""
    d = util.make_doc(NEW_CT, "ct", date="2026-10-18", region="thorax", title="CECT THORAX FOLLOW-UP (SYNTHETIC)",
                      facts={"lesion_size": util.fact(value, quote=quote)})
    d["processed"] = processed
    util.add(CASE, d)
    service.recheck(CASE, "test")


def _add_met(doc_id, status, processed):
    """A molecular report giving MET, which no earlier report gives (PRELIMINARY first, then FINAL)."""
    d = util.make_doc(doc_id, "molecular", status=status, signed="yes" if status == "FINAL" else "no", date="2026-10-16",
                      title=f"MOLECULAR PANEL {status} (SYNTHETIC)", facts={"met": util.fact(MET_VALUE, quote=f"MET: {MET_VALUE}")})
    d["processed"] = processed
    util.add(CASE, d)
    service.recheck(CASE, "test")


def _check_task(fact_id):
    v = steps.build(CASE, org.roles("dr.rao"))
    p = next((x for x in v["check"]["problems"] if x["fact_id"] == fact_id), None)
    return v, p


def test_a_value_a_newer_final_report_changed_after_sending_shows_both_values_and_the_task(tb001):
    _send()
    _add_new_ct()
    d = discord.open_differences(CASE)["lesion_size"]
    assert d["kind"] == "changed" and d.get("after_send")
    before, new = d["values"]
    assert before["doc_id"] == "D4edcec61" and before["value"] == "5.2 cm" and before["final"] and before["quote"]  # the newest final value read before sending
    assert new["doc_id"] == NEW_CT and new["value"] == NEW_SIZE and new["quote"] == NEW_QUOTE and new["status"] == "final"
    assert "waiting on the treating doctor's check" in d["line"] and "—" not in d["line"]
    rows = discord.slide_rows("lesion_size", d, 4)
    assert [r["value"] for r in rows] == ["5.2 cm (final)", f"{NEW_SIZE} (final)"] and all(r["quote"] for r in rows)
    assert [r["verification"] for r in rows] == [v["verification"] for v in d["values"]] == ["verified", "verified"]
    v, p = _check_task("lesion_size")
    assert p and p.get("since_sent") and not p.get("resolved") and p["confirmation"]["kind"] == "changed"
    assert {c["doc_id"] for c in p["confirmation"]["citations"]} == {"D4edcec61", NEW_CT}
    assert v["todo"][0]["id"] == "since_sent" and v["todo"][0]["label"] == "Check 1 value"
    assert after_send.waiting_on(store.get_case(CASE))["values"] == 1
    # noted: settled, nothing waits, the summary and the slides go back to one value
    confirm.record(CASE, "note_discordance", d["key"], {}, "read both", by="dr.rao")
    assert "lesion_size" not in discord.open_differences(CASE) and after_send.waiting_on(store.get_case(CASE)) is None
    assert not any(t.get("since_sent") for t in steps.build(CASE, org.roles("dr.rao"))["todo"])


def test_a_new_final_report_with_the_same_value_or_read_before_sending_is_not_a_change(tb001):
    _send()
    _add_new_ct(value="5.2 cm", quote="Largest lesion measures 5.2 cm")  # the same as before sending; it still differs from the 2025 CT (2.1 cm)
    assert "lesion_size" not in discord.open_differences(CASE) and after_send.waiting_on(store.get_case(CASE)) is None
    _add_new_ct(processed="2026-10-19T09:00:00")  # another value, but read before the ready mark: the doctor sent it knowing
    assert "lesion_size" not in discord.open_differences(CASE)
    v, p = _check_task("lesion_size")
    assert p is None and not any(t.get("since_sent") for t in v["todo"])


def test_a_value_only_a_preliminary_report_gives_after_sending_waits_until_the_final_lands(tb001, monkeypatch):
    _send()
    assert "met" not in discord.open_differences(CASE)
    _add_met(MOL_PRE, "PRELIMINARY", "2026-10-21T09:00:00")
    d = discord.open_differences(CASE)["met"]
    assert d["kind"] == "preliminary" and len(d["values"]) == 1
    val = d["values"][0]
    assert val["doc_id"] == MOL_PRE and val["value"] == MET_VALUE and val["quote"] == f"MET: {MET_VALUE}" and val["status"] == "preliminary" and not val["final"]
    assert f"\"{MET_VALUE}\" (MOLECULAR PANEL PRELIMINARY (SYNTHETIC), preliminary)" in d["line"] and "waiting on the treating doctor's check" in d["line"]
    assert discord.both_values(CASE, "met") == d["values"]
    rows = discord.slide_rows("met", d)
    assert len(rows) == 1 and rows[0]["value"] == f"{MET_VALUE} (preliminary)" and rows[0]["quote"] and rows[0]["verification"] == "verified"
    # the summary: the value shown "(preliminary)" with its quote
    _fake_model(monkeypatch)
    out = asyncio.run(summary.build(CASE, force=True))
    line = next(x for sec in out["sections"] for x in sec["sentences"] if x.get("differ") and x.get("fact_id") == "met")
    assert "preliminary)" in line["text"] and [c["doc_id"] for c in line["citations"]] == [MOL_PRE] and line["citations"][0]["quote"]
    # the doctor's task
    v, p = _check_task("met")
    assert p and p.get("since_sent") and p["why"] == "Only a preliminary report since sending" and p["value"] == MET_VALUE and p["quote"]["doc_id"] == MOL_PRE
    assert v["todo"][0]["label"] == "Check 1 value" and "only preliminary" in v["todo"][0]["why"]
    assert after_send.waiting_on(store.get_case(CASE))["values"] == 1
    # the final report lands with the same value: it clears
    _add_met(MOL_FINAL, "FINAL", "2026-10-23T09:00:00")
    assert "met" not in discord.open_differences(CASE) and after_send.waiting_on(store.get_case(CASE)) is None
    v, p = _check_task("met")
    assert p is None and not any(t.get("since_sent") for t in v["todo"])


def test_a_preliminary_value_read_before_sending_is_not_a_task(tb001):
    _add_met(MOL_PRE, "PRELIMINARY", "2026-10-19T09:00:00")
    _send()
    assert "met" not in discord.open_differences(CASE)
    v, p = _check_task("met")
    assert p is None and not any(t.get("since_sent") for t in v["todo"])
    assert "pdl1" not in discord.open_differences(CASE)  # the draft histopathology of the fixture was read long before sending


def test_slide_rows_carry_each_values_own_verification():
    diff = {"label": "PD-L1", "line": "x", "values": [
        {"value": "60 %", "doc_id": "D1", "doc_title": "A", "final": True, "status": "final", "quote": "TPS 60 %", "verification": "verified"},
        {"value": "6 %", "doc_id": "D2", "doc_title": "B", "final": True, "status": "final", "quote": "TPS 6 %", "verification": "confirmed"}]}
    assert [r["verification"] for r in discord.slide_rows("pdl1", diff)] == ["verified", "confirmed"]


# ---- the summary ------------------------------------------------------------------------------------------------------------------------

def _fake_model(monkeypatch):
    calls = []

    async def fake_chat(role, msgs, **kw):
        calls.append(role)
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat); monkeypatch.setattr(summary.llm, "chat", fake_chat)
    return calls


def test_the_summary_facts_carry_both_values_with_both_quotes(sent, monkeypatch):
    _fake_model(monkeypatch)
    out = asyncio.run(summary.build(CASE, force=True))
    lines = [x for sec in out["sections"] for x in sec["sentences"] if x.get("differ")]
    assert len(lines) == 1 and lines[0]["fact_id"] == "lesion_size"
    assert "waiting on the treating doctor's check" in lines[0]["text"] and PRELIM_VALUE in lines[0]["text"]
    assert {c["doc_id"] for c in lines[0]["citations"]} == {v["doc_id"] for v in discord.both_values(CASE, "lesion_size")}
    assert all(c["quote"] for c in lines[0]["citations"])
    imaging = [x["text"] for sec in out["sections"] if sec["id"] == "imaging" for x in sec["sentences"]]
    assert not any(t.lower().startswith("largest lesion size:") or t.startswith("Lesion size:") for t in imaging if "differ" not in t)  # no single value line
    assert out["differences"][0]["fact_id"] == "lesion_size"


# ---- the hook runs again ----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def hook(monkeypatch):
    prepared = []

    async def fake_prepare(case_id, role):
        prepared.append(role)
        return {"brief": {"sections": []}}
    monkeypatch.setattr(agents, "prepare", fake_prepare)
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)
    monkeypatch.setattr(ready_hook, "RUNNING", {})
    monkeypatch.setattr(ready_hook, "AGAIN", set())
    return prepared


def _hook_steps():
    return [e.get("step") for e in store.read_audit(CASE) if e.get("kind") == "ready_hook"]


def test_a_new_report_after_sending_runs_the_hook_again_and_tells_the_coordinator_only(sent, monkeypatch, hook):
    calls = _fake_model(monkeypatch)
    before = len(_notes())
    out = asyncio.run(ready_hook.run(CASE, "Vaidyx (automatic)", again=True))
    assert out["again"] and "summary" in out["done"] and calls == ["reasoner"]
    assert "again" in _hook_steps() and "start" not in _hook_steps()
    summ = store.get_state(CASE)["artefacts"]["summary"]
    assert any(x.get("differ") for sec in summ["sections"] for x in sec["sentences"])  # rebuilt with both values
    new = _notes()[before:]
    assert [n["kind"] for n in new] == ["record_arrived"] and new[0]["to"] == {"role": "coordinator"}
    assert "1 new or changed report since it was sent; the summary and the slides are updated." in new[0]["text"]
    assert "1 value needs the treating doctor's check: waiting on Dr Rao." in new[0]["text"]
    assert new[0]["title"].startswith("New record after the ready mark: ") and "—" not in new[0]["text"]
    # the first run (the ready mark itself) still tells the owner, not the coordinator
    st = store.get_state(CASE); st["artefacts"].pop("summary"); store.save_state(CASE, st)
    before = len(_notes())
    asyncio.run(ready_hook.run(CASE, "dr.rao"))
    assert [n["kind"] for n in _notes()[before:]] == ["summary_ready"]


def test_the_hook_waits_while_a_meeting_is_in_session(sent, monkeypatch, hook):
    calls = _fake_model(monkeypatch)
    looks = iter([True, True, False])
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: next(looks))
    monkeypatch.setattr(ready_hook, "MEETING_DELAY", 0)
    out = asyncio.run(ready_hook.run(CASE, "x", again=True))
    assert out["waited"] == 2 and calls == ["reasoner"]
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: True)
    monkeypatch.setattr(ready_hook, "MAX_WAITS", 0)
    before = len(_notes())
    out = asyncio.run(ready_hook.run(CASE, "x", again=True))
    assert out["failed"] == ["meeting"] and calls == ["reasoner"] and _notes()[before:] == []  # nothing during the session


def test_a_record_arriving_during_a_run_makes_it_go_once_more(sent, monkeypatch, hook):
    monkeypatch.setenv("TB_SCHEDULER", "1")
    seen = []

    async def fake_build(case_id, force=False):
        seen.append(case_id)
        if len(seen) == 1:  # a second report lands while the first pass writes the summary
            assert ready_hook.on_ready(case_id, "x", again=True)["how"] == "running"
        return {"status": "ready"}
    monkeypatch.setattr(summary, "build", fake_build)
    out = asyncio.run(ready_hook.run(CASE, "x", again=True))
    assert out["passes"] == 2 and len(seen) == 2 and _hook_steps().count("again") == 2
    assert not ready_hook.running(CASE) and CASE not in ready_hook.AGAIN


def test_a_record_arriving_during_the_last_pass_is_kept_for_the_next_call(sent, monkeypatch, hook):
    monkeypatch.setenv("TB_SCHEDULER", "1")
    seen = []

    async def fake_build(case_id, force=False):
        seen.append(case_id)
        assert ready_hook.on_ready(case_id, "x", again=True)["how"] == "running"  # a report lands during every pass, the last one too
        return {"status": "ready"}
    monkeypatch.setattr(summary, "build", fake_build)
    out = asyncio.run(ready_hook.run(CASE, "x", again=True))
    assert out["passes"] == ready_hook.MAX_PASSES == len(seen)
    assert _hook_steps().count("again_deferred") == 1 and CASE not in ready_hook.AGAIN and not ready_hook.running(CASE)
    assert store.get_state(CASE)[ready_hook.NEEDS_AGAIN]["by"] == "x"  # never dropped: kept for the next call
    runs = []

    async def fake_run(case_id, user, again=False):
        runs.append((case_id, again))
        return {}
    monkeypatch.setattr(ready_hook, "run", fake_run)
    res = ready_hook.on_ready(CASE, "Vaidyx (automatic)", again=True)
    assert res["scheduled"] and "again_honoured" in _hook_steps() and ready_hook.NEEDS_AGAIN not in store.get_state(CASE)
    # while a run is going, the flag makes it go once more even for a call that is not a new record
    st = store.get_state(CASE); st[ready_hook.NEEDS_AGAIN] = {"at": "2026-10-27T10:00:00", "by": "x"}; store.save_state(CASE, st)
    ready_hook.RUNNING[CASE] = {"started": 0, "user": "x", "step": "summary"}
    assert ready_hook.on_ready(CASE, "x")["how"] == "running" and CASE in ready_hook.AGAIN
    ready_hook.RUNNING.pop(CASE); ready_hook.AGAIN.discard(CASE)


def test_a_withdrawn_case_file_is_not_updated(sent, monkeypatch, hook):
    calls = _fake_model(monkeypatch)
    _send(withdrawn=True)
    out = asyncio.run(ready_hook.run(CASE, "x", again=True))
    assert out["done"] == [] and calls == [] and "again" not in _hook_steps()


# ---- the trigger in service.process_docs ------------------------------------------------------------------------------------------------

def test_process_docs_runs_the_hook_again_only_for_a_sent_case_file(tb001, monkeypatch):
    from tumour_board import extract
    hits = []
    monkeypatch.setattr(ready_hook, "on_ready", lambda cid, user, again=False: hits.append((cid, user, again)) or {"scheduled": True})

    async def fake_process(case_id, d, prot, patient, progress, **kw):
        doc = store.get_doc(case_id, d); doc["state"] = "ready"; doc["processed"] = store.now_iso(); store.save_doc(case_id, doc)
        progress(d, "ready")
    monkeypatch.setattr(extract, "process_document", fake_process)

    def ingest():
        d = store.add_document_file(CASE, "note.txt", b"SYNTHETIC note " + str(len(hits)).encode() + store.now_iso().encode())
        job = service._job(CASE, 1, [d["doc_id"]])
        asyncio.run(service.process_docs(CASE, [d["doc_id"]], job))
        return job
    assert ingest()["state"] == "finished" and hits == []  # not sent: nothing
    _send(withdrawn=True)
    ingest()
    assert hits == []  # taken off the agenda: nothing
    c = store.get_case(CASE); c.pop("board_send"); c["board_ready"]["at"] = "2026-01-01T00:00:00"; store.save_case(c)
    ingest()
    assert hits == [(CASE, "Vaidyx (automatic)", True)]
