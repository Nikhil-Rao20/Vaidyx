"""Load the configurable fact catalogue and per-cancer Pre-Authorization protocols (tumour_board/protocols/*.json).

Each protocol lists its required records under `records` (older files: `mandatory`; both keys are read). Every record
carries its NCG tier (a = Essential, b = Optimal, c = Optional), optionally per NCG setting in `tiers`, and the NCG quote
and page it rests on in `source` / `sources` (V1 item 4.1). The gate decides what is required with `required()`."""
import json
from functools import lru_cache

from . import config

TIERS = ("a", "b", "c")
TIER_LABEL = {"a": "Essential", "b": "Optimal", "c": "Optional", "none": "Not applicable"}
STRICTNESS = {"a": 3, "b": 2, "c": 1, "none": 0}
# A cancer with no built checklist (a typed name, or a listed cancer not built yet): four core records (owner decision R05-Q04,
# protocols/generic.json). The cancer's name is kept on the Case File as the doctor wrote it (case.json "cancer_name").
GENERIC = "generic"
GENERIC_HAEM = "generic_haem"  # the blood cancer variant (night-v3 item 2.9): marrow, flow cytometry or cytogenetics instead of staging imaging
GENERIC_IDS = frozenset({GENERIC, GENERIC_HAEM})
NO_CHECKLIST = "no checklist yet"
NO_PROTOCOL_LABEL = "No disease-specific Indian protocol"


def case_label(case, label: str = "") -> str:
    """How a list names the cancer of a Case File: "<cancer name> (no checklist yet)" under the generic rule when the name is recorded,
    else `label` (the protocol's label as the caller already has it) or the protocol's own label; "" for a Case File not listed yet."""
    case = case if isinstance(case, dict) else {}
    pid = str(case.get("protocol") or "")
    name = " ".join(str(case.get("cancer_name") or "").split())
    if pid in GENERIC_IDS and name:
        return f"{name} ({NO_CHECKLIST})"
    if label or not pid:
        return label
    try:
        return get(pid).get("label") or pid
    except (OSError, ValueError, TypeError):
        return pid


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


def setting_label(protocol_id, setting) -> str:
    """The label of an NCG setting of this protocol; "" when the protocol or the setting is unknown."""
    if not setting:
        return ""
    try:
        sets = settings(protocol_id)
    except (OSError, ValueError, TypeError):
        return ""
    return next((s.get("label") or "" for s in sets if isinstance(s, dict) and s.get("id") == setting), "")


def _is_protocol(p) -> bool:
    return isinstance(p, dict) and "id" in p and ("records" in p or "mandatory" in p)


def exists(protocol_id):
    f = config.PROTOCOL_DIR / f"{protocol_id}.json"
    if not protocol_id or not f.exists():
        return False
    try:
        return _is_protocol(json.loads(f.read_text()))
    except (ValueError, OSError):
        return False


def _normalise(p):
    """Make `records` and `mandatory` the same list (many modules still read `mandatory`), default every record's tier to
    "a" (legacy files carry no tiers: everything they list stays required) and give each record both `source` (the first
    NCG line) and `sources` (all of them). Idempotent; changes the dict in place and returns it."""
    if not isinstance(p, dict):
        return p
    recs = p.get("records") or p.get("mandatory") or []
    p["records"] = recs
    p["mandatory"] = recs
    for r in recs:
        if not isinstance(r, dict):
            continue
        r.setdefault("tier", "a")
        if r.get("sources") and not r.get("source"):
            r["source"] = r["sources"][0]
        elif r.get("source") and not r.get("sources"):
            r["sources"] = [r["source"]]
    return p


def get(protocol_id):
    return _normalise(json.loads((config.PROTOCOL_DIR / f"{protocol_id}.json").read_text()))


def records(prot) -> list:
    """The required records of a protocol (a protocol dict or its id), normalised: see `_normalise`."""
    p = get(prot) if isinstance(prot, str) else prot
    return _normalise(p).get("records", []) if isinstance(p, dict) else []


def tier_for(rec, setting) -> str:
    """The NCG tier of a record ("a", "b", "c" or "none" = not applicable) for the Case File's NCG setting.

    With a setting the record names in `tiers`, that tier. When the coordinator has not recorded the setting yet and the
    record's tier varies by setting, the strictest of its settings applies (a > b > c > none): a record that is
    Essential in any setting is then still asked for, so nothing is silently dropped because a field was left empty;
    once the setting is recorded the record relaxes to that setting's tier. A setting the record's `tiers` does not name
    (a renamed or unknown setting id) is treated like an unrecorded one. Otherwise the record's own `tier` ("a" when a
    legacy file gives none)."""
    tiers = rec.get("tiers") or {}
    if setting and setting in tiers:
        return tiers[setting]
    if tiers:
        return max(tiers.values(), key=lambda t: STRICTNESS.get(t, 0))
    return rec.get("tier", "a")


def required(rec, setting, hospital_level) -> bool:
    """Whether the gate requires this record: Essential (a) everywhere; Optimal (b) only at a hospital whose org.json
    level is "optimal"; Optional (c) and not applicable never. The tier comes from `tier_for`, so an unrecorded setting
    falls back to the strictest tier (safer: a record is never silently dropped)."""
    t = tier_for(rec, setting)
    return t == "a" or (t == "b" and hospital_level == "optimal")


def facts_for_doc(protocol_id, doc_type):
    """Fact ids worth extracting from a document of this type under this protocol. A document of type `other` (anything the
    catalogue does not name) is asked only for the protocol's required fields, not the whole extraction list (V1 item 3.2).
    Required fields are collected from every record whatever its tier: an Optimal or Optional record's value is still
    shown when the document carries it."""
    p = get(protocol_id)
    cat = facts()
    required_facts = list(dict.fromkeys(f for r in records(p) for f in r.get("required_facts", [])))
    if doc_type == "other":
        return [f for f in required_facts if f in cat]
    wanted = list(dict.fromkeys(p.get("extract_facts", [])))
    wanted += [f for f in required_facts if f not in wanted]
    return [f for f in wanted if f in cat and doc_type in cat[f]["doc_types"]]
