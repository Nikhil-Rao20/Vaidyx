"""Department uploads before patient matching (V1 item 2.3).

Department users upload without choosing a Case File. Files land in the intake area (data/tumour_board/intake/<doc_id>/)
tagged with the uploading department, user and time; they are read and classified there, their patient identity is read
(item 2.4), and they are matched to a patient: filed into the Case File automatically when the evidence allows it, or
left in the "Needs matching" queue for a person to decide (file into a Case File, start a new Case File, or discard).
Coordinators can still upload straight into a Case File. Every step is audited in intake/audit.jsonl and, once filed,
in the Case File's own audit log; the document keeps its department, uploader and the matching decision.
"""
import asyncio, re, time
from datetime import date

from . import confirm, extract, ingest, org, rules, store

MATCH_USER = "system:matching"
QUEUE_STATES = ("queued", "reading", "classifying", "identifying", "needs_matching", "duplicate", "error")


def _doc_text(pages):
    return extract._doc_text(pages)


def read_identity(doc):
    """Patient identity as printed in the document. Item 2.3 keeps only the model's quote-checked header reading; item 2.4
    replaces this with the rule-based reader (UHID, CR No., ABHA, name variants, age / sex, DOB, relation)."""
    c = doc.get("classification") or {}
    out = {"name": {"value": c["patient_name"], "quote": c["patient_name"], "page": 0, "label": "model"} if c.get("patient_name") else None,
           "ids": [{"kind": "uhid", "value": c["patient_id"], "quote": c["patient_id"], "page": 0, "label": "model"}] if c.get("patient_id") else [],
           "age": None, "sex": None, "dob": None, "relation": None, "aadhaar_seen": False, "abha": None, "notes": []}
    return out


def decide(doc):
    """The matching decision for an intake document (plan 2.4 evidence table). Item 2.3 never links automatically: every document
    goes to the Needs matching queue; 2.4 adds auto-link on an exact identifier, suggestions and new Case Files."""
    return {"decision": "needs_matching", "case_id": None, "candidates": [], "reason": "Patient matching rules arrive with item 2.4; a person decides", "matched_on": None}


def patient_from_identity(doc):
    """A Case File patient record built from what the document prints (used when a new Case File is started from the queue)."""
    idn = doc.get("identity_read") or {}
    ids = idn.get("ids") or []
    primary = next((i for i in ids if i["kind"] in ("uhid", "mrn", "hospital_no", "reg_no")), ids[0] if ids else None)
    agesex = ""
    if idn.get("age") is not None and idn.get("sex"):
        agesex = f"{idn['age']} Y / {idn['sex']}"
    return {"name": (idn.get("name") or {}).get("value", "") or "", "mrn": primary["value"] if primary else "", "agesex": agesex,
            "ids": [{"kind": i["kind"], "value": i["value"]} for i in ids], "abha": idn.get("abha"), "age": idn.get("age"), "sex": idn.get("sex"),
            "dob": idn.get("dob"), "relation": (idn.get("relation") or {}).get("name") if idn.get("relation") else None}


def next_case_id(today=None):
    """TB-<year>-<nnnn>: the next free number this year among the existing Case Files."""
    y = (today or date.today()).year
    rx = re.compile(rf"^TB-{y}-(\d{{4}})$")
    n = max([int(m.group(1)) for c in store.list_cases() for m in [rx.match(c["case_id"])] if m], default=0) + 1
    return f"TB-{y}-{n:04d}"


async def process(doc_id, progress=None):
    """Read, classify and identify one intake document, then decide. Auto-linked documents are filed and extracted; the rest wait
    in the queue. Never raises: the record ends in a terminal state (needs_matching, filed, duplicate or error)."""
    doc = store.get_intake(doc_id)
    au = store.intake_auditor(doc_id)
    path = store.intake_original_path(doc_id)
    try:
        doc["state"] = "reading"; doc.pop("error", None); store.save_intake(doc); progress and progress(doc_id, "reading")
        pages = await ingest.extract_pages(path, audit=au)
        doc["pages"] = pages
        texts = [p["text"] for p in pages]
        full = _doc_text(pages)
        if not full.strip() or all(not t.strip() for t in texts):
            doc.update(state="error", error="no readable text"); store.save_intake(doc); progress and progress(doc_id, "error"); return doc
        doc["state"] = "classifying"; store.save_intake(doc); progress and progress(doc_id, "classifying")
        c = await extract.classify(full, au)
        doc["classification"] = extract.finish_classification(c, full, texts, doc["filename"])
        doc["state"] = "identifying"; store.save_intake(doc); progress and progress(doc_id, "identifying")
        doc["identity_read"] = read_identity(doc)
        doc["match"] = decide(doc)
        doc["state"] = "needs_matching"; store.save_intake(doc)
        au({"kind": "matching_decision", **{k: doc["match"][k] for k in ("decision", "case_id", "reason")}, "candidates": [x.get("case_id") for x in doc["match"]["candidates"]]})
        d = doc["match"]["decision"]
        if d == "auto_link":
            await file_and_extract(doc_id, doc["match"]["case_id"], MATCH_USER, "auto", doc["match"]["reason"], progress)
        elif d == "new_case":
            await file_and_extract(doc_id, None, MATCH_USER, "new_case", doc["match"]["reason"], progress)
        else:
            progress and progress(doc_id, "needs_matching")
        return store.get_intake(doc_id) or doc
    except Exception as e:
        doc.update(state="error", error=f"{e.__class__.__name__}: {str(e)[:300]}"); store.save_intake(doc)
        au({"kind": "error", "error": doc["error"]}); progress and progress(doc_id, "error")
        return doc


def file_to_case(doc_id, case_id, by, how="confirmed", reason="", patient=None):
    """Move an intake document into a Case File (case_id None: start a new, unlisted Case File from the document's identity).
    An identical file already in that Case File is marked duplicate and stays in the queue. Audited in both places. Returns the
    document record (state queued inside the Case File, or duplicate)."""
    doc = store.get_intake(doc_id)
    if not doc:
        raise KeyError(doc_id)
    if case_id is None:
        case_id = next_case_id()
        pat = patient or patient_from_identity(doc)
        store.create_case(case_id, pat, "", created_by=by)
        store.audit(case_id, {"kind": "case_created", "by": by, "from_intake": doc_id, "listing": "awaiting_listing"})
        store.audit_intake({"kind": "case_created", "doc_id": doc_id, "case_id": case_id, "by": by})
    elif not store.get_case(case_id):
        raise KeyError(case_id)
    dup = next((d for d in store.list_docs(case_id) if d.get("sha256") == doc.get("sha256")), None)
    if dup:
        doc.update(state="duplicate", filed={"case_id": case_id, "same_as": dup["doc_id"], "by": by, "at": store.now_iso(), "how": how})
        store.save_intake(doc)
        store.audit_intake({"kind": "duplicate", "doc_id": doc_id, "case_id": case_id, "same_as": dup["doc_id"], "by": by})
        store.audit(case_id, {"kind": "document_duplicate_skipped", "file": doc["rel_path"], "same_as": dup["doc_id"], "by": by, "from_intake": doc_id})
        return doc
    moved = store.move_intake_to_case(doc_id, case_id)
    moved.update(state="queued", filed={"case_id": case_id, "by": by, "at": store.now_iso(), "how": how, "reason": reason})
    moved.pop("error", None)
    store.save_doc(case_id, moved)
    store.audit(case_id, {"kind": "document_filed_from_intake", "doc_id": doc_id, "file": moved["rel_path"], "department": moved.get("department"),
                          "uploaded_by": moved.get("uploaded_by"), "how": how, "reason": reason, "by": by,
                          "identity": (moved.get("identity_read") or {}).get("name", {}) and (moved["identity_read"]["name"] or {}).get("value")})
    store.audit_intake({"kind": "filed", "doc_id": doc_id, "case_id": case_id, "how": how, "by": by, "reason": reason})
    if how == "confirmed" and by != MATCH_USER:
        try:
            confirm.record(case_id, "confirm_match", doc_id, {"case_id": case_id}, reason, by)
        except ValueError:
            pass
    return moved


async def file_and_extract(doc_id, case_id, by, how, reason="", progress=None, patient=None):
    """file_to_case, then extract the document's fields under the Case File's protocol from its stored pages and re-check the gate."""
    moved = file_to_case(doc_id, case_id, by, how, reason, patient)
    if moved.get("state") == "duplicate":
        progress and progress(doc_id, "duplicate")
        return moved
    cid = moved["filed"]["case_id"]
    case = store.get_case(cid)
    out = await extract.process_document(cid, doc_id, case.get("protocol"), case.get("patient"), progress, from_stored=True)
    async with store.lock(cid):
        gate = rules.evaluate(cid)
        if gate:
            rules.sync_actions(cid, gate)
    return out


def not_this_patient(doc_id, case_id, by, reason=""):
    """Record that an intake document is not this Case File's patient (confirm_match with an empty case id in that Case File), so the
    candidate is not suggested again."""
    doc = store.get_intake(doc_id)
    if not doc or not store.get_case(case_id):
        raise KeyError(doc_id)
    rec = confirm.record(case_id, "confirm_match", doc_id, {"case_id": ""}, reason, by)
    doc.setdefault("rejected_cases", [])
    if case_id not in doc["rejected_cases"]:
        doc["rejected_cases"].append(case_id)
    doc["match"] = {**(doc.get("match") or {}), "candidates": [c for c in (doc.get("match") or {}).get("candidates", []) if c.get("case_id") != case_id]}
    if (doc.get("match") or {}).get("case_id") == case_id:
        doc["match"]["decision"], doc["match"]["case_id"] = "needs_matching", None
    store.save_intake(doc)
    store.audit_intake({"kind": "not_this_patient", "doc_id": doc_id, "case_id": case_id, "by": by, "reason": reason, "confirmation": rec["id"]})
    return doc


def discard(doc_id, by, reason=""):
    doc = store.get_intake(doc_id)
    if not doc:
        raise KeyError(doc_id)
    store.delete_intake(doc_id)
    store.audit_intake({"kind": "discarded", "doc_id": doc_id, "file": doc.get("rel_path"), "department": doc.get("department"), "by": by, "reason": reason})
    return doc


def queue(roles):
    """Intake documents this user may see: coordinators and admins all of them, department members those of their departments."""
    docs = store.list_intake()
    if not (roles.get("admin") or roles.get("coordinator")):
        mine = set(org.visible_departments_for_inbox(roles))
        docs = [d for d in docs if d.get("department") in mine]
    out = []
    for d in docs:
        out.append({k: d.get(k) for k in ("doc_id", "filename", "rel_path", "ext", "size", "added", "state", "error", "department", "uploaded_by",
                                          "classification", "identity_read", "match", "filed", "rejected_cases")} | {"pages": len(d.get("pages") or [])})
    return out
