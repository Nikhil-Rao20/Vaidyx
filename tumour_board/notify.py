"""In-app notifications and the department inbox (plan item 4.4).

Notifications: data/tumour_board/notifications.jsonl, one JSON object per line, appended on notify(); rewritten on
mark_read() and prune(). Each one is addressed to a department ({"department": "<id>"}), to the coordinators
({"role": "coordinator"}) or to one user ({"user": "<username>"}), and remembers who has read it ({user: ts}). Every
notification is a stored record: that is its audit trail (the gate side is audited in the Case File).

Inbox: every open Pre-Authorization request (an action with source "pre_authorization" in a Case File's state) for the
departments the user may see, grouped by Responsible Department. Overdue is worked out on display from the due date;
requests closed in the last 7 days are shown too, so a department sees what closed.

No model calls. A missing file means no notifications; a malformed line is skipped, never fatal.
"""
import json, logging, os, threading, uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, org, store

log = logging.getLogger(__name__)

KINDS = ("request", "request_closed", "case_ready")  # a gap routed to a department; a request closed; the Case File is ready
ROLES = ("coordinator",)
CORE = ("id", "ts", "to", "kind", "case_id", "title", "text", "read_by")
OPEN_STATUSES = ("pending", "overdue")
RECENT_COMPLETED_DAYS = 7
PRUNE_EVERY = 200

_lock = threading.Lock()
_writes = 0


def path() -> Path:
    return Path(config.DATA_ROOT) / "notifications.jsonl"


def _today() -> date:
    return date.today()


# ---- storage --------------------------------------------------------------------------------------------------------

def _load() -> list[dict]:
    """Every stored notification in file order (oldest first). Call with _lock held."""
    p = path()
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError as e:
        log.warning("notifications could not be read (%s)", e)
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            log.warning("skipping a malformed notification line")
            continue
        if isinstance(rec, dict) and isinstance(rec.get("to"), dict) and rec.get("id"):
            out.append(rec)
    return out


def _rewrite(recs: list[dict]) -> None:
    """Replace the file atomically. Call with _lock held."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, p)


def _address(to) -> dict:
    """A clean address, or ValueError with a plain message."""
    if not isinstance(to, dict) or len(to) != 1:
        raise ValueError("A notification goes to exactly one of: a department, the coordinator role or a user.")
    (k, v), = to.items()
    v = str(v or "").strip()
    if k == "department":
        did = org.department_id(v)
        if not did:
            raise ValueError(f"Unknown department {v!r}.")
        return {"department": did}
    if k == "role":
        if v not in ROLES:
            raise ValueError(f"Unknown role {v!r}; notifications can go to: {', '.join(ROLES)}.")
        return {"role": v}
    if k == "user":
        if not v:
            raise ValueError("A notification to a user needs a username.")
        return {"user": v}
    raise ValueError(f"Unknown address {k!r}; use department, role or user.")


def notify(to: dict, kind: str, case_id: str, title: str, text: str = "", **extra) -> dict:
    """Store one notification and return it. ValueError for an unknown kind or address."""
    global _writes
    if kind not in KINDS:
        raise ValueError(f"Unknown notification kind {kind!r}; use one of: {', '.join(KINDS)}.")
    addr = _address(to)
    rec = {"id": "N" + uuid.uuid4().hex[:8], "ts": store.now_iso(), "to": addr, "kind": kind,
           "case_id": str(case_id or ""), "title": str(title or ""), "text": str(text or "")}
    rec.update({k: v for k, v in extra.items() if k not in CORE})
    rec["read_by"] = {}
    with _lock:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        _writes += 1
        due_prune = _writes % PRUNE_EVERY == 0
    if due_prune:
        try:
            prune()
        except Exception as e:  # pruning is housekeeping: never fail the write for it
            log.warning("notification prune failed (%s)", e)
    return dict(rec)


# ---- what is new for me ---------------------------------------------------------------------------------------------

def _mine(rec: dict, r: dict) -> bool:
    """True if the notification is addressed to the user with roles `r` (admins also see every department's)."""
    to = rec.get("to") or {}
    r = r or {}
    if "department" in to:
        return bool(r.get("admin")) or to["department"] in (r.get("departments") or {})
    if "role" in to:
        return to["role"] == "coordinator" and bool(r.get("coordinator") or r.get("admin"))
    if "user" in to:
        return bool(r.get("user")) and to["user"] == r.get("user")
    return False


def _user_key(r: dict) -> str:
    return str((r or {}).get("user") or "")


def _public(rec: dict, user: str) -> dict:
    out = {k: v for k, v in rec.items() if k != "read_by"}
    out["read"] = user in (rec.get("read_by") or {})
    return out


def for_roles(r: dict, limit: int = 100, unread_only: bool = False) -> list[dict]:
    """My notifications, newest first, each with "read" for this user."""
    user = _user_key(r)
    with _lock:
        recs = _load()
    out = []
    for rec in reversed(recs):
        if not _mine(rec, r):
            continue
        item = _public(rec, user)
        if unread_only and item["read"]:
            continue
        out.append(item)
        if limit is not None and len(out) >= limit:
            break
    return out


def unread_count(r: dict) -> int:
    return len(for_roles(r, limit=None, unread_only=True))


def mark_read(r: dict, ids: list[str] | None = None) -> int:
    """Mark my notifications read (all of mine when ids is None). Returns how many changed; others are untouched."""
    user = _user_key(r)
    want = None if ids is None else {str(i) for i in ids}
    if want is not None and not want:
        return 0
    with _lock:
        recs = _load()
        ts, changed = store.now_iso(), 0
        for rec in recs:
            if want is not None and rec.get("id") not in want:
                continue
            if not _mine(rec, r):
                continue
            rb = rec.get("read_by") if isinstance(rec.get("read_by"), dict) else {}
            if user in rb:
                continue
            rb[user] = ts
            rec["read_by"] = rb
            changed += 1
        if changed:
            _rewrite(recs)
    return changed


def _ts(rec: dict):
    try:
        return datetime.fromisoformat(str(rec.get("ts") or ""))
    except ValueError:
        return None


def prune(max_age_days: int = 90, keep: int = 5000) -> int:
    """Drop notifications older than max_age_days, then keep only the newest `keep`. Returns how many were dropped.

    A notification whose time cannot be read is kept (subject to `keep`)."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    with _lock:
        recs = _load()
        p = path()
        try:
            lines = sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip()) if p.exists() else 0
        except OSError:
            lines = len(recs)
        kept = [rec for rec in recs if (_ts(rec) is None or _ts(rec) >= cutoff)]
        if keep is not None and len(kept) > max(keep, 0):
            kept = kept[len(kept) - max(keep, 0):]
        dropped = len(recs) - len(kept)
        if dropped or lines != len(recs):  # also clears malformed lines
            _rewrite(kept)
    return dropped


# ---- department inbox -----------------------------------------------------------------------------------------------

def _due_date(due):
    try:
        return date.fromisoformat(str(due or "")[:10])
    except ValueError:
        return None


def _action_department(a: dict) -> str | None:
    """The department id an action belongs to: its department_id when present (and known), else its department name."""
    if a.get("department_id"):
        did = org.department_id(a["department_id"])
        if did:
            return did
    return org.department_id(a.get("department") or "")


def _request(case: dict, a: dict, today: date) -> dict | None:
    """One inbox row, or None when the action is not shown (closed more than 7 days ago, or closed at an unknown time)."""
    status = str(a.get("status") or "pending")
    overdue, days = False, 0
    if status == "completed":
        done = str(a.get("completed") or "")[:10]
        if not done or done < (today - timedelta(days=RECENT_COMPLETED_DAYS)).isoformat():
            return None
    else:
        due = _due_date(a.get("due"))
        if due is not None:
            if due < today:
                status, overdue, days = "overdue", True, (today - due).days
            elif status == "overdue":  # stored as overdue but the due date was moved: not overdue today
                status = "pending"
        elif status == "overdue":
            overdue = True
    p = case.get("patient") if isinstance(case.get("patient"), dict) else {}
    return {"case_id": case.get("case_id"),
            "patient": {"name": p.get("name", ""), "mrn": p.get("mrn", ""), "agesex": p.get("agesex", "")},
            "protocol": case.get("protocol", ""), "board_date": case.get("board_date", ""),
            "action_id": a.get("id"), "requirement": a.get("requirement"), "label": a.get("label", ""),
            "what": a.get("what", ""), "level": a.get("level"), "level_label": a.get("level_label", ""),
            "due": a.get("due", ""), "status": status, "overdue": overdue, "days_overdue": days,
            "created": a.get("created", ""), "completed": a.get("completed"), "history": list(a.get("history") or [])}


def _cases():
    """(case, state) for every Case File on disk; unreadable ones are skipped."""
    base = Path(config.CASES_DIR)
    if not base.exists():
        return
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        try:
            case = store.get_case(d.name)
            st = store.get_state(d.name) if case else None
        except (ValueError, OSError) as e:
            log.warning("inbox: skipping Case File %s (%s)", d.name, e)
            continue
        if isinstance(case, dict) and isinstance(st, dict):
            yield case, st


def inbox(r: dict) -> dict:
    """Open Pre-Authorization requests (and those closed in the last 7 days) for every department the user may see."""
    today = _today()
    visible = org.visible_departments_for_inbox(r)
    rows: dict[str, list] = {did: [] for did in visible}
    if rows:
        for case, st in _cases():
            for a in st.get("actions") or []:
                if not isinstance(a, dict) or a.get("source") != "pre_authorization":
                    continue
                did = _action_department(a)
                if did not in rows:
                    continue
                req = _request(case, a, today)
                if req:
                    rows[did].append(req)
    out, total_open, total_over = [], 0, 0
    for did in visible:
        reqs = sorted(rows[did], key=lambda q: str(q.get("created") or ""), reverse=True)
        n_open = sum(1 for q in reqs if q["status"] != "completed")
        n_over = sum(1 for q in reqs if q["overdue"])
        out.append({"id": did, "name": org.department_name(did), "requests": reqs, "open": n_open, "overdue": n_over})
        total_open += n_open
        total_over += n_over
    return {"departments": out, "open": total_open, "overdue": total_over, "generated": store.now_iso()}
