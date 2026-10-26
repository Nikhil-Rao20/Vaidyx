# Cancer checklists research, part 1: GI and thoracic

Files read (all under `/data/vaidyx/tb_resources/guidelines/ncg_india/`): `management-of-colorectal-cancer.pdf` (4 pages, the colon flow), `ncg-rectal-cancer.docx` (rectal only, for the comparison), `ncg-gi-draft-2021-gastric-cancer.pdf` (2 pages), `ncg-guidelines-for-thoracic-cancer-2019.pdf` (40 pages; oesophagus on pages 16 to 20 and 28 to 31), `ncg-gi-hepatocellular-carcinoma.docx`, `ncg-gi-draft-2021-gall-bladder-cancer.pdf` (7 pages) and `ncg-gi-draft-2021-gallbladder-cancer-radiology-synoptic.pdf` (2 pages). Text was cached in `/data/vaidyx/night-v3/research_text/`. Page numbers are PDF page index + 1; for the thoracic book this equals the printed Page n of 40. The two GI Word files have no pages, so they carry n/a with a "where" heading. Records proposed: colon 11, stomach 13, oesophagus 9, liver (HCC) 15, gallbladder 11. Only the thoracic book (oesophagus flow) and the HCC file print tier marks; the colon, stomach and gallbladder files print none, so those tiers are proposed with a stated basis. In the HCC file the key reads "Normal font- Essential, Underlined -desirable, italics- optional"; the formatting was read from the Word runs (underlined means b, italics means c). The page 16 oesophagus flow chart shows no history, endoscopy or biopsy boxes in its text layer (only a logo image), so those three records have a proposed tier and a weaker source (see open questions). Existing departments missing from the hospital list (GI Oncology, Medical Gastroenterology) are not used: endoscopy goes to Gastrointestinal Surgery.

## Colon cancer (`colorectal_colon`)
### Source
`management-of-colorectal-cancer.pdf`, NCG Gastrointestinal Malignancies, no year printed (the file is the NCG colon and rectum flow). Colon work-up, staging and treatment are on page 2 (work-up, non-metastatic and metastatic flow, adjuvant), page 3 (limited metastatic disease), page 4 (surveillance, Appendices A and B). `ncg-rectal-cancer.docx` covers the rectum only (its heading is "RECTAL CANCER (adenocarcinoma)"); colon is not in it. The existing `colorectal_rectum.json` already borrows the MMR and RAS/BRAF records from this colon PDF (pages 2 and 4).

How NCG splits the disease (page 2): "Non-metastatic" with "(any T, any N, M0)", and "Metastatic disease", the latter divided into "Limited metastatic disease" ("(some potential for cure)") and disseminated metastasis (unfit or unwilling for aggressive treatment, no potential for cure). Page 3 sub-divides limited disease into asymptomatic or symptomatic primary with resectable or borderline resectable/ unresectable metastasis.

### Settings proposed
- `non_metastatic`: 'Non-metastatic (no distant disease recorded)', as recorded. Basis: page 2 "(any T, any N, M0)".
- `metastatic`: 'Metastatic (distant disease recorded)', as recorded, limited and disseminated together because the work-up is the same. Basis: page 2 "Metastatic disease" and "Limited metastatic disease". Same two ids as `colorectal_rectum`.

### Work-up records
Tiers for all rows are proposed: NCG prints no a/b/c letters in this file. Basis for a: the item sits in the "Workup:" list of page 2. Basis for c: NCG says optional, "not routinely", or "may be ordered".

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history and performance status | non_metastatic a, metastatic a | clinical_note, referral | owner | ecog, clinical_question | 2 | "Nutritional support for severely malnourished" | Colon page has no history item; carried over from the rectal record and proposed a (the board needs the question and ECOG). The quote is the only clinical-status line in the colon work-up |
| colonoscopy | Colonoscopy report | non_metastatic a, metastatic a | endoscopy | Gastrointestinal Surgery | NEW:tumour_site_colon | 2 | "Workup: Complete colonoscopy with multiple (8 or more) biopsies" | a, in the Workup list. Rectal record needs the distance from the anal verge; colon needs the segment instead |
| histopathology | Histopathology report (biopsy) | non_metastatic a, metastatic a | histopathology | Pathology | histologic_type, grade | 2 | "Workup: Complete colonoscopy with multiple (8 or more) biopsies" | a, implied by the biopsies |
| resection_histopathology | Histopathology of the resected colon | non_metastatic a, metastatic none | histopathology | Pathology | histologic_type, grade, lvi, pni, margins, recorded_stage, NEW:nodes_examined | 2 | "dHigh risk includes inadequate nodal sampling(< 12 nodes), pT4 stage, perforation - (major); poorly differentiated tumors, LVI/PNI, obstruction." | Proposed a after surgery (post-board record): the adjuvant box needs pT, N, nodes, grade, LVI/PNI |
| cea | Serum CEA | non_metastatic a, metastatic a | lab | Biochemistry | cea | 2 | "Serum CEA" | a, in the Workup list |
| cect_abdomen_pelvis_chest | CECT abdomen and pelvis; CECT chest or chest X-ray | non_metastatic a, metastatic a | ct, xray | Radiology | distant_findings, nodal_findings, lesion_size | 2 | "CECT scan abdomen and pelvis; CECT chest or Chest X-raya" | a, in the Workup list. Footnote a: "aA chest X-ray is an acceptable alternative to CT chest since there is no clear evidence to favour the latter." |
| pet_ct | PET-CT (select indications only) | non_metastatic c, metastatic c | pet_ct | Nuclear Medicine | (none) | 2 | "PET-CT is not routinely advicedb" | c: NCG limits it to three scenarios (footnote b: "bPET-CT may be ordered ina)those with limited metastatic disease in liver and being planned for potentially curative treatment") |
| mri_liver | MRI liver (problem solving) | non_metastatic c, metastatic c | mri | Radiology | distant_findings | 2 | "Optional- MRI can be problem solving for" | c, NCG writes "Optional" |
| mmr | MMR / MSI status | non_metastatic b, metastatic a | histopathology, ihc, molecular | Pathology | mmr | 2 | "Stage II (pT3-4,N0): MSI testing indicated" | Differs from the rectum record (c / a): for colon NCG says "indicated" for stage II, so b (only one sub-group); metastatic a from "Check for RAS, BRAF and MSI status" |
| ras_braf | RAS / BRAF | non_metastatic none, metastatic a | molecular, histopathology | Pathology | ras_braf | 4 | "Determine the MSI status, mutation status in" | Differs from the rectum record (c / a): colon flow asks only in metastatic disease, so none for non-metastatic |
| her2 | HER2 amplification (metastatic) | non_metastatic none, metastatic b | ihc, molecular | Pathology | her2 | 4 | "Determine the MSI status, mutation status in" | New for colon (not in the rectum file); named once in Appendix B, so proposed b |
| restaging_ct | Restaging CT abdomen and pelvis | non_metastatic none, metastatic c | ct | Radiology | distant_findings | 2 | "CT Abdomen and Pelvis with/ without CT Angiography may be used" | c: "for restaging after therapy in advanced disease"; "may be used" |
| mdt_discussion | Multidisciplinary meeting discussion | non_metastatic none, metastatic a | tumour_board_record | MDT Coordinator | clinical_question | 2 | "(DISCUSS IN MULTIDISCIPLINARY MEETING," | a for metastatic from the same box; for non-metastatic the colon flow says nothing (rectal docx says "All patients need to be evaluated by a Multidisciplinary team"), so none here |

Counting the clinical_history row, the table has 12 rows; 11 are required records and `restaging_ct` and `mri_liver` are optional.

Carried over from `colorectal_rectum.json` unchanged: clinical_history (department changes from GI Oncology to owner), histopathology, cea, pet_ct (c), the systemic staging CT record (colon says abdomen AND pelvis, rectum only abdomen). Differ: mmr and ras_braf tiers (above); `endoscopy` loses `distance_from_anal_verge`; `baseline_mri_pelvis` has no colon equivalent (no pelvic MRI in the colon flow); `restaging_mri` has no colon equivalent; digital rectal examination and rigid sigmoidoscopy (rectal docx, "Workup: Digital rectal examination (and rigid sigmoidoscopy if available)") do not apply to colon. The rectal protocol's `site` string already contains colon|sigmoid|colorectal, so the two protocols will overlap on site words (open question).

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| tumour_site_colon | Colon segment of the tumour | categorical: caecum, ascending colon, hepatic flexure, transverse colon, splenic flexure, descending colon, sigmoid colon | endoscopy, ct | Not quoted in the colon flow; appropriate colectomy with complete mesocolic excision depends on the segment (page 2) |
| nodes_examined | Lymph nodes examined | number (count) | histopathology | "inadequate nodal sampling(< 12 nodes)" (page 2) |
| obstruction_perforation | Obstruction or perforation | categorical: present, absent, not stated | ct, operative_note, clinical_note | "perforation - (major)" and "obstruction" in the high risk list (page 2). Optional; may be left out |

### Staging system
The colon flow gives pT and N groups but names no AJCC or UICC edition: "Stage I (pT1-2,N0): no adjuvant therapy", "Stage II (pT3-4,N0): MSI testing indicated" (page 2, lines as printed in the adjuvant box). The system only records the stage as written.

### Indian notes
Page 2 footnote a gives the resource-level alternative: "aA chest X-ray is an acceptable alternative to CT chest since there is no clear evidence to favour the latter." Page 4: "If MSI H or dMMR,  immunotherapy with" (treatment content, listed only to show the book links MSI to therapy). No PM-JAY, ICMR or ICRI remark found in this file.

### Regimen or dose tables
Page 2 (adjuvant regimens in the adjuvant box and footnotes c to e), page 3 (limited metastatic pathways), page 4 (Appendix A and Appendix B systemic therapy; no doses printed). Surveillance schedule: page 4.

### Open questions
- Whether the board wants limited and disseminated metastatic as separate settings (page 2 splits them); the work-up is identical, so two settings were kept.
- Overlap of site words between `colorectal_rectum` and `colorectal_colon`.
- No quoted line for the clinical history record; it relies on carry-over from the rectum protocol.
- The page 2 flow is graphic; text order in the extraction is jumbled, so quotes were taken from lines that read cleanly.

## Stomach cancer (`stomach`)
### Source
`ncg-gi-draft-2021-gastric-cancer.pdf`, NCG GI draft, 2021 (from the file name; no date is printed in the text). Page 1: flow chart with work-up, settings, surgery, perioperative and palliative therapy. Page 2: role of PET, CDH1 testing, screening, endoscopy, EUS, surveillance. No a/b/c letters are printed; the only marks are "(O)" on some drugs.

Settings as printed on page 1: "Early, Localized" with "(T1-2, N0)"; "Loco-regionally advanced" with "T3-4, N+ve"; "Metastatic Diseasea" with "Any T, any N, M1".

### Settings proposed
- `early_localized`: 'Early, localized (as recorded)'. Basis: page 1 "(T1-2, N0)".
- `locally_advanced`: 'Loco-regionally advanced (as recorded)'. Basis: page 1 "T3-4, N+ve".
- `metastatic`: 'Metastatic (as recorded)'. Basis: page 1 "Any T, any N, M1".

### Work-up records
All tiers proposed: the file prints none. Basis a: the item is in the page 1 work-up block.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history and performance status | early a, locally advanced a, metastatic a | clinical_note, referral | owner | ecog, presenting_complaint, clinical_question | 1 | "Symptoms :Dyspepsia Pain, Bleeding, Vomiting, Lumps, Unexplained weight" | a, listed first in the work-up; "Poor PS/ ASA 4" also routes treatment |
| upper_gi_endoscopy | Upper GI endoscopy with biopsies | early a, locally advanced a, metastatic a | endoscopy | Gastrointestinal Surgery | NEW:tumour_site_stomach | 1 | "Upper GI Endoscopy with multiple biopsies(6-8)" | a, in the work-up block |
| histopathology | Histopathology report | early a, locally advanced a, metastatic a | histopathology | Pathology | histologic_type, grade | 1 | "Pathology : Adenocarcinoma." | a, in the work-up block |
| cect_tap | CECT thorax, abdomen and pelvis | early a, locally advanced a, metastatic a | ct | Radiology | lesion_size, nodal_findings, distant_findings | 1 | "CECT scan thorax, abdomen and pelvis" | a, in the work-up block |
| eus | Endoscopic ultrasonography | early b, locally advanced b, metastatic none | endoscopy | Gastrointestinal Surgery | recorded_stage | 2 | "EUS is desirable in patients with resectable disease to determine precise T and N stage" | b: "desirable" is the book's Optimal wording; it also appears as "Endoscopic ultrasonography" on page 1 |
| staging_laparoscopy | Staging laparoscopy | early none, locally advanced b, metastatic none | operative_note | Surgical Oncology | distant_findings | 1 | "Staging Laparoscopy if CT s/o no mets if Periop chemo is planned" | b: conditional on perioperative chemotherapy being planned; proposed |
| her2 | HER2 testing | early none, locally advanced c, metastatic b | ihc, histopathology, molecular | Pathology | her2 | 1 | "Consider Her 2 testing" | "Consider" means not required; proposed c for locally advanced, b for metastatic where "Her2 neu positive" changes the first line |
| pdl1 | PD-L1 (third line) | early none, locally advanced none, metastatic c | ihc, histopathology | Pathology | pdl1 | 1 | "Test PDL1" | c: appears only under third-line, immunotherapy marked "(O)" |
| cdh1_testing | CDH1 germline testing (selected patients) | early a, locally advanced a, metastatic a | molecular | Medical Genetics | NEW:cdh1_result | 2 | "Testing for CDH1 mutation is essential in:" | a only under NCG's conditions, e.g. "Patient with diffuse gastric cancer under the age of 40." The system never judges the condition: the record is shown only |
| pre_anaesthetic | Pre-anaesthetic evaluation | early b, locally advanced b, metastatic none | clinical_note | owner | comorbidities | 1 | "Pre-anesthetic evaluation" | b: listed in the work-up with no letter; relevant only if surgery is planned; proposed |
| nutrition | Nutrition and supportive care evaluation | early b, locally advanced b, metastatic b | clinical_note | Palliative Medicine | (none) | 2 | "Early supportive care team and nutrition evaluation is encouraged in all cases" | b: "encouraged"; also page 1 "Nutritional support-Oral or tube feeding" |
| mdt_discussion | Multidisciplinary Tumour board | early a, locally advanced a, metastatic a | tumour_board_record | MDT Coordinator | clinical_question | 1 | "Multidisciplinary Tumour board" | a, in the work-up block |
| resection_histopathology | Histopathology of the gastrectomy | early a, locally advanced a, metastatic none | histopathology | Pathology | histologic_type, grade, margins, recorded_stage, NEW:nodes_examined | 1 | "D2 Dissection ( More than15 nodes)" | Proposed a after surgery (post-board record): adjuvant choice depends on pT, N and margins ("D1 dissection or margins positive") |

PET: page 2 says "Role of PET Scan: PET scan should NOT be performed in gastric cancer." Proposed as a do not order note, no PET record (tier none for all settings).

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| tumour_site_stomach | Site in the stomach | categorical: GE junction, cardia, fundus, body, antrum, pylorus | endoscopy | the stenting box names GE junction and pylorus (page 1, "Endoscopic Stenting if") |
| nodes_examined | Lymph nodes examined (shared with colon) | number (count) | histopathology | "D2 Dissection ( More than15 nodes)" (page 1) |
| cdh1_result | CDH1 mutation result | categorical: detected, not detected, not tested | molecular | "Testing for CDH1 mutation is essential in:" (page 2) |

### Staging system
No staging system or edition is named; the book uses TNM letters only ("(T1-2, N0)", "T3-4, N+ve", "Any T, any N, M1", page 1). Nothing computed.

### Indian notes
Page 1 uses "Poor PS/ ASA 4" and a tertiary-centre note on page 2: "EMR and follow up should be performed at tertiary care centres." No PM-JAY or ICMR line found.

### Regimen or dose tables
Page 1 only: perioperative regimens (FLOT, EOX, FOLFOX/CAPOX), palliative lines, adjuvant chemoradiotherapy with a capecitabine dose and RT dose. No other tables.

### Open questions
- MMR / MSI is not in the stomach file; whether to add it from outside NCG.
- Whether "desirable" and "encouraged" should map to b (assumed).
- Page 1 is a flow chart with jumbled extraction; which box a line belongs to (for example "Consider Her 2 testing") is inferred from the layout.

## Oesophageal cancer (`oesophagus`)
### Source
`ncg-guidelines-for-thoracic-cancer-2019.pdf`, NCG Thoracic Malignancies Management Guidelines 2019. Oesophagus: page 16 (management flow, with a/b/c letters), pages 17 to 20 (procedures, radiotherapy and chemotherapy tables), page 21 (abbreviations), pages 28 to 31 (pathology synoptic "RESECTIONS OF OESOPHAGEAL TUMOURS"). The book's radiology synoptic annexure (pages 22 to 25) has no oesophagus form (searched).

The page 16 flow splits disease by: "Early, Localized (T1, 2, N0, on", "Loco-regionally advanced-T3, 4 or N+ve" and "Metastatic disease" with "Any T, any N, M1".

### Settings proposed
- `early_localized`: 'Early, localized (as recorded)'. Basis: page 16 "Early, Localized".
- `locally_advanced`: 'Loco-regionally advanced (as recorded)'. Basis: page 16 "Loco-regionally advanced-T3, 4 or N+ve".
- `metastatic`: 'Metastatic (as recorded)'. Basis: page 16 "Any T, any N, M1".

### Work-up records
Tier letters are NCG's where a letter is quoted; proposed rows state the basis.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history and performance status | early a, locally advanced a, metastatic a | clinical_note, referral | owner | ecog, presenting_complaint, clinical_question | 4 | "Performance status; General and systemic examination" | Page 4 is the lung chapter's work-up line; the oesophagus page 16 text layer carries no history box. Proposed a, same as the lung protocol |
| histopathology | Biopsy and histopathology report | early a, locally advanced a, metastatic a | histopathology | Pathology | histologic_type, grade | 16 | "Squamous cell carcinoma" | The flow splits therapy by "Squamous cell carcinoma" and "Adenocarcinoma", so the type must be recorded; proposed a |
| upper_gi_endoscopy | Upper GI endoscopy report | early a, locally advanced a, metastatic a | endoscopy | Gastrointestinal Surgery | NEW:tumour_location_oesophagus | 28 | "d. Tumor/Lesion location: Gastro-oesophageal junction/Lower third/Middle third/Upper third" | Proposed a; the book prints no endoscopy box in the extracted text, location is the synoptic field |
| cect_staging | CECT lower neck, thorax, abdomen (pelvis for GE junction) | early a, locally advanced a, metastatic a | ct | Radiology | lesion_size, nodal_findings, distant_findings | 16 | "CECT scan lower neck, thorax, abdomen (pelvis" | (a) on the page |
| bronchoscopy | Bronchoscopy (upper and middle third, or voice change) | early b, locally advanced b, metastatic none | endoscopy | Pulmonology | (none) | 16 | "Bronchoscopy (upper and middle third or H/o" | (b) on the page; conditional on site or voice history |
| pet_cect | PET-CECT | early b, locally advanced b, metastatic b | pet_ct | Nuclear Medicine | suv_max, distant_findings | 16 | "PET-CECT(b)" | (b) on the page |
| eus | Endoscopic ultrasonography | early c, locally advanced c, metastatic none | endoscopy | Gastrointestinal Surgery | recorded_stage | 16 | "Endoscopic ultrasonography (EUS)(c) for" | (c), under "Optional Procedures- C", for borderline operable or early T1, T2, N0 |
| staging_laparoscopy | Staging laparoscopy | early none, locally advanced b, metastatic none | operative_note | Surgical Oncology | distant_findings | 16 | "If Siewart type II/III- Staging laparoscopy(b)" | (b); only for Siewert II/III adenocarcinoma and poorly differentiated tumours (condition not judged by the system) |
| her2 | HER2 (metastatic adenocarcinoma) | early none, locally advanced none, metastatic c | ihc, histopathology | Pathology | her2 | 16 | "Her2 positive" | (c) on the page: the letter is printed on the next line, a treatment line that is not quoted here; the record is the HER2 test only |
| restaging_ct | Re-evaluation CT after neoadjuvant therapy | early none, locally advanced a, metastatic none | ct | Radiology | lesion_size, distant_findings | 16 | "Followed by reevaluation with CECT(a)" | (a) on the page |
| resection_histopathology | Histopathology of the oesophagectomy | early a, locally advanced a, metastatic none | histopathology | Pathology | histologic_type, grade, lvi, pni, margins, recorded_stage | 30 | "Margin type  Involved by invasive carcinoma," | Proposed a after surgery (post-board record): the adjuvant box depends on margins ("R+ resection(a)") and pT/pN; synoptic fields on pages 29 to 31 |

Also on page 16 and proposed as an optional note record: the page 16 line on referral to palliative care guidelines for dysphagia (metastatic; Palliative Medicine; clinical_note; tier c proposed). Not counted above.

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| tumour_location_oesophagus | Tumour location | categorical: upper third, middle third, lower third, GE junction | endoscopy, ct, histopathology | "Tumor/Lesion location: Gastro-oesophageal junction/Lower third/Middle third/Upper third" (page 28) |
| siewert_type | Siewert type (as recorded) | categorical: I, II, III, not stated | endoscopy, ct, operative_note | "If Siewart type II/III- Staging laparoscopy(b)" (page 16) |
| trg | Tumour regression grade | text (Mandard or Modified Ryan, as written) | histopathology | "Tumour regression grade (TRG) should be recorded using either Mandard(5 Tier" (page 30) |

### Staging system
Page 31 (pathology synoptic): "Pathology stage (8th AJCC staging system):  p/ypTNM". Also page 30 pT categories (pT0 to pT4) and pN0 to pN3. 8th AJCC is the only edition named. Vaidyx never computes it.

### Indian notes
No India-specific, resource or PM-JAY line found in the oesophagus pages. Page 20 gives an eligibility footnote for cisplatin (treatment content, listed by page only).

### Regimen or dose tables
Pages 17 (surgery types, radiation doses, concurrent chemotherapy), 18, 19 and 20 (neoadjuvant, definitive and metastatic regimens, cisplatin ineligibility footnote on page 20).

### Open questions
- The page 16 text layer shows no history, endoscopy or biopsy boxes; the flow chart may carry them as drawn shapes. Please check the printed page.
- Whether `tumour_location_oesophagus` can be satisfied from the endoscopy report (the book's wording sits in the pathology synoptic).
- GE junction tumours may be better covered by the stomach protocol; the book places Siewert II/III in the oesophagus flow.

## Liver cancer, hepatocellular carcinoma (`liver_hcc`)
### Source
`ncg-gi-hepatocellular-carcinoma.docx`, NCG GI guideline, no year printed. Page n/a for all rows. Where: "Hepatocellular carcinoma" flow chart (work-up list at the top, treatment branches below), then the "KEY" line and "NOTES" paragraphs, then "Surveillance". Key line: "KEY – Normal font- Essential, Underlined -desirable, italics- optional" (the printed key uses an en dash after KEY; the quoted part below is exact): "Normal font- Essential, Underlined -desirable, italics- optional". The formatting of each work-up item was read from the Word runs: underlined items are desirable (b), italic items optional (c), the rest essential (a).

How NCG splits the disease: by liver function and spread, "Good Liver Function(Childs A/ B)" and "Poor liver function (Child C)"; "Resectable tumour (adequate FLR)"; "Multiple/ bilobar tumours,  Inadequate FLR, No extra hepatic disease"; "Extra hepatic disease".

### Settings proposed
- `resectable`: 'Resectable tumour, adequate FLR (as recorded)'. Basis: "Resectable tumour (adequate FLR)" under "Curative treatment options".
- `locoregional`: 'Multiple or bilobar tumour, inadequate FLR, no extrahepatic disease (as recorded)'. Basis: "Multiple/ bilobar tumours,  Inadequate FLR, No extra hepatic disease".
- `extrahepatic`: 'Extrahepatic disease (as recorded)'. Basis: "Extra hepatic disease". Child C (poor liver function) is not a separate setting: it is recorded as a Child class fact; the book routes it to "Best supportive care" or transplant.

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history and performance status | resectable a, locoregional a, extrahepatic a | clinical_note, referral | owner | ecog, presenting_complaint, clinical_question | n/a | "Right upper Quadrant pain/mass, Jaundice, Nausea, weight loss, symptoms related to metastasis" | Proposed a: first lines of the flow (presentation); where: top of the flow chart |
| triphasic_cect | Triphasic CECT abdomen and pelvis | all a | ct | Radiology | lesion_size, nodal_findings, NEW:lirads_category | n/a | "Triphasic CECT Abdomen and pelvis" | a (normal font); where: work-up list |
| mri_liver | Gadolinium MRI abdomen (cirrhotic or suspected cirrhotic) | all b | mri | Radiology | lesion_size, NEW:lirads_category | n/a | "Gadolinium enhanced MRI scan abdomen (in cirrhotics and suspected cirrhotic patients)" | b (underlined = desirable); where: work-up list |
| blood_counts_liver_function | CBC, liver function tests, PT/INR | all a | lab | Biochemistry | haemoglobin, platelets, bilirubin, NEW:inr | n/a | "CBC , Liver function tests, PT/INR HBSAg" | a (normal font); where: work-up list |
| hepatitis_serology | HBsAg and anti-HCV | all a | lab | Microbiology | NEW:hbsag, NEW:anti_hcv | n/a | "CBC , Liver function tests, PT/INR HBSAg" | a (normal font); a second note says: "If HbsAg +ve screen family and treat/vaccinate" |
| hbv_core_antibody | HBV total core antibody | all c | lab | Microbiology | NEW:hbv_core_ab | n/a | "HBV Total Core Ab" | c (italic = optional) |
| afp | Alpha fetoprotein | all a | lab | Biochemistry | NEW:afp | n/a | "Alfa feto protein" | a (normal font) |
| pivka | PIVKA | all c | lab | Biochemistry | NEW:pivka | n/a | "PIVKA" | c (italic = optional) |
| child_bclc_recorded | Child score and BCLC / HKLC as recorded | all a | clinical_note, tumour_board_record | Hepatobiliary and Pancreatic Surgery | NEW:child_pugh_class, recorded_stage | n/a | "Child and HKLC/BCLC scoring" | a (normal font); the system records what the report states and never computes |
| varices_endoscopy | Endoscopy for varices | resectable a, locoregional a, extrahepatic a | endoscopy | Gastrointestinal Surgery | NEW:varices_finding | n/a | "Endoscopy for varices" | a (normal font) |
| hvpg | HVPG | resectable c, locoregional none, extrahepatic none | other | Hepatobiliary and Pancreatic Surgery | NEW:hvpg_mmhg | n/a | "Endoscopy for varices, HVPG" | c (italic = optional). The notes tie it to resection: "no varices or HVPG < 10 mmHg" |
| chest_ct | CT chest (metastatic work-up for curative treatment) | resectable a, locoregional c, extrahepatic a | ct | Radiology | distant_findings | n/a | "Metastatic workup if curative treatment : CT Scan chest," | a (normal font) when curative treatment is planned; locoregional c and extrahepatic a proposed |
| flr_measurement | Future liver remnant measurement | resectable a, locoregional b, extrahepatic none | ct | Radiology | NEW:flr_percent | n/a | "Measurement of FLR (functional Liver Remnant) for major resections" | a (normal font) if surgical; locoregional b proposed because "Inadequate FLR" can be reassessed with PVE |
| biopsy | Image-guided biopsy (conditional) | all c | histopathology, cytology | Pathology | histologic_type | n/a | "US / CT guided Biopsy only LIRADS 4 and AFP< 400ng/mL" | NCG a (normal font) but only under the condition; proposed c because the book diagnoses by imaging and biopsies selectively. The system never judges LIRADS or AFP conditions |
| nutrition_supportive | Nutritional evaluation and supportive care | all b | clinical_note | owner | (none) | n/a | "Nutritional evaluation and supportive care for liver disease" | NCG a (normal font); proposed b because no result can be checked |
| mdt_discussion | Multidisciplinary team decision | resectable a, locoregional a, extrahepatic a | tumour_board_record | MDT Coordinator | clinical_question | n/a | "The decision should be taken by a multidisciplinary team." | Proposed a, from the ablation note |

PET: "FDG PET CT has no role in routine evaluation or follow up of HCC" (NOTES), so no PET record; none for all settings. Screening line: "A 6 monthly ultrasonography and AFP is recommended by the APASL."

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| lirads_category | LI-RADS category (as reported) | categorical: LR-1 to LR-5, LR-M, LR-TIV, not stated | ct, mri | "The LIRADS score should be followed." |
| inr | PT / INR | number (ratio) | lab | "PT/INR" |
| hbsag | HBsAg | categorical: positive, negative | lab | "HBSAg" |
| anti_hcv | HCV antibody | categorical: positive, negative | lab | "HCV" |
| hbv_core_ab | HBV total core antibody | categorical: positive, negative | lab | "HBV Total Core Ab" |
| afp | Alpha fetoprotein | number (ng/mL) | lab | "Alfa feto protein", and "AFP > 1000 ng/mL is usually a contraindication for transplant" |
| pivka | PIVKA | number (mAU/mL) | lab | "PIVKA" |
| child_pugh_class | Child class as recorded | categorical: A, B, C, not stated | clinical_note, lab | "Good Liver Function(Childs A/ B)" |
| varices_finding | Oesophageal or gastric varices | categorical: present, absent, not stated (grade as text) | endoscopy | "Endoscopy for varices" |
| hvpg_mmhg | HVPG | number (mmHg) | other | "HVPG < 10 mmHg" |
| flr_percent | Future liver remnant | number (percent) | ct | "FLR > 30%" |

### Staging system
The book names Child, HKLC and BCLC: "Child and HKLC/BCLC scoring"; BCLC is cited in the references ("the BCLC staging classification"); transplant uses Milan criteria: "Milan criteria (Single tumour < 5cm or not > 3 tumours each < 3cm in diameter)". Imaging is scored by LIRADS. No AJCC edition is named. The system never computes any of these.

### Indian notes
"These are currently not cost effective in India." (about sorafenib and lenvatinib, NOTES). Reference: "Cost-effectiveness of Sorafenib for Treatment of Advanced Hepatocellular Carcinoma in India." Hepatitis B and C: "Patients with Hepatitis B and C will need evaluation and treatment for the virus in addition". No PM-JAY mention.

### Regimen or dose tables
n/a (Word file, no pages). The only dose line is in the NOTES paragraph on targeted agents (pointer only, the dose is not copied). Treatment branches: the flow chart under "Curative treatment options" and "Surveillance".

### Open questions
- Underline and italic marks were read from the Word runs; a few runs in the flow chart may be styled in ways the key does not describe.
- NEW:child_pugh_class is a Child class as written in the report; confirm with a clinician that no recording of sub-scores is wanted.
- Whether a separate poor liver function setting is wanted.
- Hepatoblastoma (children) is in the paediatric book, not here.

## Gallbladder cancer (`gallbladder`)
### Source
`ncg-gi-draft-2021-gall-bladder-cancer.pdf`, "NCG DRAFT GUIDELINES 15 Jan 2021". Page 1: basic work-up and the four-way split; page 2: per primum GBC; page 3: incidental GBC; page 4: locally advanced GBC (work-up, staging, drainage); page 5: metastatic GBC; pages 6 and 7: references. `ncg-gi-draft-2021-gallbladder-cancer-radiology-synoptic.pdf`, same date, 2 pages: radiology report elements (page 1 gallbladder mass, bile ducts, vessels; page 2 nodes and distant metastases). No a/b/c letters are printed; the only marks are "Optional:" and "(optimal)".

How NCG splits the disease: page 1 lists "PER -PRIMUM", "INCIDENTAL GALL", "LOCALLY ADVANCED" and "METASTATIC".

### Settings proposed
- `per_primum`: 'Per primum, suspected or proven before surgery (as recorded)'. Basis: page 2 "1. PER PRIMUM GBC".
- `incidental`: 'Incidental, found after cholecystectomy (as recorded)'. Basis: page 3 "2. INCIDENTAL GBC (iGBC)".
- `locally_advanced`: 'Locally advanced (as recorded)'. Basis: page 4 "3. LOCALLY ADVANCED GBC (LAGBC)".
- `metastatic`: 'Metastatic (as recorded)'. Basis: page 5 "4. METASTATIC GBC".

### Work-up records
All tiers proposed (no letters). Basis a: listed under "BASIC WORK UP" on page 1 without "Optional".

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history, jaundice and performance status | per primum a, incidental a, locally advanced a, metastatic a | clinical_note, referral | owner | ecog, presenting_complaint, clinical_question | 1 | "BASIC WORK UP" | Proposed a: the page 1 heading is the only clinical line; "In patients presenting with OJ:" (page 4) adds jaundice |
| ultrasonography | Ultrasonography | per primum a, incidental b, locally advanced a, metastatic a | ultrasound | Radiology | NEW:gb_mass, lesion_size | 1 | "Ultrasonography" | a, in the basic work-up; incidental b because the cholecystectomy is already done |
| liver_function | Liver function tests | per primum a, incidental a, locally advanced a, metastatic a | lab | Biochemistry | bilirubin | 1 | "Blood Investigations:  Liver function tests" | a, in the basic work-up |
| ca19_9 | CA 19-9 | all a | lab | Biochemistry | NEW:ca19_9 | 3 | "Repeat all labs + Tumour marker CA 19-9" | a, basic work-up (page 1); page 3 repeats it for incidental disease |
| baseline_blood | CBC and creatinine | per primum none, incidental a, locally advanced a, metastatic none | lab | Biochemistry | haemoglobin, platelets, creatinine | 4 | "CBC Creatinine, CA 19-9, LFT" | a for locally advanced (page 4); incidental repeats "all labs" (page 3) |
| cect_cap | CECT chest, abdomen and pelvis | all a | ct | Radiology | lesion_size, nodal_findings, distant_findings, NEW:vessel_involvement, NEW:bile_duct_involvement | 1 | "CECT Scan of Chest Abdomen and pelvis" | a, in the basic work-up; page 3: "Complete metastatic work up: CT Chest abdomen pelvis / PET CT if presenting after 6 weeks" |
| histopathology | Biopsy, FNA or post-cholecystectomy histopathology | per primum b, incidental a, locally advanced a, metastatic a | histopathology, cytology | Pathology | histologic_type, margins, recorded_stage | 4 | "Obtaining tissue diagnosis: Biopsy/ FNAB is mandatory to confirm diagnosis" | a for locally advanced ("mandatory"); incidental diagnosis is histopathology itself ("Diagnosis of Gallbladder cancer based on post operative histopathology of the gallbladder specimen in a"); per primum b because the book allows no biopsy when upfront surgery is planned (page 1, "if upfront surgery not contemplated/ metastatic disease") |
| cystic_duct_margin | Cystic duct margin and cystic node (incidental review) | per primum none, incidental a, locally advanced none, metastatic none | histopathology | Pathology | NEW:cystic_duct_margin, margins | 3 | "Note T stage, cystic duct margin and" | a: part of the page 3 review of histopathology |
| ihc_if_not_adenocarcinoma | Additional IHC if adenocarcinoma is not confirmed | metastatic c, others none | ihc | Pathology | histologic_type | 5 | "to add additional IHC, if not confirmed to be an adenocarcinoma on" | c: conditional |
| pet_cect | Whole body PET-CECT | per primum c, incidental b, locally advanced a, metastatic c | pet_ct | Nuclear Medicine | suv_max, distant_findings | 4 | "Staging:  Whole body PET CECT Scan" | locally advanced a (listed under Staging); page 1 lists it under "Optional:" so c elsewhere; incidental b from page 3 |
| mri_mrcp | MRI with MRCP (obstructive jaundice) | per primum c, incidental none, locally advanced b, metastatic none | mri | Radiology | NEW:bile_duct_involvement | 4 | "MRCP to ascertain the exact level of block" | page 1: "Optional: MRI with MRCP in patients presenting with OJ" gives c; page 4 makes it part of the jaundice work-up, so b for locally advanced; conditional on OJ |
| staging_laparoscopy | Staging or diagnostic laparoscopy | per primum b, incidental b, locally advanced b, metastatic none | operative_note | Hepatobiliary and Pancreatic Surgery | distant_findings | 4 | "Staging laparoscopy (optimal)" | b: printed "(optimal)" on page 4; page 3 "Diagnostic laparoscopy if presenting after 4 weeks prior to definitive surgery."; page 2 lists it for non-metastatic per primum disease |
| mdt_discussion | Multidisciplinary team discussion | per primum none, incidental none, locally advanced a, metastatic none | tumour_board_record | MDT Coordinator | clinical_question | 2 | "discussed in MDT)" | a for locally advanced: "discussed in MDT)"; proposed |

The radiology elements of the synoptic form are the new facts below (all quotes from page 1 or 2 of the synoptic file): gallbladder mass, bile duct involvement, arterial and portal vein abutment or encasement, regional lymph nodes, distant metastases.

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| gb_mass | Gallbladder mass | categorical: absent, indeterminate, present (size as lesion_size) | ultrasound, ct, mri | "- absent, indeterminate, present, if present size (cm): ...." (synoptic, page 1) |
| bile_duct_involvement | Bile duct involvement | categorical: absent, present (level as text) | ct, mri | "Bile duct involvement: absent, present" (synoptic, page 1) |
| vessel_involvement | Arterial or portal vein involvement | categorical: none, abutment, encasement, infiltration (vessel as text) | ct, mri | "1) Arterial abutment/ encasement/ infiltration: RHA, CHA, LHA" (synoptic, page 1) |
| ca19_9 | CA 19-9 | number (U/mL) | lab | "Tumour marker CA 19-9" (page 3) |
| cystic_duct_margin | Cystic duct margin | categorical: negative, positive, not stated | histopathology | "Note T stage, cystic duct margin and" (page 3) |

Regional nodes and distant spread reuse `nodal_findings` and `distant_findings`: "III. Regional lymph nodes: absent, indeterminate, present" (synoptic page 2).

### Staging system
The book uses stage groups without naming an edition: "Stage I, II & selected stage IIIA" (page 3) and "Stage III, Stage IVA & IVB" (page 3), plus pT and N letters ("pT1b and above", "pT3, T4 and N + patients", page 3). No AJCC or UICC edition is printed. Nothing computed.

### Indian notes
The draft is from Tata Memorial and cites Indian work throughout; reference 5 (page 6): "Indian Council of Medical Research consensus document for the management of gall bladder" Resource note (page 2): radical surgery is advised only where expertise exists ("and facilities available at"), otherwise "Close and refer patient to" a centre with expertise. The text does not name the north Indian gallbladder cancer belt or PM-JAY; the high share of incidental disease is the Indian presentation shown (page 3: "Diagnosis of Gallbladder cancer based on post operative histopathology of the gallbladder specimen in a").

### Regimen or dose tables
Page 5 (palliative first and second line regimens, no doses), page 4 (neoadjuvant "Gemcitabine + Cisplatin" on the preferred pathway), page 2 (adjuvant therapy box), page 3 (adjuvant per stage). References on pages 6 and 7.

### Open questions
- The north Indian gallbladder cancer belt is not in the NCG file; this has to come from ICMR or NCRP, outside this book.
- Whether the per primum biopsy rule ("if upfront surgery not contemplated") should be a condition on the record.
- The meaning of "(optimal)" on page 4: read as NCG's Optimal tier (b).
