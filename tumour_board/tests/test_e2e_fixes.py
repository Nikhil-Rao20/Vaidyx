"""Fixes found by the live end-to-end scenario (tumour_board/eval/e2e_nik.py, 18 Oct 2026). Synthetic data only."""
from datetime import datetime, timedelta

from tumour_board import access, board, meetings, ready_hook, store


def _session(sid, status, started_at=None, date=None):
    board.sessions_dir().mkdir(parents=True, exist_ok=True)
    s = {"id": sid, "date": date or datetime.now().date().isoformat(), "title": "", "status": status, "created": store.now_iso(), "created_by": "test",
         "started_at": started_at, "started_by": "test" if started_at else None, "closed_at": None, "closed_by": None, "current": None,
         "agenda": [], "attendance": {}, "members": [], "agents": {}, "log": [], "decisions": {}}
    store._write_json(board.sessions_dir() / f"{sid}.json", s)
    return s


def test_running_now_ignores_a_session_left_in_session_from_an_earlier_day():
    now = datetime(2026, 10, 18, 12, 0, 0)
    old = {"status": "in_session", "started_at": "2026-10-14T23:49:18", "date": "2026-10-16"}
    fresh = {"status": "in_session", "started_at": "2026-10-18T10:30:00", "date": "2026-10-18"}
    no_start_today = {"status": "in_session", "date": "2026-10-18"}
    no_start_old = {"status": "in_session", "date": "2026-10-16"}
    assert not board.running_now(old, now)
    assert board.running_now(fresh, now)
    assert board.running_now(no_start_today, now) and not board.running_now(no_start_old, now)
    assert not board.running_now({"status": "planned", "started_at": "2026-10-18T11:00:00"}, now)
    assert not board.running_now({"status": "closed", "started_at": "2026-10-18T11:00:00"}, now)
    assert board.running_now({"status": "in_session", "started_at": "2026-10-18T11:00:00+05:30"}, datetime(2026, 10, 18, 11, 30))  # an offset is fine too


def test_ready_hook_and_scheduler_are_not_held_back_by_a_stale_session():
    stale = (datetime.now() - timedelta(days=4)).isoformat(timespec="seconds")
    _session("S20261016-aaaa", "in_session", started_at=stale, date=(datetime.now() - timedelta(days=2)).date().isoformat())
    assert ready_hook.meeting_in_session() is False and meetings.any_in_session() is False
    _session("S20261018-bbbb", "in_session", started_at=store.now_iso())
    assert ready_hook.meeting_in_session() is True and meetings.any_in_session() is True


# ---- the fill-in summary ------------------------------------------------------------------------------------------------------------------

def _tb002(demo_cases, drop=()):
    """The synthetic breast Case File TB-002, owned by Breast Surgery, with some IHC values removed, its gate evaluated (no model)."""
    import copy
    from tumour_board import org, service
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"dr.nair": {"departments": {"breast_surgery": "member"}, "display_name": "Dr Nair"}}
    org.save(o, by="test")
    c = store.get_case("TB-002"); c["department"] = "breast_surgery"; store.save_case(c)
    for d in store.list_docs("TB-002"):
        if (d.get("classification") or {}).get("doc_type") == "ihc":
            for f in drop:
                (d.get("facts") or {}).pop(f, None)
            store.save_doc("TB-002", d)
    service.recheck("TB-002", "test")
    return "TB-002"


def _slot(view, sid):
    from tumour_board import slots
    return next((s for s in slots._all_slots(view) if s["id"] == sid), None)


def test_a_record_of_values_only_is_not_found_while_its_values_are_missing(demo_cases):
    """Receptor status (ER, PR, HER2) has no document of its own: its line said "found" while the values were not in the file."""
    from tumour_board import org, slots
    cid = _tb002(demo_cases, drop=("er", "pr", "her2"))
    r = org.roles("dr.nair")
    v = slots.build(cid, r)
    rs = _slot(v, "record:receptor_status")
    assert rs["status"] == "not_found" and rs.get("facts_only") and "not_needed" in [a["kind"] for a in rs["actions"]]
    assert {_slot(v, f"fact:{f}")["status"] for f in ("er", "pr", "her2")} == {"not_found"}
    # the line itself is not counted on top of its three values
    assert v["left_before_board"] == sum(1 for s in slots._all_slots(v) if s.get("required") and s["status"] in slots.OPEN and not s.get("facts_only"))
    ki = _slot(v, "fact:ki67")  # Ki-67 the record and Ki-67 the value are one line now (18 Oct), kept in the report: found
    assert ki["status"] == "found" and ki.get("record_id") == "ki67" and _slot(v, "record:ki67") is None
    # the gate names a source document that only says the values are pending (the HPE report "IHC to follow"): still not found
    st = store.get_state(cid)
    hpe = next(d["doc_id"] for d in store.list_docs(cid) if (d.get("classification") or {}).get("doc_type") == "histopathology")
    for q in st["gate"]["requirements"]:
        if q["id"] == "receptor_status":
            q["source_doc_id"] = hpe
    store.save_state(cid, st)
    assert _slot(slots.build(cid, r), "record:receptor_status")["status"] == "not_found"


def test_a_typed_board_question_stands_before_the_notes_line(demo_cases):
    from tumour_board import org, slots
    cid = _tb002(demo_cases)
    r = org.roles("dr.nair")
    q = _slot(slots.build(cid, r), "fact:clinical_question")
    assert q["status"] == "found" and "enter_value" in [a["kind"] for a in q["actions"]]  # a note carries one; the doctor may still type it
    slots.set_value(cid, "fact:clinical_question", "Neoadjuvant systemic therapy or upfront surgery?", "", "dr.nair")
    q = _slot(slots.build(cid, r), "fact:clinical_question")
    assert q["status"] == "entered" and q["value"] == "Neoadjuvant systemic therapy or upfront surgery?" and q["typed_by"] == "dr.nair"
    assert q["report_value"]["quote"]["doc_id"] and q["report_value"]["value"]
    ecog = _slot(slots.build(cid, r), "fact:ecog")  # other values: a signed report still comes first
    slots.set_value(cid, "fact:ecog", "2", "", "dr.nair")
    assert _slot(slots.build(cid, r), "fact:ecog")["status"] == ecog["status"] == "found"


def test_the_agenda_shows_the_typed_board_question():
    case = {"typed_values": {"clinical_question": {"value": "Upfront surgery?", "by": "dr.nair"}}}
    assert meetings._board_question(case) == "Upfront surgery?"
    assert meetings._board_question({"typed_values": [{"id": "clinical_question", "value": "Old shape"}]}) == "Old shape"
    st = {"gate": {"requirements": [{"id": "clinical_history", "evidence": [{"doc_id": "D1", "fact": "clinical_question", "value": "From the note"}]}]}}
    assert meetings._board_question({}, st) == "From the note"
    assert meetings._board_question({}) == ""


# ---- the meeting's shared screen: images and records for the admitted members ----------------------------------------------------------

from tumour_board import org, pacs  # noqa: E402
from tumour_board.tests.test_nik_meetings import UID, As, app, join_and_admit, owned, started, tc  # noqa: E402,F401  (fixtures app, tc)


def _imaging_doc(case_id):
    doc = store.add_document_file(case_id, "ct_thorax.pdf", b"synthetic")
    doc["classification"] = {"title": "CT THORAX", "doc_type": "ct"}
    doc["his"] = {"imaging_study_ref": "ImagingStudy/img-1", "study": {"available": True, "study_uid": UID, "modality": "CT", "checked": store.now_iso()}}
    store.save_doc(case_id, doc)
    return doc


def test_an_admitted_member_without_the_case_files_scope_views_the_shared_images(tc):
    owned("TB-001", department="medical_oncology", owner="dev", residents=())
    mid = started(tc)
    join_and_admit(tc, mid, "ravi")  # Radiology: no request, not a participant: no scope on TB-001
    assert access.scope(org.roles("ravi"), store.get_case("TB-001")) is None
    doc = _imaging_doc("TB-001")
    r = As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "images", "doc_id": doc["doc_id"]})
    assert r.status_code == 200 and "ravi" in r.json()["opened"]["granted"]
    assert pacs.granted("ravi", UID)["session"] == mid
    q = f"StudyInstanceUIDs={UID}"
    assert pacs.check("ohif/viewer", q, org.roles("ravi")) is None
    assert pacs.check(f"dicom-web/studies/{UID}/series", "", org.roles("ravi")) is None
    assert As(tc, "anil").post(f"/meetings/{mid}/end").status_code == 200  # the meeting ends: the viewer ends with it
    assert pacs.check("ohif/viewer", q, org.roles("ravi"))[0] == 403
    pacs.grant("mohan", UID, "TB-001", doc["doc_id"])  # a grant outside any meeting still needs the Case File scope
    assert pacs.check("ohif/viewer", q, org.roles("mohan"))[0] == 403


def test_an_admitted_member_reads_only_the_record_on_the_shared_screen(tc):
    owned("TB-001", department="medical_oncology", owner="dev", residents=())
    mid = started(tc)
    join_and_admit(tc, mid, "ravi")
    shown = store.add_document_file("TB-001", "cbc.pdf", b"synthetic cbc")
    other = next(d for d in store.list_docs("TB-001") if d["doc_id"] != shown["doc_id"])
    assert As(tc, "ravi").get(f"/cases/TB-001/documents/{shown['doc_id']}/file").status_code == 403  # nothing on the screen yet
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "record", "doc_id": shown["doc_id"]}).status_code == 200
    r = As(tc, "ravi").get(f"/cases/TB-001/documents/{shown['doc_id']}/file")
    assert r.status_code == 200 and r.content == b"synthetic cbc"
    assert As(tc, "ravi").get(f"/cases/TB-001/documents/{other['doc_id']}/file").status_code == 403  # only that record
    assert As(tc, "ravi").get(f"/cases/TB-001/documents/{shown['doc_id']}").status_code == 403  # the file only, not the record's data
    assert As(tc, "ravi").get("/cases/TB-001").status_code == 403
    assert As(tc, "mohan").get(f"/cases/TB-001/documents/{shown['doc_id']}/file").status_code == 403  # not admitted
    assert As(tc, "anil").post(f"/meetings/{mid}/open", json={"kind": "none"}).status_code == 200
    assert As(tc, "ravi").get(f"/cases/TB-001/documents/{shown['doc_id']}/file").status_code == 403


def test_briefs_queued_by_the_ready_hook_show_as_preparing(demo_cases, monkeypatch):
    from tumour_board import helpers
    cid = _tb002(demo_cases)
    monkeypatch.setitem(ready_hook.RUNNING, cid, {"started": 0, "user": "dr.nair", "step": "summary"})
    rows = {h["role"]: h["brief"] for h in helpers.list_helpers(cid, org.roles("dr.nair"))}
    assert all(rows[r]["status"] == "preparing" and rows[r]["queued"] for r in ready_hook.HEADS)
    assert rows["nuclear_medicine"]["status"] == "none"  # on click only
    ready_hook.RUNNING[cid]["step"] = "pathology"
    rows = {h["role"]: h["brief"] for h in helpers.list_helpers(cid, org.roles("dr.nair"))}
    assert rows["pathology"]["status"] == "preparing" and rows["pathology"]["queued"] is False and rows["medical_oncology"]["queued"] is True
    assert rows["radiology"]["status"] == "none"  # its turn has passed (the fixture has no brief): not shown as coming
    ready_hook.RUNNING.pop(cid)
    assert {h["brief"]["status"] for h in helpers.list_helpers(cid, org.roles("dr.nair"))} == {"none"}


# ---- a Case File deleted while background work runs on it ---------------------------------------------------------------------------------

def test_writes_to_a_deleted_case_file_are_dropped_until_it_is_created_again():
    """The ready hook of a deleted Case File re-created its directory with an orphan state.json and audit.jsonl (18 Oct, e2e)."""
    store.create_case("TB-GHOST", {"name": "SYNTHETIC, Ghost", "mrn": "SYN-1", "agesex": "50 Y / F"}, "breast", created_by="test")
    doc = store.add_document_file("TB-GHOST", "a.txt", b"synthetic")
    store.delete_case("TB-GHOST")
    d = store.case_dir("TB-GHOST")
    store.audit("TB-GHOST", {"kind": "ready_hook", "step": "radiology"})
    st = store.get_state("TB-GHOST"); st["artefacts"]["brief_radiology"] = {"sections": []}
    store.save_state("TB-GHOST", st)
    store.save_doc("TB-GHOST", doc)
    store.save_case({"case_id": "TB-GHOST", "patient": {}})
    assert not d.exists() and store.gone("TB-GHOST") and store.get_case("TB-GHOST") is None
    try:
        store.add_document_file("TB-GHOST", "b.txt", b"synthetic")
        assert False, "a file was added to a deleted Case File"
    except FileNotFoundError:
        pass
    store.create_case("TB-GHOST", {"name": "SYNTHETIC, New", "mrn": "SYN-2", "agesex": "40 Y / M"}, "breast", created_by="test")  # the id again
    assert not store.gone("TB-GHOST") and store.get_state("TB-GHOST")["artefacts"] == {}  # nothing inherited
    store.audit("TB-GHOST", {"kind": "case_created"})
    assert [e["kind"] for e in store.read_audit("TB-GHOST")] == ["case_created"]


def test_the_ready_hook_stops_when_its_case_file_is_deleted(demo_cases, monkeypatch):
    import asyncio
    from tumour_board import agents, summary
    cid = _tb002(demo_cases)

    async def fake_build(case_id, force=False):
        store.delete_case(case_id)  # deleted while the summary was being written
        return {"status": "ready"}
    calls = []

    async def fake_prepare(case_id, role):
        calls.append(role)
        return {"brief": {}}
    monkeypatch.setattr(summary, "build", fake_build)
    monkeypatch.setattr(agents, "prepare", fake_prepare)
    monkeypatch.setattr(ready_hook, "meeting_in_session", lambda: False)
    monkeypatch.setattr(ready_hook, "RUNNING", {})
    out = asyncio.run(ready_hook.run(cid, "dr.nair"))
    assert calls == [] and "deleted" in out["failed"] and not store.case_dir(cid).exists()
