"""The meeting PDF (meetings-v2 item 4.1, D10 / T5): the HTML builder (fields, DD/MM/YYYY, no em dash, the AI agents labelled, the version
note, a Case File taken up during the meeting, an empty meeting, the Phase 5 notes hook), the two routes (who may and may not, 404s,
the audit) and one real render through the pdf venv subprocess. Hermetic: the meeting fixtures of test_nik_meetings, synthetic Case
Files, no model."""
import os
import re
import stat
from datetime import date

import pytest

from tumour_board import board, meeting_pdf, org, store
from tumour_board.tests.test_nik_meetings import As, app, tc, join_and_admit, new_meeting, owned, started  # noqa: F401

DECISION = "Upfront surgery \u2014 then adjuvant therapy as per the final histopathology."


def _decide(tc, mid, cid, **extra):
    body = {"outcome": "decision", "decision_text": DECISION, "members_present": ["Anil Kumar"], "intent": "curative", "responsible_doctor": "Dr Priya Nair",
            "modalities": ["surgery", "chemotherapy"], "stage_as_agreed": "cT2 N0 M0", "stage_source": "report",
            "investigations": [{"item": "Echocardiogram", "department": "Cardiology", "due": "05/11/2026"}],
            "concerns": [{"by": "Dr Dev", "text": "Would consider neoadjuvant chemotherapy first."}], **extra}
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/{cid}/decision", json=body)
    assert r.status_code == 200, r.text
    return r.json()["record"]


def _closed_meeting(tc, cid="TB-002"):
    """A meeting with TB-001, TB-002 for discussion and TB-003 for noting; a decision for `cid`; the radiology agent stood in for it."""
    mid = started(tc)
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": cid})
    rec = _decide(tc, mid, cid)
    s = board.get(mid)
    s.setdefault("agents", {}).setdefault(cid, {})["radiology"] = {"status": "ready", "at": store.now_iso()}
    board.save_session(s)
    assert As(tc, "anil").post(f"/meetings/{mid}/end").status_code == 200
    return mid, rec


@pytest.fixture
def fake_render(monkeypatch):
    """The routes without the subprocess: the page is kept, the 'PDF' is a stub."""
    pages = []

    def render(page, timeout=None):
        pages.append(page)
        return b"%PDF-1.7 stub"
    monkeypatch.setattr(meeting_pdf, "render_pdf", render)
    return pages


# ---- the HTML builder -----------------------------------------------------------------------------------------------------------------

def test_meeting_html_has_the_record_as_recorded(tc):
    mid, rec = _closed_meeting(tc)
    s = board.get(mid)
    page = meeting_pdf.meeting_html(mid, org.roles("anil"))
    when = date.fromisoformat(s["date"]).strftime("%d/%m/%Y")
    # the cover: hospital, Tumour Board, date DD/MM/YYYY and time, room, the coordinator, the status
    for want in ("Tumour Board", when, "10:30", "Board room 2", "Anil Kumar", "Closed", org.hospital()["name"]):
        assert want in page, want
    # the Case File: patient line (name, age and sex, UHID), the cancer, the presenter, the question, the decision and its fields
    p = store.get_case("TB-002")["patient"]
    assert p["name"] in page and p["agesex"] in page and f"UHID {p['mrn']}" in page
    assert "Upfront surgery - then adjuvant therapy" in page  # as recorded; the em dash printed as "-"
    for want in ("Decision recorded", "Curative", "Surgery, Chemotherapy", "Echocardiogram", "Cardiology", "05/11/2026",
                 "Would consider neoadjuvant chemotherapy first.", "Dr Dev", "Responsible clinician", "Dr Priya Nair", "cT2 N0 M0",
                 "Question for the board", "Presenter:", "Case 2 of 3", "For noting", "Minutes", "Follow-up of the actions"):
        assert want in page, want
    # the AI agent that stood in, labelled; the quiet footer; no em dash and no ISO date anywhere
    assert "Radiology AI agent" in page and meeting_pdf.AGENT_LABEL == "AI agent, support only, not a member" and meeting_pdf.AGENT_LABEL in page
    assert meeting_pdf.FOOTER in page and "counter(pages)" in page
    assert "\u2014" not in page
    assert not re.search(r"\d{4}-\d{2}-\d{2}", page)
    # no notes before Phase 5: the hook returns nothing and nothing is printed
    assert meeting_pdf.discussion_notes(s, "TB-002") == [] and meeting_pdf.NOTES_HEADING not in page


def test_member_copy_withholds_the_records_it_may_not_read(tc):
    owned("TB-002")
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    join_and_admit(tc, mid, "ravi")
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    _decide(tc, mid, "TB-001", decision_text="Definitive chemoradiation as discussed by the board.")
    _decide(tc, mid, "TB-002")
    priya = meeting_pdf.meeting_html(mid, org.roles("priya"))
    assert "Upfront surgery - then adjuvant" in priya  # her own Case File in full
    assert "Definitive chemoradiation" not in priya and meeting_pdf.RESTRICTED_NOTE in priya  # another department's: the outcome only
    assert store.get_case("TB-001")["patient"]["name"] in priya  # the patient line, as the meeting screen showed it to a member
    ravi = meeting_pdf.meeting_html(mid, org.roles("ravi"))
    assert "Upfront surgery" not in ravi and "Definitive chemoradiation" not in ravi and "Decision recorded" in ravi
    full = meeting_pdf.meeting_html(mid, org.roles("anil"))
    assert "Upfront surgery - then adjuvant" in full and "Definitive chemoradiation" in full and meeting_pdf.RESTRICTED_NOTE not in full
    # the members who joined, how they took part
    assert "Dr Priya Nair" in full and "Dr Ravi" in full and ("In the room" in full or "Remote" in full)


def test_taken_up_during_the_meeting_and_the_version_note(tc):
    mid, rec = _closed_meeting(tc)
    s = board.get(mid)
    for it in s["agenda_lists"]["discussion"] + s["agenda_lists"]["noting"]:
        it["added_at"] = "2000-01-01T08:00:00"
    s["started_at"] = "2000-01-01T09:00:00"
    s["agenda_lists"]["noting"][0]["added_at"] = "2000-01-01T09:20:00"  # TB-003 came on during the meeting
    board.save_session(s)
    st = store.get_state("TB-002")
    r_ = next(x for x in st["board_records"] if x["id"] == rec["id"])
    r_["version"] = 2
    r_["corrected"] = {"by": "priya", "by_name": "Dr Priya Nair", "at": "2026-11-04T09:00:00", "reason": "The sequence was typed wrong", "version": 2}
    store.save_state("TB-002", st)
    page = meeting_pdf.meeting_html(mid, org.roles("anil"))
    assert page.count(meeting_pdf.TAKEN_UP) >= 2  # its section and its agenda row
    sec = page.split("Case 3 of 3", 1)[1]
    assert meeting_pdf.TAKEN_UP in sec[:1500]
    assert meeting_pdf.TAKEN_UP not in page.split("Case 1 of 3", 1)[1].split("Case 2 of 3", 1)[0]
    assert "Corrected by Dr Priya Nair on 04/11/2026: The sequence was typed wrong" in page and "version 2 of the record" in page
    # the rule itself
    s0 = {"started_at": "2026-11-05T10:00:00"}
    assert meeting_pdf.taken_up_during(s0, {"added_at": "2026-11-05T10:20:00"})
    assert not meeting_pdf.taken_up_during(s0, {"added_at": "2026-11-05T10:00:00"}) and not meeting_pdf.taken_up_during(s0, {"added_at": "2026-11-04T09:00:00"})
    assert meeting_pdf.taken_up_during({}, {"unplanned": True}) and not meeting_pdf.taken_up_during({}, {"added_at": "2026-11-05T10:20:00"})


def test_an_empty_meeting(tc):
    mid = new_meeting(tc)
    page = meeting_pdf.meeting_html(mid, org.roles("anil"))
    assert "Planned" in page and "No Case File on the agenda." in page and "None on the agenda" in page
    assert "The meeting has not taken place yet: no minutes." in page and "No AI agent took part." in page
    assert "\u2014" not in page and not re.search(r"\d{4}-\d{2}-\d{2}", page)
    with pytest.raises(KeyError):
        meeting_pdf.meeting_html("S20991231-zzzz")


def test_the_phase5_notes_hook_is_printed_when_filled(tc, monkeypatch):
    mid, _ = _closed_meeting(tc)
    monkeypatch.setattr(meeting_pdf, "discussion_notes", lambda meeting, case_id, r=None: [
        {"text": "The surgical head favoured surgery first.", "said": [{"speaker": "Dr Lata", "words": "I would operate first", "at": "2026-11-05T10:42:00"}]}
    ] if case_id == "TB-002" else [])
    page = meeting_pdf.meeting_html(mid, org.roles("anil"))
    assert page.count(meeting_pdf.NOTES_HEADING) == 1 and "Discussion notes (AI draft, not reviewed)" in page
    assert "I would operate first" in page and "Dr Lata, 10:42" in page
    case_page = meeting_pdf.case_html("TB-002", org.roles("anil"))
    assert meeting_pdf.NOTES_HEADING in case_page


def test_case_html_lists_the_board_records_latest_first(tc):
    owned("TB-002")
    mid, rec = _closed_meeting(tc)
    st = store.get_state("TB-002")
    later = {**rec, "id": "Blater1", "decision_text": "Re-discussed: adjuvant radiotherapy added.", "recorded_at": "2099-01-01T10:00:00", "session": "", "board_date": "2099-01-01"}
    st["board_records"].append(later)
    store.save_state("TB-002", st)
    page = meeting_pdf.case_html("TB-002", org.roles("priya"))
    assert page.index("Re-discussed: adjuvant radiotherapy added.") < page.index("Upfront surgery - then adjuvant")
    assert "Board record 2 of 2" in page and "Board record 1 of 2" in page and "Board room 2" in page
    assert store.get_case("TB-002")["patient"]["name"] in page and "\u2014" not in page and not re.search(r"\d{4}-\d{2}-\d{2}", page)


# ---- the routes ---------------------------------------------------------------------------------------------------------------------------

def test_meeting_pdf_route_who_may_and_may_not(tc, fake_render):
    mid, _ = _closed_meeting(tc)
    r = As(tc, "anil").get(f"/meetings/{mid}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf") and r.content.startswith(b"%PDF")
    assert f'filename="Tumour-Board-meeting-{mid}-' in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    assert "Upfront surgery - then adjuvant" in fake_render[-1]
    ev = [e for e in board.read_audit() if e.get("session") == mid and e.get("kind") == "meeting_pdf_downloaded"]
    assert ev and ev[-1]["by"] == "anil" and ev[-1]["bytes"] > 0 and ev[-1]["restricted"] == []
    # not admitted, a doctor of another department, an outside expert even when admitted: refused
    assert As(tc, "ravi").get(f"/meetings/{mid}/pdf").status_code == 403
    assert As(tc, "mohan").get(f"/meetings/{mid}/pdf").status_code == 403
    assert As(tc, "guest").get(f"/meetings/{mid}/pdf").status_code == 403
    assert As(tc, "anil").get("/meetings/S20991231-zzzz/pdf").status_code == 404


def test_meeting_pdf_route_for_an_admitted_member_and_an_outside_expert(tc, fake_render):
    mid = started(tc)
    join_and_admit(tc, mid, "ravi")
    _decide(tc, mid, "TB-002")
    r = As(tc, "ravi").get(f"/meetings/{mid}/pdf")
    assert r.status_code == 200, r.text
    assert "Upfront surgery" not in fake_render[-1] and meeting_pdf.RESTRICTED_NOTE in fake_render[-1]
    ev = [e for e in board.read_audit() if e.get("session") == mid and e.get("kind") == "meeting_pdf_downloaded"]
    assert ev[-1]["by"] == "ravi" and "TB-002" in ev[-1]["restricted"]
    join_and_admit(tc, mid, "guest")
    r = As(tc, "guest").get(f"/meetings/{mid}/pdf")
    assert r.status_code == 403


def test_meeting_pdf_route_says_when_the_pdf_cannot_be_made(tc, monkeypatch):
    mid = new_meeting(tc)

    def broken(page, timeout=None):
        raise meeting_pdf.PdfError("The PDF tool is not installed on this server.")
    monkeypatch.setattr(meeting_pdf, "render_pdf", broken)
    r = As(tc, "anil").get(f"/meetings/{mid}/pdf")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "pdf_unavailable"


def test_case_board_pdf_route(tc, fake_render):
    owned("TB-002")
    _closed_meeting(tc)
    r = As(tc, "priya").get("/cases/TB-002/board-pdf")
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF") and 'filename="Tumour-Board-record-TB-002.pdf"' in r.headers["content-disposition"]
    assert "Upfront surgery - then adjuvant" in fake_render[-1]
    assert "board_pdf_downloaded" in (store.case_dir("TB-002") / "audit.jsonl").read_text()
    assert As(tc, "anil").get("/cases/TB-002/board-pdf").status_code == 200  # the coordinator reads every Case File in full
    assert As(tc, "mohan").get("/cases/TB-002/board-pdf").status_code == 403  # no scope on the file
    assert As(tc, "guest").get("/cases/TB-002/board-pdf").status_code == 403
    assert As(tc, "anil").get("/cases/TB-999/board-pdf").status_code == 404
    r = As(tc, "anil").get("/cases/TB-001/board-pdf")  # no board record yet
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_board_record"


# ---- the real render, through the subprocess -------------------------------------------------------------------------------------------

@pytest.mark.skipif(not meeting_pdf.available(), reason=f"the pdf venv ({meeting_pdf.PDF_PYTHON}) with WeasyPrint is not on this machine")
def test_real_render_to_pdf_bytes(tc):
    mid, _ = _closed_meeting(tc)
    data, info = meeting_pdf.build_meeting(mid, org.roles("anil"))
    assert data.startswith(b"%PDF") and len(data) > 5000 and info["cases"] == 3
    out = os.environ.get("TB_MEETING_PDF_OUT")  # a look by hand: TB_MEETING_PDF_OUT=/some/dir pytest ...
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "meeting.pdf"), "wb") as f:
            f.write(data)
        with open(os.path.join(out, "case.pdf"), "wb") as f:
            f.write(meeting_pdf.build_case("TB-002", org.roles("anil"))[0])
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    doc = pdfium.PdfDocument(data)
    try:
        n = len(doc)
        assert n >= 6  # cover, attendance and agenda, three Case Files, the minutes
        text = doc[2].get_textpage().get_text_range()
        assert "From the Tumour Board record in Vaidyx" in text and f"Page 3 of {n}" in text
    finally:
        doc.close()


def test_render_errors_are_plain(tmp_path, monkeypatch):
    monkeypatch.setattr(meeting_pdf, "PDF_PYTHON", str(tmp_path / "no-such-python"))
    with pytest.raises(meeting_pdf.PdfError) as e:
        meeting_pdf.render_pdf("<p>x</p>")
    assert e.value.code == "pdf_unavailable"
    slow = tmp_path / "bin" / "python"
    slow.parent.mkdir()
    slow.write_text("#!/bin/sh\nexec sleep 5\n")
    slow.chmod(slow.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(meeting_pdf, "PDF_PYTHON", str(slow))
    with pytest.raises(meeting_pdf.PdfError) as e:
        meeting_pdf.render_pdf("<p>x</p>", timeout=0.5)
    assert e.value.code == "pdf_timeout"
    bad = tmp_path / "bin" / "python"
    bad.write_text("#!/bin/sh\necho broken >&2\nexit 3\n")
    with pytest.raises(meeting_pdf.PdfError) as e:
        meeting_pdf.render_pdf("<p>x</p>")
    assert e.value.code == "pdf_failed"
