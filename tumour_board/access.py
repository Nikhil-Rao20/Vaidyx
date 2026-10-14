"""Who may open a Case File and who may act on it (V2 item 5.1).

A Case File is one cancer episode of one patient (a UHID) owned by one treating department (`case["department"]`); other departments
may take part (`case["participants"]`: read and comment) and a second cancer of the same patient is a linked Case File (5.3). Reading:
the Vaidyx admin and the MDT Coordinator read every Case File; the doctors of the owning department, of a participating department, of
a department with an open referral to it (5.2) and of the owner of a linked Case File read the whole Case File (scope FULL); the
doctors of a department that received a request (a sent Pre-Authorization request, a Tumour Board action) see only the items they
were asked about (scope REQUESTS: their requests and the records their department produced or the request names); everyone else is
refused. A Case File without an owning department (created by hand before 5.1, the demo Case Files) stays open to every placed account,
as before. Acting: the clinical actions of a treating doctor (confirm, waive, dismiss, upload an outside report, re-fetch, link, send and
close requests, refer, manage the participants, change the listing) belong to the owning department; a department still confirms or
deletes its own upload through its membership (the V1 rule), the coordinator keeps the board and session actions. Every change here
is audited in the Case File. No model calls."""
from datetime import date, timedelta

from . import config, org, store

FULL = "full"          # the whole Case File
REQUESTS = "requests"  # only the items the department was asked about (a supporting department)
SCOPES = (FULL, REQUESTS)
# The clinical actions a treating doctor does on the Case Files its department owns (plan section 4). The other actions keep their
# org.ACTIONS rule (board and session actions for the coordinator, a department's own upload for its doctors, reading for everyone in scope).
OWNER_ACTIONS = frozenset({"waive", "confirm", "dismiss_failed", "upload_to_case", "send_request", "create_request", "close_request",
                           "delete_document", "refer", "manage_participants", "mark_ready"})
RECENT_DAYS = 7  # a department that received a request keeps its limited view this long after the request closed (as its inbox lists it)
REFERRAL_OPEN = "requested"


class AccessError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- what the Case File records -------------------------------------------------------------------------------------------

def owner(case) -> str | None:
    """The owning treating department's id, or None for a Case File without one."""
    d = (case or {}).get("department") if isinstance(case, dict) else None
    return org.department_id(d) if d else None


def participants(case) -> list[str]:
    """The participating departments' ids (read and comment), in the order they joined."""
    out = []
    for p in (case or {}).get("participants") or []:
        did = org.department_id(p.get("department")) if isinstance(p, dict) else org.department_id(p)
        if did and did not in out:
            out.append(did)
    return out


def open_referral(case) -> dict | None:
    """The referral waiting for the receiving department's answer (5.2), or None."""
    for r in reversed((case or {}).get("referrals") or []):
        if isinstance(r, dict) and r.get("status") == REFERRAL_OPEN:
            return r
    return None


def linked_owners(case) -> list[str]:
    """The owning departments of the Case Files linked to this one (the same patient's other cancer, 5.3): the linked Case File's
    current owner (it may have been referred since the link was made), else the department recorded with the link."""
    out = []
    for l in (case or {}).get("linked_cases") or []:
        if not isinstance(l, dict):
            continue
        live = store.get_case(l.get("case_id")) if l.get("case_id") else None
        if not live:  # a link to a Case File that no longer exists gives nobody access (review Phase 5 minor 2)
            continue
        did = owner(live)
        if did and did not in out:
            out.append(did)
    return out


def _action_department(a: dict) -> str | None:
    if a.get("role") == "coordinator":
        return org.COORDINATOR_ID
    for k in ("department_id", "department"):
        did = org.department_id(a.get(k) or "")
        if did:
            return did
    return None


def _received(a: dict, today=None) -> bool:
    """True when the department holds (or recently held) this action: a sent Pre-Authorization request (or a V1 one opened before
    4.2), a Tumour Board action; never a suggestion nobody sent, nor a request closed longer ago than its inbox shows it."""
    status = str(a.get("status") or "")
    if status == "suggested" or (status == "completed" and a.get("never_sent")):
        return False
    if status == "completed":
        done = str(a.get("completed") or "")[:10]
        return bool(done) and done >= ((today or date.today()) - timedelta(days=RECENT_DAYS)).isoformat()
    return True


def asked(case_id: str, state=None, today=None) -> dict:
    """{department id: [actions it received]} for the Case File's actions (Pre-Authorization requests and Tumour Board actions)."""
    st = store.get_state(case_id) if state is None else state
    out: dict[str, list] = {}
    for a in (st or {}).get("actions") or []:
        if not isinstance(a, dict) or a.get("source") not in ("pre_authorization", "board"):
            continue
        did = _action_department(a)
        if did and _received(a, today):
            out.setdefault(did, []).append(a)
    return out


# ---- reading ---------------------------------------------------------------------------------------------------------------

def _mine(r: dict) -> set:
    return set((r or {}).get("departments") or {})


def scope(r: dict, case: dict, state=None) -> str | None:
    """FULL, REQUESTS or None (refused) for the user with roles `r` on this Case File."""
    if not isinstance(r, dict) or r.get("disabled") or not isinstance(case, dict):
        return None
    if r.get("admin"):
        return FULL
    if not r.get("known"):
        return None
    if r.get("coordinator"):
        return FULL
    own = owner(case)
    if not own:  # no owning department recorded (before 5.1, a manual Case File): every placed account, as before
        return FULL
    mine = _mine(r)
    if own in mine or (mine & set(participants(case))) or (mine & set(linked_owners(case))):
        return FULL
    ref = open_referral(case)
    if ref and org.department_id(ref.get("to")) in mine:
        return FULL
    if mine & set(asked(case["case_id"], state)):
        return REQUESTS
    return None


def refusal(r: dict, case: dict) -> str:
    own = owner(case)
    name = org.department_name(own) if own else "another department"
    return (f"This Case File belongs to {name}. Its doctors, the participating departments and the MDT Coordinator can open it; a department "
            "that received a request sees the items it was asked about.")


def visible(r: dict, cases, states=None) -> list:
    """The Case Files the user may open (any scope), each as given."""
    return [c for c in cases or [] if isinstance(c, dict) and scope(r, c, (states or {}).get(c.get("case_id"))) is not None]


def my_actions(r: dict, case_id: str, state=None) -> list:
    """The actions a department-scoped reader may see: those its departments received."""
    mine = _mine(r)
    return [a for did, acts in asked(case_id, state).items() if did in mine for a in acts]


def limited_docs(r: dict, case: dict, docs: list, state=None) -> list:
    """The records a department-scoped reader may open: those its departments produced (uploaded or, from the HIS, reported) and the
    records its requests name."""
    mine = _mine(r)
    named = {a.get("source_doc_id") for a in my_actions(r, case["case_id"], state) if a.get("source_doc_id")}
    out = []
    for d in docs or []:
        dep = org.department_id(d.get("department") or "") if d.get("department") else None
        if (dep and dep in mine) or d.get("doc_id") in named:
            out.append(d)
    return out


def limited_state(r: dict, case: dict, state: dict) -> dict:
    """A department-scoped reader's view of the state: its own actions, nothing of the gate, the board or the artefacts."""
    return {"actions": my_actions(r, case["case_id"], state), "board_records": [], "reviews": [], "artefacts": {}, "gate": None, "confirmations": [],
            "limited": True}


# ---- acting ----------------------------------------------------------------------------------------------------------------

def is_owner_doctor(r: dict, case: dict) -> bool:
    """A doctor of the owning treating department (any role), or the Vaidyx admin; for a Case File without an owner, any treating doctor."""
    if not isinstance(r, dict) or r.get("disabled"):
        return False
    if r.get("admin"):
        return True
    own = owner(case)
    treating = r.get("treating") or {}
    return (own in treating) if own else bool(treating)


def may(r: dict, action: str, case: dict, department: str | None = None) -> bool:
    """org.can() plus the owner rule: on a Case File with an owning department, an OWNER_ACTION is for the owner's treating doctors
    (and the Vaidyx admin); a department-scoped one stays open to a member or head of the department named (its own upload)."""
    if not org.can(r, action, department):
        return False
    if r.get("admin") or action not in OWNER_ACTIONS:
        return True
    own = owner(case)
    if not own:
        return True
    rule = org.ACTIONS.get(action) or {}
    if rule.get("dept") and department and org.can_as_member(r, action, department):
        return True
    return own in (r.get("treating") or {})


def require(r: dict, action: str, case: dict, department: str | None = None) -> None:
    """PermissionError (the route answers 403) unless may()."""
    if may(r, action, case, department):
        return
    if org.can(r, action, department):  # refused by the owner rule alone
        own = owner(case)
        raise PermissionError(f"Only the doctors of {org.department_name(own)}, which owns this Case File, can do '{action}' on it"
                              + (" (your department takes part: read and comment)." if set(participants(case)) & _mine(r) else "."))
    org.require(r, action, department)


def may_remind(r: dict, case: dict) -> bool:
    """Send a reminder about a Case File's requests (V2 item 6.1): the MDT Coordinator on the owner's behalf, the Vaidyx admin, and the
    owning department's doctors (any treating doctor on a Case File without an owner)."""
    if not org.can(r, "remind"):
        return False
    return bool(r.get("admin") or r.get("coordinator")) or is_owner_doctor(r, case)


def may_list(r: dict, case: dict) -> bool:
    """Change the listing (protocol, NCG setting, board date, hospital level): the MDT Coordinator, the Vaidyx admin, and the owning
    department's doctors (the new owner picks the protocol after a referral, 5.2)."""
    return org.can(r, "list_case") or (bool(owner(case)) and is_owner_doctor(r, case))


# ---- the owner and the participants ----------------------------------------------------------------------------------------

def set_owner(case_id: str, department, user: str, reason: str = "", roles: dict | None = None) -> dict:
    """Record the owning treating department of a Case File that has none yet (a manual creation by a treating doctor). Audited."""
    if case_id in config.PROTECTED_CASES:
        raise AccessError("That Case File is protected; its owner is not set here", 409)
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    did = org.department_id(department) if department else None
    if not did:
        raise AccessError(f"Unknown department: {department}")
    if org.department_group(did) != "treating":
        raise AccessError(f"{org.department_name(did)} is a supporting department; a Case File is owned by a treating department")
    if roles is not None and not (roles.get("admin") or roles.get("coordinator") or did in (roles.get("treating") or {})):
        raise AccessError(f"You are not placed in {org.department_name(did)}", 403)
    before = case.get("department")
    case["department"] = did
    case["participants"] = [p for p in case.get("participants") or [] if org.department_id((p or {}).get("department")) != did]
    store.save_case(case)
    store.audit(case_id, {"kind": "owner_set", "by": user, "department": did, "before": before, "reason": reason})
    return case


def add_participant(case_id: str, department, user: str, reason: str = "") -> dict:
    """The owner invites a department to read and comment (treating or supporting). Audited; the department is told."""
    from . import notify
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    did = org.department_id(department) if department else None
    if not did:
        raise AccessError(f"Unknown department: {department}")
    if did == owner(case):
        raise AccessError(f"{org.department_name(did)} owns this Case File", 409)
    if did in participants(case):
        raise AccessError(f"{org.department_name(did)} already takes part", 409)
    rec = {"department": did, "since": store.now_iso(), "by": user, "reason": str(reason or "")[:500]}
    case.setdefault("participants", []).append(rec)
    store.save_case(case)
    store.audit(case_id, {"kind": "participant_added", "by": user, "department": did, "reason": rec["reason"]})
    patient = (case.get("patient") or {}).get("name") or case_id
    try:
        notify.notify({"department": did}, "case_shared", case_id, f"{org.department_name(did)} takes part in the Case File of {patient} ({case_id})",
                      f"{org.department_name(owner(case))} invited your department to read and comment on this Tumour Board Case File."
                      + (f" Reason: {rec['reason']}" if rec["reason"] else ""), by=user)
    except Exception:  # the notice never fails the change
        pass
    return case


def remove_participant(case_id: str, department, user: str, reason: str = "") -> dict:
    case = store.get_case(case_id)
    if not case:
        raise AccessError("Case not found", 404)
    did = org.department_id(department) if department else None
    if not did or did not in participants(case):
        raise AccessError(f"{department} does not take part in this Case File", 404)
    from . import notify
    case["participants"] = [p for p in case.get("participants") or [] if org.department_id((p or {}).get("department")) != did]
    store.save_case(case)
    store.audit(case_id, {"kind": "participant_removed", "by": user, "department": did, "reason": str(reason or "")[:500]})
    patient = (case.get("patient") or {}).get("name") or case_id
    try:  # the department hears that it no longer takes part (review Phase 5 minor 8); the notice never fails the change
        notify.notify({"department": did}, "case_unshared", case_id, f"{org.department_name(did)} no longer takes part in the Case File of {patient} ({case_id})",
                      f"{org.department_name(owner(case)) if owner(case) else 'The owning department'} ended your department's part in this Tumour Board Case File."
                      + (f" Reason: {str(reason or '')[:500]}" if reason else ""), by=user)
    except Exception:
        pass
    return case


def public(case: dict) -> dict:
    """The ownership block of a Case File for the UI."""
    own = owner(case)
    return {"owner": {"id": own, "name": org.department_name(own)} if own else None,
            "participants": [{"id": org.department_id(p.get("department")), "name": org.department_name(org.department_id(p.get("department"))),
                              "since": p.get("since"), "by": p.get("by"), "reason": p.get("reason")} for p in case.get("participants") or [] if isinstance(p, dict)],
            "owner_history": list(case.get("owner_history") or []),
            "linked_cases": [_linked_view(l) for l in case.get("linked_cases") or [] if isinstance(l, dict)]}


def _linked_view(l: dict) -> dict:
    """A linked Case File as the UI shows it: its current protocol and owner when it still exists (a referral may have moved it since
    the link was made), else what the link recorded."""
    live = store.get_case(l.get("case_id")) if l.get("case_id") else None
    if live:
        l = {**l, "protocol": live.get("protocol") or "", "department": owner(live) or l.get("department") or ""}
    return {**l, "exists": bool(live), "department_name": org.department_name(org.department_id(l.get("department"))) if l.get("department") else ""}
