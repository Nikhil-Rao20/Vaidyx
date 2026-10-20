# Experiments still to run for the paper

Status (20 Oct 2026, evening): **items 1 to 4 run** on the owner's word ("then we will work on the benchmark tasks"); results in
[experiments/RESULTS.md](experiments/RESULTS.md), the paper and the Research page. Still open: the doctor's check of the oncology
filter (item 4), the other extractor and reasoner candidates on items 1 and 2 (they need the GPU swapped: agree a time with the
owner), and item 5 (the owner's decision).

Why: the benchmark half of the paper is solid. The grounded half carries our own claim (a general model plus the grounding layer
is safe enough to show Board facts) and today rests on small samples. Items 1 to 4 fix that; item 5 is the owner's decision.

| # | Experiment | Needs the GPU | Rough time | Changes |
|---|---|---|---|---|
| 1 | Grounding switched off, larger probe set | yes | half a day | **done** for the shipped reasoner (`experiments/probes_scale.py`) |
| 2 | Real TCGA reports at scale | yes | a few hours per model | **done** for the shipped extractor (`experiments/tcga_scale.py`) |
| 3 | Confidence intervals and paired tests | no | an hour | **done** (`experiments/stats.py`) |
| 4 | Oncology slice of the exam questions | no | an hour, plus a doctor's check | **done**; the doctor's check is open |
| 5 | Real Indian documents, clinician review | no | owner's decision | data and approvals |

Runs with our two shipped models (Qwen3.5-4B reader on :8101, Gemma-4-31B reasoner on :8100) use the servers already running.
Comparing the other candidates (MedGemma-27B-it, Lingshu-32B, HuatuoGPT-3-27B, MedGemma-27B-text-it) means swapping models on the
single H200, which pauses localhost and the public demo for those hours: agree the time with the owner first.

## 1. What the grounding layer removes (ablation), on a larger probe set

- **Gap.** The paper says zero fabrications is "the grounding layer's doing rather than the models'", but every run had the layer
  on. Zero out of 33 probes only bounds the fabrication rate below about 9 % (rule of three: 3 / n).
- **Run.** The same extractions (bake-off corpus) and the same Ask-the-Case-File probes with verification switched off in the
  evaluation path only (never in the product), then with it on. Count: what the raw model states without a matching quote
  (fabrications), how many of those the layer removes, and the cost: correct facts the layer drops because the quote did not
  match (recall loss; `dropped_unverified` in `summary_eval_*.json` is a start).
- **Probe set.** From 33 to several hundred: answerable, absent-value traps and out-of-scope requests across more synthetic Case
  Files, including one long synthetic Case File of 40 or more documents. Never the real case.
- **Where.** `tumour_board/eval/qa_eval.py`, `bakeoff.py`, `summary_eval.py`; grounding in `tumour_board/grounding.py`.
- **Paper.** New table in Section 8: with / without the layer, per model; update the abstract and the discussion.

## 2. Real pathology reports at scale

- **Gap.** 30 reports and 166 values today (0 ungrounded only bounds the rate below about 1.8 %). The synthetic bake-off is at
  ceiling (every model 48 or 49 of 49 fields), so it cannot separate the extractor candidates.
- **Data already on disk.** 9,523 TCGA reports in 33 cancer types:
  `/data/vaidyx/tb_resources/real_data/tcga_path_reports_text/TCGA_Reports.csv` (+ `tcga_patient_to_cancer_type.csv`).
  Ground truth from cBioPortal in `/data/vaidyx/tb_resources/real_data/tcga_ground_truth_clinical/`: breast (1,102 patients: ER,
  PR, HER2 IHC and FISH, pT, pN, pM, stage, histology), lung adenocarcinoma (585) and colorectal (637): pT, pN, pM, stage,
  histology. About 2,300 patients in all; the current subset is `tcga_eval_subset_30.csv`.
- **Run.** `tumour_board/eval/tcga_eval.py` on every report with ground truth, shipped reader and extractor first, then the other
  candidates. New fields: HER2, pN, pM, stage. Report grounding (ungrounded values) and agreement per field, with the same
  "metric artefact" review of disagreements as the 30-report run (a sample checked by hand).
- **Paper.** Replace Table 14 with the scaled table, one row per model; per-field agreement; update Sections 8.1 and 8.3.

## 3. Confidence intervals and paired tests (no GPU)

- **Gap.** Headline claims rest on gaps under one point (Qwen3.5-4B "matches" MedGemma-27B-it: 62.4 against 61.7). Each overall
  text score is uncertain by about one point either way, MedXpertQA by about two. Reviewers will ask for intervals first.
- **Run.** Bootstrap 95 % intervals per score and paired tests (McNemar or paired bootstrap) for the comparisons the text makes,
  from the saved per-question replies: `~/vaidyx/benchmark/results/<model>/{direct,cot}/<dataset>.jsonl` (fields id, gold, pred,
  correct) and `results_vqa*/`. Read only; write the output under this folder, never into `~/vaidyx/benchmark`.
- **Paper.** Intervals in the main tables (or a supplementary table); soften any claim whose interval overlaps.

## 4. Oncology slice (no GPU)

- **Gap.** A Tumour Board paper with no cancer-specific score.
- **Run.** A keyword pass over the saved questions finds about 680 oncology questions (MedQA 163, MedMCQA 192, MedXpertQA 328;
  cancer, carcinoma, tumour, neoplasm, lymphoma, leukaemia, sarcoma, metastasis, malignancy, chemotherapy, radiotherapy, melanoma,
  myeloma). Score every model on that slice from the saved replies. A doctor (Dr Minmini or Dr Usha) checks a random sample of the
  filter for false hits and misses before the numbers go in.
- **Paper.** One table: oncology slice against all questions, per model; does the ranking hold?

## 5. Owner's decision: real Indian documents and a clinician review

- **Gap.** Every grounded test uses either our synthetic Indian-format files or American TCGA reports. Real Indian reports bring
  phone photographs, stamps, handwriting and Hindi or regional-language parts; the Indic OCR packs are installed but never
  measured. The title says "in India".
- **Options.** (a) A de-identified set from a partner hospital, with ethics committee approval; or (b) keep the data as it is,
  say "designed for India" in the title and abstract, and state this as the main limitation.
- **Clinician review.** A small blinded review by the clinician co-authors (for example 20 Board summaries and their extracted
  fields, rated for correctness and omissions) would give the paper its only human-judged result.

## Not worth doing

More models, more exam benchmarks, thinking-mode runs, or a language-model judge for open image answers: no model reads images in
Vaidyx-TB, so more image work does not move the story.

## After any of these runs

`build_data.py` gains the new numbers, then rebuild as in `README.md` (tables, `build.sh`, copy the PDF to
`web/tb-nik/public/research/`, `npx vite build`), update the Research page wording in `content.ts` (RESEARCH), check localhost,
and publish to the public link only after the owner confirms (`~/vaidyx/public_demo/publish_site.sh`).
