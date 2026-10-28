"""Clinical scope guardrails (the hackathon scope contract, enforced in code).

The assistant does NOT: diagnose, interpret medical scans or images, recommend / prescribe treatment, derive or
assign stage, predict prognosis or make clinical decisions. It retrieves, extracts, checks and organises what the
signed records say, with sources, for clinicians who decide.

Layer 1 (input):  rules + a small LLM classifier decide whether a request is in scope.
Layer 2 (output): any sentence of generated text, outside a verified source quote, that contains prescriptive /
                  diagnostic wording or a stage pattern is removed and logged. Values must come with citations.
"""
import re

from . import llm

CATEGORIES = ["in_scope", "treatment_recommendation", "diagnosis", "scan_interpretation", "stage_derivation", "prognosis", "other_out_of_scope"]

_RULES = [
    ("treatment_recommendation", r"\b(what|which)\b.{0,40}\b(treatment|therapy|regimen|drug|chemo\w*|surgery|radiation|radiotherapy|plan|option)s?\b.{0,40}\b(should|best|recommend\w*|give|start|choose|offer)\b"),
    ("treatment_recommendation", r"\bshould\b.{0,30}\b(we|i|patient|he|she|they)\b.{0,30}\b(give|start|receive|undergo|operate|treat|get|be treated|stop|continue)\b"),
    ("treatment_recommendation", r"\b(recommend|suggest|advise)\b.{0,40}\b(treatment|therapy|regimen|drug|dose|surgery|management|plan)\b"),
    ("treatment_recommendation", r"\b(dose|dosage)\b.{0,30}\b(should|recommend|calculate)\b"),
    ("diagnosis", r"\b(diagnose|what (is|does) (the patient|he|she) (have|suffer))\b"),
    ("diagnosis", r"\b(is it|is this|could (it|this) be)\b.{0,20}\b(cancer|malignan\w*|benign|metastas\w*|tumou?r)\b"),
    ("scan_interpretation", r"\b(look at|read|interpret|analy[sz]e|review|see)\b.{0,30}\b(scan|image|images|ct|mri|x-?ray|pet|slide|film|mammogram)\b(?!.{0,15}report)"),
    ("stage_derivation", r"\b(what|calculate|derive|assign|determine|work out)\b.{0,30}\b(stage|tnm)\b(?!.{0,40}\b(recorded|documented|written|reported)\b)"),
    ("prognosis", r"\b(prognosis|survival|life expectancy|how long (will|does) (he|she|the patient)|chance of cure)\b"),
    # night-v3 item 6.4: a decision asked of an agent the way one asks a colleague; refused by rule because the classifier fails open
    ("treatment_recommendation", r"\bwhat would you do\b"),
    ("treatment_recommendation", r"\bwhich (one )?would you (pick|choose|go for)\b"),
    ("other_out_of_scope", r"\bdo you agree (with|that)\b"),
    ("treatment_recommendation", r"\bis (it|he|she|the patient|this|the tumou?r|the lesion|the disease|the mass) (operable|resectable|curable|fit for|a candidate)\b"),
    ("treatment_recommendation", r"\b(a |the )?candidate for\b.{0,30}\b(surgery|resection|chemo\w*|radiotherapy|radiation|treatment|therapy|transplant\w*)\b"),
    ("treatment_recommendation", r"\bbenefit from\b"),
    ("treatment_recommendation", r"\bdo you think\b.{0,40}\b(fit|operable|resectable|candidate|benefit|should)\b"),
    ("treatment_recommendation", r"\bcan we (go ahead|proceed) with\b"),
    ("treatment_recommendation", r"\bwould you (recommend|suggest|advise|give|offer|operate)\b"),
]

# Reference questions (night-v3 item 6.4): what a report, record, summary or checklist should contain, or which investigations a work-up
# lists, is answered with labelled reference text from the specialty's guideline pack, never applied to the patient. Such a question is in
# scope by rule when no refusal rule matches, so the classifier (which reads "what the documents hold" narrowly) does not refuse it.
_REFERENCE_OPENER = re.compile(r"\b(what|which|how)\b", re.I)
_REFERENCE_NOUN = re.compile(r"\b(report\w*|record\w*|summary|summaries|checklist\w*|work-?up|staging (investigation|imaging|test)\w*|"
                             r"baseline (test|investigation)\w*|follow-?up (investigation|test|imaging)\w*|investigations?|tests?|biomarkers?|template\w*)\b", re.I)
_REFERENCE_VERB = re.compile(r"\b(contain\w*|include\w*|list\w*|document\w*|state\w*|mention\w*|cover\w*|comprise\w*|require\w*)\b", re.I)


# A reference question never names a treatment, an indication or this patient: such a question goes to the classifier as before (the
# Phase 6 review, S1), so "what does the checklist list as the best treatment for this patient" is never let through by rule.
_REFERENCE_BLOCK = re.compile(r"\b(treat\w*|therap\w*|regimen\w*|drugs?|dos(e|es|age|ing)|chemo\w*|surg\w*|radiat\w*|radiother\w*|adjuvant|neoadjuvant|"
                              r"best|options?|indicat\w*|candidates?|eligib\w*|benefits?|next step\w*|manage\w*|prescri\w*|give|start|"
                              r"for (this|the|our|my) patient|for (her|him|them)|she|he|his|her)\b", re.I)


def reference_check(text) -> bool:
    """True for a question about what records should contain (reference text), when no refusal rule matches it and it names no
    treatment, indication or patient."""
    t = str(text or "")
    if rule_check(t) or _REFERENCE_BLOCK.search(t):
        return False
    return bool(_REFERENCE_OPENER.search(t) and _REFERENCE_NOUN.search(t) and _REFERENCE_VERB.search(t))


REFUSALS = {
    "treatment_recommendation": "I can't recommend or choose treatment. Treatment decisions belong to the Tumour Board. I can show what the signed records document, list pending results, and surface the relevant guideline sections for the board to review.",
    "diagnosis": "I can't make or suggest a diagnosis. I can show the diagnosis exactly as recorded in the signed pathology or clinical reports, with the source.",
    "scan_interpretation": "I don't interpret images or scans. I can show what the signed imaging reports record, with quotes.",
    "stage_derivation": "I don't derive or assign stage. I can show the stage exactly as recorded in a signed report, with its source.",
    "prognosis": "I can't estimate prognosis or survival. I can show what the records document.",
    "other_out_of_scope": "That is outside what this assistant does. It checks, finds and organises information in the Tumour Board Case File.",
}

CLASSIFIER_SCHEMA = {"type": "object", "additionalProperties": False,
                     "properties": {"category": {"type": "string", "enum": CATEGORIES}, "reason": {"type": "string"}},
                     "required": ["category", "reason"]}


def rule_check(text):
    t = text.lower()
    for cat, rx in _RULES:
        if re.search(rx, t):
            return cat
    return None


async def check_input(text, audit=None):
    """Returns {"allowed": bool, "category": str, "message": str, "layer": "rule"|"classifier"}."""
    hit = rule_check(text)
    if hit:
        return {"allowed": False, "category": hit, "message": REFUSALS[hit], "layer": "rule"}
    if reference_check(text):  # what a report or a work-up should contain: labelled reference text, in scope by rule (item 6.4)
        return {"allowed": True, "category": "in_scope", "message": "", "layer": "rule", "reference": True}
    msg = [{"role": "system", "content": "You are a scope classifier for a Tumour Board Case File assistant. The assistant may ONLY find, quote, list, "
            "compare dates, check completeness and organise information that is written in the patient's documents (including values, results, "
            "the stage or diagnosis AS RECORDED in a report, pending tests, timelines, who is responsible), and it may show, as labelled reference "
            "text never applied to the patient, what a guideline says a report, record, summary or work-up should contain. It must NOT recommend or "
            "choose treatment, diagnose, interpret images, derive stage, or predict prognosis."},
           {"role": "user", "content": f"Request: {text}\n\nClassify the request."}]
    try:
        r = await llm.chat("reasoner", msg, json_schema=CLASSIFIER_SCHEMA, max_tokens=120, purpose="scope check", audit=audit)
    except Exception:
        return {"allowed": True, "category": "in_scope", "message": "", "layer": "classifier-unavailable"}
    cat = r.get("category", "in_scope")
    return {"allowed": cat == "in_scope", "category": cat, "message": REFUSALS.get(cat, ""), "reason": r.get("reason"), "layer": "classifier"}


# ---------------------------------------------------------------------------------------------- output policy
_PRESCRIPTIVE_BASE = (
    r"\b(i|we) (would )?(recommend|suggest|advise)|\brecommend(ed|s|ation)?\b|\bshould (be )?(receive|undergo|start|begin|be treated|be given|be offered|consider|have)\b|"
    r"\b(is|are) (indicated|eligible|a candidate|candidates)\b|\b(best|preferred|optimal) (option|treatment|therapy|approach|management)\b|"
    r"\b(start|initiate|commence) (on )?(chemo|immuno|targeted|radio|treatment|therapy)|\bconsider (starting|giving|surgery|chemo|radiotherapy|resection)\b|"
    r"\b(likely|probably|suggestive of|consistent with|in keeping with|diagnosis is|diagnosed as having)\b|\bprognosis\b|\bsurvival (is|would)\b")
# Advice put as a need, a fitness or a verdict (the whole-run review, I1): "she needs", "requires", "is warranted", "proceed with surgery",
# "fit for", "would be appropriate", "malignant", "this is a ... carcinoma", and "should" before any verb. Checked in what the models write
# about a patient; a guideline's own reporting wording ("the report should include") is reference text and keeps the base list only.
HISTOLOGY = r"(?:\w*(?:oma|omas)|tumou?rs?|cancers?|neoplasms?|malignan\w*|metasta\w*|leuka?emias?|disease)"
ADVICE_WORDS = (r"\bneeds?\b|\bneeded\b|\brequires?\b|\brequired\b|\bwarranted\b|\badvisable\b|\bappropriate\b|\bproceed(ing)? with\b|"
                r"\bfit for\b|\bmalignant\b|\bthis is (a|an)\s+(?:[\w-]+\s+){0,3}?" + HISTOLOGY + r"\b|\bshould\s+(?:not\s+)?\w+")
PRESCRIPTIVE = re.compile(_PRESCRIPTIVE_BASE + "|" + ADVICE_WORDS, re.I)
PRESCRIPTIVE_REFERENCE = re.compile(_PRESCRIPTIVE_BASE, re.I)  # for a verified guideline quote shown as reference text only
STAGE = re.compile(r"\b[cpyr]?T[0-4][a-d]?\s*N[0-3][a-c]?(\s*M[01][a-c]?)?\b|\bstage\s+(0|I{1,3}V?|IV|[1-4])[A-C]?\b", re.I)
QUOTE = re.compile(r"\"[^\"]{2,400}\"|“[^”]{2,400}”")


# Reported speech: the sentence attributes the wording to a document or to the clinicians. It excuses a stage written in a report ("the
# PET/CT report records stage IIIA"), never advice: since the whole-run review (I1) prescriptive wording passes only inside a quoted span
# ('The report records "adjuvant chemotherapy recommended"'), so "the report records a mass, so she should undergo surgery" is refused.
REPORTED = re.compile(r"\b(the |previous |prior |earlier )?(tumou?r board|board|mdt|record|minutes|report|note|letter|summary|plan|decision|"
                      r"radiologist|pathologist|oncologist|surgeon|physician|clinician|treating team|team|dr\.?\s*[A-Z][a-z]+)\b.{0,60}"
                      r"\b(recorded|records|documented|documents|noted|notes|stated|states|wrote|writes|advised|recommended|recommends|planned|plans|decided|decision was|suggested|impression|concluded|reads)\b", re.I)


def scan_output(text, reference=False):
    """Find policy violations outside quoted source text. Returns list of {sentence, reason}. reference=True is for a verified guideline
    quote shown as labelled reference text (its own "should include" is the guideline's wording, not advice to anyone)."""
    rx = PRESCRIPTIVE_REFERENCE if reference else PRESCRIPTIVE
    issues = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        bare = QUOTE.sub(" ", sent)
        if rx.search(bare):
            issues.append({"sentence": sent.strip(), "reason": "prescriptive or diagnostic wording"})
        elif STAGE.search(bare) and not REPORTED.search(bare) and not re.search(r"\b(recorded|documented|as written|states|reported)\b", bare, re.I):
            issues.append({"sentence": sent.strip(), "reason": "stage stated without attribution to a source"})
    return issues


def outside_quotes(text, quotes):
    """The text with each cited quote taken out (its words in order, case and spacing and punctuation between them ignored), so what is
    left is what the statement says in its own words."""
    out = str(text or "")
    for q in sorted({str(q or "") for q in quotes or []}, key=len, reverse=True):
        words = re.findall(r"\w+", q)
        if words:
            out = re.sub(r"(?<!\w)" + r"\W+".join(map(re.escape, words)) + r"(?!\w)", " ", out, flags=re.I)
    return out


def unquoted_words(text, quotes, pattern):
    """The words of pattern that the text uses outside its cited quotes (lower case, sorted); empty when every such word sits in a quote."""
    return sorted({m.group(0).lower() for m in pattern.finditer(outside_quotes(text, quotes))})


def enforce(text, audit=None, where=""):
    """Remove violating sentences; return (clean_text, issues)."""
    issues = scan_output(text)
    clean = text
    for i in issues:
        if i["sentence"]:
            clean = clean.replace(i["sentence"], "[removed by clinical scope guardrail]")
    if issues and audit:
        audit({"kind": "guardrail_output", "where": where, "issues": issues})
    return clean, issues
