# The Case summary that grows with the patient (research for Phase 3)

Research for plan item 0.4, feeding items 3.3, 3.4 and 3.5 (decision D3). Written 27/10/2026. Read-only on the code; nothing was run.
Line numbers are from the working tree on branch night-v3 on that day. Web sources: what the search result or the fetched page said is stated; where a page could not be read (PMC blocked, a 429, a scanned form) that is said too, and nothing is claimed beyond it.

## 1. Summary

1. Today there is one summary per Case File, `artefacts.summary`, built once by one Gemma-4-31B (non-medical) call in the six NCG sections, quote-checked sentence by sentence, and **overwritten** on every rebuild with the review reset to "ai_draft" (`tumour_board/summary.py:183`, `:179`). Nothing is built after a board decision.
2. The summary only knows documents. It cites `doc_id` plus a quote; there is no way today to cite a board-record field, an action closure, a confirmed stage or a member's card.
3. The proposal: a new module `tumour_board/case_summary.py` and a new artefact `artefacts.case_summary` holding a list of versions. The pre-board summary is kept as `artefacts.summary_history` (item 3.5) and as the "Before the board on DD/MM/YYYY" block (item 3.4).
4. Five sections exactly as the plan lists: presentation and diagnosis; stage; each board round; treatment and follow-up since; current status and open actions.
5. Two kinds of citation: a record line (document id, quote, page, checked word for word by `qa.verify`, as now) and a board-record field (record id, field key, record version, exact text, checked by a new small verifier). Anything else is dropped.
6. The board-round and open-actions sections need no model: code writes them from the record and quotes the field text itself, so no value can be paraphrased. The model is used only for the two narrative sections (presentation and diagnosis; treatment and follow-up since), and every model sentence is checked.
7. Edits by the owner's consultant are stored beside the model text, never over it: "edited by Dr X on DD/MM/YYYY", with the model's sentence and the earlier text kept. A rebuild makes a new version; edited sentences are carried forward and shown as edited, never silently replaced.
8. The summary line (`case.summary_line`) is one short sentence taken from the Case summary, editable, carried in the list item and added to both search haystacks (server `cases_list._match`, web `search.ts haystack`), plus the cancer and the latest decision text.
9. Built in the background after each `postboard.record_decision` (the same pattern as `ready_hook`), and on demand. One call per narrative section (two calls) in parallel, about 15 to 30 s with the 32k-token reasoner; context well under the limit.
10. Open questions (section 8): who may edit and sign off, whether an edit blocks a rebuild of that sentence, whether the member cards and concerns appear by name, who sees the summary line in the list.

## 2. What exists today

### 2.1 The pre-board summary pipeline (`tumour_board/summary.py`, 185 lines)

1. Entry `build(case_id, force=False)` (`summary.py:106`). Takes the Case File signature first (`rules.case_signature`, `:111`) so a change during the model call marks the result stale (V1 item 4.5; `rules.py:663-679`: hash of documents with state, processed time and protocol, the active confirmation ids, protocol and version, setting, hospital level).
2. Gate: an unlisted Case File returns `not_listed` with no model call (`:113-114`); an unmet Pre-Authorization gate returns `gate_not_met` unless `force` (`:115-117`). The ready mark forces it (`ready_hook.py:98`).
3. Context: `search.context_for(case_id, "clinical history ... treatment", 60000)` (`:118`), 60 000 characters, no board record, no action.
4. Facts: `rules.resolve_facts(...)` with the clinician confirmations overlaid (`:119`), and the stage as recorded: the newest verified of `recorded_stage` and `figo_stage`, copied, never derived (`:121-122`).
5. Prompt: `SYS` (`:100-103`: registrar style, attribute to the source report, copy values exactly, no diagnosis, no derived stage, no treatment advice) plus the six NCG sections (`SECTIONS`, `:61-63`, which follow the NCG VTB case template) and the instruction "Findings in date order within a section. Prefer FINAL signed reports" (`:125-128`).
6. One call: `llm.chat("reasoner", msgs, json_schema=SCHEMA, max_tokens=3500, purpose="case file summary")` (`:129`). The schema asks for 10 to 18 sentences, each `{section, text, citations[{doc_id, quote}]}`, and `points_for_review` (`:64-72`).
7. Quote check: `qa.verify` (`qa.py:150-206`) finds each quote in the cited document's page text (`_locate_quote`), writes back page and character offsets, the document title, event date and status, adds "from scan (OCR)" for scanned pages, and flags `negated_before`. A number guard drops a sentence whose numbers are not in a verified quote (`qa.py:177-185`). With `config.near_match()` an approximate quote is kept and flagged `approximate` (`qa.py:186-190`). Each drop is kept with a reason in `removed` (`summary.py:136-148`). The output guardrail `guardrails.scan_output` removes advice-like sentences (`:142-147`).
8. Gap fill: `fill_from_facts` (`:30-58`) adds a plain cited sentence for a verified fact the model's sentences do not carry (`SECTION_FACTS`, `:9-18`). A clinician-confirmed value has no quote and names who confirmed it (`:47-51`).
9. Points for review: the model's, plus code findings from `discord.points` and `his_case.points` (`:157-166`); the OP / IP encounter list (`:167`, `encounter_lines` `:74-95`).
10. Stored: `st["artefacts"]["summary"] = out` (`:183`) with `sections[{id,title,sentences[{text,citations[...],from_fields?,approximate?}]}]`, `paragraphs`, `points_for_review`, `stage_as_recorded`, `removed`, `generated`, `seconds`, `model`, `review {"status":"ai_draft"}`, `signature`, `context` (`:172-180`). Audit event `summary` (`:184`). The doc says 24 to 34 s and 47/48 key fields covered (`docs_Eswar/01_how_vaidyx_tb_works.md` lines 359-383).

### 2.2 The review

`service.review` (`service.py:497-506`) replaces `a["review"]` with `{status, comment, by, at}` and appends to `st["reviews"]` (an append-only log of every review of every artefact; this is the only history of reviews). The route is `POST /cases/{id}/review` (`routes/tumour_board_routes.py:1730`, `_need(_roles, "review")`). A rebuild writes a fresh `review: ai_draft`, so the "Reviewed" label is lost on rebuild, though the log in `st["reviews"]` keeps the earlier entries without a link to the version they judged.

### 2.3 What is lost on rebuild

The whole earlier summary object (its sentences, the `removed` list, the signature, the generated time, the review) is replaced (`summary.py:183`). Only the audit event and the `st["reviews"]` log remain. There is no edit feature: a clinician cannot change a sentence today; the only human acts are "mark reviewed" and the per-value confirmations (below).

### 2.4 How confirmations survive re-process

`confirm.py` header (lines 1-14): confirmations live in `state.json`, never in `doc.json`; re-processing rewrites only `doc.json`; confirmations are overlaid at read time so they win; one active record per type and key; undo marks, never deletes. Types include `confirm_value`, `attest_final`, `waive`, `resolve_flag` (`confirm.py:20-29`). The summary reads them through `resolve_facts` and signs them into the signature (`rules.py:671`). The same pattern (a separate store, overlaid at read time) is what a summary edit should copy.

### 2.5 Readers of the summary

| Reader | Where | What it does |
|---|---|---|
| Summary step and Overview prose | `slots._prose` (`slots.py:547-565`) feeds `steps` view (`steps.py:446-477`, `:512-526`); `SummaryStep.tsx` (83 lines) shows `prose.paragraphs` through `ProseBlock` (`SummaryColumn.tsx:31`), the stale banner with "Write it again", the "Read by" mark, "Send to the board" | Reads the single artefact; label "AI draft, not reviewed" or "Reviewed". `Overview.tsx` has no direct mention of prose or summary (grep found none); it shows the steps view only |
| Citation mark | `Cites` (`SummaryColumn.tsx:16-29`) | Up to three buttons per sentence, class `quote-chip`, text "document title p. N" (page + 1), click opens the source at the quote (`h.openSource({docId, page, quote, title})`) |
| Meeting slides, deck | `meetings.slides` (`meetings.py:1380-1392`); `deck/__init__.py:334-359` `_summary_items` | Slide "Summary" from the sections; "AI draft, not reviewed" label; stale text |
| NCG VTB export | `vtb_export._summary` (`vtb_export.py:185-194`), refuses without a summary (409) | Fills the 6 slides of NCG's own template from the six sections |
| FHIR | `fhir_export.py:197-203` | Composition sections from the stored summary |
| Minutes | `board.minutes` (`board.py:1026-1093`) | Does NOT read the summary: code only, decision as dictated, actions, follow-up |
| Others | `board.py:176`, `dept_requests.py:388`, `metrics.py:73`, `mcp_server.py:209`, `ready_hook.summary_fresh` (`ready_hook.py:44-47`), `steps.py:469-477`, `routes:962,1855` | Status words and staleness (none, stale, ready) |

### 2.6 What search covers today

`cases_list._match` (`api/cases_list.py:198-213`) builds a haystack from name, age/sex, ids, `protocol_label`, `cancer_name`, setting, owner doctor and department, status label and board date. `search.ts haystack` (`web/tb-nik/src/lib/search.ts:19-29`) is the same list; the Ctrl+K bar uses the same `matches`. No clinical text, no summary line, no decision text.

### 2.7 The inputs Phase 3 will have

- Board records: `state.json board_records[]` (`postboard.record_decision`, `postboard.py:406-432`): `id`, `recorded_at`, `entered_by`, `decision_text`, `outcome_type`, `rationale`, intent fields (`INTENTS`, `:314`), `concerns`, `divergent`, `actions[{task, department, due}]`, `next_review`, `versions[]` (version 1 holds only `decision_text`, `:463-478`), `adjudication` flags, `resolution`. Phase 3 item 3.1 adds the fields of `research/02` section 5 (36 form fields; a full snapshot per version is rule 7 in its section 6).
- Actions: `state["actions"]` created by `followup.board_actions` (`followup.py:99-129`: `id`, `board_record`, `label`, `department`, `status`, `created`, `due`, `history[]`); closure fields `status="completed"`, `completed`, `closed_by`, `closed_doc_id`, a history line (`followup.py:296-322`); the patient-informed action closes through `update_communication` (`postboard.py:373-403`).
- Timeline: `postboard.timeline` (`:671-701`) already merges documents by event date, encounters, referrals, board records and actions; a Case summary can reuse its order.
- Confirmed stage: `staging.confirm` (`staging/__init__.py:417-428`) stores `d["confirmed"] = {by, by_name, at, note}` on `st["staging"]`; draft stage is never used unless confirmed (CLAUDE.md invariant). The stage as recorded in a report is `stage_as_recorded` of the summary.
- Members' cards: `meetings` storage `cards {case_id: {user: {agree, note, at}}}` (`meetings.py:18`), holders `card_holders` (`:250`).

### 2.8 Gaps against D3

| D3 says | Today |
|---|---|
| After the first decision it replaces the pre-board summary as the main summary, updated after every later decision | Nothing runs after a decision; one object |
| Every sentence cites a record line or a board-record field | Only record lines; `qa.verify` only knows documents |
| The owner's consultant reviews and edits; an edit shows "edited by Dr X" | Review mark only; no edit |
| Every version kept; pre-board summaries stay in the history | Overwritten; review reset |
| Searchable like the UHID, name and age | No text, no line |
| Reads: the plan lists the inputs: pre-board summaries, every board record, actions and closures, confirmed stage, cards | Only documents and facts |

## 3. Sources

**1. Longitudinal record summarisation**

- **HARVEST**, Hirsch JS, Tanenbaum JS, Gorman SL, Liu C, Schmitz E, Hashorva D, Ervits A, Vawdrey D, Sturm M, Elhadad N. "HARVEST, a longitudinal patient record summarizer". JAMIA 2015;22(2):263-274, DOI 10.1136/amiajnl-2014-002945 (web search result; PMC full text https://pmc.ncbi.nlm.nih.gov/articles/PMC4394965 was blocked by a browser check, so only the abstract-level facts below). A problem-based, interactive, temporal visualisation of the longitudinal record, using distributed NLP and a problem salience score over notes, combining inpatient, outpatient and emergency settings, deployed in the hospital's review system for all patients; usability evaluated as a timed task-based chart review with a questionnaire against the standard record viewer (project page https://people.dbmi.columbia.edu/noemie/harvest says "interactive, problem-oriented patient record summarization system"). Contribution for us: the unit is the *problem*, not the note, and the summary is a view onto the record with the notes behind it; the evaluation is by clinician task time, not by text overlap. I could not check how it links back to the notes, so I do not claim it.
- **Hegselmann S, Shen SZ, Gierse F, Agrawal M, Sontag D, Jiang X.** "A Data-Centric Approach to Generate Faithful and High Quality Patient Summaries with Large Language Models", arXiv 2402.15422 (2024), https://arxiv.org/html/2402.15422v2 (read to character 100 000 of 141 043). Doctors annotated hallucinations in 100 doctor-written and 100 generated summaries; the protocol separates unsupported, contradicted and incorrect facts, with nine sub-types of unsupported (condition, procedure, medication, time, location, number, name, word, other); the brief hospital course was the only ground truth. Removing hallucinations from the fine-tuning data cut them (Llama 2 from 2.60 to 1.55 per summary; GPT-4 few-shot 0.70 to 0.40). "Common quantitative metrics do not correlate well with faithfulness and quality". Contribution: the error types to test for (time and number errors matter in a record that grows), and the point that overlap scores are not a test, so our test is the per-sentence check plus expert reading. Not oncology-specific.
- **Tempus**, "Patient Records to Timelines: A LLM-Based Approach for Summarizing Oncology Patient History" (ASCO 2025 abstract, https://www.tempus.com/publications/patient-records-to-timelines-a-llm-based-approach-for-summarizing-oncology-patient-history/; the page returned 429 so I rely on the search snippet): builds JSON timelines from pan-cancer records with a long-context model and checks extracted facts (diagnosis, stage, treatments) against curated data with a second model as judge. Contribution: a structured, dated timeline is the intermediate, not free prose. Our version of "the judge" is plain code (the quote check), which fits the project rule.
- A 2026 arXiv paper on AI summaries for cancer patients (listed as arXiv 2608.26154 by the search tool; the identifier looks odd, so verify before citing) reports three error types: temporal confusion, invented specific values, misread task status. I did not open it. It supports testing "dates" and "action status" explicitly.

**2. Discharge summary as a grounded, dated record**

- **PRSB eDischarge / Transfer of Care, Acute Inpatient Discharge standard** (v2.1 December 2019; owned by NHS England from 1 January 2026; https://theprsb.org/standards/edischargesummary/). The fetched page lists 22 sections: patient demographics; GP practice; referrer details; social context; individual requirements; participation in research; admission details; discharge details; diagnoses; procedures; clinical summary; investigation results; assessments; legal information; safety alerts; medications and medical devices; allergies and adverse reactions; patient and carer concerns, expectations and wishes; information and advice given; plan and requested actions; person completing record; distribution list. Contribution: "plan and requested actions" and "person completing record" as headings; each section is coded data, the narrative is only the "clinical summary".
- **NABH** (hospital accreditation, discharge chapter): a secondary slide deck found by search says a discharge summary is given to every patient leaving, including against medical advice, with a 180-minute target, and labels the content standard AAC.14 (https://www.slideshare.net/slideshow/discharge-referral-and-death-summary/249950795, not the standard itself). A sample NABH-linked hospital policy says the summary is prepared and signed or countersigned by the clinician in charge (https://testing.nabh.co/wp-content/uploads/2025/07/C.-E-Mitra_POLICY-01_Policy-on-Information-Management-System.pdf). I could NOT read the NABH element list: the IIHMR Delhi 2024 report on discharge summary compliance (https://drs.iihmrdelhi.edu.in/items/14f9a6be-47d8-4b17-b67d-fee16100356e/full) is only a PDF link on that page. Treat the NABH heading list as unverified; a clinician should read the NABH manual. What is safe: signed or countersigned by the clinician in charge.
- **NMC Code of Medical Ethics Regulations 2002** (https://www.nmc.org.in/rules-regulations/code-of-medical-ethics-regulations-2002/, "amended upto 8th October 2016"): 1.3.1 records of indoor patients kept for 3 years from the start of treatment, in a standard proforma (Appendix 3); 1.3.2 a request for records is acknowledged and the documents issued within 72 hours. Contribution: a record must be producible on request, so an exported Case summary needs a fixed print form with versions and signer. Clinical Establishments Act records rules: I found no readable source; not claimed.

**3. Oncology longitudinal documents**

- **ASCO treatment summary and survivorship care plan** (ASCO 2014 statement, templates updated 2015 for breast, colorectal, small cell and non-small cell lung, diffuse large B-cell lymphoma, prostate; https://ascopost.com/issues/june-25-2015/asco-releases-updated-expanded-set-of-survivorship-care-planning-templates/ and https://www.healio.com/hematology-oncology/practice-management/news/online/%7Bc173f09e-1ac3-4549-935f-29dc023f8d0c%7D/asco-updates-survivorship-care-planning-template; only the search summaries were read, not the template PDFs). Treatment summary: diagnostic and staging information, provider and cancer centre contacts, prior surgery, radiation and systemic therapy, persisting adverse effects. Follow-up care plan: adjuvant treatment, schedule of visits, where and when surveillance happens, late effects. Contribution: our sections 4 (presentation and diagnosis, stage) and 6 (treatment since) match this treatment-summary content; the "next review" fits the follow-up plan. ASCO requires its identifiers removed if a template is altered, so we use the section list as a pattern only, not the template.
- **NCG Virtual Tumour Board case template** (`/data/vaidyx/tb_resources/guidelines/ncg_india/ncg-vtb-case-template.pptx`, `ppt/slides/slide1.xml` to `slide6.xml`, read with zipfile): slide 1 name of the presenter, name of the centre, diagnosis, date of presentation; slide 2 "Presenting complaints and examination (brief, and only relevant)" and "Treatment history (Surgery/chemotherapy/radiotherapy)"; slide 3 relevant investigations (biopsy, histopathology, tumour markers); slide 4 imaging (CT/MRI/PET CT); slide 5 "Fitness for Treatment (only if relevant)"; slide 6 "Questions for the tumor board". It is an input form for one discussion with no outcome fields (as `research/02` section 2.4 already found), so the Case summary adds the output sections itself.
- ICMR or Tata Memorial case summary formats: nothing public found in this search; not claimed.

**4. Grounding, faithfulness, editable versions**

- **Rashkin et al., "Measuring Attribution in Natural Language Generation Models"** (Attributable to Identified Sources, AIS), arXiv 2112.12870, 2021, revised 2022 (https://arxiv.org/abs/2112.12870). A statement is attributable when a reader can verify it from an identified source; evaluated by humans in a two-stage annotation; automatic NLI estimates (AutoAIS) were used by later work, and a later study warns the evaluator choice changes results (from the search summary). Contribution: our check is stricter and cheaper than AutoAIS: the source span must contain the quote word for word (plain code, no model).
- Method families from the same search: RARR (https://arxiv.org/pdf/2210.08726, researches and revises output against sources), Attributed QA (https://arxiv.org/pdf/2212.08037), ExpertQA (https://arxiv.org/pdf/2309.07852), and "learning to refuse" for RAG (https://arxiv.org/pdf/2409.11242). Only titles and snippets were read. Contribution: revise-or-refuse. Vaidyx already chooses refuse (drop), which costs coverage; the answer to coverage is the code-built sentences and `fill_from_facts` (section 6), not looser checks.
- **Editable summary with versions in practice**: I found no single authoritative source in this search for the "edited by Dr X" pattern; HL7 FHIR Provenance and the Composition resource carry author, attester and `Composition.section.entry` references, and `Composition.status` (preliminary, final, amended) is the version state, from my own knowledge, not checked in this run. The design in section 5 follows the project's own pattern (`confirm.py`: a separate store overlaid at read time, undo marks never deletes) and `postboard._new_version` (version rows with who, when, reason).

## 4. The proposed Case summary

General rules for every section: written in the NCG-style plain registrar voice of `summary.SYS`; every sentence either carries a citation of one of the two kinds, or is a code-built sentence that states its own source (as `fill_from_facts` does); dates DD/MM/YYYY on screen; no stage computation, no interpretation, no treatment advice, no prognosis; "AI draft, not reviewed" until the consultant reads it; no accuracy claim.

Two citation kinds (both shown with the existing chip):
- **Record line**: `{doc_id, quote, page, start, end, doc_title, date, status}` exactly as `qa.verify` returns today. Chip text: "Histopathology report p. 2".
- **Board-record field**: `{board_record, version, field, quote, board_date}` where `quote` is the exact text of that field in that record version. Checked by plain code: the normalised quote must be a substring of the normalised stored field (`grounding.norm`), and every number in the sentence must be in a quote (reuse `qa._missing_numbers`). Chip text: "Board 12/11/2026, decision". The same shape serves an action (`{action, field: "label|status|closed_by|completed", quote}`), a confirmed stage (`{staging, field: "confirmed", quote}`) and a member's card (`{meeting, case, user, field: "note", quote}`).

### 4.1 Presentation and diagnosis

- **Inputs**: verified current facts `presenting_complaint`, `diagnosis_date_mode`, `smoking_history`, `tobacco_use`, `menopausal_status`, `comorbidities`, `histologic_type`, `grade`, receptors and markers per protocol (`SECTION_FACTS["presentation"]` and `["investigations"]`, `summary.py:9-18`), with clinician confirmations overlaid; documents before the first board date in date order (event date from `dates.doc_dates`, the same as `postboard.timeline`); the first pre-board summary's sentences for these two NCG sections as a hint (not a source).
- **Grounding**: record line, checked word for word. Confirmed facts without a quote say who confirmed them (existing rule).
- **Nothing to say**: one fixed sentence "Presenting complaint and diagnosis are not documented in the records of this Case File." with no citation (code text, labelled not documented); never a guess.
- **Built by**: model (one call) plus `fill_from_facts`.

### 4.2 Stage

- **Inputs**: `stage_as_recorded` (a signed report's stage, copied); a Vaidyx draft stage only after a doctor confirmed it (`st["staging"].confirmed`, `staging/__init__.py:417-428`), labelled "Vaidyx draft stage, confirmed by Dr X"; `stage_as_agreed` of each board record (from item 3.1, with its source); a differing stage written in a report is shown and flagged, never overridden (invariant).
- **Grounding**: report stage by record line; agreed stage by board-record field; confirmed draft by the confirmation record. No model: code lists them in date order.
- **Nothing to say**: "No stage is recorded in a signed report and none has been confirmed. Cannot stage." (the project word is "cannot stage", never a guess).
- **Built by**: code only.

### 4.3 Each board round

- **Inputs**: one block per board record, oldest first, from the board record fields: `board_date` (or `recorded_at`), the question put to the board (the Case File's `clinical_question` fact at that time, as a record line, or the record's question if item 3.1 stores it), `outcome_type`, `decision_text`, `rationale`, `intent` and `intent_as_stated`, `modalities`, `sequence`, `divergent_views` and `concerns` (named), `alternatives_discussed`, `trial_considered`, `stage_as_agreed`, `next_step`, `next_review`, `responsible_doctor`, and the actions raised (`actions[]` with department and due). Members' cards: agree or concern with the note, by name.
- **Grounding**: board-record field, exact text. Code builds one sentence per field ("The board's decision, as recorded: <exact text>.") so the value is never paraphrased. Rationale and decision are quoted whole; if over 600 characters the sentence quotes the first 600 and the chip opens the whole.
- **Nothing to say**: a record with outcome "deferred", "referred", "not_discussed" or "noted" shows only its outcome line and its awaited, referred or reason field; an empty optional field is left out (no "not stated" padding). A case with no board record has no such section, and the main summary stays the pre-board summary (item 3.4).
- **Built by**: code only. Version note: if a record was corrected later (item 3.1, versions kept) the block shows the current text and "corrected on DD/MM/YYYY by Dr X, reason ..." taken from the version row.

### 4.4 Treatment and follow-up since

- **Inputs**: documents with an event date after the first board date, in date order, of types treatment summary, discharge summary, operative or procedure note, radiotherapy and chemotherapy records, clinical notes, imaging, pathology and labs (the protocol's `doc_type`s), and the facts `treatment_received`, `treatment_completion_date`, `lesion_size`, `nodal_findings`, `distant_findings`, `recorded_stage`; `closed_doc_id` of each closed action (it names the document that closed it); the HIS encounters after the board (`encounter_lines`).
- **Grounding**: record line, checked word for word, with the document's date shown ("The discharge summary of 20/12/2026 records ..."). The model may only arrange; values copied.
- **Nothing to say**: "No records dated after the board decision of DD/MM/YYYY have been added yet." (code text, no citation).
- **Built by**: model (one call over only the post-board documents, so the context is small) plus `fill_from_facts` for the treatment facts.

### 4.5 Current status and open actions

- **Inputs**: `state["actions"]` of source "board" (open: pending or overdue with due date; closed with `closed_by`, `completed`, and the closing document), the patient-informed date (`patient_informed_date`, `informed_by`), `next_review` (`st["next_review"]`), the open information flags of the latest record (`adjudication.flags` with kind communication), open Points for review that are still open.
- **Grounding**: action fields by exact text (label, department, due, status), closure by the closing document as a record line or the history line; patient-informed by board-record field.
- **Nothing to say**: "No board actions are open." when all are closed, or "No board decision has been recorded." (then the whole Case summary does not exist).
- **Built by**: code only, so it is always correct to the second; it also is the only section that must be rebuilt on every action closure (cheap, no model).

### 4.6 Example (synthetic breast Case File, plain words)

Square brackets are the citation chips. All names, dates and values are made up (SYNTHETIC, Vaidyx Demo CA).

**Presentation and diagnosis.** She presented with a lump in the right breast for three months [Clinical note p. 1]. The histopathology report of 02/11/2026 records invasive ductal carcinoma, grade 2 [Histopathology report p. 1]. Oestrogen receptor is recorded as positive and HER2 as negative [IHC report p. 1].

**Stage.** The staging CT report of 05/11/2026 records "cT2 N1 M0" as written in the report [CT chest abdomen report p. 2]. Vaidyx draft stage, confirmed by Dr A on 12/11/2026 [Stage confirmation]. No other stage is recorded.

**Board round 1, 12/11/2026.** The question put to the board was "Neoadjuvant therapy or upfront surgery?" [Question for the board]. Decision as recorded: "Neoadjuvant chemotherapy, then breast conserving surgery" [Board 12/11/2026, decision]. Treatment intent as recorded: curative [Board 12/11/2026, intent]. Rationale as recorded: "Tumour size 3.2 cm with a node on imaging" [Board 12/11/2026, rationale]. Dr B recorded a concern: "Wants genetic counselling first" [Board 12/11/2026, divergent views]. Actions raised: "Genetic counselling referral" for Medical Oncology, due 26/11/2026 [Board 12/11/2026, action A1b2c3]; "Echocardiogram" for Cardiology, due 19/11/2026 [Board 12/11/2026, action A4d5e6].

**Treatment and follow-up since.** The echocardiogram report of 18/11/2026 records an ejection fraction of 62% [Echocardiogram report p. 1]. The chemotherapy record of 03/12/2026 records cycle 1 given [Chemotherapy chart p. 1].

**Current status and open actions.** Open: "Genetic counselling referral", Medical Oncology, due 26/11/2026, overdue [Board 12/11/2026, action A1b2c3]. Closed on 18/11/2026 by Dr C with the echocardiogram report: "Echocardiogram" [Echocardiogram report p. 1]. The patient was recorded as informed on 13/11/2026 by Dr A [Board 12/11/2026, patient informed]. Next review: 15/01/2027 [Board 12/11/2026, next review].

(How the pre-board summary marks citations today: each sentence in `sentences[]` has `citations[]`; the component prints the sentence then up to three `quote-chip` buttons with the document title and "p. N". Sentences from fields or confirmations carry `from_fields` and a bracketed source inside the text, e.g. "ECOG: 1 (as recorded in the Clinic note, 03/11/2026)" at `summary.py:53`. The new board-field chip is a new kind with the same look.)

## 5. Data flow

**When built.** After each `postboard.record_decision` returns (`postboard.py:406-432`) and after `update_communication` or an action closure changes status, schedule a background build, with the same pattern and guards as `ready_hook` (a session is running means wait; one run per Case File; the owner is notified when done; failure audited). Section 4.3 and 4.5 are rebuilt by code at once (no model); 4.1 and 4.4 are rebuilt by the model only when the Case File signature changed or on demand. On demand: a "Write it again" button, same permission as `POST /cases/{id}/summary` (`routes/tumour_board_routes.py:1695-1701`, the owning department's doctors or the MDT Coordinator).

**Where stored.** `st["artefacts"]["case_summary"] = {"current": n, "versions": [v1, v2, ...]}`; each version: `{n, built_at, trigger {kind: "decision"|"action"|"on_demand", record}, signature, board_records [{id, version}], sections, points_for_review, removed, model, seconds, review {status, by, at, comment}, edits []}`. The pre-board summary becomes `artefacts.summary_history: [ ... ]` (item 3.5: `summary.build` appends the old object before replacing the live one, and the review stays inside each object) while `artefacts.summary` stays the live pre-board summary so every existing reader keeps working. Both are in `state.json`, which already holds artefacts; size grows slowly (about 10 to 40 KB per version).

**Review and edits.** The owner's consultant (and no one else, as for corrections to the decision record; `research/02` rule 8) reads the version and marks it reviewed (the existing `service.review`, extended to take a version number). Edit: per sentence, `edits[{sentence_id, text, by, by_name, at, previous, previous_citations}]` in the version; the screen shows the edited text with "edited by Dr X on DD/MM/YYYY" and a link "show the Vaidyx text". An edited sentence keeps its citations; if the edit changes a number or a name, the check runs again and the sentence is flagged "edit not checked against the record" rather than blocked (the doctor's word beats the model; an edit is audited like every user action). A rebuild writes version n+1 next to version n: sentences the consultant edited are carried forward into n+1 in the same place, marked edited, and a sentence the model now writes differently for the same source is shown as a suggestion beside it, never over it. Nothing is deleted; the version list shows who reviewed which version. Every edit and review is audited (`store.audit`).

**The main summary and the summary line (item 3.4).** After the first recorded decision the Summary section and the Overview show the current Case summary first; the pre-board summaries are listed under "Before the board on DD/MM/YYYY" (each with its review). `case.summary_line` is one sentence (about 160 characters) built from the Case summary's sections 4.1 and 4.3, for example "Invasive ductal carcinoma, right breast, cT2 N1 M0; board 12/11/2026: neoadjuvant chemotherapy then breast conserving surgery; 1 action open". Built by code from facts and the latest decision text (so it needs no extra model call and is always cited), editable by the consultant (edit marked as above), stored in `case["summary_line"]` with its version. The list item (`cases_list`) carries it; both haystacks add `summary_line`, the cancer name (already there) and the latest `decision_text`: `api/cases_list.py:198-213` parts list and `web/tb-nik/src/lib/search.ts:19-29`; `types.ts CaseListItem` gets the fields. The Ctrl+K bar already calls `matches`, so one change in `search.ts` covers both. Highlighting (`pieces`) already works on any text. The line shows in `CaseHeader.tsx` and the list rows.

**Readers that change.**
- `slots._prose` and `steps.py` (`:446-477`, `:512-569`): "ready", "stale" and "reviewed" must read the Case summary when one exists (stale also when a new board record, an action change or a confirmation changed after the build: add the board record ids and action statuses to a second signature); the "Write it again" and "Read" to-dos follow it.
- `SummaryStep.tsx` and `Overview.tsx`: new version selector, edit control, board-field chips, the "Before the board on ..." fold.
- `meetings.slides` and `deck/__init__.py`: the meeting summary slide keeps the pre-board summary for a case not yet decided; for a case with a record, the Case summary's current sections. The decision slides already show the outcome (`deck/__init__.py:446-470`).
- `vtb_export._summary`: keep reading the pre-board summary (the NCG template is a pre-board input form); add an optional line under "Questions for the tumor board" for a later round ("Previous board 12/11/2026: decision ...") only if the owner wants it (question 7).
- Minutes (`board.minutes`): unchanged (code only, "nothing here is a model output"); add the summary line under each case if wanted.
- `fhir_export.py:197`: add the Case summary sections as further Composition sections.
- `mcp_server.py:209`, `metrics.py`, `dept_requests.py:388`, `ready_hook.summary_fresh`: read the status of both artefacts.

## 6. Model use

- **Sizes.** The reasoner is Gemma-4-31B (non-medical), bf16, `--max-model-len 32768` (`tumour_board/serve_models.sh:18`). Today's call is 60 000 characters of documents (about 15 000 tokens at 4 characters a token, a rough figure; Indian-language and table text counts more) plus the prompt and 3 500 output tokens (`summary.py:118,129`). The new sections need less: 4.1 gets only the pre-board documents and the facts (cap 40 000 characters, about 10 000 tokens, output 1 500); 4.4 gets only the post-board documents (cap 40 000 characters, output 1 500). The board and actions sections add no model context (code). A structured JSON of the board records, if fed to the model for 4.4, is under 3 000 tokens.
- **One call per section or one for all.** Recommend one call each for 4.1 and 4.4, run in parallel (the queue has 48 slots, `docs_Eswar/01_how_vaidyx_tb_works.md` line 113), because each has a different document set and a failure of one leaves the other usable. One call for all five would need all documents plus all records, near 20 000 to 25 000 tokens in, which leaves little for output on a large file and mixes the pre- and post-board document sets.
- **Prompt shape.** Reuse `SYS` and the schema of `summary.SCHEMA` (section, text, citations), changed to: "Write only about the documents given. One fact per sentence where possible. Cite each sentence with the document id and the exact line that carries the value. Keep each quote short. Dates as in the record. If a section has nothing documented, return no sentence for it." Each document is labelled `[doc_id | event date | status]` as `search.context_for` already does, in date order. For 4.4 add the instruction "Mention when a report is draft or superseded".
- **Quote check.** `qa.verify` unchanged for record lines (quote located, numbers inside the quote, negation flag, near-match behind its flag), then `guardrails.scan_output`. New small function for board-record fields (substring of the stored field by `grounding.norm`, numbers guard). Both write drops into `removed` with the reason and the place, as now (V1 item 6.4).
- **Keeping every sentence attributable.** (a) Anything uncited is dropped, never kept as "needs review" (invariant), except code-built sentences that state their source. (b) Values: the model sentence must contain the value as written; the number guard drops a sentence whose numbers are not in a quote; code-built sentences quote the field verbatim, so there is nothing to paraphrase. (c) A coverage backstop like `fill_from_facts`: after the check, any verified fact of the section that no kept sentence carries is added as a plain cited sentence. This is the answer to the faithfulness against coverage trade-off: the model may be cut hard by the check, and the plain sentences refill the facts. What it cannot refill is connective narrative ("then"), which the design deliberately does not need. (d) Time: ask the model for no relative dates ("last month"); the check cannot verify them, so a sentence with one is dropped by a regex rule (a small new guard; the cancer-summary paper's temporal confusion type, section 3).
- **Expected time.** Today 24 to 34 s for one 15k-token call. Two parallel calls with smaller contexts: about 10 to 25 s; code sections under 1 s. Single H200, so background builds queue behind a running board session (the existing `ready_hook` rule) and behind eval runs.
- **Labels.** Every model section carries "Written by Gemma-4-31B (non-medical)" (via `modelLabel`, as the current step does), "AI draft, not reviewed" until the consultant marks it, and no accuracy claim.

## 7. Tests to write

Unit tests with a fake reasoner (a stub for `llm.chat`, as the other module tests do):
1. A decided synthetic case builds five sections; every sentence has a citation or is a code-built source sentence.
2. A model sentence with a quote not in the document is dropped and appears in `removed` with its reason; a sentence with a number not in its quote is dropped; an advice-like sentence is removed by the guardrail.
3. A board-field citation: exact text passes; text altered by one word fails; a number not in the field fails.
4. Two board records give two round blocks in date order; a deferred record shows only its outcome and awaited item; a corrected record shows the current text and the correction note.
5. No-document and no-record cases: the fixed "not documented" sentences, no model call for the code sections.
6. Stage: a draft stage appears only after `staging.confirm`; a differing report stage is shown and flagged, not overridden; no stage gives "cannot stage".
7. Open actions: a pending action shows overdue after its due date; closing it with a document moves it to closed with the closer's name and the chip to that document.
8. Versions: a rebuild after a second decision creates version 2, keeps version 1 unchanged, keeps each review with its version; an edit shows "edited by Dr X"; a rebuild carries the edit forward and never overwrites it; a non-consultant gets 403 on edit; every edit and review is audited.
9. Pre-board history (3.5): `summary.build` twice leaves two objects, the first with its review intact.
10. Summary line: built from the Case summary; edit changes it and marks it edited; `cases_list._match` finds a word of the line and of the decision text; the web `matches` test in `search.ts` does the same (Vitest, same cases); Ctrl+K finds it.
11. Background trigger: `record_decision` schedules one build; a second decision during a build queues one more, not two; a build failure is audited and the old version stays current.
12. Readers: Summary step status words (none, stale, ready, reviewed) with a Case summary; the meeting slide and deck use it after a decision and the pre-board summary before; VTB export still works with only a pre-board summary.
13. Print/export: the printed Case summary carries version number, date, reviewer and "edited by" marks.

Real-model run on decided synthetic Case Files (GPU, one at a time, after the unit tests; use TB-001 to TB-003, TB-007 and TB-008 with a recorded decision, a later report and one closed action added): per case the number of sentences kept and dropped by reason, time per section, and an omission check against the answer key like `summary_eval.py` (which checks key fields appear in the primary table or a sentence; precision is 100% by construction). Extend it with: every board-record field with a value appears in its round block; every open action appears in 4.5; no sentence without a citation; two runs give the same code sections. A clinician reads five versions and marks sentences wrong or missing; those counts are reported as counts, not as an accuracy claim. Never on `TB-2026-bharath`.

## 8. Open questions for the owner

1. Who may edit and sign off a Case summary: only the owner's consultants (as the plan says), or also the MDT Coordinator for the board-round block they already entered? Can a resident draft an edit for the consultant (as the Summary step does with "Send to Dr X for sign-off")?
2. When the consultant edited a sentence and the records later change so the sentence is out of date, do we keep it with a "records changed after this edit" mark (proposed), or ask the consultant before carrying it forward?
3. The consultant's edit may introduce a fact with no record line (the doctor's word). Allowed with the label "edited by Dr X, not checked against the record" (proposed), or must every edit carry a quote too?
4. Members' cards and divergent views: shown by name in the Case summary (it will be read for years by anyone who opens the file), or as "a member recorded a concern" without a name? The decision record research (`research/02`, rule 10) wants the name for the record itself.
5. Who sees `summary_line` in the list and the command search? It carries clinical text, so proposed: only people with full access to that Case File (the access scope FULL, `00_current_state.md` section 5), and for others the list stays as today.
6. Should the summary line be built by code from facts (proposed, always cited, no model) or written by the model in plain words (smoother, but another call and another check)?
7. Does the NCG VTB export (and the deck for a later board) include "Previous board" lines from the Case summary, or stay a pre-board input form as NCG's template is?
8. Retention: the NMC regulation keeps indoor records for 3 years (`nmc.org.in`, 1.3.1). Are the Case summary versions kept as long as the Case File (proposed, no deletion), and does a printed copy need a signature block (the NABH practice of a signed or countersigned summary, a secondary source)?
9. Which clinical text the NABH discharge summary content standard (AAC.14, element list not read) and the Clinical Establishments rules need: can a clinician or the hospital quality team check the heading list before the fixed layout is final?
10. Built after every recorded decision automatically (proposed), or after the consultant presses "Update the Case summary"? Automatic means a draft appears without anyone asking; the owner is notified, and nothing counts until reviewed.
