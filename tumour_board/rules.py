"""Pre-Authorization gate: deterministic evaluation of the case protocol over the processed documents.

No model is involved here. For every mandatory record it decides: satisfied / missing record / not final-signed /
missing or pending field / needs expert review, names the Responsible Department, and keeps the action list in sync
(new gaps open actions, resolved gaps close them with the evidence document)."""
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


def evaluate(case_id):
    """The Pre-Authorization gate, or None for a Case File that is not listed yet (no protocol: records are shown but nothing is checked)."""
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
    results = []
    for req in prot["mandatory"]:
        r = {"id": req["id"], "label": req["label"], "department": req["department"], "status": "satisfied", "problems": [], "evidence": []}
        w = (overrides.get("requirements") or {}).get(req["id"])
        if w and w.get("waived"):
            r["status"] = "waived"; r["waiver"] = w
            r["problems"].append(f"Waived for this Case File by {w.get('by') or 'clinician'}: {w.get('reason') or 'no reason given'}")
            results.append(r); continue
        date_needs = []  # documents whose unconfirmed or flagged date decides this requirement: a clinician confirms it (V1 item 3.1)
        type_needs = []  # documents that match this requirement under only one of their two possible types (V1 item 3.2)
        if req.get("applies_if_doc_type_present"):
            present = [d for d in ready if req["applies_if_doc_type_present"] in _doc_types(d)]
            if not present:
                r["status"] = "not_applicable"; results.append(r); continue
            type_needs += [d for d in present if len(_doc_types(d)) > 1]  # whether this requirement applies rests on a disputed type
        if not req.get("facts_only"):
            want = set(req["doc_types"])
            cands = [d for d in ready if _doc_types(d) & want and _region_ok(d, req.get("region"))]
            type_needs += [d for d in cands if len(_doc_types(d)) > 1 and len(_doc_types(d) & want) == 1]
            if req.get("must_postdate_doc_type"):
                refs = [x for x in ready if req["must_postdate_doc_type"] in _doc_types(x)]
                type_needs += [x for x in refs if len(_doc_types(x)) > 1]  # the end-of-treatment reference rests on a disputed type
                ref = max([dates.doc_dates(x)["event"] for x in refs if dates.doc_dates(x)["event"] and not dates.doc_dates(x)["questionable"]], default="")
                for x in refs:  # the reference event (end of treatment) has no trusted date: nothing can be placed after it
                    if dates.doc_dates(x)["questionable"]:
                        date_needs.append((x, f"the {req['label'].lower()} must be dated after it"))
                if ref:  # "after treatment" compares event dates (V1 item 3.1)
                    undated = [d for d in cands if dates.doc_dates(d)["questionable"]]
                    cands = [d for d in cands if not dates.doc_dates(d)["questionable"] and dates.doc_dates(d)["event"] > ref]
                    r["postdate_reference"] = ref
                    if not cands:  # only undated or flagged candidates: ask for their date instead of calling the record missing
                        date_needs += [(d, f"it must be dated after {ref}") for d in undated]
            cands.sort(key=_doc_sort_key, reverse=True)
            finals = [d for d in cands if _is_final(d, overrides)]
            if not cands:
                r["status"] = "missing_record"
                r["problems"].append(f"No {req['label'].lower()} in the Case File" + (f" dated after {r['postdate_reference']}" if r.get("postdate_reference") else ""))
            elif not finals:
                d = cands[0]; c = d["classification"]
                if _needs_confirmation(d):
                    r["status"] = "needs_confirmation"
                    r["problems"].append(f"{c.get('title') or d['filename']} has no explicit status or signature line: confirm it is the final, signed version"
                                         + ("; " + "; ".join(c.get("status_notes") or []) if c.get("status_notes") else ""))
                    r.setdefault("needs", []).append({"type": "attest_final", "doc_id": d["doc_id"]})
                else:
                    r["status"] = "not_final"
                    r["problems"].append(f"{c.get('title') or d['filename']} is {c.get('status', 'UNKNOWN')}" + (" and unsigned" if c.get("signed") == "no" else "")
                                         + ": a final, signed version is required")
                r["evidence"].append({"doc_id": d["doc_id"], "quote": c.get("status_quote") or c.get("signature_quote")})
            else:
                d = finals[0]; c = d["classification"]
                r["evidence"].append({"doc_id": d["doc_id"], "quote": c.get("status_quote") or c.get("signature_quote")})
                if c.get("status") == "UNSTATED":
                    att = (overrides.get("documents") or {}).get(d["doc_id"], {})
                    r["notes"] = [f"status not explicit in {c.get('title') or d['filename']}; " + ("attested final by " + att.get("by", "clinician") if att.get("attested_final") else "signature line present")]
                if d.get("identity") == "mismatch_or_missing":
                    r["problems"].append(f"Patient identifier not found in {c.get('title') or d['filename']}: check the document belongs to this patient")
                    r["status"] = "needs_review"
                elif d.get("identity") == "id_differs":
                    r["problems"].append(f"{c.get('title') or d['filename']} prints an identifier this Case File does not know: check the document belongs to this patient")
                    r["status"] = "needs_review"
        # required fields
        allowed = set(req.get("fact_doc_types") or req.get("doc_types") or [])
        missing, pending, review = [], [], []
        for fid in req.get("required_facts", []):
            hist = [h for h in facts.get(fid, {}).get("history", []) if not allowed or set(h["doc_types"]) & allowed]
            type_needs += [h for h in hist if allowed and len(h["doc_types"]) > 1 and len(set(h["doc_types"]) & allowed) == 1
                           and h["doc_id"] not in {x["doc_id"] for x in type_needs}]
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
                            seen.add(h["doc_id"]); date_needs.append((h, f"{cat[fid]['label'].lower()} is documented more than once and the current value depends on the dates"))
            elif any(h["state"] == "pending" for h in hist):
                h = [h for h in hist if h["state"] == "pending"][-1]
                pending.append(f"{cat[fid]['label']}: \"{h['value']}\" in {h['doc_title']}")
            elif any(h["verification"] == "needs_review" for h in hist):
                review.append(cat[fid]["label"])
            elif hist and not any(h["doc_final"] for h in hist):
                pending.append(f"{cat[fid]['label']}: only in a non-final document ({hist[-1]['doc_title']})")
            else:
                missing.append(cat[fid]["label"])
        if missing and r["status"] == "missing_record":
            r.setdefault("notes", []).append("That record must document: " + ", ".join(missing))
        elif missing:
            r["problems"].append("Required field not documented: " + ", ".join(missing))
        if pending:
            r["problems"] += ["Pending: " + p for p in pending]
        if review:
            r["problems"].append("Needs expert review (approximate source match): " + ", ".join(review))
        if r["status"] in ("satisfied", "needs_confirmation"):
            if missing or pending:
                r["status"] = "missing_field" if r["status"] == "satisfied" else r["status"]
                if r["status"] == "needs_confirmation":
                    pass  # confirmation first; field problems are listed with it
            elif review and r["status"] == "satisfied":
                r["status"] = "needs_review"
        if type_needs and r["status"] != "not_applicable":  # the document type decides whether this record counts: a clinician confirms it
            r["status"] = "needs_confirmation"
            seen = set()
            for x in type_needs:
                did = x["doc_id"]
                if did in seen:
                    continue
                seen.add(did)
                title = x.get("doc_title") or (x.get("classification") or {}).get("title") or x.get("filename") or did
                r["problems"].insert(0, f"Confirm the document type of {title}: {x.get('type_note') or _type_note(x)}")
                r.setdefault("needs", []).append({"type": "confirm_doc_type", "doc_id": did})
                if not any(e.get("doc_id") == did for e in r["evidence"]):
                    r["evidence"].append({"doc_id": did, "quote": ""})
        if date_needs and r["status"] != "not_applicable":  # confirmation first (like an attestation): the date decides the check
            r["status"] = "needs_confirmation"
            seen = set()
            for x, why in date_needs:
                did = x["doc_id"]
                if did in seen:
                    continue
                seen.add(did)
                title = x.get("doc_title") or (x.get("classification") or {}).get("title") or x.get("filename") or did
                dd = dates.doc_dates(x) if "classification" in x else None
                cause = "no document date was found in its text" if (dd is None or dd["unconfirmed"]) else "its date is flagged (" + "; ".join(dd["flags"]) + ")"
                if dd is None and x.get("date_flags"):
                    cause = "its date is flagged (" + "; ".join(x["date_flags"]) + ")"
                r["problems"].insert(0, f"Confirm the date of {title}: {cause} and {why}")
                r.setdefault("needs", []).append({"type": "confirm_dates", "doc_id": did})
                if not any(e.get("doc_id") == did for e in r["evidence"]):
                    r["evidence"].append({"doc_id": did, "quote": ""})
        results.append(r)
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
    gate = {"evaluated": store.now_iso(), "protocol": prot["id"], "protocol_version": prot.get("version"), "setting": case.get("setting") or "",
            "hospital_level": case.get("hospital_level") or "",
            "passed": len(ok) == len(applicable) and not [d for d in docs if d.get("state") not in ("ready", "error")],
            "readiness": round(100 * len(ok) / max(len(applicable), 1)), "satisfied": len(ok), "total": len(applicable),
            "requirements": results, "optional": optional, "core_data": core, "core_data_source": prot.get("core_data_source"), "policy_basis": prot.get("policy_basis"),
            "documents": {"total": len(docs), "ready": len(ready), "processing": len([d for d in docs if d.get("state") not in ("ready", "error")]),
                          "errors": len([d for d in docs if d.get("state") == "error"]),
                          "non_final": [d["doc_id"] for d in ready if not _is_final(d, overrides)],
                          "unconfirmed": [d["doc_id"] for d in ready if _needs_confirmation(d) and not _is_final(d, overrides)],
                          "date_unconfirmed": [d["doc_id"] for d in ready if dates.doc_dates(d)["unconfirmed"]],
                          "type_disagreements": [d["doc_id"] for d in ready if len(_doc_types(d)) > 1],
                          "date_flags": {d["doc_id"]: dates.doc_dates(d)["flags"] for d in ready if dates.doc_dates(d)["flags"]},
                          "identity_flags": [d["doc_id"] for d in ready if d.get("identity") in ("mismatch_or_missing", "id_differs")]}}
    return gate


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


def sync_actions(case_id, gate, by=""):
    """Open an action for every unmet requirement; complete actions whose requirement is now satisfied."""
    st = store.get_state(case_id)
    if gate is None:  # not listed yet
        st["gate"] = None
        store.save_state(case_id, st)
        return st
    actions = st.get("actions", [])
    today = date.today()
    case = store.get_case(case_id); prot = protocol.get(case["protocol"])
    sla = {r["id"]: r.get("sla_days", 3) for r in prot["mandatory"]}
    by_req = {a["requirement"]: a for a in actions if a.get("source") == "pre_authorization" and a["status"] != "completed"}
    for r in gate["requirements"]:
        a = by_req.get(r["id"])
        if r["status"] in ("satisfied", "not_applicable", "waived"):
            if a:
                a["status"] = "completed"; a["completed"] = store.now_iso()
                a["history"].append({"ts": store.now_iso(), "event": "Re-check: requirement met", "evidence": [e["doc_id"] for e in r["evidence"]]})
                store.audit(case_id, {"kind": "action_completed", "action": a["id"], "requirement": r["id"]})
            continue
        what = "; ".join(r["problems"]) or r["label"]
        if a:
            if a["what"] != what:
                a["what"] = what; a["history"].append({"ts": store.now_iso(), "event": "Re-check: gap updated", "detail": what})
            continue
        a = {"id": "A" + uuid.uuid4().hex[:6], "source": "pre_authorization", "requirement": r["id"], "label": r["label"],
             "department": r["department"], "what": what, "status": "pending", "created": store.now_iso(),
             "due": (today + timedelta(days=sla.get(r["id"], 3))).isoformat(), "history": [{"ts": store.now_iso(), "event": "Gap detected, routed to " + r["department"]}]}
        actions.append(a)
        store.audit(case_id, {"kind": "action_created", "action": a["id"], "requirement": r["id"], "department": r["department"], "what": what})
    for a in actions:
        if a["status"] == "pending" and a.get("due") and a["due"] < today.isoformat():
            a["status"] = "overdue"
    st["actions"] = actions
    st["gate"] = gate
    store.save_state(case_id, st)
    return st
