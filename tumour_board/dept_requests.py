"""Requests to departments (V2 items 4.2 and 4.3): suggested by the Pre-Authorization gate, sent by the treating doctor.

In V1 every gap opened a request and notified the department at once. In V2 the gate only SUGGESTS: rules.sync_actions opens the
request with status "suggested" and nothing goes out. The treating doctor reads the draft message (draft()), edits it and sends it
in-app (send(): status "pending", the department notified, audited), or opens it in their own mail program ("Open in mail": a
mailto: link to the department's address with the same draft; the server never sends email) or copies it. A free request
("Notify <department>", create_free()) with no gap behind it is created and sent in one step: a pre-anaesthetic check or a
medication review that no protocol lists as a record.

The supporting department reads its inbox (notify.inbox), acknowledges (acknowledge()) and sends "done" back with a note (done());
both tell the owning department. A gap request closes itself when the next re-check (a re-fetch from the HIS, an upload) finds the
record, even if "done" was never sent (rules.sync_actions); a free request closes on "done" (nothing in the Case File can prove it)
or when the owner closes it (close_free()).

Every step is stored on the action (sent / acknowledged / done, with history) and audited in the Case File (request_sent,
request_created, request_acknowledged, request_done, request_closed_by_owner). Dates are shown DD/MM/YYYY. No model calls.
"""
import urllib.parse
import uuid
from datetime import date, timedelta

from . import notify, org, store

DEFAULT_SLA_DAYS = 3
SUGGESTED = "suggested"
OPEN = ("pending", "overdue")
MAX_MESSAGE = 4000
MAX_SUBJECT = 200


class RequestError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _dmy(s) -> str:
    s = str(s or "")[:10]
    try:
        return date.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return s


def _today() -> date:
    return date.today()


def find(state: dict, action_id: str) -> dict:
    a = next((x for x in (state or {}).get("actions") or [] if isinstance(x, dict) and x.get("id") == action_id), None)
    if not a:
        raise RequestError("Request not found.", 404)
    if a.get("source") != "pre_authorization":
        raise RequestError("Only a Pre-Authorization request is sent this way; a Tumour Board action reaches the department when the decision is recorded.", 409)
    return a


def is_free(a: dict) -> bool:
    """A request the doctor wrote by hand (no protocol record behind it)."""
    return a.get("origin") == "doctor" or not a.get("requirement")


def is_sent(a: dict) -> bool:
    """The department received this request: sent through send(), or a V1 request opened before 4.2 (pending / overdue, notified at once)."""
    return bool(a.get("sent")) or a.get("status") in OPEN


def encounter_numbers(case: dict) -> dict:
    """The patient's IP No. and OP No. to print on a request (the newest of each from the Case File's identifiers)."""
    out = {}
    for x in ((case or {}).get("patient") or {}).get("ids") or []:
        if isinstance(x, dict) and x.get("kind") in ("ip_no", "op_no") and x.get("value"):
            out[x["kind"]] = x["value"]  # later entries are newer encounters (learned in encounter order)
    return out


def _patient_line(case: dict) -> str:
    p = (case or {}).get("patient") or {}
    parts = [p.get("name") or "name not recorded"]
    if p.get("agesex"):
        parts.append(p["agesex"])
    if p.get("mrn"):
        parts.append(f"UHID {p['mrn']}")
    enc = encounter_numbers(case)
    if enc.get("ip_no"):
        parts.append(f"IP No. {enc['ip_no']}")
    if enc.get("op_no"):
        parts.append(f"OP No. {enc['op_no']}")
    return ", ".join(parts)


def _to(a: dict) -> dict:
    """Where the request goes: {department (id or None), name, email, role}."""
    if a.get("role") == "coordinator" or org.is_coordinator_name(a.get("department_id")) or (not a.get("department_id") and org.is_coordinator_name(a.get("department"))):
        return {"department": None, "name": org.COORDINATOR_NAME, "email": "", "role": "coordinator"}
    did = org.department_id(a.get("department_id") or a.get("department") or "")
    return {"department": did, "name": org.department_name(did) if did else str(a.get("department") or ""), "email": org.department_email(did) if did else "", "role": None}


def proposed_due(a: dict, today=None) -> str:
    """The due date to propose when sending: the SLA of the record from the day it is sent (not from the day the gap was found)."""
    today = today or _today()
    try:
        days = int(a.get("sla_days") or DEFAULT_SLA_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_SLA_DAYS
    return (today + timedelta(days=max(days, 0))).isoformat()


def subject(case: dict, a: dict) -> str:
    p = (case or {}).get("patient") or {}
    who = p.get("name") or case.get("case_id")
    uhid = f" ({p['mrn']})" if p.get("mrn") else ""
    return f"Tumour Board Case File {case.get('case_id')}: {a.get('label') or 'record'} for {who}{uhid}"


def body(case: dict, a: dict, due: str = "", to: dict | None = None) -> str:
    """The request message: the patient (UHID, IP / OP No.), what is missing, the order or accession No. when there is one, the due date.
    Plain text the doctor edits before sending; no model writes it."""
    to = to or _to(a)
    due = due or a.get("due") or proposed_due(a)
    owner = org.department_name(case.get("department")) if case.get("department") else ""
    lines = [f"To: {to['name']}", f"Tumour Board Case File {case.get('case_id')}", f"Patient: {_patient_line(case)}"]
    if owner:
        lines.append(f"Treating department: {owner}")
    if is_free(a):
        lines.append(f"Request: {a.get('label') or ''}")
        if a.get("what"):
            lines.append(f"Details: {a['what']}")
    else:
        lvl = f" ({a['level_label']})" if a.get("level_label") else ""
        lines.append(f"Required record: {a.get('label') or a.get('requirement')}{lvl}")
        lines.append(f"What is missing: {a.get('what') or 'see the Case File'}")
    if a.get("accession"):
        po = a.get("pending_order") or {}
        stage = {"ordered": "ordered", "scheduled": "scheduled", "sample_collected": "sample collected", "cancelled": "order cancelled"}.get(po.get("stage"), "")
        lines.append(f"Accession / order No.: {a['accession']}" + (f" ({stage} in the hospital system)" if stage else ""))
    when = f"Needed by: {_dmy(due)}"
    if case.get("board_date"):
        when += f" (Tumour Board on {_dmy(case['board_date'])})"
    lines.append(when)
    lines.append("")
    if is_free(a):
        lines.append("Please record your note in the hospital system and send \"done\" back from your Tumour Board inbox.")
    elif case.get("his"):
        lines.append("Please complete and digitally sign the report in your own reporting system. The Case File is re-fetched from the hospital system and "
                     "this request closes by itself when the final, signed report arrives; \"done\" from your Tumour Board inbox tells us to re-fetch.")
    else:
        lines.append("Please provide the final, signed report. The Case File is re-checked when it arrives and this request closes by itself.")
    return "\n".join(lines)


def mailto(to: dict, subj: str, text: str) -> str:
    """A mailto: link the doctor's own mail program opens (plan 4.2: the server sends no email). "" when the department has no address."""
    if not to.get("email"):
        return ""
    q = urllib.parse.urlencode({"subject": subj, "body": text.replace("\r\n", "\n").replace("\n", "\r\n")}, quote_via=urllib.parse.quote)  # CRLF line breaks (RFC 6068)
    return f"mailto:{to['email']}?{q}"


def draft(case: dict, a: dict, user: str = "") -> dict:
    """What the Notify dialog shows: the address, a subject, the editable body, the proposed due date and the mailto: link."""
    to = _to(a)
    due = a.get("due") if a.get("status") in OPEN and a.get("due") else proposed_due(a)  # a sent request (also a V1 one) keeps its due date
    subj = subject(case, a)
    text = body(case, a, due, to)
    return {"action_id": a.get("id"), "to": to, "subject": subj, "body": text, "due": due, "mailto": mailto(to, subj, text),
            "accession": a.get("accession"), "uhid": ((case.get("patient") or {}).get("mrn") or ""), "encounter": encounter_numbers(case),
            "free": is_free(a), "sent": a.get("sent"), "status": a.get("status")}


def _signature(user: str, roles: dict | None) -> str:
    depts = [org.department_name(d) for d in ((roles or {}).get("treating") or {})]
    who = str(user or "")
    return f"Sent by {who}" + (f" ({', '.join(depts)})" if depts else "") + " through the Tumour Board."


def _check_due(due) -> str:
    s = str(due or "")[:10]
    if not s:
        return ""
    try:
        d = date.fromisoformat(s)
    except ValueError:
        raise RequestError("The due date must be a date (YYYY-MM-DD).")
    if d < _today():
        raise RequestError(f"The due date {_dmy(s)} is in the past: choose today or a later date.")
    return s


def send(case_id: str, action_id: str, user: str, roles: dict | None = None, message: str = "", due: str = "", subject_text: str = "") -> dict:
    """The treating doctor sends the request in-app: the department (or the MDT Coordinator) is notified with the edited message, the
    request opens (status pending), the due date is set, everything is audited. Sending a sent request again is a reminder."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    st = store.get_state(case_id)
    a = find(st, action_id)
    if a.get("status") == "completed":
        raise RequestError("This request is closed.", 409)
    to = _to(a)
    if not to["department"] and not to["role"]:
        raise RequestError(f"No department of the hospital matches \"{a.get('department')}\": ask the root admin to route this record.", 409)
    due = _check_due(due) or (a.get("due") if a.get("status") in OPEN and a.get("due") else "") or proposed_due(a)
    text = str(message or "").strip()[:MAX_MESSAGE] or body(case, a, due, to)
    sig = _signature(user, roles)  # the real sender's line is always the last line, whatever the text says (review M2)
    text = text if text.rstrip().endswith(sig) else text.rstrip() + "\n" + sig
    subj = str(subject_text or "").strip()[:MAX_SUBJECT] or subject(case, a)
    now = store.now_iso()
    again = bool(a.get("sent"))
    rec = {"by": user, "at": now, "to": to["department"] or to["role"], "to_name": to["name"], "subject": subj, "message": text, "channel": "in_app",
           "count": int((a.get("sent") or {}).get("count") or 0) + 1, "what": a.get("what")}
    a["sent"] = rec
    a["due"] = due
    a["status"] = "overdue" if due < _today().isoformat() else "pending"
    a.pop("changed_since_sent", None)
    a.setdefault("history", []).append({"ts": now, "event": (f"Sent again to {to['name']} by {user}" if again else f"Sent to {to['name']} by {user}") + f", due {_dmy(due)}"})
    n = notify.notify({"department": to["department"]} if to["department"] else {"role": "coordinator"}, "request", case_id,
                      f"{a.get('label') or 'Request'} needed for {(case.get('patient') or {}).get('name') or case_id} ({case_id})" + (" (reminder)" if again else ""),
                      a.get("what") or a.get("label") or "", action_id=a["id"], requirement=a.get("requirement"), due=due, level=a.get("level"),
                      level_label=a.get("level_label", ""), accession=a.get("accession"), message=text, sent_by=user, reminder=again,
                      uhid=(case.get("patient") or {}).get("mrn") or "", encounter=encounter_numbers(case))
    rec["notification_id"] = n.get("id")
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "request_sent", "action": a["id"], "requirement": a.get("requirement"), "department": to["name"], "by": user, "due": due,
                          "reminder": again, "chars": len(text)})
    return a


def create_free(case_id: str, department: str, label: str, user: str, roles: dict | None = None, message: str = "", due: str = "", what: str = "") -> dict:
    """A request with no gap behind it ("Notify <department>"): created and sent in one step. The department may be treating or
    supporting; never the MDT Coordinator (the coordinator's inbox is for previous board records)."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    did = org.department_id(department or "")
    if not did:
        raise RequestError(f"Unknown department: {department!r}.")
    label = " ".join(str(label or "").split())[:160]
    if not label:
        raise RequestError("Say what you are asking for (for example: pre-anaesthetic check-up).")
    due = _check_due(due) or (_today() + timedelta(days=DEFAULT_SLA_DAYS)).isoformat()
    now = store.now_iso()
    st = store.get_state(case_id)
    a = {"id": "A" + uuid.uuid4().hex[:6], "source": "pre_authorization", "origin": "doctor", "requirement": None, "label": label,
         "department": org.department_name(did), "department_id": did, "level": None, "level_label": "", "source_doc_id": None, "accession": None,
         "pending_order": None, "what": " ".join(str(what or "").split())[:500], "status": "pending", "created": now, "due": due, "sla_days": DEFAULT_SLA_DAYS,
         "history": [{"ts": now, "event": f"Request written by {user}, to {org.department_name(did)}"}]}
    st.setdefault("actions", []).append(a)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "request_created", "action": a["id"], "department": a["department"], "label": label, "by": user})
    return send(case_id, a["id"], user, roles, message=message, due=due)


def _tell_owner(case: dict, a: dict, kind: str, title: str, text: str, **extra) -> dict | None:
    """The owning department hears (or, for a Case File without an owner, the doctor who sent the request)."""
    to = {"department": case["department"]} if case.get("department") and org.department_id(case["department"]) else (
        {"user": (a.get("sent") or {}).get("by")} if (a.get("sent") or {}).get("by") else None)
    if not to:
        return None
    try:
        return notify.notify(to, kind, case["case_id"], title, text, action_id=a["id"], requirement=a.get("requirement"), **extra)
    except Exception as e:  # a notification problem never undoes the action
        return {"error": f"{e.__class__.__name__}: {e}"}


# ---- reminders on the owner's behalf (V2 item 6.1) ---------------------------------------------------------------------------------

def _owner_name(case: dict) -> str:
    did = org.department_id(case.get("department") or "") if case.get("department") else None
    return org.department_name(did) if did else "the treating team"


def _sender(user: str, roles: dict | None, case: dict) -> str:
    """How the reminder names its sender: the MDT Coordinator sends on the owning department's behalf; an owner's doctor in its own name."""
    r = roles or {}
    own = org.department_id(case.get("department") or "") if case.get("department") else None
    if r.get("coordinator") and not (own and own in (r.get("treating") or {})):
        return f"{user} (MDT Coordinator, on behalf of {_owner_name(case)})"
    return f"{user} ({_owner_name(case)})"


def remind(case_id: str, action_id: str, user: str, roles: dict | None = None, note: str = "") -> dict:
    """A reminder about one request: a sent one reaches the department holding it again (kind request_reminder, the request keeps its
    due date); a suggested one that nobody sent reminds the owning department to send it (kind owner_reminder). Recorded on the request
    (`reminders`), in its history and in the audit log. Nothing is sent to anyone the request does not already concern."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    st = store.get_state(case_id)
    a = find(st, action_id)
    if a.get("status") == "completed":
        raise RequestError("This request is closed; nothing to remind about.", 409)
    note = " ".join(str(note or "").split())[:MAX_MESSAGE]
    now, sender = store.now_iso(), _sender(user, roles, case)
    patient = (case.get("patient") or {}).get("name") or case_id
    label = a.get("label") or "Request"
    if is_sent(a):
        to = _to(a)
        if not to["department"] and not to["role"]:
            raise RequestError(f"No department of the hospital matches \"{a.get('department')}\".", 409)
        due = a.get("due") or ""
        text = (f"Reminder about the request sent on {_dmy((a.get('sent') or {}).get('at'))}: {a.get('what') or label}."
                + (f" Due {_dmy(due)}." if due else "") + (f" {note}" if note else "") + f" Sent by {sender}.")
        n = notify.notify({"department": to["department"]} if to["department"] else {"role": "coordinator"}, "request_reminder", case_id,
                          f"Reminder: {label} needed for {patient} ({case_id})", text, action_id=a["id"], requirement=a.get("requirement"), due=due,
                          accession=a.get("accession"), sent_by=user, on_behalf_of=case.get("department") or "", uhid=(case.get("patient") or {}).get("mrn") or "",
                          encounter=encounter_numbers(case))
        kind, target = "request_reminded", to["name"]
    else:
        to_dept = {"department": case["department"]} if case.get("department") and org.department_id(case["department"]) else None
        if not to_dept:
            raise RequestError("This Case File has no owning department to remind; the request can be sent from the Pre-Authorization tab.", 409)
        text = (f"The Pre-Authorization suggested a request to {a.get('department') or 'a department'} ({a.get('what') or label}) that nobody has sent yet."
                + (f" The board is on {_dmy(case.get('board_date'))}." if case.get("board_date") else "") + (f" {note}" if note else "") + f" Reminder from {sender}.")
        n = notify.notify(to_dept, "owner_reminder", case_id, f"Suggested request not sent: {label} for {patient} ({case_id})", text,
                          action_id=a["id"], requirement=a.get("requirement"), sent_by=user)
        kind, target = "owner_reminded", _owner_name(case)
    rec = {"by": user, "at": now, "to": target, "note": note, "notification_id": n.get("id"), "sent": is_sent(a)}
    a.setdefault("reminders", []).append(rec)
    a.setdefault("history", []).append({"ts": now, "event": f"Reminder to {target} by {user}" + (f": {note}" if note else "")})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": kind, "action": a["id"], "requirement": a.get("requirement"), "to": target, "by": user, "note": note[:300]})
    return a


def remind_owner(case_id: str, user: str, roles: dict | None = None, note: str = "") -> dict:
    """One reminder to the owning department about the Case File as a whole before the board: the suggested requests nobody sent, the
    overdue requests, the summary (missing or stale) and whether the owner has marked it ready (V2 item 6.1). Audited."""
    from . import rules
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    if not (case.get("department") and org.department_id(case["department"])):
        raise RequestError("This Case File has no owning department to remind.", 409)
    st = store.get_state(case_id)
    acts = [a for a in st.get("actions") or [] if a.get("source") == "pre_authorization" and a.get("status") != "completed"]
    unsent = [a for a in acts if a.get("status") == SUGGESTED]
    overdue = [a for a in acts if is_sent(a) and a.get("due") and str(a["due"])[:10] < _today().isoformat()]
    arts = st.get("artefacts") or {}
    summ = arts.get("summary")
    stale = bool(summ and summ.get("signature") and rules.stale_reason(summ["signature"], rules.case_signature(case_id, st)))
    parts = []
    if unsent:
        parts.append(f"{len(unsent)} suggested request(s) not sent: " + "; ".join(f"{a.get('label')} ({a.get('department')})" for a in unsent[:6]))
    if overdue:
        parts.append(f"{len(overdue)} request(s) overdue: " + "; ".join(f"{a.get('label')} ({a.get('department')}, due {_dmy(a.get('due'))})" for a in overdue[:6]))
    if not summ:
        parts.append("no Case File summary compiled yet")
    elif stale:
        parts.append("the Case File summary is stale (records changed since it was compiled)")
    if not (case.get("board_ready") or {}).get("at"):
        parts.append("not marked ready for the board")
    note = " ".join(str(note or "").split())[:MAX_MESSAGE]
    patient = (case.get("patient") or {}).get("name") or case_id
    text = ((f"Before the board on {_dmy(case.get('board_date'))}: " if case.get("board_date") else "Before the board: ")
            + ("; ".join(parts) if parts else "nothing open") + "." + (f" {note}" if note else "") + f" Reminder from {_sender(user, roles, case)}.")
    n = notify.notify({"department": case["department"]}, "owner_reminder", case_id, f"Before the board: {patient} ({case_id})", text, sent_by=user,
                      unsent=len(unsent), overdue=len(overdue))
    now = store.now_iso()
    case.setdefault("reminders", []).append({"by": user, "at": now, "note": note, "notification_id": n.get("id"), "unsent": len(unsent), "overdue": len(overdue)})
    store.save_case(case)
    store.audit(case_id, {"kind": "owner_reminded", "by": user, "unsent": len(unsent), "overdue": len(overdue), "summary": "none" if not summ else ("stale" if stale else "ready"),
                          "note": note[:300]})
    return {"case_id": case_id, "to": _owner_name(case), "text": text, "unsent": len(unsent), "overdue": len(overdue), "notification_id": n.get("id")}


def acknowledge(case_id: str, action_id: str, user: str) -> dict:
    """The supporting department has read the request and is working on it."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    st = store.get_state(case_id)
    a = find(st, action_id)
    if a.get("status") == SUGGESTED or not is_sent(a):
        raise RequestError("This request has not been sent yet.", 409)
    if a.get("status") == "completed":
        raise RequestError("This request is closed.", 409)
    if a.get("acknowledged"):
        raise RequestError(f"Already acknowledged by {a['acknowledged'].get('by')}.", 409)
    now = store.now_iso()
    a["acknowledged"] = {"by": user, "at": now}
    a.setdefault("history", []).append({"ts": now, "event": f"Acknowledged by {user} ({a.get('department')})"})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "request_acknowledged", "action": a["id"], "requirement": a.get("requirement"), "department": a.get("department"), "by": user})
    patient = (case.get("patient") or {}).get("name") or case_id
    _tell_owner(case, a, "request_acknowledged", f"{a.get('label') or 'Request'} acknowledged by {a.get('department')} for {patient} ({case_id})",
                f"{user} ({a.get('department')}) has read the request and is working on it.", by=user)
    return a


def done(case_id: str, action_id: str, user: str, note: str = "") -> dict:
    """The supporting department sends "done" back: the record is signed in its own system. A gap request stays open until the
    re-check finds the record (the owner is told to re-fetch); a free request closes here."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    st = store.get_state(case_id)
    a = find(st, action_id)
    if a.get("status") == SUGGESTED or not is_sent(a):
        raise RequestError("This request has not been sent yet.", 409)
    if a.get("status") == "completed":
        raise RequestError("This request is closed.", 409)
    if a.get("done"):
        raise RequestError(f"\"Done\" was already sent by {a['done'].get('by')}.", 409)
    note = " ".join(str(note or "").split())[:500]
    now = store.now_iso()
    a["done"] = {"by": user, "at": now, "note": note}
    if not a.get("acknowledged"):
        a["acknowledged"] = {"by": user, "at": now, "implied": True}
    free = is_free(a)
    ev = f"Done, sent back by {user} ({a.get('department')})" + (f": {note}" if note else "")
    if free:
        a["status"], a["completed"], a["closed_by"] = "completed", now, user
        ev += " (closed: no record of the Case File can confirm a free request)"
    a.setdefault("history", []).append({"ts": now, "event": ev})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "request_done", "action": a["id"], "requirement": a.get("requirement"), "department": a.get("department"), "by": user, "note": note,
                          "closed": free})
    patient = (case.get("patient") or {}).get("name") or case_id
    his = bool(case.get("his"))
    if free:
        text = f"{user} ({a.get('department')}) sent \"done\"" + (f": {note}" if note else "") + ". The request is closed."
    elif his:
        text = (f"{user} ({a.get('department')}) sent \"done\"" + (f": {note}" if note else "")
                + ". Re-fetch from the hospital system: the request closes by itself when the final, signed record arrives.")
    else:
        text = f"{user} ({a.get('department')}) sent \"done\"" + (f": {note}" if note else "") + ". The request closes when the record reaches the Case File."
    _tell_owner(case, a, "request_done", f"\"Done\" from {a.get('department')}: {a.get('label') or 'request'} for {patient} ({case_id})", text,
                by=user, note=note, refetch_offer=his and not free, closed=free)
    return a


def close_free(case_id: str, action_id: str, user: str, note: str = "") -> dict:
    """The owner closes a free request (a gap request closes itself when the record arrives, or through a waiver)."""
    case = store.get_case(case_id)
    if not case:
        raise RequestError("Case File not found.", 404)
    st = store.get_state(case_id)
    a = find(st, action_id)
    if not is_free(a):
        raise RequestError("A request for a protocol record closes by itself when the record arrives; waive the requirement if it is not needed.", 409)
    if a.get("status") == "completed":
        raise RequestError("This request is closed.", 409)
    note = " ".join(str(note or "").split())[:500]
    now = store.now_iso()
    a["status"], a["completed"], a["closed_by"] = "completed", now, user
    a.setdefault("history", []).append({"ts": now, "event": f"Closed by {user}" + (f": {note}" if note else "")})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "request_closed_by_owner", "action": a["id"], "department": a.get("department"), "by": user, "note": note})
    if a.get("sent") and a.get("department_id"):
        try:
            notify.notify({"department": a["department_id"]}, "request_closed", case_id,
                          f"{a.get('label') or 'Request'} closed for {(case.get('patient') or {}).get('name') or case_id} ({case_id})",
                          f"The request was closed by {user}" + (f": {note}" if note else "") + ".", action_id=a["id"], requirement=None, level=None)
        except Exception:
            pass
    return a


def summary(state: dict) -> dict:
    """Counts for a Case File view: suggested (unsent), sent (open), done (awaiting the record), closed."""
    acts = [a for a in (state or {}).get("actions") or [] if isinstance(a, dict) and a.get("source") == "pre_authorization"]
    return {"suggested": sum(1 for a in acts if a.get("status") == SUGGESTED),
            "sent": sum(1 for a in acts if a.get("status") in OPEN),
            "done": sum(1 for a in acts if a.get("status") in OPEN and a.get("done")),
            "closed": sum(1 for a in acts if a.get("status") == "completed")}
