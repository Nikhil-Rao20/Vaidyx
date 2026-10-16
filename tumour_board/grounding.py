"""Source grounding: verify that a quote really occurs in a document and locate it (character offsets per page).

Idea borrowed from source-grounded extraction tools (e.g. Google LangExtract): the model must return verbatim
evidence; code aligns that evidence to the source text. Anything that cannot be aligned is not trusted.
"""
import re
import unicodedata

from rapidfuzz import fuzz

_TRANS = str.maketrans({"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
                        " ": " ", "µ": "u", "μ": "u", "|": " "})


def norm_with_map(s: str):
    """Lowercase, unify punctuation, collapse whitespace. Returns (normalised, index map back into s)."""
    out, idx = [], []
    prev_space = True
    for i, ch in enumerate(s):
        ch = unicodedata.normalize("NFKC", ch).translate(_TRANS).lower()
        for c in ch:
            if c.isspace() or c in "*_`#":
                if not prev_space:
                    out.append(" "); idx.append(i); prev_space = True
            else:
                out.append(c); idx.append(i); prev_space = False
    while out and out[-1] == " ":
        out.pop(); idx.pop()
    return "".join(out), idx


def norm(s: str) -> str:
    return norm_with_map(s or "")[0]


NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers(s: str):
    return NUM.findall(s or "")


def locate(quote: str, pages: list, min_score: float = 92.0):
    """Find quote in pages (list of str). Returns dict(page, start, end, score, matched) or None."""
    q = norm(quote)
    if len(q) < 2:
        return None
    best = None
    for pi, text in enumerate(pages):
        n, idx = norm_with_map(text)
        k = n.find(q)
        if k >= 0:
            return {"page": pi, "start": idx[k], "end": idx[k + len(q) - 1] + 1, "score": 100.0, "matched": text[idx[k]: idx[k + len(q) - 1] + 1]}
        if len(q) >= 12:
            al = fuzz.partial_ratio_alignment(q, n, score_cutoff=min_score)
            if al and (best is None or al.score > best["score"]):
                s, e = al.dest_start, max(al.dest_end - 1, al.dest_start)
                best = {"page": pi, "start": idx[s], "end": idx[e] + 1, "score": round(al.score, 1), "matched": text[idx[s]: idx[e] + 1]}
    if best and set(numbers(quote)) <= set(numbers(best["matched"])):  # fuzzy match must not change any number
        return best
    return None


def value_supported(value: str, matched_text: str) -> bool:
    """The extracted value must be backed by the located evidence: every number in the value appears in the
    evidence, and the value's words overlap the evidence (tolerant to case/punctuation)."""
    if value is None:
        return False
    v, m = norm(str(value)), norm(matched_text)
    if not v:
        return False
    if v in m:
        return True
    if not set(numbers(v)) <= set(numbers(m)):
        return False
    words = [w for w in re.findall(r"[a-z0-9.+%/-]+", v) if len(w) > 1]
    if not words:
        return bool(numbers(v))
    hit = sum(1 for w in words if w in m)
    return hit / len(words) >= 0.6 or fuzz.partial_ratio(v, m) >= 85


def verify(value, quote, pages):
    """Returns dict(status=verified|unverified, location) for an extracted value + quote."""
    loc = locate(quote or "", pages)
    if not loc:
        return {"status": "unverified", "reason": "quote not found in document", "location": None}
    if value is not None and not value_supported(value, loc["matched"]):
        return {"status": "unverified", "reason": "value not supported by quoted text", "location": loc}
    if loc["score"] < 100:  # fuzzy alignment: never auto-trusted (clinical rule), shown to the expert for review
        return {"status": "needs_review", "reason": f"quote matched approximately ({loc['score']})", "location": loc}
    return {"status": "verified", "location": loc}
