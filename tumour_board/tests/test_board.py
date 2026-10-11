"""Board sessions (V1 items 6.1 and 6.3): session from the Case Files listed for a date, attendance, agent log vs board decision, export.
Synthetic Case Files in the temporary data root only; no model calls."""
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


BRIEF = {"role": "pathology", "label": "Pathology support", "generated": "2026-10-20T09:00:00", "model": "Gemma-4-31B (non-medical)",
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
    assert sp["radio_diagnosis"]["role"] == "radiology" and sp["radio_diagnosis"]["name"] == "Radio-diagnosis"
    assert sp["laboratory_medicine"]["role"] is None and "tumour_board" not in sp


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
    with pytest.raises(ValueError, match="No Case File"):
        board.create(DATE, "coord", case_ids=[])
    for bad in ("20/10/2026", "2026-13-01", "", "2026-10-20; rm"):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            board.create(bad, "coord")


def test_real_case_never_joins_even_explicitly(cases, monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-2026-bharath"})
    with pytest.raises(ValueError, match="real patient data"):  # refused before anything is read from it
        board.create(DATE, "coord", case_ids=["TB-2026-bharath"])


def test_attendance_saved_and_reloaded(cases):
    sid = _session(cases)["id"]
    board.set_attendance(sid, "radio_diagnosis", "absent", "coord")
    board.set_attendance(sid, "Histopathology", "present", "coord")  # alias resolves to Pathology
    s = board.get(sid)
    assert s["attendance"]["radio_diagnosis"] == "absent" and s["attendance"]["pathology"] == "present"
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
    board.set_attendance(sid, "radio_diagnosis", "absent", "coord")
    board.set_attendance(sid, "pathology", "present", "coord")
    s = board.remove_member(sid, s["members"][1]["id"], "coord")
    p = board.participants(s)
    assert p["text"] == "Dr Anita Rao (Medical Oncology), Pathology; absent: Radio-diagnosis, Surgical Oncology"
    assert p["present"] == ["Pathology", "Medical Oncology"] and p["absent"] == ["Radio-diagnosis", "Surgical Oncology"]
    assert board.absent_roles(s) == ["radiology", "surgical_oncology"]
    for bad in ("", "   ", "x" * 121):
        with pytest.raises(ValueError):
            board.add_member(sid, bad, "pathology", "coord")
    with pytest.raises(ValueError, match="not found"):
        board.remove_member(sid, "M000000", "coord")


def test_audit_session_public_writer(cases, data_root):
    sid = _session(cases)["id"]
    board.audit_session(sid, {"kind": "agents_prepare", "by": "coord", "roles": ["pathology"], "session": "ignored"})
    ev = _jsonl(data_root / "sessions" / "audit.jsonl")[-1]
    assert ev["kind"] == "agents_prepare" and ev["session"] == sid and ev["roles"] == ["pathology"] and ev["ts"]
    assert board.read_audit()[-1] == ev


