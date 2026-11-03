"""Ask PubMed (docs/pubmed-ask/DESIGN.md, owner decision of 3 Nov 2026): a general question answered only from PubMed records fetched
through pubmed.py. The Case File agents keep their scope (records and guidelines); this is the add-on beside them.

Steps: the scope check (a question about a patient, advice or an opinion is refused; a question about published results passes) ->
the search words (the model writes them; a patient identifier, a date or a long number never leaves the server; the question's own
words when the model's are unusable) -> PubMed's Best Match ids, widened step by step when nothing is found -> the records (retracted
papers and retraction notices are listed, never read; a paper without an abstract is listed, not read) -> every paper read by the model
in one prompt -> statements, each with a PMID and an exact quote -> a PMID that was not given, or a quote not found word for word in
that paper's title or abstract, drops the citation; a statement with no verified citation is dropped -> numbers must be in the quotes,
names like KEYNOTE-522 in the cited papers -> no advice and no patient in Vaidyx's own words -> the answer with the papers as PubMed
sent them and the provenance of every call. PubMed down: "could not be reached", never the model's own memory.

Run one question: /data/vaidyx/venv/app/bin/python -m tumour_board.pubmed_ask "question" [--fresh] [--json out.json]"""
import asyncio
import re
import time

from . import config, grounding, guardrails, llm, pubmed

LABEL = "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for this patient."
LABEL_HOME = "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for any patient."
NOT_FOUND = "No answer found in the PubMed abstracts read."
NO_PAPERS = "PubMed found no paper for these search words. Change the words and try again."
DOWN = "{reason}. Try again in a minute."  # the reason says what PubMed did ("PubMed answered 503 after 4 tries")
MODEL_DOWN = "The model could not be reached ({reason}). The papers PubMed found are listed."
REFUSED = ("Ask PubMed answers general questions about published research. It does not give advice, a stage or an outlook for a patient. "
           "Ask about published results, for example: \"What pathological complete response did trials report with neoadjuvant "
           "pembrolizumab in triple-negative breast cancer?\"")
RECORDS = "That is a question about this patient's records. Ask it under This patient's records."
IDENT = "Take the patient's name or number out of the question: Ask PubMed sends only search words to PubMed."
NOT_MEDICAL = "Ask PubMed answers questions about medical research."
MAX_QUESTION = 600
MAX_QUERY = 300
RETMAX = 20
MIN_FOUND = 5  # fewer papers than this widens the search
READ_CHARS = 60000  # the papers' text given to the model at most (its window is 32k tokens)
MAX_STATEMENTS = 6

# ---- the scope check ------------------------------------------------------------------------------------------------------------------
# A particular person ("this patient", "she", "her", never "HER2"); a request for advice or an opinion; a clinical word that, next to a
# person, makes the question about that person.
# "her 2" and "HER-2" are HER2 unless a count follows ("her 2 cycles"); "the patient population" is a group, not a person.
PERSON = re.compile(r"\b(?:this|my|our|your) (?:patient|case|lady|woman|man|gentleman|child|boy|girl)\b(?!-)|"
                    r"\bthe patient\b(?!-|\s+(?:population|group|groups|cohort|cohorts|selection|sample|level)\b)|\b(?:she|he|him|his|hers)\b|"
                    r"\bher\b(?!\s*-?\s*2\b(?!\s*(?:cycles?|doses?|courses?|weeks?|months?|years?|days?|sessions?|fractions?|visits?|"
                    r"children|kids|surgeries|operations|lines?)\b))", re.I)
ADVICE = re.compile(r"\bshould (?:we|i|she|he|they|the patient)\b|\b(?:what|which) (?:should|would) (?:we|i|you)\b|\bwould you\b|"
                    r"\bdo you (?:agree|think|recommend|suggest|advise)\b|\byour (?:opinion|advice|view|recommendation)\b|"
                    r"\b(?:can|could|shall) we (?:give|start|offer|operate|go ahead|proceed|stop|add|use|treat)\b|\bwhat would you do\b", re.I)
CLINICAL = re.compile(r"\b(?:treat\w*|therap\w*|surg\w*|operat\w*|resect\w*|chemo\w*|radi\w*|dose|drug|regimen|surviv\w*|prognos\w*|outlook|"
                      r"life expectancy|cure|curable|stage|staging|eligib\w*|candidate|fit\b|diagnos\w*|benefit\w*|respond\w*|recur\w*)", re.I)
SCAN = re.compile(r"\b(?:look at|read|interpret|analy[sz]e)\b.{0,20}\b(?:this|these|her|his|my|our|attached)\b.{0,15}"
                  r"\b(?:scan|image|images|ct|mri|x-?ray|pet|slide|film|mammogram)s?\b", re.I)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
# a date (12/03/2026, 2026-03-12, 12 March 2026, March 12, 2026; one separator throughout, so a CI "0.48-0.82" is not a date)
IDENT_RX = re.compile(r"\d{6,}|(?<![\d.])\d{1,2}([/.-])\d{1,2}\1\d{2,4}(?![\d.])|(?<![\d.])\d{4}([/.-])\d{1,2}\2\d{1,2}(?![\d.])|"
                      r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r",?\s+\d{2,4}\b|\b" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b|"
                      r"\b(?:uhid|mrn|abha|aadhaar|ip no|op no|cr no)\b|@", re.I)


def _idents(identifiers) -> list:
    """The patient's identifiers as a list (one given alone as text is one identifier, not its letters)."""
    return [identifiers] if isinstance(identifiers, (str, int)) else list(identifiers or ())


def scope(question: str, identifiers=()) -> dict:
    """{allowed, reason, message} by rule: identifiers first, then advice, a scan of a person, a clinical question about a person, a
    question about a person's records."""
    q = question or ""
    low = q.lower()
    if IDENT_RX.search(q) or any(_has_identifier(low, i) for i in _idents(identifiers)):
        return {"allowed": False, "reason": "identifier", "message": IDENT}
    if ADVICE.search(q):
        return {"allowed": False, "reason": "advice", "message": REFUSED}
    if SCAN.search(q):
        return {"allowed": False, "reason": "scan", "message": REFUSED}
    if PERSON.search(q):
        return {"allowed": False, "reason": "about_patient" if CLINICAL.search(q) else "records", "message": REFUSED if CLINICAL.search(q) else RECORDS}
    return {"allowed": True, "reason": "general", "message": ""}


def _has_identifier(low: str, ident) -> bool:
    """A patient identifier in the text: the whole identifier, a name part as a whole word, or a number part of five or more characters."""
    il = str(ident or "").lower().strip()
    if len(il) < 3:
        return False
    if il in low:
        return True
    words = set(re.findall(r"[a-z]+", low))
    for part in re.split(r"[\s,/]+", il):
        if len(part) >= 3 and part.isalpha() and part in words:
            return True
        if len(part) >= 5 and not part.isalpha() and part in low:
            return True
    return False


# ---- the search words -----------------------------------------------------------------------------------------------------------------
QUERY_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "kind": {"type": "string", "enum": ["general", "about_a_patient", "not_medical"]},
    "query": {"type": "string", "description": "PubMed search words for the question"},
    "broader_query": {"type": "string", "description": "the one or two main concepts only"}},
    "required": ["kind", "query", "broader_query"]}

QUERY_SYS = ("You write PubMed search words for a doctor's question. "
             "kind: 'general' when the question asks what published research reports (results, rates, evidence, trials, definitions, methods); "
             "'about_a_patient' when it asks for advice, a diagnosis, a stage or an outlook for a particular patient; 'not_medical' otherwise. "
             "query: PubMed syntax with the 2 to 4 main concepts joined by AND, synonyms of a concept in parentheses joined by OR, quoted "
             "phrases allowed, plain words only with no field tags such as [tiab] or [MeSH] (PubMed maps the words to its own headings), "
             "in English, at most 250 characters. broader_query: the 1 or 2 most important "
             "concepts only, in the same syntax. Never put a person's name, an identifier, a date, an age, a place or a hospital in the words.")

STOP = set("a an and are as at be by can could did do does for from had has have how in into is it its of on or that the their them "
           "there these this those to was were what when where which who whom why will with would about any between than after before "
           "during versus vs per there evidence literature published report reported show shows tell me please".split())


def keywords(question: str) -> str:
    """The question's own words without stop words (the fallback when the model's words are unusable)."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9-]+", question or "") if w.lower() not in STOP]
    return " ".join(words[:8])


def untagged(q: str) -> str:
    """The words without field tags: a wrong tag ("breast cancer"[MeSH] is not a heading) makes PubMed drop that part of the search."""
    t = " ".join(re.sub(r"\[[A-Za-z /:-]{2,30}\]", " ", q or "").split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", t))


def query_ok(q: str, identifiers=()) -> bool:
    q = q or ""
    if not (2 <= len(q) <= MAX_QUERY) or not re.search(r"[A-Za-z]{2,}", q):
        return False
    if q.count("(") != q.count(")") or q.count('"') % 2:
        return False
    return not (IDENT_RX.search(q) or any(_has_identifier(q.lower(), i) for i in _idents(identifiers)))


async def search_words(question: str, context: dict | None, identifiers=(), audit=None) -> dict:
    """{kind, query, broader_query, by}: the model's words when usable, else the question's own words."""
    ctx = ""
    if context:
        bits = [f"cancer: {context['cancer']}" if context.get("cancer") else ""] + [str(t) for t in context.get("terms") or []][:8]
        ctx = ("\n\nThe question is asked inside a patient's Case File about: " + "; ".join(b for b in bits if b) +
               ". Use these words only when the question says 'this cancer' or leaves the disease out.")
    try:
        r = await llm.chat("reasoner", [{"role": "system", "content": QUERY_SYS}, {"role": "user", "content": f"QUESTION: {question}{ctx}"}],
                           json_schema=QUERY_SCHEMA, max_tokens=300, purpose="pubmed search words", audit=audit)
    except Exception as e:  # the question's own words still search PubMed
        return {"kind": "general", "query": keywords(question), "broader_query": "", "by": "question", "error": f"{e.__class__.__name__}"}
    r = r if isinstance(r, dict) else {}  # not an object: the question's own words
    kind = r.get("kind") if r.get("kind") in ("general", "about_a_patient", "not_medical") else "general"
    q = untagged(str(r.get("query") or ""))
    b = untagged(str(r.get("broader_query") or ""))
    if not query_ok(q, identifiers):
        return {"kind": kind, "query": keywords(question), "broader_query": b if query_ok(b, identifiers) else "", "by": "question"}
    return {"kind": kind, "query": q, "broader_query": b if query_ok(b, identifiers) else "", "by": "model"}


# ---- reading and checking -------------------------------------------------------------------------------------------------------------
ANSWER_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "answer_found": {"type": "boolean"},
    "statements": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "text": {"type": "string", "description": "one short statement of what the papers report"},
        "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "pmid": {"type": "string", "description": "the PMID of the paper, digits only"},
            "quote": {"type": "string", "description": "exact text copied from that paper's title or abstract"}},
            "required": ["pmid", "quote"]}}},
        "required": ["text", "citations"]}}},
    "required": ["answer_found", "statements"]}

ANSWER_SYS = ("You answer a doctor's general question ONLY from the PubMed papers given (title and abstract of each). "
              "Write 2 to 5 short statements in plain English. Each statement cites one or more papers by PMID, each with an exact quote "
              "copied character for character from that paper's title or abstract that supports the statement. Copy numbers exactly. "
              "Say what the papers report ('The trial reported ...', 'A meta-analysis of 12 trials found ...'). Never give advice, never say "
              "what should be done for a patient, never apply a result to any patient. Use nothing from outside these papers: no paper, trial "
              "name, number or fact that is not in the text given. When papers disagree, give each finding with its own paper. If the papers "
              "answer only part of the question, answer that part; reviews and other papers that describe trial results count. If they "
              "do not answer the question at all, set answer_found=false and return no statements.")

OWN_ADVICE = re.compile(r"\b(?:i|we) (?:would )?(?:recommend|suggest|advise)\b|\byou should\b|"
                        r"\bshould (?:be )?(?:receive|undergo|start|begin|be treated|be given|be offered|consider|have|get|use)\b|"
                        r"\b(?:best|preferred|optimal|right) (?:option|choice|treatment|therapy|approach|management|regimen)\b|"
                        r"\b(?:consider|start|initiate|offer|give) (?:starting|giving|treating|chemo\w*|radio\w*|surgery|the drug)\b", re.I)
RECOMMEND = re.compile(r"\brecommend\w*", re.I)
ATTRIBUTED = re.compile(r"\b(?:authors?|guidelines?|panel|consensus|society|statement|study|trial|review|paper|investigators|meta-analysis|they)\b", re.I)
NEGATION = re.compile(r"\b(?:not|no|never|without|neither|nor|failed|fails|non|cannot|unlikely)\b|n't", re.I)
COUNTED = re.compile(r"\s+(?:patients?|participants?|women|men|people|persons|cases|subjects|children|adults|events?|deaths?)\b", re.I)  # "a 2023 trial" is a year
NAMED = re.compile(r"\b(?=[A-Za-z0-9/-]*[A-Za-z])(?=[A-Za-z0-9/-]*\d)[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*\b")


def paper_block(p: dict) -> str:
    return (f"[PMID {p['pmid']}] {p['study_type']} | {p['journal_abbr'] or p['journal']} | {p['year']} | {p['authors_line']}\n"
            f"Title: {p['title']}\nAbstract:\n{p['abstract']}")


def _locate(quote: str, p: dict) -> list:
    """Where the quote is in the paper's title or abstract, word for word (normalised spacing, case and punctuation forms). An elided
    quote ("A ... B") is checked part by part and every part must be found. [] when any part is missing."""
    pages = [p["title"], p["abstract"]]
    loc = grounding.locate(quote or "", pages)
    if loc and loc["score"] == 100:
        return [loc]
    parts = [s for s in re.split(r"\n|\s*(?:\.\.\.|…)\s*", quote or "") if len(grounding.norm(s)) >= 3]
    if not parts:  # one part is a quote that only starts or ends with "...": still checked word for word
        return []
    out = []
    for s in parts:
        l = grounding.locate(s, pages)
        if not (l and l["score"] == 100):
            return []
        out.append(l)
    for a, b in zip(out, out[1:]):  # the parts in order on one page, and what was left out between them holds no negation
        if a["page"] != b["page"] or b["start"] < a["end"] or NEGATION.search(pages[a["page"]][a["end"]:b["start"]]):
            return []
    return out


SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
WORD = re.compile(r"[a-z][a-z-]{2,}")


def _in_order(qwords: list, cwords: list) -> float:
    """The share of the quote's words found in the sentence in the same order (a word skipped in the quote is fine)."""
    k, hit = 0, 0
    for w in qwords:
        j = k
        while j < len(cwords) and cwords[j] != w:
            j += 1
        if j < len(cwords):
            hit, k = hit + 1, j + 1
    return hit / len(qwords) if qwords else 0.0


def _sentence_for(quote: str, p: dict) -> str:
    """The paper's own sentence (or two sentences in a row) that a quote the model shortened was taken from, or "". The model often
    leaves out a confidence interval without marking it; the doctor is then shown the paper's whole sentence, word for word as PubMed
    sent it. Only when at least 90% of the quote's words are in it in the same order, every number of the quote is in it and
    neither has a negation the other lacks."""
    qn = grounding.norm(quote or "")
    qwords = WORD.findall(qn)
    if len(qwords) < 5:
        return ""
    qnums = set(grounding.numbers(qn))
    best, best_cov = "", 0.0
    for page in (p["title"], p["abstract"]):
        sents = [x for x in SENT_END.split(page.replace("\n", " ")) if x.strip()]
        for i in range(len(sents)):
            for cand in (sents[i], " ".join(sents[i:i + 2]) if i + 1 < len(sents) else ""):
                cn = grounding.norm(cand)
                if not cn:
                    continue
                cov = _in_order(qwords, WORD.findall(cn))
                if (cov >= 0.9 and qnums <= set(grounding.numbers(cn)) and bool(NEGATION.search(qn)) == bool(NEGATION.search(cn))
                        and (cov > best_cov or (cov == best_cov and len(cand) < len(best)))):
                    best, best_cov = cand.strip(), cov
    return best


def _where(p: dict, loc: dict) -> str:
    """The abstract section a quote is in ("RESULTS"), or "Title"."""
    if loc["page"] == 0:
        return "Title"
    pos = 0
    for s in p["sections"]:
        size = len(f"{s['label']}: {s['text']}" if s["label"] else s["text"]) + 1
        if loc["start"] < pos + size:
            return s["label"] or "Abstract"
        pos += size
    return "Abstract"


def own_words_issue(text: str, quotes: list) -> str:
    """Why a statement's own words (outside its quotes) are not allowed, or ""."""
    # quotation marks in the text count as the paper's words only around words of a verified quote ('"is the best option"' is not)
    own = guardrails.outside_quotes(guardrails.QUOTE.sub(
        lambda m: " " if any(grounding.norm(m.group(0)[1:-1]) in grounding.norm(q) for q in quotes) else m.group(0), text), quotes)
    if PERSON.search(own):
        return "it speaks about a patient"
    m = OWN_ADVICE.search(own)
    if m:
        return f"advice in Vaidyx's own words ({m.group(0)})"
    for s in guardrails.SENTENCE.split(own):
        r = RECOMMEND.search(s)
        if r and not ATTRIBUTED.search(s[:r.start()]):
            return "a recommendation in Vaidyx's own words"
    return ""


def _unlabelled(quote: str, p: dict) -> str:
    """The quote without an abstract section label it starts with ("CONCLUSIONS: In patients ..." shows "In patients ..."); the rest is
    still the paper's own words."""
    for s in p["sections"]:
        lab = s["label"]
        if lab and quote[:len(lab)].lower() == lab.lower():
            rest = re.sub(r"^[\s:.-]+", "", quote[len(lab):])
            if len(grounding.norm(rest)) >= 3:
                return rest
    return quote


def _plain(t: str) -> str:
    """Hyphens and slashes as spaces ("5-year" is "5 year"); a decimal point stays."""
    return re.sub(r"\s+", " ", re.sub(r"[-/\u2010-\u2015]", " ", t))


def _neighbours(n: str, t: str) -> list:
    """For each place of the number n in the plain text t: (the word before, the word after, a % after), stop words left out."""
    out = []
    for m in re.finditer(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", t):
        before = re.search(r"([a-z]+)\W*$", t[:m.start()])
        after = re.match(r"\s*(%)?\W*([a-z]+)?", t[m.end():])
        b = before.group(1) if before and before.group(1) not in STOP else ""
        a = after.group(2) if after and after.group(2) and after.group(2) not in STOP else ""
        out.append((b, a, bool(after and after.group(1))))
    return out


def _sentence_holding(n: str, text: str, p: dict) -> str:
    """The paper's own sentence that states the number as the statement uses it, or "": the same word beside it ("phase 2", "36 months"),
    the same % sign, and when no word stands beside it at least two content words shared with the statement. "A phase 2 trial" never
    borrows the 2 of "in a 2:1 ratio"."""
    t = _plain(grounding.norm(text))
    words = {w for w in WORD.findall(t) if w not in STOP}
    best, best_shared = "", -1
    for page in (p["title"], p["abstract"]):
        for x in SENT_END.split(page.replace("\n", " ")):
            xt = _plain(grounding.norm(x))
            if not re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", xt):
                continue
            shared = len(words & set(WORD.findall(xt)))
            ok = False
            for b, a, pct in _neighbours(n, t):
                if pct and not re.search(r"(?<![\w.])" + re.escape(n) + r"\s*%", xt):
                    continue
                pairs = [f"{b} {n}" if b else "", f"{n} {a}" if a else ""]
                if any(pairs):
                    ok = any(x2 and re.search(r"(?<![\w.])" + re.escape(x2) + r"(?![\w.])", xt) for x2 in pairs)
                else:
                    ok = shared >= 2
                if ok:
                    break
            if ok and shared > best_shared:
                best, best_shared = x.strip(), shared
    return best


def _in_context(n: str, text: str, papers_text: str) -> bool:
    """A number outside the quotes is still the paper's when it stands in the cited papers with the same word beside it ("phase 2")."""
    t = _plain(grounding.norm(text))
    papers_text = _plain(papers_text)
    for m in re.finditer(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", t):
        before = re.search(r"([a-z]+)\W*$", t[:m.start()])
        after = re.match(r"\W*([a-z]+)", t[m.end():])
        before, after = [x if x and x.group(1) not in STOP else None for x in (before, after)]  # "at 36" says nothing: "36 months" does
        for pair in ((before.group(1) + " " + n) if before else "", (n + " " + after.group(1)) if after else ""):
            if pair and re.search(r"(?<![\w.])" + re.escape(pair) + r"(?![\w.])", papers_text):
                return True
    return False


def _year_of(n: str, text: str, years: set) -> bool:
    """A cited paper's year, used as a year ("a 2023 trial"), never as a count ("2023 patients")."""
    return n in years and not any(COUNTED.match(text, m.end()) for m in re.finditer(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", text))


def verify(statements, papers: dict) -> tuple:
    """(kept, removed, invented): each statement keeps its citations whose PMID was read and whose quote is in that paper word for word;
    then its numbers must be in those quotes (or be a cited paper's year), its names with digits in the cited papers, its own words
    free of advice and of any patient. invented counts PMIDs the model cited that were not given."""
    kept, removed, invented = [], [], 0
    for st in (statements if isinstance(statements, list) else [])[:MAX_STATEMENTS * 2]:
        if not isinstance(st, dict):
            continue
        text = " ".join(str(st.get("text") or "").split())[:600]
        if not text:
            continue
        cites, why = [], ""
        for c in st.get("citations") or []:
            if not isinstance(c, dict):
                continue
            pmid = re.sub(r"\D", "", str(c.get("pmid") or ""))
            if pmid not in papers:
                invented += 1
                why = why or "the cited paper was not among the papers read"
                continue
            locs = _locate(str(c.get("quote") or ""), papers[pmid])
            whole = ""
            if not locs:  # a shortened quote: the paper's own sentence, when it is clearly the one
                whole = _sentence_for(str(c.get("quote") or ""), papers[pmid])
                locs = _locate(whole, papers[pmid]) if whole else []
            if not locs:
                why = why or "the quote is not word for word in the paper"
                continue
            quote = _unlabelled(" ... ".join(l["matched"] for l in locs), papers[pmid])
            if any(x["pmid"] == pmid and x["quote"] == quote for x in cites):
                continue
            cites.append({"pmid": pmid, "quote": quote, "where": _where(papers[pmid], locs[0])} | ({"whole_sentence": True} if whole else {}))
        if not cites:
            removed.append({"text": text, "reason": why or "no citation",
                            "model_quotes": [str(c.get("quote") or "")[:400] for c in st.get("citations") or [] if isinstance(c, dict)][:3]})
            continue
        quotes = [c["quote"] for c in cites]
        cited = [papers[c["pmid"]] for c in cites]
        in_quotes = set(grounding.numbers(" ".join(quotes)))
        years = {p["year"] for p in cited}
        names = [n for n in NAMED.findall(text)]
        name_numbers = set(grounding.numbers(" ".join(names)))
        papers_text = grounding.norm(" ".join(p["title"] + " " + p["abstract"] for p in cited))
        missing = [n for n in grounding.numbers(text) if n not in in_quotes and not _year_of(n, text, years) and n not in name_numbers
                   and not _in_context(n, text, papers_text)]
        # a number the quote lacks but a cited paper states the same way: that paper's own sentence is shown as one more quote
        for n in list(missing):
            for cp in {c["pmid"]: papers[c["pmid"]] for c in cites}.values():
                x = _sentence_holding(n, text, cp)
                loc = grounding.locate(x, [cp["title"], cp["abstract"]]) if x else None
                if loc and loc["score"] == 100 and sum(bool(c.get("added_for_numbers")) for c in cites) < 3:
                    q = _unlabelled(loc["matched"], cp)
                    if not any(q == c["quote"] for c in cites):
                        cites.append({"pmid": cp["pmid"], "quote": q, "where": _where(cp, loc), "added_for_numbers": True})
                    missing.remove(n)
                    break
        quotes = [c["quote"] for c in cites]
        if missing:
            removed.append({"text": text, "reason": f"number {', '.join(missing)} not in the quoted text"})
            continue
        unknown = [n for n in names if grounding.norm(n) not in papers_text]
        if unknown:
            removed.append({"text": text, "reason": f"{', '.join(unknown)} not in the cited papers"})
            continue
        issue = own_words_issue(text, quotes)
        if issue:
            removed.append({"text": text, "reason": issue})
            continue
        kept.append({"text": text, "citations": cites})
        if len(kept) >= MAX_STATEMENTS:
            break
    return kept, removed, invented


def card(p: dict, rank: int, read: bool, why_not: str = "") -> dict:
    """A paper as shown: every field from PubMed's record."""
    return {k: p.get(k) for k in ("pmid", "title", "journal", "journal_abbr", "year", "authors_line", "study_type", "tier", "types", "preprint",
                                   "retracted", "retraction_notice", "concern", "erratum", "india", "doi", "pmcid", "url", "has_abstract")} | {
        "rank": rank, "read": read, "why_not_read": why_not, "provenance": p.get("provenance") or {}}


def model_line() -> str:
    m = config.models().get("reasoner") or {}
    return f"{m.get('label') or 'reasoner'} ({'medical' if m.get('medical') else 'non-medical'})"


# ---- the whole question ---------------------------------------------------------------------------------------------------------------
async def ask(question: str, *, context: dict | None = None, identifiers=(), in_case_file: bool = False, fresh: bool = False,
              years: int | None = None, on_step=None, audit=None, client=None) -> dict:
    """One Ask PubMed question. context (inside a Case File): {"cancer": ..., "terms": [...]} may sharpen the search words; identifiers:
    the patient's name and numbers, refused in the question and in the words; years limits the publication date to the last n years
    (None: every year, PubMed's Best Match order, so a landmark trial of 2015 is found). on_step(step, detail) reports progress."""
    identifiers = _idents(identifiers)
    t0 = time.time()
    steps = []

    async def step(name, detail=""):
        steps.append({"step": name, "detail": detail, "seconds": round(time.time() - t0, 2)})
        if on_step:
            r = on_step(name, detail)
            if asyncio.iscoroutine(r):
                await r

    q = " ".join(str(question or "").split())[:MAX_QUESTION]
    out = {"question": q, "label": LABEL if in_case_file else LABEL_HOME, "status": "", "message": "", "search": {}, "statements": [],
           "removed": [], "invented_pmids": 0, "papers": [], "counts": {"found": 0, "fetched": 0, "read": 0}, "calls": [],
           "model": model_line(), "searched_at": pubmed.now_iso(), "steps": steps}

    def done(status, message=""):
        out.update(status=status, message=message, seconds=round(time.time() - t0, 2))
        if audit:
            audit({"kind": "pubmed_ask", "status": status, "question": q[:300], "words": out["search"].get("used", ""),
                   "found": out["counts"]["found"], "read": out["counts"]["read"], "statements": len(out["statements"]),
                   "removed": len(out["removed"]), "invented_pmids": out["invented_pmids"], "seconds": out["seconds"]})
        return out

    if len(q) < 3 or not re.search(r"[^\W\d_]{2,}", q):  # letters of any script (a Hindi question is turned into English words)
        return done("refused", "Type a question.")
    gate = scope(q, identifiers)
    if not gate["allowed"]:
        out["refusal"] = gate["reason"]
        return done("refused", gate["message"])

    await step("words", "writing the PubMed search words")
    w = await search_words(q, context, identifiers, audit)
    if w["kind"] == "about_a_patient":
        out["refusal"] = "about_patient_model"
        return done("refused", REFUSED)
    if w["kind"] == "not_medical":
        out["refusal"] = "not_medical"
        return done("refused", NOT_MEDICAL)
    out["search"] = {"query": w["query"], "broader_query": w["broader_query"], "by": w["by"], "attempts": []}

    # PubMed's Best Match, widened step by step until MIN_FOUND papers are found; else the search that found the most
    tries, seen = [], set()
    for term, yrs in ((w["query"], years), (w["broader_query"], years), (w["query"], None), (keywords(q), None)):
        if term and (term, yrs) not in seen:
            seen.add((term, yrs))
            tries.append((term, yrs))
    found = None
    for term, yrs in tries:
        await step("search", f"searching PubMed: {term}" + (f" (last {yrs} years)" if yrs else " (all years)"))
        try:
            s = await pubmed.search(term, retmax=RETMAX, years=yrs, client=client)
        except pubmed.PubMedError as e:
            out["search"]["used"] = term
            return done("unavailable", DOWN.format(reason=str(e)))
        out["search"]["attempts"].append({"term": term, "years": yrs, "count": s["count"], "warnings": s["warnings"]})
        out["calls"].append({"what": "search", **s["provenance"]})
        if s["ids"] and (found is None or len(s["ids"]) > len(found["ids"])):
            found = s
        if len(s["ids"]) >= MIN_FOUND:
            break
    if not found:
        out["search"]["used"] = tries[-1][0] if tries else ""
        return done("no_papers", NO_PAPERS)
    out["search"].update(used=found["term"], years=found["years"], translation=found["translation"])
    out["counts"]["found"] = found["count"]

    await step("fetch", f"{found['count']} papers found, fetching the top {len(found['ids'])} records")
    try:
        f = await pubmed.fetch(found["ids"], client=client, fresh=fresh)
    except pubmed.PubMedError as e:
        return done("unavailable", DOWN.format(reason=str(e)))
    out["calls"] += [{"what": "fetch", **c} for c in f["calls"]]
    out["counts"]["fetched"] = len(f["papers"])

    # what is read: an abstract, not retracted, not a retraction notice; strongest study types first, then PubMed's order, within budget
    rank = {pmid: i + 1 for i, pmid in enumerate(found["ids"])}
    order = sorted(f["papers"], key=lambda p: (p["tier"], rank.get(p["pmid"], 999)))
    read, cards, used = {}, [], 0
    for p in order:
        why = ("retracted" if p["retracted"] else "a retraction notice" if p["retraction_notice"] else
               "no abstract in PubMed" if not p["has_abstract"] else "")
        size = len(paper_block(p))
        if not why and used + size > READ_CHARS:
            why = "the reading limit was reached"
        if not why:
            read[p["pmid"]] = p
            used += size
        cards.append(card(p, rank.get(p["pmid"], 0), not why, why))
    out["papers"] = cards
    out["counts"]["read"] = len(read)
    if not read:
        return done("not_found", NOT_FOUND)

    await step("read", f"the model is reading {len(read)} abstracts")
    papers_txt = "\n\n".join(paper_block(p) for p in read.values())
    msgs = [{"role": "system", "content": ANSWER_SYS},
            {"role": "user", "content": f"PAPERS (from PubMed):\n\n{papers_txt}\n\nQUESTION: {q}"}]
    try:
        a = await llm.chat("reasoner", msgs, json_schema=ANSWER_SCHEMA, max_tokens=1500, purpose="pubmed answer", audit=audit)
    except Exception as e:
        return done("unavailable", MODEL_DOWN.format(reason=e.__class__.__name__))

    await step("check", "checking every quote against PubMed's text")
    kept, removed, invented = verify(a.get("statements") if isinstance(a, dict) else [], read)
    out.update(statements=kept, removed=removed, invented_pmids=invented)
    cited = {c["pmid"] for s in kept for c in s["citations"]}
    for c in out["papers"]:
        c["cited"] = c["pmid"] in cited
    return done("answered" if kept else "not_found", "" if kept else NOT_FOUND)


def _print(r: dict) -> None:
    print(f"\nQUESTION: {r['question']}\nSTATUS: {r['status']}  {r['message']}")
    s = r.get("search") or {}
    if s:
        print(f"SEARCH WORDS ({s.get('by')}): {s.get('used')}  years: {s.get('years') or 'all'}  PubMed found: {r['counts']['found']}")
    print(f"PAPERS: fetched {r['counts']['fetched']}, read {r['counts']['read']}   MODEL: {r['model']}   {r.get('seconds')} s")
    for i, st in enumerate(r["statements"], 1):
        print(f"\n{i}. {st['text']}")
        for c in st["citations"]:
            print(f"   PMID {c['pmid']} [{c['where']}]: \"{c['quote']}\"")
    if r["removed"]:
        print(f"\nDROPPED {len(r['removed'])}: " + "; ".join(x["reason"] for x in r["removed"]))
    print("\nPAPERS (as PubMed sent them):")
    for p in r["papers"]:
        mark = "CITED" if p.get("cited") else "read " if p["read"] else "not read"
        print(f"  [{mark}] PMID {p['pmid']} {p['year']} {p['study_type']}, {p['journal_abbr']}: {p['title'][:90]}"
              + (f"  ({p['why_not_read']})" if p["why_not_read"] else "") + ("  [India]" if p["india"] else ""))
    print(f"\n{r['label']}")


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args()
    res = asyncio.run(ask(args.question, fresh=args.fresh, on_step=lambda s, d: print(f"  .. {d}")))
    _print(res)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1)
