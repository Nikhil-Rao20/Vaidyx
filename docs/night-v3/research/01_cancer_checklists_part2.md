# Cancer checklists research, part 2: gynaecology, urology, head and neck, thyroid

Files read: `ncg-guidelines-for-gynecological-cancer-2019.docx`, `ncg-guidelines-for-urological-malignancies-2019.pdf` (65 pages), `ncg-guidelines-for-head-neck-cancer-2019.pdf` (62 pages), plus the repo files `lung_nsclc.json`, `oral_cavity.json`, `facts.json` and `test_tiers.py`; web searches for thyroid sources (nothing downloaded). Cancers covered and records proposed: ovary 13, corpus_uteri 9, prostate 11, kidney 9, germ_cell 12, larynx 12, thyroid 6 (thyroid has almost no NCG text: only the head and neck radiology templates p 47 to 51; its tiers are all proposals and an open-access book is recommended). New document types proposed: none (the DMSA scan uses `other`). New facts proposed are listed in each cancer's part (ca125, afp, beta_hcg, ldh, inhibin_b, he4, brca_status, p53, pole, psa, gleason_isup, positive_cores, hrd_status, corrected_calcium, embryonal_component, igcccg_group, fertility_preservation, testosterone, lh, fsh, laryngeal_function, cord_mobility, laryngeal_subsite, bethesda_category, thyroglobulin, calcitonin, tirads, extrathyroid_extension). Thyroid recommendation: ESMO 2019 (Annals of Oncology), licence to be verified.

Method: PDF text from pypdf (cited page = PDF page index + 1; in all three PDFs this equals the printed "Page N of M" header). The gynaecology book is a .docx with no page numbers: page is "n/a" and the "where" column is given in the Source part of each cancer; text taken from word/document.xml (paragraph ends as newlines). Quotes are single lines copied from the extracted text. Tier letters: (a) Essential, (b) Optimal, (c) Optional as printed by NCG. "none" in a setting means the book does not list the item for it. Wherever the book prints no letter the tier is proposed and the basis is stated.

## Ovarian cancer, epithelial (`ovary`)
### Source
- File: `ncg-guidelines-for-gynecological-cancer-2019.docx` (NCG Gynaecological Cancer guidelines, 2019). No page numbers; page = "n/a".
- Where: contents list "Epithelial Ovarian Cancers": Diagnosis, Workup & Investigations (contents p 16), Primary Treatment (17), Relapsed Ovarian Cancer (19), Summary of Imaging and Management Recommendations (20 to 24). Work-up: Section "EPITHELIAL OVARIAN CANCER (LEVELS OF EVIDENCE IN PARENTHESES)", part "Work Up & Investigations"; summary table "Summary of  Imaging and Management Recommendations for Optimal and Optional Resource Setting" (columns (a)Essential, (b)Optimal, (c)Optional, Remarks). Treatment algorithm: "PRIMARY TREATMENT (Levels of evidence in parentheses)" and "RELAPSED OVARIAN CANCER (Levels of evidence in parentheses)".
- Settings in the book: the summary table splits staging work-up into three rows, each printed with its own imaging: "Early Stage I/II", "Locally advanced Stage III/IV" and "Recurrent". The treatment algorithm splits into "Clinical early stage" and "Clinical advanced stage", and relapsed disease into platinum refractory/resistant and platinum sensitive.
- Quote (settings), where: summary table, row labels: "Clinical early stage", "Clinical advanced stage" (algorithm), "Locally advanced" and "Recurrent" (summary table rows).

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| early | Early (FIGO Stage I/II), as recorded | summary table row "Early Stage I/II"; algorithm "Clinical early stage" |
| advanced | Locally advanced to metastatic (FIGO Stage III/IV), as recorded | summary table row "Locally advanced Stage III/IV"; algorithm "Clinical advanced stage" |
| recurrent | Recurrent or relapsed, as recorded | summary table row "Recurrent"; "RELAPSED OVARIAN CANCER" |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Personal and family history, clinical and pelvic examination, performance status | early a, advanced a, recurrent a | clinical_note, referral | owner | ecog, comorbidities, clinical_question, presenting_complaint | n/a | Thorough clinical examination including pelvic and per rectal examination. | No letter printed; proposed a (listed first in the book work-up for every patient, as for the oral and rectal checklists) |
| ca125_cea | Serum tumour markers CA-125 and CEA (CA 19.9 optional) | early a, advanced a, recurrent a | lab | Biochemistry | NEW:ca125, cea | n/a | Serum tumor markers: CA-125, CEA, CA 19.9 (Ca 19.9-(c)) | Summary table lists "CA 125, CEA" under (a)Essential and CA19.9 under (b)Optimal; CA 19.9 alone is printed (c) in the text, so CA 19.9 is c |
| germ_cell_markers | AFP, beta-hCG, LDH, inhibin B (patients under 40, if indicated) | early a (condition: age under 40 or if indicated), advanced a (same), recurrent a (same) | lab | Biochemistry | NEW:afp, NEW:beta_hcg, NEW:ldh, NEW:inhibin_b | n/a | (In patients <40 years to also do AFP, βHCG, S LDH, S Inhibin B if indicated) | Condition is the book's own (age under 40, "if indicated"); the summary table remark says "as indicated"; the system never judges the condition, show the record only |
| he4 | HE4 (optional marker) | early c, advanced c, recurrent c | lab | Biochemistry | NEW:he4 | n/a | HE4 | Summary table, tumour markers row, column (c)Optional |
| imaging_cect | CECT abdomen and pelvis, chest X-ray (CECT thorax if indicated) | early a, advanced a, recurrent a | ct, xray | Radiology | lesion_size, nodal_findings, distant_findings, recorded_stage | n/a | Contrast CT scan of abdomen and pelvis and chest X-ray (a) (b).CT scan of the chest if clinically indicated or Germ Cell tumor is suspected. | Printed letters (a) (b) are on the line; summary table puts CECT abdomen + pelvis and chest X-ray in (a)Essential and (b)Optimal for all three rows |
| imaging_mri_pet | MRI abdomen and pelvis, PET-CT / PET-MRI (optional) | early c, advanced c, recurrent c | mri, pet_ct | Radiology | suv_max, comparison_prior | n/a | MRI may help to better characterise benign from malignant ovarian lesion | Summary table column (c)Optional: early "MRI Abdomen and Pelvis, PET-CT/PET-MRI"; advanced "Staging Laparoscopy to determine operability, PET-CT/PET-MRI"; recurrent "PET-CT" ("may be considered if planning secondary cyto-reduction") |
| blood_counts_org | Blood counts, liver, kidney tests, electrolytes, ECG | early a, advanced a, recurrent a | lab | Biochemistry | haemoglobin, wbc, platelets, creatinine, bilirubin | n/a | Haematological and biochemical investigations | Summary table "Other work up": "CBC, LFT, RFT, Serum electrolytes, ECG" in (a) and (b); iron studies, B12, folate, 2D echo are (c) "if Clinically indicated" |
| histopathology | Histopathology: tumour type and grade (biopsy or surgical specimen) | early a, advanced a, recurrent a | histopathology | Pathology | histologic_type, grade | n/a | Grossing and complete reporting of the surgical specimen should be done | Summary table Pathology, column (a): "Pathology reporting Tumour type, grade"; recurrent row has no separate pathology entry, kept a as proposal |
| ascitic_cytology | Ascitic or pleural fluid cytology (if present) | early none, advanced a, recurrent none | cytology | Pathology | histologic_type | n/a | Ascitic fluid/ pleural fluid cytology (if present). | Summary table Pathology column (a): "Ascitic fluid cytology in advanced cancers" |
| cell_block_ihc | Ascitic fluid cell block and IHC markers as indicated | early c, advanced c, recurrent none | ihc, cytology | Pathology | histologic_type | n/a | Cell block preparation for IHC may be done (IHC (c)) | Text prints (c); the summary table places "Ascitic fluid cell block and IHC" and "IHC markers as indicated" in column (b)Optimal. Kept c (letter printed in the text); see Open questions |
| image_guided_biopsy | Image-guided biopsy or FNAC (advanced disease where primary surgery is not planned) | early none, advanced a (condition: primary surgery not planned), recurrent none | histopathology, cytology | Radiology | histologic_type | n/a | Biopsy or FNAC to be done only in advanced disease where primary surgery not planned. | Summary table Pathology column (a)/(b): "Image guided biopsy /FNAC if indicated (in advanced cancers)" |
| genetic_testing | BRCA 1 and 2 testing, genetic counselling | early c, advanced c, recurrent c | molecular | Medical Genetics | NEW:brca_status | n/a | Genetic Testing for BRCA 1 and 2 in case family history suggestive. Consider in all high grade non mucinous epithelial ovarian carcinoma (c) | Printed (c) in the text; the summary table says "Genetic counselling and testing to be offered to all non mucinous epithelial ovarian cancers" (no letter visible in the extraction) |
| gi_endoscopy | Upper and lower GI endoscopy (only if clinically indicated) | early c, advanced c, recurrent none | endoscopy | Gastrointestinal Surgery | distant_findings | n/a | Upper and Lower GI endoscopy if clinically indicated eg. | No letter printed in the text; summary table "Upper GI endoscopy, Lower GI endoscopy" is in the Remarks as "If clinically indicated to rule out Krukenberg tumor"; proposed c |
| mammogram_bilateral | Bilateral mammogram (only if clinically indicated, to rule out Krukenberg tumour) | early c, advanced c, recurrent none | mammogram | Radiology |  | n/a | B/L Mammogram | Same summary table row, remark "If clinically indicated to rule out Krukenberg tumor"; proposed c |

Where (every row): Section "EPITHELIAL OVARIAN CANCER (LEVELS OF EVIDENCE IN PARENTHESES)", part "Work Up & Investigations"; summary table "Summary of  Imaging and Management Recommendations for Optimal and Optional Resource Setting" (columns (a)Essential, (b)Optimal, (c)Optional, Remarks).

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| ca125 | CA-125 | number with unit (U/mL) | lab | Serum tumor markers: CA-125, CEA, CA 19.9 (Ca 19.9-(c)) |
| afp | Alpha-fetoprotein (AFP) | number with unit (ng/mL) | lab | AFP, βHCG, S LDH, S Inhibin B if indicated |
| beta_hcg | Beta-hCG | number with unit (mIU/mL) | lab | AFP, βHCG, S LDH, S Inhibin B if indicated |
| ldh | Serum LDH | number with unit (U/L) | lab | S LDH |
| inhibin_b | Inhibin B | number with unit (pg/mL) | lab | S Inhibin B if indicated |
| he4 | HE4 | number with unit (pmol/L) | lab | HE4 |
| brca_status | BRCA 1 / 2 result | categorical (pathogenic variant, VUS, no variant found, not tested, pending), as written | molecular | Genetic Testing for BRCA 1 and 2 |

### Staging system
- The ovarian part uses FIGO stage with no year named: "FIGO stage" (the management table header, Epithelial Ovarian Cancer Management), with early = Stage I/II and advanced = Stage III/IV. Risk groups for early disease: "Low Risk- Stage IA/IB , Grade 1, Non-Clear cell Histology" and "High Risk – Stage IA/IB, Grade  2/3, Clear cell histology, Stage IC, Stage II". The book names "FIGO 2018" only in the cervix section. No TNM edition is named for ovary.

### Indian notes
- Resource levels: the ovarian summary table is built for an "Optimal" and "Optional" resource setting (the contents page calls it "Optimal and Minimal Resource Setting"). Quote: "Summary of  Imaging and Management Recommendations for Optimal and Optional Resource Setting" (section, Epithelial ovarian summary).
- Quote: "Patient selection for primary debulking surgery over NACT based on Patient factors" (Advanced Stage surgery row; the same line lists poor performance status, low albumin, comorbidities).
- No PM-JAY text in this book.

### Regimen or dose tables
- No page numbers. Sections only: "PRIMARY TREATMENT" footnotes "**Chemotherapy -" (paclitaxel, carboplatin, bevacizumab, PARP inhibitors), "RELAPSED OVARIAN CANCER", and the summary table "Epithelial Ovarian Cancer Management" (Early Stage and Advanced Stage rows). Germ cell and sex-cord ovarian tumours have their own section "GERM CELL TUMORS Management" (not in this checklist).

### Open questions
- The summary table text is garbled (rows and columns run together in the extraction); the (a)/(b)/(c) assignment of a few items (IHC, genetic testing, GI endoscopy, mammogram) is inferred from the order of cell text and needs a look at the formatted document.
- The docx is for epithelial ovarian cancer; borderline, germ cell, sex cord-stromal tumours are separate sections and not covered here.
- Whether surgical staging records (operative note, peritoneal cytology) should be a record: the book treats them as treatment.

## Cancer of the corpus uteri, endometrium (`corpus_uteri`)
### Source
- File: `ncg-guidelines-for-gynecological-cancer-2019.docx`, 2019, no page numbers. Where: Section "Endometrial Cancer" (contents p 25 to 26: Diagnosis, Workup & Investigations), the investigation algorithm headed "Endometrial cancer / Investigations" (Clinically early stage / Advanced stage), and the table "Summary of Imaging and Management Recommendations for Endometrial Cancers". Risk groups table (Low, Intermediate, High-Intermediate, High risk) near the follow-up algorithm.
- Settings in the book: the investigation algorithm splits "Clinically early stage" and "Advanced stage"; the summary table splits "Disease Clinically confined to body of uterus", "Stage II" (cervical stroma), "Stage III" (local and/or regional spread) and later stage IV.
- Quotes: "Disease Clinically confined to body of uterus" (summary table, first row); "Clinically early stage" and "Advanced stage" (investigation algorithm).

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| early | Early, clinically confined to the uterus (FIGO Stage I and II), as recorded | algorithm "Clinically early stage"; summary table first two rows |
| advanced | Advanced (FIGO Stage III and IV), as recorded | algorithm "Advanced stage"; summary table Stage III and IV rows |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | History, examination, performance status (fitness for surgery) | early a, advanced a | clinical_note, referral | owner | ecog, comorbidities, menopausal_status, clinical_question | n/a | Staging CT scan and investigations for general fitness to treat should be done following confirmation of cancer/precancer | No letter printed for history; proposed a. The quoted line is from the vulvar section and shows the book wording for fitness; endometrial rows state "Electrocardiogram" and renal and liver tests (see blood_counts_org) |
| endometrial_biopsy | Endometrial biopsy (hysteroscopy-guided if used), with IHC as indicated | early a, advanced a | histopathology | Pathology | histologic_type, grade | n/a | Endometrial biopsy +/-IHC | Summary table Pre-treatment Workup, column (a)Essential, all rows |
| blood_counts_org | Complete haemogram, renal and liver function tests, ECG (CA125 in advanced) | early a, advanced a | lab | Biochemistry | haemoglobin, wbc, platelets, creatinine, bilirubin, NEW:ca125 | n/a | Renal and Liver Function tests, CA125 | Summary table (a) column: early rows "Complete Hemogram, Renal and Liver Function tests, Electrocardiogram"; Stage III/IV rows add "CA125" |
| chest_xray | Chest radiograph (CT thorax only if needed in advanced) | early a, advanced a | xray, ct | Radiology | distant_findings | n/a | Chest radiograph SOS CT thorax | Summary table column (a): "Chest radiograph" for all stages; "SOS CT thorax" in Stage III/IV |
| pelvic_imaging | USG (TAS + TVS) abdomen and pelvis, or CT or MRI abdomen and pelvis | early a, advanced a | ultrasound, ct, mri | Radiology | lesion_size, depth_of_invasion, nodal_findings, parametrial_involvement | n/a | USG(TAS+TVS) abdomen+ pelvis | Summary table: (a) USG(TAS+TVS) abdomen+ pelvis; (b) CT or MRI (abdomen + pelvis); Stage II adds "CECT Abdomen and Pelvis"; the algorithm for advanced disease says "CECT Abdomen + Pelvis+ Thorax or whole body PET-CT$$" with "$$: PET-CT should not be done in early lesions." |
| pathology_report | Pathology: tumour type, grade, depth of invasion, LVSI | early a, advanced a | histopathology | Pathology | histologic_type, grade, depth_of_invasion, lvi, margins | n/a | Tumour type, grade, depth of invasion, LVSI | Summary table Pathology, column (a) |
| molecular_ihc | IHC for p53 and MMR; ER, PR on tissue blocks; POLE if available | early b, advanced b | ihc, molecular | Pathology | mmr, er, pr, NEW:p53, NEW:pole | n/a | IHC for P53, MMR | Summary table column (b)Optimal: "IHC for P53, MMR  ER, PR on tissue Blocks, POLE if available"; advanced disease: "MSI High" and "HER 2 positive" (algorithm footnote; the treatment words after them are not quoted) |
| her2 | HER2 (advanced disease) | early none, advanced c | ihc | Pathology | her2 | n/a | HER 2 positive | Named in the advanced-stage algorithm without a letter; proposed c (a testing item attached to a treatment option). No test line without treatment words exists in the book, so the quote is cut before the treatment word |
| mri_fertility | MRI pelvis (a must when fertility preservation is considered) | early c (condition: young woman considering fertility preservation), advanced none | mri | Radiology | lesion_size, depth_of_invasion | n/a | MRI is a must in the above. | Printed "must" for the fertility-sparing case only; column (c)Optional; condition is the book's |
| frozen_sln | Frozen section and sentinel node (optional, surgical) | early c, advanced none | histopathology | Pathology | depth_of_invasion, grade | n/a | Frozen section examination of uterus for depth of invasion, tumor size and grade and cervical involvement | Summary table column (c)Optional; a surgery-time item, include only if the board wants it |

Where (every row): Section "Endometrial Cancer" (contents p 25 to 26: Diagnosis, Workup & Investigations), the investigation algorithm headed "Endometrial cancer / Investigations" (Clinically early stage / Advanced stage), and the table "Summary of Imaging and Management Recommendations for Endometrial Cancers".

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| ca125 | CA-125 (shared with ovary) | number with unit (U/mL) | lab | Renal and Liver Function tests, CA125 |
| p53 | p53 IHC pattern | categorical (wild type, abnormal / mutant, not done), as written | ihc | IHC for P53, MMR |
| pole | POLE mutation | categorical (mutated, not mutated, not done), as written | molecular | POLE if available |

### Staging system
- FIGO stage letters are used (Stage IA, IB, II, IIIA, IIIB, IIIC1, IIIC2) with a risk-group table (Low, Intermediate, High-Intermediate, High risk). No FIGO year or TNM edition is named in the endometrial part (the text "FIGO 2018" appears only in the cervix section). Quote: "Stage III endometrioid, no residual disease" (High Risk row of the risk-group table).

### Indian notes
- Quote (Adjuvant, Stage IA, Stage IB rows of the summary table, and the algorithm): "[Status of LVSI not known in view of poor processing/ lack of expertise: To consider as LVSI positive status]". This is a resource note: an unreported LVSI is treated as positive.
- Quote: "Referral to another centre may also be discussed for IMRT if feasible." (Adjuvant rows).

### Regimen or dose tables
- No page numbers. Sections: "Adjuvant" blocks in the summary table (Stage IA, IB), the Stage III and IV rows (a chemotherapy line, pointer only, the dose is not copied, and "Chemotherapy Regimen:"), "Histology based treatment" and "Inoperable & unfit for Surgery" in the contents.

### Open questions
- The quote used for clinical_history is the vulvar-section wording; the endometrial section has no explicit history line. A better quote should be found in the formatted docx, or the record should lean on "Electrocardiogram" (fitness).
- Which row of the extracted summary table is Stage IV is inferred from order; the Stage II, III rows are clear.
- Uterine sarcoma and carcinosarcoma are not separate in the book (carcinosarcoma is grouped with "Type II" histology).

## Prostate cancer (`prostate`)
### Source
- File: `ncg-guidelines-for-urological-malignancies-2019.pdf` (65 pages, 2019; printed page = PDF page). Prostate: investigations p 33, localised p 34, locally extensive p 35, metastatic hormone-sensitive p 36, CRPC second, third and later lines p 37 to 39, chemotherapy and dose table p 40 to 41. Imaging format p 48 (prostate MRI), pathology formats p 53 to 54 (biopsy / TURP), p 58 to 60 (radical prostatectomy).
- Settings in the book: "Localized Prostate Cancer (T1 – T3a N0)" (p 34), "Locally extensive Prostate cancer (T3b+/-cN1)" (p 35), "Metastatic Hormone Sensitive Prostate cancer (HSPC)" (p 36) and "METASTATIC CASTRATION RESISTANT PROSTATE CANCER- SECOND LINE (CRPC)" (p 37). Risk groups (p 33, 34): low, intermediate, high.

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| localised | Localised (T1 to T3a, N0), as recorded | p 34 "Localized Prostate Cancer (T1 – T3a N0)" |
| locally_extensive | Locally extensive (T3b, or cN1), as recorded | p 35 "Locally extensive Prostate cancer (T3b+/-cN1)" |
| metastatic_hspc | Metastatic, hormone sensitive, as recorded | p 36 |
| metastatic_crpc | Metastatic, castration resistant, as recorded | p 37 to 39 |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history, digital rectal examination, performance status, comorbidity | localised a, locally_extensive a, metastatic_hspc a, metastatic_crpc a | clinical_note, referral | owner | ecog, comorbidities, clinical_question, presenting_complaint | 33 | Abnormal DRE | No letter on DRE; proposed a (it is the trigger for biopsy in the book and the way cT is recorded) |
| psa | Serum PSA (with age-specific ranges) | localised a, locally_extensive a, metastatic_hspc a, metastatic_crpc a | lab | Biochemistry | NEW:psa | 33 | Elevated Age specific (PSA ng/ml)(Age (yrs) 41-50 <2.1, 51-60 <3.4, 61-70<4.2, | No letter; proposed a (the risk groups on p 33 and 34 are defined by PSA, and Roach formula p 34, 35 uses PSA) |
| histopathology | Prostate biopsy / TURP histopathology: Gleason score and ISUP grade group | localised a, locally_extensive a, metastatic_hspc a, metastatic_crpc none | histopathology | Pathology | histologic_type, NEW:gleason_isup, NEW:positive_cores | 53 | 2. Histologic Grade Group and Gleason Score | Biopsy technique is (b) on p 33 ("10-12 biopsies need to be taken (b)"); the histopathology itself has no letter, proposed a (diagnosis); IHC for basal markers is (c) on p 54 |
| biopsy_technique | TRUS-guided systematic biopsy (10 to 12 cores) | localised b, locally_extensive b, metastatic_hspc none, metastatic_crpc none | histopathology, ultrasound | Urology | NEW:positive_cores | 33 | 10-12 biopsies need to be taken (b) | Printed (b). For clinically metastatic disease or PSA over 100 the book accepts a digital-guided biopsy of about 6 cores |
| mri_prostate | MRI of the prostate (mpMRI) for local staging | localised b, locally_extensive b, metastatic_hspc none, metastatic_crpc none | mri | Radiology | lesion_size, recorded_stage | 33 | MRI of the Prostate for local staging and planning treatment. (B) | Printed (B) on p 33 and (b) on p 35; low-risk localised: "No further imaging is required" on p 33 (the system never judges the risk group, so the record is shown and the board decides). Active surveillance needs mpMRI within 3 months of biopsy (p 34) |
| ct_abdomen_pelvis | CECT abdomen and pelvis (and thorax for high-volume disease) | localised none, locally_extensive b, metastatic_hspc b, metastatic_crpc none | ct | Radiology | nodal_findings, distant_findings | 35 | CECT of abdomen and pelvis (b) | p 35 (b); p 36 "CECT of abdomen and pelvis and Thorax (b)"; p 33 lists CECT abdomen and pelvis for clinically metastatic disease without a letter |
| bone_scan | Bone scan (MDP) | localised none, locally_extensive a, metastatic_hspc a, metastatic_crpc none | bone_scan | Nuclear Medicine | distant_findings | 35 | Bone scan is Mandatory (a) | Printed (a) on p 35 and p 36; p 33 names "MDP bone scan" for clinically metastatic disease |
| psma_pet | PSMA PET-CT (optional) | localised c, locally_extensive c, metastatic_hspc c, metastatic_crpc none | pet_ct | Nuclear Medicine | distant_findings, nodal_findings | 33 | PSMA PET CT scan (c) | Printed (c) on p 33, 35, 36; p 35 also "In staging of post primary treatment recurrence disease PSMA PET is the investigation of choice (b)" |
| life_expectancy_g8 | Health assessment for life expectancy (Geriatric 8 screening) | localised b, locally_extensive none, metastatic_hspc none, metastatic_crpc none | clinical_note | owner | ecog, comorbidities | 34 | tools like Geriatric 8 (G8) screening tool (b) | Printed (b) (p 34 footnote "Life expectancy"). The book sets life expectancy against 10 years in the localised pathway |
| genetic_hrd | Genetic mutation analysis for HRD (BRCA 1 and 2, ATM) | localised none, locally_extensive none, metastatic_hspc none, metastatic_crpc c | molecular | Medical Genetics | NEW:hrd_status | 39 | Genetic mutation nalysis for HRD | Printed (c) on the next line "Olaparib (c)", beyond third line; the quote line itself carries no letter |
| renal_dental_bone_agent | Renal function and dental opinion before bone-modifying agent (CRPC) | localised none, locally_extensive none, metastatic_hspc none, metastatic_crpc a | lab, clinical_note | owner | creatinine, dental_evaluation | 37 | renal function and dental opinion | The line and the one above it name the bone-modifying agents (treatment words, not quoted; the quote is cut to the test words); proposed a for creatinine and dental opinion as the condition for the bone agent |

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| psa | PSA | number with unit (ng/mL) | lab | Elevated Age specific (PSA ng/ml) |
| gleason_isup | Gleason score and ISUP grade group | text (for example "3+4=7, Grade group 2"), as written | histopathology | Histologic Grade Group and Gleason Score; Grade group 1 (Gleason Score 3+3=6) |
| positive_cores | Positive cores / total cores | text (for example "6 of 12") | histopathology | Number of positive cores: |
| hrd_status | HRD (BRCA 1/2, ATM) result | categorical (mutation found, not found, not tested, pending), as written | molecular | Genetic mutation nalysis for HRD |

### Staging system
- Pathology format: "Path staging pT pN (AJCC 8th edition)" (p 60, radical prostatectomy). Clinical risk groups on p 33 (low: PSA under 10, Gleason 6 (ISUP 1), cT1 to T2a; intermediate: PSA 10 to 20, cT2b, Gleason 7 (ISUP 2 to 3); high: PSA over 20, T2c, Gleason over 7 (ISUP 4 to 5)). The book does not name D'Amico. Quote (p 33): "PSA <10, Gleason score 6 (ISUP".

### Indian notes
- p 33: "b) Digital (finger) guided biopsy (~6) might be considered adequate in patients with" (clinically metastatic disease or PSA over 100: a resource-saving step).
- p 33: age-specific PSA ranges are given: "Elevated Age specific (PSA ng/ml)(Age (yrs) 41-50 <2.1, 51-60 <3.4, 61-70<4.2, ".
- Cost and access remarks for drugs are on the kidney page 7 (shared urology book): "*If patient is affording for same or there is " (p 7).

### Regimen or dose tables
- p 34 (radical RT dose lines and ADT durations), p 40 and 41 (ADT, abiraterone, enzalutamide, docetaxel, cabazitaxel, olaparib and bone-agent dose table).

### Open questions
- The p 33 flow chart is garbled in the extraction: the exact tier of CECT / bone scan for localised intermediate and high risk is unclear; marked none.
- The book has no tier letters on history, PSA and the biopsy report itself; the above are proposals for clinical review.
- Whether a "post-prostatectomy histopathology (margins, capsule invasion)" record is wanted: p 35 uses it for adjuvant RT ("cut margins positive on final HPR"); it was left out as a post-treatment item.

## Kidney cancer, adult renal cell carcinoma (`kidney`)
### Source
- File: `ncg-guidelines-for-urological-malignancies-2019.pdf`, 2019. Renal cell carcinoma: investigations p 4, localised p 5, metastatic p 6, systemic therapy p 7, surveillance p 8 and drug doses p 8. Radiology format "RENAL MASS CT" p 42 to 43; pathology format "RENAL CANCER ON RADICAL NEPHRECTOMY SPECIMENS" p 61 to 63.
- Settings in the book: "Treatment pathway for localized disease" (p 5; T1a, T1b, T2-4) and "Treatment pathway for metastatic disease" (p 6; operable or inoperable kidney, clear cell and non clear cell).

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| localised | Localised (no distant disease), as recorded | p 5 |
| metastatic | Metastatic, as recorded | p 6 |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical evaluation: flank pain, mass, haematuria, incidental finding; performance status and comorbidity | localised a, metastatic a | clinical_note, referral | owner | ecog, comorbidities, presenting_complaint, clinical_question | 4 | Flank pain, mass, hematuria | No letter; proposed a. Performance status and comorbidity drive watchful waiting (p 5 "poor Performance status, significant comorbidity") |
| ultrasound | Ultrasound of the renal mass | localised a, metastatic a | ultrasound | Radiology | lesion_size | 4 | Ultrasound scan (a) | Printed (a) |
| cect_kidney | CECT kidneys (confirm creatinine) | localised a, metastatic a | ct, mri | Radiology | lesion_size, creatinine, nodal_findings, recorded_stage | 4 | CECT for kidneys (confirm creatinine) | Printed (a) at end of the line |
| chest_imaging | X-ray or CT chest (metastatic work-up) | localised a, metastatic a | xray, ct | Radiology | distant_findings | 4 | X-ray /CT chest (a) | Printed (a) under "Metastatic Work up" |
| bone_scan | Bone scan, in raised alkaline phosphatase or bony pain | localised b (condition), metastatic b (condition) | bone_scan | Nuclear Medicine | distant_findings | 4 | Bone scan – In raised alkaline phosphatase or bony pain (b) | Printed (b), with the condition |
| mri_brain | MRI brain, in the presence of neurological symptoms | localised c (condition), metastatic c (condition) | mri | Radiology | distant_findings | 4 | MRI brain – In the presence of neurological symptoms (c) | Printed (c), with the condition |
| mskcc_indices | MSKCC indices: blood count, serum LDH, corrected calcium | localised none, metastatic b | lab | Biochemistry | haemoglobin, wbc, platelets, NEW:ldh, NEW:corrected_calcium | 4 | MSKCC indices (CBP, Serum LDH and Corrected calcium level) (b) | Printed (b) under the metastatic work-up; used for risk groups p 6 ("As per MSKCC risk criteria") |
| dmsa_scan | DMSA renal scan, to decide treatment options | localised c, metastatic none | other | Nuclear Medicine | creatinine | 4 | DMSA Scan – To decide treatment options (c) | Printed (c); no better document type exists, "other" used |
| renal_mass_biopsy | Renal mass biopsy and histopathology (subtype, grade) | localised b (condition: radiological uncertainty or before surveillance, ablation or systemic treatment), metastatic a | histopathology | Pathology | histologic_type, grade | 6 | Biopsy (a) | p 4 "Routine renal mass Biopsy is not indicated (a)" and "Renal mass biopsy considered (b)"; p 6 "Biopsy (a)" in the metastatic pathway; grade is "WHO/ISUP tumour grade" (p 62) |

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| ldh | Serum LDH (shared) | number with unit (U/L) | lab | Serum LDH |
| corrected_calcium | Corrected serum calcium | number with unit (mg/dL) | lab | Corrected calcium level |

### Staging system
- Pathology format (p 63): "Tumour stage : pT….. pN….. pM….. (M1 only, if applicable)"; no TNM edition is named on the kidney format (AJCC 8th edition is named on the prostate and bladder formats, p 60 and 65). Risk groups for systemic therapy: MSKCC (p 6) and IMDC (p 7, "Low risk (IMDC"). Grade: "WHO/ISUP tumour grade" (p 62).

### Indian notes
- p 7: "*If patient is affording for same or there is " and "company insurance than these options are" (newer drugs are optimal (b) if affordable or insured, otherwise optional (c)).

### Regimen or dose tables
- p 7 (first and second line therapy tables), p 8 (surveillance schedule and drug doses). Treatment content not copied.

### Open questions
- p 5 and 6 are flow charts; the biopsy tier for localised disease depends on a condition the system never judges.
- Paediatric renal tumours (Wilms) are in another book.

## Germ cell tumour of the testis (`germ_cell`)
### Source
- File: `ncg-guidelines-for-urological-malignancies-2019.pdf`, 2019. Testicular tumours: management p 20, stage I seminoma p 21, stage II/III seminoma p 22, stage I NSGCT p 23, stage II and III NSGCT p 24, relapsed p 25, chemotherapy p 26 to 27. Radiology "TESTIS MALIGNANCY CT" p 46; pathology "RADICAL ORCHIECTOMY SPECIMENS" p 49 to 50. Ovarian or extragonadal and childhood germ cell tumours are in other books.
- Settings in the book: "STAGE – I SEMINOMA" (p 21), "STAGE – II /III SEMINOMA" (p 22), "STAGE I NSGCT" (p 23), "STAGE II and III NSGCT" (p 24), "Relapsed NSGCT  and seminoma (First line)" (p 25).

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| stage_i | Stage I (seminoma or non-seminoma), as recorded | p 21, p 23 |
| stage_ii_iii | Stage II and III (seminoma or non-seminoma), as recorded | p 22, p 24 |
| relapsed | Relapsed or second relapse, as recorded | p 25 |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical examination (testicular mass, undescended testis, lower abdominal mass), performance status | stage_i a, stage_ii_iii a, relapsed a | clinical_note, referral | owner | ecog, comorbidities, presenting_complaint, clinical_question | 20 | Clinical examination | No letter; proposed a (it opens the book pathway) |
| tumour_markers | Tumour markers AFP, beta-hCG, LDH (before orchidectomy) | stage_i a, stage_ii_iii a, relapsed a | lab | Biochemistry | NEW:afp, NEW:beta_hcg, NEW:ldh | 20 | - AFP, BhCG,LDH (a) | Printed (a); "Tumor Markers (a)" on the line above |
| post_orchidectomy_markers | Repeat tumour markers after high inguinal orchidectomy (at least 7 to 10 days) | stage_i a, stage_ii_iii a, relapsed a | lab | Biochemistry | NEW:afp, NEW:beta_hcg, NEW:ldh | 20 | HPR, Post Orchidectomy tumor marker (a) | Printed (a); p 20 "Repeat Tumour Markers after High Inguinal Orchidectomy at least after 7-10 days (a)" wraps over two lines |
| histopathology | Histopathology of high inguinal orchidectomy specimen (type, extent, LVI) | stage_i a, stage_ii_iii a, relapsed a | histopathology | Pathology | histologic_type, lvi, recorded_stage, NEW:embryonal_component | 20 | High Inguinal Orchidectomy (a) | Printed (a); p 23 risk factors "Lymphovascular invasion (LVI) + or Embryonal carcinoma component >  40%"; format p 49, 50 |
| usg_scrotum | Ultrasound of the scrotum | stage_i a, stage_ii_iii a, relapsed none | ultrasound | Radiology | lesion_size | 20 | - USG –Scrotum (a) | Printed (a) |
| ct_tap | CT thorax, abdomen and pelvis | stage_i a, stage_ii_iii a, relapsed a | ct | Radiology | nodal_findings, distant_findings, recorded_stage | 20 | - CT scan(Thorax, Abdo, Pelvis)(a) | Printed (a); p 24 "CECT T+A+P (a)" for residual mass |
| risk_stratification | Risk stratification, IGCCCG group as recorded (stage II and III) | stage_i a, stage_ii_iii a, relapsed none | tumour_board_record, clinical_note | Medical Oncology | NEW:igcccg_group, recorded_stage | 24 | Risk stratification as per IGCCC  (a) | Printed (a); p 20 "Risk Stratification (a)"; stage I seminoma risk (p 21): "Risk Stratification (b)" |
| fertility_preservation | Semen analysis and sperm banking | stage_i b, stage_ii_iii b, relapsed none | lab, clinical_note | Urology | NEW:fertility_preservation | 20 | - Sperm banking (b) | Printed (b), also "Semen analysis (b)"; p 20 "Ejaculated sperm preservation if family not completed (b)" |
| fertility_hormones | Total testosterone, LH, FSH (fertility investigations) | stage_i c, stage_ii_iii c, relapsed none | lab | Biochemistry | NEW:testosterone, NEW:lh, NEW:fsh | 20 | - Fertility investigations: Total testosterone; Luteinising | Printed (c ) |
| brain_imaging | Brain imaging in symptoms, multiple lung metastases or high beta-hCG | stage_i b (condition), stage_ii_iii b (condition), relapsed none | mri, ct | Radiology | distant_findings | 20 | - Brain Imaging if case of symptoms and patients with | Printed (b) at the end of the sentence (next lines) |
| fnac_testis | Ultrasound-guided FNAC of the testis (optional) | stage_i c, stage_ii_iii c, relapsed none | cytology | Pathology | histologic_type | 20 | - USG guided FNAC (c) | Printed (c) |
| pet_ct_post_chemo | FDG PET-CT 10 to 12 weeks after chemotherapy (seminoma, residual mass over 3 cm) | stage_i none, stage_ii_iii a (condition), relapsed none | pet_ct | Nuclear Medicine | suv_max, comparison_prior | 22 | FDG PET CT for Post chemo seminoma if residual lesion > 3cm (a) | Printed (a); a post-treatment check, include only if the board wants follow-up items |

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| afp | Alpha-fetoprotein (AFP) | number with unit (ng/mL) | lab | AFP, BhCG,LDH (a) |
| beta_hcg | Beta-hCG | number with unit (mIU/mL) | lab | AFP, BhCG,LDH (a) |
| ldh | Serum LDH | number with unit (U/L) | lab | AFP, BhCG,LDH (a) |
| embryonal_component | Embryonal carcinoma component percentage | number with unit (%) | histopathology | Embryonal carcinoma (specify percentage): _____% (p 50) |
| igcccg_group | IGCCCG risk group as recorded | categorical (good, intermediate, poor, not stated), as written, never computed | tumour_board_record, clinical_note | Risk stratification as per IGCCC  (a) |
| fertility_preservation | Sperm banking / fertility counselling documented | categorical (done, declined, not done, not documented) | clinical_note | Sperm banking (b) |
| testosterone | Total testosterone | number with unit (ng/dL) | lab | Total testosterone |
| lh | Luteinising hormone | number with unit (IU/L) | lab | Luteinising hormone |
| fsh | Follicle-stimulating hormone | number with unit (IU/L) | lab | Follicle-stimulating hormone |

### Staging system
- Risk groups "as per IGCCC" (p 24; "Good risk" and "Intermediate /Poor risk"). Stage groups I, II (IIa/IIb/IIc), III are used on p 21 to 24. Pathology format (p 50) has "Extent of tumor  ( Determines the  pT stage)"; no AJCC edition is named for the testis format. Quote (p 24): "Risk stratification as per IGCCC  (a)".

### Indian notes
- p 20: "( Scrotal Orchidectomy should not be done)" (a practice warning for referral from peripheral centres).
- p 22: "- For PET positive residual masses, consider surgery if feasible preferably at high volume center (a)" (a centre-level note).

### Regimen or dose tables
- p 26 (BEP, EP, VIP, VeIP, adjuvant carboplatin) and p 27 (TIP, GemOx, gemcitabine regimens). Treatment content not copied.

### Open questions
- Seminoma and NSGCT differ in the pathway; the checklist is one with three settings. A split by histology is not proposed because the system never decides it.
- Stage II and III seminoma treatment depends on residual mass size (a condition the system never judges).
- The testis format labels pre/post orchidectomy markers (c) (p 50) while the pathway makes them (a); the pathway letters are used.

## Cancer of the larynx (`larynx`)
### Source
- File: `ncg-guidelines-for-head-neck-cancer-2019.pdf` (62 pages, 2019; printed page = PDF page). Shared work-up for oropharynx, hypopharynx and larynx: p 10 and 11. Larynx pathways: supraglottis/glottis T1-2 N0 p 14, T1-2 N1-3 p 15 to 16, T3 N0-3 p 17 to 18, T4 any N p 19 to 20, larynx/hypopharynx any T inoperable neck node p 27, recurrent and metastatic SCC p 36. Radiology format "LARYNX AND HYPOPHARYNX" p 40 to 41; pathology format "Larynx" p 55 to 56.
- Settings in the book (by T and N): "Glottis T1-2 N0" (p 14), "Glottis/Supraglottis T1-2, N1-3" (p 15), "Supra-Glottis/Glottis T3, N0-3" (p 17), "Glottis/Supraglottis T4, Any N" (p 19), "RECURRENT/ METASTATIC SCCHN" (p 36).
- Applies from the oral cavity checklist: the line "Dental, Nutrition, Swallowing Assessment & Appropriate intervention**" (p 10) is printed in the shared oropharynx / hypopharynx / larynx pathway, so dental evaluation, nutrition and swallowing apply to larynx. The existing `oral_cavity.json` carries dental evaluation and nutrition from p 4 ("Dental evaluation/Nutrition assessment/Speech & swallowing evaluation & appropriate intervention"); the larynx records below reuse the same fact `dental_evaluation` and the same unlettered-item rule (treated as Essential). HPV / p16 testing (p 11) is for oropharynx only and does not apply.

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| early | Early (T1 to T2, N0), as recorded | p 14 |
| locally_advanced | Locally advanced (T1-2 with nodes, T3, T4, or inoperable neck nodes), as recorded | p 15 to 20, p 27 |
| metastatic | Metastatic or recurrent, as recorded | p 36 |

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical evaluation: hoarseness, dysphagia, stridor, tobacco; performance status | early a, locally_advanced a, metastatic a | clinical_note, referral | owner | ecog, tobacco_use, smoking_history, comorbidities, presenting_complaint, clinical_question | 10 | Hoarseness/Hot Potato Speech | No letter; proposed a (same rule as oral_cavity: unlettered work-up items are Essential) |
| laryngoscopy | Indirect and direct laryngoscopy (examination under anaesthesia optional): mucosal extent, cord mobility, arytenoid | early a, locally_advanced a, metastatic none | endoscopy, operative_note | ENT / Head and Neck Surgery | NEW:cord_mobility, NEW:laryngeal_function | 10 | Direct Laryngoscopy OR | No letter on laryngoscopy; proposed a; "Examination Under Anesthesia (c)" is the printed optional alternative (c) |
| laryngeal_function | Assessment of laryngeal functionality (function intact or compromised) | early a, locally_advanced a, metastatic none | clinical_note, endoscopy | ENT / Head and Neck Surgery | NEW:laryngeal_function | 10 | Assessment of laryngeal functionality | No letter; proposed a. p 17 and 19 branch on "Larynx function intact" / "Laryngeal Function compromised (Tracheostomy/Aspiration)" |
| histopathology | Biopsy and histopathology: type, grade | early a, locally_advanced a, metastatic a | histopathology | Pathology | histologic_type, grade | 56 | Histologic type of tumor: | No letter; proposed a (a diagnosis is needed to enter the pathway); format "As per WHO 2017 classification" p 56 |
| imaging_primary_neck | CECT or MRI of the primary and the neck (CECT preferred for larynx) | early b, locally_advanced b, metastatic b | ct, mri | Radiology | lesion_size, nodal_findings, ene, recorded_stage | 11 | Optimal Imaging modality for the primary and the neck may be by a CECT(b) or MRI(b). | Printed (b); "A MRI may be optimal for the Oropharynx and a CECT for the larynx and hypopharynx." (p 11). p 14: "At least a 16 slice CT scan with 3 mm cut should be preferred to evaluate involvement of cartilage." |
| chest_xray | Chest X-ray (lung metastasis, aspiration) | early a, locally_advanced a, metastatic a | xray | Radiology | distant_findings | 11 | Chest X-ray(a) is an essential investigation for ruling out lung metastasis | Printed (a) |
| cect_thorax_pet | CECT thorax or PET-CT in high risk of distant metastasis | early none, locally_advanced b (condition), metastatic b (condition) | ct, pet_ct | Radiology | distant_findings, suv_max | 11 | Either a PET CT(c) or CECT Thorax (b) should be optimal in patients being considered for | Printed: CECT thorax (b), PET-CT (c); condition is the book's (N3 node over 6 cm, multiple bilateral nodes, lower cervical nodes, T4b, advanced hypopharyngeal cancer, or symptoms of distant disease) |
| dental_evaluation | Dental evaluation and appropriate intervention | early a, locally_advanced a, metastatic none | clinical_note | owner | dental_evaluation | 10 | Dental, Nutrition, Swallowing Assessment & Appropriate intervention** | No letter; treated as Essential, as in oral_cavity (p 4); clinician to confirm it applies to larynx cases managed with radiation |
| nutrition_assessment | Nutrition assessment | early a, locally_advanced a, metastatic none | clinical_note | owner |  | 10 | Dental, Nutrition, Swallowing Assessment & Appropriate intervention** | No letter; as oral_cavity |
| speech_swallowing | Speech assessment and swallowing evaluation (bedside water swallow, 100 ml) | early b, locally_advanced b, metastatic none | clinical_note | owner |  | 11 | Assessment for speech(b) and swallowing to evaluate for aspiration(b) is considered Op- | Printed (b); FEES or videofluoroscopy (c) |
| performance_cisplatin_fitness | Performance status and cisplatin fitness (blood counts, creatinine) | early none, locally_advanced a, metastatic a | lab, clinical_note | Medical Oncology | ecog, creatinine, haemoglobin, wbc, platelets, comorbidities | 27 | ECOG performance 0-1 ECOG performance > 2 | Printed branch on ECOG; "cisplatin fitness as per standard practice/guidelines" (p 27); no letter for the labs, proposed a for non-surgical or metastatic pathways |
| surgical_pathology | Surgical specimen pathology: PNI, LVI, margins, extranodal extension, pT / pN | early none, locally_advanced none, metastatic none | histopathology | Pathology | pni, lvi, margins, ene, recorded_stage, grade | 56 | Perineural invasion (PNI):  Absent / Present / Cannot be determined | No letter; a post_board record (the surgical specimen report after surgery, from the pathology reporting format on p 56; not required before the board, so none in every setting; the board reads it at the next round) |

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| laryngeal_function | Laryngeal function (intact or compromised) and airway status | categorical (intact, compromised, tracheostomy in place, not documented), as written | clinical_note, endoscopy | Larynx function intact; Laryngeal Function compromised (Tracheostomy/Aspiration) |
| cord_mobility | Vocal cord mobility | categorical (normal, impaired, fixed), as written | endoscopy | To delineate the mucosal extent, vocal cord mobility and arytenoid status |
| laryngeal_subsite | Epicentre: glottic, supraglottic, subglottic | categorical (glottic, supraglottic, subglottic, hypopharynx, other) | ct, mri, endoscopy | If Larynx: epicentre of disease: Glottic/ Supraglottic/ Sub glottic (p 40) |

### Staging system
- The head and neck book names no AJCC or UICC edition (grep found no "AJCC" or "UICC"). Imaging formats ask "T stage:" and "N stage:" (p 40, 41); pathology format ends "TNM Stage:  pT" (p 56). Histology: "As per WHO 2017 classification" (p 56).

### Indian notes
- p 13: "#- Either Cetuximab or Nimotuzumab can be used in this setting, Optimal if affordable (em-" (employer and personal insurance named as the test of affordability).
- p 11: "HPV+Ve Oropha-" ("ryngeal Cancer is however currently noted in < 20% as per Indian studies") applies to oropharynx, not larynx.
- p 14: "*At least a 16 slice CT scan with 3 mm cut should be preferred to evaluate involvement of cartilage." (a minimum equipment standard).

### Regimen or dose tables
- Pages with Gy or mg/m2 dose lines: 13, 14, 16, 18, 20, 22, 24, 26, 28 (p 13 chemoradiation options; p 14 the primary and neck radiation dose line; larynx chemo-radiation footnotes on p 16, 18, 20; p 27 for inoperable nodes). Treatment content not copied.

### Open questions
- No biopsy line is printed in the larynx pathway (p 10); the oral pathway p 4 has "Biopsy for tissue diagnosis". The histopathology record for larynx therefore cites the pathology format p 56.
- Whether the board wants "cord mobility" as a separate fact or as part of "laryngoscopy" text.
- Hypopharynx shares the same pathway and could be added as a site in the same protocol (site words); not decided here.

## Thyroid cancer (`thyroid`)
### Source
- NCG has no thyroid management chapter. The head and neck book (`ncg-guidelines-for-head-neck-cancer-2019.pdf`) has thyroid only in the radiology synoptic annexure: "CACRNIOMA THYROID CT IMAGING" (p 47 to 49, spelling as printed), "USG THYROID DATED" (p 50 to 51) and a neck nodal mapping USG (p 51). No thyroid pathology format, no work-up list, no treatment, no tiers. A single "Endocrine work Up including thyroid(b)" (p 33) is in the nasopharynx section and is not about thyroid cancer.
- Quotes: "CACRNIOMA THYROID CT IMAGING" (p 47), "USG THYROID DATED" (p 50), "Endocrine work Up including thyroid(b)" (p 33, nasopharynx).

### Settings proposed
| id | label | NCG basis |
|---|---|---|
| localised | Primary only, no nodal or distant disease recorded, as recorded | CT format p 48 "T STAGE" |
| locoregional | Neck node disease recorded, as recorded | CT format p 48 "N STAGE:" |
| metastatic | Distant disease recorded, as recorded | CT format p 49 "M Stage" |
(These follow the book's T / N / M headings only; the real splitting must come from the open-access book chosen below and from a clinician.)

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| clinical_history | Clinical history and examination: neck swelling, voice change, radiation exposure, family history; performance status | localised a, locoregional a, metastatic a | clinical_note, referral | owner | ecog, comorbidities, presenting_complaint, clinical_question | n/a | (none in NCG) | No NCG line; proposed a (as in every other checklist); a clinician to confirm |
| thyroid_usg | High-frequency ultrasound of the thyroid (nodule features, TIRADS and TMC RSS score) | localised a, locoregional a, metastatic a | ultrasound | Radiology | lesion_size, nodal_findings | 51 | TIRADS score | Format exists in the book (p 50, 51) but no letter is printed; proposed a for a suspected thyroid cancer (ultrasound is the first test in every open-access guideline, to be confirmed against the chosen book) |
| neck_nodal_usg | Ultrasound of neck for nodal mapping (levels I to VI) | localised b, locoregional b, metastatic b | ultrasound | Radiology | nodal_findings | 51 | USG NECK FOR NODAL MAPPING DATED: | No letter; proposed b |
| fnac | FNAC of the nodule or nodes | localised a, locoregional a, metastatic a | cytology | Pathology | histologic_type, NEW:bethesda_category | 51 | FNAC correlation is suggested | Book says "FNAC correlation is suggested" on the USG format; no letter; proposed a |
| ct_neck_thyroid | CT of the neck and chest for thyroid: extrathyroid extension, trachea (Shin grade), nodes, lung nodules | localised b, locoregional b, metastatic b | ct | Radiology | lesion_size, nodal_findings, distant_findings, recorded_stage | 48 | Extra-thyroid extension: Absent/Present | No letter; the format has T, N and M sections (p 48, 49); proposed b |
| histopathology | Histopathology of the thyroid specimen (type, extrathyroid extension, margins) | localised a, locoregional a, metastatic a | histopathology | Pathology | histologic_type, grade, lvi, margins, recorded_stage | n/a | (none in NCG) | No NCG pathology format for thyroid; to be drawn from the chosen open-access book; proposed a (as in every other checklist), a clinician to confirm |

Tier letters for thyroid are all proposals: NCG prints none for it. Rows with no NCG quote cannot pass the test that every record carries an NCG source, so they need the open-access book (below) as their "book", or they are left out of the first draft. Records likely needed from that book (not read here): thyroid function tests, serum thyroglobulin and anti-thyroglobulin antibody, serum calcitonin and CEA (medullary), RET testing, radioiodine scan, laryngoscopy for cord mobility before surgery.

### New facts needed
| id | label | kind | report type | the book's wording |
|---|---|---|---|---|
| bethesda_category | Bethesda cytology category | categorical (I to VI), as written | cytology | not in NCG; FNAC correlation is suggested |
| thyroglobulin | Serum thyroglobulin (and anti-Tg antibody) | number with unit (ng/mL) | lab | not in NCG; from the chosen open-access book |
| calcitonin | Serum calcitonin (medullary) | number with unit (pg/mL) | lab | not in NCG; from the chosen open-access book |
| tirads | TIRADS / TMC RSS score | text, as written | ultrasound | Right thyroid nodule appears benign/indeterminate/suspicious on USG with TIRADS score and TMC RSS Score (p 51) |
| extrathyroid_extension | Extrathyroid extension | categorical (absent, present, not stated) | ct, ultrasound, histopathology | Extra-thyroid extension: Absent/Present (p 48) |

### Staging system
- NCG names none for thyroid. The CT format asks for "T STAGE", "N STAGE:" and "M Stage" (p 48, 49) and gives a CT ETE grade and a Shin tracheal grade. The open-access books below use AJCC / UICC TNM (8th edition for ESMO 2019; ATA 2015 uses the 7th edition staging in force at the time, to be checked).

### Indian notes
- p 51: "Right thyroid nodule appears benign/indeterminate/suspicious on USG with TIRADS score and TMC" (the format uses a Tata Memorial Centre risk score, "TMC RSS"; this is the one Indian-origin element). The same page: "*short interval follow- up: 3 months at our institution" is on p 47 (surveillance legend).

### Regimen or dose tables
- None for thyroid in the NCG head and neck book.

### Open-access sources
Searches done on the web (no downloads). No Indian national thyroid cancer guideline (Indian Thyroid Society, ICMR, AIIMS or Tata Memorial) was found in the searches; the only India-specific item found was a 2022 paper in the Journal of Head & Neck Physicians and Surgeons on applying the 2021 ATA anaplastic thyroid cancer guideline in India (covers anaplastic only). Licences below were not all confirmable from the pages that could be opened.

| organisation | title | year | official URL | licence or terms | page numbers |
|---|---|---|---|---|---|
| American Thyroid Association | 2015 American Thyroid Association Management Guidelines for Adult Patients with Thyroid Nodules and Differentiated Thyroid Cancer (Haugen BR et al., Thyroid 26(1):1-133, DOI 10.1089/thy.2015.0020) | 2015 (published Jan 2016) | https://pmc.ncbi.nlm.nih.gov/articles/PMC4739132/ (PDF link on that page: pdf/thy.2015.0020.pdf) | Free to read on PubMed Central. The page shows "Copyright 2016, Mary Ann Liebert, Inc." and no Creative Commons licence; so reading is free, but keeping and redistributing a copy on a server is not clearly allowed and needs the publisher terms checked. | Yes, 1 to 133 |
| European Society for Medical Oncology | Thyroid cancer: ESMO Clinical Practice Guidelines for diagnosis, treatment and follow-up (Filetti S et al., Ann Oncol 30(12):1856-1883, DOI 10.1093/annonc/mdz400) | 2019 | https://esmo.org/guidelines/guidelines-by-topic/endocrine-and-neuroendocrine-cancers/thyroid-cancer (the ESMO page; the journal full text is on annalsofoncology.org, which returned an access error to the fetch tool) | The ESMO page says "All rights reserved worldwide". Annals of Oncology ESMO guidelines are, as far as known, open access under a Creative Commons licence, but this could NOT be verified from the pages that opened; check the journal page before keeping a copy. | Yes, 1856 to 1883 (28 pages) |
| European Society for Medical Oncology | ESMO Clinical Practice Guideline update on the use of systemic therapy in advanced thyroid cancer | 2022 | https://www.esmo.org/guidelines/endocrine-and-neuroendocrine-cancers/thyroid-cancer/eupdate-thyroid-cancer-treatment-recommendations | Not checked (same terms question as above). Covers systemic therapy only, not work-up. | Not checked |
| American Thyroid Association | 2021 guidelines for management of patients with anaplastic thyroid cancer, and the 2025 ATA guideline for differentiated thyroid cancer (a 2026 editorial mentions it) | 2021 / 2025 | not located | not checked; the 2025 guideline is newer than the 2015 one and may now be the better book, to be checked | not checked |

Recommendation: the ESMO 2019 guideline (Filetti et al., Annals of Oncology) as the book for the draft checklist. Reasons: it covers all four histologies (papillary and follicular, medullary, anaplastic) in one 28-page document with page numbers, it has a diagnosis and work-up section, staging (TNM) and follow-up with thyroglobulin and calcitonin, and it grades recommendations with a level of evidence, so a work-up tier can be proposed from the grade. ATA 2015 is the fallback: it is longer (133 pages), covers differentiated cancer only (medullary is a separate ATA 2015 document), and its terms (Mary Ann Liebert copyright, free on PubMed Central) are less clear for keeping a copy on a server. Both are international, not Indian; the draft must carry the label "needs a clinician's check" and the Indian layer is only the NCG head and neck imaging formats cited above. Before relying on either, the licence must be read on the publisher page.

### Open questions
- No Indian thyroid guideline was found in two searches; a targeted search (Indian Journal of Endocrinology and Metabolism, Tata Memorial Centre evidence-based management, ICMR consensus) might find one.
- The licence of the ESMO 2019 PDF and the ATA 2015 PDF could not be confirmed; the person adding the book must read the terms and keep a copy only if allowed.
- Whether the system needs separate settings for differentiated, medullary and anaplastic cancers (the book choice decides this).
- Thyroid tier letters are all proposals; NCG prints none.