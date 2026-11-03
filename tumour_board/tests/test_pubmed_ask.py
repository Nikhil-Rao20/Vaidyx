"""Ask PubMed (3 Nov 2026, docs/pubmed-ask/DESIGN.md): worst cases of the whole question. PubMed is an httpx.MockTransport passed through
client= (esearch JSON and efetch XML as NCBI sends them, DOCTYPE line included) and the model a scripted fake of llm.chat, so nothing
leaves the machine. The rules under test: questions about a patient, advice, opinions and identifiers are refused before any call; the
search words never carry an identifier; papers come only from PubMed (retracted papers and retraction notices listed, never read); every
statement keeps a PMID that was read and a quote found word for word; numbers and trial names must be the papers'; no advice and no patient
in Vaidyx's own words; PubMed down or the model down means "unavailable", never an answer from memory."""
import asyncio
import copy
import hashlib
import json
from datetime import datetime
from xml.sax.saxutils import escape

import httpx
import pytest

from tumour_board import llm, pubmed
from tumour_board import pubmed_ask as pa

# ---- PubMed's records (synthetic papers; the shape is NCBI's efetch XML) -------------------------------------------------------------
DOCTYPE = ('<?xml version="1.0" ?>\n<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN" '
           '"https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd">\n')


def article(pmid, title, sections, journal, abbr, pubdate, authors, types, refs=(), doi="", pmc=""):
    abstract = ""
    if sections:
        abstract = "<Abstract>" + "".join(
            f'<AbstractText Label="{lab}" NlmCategory="{lab}">{escape(txt)}</AbstractText>' if lab else f"<AbstractText>{escape(txt)}</AbstractText>"
            for lab, txt in sections) + "<CopyrightInformation>Copyright 2024 the authors. COPYRIGHT_LINE.</CopyrightInformation></Abstract>"
    au = "".join(
        (f'<Author ValidYN="{a.get("valid", "Y")}"><LastName>{a["last"]}</LastName><ForeName>{a["fore"]}</ForeName><Initials>{a["init"]}</Initials>'
         + (f'<AffiliationInfo><Affiliation>{escape(a["aff"])}</Affiliation></AffiliationInfo>' if a.get("aff") else "") + "</Author>")
        if "last" in a else f'<Author ValidYN="Y"><CollectiveName>{a["group"]}</CollectiveName></Author>' for a in authors)
    pt = "".join(f'<PublicationType UI="D0{i:05d}">{t}</PublicationType>' for i, t in enumerate(types))
    cc = ("<CommentsCorrectionsList>" + "".join(f'<CommentsCorrections RefType="{r}"><RefSource>Breast Cancer Res Treat. 2024;205:1.</RefSource>'
                                                f'<PMID Version="1">39000999</PMID></CommentsCorrections>' for r in refs) + "</CommentsCorrectionsList>") if refs else ""
    ids = f'<ArticleId IdType="pubmed">{pmid}</ArticleId>' + (f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else "") + (
        f'<ArticleId IdType="pmc">{pmc}</ArticleId>' if pmc else "")
    return (f'<PubmedArticle><MedlineCitation Status="MEDLINE" Owner="NLM" IndexingMethod="Automated"><PMID Version="1">{pmid}</PMID>'
            f'<DateCompleted><Year>2024</Year><Month>01</Month><Day>15</Day></DateCompleted>'
            f'<Article PubModel="Print-Electronic"><Journal><ISSN IssnType="Electronic">1573-7217</ISSN><JournalIssue CitedMedium="Internet">'
            f'<Volume>201</Volume><Issue>3</Issue><PubDate>{pubdate}</PubDate></JournalIssue><Title>{journal}</Title>'
            f'<ISOAbbreviation>{abbr}</ISOAbbreviation></Journal><ArticleTitle>{escape(title)}</ArticleTitle><Pagination><MedlinePgn>401-412</MedlinePgn>'
            f'</Pagination>{abstract}<AuthorList CompleteYN="Y">{au}</AuthorList><Language>eng</Language><PublicationTypeList>{pt}</PublicationTypeList>'
            f'</Article><MedlineJournalInfo><Country>Netherlands</Country><MedlineTA>{abbr}</MedlineTA></MedlineJournalInfo>{cc}'
            f'<MeshHeadingList><MeshHeading><DescriptorName UI="D064726" MajorTopicYN="Y">Triple Negative Breast Neoplasms</DescriptorName>'
            f'</MeshHeading></MeshHeadingList></MedlineCitation><PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2024</Year>'
            f'<Month>1</Month><Day>2</Day></PubMedPubDate></History><PublicationStatus>ppublish</PublicationStatus><ArticleIdList>{ids}'
            f'</ArticleIdList></PubmedData></PubmedArticle>')


P1_TITLE = "Neoadjuvant pembrolizumab plus chemotherapy in early triple-negative breast cancer: a systematic review and meta-analysis."
P1_RESULTS = ("Twelve trials with 4120 patients were included. The pooled pathological complete response rate was 64.8% with pembrolizumab and "
              "51.2% with chemotherapy alone (risk ratio 1.27, 95% CI 1.15–1.40). Grade 3 or higher adverse events occurred in 77.1% of patients.")
P2_TITLE = "Event-free survival with neoadjuvant pembrolizumab in early triple-negative breast cancer (KEYNOTE-522): a randomised, double-blind, phase 3 trial."
P3_TITLE = "Pembrolizumab cures triple-negative breast cancer in 99% of patients: a randomised trial."
P3_SECRET = "All 99 of 100 patients were cured with a single dose of pembrolizumab."
P4_TITLE = "Retraction notice to: Pembrolizumab cures triple-negative breast cancer in 99% of patients."
P6_TITLE = ("Neoadjuvant chemotherapy with pembrolizumab in triple-negative breast cancer: a single-arm phase 2 study from a tertiary cancer "
            "centre in India.")
ART = {
    "39000101": article("39000101", P1_TITLE, [
        ("BACKGROUND", "Triple-negative breast cancer lacks oestrogen receptor, progesterone receptor and HER2 expression. Immune checkpoint "
                       "inhibitors have been added to neoadjuvant chemotherapy."),
        ("METHODS", "We searched PubMed, Embase and CENTRAL for randomised trials published up to March 2023."),
        ("RESULTS", P1_RESULTS),
        ("CONCLUSIONS", "Adding pembrolizumab to neoadjuvant chemotherapy increased the pathological complete response rate. These results support "
                        "pembrolizumab as the preferred treatment for high-risk early triple-negative breast cancer. Longer follow-up of event-free "
                        "survival is needed.")],
        "Breast cancer research and treatment", "Breast Cancer Res Treat", "<Year>2023</Year><Month>Oct</Month>",
        [{"last": "Menon", "fore": "Asha", "init": "A", "aff": "Department of Oncology, Kerala, India."}, {"last": "Fischer", "fore": "Lena", "init": "L"}],
        ["Journal Article", "Meta-Analysis", "Systematic Review"], doi="10.1007/s10549-023-00001-1", pmc="PMC10000001"),
    "39000102": article("39000102", P2_TITLE, [
        ("BACKGROUND", "In the phase 3 KEYNOTE-522 trial, pembrolizumab plus neoadjuvant chemotherapy improved the pathological complete response "
                       "rate in early triple-negative breast cancer."),
        ("METHODS", "A total of 1174 patients were randomly assigned in a 2:1 ratio to pembrolizumab or placebo every 3 weeks."),
        ("RESULTS", "At 36 months, event-free survival was 84.5% in the pembrolizumab group and 76.8% in the placebo group (hazard ratio 0.63; "
                    "95% CI 0.48 to 0.82)."),
        ("CONCLUSIONS", "Pembrolizumab improved event-free survival.")],
        "The New England journal of medicine", "N Engl J Med", "<Year>2022</Year><Month>Feb</Month><Day>10</Day>",
        [{"last": "Ray", "fore": "Sunita", "init": "S", "aff": "Oncology Unit, Boston, USA."}, {"last": "Bose", "fore": "Pia", "init": "P"},
         {"last": "Ghost", "fore": "Withdrawn", "init": "W", "valid": "N"}, {"last": "Das", "fore": "Kiran", "init": "K"},
         {"group": "KEYNOTE-522 Investigators"}],
        ["Clinical Trial, Phase III", "Journal Article", "Multicenter Study", "Randomized Controlled Trial"], doi="10.1056/NEJMoa0000002"),
    "39000103": article("39000103", P3_TITLE, [("", P3_SECRET)], "Breast cancer research and treatment", "Breast Cancer Res Treat",
                        "<Year>2021</Year>", [{"last": "Fake", "fore": "Fran", "init": "F"}], ["Journal Article", "Randomized Controlled Trial"],
                        refs=("RetractionIn",)),
    "39000104": article("39000104", P4_TITLE, [("", "This article has been retracted at the request of the editors. RETRACTION_NOTICE_TEXT.")],
                        "Breast cancer research and treatment", "Breast Cancer Res Treat", "<Year>2024</Year>", [{"group": "The Editors"}],
                        ["Retraction of Publication"], refs=("RetractionOf",)),
    "39000105": article("39000105", "Pembrolizumab in triple-negative breast cancer: a letter. LETTER_TITLE_TEXT", [], "Lancet oncology",
                        "Lancet Oncol", "<Year>2024</Year>", [{"last": "Letter", "fore": "Lee", "init": "L"}], ["Letter", "Comment"],
                        refs=("CommentOn",)),
    "39000106": article("39000106", P6_TITLE, [
        ("", "This phase 2 study enrolled 64 women with stage II or III triple-negative breast cancer. Pathological complete response was seen "
             "in 29 of 64 women (45.3%). Neutropenia was the most common grade 3 toxicity.")],
        "Indian journal of cancer", "Indian J Cancer", "<MedlineDate>2021 Jan-Feb</MedlineDate>",
        [{"last": "Iyer", "fore": "Lakshmi", "init": "L", "aff": "Department of Medical Oncology, Vaidyx Demo Cancer Institute, Pune, India."}],
        ["Clinical Trial, Phase II", "Journal Article"], doi="10.4103/ijc.ijc_106_21"),
}
IDS = ["39000106", "39000105", "39000102", "39000103", "39000101", "39000104"]  # PubMed's Best Match order
READ_IDS = ["39000101", "39000106", "39000102"]  # tier first (meta-analysis, then the trials in PubMed's order)


def efetch_xml(pmids) -> bytes:
    return (DOCTYPE + "<PubmedArticleSet>" + "".join(ART[p] for p in pmids if p in ART) + "</PubmedArticleSet>").encode()


def esearch_json(ids, term, count=None) -> bytes:
    r = {"count": str(len(ids) if count is None else count), "retmax": str(len(ids)), "retstart": "0", "idlist": list(ids),
         "translationset": [{"from": "pembrolizumab", "to": "\"pembrolizumab\"[Supplementary Concept] OR \"pembrolizumab\"[All Fields]"}],
         "querytranslation": f"{term}[All Fields]"}
    if not ids:
        r["errorlist"] = {"phrasesnotfound": [], "fieldsnotfound": []}
        r["warninglist"] = {"phrasesignored": [], "quotedphrasesnotfound": [], "outputmessages": ["No items found."]}
    return json.dumps({"header": {"type": "esearch", "version": "0.3"}, "esearchresult": r}).encode()


def PAPERS(ids=READ_IDS):
    return {p["pmid"]: p for p in pubmed.parse(efetch_xml(ids))}


class Remote:
    """NCBI E-utilities behind an httpx.MockTransport: records every request and every body sent. ids(term, years_limited) gives the ids
    of a search; esearch / efetch, when set, answer instead (a function of the request returning an httpx.Response)."""

    def __init__(self, ids=None, count=148):
        self.seen, self.sent = [], []
        self.ids = ids or (lambda term, limited: IDS)
        self.count = count
        self.esearch = self.efetch = None

    def handler(self, request: httpx.Request):
        self.seen.append(request)
        p = dict(request.url.params)
        if request.url.path.endswith("/esearch.fcgi"):
            if self.esearch:
                return self.esearch(request)
            ids = list(self.ids(p["term"], "mindate" in p))
            body = esearch_json(ids, p["term"], self.count if ids else 0)
        elif request.url.path.endswith("/efetch.fcgi"):
            if self.efetch:
                return self.efetch(request)
            body = efetch_xml(p["id"].split(","))
        else:
            return httpx.Response(404)
        self.sent.append(body)
        return httpx.Response(200, content=body)

    def paths(self):
        return [r.url.path.rsplit("/", 1)[-1] for r in self.seen]

    def terms(self):
        return [dict(r.url.params)["term"] for r in self.seen if r.url.path.endswith("esearch.fcgi")]


# ---- the model: a scripted fake of llm.chat ------------------------------------------------------------------------------------------
QUESTION = ("What pathological complete response and event-free survival did trials report with neoadjuvant pembrolizumab in "
            "triple-negative breast cancer?")
QUERY = '(pembrolizumab) AND ("triple-negative breast cancer" OR TNBC) AND neoadjuvant'
BROADER = "pembrolizumab AND triple-negative breast cancer"
WORDS = {"kind": "general", "query": QUERY, "broader_query": BROADER}
Q1 = "The pooled pathological complete response rate was 64.8% with pembrolizumab"
S_META = {"text": "A meta-analysis of twelve trials reported a pooled pathological complete response rate of 64.8% with pembrolizumab and "
                  "51.2% with chemotherapy alone.",
          "citations": [{"pmid": "39000101", "quote": "The pooled pathological complete response rate was 64.8% with pembrolizumab and 51.2% with "
                                                      "chemotherapy alone"}]}
S_TRIAL = {"text": "In the phase 3 KEYNOTE-522 trial, event-free survival at 36 months was 84.5% with pembrolizumab and 76.8% with placebo.",
           "citations": [{"pmid": "39000102", "quote": "At 36 months, event-free survival was 84.5% in the pembrolizumab group and 76.8% in the "
                                                       "placebo group"}]}
S_INDIA = {"text": "A phase 2 study from India reported pathological complete response in 29 of 64 women.",
           "citations": [{"pmid": "39000106", "quote": "Pathological complete response was seen in 29 of 64 women (45.3%)"}]}
S_RETRACTED = {"text": "A trial reported that 99 of 100 patients were cured.", "citations": [{"pmid": "39000103", "quote": P3_SECRET}]}
S_PARAPHRASE = {"text": "Pembrolizumab doubled the response rate.", "citations": [{"pmid": "39000101", "quote": "Pembrolizumab doubled the response rate"}]}
ANSWER = {"answer_found": True, "statements": [S_META, S_TRIAL, S_INDIA, S_RETRACTED, S_PARAPHRASE]}


class FakeLLM:
    """llm.chat: answers by purpose with a scripted value, an exception to raise, or a function of the messages."""

    def __init__(self, words=WORDS, answer=ANSWER):
        self.script = {"pubmed search words": words, "pubmed answer": answer}
        self.calls = []

    async def __call__(self, role, messages, *, json_schema=None, max_tokens=1024, temperature=0.0, purpose="", audit=None, **kw):
        self.calls.append({"role": role, "purpose": purpose, "messages": copy.deepcopy(messages), "schema": json_schema})
        assert purpose in self.script, f"unexpected model call: {purpose}"
        r = self.script[purpose]
        if isinstance(r, BaseException) or (isinstance(r, type) and issubclass(r, BaseException)):
            raise r
        if callable(r):
            r = r(messages)
        return copy.deepcopy(r)

    def purposes(self):
        return [c["purpose"] for c in self.calls]

    def prompt(self, purpose):
        return "\n".join(m["content"] for c in self.calls if c["purpose"] == purpose for m in c["messages"])


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """No pace, no back-off, the cache and the settings in tmp_path, no real model and no real network."""
    monkeypatch.setattr(pubmed, "DELAYS", (0.0, 0.0, 0.0))

    async def no_wait(has_key):
        return None
    monkeypatch.setattr(pubmed, "_turn", no_wait)
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "pubmed_cache")
    monkeypatch.setattr(pubmed, "SETTINGS", tmp_path / "pubmed.json")
    monkeypatch.delenv("TB_PUBMED_EMAIL", raising=False)
    monkeypatch.delenv("TB_PUBMED_API_KEY", raising=False)

    def no_network():
        raise AssertionError("a real PubMed client was made")
    monkeypatch.setattr(pubmed, "_client", no_network)

    async def no_model(*a, **k):
        raise AssertionError("a real model call")
    monkeypatch.setattr(llm, "chat", no_model)


@pytest.fixture
def model(monkeypatch):
    m = FakeLLM()
    monkeypatch.setattr(llm, "chat", m)
    return m


@pytest.fixture
def remote():
    return Remote()


def ask(remote, question=QUESTION, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(remote.handler)) as c:
            return await pa.ask(question, client=c, **kw)
    return asyncio.run(go())


def by_pmid(out):
    return {p["pmid"]: p for p in out["papers"]}


# ---- 1. the scope check --------------------------------------------------------------------------------------------------------------
NAME = ["SYNTHETIC, Ramesh Kumar", "SYN-100231", "VXH/2026/000123"]
REFUSED = [
    ("Should we give adjuvant pembrolizumab after a pathological complete response?", "advice"),
    ("What would you do for node-positive triple-negative breast cancer?", "advice"),
    ("Do you agree with neoadjuvant chemotherapy here?", "advice"),
    ("What is your opinion on neoadjuvant pembrolizumab?", "advice"),
    ("Could we start pembrolizumab now?", "advice"),
    ("Is she a candidate for surgery?", "about_patient"),
    ("What is her survival?", "about_patient"),
    ("What is this patient's prognosis?", "about_patient"),
    ("Is the patient fit for chemotherapy?", "about_patient"),
    ("Will he respond to immunotherapy?", "about_patient"),
    ("What is her ER status?", "records"),
    ("Look at this CT and tell me the size.", "scan"),
    ("Can you interpret these MRI images?", "scan"),
    ("Survival in trials of pembrolizumab 1234567", "identifier"),
    ("Outcomes of breast surgery done on 12/03/2026", "identifier"),
    ("Outcomes of breast surgery done on 12-03-26", "identifier"),
    ("UHID lung cancer trials", "identifier"),
    ("Send the trials to dr.rao@example.org", "identifier"),
    ("Pembrolizumab trials in ramesh", "identifier"),
    ("KUMAR triple-negative breast cancer trials", "identifier"),
    ("pCR rates for SYN-100231", "identifier"),
]
ALLOWED = [
    "What response rates were reported for HER2-positive breast cancer?",
    "What did trials report for HER-2 positive gastric cancer with trastuzumab?",
    "What survival did trials report for HER 2 low breast cancer with trastuzumab deruxtecan?",
    "What does her2-low mean in published studies?",
    "What survival was reported in trials for stage III NSCLC with durvalumab after chemoradiation?",
    "What patient-reported outcomes were published after mastectomy?",
    "What did the systematic review of low-dose CT screening find?",
    "How did the patients in KEYNOTE-522 respond to pembrolizumab?",
    "What surgery outcomes were reported in Rameshwaram cohorts?",  # a name part only as a whole word
    "What did trials published in 2024 report on HE4 in ovarian cancer?",  # a year is not a date; HE4 is not "he"
]


@pytest.mark.parametrize("question,reason", REFUSED)
def test_scope_refuses_advice_patient_records_scan_and_identifiers(question, reason):
    g = pa.scope(question, identifiers=NAME)
    assert g["allowed"] is False and g["reason"] == reason
    assert g["message"] == {"advice": pa.REFUSED, "about_patient": pa.REFUSED, "scan": pa.REFUSED, "records": pa.RECORDS, "identifier": pa.IDENT}[reason]


@pytest.mark.parametrize("question", ALLOWED)
def test_scope_allows_general_questions(question):
    assert pa.scope(question, identifiers=NAME) == {"allowed": True, "reason": "general", "message": ""}


def test_scope_identifiers_none_and_short_parts_are_safe():
    assert pa.scope("What survival did trials report?", identifiers=[None, "", "AB", "Li"])["allowed"] is True
    assert pa.scope("What survival did trials report?", identifiers=None)["allowed"] is True


def test_scope_iso_date_is_an_identifier():
    # the docstring: "a date ... never leaves the server"; 2026-03-12 is the form HIS exports use
    assert pa.scope("Outcomes after breast surgery on 2026-03-12")["reason"] == "identifier"
    assert pa.query_ok("breast surgery AND 2026-03-12") is False
    assert pa.scope("Trials of pembrolizumab from 2015-2024")["allowed"] is True  # a range of years is not a date


@pytest.mark.parametrize("question,reason", REFUSED + [("", "empty"), ("   ", "empty"), ("?? 12", "empty"), (None, "empty")])
def test_refused_questions_make_no_pubmed_request_and_no_model_call(remote, model, question, reason):
    audit = []
    out = ask(remote, question, identifiers=NAME, audit=audit.append, in_case_file=True)
    assert out["status"] == "refused"
    assert remote.seen == [] and model.calls == []
    assert out["papers"] == [] and out["statements"] == [] and out["calls"] == [] and out["search"] == {}
    if reason == "empty":
        assert out["message"] == "Type a question." and "refusal" not in out
    else:
        assert out["refusal"] == reason and out["message"]
    assert [a["kind"] for a in audit] == ["pubmed_ask"] and audit[0]["status"] == "refused" and audit[0]["words"] == ""


def test_a_long_question_is_cut_and_spaces_collapsed(remote, model):
    out = ask(remote, "  What   survival  " + "did trials report " * 100)
    assert len(out["question"]) == pa.MAX_QUESTION and "  " not in out["question"]
    assert model.prompt("pubmed search words").count("did trials report") < 100


# ---- 2. the search words -------------------------------------------------------------------------------------------------------------
def words(monkeypatch, reply, question=QUESTION, context=None, identifiers=()):
    m = FakeLLM(words=reply)
    monkeypatch.setattr(llm, "chat", m)
    return asyncio.run(pa.search_words(question, context, identifiers)), m


def test_keywords_drop_stop_words_and_numbers():
    assert pa.keywords(QUESTION) == "pathological complete response event-free survival trials neoadjuvant pembrolizumab"
    assert pa.keywords("What is the 5-year survival in 2024?") == "year survival"  # a word starts with a letter: "2024" never, "5-" dropped
    assert pa.keywords("") == ""


def test_search_words_from_the_model_when_valid(monkeypatch):
    w, m = words(monkeypatch, {"kind": "general", "query": "  pembrolizumab \n AND  TNBC ", "broader_query": BROADER})
    assert w == {"kind": "general", "query": "pembrolizumab AND TNBC", "broader_query": BROADER, "by": "model"}
    assert m.purposes() == ["pubmed search words"] and m.calls[0]["schema"] is pa.QUERY_SCHEMA and f"QUESTION: {QUESTION}" in m.prompt("pubmed search words")
    exact = "a" * pa.MAX_QUERY
    assert words(monkeypatch, {"kind": "general", "query": exact, "broader_query": ""})[0]["by"] == "model"  # the limit itself is allowed


@pytest.mark.parametrize("bad", [
    "(pembrolizumab AND TNBC",  # unbalanced parentheses
    '"triple-negative breast cancer AND pembrolizumab',  # an odd quote
    "pembrolizumab AND " + "breast " * 60,  # over the limit
    "NCT02819518 AND pembrolizumab",  # a digit run
    "pembrolizumab AND 12/03/2026",  # a date
    "Kumar AND pembrolizumab",  # a name part of the patient
    "SYN-100231 pembrolizumab",  # the patient's number
    "uhid pembrolizumab",
    "",
    "x",
    "12 34",
])
def test_search_words_fall_back_to_the_question(monkeypatch, bad):
    w, _ = words(monkeypatch, {"kind": "general", "query": bad, "broader_query": BROADER}, identifiers=NAME)
    assert w == {"kind": "general", "query": pa.keywords(QUESTION), "broader_query": BROADER, "by": "question"}


def test_search_words_when_the_model_fails_or_sends_rubbish(monkeypatch):
    w, _ = words(monkeypatch, llm.LLMError("reasoner unreachable"))
    assert w == {"kind": "general", "query": pa.keywords(QUESTION), "broader_query": "", "by": "question", "error": "LLMError"}
    w, _ = words(monkeypatch, asyncio.TimeoutError())
    assert w["by"] == "question" and w["error"] == "TimeoutError"
    for junk in ([], ["pembrolizumab"], "pembrolizumab", None, 7):  # not an object: the question's own words, never a crash
        w, _ = words(monkeypatch, junk)
        assert w["by"] == "question" and w["query"] == pa.keywords(QUESTION) and w["kind"] == "general", junk
    w, _ = words(monkeypatch, {"kind": "something else", "query": QUERY, "broader_query": BROADER})
    assert w["kind"] == "general" and w["by"] == "model"
    w, _ = words(monkeypatch, {"kind": "general", "query": QUERY})  # broader_query missing
    assert w["broader_query"] == "" and w["by"] == "model"


def test_search_words_broader_query_with_an_identifier_is_dropped(monkeypatch):
    w, _ = words(monkeypatch, {"kind": "general", "query": QUERY, "broader_query": "Ramesh AND pembrolizumab"}, identifiers=NAME)
    assert w["query"] == QUERY and w["broader_query"] == "" and w["by"] == "model"
    w, _ = words(monkeypatch, {"kind": "general", "query": QUERY, "broader_query": "(pembrolizumab"})
    assert w["broader_query"] == ""


@pytest.mark.parametrize("kind,refusal,message", [("about_a_patient", "about_patient_model", pa.REFUSED), ("not_medical", "not_medical", pa.NOT_MEDICAL)])
def test_the_models_kind_refuses_before_pubmed(remote, monkeypatch, kind, refusal, message):
    m = FakeLLM(words={"kind": kind, "query": QUERY, "broader_query": BROADER})
    monkeypatch.setattr(llm, "chat", m)
    audit = []
    out = ask(remote, audit=audit.append)
    assert out["status"] == "refused" and out["refusal"] == refusal and out["message"] == message
    assert remote.seen == [] and m.purposes() == ["pubmed search words"] and out["papers"] == []
    assert audit[-1]["status"] == "refused"


def test_identifier_in_the_models_words_never_reaches_pubmed(remote, monkeypatch):
    m = FakeLLM(words={"kind": "general", "query": "Ramesh Kumar AND SYN-100231 AND pembrolizumab", "broader_query": "Kumar"})
    monkeypatch.setattr(llm, "chat", m)
    out = ask(remote, identifiers=NAME)
    assert out["search"]["by"] == "question" and out["search"]["broader_query"] == ""
    assert remote.terms()[0] == pa.keywords(QUESTION)
    urls = " ".join(str(r.url) for r in remote.seen).lower()
    assert "ramesh" not in urls and "kumar" not in urls and "100231" not in urls and "synthetic" not in urls


# ---- 3. widening ---------------------------------------------------------------------------------------------------------------------
def test_widening_order_query_broader_all_years_keywords(remote, model):
    kw = pa.keywords(QUESTION)
    remote.ids = lambda term, limited: IDS if (term, limited) == (kw, False) else []
    steps = []
    out = ask(remote, years=10, on_step=lambda s, d: steps.append((s, d)))
    assert out["status"] == "answered"
    assert [(a["term"], a["years"]) for a in out["search"]["attempts"]] == [(QUERY, 10), (BROADER, 10), (QUERY, None), (kw, None)]
    assert [a["count"] for a in out["search"]["attempts"]] == [0, 0, 0, 148]
    assert out["search"]["attempts"][0]["warnings"] == ["outputmessages: No items found."]
    assert out["search"]["used"] == kw and out["search"]["years"] is None and out["counts"]["found"] == 148
    es = [dict(r.url.params) for r in remote.seen if r.url.path.endswith("esearch.fcgi")]
    y = datetime.now().year
    assert [p["term"] for p in es] == [QUERY, BROADER, QUERY, kw]
    assert [(p.get("datetype"), p.get("mindate"), p.get("maxdate")) for p in es] == [("pdat", str(y - 9), str(y))] * 2 + [(None, None, None)] * 2
    assert all(p["retmax"] == str(pa.RETMAX) and p["sort"] == "relevance" and p["db"] == "pubmed" and p["tool"] == "vaidyx-tb" for p in es)
    assert [s for s, _ in steps] == ["words", "search", "search", "search", "search", "fetch", "read", "check"]
    assert [d for s, d in steps if s == "search"] == [f"searching PubMed: {QUERY} (last 10 years)", f"searching PubMed: {BROADER} (last 10 years)",
                                                     f"searching PubMed: {QUERY} (all years)", f"searching PubMed: {kw} (all years)"]
    assert len([c for c in out["calls"] if c["what"] == "search"]) == 4


def test_widening_default_is_every_year(remote, model):
    """No year limit by default (PubMed's Best Match order), so a landmark trial older than ten years is found."""
    kw = pa.keywords(QUESTION)
    remote.ids = lambda term, limited: []
    out = ask(remote)
    assert [(a["term"], a["years"]) for a in out["search"]["attempts"]] == [(QUERY, None), (BROADER, None), (kw, None)]
    es = [dict(r.url.params) for r in remote.seen if r.url.path.endswith("esearch.fcgi")]
    assert all("datetype" not in p and "mindate" not in p for p in es)


def test_widening_stops_at_the_first_hit(remote, model):
    remote.ids = lambda term, limited: IDS if term == BROADER else []
    out = ask(remote, years=10)
    assert [(a["term"], a["years"]) for a in out["search"]["attempts"]] == [(QUERY, 10), (BROADER, 10)]
    assert out["search"]["used"] == BROADER and out["search"]["years"] == 10
    assert remote.paths() == ["esearch.fcgi", "esearch.fcgi", "efetch.fcgi"]


def test_widening_goes_on_below_min_found_and_keeps_the_biggest(remote, model):
    """Fewer than MIN_FOUND papers widens the search; when no search reaches it, the one that found the most is used."""
    kw = pa.keywords(QUESTION)
    few = {QUERY: IDS[:1], BROADER: IDS[:3], kw: IDS[:2]}
    remote.ids = lambda term, limited: few.get(term, [])
    out = ask(remote)
    assert [(a["term"], a["years"]) for a in out["search"]["attempts"]] == [(QUERY, None), (BROADER, None), (kw, None)]
    assert out["search"]["used"] == BROADER and out["counts"]["fetched"] == 3


def test_model_field_tags_are_taken_out(remote, monkeypatch):
    """A wrong field tag ("breast cancer"[MeSH] is not a heading) makes PubMed drop that part, so tags never reach PubMed."""
    m = FakeLLM(words={"kind": "general", "query": '(olaparib[tiab]) AND ("breast cancer"[MeSH] OR "breast neoplasms"[tiab])',
                       "broader_query": "olaparib[tiab]"})
    monkeypatch.setattr(llm, "chat", m)
    out = ask(remote)
    assert out["search"]["query"] == '(olaparib) AND ("breast cancer" OR "breast neoplasms")'
    assert "[" not in remote.terms()[0] and "[" not in out["search"]["query"] and out["search"]["by"] == "model"


def test_widening_skips_repeated_words(remote, monkeypatch):
    m = FakeLLM(words=llm.LLMError("down"))  # the question's words: query == keywords, no broader words
    monkeypatch.setattr(llm, "chat", m)
    remote.ids = lambda term, limited: []
    out = ask(remote, years=10)
    kw = pa.keywords(QUESTION)
    assert [(a["term"], a["years"]) for a in out["search"]["attempts"]] == [(kw, 10), (kw, None)]
    assert [(a["term"], a["years"]) for a in ask(remote)["search"]["attempts"]] == [(kw, None)]
    assert out["status"] == "no_papers"


def test_all_zero_is_no_papers(remote, model):
    remote.ids = lambda term, limited: []
    audit = []
    out = ask(remote, audit=audit.append)
    assert out["status"] == "no_papers" and out["message"] == pa.NO_PAPERS
    assert len(out["search"]["attempts"]) == 3 and out["search"]["used"] == pa.keywords(QUESTION)
    assert remote.paths() == ["esearch.fcgi"] * 3 and model.purposes() == ["pubmed search words"]
    assert out["papers"] == [] and out["statements"] == [] and out["counts"] == {"found": 0, "fetched": 0, "read": 0}
    assert audit[-1]["status"] == "no_papers" and audit[-1]["words"] == pa.keywords(QUESTION)


# ---- 4. PubMed failures --------------------------------------------------------------------------------------------------------------
def _unavailable(out, model, reason):
    assert out["status"] == "unavailable" and out["message"] == pa.DOWN.format(reason=reason)
    assert "pubmed answer" not in model.purposes()  # never an answer from the model's memory
    assert out["statements"] == []


def test_esearch_503_four_times_is_unavailable(remote, model):
    remote.esearch = lambda req: httpx.Response(503, text="Service Unavailable")
    audit = []
    out = ask(remote, audit=audit.append)
    _unavailable(out, model, "PubMed answered 503 after 4 tries")
    assert remote.paths() == ["esearch.fcgi"] * 4 and out["papers"] == []
    assert out["search"]["used"] == QUERY and audit[-1]["status"] == "unavailable"


def test_esearch_recovers_after_a_busy_answer(remote, model):
    answers = [httpx.Response(429), httpx.Response(502)]

    def flaky(req):
        if answers:
            return answers.pop(0)
        body = esearch_json(IDS, dict(req.url.params)["term"], 148)
        remote.sent.append(body)
        return httpx.Response(200, content=body)
    remote.esearch = flaky
    out = ask(remote)
    assert out["status"] == "answered"
    assert out["calls"][0]["what"] == "search" and out["calls"][0]["tries"] == 3


@pytest.mark.parametrize("answer,reason", [
    (lambda req: httpx.Response(400, text="Bad Request"), "PubMed answered 400"),  # not retried
    (lambda req: httpx.Response(200, content=b'{"error":"API rate limit exceeded","api-key":"10.0.0.1","count":"11","limit":"10"}'),
     "PubMed: API rate limit exceeded"),
    (lambda req: httpx.Response(200, content=b'{"header":{"type":"esearch"},"esearchresult":{"ERROR":"Invalid query syntax"}}'),
     "PubMed: Invalid query syntax"),
    (lambda req: httpx.Response(200, content=b"<html><body>NCBI is down for maintenance</body></html>"),
     "PubMed sent a search answer that is not JSON"),
    (lambda req: httpx.Response(200, content=b"[]"), "PubMed sent an empty search answer"),
])
def test_esearch_errors_are_unavailable(remote, model, answer, reason):
    remote.esearch = answer
    out = ask(remote)
    _unavailable(out, model, reason)
    assert "efetch.fcgi" not in remote.paths()


def test_esearch_connection_errors_are_unavailable(remote, model):
    def down(req):
        raise httpx.ConnectError("refused", request=req)
    remote.esearch = down
    out = ask(remote)
    _unavailable(out, model, "PubMed could not connect (ConnectError) after 4 tries")
    assert len(remote.seen) == 4


def test_a_failure_while_widening_is_unavailable(remote, model):
    def first_empty_then_down(req):
        if len(remote.seen) == 1:
            return httpx.Response(200, content=esearch_json([], QUERY))
        return httpx.Response(503)
    remote.esearch = first_empty_then_down
    out = ask(remote)
    _unavailable(out, model, "PubMed answered 503 after 4 tries")
    assert [a["term"] for a in out["search"]["attempts"]] == [QUERY] and out["search"]["used"] == BROADER


@pytest.mark.parametrize("body,reason", [
    (DOCTYPE.encode() + b"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>39000101</PMID>", "PubMed sent records that could not be read"),
    (b"", "PubMed sent records that could not be read"),
    (b'<?xml version="1.0" ?>\n<!DOCTYPE PubmedArticleSet [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><PubmedArticleSet>&b;</PubmedArticleSet>',
     "PubMed sent records that could not be read"),  # entities are refused (defusedxml)
    (b'<?xml version="1.0" ?>\n<eFetchResult><ERROR>Empty id list - nothing todo</ERROR></eFetchResult>', "PubMed: Empty id list - nothing todo"),
    (b"<html><head><title>Bad Gateway</title></head></html>", "PubMed sent 'html' instead of records"),
])
def test_efetch_errors_are_unavailable(remote, model, body, reason):
    remote.efetch = lambda req: httpx.Response(200, content=body)
    out = ask(remote)
    _unavailable(out, model, reason)
    assert remote.paths() == ["esearch.fcgi", "efetch.fcgi"] and out["papers"] == []


def test_efetch_503_is_unavailable(remote, model):
    remote.efetch = lambda req: httpx.Response(503)
    out = ask(remote)
    _unavailable(out, model, "PubMed answered 503 after 4 tries")
    assert remote.paths() == ["esearch.fcgi"] + ["efetch.fcgi"] * 4


# ---- 5. reading ----------------------------------------------------------------------------------------------------------------------
def test_reading_order_and_what_is_never_read(remote, model):
    out = ask(remote)
    assert [p["pmid"] for p in out["papers"]] == ["39000101", "39000106", "39000102", "39000103", "39000104", "39000105"]
    assert [p["rank"] for p in out["papers"]] == [5, 1, 3, 4, 6, 2]
    assert [p["tier"] for p in out["papers"]] == [1, 2, 2, 2, 5, 7]
    assert [(p["read"], p["why_not_read"]) for p in out["papers"]] == [(True, ""), (True, ""), (True, ""), (False, "retracted"),
                                                                      (False, "a retraction notice"), (False, "no abstract in PubMed")]
    assert out["counts"] == {"found": 148, "fetched": 6, "read": 3}
    prompt = model.prompt("pubmed answer")
    for pmid in ("39000103", "39000104", "39000105"):
        assert pmid not in prompt
    for text in (P3_TITLE, P3_SECRET, P4_TITLE, "RETRACTION_NOTICE_TEXT", "LETTER_TITLE_TEXT", "COPYRIGHT_LINE"):
        assert text not in prompt
    # the papers read, strongest first, each as PubMed sent it
    i1, i6, i2 = (prompt.index(f"[PMID {p}]") for p in ("39000101", "39000106", "39000102"))
    assert i1 < i6 < i2
    assert f"Title: {P1_TITLE}" in prompt and "RESULTS: " + P1_RESULTS in prompt and f"QUESTION: {QUESTION}" in prompt
    assert "[PMID 39000101] Meta-analysis | Breast Cancer Res Treat | 2023 | Menon A, Fischer L" in prompt
    assert "[PMID 39000102] Randomised trial | N Engl J Med | 2022 | Ray S, Bose P, Das K, et al." in prompt
    # the retracted paper the model cites anyway is not among the papers read
    assert out["invented_pmids"] == 1 and {"text": S_RETRACTED["text"], "reason": "the cited paper was not among the papers read"} in [
        {k: r[k] for k in ("text", "reason")} for r in out["removed"]]


def test_a_paper_missing_from_efetch_is_not_listed(remote, model):
    remote.efetch = lambda req: httpx.Response(200, content=efetch_xml(["39000101"]))
    out = ask(remote)
    assert [p["pmid"] for p in out["papers"]] == ["39000101"] and out["counts"]["fetched"] == 1
    assert out["status"] == "answered" and [s["text"] for s in out["statements"]] == [S_META["text"]]


def test_reading_limit(remote, model, monkeypatch):
    p = PAPERS()
    monkeypatch.setattr(pa, "READ_CHARS", len(pa.paper_block(p["39000101"])))  # exactly the first paper
    out = ask(remote)
    assert [(c["pmid"], c["read"], c["why_not_read"]) for c in out["papers"]] == [
        ("39000101", True, ""), ("39000106", False, "the reading limit was reached"), ("39000102", False, "the reading limit was reached"),
        ("39000103", False, "retracted"), ("39000104", False, "a retraction notice"), ("39000105", False, "no abstract in PubMed")]
    prompt = model.prompt("pubmed answer")
    assert "[PMID 39000101]" in prompt and "39000106" not in prompt and "39000102" not in prompt
    # the trial and the Indian study cited from outside the papers read: dropped and counted
    assert out["invented_pmids"] == 3 and [s["text"] for s in out["statements"]] == [S_META["text"]]


def test_nothing_readable_is_not_found_without_a_model_answer(remote, model, monkeypatch):
    monkeypatch.setattr(pa, "READ_CHARS", 10)
    out = ask(remote)
    assert out["status"] == "not_found" and out["message"] == pa.NOT_FOUND
    assert model.purposes() == ["pubmed search words"] and out["counts"]["read"] == 0
    assert {c["why_not_read"] for c in out["papers"]} == {"the reading limit was reached", "retracted", "a retraction notice", "no abstract in PubMed"}
    monkeypatch.setattr(pa, "READ_CHARS", 60000)
    remote.ids = lambda term, limited: ["39000103", "39000104", "39000105"]  # only papers that are never read
    model.calls.clear()
    out = ask(remote)
    assert out["status"] == "not_found" and model.purposes() == ["pubmed search words"] and len(out["papers"]) == 3
    remote.efetch = lambda req: httpx.Response(200, content=efetch_xml([]))  # PubMed sent no record at all
    model.calls.clear()
    out = ask(remote, fresh=True)
    assert out["status"] == "not_found" and out["papers"] == [] and model.purposes() == ["pubmed search words"]


def test_the_cache_serves_a_second_question(remote, model):
    first = ask(remote)
    assert remote.paths() == ["esearch.fcgi", "efetch.fcgi"]
    second = ask(remote)
    assert remote.paths() == ["esearch.fcgi", "efetch.fcgi", "esearch.fcgi"]
    assert [c["what"] for c in second["calls"]] == ["search"] and all(p["provenance"]["cached"] for p in second["papers"])
    assert [s["text"] for s in second["statements"]] == [s["text"] for s in first["statements"]]
    ask(remote, fresh=True)
    assert remote.paths()[-2:] == ["esearch.fcgi", "efetch.fcgi"]


# ---- 6. verify() ---------------------------------------------------------------------------------------------------------------------
def st(text, *cites):
    return {"text": text, "citations": [{"pmid": p, "quote": q} for p, q in cites]}


def check(*statements, ids=READ_IDS):
    return pa.verify(list(statements), PAPERS(ids))


def test_verify_drops_a_pmid_that_was_not_given():
    kept, removed, invented = check(st("The pooled rate was 64.8% with pembrolizumab.", ("12345678", Q1)),
                                    st("The pooled rate was 64.8% with pembrolizumab.", ("39000103", Q1)),
                                    st("The pooled rate was 64.8% with pembrolizumab.", ("", Q1)))
    assert kept == [] and invented == 3
    assert [r["reason"] for r in removed] == ["the cited paper was not among the papers read"] * 3


def test_verify_pmid_forms():
    kept, _, invented = check(st("The pooled rate was 64.8% with pembrolizumab.", ("PMID: 39000101", Q1)),
                              {"text": "The pooled rate was 64.8% with pembrolizumab.", "citations": [{"pmid": 39000101, "quote": Q1}]})
    assert len(kept) == 2 and invented == 0 and {c["pmid"] for s in kept for c in s["citations"]} == {"39000101"}


@pytest.mark.parametrize("quote", [
    "The pooled pCR rate was 64.8% with pembrolizumab",  # paraphrased
    "The pooled pathological complete response rate was 68.4% with pembrolizumab",  # a number changed
    "The pooled pathological complete response rate was 64.8% with pembrolizumab in all trials",  # words added
    "Pembrolizumab doubled the response rate",  # not in the paper at all
    "",
])
def test_verify_drops_a_quote_that_is_not_word_for_word(quote):
    kept, removed, invented = check(st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", quote)))
    assert kept == [] and invented == 0 and removed[0]["reason"] == "the quote is not word for word in the paper"


def test_verify_case_spacing_and_dash_forms_are_still_word_for_word():
    kept, removed, _ = check(st("The risk ratio was 1.27 (95% CI 1.15 to 1.40) with a pooled rate of 64.8%.",
                                ("39000101", "THE POOLED   pathological\ncomplete RESPONSE rate was 64.8%"),
                                ("39000101", "risk ratio 1.27, 95% CI 1.15-1.40")))
    assert removed == [] and len(kept) == 1
    assert [c["quote"] for c in kept[0]["citations"]] == ["The pooled pathological complete response rate was 64.8%",
                                                          "risk ratio 1.27, 95% CI 1.15–1.40"]  # the paper's own text, as PubMed sent it
    assert [c["where"] for c in kept[0]["citations"]] == ["RESULTS", "RESULTS"]


@pytest.mark.parametrize("quote,ok", [
    ("Twelve trials with 4120 patients were included ... 51.2% with chemotherapy alone", True),
    ("Twelve trials with 4120 patients were included … 51.2% with chemotherapy alone", True),
    ("Twelve trials with 4120 patients were included...51.2% with chemotherapy alone", True),
    ("Twelve trials with 4120 patients were included ... 70.0% with chemotherapy alone", False),
    ("Twelve trials with 5000 patients were included ... 51.2% with chemotherapy alone", False),
    ("... 51.2% with chemotherapy alone ...", True),  # a quote that only starts or ends with "..." is one part, found
])
def test_verify_elided_quotes(quote, ok):
    kept, removed, _ = check(st("Twelve trials with 4120 patients were included; the rate was 51.2% with chemotherapy alone.", ("39000101", quote)))
    if ok:
        assert removed == [] and len(kept) == 1
        q = kept[0]["citations"][0]["quote"]
        assert all(part.strip() in P1_RESULTS for part in q.split("..."))
    else:
        assert kept == [] and removed[0]["reason"] == "the quote is not word for word in the paper"


def test_verify_elided_quote_keeps_the_found_parts_only():
    kept, _, _ = check(st("Twelve trials with 4120 patients were included; the rate was 51.2% with chemotherapy alone.",
                          ("39000101", "Twelve trials with 4120 patients were included ... 51.2% with chemotherapy alone")))
    assert kept[0]["citations"][0]["quote"] == "Twelve trials with 4120 patients were included ... 51.2% with chemotherapy alone"


def test_verify_two_citations_one_bad_keeps_the_good_one():
    kept, removed, invented = check(st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", Q1), ("12345678", Q1)),
                                    st("Event-free survival was 84.5% in the pembrolizumab group.",
                                       ("39000101", "event-free survival was 84.5%"), ("39000102", "event-free survival was 84.5% in the pembrolizumab group")),
                                    st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", Q1), ("39000101", Q1.upper())))
    assert removed == [] and invented == 1
    assert [[c["pmid"] for c in s["citations"]] for s in kept] == [["39000101"], ["39000102"], ["39000101"]]  # the repeat is listed once


def test_verify_numbers_must_be_in_the_quotes():
    kept, removed, _ = check(
        st("The pooled rate was 70% with pembrolizumab.", ("39000101", Q1)),
        st("A meta-analysis of 12 trials reported a pooled rate of 64.8%.", ("39000101", Q1)),  # the paper says "Twelve"
        st("The pooled rate was 64.80% with pembrolizumab.", ("39000101", Q1)),
        st("Twelve trials with 5000 patients reported a pooled rate of 64.8%.", ("39000101", Q1)),
        st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", Q1)))
    assert [r["reason"] for r in removed] == ["number 70 not in the quoted text", "number 12 not in the quoted text",
                                              "number 64.80 not in the quoted text", "number 5000 not in the quoted text"]
    assert [s["text"] for s in kept] == ["The pooled rate was 64.8% with pembrolizumab."]


def test_verify_a_cited_papers_year_is_allowed_another_year_is_not():
    kept, removed, _ = check(st("A 2023 meta-analysis reported a pooled rate of 64.8% with pembrolizumab.", ("39000101", Q1)),
                             st("A 2021 meta-analysis reported a pooled rate of 64.8% with pembrolizumab.", ("39000101", Q1)),
                             st("A 2021 study and a 2023 meta-analysis reported rates of 45.3% and 64.8%.", ("39000101", Q1),
                                ("39000106", "Pathological complete response was seen in 29 of 64 women (45.3%)")))
    assert [s["text"][:6] for s in kept] == ["A 2023", "A 2021"] and len(kept[1]["citations"]) == 2
    assert removed == [{"text": "A 2021 meta-analysis reported a pooled rate of 64.8% with pembrolizumab.", "reason": "number 2021 not in the quoted text"}]


def test_verify_trial_names_must_be_in_the_cited_papers():
    q2 = ("39000102", "event-free survival was 84.5% in the pembrolizumab group")
    kept, removed, _ = check(
        st("The KEYNOTE-522 trial reported a pooled rate of 64.8% with pembrolizumab.", ("39000101", Q1)),  # not in the meta-analysis
        st("The IMpassion031 trial reported a pooled rate of 64.8% with pembrolizumab.", ("39000101", Q1)),
        st("In KEYNOTE-522, event-free survival was 84.5% in the pembrolizumab group.", q2),
        st("In keynote-522, event-free survival was 84.5% in the pembrolizumab group.", q2),
        st("The KEYNOTE-522 trial and a meta-analysis reported 84.5% and 64.8%.", q2, ("39000101", Q1)))
    assert [r["reason"] for r in removed] == ["KEYNOTE-522 not in the cited papers", "IMpassion031 not in the cited papers"]
    assert len(kept) == 3


def test_verify_a_number_beside_the_same_word_in_the_paper():
    q2 = ("39000102", "event-free survival was 84.5% in the pembrolizumab group")
    q6 = ("39000106", "Pathological complete response was seen in 29 of 64 women (45.3%)")
    kept, removed, _ = check(
        st("A phase 2 study reported pathological complete response in 29 of 64 women.", q6),
        st("A phase 2 trial reported event-free survival was 84.5% in the pembrolizumab group.", q2),  # the trial is phase 3
        st("Grade 3 toxicity was reported; pathological complete response was seen in 29 of 64 women (45.3%).", q6),
        st("At 36 months, event-free survival was 84.5% in the pembrolizumab group.", q2),
        st("At 36 weeks, event-free survival was 84.5% in the pembrolizumab group.", q2),  # "at 36" is in the paper, "36 weeks" is not
        st("Of 1174 patients, event-free survival was 84.5% in the pembrolizumab group.", q2),  # "of 1174" is not, "1174 patients" is
        st("Event-free survival was 84.5% in the pembrolizumab group, a 2 point gain.", q2))  # "a 2" is in the paper ("in a 2:1 ratio")
    assert [s["text"][:12] for s in kept] == ["A phase 2 st", "Grade 3 toxi", "At 36 months", "Of 1174 pati"]
    assert [r["reason"] for r in removed] == ["number 2 not in the quoted text", "number 36 not in the quoted text", "number 2 not in the quoted text"]


@pytest.mark.parametrize("text,reason", [
    ("She may expect the same: the pooled pathological complete response rate was 64.8% with pembrolizumab.", "it speaks about a patient"),
    ("For this patient, the pooled pathological complete response rate was 64.8% with pembrolizumab.", "it speaks about a patient"),
    ("In his case the pooled pathological complete response rate was 64.8% with pembrolizumab.", "it speaks about a patient"),
    ("Patients should receive pembrolizumab, as the pooled pathological complete response rate was 64.8% with pembrolizumab.",
     "advice in Vaidyx's own words (should receive)"),
    ("Pembrolizumab is the best option: the pooled pathological complete response rate was 64.8% with pembrolizumab.",
     "advice in Vaidyx's own words (best option)"),
    ("We recommend pembrolizumab because the pooled pathological complete response rate was 64.8% with pembrolizumab.",
     "advice in Vaidyx's own words (We recommend)"),
    ("You should add pembrolizumab: the pooled pathological complete response rate was 64.8% with pembrolizumab.",
     "advice in Vaidyx's own words (You should)"),
    ("Pembrolizumab is recommended because the pooled pathological complete response rate was 64.8% with pembrolizumab.",
     "a recommendation in Vaidyx's own words"),
    # quotation marks do not make Vaidyx's own words the paper's: only a verified quote is the paper's
    ('Pembrolizumab "is the best option", as the pooled pathological complete response rate was 64.8% with pembrolizumab.',
     "advice in Vaidyx's own words (best option)"),
    ('In the meta-analysis "she should receive pembrolizumab": the pooled pathological complete response rate was 64.8% with pembrolizumab.',
     "it speaks about a patient"),
])
def test_verify_no_advice_and_no_patient_in_own_words(text, reason):
    kept, removed, _ = check(st(text, ("39000101", Q1)))
    assert kept == [] and removed == [{"text": text, "reason": reason}]


@pytest.mark.parametrize("text,quote", [
    ("The authors recommend longer follow-up, noting that adding pembrolizumab to neoadjuvant chemotherapy increased the pathological "
     "complete response rate.", "Adding pembrolizumab to neoadjuvant chemotherapy increased the pathological complete response rate"),
    ('The authors concluded that "these results support pembrolizumab as the preferred treatment for high-risk early triple-negative breast '
     'cancer".', "These results support pembrolizumab as the preferred treatment for high-risk early triple-negative breast cancer"),
    ('The meta-analysis called pembrolizumab "the preferred treatment for high-risk early triple-negative breast cancer".',
     "These results support pembrolizumab as the preferred treatment for high-risk early triple-negative breast cancer"),
    ("In tumours without HER2 expression, the pooled pathological complete response rate was 64.8% with pembrolizumab.", Q1),
    ("Across the patients studied, the pooled pathological complete response rate was 64.8% with pembrolizumab.", Q1),
])
def test_verify_reported_words_and_her2_are_kept(text, quote):
    kept, removed, _ = check(st(text, ("39000101", quote)))
    assert removed == [] and len(kept) == 1


def test_verify_caps_the_statements():
    kept, removed, _ = check(*[st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", Q1)) for _ in range(pa.MAX_STATEMENTS + 4)])
    assert len(kept) == pa.MAX_STATEMENTS and removed == []


def test_verify_ignores_what_is_not_a_statement():
    good = st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", Q1))
    kept, removed, invented = pa.verify([None, "text", 42, ["x"], {"text": "", "citations": good["citations"]}, {"text": "   "},
                                         {"text": "No citations.", "citations": None}, {"text": "Bad citations.", "citations": ["39000101", None, 5]},
                                         {"text": "A string.", "citations": "39000101"}, good], PAPERS())
    assert [s["text"] for s in kept] == [good["text"]] and invented == 0
    assert [{k: r[k] for k in ("text", "reason")} for r in removed] == [{"text": "No citations.", "reason": "no citation"}, {"text": "Bad citations.", "reason": "no citation"},
                       {"text": "A string.", "reason": "no citation"}]
    for junk in (None, [], "statements", 7, {"text": good["text"], "citations": good["citations"]}):
        assert pa.verify(junk, PAPERS()) == ([], [], 0), junk


def test_verify_where_is_the_section_or_the_title():
    kept, _, _ = check(
        st("The review was titled as a systematic review and meta-analysis.", ("39000101", "a systematic review and meta-analysis")),
        st("Checkpoint inhibitors were added to neoadjuvant chemotherapy.", ("39000101", "Immune checkpoint inhibitors have been added")),
        st("The search covered PubMed, Embase and CENTRAL.", ("39000101", "We searched PubMed, Embase and CENTRAL")),
        st("The rate was 64.8%.", ("39000101", Q1)),
        st("Follow-up is needed.", ("39000101", "Longer follow-up of event-free survival is needed")),
        st("Neutropenia was the most common grade 3 toxicity.", ("39000106", "Neutropenia was the most common grade 3 toxicity")))
    assert [s["citations"][0]["where"] for s in kept] == ["Title", "BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS", "Abstract"]
    kept, _, _ = check(st("The pooled rate was 64.8% with pembrolizumab.", ("39000101", "RESULTS: Twelve trials with 4120 patients were included ... " + Q1)))
    c = kept[0]["citations"][0]
    assert c["where"] == "RESULTS" and c["quote"] == "Twelve trials with 4120 patients were included ... " + Q1  # the label is not the paper's sentence


# ---- 7. the model down at the answer step --------------------------------------------------------------------------------------------
def test_model_down_at_the_answer_is_unavailable_with_the_papers(remote, model):
    model.script["pubmed answer"] = llm.LLMError("reasoner unreachable")
    audit = []
    out = ask(remote, audit=audit.append)
    assert out["status"] == "unavailable" and out["message"] == pa.MODEL_DOWN.format(reason="LLMError") and "model" in out["message"]
    assert "PubMed" not in out["message"].split("(")[0]  # it is the model, not PubMed, that is down
    assert [p["pmid"] for p in out["papers"]] == ["39000101", "39000106", "39000102", "39000103", "39000104", "39000105"]
    assert [p["read"] for p in out["papers"]] == [True, True, True, False, False, False] and out["counts"]["read"] == 3
    assert out["statements"] == [] and audit[-1]["status"] == "unavailable"


def test_the_whole_model_down_still_lists_the_papers(remote, model):
    model.script["pubmed search words"] = llm.LLMError("down")
    model.script["pubmed answer"] = llm.LLMError("down")
    out = ask(remote)
    assert out["search"]["by"] == "question" and remote.terms()[0] == pa.keywords(QUESTION)
    assert out["status"] == "unavailable" and len(out["papers"]) == 6 and out["statements"] == []


@pytest.mark.parametrize("answer", [[], "no", None, {"answer_found": False, "statements": []}, {"answer_found": True},
                                    {"answer_found": True, "statements": {"text": "x"}}, {"answer_found": True, "statements": [S_PARAPHRASE]}])
def test_no_verified_statement_is_not_found(remote, model, answer):
    model.script["pubmed answer"] = answer
    out = ask(remote)
    assert out["status"] == "not_found" and out["message"] == pa.NOT_FOUND and out["statements"] == []
    assert len(out["papers"]) == 6 and not any(p["cited"] for p in out["papers"])


# ---- 8. the happy path ---------------------------------------------------------------------------------------------------------------
def test_answered_from_pubmed_only(remote, model, tmp_path):
    (tmp_path / "pubmed.json").write_text(json.dumps({"email": "tb-team@example.org", "api_key": "KEY123SECRET"}))
    audit, steps = [], []
    out = ask(remote, audit=audit.append, on_step=lambda s, d: steps.append(s))
    assert out["status"] == "answered" and out["message"] == "" and out["label"] == pa.LABEL_HOME
    assert out["question"] == QUESTION and out["model"] == pa.model_line()
    assert out["search"] == {"query": QUERY, "broader_query": BROADER, "by": "model", "used": QUERY, "years": None,
                             "translation": f"{QUERY}[All Fields]",
                             "attempts": [{"term": QUERY, "years": None, "count": 148, "warnings": []}]}
    # the statements, each with its verified quote and where it is
    assert [s["text"] for s in out["statements"]] == [S_META["text"], S_TRIAL["text"], S_INDIA["text"]]
    assert [[(c["pmid"], c["where"]) for c in s["citations"]] for s in out["statements"]] == [[("39000101", "RESULTS")], [("39000102", "RESULTS")],
                                                                                             [("39000106", "Abstract")]]
    for s in out["statements"]:
        for c in s["citations"]:
            p = by_pmid(out)[c["pmid"]]
            assert c["quote"] in PAPERS()[c["pmid"]]["abstract"] and p["read"] and p["cited"]
    assert [r["reason"] for r in out["removed"]] == ["the cited paper was not among the papers read", "the quote is not word for word in the paper"]
    assert out["invented_pmids"] == 1
    assert {p["pmid"]: p["cited"] for p in out["papers"]} == {"39000101": True, "39000106": True, "39000102": True, "39000103": False,
                                                              "39000104": False, "39000105": False}
    # every card field from PubMed's record
    c1, c2, c6, c3, c4, c5 = (by_pmid(out)[p] for p in ("39000101", "39000102", "39000106", "39000103", "39000104", "39000105"))
    assert (c1["title"], c1["journal"], c1["journal_abbr"], c1["year"], c1["study_type"], c1["authors_line"]) == (
        P1_TITLE, "Breast cancer research and treatment", "Breast Cancer Res Treat", "2023", "Meta-analysis", "Menon A, Fischer L")
    assert (c1["doi"], c1["pmcid"], c1["india"], c1["has_abstract"], c1["retracted"]) == ("10.1007/s10549-023-00001-1", "PMC10000001", True, True, False)
    assert (c2["title"], c2["journal"], c2["year"], c2["study_type"], c2["authors_line"], c2["india"]) == (
        P2_TITLE, "The New England journal of medicine", "2022", "Randomised trial", "Ray S, Bose P, Das K, et al.", False)
    assert (c6["year"], c6["study_type"], c6["india"], c6["journal_abbr"]) == ("2021", "Clinical trial", True, "Indian J Cancer")
    assert (c3["retracted"], c3["study_type"], c4["retraction_notice"], c5["has_abstract"], c5["study_type"]) == (
        True, "Randomised trial", True, False, "Comment or letter")
    for p in out["papers"]:
        assert p["url"] == f"https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/" and p["title"] == pubmed.parse(efetch_xml([p["pmid"]]))[0]["title"]
        assert p["provenance"]["cached"] is False and p["provenance"]["sha256"] == hashlib.sha256(remote.sent[1]).hexdigest()
    # the calls, with the provenance of what PubMed sent and never the key
    assert [c["what"] for c in out["calls"]] == ["search", "fetch"] and out["counts"] == {"found": 148, "fetched": 6, "read": 3}
    for call, body in zip(out["calls"], remote.sent):
        assert call["status"] == 200 and call["sha256"] == hashlib.sha256(body).hexdigest() and call["bytes"] == len(body) and call["tries"] == 1
        assert call["url"].startswith(pubmed.EUTILS) and "KEY123SECRET" not in call["url"] and "tool=vaidyx-tb" in call["url"]
    assert all(dict(r.url.params).get("api_key") == "KEY123SECRET" for r in remote.seen)  # sent to NCBI only
    assert dict(remote.seen[1].url.params)["id"] == ",".join(IDS) and dict(remote.seen[1].url.params)["retmode"] == "xml"
    assert "KEY123SECRET" not in json.dumps(out) and "KEY123SECRET" not in json.dumps(audit)
    # only the search words left the server, never the question
    assert remote.terms() == [QUERY] and not any("survival" in str(r.url.params) for r in remote.seen)
    # the model: the words, then one reading of the papers
    assert model.purposes() == ["pubmed search words", "pubmed answer"] and all(c["role"] == "reasoner" for c in model.calls)
    assert model.calls[1]["schema"] is pa.ANSWER_SCHEMA and model.calls[1]["messages"][0]["content"] == pa.ANSWER_SYS
    # the audit and the steps
    assert audit == [{"kind": "pubmed_ask", "status": "answered", "question": QUESTION, "words": QUERY, "found": 148, "read": 3, "statements": 3,
                      "removed": 2, "invented_pmids": 1, "seconds": out["seconds"]}]
    assert steps == ["words", "search", "fetch", "read", "check"] and [s["step"] for s in out["steps"]] == steps
    json.dumps(out)  # the whole answer is plain JSON


def test_label_inside_the_case_file(remote, model):
    assert ask(remote, in_case_file=True)["label"] == pa.LABEL
    assert ask(remote, in_case_file=False)["label"] == pa.LABEL_HOME
    assert "not advice for this patient" in pa.LABEL and "not advice for any patient" in pa.LABEL_HOME


def test_on_step_async_function(remote, model):
    seen = []

    async def on_step(step, detail):
        await asyncio.sleep(0)
        seen.append((step, detail))
    out = ask(remote, on_step=on_step)
    assert out["status"] == "answered"
    assert [s for s, _ in seen] == ["words", "search", "fetch", "read", "check"]
    assert seen[0][1] == "writing the PubMed search words" and seen[1][1] == f"searching PubMed: {QUERY} (all years)"
    assert seen[2][1] == "148 papers found, fetching the top 6 records" and seen[3][1] == "the model is reading 3 abstracts"


# ---- 9. inside a Case File -----------------------------------------------------------------------------------------------------------
CONTEXT = {"cancer": "Carcinoma cervix", "terms": ["FIGO IIB", "cisplatin chemoradiation", "squamous", "t4", "t5", "t6", "t7", "t8",
                                                    "NINTH_TERM"]}


def test_case_file_context_reaches_the_words_prompt_not_pubmed(remote, model):
    out = ask(remote, context=CONTEXT, identifiers=NAME, in_case_file=True)
    prompt = model.prompt("pubmed search words")
    assert "cancer: Carcinoma cervix" in prompt and "FIGO IIB" in prompt and "cisplatin chemoradiation" in prompt and "t8" in prompt
    assert "NINTH_TERM" not in prompt  # eight terms at most
    urls = " ".join(str(r.url) for r in remote.seen).lower()
    assert "cervix" not in urls and "figo" not in urls and "cisplatin" not in urls
    assert remote.terms() == [QUERY] and out["status"] == "answered" and out["label"] == pa.LABEL
    assert "Case File" not in model.prompt("pubmed answer")
    model.calls.clear()
    ask(remote)  # no context: no Case File line
    assert "Case File" not in model.prompt("pubmed search words")


def test_case_file_context_reaches_pubmed_only_through_the_models_words(remote, model):
    model.script["pubmed search words"] = {"kind": "general", "query": "cisplatin chemoradiation AND cervical cancer", "broader_query": "cervical cancer"}
    out = ask(remote, "What survival did trials report for this cancer with chemoradiation?", context=CONTEXT, in_case_file=True)
    assert remote.terms() == ["cisplatin chemoradiation AND cervical cancer"] and out["search"]["by"] == "model"
    model.script["pubmed search words"] = {"kind": "general", "query": "Carcinoma cervix AND Ramesh", "broader_query": ""}
    remote.seen.clear()
    out = ask(remote, "What survival did trials report for this cancer with chemoradiation?", context=CONTEXT, identifiers=NAME)
    assert out["search"]["by"] == "question" and "ramesh" not in " ".join(str(r.url) for r in remote.seen).lower()


def test_context_with_no_cancer_or_no_terms(remote, model):
    ask(remote, context={"terms": ["neoadjuvant"]})
    assert "about: neoadjuvant." in model.prompt("pubmed search words")
    model.calls.clear()
    ask(remote, context={"cancer": "Breast cancer"})
    assert "about: cancer: Breast cancer." in model.prompt("pubmed search words")


# ---- the guards added after the first live run (3 Nov) -------------------------------------------------------------------------------
def _one(abstract, title="A trial"):
    p = {"pmid": "40000001", "title": title, "abstract": abstract, "sections": [{"label": "", "text": abstract}], "year": "2023"}
    return {"40000001": p}


def test_an_elision_never_hides_a_negation():
    papers = _one("Pembrolizumab was not superior to placebo for overall survival. Toxicity was manageable.")
    kept, removed, _ = pa.verify([st("Pembrolizumab was superior to placebo.", ("40000001", "Pembrolizumab was ... superior to placebo"))], papers)
    assert kept == [] and removed[0]["reason"] == "the quote is not word for word in the paper"
    kept, _, _ = pa.verify([st("Overall survival and toxicity were reported.",
                               ("40000001", "for overall survival ... Toxicity was manageable"))], papers)
    assert len(kept) == 1


def test_elided_parts_must_be_in_order():
    papers = _one("Event-free survival improved. Grade 3 events were more common.")
    kept, _, _ = pa.verify([st("Both were reported.", ("40000001", "Grade 3 events ... Event-free survival improved"))], papers)
    assert kept == []


def test_a_papers_year_is_a_year_never_a_count():
    papers = _one("The trial enrolled 1174 patients and pathological complete response improved.")
    kept, _, _ = pa.verify([st("A 2023 trial reported that pathological complete response improved.",
                               ("40000001", "pathological complete response improved"))], papers)
    assert len(kept) == 1
    kept, removed, _ = pa.verify([st("The trial enrolled 2023 patients and pathological complete response improved.",
                                     ("40000001", "pathological complete response improved"))], papers)
    assert kept == [] and "2023" in removed[0]["reason"]


@pytest.mark.parametrize("q", ["Trials reported on 12 March 2026 for breast cancer", "Trials after March 12, 2026 in breast cancer",
                               "Results from 3rd Nov 2026 trials", "Trials started 12.03.2026"])
def test_written_dates_are_refused(q):
    assert pa.scope(q)["reason"] == "identifier"


@pytest.mark.parametrize("q", ["Trials with a hazard ratio of 0.48-0.82 for overall survival", "Trials from 2015-2024 in cervical cancer",
                               "What did trials report about the patient population in KEYNOTE-522?",
                               "What did trials report for HER-2/neu positive breast cancer?", "What did trials report for her 2 positive disease?"])
def test_general_questions_with_ranges_or_groups_pass(q):
    assert pa.scope(q)["allowed"], q


@pytest.mark.parametrize("q", ["What did trials report after her 2 cycles of chemotherapy?", "Response after her 3 doses of trastuzumab"])
def test_her_followed_by_a_count_is_a_person(q):
    assert not pa.scope(q)["allowed"]


def test_one_identifier_given_as_text_is_still_checked():
    assert pa.scope("What did trials report for Lakshmi breast cancer?", identifiers="Lakshmi Devi")["reason"] == "identifier"
    assert not pa.query_ok("Lakshmi AND breast cancer", identifiers="Lakshmi Devi")


def test_pubmed_down_message_reads_as_a_sentence():
    assert pa.DOWN.format(reason="PubMed answered 503 after 4 tries") == "PubMed answered 503 after 4 tries. Try again in a minute."


SENTENCE = ("At the first interim analysis, the percentage of patients with a pathological complete response was 64.8% (95% confidence "
            "interval [CI], 59.9 to 69.5) in the pembrolizumab-chemotherapy group and 51.2% (95% CI, 44.1 to 58.3) in the placebo-chemotherapy group.")
SHORT = ("the percentage of patients with a pathological complete response was 64.8% in the pembrolizumab-chemotherapy group and 51.2% in "
         "the placebo-chemotherapy group")


def test_a_shortened_quote_shows_the_papers_whole_sentence():
    papers = _one("Pembrolizumab was studied. " + SENTENCE + " Adverse events were similar.")
    kept, removed, _ = pa.verify([st("The trial reported pCR of 64.8% with pembrolizumab and 51.2% with placebo.", ("40000001", SHORT))], papers)
    assert removed == [] and kept[0]["citations"][0]["quote"] == SENTENCE and kept[0]["citations"][0]["whole_sentence"] is True


@pytest.mark.parametrize("quote", [
    SHORT.replace("was 64.8%", "was not 64.8%"),  # a negation the paper does not have
    SHORT.replace("64.8%", "68.4%"),  # a number changed
    "in the placebo-chemotherapy group the pathological complete response percentage was 51.2% and 64.8% with pembrolizumab-chemotherapy",  # words moved
    SHORT + " and overall survival improved",  # words added
    "response was 64.8% in pembrolizumab",  # not word for word and too short to tell the sentence
])
def test_a_shortened_quote_is_never_stretched_to_another_claim(quote):
    papers = _one("Pembrolizumab was studied. " + SENTENCE + " Adverse events were similar.")
    kept, removed, _ = pa.verify([st("The trial reported pCR of 64.8% with pembrolizumab.", ("40000001", quote))], papers)
    assert kept == [] and removed[0]["reason"] == "the quote is not word for word in the paper"



def test_numbers_from_another_sentence_of_the_paper_are_shown_as_its_quote():
    papers = _one("Invasive disease-free survival improved with abemaciclib. The 2-year rates were 92.2% and 88.7% in the two groups. "
                  "Patients were assigned in a 1:1 ratio.")
    kept, removed, _ = pa.verify([st("Invasive disease-free survival improved, with 2-year rates of 92.2% and 88.7%.",
                                     ("40000001", "Invasive disease-free survival improved with abemaciclib"))], papers)
    assert removed == [] and [c["quote"] for c in kept[0]["citations"]] == [
        "Invasive disease-free survival improved with abemaciclib", "The 2-year rates were 92.2% and 88.7% in the two groups."]
    assert kept[0]["citations"][1]["added_for_numbers"] is True
    kept, removed, _ = pa.verify([st("Invasive disease-free survival improved, with 3-year rates of 92.2% and 88.7%.",
                                     ("40000001", "Invasive disease-free survival improved with abemaciclib"))], papers)
    assert kept == [] and "3" in removed[0]["reason"]  # "3-year" is in no sentence of the paper


def test_a_dropped_line_keeps_the_models_quote_for_the_logs():
    papers = _one("Event-free survival improved.")
    _, removed, _ = pa.verify([st("Survival improved.", ("40000001", "overall survival doubled"))], papers)
    assert removed[0]["model_quotes"] == ["overall survival doubled"]
