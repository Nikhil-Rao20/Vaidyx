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

from . import access, config, dates, decision_record, identity, protocol, published, rules, search, store
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
        f = cache / (hashlib.sha1((search.EMBED_MODEL + "similar:" + t).encode()).hexdigest() + ".npy")
        if f.exists():
            try:
                vecs[i] = np.load(f)
                continue
            except (OSError, ValueError):
                pass
        todo.append((i, f))
    for k in range(0, len(todo), EMBED_BATCH):
        part = todo[k:k + EMBED_BATCH]
        new = search._embed([texts[i] for i, _ in part])
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
    store._write_json(_index_json(), {"version": VERSION, "embed_model": search.EMBED_MODEL, "chunks": chunks, "signature": sig,
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
    return meta.get("version") != VERSION or meta.get("embed_model") != search.EMBED_MODEL


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
    for t in set(search.tokenize(q)):
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
    tok = [search.tokenize(chunks[i]["text"]) for i in rows]
    q = src.get("text") or ""
    if w:
        q = f"{q} Doctor's words: {w}"
    arrays = [("lex", _bm25(tok, q))]
    if w:
        arrays.append(("lex", _bm25(tok, w)))
    if m.shape[0] == len(chunks) and m.size:
        qv = np.asarray(search._embed([q], prefix=QUERY_PREFIX)[0], dtype=np.float32)
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
