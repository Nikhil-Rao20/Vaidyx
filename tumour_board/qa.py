"""Ask the Case File: answers only from the documents, every statement with a verified quote, abstains otherwise.

Pipeline: input guardrail -> instant value finder + hybrid retrieval (or the whole Case File when it fits) ->
LLM answer as {statements:[{text, citations:[{doc_id, quote}]}]} -> every quote aligned to the source ->
statements without a verified quote are dropped -> output guardrail -> "Not documented in the Case File" if empty.
"""
import asyncio, re, time

from . import dates, grounding, guardrails, llm, negation, rules, scanned, search, store, units
from rapidfuzz.distance import Levenshtein

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


_NEG_BEFORE = re.compile(r"\b(?:no|not|without|negative for|absence of|free of|nil)\b[\s:\-]*$", re.I)


def negated_before(page_text, start):
    """True when the words right before a located quote, on its line, are a negation: the quote "Metastatic deposits seen" verifies
    inside "No metastatic deposits seen" (Phase 6 review); the statement then gets the negation check flag."""
    before = (page_text or "")[max(0, start - 30):start].rsplit("\n", 1)[-1]
    return bool(_NEG_BEFORE.search(before))


def polarity_flag(text, quotes):
    """True when a cited quote carries a negation cue but the statement carries none (possible polarity flip,
    e.g. 'no evidence of metastasis' summarised as 'metastasis'). Shown to the reader as a review flag."""
    return bool(quotes) and any(NEGATION.search(q) for q in quotes) and not NEGATION.search(text or "")


# Why an AI statement was removed (V1 item 6.4): kept with the reason so a reviewer can open "N removed items" (failed verification, not facts).
REASONS = {"document_not_found": "cited document not found", "quote_not_found": "quote not found in the cited document",
           "number_not_in_quote": "a number is not in the quoted source", "guardrail": "removed by the clinical scope guardrail"}
APPROXIMATE = "approximate source match: check source"


def removed_item(st, reason, detail):
    """A removed statement as shown to reviewers (V1 item 6.4): its text, the reason and the citations as the model gave them."""
    return {"text": (st or {}).get("text") or "", "reason": reason, "reason_label": REASONS[reason], "detail": detail,
            "citations": [{"doc_id": c.get("doc_id") or "", "quote": (c.get("quote") or "")[:400]} for c in (st or {}).get("citations") or []]}


_ALNUM = re.compile(r"[a-z0-9]+")


def _approx_quote(quote, pages):
    """V1 item 6.5: an approximate location (score >= 92) for a quote with no exact one, only when the quote has >= 12 normalised
    characters and exactly the same numbers as the matched source text, and the letters and digits agree: the same once punctuation,
    spacing and line breaks are set aside, or at most two characters apart with every word of up to four characters (RAS, KRAS, ER, PR,
    not, no) present as a whole word in the source. One character changed the meaning in the Phase 6 measurement: "RAS / BRAF: Not
    performed" matched "NRAS / BRAF Not performed" at 96. Never used by Q&A."""
    if len(grounding.norm(quote)) < 12:
        return None
    loc = grounding.locate(quote, pages)
    if not loc or loc["score"] >= 100:
        return None
    t, a, b = pages[loc["page"]], loc["start"], loc["end"]  # whole words of the source: the aligner may stop inside one ("mg/d")
    while 0 < a < len(t) and t[a].isalnum() and t[a - 1].isalnum():
        a -= 1
    while 0 < b < len(t) and t[b - 1].isalnum() and t[b].isalnum():
        b += 1
    loc = {**loc, "start": a, "end": b, "matched": t[a:b]}
    if set(grounding.numbers(quote)) != set(grounding.numbers(loc["matched"])):
        return None
    if sorted(m.lower() for m in NEGATION.findall(quote)) != sorted(m.lower() for m in NEGATION.findall(loc["matched"])):
        return None  # "No metastatic deposits seen" never matches "Metastatic deposits seen" (Phase 6 review)
    qw, sw = _ALNUM.findall(grounding.norm(quote)), _ALNUM.findall(grounding.norm(loc["matched"]))
    if "".join(qw) != "".join(sw) and (Levenshtein.distance("".join(qw), "".join(sw)) > 2 or not {w for w in qw if len(w) <= 4} <= set(sw)):
        return None
    return loc


def _missing_numbers(text, cites):
    """Numbers of the statement not supported by the located quotes (or the cited documents' titles and dates); [] = supported."""
    allowed = set(n for c in cites for n in grounding.numbers(c["quote"] + " " + (c["doc_title"] or "") + " " + (c["date"] or "")))
    allowed |= {n.lstrip("0") or "0" for n in allowed}
    nums = {n.lstrip("0") or "0" for n in grounding.numbers(text)}
    if nums - allowed:  # a statement number may also be a quoted quantity in other units ('2,45,000/µL' for '2.45 lakhs/cumm'; V1 item 3.5)
        nums = {n.lstrip("0") or "0" for n in units.unmatched_numbers(text, "\n".join(c["quote"] for c in cites))}
    miss = nums - allowed
    return list(dict.fromkeys(n for n in (x.lstrip("0") or "0" for x in grounding.numbers(text)) if n in miss)) or sorted(miss)


_DOC_ID = re.compile(r"\bD[0-9a-f]{8}\b")
_ID_GROUP = re.compile(r"\s*[\[(]\s*(?:(?:doc(?:ument)?\s*)?D[0-9a-f]{8}\s*[,;]?\s*)+[\])]")


def _without_doc_ids(text, ids):
    """The statement text with this Case File's document ids taken out: an id the model wrote inline ("[D75dbac7c]") is not a value, so its
    digits never fail the number guard (V1 item 6.4: found through the removed items, it emptied whole briefs)."""
    return _DOC_ID.sub(lambda m: " " if m.group(0) in ids else m.group(0), text or "")


def _shown_text(text, ids):
    """Bracketed document ids of this Case File removed from the text shown (with the space before them): the citation chip names the
    document. Nothing else in the text changes, so the number guard checks exactly what is shown."""
    return _ID_GROUP.sub(lambda m: "" if all(i in ids for i in _DOC_ID.findall(m.group(0))) else m.group(0), text or "").strip() or (text or "")


def _kept(st, cites):
    merged = {}
    for c in cites:  # one citation chip per document; quotes from the same document are joined
        m = merged.get(c["doc_id"])
        if m is None:
            merged[c["doc_id"]] = dict(c)
        elif c["quote"] not in m["quote"]:
            m["quote"] += " ... " + c["quote"]
            if c.get("approximate"):
                m["approximate"], m["score"] = True, min(m.get("score", 100.0), c["score"])
    item = {"text": st["text"], "citations": [{k: v for k, v in c.items() if k != "negated_before"} for c in merged.values()]}
    if polarity_flag(st["text"], [c["quote"] for c in cites]) or (any(c.get("negated_before") for c in cites) and not NEGATION.search(st["text"] or "")):
        item["flags"] = ["check negation against the source"]
    return item


def verify(case_id, statements, near_match=False):
    """Verify AI statements against the Case File. Returns (kept, dropped): kept statements carry located citations; each dropped
    one carries the reason (V1 item 6.4). near_match=True (briefs and the summary behind config.near_match(), never Q&A) also keeps a
    statement whose quote matches its source only approximately, flagged for the reader (V1 item 6.5)."""
    docs = {d["doc_id"]: d for d in rules.case_docs(case_id)}  # citations carry the confirmed date and type (V1 item 2.2)
    kept, dropped = [], []
    for st in statements or []:
        cites, approx, missing_docs, found_docs = [], [], [], 0
        for c in st.get("citations") or []:
            did = (c.get("doc_id") or "").strip()
            d = docs.get(did)
            if not d:
                missing_docs.append(did)
                continue
            found_docs += 1
            cl = d.get("classification") or {}
            pages = [p["text"] for p in d.get("pages") or []]
            meta = {"doc_title": cl.get("title") or d["filename"], "date": dates.doc_dates(d)["event"] or None, "status": cl.get("status")}
            locs = _locate_quote(c.get("quote") or "", pages)
            for loc in locs:
                cites.append({"doc_id": d["doc_id"], "quote": loc["matched"], "page": loc["page"], "start": loc["start"], "end": loc["end"], **meta,
                              **scanned.citation_source_method(d.get("pages"), loc["page"]),  # "from scan (OCR)" (V1 item 8.1)
                              **({"negated_before": True} if negated_before(pages[loc["page"]], loc["start"]) else {})})
            loc = _approx_quote(c.get("quote") or "", pages) if near_match and not locs else None
            if loc:
                approx.append({"doc_id": d["doc_id"], "quote": loc["matched"], "page": loc["page"], "start": loc["start"], "end": loc["end"], **meta,
                               **scanned.citation_source_method(d.get("pages"), loc["page"]), "approximate": True, "score": loc["score"]})
        # number guard: every number in the statement must appear in a verified quote (or the cited document's title/date)
        shown = _shown_text(st.get("text", ""), docs)
        if shown != st.get("text", ""):
            st = {**st, "text": shown}
        text = _without_doc_ids(shown, docs)
        miss = _missing_numbers(text, cites) if cites else None
        if cites and not miss:
            kept.append(_kept(st, cites))
            continue
        if approx:  # supported only with the approximate locations: kept, flagged (V1 item 6.5)
            miss = _missing_numbers(text, cites + approx)
            if not miss:
                item = _kept(st, cites + approx)
                item["approximate"] = True
                item["flags"] = item.get("flags", []) + [APPROXIMATE]
                kept.append(item)
                continue
        if miss:
            dropped.append(removed_item(st, "number_not_in_quote", ("numbers " if len(miss) > 1 else "number ") + ", ".join(miss) + " not in the quoted source"))
        elif not st.get("citations"):
            dropped.append(removed_item(st, "quote_not_found", "no quote given"))
        elif not found_docs:
            dropped.append(removed_item(st, "document_not_found", ", ".join(x or "(no id)" for x in dict.fromkeys(missing_docs)) + " not in this Case File"))
        elif not any((c.get("quote") or "").strip() for c in st.get("citations") or []):
            dropped.append(removed_item(st, "quote_not_found", "no quote given"))
        else:
            dropped.append(removed_item(st, "quote_not_found", "quote not found in " + ", ".join(dict.fromkeys(
                (c.get("doc_id") or "").strip() for c in st.get("citations") or [] if (c.get("doc_id") or "").strip() in docs))))
    return kept, dropped


def verify_statements(case_id, statements):
    """Exact verification only (Q&A and every caller before V1 item 6.5): the kept statements of verify()."""
    return verify(case_id, statements)[0]


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
    stmts, removed = verify(case_id, r.get("statements"))  # Q&A stays exact-only (V1 item 6.5)
    dropped = len(removed)
    text = " ".join(s["text"] for s in stmts)
    clean, issues = guardrails.enforce(text, au, "ask")
    if issues:
        keep = []
        for s in stmts:
            iss = guardrails.scan_output(s["text"])
            if iss:  # kept for reviewers with the reason (V1 item 6.4)
                removed.append(removed_item(s, "guardrail", "; ".join(dict.fromkeys(i["reason"] for i in iss))))
            else:
                keep.append(s)
        stmts = keep
    res = {"status": "answered" if stmts else "not_documented", "statements": stmts, "dropped_unverified": dropped, "removed": removed,
           "message": "" if stmts else "Not documented in the Case File. No statement could be verified against the source documents.",
           "value_hits": values["hits"][:12], "mode": mode, "guardrail_issues": issues, "seconds": round(time.time() - t0, 2)}
    au({"kind": "answer", "status": res["status"], "statements": len(stmts), "dropped_unverified": dropped, "seconds": res["seconds"],
        "removed": [{"reason": x["reason"], "text": x["text"][:200]} for x in removed]})
    return res
