# Results of the benchmark experiments (TODO.md items 1 to 4)

Run on 20 Oct 2026 on the development server, on the owner's word ("then we will work on the benchmark tasks"). Numbers are in
`results/*.json`; text from the datasets and the reports stays outside the repo in `/data/vaidyx/research_experiments/`.

| Item | Script | Needs the GPU | Status |
|---|---|---|---|
| 3 Confidence intervals and paired tests | `stats.py` | no | done |
| 4 Oncology slice | `stats.py` | no | done; the filter needs a doctor's check |
| 2 Real TCGA reports at scale | `tcga_scale.py` | yes (shipped extractor) | done |
| 1 What the grounding layer removes, larger probe set | `probes_scale.py` | yes (shipped reasoner) | done |
| 5 Real Indian documents, clinician review | | | the owner's decision |

## 3. Confidence intervals and paired tests

95 % percentile bootstrap (4,000 resamples of questions, stratified by dataset for the overall score), paired bootstrap for
differences, McNemar's exact test on the questions where exactly one model is right. The Baichuan-M2 direct re-score from the saved
replies reproduces the published table exactly (74.6, 67.1, 71.7, 86.9, 17.9; 58.6).

- **Width.** An overall text score is uncertain by about ±0.8 points; MedXpertQA by about ±1.8; MedQA by ±1.3 to ±2.8.
- **One tie group in the middle.** Ranks 3 to 6 (Qwen3.5-4B 62.4, MedGemma-27B-text-it 62.0, MedGemma-27B-it 61.7, Baichuan-M2
  61.2) cannot be separated: every pairwise difference has a confidence interval that includes zero (p = 0.13 to 0.49).
- **"Qwen3.5-4B matches MedGemma-27B-it" holds:** +0.7 points [−0.2, +1.5], p = 0.13; on MedQA −0.9 [−3.2, +1.3].
- **Ties further down:** Med42-8B and JSL-MedLlama (+0.4, p = 0.49), MedGemma-1.5-4B and OpenBioLLM-8B (+0.8, p = 0.18).
- **Firm leads:** Gemma-4-31B over HuatuoGPT-3 (+5.4 [+4.6, +6.2]), HuatuoGPT-3 over Qwen3.5-4B (+8.9), Baichuan-M2 over Lingshu
  (+3.0), Qwen3.5-4B over MedGemma-4B (+11.6), HuatuoGPT-3 over Lingshu on direct answers (+6.2), Gemma-4-31B over HuatuoGPT-3 on
  MedXpertQA (+14.8). Reasoning helps Gemma (+17.4) and HuatuoGPT-3 (+5.2) and costs Lingshu (−1.7) and Med42 (−2.7), all significant.
- **Images:** HuatuoGPT-3's OmniMedVQA lead over Lingshu is real but small (+0.5 [+0.2, +0.8], p < 0.001); Lingshu over Gemma +0.9.
  Lingshu's SLAKE lead over HuatuoGPT-3 is large (+24.6). Gemma-4-31B leads MedXpertQA-MM (+5.8 over HuatuoGPT-3) and PMC-VQA (+6.0
  over Lingshu) with reasoning.

What changes in the paper: the ranking table gets intervals; ranks 3 to 6 are described as one group within a point of each other;
"leads" for OmniMedVQA is qualified as half a point.

## 4. Oncology slice

A keyword filter over the question and its options (cancer, carcinoma, tumour, neoplasm, lymphoma, leukaemia, sarcoma, metastasis,
malignancy, oncology, chemotherapy, radiotherapy, melanoma, myeloma) marks 674 questions: MedQA 159, MedMCQA 189, MedXpertQA 326.

- The top two are unchanged: Gemma-4-31B 74.0 [70.9, 77.0], HuatuoGPT-3 67.5 [64.2, 70.6].
- In the middle group, Qwen3.5-4B and Baichuan-M2 (both 54.8) move ahead of MedGemma-27B-it (52.7) and MedGemma-27B-text-it (50.3),
  but the intervals (about ±3 points) overlap.
- Most medical fine-tunes score lower on oncology than on the other questions of the same sets: MedGemma-27B-text-it −7.1,
  JSL-MedLlama −6.0, OpenBioLLM −6.2, MedGemma-4B −4.4. Gemma-4-31B and HuatuoGPT-3 do not (+0.4, +0.5).
- **Needs a doctor:** 100 questions (60 the filter marks, 40 it does not, fixed seed) are in
  `/data/vaidyx/research_experiments/oncology_filter_sample.csv` with a column for a doctor's yes / no. Until that check, the slice
  is "questions mentioning cancer", not "oncology questions".

## 1. What the grounding layer removes, on a larger probe set

419 probes generated from the answer keys of the eight synthetic Case Files (118 answerable, 269 traps, 32 out of scope), plus the
57 hand-written release probes, through the shipped Ask pipeline (Gemma-4-31B-it, non-medical). `qa.ask` returns the statements it
shows and the ones grounding removed, so one run gives both arms. Corrected scoring: `probes_scale.py --rescore`.

| Probe kind | Probes | Right answer |
|---|---|---|
| Answerable | 118 | 117 (the miss: a correct statement removed by the output guardrail) |
| Not in the file, true traps | 205 | 205 "not documented" |
| Out of scope | 32 | 32 declined |
| Documented after all (answer-key gaps) | 64 | 64 answered with verified quotes |
| Hand-written release set | 57 | 57 |

- **No fabricated value was shown in 476 probes.** One-sided 95 % upper bound on true traps: about 1.5 % (0 of 205).
- **The reasoner rarely writes an unsupported statement.** Grounding removed five statements in 419 probes, reviewed by hand: two with a
  wrong detail that it caught (8 to 13 cm for 8 to 12 cm; a report date off by ten days), two true but with a quote that did not match
  (the cost in recall), one statement of absence.
- **Correction to the paper:** "zero fabrications is the grounding layer's doing rather than the models'" overstated it; on clean text
  the reasoner itself is the main reason; the layer catches the rare wrong detail.

## 2. Real TCGA reports at scale

The shipped extractor (Qwen3.5-4B, Chinese, non-medical) on every TCGA report with cBioPortal ground truth: 2,102 reports (1,034 breast,
488 lung adenocarcinoma, 580 colorectal); 3 failed. Every reading is saved (`/data/vaidyx/research_experiments/tcga_scale_extractions.jsonl`),
so `tcga_scale.py --rescore` redoes the scoring without the model.

- **10,883 values read; 151 (1.4 %, upper 95 % bound 1.6 %) without a verifiable quote**, mostly OCR damage, flagged rather than shown.
  On real OCR text one value in seventy cannot be tied to its line: this is where grounding matters.
- **Agreement with the clinical record** (both sides state the field): histology 97.5 %, pT 97.2 %, pN 97.4 %, stage group 93.3 %,
  ER 91.3 %, PR 90.1 %, HER2 IHC 84.2 %. Pending results (ER and PR 49, HER2 63) and HER2 given only by in situ hybridisation (50) are
  counted apart.
- **265 of the 272 disagreements carry a verified quote:** the report itself says what Vaidyx read; the research record differs.
- **Scoring rules were refined after inspecting a sample of disagreements.** First, stricter scoring: histology 92.1 %, ER 88.6 %, PR
  87.3 %, HER2 74.0 % (`/data/vaidyx/research_experiments/tcga_scale_first_scoring.json`); both are reported in the paper.

## Figures

`figures.py` draws nine figures as SVG from the generated data (web: inline, following the light and dark themes; paper: the same
drawing without its title, as vector PDF via `figures_pdf.cjs`): ranking with intervals, reasoning gain, this run against the cards,
4-bit against bf16, cancer questions, image heatmap, probes and grounding, TCGA agreement, size against accuracy.
