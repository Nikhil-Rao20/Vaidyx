"""Case File summary: a concise narrative for the board, compiled once the Pre-Authorization gate is met.
Every sentence carries verified quotes; stage appears only as recorded in a signed report (copied, never derived)."""
import time

from . import config, discord, grounding, guardrails, llm, protocol, qa, rules, search, store, units

# Verified facts that belong to each NCG section. If the model's sentences for a section are dropped (or it wrote none), these
# facts are added as plain, cited sentences, so a section only says "not documented" when nothing verified exists for it.
SECTION_FACTS = {
    "presentation": ["presenting_complaint", "diagnosis_date_mode", "smoking_history", "tobacco_use", "menopausal_status", "comorbidities"],
    "treatment_history": ["treatment_received", "treatment_completion_date"],
    "investigations": ["histologic_type", "grade", "lvi", "margins", "depth_of_invasion", "pni", "ene", "pdl1", "egfr", "alk", "ros1", "kras", "er", "pr", "her2",
                       "ki67", "mmr", "ras_braf", "cea"],
    "imaging": ["lesion_size", "nodal_findings", "distant_findings", "comparison_prior", "suv_max", "recorded_stage", "figo_stage", "parametrial_involvement",
                "distance_from_anal_verge", "mrf_status", "emvi"],
    "fitness": ["ecog", "comorbidities", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "hiv_status", "dental_evaluation"],
    "questions": ["clinical_question", "patient_preference"],
}


def _covered(value, text):
    v, t = grounding.norm(value).strip(" .,;:"), grounding.norm(text)
    if v and v in t:
        return True
    nums = grounding.numbers(value)
    # every number present as is or as the same quantity in other units ('2.45 lakhs/cumm' = '245 x10^3/uL'; V1 item 3.5)
    return bool(nums) and units.numbers_equivalent(value, text) and any(w in t for w in v.split() if len(w) > 3)


def fill_from_facts(sections, facts, cat, diffs=None):
    """Append cited sentences built from verified current facts that the model's verified sentences do not already carry.
    A value a clinician confirmed (V1 item 2.2) has no quote of its own: its sentence names who confirmed it and carries no citation.
    `diffs` (discord.open_differences, night-v3 item 1.5): a fact whose two reports differ and wait on the treating doctor's check gets one
    line with both values and both quotes instead of the single value (a fact no section lists goes under the investigations)."""
    added = 0
    diffs = diffs or {}
    placed = {fid for sec in sections for fid in SECTION_FACTS.get(sec["id"], [])}
    for sec in sections:
        # an approximate sentence (V1 item 6.5) never stands in for the exact one: the print view leaves it out until reviewed
        have = " ".join(x["text"] + " " + " ".join(c["quote"] for c in x["citations"]) for x in sec["sentences"] if not x.get("approximate"))
        extra = [f for f in diffs if f not in placed] if sec["id"] == "investigations" else []
        for fid in SECTION_FACTS.get(sec["id"], []) + extra:
            if fid in diffs:
                if not any(x.get("differ") and x.get("fact_id") == fid for x in sec["sentences"]):
                    sec["sentences"].append(discord.summary_sentence(diffs[fid])); added += 1
                continue
            cur = (facts.get(fid) or {}).get("current")
            if not cur or cur["verification"] not in rules.VERIFIED or cur["state"] != "present" or not cur.get("doc_final"):
                continue
            confirmed = cur.get("confirmed_by") or ("clinician" if cur["verification"] == "confirmed" else "")
            if not confirmed and not cur.get("location"):
                continue
            if _covered(cur["value"], have):
                continue
            label = cat.get(fid, {}).get("label", fid)
            if confirmed:
                sec["sentences"].append({"text": f"{label}: {cur['value']} (confirmed by {confirmed} against the {cur['doc_title']}, {cur['date'] or 'date not stated'}; no quote).",
                                         "citations": [], "from_fields": True, "confirmed_by": confirmed})
                have += " " + cur["value"]; added += 1
                continue
            loc = cur["location"]
            sec["sentences"].append({"text": f"{label}: {cur['value']} (as recorded in the {cur['doc_title']}, {cur['date'] or 'date not stated'}).",
                                     "citations": [{"doc_id": cur["doc_id"], "quote": cur["quote"], "page": loc["page"], "start": loc["start"], "end": loc["end"],
                                                    "doc_title": cur["doc_title"], "date": cur["date"], "status": cur.get("doc_status"),
                                                    **({"source_method": cur["source_method"]} if cur.get("source_method") else {})}], "from_fields": True})
            have += " " + cur["value"]; added += 1
    return added

# Section structure follows the National Cancer Grid (India) Virtual Tumour Board case template (6 slides).
SECTIONS = [("presentation", "Presenting complaints and examination"), ("treatment_history", "Treatment history"),
            ("investigations", "Investigations: histopathology, IHC, molecular, tumour markers"), ("imaging", "Imaging"),
            ("fitness", "Fitness for treatment: performance status, comorbidities, laboratory values"), ("questions", "Questions for the Tumour Board")]
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "section": {"type": "string", "enum": [k for k, _ in SECTIONS], "description": "which NCG Virtual Tumour Board section the sentence belongs to"},
        "text": {"type": "string"},
        "citations": qa.ANSWER_SCHEMA["properties"]["statements"]["items"]["properties"]["citations"]},
        "required": ["section", "text", "citations"]}, "description": "10 to 18 short sentences covering every section that has documented information"},
    "points_for_review": {"type": "array", "items": qa.ANSWER_SCHEMA["properties"]["statements"]["items"],
                          "description": "items to clarify at the board: pending results, superseded or discordant reports (not recommendations)"}},
    "required": ["sentences", "points_for_review"]}

def encounter_lines(case_id, case=None):
    """Which records came from which OP visit or IP admission (V2 item 3.4), plain code: each HIS encounter with its records, OP
    visits before the first admission labelled pre-admission OPD. [] for a Case File not created from the HIS."""
    from . import his_case
    case = case or store.get_case(case_id) or {}
    if not case.get("his"):
        return []
    docs = [d for d in rules.case_docs(case_id) if d.get("state") == "ready" and not d.get("superseded")]
    by_id = {d["doc_id"]: d for d in docs}
    out = []
    for g in his_case.encounter_groups(case, docs):
        if g.get("kind") not in ("OP", "IP") or not g["docs"]:
            continue
        titles = [((by_id[i].get("classification") or {}).get("title") or by_id[i].get("filename")) for i in g["docs"] if i in by_id]
        when = his_case.dmy(g.get("start") or "")
        if g.get("kind") == "IP" and g.get("end"):
            when += f" to {his_case.dmy(g['end'])}"
        out.append({"kind": g["kind"], "number": g["number"], "department": g.get("department"), "unit": g.get("unit"), "when": when, "pre_admission": bool(g.get("pre_admission")),
                    "records": titles, "doc_ids": [i for i in g["docs"] if i in by_id],
                    "text": f"{g['label']} ({g.get('department') or ''}{', ' + g['unit'] if g.get('unit') else ''}; {when})" + (" [pre-admission OPD]" if g.get("pre_admission") else "")
                            + ": " + "; ".join(titles)})
    return out


NOT_LISTED = "This Case File is not listed yet: list it (cancer protocol, NCG setting, board date) before compiling the summary"

SYS = ("You compile the Case File summary for a Tumour Board from signed clinical records. Write like a careful registrar presenting "
       "a case: concise, factual, chronological. Attribute every finding to its source report (for example 'The PET/CT report records ...'). "
       "Copy values exactly. Cite each sentence with the document id and an exact quote. Do not diagnose, interpret images, derive or assign "
       "stage, recommend treatment or predict prognosis. If a stage is mentioned, quote it exactly as recorded in the report that records it.")


async def build(case_id, force=False):
    t0 = time.time()
    au = store.auditor(case_id)
    st = store.get_state(case_id)
    case = store.get_case(case_id)
    sig = rules.case_signature(case_id, st)  # taken before reading anything: a change during the model call marks the summary stale (V1 item 4.5)
    gate = (st.get("gate") or rules.evaluate(case_id)) if case.get("protocol") else None
    if gate is None:  # an unlisted Case File (V1 item 2.5): no protocol, so nothing to compile against and no model call
        return {"status": "not_listed", "message": NOT_LISTED}
    if not gate.get("passed") and not force:
        return {"status": "gate_not_met", "message": "The Case File summary is compiled once every Pre-Authorization check is met.",
                "open": [r["label"] for r in gate["requirements"] if r["status"] not in ("satisfied", "not_applicable")]}
    full, mode = search.context_for(case_id, "clinical history performance status imaging findings pathology biomarkers stage as recorded treatment", 60000)
    facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))  # clinician confirmations win (V1 item 2.2)
    # the stage as recorded, or the FIGO stage as recorded (cervix, V1 item 9.2): the newest verified of the two, copied, never derived
    stage = max([c for c in (facts.get(f, {}).get("current") for f in ("recorded_stage", "figo_stage")) if c and c["verification"] in rules.VERIFIED],
                key=lambda c: (c.get("date") or "", c.get("report_date") or ""), default=None)
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": f"Patient: {case['patient'].get('name')}, {case['patient'].get('agesex', '')}.\n\nDOCUMENTS:\n{full}\n\n"
             "Write the Case File summary in the National Cancer Grid Virtual Tumour Board structure: " + "; ".join(f"{k} = {t}" for k, t in SECTIONS) +
             ". Findings in date order within a section. Prefer FINAL signed reports; mention when a report is draft, preliminary or superseded. "
             "Fitness = performance status, comorbidities and the latest laboratory values as recorded (no judgement of fitness). Questions = the "
             "treating team's documented question(s) for the board only. Keep each quote short (the line that carries the value). Then list points for review."}]
    r = await llm.chat("reasoner", msgs, json_schema=SCHEMA, max_tokens=3500, purpose="case file summary", audit=au)
    grouped = {k: [] for k, _ in SECTIONS}
    for x in r.get("sentences") or []:
        grouped.setdefault(x.get("section") if x.get("section") in grouped else "investigations", []).append(x)
    near = config.near_match()  # approximate source matches kept and flagged, behind a flag (V1 item 6.5)
    sections, paras, removed, issues = [], [], [], []

    def _check(items, where):
        """Verified items that pass the output guardrail; every removal is kept with its reason and place (V1 item 6.4)."""
        ok, drops = qa.verify(case_id, items, near_match=near)
        removed.extend({**x, "where": where} for x in drops)
        keep = []
        for s in ok:
            iss = guardrails.scan_output(s["text"])
            if iss:
                issues.extend(iss)
                removed.append({**qa.removed_item(s, "guardrail", "; ".join(dict.fromkeys(i["reason"] for i in iss))), "where": where})
            else:
                keep.append(s)
        return keep
    for key, title in SECTIONS:
        keep = _check(grouped.get(key, []), key)
        sections.append({"id": key, "title": title, "sentences": keep})
        if keep:
            paras.append(keep)
    cat = protocol.facts()
    try:  # two reports that differ and wait on the treating doctor's check: both values, both quotes (night-v3 item 1.5)
        diffs = discord.open_differences(case_id, st)
    except Exception:
        diffs = {}
    filled = fill_from_facts(sections, facts, cat, diffs)
    paras = [sec["sentences"] for sec in sections if sec["sentences"]]
    pts = _check(r.get("points_for_review"), "points_for_review")
    # the system's own findings: reports that disagree, each citing both reports (code, no model; 12 Oct)
    have = " ".join(grounding.norm(p["text"]) for p in pts)
    for dp in discord.points(case_id, st):
        if grounding.norm(dp["text"])[:60] not in have:
            pts.append(dp)
    from . import his_case  # HIS values the report text does not carry (V2 item 3.3), and the OP / IP context of the records (3.4)
    for hp in his_case.points(case_id, st):
        if grounding.norm(hp["text"])[:60] not in have:
            pts.append(hp)
    encounters = encounter_lines(case_id, case)
    # verification drops of sections AND points for review (before V1 item 6.4 dropped points were not counted)
    dropped = sum(1 for x in removed if x["reason"] != "guardrail")
    by_reason = {k: n for k in qa.REASONS if (n := sum(1 for x in removed if x["reason"] == k))}
    approximate = sum(1 for x in [s for sec in sections for s in sec["sentences"]] + pts if x.get("approximate"))
    out = {"status": "ready" if gate.get("passed") else "incomplete_gate", "sections": sections, "structure": "NCG Virtual Tumour Board case template",
           "paragraphs": paras, "points_for_review": pts,
           "stage_as_recorded": ({"value": stage["value"], "quote": "" if stage.get("confirmed_by") else stage["quote"], "doc_id": stage["doc_id"],
                                  "doc_title": stage["doc_title"], "date": stage["date"], **({"confirmed_by": stage["confirmed_by"]} if stage.get("confirmed_by") else {})}
                                 if stage and stage["verification"] in rules.VERIFIED else None),
           "dropped_unverified": dropped, "guardrail_removed": by_reason.get("guardrail", 0), "removed": removed, "approximate": approximate,
           "near_match": near, "filled_from_fields": filled, "encounters": encounters,
           "differences": [{"fact_id": f, "line": d["line"], "values": d["values"]} for f, d in diffs.items()], "generated": store.now_iso(), "seconds": round(time.time() - t0, 1),
           "model": config.models()["reasoner"].get("label") or "reasoner", "review": {"status": "ai_draft"}, "gate_passed": gate.get("passed"), "context": mode,
           "signature": sig}  # what it was compiled from; a changed Case File marks it stale (V1 item 4.5)
    if issues:
        au({"kind": "guardrail_output", "where": "summary", "issues": issues})
    st = store.get_state(case_id); st.setdefault("artefacts", {})["summary"] = out; store.save_state(case_id, st)
    au({"kind": "summary", "sentences": sum(len(p) for p in paras), "dropped_unverified": dropped, "removed": by_reason, "seconds": out["seconds"]})
    return out
