"""A resident's proposals (18 Oct 2026): "Ask Dr X to sign off".

A resident on a Case File team fills everything in but signs nothing: every consultant-only step becomes a proposal the treating
consultant approves or returns with a note. On approval the very same function the consultant's own screen calls runs, in the
consultant's name (the audit shows the consultant as the actor and the proposal id next to it); a returned proposal changes nothing.

Stored on case.json "proposals": [{"id", "action", "payload", "note", "by", "at", "status": pending | approved | returned,
"decided_by", "decided_at", "decision_note", "result"}]. Actions and what runs on approval:
  waive          payload {key: requirement id, reason}                 confirm.record("waive") + service.recheck
  not_needed     payload {slot: summary line id, reason} (the line's "Not needed (reason)")   slots.not_needed; or {key, reason} as waive
  confirm        payload {type, key, fields, reason} (confirm.TYPES)    confirm.record(type) + service.recheck (+ re-extract for a type change)
  mark_ready     payload {ready, note, list, meeting_id, presenter, reason} (+ meeting_date, presenter_name for the line shown)
                                                                        board.send_to_board (+ ready_hook.on_ready, as the route);
                                                                        ready false: board.mark_ready (withdraw)
  send_request   payload {action_id, message, due, subject} or {department, label, what, message, due}   dept_requests.send / create_free
  urgency        payload {level 1..5, note}                             team.set_urgency
  refer          payload {to, reason, his_ref}                          referral.request
  typed_value    payload {slot or fact, value, note}                    slots.set_value (the "Enter a value" line action)
  published_case payload {result, quotes}                               published.add
  key_value      payload {fact_id, value, doc_id} (the Check step's one-tap confirm)   steps.confirm_key; refused (409) when the
                 value or its report changed after the resident checked it
  reason         payload {value} (one of steps.REASONS)                 steps.set_reason
  staging_confirm payload {which: anatomic | prognostic, stage, signature, note}, pinned to the draft the resident saw
                                                                        staging.confirm; refused (409) when the draft changed since
PROPOSAL_EXECUTORS {action: fn} is the registry; another module may replace or add an executor (register(action, fn)). An approved
proposal whose action has no executor is stored as "approved, pending executor" and runs once one is registered (execute_pending).
Executors are callables fn(case_id, payload, user, roles, note) -> dict; each checks the consultant's permission the way the
consultant's own route does, and raises ValueError, PermissionError (or a module error with .status) with a plain message.

The consultant is told in-app (kind sign_off: "Dr X asks you to sign off: <action> (<patient>)"), the resident hears back (approved or
returned). Everything is audited in the Case File. No model calls."""
import re
import uuid

from . import access, board, confirm, dept_requests, org, profiles, protocol, referral, store, team

PENDING, APPROVED, RETURNED = "pending", "approved", "returned"
ACTIONS = ("waive", "not_needed", "confirm", "mark_ready", "send_request", "urgency", "refer", "typed_value", "published_case",
           "key_value", "reason", "staging_confirm")
LABELS = {"waive": "waive a requirement", "not_needed": "mark a line not needed", "confirm": "record a confirmation", "mark_ready": "send to the board",
          "send_request": "send a request", "urgency": "set the urgency", "refer": "refer the Case File", "typed_value": "enter a value", "published_case": "add a published case",
          "key_value": "confirm a key value", "reason": "set the reason for discussion", "staging_confirm": "confirm the draft stage"}
STALE_KEY = "The value changed after the resident checked it: check it again."
STALE_DRAFT = "The draft changed after the resident saw it: work it out again."
# action -> fn(case_id, payload, user, roles, note) -> dict. The modules that own typed values and published cases register theirs.
PROPOSAL_EXECUTORS: dict = {}
PENDING_EXECUTOR = "approved, pending executor"
MAX_NOTE = 500


class ProposalError(Exception):
    def __init__(self, message, status=400, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


def register(action: str, fn) -> None:
    """Another module registers the executor of an action (typed_value: slots.py; published_case: published.py)."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown proposal action: {action}")
    PROPOSAL_EXECUTORS[action] = fn


def _note(s, limit=MAX_NOTE) -> str:
    return " ".join(str(s or "").split())[:limit]


def _case(case_id: str) -> dict:
    c = store.get_case(case_id)
    if not c:
        raise ProposalError("Case not found", 404, "not_found")
    return c


def list_(case: dict) -> list[dict]:
    return [p for p in (case or {}).get("proposals") or [] if isinstance(p, dict) and p.get("id")]


def view(p: dict) -> dict:
    return {**p, "by_name": profiles.display_name(p.get("by") or ""), "decided_by_name": profiles.display_name(p.get("decided_by") or "") if p.get("decided_by") else "",
            "label": LABELS.get(p.get("action"), p.get("action"))}


def find(case: dict, pid: str) -> dict:
    p = next((x for x in list_(case) if x.get("id") == pid), None)
    if not p:
        raise ProposalError("Proposal not found", 404, "not_found")
    return p


# ---- what a resident may propose: checked before it is stored ----------------------------------------------------------------------

def check_payload(action: str, payload, case: dict) -> dict:
    """The payload of a proposal, trimmed to what its executor reads; ValueError with a plain message."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown proposal action '{action}'. Use one of: {', '.join(ACTIONS)}.")
    p = payload if isinstance(payload, dict) else {}
    if action == "not_needed" and str(p.get("slot") or "").strip():
        reason = _note(p.get("reason"))
        if not reason:
            raise ValueError("Say why this line is not needed for this Case File (it is recorded).")
        return {"slot": str(p["slot"]).strip()[:200], "reason": reason}
    if action in ("waive", "not_needed"):
        key = str(p.get("key") or p.get("requirement") or "").strip()
        reason = _note(p.get("reason"))
        if not key:
            raise ValueError("Say which requirement is not needed.")
        if not reason:
            raise ValueError("A reason is required for a waiver (it is recorded).")
        if case.get("protocol"):
            ids = {q["id"] for q in protocol.get(case["protocol"]).get("mandatory", [])}
            if key not in ids:
                raise ValueError(f"'{key}' is not a requirement of this Case File's protocol.")
        return {"key": key, "reason": reason}
    if action == "confirm":
        ctype = str(p.get("type") or "")
        if ctype not in confirm.TYPES or ctype in ("waive", "resolve_flag"):
            raise ValueError("Choose a confirmation type: " + ", ".join(t for t in confirm.TYPES if t not in ("waive", "resolve_flag")) + ".")
        clean = confirm.validate(ctype, str(p.get("key") or ""), p.get("fields") or {}, str(p.get("reason") or ""))
        return {"type": ctype, "key": clean["key"], "fields": clean["fields"], "reason": clean["reason"]}
    if action == "mark_ready":  # night-v3 item 1.4: the whole send (meeting, list, presenter, reason); checked again by board.send_to_board
        ready = bool(p.get("ready", True))
        if not ready:
            return {"ready": False, "note": _note(p.get("note"))}
        lst = str(p.get("list") or "discussion")
        if lst not in board.SEND_LISTS:
            raise ValueError("Choose for discussion or for noting.")
        out = {"ready": True, "note": _note(p.get("note")), "list": lst, "meeting_id": str(p.get("meeting_id") or "").strip()[:80],
               "presenter": str(p.get("presenter") or "").strip()[:120], "reason": _note(p.get("reason"))}
        # what the consultant's "Sign-offs from your team" line shows (not read by the executor)
        from . import meetings
        m = meetings.get(out["meeting_id"]) if out["meeting_id"] else None
        if out["meeting_id"] and not m:
            raise ValueError("Meeting not found.")
        out["meeting_date"] = (m or {}).get("date") or ""
        out["presenter_name"] = profiles.display_name(out["presenter"]) if out["presenter"] else ""
        return out
    if action == "send_request":
        if p.get("action_id"):
            return {"action_id": str(p["action_id"]), "message": str(p.get("message") or "")[:dept_requests.MAX_MESSAGE], "due": str(p.get("due") or "")[:10],
                    "subject": str(p.get("subject") or "")[:dept_requests.MAX_SUBJECT]}
        dept = str(p.get("department") or "").strip()
        label = _note(p.get("label"), 160)
        if not dept or not org.department_id(dept):
            raise ValueError("Choose the department the request goes to.")
        if not label:
            raise ValueError("Say what you are asking for.")
        return {"department": org.department_id(dept), "label": label, "what": _note(p.get("what")), "message": str(p.get("message") or "")[:dept_requests.MAX_MESSAGE],
                "due": str(p.get("due") or "")[:10]}
    if action == "urgency":
        return {"level": team.check_level(p.get("level")), "note": _note(p.get("note"))}
    if action == "refer":
        to = str(p.get("to") or "").strip()
        reason = _note(p.get("reason"), referral.MAX_REASON)
        if not to or not org.department_id(to):
            raise ValueError("Choose the treating department the Case File is referred to.")
        if not reason:
            raise ValueError("A referral needs a reason (what changed in the diagnosis).")
        return {"to": org.department_id(to), "reason": reason, "his_ref": str(p.get("his_ref") or "")}
    if action == "typed_value":
        from . import slots
        slot = str(p.get("slot") or p.get("fact") or "").strip()
        value = " ".join(str(p.get("value") if p.get("value") is not None else "").split())
        if not slot or not value:
            raise ValueError("Name the line and type the value.")
        prot = protocol.get(case["protocol"]) if case.get("protocol") and protocol.exists(case["protocol"]) else None
        kind, fid = slots.parse_slot(slot, prot)
        if kind != "fact":
            raise ValueError("A value is typed on a field line, not on a record.")
        if fid not in slots.typable_facts(prot) and fid not in slots.EXTRA_FACTS:
            raise ValueError("This line is not typed by hand: it comes from a signed report (ask the department, or propose not needed).")
        return {"slot": slot, "value": slots.validate_value(fid, value), "note": _note(p.get("note"))}
    if action == "published_case":
        from . import published
        res = p.get("result") if isinstance(p.get("result"), dict) else None
        if not res or not str(res.get("title") or "").strip():
            raise ValueError("Pick a published case (its title is needed).")
        try:
            clean = published.validate_result(res)
        except published.PublishedError as e:
            raise ValueError(str(e))
        return {"result": clean, "quotes": [q for q in (p.get("quotes") or []) if isinstance(q, dict)][:10]}
    if action == "key_value":  # the same checks as POST /cases/{id}/key-checks (steps.confirm_key)
        fid = str(p.get("fact_id") or "").strip()
        if not re.fullmatch(r"[a-z0-9_]{1,64}", fid):
            raise ValueError("Unknown value.")
        value = str(p.get("value") if p.get("value") is not None else "")[:500]
        if not value.strip():
            raise ValueError("Name the value to confirm.")
        return {"fact_id": fid, "value": value, "doc_id": str(p.get("doc_id") or "")[:64]}
    if action == "reason":  # the same check as PUT /cases/{id}/reason (steps.set_reason)
        from . import steps
        v = str(p.get("value") or "")
        if v not in steps.REASONS:
            raise ValueError("Choose one of the listed reasons.")
        return {"value": v}
    if action == "staging_confirm":  # the draft the resident saw: which one, its stage and the reports it was worked out from
        which = str(p.get("which") or "anatomic").strip().lower()
        if which not in ("anatomic", "prognostic"):
            raise ValueError("Say which draft: anatomic or prognostic.")
        stage = str(p.get("stage") or "").strip()[:32]
        signature = str(p.get("signature") or "").strip()[:128]
        if not stage or not signature:
            raise ValueError("Name the draft stage you checked (open the Stage card again).")
        now = draft_now(case.get("case_id") or "", which)
        if not now or now["status"] != "staged":
            raise ValueError("There is no draft stage to confirm." if which == "anatomic" else "There is no prognostic stage group to confirm.")
        if now["stage"] != stage or now["signature"] != signature:
            raise ValueError("The draft changed after you saw it: open the Stage card again.")
        return {"which": which, "stage": stage, "signature": signature, "note": _note(p.get("note"))}
    raise ValueError(f"Unknown proposal action '{action}'.")


def propose(case_id: str, action: str, payload, note: str, user: str, roles: dict) -> dict:
    """A resident on the team records a proposal; the owning department's consultants are asked to sign off."""
    c = _case(case_id)
    access.check_not_archived(c)
    if not access.may(roles, "propose", c):
        raise ProposalError("You are not on this Case File's team as a resident." if roles.get("resident") else "Only a resident proposes; a consultant does the action itself.", 403, "not_team_resident")
    try:
        clean = check_payload(action, payload, c)
    except ValueError as e:
        raise ProposalError(str(e), 400, "bad_payload")
    rec = {"id": "P" + uuid.uuid4().hex[:8], "action": action, "payload": clean, "note": _note(note), "by": user, "at": store.now_iso(), "status": PENDING,
           "decided_by": "", "decided_at": "", "decision_note": "", "result": None}
    c.setdefault("proposals", []).append(rec)
    store.save_case(c)
    store.audit(case_id, {"kind": "proposal_created", "by": user, "proposal": rec["id"], "action": action, "payload": clean, "note": rec["note"]})
    name = profiles.display_name(user)
    line = team.patient_line(c)
    team.tell_consultants(c, "sign_off", f"{name} asks you to sign off: {LABELS.get(action, action)} ({line})",
                          (f"{rec['note']} " if rec["note"] else "") + "Approve or return it from your home or the Case File.", proposal=rec["id"], action=action, by=user)
    return view(rec)


# ---- executors: the same functions the consultant's own buttons call ---------------------------------------------------------------

def _dept_of_requirement(case: dict, key: str) -> str | None:
    if not case.get("protocol"):
        return None
    return next((q.get("department") for q in protocol.get(case["protocol"]).get("mandatory", []) if q["id"] == key), None) or None


def _doc_department(d) -> str | None:
    d = d or {}
    return None if d.get("his") else d.get("department")


def _recheck(case_id: str, user: str):
    from . import service
    return service.recheck(case_id, user) if (store.get_case(case_id) or {}).get("protocol") else store.get_state(case_id)


def _exec_waive(case_id, payload, user, roles, note):
    c = _case(case_id)
    if payload.get("slot"):  # a summary line marked not needed: the line's own action (slots.not_needed checks the waive permission)
        from . import slots
        try:
            done = slots.not_needed(case_id, payload["slot"], payload["reason"], user, roles)
        except slots.SlotError as e:
            raise ProposalError(str(e), e.status, "cannot_run")
        return {"confirmation": (done.get("confirmation") or {}).get("id"), "record": done.get("record")}
    access.require(roles, "waive", c, _dept_of_requirement(c, payload["key"]))
    rec = confirm.record(case_id, "waive", payload["key"], {}, payload["reason"], user)
    st = _recheck(case_id, user)
    return {"confirmation": rec["id"], "gate_passed": (st.get("gate") or {}).get("passed")}


def _exec_confirm(case_id, payload, user, roles, note):
    from . import service
    c = _case(case_id)
    ctype, key = payload["type"], payload["key"]
    spec = confirm.TYPES[ctype]
    if spec["target"] in ("document", "fact"):
        doc_id = key.partition(":")[0] if spec["target"] == "fact" else key
        d = store.get_doc(case_id, doc_id) if doc_id else None
        if not d:
            raise ValueError("That record is no longer in the Case File.")
        if ctype == "confirm_match" and not d.get("outside"):
            org.require(roles, "match")
        else:
            access.require(roles, spec["action"], c, _doc_department(d))
        if ctype == "dismiss_failed" and d.get("state") != "error":
            raise ValueError("Only a document that failed to read can be dismissed.")
    else:
        access.require(roles, spec["action"], c)
    rec = confirm.record(case_id, ctype, key, payload.get("fields") or {}, payload.get("reason") or "", user)
    st = _recheck(case_id, user)
    job = service.reextract_document(case_id, key, user) if ctype == "confirm_doc_type" else None
    return {"confirmation": rec["id"], "gate_passed": (st.get("gate") or {}).get("passed"), "job": job["id"] if job else None}


def _exec_mark_ready(case_id, payload, user, roles, note):
    c = _case(case_id)
    access.require(roles, "mark_ready", c)
    ready = bool(payload.get("ready", True))
    if ready:  # the same send as the consultant's own (night-v3 item 1.4), in the consultant's name; an empty presenter is the consultant
        c = board.send_to_board(case_id, user, list=payload.get("list") or "discussion", meeting_id=payload.get("meeting_id") or "",
                                presenter=payload.get("presenter") or "", note=payload.get("note") or "", reason=payload.get("reason") or "")
    else:
        c = board.mark_ready(case_id, user, ready=False, note=payload.get("note") or "")
    if ready:  # the summary prose and the heads' briefs are prepared in the background, as POST /cases/{id}/ready does
        try:
            from . import ready_hook
            ready_hook.on_ready(case_id, user)
        except Exception:
            pass
    return {"board_ready": c.get("board_ready") or None}


def _exec_send_request(case_id, payload, user, roles, note):
    c = _case(case_id)
    if payload.get("action_id"):
        access.require(roles, "send_request", c)
        a = dept_requests.send(case_id, payload["action_id"], user, roles, message=payload.get("message") or "", due=payload.get("due") or "", subject_text=payload.get("subject") or "")
    else:
        access.require(roles, "create_request", c)
        a = dept_requests.create_free(case_id, payload["department"], payload["label"], user, roles, message=payload.get("message") or "", due=payload.get("due") or "",
                                      what=payload.get("what") or "")
    return {"action": a["id"], "status": a.get("status"), "department": a.get("department")}


def _exec_urgency(case_id, payload, user, roles, note):
    c = _case(case_id)
    access.require(roles, "set_urgency", c)
    return {"urgency": team.set_urgency(case_id, payload["level"], user, note=payload.get("note") or "")}


def _exec_refer(case_id, payload, user, roles, note):
    c = _case(case_id)
    access.require(roles, "refer", c)
    rec = referral.request(case_id, payload["to"], payload["reason"], user, his_ref=payload.get("his_ref") or "")
    return {"referral": rec["id"], "to": rec["to"]}


def _exec_typed_value(case_id, payload, user, roles, note):
    from . import slots
    c = _case(case_id)
    access.require(roles, "confirm", c)  # the same rule as POST /cases/{id}/slots/{slot}/value
    try:
        rec = slots.set_value(case_id, payload["slot"], payload["value"], payload.get("note") or "", user)
    except slots.SlotError as e:
        raise ProposalError(str(e), e.status, "cannot_run")
    return {"typed_value": rec}


def _exec_published_case(case_id, payload, user, roles, note):
    from . import published
    c = _case(case_id)
    access.require(roles, "upload_to_case", c)  # the same rule as POST /cases/{id}/published
    if not access.is_owner_doctor(roles, c):
        raise PermissionError("Only the owning department's consultants sign off a published case.")
    try:
        item = published.add(case_id, payload["result"], payload.get("quotes") or [], user)
    except published.PublishedError as e:
        raise ProposalError(str(e), e.status, "cannot_run")
    return {"published": item.get("id"), "title": item.get("title")}


def key_value_now(case_id: str, fact_id: str, roles: dict | None = None) -> tuple[str, str] | None:
    """The key value as the Check step shows it now ({value, report doc_id} of the fact line found in a report), or None."""
    from . import slots
    s = next((x for x in slots._all_slots(slots.build(case_id, roles)) if x.get("kind") == "fact" and x.get("fact_id") == fact_id), None)
    if not s or s.get("status") != "found":
        return None
    return (s.get("value") or ""), ((s.get("quote") or {}).get("doc_id") or "")


def _exec_key_value(case_id, payload, user, roles, note):
    from . import steps
    c = _case(case_id)
    access.require(roles, "confirm", c)  # the same rule as POST /cases/{id}/key-checks
    if key_value_now(case_id, payload["fact_id"], roles) != (payload.get("value") or "", payload.get("doc_id") or ""):
        raise ProposalError(STALE_KEY, 409, "stale")
    rec = steps.confirm_key(case_id, payload["fact_id"], payload["value"], payload.get("doc_id") or "", user)
    return {"key_check": {"fact_id": payload["fact_id"], **rec}}


def _exec_reason(case_id, payload, user, roles, note):
    from . import steps
    c = _case(case_id)
    access.require(roles, "confirm", c)  # the same rule as PUT /cases/{id}/reason
    return {"board_reason": steps.set_reason(case_id, payload["value"], user)}


def draft_now(case_id: str, which: str) -> dict | None:
    """{stage, signature, status} of the stored draft (anatomic, or the prognostic one inside it), or None."""
    from . import staging
    d = (store.get_state(case_id) or {}).get("staging")
    x = staging._target(d, which)
    if not x:
        return None
    return {"stage": x.get("stage"), "signature": d.get("signature"), "status": x.get("status")}


def _exec_staging_confirm(case_id, payload, user, roles, note):
    from . import staging
    c = _case(case_id)
    access.require(roles, "confirm", c)  # the same rule as POST /cases/{id}/staging/confirm
    which = payload.get("which") or "anatomic"
    now = draft_now(case_id, which)
    if not now or now["stage"] != payload.get("stage") or now["signature"] != payload.get("signature"):
        raise ProposalError(STALE_DRAFT, 409, "stale")
    staging.confirm(case_id, user, payload.get("note") or note or "", which)  # guard 1: counted once a doctor confirms, in that doctor's name
    return {"which": which, "stage": payload["stage"], "confirmed_by": user}


PROPOSAL_EXECUTORS.update({"waive": _exec_waive, "not_needed": _exec_waive, "confirm": _exec_confirm, "mark_ready": _exec_mark_ready,
                           "send_request": _exec_send_request, "urgency": _exec_urgency, "refer": _exec_refer,
                           "typed_value": _exec_typed_value, "published_case": _exec_published_case,
                           "key_value": _exec_key_value, "reason": _exec_reason, "staging_confirm": _exec_staging_confirm})


def _run(case_id: str, p: dict, user: str, roles: dict, note: str) -> dict:
    fn = PROPOSAL_EXECUTORS.get(p["action"])
    if fn is None:
        return {"status": PENDING_EXECUTOR}
    try:
        out = fn(case_id, p.get("payload") or {}, user, roles, note)
    except PermissionError as e:
        raise ProposalError(str(e), 403, "forbidden")
    except ProposalError:
        raise
    except (ValueError, KeyError) as e:
        raise ProposalError(str(e).strip("'") or "The action could not be done.", 400, "cannot_run")
    except Exception as e:
        status = getattr(e, "status", None)
        if isinstance(status, int):  # dept_requests.RequestError, referral.ReferralError, team.TeamError, access.AccessError
            raise ProposalError(str(e), status, "cannot_run")
        raise
    return {"status": "done", **(out if isinstance(out, dict) else {})}


def approve(case_id: str, pid: str, user: str, roles: dict, note: str = "") -> tuple[dict, dict]:
    """The consultant approves: the action runs in the consultant's name; the proposal records the result; the resident hears back.
    A refused or failing action leaves the proposal pending and raises ProposalError with the plain message."""
    c = _case(case_id)
    access.check_not_archived(c)
    access.require(roles, "approve_proposal", c)
    p = find(c, pid)
    if p.get("status") != PENDING:
        raise ProposalError(f"This proposal was already {p.get('status')}.", 409, "not_pending")
    result = _run(case_id, p, user, roles, note)
    c = _case(case_id)  # the action may have rewritten case.json (ready mark, urgency, referral)
    p = find(c, pid)
    p.update({"status": APPROVED, "decided_by": user, "decided_at": store.now_iso(), "decision_note": _note(note), "result": result})
    store.save_case(c)
    store.audit(case_id, {"kind": "proposal_approved", "by": user, "proposal": pid, "action": p["action"], "proposed_by": p.get("by"), "note": p["decision_note"],
                          "result": result})
    line = team.patient_line(c)
    team._tell({"user": p["by"]}, "sign_off", case_id, f"Approved: {LABELS.get(p['action'], p['action'])} ({line})",
               f"{profiles.display_name(user)} signed off your proposal." + (f" Note: {p['decision_note']}" if p["decision_note"] else "")
               + (" It runs when its module is ready." if result.get("status") == PENDING_EXECUTOR else ""), proposal=pid, status="approved", by=user)
    return view(p), result


def return_(case_id: str, pid: str, user: str, roles: dict, note: str) -> dict:
    """The consultant returns the proposal with a note; nothing changes on the Case File."""
    c = _case(case_id)
    access.require(roles, "approve_proposal", c)
    p = find(c, pid)
    if p.get("status") != PENDING:
        raise ProposalError(f"This proposal was already {p.get('status')}.", 409, "not_pending")
    note = _note(note)
    if not note:
        raise ProposalError("Tell the resident what to change (a note is required).", 400, "note_required")
    p.update({"status": RETURNED, "decided_by": user, "decided_at": store.now_iso(), "decision_note": note})
    store.save_case(c)
    store.audit(case_id, {"kind": "proposal_returned", "by": user, "proposal": pid, "action": p["action"], "proposed_by": p.get("by"), "note": note})
    team._tell({"user": p["by"]}, "sign_off", case_id, f"Returned: {LABELS.get(p['action'], p['action'])} ({team.patient_line(c)})",
               f"{profiles.display_name(user)} returned your proposal. Note: {note}", proposal=pid, status="returned", by=user)
    return view(p)


def execute_pending(case_id: str, user: str = "", roles: dict | None = None) -> list[dict]:
    """Run the approved proposals still waiting for an executor (typed values, published cases) once their module registered it;
    each runs in the approving consultant's name. Returns the proposals that ran."""
    c = _case(case_id)
    ran = []
    for p in list_(c):
        if p.get("status") != APPROVED or (p.get("result") or {}).get("status") != PENDING_EXECUTOR or p["action"] not in PROPOSAL_EXECUTORS:
            continue
        who = p.get("decided_by") or user
        result = _run(case_id, p, who, roles or org.roles(who), p.get("decision_note") or "")
        p["result"] = result
        ran.append(p)
    if ran:
        store.save_case(c)
        for p in ran:
            store.audit(case_id, {"kind": "proposal_executed", "by": p.get("decided_by") or user, "proposal": p["id"], "action": p["action"], "result": p["result"]})
    return [view(p) for p in ran]


# ---- the home: what waits for whom ---------------------------------------------------------------------------------------------------

def _cases():
    for c in store.list_cases():
        if c.get("case_id") in __import__("tumour_board.config", fromlist=["config"]).PROTECTED_CASES:
            continue
        yield c


def waiting_for(r: dict, cases=None) -> list[dict]:
    """What waits for this consultant on the Case Files its department owns: residents' proposals, join requests and the records whose
    reading needs a confirmation (kind review). Newest first."""
    out = []
    if not isinstance(r, dict) or r.get("disabled") or not r.get("treating"):
        return out
    for c in (cases if cases is not None else store.list_cases()):
        if not access.is_owner_consultant(r, c) or not access.owner(c) or access.is_archived(c) or access.hidden(r, c):
            continue
        line = team.patient_line(c)
        for p in list_(c):
            if p.get("status") == PENDING:
                out.append({"id": p["id"], "kind": "proposal", "case_id": c["case_id"], "patient_line": line, "title": f"Sign off: {LABELS.get(p['action'], p['action'])}",
                            "by": p.get("by"), "by_name": profiles.display_name(p.get("by") or ""), "at": p.get("at") or "", "action": p.get("action"), "note": p.get("note") or ""})
        for x in ((c.get("team") or {}).get("pending") or []):
            if isinstance(x, dict) and x.get("user"):
                out.append({"id": f"{c['case_id']}:join:{x['user']}", "kind": "join", "case_id": c["case_id"], "patient_line": line, "title": "Join request",
                            "by": x["user"], "by_name": profiles.display_name(x["user"]), "at": x.get("requested_at") or ""})
        st = store.get_state(c["case_id"])
        for q in ((st or {}).get("gate") or {}).get("requirements") or []:
            if isinstance(q, dict) and q.get("status") == "needs_confirmation":
                out.append({"id": f"{c['case_id']}:review:{q.get('id')}", "kind": "review", "case_id": c["case_id"], "patient_line": line,
                            "title": f"Needs your confirmation: {q.get('label') or q.get('id')}", "by": "", "by_name": "", "at": (st.get("gate") or {}).get("evaluated") or c.get("created") or ""})
    out.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return out


def mine(r: dict, cases=None) -> list[dict]:
    """A resident's own proposals that are still waiting or were returned (the resident home's "waiting for Dr X" items)."""
    out = []
    u = (r or {}).get("user")
    if not u:
        return out
    for c in (cases if cases is not None else store.list_cases()):
        if access.hidden(r, c):
            continue
        for p in list_(c):
            if p.get("by") == u and p.get("status") in (PENDING, RETURNED):
                cons = team.owner_consultants(c)
                out.append({"id": p["id"], "kind": "proposal", "case_id": c["case_id"], "patient_line": team.patient_line(c), "status": p["status"],
                            "title": (f"Waiting for {', '.join(profiles.display_name(x) for x in cons[:2])}" if cons and p["status"] == PENDING else
                                      f"Returned by {profiles.display_name(p.get('decided_by') or '')}: {p.get('decision_note') or ''}" if p["status"] == RETURNED else "Waiting for the consultant"),
                            "action": p.get("action"), "at": p.get("decided_at") or p.get("at") or ""})
    out.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return out
