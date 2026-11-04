"""The Case summary (night-v3 item 3.3, owner decision D3): after the first board decision it replaces the pre-board summary as the main
summary and is written again after every later decision. Every version is kept; the owner's consultant reviews and edits it.

Storage: st["artefacts"]["case_summary"] = {"current": n, "case_id": id, "versions": [v1, v2, ...]}, written through store.save_state.
Five sections (six when the board kept discussion notes), in this order:
  presentation  "Presentation and diagnosis"                 the reasoner over the records dated up to the first board, plus
                                                             summary.fill_from_facts for the presentation and investigation facts
  stage         "Stage"                                      code only: the stage as recorded in a signed report, a Vaidyx draft stage
                                                             only after a doctor confirmed it, the stage as agreed by each board
  rounds        "Board rounds"                               code only: one block per board record, oldest first
  discussion    "What was said at the board"                 only when the meetings of the board records kept AI discussion notes for
                (meetings-v2 item 5.4)                       this Case File (meeting_notes, item 5.3): the reasoner over those notes,
                                                             given as what was said at the board, attributed to the speakers; never
                                                             a decision, a plan or advice in Vaidyx's own voice
  since         "Treatment and follow-up since the board"    the reasoner over the records dated after the first board, plus the
                                                             treatment facts of those records and the HIS encounters after the board
  status        "Current status and open actions"            code only: open and closed board actions, the patient told, next review
Every sentence cites a record line (qa.verify, word for word), a board-record field, an action, the stage confirmation or a member's card
(the exact stored text, checked by verify_field), a note line of the board discussion (kind "said": {meeting_id, line_id, speaker,
speaker_name, department, at, board_date, quote}; the line still in that meeting's notes for this Case File and the quote word for word in
what the speaker said, verify_said), or is code (code: true). A model sentence that fails a check is kept in `removed` with its reason.
Code-built sentences quote the stored field itself, so nothing is paraphrased. No diagnosis, no stage computation, no interpretation, no
treatment advice, no prognosis. The model is the reasoner (non-medical); "AI draft, not reviewed" until reviewed. Every screen titles it
TITLE ("Summary after the board", owner decision D14) beside the pre-board summary (TITLE_BEFORE, "Summary before the board"); it is
written again when the discussion notes of one of its meetings are built or edited (on_notes_changed, called by meeting_notes).

The consultant's edits are never overwritten: a rebuild carries an edited sentence forward with its edited text; a different model
sentence for the same place is kept under edited.suggested. Never for a protected Case File (config.PROTECTED_CASES)."""
import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import threading
import time

from . import config, dates, decision_record, grounding, guardrails, llm, protocol, qa, rules, search, store, summary

log = logging.getLogger("tumour_board")

ART = "case_summary"
SECTIONS = [("presentation", "Presentation and diagnosis"), ("stage", "Stage"), ("rounds", "Board rounds"),
            ("discussion", "What was said at the board"),
            ("since", "Treatment and follow-up since the board"), ("status", "Current status and open actions")]
TITLES = dict(SECTIONS)
MODEL_SECTIONS = ("presentation", "discussion", "since")
TITLE = "Summary after the board"            # the Case summary's title on every screen (meetings-v2 item 5.4, owner decision D14)
TITLE_BEFORE = "Summary before the board"    # the pre-board summary's title beside it
CONTEXT_BUDGET = 40000
CLIP = 600
REVIEW_STATUSES = ("reviewed", "flagged", "ai_draft")
MAX_EDIT = 1000

NOTHING = {
    "presentation": "Presenting complaint and diagnosis are not documented in the records of this Case File.",
    "stage": "No stage is recorded in a signed report and none has been confirmed. Cannot stage.",
    "status": "No board actions are open.",
}
NOTHING_SINCE = "No records dated after the board decision of {date} have been added yet."
NOTHING_CHECKED_SINCE = "Records dated after the board decision of {date} are in the Case File, but no statement could be checked against them."
CODE_EDIT = "This sentence quotes the record itself and cannot be edited; correct the board record or the report instead."
FIXED_EDIT = "This sentence is written by Vaidyx when nothing is documented and cannot be edited."

REASONS = {**qa.REASONS, "relative_date": "a relative date (for example \"last month\") cannot be checked against the record",
           "not_given": "the cited record was not among the records given for this section",
           "no_citation": "the sentence cites no note line of the board discussion",
           "not_attributed": "the sentence does not say who spoke at the board",
           "said_as_decision": "what was said at the board is written as a decision or a plan",
           "names": "a name or term of the sentence is not in the quoted words and is not the speaker's"}

# "last month", "two weeks ago", "recently", "yesterday": a date the record cannot confirm (the reader does not know "when" it was written)
RELATIVE = re.compile(r"\b(?:last|past|previous|next|this|coming)\s+(?:\d+\s+|few\s+|several\s+)?(?:day|week|fortnight|month|year)s?\b|"
                      r"\b(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|few|several|some|a\s+few)\s+"
                      r"(?:day|week|fortnight|month|year)s?\s+(?:ago|back|later|after|afterwards|earlier|before|following)\b|"
                      r"\bthe\s+(?:following|next|previous|preceding|same)\s+(?:day|week|fortnight|month|year|morning|evening|night)\b|"
                      r"\bthe\s+(?:day|week|month)\s+(?:after|before)\b|\brecently\b|\byesterday\b|\btoday\b|\btomorrow\b|"
                      r"\bearlier this\b|\blater this\b", re.I)

SYS_EXTRA = ("Write only about the documents given. One fact per sentence where possible. Cite each sentence with the document id and the "
             "exact line that carries the value. Keep each quote short. Dates as in the record, never relative. If nothing is documented, "
             "return no sentence.")
SINCE_EXTRA = "Say when a report is draft or superseded."
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "text": {"type": "string"},
        "citations": qa.ANSWER_SCHEMA["properties"]["statements"]["items"]["properties"]["citations"]},
        "required": ["text", "citations"]}}},
    "required": ["sentences"]}

PRESENTATION_FACTS = summary.SECTION_FACTS["presentation"] + summary.SECTION_FACTS["investigations"]
SINCE_FACTS = ("treatment_received", "treatment_completion_date", "lesion_size", "nodal_findings", "distant_findings", "recorded_stage")
STATUS_COMM = ("patient_informed_date", "informed_by")  # the communication fields the status section shows
ROUND_COMM = ("intent", "intent_as_recorded", "trial_considered", "trial_name")  # those the board rounds show


# ---- small helpers -------------------------------------------------------------------------------------------------------------

def dmy(iso) -> str:
    return decision_record.dmy(iso)


def _fold(s) -> str:
    return " ".join(str(s if s is not None else "").split())


def _clip(s, n=CLIP) -> str:
    s = _fold(s)
    return s if len(s) <= n else s[:n].rstrip() + "..."


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def today() -> str:
    """Today, ISO (followup._today, so tests can move the day)."""
    from . import followup
    return followup._today().isoformat()


def _name(user) -> str:
    try:
        from .slots import display_name
        return display_name(user) or str(user or "")
    except Exception:
        return str(user or "")


def _rec_date(rec) -> str:
    return str((rec or {}).get("board_date") or (rec or {}).get("recorded_at") or "")[:10]


def records(st) -> list:
    """The board records, oldest first (board date, then the time recorded)."""
    recs = [b for b in (st or {}).get("board_records") or [] if isinstance(b, dict) and b.get("id")]
    return sorted(recs, key=lambda b: (_rec_date(b), str(b.get("recorded_at") or "")))


def _outcome(rec) -> str:
    return str(rec.get("outcome_type") or rec.get("outcome") or "decision")


def _artefact(st):
    a = ((st or {}).get("artefacts") or {}).get(ART)
    return a if isinstance(a, dict) and isinstance(a.get("versions"), list) else None


def current(st) -> dict | None:
    a = _artefact(st)
    if not a or not a["versions"]:
        return None
    n = a.get("current") or len(a["versions"])
    return next((v for v in a["versions"] if v.get("n") == n), a["versions"][-1])


def _version(st, n) -> dict:
    a = _artefact(st)
    v = next((x for x in (a or {}).get("versions") or [] if x.get("n") == n), None)
    if v is None:
        raise KeyError(f"No version {n} of the Case summary")
    return v


def all_sentences(version) -> list:
    """Every sentence of a version, the board-round blocks included, in section order."""
    out = []
    for sec in (version or {}).get("sections") or []:
        out.extend(sec.get("sentences") or [])
        for b in sec.get("blocks") or []:
            out.extend(b.get("sentences") or [])
    return out


# ---- checks ----------------------------------------------------------------------------------------------------------------------

def verify_field(quote, stored_text, sentence=None) -> bool:
    """A board-field (or action, stage confirmation, card) citation: the normalised quote is in the normalised stored text, and every
    number of the sentence (when given) is in the quote."""
    q, t = grounding.norm(str(quote or "")), grounding.norm(str(stored_text or ""))
    if not q or q not in t:
        return False
    if sentence is not None and qa._missing_numbers(str(sentence), [{"quote": str(quote), "doc_title": "", "date": ""}]):
        return False
    return True


def _numbers_ok(text, cites) -> bool:
    """Every number of a code sentence is in one of its quotes (or a record title, a board date, a due or closing time it cites)."""
    meta = [{"quote": str(c.get("quote") or ""), "doc_title": str(c.get("doc_title") or ""),
             "date": " ".join(str(c.get(k) or "") for k in ("date", "board_date", "at"))} for c in cites]
    return not qa._missing_numbers(text, meta) if meta else not grounding.numbers(text)


def _removed(item, reason, detail, where):
    return {"text": (item or {}).get("text") or "", "reason": reason, "reason_label": REASONS[reason], "detail": detail, "where": where,
            "citations": [{"doc_id": c.get("doc_id") or "", "quote": (c.get("quote") or "")[:400],
                           **({"note_line": str(c.get("note_line") or c.get("line_id"))} if c.get("note_line") or c.get("line_id") else {})}
                          for c in (item or {}).get("citations") or [] if isinstance(c, dict)]}


def _check_model(case_id, items, allowed, where, removed, issues, near):
    """The model's sentences that pass: no relative date, cite a record given for the section, the quote found word for word with every
    number in it (qa.verify), and the clinical scope guardrail. Every drop is kept with its reason."""
    pre = []
    for x in items or []:
        if not isinstance(x, dict) or not _fold(x.get("text")):
            continue
        x = {"text": _fold(x.get("text")), "citations": [c for c in x.get("citations") or [] if isinstance(c, dict)]}
        m = RELATIVE.search(x["text"])
        if m:
            removed.append(_removed(x, "relative_date", f"\"{m.group(0)}\" is a relative date", where))
            continue
        cites = [c for c in x["citations"] if str(c.get("doc_id") or "").strip() in allowed]
        if x["citations"] and not cites:
            removed.append(_removed(x, "not_given", ", ".join(dict.fromkeys(str(c.get("doc_id") or "(no id)") for c in x["citations"])), where))
            continue
        pre.append({**x, "citations": cites})
    ok, drops = qa.verify(case_id, pre, near_match=near)
    removed.extend({**d, "where": where} for d in drops)
    keep = []
    for s in ok:
        iss = guardrails.scan_output(s["text"], quotes=guardrails.statement_quotes(s))  # advice words only outside the cited quotes (review E, S1)
        if iss:
            issues.extend(iss)
            removed.append({**qa.removed_item(s, "guardrail", "; ".join(dict.fromkeys(i["reason"] for i in iss))), "where": where})
        else:
            s["text"] = _ISO_DATE.sub(lambda m: dmy(m.group(0)), s["text"])  # a date the model wrote as YYYY-MM-DD reads DD/MM/YYYY; checked before, the quote untouched
            keep.append(s)
    return keep


_ISO_DATE = re.compile(r"\b(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")


def _record_line(case_id, text, doc_id, quote):
    """A code sentence citing a record line, checked by qa.verify like a model sentence; None when the quote is not found."""
    text = _END.sub(r'\1"', text)
    ok, _ = qa.verify(case_id, [{"text": text, "citations": [{"doc_id": doc_id, "quote": quote}]}])
    return ok[0] if ok else None


def _code(sid, text, cites, removed=None, **extra):
    """A code-built sentence. Each board, action, staging or card citation must hold its stored text (verify_field) and every number of
    the sentence must be in its quotes; one that does not is left out (kept in removed)."""
    for c in cites:
        if c.get("kind") and "stored" in c:
            if not verify_field(c["quote"], c.pop("stored")):
                if removed is not None:
                    removed.append(_removed({"text": text, "citations": []}, "quote_not_found", f"{c.get('field')} does not hold the quoted text", "code"))
                return None
    text = _END.sub(r'\1"', text)  # 'recorded: "Surgery first."' never ends '."."' (Phase 3 review N5)
    if not _numbers_ok(text, cites):
        if removed is not None:
            removed.append(_removed({"text": text, "citations": []}, "number_not_in_quote", "a number is not in the quoted field", "code"))
        return None
    return {"id": sid, "text": text, "citations": cites, "code": True, **extra}


_END = re.compile(r'([.!?])"\.$')
# the short words for a communication flag of the latest record ("Not yet recorded: the date the patient was told.")
FLAG_WORDS = {"patient_informed_date": "the date the patient was told", "key_worker": "the key worker", "trial_considered": "whether a clinical trial was considered",
              "intent_as_recorded": "the treatment intent", "consent_recorded": "the patient's consent to the discussion"}


def _lower_first(s) -> str:
    """"As recorded in a report" -> "as recorded in a report"; "A Vaidyx draft stage..." keeps "Vaidyx"."""
    s = str(s or "")
    return s[:1].lower() + s[1:]


def _fixed(sid, text):
    return {"id": sid, "text": text, "citations": [], "code": True, "fixed": True}


def _stored(rec, field):
    v = rec.get(field)
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if not isinstance(x, dict))
    return "" if v is None else str(v)


def _bcite(rec, field, quote=None, stored=None):
    q = _stored(rec, field) if quote is None else str(quote)
    return {"kind": "board", "board_record": rec["id"], "version": rec.get("version", 1), "field": field, "quote": q,
            "board_date": _rec_date(rec), "stored": _stored(rec, field) if stored is None else stored}


def _acite(a, field, quote=None):
    v = a.get(field)
    q = str(v or "") if quote is None else str(quote)
    return {"kind": "action", "action": a.get("id"), "board_record": a.get("board_record"), "field": field, "quote": q,
            **({"at": str(v)} if field in ("completed", "due") else {}), "stored": str(v or "")}


# ---- documents and context ------------------------------------------------------------------------------------------------------

def _docs(case_id, st):
    docs = [d for d in rules.case_docs(case_id, st) if d.get("state") == "ready" and not d.get("dismissed")]
    return sorted(docs, key=lambda d: dates.doc_dates(d)["sort"])


def _split(docs, first_date):
    """(records dated up to the first board, records dated after it); an undated record counts as before the board."""
    pre, post = [], []
    for d in docs:
        ev = dates.doc_dates(d)["event"]
        (post if ev and first_date and ev > first_date else pre).append(d)
    return pre, post


def _context(docs, budget=CONTEXT_BUDGET):
    """The documents in date order, each labelled as search.context_for labels them, whole, until the budget is used."""
    parts, used, ids, left = [], 0, [], 0
    for d in docs:
        blk = search._doc_block(d, "\n".join(p.get("text") or "" for p in d.get("pages") or []))
        if used + len(blk) > budget:
            left += 1
            continue
        parts.append(blk); used += len(blk) + 2; ids.append(d["doc_id"])
    return "\n\n".join(parts), ids, {"documents": len(ids), "left_out": left, "characters": used}


def _sid(sec, n):
    return f"s{sec}-{n}"


# ---- the five sections -------------------------------------------------------------------------------------------------------------

def _fill(sentences, facts, ids, cat):
    """summary.fill_from_facts for the given fact ids, into one list of sentences."""
    want = {k: v for k, v in facts.items() if k in ids}
    groups = [{"id": sid, "sentences": sentences} for sid, fids in summary.SECTION_FACTS.items() if set(fids) & set(ids)]
    # fill_from_facts reads summary.SECTION_FACTS by section id; the groups share one list, and only the facts asked for are offered
    k = len(sentences)
    added = summary.fill_from_facts(groups, want, cat) if groups else 0
    for x in sentences[k:]:  # the record's date as DD/MM/YYYY on screen (the value itself is never touched)
        x["text"] = _SOURCE_DATE.sub(lambda m: ", " + dmy(m.group(1)) + m.group(2), x["text"])
    return added


_SOURCE_DATE = re.compile(r", (\d{4}-\d{2}-\d{2})((?:; no quote)?\)\.)$")  # the record's date closing the bracket (titles may hold brackets)


def _finish_model_section(key, sentences):
    out = []
    for i, s in enumerate(sentences, 1):
        s = dict(s)
        s["id"] = _sid(key, i)
        if not s.get("citations"):
            s["code"] = True
        out.append(s)
    return out


def stage_section(case_id, st, facts, recs, removed):
    out = []
    n = 0

    def add(s):
        nonlocal n
        if s:
            n += 1
            s["id"] = _sid("stage", n)
            out.append(s)
    cands = [c for c in (facts.get(f, {}).get("current") for f in ("recorded_stage", "figo_stage")) if c and c.get("verification") in rules.VERIFIED]
    rep = max(cands, key=lambda c: (c.get("date") or "", c.get("report_date") or ""), default=None)
    rep_line = None
    if rep:
        when = f" of {dmy(rep['date'])}" if rep.get("date") else ""
        if rep.get("confirmed_by") or not rep.get("quote"):
            rep_line = {"text": f"The {rep['doc_title']}{when} records the stage as \"{rep['value']}\" (confirmed by {rep.get('confirmed_by') or 'a clinician'}; no quote).",
                        "citations": [], "code": True, "from_fields": True}
        else:
            rep_line = _record_line(case_id, f"The {rep['doc_title']}{when} records the stage as \"{rep['value']}\".", rep["doc_id"], rep["quote"])
            if rep_line:
                rep_line["code"] = True
        add(rep_line)
    d = st.get("staging") if isinstance(st.get("staging"), dict) else None
    if d and isinstance(d.get("confirmed"), dict) and d["confirmed"].get("at") and not d.get("rejected") and d.get("status") == "staged":
        comps = " ".join(str((d.get("components") or {}).get(k, {}).get("cat") or "") for k in ("T", "N", "M")).strip()
        stage_text = ", ".join(x for x in (comps, f"stage {d['stage']}" if d.get("stage") else "") if x)
        c = d["confirmed"]
        by = c.get("by_name") or c.get("by") or "a doctor"
        add(_code("", f"Vaidyx draft stage, confirmed by {by} on {dmy(c['at'])}: {stage_text}.",
                  [{"kind": "staging", "field": "confirmed", "quote": stage_text, "by": by, "at": c["at"], "stored": stage_text}], removed, draft_stage=True))
    for rec in recs:
        agreed = _fold(rec.get("stage_as_agreed"))
        if not agreed:
            continue
        src = decision_record.choice_label("stage_source", rec.get("stage_source")) if rec.get("stage_source") else ""
        cites = [_bcite(rec, "stage_as_agreed")] + ([_bcite(rec, "stage_source")] if src else [])
        add(_code("", f"The board of {dmy(_rec_date(rec))} recorded the stage as agreed: \"{agreed}\"" + (f" ({_lower_first(src)})." if src else "."), cites, removed))
        if rep and _stage_key(rep["value"]) != _stage_key(agreed):
            cites = list(rep_line["citations"]) if rep_line else []
            add(_code("", f"The stage recorded in the {rep['doc_title']} (\"{rep['value']}\") differs from the stage as agreed by the board on {dmy(_rec_date(rec))}.",
                      cites + [_bcite(rec, "stage_as_agreed")], removed, flags=["stage differs"]))
    if not out:
        add(_fixed("", NOTHING["stage"]))
    return {"id": "stage", "title": TITLES["stage"], "sentences": out, "built_by": "code"}


def _stage_key(s) -> str:
    return re.sub(r"[\s,;]+|\bstage\b", "", grounding.norm(str(s or "")))


def _question(case_id, facts, on_or_before):
    """The Case File's documented question for the board as of that board date (the newest verified line dated on or before it)."""
    hist = [e for e in (facts.get("clinical_question") or {}).get("history") or []
            if e.get("verification") in rules.VERIFIED and e.get("quote") and (not e.get("date") or e["date"] <= on_or_before) and not e.get("superseded")]
    if not hist:
        return None
    e = hist[-1]
    s = _record_line(case_id, f"The question put to the board, as documented: \"{_clip(e['value'], 300)}\".", e["doc_id"], e["quote"])
    if s:
        s["code"] = True
    return s


def _cards(rec, case_id) -> list:
    mid = rec.get("session")
    if not mid:
        return []
    try:
        from . import meetings
        s = meetings.get(mid) or {}
    except Exception:
        return []
    got = ((s.get("cards") or {}).get(case_id) or {})
    return [(u, c) for u, c in got.items() if isinstance(c, dict)]


def round_block(case_id, st, rec, facts, removed) -> dict:
    rid = rec["id"]
    out = []

    def add(field, s):
        if s:
            s["id"] = f"r{rid}-{field}"
            out.append(s)
    date = _rec_date(rec)
    oc = _outcome(rec)
    add("date", _code("", f"Tumour Board of {dmy(date)}.", [_bcite(rec, "board_date", date, stored=date)], removed))
    if oc == "decision":
        add("question", _question(case_id, facts, date))
    add("outcome", _code("", f"Outcome as recorded: {decision_record.OUTCOMES.get(oc, oc)}.", [_bcite(rec, "outcome_type", oc, stored=oc)], removed))
    if oc == "deferred":
        aw = _fold(rec.get("awaited")) or _fold(rec.get("deferred_reason"))
        if aw:
            f = "awaited" if _fold(rec.get("awaited")) else "deferred_reason"
            frm = _fold(rec.get("awaited_from"))
            cites = [_bcite(rec, f, aw)] + ([_bcite(rec, "awaited_from")] if frm and f == "awaited" else [])
            add("awaited", _code("", f"Awaited, as recorded: \"{_clip(aw)}\"" + (f" from {frm}." if frm and f == "awaited" else "."), cites, removed))
    elif oc == "referred":
        if _fold(rec.get("referred_to")):
            add("referred_to", _code("", f"Referred to, as recorded: \"{_clip(rec['referred_to'])}\".", [_bcite(rec, "referred_to")], removed))
    elif oc == "not_discussed":
        if rec.get("not_discussed_reason"):
            add("not_discussed_reason", _code("", f"Why not discussed, as recorded: {decision_record.choice_label('not_discussed_reason', rec['not_discussed_reason'])}.",
                                              [_bcite(rec, "not_discussed_reason")], removed))
    elif oc == "decision":
        _decision_lines(case_id, st, rec, add, removed)
    c = rec.get("corrected")
    if isinstance(c, dict) and c.get("at"):
        row = next((v for v in rec.get("versions") or [] if v.get("version") == c.get("version")), {})
        reason = _fold(c.get("reason"))
        by = c.get("by_name") or c.get("by") or "a consultant"
        quote = reason or str(row.get("reason") or "")
        cite = {"kind": "board", "board_record": rid, "version": c.get("version"), "field": "versions", "quote": quote, "at": c["at"],
                "board_date": date, "stored": " ".join(str(x) for x in (row.get("reason"), c.get("reason")) if x) or quote}
        text = f"Corrected on {dmy(c['at'])} by {by}" + (f": {reason}." if reason else ".")
        add("corrected", _code("", text, [cite] if quote else [{**cite, "quote": c["at"], "stored": c["at"]}], removed))
    return {"record": rid, "version": rec.get("version", 1), "date": date, "outcome": oc, "sentences": out}


def _decision_lines(case_id, st, rec, add, removed):
    def quoted(field, lead):
        v = rec.get(field)
        if _fold(v):
            add(field, _code("", f"{lead}: \"{_clip(v)}\".", [_bcite(rec, field)], removed))
    quoted("decision_text", "Decision as recorded")
    quoted("rationale", "Rationale as recorded")
    intent = rec.get("intent") or rec.get("intent_as_recorded")
    if intent:
        f = "intent" if rec.get("intent") else "intent_as_recorded"
        add("intent", _code("", f"Treatment intent as recorded: {decision_record.choice_label('intent', intent)}.", [_bcite(rec, f)], removed))
    quoted("intent_as_stated", "Intent, in the board's words")
    if rec.get("modalities"):
        add("modalities", _code("", f"Modalities as recorded: {decision_record.choice_label('modalities', rec['modalities'])}.", [_bcite(rec, "modalities")], removed))
    quoted("sequence", "Sequence as recorded")
    quoted("alternatives_discussed", "Alternatives discussed, as recorded")
    rows = [x for x in rec.get("concerns") or [] if isinstance(x, dict) and _fold(x.get("text"))]
    for i, x in enumerate(rows, 1):
        who = _fold(x.get("by")) or "A member"
        add(f"concerns-{i}", _code("", f"{who} recorded a view: \"{_clip(x['text'])}\".",
                                   [{**_bcite(rec, "concerns", x["text"], stored=x["text"]), "row": i}], removed))
    if not rows and _fold(rec.get("divergent_opinions")):
        quoted("divergent_opinions", "Divergent views as recorded")
    if _fold(rec.get("stage_as_agreed")):
        src = decision_record.choice_label("stage_source", rec.get("stage_source")) if rec.get("stage_source") else ""
        add("stage_as_agreed", _code("", f"Stage as agreed by the board: \"{_fold(rec['stage_as_agreed'])}\"" + (f" ({_lower_first(src)})." if src else "."),
                                     [_bcite(rec, "stage_as_agreed")] + ([_bcite(rec, "stage_source")] if src else []), removed))
    if rec.get("trial_considered"):
        add("trial_considered", _code("", f"Clinical trial considered: {decision_record.choice_label('trial_considered', rec['trial_considered'])}.",
                                      [_bcite(rec, "trial_considered")], removed))
    quoted("trial_name", "Trial, as recorded")
    if rec.get("referrals"):
        txt = decision_record.value_text("referrals", rec["referrals"])
        if txt:
            add("referrals", _code("", f"Referrals as recorded: {txt}.", [_bcite(rec, "referrals", txt, stored=txt)], removed))
    if _fold(rec.get("next_step")):
        nd = rec.get("next_step_date")
        add("next_step", _code("", f"Next step as recorded: \"{_clip(rec['next_step'])}\"" + (f", by {dmy(nd)}." if nd else "."),
                               [_bcite(rec, "next_step")] + ([_bcite(rec, "next_step_date")] if nd else []), removed))
    if rec.get("next_review"):
        add("next_review", _code("", f"Next review as recorded: {dmy(rec['next_review'])}.", [_bcite(rec, "next_review")], removed))
    quoted("next_review_trigger", "Or re-discussion, as recorded")
    if _fold(rec.get("responsible_doctor")):
        add("responsible_doctor", _code("", f"Responsible clinician as recorded: {_fold(rec['responsible_doctor'])}.", [_bcite(rec, "responsible_doctor")], removed))
    for a in [a for a in st.get("actions") or [] if isinstance(a, dict) and a.get("board_record") == rec["id"]]:
        label = _fold(a.get("label")) or "Board action"
        cites = [_acite(a, "label")] + ([_acite(a, "department")] if a.get("department") else []) + ([_acite(a, "due")] if a.get("due") else [])
        add(f"action-{a.get('id')}", _code("", f"Action raised: \"{_clip(label, 300)}\"" + (f" for {a['department']}" if a.get("department") else "")
                                           + (f", due {dmy(a['due'])}." if a.get("due") else "."), cites, removed))
    from_card = {x.get("user") for x in rows if x.get("from_card") and x.get("user")}
    for u, c in _cards(rec, case_id):
        name = c.get("name") or _name(u)
        note = _fold(c.get("note"))
        base = {"kind": "card", "meeting": rec.get("session"), "user": u, "board_date": _rec_date(rec)}
        if c.get("agree"):
            cite = {**base, "field": "note", "quote": note, "stored": note} if note else {**base, "field": "agree", "quote": "agree", "stored": "agree"}
            add(f"card-{u}", _code("", f"{name} agreed" + (f": \"{_clip(note)}\"." if note else "."), [cite], removed))
        elif u not in from_card and note:
            add(f"card-{u}", _code("", f"{name} recorded a concern: \"{_clip(note)}\".", [{**base, "field": "note", "quote": note, "stored": note}], removed))


def rounds_section(case_id, st, recs, facts, removed):
    return {"id": "rounds", "title": TITLES["rounds"], "blocks": [round_block(case_id, st, r, facts, removed) for r in recs], "built_by": "code"}


def _board_actions(st):
    return [a for a in (st or {}).get("actions") or [] if isinstance(a, dict) and a.get("source") == "board"]


def _doc_cite(case_id, doc_id):
    """The closing record of an action as a record line by its title (its location when the title is on a page)."""
    d = store.get_doc(case_id, doc_id) if doc_id else None
    if not d:
        return None
    d = next((x for x in rules.case_docs(case_id) if x["doc_id"] == doc_id), d)
    cl = d.get("classification") or {}
    title = cl.get("title") or d.get("filename") or doc_id
    pages = [p.get("text") or "" for p in d.get("pages") or []]
    locs = qa._locate_quote(title, pages)
    loc = locs[0] if locs else None
    return {"doc_id": doc_id, "quote": loc["matched"] if loc else "", "page": loc["page"] if loc else 0, "start": loc["start"] if loc else None,
            "end": loc["end"] if loc else None, "doc_title": title, "date": dates.doc_dates(d)["event"] or None, "status": cl.get("status"), "by_title": True}


def status_section(case_id, st, recs, removed=None):
    removed = [] if removed is None else removed
    out = []
    today_iso = today()

    def add(s):
        if s:
            s["id"] = _sid("status", len(out) + 1)
            out.append(s)
    acts = _board_actions(st)
    for a in [a for a in acts if a.get("status") != "completed"]:
        label = _fold(a.get("label")) or "Board action"
        due = str(a.get("due") or "")[:10]
        late = bool(due and due < today_iso)
        cites = [_acite(a, "label")] + ([_acite(a, "department")] if a.get("department") else []) + ([_acite(a, "due")] if due else [])
        add(_code("", f"Open: \"{_clip(label, 300)}\"" + (f", {a['department']}" if a.get("department") else "") + (f", due {dmy(due)}" if due else "")
                  + (", overdue." if late else "."), cites, removed, open=True, overdue=late))
    for a in [a for a in acts if a.get("status") == "completed"]:
        label = _fold(a.get("label")) or "Board action"
        when = a.get("completed") or ""
        by = _name(a.get("closed_by")) if a.get("closed_by") else ""
        doc = _doc_cite(case_id, a.get("closed_doc_id")) if a.get("closed_doc_id") else None
        cites = [_acite(a, "label")] + ([_acite(a, "completed")] if when else []) + ([_acite(a, "closed_by")] if a.get("closed_by") else [])
        text = ("Closed" + (f" on {dmy(when)}" if when else "") + (f" by {by}" if by else "") + (f" with the {doc['doc_title']}" if doc else "")
                + f": \"{_clip(label, 300)}\".")
        add(_code("", text, cites + ([doc] if doc else []), removed, open=False))
    dec = [r for r in recs if _outcome(r) == "decision"]
    latest = dec[-1] if dec else (recs[-1] if recs else None)
    if latest and latest.get("patient_informed_date"):
        by = _fold(latest.get("informed_by"))
        add(_code("", f"The patient was recorded as informed on {dmy(latest['patient_informed_date'])}" + (f" by {by}." if by else "."),
                  [_bcite(latest, "patient_informed_date")] + ([_bcite(latest, "informed_by")] if by else []), removed))
    nr = st.get("next_review") if isinstance(st.get("next_review"), dict) else None
    if nr and nr.get("date"):
        src = next((r for r in recs if r["id"] == nr.get("from_record")), None)
        if src and src.get("next_review"):
            add(_code("", f"Next review: {dmy(src['next_review'])}.", [_bcite(src, "next_review")], removed))
    if latest:
        trig = _fold(latest.get("next_review_trigger"))
        if trig:
            add(_code("", f"Or re-discussion, as recorded: \"{_clip(trig)}\".", [_bcite(latest, "next_review_trigger")], removed))
        for f in ((latest.get("adjudication") or {}).get("flags") or []):
            if f.get("kind") == "communication" and not f.get("resolution") and f.get("text"):
                add(_code("", f"Not yet recorded: {FLAG_WORDS.get(f.get('field'), f['text'])}.", [{**_bcite(latest, "flags", f["text"], stored=f["text"]), "flag": f.get("field")}], removed))
    if not any(s.get("open") for s in out):
        add(_fixed("", NOTHING["status"]))
    return {"id": "status", "title": TITLES["status"], "sentences": out, "built_by": "code"}


# ---- the model sections ------------------------------------------------------------------------------------------------------------

def _hint_lines(st) -> str:
    """The first pre-board summary's presentation and investigation sentences: a hint of what to look for, never a source."""
    hist = summary.history(st)
    if not hist:
        return ""
    lines = [s.get("text") or "" for sec in hist[0].get("sections") or [] if sec.get("id") in ("presentation", "investigations")
             for s in sec.get("sentences") or []]
    return "\n".join(f"- {x}" for x in lines if x)


def _messages(case, sec, ctx, first_date, st, hints=""):
    p = case.get("patient") or {}
    sysmsg = summary.SYS + " " + SYS_EXTRA + (" " + SINCE_EXTRA if sec == "since" else "")
    if sec == "presentation":
        task = ("Write the 'Presentation and diagnosis' part of the Case summary: how the patient presented and how the cancer was diagnosed "
                "(histology, grade, receptors and markers) as these records document it, in date order.")
        hint = _hint_lines(st)
        extra = ("\n\nEARLIER SUMMARY (a hint of what to look for, NOT a source: cite only the documents above):\n" + hint) if hint else ""
        head = f"DOCUMENTS (dated on or before the board of {dmy(first_date)}):"
    else:
        task = (f"Write the 'Treatment and follow-up since the board' part of the Case summary: what the records dated after the board decision "
                f"of {dmy(first_date)} document (treatment given, operations, results, imaging), in date order, each with the date of its record.")
        extra = ("\n\nBOARD ACTIONS CLOSED WITH A RECORD (a hint, not a source):\n" + hints) if hints else ""
        head = f"DOCUMENTS (dated after the board of {dmy(first_date)}):"
    return [{"role": "system", "content": sysmsg},
            {"role": "user", "content": f"Patient: {p.get('name')}, {p.get('agesex', '')}.\n\n{head}\n{ctx}{extra}\n\n{task}"}]


async def _ask(case_id, sec, msgs, au, schema=None):
    return await llm.chat("reasoner", msgs, json_schema=schema or SCHEMA, max_tokens=1500, purpose=f"case summary {sec}", audit=au)


def _closed_hints(case_id, st) -> str:
    out = []
    for a in _board_actions(st):
        if a.get("status") == "completed" and a.get("closed_doc_id"):
            d = store.get_doc(case_id, a["closed_doc_id"]) or {}
            title = (d.get("classification") or {}).get("title") or d.get("filename") or a["closed_doc_id"]
            out.append(f"- \"{a.get('label')}\" closed on {dmy(a.get('completed'))} with document {a['closed_doc_id']} ({title})")
    return "\n".join(out)


def _encounters_after(case_id, case, first_date) -> list:
    out = []
    for e in summary.encounter_lines(case_id, case):
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", e.get("when") or "")
        iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
        if iso and iso > first_date:
            out.append({"text": e["text"], "citations": [], "from_fields": True, "code": True, "encounter": e.get("number")})
    return out


# ---- what was said at the board (meetings-v2 item 5.4, owner decision D14) -----------------------------------------------------------

DISCUSSION_SYS = (
    "You write the 'What was said at the board' part of the Case summary of a hospital Tumour Board Case File. You are given the "
    "discussion notes of each board meeting for this Case File: every note line has its id, the time, the speaker and the exact words "
    "that speaker said. This is WHAT WAS SAID AT THE BOARD, not what was decided: the board's decision is recorded elsewhere and you never "
    "restate it, never turn what someone said into a decision or a plan, and never decide, advise, diagnose, stage, judge or conclude "
    "anything yourself.\n\n"
    "Rules for every sentence:\n"
    "1. Begin with the board date as given and name who spoke as the note gives it, for example \"At the board of 23/10/2026, Dr Rao "
    "(Radiology) noted ...\". A note from the Board room microphone has no known speaker: write \"At the board of 23/10/2026, it was "
    "said in the room that ...\" or \"... someone in the room asked ...\".\n"
    "2. Use only plain reporting verbs: said, noted, asked, reported, raised, mentioned, read out, gave their view. Never write in your "
    "own words that something was decided, agreed on, planned, recommended, advised, indicated, needed or should be done; a speaker's "
    "own view stays in their exact words, in quotation marks.\n"
    "3. Cite every sentence: note_line is the id of the note line it reports, quote is a part of that line's exact words copied word "
    "for word (at least three words).\n"
    "4. Never add a fact, number, date, name, drug, stage, diagnosis or decision that is not in the quoted words. Write a number only "
    "exactly as the quote has it. Dates as DD/MM/YYYY, never relative.\n"
    "5. At most one sentence per note line; leave out lines that only repeat another, greetings and anything not about this Case File.\n"
    "6. Plain English. No em dashes. Do not write the patient's name. If there is nothing to report, return no sentence.")
DISCUSSION_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "text": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "note_line": {"type": "string"}, "quote": {"type": "string"}}, "required": ["note_line", "quote"]}}},
        "required": ["text", "citations"]}}},
    "required": ["sentences"]}
DISCUSSION_BUDGET = 30000   # characters of notes per call
MAX_NOTE_LINES = 150        # note lines given to the model
MIN_SAID_WORDS = 3          # a quote shorter than this must be the speaker's whole words
NOTHING_DISCUSSION = ("The discussion notes of the board are kept with the meeting; no sentence of what was said could be checked "
                      "against them.")
ROOM = "room"
# what was said, written as a decision or a plan in the sentence's own words (outside the quoted words)
SAID_DECISION = re.compile(r"\b(?:decid\w*|decision\w*|conclu\w*|resolv\w*|finali[sz]\w*|agreed\s+(?:to|on|upon)\b|the\s+(?:board|team|panel|mdt)\s+"
                           r"agreed|(?:the|a)\s+plan\b|plan\s+(?:is|was)\b|planned\b|will\s+(?:undergo|receive|have|get|start|be\s+given|be\s+treated)\b)", re.I)
_SAID_MARKS = re.compile(r"[\"“”‘’`]")
_SAID_CAPS = re.compile(r"\b[A-Z][A-Za-z0-9+\-/]*")
_SAID_PLAIN = {"the", "in", "a", "an", "it", "they", "he", "she", "there", "this", "that", "both", "all", "someone", "members", "member", "board",
               "tumour", "mdt", "coordinator", "room", "dr", "doctor", "prof", "professor", "i", "at", "on", "of", "during", "when", "while"}
_SPEAKER_STOP = {"the", "and", "dept", "department", "of", "unit", "dr", "doctor", "prof"}


def board_notes(case_id, recs) -> list:
    """The AI discussion notes of this Case File kept by the meeting of each board record (meeting_notes, item 5.3), oldest board first:
    [{meeting_id, date, record, review, lines: [stored note line]}]; only lines with the speaker's exact words. [] for a protected Case
    File or when no meeting of its board records kept notes."""
    if not case_id or case_id in config.PROTECTED_CASES:
        return []
    out, seen = [], set()
    for rec in recs or []:
        mid = str(rec.get("session") or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        try:
            from . import meetings
            s = meetings.get(mid) or {}
        except Exception:
            continue
        e = (s.get("notes") or {}).get(case_id) if isinstance(s.get("notes"), dict) else None
        if not isinstance(e, dict):
            continue
        lines = [x for x in e.get("lines") or [] if isinstance(x, dict) and x.get("id") and isinstance(x.get("said"), dict)
                 and _fold(x["said"].get("quote"))]
        if lines:
            out.append({"meeting_id": mid, "date": str(s.get("date") or _rec_date(rec))[:10], "record": rec["id"],
                        "review": e.get("review") if isinstance(e.get("review"), dict) else {}, "lines": lines})
    return out


def _notes_part(case_id, recs) -> str:
    """What the discussion part is built from (the note lines' ids, texts and exact words); "" when there are none, so a Case File
    without notes keeps the signature it had before item 5.4."""
    notes = board_notes(case_id, recs)
    if not notes:
        return ""
    return _hash([(m["meeting_id"], [(x["id"], _fold(x.get("text")), _fold(x["said"].get("quote"))) for x in m["lines"]]) for m in notes])


def _said_cite(m, ln, quote) -> dict:
    """The "said" citation of a note line: which meeting and line, who spoke, when, the board date and the quoted words."""
    said = ln.get("said") or {}
    return {"kind": "said", "meeting_id": m["meeting_id"], "line_id": ln["id"], "speaker": str(said.get("speaker") or ""),
            "speaker_name": str(said.get("speaker_name") or ""), "department": str(said.get("department") or ""), "at": str(said.get("at") or ""),
            "board_date": m["date"], "quote": quote}


def _find_line(notes, meeting_id, line_id):
    for m in notes or []:
        if m["meeting_id"] == meeting_id or meeting_id is None:
            for ln in m["lines"]:
                if ln.get("id") == line_id:
                    return m, ln
    return None, None


def verify_said(case_id, cite, notes=None, sentence=None) -> bool:
    """A "said" citation holds: its note line is still in that meeting's notes for this Case File (a board record of it names the
    meeting), the quote is word for word in what the speaker said (verify_field: whitespace, case and punctuation forms only) and long
    enough to stand for it, and every number of the sentence (when given) is in the quote."""
    if not isinstance(cite, dict) or cite.get("kind") != "said":
        return False
    if notes is None:
        notes = board_notes(case_id, records(store.get_state(case_id)))
    m, ln = _find_line(notes, cite.get("meeting_id"), cite.get("line_id"))
    if not ln:
        return False
    said = _fold((ln.get("said") or {}).get("quote"))
    q = _fold(cite.get("quote"))
    if len(re.findall(r"\w+", q)) < MIN_SAID_WORDS and grounding.norm(q) != grounding.norm(said):
        return False
    return verify_field(q, said, sentence)


def _speaker_pool(c) -> str:
    """The speaker's name, and the name and aliases of the speaker's department (as meeting_notes checks a note line)."""
    try:
        from . import meeting_notes
        return meeting_notes._speaker_pool(c)
    except Exception:
        return " ".join(str(c.get(k) or "") for k in ("speaker_name", "department"))


def _said_own(text, quotes) -> str:
    """The sentence's own words: the quoted words taken out and every quotation mark removed."""
    return _fold(_SAID_MARKS.sub(" ", guardrails.outside_quotes(text, quotes)))


def _attributed(own, cites) -> bool:
    """The sentence's own words say who spoke: a word of a cited speaker's name or department, or "room" for the Board room microphone."""
    words = set(re.findall(r"[a-z0-9]+", grounding.norm(own)))
    for c in cites:
        if c.get("speaker") == ROOM:
            if "room" in words:
                return True
            continue
        toks = {w for w in re.findall(r"[a-z0-9]+", grounding.norm(_speaker_pool(c))) if len(w) >= 3 and w not in _SPEAKER_STOP}
        if toks & words:
            return True
    return False


def _said_names_ok(own, cites, full_words) -> bool:
    """Every capitalised word of the sentence's own words (a name, a department, a test, a marker) is in what the cited speakers said or
    is a cited speaker's name or department; a few plain words excepted. So a sentence cannot put words in another person's mouth."""
    pool = grounding.norm(" ".join(full_words + [c["quote"] for c in cites] + [_speaker_pool(c) for c in cites]))
    for mm in _SAID_CAPS.finditer(own):
        w = mm.group(0)
        if w.lower() in _SAID_PLAIN:
            continue
        if grounding.norm(w) not in pool:
            return False
    return True


def _check_said(items, notes, removed, issues) -> list:
    """The model's sentences of what was said that pass: no relative date, every citation a note line given (verify_said: the line is in
    the notes now and the quote is word for word in the speaker's words), every number in the quotes (or the board date and time), the
    speaker named in the sentence's own words, no decision or plan in its own words, no name the speakers did not say, and the advice
    guardrail on its own words. Every drop is kept in `removed` with its reason. In board order, then the order spoken."""
    where = "discussion"
    place = {(m["meeting_id"], ln["id"]): (m["date"], i) for m in notes for i, ln in enumerate(m["lines"])}
    keep = []
    for k, x in enumerate(items or []):
        if not isinstance(x, dict):
            continue
        text = _fold(str(x.get("text") or "").replace("—", "-").replace("–", "-"))
        raw = [c for c in x.get("citations") or [] if isinstance(c, dict)]
        item = {"text": text, "citations": raw}
        if not text:
            continue
        m_ = RELATIVE.search(text)
        if m_:
            removed.append(_removed(item, "relative_date", f"\"{m_.group(0)}\" is a relative date", where))
            continue
        if not raw:
            removed.append(_removed(item, "no_citation", "no note line cited", where))
            continue
        cites, why, full = [], None, []
        for c in raw:
            lid = str(c.get("note_line") or c.get("line_id") or "").strip()
            m, ln = _find_line(notes, None, lid)
            if not ln:
                why = ("not_given", lid or "(no id)")
                break
            cite = _said_cite(m, ln, _fold(c.get("quote")))
            if not verify_said("", cite, notes):
                short = len(re.findall(r"\w+", cite["quote"])) < MIN_SAID_WORDS and verify_field(cite["quote"], ln["said"].get("quote"))
                why = ("quote_not_found", f"too short to stand for what {cite['speaker_name'] or 'the speaker'} said (note line {lid})" if short
                       else f"not word for word in what {cite['speaker_name'] or 'the speaker'} said (note line {lid})")
                break
            cites.append(cite)
            full.append(_fold(ln["said"].get("quote")))
        if why:
            removed.append(_removed(item, why[0], why[1], where))
            continue
        if not _numbers_ok(text, cites):
            removed.append(_removed(item, "number_not_in_quote", "a number is not in the quoted words", where))
            continue
        own = _said_own(text, [c["quote"] for c in cites])
        if not _attributed(own, cites):
            removed.append(_removed(item, "not_attributed", "no speaker named", where))
            continue
        dec = SAID_DECISION.search(own)
        if dec:
            removed.append(_removed(item, "said_as_decision", f"\"{dec.group(0)}\" outside the quoted words", where))
            continue
        if not _said_names_ok(own, cites, full):
            removed.append(_removed(item, "names", "a name or term the speakers did not say", where))
            continue
        iss = guardrails.scan_output(own)
        if iss:
            issues.extend(iss)
            removed.append(_removed(item, "guardrail", "; ".join(dict.fromkeys(i["reason"] for i in iss)), where))
            continue
        text = _ISO_DATE.sub(lambda mm: dmy(mm.group(0)), text)
        first = min(place.get((c["meeting_id"], c["line_id"]), ("9999", 10 ** 6)) for c in cites)
        keep.append((first, k, {"text": text, "citations": cites}))
    keep.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in keep]


def _who(said) -> str:
    if said.get("speaker") == ROOM:
        return "Board room microphone (speaker not known)"
    dept = str(said.get("department") or "")
    name = str(said.get("speaker_name") or said.get("speaker") or "A member")
    if not dept:
        return name
    try:
        from . import org
        return f"{name} ({org.department_name(dept)})"
    except Exception:
        return f"{name} ({dept})"


def _discussion_messages(notes):
    """The notes of each board, oldest first, as what was said at the board: id, time, speaker, the note line and the exact words. No
    patient name."""
    parts, used, n = [], 0, 0
    total = sum(len(m["lines"]) for m in notes)
    for m in notes:
        rv = m.get("review") or {}
        state = f"reviewed by {rv.get('by_name') or rv.get('by')}" if rv.get("status") == "reviewed" else "AI draft, not reviewed"
        rows = []
        for ln in m["lines"]:
            said = ln.get("said") or {}
            row = (f"[{ln['id']}] {str(said.get('at') or '')[11:16]} {_who(said)}. Note: {_fold(ln.get('text'))} "
                   f"Exact words: \"{_fold(said.get('quote'))}\"")
            if n >= MAX_NOTE_LINES or used + len(row) > DISCUSSION_BUDGET:
                break
            rows.append(row); used += len(row) + 1; n += 1
        if rows:
            parts.append(f"BOARD OF {dmy(m['date'])} (meeting notes, {state}):\n" + "\n".join(rows))
    user = ("WHAT WAS SAID AT THE BOARD (the discussion notes of this Case File, attributed to the speakers; not the board's decision):\n\n"
            + "\n\n".join(parts) + "\n\nWrite the 'What was said at the board' part of the Case summary.")
    return ([{"role": "system", "content": DISCUSSION_SYS}, {"role": "user", "content": user}],
            {"meetings": len(parts), "lines": n, "left_out": total - n, "characters": used})


def discussion_section(sentences, context) -> dict:
    out = [{**s, "id": _sid("discussion", i)} for i, s in enumerate(sentences, 1)]
    if not out:
        out = [_fixed(_sid("discussion", 1), NOTHING_DISCUSSION)]
    return {"id": "discussion", "title": TITLES["discussion"], "sentences": out, "built_by": "model", "context": context,
            "note": "From the AI discussion notes of the board: what was said, attributed to the speakers; never the board's decision."}


def on_notes_changed(mid, case_id, by="", why="notes_built") -> dict:
    """HOOK (meeting_notes, after the notes of a Case File were built or a line edited): the summary after the board is written again in
    the background when a board record of this Case File comes from that meeting (schedule waits while a meeting is in session). Never
    raises. {"scheduled", "how"}."""
    try:
        if not case_id or case_id in config.PROTECTED_CASES:
            return {"scheduled": False, "how": "off"}
        if not any(str(r.get("session") or "") == str(mid) for r in records(store.get_state(case_id))):
            return {"scheduled": False, "how": "no_board_record"}
        return schedule(case_id, {"kind": "notes", "meeting": mid, "why": why}, by)
    except Exception as e:
        log.warning("Case summary not scheduled after the notes of %s in %s (%s)", case_id, mid, e.__class__.__name__)
        return {"scheduled": False, "how": "error"}


# ---- signature, staleness -----------------------------------------------------------------------------------------------------------

def _status_part(st, recs):
    dec = [r for r in recs if _outcome(r) == "decision"]
    latest = dec[-1] if dec else (recs[-1] if recs else {})
    flags = [f.get("text") for f in ((latest or {}).get("adjudication") or {}).get("flags") or [] if f.get("kind") == "communication"]
    return _hash({"actions": [(a.get("id"), a.get("status"), a.get("closed_doc_id")) for a in _board_actions(st)],
                  "latest": [(latest or {}).get(k) for k in STATUS_COMM] + [(latest or {}).get("next_review_trigger")], "flags": flags,
                  "next_review": (st.get("next_review") or {}) if isinstance(st.get("next_review"), dict) else None})


def signature(case_id, st) -> dict:
    """What a version is built from: rules.case_signature, the board records (ids, versions and the round's communication fields), the
    board actions and the latest record's patient-informed fields and flags (the status part), the draft stage confirmation, and the
    discussion notes of the board records' meetings (only when there are some)."""
    st = st if isinstance(st, dict) else store.get_state(case_id)
    recs = records(st)
    base = rules.case_signature(case_id, st)
    d = st.get("staging") if isinstance(st.get("staging"), dict) else {}
    conf = (d.get("confirmed") or {}).get("at") if isinstance(d.get("confirmed"), dict) and not d.get("rejected") else None
    parts = {"case": base["hash"],
             "board": _hash([(r["id"], r.get("version", 1), *[r.get(k) for k in ROUND_COMM]) for r in recs]),
             "status": _status_part(st, recs), "staging": conf or ""}
    notes = _notes_part(case_id, recs)
    if notes:  # only with notes: a Case File without them keeps the hash it had before item 5.4
        parts["notes"] = notes
    return {"hash": _hash(parts), "parts": parts, "case": base, "records": len(recs)}


def stale_reason(then, now) -> str:
    """Plain words for why a version is out of date; "" when it is not."""
    if not then or then.get("hash") == now.get("hash"):
        return ""
    tp, np_ = then.get("parts") or {}, now.get("parts") or {}
    why = []
    if tp.get("case") != np_.get("case"):
        why.append(rules.stale_reason(then.get("case") or {}, now.get("case") or {}) or "The records changed since this was built")
    if tp.get("board") != np_.get("board"):
        why.append("A board record was added or corrected since this was built")
    if tp.get("staging") != np_.get("staging"):
        why.append("The draft stage confirmation changed since this was built")
    if tp.get("status") != np_.get("status"):
        why.append("Board actions or the record of telling the patient changed since this was built")
    if (tp.get("notes") or "") != (np_.get("notes") or ""):
        why.append("The discussion notes of the board changed since this was built")
    return ". ".join(why) or "The Case File changed since this was built"


# ---- build --------------------------------------------------------------------------------------------------------------------------

def _cite_keys(sentence) -> set:
    """(record, quote) of each record-line citation, and ("said:" note line, quote) of each note-line citation."""
    return {(str(c.get("doc_id") or "") if c.get("doc_id") else "said:" + str(c.get("line_id")), grounding.norm(str(c.get("quote") or "")))
            for c in sentence.get("citations") or []
            if isinstance(c, dict) and (c.get("doc_id") or (c.get("kind") == "said" and c.get("line_id"))) and c.get("quote")}


def _carry_edits(prev, sections, case_id):
    """The consultant's edits of the previous version stay. An edited sentence is matched to a new one by content (the same Vaidyx text,
    else a shared cited record line), never by position; it replaces only that sentence, and a different new text for it is kept under
    edited.suggested, never over the edit. An edited sentence with no match is added at the end of its section (carried), the new
    sentences left as they are."""
    if not prev:
        return 0
    carried = 0
    by_sec = {s["id"]: s for s in sections}
    for psec in prev.get("sections") or []:
        if psec.get("id") not in MODEL_SECTIONS or psec["id"] not in by_sec:
            continue
        sec = by_sec[psec["id"]]
        used = set()
        for ps in psec.get("sentences") or []:
            if not isinstance(ps.get("edited"), dict):
                continue
            keep = {k: v for k, v in ps.items() if k not in ("edited", "id")}
            ed = {**ps["edited"], "carried_from": prev.get("n")}
            ed.pop("suggested", None)
            ed["records_changed"] = _records_changed(ed, case_id)
            vt = _fold(ed.get("vaidyx_text"))
            cands = [x for x in sec["sentences"] if not x.get("fixed") and not isinstance(x.get("edited"), dict) and id(x) not in used]
            new = next((x for x in cands if vt and _fold(x["text"]) == vt), None)
            if new is None and _cite_keys(ps):
                new = next((x for x in cands if _cite_keys(x) & _cite_keys(ps)), None)
            if new is not None:
                if _fold(new["text"]) not in (_fold(ps["text"]), vt):
                    ed["suggested"] = {"text": new["text"], "citations": new.get("citations") or []}
                item = {**keep, "id": new["id"], "edited": ed}
                used.add(id(item))
                sec["sentences"][sec["sentences"].index(new)] = item
            else:
                sec["sentences"] = [x for x in sec["sentences"] if not x.get("fixed")]
                ids = {x.get("id") for x in sec["sentences"]}
                k = len(sec["sentences"]) + 1
                while _sid(sec["id"], k) in ids:
                    k += 1
                item = {**keep, "id": _sid(sec["id"], k), "edited": {**ed, "unmatched": True}}
                used.add(id(item))
                sec["sentences"].append(item)
            carried += 1
    return carried


def _records_changed(ed, case_id) -> bool:
    """True when a record the edited sentence cites was re-processed or removed since the edit."""
    for did, processed in (ed.get("records") or {}).items():
        d = store.get_doc(case_id, did)
        if not d or str(d.get("processed") or "") != str(processed or ""):
            return True
    return bool(ed.get("records_changed"))


async def build(case_id, trigger: dict, user="") -> dict:
    """Build a new version of the Case summary; returns it. {"status": "no_decision"} (nothing stored) without a board record. A model
    failure leaves that section with its fixed sentence and model_error on the version. ValueError for a protected Case File."""
    if case_id in config.PROTECTED_CASES:
        raise ValueError("This Case File is protected: Vaidyx does not build a Case summary for it.")
    t0 = time.time()
    case = store.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    au = store.auditor(case_id)
    st = store.get_state(case_id)
    recs = records(st)
    if not recs:
        return {"status": "no_decision", "message": "No board decision has been recorded for this Case File."}
    sig = signature(case_id, st)  # taken first: a change during the model calls marks the version out of date
    trigger = {**(trigger if isinstance(trigger, dict) else {}), "by": (trigger or {}).get("by") or user}
    first = _rec_date(recs[0])
    docs = _docs(case_id, st)
    pre, post = _split(docs, first)
    facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    cat = protocol.facts()
    near = config.near_match()
    removed, issues, model_error = [], [], {}
    ctx_pre, ids_pre, mode_pre = _context(pre)
    ctx_post, ids_post, mode_post = _context(post)
    calls = {}
    if ids_pre:
        calls["presentation"] = _ask(case_id, "presentation", _messages(case, "presentation", ctx_pre, first, st), au)
    if ids_post:
        calls["since"] = _ask(case_id, "since", _messages(case, "since", ctx_post, first, st, _closed_hints(case_id, st)), au)
    notes = board_notes(case_id, recs)  # what was said at the board (item 5.4): only when a meeting of the records kept notes
    mode_disc = None
    if notes:
        msgs_disc, mode_disc = _discussion_messages(notes)
        calls["discussion"] = _ask(case_id, "discussion", msgs_disc, au, DISCUSSION_SCHEMA)
    got = dict(zip(calls, await asyncio.gather(*calls.values(), return_exceptions=True))) if calls else {}
    for k, r in got.items():
        if isinstance(r, BaseException):
            model_error[k] = f"{r.__class__.__name__}: {str(r)[:200]}"
            au({"kind": "case_summary_model_error", "section": k, "why": model_error[k]})
            got[k] = {}
    pres = _check_model(case_id, (got.get("presentation") or {}).get("sentences"), set(ids_pre), "presentation", removed, issues, near)
    _fill(pres, facts, PRESENTATION_FACTS, cat)
    pres = _finish_model_section("presentation", pres) or [{**_fixed(_sid("presentation", 1), NOTHING["presentation"])}]
    post_ids = {d["doc_id"] for d in post}
    since_facts = {k: v for k, v in facts.items() if k in SINCE_FACTS and ((v.get("current") or {}).get("doc_id") in post_ids)}
    since = _check_model(case_id, (got.get("since") or {}).get("sentences"), set(ids_post), "since", removed, issues, near)
    _fill(since, since_facts, SINCE_FACTS, cat)
    since += _encounters_after(case_id, case, first)
    since = _finish_model_section("since", since)
    if not since:
        since = [_fixed(_sid("since", 1), (NOTHING_CHECKED_SINCE if post else NOTHING_SINCE).format(date=dmy(first)))]
    disc = None
    if notes:  # checked against the notes as they are now (a rebuild of the notes during the model call drops the old lines)
        disc = discussion_section(_check_said((got.get("discussion") or {}).get("sentences"), board_notes(case_id, recs), removed, issues), mode_disc)
    sections = [{"id": "presentation", "title": TITLES["presentation"], "sentences": pres, "built_by": "model", "context": mode_pre},
                stage_section(case_id, st, facts, recs, removed),
                rounds_section(case_id, st, recs, facts, removed),
                *([disc] if disc else []),
                {"id": "since", "title": TITLES["since"], "sentences": since, "built_by": "model", "context": mode_post},
                status_section(case_id, st, recs, removed)]
    if issues:
        au({"kind": "guardrail_output", "where": "case_summary", "issues": issues})
    label = config.models().get("reasoner", {}).get("label") or "the reasoner model"
    st = store.get_state(case_id)  # read again and written at once (no await in between)
    art = st.setdefault("artefacts", {}).get(ART)
    if not isinstance(art, dict) or not isinstance(art.get("versions"), list):
        art = {"current": 0, "versions": []}
    carried = _carry_edits(current(st) if _artefact(st) else None, sections, case_id)
    n = max([v.get("n") or 0 for v in art["versions"]] + [0]) + 1
    sents = all_sentences({"sections": sections})
    v = {"n": n, "built_at": store.now_iso(), "trigger": trigger, "signature": sig,
         "inputs": {"board_records": [{"id": r["id"], "version": r.get("version", 1)} for r in recs],
                    "actions": [{"id": a.get("id"), "status": a.get("status")} for a in _board_actions(st)],
                    "stage_confirmed_at": sig["parts"]["staging"] or None, "documents": len(docs),
                    "documents_before": len(pre), "documents_after": len(post),
                    "notes": [{"meeting_id": m["meeting_id"], "lines": len(m["lines"])} for m in notes]},
         "title": TITLE, "first_board_date": first, "last_board_date": _rec_date(recs[-1]), "sections": sections, "removed": removed, "model": label, "model_line": f"Written by {label} (non-medical)",
         "label": "AI draft, not reviewed", "status_day": today(), "seconds": round(time.time() - t0, 1), "review": {"status": "ai_draft"}, "edits": [],
         "carried_edits": carried, **({"model_error": model_error} if model_error else {})}
    art["versions"].append(v)
    art["current"] = n
    art["case_id"] = case_id
    st["artefacts"][ART] = art
    store.save_state(case_id, st)
    write_line(case_id, st)  # the summary line of the Case File follows the new version (item 3.4); an edited line is kept
    au({"kind": "case_summary", "version": n, "trigger": trigger.get("kind"), "sentences": len(sents), "dropped": len(removed),
        "removed": {k: c for k in REASONS if (c := sum(1 for x in removed if x.get("reason") == k))}, "seconds": v["seconds"],
        **({"model_error": sorted(model_error)} if model_error else {})})
    return v


# ---- the status section after an action closure or a communication update --------------------------------------------------------

def refresh_status(case_id=None, state=None):
    """Rewrite only the status section of the current version (code, no model, no new version) and set refreshed_at. With `state` the
    state is changed in place and the caller saves it (followup.close_action: the route saves); otherwise it is read and saved here.
    None when there is no Case summary."""
    own = state is None
    st = store.get_state(case_id) if own else state
    art = _artefact(st)
    v = current(st) if art else None
    case_id = case_id or (art or {}).get("case_id")
    if not v or not case_id or case_id in config.PROTECTED_CASES:
        return None
    recs = records(st)
    sec = status_section(case_id, st, recs)
    v["sections"] = [sec if s.get("id") == "status" else s for s in v.get("sections") or []]
    v["refreshed_at"] = store.now_iso()
    v["status_day"] = today()
    v.setdefault("inputs", {})["actions"] = [{"id": a.get("id"), "status": a.get("status")} for a in _board_actions(st)]
    sig = v.get("signature") or {}
    if isinstance(sig.get("parts"), dict):
        sig["parts"]["status"] = _status_part(st, recs)
        sig["hash"] = _hash(sig["parts"])
    if own:
        store.save_state(case_id, st)
    store.audit(case_id, {"kind": "case_summary_status_refreshed", "version": v.get("n")})
    try:  # "N actions open" in the summary line follows too (item 3.4)
        write_line(case_id, st)
    except Exception as e:
        log.warning("summary line not written for %s (%s)", case_id, e)
    return v


# ---- background build after a decision -------------------------------------------------------------------------------------------

RUNNING: dict = {}  # case_id -> {"started", "trigger", "user"}
AGAIN: dict = {}  # case_id -> (trigger, user): one more run after the current one, the latest request only
TASKS: set = set()
_lock = threading.Lock()


def enabled() -> bool:
    """TB_SCHEDULER=0 turns the background build off; under pytest it runs only with TB_SCHEDULER=1 (tests call build directly)."""
    raw = os.getenv("TB_SCHEDULER")
    v = str(raw).strip().lower() if raw is not None else ""
    if v in ("0", "false", "no", "off"):
        return False
    return not ("PYTEST_CURRENT_TEST" in os.environ and v != "1")


def building(case_id) -> bool:
    return case_id in RUNNING


def _notify_owner(case_id, v, user):
    from . import notify, org
    case = store.get_case(case_id) or {}
    patient = (case.get("patient") or {}).get("name") or case_id
    to = {"department": case["department"]} if case.get("department") and org.department_id(case["department"]) else {"user": user}
    rid = (v.get("trigger") or {}).get("record")
    mid = (v.get("trigger") or {}).get("meeting")
    st = store.get_state(case_id)
    rec = (next((r for r in records(st) if r["id"] == rid), None) or next((r for r in reversed(records(st)) if mid and r.get("session") == mid), None)
           or (records(st) or [{}])[-1])
    title = f"{TITLE} updated: {patient} ({case_id})"
    after = (f"with the discussion notes of the board of {dmy(_rec_date(rec))}" if (v.get("trigger") or {}).get("kind") == "notes"
             else f"after the board decision of {dmy(_rec_date(rec))}")
    text = f"Version {v['n']} {after}: AI draft, not reviewed. The owner's consultant reviews and edits it."
    for kind in ("summary_ready", "owner_reminder"):
        try:
            return notify.notify(to, kind, case_id, title, text, by="Vaidyx (automatic)", version=v["n"], artefact=ART)
        except ValueError:
            continue
        except Exception as e:
            return {"error": f"{e.__class__.__name__}: {e}"}
    return None


async def _run(case_id, trigger, user):
    from . import ready_hook
    done = False
    try:
        while True:
            waits = 0
            while ready_hook.meeting_in_session():
                if waits >= ready_hook.MAX_WAITS:
                    store.audit(case_id, {"kind": "case_summary_failed", "by": user, "why": "a board session stayed in session", "trigger": trigger})
                    break
                waits += 1
                await asyncio.sleep(ready_hook.MEETING_DELAY)
            if waits < ready_hook.MAX_WAITS and not store.gone(case_id) and store.get_case(case_id):
                try:
                    v = await build(case_id, trigger, user)
                    if isinstance(v, dict) and v.get("n"):
                        _notify_owner(case_id, v, user)
                except Exception as e:  # the old version stays current
                    log.warning("Case summary build failed for %s (%s)", case_id, e)
                    try:
                        store.audit(case_id, {"kind": "case_summary_failed", "by": user, "trigger": trigger, "why": f"{e.__class__.__name__}: {str(e)[:200]}"})
                    except Exception:
                        pass
            with _lock:
                nxt = AGAIN.pop(case_id, None)
                if nxt is None:
                    RUNNING.pop(case_id, None)
                    done = True
                    return
                trigger, user = nxt
                RUNNING[case_id] = {"started": time.time(), "trigger": trigger, "user": user}
    finally:
        if not done:  # cancelled or an unexpected error: the Case File is free for the next request
            with _lock:
                RUNNING.pop(case_id, None)
                AGAIN.pop(case_id, None)


def schedule(case_id, trigger, user="") -> dict:
    """Build the Case summary in the background and return at once: {"scheduled", "how": loop|thread|queued|off}. One run per Case
    File; a request during a run queues exactly one more (the latest). Waits while a board session is in session."""
    if not enabled():
        return {"scheduled": False, "how": "off", "reason": "TB_SCHEDULER=0"}
    if case_id in config.PROTECTED_CASES:
        return {"scheduled": False, "how": "off", "reason": "protected Case File"}
    trigger = trigger if isinstance(trigger, dict) else {}
    with _lock:
        if case_id in RUNNING:
            AGAIN[case_id] = (trigger, user)
            return {"scheduled": False, "how": "queued"}
        RUNNING[case_id] = {"started": time.time(), "trigger": trigger, "user": user}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(_run(case_id, trigger, user))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
        return {"scheduled": True, "how": "loop"}
    threading.Thread(target=lambda: asyncio.run(_run(case_id, trigger, user)), daemon=True, name=f"tb-case-summary-{case_id}").start()
    return {"scheduled": True, "how": "thread"}


# ---- review and edit ----------------------------------------------------------------------------------------------------------------

def review(case_id, n, status, comment, user) -> dict:
    """The owner's consultant marks version n reviewed or flagged (or back to AI draft); kept on that version and in st["reviews"]."""
    if status not in REVIEW_STATUSES:
        raise ValueError("The review status must be one of: " + ", ".join(REVIEW_STATUSES) + ".")
    st = store.get_state(case_id)
    v = _version(st, int(n))
    rv = {"status": status, "comment": _fold(comment)[:2000], "by": user, "by_name": _name(user), "at": store.now_iso(), "generated": v.get("built_at")}
    v["review"] = rv
    st.setdefault("reviews", []).append({"artefact": ART, "version": v["n"], **rv})
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "expert_review", "artefact": ART, "version": v["n"], "status": status, "by": user, "comment": rv["comment"]})
    return rv


_CAPS = re.compile(r"\b[A-Z][A-Za-z0-9+\-/]*")
_CLAUSE_START = re.compile(r"(?:^|[.:;!?]\s+|\(\s*)$")


def _checked(text, cites) -> bool:
    """True when every number and every capitalised word (a name, a marker) of the edited text is in one of the sentence's quotes (or a
    cited record's title)."""
    cites = [c for c in cites or [] if isinstance(c, dict)]
    if not cites:
        return False
    rows = [{"quote": str(c.get("quote") or ""), "doc_title": str(c.get("doc_title") or (_speaker_pool(c) if c.get("kind") == "said" else "")),
             "date": " ".join(str(c.get(k) or "") for k in ("date", "board_date"))} for c in cites]
    if qa._missing_numbers(text, rows):
        return False
    pool = grounding.norm(" ".join(r["quote"] + " " + r["doc_title"] for r in rows))
    for m in _CAPS.finditer(text):
        if _CLAUSE_START.search(text[:m.start()]):
            continue
        if grounding.norm(m.group(0)) not in pool:
            return False
    return True


def edit(case_id, n, sentence_id, text, user, user_name="") -> dict:
    """The owner's consultant changes one sentence of the presentation or since section of the current version. Every edit is a new
    entry in the version's edits (nothing deleted; undo is an edit back). The citations stay; `checked` says whether every number and
    name of the new text is still in its quotes. Returns the sentence."""
    text = " ".join(str(text or "").replace("\u2014", "-").replace("\u2013", "-").split())  # em and en dash (review M6)
    if not 1 <= len(text) <= MAX_EDIT:
        raise ValueError(f"Write the sentence (1 to {MAX_EDIT} characters).")
    st = store.get_state(case_id)
    v = _version(st, int(n))
    cur = current(st)
    if cur is None or cur.get("n") != v.get("n"):
        raise ValueError("Only the current version of the Case summary is edited; earlier versions stay as they were.")
    sec = next((sec for sec in v.get("sections") or [] if any(x.get("id") == sentence_id for x in all_sentences({"sections": [sec]}))), None)
    if sec is None:
        raise KeyError(f"No sentence {sentence_id} in version {v['n']}")
    if sec.get("id") not in MODEL_SECTIONS:
        raise ValueError(CODE_EDIT)
    s = next(x for x in sec["sentences"] if x.get("id") == sentence_id)
    if s.get("fixed"):
        raise ValueError(FIXED_EDIT)
    if s.get("code") or s.get("from_fields"):
        raise ValueError(CODE_EDIT)
    now = store.now_iso()
    name = user_name or _name(user)
    prev_ed = s.get("edited") if isinstance(s.get("edited"), dict) else {}
    vaidyx_text = prev_ed.get("vaidyx_text") or s["text"]
    v.setdefault("edits", []).append({"sentence_id": sentence_id, "text": text, "by": user, "by_name": name, "at": now, "previous": s["text"],
                                      "previous_citations": list(s.get("citations") or [])})
    s["text"] = text
    if text == _fold(vaidyx_text) and not prev_ed.get("carried_from"):
        s.pop("edited", None)  # back to the Vaidyx text: the edits keep the chain
    else:
        recs = {}
        for c in s.get("citations") or []:
            d = store.get_doc(case_id, c.get("doc_id")) if c.get("doc_id") else None
            if d:
                recs[c["doc_id"]] = d.get("processed") or ""
        s["edited"] = {"by": user, "by_name": name, "at": now, "checked": _checked(text, s.get("citations")), "vaidyx_text": vaidyx_text,
                       "records": recs, **({"carried_from": prev_ed["carried_from"]} if prev_ed.get("carried_from") else {})}
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "case_summary_edit", "version": v["n"], "sentence": sentence_id, "by": user,
                          "checked": bool((s.get("edited") or {}).get("checked")), "text": text[:300]})
    return s


# ---- readers -------------------------------------------------------------------------------------------------------------------------

def history(st) -> list:
    """Every version, oldest first: {n, built_at, trigger, review, edits: count, sentences: count}."""
    a = _artefact(st)
    return [{"n": v.get("n"), "built_at": v.get("built_at"), "trigger": v.get("trigger"), "review": v.get("review"),
             "edits": len(v.get("edits") or []), "sentences": len(all_sentences(v))} for v in (a or {}).get("versions") or []]


def status(st, case_id) -> dict:
    """{"status": none|building|ready|stale|reviewed, "version", "built_at", "stale_reason"}."""
    v = current(st)
    if building(case_id):
        return {"status": "building", "version": (v or {}).get("n"), "built_at": (v or {}).get("built_at"), "stale_reason": ""}
    if not v:
        return {"status": "none", "version": None, "built_at": None, "stale_reason": ""}
    why = stale_reason(v.get("signature"), signature(case_id, st))
    word = "stale" if why else ("reviewed" if (v.get("review") or {}).get("status") == "reviewed" else "ready")
    return {"status": word, "version": v.get("n"), "built_at": v.get("built_at"), "stale_reason": why}


_GENERIC = {"cancer", "carcinoma", "ca", "tumour", "tumor", "tumours", "of", "the", "and", "malignancy", "neoplasm", "protocol"}


def summary_line(st, case) -> str:
    """One line (at most 160 characters) built by code: "<histology>, <stage>; board DD/MM/YYYY: <decision>; N actions open". Stores nothing."""
    case = case if isinstance(case, dict) else {}
    cid = case.get("case_id") or ""
    try:
        facts = rules.resolve_facts(rules.case_docs(cid, st), (st or {}).get("overrides")) if cid else {}
    except Exception:
        facts = {}
    cur = lambda f: (facts.get(f) or {}).get("current") or {}
    hist = cur("histologic_type").get("value") if cur("histologic_type").get("verification") in rules.VERIFIED else ""
    try:
        label = protocol.case_label(case)
    except Exception:
        label = ""
    site = " ".join(w for w in re.findall(r"[A-Za-z]+", label or "") if w.lower() not in _GENERIC and len(w) > 3 and w.lower() not in _fold(hist).lower())
    head = _fold(hist) or _fold(label)
    if hist and site:  # the site words of the cancer label that the histology does not already say
        head = f"{_fold(hist)}, {site.lower()}"
    stage = max([c for c in (cur("recorded_stage"), cur("figo_stage")) if c and c.get("verification") in rules.VERIFIED],
                key=lambda c: (c.get("date") or "", c.get("report_date") or ""), default=None)
    recs = records(st)
    stage_v = _fold((stage or {}).get("value")) or next((_fold(r.get("stage_as_agreed")) for r in reversed(recs) if _fold(r.get("stage_as_agreed"))), "")
    head_part = ", ".join(x for x in (head, stage_v) if x)
    dec_part = ""
    if recs:
        r = recs[-1]
        dec = _fold(r.get("decision_text")) or decision_record.OUTCOMES.get(_outcome(r), "")
        dec_part = f"board {dmy(_rec_date(r))}: {dec}"
    k = sum(1 for a in _board_actions(st) if a.get("status") != "completed")
    tail = f"{k} {'action' if k == 1 else 'actions'} open"
    # fit in MAX_LINE: the decision text gives way first (at a word boundary, with "..."), then the head; the tail always stays
    sep = "; "
    room = MAX_LINE - len(tail) - len(sep) - (len(head_part) + len(sep) if head_part else 0)
    dec_part = _cut_words(dec_part, room)
    if head_part and len(head_part) + len(sep) + (len(dec_part) + len(sep) if dec_part else 0) + len(tail) > MAX_LINE:
        head_part = _cut_words(head_part, MAX_LINE - len(tail) - len(sep) - (len(dec_part) + len(sep) if dec_part else 0))
    line = sep.join(x for x in (head_part, dec_part, tail) if x)
    line = line.replace("\u2014", "-").replace("\u2013", "-")
    return line[:MAX_LINE]


def _cut_words(text, room) -> str:
    """`text` within `room` characters, cut at a word boundary with "..."; "" when the room is too small for anything readable."""
    text = _fold(text)
    if len(text) <= room:
        return text
    if room < 16:
        return ""
    cut = text[:room - 3].rsplit(" ", 1)[0].rstrip(" ,;:(")
    return cut + "..."


# ---- the main summary and the summary line (night-v3 item 3.4) ------------------------------------------------------------------------

VAIDYX = "vaidyx"
VAIDYX_NAME = "Vaidyx"
MAX_LINE = 160
BOARD_LABELS = {"versions": "Correction", "outcome_type": "Outcome", "board_date": "Board date", "flags": "Not yet recorded",
                "deferred_reason": "What is awaited", "divergent_opinions": "Divergent views", "intent_as_recorded": "Treatment intent"}


def board_label(field) -> str:
    """The words a board chip reads after "Board DD/MM/YYYY, ": the field's label from decision_record."""
    return BOARD_LABELS.get(field) or decision_record.label(field)


def with_labels(v) -> dict:
    """A copy of a version whose board citations carry `label` (the stored version is never changed by reading it)."""
    out = copy.deepcopy(v)
    for sen in all_sentences(out):
        for c in sen.get("citations") or []:
            if isinstance(c, dict) and c.get("kind") == "board" and not c.get("label"):
                c["label"] = board_label(c.get("field"))
        sug = (sen.get("edited") or {}).get("suggested") if isinstance(sen.get("edited"), dict) else None
        for c in (sug or {}).get("citations") or []:
            if isinstance(c, dict) and c.get("kind") == "board" and not c.get("label"):
                c["label"] = board_label(c.get("field"))
    return out


def display(case_id, st, v) -> dict:
    """A version as shown: board chips labelled, and for the current version the status section worked out now (code, no model), so
    "overdue" and the open actions are true today without writing anything on a read (Phase 3 review N3). Earlier versions as stored."""
    out = with_labels(v)
    out.setdefault("title", TITLE)  # a version built before item 5.4 reads with the same title
    if not out.get("last_board_date"):
        rounds = next((x for x in out.get("sections") or [] if x.get("id") == "rounds"), None) or {}
        out["last_board_date"] = next((b.get("date") for b in reversed(rounds.get("blocks") or []) if b.get("date")), None)
    cur = current(st)
    if cur and v.get("n") == cur.get("n") and case_id not in config.PROTECTED_CASES:
        try:
            sec = status_section(case_id, st, records(st))
            out["sections"] = [sec if x.get("id") == "status" else x for x in out.get("sections") or []]
            out["status_day"] = today()
        except Exception as e:
            log.warning("status section not worked out for %s (%s)", case_id, e)
    return out


def _can(case_id, roles) -> dict:
    from . import access, org
    r = roles if isinstance(roles, dict) else {}
    c = store.get_case(case_id) or {}
    if not r or r.get("disabled"):
        return {"build": False, "review": False, "edit": False}
    owner = access.is_owner_doctor(r, c)
    return {"build": bool(org.can(r, "list_case") or access.may(r, "upload_to_case", c)), "review": owner, "edit": owner}


def view(case_id, st, roles=None, n=None) -> dict | None:
    """What the Summary section and the Overview show of the Case summary (CaseSummaryView); None when there is none. `n` picks a version
    (the current one by default); the status words are those of the current version."""
    st = st if isinstance(st, dict) else store.get_state(case_id)
    cur = current(st)
    if not cur:
        return None
    v = cur if n is None else _version(st, int(n))
    stt = status(st, case_id)
    rv = v.get("review") or {}
    reviewed = rv.get("status") == "reviewed"
    lv = display(case_id, st, v)
    recs = records(st)
    return {"status": stt["status"], "current": cur.get("n"), "n": v.get("n"), "built_at": v.get("built_at"),
            "title": TITLE, "before_title": TITLE_BEFORE, "last_board_date": v.get("last_board_date") or (_rec_date(recs[-1]) if recs else None),
            "trigger": {"kind": (v.get("trigger") or {}).get("kind"), "by": (v.get("trigger") or {}).get("by")},
            "model_line": v.get("model_line") or "", "model": v.get("model") or "",
            "label": f"Reviewed by {rv.get('by_name') or _name(rv.get('by'))}" if reviewed else "AI draft, not reviewed",
            "stale_reason": stt.get("stale_reason") or "",
            "review": {"status": rv.get("status") or "ai_draft", "by": rv.get("by"), "by_name": rv.get("by_name") or (_name(rv.get("by")) if rv.get("by") else ""),
                       "at": rv.get("at"), "comment": rv.get("comment") or ""},
            "sections": lv.get("sections") or [], "removed": len(v.get("removed") or []), "edits": len(v.get("edits") or []),
            "first_board_date": v.get("first_board_date"), "refreshed_at": v.get("refreshed_at"),
            "versions": [{"n": h["n"], "built_at": h["built_at"], "trigger": {"kind": (h.get("trigger") or {}).get("kind")},
                          "review": {"status": (h.get("review") or {}).get("status") or "ai_draft", "by_name": (h.get("review") or {}).get("by_name")
                                     or (_name((h.get("review") or {}).get("by")) if (h.get("review") or {}).get("by") else "")},
                          "edits": h["edits"], "sentences": h["sentences"]} for h in history(st)],
            "can": _can(case_id, roles)}


FULL_ARCHIVED = 3  # archived pre-board summaries sent in full; older ones as a line each (Phase 3 follow-up review M3)


def pre_board_history(st) -> list:
    """The pre-board summaries (summary.history, item 3.5), oldest first, the live one last (live true). The live one and the newest three
    archived ones come in full (full true: paragraphs, points for review, the stage as recorded); older ones as {generated, archived_at,
    review, model, sentences: count, live, full: false}: they stay on disk in full."""
    hist = summary.history(st)
    archived = [i for i, h in enumerate(hist) if h.get("archived_at") is not None]
    full_idx = set(archived[-FULL_ARCHIVED:]) | {i for i, h in enumerate(hist) if h.get("archived_at") is None}
    out = []
    for i, h in enumerate(hist):
        rv = h.get("review") or {}
        row = {"generated": h.get("generated"), "archived_at": h.get("archived_at"),
               "review": {"status": rv.get("status") or "ai_draft", "by": rv.get("by"), "by_name": _name(rv.get("by")) if rv.get("by") else "",
                          "at": rv.get("at"), "comment": rv.get("comment") or ""},
               "model": h.get("model") or "", "sentences": sum(len(x.get("sentences") or []) for x in h.get("sections") or []),
               "live": h.get("archived_at") is None, "full": i in full_idx}
        if row["full"]:
            row.update({"paragraphs": [{"id": x.get("id"), "title": x.get("title"), "sentences": x.get("sentences") or []} for x in h.get("sections") or []],
                        "points_for_review": h.get("points_for_review") or [], "stage_as_recorded": h.get("stage_as_recorded")})
        out.append(row)
    return out


def _clean_line(text) -> str:
    return " ".join(str(text or "").replace("\u2014", "-").replace("\u2013", "-").split())


def write_line(case_id, st=None) -> dict | None:
    """case["summary_line"] from the current version: the Vaidyx line (code, summary_line()), unless the consultant edited it; then the
    edited text stays, `vaidyx_text` holds the Vaidyx line now and `stale` turns true once that differs from the one the edit replaced.
    Saved only when something changed. None when there is no Case summary."""
    st = st if isinstance(st, dict) else store.get_state(case_id)
    v = current(st)
    case = store.get_case(case_id)
    if not v or not case or case_id in config.PROTECTED_CASES:
        return None
    text = summary_line(st, case)
    cur = case.get("summary_line") if isinstance(case.get("summary_line"), dict) else None
    if cur and cur.get("edited"):
        new = dict(cur)
        if text != cur.get("vaidyx_text"):
            new["stale"] = True
            new["vaidyx_text"] = text
    else:
        same = bool(cur) and cur.get("text") == text and cur.get("version") == v.get("n")
        new = {"text": text, "version": v.get("n"), "at": cur.get("at") if same else store.now_iso(), "by": VAIDYX, "by_name": VAIDYX_NAME, "edited": False}
    if new != cur:
        case["summary_line"] = new
        store.save_case(case)
    return new


def edit_line(case_id, text, user, user_name="") -> dict:
    """The owner's consultant writes the summary line (at most 160 characters, whitespace folded, no em dash); an empty text goes back to
    the Vaidyx line. Audited. LookupError when there is no Case summary yet; ValueError for a line over 160 characters."""
    st = store.get_state(case_id)
    v = current(st)
    case = store.get_case(case_id)
    if not v or not case:
        raise LookupError("There is no Case summary yet, so there is no summary line to edit.")
    text = _clean_line(text)
    if len(text) > MAX_LINE:
        raise ValueError(f"The summary line: at most {MAX_LINE} characters ({len(text)} written). Shorten it.")
    old = case.get("summary_line") if isinstance(case.get("summary_line"), dict) else {}
    vaidyx = summary_line(st, case)
    now = store.now_iso()
    if not text:
        line = {"text": vaidyx, "version": v.get("n"), "at": now, "by": VAIDYX, "by_name": VAIDYX_NAME, "edited": False}
    else:
        line = {"text": text, "version": v.get("n"), "at": now, "by": user, "by_name": user_name or _name(user), "edited": True, "stale": False,
                "vaidyx_text": vaidyx}
    case["summary_line"] = line
    store.save_case(case)
    store.audit(case_id, {"kind": "summary_line_edit", "by": user, "text": line["text"], "edited": line["edited"], "previous": old.get("text") or "",
                          "version": v.get("n")})
    return line


def case_for(c, scope, also=()) -> dict:
    """The case record for a reader: `summary_line` (clinical text) only when the reader's scope is FULL (or one of `also`); a department
    that was only asked, a linked reader or a meeting screen never receives it (Phase 3 follow-up review S2)."""
    from . import access
    if not isinstance(c, dict) or "summary_line" not in c or scope == access.FULL or (scope and scope in also):
        return c
    return {k: v for k, v in c.items() if k != "summary_line"}
