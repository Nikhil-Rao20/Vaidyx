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
import asyncio, inspect, json, re, time

from . import config, dates, grounding, guardrails, guidelines, llm, org, packs, protocol, qa, rules, search, skills, store

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



def spec(role):
    """The role as the agent runs it: the code defaults of ROLES under the role's skill file (label, department, doc_types, focus,
    guideline query and guidance from tumour_board/skills/<role>/SKILL.md, or the hospital's edit of it). The hard rules never
    come from the skill (see _system). KeyError for an unknown role: skills cannot add roles."""
    r = dict(ROLES[role])
    s = skills.get(role)
    if s:
        r.update(label=s["label"], department=s["department"], doc_types=list(s["doc_types"]), focus=s["focus_text"],
                 guideline_query=s["guideline_query"] or ROLE_QUERY.get(role, ""), guidance=s["guidance"], skill_origin=s["origin"], skill_sha=s["sha"],
                 allowed_tools=s.get("allowed_tools"))  # a skill may only restrict the fixed tool list
    else:
        r.update(guideline_query=ROLE_QUERY.get(role, ""), guidance=[], skill_origin="code", skill_sha="", allowed_tools=None)
    return r


NOT_LISTED = "This Case File is not listed yet: list it before preparing a brief"
# the brief's format: a board session reuses a stored brief only when it has this version (2: removed items and document ids not read as
# numbers, V1 item 6.4), no focus question and the same near-match setting (Phase 6 review)
BRIEF_VERSION = 2

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


def _guidance_text(r):
    """The skill's optional guidance sections ('What to look for in the records', 'Points for review to raise') as prompt lines."""
    out = []
    for heading, items in r.get("guidance") or []:
        out.append(heading.replace("_", " ").capitalize() + ": " + "; ".join(items))
    return (" ".join(out) + "\n") if out else ""


def _system(role):
    r = spec(role)
    return (f"You are the {r['label']} agent for a cancer Tumour Board. You act as a physician assistant: you prepare a specialty-specific "
            f"brief from the Case File records for the multidisciplinary team, for use when the {r['department']} specialist is unavailable. "
            f"Focus: {r['focus']}.\n" + _guidance_text(r) +
            "Strict rules: use only what is written in the documents; copy values exactly; cite every statement with the document id and an exact "
            "quote; do not interpret images or scans (only what reports state); do not diagnose; do not derive or assign stage (only quote the stage "
            "as recorded); do not recommend, suggest or choose any treatment or management; do not predict prognosis. Points for review are "
            "questions or clarifications for the board about the records (for example a pending result, a draft report, two reports that differ), "
            "never recommendations. Guideline passages (ids G1, G2 ...) are reference text: cite them only under 'references' of a point for "
            "review, and only passages about what reports and records should document or which records a work-up lists, never treatment "
            "options, indications, eligibility or management; prefer Indian sources (NCG, ICMR, Tata Memorial Centre, PM-JAY, ICRI / IRIA); never "
            "present guideline text as a fact about the patient or apply it to this patient. Your output is a draft for expert review.")


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
ROLE_QUERY = {  # the pack search run before the first step, with the protocol label in front: records and reporting, never treatment
    "radiology": "imaging report contents and reporting checklist", "pathology": "pathology report contents and biomarker reporting",
    "medical_oncology": "baseline investigations, performance status and laboratory records in the work-up",
    "surgical_oncology": "documentation of tumour extent and prior procedures in the work-up records",
    "radiation_oncology": "documentation of radiotherapy delivered and restaging imaging reports",
    "nuclear_medicine": "PET-CT and bone scan report contents in the work-up"}
# a reference quote that states a treatment, an indication or eligibility is never shown under a patient's point (V1 Phase 5 review):
# only passages about what reports and work-up records contain are references
_DIRECTIVE = re.compile(
    r"\b(?:offer(?:ed|s)?|recommend\w*|indicat\w*|should (?:not )?be (?:offered|treated|given|considered|performed|done|started)|should (?:receive|undergo)"
    r"|consider\w*|prefer\w*|treatment of choice|standard (?:of care|treatment|operation|option)"
    r"|advis\w*|candidates?|eligib\w*|benefit\w*|surg\w*|resect\w*|lobectomy|pneumonectomy|mastectomy|lumpectomy|dissection|excision|chemo\w*"
    r"|radiotherap\w*|radiation therapy|irradiation|\bRT\b|SBRT|SABR|brachytherap\w*|CTRT|\bCRT\b|NACT|\bTNT\b|immunotherap\w*|targeted therap\w*|TKIs?"
    r"|\w+(?:mab|nib|platin|taxel|rubicin)\b|tamoxifen|letrozole|anastrozole|capecitabine|5-?FU|dose|\bGy\b|fractions?|watch and wait|non-operative"
    r"|palliat\w*|adjuvant|neoadjuvant|systemic therap\w*|endocrine therap\w*|hormon\w* therap\w*|treatment options?|treated with|first[- ]line"
    r"|second[- ]line|maintenance|regimens?|cycles?)\b", re.I)
# a point for review that asks for a treatment or work-up decision for this patient is dropped like any other scope breach
_POINT_SCOPE = re.compile(
    r"\bindicated\b[^.?]{0,60}\b(?:for (?:this|the) patient|given)\b|\bis (?:an? |the )?[\w/\- ]{1,30} (?:indicated|required|needed) (?:for|in) (?:this|the) patient"
    r"|\bto (?:determine|decide|assess|plan|guide)\b[^.?]{0,40}\b(?:surgical approach|resectab\w*|treatment|management|therapy|surgery)"
    r"|surgical approach|treatment sequencing|\bsequenc\w*[^.?]{0,30}\b(?:surgery|chemo\w*|NACT|radio\w*)\b|\bcandidate for\b|\beligib\w* for\b", re.I)
_GENERIC = set("the and for with from that this which there their these those into about after before between within without also only "
               "not any are was were been has have had can may should would will report reports reported patient case file documented document "
               "documents board clarify clarification whether confirm please result results date dated available stated state status".split())


# cancer sites named in guideline file names: a passage from a guideline for another cancer is never attached to this Case File
_SITES = ("lung", "nsclc", "thoracic", "breast", "rect", "colorectal", "colon", "head", "neck", "oral", "gyn", "cervi", "ovar", "endomet",
          "prostate", "gall", "liver", "hepat", "gastric", "stomach", "oesoph", "esoph", "pancrea", "renal", "kidney", "bladder", "thyroid",
          "glioma", "lymphoma", "sarcoma")


def _word_start(words, text):
    """Whether any of the words starts a word of the text ('rect' matches 'rectal', never 'direct'); file names count _ - . / as spaces."""
    return bool(words) and bool(re.search(r"\b(?:" + "|".join(map(re.escape, words)) + ")", re.sub(r"[_\-./]+", " ", text.lower())))


def _cancer_fit(h, protocol_id):
    """'same' when the passage's guideline is about this Case File's cancer, 'other' when it is about another cancer, '' otherwise
    (a guideline for many cancers, such as ICRI / IRIA or the PM-JAY manual, or a protocol with no cancer words yet)."""
    words = guidelines.CANCER_WORDS.get(protocol_id or "", [])
    if not words:
        return ""
    name = h["file"] + " " + h["title"]
    if _word_start(words, name):
        return "same"
    return "other" if _word_start(_SITES, name) else ""


def _content_words(text):
    return {t for t in search.tokenize(text or "") if len(t) >= 3 and t not in _GENERIC and not t.isdigit()}


def _page_kind(h):
    """'page' for a PDF page; 'part' for a 6,000-character block of a Word or text file (no real page number)."""
    return "page" if h["file"].lower().endswith(".pdf") else "part"


def _ref_label(h):
    span = f"{h['page']}" + (f"-{h['page_end']}" if h.get("page_end") and h["page_end"] != h["page"] else "")
    return f"{h['org']} | {h['title']} | {'p.' if _page_kind(h) == 'page' else 'part'} {span} | {h['region']}"


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
            "page_end": h.get("page_end") or h["page"], "page_kind": _page_kind(h), "quote": quote, "by": by}


def _in_scope(quote):
    """A reference quote may be shown under a patient's point only when it states no treatment, indication or eligibility."""
    return not _DIRECTIVE.search(quote or "") and not guardrails.scan_output(quote or "")


def _verify_references(point_refs, refs, protocol_id=None):
    """The point's references whose quote is verbatim in the cited guideline passage and whose guideline is not about another cancer;
    the rest are dropped (counted)."""
    out, dropped = [], 0
    for r in point_refs or []:
        h = refs.get((r.get("ref_id") or "").strip())
        locs = qa._locate_quote(r.get("quote") or "", [h["text"]]) if h else []
        # every kept segment must be substantial and together they must make up most of the quote: 'the' or 'for' never verify one
        locs = [l for l in locs if len(grounding.norm(l["matched"])) >= 20 or len(l["matched"].split()) >= 4]
        covered = sum(len(grounding.norm(l["matched"])) for l in locs) / max(len(grounding.norm(r.get("quote") or "")), 1)
        if not locs or covered < 0.6 or (protocol_id and _cancer_fit(h, protocol_id) == "other") \
                or not _in_scope(" ".join(l["matched"] for l in locs)):
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
    """When a point cites no Indian source: the best Indian passage of the pack for the point, if it shares at least three content words
    (an acronym such as EGFR counts twice) with it and comes from a guideline for this cancer (or a general one whose passage names the cancer);
    the quote is its most overlapping sentence, verbatim. None when the pack has no such passage."""
    cwords = guidelines.CANCER_WORDS.get(case.get("protocol") or "", [])
    words = _content_words(text)
    acronyms = {t.lower() for t in re.findall(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*\b", text or "") if len(t) >= 3} & words
    if not words:
        return None
    for h in packs.search(role, text, case.get("protocol"), india=3, intl=0)["india"]:
        fit = _cancer_fit(h, case.get("protocol"))
        if fit == "other" or (fit == "" and not _word_start(cwords, h["text"])):
            continue
        if _relevance(words, acronyms, h["text"]) < 3:
            continue
        # a whole sentence (40 characters or 6 words), not a table cell or a bullet fragment, sharing three content words (an acronym
        # counts twice), in scope; two shared words attached unrelated lines half the time in the Phase 5 measurement
        sents = [x.strip() for x in re.split(r"(?<=[.;:])\s+|\n", h["text"])]
        sents = [x for x in sents if (len(x) >= 40 or len(x.split()) >= 6) and x[:1].isalnum() and _in_scope(x)
                 and _relevance(words, acronyms, x) >= 3]
        if sents:
            return _reference(h, max(sents, key=lambda x: _relevance(words, acronyms, x))[:400], "search")
    return None


async def _tool(case_id, tool, arg, role=None, refs=None):
    if tool == "search_guidelines":
        if role is None or refs is None:
            return "Guideline search is not available here."
        if not guidelines.ready():
            return "The guideline library is still loading; continue with the records."
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
    """What the brief drew on: the pack's sources (India first) and the reporting checklist used, for the reader; None when the pack
    file cannot be read (the brief is still written from the records)."""
    try:
        pk = packs.pack(role)
    except Exception:
        return None
    cl = packs.checklist(role, protocol_id)
    return {"label": pk["label"], "sources": [{"org": s["org"], "region": s["region"]} for s in pk["sources"]],
            "checklist": {"title": cl["title"], "org": cl["org"], "region": cl["region"], "pages": cl["pages"], "file": cl["file"]} if cl else None}


def department_of(role):
    """The hospital's name for the agent's specialty (Indian names from org.json: Radiology support speaks for Radio-diagnosis)."""
    r = spec(role)
    return org.department_name(org.department_id(r["department"])) if org.department_id(r["department"]) else r["department"]


def specialty_documents(case_id, role):
    """(ready, waiting, failed) documents of the agent's specialty: its document types, or uploaded by its department (V1 item 6.6)."""
    r = spec(role); dept = org.department_id(r["department"])
    mine = [d for d in rules.case_docs(case_id) if (d.get("classification") or {}).get("doc_type") in r["doc_types"]
            or (dept and d.get("department") and org.department_id(d["department"]) == dept)]  # V1 ids resolve (V2 2.1)
    return ([d for d in mine if d.get("state") == "ready"], [d for d in mine if d.get("state") not in ("ready", "error")],
            [d for d in mine if d.get("state") == "error"])


def open_department_items(case_id, role):
    """The Pre-Authorization requests still open for the agent's department in this Case File (V1 item 6.6)."""
    dept = org.department_id(spec(role)["department"])
    out = []
    for a in store.get_state(case_id).get("actions") or []:
        if a.get("source") != "pre_authorization" or a.get("status") == "completed":
            continue
        if (a.get("department_id") or org.department_id(a.get("department") or "")) == dept:
            out.append({"label": a.get("label") or "", "what": a.get("what") or "", "level": a.get("level_label") or "", "due": a.get("due") or "",
                        "status": a.get("status") or ""})
    return out


def no_documents_brief(case_id, role, sig, t0):
    """A specialty with no documents in the Case File: no model call, the message and the department's open requests (V1 item 6.6)."""
    _, waiting, failed = specialty_documents(case_id, role)
    dept = department_of(role)
    extra = ([f"{len(waiting)} still being read"] if waiting else []) + ([f"{len(failed)} failed to read"] if failed else [])
    return {"role": role, "label": spec(role)["label"], "no_documents": True, "department": dept,
            "message": f"No {dept} documents in this Case File" + (f" ({', '.join(extra)})" if extra else ""),
            "open_items": open_department_items(case_id, role), "sections": [], "points_for_review": [], "not_documented": [], "removed": [],
            "dropped_unverified": 0, "guardrail_removed": 0, "not_documented_rejected": 0, "references_dropped": 0, "approximate": 0,
            "generated": store.now_iso(), "model": "", "seconds": round(time.time() - t0, 1), "review": {"status": "no_model_call"}, "signature": sig,
            "version": BRIEF_VERSION, "focus": "", "near_match": config.near_match()}


def _removed(item, reason, detail, where):
    """An item taken out after the model wrote it, kept with the reason for reviewers: failed verification, not a fact (V1 item 6.4)."""
    return {"text": item.get("text") if isinstance(item, dict) else str(item), "reason": reason,
            "reason_label": qa.REASONS.get(reason) or REMOVED_REASONS.get(reason, reason), "detail": detail, "where": where,
            "citations": [{"doc_id": c.get("doc_id"), "quote": (c.get("quote") or "")[:400]} for c in ((item.get("citations") or []) if isinstance(item, dict) else [])]}


REMOVED_REASONS = {"found_in_case_file": "said to be not documented, but found in the Case File",
                   "malformed": "a line of the answer that was not one readable statement"}


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
    r = spec(role)
    sig = rules.case_signature(case_id)  # taken before reading the records: a change during the run marks the brief stale (V1 item 4.5)
    if not specialty_documents(case_id, role)[0]:  # nothing of this specialty to read: return at once, no model call (V1 item 6.6)
        brief = no_documents_brief(case_id, role, sig, t0)
        st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
        au({"kind": "agent_no_documents", "role": role, "department": brief["department"], "open_items": len(brief["open_items"])})
        yield {"type": "brief", "brief": brief}; return
    au({"kind": "agent_start", "role": role, "focus": focus_question})
    yield {"type": "start", "role": role, "label": r["label"]}
    if focus_question:
        g = await guardrails.check_input(focus_question, au)
        if not g["allowed"]:
            yield {"type": "error", "message": g["message"], "category": g["category"]}; return
    relevant = sorted(specialty_documents(case_id, role)[0], key=lambda d: dates.doc_dates(d)["sort"], reverse=True)
    scratch = [f"Patient: {case['patient'].get('name')} ({case['patient'].get('mrn')}). Protocol: {case['protocol']}.",
               "DOCUMENTS:\n" + _doc_list(case_id),
               "VERIFIED FIELDS:\n" + _facts_text(case_id),
               "PRE-AUTHORIZATION GAPS:\n" + _gaps_text(case_id)]
    refs = {}  # guideline passages seen in this run, by id (V1 item 5.5)
    try:
        checklist = packs.checklist_text(role, case["protocol"])
    except Exception as e:  # an unreadable pack file never stops a brief: the records still are the source
        checklist = ""
        au({"kind": "agent_pack_unavailable", "role": role, "error": str(e)[:200]})
    if checklist:
        scratch.append(checklist)
    try:
        from . import discord
        dtext = discord.text(case_id)  # reports that disagree (code-found; the brief still needs quotes to restate one; 12 Oct)
        if dtext:
            scratch.append(dtext)
    except Exception as e:
        au({"kind": "agent_discordances_unavailable", "role": role, "error": str(e)[:200]})
    prot_label = (protocol.get(case["protocol"]) or {}).get("label") or case["protocol"]
    gq = f"{prot_label}: {r.get('guideline_query') or r['focus'][:80]}"
    try:
        if not guidelines.ready():  # never wait for a guideline index rebuild (minutes on CPU)
            raise RuntimeError("guideline library still loading")
        gl = await asyncio.to_thread(_search_guidelines, role, case, gq, refs)
        scratch.append(f"GUIDELINE REFERENCES (reference text from the {r['label'].lower()} pack, Indian sources first; cite by id under "
                       f"'references' of a point for review, only for what records and reports should contain; never a fact about this patient, "
                       f"never a treatment option or a recommendation for this patient):\n{gl}")
        au({"kind": "agent_tool", "role": role, "tool": "search_guidelines", "input": gq, "auto": True})
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
            if r.get("allowed_tools") and tool not in r["allowed_tools"]:  # the skill restricted this tool
                obs = f"The tool {tool} is not available to this skill (allowed: {', '.join(r['allowed_tools'])}); continue with the records."
            else:
                obs = await _tool(case_id, tool, arg, role, refs)
        except Exception as e:  # a failing tool (e.g. the guideline index not built) is an observation, not the end of the brief
            obs = f"The tool failed ({type(e).__name__}); continue with the records."
        scratch.append(f"TOOL {tool}({arg}) RESULT:\n{obs[:READ_CAP]}")
        au({"kind": "agent_tool", "role": role, "tool": tool, "input": arg})
        yield {"type": "step", "tool": tool, "input": arg, "thought": s.get("thought", ""), "observation": obs[:600]}
    msgs = [{"role": "system", "content": _system(role)},
            {"role": "user", "content": "\n\n".join(scratch) + f"\n\nTASK: {task}\nWrite the brief now: 3 to 5 sections with short factual items "
             "(each with citations), points for review (questions about the records for the board, each with citations, and with references "
             "to guideline passages above about what the records or reports should contain, by id with an exact quote of at least a full "
             "phrase, Indian sources first; never a passage about treatment, indications or eligibility; an empty list when none "
             "applies), and anything relevant to this specialty that is not documented."}]
    try:
        b = await llm.chat("reasoner", msgs, json_schema=BRIEF_SCHEMA, max_tokens=2200, purpose=f"agent {role} brief", audit=au)
    except Exception as e:
        yield {"type": "error", "message": str(e)[:200]}; return
    dropped = 0; issues = []; removed = []  # removed: every item taken out, with the reason (V1 item 6.4)
    near = config.near_match()  # approximate quotes kept, flagged "check source", only behind TB_NEAR_MATCH (V1 item 6.5)
    sections = []
    for sec in b.get("sections") or []:
        items, drop = qa.verify(case_id, sec.get("items"), near_match=near)
        dropped += len(drop); removed += [{**x, "where": sec.get("heading", "")} for x in drop]
        kept = []
        for it in items:
            iss = guardrails.scan_output(it["text"])
            if iss:
                issues += iss; removed.append(_removed(it, "guardrail", "; ".join(i["reason"] for i in iss), sec.get("heading", "")))
            else:
                kept.append(it)
        if kept:
            sections.append({"heading": sec.get("heading", ""), "items": kept})
    pts2, refs_dropped = [], 0
    for raw in b.get("points_for_review") or []:
        v, drop = qa.verify(case_id, [raw], near_match=near)  # one at a time: each kept point keeps its own references
        if not v:
            dropped += 1; removed += [{**x, "where": "points_for_review"} for x in drop]; continue
        p = v[0]
        iss = guardrails.scan_output(p["text"])
        if not iss and _POINT_SCOPE.search(p["text"]):
            iss = [{"sentence": p["text"], "reason": "asks for a treatment or work-up decision for this patient"}]
        issues += iss
        if iss:
            removed.append(_removed(p, "guardrail", "; ".join(i["reason"] for i in iss), "points_for_review"))
            continue
        p["references"], nd_refs = _verify_references(raw.get("references"), refs, case["protocol"])
        refs_dropped += nd_refs
        if not any(x["region"] == "India" for x in p["references"]) and guidelines.ready():  # an Indian source whenever one fits
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
        iss = guardrails.scan_output(x)
        if iss:
            removed.append(_removed({"text": x}, "guardrail", "; ".join(i["reason"] for i in iss), "not_documented")); continue
        hits = search.find_values(case_id, x, 5)["hits"]  # the claim 'X is not documented' is checked against the Case File
        if hits:
            nd_dropped += 1
            removed.append(_removed({"text": x}, "found_in_case_file", "a line mentions it in " + ", ".join(sorted({h["doc_id"] for h in hits[:3]})), "not_documented"))
            au({"kind": "not_documented_claim_rejected", "role": role, "claim": x, "found_in": [h["doc_id"] for h in hits[:3]]})
        else:
            nd.append(x)
    if issues:
        au({"kind": "guardrail_output", "where": f"agent {role}", "issues": issues})
    brief = {"role": role, "label": r["label"], "sections": sections, "points_for_review": pts2, "not_documented": nd,
             "dropped_unverified": dropped, "guardrail_removed": sum(x["reason"] == "guardrail" for x in removed), "not_documented_rejected": nd_dropped,
             "removed": removed, "near_match": near, "generated": store.now_iso(),
             "approximate": sum(bool(it.get("approximate")) for s_ in sections for it in s_["items"]) + sum(bool(p.get("approximate")) for p in pts2),
             "references_dropped": refs_dropped, "pack": _pack_summary(role, case["protocol"]),
             "model": config.models()["reasoner"].get("label") or "reasoner",
             "seconds": round(time.time() - t0, 1), "review": {"status": "ai_draft"},
             "signature": sig,  # what it was written from; a changed Case File marks it stale (V1 item 4.5)
             "version": BRIEF_VERSION, "focus": focus_question,
             "skill": {"origin": r.get("skill_origin", "code"), "sha": r.get("skill_sha", "")}}  # which role definition wrote it
    st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
    au({"kind": "agent_brief", "role": role, "items": sum(len(s["items"]) for s in sections), "points": len(pts2), "dropped_unverified": dropped,
        "guardrail_removed": brief["guardrail_removed"], "removed": {k: sum(x["reason"] == k for x in removed) for k in sorted({x["reason"] for x in removed})},
        "approximate": brief["approximate"], "seconds": brief["seconds"], "references": sum(len(p["references"]) for p in pts2),
        "points_with_indian_reference": sum(any(x["region"] == "India" for x in p["references"]) for p in pts2), "references_dropped": refs_dropped})
    yield {"type": "brief", "brief": brief}


async def prepare(case_id, role, focus_question="", max_steps=5):
    """Run the agent to the end, for a preparation in the background (18 Oct: the Specialty helpers of the fill-in summary and the ready
    hook): the brief it wrote (also saved under state.artefacts.brief_<role> by run_agent), or the error it stopped on."""
    brief, err, steps = None, None, 0
    async for ev in run_agent(case_id, role, focus_question, max_steps):
        if ev.get("type") == "brief":
            brief = ev.get("brief")
        elif ev.get("type") == "error":
            err = ev.get("message") or "The agent wrote no brief"
        elif ev.get("type") == "step":
            steps += 1
    return {"role": role, "brief": brief, "error": None if brief else (err or "The agent wrote no brief"), "steps": steps}


def fresh(art, sig) -> bool:
    """A stored brief still stands for the Case File (the rule service._prepare_one reuses): same Case File signature, current format,
    no focus question, same near-match setting."""
    if not isinstance(art, dict) or not art.get("signature") or not isinstance(sig, dict):
        return False
    return (not rules.stale_reason(art["signature"], sig) and art.get("version") == BRIEF_VERSION and not art.get("focus")
            and bool(art.get("near_match")) == config.near_match())


# V1 item 6.2: the agent of an absent specialty answers the board's questions live, from the Case File records and its guideline pack.
# Night-v3 item 6.3: with a callback the answer streams statement by statement, each one verified and scanned before it is passed on.
LIVE_LABEL = "AI agent, support only"
LIVE_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "answer_found": {"type": "boolean"},
    "statements": qa.ANSWER_SCHEMA["properties"]["statements"],
    "references": POINT["properties"]["references"]}, "required": ["answer_found", "statements", "references"]}
NOT_DOCUMENTED = "Not documented in the Case File. No statement could be verified against the source documents."
REFERENCE_ONLY = "Not documented about this patient. The guideline passages below are reference text, not about this patient."
HISTORY_MESSAGES = 6  # three exchanges of the shared thread (research 05_board_agents.md section 6.5)

# the document type in the outside-specialty note, with its article ("This is an MRI record; ...")
DOC_TYPE_PHRASES = {"ct": "a CT", "mri": "an MRI", "xray": "an X-ray", "ultrasound": "an ultrasound", "mammogram": "a mammogram", "pet_ct": "a PET-CT",
                    "bone_scan": "a bone scan", "histopathology": "a histopathology", "cytology": "a cytology", "ihc": "an IHC", "molecular": "a molecular",
                    "lab": "a lab", "clinical_note": "a clinical note", "referral": "a referral", "discharge_summary": "a discharge summary",
                    "treatment_summary": "a treatment summary", "tumour_board_record": "a Tumour Board", "endoscopy": "an endoscopy",
                    "operative_note": "an operative note"}
_UNKNOWN_TYPES = {"", "unknown", "other"}


def _live_system(role):
    sys_ = _system(role)
    brief = "you prepare a specialty-specific brief from the Case File records for the multidisciplinary team"
    return (sys_.replace(brief, "you answer the multidisciplinary team's questions from the Case File records")
            + " Now the board asks you a question during the meeting. Answer ONLY from the documents provided, in short factual statements; "
            "copy values exactly; every statement cites the document id and an exact quote copied character for character. If the documents "
            "do not contain the answer, set answer_found=false and return no statements. Guideline passages (G1, G2 ...) go under 'references' "
            "only when they say what a report or record should contain, never as an answer about this patient.")


STREAM_FORMAT = (" Write the answer as JSON Lines: one JSON object on each line and nothing else (no prose, no code fences, no list brackets). "
                 'Each statement is one line: {"text": "<one short factual statement>", "citations": [{"doc_id": "<document id>", '
                 '"quote": "<exact text copied from that document>"}]}. The last line is always: {"end": true, "answer_found": true or false, '
                 '"references": [{"ref_id": "G1", "quote": "<exact text copied from that guideline passage>"}]}. If the documents do not '
                 "contain the answer, write only the last line, with answer_found false.")


def _live_stream_system(role):
    """The live prompt with the line protocol of the streamed answer (llm.stream takes no schema, so the format is in the prompt)."""
    return _live_system(role).replace("set answer_found=false and return no statements", "write no statement line") + STREAM_FORMAT


def _type_phrase(t):
    return DOC_TYPE_PHRASES.get(t) or (("an " if t[:1] in "aeiou" else "a ") + t.replace("_", " "))


def _note_maker(case_id, role):
    """note(statement) -> the fixed line for a statement whose first cited record lies outside the role's document types ("This is a CT
    record; the Radiology agent can say more.", the first role in ROLES order that reads that type), or None: a type of the role, an
    unknown type, or a type no role reads. Written by code, never by the model; shown, never spoken. The documents are read once."""
    cache = {}

    def note(stmt):
        if not cache:
            cache["types"] = {d["doc_id"]: (d.get("classification") or {}).get("doc_type") or "" for d in rules.case_docs(case_id)}
            cache["specs"] = {x: spec(x) for x in ROLES}
        c = next((c for c in stmt.get("citations") or [] if isinstance(c, dict) and c.get("doc_id")), None)
        t = cache["types"].get(c["doc_id"], "") if c else ""
        if t in _UNKNOWN_TYPES or t in cache["specs"][role]["doc_types"]:
            return None
        owner = next((x for x in ROLES if t in cache["specs"][x]["doc_types"]), None)
        return f"This is {_type_phrase(t)} record; the {cache['specs'][owner]['department']} agent can say more." if owner else None
    return note


def _screen(case_id, statements, note):
    """Statements as the model wrote them -> (kept, removed, unverified count): exact quotes only (qa.verify, as in Ask the Case File), then
    the scope guardrail on each kept text; a kept statement outside the specialty gains its note."""
    stmts, drop = qa.verify(case_id, statements)
    removed, kept = [{**x, "where": "answer"} for x in drop], []
    for st_ in stmts:
        iss = guardrails.scan_output(st_["text"])
        if iss:
            removed.append(_removed(st_, "guardrail", "; ".join(i["reason"] for i in iss), "answer"))
            continue
        n = note(st_)
        kept.append({**st_, "note": n} if n else st_)
    return kept, removed, len(drop)


def _statement(obj):
    """A statement object of the line protocol, cleaned ({text, citations[dict]}), or None when it is not one."""
    if not isinstance(obj, dict) or not isinstance(obj.get("text"), str) or not obj["text"].strip() or not isinstance(obj.get("citations"), list):
        return None
    return {"text": obj["text"], "citations": [c for c in obj["citations"] if isinstance(c, dict)]}


def _parse_line(line):
    """One line of the streamed answer -> ("skip", None) for a blank line or a code fence, ("statement", {text, citations}), ("end", obj),
    ("whole", obj) for one LIVE_SCHEMA object written on a line, or ("malformed", None)."""
    s = line.strip()
    if not s or s.startswith("```") or s in ("[", "]"):
        return "skip", None
    try:
        obj = json.loads(s.rstrip(",").strip())
    except ValueError:
        return "malformed", None
    if isinstance(obj, dict) and obj.get("end") is True:
        return "end", obj
    if isinstance(obj, dict) and isinstance(obj.get("statements"), list):
        return "whole", obj
    st_ = _statement(obj)
    return ("statement", st_) if st_ else ("malformed", None)


class _Refused(Exception):
    """The scope check refused the question while the answer was streaming."""


async def _call(fn, *args):
    r = fn(*args)
    if inspect.isawaitable(r):
        await r


async def _streamed_answer(case_id, role, smsgs, msgs, au, scope_task, note, on_statement, t0):
    """The streamed answer (night-v3 item 6.3): one JSON object per line; each complete statement line is verified and scanned on its own
    and only a kept statement reaches on_statement(statement, index), in order; the first one waits for the scope check (a refusal closes
    the stream and nothing is passed on). A stream with no readable statement or end line falls back to the one-shot call (never a second
    stream after a statement went out). A stream that fails halfway is not restarted: the statements passed on stand, the error rises.
    Returns {gate, kept, removed, dropped, end, first, streamed, malformed}."""
    out = {"gate": None, "kept": [], "removed": [], "dropped": 0, "end": None, "first": None, "streamed": True, "malformed": 0}
    seen = False

    async def take(raw):
        if out["gate"] is None:
            out["gate"] = await scope_task
            if not out["gate"]["allowed"]:
                raise _Refused
        kept, removed, dropped = _screen(case_id, [raw], note)
        out["removed"] += removed; out["dropped"] += dropped
        for s in kept:
            if out["first"] is None:
                out["first"] = round(time.time() - t0, 2)
            await _call(on_statement, s, len(out["kept"]))
            out["kept"].append(s)

    async def line(text):
        nonlocal seen
        kind, obj = _parse_line(text)
        if kind == "malformed":
            out["malformed"] += 1
            out["removed"].append(_removed({"text": text.strip()[:200]}, "malformed", "not one JSON object on its line", "answer"))
        elif kind == "statement":
            seen = True
            await take(obj)
        elif kind == "whole":
            seen = True
            for raw in obj["statements"]:
                st_ = _statement(raw)
                if st_:
                    await take(st_)
            out["end"] = {"answer_found": obj.get("answer_found"), "references": obj.get("references")}
        elif kind == "end":
            seen = True
            out["end"] = obj

    agen = llm.stream("reasoner", smsgs, max_tokens=1200, audit=au)
    try:
        buf = ""
        async for chunk in agen:
            buf += chunk or ""
            while "\n" in buf and out["end"] is None:
                text, buf = buf.split("\n", 1)
                await line(text)
            if out["end"] is not None:
                break  # nothing after the end line is read
        if out["end"] is None and buf.strip():
            await line(buf)  # the last line without a final newline
        if out["gate"] is None:
            out["gate"] = await scope_task
            if not out["gate"]["allowed"]:
                raise _Refused
        if not seen:  # nothing readable came: the one-shot call, its statements through the same checks and the callback
            out["streamed"] = False
            a = await llm.chat("reasoner", msgs, json_schema=LIVE_SCHEMA, max_tokens=1200, purpose=f"agent {role} live answer", audit=au)
            for raw in a.get("statements") or []:
                st_ = _statement(raw)
                if st_:
                    await take(st_)
            out["end"] = {"answer_found": a.get("answer_found"), "references": a.get("references")}
    except _Refused:
        out["kept"], out["streamed"] = [], False
    except Exception as e:
        au({"kind": "agent_answer_failed", "role": role, "statements": len(out["kept"]), "error": f"{e.__class__.__name__}: {str(e)[:200]}"})
        raise
    finally:
        if not scope_task.done():
            scope_task.cancel()
        if hasattr(agen, "aclose"):
            await agen.aclose()  # a refusal or an end line stops the model's stream
    return out


async def ask(case_id, role, question, history=None, user="", on_statement=None):
    """One live question to the agent of `role` (V1 item 6.2): scope check first (a refused question gets no answer), the Case File
    records and the specialty pack as context, every statement verified against its quote (exact only, like Ask the Case File), the scope
    guardrail on the output, references verified verbatim and limited to record and report contents. Returns the answer record.
    With on_statement (night-v3 item 6.3) the answer is streamed and each kept statement is passed on as soon as it is verified (a plain
    function or a coroutine function, called with the statement and its index); the record then says `streamed` and `first_seconds`."""
    if role not in ROLES:
        raise ValueError("unknown role")
    t0, au, r = time.time(), store.auditor(case_id), spec(role)
    case = store.get_case(case_id)
    base = {"role": role, "label": r["label"], "kind": LIVE_LABEL, "question": question, "statements": [], "references": [], "removed": [],
            "dropped_unverified": 0, "model": config.models()["reasoner"].get("label") or "reasoner", "streamed": False, "first_seconds": None}
    if not case.get("protocol"):
        return {**base, "status": "not_listed", "message": NOT_LISTED, "seconds": round(time.time() - t0, 2)}
    au({"kind": "agent_question", "role": role, "question": question, "by": user})

    def refused(gate):
        au({"kind": "guardrail_input", "where": f"agent {role}", "category": gate["category"], "layer": gate["layer"]})
        return {**base, "status": "out_of_scope", "category": gate["category"], "message": gate["message"], "seconds": round(time.time() - t0, 2)}

    hit = guardrails.rule_check(question)
    scope_task = asyncio.create_task(guardrails.check_input(question, au))
    if hit:  # refused by rule: no retrieval and no answer call
        return refused(await scope_task)
    values = await asyncio.to_thread(search.find_values, case_id, question)
    context, mode = await asyncio.to_thread(search.context_for, case_id, question, 40000)
    extra = ""  # the question-dependent part (matching lines, guideline passages): the documents block stays a stable prefix (item 6.4)
    if values["hits"]:
        extra += "\n\n=== LINES MATCHING THE QUESTION (for convenience; cite the document) ===\n" + \
                   "\n".join(f"[{h['doc_id']} | {h['date'] or '?'}] {h['text']}" for h in values["hits"][:25])
    refs = {}
    if guidelines.ready():  # never wait for a guideline index rebuild; the records alone still answer
        try:
            gl = await asyncio.to_thread(_search_guidelines, role, case, question, refs)
            extra += f"\n\n=== GUIDELINE REFERENCES ({r['label'].lower()} pack, Indian sources first; reference text, never a fact about this patient) ===\n{gl}"
        except Exception as e:
            au({"kind": "agent_guidelines_unavailable", "role": role, "error": str(e)[:200]})
    turns = []
    for h in (history or [])[-HISTORY_MESSAGES:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            turns.append({"role": h["role"], "content": h["content"][:2000]})
    # The documents first, the same text every question of this Case File sends (warm() pre-loads it when the case comes on the floor),
    # then the thread's turns, then the question with its matching lines and guideline passages.
    docs_msg = {"role": "user", "content": f"DOCUMENTS:\n{context}"}
    asked = {"role": "user", "content": f"{extra.strip()}\n\nQUESTION FROM THE BOARD: {question}".strip()}
    msgs = [{"role": "system", "content": _live_system(role)}, docs_msg, *turns, asked]
    reference_q = guardrails.reference_check(question)  # reference text is kept even when no statement about the patient survives
    note = _note_maker(case_id, role)
    malformed = 0
    if on_statement is None:
        answer_task = asyncio.create_task(llm.chat("reasoner", msgs, json_schema=LIVE_SCHEMA, max_tokens=1200, purpose=f"agent {role} live answer", audit=au))
        gate = await scope_task
        if not gate["allowed"]:
            answer_task.cancel()
            return refused(gate)
        a = await answer_task
        kept, removed, dropped = _screen(case_id, a.get("statements"), note)
        raw_refs, streamed, first = a.get("references"), False, None
    else:
        smsgs = [{"role": "system", "content": _live_stream_system(role)}, docs_msg, *turns, asked]
        s = await _streamed_answer(case_id, role, smsgs, msgs, au, scope_task, note, on_statement, t0)
        if not s["gate"]["allowed"]:
            return refused(s["gate"])
        kept, removed, dropped, streamed, first, malformed = s["kept"], s["removed"], s["dropped"], s["streamed"], s["first"], s["malformed"]
        raw_refs = (s["end"] or {}).get("references")
    raw_refs = [x for x in raw_refs if isinstance(x, dict)] if isinstance(raw_refs, list) else []
    if any(x["reason"] == "guardrail" for x in removed):
        au({"kind": "guardrail_output", "where": f"agent {role} live answer", "issues": [x["text"] for x in removed if x["reason"] == "guardrail"]})
    references, refs_dropped = _verify_references(raw_refs, refs, case["protocol"]) if (kept or reference_q) else ([], len(raw_refs))
    references.sort(key=lambda x: x["region"] != "India")  # references only beside a verified answer: never guideline text as the answer
    seconds = round(time.time() - t0, 2)
    out = {**base, "status": "answered" if kept else "not_documented", "statements": kept, "references": references, "removed": removed,
           "dropped_unverified": dropped, "references_dropped": refs_dropped, "mode": mode, "answered_at": store.now_iso(),
           "message": "" if kept else (REFERENCE_ONLY if references else NOT_DOCUMENTED), "reference_question": reference_q, "seconds": seconds, "streamed": streamed,
           "first_seconds": (first if on_statement is not None else seconds) if kept else None}
    au({"kind": "agent_answer", "role": role, "by": user, "status": out["status"], "statements": len(kept), "dropped_unverified": dropped,
        "guardrail_removed": sum(x["reason"] == "guardrail" for x in removed), "references": len(references), "seconds": out["seconds"],
        "streamed": streamed, "first_seconds": out["first_seconds"], "malformed": malformed})
    return out


# night-v3 item 6.4: the context pre-loaded when a Case File comes on the floor
_WARM: dict = {}  # (case_id, role) -> the Case File signature hash the reasoner's cache holds the documents for
WARM_PURPOSE = "agent warm"


async def warm(case_id, role):
    """Pre-load an agent's context when its Case File comes on the floor (night-v3 item 6.4): the documents block of the live prompt, the
    same text the next question of this Case File sends first, goes to the reasoner once with one output token so its prefix cache holds
    it (vLLM keeps prefixes by default); the search caches warm on the way. Once per Case File signature and role. Nothing is shown;
    audited as an llm_call with purpose "agent warm". Returns the seconds taken, or None when skipped or failed."""
    if role not in ROLES:
        raise ValueError("unknown role")
    case = store.get_case(case_id)
    if not case or not case.get("protocol"):
        return None
    sig = rules.case_signature(case_id)["hash"]
    if _WARM.get((case_id, role)) == sig:
        return None
    t0, au = time.time(), store.auditor(case_id)
    context, mode = await asyncio.to_thread(search.context_for, case_id, "", 40000)
    msgs = [{"role": "system", "content": _live_stream_system(role)}, {"role": "user", "content": f"DOCUMENTS:\n{context}"}]
    try:
        await llm.chat("reasoner", msgs, max_tokens=1, purpose=WARM_PURPOSE, audit=au)
    except Exception as e:
        au({"kind": "agent_warm_failed", "role": role, "error": f"{e.__class__.__name__}: {str(e)[:120]}"})
        return None
    _WARM[(case_id, role)] = sig
    secs = round(time.time() - t0, 2)
    au({"kind": "agent_warm", "role": role, "seconds": secs, "mode": mode, "chars": len(context)})
    return secs
