"""Guideline library retrieval (reference text for the board, never a recommendation for this patient).

Indexes the freely available guideline documents in TB_GUIDELINE_DIR (see docs/tumour-board/RESOURCES.md):
India first (National Cancer Grid, ICMR), then international (ESMO incl. Pan-Asian adaptations, CAP / ASCO-CAP,
ACR, RECIST) and US public-domain summaries (NCI PDQ). Hybrid BM25 + embeddings, with an India-first boost.
NCCN content is not ingested (licence restricts AI use)."""
import hashlib, json, math, re, threading
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
}
CANCER_WORDS = {"lung_nsclc": ["lung", "nsclc", "thoracic"], "breast": ["breast"], "colorectal_rectum": ["rect", "colorectal", "colon"]}
_lock = threading.Lock()
_IDX = None


def _title(p: Path):
    return re.sub(r"[_\-]+", " ", p.stem).strip()


_REF_LINE = re.compile(r"(^|\n|\.\s)[A-Z][A-Za-z'\-]+ [A-Z]{1,3}[,.]\s")


def _is_reference_list(t):
    """Bibliography text (author lists, journal citations) is not guideline content."""
    hits = len(re.findall(r"et al\.|\bdoi\b|\d{4};\s?\d+|\bPMID\b|\d{4}\.\s?\d+\(|\b\d{1,3}\(\d{1,2}\):\s?\d+|\b\d{1,4}:\d{1,4}-\d{1,4}\b", t))
    authors = len(re.findall(r"\b[A-Z][a-z]+ [A-Z]{1,3}\b(?=[,.])", t))  # 'Lee HJ,' 'Chung WS,' style author tokens
    return hits >= 3 or (hits >= 1 and (len(_REF_LINE.findall(t)) >= 2 or authors >= 3)) or authors >= 6 \
        or bool(re.match(r"\s*[A-Z][a-z]+ [A-Z]{1,2}[,.] .{0,120}(et al|\d{4})", t))


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


def _files_sig(root):
    fs = sorted((str(p.relative_to(root)), p.stat().st_size, int(p.stat().st_mtime)) for p in root.rglob("*") if p.is_file())
    return hashlib.sha1(json.dumps(fs).encode()).hexdigest()


class GuidelineIndex:
    def __init__(self):
        root = config.GUIDELINE_DIR
        cdir = config.DATA_ROOT / "embed_cache"; cdir.mkdir(parents=True, exist_ok=True)
        fsig = _files_sig(root) if root.exists() else "none"
        cached = cdir / "guidelines_index.json"
        if cached.exists():
            d = json.loads(cached.read_text())
            if d.get("files_sig") == fsig and (cdir / "guidelines.npz").exists():
                self.chunks = d["chunks"]; self._finish(cdir, d["emb_sig"]); return
        self.chunks = []
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in (".pdf", ".txt", ".md", ".docx") or "cap_protocols" in str(p) and p.suffix.lower() == ".docx":
                continue
            folder = p.relative_to(root).parts[0]
            org, region, boost = SOURCES.get(folder, (folder, "International", 1.0))
            for page, text in _read(p):
                text = re.sub(r"[ \t]+", " ", text)
                paras = [x.strip() for x in re.split(r"\n\s*\n|(?<=\.)\n", text) if len(x.strip()) > 40 and not _is_reference_list(x)]
                buf = ""
                for para in paras:
                    if len(buf) + len(para) > 1100 and buf:
                        self.chunks.append({"text": buf.strip(), "file": str(p.relative_to(root)), "title": _title(p), "org": org, "region": region, "boost": boost, "page": page + 1}); buf = ""
                    buf += para + "\n"
                if buf.strip():
                    self.chunks.append({"text": buf.strip(), "file": str(p.relative_to(root)), "title": _title(p), "org": org, "region": region, "boost": boost, "page": page + 1})
        sig = hashlib.sha1(json.dumps([c["file"] + str(c["page"]) + c["text"][:50] for c in self.chunks]).encode()).hexdigest()
        self._finish(cdir, sig)
        cached.write_text(json.dumps({"files_sig": fsig, "emb_sig": sig, "chunks": self.chunks}))

    def _finish(self, cdir, sig):
        self.tok = [search.tokenize(c["title"] + " " + c["text"]) for c in self.chunks]
        self.df = Counter(t for ts in self.tok for t in set(ts))
        self.avgdl = sum(map(len, self.tok)) / max(len(self.tok), 1)
        cache = cdir / "guidelines.npz"
        if cache.exists() and np.load(cache)["sig"].item() == sig:
            self.emb = np.load(cache)["emb"]
        else:
            # embed in batches so a long rebuild never holds the embedder lock continuously (Case File searches interleave)
            texts = [c["title"] + "\n" + c["text"] for c in self.chunks]
            m = np.concatenate([search._embed(texts[i:i + 128]) for i in range(0, len(texts), 128)]) if texts else np.zeros((0, 768), np.float32)
            self.emb = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
            cache.parent.mkdir(parents=True, exist_ok=True); np.savez(cache, emb=self.emb, sig=np.array(sig))

    def search(self, q, k=8, cancer=None):
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
        rr = np.zeros(n)
        for arr in (lex, sem):
            for rank, i in enumerate(np.argsort(-arr)[:300]):
                rr[i] += 1.0 / (60 + rank + 1)
        words = CANCER_WORDS.get(cancer or "", [])
        for i, c in enumerate(self.chunks):
            rr[i] *= c["boost"] * (1.25 if words and any(w in (c["file"] + c["title"]).lower() for w in words) else (0.8 if words else 1.0))
        top = np.argsort(-rr)[:k]
        return [{**{k2: self.chunks[i][k2] for k2 in ("text", "file", "title", "org", "region", "page")}, "score": round(float(rr[i]), 5)} for i in top]


def search_grouped(q, cancer=None, india=3, intl=4):
    """India-first presentation: top Indian (NCG / ICMR) passages, then international ones. Reference lists excluded."""
    hits = [h for h in index().search(q, 60, cancer) if not _is_reference_list(h["text"])]
    return {"india": [h for h in hits if h["region"] == "India"][:india], "international": [h for h in hits if h["region"] != "India"][:intl]}


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
