"""Guideline library retrieval (reference text for the board, never a recommendation for this patient).

Indexes the freely available guideline documents in TB_GUIDELINE_DIR (see docs/tumour-board/RESOURCES.md):
India first (National Cancer Grid incl. head & neck and gynaecological 2019, ICMR, Tata Memorial Centre Evidence Based
Management 2024, PM-JAY HBP 2.2, ICRI / IRIA), then international (ESMO incl. Pan-Asian adaptations, CAP / ASCO-CAP,
ACR, RECIST) and US public-domain summaries (NCI PDQ). Hybrid BM25 + embeddings, with an India-first boost.
NCCN content is not ingested (licence restricts AI use)."""
import hashlib, json, math, os, re, threading
from collections import Counter
from pathlib import Path

import numpy as np

from . import config, protocol, search

SOURCES = {  # folder -> (organisation label, region tag, boost)
    "ncg_india": ("National Cancer Grid (NCG), India", "India", 1.35), "icmr": ("ICMR consensus, India", "India", 1.3),
    "esmo": ("ESMO", "International", 1.0), "cap_protocols": ("CAP cancer protocol", "International", 1.0),
    "asco_cap": ("ASCO / CAP", "International", 1.0), "acr_appropriateness": ("ACR Appropriateness Criteria", "International", 0.95),
    "acr_rads": ("ACR RADS", "International", 0.9), "recist": ("RECIST", "International", 0.9), "nci_pdq": ("NCI PDQ (US)", "US", 0.85),
    "pmjay": ("PM-JAY / National Health Authority, India", "India", 1.3), "iria": ("ICRI / IRIA onco-imaging checklists, India", "India", 1.25),
    "nhs_england": ("NHS England MDT guidance", "UK", 1.0), "rcpath": ("Royal College of Pathologists dataset", "UK", 1.0),
    "rcr": ("Royal College of Radiologists imaging recommendations", "UK", 0.95), "nice": ("NICE guideline", "UK", 0.95),
    "iccr": ("ICCR dataset", "International", 1.0), "eusoma": ("EUSOMA / ESMO", "International", 0.95),
    "victoria_au": ("Victorian Cancer MDM quality framework", "Australia", 0.9),
    "tmc": ("Tata Memorial Centre Evidence Based Management, India", "India", 1.3),
}
CANCER_WORDS = {"lung_nsclc": ["lung", "nsclc", "thoracic"], "breast": ["breast"], "colorectal_rectum": ["rect", "colorectal", "colon"]}
INDEX_VERSION = 5  # bump when chunking or filtering changes: the cached index is rebuilt, embeddings of unchanged chunks reused
_lock = threading.Lock()
_IDX = None


def _title(p: Path):
    return re.sub(r"[_\-]+", " ", p.stem).strip()


_REF_LINE = re.compile(r"(^|\n|\.\s)(?!Any\b)[A-Z][A-Za-z'\-]+ [A-Z]{1,3}[,.]\s")
# journal running footers ("https://doi.org/10.1016/j.annonc... Volume 36 - Issue 9 - 2025") are not citations: removed before counting
_FOOTER = re.compile(r"https?://(?:dx\.)?doi\.org/\S+|\bVolume \d+\s?[\-\u2013]\s?Issue \d+\s?[\-\u2013]\s?\d{4}")


# One bibliography entry (V1 item 5.2): an author start ('9. Eisenhauer EA,', 'Therasse P ,', 'Rosselli Del Turco M,', 'N.S. Nair,')
# followed within a few lines by a citation tail ('2009;45(2):228-247', '365(5):395-409', ':1596-1606' with any dash, doi, PMID,
# '(2003): 2912', 'Abstract LBA38'). Inline citations in guideline prose cover little of a passage; a reference list covers most of it.
_L = r"[^\W\d_]"
_DASH = "\\-\u2010\u2011\u2012\u2013\u2014\u2015"
_SUR = r"(?!Any\b)[A-Z]'?[a-z\u00df-\u024f]" + _L + r"*(?:[" + _DASH + r"' ][A-Z]?" + _L + r"+){0,2}"
_INI = r"[A-Z]{1,3}"
_START = (r"(?:\[\d{1,3}\]\s?|\d{1,3}[a-z]?\s?[.)]\s?)?(?:" + _SUR + r" " + _INI + r"\s?[,.;:]|" + _SUR + r",? (?:" + _INI + r"\.? ?){1,3}(?:,|et\s?al)"
          r"|[A-Z]\.\s?(?:[A-Z]\.\s?)?" + _SUR + r",)")
_TAIL = (r"(?:\b(?:19|20)\d{2}\s?(?:[A-Z][a-z]{2}(?:\s?\d{1,2})?\s?)?;\s?\d+|\b\d{1,4}\s?\(\s?(?:Suppl\.?\s?)?\d{1,4}\s?\)\s?:\s?[eE]?\d+"
         r"|:\s?[eE]?\d{1,6}\s?[" + _DASH + r"]\s?[eE]?\d{1,6}|\bdoi\b|doi\.org|\bPMID\b|\((?:19|20)\d{2}\)\s?:\s?\d+|\b(?:19|20)\d{2}\.\s*$"
         r"|\bAbstract\s+[A-Z]*\d+|\bet\s?al\.?\s?\(?(?:19|20)\d{2})")
_ENTRY = re.compile(r"(?:^|(?<=[\n.;\]]))[ ,]*(?:[^\n]{0,80}?, )?" + _START + r"[\s\S]{0,420}?" + _TAIL, re.M)


def _citation_coverage(t):
    """Share of the text inside bibliography entries."""
    return sum(m.end() - m.start() for m in _ENTRY.finditer(t)) / max(len(t), 1)


def _is_reference_list(t):
    """Bibliography text (author lists, journal citations) is not guideline content. Journal footers and TNM table cells ('Any T,
    Any N') are not counted (V1 Phase 5 review)."""
    if _citation_coverage(t) >= 0.5:
        return True
    t = _FOOTER.sub(" ", t)
    hits = len(re.findall(r"et al\.|\bdoi\b|\d{4};\s?\d+|\bPMID\b|\d{4}\.\s?\d+\(|\b\d{1,3}\(\d{1,2}\):\s?\d+|\b\d{1,4}:\d{1,4}-\d{1,4}\b", t))
    authors = len(re.findall(r"\b(?!Any\b)[A-Z][a-z]+ [A-Z]{1,3}\b(?=[,.])", t))  # 'Lee HJ,' 'Chung WS,' style author tokens
    return hits >= 3 or (hits >= 1 and (len(_REF_LINE.findall(t)) >= 2 or authors >= 3)) or authors >= 6 \
        or bool(re.match(r"\s*(?!Any\b)[A-Z][a-z]+ [A-Z]{1,2}[,.] .{0,120}(et al|\d{4})", t))


def _read(p: Path):
    if p.suffix.lower() == ".docx":
        import zipfile
        try:
            xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf8", "replace")
        except Exception:
            return []
        t = re.sub(r"<w:p[ >].*?</w:p>", lambda m: re.sub(r"<[^>]+>", "", m.group(0)) + "\n", xml, flags=re.S)
        t = re.sub(r"<[^>]+>", "", t)
        return [(i, t[i * 6000:(i + 1) * 6000]) for i in range(math.ceil(len(t) / 6000))]
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        try:
            return [(i, pg.extract_text() or "") for i, pg in enumerate(PdfReader(str(p)).pages)]
        except Exception:
            return []
    if p.suffix.lower() in (".txt", ".md"):
        t = p.read_text(errors="replace")
        return [(i, t[i * 6000:(i + 1) * 6000]) for i in range(math.ceil(len(t) / 6000))]
    return []


def _chunk_key(c):
    """Identity of a chunk's embedding input (title + text, the embedding model): equal keys can share one vector."""
    return hashlib.sha1((search.EMBED_MODEL + "\n" + c["title"] + "\n" + c["text"]).encode()).hexdigest()


def _sources_sig():
    """Organisation, region and boost are stored in each cached passage: a SOURCES or embedding model change rebuilds the index."""
    return hashlib.sha1((json.dumps(SOURCES, sort_keys=True) + search.EMBED_MODEL).encode()).hexdigest()


def _files_sig(root):
    fs = sorted((str(p.relative_to(root)), p.stat().st_size, int(p.stat().st_mtime)) for p in root.rglob("*") if p.is_file())
    return hashlib.sha1(json.dumps(fs).encode()).hexdigest()


CHUNK_CHARS = 1100


def _paragraphs(text):
    return [x.strip() for x in re.split(r"\n\s*\n|(?<=\.)\n", text) if len(x.strip()) > 40 and not _is_reference_list(x)]


def _fixed_chunks(pages):
    """Paragraphs packed into passages of about CHUNK_CHARS, never across a page: [(page, page_end, text)]."""
    out = []
    for i, text in pages:
        buf = ""
        for para in _paragraphs(re.sub(r"[ \t]+", " ", text)):
            if len(buf) + len(para) > CHUNK_CHARS and buf:
                out.append((i + 1, i + 1, buf.strip())); buf = ""
            buf += para + "\n"
        if buf.strip():
            out.append((i + 1, i + 1, buf.strip()))
    return out


# Section-aware chunking (V1 item 5.4): headings are numbered lines ("3.2 Imaging"), short ALL CAPS lines and "Recommendation"
# lines; a run of consecutive single-number lines is a list, not headings; table-of-contents lines (ending in a page number) are not
# headings; lines printed on many pages of a file (running header / footer) are dropped.
_NUM_HEAD = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][^\n]{2,90})$")
_RECOMM = re.compile(r"^(?:Key\s+)?Recommendations?\b[^\n]{0,90}$", re.I)


def _caps_line(s):
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 5 and sum(c.isupper() for c in letters) / len(letters) > 0.85 and len(s) <= 90 and len(s.split()) <= 12


def _heading(line, prev="", nxt=""):
    """(level, text) when a line is a section heading: 1 to 4 for numbered ones, 0 for ALL CAPS, 9 for Recommendation."""
    s = line.strip()
    if not s or len(s) > 100 or s.endswith((".", ",", ";")) or re.search(r"\s\d{1,3}$", s) or _is_reference_list(s):
        return None
    m = _NUM_HEAD.match(s)
    if m and len(s.split()) <= 14 and not re.search(r"\b[A-Z][a-z]+ [A-Z]{1,3}[,.]", s):
        level = m.group(1).count(".") + 1
        if level == 1 and any(_NUM_HEAD.match(x.strip()) and "." not in _NUM_HEAD.match(x.strip()).group(1) for x in (prev, nxt) if x.strip()):
            return None  # '1. History', '2. CECT thorax', ...: a list
        return (level, s)
    if _RECOMM.match(s):
        return (9, s)
    if _caps_line(s) and not re.fullmatch(r"[\dA-Z .:/\-]+\d", s):
        return (0, s)
    return None


def _running_lines(pages):
    """Lines (digits masked) printed on at least 40 % of a file's pages: running headers and footers."""
    if len(pages) < 4:
        return set()
    cnt = Counter()
    for _, t in pages:
        cnt.update({re.sub(r"\d+", "#", ln.strip()) for ln in t.splitlines() if ln.strip()})
    return {k for k, n in cnt.items() if n >= max(3, 0.4 * len(pages))}


def _section_chunks(pages, min_break=400):
    """Passages within sections, each prefixed with its heading path; a passage may run across pages inside one section, small
    sections are merged until a passage holds min_break characters: [(page, page_end, text)]."""
    running = _running_lines(pages)
    lines = [(i + 1, ln) for i, t in pages for ln in re.sub(r"[ \t]+", " ", t).splitlines() if re.sub(r"\d+", "#", ln.strip()) not in running]
    sections, cur, stack = [], {"head": [], "lines": []}, []
    for j, (pg, ln) in enumerate(lines):
        h = _heading(ln, lines[j - 1][1] if j else "", lines[j + 1][1] if j + 1 < len(lines) else "")
        if not h:
            cur["lines"].append((pg, ln)); continue
        lvl, txt = h
        if 1 <= lvl <= 4:
            stack = [x for x in stack if x[0] < lvl] + [(lvl, txt)]
            path = [x[1] for x in stack]
        else:
            path = ([stack[-1][1]] if stack else []) + [txt]
        sections.append(cur); cur = {"head": path, "lines": []}
    sections.append(cur)
    out, st = [], {"buf": "", "a": None, "b": None, "head": []}

    def flush():
        if st["buf"].strip():
            prefix = " > ".join(st["head"])
            out.append((st["a"], st["b"], (prefix + "\n" if prefix else "") + st["buf"].strip()))
        st.update(buf="", a=None)
    def close(par, paras):  # a paragraph longer than a passage (tables, flowcharts) is cut at line ends
        piece = []
        for pg, ln in par:
            if piece and sum(len(x) + 1 for _, x in piece) + len(ln) > CHUNK_CHARS:
                paras.append((piece[0][0], piece[-1][0], "\n".join(x for _, x in piece))); piece = []
            piece.append((pg, ln))
        if piece:
            paras.append((piece[0][0], piece[-1][0], "\n".join(x for _, x in piece)))
    for sec in sections:
        paras, cur_p = [], []
        for pg, ln in sec["lines"]:
            if not ln.strip():
                if cur_p:
                    close(cur_p, paras); cur_p = []
                continue
            cur_p.append((pg, ln))
            if ln.rstrip().endswith("."):
                close(cur_p, paras); cur_p = []
        if cur_p:
            close(cur_p, paras)
        paras = [(a, b, x.strip()) for a, b, x in paras if len(x.strip()) > 40 and not _is_reference_list(x)]
        if not paras:
            continue
        if len(st["buf"]) >= min_break:
            flush()
        if st["a"] is None:
            st["head"] = sec["head"]
        for a, b, x in paras:
            if len(st["buf"]) + len(x) > CHUNK_CHARS and st["buf"]:
                flush(); st["head"] = sec["head"]
            if st["a"] is None:
                st["a"] = a
            st["buf"] += x + "\n"; st["b"] = b
    flush()
    return out


CHUNKERS = {"fixed": _fixed_chunks, "section": _section_chunks}


class GuidelineIndex:
    def __init__(self, chunking=None):
        """chunking: "fixed" (paragraphs packed per page) or "section" (within detected sections, heading prefixed, V1 item 5.4);
        default config.GUIDELINE_CHUNKING. Each mode keeps its own cache files."""
        self.chunking = chunking or config.GUIDELINE_CHUNKING
        if self.chunking not in CHUNKERS:
            raise ValueError(f"unknown guideline chunking {self.chunking!r}")
        root = config.GUIDELINE_DIR
        cdir = config.DATA_ROOT / "embed_cache"; cdir.mkdir(parents=True, exist_ok=True)
        stem = "guidelines" if self.chunking == "fixed" else f"guidelines_{self.chunking}"
        self._npz = cdir / f"{stem}.npz"
        fsig = _files_sig(root) if root.exists() else "none"
        cached = cdir / f"{stem}_index.json"
        old = []
        if cached.exists():
            d = json.loads(cached.read_text())
            if d.get("files_sig") == fsig and d.get("version") == INDEX_VERSION and d.get("sources_sig") == _sources_sig() and self._npz.exists():
                self.chunks = d["chunks"]; self._finish(cdir, d["emb_sig"]); return
            old = d.get("chunks") or []  # rows of the cached vectors: unchanged chunks keep their embedding
        self.chunks = []
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in (".pdf", ".txt", ".md", ".docx") or "cap_protocols" in str(p) and p.suffix.lower() == ".docx":
                continue
            folder = p.relative_to(root).parts[0]
            org, region, boost = SOURCES.get(folder, (folder, "International", 1.0))
            meta = {"file": str(p.relative_to(root)), "title": _title(p), "org": org, "region": region, "boost": boost}
            self.chunks += [{"text": t, **meta, "page": a, "page_end": b} for a, b, t in CHUNKERS[self.chunking](_read(p))]
        sig = hashlib.sha1(json.dumps([c["file"] + str(c["page"]) + c["text"][:50] for c in self.chunks]).encode()).hexdigest()
        self._finish(cdir, sig, old)
        tmp = cached.with_name(cached.name + f".{os.getpid()}.tmp")  # written whole, then renamed: a reader never sees half a file
        tmp.write_text(json.dumps({"files_sig": fsig, "version": INDEX_VERSION, "sources_sig": _sources_sig(), "chunking": self.chunking,
                                   "emb_sig": sig, "chunks": self.chunks}))
        os.replace(tmp, cached)

    def _finish(self, cdir, sig, old=()):
        self.tok = [search.tokenize(c["title"] + " " + c["text"]) for c in self.chunks]
        self.df = Counter(t for ts in self.tok for t in set(ts))
        self.avgdl = sum(map(len, self.tok)) / max(len(self.tok), 1)
        cache = getattr(self, "_npz", cdir / "guidelines.npz")
        z = dict(np.load(cache)) if cache.exists() else None
        if z is not None and z["sig"].item() == sig:
            self.emb = z["emb"]; self.reused = len(self.chunks)
        else:
            keys = [_chunk_key(c) for c in self.chunks]
            reuse = {}
            if z is not None:  # vectors of the previous build, by chunk key (older caches: keyed through the previous chunk list)
                prev = list(z["keys"]) if "keys" in z else ([_chunk_key(c) for c in old] if len(old) == len(z["emb"]) else [])
                reuse = dict(zip(prev, z["emb"]))
            todo = [i for i, k in enumerate(keys) if k not in reuse]
            texts = [self.chunks[i]["title"] + "\n" + self.chunks[i]["text"] for i in todo]
            # embed in batches so a long rebuild never holds the embedder lock continuously (Case File searches interleave)
            m = np.concatenate([search._embed(texts[i:i + 128]) for i in range(0, len(texts), 128)]) if texts else np.zeros((0, 768), np.float32)
            m = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
            new = dict(zip(todo, m))
            self.emb = np.array([new[i] if i in new else reuse[k] for i, k in enumerate(keys)], np.float32).reshape(len(keys), -1) \
                if keys else np.zeros((0, 768), np.float32)
            self.reused = len(keys) - len(todo)
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_name(f"{cache.stem}.{os.getpid()}.tmp.npz")
            np.savez(tmp, emb=self.emb, sig=np.array(sig), keys=np.array(keys)); os.replace(tmp, cache)

    def _source_mask(self, sources):
        """Chunks inside the given sources: [(folder, file names or None)] (a specialty pack, V1 item 5.5); cached per pack."""
        key = tuple((f, tuple(sorted(fs)) if fs else None) for f, fs in sources)
        masks = self.__dict__.setdefault("_masks", {})
        if key not in masks:
            allow = dict(key)
            masks[key] = np.array([(c["file"].split("/")[0] in allow) and (allow[c["file"].split("/")[0]] is None or c["file"].rsplit("/", 1)[-1] in allow[c["file"].split("/")[0]])
                                   for c in self.chunks], bool)
        return masks[key]

    def search(self, q, k=8, cancer=None, sources=None):
        """Hybrid search; sources=[(folder, file names or None)] limits it to those folders / files, ranked among them only."""
        if not self.chunks:
            return []
        n = len(self.chunks); lex = np.zeros(n)
        for t in set(search.tokenize(q)):
            if t in self.df:
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                for i, ts in enumerate(self.tok):
                    tf = ts.count(t)
                    if tf:
                        lex[i] += idf * tf * 2.4 / (tf + 1.4 * (0.25 + 0.75 * len(ts) / self.avgdl))
        qv = search._embed([q], prefix="Represent this sentence for searching relevant passages: ")[0]
        sem = self.emb @ (qv / np.linalg.norm(qv))
        mask = self._source_mask(sources) if sources is not None else None
        if mask is not None:
            lex = np.where(mask, lex, -np.inf); sem = np.where(mask, sem, -np.inf)
        rr = np.zeros(n)
        for arr in (lex, sem):
            for rank, i in enumerate(np.argsort(-arr)[:300]):
                rr[i] += 1.0 / (60 + rank + 1)
        words = CANCER_WORDS.get(cancer or "", [])
        for i, c in enumerate(self.chunks):
            rr[i] *= c["boost"] * (1.25 if words and any(w in (c["file"] + c["title"]).lower() for w in words) else (0.8 if words else 1.0))
        if mask is not None:
            rr = np.where(mask, rr, -1.0)
        top = [i for i in np.argsort(-rr)[:k] if rr[i] >= 0]
        return [{**{k2: self.chunks[i][k2] for k2 in ("text", "file", "title", "org", "region", "page")}, "page_end": self.chunks[i].get("page_end") or self.chunks[i]["page"],
                 "score": round(float(rr[i]), 5)} for i in top]


def search_grouped(q, cancer=None, india=3, intl=4):
    """India-first presentation: top Indian (NCG / ICMR) passages, then international ones. Reference lists excluded."""
    hits = [h for h in index().search(q, 60, cancer) if not _is_reference_list(h["text"])]
    return {"india": [h for h in hits if h["region"] == "India"][:india], "international": [h for h in hits if h["region"] != "India"][:intl]}


def ready():
    """Whether the shared index is loaded (the agents never wait for a rebuild, V1 Phase 5 review)."""
    return _IDX is not None


def index():
    global _IDX
    with _lock:
        if _IDX is None:
            _IDX = GuidelineIndex()
        return _IDX


def queries_for_case(case_id):
    """Turn the case's open Pre-Authorization items and protocol into guideline look-ups (reference only). An unlisted
    Case File (V1 item 2.5) has no protocol and no gate, so there is nothing case-specific to look up yet."""
    from . import store
    case = store.get_case(case_id)
    if not case.get("protocol"):
        return []
    prot = protocol.get(case["protocol"])
    gate = store.get_state(case_id).get("gate") or {}
    qs = []
    for r in gate.get("requirements", []):
        if r["status"] not in ("satisfied", "not_applicable"):
            qs.append(f"{prot['label']}: {r['label']} before multidisciplinary treatment planning")
    base = {"lung_nsclc": ["NSCLC staging work-up PET-CT brain MRI", "NSCLC biomarker testing EGFR ALK ROS1 PD-L1 before treatment"],
            "breast": ["breast cancer ER PR HER2 Ki-67 testing and reporting", "breast cancer staging work-up imaging locally advanced"],
            "colorectal_rectum": ["rectal cancer restaging MRI after chemoradiotherapy response assessment", "rectal cancer MRI reporting mesorectal fascia EMVI"]}
    return (qs + base.get(prot["id"], []))[:6]
