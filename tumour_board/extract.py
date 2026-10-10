"""Document understanding: classification, FINAL / SIGNED status, primary-field extraction with verbatim quotes,
then deterministic grounding. Nothing the model says is trusted until its quote is found in the source text."""
import asyncio, re

from . import docstatus, grounding, identity, ingest, llm, negation, protocol, store

STATUS = ["FINAL", "AMENDED", "CORRECTED", "PRELIMINARY", "DRAFT", "CANCELLED", "UNKNOWN"]
# Negation cues shared with qa and postboard (see negation.py).
NEGATED_RE = re.compile(r"\b(" + negation.NO + "|not|negative|absent|without|free of|" + negation.NON + r"|not seen|not identified|not detected|no evidence)\b", re.I)
PENDING_RE = re.compile(r"\b(pending|awaited|not reported|not available|not performed|not done|to follow|sent to|in process|requested|will follow)\b", re.I)

SYS = ("You read clinical documents for a Tumour Board Case File. You copy information exactly as written. "
       "You never interpret, infer, calculate, diagnose, assign stage or recommend anything. "
       "If something is not written in the document, you say it is not found.")


def _doc_text(pages):
    return "\n\n".join(f"[page {i + 1}]\n{p['text']}" for i, p in enumerate(pages))


CLASSIFY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "description": "document title as written"}, "department": {"type": "string"},
        "doc_type": {"type": "string", "enum": None},
        "body_region": {"type": "string", "description": "anatomical region of the study or specimen, empty if not applicable"},
        "report_date": {"type": "string", "description": "report / study / sample date as written"},
        "status_quote": {"type": "string", "description": "exact text stating the report status, empty if none"},
        "signature_quote": {"type": "string", "description": "exact signature / sign-out line, empty if none"},
        "signer": {"type": "string"},
        "patient_name": {"type": "string"}, "patient_id": {"type": "string"},
    },
    "required": ["title", "department", "doc_type", "body_region", "report_date", "status_quote", "signature_quote", "signer", "patient_name", "patient_id"],
}


def parse_date(s):  # compatibility wrapper
    return docstatus.parse_date(s)


async def classify(text, audit=None):
    schema = {**CLASSIFY_SCHEMA, "properties": {**CLASSIFY_SCHEMA["properties"], "doc_type": {"type": "string", "enum": protocol.doc_types()}}}
    msg = [{"role": "system", "content": SYS},
           {"role": "user", "content": "Classify this clinical document and copy its header details exactly as written.\n"
            "doc_type guide (decide from the title and department):\n"
            "- clinical_note: OPD / clinic / consultation / follow-up / progress note by a clinician\n- referral: referral letter\n"
            "- discharge_summary: discharge summary of an admission\n"
            "- ct / mri / xray / ultrasound / mammogram / pet_ct / bone_scan: imaging reports of that modality\n"
            "- histopathology: biopsy or resection pathology report\n- cytology: FNAC or fluid cytology\n"
            "- ihc: stand-alone immunohistochemistry / receptor report or its addendum\n- molecular: mutation / NGS / PCR / FISH report\n"
            "- lab: blood tests, biochemistry, tumour markers\n- endoscopy: colonoscopy / bronchoscopy / endoscopy procedure report\n"
            "- operative_note: surgery note\n- treatment_summary: a summary of a COMPLETED chemotherapy / radiotherapy course\n"
            "- tumour_board_record: minutes or decision record of a previous Tumour Board\n- pulmonary_function: PFT report\n- other: anything else\n\n"
            "DOCUMENT:\n" + text[:12000]}]
    return await llm.chat("extractor", msg, json_schema=schema, max_tokens=600, purpose="classify document", audit=audit)


def _facts_schema(fact_ids):
    item = {"type": "object", "additionalProperties": False,
            "properties": {"found": {"type": "boolean"}, "value": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["found", "value", "quote"]}
    return {"type": "object", "additionalProperties": False, "properties": {f: item for f in fact_ids}, "required": list(fact_ids)}


async def extract_facts(text, fact_ids, audit=None):
    if not fact_ids:
        return {}
    cat = protocol.facts()
    spec = "\n".join(f"- {f}: {cat[f]['label']} ({cat[f]['desc']})" for f in fact_ids)
    msg = [{"role": "system", "content": SYS},
           {"role": "user", "content": "Find these fields in the document.\n" + spec + "\n\nRules:\n"
            "1. value: copy the value exactly as written in the document (keep units, wording such as 'Pending' or 'Not reported').\n"
            "2. quote: copy the shortest complete line or phrase from the document that contains the value, character for character.\n"
            "3. If the field is not written in this document, set found=false and leave value and quote empty. Do not guess, infer or calculate.\n\n"
            "DOCUMENT:\n" + text[:14000]}]
    return await llm.chat("extractor", msg, json_schema=_facts_schema(fact_ids), max_tokens=1800, purpose="extract fields", audit=audit)


def finish_classification(c, full, texts, filename):
    """Rules over the model's header reading: status and signature from docstatus, the model's quotes kept only when found in the
    text, the report date from the model then the filename then the first date in the text (item 3.1 replaces this), the patient id
    kept only when found verbatim. Shared by Case File processing and intake (V1 item 2.3)."""
    status, squote, notes = docstatus.detect_status(full)
    signed, sline = docstatus.detect_signature(full)
    if status == "UNSTATED" and c.get("status_quote") and grounding.locate(c["status_quote"], texts):
        st2, _, _ = docstatus.detect_status(c["status_quote"])  # the model found a status line the rules missed
        if st2 != "UNSTATED":
            status, squote = st2, c["status_quote"]
    c["status"], c["status_quote"], c["signed"], c["status_notes"] = status, squote, signed, notes
    c["signature_quote"] = sline or (c.get("signature_quote") if c.get("signature_quote") and grounding.locate(c["signature_quote"], texts) else "")
    c["report_date_iso"] = docstatus.parse_date(c.get("report_date")) or docstatus.parse_date(filename.replace("_", " ")) \
        or (docstatus.find_dates(full) or [""])[0]
    if c.get("patient_id") and not grounding.locate(c["patient_id"], texts):
        c["patient_id_unverified"] = c["patient_id"]; c["patient_id"] = ""
    return c


def mask_pages(pages):
    """Aadhaar numbers are masked in the page text before anything is stored, shown or sent to a model (V1 item 2.4): never used,
    never kept. The page records how many were masked."""
    for p in pages:
        t, n = identity.mask_aadhaar(p.get("text") or "")
        if n:
            p["text"] = t; p["aadhaar_masked"] = n
    return pages


def identity_check(full, case_patient, idr=None):
    """Does the document belong to this Case File's patient? match: an identifier printed on the document equals one the Case File
    knows (or the UHID / MRN is found in the text); name_match: the printed name is compatible with the patient's (exact, a
    transliteration variant or initials) but no identifier agrees; mismatch_or_missing: an identifier agrees but the name, age or
    sex differs (possible wrong patient), or nothing agrees. None when the Case File has no patient."""
    if not (case_patient and (case_patient.get("mrn") or case_patient.get("name"))):
        return None
    if idr is not None:
        m = identity.match(idr, [{"case_id": "this", "patient": case_patient}])
        if m["decision"] == "auto_link":
            return "match"
        if m["decision"] == "id_conflict":
            return "mismatch_or_missing"
        if any(c.get("name_match") in ("exact", "variant", "initials") and not c.get("sex_fit") is False for c in m.get("candidates", [])):
            return "name_match"
    nf = grounding.norm(full)
    mrn = grounding.norm(case_patient.get("mrn") or "")
    toks = [t for t in re.findall(r"[a-z]{3,}", grounding.norm(case_patient.get("name") or "")) if t not in ("synthetic", "mr", "mrs", "ms", "dr")]
    if mrn and mrn in nf:
        return "match"
    if toks and sum(1 for t in toks if t in nf) >= min(2, len(toks)):
        return "name_match"
    return "mismatch_or_missing"


async def process_document(case_id, doc_id, protocol_id, case_patient=None, progress=None, from_stored=False):
    """Full pipeline for one document. Writes results into the doc record. Safe to re-run.

    from_stored=True (a document filed from the intake area, or re-extracted after a clinician confirmation): the stored pages and
    classification are reused, nothing is re-read or re-classified; only the identity check and the field extraction run.
    protocol_id empty (a Case File not yet listed, V1 item 2.5): no fields are extracted; the document is read and classified only."""
    au = store.auditor(case_id)
    doc = store.get_doc(case_id, doc_id)
    path = store.original_path(case_id, doc_id)
    try:
        if from_stored and doc.get("pages") and doc.get("classification"):
            pages = doc["pages"]
        else:
            doc["state"] = "reading"; doc.pop("error", None); store.save_doc(case_id, doc); progress and progress(doc_id, "reading")
            pages = mask_pages(await ingest.extract_pages(path, audit=au))  # Aadhaar masked before anything is stored (V1 item 2.4)
            doc["pages"] = pages
            doc.pop("classification", None)
        texts = [p["text"] for p in pages]
        full = _doc_text(pages)
        if not full.strip() or all(not t.strip() for t in texts):
            doc.update(state="error", error="no readable text"); store.save_doc(case_id, doc); progress and progress(doc_id, "error"); return doc
        if not doc.get("classification"):
            doc["state"] = "classifying"; store.save_doc(case_id, doc); progress and progress(doc_id, "classifying")
            c = await classify(full, au)
            doc["classification"] = finish_classification(c, full, texts, doc["filename"])
        c = doc["classification"]
        # identity as printed (rules first; V1 item 2.4) and the check that the document belongs to this Case File's patient
        if not doc.get("identity_read"):
            from . import intake  # the same reader as the intake area (model fallback quote checked)
            doc["identity_read"] = intake.read_identity(doc, identity.patient_record(case_patient or {})["ids"])
        ident = identity_check(full, case_patient, doc["identity_read"])
        if ident:
            doc["identity"] = ident
            if ident == "match":  # an exact identifier: the Case File learns the record's other identifiers (CR No., ABHA, IP No.)
                from . import intake
                intake.learn_ids(case_id, doc["identity_read"], "system:identity", doc_id)
        if not protocol_id:  # not listed yet: no protocol, so nothing to extract (V1 item 2.5)
            doc["facts"] = {}
            doc["state"] = "ready"; doc["processed"] = store.now_iso()
            store.save_doc(case_id, doc); progress and progress(doc_id, "ready")
            return doc
        doc["state"] = "extracting"; store.save_doc(case_id, doc); progress and progress(doc_id, "extracting")
        fids = protocol.facts_for_doc(protocol_id, c["doc_type"])
        raw = await extract_facts(full, fids, au)
        facts = {}
        for fid in fids:
            r = raw.get(fid) or {}
            if not r.get("found") or not (r.get("value") or "").strip():
                continue
            v = grounding.verify(r["value"], r.get("quote") or r["value"], texts)
            if v["status"] == "unverified" and r.get("quote") != r["value"]:  # the value itself may be the verbatim evidence
                v2 = grounding.verify(r["value"], r["value"], texts)
                if v2["status"] != "unverified":
                    v = v2
            pending = bool(PENDING_RE.search(r["value"]))
            # numbers the two OCR reads disagreed on make the value uncertain (expert must read the scan)
            if v["status"] == "verified" and v["location"] is not None:
                unc = set((pages[v["location"]["page"]].get("ocr_uncertain_numbers") or []))
                if unc & set(x.replace(",", "") for x in re.findall(r"\d+(?:[.,]\d+)*", r["value"])):
                    v = {**v, "status": "needs_review", "reason": "the two OCR reads of this page disagree on a number in this value"}
            facts[fid] = {"value": r["value"].strip(), "quote": (v["location"] or {}).get("matched") or r.get("quote", ""),
                          "model_quote": r.get("quote", ""), "verification": v["status"], "reason": v.get("reason"),
                          "location": v["location"], "state": "pending" if pending else "present",
                          "polarity": "negated" if NEGATED_RE.search(r["value"]) else "affirmed"}
            au({"kind": "fact_verification", "doc_id": doc_id, "fact": fid, "value": r["value"], "result": v["status"], "reason": v.get("reason")})
        doc["facts"] = facts
        doc["state"] = "ready"; doc["processed"] = store.now_iso()
        store.save_doc(case_id, doc); progress and progress(doc_id, "ready")
        return doc
    except Exception as e:
        doc.update(state="error", error=f"{e.__class__.__name__}: {str(e)[:300]}"); store.save_doc(case_id, doc)
        au({"kind": "error", "doc_id": doc_id, "error": doc["error"]}); progress and progress(doc_id, "error")
        return doc
