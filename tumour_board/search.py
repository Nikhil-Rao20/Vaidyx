"""Case File search: (1) instant value finder over every line of every document, with oncology synonyms;
(2) hybrid retrieval = BM25 (exact terms, values) + dense embeddings (meaning), fused by Reciprocal Rank Fusion.

Every hit carries doc_id, page and character offsets so the UI can highlight the exact source text."""
import hashlib, math, re, threading
from collections import Counter

import numpy as np

from . import config, dates, rules, store

EMBED_MODEL = "snowflake/snowflake-arctic-embed-m-long"  # US (Snowflake), Apache-2.0, non-medical, fp32 ONNX on CPU
_embedder = None
_emb_lock = threading.Lock()
_index_cache = {}

SYNONYMS = {
    "pd-l1": ["pd-l1", "pdl1", "pd l1", "tps", "22c3", "sp263", "cps"], "ki-67": ["ki-67", "ki67", "mib-1", "mib1"],
    "her2": ["her2", "her-2", "erbb2", "her2/neu", "cep17"], "er": ["estrogen receptor", "oestrogen receptor", r"\ber\b"],
    "pr": ["progesterone receptor", r"\bpr\b", r"\bpgr\b"], "cea": [r"\bcea\b", "carcinoembryonic"],
    "egfr": ["egfr"], "alk": [r"\balk\b"], "ros1": ["ros1"], "kras": ["kras"], "braf": ["braf"], "nras": ["nras"],
    "mmr": [r"\bmmr\b", "mlh1", "msh2", "msh6", "pms2", "mismatch repair", r"\bmsi\b"],
    "haemoglobin": ["haemoglobin", "hemoglobin", r"\bhb\b", r"\bhgb\b"], "wbc": [r"\bwbc\b", "white cell", r"\btlc\b", "leucocyte", "leukocyte"],
    "platelets": ["platelet", r"\bplt\b"], "creatinine": ["creatinine"], "bilirubin": ["bilirubin"],
    "ecog": [r"\becog\b", "performance status", r"\bkps\b", "karnofsky"], "suv": [r"\bsuv", "suvmax"],
    "stage": [r"\bstage\b", r"\b[cpy]?t[0-4][a-d]?\s*n[0-3]", r"\bm[01][a-c]?\b", r"\btnm\b"], "grade": [r"\bgrade\b", "differentiated", "nottingham"],
    "margin": ["margin", r"\bcrm\b", "mesorectal fascia", r"\bmrf\b"], "lvi": ["lymphovascular", r"\blvi\b", "emvi", r"\blvsi\b"],
    # V1 item 9.1 (oral cavity)
    "doi": ["depth of invasion", r"\bdoi\b"], "pni": ["perineural", r"\bpni\b"],
    "ene": ["extranodal", "extra nodal", "extracapsular", "perinodal", r"\bene\b", r"\bece\b"],
    "tobacco": ["tobacco", "gutka", "gutkha", "khaini", r"\bmawa\b", "betel", r"\bpaan\b", r"\bareca\b", r"\bbidi\b", r"\bbeedi\b"],
    "dental": [r"\bdental\b", r"\bopg\b", "orthopantomogram"],
    # V1 item 9.2 (cervix)
    "figo": [r"\bfigo\b"], "parametrium": [r"\bparametri"], "hiv": [r"\bhiv\b", "retroviral"],
}
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


def tokenize(s):
    return _TOKEN.findall(s.lower())


def _patterns(query):
    q = query.lower().strip()
    pats = []
    for key, syns in SYNONYMS.items():
        # the key itself matches only as a whole word: "er" must not match inside "her2" (V1 item 1.1)
        if any(re.search(s if s.startswith(r"\b") else re.escape(s), q) for s in syns) or re.search(r"\b" + re.escape(key) + r"\b", q):
            pats += [s if s.startswith(r"\b") else (r"\b" + re.escape(s) + r"\b" if len(s) <= 5 else re.escape(s)) for s in syns]
    if not pats:  # plain words of the query (skip filler words)
        stop = {"what", "is", "the", "of", "a", "an", "in", "for", "and", "was", "were", "value", "result", "results", "find", "show", "me", "where", "patient",
                "patients", "any", "all", "report", "reports", "on", "to", "does", "did", "has", "have", "with", "level", "levels", "he", "she", "him", "her",
                "his", "they", "them", "it", "this", "that", "these", "those", "should", "would", "could", "can", "will", "be", "been", "being", "are", "am",
                "do", "give", "get", "receive", "which", "when", "who", "whom", "how", "why", "from", "by", "at", "as", "or", "if", "there", "list", "every",
                "each", "its", "date", "dates", "tell", "please", "about", "documented", "recorded", "case", "file", "most", "latest", "current"}
        pats = [r"\b" + re.escape(w) + r"\b" for w in tokenize(q) if w not in stop and len(w) > 1]
    return pats


def _docs(case_id):
    """The documents with clinician confirmations overlaid (V1 item 2.2): page text is unchanged, but the document type and
    dates shown with every hit and passage are the confirmed ones."""
    return rules.case_docs(case_id)


def find_values(case_id, query, limit=60):
    """Line-level scan of every page of every document. Milliseconds for a Case File of hundreds of pages."""
    pats = _patterns(query)
    if not pats:
        return {"patterns": [], "hits": []}
    rx = re.compile("|".join(f"(?:{p})" for p in pats), re.I)
    hits = []
    for d in _docs(case_id):
        if d.get("state") != "ready":
            continue
        c = d.get("classification") or {}
        for pi, pg in enumerate(d.get("pages") or []):
            text = pg["text"]; pos = 0
            for line in text.splitlines(keepends=True):
                m = rx.search(line)
                if m and len(line.strip()) > 1:
                    s = pos + (len(line) - len(line.lstrip()))
                    hits.append({"doc_id": d["doc_id"], "doc_title": c.get("title") or d["filename"], "doc_type": c.get("doc_type"),
                                 "date": dates.doc_dates(d)["event"] or None, "status": c.get("status"), "page": pi, "start": s, "end": pos + len(line.rstrip()),
                                 "text": line.strip(), "match": m.group(0)})
                pos += len(line)
    hits.sort(key=lambda h: (h["date"] or ""), reverse=True)
    return {"patterns": pats, "hits": hits[:limit]}


# --------------------------------------------------------------------------------------------------------------
def chunks_for(doc, size=700, overlap_lines=1):
    out = []
    for pi, pg in enumerate(doc.get("pages") or []):
        lines, pos, buf, start = pg["text"].splitlines(keepends=True), 0, [], 0
        offs = []
        for ln in lines:
            offs.append(pos); pos += len(ln)
        i = 0
        while i < len(lines):
            j, length = i, 0
            while j < len(lines) and (length + len(lines[j]) <= size or j == i):
                length += len(lines[j]); j += 1
            text = "".join(lines[i:j]).strip()
            if text:
                out.append({"doc_id": doc["doc_id"], "page": pi, "start": offs[i], "end": offs[j - 1] + len(lines[j - 1]), "text": text})
            if j >= len(lines):
                break
            i = max(j - overlap_lines, i + 1)
    return out


def _embed(texts, prefix=""):
    global _embedder
    with _emb_lock:
        if _embedder is None:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(EMBED_MODEL, cache_dir=str(config.DATA_ROOT / "embed_cache"), threads=16)
        return np.array(list(_embedder.embed([prefix + t for t in texts], batch_size=32)), dtype=np.float32)


class CaseIndex:
    def __init__(self, case_id):
        docs = [d for d in _docs(case_id) if d.get("state") == "ready"]
        self.meta = {d["doc_id"]: d for d in docs}
        self.chunks = [ch for d in docs for ch in chunks_for(d)]
        for i, ch in enumerate(self.chunks):
            c = self.meta[ch["doc_id"]].get("classification") or {}
            ch.update(id=f"C{i}", doc_title=c.get("title") or self.meta[ch["doc_id"]]["filename"], doc_type=c.get("doc_type"),
                      date=dates.doc_dates(self.meta[ch["doc_id"]])["event"] or None, status=c.get("status"))
        self.tok = [tokenize(c["doc_title"] + " " + c["text"]) for c in self.chunks]
        self.df = Counter(t for ts in self.tok for t in set(ts))
        self.avgdl = sum(map(len, self.tok)) / max(len(self.tok), 1)
        self.emb = None
        if self.chunks:
            cache = config.DATA_ROOT / "embed_cache" / "chunks"; cache.mkdir(parents=True, exist_ok=True)
            vecs, todo = [None] * len(self.chunks), []
            for i, ch in enumerate(self.chunks):
                h = hashlib.sha1((EMBED_MODEL + ch["text"]).encode()).hexdigest()
                f = cache / f"{h}.npy"
                if f.exists():
                    vecs[i] = np.load(f)
                else:
                    todo.append((i, f))
            if todo:
                new = _embed([self.chunks[i]["doc_title"] + "\n" + self.chunks[i]["text"] for i, _ in todo])
                for (i, f), v in zip(todo, new):
                    np.save(f, v); vecs[i] = v
            m = np.stack(vecs); self.emb = m / np.linalg.norm(m, axis=1, keepdims=True)

    def bm25(self, q, k1=1.4, b=0.75):
        qt = tokenize(q); n = len(self.chunks); scores = np.zeros(n)
        for t in set(qt):
            if t not in self.df:
                continue
            idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            for i, ts in enumerate(self.tok):
                tf = ts.count(t)
                if tf:
                    scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(ts) / self.avgdl))
        return scores

    def search(self, q, k=10):
        if not self.chunks:
            return []
        lex = self.bm25(q + " " + " ".join(p.replace("\\b", "").replace("\\", "") for p in _patterns(q)))
        qv = _embed([q], prefix="Represent this sentence for searching relevant passages: ")[0]
        sem = self.emb @ (qv / np.linalg.norm(qv))
        rr = np.zeros(len(self.chunks))
        for arr in (lex, sem):
            order = np.argsort(-arr)
            for rank, i in enumerate(order):
                if arr is lex and arr[i] <= 0:
                    break
                rr[i] += 1.0 / (60 + rank + 1)
        top = np.argsort(-rr)[:k]
        return [{**self.chunks[i], "score": round(float(rr[i]), 5), "bm25": round(float(lex[i]), 3), "cosine": round(float(sem[i]), 3)} for i in top]


def index(case_id):
    sig = tuple(sorted((d["doc_id"], d.get("processed", ""), tuple(d.get("confirmations") or ())) for d in _docs(case_id) if d.get("state") == "ready"))
    cur = _index_cache.get(case_id)
    if not cur or cur[0] != sig:
        _index_cache[case_id] = (sig, CaseIndex(case_id))
    return _index_cache[case_id][1]


def _doc_block(d, text):
    c = d.get("classification") or {}
    return (f"=== DOCUMENT {d['doc_id']} | {c.get('title') or d['filename']} | type {c.get('doc_type')} | date {dates.doc_dates(d)['event'] or c.get('report_date') or '?'} "
            f"| status {c.get('status')}{' | UNSIGNED' if c.get('signed') == 'no' else ''} ===\n{text}")


def context_for(case_id, question, budget=48000, doc_types=None):
    """Model context for a question. Whole Case File when it fits; otherwise whole documents in relevance order
    (most relevant passage score, recency as tie-break) until the budget is used, then the best remaining passages.
    Returns (context, mode)."""
    docs = [d for d in _docs(case_id) if d.get("state") == "ready" and (not doc_types or (d.get("classification") or {}).get("doc_type") in doc_types)]
    full = {d["doc_id"]: "\n".join(p["text"] for p in d.get("pages") or []) for d in docs}
    total = sum(len(_doc_block(d, full[d["doc_id"]])) + 2 for d in docs)
    if total <= budget:
        return "\n\n".join(_doc_block(d, full[d["doc_id"]]) for d in docs), "full Case File"
    ix = index(case_id)
    hits = ix.search(question, k=60)
    best = {}
    for h in hits:
        if h["doc_id"] in full:
            best[h["doc_id"]] = max(best.get(h["doc_id"], 0.0), h["score"])
    order = sorted(docs, key=lambda d: (best.get(d["doc_id"], 0.0), dates.doc_dates(d)["event"]), reverse=True)
    parts, used, included = [], 0, set()
    for d in order:
        blk = _doc_block(d, full[d["doc_id"]])
        if used + len(blk) <= budget * 0.85:
            parts.append(blk); used += len(blk) + 2; included.add(d["doc_id"])
    for h in hits:  # best passages from documents that did not fit whole
        if h["doc_id"] in included:
            continue
        blk = f"=== PASSAGE from {h['doc_id']} | {h['doc_title']} | {h['date'] or '?'} | page {h['page'] + 1} ===\n{h['text']}"
        if used + len(blk) > budget:
            break
        parts.append(blk); used += len(blk) + 2
    return "\n\n".join(parts), f"{len(included)} of {len(docs)} documents whole, plus passages"
