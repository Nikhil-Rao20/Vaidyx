"""After the Tumour Board: recorded decision, AI-assisted adjudication, scheduling and the longitudinal timeline.

The board's decision is entered by a clinician. The agent never decides; it checks the RECORD:
  1. documentation rules from the protocol (decision text, recorded by, actions with a Responsible Department and due date);
  2. values quoted in the decision vs the verified source values (possible transcription discrepancy, e.g. 6% vs 60%);
  3. decision recorded while Pre-Authorization items were still open (documentation consistency).
Flags go to expert review; the agent does not decide which value is clinically correct."""
import re
import uuid
from datetime import date, timedelta

from . import grounding, llm, negation, protocol, rules, store

CLAIMS_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"claims": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "properties": {
        "fact": {"type": "string", "enum": None}, "value_as_written": {"type": "string"}, "span": {"type": "string", "description": "exact text from the decision"}},
    "required": ["fact", "value_as_written", "span"]}}}, "required": ["claims"]}


# result negations first (shared cues in negation.py): "non-amplified" must never read as "amplified"
_NEG = r"\b(" + negation.NON + r"|negative|not detected|no mutation detected|no (pathogenic )?(variant|alteration)s? detected|wild[- ]?type|absent|not amplified|no evidence of|not seen|not identified|free of|without)\b|\b" + negation.NO + r"\b"
_POS = r"\b(positive|detected|detectable|mutated|mutation present|present|amplified|evidence of|seen|identified|involved|suspicious)\b"


def _polarity(s):
    import re as _re
    s = (s or "").lower()
    if _re.search(_NEG, s):
        return "neg"
    if _re.search(_POS, s):
        return "pos"
    return None


def _nums(s):
    return [float(x) for x in grounding.numbers(s)]


async def adjudicate(case_id, record):
    au = store.auditor(case_id)
    case = store.get_case(case_id)
    prot = protocol.get(case["protocol"])
    flags = []
    for f in prot.get("post_board", {}).get("required_record_fields", []):
        if not record.get(f):
            flags.append({"kind": "documentation", "severity": "review", "text": f"Decision record is missing: {f.replace('_', ' ')}"})
    # Victorian Cancer MDM quality framework: errors or changes to pathology / radiology reports raised at the meeting must be recorded
    if re.search(r"\b(discrepan|correct(ed|ion)|amend|error|wrong|revise|mis-?report|typo)", record.get("decision_text", ""), re.I) and not record.get("report_corrections_raised"):
        flags.append({"kind": "documentation", "severity": "review", "text": "The decision text mentions a correction or discrepancy; record it under 'Report corrections raised at the meeting'"})
    for i, a in enumerate(record.get("actions") or []):
        if not a.get("department"):
            flags.append({"kind": "documentation", "severity": "review", "text": f"Action {i + 1} has no Responsible Department"})
        if not a.get("due"):
            flags.append({"kind": "documentation", "severity": "review", "text": f"Action {i + 1} has no due date"})
    gate = store.get_state(case_id).get("gate") or {}
    open_items = [r["label"] for r in gate.get("requirements", []) if r["status"] not in ("satisfied", "not_applicable")]
    if open_items:
        flags.append({"kind": "consistency", "severity": "review", "text": "Decision recorded while these Pre-Authorization items were open: " + "; ".join(open_items)})
    # value claims in the decision text vs verified source values
    cat = protocol.facts()
    fact_ids = list(cat.keys())
    schema = {**CLAIMS_SCHEMA}
    schema["properties"] = {"claims": {**CLAIMS_SCHEMA["properties"]["claims"]}}
    schema["properties"]["claims"]["items"] = {**CLAIMS_SCHEMA["properties"]["claims"]["items"]}
    schema["properties"]["claims"]["items"]["properties"] = {**CLAIMS_SCHEMA["properties"]["claims"]["items"]["properties"], "fact": {"type": "string", "enum": fact_ids}}
    spec = ", ".join(f"{k} ({v['label']})" for k, v in cat.items())
    msg = [{"role": "system", "content": "You list the patient data values quoted in a Tumour Board decision record. Copy them exactly. Do not judge them."},
           {"role": "user", "content": f"Known fields: {spec}\n\nDECISION RECORD:\n{record.get('decision_text', '')}\n\nList every value in the record that "
            "corresponds to one of the known fields (for example a biomarker percentage, a lab value, a tumour size, a stage as quoted). "
            "If there are none, return an empty list."}]
    claims = []
    try:
        claims = (await llm.chat("reasoner", msg, json_schema=schema, max_tokens=700, purpose="adjudication: values in decision", audit=au)).get("claims", [])
    except Exception as e:
        flags.append({"kind": "system", "severity": "info", "text": f"Value check unavailable: {str(e)[:120]}"})
    facts = rules.resolve_facts(store.list_docs(case_id), store.get_state(case_id).get("overrides"))  # attestations count (V1 item 1.2)
    checks = []
    for c in claims:
        if c.get("span") and not grounding.locate(c["span"], [record.get("decision_text", "")]):
            continue  # model must quote the decision text itself
        src = facts.get(c["fact"], {}).get("current")
        if not src or src["verification"] != "verified":
            checks.append({**c, "result": "no_verified_source", "source": None})
            continue
        a, b = _nums(c["value_as_written"]), _nums(src["value"] + " " + (src.get("quote") or ""))
        if a and b and not set(a) <= set(b):  # every number the board wrote must exist in the source value / quote
            res = "discrepancy"
            flags.append({"kind": "transcription", "severity": "expert_review", "fact": c["fact"],
                          "text": f"Possible transcription discrepancy: {cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source value \"{src['value']}\"",
                          "recorded": c["value_as_written"], "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        elif _polarity(c["value_as_written"]) and _polarity(src["value"] + " " + (src.get("quote") or "")) and _polarity(c["value_as_written"]) != _polarity(src["value"] + " " + (src.get("quote") or "")):
            res = "discrepancy"  # polarity flip: 'negative' recorded where the source says positive, or the reverse
            flags.append({"kind": "transcription", "severity": "expert_review", "fact": c["fact"],
                          "text": f"Possible polarity discrepancy: {cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source states \"{src['value']}\"",
                          "recorded": c["value_as_written"], "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        elif not a and _polarity(c["value_as_written"]) and _polarity(c["value_as_written"]) == _polarity(src["value"]):
            res = "consistent"
        elif not a and grounding.norm(c["value_as_written"]) not in grounding.norm(src["value"]) and grounding.norm(src["value"]) not in grounding.norm(c["value_as_written"]):
            res = "wording_differs"
            flags.append({"kind": "transcription", "severity": "review", "fact": c["fact"],
                          "text": f"{cat[c['fact']]['label']} recorded as \"{c['value_as_written']}\"; source states \"{src['value']}\"",
                          "recorded": c["value_as_written"], "source_value": src["value"], "source_quote": src["quote"], "source_doc": src["doc_id"], "source_title": src["doc_title"]})
        else:
            res = "consistent"
        checks.append({**c, "result": res, "source": {"value": src["value"], "doc_id": src["doc_id"], "quote": src["quote"]}})
    au({"kind": "adjudication", "flags": len(flags), "claims": len(claims)})
    return {"flags": flags, "value_checks": checks, "status": "flag_for_expert_review" if flags else "consistent", "evaluated": store.now_iso()}


async def record_decision(case_id, record, user=""):
    record = {**record, "id": "B" + uuid.uuid4().hex[:6], "recorded_at": store.now_iso(), "entered_by": user}
    record["adjudication"] = await adjudicate(case_id, record)
    st = store.get_state(case_id)
    st.setdefault("board_records", []).append(record)
    for a in record.get("actions") or []:  # board actions become tracked follow-up actions
        st.setdefault("actions", []).append({"id": "A" + uuid.uuid4().hex[:6], "source": "board", "board_record": record["id"], "label": a.get("task") or "Board action",
                                             "department": a.get("department") or "", "what": a.get("task") or "", "status": "pending",
                                             "created": store.now_iso(), "due": a.get("due") or (date.today() + timedelta(days=14)).isoformat(),
                                             "history": [{"ts": store.now_iso(), "event": "Created from Tumour Board record " + record["id"]}]})
    if record.get("next_review"):
        st["next_review"] = {"date": record["next_review"], "from_record": record["id"]}
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "board_record", "record": record["id"], "by": user, "flags": len(record["adjudication"]["flags"])})
    return record


def timeline(case_id):
    ev = []
    for d in store.list_docs(case_id):
        c = d.get("classification") or {}
        if c.get("report_date_iso"):
            ev.append({"date": c["report_date_iso"], "kind": "document", "doc_type": c.get("doc_type"), "title": c.get("title") or d["filename"],
                       "status": c.get("status"), "doc_id": d["doc_id"]})
    st = store.get_state(case_id)
    for b in st.get("board_records", []):
        ev.append({"date": (b.get("board_date") or b["recorded_at"])[:10], "kind": "board", "title": "Tumour Board decision recorded", "record": b["id"]})
    for a in st.get("actions", []):
        ev.append({"date": a["due"], "kind": "action", "title": f"{a['label']} ({a['department']})", "status": a["status"], "action": a["id"]})
    if st.get("next_review"):
        ev.append({"date": st["next_review"]["date"], "kind": "review", "title": "Next Tumour Board review"})
    return sorted(ev, key=lambda e: e["date"])
