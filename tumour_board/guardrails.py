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
]

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
    msg = [{"role": "system", "content": "You are a scope classifier for a Tumour Board Case File assistant. The assistant may ONLY find, quote, list, "
            "compare dates, check completeness and organise information that is written in the patient's documents (including values, results, "
            "the stage or diagnosis AS RECORDED in a report, pending tests, timelines, who is responsible). It must NOT recommend or choose treatment, "
            "diagnose, interpret images, derive stage, or predict prognosis."},
           {"role": "user", "content": f"Request: {text}\n\nClassify the request."}]
    try:
        r = await llm.chat("reasoner", msg, json_schema=CLASSIFIER_SCHEMA, max_tokens=120, purpose="scope check", audit=audit)
    except Exception:
        return {"allowed": True, "category": "in_scope", "message": "", "layer": "classifier-unavailable"}
    cat = r.get("category", "in_scope")
    return {"allowed": cat == "in_scope", "category": cat, "message": REFUSALS.get(cat, ""), "reason": r.get("reason"), "layer": "classifier"}


# ---------------------------------------------------------------------------------------------- output policy
PRESCRIPTIVE = re.compile(
    r"\b(i|we) (would )?(recommend|suggest|advise)|\brecommend(ed|s|ation)?\b|\bshould (be )?(receive|undergo|start|begin|be treated|be given|be offered|consider|have)\b|"
    r"\b(is|are) (indicated|eligible|a candidate|candidates)\b|\b(best|preferred|optimal) (option|treatment|therapy|approach|management)\b|"
    r"\b(start|initiate|commence) (on )?(chemo|immuno|targeted|radio|treatment|therapy)|\bconsider (starting|giving|surgery|chemo|radiotherapy|resection)\b|"
    r"\b(likely|probably|suggestive of|consistent with|in keeping with|diagnosis is|diagnosed as having)\b|\bprognosis\b|\bsurvival (is|would)\b", re.I)
STAGE = re.compile(r"\b[cpyr]?T[0-4][a-d]?\s*N[0-3][a-c]?(\s*M[01][a-c]?)?\b|\bstage\s+(0|I{1,3}V?|IV|[1-4])[A-C]?\b", re.I)
QUOTE = re.compile(r"\"[^\"]{2,400}\"|“[^”]{2,400}”")


# Reported speech: the sentence attributes the wording to a document or to the clinicians, so it is documentation, not advice.
REPORTED = re.compile(r"\b(the |previous |prior |earlier )?(tumou?r board|board|mdt|record|minutes|report|note|letter|summary|plan|decision|"
                      r"radiologist|pathologist|oncologist|surgeon|physician|clinician|treating team|team|dr\.?\s*[A-Z][a-z]+)\b.{0,60}"
                      r"\b(recorded|records|documented|documents|noted|notes|stated|states|wrote|writes|advised|recommended|recommends|planned|plans|decided|decision was|suggested|impression|concluded|reads)\b", re.I)


def scan_output(text):
    """Find policy violations outside quoted source text. Returns list of {sentence, reason}."""
    issues = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        bare = QUOTE.sub(" ", sent)
        if REPORTED.search(bare) and not re.search(r"\b(i|we)\b\s+(would\s+)?(recommend|suggest|advise)", bare, re.I):
            continue  # documented wording attributed to its source
        if PRESCRIPTIVE.search(bare):
            issues.append({"sentence": sent.strip(), "reason": "prescriptive or diagnostic wording"})
        elif STAGE.search(bare) and not re.search(r"\b(recorded|documented|as written|states|reported)\b", bare, re.I):
            issues.append({"sentence": sent.strip(), "reason": "stage stated without attribution to a source"})
    return issues


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
