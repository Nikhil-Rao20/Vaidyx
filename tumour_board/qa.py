"""Ask the Case File: answers only from the documents, every statement with a verified quote, abstains otherwise.

Pipeline: input guardrail -> instant value finder + hybrid retrieval (or the whole Case File when it fits) ->
LLM answer as {statements:[{text, citations:[{doc_id, quote}]}]} -> every quote aligned to the source ->
statements without a verified quote are dropped -> output guardrail -> "Not documented in the Case File" if empty.
"""
import asyncio, re, time

from . import grounding, guardrails, llm, negation, search, store

ANSWER_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "answer_found": {"type": "boolean"},
    "statements": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "text": {"type": "string", "description": "one short factual statement taken from the documents"},
        "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "doc_id": {"type": "string", "description": "the document id, e.g. D1a2b3c4d"},
            "quote": {"type": "string", "description": "exact text copied from that document that supports the statement"}},
            "required": ["doc_id", "quote"]}}},
        "required": ["text", "citations"]}}},
    "required": ["answer_found", "statements"]}

SYS = ("You are the Case File assistant of a Tumour Board. You answer ONLY from the documents provided. "
       "Copy values exactly as written (units, wording). Every statement must cite the document id and an exact quote copied "
       "character for character from that document. If the documents do not contain the answer, set answer_found=false and return no statements. "
       "Never infer, calculate, diagnose, interpret images, assign stage or recommend treatment. If several documents give different values "
       "(for example over time), list each with its date and source.")


def _locate_quote(quote, pages):
    """Exact (normalised) location of a quote. A multi-line or elided quote is verified line by line: each segment must
    be found exactly; segments that are not found are discarded (never trusted). Returns list of locations."""
    loc = grounding.locate(quote or "", pages)
    if loc and loc["score"] == 100:
        return [loc]
    out = []
    for seg in re.split(r"\n|\s*(?:\.\.\.|\u2026)\s*", quote or ""):
        if len(grounding.norm(seg)) >= 3:
            l = grounding.locate(seg, pages)
            if l and l["score"] == 100:
                out.append(l)
    return out


# "no special type" (breast NST) and "non-" alone are not negations (Non-small cell carcinoma, Non-Hodgkin): only the result negations count (V1 item 1.1)
NEGATION = re.compile(r"\b(" + negation.NO + "|not|negative|absent|without|free of|" + negation.NON + r"|never|neither|nor|none|unremarkable|normal|denies|ruled out|not identified|not seen|not detected)\b", re.I)


def polarity_flag(text, quotes):
    """True when a cited quote carries a negation cue but the statement carries none (possible polarity flip,
    e.g. 'no evidence of metastasis' summarised as 'metastasis'). Shown to the reader as a review flag."""
    return bool(quotes) and any(NEGATION.search(q) for q in quotes) and not NEGATION.search(text or "")


def verify_statements(case_id, statements):
    docs = {d["doc_id"]: d for d in store.list_docs(case_id)}
    out = []
    for st in statements or []:
        cites = []
        for c in st.get("citations") or []:
            d = docs.get((c.get("doc_id") or "").strip())
            if not d:
                continue
            cl = d.get("classification") or {}
            for loc in _locate_quote(c.get("quote") or "", [p["text"] for p in d.get("pages") or []]):
                cites.append({"doc_id": d["doc_id"], "quote": loc["matched"], "page": loc["page"], "start": loc["start"], "end": loc["end"],
                              "doc_title": cl.get("title") or d["filename"], "date": cl.get("report_date_iso"), "status": cl.get("status")})
        # number guard: every number in the statement must appear in a verified quote (or the cited document's title/date)
        allowed = set(n for c in cites for n in grounding.numbers(c["quote"] + " " + (c["doc_title"] or "") + " " + (c["date"] or "")))
        allowed |= {n.lstrip("0") or "0" for n in allowed}
        nums = {n.lstrip("0") or "0" for n in grounding.numbers(st.get("text", ""))}
        if cites and nums <= allowed:
            merged = {}
            for c in cites:  # one citation chip per document; quotes from the same document are joined
                m = merged.get(c["doc_id"])
                if m is None:
                    merged[c["doc_id"]] = dict(c)
                elif c["quote"] not in m["quote"]:
                    m["quote"] += " ... " + c["quote"]
            item = {"text": st["text"], "citations": list(merged.values())}
            if polarity_flag(st["text"], [c["quote"] for c in cites]):
                item["flags"] = ["check negation against the source"]
            out.append(item)
    return out


async def ask(case_id, question, history=None):
    t0 = time.time()
    au = store.auditor(case_id)
    au({"kind": "question", "question": question})
    # scope check and the answer run concurrently; the answer is discarded if the request is out of scope
    hit = guardrails.rule_check(question)
    scope_task = asyncio.create_task(guardrails.check_input(question, au))
    values = await asyncio.to_thread(search.find_values, case_id, question)
    if hit:
        gate = await scope_task
    else:
        gate = None
    if gate and not gate["allowed"]:
        au({"kind": "guardrail_input", "category": gate["category"], "layer": gate["layer"]})
        return {"status": "out_of_scope", "category": gate["category"], "message": gate["message"], "value_hits": values["hits"][:12],
                "seconds": round(time.time() - t0, 2)}
    context, mode = await asyncio.to_thread(search.context_for, case_id, question, 48000)
    if values["hits"]:
        context += "\n\n=== LINES MATCHING THE QUESTION (for convenience; cite the document) ===\n" + \
                   "\n".join(f"[{h['doc_id']} | {h['date'] or '?'}] {h['text']}" for h in values["hits"][:25])
    msgs = [{"role": "system", "content": SYS}]
    for h in (history or [])[-4:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": f"DOCUMENTS:\n{context}\n\nQUESTION: {question}"})
    answer_task = asyncio.create_task(llm.chat("reasoner", msgs, json_schema=ANSWER_SCHEMA, max_tokens=1200, purpose="ask case file", audit=au))
    gate = await scope_task
    if not gate["allowed"]:
        answer_task.cancel()
        au({"kind": "guardrail_input", "category": gate["category"], "layer": gate["layer"]})
        return {"status": "out_of_scope", "category": gate["category"], "message": gate["message"], "value_hits": values["hits"][:12],
                "seconds": round(time.time() - t0, 2)}
    r = await answer_task
    stmts = verify_statements(case_id, r.get("statements"))
    dropped = len(r.get("statements") or []) - len(stmts)
    text = " ".join(s["text"] for s in stmts)
    clean, issues = guardrails.enforce(text, au, "ask")
    if issues:
        stmts = [s for s in stmts if not guardrails.scan_output(s["text"])]
    res = {"status": "answered" if stmts else "not_documented", "statements": stmts, "dropped_unverified": dropped,
           "message": "" if stmts else "Not documented in the Case File. No statement could be verified against the source documents.",
           "value_hits": values["hits"][:12], "mode": mode, "guardrail_issues": issues, "seconds": round(time.time() - t0, 2)}
    au({"kind": "answer", "status": res["status"], "statements": len(stmts), "dropped_unverified": dropped, "seconds": res["seconds"]})
    return res
