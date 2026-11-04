"""The meeting PDF (meetings-v2 item 4.1; owner decision D10 "Replace with a PDF", technical decision T5): a clean A4 record of a Tumour
Board meeting that replaces the PowerPoint deck, and the board record PDF of one Case File. No model call: every line is what the
meeting record and the board records hold, as recorded; Vaidyx adds labels and layout only.

    meeting_html(mid, r)  -> str      cover, attendance and agenda, one section per Case File in agenda order, the minutes
    case_html(cid, r)     -> str      the board records of one Case File, latest first
    render_pdf(html)      -> bytes    WeasyPrint in the pdf venv, a separate process (stdin HTML, stdout PDF, nothing written to disk)
    build_meeting(mid, r), build_case(cid, r) -> bytes; filename(kind, ident, when)

Who reads what (the routes in api/meeting_pdf.py check who may download): the MDT Coordinator gets every Case File in full. An admitted
member gets, for every Case File, what the meeting screen showed it (the patient line, the cancer, the presenter, the question for the
board, the outcome label); the decision record itself (the decision text, intent, modalities, actions, concerns, the version note) only
for the Case Files it may read in full, as the meeting page (meetings.view) and the minutes (board.minutes) already rule. A protected
Case File is never printed.

The look: A4 portrait, ink on white, one teal accent, the hospital's logo when one was uploaded (the demo emblem for the demo hospital),
page numbers and the quiet footer FOOTER. The CSS is meeting_pdf_template/meeting.css; the images are copies kept beside it, so this
module does not depend on the deck (which item 4.2 removes).

Phase 5: discussion_notes(meeting, case_id, r) returns the AI notes of one Case File in one meeting (meeting_notes, items 5.3 and 5.4) for
a reader who may read them (the meeting's members, the Case File's full readers; never an outside expert without consent); each Case File
section and the latest board record of each meeting print them under NOTES_HEADING, every line with the speaker's exact words.
"""
from __future__ import annotations

import base64
import html as _html
import logging
import os
import re
import subprocess
import threading
from datetime import date, datetime
from pathlib import Path

from . import access, board, config, decision_record, meetings, org, store

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "meeting_pdf_template"
CSS_FILE = TEMPLATE_DIR / "meeting.css"
PDF_PYTHON = os.environ.get("TB_PDF_PYTHON") or "/data/vaidyx/venv/pdf/bin/python"
TIMEOUT = float(os.environ.get("TB_PDF_TIMEOUT") or 90)   # seconds for one render; the process is killed after it
MAX_PARALLEL = 2                                          # renders at the same time; a third waits for a slot
_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL)
LOGO_MAX = 1_000_000                                      # the upload route's own limit (api/deck.py)

FOOTER = "From the Tumour Board record in Vaidyx. Decisions are the board's."
AGENT_LABEL = "AI agent, support only, not a member"
NOTES_HEADING = "Discussion notes (AI draft, not reviewed)"
TAKEN_UP = "Taken up during the meeting"
SCOPE_LINE = ("Vaidyx checks, routes, summarises and flags. It never decides and never advises treatment: every decision in this record is "
              "the board's, as recorded.")
CONFIDENTIAL = "Internal record of the hospital. It names patients: keep it as confidential as the Case File."
RESTRICTED_NOTE = ("The decision record of this Case File is for its treating team and the MDT Coordinator; it is not printed in this copy. "
                   "Open the Case File, or ask the MDT Coordinator.")
STATUS_WORDS = {"planned": "Planned", "in_session": "In session", "closed": "Closed", "decided": "Closed", "cancelled": "Cancelled"}
STATUS_TONE = {"planned": "teal", "in_session": "warn", "closed": "ok", "decided": "ok", "cancelled": "bad"}
OUTCOME_TONE = {"decision": "ok", "deferred": "warn", "not_discussed": "warn", "referred": "teal", "noted": "teal"}
LIST_WORDS = {"discussion": "For discussion", "noting": "For noting"}
# the decision record fields printed in their own places; the rest go under "Further details as recorded"
PRIMARY_KEYS = ("intent", "intent_as_stated", "modalities", "sequence")
OUTCOME_KEYS = ("awaited", "awaited_from", "referred_to", "not_discussed_reason")
ELSEWHERE_KEYS = ("outcome", "decision_text", "concerns", "investigations", "members_present", "corrected")


class PdfError(Exception):
    """The PDF could not be made (the pdf venv is missing, the render failed or took too long). The route answers 503."""

    def __init__(self, message: str, code: str = "pdf_unavailable"):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------------------------------- small helpers
def _h(x) -> str:
    """Text for the page: escaped, an em dash printed as '-' (no em dashes in reports, as board._h)."""
    return _html.escape(str(x if x is not None else "").replace("\u2014", "-"), quote=True)


def _clean(x) -> str:
    return " ".join(str(x or "").split())


def _dmy(iso) -> str:
    """'2026-11-05' or '2026-11-05T10:30:00' -> '05/11/2026'; anything else as given."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso or "")


def _dmy_hm(iso) -> str:
    """'2026-11-05T10:30:00' -> '05/11/2026, 10:30'; a date alone -> '05/11/2026'."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}, {m.group(4)}:{m.group(5)}" if m else _dmy(iso)


def _hm(iso) -> str:
    m = re.match(r"^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})", str(iso or ""))
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def _weekday_date(iso) -> str:
    """'2026-11-05' -> 'Thursday, 05/11/2026'."""
    try:
        d = date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return _dmy(iso)
    return f"{d.strftime('%A')}, {d.strftime('%d/%m/%Y')}"


def _meeting_when(s: dict) -> str:
    """'Thursday, 05/11/2026 at 10:30'."""
    return _weekday_date(s.get("date")) + (f" at {s['time']}" if s.get("time") else "")


def _data_uri(path: Path | None, max_bytes: int = LOGO_MAX) -> str:
    """A PNG or JPEG file as a data: URI (checked by its first bytes), or "" when there is none or it is not one."""
    try:
        if not path or not Path(path).is_file():
            return ""
        raw = Path(path).read_bytes()
    except OSError:
        return ""
    if not raw or len(raw) > max_bytes:
        return ""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "image/png"
    elif raw.startswith(b"\xff\xd8"):
        kind = "image/jpeg"
    else:
        return ""
    return f"data:{kind};base64," + base64.b64encode(raw).decode("ascii")


def logo_path() -> Path | None:
    """The hospital's uploaded logo (PNG or JPEG under the data root, as the upload route keeps it), else the demo emblem when the
    hospital is the demo one, else None. The same rule as the deck's, kept here so the deck can go (item 4.2)."""
    h = org.hospital()
    logo = h.get("logo") if isinstance(h.get("logo"), dict) else {}
    f = str(logo.get("file") or "")
    if f and re.match(r"^hospital_logo\.(png|jpe?g)$", f):
        p = Path(config.DATA_ROOT) / f
        if p.exists():
            return p
    if "demo" in _clean(h.get("name")).lower():
        return TEMPLATE_DIR / "demo-hospital.png"
    return None


def _is_synthetic(hospital: dict, cases: list) -> bool:
    if "demo" in _clean(hospital.get("name")).lower():
        return True
    return any("synthetic" in _clean(((c or {}).get("patient") or {}).get("name")).lower() for c in cases if isinstance(c, dict))


def _case(cid) -> dict | None:
    """The Case File, or None (missing, a bad id, or protected: real patient data is never printed)."""
    if not cid or cid in config.PROTECTED_CASES:
        return None
    try:
        c = store.get_case(cid)
    except (ValueError, OSError):
        return None
    if not isinstance(c, dict):
        return None
    try:
        if access.is_protected(c):
            return None
    except Exception:
        return None
    return c


def _cancer_line(c: dict) -> str:
    """'Carcinoma breast, early (setting as recorded)' from the Case File's cancer name or its protocol label, and its setting."""
    cancer = _clean(c.get("cancer_name"))
    if not cancer and c.get("protocol"):
        try:
            from . import protocol
            cancer = _clean(protocol.get(c["protocol"]).get("label"))
        except Exception:
            cancer = ""
        cancer = cancer or _clean(c.get("protocol")).replace("_", " ")
    setting = _clean(c.get("setting")).replace("_", " ")
    return (cancer or "Cancer not recorded") + (f", {setting} (setting as recorded)" if setting else "")


def _presenter(c: dict) -> str:
    p = meetings.chosen_presenter(c)
    if p and p.get("name"):
        return p["name"]
    u = meetings.presenter_of(c)
    return meetings.display_name(u) if u else ""


def _dept_name(d) -> str:
    d = _clean(d)
    if not d:
        return ""
    did = org.department_id(d)
    return org.department_name(did) if did else d


def _role_name(role: str) -> str:
    return org.department_name(board.ROLE_DEPARTMENT.get(role, role))


def _is_coordinator(user: str) -> bool:
    try:
        return bool(org.roles(user).get("coordinator"))
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------------- the Phase 5 hook
def discussion_notes(meeting: dict, case_id: str, r: dict | None = None) -> list[dict]:
    """The AI notes of what was said about one Case File in one meeting (meetings-v2 items 5.3 and 5.4), for the reader `r`; [] when there
    are none or the reader may not read them, and nothing is printed then. Who reads them is the rule of GET /meetings/{mid}/notes (D13:
    every member of that meeting, the MDT Coordinator) and of GET /cases/{id}/meeting-notes (whoever reads the whole Case File); never an
    outside expert without the patient's consent to an outside discussion; never a protected Case File. `r` None: internal, everything.
    Each line:

        {"text": "...", "said": [{"speaker": "Dr X", "words": "exact words", "at": "2026-11-05T10:42:00"}], "edited": bool,
         "edited_by": "Dr Z" | None, "reviewed_by": "Dr Y" | None}

    The section prints NOTES_HEADING ("Discussion notes (AI draft, not reviewed)", or reviewed by whom), each line with its "said" words
    and speaker beneath."""
    if not isinstance(meeting, dict) or not case_id or case_id in config.PROTECTED_CASES:
        return []
    e = (meeting.get("notes") or {}).get(case_id) if isinstance(meeting.get("notes"), dict) else None
    if not isinstance(e, dict) or not e.get("lines"):
        return []
    if r is not None:
        if not isinstance(r, dict) or r.get("disabled"):
            return []
        c = store.get_case(case_id)
        if not c or access.is_protected(c):
            return []
        try:
            full = access.scope(r, c) == access.FULL
        except Exception:
            full = False
        if not (meetings.is_member(r, meeting) or full):
            return []
        if r.get("outside_expert") and not meetings.manage(r) and meetings.outside_view(r, c):
            return []
    rv = e.get("review") if isinstance(e.get("review"), dict) else {}
    reviewed_by = _clean(rv.get("by_name") or meetings.display_name(rv.get("by"))) if rv.get("status") == "reviewed" and (rv.get("by_name") or rv.get("by")) else None
    out = []
    for ln in e.get("lines") or []:
        if not isinstance(ln, dict) or not _clean(ln.get("text")):
            continue
        said = ln.get("said") if isinstance(ln.get("said"), dict) else {}
        ed = ln.get("edited") if isinstance(ln.get("edited"), dict) else None
        who = _clean(said.get("speaker_name")) or ("Board room" if said.get("speaker") == "room" else meetings.display_name(said.get("speaker")) if said.get("speaker") else "")
        out.append({"text": _clean(ln.get("text")),
                    "said": [{"speaker": who, "words": _clean(said.get("quote")), "at": said.get("at") or ""}] if _clean(said.get("quote")) else [],
                    "edited": bool(ed), "edited_by": (_clean(ed.get("by_name")) or meetings.display_name(ed.get("by")) if ed and (ed.get("by_name") or ed.get("by")) else None),
                    "reviewed_by": reviewed_by})
    return out


def notes_heading(notes: list) -> str:
    """NOTES_HEADING while the notes are an AI draft; "Discussion notes (AI notes, reviewed by Dr Y)" once the coordinator marked them."""
    by = {n.get("reviewed_by") for n in notes or [] if isinstance(n, dict)}
    one = next(iter(by)) if len(by) == 1 else None
    return f"Discussion notes (AI notes, reviewed by {one})" if one else NOTES_HEADING


def _notes_html(notes: list) -> str:
    lines = [n for n in notes or [] if isinstance(n, dict) and _clean(n.get("text"))]
    if not lines:
        return ""
    heading = notes_heading(lines)
    out = [f"<div class='notes'><div class='kicker'>{_h(heading)}</div><ul class='plain'>"]
    for n in lines:
        edited = (" <span class='muted small'>(edited" + (f" by {_h(n['edited_by'])}" if n.get("edited_by") else "") + ")</span>") if n.get("edited") else ""
        out.append(f"<li>{_h(n.get('text'))}{edited}"
                   + (f" <span class='muted small'>(reviewed by {_h(n['reviewed_by'])})</span>" if n.get("reviewed_by") and heading == NOTES_HEADING else ""))
        for x in n.get("said") or []:
            if isinstance(x, dict) and _clean(x.get("words")):
                who = ", ".join(v for v in (_clean(x.get("speaker")), _hm(x.get("at"))) if v)
                out.append(f"<div class='said'>said{(' by ' + _h(who)) if who else ''}: “{_h(x.get('words'))}”</div>")
        out.append("</li>")
    out.append("</ul></div>")
    return "".join(out)


# ---------------------------------------------------------------------------------------------------- what the meeting holds
def taken_up_during(s: dict, entry: dict) -> bool:
    """A Case File taken up during the meeting (D7, item 3.4): its list entry says so (unplanned, taken_up or taken_up_at), or it was
    added to the meeting's lists after the second the meeting started (the agenda set in that same second counts as planned)."""
    if not isinstance(entry, dict):
        return False
    if entry.get("unplanned") or entry.get("taken_up") or entry.get("taken_up_at"):
        return True
    started, added = str(s.get("started_at") or ""), str(entry.get("added_at") or "")
    return bool(started and added and added[:19] > started[:19])


def _agents(s: dict) -> dict:
    """{role: {"cases": [case ids], "answers": n, "called": bool}}: the AI agents that took part, from the meeting record: a brief
    prepared for a Case File (standing in for a head not present), an answer to a member's question, or the coordinator calling it."""
    out: dict[str, dict] = {}

    def add(role, cid, **kw):
        if not role or role not in board.ROLE_DEPARTMENT:
            return
        a = out.setdefault(role, {"cases": [], "answers": 0, "called": False})
        if cid and cid not in a["cases"]:
            a["cases"].append(cid)
        a["answers"] += kw.get("answers", 0)
        a["called"] = a["called"] or bool(kw.get("called"))
    for cid, by_role in (s.get("agents") or {}).items():
        for role, x in (by_role.items() if isinstance(by_role, dict) else ()):
            if isinstance(x, dict) and x.get("status") in ("ready", "no_documents"):
                add(role, cid)
    for q in s.get("questions") or []:
        a = q.get("answer") if isinstance(q, dict) else None
        if isinstance(q, dict) and q.get("role") and isinstance(a, dict) and a.get("status") not in ("error", "answering"):
            add(q["role"], q.get("case_id"), answers=1)
    for cid, by_role in (s.get("agents_active") or {}).items():
        for role, o in (by_role.items() if isinstance(by_role, dict) else ()):
            if isinstance(o, dict) and o.get("on"):
                add(role, cid, called=True)
    return {r: out[r] for r in board.ROLE_DEPARTMENT if r in out}


def _record_for(st: dict, mid: str | None, oc: dict | None) -> dict | None:
    """The board record of this Case File for meeting `mid`: the one the outcome names, else the latest record of that meeting."""
    recs = [x for x in (st or {}).get("board_records") or [] if isinstance(x, dict)]
    rid = (oc or {}).get("record")
    if rid:
        for x in recs:
            if x.get("id") == rid:
                return x
    if mid:
        for x in reversed(recs):
            if x.get("session") == mid:
                return x
    return None


def _record_view(rec: dict) -> dict:
    """The decision record as the PDF prints it: outcome, the decision text, the key fields, actions, concerns, further fields, the
    version note. Every value as recorded (labels and dates DD/MM/YYYY by decision_record)."""
    lines = {x["key"]: x for x in decision_record.display_lines(rec)}
    if "awaited_from" in lines:  # stored as a department id or name: printed as the department's name
        lines["awaited_from"] = {**lines["awaited_from"], "text": _dept_name(lines["awaited_from"]["text"])}
    outcome = rec.get("outcome_type") or "decision"
    concerns = [{"by": _clean(x.get("by")), "text": _clean(x.get("text"))} for x in rec.get("concerns") or [] if isinstance(x, dict) and _clean(x.get("text"))]
    if not concerns and _clean(rec.get("divergent_opinions")):
        concerns = [{"by": "", "text": _clean(rec.get("divergent_opinions"))}]
    actions = [{"task": _clean(a.get("task") or a.get("what") or a.get("label")), "department": _dept_name(a.get("department")), "due": _dmy(a.get("due"))}
               for a in rec.get("actions") or [] if isinstance(a, dict) and _clean(a.get("task") or a.get("what") or a.get("label"))]
    version = int(rec.get("version") or 1)
    corrected = decision_record.corrected_line(rec)
    note = ""
    if corrected or version > 1:
        note = (corrected + "." if corrected else "The record was changed after the meeting.") + f" This is version {version} of the record; every earlier version is kept in the Case File."
    skip = set(PRIMARY_KEYS) | set(OUTCOME_KEYS) | set(ELSEWHERE_KEYS)
    return {"id": rec.get("id") or "", "outcome": outcome, "outcome_label": decision_record.OUTCOMES.get(outcome, _clean(outcome) or "Outcome"),
            "decision_text": str(rec.get("decision_text") or "").strip(),
            "recorded_by": _clean(rec.get("recorded_by") or rec.get("entered_by")), "recorded_at": rec.get("recorded_at") or "",
            "outcome_lines": [lines[k] for k in OUTCOME_KEYS if k in lines], "primary": [lines[k] for k in PRIMARY_KEYS if k in lines],
            "actions": actions, "concerns": concerns, "further": [x for k, x in lines.items() if k not in skip], "version": version, "version_note": note,
            "session": rec.get("session") or ""}


def _cards(s: dict, cid: str) -> dict:
    agreed, concern = [], []
    for u, c in ((s.get("cards") or {}).get(cid) or {}).items():
        if isinstance(c, dict):
            (agreed if c.get("agree") else concern).append(_clean(c.get("name")) or meetings.display_name(u))
    return {"agreed": agreed, "concern": concern}


def _case_entry(s: dict, it: dict, lst: str, n: int, total: int, r: dict | None, full: set | None, agents: dict) -> dict:
    cid = str(it.get("case_id") or "")
    c = _case(cid)
    base = {"n": n, "total": total, "case_id": cid, "list": lst, "list_label": LIST_WORDS.get(lst, ""), "taken_up": taken_up_during(s, it)}
    if not c:
        return {**base, "missing": True}
    st = store.get_state(cid) or {}
    oc = (s.get("outcomes") or {}).get(cid) if isinstance(s.get("outcomes"), dict) else None
    oc = oc if isinstance(oc, dict) else {}
    restricted = full is not None and cid not in full
    rec = None if restricted else _record_for(st, s.get("id"), oc)
    ended = (s.get("ended") or {}).get(cid) or {}
    secs = ended.get("elapsed_seconds") if isinstance(ended, dict) else None
    if secs is None:
        secs = board.timing(s).get(cid)
    moved = ""
    if oc.get("moved_to"):
        nxt = meetings.get(oc["moved_to"]) or {}
        moved = f"Moved to the meeting on {_dmy(nxt.get('date'))}" if nxt.get("date") else "Moved to a later meeting"
    elif oc.get("flagged"):
        moved = "No later meeting was planned: it waits for the next meeting made"
    roles = [role for role, a in agents.items() if cid in a["cases"]]
    return {**base, "case": c, "patient_line": meetings.patient_line(c, r), "cancer": _cancer_line(c),
            "owner": org.department_name(access.owner(c)) if access.owner(c) else "", "presenter": _presenter(c),
            "question": meetings._board_question(c, st), "restricted": restricted, "reason": _clean(it.get("reason")),
            "outcome": oc.get("outcome") or (rec or {}).get("outcome_type") or "", "outcome_label": _clean(oc.get("label")) or (decision_record.OUTCOMES.get((rec or {}).get("outcome_type") or "", "") if rec else ""),
            "moved": moved, "record": _record_view(rec) if rec else None, "cards": _cards(s, cid) if not restricted else {"agreed": [], "concern": []},
            "minutes_on_floor": round(float(secs) / 60) if secs else 0, "agents": [_role_name(x) for x in roles],
            "notes": discussion_notes(s, cid, r)}


def _coordinators(s: dict) -> list[str]:
    people = s.get("people") or {}
    names = [p.get("name") or meetings.display_name(u) for u, p in people.items() if p.get("status") in meetings.ADMITTED and _is_coordinator(u)]
    if names:
        return names
    for u in (s.get("started_by"), s.get("created_by")):
        if u and _is_coordinator(u):
            return [meetings.display_name(u)]
    return []


def _attendance(s: dict, agents: dict) -> dict:
    people = s.get("people") or {}
    rows, named = [], set()
    for u, p in people.items():
        if p.get("status") not in meetings.ADMITTED:
            continue
        did = p.get("department") or ""
        placement = ((org.roles(u).get("departments") or {}).get(did) or "") if did else ""
        rows.append({"name": p.get("name") or meetings.display_name(u), "department": "MDT Coordinator" if _is_coordinator(u) and not did else (org.department_name(did) if did else ""),
                     "how": "In the room" if p.get("status") == "present" else "Remote", "head": placement == "head", "outside": bool(p.get("outside_expert"))})
        named.add(u)
    for m in s.get("members") or []:  # a member recorded by hand in the old room, never joined through Vaidyx
        if isinstance(m, dict) and m.get("user") not in named and _clean(m.get("name")) and m.get("department") != org.COORDINATOR_ID:
            rows.append({"name": _clean(m.get("name")), "department": org.department_name(m.get("department")) if m.get("department") else "", "how": "Recorded present",
                         "head": False, "outside": False})
    rows.sort(key=lambda x: ({"In the room": 0, "Remote": 1}.get(x["how"], 2), x["name"]))
    heads = []
    if s.get("status") not in ("planned", "cancelled"):
        try:
            q = meetings.quorum_view(s)
        except Exception:
            q = {"heads": []}
        for h in q.get("heads") or []:
            if not h.get("present"):
                a = agents.get(h.get("role") or "")
                heads.append({"name": h.get("name") or "", "agent": bool(a)})
    return {"rows": rows, "absent_heads": heads}


def meeting_data(mid: str, r: dict | None = None) -> dict:
    """Everything the meeting PDF prints, for the reader `r` (None: everything, for internal use)."""
    s = meetings.get(mid)
    if not s:
        raise KeyError(mid)
    hospital = org.hospital()
    full = None if r is None else meetings.full_cases(r, s)
    lists = s.get("agenda_lists") or {}
    entries = [(it, k) for k in ("discussion", "noting") for it in lists.get(k) or [] if isinstance(it, dict) and it.get("case_id")]
    seen = {it["case_id"] for it, _ in entries}
    for cid in (s.get("outcomes") or {}):  # an outcome recorded for a Case File no longer on the lists still belongs to this record
        if cid not in seen:
            entries.append(({"case_id": cid}, "")); seen.add(cid)
    agents = _agents(s)
    cases = [_case_entry(s, it, lst, i + 1, len(entries), r, full, agents) for i, (it, lst) in enumerate(entries)]
    counts = {k: sum(1 for x in cases if x["list"] == k) for k in ("discussion", "noting")}
    allowed = None if full is None else set(full)
    try:
        fu = board.followup(s, allowed)
    except Exception as e:
        log.warning("meeting pdf %s: follow-up not read (%s)", mid, e)
        fu = {"actions": [], "open": 0, "overdue": 0, "closed": 0}
    by_case = {x["case_id"]: x for x in cases}
    for a in fu.get("actions") or []:
        a["n"] = (by_case.get(a.get("case_id")) or {}).get("n")
    return {"meeting": s, "hospital": hospital, "when": _meeting_when(s), "coordinators": _coordinators(s), "status": s.get("status") or "planned",
            "cases": cases, "counts": counts, "attendance": _attendance(s, agents), "agents": agents, "followup": fu,
            "restricted": sorted(x["case_id"] for x in cases if x.get("restricted")), "synthetic": _is_synthetic(hospital, [x.get("case") for x in cases]),
            "logo": logo_path(), "generated": store.now_iso(), "reader_full": full is None}


# ---------------------------------------------------------------------------------------------------- HTML
def _css() -> str:
    try:
        css = CSS_FILE.read_text(encoding="utf-8")
    except OSError:
        css = ""
    return css.replace("__FOOTER__", FOOTER.replace("\\", "\\\\").replace('"', '\\"'))


def _doc(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en-IN'><head><meta charset='utf-8'><title>{_h(title)}</title><style>{_css()}</style></head>"
            f"<body>{body}</body></html>")


def _pill(text: str, tone: str = "") -> str:
    return f"<span class='pill {tone}'>{_h(text)}</span>"


def _brand() -> str:
    icon, word = _data_uri(TEMPLATE_DIR / "vaidyx-icon.png"), _data_uri(TEMPLATE_DIR / "vaidyx-wordmark.png")
    imgs = (f"<img src='{icon}' alt=''>" if icon else "") + (f"<img src='{word}' alt='Vaidyx'>" if word else "")
    return f"<div class='brand'>{imgs}<span>Tumour Board</span></div>"


def _kv(rows: list[tuple[str, str]]) -> str:
    rows = [(k, v) for k, v in rows if _clean(v)]
    if not rows:
        return ""
    return "<table class='kv'>" + "".join(f"<tr><th>{_h(k)}</th><td>{_h(v)}</td></tr>" for k, v in rows) + "</table>"


def _record_html(rv: dict, title: str = "", notes: list | None = None) -> str:
    """One board record: the outcome, the decision in the board's words, intent and modalities, actions, concerns, further fields, the
    version note, and the Phase 5 notes when there are any."""
    out = []
    if title:
        out.append(f"<div class='kicker'>{_h(title)}</div>")
    who = ", ".join(v for v in (f"recorded by {rv['recorded_by']}" if rv["recorded_by"] else "", f"on {_dmy_hm(rv['recorded_at'])}" if rv["recorded_at"] else "") if v)
    out.append(f"<div class='outcome-row'>{_pill(rv['outcome_label'], OUTCOME_TONE.get(rv['outcome'], ''))}"
               + (f" <span class='meta'>{_h(who[:1].upper() + who[1:])}</span>" if who else "") + "</div>")
    if rv["outcome_lines"]:
        out.append(_kv([(x["label"], x["text"]) for x in rv["outcome_lines"]]))
    out.append("<div class='lead'>Decision, in the board's words</div>")
    out.append(f"<div class='decision'>{_h(rv['decision_text'])}</div>" if rv["decision_text"] else "<p class='none'>No decision text recorded.</p>")
    if rv["primary"]:
        out.append(_kv([(x["label"], x["text"]) for x in rv["primary"]]))
    out.append("<h3>Actions</h3>")
    if rv["actions"]:
        out.append("<table class='grid'><tr><th>Action</th><th style='width:45mm'>Responsible Department</th><th style='width:24mm'>Due</th></tr>"
                   + "".join(f"<tr><td class='strong'>{_h(a['task'])}</td><td>{_h(a['department'] or 'Not named')}</td><td>{_h(a['due'] or 'Not set')}</td></tr>" for a in rv["actions"])
                   + "</table>")
    else:
        out.append("<p class='none'>No action recorded.</p>")
    out.append("<h3>Concerns and divergent views</h3>")
    if rv["concerns"]:
        out.append("<ul class='plain'>" + "".join(f"<li>{('<b>' + _h(c['by']) + ':</b> ') if c['by'] else ''}{_h(c['text'])}</li>" for c in rv["concerns"]) + "</ul>")
    else:
        out.append("<p class='none'>None recorded.</p>")
    if rv["further"]:
        out.append("<h3>Further details as recorded</h3>" + _kv([(x["label"], x["text"]) for x in rv["further"]]))
    if rv["version_note"]:
        out.append(f"<div class='version'>{_h(rv['version_note'])}</div>")
    out.append(_notes_html(notes or []))
    return "".join(out)


def _cover_html(d: dict) -> str:
    s, hosp = d["meeting"], d["hospital"]
    logo = _data_uri(d["logo"])
    status = d["status"]
    st_line = _pill(STATUS_WORDS.get(status, status.replace("_", " ").capitalize()), STATUS_TONE.get(status, ""))
    extra = []
    if s.get("started_at"):
        extra.append(f"started {_dmy_hm(s['started_at'])}")
    if s.get("closed_at"):
        extra.append(f"closed {_dmy_hm(s['closed_at'])}")
    canc = s.get("cancelled") if isinstance(s.get("cancelled"), dict) else None
    if status == "cancelled" and canc:
        extra.append(f"cancelled {_dmy(canc.get('at'))}" + (f": {_clean(canc.get('reason'))}" if _clean(canc.get("reason")) else ""))
    n_disc, n_note = d["counts"]["discussion"], d["counts"]["noting"]
    counts = f"{n_disc} for discussion, {n_note} for noting" if (n_disc or n_note) else "None on the agenda"
    facts = [("Date", _weekday_date(s.get("date"))), ("Time", s.get("time") or "Not set"), ("Room", _clean(s.get("room")) or "Not set"),
             ("MDT Coordinator", ", ".join(d["coordinators"]) or "Not recorded")]
    rows = "".join(f"<tr><th>{_h(k)}</th><td>{_h(v)}</td></tr>" for k, v in facts)
    rows += f"<tr><th>Status</th><td>{st_line}{(' <span class=muted>' + _h('; '.join(extra)) + '</span>') if extra else ''}</td></tr>"
    rows += f"<tr><th>Case Files</th><td>{_h(counts)}</td></tr>"
    if s.get("series_id"):
        rows += "<tr><th>Series</th><td>A meeting of the weekly Tumour Board</td></tr>"
    when = _meeting_when(s)
    logo_img = f"<img class='hosp-logo' src='{logo}' alt=''>" if logo else ""
    return ("<section class='cover'>"
            f"<div class='cover-top'>{logo_img}<div class='hosp-name'>{_h(_clean(hosp.get('name')) or 'Hospital')}</div></div>"
            "<div class='cover-main'><div class='rule'></div><div class='kicker'>Meeting record</div><h1>Tumour Board</h1>"
            f"<div class='when'>{_h(when)}</div>" + (f"<div class='subtitle'>{_h(_clean(s.get('title')))}</div>" if _clean(s.get("title")) else "")
            + f"<table class='facts'>{rows}</table></div>"
            "<div class='cover-bottom'>"
            + ("<p class='synthetic'>SYNTHETIC DATA: demo hospital, fake patients.</p>" if d["synthetic"] else "")
            + f"<p>{_h(CONFIDENTIAL)}</p><p>{_h(SCOPE_LINE)}</p>"
            + f"<p>Made by Vaidyx on {_h(_dmy_hm(d['generated']))} from the meeting record {_h(s.get('id'))}.</p>"
            + (f"<p>{_h('This copy prints the decision records of the Case Files you may open in full; the others show their outcome only.')}</p>" if d["restricted"] else "")
            + _brand() + "</div></section>")


def _attendance_html(d: dict) -> str:
    a = d["attendance"]
    out = ["<section class='section'><div class='runhead'>" + _h(f"Tumour Board, {_dmy(d['meeting'].get('date'))}, {_clean(d['hospital'].get('name')) or 'Hospital'}") + "</div>",
           "<div class='casehead'>Attendance and agenda</div><div class='kicker'>Who took part</div><h2>Attendance</h2>"]
    if d["status"] == "planned":
        out.append("<p class='muted'>The meeting has not started yet: this copy is the agenda.</p>")
    if a["rows"]:
        out.append("<table class='grid'><tr><th>Name</th><th>Department</th><th style='width:32mm'>Took part</th></tr>")
        for x in a["rows"]:
            tag = " <span class='muted small'>(head)</span>" if x["head"] else (" <span class='muted small'>(outside expert)</span>" if x["outside"] else "")
            out.append(f"<tr><td class='strong'>{_h(x['name'])}{tag}</td><td>{_h(x['department'])}</td><td>{_h(x['how'])}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='none'>No member recorded as present.</p>")
    if a["absent_heads"]:
        out.append("<h3>Board heads not present</h3><ul class='plain'>")
        for h in a["absent_heads"]:
            out.append(f"<li>{_h(h['name'])}" + (" <span class='muted'>(its AI agent stood in: see below)</span>" if h["agent"] else "") + "</li>")
        out.append("</ul>")
    out.append("<h3>AI agents</h3>")
    if d["agents"]:
        nums = {x["case_id"]: x["n"] for x in d["cases"]}
        out.append("<ul class='plain'>")
        for role, ag in d["agents"].items():
            which = [str(nums[c]) for c in ag["cases"] if c in nums]
            bits = []
            if which:
                bits.append(("for Case File " if len(which) == 1 else "for Case Files ") + ", ".join(which))
            if ag["answers"]:
                bits.append(f"answered {ag['answers']} question{'s' if ag['answers'] != 1 else ''}")
            if ag["called"]:
                bits.append("called by the MDT Coordinator")
            out.append(f"<li class='agent'><b>{_h(_role_name(role))} AI agent</b><span class='agent-tag'>{_h(AGENT_LABEL)}</span>"
                       + (f" <span class='muted'>{_h('; '.join(bits))}</span>" if bits else "") + "</li>")
        out.append("</ul><p class='muted small'>The AI agents answer from the records and guidelines only. They never decide, never count for the quorum and are never members of the board.</p>")
    else:
        out.append("<p class='none'>No AI agent took part.</p>")
    out.append("<h3>Agenda</h3>")
    if d["cases"]:
        out.append("<table class='grid'><tr><th style='width:7mm'>#</th><th>Patient</th><th>Cancer</th><th style='width:26mm'>List</th><th style='width:34mm'>Outcome</th></tr>")
        for x in d["cases"]:
            if x.get("missing"):
                out.append(f"<tr><td>{x['n']}</td><td colspan='4' class='none'>This Case File is not available.</td></tr>"); continue
            lst = x["list_label"] + (f"<br><span class='small muted'>{_h(TAKEN_UP)}</span>" if x["taken_up"] else "")
            out.append(f"<tr><td>{x['n']}</td><td class='strong'>{_h(x['patient_line'])}</td><td>{_h(x['cancer'])}</td><td>{lst}</td>"
                       f"<td>{_h(x['outcome_label'] or ('Not recorded' if d['status'] != 'planned' else ''))}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='none'>No Case File on the agenda.</p>")
    out.append("</section>")
    return "".join(out)


def _case_section_html(x: dict, d: dict) -> str:
    head = f"Case {x['n']} of {x['total']}"
    out = ["<section class='section'>"]
    if x.get("missing"):
        out.append(f"<div class='casehead'>{_h(head)}</div><div class='kicker'>{_h(head)}</div><h2>Case File not available</h2>"
                   "<p class='none'>This Case File is not in Vaidyx any more, or it is a protected file that is never printed.</p></section>")
        return "".join(out)
    out.append(f"<div class='casehead'>{_h(head + ': ' + x['patient_line'])}</div>")
    kick = " · ".join(v for v in (head, x["list_label"]) if v)
    out.append(f"<div class='kicker'>{_h(kick)}</div>")
    out.append(f"<h2>{_h(x['patient_line'])}</h2>")
    if x["taken_up"]:
        out.append(f"<div style='margin-bottom:1.5mm'>{_pill(TAKEN_UP, 'warn')}</div>")
    out.append(f"<div class='meta'><b>Cancer:</b> {_h(x['cancer'])}</div>")
    meta = [f"<b>Case File:</b> {_h(x['case_id'])}"]
    if x["owner"]:
        meta.append(f"<b>Responsible Department:</b> {_h(x['owner'])}")
    meta.append(f"<b>Presenter:</b> {_h(x['presenter'] or 'Not named')}")
    out.append("<div class='meta'>" + " &nbsp;·&nbsp; ".join(meta) + "</div>")
    if x["minutes_on_floor"]:
        out.append(f"<div class='meta'><b>Time on the floor:</b> {x['minutes_on_floor']} min</div>")
    if x["reason"]:
        out.append(f"<div class='meta'><b>Note on the agenda:</b> {_h(x['reason'])}</div>")
    out.append(f"<div class='question'><div class='kicker'>Question for the board</div><div class='text'>{_h(x['question'] or 'Not recorded.')}</div></div>")
    if x["agents"]:
        out.append("<div class='meta' style='margin-top:2mm'><b>AI agents for this Case File:</b> " + _h(", ".join(x["agents"]))
                   + f"<span class='agent-tag'>{_h(AGENT_LABEL)}</span></div>")
    if x["restricted"]:
        if x["outcome_label"]:
            out.append(f"<div class='outcome-row'>{_pill(x['outcome_label'], OUTCOME_TONE.get(x['outcome'], ''))}"
                       + (f" <span class='meta'>{_h(x['moved'])}</span>" if x["moved"] else "") + "</div>")
        out.append(f"<div class='restricted'>{_h(RESTRICTED_NOTE)}</div>")
    elif x["record"]:
        out.append(_record_html(x["record"], notes=None))
        if x["moved"]:
            out.append(f"<p class='meta' style='margin-top:2mm'>{_h(x['moved'])}.</p>")
        cards = x["cards"]
        if cards["agreed"] or cards["concern"]:
            bits = ([f"agreed: {', '.join(cards['agreed'])}"] if cards["agreed"] else []) + ([f"concern: {', '.join(cards['concern'])}"] if cards["concern"] else [])
            out.append(f"<p class='meta' style='margin-top:2mm'><b>Cards from the heads:</b> {_h('; '.join(bits))}</p>")
    elif x["outcome_label"]:
        out.append(f"<div class='outcome-row'>{_pill(x['outcome_label'], OUTCOME_TONE.get(x['outcome'], ''))}</div>"
                   "<p class='none'>The board record of this outcome is not in the Case File.</p>")
    else:
        out.append("<p class='none' style='margin-top:5mm'>" + ("The meeting has not taken place yet." if d["status"] == "planned"
                   else "No outcome recorded for this Case File in this meeting.") + "</p>")
    # Phase 5 (items 5.3, 5.4): the AI notes of what was said about this Case File, labelled NOTES_HEADING
    out.append(_notes_html(x.get("notes") or []))
    out.append("</section>")
    return "".join(out)


def _minutes_html(d: dict) -> str:
    s = d["meeting"]
    out = ["<section class='section'><div class='casehead'>Minutes</div><div class='kicker'>After the meeting</div><h2>Minutes</h2>",
           "<p class='muted'>As dictated by the board and entered by the MDT Coordinator. The AI agents' points are not minutes; an AI agent is never a member of the board.</p>"]
    held = []
    if s.get("started_at"):
        held.append(f"Started {_dmy_hm(s['started_at'])}" + (f" by {meetings.display_name(s['started_by'])}" if s.get("started_by") else ""))
    if s.get("closed_at"):
        held.append(f"closed {_dmy_hm(s['closed_at'])}" + (f" by {meetings.display_name(s['closed_by'])}" if s.get("closed_by") else ""))
    if held:
        out.append(f"<p>{_h('; '.join(held))}.</p>")
    if d["status"] == "planned":
        out.append("<p class='none'>The meeting has not taken place yet: no minutes.</p></section>")
        return "".join(out)
    if d["status"] == "cancelled":
        out.append("<p class='none'>The meeting was cancelled: no minutes.</p></section>")
        return "".join(out)
    out.append("<h3>Outcomes</h3>")
    if d["cases"]:
        out.append("<table class='grid fixed'><tr><th style='width:7mm'>#</th><th style='width:52mm'>Patient</th><th style='width:30mm'>Outcome</th><th>Decision as recorded</th></tr>")
        for x in d["cases"]:
            if x.get("missing"):
                out.append(f"<tr><td>{x['n']}</td><td colspan='3' class='none'>Not available.</td></tr>"); continue
            if x["restricted"]:
                text = "Not printed in this copy."
            elif x["record"]:
                text = x["record"]["decision_text"]
                text = text if len(text) <= 400 else text[:400].rsplit(" ", 1)[0] + " ... (in full in Case " + str(x["n"]) + ")"
            else:
                text = ""
            out.append(f"<tr><td>{x['n']}</td><td class='strong'>{_h(x['patient_line'])}" + (f"<br><span class='small muted'>{_h(TAKEN_UP)}</span>" if x["taken_up"] else "")
                       + f"</td><td>{_h(x['outcome_label'] or 'Not recorded')}</td><td style='white-space:pre-wrap'>{_h(text)}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='none'>No Case File was on the agenda.</p>")
    fu = d["followup"]
    out.append(f"<h3>Follow-up of the actions</h3><p class='meta'>{fu.get('open', 0)} open, {fu.get('overdue', 0)} overdue, {fu.get('closed', 0)} closed, on {_h(_dmy(d['generated']))}.</p>")
    if fu.get("actions"):
        out.append("<table class='grid'><tr><th style='width:9mm'>Case</th><th>Action</th><th style='width:40mm'>Responsible Department</th><th style='width:20mm'>Due</th><th style='width:26mm'>Status</th></tr>")
        for a in fu["actions"]:
            status = ("Closed " + _dmy(a.get("completed"))) if a.get("status") == "completed" else ("Overdue" if a.get("overdue") else (_clean(a.get("status")).replace("_", " ").capitalize() or "Open"))
            out.append(f"<tr><td>{_h(a.get('n') or '')}</td><td class='strong'>{_h(a.get('task'))}</td><td>{_h(_dept_name(a.get('department')))}</td>"
                       f"<td>{_h(_dmy(a.get('due')) or 'Not set')}</td><td>{_h(status)}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='none'>No follow-up action from this meeting.</p>")
    out.append("</section>")
    return "".join(out)


def _meeting_page(d: dict) -> str:
    body = [_cover_html(d), _attendance_html(d)] + [_case_section_html(x, d) for x in d["cases"]] + [_minutes_html(d)]
    return _doc(f"Tumour Board, {_dmy(d['meeting'].get('date'))}", "".join(body))


def meeting_html(mid: str, r: dict | None = None) -> str:
    """The meeting PDF as one HTML page (inline CSS, images as data: URIs, no scripts, no outside link)."""
    return _meeting_page(meeting_data(mid, r))


# ---------------------------------------------------------------------------------------------------- one Case File
def case_data(cid: str, r: dict | None = None) -> dict:
    """One Case File's board records, latest first, each with the meeting it came from. KeyError when the Case File is missing or
    protected."""
    c = _case(cid)
    if not c:
        raise KeyError(cid)
    st = store.get_state(cid) or {}
    recs = [x for x in st.get("board_records") or [] if isinstance(x, dict)]
    recs = sorted(enumerate(recs), key=lambda p: (str(p[1].get("recorded_at") or ""), p[0]), reverse=True)
    out, noted = [], set()
    for _, rec in recs:
        rv = _record_view(rec)
        s = meetings.get(rv["session"]) if rv["session"] else None
        where = ""
        if s:
            where = "Tumour Board on " + _meeting_when(s) + (f", {_clean(s.get('room'))}" if _clean(s.get("room")) else "")
        elif rec.get("board_date"):
            where = f"Tumour Board on {_weekday_date(rec.get('board_date'))}"
        entry = None
        if s:
            entry = next((it for k in ("discussion", "noting") for it in (s.get("agenda_lists") or {}).get(k) or [] if isinstance(it, dict) and it.get("case_id") == cid), None)
        notes = discussion_notes(s, cid, r) if s and s.get("id") not in noted else []  # a meeting's notes once, with its latest record
        if s:
            noted.add(s.get("id"))
        out.append({"view": rv, "where": where, "taken_up": bool(s and entry and taken_up_during(s, entry)), "notes": notes})
    hospital = org.hospital()
    return {"case": c, "case_id": cid, "hospital": hospital, "patient_line": meetings.patient_line(c, r), "cancer": _cancer_line(c),
            "owner": org.department_name(access.owner(c)) if access.owner(c) else "", "presenter": _presenter(c),
            "question": meetings._board_question(c, st), "records": out, "synthetic": _is_synthetic(hospital, [c]), "logo": logo_path(),
            "generated": store.now_iso()}


def case_html(cid: str, r: dict | None = None) -> str:
    """The board record PDF of one Case File as one HTML page."""
    return _case_page(case_data(cid, r))


def _case_page(d: dict) -> str:
    logo = _data_uri(d["logo"])
    out = ["<div class='runhead'>" + _h(f"Tumour Board record, {d['case_id']}, {_clean(d['hospital'].get('name')) or 'Hospital'}") + "</div>",
           f"<div class='casehead'>{_h(d['patient_line'])}</div>",
           "<div class='case-top'>" + (f"<img src='{logo}' alt=''>" if logo else "") + f"<div class='hosp-name'>{_h(_clean(d['hospital'].get('name')) or 'Hospital')}</div></div>",
           "<div class='case-head'><div class='rule'></div><div class='kicker'>Tumour Board record</div>", f"<h1>{_h(d['patient_line'])}</h1>",
           f"<div class='meta'><b>Cancer:</b> {_h(d['cancer'])}</div>"]
    meta = [f"<b>Case File:</b> {_h(d['case_id'])}"]
    if d["owner"]:
        meta.append(f"<b>Responsible Department:</b> {_h(d['owner'])}")
    meta.append(f"<b>Presenter:</b> {_h(d['presenter'] or 'Not named')}")
    out.append("<div class='meta'>" + " &nbsp;·&nbsp; ".join(meta) + "</div>")
    out.append(f"<div class='question'><div class='kicker'>Question for the board</div><div class='text'>{_h(d['question'] or 'Not recorded.')}</div></div>")
    out.append(f"<p class='meta' style='margin-top:3mm'>{len(d['records'])} board record{'s' if len(d['records']) != 1 else ''}, latest first. Made by Vaidyx on {_h(_dmy_hm(d['generated']))}. {_h(CONFIDENTIAL)}"
               + (" <span class='synthetic'>SYNTHETIC DATA: demo hospital, fake patients.</span>" if d["synthetic"] else "") + "</p></div>")
    if not d["records"]:
        out.append("<p class='none'>No board decision recorded for this Case File yet.</p>")
    total = len(d["records"])
    for i, x in enumerate(d["records"]):
        title = f"Board record {total - i} of {total}" + (f" · {x['where']}" if x["where"] else "")
        out.append("<div class='record'>")
        if x["taken_up"]:
            out.append(f"<div style='margin-bottom:1mm'>{_pill(TAKEN_UP, 'warn')}</div>")
        out.append(_record_html(x["view"], title=title, notes=x["notes"]))
        out.append("</div>")
    out.append(f"<p class='muted small' style='margin-top:6mm'>{_h(SCOPE_LINE)}</p>")
    return _doc(f"Tumour Board record, {d['case_id']}", "".join(out))


# ---------------------------------------------------------------------------------------------------- the PDF, in a separate process
# Runs in the pdf venv with -I (no user site, no current directory on the path): reads the HTML on stdin, writes the PDF on stdout.
# Only data: URIs may be fetched (the images are inline); a file, http or any other link is refused, so nothing outside the page is read.
_RENDER = r"""
import logging, sys
for n in ("weasyprint", "fontTools", "fontTools.subset", "fontTools.ttLib"):
    logging.getLogger(n).setLevel(logging.ERROR)
import weasyprint
try:
    fetcher = weasyprint.URLFetcher(allowed_protocols=("data",), allow_redirects=False, timeout=5)
except AttributeError:
    def fetcher(url, *a, **k):
        if not str(url).startswith("data:"):
            raise ValueError("Only inline images are allowed")
        return weasyprint.default_url_fetcher(url)
page = sys.stdin.buffer.read().decode("utf-8")
sys.stdout.buffer.write(weasyprint.HTML(string=page, url_fetcher=fetcher).write_pdf())
"""


def _python() -> Path:
    return Path(PDF_PYTHON)


def available() -> bool:
    """True when the pdf venv's Python is there (WeasyPrint lives there, CLAUDE.md "How to run")."""
    p = _python()
    return p.is_file() and os.access(p, os.X_OK)


def render_pdf(page: str, timeout: float | None = None) -> bytes:
    """The PDF of `page` (HTML), made by WeasyPrint in the pdf venv as a separate process: the HTML goes in on stdin, the PDF comes back on
    stdout; nothing is written to disk. At most MAX_PARALLEL renders at once. PdfError when the venv is missing, the render fails or
    it runs past `timeout` seconds (the process is killed)."""
    py = _python()
    if not available():
        raise PdfError("The PDF tool is not installed on this server.", "pdf_unavailable")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    lib = str(py.parent.parent / "lib")
    env["LD_LIBRARY_PATH"] = lib + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    wait = float(timeout or TIMEOUT)
    if not _SLOTS.acquire(timeout=wait):
        raise PdfError("Too many PDFs are being made right now. Try again in a minute.", "pdf_busy")
    try:
        res = subprocess.run([str(py), "-I", "-c", _RENDER], input=page.encode("utf-8"), capture_output=True, timeout=wait, env=env,
                             cwd=str(py.parent), check=False)
    except subprocess.TimeoutExpired:
        log.warning("meeting pdf: the render took longer than %.0f s and was stopped", wait)
        raise PdfError("Making the PDF took too long. Try again.", "pdf_timeout") from None
    except OSError as e:
        log.warning("meeting pdf: the render could not start (%s)", e)
        raise PdfError("The PDF tool could not be started.", "pdf_unavailable") from None
    finally:
        _SLOTS.release()
    if res.returncode != 0 or not res.stdout.startswith(b"%PDF"):
        log.warning("meeting pdf: the render failed (exit %s): %s", res.returncode, (res.stderr or b"").decode("utf-8", "replace")[-1500:])
        raise PdfError("The PDF could not be made. Try again, or tell the Vaidyx admin.", "pdf_failed")
    return res.stdout


def build_meeting(mid: str, r: dict | None = None) -> tuple[bytes, dict]:
    """(PDF bytes, what it holds: {"cases", "restricted"}) of a meeting. KeyError when the meeting does not exist."""
    d = meeting_data(mid, r)
    return render_pdf(_meeting_page(d)), {"cases": len(d["cases"]), "restricted": d["restricted"], "date": d["meeting"].get("date") or ""}


def build_case(cid: str, r: dict | None = None) -> tuple[bytes, int]:
    """(PDF bytes, the number of board records) of one Case File. KeyError when it is missing or protected."""
    d = case_data(cid, r)
    return render_pdf(_case_page(d)), len(d["records"])


def filename(kind: str, ident: str, when: str = "") -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", str(ident or "")).strip("-") or "record"
    day = _dmy(when).replace("/", "-") if when else ""
    return f"Tumour-Board-{kind}-{safe}{('-' + day) if day else ''}.pdf"
