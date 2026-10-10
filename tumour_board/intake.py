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

from . import config, confirm, extract, grounding, identity, ingest, org, rules, store

MATCH_USER = "system:matching"
MODEL_LABEL = "Qwen3.5-4B reader (Chinese, non-medical), quote checked"  # a value read by the model, not by the rules
ACTIONABLE = ("needs_matching", "duplicate", "error")  # states in which a person may file, discard or re-read an intake record
LEARN_KINDS = ("uhid", "mrn", "cr_no", "ip_no", "op_no", "hospital_no", "abha")  # identifiers a Case File learns from its matched records
QUEUE_STATES = ("queued", "reading", "classifying", "identifying", "needs_matching", "duplicate", "error")


def _doc_text(pages):
    return extract._doc_text(pages)


def read_identity(doc, known_ids=None):
    """Patient identity as printed in the document: rules first (identity.read_identity: UHID / MRN / CR No. / IP / OP No. / ABHA,
    name, age / sex, DOB, S/o W/o D/o; every value quote-checked), the reader model only as a quote-checked fallback when the rules
    read no name or no identifier. A model identifier is used for matching only when it equals an identifier a Case File already
    has (it carries no label, so it could be a sample number); otherwise it is shown as a note for the person. Aadhaar is never read."""
    pages = doc.get("pages") or []
    texts = [p.get("text", "") for p in pages]
    idr = identity.read_identity(texts, doc.get("filename", ""))
    c = doc.get("classification") or {}
    idr["model_read"] = []
    if idr.get("name") is None and c.get("patient_name"):
        loc = grounding.locate(c["patient_name"], texts)
        if loc and loc["score"] >= 100:  # the located text itself, exact only: a fuzzy match could let a normalised spelling through
            idr["name"] = {"value": loc["matched"].strip(), "quote": loc["matched"], "page": loc["page"], "label": MODEL_LABEL}
            idr["model_read"].append("name")
            idr["notes"].append("patient name read by the Qwen3.5-4B reader (Chinese, non-medical); the rules found none; quote checked")
    if not idr.get("ids") and c.get("patient_id"):
        loc = grounding.locate(c["patient_id"], texts)
        nv = identity.normalise_id(c["patient_id"])
        if loc and nv:
            known = {v for kind, v in (known_ids or set()) if kind in identity.HOSPITAL_ID_KINDS}
            if nv in known:
                idr["ids"].append({"kind": "uhid", "value": loc["matched"].strip(), "quote": loc["matched"], "page": loc["page"], "label": MODEL_LABEL + ", equals a known UHID / MRN"})
                idr["model_read"].append("id")
            idr["notes"].append(f"identifier read by the Qwen3.5-4B reader without a label: {c['patient_id']}" + ("" if nv in known else " (not used for matching: no label, matches no Case File)"))
    return idr


def patients_for_matching(exclude=()):
    """Every Case File's registered patient, for the matcher."""
    return [{"case_id": c["case_id"], "patient": c.get("patient") or {}, "listed": (c.get("listing") or {}).get("status") != "awaiting_listing"}
            for c in store.list_cases() if c["case_id"] not in exclude and c["case_id"] not in config.PROTECTED_CASES]


def known_ids(patients=None):
    out = set()
    for p in patients if patients is not None else patients_for_matching():
        out |= identity.patient_record(p.get("patient") or {})["ids"]
    return out


def decide(doc, patients=None):
    """The matching decision for an intake document (plan 2.4 evidence table, identity.match): auto-link on an exact identifier with a
    compatible name, suggest on name + age / sex fitting exactly one patient (a person confirms), new Case File on an unknown
    hospital identifier, needs matching for everything else. Two safeguards on top of the matcher: a Case File a person already
    marked "not this patient" is never linked or suggested again, and a Hospital No. / Reg. No. from another hospital's header never
    opens a Case File when the hospital name is configured."""
    patients = patients_for_matching() if patients is None else patients
    idr = doc.get("identity_read") or {}
    m = identity.match(idr, patients)
    rejected = set(doc.get("rejected_cases") or [])
    if m["decision"] == "auto_link" and {"name", "id"} <= set(idr.get("model_read") or []):  # both the name and the identifier came from the model: a person confirms
        m = {**m, "decision": "suggest", "reason": m["reason"] + ". Both the name and the identifier were read by the reader model, not by the rules: suggested, a person confirms"}
    if m["decision"] in ("auto_link", "suggest") and m["case_id"] in rejected:
        m = {**m, "decision": "needs_matching", "case_id": None,
             "reason": f"{m['reason']}. A person already recorded that this record is not {m['case_id']}: a person must decide"}
    hosp = (org.load().get("hospital") or {}).get("name", "").strip().lower()
    if m["decision"] == "new_case" and (m.get("matched_on") or {}).get("kind") in ("hospital_no", "reg_no") and hosp and hosp not in (idr.get("hospital_header") or "").lower():
        m = {**m, "decision": "needs_matching", "case_id": None,
             "reason": f"{m['reason']}; the header names another hospital ({idr.get('hospital_header', '')}), so the number may not be this hospital's: a person must decide"}
    return m


def learn_ids(case_id, idr, by, doc_id=None):
    """A Case File learns the other identifiers printed on a record that matched it exactly (or that a person filed into it):
    UHID / MRN / CR No. / IP / OP No. / ABHA are added to case.patient.ids when new, audited, so a later record carrying only the
    CR No. still auto-links. Never Aadhaar, never from a name-only match."""
    case = store.get_case(case_id)
    if not case or case_id in config.PROTECTED_CASES:
        return []
    pat = case.setdefault("patient", {})
    have = identity.patient_record(pat)["ids"]
    new = []
    for it in (idr or {}).get("ids") or []:
        kind, val = it.get("kind"), it.get("value")
        if kind in LEARN_KINDS and val and (kind, identity.normalise_id(val)) not in have and not any(x.get("kind") == kind and identity.normalise_id(x.get("value")) == identity.normalise_id(val) for x in new):
            new.append({"kind": kind, "value": val, "from_doc": doc_id})
    if (idr or {}).get("abha") and ("abha", idr["abha"]) not in have and not any(x["kind"] == "abha" for x in new):
        new.append({"kind": "abha", "value": idr["abha"], "from_doc": doc_id})
    if not new:
        return []
    pat.setdefault("ids", []).extend(new)
    if not pat.get("mrn"):
        pat["mrn"] = next((x["value"] for x in new if x["kind"] in ("uhid", "mrn", "hospital_no")), pat.get("mrn", ""))
    if not pat.get("agesex") and idr.get("age") is not None and idr.get("sex"):
        pat["agesex"] = f"{idr['age']} Y / {idr['sex']}"
    store.save_case(case)
    store.audit(case_id, {"kind": "patient_ids_learned", "ids": new, "doc_id": doc_id, "by": by})
    return new


def unlearn_ids(case_id, doc_id, by):
    """Forget the identifiers a Case File learned from one record (when the record is unfiled or removed), audited."""
    case = store.get_case(case_id)
    if not case:
        return []
    ids = (case.get("patient") or {}).get("ids") or []
    gone = [x for x in ids if x.get("from_doc") == doc_id]
    if not gone:
        return []
    case["patient"]["ids"] = [x for x in ids if x.get("from_doc") != doc_id]
    store.save_case(case)
    store.audit(case_id, {"kind": "patient_ids_unlearned", "ids": gone, "doc_id": doc_id, "by": by})
    return gone


def _alive(doc_id):
    """False once a person has filed or discarded the record while it was being read: nothing more may be written for it."""
    return (store.intake_doc_dir(doc_id) / "doc.json").exists()


def unfile(case_id, doc_id, by, reason=""):
    """Reverse a link: move a document that came from the intake area back to the Needs matching queue. The Case File forgets the
    identifiers learned from it, is marked "not this patient" for the record, and its open confirm_match is undone. Audited both sides."""
    doc = store.get_doc(case_id, doc_id)
    if not doc:
        raise KeyError(doc_id)
    if not doc.get("intake"):
        raise ValueError("This document was uploaded straight into the Case File; remove it instead")
    unlearn_ids(case_id, doc_id, by)
    for c in confirm.active(case_id, "confirm_match", doc_id):
        confirm.undo(case_id, c["id"], by)
    moved = store.move_case_doc_to_intake(case_id, doc_id)
    moved.pop("facts", None); moved.pop("identity", None); moved.pop("processed", None); moved.pop("extracted_under", None)
    prev = moved.pop("filed", None)
    moved["unfiled"] = {"case_id": case_id, "by": by, "at": store.now_iso(), "reason": reason, "was": prev}
    moved.setdefault("rejected_cases", [])
    if case_id not in moved["rejected_cases"]:
        moved["rejected_cases"].append(case_id)
    moved["match"] = {"decision": "needs_matching", "case_id": None, "candidates": [c for c in (moved.get("match") or {}).get("candidates", []) if c.get("case_id") != case_id],
                      "reason": f"Moved back from {case_id} by {by}" + (f": {reason}" if reason else "") + ". A person decides where it belongs", "matched_on": None}
    moved["state"] = "needs_matching"
    store.save_intake(moved)
    store.audit(case_id, {"kind": "document_unfiled", "doc_id": doc_id, "file": moved.get("rel_path"), "by": by, "reason": reason})
    store.audit_intake({"kind": "unfiled", "doc_id": doc_id, "case_id": case_id, "by": by, "reason": reason})
    return moved


def clear_rejection(doc_id, case_id):
    """Undo of a "not this patient": the Case File may be suggested again for the record (if it is still in the queue)."""
    doc = store.get_intake(doc_id)
    if not doc:
        return None
    doc["rejected_cases"] = [c for c in doc.get("rejected_cases") or [] if c != case_id]
    store.save_intake(doc)
    return doc


_TITLE_RX = re.compile(r"^(?:(?:" + "|".join(identity.TITLES) + r")\.?\s+)+", re.I)
_REL_CUT = re.compile(r"\s+(?:[SWDC]\s*/\s*O\b.*|(?:son|wife|daughter|care)\s+of\b.*)$", re.I)


def registered_name(printed):
    """The name as the Case File registers it: titles (Shri, Smt, Mr, Dr...) and the relation part (S/o ...) removed, casing kept."""
    return _REL_CUT.sub("", _TITLE_RX.sub("", (printed or "").strip())).strip(" ,")


def patient_from_identity(doc):
    """A Case File patient record built from what the document prints (used when a new Case File is started from the queue)."""
    idn = doc.get("identity_read") or {}
    ids = idn.get("ids") or []
    primary = next((i for i in ids if i["kind"] in ("uhid", "mrn", "hospital_no", "reg_no")), ids[0] if ids else None)
    agesex = ""
    if idn.get("age") is not None and idn.get("sex"):
        agesex = f"{idn['age']} Y / {idn['sex']}"
    return {"name": registered_name((idn.get("name") or {}).get("value", "")), "mrn": primary["value"] if primary else "", "agesex": agesex,
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
        pages = extract.mask_pages(await ingest.extract_pages(path, audit=au))  # Aadhaar masked before anything is stored or prompted
        if not _alive(doc_id):
            return doc
        doc["pages"] = pages
        texts = [p["text"] for p in pages]
        full = _doc_text(pages)
        if not full.strip() or all(not t.strip() for t in texts):
            doc.update(state="error", error="no readable text"); store.save_intake(doc); progress and progress(doc_id, "error"); return doc
        doc["state"] = "classifying"; store.save_intake(doc); progress and progress(doc_id, "classifying")
        c = await extract.classify(full, au)
        if not _alive(doc_id):
            return doc
        doc["classification"] = extract.finish_classification(c, full, texts, doc["filename"], "", doc.get("pages"))
        doc["state"] = "identifying"; store.save_intake(doc); progress and progress(doc_id, "identifying")
        patients = patients_for_matching()
        doc["identity_read"] = read_identity(doc, known_ids(patients))
        doc["match"] = decide(doc, patients)
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
        doc.update(state="error", error=f"{e.__class__.__name__}: {str(e)[:300]}")
        if _alive(doc_id):
            store.save_intake(doc)
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
    if how in ("confirmed", "auto", "new_case"):  # a person's decision, or the matcher's: both are recorded in the Case File and can be undone (unfile)
        try:
            confirm.record(case_id, "confirm_match", doc_id, {"case_id": case_id}, reason, by)
        except ValueError:
            pass
    if how in ("auto", "confirmed", "new_case"):  # an exact match or a person's decision: the Case File learns the record's other identifiers
        learn_ids(case_id, moved.get("identity_read"), by, doc_id)
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
