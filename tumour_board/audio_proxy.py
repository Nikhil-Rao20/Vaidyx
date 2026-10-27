"""Voice through the app (night-v3 item 4.2, owner decision D1): the app speaks to the local audio service (127.0.0.1:7120, item 4.1)
for signed-in Tumour Board users; the browser never reaches the service.

    enabled()                   voice is on when TB_AUDIO_URL is set (config.AUDIO_URL); empty means off and nothing is ever called
    token()                     the shared token of the service, read once from config.AUDIO_TOKEN_FILE ({"token": "..."}); never logged,
                                printed or returned; a missing file sends an empty header (the service refuses, the status says down)
    status()                    {enabled, stt, tts, limits, cohere, voices} from the service's /health (1.5 s timeout), cached 15 s;
                                never raises: off, ready, loading or down
    transcribe(...)             one recording to the service's /stt (multipart, the token header only, never cookies or Authorization)
    speak(text, voice, speed)   one piece of text to the service's /tts; the WAV and the allowed response headers back
    error_for(status, code)     the service's refusal as the app's (status, plain message, code); everything degrades to typing
    split_sentences(text)       the fixed sentence rule the front end carries too (item 4.3)
    RESOLVERS / resolve(...)    a saved statement by reference (chat, agent, meeting_answer, summary, points): the screen's own check
                                first, then the exact text the screen shows; None for refused and unknown alike
    audit_*                     audit lines without content: never the text, the audio, a filename or the token

Scope: speech to text only fills an editable text box; text to speech only reads text already on screen or a saved, grounded
statement. The audio is never stored; nothing here reads an image or writes a fact."""
import json
import re
import threading
import time

import httpx

from . import config, store

STT_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB of audio (the service's own cap)
STT_BODY_SLACK = 64 * 1024        # the multipart wrapping around it
TEXT_MAX = 1000                   # on-screen text read back (mode b)
TTS_MAX = 2000                    # one request to the service
STATUS_TTL = 15.0
STATUS_TIMEOUT = 1.5
VOICES = ("af_heart", "bf_emma", "am_michael")
DEFAULT_VOICE = "af_heart"
SPEED_MIN, SPEED_MAX = 0.8, 1.25
CONTEXTS = ("question", "decision", "note", "reason")
ENGINES = ("whisper", "parakeet")
LIMITS = {"stt_seconds": 60, "stt_bytes": STT_MAX_BYTES, "tts_chars": TTS_MAX}
KINDS = ("chat", "agent", "meeting_answer", "summary", "points")
CASE_KINDS = ("chat", "agent", "summary", "points")
_SCREEN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")  # the helper roles carry an underscore (medical_oncology)
TEXT_SCREENS = ("decision",)  # the only boxes whose on-screen text may be read back (mode b)
RESP_HEADERS = ("content-type", "content-length", "x-took-ms", "x-sample-rate")

UNAVAILABLE = "Voice is not available right now. You can type instead."
TOO_LONG = "That was longer than one minute. Record in shorter parts."
TOO_BIG = "That recording is too large. Record in shorter parts."
UNREADABLE = "The recording could not be read."
BUSY = "Too many voice requests. Wait a minute, or type."
TEXT_TOO_LONG = "That text is too long to read aloud. Read it in shorter parts."
NOTHING = "Nothing to read here."


def enabled() -> bool:
    return bool(config.AUDIO_URL)


def valid_screen(screen) -> bool:
    return isinstance(screen, str) and bool(_SCREEN.match(screen))


# ---------------------------------------------------------------------------------------------------- the token and the client
_token: dict = {}
_lock = threading.Lock()


def token() -> str:
    """The service's shared token, read once from config.AUDIO_TOKEN_FILE ({"token": "..."}); "" when missing or unreadable."""
    path = str(config.AUDIO_TOKEN_FILE or "")
    with _lock:
        if _token.get("path") != path or not _token.get("value"):  # an empty token is never cached: the file may appear later
            value = ""
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                value = str(data.get("token") or "").strip() if isinstance(data, dict) else ""
            except (OSError, ValueError):
                value = ""
            _token.clear()
            _token.update(path=path, value=value)
        return _token["value"]


_CLIENT: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    """One shared client to the audio service (created on first use): 30 s to answer, 2 s to connect, redirects never followed."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=2), follow_redirects=False)
    return _CLIENT


def reset() -> None:
    """Tests and a changed configuration: forget the token, the cached status and the client."""
    global _CLIENT
    with _lock:
        _token.clear()
    _status.clear()
    _CLIENT = None


# ---------------------------------------------------------------------------------------------------- status
_status: dict = {}  # {"at": monotonic time, "value": the last answer}


def _state(engine: dict) -> str:
    s = str((engine or {}).get("state") or "")
    if s in ("ready", "not_loaded"):  # not_loaded: the engine loads on the first request (a few seconds), so the buttons stay usable
        return "ready"
    if s == "loading":
        return "loading"
    return "down"


def _off() -> dict:
    return {"enabled": False, "stt": "off", "tts": "off", "limits": dict(LIMITS), "cohere": False, "voices": []}


def _down() -> dict:
    return {"enabled": True, "stt": "down", "tts": "down", "limits": dict(LIMITS), "cohere": False, "voices": []}


def _from_health(h: dict) -> dict:
    lim = h.get("limits") if isinstance(h.get("limits"), dict) else {}
    limits = {k: (lim[k] if isinstance(lim.get(k), (int, float)) and not isinstance(lim.get(k), bool) else v) for k, v in LIMITS.items()}
    tts = h.get("tts") if isinstance(h.get("tts"), dict) else {}
    voices = [v for v in (tts.get("voices") or []) if isinstance(v, str) and v in VOICES]
    engines = h.get("engines") if isinstance(h.get("engines"), dict) else {}
    return {"enabled": True, "stt": _state(h.get("stt") if isinstance(h.get("stt"), dict) else {}), "tts": _state(tts),
            "limits": limits, "cohere": engines.get("cohere") == "ready", "voices": voices}


async def status(now: float | None = None) -> dict:
    """What the front end needs to show or hide the microphone and the speaker. Never raises."""
    if not enabled():
        return _off()
    now = time.monotonic() if now is None else now
    hit = _status.get("value")
    if hit is not None and now - _status.get("at", 0) < STATUS_TTL and _status.get("url") == config.AUDIO_URL:
        return dict(hit)
    try:
        if not token():  # the service would refuse every request
            value = _down()
        else:
            r = await _client().get(config.AUDIO_URL + "/health", timeout=STATUS_TIMEOUT)
            body = r.json() if r.status_code == 200 else None
            value = _from_health(body) if isinstance(body, dict) else _down()
    except Exception:  # connection refused, timeout, a body that is not JSON
        value = _down()
    _status.update(at=now, value=value, url=config.AUDIO_URL)
    return dict(value)


# ---------------------------------------------------------------------------------------------------- the service calls
class ServiceError(Exception):
    """A refusal or failure of the audio service: status 0 for no answer (connection, timeout), else the HTTP status and its code."""

    def __init__(self, status: int, code: str = ""):
        super().__init__(f"audio service {status} {code}".strip())
        self.status, self.code = status, code


def error_for(status: int, code: str = "") -> tuple:
    """(status, plain message, code) for the app's answer to a refusal of the service."""
    if status == 0 or status == 503:
        return 503, UNAVAILABLE, "voice_unavailable"
    if status == 413 and code == "too_long":
        return 413, TOO_LONG, "too_long"
    if status == 413 and code == "text_too_long":
        return 413, TEXT_TOO_LONG, "text_too_long"
    if status == 413:
        return 413, TOO_BIG, "too_big"
    if status == 415:
        return 415, UNREADABLE, "unsupported_audio"
    if status == 429:
        return 429, BUSY, "busy"
    return 502, UNAVAILABLE, "voice_failed"


def _headers() -> dict:
    return {"X-Audio-Token": token()}


def _code(r: httpx.Response) -> str:
    try:
        b = r.json()
    except Exception:
        return ""
    return str(b.get("code") or "") if isinstance(b, dict) else ""


async def transcribe(audio: bytes, content_type: str = "", engine: str = "whisper", context: str = "") -> dict:
    """One recording to the service's /stt. Returns {text, segments, duration, engine, took_ms, code}; raises ServiceError."""
    if not enabled():
        raise ServiceError(0)
    files = {"audio": ("recording", audio, content_type or "application/octet-stream")}
    data = {"engine": engine if engine in ENGINES else "whisper", "language": "en", "context": context if context in CONTEXTS else "", "words": "0"}
    try:
        r = await _client().post(config.AUDIO_URL + "/stt", files=files, data=data, headers=_headers())
    except httpx.HTTPError:
        raise ServiceError(0)
    if r.status_code != 200:
        raise ServiceError(r.status_code, _code(r))
    try:
        b = r.json()
    except ValueError:
        raise ServiceError(500, "failed")
    if not isinstance(b, dict):
        raise ServiceError(500, "failed")
    segs = [{"start": s.get("start"), "end": s.get("end"), "text": str(s.get("text") or "")} for s in b.get("segments") or [] if isinstance(s, dict)]
    return {"text": str(b.get("text") or ""), "segments": segs, "duration": b.get("duration"), "engine": str(b.get("engine") or ""),
            "took_ms": b.get("took_ms"), "code": b.get("code") or None}


async def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> tuple:
    """One piece of text to the service's /tts. Returns (wav bytes, headers from the allow-list); raises ServiceError."""
    if not enabled():
        raise ServiceError(0)
    body = {"text": text, "voice": voice, "speed": speed, "normalise": True, "format": "wav"}
    try:
        r = await _client().post(config.AUDIO_URL + "/tts", json=body, headers=_headers())
    except httpx.HTTPError:
        raise ServiceError(0)
    if r.status_code != 200:
        raise ServiceError(r.status_code, _code(r))
    out = {k: v for k, v in r.headers.items() if k.lower() in RESP_HEADERS and k.lower() != "content-length"}
    return r.content, out


def took_ms(headers: dict):
    v = next((x for k, x in (headers or {}).items() if k.lower() == "x-took-ms"), None)
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------------- the sentence rule
_ABBREV = {"dr", "mr", "mrs", "no", "reg", "e.g", "i.e", "vs"}
_BREAK = re.compile("([.?!])([\"'”’)\\]]?) (?=[A-Z0-9\"'“‘(\\[])")
_OPENERS = "(\"'[“‘"
LONG, CUT_FROM, CUT_UNTIL, HARD = 400, 300, 1000, 400


def _cut_long(s: str) -> list:
    out = []
    while len(s) > LONG:
        hits = [j for j in (s.find(", ", CUT_FROM), s.find("; ", CUT_FROM)) if 0 <= j <= CUT_UNTIL]
        if hits:
            i = min(hits) + 1
        else:
            sp = s.find(" ", CUT_FROM)
            i = sp if 0 <= sp <= CUT_UNTIL else HARD
        head, s = s[:i].strip(), s[i:].strip()
        if head:
            out.append(head)
    if s:
        out.append(s)
    return out


def split_sentences(text) -> list:
    """The text as the sentences it is read in, one request each. A fixed rule (the front end carries the same, item 4.3):

    1. Every line is its own piece (split on line breaks); spaces inside a line are collapsed; empty lines are dropped.
    2. A line is cut after ".", "?" or "!" (and one closing quote or bracket right after it) followed by one space and then an
       uppercase letter, a digit, a quote or an opening bracket: "Mass seen. Nodes clear." gives two; "Mass seen. nodes" gives one.
    3. Never after an abbreviation: "Dr.", "Mr.", "Mrs.", "No.", "Reg.", "e.g.", "i.e.", "vs." (any case, an opening bracket or
       quote before it ignored): "Seen by Dr. Rao." stays one, "Reg. No. 123 is listed." stays one.
    4. Never inside a decimal number: "5.2 cm" has no space after the point, so it is never a cut.
    5. A piece over 400 characters is cut at the first ", " or "; " between characters 300 and 1000 (the comma stays with the first
       part); with none there, at the first space between 300 and 1000; with none, at character 400. Repeated on the rest.
    """
    out = []
    for raw in str(text or "").splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        start = 0
        for m in _BREAK.finditer(line):
            if m.group(1) == "." and not m.group(2):
                before = line[start:m.start()].split()
                word = before[-1].lstrip(_OPENERS).lower() if before else ""
                if word in _ABBREV:
                    continue
            piece = line[start:m.end()].strip()
            if piece:
                out.extend(_cut_long(piece))
            start = m.end()
        rest = line[start:].strip()
        if rest:
            out.extend(_cut_long(rest))
    return out


_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def screen_text(text) -> str:
    """Dates as the screen shows them (DD/MM/YYYY, the front end's indianDates)."""
    return _ISO.sub(lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}", str(text or ""))


# ---------------------------------------------------------------------------------------------------- saved statements by reference
def _sid(v) -> str:
    return str(v or "").strip()[:80]


def _index(ref):
    i = ref.get("index")
    if isinstance(i, bool) or not isinstance(i, int) or i < 0:
        return None
    return i


def _pick(rows, ref):
    """A row by its id when the reference gives one, else by its place on the screen (index)."""
    rid = _sid(ref.get("id"))
    if rid:
        return next((x for x in rows if isinstance(x, dict) and x.get("id") == rid), None)
    i = _index(ref)
    return rows[i] if i is not None and i < len(rows) and isinstance(rows[i], dict) else None


def _case(case_id):
    try:
        return store.get_case(case_id) if case_id else None
    except (ValueError, OSError):
        return None


def case_scope(roles, case_id):
    """access.scope of this user on this Case File; None for an unknown or unreadable id."""
    from . import access
    c = _case(case_id)
    return access.scope(roles, c) if c else None


def _full(roles, ref) -> bool:
    from . import access
    return case_scope(roles, _sid(ref.get("case_id"))) == access.FULL


def _team_chat(roles, ref) -> bool:
    """The Case File's chat and the helper chats are shown to the treating team and the coordinator in FULL scope (chats.may_read)."""
    from . import access, chats
    sc = case_scope(roles, _sid(ref.get("case_id")))
    return sc == access.FULL and chats.may_read(roles, sc)


def _meeting_member(roles, ref) -> bool:
    """The meeting page (meetings.may_view), and its questions and answers are shown to members only (meetings.view)."""
    from . import meetings
    try:
        s = meetings.need(_sid(ref.get("meeting_id")))
    except Exception:
        return False
    return meetings.may_view(roles, s) and meetings.is_member(roles, s)


def _statements(rows) -> str:
    return " ".join(str(s.get("text") or "").strip() for s in rows or [] if isinstance(s, dict) and str(s.get("text") or "").strip())


def _chat_text(ref):
    from . import chats
    t = _pick(chats.threads(_sid(ref.get("case_id"))), ref)
    if not t:
        return None
    parts = []
    if t.get("message") and t.get("status") != "answered":
        parts.append(str(t["message"]).strip())
    st = _statements(t.get("statements"))
    if st:
        parts.append(st)
    if not parts and t.get("status") == "not_documented":
        parts.append("Not found in the records.")
    if not parts and t.get("status") == "out_of_scope":
        parts.append("Outside what Vaidyx answers.")
    return " ".join(parts)


def _agent_text(ref):
    from . import helpers
    role = _sid(ref.get("role"))
    if role not in helpers.ROLES:
        return None
    m = _pick(helpers.messages(_sid(ref.get("case_id")), role), ref)
    if not m:
        return None
    return _statements(m.get("statements")) or str(m.get("message") or "").strip() or "Nothing in the records answers this."


def _meeting_text(ref, roles=None):
    """A question's answer on the meeting screen (by the question id), or the agent answer logged by board.log_answer (by its entry
    id). A log entry belongs to one Case File and the Board room shows it only to readers of that file, so it needs FULL scope on
    that Case File too (review S of Phase 4, finding M1)."""
    from . import access, meetings
    s = meetings.get(_sid(ref.get("meeting_id")))
    rid = _sid(ref.get("id"))
    if not s or not rid:
        return None
    q = next((x for x in s.get("questions") or [] if isinstance(x, dict) and x.get("id") == rid), None)
    if q is not None:
        a = q.get("answer")
        return a if isinstance(a, str) else (str(a.get("text") or "") if isinstance(a, dict) else None)
    e = next((x for x in s.get("log") or [] if isinstance(x, dict) and x.get("id") == rid and x.get("kind") == "answer"), None)
    if not e:
        return None
    if roles is None or case_scope(roles, _sid(e.get("case_id"))) != access.FULL:
        return None
    return str(e.get("text") or "")


def _section_text(sec) -> str:
    rows = list(sec.get("sentences") or [])
    for b in sec.get("blocks") or []:
        rows.extend((b or {}).get("sentences") or [])
    return " ".join(x.strip() for x in ((r.get("text") if isinstance(r, dict) else r) for r in rows) if isinstance(x, str) and x.strip())


def _summary_text(ref):
    """A section of the Case summary's current version as the screen shows it (the status section worked out for today); before the
    first decision, or with "source": "pre_board", a section of the pre-board summary."""
    from . import case_summary
    case_id = _sid(ref.get("case_id"))
    st = store.get_state(case_id)
    sid = _sid(ref.get("id"))
    cur = case_summary.current(st) if ref.get("source") != "pre_board" else None
    if cur:
        sections = case_summary.display(case_id, st, cur).get("sections") or []
    else:
        summ = (st.get("artefacts") or {}).get("summary")
        sections = summ.get("sections") if isinstance(summ, dict) and isinstance(summ.get("sections"), list) else []
    sec = next((x for x in sections if isinstance(x, dict) and x.get("id") == sid), None)
    return _section_text(sec) if sec else None


def _points_text(ref):
    """The Points for review of the Case File (the pre-board summary's points, as the Summary step lists them), one line each."""
    st = store.get_state(_sid(ref.get("case_id")))
    summ = (st.get("artefacts") or {}).get("summary")
    if not isinstance(summ, dict) or not isinstance(summ.get("sections"), list):
        return None
    return "\n".join(str(p.get("text") or "").strip() for p in summ.get("points_for_review") or [] if isinstance(p, dict) and str(p.get("text") or "").strip())


_LOADERS = {"chat": _chat_text, "agent": _agent_text, "meeting_answer": _meeting_text, "summary": _summary_text, "points": _points_text}
_CHECKS = {"chat": _team_chat, "agent": _team_chat, "meeting_answer": _meeting_member, "summary": _full, "points": _full}


def statement_text(kind, ref, roles=None) -> str | None:
    """The saved statement's text exactly as its screen shows it (no citations, chip labels or model names; dates DD/MM/YYYY); None
    when there is none. No access check of its own: callers go through RESOLVERS (meeting_answer log entries also need the roles)."""
    fn = _LOADERS.get(kind)
    if not fn or not isinstance(ref, dict):
        return None
    try:
        t = fn(ref, roles) if kind == "meeting_answer" else fn(ref)
    except (KeyError, ValueError, OSError):
        return None
    t = screen_text(t).strip() if isinstance(t, str) else ""
    return t or None


def _resolver(kind):
    def resolve_kind(roles, ref):
        if not isinstance(ref, dict) or not _CHECKS[kind](roles, ref):  # the screen's own check, before anything is loaded
            return None
        return statement_text(kind, ref, roles)
    resolve_kind.__name__ = f"resolve_{kind}"
    return resolve_kind


RESOLVERS = {k: _resolver(k) for k in KINDS}  # Phase 6 adds kinds here: {kind: fn(roles, ref) -> str | None}


def resolve(roles, ref) -> str | None:
    fn = RESOLVERS.get(str((ref or {}).get("kind") or "")) if isinstance(ref, dict) else None
    return fn(roles, ref) if fn else None


def audit_case_id(ref) -> str:
    """The Case File id for the audit line: the stored id of the file the reference names (never the raw field, so a padded id
    cannot write a line into a new folder; review of Phase 4, note N4); "" when the file does not exist."""
    c = _case(_sid((ref or {}).get("case_id"))) if isinstance(ref, dict) else None
    return str((c or {}).get("case_id") or (c or {}).get("id") or "") if c else ""


def ref_key(ref) -> str:
    """"<kind>:<case or meeting id>:<id>:<index>" for the audit line (ids only, never text)."""
    ref = ref if isinstance(ref, dict) else {}
    kind = _sid(ref.get("kind"))
    where = _sid(ref.get("meeting_id")) if kind == "meeting_answer" else _sid(ref.get("case_id"))
    rid = _sid(ref.get("id")) or (_sid(ref.get("role")) if kind == "agent" else "")
    i = _index(ref)
    return f"{kind}:{where}:{rid}:{'' if i is None else i}"


# ---------------------------------------------------------------------------------------------------- audit (never content)
def audit_transcribed(user, screen, case_id, seconds, engine, took, chars) -> None:
    from . import org
    fields = {"screen": screen, "seconds": seconds, "engine": engine, "took_ms": took, "chars": chars}
    if case_id:
        store.audit(case_id, {"kind": "audio_transcribed", "by": user, **fields})
    org.audit("audio_transcribed", user, case_id=case_id or "", **fields)


def audit_spoken(user, screen, ref, parts, chars, voice, took, case_id="", part=0) -> None:
    """One organisation line per request (every part, so a part asked for on its own is audited too); the Case File's own log gets
    one line per statement (part 0)."""
    from . import org
    org.audit("audio_spoken", user, screen=screen, ref=ref, part=part, parts=parts, chars=chars, voice=voice, took_ms=took)
    if case_id and part == 0:
        store.audit(case_id, {"kind": "audio_spoken", "by": user, "ref": ref, "parts": parts, "chars": chars})


def audit_refused(user, ref) -> None:
    """A reference that was refused or does not exist: the kind and the Case File (or meeting) id only."""
    from . import org
    ref = ref if isinstance(ref, dict) else {}
    kind = _sid(ref.get("kind"))
    org.audit("audio_refused", user, ref_kind=kind, case_id=_sid(ref.get("meeting_id") if kind == "meeting_answer" else ref.get("case_id")))
