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
AUDIO_URL = os.getenv("TB_AUDIO_URL", "").rstrip("/")  # the local audio service (night-v3 item 4.2); empty means voice is off
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


def near_match() -> bool:
    """V1 item 6.5: keep items whose quote matches the source only approximately in briefs and the summary, flagged "approximate source
    match: check source" (TB_NEAR_MATCH=1). Off until the clinical team accepts it; read on every call. Q&A never uses it."""
    return os.getenv("TB_NEAR_MATCH", "").strip().lower() in ("1", "true", "yes", "on")
