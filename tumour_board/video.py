"""Video for a meeting (18 Oct, B3): the self-hosted LiveKit server on localhost and the access tokens for its rooms.

Keys: data/tumour_board/livekit.json {"api_key", "api_secret", "url"} written by scripts/livekit.sh (random key and secret, mode 600);
without the file video is off. A member of a meeting gets an access token (a LiveKit JWT, HS256: iss = api key, sub = identity, nbf,
exp 2 hours, name, "video" grant for the room "tb-<meeting id>") signed with PyJWT when it is installed, else with the small
base64url HMAC-SHA256 encoder here (no padding). Identity = the Vaidyx username. Text questions stay in the app; the video carries
people only."""
import base64, hashlib, hmac, json, logging, time

from . import config, store

log = logging.getLogger(__name__)

KEYS_FILE = "livekit.json"
DEFAULT_URL = "ws://127.0.0.1:7880"
TOKEN_TTL = 2 * 3600


def keys_path():
    return config.DATA_ROOT / KEYS_FILE


def keys() -> dict | None:
    """{api_key, api_secret, url} or None when video is not set up."""
    p = keys_path()
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("api_key") or not d.get("api_secret"):
        return None
    return {"api_key": str(d["api_key"]), "api_secret": str(d["api_secret"]), "url": str(d.get("url") or DEFAULT_URL)}


def enabled() -> bool:
    return keys() is not None


def url() -> str:
    return (keys() or {}).get("url") or DEFAULT_URL


def status() -> dict:
    k = keys()
    return {"enabled": bool(k), "url": k["url"] if k else None}


def room_name(mid: str) -> str:
    return "tb-" + store.safe_id(str(mid))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    s = str(s)
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hmac_jwt(payload: dict, secret: str) -> str:
    """A minimal JWT (HS256, base64url without padding), used when PyJWT is not installed."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing = f"{header}.{body}".encode("ascii")
    sig = hmac.new(str(secret).encode("utf-8"), signing, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def token(identity: str, name: str, room: str, ttl: int = TOKEN_TTL, now: int | None = None, keys_: dict | None = None,
          can_publish: bool = True, can_subscribe: bool = True) -> str:
    """A LiveKit access token for `identity` to join `room`."""
    k = keys_ or keys()
    if not k:
        raise RuntimeError("Video is not set up (data/tumour_board/livekit.json is missing)")
    now = int(time.time()) if now is None else int(now)
    payload = {"iss": k["api_key"], "sub": str(identity), "nbf": now, "exp": now + int(ttl), "iat": now, "name": str(name or identity),
               "video": {"roomJoin": True, "room": str(room), "canPublish": bool(can_publish), "canSubscribe": bool(can_subscribe)}}
    try:
        import jwt  # PyJWT
    except ImportError:
        return hmac_jwt(payload, k["api_secret"])
    out = jwt.encode(payload, k["api_secret"], algorithm="HS256")
    return out.decode("ascii") if isinstance(out, bytes) else out


def decode(tok: str, secret: str) -> dict:
    """Verify and read a token (tests and the status page): PyJWT when available, else the HMAC check in reverse. ValueError when bad."""
    try:
        import jwt
        try:
            return jwt.decode(tok, secret, algorithms=["HS256"], options={"verify_exp": False})
        except jwt.PyJWTError as e:
            raise ValueError(str(e))
    except ImportError:
        pass
    try:
        header, body, sig = str(tok).split(".")
    except ValueError:
        raise ValueError("not a JWT")
    want = hmac.new(str(secret).encode("utf-8"), f"{header}.{body}".encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url(want), sig):
        raise ValueError("bad signature")
    return json.loads(_b64url_decode(body))


def for_meeting(mid: str, identity: str, name: str) -> dict:
    """{url, token, room, identity, name} for a member of the meeting."""
    room = room_name(mid)
    return {"url": url(), "token": token(identity, name, room), "room": room, "identity": str(identity), "name": str(name or identity), "expires_in": TOKEN_TTL}
