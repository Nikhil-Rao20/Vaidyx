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

Nothing here reads images: imaging REPORTS are read like every other report."""
import json
import os
import re
from pathlib import Path

from .. import grounding, llm, rules, store

RULES_DIR = Path(__file__).resolve().parent / "rules"
PROTOCOL_RULES = {"breast": "breast_ajcc8"}  # lung and cervix follow the same shape
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
    """The row of the stage table for the T, N and M groups, or None."""
    for row in rule["groups"]["rows"]:
        if ("*" in row["T"] or t in row["T"]) and ("*" in row["N"] or n in row["N"]) and ("*" in row["M"] or m in row["M"]):
            return row
    return None


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
            out.append({"fact": fid, "value": v, "quote": h.get("quote") or "", "doc_id": h.get("doc_id"), "doc_title": h.get("doc_title"), "date": h.get("date"),
                        "page": loc.get("page"), "prefix": prefix, "superseded": bool(h.get("superseded")), "final": bool(h.get("doc_final"))})
    out.sort(key=lambda x: x.get("date") or "")
    return out


def parse_written(v: str) -> dict:
    """The T, N, M and stage group a written stage names ("cT2 N1 M0, stage IIB" -> T2, N1, M0, IIB); missing parts are None."""
    s = str(v or "")
    t = re.search(r"(?:^|[^A-Za-z])(?:yp|p|c|mr)?(T(?:is|X|0|[1-4])[a-d]?(?:mi)?)", s)
    n = re.search(r"(?:yp|p|c)?(N(?:X|[0-3])[a-c]?(?:mi)?)", s)
    m = re.search(r"(?:p|c)?(M[01])", s)
    g = re.search(r"\bstage\s*(0|I{1,3}V?|IV)\s*([ABC])?\b", s, re.I)
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
    return {"doc_id": d["doc_id"], "doc_title": c.get("title") or d.get("filename"), "quote": quote, "page": (v.get("location") or {}).get("page"),
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
    # T: a direct extension (T4) needs its own quoted line; otherwise the measured size decides
    a = answer.get("T") or {}
    quotes = [x for x in (_check(q, by_id) for q in a.get("quotes") or []) if x]
    size_q = _check(a.get("size_quote"), by_id) or next((q for q in quotes if size_mm(q["quote"]) is not None), None) or fallback_size
    picked = _crit(rule, "T", a.get("cat"))
    if picked and picked.get("feature") and quotes:
        comps["T"] = {"cat": picked["cat"], "group": picked["group"], "criterion": picked, "quotes": quotes, "how": "the report describes it"}
    elif size_q and size_mm(size_q["quote"]) is not None:
        mm = size_mm(size_q["quote"])
        c = t_by_size(rule, mm)
        if c:
            note = "" if not picked or picked["cat"] == c["cat"] else f"the measured size decides ({mm:g} mm), not the reading {picked['cat']}"
            comps["T"] = {"cat": c["cat"], "group": c["group"], "criterion": c, "quotes": [size_q], "size_mm": mm, "how": "the measured size", "note": note}
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
    row = stage_group(rule, comps["T"]["group"], group_of(comps["N"]["cat"], "N"), comps["M"]["group"])
    if not row:
        return {**out, "status": "cannot_stage", "stage": None, "row": None, "missing": ["The stage table has no row for this combination"]}
    return {**out, "status": "staged", "stage": row["stage"], "row": row}


def compare(draft: dict, written: list[dict]) -> dict | None:
    """The newest clinical (or unprefixed) stage a report wrote against the draft: "matches", "differs" (what differs) or "partial"."""
    pool = [w for w in written if not w["superseded"] and w["prefix"] in ("", "c")] or [w for w in written if not w["superseded"]]
    if not pool or draft.get("status") != "staged":
        return None
    w = pool[-1]
    p = parse_written(w["value"])
    comps = draft["components"]
    mine = {"T": comps["T"]["group"], "N": group_of(comps["N"]["cat"], "N"), "M": comps["M"]["group"], "stage": draft["stage"]}
    diffs = []
    for k in ("T", "N", "M", "stage"):
        if p.get(k) is None:
            continue
        theirs = group_of(p[k], k) if k != "stage" else p[k]
        if theirs != mine[k]:
            diffs.append(f"{'Stage' if k == 'stage' else k}: the report writes {p[k]}, the draft {mine[k]}")
    named = [k for k in ("T", "N", "M", "stage") if p.get(k)]
    return {"written": w, "result": "differs" if diffs else "matches" if named else "partial", "differences": diffs}


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
    st["staging"] = rec
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage", "by": user, "status": draft["status"], "stage": draft.get("stage"),
                          "components": {k: v["cat"] for k, v in draft["components"].items()}, "rules": rule["id"]})
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
    out = {"switch": sw, "draft_label": DRAFT_LABEL, "written": written, "draft": None, "comparison": None, "stale": False,
           "book": (rule or {}).get("book"), "system": (rule or {}).get("system"), "label": (rule or {}).get("label"),
           "groups_note": ((rule or {}).get("groups") or {}).get("note"), "groups_ref": {k: ((rule or {}).get("groups") or {}).get(k) for k in ("title", "page", "find")} if rule else None,
           "criteria": {k: [{"cat": c["cat"], "text": c["text"]} for c in rule[k] if not c.get("rare")] for k in ("T", "N", "M")} if rule and sw["on"] else None}
    if not sw["on"]:
        return out
    st = store.get_state(case_id)
    d = st.get("staging")
    if isinstance(d, dict) and d.get("rules") == rule["id"]:
        sig = rules.case_signature(case_id, st)
        out["draft"] = d
        out["stale"] = bool(d.get("signature") and d["signature"] != sig.get("hash"))
        out["comparison"] = compare(d, written)
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
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_part_entered", "by": user, "part": part, "cat": cat or None, "reason": (ent.get(part) or {}).get("reason")})
    return view(case_id)


def confirm(case_id, user, note="") -> dict:
    st = store.get_state(case_id)
    d = st.get("staging")
    if not isinstance(d, dict) or d.get("status") != "staged":
        raise StagingError("There is no draft stage to confirm.", 409)
    if d.get("signature") != rules.case_signature(case_id, st).get("hash"):
        raise StagingError("The reports changed after this draft was worked out: work it out again first.", 409)
    from ..slots import display_name
    d["confirmed"] = {"by": user, "by_name": display_name(user), "at": store.now_iso(), "note": " ".join(str(note or "").split())[:500]}
    d["rejected"] = None
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_confirmed", "by": user, "stage": d.get("stage"), "components": {k: v["cat"] for k, v in d["components"].items()}})
    return view(case_id)


def reject(case_id, user, reason) -> dict:
    reason = " ".join(str(reason or "").split())[:500]
    if len(reason) < 3:
        raise StagingError("Say what is wrong: it is recorded with your name.", 400)
    st = store.get_state(case_id)
    d = st.get("staging")
    if not isinstance(d, dict):
        raise StagingError("There is no draft stage.", 409)
    from ..slots import display_name
    d["rejected"] = {"by": user, "by_name": display_name(user), "at": store.now_iso(), "reason": reason}
    d["confirmed"] = None
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "draft_stage_rejected", "by": user, "reason": reason, "stage": d.get("stage")})
    return view(case_id)
