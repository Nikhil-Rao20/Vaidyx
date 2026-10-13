"""Board sessions (V1 items 6.1 and 6.3): session from the Case Files listed for a date, attendance, agent log vs board decision, export.
Synthetic Case Files in the temporary data root only; no model calls."""
import html
import json

import pytest

from tumour_board import board, config, store
from tumour_board.tests import util

DATE = "2026-10-20"


def _case(cid, board_date=DATE, protocol="lung_nsclc", listed_at=None, name="SYNTHETIC, Board Patient"):
    store.create_case(cid, {**util.PATIENT, "name": name}, protocol, board_date=board_date, created_by="test")
    if listed_at:
        c = store.get_case(cid); c["listing"]["listed_at"] = listed_at; store.save_case(c)


@pytest.fixture
def cases(monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-PROT"})
    _case("TB-B", listed_at="2026-10-01T09:00:00")
    _case("TB-A", listed_at="2026-10-01T10:00:00")
    _case("TB-C", listed_at="2026-10-01T09:00:00")
    _case("TB-PROT", listed_at="2026-10-01T08:00:00")      # protected: real patient data stand-in (synthetic here)
    _case("TB-OTHER", board_date="2026-10-27")             # another board date
    _case("TB-UNL", protocol="")                           # awaiting listing
    c = store.get_case("TB-UNL"); c["board_date"] = DATE; store.save_case(c)
    return ["TB-B", "TB-C", "TB-A"]


BRIEF = {"role": "pathology", "label": "Pathology support", "generated": "2026-10-20T09:00:00", "model": "Gemma-4-31B-it",
         "sections": [{"heading": "Histology", "items": [
             {"text": "Adenocarcinoma on biopsy.", "citations": [{"doc_id": "D1", "doc_title": "HISTOPATHOLOGY REPORT", "quote": "Diagnosis: Adenocarcinoma"}]},
             {"text": "PD-L1 22C3 TPS 60%.", "citations": [{"doc_id": "D2", "quote": "TPS 60%"}]}]}],
         "points_for_review": [{"text": "Is the EGFR result on the record?", "citations": [{"doc_id": "D1", "quote": "EGFR pending"}],
                                "references": [{"org": "ICMR", "title": "Consensus document for lung cancer", "page": 12, "region": "India",
                                                "quote": "EGFR mutation testing should be reported"}]}],
         "not_documented": []}


def _session(cases, **kw):
    return board.create(DATE, "coord", **kw)


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ---- V1 item 6.1: session and attendance -------------------------------------------------------------------------------

def test_listed_for_date_order_and_exclusions(cases):
    rows = board.listed_for_date(DATE)
    assert [r["case_id"] for r in rows] == cases  # listed_at then case_id; protected, unlisted and other dates excluded
    assert rows[0]["patient"]["mrn"] == util.PATIENT["mrn"] and rows[0]["protocol"] == "lung_nsclc"


def test_older_case_without_listing_counts_as_listed(demo_cases):
    c = store.get_case("TB-001"); assert "listing" not in c
    c["board_date"] = DATE; store.save_case(c)
    assert [r["case_id"] for r in board.listed_for_date(DATE)] == ["TB-001"]


def test_create_from_listed_cases(cases, data_root):
    s = _session(cases, title="Thoracic board")
    assert s["id"].startswith("S20261020-") and len(s["id"]) == len("S20261020-") + 4
    assert [a["case_id"] for a in s["agenda"]] == cases and all(a["status"] == "waiting" for a in s["agenda"])
    assert s["status"] == "planned" and s["title"] == "Thoracic board"
    assert set(s["attendance"]) == {d["id"] for d in board.specialties()} and set(s["attendance"].values()) == {"not_marked"}
    assert "tumour_board" not in s["attendance"]
    assert (data_root / "sessions" / f"{s['id']}.json").exists()
    assert board.get(s["id"]) == s
    assert board.list_sessions()[0] == {"id": s["id"], "date": DATE, "title": "Thoracic board", "status": "planned", "cases": 3,
                                        "created": s["created"], "created_by": "coord"}


def test_specialties_roles():
    sp = {d["id"]: d for d in board.specialties()}
    assert sp["radiology"]["role"] == "radiology" and sp["radiology"]["name"] == "Radiology"
    assert sp["biochemistry"]["role"] is None and "coordinator" not in sp and sp["radiology"]["group"] == "supporting"


def test_create_explicit_order_and_validation(cases):
    s = _session(cases, case_ids=["TB-A", "TB-OTHER", "TB-A"])  # explicit: order kept, another date allowed, duplicates dropped
    assert [a["case_id"] for a in s["agenda"]] == ["TB-A", "TB-OTHER"]
    with pytest.raises(ValueError, match="TB-PROT"):
        board.create(DATE, "coord", case_ids=["TB-A", "TB-PROT"])
    with pytest.raises(ValueError, match="TB-UNL.*not listed"):
        board.create(DATE, "coord", case_ids=["TB-UNL"])
    with pytest.raises(ValueError, match="TB-NONE not found"):
        board.create(DATE, "coord", case_ids=["TB-NONE"])
    with pytest.raises(ValueError, match="No Case File is listed for the board on 21/10/2026"):
        board.create("2026-10-21", "coord")
    with pytest.raises(ValueError, match="^Choose at least one Case File for the agenda$"):
        board.create(DATE, "coord", case_ids=[])  # an explicitly empty agenda is not the date-based default
    for bad in ("20/10/2026", "2026-13-01", "", "2026-10-20; rm"):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            board.create(bad, "coord")


def test_real_case_never_joins_even_explicitly(cases, monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-2026-bharath"})
    with pytest.raises(ValueError, match="real patient data"):  # refused before anything is read from it
        board.create(DATE, "coord", case_ids=["TB-2026-bharath"])


def test_set_agenda_keeps_item_state(cases):
    s = _session(cases)
    board.start(s["id"], "coord")
    board.link_decision(s["id"], "TB-C", {"id": "B1", "decision_text": "Discussed"}, "coord")
    s = board.set_agenda(s["id"], ["TB-C", "TB-OTHER", "TB-B"], "coord")  # TB-A removed, TB-OTHER added, reordered
    assert [(a["case_id"], a["status"]) for a in s["agenda"]] == [("TB-C", "decided"), ("TB-OTHER", "waiting"), ("TB-B", "current")]
    with pytest.raises(ValueError, match="TB-PROT"):
        board.set_agenda(s["id"], ["TB-PROT"], "coord")
    s = board.set_agenda(s["id"], ["TB-C", "TB-OTHER"], "coord")  # the current Case File removed: next undecided becomes current
    assert s["current"] == "TB-OTHER" and s["agenda"][1]["status"] == "current"
    kinds = [e["kind"] for e in store.read_audit("TB-A")]
    assert "board_session_agenda_added" in kinds and "board_session_agenda_removed" in kinds


def test_attendance_saved_and_reloaded(cases):
    sid = _session(cases)["id"]
    board.set_attendance(sid, "radiology", "absent", "coord")
    board.set_attendance(sid, "Histopathology", "present", "coord")  # alias resolves to Pathology
    s = board.get(sid)
    assert s["attendance"]["radiology"] == "absent" and s["attendance"]["pathology"] == "present"
    for bad in ("cardiology", "tumour_board", ""):
        with pytest.raises(ValueError, match="Unknown department"):
            board.set_attendance(sid, bad, "present", "coord")
    with pytest.raises(ValueError, match="Attendance must be"):
        board.set_attendance(sid, "pathology", "late", "coord")


def test_members_and_participants(cases):
    sid = _session(cases)["id"]
    s = board.add_member(sid, "  Dr  Anita Rao ", "medical_oncology", "coord")
    m = s["members"][0]
    assert m["name"] == "Dr Anita Rao" and m["id"].startswith("M") and m["department"] == "medical_oncology"
    assert s["attendance"]["medical_oncology"] == "present"  # not_marked -> present
    board.set_attendance(sid, "surgical_oncology", "absent", "coord")
    s = board.add_member(sid, "Dr Vikram Shah", "surgical_oncology", "coord")
    assert s["attendance"]["surgical_oncology"] == "absent"  # an explicit mark is not overridden
    board.set_attendance(sid, "radiology", "absent", "coord")
    board.set_attendance(sid, "pathology", "present", "coord")
    s = board.remove_member(sid, s["members"][1]["id"], "coord")
    p = board.participants(s)
    assert p["text"] == "Dr Anita Rao (Medical Oncology), Pathology; absent: Surgical Oncology, Radiology"
    assert p["present"] == ["Medical Oncology", "Pathology"] and p["absent"] == ["Surgical Oncology", "Radiology"]
    assert board.absent_roles(s) == ["radiology", "surgical_oncology"]
    for bad in ("", "   ", "x" * 121):
        with pytest.raises(ValueError):
            board.add_member(sid, bad, "pathology", "coord")
    with pytest.raises(ValueError, match="not found"):
        board.remove_member(sid, "M000000", "coord")


def test_transitions(cases):
    sid = _session(cases)["id"]
    with pytest.raises(ValueError, match="Start the board session first"):
        board.set_current(sid, "TB-A", "coord")
    s = board.start(sid, "chair")
    assert s["status"] == "in_session" and s["started_by"] == "chair" and s["current"] == "TB-B" and s["agenda"][0]["status"] == "current"
    with pytest.raises(ValueError, match="planned"):
        board.start(sid, "chair")
    s = board.set_current(sid, "TB-C", "chair")
    assert s["current"] == "TB-C" and [a["status"] for a in s["agenda"]] == ["waiting", "current", "waiting"]
    board.link_decision(sid, "TB-C", {"id": "B9", "decision_text": "x"}, "chair")
    s = board.set_current(sid, "TB-A", "chair")
    assert [a["status"] for a in s["agenda"]] == ["waiting", "decided", "current"]
    with pytest.raises(ValueError, match="not on the agenda"):
        board.set_current(sid, "TB-OTHER", "chair")
    s = board.close(sid, "chair")
    assert s["status"] == "closed" and s["closed_by"] == "chair" and s["closed_at"]
    for f in (lambda: board.set_attendance(sid, "pathology", "present", "c"), lambda: board.add_member(sid, "Dr X", "pathology", "c"),
              lambda: board.set_current(sid, "TB-B", "c"), lambda: board.close(sid, "c"), lambda: board.set_agenda(sid, ["TB-A"], "c"),
              lambda: board.log_brief(sid, "TB-A", "pathology", BRIEF)):
        with pytest.raises(ValueError, match="closed"):
            f()
    assert board.export(sid)["session"]["status"] == "closed"
    with pytest.raises(ValueError, match="not found"):
        board.start("S20261020-zzzz", "c")
    assert board.get("../etc") is None and board.get("") is None


# ---- V1 items 6.2 / 6.3: agents and the agent log ------------------------------------------------------------------------

def test_set_agent(cases):
    sid = _session(cases)["id"]
    board.set_agent(sid, "TB-A", "pathology", "running")
    s = board.set_agent(sid, "TB-A", "pathology", "ready", generated="2026-10-20T09:00:00", seconds=12.5, reused=False)
    a = s["agents"]["TB-A"]["pathology"]
    assert a["status"] == "ready" and a["seconds"] == 12.5 and a["at"]
    with pytest.raises(ValueError, match="Unknown agent role"):
        board.set_agent(sid, "TB-A", "cardiology", "ready")
    with pytest.raises(ValueError, match="status"):
        board.set_agent(sid, "TB-A", "pathology", "done")
    with pytest.raises(ValueError, match="not on the agenda"):
        board.set_agent(sid, "TB-OTHER", "pathology", "ready")
    assert [e["kind"] for e in store.read_audit("TB-A") if e["kind"] == "board_session_agent"] == ["board_session_agent"]  # ready only


def test_log_brief_entries_and_superseded(cases):
    sid = _session(cases)["id"]
    assert board.log_brief(sid, "TB-A", "pathology", BRIEF) == 3
    log = board.entries(board.get(sid), "TB-A")
    assert [e["kind"] for e in log] == ["brief_item", "brief_item", "point_for_review"]
    assert [e["id"] for e in log] == ["P1", "P2", "P3"]
    assert log[0]["heading"] == "Histology" and log[0]["label"] == "Pathology support" and log[0]["source"] == "brief"
    assert log[0]["citations"][0]["quote"] == "Diagnosis: Adenocarcinoma" and log[0]["model"] == "Gemma-4-31B-it"
    assert log[0]["brief_generated"] == BRIEF["generated"] and log[0]["mark"] is None and log[0]["note"] == ""
    assert log[2]["references"][0]["org"] == "ICMR" and "references" not in log[0]
    assert board.log_brief(sid, "TB-A", "pathology", BRIEF) == 0  # the same brief is not logged twice
    newer = {**BRIEF, "generated": "2026-10-20T10:00:00", "points_for_review": []}
    assert board.log_brief(sid, "TB-A", "pathology", newer) == 2
    log = board.entries(board.get(sid), "TB-A")
    assert len(log) == 5 and [bool(e.get("superseded")) for e in log] == [True, True, True, False, False]
    nd = {"role": "radiology", "label": "Radiology support", "no_documents": True, "message": "No radiology documents in the Case File."}
    assert board.log_brief(sid, "TB-A", "radiology", nd) == 1
    e = board.entries(board.get(sid), "TB-A")[-1]
    assert e["kind"] == "no_documents" and e["text"] == nd["message"] and e["id"] == "P6"
    assert not any(x.get("superseded") for x in board.entries(board.get(sid), "TB-A") if x["role"] == "pathology" and x["id"] in ("P4", "P5"))
    with pytest.raises(ValueError, match="Unknown agent role"):
        board.log_brief(sid, "TB-A", "oncology", BRIEF)


def test_log_answer(cases):
    sid = _session(cases)["id"]
    ans = {"status": "answered", "label": "Pathology support", "model": "Gemma-4-31B-it",
           "statements": [{"text": "TPS is 60%.", "citations": [{"doc_id": "D2", "quote": "TPS 60%"}]}, {"text": "Clone 22C3.", "citations": []}]}
    e = board.log_answer(sid, "TB-A", "pathology", "What is the PD-L1 TPS?", ans)
    assert e["kind"] == "answer" and e["source"] == "live" and e["status"] == "answered" and e["text"] == "TPS is 60%. Clone 22C3."
    assert e["question"] == "What is the PD-L1 TPS?" and len(e["statements"]) == 2 and e["citations"][0]["quote"] == "TPS 60%"
    e2 = board.log_answer(sid, "TB-A", "pathology", "Should we give chemotherapy?",
                          {"status": "out_of_scope", "message": "Outside the agent's scope.", "statements": []})
    assert e2["status"] == "out_of_scope" and e2["text"] == "Outside the agent's scope." and e2["id"] == "P2"
    assert [x["kind"] for x in store.read_audit("TB-A")].count("board_session_answer") == 2


def test_mark_only_after_decision(cases):
    sid = _session(cases)["id"]
    board.log_brief(sid, "TB-A", "pathology", BRIEF)
    with pytest.raises(ValueError, match="Record the board decision first"):
        board.mark(sid, "TB-A", "P1", "accepted", "chair")
    rec = {"id": "Babc123", "decision_text": "Await EGFR result; re-discuss.", "entered_by": "chair", "recorded_at": "2026-10-20T11:00:00"}
    s = board.link_decision(sid, "TB-A", rec, "coord")
    d = s["decisions"]["TB-A"]
    assert d["board_record"] == "Babc123" and d["recorded_by"] == "chair" and d["linked_by"] == "coord"
    assert next(a for a in s["agenda"] if a["case_id"] == "TB-A")["status"] == "decided"
    s = board.mark(sid, "TB-A", "P1", "accepted", "chair", note="Matches the HPE")
    e = board.entries(s, "TB-A")[0]
    assert (e["mark"], e["mark_by"], e["note"]) == ("accepted", "chair", "Matches the HPE") and e["mark_at"]
    board.close(sid, "chair")  # marking after close is documenting the meeting: allowed
    board.mark(sid, "TB-A", "P3", "not_relevant", "chair")
    s = board.mark(sid, "TB-A", "P1", None, "chair")
    assert board.entries(s, "TB-A")[0]["mark"] is None and board.entries(s, "TB-A")[0]["note"] == ""
    with pytest.raises(ValueError, match="Mark must be"):
        board.mark(sid, "TB-A", "P1", "wrong", "chair")
    with pytest.raises(ValueError, match="not found"):
        board.mark(sid, "TB-A", "P99", "accepted", "chair")
    with pytest.raises(ValueError, match="no id"):
        board.link_decision(sid, "TB-A", {"decision_text": "x"}, "coord")


# ---- V1 item 6.3: export, side by side ---------------------------------------------------------------------------------

def _decided_session(cases, decision="Await EGFR result <script>alert(1)</script>; re-discuss."):
    sid = _session(cases)["id"]
    board.add_member(sid, "Dr Anita Rao", "medical_oncology", "coord")
    board.set_attendance(sid, "pathology", "absent", "coord")
    board.start(sid, "chair")
    board.log_brief(sid, "TB-A", "pathology", BRIEF)
    board.log_brief(sid, "TB-A", "pathology", {**BRIEF, "generated": "2026-10-20T10:00:00", "points_for_review": []})
    board.log_answer(sid, "TB-A", "pathology", "PD-L1?", {"status": "answered", "label": "Pathology support", "model": "Gemma-4-31B-it",
                                                         "statements": [{"text": "TPS 60%.", "citations": [{"doc_id": "D2", "quote": "TPS 60%"}]}]})
    board.link_decision(sid, "TB-A", {"id": "Babc123", "decision_text": decision, "entered_by": "chair", "recorded_at": "2026-10-20T11:00:00"}, "coord")
    board.mark(sid, "TB-A", "P4", "accepted", "chair", note="Confirmed")
    board.mark(sid, "TB-A", "P6", "discussed", "chair")
    board.mark(sid, "TB-A", "P3", "not_relevant", "chair")  # a superseded point can still be marked
    return sid


def test_export_side_by_side(cases):
    sid = _decided_session(cases)
    x = board.export(sid)
    assert x["session"]["id"] == sid and x["session"]["status"] == "in_session" and x["absent_roles"] == ["pathology"]
    assert x["note"] == board.NOTE and "accuracy" in x["note"]
    att = {a["department"]: a for a in x["attendance"]}
    assert att["medical_oncology"]["members"] == ["Dr Anita Rao"] and att["pathology"]["status"] == "absent"
    c = next(c for c in x["cases"] if c["case_id"] == "TB-A")
    assert c["patient"] == {"name": "SYNTHETIC, Board Patient", "mrn": util.PATIENT["mrn"], "agesex": util.PATIENT["agesex"]}
    assert [e["id"] for e in c["agent_log"]] == ["P4", "P5", "P6", "P1", "P2", "P3"]  # superseded last
    assert c["decision"]["board_record"] == "Babc123" and "Await EGFR" in c["decision"]["decision_text"]
    assert c["marks"] == {"discussed": 1, "accepted": 1, "not_relevant": 1, "unmarked": 1}
    other = next(c for c in x["cases"] if c["case_id"] == "TB-B")
    assert other["decision"] is None and other["agent_log"] == []


def test_export_html(cases):
    sid = _decided_session(cases)
    h = board.export_html(sid)
    assert "Board session 20/10/2026: agent log and board decision" in h
    assert "What the AI support agents said (role-specific, AI draft)" in h and "What the board decided" in h
    assert "Await EGFR result &lt;script&gt;alert(1)&lt;/script&gt;; re-discuss." in h and "<script" not in h
    assert h.count("Await EGFR result") == 1  # the decision once per case
    for m in ("Accepted", "Discussed", "Not relevant", "Not marked", "Confirmed"):
        assert m in h
    assert "[HISTOPATHOLOGY REPORT, Diagnosis: Adenocarcinoma]" in h and "[D2, TPS 60%]" in h
    assert "Reference: ICMR, Consensus document for lung cancer, page 12, EGFR mutation testing should be reported" in h
    assert "Question: PD-L1?" in h and "superseded" in h and "Dr Anita Rao" in h
    assert board.NOTE in h and "Gemma-4-31B-it (non-medical)" in h
    assert "AI support agents' model: Gemma-4-31B-it (non-medical)</p>" in h
    assert "AI support agents prepared briefs for the absent specialties: Pathology</div>" in h
    assert "\u2014" not in h and "2026-10-20" not in h  # no em dash; Indian date format


def test_export_html_no_em_dash_from_source_text(cases):
    sid = _decided_session(cases, decision="Re-discuss \u2014 after EGFR")
    assert "\u2014" not in board.export_html(sid)


# ---- audit -------------------------------------------------------------------------------------------------------------

def test_audit_both_logs(cases, data_root):
    sid = _decided_session(cases)
    ev = _jsonl(data_root / "sessions" / "audit.jsonl")
    kinds = [e["kind"] for e in ev]
    for k in ("created", "agenda_added", "member_added", "attendance", "started", "current", "brief_logged", "answer_logged",
              "decision_linked", "mark"):
        assert k in kinds, k
    assert all(e["session"] == sid and "ts" in e and "by" in e for e in ev)
    case_kinds = [e["kind"] for e in store.read_audit("TB-A") if e.get("session") == sid]
    for k in ("board_session_agenda_added", "board_session_answer", "board_session_decision", "board_session_mark"):
        assert k in case_kinds, k
    assert [e for e in store.read_audit("TB-B") if e.get("kind") == "board_session_current"][0]["by"] == "chair"
    assert not (data_root / "cases" / "TB-PROT" / "audit.jsonl").exists()  # the protected Case File is never written to


def test_audit_session_public_writer(cases, data_root):
    sid = _session(cases)["id"]
    board.audit_session(sid, {"kind": "agents_prepare", "by": "coord", "roles": ["pathology"], "session": "ignored"})
    ev = _jsonl(data_root / "sessions" / "audit.jsonl")[-1]
    assert ev["kind"] == "agents_prepare" and ev["session"] == sid and ev["roles"] == ["pathology"] and ev["ts"]
    assert board.read_audit()[-1] == ev


def test_set_agent_creates_missing_entry(cases):
    sid = _session(cases)["id"]
    s = board.set_agent(sid, "TB-C", "radiation_oncology", "queued")
    assert s["agents"]["TB-C"]["radiation_oncology"]["status"] == "queued" and board.get(sid)["agents"] == s["agents"]


def test_log_brief_keeps_not_documented_items_flags_and_open_requests(demo_cases):
    """What the agent said includes the gaps it named and its items' check flags; a no-documents brief carries its department's open requests."""
    s = board.create("2026-09-18", "coord", ["TB-001"])
    brief = {"label": "Radiology support", "generated": "2026-10-11T10:00:00", "model": "Gemma", "not_documented": ["No brain MRI report"],
             "sections": [{"heading": "Imaging", "items": [{"text": "Mass 3.2 cm.", "citations": [], "flags": ["approximate source match: check source"]}]}],
             "points_for_review": []}
    assert board.log_brief(s["id"], "TB-001", "radiology", brief) == 2
    log = board.entries(board.get(s["id"]), "TB-001")
    assert [e["kind"] for e in log] == ["brief_item", "not_documented"] and log[0]["flags"] == ["approximate source match: check source"]
    assert "Check: approximate source match: check source" in board.export_html(s["id"]) and "Not documented" in board.export_html(s["id"])
    nd = {"label": "Nuclear medicine support", "generated": "2026-10-11T10:01:00", "no_documents": True, "message": "No Nuclear Medicine documents in this Case File",
          "open_items": [{"label": "PET-CT", "what": "No final, signed PET-CT report"}]}
    board.log_brief(s["id"], "TB-001", "nuclear_medicine", nd)
    e = [x for x in board.entries(board.get(s["id"]), "TB-001") if x["kind"] == "no_documents"][0]
    assert e["text"] == "No Nuclear Medicine documents in this Case File. Open requests: PET-CT: No final, signed PET-CT report"


# ---- review fixes (Phase 6 review) -------------------------------------------------------------------------------------

def test_close_fails_waiting_agents(cases, data_root):
    """S3: closing while briefs are preparing leaves no agent queued / running; later loads see errors, not a stuck session."""
    sid = _session(cases)["id"]
    board.set_agent(sid, "TB-A", "pathology", "queued")
    board.set_agent(sid, "TB-A", "radiology", "running")
    board.set_agent(sid, "TB-B", "pathology", "ready", generated="2026-10-20T09:00:00")
    s = board.close(sid, "chair")
    ag = board.get(sid)["agents"]
    assert s["status"] == "closed" and ag == s["agents"]
    for role in ("pathology", "radiology"):
        a = ag["TB-A"][role]
        assert a["status"] == "error" and a["message"] == "The session was closed before the brief was ready" and a["at"]
    assert ag["TB-B"]["pathology"]["status"] == "ready" and ag["TB-B"]["pathology"]["generated"] == "2026-10-20T09:00:00"
    ev = [e for e in _jsonl(data_root / "sessions" / "audit.jsonl") if e["kind"] in ("agents_failed", "closed")]
    assert [e["kind"] for e in ev] == ["agents_failed", "closed"]
    assert ev[0]["pairs"] == [["TB-A", "pathology"], ["TB-A", "radiology"]] and ev[0]["by"] == "system"
    for f in (lambda: board.set_agent(sid, "TB-A", "pathology", "ready"), lambda: board.log_brief(sid, "TB-A", "pathology", BRIEF),
              lambda: board.log_answer(sid, "TB-A", "pathology", "Q?", {"statements": []})):
        with pytest.raises(ValueError, match="closed"):
            f()


def test_fail_waiting_any_status(cases, data_root):
    sid = _session(cases)["id"]
    board.set_agent(sid, "TB-C", "nuclear_medicine", "running")
    s = board.fail_waiting(sid, "The service restarted")
    assert s["agents"]["TB-C"]["nuclear_medicine"]["status"] == "error" and s["agents"]["TB-C"]["nuclear_medicine"]["message"] == "The service restarted"
    n = len(_jsonl(data_root / "sessions" / "audit.jsonl"))
    board.fail_waiting(sid, "again")  # nothing waiting: no change, no audit line
    assert len(_jsonl(data_root / "sessions" / "audit.jsonl")) == n
    # a session closed by an older build with agents still running: fail_waiting still works on it
    s = board.get(sid); s["status"] = "closed"; s["agents"]["TB-C"]["nuclear_medicine"]["status"] = "queued"; board._save(s)
    s = board.fail_waiting(sid, "Closed earlier")
    assert board.get(sid)["agents"]["TB-C"]["nuclear_medicine"] == {"status": "error", "message": "Closed earlier",
                                                                    "at": s["agents"]["TB-C"]["nuclear_medicine"]["at"]}
    assert _jsonl(data_root / "sessions" / "audit.jsonl")[-1]["kind"] == "agents_failed"
    with pytest.raises(ValueError, match="not found"):
        board.fail_waiting("S20261020-zzzz", "x")


APPROX = {**BRIEF, "generated": "2026-10-20T12:00:00",
          "sections": [{"heading": "Histology", "items": [
              {"text": "Near-match item text.", "approximate": True, "flags": ["approximate source match: check source"],
               "citations": [{"doc_id": "D1", "quote": "Near quote"}]},
              {"text": "Exact item.", "citations": [{"doc_id": "D1", "quote": "Exact quote"}]}]}],
          "points_for_review": [{"text": "Near-match point.", "approximate": True, "citations": [{"doc_id": "D1", "quote": "Near point quote"}],
                                 "references": [{"org": "NCG", "title": "Guideline", "quote": "Near ref quote"}]}]}


def _brief_artefact(cid, role, generated, review):
    st = store.get_state(cid); st.setdefault("artefacts", {})[f"brief_{role}"] = {"generated": generated, "review": {"status": review}}
    store.save_state(cid, st)


def test_approximate_items_printed_only_after_review(cases):
    """M4 / 6.5: near-match items stay in the log and the JSON export; the printable export holds them back until the brief is reviewed."""
    sid = _session(cases)["id"]
    assert board.log_brief(sid, "TB-A", "pathology", APPROX) == 3
    log = board.entries(board.get(sid), "TB-A")
    assert [e["approximate"] for e in log] == [True, False, True]
    c = next(c for c in board.export(sid)["cases"] if c["case_id"] == "TB-A")
    assert [(e["approximate"], e["printable"]) for e in c["agent_log"]] == [(True, False), (False, True), (True, False)]
    assert c["agent_log"][0]["text"] == "Near-match item text."  # JSON keeps the entry
    for review in (None, "pending"):  # no artefact, then an artefact not yet reviewed
        if review:
            _brief_artefact("TB-A", "pathology", APPROX["generated"], review)
        h = board.export_html(sid)
        assert h.count(board.NOT_PRINTED) == 2 and "Exact item." in h and "Exact quote" in h
        for hidden in ("Near-match item text.", "Near quote", "Near-match point.", "Near point quote", "Near ref quote"):
            assert hidden not in h, hidden
        assert "P1" in h and "P3" in h and "Point for review" in h and h.count("Not marked") >= 3  # label, kind, mark row kept
    _brief_artefact("TB-A", "pathology", "2026-10-20T13:00:00", "reviewed")  # a newer brief was reviewed, not this one
    assert board.export_html(sid).count(board.NOT_PRINTED) == 2
    _brief_artefact("TB-A", "pathology", APPROX["generated"], "reviewed")
    h = board.export_html(sid)
    assert board.NOT_PRINTED not in h and "Near-match item text." in h and "Near point quote" in h and "Near ref quote" in h
    assert all(e["printable"] for e in next(c for c in board.export(sid)["cases"] if c["case_id"] == "TB-A")["agent_log"])


def test_log_answer_who_asked_and_removed(cases, data_root):
    """M6: who asked is on the entry and in the audit; removed statements stay with the entry."""
    sid = _session(cases)["id"]
    removed = [{"text": "TPS 70%.", "reason": "number_not_in_quote"}]
    e = board.log_answer(sid, "TB-A", "pathology", "TPS?", {"status": "answered", "statements": [{"text": "TPS 60%.", "citations": []}],
                                                           "removed": removed}, by="dr.rao")
    assert e["asked_by"] == "dr.rao" and e["removed"] == removed and board.entries(board.get(sid), "TB-A")[0]["removed"] == removed
    ev = [x for x in _jsonl(data_root / "sessions" / "audit.jsonl") if x["kind"] == "answer_logged"][-1]
    assert ev["by"] == "dr.rao"
    assert [x for x in store.read_audit("TB-A") if x["kind"] == "board_session_answer"][-1]["by"] == "dr.rao"
    e = board.log_answer(sid, "TB-A", "pathology", "Q2?", {"statements": []})
    assert e["asked_by"] == "" and e["removed"] == [] and e["status"] == "not_documented"
    assert [x for x in _jsonl(data_root / "sessions" / "audit.jsonl") if x["kind"] == "answer_logged"][-1]["by"] == "system"


def test_model_words():
    assert board.model_words("Gemma-4-31B-it") == "Gemma-4-31B-it (non-medical)"
    assert board.model_words("Gemma-4-31B (non-medical)") == "Gemma-4-31B (non-medical)"
    assert board.model_words("Gemma-4-31B, Non-Medical") == "Gemma-4-31B, Non-Medical"
    for x in (None, "", "reasoner"):
        assert board.model_words(x) == "the reasoner model (non-medical)"


def test_export_html_models_statuses_absent_names(cases):
    """M7 / 16: models always printed as non-medical; refusals and not documented answers labelled; absent specialties by name."""
    sid = _session(cases)["id"]
    board.set_attendance(sid, "radiology", "absent", "coord")
    board.set_attendance(sid, "surgical_oncology", "absent", "coord")
    board.log_brief(sid, "TB-A", "radiology", {**BRIEF, "model": "reasoner"})
    board.log_brief(sid, "TB-A", "pathology", {"label": "Pathology support", "no_documents": True, "message": "No pathology documents"})
    board.log_answer(sid, "TB-A", "pathology", "Give chemo?", {"status": "out_of_scope", "message": "Outside the agent's scope.", "model": "Gemma-4-31B-it"})
    board.log_answer(sid, "TB-A", "pathology", "Ki-67?", {"status": "not_documented", "message": "Not in the record.", "model": None})
    h = html.unescape(board.export_html(sid))
    assert "AI support agents prepared briefs for the absent specialties: Radiology, Surgical Oncology</div>" in h
    assert "surgical_oncology" not in h and "surgical oncology" not in h  # never role ids
    assert "Answer to the board's question \u00b7 Outside the agent's scope (refused)" in h
    assert "Answer to the board's question \u00b7 Not documented in the Case File" in h
    assert "Gemma-4-31B-it (non-medical)" in h and "the reasoner model (non-medical)" in h
    assert "AI support agents' model: the reasoner model (non-medical), Gemma-4-31B-it (non-medical)</p>" in h
    assert "Gemma-4-31B-it<" not in h and "Gemma-4-31B-it &" not in h  # never printed without "(non-medical)"


def test_export_html_quotes_verbatim_other_text_dashed(cases):
    """16: verified quotes are printed exactly as stored (an em dash included); other text has no em dash."""
    sid = _session(cases)["id"]
    brief = {**BRIEF, "sections": [{"heading": "Histology \u2014 core", "items": [
        {"text": "Adenocarcinoma \u2014 on biopsy.", "citations": [{"doc_id": "D1", "quote": "Diagnosis \u2014 Adenocarcinoma"}]}]}],
             "points_for_review": [{"text": "Check \u2014 EGFR", "citations": [],
                                    "references": [{"org": "ICMR", "title": "Lung \u2014 consensus", "quote": "EGFR \u2014 should be reported"}]}]}
    board.log_brief(sid, "TB-A", "pathology", brief)
    h = board.export_html(sid)
    assert "[D1, Diagnosis \u2014 Adenocarcinoma]" in h and "EGFR \u2014 should be reported" in h
    assert "Adenocarcinoma - on biopsy." in h and "Histology - core" in h and "Check - EGFR" in h and "Lung - consensus" in h
    assert h.count("\u2014") == 2


def test_check_cases_uses_safe_id(cases, monkeypatch):
    """19: the protected check is made on the id as stored on disk; a malformed id is refused with a plain message."""
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-2026-bharath"})
    for spelled in ("TB 2026 bharath", "TB/2026/bharath", " TB-2026-bharath "):
        with pytest.raises(ValueError, match="real patient data"):
            board.create(DATE, "coord", case_ids=[spelled])
    for bad in ("", "   ", ".hidden", "../x"):
        with pytest.raises(ValueError, match="^Invalid Case File id"):
            board.create(DATE, "coord", case_ids=[bad])
    with pytest.raises(ValueError, match="^Invalid Case File id 'TB A'$"):  # another spelling of TB-A is not silently accepted
        board.create(DATE, "coord", case_ids=["TB A"])


# ---- V1 item 7.3: an amended decision shows in the session and its export -------------------------------------------------
def test_decision_amended_updates_the_session_and_the_export(cases):
    sid = _decided_session(cases)
    rec = {"id": "Babc123", "decision_text": "Doxorubicin 60 mg/m2 as decided.", "version": 2, "resolution": {"final": True}}
    s = board.decision_amended(sid, "TB-A", rec, "Dr. Rao")
    d = s["decisions"]["TB-A"]
    assert d["decision_text"] == "Doxorubicin 60 mg/m2 as decided." and d["version"] == 2 and d["final"] is True and d["amended_by"] == "Dr. Rao"
    html = board.export_html(sid)
    assert "Doxorubicin 60 mg/m2 as decided." in html and "amended: version 2" in html
    assert board.decision_amended(sid, "TB-A", {**rec, "id": "Bother1"}, "Dr. Rao") is None  # not the record linked to this agenda item
    assert any(e["kind"] == "decision_amended" and e.get("version") == 2 for e in board.read_audit())


def test_v1_attendance_keys_resolve(cases):
    """Review M7: a session stored before the 2.1 migration keys attendance by V1 ids; the board reads them as the V2 departments and a
    new mark replaces the old key."""
    sid = _session(cases)["id"]
    s = board.get(sid)
    s["attendance"] = {"radio_diagnosis": "absent", "pathology": "present", "tumour_board": "present", "laboratory_medicine": "not_marked"}
    board._save(s)
    assert board.attendance(board.get(sid)) == {"radiology": "absent", "pathology": "present", "biochemistry": "not_marked"}
    assert board.absent_roles(board.get(sid)) == ["radiology"] and board.participants(board.get(sid))["absent"] == ["Radiology"]
    s = board.set_attendance(sid, "radiology", "present", "coord")
    assert "radio_diagnosis" not in s["attendance"] and s["attendance"]["radiology"] == "present"
