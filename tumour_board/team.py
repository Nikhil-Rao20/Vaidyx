"""The Case File team, its urgency tag, archive, consent and break-glass (18 Oct 2026, new interface).

Stored on case.json:
  "urgency"  {"level": 1..5, "set_by", "at", "note"}: set by the owning department's consultant (a resident proposes, proposals.py);
             5 is the most urgent. Urgency is a person's call: Vaidyx never sets or suggests it.
  "team"     {"residents": [{"user", "added_by", "since", "end_date", "removed": {"by", "at", "reason"} | absent}],
              "join_code": {"code" (6 digits), "created_by", "created_at", "expires", "uses"} | absent,
              "pending": [{"user", "requested_at", "department", "role" ("resident" | "consultant"), "note"?, "how"?}],
              "members": [{"user", "department", "role": "consultant", "added_by", "added_at", "removed"?}]}: the residents on the
             Case File (full read scope, upload, ask, propose), the join code the owner hands out (7 days), the join requests waiting
             for the owner's approval (a resident with the code, or any doctor through "Ask to join" from the New Case File page, night-v3
             item 1.1) and the consultants of other departments the owner let in (they read the whole Case File; the owner's rights stay
             with the owning department's consultants, access.py).
  "archived" {"by", "at", "reason"}: archived instead of deleted; every change is refused until it is taken back (access.py).
  "consent"  {"outside_discussion": bool, "note", "by", "at"}: whether the patient agreed to an outside expert seeing the Case File
             in a meeting (without it an outside expert sees initials, age and sex only: meetings.py).

Every change is audited in the Case File; the people concerned are told in-app (notify). No model calls."""
import hmac, secrets
from datetime import date, datetime, timedelta

from . import access, config, notify, org, profiles, store

URGENCY_LEVELS = (1, 2, 3, 4, 5)
URGENCY_LABELS = {1: "Not urgent", 2: "Routine", 3: "Soon", 4: "Urgent", 5: "Most urgent"}
CODE_DAYS = 7
CODE_DIGITS = 6
MAX_NOTE = 500
# in-app notification kinds this module and proposals.py use; registered here when notify.py does not list them yet (push.py adds
# the same names to notify.KINDS; the registration is then a no-op)
KINDS = ("sign_off", "join_request", "team_changed", "break_glass")


def _register_kinds():
    missing = tuple(k for k in KINDS if k not in notify.KINDS)
    if missing:
        notify.KINDS = tuple(notify.KINDS) + missing


_register_kinds()


class TeamError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers, `code` a short word the interface may act on."""

    def __init__(self, message, status=400, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


def _case(case_id: str) -> dict:
    c = store.get_case(case_id)
    if not c:
        raise TeamError("Case not found", 404, "not_found")
    return c


def _note(s, limit=MAX_NOTE) -> str:
    return " ".join(str(s or "").split())[:limit]


def _tell(to: dict, kind: str, case_id: str, title: str, text: str = "", **extra):
    try:
        return notify.notify(to, kind, case_id, title, text, **extra)
    except Exception as e:  # a notice never fails the change
        return {"error": f"{e.__class__.__name__}: {e}"}


def patient_line(case: dict) -> str:
    """Name, age / sex and UHID on one line (what a notification or a home row shows)."""
    p = (case or {}).get("patient") or {}
    parts = [p.get("name") or "name not recorded"]
    if p.get("agesex"):
        parts.append(str(p["agesex"]))
    if p.get("mrn"):
        parts.append(f"UHID {p['mrn']}")
    return ", ".join(parts)


def owner_consultants(case: dict) -> list[str]:
    """The logins of the owning department's consultants (member or head, not disabled); empty for a Case File without an owner."""
    own = access.owner(case)
    if not own:
        return []
    out = []
    for u, v in sorted((org.load().get("users") or {}).items()):
        if isinstance(v, dict) and (v.get("departments") or {}).get(own) in org.DEPT_ROLES and not v.get("disabled"):
            out.append(u)
    return out


def tell_consultants(case: dict, kind: str, title: str, text: str = "", **extra) -> list:
    """One notification per consultant of the owning department (the whole department when nobody is placed as a consultant yet)."""
    us = owner_consultants(case)
    if not us:
        own = access.owner(case)
        return [_tell({"department": own}, kind, case["case_id"], title, text, **extra)] if own else []
    return [_tell({"user": u}, kind, case["case_id"], title, text, **extra) for u in us]


# ---- urgency --------------------------------------------------------------------------------------------------------------------

def check_level(level) -> int:
    try:
        lv = int(level)
    except (TypeError, ValueError):
        raise TeamError("Urgency is a number from 1 to 5 (5 is the most urgent).", 400, "bad_level")
    if lv not in URGENCY_LEVELS:
        raise TeamError("Urgency is a number from 1 to 5 (5 is the most urgent).", 400, "bad_level")
    return lv


def set_urgency(case_id: str, level, user: str, note: str = "") -> dict:
    """The owner's consultant sets the tag (the route checks the role; a resident's call becomes a proposal). Audited with the value before."""
    lv = check_level(level)
    c = _case(case_id)
    access.check_not_archived(c)
    before = c.get("urgency") if isinstance(c.get("urgency"), dict) else None
    rec = {"level": lv, "set_by": user, "at": store.now_iso(), "note": _note(note)}
    c["urgency"] = rec
    c.setdefault("urgency_history", []).append(rec)
    store.save_case(c)
    store.audit(case_id, {"kind": "urgency_set", "by": user, "level": lv, "before": (before or {}).get("level"), "note": rec["note"]})
    return urgency_view(c)


def urgency_view(case: dict) -> dict | None:
    """{level, label, set_by, set_by_name, at, note, proposed} or None when nobody set it; `proposed` is a resident's pending proposal."""
    u = case.get("urgency") if isinstance(case.get("urgency"), dict) else None
    from . import proposals
    pend = next((p for p in reversed(proposals.list_(case)) if p.get("action") == "urgency" and p.get("status") == proposals.PENDING), None)
    proposed = {"level": (pend.get("payload") or {}).get("level"), "by": pend.get("by"), "by_name": pend.get("by_name"), "at": pend.get("at"), "id": pend.get("id")} if pend else None
    if not u:
        return {"level": None, "label": "", "set_by": "", "set_by_name": "", "at": "", "note": "", "proposed": proposed} if proposed else None
    return {"level": u.get("level"), "label": URGENCY_LABELS.get(u.get("level"), ""), "set_by": u.get("set_by") or "", "set_by_name": profiles.display_name(u.get("set_by") or ""),
            "at": u.get("at") or "", "note": u.get("note") or "", "proposed": proposed}


# ---- the team -------------------------------------------------------------------------------------------------------------------

def _team(case: dict) -> dict:
    t = case.get("team") if isinstance(case.get("team"), dict) else {}
    t.setdefault("residents", [])
    t.setdefault("pending", [])
    t.setdefault("members", [])
    case["team"] = t
    return t


def _active_code(t: dict) -> dict | None:
    jc = t.get("join_code")
    if not isinstance(jc, dict) or not jc.get("code"):
        return None
    try:
        if datetime.fromisoformat(str(jc.get("expires"))) <= datetime.now():
            return None
    except (TypeError, ValueError):
        return None
    return jc


def view(case: dict, show_code: bool = False) -> dict:
    """The team panel: the owner with its consultants, the residents (with end dates), the participating departments, the join code
    (its value only for those who may manage the team) and the join requests waiting."""
    own = access.owner(case)
    t = _team(dict(case))
    jc = _active_code(t)
    today = date.today().isoformat()
    return {"owner": {"department": own, "department_label": org.department_name(own) if own else "",
                      "doctors": [{"user": u, "name": profiles.display_name(u)} for u in owner_consultants(case)]},
            "residents": [{"user": x.get("user"), "name": profiles.display_name(x.get("user")), "end_date": x.get("end_date") or "", "added_by": x.get("added_by") or "",
                           "since": x.get("since") or "", "expired": bool(x.get("end_date")) and str(x["end_date"])[:10] < today}
                          for x in t["residents"] if isinstance(x, dict) and x.get("user") and not x.get("removed")],
            "members": [{"user": x.get("user"), "name": profiles.display_name(x.get("user")), "role": x.get("role") or "consultant", "department": x.get("department") or "",
                         "department_label": org.department_name(x.get("department")) if x.get("department") else "", "added_by": x.get("added_by") or "",
                         "added_at": x.get("added_at") or ""} for x in access.team_members(case)],
            "departments": [{"id": org.department_id(p.get("department")), "label": org.department_name(org.department_id(p.get("department"))), "since": p.get("since") or ""}
                            for p in case.get("participants") or [] if isinstance(p, dict) and org.department_id(p.get("department"))],
            "join_code": ({"code": jc["code"] if show_code else "", "expires_at": jc.get("expires"), "uses": int(jc.get("uses") or 0)} if jc else None),
            "pending": [{"user": x.get("user"), "name": profiles.display_name(x.get("user")), "requested_at": x.get("requested_at") or "",
                         "department": x.get("department") or "", "department_label": org.department_name(x.get("department")) if x.get("department") else "",
                         "role": x.get("role") or "resident", "note": x.get("note") or ""}
                        for x in t["pending"] if isinstance(x, dict) and x.get("user")],
            "archived": dict(case["archived"]) if access.is_archived(case) else None,
            "consent": dict(case["consent"]) if isinstance(case.get("consent"), dict) else None}


def new_code(case_id: str, user: str) -> dict:
    """A fresh 6-digit join code (secrets), good for 7 days; it replaces the old one. Audited (never with the code itself)."""
    c = _case(case_id)
    access.check_not_archived(c)
    t = _team(c)
    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    expires = (datetime.now() + timedelta(days=CODE_DAYS)).isoformat(timespec="seconds")
    t["join_code"] = {"code": code, "created_by": user, "created_at": store.now_iso(), "expires": expires, "uses": 0}
    store.save_case(c)
    store.audit(case_id, {"kind": "join_code_created", "by": user, "expires": expires, "replaced": bool(_active_code({"join_code": t.get("join_code")}))})
    return {"code": code, "expires_at": expires}


def clear_code(case_id: str, user: str) -> bool:
    c = _case(case_id)
    t = _team(c)
    had = bool(t.pop("join_code", None))
    if had:
        store.save_case(c)
        store.audit(case_id, {"kind": "join_code_cleared", "by": user})
    return had


def _check_code(code) -> str:
    s = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(s) != CODE_DIGITS:
        raise TeamError(f"The join code has {CODE_DIGITS} digits.", 400, "bad_code")
    return s


def find_by_code(code: str) -> dict | None:
    """The Case File whose unexpired join code matches (compared in constant time), or None."""
    want = _check_code(code)
    base = config.CASES_DIR
    if not base.exists():
        return None
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name in config.PROTECTED_CASES:
            continue
        try:
            c = store.get_case(d.name)
        except (ValueError, OSError):
            continue
        if not isinstance(c, dict):
            continue
        jc = _active_code(_team(dict(c)))
        if jc and hmac.compare_digest(str(jc["code"]), want):
            return c
    return None


def on_team(case: dict, user: str) -> bool:
    """A resident or a consultant member on this Case File's team."""
    return any(x.get("user") == user for x in access.team_residents(case)) or any(x.get("user") == user for x in access.team_members(case))


def ask_to_join(case_id: str, roles: dict, user: str, note: str = "") -> dict:
    """"Ask to join" without a code (night-v3 item 1.1): a placed doctor (a consultant or a resident of any department) who cannot open
    this Case File asks its owner; the request waits in the team's pending list with the asker's role and department, is audited
    (join_requested) and the owner's consultants are told (join_request). Someone who can open it already: 409 can_open."""
    r = roles if isinstance(roles, dict) else {}
    if r.get("disabled") or r.get("expired") or not r.get("known") or r.get("vaidyx_admin"):
        raise TeamError("Only a doctor placed in a department asks to join a Case File.", 403, "not_placed")
    consultant_of = [d for d in (r.get("departments") or {}) if d not in (r.get("resident") or {})]
    resident_of = list(r.get("resident") or {})
    if not consultant_of and not resident_of:
        raise TeamError("Only a doctor placed in a department asks to join a Case File.", 403, "not_placed")
    c = store.get_case(case_id) if case_id else None
    if not c or access.is_protected(c):  # a protected Case File is never named to anyone else (security review finding 0)
        raise TeamError("Case not found", 404, "not_found")
    if access.is_archived(c):
        raise TeamError(access.ARCHIVED_MESSAGE + ": nobody joins it until it is taken out of the archive.", 409, "archived")
    if access.scope(r, c) == access.FULL:
        raise TeamError("You can open this Case File.", 409, "can_open")
    t = _team(c)
    if any(x.get("user") == user for x in t["pending"]):
        return {"status": "pending", "case_id": case_id, "already": True}
    role = "consultant" if consultant_of else "resident"
    dept = (consultant_of or resident_of)[0]
    rec = {"user": user, "requested_at": store.now_iso(), "department": dept, "role": role, "how": "ask"}
    if _note(note):
        rec["note"] = _note(note)
    t["pending"].append(rec)
    store.save_case(c)
    store.audit(case_id, {"kind": "join_requested", "by": user, "department": dept, "role": role, "how": "ask", **({"note": rec["note"]} if rec.get("note") else {})})
    name = profiles.display_name(user)
    tell_consultants(c, "join_request", f"{name} asks to join the team of {patient_line(c)} ({case_id})",
                     f"{name} ({org.department_name(dept)}, {role}) asked to join from the New Case File page."
                     + (f" Note: {rec['note']}" if rec.get("note") else "") + " Approve or reject the request from the Team panel.", user=user, by=user)
    return {"status": "pending", "case_id": case_id}


def join(code: str, roles: dict, user: str) -> dict:
    """A resident joins with the code: a resident of the owning department joins at once, another department's resident waits for the
    owner's approval (the consultants are told). Wrong or expired code: 404 no_such_code (the route rate-limits the tries)."""
    if not isinstance(roles, dict) or roles.get("disabled") or roles.get("expired") or not roles.get("resident"):
        raise TeamError("Only a resident placed in a department joins a Case File team with a code.", 403, "not_resident")
    c = find_by_code(code)
    if not c:
        raise TeamError("No Case File has this join code; check the digits or ask the treating doctor for a new code.", 404, "no_such_code")
    case_id = c["case_id"]
    access.check_not_archived(c)
    t = _team(c)
    line = patient_line(c)
    if on_team(c, user):
        return {"status": "joined", "case_id": case_id, "patient_line": line, "already": True}
    t["join_code"]["uses"] = int(t["join_code"].get("uses") or 0) + 1
    now = store.now_iso()
    own = access.owner(c)
    dept = next(iter(roles.get("resident") or {}), "")
    removed = access.removed_from_team(c, user)  # taken off this team before: the owner decides again
    if not removed and (not own or own in (roles.get("resident") or {})):  # the owning department's resident (or no owner): joins at once
        if own:
            dept = own
        t["residents"] = [x for x in t["residents"] if x.get("user") != user] + [{"user": user, "added_by": "join code", "since": now,
                                                                                    "end_date": roles.get("end_date") or "", "department": dept}]
        store.save_case(c)
        store.audit(case_id, {"kind": "resident_joined", "by": user, "department": dept, "how": "join code"})
        if own:
            name = profiles.display_name(user)
            tell_consultants(c, "team_changed", f"{name} joined the team of {line} ({case_id})", f"{name} used the join code.", user=user, by=user)
        return {"status": "joined", "case_id": case_id, "patient_line": line}
    if any(x.get("user") == user for x in t["pending"]):
        store.save_case(c)
        return {"status": "pending", "case_id": case_id, "patient_line": line, "already": True}
    t["pending"].append({"user": user, "requested_at": now, "department": dept})
    store.save_case(c)
    store.audit(case_id, {"kind": "join_requested", "by": user, "department": dept})
    name = profiles.display_name(user)
    tell_consultants(c, "join_request", f"{name} asks to join the team of {line} ({case_id})",
                     f"{name} ({org.department_name(dept)}) used the join code. Approve or reject the request from the Team panel.", user=user, by=user)
    return {"status": "pending", "case_id": case_id, "patient_line": line}


def _pop_pending(t: dict, user: str) -> dict:
    p = next((x for x in t["pending"] if x.get("user") == user), None)
    if not p:
        raise TeamError("No join request from this person is waiting.", 404, "not_pending")
    t["pending"] = [x for x in t["pending"] if x.get("user") != user]
    return p


def approve_pending(case_id: str, user: str, by: str, note: str = "") -> dict:
    c = _case(case_id)
    access.check_not_archived(c)
    t = _team(c)
    p = _pop_pending(t, user)
    r = org.roles(user)
    if p.get("role") == "consultant":  # a consultant of another department (Ask to join): reads the whole Case File, never the owner's rights
        rec = {"user": user, "department": p.get("department") or "", "role": "consultant", "added_by": by, "added_at": store.now_iso()}
        t["members"] = [x for x in t["members"] if x.get("user") != user] + [rec]
        store.save_case(c)
        store.audit(case_id, {"kind": "member_approved", "by": by, "user": user, "department": rec["department"], "note": _note(note)})
    else:
        rec = {"user": user, "added_by": by, "since": store.now_iso(), "end_date": r.get("end_date") or "", "department": p.get("department") or ""}
        t["residents"] = [x for x in t["residents"] if x.get("user") != user] + [rec]
        store.save_case(c)
        store.audit(case_id, {"kind": "resident_approved", "by": by, "user": user, "note": _note(note)})
    _tell({"user": user}, "team_changed", case_id, f"You are on the team of {patient_line(c)} ({case_id})",
          f"{profiles.display_name(by)} approved your request." + (f" Note: {_note(note)}" if note else ""), status="approved", by=by)
    return rec


def reject_pending(case_id: str, user: str, by: str, note: str = "") -> dict:
    c = _case(case_id)
    t = _team(c)
    p = _pop_pending(t, user)
    store.save_case(c)
    store.audit(case_id, {"kind": "join_rejected", "by": by, "user": user, "note": _note(note)})
    _tell({"user": user}, "team_changed", case_id, f"Your request to join the team of {patient_line(c)} ({case_id}) was not approved",
          f"{profiles.display_name(by)} did not approve the request." + (f" Note: {_note(note)}" if note else ""), status="rejected", by=by)
    return p


def add_resident(case_id: str, user: str, by: str, end_date: str = "") -> dict:
    """The owner adds a resident by login (no code); the person must hold a resident placement."""
    c = _case(case_id)
    access.check_not_archived(c)
    r = org.roles(user)
    if not r.get("resident") or r.get("disabled"):
        raise TeamError(f"'{user}' is not placed as a resident.", 409, "not_resident")
    ed = str(end_date or r.get("end_date") or "")[:10]
    if ed:
        try:
            date.fromisoformat(ed)
        except ValueError:
            raise TeamError("The end date must be a date (YYYY-MM-DD).", 400, "bad_date")
    t = _team(c)
    rec = {"user": user, "added_by": by, "since": store.now_iso(), "end_date": ed, "department": next(iter(r["resident"]), "")}
    t["residents"] = [x for x in t["residents"] if x.get("user") != user] + [rec]
    t["pending"] = [x for x in t["pending"] if x.get("user") != user]
    store.save_case(c)
    store.audit(case_id, {"kind": "resident_added", "by": by, "user": user, "end_date": ed})
    _tell({"user": user}, "team_changed", case_id, f"You are on the team of {patient_line(c)} ({case_id})", f"Added by {profiles.display_name(by)}.", status="added", by=by)
    return rec


def remove_resident(case_id: str, user: str, by: str, reason: str = "") -> dict:
    """The owner, a department admin or the resident itself takes the resident off the team; the removed resident loses access."""
    c = _case(case_id)
    t = _team(c)
    m = next((x for x in t["members"] if x.get("user") == user and not x.get("removed")), None)
    if m:  # a consultant member (Ask to join) leaves or is taken off the team the same way
        m["removed"] = {"by": by, "at": store.now_iso(), "reason": _note(reason)}
        store.save_case(c)
        store.audit(case_id, {"kind": "member_removed", "by": by, "user": user, "reason": m["removed"]["reason"]})
        if by != user:
            _tell({"user": user}, "team_changed", case_id, f"You are no longer on the team of {patient_line(c)} ({case_id})",
                  f"Removed by {profiles.display_name(by)}." + (f" Reason: {m['removed']['reason']}" if reason else ""), status="removed", by=by)
        return m
    x = next((x for x in t["residents"] if x.get("user") == user and not x.get("removed")), None)
    if not x:
        own = access.owner(c)
        if own and own in (org.roles(user).get("resident") or {}) and not access.removed_from_team(c, user):  # the owning department's resident reads every Case File of it: taken off this one
            x = {"user": user, "added_by": "department", "since": "", "end_date": org.roles(user).get("end_date") or "", "department": own}
            t["residents"] = [y for y in t["residents"] if y.get("user") != user] + [x]
        else:
            raise TeamError("This person is not on the team.", 404, "not_on_team")
    x["removed"] = {"by": by, "at": store.now_iso(), "reason": _note(reason)}
    store.save_case(c)
    store.audit(case_id, {"kind": "resident_removed", "by": by, "user": user, "reason": x["removed"]["reason"]})
    if by != user:
        _tell({"user": user}, "team_changed", case_id, f"You are no longer on the team of {patient_line(c)} ({case_id})",
              f"Removed by {profiles.display_name(by)}." + (f" Reason: {x['removed']['reason']}" if reason else ""), status="removed", by=by)
    return x


# ---- archive and consent --------------------------------------------------------------------------------------------------------

def archive(case_id: str, by: str, reason: str) -> dict:
    c = _case(case_id)
    if access.is_archived(c):
        raise TeamError(access.ARCHIVED_MESSAGE + " already.", 409, "archived")
    reason = _note(reason)
    if not reason:
        raise TeamError("Give the reason for archiving this Case File.", 400, "reason_required")
    c["archived"] = {"by": by, "at": store.now_iso(), "reason": reason}
    was_ready = c.pop("board_ready", None)
    if was_ready:  # an archived Case File is not ready for any board: the mark goes, with a line in its history
        c.setdefault("board_ready_history", []).append({"ready": False, "by": by, "at": c["archived"]["at"], "note": "archived"})
    store.save_case(c)
    store.audit(case_id, {"kind": "case_archived", "by": by, "reason": reason, "ready_mark_removed": bool(was_ready)})
    return c


def unarchive(case_id: str, by: str, note: str = "") -> dict:
    c = _case(case_id)
    if not access.is_archived(c):
        raise TeamError("This Case File is not archived.", 409, "not_archived")
    before = c.pop("archived")
    c.setdefault("archive_history", []).append({**before, "unarchived_by": by, "unarchived_at": store.now_iso(), "note": _note(note)})
    store.save_case(c)
    store.audit(case_id, {"kind": "case_unarchived", "by": by, "note": _note(note), "archived_by": before.get("by"), "archived_at": before.get("at")})
    return c


def set_consent(case_id: str, by: str, outside_discussion, note: str = "") -> dict:
    if not isinstance(outside_discussion, bool):
        raise TeamError("outside_discussion must be true or false.", 400, "bad_value")
    c = _case(case_id)
    access.check_not_archived(c)
    rec = {"outside_discussion": outside_discussion, "note": _note(note), "by": by, "at": store.now_iso()}
    before = c.get("consent") if isinstance(c.get("consent"), dict) else None
    c["consent"] = rec
    store.save_case(c)
    store.audit(case_id, {"kind": "consent_set", "by": by, "outside_discussion": outside_discussion, "before": (before or {}).get("outside_discussion"), "note": rec["note"]})
    return rec


# ---- break-glass ----------------------------------------------------------------------------------------------------------------

def break_glass(user: str, case_id: str, reason: str, hours=None) -> dict:
    """The Vaidyx admin's window on one Case File (access.open_break_glass); the owning department's consultants are told."""
    c = _case(case_id)
    w = access.open_break_glass(user, case_id, reason, hours)
    tell_consultants(c, "break_glass", f"Break-glass: {user} opened the Case File of {patient_line(c)} ({case_id})",
                     f"The Vaidyx admin {user} opened this Case File until {w['until'][:16].replace('T', ' ')}. Reason: {w['reason']}", user=user, until=w["until"], by=user)
    return w


def _dmy_hm(iso: str) -> str:
    """2026-10-28T14:05:00 as 28/10/2026 14:05."""
    try:
        d = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return str(iso or "")[:16].replace("T", " ")
    return d.strftime("%d/%m/%Y %H:%M")


def break_glass_doctor(user: str, roles: dict, case_id: str, reason: str, via: str = "") -> dict:
    """A doctor without access opens one Case File read-only with a reason (owner decision D8, night-v3 item 1.9): 24 hours, audited in
    the Case File and the organisation log, the owning department's consultants told. A protected or unknown Case File answers 404
    (never named); a person who can open it already 409 `can_open`; anyone but a placed consultant or resident 403 `not_placed`. A new
    opening of the same Case File renews the window. `via` is a short tag of where the doctor came from (Phase 7: "similar to TB-xxx")."""
    c = store.get_case(case_id)
    if not c or access.is_protected(c):
        raise TeamError("Case not found", 404, "not_found")
    sc = access.scope(roles, c)
    if sc is not None and sc != access.READ:
        raise TeamError("You can open this Case File already.", 409, "can_open")
    if not access.may_open_with_reason(roles, c):
        raise TeamError("Only a doctor placed in a department (a consultant or a resident) opens a Case File with a reason.", 403, "not_placed")
    try:
        w = access.open_doctor_window(user, case_id, reason, via)
    except access.AccessError as e:
        raise TeamError(str(e), e.status, e.code or "bad_reason")
    store.audit(case_id, {"kind": "break_glass_doctor", "by": user, "reason": w["reason"], "via": w["via"], "until": w["until"],
                          "window": w["id"], "renewed": w["renewed"]})
    org.audit("break_glass_doctor", user, case_id=case_id, reason=w["reason"], via=w["via"], until=w["until"])
    name = profiles.display_name(user)
    tell_consultants(c, "break_glass", f"Opened with a reason: {name} opened the Case File of {patient_line(c)} ({case_id})",
                     f"{name} reads this Case File read-only until {_dmy_hm(w['until'])}. Reason: {w['reason']}"
                     + (f" ({w['via']})" if w["via"] else ""), user=user, until=w["until"], by=user, via=w["via"], read_only=True)
    return w


def close_break_glass_doctor(user: str, case_id: str) -> dict:
    """The doctor closes its own window on a Case File (audited, access.close_doctor_window); 404 `no_window` when none is open."""
    w = access.close_doctor_window(user, case_id, by=user)
    if not w:
        raise TeamError("You have no open window on this Case File.", 404, "no_window")
    return w
