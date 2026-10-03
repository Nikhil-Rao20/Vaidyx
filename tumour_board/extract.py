"""Document understanding: classification, FINAL / SIGNED status, primary-field extraction with verbatim quotes,
then deterministic grounding. Nothing the model says is trusted until its quote is found in the source text."""
import asyncio, re
from datetime import datetime

from . import grounding, ingest, llm, protocol, store

STATUS = ["FINAL", "AMENDED", "CORRECTED", "PRELIMINARY", "DRAFT", "CANCELLED", "UNKNOWN"]
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


def _status_from_text(text):
    """Deterministic status / signature detection from the document text itself."""
    m = re.search(r"(?:report|record|document)\s+status\s*[:\-]\s*([A-Za-z ()/-]{3,40})", text, re.I)
    status, squote = "UNKNOWN", ""
    if m:
        squote = m.group(0).strip()
        v = m.group(1).upper()
        for s in ["CORRECTED", "AMENDED", "PRELIMINARY", "DRAFT", "CANCELLED", "FINAL"]:
            if s in v:
                status = s; break
        if status == "FINAL" and "AMEND" in v:
            status = "AMENDED"
    elif re.search(r"\bdraft\b", text, re.I):
        status, squote = "DRAFT", re.search(r".{0,30}\bdraft\b.{0,30}", text, re.I).group(0).strip()
    signed = "unknown"
    if re.search(r"signature\s+pending|unsigned|not\s+signed|awaiting\s+signature", text, re.I):
        signed = "no"
    elif re.search(r"electronically signed|digitally signed|\bsigned\s*(by|:|on)\b|\(signed\)", text, re.I):
        signed = "yes"
    return status, squote, signed


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%b %d, %Y", "%d %B %Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s[:20].strip(), fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})[-/ ](\w{3})[-/ ](\d{4})|(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return parse_date(m.group(0))
    return ""


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


async def process_document(case_id, doc_id, protocol_id, case_patient=None, progress=None):
    """Full pipeline for one document. Writes results into the doc record. Safe to re-run."""
    au = store.auditor(case_id)
    doc = store.get_doc(case_id, doc_id)
    path = store.original_path(case_id, doc_id)
    try:
        doc["state"] = "reading"; store.save_doc(case_id, doc); progress and progress(doc_id, "reading")
        pages = await ingest.extract_pages(path, audit=au)
        doc["pages"] = pages
        texts = [p["text"] for p in pages]
        full = _doc_text(pages)
        if not full.strip() or all(not t.strip() for t in texts):
            doc.update(state="error", error="no readable text"); store.save_doc(case_id, doc); return doc
        doc["state"] = "classifying"; store.save_doc(case_id, doc); progress and progress(doc_id, "classifying")
        c = await classify(full, au)
        status, squote, signed = _status_from_text(full)
        if status == "UNKNOWN" and c.get("status_quote"):
            status = _status_from_text(c["status_quote"])[0]
            squote = c["status_quote"] if grounding.locate(c["status_quote"], texts) else ""
        c["status"], c["status_quote"], c["signed"] = status, squote, signed
        m = re.search(r"^.*\b(reported|signed|verified|checked|authori[sz]ed|recorded)\s+(and verified\s+)?by\b.*$", full, re.I | re.M)
        if m:  # the signature line as written (more reliable than the model's choice)
            c["signature_quote"] = m.group(0).strip()
        c["report_date_iso"] = parse_date(c.get("report_date")) or parse_date(doc["filename"].replace("_", " "))
        for k in ("signature_quote", "patient_id"):  # header values are kept only if they are really in the text
            if c.get(k) and not grounding.locate(c[k], texts):
                c[k + "_unverified"] = c[k]; c[k] = ""
        doc["classification"] = c
        # identity check: the document should belong to this Case File's patient
        if case_patient and case_patient.get("mrn"):
            mrn = grounding.norm(case_patient["mrn"])
            doc["identity"] = "match" if mrn and mrn in grounding.norm(full) else "mismatch_or_missing"
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
            facts[fid] = {"value": r["value"].strip(), "quote": (v["location"] or {}).get("matched") or r.get("quote", ""),
                          "model_quote": r.get("quote", ""), "verification": v["status"], "reason": v.get("reason"),
                          "location": v["location"], "state": "pending" if pending else "present"}
            au({"kind": "fact_verification", "doc_id": doc_id, "fact": fid, "value": r["value"], "result": v["status"], "reason": v.get("reason")})
        doc["facts"] = facts
        doc["state"] = "ready"; doc["processed"] = store.now_iso()
        store.save_doc(case_id, doc); progress and progress(doc_id, "ready")
        return doc
    except Exception as e:
        doc.update(state="error", error=f"{e.__class__.__name__}: {str(e)[:300]}"); store.save_doc(case_id, doc)
        au({"kind": "error", "doc_id": doc_id, "error": doc["error"]}); progress and progress(doc_id, "error")
        return doc
