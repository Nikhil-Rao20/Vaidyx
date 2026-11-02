"""The people and departments directory (night-v3 item 8.3, contract docs/night-v3/research/06_messages.md section 9.6).

Who is listed: every login of org.json that may use Messages (messages.may_use: placed in a department and not disabled or expired, or
the MDT Coordinator). Disabled, expired and unplaced accounts (root admin, auditor, outside expert, a department admin without a
placement, the Vaidyx admin) are not listed.

What is shown of a person: the login, the display name, the title, the departments with the role in each (Head, Consultant, Resident),
the MDT Coordinator badge, the presence state, a link to the photo (never the photo itself inside a list) and the mobile number only
when the person chose to show it. Never the registration number, the e-mail, the password or any admin flag.

Reading only: nothing here writes a file. No model calls."""
from __future__ import annotations

import base64, re
from urllib.parse import quote

from . import messages, org, profiles

MAX_PEOPLE = 30
ROLE_LABELS = {"head": "Head", "member": "Consultant", "resident": "Resident"}
_ROLE_ORDER = {"head": 0, "member": 1, "resident": 2}
_WORD = re.compile(r"[^\w]+", re.UNICODE)
_MEDIA = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


def photo_url(user: str) -> str:
    return f"/api/tb/directory/{quote(str(user), safe='')}/photo"


def _words(text) -> list[str]:
    return [w for w in _WORD.split(str(text or "").casefold()) if w]


def _matches(query_words: list[str], haystack: list[str]) -> bool:
    """Every word of the query is the start of some word of the name, the title or a department name (case insensitive)."""
    return all(any(h.startswith(q) for h in haystack) for q in query_words)


def _stored_profiles() -> dict:
    """profiles.json read once per call (a list of people would otherwise read the file, photos and all, once per person)."""
    try:
        d = profiles._load()
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _photo(stored: dict):
    """(bytes, media type) of a stored photo data URL, or None when there is none or it cannot be read."""
    photo = str((stored or {}).get("photo") or "").strip()
    m = profiles._PHOTO.match(photo) if photo else None
    if not m:
        return None
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
    except (ValueError, TypeError):
        return None
    return (raw, _MEDIA[m.group(1)]) if raw else None


def _placed_logins() -> list[tuple[str, dict]]:
    """(login, roles) for every login of org.json that may use Messages."""
    out = []
    for login in (org.load().get("users") or {}):
        if not isinstance(login, str) or not login.strip():
            continue
        try:
            r = org.roles(login)
        except Exception:
            continue
        if messages.may_use(r):
            out.append((login, r))
    return out


def _person(login: str, r: dict, stored: dict) -> dict:
    p = stored.get(login) if isinstance(stored.get(login), dict) else {}
    name = str(p.get("display_name") or "").strip() or org.display_name(login) or login
    phone = str(p.get("phone") or "").strip()
    depts = sorted(((d, role) for d, role in (r.get("departments") or {}).items()),
                   key=lambda x: (_ROLE_ORDER.get(x[1], 9), org.department_name(x[0]).casefold()))
    return {"user": login, "display_name": name, "title": str(p.get("title") or "").strip(),
            "departments": [{"id": d, "name": org.department_name(d), "role": ROLE_LABELS.get(role, "Consultant")} for d, role in depts],
            "coordinator": bool(r.get("coordinator")), "online": messages.presence(login),
            "photo": photo_url(login) if _photo(p) else None,
            "phone": phone if (p.get("phone_visible") is True and phone) else None}


def _haystack(person: dict) -> list[str]:
    words = _words(person["display_name"]) + _words(person["title"])
    for d in person["departments"]:
        words += _words(d["name"])
    if person["coordinator"]:
        words += _words(org.COORDINATOR_NAME)
    return words


def _sorted(people: list[dict]) -> list[dict]:
    return sorted(people, key=lambda x: (x["display_name"].casefold(), x["user"]))


def _department_id(department) -> str | None:
    d = str(department or "").strip()
    if not d:
        return None
    found = org.department(d)  # an id, or a name or alias that resolves to one
    return found.get("id") if found else None


def people(q: str = "", department=None) -> list[dict]:
    """The people who may use Messages, sorted by display name: `q` keeps those where every word of it starts a word of the name, the
    title or a department name (case insensitive); `department` (an id) keeps those placed in it. At most MAX_PEOPLE."""
    stored = _stored_profiles()
    want_dept = None
    if department not in (None, ""):
        want_dept = _department_id(department)
        if not want_dept:
            return []
    qw = _words(q)
    out = []
    for login, r in _placed_logins():
        if want_dept and want_dept not in (r.get("departments") or {}):
            continue
        person = _person(login, r, stored)
        if qw and not _matches(qw, _haystack(person)):
            continue
        out.append(person)
    return _sorted(out)[:MAX_PEOPLE]


def coordinators() -> list[dict]:
    """Every MDT Coordinator who may use Messages (so "Message the MDT Coordinator" always has someone to reach)."""
    stored = _stored_profiles()
    return _sorted([_person(login, r, stored) for login, r in _placed_logins() if r.get("coordinator")])


def departments(q: str = "") -> list[dict]:
    """The departments with at least one member who may use Messages: [{id, name, group, members}], sorted by name. `q` (optional)
    keeps those whose name has a word starting with each word of it."""
    counts: dict[str, int] = {}
    for _login, r in _placed_logins():
        for d in r.get("departments") or {}:
            counts[d] = counts.get(d, 0) + 1
    qw = _words(q)
    out = []
    for d in org.departments():
        did = d.get("id")
        if not did or not counts.get(did):
            continue
        name = str(d.get("name") or did)
        if qw and not _matches(qw, _words(name)):
            continue
        out.append({"id": did, "name": name, "group": d.get("group") if d.get("group") in ("treating", "supporting") else "supporting",
                    "members": counts[did]})
    return sorted(out, key=lambda x: x["name"].casefold())


def photo(user: str):
    """(bytes, media type) of this person's photo when the person may use Messages and has one, else None."""
    u = str(user or "").strip()
    if not u or u not in (org.load().get("users") or {}):
        return None
    try:
        if not messages.may_use(org.roles(u)):
            return None
    except Exception:
        return None
    stored = _stored_profiles().get(u)
    return _photo(stored) if isinstance(stored, dict) else None
