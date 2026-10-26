"""The draft stage (owner decision, 22 Oct 2026, docs/staging/DECISION.md): Vaidyx does the doctor's walk through the staging book (T, then
N, then M, then the stage table) and shows every step with the report line and the book line beside it.

The six guards, in code:
  1. The result is a DRAFT ("Vaidyx draft stage, for the board to confirm"); it counts only after a doctor confirms (confirm(), audited).
  2. The book's tables are fixed rules (rules/*.json, written from the book with their page). The reasoner only picks which report line
     fits a category and quotes it; every quote is checked against the report text (grounding.verify) and an unchecked quote counts as
     nothing. A size category comes from the measured size in code; the stage group is a table lookup in code.
  3. Missing or unclear inputs give "Cannot stage: <what is missing>", never a guess.
  4. A stage written in a report is shown beside the draft; a difference is flagged, nothing is overridden.
  5. A clinician checks each rule file before it is switched on: TB_STAGING = off (default) | preview (labelled, the internal
     instance) | on (only rule files with "signed_off").
  6. No treatment advice: the output is categories, quotes and pages only.

For breast, the prognostic stage group (AJCC 8, pp. 621 to 624: the anatomic draft's T, N and M with grade, HER2, ER and PR) is worked out
beside the anatomic one with the same guards: the table is data in the rule file, the grade and biomarker lines are the values Vaidyx
already verified (checked again word for word), the category is decided in code from the line, anything missing or unclear gives
"cannot stage", a prognostic stage written in a report is shown and flagged, and each draft is confirmed on its own.

Nothing here reads images: imaging REPORTS are read like every other report."""
import json
import os
import re
from pathlib import Path

from .. import grounding, llm, rules, store

RULES_DIR = Path(__file__).resolve().parent / "rules"
PROTOCOL_RULES = {"breast": "breast_ajcc8", "lung_nsclc": "lung_ajcc8", "cervix": "cervix_figo2018"}
DRAFT_LABEL = "Vaidyx draft stage, for the board to confirm"
PREVIEW_LABEL = "Preview: these staging rules are not yet checked by a clinician"
STAGE_FACTS = ("recorded_stage", "figo_stage")


class StagingError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- rule files and the switch -----------------------------------------------------------------------------------------------------

def mode() -> str:
    m = os.getenv("TB_STAGING", "off").strip().lower()
    return m if m in ("off", "preview", "on") else "off"


def rules_for(protocol_id: str | None) -> dict | None:
    rid = PROTOCOL_RULES.get(protocol_id or "")
    if not rid:
        return None
    p = RULES_DIR / f"{rid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def switch(protocol_id: str | None) -> dict:
    """{"on": bool, "preview": bool, "label": str, "why": str}: whether the draft stage is shown for this cancer on this instance."""
    r = rules_for(protocol_id)
    m = mode()
    if not r:
        return {"on": False, "preview": False, "label": "", "why": "No staging rules for this cancer yet"}
    if m == "off":
        return {"on": False, "preview": False, "label": "", "why": "Draft staging is switched off on this server"}
    if m == "on" and not r.get("signed_off"):
        return {"on": False, "preview": False, "label": "", "why": "These staging rules are waiting for a clinician's check"}
    preview = m == "preview" and not r.get("signed_off")
    return {"on": True, "preview": preview, "label": PREVIEW_LABEL if preview else "", "why": ""}


# ---- measurements and table lookups (plain code, guard 2) --------------------------------------------------------------------------

_DIM = re.compile(r"(\d+(?:\.\d+)?)\s*(?:(?:x|×|\*|by)\s*(\d+(?:\.\d+)?)\s*)?(?:(?:x|×|\*|by)\s*(\d+(?:\.\d+)?)\s*)?(mm|cm)\b", re.I)


def size_mm(text: str) -> float | None:
    """The greatest dimension in millimetres of the first measurement in a line ("2.8 × 2.2 cm" -> 28, "18 x 12 mm" -> 18)."""
    m = _DIM.search(str(text or ""))
    if not m:
        return None
    nums = [float(x) for x in m.groups()[:3] if x]
    mm = max(nums) * (10 if m.group(4).lower() == "cm" else 1)
    return round(mm, 2)


def t_by_size(rule: dict, mm: float) -> dict | None:
    """The size category: > min_mm and <= max_mm (T1mi has no lower bound, T3 no upper bound)."""
    for c in rule["T"]:
        if c.get("feature") or ("min_mm" not in c and "max_mm" not in c):
            continue
        lo, hi = c.get("min_mm"), c.get("max_mm")
        if (lo is None or mm > lo) and (hi is None or mm <= hi):
            return c
    return None


def group_of(cat: str, kind: str) -> str:
    """"T1c" -> "T1", "cN2a" -> "N2", "cN1mi" -> "N1mi", "cM0" -> "M0"."""
    c = re.sub(r"^[cpy]+", "", cat or "")
    if kind == "N" and c.startswith("N1mi"):
        return "N1mi"
    m = re.match(r"(T(?:is|X|0|[1-4])|N(?:X|[0-3])|M[01])", c)
    return m.group(1) if m else c


def stage_group(rule: dict, t: str, n: str, m: str) -> dict | None:
    """The row of the stage table for T, N and M, each given as a category or its group ("T2a" matches a row naming "T2a" or "T2";
    "cM1b" a row naming "M1b" or "M1"), or None."""
    t, n, m = (re.sub(r"^c(?=[TNM])", "", x or "") for x in (t, n, m))
    ok = lambda want, x, k: "*" in want or x in want or group_of(x, k) in want
    for row in rule["groups"]["rows"]:
        if ok(row["T"], t, "T") and ok(row["N"], n, "N") and ok(row["M"], m, "M"):
            return row
    return None


def t_rank(rule: dict, cat: str) -> int:
    order = rule.get("t_order") or []
    return order.index(cat) if cat in order else -1


def feature_cat(c: dict, mm: float | None) -> str:
    """The category a described feature gives: its own, an "assign", or by size (lung T2 features: T2a if <= 4 cm or the size is unknown)."""
    if c.get("by_size"):
        for b in c["by_size"]:
            if mm is None:
                return c["by_size"][0]["cat"]
            if (b.get("min_mm") is None or mm > b["min_mm"]) and (b.get("max_mm") is None or mm <= b["max_mm"]):
                return b["cat"]
        return c["by_size"][-1]["cat"]
    return c.get("assign") or c["cat"]


# ---- what the reports say ----------------------------------------------------------------------------------------------------------

def _texts(d) -> list[str]:
    return [p.get("text") or "" for p in d.get("pages") or [] if isinstance(p, dict)]


def evidence_docs(case_id, rule) -> list[dict]:
    """The current, ready reports of the types the inputs read, newest last; final reports first among equals."""
    types = {t for v in rule["inputs"].values() for t in v["doc_types"]}
    out = []
    for d in rules.case_docs(case_id):
        c = d.get("classification") or {}
        if d.get("state") != "ready" or d.get("superseded") or d.get("dismissed") or c.get("doc_type") not in types:
            continue
        out.append(d)
    return out


def written_stages(case_id) -> list[dict]:
    """Every stage a report wrote (the stage as recorded, the FIGO stage as recorded), oldest first: value, quote, report, date, and the
    prefix it carries (c, p, yp)."""
    facts = rules.resolve_facts(rules.case_docs(case_id), (store.get_state(case_id) or {}).get("overrides"))
    out = []
    for fid in STAGE_FACTS:
        for h in (facts.get(fid) or {}).get("history") or []:
            if h.get("verification") not in rules.VERIFIED or not h.get("value"):
                continue
            v = str(h["value"])
            prefix = "yp" if re.search(r"\byp", v, re.I) else "p" if re.search(r"\bp[TN]", v) else "c" if re.search(r"\bc[TN]|\bmr[TN]", v) else ""
            loc = h.get("location") if isinstance(h.get("location"), dict) else {}
            kind = "prognostic" if re.search(r"\bprognostic\b", v + " " + str(h.get("quote") or ""), re.I) else "anatomic"
            out.append({"fact": fid, "value": v, "quote": h.get("quote") or "", "doc_id": h.get("doc_id"), "doc_title": h.get("doc_title"), "date": h.get("date"),
                        "page": loc.get("page"), "prefix": prefix, "superseded": bool(h.get("superseded")), "final": bool(h.get("doc_final")), "kind": kind})
    seen, uniq = set(), []
    for w in sorted(out, key=lambda x: x.get("date") or ""):  # the same words from the same report under two fields: once
        k = (w["doc_id"], re.sub(r"\s+", " ", w["value"]).strip().lower())
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    return uniq


def parse_written(v: str) -> dict:
    """The T, N, M and stage group a written stage names ("cT2 N1 M0, stage IIB" -> T2, N1, M0, IIB); missing parts are None."""
    s = str(v or "")
    t = re.search(r"(?:^|[^A-Za-z])(?:yp|p|c|mr)?(T(?:is|X|0|[1-4])[a-d]?(?:mi)?)", s)
    n = re.search(r"(?:yp|p|c)?(N(?:X|[0-3])[a-c]?(?:mi)?)", s)
    m = re.search(r"(?:p|c)?(M[01])", s)
    g = re.search(r"\bstage\s*(0|IV|I{1,3})\s*([ABC][123]?)?\s*(?:[rp]\b)?", s, re.I) or \
        re.fullmatch(r"\s*(?:FIGO\s*(?:\d{4})?\s*)?(IV|I{1,3})([ABC][123]?)?[rp]?\s*", s)  # a bare stage as written: "IIB", "IIIC1r"
    return {"T": t.group(1) if t else None, "N": n.group(1) if n else None, "M": m.group(1) if m else None,
            "stage": (g.group(1).upper() + (g.group(2) or "").upper()) if g else None}


# ---- the run -----------------------------------------------------------------------------------------------------------------------

SYS = ("You help a doctor stage a cancer for a Tumour Board. You are given the patient's reports and, for each of T, N and M, the list of "
       "criteria from the staging book. For each of T, N and M pick the ONE criterion the reports state, and copy the exact sentence or "
       "phrase from a report that states it (word for word, with its document id). Use only what a report says; never infer, never assume, "
       "never use outside knowledge, never interpret images. If the reports do not state what a criterion needs, answer \"not_stated\" "
       "and say in a few words what is missing. For T, also copy the line with the tumour's measured size when a report gives one. "
       "Do not give a stage group and do not advise treatment.")

SCHEMA = {"type": "object", "properties": {
    k: {"type": "object", "properties": {
        "cat": {"type": "string"},
        "quotes": {"type": "array", "items": {"type": "object", "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["doc_id", "quote"]}},
        "size_quote": {"type": "object", "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string"}}},
        "missing": {"type": "string"}},
        "required": ["cat", "quotes"]} for k in ("T", "N", "M")},
    "required": ["T", "N", "M"]}


def _prompt(case, rule, docs) -> list:
    crit = []
    for k in ("T", "N", "M"):
        lines = "\n".join(f"  {c['cat']}: {c['text']}" for c in rule[k])
        crit.append(f"{k} criteria (what to look for: {rule['inputs'][k]['ask']}):\n{lines}")
    body = []
    for d in docs:
        c = d.get("classification") or {}
        body.append(f"=== document {d['doc_id']}: {c.get('title') or d.get('filename')} ({c.get('doc_type')}, {c.get('status') or 'status not stated'}) ===\n" + "\n".join(_texts(d)))
    return [{"role": "system", "content": SYS},
            {"role": "user", "content": "\n\n".join(crit) + "\n\nREPORTS:\n" + "\n\n".join(body)[:60000] +
             "\n\nReturn JSON {T: {cat, quotes, size_quote, missing}, N: {...}, M: {...}}. cat is one of the listed categories or \"not_stated\"."}]


def _check(q, by_id) -> dict | None:
    """A quote the reasoner gave, checked word for word against its report; None when it is not found."""
    d = by_id.get(str((q or {}).get("doc_id") or ""))
    quote = str((q or {}).get("quote") or "").strip()
    if not d or len(quote) < 3:
        return None
    v = grounding.verify(None, quote, _texts(d))
    if v["status"] != "verified":
        return None
    c = d.get("classification") or {}
    return {"doc_id": d["doc_id"], "doc_title": c.get("title") or d.get("filename"), "doc_type": c.get("doc_type"), "quote": quote, "page": (v.get("location") or {}).get("page"),
            "date": (c.get("event_date_iso") or c.get("report_date_iso") or None), "final": str(c.get("status") or "").upper() in ("FINAL", "AMENDED", "CORRECTED")}


def _crit(rule, k, cat):
    return next((c for c in rule[k] if c["cat"] == cat), None)


def size_fact(case_id, by_id) -> dict | None:
    """The tumour size Vaidyx already read and verified (the lesion_size value, newest final report), as a checked line: the size step's
    fallback when the reasoner gives no size line."""
    facts = rules.resolve_facts(rules.case_docs(case_id), (store.get_state(case_id) or {}).get("overrides"))
    cur = (facts.get("lesion_size") or {}).get("current") or {}
    if cur.get("verification") not in rules.VERIFIED or not cur.get("quote") or cur.get("doc_id") not in by_id:
        return None
    return _check({"doc_id": cur["doc_id"], "quote": cur["quote"]}, by_id)


def decide(rule: dict, answer: dict, by_id: dict, fallback_size: dict | None = None, entered: dict | None = None) -> dict:
    """The draft from the reasoner's picks: every pick needs a checked quote; size categories come from the measured size in code; then
    the stage table. Returns {"components": {T, N, M}, "stage", "row", "status": "staged" | "cannot_stage", "missing": [...]}."""
    comps, missing = {}, []
    # T: the measured size gives a category in code; a described feature (an invasion, a separate nodule, skin or chest wall) needs its own
    # checked line; the higher of the two stands (rank in t_order)
    a = answer.get("T") or {}
    quotes = [x for x in (_check(q, by_id) for q in a.get("quotes") or []) if x]
    size_q = _check(a.get("size_quote"), by_id) or next((q for q in quotes if size_mm(q["quote"]) is not None), None) or fallback_size
    mm = size_mm(size_q["quote"]) if size_q else None
    by_size = t_by_size(rule, mm) if mm is not None else None
    picked = _crit(rule, "T", a.get("cat"))
    feat_quotes = [q for q in quotes if size_q is None or q["quote"] != size_q["quote"]] or quotes
    feat = picked if picked and picked.get("feature") and feat_quotes else None
    if feat:
        fcat = feature_cat(feat, mm)
        if by_size and t_rank(rule, by_size["cat"]) > t_rank(rule, fcat):
            comps["T"] = {"cat": by_size["cat"], "group": by_size["group"], "criterion": by_size, "quotes": [size_q], "size_mm": mm, "how": "the measured size",
                          "note": f"the size gives a higher category than the feature described ({fcat})"}
        else:
            comps["T"] = {"cat": fcat, "group": group_of(fcat, "T"), "criterion": feat, "quotes": feat_quotes + ([size_q] if size_q and size_q not in feat_quotes else []),
                          "how": "the report describes it", **({"size_mm": mm} if mm is not None else {}),
                          **({"note": f"the size alone gives {by_size['cat']}; the feature described gives {fcat}"} if by_size and by_size["cat"] != fcat else {})}
    elif by_size:
        note = "" if not picked or picked["cat"] == by_size["cat"] else f"the measured size decides ({mm:g} mm), not the reading {picked['cat']}"
        comps["T"] = {"cat": by_size["cat"], "group": by_size["group"], "criterion": by_size, "quotes": [size_q], "size_mm": mm, "how": "the measured size", "note": note}
    if "T" not in comps:
        missing.append("T: " + (a.get("missing") or "the tumour size is not stated in a report"))
    # N and M: the pick with its checked quote, or nothing
    for k, what in (("N", "the regional lymph nodes are not described"), ("M", "distant metastases are not described")):
        a = answer.get(k) or {}
        picked = _crit(rule, k, a.get("cat"))
        quotes = [x for x in (_check(q, by_id) for q in a.get("quotes") or []) if x]
        if picked and quotes and not picked.get("rare"):
            comps[k] = {"cat": picked["cat"], "group": picked["group"], "criterion": picked, "quotes": quotes, "how": "the report describes it"}
        else:
            missing.append(f"{k}: " + (a.get("missing") or (what if not picked else f"no report line found for {picked['cat']}")))
    # a part no report states, filled in by the treating doctor with a reason (shown "entered by Dr X, no report"; AJCC allows cM0
    # without imaging, p. 620): it fills a gap only, never replaces a part a report states
    for k, e in (entered or {}).items():
        c = _crit(rule, k, (e or {}).get("cat"))
        if k in ("T", "N", "M") and k not in comps and c:
            comps[k] = {"cat": c["cat"], "group": c.get("group") or group_of(c["cat"], k), "criterion": c, "quotes": [], "how": "entered by the doctor",
                        "entered": {"by": e.get("by"), "by_name": e.get("by_name"), "at": e.get("at"), "reason": e.get("reason")}}
            missing = [m for m in missing if not m.startswith(f"{k}:")]
    out = {"components": comps, "missing": missing}
    if missing:
        return {**out, "status": "cannot_stage", "stage": None, "row": None}
    row = stage_group(rule, comps["T"]["cat"], comps["N"]["cat"], comps["M"]["cat"])
    if not row:
        return {**out, "status": "cannot_stage", "stage": None, "row": None, "missing": ["The stage table has no row for this combination"]}
    stage = row["stage"]
    if stage in (rule["groups"].get("suffix_for") or []):  # FIGO: r when imaging allots Stage IIIC, p when pathology does (note d)
        q = (comps["N"].get("quotes") or [None])[0]
        if q:
            stage += "p" if q.get("doc_type") in ("histopathology", "cytology") else "r"
    return {**out, "status": "staged", "stage": stage, "row": row}


def compare(draft: dict, written: list[dict]) -> dict | None:
    """The newest clinical (or unprefixed) stage a report wrote against the draft: "matches", "differs" (what differs) or "partial"."""
    written = [w for w in written if w.get("kind") != "prognostic"]  # a prognostic stage is compared with the prognostic draft
    pool = [w for w in written if not w["superseded"] and w["prefix"] in ("", "c")] or [w for w in written if not w["superseded"]]
    if not pool or draft.get("status") != "staged":
        return None
    w = pool[-1]
    p = parse_written(w["value"])
    comps = draft["components"]
    mine = {"T": comps["T"]["group"], "N": group_of(comps["N"]["cat"], "N"), "M": comps["M"]["group"], "stage": re.sub(r"[rp]$", "", draft["stage"] or "")}
    diffs = []
    for k in ("T", "N", "M", "stage"):
        if p.get(k) is None:
            continue
        theirs = group_of(p[k], k) if k != "stage" else p[k]
        if theirs != mine[k]:
            diffs.append(f"{'Stage' if k == 'stage' else k}: the report writes {p[k]}, the draft {mine[k]}")
    named = [k for k in ("T", "N", "M", "stage") if p.get(k)]
    return {"written": w, "result": "differs" if diffs else "matches" if named else "partial", "differences": diffs}


# ---- the prognostic stage group (AJCC 8 breast, pp. 621 to 624; night-v3 item 1.12) ---------------------------------------------------
# The same six guards. The table is data ("groups_prognostic" in the rule file, every row with its page). Grade, HER2, ER and PR come from
# the values Vaidyx already read and verified (the grade, her2, er and pr facts); each quote is checked again word for word (_check) and
# the category is decided here in code from the quoted line. Anything missing or unclear gives "cannot stage"; a row marked "unsure" in
# the rule file needs a clinician's check and is never used; the Oncotype Dx row needs a recurrence score Vaidyx never has and is never
# applied.

PROGNOSTIC_PARTS = ("G", "HER2", "ER", "PR")
_PENDING = re.compile(r"\b(?:pending|awaited|sent\s+(?:out|for)|to\s+follow|not\s+(?:done|performed|available|reported))\b", re.I)
_CONTROLS = re.compile(r"\b(?:external|internal)?\s*(?:positive|negative)\s+controls?\b", re.I)
_MARK = re.compile(r"(?P<HER2>(?i:\bHER[\s-]?2(?:/neu)?\b|\bc-?erb\s?B-?2\b))|(?P<ER>\bER\b|(?i:\b(?:o?estrogen)\b))|"
                   r"(?P<PR>\bPR\b|\bPgR\b|(?i:\bprogesterone\b))|(?P<KI>(?i:\bKi[\s-]?67\b))")
_POS = re.compile(r"\bpositive\b|\+\s*ve\b|\(\s*\+\s*\)", re.I)
_NEG = re.compile(r"\bnegative\b|(?<!\+)-\s*ve\b|\(\s*-\s*\)", re.I)
_ISH = re.compile(r"\b(?:F|C|S|DD)?ISH\b|in[\s-]situ\s+hybridi[sz]ation", re.I)
_GRADE = re.compile(r"(?:(?i:\bgrade\b)\s*(?:(?i:is)\s*)?[:\-]?\s*|\bG(?=[123]\b))(III|II|I|[123])(?![\w])(\s*(?:[-/–]|to|or|and)\s*(?:III|II|I|[123])(?![\w]))?")
_ROMAN = {"I": "1", "II": "2", "III": "3"}


def _segment(text: str, kind: str) -> str:
    """The part of a line about one marker ("ER: positive (90%), PR: negative" -> "PR: negative" for PR); the whole line when it names
    no marker (a fact's quote can be the result alone)."""
    s = str(text or "")
    marks = [(m.start(), m.lastgroup) for m in _MARK.finditer(s)]
    mine = [i for i, (_, k) in enumerate(marks) if k == kind]
    if not mine:
        return s if not marks else ""
    i = mine[0]
    end = next((p for p, k in marks[i + 1:] if k != kind), len(s))
    return s[marks[i][0]:end]


def grade_cat(text) -> tuple:
    """("G1" | "G2" | "G3" | None, why): the histologic grade a line writes ("Grade 2", "grade II", "G3", "MBR grade: 2"). GX, a range
    ("grade II-III"), two different grades, words alone ("moderately differentiated") or a nuclear grade alone are unclear (None)."""
    s = str(text or "")
    if re.search(r"\bGX\b|grade\s+cannot\s+be\s+assessed", s, re.I):
        return None, "the grade cannot be assessed (GX)"
    if _PENDING.search(s):
        return None, "the grade is not yet reported"
    s = re.sub(r"(?i:nuclear)\s+(?i:grade)\s*[:\-]?\s*(?:III|II|I|[123])(?![\w])", " ", s)
    found = set()
    for m in _GRADE.finditer(s):
        if m.group(2):
            return None, "the line gives a range of grades"
        found.add(_ROMAN.get(m.group(1).upper(), m.group(1)))
    if len(found) > 1:
        return None, "the line gives more than one grade"
    if not found:
        return None, "the line does not state grade 1, 2 or 3"
    return f"G{found.pop()}", ""


def receptor_cat(text, kind: str) -> tuple:
    """("positive" | "negative" | None, why) for ER or PR: the words of the line ("positive", "+ve", "negative", "-ve"); a percentage or
    a score alone, a pending result or both words are unclear (None)."""
    seg = _segment(text, kind)
    if not seg:
        return None, f"the line is not about {kind}"
    if _PENDING.search(seg):
        return None, "the result is not yet reported"
    seg = _CONTROLS.sub(" ", seg)
    p, n = bool(_POS.search(seg)), bool(_NEG.search(seg))
    if p and not n:
        return "positive", ""
    if n and not p:
        return "negative", ""
    return None, "the line says both positive and negative" if p and n else "the line does not say positive or negative"


def her2_cat(text) -> tuple:
    """("positive" | "negative" | "negative_ish_equivocal" | None, why): an ISH result decides when the line gives one ("amplified",
    "not amplified"; "equivocal" by ISH counts as negative, the table's footnote *, p. 624); otherwise IHC 3+ is positive and 0 or 1+
    negative (p. 616) or the words positive / negative. IHC 2+ (equivocal) without an ISH result, a pending test or words that disagree
    are unclear (None)."""
    seg = _segment(text, "HER2")
    if not seg:
        return None, "the line is not about HER2"
    if _PENDING.search(seg):
        return None, "the result is not yet reported"
    seg = _CONTROLS.sub(" ", seg)
    ish = _ISH.search(seg)
    if ish:
        tail = seg[ish.start():]
        if re.search(r"\bnot\s+amplified\b|\bnon[\s-]?amplified\b|\bno\s+amplification\b|\bwithout\s+amplification\b", seg, re.I):
            return "negative", "ISH: not amplified"
        if re.search(r"\bamplified\b", seg, re.I):
            return "positive", "ISH: amplified"
        if re.search(r"\bequivocal\b", tail, re.I) or re.search(r"\bequivocal\s+(?:by|on|in)\s+(?:\w+\s+)?(?:F|C|S|DD)?ISH\b", seg, re.I):
            return "negative_ish_equivocal", "ISH: equivocal, counted as negative (footnote *)"
        p, n = bool(_POS.search(tail)), bool(_NEG.search(tail))
        if p != n:
            return ("positive" if p else "negative"), "ISH result"
        return None, "an ISH test is named but the line gives no clear ISH result"
    scores = set(re.findall(r"(?<![\d.])([0-3])\s*\+", seg)) | ({"0"} if re.search(r"(?:\bscore|\bIHC|\bHER[\s-]?2(?:/neu)?)\s*[:\-]?\s*0(?![\d.%+])", seg, re.I) else set())
    if "2" in scores or re.search(r"\bequivocal\b", seg, re.I):
        return None, "IHC 2+ (equivocal) with no ISH result in the line"
    p, n = bool(_POS.search(seg)), bool(_NEG.search(seg))
    by_score = "positive" if scores == {"3"} else "negative" if scores and scores <= {"0", "1"} else None
    if len(scores) > 1 and by_score is None:
        return None, "the line gives more than one IHC score"
    words = "positive" if p and not n else "negative" if n and not p else None
    if p and n:
        return None, "the line says both positive and negative"
    if by_score and words and by_score != words:
        return None, "the IHC score and the words disagree"
    cat = by_score or words
    if not cat:
        return None, "the line does not give the HER2 status"
    return cat, ("IHC 3+" if by_score == "positive" else "IHC 0 or 1+" if by_score == "negative" else "")


_CATS = {"G": grade_cat, "HER2": her2_cat, "ER": lambda t: receptor_cat(t, "ER"), "PR": lambda t: receptor_cat(t, "PR")}


def prognostic_docs(case_id, rule) -> dict:
    """The current, ready reports of the types the grade and biomarker facts come from, by id."""
    types = {t for v in rule["groups_prognostic"]["inputs"].values() for t in v["doc_types"]}
    return {d["doc_id"]: d for d in rules.case_docs(case_id) if d.get("state") == "ready" and not d.get("superseded") and not d.get("dismissed")
            and (d.get("classification") or {}).get("doc_type") in types}


def prognostic_inputs(rule, facts: dict, by_id: dict) -> dict:
    """For each of G, HER2, ER, PR: {"cat", "value", "quotes", "how", "criterion"} from the verified fact, or {"missing": why}."""
    gp = rule["groups_prognostic"]
    out = {}
    for k in PROGNOSTIC_PARTS:
        spec = gp["inputs"][k]
        cur = next(((facts.get(f) or {}).get("current") for f in spec["facts"] if (facts.get(f) or {}).get("current")), None) or {}
        if not cur or not cur.get("value"):
            out[k] = {"missing": f"{spec['what']} is not in a report"}
            continue
        if cur.get("verification") not in rules.VERIFIED or not cur.get("quote") or cur.get("doc_id") not in by_id:
            out[k] = {"missing": f"{spec['what']} is not verified against its report"}
            continue
        q = _check({"doc_id": cur["doc_id"], "quote": cur["quote"]}, by_id)
        if not q:
            out[k] = {"missing": f"the line for {spec['what']} is not found word for word in its report"}
            continue
        cat, why = _CATS[k](q["quote"])
        how = "the report line"
        if cat is None and k in ("ER", "PR"):  # the value as read carries the category ("Positive") when the line gives only a number
            vcat, _ = receptor_cat(cur.get("value"), k)
            if vcat:
                cat, how = vcat, "the value as read from this line"
        if cat is None:
            out[k] = {"missing": f"unclear: {why} (\"{q['quote']}\")", "quotes": [q]}
            continue
        crit = next((c for c in gp["criteria"][k] if c["cat"] == cat), None)
        if k == "HER2" and why.startswith("IHC") and cat in ("positive", "negative"):
            crit = next((c for c in gp["criteria"]["HER2"] if c.get("assign") == cat and c["cat"].startswith("ihc_")), crit)
        if k == "HER2" and cat == "negative_ish_equivocal":
            cat = "negative"
        out[k] = {"cat": cat, "value": cur.get("value"), "quotes": [q], "how": how + (f" ({why})" if why else ""), "criterion": crit}
    return out


def prognostic_group(rule: dict, t: str, n: str, m: str, g, her2: str, er: str, pr: str) -> dict | None:
    """The row of the prognostic table for T, N, M (categories or groups, as the anatomic draft gives them), the grade (1, 2, 3 or "G2")
    and the HER2, ER and PR status ("positive" / "negative"), or None. Rows needing a recurrence score are never used."""
    t, n, m = (re.sub(r"^c(?=[TNM])", "", x or "") for x in (t, n, m))
    g = int(str(g).lstrip("Gg")) if str(g or "").lstrip("Gg") in ("1", "2", "3") else None
    ok = lambda want, x, k: "*" in want or x in want or group_of(x, k) in want
    st = lambda want, x: want == "any" or want == x
    for row in rule["groups_prognostic"]["rows"]:
        if row.get("requires"):
            continue
        if ok(row["T"], t, "T") and ok(row["N"], n, "N") and ok(row["M"], m, "M") and g in row["G"] and \
                st(row["HER2"], her2) and st(row["ER"], er) and st(row["PR"], pr):
            return row
    return None


def decide_prognostic(rule: dict, anatomic: dict, inputs: dict) -> dict:
    """The prognostic draft beside the anatomic one, the same shape: {"components": {G, HER2, ER, PR}, "tnm", "stage", "row", "status",
    "missing", "label", "multigene"}."""
    gp = rule["groups_prognostic"]
    comps = {k: v for k, v in inputs.items() if v.get("cat")}
    missing = [f"{k}: {v['missing']}" for k, v in inputs.items() if not v.get("cat")]
    ac = (anatomic or {}).get("components") or {}
    tnm = {k: ac[k]["cat"] for k in ("T", "N", "M") if k in ac}
    if (anatomic or {}).get("status") != "staged":
        missing.insert(0, "T, N and M: the anatomic draft cannot stage yet")
    out = {"label": gp.get("label"), "components": comps, "tnm": tnm, "missing": missing, "stage": None, "row": None, "status": "cannot_stage",
           "multigene": {"applied": False, "note": gp.get("multigene_note")}, "confirmed": None, "rejected": None}
    if missing:
        return out
    g = comps["G"]["cat"]
    row = prognostic_group(rule, tnm["T"], tnm["N"], tnm["M"], g, comps["HER2"]["cat"], comps["ER"]["cat"], comps["PR"]["cat"])
    if not row:
        return {**out, "missing": ["The prognostic table as printed has no row for this combination"]}
    if row.get("unsure"):
        return {**out, "missing": ["The table row needs a clinician's check"], "row": row}
    return {**out, "status": "staged", "stage": row["stage"], "row": row}


_PROG_WRITTEN = re.compile(r"prognostic\s+stage(?:\s+group)?\s*(?:(?i:is)\s*)?[:\-=]?\s*(?:(?i:stage)\s*)?(0|IV|III|II|I)([ABC])?(?![a-z])", re.I)


def parse_prognostic(v: str) -> str | None:
    """The stage a "prognostic stage" line writes ("AJCC prognostic stage group: IB" -> IB), or None."""
    m = _PROG_WRITTEN.search(str(v or ""))
    return (m.group(1).upper() + (m.group(2) or "").upper()) if m else None


def written_prognostic(case_id, written: list[dict]) -> list[dict]:
    """Every prognostic stage a report wrote, oldest first: the stages as recorded that say "prognostic", and any report line with the
    words "prognostic stage" and a stage (the line checked word for word against its report like every quote)."""
    out = [{**w, "stage": parse_prognostic(w["value"]) or parse_prognostic(w["quote"])} for w in written if w.get("kind") == "prognostic"]
    seen = {(w["doc_id"], w["stage"]) for w in out}
    for d in rules.case_docs(case_id):
        if d.get("state") != "ready" or d.get("superseded") or d.get("dismissed"):
            continue
        for text in _texts(d):
            for line in str(text).splitlines():
                stage = parse_prognostic(line)
                if not stage or (d["doc_id"], stage) in seen:
                    continue
                q = _check({"doc_id": d["doc_id"], "quote": line.strip()}, {d["doc_id"]: d})
                if q:
                    seen.add((d["doc_id"], stage))
                    out.append({"fact": None, "value": line.strip(), "quote": q["quote"], "doc_id": d["doc_id"], "doc_title": q["doc_title"], "date": q["date"],
                                "page": q["page"], "prefix": "", "superseded": False, "final": q["final"], "kind": "prognostic", "stage": stage})
    return sorted([w for w in out if w["stage"]], key=lambda x: x.get("date") or "")


def compare_prognostic(draft: dict | None, written: list[dict]) -> dict | None:
    """The newest prognostic stage a report wrote against the prognostic draft: "matches" or "differs"; shown, never overridden."""
    pool = [w for w in written if not w.get("superseded")]
    if not pool or not draft or draft.get("status") != "staged":
        return None
    w = pool[-1]
    diffs = [] if w["stage"] == draft["stage"] else [f"Prognostic stage: the report writes {w['stage']}, the draft {draft['stage']}"]
    return {"written": w, "result": "differs" if diffs else "matches", "differences": diffs}


def prognostic_for(case_id, rule, anatomic) -> dict | None:
    """The prognostic draft for this Case File (no model call: the grade and biomarker values Vaidyx already verified), or None when the
    rule file has no prognostic table."""
    if not (rule or {}).get("groups_prognostic"):
        return None
    by_id = prognostic_docs(case_id, rule)
    facts = rules.resolve_facts(rules.case_docs(case_id), (store.get_state(case_id) or {}).get("overrides"))
    return decide_prognostic(rule, anatomic, prognostic_inputs(rule, facts, by_id))


async def run(case_id, user) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise StagingError("Case File not found.", 404)
    sw = switch(case.get("protocol"))
    if not sw["on"]:
        raise StagingError(sw["why"], 409)
    rule = rules_for(case.get("protocol"))
    docs = evidence_docs(case_id, rule)
    if not docs:
        raise StagingError("No imaging report or clinical note is in the Case File yet: nothing to stage from.", 409)
    st = store.get_state(case_id)
    sig = rules.case_signature(case_id, st)
    au = store.auditor(case_id)
    answer = await llm.chat("reasoner", _prompt(case, rule, docs), json_schema=SCHEMA, max_tokens=1600, purpose="draft stage", audit=au)
    by_id = {d["doc_id"]: d for d in docs}
    answer = answer if isinstance(answer, dict) else {}
    st = store.get_state(case_id)
    entered = st.get("staging_entered") if isinstance(st.get("staging_entered"), dict) else {}
    draft = decide(rule, answer, by_id, size_fact(case_id, by_id), entered)
    rec = {**draft, "rules": rule["id"], "system": rule["system"], "at": store.now_iso(), "by": user, "signature": sig.get("hash"),
           "model": (llm_model_label()), "confirmed": None, "rejected": None, "answer": answer}
    prog = prognostic_for(case_id, rule, draft)
    if prog is not None:
        rec["prognostic"] = prog
    st["staging"] = rec
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage", "by": user, "status": draft["status"], "stage": draft.get("stage"),
                          "components": {k: v["cat"] for k, v in draft["components"].items()}, "rules": rule["id"],
                          **({"prognostic": {"status": prog["status"], "stage": prog["stage"], "components": {k: v["cat"] for k, v in prog["components"].items()}}} if prog else {})})
    return view(case_id)


def llm_model_label() -> str:
    try:
        from .. import config
        return str((config.models().get("reasoner") or {}).get("model") or "")
    except Exception:
        return ""


def view(case_id) -> dict:
    """What the Staging card shows: the switch, the draft (stale when the reports changed since), the written stages and their history,
    the comparison, the book."""
    case = store.get_case(case_id)
    if not case:
        raise StagingError("Case File not found.", 404)
    sw = switch(case.get("protocol"))
    rule = rules_for(case.get("protocol"))
    written = written_stages(case_id)
    from . import book as _book
    out = {"switch": sw, "draft_label": DRAFT_LABEL, "written": written, "draft": None, "comparison": None, "stale": False,
           "book": (rule or {}).get("book"), "book_here": bool(rule and (rule.get("book") or {}).get("id") in _book.books()),
           "notation": (rule or {}).get("notation") or "tnm", "system": (rule or {}).get("system"), "label": (rule or {}).get("label"),
           "groups_note": ((rule or {}).get("groups") or {}).get("note"), "groups_ref": {k: ((rule or {}).get("groups") or {}).get(k) for k in ("title", "page", "find")} if rule else None,
           "criteria": {k: [{"cat": c["cat"], "text": c["text"]} for c in rule[k] if not c.get("rare")] for k in ("T", "N", "M")} if rule and sw["on"] else None,
           "prognostic": None, "prognostic_written": [], "prognostic_comparison": None, "prognostic_ref": None}
    if not sw["on"]:
        return out
    gp = rule.get("groups_prognostic")
    if gp:
        out["prognostic_ref"] = {k: gp.get(k) for k in ("title", "page", "find", "label", "note", "footnotes", "multigene_note")}
        out["prognostic_written"] = written_prognostic(case_id, written)
    st = store.get_state(case_id)
    d = st.get("staging")
    if isinstance(d, dict) and d.get("rules") == rule["id"]:
        sig = rules.case_signature(case_id, st)
        out["draft"] = {k: v for k, v in d.items() if k != "prognostic"}
        out["stale"] = bool(d.get("signature") and d["signature"] != sig.get("hash"))
        out["comparison"] = compare(d, written)
        if gp and isinstance(d.get("prognostic"), dict):
            out["prognostic"] = d["prognostic"]
            out["prognostic_comparison"] = compare_prognostic(d["prognostic"], out["prognostic_written"])
    return out


def enter(case_id, user, part, cat, reason) -> dict:
    """The treating doctor fills a part no report states (T, N or M), with a reason; the draft is worked out again from the same reading
    of the reports (no new model call). An empty category takes the entry back."""
    case = store.get_case(case_id)
    rule = rules_for((case or {}).get("protocol"))
    if not case or not rule:
        raise StagingError("No staging rules for this Case File.", 409)
    if part not in ("T", "N", "M"):
        raise StagingError("Choose T, N or M.", 400)
    st = store.get_state(case_id)
    ent = st.get("staging_entered") if isinstance(st.get("staging_entered"), dict) else {}
    if not cat:
        ent.pop(part, None)
    else:
        if not _crit(rule, part, cat):
            raise StagingError(f"{cat} is not a {part} category of {rule['system']}.", 400)
        reason = " ".join(str(reason or "").split())[:500]
        if len(reason) < 3:
            raise StagingError("Say on what you base it (for example: clinical examination, no symptoms): it is recorded with your name.", 400)
        from ..slots import display_name
        ent[part] = {"cat": cat, "reason": reason, "by": user, "by_name": display_name(user), "at": store.now_iso()}
    st["staging_entered"] = ent
    d = st.get("staging")
    if isinstance(d, dict) and d.get("rules") == rule["id"] and isinstance(d.get("answer"), dict):  # an older draft without its reading: work it out again
        by_id = {x["doc_id"]: x for x in evidence_docs(case_id, rule)}
        again = decide(rule, d.get("answer") or {}, by_id, size_fact(case_id, by_id), ent)
        d.update({**again, "confirmed": None, "rejected": None})
        prog = prognostic_for(case_id, rule, again)
        if prog is not None:
            d["prognostic"] = prog
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_part_entered", "by": user, "part": part, "cat": cat or None, "reason": (ent.get(part) or {}).get("reason")})
    return view(case_id)


DRAFTS = ("anatomic", "prognostic")


def _which(which) -> str:
    w = str(which or "anatomic").strip().lower()
    if w not in DRAFTS:
        raise StagingError("Say which draft: anatomic or prognostic.", 400)
    return w


def _target(d, w):
    """The anatomic draft itself, or the prognostic draft stored inside it."""
    if not isinstance(d, dict):
        return None
    return d if w == "anatomic" else (d.get("prognostic") if isinstance(d.get("prognostic"), dict) else None)


def confirm(case_id, user, note="", which="anatomic") -> dict:
    """A doctor confirms one draft (anatomic by default, or the prognostic stage group); audited with which draft it was."""
    w = _which(which)
    st = store.get_state(case_id)
    d = st.get("staging")
    x = _target(d, w)
    if not x or x.get("status") != "staged":
        raise StagingError("There is no draft stage to confirm." if w == "anatomic" else "There is no prognostic stage group to confirm.", 409)
    if d.get("signature") != rules.case_signature(case_id, st).get("hash"):
        raise StagingError("The reports changed after this draft was worked out: work it out again first.", 409)
    from ..slots import display_name
    x["confirmed"] = {"by": user, "by_name": display_name(user), "at": store.now_iso(), "note": " ".join(str(note or "").split())[:500], "which": w}
    x["rejected"] = None
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_confirmed", "which": w, "by": user, "stage": x.get("stage"), "components": {k: v["cat"] for k, v in x["components"].items()},
                          **({"tnm": x.get("tnm")} if w == "prognostic" else {})})
    return view(case_id)


def reject(case_id, user, reason, which="anatomic") -> dict:
    w = _which(which)
    reason = " ".join(str(reason or "").split())[:500]
    if len(reason) < 3:
        raise StagingError("Say what is wrong: it is recorded with your name.", 400)
    st = store.get_state(case_id)
    x = _target(st.get("staging"), w)
    if not x:
        raise StagingError("There is no draft stage." if w == "anatomic" else "There is no prognostic stage group.", 409)
    from ..slots import display_name
    x["rejected"] = {"by": user, "by_name": display_name(user), "at": store.now_iso(), "reason": reason, "which": w}
    x["confirmed"] = None
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_rejected", "which": w, "by": user, "reason": reason, "stage": x.get("stage")})
    return view(case_id)
