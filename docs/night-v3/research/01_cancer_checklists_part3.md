# Cancer checklists research, part 3: blood cancers, paediatric, sarcoma, CNS

Files read (all under `/data/vaidyx/tb_resources/guidelines/ncg_india/`): `ncg-guidelines-for-adult-hematolymphoid-2019.pdf` (95 pages), `ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf` (66 pages), `ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf` (52 pages) and `ncg-guidelines-manual-2021.pdf` (85 pages, searched for CNS only). Text was cached once per file in `/data/vaidyx/night-v3/research_text/`. Page numbers are PDF page index + 1. For the adult and the bone books this equals the printed 'Page n of N'. For the paediatric book the printed footer ('NCG PHL AND PST 2020 n') is one less than the PDF page (PDF page 7 prints 6). Cancers covered and records proposed: lymphoma 16 (settings `adult_hodgkin`, `adult_nhl`, `child_hodgkin`, `child_nhl`), leukaemia 16 (`adult_acute`, `adult_chronic`, `child_all`, `child_aml`), Wilms tumour 8 (`unilateral`, `bilateral`), retinoblastoma 8 (`unilateral`, `bilateral`), bone sarcoma 13 (`osteosarcoma`, `ewing`, `chondrosarcoma`), soft tissue sarcoma 13 (`non_metastatic`, `metastatic`, `paediatric_rhabdomyosarcoma`), brain and CNS 0 verified records (5 skeleton rows) (NCG has no CNS file; a skeleton and the open-access source search are given).

IMPORTANT, read first. In the adult haematolymphoid book every disease flow chart (AML, APML, ALL, CLL, DLBCL, FL, MCL, MZL, HL and the others) is a picture with NO text layer; pypdf returns only the page heading. The work-up boxes with their (a)/(b)/(c) marks were read by eye from the page images (one image per flow page). Those rows are marked IMAGE in the quote column: the page is real and the tier letter is printed in the book, but there is no verifiable text line. Where a text line on another page supports the same item (annexures 1 to 3, pages 79 to 95) it is quoted instead and the image reading is given in the tier basis column without double quotes. The paediatric and bone books have a text layer for nearly everything. If the build needs every quote to be machine-verified, the adult flow pages need OCR (an OCR venv exists at `/data/vaidyx/venv/ocr`, not used here) or a manual transcription; this is listed under open questions.

Tier rule used for conditional items: where NCG prints a letter only under a condition the system never judges (for example "if indicated"), the proposed system tier is `c` (shown only) with the NCG tier under the condition named in the basis column, like the existing `condition` field.

## Lymphoma (`lymphoma`)
### Source
Adult: `ncg-guidelines-for-adult-hematolymphoid-2019.pdf`, NCG 2019 (a later reference in the file is dated 2021). Newly diagnosed work-up boxes: DLBCL page 17 (image), follicular lymphoma page 24 (image), mantle cell page 28, marginal zone page 32, Burkitt page 35, hairy cell 39, Waldenstrom 41, peripheral T 44, AITL 47, ALCL 51 and 55, NK/T 58 (all images, same box layout), Hodgkin page 61 (image) with treatment pages 62 to 65. Annexure 1 radiology synoptic and Cotswolds staging pages 83 to 86; Annexure 2 diagnostic and IHC panels pages 87 to 90; Annexure 3 flow panels pages 91 to 95.
Child: `ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf`, NCG 2019 (footer "NCG PHL AND PST 2020"). NHL diagnostic work-up, Murphy staging and treatment pages 22 to 29; Hodgkin work-up, Ann Arbor staging and treatment pages 30 to 33; appendices A to C pages 34 to 42.
How NCG splits the disease: adult book contents, page 3: "6.  Non Hodgkin’s Lymphoma 17 " and "7.  Hodgkin’s Lymphoma 61 ". The adult NHL section then lists one flow per subtype (DLBCL, follicular, mantle cell, marginal zone, Burkitt, hairy cell, Waldenstrom, PTCL NOS, AITL, ALCL ALK negative and positive, NK/T). Myeloma and plasma cell disorders are a separate chapter (page 70) and are not in this protocol. Child book contents, page 2: "NON-HODGKIN LYMPHOMA (NHL)" and "PEDIATRIC HODGKIN LYMPHOMA". The adult NHL work-up box is the same for every subtype, so one adult NHL setting is enough.

### Settings proposed
- `adult_hodgkin`: 'Adult Hodgkin lymphoma (as recorded)'. Basis: adult page 3 "7.  Hodgkin’s Lymphoma 61 ", flow page 61.
- `adult_nhl`: 'Adult non-Hodgkin lymphoma (as recorded)'. Basis: adult page 3 "6.  Non Hodgkin’s Lymphoma 17 ", flows pages 17 to 60.
- `child_hodgkin`: 'Child Hodgkin lymphoma (as recorded)'. Basis: child page 30 "PEDIATRIC HODGKIN LYMPHOMA".
- `child_nhl`: 'Child non-Hodgkin lymphoma, includes lymphoblastic lymphoma (as recorded)'. Basis: child page 22 "NON-HODGKIN LYMPHOMA (NHL)". The book does not give an age cut-off between adult and child pages (open question).
The doctor records the setting; the system never decides it.

### Work-up records
Tier letters are the book's unless the last column says proposed. Tiers are given per setting in the order AH (adult_hodgkin), AN (adult_nhl), CH (child_hodgkin), CN (child_nhl).

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_b_symptoms | History, examination, B symptoms, performance status | AH a, AN a, CH a, CN a | clinical_note, referral | owner | ecog, comorbidities, NEW:b_symptoms | 85 | "B: presence of B symptoms (including fever, night sweats and weight loss of over 10% of body" | Proposed a, first box of every flow (IMAGE pages 17, 61: Age, comorbidities and symptoms; Examination of lymph nodes, liver, spleen, performance status). Child page 30: "B symptoms (any one is sufficient)" |
| lymph_node_histopathology | Excision or core biopsy, histopathology | AH a, AN a, CH a, CN a | histopathology | Pathology | histologic_type | 88 | "Histological evaluation, i.e. biopsy as a method of investigation with comprehensive" | NCG a. Image page 17 and 61: HPE examination (a). Child page 39 "Essential: (a)" with the same text; child page 30 "Excision biopsy of a peripheral lymph node or" |
| lymphoma_ihc | Immunohistochemistry panel | AH a, AN a, CH a, CN a | ihc, histopathology | Pathology | histologic_type, ki67 | 89 | "IHC: LCA, CD20, CD3, MIB-1" | NCG Mandatory (adult) or Essential (a) (child page 40). Hodgkin: page 88 "CD3, CD20, CD30, CD15, Pax5, AE1/AE3*, ALK-1**". MIB-1 is the Ki-67 stain, so ki67 is the fact. Image page 61 reads CD45, 30, 15, 20 (a); PAX-5, CD3, CD79a (b) |
| lymphoma_molecular | FISH and molecular tests (MYC, BCL2, BCL6, others) | AH none, AN b, CH none, CN b | molecular, ihc | Pathology | NEW:molecular_markers_haem | 89 | "FISH: MYC/BCL2/BCL6 gene rearrangement" | NCG Optimal/extended work-up (b), adult page 89; child page 22 "Burkitt lymphoma t(8;14)(q24;q32) t(2;8) or t(8;22)(b)" |
| bone_marrow_lymphoma | Bone marrow aspirate and biopsy | AH c, AN b, CH b, CN a | NEW:bone_marrow, histopathology | Pathology | NEW:bone_marrow_result | 88 | "Bone marrow biopsy, aspirate and imprint smear (as listed in the algorithm" | Image page 61: bone marrow biopsy only if PET-CT not done and stage IIB or more (a), so system tier c with condition a. Image page 17 DLBCL: bone marrow biopsy (b); image page 24 follicular: for all patients except if peripheral blood is involved (a). Child page 22 "Bone marrow aspirate and biopsy (a)"; child page 30 "Bone marrow aspirate and biopsy for stage IV only (b)" |
| lymphoma_baseline_labs | CBC, ESR, kidney and liver tests, LDH, calcium, uric acid | AH a, AN a, CH a, CN a | lab | Biochemistry | haemoglobin, wbc, platelets, creatinine, bilirubin, NEW:ldh | 30 | "2 Laboratory Baseline labs CBC, Renal function test, Liver function test, serum" | Adult image pages 17, 61: INVESTIGATIONS (a) (CBC, P smear, biochemistry with RFT, LFT, albumin, LDH, SE, Ca, PO4, uric acid; blood group; viral markers). Child page 22 "2 Laboratory Baseline labs CBC, Renal function test, Liver function test, serum electrolytes LDH" |
| viral_markers_lymphoma | Viral markers (HIV, hepatitis B core antibody) | AH a, AN a, CH b, CN b | lab | Microbiology | hiv_status | 22 | "Coagulation profile, (a) Viral Markers(b)" | Adult image page 17: HBCore antibody (a) and viral markers; child page 22 prints (b). Child Hodgkin page 30 also (b) |
| staging_ct_lymphoma | CT neck, chest, abdomen, pelvis (staging) | AH a, AN a, CH a, CN a | ct | Radiology | nodal_findings, distant_findings | 83 | "CT SCAN OF NECK, CHEST, ABDOMEN AND PELVIS " | NCG a: image pages 17, 61 CECT neck chest abdomen pelvis (a). Child NHL page 22 "CT scan neck chest abdomen" (a); child Hodgkin page 30 "CT scan chest abdomen and pelvis (if PET not available)" so proposed a |
| pet_ct_lymphoma | Whole-body PET-CT | AH a, AN b, CH a, CN b | pet_ct | Nuclear Medicine | NEW:deauville_score, suv_max | 85 | "Normalization of FDG-PET (Deauville score 1–3)" | Image page 61 whole body PET-CT (a); image page 17 (b). Child page 22 "PET scan whole body (b)"; child page 30 "PET scan whole body (a)". Deauville scale child page 42 "Deauville score" |
| chest_xray_lymphoma | Chest X-ray | AH none, AN none, CH a, CN a | xray | Radiology | distant_findings | 22 | "CXR (a)" | Child NHL page 22 prints (a). Child Hodgkin page 30 "CXR" has no letter, proposed a. Not in the adult boxes |
| echo_ecg_lymphoma | Echocardiogram and ECG | AH a, AN a, CH a, CN a | NEW:echocardiogram | owner | (none) | 30 | "2D ECHO (a)" | Adult images pages 17, 61: ECG (a), ECHOcardiogram (a). Child page 22 "2 D ECHO (a)". No cardiology department exists, so route to owner |
| csf_lymphoma | CSF cytology | AH none, AN c, CH c, CN a | NEW:csf | Pathology | NEW:csf_cytology | 22 | "CSF cytospin and morphology (a)" | Child NHL (a). Adult image page 17: CSF cytology after spin (a) when indicated (high-risk sites listed in the footnote), so system tier c with condition a. Child Hodgkin page 30 "CSF cytospin and morphology only if indicated (b)" so c with condition b |
| pft_lymphoma | Lung function (PFT, DLCO) | AH b, AN none, CH none, CN none | pulmonary_function | Pulmonology | (none) | 61 | IMAGE | Image page 61: PFT, DLCO (b) |
| flow_cytometry_lymphoma | Flow cytometry (FNA, peripheral blood, pleural or ascitic fluid) | AH none, AN c, CH none, CN b | NEW:flow_cytometry | Pathology | NEW:flow_cytometry_result | 88 | "• Flow cytometric immunophenotypic evaluation" | Adult Optional/extended work-up page 88 (heading "Optional/extended work-up:", treated as c); image page 24: flow cytometry on peripheral blood presenting with lymphocytosis (a) for follicular. Child page 22 "Flowcytometry on pleural" |
| stage_as_recorded_lymphoma | Stage as recorded in a report | AH a, AN a, CH a, CN a | ct, pet_ct, clinical_note | Radiology | recorded_stage | 84 | "Cotswolds  modified Ann Arbor Staging Classification for both Hodgkin and non-Hodgkin lymphoma" | Proposed a (the board needs the stage; the system only copies a stage written in a report, never computes it) |
| fertility_semen_lymphoma | Semen cryopreservation (optional) | AH c, AN c, CH none, CN none | clinical_note, referral | owner | (none) | 61 | IMAGE | Image pages 17, 61: OPTIONAL (c) Semen cryopreservation |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:b_symptoms | B symptoms (fever, night sweats, weight loss over 10 percent in 6 months) | categorical: present, absent, not recorded | clinical_note | adult page 85 "B: presence of B symptoms (including fever, night sweats and weight loss of over 10% of body"; child page 30 "B symptoms (any one is sufficient)" |
| NEW:ldh | Serum LDH | number with unit (U/L) | lab | child page 22 "Coagulation profile, (a) Viral Markers(b)" sits after LDH in the same list; adult image INVESTIGATIONS (LDH) |
| NEW:bone_marrow_result | Bone marrow involvement as reported | categorical: involved, not involved, not stated, with the percentage as text | NEW:bone_marrow | child page 22 "• Bone marrow involvement is defined as 5% or more malignant cells the bone marrow, with" |
| NEW:molecular_markers_haem | Molecular and FISH markers as reported (MYC, BCL2, BCL6, BCR-ABL, FLT3, NPM1 and others) | text, one value per marker | molecular | adult page 89 "FISH: MYC/BCL2/BCL6 gene rearrangement" |
| NEW:deauville_score | Deauville score as reported | categorical 1, 2, 3, 4, 5 | pet_ct | child page 42 "Deauville score" |
| NEW:csf_cytology | CSF cytology | categorical: malignant cells present, absent, not done | NEW:csf | child page 23 "• CNS disease is any malignant cell present in the CSF regardless of cell count." |
| NEW:flow_cytometry_result | Flow cytometry result as reported | text | NEW:flow_cytometry | adult page 91 "Essential (a)" panel list |
New document types: NEW:bone_marrow, NEW:csf, NEW:flow_cytometry, NEW:echocardiogram (shared with leukaemia).

### Staging system
Adult: Cotswolds modified Ann Arbor for both Hodgkin and non-Hodgkin, page 84 "Cotswolds  modified Ann Arbor Staging Classification for both Hodgkin and non-Hodgkin lymphoma", with sub-stage letters A, B and X (page 85 "X: bulky nodal disease: nodal mass >1/3 of intrathoracic diameter or 10 cm in dimension"). Response uses RECIL 2017 and Deauville (page 84 "CT response assessment should be based on RECIL 2017 criteria."). The DLBCL, follicular and Hodgkin flows split early stage (I, II) and advanced stage (III, IV), page 18 "ADVANCED STAGE DISEASE (III, IV)". Hodgkin risk factors on page 62 "EARLY STAGE UNFAVORABLE STAGE I, II WITH RISK FACTORS".
Child NHL: Murphy staging, page 22 "Staging (Due to high incidence of extra-nodal disease Murphy’s staging is used for NHL)", with FAB/LMB groups A, B, C (page 23) and BFM groups R1 to R4 (page 28). Child Hodgkin: Ann Arbor, page 30 "Staging information (Ann-Arbor staging system)", bulky disease "nodal mass >6cm in longest diameter" (page 31).
Vaidyx never computes any of these; a stage is shown only as recorded in a report.

### Indian notes
- Adult flow charts carry doses for Indian practice and cite Indian series (page 12 "MCP-841: Advani S, Pai S, Venzon D, et al (1999) Acute lymphoblastic leukemia in India" is the ALL reference).
- Flow cytometry quality: page 91 refers to "Quality Control should be done as per Euroflow protocols or ICMR" (the ICMR immunophenotyping guideline).
- Resource note on pathology, page 90: "The laboratory without expertise in diagnosing hematolymphoid neoplasms and with" (it should refer the sample to a specialist lab). Child book repeats it on page 41.
- HIV-positive lymphoma has its own regimen line, page 18 "FOR HIV POSITIVE LYMPHOMA ".
- Child NHL regimens name the Indian protocol MCP-842, page 23 "MCP-842 (4 to 6 cycles)".
- Methotrexate level monitoring needs facilities (image page 17 footnote 2: creatinine clearance, third space, methotrexate level, in-patient beds). No PM-JAY text in these books.

### Regimen or dose tables
Adult: DLBCL pages 17 to 21 (R-CHOP and variants; DLBCL relapsed 22 to 23); follicular 25 to 27; mantle 29 to 31; marginal zone 33 to 34; Burkitt 36 to 37; hairy cell 40; Waldenstrom 42 to 43; PTCL 45 to 46; AITL 48 to 50; ALCL 52 to 54 and 56 to 57; NK/T 59 to 60; Hodgkin 62 to 65 and relapsed 67 to 69. Child: NHL page 23 to 28; Hodgkin pages 31 to 33 (protocol doses page 32); radiotherapy page 33.

### Open questions
- The adult flow boxes are images (see the note at the top); every adult tier marked IMAGE needs OCR or manual transcription before the build can carry a verbatim quote.
- No age cut-off between the adult and the child book is stated in either file.
- Adult Hodgkin, adult NHL: the book gives a different box per subtype only for the treatment, not the work-up; I read DLBCL (page 17), follicular (24), mantle (28) and Hodgkin (61) images and the common box is the same. Burkitt, T-cell and NK/T boxes (pages 35 to 58) were not viewed.
- Myeloma and plasma cell disorders (page 70 onwards) are not covered by a protocol id here.
- Child lymphoblastic lymphoma follows the leukaemia pathway (child page 28); it is included in `child_nhl`, not in `leukaemia`.

## Leukaemia (`leukaemia`)
### Source
Adult: `ncg-guidelines-for-adult-hematolymphoid-2019.pdf` (NCG 2019). AML (non APML) work-up and flow page 5 (image), risk table and induction page 6, unfit page 7; APML page 8 (image) and 9 to 10; ALL page 11 (image) with references on page 12; CLL page 13 (image) and treatment 14 to 15; CML page 16 (regimens only, no work-up box). Flow cytometry panels, annexure 3, pages 91 to 95.
Child: `ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf` (NCG 2019). ALL work-up and flow page 7, footnotes page 8, risk and regimens pages 9 to 12; AML work-up page 13, regimens and risk 14; APML page 15 to 16; CML work-up and monitoring pages 17 to 19; Langerhans cell histiocytosis pages 19 to 21 (not part of this protocol); flow appendix pages 34 to 38.
How NCG splits the disease: adult contents, page 3: "1.  Acute Myeloid Leukemia 05", "2.  Acute Promyelocytic Leukemia 08", "3.  Acute Lymphoblastic Leukemia 11", "4.  Chronic Lymphoid Leukemia 13", "5.  Chronic Myeloid Leukemia 16". Child contents, page 2: "PEDIATRIC ACUTE LYMPHOBLASTIC LEUKEMIA", "PEDIATRIC ACUTE MYELOID LEUKEMIA", "PEDIATRIC CHRONIC MYELOID LEUKEMIA"; child APML is run on the AML pathway (page 15 "Treatment Algorithm: Newly diagnosed APML  (start from AML pathway)").

### Settings proposed
At most four, so the diseases are grouped. Where the book gives different letters to two diseases inside one setting, the tier below is the highest one and the lower is in the basis column.
- `adult_acute`: 'Adult acute leukaemia: AML, APML or ALL (as recorded)'. Basis: adult page 3 contents entries 1 to 3; images pages 5, 8, 11.
- `adult_chronic`: 'Adult chronic leukaemia: CLL or CML (as recorded)'. Basis: adult page 3 "4.  Chronic Lymphoid Leukemia 13", "5.  Chronic Myeloid Leukemia 16". Child CML (child page 17) has no setting of its own and is also read under this one (see open questions).
- `child_all`: 'Child acute lymphoblastic leukaemia (as recorded)'. Basis: child page 2 "PEDIATRIC ACUTE LYMPHOBLASTIC LEUKEMIA".
- `child_aml`: 'Child acute myeloid leukaemia, includes APML (as recorded)'. Basis: child page 2 "PEDIATRIC ACUTE MYELOID LEUKEMIA", page 15.

### Work-up records
Setting columns: AA adult_acute, AC adult_chronic, CA child_all, CM child_aml.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_exam_leukaemia | History, examination (CNS, testis, nodes, liver, spleen), performance status | AA a, AC a, CA a, CM a | clinical_note, referral | owner | ecog, comorbidities | 7 | "CNS, Lymph nodes, Liver, Spleen, Testes" | Proposed a, first box of every flow. Image pages 5, 11, 13 list examination and performance status; child AML page 13 adds "Gum hypertrophy, Presence of skin lesions" |
| cbc_smear | CBC and peripheral smear with MPO | AA a, AC a, CA a, CM a | lab | Pathology | haemoglobin, wbc, platelets | 91 | "1. Smears stained with a Romanowsky stain and Myeloperoxidase or Sudan Black B" | Adult images pages 5, 11, 13: CBC, P smear, MPO (AML). Child page 7 "CBC, peripheral smear, blood group," and page 13 "CBC, peripheral smear, MPO stain, Renal". Proposed a (no letter) |
| biochemistry_ldh_leukaemia | Kidney, liver, electrolytes, LDH, calcium, phosphate, uric acid | AA a, AC a, CA a, CM a | lab | Biochemistry | creatinine, bilirubin, NEW:ldh | 7 | "Test(LFT), Serum electrolyte, LDH" | ALL image page 11 prints (a) after viral markers on this list; AML image page 5 lists LDH, SE, Ca, PO4, uric acid without a letter, proposed a; CLL image page 13 lists the same |
| coagulation_leukaemia | Coagulation profile, fibrinogen | AA a, AC none, CA a, CM a | lab | Pathology | (none) | 7 | "Coagulation profile(a), Viral markers(b)" | Child ALL (a) here and child AML page 13 "Coagulation profile, (a),". Adult APML image page 8: coagulation profile and fibrinogen (a). Child APML page 15 "CBC, peripheral smear, coagulation profile including" |
| viral_markers_leukaemia | Viral markers (HIV, hepatitis) | AA a, AC a, CA b, CM b | lab | Microbiology | hiv_status | 13 | "Viral markers(b) " | Child printed (b) on pages 7 and 13. Adult ALL image page 11 viral markers (a); adult AML and CLL images list it without a letter, proposed a |
| bone_marrow_leukaemia | Bone marrow aspirate, biopsy, morphology (peripheral blood if too unstable or high counts) | AA a, AC none, CA a, CM a | NEW:bone_marrow, histopathology | Pathology | NEW:bone_marrow_result | 7 | "Bone marrow/peripheral blood if child" | Child page 7 and 13 same words, no letter on the heading, proposed a. Adult AML image page 5 flow cytometry and immunocytochemistry (a), peripheral blood if high counts (b). CLL image page 13: bone marrow is not required unless done for work-up of CLPD or unexplained cytopenias, so none |
| flow_cytometry_acute | Flow cytometry immunophenotype (acute leukaemia panel; CLL peripheral blood) | AA a, AC a, CA a, CM a | NEW:flow_cytometry | Pathology | NEW:flow_cytometry_result | 91 | "Essential (a)" | Adult page 91 panel heading "2. Acute Leukemia- Essential panel"; child page 34 "A. Acute Leukemia - Essential panel (a)". CLL image page 13: peripheral blood flow cytometry (a). Child ALL page 7 "Baseline ALL panel (a) + ploidy(DNA" |
| cytogenetics_fish | Karyotype and FISH (BCR-ABL, PML-RARA, ETV6-RUNX1, 11q23, 17p, 5q, 7q) | AA a, AC a, CA a, CM a | NEW:cytogenetics, molecular | Pathology | NEW:cytogenetics_result | 7 | "Cytogenetics (a) karyotyping for" | Child ALL page 7 (a); child AML page 13 "Cytogenetics combination of conventional" (a). Adult AML image page 5 conventional cytogenetics (a), t(8;21), inv(16), PML-RARA, BCR-ABL (a), 5q 7q 17p (b); adult ALL image page 11 cytogenetics (b), BCR-ABL (a), MLL (b), so the adult acute tier is the highest (a). CLL image page 13: del 17p or p53 mutation by FISH (a), del 11q, trisomy 12, del 13q (b). APML child page 15 "Diagnosis by FISH for PML-RARA (a)" |
| molecular_markers_leukaemia | Molecular tests (NPM1, FLT3, CEBPA, KIT, BCR-ABL RQ-PCR, IgHV) | AA a, AC a, CA b, CM b | molecular | Pathology | NEW:molecular_markers_haem | 13 | "FLT3-ITD, NPM1 mutation Biallelic mutation" | Child AML printed (b) on that block; child ALL page 7 "Molecular PCR studies as indicated (b)". Adult AML image page 5: NPM, Flt3 by fragment length analysis (a). CML: child page 17 "RT/RQ-PCR (a)" at baseline (adult CML has no work-up box). CLL IgHV (c) |
| csf_leukaemia | CSF cell count and cytospin | AA a, AC none, CA a, CM a | NEW:csf | Pathology | NEW:csf_cytology | 7 | "CSF studies cell count + cytospin (a)" | Child AML page 13 "CSF studies cell count + cytospin at baseline" (a). Adult ALL image page 11: CSF cytomorphology (a). Adult AML image page 5 lists CNS examination only |
| echo_leukaemia | 2-D echocardiogram | AA a, AC none, CA b, CM a | NEW:echocardiogram | owner | (none) | 13 | "2-D ECHO (a)" | Child ALL page 7 "2D-ECHO (b)". Adult AML and ALL images: 2-D echocardiography (a). No cardiology department, route to owner |
| chest_imaging_leukaemia | Chest X-ray (CT thorax for child AML and CLL when indicated) | AA a, AC b, CA a, CM a | xray, ct | Radiology | distant_findings | 7 | "Chest Radiograph (a)" | Child AML page 13 "Chest Radiograph (a)" and "CT scan thorax (b)". Adult ALL image page 11 chest X-ray (a); AML image page 5 chest X-ray or NCCT chest (a). CLL image page 13: CXR and USG abdomen and pelvis if treatment is indicated (a), CECT chest, abdomen, pelvis if therapy is indicated (b), PET-CT not indicated unless Richter transformation is suspected. AC tier b is the CT line, the plain X-ray is conditional on therapy |
| hla_typing_leukaemia | HLA typing and transplant work-up | AA b, AC none, CA none, CM b | lab | Haematology | (none) | 13 | "HLA typing upfront" | Adult AML image page 5: HLA typing (b). Child AML page 13 prints transplant counselling and work-up (a) only for patients not in remission and for high-risk AML; proposed b at baseline |
| mrd_leukaemia | Minimal residual disease by flow or PCR | AA b, AC c, CA a, CM b | NEW:flow_cytometry, molecular | Pathology | NEW:flow_cytometry_result | 94 | "7. B-ALL MRD" | Adult annexure 3 pages 94 to 95 (B-ALL, T-ALL, AML MRD panels with (a)(b)(c) columns). Image page 11 MRD panel (b), page 5 MRD panel (c), page 13 MRD panel (c). Child page 7 "If MRD> 0.01% at" drives risk, and child page 2 lists the B-ALL MRD panel as Essential (a) + Optional (c). Follow-up item, not a baseline requirement |
| testicular_assessment | Testicular ultrasound or biopsy | AA none, AC none, CA c, CM c | ultrasound | Radiology | (none) | 7 | "USG/testicular biopsy when indicated" | No letter; child ALL "when indicated", so c. Child AML page 13 "USG/testicular biopsy when indicated (b)" so c with condition b |
| cll_special_labs | Coombs test, beta-2 microglobulin, immunoglobulin levels | AA none, AC b, CA none, CM none | lab | Biochemistry | NEW:beta2_microglobulin | 13 | IMAGE | CLL image page 13: Coomb's test (a) if hemolysis is suspected, beta-2 microglobulin (b), immunoglobulin levels (b); system tier b for the group, Coombs is conditional |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:bone_marrow_result | Bone marrow findings as reported (blast percentage, involvement) | text with blast percentage as number | NEW:bone_marrow | child page 18 "Bone marrow blasts <10%" (CML phases) and page 22 child NHL involvement definition |
| NEW:flow_cytometry_result | Flow cytometry immunophenotype as reported | text | NEW:flow_cytometry | adult page 91 "Essential (a)" panel |
| NEW:cytogenetics_result | Karyotype and FISH findings as reported | text, one line per abnormality | NEW:cytogenetics | child page 13 "t(8;21) RUNX1-RUNX1T1" and page 7 "Cytogenetics (a) karyotyping for" |
| NEW:molecular_markers_haem | Molecular markers as reported (shared with lymphoma) | text | molecular | child page 13 "FLT3-ITD, NPM1 mutation Biallelic mutation" |
| NEW:ldh | Serum LDH (shared with lymphoma) | number with unit | lab | child page 7 "Test(LFT), Serum electrolyte, LDH" |
| NEW:csf_cytology | CSF cytology and cell count (shared) | categorical: malignant cells present, absent, not done | NEW:csf | child page 7 "CSF studies cell count + cytospin (a)" |
| NEW:beta2_microglobulin | Beta-2 microglobulin | number with unit | lab | CLL image page 13 only |
New document types: NEW:bone_marrow, NEW:flow_cytometry, NEW:cytogenetics, NEW:csf, NEW:echocardiogram.

### Staging system
Leukaemia has no stage. The books name risk groups; the system only records them if a report states them.
- Adult AML: favourable, intermediate, poor risk by cytogenetics and molecular, page 6 "Favorable risk", "Poor risk", "Complex (>3 abnormalities)".
- Adult ALL: standard or high risk from the flow footnote (image page 11: Ph or BCR-ABL positive, MLL rearrangement, age over 35, WBC cut-offs, CNS positive).
- Adult CLL: need for therapy and fitness only (image page 13 footnotes); Rai and Binet are not named in the text or in the image.
- Child ALL: standard, intermediate, high risk with age, WBC, cytogenetics, steroid response, MRD (page 9, "Standard Risk", "Intermediate risk", "High risk"); child AML: standard, intermediate, high risk (page 14, "Standard risk Based on cytogenetics and M1 marrow"); child CML: chronic, accelerated, blast phase (page 18 "Chronic Phase").
- ELN and WHO are not named in these books.

### Indian notes
- Page 12 (adult) cites Indian protocols: "MCP-841: Advani S, Pai S, Venzon D, et al (1999) Acute lymphoblastic leukemia in India" and the Indian GMALL series (page 12 "GMALL: Bajel A, George B, Mathews V, Viswabandya A, Kavitha ML, Srivastava A, Chandy M (2007)").
- Adult ALL image page 11 allows an unfit or elderly Ph negative patient palliative care or oral therapy with best supportive care.
- Page 91 points to the ICMR flow cytometry guideline for processing and quality control.
- AML centre expertise: image page 5 (treatment preferably in centres with expertise in AML, (a)); the child equivalent is page 15 "Refer to center with expertise in".
- MRD labs: page 94 "Should be done in a laboratory with workload of minimum 30 acute leukemia samples per month". No PM-JAY text.

### Regimen or dose tables
Adult: AML pages 6 to 7; APML 9 to 10; ALL page 12 (references only; protocol names in image page 11); CLL 14 to 15; CML 16. Child: ALL pages 9 to 12; AML 14; APML 15 to 16; CML 19; Langerhans 20 to 21.

### Open questions
- Adult leukaemia work-up boxes are images; letters were read by eye (see top note). Pages 5, 8, 11, 13 need OCR or transcription for verbatim quotes.
- Adult CML (page 16) has regimens only, no work-up box; baseline CML work-up (FISH, RQ-PCR, bone marrow) comes only from child page 17. A clinician should say whether to use the child list for adults.
- Child CML and child APML have no setting of their own (setting cap of four).
- Where adult ALL and AML differ in letter inside `adult_acute`, a single tier hides it; the build could split by recorded disease if a field is added.
- The adult book names no Rai or Binet stage and no ELN risk set.

## Wilms tumour (`wilms`)
### Source
`ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf` (NCG 2019). Wilms algorithm page 44 (printed 43); chemotherapy and SIOP note page 45; risk stratification, staging and radiotherapy pages 46 to 47; Annexure 1 diagnostic table page 64; the pathology reporting proforma for paediatric renal tumours is listed in the contents (page 4) but the annexure 3 text is not in this file ("Error! Bookmark not defined." in the contents).
How NCG splits the disease (page 44): the algorithm opens with "Unilateral Renal Mass" and "Bilateral Renal Mass", each with its own treatment line; unilateral is further split into resectable and borderline or unresectable (or stage 4) on imaging.

### Settings proposed
- `unilateral`: 'Unilateral renal mass, suspected Wilms tumour (as recorded)'. Basis: page 44 "Unilateral Renal Mass".
- `bilateral`: 'Bilateral renal mass, suspected Wilms tumour (as recorded)'. Basis: page 44 "Bilateral Renal Mass".

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_exam_wilms | History and examination (abdominal mass, urine, blood pressure) | unilateral a, bilateral a | clinical_note, referral | owner | comorbidities, clinical_question | 44 | "Suspected Wilms Tumour" | Proposed a; the book has no history box for Wilms. Blood pressure and urine are not named, so only history and examination are proposed |
| usg_abdomen_wilms | Ultrasound abdomen | unilateral a, bilateral a | ultrasound | Radiology | lesion_size | 44 | "Essential: US abdomen, CT scan thorax, abdomen and pelvis (a)," | NCG a. Annexure 1 page 64 "USG abdomen to be part of basic diagnostic workup" |
| ct_thorax_abdomen_pelvis_wilms | CT thorax, abdomen and pelvis | unilateral a, bilateral a | ct | Radiology | lesion_size, nodal_findings, distant_findings | 64 | "Wilms Tumor  CT scan thorax, abdomen and pelvis  USG doppler" | NCG a, page 44 same line as above; page 64 table row |
| usg_doppler_wilms | Ultrasound doppler (vessels, vena cava) | unilateral b, bilateral b | ultrasound | Radiology | (none) | 44 | "Optimal: USG doppler, MRI for Bilateral WT and nephroblastomatosis (b)" | NCG b |
| mri_bilateral_wilms | MRI for bilateral Wilms tumour and nephroblastomatosis | unilateral none, bilateral b | mri | Radiology | lesion_size | 44 | "Optimal: USG doppler, MRI for Bilateral WT and nephroblastomatosis (b)" | NCG b; the text ties MRI to bilateral disease |
| biopsy_wilms | Image-guided core biopsy or FNAC (borderline or unresectable) | unilateral c, bilateral none | histopathology, cytology | Pathology | histologic_type | 44 | "Optional: Image guided core" | The text prints "Optional" with (b); system tier c as it applies only to borderline or unresectable disease (condition ncg_tier b) |
| nephrectomy_histopathology | Histopathology of the nephrectomy: histology type, anaplasia, surgico-pathologic stage | unilateral a, bilateral a | histopathology | Pathology | histologic_type, recorded_stage, margins, NEW:anaplasia | 44 | "Surgico-pathologic stage assessment*" | Proposed a (post-surgery record); anaplasia labels page 45 "DA- diffuse anaplasia, FA-focal anaplasia" |
| loh_1p_16q | LOH 1p/16q and 1p gain | unilateral c, bilateral c | molecular | Pathology | NEW:loh_1p_16q | 44 | "Optional: LOH1p/16q and 1p gain (c)" | NCG c |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:anaplasia | Anaplasia as reported | categorical: none, focal, diffuse, not stated | histopathology | page 45 "DA- diffuse anaplasia, FA-focal anaplasia" |
| NEW:loh_1p_16q | LOH 1p/16q and 1p gain | text | molecular | page 44 "Optional: LOH1p/16q and 1p gain (c)" |
Histology (favourable, focal anaplasia, diffuse anaplasia) can use `histologic_type`; the stage as written uses `recorded_stage`.

### Staging system
Surgico-pathologic stages 1 to 5, page 46: "Stage 5 Bilateral renal involvement at diagnosis." (stage 1 to 4 on the same page, "Staging of Wilms Tumour"). The book is COG-style with a note for SIOP centres, page 45 "In centres adopting the SIOP approach to management of Wilms tumor, post-operative chemotherapy is". Risk groups (low, intermediate, high) on page 46 "Risk Stratification". Favourable histology (FH), focal anaplasia (FA) and diffuse anaplasia (DA) are the histology labels used in the algorithm. Vaidyx never computes these.

### Indian notes
- Page 45 gives a resource-sensitive observation line ("Tumours weighing <550g in children aged <24 months and with favorable histology may be observed" after surgery) and a SIOP-approach alternative. Page 47 "3D Conformal RT and Intensity Modulated RT are standard forms of delivery of RT in children with" Wilms tumour. No PM-JAY text.

### Regimen or dose tables
Chemotherapy and regimens page 45; risk-stratified regimen table page 46; radiotherapy dose table pages 46 to 47.

### Open questions
- No baseline blood tests (CBC, kidney function, urine) are listed for Wilms in this book; only imaging and tissue.
- The paediatric renal tumour pathology proforma (annexure 3) is in the contents but not in the file text.
- Timing of the "CT Scan for reassessment" after chemotherapy (page 44) is a follow-up step, not a baseline record.

## Retinoblastoma (`retinoblastoma`)
### Source
`ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf` (NCG 2019). Work-up and intraocular grouping pages 52 to 53 (printed 51 to 52); unilateral algorithm page 54; bilateral algorithm page 55; chemotherapy, adjuvant indications and radiotherapy page 56; Annexure 1 row page 64.
How NCG splits the disease: page 52 "Unilateral RB" and "Bilateral RB" under "Intraocular Mass (Suspected Retinoblastoma)"; extra-ocular disease is a branch inside each (page 54 "Extraocular disease: 12 cycles of chemotherapy(VEC), Secondary Enucleation ( after 2-4 cycles) and EBRT").

### Settings proposed
- `unilateral`: 'Unilateral retinoblastoma (as recorded)'. Basis: page 52 "Unilateral RB"; algorithm page 54.
- `bilateral`: 'Bilateral retinoblastoma (as recorded)'. Basis: page 52 "Bilateral RB"; algorithm page 55.

### Work-up records
There is no ophthalmology department; the eye examination routes to owner, and a new document type NEW:ophthalmology_note carries the examination.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| eye_exam_eua | Examination under anaesthesia, eye findings and intraocular group as recorded | unilateral a, bilateral a | NEW:ophthalmology_note | owner | NEW:ophthalmic_examination, NEW:rb_group | 52 | "Essential: B scan Ultrasound, MR Orbit + Screening Brain, Examination under Anaesthesia (a)" | NCG a. The group labels are on page 52 "Grouping for Intraocular Retinoblastoma" |
| b_scan_ultrasound | B-scan ultrasound of the eye | unilateral a, bilateral a | ultrasound | Radiology | lesion_size | 52 | "Essential: B scan Ultrasound, MR Orbit + Screening Brain, Examination under Anaesthesia (a)" | NCG a |
| mri_orbit_brain | MRI orbit with screening of the brain | unilateral a, bilateral a | mri | Radiology | distant_findings | 64 | "MR Orbit + Screening Brain" | NCG a, page 52 same line |
| bone_marrow_csf_rb | Bilateral bone marrow aspirate or biopsy and CSF cytology (extra-ocular disease or optic nerve involvement) | unilateral c, bilateral c | NEW:bone_marrow, NEW:csf | Pathology | NEW:bone_marrow_result, NEW:csf_cytology | 52 | "In extra-ocular disease or optic nerve involvement: B/L Bone Marrow aspirate/biopsy, CSF cytology (a)" | System tier c with condition (a), because the system does not judge extra-ocular disease |
| germline_ngs | Germline mutation test (NGS) | unilateral b, bilateral b | molecular | Medical Genetics | NEW:germline_result | 52 | "Optimal: NGS for Germ Line Mutation (b)" | NCG b |
| ct_orbit_rb | CT orbit with screening of the brain | unilateral c, bilateral c | ct | Radiology | (none) | 52 | "Optional: CT Orbit + Screening Brain (c)" | NCG c |
| genetic_counselling_rb | Genetic counselling of the family | unilateral a, bilateral a | clinical_note, referral | Medical Genetics | (none) | 53 | "Genetic counseling needs to be done in all families, with genetic testing indicated in cases of suspected" | Proposed a, the book says "needs to be done in all families" (no letter). Sibling screening, same page: "Screening of all siblings less than 7 years of age should be done" |
| enucleation_histopathology | Histopathology after enucleation (optic nerve, choroid, sclera) | unilateral b, bilateral b | histopathology | Pathology | histologic_type, margins | 56 | "Indications for Adjuvant Chemotherapy:" | Proposed b; the adjuvant indications (page 56) depend on pathology. Post-surgery record |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:ophthalmic_examination | Eye examination findings (as written: tumour size, seeding, subretinal fluid, anterior segment) | text | NEW:ophthalmology_note | page 52 "Essential: B scan Ultrasound, MR Orbit + Screening Brain, Examination under Anaesthesia (a)" |
| NEW:rb_group | Intraocular group as recorded (A, B, C, D, E, per eye) | categorical A to E, per eye | NEW:ophthalmology_note | page 52 "Grouping for Intraocular Retinoblastoma" |
| NEW:germline_result | Germline test result | text | molecular | page 52 "Optimal: NGS for Germ Line Mutation (b)" |
| NEW:bone_marrow_result, NEW:csf_cytology | shared with leukaemia | | | see leukaemia |
New document types: NEW:ophthalmology_note (and the shared NEW:bone_marrow, NEW:csf).

### Staging system
The book uses an intraocular grouping A to E (page 52 "Group A Small tumors away from foveola and disc", "Group E  Presence of any one or more of these poor prognosis features" on page 53) and refers to extra-ocular disease and "Stage 4 Bone Marrow disease" and "Stage 4 Central nervous system disease" (page 56). The words International Classification of Retinoblastoma do not appear; the grouping is the A to E scheme. Vaidyx never assigns the group; it copies the group written in the examination note.

### Indian notes
- Page 56 "Stage 4 Central nervous system disease." is to be decided "case-to case basis by MDT. To consider palliation".
- Page 55 "To consider ophthalmic artery chemoinfusion/ intra-arterial chemotherapy case to case basis and" where expertise is available (resource note). No PM-JAY text.

### Regimen or dose tables
Chemotherapy details and doses page 56 (VEC, doses, adjuvant radiotherapy doses); algorithms pages 54 to 55.

### Open questions
- No ophthalmology department in the hospital list; the owner must confirm that routing to owner is acceptable.
- No baseline blood tests are listed for retinoblastoma.
- Pathology synoptic form for retinoblastoma is not in this file.

## Bone sarcoma (`bone_sarcoma`)
### Source
`ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf` (NCG 2019, 52 pages, printed page = PDF page). Evaluation of suspected bone sarcoma page 4 (image flow); osteosarcoma pages 7 to 11 (work-up page 7, treatment pages 8 to 9, chemotherapy page 10, radiotherapy page 11); Ewing sarcoma pages 12 to 16 (work-up page 12); chondrosarcoma pages 17 to 19; surveillance page 24; appendix 1 principles and staging work-up pages 25 to 32; appendix 2 imaging pages 33 to 36; appendix 4 bone pathology format pages 38 to 40.
How NCG splits the disease: contents page 3: "4.  Osteosarcoma  ", "5.  Ewing’s Sarcoma   ", "6.  Chondrosarcoma " (each with work-up for diagnosis, work-up for staging, then non-metastatic and metastatic presentation).

### Settings proposed
- `osteosarcoma`: 'Osteosarcoma (as recorded)'. Basis: page 7 "OSTEOSARCOMA".
- `ewing`: 'Ewing sarcoma (as recorded)'. Basis: page 12 "EWING’s SARCOMA".
- `chondrosarcoma`: 'Chondrosarcoma (as recorded)'. Basis: page 17 "CHONDROSARCOMA". (The task named osteosarcoma and Ewing; chondrosarcoma is a third section of the same book and can be dropped.)
Non-metastatic and metastatic are not settings: the work-up is common and the split follows staging.

### Work-up records
| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_exam_bone | Detailed clinical history and examination (pain, swelling, pathological fracture) | osteosarcoma a, ewing a, chondrosarcoma a | clinical_note, referral | owner | ecog, presenting_complaint | 7 | "Detailed clinical history" | Proposed a, first box of each flow (image page 4, detailed history and clinical examination) |
| radiographs_bone | Plain radiographs of the lesion and chest X-ray | osteosarcoma a, ewing a, chondrosarcoma a | xray | Radiology | lesion_size | 7 | "Basic imaging (local & chest x-ray) & routine blood investigations (a)" | NCG a. Appendix 2 page 33 radiograph "first line of imaging in evaluation" |
| routine_blood_bone | Routine blood investigations | osteosarcoma a, ewing a, chondrosarcoma a | lab | Biochemistry | haemoglobin, wbc, platelets, creatinine, bilirubin | 7 | "Basic imaging (local & chest x-ray) & routine blood investigations (a)" | NCG a (same line) |
| mri_local_bone | MRI with contrast of the entire bone with adjoining joints | osteosarcoma a, ewing a, chondrosarcoma a | mri | Radiology | lesion_size | 7 | "Local 3D imaging - MRI (with contrast) of entire bone with adjoining joints (a)" | NCG a; the alternative line is X-ray and dynamic contrast MRI with diffusion (b) |
| alp_ldh_bone | Alkaline phosphatase and LDH | osteosarcoma a, ewing a, chondrosarcoma none | lab | Biochemistry | NEW:alkaline_phosphatase, NEW:ldh | 7 | "Additional serological investigations (alkaline phosphatase and lactate dehydrogenase) (a)" | NCG a for osteosarcoma and Ewing (page 12 same words); not in the chondrosarcoma flow |
| biopsy_bone | Core needle biopsy and histopathology | osteosarcoma a, ewing a, chondrosarcoma a | histopathology | Pathology | histologic_type, grade, margins | 7 | "Biopsy (core needle biopsy preferred) (a)" | NCG a. Appendix 4 format page 38 "Histologic Subtype (According to WHO Classification of Bone Tumours):" |
| ihc_bone | Immunohistochemistry | osteosarcoma c, ewing a, chondrosarcoma none | ihc | Pathology | histologic_type | 12 | "Histopathological diagnosis with IHC (a) AND Molecular Pathology (c)" | Ewing a (page 12); osteosarcoma page 7 "Histopathological diagnosis (Use of Immunohistochemistry where applicable- (c)" |
| molecular_ewing | Molecular pathology (EWSR1, EWS-FLI1 and other fusions) | osteosarcoma none, ewing c, chondrosarcoma none | molecular | Pathology | NEW:sarcoma_fusion | 12 | "Histopathological diagnosis with IHC (a) AND Molecular Pathology (c)" | NCG c. Appendix 4 page 39 "Type of tests: (Interphase cytogenetics) FISH test EWSR1, etc." |
| ct_chest_bone | Non-contrast CT chest | osteosarcoma a, ewing a, chondrosarcoma a | ct | Radiology | distant_findings | 26 | "Osteosarcoma and chondrosarcoma are staged with non-contrast CT scan (NCCT)" | NCG a on that line group; osteosarcoma page 7 "(NCCT scan chest & Bone scan) (a)"; chondrosarcoma page 17 prints CT chest without a letter (bone scan (c)), proposed a |
| bone_scan_bone | Bone scan (skeletal metastases) | osteosarcoma a, ewing a, chondrosarcoma c | bone_scan | Nuclear Medicine | distant_findings | 36 | "Radionuclide bone scan do not aid diagnosis of bone tumours, however remains the primary" | Page 36 continues "(a)" for the screening role. Ewing may use PET instead (page 12). Chondrosarcoma page 17 "Bone scan –(c) in primary cases)" |
| bone_marrow_ewing | Bone marrow aspiration from two sites (bilateral) | osteosarcoma none, ewing a, chondrosarcoma none | NEW:bone_marrow | Pathology | NEW:bone_marrow_result | 12 | "Non-Contrast Computed Tomography of Chest AND Bone Scan AND Bone Marrow" | NCG a; line continues "Aspiration (2 sites-Bilateral) (a)". PET is an alternative: page 12 "FDG PET Scan with Breath Hold CT Chest (a)" |
| pet_ct_bone | FDG PET-CT with breath-hold CT chest | osteosarcoma c, ewing a, chondrosarcoma none | pet_ct | Nuclear Medicine | suv_max, distant_findings | 12 | "FDG PET Scan with Breath Hold CT Chest (a)" | Ewing a as an alternative to CT + bone scan + marrow; osteosarcoma page 7 "Or - (c) -F18 PET/EDF PET -with breath hold chest CT Scan)"; appendix 2 page 36 "PET scan is helping in staging sarcomas. FDG or F-18 PET scan are utilized. (c)" |
| baseline_organ_function_bone | Baseline kidney, heart and hearing assessment before chemotherapy | osteosarcoma a, ewing a, chondrosarcoma none | lab, NEW:echocardiogram, NEW:audiometry | Biochemistry | creatinine, bilirubin | 28 | "Baseline assessment of renal, cardiac and auditory function - (CBC, RFT, LFT, SE," | No letter; proposed a because multiagent chemotherapy is (a) (page 27 "Multiagent chemotherapy is the stand ard of care in osteosarcoma"). Echo and audiometry go to owner (no cardiology or audiology department) |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:alkaline_phosphatase | Serum alkaline phosphatase | number with unit (U/L) | lab | page 7 "Additional serological investigations (alkaline phosphatase and lactate dehydrogenase) (a)" |
| NEW:ldh | Serum LDH (shared) | number with unit | lab | same line |
| NEW:sarcoma_fusion | Fusion or translocation test result (EWSR1, EWS-FLI1, SYT-SSX, PAX3-FKHR) | text | molecular | page 39 "Molecular by RT-PCR: EWS-FLI1, EWS-ERG, etc SYT-SSX, SYT-SSX1, SYT-SSX2, EWS-WT1," |
| NEW:percent_necrosis | Tumour necrosis after chemotherapy | number, percent | histopathology | page 39 "Percentage necrosis (post chemotherapy treated resection specimens):" (follow-up record, not baseline) |
New document types: NEW:bone_marrow (shared), NEW:echocardiogram (shared), NEW:audiometry.

### Staging system
The bone book gives no Enneking and no AJCC bone table. Pathology format page 39: "TNM Tumour Stage:  T/N/M (to type) / Cannot be ascertained." The TNM table printed in the bone pathology section on page 40 (T1 ≤ 8 cm, T2 > 8 cm, superficial or deep, stages IA to IV by grade) is the same table used for soft tissue (page 43). The book also uses metastatic or non-metastatic at presentation and oligometastatic (page 9 "(Oligometastatic -  and/or Deemed inoperable"). Vaidyx never computes a stage.

### Indian notes
- Page 8 resource note: "MAP regimen should only be administered in centers with adequate facility for" monitoring methotrexate levels.
- Page 25 "Any suspicious lesion (see below) in the bone or soft tissue should be referred to a" "specialized sarcoma care unit for better outcomes."
- Page 27: PET is described for soft tissue as "metastatic workup but is not cost effective and yet not recommended as standard of".
- Page 28 fertility: "Counselling for Sperm banking for male patients of reproductive age while using". No PM-JAY text.
- Pathological fracture rule, page 28 "Internal fixation of pathological fracture through a sarcoma should not be" done (record the fracture in the note).

### Regimen or dose tables
Chemotherapy: osteosarcoma page 10, Ewing page 15, appendix 5 pages 44 to 49; radiotherapy: osteosarcoma page 11, Ewing page 16, chondrosarcoma page 19, appendix 6 pages 50 to 52.

### Open questions
- The suspected bone sarcoma flow (page 4) is an image but short, and was read: history, radiograph, MRI, biopsy, then the specific sarcoma guideline.
- Pathology appendix 4 contains a TNM table with soft tissue T cut-offs under the bone format; the bone book has no bone-specific stage table.
- Paediatric overlap: Ewing sarcoma and osteosarcoma are not in the paediatric book (it covers soft tissue only through rhabdomyosarcoma, see next section). The bone book gives no age rule (image page 4: symptomatic bone lesion, pain or swelling, under 40 years).

## Soft tissue sarcoma (`soft_tissue_sarcoma`)
### Source
`ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf` (NCG 2019). Evaluation of a soft tissue neoplasm page 5 (image); extremity soft tissue sarcoma work-up page 20, non-metastatic page 21, metastatic page 22, chemotherapy and radiotherapy page 23; surveillance page 24; staging work-up pages 26 to 27; pathology format and TNM, FNCLCC grading pages 41 to 43.
Paediatric overlap: `ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf`, rhabdomyosarcoma pages 59 to 62 (work-up page 59, staging and risk page 61, Annexure 1 row page 64). Note that the RMS heading on page 59 reads "Treatment Algorithm: Neuroblastoma" (a typing slip in the book).
How NCG splits the disease: contents page 3: "7.  Extremity Soft Tissue Sarcoma " only; no retroperitoneal, trunk or visceral sarcoma flow exists. Within it page 20 "Non- metastatic soft tissue sarcoma" and "Metastatic soft tissue sarcoma".

### Settings proposed
- `non_metastatic`: 'Extremity soft tissue sarcoma, no distant disease recorded (as recorded)'. Basis: page 20 "Non- metastatic soft tissue sarcoma".
- `metastatic`: 'Extremity soft tissue sarcoma, distant disease recorded (as recorded)'. Basis: page 20 "Metastatic soft tissue sarcoma"; page 22 "EXTREMITY SOFT TISSUE SARCOMA – METASTATIC AT PRESENTATION".
- `paediatric_rhabdomyosarcoma`: 'Rhabdomyosarcoma, child (as recorded)'. Basis: paediatric page 59 "Suspected Rhabdomyosarcoma".

### Work-up records
Setting columns: NM non_metastatic, M metastatic, RMS paediatric_rhabdomyosarcoma.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_exam_sts | Detailed history and examination (size, depth, growth) | NM a, M a, RMS a | clinical_note, referral | owner | ecog, presenting_complaint | 20 | "Detailed clinical history and examination" | Proposed a, first box of the flow. Page 25 "Any soft tissue lump greater than 5cmsand located deep to" the deep fascia counts as sarcoma until proved otherwise |
| basic_imaging_sts | Radiograph, chest X-ray, local MRI | NM a, M a, RMS none | xray, mri | Radiology | lesion_size | 20 | "Basic imaging (local & chest x-ray, local MRI) & routine blood investigations (a)" | NCG a |
| routine_blood_sts | Routine blood investigations | NM a, M a, RMS a | lab | Biochemistry | haemoglobin, wbc, platelets, creatinine, bilirubin | 20 | "Basic imaging (local & chest x-ray, local MRI) & routine blood investigations (a)" | NCG a (same line). RMS: proposed a, the paediatric book has no blood list |
| mri_contrast_sts | MRI with contrast of the primary site (before biopsy) | NM a, M a, RMS a | mri | Radiology | lesion_size, nodal_findings | 26 | "contrast is recommended in all cases  (a)" | NCG a, page 26 "STS Staging - Local imaging to be performed prior to doing a biopsy  (a)". RMS page 59 "Essential: CT scan of chest/ abdomen/pelvis, MRI scan for extremity and head/neck primary/genitourinary RMS (must" |
| biopsy_sts | Core needle biopsy | NM a, M a, RMS a | histopathology | Pathology | histologic_type, grade | 20 | "Biopsy (core needle biopsy preferred) (a)" | NCG a. RMS page 59 "Bone scan,Biopsy of mass, B/L bone marrow biopsy  (a)" |
| histopathology_report_sts | Pathology report: subtype, FNCLCC grade, depth, size, margins | NM a, M a, RMS a | histopathology | Pathology | histologic_type, grade, lesion_size, margins, lvi, NEW:tumour_depth | 42 | "System used:  French Federation of Cancer Centres Sarcoma Group (FNCLCC)" | Proposed a (the grade and margins drive the radiotherapy and chemotherapy lines on pages 21 and 31). Depth wording page 42 "Superficial: Defined as above fascia." |
| molecular_sts | Immunohistochemistry, cytogenetic and molecular studies (fusion tests) | NM c, M c, RMS b | ihc, molecular | Pathology | NEW:sarcoma_fusion | 26 | "immunohistochemistry, cytogenetic, and molecular studies are desirable in some" | NCG c for sarcomas (Ewing and STS); RMS page 59 "Optimal: Molecular studies on tissue specimen (PAX-3 FKHR, PAX-7 FKHR fusion status) Whole body PET CT scan (b)" |
| ct_chest_sts | Non-contrast CT chest (metastatic work-up) | NM a, M a, RMS a | ct | Radiology | distant_findings | 26 | "NCCT chest for metastatic workup  is" | NCG a. RMS page 59 CT of chest, abdomen, pelvis (a) |
| usg_nodes_sts | Ultrasound of abdomen, pelvis, groin, neck, axilla (regional nodes) | NM a, M a, RMS none | ultrasound | Radiology | nodal_findings | 20 | "NCCT scan chest & USG abdomen pelvis/groin/neck / axilla) (a)" | NCG a on page 20; page 26 "Ultrasonography of regional lymph node basin may be done, particularly" for certain histologies (c) |
| histology_specific_imaging_sts | Extra imaging by histology (MRI spine, CT abdomen and pelvis, MRI brain) | NM c, M c, RMS none | mri, ct | Radiology | distant_findings | 26 | "Additional imaging to be considered based on histology are as follows (a)" | NCG a under a histology condition the system does not judge, so tier c with condition a. Page 27 "iii) MRI brain: Alveolar soft part sarcoma and angiosarcoma" |
| pet_ct_sts | FDG PET-CT with breath-hold CT chest | NM c, M c, RMS b | pet_ct | Nuclear Medicine | suv_max, distant_findings | 27 | "The F18 FDG PET CT scan with a breath hold CT of the chest may be used for" | c (the text continues: not cost effective and not recommended as standard of care, (c)). RMS page 59 whole body PET CT (b) |
| bone_scan_marrow_rms | Bone scan and bilateral bone marrow biopsy (rhabdomyosarcoma) | NM none, M none, RMS a | bone_scan, NEW:bone_marrow | Nuclear Medicine | NEW:bone_marrow_result, distant_findings | 59 | "Bone scan,Biopsy of mass, B/L bone marrow biopsy  (a)" | NCG a for RMS only (page 59; Annexure 1 page 64) |
| prior_excision_sts | Report of a prior excision with margins | NM c, M c, RMS none | operative_note, histopathology | Surgical Oncology | margins | 20 | "Tumors referred after prior excision with inadequate or unknown margins need to" | No letter; shown only because the book asks for re-excision of such tumours; proposed c |

### New facts needed
| id | label | kind | report type | book's wording |
|---|---|---|---|---|
| NEW:tumour_depth | Tumour depth relative to the fascia | categorical: superficial, deep, not stated | histopathology, mri | page 42 "Superficial: Defined as above fascia." |
| NEW:sarcoma_fusion | Fusion test result (shared with bone) | text | molecular | page 39 "Molecular by RT-PCR: EWS-FLI1, EWS-ERG, etc SYT-SSX, SYT-SSX1, SYT-SSX2, EWS-WT1," |
| NEW:bone_marrow_result | shared | | | see leukaemia |
FNCLCC grade can use the existing `grade` fact (values 1 to 3 as written).

### Staging system
Adult: TNM with superficial or deep, T1 up to 5 cm and T2 over 5 cm, stages IA to IV with grade (page 41 "T1 :       ≤ 5cm,  a: superficial b: deep" and the table page 43 "Stage IV         Any T N1 M0          Any grade"); histologic grade is FNCLCC (page 42), grades 2 and 3 count as high grade. Paediatric RMS: a TNM-and-site stage (page 61 "Staging based on the TNM and site of disease:"), surgico-pathologic groups I to IV (page 61 "Grouping based on the surgico-pathological resection") and risk groups low, intermediate, high. No Enneking and no AJCC edition number is printed. Vaidyx never computes any of these.

### Indian notes
- Page 21 "Chemotherapy may be offered to patients with high grade lesions > 5cm or recurrent" after multidisciplinary clinic discussion (resource-aware wording); page 22 and 23 "Decision for palliative intent of treatment should be taken after discussion in multi-" disciplinary tumor board.
- Page 21 "All upfront resectable cases should be evaluated for feasibility of intra-operative" interstitial brachytherapy. No PM-JAY text.

### Regimen or dose tables
Adult: chemotherapy page 23 and appendix 5 pages 47 to 49 (soft tissue part); radiotherapy page 23 and appendix 6 pages 50 to 52. Paediatric RMS: chemotherapy options page 60 (regimens VA, VAC, VIE, IVA, IVADo, VDC-IE, VIrn); radiotherapy dose table pages 60 to 61.

### Open questions
- Only extremity soft tissue sarcoma has a flow. Retroperitoneal, trunk, head and neck and uterine sarcomas have no NCG flow.
- The adult staging TNM table starts on page 40 inside the bone pathology section and repeats on pages 41 and 43; the T cut-off differs (8 cm on page 40, 5 cm on page 41).
- The book never says which AJCC edition is meant.

## Brain and CNS tumours (`brain_cns`)
### Source
NCG has no CNS guideline file in `/data/vaidyx/tb_resources/guidelines/ncg_india/` (the folder holds the 2019 adult haematolymphoid, paediatric, bone and soft tissue, head and neck, thoracic and urological books, the GI and gynaecology files and the manual). What exists:
- `ncg-guidelines-manual-2021.pdf` (NCG Guidelines Manual 2021, release date November 2021): the only CNS mentions are examples from the NICE brain tumour guideline NG99, not NCG advice. Page 30 (printed 21), box 3.5, an example of a review question: "x What are the most useful molecular markers to determine prognosis/guide treatment for" gliomas; and page 59 (printed 50), box 6.1: "Brain tumours (primary) and brain metastases in adults NG99 (July 2018) (accessed 4". No table of contents entry covers brain or CNS tumours.
- `ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf`: no medulloblastoma, glioma or other primary CNS tumour (search for medulloblastoma, glioma, ependymoma, craniopharyngioma, intracranial returned nothing). CNS appears only as a screening or spread item: retinoblastoma page 52 "MR Orbit + Screening Brain", page 56 "Stage 4 Central nervous system disease.", CNS involvement in leukaemia and lymphoma (pages 7, 13, 23).
- `ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf` page 27: "iii) MRI brain: Alveolar soft part sarcoma and angiosarcoma" (brain imaging for sarcoma, not a CNS tumour).
Conclusion: a brain and CNS checklist cannot carry an NCG quote. It must be a draft checklist labelled 'needs a clinician's check' with an open-access non-NCG book (see below).

### Settings proposed
- `adult_diffuse_glioma`: 'Adult diffuse glioma (as recorded)'. Basis: the recommended EANO guideline title below (adult diffuse gliomas). The system never grades.
- `other_cns_tumour`: 'Other brain or CNS tumour, adult or child (as recorded)'. Basis: none in NCG; kept as a thin setting that asks only for the generic records (history, MRI, histopathology, neurosurgical opinion) until a book for medulloblastoma, meningioma and others is chosen. Medulloblastoma has an Indian source (ISNO 2017, see candidates).

### Work-up records
No record can be verified. Skeleton to be filled from the cached text of the chosen book (page and verbatim quote needed). Tiers are proposed and carry no NCG basis; the guideline's own evidence classes (EANO uses class of evidence and level of recommendation) replace a, b, c, so a mapping rule is needed.

| record id | label | tier per setting | doc_types | department | required facts | page | verbatim quote | tier basis |
|---|---|---|---|---|---|---|---|---|
| history_neuro_exam_brain | History, seizures, neurological examination, steroid use, performance status | adult_diffuse_glioma a, other_cns_tumour a | clinical_note, referral | Neurosurgery | ecog, comorbidities, NEW:kps | n/a | to be quoted from the chosen book | proposed a |
| mri_brain_contrast | MRI brain with contrast (before surgery) | adult_diffuse_glioma a, other_cns_tumour a | mri | Radiology | lesion_size, distant_findings | n/a | to be quoted | proposed a |
| post_op_mri_brain | MRI brain after surgery | adult_diffuse_glioma b, other_cns_tumour none | mri | Radiology | comparison_prior | n/a | to be quoted | proposed b, post-surgery record |
| neurosurgery_opinion | Neurosurgical opinion on resectability or biopsy | adult_diffuse_glioma a, other_cns_tumour a | clinical_note, operative_note | Neurosurgery | clinical_question | n/a | to be quoted | proposed a |
| glioma_histopathology | Histopathology with integrated molecular diagnosis | adult_diffuse_glioma a, other_cns_tumour a | histopathology, ihc, molecular | Pathology | histologic_type, grade, ki67, NEW:idh_status, NEW:codeletion_1p19q, NEW:mgmt_promoter | n/a | to be quoted | proposed a |
| ct_chest_abd_brain_met | Staging imaging for suspected brain metastasis (primary elsewhere) | not in scope | | | | n/a | | metastases to the brain belong to the primary cancer's protocol |

### New facts needed
Proposed, not yet backed by a quote: NEW:kps (Karnofsky performance status, number 0 to 100, from clinical_note), NEW:idh_status (categorical: mutant, wild type, not tested), NEW:codeletion_1p19q (categorical: present, absent, not tested), NEW:mgmt_promoter (categorical: methylated, unmethylated, not tested). The guideline's wording must be quoted once its text is cached. No new document type is needed.

### Staging system
Brain and CNS tumours have no stage; the book would name a WHO grade or integrated diagnosis. Not read from an NCG source. Vaidyx never grades.

### Indian notes
The Indian ISNO consensus (2019) is written for cost and turnaround time in India ('predominantly using immunohistochemistry, with minimum possible additional molecular testing', from its abstract, not an NCG file). No NCG or PM-JAY text exists for CNS in the local files.

### Regimen or dose tables
None in NCG for CNS.

### Open questions
- Which book the owner approves (see below), and that its PDF text is cached and page-numbered before any record is written.
- Whether paediatric CNS (medulloblastoma) is wanted in this protocol; the ISNO 2017 medulloblastoma consensus exists but its licence is unconfirmed.
- The label 'needs a clinician's check' applies to the whole checklist (owner decision 27 Oct 2026).

### Open-access sources
Searched on 27 Oct 2026 with web search only; nothing downloaded. Licences below were read from search result pages and Europe PMC records, not from the PDFs, so the licence line must be re-read on the publisher page before a PDF is stored on the server. NCCN is not considered.

| Organisation | Title | Year | Official URL | Licence or terms | Page numbers | Notes |
|---|---|---|---|---|---|---|
| EANO (European Association of Neuro-Oncology), published in Nature Reviews Clinical Oncology 18:170-186 | EANO guidelines on the diagnosis and treatment of diffuse gliomas of adulthood | online 8 Dec 2020, issue 2021 | https://pmc.ncbi.nlm.nih.gov/articles/PMC7904519/ (PMC copy; PDF linked from that page; DOI https://doi.org/10.1038/s41571-020-00447-z; EANO page https://www.eano.eu/publications/eano-guidelines/eano-guidelines-on-the-diagnosis-and-treatment-of-diffuse-gliomas-of-adulthood/) | Open access, CC BY 4.0, copyright held by the authors (read on the PMC page). Free to download and keep, with attribution | Yes: journal pages 170 to 186 (17 pages); recommendations carry class of evidence and level (for example 'C: IV; L: B') | Covers MRI, tissue acquisition, integrated histomolecular diagnosis (IDH, 1p/19q, ATRX, MGMT, CDKN2A/B), treatment and follow-up; based on WHO 2016 plus cIMPACT-NOW, so partly dated against WHO 2021. European, not Indian |
| ISNO (Indian Society of Neuro-Oncology), Neurology India 67(1):173-182 | ISNO consensus guidelines for practical adaptation of the WHO 2016 classification of adult diffuse gliomas | 2019 | https://doi.org/10.4103/0028-3886.253572 | Not confirmed. Europe PMC marks it not open access (no PMCID); the DOI resolves to a publisher page. Terms unknown | Yes (10 journal pages) | India first and cost-aware (IHC with minimal extra molecular tests, mandatory and optional tests per scenario), but diagnosis and pathology only, no full work-up or treatment. Companion paper: 'The Indian Society of Neuro-oncology guidelines: A personalized approach to treating adult diffuse gliomas', Neurol India 2019, doi 10.4103/0028-3886.253602, also not marked open access |
| ISNO, Neurology India | Indian Society of Neuro-Oncology consensus guidelines for the contemporary management of medulloblastoma | 2017 | https://doi.org/10.4103/0028-3886.201841 | Not confirmed; Europe PMC marks it not open access | Yes | Indian, paediatric and adult medulloblastoma; relevant if `other_cns_tumour` is extended |
| ESMO (Annals of Oncology 25 suppl 3:iii93-iii101) | High-grade malignant glioma: ESMO Clinical Practice Guidelines for diagnosis, treatment and follow-up (Stupp et al.) | 2014 | https://www.esmo.org/guidelines/guidelines-by-topic/esmo-clinical-practice-guidelines-neuro-oncology/high-grade-malignant-glioma | Not confirmed; the ESMO page shows only a site-wide rights notice; the 2010 edition was found behind campus access | Yes (9 journal pages) | Short and old, pre-molecular classification; not recommended |
| ICMR | none found | | | | | No ICMR consensus document on brain tumours or glioma was found by search |
| NICE (UK) | Brain tumours (primary) and brain metastases in over 16s, NG99 | 2018 | https://www.nice.org.uk/guidance/ng99 | NICE content terms (not reviewed here); free to read; reuse terms must be checked | Yes | The same guideline the NCG manual uses as an example (manual pages 30 and 59). UK, not requested; kept as a fallback |
| Pakistan Brain Tumour Consortium (JPMA) | Consensus guidelines for the management of adult low-grade gliomas for low and middle-income countries | not read | https://jpma.org.pk | Not reviewed | not reviewed | A resource-limited setting, low-grade glioma only; not enough alone |

Recommendation: use the EANO 2021 guideline (CC BY 4.0, PMC copy, page-numbered, evidence-graded, covers work-up through follow-up) as the book for the draft adult glioma checklist, with ISNO 2019 added as the India-first source for the pathology records once its terms are confirmed. Reason: it is the only candidate whose open licence was confirmed in this search and it covers the whole work-up; the ISNO papers are Indian and cost-aware but narrower and their reuse terms are not confirmed. A clinician must still check the checklist, and the labelling must say the book is European and not NCG.
