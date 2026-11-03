# Ask PubMed: design (3 Nov 2026)

The prof's suggestion, through the owner: general questions are answered from PubMed only. Owner's answers (3 Nov 2026):
shown proudly in the screens, not hidden; the Case File agents keep their scope (records and guidelines); Ask PubMed is an add-on
with its own label; the papers come from the PubMed API, never from the model; it must work without backend errors.

## 1. Decisions

| # | Decision | Owner's answer |
|---|---|---|
| 1 | Scope | The agents answer only from the records and the guideline library, as now. Ask PubMed is a separate add-on, labelled "Published evidence, not advice for this patient". |
| 2 | Sources | General questions: PubMed only. Patient questions: the records, with guideline references beside them, as now. |
| 3 | Who picks PubMed | Vaidyx suggests it for a general question, the doctor confirms with one click. In the meeting the agent says "From PubMed" aloud. |
| 4 | Text read | Abstracts first; PubMed Central free full text later. |
| 5 | Without a Case File | Yes: an "Ask PubMed" page on Home. Same engine; inside a Case File it knows the cancer and the documented biomarkers, outside it knows nothing else. |

Wording (label under every PubMed answer):
"From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for this patient."
Wording (records answer, unchanged scope): "From this patient's records only."

## 2. Where it shows (proudly)

| Place | What the doctor sees |
|---|---|
| Case File, Ask | Two equal tabs at the top: **This patient's records** and **PubMed**. A general question typed in Records gets "This is a general question. Ask PubMed?" (one click). |
| Home | An **Ask PubMed** card and its own page (`/pubmed`), in the nav and the phone Dock. Each user's own history. |
| Meeting, AI agents | An **Ask PubMed** tab beside the agents. A voice answer starts "From PubMed:" and names the first author, journal and year. |
| Published panel | **Save** on any paper card puts it in the Case File's Published list (existing panel). |

While it works, the steps are shown live: "Searching PubMed... 305 papers found, reading the top 20 abstracts... writing... checking
every quote". The answer card: the search words (editable, run again), 2 to 5 lines each with a quote chip and a paper number, then
the paper cards (title, authors, journal, year, study type, peer reviewed, India mark, PMID link, Save), "N papers read, searched <time>".

## 3. How an answer is made

| Step | Rule |
|---|---|
| 1. Sort | About this patient: records (unchanged). General: PubMed. Advice for this patient ("should we give her..."): refused (unchanged). |
| 2. Search words | The model writes PubMed search words from the question (in a Case File it may add the cancer site and the documented histology, stage and biomarkers). Never sent: name, UHID, IP / OP No., ABHA, dates, age, place, hospital, long digit runs (the published.py filter, extended). The words are shown. |
| 3. Papers | Only from NCBI E-utilities: esearch (Best Match, humans, last 10 years by default, the doctor may widen), then efetch XML for the top 20. Retracted papers dropped. Order: meta-analysis and systematic review, trial, guideline, review, cohort, case report. India mark from the authors' affiliations. |
| 4. Answer | The model writes 2 to 5 short lines; each cites a PMID and an exact quote. A PMID not in the fetched set, or a quote not found word for word in that abstract, drops the line. |
| 5. Output check | No advice and no "this patient" in Vaidyx's own words (quotes are the papers' words and may say "recommended"). Conflicting papers are shown side by side, never resolved. |
| 6. Nothing | "No answer found in the PubMed abstracts read." PubMed down: "PubMed could not be reached (reason). Try again." Never the model's own memory. |

Paper details (title, authors, journal, year, type, DOI, PMCID) come from the API record, never from the model.

## 4. Backend

| Piece | What |
|---|---|
| `tumour_board/pubmed.py` | The client: esearch, efetch XML parsing (structured abstract sections, publication types, retraction, affiliations, MeSH), a rate limit (3 calls/s, 10 with an NCBI API key), retries with back-off on 429 / 5xx / time-outs, 15 s per call, `tool=vaidyx-tb` and a contact email (NCBI policy), a disk cache of public abstracts by PMID (30 days). published.py moves onto it. |
| `tumour_board/pubmed_ask.py` | The pipeline of section 3; its own guardrail policy (section 6, item 1). |
| Routes | `POST /cases/{id}/pubmed/ask` (saved in the team chat as a PubMed thread), `POST /pubmed/ask` and `GET /pubmed/history` (Home, per user), Save to Published (existing route), the meeting agents' tab uses the Case File route. |
| Audit | Every search: who, the words sent, papers found, seconds. |
| Models | Reasoner Gemma-4-31B (non-medical), labelled on every answer. |

## 5. Checks

| Check | How |
|---|---|
| Unit | Recorded PubMed XML: normal, structured abstract, no abstract, retracted, empty result, malformed XML, 429, 500, time-out, identifier in the question. |
| Live | 20 fixed general questions (breast, lung, cervix, head and neck) against real PubMed: every paper from the API, every quote verified, zero backend errors, time per answer. |
| Screens | Playwright: Case File tabs, Home page, meeting tab, Save; all roles; desktop and phone. |

## 6. Open points for the owner

1. Guardrail: today the rules refuse "survival" and "best treatment" questions. Ask PubMed would allow them when asked about published
   results ("What survival did trials report for ...?") and still refuse them about this patient ("What is her survival?").
2. NCBI API key and contact email: free key from an NCBI account (10 calls/s instead of 3); which email goes to NCBI.
3. The public website wording is the owner's (content.ts); the public demo only on the owner's word.
4. Branding: the word "PubMed" with a link and "U.S. National Library of Medicine", no NLM logo (NLM asks that its logo is not used to
   suggest endorsement).
