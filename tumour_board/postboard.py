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
_AGENT_WORDS = re.compile(r"(?i:\bagents?\b|\bartificial intelligence\b)|\bAI\b")  # "Agent", "agent", "AI support" (AI in capitals only)
_ABSENT_WORDS = re.compile(r"\b(?:absent|apologies|not present|not attended|did not attend|on leave|unavailable|excused)\b", re.I)
_HEADING = re.compile(r"\b(absent|apologies|not present|present|in attendance|attended|attending)\s*:", re.I)  # "Present: ... Absent: ..."

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
    never from an earlier board record; a clinician-confirmed value stands on its own. None when no signed report records a stage.
    The FIGO stage as recorded (cervix, V1 item 9.2) is a stage as recorded too: both fields are read, newest by event / report date."""
    hist = ((facts or {}).get("recorded_stage") or {}).get("history") or []
    figo = ((facts or {}).get("figo_stage") or {}).get("history") or []
    if figo:
        hist = sorted(hist + figo, key=lambda e: (e.get("date") or "", e.get("report_date") or ""))
    ok = [e for e in hist if e.get("verification") in rules.VERIFIED and e.get("doc_final") and e.get("state", "present") == "present"
          and e.get("doc_type") != "tumour_board_record"]
    if not ok:
        return None
    e = ok[-1]
    return {"value": e["value"], "quote": "" if e.get("confirmed_by") else (e.get("quote") or ""), "doc_id": e["doc_id"], "doc_title": e.get("doc_title") or e["doc_id"],
            **({"confirmed_by": e["confirmed_by"]} if e.get("confirmed_by") else {})}


def _text_present(text):
    """(department ids present, any specialty named) from a participants text. Parts are cut at commas, semicolons, line ends and
    headings ("Present:", "Absent:"); a part is absent when it says so anywhere ("absent: Dr C (Rad Onc)", "Rad Onc not present",
    "Dr C (Rad Onc) on leave") or sits under an absent heading; a part naming an agent never counts; a specialty that is both present
    and absent somewhere in the text is not counted as present (a person checks it)."""
    heads = [(m.start(), m.group(1).lower()) for m in _HEADING.finditer(text)]
    cuts = sorted({0, len(text)} | {p for p, _ in heads} | {m.end() for m in re.finditer(r"[,;\n]", text)})
    present, absent, named = set(), set(), False
    for a, b in zip(cuts, cuts[1:]):
        piece = text[a:b]
        depts = _piece_departments(piece)
        if not depts:
            continue
        named = True
        head = next((h for p, h in reversed(heads) if p <= a), "present")
        if _ABSENT_WORDS.search(piece) or head in ("absent", "apologies", "not present"):
            absent |= depts
        elif not _AGENT_WORDS.search(piece):  # "Radiation Oncology (AI support agent)": an agent is never a member
            present |= depts
    return present - absent, named


NOT_EMPANELLED = "The hospital is not PM-JAY empanelled, so the HBP 2.2 board composition requirement does not apply"


def pmjay_seat(present: set, own=None) -> dict:
    """The surgical seat for PM-JAY (V2 item 6.4): a Surgical Oncologist present fills it; otherwise a surgeon present from one of the
    hospital's surgical departments fills it, without a note when that department is on the hospital's PM-JAY surgical oncology list
    (default Surgical Oncology, Gynaecologic Oncology, Orthopaedic Oncology) and with "check PM-JAY requirement" when it is not.
    `own`: the Case File's own surgical departments (board._case_surgical): a surgeon from a department outside the PM-JAY list fills
    the seat only when it is one of them (plan 6.2; Phase 6 review M1). None: any surgical department (a session-level count).
    Returns {"filled", "filled_by", "check", "note"}; `present` is a set of department ids."""
    h = org.hospital()
    pmj = {org.department_id(x) for x in h.get("pmjay_surgical_oncology") or []} - {None}
    surg = {org.department_id(x) for x in h.get("surgical_departments") or []} - {None}
    if "surgical_oncology" in present:
        return {"filled": True, "filled_by": ["surgical_oncology"], "check": False, "note": ""}
    listed = sorted(d for d in present if d in pmj)
    if listed:
        return {"filled": True, "filled_by": listed, "check": False,
                "note": f"Surgical seat filled by {', '.join(org.department_name(d) for d in listed)} (on the hospital's PM-JAY surgical oncology list)"}
    other = sorted(d for d in present if d in surg and (own is None or d in set(own)))
    if other:
        return {"filled": True, "filled_by": other, "check": True,
                "note": f"Surgical seat filled by {', '.join(org.department_name(d) for d in other)}: check the PM-JAY requirement, which names a Surgical Oncologist"}
    return {"filled": False, "filled_by": [], "check": False, "note": ""}


def pmjay_present(present: set, own=None) -> set:
    """The PM-JAY specialties counted present: the three oncologists, with the surgical seat filled as pmjay_seat() says (V2 item 6.4)."""
    out = {d for d in PMJAY_BOARD if d in present}
    if pmjay_seat(present, own)["filled"]:
        out.add("surgical_oncology")
    return out


def composition(record, own=None):
    """Which of PM-JAY's three oncology specialties were present (V1 item 7.1). From the structured attendance when the record has one
    (Board room session, or members typed with their department), else from the participants text. Returns {"checked", "how",
    "present", "missing", "reference", "seat", "seat_note"}; "checked" is False when nothing says which specialties were there. V2 item
    6.4: only for a PM-JAY empanelled hospital (hospital setting, default yes); otherwise {"checked": False, "not_applicable": True} and
    no flag; the surgical seat may be filled by a surgeon of the Case File's department, with "check PM-JAY requirement" when that
    department is outside the hospital's surgical oncology list. Never a block; an AI support agent never counts."""
    if not org.hospital().get("pmjay_empanelled", True):
        return {"checked": False, "not_applicable": True, "how": None, "present": [], "missing": [], "reference": PMJAY_REFERENCE, "reason": NOT_EMPANELLED,
                "seat": {"filled": False, "filled_by": [], "check": False, "note": ""}, "seat_note": ""}
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
        present, named_any = _text_present(str(record.get("participants") or ""))
        how = "participants text" if named_any else None
    present.discard(None)
    seat = pmjay_seat(present, own) if how else {"filled": False, "filled_by": [], "check": False, "note": ""}
    counted = pmjay_present(present, own) if how else set()
    found = [d for d in PMJAY_BOARD if d in counted]
    return {"checked": how is not None, "how": how, "present": found, "missing": [d for d in PMJAY_BOARD if d not in counted] if how else [],
            "reference": PMJAY_REFERENCE, "seat": seat, "seat_note": seat["note"]}


def _composition_flag(comp):
    ref = PMJAY_REFERENCE
    cite = f"PM-JAY HBP 2.2 (p {ref['page']}): the tumour board \"{ref['quote'].removeprefix('that ')}\""
    if comp.get("not_applicable"):  # not an empanelled hospital: no requirement, no flag (V2 item 6.4)
        return None
    if not comp["checked"]:
        return {"kind": "composition", "severity": "review", "missing": list(PMJAY_BOARD), "reference": ref,
                "text": f"PM-JAY board composition not checked: the record does not say which specialties were present. {cite}. "
                        "Add the members present with their departments."}
    if comp["missing"]:
        who = ", ".join(PMJAY_SPECIALIST[d] for d in comp["missing"])
        return {"kind": "composition", "severity": "review", "missing": comp["missing"], "reference": ref,
                "text": f"PM-JAY board composition: no {who} recorded as present at this board. {cite}. An AI support agent does not count as a member."
                        + (f" {comp['seat_note']}." if comp.get("seat_note") else "")}
    if (comp.get("seat") or {}).get("check"):  # the seat is filled, by a surgeon outside the hospital's PM-JAY surgical oncology list (V2 item 6.4)
        return {"kind": "composition", "severity": "review", "missing": [], "check": "surgical_seat", "reference": ref,
                "text": f"PM-JAY board composition: {comp['seat_note']}. {cite}. A flag for review, not a block; an AI support agent does not count as a member."}
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
    from . import board as _board
    comp = composition(record, own=_board._case_surgical(case))  # PM-JAY: surgical, radiation and medical oncologist (V1 item 7.1); the seat per Case File (6.2 / 6.4)
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
    flags += outcome_flags(record)  # outcome and patient-facing items (12 Oct)
    for i, f in enumerate(flags):
        f["id"] = f"F{i + 1}"  # flags are resolved by id (V1 item 7.3)
    au({"kind": "adjudication", "flags": len(flags), "claims": len(claims)})
    # information-only items (a check that found no guideline reference) need no resolution; a check that could not run still shows
    attention = any(needs_resolution(f) or f.get("kind") == "system" for f in flags)
    return {"flags": flags, "value_checks": checks, "composition": comp, "guideline_checks": {"checks": (guide or {}).get("checks", []), "ran": guide is not None},
            "status": "flag_for_expert_review" if attention else "consistent", "evaluated": store.now_iso()}


# ---- outcome of the discussion and what the board recorded about the patient (12 Oct) ----------------------------------------
# CRUK 2017: a case not discussed because information was missing must be recorded; Victorian MDM framework 2018 8.4 / 8.5: the
# recommendation reaches the patient (lead clinician) and the GP within a week; Manual for Cancer Services 13-2N-113: key worker named;
# NHS England 2020: clinical trial availability and suitability recorded; HBCR 2025: intention to treat as recorded by the board.
OUTCOMES = {"decision": "Decision recorded", "deferred": "Deferred: information awaited", "referred": "Referred to another board or centre",
            "not_discussed": "Not discussed: information missing"}
INTENTS = ("", "curative", "palliative", "not_stated")
YES_NO = ("", "yes", "no", "not_stated")
COMMUNICATION_FIELDS = ("patient_informed_date", "informed_by", "key_worker", "intent_as_recorded", "trial_considered", "consent_recorded")
COMM_SOURCES = {"patient_informed_date": "Victorian MDM framework 2018 (8.5)", "key_worker": "Manual for Cancer Services 2013 (13-2N-113)",
                "trial_considered": "NHS England, Streamlining MDT meetings 2020 (minimum core data)", "intent_as_recorded": "HBCR procedure manual 2025 (intention to treat)",
                "consent_recorded": "Victorian MDM framework 2018 (5.2)"}


def clean_record_fields(record: dict) -> dict:
    """The outcome and communication fields as stored: enums checked, text trimmed, dates ISO (ValueError with a plain message)."""
    from .docstatus import parse_date
    out = dict(record)
    oc = str(out.get("outcome_type") or "decision").strip()
    if oc not in OUTCOMES:
        raise ValueError(f"outcome_type must be one of {', '.join(OUTCOMES)}")
    out["outcome_type"] = oc
    for k in ("deferred_reason", "referred_to", "informed_by", "key_worker"):
        out[k] = str(out.get(k) or "").strip()[:300]
    d = str(out.get("patient_informed_date") or "").strip()
    if d:
        iso = parse_date(d)
        if not iso:
            raise ValueError(f"Not a valid date: {d}")
        d = iso
    out["patient_informed_date"] = d
    for k, allowed in (("intent_as_recorded", INTENTS), ("trial_considered", YES_NO), ("consent_recorded", YES_NO)):
        v = str(out.get(k) or "").strip()
        if v not in allowed:
            raise ValueError(f"{k} must be one of: {', '.join(x or 'empty' for x in allowed)}")
        out[k] = v
    return out


def outcome_flags(record: dict) -> list:
    """Documentation flags about the outcome and the patient-facing items. Review: a deferred or not-discussed case with no action saying
    what is awaited; a referral with no destination. Information only (no resolution needed, counted on the dashboard): patient not yet
    informed, key worker, trial consideration, intent and consent not recorded."""
    flags = []
    oc = record.get("outcome_type") or "decision"
    if oc in ("deferred", "not_discussed") and not (record.get("actions") or []):
        flags.append({"kind": "documentation", "severity": "review", "field": "actions",
                      "text": f"{OUTCOMES[oc]}: add an action saying which record or result is awaited and from which department (CRUK 2017: a case not discussed for missing information must be recorded with the reason)"})
    if oc == "referred" and not record.get("referred_to"):
        flags.append({"kind": "documentation", "severity": "review", "field": "referred_to", "text": "Referred: record the board or centre the Case File was referred to"})
    if oc == "decision":
        if not record.get("patient_informed_date"):
            flags.append({"kind": "communication", "severity": "info", "field": "patient_informed_date", "source": COMM_SOURCES["patient_informed_date"],
                          "text": "Patient not yet recorded as informed of the outcome (record the date once the lead clinician has told the patient; a follow-up action is open)"})
        if not record.get("key_worker"):
            flags.append({"kind": "communication", "severity": "info", "field": "key_worker", "source": COMM_SOURCES["key_worker"], "text": "Key worker (name and contact) not recorded"})
        if not record.get("trial_considered"):
            flags.append({"kind": "communication", "severity": "info", "field": "trial_considered", "source": COMM_SOURCES["trial_considered"], "text": "Clinical trial availability and suitability not recorded as considered"})
        if not record.get("intent_as_recorded"):
            flags.append({"kind": "communication", "severity": "info", "field": "intent_as_recorded", "source": COMM_SOURCES["intent_as_recorded"], "text": "Intention to treat, as the board recorded it, not stated (curative / palliative)"})
        if not record.get("consent_recorded"):
            flags.append({"kind": "communication", "severity": "info", "field": "consent_recorded", "source": COMM_SOURCES["consent_recorded"], "text": "Patient consent to the discussion not recorded"})
    return flags


def update_communication(case_id, record_id, fields: dict, user="") -> dict:
    """Set the patient-communication fields of a recorded decision later (who informed the patient and when, key worker, intent, trial,
    consent). Not a change of the decision: no new version; kept in the record's history and audited. Completes the open
    'Inform the patient' follow-up action when a date is given."""
    st = store.get_state(case_id)
    rec = next((b for b in st.get("board_records") or [] if b["id"] == record_id), None)
    if not rec:
        raise KeyError(record_id)
    allowed = {k: v for k, v in (fields or {}).items() if k in COMMUNICATION_FIELDS}
    clean = clean_record_fields({**rec, **allowed})
    changed = {k: clean[k] for k in COMMUNICATION_FIELDS if clean.get(k) != rec.get(k)}
    for k, v in changed.items():
        rec[k] = v
    rec.setdefault("communication_history", []).append({"ts": store.now_iso(), "by": user, "changed": changed})
    adj = rec.get("adjudication") or {}  # the information flags follow the fields; every other flag stays as it is
    kept = [f for f in adj.get("flags") or [] if f.get("kind") != "communication"]
    new = [f for f in outcome_flags(rec) if f.get("kind") == "communication"]
    for i, f in enumerate(new):
        f["id"] = f"K{i + 1}"
    adj["flags"] = kept + new
    rec["resolution"] = resolution_status(rec)
    closed = []
    if rec.get("patient_informed_date"):
        for a in st.get("actions") or []:
            if a.get("board_record") == record_id and a.get("communication") and a.get("status") != "completed":
                a["status"] = "completed"; a["completed"] = store.now_iso()
                a.setdefault("history", []).append({"ts": store.now_iso(), "event": f"Patient recorded as informed on {rec['patient_informed_date']} by {rec.get('informed_by') or user}"})
                closed.append(a["id"])
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_record_communication", "record": record_id, "by": user, "changed": changed, "actions_closed": closed})
    return rec


async def record_decision(case_id, record, user=""):
    record = clean_record_fields(record)
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
    comm = followup.communication_action(case_id, record, by=user)  # the patient must be told; a follow-up until the date is recorded (12 Oct)
    if comm:
        st["actions"].append(comm)
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
    """{"final", "open", "resolved", "total", "open_flags", "checks_complete"}: the decision counts as final when every flag needing a
    person is resolved and every check ran (a check that could not run leaves the record not final: review finding M8)."""
    flags = _flags(record)
    need = [f for f in flags if needs_resolution(f)]
    open_ids = [f["id"] for f in need if not f.get("resolution")]
    complete = not any(f.get("kind") == "system" for f in flags)
    return {"final": not open_ids and complete, "open": len(open_ids), "resolved": len(need) - len(open_ids), "total": len(need),
            "open_flags": open_ids, "checks_complete": complete}


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


def _token_at(text, token, lo=0, hi=None):
    """Positions of `token` in text[lo:hi] as a whole value: never inside a longer number or word ("40 mg/m2" is not in "140 mg/m2")."""
    hi = len(text) if hi is None else hi
    rx = re.compile(r"(?<![\w.])" + re.escape(token) + r"(?!\w)")
    return [m.start() for m in rx.finditer(text, lo, hi)]


def _amend(record, flag, value):
    """Apply a correction; returns the change kept with the new version (and used to undo it).
    Decision text: the recorded value is replaced where it stands, inside the flag's span when the decision holds the span once and the
    value once in it, else where the value stands once in the whole decision ({"field", "at", "from", "to"}); the rest of the decision is
    never rewritten. A missing record field is filled in; a composition correction is added to the participants; anything else becomes an
    amendment line at the end of the decision."""
    text = record.get("decision_text", "")
    span, recorded = flag.get("span") or "", (flag.get("recorded") or "").strip()
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
    at = None
    if recorded:
        spans = _token_at(text, span) if span else []
        inside = _token_at(text, recorded, spans[0], spans[0] + len(span)) if len(spans) == 1 else []
        anywhere = _token_at(text, recorded)
        at = inside[0] if len(inside) == 1 else anywhere[0] if len(anywhere) == 1 else None
    if at is not None:
        record["decision_text"] = text[:at] + value + text[at + len(recorded):]
        return {"field": "decision_text", "at": at, "from": recorded, "to": value}
    line = f"Amendment ({flag['id']}): {value}"
    record["decision_text"] = text.rstrip() + "\n" + line
    return {"field": "decision_text", "at": len(text.rstrip()), "from": text[len(text.rstrip()):], "to": "\n" + line}


def _revert_plan(record, change):
    """How to take one correction back without touching later ones: (field, new value) or None when the corrected text is no longer
    there as written (a later correction changed it: that one is undone first)."""
    field, old, new = change.get("field"), change.get("from", ""), change.get("to", "")
    cur = record.get(field) if field != "decision_text" else record.get("decision_text", "")
    if field != "decision_text":
        return (field, old) if cur == new else None
    at = change.get("at")
    if isinstance(at, int) and cur[at:at + len(new)] == new and (not new.strip() or at in _token_at(cur, new) or new.startswith("\n")):
        return field, cur[:at] + old + cur[at + len(new):]
    hits = [k for k in _token_at(cur, new.strip()) if new.strip()] if new.strip() else []
    if len(hits) == 1:  # moved by an earlier change of different length
        k = hits[0] - (len(new) - len(new.lstrip()))
        return field, cur[:k] + old + cur[k + len(new):]
    return None


def _find_record(st, record_id):
    rec = next((b for b in st.get("board_records") or [] if b.get("id") == record_id), None)
    if not rec:
        raise KeyError("board record not found")
    return rec


def _check_undoable(record, flag):
    """ValueError when the flag's correction can no longer be taken back as written (a later correction changed the same words)."""
    res = flag.get("resolution") or {}
    if res.get("resolution") == "corrected" and res.get("change") and _revert_plan(record, res["change"]) is None:
        raise ValueError(f"The correction of {flag['id']} was changed again by a later correction; undo that one first")


def _undo_correction(record, flag, by, why):
    """If the flag's current resolution amended the decision, take that amendment back (a new version). Call _check_undoable first."""
    res = flag.get("resolution") or {}
    if res.get("resolution") != "corrected" or not res.get("change"):
        return None
    field, value = _revert_plan(record, res["change"])
    record[field] = value
    return _new_version(record, by, f"{why}: correction of {flag['id']} taken back", {"flag": flag["id"], "undo_of": res.get("version")})


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
    if clean["fields"]["resolution"] == "corrected" and flag.get("recorded") and clean["fields"]["value"] == flag["recorded"].strip():
        raise ValueError("The corrected value is the same as the recorded one: choose False alarm or Intentional deviation instead")
    _check_undoable(rec, flag)  # before anything is recorded
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
        change = _amend(rec, flag, res["value"])
        v = _new_version(rec, by, f"{flag['id']} corrected: \"{flag.get('recorded') or flag['text'][:60]}\" to \"{res['value']}\"", {"flag": flag_id, **change})
        res.update({"change": change, "version": v["version"]})
    flag["resolution"] = res
    rec["resolution"] = resolution_status(rec)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_flag_resolved", "record": record_id, "flag": flag_id, "resolution": res["resolution"], "value": res["value"],
                          "reason": res["reason"], "by": by, "confirmation": conf["id"], "version": rec.get("version", 1), "final": rec["resolution"]["final"]})
    return rec


def undo_resolution(case_id, conf_id, by=""):
    """Undo one flag resolution (the resolve_flag confirmation is marked undone, kept); a correction is taken back as a new version.
    Returns the record, or None when the confirmation belongs to no flag any more. ValueError (nothing changed) when a later correction
    changed the same words. Caller holds the Case File lock."""
    from . import confirm
    rec_c = next((c for c in store.get_state(case_id).get("confirmations") or [] if c["id"] == conf_id), None)
    record_id, _, flag_id = (rec_c or {}).get("key", "").partition(":")
    st = store.get_state(case_id)
    rec = next((b for b in st.get("board_records") or [] if b.get("id") == record_id), None)
    flag = next((f for f in _flags(rec) if f["id"] == flag_id), None) if rec else None
    mine = bool(flag and (flag.get("resolution") or {}).get("confirmation") == conf_id)
    if mine:
        _check_undoable(rec, flag)  # before the confirmation is marked undone
    confirm.undo(case_id, conf_id, by)
    if not mine:
        return None
    st = store.get_state(case_id)
    rec = _find_record(st, record_id)
    flag = next(f for f in _flags(rec) if f["id"] == flag_id)
    _versions(rec)
    _undo_correction(rec, flag, by, "Resolution undone")
    flag.setdefault("resolution_history", []).append({**flag.pop("resolution"), "undone_by": by, "undone_at": store.now_iso()})
    rec["resolution"] = resolution_status(rec)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_flag_resolution_undone", "record": record_id, "flag": flag_id, "by": by, "confirmation": conf_id,
                          "version": rec.get("version", 1), "final": rec["resolution"]["final"]})
    return rec


TREND_FIELDS = ["ecog", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "cea", "lesion_size", "suv_max", "depth_of_invasion", "distance_from_anal_verge"]


def _first_number(s):
    for x in grounding.numbers(s or ""):
        try:
            return float(x.replace(",", ""))
        except ValueError:
            continue
    return None


def trends(case_id, state=None):
    """Verified values of the numeric fields over time (labs, markers, sizes, performance status): every entry of the history with its
    document, date and quote, oldest first; the number is the first number written in the value, the units as written. A table for the
    board, never an interpretation (12 Oct)."""
    st = state if state is not None else store.get_state(case_id)
    facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    cat = protocol.facts()
    out = []
    for fid in TREND_FIELDS:
        hist = [e for e in (facts.get(fid) or {}).get("history") or [] if e.get("verification") in rules.VERIFIED and e.get("state", "present") == "present" and e.get("value")]
        if len(hist) < 2:
            continue
        rows = []
        for e in sorted(hist, key=lambda x: (x.get("date") or "", x.get("report_date") or "")):
            loc = e.get("location") or {}
            rows.append({"date": e.get("date"), "value": e["value"], "number": _first_number(e["value"]), "doc_id": e["doc_id"], "doc_title": e.get("doc_title"),
                         "final": bool(e.get("doc_final")), "status": e.get("doc_status"), "quote": e.get("quote") or "", "page": loc.get("page"), "start": loc.get("start"), "end": loc.get("end"),
                         **({"source_method": e["source_method"]} if e.get("source_method") else {}), **({"confirmed_by": e["confirmed_by"]} if e.get("confirmed_by") else {})})
        nums = [r["number"] for r in rows if r["number"] is not None]
        out.append({"field": fid, "label": cat.get(fid, {}).get("label", fid), "rows": rows, "max": max(nums) if nums else None, "min": min(nums) if nums else None})
    return out


def _protocol_label(pid) -> str:
    try:
        from . import protocol
        return (protocol.get(pid) or {}).get("label") or str(pid)
    except Exception:
        return str(pid)


def timeline(case_id):
    ev = []
    for d in rules.case_docs(case_id):  # confirmed dates and document types (V1 item 2.2)
        c = d.get("classification") or {}
        dd = dates.doc_dates(d)  # the timeline uses the event date (V1 item 3.1)
        if dd["event"]:
            ev.append({"date": dd["event"], "kind": "document", "doc_type": c.get("doc_type"), "title": c.get("title") or d["filename"],
                       "status": c.get("status"), "doc_id": d["doc_id"], "report_date": dd["report"], "date_assumed": dd["event_assumed"]})
    for e in ((store.get_case(case_id) or {}).get("his") or {}).get("encounters") or []:  # OP visits and IP admissions from the HIS (V2 item 3.4)
        if e.get("start"):
            title = ("IP admission " if e.get("kind") == "IP" else "OP visit ") + str(e.get("number") or "") + (f", {e['department']}" if e.get("department") else "") + (f", {e['unit']}" if e.get("unit") else "")
            ev.append({"date": str(e["start"])[:10], "kind": "encounter", "encounter_kind": e.get("kind"), "number": e.get("number"), "title": title, "end": str(e.get("end") or "")[:10],
                       "ward_history": e.get("ward_history") or [], "status": e.get("status")})
    for r in (store.get_case(case_id) or {}).get("referrals") or []:  # referrals and the ownership moves they made (V2 item 5.2)
        if isinstance(r, dict) and r.get("at"):
            from . import org
            frm, to = org.department_name(r.get("from")), org.department_name(r.get("to"))
            ev.append({"date": str(r["at"])[:10], "kind": "referral", "title": f"Referred from {frm} to {to}", "status": r.get("status"), "referral": r.get("id"), "reason": r.get("reason")})
            if r.get("status") == "accepted" and r.get("answered_at"):
                ev.append({"date": str(r["answered_at"])[:10], "kind": "referral", "title": f"Referral accepted: {to} owns the Case File" + (f", listed under {_protocol_label(r['protocol_after'])}" if r.get("protocol_after") else ""),
                           "status": "owner_changed", "referral": r.get("id")})
    st = store.get_state(case_id)
    for b in st.get("board_records", []):
        ev.append({"date": (b.get("board_date") or b["recorded_at"])[:10], "kind": "board", "title": "Tumour Board decision recorded", "record": b["id"]})
    for a in st.get("actions", []):  # a suggested request has no due date yet (V2 item 4.2): it sits on the day the gap was found
        day = str(a.get("due") or a.get("created") or "")[:10]
        if day:
            ev.append({"date": day, "kind": "action", "title": f"{a['label']} ({a['department']})", "status": a["status"], "action": a["id"]})
    if st.get("next_review"):
        ev.append({"date": st["next_review"]["date"], "kind": "review", "title": "Next Tumour Board review"})
    return sorted(ev, key=lambda e: e["date"])
