"""Follow-up actions from the Tumour Board to department inboxes (plan item 7.4).

Each action of a recorded board decision becomes a request in the Responsible Department's inbox (item 4.4), with a due
date (the one typed, else today + the protocol's post_board.follow_up_default_days, default 14). Overdue is worked out on
display (notify.inbox), never stored here.

A new document of the Case File can SUGGEST closing an action: the action's task names a document type ("MRI pelvis after
neoadjuvant chemoradiation" asks for an MRI), and a ready document of that type arrived after the action was created. The
suggestion is shown; a person closes the action (close_action) or rejects the suggestion (dismiss_suggestion). Nothing here
closes an action by itself, and nothing here reads a document's content: only its document type (the clinician-confirmed one
when present: callers pass documents through rules.case_docs) and when it arrived.

Task words -> document types: the document type keywords of item 3.2 (protocols/doc_type_keywords.json: patterns,
title-only words, case-sensitive gene names, ignore phrases such as "CT guided"), the facts.json document type ids written as
words ("pet ct", "bone scan"), and the few task words in TASK_WORDS ("repeat biopsy" asks for a histopathology report). Only
the investigation types in REQUESTABLE count: a task such as "Follow up in OPD" or "Refer to Radiation Oncology" names no
record to wait for, so it never gets a suggestion. A type whose match sits inside a match of a type that beats it is dropped
("PET-CT" is pet_ct, not ct).

No model calls. Callers save the state and write the audit events (each helper returns what changed).
"""
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from functools import lru_cache

from . import config, doctype, notify, org, protocol, store

log = logging.getLogger(__name__)

DEFAULT_DAYS = 14
OPEN = ("pending", "overdue")

# Document types a board action can ask for (records a department produces). Treatment and administrative types
# (operative note, discharge / treatment summary, clinical note, referral, tumour board record, other) are left out on
# purpose: "Surgery: APR" or "Follow up in 3 months" is not a request for one document.
REQUESTABLE = ("ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan", "histopathology", "cytology", "ihc",
               "molecular", "lab", "endoscopy", "pulmonary_function")

# Words a task uses for a record that the header keywords of item 3.2 do not carry (those read report titles, not requests).
TASK_WORDS = {
    "histopathology": ["biopsy", "biopsies", "rebiopsy", "re-biopsy", "HPR", "histopathological examination"],
    "ihc": ["PD-L1", "PDL1", "Ki-67", "Ki67", "MMR IHC", "MMR status"],
    "molecular": ["mutation", "mutational", "genetic testing", "germline testing", "MSI"],
    "lab": ["blood counts", "tumour marker levels", "tumor marker levels"],
    "pulmonary_function": ["lung function"],
}


def _today() -> date:
    return date.today()


def _notify(*a, **kw):
    """In-app notification (item 4.4); a notification problem never breaks recording (same pattern as rules._notify)."""
    try:
        return notify.notify(*a, **kw)
    except Exception as e:  # unknown department, disk problem: the board record still stands
        log.warning("follow-up notification failed (%s: %s)", e.__class__.__name__, e)
        return {"error": f"{e.__class__.__name__}: {e}"}


def _dmy(iso) -> str:
    """DD/MM/YYYY (Indian format) for an ISO date or timestamp; the text as given when it cannot be read."""
    s = str(iso or "")
    try:
        return date.fromisoformat(s[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return s


def _when(ts):
    try:
        return datetime.fromisoformat(str(ts or ""))
    except ValueError:
        return None


def default_days(case: dict | None) -> int:
    """The protocol's post_board.follow_up_default_days (14 when the Case File is not listed or the protocol has none)."""
    pid = (case or {}).get("protocol")
    if not pid:
        return DEFAULT_DAYS
    try:
        days = (protocol.get(pid).get("post_board") or {}).get("follow_up_default_days", DEFAULT_DAYS)
        days = int(days)
    except Exception:  # an unknown protocol or a malformed value: the default stands
        return DEFAULT_DAYS
    return days if days > 0 else DEFAULT_DAYS


def _patient(case: dict | None, case_id: str) -> str:
    return ((case or {}).get("patient") or {}).get("name") or case_id


# ---- board decision -> follow-up actions ----------------------------------------------------------------------------

def board_actions(case_id: str, record: dict, by: str = "") -> list[dict]:
    """The follow-up actions for a newly recorded board decision (the caller appends them to state["actions"] and saves).

    One action per entry of record["actions"] ({task, department, due}). The department is kept as typed and resolved to a
    department id through org (names and aliases: "Radio-diagnosis" -> radiology); a department that does not resolve gets
    department_id None and no notification (the coordinator sees it in the Case File); an action typed for the MDT Coordinator
    goes to the coordinator role (V2 item 2.1). A known department is notified (kind "board_action")."""
    case = store.get_case(case_id) or {}
    days = default_days(case)
    patient = _patient(case, case_id)
    rid = str(record.get("id") or "")
    out = []
    for a in record.get("actions") or []:
        if not isinstance(a, dict):
            continue
        task = str(a.get("task") or "").strip()
        dept = str(a.get("department") or "").strip()
        to_coord = org.is_coordinator_name(dept)  # an action typed for the MDT Coordinator (a role, not a department)
        did = org.department_id(dept) if dept and not to_coord else None
        due = str(a.get("due") or "").strip() or (_today() + timedelta(days=days)).isoformat()
        now = store.now_iso()
        act = {"id": "A" + uuid.uuid4().hex[:6], "source": "board", "board_record": rid, "label": task or "Board action",
               "department": org.COORDINATOR_NAME if to_coord else dept, "department_id": did, "requirement": None, "what": task, "status": "pending",
               "created": now, "due": due, "history": [{"ts": now, "event": "Created from Tumour Board record " + rid}]}
        if to_coord:
            act["role"] = "coordinator"
        if did or to_coord:
            _notify({"department": did} if did else {"role": "coordinator"}, "board_action", case_id, f"Tumour Board action for {patient} ({case_id}): {act['label']}",
                    f"{task or 'Board action'}. Due {_dmy(due)}.", action_id=act["id"], due=due, board_record=rid, by=by)
        out.append(act)
    return out


def communication_action(case_id: str, record: dict, by: str = "") -> dict | None:
    """A decision the patient has not yet been told about: one follow-up to the MDT Coordinator, due a week after the board
    (12 Oct; Victorian MDM framework 2018 8.4 / 8.5: the recommendation reaches the patient and the GP within a week). None when the
    outcome is not a decision or the record already carries the date."""
    if (record.get("outcome_type") or "decision") != "decision" or record.get("patient_informed_date"):
        return None
    case = store.get_case(case_id) or {}
    patient = _patient(case, case_id)
    rid = str(record.get("id") or "")
    base = str(record.get("board_date") or "")[:10]
    try:
        due = (date.fromisoformat(base) + timedelta(days=7)).isoformat() if base else (_today() + timedelta(days=7)).isoformat()
    except ValueError:
        due = (_today() + timedelta(days=7)).isoformat()
    now = store.now_iso()
    # V2 item 2.1: the MDT Coordinator is a role, not a department; the action sits in the coordinator's inbox row
    act = {"id": "A" + uuid.uuid4().hex[:6], "source": "board", "board_record": rid, "label": "Inform the patient of the Tumour Board outcome and record the date",
           "department": org.COORDINATOR_NAME, "department_id": None, "role": "coordinator", "requirement": None, "communication": True,
           "what": "Tell the patient (or carer) the board's outcome through the lead clinician and record the date and who informed them on the board record (within one week).",
           "status": "pending", "created": now, "due": due, "history": [{"ts": now, "event": "Created from Tumour Board record " + rid + " (patient not yet recorded as informed)"}]}
    _notify({"role": "coordinator"}, "board_action", case_id, f"Tumour Board action for {patient} ({case_id}): {act['label']}", f"Due {_dmy(due)}.", action_id=act["id"], due=due, board_record=rid, by=by)
    return act


# ---- task words -> document types -----------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _task_table() -> dict:
    """{doc type: (regex any case, regex exact capitals or None)} for the requestable types that exist in facts.json."""
    raw = json.loads((config.PROTOCOL_DIR / "doc_type_keywords.json").read_text())
    known = set(protocol.doc_types())
    out = {}
    for t in REQUESTABLE:
        if t not in known:
            continue
        spec = (raw.get("types") or {}).get(t) or {}
        phrases = list(spec.get("patterns") or []) + list(spec.get("title_only") or []) + TASK_WORDS.get(t, []) + [t.replace("_", " ")]
        out[t] = {"any": doctype._alt(phrases), "cs": doctype._alt(spec.get("case_sensitive") or [], 0),
                  "beats": list(spec.get("beats") or [])}
    return out


def task_doc_types(task: str) -> set[str]:
    """The document types a task asks for ("MRI pelvis after chemotherapy" -> {"mri"}; "PET-CT" -> {"pet_ct"}); empty when
    the task names no requestable document type."""
    text = str(task or "")
    if not text.strip():
        return set()
    text = doctype._blank(doctype.table()["ignore"], text)  # "CT guided biopsy" is a biopsy, not a CT
    tb = _task_table()
    spans: dict[str, list] = {}
    for t, rx in tb.items():
        for key in ("any", "cs"):
            if rx[key] is not None:
                spans.setdefault(t, []).extend(m.span() for m in rx[key].finditer(text))
    spans = {t: s for t, s in spans.items() if s}

    def covered(t, span):
        for b, bs in spans.items():
            if b != t and t in tb[b]["beats"] and any(x0 <= span[0] and span[1] <= x1 for x0, x1 in bs):
                return True
        return False
    return {t for t, ss in spans.items() if any(not covered(t, s) for s in ss)}


# ---- closing suggestions --------------------------------------------------------------------------------------------

def _arrived(d: dict, case_id: str):
    """When the document joined this Case File: the later of its upload time ("added") and its filing from the intake area
    (filed.at, item 2.3). None when neither can be read."""
    times = [_when(d.get("added"))]
    f = d.get("filed")
    if isinstance(f, dict) and (not f.get("case_id") or f.get("case_id") == case_id):
        times.append(_when(f.get("at")))
    times = [t for t in times if t is not None]
    return max(times) if times else None


def _doc_title(d: dict) -> str:
    c = d.get("classification") or {}
    return str(c.get("title") or d.get("filename") or d.get("doc_id") or "")


def _is_open_board(a) -> bool:
    return isinstance(a, dict) and a.get("source") == "board" and str(a.get("status") or "pending") in OPEN


def _best_match(a: dict, docs, case_id: str):
    """(document, arrival time) of the newest ready document whose type the task asks for and that arrived after the action
    was created, or (None, None)."""
    wanted = task_doc_types(a.get("what") or "")
    created = _when(a.get("created"))
    if not wanted or created is None:
        return None, None
    dismissed = set(a.get("suggestion_dismissed") or [])
    best, best_at = None, None
    for d in docs or []:
        if not isinstance(d, dict) or d.get("state") != "ready" or d.get("doc_id") in dismissed:
            continue
        if (d.get("classification") or {}).get("doc_type") not in wanted:
            continue
        at = _arrived(d, case_id)
        if at is None or at < created:  # same second counts: timestamps have one-second resolution; a person still decides
            continue
        if best is None or at > best_at:
            best, best_at = d, at
    return best, best_at


def suggest_closures(case_id: str, state: dict, docs, by: str = "") -> list[dict]:
    """Suggest closing open board actions that a newly arrived document may answer. Mutates state["actions"] in place.

    For each open board action: the newest ready document of a type the task asks for, added after the action was created
    and not dismissed for this action, becomes action["suggested_close"] = {doc_id, title, doc_type, at, reason} with a
    history line, and the action's department is notified once for that suggestion (kind "board_action_suggestion"; the
    same suggestion found again on a later check is not repeated). A suggestion whose document no longer qualifies (deleted,
    re-typed, re-processing) is withdrawn with a history line.

    Returns one entry per change, for the caller to audit: {"event": "suggested" | "withdrawn", "action_id", "doc_id",
    "title", "doc_type", "at", "reason"}."""
    case = None
    changes = []
    for a in (state or {}).get("actions") or []:
        if not _is_open_board(a):
            continue
        best, at = _best_match(a, docs, case_id)
        cur = a.get("suggested_close") if isinstance(a.get("suggested_close"), dict) else None
        if best is None:
            if cur:
                a.pop("suggested_close", None)
                a.setdefault("history", []).append({"ts": store.now_iso(), "event": f"Suggestion withdrawn: {cur.get('title') or cur.get('doc_id')} no longer matches this action"})
                changes.append({"event": "withdrawn", "action_id": a.get("id"), **{k: cur.get(k) for k in ("doc_id", "title", "doc_type", "at", "reason")}})
            continue
        if cur and cur.get("doc_id") == best["doc_id"]:
            continue
        dtype = (best.get("classification") or {}).get("doc_type")
        title = _doc_title(best)
        sug = {"doc_id": best["doc_id"], "title": title, "doc_type": dtype, "at": at.isoformat(timespec="seconds"),
               "reason": f"{title} ({dtype}) added on {at.strftime('%d/%m/%Y')} after the action was created"}
        a["suggested_close"] = sug
        a.setdefault("history", []).append({"ts": store.now_iso(), "event": "Closing suggested: " + sug["reason"], "doc_id": best["doc_id"]})
        changes.append({"event": "suggested", "action_id": a.get("id"), **sug})
        did = notify._action_department(a)  # department_id first, then the typed name or alias
        if did:
            if case is None:
                case = store.get_case(case_id) or {}
            _notify({"department": did}, "board_action_suggestion", case_id,
                    f"Tumour Board action may be complete for {_patient(case, case_id)} ({case_id}): {a.get('label') or 'Board action'}",
                    sug["reason"] + ". A person decides whether it closes the action.", action_id=a.get("id"), doc_id=best["doc_id"],
                    board_record=a.get("board_record"), by=by)
    return changes


def _find(state: dict, action_id: str) -> dict:
    for a in (state or {}).get("actions") or []:
        if isinstance(a, dict) and a.get("id") == action_id:
            return a
    raise KeyError(action_id)


def close_action(state: dict, action_id: str, by: str, doc_id: str | None = None, note: str = "") -> dict:
    """A person closes a board action (optionally with the document that answers it). Mutates the state in place.

    KeyError: no such action; ValueError: not a board action, or already closed. Returns the audit event
    {"kind": "board_action_closed", "action", "by", "doc_id", "note", "suggested"} (suggested: the document was the one
    suggested)."""
    a = _find(state, action_id)
    if a.get("source") != "board":
        raise ValueError("Only a Tumour Board action is closed here; a Pre-Authorization request closes when the re-check finds the record.")
    if a.get("status") == "completed":
        raise ValueError("This action is already closed.")
    note = str(note or "").strip()
    doc_id = str(doc_id or "").strip() or None
    sug = a.get("suggested_close") if isinstance(a.get("suggested_close"), dict) else {}
    suggested = bool(doc_id and sug.get("doc_id") == doc_id)
    now = store.now_iso()
    event = f"Closed by {by or 'unknown user'}"
    if doc_id:
        event += f" with {sug.get('title')} ({doc_id})" if suggested else f" with document {doc_id}"
    if note:
        event += f": {note}"
    a["status"], a["completed"], a["closed_by"] = "completed", now, by
    if doc_id:
        a["closed_doc_id"] = doc_id
    a.pop("suggested_close", None)
    a.setdefault("history", []).append({"ts": now, "event": event, **({"doc_id": doc_id} if doc_id else {})})
    return {"kind": "board_action_closed", "action": action_id, "by": by, "doc_id": doc_id, "note": note, "suggested": suggested}


def dismiss_suggestion(state: dict, action_id: str, by: str) -> dict:
    """A person rejects the closing suggestion: that document is never suggested again for this action. Mutates the state.

    KeyError: no such action; ValueError: the action has no suggestion. Returns the audit event
    {"kind": "board_action_suggestion_dismissed", "action", "by", "doc_id"}."""
    a = _find(state, action_id)
    sug = a.get("suggested_close") if isinstance(a.get("suggested_close"), dict) else None
    if not sug or not sug.get("doc_id"):
        raise ValueError("This action has no closing suggestion to dismiss.")
    dismissed = list(a.get("suggestion_dismissed") or [])
    if sug["doc_id"] not in dismissed:
        dismissed.append(sug["doc_id"])
    a["suggestion_dismissed"] = dismissed
    a.pop("suggested_close", None)
    a.setdefault("history", []).append({"ts": store.now_iso(), "event": f"Suggestion dismissed by {by or 'unknown user'}: {sug.get('title') or sug['doc_id']} does not close this action",
                                        "doc_id": sug["doc_id"]})
    return {"kind": "board_action_suggestion_dismissed", "action": action_id, "by": by, "doc_id": sug["doc_id"]}
