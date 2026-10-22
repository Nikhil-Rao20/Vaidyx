"""A home per role (V2 item 7.1): what each person sees first after logging in, built from the roles in org.json (plan section 4).

  Treating doctor    its department's Case Files (owned, participating, asked about), Create from UHID, requests to its department,
                     referrals to answer or waiting, notifications
  Supporting doctor  its inbox: the requests to its department (open, overdue), acknowledge and "done" from the home
  MDT Coordinator    the sessions, the readiness of the next board date and the chase list, the Case Files marked ready
  Department admin   its doctors (placed, heads, disabled, without a Vaidyx login)
  Root admin         the organisation and its settings; the first set-up question (hospital name, NCG level, PM-JAY empanelled) until
                     it is answered once (plan section 11: default yes, asked at first set-up)
  Resident           (18 Oct) the Case Files it is on (its department's and the ones it joined), with its proposals waiting for the
                     consultant ("waiting for Dr X") and the ones returned

From 18 Oct every home also carries "waiting_for_me" (a consultant's residents' proposals, join requests and records needing a
confirmation, proposals.waiting_for; for a resident, its proposals returned with a note) and each Case File row its urgency tag (set
by people, team.urgency_view).

One login may hold several roles (a department admin who is also a doctor): its home stacks the sections, the clinical one first.
A Vaidyx admin (everything) sees every Case File, the coordinator's view and the organisation. An account placed nowhere sees no
section (the UI explains). Everything here is read from the store; nothing is decided or computed about the patient. The server
decides every permission on the routes behind the home (org.can, access.scope); the home only sums up what the user may open."""
from datetime import date

from . import access, accounts, board, his_client, metrics, notify, org, proposals, referral, store, team

SECTIONS = ("treating", "resident", "supporting", "coordinator", "dept_admin", "root_admin")
ADMIN_SECTIONS = ("treating", "coordinator", "root_admin")  # a Vaidyx admin: every Case File, the board, the organisation
MAX_CASES = 60
MAX_REQUESTS = 12
MAX_NOTIFICATIONS = 8
MAX_SESSIONS = 8
MAX_DOCTORS = 12


def sections_for(r: dict) -> list[str]:
    """The home sections a login holds, in display order (the clinical ones first). A disabled login has none."""
    if not isinstance(r, dict) or r.get("disabled"):
        return []
    if r.get("admin"):
        return list(ADMIN_SECTIONS)
    out = []
    if r.get("treating"):
        out.append("treating")
    if r.get("resident"):
        out.append("resident")
    if r.get("supporting"):
        out.append("supporting")
    if r.get("coordinator"):
        out.append("coordinator")
    if r.get("admin_of"):
        out.append("dept_admin")
    if r.get("root_admin"):
        out.append("root_admin")
    return out


def _patient(c: dict) -> dict:
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    return {"name": p.get("name", ""), "mrn": p.get("mrn", ""), "agesex": p.get("agesex", "")}


def _today() -> str:
    return date.today().isoformat()


# ---- treating doctor ------------------------------------------------------------------------------------------------------------

def _case_row(c: dict, r: dict, mine: set) -> dict:
    own = access.owner(c)
    sc = access.scope(r, c)
    parts = set(access.participants(c))
    linked = set(access.linked_owners(c))
    ref = access.open_referral(c)
    ready = c.get("board_ready") if isinstance(c.get("board_ready"), dict) else None
    h = c.get("his") if isinstance(c.get("his"), dict) else {}
    relation = ("owner" if own and own in mine else "participant" if mine & (parts | linked) else "referred" if ref and org.department_id(ref.get("to")) in mine
                else "asked" if sc == access.REQUESTS else "open" if not own else "all")  # "all": a Vaidyx admin or the coordinator on another department's Case File
    return {"case_id": c.get("case_id"), "patient": _patient(c), "uhid": h.get("uhid") or _patient(c)["mrn"], "protocol": c.get("protocol") or "",
            "board_date": c.get("board_date") or "", "listing": (c.get("listing") or {}).get("status"), "documents": c.get("documents", 0),
            "open_actions": c.get("open_actions", 0), "readiness": c.get("readiness"), "gate_passed": c.get("gate_passed"),
            "owner": own, "owner_name": org.department_name(own) if own else "", "relation": relation, "scope": sc,
            "ready": {"by": ready.get("by", ""), "at": ready.get("at", ""), "note": ready.get("note", "")} if ready else None,
            "referral": org.department_name(ref.get("to")) if ref else "", "linked": len(c.get("linked_cases") or []), "created": c.get("created") or "",
            "urgency": team.urgency_view(c), "archived": access.is_archived(c)}  # 18 Oct: the urgency tag people set; archived Case Files stay listed, greyed


def _date_key(board_date: str, today: str) -> tuple:
    """Upcoming boards first (nearest first), then past ones (latest first), then Case Files without a board date (review Phase 7 M3)."""
    bd = (board_date or "")[:10]
    try:
        n = int(bd.replace("-", "")) if bd else 0
    except ValueError:
        n = 0
    if not n:
        return (2, 0)
    return (0, n) if bd >= today else (1, -n)


def treating(r: dict, cases: list | None = None) -> dict:
    """The Case Files the user may open, the owned ones first; counts; the requests to its treating departments; its referrals."""
    mine = set(r.get("treating") or {}) if not r.get("admin") else set()
    today = _today()
    rows = []
    for c in (cases if cases is not None else store.list_cases()):
        if access.scope(r, c):
            row = _case_row(c, r, mine)
            if row["relation"] == "owner" or (r.get("admin") and row["relation"] != "asked"):
                row["suggested_unsent"] = int(c.get("suggested_actions") or 0)  # requests nobody sent yet (counted by store.list_cases)
            rows.append(row)
    order = {"owner": 0, "referred": 1, "participant": 2, "open": 3, "all": 4, "asked": 5}
    rows.sort(key=lambda x: (order.get(x["relation"], 9), _date_key(x["board_date"], today), x["case_id"]))
    owned = [x for x in rows if "suggested_unsent" in x]
    counts = {"visible": len(rows), "mine": sum(1 for x in rows if x["relation"] == "owner"), "participating": sum(1 for x in rows if x["relation"] in ("participant", "referred")),
              "asked": sum(1 for x in rows if x["relation"] == "asked"), "awaiting_listing": sum(1 for x in owned if x["listing"] == "awaiting_listing"),
              "gate_passed": sum(1 for x in owned if x["gate_passed"] is True), "ready_marked": sum(1 for x in owned if x["ready"]),
              "referral_waiting": sum(1 for x in owned if x["referral"]), "suggested_unsent": sum(x.get("suggested_unsent", 0) for x in owned)}
    refs = referral.inbox(r)
    ib = notify.inbox(r)
    depts = [{"id": d["id"], "name": d["name"], "open": d["open"], "overdue": d["overdue"]} for d in ib["departments"] if d.get("group") == "treating"]
    return {"departments": [{"id": d["id"], "name": d["name"], "role": d.get("role")} for d in org.my_departments(r) if d.get("group") == "treating"],
            "cases": rows[:MAX_CASES], "cases_more": max(0, len(rows) - MAX_CASES), "counts": counts, "referrals": refs[:MAX_REQUESTS], "referrals_to_answer": sum(1 for x in refs if x.get("can_answer")),
            "inbox": {"departments": depts, "open": sum(d["open"] for d in depts), "overdue": sum(d["overdue"] for d in depts)},
            "can_create": org.can(r, "create_case"), "his_enabled": bool(his_client.settings().get("enabled"))}


# ---- resident (18 Oct) -----------------------------------------------------------------------------------------------------------

def resident(r: dict, cases: list | None = None) -> dict:
    """The Case Files the resident is on (its department's and the ones it joined by code), its proposals waiting for the consultant
    or returned, and the join requests still pending."""
    today = _today()
    rows = []
    pending = []
    u = r.get("user")
    for c in (cases if cases is not None else store.list_cases()):
        if access.is_team_resident(r, c) and access.scope(r, c) == access.FULL:
            row = _case_row(c, r, set(r.get("resident") or {}))
            row["relation"] = "team"
            rows.append(row)
        elif any(x.get("user") == u for x in ((c.get("team") or {}).get("pending") or []) if isinstance(x, dict)):
            pending.append({"case_id": c["case_id"], "patient": _patient(c), "owner_name": org.department_name(access.owner(c)) if access.owner(c) else ""})
    rows.sort(key=lambda x: (_date_key(x["board_date"], today), x["case_id"]))
    waiting = proposals.mine(r, cases)
    return {"departments": [{"id": d, "name": org.department_name(d)} for d in (r.get("resident") or {})], "end_date": r.get("end_date") or "",
            "cases": rows[:MAX_CASES], "cases_more": max(0, len(rows) - MAX_CASES), "waiting": waiting[:MAX_REQUESTS],
            "counts": {"cases": len(rows), "waiting": sum(1 for w in waiting if w.get("status") == proposals.PENDING),
                       "returned": sum(1 for w in waiting if w.get("status") == proposals.RETURNED), "pending_joins": len(pending)},
            "pending_joins": pending, "can_join": True}


# ---- supporting doctor ----------------------------------------------------------------------------------------------------------

def supporting(r: dict) -> dict:
    """The requests to the user's supporting departments (open first), as the department inbox lists them."""
    ib = notify.inbox(r)
    out = []
    for d in ib["departments"]:
        if d.get("group") != "supporting":
            continue
        reqs = sorted(d["requests"], key=lambda q: (q.get("status") == "completed", not q.get("overdue"), str(q.get("due") or "9999")))
        out.append({"id": d["id"], "name": d["name"], "open": d["open"], "overdue": d["overdue"], "requests": reqs[:MAX_REQUESTS], "more": max(0, len(reqs) - MAX_REQUESTS),
                    "acknowledged": sum(1 for q in d["requests"] if q.get("status") != "completed" and q.get("acknowledged")),
                    "done": sum(1 for q in d["requests"] if q.get("status") != "completed" and q.get("done"))})
    return {"departments": out, "open": sum(d["open"] for d in out), "overdue": sum(d["overdue"] for d in out)}


# ---- MDT Coordinator -------------------------------------------------------------------------------------------------------------

def _next_board_date(cases: list, today: str) -> str:
    dates = sorted({(c.get("board_date") or "")[:10] for c in cases if c.get("board_date")})
    coming = [d for d in dates if d >= today]
    return coming[0] if coming else (dates[-1] if dates else "")


def coordinator(r: dict, cases: list | None = None) -> dict:
    """The board sessions (open ones first), the readiness of the next board date with its chase list, the ready marks. Built for the
    MDT Coordinator and admins only (sections_for); anyone else gets no agenda and only the sessions it may open."""
    today = _today()
    cases = [c for c in (cases if cases is not None else store.list_cases()) if not access.hidden(r, c)]  # finding 0
    nxt = _next_board_date(cases, today)
    allowed = org.board_wide(r)  # never the Vaidyx admin (review #2)
    agenda = metrics.agenda(nxt) if nxt and allowed else None
    sessions = board.list_sessions()
    if not allowed:
        sessions = [x for x in sessions if board.may_open(r, board.get(x["id"]))]
    open_ = sorted([s for s in sessions if s.get("status") != "closed"], key=lambda s: (s.get("date") or "", s.get("created") or ""))
    closed = [s for s in sessions if s.get("status") == "closed"]
    ready = [c for c in cases if isinstance(c.get("board_ready"), dict)]
    return {"today": today, "next_board_date": nxt, "agenda": agenda,
            "sessions": {"open": open_[:MAX_SESSIONS], "closed": closed[:3], "planned": sum(1 for s in open_ if s.get("status") == "planned"),
                         "in_session": sum(1 for s in open_ if s.get("status") == "in_session"), "closed_n": len(closed)},
            "ready_marked": len(ready), "listed_total": sum(1 for c in cases if (c.get("listing") or {}).get("status") == "listed"),
            "awaiting_listing": sum(1 for c in cases if (c.get("listing") or {}).get("status") == "awaiting_listing"),
            "can_manage": org.can(r, "session")}


# ---- department admin ----------------------------------------------------------------------------------------------------------

def dept_admin(r: dict, mgr=None) -> dict:
    """The departments the user administers (admin_of), each with its doctors: placed, heads, disabled, without a Vaidyx login."""
    out = []
    for d in org.departments():
        if d["id"] not in (r.get("admin_of") or []):
            continue
        docs = accounts.department_doctors(d["id"], mgr)
        placed = [x for x in docs if x.get("role")]
        out.append({"id": d["id"], "name": d["name"], "group": d.get("group"), "doctors": len(placed), "heads": sum(1 for x in placed if x.get("role") == "head"),
                    "disabled": sum(1 for x in placed if x.get("disabled")), "no_login": sum(1 for x in placed if x.get("account") is False),
                    "admins": sum(1 for x in docs if x.get("admin")),
                    "list": [{"username": x["username"], "display_name": x.get("display_name") or "", "role": x.get("role"), "disabled": bool(x.get("disabled")),
                              "account": x.get("account")} for x in placed[:MAX_DOCTORS]]})
    return {"departments": out}


# ---- root admin ----------------------------------------------------------------------------------------------------------------

def setup_needed(h: dict | None = None) -> bool:
    """True until the root admin has answered the first set-up once (the PM-JAY question of plan section 11)."""
    h = h if h is not None else org.hospital()
    return not isinstance(h.get("first_setup"), dict)


def root_admin(r: dict, mgr=None) -> dict:
    o = org.load()
    h = org.hospital()
    users = o.get("users") or {}
    depts = o.get("departments") or []
    users_ok = {u: v for u, v in users.items() if isinstance(v, dict)}
    try:
        his = his_client.public(his_client.settings(), manager=False)
    except Exception:
        his = {}
    return {"hospital": {k: h.get(k) for k in ("name", "level", "type", "pmjay_empanelled", "fetch_window_months")},
            "first_setup": h.get("first_setup") if isinstance(h.get("first_setup"), dict) else None, "setup_needed": setup_needed(h),
            "departments": {"treating": sum(1 for d in depts if d.get("group") == "treating"), "supporting": sum(1 for d in depts if d.get("group") == "supporting"),
                            "placeholder_emails": sum(1 for d in depts if not d.get("email") or str(d.get("email")).endswith("@" + org.PLACEHOLDER_DOMAIN))},
            "accounts": {"placed": len(users_ok), "doctors": sum(1 for v in users_ok.values() if v.get("departments")), "dept_admins": sum(1 for v in users_ok.values() if v.get("admin_of")),
                         "coordinators": sum(1 for v in users_ok.values() if v.get("coordinator") is True), "root_admins": len(o.get("admins") or []),
                         "disabled": sum(1 for v in users_ok.values() if v.get("disabled") is True),
                         "no_login": sum(1 for u in users_ok if mgr is not None and not accounts.account_exists(mgr, u))},
            "his": {"enabled": bool(his.get("enabled")), "label": his.get("label") or "", "kind": his.get("kind") or "", "url": his.get("url") or "",
                    "pacs_url": his.get("pacs_url") or ""},
            "routes_overridden": len(o.get("routes") or {}), "board_heads": [org.department_name(x) for x in h.get("board_heads") or []]}


# ---- the whole home ------------------------------------------------------------------------------------------------------------

def build(r: dict, mgr=None) -> dict:
    """Everything the home of this login shows. `sections` names the parts in display order; each part is under its own key."""
    secs = sections_for(r)
    u = str((r or {}).get("user") or "")
    disp = ((org.load().get("users") or {}).get(u) or {}).get("display_name") if u else ""
    out = {"user": u, "display_name": disp or "", "today": _today(), "sections": secs, "primary": secs[0] if secs else "none",
           "roles": {k: r.get(k) for k in ("admin", "root_admin", "coordinator", "known", "disabled")} if isinstance(r, dict) else {},
           "departments": [{"id": d["id"], "name": d["name"], "group": d.get("group"), "role": d.get("role")} for d in org.my_departments(r)] if not (r or {}).get("admin") else [],
           "admin_of": [{"id": d["id"], "name": d["name"]} for d in org.departments() if d["id"] in ((r or {}).get("admin_of") or [])],
           "unread": notify.unread_count(r) if secs else 0, "notifications": notify.for_roles(r, limit=MAX_NOTIFICATIONS) if secs else []}
    cases = store.list_cases() if ("treating" in secs or "coordinator" in secs or "resident" in secs) else None  # read once for every section
    if "treating" in secs:
        out["treating"] = treating(r, cases)
    # 18 Oct: a consultant's residents' proposals, join requests and confirmations; a resident's own proposals returned with a note
    out["waiting_for_me"] = (proposals.waiting_for(r, cases) if "treating" in secs else
                             [p for p in proposals.mine(r, cases) if p.get("status") == proposals.RETURNED] if "resident" in secs else [])
    if "resident" in secs:
        out["resident"] = resident(r, cases)
    if "supporting" in secs:
        out["supporting"] = supporting(r)
    if "coordinator" in secs:
        out["coordinator"] = coordinator(r, cases)
    if "dept_admin" in secs:
        out["dept_admin"] = dept_admin(r, mgr)
    if "root_admin" in secs:
        out["root_admin"] = root_admin(r, mgr)
    return out
