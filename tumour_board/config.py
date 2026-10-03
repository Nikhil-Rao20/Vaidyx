"""Runtime configuration. Model endpoints are OpenAI-compatible vLLM servers on the local H200.

Override with environment variables or data/tumour_board/models.json (written by the admin UI / scripts):
  {"reader":   {"base_url": "...", "model": "...", "label": "...", "origin": "...", "medical": true},
   "reasoner": {...}}
"""
import json, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("TB_DATA_ROOT", REPO / "data" / "tumour_board"))
CASES_DIR = DATA_ROOT / "cases"
PROTOCOL_DIR = Path(__file__).resolve().parent / "protocols"
DEMO_CORPUS = Path(os.getenv("TB_DEMO_CORPUS", "/data/vaidyx/tb_demo_corpus"))
GUIDELINE_DIR = Path(os.getenv("TB_GUIDELINE_DIR", "/data/vaidyx/tb_resources/guidelines"))

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
OCR_MAX_SIDE = int(os.getenv("TB_OCR_MAX_SIDE", "1800"))
