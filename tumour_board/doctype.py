"""Document type cross-check (V1 item 3.2): a keyword second opinion on the reader model's document type.

Deterministic, no model. Reads ONLY the header of page 1 (the first ~10 non-empty lines: hospital, department, title,
study name) and the filename, never deeper, against the editable table protocols/doc_type_keywords.json (its `_note`
explains the matching). A histopathology report that mentions a "CT guided biopsy" in its body stays histopathology.

  keyword_type(texts, filename)            -> {"type", "evidence", "scores"}
  cross_check(model_type, texts, filename) -> {"keyword_type", "model_type", "agree", "evidence", "note"}

Agree, or no keyword evidence (agree is None): the model's type stands. Disagree: the caller keeps both types and asks a
clinician to confirm the type wherever it matters (confirm_doc_type). This module only reports; it never decides.
"""
import json
import re
from functools import lru_cache

from . import config

_SEP = r"[\s\-/._]*"           # a space, hyphen, slash, dot or underscore in a phrase matches any of them or nothing
_SPLIT_PHRASE = re.compile(r"[\s\-/._]+")
_SEGMENT = re.compile(r"\s+[-–]\s+|[,;:]\s+|\s{3,}")  # " - ", ": ", ", " and wide gaps separate header segments
_REPORT_END = re.compile(r"\breport\b(?:\s*\([^()]*\))?\W*$", re.I)  # "... REPORT", "... REPORT (LIS export)"


def _phrase(p: str) -> str:
    body = _SEP.join(re.escape(x) for x in _SPLIT_PHRASE.split(p.strip()) if x)
    return rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"


def _alt(phrases, flags=re.I):
    phrases = [p for p in phrases or [] if p and p.strip()]
    if not phrases:
        return None
    # longest first, so the evidence names the most specific phrase ("CECT" before "CT")
    return re.compile("|".join(_phrase(p) for p in sorted(phrases, key=len, reverse=True)), flags)


@lru_cache(maxsize=1)
def table() -> dict:
    """protocols/doc_type_keywords.json with every phrase list compiled (loaded once)."""
    d = json.loads((config.PROTOCOL_DIR / "doc_type_keywords.json").read_text())
    types = {}
    for t, spec in d["types"].items():
        cs = spec.get("case_sensitive") or []
        types[t] = {"any": _alt(spec.get("patterns")), "title": _alt(spec.get("title_only")),
                    "cs": _alt(cs, 0), "cs_any_case": _alt(cs), "beats": list(spec.get("beats") or [])}
    add = d.get("addendum") or {}
    return {"header_lines": int(d.get("header_lines", 10)), "title_lines": int(d.get("title_lines", 3)),
            "weights": {"title": 3, "header": 1, "filename": 0.5, "addendum_parent": 5, **(d.get("weights") or {})},
            "types": types, "ignore": _alt(d.get("ignore")),
            "department": _alt(d.get("department_words")), "institution": _alt(d.get("institution_words")),
            "addendum_title": _alt(add.get("title_words")), "addendum_parent": _alt(add.get("parent_phrases"))}


def _blank(rx, s: str) -> str:
    """The ignore phrases replaced by spaces (positions kept)."""
    return rx.sub(lambda m: " " * len(m.group(0)), s) if rx else s


def _first_page(texts) -> str:
    if isinstance(texts, str):
        return texts
    for t in texts or []:
        return (t.get("text") if isinstance(t, dict) else t) or ""
    return ""


def _is_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) >= 0.85 * len(letters)


def _header(text: str, n: int):
    """[(line number, line)] of the first n non-empty lines (a line needs a letter or digit to count)."""
    out = []
    for i, raw in enumerate(text.splitlines(), 1):
        if re.search(r"[A-Za-z0-9]", raw):
            out.append((i, raw.strip()))
            if len(out) >= n:
                break
    return out


def _segments(line: str):
    for cell in line.split("|"):
        for seg in _SEGMENT.split(cell):
            if seg.strip():
                yield seg


def _match(seg: str, tb: dict, title: bool, filename: bool = False) -> dict:
    """{type: matched text} for one piece of text (ignore phrases already blanked)."""
    hits = {}
    for t, rx in tb["types"].items():
        for key in ("any", "title", "cs_any_case" if filename else "cs"):
            if key == "title" and not title:
                continue
            m = rx[key].search(seg) if rx[key] else None
            if m and (t not in hits or len(m.group(0)) > len(hits[t])):
                hits[t] = m.group(0)
    return hits


def _apply_beats(hits: dict, tb: dict) -> dict:
    present = set(hits)
    beaten = {b for t in present for b in tb["types"][t]["beats"]}
    return {t: v for t, v in hits.items() if t not in beaten}


def keyword_type(texts, filename: str = "") -> dict:
    """The document type named by the header of page 1 and the filename.

    Returns {"type": a facts.json doc type or "" (no evidence, or two types share the top score),
             "evidence": [{"type", "keyword", "quote" (the exact line, or the filename), "where" ("line 3" | "filename"),
                           "weight"}],
             "scores": {type: score}}."""
    tb = table()
    w = tb["weights"]
    lines = _header(_first_page(texts), tb["header_lines"])
    many_caps = sum(_is_caps(s) for _, s in lines) > 0.6 * max(1, len(lines))  # an all-capitals report: capitals mark nothing
    evidence = []
    rows = []  # (line number, line, {type: (weight, keyword)}, is addendum title)
    for k, (num, line) in enumerate(lines):
        clean = _blank(tb["ignore"], line)
        is_title = k < tb["title_lines"] or (_is_caps(clean) and not many_caps) or bool(_REPORT_END.search(clean))
        hits, addendum = {}, False
        for seg in _segments(clean):
            # a department or hospital name is not the document's title, even in capitals
            minor = any(rx is not None and rx.search(seg) for rx in (tb["department"], tb["institution"]))
            seg_title = is_title and not minor
            if seg_title and tb["addendum_title"] is not None and tb["addendum_title"].search(seg):
                addendum = True
            for t, kw in _match(seg, tb, seg_title).items():
                wt = w["title"] if seg_title else w["header"]
                if t not in hits or wt > hits[t][0]:
                    hits[t] = (wt, kw)
        kept = _apply_beats({t: v[1] for t, v in hits.items()}, tb)
        rows.append((num, line, {t: hits[t] for t in kept}, addendum))

    # an addendum is filed with the report it belongs to ("Relates to IHC report of 19-Aug-2026")
    if any(r[3] for r in rows) and tb["addendum_parent"] is not None:
        for i, (num, line, hits, addendum) in enumerate(rows):
            m = None if addendum else tb["addendum_parent"].search(_blank(tb["ignore"], line))
            if not m:
                continue
            ref = _blank(tb["ignore"], line)[m.end():]
            ref = re.split(r"(?i)\breport\b", ref)[0]
            for t, kw in _apply_beats(_match(ref, tb, True), tb).items():
                hits[t] = (w["addendum_parent"], kw)

    for num, line, hits, _ in rows:
        for t, (wt, kw) in sorted(hits.items(), key=lambda x: -x[1][0]):
            evidence.append({"type": t, "keyword": kw, "quote": line, "where": f"line {num}", "weight": wt})

    if filename:
        base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename.replace("\\", "/").rsplit("/", 1)[-1])
        name = _blank(tb["ignore"], base.replace("_", " "))
        for t, kw in _apply_beats(_match(name, tb, True, filename=True), tb).items():
            evidence.append({"type": t, "keyword": kw, "quote": filename, "where": "filename", "weight": w["filename"]})

    scores = {}
    for e in evidence:
        scores[e["type"]] = scores.get(e["type"], 0) + e["weight"]
    best = ""
    if scores:
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            best = ranked[0][0]
    return {"type": best, "evidence": evidence, "scores": scores}


def _where(e: dict) -> str:
    if e["where"] == "filename":
        return f"the filename {e['quote']}"
    tb = table()["weights"]
    kind = "the title line" if e["weight"] >= tb["title"] else f"header {e['where']}"
    return f"{kind} says {e['quote']}"


STRONG = 3  # a disagreement needs title-level evidence (a title line scores 3); a lone header line (1) or filename (0.5) is only a hint


def cross_check(model_type, texts, filename: str = "") -> dict:
    """The keyword type against the reader model's type.

    agree: True (same type), False (different: keep both, confirm_doc_type where it matters), None (no keyword evidence
    or ambiguous evidence: the model's type stands). note: one plain-English sentence for the reviewer."""
    model_type = (model_type or "").strip()
    kw = keyword_type(texts, filename)
    kt = kw["type"]
    said = f"the reader model said {model_type}" if model_type else "the reader model gave no type"
    if not kt:
        if kw["scores"]:
            tops = sorted(t for t, s in kw["scores"].items() if s == max(kw["scores"].values()))
            note = f"the header points to more than one type ({', '.join(tops)}); "
        else:
            note = "no document type keywords in the header or filename; "
        note += f"the reader model's type ({model_type}) stands" if model_type else "the reader model gave no type"
        return {"keyword_type": "", "model_type": model_type, "agree": None, "evidence": kw["evidence"], "note": note}
    top = max((e for e in kw["evidence"] if e["type"] == kt), key=lambda e: e["weight"])
    agree = kt == model_type
    if not agree and model_type and kw["scores"].get(kt, 0) < STRONG and not (model_type == "other" and top.get("where") == "filename"):
        # a lone header line ("Review with CBP, LFT after 1 week" in an OPD note) is a hint, not a title: the model's type stands;
        # when the model gave up (other), the filename still counts
        note = f"only a weak keyword hint: {_where(top)} ({kt}); the reader model's type ({model_type}) stands"
        return {"keyword_type": kt, "model_type": model_type, "agree": None, "evidence": kw["evidence"], "note": note}
    note = f"{_where(top)} ({kt}); " + (f"the reader model also said {model_type}" if agree else said)
    return {"keyword_type": kt, "model_type": model_type, "agree": agree, "evidence": kw["evidence"], "note": note}
