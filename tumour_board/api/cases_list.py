"""GET /case-list (18 Oct 2026, new interface): the one neat list of the Case Files a person may open, with the status word the home shows.

One row per Case File the person may open (access.scope, as GET /cases): the patient, the cancer, the owner, the urgency tag people
set, a status, the board date, how many required records are still open, whether imaging is present, the last change. Status, in this
order: archived; decided (a board record exists for the current listing); scheduled (on the agenda of a planned or running meeting);
ready (the owner marked it ready); waiting_department (a sent request is open); needs_me (the treating team has a step to take:
proposals wait for this consultant, a reading needs a confirmation, no cancer is chosen yet, required records are open and nobody was
asked, or every check is met and the ready mark is the next step); draft (records are still being read, or nothing is checked yet).
For anyone but the owner's consultants and the team's residents the needs_me label reads "Needs the treating team". Archived Case Files
are listed only with status=archived. Filters are simple server-side matches; the client may filter further. Sorted newest first.
Nothing here judges the patient: the words describe the paperwork.

Each row also says why the person sees it (`relation`, night-v3 item 1.3): owner, team, participant, referred, coordinator, linked,
asked, creator (or admin inside a break-glass window). A "linked" row is another department's Case File seen only because it is linked to
one of the person's own (the same patient's other cancer): it carries linked_only, read_only and owned_by, is never "mine", and the
website lists it apart and leaves it out of every count."""

import re
from fastapi import Request

from tumour_board import access, board, org, profiles, proposals, protocol, service, store, team
from tumour_board.api.common import make_router, need, roles

router = make_router()
IMAGING_TYPES = {"ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan"}
PROCESSING_STATES = {"queued", "reading", "identifying", "classifying", "extracting"}
OPEN_REQUEST = {"pending", "overdue"}
STATUS_LABELS = {"needs_me": "Needs you", "waiting_department": "Waiting on a department", "ready": "Ready for the board", "scheduled": "Scheduled",
                 "decided": "Decided", "archived": "Archived", "draft": "Draft"}
STATUSES = ("needs_me", "waiting_department", "ready", "scheduled", "decided", "archived", "draft")
OTHERS_NEED = "Needs the treating team"


def _scheduled() -> dict:
    """{case_id: {meeting_id, date, status}} for the Case Files on the agenda of a planned or running session (the V2 agenda list, or the
    new meetings' agenda lists discussion / noting)."""
    out = {}
    try:
        rows = board.list_sessions()
    except Exception:
        return out
    for row in rows:
        if row.get("status") not in ("planned", "in_session"):
            continue
        s = board.get(row["id"]) or {}
        ids = []
        for agenda in (s.get("agenda"), s.get("agenda_lists")):
            if isinstance(agenda, list):
                ids += [a.get("case_id") if isinstance(a, dict) else a for a in agenda]
            elif isinstance(agenda, dict):
                for key in ("discussion", "noting"):
                    ids += [a.get("case_id") if isinstance(a, dict) else a for a in agenda.get(key) or []]
        for cid in ids:
            if cid and (cid not in out or str(s.get("date") or "") < str(out[cid]["date"] or "")):
                out[cid] = {"meeting_id": s["id"], "date": s.get("date") or "", "status": s.get("status")}
    return out


def _decided(c: dict, st: dict) -> bool:
    """A board record exists for the current listing (recorded after it was listed; any record when the listing has no time)."""
    recs = [x for x in (st.get("board_records") or []) if isinstance(x, dict)]
    if not recs:
        return False
    listed = str((c.get("listing") or {}).get("listed_at") or "")[:19]
    if not listed:
        return True
    return any(str(x.get("recorded_at") or x.get("at") or x.get("created") or x.get("board_date") or "")[:19] >= listed[:10] for x in recs)


def _last_change(case_id: str) -> str:
    d = store.case_dir(case_id)
    best = ""
    p = d / "audit.jsonl"
    if p.exists():
        try:
            with open(p, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                tail = f.read().decode("utf-8", "replace").strip().splitlines()
            import json
            for line in reversed(tail):
                try:
                    best = str(json.loads(line).get("ts") or "")
                    break
                except ValueError:
                    continue
        except OSError:
            pass
    from datetime import datetime
    for name in ("state.json", "case.json"):
        try:
            m = datetime.fromtimestamp((d / name).stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            continue
        if m > best:
            best = m
    return best


def _owner_doctor(c: dict) -> str:
    """The consultant who owns the Case File: its creator when that person is a consultant of the owning department, else the first one."""
    cons = team.owner_consultants(c)
    by = c.get("created_by") or ""
    return by if by in cons else (cons[0] if cons else by)


def status_of(c: dict, st: dict, docs: list, r: dict, sched: dict) -> dict:
    cid = c["case_id"]
    if access.is_archived(c):
        return {"key": "archived", "label": STATUS_LABELS["archived"], "detail": (c.get("archived") or {}).get("reason") or ""}
    if _decided(c, st):
        return {"key": "decided", "label": STATUS_LABELS["decided"], "detail": "a board record exists"}
    if cid in sched:
        s = sched[cid]
        return {"key": "scheduled", "label": f"Scheduled {s['date']}", "detail": "in session" if s["status"] == "in_session" else "on the agenda", "meeting_id": s["meeting_id"]}
    if isinstance(c.get("board_ready"), dict) and c["board_ready"].get("at"):
        return {"key": "ready", "label": STATUS_LABELS["ready"], "detail": f"marked by {profiles.display_name(c['board_ready'].get('by') or '')}"}
    acts = [a for a in st.get("actions") or [] if isinstance(a, dict) and a.get("source") == "pre_authorization"]
    open_ = [a for a in acts if a.get("status") in OPEN_REQUEST]
    if open_:
        depts = []
        for a in open_:
            name = a.get("department") or org.COORDINATOR_NAME
            if name not in depts:
                depts.append(name)
        return {"key": "waiting_department", "label": "Waiting on " + ", ".join(depts[:2]) + (" and others" if len(depts) > 2 else ""), "detail": f"{len(open_)} open request(s)"}
    gate = st.get("gate") or {}
    consultant = access.is_owner_consultant(r, c)
    mine = consultant or access.is_team_resident(r, c)  # the resident fills everything in, so "Needs you" is its word too

    def needs(detail):
        return {"key": "needs_me", "label": STATUS_LABELS["needs_me"] if mine else OTHERS_NEED, "detail": detail}

    pend = [p for p in proposals.list_(c) if p.get("status") == proposals.PENDING]
    needs_conf = [q for q in gate.get("requirements") or [] if isinstance(q, dict) and q.get("status") == "needs_confirmation"]
    if (pend and consultant) or needs_conf:
        return needs("; ".join(x for x in ((f"{len(pend)} proposal(s) to sign off" if pend and consultant else ""),
                                           (f"{len(needs_conf)} confirmation(s) needed" if needs_conf else "")) if x))
    reading = sum(1 for d in docs if d.get("state") in PROCESSING_STATES)
    if reading:
        return {"key": "draft", "label": STATUS_LABELS["draft"], "detail": f"{reading} record(s) being read"}
    if not c.get("protocol"):
        return needs("no cancer chosen yet")
    if gate.get("passed") is not None:  # the one count of what is left (steps.open_count, 21 Oct), so the row never says "ready" beside "7 left"
        n = _left_of(cid, gate)
        if n:
            return needs(f"{n} left before the board" + (", nobody asked yet" if gate.get("passed") is False else ""))
        return needs("everything is settled: send it to the board")
    return {"key": "draft", "label": STATUS_LABELS["draft"], "detail": "records not checked yet"}


def _left_of(cid, gate) -> int:
    """The one count of what is left before the board (steps.open_count, 21 Oct); the gate's open records only when that cannot be built."""
    from tumour_board import steps
    n = steps.open_count(cid)
    if n is not None:
        return n
    return sum(1 for q in gate.get("requirements") or [] if isinstance(q, dict) and q.get("status") not in ("satisfied", "not_applicable", "waived"))


MINE_RELATIONS = ("owner", "team", "creator")


def relation(r: dict, c: dict) -> str | None:
    """Why this person sees this Case File, the strongest reason first (the same paths as access.scope): "owner" (a consultant of the
    owning department), "team" (a resident or member of its team, or a resident of the owning department), "creator" (no owner yet, it
    made it), "participant", "referred" (an open referral to its department), "coordinator", "linked" (only through a linked Case File of
    its own department), "asked" (requests only), "admin" (a break-glass window or single-user mode); None when it may not open it."""
    sc = access.scope(r, c)
    if sc is None:
        return None
    if access.is_protected(c) or r.get("admin"):
        return "creator" if access.is_creator(r, c) else "admin"
    own = access.owner(c)
    cons = set(r.get("departments") or {}) - set(r.get("resident") or {})  # consultant placements, as access.scope reads them
    if own and own in cons:
        return "owner"
    if access.is_team_resident(r, c) or access.is_team_member(r, c):
        return "team"
    if not own:
        return "creator" if access.is_creator(r, c) else "coordinator"
    if cons & set(access.participants(c)):
        return "participant"
    ref = access.open_referral(c)
    if ref and org.department_id(ref.get("to")) in cons:
        return "referred"
    if r.get("coordinator"):
        return "coordinator"
    if cons & set(access.linked_owners(c)):
        return "linked"
    return "asked" if sc == access.REQUESTS else "coordinator"


def row(c: dict, r: dict, sched: dict, labels: dict) -> dict:
    cid = c["case_id"]
    st = store.get_state(cid) or {}
    docs = store.list_docs(cid)
    gate = st.get("gate") or {}
    own = access.owner(c)
    doc_owner = _owner_doctor(c)
    status = status_of(c, st, docs, r, sched)
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    sc = sched.get(cid)
    rel = relation(r, c)
    mine = rel in MINE_RELATIONS or bool(own and own in (r.get("resident") or {}) and rel != "linked") or bool(rel != "linked" and c.get("created_by") == r.get("user"))  # as before, its creator too; never a linked row
    extra = {"linked_only": True, "read_only": True, "owned_by": {"department": own, "label": org.department_name(own)}} if rel == "linked" else {}
    scope = access.scope(r, c)
    clinical = _clinical_text(c, st) if scope == access.FULL else {"summary_line": "", "decision_text": ""}  # never to a department only asked
    return {"case_id": cid, "patient": {"name": p.get("name") or "", "agesex": p.get("agesex") or "", "uhid": p.get("mrn") or ""},
            "protocol": c.get("protocol") or "", "setting": c.get("setting") or "",
            # a cancer with no checklist yet (generic rule, R05-Q04) reads "<cancer name> (no checklist yet)"; the name is kept as typed
            "protocol_label": protocol.case_label(c, labels.get(c.get("protocol") or "", c.get("protocol") or "")), "cancer_name": c.get("cancer_name") or "",
            "owner": {"department": own or "", "department_label": org.department_name(own) if own else "", "doctor": doc_owner, "doctor_name": profiles.display_name(doc_owner) if doc_owner else ""},
            "urgency": team.urgency_view(c), "status": status, "board_date": (sc or {}).get("date") or c.get("board_date") or "", "meeting_id": (sc or {}).get("meeting_id"),
            "left_before_board": _left_of(cid, gate),
            "gate_passed": gate.get("passed"), "readiness": gate.get("readiness"),
            "imaging_present": any(((d.get("classification") or {}).get("doc_type") in IMAGING_TYPES) and d.get("state") == "ready" and not d.get("dismissed") for d in docs),
            "ids": _identifiers(c), "accessions": _accessions(docs),
            "documents": len(docs), "last_change": _last_change(cid), "created": c.get("created") or "", "created_by": c.get("created_by") or "",
            "residents_count": len(access.team_residents(c)), "scope": scope, "archived": access.is_archived(c),
            "relation": rel, "mine": mine, **clinical, **extra}


def _clinical_text(c: dict, st: dict) -> dict:
    """The summary line (night-v3 item 3.4) and the latest board record's decision text (at most 200 characters), for FULL readers only."""
    line = c.get("summary_line")
    text = str(line.get("text") or "") if isinstance(line, dict) else ""
    recs = [b for b in (st or {}).get("board_records") or [] if isinstance(b, dict)]
    recs.sort(key=lambda b: (str(b.get("board_date") or b.get("recorded_at") or "")[:10], str(b.get("recorded_at") or "")))
    dec = " ".join(str((recs[-1] if recs else {}).get("decision_text") or "").split())
    return {"summary_line": text, "decision_text": dec[:200]}


def _compact(s: str) -> str:
    """Letters and digits only, lower case: "VXH/26/004327" -> "vxh26004327"."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _loose(s: str) -> str:
    """_compact() of the text with the leading zeros of every digit run dropped first: "VXH/26/004327" -> "vxh264327", so "4327" and
    "VXH/26/4327" match too (the zeros go before the separators do, else "26/004327" would read as one run)."""
    return _compact(re.sub(r"(?<![0-9])0+(?=[0-9])", "", s or ""))


def _dmy(iso: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def _match(x: dict, q: str) -> bool:
    """The same matching as the website (web/tb-nik/src/lib/search.ts): case-insensitive, every typed word found somewhere, and an
    identifier found by any part of it with the separators ignored ("00764", "vdx", "VDX/2026/00764", "vdx 764" all find
    VDX/2026/00764; the owner, 19 Oct 2026)."""
    ids = [x["patient"]["uhid"], *x.get("ids", []), *x.get("accessions", []), x["case_id"]]
    parts = [x["patient"]["name"], x["patient"].get("agesex"), *ids, x["protocol_label"], x.get("cancer_name"), (x.get("setting") or "").replace("_", " "),
             x["owner"]["doctor_name"], x["owner"]["department_label"], (x.get("status") or {}).get("label"), _dmy(x.get("board_date") or ""),
             x.get("summary_line"), x.get("decision_text")]  # both "" unless the reader has the whole Case File (item 3.4)
    words = " ".join(str(v) for v in parts if v).lower()
    id_text = " ".join(str(v) for v in ids if v)
    comp, loose = _compact(id_text), _loose(id_text)
    for t in q.lower().split():
        tc, tl = _compact(t), _loose(t)
        if t in words or (tc and tc in comp) or (tl and tl in loose):
            continue
        return False
    return True


def _identifiers(c: dict) -> list:
    """Every identifier the file carries, in order: the UHID / MRN, the patient's other ids from the hospital system (ABHA, PM-JAY,
    IP / OP numbers) and the IP / OP numbers of the fetched encounters."""
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    out = []
    for v in [p.get("mrn"), *[i.get("value") for i in (p.get("ids") or []) if isinstance(i, dict)],
              *[e.get("number") for e in ((c.get("his") or {}).get("encounters") or []) if isinstance(e, dict)]]:
        v = str(v or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def _accessions(docs: list) -> list:
    out = []
    for d in docs:
        v = str(((d.get("his") or {}) if isinstance(d.get("his"), dict) else {}).get("accession") or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def _csv(value: str) -> list:
    return [s.strip() for s in (value or "").split(",") if s.strip()]


@router.get("/case-list")
async def case_list(request: Request, q: str = "", urgency: str = "", status: str = "", department: str = "", organ: str = "", owner: str = "",
                    board_from: str = "", board_to: str = "", imaging: str = "", mine: str = ""):
    r = roles(request)
    need(r, "read_case")
    labels = {p["id"]: p.get("label") or p["id"] for p in protocol.list_protocols()}
    sched = _scheduled()
    rows = []
    for c in store.list_cases():  # the same visibility as GET /cases (access.scope)
        if access.scope(r, c) in (None, access.READ):  # a Case File opened with a reason is never listed among the person's own (item 1.9)
            continue
        rows.append(row(c, r, sched, labels))
    filters = {"departments": sorted({(x["owner"]["department"], x["owner"]["department_label"]) for x in rows if x["owner"]["department"]}),
               "organs": sorted({(x["protocol"], labels.get(x["protocol"], x["protocol"])) for x in rows if x["protocol"]}),  # one entry per checklist (all generic Case Files together)
               "owners": sorted({(x["owner"]["doctor"], x["owner"]["doctor_name"]) for x in rows if x["owner"]["doctor"]}),
               "statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in STATUSES]}
    filters = {k: ([{"id": a, "label": b} for a, b in v] if k != "statuses" else v) for k, v in filters.items()}
    want_status = [s.strip() for s in status.split(",") if s.strip()]
    if "archived" not in want_status:
        rows = [x for x in rows if not x["archived"]]
    if want_status:
        rows = [x for x in rows if x["status"]["key"] in want_status]
    if q.strip():
        rows = [x for x in rows if _match(x, q.strip())]
    if urgency.strip():
        levels = {int(u) for u in urgency.replace(" ", "").split(",") if u.isdigit()}
        rows = [x for x in rows if (x["urgency"] or {}).get("level") in levels]
    if department.strip():  # comma-separated lists on department, organ and owner (the filter panel ticks several)
        dids = {org.department_id(d) or d for d in _csv(department)}
        rows = [x for x in rows if x["owner"]["department"] in dids]
    if organ.strip():
        organs = set(_csv(organ))
        rows = [x for x in rows if x["protocol"] in organs]
    if owner.strip():
        owners = {o.lower() for o in _csv(owner)}
        rows = [x for x in rows if x["owner"]["doctor"] in owners]
    if board_from.strip():
        rows = [x for x in rows if x["board_date"] and x["board_date"][:10] >= board_from.strip()[:10]]
    if board_to.strip():
        rows = [x for x in rows if x["board_date"] and x["board_date"][:10] <= board_to.strip()[:10]]
    if imaging.strip().lower() in ("1", "true", "yes"):
        rows = [x for x in rows if x["imaging_present"]]
    if mine.strip().lower() in ("1", "true", "yes"):
        rows = [x for x in rows if x["mine"]]
    rows.sort(key=lambda x: (str(x.get("created") or ""), x["case_id"]), reverse=True)
    try:
        demo = service.list_demo()
    except Exception:
        demo = []
    linked = sum(1 for x in rows if x.get("linked_only"))  # another department's linked Case Files: listed, never counted as the person's own
    return {"cases": rows, "filters": filters, "total": len(rows) - linked, "linked": linked, "demo": demo, "can_create": org.can(r, "create_case")}
