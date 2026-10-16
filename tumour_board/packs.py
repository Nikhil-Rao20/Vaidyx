"""Specialty knowledge packs (V1 item 5.5).

protocols/specialty_packs.json maps each specialty agent (agents.ROLES) to the guideline folders it may search, Indian
sources first (NCG, ICMR, TMC, PM-JAY, ICRI / IRIA before ESMO, NICE, CAP, ACR ...), and gives a short reporting checklist
per protocol: element names, each with the page and a verbatim line of the source document. Organisation and region come
from guidelines.SOURCES (per folder), never from the pack file.

Reference only: a checklist lets an agent note which reporting elements the Case File records do not document. It is never
used to interpret images, stage, diagnose or recommend treatment, and guideline text is never a fact about the patient.
"""
import json

from . import config, guidelines, protocol

PACK_FILE = "specialty_packs.json"
_cache = {"mtime": None, "data": None}


def _path():
    return config.PROTOCOL_DIR / PACK_FILE


def _region(folder):
    return guidelines.SOURCES[folder][1]


def _org(folder):
    return guidelines.SOURCES[folder][0]


def _validate(data):
    """Raise ValueError naming the pack and the problem; return data unchanged when valid."""
    from .agents import ROLES  # lazy: agents imports packs
    if not isinstance(data, dict) or not isinstance(data.get("packs"), dict):
        raise ValueError(f"{PACK_FILE}: no 'packs' object")
    packs = data["packs"]
    missing = [r for r in ROLES if r not in packs]
    if missing:
        raise ValueError(f"{PACK_FILE}: no pack for role(s) {', '.join(missing)}")
    protocol_ids = {p["id"] for p in protocol.list_protocols()}
    for role, pk in packs.items():
        if not isinstance(pk, dict) or not pk.get("label"):
            raise ValueError(f"pack {role}: no label")
        sources = pk.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"pack {role}: no sources")
        seen_intl = None
        for s in sources:
            folder = s.get("folder") if isinstance(s, dict) else None
            if folder not in guidelines.SOURCES:
                raise ValueError(f"pack {role}: unknown guideline folder {folder!r}")
            files = s.get("files")
            if files is not None and (not isinstance(files, list) or not files or not all(isinstance(f, str) and f and "/" not in f for f in files)):
                raise ValueError(f"pack {role}: 'files' of folder {folder} must be a non-empty list of file names")
            if _region(folder) == "India":
                if seen_intl:
                    raise ValueError(f"pack {role}: Indian source {folder} listed after international source {seen_intl}")
            elif seen_intl is None:
                seen_intl = folder
        checklists = pk.get("checklists")
        if not isinstance(checklists, dict):
            raise ValueError(f"pack {role}: 'checklists' must be an object (empty when there is none)")
        for pid, cl in checklists.items():
            if pid not in protocol_ids:
                raise ValueError(f"pack {role}: checklist {pid!r} is not a protocol")
            if not isinstance(cl, dict) or not cl.get("title") or not cl.get("file"):
                raise ValueError(f"pack {role}: checklist {pid} needs a title and a file")
            folder = cl["file"].split("/")[0]
            if "/" not in cl["file"] or folder not in guidelines.SOURCES:
                raise ValueError(f"pack {role}: checklist {pid} file {cl['file']!r} is not in a known guideline folder")
            items = cl.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError(f"pack {role}: checklist {pid} has no items")
            for i, it in enumerate(items, 1):
                if not isinstance(it, dict) or not str(it.get("text") or "").strip():
                    raise ValueError(f"pack {role}: checklist {pid} item {i} has no text")
                page = it.get("page")
                if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                    raise ValueError(f"pack {role}: checklist {pid} item {i} ({it['text']}) has no page")
                if not str(it.get("quote") or "").strip():
                    raise ValueError(f"pack {role}: checklist {pid} item {i} ({it['text']}) has no quote")
    return data


def load():
    """The validated pack file, cached on its modification time."""
    p = _path()
    mtime = (str(p), p.stat().st_mtime_ns)
    if _cache["mtime"] != mtime:
        data = _validate(json.loads(p.read_text()))
        _cache.update(mtime=mtime, data=data)
    return _cache["data"]


def _raw(role):
    packs = load()["packs"]
    if role not in packs:
        raise KeyError(role)
    return packs[role]


def _pages(items):
    pages = sorted({it["page"] for it in items})
    return f"p. {pages[0]}" if len(pages) == 1 else f"pp. {pages[0]}-{pages[-1]}"


def pack(role):
    """{"role", "label", "sources": [{"folder", "files", "org", "region"}], "checklists", "checklist_note"}; KeyError if unknown."""
    pk = _raw(role)
    return {"role": role, "label": pk["label"],
            "sources": [{"folder": s["folder"], "files": list(s["files"]) if s.get("files") else None,
                         "org": _org(s["folder"]), "region": _region(s["folder"])} for s in pk["sources"]],
            "checklists": {pid: checklist(role, pid) for pid in pk["checklists"]},
            "checklist_note": pk.get("checklist_note", "")}


def allowed_sources(role):
    """[(folder, frozenset(file names) or None)] in pack order: the guideline search filter for this agent."""
    return [(s["folder"], frozenset(s["files"]) if s.get("files") else None) for s in _raw(role)["sources"]]


def checklist(role, protocol_id):
    """The checklist of this role for this protocol, plus "org" and "region" of its file's folder; None when there is none."""
    cl = _raw(role)["checklists"].get(protocol_id)
    if not cl:
        return None
    folder = cl["file"].split("/")[0]
    return {**cl, "items": [dict(it) for it in cl["items"]], "org": _org(folder), "region": _region(folder),
            "pages": _pages(cl["items"])}


def checklist_text(role, protocol_id):
    """A short prompt block listing the reporting elements, or "" when this role has no checklist for the protocol."""
    cl = checklist(role, protocol_id)
    if not cl:
        return ""
    head = (f"REPORTING CHECKLIST (reference: {cl['title']}, {cl['region']}, {cl['pages']}). Use it only to note which elements "
            "the reports do not document; never to interpret images, stage or recommend:")
    return "\n".join([head] + [f"- {it['text']}" for it in cl["items"]])


def describe():
    """Per role, for the UI and docs: label, source organisations in order with region, checklist titles per protocol."""
    out = []
    for role in load()["packs"]:
        pk = pack(role)
        out.append({"role": role, "label": pk["label"],
                    "sources": [{"folder": s["folder"], "org": s["org"], "region": s["region"], "files": s["files"]} for s in pk["sources"]],
                    "checklists": {pid: {"title": cl["title"], "org": cl["org"], "region": cl["region"], "pages": cl["pages"],
                                         "items": len(cl["items"])} for pid, cl in pk["checklists"].items()},
                    "checklist_note": pk["checklist_note"]})
    return out


def search(role, q, cancer=None, india=3, intl=2):
    """Guideline passages from this role's pack only, Indian sources first: {"india": [...], "international": [...]}. Reference text
    for the board, never a recommendation for this patient (bibliography passages dropped, as in guidelines.search_grouped)."""
    hits = [h for h in guidelines.index().search(q, 60, cancer, sources=allowed_sources(role)) if not guidelines._is_reference_list(h["text"])]
    return {"india": [h for h in hits if h["region"] == "India"][:india], "international": [h for h in hits if h["region"] != "India"][:intl]}
