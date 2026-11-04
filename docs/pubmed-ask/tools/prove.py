"""Ask PubMed, Part 1 proof (owner, 3 Nov 2026: "show me that you can fetch the topic in PubMed and confirm it is from PubMed only").
Each question is asked with fresh PubMed records (no cache), then every answer is checked against PubMed through two routes that do not
use the records Vaidyx fetched:
  A. NCBI esummary (another E-utility): every paper's title and year as PubMed lists them;
  B. the paper's own page on the PubMed website (pubmed.ncbi.nlm.nih.gov/<pmid>/?format=pubmed): every quote is found word for word in
     the title or abstract printed there.
It also checks that every cited PMID is one PubMed's search returned, and counts the PMIDs the model cited that were not given (dropped).
Writes docs/pubmed-ask/PROOF.md and docs/pubmed-ask/proof/q<n>.json. Synthetic questions only, no patient data.
Run: /data/vaidyx/venv/app/bin/python docs/pubmed-ask/tools/prove.py"""
import asyncio
import html
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import httpx  # noqa: E402

from tumour_board import grounding, pubmed, pubmed_ask  # noqa: E402

OUT = REPO / "docs" / "pubmed-ask"
QUESTIONS = [
    ("Breast", "What pathological complete response rates did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?"),
    ("Lung", "What disease-free survival did trials report with adjuvant osimertinib in resected EGFR-mutated non-small cell lung cancer?"),
    ("Cervix", "What did trials report about induction chemotherapy before chemoradiation in locally advanced cervical cancer?"),
    ("Head and neck", "What did trials from India report about low-dose metronomic chemotherapy in head and neck cancer?"),
]


def _t(s):
    """A title compared by its letters and digits only: esummary writes a superscript as "ER(+)", the record as "ER+"."""
    return re.sub(r"[^a-z0-9]", "", grounding.norm(re.sub(r"<[^>]+>", "", html.unescape(s or ""))))


def _nb(s):
    return re.sub(r"[()\[\]]", " ", s or "")


async def esummary(client, ids):
    body, _ = await pubmed._call(client, "esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    res = json.loads(body).get("result") or {}
    return {i: res.get(i) or {} for i in ids}


def medline_fields(page):
    m = re.search(r'<pre class="article-details" id="article-details">(.*?)</pre>', page, re.S)
    text = html.unescape(m.group(1)) if m else ""
    fields, key = {}, None
    for line in text.splitlines():
        if re.match(r"^[A-Z]{2,4}\s*- ", line):
            key, val = line[:4].strip(), line[6:]
            fields.setdefault(key, []).append(val)
        elif key and line.startswith("      "):
            fields[key][-1] += " " + line.strip()
    return fields


async def website(client, pmid):
    """The paper's MEDLINE text from its PubMed web page; four tries, since the website may send a holding page to quick callers.
    {"loaded": False} when no try gave the record."""
    for wait in (1.0, 5.0, 15.0, 30.0):
        await asyncio.sleep(wait)  # gentle on the public website
        try:
            r = await client.get(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", params={"format": "pubmed"})
        except httpx.HTTPError:
            continue
        f = medline_fields(r.text) if r.status_code == 200 else {}
        if " ".join(f.get("PMID", [])).strip() == pmid:
            return {"loaded": True, "pmid": pmid, "title": " ".join(f.get("TI", [])), "abstract": " ".join(f.get("AB", []))}
    return {"loaded": False, "pmid": pmid, "title": "", "abstract": ""}


def search_link(term, years):
    q = {"term": term, "sort": "relevance"}
    if years:
        y = datetime.now().year
        q["filter"] = f"years.{y - years + 1}-{y}"
    return "https://pubmed.ncbi.nlm.nih.gov/?" + urllib.parse.urlencode(q)


async def prove_one(n, area, question, client):
    r = await pubmed_ask.ask(question, fresh=True)
    (OUT / "proof").mkdir(parents=True, exist_ok=True)
    (OUT / "proof" / f"q{n}.json").write_text(json.dumps(r, indent=1))
    checks = {"status": r["status"]}
    search_ids = set()
    if r["status"] in ("answered", "not_found"):
        # PubMed's whole result list for the same words (Best Match order may move a little between calls; membership is the claim)
        s = await pubmed.search(r["search"]["used"], retmax=pubmed.MAX_IDS, years=r["search"].get("years"), client=client)
        search_ids = set(s["ids"])
    cited = sorted({c["pmid"] for st in r["statements"] for c in st["citations"]})
    checks["cited_in_search"] = (sum(p in search_ids for p in cited), len(cited))
    ids = [p["pmid"] for p in r["papers"]]
    summ = await esummary(client, ids) if ids else {}
    ok = 0
    mism = []
    for p in r["papers"]:
        e = summ.get(p["pmid"]) or {}
        same = _t(e.get("title")) == _t(p["title"]) and str(e.get("pubdate") or "")[:4] in (p["year"], "")
        ok += same
        if not same:
            mism.append(f"{p['pmid']}: esummary '{str(e.get('title'))[:60]}' {str(e.get('pubdate'))[:4]} vs '{p['title'][:60]}' {p['year']}")
    checks["esummary_match"] = (ok, len(r["papers"]), mism)
    pages, q_ok, q_all, q_bad = {}, 0, 0, []
    for st in r["statements"]:
        for c in st["citations"]:
            if c["pmid"] not in pages:
                pages[c["pmid"]] = await website(client, c["pmid"])
            w = pages[c["pmid"]]
            parts = [x for x in c["quote"].split(" ... ") if x.strip()]
            # the website prints a sub- or superscript in brackets ("HR (EGFR-TKI/C+IO)"), the XML without ("HR EGFR-TKI/C+IO"): brackets
            # are left out on both sides, every word and number must still match in order
            found = w["loaded"] and all((grounding.locate(_nb(x), [_nb(w["title"]), _nb(w["abstract"])]) or {}).get("score") == 100 for x in parts)
            q_all += 1
            q_ok += found
            if not found:
                q_bad.append(f"PMID {c['pmid']}: " + ("the PubMed page did not load after 4 tries" if not w["loaded"] else f"not on the page: {c['quote'][:80]}"))
    checks["quotes_on_website"] = (q_ok, q_all, q_bad)
    checks["invented_pmids"] = r["invented_pmids"]
    return area, r, checks


def table_row(cells):
    return "| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |"


def report(results):
    lines = ["# Ask PubMed: proof that the papers come from PubMed only (Part 1, backend only)", "",
             f"Run {datetime.now().strftime('%d %b %Y %H:%M')} on the server, fresh PubMed records (no cache), the reasoner "
             f"{pubmed_ask.model_line()}. Not wired into the app yet.", "",
             "How each answer is checked, without the records Vaidyx fetched:", "",
             "| Check | How |", "|---|---|",
             "| Cited papers came from PubMed's search | the same search is run again and every cited PMID must be in PubMed's list |",
             "| Paper details are PubMed's | every paper's title and year compared with NCBI esummary (a second NCBI service) |",
             "| Quotes are PubMed's text | every quote found word for word on the paper's own PubMed web page |",
             "| The model invented nothing | PMIDs the model cited that were not given are counted (and dropped) |", "",
             "## Summary", "", "| Area | Status | PubMed found | Read | Lines kept | Lines dropped | Cited in search | Details match esummary | Quotes on PubMed page | Invented PMIDs | Seconds |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for area, r, c in results:
        lines.append(table_row([area, r["status"], r["counts"]["found"], r["counts"]["read"], len(r["statements"]), len(r["removed"]),
                                "%d / %d" % c["cited_in_search"], "%d / %d" % c["esummary_match"][:2], "%d / %d" % c["quotes_on_website"][:2],
                                c["invented_pmids"], r.get("seconds")]))
    for n, (area, r, c) in enumerate(results, 1):
        s = r["search"]
        lines += ["", f"## {n}. {area}", "", f"**Question:** {r['question']}", "",
                  f"**Search words** (written by the {'model' if s.get('by') == 'model' else 'question'}): `{s.get('used')}`, "
                  f"{'last ' + str(s.get('years')) + ' years' if s.get('years') else 'all years'}. PubMed found **{r['counts']['found']}** papers. "
                  f"[Open the same search on PubMed]({search_link(s.get('used') or '', s.get('years'))})", ""]
        if r["statements"]:
            lines += ["**Answer** (each line with the exact words from the paper):", ""]
            for i, st in enumerate(r["statements"], 1):
                lines.append(f"{i}. {st['text']}")
                for q in st["citations"]:
                    lines.append(f"   - [PMID {q['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{q['pmid']}/), {q['where']}: \"{q['quote']}\"")
            lines.append("")
        else:
            lines += [f"**Answer:** {r['message']}", ""]
        if r["removed"]:
            lines += ["Dropped by the checks: " + "; ".join(f"\"{x['text'][:90]}\" ({x['reason']})" for x in r["removed"]), ""]
        lines += [f"**Papers** ({r['counts']['fetched']} fetched from PubMed, {r['counts']['read']} read by the model):", "",
                  "| # | PMID | Year | Study type (PubMed) | Journal | Title | Read |", "|---|---|---|---|---|---|---|"]
        for p in r["papers"]:
            lines.append(table_row([p["rank"], f"[{p['pmid']}]({p['url']})", p["year"], p["study_type"], p["journal_abbr"] or p["journal"],
                                    p["title"][:110] + (" (India)" if p["india"] else ""),
                                    "cited" if p.get("cited") else "read" if p["read"] else f"not read: {p['why_not_read']}"]))
        lines += ["", "| Check | Result |", "|---|---|",
                  table_row(["Cited papers in PubMed's search", "%d of %d" % c["cited_in_search"]]),
                  table_row(["Titles and years match NCBI esummary", "%d of %d" % c["esummary_match"][:2] + ("; " + "; ".join(c["esummary_match"][2]) if c["esummary_match"][2] else "")]),
                  table_row(["Quotes found on the PubMed web page", "%d of %d" % c["quotes_on_website"][:2] + ("; " + "; ".join(c["quotes_on_website"][2]) if c["quotes_on_website"][2] else "")]),
                  table_row(["PMIDs the model cited that were not given", c["invented_pmids"]]),
                  table_row(["Raw PubMed answers (SHA-256)", ", ".join(f"{x['what']} {x['sha256'][:16]}" for x in r["calls"])])]
    lines += ["", f"_{pubmed_ask.LABEL_HOME}_", ""]
    (OUT / "PROOF.md").write_text("\n".join(lines))


async def main():
    results = []
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "vaidyx-tb/1.0"}, follow_redirects=True) as client:
        for n, (area, q) in enumerate(QUESTIONS, 1):
            res = await prove_one(n, area, q, client)
            results.append(res)
            a, r, c = res
            print(f"{a}: {r['status']} found {r['counts']['found']} read {r['counts']['read']} kept {len(r['statements'])} dropped {len(r['removed'])} "
                  f"cited-in-search {c['cited_in_search']} esummary {c['esummary_match'][:2]} website {c['quotes_on_website'][:2]} invented {c['invented_pmids']} {r.get('seconds')} s",
                  flush=True)
    report(results)
    print("wrote", OUT / "PROOF.md")


if __name__ == "__main__":
    asyncio.run(main())
