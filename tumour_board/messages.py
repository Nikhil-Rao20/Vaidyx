"""Messages between logins (night-v3 Phase 8, owner decision D5): any placed login may write to any person or any department of the
same hospital; a department message reaches all its members and any member may answer; a message never grants access to a Case File it
links to; push notifications carry no patient details.

The contract is docs/night-v3/research/06_messages.md section 9. Storage: data/tumour_board/messages/ (index.json, reads.json and one
append-only c_<id>.jsonl per conversation), all under one lock. Message text lives only here: never in a notification, a push, an audit
line or a log.

Every public function takes the login `by` (never a request) and an optional roles dict `r` (the router passes the one it computed, so
a Vaidyx admin flag is honoured); it raises Refused(status, code, message) for the router to turn into a plain refusal.
"""
from __future__ import annotations

import json, logging, os, re, threading, time, uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import config, org, profiles, store

log = logging.getLogger(__name__)

REACTIONS = ("thumbs_up", "seen", "thanks", "will_do", "tick")
TEXT_MAX = 2000
EDIT_WINDOW_SECONDS = 600
PRESENCE_AWAY_SECONDS = 600
PREVIEW_CHARS = 120
MENTIONS_MAX = 8
SEARCH_MIN = 2
SEARCH_MAX = 50
PAGE_DEFAULT = 100
PAGE_MAX = 500
LINKS_MAX = 20
PUSH_EVERY = 300.0  # at most one push per reader per conversation in this many seconds
DENIED_EVERY = 60.0  # at most one message_denied audit line per login in this many seconds
KINDS = ("direct", "department", "coordinator")
FILTERS = ("all", "unread", "open", "resolved")
EVENTS = ("msg", "edit", "delete", "react", "resolve")

NOT_PLACED = "Messages are for placed hospital staff."
SELF_MESSAGE = "You cannot message yourself."
CANNOT_REACH = "That person cannot be reached."
TOO_LONG = f"A message can have at most {TEXT_MAX} characters."
EMPTY = "Write a message first."
LINK_NOT_ALLOWED = "You can only attach a Case File you can open."
EDIT_WINDOW_OVER = "You can only edit a message for 10 minutes."
NOT_FOUND = "No such conversation."

_CID = re.compile(r"^C[0-9a-f]{10}$")
_MID = re.compile(r"^M[0-9a-f]{10}$")
_MENTION = re.compile(r"(?<![\w.@])@([A-Za-z0-9_][A-Za-z0-9_.\-]{0,63})")

_lock = threading.RLock()  # every read-modify-write of the store (the scheduler's retention job included)
_cache: dict = {}  # str(path) -> ((mtime_ns, size), events) for the conversation files
_PUSHED: dict = {}  # (reader, conversation) -> monotonic time of the last push
_DENIED: dict = {}  # login -> monotonic time of the last message_denied audit line

# Real time (item 8.2): tumour_board/api/messages_ws.py registers its sender here at import. A listener gets (reader, event) with the
# event already built for that reader; INTERESTED(reader) says whether the reader has a live socket (no socket: nothing is built).
LISTENERS: list[Callable[[str, dict], None]] = []
INTERESTED: Callable[[str], bool] = lambda user: True  # noqa: E731


class Refused(Exception):
    """A refused action: the router turns it into common.fail(status, message, code)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def may_use(r: dict) -> bool:
    """Who may use Messages and be reached: a signed-in login that is not disabled or expired and is placed in a department or is the
    MDT Coordinator. Never `known` alone (true for a Vaidyx admin with no placement). No root admin, auditor, outside expert or Vaidyx
    admin without a placement."""
    if not isinstance(r, dict) or not r.get("user"):
        return False
    if r.get("disabled") or r.get("expired"):
        return False
    return bool(r.get("departments")) or bool(r.get("coordinator"))


# Presence (item 8.2): the socket module replaces this with the hub's state. "online" | "away" | "offline".
PRESENCE = lambda user: "offline"  # noqa: E731


def presence(user: str) -> str:
    try:
        return str(PRESENCE(user) or "offline")
    except Exception:
        return "offline"


def ONLINE(user: str) -> bool:  # noqa: N802 (the contract's name)
    return presence(user) == "online"


# ---- time -------------------------------------------------------------------------------------------------------------------------------

def _now() -> datetime:
    """The one clock of this module (tests replace it): stored times and the 10-minute window both come from here."""
    return datetime.fromisoformat(store.now_iso())


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _parse(ts) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return d.replace(tzinfo=None) if d.tzinfo else d


# ---- storage ----------------------------------------------------------------------------------------------------------------------------

def _dir(create: bool = False) -> Path:
    d = Path(config.DATA_ROOT) / "messages"
    if create:
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    return d


def _read_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("messages: %s unreadable (%s)", p.name, e.__class__.__name__)
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(p: Path, obj: dict) -> None:
    """Atomic: a sibling .tmp (mode 600) written and fsynced, then os.replace. A crash before the replace leaves the old file whole."""
    _dir(create=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _index() -> dict:
    d = _read_json(_dir() / "index.json")
    convs = d.get("conversations")
    return {"conversations": {k: v for k, v in convs.items() if isinstance(v, dict) and _CID.match(str(k))} if isinstance(convs, dict) else {}}


def _save_index(d: dict) -> None:
    _write_json(_dir() / "index.json", d)


def _reads() -> dict:
    d = _read_json(_dir() / "reads.json")
    users = d.get("users")
    return {"users": users if isinstance(users, dict) else {}}


def _save_reads(d: dict) -> None:
    _write_json(_dir() / "reads.json", d)


def _conv_path(cid: str) -> Path:
    return _dir() / f"c_{cid}.jsonl"


def _events(cid: str) -> list[dict]:
    """The events of one conversation in file order; a malformed line is skipped. Callers must not change the returned dicts."""
    p = _conv_path(cid)
    with _lock:
        try:
            st = p.stat()
        except FileNotFoundError:
            return []
        key = (st.st_mtime_ns, st.st_size)
        hit = _cache.get(str(p))
        if hit and hit[0] == key:
            return hit[1]
        out = []
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and isinstance(ev.get("seq"), int) and ev.get("t") in EVENTS:
                        out.append(ev)
        except OSError as e:
            log.warning("messages: a conversation file is unreadable (%s)", e.__class__.__name__)
            return []
        _cache[str(p)] = (key, out)
        return out


def _append(cid: str, ev: dict) -> None:
    """One event as one line, flushed and fsynced (call with _lock)."""
    _dir(create=True)
    p = _conv_path(cid)
    fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    _cache.pop(str(p), None)


def _rewrite(cid: str, events: list[dict]) -> None:
    """Only the retention job rewrites a conversation file (tmp + os.replace, mode 600; call with _lock)."""
    p = _conv_path(cid)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    _cache.pop(str(p), None)


def _next_seq(cid: str) -> int:
    return max((ev["seq"] for ev in _events(cid)), default=0) + 1


# ---- who --------------------------------------------------------------------------------------------------------------------------------

def _roles_of(user: str) -> dict:
    try:
        return org.roles(str(user or "")) if user else {}
    except Exception:
        return {}


def _need_use(rl: dict) -> None:
    if not may_use(rl):
        raise Refused(403, "not_placed", NOT_PLACED)


def reachable(user: str) -> bool:
    """The same test as may_use, on the target login (an unknown login is simply not reachable)."""
    return bool(user) and may_use(_roles_of(user))


def _name(user: str) -> str:
    try:
        return profiles.display_name(user)
    except Exception:
        return str(user or "")


def _title(user: str) -> str:
    try:
        return str(profiles.get(user).get("title") or "")
    except Exception:
        return ""


def _members(did: str) -> list[str]:
    """Everyone placed in the department now who may use Messages (push.users_for's rule, then not expired)."""
    from . import push
    out = []
    for u in push.users_for({"department": did}):
        rl = _roles_of(u)
        if may_use(rl) and did in (rl.get("departments") or {}):
            out.append(u)
    return out


def _coordinators() -> list[str]:
    users = org.load().get("users") or {}
    return [u for u in sorted(users) if isinstance(users[u], dict) and users[u].get("coordinator") is True and may_use(_roles_of(u))]


def readers(conv: dict) -> list[str]:
    """Who reads this conversation now: direct = the two; department = the sender and every current member; coordinator = the sender
    and the coordinators. Only logins that may use Messages now."""
    people = [str(p) for p in (conv.get("people") or []) if p]
    kind = conv.get("kind")
    if kind == "department":
        cand = people + _members(str(conv.get("department") or ""))
    elif kind == "coordinator":
        cand = people + _coordinators()
    else:
        cand = people
    return [u for u in dict.fromkeys(cand) if may_use(_roles_of(u))]


def _is_reader(conv: dict, user: str, rl: dict) -> bool:
    if not may_use(rl) or rl.get("user") != user:
        return False
    if user in (conv.get("people") or []):
        return True
    if conv.get("kind") == "department":
        return str(conv.get("department") or "") in (rl.get("departments") or {})
    if conv.get("kind") == "coordinator":
        return bool(rl.get("coordinator"))
    return False


def _conv_for(conv_id: str, by: str, rl: dict, idx: dict | None = None) -> dict:
    """The conversation when `by` reads it; else 404 with the same words as an unknown id."""
    cid = str(conv_id or "")
    if not _CID.match(cid):
        raise Refused(404, "not_found", NOT_FOUND)
    conv = (idx or _index())["conversations"].get(cid)
    if not conv or not _is_reader(conv, by, rl):
        raise Refused(404, "not_found", NOT_FOUND)
    return conv


def _audit_to(conv: dict, by: str) -> str:
    if conv.get("kind") == "department":
        return str(conv.get("department") or "")
    if conv.get("kind") == "coordinator":
        return "coordinator"
    return next((p for p in conv.get("people") or [] if p != by), by)


def _audit(kind: str, by: str, conv: dict) -> None:
    """An audit line with the conversation id, its kind and its target; never a text, a message id or a Case File id."""
    try:
        org.audit(kind, by, conversation=conv.get("id"), type=conv.get("kind"), to=_audit_to(conv, by))
    except Exception as e:
        log.warning("messages: audit failed (%s)", e.__class__.__name__)


def note_denied(by: str, route: str, conv_id: str = "") -> None:
    """A refused message route (not placed, not a participant): one audit line a minute per login at most, so probing shows."""
    now = time.monotonic()
    key = str(by or "")
    if now - _DENIED.get(key, -1e9) < DENIED_EVERY:
        return
    _DENIED[key] = now
    try:
        org.audit("message_denied", key, type=str(route or "")[:60], conversation=str(conv_id or "")[:20])
    except Exception:
        pass


# ---- links (9.4: a link grants nothing) ----------------------------------------------------------------------------------------------

def _case(cid: str):
    from . import access
    cid = str(cid or "").strip()
    if not cid or access.is_protected(cid):
        return None
    try:
        if store.safe_id(cid) != cid:
            return None
        c = store.get_case(cid)
    except (ValueError, OSError):
        return None
    return c if isinstance(c, dict) else None


def _meeting(mid: str):
    from . import meetings
    try:
        return meetings.get(str(mid or "")) if mid else None
    except Exception:
        return None


def _case_label(c: dict) -> str:
    from . import protocol
    try:
        label = protocol.case_label(c)
    except Exception:
        label = ""
    cid = str(c.get("case_id") or "")
    return f"{cid}, {label}" if label else cid


def check_link(by: str, link, r: dict | None = None):
    """The link as stored ({"type", "id"}) when the sender may attach it, None for no link; else 400 link_not_allowed (the same for an
    unknown type or id, so ids cannot be probed)."""
    if link is None or link == "" or link == {}:
        return None
    rl = r if r is not None else _roles_of(by)
    if not isinstance(link, dict):
        raise Refused(400, "link_not_allowed", LINK_NOT_ALLOWED)
    typ, lid = link.get("type"), str(link.get("id") or "").strip()
    try:
        if typ == "case":
            from . import access
            c = _case(lid)
            if c and not access.is_protected(c) and access.scope(rl, c) is not None:
                return {"type": "case", "id": lid}
        elif typ == "meeting":
            from . import meetings
            s = _meeting(lid)
            if s and meetings.may_view(rl, s):
                return {"type": "meeting", "id": str(s.get("id") or lid)}
    except Refused:
        raise
    except Exception as e:
        log.warning("messages: link check failed (%s)", e.__class__.__name__)
    raise Refused(400, "link_not_allowed", LINK_NOT_ALLOWED)


def link_view(by: str, link, r: dict | None = None):
    """The chip one reader sees, computed now with the reader's roles: a label only when the reader may open the Case File (the case
    id and the cancer name, never the patient's name or UHID) or view the meeting; nothing is written anywhere."""
    if not isinstance(link, dict) or link.get("type") not in ("case", "meeting"):
        return None
    rl = r if r is not None else _roles_of(by)
    lid = str(link.get("id") or "")
    chip = {"type": link["type"], "id": lid, "label": None, "can_open": False, "offer": False}
    try:
        if link["type"] == "case":
            from . import access
            if access.is_protected(lid):
                return chip
            c = _case(lid)
            if not c:
                return chip
            if access.scope(rl, c) is not None:
                chip.update(label=_case_label(c), can_open=True)
            else:
                chip["offer"] = bool(access.may_open_with_reason(rl, c))
        else:
            from . import meetings
            s = _meeting(lid)
            if s and meetings.may_view(rl, s):
                chip.update(label=meetings.summary_row(s).get("label"), can_open=True)
    except Exception as e:
        log.warning("messages: chip failed (%s)", e.__class__.__name__)
        return {"type": link["type"], "id": lid, "label": None, "can_open": False, "offer": False}
    return chip


def attachable(by: str, q: str = "", r: dict | None = None) -> dict:
    """What the sender may attach: the Case Files they can open (never a protected or archived one) and the meetings they can view, at
    most LINKS_MAX each, `q` filtering the label."""
    from . import access, meetings
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    want = " ".join(str(q or "").lower().split())
    cases = []
    try:
        listed = sorted(store.list_cases(), key=lambda c: str(c.get("created") or ""), reverse=True)
    except Exception:
        listed = []
    for c in listed:
        cid = str(c.get("case_id") or "")
        if not cid or access.is_protected(cid) or access.is_archived(c):
            continue
        try:
            if access.scope(rl, c) is None:
                continue
        except Exception:
            continue
        label = _case_label(c)
        if want and want not in label.lower():
            continue
        cases.append({"id": cid, "label": label})
        if len(cases) >= LINKS_MAX:
            break
    rows = []
    try:
        rows = [m for m in meetings.list_meetings(rl).get("meetings") or [] if not m.get("cancelled")]
    except Exception:
        rows = []
    rows.sort(key=lambda m: (str(m.get("date") or ""), str(m.get("time") or "")), reverse=True)
    mts = []
    for m in rows:
        label = str(m.get("label") or "")
        if want and want not in label.lower():
            continue
        mts.append({"id": m.get("id"), "label": label})
        if len(mts) >= LINKS_MAX:
            break
    return {"cases": cases, "meetings": mts}


# ---- folding the events -------------------------------------------------------------------------------------------------------------

def _fold(events: list[dict]) -> tuple[dict, list]:
    """The messages as they stand: {id: state} and the list in send order."""
    msgs, order = {}, []
    for ev in events:
        t = ev.get("t")
        if t == "msg":
            mid = ev.get("id")
            if not mid or mid in msgs:
                continue
            m = {"id": mid, "seq": ev["seq"], "ts": ev.get("ts"), "by": ev.get("by"), "text": str(ev.get("text") or ""),
                 "link": ev.get("link") if isinstance(ev.get("link"), dict) else None,
                 "mentions": [str(x) for x in (ev.get("mentions") or []) if x], "edited": False, "edited_ts": None,
                 "deleted": False, "removed": bool(ev.get("removed")), "reactions": {}}
            msgs[mid] = m
            order.append(m)
            continue
        m = msgs.get(ev.get("of"))
        if not m:
            continue
        if t == "edit" and ev.get("by") == m["by"] and not m["deleted"]:
            m["text"] = str(ev.get("text") or "")
            m["edited"], m["edited_ts"] = True, ev.get("ts")
            if ev.get("removed"):
                m["removed"] = True
        elif t == "delete" and ev.get("by") == m["by"]:
            m["deleted"], m["text"] = True, ""
        elif t == "react":
            who, emoji = ev.get("by"), ev.get("emoji")
            if emoji is None:
                for k in list(m["reactions"]):
                    m["reactions"][k] = [u for u in m["reactions"][k] if u != who]
                    if not m["reactions"][k]:
                        del m["reactions"][k]
            elif emoji in REACTIONS and who not in m["reactions"].get(emoji, []):
                m["reactions"].setdefault(emoji, []).append(who)
    return msgs, order


def _until(m: dict) -> datetime | None:
    ts = _parse(m.get("ts"))
    return ts + timedelta(seconds=EDIT_WINDOW_SECONDS) if ts else None


def _message(m: dict, reader: str, rl: dict, names: dict | None = None) -> dict:
    """Message as one reader sees it (9.2): a deleted or removed one has no text and no chip."""
    names = names if names is not None else {}
    by = m.get("by") or ""
    if by not in names:
        names[by] = _name(by)
    gone = m["deleted"] or m["removed"]
    can_until = None
    if by == reader and not gone:
        until = _until(m)
        if until and _now() <= until:
            can_until = _iso(until)
    return {"id": m["id"], "seq": m["seq"], "ts": m["ts"], "by": by, "by_name": names[by], "text": "" if gone else m["text"],
            "link": None if gone or not m.get("link") else link_view(reader, m["link"], r=rl), "mentions": list(m["mentions"]),
            "edited": bool(m["edited"]), "edited_ts": m["edited_ts"], "deleted": bool(m["deleted"]), "removed": bool(m["removed"]),
            "reactions": {k: list(v) for k, v in m["reactions"].items()}, "can_edit_until": can_until}


def _last_msg_seq(cid: str) -> int:
    return max((ev["seq"] for ev in _events(cid) if ev.get("t") == "msg"), default=0)


def _read_entry(reads: dict, user: str, cid: str) -> dict:
    e = (((reads.get("users") or {}).get(user) or {}).get("conversations") or {}).get(cid)
    return e if isinstance(e, dict) else {}


def _unread(order: list, user: str, seen: int) -> int:
    return sum(1 for m in order if m["seq"] > seen and m.get("by") != user)


def _plural(n: int, one: str, many: str) -> str:
    return f"Reaches {n} {one if n == 1 else many}"


def _row(conv: dict, by: str, rl: dict, reads: dict | None = None, order: list | None = None) -> dict:
    """ConversationRow (9.2) as `by` sees it."""
    cid = conv["id"]
    if order is None:
        order = _fold(_events(cid))[1]
    reads = reads if reads is not None else _reads()
    entry = _read_entry(reads, by, cid)
    kind = conv.get("kind")
    creator = conv.get("created_by") or ""
    with_, dept = None, None
    if kind == "department":
        did = str(conv.get("department") or "")
        members = _members(did)
        dept = {"id": did, "name": org.department_name(did), "members": len(members)}
        title = dept["name"]
        if by == creator:
            subtitle = _plural(len([u for u in dict.fromkeys([creator] + members) if u != by]), "person", "people")
        else:
            subtitle = f"From {_name(creator)}"
    elif kind == "coordinator":
        title = org.COORDINATOR_NAME
        subtitle = _plural(len([u for u in _coordinators() if u != by]), "coordinator", "coordinators") if by == creator else f"From {_name(creator)}"
    else:
        other = next((p for p in conv.get("people") or [] if p != by), by)
        orl = _roles_of(other)
        names = [org.department_name(d) for d in (orl.get("departments") or {})]
        if orl.get("coordinator"):
            names.append(org.COORDINATOR_NAME)
        t = _title(other)
        state = presence(other)
        with_ = {"user": other, "display_name": _name(other), "title": t, "departments": names, "online": state == "online", "presence": state}
        title = with_["display_name"]
        subtitle = ", ".join(x for x in [t, *names] if x)
    last = None
    if order:
        m = order[-1]
        gone = m["deleted"] or m["removed"]
        last = {"seq": m["seq"], "ts": m["ts"], "by": m["by"], "by_name": _name(m["by"]), "preview": "" if gone else m["text"][:PREVIEW_CHARS]}
    res = conv.get("resolved")
    resolved = {"by": res.get("by"), "by_name": _name(res.get("by")), "ts": res.get("ts")} if isinstance(res, dict) else None
    return {"id": cid, "kind": kind, "title": title, "subtitle": subtitle, "with": with_, "department": dept, "created_by": creator,
            "last": last, "unread": _unread(order, by, int(entry.get("seq") or 0)), "resolved": resolved, "muted": bool(entry.get("muted"))}


def conversation_row(by: str, conv_id: str, r: dict | None = None) -> dict:
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    with _lock:
        return _row(_conv_for(conv_id, by, rl), by, rl)


# ---- the notifiers and the live events (never raise) --------------------------------------------------------------------------------

def _emit(readers_: list, build: Callable[[str], dict]) -> None:
    """Give each live listener the event built for each reader. Exceptions are logged (no text), never raised."""
    if not LISTENERS:
        return
    for u in readers_:
        try:
            if not INTERESTED(u):
                continue
            ev = build(u)
        except Exception as e:
            log.warning("messages: a live event could not be built (%s)", e.__class__.__name__)
            continue
        if not ev:
            continue
        for fn in list(LISTENERS):
            try:
                fn(u, ev)
            except Exception as e:
                log.warning("messages: a live listener failed (%s)", e.__class__.__name__)


def _bell_ids(reader: str, cid: str) -> list[str]:
    from . import notify
    return [n["id"] for n in notify.for_roles(_roles_of(reader), limit=None, unread_only=True)
            if n.get("kind") == "message" and n.get("conversation") == cid and n.get("id")]


def _bell(reader: str, cid: str, sender_name: str) -> None:
    """One unread "message" item per reader and conversation (coalesced); addressed to the user, never a department (admins see those)."""
    from . import notify
    if _bell_ids(reader, cid):
        return
    notify.notify({"user": reader}, "message", "", f"New message from {sender_name}", "", conversation=cid)


def _push(users: list, cid: str, sender_name: str) -> None:
    """The push names the sender and nothing else; at most one per reader per conversation per PUSH_EVERY seconds."""
    from . import push
    if not users or not push.enabled():
        return
    now = time.monotonic()
    due = []
    for u in users:
        if now - _PUSHED.get((u, cid), -1e9) >= PUSH_EVERY:
            _PUSHED[(u, cid)] = now
            due.append(u)
    if not due:
        return
    text = f"Vaidyx-TB: New message from {sender_name}"
    if push.ASYNC:
        threading.Thread(target=push.send_to_users, args=(due, "message", text), daemon=True, name="tb-message-push").start()
    else:
        push.send_to_users(due, "message", text)


def _after_send(conv: dict, by: str, mid: str, readers_: list, reopened: bool) -> None:
    cid = conv["id"]
    try:
        name = _name(by)
        reads = _reads()
        others = [u for u in readers_ if u != by]
        wanting = [u for u in others if not _read_entry(reads, u, cid).get("muted")]
        for u in wanting:
            try:
                _bell(u, cid, name)
            except Exception as e:
                log.warning("messages: bell item failed (%s)", e.__class__.__name__)
        try:
            _push(wanting, cid, name)
        except Exception as e:
            log.warning("messages: push failed (%s)", e.__class__.__name__)
    except Exception as e:
        log.warning("messages: notifiers failed (%s)", e.__class__.__name__)

    def build(u):
        rl = _roles_of(u)
        with _lock:
            msgs, order = _fold(_events(cid))
            c = _index()["conversations"].get(cid) or conv
            return {"type": "message", "conversation": _row(c, u, rl, order=order), "message": _message(msgs[mid], u, rl)}
    _emit(readers_, build)
    if reopened:
        _emit(readers_, lambda u: {"type": "resolve", "conversation_id": cid, "resolved": None})
    _emit([u for u in readers_ if u != by], lambda u: {"type": "unread", "total": unread_total(u)})


def _emit_message(conv: dict, mid: str, kind: str) -> None:
    cid = conv["id"]

    def build(u):
        rl = _roles_of(u)
        msgs, _ = _fold(_events(cid))
        return {"type": kind, "conversation_id": cid, "message": _message(msgs[mid], u, rl)} if mid in msgs else None
    try:
        _emit(readers(conv), build)
    except Exception as e:
        log.warning("messages: live %s failed (%s)", kind, e.__class__.__name__)


# ---- text ---------------------------------------------------------------------------------------------------------------------------

def _clean_text(text) -> str:
    t = str(text if text is not None else "").strip()
    if not t:
        raise Refused(400, "empty", EMPTY)
    if len(t) > TEXT_MAX:
        raise Refused(400, "too_long", TOO_LONG)
    return t


def _mentions(mentions, text: str, readers_: list, by: str) -> list[str]:
    cand = [str(x) for x in (mentions or []) if isinstance(x, str)] if isinstance(mentions, list) else []
    cand += _MENTION.findall(text or "")
    ok = set(readers_) - {by}
    return [u for u in dict.fromkeys(cand) if u in ok][:MENTIONS_MAX]


# ---- conversations ------------------------------------------------------------------------------------------------------------------

def _target(by: str, rl: dict, to) -> tuple[str, str]:
    """(kind, target) for a `to` of start(): a reachable other person, an existing department with someone else in it, or the MDT
    Coordinator role (when there is one and the sender is not a coordinator)."""
    if not isinstance(to, dict):
        raise Refused(400, "cannot_reach", CANNOT_REACH)
    if "user" in to:
        u = str(to.get("user") or "").strip()
        if u and u == by:
            raise Refused(400, "self_message", SELF_MESSAGE)
        if not u or not reachable(u):
            raise Refused(400, "cannot_reach", CANNOT_REACH)
        return "direct", u
    if "department" in to:
        did = str(to.get("department") or "").strip()
        if not did or org.is_coordinator_name(did) or not any(d.get("id") == did for d in org.departments()):
            raise Refused(400, "cannot_reach", CANNOT_REACH)
        if not [u for u in _members(did) if u != by]:
            raise Refused(400, "cannot_reach", CANNOT_REACH)
        return "department", did
    if to.get("role") == "coordinator":
        if rl.get("coordinator"):
            raise Refused(400, "self_message", SELF_MESSAGE)
        if not [u for u in _coordinators() if u != by]:
            raise Refused(400, "cannot_reach", CANNOT_REACH)
        return "coordinator", "coordinator"
    raise Refused(400, "cannot_reach", CANNOT_REACH)


def _find(idx: dict, by: str, kind: str, target: str) -> dict | None:
    for c in idx["conversations"].values():
        if c.get("kind") != kind:
            continue
        if kind == "direct" and set(c.get("people") or []) == {by, target}:
            return c
        if kind == "department" and c.get("created_by") == by and c.get("department") == target:
            return c
        if kind == "coordinator" and c.get("created_by") == by:
            return c
    return None


def find(by: str, to, r: dict | None = None) -> str | None:
    """The id of the conversation start() would add to, or None when it would create one (the router picks its rate limit with it).
    Refuses the same way as start()."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    kind, target = _target(by, rl, to)
    with _lock:
        c = _find(_index(), by, kind, target)
    return c["id"] if c else None


def start(by: str, to, text, link=None, mentions=None, r: dict | None = None) -> tuple[dict, dict]:
    """Start a conversation (or add to the existing one with the same person, department or the coordinator) and send the first
    message. Returns (Conversation as stored, Message)."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    kind, target = _target(by, rl, to)
    _clean_text(text)
    check_link(by, link, r=rl)  # refuse before anything is created
    with _lock:
        idx = _index()
        conv = _find(idx, by, kind, target)
        if conv is None:
            cid = "C" + uuid.uuid4().hex[:10]
            while cid in idx["conversations"]:
                cid = "C" + uuid.uuid4().hex[:10]
            conv = {"id": cid, "kind": kind, "created": _iso(), "created_by": by,
                    "people": [by, target] if kind == "direct" else [by], "department": target if kind == "department" else None,
                    "last_seq": 0, "last_ts": None, "last_by": None, "resolved": None}
            idx["conversations"][cid] = conv
            _save_index(idx)
            _audit("conversation_started", by, conv)
        cid = conv["id"]
    msg = send(by, cid, text, link=link, mentions=mentions, r=rl)
    with _lock:
        conv = _index()["conversations"].get(cid) or conv
    return dict(conv), msg


def _set_read(by: str, cid: str, seq: int) -> bool:
    """Move `by`'s read position forward (call with _lock). True when it moved."""
    reads = _reads()
    u = reads["users"].setdefault(by, {})
    if not isinstance(u, dict):
        u = reads["users"][by] = {}
    convs = u.setdefault("conversations", {})
    e = convs.setdefault(cid, {"seq": 0, "muted": False})
    if seq <= int(e.get("seq") or 0):
        return False
    e["seq"] = int(seq)
    _save_reads(reads)
    return True


def send(by: str, conv_id: str, text, link=None, mentions=None, r: dict | None = None) -> dict:
    """Add a message to a conversation `by` reads. A resolved conversation is reopened (audited). Returns the Message."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    conv = _conv_for(conv_id, by, rl)
    text = _clean_text(text)
    link = check_link(by, link, r=rl)
    rd = readers(conv)
    ment = _mentions(mentions, text, rd, by)
    with _lock:
        idx = _index()
        conv = _conv_for(conv_id, by, rl, idx)
        cid = conv["id"]
        ts = _iso()
        seq = _next_seq(cid)
        mid = "M" + uuid.uuid4().hex[:10]
        _append(cid, {"seq": seq, "t": "msg", "id": mid, "ts": ts, "by": by, "text": text, "link": link, "mentions": ment})
        reopened = bool(conv.get("resolved"))
        if reopened:
            _append(cid, {"seq": seq + 1, "t": "resolve", "by": by, "ts": ts, "resolved": False, "reopened_by_message": True})
            conv["resolved"] = None
        conv.update(last_seq=seq, last_ts=ts, last_by=by)
        _save_index(idx)
        _set_read(by, cid, seq)  # your own message: you have seen the conversation up to here
        msgs, _ = _fold(_events(cid))
        out = _message(msgs[mid], by, rl)
        conv = dict(conv)
    _audit("message_sent", by, conv)
    if reopened:
        _audit("conversation_reopened", by, conv)
    try:
        ids = _bell_ids(by, cid)  # the sender's own bell item of this conversation is read now
        if ids:
            from . import notify
            notify.mark_read(_roles_of(by), ids)
    except Exception as e:
        log.warning("messages: bell read failed (%s)", e.__class__.__name__)
    _after_send(conv, by, mid, rd, reopened)
    return out


def _own(cid: str, mid: str, by: str, window: bool = True) -> dict:
    """The message `mid` when `by` may change it (call with _lock)."""
    if not _MID.match(str(mid or "")):
        raise Refused(404, "not_found", "No such message.")
    msgs, _ = _fold(_events(cid))
    m = msgs.get(mid)
    if not m:
        raise Refused(404, "not_found", "No such message.")
    if m["by"] != by:
        raise Refused(403, "not_own", "You can only change your own messages.")
    if m["deleted"] or m["removed"]:
        raise Refused(400, "deleted", "This message was deleted.")
    if window:
        until = _until(m)
        if not until or _now() > until:
            raise Refused(403, "edit_window_over", EDIT_WINDOW_OVER)
    return m


def edit(by: str, conv_id: str, mid: str, text, r: dict | None = None) -> dict:
    """Change your own message within 10 minutes; the old text stays in the file ("old")."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    text = _clean_text(text)
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        m = _own(cid, mid, by)
        _append(cid, {"seq": _next_seq(cid), "t": "edit", "of": mid, "ts": _iso(), "by": by, "old": m["text"], "text": text})
        out = _message(_fold(_events(cid))[0][mid], by, rl)
    _audit("message_edited", by, conv)
    _emit_message(conv, mid, "edit")
    return out


def delete(by: str, conv_id: str, mid: str, r: dict | None = None) -> dict:
    """Delete your own message within 10 minutes: readers see a tombstone; the text stays in the file until retention removes it."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        _own(cid, mid, by)
        _append(cid, {"seq": _next_seq(cid), "t": "delete", "of": mid, "ts": _iso(), "by": by})
        out = _message(_fold(_events(cid))[0][mid], by, rl)
    _audit("message_deleted", by, conv)
    _emit_message(conv, mid, "delete")
    return out


def react(by: str, conv_id: str, mid: str, emoji, r: dict | None = None) -> dict:
    """Add one of REACTIONS (one per person per kind; adding it again changes nothing) or, with None, remove all of yours."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    if emoji == "":
        emoji = None
    if emoji is not None and emoji not in REACTIONS:
        raise Refused(400, "bad_reaction", "Choose one of the reactions.")
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        if not _MID.match(str(mid or "")):
            raise Refused(404, "not_found", "No such message.")
        m = _fold(_events(cid))[0].get(mid)
        if not m:
            raise Refused(404, "not_found", "No such message.")
        if m["deleted"] or m["removed"]:
            raise Refused(400, "deleted", "This message was deleted.")
        mine = {k for k, v in m["reactions"].items() if by in v}
        changed = (emoji is None and bool(mine)) or (emoji is not None and emoji not in mine)
        if changed:
            _append(cid, {"seq": _next_seq(cid), "t": "react", "of": mid, "by": by, "emoji": emoji, "ts": _iso()})
        out = _message(_fold(_events(cid))[0][mid], by, rl)
    if changed:
        _audit("message_reacted", by, conv)
        _emit_message(conv, mid, "react")
    return out


def resolve(by: str, conv_id: str, resolved: bool, r: dict | None = None) -> dict:
    """Mark resolved or reopen: any participant (any member of a department conversation). Returns the ConversationRow."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    resolved = bool(resolved)
    with _lock:
        idx = _index()
        conv = _conv_for(conv_id, by, rl, idx)
        cid = conv["id"]
        changed = bool(conv.get("resolved")) != resolved
        if changed:
            ts = _iso()
            _append(cid, {"seq": _next_seq(cid), "t": "resolve", "by": by, "ts": ts, "resolved": resolved})
            conv["resolved"] = {"by": by, "ts": ts} if resolved else None
            _save_index(idx)
        conv = dict(conv)
        row = _row(conv, by, rl)
    if changed:
        _audit("conversation_resolved" if resolved else "conversation_reopened", by, conv)
        state = row["resolved"]
        try:
            _emit(readers(conv), lambda u: {"type": "resolve", "conversation_id": cid, "resolved": state})
        except Exception as e:
            log.warning("messages: live resolve failed (%s)", e.__class__.__name__)
    return row


def mark_read(by: str, conv_id: str, seq, r: dict | None = None) -> int:
    """Read up to `seq` (never past the last message); the reader's bell items of this conversation are marked read. Returns the new
    unread total. The direct partner is told ("Seen")."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    try:
        seq = int(seq)
    except (TypeError, ValueError):
        raise Refused(400, "bad_seq", "A read position must be a number.")
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        upto = min(seq, _last_msg_seq(cid))
        moved = _set_read(by, cid, upto)
    try:
        ids = _bell_ids(by, cid)
        if ids:
            from . import notify
            notify.mark_read(rl if rl.get("user") == by else _roles_of(by), ids)
    except Exception as e:
        log.warning("messages: bell read failed (%s)", e.__class__.__name__)
    total = unread_total(by, r=rl)
    if moved:
        if conv.get("kind") == "direct":
            other = [p for p in conv.get("people") or [] if p != by]
            _emit(other, lambda u: {"type": "read", "conversation_id": cid, "by": by, "seq": upto})
        _emit([by], lambda u: {"type": "unread", "total": total})
    return total


def mute(by: str, conv_id: str, muted: bool, r: dict | None = None) -> dict:
    """Mute: no bell item and no push for this conversation; its unread messages still count."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        reads = _reads()
        u = reads["users"].setdefault(by, {})
        e = u.setdefault("conversations", {}).setdefault(cid, {"seq": 0, "muted": False})
        if bool(e.get("muted")) != bool(muted):
            e["muted"] = bool(muted)
            _save_reads(reads)
        return _row(conv, by, rl, reads=reads)


def list_conversations(by: str, filter: str = "all", q: str = "", r: dict | None = None) -> list[dict]:  # noqa: A002 (the contract's name)
    """The conversations `by` reads, newest first; `filter` all | unread | open | resolved; `q` matches the title (the other person or
    the department), the department name or the last preview."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    with _lock:
        idx = _index()
        reads = _reads()
        rows = [_row(c, by, rl, reads=reads) for c in idx["conversations"].values() if _is_reader(c, by, rl)]
    f = filter if filter in FILTERS else "all"
    if f == "unread":
        rows = [x for x in rows if x["unread"]]
    elif f == "open":
        rows = [x for x in rows if not x["resolved"]]
    elif f == "resolved":
        rows = [x for x in rows if x["resolved"]]
    want = " ".join(str(q or "").lower().split())
    if want:
        def hit(x):
            hay = [x["title"], (x.get("department") or {}).get("name") or "", (x.get("last") or {}).get("preview") or ""]
            return any(want in str(h).lower() for h in hay)
        rows = [x for x in rows if hit(x)]
    rows.sort(key=lambda x: str((x.get("last") or {}).get("ts") or ""), reverse=True)
    return rows


def get_conversation(by: str, conv_id: str, before: int | None = None, limit: int = PAGE_DEFAULT, r: dict | None = None) -> dict:
    """ConversationView: the last `limit` messages before `before` (oldest first), the readers, "Seen" for a direct conversation.
    Opening does not mark read."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    try:
        limit = max(1, min(PAGE_MAX, int(limit)))
    except (TypeError, ValueError):
        limit = PAGE_DEFAULT
    with _lock:
        conv = _conv_for(conv_id, by, rl)
        cid = conv["id"]
        reads = _reads()
        _, order = _fold(_events(cid))
        row = _row(conv, by, rl, reads=reads, order=order)
        seen_seq = None
        if conv.get("kind") == "direct":
            other = next((p for p in conv.get("people") or [] if p != by), None)
            e = _read_entry(reads, other, cid) if other else {}
            seen_seq = int(e["seq"]) if e.get("seq") else None
        notice = bool((reads["users"].get(by) or {}).get("notice_seen"))
    pool = [m for m in order if before is None or m["seq"] < int(before)]
    page = pool[-limit:]
    names: dict = {}
    return {"conversation": row, "messages": [_message(m, by, rl, names) for m in page], "has_more": len(pool) > len(page),
            "readers": [{"user": u, "display_name": _name(u)} for u in readers(conv)], "seen_seq": seen_seq, "notice_seen": notice}


def search(by: str, q: str, r: dict | None = None) -> list[dict]:
    """Messages of my own conversations whose text or sender name holds `q` (at least 2 characters), newest first, at most 50."""
    rl = r if r is not None else _roles_of(by)
    _need_use(rl)
    want = " ".join(str(q or "").lower().split())
    if len(want) < SEARCH_MIN:
        return []
    found = []
    names: dict = {}
    with _lock:
        idx = _index()
        reads = _reads()
        convs = [c for c in idx["conversations"].values() if _is_reader(c, by, rl)]
        for c in convs:
            for m in _fold(_events(c["id"]))[1]:
                if m["deleted"] or m["removed"]:
                    continue
                who = m.get("by") or ""
                if who not in names:
                    names[who] = _name(who)
                if want in m["text"].lower() or want in names[who].lower():
                    found.append((str(m.get("ts") or ""), m["seq"], c, m))
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    titles: dict = {}
    out = []
    for _, _, c, m in found[:SEARCH_MAX]:
        if c["id"] not in titles:
            titles[c["id"]] = _row(c, by, rl, reads=reads)["title"]
        out.append({"conversation_id": c["id"], "title": titles[c["id"]], "message": _message(m, by, rl, names)})
    return out


def unread_total(by: str, r: dict | None = None) -> int:
    """Unread messages over every conversation `by` reads (muted ones count too)."""
    rl = r if r is not None else _roles_of(by)
    if not may_use(rl):
        return 0
    total = 0
    with _lock:
        reads = _reads()
        for c in _index()["conversations"].values():
            if not _is_reader(c, by, rl):
                continue
            seen = int(_read_entry(reads, by, c["id"]).get("seq") or 0)
            if seen >= int(c.get("last_seq") or 0):  # nothing newer than my read position (the index's last message)
                continue
            total += _unread(_fold(_events(c["id"]))[1], by, seen)
    return total


def notice_seen(by: str) -> bool:
    with _lock:
        return bool((_reads()["users"].get(by) or {}).get("notice_seen"))


def set_notice_seen(by: str) -> bool:
    with _lock:
        reads = _reads()
        u = reads["users"].setdefault(by, {})
        if not u.get("notice_seen"):
            u["notice_seen"] = True
            _save_reads(reads)
    return True


def contacts(user: str) -> list[str]:
    """Everyone who shares a conversation with `user` now (presence goes to them only)."""
    rl = _roles_of(user)
    if not may_use(rl):
        return []
    out = set()
    with _lock:
        convs = [c for c in _index()["conversations"].values() if _is_reader(c, user, rl)]
    for c in convs:
        out.update(readers(c))
    out.discard(user)
    return sorted(out)


def typing(by: str, conv_id: str, r: dict | None = None) -> bool:
    """Tell the other readers that `by` is typing; dropped (False) unless `by` reads the conversation. The throttle is the socket's."""
    rl = r if r is not None else _roles_of(by)
    if not may_use(rl):
        return False
    try:
        with _lock:
            conv = _conv_for(conv_id, by, rl)
    except Refused:
        return False
    name = _name(by)
    _emit([u for u in readers(conv) if u != by], lambda u: {"type": "typing", "conversation_id": conv["id"], "by": by, "by_name": name})
    return True


# ---- retention ----------------------------------------------------------------------------------------------------------------------

def retention(days: int | None = None, now: datetime | None = None) -> int:
    """Remove the text (and the old text of edits) of conversations whose last message is older than `days` (default: the hospital's
    message_retention_days; 0 keeps everything). The events stay, marked "removed". Returns how many conversations were touched."""
    if days is None:
        try:
            days = org.hospital().get("message_retention_days", 365)
        except Exception:
            days = 365
    try:
        days = int(days if days is not None else 365)
    except (TypeError, ValueError):
        days = 365
    if days <= 0:
        return 0
    now = now or _now()
    if now.tzinfo:
        now = now.replace(tzinfo=None)
    cutoff = now - timedelta(days=days)
    touched = 0
    with _lock:
        for cid, conv in _index()["conversations"].items():
            last = _parse(conv.get("last_ts") or conv.get("created"))
            if last is None or last >= cutoff:
                continue
            changed, new = False, []
            for ev in _events(cid):
                ev = dict(ev)
                if ev.get("t") in ("msg", "edit") and not ev.get("removed"):
                    ev["text"] = ""
                    if "old" in ev:
                        ev["old"] = ""
                    ev["removed"] = True
                    changed = True
                new.append(ev)
            if changed:
                _rewrite(cid, new)
                touched += 1
    return touched


def job(now: datetime) -> dict:
    """The scheduler's messages_retention job (every 24 hours, in the scheduler thread)."""
    return {"conversations": retention(now=now)}
