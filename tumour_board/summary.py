"""Case File summary: a concise narrative for the board, compiled once the Pre-Authorization gate is met.
Every sentence carries verified quotes; stage appears only as recorded in a signed report (copied, never derived)."""
import time

from . import config, guardrails, llm, protocol, qa, rules, search, store

SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "paragraph": {"type": "integer", "description": "1 = presentation and clinical history, 2 = investigations and findings"},
        "text": {"type": "string"},
        "citations": qa.ANSWER_SCHEMA["properties"]["statements"]["items"]["properties"]["citations"]},
        "required": ["paragraph", "text", "citations"]}, "description": "8 to 14 short sentences"},
    "points_for_review": {"type": "array", "items": qa.ANSWER_SCHEMA["properties"]["statements"]["items"],
                          "description": "items to clarify at the board: pending results, superseded or discordant reports (not recommendations)"}},
    "required": ["sentences", "points_for_review"]}

SYS = ("You compile the Case File summary for a Tumour Board from signed clinical records. Write like a careful registrar presenting "
       "a case: concise, factual, chronological. Attribute every finding to its source report (for example 'The PET/CT report records ...'). "
       "Copy values exactly. Cite each sentence with the document id and an exact quote. Do not diagnose, interpret images, derive or assign "
       "stage, recommend treatment or predict prognosis. If a stage is mentioned, quote it exactly as recorded in the report that records it.")


async def build(case_id, force=False):
    t0 = time.time()
    au = store.auditor(case_id)
    st = store.get_state(case_id)
    gate = st.get("gate") or rules.evaluate(case_id)
    if not gate.get("passed") and not force:
        return {"status": "gate_not_met", "message": "The Case File summary is compiled once every Pre-Authorization check is met.",
                "open": [r["label"] for r in gate["requirements"] if r["status"] not in ("satisfied", "not_applicable")]}
    case = store.get_case(case_id)
    full = search.case_text(case_id, 60000) or ""
    facts = rules.resolve_facts(store.list_docs(case_id))
    stage = facts.get("recorded_stage", {}).get("current")
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": f"Patient: {case['patient'].get('name')}, {case['patient'].get('agesex', '')}.\n\nDOCUMENTS:\n{full}\n\n"
             "Write the Case File summary: paragraph 1 = presentation, clinical history and performance status; paragraph 2 = imaging, "
             "pathology and biomarker findings as recorded, in date order. Prefer FINAL signed reports; mention when a report is draft, "
             "preliminary or superseded. Keep each quote short (the line that carries the value). Then list points for review."}]
    r = await llm.chat("reasoner", msgs, json_schema=SCHEMA, max_tokens=3500, purpose="case file summary", audit=au)
    grouped = {}
    for x in r.get("sentences") or []:
        grouped.setdefault(int(x.get("paragraph") or 1), []).append(x)
    paras, dropped, removed = [], 0, []
    for _, p in sorted(grouped.items()):
        ok = qa.verify_statements(case_id, p)
        dropped += len(p) - len(ok)
        keep = []
        for s in ok:
            iss = guardrails.scan_output(s["text"])
            (removed.extend(iss) if iss else keep.append(s))
        if keep:
            paras.append(keep)
    pts = [s for s in qa.verify_statements(case_id, r.get("points_for_review")) if not guardrails.scan_output(s["text"])]
    out = {"status": "ready" if gate.get("passed") else "incomplete_gate", "paragraphs": paras, "points_for_review": pts,
           "stage_as_recorded": ({"value": stage["value"], "quote": stage["quote"], "doc_id": stage["doc_id"], "doc_title": stage["doc_title"], "date": stage["date"]}
                                 if stage and stage["verification"] == "verified" else None),
           "dropped_unverified": dropped, "guardrail_removed": len(removed), "generated": store.now_iso(), "seconds": round(time.time() - t0, 1),
           "model": config.models()["reasoner"].get("label") or "reasoner", "review": {"status": "ai_draft"}, "gate_passed": gate.get("passed")}
    if removed:
        au({"kind": "guardrail_output", "where": "summary", "issues": removed})
    st = store.get_state(case_id); st.setdefault("artefacts", {})["summary"] = out; store.save_state(case_id, st)
    au({"kind": "summary", "sentences": sum(len(p) for p in paras), "dropped_unverified": dropped, "seconds": out["seconds"]})
    return out
