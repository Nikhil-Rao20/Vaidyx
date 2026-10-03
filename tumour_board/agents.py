"""Role-specific AI support agents for the Tumour Board.

When a specialist is unavailable, the corresponding agent prepares a specialty-specific brief from the Case File
records: what the signed reports document, what is pending or missing, discrepancies between documents, and points
the board may want to clarify. It does not interpret images, diagnose, stage or recommend treatment; every item
carries a verified quote; the brief stays an AI draft until an expert marks it reviewed (expert-in-the-loop).

Agent loop (ReAct style, model-agnostic, JSON steps): observe -> choose a tool -> read the result -> ... -> write
the brief. Tools only read the Case File.
"""
import asyncio, json, time

from . import guardrails, llm, protocol, qa, rules, search, store

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

TOOLS_DOC = """Tools (all read-only):
- list_documents: no input. Lists every document with id, title, type, date, status.
- read_document: input = a document id. Returns the full text of that document.
- search: input = a question or keywords. Returns the most relevant passages from all documents.
- find_values: input = a term (for example 'PD-L1', 'CEA', 'Ki-67'). Returns every line in the Case File that mentions it, with dates.
- get_facts: no input. Returns the primary fields already extracted and verified by the system.
- get_gaps: no input. Returns the Pre-Authorization gaps (missing, pending or non-final records).
- finish: no input. Use when you have read enough to write the brief."""

STEP_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "thought": {"type": "string", "description": "one short sentence: what you still need"},
    "tool": {"type": "string", "enum": ["list_documents", "read_document", "search", "find_values", "get_facts", "get_gaps", "finish"]},
    "input": {"type": "string"}}, "required": ["thought", "tool", "input"]}

ITEM = {"type": "object", "additionalProperties": False, "properties": {
    "text": {"type": "string"},
    "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string", "description": "exact text copied from that document"}},
                  "required": ["doc_id", "quote"]}}}, "required": ["text", "citations"]}
BRIEF_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sections": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "properties": {"heading": {"type": "string"}, "items": {"type": "array", "items": ITEM}}, "required": ["heading", "items"]}},
    "points_for_review": {"type": "array", "items": ITEM, "description": "questions or clarifications for the board (never treatment recommendations)"},
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
            "never recommendations. Your output is a draft for expert review.")


def _doc_list(case_id):
    rows = []
    for d in store.list_docs(case_id):
        c = d.get("classification") or {}
        rows.append(f"{d['doc_id']} | {c.get('title') or d['filename']} | {c.get('doc_type')} | {c.get('report_date_iso') or '?'} | {c.get('status')}"
                    + (" | unsigned" if c.get("signed") == "no" else ""))
    return "\n".join(rows)


def _facts_text(case_id):
    facts = rules.resolve_facts(store.list_docs(case_id))
    cat = protocol.facts()
    lines = []
    for fid, f in facts.items():
        for h in f["history"]:
            if h["verification"] == "verified":
                lines.append(f"{cat.get(fid, {}).get('label', fid)}: {h['value']}  [{h['doc_id']} {h['doc_title']} {h['date'] or ''} {h['doc_status']}]")
    return "\n".join(lines) or "(none)"


def _gaps_text(case_id):
    g = store.get_state(case_id).get("gate") or rules.evaluate(case_id)
    return "\n".join(f"- {r['label']} ({r['department']}): {r['status']}. {'; '.join(r['problems'])}" for r in g["requirements"] if r["status"] != "satisfied") or "(no gaps)"


async def _tool(case_id, tool, arg):
    if tool == "list_documents":
        return _doc_list(case_id)
    if tool == "read_document":
        d = store.get_doc(case_id, arg.strip().split()[0]) if arg.strip() else None
        if not d:
            return "No document with that id. Use list_documents."
        return "\n".join(p["text"] for p in d.get("pages") or [])[:7000]
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


async def run_agent(case_id, role, focus_question="", max_steps=5):
    """Async generator of events: {"type": "start"|"step"|"brief"|"error", ...}."""
    if role not in ROLES:
        yield {"type": "error", "message": "unknown role"}; return
    au = store.auditor(case_id)
    t0 = time.time()
    case = store.get_case(case_id)
    r = ROLES[role]
    au({"kind": "agent_start", "role": role, "focus": focus_question})
    yield {"type": "start", "role": role, "label": r["label"]}
    if focus_question:
        g = await guardrails.check_input(focus_question, au)
        if not g["allowed"]:
            yield {"type": "error", "message": g["message"], "category": g["category"]}; return
    relevant = [d for d in store.list_docs(case_id) if (d.get("classification") or {}).get("doc_type") in r["doc_types"]]
    scratch = [f"Patient: {case['patient'].get('name')} ({case['patient'].get('mrn')}). Protocol: {case['protocol']}.",
               "DOCUMENTS:\n" + _doc_list(case_id),
               "VERIFIED FIELDS:\n" + _facts_text(case_id),
               "PRE-AUTHORIZATION GAPS:\n" + _gaps_text(case_id)]
    # documents of this specialty are read up front (Case Files are small; fewer tool calls = faster)
    for d in relevant[:6]:
        scratch.append(f"DOCUMENT {d['doc_id']} (read):\n" + "\n".join(p["text"] for p in d.get("pages") or [])[:6000])
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
        obs = await _tool(case_id, tool, arg)
        scratch.append(f"TOOL {tool}({arg}) RESULT:\n{obs[:6000]}")
        au({"kind": "agent_tool", "role": role, "tool": tool, "input": arg})
        yield {"type": "step", "tool": tool, "input": arg, "thought": s.get("thought", ""), "observation": obs[:600]}
    msgs = [{"role": "system", "content": _system(role)},
            {"role": "user", "content": "\n\n".join(scratch) + f"\n\nTASK: {task}\nWrite the brief now: 3 to 5 sections with short factual items "
             "(each with citations), points for review (questions about the records for the board, each with citations), and anything relevant "
             "to this specialty that is not documented."}]
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
    pts = qa.verify_statements(case_id, b.get("points_for_review"))
    dropped += len(b.get("points_for_review") or []) - len(pts)
    pts2 = []
    for p in pts:
        iss = guardrails.scan_output(p["text"])
        issues += iss
        if not iss:
            pts2.append(p)
    nd = [x for x in (b.get("not_documented") or []) if not guardrails.scan_output(x)]
    if issues:
        au({"kind": "guardrail_output", "where": f"agent {role}", "issues": issues})
    brief = {"role": role, "label": r["label"], "sections": sections, "points_for_review": pts2, "not_documented": nd,
             "dropped_unverified": dropped, "guardrail_removed": len(issues), "generated": store.now_iso(),
             "model": __import__("tumour_board.config", fromlist=["models"]).models()["reasoner"].get("label") or "reasoner",
             "seconds": round(time.time() - t0, 1), "review": {"status": "ai_draft"}}
    st = store.get_state(case_id); st.setdefault("artefacts", {})[f"brief_{role}"] = brief; store.save_state(case_id, st)
    au({"kind": "agent_brief", "role": role, "items": sum(len(s["items"]) for s in sections), "points": len(pts2), "dropped_unverified": dropped,
        "guardrail_removed": len(issues), "seconds": brief["seconds"]})
    yield {"type": "brief", "brief": brief}
