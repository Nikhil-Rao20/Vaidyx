"""Pre-Authorization gate: deterministic evaluation of the case protocol over the processed documents.

No model is involved here. For every mandatory record it decides: satisfied / missing record / not final-signed /
missing or pending field / needs expert review, names the Responsible Department, and keeps the action list in sync
(new gaps open actions, resolved gaps close them with the evidence document)."""
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta

from . import confirm, dates, doctype, grounding, protocol, store

FINAL_OK = {"FINAL", "AMENDED", "CORRECTED"}
VERIFIED = {"verified", "confirmed"}  # a value counts when code found its quote, or a clinician confirmed it against the source (V1 item 2.2)


def case_docs(case_id, state=None):
    """The Case File's documents as the clinicians confirmed them: confirmations (document type, dates, values) are overlaid
    on the model's reading at read time, so they win and survive a re-process (V1 item 2.2)."""
    return confirm.apply_to_docs(store.list_docs(case_id), store.get_state(case_id) if state is None else state)
STATUS_RANK = {"CORRECTED": 4, "AMENDED": 4, "FINAL": 3, "PRELIMINARY": 1, "DRAFT": 0, "CANCELLED": -1, "UNKNOWN": 0}


def _doc_sort_key(d):
    """Clinical order: event date, then report date, then status (V1 item 3.1)."""
    c = d.get("classification") or {}
    return (*dates.doc_dates(d)["sort"], STATUS_RANK.get(c.get("status"), 0))


NEGATIVE = {"DRAFT", "PRELIMINARY", "CANCELLED"}


def _is_final(d, overrides=None):
    """FINAL/AMENDED/CORRECTED and not explicitly unsigned. A document with no explicit status marker counts when it carries
    a signature line, or when a clinician has attested it is the final signed version (audited override)."""
    c = d.get("classification") or {}
    if c.get("signed") == "no" or c.get("status") in NEGATIVE:
        return False
    if c.get("status") in FINAL_OK:
        return True
    if c.get("status") == "UNSTATED":
        att = ((overrides or {}).get("documents") or {}).get(d["doc_id"], {})
        return c.get("signed") == "yes" or bool(att.get("attested_final"))
    return False


def _needs_confirmation(d):
    c = d.get("classification") or {}
    return c.get("status") == "UNSTATED" and c.get("signed") != "no"


def _study_lines(d):
    """The header lines that name the study ("CECT THORAX", "MRI BRAIN"): the title keyword hits of the first lines of page 1 (V1 item
    3.2). Department, hospital, patient and signature lines carry no study keyword and never count ("Head: Dr. Rao" is not a brain study)."""
    pages = d.get("pages") or []
    text = (pages[0].get("text") if pages and isinstance(pages[0], dict) else "") or ""
    if not text:
        return ""
    ev = doctype.keyword_type([text], "").get("evidence") or []
    return "\n".join(e.get("quote") or "" for e in ev if str(e.get("where", "")).startswith("line"))


def _region_ok(d, region):
    if not region:
        return True
    c = d.get("classification") or {}
    hay = " ".join([c.get("body_region", ""), c.get("title", ""), d.get("filename", ""), _study_lines(d)]).lower()
    return re.search(r"\b(?:" + region + ")", hay) is not None  # whole words from the start ("rect" still matches rectum / rectal)


def _doc_types(d) -> set:
    """The document types a document may be: the model's, plus the keyword table's when they disagree and no clinician has
    confirmed the type yet (V1 item 3.2). A confirmed type (rules.case_docs overlay) is the only one."""
    c = d.get("classification") or {}
    types = {c.get("doc_type")} if c.get("doc_type") else set()
    dis = c.get("doc_type_disagreement")
    if dis and dis.get("keyword_type") and not c.get("doc_type_confirmed_by"):
        types.add(dis["keyword_type"])
    return types


def _type_note(d):
    c = d.get("classification") or {}
    dis = c.get("doc_type_disagreement") or {}
    return dis.get("note") or f"the reader model (Qwen3.5-4B, Chinese, non-medical) called it {c.get('doc_type')} and the title keywords say {dis.get('keyword_type')}"


def resolve_facts(docs, overrides=None):
    """Case-level view of every fact. Current value = most recent verified value from a FINAL/SIGNED document; if none,
    the most recent verified value; else the most recent value. Every value is kept in `history` (longitudinal record)."""
    hist = {}
    for d in sorted([d for d in docs if d.get("state") == "ready"], key=_doc_sort_key):
        c = d.get("classification") or {}
        for fid, f in (d.get("facts") or {}).items():
            hist.setdefault(fid, []).append({**f, "doc_id": d["doc_id"], "doc_title": c.get("title") or d["filename"], "doc_type": c.get("doc_type"),
                                             "doc_types": sorted(_doc_types(d)), "type_note": _type_note(d) if len(_doc_types(d)) > 1 else "",
                                             "date": dates.doc_dates(d)["event"] or None, "report_date": dates.doc_dates(d)["report"] or None,
                                             "date_unconfirmed": dates.doc_dates(d)["unconfirmed"], "date_questionable": dates.doc_dates(d)["questionable"],
                                             "date_flags": dates.doc_dates(d)["flags"],
                                             "doc_final": _is_final(d, overrides), "doc_status": c.get("status")})
    out = {}
    for fid, h in hist.items():
        tiers = [[e for e in h if e["verification"] in VERIFIED and e["doc_final"] and e["state"] == "present"],
                 [e for e in h if e["verification"] in VERIFIED], h]
        out[fid] = {"current": next(t[-1] for t in tiers if t), "history": h}
    return out


LEVEL_LABEL = {1: "Level 1: Case File", 2: "Level 2: Records"}  # V1 item 4.2: records present, final, signed, right patient; then the values in them
LEVEL_WHAT = {1: "the record is missing, not final or not this patient", 2: "a required value is missing, pending or not verified in the record"}


def _hospital():
    try:
        from . import org
        return org.load().get("hospital") or {}
    except Exception:
        return {}


def _dept_id(name):
    try:
        from . import org
        return org.department_id(name) if name else None
    except Exception:
        return None


def _dept_name(dept_id):
    """The department's name, or "" when the id is not (or no longer) a department of org.json."""
    try:
        from . import org
        d = org.department(dept_id) if dept_id else None
        return d["name"] if d else ""
    except Exception:
        return ""


def _title(x):
    return x.get("doc_title") or (x.get("classification") or {}).get("title") or x.get("filename") or x.get("doc_id") or ""


def _evaluate_record(req, ready, facts, overrides, cat):
    """One record of the protocol against the Case File: the verdict (status, problems, evidence, needs) as before, now split into
    Level 1 (the record: present, final and signed, right patient, its type and date settled) and Level 2 (the required values in it:
    present, verified, not pending) with the document a Level 2 gap sits in (V1 item 4.2). `problems` keeps its order: confirmations
    first, then the record's status, then the fields."""
    r = {"id": req["id"], "label": req["label"], "department": req["department"], "status": "satisfied", "problems": [], "evidence": []}
    l1 = {"status": "satisfied", "problems": [], "needs": []}
    l2 = {"status": "satisfied", "problems": [], "needs": []}
    source_doc = None  # the document a Level 2 gap sits in (routing: the department that uploaded it)
    w = (overrides.get("requirements") or {}).get(req["id"])
    if w and w.get("waived"):
        r["status"] = "waived"; r["waiver"] = w
        r["problems"].append(f"Waived for this Case File by {w.get('by') or 'clinician'}: {w.get('reason') or 'no reason given'}")
        r["level"] = None; r["level1"] = l1; r["level2"] = l2
        return r
    date_needs = []  # (doc or history entry, why, level): a clinician confirms the date that decides this requirement (V1 item 3.1)
    type_needs = []  # (doc or history entry, level): documents that match under only one of their two possible types (V1 item 3.2)
    if req.get("applies_if_doc_type_present"):
        present = [d for d in ready if req["applies_if_doc_type_present"] in _doc_types(d)]
        if not present:
            r["status"] = "not_applicable"; r["level"] = None; r["level1"] = l1; r["level2"] = l2
            return r
        type_needs += [(d, 1) for d in present if len(_doc_types(d)) > 1]  # whether this requirement applies rests on a disputed type
    allowed = set(req.get("fact_doc_types") or req.get("doc_types") or [])
    if not req.get("facts_only"):
        want = set(req["doc_types"])
        cands = [d for d in ready if _doc_types(d) & want and _region_ok(d, req.get("region"))]
        type_needs += [(d, 1) for d in cands if len(_doc_types(d)) > 1 and len(_doc_types(d) & want) == 1]
        if req.get("must_postdate_doc_type"):
            refs = [x for x in ready if req["must_postdate_doc_type"] in _doc_types(x)]
            type_needs += [(x, 1) for x in refs if len(_doc_types(x)) > 1]  # the end-of-treatment reference rests on a disputed type
            ref = max([dates.doc_dates(x)["event"] for x in refs if dates.doc_dates(x)["event"] and not dates.doc_dates(x)["questionable"]], default="")
            for x in refs:  # the reference event (end of treatment) has no trusted date: nothing can be placed after it
                if dates.doc_dates(x)["questionable"]:
                    date_needs.append((x, f"the {req['label'].lower()} must be dated after it", 1))
            if ref:  # "after treatment" compares event dates (V1 item 3.1)
                undated = [d for d in cands if dates.doc_dates(d)["questionable"]]
                cands = [d for d in cands if not dates.doc_dates(d)["questionable"] and dates.doc_dates(d)["event"] > ref]
                r["postdate_reference"] = ref
                if not cands:  # only undated or flagged candidates: ask for their date instead of calling the record missing
                    date_needs += [(d, f"it must be dated after {ref}", 1) for d in undated]
        cands.sort(key=_doc_sort_key, reverse=True)
        finals = [d for d in cands if _is_final(d, overrides)]
        if not cands:
            r["status"] = l1["status"] = "missing_record"
            p = f"No {req['label'].lower()} in the Case File" + (f" dated after {r['postdate_reference']}" if r.get("postdate_reference") else "")
            r["problems"].append(p); l1["problems"].append(p)
        elif not finals:
            d = cands[0]; c = d["classification"]; source_doc = d
            if _needs_confirmation(d):
                r["status"] = l1["status"] = "needs_confirmation"
                p = (f"{c.get('title') or d['filename']} has no explicit status or signature line: confirm it is the final, signed version"
                     + ("; " + "; ".join(c.get("status_notes") or []) if c.get("status_notes") else ""))
                r["problems"].append(p); l1["problems"].append(p)
                r.setdefault("needs", []).append({"type": "attest_final", "doc_id": d["doc_id"]}); l1["needs"].append({"type": "attest_final", "doc_id": d["doc_id"]})
            else:
                r["status"] = l1["status"] = "not_final"
                p = (f"{c.get('title') or d['filename']} is {c.get('status', 'UNKNOWN')}" + (" and unsigned" if c.get("signed") == "no" else "")
                     + ": a final, signed version is required")
                r["problems"].append(p); l1["problems"].append(p)
            r["evidence"].append({"doc_id": d["doc_id"], "quote": c.get("status_quote") or c.get("signature_quote")})
        else:
            d = finals[0]; c = d["classification"]; source_doc = d
            r["evidence"].append({"doc_id": d["doc_id"], "quote": c.get("status_quote") or c.get("signature_quote")})
            if c.get("status") == "UNSTATED":
                att = (overrides.get("documents") or {}).get(d["doc_id"], {})
                r["notes"] = [f"status not explicit in {c.get('title') or d['filename']}; " + ("attested final by " + att.get("by", "clinician") if att.get("attested_final") else "signature line present")]
            if d.get("identity") == "mismatch_or_missing":
                p = f"Patient identifier not found in {c.get('title') or d['filename']}: check the document belongs to this patient"
                r["problems"].append(p); l1["problems"].append(p); r["status"] = l1["status"] = "needs_review"
            elif d.get("identity") == "id_differs":
                p = f"{c.get('title') or d['filename']} prints an identifier this Case File does not know: check the document belongs to this patient"
                r["problems"].append(p); l1["problems"].append(p); r["status"] = l1["status"] = "needs_review"
    else:  # facts_only: Level 1 is a final document of a type that can carry the values (the record that should document them)
        carriers = [d for d in ready if _doc_types(d) & allowed and _is_final(d, overrides)]
        carriers.sort(key=_doc_sort_key, reverse=True)
        if carriers:
            source_doc = carriers[0]
        else:
            l1["status"] = "missing_record"
            l1["problems"].append("No final, signed " + " / ".join(allowed_label(cat, t) for t in sorted(allowed)) + " report in the Case File to carry: "
                                  + ", ".join(cat[f]["label"] for f in req.get("required_facts", []) if f in cat))
    # required fields (Level 2)
    missing, pending, review = [], [], []
    open_doc = None  # the document the open value sits in (pending, approximate or non-final)
    for fid in req.get("required_facts", []):
        hist = [h for h in facts.get(fid, {}).get("history", []) if not allowed or set(h["doc_types"]) & allowed]
        type_needs += [(h, 2) for h in hist if allowed and len(h["doc_types"]) > 1 and len(set(h["doc_types"]) & allowed) == 1
                       and h["doc_id"] not in {x["doc_id"] for x, _ in type_needs}]
        good = [h for h in hist if h["verification"] in VERIFIED and h["doc_final"] and h["state"] == "present"]
        if req.get("must_postdate_doc_type") and r.get("postdate_reference"):
            good = [h for h in good if (h["date"] or "") > r["postdate_reference"]]
        if good:
            g = sorted(good, key=lambda h: h["date"] or "")[-1]
            r["evidence"].append({"doc_id": g["doc_id"], "fact": fid, "value": g["value"], "quote": g["quote"]})
            if len({h["doc_id"] for h in good}) > 1 and len({grounding.norm(h["value"]) for h in good}) > 1:  # which value is current depends on the dates
                seen = set()
                for h in good:
                    if h.get("date_questionable") and h["doc_id"] not in seen:
                        seen.add(h["doc_id"]); date_needs.append((h, f"{cat[fid]['label'].lower()} is documented more than once and the current value depends on the dates", 2))
        elif any(h["state"] == "pending" for h in hist):
            h = [h for h in hist if h["state"] == "pending"][-1]; open_doc = open_doc or h
            pending.append(f"{cat[fid]['label']}: \"{h['value']}\" in {h['doc_title']}")
        elif any(h["verification"] == "needs_review" for h in hist):
            open_doc = open_doc or [h for h in hist if h["verification"] == "needs_review"][-1]
            review.append(cat[fid]["label"])
        elif hist and not any(h["doc_final"] for h in hist):
            open_doc = open_doc or hist[-1]
            pending.append(f"{cat[fid]['label']}: only in a non-final document ({hist[-1]['doc_title']})")
        else:
            missing.append(cat[fid]["label"])
    if missing and r["status"] == "missing_record":
        r.setdefault("notes", []).append("That record must document: " + ", ".join(missing))
        l2["problems"].append("Required field not documented: " + ", ".join(missing))
    elif missing:
        p = "Required field not documented: " + ", ".join(missing); r["problems"].append(p); l2["problems"].append(p)
    if pending:
        r["problems"] += ["Pending: " + p for p in pending]; l2["problems"] += ["Pending: " + p for p in pending]
    if review:
        p = "Needs expert review (approximate source match): " + ", ".join(review); r["problems"].append(p); l2["problems"].append(p)
    if missing or pending:
        l2["status"] = "missing_field"
    elif review:
        l2["status"] = "needs_review"
    if r["status"] in ("satisfied", "needs_confirmation"):
        if missing or pending:
            r["status"] = "missing_field" if r["status"] == "satisfied" else r["status"]
        elif review and r["status"] == "satisfied":
            r["status"] = "needs_review"
    if type_needs and r["status"] != "not_applicable":  # the document type decides whether this record counts: a clinician confirms it
        r["status"] = "needs_confirmation"
        seen = set()
        for x, lvl in type_needs:
            did = x["doc_id"]
            if did in seen:
                continue
            seen.add(did)
            p = f"Confirm the document type of {_title(x)}: {x.get('type_note') or _type_note(x)}"
            r["problems"].insert(0, p)
            r.setdefault("needs", []).append({"type": "confirm_doc_type", "doc_id": did})
            lv = l1 if lvl == 1 else l2
            lv["status"] = "needs_confirmation"; lv["problems"].insert(0, p); lv["needs"].append({"type": "confirm_doc_type", "doc_id": did})
            if not any(e.get("doc_id") == did for e in r["evidence"]):
                r["evidence"].append({"doc_id": did, "quote": ""})
    if date_needs and r["status"] != "not_applicable":  # confirmation first (like an attestation): the date decides the check
        r["status"] = "needs_confirmation"
        seen = set()
        for x, why, lvl in date_needs:
            did = x["doc_id"]
            if did in seen:
                continue
            seen.add(did)
            dd = dates.doc_dates(x) if "classification" in x else None
            cause = "no document date was found in its text" if (dd is None or dd["unconfirmed"]) else "its date is flagged (" + "; ".join(dd["flags"]) + ")"
            if dd is None and x.get("date_flags"):
                cause = "its date is flagged (" + "; ".join(x["date_flags"]) + ")"
            p = f"Confirm the date of {_title(x)}: {cause} and {why}"
            r["problems"].insert(0, p)
            r.setdefault("needs", []).append({"type": "confirm_dates", "doc_id": did})
            lv = l1 if lvl == 1 else l2
            lv["status"] = "needs_confirmation"; lv["problems"].insert(0, p); lv["needs"].append({"type": "confirm_dates", "doc_id": did})
            if not any(e.get("doc_id") == did for e in r["evidence"]):
                r["evidence"].append({"doc_id": did, "quote": ""})
    r["level"] = 1 if l1["status"] != "satisfied" else 2 if l2["status"] != "satisfied" else None
    r["level_label"] = LEVEL_LABEL.get(r["level"], "")
    r["level1"], r["level2"] = l1, l2
    if r["level"] == 2 and open_doc:
        src = open_doc  # the document the pending, approximate or non-final value sits in
    elif r["level"] == 2 and req.get("facts_only"):
        src = None  # a value missing from every carrier (e.g. EGFR with only the histopathology filed): the department that owns the test is asked
    else:
        src = source_doc
    r["source_doc_id"] = (src or {}).get("doc_id")
    return r


def allowed_label(cat, doc_type):
    return doc_type.replace("_", " ")


def evaluate(case_id):
    """The Pre-Authorization gate, or None for a Case File that is not listed yet (no protocol: records are shown but nothing is checked).

    V1 item 4.1: every record of the protocol carries its NCG tier for the Case File's setting (a Essential, b Optimal, c Optional, none =
    not applicable in that setting); a record counts (is in `requirements`) when it is Essential, or Optimal at an Optimal hospital; the
    others are evaluated the same way and listed under `shown` (never counted, never routed). V1 item 4.2: each result carries its Level 1
    (Case File) and Level 2 (Records) verdicts. V1 item 4.3: a document that failed to read and was neither re-processed nor dismissed
    blocks `passed` (`blockers`)."""
    case = store.get_case(case_id)
    if not case.get("protocol"):
        return None
    prot = protocol.get(case["protocol"])
    cat = protocol.facts()
    state = store.get_state(case_id)
    docs = case_docs(case_id, state)
    ready = [d for d in docs if d.get("state") == "ready"]
    overrides = state.get("overrides") or {}
    facts = resolve_facts(docs, overrides)
    setting = case.get("setting") or ""
    hospital = _hospital()
    level = case.get("hospital_level") or hospital.get("level") or "essential"
    results, shown = [], []
    for req in protocol.records(prot):
        tier = protocol.tier_for(req, setting)
        is_required = tier != "none" and protocol.required(req, setting, level)
        if tier == "none":
            r = {"id": req["id"], "label": req["label"], "department": req["department"], "status": "not_applicable", "problems": [], "evidence": [],
                 "level": None, "level1": {"status": "satisfied", "problems": [], "needs": []}, "level2": {"status": "satisfied", "problems": [], "needs": []}}
        else:
            r = _evaluate_record(req, ready, facts, overrides, cat)
        r["tier"] = tier; r["tier_label"] = protocol.TIER_LABEL.get(tier, tier); r["required"] = is_required
        for k in ("source", "sources", "note", "tier_basis"):
            if req.get(k):
                r[k] = req[k]
        if req.get("tiers") and not setting:
            r["setting_note"] = "NCG setting not recorded for this Case File: the strictest tier applies until the coordinator records it"
        elif req.get("tiers") and setting:
            r["setting_note"] = f"tier {tier} in the {protocol.setting_label(prot['id'], setting) or setting} setting"
        if tier == "b" and not is_required:
            r["tier_note"] = "NCG Optimal: shown; required at an Optimal hospital"
        elif tier == "c":
            r["tier_note"] = "NCG Optional: shown only"
        elif tier == "none":
            r["tier_note"] = "not applicable in this NCG setting"
        (results if is_required else shown).append(r)
    optional = []
    for opt in prot.get("optional", []):
        hit = [d for d in ready if _doc_types(d) & set(opt["doc_types"])]
        optional.append({"id": opt["id"], "label": opt["label"], "available": bool(hit), "doc_ids": [d["doc_id"] for d in hit]})
    core = []  # informational MDT minimum core data (not part of the gate): documented anywhere in the Case File, verified
    for c in prot.get("core_data", []):
        hits = [h for fid in c["facts"] for h in facts.get(fid, {}).get("history", []) if h["verification"] in VERIFIED and h["state"] == "present"]
        core.append({"id": c["id"], "label": c["label"], "present": bool(hits),
                     "evidence": [{"doc_id": h["doc_id"], "fact": fid, "value": h["value"], "quote": h["quote"]} for fid in c["facts"] for h in facts.get(fid, {}).get("history", [])
                                  if h["verification"] in VERIFIED and h["state"] == "present"][:3]})
    applicable = [r for r in results if r["status"] not in ("not_applicable", "waived")]
    ok = [r for r in applicable if r["status"] == "satisfied"]
    listed = {r["id"] for r in protocol.records(prot)}
    orphaned = [{"requirement": k, "by": w.get("by") or "", "reason": w.get("reason") or "", "at": w.get("at") or ""}
                for k, w in sorted((overrides.get("requirements") or {}).items()) if w and w.get("waived") and k not in listed]
    failed = [d for d in docs if d.get("state") == "error" and not d.get("dismissed")]  # V1 item 4.3: re-process or dismiss before the gate can pass
    dismissed = [d for d in docs if d.get("state") == "error" and d.get("dismissed")]
    blockers = [{"doc_id": d["doc_id"], "filename": d.get("rel_path") or d.get("filename") or d["doc_id"], "error": d.get("error") or "could not be read",
                 "department": d.get("department")} for d in failed]
    processing = [d for d in docs if d.get("state") not in ("ready", "error")]
    gate = {"evaluated": store.now_iso(), "protocol": prot["id"], "protocol_version": prot.get("version"), "setting": setting,
            "setting_label": protocol.setting_label(prot["id"], setting) if setting else "",
            "hospital_level": level, "hospital_type": hospital.get("type") or "",
            "pmjay_note": "PM-JAY mandatory document lists per package are not available yet (pendings); the hospital type ("
                          + (hospital.get("type") or "not set") + ") changes only that paperwork, never this check.",
            "tiers_note": "NCG tiers: a = Essential (required everywhere), b = Optimal (required at an Optimal hospital, otherwise shown), c = Optional (shown only). Clinical review before real use.",
            "passed": len(ok) == len(applicable) and not processing and not blockers,
            "readiness": round(100 * len(ok) / max(len(applicable), 1)), "satisfied": len(ok), "total": len(applicable),
            "levels": {"1": {"label": LEVEL_LABEL[1], "what": LEVEL_WHAT[1], "open": sum(1 for r in applicable if r.get("level") == 1)},
                       "2": {"label": LEVEL_LABEL[2], "what": LEVEL_WHAT[2], "open": sum(1 for r in applicable if r.get("level") == 2)}},
            "requirements": results, "shown": shown, "optional": optional, "core_data": core, "core_data_source": prot.get("core_data_source"), "policy_basis": prot.get("policy_basis"),
            "blockers": blockers,
            "orphaned_waivers": orphaned,  # recorded for a record this protocol version no longer lists (renamed or removed): review
            "documents": {"total": len(docs), "ready": len(ready), "processing": len(processing),
                          "errors": len([d for d in docs if d.get("state") == "error"]),
                          "failed": [d["doc_id"] for d in failed], "dismissed": [{"doc_id": d["doc_id"], **(d.get("dismissed") or {})} for d in dismissed],
                          "non_final": [d["doc_id"] for d in ready if not _is_final(d, overrides)],
                          "unconfirmed": [d["doc_id"] for d in ready if _needs_confirmation(d) and not _is_final(d, overrides)],
                          "date_unconfirmed": [d["doc_id"] for d in ready if dates.doc_dates(d)["unconfirmed"]],
                          "type_disagreements": [d["doc_id"] for d in ready if len(_doc_types(d)) > 1],
                          "date_flags": {d["doc_id"]: dates.doc_dates(d)["flags"] for d in ready if dates.doc_dates(d)["flags"]},
                          "identity_flags": [d["doc_id"] for d in ready if d.get("identity") in ("mismatch_or_missing", "id_differs")]}}
    return gate


def case_signature(case_id, state=None):
    """What a summary or brief was generated from (V1 item 4.5): the processed documents (id, state, processed time, protocol they
    were extracted under), the active clinician confirmations, the protocol and its version, the NCG setting and the hospital level.
    Stored with every artefact; a different hash on load means the Case File changed since it was generated."""
    st = store.get_state(case_id) if state is None else state
    case = store.get_case(case_id) or {}
    docs = store.list_docs(case_id)
    parts = sorted(f"{d['doc_id']}:{d.get('state')}:{d.get('processed') or ''}:{d.get('extracted_under') or ''}" for d in docs)
    confs = sorted(c["id"] for c in confirm.active(st))
    prot = protocol.get(case["protocol"]) if case.get("protocol") else {}
    level = case.get("hospital_level") or _hospital().get("level") or "essential"  # as the gate uses it
    basis = {"documents": parts, "confirmations": confs, "protocol": case.get("protocol") or "", "protocol_version": prot.get("version") or "",
             "setting": case.get("setting") or "", "hospital_level": level}
    return {"hash": hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:16],
            "documents": len(docs), "ready": sum(1 for d in docs if d.get("state") == "ready"), "confirmations": len(confs),
            "protocol": basis["protocol"], "protocol_version": basis["protocol_version"], "setting": basis["setting"], "hospital_level": basis["hospital_level"],
            "at": store.now_iso()}


def stale_reason(then, now):
    """Plain words for why an artefact is stale, from its stored signature and the current one; "" when they agree."""
    if not then or then.get("hash") == now.get("hash"):
        return ""
    why = []
    for k, what in (("documents", "document"), ("ready", "processed document"), ("confirmations", "clinician confirmation")):
        d = (now.get(k) or 0) - (then.get(k) or 0)
        if d:
            why.append(f"{abs(d)} {what}{'s' if abs(d) != 1 else ''} {'added' if d > 0 else 'removed'}")
    if then.get("protocol") != now.get("protocol") or then.get("protocol_version") != now.get("protocol_version"):
        why.append(f"protocol {then.get('protocol') or '?'} v{then.get('protocol_version') or '?'} is now {now.get('protocol') or '?'} v{now.get('protocol_version') or '?'}")
    if then.get("setting") != now.get("setting"):
        why.append("the NCG setting changed")
    if then.get("hospital_level") != now.get("hospital_level"):
        why.append("the hospital level changed")
    return "The Case File changed since this was generated" + (": " + ", ".join(why) if why else " (documents were re-processed or confirmations changed)")


def set_override(case_id, kind, key, value: dict, by=""):
    """Per-Case-File clinical override: waive a requirement, or attest a document is the final signed version. Audited."""
    st = store.get_state(case_id)
    ov = st.setdefault("overrides", {}).setdefault(kind, {})
    if value is None:
        ov.pop(key, None)
    else:
        ov[key] = {**value, "by": by, "at": store.now_iso()}
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "override", "target": kind, "key": key, "value": value, "by": by})


def _notify(*a, **kw):
    """In-app notification (V1 item 4.4); never lets a notification problem break the gate."""
    try:
        from . import notify
        return notify.notify(*a, **kw)
    except ImportError:
        return None
    except Exception as e:  # unknown department, disk problem: the gate result still stands
        return {"error": f"{e.__class__.__name__}: {e}"}


def _route(r, case_id):
    """Where a gap goes (V1 items 4.2 / 4.4): a Level 1 gap to the department that owns the record type (the protocol's Responsible
    Department); a Level 2 gap to the department that uploaded the record the value should be in, when a department uploaded it
    (otherwise the Responsible Department). Returns (department name, department id or None, doc id or None)."""
    name, doc_id = r["department"], r.get("source_doc_id")
    if r.get("level") == 2 and doc_id:
        d = store.get_doc(case_id, doc_id) or {}
        if d.get("department") and _dept_name(d["department"]):
            return _dept_name(d["department"]), d["department"], doc_id
    return name, _dept_id(name), doc_id


def sync_actions(case_id, gate, by=""):
    """Open an action (request) for every unmet requirement; complete actions whose requirement is now satisfied. Each request
    carries its level and goes to the department that can act on it (V1 item 4.2); the department is notified when a request opens
    or closes and the coordinator when the Case File is ready (V1 item 4.4)."""
    st = store.get_state(case_id)
    if gate is None:  # not listed yet
        st["gate"] = None
        store.save_state(case_id, st)
        return st
    actions = st.get("actions", [])
    today = date.today()
    case = store.get_case(case_id); prot = protocol.get(case["protocol"])
    patient = (case.get("patient") or {}).get("name") or case_id
    sla = {r["id"]: r.get("sla_days", 3) for r in protocol.records(prot)}
    by_req = {a["requirement"]: a for a in actions if a.get("source") == "pre_authorization" and a["status"] != "completed"}
    required_ids = {r["id"] for r in gate["requirements"]}
    shown_ids = {r["id"] for r in gate.get("shown", [])}
    for rid, a in list(by_req.items()):  # nothing left to request: the protocol no longer lists the record, or no longer requires it here
        if rid not in required_ids:
            if rid in shown_ids:  # the NCG setting or the hospital level changed: the record is now shown, not counted
                event, reason = "Closed: no longer required for this Case File (NCG tier for its setting and hospital level)", "requirement no longer required (NCG tier)"
            else:
                event, reason = f"Closed: the protocol ({prot['id']} v{prot.get('version')}) no longer lists this record", "requirement removed from the protocol"
            a["status"] = "completed"; a["completed"] = store.now_iso()
            a["history"].append({"ts": store.now_iso(), "event": event})
            store.audit(case_id, {"kind": "action_completed", "action": a["id"], "requirement": rid, "reason": reason})
            if a.get("department_id"):
                _notify({"department": a["department_id"]}, "request_closed", case_id, f"{a.get('label') or rid} no longer needed for {patient} ({case_id})",
                        event.replace("Closed: ", "The request closed: ") + ".", action_id=a["id"], requirement=rid, level=a.get("level"))
            by_req.pop(rid)
    for r in gate["requirements"]:
        a = by_req.get(r["id"])
        if r["status"] in ("satisfied", "not_applicable", "waived"):
            if a:
                a["status"] = "completed"; a["completed"] = store.now_iso()
                a["history"].append({"ts": store.now_iso(), "event": "Re-check: requirement met", "evidence": [e["doc_id"] for e in r["evidence"]]})
                store.audit(case_id, {"kind": "action_completed", "action": a["id"], "requirement": r["id"]})
                if a.get("department_id"):
                    why = {"waived": ("waived", "The request closed: the requirement was waived for this Case File (audited)."),
                           "not_applicable": ("no longer applicable", "The request closed: the requirement does not apply to this Case File any more.")}
                    head, text = why.get(r["status"], ("received", "The request closed automatically: the Case File re-check found the requirement met."))
                    _notify({"department": a["department_id"]}, "request_closed", case_id, f"{r['label']} {head} for {patient} ({case_id})",
                            text, action_id=a["id"], requirement=r["id"], level=a.get("level"))
            continue
        what = "; ".join(r["problems"]) or r["label"]
        dept, dept_id, doc_id = _route(r, case_id)
        if a:
            legacy = "level" not in a  # a request opened before the two levels existed: classified once, not a move
            moved = (a.get("department") != dept) or (not legacy and a.get("level") != r.get("level"))
            if a["what"] != what or moved or legacy:
                a["what"] = what
                if moved:
                    old_dept = a.get("department_id")
                    a["history"].append({"ts": store.now_iso(), "event": f"Re-check: {LEVEL_LABEL.get(r.get('level'), 'gap')} routed to {dept}", "detail": what})
                    a["level"], a["level_label"], a["department"], a["department_id"], a["source_doc_id"] = r.get("level"), r.get("level_label", ""), dept, dept_id, doc_id
                    if old_dept and old_dept != dept_id:  # the department it left is told, so its inbox makes sense
                        _notify({"department": old_dept}, "request_closed", case_id, f"{r['label']} request for {patient} ({case_id}) moved to {dept}",
                                f"The request now sits with {dept} ({LEVEL_LABEL.get(r.get('level'), 'gap')}).", action_id=a["id"], requirement=r["id"], level=r.get("level"))
                    if dept_id:
                        _notify({"department": dept_id}, "request", case_id, f"{r['label']} needed for {patient} ({case_id})", what,
                                action_id=a["id"], requirement=r["id"], due=a.get("due"), level=r.get("level"), level_label=r.get("level_label", ""))
                elif legacy:
                    a["history"].append({"ts": store.now_iso(), "event": f"Re-check: {LEVEL_LABEL.get(r.get('level'), 'gap')}", "detail": what})
                    a["level"], a["level_label"], a["department_id"], a["source_doc_id"] = r.get("level"), r.get("level_label", ""), dept_id, doc_id
                else:
                    a["history"].append({"ts": store.now_iso(), "event": "Re-check: gap updated", "detail": what})
            continue
        a = {"id": "A" + uuid.uuid4().hex[:6], "source": "pre_authorization", "requirement": r["id"], "label": r["label"],
             "department": dept, "department_id": dept_id, "level": r.get("level"), "level_label": r.get("level_label", ""), "source_doc_id": doc_id,
             "what": what, "status": "pending", "created": store.now_iso(),
             "due": (today + timedelta(days=sla.get(r["id"], 3))).isoformat(), "history": [{"ts": store.now_iso(), "event": f"Gap detected ({LEVEL_LABEL.get(r.get('level'), 'gap')}), routed to " + dept}]}
        actions.append(a)
        store.audit(case_id, {"kind": "action_created", "action": a["id"], "requirement": r["id"], "department": dept, "level": r.get("level"), "what": what})
        if dept_id:
            _notify({"department": dept_id}, "request", case_id, f"{r['label']} needed for {patient} ({case_id})", what,
                    action_id=a["id"], requirement=r["id"], due=a["due"], level=r.get("level"), level_label=r.get("level_label", ""))
    for a in actions:
        if a["status"] == "pending" and a.get("due") and a["due"] < today.isoformat():
            a["status"] = "overdue"
    before = st.get("gate") or {}
    if gate.get("passed") and not before.get("passed"):  # the coordinator hears once, when the Case File becomes ready (V1 item 4.4)
        n = _notify({"role": "coordinator"}, "case_ready", case_id, f"Case File ready: {patient} ({case_id})",
                    f"Every Pre-Authorization check is met ({gate['satisfied']} of {gate['total']} records). The Case File summary can be compiled.", by=by)
        store.audit(case_id, {"kind": "case_ready", "by": by, "satisfied": gate["satisfied"], "total": gate["total"], "notified": bool(n and not n.get("error"))})
    st["actions"] = actions
    st["gate"] = gate
    store.save_state(case_id, st)
    return st
