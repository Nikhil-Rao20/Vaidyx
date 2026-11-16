"""Runtime configuration. Model endpoints are OpenAI-compatible vLLM servers on the local H200.

Override with environment variables or data/tumour_board/models.json (written by the admin UI / scripts):
  {"reader":   {"base_url": "...", "model": "...", "label": "...", "origin": "...", "medical": true},
   "reasoner": {...}}

Model queues: one queue (concurrency limit) per model server URL, so a big scan on the reader does not make Q&A on the
reasoner wait behind hundreds of queued calls. Roles that point at the same URL share one queue. Sizes:
  TB_CONCURRENCY_READER    in-flight calls to the reader's server   (default 24)
  TB_CONCURRENCY_REASONER  in-flight calls to the reasoner's server (default 32)
  TB_LLM_CONCURRENCY       in-flight calls to any other server      (default 48)

Hospitals (admin consoles, 16 Nov 2026, docs/admin-console/DESIGN.md D1, D12): one running app serves several hospitals, each with its
own data folder. Today's folder (TB_DATA_ROOT) is BASE_ROOT and the hospital "default"; another hospital lives in
HOSPITALS_ROOT/<id>/ (TB_HOSPITALS_ROOT, default a sibling of BASE_ROOT named "hospitals", never inside it) with the same layout. The
current hospital is a ContextVar: the route class sets it per request (set_hospital, never reset: a stream runs after the handler
returns), background work runs inside use_hospital(hid), and a plain thread must start inside contextvars.copy_context().run so it
carries the hospital of the code that started it. DATA_ROOT and CASES_DIR are path proxies that resolve through the ContextVar at
every use, so every existing `config.DATA_ROOT / ...` reads the current hospital's folder. Shared by all hospitals (shared_root(),
BASE_ROOT): the model settings and cards, the embedding model weights and the guideline index, the PubMed cache and settings, the
audio token, the video keys, the push keys and the website's enquiries and mail settings. In-memory maps keyed by a Case File or
meeting id use ScopedDict / ScopedSet (or scoped(key)) so two hospitals that both have TB-2026-0001 never share an entry.
With no current hospital the code uses "default"; once a second hospital exists that is logged (once) and, with
TB_HOSPITAL_STRICT=1 (tests), raised, so a missed background thread is found before a person finds it. A test or script that replaces
config.DATA_ROOT with a plain Path pins everything (shared things too) to that one folder, as before.
"""
import contextlib, contextvars, json, logging, os, re
from collections.abc import MutableMapping, MutableSet
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE_ROOT = Path(os.getenv("TB_DATA_ROOT", REPO / "data" / "tumour_board"))
HOSPITALS_ROOT = Path(os.getenv("TB_HOSPITALS_ROOT") or (BASE_ROOT.parent / "hospitals"))
DEFAULT_HOSPITAL = "default"
HOSPITAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_HOSPITAL: contextvars.ContextVar = contextvars.ContextVar("tb_hospital", default=None)
_hlog = logging.getLogger("tumour_board.hospitals")
_warned_unset = [False]
_others_cache: dict = {}  # registry path -> ((inode, mtime_ns, size), there are hospitals besides "default")


class HospitalContextError(RuntimeError):
    """Strict mode (TB_HOSPITAL_STRICT=1): code asked for the data folder without a current hospital while several hospitals exist."""


def check_hospital_id(hid) -> str:
    """The hospital id as given when it is well formed (lower-case letters, digits and hyphens, 2 to 41 characters), else ValueError."""
    h = str(hid or "")
    if not HOSPITAL_ID.match(h):
        raise ValueError("not a valid hospital id")
    return h


def strict() -> bool:
    return os.getenv("TB_HOSPITAL_STRICT", "").strip().lower() in ("1", "true", "yes", "on")


def _has_other_hospitals() -> bool:
    """True when the registry lists a hospital besides "default" (cached on the registry file's modification time)."""
    p = Path(globals()["HOSPITALS_ROOT"]) / "registry.json"
    try:
        st = p.stat()
    except OSError:
        return False
    sig = (st.st_ino, st.st_mtime_ns, st.st_size)  # a new inode on every atomic write
    hit = _others_cache.get(str(p))
    if hit and hit[0] == sig:
        return hit[1]
    try:
        hs = (json.loads(p.read_text(encoding="utf-8")) or {}).get("hospitals") or {}
        val = any(k != DEFAULT_HOSPITAL for k in hs) if isinstance(hs, dict) else False
    except (OSError, ValueError, AttributeError):
        val = False
    if len(_others_cache) > 64:  # one registry in production; many temporary ones in the tests
        _others_cache.clear()
    _others_cache[str(p)] = (sig, val)
    return val


def hospital_id() -> str:
    """The current hospital ("default" when none is set; see the module docstring for strict mode)."""
    h = _HOSPITAL.get()
    if h is not None:
        return h
    if _has_other_hospitals():
        if strict():
            raise HospitalContextError("no current hospital: run this inside config.use_hospital() or contextvars.copy_context()")
        if not _warned_unset[0]:
            _warned_unset[0] = True
            _hlog.warning("tumour board: data folder asked for without a current hospital; using the default hospital")
    return DEFAULT_HOSPITAL


def set_hospital(hid) -> None:
    """Make `hid` the current hospital of this context (the request hook; never reset: the response may stream after the handler)."""
    _HOSPITAL.set(check_hospital_id(hid))


@contextlib.contextmanager
def use_hospital(hid):
    """Run a block inside hospital `hid` (background work, tests, set-up of a new hospital)."""
    tok = _HOSPITAL.set(check_hospital_id(hid))
    try:
        yield hid
    finally:
        _HOSPITAL.reset(tok)


def shared_root() -> Path:
    """The folder of what every hospital shares (BASE_ROOT), or the one folder a test or script pinned config.DATA_ROOT to."""
    d = globals()["DATA_ROOT"]
    return Path(d) if not isinstance(d, HospitalPath) else Path(globals()["BASE_ROOT"])


def root_for(hid) -> Path:
    """The data folder of hospital `hid`: BASE_ROOT for "default", HOSPITALS_ROOT/<id> for the others."""
    h = check_hospital_id(hid)
    if h == DEFAULT_HOSPITAL:
        return shared_root()
    return Path(globals()["HOSPITALS_ROOT"]) / h


def scoped(key):
    """(current hospital, key): the key of an in-memory map that holds entries of several hospitals."""
    return (hospital_id(), key)


class HospitalPath(os.PathLike):
    """A Path that names the current hospital's folder (or a sub-folder of it) at every use: `/`, os.fspath, str, ==, and every Path
    attribute (exists, iterdir, glob, mkdir, parent, name, ...) are those of the real Path of the current hospital."""
    __slots__ = ("_sub",)

    def __init__(self, sub: str = ""):
        self._sub = sub

    def _path(self) -> Path:
        p = root_for(hospital_id())
        return p / self._sub if self._sub else p

    def __fspath__(self) -> str:
        return os.fspath(self._path())

    def __truediv__(self, other) -> Path:
        return self._path() / other

    def __rtruediv__(self, other) -> Path:
        return Path(other) / self._path()

    def __str__(self) -> str:
        return str(self._path())

    def __repr__(self) -> str:
        return f"HospitalPath({str(self._path())!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, HospitalPath):
            other = other._path()
        return self._path() == other

    def __hash__(self) -> int:
        return hash(self._path())

    def __getattr__(self, name):
        if name.startswith("__") or name == "_sub":  # copy / pickle probes, and no recursion before __init__ ran
            raise AttributeError(name)
        return getattr(self._path(), name)


DATA_ROOT = HospitalPath()
CASES_DIR = HospitalPath("cases")


class ScopedDict(MutableMapping):
    """A dict whose keys belong to the current hospital: d[k] is d[(hospital, k)] underneath; len, iteration, items() see the current
    hospital's entries only. clear() empties every hospital's (tests reset with it)."""

    def __init__(self, *a, **kw):
        self._d: dict = {}
        self.update(*a, **kw)

    def __getitem__(self, k):
        return self._d[(hospital_id(), k)]

    def __setitem__(self, k, v):
        self._d[(hospital_id(), k)] = v

    def __delitem__(self, k):
        del self._d[(hospital_id(), k)]

    def __contains__(self, k):
        return (hospital_id(), k) in self._d

    def __iter__(self):
        h = hospital_id()
        return iter([k for (hh, k) in list(self._d) if hh == h])

    def __len__(self):
        h = hospital_id()
        return sum(1 for (hh, _k) in list(self._d) if hh == h)

    def get(self, k, default=None):
        return self._d.get((hospital_id(), k), default)

    def pop(self, k, *default):
        return self._d.pop((hospital_id(), k), *default)

    def setdefault(self, k, default=None):
        return self._d.setdefault((hospital_id(), k), default)

    def clear(self):
        self._d.clear()

    def __repr__(self):
        return f"ScopedDict({dict(self.items())!r})"


class ScopedSet(MutableSet):
    """A set whose members belong to the current hospital (see ScopedDict). clear() empties every hospital's."""

    def __init__(self, items=()):
        self._s: set = set()
        for x in items:
            self.add(x)

    def __contains__(self, x):
        return (hospital_id(), x) in self._s

    def __iter__(self):
        h = hospital_id()
        return iter([x for (hh, x) in list(self._s) if hh == h])

    def __len__(self):
        h = hospital_id()
        return sum(1 for (hh, _x) in list(self._s) if hh == h)

    def add(self, x):
        self._s.add((hospital_id(), x))

    def discard(self, x):
        self._s.discard((hospital_id(), x))

    def clear(self):
        self._s.clear()

    def __repr__(self):
        return f"ScopedSet({set(self)!r})"
PROTOCOL_DIR = Path(__file__).resolve().parent / "protocols"
DEMO_CORPUS = Path(os.getenv("TB_DEMO_CORPUS", "/data/vaidyx/tb_demo_corpus"))
GUIDELINE_DIR = Path(os.getenv("TB_GUIDELINE_DIR", "/data/vaidyx/tb_resources/guidelines"))
GUIDELINE_CHUNKING = os.getenv("TB_GUIDELINE_CHUNKING", "fixed")  # "fixed" or "section" (V1 item 5.4)


def loopback_audio_url(raw) -> str:
    """TB_AUDIO_URL as voice may use it: only http://127.0.0.1:<port> or http://localhost:<port> (the recordings and the token never
    leave the machine, review 9 D, M3). Anything else turns voice off with one log line that names no value."""
    import re
    url = str(raw or "").strip().rstrip("/")
    if not url:
        return ""
    if re.fullmatch(r"http://(127\.0\.0\.1|localhost):\d{1,5}", url) and 0 < int(url.rsplit(":", 1)[1]) < 65536:
        return url
    import logging
    logging.getLogger(__name__).warning("TB_AUDIO_URL is not http://127.0.0.1:<port> or http://localhost:<port>; voice is off")
    return ""


AUDIO_URL = loopback_audio_url(os.getenv("TB_AUDIO_URL", ""))  # the local audio service (night-v3 item 4.2); empty means voice is off
AUDIO_TOKEN_FILE = os.getenv("TB_AUDIO_TOKEN_FILE", str(BASE_ROOT / "audio_token.json"))  # shared by all hospitals

DEFAULT_MODELS = {
    "reasoner": {"base_url": os.getenv("TB_REASONER_URL", "http://127.0.0.1:8100/v1"), "model": os.getenv("TB_REASONER_MODEL", "reasoner"),
                 "label": "", "origin": "", "medical": None},
    "reader": {"base_url": os.getenv("TB_READER_URL", "http://127.0.0.1:8101/v1"), "model": os.getenv("TB_READER_MODEL", "reader"),
               "label": "", "origin": "", "medical": None},
}


def models():
    cfg = json.loads(json.dumps(DEFAULT_MODELS))
    f = shared_root() / "models.json"  # one set of model servers for every hospital
    if f.exists():
        try:
            for k, v in json.loads(f.read_text()).items():
                cfg.setdefault(k, {}).update(v)
        except Exception:
            pass
    # the extractor uses the reasoner unless configured separately
    cfg.setdefault("extractor", dict(cfg["reasoner"]))
    return cfg


LLM_CONCURRENCY = int(os.getenv("TB_LLM_CONCURRENCY", "48"))


def concurrency() -> dict:
    """Queue sizes per server kind (read from the environment on each call; see the module docstring)."""
    return {
        # Lower than the reasoner: vision calls with 1800 px images saturate the reader's API server (it stalls accepting connections).
        "reader": int(os.getenv("TB_CONCURRENCY_READER", "24")),
        "reasoner": int(os.getenv("TB_CONCURRENCY_REASONER", "32")),
        "other": int(os.getenv("TB_LLM_CONCURRENCY", str(LLM_CONCURRENCY))),
    }
OCR_MAX_SIDE = int(os.getenv("TB_OCR_MAX_SIDE", "1800"))
# Case Files holding real patient data that automatic matching must never link into or write to (V1 item 2.4): the intake matcher
# skips them and no identifier is ever learned into them. Comma-separated ids; the default is the real case on this server.
PROTECTED_CASES = {c.strip() for c in os.getenv("TB_PROTECTED_CASES", "TB-2026-bharath").split(",") if c.strip()}

# Private Case Files (guest reviewers' own anonymized files, 5 Nov 2026): created by a login with the real_data flag; its folder holds
# the PRIVATE marker. HIDDEN_CASES = PROTECTED_CASES + every private Case File: never listed, named, shown in a meeting, matched,
# counted or suggested to anyone but the login that created it and the MDT Coordinator (the visibility checks use HIDDEN_CASES); once
# sent to the board it may be on a meeting (BOARD_HIDDEN, the board and meeting code only). PROTECTED_CASES alone
# keeps its second meaning: no AI processing (summary, helper briefs, preparation), which a private Case File does get.
PRIVATE_MARKER = "PRIVATE"
_PRIVATE_ID = __import__("re").compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")


def is_private(case_id) -> bool:
    cid = str(case_id or "")
    return bool(_PRIVATE_ID.match(cid)) and (globals()["CASES_DIR"] / cid / PRIVATE_MARKER).is_file()


class _HiddenCases:
    """`cid in HIDDEN_CASES`: a protected (real) Case File or a private one. Read on every check (a marker file), so it is never stale."""

    def __contains__(self, cid) -> bool:
        return (cid in globals()["PROTECTED_CASES"]) or is_private(cid)

    def __iter__(self):
        ids = set(globals()["PROTECTED_CASES"])
        try:
            ids |= {d.name for d in globals()["CASES_DIR"].iterdir() if (d / PRIVATE_MARKER).is_file()}
        except OSError:
            pass
        return iter(sorted(ids))

    def __len__(self) -> int:
        return len(list(iter(self)))


HIDDEN_CASES = _HiddenCases()


def sent_to_board(case_id) -> bool:
    """A private Case File its guest reviewer sent to the board (Eswar, 5 Nov 2026): the last entry of case.json board_ready_history is a
    send, not a take-back. Read from the file on every check (config never imports store)."""
    import json
    try:
        c = json.loads((globals()["CASES_DIR"] / str(case_id) / "case.json").read_text())
    except (OSError, ValueError):
        return False
    h = [x for x in (c.get("board_ready_history") or []) if isinstance(x, dict)]
    return bool(h) and bool(h[-1].get("ready"))


class _BoardHidden:
    """`cid in BOARD_HIDDEN`, for the board and meeting code only (agenda, meeting screens, notes, PDF, the meeting window): the real case
    always; a private Case File until its guest reviewer sends it to the board (Eswar, 5 Nov 2026: "Allow the board": the MDT Coordinator
    puts it on a meeting and the people in that meeting see it there, read only). Everywhere else HIDDEN_CASES still applies."""

    def __contains__(self, cid) -> bool:
        return (cid in globals()["PROTECTED_CASES"]) or (is_private(cid) and not sent_to_board(cid))


BOARD_HIDDEN = _BoardHidden()


def near_match() -> bool:
    """V1 item 6.5: keep items whose quote matches the source only approximately in briefs and the summary, flagged "approximate source
    match: check source" (TB_NEAR_MATCH=1). Off until the clinical team accepts it; read on every call. Q&A never uses it."""
    return os.getenv("TB_NEAR_MATCH", "").strip().lower() in ("1", "true", "yes", "on")
