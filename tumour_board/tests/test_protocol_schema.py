"""Every checklist (protocol) file parses and holds together, and every source line is found on its cited page of its book
(night-v3 item 2.1, the groundwork for the Phase 2 cancer checklists).

Structure, for every protocol in config.PROTOCOL_DIR: record ids unique, tiers valid against the file's settings, facts and document
types in the catalogue (facts.json), every department resolves (a department, the owning team or the MDT Coordinator), every required
record cites a source. A Phase 2 draft (version "0.1-draft", approval "draft", not cup) also names the book file of every source with a
PDF page (or "n/a" and where, for the Word books) and carries no em or en dash outside its verbatim quotes.

Quotes: every source with a `file` is looked up in that book (whitespace folded): on its PDF page through pypdf, or anywhere in the text
of a .docx. Skipped when the guideline library or pypdf is not on this machine."""
import html
import json
import re
import zipfile
from functools import lru_cache

import pytest

from tumour_board import config, org, protocol

DASHES = ("\u2014", "\u2013")
_LEXICONS = {"facts", "dates", "units", "doc_type_keywords", "his_codes", "dose_references", "specialty_packs"}


def _protocol_files():
    """{protocol id: None, or the reason the file does not parse}: every .json of the folder that is a protocol, plus any file that
    does not parse at all (a half-written checklist must fail here, not break the whole test collection)."""
    out = {}
    for f in sorted(config.PROTOCOL_DIR.glob("*.json")):
        if f.stem in _LEXICONS:
            continue
        try:
            d = json.loads(f.read_text())
        except ValueError as e:
            out[f.stem] = f"{e.__class__.__name__}: {e}"
            continue
        if isinstance(d, dict) and "id" in d and ("records" in d or "mandatory" in d):
            out[f.stem] = None
    return out


FILES = _protocol_files()
PIDS = sorted(k for k, v in FILES.items() if v is None)


def _draft_pids():
    out = []
    for pid in PIDS:
        try:
            if _is_phase2_draft(protocol.get(pid)):
                out.append(pid)
        except (OSError, ValueError):
            continue
    return out


def _fold(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _all_records(p):
    return [("records", r) for r in p.get("records") or []] + [("optional", r) for r in p.get("optional") or []]


def _sources(r):
    return list(r.get("sources") or ([r["source"]] if r.get("source") else []))


def _is_phase2_draft(p) -> bool:
    return p.get("id") != "cup" and p.get("version") == "0.1-draft" and (p.get("approval") or {}).get("status") == "draft"


def _strings_outside_quotes(node, path=""):
    """(path, text) of every string in the file except the values of `quote` keys (a book's own dash stays verbatim)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "quote":
                continue
            yield from _strings_outside_quotes(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings_outside_quotes(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_there_are_protocols():
    assert {"breast", "cervix", "colorectal_rectum", "cup", "generic", "lung_nsclc", "oral_cavity"} <= set(PIDS)


@pytest.mark.parametrize("name", sorted(FILES))
def test_every_protocol_file_parses(name):
    assert FILES[name] is None, f"{name}.json: {FILES[name]}"
    p = protocol.get(name)
    assert p["id"] == name, f"{name}.json carries id {p['id']}"  # the file name is the id (protocol.get reads <id>.json)
    assert name in {x["id"] for x in protocol.list_protocols()}


@pytest.mark.parametrize("pid", PIDS)
def test_protocol_structure(pid):
    p = protocol.get(pid)
    assert protocol.exists(pid) and p["id"] == pid and p.get("label")
    settings = {s["id"] for s in p.get("settings") or []}
    cat, doc_types = protocol.facts(), set(protocol.doc_types())
    tiers_ok = (*protocol.TIERS, "none")
    ids = [r.get("id") for _, r in _all_records(p)]
    assert all(ids) and len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    bad = []
    for kind, r in _all_records(p):
        rid = r["id"]
        if kind == "records" or "tier" in r:
            if r.get("tier") not in protocol.TIERS:
                bad.append((rid, "tier", r.get("tier")))
        for s, t in (r.get("tiers") or {}).items():
            if s not in settings or t not in tiers_ok:
                bad.append((rid, "tiers", s, t))
        for f in r.get("required_facts") or []:
            if f not in cat:
                bad.append((rid, "fact not in facts.json", f))
        for t in list(r.get("doc_types") or []) + list(r.get("fact_doc_types") or []):
            if t not in doc_types:
                bad.append((rid, "document type not in facts.json", t))
        dept = r.get("department")
        if not (org.department_id(dept) or org.is_owner_alias(dept) or org.is_coordinator_name(dept)):
            bad.append((rid, "department does not resolve", dept))
        if kind == "records" and not _sources(r):
            bad.append((rid, "no source"))
        for src in _sources(r):
            if not _fold(src.get("quote")):
                bad.append((rid, "empty quote"))
    assert bad == [], bad


@pytest.mark.parametrize("pid", _draft_pids())
def test_phase2_draft_sources_and_text(pid):
    p = protocol.get(pid)
    raw = (config.PROTOCOL_DIR / f"{pid}.json").read_text()
    bad = []
    for _, r in _all_records(p):
        for src in _sources(r):
            f = src.get("file")
            if not isinstance(f, str) or not f or f.startswith("/") or ".." in f.split("/"):
                bad.append((r["id"], "file", f))
            elif config.GUIDELINE_DIR.is_dir() and not (config.GUIDELINE_DIR / f).is_file():
                bad.append((r["id"], "file not in the guideline library", f))
            page = src.get("page")
            if not ((isinstance(page, int) and not isinstance(page, bool) and page >= 1) or (page == "n/a" and src.get("where"))):
                bad.append((r["id"], "page", page))
    dashed = [(where, text) for where, text in _strings_outside_quotes(json.loads(raw)) if any(d in text for d in DASHES)]
    assert bad == [], bad
    assert dashed == [], dashed


# ---- every quote is in its book -------------------------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _pdf_pages(path: str) -> tuple:
    from pypdf import PdfReader
    return tuple(_fold(pg.extract_text() or "") for pg in PdfReader(path).pages)


@lru_cache(maxsize=None)
def _docx_texts(path: str) -> tuple:
    """The Word book's text two ways: paragraphs with their runs joined (tags stripped) and every tag read as a space."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf8", "replace")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    joined = " ".join(html.unescape(re.sub(r"<[^>]+>", "", x)) for x in paras)
    spaced = html.unescape(re.sub(r"<[^>]+>", " ", xml))
    return _fold(joined), _fold(spaced)


def _found(src) -> str:
    """'' when the quote is in its book at the cited place, else the reason."""
    path = config.GUIDELINE_DIR / src["file"]
    if not path.is_file():
        return "file not found"
    q = _fold(src.get("quote"))
    if path.suffix.lower() == ".docx":
        return "" if any(q in t for t in _docx_texts(str(path))) else "not in the document"
    if path.suffix.lower() == ".pdf":
        pages = _pdf_pages(str(path))
        page = src.get("page")
        if not isinstance(page, int) or not 1 <= page <= len(pages):
            return f"page {page} not in the book ({len(pages)} pages)"
        return "" if q in pages[page - 1] else f"not on page {page}"
    return f"unknown book format {path.suffix}"


@pytest.mark.parametrize("pid", PIDS)
def test_every_source_line_is_on_its_cited_page(pid):
    if not config.GUIDELINE_DIR.is_dir():
        pytest.skip("guideline library not on this machine")
    pytest.importorskip("pypdf")
    p = protocol.get(pid)
    srcs = [(r["id"], s) for _, r in _all_records(p) for s in _sources(r) if s.get("file")]
    if not srcs:
        pytest.skip(f"{pid}: no source names its book file (written before night-v3)")
    missing = [(rid, s.get("page"), why, _fold(s.get("quote"))[:80]) for rid, s in srcs if (why := _found(s))]
    assert missing == [], missing
