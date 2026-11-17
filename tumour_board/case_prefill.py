"""AI pre-fill of the New Case File (docs/new-case/DESIGN.md decision N6): after the hospital system lookup finds the patient, the
reasoning model reads that patient's reports and suggests the Cancer step (cancer, colon / rectum or adult / child variant, NCG setting
as recorded) and the Logistics step (a draft board question, an urgency suggestion). The doctor checks and edits every value; nothing
is created here and nothing is written to the hospital system.

Why a job: reading up to 12 reports and one model call take 10 to 60 seconds, and the doctor must be able to carry on with the steps
meanwhile. POST /his/prefill starts it and answers at once with the job id; GET /his/prefill/{job} answers {state, result?, error?}.
Jobs live in memory per hospital (config.ScopedDict: two hospitals never see each other's job), only the user who started a job may
read it (another user gets "not found", never "forbidden": a job id says nothing about who asked), and a job is forgotten 30 minutes
after it started. A user has at most one running job: a new lookup cancels the earlier one (the doctor moved to another patient), and
the same lookup asked again within those 30 minutes gets the same job back (no second model call when the doctor goes back a step).
asyncio.create_task copies the current context, so the job runs inside the hospital of the request that started it (config.DATA_ROOT).

What the model sees: the reports of the lookup's window (his_case.window_start), current versions only, newest 12, each read from its
PDF text layer (the same pypdf reading and "usable text" test as ingest.py) and cut at REPORT_CHARS; the whole prompt stays within
PROMPT_CHARS (the reasoner serves 32768 tokens; about 12k tokens of reports leaves room for the instructions and the answer). A scanned
page with no text layer is not read here: the vision reader would add minutes and shared model load to a suggestion the doctor can
type in a second, so such a report is counted in `reports_skipped` and the first fetch reads it in full after Create.

Grounding (project rule: every answer shows its proof): every value that comes with a quote is kept only when the quote (at least
MIN_QUOTE characters and MIN_QUOTE_WORDS words) is found word for word (case, spacing and punctuation variants aside: grounding.norm)
in the text of a report that was read. The model names the report; when the quote sits in another report read, the value is kept and
pointed at that report (the proof shown is where the words really are). Found is not enough: the quote must also SAY the value (review
of 17 Nov 2026). The cancer's quote must call it a cancer, not negated or hedged, and name the site of the suggested checklist
(site_ok: a word list per checklist, the label's main word for one without a list), and the stored name is the words of the quote
(name_from). The setting's quote must state that setting in its label's words or a stage its label names (setting_ok; an adult or
child setting also needs the patient's age); a setting with no rule is never suggested. The urgency quote must be a finding, not a
heading or a status line (urgency_quote_ok). A value that fails is dropped and listed in `dropped` with the reason: a dropped value
costs the doctor one click, a wrong one may be believed. The NCG setting must belong to the suggested checklist (and is dropped with
the cancer); urgency must be 1 to 5. The board question is a draft for the doctor to edit
and carries `basis` (the reports it rests on) instead of a quote. The owning department is chosen WITHOUT the model: the doctor's own
treating departments that appear in the patient's visits; exactly one such department is suggested.

The model is told to leave a field empty when the records do not say it and never to work out a stage (the setting is "as recorded").
Urgency is only ever a suggestion: the screen never pre-selects it (owner rule: the treating consultant's own call).

If the hospital system or the model server does not answer, or the model answers badly, the job ends `failed` with a plain message;
the lookup and Create never wait for it. Audited: org.audit("case_prefill", ...) with the fields filled and the count dropped, and every
model call as llm_call (prompt hash, tokens, seconds) like the other model callers.
"""
import asyncio
import io
import logging
import re
import secrets
import time

from . import config, grounding, his_case, his_client, llm, org, protocol
from .api import common as _api_common

log = logging.getLogger("tumour_board")

MAX_REPORTS = 12
REPORT_CHARS = 6000
PROMPT_CHARS = 48000
JOB_TTL = 30 * 60          # seconds a job is kept after it started
DOWNLOADS = 4               # reports downloaded at once
MIN_QUOTE = 15              # characters (normalised) a quote needs to count as proof
MIN_QUOTE_WORDS = 3         # and words: "left breast" proves nothing about a cancer
MIN_URGENCY_WORDS = 4       # an urgency quote is a finding, never a heading or a status line
CHILD_AGE = 18              # under this age a setting named "child" applies, from it one named "adult"
QUESTION_MAX = 600          # the board question box takes 600 characters
REASON_MAX = 240
MAX_TOKENS = 1200
PURPOSE = "new case prefill"
# POST /his/prefill per login: each new patient costs one model call on a server shared with every hospital; a doctor starting 30
# Case Files in 10 minutes is far beyond a real clinic, so more than that is a loop or a script (review of 17 Nov 2026).
START_LIMIT = _api_common.RateLimit(30, 10 * 60)
BUSY = "Too many AI look-ups in a short time. Wait a few minutes and try again; you can fill the steps yourself meanwhile."
NO_CLINICAL_ACCESS = "The Vaidyx admin has no clinical access, so the AI does not read a patient's reports for it."

# The cancers.ts entries with a follow-up question, by the checklist each answer leads to: {protocol: (entry id, variant id)}.
# The ids match web/tb-nik/src/lib/cancers.ts (Colorectal: colon / rectum; Kidney: rcc / wilms; Liver: hcc).
VARIANTS = {"colorectal_colon": ("colorectal", "colon"), "colorectal_rectum": ("colorectal", "rectum"),
            "kidney": ("kidney", "rcc"), "wilms": ("kidney", "wilms"), "liver_hcc": ("liver", "hcc")}

JOBS: dict = config.ScopedDict()  # per hospital: job id -> {"id", "user", "key", "state", "started", "result", "error", "task"}

FAILED_MODEL = "The AI could not read the records just now. Fill the steps yourself; nothing else is affected."
FAILED_HIS = "The hospital system did not answer, so the AI could not read the records. Fill the steps yourself."
NOT_FOUND = "The patient was not found in the hospital system."

SCHEMA = {
    "type": "object",
    "properties": {
        "cancer": {"type": "object", "properties": {
            "name": {"type": "string", "description": "the cancer in the words of the quote (a part of the quote copied, e.g. Invasive ductal carcinoma of the left breast); empty when the records do not name a cancer"},
            "protocol": {"type": "string", "description": "one checklist id from the CHECKLISTS list; empty when unsure"},
            "quote": {"type": "string", "description": "the diagnosis line of the report that names this cancer and its site, copied character for character (the words after Diagnosis or Impression, at least four words)"},
            "report": {"type": "string", "description": "the report the quote is from, e.g. R2"}}},
        "setting": {"type": "object", "properties": {
            "id": {"type": "string", "description": "one setting id of the chosen checklist, or not_recorded"},
            "quote": {"type": "string", "description": "the words of the report that state this setting itself (e.g. multiple liver metastases, FIGO 2018 stage IIIB, locally advanced), copied character for character"},
            "report": {"type": "string", "description": "the report the quote is from, e.g. R4"}}},
        "board_question": {"type": "object", "properties": {
            "text": {"type": "string", "description": "the question for the tumour board in one or two sentences, as the treating clinician would write it; empty when the records give no basis"},
            "basis": {"type": "array", "items": {"type": "string", "description": "a report it rests on, e.g. R1"}}}},
        "urgency": {"type": "object", "properties": {
            "level": {"type": "integer", "description": "1 (least urgent) to 5 (most urgent); 0 only when no cancer is recorded"},
            "reason": {"type": "string", "description": "one short sentence: why this level"},
            "quote": {"type": "string", "description": "the finding the reason rests on, a sentence of the report copied character for character (never a heading, title or status line)"},
            "report": {"type": "string", "description": "the report the quote is from, e.g. R3"}}},
    },
}


# ---- jobs ---------------------------------------------------------------------------------------------------------------------

def _purge(now: float | None = None) -> None:
    now = now or time.time()
    for jid in [j for j, v in list(JOBS.items()) if now - v.get("started", 0) > JOB_TTL]:
        job = JOBS.pop(jid, None)
        t = (job or {}).get("task")
        if t is not None and not t.done():
            t.cancel()


def _key(identifier: str, window: dict) -> str:
    w = window or {}
    return f"{identifier.strip().upper()}|{w.get('months') or ''}|{'all' if w.get('all') else ''}|{w.get('from') or ''}"


def start(identifier: str, window, user: str, roles: dict) -> dict:
    """Start (or find again) the pre-fill job of one lookup. Raises his_case.HISCaseError for a missing identifier, a bad window or no
    hospital system (the same messages as the lookup). Returns the job record."""
    identifier = str(identifier or "").strip()
    if not identifier:
        raise his_case.HISCaseError("Enter a UHID, IP No. or OP No.")
    window = his_case.window_from(window)
    his_case._client()  # no hospital system configured: the same 409 as the lookup, before any job exists
    _purge()
    key = _key(identifier, window)
    for job in JOBS.values():
        if job["user"] == user and job["key"] == key and job["state"] in ("running", "done"):
            return job  # the same lookup again (the doctor went back a step): the same job, no second model call
    for job in JOBS.values():  # one running job per user: the doctor has moved to another patient
        t = job.get("task")
        if job["user"] == user and job["state"] == "running" and t is not None and not t.done():
            t.cancel()
            job["state"], job["error"] = "failed", "Stopped: another patient was looked up."
    jid = "PF-" + secrets.token_hex(6)
    job = {"id": jid, "user": user, "key": key, "state": "running", "started": time.time(), "result": None, "error": ""}
    JOBS[jid] = job
    job["task"] = asyncio.create_task(_run(job, identifier, window, user, dict(roles or {})))
    return job


def view(job_id: str, user: str) -> dict | None:
    """What the screen polls: {job, state, result?, error?}; None for an unknown, expired or someone else's job."""
    _purge()
    job = JOBS.get(str(job_id or ""))
    if not job or job["user"] != user:
        return None
    out = {"job": job["id"], "state": job["state"]}
    if job["state"] == "done":
        out["result"] = job["result"]
    if job["state"] == "failed":
        out["error"] = job["error"] or FAILED_MODEL
    return out


async def _run(job: dict, identifier: str, window: dict, user: str, roles: dict) -> None:
    try:
        job["result"] = await prefill(identifier, window, user, roles)
        job["state"] = "done"
    except asyncio.CancelledError:
        job["state"] = "failed"
        job["error"] = job.get("error") or "Stopped."
    except his_case.HISCaseError as e:
        job["state"], job["error"] = "failed", str(e) if e.status == 404 else FAILED_HIS
    except his_client.HISError as e:
        log.info("case prefill: hospital system error %s", e)
        job["state"], job["error"] = "failed", FAILED_HIS
    except llm.LLMError as e:
        log.info("case prefill: model error %s", str(e)[:200])
        job["state"], job["error"] = "failed", FAILED_MODEL
    except Exception as e:  # never let a suggestion break anything: a quiet failure
        log.warning("case prefill failed: %s: %s", type(e).__name__, str(e)[:200])
        job["state"], job["error"] = "failed", FAILED_MODEL
    if job["state"] == "failed":
        try:
            org.audit("case_prefill_failed", user, job=job["id"], error=job["error"][:200])
        except Exception:
            pass


# ---- reading the records ----------------------------------------------------------------------------------------------------------

def _day(r: dict) -> str:
    return str(r.get("issued") or r.get("effective") or r.get("last_updated") or "")[:10]


def text_of(d: dict) -> tuple[str, bool]:
    """The text of one downloaded record ({"content": bytes, "content_type", ...} from his_client.document) and whether part of it
    could not be read (a scanned page with no text layer). PDF: pypdf's text layer, each page kept only when ingest's test calls it
    usable text. Plain text: decoded. Anything else (an image): ("", True)."""
    from . import ingest
    data = d.get("content") or b""
    ctype = str(d.get("content_type") or "").lower()
    if data[:5] == b"%PDF-" or "pdf" in ctype:
        try:
            from pypdf import PdfReader
            pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
        except Exception:
            return "", True
        kept = [t for t in pages if ingest._layer_ok(t)]
        return "\n".join(kept).strip(), len(kept) < len(pages)
    if ctype.startswith("text/") or ctype in ("", "application/octet-stream"):
        try:
            return data.decode("utf-8").strip(), False
        except UnicodeDecodeError:
            return "", True
    return "", True


async def _read(client, reports: list) -> tuple[list, int]:
    """Download and read the reports (DOWNLOADS at a time), in the order given. Returns ([{id, title, date, department, text,
    partial}], skipped): a report that could not be downloaded or has no readable text is skipped."""
    sem = asyncio.Semaphore(DOWNLOADS)

    async def one(r):
        async with sem:
            try:
                d = await client.document(r["document_ref"])
            except his_client.HISError as e:
                log.info("case prefill: report %s not downloaded: %s", r.get("document_ref"), e)
                return None
        text, partial = await asyncio.to_thread(text_of, d)
        return {"id": "", "title": str(r.get("title") or d.get("title") or "Report").strip()[:120], "date": _day(r),
                "department": str(r.get("performer_department") or ""), "text": text[:REPORT_CHARS], "partial": partial}

    got = await asyncio.gather(*[one(r) for r in reports])
    read = [g for g in got if g and g["text"]]
    for i, g in enumerate(read):  # R1..Rn over the reports actually read, newest first, as the model sees them
        g["id"] = f"R{i + 1}"
    return read, len(reports) - len(read)


def _checklists() -> list:
    """[{id, label, settings: [{id, label}]}] of every built checklist, for the prompt and the checks."""
    out = []
    for p in protocol.list_protocols():
        out.append({"id": p["id"], "label": p["label"], "settings": [{"id": s.get("id"), "label": s.get("label") or s.get("id")}
                                                                    for s in p.get("settings") or [] if isinstance(s, dict) and s.get("id")]})
    return out


def messages(patient: dict, reports: list, checklists: list) -> list:
    """The prompt: the checklists with their settings, the reports labelled R1..Rn (newest first) within PROMPT_CHARS, the task."""
    lines = []
    for c in checklists:
        sets = "; ".join(f"{s['id']} = {s['label']}" for s in c["settings"]) or "none"
        lines.append(f"- {c['id']}: {c['label']} (settings: {sets})")
    blocks, used = [], 0
    for r in reports:
        head = f"[{r['id']}] {r['title']}" + (f", {r['department']}" if r["department"] else "") + (f", dated {his_case.dmy(r['date'])}" if r["date"] else "")
        block = f"{head}\n{r['text']}\n[end of {r['id']}]"
        if used + len(block) > PROMPT_CHARS:
            room = PROMPT_CHARS - used - len(head) - 40
            if room < 500:
                break
            block = f"{head}\n{r['text'][:room]}\n[{r['id']} cut here]"
        blocks.append(block)
        used += len(block)
    agesex = ", ".join(str(x) for x in (patient.get("age"), patient.get("sex")) if x not in (None, ""))
    system = ("You help an Indian oncologist start a tumour board Case File. You read the patient's hospital reports and suggest "
              "values the doctor will check. Rules: use only what the reports say; leave a field empty when the reports do not say it; "
              "never work out or guess a stage or setting that is not written in a report; every quote must be copied word for word "
              "from the report you name (no ellipsis, no rewording, one short passage); write in plain English.")
    task = ("Suggest:\n"
            "1. cancer: the quote is the diagnosis line that names the cancer and its site (for example the words after Diagnosis in a "
            "histopathology report); the name is those words, copied from the quote; the protocol is the one checklist id from CHECKLISTS "
            "for that site (generic for a solid cancer with no checklist, generic_haem for a blood cancer with no checklist).\n"
            "2. setting: the NCG setting of that checklist ONLY when a report states it in words (for example metastatic disease "
            "written in an imaging report, or a stage the setting's label names); otherwise not_recorded. The quote must hold those words.\n"
            "3. board_question: the question this patient's records raise for the tumour board, one or two sentences, as the "
            "treating clinician would write it, with the reports it rests on.\n"
            "4. urgency: how soon this patient needs the board, from 1 (least urgent, e.g. follow-up after finished treatment) to 5 "
            "(most urgent, e.g. spread or a threatening complication), with a one-sentence reason and the quote of the finding it rests "
            "on (a sentence about a diagnosis, a symptom, spread or a waiting treatment; never a heading, title or status line). Give a level whenever a cancer is recorded; 0 only when no cancer "
            "is recorded. It is a suggestion: the consultant decides.")
    user = (f"Patient: {agesex or 'age and sex not recorded'}.\n\nCHECKLISTS (id: label (settings)):\n" + "\n".join(lines)
            + f"\n\nREPORTS (newest first, {len(blocks)} of them):\n\n" + "\n\n".join(blocks) + "\n\n" + task)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---- what a quote supports --------------------------------------------------------------------------------------------------------
# A quote found word for word proves only that the words are in a report. These rules check that the words also say what the value
# says (review of 17 Nov 2026: "Carcinoma of the RIGHT breast" kept on a quote about the left breast, "metastatic" on "Report status:
# FINAL", urgency 5 on "HISTOPATHOLOGY REPORT", the lung checklist on a breast report). Each rule is a set of regular expressions over
# the quote in lower case; acronyms (AML, ALL, CUP, NHL) are matched on the quote as written, so the English word "all" never reads as
# ALL. When no rule fits, or the words are negated or hedged ("no evidence of", "suspicious for"), the value is dropped: a dropped
# suggestion costs the doctor one click, a wrong one may be believed.

def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts))


def _caps(*parts: str) -> re.Pattern:
    """Acronyms, matched on the quote as written (case kept)."""
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


# Words that say "this is a cancer" (a mass or a node alone is not a diagnosis to start a Case File on).
CANCER_WORDS = _rx(r"carcinom", r"cancer", r"malignan", r"sarcom", r"neoplas", r"tumou?r", r"blastom", r"melanom", r"mesotheliom",
                   r"seminom", r"germinom", r"thymom", r"myelom", r"lymphom", r"leuka?emi", r"gliom", r"astrocytom", r"ependymom",
                   r"meningiom", r"hepatom", r"wilms", r"hodgkin", r"teratom", r"ewing", r"\bdcis\b", r"\blcis\b")
CANCER_CAPS = _caps(r"AML", r"ALL", r"APML", r"APL", r"CLL", r"CML", r"NHL", r"DLBCL", r"HCC", r"RCC", r"NSCLC", r"MDS")

# The words that place a quote at the site of each checklist: {protocol: (words, acronyms or None, words that rule it out or None)}.
SITE = {
    "bone_sarcoma": (_rx(r"osteosarc", r"\bewing", r"chondrosarc", r"\bbone\b"), None, None),
    "brain_cns": (_rx(r"\bbrain", r"cerebr", r"cerebell", r"gliom", r"glioblastom", r"astrocyt", r"oligodendro", r"meningiom",
                      r"medulloblast", r"ependym", r"\bcns\b", r"intracranial", r"craniopharyng", r"schwannom", r"pituitar"), None, None),
    "breast": (_rx(r"\bbreast", r"\bmammary"), None, None),
    "cervix": (_rx(r"\bcervix", r"\bcervical\b(?!\s+(?:lymph|node|spine|vertebr|region|level))", r"endocervi", r"ectocervi"), None, None),
    "colorectal_colon": (_rx(r"\bcolon\b", r"\bcolonic", r"\bca?ecum\b", r"\bca?ecal\b", r"\bsigmoid", r"\bflexure", r"ileoca?ecal"), None, None),
    "colorectal_rectum": (_rx(r"\brectum\b", r"\brectal\b", r"\banal verge"), None, None),
    "corpus_uteri": (_rx(r"endometri", r"\bcorpus\b", r"\buterus\b", r"\buterine\b"), None, _rx(r"\bcervix", r"\bcervical\b")),
    "cup": (_rx(r"unknown primary", r"undefined primary", r"occult primary", r"primary (?:is )?not (?:known|identified|found)"), _caps(r"CUP", r"MUO"), None),
    "gallbladder": (_rx(r"gall ?bladder", r"cholecyst"), _caps(r"GB", r"GBC"), None),
    "germ_cell": (_rx(r"\btestis\b", r"\btestes\b", r"testicular", r"seminom", r"germ cell", r"yolk sac", r"teratom", r"embryonal carc",
                      r"choriocarc"), None, None),
    "kidney": (_rx(r"\bkidney", r"\brenal\b", r"nephrectomy", r"clear cell renal"), _caps(r"RCC", r"ccRCC"), _rx(r"wilms", r"nephroblastom")),
    "larynx": (_rx(r"laryn", r"glott", r"vocal (?:cord|fold)"), None, None),
    "leukaemia": (_rx(r"leuka?emi", r"blast crisis"), _caps(r"AML", r"ALL", r"APML", r"APL", r"CLL", r"CML", r"B-ALL", r"T-ALL"), None),
    "liver_hcc": (_rx(r"hepatocellular", r"hepatoma"), _caps(r"HCC"), None),
    "lung_nsclc": (_rx(r"\blungs?\b", r"pulmonary", r"bronch", r"non[- ]?small[- ]cell"), _caps(r"NSCLC"),
                   _rx(r"(?<!non[- ])(?<!non)\bsmall[- ]cell (?:lung )?(?:carcinoma|cancer)")),
    "lymphoma": (_rx(r"lymphom", r"hodgkin"), _caps(r"NHL", r"DLBCL", r"HL"), None),
    "oesophagus": (_rx(r"o?esophag", r"gastro-?o?esophageal junction"), _caps(r"GEJ", r"OGJ", r"GOJ"), None),
    "oral_cavity": (_rx(r"\boral\b", r"\btongue", r"\bbuccal", r"gingiv", r"\bmouth\b", r"\balveolus\b", r"retromolar", r"\bpalat",
                        r"\blips?\b", r"\bcheek"), None, None),
    "ovary": (_rx(r"\bovar", r"\badnex", r"fallopian", r"tubo-?ovarian", r"primary peritoneal"), None, None),
    "prostate": (_rx(r"prostat", r"gleason"), None, None),
    "retinoblastoma": (_rx(r"retinoblastom", r"\bretina", r"\bretinal\b"), None, None),
    "soft_tissue_sarcoma": (_rx(r"soft tissue", r"rhabdomyosarc", r"liposarc", r"leiomyosarc", r"synovial sarc", r"fibrosarc", r"\bsarcoma\b"),
                            _caps(r"MPNST", r"STS"), _rx(r"osteosarc", r"\bewing", r"chondrosarc")),
    "stomach": (_rx(r"\bstomach", r"\bgastric\b", r"\bantr(?:um|al)\b", r"pylor", r"\bcardia\b", r"(?:lesser|greater) curvature"), None, None),
    "wilms": (_rx(r"wilms", r"nephroblastom"), None, None),
    "generic": (CANCER_WORDS, CANCER_CAPS, None),
    "generic_haem": (_rx(r"leuka?emi", r"lymphom", r"myelom", r"myelodysplas", r"myeloprolif", r"myelofibros", r"polycyth", r"thrombocyth",
                         r"macroglobulin", r"plasma cell", r"mastocyt", r"histiocyt"), _caps(r"MDS", r"MPN", r"AML", r"ALL", r"CLL", r"CML", r"NHL"), None),
}
_LABEL_SKIP = {"cancer", "other", "adult", "child", "tumour", "tumours", "carcinoma", "with", "from", "and", "the"}

# "No evidence of", "suspicious for", "?": the words that follow are not stated as present. A clause ends at . ; or : (a comma does not
# end it: "no nodal, or distant, metastasis" stays negated).
NEGATED = re.compile(r"\b(?:no|not|without|negative|nil|free of|absence of|absent|ruled out|rule out|r/o|excluded?|cannot|could not)\b")
HEDGED = re.compile(r"\b(?:suspicious|suspected|suspicion|possible|possibly|probable|probably|likely|unlikely|query|equivocal|indeterminate|"
                    r"cannot be excluded|to be ruled out)\b|\?")
NEGATED_AFTER = re.compile(r"^[^.;:]{0,30}?\b(?:not (?:seen|identified|detected|found|present|noted)|ruled out|excluded|absent)\b")
NON = re.compile(r"\bnon[- ]?$")  # "non-metastatic", "non-Hodgkin": negates only the word it is joined to ("non-small cell carcinoma" is a carcinoma)


def _clause_before(q: str, i: int) -> str:
    before = q[max(0, i - 80):i]
    return re.split(r"[.;:]", before)[-1]


def _negated(clause: str, after: str) -> bool:
    return bool(NEGATED.search(clause) or NON.search(clause) or NEGATED_AFTER.search(after))


def _said(q: str, rx: re.Pattern, raw: str = "") -> bool:
    """`rx` matches the quote somewhere that is stated as present: not negated, not hedged (raw: the quote as written, for acronyms)."""
    text = raw if raw else q
    for m in rx.finditer(text):
        clause = _clause_before(text.lower(), m.start())
        after = text.lower()[m.end():m.end() + 40]
        if not _negated(clause, after) and not HEDGED.search(clause) and not after.startswith("?"):
            return True
    return False


def _denied(q: str, rx: re.Pattern) -> bool:
    """`rx` matches the quote somewhere that is stated as absent ("no evidence of distant metastasis", "non-metastatic"), not hedged."""
    for m in rx.finditer(q):
        clause = _clause_before(q, m.start())
        after = q[m.end():m.end() + 40]
        if _negated(clause, after) and not HEDGED.search(clause) and not after.startswith("?"):
            return True
    return False


def _low(quote: str) -> str:
    return " ".join(str(quote or "").lower().split())


def site_ok(quote: str, protocol_id: str, label: str = "") -> bool:
    """The quote names the site (or, for the two generic rules, the kind) of cancer of this checklist and says it is a cancer. A
    checklist with no word list here needs the main word of its label ("Thyroid cancer": thyroid)."""
    q = _low(quote)
    if not (_said(q, CANCER_WORDS) or _said(q, CANCER_CAPS, str(quote or ""))):
        return False
    words, caps, never = SITE.get(protocol_id) or (None, None, None)
    if words is None:
        main = [w for w in re.findall(r"[a-z]+", str(label or "").lower()) if len(w) >= 4 and w not in _LABEL_SKIP]
        if not main:
            return False
        words = re.compile(r"\b" + re.escape(main[0][:5]))
    if never is not None and never.search(q):
        return False
    return bool(words.search(q) or (caps is not None and caps.search(str(quote or ""))))


# Stage tokens after "stage" or "FIGO" ("FIGO 2018 stage IIIC1r", "Stage IVB"), and which of them each setting's label names.
STAGE = re.compile(r"\b(?:figo(?:\s*\d{4})?\s*(?:stage\s*)?|stage\s*)((?:iv|i{1,3})(?:[abc][0-9]?)?)[rp]?\b")
STAGE_EXACT = {
    ("cervix", "early"): {"ia", "ia1", "ia2", "ib1", "ib2", "iia1"},
    ("cervix", "locally_advanced"): {"ib3", "iia2", "iib", "iii", "iiia", "iiib", "iiic", "iiic1", "iiic2", "iva"},
    ("cervix", "metastatic"): {"ivb"},
    ("oral_cavity", "locally_advanced"): {"iii", "iva", "ivb"},
    ("oral_cavity", "metastatic"): {"ivc"},
}
STAGE_ROMAN = {
    ("corpus_uteri", "early"): {"i", "ii"}, ("corpus_uteri", "advanced"): {"iii", "iv"},
    ("oral_cavity", "early"): {"i", "ii"},
    ("ovary", "early"): {"i", "ii"}, ("ovary", "advanced"): {"iii", "iv"},
    ("germ_cell", "stage_i"): {"i"}, ("germ_cell", "stage_ii_iii"): {"ii", "iii"},
}


def _stage_ok(q: str, protocol_id: str, setting_id: str) -> bool:
    exact, roman = STAGE_EXACT.get((protocol_id, setting_id)), STAGE_ROMAN.get((protocol_id, setting_id))
    if not exact and not roman:
        return False
    for m in STAGE.finditer(q):
        tok = m.group(1)
        if exact and tok in exact:
            return True
        if roman and re.match(r"iv|i{1,3}", tok).group(0) in roman:
            return True
    return False


SPREAD = _rx(r"metasta", r"\bdistant (?:disease|spread|deposits?)", r"\bsecondar(?:y|ies) deposits?", r"\bsecondaries\b")
EARLY = _rx(r"\bearly[\s-]+(?:stage|breast|cervical|cervix|carcinoma|cancer|disease|invasive|operable|oral|ovarian|endometrial|laryngeal|glottic)")
LOCALLY_ADVANCED = _rx(r"locally[- ]advanced", r"loco-?\s?regionally[- ]advanced")
RECURRENT = _rx(r"recurren", r"relaps")
ACUTE = _rx(r"acute (?:myeloid|myelogenous|lymphoblastic|lymphocytic|promyelocytic)")
ACUTE_CAPS = _caps(r"AML", r"ALL", r"APML", r"APL", r"B-ALL", r"T-ALL")
CHRONIC = _rx(r"chronic (?:myeloid|myelogenous|lymphocytic|lymphoid)")
CHRONIC_CAPS = _caps(r"CLL", r"CML")
NHL = _rx(r"non[- ]?hodgkin", r"dlbcl", r"diffuse large b", r"follicular lymphom", r"mantle cell", r"burkitt", r"lymphoblastic lymphom",
          r"marginal zone", r"[bt][- ]cell lymphom")
GLIOMA = _rx(r"gliom", r"glioblastom", r"astrocytom", r"oligodendrogliom")
BRAIN_OTHER = _rx(r"meningiom", r"schwannom", r"ependymom", r"pituitar", r"craniopharyngiom", r"ha?emangioblastom", r"cns lymphom", r"metasta")
BRAIN_CHILD = _rx(r"gliom", r"astrocytom", r"medulloblastom", r"ependymom", r"craniopharyngiom", r"germinom", r"\bdipg\b", r"\bbrain",
                  r"cerebell", r"\bcns\b", r"intracranial")
CUP = _rx(r"unknown primary")
CUP_CAPS = _caps(r"CUP")


def _age(patient) -> int | None:
    a = patient.get("age") if isinstance(patient, dict) else None
    m = re.search(r"\d+", str(a)) if a not in (None, "") else None
    return int(m.group(0)) if m else None


def setting_ok(quote: str, protocol_id: str, setting_id: str, patient: dict | None = None) -> bool:
    """The quote states this setting in words its label uses (or a stage its label names). A setting for an adult or a child also
    needs the patient's age on the right side of CHILD_AGE; no age, no such setting."""
    q, raw = _low(quote), str(quote or "")
    p, s = protocol_id, setting_id
    age = _age(patient)
    adult, child = age is not None and age >= CHILD_AGE, age is not None and age < CHILD_AGE
    said = lambda rx: _said(q, rx)
    caps = lambda rx: _said(q, rx, raw)
    stage = _stage_ok(q, p, s)
    if s == "metastatic":
        extra = said(RECURRENT) if p in ("cervix", "larynx", "oral_cavity") else False
        return said(SPREAD) or extra or stage
    if s == "metastatic_hspc":
        return said(SPREAD) and said(_rx(r"hormone[- ]sensitive", r"castration[- ]sensitive", r"hormone[- ]na[iï]ve", r"\bm?hspc\b", r"\bm?cspc\b"))
    if s == "metastatic_crpc":
        return said(_rx(r"\bmcrpc\b")) or (said(SPREAD) and said(_rx(r"castration[- ]resistant", r"\bcrpc\b")))
    if s == "non_metastatic":
        return _denied(q, SPREAD) or said(_rx(r"\bm0\b"))
    if s == "localised":
        return said(_rx(r"locali[sz]ed", r"organ[- ]confined")) or (p == "kidney" and _denied(q, SPREAD))
    if s == "locally_extensive":
        return said(_rx(r"locally extensive", r"\b[cp]?t3b\b", r"\bcn1\b"))
    if s == "early":
        return said(EARLY) or (p == "breast" and said(_rx(r"\boperable\b"))) or stage
    if s == "early_localized":
        return said(EARLY) or said(_rx(r"\blocali[sz]ed (?:disease|tumou?r|cancer|carcinoma)"))
    if s == "locally_advanced":
        return said(LOCALLY_ADVANCED) or stage
    if s == "advanced":
        return said(_rx(r"\badvanced\b")) or said(SPREAD) or stage
    if s in ("recurrent", "relapsed"):
        return said(RECURRENT)
    if s in ("stage_i", "stage_ii_iii"):
        return stage
    if s in ("osteosarcoma", "ewing", "chondrosarcoma"):
        return said({"osteosarcoma": _rx(r"osteosarc"), "ewing": _rx(r"\bewing"), "chondrosarcoma": _rx(r"chondrosarc")}[s])
    if s == "adult_glioma":
        return adult and said(GLIOMA)
    if s == "adult_other":
        return adult and said(BRAIN_OTHER)
    if s == "child" and p == "brain_cns":
        return child and said(BRAIN_CHILD)
    if s == "muo":
        return said(_rx(r"undefined primary", r"\bmuo\b"))
    if s in ("provisional_cup", "confirmed_cup"):
        word = "provisional" if s == "provisional_cup" else "confirmed"
        return said(_rx(r"\b" + word + r"\b")) and (said(CUP) or caps(CUP_CAPS))
    if s == "per_primum":
        return said(_rx(r"per primum"))
    if s == "incidental":
        return said(_rx(r"incidental"))
    if s == "resectable":
        return said(_rx(r"\bresectable\b"))
    if s == "locoregional":
        return said(_rx(r"bilobar", r"multifocal", r"multicentric", r"inadequate (?:future )?(?:liver remnant|flr)"))
    if s in ("adult_acute", "child_acute"):
        return (adult if s == "adult_acute" else child) and (said(ACUTE) or caps(ACUTE_CAPS))
    if s == "adult_chronic":
        return adult and (said(CHRONIC) or caps(CHRONIC_CAPS))
    if s == "child_chronic":
        return child and (said(_rx(r"chronic myel")) or caps(_caps(r"CML")))
    if s in ("adult_hodgkin", "child_hodgkin"):
        return (adult if s == "adult_hodgkin" else child) and said(_rx(r"hodgkin")) and not said(NHL)
    if s in ("adult_nhl", "child_nhl"):
        return (adult if s == "adult_nhl" else child) and (said(NHL) or caps(_caps(r"NHL", r"DLBCL")))
    if s in ("unilateral", "bilateral"):
        return said(_rx(r"\b" + s))
    if s == "paediatric_rhabdomyosarcoma":
        return child and said(_rx(r"rhabdomyosarc"))
    return False  # a setting with no rule here: never suggested (the doctor picks it)


HEADING_WORDS = {"report", "reports", "status", "final", "preliminary", "provisional", "amended", "addendum", "page", "of", "hospital",
                 "department", "dept", "histopathology", "pathology", "radiology", "laboratory", "lab", "cytology", "consultation", "note",
                 "opd", "ipd", "discharge", "summary", "name", "uhid", "mrn", "age", "sex", "date", "time", "signed", "by", "dr", "synthetic",
                 "demo", "the", "and", "a", "an", "to", "in", "on", "for", "no", "ip", "op", "ref", "referred", "specimen", "sample"}


def urgency_quote_ok(quote: str, src: dict) -> bool:
    """An urgency rests on a finding: at least MIN_URGENCY_WORDS words, not a status line ("Report status: FINAL"), not the report's
    title, not an all-capitals heading line of the report ("HISTOPATHOLOGY REPORT", "CECT THORAX ABDOMEN PELVIS"), and at least three
    words that are not heading words."""
    words = re.findall(r"[A-Za-z0-9]+", str(quote or ""))
    if len(words) < MIN_URGENCY_WORDS:
        return False
    q = grounding.norm(quote).strip(" .:;,")
    if re.match(r"(?:report )?status\b", q) or q == grounding.norm(src.get("title") or "").strip(" .:;,"):
        return False
    if len([w for w in words if w.lower() not in HEADING_WORDS and not w.isdigit()]) < 3:
        return False
    letters = re.sub(r"[^A-Za-z]", "", str(quote))
    if letters and letters.isupper() and ":" not in str(quote):
        lines = {grounding.norm(x).strip(" .:;,") for x in str(src.get("text") or "").splitlines()}
        if q in lines:
            return False
    return True


def name_from(name: str, quote: str) -> str:
    """The cancer's name as the report words it: the model's name when it is inside the quote (case, spacing and punctuation aside),
    else the first sentence of the quote without a leading label ("Diagnosis:") or trailing punctuation, when that fits the 80
    characters of the name box; "" when neither does (the cancer is then dropped)."""
    if name and grounding.norm(name) in grounding.norm(quote):
        return name
    words = _s(quote)
    head, sep, rest = words.partition(":")
    if sep and len(head.split()) <= 3 and rest.strip():
        words = rest.strip()
    words = re.split(r"(?<=[a-z0-9)])\.\s", words, maxsplit=1)[0].strip(" .;:,")
    return words if 2 <= len(words) <= 80 else ""


# ---- checking the answer --------------------------------------------------------------------------------------------------------

def _s(v, n: int = 400) -> str:
    return " ".join(str(v or "").split())[:n]


def find_quote(quote: str, named: str, reports: list) -> dict | None:
    """The report whose text holds the quote word for word (grounding.norm on both sides): the named report first, then any other
    report read. None when the quote is too short to prove anything (MIN_QUOTE characters and MIN_QUOTE_WORDS words) or is found
    nowhere."""
    q = grounding.norm(quote)
    if len(q) < MIN_QUOTE or len(re.findall(r"[a-z0-9]+", q)) < MIN_QUOTE_WORDS:
        return None
    order = sorted(reports, key=lambda r: r["id"] != str(named or "").strip().upper())
    for r in order:
        if q in grounding.norm(r["text"]):
            return r
    return None


def _source(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "date": r["date"], "department": r["department"]}


def check(raw, reports: list, checklists: list, patient: dict | None = None) -> tuple[dict, list]:
    """The model's answer checked: (kept values, dropped [{field, reason}]). See the module docstring for each rule; `patient` gives
    the age that an adult or child setting needs."""
    raw = raw if isinstance(raw, dict) else {}
    out, dropped = {}, []
    known = {c["id"]: c for c in checklists}
    c = raw.get("cancer") if isinstance(raw.get("cancer"), dict) else {}
    name, pid, quote = _s(c.get("name"), 80), _s(c.get("protocol"), 40).lower(), _s(c.get("quote"))
    if name or pid:
        src = find_quote(quote, c.get("report"), reports) if quote else None
        if pid not in known:
            dropped.append({"field": "cancer", "reason": f"not one of the checklists ({pid or 'none given'})"})
        elif not src:
            dropped.append({"field": "cancer", "reason": "the quote was not found in the reports" if quote else "no quote given"})
        elif not site_ok(quote, pid, known[pid]["label"]):
            dropped.append({"field": "cancer", "reason": f"the quote does not name a cancer of the {known[pid]['label']} checklist"})
        elif not name_from(name, quote):
            dropped.append({"field": "cancer", "reason": "the name is not in the words of the quote"})
        else:
            ent = {"name": name_from(name, quote), "protocol": pid, "label": known[pid]["label"], "quote": quote, "report": _source(src)}
            if pid in VARIANTS:
                ent["entry"], ent["variant"] = VARIANTS[pid]
            out["cancer"] = ent
    s = raw.get("setting") if isinstance(raw.get("setting"), dict) else {}
    sid, squote = _s(s.get("id"), 60), _s(s.get("quote"))
    if sid and sid.lower() not in ("not_recorded", "not recorded", "none", "unknown"):
        cancer = out.get("cancer")
        sets = {x["id"]: x["label"] for x in (known.get(cancer["protocol"], {}).get("settings") or [])} if cancer else {}
        src = find_quote(squote, s.get("report"), reports) if squote else None
        if not cancer:
            dropped.append({"field": "setting", "reason": "no cancer was kept to hang the setting on"})
        elif cancer["protocol"] in protocol.GENERIC_IDS:
            pass  # the generic rule has one setting ("as recorded"): nothing to suggest
        elif sid not in sets:
            dropped.append({"field": "setting", "reason": f"{sid} is not a setting of the {cancer['label']} checklist"})
        elif not src:
            dropped.append({"field": "setting", "reason": "the quote was not found in the reports" if squote else "no quote given"})
        elif not setting_ok(squote, cancer["protocol"], sid, patient):
            dropped.append({"field": "setting", "reason": f"the quote does not state {sets[sid]}"})
        else:
            out["setting"] = {"id": sid, "label": sets[sid], "quote": squote, "report": _source(src)}
    q = raw.get("board_question") if isinstance(raw.get("board_question"), dict) else {}
    text = _s(q.get("text"), QUESTION_MAX)
    if text:
        ids = {r["id"]: r for r in reports}
        basis = []
        for b in q.get("basis") or []:
            m = re.search(r"R\d+", str(b).upper())
            if m and m.group(0) in ids and _source(ids[m.group(0)]) not in basis:
                basis.append(_source(ids[m.group(0)]))
        out["board_question"] = {"text": text, "basis": basis, "draft": True}
    u = raw.get("urgency") if isinstance(raw.get("urgency"), dict) else {}
    level, uquote = u.get("level"), _s(u.get("quote"))
    try:
        level = int(level) if level not in (None, "", 0, "0") else 0
    except (TypeError, ValueError):
        level = -1
    if level:
        src = find_quote(uquote, u.get("report"), reports) if uquote else None
        if not 1 <= level <= 5:
            dropped.append({"field": "urgency", "reason": "urgency must be 1 to 5"})
        elif not src:
            dropped.append({"field": "urgency", "reason": "the quote was not found in the reports" if uquote else "no quote given"})
        elif not urgency_quote_ok(uquote, src):
            dropped.append({"field": "urgency", "reason": "the quote is a heading or a status line, not a finding"})
        else:
            out["urgency"] = {"level": level, "reason": _s(u.get("reason"), REASON_MAX), "quote": uquote, "report": _source(src)}
    return out, dropped


def department_for(roles: dict, encounters: list) -> dict | None:
    """The owning department suggested WITHOUT the model: the doctor's own treating departments that appear in the patient's visits;
    exactly one such department is suggested, with the visit that shows it. None for none or several."""
    treating = set(((roles or {}).get("treating") or {}).keys())
    seen: dict = {}
    for e in encounters or []:
        did = org.department_id(str(e.get("department") or "")) if e.get("department") else None
        if did and did in treating:
            seen.setdefault(did, e)
    if len(seen) != 1:
        return None
    did, e = next(iter(seen.items()))
    visit = " ".join(x for x in (str(e.get("kind") or ""), "visit" if e.get("kind") else "", str(e.get("number") or "")) if x).strip()
    when = his_case.dmy(e.get("start")) if e.get("start") else ""
    return {"id": did, "name": org.department_name(did),
            "why": "Your department in the patient's visits" + (f": {visit}" if visit else "") + (f" on {when}" if when else "")}


def model_info() -> dict:
    m = config.models().get("reasoner") or {}
    return {"label": m.get("label") or "reasoner", "origin": m.get("origin") or "", "medical": m.get("medical")}


async def prefill(identifier: str, window: dict, user: str, roles: dict) -> dict:
    """The whole pre-fill for one lookup: find, read, ask, check, audit. Raises HISCaseError / HISError / LLMError (the job turns
    them into a plain failure)."""
    client = his_case._client()
    p = await client.find_patient(identifier)
    if not p:
        raise his_case.HISCaseError(NOT_FOUND, 404)
    encs = await client.encounters(p["id"])
    reports = await client.reports(p["id"])
    start_day = his_case.window_start(window)
    inside = [r for r in reports if r.get("current", True) and r.get("document_ref") and his_case._in_window(r, start_day)]
    inside.sort(key=lambda r: (_day(r), str(r.get("last_updated") or "")), reverse=True)
    picked = inside[:MAX_REPORTS]
    read, skipped = await _read(client, picked)
    uhid = p.get("uhid") or identifier
    result = {"uhid": uhid, "model": model_info(), "reports_in_window": len(inside), "reports_read": len(read), "reports_skipped": skipped,
              "reports": [_source(r) for r in read], "dropped": []}
    dept = department_for(roles, encs)
    if dept:
        result["department"] = dept
    if read:
        checklists = _checklists()

        def au(ev):
            org.audit(ev.get("kind") or "llm_call", user, purpose=PURPOSE, uhid=uhid, **{k: v for k, v in ev.items() if k not in ("kind", "purpose")})
        raw = await llm.chat("reasoner", messages(p, read, checklists), json_schema=SCHEMA, max_tokens=MAX_TOKENS, temperature=0.0,
                             purpose=PURPOSE, audit=au)
        kept, dropped = check(raw, read, checklists, p)
        result.update(kept)
        result["dropped"] = dropped
    filled = [k for k in ("cancer", "setting", "board_question", "urgency", "department") if k in result]
    org.audit("case_prefill", user, uhid=uhid, fields=filled, dropped=len(result["dropped"]), reports=len(read), skipped=skipped)
    return result
