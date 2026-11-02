"""Browser push notifications (18 Oct, B3), best effort and off when the keys are missing.

Keys: data/tumour_board/push_keys.json (VAPID key pair, generated once with py_vapid, mode 600; the public key is what the page
subscribes with). Subscriptions: push_subs.json {user: [{endpoint, keys{p256dh, auth}, added}]}. Preferences: notify_prefs.json
{user: {digest_time: "08:00", kinds: {kind: true|false}}} (a kind missing is on). notify.notify() calls on_notification(rec) after
storing a notification: the people addressed (a department: everyone placed in it; the coordinator role: the coordinators; a user)
get a push with a GENERIC text per kind (never a UHID, a patient name or any clinical word). A subscription the push service refuses
with 404 or 410 is removed. Sends run in a daemon thread so a route never waits for the push service; ASYNC = False makes them run
inline (tests)."""
import base64, json, logging, os, re, threading
from datetime import datetime

from . import config, org, store

log = logging.getLogger(__name__)

KEYS_FILE, SUBS_FILE, PREFS_FILE = "push_keys.json", "push_subs.json", "notify_prefs.json"
CONTACT = os.getenv("TB_PUSH_CONTACT", "mailto:vaidyx-tb@localhost")
ASYNC = True
TTL = 3600
TEXTS = {
    "request": "Vaidyx-TB: a request needs your attention",
    "request_reminder": "Vaidyx-TB: a reminder about an open request",
    "reminder_automatic": "Vaidyx-TB: an open request is past its due date",
    "owner_reminder": "Vaidyx-TB: something is open before the board",
    "request_closed": "Vaidyx-TB: a request was closed",
    "request_acknowledged": "Vaidyx-TB: a request was acknowledged",
    "request_done": "Vaidyx-TB: a department answered a request",
    "case_ready": "Vaidyx-TB: a Case File is ready for the board",
    "board_ready": "Vaidyx-TB: a Case File was marked ready for the board",
    "board_action": "Vaidyx-TB: a board action is in your inbox",
    "board_action_suggestion": "Vaidyx-TB: a board action may be complete",
    "decision_value_changed": "Vaidyx-TB: a value a decision cited has changed",
    "case_shared": "Vaidyx-TB: your department was added to a Case File",
    "case_unshared": "Vaidyx-TB: your department was removed from a Case File",
    "referral": "Vaidyx-TB: a Case File was referred to your department",
    "referral_answered": "Vaidyx-TB: a referral was answered",
    "sign_off": "Vaidyx-TB: a resident asks you to sign off",
    "join_request": "Vaidyx-TB: someone asks to join a Case File team",
    "outcome": "Vaidyx-TB: the board recorded an outcome for one of your Case Files",
    "agenda": "Vaidyx-TB: the Tumour Board agenda changed",
    "meeting_starting": "Vaidyx-TB: the Tumour Board starts in 15 minutes",
    "summary_stale": "Vaidyx-TB: a Case File summary is out of date",
    "record_arrived": "Vaidyx-TB: a record arrived for one of your Case Files",
    "card_requested": "Vaidyx-TB: your card is requested after a case",
    "digest": "Vaidyx-TB: your daily digest is ready",
    "summary_ready": "Vaidyx-TB: a Case File summary is ready for review",
    "team_changed": "Vaidyx-TB: a Case File team changed",
    "break_glass": "Vaidyx-TB: an emergency access to a Case File was opened",
    "message": "Vaidyx-TB: you have a new message",  # night-v3 Phase 8: messages.py sends its own push ("New message from Dr X", coalesced); this text is the fallback
}
GENERIC = "Vaidyx-TB: you have a new notification"
_lock = threading.Lock()
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _path(name) -> "os.PathLike":
    return config.DATA_ROOT / name


def _read(name, default):
    p = _path(name)
    if not p.exists():
        return default
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return d if isinstance(d, type(default)) else default


def _write(name, obj, mode=None) -> None:
    """Atomic write; with `mode` (the keys and the subscriptions: 0o600) the file is created with that mode, never readable by others
    even for a moment."""
    p = _path(name)
    if mode is None:
        store._write_json(p, obj)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.chmod(tmp, mode)
    os.replace(tmp, p)


# ---- keys -------------------------------------------------------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_keys() -> dict:
    """A fresh VAPID key pair (py_vapid / cryptography): the raw private scalar and the uncompressed public point, base64url."""
    from py_vapid import Vapid01
    from cryptography.hazmat.primitives import serialization
    v = Vapid01()
    v.generate_keys()
    priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"public_key": _b64url(pub), "private_key": _b64url(priv), "created": store.now_iso()}


def keys(create: bool = False) -> dict | None:
    """The stored keys; with create=True they are generated once (file mode 600). None when missing and not created."""
    d = _read(KEYS_FILE, {})
    if d.get("public_key") and d.get("private_key"):
        return d
    if not create:
        return None
    with _lock:
        d = _read(KEYS_FILE, {})
        if d.get("public_key") and d.get("private_key"):
            return d
        try:
            d = generate_keys()
        except Exception as e:
            log.warning("push keys not generated (%s)", e)
            return None
        _write(KEYS_FILE, d, 0o600)
        return d


def public_key() -> str | None:
    return (keys() or {}).get("public_key")


def available() -> bool:
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


def enabled() -> bool:
    return keys() is not None and available()


# ---- subscriptions and preferences ------------------------------------------------------------------------------------------------------

# The push services browsers subscribe with (security review #17): the server only ever posts to these hosts, over https.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
PUSH_HOST_SUFFIXES = (".notify.windows.com",)


def endpoint_allowed(endpoint) -> bool:
    """True for an https URL on a known push service (Chrome / Edge FCM, Firefox, Safari, Windows WNS), default port, no user info."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(str(endpoint or ""))
        host, port = (u.hostname or "").lower(), u.port
    except ValueError:
        return False
    if u.scheme != "https" or not host or u.username or u.password or port not in (None, 443):
        return False
    return host in PUSH_HOSTS or any(host.endswith(sfx) and len(host) > len(sfx) for sfx in PUSH_HOST_SUFFIXES)


def _clean_subscription(sub) -> dict:
    if not isinstance(sub, dict) or not str(sub.get("endpoint") or "").startswith("https://") or not isinstance(sub.get("keys"), dict):
        raise ValueError("A push subscription needs an https endpoint and its keys (p256dh, auth).")
    if not endpoint_allowed(sub.get("endpoint")):
        raise ValueError("This browser's push service is not one this server sends to (Chrome, Edge, Firefox and Safari are).")
    k = sub["keys"]
    if not k.get("p256dh") or not k.get("auth"):
        raise ValueError("A push subscription needs its keys (p256dh, auth).")
    return {"endpoint": str(sub["endpoint"])[:2000], "keys": {"p256dh": str(k["p256dh"])[:400], "auth": str(k["auth"])[:200]},
            "expirationTime": sub.get("expirationTime")}


def subscriptions(user: str | None = None):
    d = _read(SUBS_FILE, {})
    return list(d.get(str(user or "")) or []) if user is not None else d


def subscribe(user: str, sub: dict, agent: str = "") -> dict:
    clean = _clean_subscription(sub)
    with _lock:
        d = _read(SUBS_FILE, {})
        mine = [x for x in d.get(user) or [] if x.get("endpoint") != clean["endpoint"]]
        mine.append({**clean, "added": store.now_iso(), "agent": str(agent or "")[:200]})
        d[user] = mine[-5:]  # a person's last five browsers
        _write(SUBS_FILE, d, 0o600)
    return {"subscribed": True, "count": len(d[user])}


def unsubscribe(user: str, endpoint: str) -> dict:
    with _lock:
        d = _read(SUBS_FILE, {})
        before = len(d.get(user) or [])
        d[user] = [x for x in d.get(user) or [] if x.get("endpoint") != endpoint]
        if not d[user]:
            d.pop(user, None)
        _write(SUBS_FILE, d, 0o600)
    return {"removed": before - len(d.get(user) or [])}


def _remove(user: str, endpoint: str) -> None:
    with _lock:
        d = _read(SUBS_FILE, {})
        d[user] = [x for x in d.get(user) or [] if x.get("endpoint") != endpoint]
        if not d[user]:
            d.pop(user, None)
        _write(SUBS_FILE, d, 0o600)


def prefs(user: str) -> dict:
    d = _read(PREFS_FILE, {}).get(str(user or "")) or {}
    kinds = d.get("kinds") if isinstance(d.get("kinds"), dict) else {}
    return {"digest_time": d.get("digest_time") if _TIME.match(str(d.get("digest_time") or "")) else "08:00", "kinds": {k: bool(v) for k, v in kinds.items()},
            "push": bool(d.get("push", True))}


def set_prefs(user: str, data: dict) -> dict:
    cur = prefs(user)
    if "digest_time" in data and data["digest_time"] is not None:
        t = str(data["digest_time"]).strip()
        if not _TIME.match(t):
            raise ValueError("The digest time must be HH:MM (24-hour clock).")
        cur["digest_time"] = t
    if "kinds" in data and data["kinds"] is not None:
        if not isinstance(data["kinds"], dict):
            raise ValueError("kinds must be an object of kind: true | false.")
        from . import notify
        bad = [k for k in data["kinds"] if k not in notify.KINDS]
        if bad:
            raise ValueError(f"Unknown notification kind(s): {', '.join(sorted(bad))}.")
        cur["kinds"] = {**cur["kinds"], **{k: bool(v) for k, v in data["kinds"].items()}}
    if "push" in data and data["push"] is not None:
        cur["push"] = bool(data["push"])
    with _lock:
        d = _read(PREFS_FILE, {})
        d[user] = cur
        _write(PREFS_FILE, d)
    return cur


def wants(user: str, kind: str) -> bool:
    p = prefs(user)
    return p.get("push", True) and p["kinds"].get(kind, True)


# ---- who and what -------------------------------------------------------------------------------------------------------------------------

def users_for(to: dict) -> list[str]:
    """The logins a notification address reaches: a department -> everyone placed in it; the coordinator role -> the coordinators; a user."""
    to = to or {}
    users = org.load().get("users") or {}
    if "user" in to:
        return [str(to["user"])] if to["user"] else []
    if "role" in to:
        return sorted(u for u, rec in users.items() if isinstance(rec, dict) and rec.get("coordinator") is True and not rec.get("disabled"))
    if "department" in to:
        did = org.department_id(to["department"]) or to["department"]
        if org.is_coordinator_name(did):
            return users_for({"role": "coordinator"})
        return sorted(u for u, rec in users.items() if isinstance(rec, dict) and not rec.get("disabled") and did in (rec.get("departments") or {}))
    return []


def text_for(kind: str) -> str:
    return TEXTS.get(kind, GENERIC)


def deliver(sub: dict, text: str, kind: str = "") -> int:
    """One push; returns the HTTP status (201 or 200 on success; 404 / 410 mean the subscription is gone). Raises on other failures."""
    from pywebpush import WebPushException, webpush
    if not endpoint_allowed(sub.get("endpoint")):  # a subscription saved before the allow-list: dropped as gone (security review #17)
        return 410
    k = keys()
    if not k:
        return 0
    payload = json.dumps({"title": "Vaidyx-TB", "body": text, "kind": kind, "url": "/tb-nik"})
    try:
        r = webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=payload, vapid_private_key=k["private_key"],
                    vapid_claims={"sub": CONTACT}, ttl=TTL, timeout=10)
    except WebPushException as e:
        resp = getattr(e, "response", None)
        status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status in (404, 410):
            return int(status)
        raise
    return int(getattr(r, "status_code", 201) or 201)


def send_to_users(users, kind: str, text: str | None = None) -> dict:
    """Push the generic text for `kind` to every subscription of `users` (honouring their preferences). Never raises."""
    out = {"sent": 0, "removed": 0, "skipped": 0, "failed": 0}
    if not enabled():
        out["skipped"] = len(list(users or []))
        return out
    text = text or text_for(kind)
    for u in dict.fromkeys(users or []):
        if not wants(u, kind):
            out["skipped"] += 1
            continue
        for sub in subscriptions(u):
            try:
                status = deliver(sub, text, kind)
            except Exception as e:
                out["failed"] += 1
                log.info("push to %s failed (%s)", u, e.__class__.__name__)
                continue
            if status in (404, 410):
                _remove(u, sub.get("endpoint") or "")
                out["removed"] += 1
            elif status:
                out["sent"] += 1
    return out


def on_notification(rec: dict) -> dict | None:
    """Called by notify.notify after a notification is stored: a generic push to the people addressed (in a thread unless ASYNC is off)."""
    if not isinstance(rec, dict) or not enabled():
        return None
    if rec.get("kind") == "message":
        return None  # messages.py pushes "New message from Dr X" itself, at most once per conversation per five minutes (Phase 8)
    users = users_for(rec.get("to") or {})
    if not users:
        return None
    kind = str(rec.get("kind") or "")
    if ASYNC:
        threading.Thread(target=send_to_users, args=(users, kind), daemon=True, name="tb-push").start()
        return {"queued": len(users)}
    return send_to_users(users, kind)


def digest_due(user: str, now: datetime, last_sent: str | None) -> bool:
    """True once a day from the user's digest time on (08:00 by default), unless a digest went out today already."""
    t = prefs(user)["digest_time"]
    if last_sent and str(last_sent)[:10] == now.date().isoformat():
        return False
    return now.strftime("%H:%M") >= t
