"""Pre-Authorization gate: deterministic evaluation of the case protocol over the processed documents.

No model is involved here. For every mandatory record it decides: satisfied / missing record / not final-signed /
missing or pending field / needs expert review, names the Responsible Department, and keeps the action list in sync
(new gaps open actions, resolved gaps close them with the evidence document)."""
import re
import uuid
from datetime import date, datetime, timedelta

from . import protocol, store

FINAL_OK = {"FINAL", "AMENDED", "CORRECTED"}
STATUS_RANK = {"CORRECTED": 4, "AMENDED": 4, "FINAL": 3, "PRELIMINARY": 1, "DRAFT": 0, "CANCELLED": -1, "UNKNOWN": 0}


def _doc_sort_key(d):
    c = d.get("classification") or {}
    return (c.get("report_date_iso") or "", STATUS_RANK.get(c.get("status"), 0))


def _is_final(d):
    c = d.get("classification") or {}
    return c.get("status") in FINAL_OK and c.get("signed") != "no"


def _region_ok(d, region):
    if not region:
        return True
    c = d.get("classification") or {}
    hay = " ".join([c.get("body_region", ""), c.get("title", ""), d.get("filename", "")]).lower()
    return re.search(region, hay) is not None


def resolve_facts(docs):
    """Case-level view of every fact. Current value = most recent verified value from a FINAL/SIGNED document; if none,
    the most recent verified value; else the most recent value. Every value is kept in `history` (longitudinal record)."""
    hist = {}
    for d in sorted([d for d in docs if d.get("state") == "ready"], key=_doc_sort_key):
        c = d.get("classification") or {}
        for fid, f in (d.get("facts") or {}).items():
            hist.setdefault(fid, []).append({**f, "doc_id": d["doc_id"], "doc_title": c.get("title") or d["filename"], "doc_type": c.get("doc_type"),
                                             "date": c.get("report_date_iso"), "doc_final": _is_final(d), "doc_status": c.get("status")})
    out = {}
    for fid, h in hist.items():
        tiers = [[e for e in h if e["verification"] == "verified" and e["doc_final"] and e["state"] == "present"],
                 [e for e in h if e["verification"] == "verified"], h]
        out[fid] = {"current": next(t[-1] for t in tiers if t), "history": h}
    return out


def evaluate(case_id):
    case = store.get_case(case_id)
    prot = protocol.get(case["protocol"])
    cat = protocol.facts()
    docs = store.list_docs(case_id)
    ready = [d for d in docs if d.get("state") == "ready"]
    facts = resolve_facts(docs)
    results = []
    for req in prot["mandatory"]:
        r = {"id": req["id"], "label": req["label"], "department": req["department"], "status": "satisfied", "problems": [], "evidence": []}
        if req.get("applies_if_doc_type_present") and not any((d.get("classification") or {}).get("doc_type") == req["applies_if_doc_type_present"] for d in ready):
            r["status"] = "not_applicable"; results.append(r); continue
        if not req.get("facts_only"):
            cands = [d for d in ready if (d.get("classification") or {}).get("doc_type") in req["doc_types"] and _region_ok(d, req.get("region"))]
            if req.get("must_postdate_doc_type"):
                ref = [x["classification"].get("report_date_iso") for x in ready if (x.get("classification") or {}).get("doc_type") == req["must_postdate_doc_type"]]
                ref = max([x for x in ref if x], default="")
                if ref:
                    cands = [d for d in cands if (d["classification"].get("report_date_iso") or "") > ref]
                    r["postdate_reference"] = ref
            cands.sort(key=_doc_sort_key, reverse=True)
            finals = [d for d in cands if _is_final(d)]
            if not cands:
                r["status"] = "missing_record"
                r["problems"].append(f"No {req['label'].lower()} in the Case File" + (f" dated after {r['postdate_reference']}" if r.get("postdate_reference") else ""))
            elif not finals:
                d = cands[0]; c = d["classification"]
                r["status"] = "not_final"
                r["problems"].append(f"{c.get('title') or d['filename']} is {c.get('status', 'UNKNOWN')}" + (" and unsigned" if c.get("signed") == "no" else "")
                                     + ": a final, signed version is required")
                r["evidence"].append({"doc_id": d["doc_id"], "quote": c.get("status_quote") or c.get("signature_quote")})
            else:
                d = finals[0]
                r["evidence"].append({"doc_id": d["doc_id"], "quote": d["classification"].get("status_quote")})
                if any(x.get("identity") == "mismatch_or_missing" for x in [d]):
                    r["problems"].append(f"Patient identifier not found in {d['classification'].get('title') or d['filename']}: check the document belongs to this patient")
                    r["status"] = "needs_review"
        # required fields
        allowed = set(req.get("fact_doc_types") or req.get("doc_types") or [])
        missing, pending, review = [], [], []
        for fid in req.get("required_facts", []):
            hist = [h for h in facts.get(fid, {}).get("history", []) if not allowed or h["doc_type"] in allowed]
            good = [h for h in hist if h["verification"] == "verified" and h["doc_final"] and h["state"] == "present"]
            if req.get("must_postdate_doc_type") and r.get("postdate_reference"):
                good = [h for h in good if (h["date"] or "") > r["postdate_reference"]]
            if good:
                g = sorted(good, key=lambda h: h["date"] or "")[-1]
                r["evidence"].append({"doc_id": g["doc_id"], "fact": fid, "value": g["value"], "quote": g["quote"]})
            elif any(h["state"] == "pending" for h in hist):
                h = [h for h in hist if h["state"] == "pending"][-1]
                pending.append(f"{cat[fid]['label']}: \"{h['value']}\" in {h['doc_title']}")
            elif any(h["verification"] == "needs_review" for h in hist):
                review.append(cat[fid]["label"])
            elif hist and not any(h["doc_final"] for h in hist):
                pending.append(f"{cat[fid]['label']}: only in a non-final document ({hist[-1]['doc_title']})")
            else:
                missing.append(cat[fid]["label"])
        if missing:
            r["problems"].append("Required field not documented: " + ", ".join(missing))
        if pending:
            r["problems"] += ["Pending: " + p for p in pending]
        if review:
            r["problems"].append("Needs expert review (approximate source match): " + ", ".join(review))
        if r["status"] == "satisfied":
            if missing or pending:
                r["status"] = "missing_field"
            elif review:
                r["status"] = "needs_review"
        results.append(r)
    optional = []
    for opt in prot.get("optional", []):
        hit = [d for d in ready if (d.get("classification") or {}).get("doc_type") in opt["doc_types"]]
        optional.append({"id": opt["id"], "label": opt["label"], "available": bool(hit), "doc_ids": [d["doc_id"] for d in hit]})
    applicable = [r for r in results if r["status"] != "not_applicable"]
    ok = [r for r in applicable if r["status"] == "satisfied"]
    gate = {"evaluated": store.now_iso(), "protocol": prot["id"], "protocol_version": prot.get("version"),
            "passed": len(ok) == len(applicable) and not [d for d in docs if d.get("state") not in ("ready", "error")],
            "readiness": round(100 * len(ok) / max(len(applicable), 1)), "satisfied": len(ok), "total": len(applicable),
            "requirements": results, "optional": optional,
            "documents": {"total": len(docs), "ready": len(ready), "processing": len([d for d in docs if d.get("state") not in ("ready", "error")]),
                          "errors": len([d for d in docs if d.get("state") == "error"]),
                          "non_final": [d["doc_id"] for d in ready if not _is_final(d)],
                          "identity_flags": [d["doc_id"] for d in ready if d.get("identity") == "mismatch_or_missing"]}}
    return gate


def sync_actions(case_id, gate, by=""):
    """Open an action for every unmet requirement; complete actions whose requirement is now satisfied."""
    st = store.get_state(case_id)
    actions = st.get("actions", [])
    today = date.today()
    case = store.get_case(case_id); prot = protocol.get(case["protocol"])
    sla = {r["id"]: r.get("sla_days", 3) for r in prot["mandatory"]}
    by_req = {a["requirement"]: a for a in actions if a.get("source") == "pre_authorization" and a["status"] != "completed"}
    for r in gate["requirements"]:
        a = by_req.get(r["id"])
        if r["status"] in ("satisfied", "not_applicable"):
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
