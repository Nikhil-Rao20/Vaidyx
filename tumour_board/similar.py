"""Similar Case Files (night-v3 Phase 7): past Case Files of this hospital like the one open, listed in order with quoted reasons.

Owner decision (27 Oct 2026, docs/night-v3/PLAN.md section 2): similar Case Files of this hospital may be listed in order with quoted
"why similar" lines, no numeric score, labelled "Past Case File, not advice for this patient", opened read-only through a doctor
break-glass with a reason. Design: docs/night-v3/research/07_similar_cases.md section 4, contract in its section 8.

Part 1 (item 7.1, this part): the Case profile index.
- A profile per eligible Case File (listed, not archived, never protected, with a recorded board decision), built by code only from the
  verified facts (each with its verbatim quote), the stage as recorded, confirmed or agreed (never computed), the board records and the
  Case summary's "since the board" sentences. No identifier is kept: every text goes through `scrub` (the file's own identifiers and
  name words, long numbers and day-level dates become "[id]" / "[date]").
- The index: profiles/<case_id>.json, index.json (the chunks) and index.npz (normalised vectors), under config.DATA_ROOT / "similar".
  `ensure()` compares a signature per file and rebuilds only what changed; it runs before every search and in the scheduler job.
- The candidates: the same cancer group only, BM25 plus dense vectors fused by Reciprocal Rank Fusion as search.CaseIndex.search does.
  Ranks stay internal (item 7.2 orders with the reasoner and never shows a number).

The real case: every entry refuses a protected id, and the scan skips its directory by name before anything in it is opened."""
import hashlib
import json
import logging
import math
import os
import re
import threading
from collections import Counter
from datetime import date

import numpy as np

from . import access, config, dates, decision_record, identity, protocol, published, rules, store
from . import search as retrieval  # the published-cases search module: its embedder, tokenizer and model name (the public `search` below is ours)
from . import case_summary

log = logging.getLogger(__name__)

VERSION = 1  # the profile schema
LABEL = "Past Case File, not advice for this patient"
GROUPS = {"colorectal_colon": "colorectal", "colorectal_rectum": "colorectal"}  # protocol id -> cancer group (others: their own id)
GROUP_LABELS = {"colorectal": "Colorectal cancer"}
NAME_PREFIX = "name:"
CHUNK_CHARS = 1500
MAX_LINES = 40
EMBED_BATCH = 64
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # as search.CaseIndex.search
RRF_K = 60
TOP_N = 20
FEW = 3
WORDS_MAX = 200

HISTOLOGY = ("histologic_type", "grade")
BIOMARKERS = ("er", "pr", "her2", "ki67", "pdl1", "egfr", "alk", "ros1", "kras", "mmr", "ras_braf", "cea")
STAGE_FACTS = ("recorded_stage", "figo_stage")
TREATMENTS = ("treatment_received", "treatment_completion_date")
OTHER = ("lesion_size", "nodal_findings", "distant_findings", "ecog", "menopausal_status", "smoking_history", "tobacco_use", "lvi", "margins",
         "ene", "pni", "depth_of_invasion")
DECISION_FIELDS = ("decision_text", "intent", "modalities", "sequence", "rationale")

NO_GROUP = "No cancer group on this file."
NO_RECORDS_AFTER = "No records after the board decision yet"
NO_DECISION_YET = "No board decision recorded yet"

_lock = threading.Lock()  # one ensure / forget at a time (the whole index is rewritten)
_loaded: dict = {"key": None, "meta": None, "matrix": None}


# ---- paths (computed at call time: tests move config.DATA_ROOT) -----------------------------------------------------------------

def DIR():
    return config.DATA_ROOT / "similar"


def _profiles_dir():
    return DIR() / "profiles"


def _profile_path(case_id):
    return _profiles_dir() / f"{store.safe_id(case_id)}.json"


def _index_json():
    return DIR() / "index.json"


def _index_npz():
    return DIR() / "index.npz"


def _cache_dir():
    return DIR() / "cache"


def _vec_cache():
    return config.DATA_ROOT / "embed_cache" / "chunks"


# ---- small helpers ----------------------------------------------------------------------------------------------------------------

def _protected(case_id) -> bool:
    return bool(case_id) and (str(case_id) in config.PROTECTED_CASES or access.is_protected(str(case_id)))


def _guard(case_id):
    if _protected(case_id):
        raise ValueError("protected")


def _month(iso) -> str:
    """"Sep 2026" from an ISO date or time; "" when it does not parse."""
    try:
        return date.fromisoformat(str(iso or "")[:10]).strftime("%b %Y")
    except ValueError:
        return ""


def _dmy(iso) -> str:
    try:
        return date.fromisoformat(str(iso or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def _clip(s, n) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def _display(user) -> str:
    try:
        from .slots import display_name
        return display_name(user) or ""
    except Exception:
        return ""


def norm_name(name) -> str:
    """A typed cancer name for matching: lower case, punctuation removed, whitespace collapsed."""
    return " ".join(re.sub(r"[^\w\s]|_", " ", str(name or "").lower()).split())


def group(case) -> str | None:
    """The cancer group of a Case File: colon and rectum share "colorectal"; a generic protocol (or none) groups by the typed cancer
    name ("name:<normalised name>"); every other protocol is its own group. None when there is nothing to group by."""
    case = case if isinstance(case, dict) else {}
    pid = str(case.get("protocol") or "")
    if pid and pid not in protocol.GENERIC_IDS:
        return GROUPS.get(pid, pid)
    n = norm_name(case.get("cancer_name"))
    return NAME_PREFIX + n if n else None


def group_label(case) -> str:
    """How the group is named: the protocol's label, "Colorectal cancer" for the shared group, the typed cancer name for generic."""
    case = case if isinstance(case, dict) else {}
    g = group(case)
    if not g:
        return ""
    if g.startswith(NAME_PREFIX):
        return " ".join(str(case.get("cancer_name") or "").split())
    if g in GROUP_LABELS:
        return GROUP_LABELS[g]
    pid = str(case.get("protocol") or "")
    try:
        return protocol.get(pid).get("label") or pid
    except (OSError, ValueError, TypeError):
        return pid


def _outcome(rec) -> str:
    return case_summary._outcome(rec)


def _records(st) -> list:
    return case_summary.records(st)


# ---- the scrubber -----------------------------------------------------------------------------------------------------------------

_LONG_DIGITS = re.compile(r"\d{6,}")
_DAY_DATE = re.compile(r"(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{4}(?!\d)|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")


def _scrub_patterns(case) -> list:
    pats = set()
    p = (case or {}).get("patient") or {}
    for ident in published._identifiers(case):
        ident = " ".join(str(ident).split())
        if len(ident) >= 3:
            pats.add(re.escape(ident))
        for part in re.split(r"[\s,/]+", ident):
            if len(part) >= 5 and not part.isalpha():  # a number or mixed part of an identifier
                pats.add(re.escape(part))
    for x in (p.get("ids") or []):
        if isinstance(x, dict) and x.get("value"):
            pats.add(re.escape(str(x["value"])))
    for w in re.findall(r"[^\W\d_]{3,}", str(p.get("name") or "")):
        pats.add(re.escape(w))
    # the longest first, so a whole identifier goes before its parts
    return [re.compile(r"(?<![A-Za-z0-9])" + x + r"(?![A-Za-z0-9])", re.I) for x in sorted(pats, key=len, reverse=True)]


def scrub(text, case, _pats=None) -> str:
    """Remove what could name the patient of `case` from a text: any of its identifiers (published._identifiers, every part of five
    or more characters that is not a word, every name word of three or more letters; whole words, any case) becomes "[id]", as does a run
    of six or more digits; a day-level date becomes "[date]". Used on every profile text and, by item 7.2, on every quote shown."""
    s = str(text or "")
    for rx in (_scrub_patterns(case) if _pats is None else _pats):
        s = rx.sub("[id]", s)
    s = _DAY_DATE.sub("[date]", s)
    return _LONG_DIGITS.sub("[id]", s)


# ---- eligibility and signature ------------------------------------------------------------------------------------------------------

def eligible(case, state, exclude=()) -> bool:
    """A past Case File that may be profiled and listed: not protected, not archived, listed, with a cancer group, with at least one
    board record whose outcome is a decision, and not one of `exclude`."""
    if not isinstance(case, dict):
        return False
    cid = str(case.get("case_id") or "")
    if not cid or _protected(cid) or access.is_protected(case) or access.is_archived(case):
        return False
    if ((case.get("listing") or {}).get("status")) != "listed":
        return False
    if not (case.get("protocol") or case.get("cancer_name")) or not group(case):
        return False
    if cid in set(exclude or ()):
        return False
    return any(_outcome(r) == "decision" for r in _records(state or {}))


def signature(case, state) -> str:
    """What a profile was built from (16 hex): the documents and confirmations (rules.case_signature), the board records and their
    versions, the stage confirmations, the Case summary's current version, its review and edits, the archive and listing state, the
    protocol, cancer name, setting and age / sex, and the profile schema."""
    cid = case["case_id"]
    st = state or {}
    stg = st.get("staging") if isinstance(st.get("staging"), dict) else {}
    pro = stg.get("prognostic") if isinstance(stg.get("prognostic"), dict) else {}
    v = case_summary.current(st) or {}
    basis = {
        "case": rules.case_signature(cid, st).get("hash"),
        "records": [[r.get("id"), r.get("version"), _outcome(r)] for r in _records(st)],
        "staging": [((stg.get("confirmed") or {}) if isinstance(stg.get("confirmed"), dict) else {}).get("at"),
                    ((pro.get("confirmed") or {}) if isinstance(pro.get("confirmed"), dict) else {}).get("at"), bool(stg.get("rejected"))],
        "summary": [v.get("n"), (v.get("review") or {}).get("status"), len(v.get("edits") or [])],
        "archived": (case.get("archived") or {}).get("at") if isinstance(case.get("archived"), dict) else None,
        "listing": (case.get("listing") or {}).get("status"),
        "protocol": case.get("protocol") or "", "cancer_name": case.get("cancer_name") or "", "setting": case.get("setting") or "",
        "agesex": (case.get("patient") or {}).get("agesex") or "", "version": VERSION}
    return hashlib.sha1(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---- the profile ------------------------------------------------------------------------------------------------------------------

def age_band(agesex) -> tuple:
    """(age band, sex) from the Case File's "52 Y / F": ten-year bands ("50 to 59", "90 or older"); "" when it does not parse."""
    age, sex = identity.parse_agesex(str(agesex or ""))
    band = "" if age is None else "90 or older" if age >= 90 else f"{age // 10 * 10} to {age // 10 * 10 + 9}"
    return band, sex or ""


def _title(cur, filenames) -> str:
    t = " ".join(str(cur.get("doc_title") or "").split())
    if not t or t in filenames:  # a title that is only the file name (file names can carry names)
        t = str(cur.get("doc_type") or "report").replace("_", " ").capitalize()
    return t


def _entry(fid, cur, cat, filenames, scr) -> dict | None:
    """One fact as the profile keeps it, or None when it does not pass the gate of summary.fill_from_facts: verified or confirmed,
    present, from a final report, with a located quote unless a clinician confirmed it (then no quote, marked confirmed)."""
    if not isinstance(cur, dict) or cur.get("verification") not in rules.VERIFIED or cur.get("state") != "present" or not cur.get("doc_final"):
        return None
    confirmed_by = cur.get("confirmed_by") or ("clinician" if cur.get("verification") == "confirmed" else "")
    loc = cur.get("location") if isinstance(cur.get("location"), dict) else None
    if not confirmed_by and not (loc and cur.get("quote")):
        return None
    title = _title(cur, filenames)
    e = {"fact": fid, "label": (cat.get(fid) or {}).get("label") or fid, "value": scr(cur.get("value")), "quote": "",
         "doc_id": cur.get("doc_id"), "doc_title": scr(title), "date": cur.get("date") or "", "month": _month(cur.get("date")),
         "page": None, "start": None, "end": None, "confirmed": bool(confirmed_by)}
    if confirmed_by:
        e["confirmed_by"] = "a clinician" if confirmed_by == "clinician" else (_display(confirmed_by) or "a clinician")
    else:
        e.update(quote=scr(cur.get("quote")), page=loc.get("page"), start=loc.get("start"), end=loc.get("end"))
    return e


def _where(title, iso, full=False) -> str:
    d = _dmy(iso) if full else _month(iso)
    return f"{title}, {d or 'date not stated'}"


def _staging(st) -> list:
    out = []
    d = st.get("staging") if isinstance(st.get("staging"), dict) else None
    if not d or d.get("rejected") or d.get("status") != "staged" or not isinstance(d.get("confirmed"), dict) or not d["confirmed"].get("at"):
        return out
    comps = " ".join(str((d.get("components") or {}).get(k, {}).get("cat") or "") for k in ("T", "N", "M")).strip()
    text = ", ".join(x for x in (comps, f"stage {d['stage']}" if d.get("stage") else "") if x)
    c = d["confirmed"]
    by = c.get("by_name") or _display(c.get("by")) or "a doctor"
    if text:
        out.append({"text": text, "kind": "confirmed_draft", "label": f"Vaidyx draft stage, confirmed by {by}", "quote": text,
                    "date": str(c["at"])[:10], "by": by})
    p = d.get("prognostic") if isinstance(d.get("prognostic"), dict) else None
    if p and isinstance(p.get("confirmed"), dict) and p["confirmed"].get("at") and not p.get("rejected") and p.get("stage"):
        pby = p["confirmed"].get("by_name") or _display(p["confirmed"].get("by")) or "a doctor"
        t = f"prognostic stage group {p['stage']}"
        out.append({"text": t, "kind": "confirmed_draft", "label": f"Vaidyx draft prognostic stage group, confirmed by {pby}", "quote": t,
                    "date": str(p["confirmed"]["at"])[:10], "by": pby})
    return out


def _summary_part(st, scr) -> tuple:
    """The "since the board" sentences of the current Case summary (placeholders left out), each with where it comes from."""
    v = case_summary.current(st)
    if not v:
        return [], ""
    out = []
    for sec in v.get("sections") or []:
        if sec.get("id") != "since":
            continue
        for s in sec.get("sentences") or []:
            if not isinstance(s, dict) or s.get("fixed") or not str(s.get("text") or "").strip():
                continue
            cite = next((c for c in s.get("citations") or [] if isinstance(c, dict) and c.get("doc_id") and c.get("doc_title")), None)
            where = _where(scr(cite["doc_title"]), cite.get("date")) if cite else _where("Case summary", v.get("built_at"))
            out.append({"text": scr(s["text"]), "where": where, "source": {"sentence": s.get("id"), "section": "since"}})
    return out, str(v.get("built_at") or "")


def _later_records(docs, recs) -> str:
    dec = [r for r in recs if _outcome(r) == "decision"]
    if not dec:
        return NO_DECISION_YET
    last = case_summary._rec_date(dec[-1])
    after = sorted(ev for ev in (dates.doc_dates(d)["event"] for d in docs) if ev and last and ev > last)
    if not after:
        return NO_RECORDS_AFTER
    n = len(after)
    return f"{n} record{'s' if n != 1 else ''} dated after the last board decision; latest {_month(after[-1])}"


def _decision(rec, scr) -> dict:
    mods = rec.get("modalities") if isinstance(rec.get("modalities"), list) else []
    return {"record_id": rec.get("id"), "date": case_summary._rec_date(rec), "when": _month(case_summary._rec_date(rec)),
            "outcome": _outcome(rec), "outcome_label": decision_record.OUTCOMES.get(_outcome(rec), _outcome(rec)),
            "intent": str(rec.get("intent") or ""), "intent_label": decision_record.choice_label("intent", rec.get("intent")) if rec.get("intent") else "",
            "text": scr(rec.get("decision_text")), "rationale": scr(str(rec.get("rationale") or "")[:600]),
            "modalities": [decision_record.choice_label("modalities", m) for m in mods],
            "sequence": scr(rec.get("sequence")), "stage_as_agreed": scr(rec.get("stage_as_agreed")), "version": rec.get("version", 1)}


def _text(p) -> tuple:
    """The plain paragraph embedded and matched (built by code from the structured part), and the decisions chunk when it is long."""
    bits = []
    if p["group_label"]:
        bits.append(f"Cancer group: {p['group_label']}.")
    if p["setting_label"]:
        bits.append(f"Setting: {p['setting_label']}.")
    if p["age_band"]:
        bits.append(f"Age band {p['age_band']}.")
    if p["sex"]:
        bits.append(f"Sex {p['sex']}.")
    for s in p["stage"]:
        bits.append(f"Stage {s['label']}: {s['text']}.")

    def fact_text(e):
        q = e.get("quote") or ""
        extra = f" ({q})" if q and grounding_norm(q) != grounding_norm(e["value"]) and len(q) <= 200 else ""
        return f"{e['label']}: {e['value']}{extra}"
    if p["histology"]:
        bits.append("Histology: " + "; ".join(fact_text(e) for e in p["histology"]) + ".")
    for e in p["biomarkers"] + p["other"]:
        bits.append(fact_text(e) + ".")
    if p["treatments"]:
        bits.append("Treatments received: " + "; ".join(fact_text(e) for e in p["treatments"]) + ".")
    for s in p["outcome_so_far"]["sentences"]:
        bits.append(s["text"])
    clinical = " ".join(bits)
    decs = []
    for d in p["decisions"]:
        head = d["outcome_label"].lower() + (f", intent {d['intent_label'].lower()}" if d["intent_label"] else "")
        mods = f", {', '.join(m.lower() for m in d['modalities'])}" if d["modalities"] else ""
        decs.append(f"{head}{mods}" + (f": {_clip(d['text'], 300)}" if d["text"] else ""))
    decisions = ("Board decisions: " + "; ".join(decs) + ".") if decs else ""
    whole = " ".join(x for x in (clinical, decisions) if x)
    if len(whole) <= CHUNK_CHARS:
        return whole, ""
    return _clip(clinical, CHUNK_CHARS), _clip(decisions, CHUNK_CHARS)


def grounding_norm(s) -> str:
    from .grounding import norm
    return norm(str(s or ""))


def _lines(p) -> list:
    """The numbered evidence lines (item 7.2 quotes them): quoted facts first (biomarkers, histology, stage, treatments, other), then
    the Case summary sentences, then the decision fields (kind "decision": shown, never offered as a "why similar" line)."""
    out = []

    def add(kind, text, where, where_full, source, fact=None):
        if not str(text or "").strip() or len(out) >= MAX_LINES:
            return
        out.append({"id": f"L{len(out) + 1}", "kind": kind, **({"fact": fact} if fact else {}), "text": text, "where": where,
                    "where_full": where_full, "source": source})

    def facts(entries, kind):
        for e in entries:
            if e.get("confirmed") or not e.get("quote"):
                continue  # a confirmed value without a quote is never a quoted line
            add(kind, e["quote"], _where(e["doc_title"], e["date"]), _where(e["doc_title"], e["date"], True),
                {"doc_id": e["doc_id"], "page": e["page"], "start": e["start"], "end": e["end"]}, e["fact"])
    facts(p["biomarkers"], "fact")
    facts(p["histology"], "fact")
    for s in p["stage"]:
        if s["kind"] == "recorded" and s.get("quote"):
            add("stage", s["quote"], _where(s["doc_title"], s["date"]), _where(s["doc_title"], s["date"], True),
                {"doc_id": s["doc_id"], "page": s["page"], "start": s["start"], "end": s["end"]}, s.get("fact"))
        elif s["kind"] == "confirmed_draft":
            add("stage", s["quote"], _where("Vaidyx draft stage confirmation", s["date"]), _where("Vaidyx draft stage confirmation", s["date"], True),
                {"staging": "confirmed"})
        elif s["kind"] == "agreed":
            add("stage", s["quote"], _where("Board record", s["date"]), _where("Board record", s["date"], True),
                {"record": s["record"], "field": "stage_as_agreed"})
    facts(p["treatments"], "treatment")
    facts(p["other"], "fact")
    for s in p["outcome_so_far"]["sentences"]:
        add("summary", s["text"], s["where"], s["where"], s["source"])
    for d in p["decisions"]:
        w, wf = _where("Board record", d["date"]), _where("Board record", d["date"], True)
        for f in DECISION_FIELDS:
            val = {"decision_text": d["text"], "intent": d["intent_label"], "modalities": ", ".join(d["modalities"]),
                   "sequence": d["sequence"], "rationale": d["rationale"]}[f]
            add("decision", val, w, wf, {"record": d["record_id"], "field": f}, f)
    return out


def build_profile(case_id, case=None, state=None) -> dict:
    """The profile of one Case File, by code only (no model): see the module docstring. Raises ValueError("protected") for the real
    case and ValueError("not_found") for a missing one. Nothing is stored here (ensure() stores)."""
    _guard(case_id)
    case = store.get_case(case_id) if case is None else case
    if not isinstance(case, dict):
        raise ValueError("not_found")
    _guard(case.get("case_id"))
    st = store.get_state(case_id) if state is None else state
    pats = _scrub_patterns(case)

    def scr(t):
        return scrub(t, case, pats)
    docs = [d for d in rules.case_docs(case_id, st) if d.get("state") == "ready" and not d.get("dismissed")]
    filenames = {str(d.get("filename") or "") for d in docs} - {""}
    facts = rules.resolve_facts(docs, st.get("overrides"))
    cat = protocol.facts()

    def cur(fid):
        return (facts.get(fid) or {}).get("current")

    def keep(ids):
        return [e for e in (_entry(f, cur(f), cat, filenames, scr) for f in ids) if e]
    pid = str(case.get("protocol") or "")
    recs = _records(st)
    band, sex = age_band((case.get("patient") or {}).get("agesex"))
    # the stage as recorded: the newest of the stage facts that pass the gate (as summary.py picks it), copied, never derived
    stage = []
    rec_stage = max(keep(STAGE_FACTS), key=lambda e: e["date"] or "", default=None)
    if rec_stage:
        stage.append({"text": rec_stage["value"], "kind": "recorded", "label": "as recorded", "quote": rec_stage["quote"],
                      "doc_id": rec_stage["doc_id"], "doc_title": rec_stage["doc_title"], "date": rec_stage["date"], "month": rec_stage["month"],
                      "page": rec_stage["page"], "start": rec_stage["start"], "end": rec_stage["end"], "fact": rec_stage["fact"],
                      "confirmed": rec_stage["confirmed"]})
    for s in _staging(st):
        stage.append({"text": scr(s["text"]), "kind": "confirmed_draft", "label": s["label"], "quote": scr(s["quote"]), "doc_id": None,
                      "doc_title": "", "date": s["date"], "month": _month(s["date"]), "page": None, "start": None, "end": None,
                      "source": {"staging": "confirmed"}})
    for r in recs:
        agreed = " ".join(str(r.get("stage_as_agreed") or "").split())
        if agreed:
            stage.append({"text": scr(agreed), "kind": "agreed", "label": "as agreed by the board", "quote": scr(agreed), "doc_id": None,
                          "doc_title": "", "date": case_summary._rec_date(r), "month": _month(case_summary._rec_date(r)), "page": None,
                          "start": None, "end": None, "record": r.get("id"), "source": {"record": r.get("id"), "field": "stage_as_agreed"}})
    # treatments: every verified line of the treatment facts (a surgery then a chemotherapy are two reports), oldest first
    treatments, seen = [], set()
    for fid in TREATMENTS:
        for h in (facts.get(fid) or {}).get("history") or []:
            if h.get("superseded"):
                continue
            e = _entry(fid, h, cat, filenames, scr)
            if e and (fid, e["value"], e["doc_id"]) not in seen:
                seen.add((fid, e["value"], e["doc_id"]))
                treatments.append(e)
    treatments.sort(key=lambda e: e["date"] or "")
    sentences, _ = _summary_part(st, scr)
    p = {"case_id": case_id, "version": VERSION, "signature": signature({**case, "case_id": case_id}, st), "built_at": store.now_iso(),
         "group": group(case), "group_label": group_label(case), "cancer": protocol.case_label(case), "protocol": pid,
         "cancer_name": " ".join(str(case.get("cancer_name") or "").split()), "setting": case.get("setting") or "",
         "setting_label": protocol.setting_label(pid, case.get("setting")) or str(case.get("setting") or "").replace("_", " "),
         "hospital_level": case.get("hospital_level") or "", "age_band": band, "sex": sex, "stage": stage,
         "histology": keep(HISTOLOGY), "biomarkers": keep(BIOMARKERS), "treatments": treatments, "other": keep(OTHER),
         "decisions": [_decision(r, scr) for r in recs],
         "outcome_so_far": {"sentences": sentences, "later_records": _later_records(docs, recs)}}
    try:
        p["department"] = access.owner(case) or ""  # internal only: the card names it only after opening (contract 8.1 point 1)
    except Exception:
        p["department"] = ""
    p["lines"] = _lines(p)
    text, text_dec = _text(p)
    p["text"], p["text_decisions"] = scr(text), scr(text_dec)
    return p


def query_profile(case_id) -> dict:
    """The profile of the file searched from, whatever its eligibility (transient, never stored)."""
    _guard(case_id)
    return build_profile(case_id)


# ---- the index ----------------------------------------------------------------------------------------------------------------------

def _load_profile(case_id) -> dict | None:
    try:
        p = store._read_json(_profile_path(case_id), None)
    except (ValueError, OSError):
        return None
    return p if isinstance(p, dict) else None


def _chunks_of(p) -> list:
    base = {"case_id": p["case_id"], "group": p.get("group"), "setting": p.get("setting") or "", "age_band": p.get("age_band") or "",
            "sex": p.get("sex") or ""}
    out = [{**base, "chunk": "main", "text": p.get("text") or ""}]
    if p.get("text_decisions"):
        out.append({**base, "chunk": "decisions", "text": p["text_decisions"]})
    return [c for c in out if c["text"].strip()]


def _vectors(texts) -> tuple:
    """Raw vectors for the chunk texts through search._embed, content-cached (sha1 of the model + "similar:" + text) so an unchanged
    chunk is never embedded twice. Returns (vectors, number embedded now)."""
    cache = _vec_cache()
    cache.mkdir(parents=True, exist_ok=True)
    vecs, todo = [None] * len(texts), []
    for i, t in enumerate(texts):
        f = cache / (hashlib.sha1((retrieval.EMBED_MODEL + "similar:" + t).encode()).hexdigest() + ".npy")
        if f.exists():
            try:
                vecs[i] = np.load(f)
                continue
            except (OSError, ValueError):
                pass
        todo.append((i, f))
    for k in range(0, len(todo), EMBED_BATCH):
        part = todo[k:k + EMBED_BATCH]
        new = retrieval._embed([texts[i] for i, _ in part])
        for (i, f), v in zip(part, new):
            v = np.asarray(v, dtype=np.float32)
            np.save(f, v)
            vecs[i] = v
    return vecs, len(todo)


def _write_index(chunks, vecs) -> None:
    """index.npz first (a .tmp then os.replace), then index.json: a reader keyed on both mtimes never sees a half pair."""
    DIR().mkdir(parents=True, exist_ok=True)
    if vecs:
        m = np.stack([np.asarray(v, dtype=np.float32) for v in vecs])
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        m = (m / np.where(norms == 0, 1, norms)).astype(np.float32)
    else:
        m = np.zeros((0, 0), dtype=np.float32)
    keys = np.array([f"{c['case_id']}|{c['chunk']}" for c in chunks], dtype=str)
    tmp = _index_npz().with_suffix(".npz.tmp")
    with open(tmp, "wb") as fh:
        np.savez(fh, vectors=m, keys=keys)
    os.replace(tmp, _index_npz())
    sig = hashlib.sha1(json.dumps(sorted(f"{c['case_id']}|{c['chunk']}|{hashlib.sha1(c['text'].encode()).hexdigest()}" for c in chunks)).encode()).hexdigest()[:16]
    store._write_json(_index_json(), {"version": VERSION, "embed_model": retrieval.EMBED_MODEL, "chunks": chunks, "signature": sig,
                                      "built_at": store.now_iso()})


def _rebuild_index() -> int:
    chunks = []
    d = _profiles_dir()
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        cid = f.stem
        if _protected(cid):
            continue
        p = _load_profile(cid)
        if p and p.get("case_id") == cid:
            chunks.extend(_chunks_of(p))
    vecs, n = _vectors([c["text"] for c in chunks])
    _write_index(chunks, vecs)
    return n


def _remove(case_id) -> bool:
    try:
        _profile_path(case_id).unlink()
        return True
    except (FileNotFoundError, ValueError):
        return False


def ensure(force=False) -> dict:
    """Bring the index up to date: every Case File directory is looked at (a protected id skipped by its name before anything in it is
    opened), an eligible file whose signature changed is profiled again, an ineligible or vanished one loses its profile, and the
    index files are rewritten when anything changed. Returns counts."""
    out = {"scanned": 0, "built": 0, "removed": 0, "unchanged": 0, "embedded": 0, "failed": 0}
    with _lock:
        live = set()
        changed = False
        root = config.CASES_DIR
        dirs = sorted(root.iterdir()) if root.exists() else []
        for d in dirs:
            name = d.name
            if _protected(name):  # the real case: never opened, never profiled
                continue
            try:
                if store.safe_id(name) != name or not d.is_dir():
                    continue
            except ValueError:
                continue
            out["scanned"] += 1
            try:
                case = store.get_case(name)
                if not isinstance(case, dict) or _protected(case.get("case_id")):
                    continue
                case = {**case, "case_id": name}
                st = store.get_state(name)
                if not eligible(case, st):
                    continue
                sig = signature(case, st)
                old = _load_profile(name)
                if not force and old and old.get("signature") == sig and old.get("version") == VERSION:
                    live.add(name)
                    out["unchanged"] += 1
                    continue
                p = build_profile(name, case, st)
                store._write_json(_profile_path(name), p)
                live.add(name)
                out["built"] += 1
                changed = True
            except Exception as e:  # one broken Case File never stops the scan
                log.warning("similar: profile of %s not built (%s)", name, e)
                out["failed"] += 1
        pdir = _profiles_dir()
        for f in sorted(pdir.glob("*.json")) if pdir.exists() else []:
            if f.stem not in live:
                f.unlink(missing_ok=True)
                out["removed"] += 1
                changed = True
        if changed or force or not _index_json().exists() or not _index_npz().exists() or _stale_meta():
            out["embedded"] = _rebuild_index()
    return out


def _stale_meta() -> bool:
    try:
        meta = store._read_json(_index_json(), None) or {}
    except (ValueError, OSError):
        return True
    return meta.get("version") != VERSION or meta.get("embed_model") != retrieval.EMBED_MODEL


def forget(case_id) -> None:
    """Remove a Case File from the index at once (archived, deleted, protected): its profile and its chunks, no embedding."""
    with _lock:
        _remove(case_id)
        if not (_index_json().exists() or _index_npz().exists()):
            return
        meta, m = _read_index()
        all_chunks = meta.get("chunks") or []
        keep = [i for i, c in enumerate(all_chunks) if c.get("case_id") != case_id]
        if m.shape[0] != len(all_chunks):  # the pair does not line up: drop both, the next ensure() rebuilds them
            for f in (_index_json(), _index_npz()):
                f.unlink(missing_ok=True)
            return
        _write_index([all_chunks[i] for i in keep], [m[i] for i in keep])


def job(now=None) -> dict:
    """The scheduler job (every 30 minutes): ensure(); never raises."""
    try:
        return ensure()
    except Exception as e:
        log.warning("similar index job failed (%s)", e)
        return {"error": f"{e.__class__.__name__}: {str(e)[:200]}"}


def _read_index() -> tuple:
    meta, m = {"chunks": []}, np.zeros((0, 0), dtype=np.float32)
    try:
        meta = store._read_json(_index_json(), None) or {"chunks": []}
        with np.load(_index_npz(), allow_pickle=False) as z:
            vec, keys = z["vectors"], [str(k) for k in z["keys"]]
        rows = {k: i for i, k in enumerate(keys)}
        idx = [rows.get(f"{c.get('case_id')}|{c.get('chunk')}") for c in meta.get("chunks") or []]
        if vec.size and all(i is not None for i in idx):
            m = vec[idx] if idx else np.zeros((0, vec.shape[1]), dtype=np.float32)
        elif not (meta.get("chunks") or []):
            m = np.zeros((0, 0), dtype=np.float32)
        else:  # the pair does not line up: no vectors (ensure(force=True) rebuilds)
            m = np.zeros((0, 0), dtype=np.float32)
    except (OSError, ValueError, KeyError):
        pass
    return meta, m


def load_index() -> tuple:
    """(index.json as a dict, the vectors aligned with its chunks), cached in memory and reloaded when the files change on disk."""
    try:
        key = (str(_index_json()), _index_json().stat().st_mtime_ns, _index_npz().stat().st_mtime_ns)
    except OSError:
        return {"chunks": []}, np.zeros((0, 0), dtype=np.float32)
    if _loaded["key"] != key:
        meta, m = _read_index()
        _loaded.update(key=key, meta=meta, matrix=m)
    return _loaded["meta"], _loaded["matrix"]


# ---- the candidates (item 7.1; item 7.2 orders them with the reasoner) ----------------------------------------------------------------

def _ids(case) -> set:
    return {x for x in (identity.normalise_id(i) for i in published._identifiers(case)) if len(x) >= 3}


def _linked(case) -> set:
    out = set()
    for l in (case or {}).get("linked_cases") or []:
        cid = l.get("case_id") if isinstance(l, dict) else l
        if cid:
            out.add(str(cid))
    return out


def _bm25(tok, q, k1=1.4, b=0.75):
    """search.CaseIndex.bm25, over a list of token lists."""
    n = len(tok)
    df = Counter(t for ts in tok for t in set(ts))
    avgdl = sum(map(len, tok)) / max(n, 1)
    scores = np.zeros(n)
    for t in set(retrieval.tokenize(q)):
        if t not in df:
            continue
        idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
        for i, ts in enumerate(tok):
            tf = ts.count(t)
            if tf:
                scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(ts) / avgdl))
    return scores


def candidates(case_id, words="", n=TOP_N, profile=None) -> dict:
    """The past Case Files of the same cancer group most like this one, by BM25 plus dense vectors fused by Reciprocal Rank Fusion
    (as search.CaseIndex.search). Never the file itself, a file of the same patient (an identifier in common) or a linked file.
    `words` (the doctor's extra words) are screened by published.check_terms (PublishedError) and weigh in both sides. The ranks are
    internal: nothing here is ever shown as a number."""
    _guard(case_id)
    case = store.get_case(case_id)
    if not isinstance(case, dict):
        raise ValueError("not_found")
    case = {**case, "case_id": case_id}
    w = published.check_terms(case, words)[:WORDS_MAX] if str(words or "").strip() else ""
    ensure()
    src = profile or query_profile(case_id)
    g = src.get("group")
    if not g:
        return {"group": None, "group_label": "", "candidates": [], "n_in_group": 0, "note": NO_GROUP}
    meta, m = load_index()
    chunks = meta.get("chunks") or []
    my_ids, my_links = _ids(case), _linked(case)
    ok: dict = {}
    rows = []
    for i, c in enumerate(chunks):
        cid = str(c.get("case_id") or "")
        if c.get("group") != g or not cid or cid == case_id or cid in my_links or _protected(cid):
            continue
        if cid not in ok:
            other = store.get_case(cid)
            good = isinstance(other, dict) and not _protected(other.get("case_id"))
            if good:
                other = {**other, "case_id": cid}
                good = (eligible(other, store.get_state(cid), exclude=(case_id,)) and not (_ids(other) & my_ids)
                        and case_id not in _linked(other))
            ok[cid] = good
        if ok[cid]:
            rows.append(i)
    n_in = len({chunks[i]["case_id"] for i in rows})
    note = ""
    if n_in < FEW:
        note = ("No past Case File of this cancer group has a recorded decision." if n_in == 0 else
                f"Only {n_in} past Case File{'s' if n_in != 1 else ''} of this cancer group {'have' if n_in != 1 else 'has'} a recorded decision.")
    if not rows:
        return {"group": g, "group_label": src.get("group_label") or "", "candidates": [], "n_in_group": 0, "note": note}
    tok = [retrieval.tokenize(chunks[i]["text"]) for i in rows]
    q = src.get("text") or ""
    if w:
        q = f"{q} Doctor's words: {w}"
    arrays = [("lex", _bm25(tok, q))]
    if w:
        arrays.append(("lex", _bm25(tok, w)))
    if m.shape[0] == len(chunks) and m.size:
        qv = np.asarray(retrieval._embed([q], prefix=QUERY_PREFIX)[0], dtype=np.float32)
        nq = float(np.linalg.norm(qv)) or 1.0
        arrays.append(("sem", m[rows] @ (qv / nq)))
    rr = np.zeros(len(rows))
    for kind, arr in arrays:
        order = np.argsort(-arr, kind="stable")
        for rank, i in enumerate(order):
            if kind == "lex" and arr[i] <= 0:
                break
            rr[i] += 1.0 / (RRF_K + rank + 1)
    best: dict = {}
    for j, i in enumerate(rows):
        cid = chunks[i]["case_id"]
        best[cid] = max(best.get(cid, 0.0), float(rr[j]))
    ordered = sorted(best, key=lambda c: (-best[c], c))[:max(0, int(n))]
    return {"group": g, "group_label": src.get("group_label") or "", "candidates": [{"case_id": c, "rrf_rank": k + 1} for k, c in enumerate(ordered)],
            "n_in_group": n_in, "note": note}


# ---- item 7.2 adds here: search (the reasoner ordering), order, lines (the "why similar" and "how it differs" picks), the cards --------

# Part 2 (item 7.2): the reasoner's order, the quoted "why similar" and "how it differs" lines, the result cards, the search, the
# routes' helpers (info, open_info). The order is the only rank: nothing numeric is shown, the model answers with ids only, every
# shown line is a stored quote checked again word for word against its source, and a past board's decision is never a reason.
import asyncio
import random
import statistics
import time

from . import grounding, llm, org

PROMPT_VERSION = "similar-v1"
MODEL_NAME = "Gemma-4-31B"
MODEL_LINE = "Gemma-4-31B, a non-medical model; it only orders the list and picks quoted lines"
ORDER_NOTE_MODEL = "Listed in order of likeness as judged by Gemma-4-31B (non-medical). The order is not a score."
ORDER_NOTE_TEXT = "Ordered by text match only; the model ordering was not available."
SHOWN = 10
LINES_MAX = 25
SIMILAR_MAX = 3
DIFFERS_MAX = 2
SEARCH_BUDGET_S = 45
ADVICE_WORDS = ("do the same", "consider", "suggest", "recommend", "treat as", "follow", "best match")

PROTECTED_REASON = "This Case File is not searched from."
NO_GROUP_REASON = "No cancer group on this file: set the protocol or the cancer name first."
ADMIN_REASON = "A Vaidyx admin does not search Case Files."
SCOPE_REASON = "Only a doctor with full access to this Case File can search; a window opened with a reason cannot."
LINES_LATE = "The quoted lines took too long this time; the files are listed without them."
MATCH_FIELDS = ("cancer group", "setting", "age band", "sex", "stage as recorded")
_DECISIONS_MARK = "Board decisions: "

ORDER_SYSTEM = ("You order past Case Files by how much their recorded facts resemble the current Case File: same cancer, setting, stage, "
                "histology, markers, treatments already received, and what the doctor asked for. Use only the text given. Do not judge "
                "any treatment, do not say which is better, do not say what to do. Return the ids from most to least similar, every id once.")
ORDER_SCHEMA = {"type": "object", "required": ["order"], "properties": {
    "order": {"type": "array", "items": {"type": "string", "description": "an id of the list, like P3"}}}}
LINES_SYSTEM = ("You compare the recorded lines of two Case Files. List A holds lines of the current Case File, list B lines of a past Case "
                "File. Pair a line of A with a line of B only when both are about the same kind of fact (the same marker, the histology, "
                "the grade, the stage, the treatments received, the course since the board). Put a pair under \"similar\" when the two "
                "lines agree and under \"differs\" when they say different things. Use only the lines given. Do not judge any treatment, "
                "do not say which is better, do not say what to do. Answer with the ids only: at most three similar pairs and two differs pairs.")
_PAIR = {"type": "object", "properties": {"a": {"type": "string", "description": "an id of list A, like A3"},
                                          "b": {"type": "string", "description": "an id of list B, like B2"}}}
LINES_SCHEMA = {"type": "object", "required": ["similar", "differs"], "properties": {
    "similar": {"type": "array", "items": _PAIR}, "differs": {"type": "array", "items": _PAIR}}}


def _sha(s) -> str:
    return hashlib.sha1(str(s).encode()).hexdigest()


# ---- the text the reasoner reads ------------------------------------------------------------------------------------------------

def candidate_text(profile) -> str:
    """The profile's text without its "Board decisions: ..." sentence (research 4.8: the order is by likeness of the recorded facts,
    never by what a board did); text_decisions is never read. Used for the source and for every candidate."""
    t = str((profile or {}).get("text") or "")
    i = t.find(_DECISIONS_MARK)
    return (t[:i] if i >= 0 else t).strip()


# ---- the order (research 4.5, contract 8.2) ---------------------------------------------------------------------------------------

def _order_key(src, cands, words) -> str:
    return _sha(json.dumps([src.get("signature"), [c.get("signature") for c in cands], words or "", PROMPT_VERSION, MODEL_NAME]))


def _cache_path(key):
    return _cache_dir() / f"{key}.json"


def _cache_get(key, ids) -> list | None:
    try:
        d = store._read_json(_cache_path(key), None)
    except (ValueError, OSError):
        return None
    got = (d or {}).get("order") if isinstance(d, dict) else None
    if not isinstance(got, list) or len(got) != len(ids) or set(got) != set(ids) or d.get("prompt_version") != PROMPT_VERSION:
        return None
    return [str(x) for x in got]


def _permutations(src, cands) -> list:
    """Three fixed orders of the candidates (indices): the RRF order, its reverse and a shuffle seeded by the file and the list."""
    n = len(cands)
    seed = int(_sha(str(src.get("case_id") or "") + "".join(sorted(str(c.get("signature") or "") for c in cands)))[:16], 16)
    shuffled = list(range(n))
    random.Random(seed).shuffle(shuffled)
    return [list(range(n)), list(range(n))[::-1], shuffled]


def _order_messages(src, texts, words) -> list:
    asked = f"The doctor asked to look for: {words}\n\n" if words else ""
    listing = "\n".join(f"P{k + 1}: {t}" for k, t in enumerate(texts))
    user = (f"Current Case File:\n{candidate_text(src)}\n\n{asked}Past Case Files:\n{listing}\n\n"
            f"Return every id once (P1 to P{len(texts)}), from most to least similar.")
    return [{"role": "system", "content": ORDER_SYSTEM}, {"role": "user", "content": user}]


def _as_permutation(answer, n) -> list | None:
    """The positions (0-based) in the order the model gave, or None unless the answer is exactly a permutation of P1..Pn."""
    got = answer.get("order") if isinstance(answer, dict) else None
    if not isinstance(got, list) or len(got) != n:
        return None
    out = []
    for x in got:
        m = re.fullmatch(r"P(\d+)", str(x).strip().upper()) if isinstance(x, str) else None
        if not m or not 1 <= int(m.group(1)) <= n:
            return None
        out.append(int(m.group(1)) - 1)
    return out if len(set(out)) == n else None


async def order(src, cands, words="", *, info=None, audit=None) -> tuple:
    """(case ids in order, "model" | "text"). `cands` are candidate profiles in RRF order. The reasoner sees them three times (the RRF
    order, its reverse, a seeded shuffle) under the ids P1..Pn of that listing, never a Case File id; the answers that are a permutation
    are merged by median rank per candidate, ties by the RRF rank. No valid answer: the RRF order and "text". A model order is cached
    by the profiles' signatures, the words, the prompt version and the model (ids only, never a text). `info` (a dict) receives
    {fallback, cached, valid}."""
    info = {} if info is None else info
    info.update(fallback="", cached=False, valid=0)
    ids = [str(c["case_id"]) for c in cands]
    if len(ids) < 2:
        return ids, "model"  # nothing to order: no call
    key = _order_key(src, cands, words)
    hit = _cache_get(key, ids)
    if hit:
        info["cached"] = True
        return hit, "model"
    texts = [candidate_text(c) for c in cands]
    perms = _permutations(src, cands)

    async def one(perm):
        msgs = _order_messages(src, [texts[i] for i in perm], words)
        ans = await llm.chat("reasoner", msgs, json_schema=ORDER_SCHEMA, max_tokens=60 + 12 * len(perm), temperature=0,
                             purpose="similar_order", audit=audit)
        pos = _as_permutation(ans, len(perm))
        if pos is None:
            raise ValueError("not a permutation of the ids")
        return [perm[p] for p in pos]
    res = await asyncio.gather(*(one(p) for p in perms), return_exceptions=True)
    good = [r for r in res if isinstance(r, list)]
    info["valid"] = len(good)
    if not good:
        errs = sorted({type(r).__name__ for r in res if isinstance(r, BaseException)})
        info["fallback"] = "no valid model order (" + ", ".join(errs) + ")" if errs else "no valid model order"
        return ids, "text"
    ranks = {i: [] for i in range(len(ids))}
    for o in good:
        for r, i in enumerate(o):
            ranks[i].append(r)
    merged = sorted(range(len(ids)), key=lambda i: (statistics.median(ranks[i]), i))
    out = [ids[i] for i in merged]
    try:
        store._write_json(_cache_path(key), {"order": out, "ordered_by": "model", "prompt_version": PROMPT_VERSION, "at": store.now_iso()})
    except OSError as e:
        log.warning("similar: order cache not written (%s)", e)
    return out, "model"


# ---- the quoted lines (research 4.6) ----------------------------------------------------------------------------------------------

def _source(case_id) -> dict | None:
    """One Case File read again now, for checking quotes against their sources: its documents (confirmations applied), board records,
    the current Case summary's sentences and the confirmed draft stage. None for a missing file; a protected id raises."""
    _guard(case_id)
    case = store.get_case(case_id)
    if not isinstance(case, dict):
        return None
    case = {**case, "case_id": case_id}
    _guard(case.get("case_id"))
    st = store.get_state(case_id)
    docs = {str(d.get("doc_id")): d for d in rules.case_docs(case_id, st) if d.get("state") == "ready" and not d.get("dismissed")}
    sents = {}
    for sec in (case_summary.current(st) or {}).get("sections") or []:
        for s in sec.get("sentences") or []:
            if isinstance(s, dict) and s.get("id"):
                sents[(sec.get("id"), s.get("id"))] = str(s.get("text") or "")
    return {"case": case, "pats": _scrub_patterns(case), "docs": docs, "records": {r.get("id"): r for r in _records(st)},
            "sentences": sents, "staging": [s["quote"] for s in _staging(st)]}


def _verified(line, src) -> bool:
    """The stored (scrubbed) line text equals, after grounding.norm, its source read now and scrubbed the same way: a report line at
    its page and offsets, a board record field, a Case summary sentence, the confirmed draft stage. Exact; no fuzzy score."""
    if not src:
        return False
    want = grounding.norm(str(line.get("text") or ""))
    if len(want) < 2:
        return False
    s = line.get("source") if isinstance(line.get("source"), dict) else {}

    def same(text):
        return grounding.norm(scrub(text, src["case"], src["pats"])) == want
    if s.get("doc_id"):
        d = src["docs"].get(str(s["doc_id"]))
        page, start, end = s.get("page"), s.get("start"), s.get("end")
        if not d or not all(isinstance(x, int) and not isinstance(x, bool) for x in (page, start, end)):
            return False
        pages = d.get("pages") or []
        if not 0 <= page < len(pages):
            return False
        text = str((pages[page] or {}).get("text") or "")
        return 0 <= start < end <= len(text) and same(text[start:end])
    if s.get("record"):
        rec = src["records"].get(s["record"])
        return bool(rec) and same(" ".join(str(rec.get(s.get("field") or "") or "").split()))
    if s.get("sentence"):
        return (s.get("section"), s["sentence"]) in src["sentences"] and same(src["sentences"][(s.get("section"), s["sentence"])])
    if s.get("staging"):
        return any(same(q) for q in src["staging"])
    return False


def _carries_id(text, case) -> bool:
    """A text that still names the patient of `case`: an identifier of published._identifiers (whole, any case), a name word as a
    whole word, a number or mixed part of five or more characters, a run of six or more digits, a day-level date."""
    t = str(text or "")
    low = t.lower()
    words = set(re.findall(r"[^\W\d_]+", low))
    for ident in published._identifiers(case):
        il = " ".join(str(ident).lower().split())
        if len(il) >= 3 and il in low:
            return True
        for part in re.split(r"[\s,/]+", il):
            if len(part) < 3:
                continue
            if part.isalpha():
                if part in words:
                    return True
            elif len(part) >= 5 and part in low:
                return True
    return bool(_LONG_DIGITS.search(t) or _DAY_DATE.search(t))


def _numbered(p, prefix) -> dict:
    lines = [l for l in (p or {}).get("lines") or [] if isinstance(l, dict) and l.get("kind") != "decision" and str(l.get("text") or "").strip()]
    return {f"{prefix}{k + 1}": l for k, l in enumerate(lines[:LINES_MAX])}


def _line_label(line, cat) -> str:
    k = line.get("kind")
    if k == "stage":
        return "stage"
    if k == "summary":
        return "since the board"
    if k == "treatment":
        return "treatment"
    return (cat.get(line.get("fact")) or {}).get("label") or str(line.get("fact") or "fact")


def _about(a, b, cat) -> str | None:
    """What a pair is about, or None when the two lines are not the same kind of fact (the model cannot pair unrelated lines)."""
    if a.get("kind") == "decision" or b.get("kind") == "decision":
        return None
    for k, about in (("stage", "stage"), ("treatment", "treatment"), ("summary", "since the board")):
        if a.get("kind") == k and b.get("kind") == k:
            return about
    if a.get("fact") and a.get("fact") == b.get("fact"):
        return (cat.get(a["fact"]) or {}).get("label") or str(a["fact"])
    return None


def _lines_messages(la, lb, cat) -> list:
    def block(d):
        return "\n".join(f"{i} [{_line_label(l, cat)}]: {l['text']}" for i, l in d.items())
    user = f"List A (the current Case File):\n{block(la)}\n\nList B (the past Case File):\n{block(lb)}"
    return [{"role": "system", "content": LINES_SYSTEM}, {"role": "user", "content": user}]


def _empty_picks(dropped=0) -> dict:
    return {"similar": [], "differs": [], "no_reasons": True, "dropped": dropped}


async def pick_lines(src, past, *, sources=None, audit=None) -> dict:
    """The "why similar" (up to SIMILAR_MAX) and "how it differs" (up to DIFFERS_MAX) pairs for one past file: the reasoner picks
    ids from the two numbered lists (decision lines left out of both); code keeps a pair only when both ids exist, both quotes match
    their sources read now, the past line names nobody, a "differs" pair really differs, and both lines are the same kind of fact.
    {similar, differs, no_reasons (fewer than two lines in all), dropped (pairs refused by the checks)}. A model error or an invalid
    answer gives no lines. `sources` caches the re-read files by Case File id."""
    la, lb = _numbered(src, "A"), _numbered(past, "B")
    if not la or not lb:
        return _empty_picks()
    cat = protocol.facts()
    try:
        ans = await llm.chat("reasoner", _lines_messages(la, lb, cat), json_schema=LINES_SCHEMA, max_tokens=300, temperature=0,
                             purpose="similar_lines", audit=audit)
    except Exception as e:  # the model is down or answered no JSON: the card is shown without quoted reasons
        log.warning("similar: lines not picked (%s)", type(e).__name__)
        return _empty_picks()
    if not isinstance(ans, dict) or not isinstance(ans.get("similar", []), list) or not isinstance(ans.get("differs", []), list):
        return _empty_picks()
    sources = {} if sources is None else sources

    async def source(cid):
        if cid not in sources:
            sources[cid] = await asyncio.to_thread(_source, cid)
        return sources[cid]
    s_src, p_src = await source(src["case_id"]), await source(past["case_id"])
    if not p_src:
        return _empty_picks()
    checked: dict = {}

    def ok(key, line, s):
        if key not in checked:
            checked[key] = _verified(line, s)
        return checked[key]
    out = {"similar": [], "differs": []}
    dropped, seen = 0, set()
    for kind in ("similar", "differs"):
        for pair in ans.get(kind) or []:
            a_id = str((pair or {}).get("a") or "").strip().upper() if isinstance(pair, dict) else ""
            b_id = str((pair or {}).get("b") or "").strip().upper() if isinstance(pair, dict) else ""
            a, b = la.get(a_id), lb.get(b_id)
            if not a or not b or a.get("kind") == "decision" or b.get("kind") == "decision":    # (1)
                dropped += 1
                continue
            if not ok(a_id, a, s_src) or not ok(b_id, b, p_src):                                # (2)
                dropped += 1
                continue
            if _carries_id(b["text"], p_src["case"]):                                           # (3)
                dropped += 1
                continue
            about = _about(a, b, cat)
            same = grounding.norm(a["text"]) == grounding.norm(b["text"])
            if about is None or (kind == "differs" and same):                                   # (4)
                dropped += 1
                continue
            if (a_id, b_id) in seen:
                continue
            seen.add((a_id, b_id))
            if len(out[kind]) >= (SIMILAR_MAX if kind == "similar" else DIFFERS_MAX):           # (5)
                continue
            out[kind].append({"about": about, "this": {"text": a["text"], "where": a.get("where_full") or a.get("where") or ""},
                              "past": {"text": b["text"], "where": b.get("where") or ""}})
    return {**out, "no_reasons": len(out["similar"]) + len(out["differs"]) < 2, "dropped": dropped}


# ---- the result card (research 4.7, contract 8.4) ---------------------------------------------------------------------------------

def _stage_where(s) -> str:
    if s.get("kind") == "confirmed_draft":
        return _where("Vaidyx draft stage confirmation", s.get("date"))
    if s.get("kind") == "agreed":
        return _where("Board record", s.get("date"))
    return _where(s.get("doc_title") or "Report", s.get("date"))


def _recorded_stage(p) -> str:
    s = next((x for x in (p or {}).get("stage") or [] if x.get("kind") == "recorded"), None)
    return grounding.norm(s["text"]) if s and s.get("text") else ""


def _matched_by(past, src) -> list:
    out = []
    if past.get("group") and past.get("group") == src.get("group"):
        out.append("cancer group")
    for label, key in (("setting", "setting"), ("age band", "age_band"), ("sex", "sex")):
        if past.get(key) and past.get(key) == src.get(key):
            out.append(label)
    if _recorded_stage(past) and _recorded_stage(past) == _recorded_stage(src):
        out.append("stage as recorded")
    return out


def card(past, src, picks, open_info) -> dict:
    """One past Case File as the screen shows it (contract 8.4, SimilarResult of types.ts): month and year only for its dates, no
    number anywhere, the past board's decisions whole as written, the quoted pairs, the label first."""
    picks = picks if isinstance(picks, dict) else _empty_picks()
    sim, dif = list(picks.get("similar") or []), list(picks.get("differs") or [])
    no_reasons = bool(picks.get("no_reasons", len(sim) + len(dif) < 2))
    mine = {e.get("fact") for k in ("histology", "biomarkers") for e in (src or {}).get(k) or []}

    def value(e):
        where = _where(e.get("doc_title") or "Report", e.get("date"))
        if e.get("confirmed"):
            where += ", confirmed by a clinician"
        return {"fact": e.get("fact") or "", "label": e.get("label") or "", "value": e.get("value") or "", "quote": e.get("quote") or "",
                "where": where, "shared": e.get("fact") in mine}
    markers = [value(e) for e in past.get("biomarkers") or []]
    values = [value(e) for e in past.get("histology") or []] + sorted(markers, key=lambda v: not v["shared"])
    oi = open_info if isinstance(open_info, dict) else {}
    return {
        "case_id": past["case_id"], "cancer": past.get("cancer") or past.get("group_label") or "", "setting": past.get("setting_label") or "",
        "age_band": past.get("age_band") or "", "sex": past.get("sex") or "",
        "stage": [{"text": s.get("text") or "", "kind": s.get("kind") or "", "label": s.get("label") or "", "quote": s.get("quote") or "",
                   "where": _stage_where(s)} for s in past.get("stage") or []],
        "values": values,
        "decisions": [{"record_id": d.get("record_id") or "", "when": d.get("when") or "", "outcome": d.get("outcome") or "",
                       "outcome_label": d.get("outcome_label") or "", "intent": d.get("intent") or "", "intent_label": d.get("intent_label") or "",
                       "text": d.get("text") or "", "modalities": [str(m) for m in d.get("modalities") or []],
                       "stage_as_agreed": d.get("stage_as_agreed") or ""} for d in past.get("decisions") or []],
        "outcome_so_far": {"sentences": [{"text": s.get("text") or "", "where": s.get("where") or ""}
                                         for s in (past.get("outcome_so_far") or {}).get("sentences") or []],
                           "later_records": (past.get("outcome_so_far") or {}).get("later_records") or ""},
        "similar": sim, "differs": dif,
        "matched_by": _matched_by(past, src or {}) if no_reasons else None, "no_reasons": no_reasons,
        "open": {"how": oi.get("how") or "refused", "reason": oi.get("reason") or "", "via": oi.get("via") or ""},
        "label": LABEL}


def _weaker(c) -> bool:
    return bool(c.get("no_reasons")) and (c.get("matched_by") or []) == ["cancer group"]


# ---- opening a result (research 4.10, contract 8.3) ---------------------------------------------------------------------------------

def open_info(rl, past_case_id, this_case_id) -> dict:
    """How this person may open a past Case File: FULL, REQUESTS or READ (a window already open) is "normal"; no access but a doctor who
    may open it with a reason is "with_reason" (reason and via pre-filled; the break-glass route audits itself); else "refused". A past
    file that is no longer eligible (archived, unlisted, protected, missing) raises ValueError("not_found")."""
    pid = str(past_case_id or "").strip()
    if not pid or _protected(pid) or pid == str(this_case_id or ""):
        raise ValueError("not_found")
    try:
        store.safe_id(pid)
    except ValueError:
        raise ValueError("not_found")
    past = store.get_case(pid)
    if not isinstance(past, dict) or _protected(past.get("case_id")):
        raise ValueError("not_found")
    past = {**past, "case_id": pid}
    if not eligible(past, store.get_state(pid), exclude=(this_case_id,)):
        raise ValueError("not_found")
    out = {"how": "refused", "scope": None, "reason": "", "via": "", "label": LABEL}
    sc = access.scope(rl, past)
    if sc in (access.FULL, access.REQUESTS, access.READ):
        out.update(how="normal", scope=sc)
    elif access.may_open_with_reason(rl, past):
        out.update(how="with_reason", reason=f"similar to Case File {this_case_id}", via=f"similar:{this_case_id}")
    return out


# ---- the GET (contract 8.3) ----------------------------------------------------------------------------------------------------------

def _recent(case_id, n=5) -> list:
    evs = [e for e in store.read_audit(case_id, limit=5000) if e.get("kind") == "similar_search" and e.get("fallback") != "bad_words"]
    return [{"words": str(e.get("words") or ""), "at": str(e.get("ts") or ""), "by_name": _display(e.get("by")) or str(e.get("by") or "")}
            for e in reversed(evs[-n:])]


def info(case_id, rl) -> dict:
    """Whether a search is possible here and the last five searches of this file (newest first)."""
    out = {"available": False, "reason": "", "label": LABEL, "order_note": ORDER_NOTE_MODEL, "model_line": MODEL_LINE,
           "cancer_group": "", "group_label": "", "searches": []}
    if _protected(case_id):
        out["reason"] = PROTECTED_REASON
        return out
    case = store.get_case(case_id)
    if not isinstance(case, dict):
        raise ValueError("not_found")
    case = {**case, "case_id": case_id}
    if access.is_protected(case):
        out["reason"] = PROTECTED_REASON
        return out
    out["cancer_group"], out["group_label"] = group(case) or "", group_label(case)
    if not out["cancer_group"]:
        out["reason"] = NO_GROUP_REASON
    elif (rl or {}).get("vaidyx_admin"):
        out["reason"] = ADMIN_REASON
    elif access.scope(rl, case) != access.FULL:
        out["reason"] = SCOPE_REASON
    else:
        out["available"] = True
    out["searches"] = _recent(case_id)
    return out


# ---- the search (contract 8.4 and 8.5) ----------------------------------------------------------------------------------------------

async def search(case_id, words, user, rl) -> dict:
    """The SimilarResponse for this Case File and the doctor's words: the candidates (same cancer group, BM25 plus dense vectors, off
    the loop), the reasoner's order, the quoted lines of the first SHOWN (concurrently), the cards, all under SEARCH_BUDGET_S (a late
    order falls back to the text order; late lines give cards without quoted reasons). Every search is audited, an empty or failed
    one too: this file (`similar_search`, the words and counts, a hash of the shown ids), each shown file (`similar_shown`) and the
    organisation log (a hash of the words, the shown ids). Raises published.PublishedError for words that carry an identifier."""
    _guard(case_id)
    case = store.get_case(case_id)
    if not isinstance(case, dict):
        raise ValueError("not_found")
    case = {**case, "case_id": case_id}
    _guard(case.get("case_id"))
    t0 = time.monotonic()
    au = store.auditor(case_id)
    ev = {"by": user, "words": "", "cancer_group": "", "n_candidates": 0, "n_results": 0, "n_weaker": 0, "ordered_by": "", "fallback": "",
          "shown_hash": "", "dropped_lines": 0, "prompt_version": PROMPT_VERSION, "seconds": 0}
    shown: list = []
    try:
        raw = " ".join(str(words or "").split())
        try:
            w = published.check_terms(case, raw)[:WORDS_MAX] if raw else ""
        except published.PublishedError:
            ev["fallback"] = "bad_words"  # the refused words are never written down
            raise
        ev["words"] = w

        def gather_candidates():
            src = query_profile(case_id)
            res = candidates(case_id, w, profile=src)
            cands = []
            for c in res.get("candidates") or []:
                cid = c["case_id"]
                p = None if _protected(cid) else _load_profile(cid)
                if p and p.get("case_id") == cid:
                    cands.append(p)
            return src, res, cands
        src, res, cands = await asyncio.to_thread(gather_candidates)
        ev["cancer_group"], ev["n_candidates"] = res.get("group") or "", len(cands)
        note = res.get("note") or ""
        oinfo: dict = {}
        rrf = [c["case_id"] for c in cands]
        try:
            ids, ordered_by = await asyncio.wait_for(order(src, cands, w, info=oinfo, audit=au), max(1.0, SEARCH_BUDGET_S - (time.monotonic() - t0)))
        except asyncio.TimeoutError:
            ids, ordered_by, oinfo["fallback"] = rrf, "text", "the model ordering took too long"
        except Exception as e:  # the honest fallback: the text order
            ids, ordered_by, oinfo["fallback"] = rrf, "text", f"model ordering failed ({type(e).__name__})"
        ev["ordered_by"], ev["fallback"] = ordered_by, oinfo.get("fallback") or ""
        by_id = {c["case_id"]: c for c in cands}
        top = [by_id[i] for i in ids if i in by_id][:SHOWN]
        sources = {case_id: await asyncio.to_thread(_source, case_id)}  # this file read once for every pair check
        left = SEARCH_BUDGET_S - (time.monotonic() - t0)
        picks = [_empty_picks() for _ in top]
        try:
            got = await asyncio.wait_for(asyncio.gather(*(pick_lines(src, p, sources=sources, audit=au) for p in top), return_exceptions=True),
                                         max(1.0, left))
            picks = [g if isinstance(g, dict) else _empty_picks() for g in got]
        except asyncio.TimeoutError:
            note = " ".join(x for x in (note, LINES_LATE) if x)
            ev["fallback"] = "; ".join(x for x in (ev["fallback"], "the quoted lines took too long") if x)
        ev["dropped_lines"] = sum(int(p.get("dropped") or 0) for p in picks)
        results, weaker = [], []
        for p, pk in zip(top, picks):
            try:
                oi = open_info(rl, p["case_id"], case_id)  # eligible again on live data, at card time
            except ValueError:
                continue
            c = card(p, src, pk, oi)
            (weaker if _weaker(c) else results).append(c)
        shown = [c["case_id"] for c in results + weaker]
        ev["n_results"], ev["n_weaker"] = len(results), len(weaker)
        return {"label": LABEL, "ordered_by": ordered_by, "order_note": ORDER_NOTE_MODEL if ordered_by == "model" else ORDER_NOTE_TEXT,
                "model_line": MODEL_LINE, "cancer_group": res.get("group") or "", "group_label": res.get("group_label") or "", "words": w,
                "note": note, "results": results, "weaker": weaker}
    except BaseException as e:
        if not ev["fallback"]:
            ev["fallback"] = f"search failed ({type(e).__name__})"
        raise
    finally:
        ev["seconds"] = round(time.monotonic() - t0, 2)
        ev["shown_hash"] = _sha(",".join(shown))[:16] if shown else ""
        try:
            store.audit(case_id, {"kind": "similar_search", **ev})
            for sid in shown:
                store.audit(sid, {"kind": "similar_shown", "by": user, "from": case_id})
            org.audit("similar_search", user, case_id=case_id, words_hash=_sha(ev["words"])[:12] if ev["words"] else "", shown=shown,
                      n_results=ev["n_results"])
        except Exception as e:  # an audit write that fails is logged; it never hides the search's own error
            log.warning("similar: search audit not written (%s)", e)
