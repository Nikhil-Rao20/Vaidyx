"""PubMed client for Ask PubMed (docs/pubmed-ask/DESIGN.md, owner decision of 3 Nov 2026). The only way a paper enters Ask PubMed: every
paper is a PubMed record of the U.S. National Library of Medicine fetched here through NCBI E-utilities (esearch for the ids, efetch XML
for the records); the model never names a paper. Every call keeps its provenance (the request URL without the API key, the time, the
HTTP status, the SHA-256 of the raw bytes), so an answer can be traced back to what PubMed sent.

NCBI policy: tool "vaidyx-tb", a contact email, at most 3 calls a second (10 with an API key). Settings in data/tumour_board/pubmed.json
{"email", "api_key"} or TB_PUBMED_EMAIL / TB_PUBMED_API_KEY; the key is read in code, never logged or shown. One pace for the whole
process. 429, 5xx, time-outs and connection errors are retried with back-off (Retry-After honoured); NCBI's error answers (a JSON "error"
or "ERROR", an XML <ERROR>, a page that is not a PubmedArticleSet) are errors too, never an empty result. XML is parsed with defusedxml.
Abstracts are public records, cached by PMID for 7 days in data/tumour_board/pubmed_cache (no patient data ever goes there)."""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

import httpx
from defusedxml import ElementTree as DET
from defusedxml.common import DefusedXmlException

from . import config

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = "vaidyx-tb"
TIMEOUT = 15.0
DELAYS = (1.0, 2.0, 4.0)  # the waits before the 2nd, 3rd and 4th try
MAX_WAIT = 10.0  # a Retry-After longer than this is cut to it
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_IDS = 200
BATCH = 50
CACHE_DAYS = 7  # a retraction reaches a cached record within a week; the proof tools fetch fresh
CACHE_DIR = config.DATA_ROOT / "pubmed_cache"
SETTINGS = config.DATA_ROOT / "pubmed.json"


class PubMedError(Exception):
    """PubMed gave no usable answer. The message is short and safe to show ("PubMed answered 503 after 4 tries")."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def settings() -> dict:
    s = {}
    try:
        s = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, ValueError):
        s = {}
    if not isinstance(s, dict):
        s = {}
    return {"email": (os.getenv("TB_PUBMED_EMAIL") or str(s.get("email") or "")).strip(),
            "api_key": (os.getenv("TB_PUBMED_API_KEY") or str(s.get("api_key") or "")).strip()}


# ---- the pace: one queue of call times for the whole process (any event loop, any thread) --------------------------------------------
_pace_lock = threading.Lock()
_next_at = 0.0


async def _turn(has_key: bool) -> None:
    global _next_at
    gap = 0.11 if has_key else 0.34
    with _pace_lock:
        now = time.monotonic()
        at = max(now, _next_at)
        _next_at = at + gap
    if at > now:
        await asyncio.sleep(at - now)


def _client() -> httpx.AsyncClient:
    """One client per search or fetch (tests replace it with an httpx.MockTransport)."""
    return httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": f"{TOOL}/1.0"})


def _retry_after(r) -> float:
    try:
        return min(MAX_WAIT, max(0.0, float(r.headers.get("Retry-After") or 0)))
    except ValueError:
        return 0.0


async def _call(client, util: str, params: dict) -> tuple:
    """GET one E-utility with retries. Returns (raw bytes, provenance); PubMedError when every try failed."""
    s = settings()
    q = {**params, "tool": TOOL}
    shown = str(httpx.URL(EUTILS + util, params=q))  # the provenance carries neither the contact email nor the key (it is kept in files)
    if s["email"]:
        q["email"] = s["email"]
    if s["api_key"]:
        q["api_key"] = s["api_key"]
    last, t0 = "", time.time()
    for attempt in range(len(DELAYS) + 1):
        await _turn(bool(s["api_key"]))
        wait = 0.0
        try:
            r = await client.get(EUTILS + util, params=q)
        except httpx.TimeoutException:
            last = f"gave no answer in {TIMEOUT:.0f} s"
        except httpx.HTTPError as e:
            last = f"could not connect ({e.__class__.__name__})"
        else:
            if r.status_code == 200:
                body = r.content
                return body, {"url": shown, "at": now_iso(), "status": 200, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                              "tries": attempt + 1, "seconds": round(time.time() - t0, 2)}
            last = f"answered {r.status_code}" + (" (busy)" if r.status_code == 429 else "")
            if r.status_code not in RETRY_STATUS:
                raise PubMedError(f"PubMed {last}")
            wait = _retry_after(r)
        if attempt < len(DELAYS):
            await asyncio.sleep(max(DELAYS[attempt], wait))
    raise PubMedError(f"PubMed {last} after {len(DELAYS) + 1} tries")


async def _with(client, util, params):
    if client is not None:
        return await _call(client, util, params)
    async with _client() as c:
        return await _call(c, util, params)


# ---- search ---------------------------------------------------------------------------------------------------------------------------
async def search(term: str, *, retmax: int = 20, years: int | None = 10, client=None) -> dict:
    """PubMed's Best Match ids for the words: {term, count, ids, translation, warnings, years, provenance}. years limits the publication
    date to the last n calendar years (this one included); None searches every year."""
    term = " ".join(str(term or "").split())
    if not term:
        raise PubMedError("no search words")
    params = {"db": "pubmed", "term": term, "retmax": max(1, min(int(retmax), MAX_IDS)), "retmode": "json", "sort": "relevance"}
    if years:
        y = datetime.now().year
        params.update(datetype="pdat", mindate=str(y - int(years) + 1), maxdate=str(y))
    body, prov = await _with(client, "esearch.fcgi", params)
    try:
        d = json.loads(body)
    except ValueError:
        raise PubMedError("PubMed sent a search answer that is not JSON") from None
    if not isinstance(d, dict):
        raise PubMedError("PubMed sent an empty search answer")
    if d.get("error"):
        raise PubMedError(f"PubMed: {str(d['error'])[:160]}")
    r = d.get("esearchresult")
    if not isinstance(r, dict):
        raise PubMedError("PubMed sent no search result")
    if r.get("ERROR"):
        raise PubMedError(f"PubMed: {str(r['ERROR'])[:160]}")
    ids = [str(x) for x in r.get("idlist") or [] if str(x).isdigit()]
    count = str(r.get("count") or "0")
    warnings = []
    for k, v in ((r.get("warninglist") or {}).items() if isinstance(r.get("warninglist"), dict) else []):
        if v:
            warnings.append(f"{k}: {', '.join(map(str, v))[:200]}")
    for k, v in ((r.get("errorlist") or {}).items() if isinstance(r.get("errorlist"), dict) else []):
        if v:
            warnings.append(f"{k}: {', '.join(map(str, v))[:200]}")
    return {"term": term, "count": int(count) if count.isdigit() else len(ids), "ids": ids, "translation": str(r.get("querytranslation") or ""),
            "warnings": warnings, "years": years, "provenance": prov}


# ---- records --------------------------------------------------------------------------------------------------------------------------
# Study types, strongest first (from PubMed's publication types, never from the model).
TIERS = [
    (1, "Meta-analysis", {"meta-analysis", "network meta-analysis"}),
    (1, "Systematic review", {"systematic review"}),
    (2, "Randomised trial", {"randomized controlled trial", "equivalence trial", "pragmatic clinical trial"}),
    (2, "Clinical trial", {"clinical trial, phase iii", "clinical trial, phase ii", "clinical trial, phase iv", "clinical trial, phase i",
                           "controlled clinical trial", "clinical trial", "adaptive clinical trial"}),
    (3, "Guideline", {"practice guideline", "guideline", "consensus development conference", "consensus development conference, nih"}),
    (4, "Review", {"review", "scoping review"}),
    (5, "Observational study", {"observational study", "multicenter study", "comparative study", "validation study", "evaluation study",
                                "twin study", "cohort study"}),
    (6, "Case report", {"case reports"}),
    (7, "Comment or letter", {"editorial", "comment", "letter", "news", "interview", "biography", "historical article"}),
]


def study_type(types) -> tuple:
    low = {str(t).strip().lower() for t in types or []}
    if "preprint" in low:
        return 8, "Preprint"
    for tier, label, names in TIERS:
        if low & names:
            return tier, label
    return 5, "Journal article"


def _t(el) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _year(art, mc) -> str:
    # the issue's date (Year or MedlineDate) is the citation's year; the electronic date only when the issue has none
    y = _t(art.find("Journal/JournalIssue/PubDate/Year"))
    if y[:4].isdigit():
        return y[:4]
    m = re.search(r"\b(19|20)\d{2}\b", _t(art.find("Journal/JournalIssue/PubDate/MedlineDate")))
    if m:
        return m.group(0)
    y = _t(art.find("ArticleDate/Year")) or _t(mc.find("DateCompleted/Year")) or _t(mc.find("DateRevised/Year"))
    return y[:4] if y[:4].isdigit() else ""


def _authors(els) -> list:
    out = []
    for au in els:
        if au.get("ValidYN") == "N":
            continue
        name = (_t(au.find("LastName")) + " " + _t(au.find("Initials"))).strip() or _t(au.find("CollectiveName"))
        if name:
            out.append(name)
    return out


def authors_line(authors) -> str:
    return ", ".join(authors[:3]) + (", et al." if len(authors) > 3 else "") if authors else ""


def _record(pmid, title, sections, journal, abbr, year, authors, affs, types, langs, mesh, ids, refs, status, book=False) -> dict:
    abstract = "\n".join(f"{s['label']}: {s['text']}" if s["label"] else s["text"] for s in sections)
    tier, kind = (5, "Book chapter") if book else study_type(types)
    low = {t.lower() for t in types}
    return {"pmid": pmid, "title": title, "abstract": abstract, "sections": sections, "has_abstract": bool(abstract.strip()),
            "journal": journal, "journal_abbr": abbr, "year": year, "authors": authors, "authors_line": authors_line(authors),
            "types": types, "study_type": kind, "tier": tier, "preprint": "preprint" in low,
            "retracted": "retracted publication" in low or "RetractionIn" in refs,
            "retraction_notice": "retraction of publication" in low, "concern": "ExpressionOfConcernIn" in refs, "erratum": "ErratumIn" in refs,
            "india": any(re.search(r"\bIndia\b", a, re.I) for a in affs), "languages": langs, "mesh": mesh,
            "doi": ids.get("doi", ""), "pmcid": ids.get("pmc", ""), "status": status, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}


def _sections(abstract_el) -> list:
    out = []
    for x in abstract_el.findall("AbstractText") if abstract_el is not None else []:
        txt = _t(x)
        if txt:
            out.append({"label": " ".join((x.get("Label") or "").split()), "text": txt})
    return out


def _article(a) -> dict | None:
    mc = a.find("MedlineCitation")
    art = mc.find("Article") if mc is not None else None
    pmid = _t(mc.find("PMID")) if mc is not None else ""
    if art is None or not pmid.isdigit():
        return None
    ids = {x.get("IdType"): _t(x) for x in a.findall("PubmedData/ArticleIdList/ArticleId")}
    return _record(pmid, _t(art.find("ArticleTitle")) or _t(art.find("VernacularTitle")), _sections(art.find("Abstract")),
                   _t(art.find("Journal/Title")), _t(art.find("Journal/ISOAbbreviation")), _year(art, mc),
                   _authors(art.findall("AuthorList/Author")), [_t(x) for x in art.findall("AuthorList/Author/AffiliationInfo/Affiliation")],
                   [_t(x) for x in art.findall("PublicationTypeList/PublicationType")], [_t(x) for x in art.findall("Language")],
                   [_t(x) for x in mc.findall("MeshHeadingList/MeshHeading/DescriptorName")], ids,
                   {x.get("RefType") or "" for x in mc.findall("CommentsCorrectionsList/CommentsCorrections")},
                   _t(a.find("PubmedData/PublicationStatus")))


def _book(a) -> dict | None:
    bd = a.find("BookDocument")
    pmid = _t(bd.find("PMID")) if bd is not None else ""
    if not pmid.isdigit():
        return None
    book = bd.find("Book")
    y = _t(book.find("PubDate/Year")) if book is not None else ""
    ids = {x.get("IdType"): _t(x) for x in a.findall("PubmedBookData/ArticleIdList/ArticleId")}
    return _record(pmid, _t(bd.find("ArticleTitle")) or (_t(book.find("BookTitle")) if book is not None else ""), _sections(bd.find("Abstract")),
                   _t(book.find("BookTitle")) if book is not None else "", "", y[:4] if y[:4].isdigit() else "",
                   _authors(bd.findall("AuthorList/Author")), [_t(x) for x in bd.findall("AuthorList/Author/AffiliationInfo/Affiliation")],
                   [_t(x) for x in bd.findall("PublicationType")], [_t(x) for x in bd.findall("Language")], [], ids, set(),
                   _t(a.find("PubmedBookData/PublicationStatus")), book=True)


def parse(body: bytes) -> list:
    """The records of an efetch XML answer. PubMedError for XML that cannot be read or an answer that is not a PubmedArticleSet."""
    try:
        root = DET.fromstring(body)
    except (DET.ParseError, DefusedXmlException, ValueError):
        raise PubMedError("PubMed sent records that could not be read") from None
    if root.tag != "PubmedArticleSet":
        err = _t(root.find(".//ERROR"))
        raise PubMedError(f"PubMed: {err[:160]}" if err else f"PubMed sent '{root.tag}' instead of records")
    out = []
    for a in root:
        rec = _article(a) if a.tag == "PubmedArticle" else _book(a) if a.tag == "PubmedBookArticle" else None
        if rec:
            out.append(rec)
    return out


# ---- the cache of public records ------------------------------------------------------------------------------------------------------
def _cache_get(pmid: str):
    p = CACHE_DIR / f"{pmid}.json"
    try:
        d = json.loads(p.read_text())
        if not isinstance(d, dict) or time.time() - float(d.get("saved") or 0) > CACHE_DAYS * 86400 or not isinstance(d.get("paper"), dict):
            return None
        rec = d["paper"]
        rec["provenance"] = {**(rec.get("provenance") or {}), "cached": True}
    except (OSError, ValueError, TypeError):  # a damaged file is a miss, never an error
        return None
    return rec if rec.get("pmid") == pmid else None


def _cache_put(rec: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = CACHE_DIR / f"{rec['pmid']}.json"
        tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"saved": time.time(), "paper": rec}))
        os.replace(tmp, p)
    except OSError:
        pass  # a cache that cannot be written only costs a fetch next time


async def fetch(pmids, *, client=None, fresh: bool = False) -> dict:
    """The PubMed records of the ids, in the order asked: {papers, missing, calls}. Each paper carries its provenance (the efetch call it
    came from, or cached). fresh=True skips the cache."""
    ids = []
    if isinstance(pmids, (str, int)):
        pmids = [pmids]  # one id given alone, never its characters one by one
    for x in pmids or []:
        if len(ids) >= MAX_IDS:
            break  # a long list is never scanned past the cap
        x = str(x).strip()
        if x.isascii() and x.isdigit() and x not in ids:  # PMIDs are ASCII digits (isdigit also takes other scripts' digits)
            ids.append(x)
    ids = ids[:MAX_IDS]
    got, calls = {}, []
    if not fresh:
        for i in ids:
            rec = _cache_get(i)
            if rec:
                got[i] = rec
    need = [i for i in ids if i not in got]

    async def run(c):
        for k in range(0, len(need), BATCH):
            body, prov = await _call(c, "efetch.fcgi", {"db": "pubmed", "id": ",".join(need[k:k + BATCH]), "retmode": "xml"})
            calls.append(prov)
            for rec in parse(body):
                rec["provenance"] = {**prov, "cached": False}
                got[rec["pmid"]] = rec
                _cache_put(rec)

    if need:
        if client is not None:
            await run(client)
        else:
            async with _client() as c:
                await run(c)
    return {"papers": [got[i] for i in ids if i in got], "missing": [i for i in ids if i not in got], "calls": calls}
