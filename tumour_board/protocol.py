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
        if f.name == "facts.json":
            continue
        p = json.loads(f.read_text())
        out.append({"id": p["id"], "label": p["label"], "version": p.get("version"), "note": p.get("note"), "settings": p.get("settings") or []})
    return out


def settings(protocol_id):
    """The NCG settings a Case File under this protocol can be listed with (chosen by the clinician, V1 item 2.5)."""
    return get(protocol_id).get("settings") or []


def exists(protocol_id):
    return bool(protocol_id) and (config.PROTOCOL_DIR / f"{protocol_id}.json").exists() and protocol_id != "facts"


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
