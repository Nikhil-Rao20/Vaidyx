"""Role-specific AI support agents for the Tumour Board.

When a specialist is unavailable, the corresponding agent prepares a specialty-specific brief from the Case File
records: what the signed reports document, what is pending or missing, discrepancies between documents, and points
the board may want to clarify. It does not interpret images, diagnose, stage or recommend treatment; every item
carries a verified quote; the brief stays an AI draft until an expert marks it reviewed (expert-in-the-loop).

Agent loop (ReAct style, model-agnostic, JSON steps): observe -> choose a tool -> read the result -> ... -> write
the brief. Tools only read the Case File and the agent's guideline pack (V1 item 5.5: guideline folders of its specialty, Indian
sources first, and a reporting checklist). A guideline passage is a "reference" cited by id with a verbatim quote, kept apart from
the record citations; it is never a fact about the patient and never a recommendation for this patient.
"""
import asyncio, json, re, time

from . import dates, guardrails, guidelines, llm, packs, protocol, qa, rules, search, store

ROLES = {
    "radiology": {"label": "Radiology support", "department": "Radiology",
                  "focus": "imaging reports: modality and date of each study, lesion sizes and measurements exactly as reported, nodal and distant "
                           "findings as reported, comparison with prior imaging as documented, imaging that is missing, pending or not final, and "
                           "differences between reports",
                  "doc_types": ["ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan"]},
    "pathology": {"label": "Pathology support", "department": "Pathology",
                  "focus": "histopathology, cytology, IHC and molecular reports: specimen, histologic type and grade as reported, IHC and biomarker "
                           "results with method/clone as written, report status and signature, superseded or preliminary reports, tests pending",
                  "doc_types": ["histopathology", "cytology", "ihc", "molecular"]},
    "medical_oncology": {"label": "Medical oncology support", "department": "Medical Oncology",
                         "focus": "clinical history, performance status, comorbidities, current medications, prior and ongoing treatment as documented, "
                                  "laboratory values relevant to fitness as reported, the question the treating team asks the board",
                         "doc_types": ["clinical_note", "referral", "discharge_summary", "lab", "treatment_summary", "tumour_board_record"]},
    "surgical_oncology": {"label": "Surgical oncology support", "department": "Surgical Oncology",
                          "focus": "documented tumour location and extent from reports, prior procedures and endoscopy, comorbidities and performance "
                                   "status as documented, previous Tumour Board decisions and whether their actions are documented as done",
                          "doc_types": ["clinical_note", "endoscopy", "operative_note", "ct", "mri", "tumour_board_record"]},
    "radiation_oncology": {"label": "Radiation oncology support", "department": "Radiation Oncology",
                           "focus": "radiotherapy delivered as documented (dose, fractions, dates, concurrent agents, toxicity), restaging after "
                                    "treatment, previous Tumour Board plans involving radiotherapy and whether follow-up is documented",
                           "doc_types": ["treatment_summary", "clinical_note", "mri", "ct", "tumour_board_record"]},
    "nuclear_medicine": {"label": "Nuclear medicine support", "department": "Nuclear Medicine",
                         "focus": "PET/CT and bone scan reports: study dates, SUV values and findings exactly as reported, staging as recorded in the "
                                  "report, comparison with other imaging as documented",
                         "doc_types": ["pet_ct", "bone_scan"]},
}

NOT_LISTED = "This Case File is not listed yet: list it before preparing a brief"

TOOLS_DOC = """Tools (all read-only):
- list_documents: no input. Lists every document with id, title, type, date, status (and clinician attestations).
- read_document: input = a document id, optionally with pages (for example 'D123 pages 3-5' or 'D123 page 2'). Returns the text of
  those pages (up to 12,000 characters). Without pages it returns the first pages that fit and says which pages are not shown.
- search: input = a question or keywords. Returns the most relevant passages from all documents.
- find_values: input = a term (for example 'PD-L1', 'CEA', 'Ki-67'). Returns every line in the Case File that mentions it, with dates.
- get_facts: no input. Returns the primary fields already extracted and verified by the system.
- get_gaps: no input. Returns the Pre-Authorization gaps (missing, pending or non-final records).
- search_guidelines: input = a question or keywords. Returns reference passages from this specialty's guideline pack, Indian sources
  first (NCG, ICMR, Tata Memorial Centre, PM-JAY, ICRI / IRIA), then international, each with an id such as G3. Reference text only:
  never a fact about this patient and never a recommendation for this patient.
- finish: no input. Use when you have read enough to write the brief."""

STEP_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "thought": {"type": "string", "description": "one short sentence: what you still need"},
    "tool": {"type": "string", "enum": ["list_documents", "read_document", "search", "find_values", "get_facts", "get_gaps", "search_guidelines", "finish"]},
    "input": {"type": "string"}}, "required": ["thought", "tool", "input"]}

ITEM = {"type": "object", "additionalProperties": False, "properties": {
    "text": {"type": "string"},
    "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string", "description": "exact text copied from that document"}},
                  "required": ["doc_id", "quote"]}}}, "required": ["text", "citations"]}
POINT = {"type": "object", "additionalProperties": False, "properties": {  # a point for review may cite guideline references (V1 item 5.5)
    "text": {"type": "string"}, "citations": ITEM["properties"]["citations"],
    "references": {"type": "array", "description": "guideline passages relevant to this point, by id (G1, G2 ...), Indian sources first",
                   "items": {"type": "object", "additionalProperties": False,
                             "properties": {"ref_id": {"type": "string"}, "quote": {"type": "string", "description": "exact text copied from that guideline passage"}},
                             "required": ["ref_id", "quote"]}}}, "required": ["text", "citations", "references"]}
BRIEF_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sections": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "properties": {"heading": {"type": "string"}, "items": {"type": "array", "items": ITEM}}, "required": ["heading", "items"]}},
    "points_for_review": {"type": "array", "items": POINT, "description": "questions or clarifications for the board (never treatment recommendations)"},
    "not_documented": {"type": "array", "items": {"type": "string"}, "description": "items relevant to this specialty that are not documented"}},
    "required": ["sections", "points_for_review", "not_documented"]}


def _system(role):
    r = ROLES[role]
    return (f"You are the {r['label']} agent for a cancer Tumour Board. You act as a physician assistant: you prepare a specialty-specific "
            f"brief from the Case File records for the multidisciplinary team, for use when the {r['department']} specialist is unavailable. "
            f"Focus: {r['focus']}.\n"
            "Strict rules: use only what is written in the documents; copy values exactly; cite every statement with the document id and an exact "
            "quote; do not interpret images or scans (only what reports state); do not diagnose; do not derive or assign stage (only quote the stage "
            "as recorded); do not recommend, suggest or choose any treatment or management; do not predict prognosis. Points for review are "
            "questions or clarifications for the board about the records (for example a pending result, a draft report, two reports that differ), "
            "never recommendations. Guideline passages (ids G1, G2 ...) are reference text: cite them only under 'references' of a point for "
            "review, prefer Indian sources (NCG, ICMR, Tata Memorial Centre, PM-JAY, ICRI / IRIA), never present guideline text as a fact about "
            "the patient or as advice for this patient. Your output is a draft for expert review.")


def _overrides(case_id):
    """The Case File's clinician confirmations (attestations, waivers): they beat the model's reading everywhere (V1 item 1.2)."""
    return store.get_state(case_id).get("overrides") or {}


def _attestation(overrides, doc_id):
    att = (overrides.get("documents") or {}).get(doc_id) or {}
    return f"attested final by {att.get('by') or 'clinician'}" if att.get("attested_final") else ""


def _doc_list(case_id):
    rows, ov = [], _overrides(case_id)
    for d in rules.case_docs(case_id):  # confirmed document type and dates win (V1 item 2.2)
        c = d.get("classification") or {}
        att = _attestation(ov, d["doc_id"])
        status = c.get("status")
        if att:
            status = f"status not stated, {att}" if status in ("UNSTATED", "UNKNOWN", None) else f"{status}, {att}"
        rows.append(f"{d['doc_id']} | {c.get('title') or d['filename']} | {c.get('doc_type')} | {dates.doc_dates(d)['event'] or '?'} | {status}"
                    + (" | unsigned" if c.get("signed") == "no" and not att else ""))
    return "\n".join(rows)


def _facts_text(case_id):
    ov = _overrides(case_id)
    facts = rules.resolve_facts(rules.case_docs(case_id), ov)
    cat = protocol.facts()
    lines = []
    for fid, f in facts.items():
        for h in f["history"]:
            if h["verification"] in rules.VERIFIED:
                att = _attestation(ov, h["doc_id"])
                # a value a clinician confirmed carries no quote of its own: say who confirmed it (V1 item 2.2)
                conf = h.get("confirmed_by") or ("clinician" if h["verification"] == "confirmed" else "")
                lines.append(f"{cat.get(fid, {}).get('label', fid)}: {h['value']}" + (f" (confirmed by {conf}, no quote)" if conf else "")
                             + f"  [{h['doc_id']} {h['doc_title']} {h['date'] or ''} {h['doc_status']}" + (f", {att}" if att else "") + "]")
    return "\n".join(lines) or "(none)"


def _gaps_text(case_id):
    g = (store.get_state(case_id).get("gate") or rules.evaluate(case_id)) if store.get_case(case_id).get("protocol") else None
    if g is None:
        return "(not listed: no Pre-Authorization check yet)"
    return "\n".join(f"- {r['label']} ({r['department']}): {r['status']}. {'; '.join(r['problems'])}" for r in g["requirements"] if r["status"] != "satisfied") or "(no gaps)"


READ_CAP = 12000  # characters per read_document result and per tool result kept in the scratchpad (V1 item 3.4)
_PAGE_RANGE = re.compile(r"^(?:pages?|pp?\.?)?\s*(\d+)(?:\s*(?:-|to)\s*(\d+))?$", re.I)


def _read_document(case_id, arg):
    """'<doc id>' or '<doc id> pages 3-5' (also 'p3-5', 'pages 3', 'page 3'); pages are 1-based. Returns the pages that fit in
    READ_CAP characters, each under a [page N] line, and a last line naming the pages not shown when the text is cut."""
    parts = arg.strip().replace("\u2013", "-").split(None, 1)  # "D123, pages 3-5" and an en dash are accepted
    if parts:
        parts[0] = parts[0].strip(",;:")
    d = store.get_doc(case_id, parts[0]) if parts and parts[0] else None
    if not d:
        return "No document with that id. Use list_documents."
    pages = d.get("pages") or []
    n = len(pages)
    if not n:
        return "This document has no readable text."
    a, b = 1, n
    if len(parts) > 1:
        m = _PAGE_RANGE.match(parts[1].strip())
        if not m:
            return f"Could not read the page range '{parts[1].strip()}'. Ask for pages like '{d['doc_id']} pages 2-4' or '{d['doc_id']} page 2'."
        a = int(m.group(1)); b = int(m.group(2) or a)
        if a < 1 or b < a or a > n:
            return f"Document {d['doc_id']} has {n} page{'s' if n != 1 else ''}; pages {a} to {b} do not exist. Ask for pages 1 to {n}."
        b = min(b, n)
    budget = READ_CAP - 200  # room for the continuation line

    def rest(i):  # pages i..b not shown
        if i == b:
            return f"page {i} not shown; ask for it with '{d['doc_id']} page {i}'"
        return f"pages {i} to {b} not shown; ask for them with '{d['doc_id']} pages {i}-{b}'"
    out, used, last = [], 0, a - 1
    for i in range(a, b + 1):
        block = f"[page {i}]\n{pages[i - 1].get('text') or ''}"
        if used + len(block) + 1 > budget:
            if not out:  # one page longer than the cap: show its start
                out.append(block[:budget])
                more = f"the rest of page {i} is not shown"
                out.append(f"[... document continues: {more}" + (f"; {rest(i + 1)}" if i < b else "") + "]")
                return "\n".join(out)
            break
        out.append(block); used += len(block) + 1; last = i
    if last < b:
        out.append(f"[... document continues: {rest(last + 1)}]")
    return "\n".join(out)


# V1 item 5.5: guideline references of the specialty pack
ROLE_QUERY = {  # the pack search run before the first step, with the protocol label in front
    "radiology": "imaging work-up and imaging report contents", "pathology": "pathology reporting and biomarker testing",
    "medical_oncology": "work-up and fitness assessment before systemic therapy", "surgical_oncology": "work-up and assessment of resectability",
    "radiation_oncology": "work-up before radiotherapy and response assessment", "nuclear_medicine": "PET-CT and bone scan indications in staging"}
_GENERIC = set("the and for with from that this which there their these those into about after before between within without also only "
               "not any are was were been has have had can may should would will report reports reported patient case file documented document "
               "documents board clarify clarification whether confirm please result results date dated available stated state status".split())


# cancer sites named in guideline file names: a passage from a guideline for another cancer is never attached to this Case File
_SITES = ("lung", "nsclc", "thoracic", "breast", "rect", "colorectal", "colon", "head", "neck", "oral", "gyn", "cervi", "ovar", "endomet",
          "prostate", "gall", "liver", "hepat", "gastric", "stomach", "oesoph", "esoph", "pancrea", "renal", "kidney", "bladder", "thyroid",
          "glioma", "lymphoma", "sarcoma")


def _cancer_fit(h, protocol_id):
    """'same' when the passage's guideline is about this Case File's cancer, 'other' when it is about another cancer, '' otherwise
    (a guideline for many cancers, such as ICRI / IRIA or the PM-JAY manual)."""
    name = (h["file"] + " " + h["title"]).lower()
    words = guidelines.CANCER_WORDS.get(protocol_id or "", [])
    if any(w in name for w in words):
        return "same"
    return "other" if any(x in name for x in _SITES) else ""


def _content_words(text):
    return {t for t in search.tokenize(text or "") if len(t) >= 3 and t not in _GENERIC and not t.isdigit()}


def _ref_label(h):
    return f"{h['org']} | {h['title']} | p. {h['page']}" + (f"-{h['page_end']}" if h.get("page_end") and h["page_end"] != h["page"] else "") + f" | {h['region']}"


def _search_guidelines(role, case, arg, refs):
    """Pack search; every passage gets an id (G1, G2 ...) kept in refs for the references of the brief."""
    res = packs.search(role, arg, case.get("protocol"))
    out = []
    for h in res["india"] + res["international"]:
        rid = next((k for k, v in refs.items() if (v["file"], v["page"], v["text"]) == (h["file"], h["page"], h["text"])), None)
        if rid is None:
            rid = f"G{len(refs) + 1}"; refs[rid] = h
        out.append(f"[{rid} | {_ref_label(h)}]\n{h['text'][:2000]}")  # a passage is about 1,100 characters; tables can run longer
    return "\n\n".join(out) or "No guideline passage found in this specialty's pack."


def _reference(h, quote, by):
    return {"file": h["file"], "title": h["title"], "org": h["org"], "region": h["region"], "page": h["page"],
            "page_end": h.get("page_end") or h["page"], "quote": quote, "by": by}


def _verify_references(point_refs, refs, protocol_id=None):
    """The point's references whose quote is verbatim in the cited guideline passage and whose guideline is not about another cancer;
    the rest are dropped (counted)."""
    out, dropped = [], 0
    for r in point_refs or []:
        h = refs.get((r.get("ref_id") or "").strip())
        locs = qa._locate_quote(r.get("quote") or "", [h["text"]]) if h else []
        if not locs or (protocol_id and _cancer_fit(h, protocol_id) == "other"):
            dropped += 1; continue
        ref = _reference(h, " ... ".join(l["matched"] for l in locs), "agent")
        if not any((x["file"], x["page"]) == (ref["file"], ref["page"]) for x in out):
            out.append(ref)
    return out, dropped


def _relevance(words, acronyms, text):
    """Content words shared with a passage; a shared acronym (EGFR, PET-CT, CECT, HER2) counts twice."""
    shared = words & _content_words(text)
    return len(shared) + len(shared & acronyms)


def _indian_reference(role, case, text):
    """When a point cites no Indian source: the best Indian passage of the pack for the point, if it shares at least two content words
    (or one acronym such as EGFR) with it and comes from a guideline for this cancer (or a general one whose passage names the cancer);
    the quote is its most overlapping sentence, verbatim. None when the pack has no such passage."""
    cwords = guidelines.CANCER_WORDS.get(case.get("protocol") or "", [])
    words = _content_words(text)
    acronyms = {t.lower() for t in re.findall(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*\b", text or "") if len(t) >= 3} & words
    if not words:
        return None
    for h in packs.search(role, text, case.get("protocol"), india=3, intl=0)["india"]:
        fit = _cancer_fit(h, case.get("protocol"))
        if fit == "other" or (fit == "" and not any(w in h["text"].lower() for w in cwords)):
            continue
        if _relevance(words, acronyms, h["text"]) < 2:
            continue
        sents = [x.strip() for x in re.split(r"(?<=[.;:])\s+|\n", h["text"]) if len(x.strip()) >= 20]
        best = max(sents, key=lambda x: _relevance(words, acronyms, x), default="")
        if best and _relevance(words, acronyms, best) >= 1:
            return _reference(h, best[:400], "search")
    return None


async def _tool(case_id, tool, arg, role=None, refs=None):
    if tool == "search_guidelines":
        if role is None or refs is None:
            return "Guideline search is not available here."
        return await asyncio.to_thread(_search_guidelines, role, store.get_case(case_id), arg, refs)
    if tool == "list_documents":
        return _doc_list(case_id)
    if tool == "read_document":
        return _read_document(case_id, arg)
    if tool == "search":
        hits = await asyncio.to_thread(search.index(case_id).search, arg, 6)
        return "\n\n".join(f"[{h['doc_id']} | {h['doc_title']} | {h['date'] or '?'}]\n{h['text']}" for h in hits) or "No results."
    if tool == "find_values":
        r = search.find_values(case_id, arg, 25)
        return "\n".join(f"[{h['doc_id']} | {h['doc_title']} | {h['date'] or '?'} | {h['status']}] {h['text']}" for h in r["hits"]) or "No line mentions it."
    if tool == "get_facts":
        return _facts_text(case_id)
    if tool == "get_gaps":
        return _gaps_text(case_id)
    return ""


def _pack_summary(role, protocol_id):
    """What the brief drew on: the pack's sources (India first) and the reporting checklist used, for the reader."""
    pk = packs.pack(role)
    cl = packs.checklist(role, protocol_id)
    return {"label": pk["label"], "sources": [{"org": s["org"], "region": s["region"]} for s in pk["sources"]],
            "checklist": {"title": cl["title"], "org": cl["org"], "region": cl["region"], "pages": cl["pages"], "file": cl["file"]} if cl else None}


async def run_agent(case_id, role, focus_question="", max_steps=5):
    """Async generator of events: {"type": "start"|"step"|"brief"|"error", ...}."""
    if role not in ROLES:
        yield {"type": "error", "message": "unknown role"}; return
    au = store.auditor(case_id)
    t0 = time.time()
    case = store.get_case(case_id)
    if not case.get("protocol"):  # an unlisted Case File (V1 item 2.5): no brief, no model call
        au({"kind": "agent_not_listed", "role": role})
        yield {"type": "error", "message": NOT_LISTED}; return
    r = ROLES[role]
    sig = rules.case_signature(case_id)  # taken before reading the records: a change during the run marks the brief stale (V1 item 4.5)
    au({"kind": "agent_start", "role": role, "focus": focus_question})
    yield {"type": "start", "role": role, "label": r["label"]}
    if focus_question:
        g = await guardrails.check_input(focus_question, au)
        if not g["allowed"]:
            yield {"type": "error", "message": g["message"], "category": g["category"]}; return
    relevant = sorted([d for d in rules.case_docs(case_id) if d.get("state") == "ready" and (d.get("classification") or {}).get("doc_type") in r["doc_types"]],
                      key=lambda d: dates.doc_dates(d)["sort"], reverse=True)
    scratch = [f"Patient: {case['patient'].get('name')} ({case['patient'].get('mrn')}). Protocol: {case['protocol']}.",
               "DOCUMENTS:\n" + _doc_list(case_id),
               "VERIFIED FIELDS:\n" + _facts_text(case_id),
               "PRE-AUTHORIZATION GAPS:\n" + _gaps_text(case_id)]
    refs = {}  # guideline passages seen in this run, by id (V1 item 5.5)
    checklist = packs.checklist_text(role, case["protocol"])
    if checklist:
        scratch.append(checklist)
    prot_label = (protocol.get(case["protocol"]) or {}).get("label") or case["protocol"]
    gq = f"{prot_label}: {ROLE_QUERY.get(role, r['focus'][:80])}"
    try:
        gl = await asyncio.to_thread(_search_guidelines, role, case, gq, refs)
        scratch.append(f"GUIDELINE REFERENCES (reference text from the {r['label'].lower()} pack, Indian sources first; cite by id under "
                       f"'references' of a point for review; never a fact about this patient or a recommendation for this patient):\n{gl}")
        yield {"type": "step", "tool": "search_guidelines", "input": gq, "thought": "Guideline pack, Indian sources first", "auto": True}
    except Exception as e:  # the guideline index is optional for a brief: the records still are the source
        au({"kind": "agent_guidelines_unavailable", "role": role, "error": str(e)[:200]})
    # documents of this specialty are read up front, newest first, within a context budget (the rest stay reachable via tools)
    budget, used = 40000, 0
    for d in relevant:
        text = "\n".join(p["text"] for p in d.get("pages") or [])
        if used + len(text) > budget:
            yield {"type": "step", "tool": "skip", "input": d["doc_id"], "thought": f"Not pre-read (context budget): {(d.get('classification') or {}).get('title') or d['filename']}; available via read_document", "auto": True}
            continue
        used += len(text)
        scratch.append(f"DOCUMENT {d['doc_id']} (read):\n" + text)
        yield {"type": "step", "tool": "read_document", "input": d["doc_id"], "thought": f"Reading {(d.get('classification') or {}).get('title') or d['filename']}", "auto": True}
    task = f"Prepare the {r['label']} brief" + (f", focusing on: {focus_question}" if focus_question else "") + "."
    for step in range(max_steps):
        msgs = [{"role": "system", "content": _system(role)},
                {"role": "user", "content": "\n\n".join(scratch) + f"\n\n{TOOLS_DOC}\n\nTASK: {task}\nDecide the next tool call. If you already have what you need, choose finish."}]
        try:
            s = await llm.chat("reasoner", msgs, json_schema=STEP_SCHEMA, max_tokens=200, purpose=f"agent {role} step", audit=au)
        except Exception as e:
            yield {"type": "error", "message": str(e)[:200]}; return
        tool, arg = s.get("tool", "finish"), s.get("input", "")
        if tool == "finish":
            yield {"type": "step", "tool": "finish", "input": "", "thought": s.get("thought", "")}
            break
        try:
            obs = await _tool(case_id, tool, arg, role, refs)
        except Exception as e:  # a failing tool (e.g. the guideline index not built) is an observation, not the end of the brief
            obs = f"The tool failed ({type(e).__name__}); continue with the records."
        scratch.append(f"TOOL {tool}({arg}) RESULT:\n{obs[:READ_CAP]}")
        au({"kind": "agent_tool", "role": role, "tool": tool, "input": arg})
        yield {"type": "step", "tool": tool, "input": arg, "thought": s.get("thought", ""), "observation": obs[:600]}
    msgs = [{"role": "system", "content": _system(role)},
            {"role": "user", "content": "\n\n".join(scratch) + f"\n\nTASK: {task}\nWrite the brief now: 3 to 5 sections with short factual items "
             "(each with citations), points for review (questions about the records for the board, each with citations, and with references "
             "to the guideline passages above that bear on the point, by id with an exact quote, Indian sources first; an empty list when none "
             "applies), and anything relevant to this specialty that is not documented."}]
    try:
        b = await llm.chat("reasoner", msgs, json_schema=BRIEF_SCHEMA, max_tokens=2200, purpose=f"agent {role} brief", audit=au)
    except Exception as e:
        yield {"type": "error", "message": str(e)[:200]}; return
    dropped = 0; issues = []
    sections = []
    for sec in b.get("sections") or []:
        items = qa.verify_statements(case_id, sec.get("items"))
        dropped += len(sec.get("items") or []) - len(items)
        kept = []
        for it in items:
            iss = guardrails.scan_output(it["text"])
            if iss:
                issues += iss
            else:
                kept.append(it)
        if kept:
            sections.append({"heading": sec.get("heading", ""), "items": kept})
    pts2, refs_dropped = [], 0
    for raw in b.get("points_for_review") or []:
        v = qa.verify_statements(case_id, [raw])  # one at a time: each kept point keeps its own references
        if not v:
            dropped += 1; continue
        p = v[0]
        iss = guardrails.scan_output(p["text"])
        issues += iss
        if iss:
            continue
        p["references"], nd_refs = _verify_references(raw.get("references"), refs, case["protocol"])
        refs_dropped += nd_refs
        if not any(x["region"] == "India" for x in p["references"]):  # an Indian source whenever the pack has one for this point
            try:
                ind = await asyncio.to_thread(_indian_reference, role, case, p["text"])
            except Exception:
                ind = None
            if ind:
                p["references"].insert(0, ind)
        p["references"].sort(key=lambda x: x["region"] != "India")
        pts2.append(p)
    nd, nd_dropped = [], 0
    for x in (b.get("not_documented") or []):
        if guardrails.scan_output(x):
            continue
        hits = search.find_values(case_id, x, 5)["hits"]  # the claim 'X is not documented' is checked against the Case File
        if hits:
            nd_dropped += 1
            au({"kind": "not_documented_claim_rejected", "role": role, "claim": x, "found_in": [h["doc_id"] for h in hits[:3]]})
        else:
            nd.append(x)
    if issues:
        au({"kind": "guardrail_output", "where": f"agent {role}", "issues": issues})
    brief = {"role": role, "label": r["label"], "sections": sections, "points_for_review": pts2, "not_documented": nd,
             "dropped_unverified": dropped, "guardrail_removed": len(issues), "not_documented_rejected": nd_dropped, "generated": store.now_iso(),
             "references_dropped": refs_dropped, "pack": _pack_summary(role, case["protocol"]),
             "model": __import__("tumour_board.config", fromlist=["models"]).models()["reasoner"].get("label") or "reasoner",
             "seconds": round(time.time() - t0, 1), "review": {"status": "ai_draft"},
             "signature": sig}  # what it was written from; a changed Case File marks it stale (V1 item 4.5)
    st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
    au({"kind": "agent_brief", "role": role, "items": sum(len(s["items"]) for s in sections), "points": len(pts2), "dropped_unverified": dropped,
        "guardrail_removed": len(issues), "seconds": brief["seconds"], "references": sum(len(p["references"]) for p in pts2),
        "points_with_indian_reference": sum(any(x["region"] == "India" for x in p["references"]) for p in pts2), "references_dropped": refs_dropped})
    yield {"type": "brief", "brief": brief}
