"""Published cases (18 Oct, SPEC 3.5; owner exception of 17 Oct): a paper the doctor picks is shown with its authors, journal, year, link and
peer-review status, and its procedure and conclusion only as verbatim quotes the doctor pastes from the paper, labelled "Published case, not
advice for this patient". Vaidyx never applies it to the patient and computes no similarity.

Search: the local library first (the guideline index over /data/vaidyx/tb_resources, marked source "local"; guideline and consensus
documents, so not peer-reviewed papers), then PubMed E-utilities (esearch + esummary, tool "vaidyx-tb") and Europe PMC REST, with the
doctor's search words only: patient identifiers (name, UHID, IP / OP No., long digit runs) are refused before anything leaves the server.
Every search is logged in the Case File audit ("published_search", the words) and in the file. 15 s per call; a failing source returns
{results: [], error}. Items live in cases/<id>/published.json."""
import asyncio
import logging
import re
import threading
import uuid

import httpx

from . import guidelines, store

log = logging.getLogger("tumour_board")

FILE = "published.json"
LABEL = "Published case, not advice for this patient"
TOOL = "vaidyx-tb"
TIMEOUT = 15.0
RETMAX = 10
MAX_ITEMS = 50
MAX_QUOTES = 20
MAX_QUOTE, MAX_WHERE = 2000, 200
SOURCES = ("local", "pubmed", "europepmc", "manual")
KINDS = ("paper", "preprint", "white_paper", "book", "guideline")
PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_DIGITS = re.compile(r"\d{6,}")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
_URL = re.compile(r"^https?://[^\s]+$", re.I)
_lock = threading.Lock()


class PublishedError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _client():
    """One async client per search (tests replace it with an httpx.MockTransport)."""
    return httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": f"{TOOL}/1.0"})


def _path(case_id):
    return store.case_dir(case_id) / FILE


def load(case_id) -> dict:
    data = store._read_json(_path(case_id), {"items": [], "searches": []}) or {}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    if not isinstance(data.get("searches"), list):
        data["searches"] = []
    return data


def save(case_id, data) -> None:
    store._write_json(_path(case_id), data)


# ---- the search words ---------------------------------------------------------------------------------------------------------------

def _identifiers(case) -> list:
    p = (case or {}).get("patient") or {}
    out = []
    for v in (p.get("mrn"), p.get("name")):
        if v:
            out.append(str(v))
    for x in p.get("ids") or []:
        if isinstance(x, dict) and x.get("value"):
            out.append(str(x["value"]))
    his = (case or {}).get("his") or {}
    for k in ("uhid", "patient_id"):
        if his.get(k):
            out.append(str(his[k]))
    return out


def check_terms(case, terms) -> str:
    """The search words, cleaned; PublishedError when they are empty, too long or carry a patient identifier (name parts, UHID, IP / OP No.,
    a run of six or more digits)."""
    t = " ".join(str(terms or "").split())
    if len(t) < 2:
        raise PublishedError("Type the search words (the diagnosis, the procedure, the question).")
    if len(t) > 200:
        raise PublishedError("Search words are limited to 200 characters.")
    if not re.search(r"[A-Za-z]{2,}", t):
        raise PublishedError("Search words need at least one word.")
    low = t.lower()
    words = set(low.split())
    for ident in _identifiers(case):
        il = ident.lower()
        if il in low:  # the whole identifier (UHID, IP / OP No.) anywhere in the words
            raise PublishedError("Search words must not carry a patient identifier (name, UHID, IP / OP No.).")
        for part in re.split(r"[\s,/]+", il):
            if len(part) < 3:
                continue
            if part.isalpha():  # a name part: as a whole word
                if part in words:
                    raise PublishedError("Search words must not carry a patient identifier (name, UHID, IP / OP No.).")
            elif len(part) >= 5 and part in low:  # a number or mixed part of an identifier (not a four-digit year)
                raise PublishedError("Search words must not carry a patient identifier (name, UHID, IP / OP No.).")
    if _DIGITS.search(t):
        raise PublishedError("Search words must not carry an identifier (a long number).")
    return t


# ---- the sources --------------------------------------------------------------------------------------------------------------------

def _result(**kw) -> dict:
    base = {"title": "", "authors": "", "journal": "", "year": "", "doi": "", "url": "", "source": "manual", "source_id": "", "peer_reviewed": False,
            "kind": "paper", "snippet": "", "where": "", "note": ""}
    base.update({k: v for k, v in kw.items() if v is not None})
    return base


def search_local(case, terms, k=RETMAX) -> list:
    """Passages of the local library (guideline index) for the words: reference documents from Indian and international bodies, each with
    its file and page; never a peer-reviewed paper. [] while the index is not loaded (it is never built for a search)."""
    if not guidelines.ready():
        return []
    hits = [h for h in guidelines.index().search(terms, k * 3, (case or {}).get("protocol")) if not guidelines._is_reference_list(h.get("text") or "")]
    out, seen = [], set()
    for h in hits:
        key = (h.get("file"), h.get("page"))
        if key in seen:
            continue
        seen.add(key)
        out.append(_result(title=h.get("title") or h.get("file") or "", authors=h.get("org") or "", journal=h.get("org") or "", year="", doi="",
                           url="/api/tb/guidelines/file?path=" + str(h.get("file") or ""), source="local", source_id=f"{h.get('file')}#p{h.get('page')}",
                           peer_reviewed=False, kind="guideline", snippet=(h.get("text") or "")[:600], where=f"p. {h.get('page')}", region=h.get("region") or "",
                           note="Guideline or consensus document from the local library, not a peer-reviewed paper"))
        if len(out) >= k:
            break
    return out


def _pubmed_kind(pubtypes) -> tuple:
    kinds = {str(x).lower() for x in pubtypes or []}
    if any("preprint" in x for x in kinds):
        return "preprint", False
    if any("book" in x for x in kinds):
        return "book", False
    return "paper", True


async def search_pubmed(client, terms, k=RETMAX) -> list:
    r = await client.get(PUBMED + "esearch.fcgi", params={"db": "pubmed", "term": terms, "retmax": k, "retmode": "json", "sort": "relevance", "tool": TOOL})
    r.raise_for_status()
    ids = [str(x) for x in ((r.json().get("esearchresult") or {}).get("idlist") or [])][:k]
    if not ids:
        return []
    s = await client.get(PUBMED + "esummary.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "json", "tool": TOOL})
    s.raise_for_status()
    res = s.json().get("result") or {}
    out = []
    for pmid in res.get("uids") or ids:
        d = res.get(pmid)
        if not isinstance(d, dict):
            continue
        doi = next((a.get("value") for a in d.get("articleids") or [] if isinstance(a, dict) and a.get("idtype") == "doi"), "") or ""
        kind, peer = _pubmed_kind(d.get("pubtype"))
        year = str(d.get("pubdate") or "")[:4]
        out.append(_result(title=d.get("title") or "", authors=", ".join(a.get("name") or "" for a in d.get("authors") or [] if isinstance(a, dict))[:500],
                           journal=d.get("fulljournalname") or d.get("source") or "", year=year if year.isdigit() else "", doi=doi,
                           url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", source="pubmed", source_id=pmid, pmid=pmid, peer_reviewed=peer, kind=kind,
                           pubtypes=list(d.get("pubtype") or [])))
    return out


def _epmc_kind(d) -> tuple:
    src = str(d.get("source") or "").upper()
    types = str(d.get("pubType") or "").lower()
    if src == "PPR" or "preprint" in types:
        return "preprint", False
    if src == "BOOKS" or "book" in types:
        return "book", False
    return "paper", True


async def search_europepmc(client, terms, k=RETMAX) -> list:
    r = await client.get(EUROPEPMC, params={"query": terms, "format": "json", "pageSize": k, "resultType": "lite"})
    r.raise_for_status()
    out = []
    for d in ((r.json().get("resultList") or {}).get("result") or [])[:k]:
        if not isinstance(d, dict):
            continue
        kind, peer = _epmc_kind(d)
        src, ident = str(d.get("source") or ""), str(d.get("id") or "")
        url = f"https://pubmed.ncbi.nlm.nih.gov/{d['pmid']}/" if d.get("pmid") else f"https://europepmc.org/article/{src}/{ident}" if src and ident else ""
        out.append(_result(title=d.get("title") or "", authors=str(d.get("authorString") or "")[:500], journal=d.get("journalTitle") or "",
                           year=str(d.get("pubYear") or "")[:4], doi=d.get("doi") or "", url=url, source="europepmc", source_id=f"{src}:{ident}",
                           pmid=str(d.get("pmid") or ""), peer_reviewed=peer, kind=kind, pubtypes=[d.get("pubType")] if d.get("pubType") else []))
    return out


async def search(case_id, terms, user) -> dict:
    """{results[], counts{local, pubmed, europepmc}, error} for the doctor's words; logged in the audit with the words."""
    case = store.get_case(case_id)
    if not case:
        raise PublishedError("Case File not found.", 404)
    t = check_terms(case, terms)
    results, errors, counts = [], [], {"local": 0, "pubmed": 0, "europepmc": 0}
    try:
        local = await asyncio.to_thread(search_local, case, t)
        counts["local"] = len(local); results += local
    except Exception as e:
        errors.append(f"local library: {e.__class__.__name__}")
        log.warning("published search (local) failed: %s", e)
    seen = set()
    async with _client() as client:
        for name, fn in (("pubmed", search_pubmed), ("europepmc", search_europepmc)):
            try:
                rows = await fn(client, t)
            except Exception as e:
                errors.append(f"{'PubMed' if name == 'pubmed' else 'Europe PMC'}: {e.__class__.__name__}")
                log.warning("published search (%s) failed: %s", name, e)
                continue
            kept = []
            for x in rows:
                key = (x.get("doi") or "").lower() or (f"pmid:{x['pmid']}" if x.get("pmid") else (x.get("title") or "").lower()[:80])
                if key in seen:
                    continue
                seen.add(key); kept.append(x)
            counts[name] = len(kept); results += kept
    with _lock:
        data = load(case_id)
        data["searches"].append({"by": user, "at": store.now_iso(), "terms": t, "counts": counts, "errors": errors})
        data["searches"] = data["searches"][-100:]
        save(case_id, data)
    store.audit(case_id, {"kind": "published_search", "by": user, "terms": t, "counts": counts, "errors": errors})
    return {"results": results, "counts": counts, "error": "; ".join(errors) if errors else "", "terms": t, "label": LABEL}


# ---- the items ----------------------------------------------------------------------------------------------------------------------

def _clean_quotes(quotes) -> list:
    out = []
    for q in quotes or []:
        if isinstance(q, str):
            q = {"text": q}
        if not isinstance(q, dict):
            continue
        text = str(q.get("text") or "").strip()  # stored as pasted (verbatim); only the ends are trimmed
        if not text:
            continue
        if len(text) > MAX_QUOTE:
            raise PublishedError(f"A quote is limited to {MAX_QUOTE} characters.")
        out.append({"text": text, "where": " ".join(str(q.get("where") or "").split())[:MAX_WHERE], "label": str(q.get("label") or "")[:40]})
    if len(out) > MAX_QUOTES:
        raise PublishedError(f"At most {MAX_QUOTES} quotes per paper.")
    return out


def validate_result(res) -> dict:
    if not isinstance(res, dict):
        raise PublishedError("Give the paper as an object (a search result, or title, authors, journal, year, url).")
    title = " ".join(str(res.get("title") or "").split())[:500]
    if not title:
        raise PublishedError("The paper needs a title.")
    source = str(res.get("source") or "manual")
    if source not in SOURCES:
        raise PublishedError(f"Unknown source {source!r}.")
    kind = str(res.get("kind") or "paper")
    if kind not in KINDS:
        raise PublishedError(f"Unknown kind {kind!r}.")
    url = str(res.get("url") or "").strip()
    if url and not (_URL.match(url) or url.startswith("/api/tb/guidelines/file?path=")):
        raise PublishedError("The link must be an http(s) URL.")
    doi = str(res.get("doi") or "").strip()
    if doi and not _DOI.match(doi):
        raise PublishedError("That is not a DOI (10.xxxx/...).")
    year = str(res.get("year") or "").strip()[:4]
    if year and not year.isdigit():
        raise PublishedError("The year must be four digits.")
    return {"title": title, "authors": " ".join(str(res.get("authors") or "").split())[:500], "journal": " ".join(str(res.get("journal") or "").split())[:200],
            "year": year, "doi": doi, "url": url, "source": source, "source_id": str(res.get("source_id") or "")[:200], "pmid": str(res.get("pmid") or "")[:20],
            "peer_reviewed": bool(res.get("peer_reviewed")), "kind": kind, "snippet": str(res.get("snippet") or "")[:600], "where": str(res.get("where") or "")[:200],
            "note": str(res.get("note") or "")[:300]}


def add(case_id, result, quotes, user) -> dict:
    """The doctor adds a paper (the quotes are verbatim text pasted from it, with where they come from). Audited "published_added"."""
    clean = validate_result(result)
    qs = _clean_quotes(quotes)
    from .slots import display_name
    item = {"id": "P" + uuid.uuid4().hex[:8], **clean, "quotes": qs, "added_by": user, "by_name": display_name(user), "at": store.now_iso(), "label": LABEL}
    with _lock:
        data = load(case_id)
        if len(data["items"]) >= MAX_ITEMS:
            raise PublishedError(f"At most {MAX_ITEMS} published cases per Case File; remove one first.", 409)
        dup = next((x for x in data["items"] if (clean["doi"] and x.get("doi", "").lower() == clean["doi"].lower()) or (clean["url"] and x.get("url") == clean["url"])), None)
        if dup:
            raise PublishedError("This paper is already on the Case File.", 409)
        data["items"].append(item)
        save(case_id, data)
    store.audit(case_id, {"kind": "published_added", "by": user, "item": item["id"], "title": item["title"][:200], "source": item["source"], "doi": item["doi"],
                          "peer_reviewed": item["peer_reviewed"], "quotes": len(qs)})
    return item


def add_quotes(case_id, item_id, quotes, user) -> dict:
    qs = _clean_quotes(quotes)
    with _lock:
        data = load(case_id)
        item = next((x for x in data["items"] if x.get("id") == item_id), None)
        if not item:
            raise PublishedError("Published case not found.", 404)
        if len(item.get("quotes") or []) + len(qs) > MAX_QUOTES:
            raise PublishedError(f"At most {MAX_QUOTES} quotes per paper.")
        item.setdefault("quotes", []).extend(qs)
        save(case_id, data)
    store.audit(case_id, {"kind": "published_quotes_added", "by": user, "item": item_id, "quotes": len(qs)})
    return item


def remove(case_id, item_id, user) -> dict:
    with _lock:
        data = load(case_id)
        item = next((x for x in data["items"] if x.get("id") == item_id), None)
        if not item:
            raise PublishedError("Published case not found.", 404)
        data["items"] = [x for x in data["items"] if x.get("id") != item_id]
        save(case_id, data)
    store.audit(case_id, {"kind": "published_removed", "by": user, "item": item_id, "title": (item.get("title") or "")[:200]})
    return item


def view(case_id) -> dict:
    data = load(case_id)
    return {"items": data["items"], "searches": data["searches"][-20:], "label": LABEL}
