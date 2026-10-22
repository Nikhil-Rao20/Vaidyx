"""Published cases (18 Oct): the search over the local library (stubbed index), PubMed E-utilities and Europe PMC (httpx.MockTransport:
nothing leaves the machine), patient identifiers refused, failures reported, items added with pasted verbatim quotes and removed. The
label "Published case, not advice for this patient" is on every item."""
import json
import urllib.parse

import httpx
import pytest

from tumour_board import guidelines, published, store
from tumour_board.api import common
from tumour_board.api import published as published_api
from tumour_board.tests.test_nik_slots import CASE, OWNER, audit_kinds, nik_app, people, tb001  # noqa: F401 (fixtures)

ESEARCH = {"esearchresult": {"idlist": ["39000001", "39000002"], "count": "2"}}
ESUMMARY = {"result": {"uids": ["39000001", "39000002"],
                       "39000001": {"uid": "39000001", "title": "Osimertinib in resected EGFR-mutated NSCLC: a multicentre cohort.", "authors": [{"name": "Rao A"}, {"name": "Iyer L"}],
                                    "fulljournalname": "Indian Journal of Cancer", "source": "Indian J Cancer", "pubdate": "2024 Mar", "pubtype": ["Journal Article", "Multicenter Study"],
                                    "articleids": [{"idtype": "pubmed", "value": "39000001"}, {"idtype": "doi", "value": "10.4103/ijc.ijc_1_24"}]},
                       "39000002": {"uid": "39000002", "title": "A preprint on stage III NSCLC", "authors": [{"name": "Nair K"}], "fulljournalname": "", "source": "medRxiv",
                                    "pubdate": "2025", "pubtype": ["Preprint"], "articleids": [{"idtype": "doi", "value": "10.1101/2025.01.01.25"}]}}}
EPMC = {"resultList": {"result": [
    {"id": "39000001", "source": "MED", "pmid": "39000001", "doi": "10.4103/ijc.ijc_1_24", "title": "Osimertinib in resected EGFR-mutated NSCLC: a multicentre cohort.",
     "authorString": "Rao A, Iyer L.", "journalTitle": "Indian J Cancer", "pubYear": "2024", "pubType": "research-article; journal article"},
    {"id": "PPR900001", "source": "PPR", "doi": "10.21203/rs.3.rs-1", "title": "Concurrent chemoradiation in unresectable NSCLC: a single-centre audit (preprint)",
     "authorString": "Mehta S.", "journalTitle": "", "pubYear": "2025", "pubType": "preprint"},
    {"id": "PMC7000001", "source": "PMC", "pmcid": "PMC7000001", "doi": "10.1000/book.1", "title": "Lung cancer: a textbook chapter", "authorString": "Editors.", "journalTitle": "",
     "pubYear": "2023", "pubType": "book"}]}}


class Remote:
    """PubMed and Europe PMC behind an httpx.MockTransport: records every request, answers by host, or fails."""

    def __init__(self):
        self.seen, self.fail = [], {}

    def handler(self, request: httpx.Request):
        self.seen.append(request)
        host = request.url.host
        if host in self.fail:
            raise self.fail[host]("down", request=request)
        if host == "eutils.ncbi.nlm.nih.gov":
            if request.url.path.endswith("esearch.fcgi"):
                return httpx.Response(200, json=ESEARCH)
            return httpx.Response(200, json=ESUMMARY)
        if host == "www.ebi.ac.uk":
            return httpx.Response(200, json=EPMC)
        return httpx.Response(404)


class LocalIndex:
    chunks = [1]

    def search(self, q, k=8, cancer=None, sources=None):
        return [{"text": "Molecular testing: report EGFR, ALK and ROS1 status with the method used.", "file": "ncg_india/ncg_lung_2023.pdf", "title": "NCG lung guideline",
                 "org": "National Cancer Grid (NCG), India", "region": "India", "page": 12, "page_end": 12, "score": 0.9},
                {"text": "Smith J, Jones K. Lung cancer. J Clin Oncol. 2019;37(1):12-20. Brown T. Cancer. 2018;12:1-5.", "file": "esmo/esmo_lung.pdf", "title": "ESMO lung",
                 "org": "ESMO", "region": "International", "page": 40, "page_end": 40, "score": 0.5}]


@pytest.fixture
def remote(monkeypatch):
    fake = Remote()
    monkeypatch.setattr(published, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(guidelines, "ready", lambda: True)
    monkeypatch.setattr(guidelines, "index", lambda: LocalIndex())
    return fake


def test_search_local_first_then_pubmed_and_europe_pmc(nik_app, tb001, remote):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/published/search", json={"terms": " EGFR mutated  NSCLC adjuvant osimertinib "})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["error"] == "" and out["terms"] == "EGFR mutated NSCLC adjuvant osimertinib" and out["label"] == published.LABEL
    assert out["counts"] == {"local": 1, "pubmed": 2, "europepmc": 2}
    assert [x["source"] for x in out["results"]] == ["local", "pubmed", "pubmed", "europepmc", "europepmc"]
    loc = out["results"][0]
    assert loc["kind"] == "guideline" and loc["peer_reviewed"] is False and loc["title"] == "NCG lung guideline" and loc["where"] == "p. 12" and loc["region"] == "India"
    assert loc["url"] == "/api/tb/guidelines/file?path=ncg_india/ncg_lung_2023.pdf" and "EGFR" in loc["snippet"]  # the reference list page is dropped
    pm = out["results"][1]
    assert pm["peer_reviewed"] is True and pm["kind"] == "paper" and pm["authors"] == "Rao A, Iyer L" and pm["journal"] == "Indian Journal of Cancer" and pm["year"] == "2024"
    assert pm["doi"] == "10.4103/ijc.ijc_1_24" and pm["url"] == "https://pubmed.ncbi.nlm.nih.gov/39000001/" and pm["pmid"] == "39000001"
    pre = out["results"][2]
    assert pre["kind"] == "preprint" and pre["peer_reviewed"] is False
    ep = out["results"][3]  # the PubMed paper came back from Europe PMC too: listed once
    assert ep["kind"] == "preprint" and ep["peer_reviewed"] is False and ep["url"] == "https://europepmc.org/article/PPR/PPR900001"
    assert out["results"][4]["kind"] == "book" and out["results"][4]["peer_reviewed"] is False
    # what left the server: the words only, the tool name, no identifier
    urls = [str(q.url) for q in remote.seen]
    assert len(urls) == 3 and all("SYN-100231" not in u and "Ramesh" not in u for u in urls)
    es = urllib.parse.parse_qs(remote.seen[0].url.query.decode())
    assert es["term"] == ["EGFR mutated NSCLC adjuvant osimertinib"] and es["tool"] == ["vaidyx-tb"] and es["retmax"] == ["10"] and es["db"] == ["pubmed"]
    assert urllib.parse.parse_qs(remote.seen[1].url.query.decode())["id"] == ["39000001,39000002"]
    assert urllib.parse.parse_qs(remote.seen[2].url.query.decode())["query"] == ["EGFR mutated NSCLC adjuvant osimertinib"]
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "published_search"]
    assert ev[-1]["terms"] == "EGFR mutated NSCLC adjuvant osimertinib" and ev[-1]["by"] == "dr.rao" and ev[-1]["counts"]["pubmed"] == 2
    v = tc.get(f"/api/tb/cases/{CASE}/published").json()
    assert v["items"] == [] and v["searches"][-1]["terms"] == "EGFR mutated NSCLC adjuvant osimertinib" and v["label"] == published.LABEL


@pytest.mark.parametrize("terms", ["EGFR NSCLC SYN-100231", "Ramesh Kumar lung cancer", "lung cancer 1234567", "", "x", "12 34"])
def test_search_refuses_identifiers_and_empty_words(nik_app, tb001, remote, terms):
    tc, who = nik_app
    r = tc.post(f"/api/tb/cases/{CASE}/published/search", json={"terms": terms})
    assert r.status_code == 400, r.text
    assert not remote.seen and not [e for e in store.read_audit(CASE) if e.get("kind") == "published_search"]


def test_search_failures_are_reported_not_raised(nik_app, tb001, remote, monkeypatch):
    tc, who = nik_app
    remote.fail = {"eutils.ncbi.nlm.nih.gov": httpx.ConnectError, "www.ebi.ac.uk": httpx.ReadTimeout}
    monkeypatch.setattr(guidelines, "ready", lambda: False)  # the library is not loaded: no local results, never a wait for the build
    r = tc.post(f"/api/tb/cases/{CASE}/published/search", json={"terms": "stage III NSCLC chemoradiation"})
    assert r.status_code == 200
    out = r.json()
    assert out["results"] == [] and out["error"] == "PubMed: ConnectError; Europe PMC: ReadTimeout" and out["counts"] == {"local": 0, "pubmed": 0, "europepmc": 0}
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "published_search"]
    assert ev[-1]["errors"] == ["PubMed: ConnectError", "Europe PMC: ReadTimeout"]
    monkeypatch.setattr(published_api, "SEARCH_LIMIT", common.RateLimit(1, 600))
    assert tc.post(f"/api/tb/cases/{CASE}/published/search", json={"terms": "stage III NSCLC"}).status_code == 200
    assert tc.post(f"/api/tb/cases/{CASE}/published/search", json={"terms": "stage III NSCLC"}).status_code == 429


def test_add_quotes_and_delete(nik_app, tb001):
    tc, who = nik_app
    result = {"title": "Osimertinib in resected EGFR-mutated NSCLC: a multicentre cohort.", "authors": "Rao A, Iyer L", "journal": "Indian Journal of Cancer", "year": "2024",
              "doi": "10.4103/ijc.ijc_1_24", "url": "https://pubmed.ncbi.nlm.nih.gov/39000001/", "source": "pubmed", "peer_reviewed": True, "kind": "paper", "pmid": "39000001"}
    quotes = [{"text": "Patients received osimertinib 80 mg daily for three years after complete resection.", "where": "Methods, p. 3"},
              {"text": "Disease-free survival at 24 months was 89% (95% CI 84 to 93).", "where": "Results, Table 2", "label": "conclusion"}]
    r = tc.post(f"/api/tb/cases/{CASE}/published", json={"result": result, "quotes": quotes})
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["id"].startswith("P") and item["label"] == "Published case, not advice for this patient" and item["added_by"] == "dr.rao" and item["by_name"] == "Dr Rao"
    assert item["peer_reviewed"] is True and item["kind"] == "paper" and item["year"] == "2024" and item["doi"] == "10.4103/ijc.ijc_1_24"
    assert item["quotes"][0] == {"text": quotes[0]["text"], "where": "Methods, p. 3", "label": ""} and item["quotes"][1]["label"] == "conclusion"
    assert "similarity" not in json.dumps(item)
    v = tc.get(f"/api/tb/cases/{CASE}/published").json()
    assert [x["id"] for x in v["items"]] == [item["id"]]
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": result}).status_code == 409  # the same DOI twice
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": {**result, "doi": "", "url": "javascript:alert(1)"}}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": {**result, "doi": "", "url": "", "year": "soon"}}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": {"title": ""}}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": {**result, "doi": "", "url": "", "kind": "opinion"}}).status_code == 400
    # more quotes later, a flat body (no "result" wrapper) and a manual entry
    r = tc.post(f"/api/tb/cases/{CASE}/published/{item['id']}/quotes", json={"quotes": [{"text": "Grade 3 adverse events occurred in 12% of patients.", "where": "Results"}]})
    assert r.status_code == 200 and len(r.json()["quotes"]) == 3
    assert tc.post(f"/api/tb/cases/{CASE}/published/Pnope/quotes", json={"quotes": [{"text": "x"}]}).status_code == 404
    flat = tc.post(f"/api/tb/cases/{CASE}/published", json={"title": "A case report from the department library", "authors": "Dept", "source": "manual", "kind": "paper",
                                                            "url": "https://example.org/case.pdf", "quotes": ["Verbatim line pasted by the doctor."]})
    assert flat.status_code == 200 and flat.json()["source"] == "manual" and flat.json()["peer_reviewed"] is False and flat.json()["quotes"][0]["text"] == "Verbatim line pasted by the doctor."
    ev = [e for e in store.read_audit(CASE) if e.get("kind") in ("published_added", "published_quotes_added")]
    assert [e["kind"] for e in ev] == ["published_added", "published_quotes_added", "published_added"] and ev[0]["quotes"] == 2
    # only the owner's doctors add or remove; a participating treating doctor reads
    c = store.get_case(CASE); c["participants"] = [{"department": "breast_surgery", "since": store.now_iso(), "by": "dr.rao"}]; store.save_case(c)
    who["user"] = "dr.nair"
    assert tc.get(f"/api/tb/cases/{CASE}/published").status_code == 200
    assert tc.post(f"/api/tb/cases/{CASE}/published", json={"result": {"title": "Another", "source": "manual"}}).status_code == 403
    assert tc.delete(f"/api/tb/cases/{CASE}/published/{item['id']}").status_code == 403
    who["user"] = "dr.rao"
    r = tc.delete(f"/api/tb/cases/{CASE}/published/{item['id']}")
    assert r.status_code == 200 and r.json()["removed"]["id"] == item["id"]
    assert [x["id"] for x in tc.get(f"/api/tb/cases/{CASE}/published").json()["items"]] == [flat.json()["id"]]
    assert tc.delete(f"/api/tb/cases/{CASE}/published/{item['id']}").status_code == 404
    assert "published_removed" in audit_kinds(CASE) and store.verify_audit(CASE)["ok"]


def test_check_terms_rules():
    case = {"patient": {"name": "SYNTHETIC, Ramesh Kumar", "mrn": "SYN-100231", "ids": [{"kind": "ip_no", "value": "IP/2026/0042"}]}, "his": {"uhid": "VXH/2026/000123"}}
    assert published.check_terms(case, "  EGFR  NSCLC ") == "EGFR NSCLC"
    for bad in ("NSCLC SYN-100231", "kumar lung", "ip/2026/0042 lung", "VXH/2026/000123", "lung 2026000123", "SYNTHETIC lung", "lung 000123"):
        with pytest.raises(published.PublishedError):
            published.check_terms(case, bad)
    # a year is not an identifier, even the year inside the patient's IP No.; two numbers are not one long number
    assert published.check_terms(case, "stage IIIB NSCLC 2026 chemoradiation") == "stage IIIB NSCLC 2026 chemoradiation"
    assert published.check_terms(case, "NSCLC 2024 2025 trials") == "NSCLC 2024 2025 trials"
