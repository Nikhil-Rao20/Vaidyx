"""Document understanding: classification, FINAL / SIGNED status, primary-field extraction with verbatim quotes,
then deterministic grounding. Nothing the model says is trusted until its quote is found in the source text."""
import asyncio, re

from . import dates, docstatus, grounding, identity, ingest, llm, negation, protocol, store

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


WINDOW = 12000  # characters per extraction window; longer documents are read in windows along page boundaries (V1 item 3.4)


def _page_spans(text):
    """(page number, start, end) of each '[page N]' block of a _doc_text() text; a text without page markers is one block (page None)."""
    if not text.startswith("[page 1]\n"):
        return [(None, 0, len(text))]
    starts, k = [0], 2
    while (j := text.find(f"\n\n[page {k}]\n", starts[-1])) >= 0:
        starts.append(j + 2); k += 1
    return [(i + 1, st, starts[i + 1] - 2 if i + 1 < len(starts) else len(text)) for i, st in enumerate(starts)]


def _line_chunks(text, start, end, limit):
    """[start, end) cut into pieces of at most `limit` characters at line boundaries (mid-line only for a line longer than `limit`)."""
    out = []
    while end - start > limit:
        cut = text.rfind("\n", start, start + limit)
        if cut <= start:
            out.append((start, start + limit)); start += limit
        else:
            out.append((start, cut)); start = cut + 1
    out.append((start, end))
    return out


def _windows(text, limit=WINDOW):
    """Windows of at most `limit` characters along page boundaries, one page of overlap between consecutive windows. A page longer
    than `limit` is cut at line boundaries into windows of its own. Returns [(start, end, label)]; one window when the text fits."""
    if len(text) <= limit:
        return [(0, len(text), "")]
    units = []  # (page, start, end, part, parts)
    for pg, st, en in _page_spans(text):
        pieces = _line_chunks(text, st, en, limit)
        units += [(pg, a, b, i + 1, len(pieces)) for i, (a, b) in enumerate(pieces)]
    npages = sum(1 for u in units if u[3] == 1)
    out, i = [], 0
    while i < len(units):
        j = i
        while j + 1 < len(units) and units[j + 1][2] - units[i][1] <= limit:
            j += 1
        first, last = units[i], units[j]
        if first[0] is None:
            label = ""
        elif first[4] > 1:
            label = f"page {first[0]} (piece {first[3]} of {first[4]}) of {npages}"
        elif first[0] == last[0]:
            label = f"page {first[0]} of {npages}"
        else:
            label = f"pages {first[0]} to {last[0]} of {npages}"
        out.append((first[1], last[2], label))
        if j == len(units) - 1:
            break
        # the next window starts on this window's last page (overlap) unless that page alone would leave no room for the next one
        i = j if j > i and units[j + 1][2] - units[j][1] <= limit else j + 1
    return out


def _facts_prompt(spec, document, part=""):
    where = "this part of the document" if part else "this document"
    head = f"DOCUMENT, {part}; the other parts are read separately:\n" if part else "DOCUMENT:\n"
    return ("Find these fields in the document.\n" + spec + "\n\nRules:\n"
            "1. value: copy the value exactly as written in the document (keep units, wording such as 'Pending' or 'Not reported').\n"
            "2. quote: copy the shortest complete line or phrase from the document that contains the value, character for character.\n"
            f"3. If the field is not written in {where}, set found=false and leave value and quote empty. Do not guess, infer or calculate.\n\n"
            + head + document)


async def extract_facts(text, fact_ids, audit=None, pages=None):
    """Primary fields with verbatim quotes. A document that fits in one window (WINDOW characters) is read in one call, as before;
    a longer one is read in windows along page boundaries, in parallel (V1 item 3.4). Per field the first answer in document order
    is returned; other windows' answers with a different value are kept under "alternatives" ([{value, quote}]) for the caller
    to verify against the whole document. `pages` (the page records) may be given instead of the joined text."""
    if not fact_ids:
        return {}
    if pages is not None:
        text = _doc_text(pages)
    cat = protocol.facts()
    spec = "\n".join(f"- {f}: {cat[f]['label']} ({cat[f]['desc']})" for f in fact_ids)
    wins = _windows(text)
    if len(wins) == 1:
        msg = [{"role": "system", "content": SYS}, {"role": "user", "content": _facts_prompt(spec, text[:14000])}]
        return await llm.chat("extractor", msg, json_schema=_facts_schema(fact_ids), max_tokens=1800, purpose="extract fields", audit=audit)
    n = len(wins)

    def part(i, label):
        return f"part {i + 1} of {n}" + (f" ({label})" if label else "")
    results = await asyncio.gather(*[
        llm.chat("extractor", [{"role": "system", "content": SYS}, {"role": "user", "content": _facts_prompt(spec, text[a:b], part(i, label))}],
                 json_schema=_facts_schema(fact_ids), max_tokens=1800, purpose=f"extract fields (window {i + 1} of {n})", audit=audit)
        for i, (a, b, label) in enumerate(wins)])
    out = {}
    for fid in fact_ids:
        answers = [r[fid] for r in results if isinstance((r or {}).get(fid), dict) and r[fid].get("found") and (r[fid].get("value") or "").strip()]
        if not answers:
            out[fid] = {"found": False, "value": "", "quote": ""}
            continue
        first = answers[0]
        out[fid] = {"found": True, "value": first["value"], "quote": first.get("quote") or ""}
        seen, alts = {grounding.norm(first["value"])}, []
        for a in answers[1:]:
            k = grounding.norm(a["value"])
            if k not in seen:  # the same value read twice (the overlap page) is one value
                seen.add(k); alts.append({"value": a["value"], "quote": a.get("quote") or ""})
        if alts:
            out[fid]["alternatives"] = alts
    return out


def _verify_value(value, quote, texts, pages):
    """Grounding of one extracted value against the whole document: the quote, else the value itself as the verbatim evidence;
    a number the two OCR reads of its page disagreed on makes a verified value needs_review (the expert reads the scan)."""
    v = grounding.verify(value, quote or value, texts)
    if v["status"] == "unverified" and quote != value:  # the value itself may be the verbatim evidence
        v2 = grounding.verify(value, value, texts)
        if v2["status"] != "unverified":
            v = v2
    if v["status"] == "verified" and v["location"] is not None:
        loc = v["location"]; page = pages[loc["page"]] if loc["page"] < len(pages) else {}
        span = ingest.uncertain_overlap(page, loc["start"], loc["end"])  # the quote sits on a line the two OCR reads disagree on (V1 item 3.3)
        if span is not None:
            v = {**v, "status": "needs_review", "reason": "OCR check: " + span["reason"]}
        elif "ocr_uncertain_spans" not in page and page.get("ocr_uncertain_numbers"):  # a page read before the line check existed: the old per-page list
            unc = set(page["ocr_uncertain_numbers"])
            if unc & set(x.replace(",", "") for x in re.findall(r"\d+(?:[.,]\d+)*", value)):
                v = {**v, "status": "needs_review", "reason": "the two OCR reads of this page disagree on a number in this value"}
        if v["status"] == "verified":  # Hindi / regional script or illegible parts on the quoted line: a person checks it (V1 item 3.6)
            fl = ingest.flagged_overlap(page, loc["start"], loc["end"])
            if fl is not None:
                v = {**v, "status": "needs_review", "reason": "the quoted line " + fl["flag"].replace(": verify", "") + ": verify against the source"}
    return v


DATE_KEYS = ("report_date_iso", "event_date_iso", "report_date_assumed", "event_date_assumed", "report_date_quote", "event_date_quote",
             "report_date_label", "event_date_label", "date_unconfirmed", "date_suggestion", "date_flags", "dates", "model_date_iso")


def finish_classification(c, full, texts, filename, dob_iso=""):
    """Rules over the model's header reading: status and signature from docstatus, the model's quotes kept only when found in the
    text, the report and event dates read with their labels from the text (V1 item 3.1: the model's date only when found in the text,
    the filename a suggestion only, no date found = unconfirmed), the patient id kept only when found verbatim. Shared by Case File
    processing and intake (V1 item 2.3)."""
    status, squote, notes = docstatus.detect_status(full)
    signed, sline = docstatus.detect_signature(full)
    if status == "UNSTATED" and c.get("status_quote") and grounding.locate(c["status_quote"], texts):
        st2, _, _ = docstatus.detect_status(c["status_quote"])  # the model found a status line the rules missed
        if st2 != "UNSTATED":
            status, squote = st2, c["status_quote"]
    c["status"], c["status_quote"], c["signed"], c["status_notes"] = status, squote, signed, notes
    c["signature_quote"] = sline or (c.get("signature_quote") if c.get("signature_quote") and grounding.locate(c["signature_quote"], texts) else "")
    dd = dates.document_dates(texts, filename, c.get("doc_type") or "", c.get("report_date") or "", dob_iso)
    c.update({k: dd[k] for k in DATE_KEYS})
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
    """Does the document belong to this Case File's patient? Returns (verdict, matcher decision).
    match: an identifier printed on the document equals one the Case File knows (compatible name, no sex or age conflict);
    name_match: no identifier agrees but the printed name is compatible (exact, a transliteration variant, initials) and no identifier
    contradicts; id_differs: the document prints a hospital identifier this Case File does not know (another patient's, or one not
    learned yet): check it; mismatch_or_missing: an identifier agrees but the name, age or sex differs (possible wrong patient), or
    nothing agrees. The old text search (UHID / MRN substring, name tokens) is used only when the rules read neither an identifier
    nor a name. None when the Case File has no patient."""
    if not (case_patient and (case_patient.get("mrn") or case_patient.get("name"))):
        return None, None
    if idr is not None and (idr.get("ids") or idr.get("name")):
        m = identity.match(idr, [{"case_id": "this", "patient": case_patient}])
        d = m["decision"]
        compatible = any(c.get("name_match") in ("exact", "variant", "initials") and c.get("sex_fit") is not False for c in m.get("candidates", []))
        if d == "auto_link":
            return "match", m
        if d == "id_conflict":
            return "mismatch_or_missing", m
        if d == "new_case" or (idr.get("ids") and compatible):
            return "id_differs", m
        if compatible or d == "suggest":
            return "name_match", m
        return "mismatch_or_missing", m
    nf = grounding.norm(full)
    mrn = grounding.norm(case_patient.get("mrn") or "")
    toks = [t for t in re.findall(r"[a-z]{3,}", grounding.norm(case_patient.get("name") or "")) if t not in ("synthetic", "mr", "mrs", "ms", "dr")]
    if mrn and mrn in nf:
        return "match", None
    if toks and sum(1 for t in toks if t in nf) >= min(2, len(toks)):
        return "name_match", None
    return "mismatch_or_missing", None


def refresh_identity(case_id, doc_id, case_patient):
    """Re-run the identity check of a processed document against the Case File's current patient record (no model): after the Case
    File learned identifiers from other records, a document that printed only the CR No. may now match."""
    doc = store.get_doc(case_id, doc_id)
    if not doc or doc.get("state") != "ready" or not doc.get("identity_read"):
        return doc
    ident, m = identity_check(_doc_text(doc.get("pages") or []), case_patient, doc["identity_read"])
    if ident and ident != doc.get("identity"):
        doc["identity"] = ident
        if ident == "match":
            from . import intake
            intake.learn_ids(case_id, doc["identity_read"], "system:identity", doc_id)
        store.save_doc(case_id, doc)
    return doc


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
            doc["classification"] = finish_classification(c, full, texts, doc["filename"], identity.patient_record(case_patient or {}).get("dob") or "")
        c = doc["classification"]
        # identity as printed (rules first; V1 item 2.4) and the check that the document belongs to this Case File's patient
        if not doc.get("identity_read"):
            from . import intake  # the same reader as the intake area (model fallback quote checked)
            doc["identity_read"] = intake.read_identity(doc, identity.patient_record(case_patient or {})["ids"])
        ident, m = identity_check(full, case_patient, doc["identity_read"])
        if ident:
            doc["identity"] = ident
            if ident == "match" and m is not None and m["decision"] == "auto_link":  # an exact identifier: the Case File learns the record's other identifiers
                from . import intake
                intake.learn_ids(case_id, doc["identity_read"], "system:identity", doc_id)
        doc["extracted_under"] = protocol_id or ""  # the protocol the fields were extracted under (re-run if the Case File is listed meanwhile)
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
            # every value read (the first, and different values from other windows of a long document) is verified against the
            # whole document; unverified alternatives are dropped, several verified values go to the expert with every quote (V1 item 3.4)
            cands = [{"value": r["value"], "quote": r.get("quote", "")}] + [
                {"value": a["value"], "quote": a.get("quote") or ""} for a in r.get("alternatives") or [] if (a.get("value") or "").strip()]
            checked = [(cd, _verify_value(cd["value"], cd["quote"], texts, pages)) for cd in cands]
            ok = [(cd, v) for cd, v in checked if v["status"] != "unverified"]
            (main, v), others = (ok[0] if ok else checked[0]), ok[1:]
            pending = bool(PENDING_RE.search(main["value"]))
            facts[fid] = {"value": main["value"].strip(), "quote": (v["location"] or {}).get("matched") or main["quote"],
                          "model_quote": main["quote"], "verification": v["status"], "reason": v.get("reason"),
                          "location": v["location"], "state": "pending" if pending else "present",
                          "polarity": "negated" if NEGATED_RE.search(main["value"]) else "affirmed"}
            ev = {"kind": "fact_verification", "doc_id": doc_id, "fact": fid, "value": main["value"], "result": v["status"], "reason": v.get("reason")}
            if others:
                facts[fid].update(verification="needs_review", reason="different values in different parts of the document",
                                  alternatives=[{"value": cd["value"].strip(), "quote": (w["location"] or {}).get("matched") or cd["quote"],
                                                 "location": w["location"], "verification": w["status"]} for cd, w in others])
                ev.update(result="needs_review", reason=facts[fid]["reason"], alternatives=[cd["value"] for cd, _ in others])
            if len(cands) > 1:
                ev["alternatives_dropped"] = len(cands) - len(ok) - (0 if ok else 1)
            au(ev)
        doc["facts"] = facts
        doc["state"] = "ready"; doc["processed"] = store.now_iso()
        store.save_doc(case_id, doc); progress and progress(doc_id, "ready")
        return doc
    except Exception as e:
        doc.update(state="error", error=f"{e.__class__.__name__}: {str(e)[:300]}"); store.save_doc(case_id, doc)
        au({"kind": "error", "doc_id": doc_id, "error": doc["error"]}); progress and progress(doc_id, "error")
        return doc
