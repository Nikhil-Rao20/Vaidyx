"""After the Tumour Board: recorded decision, AI-assisted adjudication, scheduling and the longitudinal timeline.

The board's decision is entered by a clinician. The agent never decides; it checks the RECORD:
  1. documentation rules from the protocol (decision text, recorded by, actions with a Responsible Department and due date);
  2. values quoted in the decision vs the verified source values (possible transcription discrepancy, e.g. 6% vs 60%);
  3. decision recorded while Pre-Authorization items were still open (documentation consistency);
  4. board composition: PM-JAY HBP 2.2 asks for surgical, radiation and medical oncologists (V1 item 7.1); an agent never counts;
  5. guideline checks (V1 item 7.2, dosecheck.py): drug doses and radiotherapy schedules as written vs the dose references of the
     Case File's cancer (Indian first, each with its page and verbatim line), the stage as written vs the stage recorded in signed reports.
Flags go to expert review; the agent does not decide which value is clinically correct.

Human over the loop (V1 item 7.3): each flag is resolved by a person as corrected (the new value amends the decision: a new version,
every version kept), intentional deviation (reason required: deviating from a guideline is not an error) or false alarm. Each
resolution is a clinician confirmation (resolve_flag: audited, undoable). The decision counts as final when every flag is resolved."""
import asyncio
import re
import uuid

from . import dates, dosecheck, followup, grounding, llm, negation, org, protocol, rules, store, units

NOT_LISTED = "Case File not listed: no Pre-Authorization check to compare with"

# PM-JAY HBP 2.2 (s 3.9 Medical Oncology, p 27; repeated in the radiation oncology section, p 33): the tumour board "should include a highly trained team of Surgical, Radiation and Medical
# Oncologist" (V1 item 7.1). Present means marked present in the attendance or named as a member; an AI support agent never counts.
PMJAY_BOARD = ("surgical_oncology", "radiation_oncology", "medical_oncology")
PMJAY_SPECIALIST = {"surgical_oncology": "Surgical Oncologist", "radiation_oncology": "Radiation Oncologist", "medical_oncology": "Medical Oncologist"}
PMJAY_REFERENCE = {"org": "PM-JAY / National Health Authority, India", "region": "India", "title": "NHA HBP 2.2 manual 2021",
                   "file": "pmjay/NHA-HBP-2.2-manual-2021.pdf", "page": 27,
                   "quote": "that should include a highly trained team of Surgical, Radiation and Medical Oncologist"}
_SPECIALTY_WORDS = {  # free-text participants ("Dr A (Med Onc), Dr B (Surg Onc)"); a bare "Oncology" is not enough to tell which
    "medical_oncology": re.compile(r"\bmed(?:ical)?\.?\s*onc(?:o|ology|ologist)?\b", re.I),
    "surgical_oncology": re.compile(r"\bsurg(?:ical)?\.?\s*onc(?:o|ology|ologist)?\b|\bonco[- ]?surg(?:eon|ery)\b", re.I),
    "radiation_oncology": re.compile(r"\brad(?:iation)?\.?\s*onc(?:o|ology|ologist)?\b|\bradiotherap(?:y|ist)\b", re.I)}
_AGENT_WORDS = re.compile(r"\bagents?\b|\bAI\b|\bartificial intelligence\b")
_ABSENT_PART = re.compile(r"^\s*(?:absent|apologies|not present|not attended)\b", re.I)

CLAIMS_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"claims": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "properties": {
        "fact": {"type": "string", "enum": None}, "value_as_written": {"type": "string"}, "span": {"type": "string", "description": "exact text from the decision"}},
    "required": ["fact", "value_as_written", "span"]}}}, "required": ["claims"]}


# result negations first (shared cues in negation.py): "non-amplified" must never read as "amplified"
_NEG = r"\b(" + negation.NON + r"|negative|not detected|no mutation detected|no (pathogenic )?(variant|alteration)s? detected|wild[- ]?type|absent|not amplified|no evidence of|not seen|not identified|free of|without)\b|\b" + negation.NO + r"\b"
_POS = r"\b(positive|detected|detectable|mutated|mutation present|present|amplified|evidence of|seen|identified|involved|suspicious)\b"


def _polarity(s):
    import re as _re
    s = (s or "").lower()
    if _re.search(_NEG, s):
        return "neg"
    if _re.search(_POS, s):
        return "pos"
    return None


def _nums(s):
    return [float(x) for x in grounding.numbers(s)]


def attendance_from_members(members):
    """{"present", "members"} from members typed on the Board tab ([{"name", "department"}]), the same shape a board session gives."""
    out = []
    for m in members or []:
        if not isinstance(m, dict) or not str(m.get("name", "")).strip():
            continue
        did = org.department_id(str(m.get("department", "")))
        out.append({"name": str(m["name"]).strip()[:120], "department": did or "", "department_name": org.department_name(did) if did else str(m.get("department", ""))[:80]})
    present = list(dict.fromkeys(m["department_name"] for m in out if m["department"]))
    return {"present": present, "absent": [], "members": out}


def _piece_departments(piece):
    """Department ids one participant entry names: "Dr B (Surg Onc)", "Dr C (Radiology)", "Pathology"."""
    out = {did for did, rx in _SPECIALTY_WORDS.items() if rx.search(piece)}
    for chunk in [*re.findall(r"\(([^)]*)\)", piece), re.sub(r"\([^)]*\)", " ", piece)]:
        did = org.department_id(chunk.strip())
        if did and not re.fullmatch(r"(?:gi\s+)?oncology", chunk.strip(), re.I):  # a bare "Oncology" does not say which oncologist
            out.add(did)
    return out


def recorded_stage(facts):
    """The stage as recorded by a reporting clinician in a signed report (V1 item 7.2): the newest verified value from a final document,
    never from an earlier board record; a clinician-confirmed value stands on its own. None when no signed report records a stage."""
    hist = ((facts or {}).get("recorded_stage") or {}).get("history") or []
    ok = [e for e in hist if e.get("verification") in rules.VERIFIED and e.get("doc_final") and e.get("state", "present") == "present"
          and e.get("doc_type") != "tumour_board_record"]
    if not ok:
        return None
    e = ok[-1]
    return {"value": e["value"], "quote": "" if e.get("confirmed_by") else (e.get("quote") or ""), "doc_id": e["doc_id"], "doc_title": e.get("doc_title") or e["doc_id"]}


def composition(record):
    """Which of PM-JAY's three oncology specialties were present (V1 item 7.1). From the structured attendance when the record has one
    (Board room session, or members typed with their department), else from the participants text. Returns {"checked", "how",
    "present", "missing", "reference"}; "checked" is False when nothing says which specialties were there."""
    att = record.get("attendance") if isinstance(record.get("attendance"), dict) else {}
    present, how = set(), None
    if att.get("present") or att.get("members"):
        how = "attendance"
        for name in att.get("present") or []:
            present.add(org.department_id(str(name)))
        for m in att.get("members") or []:
            if isinstance(m, dict) and not _AGENT_WORDS.search(str(m.get("name", ""))):
                present.add(org.department_id(str(m.get("department") or "")) or org.department_id(str(m.get("department_name") or "")))
    else:
        named_any = False
        for part in re.split(r"[;\n]", str(record.get("participants") or "")):
            if _ABSENT_PART.search(part):
                continue  # "absent: Radiation Oncology" (the session's participants text)
            for piece in part.split(","):
                depts = _piece_departments(piece)
                named_any = named_any or bool(depts)
                if not _AGENT_WORDS.search(piece):  # "Radiation Oncology (AI support agent)": an agent is never a member
                    present |= depts
        how = "participants text" if named_any else None
    present.discard(None)
    found = [d for d in PMJAY_BOARD if d in present]
    return {"checked": how is not None, "how": how, "present": found, "missing": [d for d in PMJAY_BOARD if d not in present] if how else [],
            "reference": PMJAY_REFERENCE}


def _composition_flag(comp):
    ref = PMJAY_REFERENCE
    cite = f"PM-JAY HBP 2.2 (p {ref['page']}): the tumour board \"{ref['quote'].removeprefix('that ')}\""
    if not comp["checked"]:
        return {"kind": "composition", "severity": "review", "missing": list(PMJAY_BOARD), "reference": ref,
                "text": f"PM-JAY board composition not checked: the record does not say which specialties were present. {cite}. "
                        "Add the members present with their departments."}
    if comp["missing"]:
        who = ", ".join(PMJAY_SPECIALIST[d] for d in comp["missing"])
        return {"kind": "composition", "severity": "review", "missing": comp["missing"], "reference": ref,
                "text": f"PM-JAY board composition: no {who} recorded as present at this board. {cite}. An AI support agent does not count as a member."}
    return None


async def adjudicate(case_id, record):
    au = store.auditor(case_id)
    case = store.get_case(case_id)
    listed = bool(case.get("protocol"))  # an unlisted Case File (V1 item 2.5) has no protocol and no Pre-Authorization gate
    flags = []
    if not listed:
        flags.append({"kind": "consistency", "severity": "review", "text": NOT_LISTED})
    for f in (protocol.get(case["protocol"]).get("post_board", {}).get("required_record_fields", []) if listed else []):
        if not record.get(f):
            flags.append({"kind": "documentation", "severity": "review", "field": f, "text": f"Decision record is missing: {f.replace('_', ' ')}"})
    # Victorian Cancer MDM quality framework: errors or changes to pathology / radiology reports raised at the meeting must be recorded
    if re.search(r"\b(discrepan|correct(ed|ion)|amend|error|wrong|revise|mis-?report|typo)", record.get("decision_text", ""), re.I) and not record.get("report_corrections_raised"):
        flags.append({"kind": "documentation", "severity": "review", "text": "The decision text mentions a correction or discrepancy; record it under 'Report corrections raised at the meeting'"})
    for i, a in enumerate(record.get("actions") or []):
        if not a.get("department"):
            flags.append({"kind": "documentation", "severity": "review", "text": f"Action {i + 1} has no Responsible Department"})
        if not a.get("due"):
            flags.append({"kind": "documentation", "severity": "review", "text": f"Action {i + 1} has no due date"})
    comp = composition(record)  # PM-JAY: surgical, radiation and medical oncologist (V1 item 7.1)
    if _composition_flag(comp):
        flags.append(_composition_flag(comp))
    gate = (store.get_state(case_id).get("gate") or {}) if listed else {}
    open_items = [r["label"] for r in gate.get("requirements", []) if r["status"] not in ("satisfied", "not_applicable")]
    if open_items:
        flags.append({"kind": "consistency", "severity": "review", "text": "Decision recorded while these Pre-Authorization items were open: " + "; ".join(open_items)})
    # value claims in the decision text vs verified source values
    cat = protocol.facts()
    fact_ids = list(cat.keys())
    schema = {**CLAIMS_SCHEMA}
    schema["properties"] = {"claims": {**CLAIMS_SCHEMA["properties"]["claims"]}}
    schema["properties"]["claims"]["items"] = {**CLAIMS_SCHEMA["properties"]["claims"]["items"]}
    schema["properties"]["claims"]["items"]["properties"] = {**CLAIMS_SCHEMA["properties"]["claims"]["items"]["properties"], "fact": {"type": "string", "enum": fact_ids}}
    spec = ", ".join(f"{k} ({v['label']})" for k, v in cat.items())
    msg = [{"role": "system", "content": "You list the patient data values quoted in a Tumour Board decision record. Copy them exactly. Do not judge them."},
           {"role": "user", "content": f"Known fields: {spec}\n\nDECISION RECORD:\n{record.get('decision_text', '')}\n\nList every value in the record that "
            "corresponds to one of the known fields (for example a biomarker percentage, a lab value, a tumour size, a stage as quoted). "
            "If there are none, return an empty list."}]
    facts = rules.resolve_facts(rules.case_docs(case_id), store.get_state(case_id).get("overrides"))  # attestations (V1 item 1.2) and confirmations (2.2) count
    # the value listing and the guideline checks (V1 item 7.2) are independent reasoner calls: run together
    claims_call = llm.chat("reasoner", msg, json_schema=schema, max_tokens=700, purpose="adjudication: values in decision", audit=au)
    guide_call = dosecheck.check_decision(record.get("decision_text", ""), case["protocol"], recorded_stage(facts), audit=au) if listed else None
    got = await asyncio.gather(claims_call, *([guide_call] if guide_call else []), return_exceptions=True)
    claims = []
    if isinstance(got[0], BaseException):
        flags.append({"kind": "system", "severity": "info", "text": f"Value check unavailable: {str(got[0])[:120]}"})
    else:
        claims = (got[0] or {}).get("claims", [])
    guide = None
    if guide_call:
        if isinstance(got[1], BaseException):
            flags.append({"kind": "system", "severity": "info", "text": f"Guideline checks unavailable: {str(got[1])[:120]}"})
        else:
            guide = got[1]
    checks = []
    for c in claims:
        if c.get("span") and not grounding.locate(c["span"], [record.get("decision_text", "")]):
            continue  # model must quote the decision text itself
        src = facts.get(c["fact"], {}).get("current")
        if not src or src["verification"] not in rules.VERIFIED:
            checks.append({**c, "result": "no_verified_source", "source": None})
            continue
        if src.get("confirmed_by"):  # a clinician-confirmed value is compared on its own (the model's quote may carry the value it replaced)
            src = {**src, "quote": ""}
        src_text = src["value"] + " " + (src.get("quote") or "")
        a, b = _nums(c["value_as_written"]), _nums(src_text)
        # every number the board wrote must exist in the source value / quote, as is or as the same quantity in other units (V1 item 3.5)
        if a and b and not set(a) <= set(b) and not units.numbers_equivalent(c["value_as_written"], src_text):
            res = "discrepancy"
            flags.append({"kind": "transcription", "severity": "expert_review", "fact": c["fact"],
                          "text": f"Possible transcription discrepancy: {cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source value \"{src['value']}\"",
                          "recorded": c["value_as_written"], "span": c.get("span") or "", "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        elif _polarity(c["value_as_written"]) and _polarity(src_text) and _polarity(c["value_as_written"]) != _polarity(src_text):
            res = "discrepancy"  # polarity flip: 'negative' recorded where the source says positive, or the reverse
            flags.append({"kind": "transcription", "severity": "expert_review", "fact": c["fact"],
                          "text": f"Possible polarity discrepancy: {cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source states \"{src['value']}\"",
                          "recorded": c["value_as_written"], "span": c.get("span") or "", "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        elif not a and _polarity(c["value_as_written"]) and _polarity(c["value_as_written"]) == _polarity(src["value"]):
            res = "consistent"
        elif not a and grounding.norm(c["value_as_written"]) not in grounding.norm(src["value"]) and grounding.norm(src["value"]) not in grounding.norm(c["value_as_written"]):
            res = "wording_differs"
            flags.append({"kind": "transcription", "severity": "review", "fact": c["fact"],
                          "text": f"{cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source states \"{src['value']}\"",
                          "recorded": c["value_as_written"], "span": c.get("span") or "", "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        else:
            res = "consistent"
        checks.append({**c, "result": res, "source": {"value": src["value"], "doc_id": src["doc_id"], "quote": src["quote"],
                                                       **({"confirmed_by": src["confirmed_by"]} if src.get("confirmed_by") else {})}})
    if guide:
        flags += guide["flags"]
    for i, f in enumerate(flags):
        f["id"] = f"F{i + 1}"  # flags are resolved by id (V1 item 7.3)
    au({"kind": "adjudication", "flags": len(flags), "claims": len(claims)})
    # information-only items (a check that found no guideline reference) need no resolution; a check that could not run still shows
    attention = any(needs_resolution(f) or f.get("kind") == "system" for f in flags)
    return {"flags": flags, "value_checks": checks, "composition": comp, "guideline_checks": {"checks": (guide or {}).get("checks", []), "ran": guide is not None},
            "status": "flag_for_expert_review" if attention else "consistent", "evaluated": store.now_iso()}


async def record_decision(case_id, record, user=""):
    record = {**record, "id": "B" + uuid.uuid4().hex[:6], "recorded_at": store.now_iso(), "entered_by": user}
    if record.get("members") and not record.get("attendance"):  # members typed with their departments on the Board tab (V1 item 7.1)
        record["attendance"] = attendance_from_members(record.pop("members"))
        if not str(record.get("participants") or "").strip():
            record["participants"] = ", ".join(f"{m['name']} ({m['department_name']})" if m["department_name"] else m["name"] for m in record["attendance"]["members"])
    record.pop("members", None)
    record["adjudication"] = await adjudicate(case_id, record)
    _versions(record)
    record["resolution"] = resolution_status(record)
    st = store.get_state(case_id)
    st.setdefault("board_records", []).append(record)
    # board actions become follow-up requests in the Responsible Department's inbox, the department notified (V1 item 7.4)
    st.setdefault("actions", []).extend(followup.board_actions(case_id, record, by=user))
    if record.get("next_review"):
        st["next_review"] = {"date": record["next_review"], "from_record": record["id"]}
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_record", "record": record["id"], "by": user, "flags": len(record["adjudication"]["flags"])})
    return record


# ---- human over the loop: flag resolution and the amended decision (V1 item 7.3) -----------------------------------------
NEEDS_RESOLUTION = ("review", "expert_review")
RESOLUTION_LABEL = {"corrected": "Corrected", "intentional_deviation": "Intentional deviation", "false_alarm": "False alarm"}


def needs_resolution(flag) -> bool:
    """Review and expert-review flags are resolved by a person; information-only items (no guideline reference found, a check that
    could not run) are not."""
    return (flag or {}).get("severity") in NEEDS_RESOLUTION


def _flags(record):
    flags = (record.get("adjudication") or {}).get("flags") or []
    for i, f in enumerate(flags):
        f.setdefault("id", f"F{i + 1}")  # records adjudicated before 7.3 get their ids on first use, in the same order
    return flags


def resolution_status(record) -> dict:
    """{"final", "open", "resolved", "total", "open_flags"}: the decision counts as final when every flag needing a person is resolved."""
    need = [f for f in _flags(record) if needs_resolution(f)]
    open_ids = [f["id"] for f in need if not f.get("resolution")]
    return {"final": not open_ids, "open": len(open_ids), "resolved": len(need) - len(open_ids), "total": len(need), "open_flags": open_ids}


def _versions(record):
    """Every version of the decision is kept; version 1 is the decision as recorded."""
    if not record.get("versions"):
        record["versions"] = [{"version": 1, "decision_text": record.get("decision_text", ""), "at": record.get("recorded_at"),
                               "by": record.get("entered_by", ""), "reason": "Recorded by the Tumour Board"}]
        record["version"] = 1
    return record["versions"]


def _new_version(record, by, reason, change):
    vs = _versions(record)
    v = {"version": vs[-1]["version"] + 1, "decision_text": record.get("decision_text", ""), "at": store.now_iso(), "by": by, "reason": reason,
         "change": change, **{k: record.get(k) for k in ("participants", "recorded_by") if record.get(k) is not None}}
    vs.append(v)
    record["version"] = v["version"]
    return v


def _amend(record, flag, value, by):
    """Apply a correction; returns the change {"field", "from", "to"} kept with the new version (and used to undo it).
    A value written in the decision text (the flag's span) is replaced inside that span; a missing record field is filled in; a board
    composition correction is added to the participants; anything else is added to the decision as an amendment line."""
    text = record.get("decision_text", "")
    span, recorded = flag.get("span") or "", flag.get("recorded") or ""
    if flag.get("field") and flag["field"] not in ("decision_text", "actions"):  # actions are a list: their correction is an amendment line
        old = record.get(flag["field"])
        new = value if not old else f"{old}; {value}"
        record[flag["field"]] = new
        return {"field": flag["field"], "from": old or "", "to": new}
    if flag.get("kind") == "composition":
        old = record.get("participants") or ""
        new = f"{old}; {value}" if old else value
        record["participants"] = new
        return {"field": "participants", "from": old, "to": new}
    if span and text.count(span) == 1:
        new_span = span.replace(recorded, value, 1) if recorded and recorded in span else value
        record["decision_text"] = text.replace(span, new_span, 1)
        return {"field": "decision_text", "from": span, "to": new_span}
    if recorded and text.count(recorded) == 1:
        record["decision_text"] = text.replace(recorded, value, 1)
        return {"field": "decision_text", "from": recorded, "to": value}
    line = f"Amendment ({flag['id']}): {value}"
    record["decision_text"] = text.rstrip() + "\n" + line
    return {"field": "decision_text", "from": "", "to": "\n" + line}


def _revert(record, change) -> bool:
    """Take one correction back without touching later ones; False when the corrected text is no longer there as written."""
    field, old, new = change.get("field"), change.get("from", ""), change.get("to", "")
    if field == "decision_text":
        text = record.get("decision_text", "")
        if not new or text.count(new) != 1:
            return False
        record["decision_text"] = text.replace(new, old, 1)
        return True
    if record.get(field) != new:
        return False
    record[field] = old
    return True


def _find_record(st, record_id):
    rec = next((b for b in st.get("board_records") or [] if b.get("id") == record_id), None)
    if not rec:
        raise KeyError("board record not found")
    return rec


def _undo_correction(record, flag, by, why):
    """If the flag's current resolution amended the decision, take that amendment back (a new version)."""
    res = flag.get("resolution") or {}
    if res.get("resolution") != "corrected" or not res.get("change"):
        return None
    ok = _revert(record, res["change"])
    if not ok:  # the text changed since: say so in the decision rather than guess
        record["decision_text"] = record.get("decision_text", "").rstrip() + f"\nAmendment withdrawn ({flag['id']}): {res['change'].get('to', '').strip()}"
    return _new_version(record, by, f"{why}: correction of {flag['id']} taken back", {"flag": flag["id"], "undo_of": res.get("version"), "reverted": ok})


def resolve_flag(case_id, record_id, flag_id, resolution, value="", reason="", by=""):
    """A person resolves one flag of a board record: corrected (value required; the decision is amended, version + 1), intentional
    deviation (reason required) or false alarm. Recorded as a resolve_flag confirmation (audited, undoable); a new resolution of the
    same flag supersedes the old one (a previous correction is taken back first). Returns the record. Caller holds the Case File lock.
    ValueError for invalid input, KeyError for an unknown record or flag."""
    st = store.get_state(case_id)
    rec = _find_record(st, record_id)
    flag = next((f for f in _flags(rec) if f["id"] == flag_id), None)
    if not flag:
        raise KeyError("flag not found")
    if not needs_resolution(flag):
        raise ValueError("This item is information only; it needs no resolution")
    from . import confirm
    clean = confirm.validate("resolve_flag", f"{record_id}:{flag_id}", {"resolution": resolution, "value": value}, reason)
    conf = confirm.record(case_id, "resolve_flag", clean["key"], clean["fields"], clean["reason"], by)  # saves the confirmation
    st = store.get_state(case_id)
    rec = _find_record(st, record_id)
    flag = next(f for f in _flags(rec) if f["id"] == flag_id)
    _versions(rec)
    _undo_correction(rec, flag, by, "Resolution changed")
    if flag.get("resolution"):
        flag.setdefault("resolution_history", []).append({**flag["resolution"], "superseded_by": conf["id"]})
    res = {"resolution": clean["fields"]["resolution"], "value": clean["fields"]["value"], "reason": clean["reason"], "by": by, "at": conf["at"], "confirmation": conf["id"]}
    if res["resolution"] == "corrected":
        change = _amend(rec, flag, res["value"], by)
        v = _new_version(rec, by, f"{flag['id']} corrected: \"{flag.get('recorded') or change['from'].strip() or flag['text'][:60]}\" to \"{res['value']}\"", {"flag": flag_id, **change})
        res.update({"change": change, "version": v["version"]})
    flag["resolution"] = res
    rec["resolution"] = resolution_status(rec)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_flag_resolved", "record": record_id, "flag": flag_id, "resolution": res["resolution"], "value": res["value"],
                          "reason": res["reason"], "by": by, "confirmation": conf["id"], "version": rec.get("version", 1), "final": rec["resolution"]["final"]})
    return rec


def undo_resolution(case_id, conf_id, by=""):
    """Undo one flag resolution (the resolve_flag confirmation is marked undone, kept); a correction is taken back as a new version.
    Returns the record, or None when the confirmation belongs to no flag any more. Caller holds the Case File lock."""
    from . import confirm
    rec_c = confirm.undo(case_id, conf_id, by)
    record_id, _, flag_id = rec_c["key"].partition(":")
    st = store.get_state(case_id)
    try:
        rec = _find_record(st, record_id)
    except KeyError:
        return None
    flag = next((f for f in _flags(rec) if f["id"] == flag_id), None)
    if not flag or (flag.get("resolution") or {}).get("confirmation") != conf_id:
        return None
    _versions(rec)
    _undo_correction(rec, flag, by, "Resolution undone")
    flag.setdefault("resolution_history", []).append({**flag.pop("resolution"), "undone_by": by, "undone_at": store.now_iso()})
    rec["resolution"] = resolution_status(rec)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_flag_resolution_undone", "record": record_id, "flag": flag_id, "by": by, "confirmation": conf_id,
                          "version": rec.get("version", 1), "final": rec["resolution"]["final"]})
    return rec


def timeline(case_id):
    ev = []
    for d in rules.case_docs(case_id):  # confirmed dates and document types (V1 item 2.2)
        c = d.get("classification") or {}
        dd = dates.doc_dates(d)  # the timeline uses the event date (V1 item 3.1)
        if dd["event"]:
            ev.append({"date": dd["event"], "kind": "document", "doc_type": c.get("doc_type"), "title": c.get("title") or d["filename"],
                       "status": c.get("status"), "doc_id": d["doc_id"], "report_date": dd["report"], "date_assumed": dd["event_assumed"]})
    st = store.get_state(case_id)
    for b in st.get("board_records", []):
        ev.append({"date": (b.get("board_date") or b["recorded_at"])[:10], "kind": "board", "title": "Tumour Board decision recorded", "record": b["id"]})
    for a in st.get("actions", []):
        ev.append({"date": a["due"], "kind": "action", "title": f"{a['label']} ({a['department']})", "status": a["status"], "action": a["id"]})
    if st.get("next_review"):
        ev.append({"date": st["next_review"]["date"], "kind": "review", "title": "Next Tumour Board review"})
    return sorted(ev, key=lambda e: e["date"])
