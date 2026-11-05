"""The profile of each person who signs in (18 Oct 2026, new interface): data/tumour_board/profiles.json {username: {...}}.

A profile holds what the person chose at first login and later in Settings: display name and title, registration number (doctors),
mobile number with the consent to show it to signed-in hospital members, a small photo (a data URL, at most 200 KB), theme, text size,
start page and the saved filters of the home list. The roles stay in org.json (org.roles); the display name is mirrored there when the
person is placed, so the old screens show the same name. A profile is "set up" once the display name is there (and, for a doctor, the
registration number). Every change is recorded in org_audit.jsonl by field name, never by value (the phone and the photo are personal).
No model calls."""
import base64, json, os, re, threading
from pathlib import Path

from . import config, org
from .store import now_iso

FIELDS = ("display_name", "title", "registration_no", "phone", "phone_visible", "photo", "theme", "text_size", "start_page", "saved_filters")
THEMES = ("system", "light", "dark")
TEXT_SIZES = ("small", "normal", "large")
START_PAGES = ("home", "cases", "last_case", "meetings", "requests", "admin")
PHOTO_MAX_BYTES = 200 * 1024
MAX_FILTERS = 20
MAX_FILTER_CHARS = 4000
_PHOTO = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")
_PHONE = re.compile(r"^\+?[0-9][0-9 \-]{6,19}$")
_REG = re.compile(r"^[A-Za-z0-9 /.\-]{2,40}$")
_lock = threading.Lock()


def path() -> Path:
    return Path(config.DATA_ROOT) / "profiles.json"


def _load() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save(d: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


def blank() -> dict:
    return {"display_name": "", "title": "", "registration_no": "", "phone": "", "phone_visible": False, "photo": "", "theme": "system",
            "text_size": "normal", "start_page": "home", "saved_filters": [], "setup_complete": False, "updated": ""}


def get(username: str) -> dict:
    """The profile with every field present; the display name falls back to the one in org.json."""
    u = str(username or "")
    out = {**blank(), **{k: v for k, v in (_load().get(u) or {}).items() if k in FIELDS or k in ("setup_complete", "updated")}}
    if not out["display_name"]:
        out["display_name"] = org.display_name(u) if u else ""
        if out["display_name"] == u:
            out["display_name"] = ""
    return out


def is_doctor(r: dict) -> bool:
    """Whether the registration number is part of the set-up: anyone placed in a department (consultant or resident). A guest reviewer
    (real_data) may leave it empty: an outside reviewer may have none (Eswar, 5 Nov 2026)."""
    return bool((r or {}).get("departments")) and not (r or {}).get("real_data")


def _complete(p: dict, doctor: bool) -> bool:
    return bool(str(p.get("display_name") or "").strip()) and (bool(str(p.get("registration_no") or "").strip()) or not doctor)


def name_ok(name: str) -> bool:
    """A display name the screens show as it is (security review #19): 2 to 80 characters of letters (any script, with its vowel
    signs), spaces, dots, apostrophes, hyphens and round brackets; no digits, other brackets or markup. Round brackets are allowed
    because a department admin's placement accepts them ("Dr Meera (demo)") and such a login was stuck at its first set-up (owner,
    2 Nov 2026)."""
    import unicodedata
    v = str(name or "")
    if not 2 <= len(v) <= 80:
        return False
    return all(ch in " .'-\u2019()" or unicodedata.category(ch)[0] in ("L", "M") for ch in v) and any(unicodedata.category(ch)[0] == "L" for ch in v)


def clean(fields: dict) -> dict:
    """The fields of a profile update, checked; ValueError with a plain message. Unknown fields are ignored."""
    if not isinstance(fields, dict):
        raise ValueError("Send the profile fields as an object.")
    out = {}
    for k in ("display_name", "title", "registration_no", "phone"):
        if k in fields:
            v = " ".join(str(fields[k] or "").split())
            limit = {"display_name": 80, "title": 60, "registration_no": 40, "phone": 20}[k]
            if len(v) > limit:
                raise ValueError(f"{k.replace('_', ' ').capitalize()} is too long (at most {limit} characters).")
            if k == "display_name" and v and not name_ok(v):
                raise ValueError("The name may hold letters, spaces, dots, apostrophes, hyphens and round brackets only (2 to 80 characters).")
            if k == "phone" and v and not _PHONE.match(v):
                raise ValueError("The mobile number may hold digits, spaces and hyphens, with an optional leading +.")
            if k == "registration_no" and v and not _REG.match(v):
                raise ValueError("The registration number may hold letters, digits, spaces, slashes, dots and hyphens.")
            out[k] = v
    if "phone_visible" in fields:
        if not isinstance(fields["phone_visible"], bool):
            raise ValueError("phone_visible must be true or false.")
        out["phone_visible"] = fields["phone_visible"]
    if "photo" in fields:
        photo = str(fields["photo"] or "").strip()
        if photo:
            m = _PHOTO.match(photo)
            if not m:
                raise ValueError("The photo must be a PNG, JPEG, WebP or GIF image as a data URL.")
            try:
                raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
            except (ValueError, TypeError):
                raise ValueError("The photo data could not be read.")
            if len(raw) > PHOTO_MAX_BYTES:
                raise ValueError("The photo must be 200 KB or smaller.")
        out["photo"] = photo
    for k, allowed in (("theme", THEMES), ("text_size", TEXT_SIZES), ("start_page", START_PAGES)):
        if k in fields:
            v = str(fields[k] or "").strip().lower()
            if v not in allowed:
                raise ValueError(f"{k.replace('_', ' ').capitalize()} must be one of: {', '.join(allowed)}.")
            out[k] = v
    if "saved_filters" in fields:
        sf = fields["saved_filters"]
        if not isinstance(sf, list) or len(sf) > MAX_FILTERS:
            raise ValueError(f"Saved filters must be a list of at most {MAX_FILTERS} entries.")
        clean_sf = []
        for f in sf:
            if not isinstance(f, dict) or not str(f.get("name") or "").strip():
                raise ValueError("Each saved filter needs a name.")
            entry = {"name": " ".join(str(f["name"]).split())[:60], "query": f.get("query") if isinstance(f.get("query"), (dict, str)) else {},
                     "pinned": bool(f.get("pinned"))}
            if len(json.dumps(entry, ensure_ascii=False)) > MAX_FILTER_CHARS:
                raise ValueError(f"The saved filter '{entry['name']}' is too long.")
            clean_sf.append(entry)
        out["saved_filters"] = clean_sf
    return out


def update(username: str, fields: dict, doctor: bool = False, by: str = "") -> dict:
    """Merge the checked fields into the profile, recompute setup_complete, mirror the display name into org.json when the person is
    placed there, and audit the field names. Returns the profile."""
    u = str(username or "").strip()
    if not u:
        raise ValueError("No login to update.")
    changes = clean(fields)
    with _lock:
        d = _load()
        cur = {**blank(), **(d.get(u) or {})}
        cur.update(changes)
        cur["setup_complete"] = _complete(cur, doctor)
        cur["updated"] = now_iso()
        d[u] = cur
        _save(d)
    if "display_name" in changes and changes["display_name"]:
        _mirror_name(u, changes["display_name"], by or u)
    org.audit("profile_updated", by or u, username=u, fields=sorted(changes), setup_complete=cur["setup_complete"])
    return get(u)


def _mirror_name(username: str, name: str, by: str) -> None:
    """The display name also lives in org.json (the old screens read it there); saved only when it differs, audited by org.save."""
    try:
        import copy
        o = org.load()
        user = (o.get("users") or {}).get(username)
        if not isinstance(user, dict) or user.get("display_name") == name:
            return
        o2 = copy.deepcopy(o)
        o2["users"][username]["display_name"] = name
        org.save(o2, by)
    except Exception:  # the profile is saved either way
        pass


def display_name(username: str) -> str:
    """The name to show for a login: the profile's, else org.json's, else the login itself."""
    u = str(username or "")
    p = _load().get(u) or {}
    name = str(p.get("display_name") or "").strip()
    return name or org.display_name(u)


def setup_complete(username: str, doctor: bool = False) -> bool:
    """Whether the person has done the first-login profile set-up: what they saved themselves (profiles.json), never the name an admin
    typed into org.json, so everyone sees the set-up once (SPEC 3.2)."""
    stored = _load().get(str(username or "")) or {}
    return isinstance(stored, dict) and _complete(stored, doctor)


def public(username: str, viewer_known: bool = False) -> dict:
    """What other signed-in people see: name, title, photo, and the mobile number only when the person allowed it."""
    p = get(username)
    return {"user": username, "display_name": p["display_name"] or org.display_name(username), "title": p["title"], "photo": p["photo"],
            "phone": p["phone"] if (p["phone_visible"] and viewer_known) else ""}
