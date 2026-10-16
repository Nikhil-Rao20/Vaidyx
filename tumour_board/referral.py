"""Referral to another treating department (V2 item 5.2): the diagnosis changes (a lung work-up turns out to be a colorectal primary), so
the Case File moves.

1. A doctor of the owning department refers the Case File to another treating department with a reason (request()); the hospital
   system's own inter-department referrals are suggested from the HIS encounters (suggestions()), a person decides.
2. The receiving department sees the referral in its inbox and bell (and may read the whole Case File while it is open) and accepts
   or declines (accept(), decline()); the referring department may withdraw an unanswered one (withdraw()).
3. On accept, ownership moves: the receiving department owns the Case File, the referring department stays as a participant (read
   and comment). The new owner picks the new cancer protocol (given with the acceptance, or later on the listing form); the
   Pre-Authorization gate re-runs on the same records with the new gaps (service.list_case re-extracts under the new protocol).
4. The earlier protocol's gate and its open requests are archived read-only in state["gate_history"]; every step is audited
   (referral_requested / accepted / declined / withdrawn, owner_changed) and the other side is told in-app.

No model calls; nothing moves without a person."""
import uuid
from datetime import date, timedelta

from . import access, notify, org, protocol, store

REQUESTED, ACCEPTED, DECLINED, WITHDRAWN = "requested", "accepted", "declined", "withdrawn"
STATUSES = (REQUESTED, ACCEPTED, DECLINED, WITHDRAWN)
RECENT_DAYS = 7  # answered referrals stay in the inboxes this long
MAX_REASON = 1000


class ReferralError(Exception):
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


def _case(case_id):
    c = store.get_case(case_id)
    if not c:
        raise ReferralError("Case not found", 404)
    return c


def _treating(department) -> str:
    did = org.department_id(department) if department else None
    if not did:
        raise ReferralError(f"Unknown department: {department}")
    if org.department_group(did) != "treating":
        raise ReferralError(f"{org.department_name(did)} is a supporting department; a Case File is referred to a treating department")
    return did


def open_(case: dict) -> dict | None:
    return access.open_referral(case)


def find(case: dict, referral_id: str) -> dict:
    r = next((x for x in case.get("referrals") or [] if isinstance(x, dict) and x.get("id") == referral_id), None)
    if not r:
        raise ReferralError("Referral not found", 404)
    return r


def _tell(to: dict, kind: str, case: dict, title: str, text: str, **extra):
    try:
        return notify.notify(to, kind, case["case_id"], title, text, **extra)
    except Exception as e:  # a notification problem never undoes the referral
        return {"error": f"{e.__class__.__name__}: {e}"}


def _patient(case: dict) -> str:
    return (case.get("patient") or {}).get("name") or case["case_id"]


# ---- the hospital system's referrals, suggested -------------------------------------------------------------------------------

def suggestions(case: dict) -> list[dict]:
    """The HIS inter-department referrals (and nothing else) that point at a treating department other than the owner and were not
    acted on or dismissed here: Vaidyx-TB suggests the referral, a person decides (plan 5.2)."""
    out = []
    owner = access.owner(case)
    used = {r.get("his_ref") for r in case.get("referrals") or [] if isinstance(r, dict) and r.get("his_ref")}
    dismissed = set(case.get("referral_suggestions_dismissed") or [])
    for h in ((case.get("his") or {}).get("referrals") or []):
        if not isinstance(h, dict) or not h.get("id") or h["id"] in used or h["id"] in dismissed:
            continue
        to = org.department_id(h.get("to_department") or "")
        if not to or org.department_group(to) != "treating" or to == owner:
            continue
        frm = org.department_id(h.get("from_department") or "")
        out.append({"his_ref": h["id"], "from": frm, "from_name": org.department_name(frm) if frm else (h.get("from_department") or ""),
                    "to": to, "to_name": org.department_name(to), "reason": h.get("reason") or "", "status": h.get("status") or "",
                    "on": _dmy(h.get("requested")), "accepted_on": _dmy(h.get("accepted")) if h.get("accepted") else "",
                    "encounter_number": h.get("encounter_number") or "",
                    "text": f"The hospital system records a referral from {org.department_name(frm) if frm else (h.get('from_department') or 'another department')} "
                            f"to {org.department_name(to)} on {_dmy(h.get('requested'))}" + (f" ({h.get('status')})" if h.get("status") else "")
                            + (f": {h.get('reason')}" if h.get("reason") else "") + ". Refer this Case File?"})
    return out


def dismiss_suggestion(case_id: str, his_ref: str, user: str, note: str = "") -> dict:
    """The owner decides not to follow the hospital system's referral (audited; the suggestion is not shown again)."""
    case = _case(case_id)
    if not any(s["his_ref"] == his_ref for s in suggestions(case)):
        raise ReferralError("No such suggested referral", 404)
    case.setdefault("referral_suggestions_dismissed", []).append(his_ref)
    store.save_case(case)
    store.audit(case_id, {"kind": "referral_suggestion_dismissed", "by": user, "his_ref": his_ref, "note": str(note or "")[:500]})
    return case


# ---- request, withdraw, decline, accept ------------------------------------------------------------------------------------------

def request(case_id: str, to_department, reason: str, user: str, his_ref: str = "") -> dict:
    """The owning department refers the Case File to another treating department, with a reason. The receiving department is told."""
    case = _case(case_id)
    owner = access.owner(case)
    if not owner:
        raise ReferralError("This Case File has no owning department yet: record the owner first, then refer it.", 409)
    to = _treating(to_department)
    if to == owner:
        raise ReferralError(f"{org.department_name(to)} already owns this Case File", 409)
    if open_(case):
        raise ReferralError(f"A referral to {org.department_name(open_(case)['to'])} is waiting for an answer; withdraw it first.", 409)
    reason = str(reason or "").strip()
    if not reason:
        raise ReferralError("A referral needs a reason (what changed in the diagnosis).")
    his_ref = str(his_ref or "").strip()
    if his_ref and not any(s["his_ref"] == his_ref for s in suggestions(case)):
        raise ReferralError("No such suggested referral", 404)
    rec = {"id": "R" + uuid.uuid4().hex[:6], "from": owner, "to": to, "reason": reason[:MAX_REASON], "by": user, "at": store.now_iso(), "status": REQUESTED,
           "his_ref": his_ref or None, "protocol_before": case.get("protocol") or "", "setting_before": case.get("setting") or ""}
    case.setdefault("referrals", []).append(rec)
    store.save_case(case)
    store.audit(case_id, {"kind": "referral_requested", "by": user, "referral": rec["id"], "from": owner, "to": to, "reason": rec["reason"], "his_ref": rec["his_ref"]})
    p = case.get("patient") or {}
    _tell({"department": to}, "referral", case, f"Referral of {_patient(case)} ({case_id}) from {org.department_name(owner)}",
          f"{org.department_name(owner)} refers this Tumour Board Case File to {org.department_name(to)}. Reason: {rec['reason'].rstrip('.')}."
          + (f" UHID {p['mrn']}." if p.get("mrn") else "") + " Accept or decline on the Case File or in your inbox; on acceptance your department owns the Case File and picks the cancer protocol.",
          referral=rec["id"], from_department=owner, to_department=to, uhid=p.get("mrn", ""), by=user)
    return rec


def _open_or_409(case: dict, referral_id: str = "") -> dict:
    """The referral waiting for an answer, which must be the one the caller saw (`referral_id`): a referral withdrawn and replaced while
    the click was in flight is never answered in its place (review Phase 5 M3)."""
    rec = open_(case)
    if not rec:
        raise ReferralError("No referral is waiting for an answer", 409)
    if referral_id and rec.get("id") != referral_id:
        raise ReferralError("That referral is not waiting for an answer any more", 409)
    return rec


def withdraw(case_id: str, user: str, note: str = "", referral_id: str = "") -> dict:
    """The referring department takes back an unanswered referral; the receiving department is told."""
    case = _case(case_id)
    rec = _open_or_409(case, referral_id)
    rec.update(status=WITHDRAWN, answered_by=user, answered_at=store.now_iso(), note=str(note or "")[:500])
    store.save_case(case)
    store.audit(case_id, {"kind": "referral_withdrawn", "by": user, "referral": rec["id"], "to": rec["to"], "note": rec["note"]})
    _tell({"department": rec["to"]}, "referral_answered", case, f"Referral of {_patient(case)} ({case_id}) withdrawn by {org.department_name(rec['from'])}",
          "The referring department took the referral back." + (f" Note: {rec['note']}" if rec["note"] else ""), referral=rec["id"], status=WITHDRAWN, by=user)
    return rec


def decline(case_id: str, user: str, note: str = "", referral_id: str = "") -> dict:
    """The receiving department declines; the Case File stays with its owner, who is told."""
    case = _case(case_id)
    rec = _open_or_409(case, referral_id)
    rec.update(status=DECLINED, answered_by=user, answered_at=store.now_iso(), note=str(note or "")[:500])
    store.save_case(case)
    store.audit(case_id, {"kind": "referral_declined", "by": user, "referral": rec["id"], "from": rec["from"], "to": rec["to"], "note": rec["note"]})
    _tell({"department": rec["from"]}, "referral_answered", case, f"Referral of {_patient(case)} ({case_id}) declined by {org.department_name(rec['to'])}",
          f"{org.department_name(rec['to'])} declined the referral; the Case File stays with {org.department_name(rec['from'])}." + (f" Note: {rec['note']}" if rec["note"] else ""),
          referral=rec["id"], status=DECLINED, by=user)
    return rec


def _archive_gate(case: dict, st: dict, rec: dict, user: str) -> dict:
    """The earlier protocol's gate and its open requests, kept read-only (plan 5.2: history, never re-evaluated)."""
    from . import rules
    prot = protocol.get(case["protocol"]) if case.get("protocol") else {}
    entry = {"archived_at": store.now_iso(), "by": user, "reason": "referral", "referral": rec["id"], "owner": rec["from"], "owner_name": org.department_name(rec["from"]),
             "protocol": case.get("protocol") or "", "protocol_version": prot.get("version") or "", "setting": case.get("setting") or "",
             "setting_label": protocol.setting_label(case["protocol"], case["setting"]) if case.get("protocol") and case.get("setting") else "",
             "hospital_level": case.get("hospital_level") or "", "gate": st.get("gate"),
             "actions": [{k: a.get(k) for k in ("id", "requirement", "label", "department", "department_id", "level", "level_label", "status", "due", "what", "accession")}
                         for a in st.get("actions") or [] if a.get("source") == "pre_authorization" and a.get("status") != "completed"],
             "signature": rules.case_signature(case["case_id"], st)}
    st.setdefault("gate_history", []).append(entry)
    return entry


def accept(case_id: str, user: str, note: str = "", protocol_id: str = "", setting: str = "", hospital_level: str = "", referral_id: str = ""):
    """The receiving department accepts: ownership moves, the referring department stays as a participant, the earlier gate is
    archived; with a protocol the Case File is listed under it at once (the gate re-runs on the same records), otherwise it waits
    for the new owner to pick one. Returns {"referral", "case", "job"} (job None when no protocol was given)."""
    from . import service
    case = _case(case_id)
    rec = _open_or_409(case, referral_id)
    protocol_id = str(protocol_id or "").strip()
    if protocol_id:
        if not protocol.exists(protocol_id):
            raise ReferralError(f"Unknown protocol: {protocol_id}")
        if setting and setting not in {x["id"] for x in protocol.settings(protocol_id)}:
            raise ReferralError(f"Unknown NCG setting for {protocol_id}: {setting}")
        if hospital_level and hospital_level not in org.LEVELS:
            raise ReferralError("Hospital level must be essential or optimal")
    st = store.get_state(case_id)
    archived = _archive_gate(case, st, rec, user)
    old, new = rec["from"], rec["to"]
    case["department"] = new
    parts = [p for p in case.get("participants") or [] if org.department_id((p or {}).get("department")) != new]
    if old not in [org.department_id((p or {}).get("department")) for p in parts]:
        parts.append({"department": old, "since": store.now_iso(), "by": user, "reason": f"referred the Case File to {org.department_name(new)}"})
    case["participants"] = parts
    case.setdefault("owner_history", []).append({"from": old, "to": new, "at": store.now_iso(), "by": user, "referral": rec["id"]})
    rec.update(status=ACCEPTED, answered_by=user, answered_at=store.now_iso(), note=str(note or "")[:500], protocol_after=protocol_id or "", setting_after=setting or "")
    if not protocol_id:  # the new owner picks the protocol later: the Case File waits, nothing is checked meanwhile
        case["protocol"], case["setting"] = "", ""
        case["listing"] = {"status": "awaiting_listing", "previous": case.get("listing"), "reason": "referred", "since": store.now_iso()}
    store.save_case(case)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "referral_accepted", "by": user, "referral": rec["id"], "from": old, "to": new, "note": rec["note"],
                          "protocol_before": archived["protocol"], "protocol_after": protocol_id or None, "setting_after": setting or None, "gate_archived": bool(archived.get("gate"))})
    store.audit(case_id, {"kind": "owner_changed", "by": user, "from": old, "to": new, "referral": rec["id"]})
    job = None
    if protocol_id:
        job = service.list_case(case_id, protocol_id, setting or "", case.get("board_date") or "", hospital_level or case.get("hospital_level") or "", user)
    else:
        from . import rules
        rules.close_requests_on_referral(case_id, org.department_name(new), user)  # nothing stays asked of a department for a protocol nobody follows any more (review Phase 5 M4)
        service.recheck(case_id, user)  # no protocol: the gate is cleared until the new owner lists the Case File
    case = store.get_case(case_id)
    plabel = (protocol.get(protocol_id) or {}).get("label") or protocol_id if protocol_id else ""
    what = (f"{org.department_name(new)} now owns the Case File and listed it under {plabel}" + (f" ({protocol.setting_label(protocol_id, setting)})" if setting else "")
            + "; the Pre-Authorization re-runs on the same records.") if protocol_id else f"{org.department_name(new)} now owns the Case File and will pick the cancer protocol."
    _tell({"department": old}, "referral_answered", case, f"Referral of {_patient(case)} ({case_id}) accepted by {org.department_name(new)}",
          what + f" {org.department_name(old)} stays as a participating department (read and comment)." + (f" Note: {rec['note']}" if rec["note"] else ""),
          referral=rec["id"], status=ACCEPTED, protocol=protocol_id or None, by=user)
    return {"referral": rec, "case": case, "job": job}


# ---- views -----------------------------------------------------------------------------------------------------------------------

def _row(case: dict, r: dict) -> dict:
    p = case.get("patient") if isinstance(case.get("patient"), dict) else {}
    return {**r, "from_name": org.department_name(r.get("from")), "to_name": org.department_name(r.get("to")), "on": _dmy(r.get("at")),
            "answered_on": _dmy(r.get("answered_at")) if r.get("answered_at") else "",
            "case_id": case.get("case_id"), "patient": {"name": p.get("name", ""), "mrn": p.get("mrn", ""), "agesex": p.get("agesex", "")}, "uhid": p.get("mrn", ""),
            "protocol": case.get("protocol", ""), "board_date": case.get("board_date", "")}


def public(case: dict) -> dict:
    """The referral block of a Case File view: the open referral, the history, the hospital system's suggestions."""
    hist = [_row(case, r) for r in case.get("referrals") or [] if isinstance(r, dict)]
    o = open_(case)
    return {"open": _row(case, o) if o else None, "history": hist, "suggestions": suggestions(case),
            "dismissed": list(case.get("referral_suggestions_dismissed") or [])}


def inbox(r: dict) -> list[dict]:
    """The referrals addressed to the user's departments (waiting for an answer, and those answered in the last days) and the ones
    its departments sent, newest first; `can_answer` says whether this user may accept or decline. Admins see every open one."""
    mine = set((r or {}).get("departments") or {})
    admin = bool((r or {}).get("admin"))
    if not mine and not admin:
        return []
    since = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
    out = []
    for case, _st in notify._cases():
        for i, rec in enumerate(case.get("referrals") or []):
            if not isinstance(rec, dict):
                continue
            to_me, from_me = rec.get("to") in mine, rec.get("from") in mine
            if not (to_me or from_me or admin):
                continue
            if rec.get("status") != REQUESTED and str(rec.get("answered_at") or "")[:10] < since:
                continue
            out.append({**_row(case, rec), "direction": "to" if to_me else ("from" if from_me else "other"), "_i": i,
                        "can_answer": rec.get("status") == REQUESTED and org.can(r, "answer_referral", rec.get("to")),
                        "can_withdraw": rec.get("status") == REQUESTED and (admin or (from_me and bool(r.get("treating", {}).get(rec.get("from")))))})
    out.sort(key=lambda x: (str(x.get("at") or ""), x["_i"]), reverse=True)  # newest first; the later referral of a Case File first within one second
    for x in out:
        x.pop("_i", None)
    return out
