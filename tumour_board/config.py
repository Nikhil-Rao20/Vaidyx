"""Runtime configuration. Model endpoints are OpenAI-compatible vLLM servers on the local H200.

Override with environment variables or data/tumour_board/models.json (written by the admin UI / scripts):
  {"reader":   {"base_url": "...", "model": "...", "label": "...", "origin": "...", "medical": true},
   "reasoner": {...}}

Model queues: one queue (concurrency limit) per model server URL, so a big scan on the reader does not make Q&A on the
reasoner wait behind hundreds of queued calls. Roles that point at the same URL share one queue. Sizes:
  TB_CONCURRENCY_READER    in-flight calls to the reader's server   (default 24)
  TB_CONCURRENCY_REASONER  in-flight calls to the reasoner's server (default 32)
  TB_LLM_CONCURRENCY       in-flight calls to any other server      (default 48)
"""
import json, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("TB_DATA_ROOT", REPO / "data" / "tumour_board"))
CASES_DIR = DATA_ROOT / "cases"
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
AUDIO_TOKEN_FILE = os.getenv("TB_AUDIO_TOKEN_FILE", str(DATA_ROOT / "audio_token.json"))

DEFAULT_MODELS = {
    "reasoner": {"base_url": os.getenv("TB_REASONER_URL", "http://127.0.0.1:8100/v1"), "model": os.getenv("TB_REASONER_MODEL", "reasoner"),
                 "label": "", "origin": "", "medical": None},
    "reader": {"base_url": os.getenv("TB_READER_URL", "http://127.0.0.1:8101/v1"), "model": os.getenv("TB_READER_MODEL", "reader"),
               "label": "", "origin": "", "medical": None},
}


def models():
    cfg = json.loads(json.dumps(DEFAULT_MODELS))
    f = DATA_ROOT / "models.json"
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
# counted or suggested to anyone but the login that created it (the visibility checks use HIDDEN_CASES). PROTECTED_CASES alone
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


def near_match() -> bool:
    """V1 item 6.5: keep items whose quote matches the source only approximately in briefs and the summary, flagged "approximate source
    match: check source" (TB_NEAR_MATCH=1). Off until the clinical team accepts it; read on every call. Q&A never uses it."""
    return os.getenv("TB_NEAR_MATCH", "").strip().lower() in ("1", "true", "yes", "on")
