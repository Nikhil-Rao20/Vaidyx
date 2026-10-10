"""Load the configurable fact catalogue and per-cancer Pre-Authorization protocols (tumour_board/protocols/*.json)."""
import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def catalogue():
    return json.loads((config.PROTOCOL_DIR / "facts.json").read_text())


def doc_types():
    return catalogue()["doc_types"]


def facts():
    return catalogue()["facts"]


def list_protocols():
    out = []
    for f in sorted(config.PROTOCOL_DIR.glob("*.json")):
        p = json.loads(f.read_text())
        if not _is_protocol(p):  # facts.json and the lexicons (dates, units, document type keywords) live in the same folder
            continue
        out.append({"id": p["id"], "label": p["label"], "version": p.get("version"), "note": p.get("note"), "settings": p.get("settings") or []})
    return out


def settings(protocol_id):
    """The NCG settings a Case File under this protocol can be listed with (chosen by the clinician, V1 item 2.5)."""
    return get(protocol_id).get("settings") or []


def _is_protocol(p) -> bool:
    return isinstance(p, dict) and "id" in p and "mandatory" in p


def exists(protocol_id):
    f = config.PROTOCOL_DIR / f"{protocol_id}.json"
    if not protocol_id or not f.exists():
        return False
    try:
        return _is_protocol(json.loads(f.read_text()))
    except (ValueError, OSError):
        return False


def get(protocol_id):
    return json.loads((config.PROTOCOL_DIR / f"{protocol_id}.json").read_text())


def facts_for_doc(protocol_id, doc_type):
    """Fact ids worth extracting from a document of this type under this protocol."""
    p = get(protocol_id)
    cat = facts()
    wanted = list(dict.fromkeys(p.get("extract_facts", [])))
    for r in p["mandatory"]:
        wanted += [f for f in r.get("required_facts", []) if f not in wanted]
    return [f for f in wanted if f in cat and (doc_type in cat[f]["doc_types"] or doc_type == "other")]
