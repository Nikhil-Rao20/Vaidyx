"""PubMed client (tumour_board/pubmed.py, Ask PubMed, 3 Nov 2026), worst cases. NCBI E-utilities sit behind an httpx.MockTransport
(nothing leaves the machine): NCBI's error shapes (a JSON "error" with 200, esearchresult ERROR, an XML <ERROR>, an HTML page),
retries and back-off, entity payloads, the cache by PMID, the pace, and the API key never in the provenance. Every record here is
synthetic (fake PMIDs, fake journals); no patient data."""
import asyncio
import hashlib
import itertools
import json
import os
import time
from datetime import datetime

import httpx
import pytest

from tumour_board import pubmed

REAL_TURN = pubmed._turn  # kept before the fixture replaces it: the pace tests use the real one
KEY = "SYNTHETIC-TEST-KEY-0000"  # not a real NCBI key
EMAIL = "mdt.desk@example.org"


class _Proxy:
    """A module stand-in (asyncio or time inside pubmed) with a few names replaced; everything else is the real module."""

    def __init__(self, real, **names):
        self._real = real
        self.__dict__.update(names)

    def __getattr__(self, name):
        return getattr(self._real, name)


class Waits(list):
    """asyncio.sleep inside pubmed: records the wait and only yields, never really sleeps."""

    async def sleep(self, s):
        self.append(s)
        await _real_sleep(0)


_real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def waits(tmp_path, monkeypatch):
    """No network, no real waits, no data/: zero back-off, no pace, cache and settings in tmp_path, no env settings."""
    monkeypatch.setattr(pubmed, "DELAYS", (0.0, 0.0, 0.0))

    async def no_pace(has_key):
        return None
    monkeypatch.setattr(pubmed, "_turn", no_pace)
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "pubmed_cache")
    monkeypatch.setattr(pubmed, "SETTINGS", tmp_path / "pubmed.json")
    for k in ("TB_PUBMED_EMAIL", "TB_PUBMED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    w = Waits()
    monkeypatch.setattr(pubmed, "asyncio", _Proxy(asyncio, sleep=w.sleep))

    def no_network():
        raise AssertionError("a test reached for the real httpx client")
    monkeypatch.setattr(pubmed, "_client", no_network)
    return w


def run(coro):
    return asyncio.run(coro)


class NCBI:
    """E-utilities behind an httpx.MockTransport: records every request; answer(request, n) gives the n-th answer (1-based): an
    httpx.Response, or an httpx exception class to raise."""

    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def handler(self, request: httpx.Request):
        self.seen.append(request)
        out = self.answer(request, len(self.seen))
        if isinstance(out, type) and issubclass(out, Exception):
            raise out(f"synthetic failure for {request.url}", request=request)
        return out

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def params(self, i=-1) -> dict:
        return dict(self.seen[i].url.params)

    def ids(self, i=-1) -> list:
        return self.seen[i].url.params["id"].split(",")


def steps(*answers):
    """The answers in order, the last one repeated."""
    return lambda request, n: answers[min(n, len(answers)) - 1]


def esearch_json(ids=("39100001", "39100002"), count=None, **extra):
    return httpx.Response(200, json={"header": {"type": "esearch", "version": "0.3"},
                                     "esearchresult": {"count": str(len(ids) if count is None else count), "retmax": str(len(ids)), "retstart": "0",
                                                       "idlist": list(ids), "translationset": [], "querytranslation": "synthetic[All Fields]",
                                                       **extra}})


# ---- realistic efetch XML (synthetic records in PubMed's own shape) ------------------------------------------------------------------
DOCTYPE = ('<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN" '
           '"https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd">')


def article_set(*records: str) -> bytes:
    return ('<?xml version="1.0" ?>\n' + DOCTYPE + "\n<PubmedArticleSet>\n" + "\n".join(records) + "\n</PubmedArticleSet>\n").encode()


def article(pmid, *, title="A synthetic cohort of stage III NSCLC.", abstract=(("", "Synthetic abstract sentence."),),
            pubdate="<Year>2024</Year><Month>Mar</Month>", article_date="", types=("Journal Article",), refs=(), authors=None, doi="", pmc="",
            completed="") -> str:
    au = authors if authors is not None else (
        '<Author ValidYN="Y"><LastName>Mehta</LastName><ForeName>Suresh</ForeName><Initials>S</Initials>'
        '<AffiliationInfo><Affiliation>Synthetic Cancer Centre, Pune, India.</Affiliation></AffiliationInfo></Author>')
    ab = ("<Abstract>" + "".join(f'<AbstractText Label="{lab}">{txt}</AbstractText>' if lab else f"<AbstractText>{txt}</AbstractText>"
                                 for lab, txt in abstract) + "</Abstract>") if abstract else ""
    pt = "".join(f'<PublicationType UI="D000000">{t}</PublicationType>' for t in types)
    cc = ("<CommentsCorrectionsList>" + "".join(f'<CommentsCorrections RefType="{r}"><RefSource>Synth J. 2025;1:1</RefSource>'
                                                f'<PMID Version="1">39199999</PMID></CommentsCorrections>' for r in refs)
          + "</CommentsCorrectionsList>") if refs else ""
    aid = f'<ArticleId IdType="pubmed">{pmid}</ArticleId>' + (f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else "") + (
        f'<ArticleId IdType="pmc">{pmc}</ArticleId>' if pmc else "")
    return (f'<PubmedArticle><MedlineCitation Status="MEDLINE" Owner="NLM"><PMID Version="1">{pmid}</PMID>{completed}'
            f'<Article PubModel="Print"><Journal><ISSN IssnType="Print">0000-0000</ISSN><JournalIssue CitedMedium="Print"><Volume>1</Volume>'
            f'<PubDate>{pubdate}</PubDate></JournalIssue><Title>Synthetic Journal of Oncology</Title><ISOAbbreviation>Synth J Oncol</ISOAbbreviation>'
            f'</Journal><ArticleTitle>{title}</ArticleTitle>{ab}<AuthorList CompleteYN="Y">{au}</AuthorList><Language>eng</Language>'
            f'<PublicationTypeList>{pt}</PublicationTypeList>{article_date}</Article>{cc}</MedlineCitation>'
            f'<PubmedData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList>{aid}</ArticleIdList></PubmedData></PubmedArticle>')


def efetch_echo(request, n):
    """efetch answering with a synthetic record for every id asked."""
    return httpx.Response(200, content=article_set(*(article(i) for i in request.url.params["id"].split(","))))


RCT = """<PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM" IndexingMethod="Automated">
      <PMID Version="1">39100001</PMID>
      <DateCompleted><Year>2024</Year><Month>09</Month><Day>01</Day></DateCompleted>
      <DateRevised><Year>2025</Year><Month>01</Month><Day>10</Day></DateRevised>
      <Article PubModel="Print-Electronic">
        <Journal>
          <ISSN IssnType="Electronic">0000-0001</ISSN>
          <JournalIssue CitedMedium="Internet"><Volume>12</Volume><Issue>3</Issue><PubDate><Year>2024</Year><Month>Aug</Month></PubDate></JournalIssue>
          <Title>Synthetic Journal of Thoracic Oncology</Title>
          <ISOAbbreviation>Synth J Thorac Oncol</ISOAbbreviation>
        </Journal>
        <ArticleTitle>Adjuvant osimertinib in resected <i>EGFR</i>-mutated NSCLC: a randomised trial.</ArticleTitle>
        <Pagination><StartPage>101</StartPage><EndPage>110</EndPage><MedlinePgn>101-110</MedlinePgn></Pagination>
        <ELocationID EIdType="doi" ValidYN="Y">10.5555/synth.2024.001</ELocationID>
        <Abstract>
          <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">Adjuvant therapy after resection of
              <i>EGFR</i>-mutated NSCLC is uncertain.</AbstractText>
          <AbstractText Label="METHODS" NlmCategory="METHODS">Patients with stage IB to IIIA disease were randomly assigned (1:1) to osimertinib 80 mg or placebo.</AbstractText>
          <AbstractText Label="RESULTS" NlmCategory="RESULTS">Disease-free survival at 24 months was 89% versus 52% (HR 0.<i>21</i>; 95% CI 0.16 to 0.28; p&lt;10<sup>-4</sup>); T<sub>max</sub> was 6 h.</AbstractText>
          <AbstractText Label="CONCLUSIONS" NlmCategory="CONCLUSIONS">Osimertinib improved disease-free survival (&#8805; 2 years of follow-up) &amp; was tolerable.</AbstractText>
          <CopyrightInformation>Copyright 2024 Synthetic Publisher.</CopyrightInformation>
        </Abstract>
        <AuthorList CompleteYN="Y">
          <Author ValidYN="Y"><LastName>Rao</LastName><ForeName>Anil</ForeName><Initials>A</Initials>
            <AffiliationInfo><Affiliation>Department of Medical Oncology, Synthetic Memorial Centre, Mumbai, India.</Affiliation></AffiliationInfo></Author>
          <Author ValidYN="N"><LastName>Wrongname</LastName><ForeName>Xavier</ForeName><Initials>X</Initials></Author>
          <Author ValidYN="Y"><LastName>Iyer</LastName><ForeName>Lakshmi</ForeName><Initials>L</Initials>
            <AffiliationInfo><Affiliation>Indiana University School of Medicine, Indianapolis, IN, USA.</Affiliation></AffiliationInfo></Author>
          <Author ValidYN="Y"><CollectiveName>SYNTH-LUNG Trial Investigators</CollectiveName></Author>
          <Author ValidYN="Y"><LastName>Nair</LastName><ForeName>Kavya</ForeName><Initials>K</Initials></Author>
        </AuthorList>
        <Language>eng</Language>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
          <PublicationType UI="D016449">Randomized Controlled Trial</PublicationType>
          <PublicationType UI="D017427">Clinical Trial, Phase III</PublicationType>
          <PublicationType UI="D016448">Multicenter Study</PublicationType>
        </PublicationTypeList>
        <ArticleDate DateType="Electronic"><Year>2024</Year><Month>06</Month><Day>12</Day></ArticleDate>
      </Article>
      <MedlineJournalInfo><Country>India</Country><MedlineTA>Synth J Thorac Oncol</MedlineTA><NlmUniqueID>000000001</NlmUniqueID></MedlineJournalInfo>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="ErratumIn"><RefSource>Synth J Thorac Oncol. 2024;12(4):200</RefSource><PMID Version="1">39100099</PMID></CommentsCorrections>
      </CommentsCorrectionsList>
      <MeshHeadingList>
        <MeshHeading><DescriptorName UI="D002289" MajorTopicYN="Y">Carcinoma, Non-Small-Cell Lung</DescriptorName><QualifierName UI="Q000188" MajorTopicYN="N">drug therapy</QualifierName></MeshHeading>
        <MeshHeading><DescriptorName UI="D066246" MajorTopicYN="N">ErbB Receptors</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName UI="D006801" MajorTopicYN="N">Humans</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <History><PubMedPubDate PubStatus="received"><Year>2024</Year><Month>1</Month><Day>2</Day></PubMedPubDate></History>
      <PublicationStatus>ppublish</PublicationStatus>
      <ArticleIdList>
        <ArticleId IdType="pubmed">39100001</ArticleId>
        <ArticleId IdType="pmc">PMC11000001</ArticleId>
        <ArticleId IdType="doi">10.5555/synth.2024.001</ArticleId>
        <ArticleId IdType="pii">S0000-0000(24)00001-1</ArticleId>
      </ArticleIdList>
      <ReferenceList><Reference><Citation>An older synthetic reference.</Citation>
        <ArticleIdList><ArticleId IdType="pubmed">11111111</ArticleId><ArticleId IdType="doi">10.9999/not.this.paper</ArticleId></ArticleIdList>
      </Reference></ReferenceList>
    </PubmedData>
  </PubmedArticle>"""

META = """<PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">39100002</PMID>
      <Article PubModel="Print">
        <Journal><JournalIssue CitedMedium="Print"><Volume>8</Volume><PubDate><MedlineDate>2019 Nov-Dec</MedlineDate></PubDate></JournalIssue>
          <Title>Synthetic Reviews in Oncology</Title><ISOAbbreviation>Synth Rev Oncol</ISOAbbreviation></Journal>
        <ArticleTitle>Chemoradiation in stage III NSCLC: a meta-analysis.</ArticleTitle>
        <AuthorList CompleteYN="Y">
          <Author ValidYN="Y"><LastName>Brown</LastName><ForeName>Tara</ForeName><Initials>T</Initials>
            <AffiliationInfo><Affiliation>Indiana University, Indianapolis, USA.</Affiliation></AffiliationInfo></Author>
        </AuthorList>
        <Language>eng</Language>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
          <PublicationType UI="D017418">Meta-Analysis</PublicationType>
          <PublicationType UI="D000078182">Systematic Review</PublicationType>
          <PublicationType UI="D016454">Review</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData><PublicationStatus>ppublish</PublicationStatus><ArticleIdList><ArticleId IdType="pubmed">39100002</ArticleId></ArticleIdList></PubmedData>
  </PubmedArticle>"""

BOOK = """<PubmedBookArticle>
    <BookDocument>
      <PMID Version="1">20301425</PMID>
      <ArticleIdList><ArticleId IdType="bookaccession">NBK0001</ArticleId></ArticleIdList>
      <Book>
        <Publisher><PublisherName>Synthetic University Press</PublisherName><PublisherLocation>Pune</PublisherLocation></Publisher>
        <BookTitle book="synth">SynthReviews<sup>&#174;</sup></BookTitle>
        <PubDate><Year>1993</Year></PubDate>
        <AuthorList Type="editors"><Author ValidYN="Y"><LastName>Editor</LastName><ForeName>Ed</ForeName><Initials>E</Initials></Author></AuthorList>
        <Medium>Internet</Medium>
      </Book>
      <LocationLabel Type="chapter">Hereditary breast cancer</LocationLabel>
      <ArticleTitle book="synth" part="hbc">BRCA1- and BRCA2-associated hereditary breast and ovarian cancer</ArticleTitle>
      <Language>eng</Language>
      <AuthorList Type="authors">
        <Author ValidYN="Y"><LastName>Kulkarni</LastName><ForeName>Meera</ForeName><Initials>M</Initials>
          <AffiliationInfo><Affiliation>Synthetic Institute, Bengaluru, India</Affiliation></AffiliationInfo></Author>
      </AuthorList>
      <PublicationType UI="D016454">Review</PublicationType>
      <Abstract><AbstractText Label="CLINICAL CHARACTERISTICS" NlmCategory="UNASSIGNED">A synthetic chapter abstract.</AbstractText></Abstract>
    </BookDocument>
    <PubmedBookData>
      <PublicationStatus>ppublish</PublicationStatus>
      <ArticleIdList><ArticleId IdType="pubmed">20301425</ArticleId></ArticleIdList>
    </PubmedBookData>
  </PubmedBookArticle>"""

NO_PMID = "<PubmedArticle><MedlineCitation><PMID>not-a-number</PMID><Article><ArticleTitle>Broken</ArticleTitle></Article></MedlineCitation></PubmedArticle>"
DELETED = '<DeleteCitation><PMID Version="1">39100098</PMID></DeleteCitation>'


# ---- 1. esearch -----------------------------------------------------------------------------------------------------------------------
def test_search_ids_count_translation_warnings_and_years():
    ncbi = NCBI(steps(esearch_json(ids=("39100001", "39100002", "abc", "", "39100003"), count="1234",
                                   querytranslation='"carcinoma, non small cell lung"[MeSH Terms] AND osimertinib[All Fields]',
                                   warninglist={"phrasesignored": ["the"], "quotedphrasesnotfound": [], "outputmessages": []},
                                   errorlist={"phrasesnotfound": ["xyzzyq", "qqqzz"], "fieldsnotfound": []})))
    out = run(pubmed.search("  osimertinib \n the  NSCLC xyzzyq ", retmax=20, client=ncbi.client()))
    assert out["ids"] == ["39100001", "39100002", "39100003"]  # junk ids dropped
    assert out["count"] == 1234 and out["term"] == "osimertinib the NSCLC xyzzyq" and out["years"] == 10
    assert out["translation"] == '"carcinoma, non small cell lung"[MeSH Terms] AND osimertinib[All Fields]'
    assert out["warnings"] == ["phrasesignored: the", "phrasesnotfound: xyzzyq, qqqzz"]
    p, y = ncbi.params(), datetime.now().year
    assert p["db"] == "pubmed" and p["term"] == "osimertinib the NSCLC xyzzyq" and p["retmode"] == "json" and p["sort"] == "relevance"
    assert p["retmax"] == "20" and p["tool"] == "vaidyx-tb" and "email" not in p and "api_key" not in p
    assert (p["datetype"], p["mindate"], p["maxdate"]) == ("pdat", str(y - 9), str(y))
    assert ncbi.seen[0].url.path == "/entrez/eutils/esearch.fcgi" and ncbi.seen[0].url.host == "eutils.ncbi.nlm.nih.gov"
    assert out["provenance"]["status"] == 200 and out["provenance"]["tries"] == 1


@pytest.mark.parametrize("years", [None, 0])
def test_search_every_year_sends_no_dates(years):
    ncbi = NCBI(steps(esearch_json()))
    out = run(pubmed.search("NSCLC", years=years, client=ncbi.client()))
    p = ncbi.params()
    assert not {"datetype", "mindate", "maxdate"} & set(p) and out["years"] == years


def test_search_years_window_and_retmax_bounds():
    ncbi = NCBI(steps(esearch_json()))
    y = datetime.now().year
    run(pubmed.search("NSCLC", years=3, retmax=5000, client=ncbi.client()))
    assert (ncbi.params()["mindate"], ncbi.params()["maxdate"], ncbi.params()["retmax"]) == (str(y - 2), str(y), str(pubmed.MAX_IDS))
    run(pubmed.search("NSCLC", years=1, retmax=0, client=ncbi.client()))
    assert (ncbi.params()["mindate"], ncbi.params()["retmax"]) == (str(y), "1")
    run(pubmed.search("NSCLC", retmax=-7, client=ncbi.client()))
    assert ncbi.params()["retmax"] == "1"


def test_search_no_hits_comes_back_with_the_reason():
    ncbi = NCBI(steps(esearch_json(ids=(), count="0", warninglist={"phrasesignored": [], "quotedphrasesnotfound": [], "outputmessages": ["No items found."]},
                                   errorlist={"phrasesnotfound": ["zzqxq"], "fieldsnotfound": []})))
    out = run(pubmed.search("zzqxq", client=ncbi.client()))
    assert out["ids"] == [] and out["count"] == 0 and out["warnings"] == ["outputmessages: No items found.", "phrasesnotfound: zzqxq"]


def test_search_odd_but_valid_shapes():
    # count missing or not a number: the ids are counted; warninglist / errorlist not dicts: ignored, never a crash
    ncbi = NCBI(steps(httpx.Response(200, json={"esearchresult": {"idlist": ["39100001", 39100002], "count": "many", "warninglist": ["x"], "errorlist": None}})))
    out = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert out["ids"] == ["39100001", "39100002"] and out["count"] == 2 and out["warnings"] == [] and out["translation"] == ""


# ---- 2. esearch error shapes ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer, said", [
    (httpx.Response(200, json={"error": "API rate limit exceeded", "api-key": "203.0.113.9", "count": "11", "limit": "10"}), "PubMed: API rate limit exceeded"),
    (httpx.Response(200, json={"error": "API key invalid", "api-key": KEY, "type": "invalid", "status": "unknown"}), "PubMed: API key invalid"),
    (httpx.Response(200, json={"esearchresult": {"ERROR": "Invalid query syntax near ((("}}), "PubMed: Invalid query syntax near ((("),
    (httpx.Response(200, json={"header": {}, "esearchresult": {"ERROR": "x" * 500}}), "PubMed: " + "x" * 160),
    (httpx.Response(200, content=b"<html><body><h1>Service unavailable</h1></body></html>"), "not JSON"),
    (httpx.Response(200, content=b""), "not JSON"),
    (httpx.Response(200, content=b'{"esearchresult": {"idlist": ["391'), "not JSON"),  # cut off mid-answer
    (httpx.Response(200, content=b"\xff\xfe\x00\xd8garbage"), "not JSON"),
    (httpx.Response(200, json=[]), "empty search answer"),
    (httpx.Response(200, json=[{"esearchresult": {"idlist": ["39100001"]}}]), "empty search answer"),
    (httpx.Response(200, json="esearchresult"), "empty search answer"),
    (httpx.Response(200, content=b"null"), "empty search answer"),
    (httpx.Response(200, json={"header": {"type": "esearch"}}), "no search result"),
    (httpx.Response(200, json={"esearchresult": None}), "no search result"),
    (httpx.Response(200, json={"esearchresult": ["39100001"]}), "no search result"),
])
def test_search_error_shapes_raise_never_an_empty_result(answer, said):
    ncbi = NCBI(steps(answer))
    with pytest.raises(pubmed.PubMedError) as e:
        run(pubmed.search("NSCLC", client=ncbi.client()))
    assert said in str(e.value) and "203.0.113.9" not in str(e.value) and KEY not in str(e.value)
    assert len(str(e.value)) <= 200 and len(ncbi.seen) == 1  # an answer, even a bad one, is not retried


@pytest.mark.parametrize("term", ["", "   \n\t ", None])
def test_search_without_words_asks_nothing(term):
    ncbi = NCBI(steps(esearch_json()))
    with pytest.raises(pubmed.PubMedError, match="no search words"):
        run(pubmed.search(term, client=ncbi.client()))
    assert ncbi.seen == []


# ---- 3. retries -----------------------------------------------------------------------------------------------------------------------
def test_429_then_200_succeeds_on_the_second_try(waits):
    ncbi = NCBI(steps(httpx.Response(429, json={"error": "API rate limit exceeded"}), esearch_json()))
    out = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert out["ids"] == ["39100001", "39100002"] and out["provenance"]["tries"] == 2 and len(ncbi.seen) == 2 and waits == [0.0]


@pytest.mark.parametrize("header, wait", [("3", 3.0), ("0.5", 0.5), ("120", 10.0), ("inf", 10.0), ("-5", 0.0), ("nan", 0.0), ("", 0.0),
                                          ("Wed, 21 Oct 2026 07:28:00 GMT", 0.0), ("soon", 0.0)])
def test_retry_after_is_honoured_but_capped(waits, header, wait):
    ncbi = NCBI(steps(httpx.Response(429, headers={"Retry-After": header}), esearch_json()))
    out = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert out["provenance"]["tries"] == 2 and waits == [wait]


def test_retry_after_and_back_off_take_the_longer(waits, monkeypatch):
    monkeypatch.setattr(pubmed, "DELAYS", (1.0, 2.0, 4.0))
    ncbi = NCBI(steps(httpx.Response(503, headers={"Retry-After": "0.2"}), httpx.Response(429, headers={"Retry-After": "600"}),
                      httpx.Response(502), esearch_json()))
    out = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert out["provenance"]["tries"] == 4 and waits == [1.0, pubmed.MAX_WAIT, 4.0]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_busy_or_server_error_four_times_raises(waits, status):
    ncbi = NCBI(steps(httpx.Response(status, text="<html>busy</html>")))
    with pytest.raises(pubmed.PubMedError) as e:
        run(pubmed.search("NSCLC", client=ncbi.client()))
    msg = str(e.value)
    assert f"answered {status}" in msg and "4 tries" in msg and msg.startswith("PubMed")
    assert len(ncbi.seen) == 4 and len(waits) == 3  # no wait after the last try
    assert ("(busy)" in msg) == (status == 429)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 414, 301, 302])
def test_client_errors_and_redirects_are_not_retried(waits, status):
    ncbi = NCBI(steps(httpx.Response(status, headers={"Location": "https://example.org/"}, text="Bad Request")))
    with pytest.raises(pubmed.PubMedError) as e:
        run(pubmed.search("NSCLC", client=ncbi.client()))
    assert str(e.value) == f"PubMed answered {status}" and len(ncbi.seen) == 1 and waits == []


@pytest.mark.parametrize("exc, said", [(httpx.ReadTimeout, "no answer in 15 s"), (httpx.ConnectTimeout, "no answer in 15 s"),
                                       (httpx.PoolTimeout, "no answer in 15 s"), (httpx.ConnectError, "could not connect (ConnectError)"),
                                       (httpx.ReadError, "(ReadError)"), (httpx.RemoteProtocolError, "(RemoteProtocolError)")])
def test_time_outs_and_connection_errors_are_retried_then_raise(waits, monkeypatch, exc, said):
    monkeypatch.setenv("TB_PUBMED_API_KEY", KEY)  # the failure text from httpx carries the URL with the key: never shown
    ncbi = NCBI(steps(exc))
    with pytest.raises(pubmed.PubMedError) as e:
        run(pubmed.fetch(["39100001"], client=ncbi.client()))
    msg = str(e.value)
    assert said in msg and msg.endswith("after 4 tries") and msg.startswith("PubMed ") and KEY not in msg and "http" not in msg
    assert len(ncbi.seen) == 4 and len(waits) == 3 and ncbi.params()["api_key"] == KEY
    assert not pubmed.CACHE_DIR.exists() or not list(pubmed.CACHE_DIR.iterdir())


def test_timeout_message_reads_as_a_sentence():
    ncbi = NCBI(steps(httpx.ReadTimeout))
    with pytest.raises(pubmed.PubMedError) as e:
        run(pubmed.search("NSCLC", client=ncbi.client()))
    assert str(e.value) == "PubMed gave no answer in 15 s after 4 tries"


def test_mixed_failures_then_success():
    ncbi = NCBI(steps(httpx.ConnectError, httpx.Response(503), httpx.ReadTimeout, httpx.Response(200, content=article_set(article("39100001")))))
    out = run(pubmed.fetch(["39100001"], client=ncbi.client()))
    assert [p["pmid"] for p in out["papers"]] == ["39100001"] and out["calls"][0]["tries"] == 4 and len(ncbi.seen) == 4


# ---- 4. efetch XML --------------------------------------------------------------------------------------------------------------------
def test_parse_a_realistic_article_set_with_the_pubmed_doctype():
    body = article_set(RCT, META, NO_PMID, DELETED, BOOK)
    assert body.startswith(b'<?xml version="1.0" ?>\n<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN"')
    recs = {r["pmid"]: r for r in pubmed.parse(body)}
    assert list(recs) == ["39100001", "39100002", "20301425"]  # the broken record and the deleted citation are left out
    r = recs["39100001"]
    assert r["title"] == "Adjuvant osimertinib in resected EGFR-mutated NSCLC: a randomised trial."
    assert r["sections"] == [
        {"label": "BACKGROUND", "text": "Adjuvant therapy after resection of EGFR-mutated NSCLC is uncertain."},
        {"label": "METHODS", "text": "Patients with stage IB to IIIA disease were randomly assigned (1:1) to osimertinib 80 mg or placebo."},
        {"label": "RESULTS", "text": "Disease-free survival at 24 months was 89% versus 52% (HR 0.21; 95% CI 0.16 to 0.28; p<10-4); Tmax was 6 h."},
        {"label": "CONCLUSIONS", "text": "Osimertinib improved disease-free survival (≥ 2 years of follow-up) & was tolerable."}]
    assert r["abstract"] == "\n".join(f"{s['label']}: {s['text']}" for s in r["sections"]) and "Copyright" not in r["abstract"]
    assert r["has_abstract"] is True and "<" not in r["abstract"].replace("p<10", "")
    assert r["journal"] == "Synthetic Journal of Thoracic Oncology" and r["journal_abbr"] == "Synth J Thorac Oncol" and r["year"] == "2024"
    assert r["authors"] == ["Rao A", "Iyer L", "SYNTH-LUNG Trial Investigators", "Nair K"]  # ValidYN="N" skipped, the group kept
    assert r["authors_line"] == "Rao A, Iyer L, SYNTH-LUNG Trial Investigators, et al."
    assert r["types"] == ["Journal Article", "Randomized Controlled Trial", "Clinical Trial, Phase III", "Multicenter Study"]
    assert (r["tier"], r["study_type"]) == (2, "Randomised trial") and r["preprint"] is False
    assert (r["retracted"], r["retraction_notice"], r["concern"], r["erratum"]) == (False, False, False, True)
    assert r["india"] is True and r["languages"] == ["eng"] and r["mesh"] == ["Carcinoma, Non-Small-Cell Lung", "ErbB Receptors", "Humans"]
    assert r["doi"] == "10.5555/synth.2024.001" and r["pmcid"] == "PMC11000001"  # never a reference's DOI
    assert r["status"] == "ppublish" and r["url"] == "https://pubmed.ncbi.nlm.nih.gov/39100001/"
    m = recs["39100002"]
    assert m["has_abstract"] is False and m["abstract"] == "" and m["sections"] == [] and m["year"] == "2019"
    assert (m["tier"], m["study_type"]) == (1, "Meta-analysis") and m["india"] is False  # Indiana is not India
    assert m["doi"] == "" and m["pmcid"] == "" and m["authors_line"] == "Brown T"
    b = recs["20301425"]
    assert (b["study_type"], b["tier"]) == ("Book chapter", 5) and b["title"] == "BRCA1- and BRCA2-associated hereditary breast and ovarian cancer"
    assert b["journal"] == "SynthReviews®" and b["journal_abbr"] == "" and b["year"] == "1993" and b["authors"] == ["Kulkarni M"]
    assert b["abstract"] == "CLINICAL CHARACTERISTICS: A synthetic chapter abstract." and b["india"] is True and b["types"] == ["Review"]
    assert b["url"] == "https://pubmed.ncbi.nlm.nih.gov/20301425/" and b["retracted"] is False and b["mesh"] == []
    json.dumps(list(recs.values()))  # every record can be cached as JSON


def test_inline_markup_and_labels_are_joined_cleanly():
    rec = pubmed.parse(article_set(article("39100010", title="<b>PD-L1</b> &#8805;50% in <i>KRAS</i><sup>G12C</sup>\n   NSCLC",
                                           abstract=(("  KEY   FINDINGS ", "CO<sub>2</sub> and <u>Ki-67</u>\n\t\t  index"), ("RESULTS", ""),
                                                     ("", "An unlabelled <i>last</i>   line.")))))[0]
    assert rec["title"] == "PD-L1 ≥50% in KRASG12C NSCLC"
    assert rec["sections"] == [{"label": "KEY FINDINGS", "text": "CO2 and Ki-67 index"}, {"label": "", "text": "An unlabelled last line."}]
    assert rec["abstract"] == "KEY FINDINGS: CO2 and Ki-67 index\nAn unlabelled last line."


@pytest.mark.parametrize("pubdate, article_date, completed, year", [
    ("<Year>2024</Year><Month>Mar</Month>", "", "", "2024"),
    ("<MedlineDate>2019 Nov-Dec</MedlineDate>", "", "", "2019"),
    ("<MedlineDate>1998 Dec-1999 Jan</MedlineDate>", "", "", "1998"),
    ("<MedlineDate>Winter 2017</MedlineDate>", "", "", "2017"),
    # the issue's date is the citation's year; the earlier electronic date only when the issue has none
    ("<MedlineDate>2020 Jan-Feb</MedlineDate>", '<ArticleDate DateType="Electronic"><Year>2019</Year><Month>12</Month><Day>5</Day></ArticleDate>', "", "2020"),
    ("<Year>2021</Year>", '<ArticleDate DateType="Electronic"><Year>2020</Year></ArticleDate>', "", "2021"),
    ("<Month>Dec</Month>", '<ArticleDate DateType="Electronic"><Year>2021</Year><Month>11</Month></ArticleDate>', "", "2021"),
    ("", "", "<DateCompleted><Year>2017</Year><Month>1</Month><Day>1</Day></DateCompleted>", "2017"),
    ("<MedlineDate>Spring</MedlineDate>", "", "", ""),
])
def test_year_rules(pubdate, article_date, completed, year):
    assert pubmed.parse(article_set(article("39100011", pubdate=pubdate, article_date=article_date, completed=completed)))[0]["year"] == year


@pytest.mark.parametrize("types, tier, label", [
    (["Journal Article", "Meta-Analysis"], 1, "Meta-analysis"),
    (["Review", "Network Meta-Analysis"], 1, "Meta-analysis"),
    (["Systematic Review", "Review"], 1, "Systematic review"),
    (["Journal Article", "Randomized Controlled Trial"], 2, "Randomised trial"),
    ([" randomized controlled trial  "], 2, "Randomised trial"),
    (["Clinical Trial, Phase II"], 2, "Clinical trial"),
    (["Practice Guideline"], 3, "Guideline"),
    (["Journal Article", "Review"], 4, "Review"),
    (["Observational Study"], 5, "Observational study"),
    (["Journal Article"], 5, "Journal article"),
    ([], 5, "Journal article"),
    (["Case Reports", "Journal Article"], 6, "Case report"),
    (["Letter", "Comment"], 7, "Comment or letter"),
    (["Preprint", "Randomized Controlled Trial"], 8, "Preprint"),  # a preprint is never a trial's tier
])
def test_publication_types_give_study_type_and_tier(types, tier, label):
    assert pubmed.study_type(types) == (tier, label)
    rec = pubmed.parse(article_set(article("39100012", types=types)))[0]
    assert (rec["tier"], rec["study_type"], rec["preprint"]) == (tier, label, label == "Preprint")


@pytest.mark.parametrize("types, refs, flags", [
    (["Journal Article", "Retracted Publication"], [], dict(retracted=True, retraction_notice=False)),
    (["Journal Article"], ["RetractionIn"], dict(retracted=True, retraction_notice=False)),
    (["Retraction of Publication"], ["RetractionOf"], dict(retracted=False, retraction_notice=True)),
    (["Case Reports"], ["ExpressionOfConcernIn"], dict(retracted=False, concern=True, erratum=False)),
    (["Journal Article"], ["ErratumIn", "CommentIn"], dict(retracted=False, concern=False, erratum=True)),
    (["Journal Article"], ["RetractionOf", "ExpressionOfConcernFor", "ErratumFor"], dict(retracted=False, retraction_notice=False, concern=False, erratum=False)),
])
def test_retraction_concern_and_erratum_flags(types, refs, flags):
    rec = pubmed.parse(article_set(article("39100013", types=types, refs=refs)))[0]
    assert {k: rec[k] for k in flags} == flags and rec["pmid"] == "39100013"  # the PMID of a comment or correction is never the paper's


def test_authors_and_india_mark():
    au = ('<Author ValidYN="Y"><LastName>Smith</LastName><ForeName>Jo</ForeName><Initials>J</Initials>'
          '<AffiliationInfo><Affiliation>Indianapolis Cancer Center, Indiana, USA; Indian River Clinic, FL.</Affiliation></AffiliationInfo></Author>'
          '<Author ValidYN="N"><LastName>Ghost</LastName><Initials>G</Initials></Author>'
          '<Author><LastName>Onlylast</LastName></Author><Author ValidYN="Y"><CollectiveName>Synthetic  Study\n Group</CollectiveName></Author>'
          '<Author ValidYN="Y"></Author>')
    rec = pubmed.parse(article_set(article("39100014", authors=au)))[0]
    assert rec["authors"] == ["Smith J", "Onlylast", "Synthetic Study Group"] and rec["india"] is False
    rec = pubmed.parse(article_set(article("39100015", authors="")))[0]
    assert rec["authors"] == [] and rec["authors_line"] == "" and rec["india"] is False
    au = '<Author ValidYN="Y"><LastName>Das</LastName><Initials>P</Initials><AffiliationInfo><Affiliation>AIIMS, New Delhi 110029, India</Affiliation></AffiliationInfo></Author>'
    assert pubmed.parse(article_set(article("39100016", authors=au)))[0]["india"] is True


def test_doi_and_pmc_ids():
    rec = pubmed.parse(article_set(article("39100017", doi="10.5555/synth.17", pmc="PMC1700017")))[0]
    assert (rec["doi"], rec["pmcid"]) == ("10.5555/synth.17", "PMC1700017")


# ---- 5. efetch error shapes -----------------------------------------------------------------------------------------------------------
BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
 <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
 <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
 <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
 <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>39100001</PMID><Article><ArticleTitle>&lol9;</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
EXTERNAL_ENTITY = b"""<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>39100001</PMID><Article><ArticleTitle>&xxe;</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
PARAMETER_ENTITY = b"""<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet [<!ENTITY % remote SYSTEM "http://127.0.0.1:9/evil.dtd"> %remote;]>
<PubmedArticleSet/>"""
HTML_WELL_FORMED = b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>NCBI</title></head><body><h1>Service unavailable</h1></body></html>'
HTML_LOOSE = b'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>503</title></head><body><p>Busy&nbsp;now<br></body></html>'


@pytest.mark.parametrize("body, said", [
    (b'<?xml version="1.0" encoding="UTF-8" ?>\n<!DOCTYPE eFetchResult PUBLIC "-//NLM//DTD efetch 20131226//EN" '
     b'"https://eutils.ncbi.nlm.nih.gov/eutils/dtd/20131226/efetch.dtd">\n<eFetchResult>\n\t<ERROR>Empty id list - nothing todo</ERROR>\n</eFetchResult>',
     "PubMed: Empty id list - nothing todo"),
    (b"<eFetchResult><ERROR>" + b"y" * 400 + b"</ERROR></eFetchResult>", "PubMed: " + "y" * 160),
    (HTML_WELL_FORMED, "instead of records"),
    (HTML_LOOSE, "could not be read"),
    (article_set(RCT)[:900], "could not be read"),  # cut off mid-record
    (article_set(RCT).replace(b"</ArticleTitle>", b"</ArticleTitl>"), "could not be read"),
    (b"", "could not be read"),
    (b"   \n", "could not be read"),
    (b'{"error":"API rate limit exceeded","api-key":"203.0.113.9","count":"11","limit":"10"}', "could not be read"),
    (BILLION_LAUGHS, "could not be read"),
    (EXTERNAL_ENTITY, "could not be read"),
    (PARAMETER_ENTITY, "could not be read"),
    (b"<PubmedArticle><MedlineCitation><PMID>39100001</PMID></MedlineCitation></PubmedArticle>", "'PubmedArticle' instead of records"),
])
def test_efetch_error_shapes_raise(body, said):
    t = time.time()
    with pytest.raises(pubmed.PubMedError) as e:
        pubmed.parse(body)
    assert said in str(e.value) and "203.0.113.9" not in str(e.value) and "root:" not in str(e.value) and time.time() - t < 1.0
    ncbi = NCBI(steps(httpx.Response(200, content=body)))
    with pytest.raises(pubmed.PubMedError):
        run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client()))
    assert len(ncbi.seen) == 1 and not (pubmed.CACHE_DIR / "39100001.json").exists()  # an answer that is an error is not retried, nothing cached


def test_entity_payloads_are_never_expanded():
    for body in (BILLION_LAUGHS, EXTERNAL_ENTITY):
        try:
            pubmed.parse(body)
        except pubmed.PubMedError as e:
            assert "lol" not in str(e) and "passwd" not in str(e)
        else:
            raise AssertionError("an entity payload was parsed")


def test_empty_article_set_means_every_id_is_missing():
    ncbi = NCBI(steps(httpx.Response(200, content=article_set())))
    out = run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client()))
    assert out["papers"] == [] and out["missing"] == ["39100001", "39100002"] and len(out["calls"]) == 1
    assert pubmed.parse(b'<?xml version="1.0"?>' + DOCTYPE.encode() + b"<PubmedArticleSet/>") == []


# ---- 6. fetch -------------------------------------------------------------------------------------------------------------------------
def test_fetch_keeps_the_order_asked_and_drops_duplicates_and_junk():
    ncbi = NCBI(lambda req, n: httpx.Response(200, content=article_set(*(article(i) for i in reversed(req.url.params["id"].split(","))))))
    asked = ["39100003", " 39100001 ", 39100002, "39100001", "abc", "", None, "12a", "-5", "3.0", "39100003", "١٢٣", "²", "１２"]
    out = run(pubmed.fetch(asked, client=ncbi.client()))
    assert [p["pmid"] for p in out["papers"]] == ["39100003", "39100001", "39100002"] and out["missing"] == []
    assert ncbi.ids() == ["39100003", "39100001", "39100002"] and len(ncbi.seen) == 1  # non-ASCII digits are not PMIDs
    p = ncbi.params()
    assert p["db"] == "pubmed" and p["retmode"] == "xml" and p["tool"] == "vaidyx-tb" and ncbi.seen[0].url.path.endswith("/efetch.fcgi")


@pytest.mark.parametrize("asked", [[], None, ["abc", "", "  "], ()])
def test_fetch_of_nothing_asks_nothing(asked):
    ncbi = NCBI(efetch_echo)
    assert run(pubmed.fetch(asked, client=ncbi.client())) == {"papers": [], "missing": [], "calls": []} and ncbi.seen == []


def test_fetch_caps_at_max_ids_in_batches():
    ncbi = NCBI(efetch_echo)
    asked = [str(39000000 + i) for i in range(450)]
    out = run(pubmed.fetch(asked, client=ncbi.client()))
    assert len(out["papers"]) == pubmed.MAX_IDS == 200 and [p["pmid"] for p in out["papers"]] == asked[:200] and out["missing"] == []
    assert [len(ncbi.ids(i)) for i in range(len(ncbi.seen))] == [50, 50, 50, 50] and len(out["calls"]) == 4
    assert sum((ncbi.ids(i) for i in range(4)), []) == asked[:200]
    assert all(p["provenance"]["url"] == out["calls"][k // 50]["url"] for k, p in enumerate(out["papers"]))


def test_fetch_of_a_huge_id_list_stops_at_the_cap_quickly():
    ncbi = NCBI(efetch_echo)
    t = time.time()
    out = run(pubmed.fetch((str(30000000 + i) for i in range(300000)), client=ncbi.client()))
    assert len(out["papers"]) == 200 and len(ncbi.seen) == 4 and time.time() - t < 3.0
    out = run(pubmed.fetch(map(str, itertools.count(40000000)), client=ncbi.client(), fresh=True))  # endless: still the first 200
    assert len(out["papers"]) == 200


def test_fetch_lists_missing_ids_and_ignores_records_not_asked():
    def answer(req, n):
        return httpx.Response(200, content=article_set(article("39100001"), article("39100777"), article("39100003")))
    ncbi = NCBI(answer)
    out = run(pubmed.fetch(["39100001", "39100002", "39100003", "39100004"], client=ncbi.client()))
    assert [p["pmid"] for p in out["papers"]] == ["39100001", "39100003"] and out["missing"] == ["39100002", "39100004"]


def test_fetch_error_in_a_later_batch_raises():
    ncbi = NCBI(lambda req, n: efetch_echo(req, n) if n == 1 else httpx.Response(200, content=b"<eFetchResult><ERROR>Unable to obtain query #1</ERROR></eFetchResult>"))
    with pytest.raises(pubmed.PubMedError, match="Unable to obtain query #1"):
        run(pubmed.fetch([str(39000000 + i) for i in range(60)], client=ncbi.client()))
    assert len(ncbi.seen) == 2


def test_search_and_fetch_without_a_client_open_their_own(monkeypatch):
    ncbi = NCBI(lambda req, n: esearch_json() if req.url.path.endswith("esearch.fcgi") else efetch_echo(req, n))
    monkeypatch.setattr(pubmed, "_client", ncbi.client)
    assert run(pubmed.search("NSCLC"))["ids"] == ["39100001", "39100002"]
    out = run(pubmed.fetch(["39100001"]))
    assert [p["pmid"] for p in out["papers"]] == ["39100001"] and len(ncbi.seen) == 2


def test_cache_second_fetch_asks_nothing_and_fresh_refetches():
    ncbi = NCBI(efetch_echo)
    first = run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client()))
    assert len(ncbi.seen) == 1 and all(p["provenance"]["cached"] is False for p in first["papers"])
    assert sorted(f.name for f in pubmed.CACHE_DIR.iterdir()) == ["39100001.json", "39100002.json"]  # no tmp file left behind
    again = run(pubmed.fetch(["39100002", "39100001"], client=ncbi.client()))
    assert len(ncbi.seen) == 1 and again["calls"] == [] and [p["pmid"] for p in again["papers"]] == ["39100002", "39100001"]
    assert all(p["provenance"]["cached"] is True for p in again["papers"])
    assert again["papers"][1]["provenance"]["sha256"] == first["calls"][0]["sha256"]  # the provenance of the call it came from
    assert {k: v for k, v in again["papers"][1].items() if k != "provenance"} == {k: v for k, v in first["papers"][0].items() if k != "provenance"}
    part = run(pubmed.fetch(["39100001", "39100005"], client=ncbi.client()))
    assert ncbi.ids() == ["39100005"] and [p["provenance"]["cached"] for p in part["papers"]] == [True, False]
    fresh = run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client(), fresh=True))
    assert ncbi.ids() == ["39100001", "39100002"] and all(p["provenance"]["cached"] is False for p in fresh["papers"]) and len(fresh["calls"]) == 1


def test_cache_entry_older_than_cache_days_is_fetched_again():
    ncbi = NCBI(efetch_echo)
    run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client()))
    for pmid, age in (("39100001", pubmed.CACHE_DAYS * 86400 + 60), ("39100002", pubmed.CACHE_DAYS * 86400 - 60)):
        p = pubmed.CACHE_DIR / f"{pmid}.json"
        d = json.loads(p.read_text())
        d["saved"] = time.time() - age
        p.write_text(json.dumps(d))
    out = run(pubmed.fetch(["39100001", "39100002"], client=ncbi.client()))
    assert ncbi.ids() == ["39100001"] and [p["provenance"]["cached"] for p in out["papers"]] == [False, True]
    assert time.time() - json.loads((pubmed.CACHE_DIR / "39100001.json").read_text())["saved"] < 60  # saved again


NOW = time.time()


@pytest.mark.parametrize("content", [
    b"{not json", b"", b"\xff\xfe\x00\x81", b"[]", b"null", b'"a string"', b'{"saved": "yesterday", "paper": {"pmid": "39100001"}}',
    b'{"saved": [1], "paper": {"pmid": "39100001"}}', b'{"saved": {"t": 1}, "paper": {"pmid": "39100001"}}',
    f'{{"saved": {NOW}, "paper": "39100001"}}'.encode(), f'{{"saved": {NOW}, "paper": {{"pmid": "39100999"}}}}'.encode(),
    f'{{"saved": {NOW}, "paper": {{"pmid": 39100001}}}}'.encode(), f'{{"saved": {NOW}, "paper": {{"pmid": "39100001", "provenance": "x"}}}}'.encode(),
    f'{{"saved": {NOW}, "paper": {{"pmid": "39100001", "provenance": [1, 2]}}}}'.encode(), f'{{"saved": {NOW}}}'.encode(),
])
def test_a_corrupt_cache_file_is_ignored(content):
    pubmed.CACHE_DIR.mkdir(parents=True)
    (pubmed.CACHE_DIR / "39100001.json").write_bytes(content)
    ncbi = NCBI(efetch_echo)
    out = run(pubmed.fetch(["39100001"], client=ncbi.client()))
    assert len(ncbi.seen) == 1 and out["papers"][0]["pmid"] == "39100001" and out["papers"][0]["provenance"]["cached"] is False
    assert json.loads((pubmed.CACHE_DIR / "39100001.json").read_text())["paper"]["pmid"] == "39100001"  # replaced by a good one


def test_cache_directory_that_cannot_be_written_does_not_raise(tmp_path, monkeypatch):
    blocker = tmp_path / "a_file"
    blocker.write_text("not a directory")
    for where in (blocker / "pubmed_cache", blocker):
        monkeypatch.setattr(pubmed, "CACHE_DIR", where)
        ncbi = NCBI(efetch_echo)
        assert [p["pmid"] for p in run(pubmed.fetch(["39100001"], client=ncbi.client()))["papers"]] == ["39100001"]
        run(pubmed.fetch(["39100001"], client=ncbi.client()))
        assert len(ncbi.seen) == 2  # nothing cached, fetched again
    assert blocker.read_text() == "not a directory"


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_read_only_cache_directory_does_not_raise():
    pubmed.CACHE_DIR.mkdir(parents=True)
    pubmed.CACHE_DIR.chmod(0o500)
    try:
        ncbi = NCBI(efetch_echo)
        out = run(pubmed.fetch(["39100001"], client=ncbi.client()))
        assert [p["pmid"] for p in out["papers"]] == ["39100001"] and list(pubmed.CACHE_DIR.iterdir()) == []
    finally:
        pubmed.CACHE_DIR.chmod(0o700)


# ---- 7. provenance and settings -------------------------------------------------------------------------------------------------------
def test_provenance_has_the_tool_never_the_email_or_the_api_key(monkeypatch):
    monkeypatch.setenv("TB_PUBMED_EMAIL", f"  {EMAIL} ")
    monkeypatch.setenv("TB_PUBMED_API_KEY", f" {KEY} ")
    bodies = []

    def answer(req, n):
        r = esearch_json() if req.url.path.endswith("esearch.fcgi") else efetch_echo(req, n)
        bodies.append(r.content)
        return r
    ncbi = NCBI(answer)
    s = run(pubmed.search("NSCLC", client=ncbi.client()))
    f = run(pubmed.fetch(s["ids"], client=ncbi.client()))
    for req in ncbi.seen:  # the key and the email go to NCBI
        assert req.url.params["api_key"] == KEY and req.url.params["email"] == EMAIL and req.url.params["tool"] == "vaidyx-tb"
    for prov, body in ((s["provenance"], bodies[0]), (f["calls"][0], bodies[1])):
        u = httpx.URL(prov["url"])
        assert u.params["tool"] == "vaidyx-tb" and "email" not in u.params and "api_key" not in u.params and KEY not in prov["url"]
        assert prov["sha256"] == hashlib.sha256(body).hexdigest() and prov["bytes"] == len(body) and prov["status"] == 200 and prov["tries"] == 1
        assert datetime.fromisoformat(prov["at"]).tzinfo is not None and prov["seconds"] >= 0
    assert u.host == "eutils.ncbi.nlm.nih.gov" and u.params["id"] == "39100001,39100002"
    assert KEY not in json.dumps(s) and KEY not in json.dumps(f) and all(p["provenance"]["url"] == f["calls"][0]["url"] for p in f["papers"])
    assert not any(KEY in p.read_text() for p in pubmed.CACHE_DIR.iterdir())  # never in the cache on disk


def test_key_is_never_in_an_error_message(monkeypatch):
    monkeypatch.setenv("TB_PUBMED_API_KEY", KEY)
    for answer in (httpx.Response(400, text=f"bad key {KEY}"), httpx.Response(503, text=KEY), httpx.ConnectError,
                   httpx.Response(200, json={"error": "API key invalid", "api-key": KEY})):
        ncbi = NCBI(steps(answer))
        with pytest.raises(pubmed.PubMedError) as e:
            run(pubmed.search("NSCLC", client=ncbi.client()))
        assert KEY not in str(e.value) and KEY not in repr(e.value)


def test_settings_from_the_file_and_env_overrides(monkeypatch):
    pubmed.SETTINGS.write_text(json.dumps({"email": "file@example.org", "api_key": "FILE-SYNTHETIC-KEY"}))
    assert pubmed.settings() == {"email": "file@example.org", "api_key": "FILE-SYNTHETIC-KEY"}
    ncbi = NCBI(steps(esearch_json()))
    s = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert ncbi.params()["api_key"] == "FILE-SYNTHETIC-KEY" and "FILE-SYNTHETIC-KEY" not in s["provenance"]["url"]
    monkeypatch.setenv("TB_PUBMED_EMAIL", EMAIL)
    monkeypatch.setenv("TB_PUBMED_API_KEY", KEY)
    assert pubmed.settings() == {"email": EMAIL, "api_key": KEY}


@pytest.mark.parametrize("content", ["{broken", "[1, 2]", '"text"', "null", '{"email": null, "api_key": 0}', ""])
def test_bad_settings_file_means_no_settings(content):
    pubmed.SETTINGS.write_text(content)
    assert pubmed.settings() == {"email": "", "api_key": ""}
    ncbi = NCBI(steps(esearch_json()))
    s = run(pubmed.search("NSCLC", client=ncbi.client()))
    assert "email" not in ncbi.params() and "api_key" not in ncbi.params() and "email" not in httpx.URL(s["provenance"]["url"]).params


def test_settings_path_that_is_a_directory_means_no_settings():
    pubmed.SETTINGS.mkdir()
    assert pubmed.settings() == {"email": "", "api_key": ""}


# ---- 8. the pace ----------------------------------------------------------------------------------------------------------------------
class Clock:
    """time.monotonic and asyncio.sleep for _turn: a sleep moves the clock on (advance=True) or leaves it standing (advance=False)."""

    def __init__(self, advance=True):
        self.t, self.advance, self.waits = 1000.0, advance, []

    def monotonic(self):
        return self.t

    async def sleep(self, s):
        self.waits.append(s)
        if self.advance:
            self.t += s


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(pubmed, "_turn", REAL_TURN)
    monkeypatch.setattr(pubmed, "_next_at", 0.0)
    monkeypatch.setattr(pubmed, "time", _Proxy(time, monotonic=c.monotonic))
    monkeypatch.setattr(pubmed, "asyncio", _Proxy(asyncio, sleep=c.sleep))
    return c


@pytest.mark.parametrize("has_key, gap", [(False, 0.34), (True, 0.11)])
def test_pace_spaces_back_to_back_calls(clock, has_key, gap):
    starts = []

    async def go():
        for _ in range(3):
            await pubmed._turn(has_key)
            starts.append(clock.t)
    run(go())
    assert clock.waits == pytest.approx([gap, gap])
    assert [b - a for a, b in zip(starts, starts[1:])] == pytest.approx([gap, gap])
    clock.t += 5.0  # after a quiet spell the next call goes at once
    run(pubmed._turn(has_key))
    assert len(clock.waits) == 2


def test_pace_is_shared_by_concurrent_calls(clock):
    clock.advance = False

    async def go():
        await asyncio.gather(*(pubmed._turn(False) for _ in range(4)))
    run(go())
    assert sorted(clock.waits) == pytest.approx([0.34, 0.68, 1.02])


def test_every_try_waits_its_turn_with_the_right_gap(monkeypatch):
    turns = []

    async def turn(has_key):
        turns.append(has_key)
    monkeypatch.setattr(pubmed, "_turn", turn)
    ncbi = NCBI(steps(httpx.Response(429), httpx.Response(503), esearch_json()))
    run(pubmed.search("NSCLC", client=ncbi.client()))
    assert turns == [False, False, False]
    monkeypatch.setenv("TB_PUBMED_API_KEY", KEY)
    run(pubmed.search("NSCLC", client=NCBI(steps(esearch_json())).client()))
    assert turns[-1] is True


# ---- 9. concurrency -------------------------------------------------------------------------------------------------------------------
def test_ten_concurrent_fetches_through_429s_all_succeed(monkeypatch):
    busy = 6

    def answer(req, n):
        return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "API rate limit exceeded"}) if n <= busy else efetch_echo(req, n)
    ncbi = NCBI(answer)
    monkeypatch.setattr(pubmed, "_client", ncbi.client)
    asked = [[str(39100100 + k), str(39100200 + k)] for k in range(10)]

    async def go():
        return await asyncio.gather(*(pubmed.fetch(ids) for ids in asked))
    outs = run(go())
    assert [[p["pmid"] for p in o["papers"]] for o in outs] == asked and all(o["missing"] == [] for o in outs)
    assert len(ncbi.seen) == 10 + busy and sum(o["calls"][0]["tries"] for o in outs) == 10 + busy
    assert len(list(pubmed.CACHE_DIR.glob("*.json"))) == 20 and not list(pubmed.CACHE_DIR.glob("*.tmp"))


def test_concurrent_fetches_of_the_same_ids_through_one_client():
    ncbi = NCBI(lambda req, n: httpx.Response(503) if n % 3 == 0 else efetch_echo(req, n))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(ncbi.handler)) as c:
            return await asyncio.gather(*(pubmed.fetch(["39100001", "39100002"], client=c, fresh=True) for _ in range(10)))
    outs = run(go())
    assert all([p["pmid"] for p in o["papers"]] == ["39100001", "39100002"] for o in outs)
    assert json.loads((pubmed.CACHE_DIR / "39100001.json").read_text())["paper"]["pmid"] == "39100001"


def test_fetch_one_id_given_as_text_is_one_id(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.params.get("id"))
        return httpx.Response(200, content=b"<PubmedArticleSet></PubmedArticleSet>")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    r = asyncio.run(pubmed.fetch("38000001", client=client))
    assert seen == ["38000001"] and r["missing"] == ["38000001"]


def test_india_in_capitals_is_marked():
    xml = (b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>T</ArticleTitle>'
           b'<AuthorList><Author><LastName>Rao</LastName><Initials>N</Initials><AffiliationInfo><Affiliation>TATA MEMORIAL HOSPITAL, MUMBAI, INDIA'
           b'</Affiliation></AffiliationInfo></Author></AuthorList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>')
    assert pubmed.parse(xml)[0]["india"] is True
