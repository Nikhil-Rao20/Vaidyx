"""The fill-in summary (18 Oct, new interface /tb-nik, SPEC 3.5): the Case File page's checklist, built from the protocol and the gate.

A slot template per protocol is built at request time, with no model: every protocol record and every required fact becomes a line
in its section, in board order (presenting history and performance status; pathology; imaging; labs and tumour markers; staging data as
recorded; prior treatment; board question; other records). Each line shows a value only as a verified verbatim quote with its source
(document, page) from rules.resolve_facts, or a blank with the actions the doctor can take in place: ask the department (the gate's
suggested request, sent through dept_requests), not needed (a waive confirmation), enter a value (a short fixed list: ECOG, menopausal
status, weight, height, the board question; shown "entered by Dr X, no report"), review (a confirmation the gate asks for: final version,
document type, date, patient match, a value read from a scan, two reports that disagree), remind (a sent request).

Typed values live in case.json "typed_values" {fact_id: {value, by, at, note}} (audited "typed_value") and reach the Pre-Authorization
gate through rules.typed_overlay (a clearly marked overlay: verification "entered_by_doctor", no quote, never shown as a verified value and
never used by the summary, the briefs or Q&A). Nothing here diagnoses, stages or advises: the lines are the records and their gaps."""
import re

from . import access, confirm, dept_requests, discord, org, protocol, rules, scanned, store

SECTIONS = [("presenting", "Presenting history and performance status"), ("pathology", "Pathology"), ("imaging", "Imaging"),
            ("labs", "Labs and tumour markers"), ("staging", "Staging data as recorded"), ("prior_treatment", "Prior treatment"),
            ("question", "Board question"), ("other", "Other records")]
SECTION_LABEL = dict(SECTIONS)
DOC_SECTION = {"clinical_note": "presenting", "referral": "presenting", "discharge_summary": "presenting",
               "histopathology": "pathology", "cytology": "pathology", "ihc": "pathology", "molecular": "pathology",
               "ct": "imaging", "mri": "imaging", "xray": "imaging", "ultrasound": "imaging", "mammogram": "imaging", "pet_ct": "imaging", "bone_scan": "imaging",
               "lab": "labs", "treatment_summary": "prior_treatment", "tumour_board_record": "prior_treatment",
               "endoscopy": "other", "operative_note": "other", "pulmonary_function": "other", "other": "other"}
FACT_SECTION = {"presenting_complaint": "presenting", "ecog": "presenting", "smoking_history": "presenting", "tobacco_use": "presenting",
                "menopausal_status": "presenting", "comorbidities": "presenting", "diagnosis_date_mode": "presenting", "patient_preference": "presenting", "patient_awareness": "presenting",
                "clinical_trial_note": "presenting", "weight": "presenting", "height": "presenting", "dental_evaluation": "other",
                "clinical_question": "question", "recorded_stage": "staging", "figo_stage": "staging",
                "histologic_type": "pathology", "grade": "pathology", "lvi": "pathology", "pni": "pathology", "margins": "pathology", "depth_of_invasion": "pathology",
                "ene": "pathology", "pdl1": "pathology", "egfr": "pathology", "alk": "pathology", "ros1": "pathology", "met": "pathology", "kras": "pathology",
                "er": "pathology", "pr": "pathology", "her2": "pathology", "ki67": "pathology", "mmr": "pathology", "ras_braf": "pathology",
                "lesion_size": "imaging", "nodal_findings": "imaging", "distant_findings": "imaging", "comparison_prior": "imaging", "suv_max": "imaging",
                "parametrial_involvement": "imaging", "distance_from_anal_verge": "imaging", "mrf_status": "imaging", "emvi": "imaging",
                "haemoglobin": "labs", "wbc": "labs", "platelets": "labs", "creatinine": "labs", "bilirubin": "labs", "hiv_status": "labs", "cea": "labs",
                "treatment_received": "prior_treatment", "treatment_completion_date": "prior_treatment"}
# The doctor may also type the patient's wishes, the comorbidities and whether the patient knows the diagnosis (owner, 21 Oct 2026, B3):
# facts reports rarely carry; shown "entered by Dr X, no report", never as a verified value.
DOCTOR_FACTS = {"patient_preference", "comorbidities", "patient_awareness"}
TYPABLE = {"ecog", "menopausal_status", "weight", "height", "clinical_question"} | DOCTOR_FACTS  # plus any protocol fact flagged "typable": true
DOCTOR_FIRST = {"clinical_question"} | DOCTOR_FACTS  # a typed value stands before a value read from a report: the question for the board is the treating doctor's own
EXTRA_FACTS = {"weight": "Weight", "height": "Height", "patient_preference": "Patient's wishes", "comorbidities": "Comorbidities",
               "patient_awareness": "Patient knows the diagnosis"}  # typed lines every Case File has (a protocol fact of the same id keeps its own line)
AWARENESS = {"yes": "Yes", "no": "No", "partly": "Partly"}
OPEN = ("not_found", "waiting", "needs_confirmation")  # a required line in one of these states is "left before the board"
MENOPAUSE = {"pre": "premenopausal", "peri": "perimenopausal", "post": "postmenopausal"}
ENTERED_LABEL = "entered by {who}, no report"
MAX_NOTE, MAX_REASON, MAX_TEXT = 500, 500, 1000


class SlotError(Exception):
    """A plain message for the user; `status` is the HTTP status the route answers."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- names and helpers -------------------------------------------------------------------------------------------------------------

def display_name(user) -> str:
    """How a person is named on a line: the display name of org.json (or profiles.json of the new interface), else the login."""
    user = str(user or "")
    if not user:
        return ""
    try:
        u = (org.load().get("users") or {}).get(user) or {}
        if u.get("display_name"):
            return str(u["display_name"])
    except Exception:
        pass
    try:
        from . import config
        p = store._read_json(config.DATA_ROOT / "profiles.json", {}) or {}
        dn = ((p.get(user) or {}) if isinstance(p, dict) else {}).get("display_name")
        if dn:
            return str(dn)
    except Exception:
        pass
    return user


def _dmy(s) -> str:
    s = str(s or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else s


def typable_facts(prot) -> set:
    """The facts a doctor may type: the fixed list plus every protocol record fact flagged "typable": true (unknown record keys stay opaque)."""
    out = set(TYPABLE)
    for r in protocol.records(prot) if prot else []:
        if r.get("typable") is True:
            out |= set(r.get("required_facts") or [])
        for f in (r.get("typable_facts") or []) if isinstance(r.get("typable_facts"), list) else []:
            out.add(str(f))
    return out


def section_for_record(rec) -> str:
    for t in rec.get("doc_types") or rec.get("fact_doc_types") or []:
        if t in DOC_SECTION:
            return DOC_SECTION[t]
    for f in rec.get("required_facts") or []:
        if f in FACT_SECTION:
            return FACT_SECTION[f]
    return "other"


def parse_slot(slot_id, prot):
    """("record", id) or ("fact", id) for a slot id ("record:histopathology", "fact:ecog", or a bare id: a record first, then a fact)."""
    s = str(slot_id or "").strip()
    kind, _, ident = s.partition(":")
    if _ and kind in ("record", "fact") and ident:
        return kind, ident
    ids = {r["id"] for r in protocol.records(prot)} if prot else set()
    if s in ids:
        return "record", s
    return "fact", s


def validate_value(fid, value):
    """The typed value, cleaned and checked for its field; ValueError with a plain message."""
    v = " ".join(str(value if value is not None else "").split())
    if not v:
        raise ValueError("Type a value")
    if fid == "ecog":
        m = re.fullmatch(r"(?:ecog|ps|performance status)?\s*[:=]?\s*([0-4])", v, re.I)
        if not m:
            raise ValueError("ECOG performance status is a whole number from 0 to 4")
        return m.group(1)
    if fid == "menopausal_status":
        m = re.fullmatch(r"(pre|peri|post)\s*-?\s*menopaus\w*|(pre|peri|post)", v, re.I)
        if not m:
            raise ValueError("Menopausal status is premenopausal, perimenopausal or postmenopausal")
        return MENOPAUSE[(m.group(1) or m.group(2)).lower()]
    if fid == "weight":
        m = re.fullmatch(r"(\d{1,3}(?:\.\d{1,2})?)\s*(?:kg|kgs|kilograms?)?", v, re.I)
        if not m or not 2 <= float(m.group(1)) <= 400:
            raise ValueError("Weight is a number of kilograms (2 to 400)")
        return f"{m.group(1)} kg"
    if fid == "height":
        m = re.fullmatch(r"(\d{1,3}(?:\.\d{1,2})?)\s*(cm|cms|centimetres?|centimeters?|m|metres?|meters?)?", v, re.I)
        if not m:
            raise ValueError("Height is a number of centimetres (50 to 250)")
        n, unit = float(m.group(1)), (m.group(2) or "cm").lower()
        if unit.startswith("m") and not unit.startswith("mm"):
            n = n * 100 if n < 3 else n
        if not 50 <= n <= 250:
            raise ValueError("Height is a number of centimetres (50 to 250)")
        return f"{n:g} cm"
    if fid == "patient_awareness":
        if v.lower() not in AWARENESS:
            raise ValueError("Whether the patient knows the diagnosis is Yes, No or Partly")
        return AWARENESS[v.lower()]
    if fid in ("patient_preference", "comorbidities"):
        if len(v) < 2:
            raise ValueError("Type a few words")
        return v[:MAX_TEXT]
    if fid == "clinical_question":
        if len(v) < 5:
            raise ValueError("The question for the Tumour Board needs a few words")
        return v[:MAX_TEXT]
    if len(v) > MAX_TEXT:
        raise ValueError(f"At most {MAX_TEXT} characters")
    return v


# ---- typed values, not needed, ask the department ----------------------------------------------------------------------------------

def _case_and_protocol(case_id):
    case = store.get_case(case_id)
    if not case:
        raise SlotError("Case File not found.", 404)
    prot = protocol.get(case["protocol"]) if case.get("protocol") and protocol.exists(case["protocol"]) else None
    return case, prot


def _recheck(case_id, user):
    from . import service
    try:
        service.recheck(case_id, user)
    except Exception as e:  # the value is saved and audited; the gate catches up on the next re-check
        store.audit(case_id, {"kind": "error", "where": "slots_recheck", "error": f"{e.__class__.__name__}: {str(e)[:200]}", "by": user})


def set_value(case_id, slot_id, value, note, user) -> dict:
    """Store a typed value for a typable fact (validated), audited "typed_value"; the gate is re-checked so the value settles its gap."""
    case, prot = _case_and_protocol(case_id)
    kind, fid = parse_slot(slot_id, prot)
    if kind != "fact":
        raise SlotError("A value is typed on a field line, not on a record.", 409)
    cat = protocol.facts()
    if fid not in typable_facts(prot) and not (fid in EXTRA_FACTS):
        label = cat.get(fid, {}).get("label") or fid
        raise SlotError(f"{label} is not typed by hand: it comes from a signed report (ask the department, or mark it not needed).", 409)
    if fid not in cat and fid not in EXTRA_FACTS:
        raise SlotError(f"Unknown field: {fid}", 404)
    try:
        clean = validate_value(fid, value)
    except ValueError as e:
        raise SlotError(str(e), 400)
    note = " ".join(str(note or "").split())[:MAX_NOTE]
    rec = {"value": clean, "by": user, "at": store.now_iso(), "note": note}
    before = (case.get("typed_values") or {}).get(fid)
    case.setdefault("typed_values", {})[fid] = rec
    store.save_case(case)
    store.audit(case_id, {"kind": "typed_value", "fact": fid, "value": clean, "note": note, "by": user, "before": before})
    _recheck(case_id, user)
    return rec


def clear_value(case_id, slot_id, user) -> dict | None:
    case, prot = _case_and_protocol(case_id)
    kind, fid = parse_slot(slot_id, prot)
    typed = case.get("typed_values") or {}
    if kind != "fact" or fid not in typed:
        raise SlotError("No typed value on this line.", 404)
    before = typed.pop(fid)
    case["typed_values"] = typed
    store.save_case(case)
    store.audit(case_id, {"kind": "typed_value_removed", "fact": fid, "before": before, "by": user})
    _recheck(case_id, user)
    return before


def _gate(case_id, case, prot, st):
    g = st.get("gate")
    if isinstance(g, dict) and g.get("protocol") == (prot or {}).get("id") and g.get("requirements") is not None:
        return g
    return rules.evaluate(case_id) if prot else None


def not_needed(case_id, slot_id, reason, user, roles) -> dict:
    """Mark a record (or the one open value of a record) not needed: a waive confirmation with a reason, then a re-check."""
    case, prot = _case_and_protocol(case_id)
    if not prot:
        raise SlotError("The Case File is not listed yet: no protocol record to waive.", 409)
    reason = " ".join(str(reason or "").split())[:MAX_REASON]
    if not reason:
        raise SlotError("Say why this is not needed for this Case File.", 400)
    kind, ident = parse_slot(slot_id, prot)
    recs = {r["id"]: r for r in protocol.records(prot)}
    st = store.get_state(case_id)
    gate = _gate(case_id, case, prot, st) or {}
    rows = {r["id"]: r for r in (gate.get("requirements") or []) + (gate.get("shown") or [])}
    cat = protocol.facts()
    if kind == "record":
        rec = recs.get(ident)
        if not rec:
            raise SlotError(f"No record {ident} in the {prot.get('label') or prot['id']} protocol.", 404)
    else:
        needing = [r for r in recs.values() if ident in (r.get("required_facts") or [])]
        label = cat.get(ident, {}).get("label") or EXTRA_FACTS.get(ident) or ident
        if not needing:
            raise SlotError(f"{label} is not a requirement of this protocol; there is nothing to waive.", 409)
        live = [r for r in needing if (rows.get(r["id"]) or {}).get("status") not in ("waived", "not_applicable")]
        if not live:
            raise SlotError(f"{label} is already not needed (its record is waived or not applicable).", 409)
        if len(live) > 1:
            raise SlotError(f"{label} is required by several records ({', '.join(r['label'] for r in live)}): mark each record not needed from its own row.", 409)
        rec = live[0]
        view = build(case_id, roles)
        others = [s for s in _all_slots(view) if s.get("kind") == "fact" and rec["id"] in (s.get("records") or []) and s.get("fact_id") != ident
                  and s.get("status") in OPEN]
        if others:
            raise SlotError(f"{label} belongs to the record {rec['label']}, whose other values are still open ({', '.join(s['label'] for s in others)}): "
                            "mark the record not needed from its own row, or settle them first.", 409)
        reason = f"{label}: {reason}"
    try:
        access.require(roles, "waive", case, rec.get("department") or None)
    except PermissionError as e:
        raise SlotError(str(e), 403)
    try:
        conf = confirm.record(case_id, "waive", rec["id"], {}, reason, user)
    except ValueError as e:
        raise SlotError(str(e), 400)
    _recheck(case_id, user)
    return {"confirmation": conf, "record": rec["id"]}


def _open_action(st, record_id):
    return next((a for a in st.get("actions") or [] if isinstance(a, dict) and a.get("source") == "pre_authorization" and a.get("requirement") == record_id
                 and a.get("status") != "completed"), None)


def ask_department(case_id, slot_id, user, roles, message="", due="") -> dict:
    """Send the request the gate suggested for the slot's record (dept_requests.draft text unless the doctor edited it). Returns the
    action as sent."""
    case, prot = _case_and_protocol(case_id)
    if not prot:
        raise SlotError("The Case File is not listed yet: list it before asking a department.", 409)
    kind, ident = parse_slot(slot_id, prot)
    recs = {r["id"]: r for r in protocol.records(prot)}
    if kind == "record":
        rec = recs.get(ident)
        if not rec:
            raise SlotError(f"No record {ident} in this protocol.", 404)
        candidates = [rec]
    else:
        candidates = [r for r in recs.values() if ident in (r.get("required_facts") or [])]
        if not candidates:
            raise SlotError("This value is not a protocol requirement: write a free request to the department instead.", 409)
    try:
        access.require(roles, "send_request", case)
    except PermissionError as e:
        raise SlotError(str(e), 403)
    st = store.get_state(case_id)
    a = next((x for r in candidates if (x := _open_action(st, r["id"]))), None)
    if a is None:
        _recheck(case_id, user)  # the gate suggests the request for every open gap; a met record has none
        st = store.get_state(case_id)
        a = next((x for r in candidates if (x := _open_action(st, r["id"]))), None)
    if a is None:
        raise SlotError("Nothing to ask: the record is met, waived or not applicable for this Case File.", 409)
    try:
        return dept_requests.send(case_id, a["id"], user, roles, message=message, due=due)
    except dept_requests.RequestError as e:
        raise SlotError(str(e), e.status)


# ---- the view ----------------------------------------------------------------------------------------------------------------------

def _quote(h, fid=None) -> dict:
    loc = h.get("location") or {}
    out = {"text": h.get("quote") or "", "doc_id": h.get("doc_id") or "", "doc_title": h.get("doc_title") or "", "page": loc.get("page") if isinstance(loc, dict) else None,
           "fact_id": fid, "date": h.get("date"), "status": h.get("doc_status")}
    if h.get("source_method"):
        out["source_method"] = h["source_method"]
        out["scan"] = h["source_method"] == scanned.SCAN_METHOD
    if h.get("confirmed_by"):
        out["confirmed_by"] = h["confirmed_by"]
    return out


def _doc_quote(d, text="") -> dict:
    c = (d or {}).get("classification") or {}
    from . import dates
    return {"text": text or c.get("status_quote") or c.get("signature_quote") or "", "doc_id": d.get("doc_id"), "doc_title": c.get("title") or d.get("filename"),
            "page": 0 if d.get("pages") else None, "fact_id": None, "date": dates.doc_dates(d)["event"] or None, "status": c.get("status")}


def _request(a) -> dict:
    sent = a.get("sent") or {}
    return {"action_id": a["id"], "department": a.get("department") or "", "department_id": a.get("department_id"), "department_label": a.get("department") or "",
            "sent_at": sent.get("at"), "sent_by": sent.get("by"), "due": a.get("due"), "due_label": _dmy(a.get("due")), "status": a.get("status"),
            "acknowledged": a.get("acknowledged"), "done": a.get("done"), "reminders": len(a.get("reminders") or []), "what": a.get("what") or "",
            "level": a.get("level"), "accession": a.get("accession")}


def _dept(r):
    name = (r or {}).get("department") or ""
    return name, rules._dept_id(name)


def _actions_for(s, row, action):
    """The in-place actions of a line for its status (the route still checks every permission)."""
    acts = []
    name, did = _dept(row)
    aid = action["id"] if action else None
    st = s["status"]
    if st == "found":
        if s.get("quote") and s["quote"].get("doc_id"):
            acts.append({"kind": "open_source", "label": "Open the source page", "doc_id": s["quote"]["doc_id"], "page": s["quote"].get("page")})
        if s.get("fact_id") in DOCTOR_FIRST and s.get("typable"):  # the treating doctor states the board question, even when a note carries one
            acts.append({"kind": "enter_value", "label": "Type the question", "fact_id": s.get("fact_id")})
    elif st == "entered":
        acts.append({"kind": "enter_value", "label": "Change the value", "fact_id": s.get("fact_id")})
    elif st == "not_found":
        if row is not None and name:
            acts.append({"kind": "ask_department", "label": f"Ask {name}", "department": name, "department_id": did, "action_id": aid})
        if row is not None:
            acts.append({"kind": "not_needed", "label": "Not needed", "reason_required": True})
        if s.get("typable"):
            acts.append({"kind": "enter_value", "label": "Enter a value", "fact_id": s.get("fact_id")})
    elif st == "waiting":
        if aid:
            acts.append({"kind": "remind", "label": "Remind", "action_id": aid, "department": name, "department_id": did})
        acts.append({"kind": "not_needed", "label": "Not needed", "reason_required": True})
        if s.get("typable"):
            acts.append({"kind": "enter_value", "label": "Enter a value", "fact_id": s.get("fact_id")})
    elif st == "needs_confirmation":
        acts.append({"kind": "review", "label": "Review", "confirmation": s.get("confirmation")})
        if s.get("quote") and s["quote"].get("doc_id"):
            acts.append({"kind": "open_source", "label": "Open the source page", "doc_id": s["quote"]["doc_id"], "page": s["quote"].get("page")})
    return acts


def _same_label(a, b) -> bool:
    """Two labels that say the same thing once case, brackets and punctuation are set aside ("Ki-67" and "Ki-67")."""
    import re as _re
    norm = lambda s: _re.sub(r"[^a-z0-9]+", "", _re.sub(r"\(.*?\)", "", str(s or "").lower()))
    return bool(norm(a)) and norm(a) == norm(b)


def _record_slot(rec, r, action, by_doc, required, cat):
    name, did = _dept(r)
    l1 = r.get("level1") or {}
    s = {"id": f"record:{rec['id']}", "kind": "record", "record_id": rec["id"], "label": rec["label"], "section": section_for_record(rec),
         "required": required and r["status"] not in ("waived", "not_applicable"), "department": name, "department_id": did,
         "tier": r.get("tier"), "tier_label": r.get("tier_label"), "tier_note": r.get("tier_note") or "", "facts": [f"fact:{f}" for f in rec.get("required_facts") or []],
         "gate_status": r["status"], "level": r.get("level"), "problems": list(r.get("problems") or []), "notes": list(r.get("notes") or []),
         "status": "not_found", "value": "", "as_of": None, "quote": None, "request": None, "confirmation": None, "actions": [], "note": ""}
    if r.get("pending_order"):
        s["pending_order"] = r["pending_order"]
    ev_doc = next((by_doc[e["doc_id"]] for e in r.get("evidence") or [] if e.get("doc_id") in by_doc), None)
    src = by_doc.get(r.get("source_doc_id")) or ev_doc
    if r["status"] == "waived":
        w = r.get("waiver") or {}
        s["status"] = "not_needed"; s["waiver"] = {"by": w.get("by"), "by_name": display_name(w.get("by")), "at": w.get("at"), "reason": w.get("reason"), "confirmation": w.get("confirmation")}
        s["note"] = f"Not needed: {w.get('reason') or 'no reason given'} ({display_name(w.get('by')) or 'clinician'})"
    elif r["status"] == "not_applicable":
        s["status"] = "not_needed"; s["note"] = r.get("tier_note") or "Not applicable in this NCG setting"
    else:
        l1s = l1.get("status") or "satisfied"
        # a record of values only (no document type of its own: receptor status, grade, Ki-67) is as complete as its values; the gate's
        # source document may be a report that only says the values are pending (18 Oct, e2e: the line said "found" from the HPE report
        # "IHC to follow" while ER, PR and HER2 were not in the file). Its value lines are counted "left before the board", not this line too.
        facts_only = l1s == "satisfied" and not (rec.get("doc_types") or [])
        if facts_only:
            s["facts_only"] = True
        if facts_only and r["status"] in ("needs_confirmation", "needs_review"):
            s["status"] = "needs_confirmation"; s["note"] = "; ".join(r.get("problems") or [])
        elif facts_only and r["status"] != "satisfied":
            s["status"] = "waiting" if action and dept_requests.is_sent(action) else "not_found"
            s["note"] = "; ".join(r.get("problems") or []) or "Not found in the file"
            if r.get("pending_order"):
                s["value"] = ""
        elif l1s == "satisfied" and src:
            c = src.get("classification") or {}
            s["status"] = "found"
            s["value"] = ", ".join(x for x in [c.get("title") or src.get("filename"), _dmy((_doc_quote(src).get("date") or "")), (c.get("status") or "").lower() or ""] if x)
            s["quote"] = _doc_quote(src, next((e.get("quote") for e in r.get("evidence") or [] if e.get("doc_id") == src["doc_id"] and e.get("quote")), ""))
            s["as_of"] = s["quote"].get("date")
            if r.get("notes"):
                s["note"] = "; ".join(r["notes"])
        elif l1s == "satisfied":  # a record whose carriers hold the values (no single source document)
            s["status"] = "found"; s["value"] = "see the values below"
        elif l1s in ("needs_confirmation", "needs_review"):
            need = next((n for n in l1.get("needs") or []), None) or ({"type": "confirm_match", "doc_id": src["doc_id"]} if src else None)
            s["status"] = "needs_confirmation"
            if need:
                d = by_doc.get(need.get("doc_id")) or src or {}
                s["confirmation"] = {"type": need.get("type"), "key": need.get("doc_id"), "doc_id": need.get("doc_id"), "doc_title": ((d.get("classification") or {}).get("title") or d.get("filename") or ""),
                                     "why": next(iter(l1.get("problems") or r.get("problems") or []), "")}
            if src:
                s["quote"] = _doc_quote(src); s["value"] = (src.get("classification") or {}).get("title") or src.get("filename") or ""
            s["note"] = "; ".join(l1.get("problems") or r.get("problems") or [])
        else:  # missing_record, not_final
            s["status"] = "waiting" if action and dept_requests.is_sent(action) else "not_found"
            s["note"] = "; ".join(l1.get("problems") or r.get("problems") or []) or "Not found in the file"
            if l1s == "not_final" and src:
                c = src.get("classification") or {}
                s["draft"] = {"doc_id": src["doc_id"], "doc_title": c.get("title") or src.get("filename"), "status": c.get("status"), "signed": c.get("signed")}
                s["value"] = ""
    if action and dept_requests.is_sent(action) and s["status"] in ("waiting", "not_found", "needs_confirmation"):
        s["request"] = _request(action)
    s["actions"] = _actions_for(s, r, action)
    return s


def _fact_slot(fid, recs, rows, facts, typed, needs, disc, typable, required_ids, actions, cat):
    label = cat.get(fid, {}).get("label") or EXTRA_FACTS.get(fid) or fid
    rec_rows = [rows[r["id"]] for r in recs if r["id"] in rows]
    live = [r for r in rec_rows if r["status"] not in ("waived", "not_applicable")]
    primary = next((r for r in live if r["id"] in required_ids), live[0] if live else (rec_rows[0] if rec_rows else None))
    s = {"id": f"fact:{fid}", "kind": "fact", "fact_id": fid, "label": label, "section": FACT_SECTION.get(fid) or (section_for_record(recs[0]) if recs else "other"),
         "records": [r["id"] for r in recs], "required": any(r["id"] in required_ids for r in live), "typable": fid in typable or fid in EXTRA_FACTS,
         "status": "not_found", "value": "", "unit": "", "as_of": None, "quote": None, "request": None, "confirmation": None, "actions": [], "note": ""}
    f = facts.get(fid) or {}
    hist = [h for h in f.get("history") or [] if not h.get("superseded")]
    good = [h for h in hist if h.get("verification") in rules.VERIFIED and h.get("doc_final") and h.get("state") == "present"]
    prec = next((r for r in recs if primary and r["id"] == primary["id"]), None)  # the value the gate rests on: from the record's own document types
    allowed = set((prec or {}).get("fact_doc_types") or (prec or {}).get("doc_types") or [])
    if allowed:
        good = [h for h in good if set(h.get("doc_types") or []) & allowed] or good
    t = typed.get(fid) if isinstance(typed.get(fid), dict) and str(typed.get(fid, {}).get("value") or "").strip() else None
    if t:
        s["typed"] = {"value": t.get("value"), "by": t.get("by"), "by_name": display_name(t.get("by")), "at": t.get("at"), "note": t.get("note") or ""}
    if good and t and fid in DOCTOR_FIRST:  # the doctor typed the question for the board: it stands; the note's line is kept beside it
        g = sorted(good, key=lambda h: ((h.get("date") or ""), (h.get("report_date") or "")))[-1]
        s["status"] = "entered"; s["value"] = t.get("value") or ""; s["typed_by"] = t.get("by"); s["typed_by_name"] = display_name(t.get("by")); s["typed_at"] = t.get("at")
        s["note"] = ENTERED_LABEL.format(who=display_name(t.get("by")) or "the treating doctor") + (f"; {t['note']}" if t.get("note") else "")
        s["report_value"] = {"value": g.get("value") or "", "quote": _quote(g, fid), "as_of": g.get("date")}
    elif good:
        g = sorted(good, key=lambda h: ((h.get("date") or ""), (h.get("report_date") or "")))[-1]
        pk = (f.get("current") or {}).get("picked")  # the value a doctor picked for the board when two reports differ (night-v3 item 1.7)
        if pk:
            g = next((h for h in hist if h.get("doc_id") == pk.get("doc_id") and h.get("value") == pk.get("value")), g)
        s["status"] = "found"; s["value"] = g.get("value") or ""; s["as_of"] = g.get("date"); s["quote"] = _quote(g, fid)
        if g.get("confirmed_by"):
            s["confirmed_by"] = g["confirmed_by"]; s["note"] = f"confirmed by {display_name(g['confirmed_by'])} against the source, no quote"
        need = needs.get(fid)
        item = disc.get(fid)
        if need:
            s["status"] = "needs_confirmation"
            s["confirmation"] = {"type": need.get("type"), "key": f"{need.get('doc_id')}:{fid}", "doc_id": need.get("doc_id"), "fact_id": fid, "value": need.get("value"),
                                 "page": need.get("page"), "start": need.get("start"), "end": need.get("end"), "boxes": need.get("boxes") or [], "why": need.get("why") or ""}
        elif item:
            s["status"] = "found" if item.get("picked") else "needs_confirmation"  # a picked value settles it; the difference stays shown
            s["confirmation"] = {"type": "note_discordance", "key": item["key"], "fact_id": fid, "kind": item.get("kind"), "kind_label": item.get("kind_label"),
                                 "why": item.get("text") or "", "citations": item.get("citations") or []}
            if item.get("picked"):
                s["picked"] = s["confirmation"]["picked"] = item["picked"]
    elif rec_rows and not live:
        s["status"] = "not_needed"
        w = (rec_rows[0].get("waiver") or {}) if rec_rows[0]["status"] == "waived" else {}
        s["note"] = (f"Not needed: {w.get('reason') or 'no reason given'} ({display_name(w.get('by')) or 'clinician'})" if w
                     else (rec_rows[0].get("tier_note") or "Not applicable in this NCG setting"))
        if t:
            s["status"] = "entered"; s["value"] = t.get("value") or ""; s["typed_by"] = t.get("by"); s["typed_by_name"] = display_name(t.get("by")); s["typed_at"] = t.get("at")
            s["note"] = ENTERED_LABEL.format(who=display_name(t.get("by")) or "the treating doctor")
    elif t:
        s["status"] = "entered"; s["value"] = t.get("value") or ""; s["typed_by"] = t.get("by"); s["typed_by_name"] = display_name(t.get("by")); s["typed_at"] = t.get("at")
        s["note"] = ENTERED_LABEL.format(who=display_name(t.get("by")) or "the treating doctor") + (f"; {t['note']}" if t.get("note") else "")
    elif any(h.get("state") == "pending" for h in hist):
        h = [h for h in hist if h.get("state") == "pending"][-1]
        s["status"] = "not_found"; s["pending"] = True; s["value"] = ""; s["quote"] = _quote(h, fid) if h.get("quote") else None
        s["note"] = f"Pending: \"{h.get('value')}\" in {h.get('doc_title')}"
    elif any(h.get("verification") == "needs_review" for h in hist):
        h = [h for h in hist if h.get("verification") == "needs_review"][-1]
        s["status"] = "needs_confirmation"; s["quote"] = _quote(h, fid)
        s["confirmation"] = {"type": "confirm_value", "key": f"{h.get('doc_id')}:{fid}", "doc_id": h.get("doc_id"), "fact_id": fid, "value": h.get("value"),
                             "why": f"\"{h.get('value')}\" matched its source only approximately in {h.get('doc_title')}: read the value in the source and confirm it"}
        s["note"] = s["confirmation"]["why"]
    elif hist and not any(h.get("doc_final") for h in hist):
        h = hist[-1]
        s["status"] = "not_found"; s["note"] = f"Only in a non-final document ({h.get('doc_title')}): a final, signed report is required"
        s["draft"] = {"doc_id": h.get("doc_id"), "doc_title": h.get("doc_title"), "status": h.get("doc_status"), "value": h.get("value")}
    else:
        s["status"] = "not_found"; s["note"] = "Not found in the file"
    action = next((actions.get(r["id"]) for r in live if actions.get(r["id"])), None)
    if s["status"] == "not_found" and action and dept_requests.is_sent(action):
        s["status"] = "waiting"
    if action and dept_requests.is_sent(action) and s["status"] in ("waiting", "not_found"):
        s["request"] = _request(action)
    s["actions"] = _actions_for(s, primary, action)
    return s


def _needs_by_fact(gate) -> dict:
    """Level 2 confirmations the gate asks for, by fact: a critical value read from a scan (confirm_value), with its place on the image."""
    out = {}
    for r in (gate.get("requirements") or []) + (gate.get("shown") or []):
        for n in r.get("needs") or []:
            if n.get("type") == "confirm_value" and n.get("fact") and n["fact"] not in out:
                why = next((p for p in r.get("problems") or [] if p.startswith("Confirm")), "")
                out[n["fact"]] = {**n, "why": why}
    return out


def _prose(case, st, sig, preparing=False) -> dict:
    summ = (st.get("artefacts") or {}).get("summary")
    marked = bool((case.get("board_ready") or {}).get("at"))
    if isinstance(summ, dict) and isinstance(summ.get("sections"), list):
        why = rules.stale_reason(summ.get("signature"), sig) if summ.get("signature") else "Compiled before the Case File signature was kept, so changes since then cannot be checked"
        reviewed = (summ.get("review") or {}).get("status") == "reviewed"
        return {"status": "stale" if why else "ready", "paragraphs": [{"id": x.get("id"), "title": x.get("title"), "sentences": x.get("sentences") or []} for x in summ["sections"]],
                "points_for_review": summ.get("points_for_review") or [], "reviewed": reviewed, "reviewed_by": (summ.get("review") or {}).get("by") if reviewed else None,
                "label": "Reviewed" if reviewed else "AI draft, not reviewed", "generated": summ.get("generated"), "model": summ.get("model") or "",
                "stale_reason": why, "stage_as_recorded": summ.get("stage_as_recorded"), "summary_status": summ.get("status"), "preparing": bool(preparing)}
    if marked or preparing:
        return {"status": "pending", "paragraphs": [], "points_for_review": [], "reviewed": False, "label": "AI draft being prepared", "generated": None, "model": "",
                "stale_reason": "", "preparing": bool(preparing)}
    return {"status": "none", "paragraphs": [], "points_for_review": [], "reviewed": False, "label": "Written at the ready mark", "generated": None, "model": "",
            "stale_reason": "", "preparing": False}


def _all_slots(view):
    return [s for sec in view.get("sections") or [] for s in sec.get("slots") or []]


def _permissions(roles, case) -> dict:
    if not isinstance(roles, dict):
        return {k: False for k in ("enter_value", "not_needed", "ask_department", "remind", "review", "mark_ready")}
    return {"enter_value": access.may(roles, "confirm", case), "not_needed": access.may(roles, "waive", case), "ask_department": access.may(roles, "send_request", case),
            "remind": access.may_remind(roles, case), "review": access.may(roles, "confirm", case), "mark_ready": access.may(roles, "mark_ready", case)}


def build(case_id, roles=None) -> dict:
    """The fill-in summary of a Case File: sections of slots, the count left before the board, the blockers, whether the ready mark is
    allowed for this user, and the AI prose block (none / pending / ready / stale)."""
    case = store.get_case(case_id)
    if not case:
        raise SlotError("Case File not found.", 404)
    st = store.get_state(case_id)
    sig = rules.case_signature(case_id, st)
    prot = protocol.get(case["protocol"]) if case.get("protocol") and protocol.exists(case["protocol"]) else None
    try:
        from . import ready_hook
        preparing = ready_hook.running(case_id)
    except Exception:
        preparing = False
    prose = _prose(case, st, sig, preparing)
    base = {"case_id": case_id, "protocol": case.get("protocol") or "", "protocol_label": (prot or {}).get("label") or "", "setting": case.get("setting") or "",
            "board_ready": case.get("board_ready") or None, "signature": sig.get("hash"), "permissions": _permissions(roles, case), "prose": prose}
    if not prot:
        return {**base, "listed": False, "sections": [], "left_before_board": 0, "blockers": [{"slot_id": "", "why": "The Case File is not listed yet: choose the cancer protocol first"}],
                "ready_allowed": False, "gate": None, "message": "This Case File is not listed yet (no cancer protocol): nothing is checked until it is."}
    gate = _gate(case_id, case, prot, st) or {}
    rows = {r["id"]: r for r in (gate.get("requirements") or []) + (gate.get("shown") or [])}
    required_ids = {r["id"] for r in gate.get("requirements") or []}
    docs = rules.case_docs(case_id, st)
    by_doc = {d["doc_id"]: d for d in docs}
    facts = rules.resolve_facts(docs, st.get("overrides"))
    cat = protocol.facts()
    typed = case.get("typed_values") if isinstance(case.get("typed_values"), dict) else {}
    actions = {}
    for a in st.get("actions") or []:
        if isinstance(a, dict) and a.get("source") == "pre_authorization" and a.get("requirement") and a.get("status") != "completed":
            actions.setdefault(a["requirement"], a)
    try:
        disc = {}
        for it in discord.items(case_id, st):
            if it.get("severity") == "review" and (not it.get("noted") or it.get("picked")) and it.get("field") and it["field"] not in disc:
                disc[it["field"]] = it
    except Exception:
        disc = {}
    needs = _needs_by_fact(gate)
    typable = typable_facts(prot)
    sections = {sid: [] for sid, _ in SECTIONS}
    fact_recs = {}
    for rec in protocol.records(prot):
        for fid in rec.get("required_facts") or []:
            fact_recs.setdefault(fid, []).append(rec)
    made = set()
    if prose["status"] in ("none", "pending"):
        sections["presenting"].append({"id": "prose:history", "kind": "prose", "label": "History narrative (AI draft)", "section": "presenting", "required": False,
                                       "status": "pending_ready", "value": "", "quote": None, "request": None, "confirmation": None, "actions": [],
                                       "note": "Written at the ready mark from the verified records; labelled AI draft until reviewed" if prose["status"] == "none"
                                               else "Being prepared from the verified records; labelled AI draft until reviewed"})
    for rec in protocol.records(prot):
        r = rows.get(rec["id"])
        if r is None:
            continue
        rs = _record_slot(rec, r, actions.get(rec["id"]), by_doc, rec["id"] in required_ids, cat)
        only = rec.get("required_facts") or []
        merge = len(only) == 1 and only[0] not in made and _same_label(rec["label"], (cat.get(only[0]) or {}).get("label") or only[0])
        if not merge:
            sections[rs["section"]].append(rs)
        for fid in rec.get("required_facts") or []:
            if fid in made:
                continue
            made.add(fid)
            fs = _fact_slot(fid, fact_recs.get(fid) or [rec], rows, facts, typed, needs, disc, typable, required_ids, actions, cat)
            if merge:  # "Ki-67" the record and "Ki-67" the value: one line, the value's, carrying the record's request (18 Oct)
                fs["record_id"], fs["required"] = rec["id"], bool(fs.get("required") or rs.get("required"))
                fs["note"] = fs.get("note") or rs.get("note") or ""
                fs["request"] = fs.get("request") or rs.get("request")
                kinds = {a.get("kind") for a in fs.get("actions") or []}
                fs["actions"] = list(fs.get("actions") or []) + [a for a in rs.get("actions") or [] if a.get("kind") not in kinds]
            sections[fs["section"]].append(fs)
    extra = list(dict.fromkeys(list(prot.get("extract_facts") or []) + [f for c in prot.get("core_data") or [] for f in c.get("facts") or []]))
    for fid in extra:
        if fid in made or fid not in cat:
            continue
        f = facts.get(fid) or {}
        good = [h for h in f.get("history") or [] if h.get("verification") in rules.VERIFIED and h.get("doc_final") and h.get("state") == "present" and not h.get("superseded")]
        if not good and not (isinstance(typed.get(fid), dict) and fid in typable):
            continue
        made.add(fid)
        fs = _fact_slot(fid, [], rows, facts, typed, needs, disc, typable, required_ids, actions, cat)
        fs["extra"] = True
        sections[fs["section"]].append(fs)
    for fid, label in EXTRA_FACTS.items():
        if fid in made:
            continue
        made.add(fid)
        fs = _fact_slot(fid, [], rows, facts, typed, needs, disc, typable, required_ids, actions, cat)
        fs["label"], fs["extra"], fs["required"] = label, True, False
        if fs["status"] == "not_found":
            fs["note"] = "Not recorded; type it if the board needs it"
            fs["actions"] = [{"kind": "enter_value", "label": "Enter a value", "fact_id": fid}]
        sections[fs["section"]].append(fs)
    out_sections = [{"id": sid, "label": label, "slots": sections[sid]} for sid, label in SECTIONS if sections[sid] or sid != "other"]
    slots = [s for sec in out_sections for s in sec["slots"]]
    left = sum(1 for s in slots if s.get("required") and s.get("status") in OPEN and not s.get("facts_only"))
    blockers = []
    for b in gate.get("blockers") or []:
        blockers.append({"slot_id": f"document:{b.get('doc_id')}", "why": f"{b.get('filename') or b.get('doc_id')} could not be read ({b.get('error') or 'error'}): re-process or dismiss it", "doc_id": b.get("doc_id")})
    if (gate.get("documents") or {}).get("processing"):
        blockers.append({"slot_id": "", "why": f"{gate['documents']['processing']} document(s) still being read: wait for them"})
    q = next((s for s in slots if s.get("id") == "fact:clinical_question"), None)
    if q is None or q.get("status") != "entered":  # the treating doctor's own words; a question copied from a note does not count (owner, 21 Oct, B3)
        blockers.append({"slot_id": "fact:clinical_question", "why": "The question for the Tumour Board is not written yet: the treating doctor writes it in the Question step"})
    ready_allowed = bool(isinstance(roles, dict) and access.may(roles, "mark_ready", case) and not blockers)
    return {**base, "listed": True, "sections": out_sections, "left_before_board": left, "blockers": blockers, "ready_allowed": ready_allowed,
            "gate": {k: gate.get(k) for k in ("passed", "readiness", "satisfied", "total", "evaluated")}, "typed_values": typed}


def one(case_id, slot_id, roles=None) -> dict:
    view = build(case_id, roles)
    prot = protocol.get(view["protocol"]) if view.get("protocol") and protocol.exists(view["protocol"]) else None
    s = next((x for x in _all_slots(view) if x.get("id") == str(slot_id or "")), None)  # a full id first (also prose:history)
    if s is None:
        kind, ident = parse_slot(slot_id, prot)
        sid = f"{kind}:{ident}"
        s = next((x for x in _all_slots(view) if x.get("id") == sid), None)
    if s is None:
        raise SlotError(f"No line {slot_id} in this Case File's summary.", 404)
    return {**s, "left_before_board": view["left_before_board"], "blockers": view["blockers"], "ready_allowed": view["ready_allowed"]}
