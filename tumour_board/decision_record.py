"""The Tumour Board decision record (night-v3 item 3.1): the one table of outcomes, steps, fields, choices and limits.

Every place that writes or shows a board record reads this module: the coordinator's meeting form (meetings.record_decision, strict),
the old routes and the board tab (postboard.record_decision, not strict), the later correction by the owner's consultant
(postboard.correct_record), the minutes, the deck, the FHIR export and the NCG VTB export. The web form reads the same table as JSON
(`python -m tumour_board.decision_record --write` writes web/tb-nik/src/features/meetings/decision_fields.json; a unit test checks the
file equals spec()).

The record holds what the board said. Vaidyx never suggests a decision, a modality or an intent: the only defaults are the owner
doctor pre-filled in the form, the responsible clinician as the one who tells the patient, and the date 2 working days after the
meeting (postboard.record_decision). Over-limit text is refused with a plain message, never cut. Dates are ISO in storage.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

OUTCOMES = {"decision": "Decision recorded", "deferred": "Deferred: information awaited",
            "referred": "Referred to another board or centre", "not_discussed": "Not discussed", "noted": "Noted for information"}
OUTCOME_HINTS = {"decision": "The board decided", "deferred": "Something is awaited", "referred": "To another board or centre",
                 "not_discussed": "Moves to the next meeting", "noted": "For noting only"}
LIMITS = {"name": 120, "short": 300, "long": 2000, "decision": 4000, "rationale": 4000, "note": 2000}
STEPS = [("outcome", "Outcome"), ("recommendation", "The board's recommendation"), ("considered", "What the board considered"),
         ("next", "What happens next"), ("responsibility", "Responsibility and telling the patient"), ("pmjay", "PM-JAY and attendance")]
YN = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}, {"id": "not_applicable", "label": "Not applicable"}, {"id": "not_stated", "label": "Not stated"}]
ALL_OUTCOMES = list(OUTCOMES)
MIN_DECISION = 5
SPEC_PATH = Path(__file__).resolve().parents[1] / "web" / "tb-nik" / "src" / "features" / "meetings" / "decision_fields.json"


def _c(*pairs):
    return [{"id": i, "label": l} for i, l in pairs]


CHOICES = {
    "not_discussed_reason": _c(("information_missing", "Information missing"), ("member_absent", "A member was absent"), ("time", "Time ran out"), ("other", "Other reason")),
    "intent": _c(("curative", "Curative"), ("palliative", "Palliative"), ("not_stated", "Not stated by the board")),
    "modalities": _c(("surgery", "Surgery"), ("chemotherapy", "Chemotherapy"), ("radiotherapy", "Radiotherapy"), ("endocrine", "Endocrine therapy"),
                     ("targeted", "Targeted therapy"), ("immunotherapy", "Immunotherapy"), ("supportive", "Supportive or palliative care"),
                     ("observation", "Observation"), ("other", "Other")),
    "stage_source": _c(("report", "As recorded in a report"), ("confirmed_draft", "A Vaidyx draft stage a doctor confirmed"), ("board", "The board's own"), ("not_staged", "Not staged")),
    "trial_considered": _c(("yes", "Yes"), ("no", "No"), ("not_stated", "Not stated")),
    "supportive_needs": _c(("physical", "Physical"), ("psychological", "Psychological"), ("social", "Social"), ("information", "Information"),
                           ("spiritual", "Spiritual"), ("none", "None")),
    "consent_recorded": _c(("yes", "Yes"), ("pending", "Pending"), ("no", "No"), ("not_stated", "Not stated")),
    "referral_kind": _c(("genetics", "Genetics and counselling"), ("palliative", "Palliative care"), ("nutrition", "Nutrition"), ("psycho_oncology", "Psycho-oncology"),
                        ("fertility", "Fertility preservation"), ("dental", "Dental"), ("physiotherapy", "Physiotherapy"), ("social_work", "Social work"), ("other", "Other")),
    "pmjay_plan_approval": _c(("yes", "Yes"), ("no", "No"), ("not_applicable", "Not applicable")),
}


def _f(key, label, kind, step, **kw):
    return {"key": key, "label": label, "kind": kind, "step": step, **{k: v for k, v in kw.items() if v is not None}}


FIELDS = [
    _f("outcome", "Outcome", "choice", "outcome", required=ALL_OUTCOMES),
    _f("awaited", "What is awaited", "short", "outcome", limit=300, required=["deferred"], reason=True),
    _f("awaited_from", "From which department", "dept", "outcome", limit=120, required=["deferred"], reason=True, source="departments"),
    _f("referred_to", "Referred to (board or centre)", "short", "outcome", limit=300, required=["referred"], reason=True),
    _f("not_discussed_reason", "Why not discussed", "choice", "outcome", choices="not_discussed_reason", required=["not_discussed"], reason=True),
    _f("decision_text", "Decision, in the board's words", "long", "recommendation", limit=4000, required=["decision"], reason=True),
    _f("rationale", "Rationale as discussed", "long", "recommendation", limit=4000, reason=True),
    _f("intent", "Treatment intent", "choice", "recommendation", choices="intent", required=["decision"], reason=True),
    _f("intent_as_stated", "Intent, in the board's words", "short", "recommendation", limit=300, reason=True),
    _f("modalities", "Modalities", "multi", "recommendation", choices="modalities", reason=True),
    _f("sequence", "Sequence", "short", "recommendation", limit=300, reason=True, hint="As the board stated it, for example surgery then adjuvant chemotherapy"),
    _f("alternatives_discussed", "Alternatives discussed", "long", "recommendation", limit=2000, reason=True),
    _f("concerns", "Divergent views and concerns (name and words)", "concerns", "recommendation", limit={"by": 120, "text": 2000}, reason=True),
    _f("stage_as_agreed", "Stage as agreed by the board", "short", "recommendation", limit=300, reason=True),
    _f("stage_source", "Where the stage comes from", "choice", "recommendation", choices="stage_source", reason=True),
    _f("report_corrections_raised", "Report errors or corrections raised", "long", "recommendation", limit=2000, reason=True),
    _f("patient_preference", "Patient preference considered", "yn", "considered"),
    _f("patient_preference_note", "Patient preference, in words", "short", "considered", limit=300),
    _f("fitness_considered", "Fitness and comorbidities considered", "yn", "considered"),
    _f("trial_considered", "Clinical trial considered", "choice", "considered", choices="trial_considered"),
    _f("trial_name", "Trial name and requirements", "short", "considered", limit=300),
    _f("genomic_considered", "Genomic or genetic testing considered", "yn", "considered"),
    _f("supportive_needs", "Supportive and psychosocial needs", "multi", "considered", choices="supportive_needs", after=True),
    _f("consent_recorded", "Patient consent to the discussion", "choice", "considered", choices="consent_recorded"),
    _f("investigations", "Further investigations", "investigations", "next", limit={"item": 300, "department": 120}, source="departments"),
    _f("referrals", "Referrals", "referrals", "next", choices="referral_kind", limit={"note": 300, "department": 120}, source="departments"),
    _f("next_step", "Next step", "short", "next", limit=300),
    _f("next_step_date", "By date", "date", "next"),
    _f("next_review", "Next review", "date", "next"),
    _f("next_review_trigger", "Or the trigger for re-discussion", "short", "next", limit=300, hint="For example after the restaging CT"),
    _f("responsible_doctor", "Responsible clinician", "person", "responsibility", limit=120, required=["decision"], source="owner_doctor"),
    _f("key_worker", "Key worker", "short", "responsibility", limit=120, after=True, hint="Name and contact"),
    _f("informed_by", "Who tells the patient", "person", "responsibility", limit=120, hint="Vaidyx fills the responsible clinician when empty"),
    _f("inform_by_date", "Tell the patient by", "date", "responsibility", hint="Vaidyx fills 2 working days after the meeting when empty"),
    _f("patient_informed_date", "Date the patient was told", "date", "responsibility", after=True),
    _f("gp_informed_date", "Date the referring doctor was informed", "date", "responsibility", after=True),
    _f("pmjay_plan_approval", "PM-JAY treatment plan approval", "choice", "pmjay", choices="pmjay_plan_approval", after=True),
    _f("pmjay_plan_note", "Plan or approval reference", "short", "pmjay", limit=300, after=True),
    _f("members_present", "Members present", "people", "pmjay", limit=120, source="admitted_members"),
]
BY_KEY = {f["key"]: f for f in FIELDS}
KEYS = [f["key"] for f in FIELDS]
LIST_KINDS = ("multi", "people", "concerns", "investigations", "referrals")
TEXT_KINDS = ("short", "long", "person", "dept")
_YN_IDS = [x["id"] for x in YN]
_REQUIRED_MESSAGE = {
    "outcome": "Choose the outcome.",
    "decision_text": f"Write the board's decision (at least {MIN_DECISION} characters).",
    "intent": "Choose the treatment intent (curative, palliative or not stated by the board).",
    "responsible_doctor": "Name the responsible clinician.",
    "awaited": "Say what is awaited.",
    "awaited_from": "Say which department it is awaited from.",
    "referred_to": "Say where the Case File is referred to.",
    "not_discussed_reason": "Say why the Case File was not discussed.",
}


def _fold(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def _fold_long(v) -> str:
    """Spaces folded inside each line; line breaks kept (at most one empty line in a row), the ends trimmed."""
    lines = [" ".join(x.split()) for x in str(v if v is not None else "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _too_long(label, limit, text) -> str:
    return f"{label}: at most {limit} characters ({len(text)} written). Shorten it."


def _choice_ids(name) -> list[str]:
    return [x["id"] for x in CHOICES.get(name) or []]


def _match_choice(v, ids, labels) -> str | None:
    """The choice id for a value given as its id or its label, any case; "" for empty; None when it is not one of them."""
    s = _fold(v)
    if not s:
        return ""
    k = s.lower().replace(" ", "_").replace("-", "_")
    if k in ids:
        return k
    for i, l in labels.items():
        if s.lower() == l.lower():
            return i
    return None


def _labels(name) -> dict:
    if name == "outcome":
        return dict(OUTCOMES)
    if name == "yn":
        return {x["id"]: x["label"] for x in YN}
    return {x["id"]: x["label"] for x in CHOICES.get(name) or []}


def _parse_date(v):
    from .docstatus import parse_date
    s = _fold(v)
    if not s:
        return ""
    return parse_date(s) or None


def _rows(v):
    if v is None or v == "":
        return []
    if isinstance(v, dict):
        return [v]
    if isinstance(v, (list, tuple)):
        return list(v)
    return None


def join_concerns(concerns) -> str:
    """The old one-line `divergent_opinions` from the concern rows: "Name: words; Name: words"."""
    return "; ".join(f"{x['by']}: {x['text']}" if x.get("by") else x["text"] for x in concerns or [] if isinstance(x, dict) and x.get("text"))


def _outcome_of(body) -> str:
    return _fold(body.get("outcome") or body.get("outcome_type") or "")


def clean(body: dict, *, strict: bool) -> dict:
    """Every FIELDS key normalised: whitespace folded (line breaks kept in long text), choices checked, dates ISO, list rows cleaned, ""
    for an absent scalar and [] for an absent list. Over-limit text is refused, never cut. strict=True (the coordinator's meeting form,
    a correction) also applies the required-by-outcome rule. Compatibility keys: intent_as_recorded (= intent), divergent_opinions
    (joined from the concerns), deferred_reason. ValueError with every problem in plain words."""
    body = body if isinstance(body, dict) else {}
    out, errs = {}, []
    oc_raw = _outcome_of(body)
    oc = _match_choice(oc_raw, ALL_OUTCOMES, OUTCOMES) if oc_raw else ""
    if oc is None:
        raise ValueError(f"The outcome must be one of: {', '.join(OUTCOMES)}.")
    if not oc and not strict:
        oc = "decision"
    out["outcome"] = oc
    for f in FIELDS[1:]:
        k, kind, label = f["key"], f["kind"], f["label"]
        v = body.get(k)
        if kind in TEXT_KINDS:
            s = _fold_long(v) if kind == "long" else _fold(v)
            if len(s) > f["limit"]:
                errs.append(_too_long(label, f["limit"], s))
            out[k] = s
        elif kind == "date":
            iso = _parse_date(v)
            if iso is None:
                errs.append(f"{label}: not a valid date ({_fold(v)}). Write it as DD/MM/YYYY.")
                iso = ""
            out[k] = iso
        elif kind in ("choice", "yn"):
            name = "yn" if kind == "yn" else f["choices"]
            ids = _YN_IDS if kind == "yn" else _choice_ids(name)
            got = _match_choice(v, ids, _labels(name))
            if got is None:
                errs.append(f"{label}: choose one of {', '.join(_labels(name).values())}.")
                got = ""
            out[k] = got
        elif kind == "multi":
            rows = _rows(v) if not isinstance(v, str) else [x for x in v.split(",")]
            vals = []
            for x in rows or []:
                got = _match_choice(x, _choice_ids(f["choices"]), _labels(f["choices"]))
                if got is None:
                    errs.append(f"{label}: {_fold(x)} is not one of the choices.")
                elif got and got not in vals:
                    vals.append(got)
            if rows is None:
                errs.append(f"{label}: give a list of choices.")
            out[k] = vals
        elif kind == "people":
            rows = _rows(v) if not isinstance(v, str) else [x for x in v.split(",")]
            vals = []
            for x in rows or []:
                s = _fold(x.get("name") if isinstance(x, dict) else x)
                if len(s) > f["limit"]:
                    errs.append(_too_long(f"{label} ({s[:30]})", f["limit"], s))
                elif s and s not in vals:
                    vals.append(s)
            if rows is None:
                errs.append(f"{label}: give a list of names.")
            out[k] = vals
        else:
            rows = _rows(v)
            if rows is None:
                errs.append(f"{label}: give a list of rows.")
                rows = []
            out[k] = _clean_rows(f, rows, strict, errs)
    # the old free-text intent keys: the intent as a choice only when the words match a choice (research 02, rule 4)
    if not out["intent"]:
        for old in (body.get("intent_as_recorded"), out["intent_as_stated"]):
            got = _match_choice(old, _choice_ids("intent"), _labels("intent")) if old else None
            if got:
                out["intent"] = got
                break
    if strict:
        errs += [_REQUIRED_MESSAGE[k] for k in missing_required(out)]
    if errs:
        raise ValueError(" ".join(dict.fromkeys(errs)))
    out["intent_as_recorded"] = out["intent"]
    out["divergent_opinions"] = join_concerns(out["concerns"]) or _fold(body.get("divergent_opinions"))
    if oc == "deferred" and out["awaited"]:
        out["deferred_reason"] = out["awaited"] + (f" (from {out['awaited_from']})" if out["awaited_from"] else "")
    else:
        out["deferred_reason"] = _fold(body.get("deferred_reason"))
    return out


def _clean_rows(f, rows, strict, errs) -> list[dict]:
    k, label, lim = f["key"], f["label"], f["limit"]
    out = []
    for n, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            r = {"text": r} if k == "concerns" else {"item": r} if k == "investigations" else {"note": r}
        if k == "concerns":
            by, text = _fold(r.get("by")), _fold_long(r.get("text"))
            if not by and not text:
                continue
            if len(by) > lim["by"]:
                errs.append(_too_long(f"{label}, row {n}, name", lim["by"], by))
            if len(text) > lim["text"]:
                errs.append(_too_long(f"{label}, row {n}", lim["text"], text))
            if not text:
                if strict:
                    errs.append(f"{label}, row {n}: write the words of the view or concern.")
                continue
            if strict and not by:
                errs.append(f"{label}, row {n}: name who raised it.")
            row = {"by": by, "text": text}
            if r.get("user"):
                row["user"] = _fold(r["user"])
            if r.get("from_card"):
                row["from_card"] = True
            out.append(row)
        elif k == "investigations":
            item, dept = _fold(r.get("item") or r.get("task")), _fold(r.get("department"))
            due = _parse_date(r.get("due"))
            if not item and not dept and not due:
                continue
            if len(item) > lim["item"]:
                errs.append(_too_long(f"{label}, row {n}", lim["item"], item))
            if len(dept) > lim["department"]:
                errs.append(_too_long(f"{label}, row {n}, department", lim["department"], dept))
            if due is None:
                errs.append(f"{label}, row {n}: the due date is not a valid date ({_fold(r.get('due'))}). Write it as DD/MM/YYYY.")
                due = ""
            if not item:
                errs.append(f"{label}, row {n}: write the investigation.")
                continue
            out.append({"item": item, "department": dept, "due": due})
        else:  # referrals
            kind_raw, dept, note = r.get("kind"), _fold(r.get("department")), _fold(r.get("note"))
            kind = _match_choice(kind_raw, _choice_ids("referral_kind"), _labels("referral_kind"))
            if not kind and not dept and not note:
                continue
            if kind is None:
                errs.append(f"{label}, row {n}: {_fold(kind_raw)} is not one of the kinds of referral.")
                continue
            if len(note) > lim["note"]:
                errs.append(_too_long(f"{label}, row {n}", lim["note"], note))
            if len(dept) > lim["department"]:
                errs.append(_too_long(f"{label}, row {n}, department", lim["department"], dept))
            if not kind:
                if strict:
                    errs.append(f"{label}, row {n}: choose the kind of referral.")
                    continue
                kind = "other"
            out.append({"kind": kind, "department": dept, "note": note})
    return out


def missing_required(record: dict) -> list[str]:
    """The field keys the record's outcome needs and does not have (an unknown or empty outcome: ["outcome"])."""
    record = record if isinstance(record, dict) else {}
    oc = _outcome_of(record)
    if oc not in OUTCOMES:
        return ["outcome"]
    out = []
    for f in FIELDS[1:]:
        if oc not in (f.get("required") or []):
            continue
        v = record.get(f["key"])
        if f["key"] == "decision_text":
            if len(_fold(v)) < MIN_DECISION:
                out.append("decision_text")
        elif not (v if not isinstance(v, str) else v.strip()):
            out.append(f["key"])
    return out


def spec() -> dict:
    """The table the web form reads (decision_fields.json)."""
    return {"outcomes": [{"id": k, "label": v, "hint": OUTCOME_HINTS[k]} for k, v in OUTCOMES.items()],
            "steps": [{"id": i, "title": t} for i, t in STEPS], "fields": copy.deepcopy(FIELDS), "choices": copy.deepcopy(CHOICES),
            "limits": dict(LIMITS), "yn": copy.deepcopy(YN)}


def spec_json() -> str:
    return json.dumps(spec(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _empty(f):
    return [] if f["kind"] in LIST_KINDS else ""


def form_fields(record: dict) -> dict:
    """The snapshot of every FIELDS key of a record (kept with each version)."""
    record = record if isinstance(record, dict) else {}
    out = {}
    for f in FIELDS:
        k = f["key"]
        v = record.get(k)
        if k == "outcome" and not v:
            v = record.get("outcome_type") or ""
        out[k] = copy.deepcopy(v) if v is not None else _empty(f)
    return out


def reason_needed(changed_keys) -> bool:
    """True when a change touches a field whose correction needs a reason (the decision, intent, divergent views, stage...)."""
    return any((BY_KEY.get(k) or {}).get("reason") for k in changed_keys or [])


def label(key: str) -> str:
    return (BY_KEY.get(key) or {}).get("label") or key.replace("_", " ").capitalize()


def choice_label(key: str, value) -> str:
    """The label of a choice value ("curative" -> "Curative"); a list joins its labels; an unknown value comes back as given."""
    f = BY_KEY.get(key) or {}
    name = "outcome" if key == "outcome" else "yn" if f.get("kind") == "yn" else f.get("choices") or ""
    labels = _labels(name) if name else {}
    if isinstance(value, (list, tuple)):
        return ", ".join(labels.get(str(x), str(x)) for x in value)
    return labels.get(str(value or ""), str(value or ""))


def dmy(iso) -> str:
    s = str(iso or "")[:10]
    try:
        return date.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return s


def add_working_days(iso: str, n: int = 2) -> str:
    """The date n working days after `iso` (Monday to Saturday are working days in India: only Sundays are skipped)."""
    d = date.fromisoformat(str(iso)[:10])
    left = n
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:
            left -= 1
    return d.isoformat()


def value_text(key: str, value) -> str:
    """One field's value as shown in the minutes, the deck and the exports: choice labels, dates DD/MM/YYYY, list rows as
    "item (department, due DD/MM/YYYY)"; "" when empty."""
    f = BY_KEY.get(key) or {}
    kind = f.get("kind")
    if value in (None, "", [], {}):
        return ""
    if kind in ("choice", "yn", "multi"):
        return choice_label(key, value)
    if kind == "date":
        return dmy(value)
    if kind == "people":
        return ", ".join(str(x) for x in value if x)
    if kind == "concerns":
        return "; ".join((f"{x.get('by')}: " if x.get("by") else "") + str(x.get("text") or "") for x in value if isinstance(x, dict) and x.get("text"))
    if kind == "investigations":
        out = []
        for x in value:
            if isinstance(x, dict) and x.get("item"):
                extra = ", ".join(p for p in (x.get("department") or "", f"due {dmy(x['due'])}" if x.get("due") else "") if p)
                out.append(x["item"] + (f" ({extra})" if extra else ""))
        return "; ".join(out)
    if kind == "referrals":
        out = []
        for x in value:
            if isinstance(x, dict) and x.get("kind"):
                extra = ", ".join(p for p in (x.get("department") or "", x.get("note") or "") if p)
                out.append(choice_label("referrals", x["kind"]) + (f" ({extra})" if extra else ""))
        return "; ".join(out)
    return str(value)


def display_lines(record: dict, skip=()) -> list[dict]:
    """[{key, label, text}] for every field with a value, in step order (the outcome itself first), then the correction line when
    the record was corrected. `skip`: keys the caller shows another way."""
    record = record if isinstance(record, dict) else {}
    vals = form_fields(record)
    if not vals.get("intent") and record.get("intent_as_recorded"):  # records from before item 3.1 keep their old keys
        vals["intent"] = record["intent_as_recorded"]
    if not vals.get("awaited") and record.get("deferred_reason"):
        vals["awaited"] = record["deferred_reason"]
    out = []
    for f in FIELDS:
        k = f["key"]
        if k in skip:
            continue
        t = value_text(k, vals.get(k))
        if not t and k == "concerns":
            t = _fold(record.get("divergent_opinions"))
        if t:
            out.append({"key": k, "label": f["label"], "text": t})
    line = corrected_line(record)
    if line and "corrected" not in skip:
        out.append({"key": "corrected", "label": "Correction", "text": line})
    return out


def corrected_line(record: dict) -> str:
    """"Corrected by <name> on DD/MM/YYYY: <reason>" for a record its owner's consultant corrected; "" otherwise."""
    c = (record or {}).get("corrected") if isinstance(record, dict) else None
    if not isinstance(c, dict) or not c.get("at"):
        return ""
    return f"Corrected by {c.get('by_name') or c.get('by') or 'a consultant'} on {dmy(c['at'])}" + (f": {c['reason']}" if c.get("reason") else "")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--write" in argv:
        SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
        SPEC_PATH.write_text(spec_json(), encoding="utf-8")
        print(f"Wrote {SPEC_PATH}")
        return 0
    sys.stdout.write(spec_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
