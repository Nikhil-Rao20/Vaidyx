"""Find a patient by name or by words on the New Case File page (docs/new-case/DESIGN.md N1 to N4, piece NC-A).

Doctors remember the patient's name (often shortened or misspelt), or a word from a report ("breast cancer", "chemotherapy"), not the
UHID. GET /his/find?q=... answers a drop-down of at most MAX_ROWS rows; picking one puts its UHID in the box and runs today's exact
lookup (GET /his/lookup), which stays the main way. Nothing here creates or changes a Case File.

Where the matches come from (N2):
  live        the hospital system itself: FHIR Patient?name=<word> for each typed word of 2+ letters (HISClient.search_patients; any
              FHIR system answers it, other transports answer []). Works on day one, without an index, for names spelt right.
  index       a per-hospital patient index built from the hospital system in the background: every registration (paged with
              _count / next links), the visits (department, attending doctor, date), the report titles and the report TEXT (the PDF's
              text layer, reports of the last TEXT_MONTHS months, at most TEXT_CHARS characters each, at most TEXTS_PER_BUILD new
              downloads per build). It is what makes a misspelt name and a word like "chemotherapy" findable. Built lazily: the first
              search starts it and is answered from the live search meanwhile; it is refreshed when older than REFRESH_SECONDS, and a
              refresh asks only for what changed (_lastUpdated=ge<watermark>; report text is cached by report id and version, so an
              unchanged report is never downloaded twice); a full rebuild once a day drops registrations the hospital removed. One
              build at a time per hospital. A hospital system that cannot list its patients (an HL7 folder, an MCP connector, a server
              that refuses a bare search) simply leaves the index empty; the live search still works.
  Case Files  this hospital's own Case Files (patient name, UHIDs, cancer, department, status), so a row says "Has a Case File".
              Words from a Case File (its cancer, department, status) count only when this person may open it (access.scope is not
              None); a Case File made by hand (no "his" block) is found by its name or number only by a person who may open it; the
              badge of one this person may not open says only "A Case File exists (<department>)". Archived, protected and private
              Case Files are never used. The list is cached per hospital (CASES_TTL seconds, or until the cases folder changes) and
              read in a thread; who may open what is worked out per search.

Matching built for Indian names (N3): lower case, "(SYNTHETIC)" and leading titles (Mr, Mrs, Smt, Sri, Dr, Baby, Master, Kumari, ...)
dropped, an Indian spelling fold as a second key (aa/a, ee/i, oo/u, th/t, dh/d, bh/b, kh/k, gh/g, sh/s, ph/f, w/v, z/j, x/ks, double
letters, a trailing h: Lakshmi and Laxmi both fold to "laksmi"), initials either way ("P Venkatesan", "Priya V"), one typing mistake in
a word of 4 to 6 letters and two in a longer one (Damerau-Levenshtein on the folded key), words in any order, and a part of a number
("4219" finds VXH/26/004219). Words: every typed word must match somewhere (the name, a visit's department or doctor, a report title or
its text, a Case File's cancer), with a small oncology table (ca / carcinoma / cancer, chemo / chemotherapy, NACT / neoadjuvant, RT /
radiotherapy, IDC / invasive ductal, mets / metastasis, FNAC, HPE / histopathology / biopsy, CECT / CT, PET / PET-CT, mammo /
mammogram) and the start of a word of 4+ letters. Rank: an exact number, then the full name, then a near name, then words; ties go to
the latest visit.

Speed: every key is worked out once when the index is compiled (in a thread), so a search does dictionary look-ups, bisect for the
starts of words and one rapidfuzz pass over the vocabulary for typing mistakes; no file is read per search. Report text lives in memory
per hospital up to TEXT_MEMORY_CHARS characters (newest reports first).

What is shown (N4): the same gate as the lookup (create_case; a guest reviewer and the Vaidyx admin are refused: admin consoles D5, the
Vaidyx admin reads patients only through break-glass), at most MAX_ROWS rows, never more report text than a SNIPPET-character piece
around the matched words, at most FIND_PER_WINDOW searches per login per hospital per FIND_WINDOW seconds (check_rate). Every search is
audited by the route (patient_find). The index files live in <DATA_ROOT>/patient_index/ (folder 700, files 600, written atomically, in
a thread, at most TEXTS_KEPT report texts): one hospital never reads another's, and the in-memory index is kept per hospital
(config.ScopedDict) with the signature of the hospital system it came from; an index of another system is never searched."""
import asyncio
import base64
import bisect
import hashlib
import heapq
import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rapidfuzz import process as _rf_process
from rapidfuzz.distance import DamerauLevenshtein

from . import config, his_case, his_client, identity, store
from .api.common import RateLimit

log = logging.getLogger("tumour_board.patient_finder")

MAX_ROWS = 8
SNIPPET = 120
MAX_QUERY = 80
REFRESH_SECONDS = 10 * 60          # the index is refreshed (only what changed) when older than this
FULL_EVERY_SECONDS = 24 * 3600     # and listed in full once a day, so removed registrations leave it
RETRY_AFTER_FAIL = 60              # a build that failed (the hospital system down) is not retried on every keystroke
TEXT_MONTHS = 24
TEXT_CHARS = 4000
TEXTS_PER_BUILD = 3000
TEXTS_KEPT = 20_000                # report texts kept per hospital (newest first): texts.json and the memory stay bounded
TEXT_MEMORY_CHARS = 40_000_000
PAGE = 200
MAX_LIST_PAGES = 1000              # 200,000 resources of one type at most
LIVE_WORDS = 4
LIVE_LIMIT = 50
LIVE_TIMEOUT = 4.0
VISIT_TIMEOUT = 3.0
DOWNLOADS_AT_ONCE = 4
INLINE_BYTES = 64_000_000          # report files kept from a listing (base64) while a build runs; beyond it they are downloaded one by one
INDEX_DIR = "patient_index"
INDEX_VERSION = 1
CASES_TTL = 5.0                    # the Case File list behind a search is re-read at most this often (or when the folder changes)
FIND_PER_WINDOW = 120              # searches per login per hospital per FIND_WINDOW seconds (a name search shows many people: N4)
FIND_WINDOW = 10 * 60
FIND_LIMIT = RateLimit(FIND_PER_WINDOW, FIND_WINDOW)
NO_ADMIN_SEARCH = "The Vaidyx admin does not search patients; open a Case File through break-glass."
TOO_MANY = "Too many searches. Wait a few minutes and try again, or type the UHID and press Look up."

# ---------------------------------------------------------------------------------------------------- words and names
_SYNTHETIC = re.compile(r"\(\s*synthetic\s*\)", re.I)
_TOKEN = re.compile(r"[a-z0-9]+")
TITLES = {"mr", "mrs", "ms", "miss", "smt", "srimati", "shrimati", "sri", "shri", "dr", "baby", "master", "kumari", "kum", "km", "prof"}
_FOLD_PAIRS = (("x", "ks"), ("aa", "a"), ("ee", "i"), ("oo", "u"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("kh", "k"), ("gh", "g"),
               ("sh", "s"), ("ph", "f"), ("w", "v"), ("z", "j"))
_DOUBLE = re.compile(r"(.)\1+")

# Oncology short forms (N3): any word of a group finds the others. A phrase ("invasive ductal") must have all its words in one patient.
SYNONYM_GROUPS = (
    ("ca", "carcinoma", "cancer", "malignancy", "malignant"),
    ("chemo", "chemotherapy"),
    ("nact", "neoadjuvant"),
    ("rt", "radiotherapy", "radiation"),
    ("idc", "invasive ductal"),
    ("mets", "metastasis", "metastatic", "metastases"),
    ("fnac", "fine needle"),
    ("hpe", "histopathology", "biopsy"),
    ("cect", "ct"),
    ("pet", "pet ct", "petct"),
    ("mammo", "mammogram", "mammography"),
)
SYNONYMS: dict = {}
for _g in SYNONYM_GROUPS:
    for _w in _g:
        SYNONYMS.setdefault(_w, set()).update(x for x in _g if x != _w)


def plain(text) -> str:
    """Lower case, accents off, "(SYNTHETIC)" off."""
    t = unicodedata.normalize("NFKD", _SYNTHETIC.sub(" ", str(text or "")))
    return "".join(ch for ch in t if not unicodedata.combining(ch)).lower()


def words(text) -> list:
    """The letter / digit words of a text, lower case."""
    return _TOKEN.findall(plain(text))


def name_words(name) -> list:
    """The words of a person's name without the titles in front (Mr, Smt, Dr, Baby, Kumari, ...); a title is kept when it is the only word."""
    ws = words(name)
    while len(ws) > 1 and ws[0] in TITLES:
        ws.pop(0)
    return ws


def fold(word: str) -> str:
    """The Indian spelling fold of one lower-case word (a second key: Lakshmi / Laxmi -> laksmi, Venkatesh / Wenkatesh -> venkates)."""
    w = word
    for a, b in _FOLD_PAIRS:
        w = w.replace(a, b)
    w = _DOUBLE.sub(r"\1", w)
    if len(w) > 2 and w.endswith("h"):
        w = w[:-1]
    return w


def typos_allowed(word: str) -> int:
    """How many typing mistakes a word may carry: none under 4 letters, one for 4 to 6, two for 7 or more."""
    n = len(word)
    return 0 if n < 4 else 1 if n <= 6 else 2


def _starting(keys: list, prefix: str) -> list:
    """The keys of a sorted list that start with `prefix`."""
    i = bisect.bisect_left(keys, prefix)
    out = []
    while i < len(keys) and keys[i].startswith(prefix):
        out.append(keys[i])
        i += 1
    return out


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def snippet_around(text: str, terms) -> str:
    """At most SNIPPET characters of `text` around the matched terms: the window that holds the most different terms (the earliest such
    window), cut at spaces where possible; "" when no term is in the text."""
    t = " ".join(str(text or "").split())
    low = t.lower()
    hits = []
    for term in set(terms):
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(term), low):
            hits.append((m.start(), m.end(), term))
    if not hits:
        return ""
    hits.sort()
    room = SNIPPET - 6
    best, best_n = hits[0], 0
    for h in hits:
        n = len({x[2] for x in hits if h[0] <= x[0] and x[1] <= h[0] + room - 10})
        if n > best_n:
            best, best_n = h, n
    first = best[0]
    start = max(0, first - room // 4)
    if start > 0:
        sp = t.rfind(" ", 0, start)
        start = sp + 1 if sp >= 0 and start - sp < 15 else start
    end = min(len(t), start + room)
    if end < len(t):
        sp = t.rfind(" ", start, end)
        end = sp if sp > first + 3 else end
    out = t[start:end].strip()
    return ("..." if start > 0 else "") + out + ("..." if end < len(t) else "")


def _count_terms(text: str, terms) -> int:
    low = " ".join(str(text or "").split()).lower()
    return sum(1 for term in terms if re.search(r"(?<![a-z0-9])" + re.escape(term), low))


# ---------------------------------------------------------------------------------------------------- the compiled index
class Index:
    """Rows (patients) with every search key worked out once. A row: {"key", "pid", "uhid", "name", "age", "sex", "last_visit":
    {"department", "date"} | None, "ids": [numbers], "sources": [(label, text)], "from": "his" | "live" | "case_file", ...}. `sources`
    are the texts words are found in (visits, report titles, report text, a Case File's cancer); their words go in the word vocabulary."""

    def __init__(self, rows: list):
        self.rows = rows
        self.name_raw: dict = {}
        self.name_fold: dict = {}
        self.name_len: list = []
        self.words: dict = {}
        self.ids: dict = {}
        self.id_list: list = []
        for i, r in enumerate(rows):
            nw = name_words(r.get("name"))
            self.name_len.append(len(nw))
            for w in nw:
                self.name_raw.setdefault(w, set()).add(i)
                self.name_fold.setdefault(fold(w), set()).add(i)
                self.words.setdefault(w, set()).add(i)
            for v in r.get("ids") or ():
                n = identity.normalise_id(v)
                if n:
                    self.ids.setdefault(n, set()).add(i)
                    self.id_list.append((n, i, v))
            for _label, text in r.get("sources") or ():
                for w in set(_TOKEN.findall(plain(text))):
                    if len(w) >= 2 and not w.isdigit():
                        self.words.setdefault(w, set()).add(i)
        self.name_raw_keys = sorted(self.name_raw)
        self.name_fold_keys = sorted(self.name_fold)
        self.word_keys = sorted(self.words)

    def __len__(self):
        return len(self.rows)

    # ---- one word against the names
    def name_hits(self, w: str, initials: bool = True) -> dict:
        """{row: best score} of the rows whose name has a word matching `w`: 100 the same word, 96 the same after the fold, 86 / 84 the
        start of a name word, 86 / 82 one / two typing mistakes, 70 an initial (either way)."""
        out: dict = {}

        def put(rows, s):
            for i in rows:
                if out.get(i, 0) < s:
                    out[i] = s
        if len(w) == 1:
            if initials:
                for k in _starting(self.name_raw_keys, w):
                    put(self.name_raw[k], 70)
            return out
        put(self.name_raw.get(w, ()), 100)
        fw = fold(w)
        put(self.name_fold.get(fw, ()), 96)
        if initials:
            put(self.name_raw.get(w[0], ()), 70)  # "P Venkatesan" in the hospital system, "Priya Venkatesan" typed
        for k in _starting(self.name_raw_keys, w):
            if k != w:
                put(self.name_raw[k], 86)
        if len(fw) >= 2:
            for k in _starting(self.name_fold_keys, fw):
                if k != fw:
                    put(self.name_fold[k], 84)
        n = typos_allowed(w)
        if n and self.name_fold_keys:
            for key, d, _ in _rf_process.extract(fw, self.name_fold_keys, scorer=DamerauLevenshtein.distance, score_cutoff=n, limit=None):
                if d > 0:
                    put(self.name_fold[key], 90 - 4 * d)
        return out

    # ---- one word anywhere
    def word_hits(self, w: str, names: dict | None = None) -> tuple:
        """({row: best score}, {vocabulary word: score}) of the rows where `w` (or a word of its group) is found anywhere: 100 the word,
        95 a word of its oncology group, 85 the start of a longer word (4+ letters typed), 80 / 76 one / two typing mistakes; a name
        that matches after the fold or with a typing mistake counts too."""
        out: dict = {}
        terms: dict = {}

        def put(rows, s):
            for i in rows:
                if out.get(i, 0) < s:
                    out[i] = s

        def term(k, s, rows):
            put(rows, s)
            if terms.get(k, 0) < s:
                terms[k] = s
        if w in self.words:
            term(w, 100, self.words[w])
        for alt in SYNONYMS.get(w, ()):
            parts = alt.split()
            if len(parts) > 1:
                sets = [self.words.get(p) for p in parts]
                if all(sets):
                    rows = set.intersection(*sets)
                    for p in parts:
                        term(p, 95, rows)
            elif alt in self.words:
                term(alt, 95, self.words[alt])
        if len(w) >= 4:
            for k in _starting(self.word_keys, w):
                if k != w:
                    term(k, 85, self.words[k])
            n = typos_allowed(w)
            for key, d, _ in _rf_process.extract(w, self.word_keys, scorer=DamerauLevenshtein.distance, score_cutoff=n, limit=None):
                if d > 0:
                    term(key, 84 - 4 * d, self.words[key])
        for i, s in (self.name_hits(w, initials=False) if names is None else names).items():  # Laxmi typed, Lakshmi in the name
            if 70 < s < 100 and out.get(i, 0) < s - 5:
                out[i] = s - 5
        return out, terms

    # ---- a whole query
    def search(self, q: str, limit: int = MAX_ROWS * 3) -> list:
        """The best rows for `q` as (score, last visit date, row index, how it matched, matched words), best first."""
        found: dict = {}

        def better(i, score, on, terms):
            cur = found.get(i)
            if cur is None or score > cur[0]:
                found[i] = (score, on, terms)
        toks = words(q)
        # a number, or a part of one ("4219", "004219", "VXH/26/004219")
        if any(ch.isdigit() for ch in q):
            qn = identity.normalise_id(q)
            for i in self.ids.get(qn, ()):
                better(i, 1000, "identifier", [qn])
            if len(qn) >= 3 and sum(ch.isdigit() for ch in qn) >= 3:
                for n, i, raw in self.id_list:
                    if qn in n and n != qn:
                        better(i, 800 + int(50 * len(qn) / max(len(n), 1)), "identifier", [raw])
        alpha = [t for t in toks if not any(ch.isdigit() for ch in t)]
        while len(alpha) > 1 and alpha[0] in TITLES:
            alpha.pop(0)
        if alpha:
            # the name: every typed word matches a word of the name, in any order
            hits = [self.name_hits(w) for w in alpha]
            by_word = dict(zip(alpha, hits))
            if all(hits):
                common = set.intersection(*(set(h) for h in hits))
                for i in common:
                    if self.name_len[i] < len(alpha):
                        continue
                    scores = [h[i] for h in hits]
                    mean = sum(scores) / len(scores)
                    cover = len(alpha) / max(self.name_len[i], 1)
                    if min(scores) >= 96:
                        better(i, 900 + int(40 * cover) + int(mean - 96), "name", [])
                    else:
                        better(i, 600 + int(mean) + int(40 * cover), "name", [])
            # words: every typed word matches somewhere
            ws = [w for w in alpha if len(w) >= 2 and w not in TITLES] or [w for w in alpha if len(w) >= 2]
            if ws:
                wh = [self.word_hits(w, by_word.get(w)) for w in ws]
                if all(h for h, _t in wh):
                    common = set.intersection(*(set(h) for h, _t in wh))
                    for i in common:
                        mean = sum(h[i] for h, _t in wh) / len(wh)
                        better(i, 300 + int(mean), "words", None)
                    vocab = {k for _h, t in wh for k in t}
        best = heapq.nlargest(limit, found.items(), key=lambda kv: (kv[1][0], (self.rows[kv[0]].get("last_visit") or {}).get("date") or ""))
        out = []
        for i, (s, on, terms) in best:
            if on == "words":  # the vocabulary words this row holds, for its snippet (worked out for the shown rows only)
                terms = [k for k in vocab if i in self.words.get(k, ())]
            out.append((s, (self.rows[i].get("last_visit") or {}).get("date") or "", i, on, terms))
        return out

    def matched(self, i: int, on: str, terms) -> dict:
        """How row `i` matched, for the drop-down: {"on", "snippet", "terms", "source"} (a word match's snippet from the source that holds
        the most matched words; at most SNIPPET characters)."""
        if on == "identifier":
            return {"on": on, "snippet": _clip(str(terms[0]) if terms else "", SNIPPET), "terms": [], "source": ""}
        if on != "words":
            return {"on": on, "snippet": "", "terms": [], "source": ""}
        terms = sorted(set(terms), key=len, reverse=True)
        best, best_n = None, 0
        for label, text in self.rows[i].get("sources") or ():
            n = _count_terms(text, terms)
            if n > best_n:
                best, best_n = (label, text), n
        if not best:
            return {"on": on, "snippet": "", "terms": terms, "source": ""}
        return {"on": on, "snippet": snippet_around(best[1], terms), "terms": terms, "source": _clip(str(best[0] or ""), 80)}


# ---------------------------------------------------------------------------------------------------- the index on disk
def _dir() -> Path:
    d = Path(config.DATA_ROOT) / INDEX_DIR
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _write(p: Path, obj) -> None:
    """Atomic, owner-only (600). Called in a thread (asyncio.to_thread): the temporary name carries the thread too, so a superseded
    build still writing in its thread never shares a temporary file with the build that replaced it."""
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _read(p: Path, default):
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def his_signature(settings: dict | None = None) -> str:
    """Which hospital system the index was built from, and how its numbers are read: the kind, label, url, connector, the adapter's
    base path or folder, its preset and its identifier systems (which identifier is the UHID; their order decides which one wins).
    Any change starts the index over, so a number never keeps the meaning it had under the old settings."""
    d = his_client.settings() if settings is None else settings
    a = d.get("adapter") if isinstance(d.get("adapter"), dict) else {}
    systems = a.get("identifier_systems") if isinstance(a.get("identifier_systems"), list) else []
    keep = {"kind": d.get("kind"), "label": d.get("label"), "url": d.get("url"), "connector": d.get("connector"),
            "base": a.get("base_path") or a.get("folder") or "", "preset": a.get("preset") or "",
            "identifier_systems": [str(x) for x in systems]}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _empty_raw(sig: str) -> dict:
    return {"version": INDEX_VERSION, "his": sig, "built_at": None, "full_at": None, "watermark": "", "patients": {}, "encounters": {},
            "reports": {}, "docs": {}}


# ---------------------------------------------------------------------------------------------------- reading the hospital system
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=his_client.IST)


async def _list(client, c, rtype: str, since: str = "", keep=None) -> list:
    """Every `rtype` resource of the hospital system, page by page (next links on the same server only), or only those changed at or
    after `since`. `keep` turns each resource into what is kept (None drops it) as each page arrives, so a page of documents that
    carry their files is let go before the next one comes."""
    params = [("_count", str(PAGE))] + ([("_lastUpdated", "ge" + since)] if since else [])
    out: list = []

    def take(b):
        if b.get("resourceType") != "Bundle":
            raise his_client.HISError(f"the HIS answer for {rtype} is not a Bundle")
        for e in b.get("entry") or []:
            r = e.get("resource")
            if isinstance(r, dict) and r.get("resourceType") == rtype and r.get("id"):
                k = keep(r) if keep else r
                if k is not None:
                    out.append(k)
    b = await client._get_json(c, rtype, params)
    take(b)
    for _ in range(MAX_LIST_PAGES):
        nxt = next((link.get("url") for link in b.get("link") or [] if link.get("relation") == "next"), None)
        if not nxt:
            break
        b = await client._get_json(c, nxt)
        take(b)
    return out


def _subject(res) -> str:
    ref = his_client._ref(res.get("subject"))
    return his_client._ref_id(ref, "Patient") if ref.startswith("Patient/") else ""


def _patient_entry(client, p: dict) -> dict:
    conv = getattr(client, "_patient", None)
    d = conv(p) if callable(conv) else his_client.patient_dict(p)
    ids = [d.get("uhid")] + [x.get("value") for x in d.get("identifiers") or [] if isinstance(x, dict)]
    return {"uhid": d.get("uhid") or "", "name": d.get("name") or "", "sex": d.get("sex") or "", "dob": d.get("dob") or "",
            "ids": sorted({str(x) for x in ids if x})}


def _encounter_entry(e: dict) -> dict:
    d = his_client.encounter_dict(e)
    return {"pid": _subject(e), "department": d.get("department") or "", "doctor": ((d.get("consultant") or {}).get("name") or ""),
            "date": str(d.get("start") or "")[:10], "number": d.get("number") or "", "kind": d.get("kind") or ""}


def _report_entry(r: dict) -> dict:
    code = r.get("code") or {}
    title = code.get("text") or ((his_client._first(code.get("coding")) or {}).get("display") or "")
    return {"pid": _subject(r), "title": title, "date": str(r.get("issued") or r.get("effectiveDateTime") or "")[:10],
            "status": r.get("status") or "", "conclusion": str(r.get("conclusion") or "")[:300]}


def _doc_entry(d: dict) -> dict:
    att = his_client._attachment(d)
    return {"pid": _subject(d), "rid": his_client._doc_report_id(d), "version": his_client._doc_version(d),
            "title": d.get("description") or att.get("title") or ((d.get("type") or {}).get("text") or ""),
            "date": str(d.get("date") or att.get("creation") or "")[:10], "status": d.get("status") or "",
            "content_type": att.get("contentType") or "", "inline": bool(att.get("data"))}


def text_of(data: bytes, content_type: str = "") -> str:
    """The searchable text of a report file: the PDF's text layer (pypdf; a scanned page without one gives nothing, no OCR here), or a
    text file as it is. At most TEXT_CHARS characters, spaces collapsed."""
    t = ""
    if data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
            parts, n = [], 0
            for page in PdfReader(io.BytesIO(data)).pages:
                s = page.extract_text() or ""
                parts.append(s)
                n += len(s)
                if n > TEXT_CHARS * 2:
                    break
            t = "\n".join(parts)
        except Exception as e:  # a broken PDF is left unread; the title still finds it
            log.info("patient index: a report PDF could not be read (%s)", type(e).__name__)
            t = ""
    elif content_type.startswith("text/") or not content_type:
        try:
            t = data.decode("utf-8")
        except UnicodeDecodeError:
            t = ""
    return " ".join(t.split())[:TEXT_CHARS]


def _want_text(docs: dict, today: date) -> list:
    """The documents whose text the index keeps: the newest version of each current report of the last TEXT_MONTHS months, newest first."""
    cut = (today - timedelta(days=int(TEXT_MONTHS * 30.5))).isoformat()
    best: dict = {}
    for did, d in docs.items():
        if d.get("status") in ("superseded", "entered-in-error") or not d.get("date") or d["date"] < cut:
            continue
        key = d.get("rid") or did
        cur = best.get(key)
        if cur is None or d.get("version", 1) > cur[1].get("version", 1):
            best[key] = (did, d)
    return sorted(best.values(), key=lambda x: x[1].get("date") or "", reverse=True)


async def build(client=None, full: bool | None = None) -> dict:
    """Build or refresh this hospital's index from its hospital system, save it and put it in memory. Returns {"patients", "texts",
    "downloaded", "full"}. A system that cannot list registrations (not a FHIR client, or a refused bare search) leaves the index empty.

    The event loop is never held by the files: index.json and texts.json are read and written in a thread (asyncio.to_thread keeps the
    hospital's context), and the raw index stays in memory between builds (read from disk only after a restart or a failed build).
    A build whose hospital system changed while it ran is not put in memory (ensure_fresh cancels it; this is the second guard)."""
    st = _state()
    work: dict = {}
    try:
        return await _build(st, client, full, work)
    except BaseException:  # failed or cancelled half way: the next build starts again from the saved files, never from a half-changed copy
        _forget_raw(st, work)
        raise


def _forget_raw(st: dict, work: dict) -> None:
    """Drop the in-memory raw index when it is the copy this build was changing (never the copy of a newer build)."""
    if work.get("raw") is not None and st.get("raw") is work["raw"]:
        st.update(raw=None, texts=None)


async def _build(st: dict, client, full, work: dict) -> dict:
    client = his_client.client() if client is None else client
    sig = his_signature()
    d = _dir()
    raw, texts = st.get("raw"), st.get("texts")
    work["raw"] = raw
    if not isinstance(raw, dict) or not isinstance(texts, dict) or raw.get("his") != sig:
        raw = await asyncio.to_thread(_read, d / "index.json", {})
        texts = await asyncio.to_thread(_read, d / "texts.json", {})
    if raw.get("version") != INDEX_VERSION or raw.get("his") != sig:
        raw, texts = _empty_raw(sig), {}
    started = _now()
    full_at = _parse(raw.get("full_at")) if raw.get("full_at") else None
    if full is None:
        full = not raw.get("built_at") or full_at is None or (started - full_at).total_seconds() > FULL_EVERY_SECONDS
    downloaded = 0
    if client is not None and isinstance(client, his_client.FHIRClient):
        since = "" if full else str(raw.get("watermark") or "")
        inline: dict = {}
        room = [INLINE_BYTES]
        cut = (date.today() - timedelta(days=int(TEXT_MONTHS * 30.5))).isoformat()

        def doc_kept(doc):
            """The document's index entry; its file (base64 in the listing) is kept only when its text is still wanted, up to INLINE_BYTES
            in all (the rest is downloaded one by one later)."""
            entry = _doc_entry(doc)
            att = his_client._attachment(doc)
            data = att.get("data")
            if (data and entry["status"] not in ("superseded", "entered-in-error") and entry["date"] >= cut
                    and f"{entry['rid'] or doc['id']}@v{entry['version']}" not in texts and len(data) <= room[0]):
                room[0] -= len(data)
                inline[doc["id"]] = (data, his_client._ext_value(doc, "document-sha256") or "", att.get("hash") or "", att.get("contentType") or "")
            return (doc["id"], entry)
        async with client._client() as c:
            async def listed(rtype, keep):
                try:
                    return await _list(client, c, rtype, since, keep)
                except his_client.HISError as e:
                    if since and "HTTP 400" in str(e):  # a server without _lastUpdated: the whole list
                        return await _list(client, c, rtype, "", keep)
                    raise
            pats = await listed("Patient", lambda p: (p["id"], _patient_entry(client, p)))
            encs = await listed("Encounter", lambda e: (e["id"], _encounter_entry(e)))
            try:
                reps = await listed("DiagnosticReport", lambda r: (r["id"], _report_entry(r)))
            except his_client.HISError as e:  # report titles are a bonus; registrations and visits still count
                if "refused" in str(e) or "cannot reach" in str(e):
                    raise
                reps = []
            try:
                docs = await listed("DocumentReference", doc_kept)
            except his_client.HISError as e:
                if "refused" in str(e) or "cannot reach" in str(e):
                    raise
                docs = []
        if full:
            raw["patients"], raw["encounters"], raw["reports"], raw["docs"] = {}, {}, {}, {}
        raw["patients"].update(pats)
        raw["encounters"].update(encs)
        raw["reports"].update(reps)
        raw["docs"].update(docs)
        del pats, encs, reps, docs
        # the text of the reports that changed (by report id and version): from the listing when it carries the file, else downloaded;
        # only the newest TEXTS_KEPT reports, so an older one is never downloaded just to be dropped again
        want = _want_text(raw["docs"], date.today())[:TEXTS_KEPT]
        keep = {f"{x[1].get('rid') or x[0]}@v{x[1].get('version', 1)}" for x in want}
        todo = [(did, e) for did, e in want if f"{e.get('rid') or did}@v{e.get('version', 1)}" not in texts][:TEXTS_PER_BUILD]
        sem = asyncio.Semaphore(DOWNLOADS_AT_ONCE)

        async def one(did, e):
            async with sem:
                try:
                    if did in inline:
                        b64, sha, sha1, ctype = inline[did]
                        data = base64.b64decode(b64, validate=True)
                        his_client._check_sha(data, sha, sha1, f"document {did}")
                    else:
                        got = await client.document(f"DocumentReference/{did}")
                        data, ctype = got.get("content") or b"", got.get("content_type") or ""
                except (his_client.HISError, ValueError, TypeError) as err:
                    log.info("patient index: report %s left without its text (%s)", did, str(err)[:120])
                    return did, e, None
                return did, e, await asyncio.to_thread(text_of, data, ctype)
        for did, e, t in await asyncio.gather(*(one(did, e) for did, e in todo)):
            if t is not None:
                texts[f"{e.get('rid') or did}@v{e.get('version', 1)}"] = {"t": t, "d": e.get("date") or ""}
                downloaded += 1
        inline.clear()
        texts = {k: v for k, v in texts.items() if k in keep}
    elif client is not None:
        raw = _empty_raw(sig)  # a transport that cannot list registrations: the live search only
        texts = {}
    raw["built_at"] = _iso(started)
    if full:
        raw["full_at"] = _iso(started)
    raw["watermark"] = _iso(started - timedelta(minutes=2))
    await asyncio.to_thread(_write, d / "index.json", raw)
    await asyncio.to_thread(_write, d / "texts.json", texts)
    idx = await asyncio.to_thread(compile_index, raw, texts)
    out = {"patients": len(raw["patients"]), "texts": len(texts), "downloaded": downloaded, "full": bool(full)}
    if his_signature() != sig:  # the hospital system changed while this build ran: its index answers nobody
        _forget_raw(st, work)
        return out
    st.update(index=idx, built_at=raw["built_at"], sig=sig, error="", loaded=True, raw=raw, texts=texts)
    return out


def compile_index(raw: dict, texts: dict) -> Index:
    """The in-memory Index of the saved data: one row per registration with its visits, report titles and report text (newest first,
    up to TEXT_MEMORY_CHARS characters in all)."""
    visits: dict = {}
    for e in (raw.get("encounters") or {}).values():
        if e.get("pid"):
            visits.setdefault(e["pid"], []).append(e)
    titles: dict = {}
    for r in (raw.get("reports") or {}).values():
        if r.get("pid") and r.get("title"):
            titles.setdefault(r["pid"], []).append((r["title"], r.get("date") or "", r.get("conclusion") or ""))
    reps: dict = {}
    budget = TEXT_MEMORY_CHARS
    for did, e in _want_text(raw.get("docs") or {}, date.today()):
        t = (texts.get(f"{e.get('rid') or did}@v{e.get('version', 1)}") or {}).get("t") or ""
        if e.get("pid"):
            if t and budget > 0:
                budget -= len(t)
            else:
                t = ""
            reps.setdefault(e["pid"], []).append((e.get("title") or "", e.get("date") or "", t))
    rows = []
    for pid, p in (raw.get("patients") or {}).items():
        vs = sorted(visits.get(pid, []), key=lambda v: v.get("date") or "")
        last = vs[-1] if vs else None
        ids = list(p.get("ids") or []) + [v["number"] for v in vs if v.get("number")]
        sources = []
        if vs:
            depts = sorted({v.get("department") for v in vs if v.get("department")})
            docs_ = sorted({v.get("doctor") for v in vs if v.get("doctor")})
            sources.append(("Visits", ", ".join(depts + docs_)))
        seen = set()
        for title, day, text in sorted(reps.get(pid, []), key=lambda x: x[1], reverse=True):
            label = f"{title}, {_dmy(day)}" if day else title
            seen.add((title.lower(), day))
            if title:
                sources.append((label, title))
            if text:
                sources.append((label, text))
        for title, day, concl in sorted(titles.get(pid, []), key=lambda x: x[1], reverse=True):
            if (title.lower(), day) not in seen:
                label = f"{title}, {_dmy(day)}" if day else title
                sources.append((label, title))
            if concl:
                sources.append((f"{title}, {_dmy(day)}" if day else title, concl))
        rows.append({"key": identity.normalise_id(p.get("uhid")) or f"his:{pid}", "pid": pid, "uhid": p.get("uhid") or "",
                     "name": p.get("name") or "", "age": his_client._age(p.get("dob") or ""), "sex": p.get("sex") or "",
                     "last_visit": {"department": last.get("department") or "", "date": last.get("date") or ""} if last else None,
                     "ids": ids, "sources": sources, "from": "his"})
    return Index(rows)


def _dmy(day: str) -> str:
    try:
        return date.fromisoformat(str(day)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(day or "")


# ---------------------------------------------------------------------------------------------------- per-hospital state
_STATES = config.ScopedDict()


def _state() -> dict:
    """This hospital's finder: the compiled index and the signature of the system it came from (sig), the raw index and report texts
    it was compiled from (raw, texts: kept so a refresh does not re-read the files), the running build and the signature it was
    started for (task, task_sig), the last failure (error, failed_at, failed_sig) and the cached Case File list (cases)."""
    return _STATES.setdefault("finder", {"index": None, "built_at": None, "sig": "", "task": None, "task_sig": "", "error": "",
                                          "failed_at": 0.0, "failed_sig": "", "loaded": False, "raw": None, "texts": None, "cases": None})


def reset() -> None:
    """Forget every hospital's in-memory index and the search counts (tests)."""
    _STATES.clear()
    with FIND_LIMIT._lock:
        FIND_LIMIT._hits.clear()


def check_rate(user: str) -> None:
    """At most FIND_PER_WINDOW searches per login per hospital per FIND_WINDOW seconds (429 with a plain message beyond it): the drop-down
    names many patients, so a script cannot walk the hospital's register through it."""
    FIND_LIMIT.check(f"{config.hospital_id()}\n{user or ''}", TOO_MANY)


def _building(st: dict) -> bool:
    t = st.get("task")
    return bool(t is not None and not t.done())


async def _run(full=None):
    st = _state()
    sig = his_signature()
    try:
        if not st.get("loaded"):  # a restart: the saved index answers at once while the refresh runs
            d = _dir()
            raw = await asyncio.to_thread(_read, d / "index.json", {})
            if raw.get("version") == INDEX_VERSION and raw.get("his") == sig and raw.get("built_at"):
                texts = await asyncio.to_thread(_read, d / "texts.json", {})
                idx = await asyncio.to_thread(compile_index, raw, texts)
                if his_signature() != sig:
                    return
                st.update(index=idx, built_at=raw["built_at"], sig=raw["his"], loaded=True, raw=raw, texts=texts)
                age = (_now() - (_parse(raw["built_at"]) or _now())).total_seconds()
                if age < REFRESH_SECONDS:
                    return
            st["loaded"] = True
        await build(full=full)
    except Exception as e:  # the hospital system down or a refused list: the live search and the Case Files still answer
        st.update(error=str(e)[:200], failed_at=time.time(), failed_sig=sig)
        log.warning("patient index of hospital %s not built: %s", config.hospital_id(), str(e)[:200])


def ensure_fresh(sig: str | None = None) -> None:
    """Start a build in the background (in this hospital's context) when there is no index yet, a different hospital system, or one older
    than REFRESH_SECONDS; never two at once, and not again within RETRY_AFTER_FAIL seconds of a failure of the same system.

    A change of hospital system (his_signature) first drops the index of the old one, then cancels a build still running for the old
    one and starts one for the new: the old system's patients are never shown under the new system's settings."""
    st = _state()
    sig = his_signature() if sig is None else sig
    if st.get("sig") and st.get("sig") != sig:
        st.update(index=None, built_at=None, sig="", loaded=False, raw=None, texts=None)
    if _building(st):
        if st.get("task_sig") == sig:
            return
        st["task"].cancel()  # a build for the old system: superseded
    elif st.get("error") and st.get("failed_sig") == sig and time.time() - float(st.get("failed_at") or 0) < RETRY_AFTER_FAIL:
        return
    else:
        built = _parse(st.get("built_at")) if st.get("built_at") else None
        if st.get("index") is not None and st.get("sig") == sig and built and (_now() - built).total_seconds() < REFRESH_SECONDS:
            return
    # the task copies this context: the same hospital
    st.update(task=asyncio.get_running_loop().create_task(_run()), task_sig=sig)


def current_index(sig: str):
    """The in-memory index only when it was built from the hospital system configured now (`sig`), else None."""
    st = _state()
    return st.get("index") if st.get("index") is not None and st.get("sig") == sig else None


def index_status(sig: str | None = None) -> dict:
    st = _state()
    idx = current_index(his_signature() if sig is None else sig)
    return {"patients": len(idx) if idx is not None else 0, "built_at": st.get("built_at") if idx is not None else None,
            "building": _building(st)}


# ---------------------------------------------------------------------------------------------------- Case Files
def _visible_cases() -> list:
    """This hospital's live Case Files (the rule of his_case.same_patient_cases: never archived, protected or private)."""
    from . import access
    return [c for c in store.list_cases()
            if c.get("case_id") and c["case_id"] not in config.HIDDEN_CASES and not access.is_archived(c)]


def _cases_signal() -> tuple:
    """A cheap sign that Case Files were added or removed: the cases folder's modification time and how many entries it holds."""
    try:
        st = os.stat(config.CASES_DIR)
        return (st.st_mtime_ns, len(os.listdir(config.CASES_DIR)))
    except OSError:
        return (0, 0)


async def _cached_cases() -> list:
    """This hospital's live Case Files for a search, read at most every CASES_TTL seconds or when the cases folder changed. store.list_cases
    reads every Case File's files, so it runs in a thread (it keeps the hospital's context) and is not repeated on every keystroke of
    every doctor. A Case File made private since (HIDDEN_CASES reads its marker on every check) is dropped at once."""
    st = _state()
    sig = await asyncio.to_thread(_cases_signal)
    hit = st.get("cases")
    if not (hit and hit[0] == sig and time.monotonic() - hit[1] < CASES_TTL):
        hit = (sig, time.monotonic(), await asyncio.to_thread(_visible_cases))
        st["cases"] = hit
    return [c for c in hit[2] if c["case_id"] not in config.HIDDEN_CASES]


def _scopes(cases: list, roles: dict) -> dict:
    """{case id: access.scope} for this person (None: may not open it). Worked out per request: the cache is shared by every login."""
    from . import access
    out = {}
    for c in cases:
        try:
            out[c["case_id"]] = access.scope(roles, c)
        except Exception:
            out[c["case_id"]] = None
    return out


def _case_brief(c: dict, roles: dict, scope) -> dict:
    """A Case File badge. One this person may not open says only that it exists and its department ("A Case File exists (Breast
    Surgery)"): no id, no cancer, no status, so the drop-down never tells a doctor more about another department's patient than the
    duplicate check at creation would."""
    from .api.patients import _status_label
    b = his_case.file_brief(c, roles)
    if scope is None:
        return {"department": b.get("department_name") or "", "can_open": False}
    return {"case_id": c["case_id"], "department": b.get("department_name") or "", "department_id": b.get("department") or "",
            "cancer": b.get("cancer_label") or "", "status": _status_label(c), "can_open": bool(b.get("can_open"))}


def _case_index(cases: list, roles: dict, scopes: dict | None = None) -> Index:
    """The Case Files as rows. A Case File made from the hospital system: its name and UHIDs always (the patient is in the hospital
    system anyway). A Case File made by hand (no "his" block; the patient may not be in the hospital system at all): only for a person
    who may open it. The cancer, department and status count as words only for a person who may open it."""
    from . import org, protocol
    scopes = _scopes(cases, roles) if scopes is None else scopes
    rows = []
    for c in cases:
        p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
        uh = sorted(his_case.case_uhids(c))
        mrn = str(p.get("mrn") or "")
        uhid = (c.get("his") or {}).get("uhid") if isinstance(c.get("his"), dict) else ""
        uhid = uhid or mrn
        sources = []
        may = scopes.get(c["case_id"]) is not None
        if not may and not isinstance(c.get("his"), dict):
            continue
        if may:
            dept = org.department_name(c["department"]) if c.get("department") else ""
            sources.append((f"Case File {c['case_id']}", ", ".join(x for x in (protocol.case_label(c), c.get("cancer_name") or "", dept) if x)))
        age = p.get("age")
        rows.append({"key": identity.normalise_id(uhid) or f"case:{c['case_id']}", "pid": "", "uhid": uhid, "name": p.get("name") or "",
                     "age": age if isinstance(age, int) else _age_of(p), "sex": p.get("sex") or _sex_of(p), "last_visit": None,
                     "ids": uh + ([mrn] if mrn else []), "sources": sources, "from": "case_file", "case_id": c["case_id"]})
    return Index(rows)


def _age_of(p: dict):
    m = re.match(r"\s*(\d{1,3})", str(p.get("agesex") or ""))
    return int(m.group(1)) if m else None


def _sex_of(p: dict) -> str:
    m = re.search(r"/\s*([MFO])", str(p.get("agesex") or ""), re.I)
    return m.group(1).upper() if m else ""


# ---------------------------------------------------------------------------------------------------- the search
async def _live(client, q: str) -> tuple:
    """(Index of the registrations the hospital system names for each typed word, True when every call answered)."""
    ws = [w for w in name_words(q) if len(w) >= 2 and not any(ch.isdigit() for ch in w) and w not in TITLES][:LIVE_WORDS]
    if client is None or not ws:
        return Index([]), client is not None
    try:
        got = await asyncio.wait_for(asyncio.gather(*(client.search_patients(w, LIVE_LIMIT) for w in ws)), LIVE_TIMEOUT)
    except (his_client.HISError, asyncio.TimeoutError, NotImplementedError) as e:
        log.info("patient finder: the live name search did not answer (%s)", str(e)[:120] or type(e).__name__)
        return Index([]), False
    seen, rows = set(), []
    for lst in got:
        for p in lst or []:
            k = identity.normalise_id(p.get("uhid")) or f"his:{p.get('id')}"
            if k in seen:
                continue
            seen.add(k)
            rows.append({"key": k, "pid": p.get("id") or "", "uhid": p.get("uhid") or "", "name": p.get("name") or "", "age": p.get("age"),
                         "sex": p.get("sex") or "", "last_visit": None,
                         "ids": [p.get("uhid")] + [x.get("value") for x in p.get("identifiers") or [] if isinstance(x, dict)],
                         "sources": [], "from": "live"})
    return Index(rows), True


async def _visits(client, rows: list) -> None:
    """The last visit of rows the index does not know yet (found by the live search while the index is being built)."""
    need = [r for r in rows if r.get("last_visit") is None and r.get("pid") and r.get("from") == "live"]
    if client is None or not need:
        return

    async def one(r):
        try:
            encs = await client.encounters(r["pid"])
        except (his_client.HISError, NotImplementedError):
            return
        if encs:
            e = encs[-1]
            r["last_visit"] = {"department": e.get("department") or "", "date": str(e.get("start") or "")[:10]}
    try:
        await asyncio.wait_for(asyncio.gather(*(one(r) for r in need)), VISIT_TIMEOUT)
    except asyncio.TimeoutError:
        pass


async def find(q: str, roles: dict, client="auto") -> dict:
    """GET /his/find: at most MAX_ROWS rows for `q` (see the module docstring) and where they came from."""
    q = " ".join(str(q or "").split())[:MAX_QUERY]
    if client == "auto":
        client = his_client.client()
    out = {"q": q, "results": [], "sources": {"his_live": False, "index": {"patients": 0, "built_at": None, "building": False}}}
    sig = his_signature() if client is not None else ""
    if client is not None:
        ensure_fresh(sig)
    if len(q) < 2:
        out["sources"]["his_live"] = client is not None
        out["sources"]["index"] = index_status(sig) if client is not None else out["sources"]["index"]
        return out
    live_task = asyncio.ensure_future(_live(client, q))
    cases = await _cached_cases()
    scopes, case_idx = await asyncio.to_thread(_case_part, cases, roles)
    his_idx = current_index(sig) if client is not None else None  # never the index of a hospital system configured before
    found = []  # (score, date, rank of the source, row, matched)
    for rank, idx in ((0, his_idx), (2, case_idx)):
        if idx is None or not len(idx):
            continue
        for score, day, i, on, terms in idx.search(q):
            found.append((score, day, rank, idx.rows[i], idx.matched(i, on, terms)))
    live_idx, live_ok = await live_task
    for score, day, i, on, terms in live_idx.search(q):
        found.append((score, day, 1, live_idx.rows[i], live_idx.matched(i, on, terms)))
    # one row per patient (the UHID): the hospital system's details first, the best match
    merged: dict = {}
    for score, day, rank, row, m in found:
        cur = merged.get(row["key"])
        if cur is None:
            merged[row["key"]] = {"row": dict(row), "rank": rank, "score": score, "matched": m}
            continue
        if rank < cur["rank"]:
            keep = cur["row"]
            cur["row"], cur["rank"] = dict(row), rank
            if not cur["row"].get("last_visit") and keep.get("last_visit"):
                cur["row"]["last_visit"] = keep["last_visit"]
        if score > cur["score"]:
            cur["score"], cur["matched"] = score, m
    best = sorted(merged.values(), key=lambda x: (x["score"], (x["row"].get("last_visit") or {}).get("date") or ""), reverse=True)[:MAX_ROWS]
    await _visits(client, [b["row"] for b in best])
    system = (client.kind, client.label) if client is not None else None
    results = []
    for b in best:
        r = b["row"]
        want = {identity.normalise_id(r.get("uhid"))} - {""}
        files = []
        for c in cases:
            h = c.get("his") if isinstance(c.get("his"), dict) else None
            if system and h and (h.get("kind"), str(h.get("label") or "")) != (system[0], str(system[1] or "")):
                continue
            if (want and his_case.case_uhids(c) & want) or (r.get("case_id") and c["case_id"] == r["case_id"]):
                files.append(_case_brief(c, roles, scopes.get(c["case_id"])))
        results.append({"uhid": r.get("uhid") or "", "name": r.get("name") or "", "age": r.get("age"), "sex": r.get("sex") or "",
                        "last_visit": r.get("last_visit"), "case_files": files, "matched": b["matched"], "score": int(b["score"]),
                        "from": r.get("from") or ""})
    out["results"] = results
    out["sources"] = {"his_live": bool(client is not None and live_ok), "index": index_status(sig) if client is not None else out["sources"]["index"]}
    return out


def _case_part(cases: list, roles: dict) -> tuple:
    """(scopes, Index) of the Case Files for this person: run in a thread, as access.scope may read files for each Case File."""
    scopes = _scopes(cases, roles)
    return scopes, _case_index(cases, roles, scopes)
