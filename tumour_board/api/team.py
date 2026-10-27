"""Routes for the Case File team, urgency, proposals, archive, consent and break-glass (18 Oct 2026, new interface; SPEC-API team.py).

The logic lives in team.py and proposals.py; this module checks who is asking (api.common), locks the Case File while it changes, turns
the modules' errors into plain JSON and keeps the paths of the contract (POST /case-join rather than /cases/join, so the Case File
guard does not take "join" for a Case File id)."""
from fastapi import Request

from tumour_board import access, case_summary, org, proposals, store, team
from tumour_board.api.common import RateLimit, body, case, fail, make_router, need_case, need_known, roles

router = make_router()
JOIN_LIMIT = RateLimit(5, 15 * 60)
ASK_LIMIT = RateLimit(5, 15 * 60)  # "Ask to join" (night-v3 item 1.1): the same pace as the join code
OPEN_LIMIT = RateLimit(10, 60 * 60)  # a doctor's "Open with a reason" (item 1.9): ten openings an hour per login (review, 27 Oct)


def _err(e):
    fail(getattr(e, "status", 400), str(e), getattr(e, "code", "") or "")


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (team.TeamError, proposals.ProposalError, access.AccessError) as e:
        _err(e)
    except PermissionError as e:
        fail(403, str(e), "forbidden")
    except ValueError as e:
        fail(400, str(e), "bad_value")


# ---- urgency --------------------------------------------------------------------------------------------------------------------

@router.put("/cases/{case_id}/urgency")
async def put_urgency(case_id: str, request: Request):
    """{level 1..5, note?}: the owner's consultant sets the tag; a resident's call becomes a proposal ({proposal}). People only."""
    r = roles(request); c = case(case_id); b = await body(request)
    level, note = b.get("level"), str(b.get("note") or "")
    async with store.lock(case_id):
        if access.may(r, "set_urgency", c):
            return {"urgency": _run(team.set_urgency, case_id, level, r["user"], note)}
        if access.may(r, "propose", c):
            return {"proposal": _run(proposals.propose, case_id, "urgency", {"level": level, "note": note}, note, r["user"], r), "urgency": team.urgency_view(c)}
    need_case(r, "set_urgency", c)


# ---- the team -------------------------------------------------------------------------------------------------------------------

@router.get("/cases/{case_id}/team")
async def get_team(case_id: str, request: Request):
    r = roles(request); c = case(case_id)
    manage = access.may(r, "manage_team", c)
    out = team.view(c, show_code=manage)
    out["can"] = {"manage": manage, "leave": team.on_team(c, r["user"]), "set_urgency": access.may(r, "set_urgency", c), "propose": access.may(r, "propose", c),
                  "archive": _may_archive(r, c), "consent": access.may(r, "set_consent", c)}
    out["urgency"] = team.urgency_view(c)
    return out


@router.post("/cases/{case_id}/team/code")
async def new_code(case_id: str, request: Request):
    r = roles(request); c = case(case_id); need_case(r, "manage_team", c)
    async with store.lock(case_id):
        return _run(team.new_code, case_id, r["user"])


@router.delete("/cases/{case_id}/team/code")
async def delete_code(case_id: str, request: Request):
    r = roles(request); c = case(case_id); need_case(r, "manage_team", c)
    async with store.lock(case_id):
        return {"ok": True, "removed": _run(team.clear_code, case_id, r["user"])}


@router.post("/case-join")
async def join(request: Request):
    """{code}: a resident joins a Case File team. 5 tries per 15 minutes per login; a wrong code is a 404 no_such_code."""
    r = roles(request); need_known(r)
    JOIN_LIMIT.check(r["user"], "Too many join attempts. Wait 15 minutes, or ask the treating doctor for the code again.")
    b = await body(request)
    return _run(team.join, str(b.get("code") or ""), r, r["user"])


@router.post("/case-join/ask")
async def ask_to_join(request: Request):
    """{case_id, note?}: "Ask to join" without a code (night-v3 item 1.1). A placed doctor (consultant or resident of any department)
    who cannot open the Case File asks its owner; the owner's consultants are told and approve or reject it in the Team panel. Under
    /case-join so the Case File guard does not refuse a person who cannot open it yet. 5 requests per 15 minutes per login."""
    r = roles(request); need_known(r)
    ASK_LIMIT.check(r["user"], "Too many requests to join. Wait 15 minutes and try again.")
    b = await body(request)
    try:
        cid = store.safe_id(str(b.get("case_id") or "").strip())
    except ValueError:
        fail(400, "Give the Case File id.", "bad_case")
    if not cid:
        fail(400, "Give the Case File id.", "bad_case")
    async with store.lock(cid):
        return _run(team.ask_to_join, cid, r, r["user"], str(b.get("note") or ""))


@router.post("/cases/{case_id}/team/pending/{user}/approve")
async def approve_join(case_id: str, user: str, request: Request):
    r = roles(request); c = case(case_id); need_case(r, "manage_team", c)
    b = await body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        rec = _run(team.approve_pending, case_id, user.strip().lower(), r["user"], str(b.get("note") or ""))
    return {"resident" if "since" in rec else "member": rec, "team": team.view(store.get_case(case_id), show_code=True)}


@router.post("/cases/{case_id}/team/pending/{user}/reject")
async def reject_join(case_id: str, user: str, request: Request):
    r = roles(request); c = case(case_id); need_case(r, "manage_team", c)
    b = await body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        _run(team.reject_pending, case_id, user.strip().lower(), r["user"], str(b.get("note") or ""))
    return {"ok": True, "team": team.view(store.get_case(case_id), show_code=True)}


@router.post("/cases/{case_id}/team/residents")
async def add_resident(case_id: str, request: Request):
    """{user, end_date?}: the owner adds a resident by login without a code (the New Case File stepper)."""
    r = roles(request); c = case(case_id); need_case(r, "manage_team", c); b = await body(request)
    async with store.lock(case_id):
        rec = _run(team.add_resident, case_id, str(b.get("user") or "").strip().lower(), r["user"], str(b.get("end_date") or ""))
    return {"resident": rec, "team": team.view(store.get_case(case_id), show_code=True)}


@router.delete("/cases/{case_id}/team/residents/{user}")
async def remove_resident(case_id: str, user: str, request: Request):
    """The owner's consultant, a department admin of the resident's department, or the resident itself."""
    r = roles(request); c = case(case_id)
    u = user.strip().lower()
    entry = next((x for x in access.team_residents(c) if x.get("user") == u), None)
    dept = (entry or {}).get("department") or next(iter(org.roles(u).get("resident") or {}), "")
    allowed = access.may(r, "manage_team", c) or (u == r["user"] and team.on_team(c, u)) or (dept and org.can(r, "manage_department", dept))
    if not allowed:
        fail(403, "Only the treating consultant, the resident's department admin or the resident itself removes a resident from the team.", "forbidden")
    reason = request.query_params.get("reason", "")
    async with store.lock(case_id):
        _run(team.remove_resident, case_id, u, r["user"], reason)
    return {"ok": True, "team": team.view(store.get_case(case_id), show_code=access.may(r, "manage_team", c))}


# ---- proposals ------------------------------------------------------------------------------------------------------------------

@router.post("/cases/{case_id}/proposals")
async def propose(case_id: str, request: Request):
    """{action, payload, note?}: a resident asks the consultant to sign off (proposals.ACTIONS)."""
    r = roles(request); c = case(case_id); b = await body(request)
    async with store.lock(case_id):
        p = _run(proposals.propose, case_id, str(b.get("action") or ""), b.get("payload") or {}, str(b.get("note") or ""), r["user"], r)
    return {"proposal": p}


@router.get("/cases/{case_id}/proposals")
async def list_proposals(case_id: str, request: Request):
    r = roles(request); c = case(case_id)
    return {"proposals": [proposals.view(p) for p in proposals.list_(c)], "can_approve": access.may(r, "approve_proposal", c), "can_propose": access.may(r, "propose", c),
            "actions": [{"id": a, "label": proposals.LABELS[a], "executor": a in proposals.PROPOSAL_EXECUTORS} for a in proposals.ACTIONS]}


@router.post("/cases/{case_id}/proposals/{pid}/approve")
async def approve_proposal(case_id: str, pid: str, request: Request):
    """{note?}: runs the action in the consultant's name and returns {proposal, result}."""
    r = roles(request); c = case(case_id)
    b = await body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        p, result = _run(proposals.approve, case_id, pid, r["user"], r, str(b.get("note") or ""))
    return {"proposal": p, "result": result}


@router.post("/cases/{case_id}/proposals/{pid}/return")
async def return_proposal(case_id: str, pid: str, request: Request):
    r = roles(request); c = case(case_id); b = await body(request)
    async with store.lock(case_id):
        p = _run(proposals.return_, case_id, pid, r["user"], r, str(b.get("note") or ""))
    return {"proposal": p}


@router.get("/waiting")
async def waiting(request: Request):
    """What waits for this person: a consultant's sign-offs, join requests and confirmations; a resident's own proposals."""
    r = roles(request); need_known(r)
    items = proposals.waiting_for(r) if r.get("treating") else []
    mine = proposals.mine(r) if r.get("resident") else []
    return {"items": items, "mine": mine}


# ---- archive and consent --------------------------------------------------------------------------------------------------------

def _may_archive(r: dict, c: dict) -> bool:
    if not org.can(r, "archive"):
        return False
    if r.get("admin"):
        return not r.get("vaidyx_admin") and access.may(r, "view", c) and access.scope(r, c) is not None  # break-glass is read only (review #6)
    return access.is_owner_consultant(r, c) or bool(r.get("coordinator"))


@router.post("/cases/{case_id}/archive")
async def archive(case_id: str, request: Request):
    """{reason}: the owner's consultant, or the MDT Coordinator with a reason. Archived instead of deleted; every change is then refused."""
    r = roles(request); c = case(case_id)
    if not _may_archive(r, c):
        fail(403, "Only the owning department's consultants or the MDT Coordinator archive a Case File.", "forbidden")
    b = await body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        c = _run(team.archive, case_id, r["user"], str(b.get("reason") or ""))
    return {"case": case_summary.case_for(c, access.scope(r, c)), "archived": c.get("archived")}


@router.post("/cases/{case_id}/unarchive")
async def unarchive(case_id: str, request: Request):
    r = roles(request); c = case(case_id)
    if not _may_archive(r, c):
        fail(403, "Only the owning department's consultants or the MDT Coordinator take a Case File out of the archive.", "forbidden")
    b = await body(request) if (await request.body()) else {}
    async with store.lock(case_id):
        c = _run(team.unarchive, case_id, r["user"], str(b.get("note") or ""))
    return {"case": case_summary.case_for(c, access.scope(r, c)), "archived": None}


@router.put("/cases/{case_id}/consent")
async def put_consent(case_id: str, request: Request):
    """{outside_discussion: bool, note?}: recorded by the owner's consultant; without it an outside expert sees initials, age and sex only."""
    r = roles(request); c = case(case_id); need_case(r, "set_consent", c); b = await body(request)
    async with store.lock(case_id):
        rec = _run(team.set_consent, case_id, r["user"], b.get("outside_discussion"), str(b.get("note") or ""))
    return {"consent": rec}


# ---- break-glass ----------------------------------------------------------------------------------------------------------------

@router.post("/break-glass")
async def break_glass(request: Request):
    """{case_id, reason, hours?}: a Vaidyx admin opens one Case File for a while; the owner is told; audited. {case_id, reason, via?}: a
    doctor without access opens one Case File read-only for 24 hours with a reason (owner decision D8, night-v3 item 1.9); the owner's
    consultants are told; audited. 404 for an unknown or protected Case File, 409 `can_open`, 403 `not_placed`."""
    r = roles(request)
    if not r.get("vaidyx_admin") and not access.placed_doctor(r) and not r.get("coordinator"):
        fail(403, "Only a doctor placed in a department (a consultant or a resident) opens a Case File with a reason.", "not_placed")
    b = await body(request)
    cid = str(b.get("case_id") or "").strip()
    try:
        cid = store.safe_id(cid)
    except ValueError:
        fail(400, "Give the Case File id.", "bad_case")
    if r.get("vaidyx_admin"):
        case(cid)
        w = _run(team.break_glass, r["user"], cid, str(b.get("reason") or ""), b.get("hours"))
        return {"until": w["until"], "case_id": cid, "reason": w["reason"]}
    OPEN_LIMIT.check(r["user"], "Too many Case Files opened with a reason. Wait an hour and try again.")
    w = _run(team.break_glass_doctor, r["user"], r, cid, str(b.get("reason") or ""), str(b.get("via") or ""))
    return {"until": w["until"], "case_id": cid, "reason": w["reason"], "via": w["via"], "renewed": w["renewed"], "scope": access.READ}


@router.get("/break-glass")
async def break_glass_windows(request: Request):
    r = roles(request)
    if not (r.get("vaidyx_admin") or r.get("root_admin") or r.get("auditor")):
        fail(403, "Only an admin or the auditor sees the break-glass windows.", "forbidden")
    return {"windows": access.break_glass_windows(), "mine": access.break_glass_window(r["user"]) if r.get("vaidyx_admin") else None}


@router.delete("/break-glass")
async def close_break_glass(request: Request):
    """The Vaidyx admin closes its window; a doctor closes its own window on one Case File ({case_id}, audited)."""
    r = roles(request)
    if r.get("vaidyx_admin"):
        return {"closed": access.close_break_glass(r["user"], by=r["user"])}
    if not access.placed_doctor(r):
        fail(403, "Only the Vaidyx admin or a placed doctor closes a break-glass window.", "forbidden")
    b = await body(request) if (await request.body()) else {}
    cid = str(b.get("case_id") or "").strip()
    try:
        cid = store.safe_id(cid)
    except ValueError:
        fail(400, "Give the Case File id.", "bad_case")
    return {"closed": _run(team.close_break_glass_doctor, r["user"], cid)}
