# Ask PubMed: proof that the papers come from PubMed only (Part 1, backend only)

Run 03 Nov 2026 19:40 on the server, fresh PubMed records (no cache), the reasoner Gemma-4-31B-it (non-medical). Not wired into the app yet.

How each answer is checked, without the records Vaidyx fetched:

| Check | How |
|---|---|
| Cited papers came from PubMed's search | the same search is run again and every cited PMID must be in PubMed's list |
| Paper details are PubMed's | every paper's title and year compared with NCBI esummary (a second NCBI service) |
| Quotes are PubMed's text | every quote found word for word on the paper's own PubMed web page |
| The model invented nothing | PMIDs the model cited that were not given are counted (and dropped) |

## Summary

| Area | Status | PubMed found | Read | Lines kept | Lines dropped | Cited in search | Details match esummary | Quotes on PubMed page | Invented PMIDs | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| Breast | answered | 209 | 17 | 2 | 0 | 2 / 2 | 20 / 20 | 2 / 2 | 0 | 9.3 |
| Lung | answered | 84 | 20 | 4 | 0 | 3 / 3 | 20 / 20 | 4 / 4 | 0 | 13.54 |
| Cervix | answered | 146 | 17 | 4 | 0 | 4 / 4 | 20 / 20 | 4 / 4 | 0 | 12.66 |
| Head and neck | answered | 56 | 15 | 3 | 1 | 3 / 3 | 20 / 20 | 3 / 3 | 0 | 11.74 |

## 1. Breast

**Question:** What pathological complete response rates did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?

**Search words** (written by the model): `(pembrolizumab OR immunotherapy) AND "triple-negative breast cancer" AND "pathological complete response"`, all years. PubMed found **209** papers. [Open the same search on PubMed](https://pubmed.ncbi.nlm.nih.gov/?term=%28pembrolizumab+OR+immunotherapy%29+AND+%22triple-negative+breast+cancer%22+AND+%22pathological+complete+response%22&sort=relevance)

**Answer** (each line with the exact words from the paper):

1. A phase 3 trial reported that the percentage of patients with a pathological complete response was 64.8% in the pembrolizumab-chemotherapy group compared to 51.2% in the placebo-chemotherapy group.
   - [PMID 32101663](https://pubmed.ncbi.nlm.nih.gov/32101663/), RESULTS: "the percentage of patients with a pathological complete response was 64.8% (95% confidence interval [CI], 59.9 to 69.5) in the pembrolizumab-chemotherapy group and 51.2% (95% CI, 44.1 to 58.3) in the placebo-chemotherapy group"
2. A meta-analysis found that neoadjuvant chemoimmunotherapy was associated with a higher pathological complete response rate (OR 1.95).
   - [PMID 35740985](https://pubmed.ncbi.nlm.nih.gov/35740985/), Abstract: "the use of neoadjuvant chemoimmunotherapy was associated with higher pCR (OR 1.95; 95% Confidence Intervals, 1.27-2.99)"

**Papers** (20 fetched from PubMed, 17 read by the model):

| # | PMID | Year | Study type (PubMed) | Journal | Title | Read |
|---|---|---|---|---|---|---|
| 18 | [35740985](https://pubmed.ncbi.nlm.nih.gov/35740985/) | 2022 | Meta-analysis | Cells | Pathological Complete Response to Neoadjuvant Chemoimmunotherapy for Early Triple-Negative Breast Cancer: An U | cited |
| 1 | [38369015](https://pubmed.ncbi.nlm.nih.gov/38369015/) | 2024 | Randomised trial | Ann Oncol | Event-free survival by residual cancer burden with pembrolizumab in early-stage TNBC: exploratory analysis fro | read |
| 2 | [39282906](https://pubmed.ncbi.nlm.nih.gov/39282906/) | 2024 | Randomised trial | N Engl J Med | Overall Survival with Pembrolizumab in Early-Stage Triple-Negative Breast Cancer. | read |
| 3 | [32101663](https://pubmed.ncbi.nlm.nih.gov/32101663/) | 2020 | Randomised trial | N Engl J Med | Pembrolizumab for Early Triple-Negative Breast Cancer. | cited |
| 6 | [35139274](https://pubmed.ncbi.nlm.nih.gov/35139274/) | 2022 | Randomised trial | N Engl J Med | Event-free Survival with Pembrolizumab in Early Triple-Negative Breast Cancer. | read |
| 8 | [39838117](https://pubmed.ncbi.nlm.nih.gov/39838117/) | 2025 | Randomised trial | Nat Med | Pembrolizumab and chemotherapy in high-risk, early-stage, ER+/HER2- breast cancer: a randomized phase 3 trial. | read |
| 16 | [38913881](https://pubmed.ncbi.nlm.nih.gov/38913881/) | 2024 | Randomised trial | J Natl Cancer Inst | Neoadjuvant pembrolizumab plus chemotherapy/adjuvant pembrolizumab for early-stage triple-negative breast canc | read |
| 19 | [39284953](https://pubmed.ncbi.nlm.nih.gov/39284953/) | 2024 | Clinical trial | Nat Med | Neoadjuvant nivolumab or nivolumab plus ipilimumab in early-stage triple-negative breast cancer: a phase 2 ada | read |
| 5 | [40124876](https://pubmed.ncbi.nlm.nih.gov/40124876/) | 2025 | Review | Breast Cancer (Dove Med Press) | Diagnosis, Prognosis, and Treatment of Triple-Negative Breast Cancer: A Review. | read |
| 15 | [38464390](https://pubmed.ncbi.nlm.nih.gov/38464390/) | 2024 | Review | Explor Target Antitumor Ther | Early-stage triple negative breast cancer: the therapeutic role of immunotherapy and the prognostic value of p | read |
| 4 | [33958794](https://pubmed.ncbi.nlm.nih.gov/33958794/) | 2021 | Journal article | Nat Med | A single-cell map of intratumoral changes during anti-PD1 treatment of patients with breast cancer. | read |
| 7 | [39076844](https://pubmed.ncbi.nlm.nih.gov/39076844/) | 2024 | Journal article | Ther Adv Med Oncol | Additional biomarkers for pathological complete response in triple negative breast cancer. | not read: no abstract in PubMed |
| 9 | [40280564](https://pubmed.ncbi.nlm.nih.gov/40280564/) | 2025 | Journal article | J Immunother Cancer | Intratumoral microbiota predicts the response to neoadjuvant chemoimmunotherapy in triple-negative breast canc | read |
| 12 | [38686016](https://pubmed.ncbi.nlm.nih.gov/38686016/) | 2024 | Journal article | Ther Adv Med Oncol | TROPION-Breast03: a randomized phase III global trial of datopotamab deruxtecan ± durvalumab in patients with  | read |
| 13 | [38092228](https://pubmed.ncbi.nlm.nih.gov/38092228/) | 2024 | Journal article | Ann Oncol | Response-guided neoadjuvant sacituzumab govitecan for localized triple-negative breast cancer: results from th | read |
| 14 | [39917260](https://pubmed.ncbi.nlm.nih.gov/39917260/) | 2025 | Journal article | Ther Adv Med Oncol | TROPION-Breast04: a randomized phase III study of neoadjuvant datopotamab deruxtecan (Dato-DXd) plus durvaluma | read |
| 17 | [41022779](https://pubmed.ncbi.nlm.nih.gov/41022779/) | 2025 | Journal article | NPJ Breast Cancer | Tumor-specific major histocompatibility-II expression predicts pathological complete response to atezolizumab  | read |
| 20 | [40011935](https://pubmed.ncbi.nlm.nih.gov/40011935/) | 2025 | Journal article | Trials | A phase II, randomized, open-labeled study to evaluate low-dose pembrolizumab in addition to neoadjuvant chemo (India) | read |
| 10 | [40223028](https://pubmed.ncbi.nlm.nih.gov/40223028/) | 2025 | Comment or letter | Breast Cancer | Reply to the letter to the editor "Pembrolizumab added to neoadjuvant chemotherapy may improve pathological co | not read: no abstract in PubMed |
| 11 | [39881092](https://pubmed.ncbi.nlm.nih.gov/39881092/) | 2025 | Comment or letter | Breast Cancer | Pembrolizumab added to neoadjuvant chemotherapy may improve pathological complete response in androgen-recepto | not read: no abstract in PubMed |

| Check | Result |
|---|---|
| Cited papers in PubMed's search | 2 of 2 |
| Titles and years match NCBI esummary | 20 of 20 |
| Quotes found on the PubMed web page | 2 of 2 |
| PMIDs the model cited that were not given | 0 |
| Raw PubMed answers (SHA-256) | search 8edecd91bd6e8884, fetch 49aa139ec7d6c5b8 |

## 2. Lung

**Question:** What disease-free survival did trials report with adjuvant osimertinib in resected EGFR-mutated non-small cell lung cancer?

**Search words** (written by the model): `(osimertinib) AND ("non-small cell lung cancer" OR NSCLC) AND (resected OR adjuvant) AND ("disease-free survival" OR DFS)`, all years. PubMed found **84** papers. [Open the same search on PubMed](https://pubmed.ncbi.nlm.nih.gov/?term=%28osimertinib%29+AND+%28%22non-small+cell+lung+cancer%22+OR+NSCLC%29+AND+%28resected+OR+adjuvant%29+AND+%28%22disease-free+survival%22+OR+DFS%29&sort=relevance)

**Answer** (each line with the exact words from the paper):

1. In the ADAURA trial, adjuvant osimertinib significantly improved disease-free survival (DFS) in patients with resected stage IB to IIIA EGFR-mutated NSCLC compared to placebo, with a hazard ratio of 0.20 (99.12% CI, 0.14 to 0.30).
   - [PMID 32955177](https://pubmed.ncbi.nlm.nih.gov/32955177/), RESULTS: "In the overall population, 89% of the patients in the osimertinib group (95% CI, 85 to 92) and 52% of those in the placebo group (95% CI, 46 to 58) were alive and disease-free at 24 months (overall hazard ratio for disease recurrence or death, 0.20; 99.12% CI, 0.14 to 0.30; P<0.001)."
2. Updated ADAURA results showed a 4-year DFS rate of 73% for osimertinib versus 38% for placebo in the overall population.
   - [PMID 36720083](https://pubmed.ncbi.nlm.nih.gov/36720083/), RESULTS: "In the overall population, DFS HR was 0.27 (95% CI, 0.21 to 0.34); 4-year DFS rate was 73% (osimertinib) and 38% (placebo)."
3. A meta-analysis of nine RCTs reported that first-, second-, and/or third-generation EGFR TKIs may improve DFS compared to placebo/BSC, though the evidence is very uncertain (HR 0.34, 95% CI 0.28 to 0.41).
   - [PMID 40421698](https://pubmed.ncbi.nlm.nih.gov/40421698/), MAIN RESULTS: "TKIs may improve disease-free survival compared to placebo/BSC, but the evidence is very uncertain (HR 0.34, 95% CI 0.28 to 0.41; 5 studies, 1153 participants)."
4. The same meta-analysis found that EGFR TKIs may have improved DFS compared to chemotherapy (HR 0.54, 95% CI 0.35 to 0.83).
   - [PMID 40421698](https://pubmed.ncbi.nlm.nih.gov/40421698/), MAIN RESULTS: "TKIs may have improved disease-free survival compared to chemotherapy (HR 0.54, 95% CI 0.35 to 0.83; 4 studies, 878 participants; low-certainty evidence)."

**Papers** (20 fetched from PubMed, 20 read by the model):

| # | PMID | Year | Study type (PubMed) | Journal | Title | Read |
|---|---|---|---|---|---|---|
| 8 | [40421698](https://pubmed.ncbi.nlm.nih.gov/40421698/) | 2025 | Meta-analysis | Cochrane Database Syst Rev | Adjuvant epidermal growth factor receptor (EGFR) tyrosine kinase inhibitors (TKIs) for the treatment of people | cited |
| 1 | [36720083](https://pubmed.ncbi.nlm.nih.gov/36720083/) | 2023 | Randomised trial | J Clin Oncol | Adjuvant Osimertinib for Resected EGFR-Mutated Stage IB-IIIA Non-Small-Cell Lung Cancer: Updated Results From  | cited |
| 2 | [32955177](https://pubmed.ncbi.nlm.nih.gov/32955177/) | 2020 | Randomised trial | N Engl J Med | Osimertinib in Resected EGFR-Mutated Non-Small-Cell Lung Cancer. | cited |
| 3 | [37272535](https://pubmed.ncbi.nlm.nih.gov/37272535/) | 2023 | Randomised trial | N Engl J Med | Overall Survival with Osimertinib in Resected EGFR-Mutated NSCLC. | read |
| 4 | [40097663](https://pubmed.ncbi.nlm.nih.gov/40097663/) | 2025 | Randomised trial | Nat Med | Molecular residual disease analysis of adjuvant osimertinib in resected EGFR-mutated stage IB-IIIA non-small-c | read |
| 9 | [34278827](https://pubmed.ncbi.nlm.nih.gov/34278827/) | 2021 | Randomised trial | Future Oncol | Neoadjuvant osimertinib with/without chemotherapy versus chemotherapy alone for EGFR-mutated resectable non-sm | read |
| 11 | [39732365](https://pubmed.ncbi.nlm.nih.gov/39732365/) | 2025 | Clinical trial | J Thorac Oncol | Neoadjuvant and Adjuvant Osimertinib in Stage IA to IIIA, EGFR-Mutant NSCLC (NORA). | read |
| 12 | [39028931](https://pubmed.ncbi.nlm.nih.gov/39028931/) | 2024 | Clinical trial | J Clin Oncol | Neoadjuvant Osimertinib for the Treatment of Stage I-IIIA Epidermal Growth Factor Receptor-Mutated Non-Small C | read |
| 13 | [29789220](https://pubmed.ncbi.nlm.nih.gov/29789220/) | 2018 | Randomised trial | Clin Lung Cancer | ADAURA: Phase III, Double-blind, Randomized Study of Osimertinib Versus Placebo in EGFR Mutation-positive Earl | read |
| 18 | [34740861](https://pubmed.ncbi.nlm.nih.gov/34740861/) | 2022 | Randomised trial | J Thorac Oncol | Postoperative Chemotherapy Use and Outcomes From ADAURA: Osimertinib as Adjuvant Therapy for Resected EGFR-Mut | read |
| 15 | [35596880](https://pubmed.ncbi.nlm.nih.gov/35596880/) | 2022 | Review | Drugs | Neoadjuvant and Adjuvant Systemic Therapy for Early-Stage Non-small-Cell Lung Cancer. | read |
| 19 | [37166792](https://pubmed.ncbi.nlm.nih.gov/37166792/) | 2023 | Review | JAMA Oncol | Adjuvant Treatments for Surgically Resected Non-Small Cell Lung Cancer Harboring EGFR Mutations: A Review. | read |
| 5 | [42732874](https://pubmed.ncbi.nlm.nih.gov/42732874/) | 2026 | Journal article | J Thorac Oncol | Adjuvant Osimertinib in Resected EGFR-Mutated Stage IB-IIIA NSCLC: Exploratory 8-Year Overall Survival Landmar | read |
| 6 | [36108559](https://pubmed.ncbi.nlm.nih.gov/36108559/) | 2022 | Journal article | ESMO Open | The value of disease-free survival (DFS) and osimertinib in adjuvant non-small-cell lung cancer (NSCLC): an in | read |
| 7 | [36872181](https://pubmed.ncbi.nlm.nih.gov/36872181/) | 2023 | Journal article | Clin Lung Cancer | Adjuvant Osimertinib vs. Placebo in Completely Resected Stage IA2-IA3 EGFR-Mutated NSCLC: ADAURA2. | read |
| 14 | [35294773](https://pubmed.ncbi.nlm.nih.gov/35294773/) | 2022 | Journal article | Oncol Ther | ADAURA: The Splash of Osimertinib in Adjuvant EGFR-Mutant Non-small Cell Lung Cancer. | read |
| 16 | [39830775](https://pubmed.ncbi.nlm.nih.gov/39830775/) | 2024 | Journal article | Transl Lung Cancer Res | Osimertinib as a neoadjuvant therapy in resectable EGFR-mutant non-small cell lung cancer: a real-world, multi | read |
| 17 | [35285487](https://pubmed.ncbi.nlm.nih.gov/35285487/) | 2022 | Journal article | Oncologist | Modeling the Cost-Effectiveness of Adjuvant Osimertinib for Patients with Resected EGFR-mutant Non-Small Cell  | read |
| 20 | [33993094](https://pubmed.ncbi.nlm.nih.gov/33993094/) | 2021 | Journal article | Transl Oncol | Weekly osimertinib dosing prevents EGFR mutant tumor cells destined to home mouse lungs. (India) | read |
| 10 | [35320359](https://pubmed.ncbi.nlm.nih.gov/35320359/) | 2022 | Comment or letter | Clin Cancer Res | Adjuvant Osimertinib in EGFR-Mutant Early-Stage NSCLC: Does HRQoL Influence Decisions? | read |

| Check | Result |
|---|---|
| Cited papers in PubMed's search | 3 of 3 |
| Titles and years match NCBI esummary | 20 of 20 |
| Quotes found on the PubMed web page | 4 of 4 |
| PMIDs the model cited that were not given | 0 |
| Raw PubMed answers (SHA-256) | search 31242ba0a3434baa, fetch a7ae538bb89f0e8d |

## 3. Cervix

**Question:** What did trials report about induction chemotherapy before chemoradiation in locally advanced cervical cancer?

**Search words** (written by the model): `("induction chemotherapy" OR "neoadjuvant chemotherapy") AND ("chemoradiation" OR "chemoradiotherapy") AND ("locally advanced cervical cancer" OR "cervical neoplasia")`, all years. PubMed found **146** papers. [Open the same search on PubMed](https://pubmed.ncbi.nlm.nih.gov/?term=%28%22induction+chemotherapy%22+OR+%22neoadjuvant+chemotherapy%22%29+AND+%28%22chemoradiation%22+OR+%22chemoradiotherapy%22%29+AND+%28%22locally+advanced+cervical+cancer%22+OR+%22cervical+neoplasia%22%29&sort=relevance)

**Answer** (each line with the exact words from the paper):

1. A phase 3 trial reported that short-course induction chemotherapy followed by chemoradiotherapy significantly improved 5-year progression-free survival (72% vs 64%) and overall survival (80% vs 72%) compared to chemoradiotherapy alone.
   - [PMID 39419054](https://pubmed.ncbi.nlm.nih.gov/39419054/), FINDINGS: "After a median follow-up of 67 months, 5-year progression-free survival rates were 72% in the induction chemotherapy with chemoradiotherapy group and 64% in the chemoradiotherapy alone group with a hazard ratio (HR) of 0·65 (95% CI 0·46-0·91, p=0·013). 5-year overall survival rates were 80% in the induction chemotherapy with chemoradiotherapy group and 72% in the chemoradiotherapy alone group, with an HR of 0·60 (95% CI 0·40-0·91, p=0·015)."
2. A meta-analysis found that adding induction chemotherapy to chemoradiotherapy significantly improves progression-free survival and overall survival, provided the induction chemotherapy is a platinum doublet with paclitaxel administered within 6 weeks.
   - [PMID 40408847](https://pubmed.ncbi.nlm.nih.gov/40408847/), CONCLUSION: "In patients with LACC, ICT + CCRT significantly improves PFS and OS compared to CCRT alone, provided that the ICT involves a platinum doublet with paclitaxel and is administered within ≤ 6 weeks."
3. A report on 50 patients receiving weekly cisplatin and paclitaxel followed by chemoradiation showed a 3-year overall survival rate of 83.9% and a 3-year progression-free survival rate of 73.6%.
   - [PMID 36641433](https://pubmed.ncbi.nlm.nih.gov/36641433/), RESULTS: "After a median follow-up of 28 months, the 3-year OS rate was 83.9%, and the 3-year PFS rate was 73.6%."
4. The addition of induction chemotherapy to chemoradiation did not adversely impact quality of life compared to chemoradiation alone.
   - [PMID 40139003](https://pubmed.ncbi.nlm.nih.gov/40139003/), CONCLUSION: "IC added to CRT does not adversely impact QoL compared to CRT, either during IC, during CRT or later."

**Papers** (20 fetched from PubMed, 17 read by the model):

| # | PMID | Year | Study type (PubMed) | Journal | Title | Read |
|---|---|---|---|---|---|---|
| 14 | [40408847](https://pubmed.ncbi.nlm.nih.gov/40408847/) | 2025 | Meta-analysis | Cancer Treat Rev | Induction chemotherapy followed by chemoradiotherapy for locally advanced cervical cancer: A systematic review | cited |
| 1 | [39419054](https://pubmed.ncbi.nlm.nih.gov/39419054/) | 2024 | Randomised trial | Lancet | Induction chemotherapy followed by standard chemoradiotherapy versus standard chemoradiotherapy alone in patie (India) | cited |
| 3 | [38048802](https://pubmed.ncbi.nlm.nih.gov/38048802/) | 2024 | Clinical trial | Lancet Oncol | Neoadjuvant chemotherapy plus camrelizumab for locally advanced cervical cancer (NACI study): a multicentre, s | read |
| 4 | [29432076](https://pubmed.ncbi.nlm.nih.gov/29432076/) | 2018 | Randomised trial | J Clin Oncol | Neoadjuvant Chemotherapy Followed by Radical Surgery Versus Concomitant Chemotherapy and Radiotherapy in Patie (India) | read |
| 8 | [31898673](https://pubmed.ncbi.nlm.nih.gov/31898673/) | 2019 | Clinical trial | J Cancer Res Ther | Locally advanced cervical cancer - neoadjuvant chemotherapy followed by concurrent chemoradiation and targeted (India) | read |
| 12 | [33387427](https://pubmed.ncbi.nlm.nih.gov/33387427/) | 2020 | Randomised trial | Pol Merkur Lekarski | Influence of neoadjuvant chemoradiotherapy for locally advanced cervical cancer. | read |
| 17 | [12576919](https://pubmed.ncbi.nlm.nih.gov/12576919/) | 2003 | Clinical trial | Am J Clin Oncol | Induction chemotherapy with gemcitabine and oxaliplatin for locally advanced cervical carcinoma. | read |
| 18 | [40139003](https://pubmed.ncbi.nlm.nih.gov/40139003/) | 2025 | Randomised trial | Eur J Cancer | Induction chemotherapy followed by chemoradiation in locally advanced cervical cancer: Quality of life outcome | cited |
| 2 | [38651760](https://pubmed.ncbi.nlm.nih.gov/38651760/) | 2024 | Review | Cancer | Top advances of the year: Cervical cancer. | read |
| 5 | [35325372](https://pubmed.ncbi.nlm.nih.gov/35325372/) | 2022 | Review | Radiol Med | Radiomics-based prediction of two-year clinical outcome in locally advanced cervical cancer patients undergoin | read |
| 7 | [30534016](https://pubmed.ncbi.nlm.nih.gov/30534016/) | 2018 | Review | Rep Pract Oncol Radiother | Neoadjuvant chemotherapy in woman with early or locally advanced cervical cancer. | read |
| 9 | [32878770](https://pubmed.ncbi.nlm.nih.gov/32878770/) | 2020 | Review | Anticancer Res | Neoadjuvant Chemotherapy in Locally Advanced Cervical Cancer: Review of the Literature and Perspectives of Cli | read |
| 19 | [11848519](https://pubmed.ncbi.nlm.nih.gov/11848519/) | 2001 | Review | Anticancer Res | Neoadjuvant chemotherapy and concurrent chemoradiation in the treatment of advanced cervical cancer. | read |
| 11 | [33622931](https://pubmed.ncbi.nlm.nih.gov/33622931/) | 2021 | Journal article | In Vivo | Response to Neoadjuvant Chemotherapy in Locally Advanced Cervical Cancer: The Role of Immune-related Factors. | read |
| 15 | [36641433](https://pubmed.ncbi.nlm.nih.gov/36641433/) | 2023 | Journal article | BMC Cancer | Neoadjuvant chemotherapy with weekly cisplatin and paclitaxel followed by chemoradiation for locally advanced  | cited |
| 16 | [27199522](https://pubmed.ncbi.nlm.nih.gov/27199522/) | 2016 | Journal article | Chin J Cancer Res | Neoadjuvant chemotherapy for locally advanced cervical cancer. | read |
| 20 | [39475968](https://pubmed.ncbi.nlm.nih.gov/39475968/) | 2024 | Journal article | PLoS One | Locally advanced cervical cancer: Neoadjuvant chemotherapy plus radical surgery an alternative approach to che | read |
| 6 | [40441923](https://pubmed.ncbi.nlm.nih.gov/40441923/) | 2025 | Comment or letter | Eur J Cancer | Letter Re: Induction chemotherapy followed by chemoradiation in locally advanced cervical cancer: Quality of l | not read: no abstract in PubMed |
| 10 | [40274459](https://pubmed.ncbi.nlm.nih.gov/40274459/) | 2025 | Comment or letter | Eur J Cancer | Letter comments on: "Induction chemotherapy followed by chemoradiation in locally advanced cervical cancer: Qu | not read: no abstract in PubMed |
| 13 | [40300942](https://pubmed.ncbi.nlm.nih.gov/40300942/) | 2025 | Comment or letter | Eur J Cancer | Response to letter Re: Induction chemotherapy followed by chemoradiation in locally advanced cervical cancer:  | not read: no abstract in PubMed |

| Check | Result |
|---|---|
| Cited papers in PubMed's search | 4 of 4 |
| Titles and years match NCBI esummary | 20 of 20 |
| Quotes found on the PubMed web page | 4 of 4 |
| PMIDs the model cited that were not given | 0 |
| Raw PubMed answers (SHA-256) | search e59a77b90202af4f, fetch d76505e74ff54498 |

## 4. Head and neck

**Question:** What did trials from India report about low-dose metronomic chemotherapy in head and neck cancer?

**Search words** (written by the model): `(metronomic chemotherapy OR low-dose chemotherapy) AND ("head and neck neoplasms" OR "head and neck cancer") AND (India OR Indian)`, all years. PubMed found **56** papers. [Open the same search on PubMed](https://pubmed.ncbi.nlm.nih.gov/?term=%28metronomic+chemotherapy+OR+low-dose+chemotherapy%29+AND+%28%22head+and+neck+neoplasms%22+OR+%22head+and+neck+cancer%22%29+AND+%28India+OR+Indian%29&sort=relevance)

**Answer** (each line with the exact words from the paper):

1. A randomized phase III trial in India found that triple metronomic chemotherapy (TMC) significantly improved survival outcomes compared to physician choice therapy in platinum-refractory head and neck cancer.
   - [PMID 40209850](https://pubmed.ncbi.nlm.nih.gov/40209850/), Abstract: "These results suggest that TMC significantly improves survival outcomes over physician choice therapy in platinum-refractory head and neck cancer."
2. A randomized phase III superiority study reported that adding low-dose nivolumab to triple metronomic chemotherapy improved 1-year overall survival from 16.3% to 43.4%.
   - [PMID 36265101](https://pubmed.ncbi.nlm.nih.gov/36265101/), RESULTS: "The addition of low-dose nivolumab led to an improvement in the 1-year OS from 16.3% (95% CI, 8.0 to 27.4) to 43.4% (95% CI, 30.8 to 55.3; hazard ratio, 0.545; 95% CI, 0.362 to 0.820; P = .0036)."
3. A retrospective analysis of 340 patients found that oral metronomic chemotherapy had promising results in selected cohorts, but dismal results for those who failed within 6 months of previous treatment.
   - [PMID 29199656](https://pubmed.ncbi.nlm.nih.gov/29199656/), CONCLUSION: "Oral metronomic chemotherapy has promising results when used in a selected cohort of patients but has dismal results in patients who failed within 6 months of previous treatment."

Dropped by the checks: "A retrospective analysis of 100 oral cancer patients with platinum-insensitive or early fa" (number 100 not in the quoted text)

**Papers** (20 fetched from PubMed, 15 read by the model):

| # | PMID | Year | Study type (PubMed) | Journal | Title | Read |
|---|---|---|---|---|---|---|
| 19 | [28533474](https://pubmed.ncbi.nlm.nih.gov/28533474/) | 2017 | Meta-analysis | Oncologist | Weekly Low-Dose Versus Three-Weekly High-Dose Cisplatin for Concurrent Chemoradiation in Locoregionally Advanc (India) | read |
| 20 | [29290286](https://pubmed.ncbi.nlm.nih.gov/29290286/) | 2018 | Meta-analysis | Oral Oncol | Altered fractionation radiotherapy combined with concurrent low-dose or high-dose cisplatin in head and neck c (India) | read |
| 1 | [36265101](https://pubmed.ncbi.nlm.nih.gov/36265101/) | 2023 | Randomised trial | J Clin Oncol | Low-Dose Immunotherapy in Head and Neck Cancer: A Randomized Study. (India) | cited |
| 4 | [29220295](https://pubmed.ncbi.nlm.nih.gov/29220295/) | 2018 | Randomised trial | J Clin Oncol | Once-a-Week Versus Once-Every-3-Weeks Cisplatin Chemoradiation for Locally Advanced Head and Neck Cancer: A Ph (India) | read |
| 7 | [41104574](https://pubmed.ncbi.nlm.nih.gov/41104574/) | 2026 | Clinical trial | Head Neck | A Real-World Phase IV Superiority Trial and Cost-Effectiveness Analysis of the Addition of Low-Dose Nivolumab  (India) | read |
| 15 | [40209850](https://pubmed.ncbi.nlm.nih.gov/40209850/) | 2025 | Randomised trial | Cancer Lett | Phase 3 randomized study of physician choice vs metronomic chemotherapy in platinum refractory/ineligible head (India) | cited |
| 8 | [34308772](https://pubmed.ncbi.nlm.nih.gov/34308772/) | 2022 | Review | J Chemother | Current status of systemic therapy in head and neck cancer. (India) | read |
| 10 | [31899993](https://pubmed.ncbi.nlm.nih.gov/31899993/) | 2020 | Review | Expert Rev Anticancer Ther | Palliative chemotherapy in head and neck cancer: balancing between beneficial and adverse effects. (India) | read |
| 11 | [34187268](https://pubmed.ncbi.nlm.nih.gov/34187268/) | 2021 | Review | Expert Opin Pharmacother | Advances in pharmacotherapy for head and neck cancer. (India) | read |
| 3 | [39220001](https://pubmed.ncbi.nlm.nih.gov/39220001/) | 2024 | Journal article | J Immunother Precis Oncol | Novel Effective Therapeutic Regimen for Recurrent/Metastatic Head and Neck Squamous Cell Cancer: Concurrent Tr (India) | not read: no abstract in PubMed |
| 5 | [29199656](https://pubmed.ncbi.nlm.nih.gov/29199656/) | 2017 | Journal article | Indian J Cancer | Retrospective analysis of palliative metronomic chemotherapy in head and neck cancer. (India) | cited |
| 12 | [27275447](https://pubmed.ncbi.nlm.nih.gov/27275447/) | 2016 | Journal article | South Asian J Cancer | Metronomic palliative chemotherapy in maxillary sinus tumor. (India) | read |
| 13 | [32719267](https://pubmed.ncbi.nlm.nih.gov/32719267/) | 2020 | Observational study | J Cancer Res Ther | Metronomic palliative chemotherapy in locally advanced, recurrent and metastatic head-and-neck cancer: A singl (India) | read |
| 16 | [26855524](https://pubmed.ncbi.nlm.nih.gov/26855524/) | 2015 | Journal article | Indian J Med Paediatr Oncol | Metronomic chemotherapy in platinum-insensitive failures and/or early failures postmultimodality management in (India) | read |
| 17 | [34708450](https://pubmed.ncbi.nlm.nih.gov/34708450/) | 2022 | Observational study | Head Neck | Role of metronomic therapy for advanced oral cancers and predictors of response: Multi-institutional feasibili (India) | read |
| 18 | [41062634](https://pubmed.ncbi.nlm.nih.gov/41062634/) | 2025 | Journal article | Sci Rep | Low-dose nivolumab plus induction chemotherapy for locally advanced or unresectable head and neck cancer is as (India) | read |
| 2 | [33338456](https://pubmed.ncbi.nlm.nih.gov/33338456/) | 2021 | Comment or letter | Lancet Glob Health | Oral metronomic therapy in head and neck cancer - Authors' reply. (India) | not read: no abstract in PubMed |
| 6 | [33338455](https://pubmed.ncbi.nlm.nih.gov/33338455/) | 2021 | Comment or letter | Lancet Glob Health | Oral metronomic therapy in head and neck cancer. (India) | not read: no abstract in PubMed |
| 9 | [33338454](https://pubmed.ncbi.nlm.nih.gov/33338454/) | 2021 | Comment or letter | Lancet Glob Health | Oral metronomic therapy in head and neck cancer. (India) | not read: no abstract in PubMed |
| 14 | [37742471](https://pubmed.ncbi.nlm.nih.gov/37742471/) | 2023 | Comment or letter | Oral Oncol | Oral metronomic therapy as a resource-adaptive palliative strategy for recurrent/metastatic head and neck squa (India) | not read: no abstract in PubMed |

| Check | Result |
|---|---|
| Cited papers in PubMed's search | 3 of 3 |
| Titles and years match NCBI esummary | 20 of 20 |
| Quotes found on the PubMed web page | 3 of 3 |
| PMIDs the model cited that were not given | 0 |
| Raw PubMed answers (SHA-256) | search 9c098e7fe3c676be, fetch 172bbceceb38448b |

_From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for any patient._
