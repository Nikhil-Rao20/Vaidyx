/* Vaidyx-TB workflow atlas: the doctors' inputs (Dr Minmini, Radiology; Dr Usha, Biochemistry; TANUH) and what the code does with
   them, checked 16 Oct 2026 against branch the-ui, /data/vaidyx/tb_resources/guidelines, the chats and every branch. No em dashes. */
window.ATLAS.doctors = {
  who: "Dr Minmini (Radiology) and Dr Usha (Biochemistry), both professors, TANUH. They shared the department lists, five guideline reading lists, the AJCC book and comments on the Pre-Authorization validation sheet (15 Oct).",

  /* one row per point the user brought (16 Oct) */
  points: [
    { id: "P1", title: "AJCC Cancer Staging Manual, 8th edition", status: "partial",
      have: "Full book on the server since 11 Oct (58 MB, licensed copy, internal use only, kept out of the public demo). 8 chapters are in the guideline search: general rules, head and neck overview, neck nodes and unknown primary (head and neck), lip and oral cavity, colon and rectum, lung, breast, cervix.",
      missing: "The other chapters are not indexed (needed when new cancers are added). Used only as reference text in the guideline search; it is in none of the specialty agents' packs. Scope rule: never used to work out a stage. An AJCC licence is needed for any use beyond internal reference; AJCC version 9 protocols are still wanted.",
      where: "/data/vaidyx/tb_resources/guidelines/_licensed_full_books/, ajcc/ ; tumour_board/guidelines.py SOURCES" },
    { id: "P2", title: "Five guideline reading lists (imaging, histopathology and TNM, radiotherapy, tumour management, chemotherapy)", status: "partial",
      have: "All five .docx files on the server since 11 Oct: 80 entries in total (many repeat across lists). Documents for the 5 current cancers were downloaded where free and allowed; the guideline search holds 8,978 passages from 26 sources.",
      missing: "The documents added from these lists on 11 Oct (ASCO, ASTRO, ESTRO, AJCC, MoHFW STG, DHR / DGHS) reach only the general guideline search: they were never added to the specialty agents' packs or to the dose and radiotherapy reference table (both last changed before they arrived). Paid, licensed or login-only items were not obtained. Entries for cancers we do not have (prostate, liver, lymphoma, brain, myeloma, sarcoma, paediatric) were skipped. Nothing in the interface shows the doctors what the library holds. Entry by entry below.",
      where: "/data/vaidyx/tb_resources/guidelines/_reading_lists/ ; protocols/specialty_packs.json ; protocols/dose_references.json" },
    { id: "P3", title: "Treating departments (24 in the doctors' list)", status: "partial",
      have: "The code has 22 treating departments: the first 20 of the list exactly, plus Palliative Medicine (doctors' no. 24) and Medical Gastroenterology (added by the V2 build for endoscopy requests; not in the doctors' list). Hematology (no. 21) is already the same department as Haematology (no. 15): 'Hematology' is an alias.",
      missing: "Pediatric Surgery (no. 22) and Medical Genetics ('Medical Geneticist', no. 23) are not in the code. The 4 additions came on 15 Oct on WhatsApp, after V2 was built from Eswar's 13 Oct list of 20. To confirm with the doctors: keep Medical Gastroenterology; is Medical Genetics treating (owns Case Files) or supporting (answers requests, counselling, germline tests)?",
      where: "tumour_board/org.py department defaults ; data/tumour_board/org.json" },
    { id: "P4", title: "Supporting departments (6 in the doctors' list)", status: "done",
      have: "All 6 are in the code with the same names: Radiology, Pathology, Microbiology, Biochemistry, Nuclear Medicine, Clinical Pharmacology.",
      missing: "The code has 2 more, added by the V2 build: Dental Surgery / Oral and Maxillofacial Surgery (pre-radiotherapy dental evaluation, oral cavity protocol) and Anaesthesiology (pre-anaesthetic check). To confirm with the doctors: keep or remove.",
      where: "tumour_board/org.py ; changes_v2.md §4" },
    { id: "P5", title: "WhatsApp discussion of 15 to 16 Oct", status: "missing",
      have: "Nothing from this chat is in the code, the docs or any earlier chat. It answers the validation sheet Bharath sent on 15 Oct (docs/tumour-board/PreAuth_Checks_for_Validation.pdf).",
      missing: "Every ask below is new work.",
      where: "" }
  ],

  /* the asks inside the WhatsApp chat */
  asks: [
    { id: "W1", who: "Dr Usha", ask: "Have a justification for whatever you are listing.", today: "Partly. Every Pre-Authorization record already cites its NCG guideline line and page. The cancer list, the departments and the 'added' items have no stated reason in the interface.", gap: "A visible reason (with source) next to every listed cancer, department and check." },
    { id: "W2", who: "Dr Usha", ask: "List the top 10 cancers, followed by manual entry (any number).", today: "Not built. The Case File form offers only 5 fixed protocols (breast, cervix, lung NSCLC, rectal, oral cavity). There is no 'other cancer' entry; a Case File for any other cancer cannot be created from the hospital system. Only an accepted referral may leave the protocol 'for later' (no check runs).", gap: "A top-10 list justified by Indian data, plus a manual entry. A manually entered cancer has no protocol, so it needs a generic minimum record set or a clear 'no automatic check' state." },
    { id: "W3", who: "Dr Usha", ask: "Or list male cancers, female cancers, paediatric cancers and general cancers.", today: "Not built. Protocols have no sex or age grouping.", gap: "A grouped picker (by sex and age, or by organ system), each item with its source." },
    { id: "W4", who: "Dr Minmini", ask: "Cancer of Unknown Primary must be there. Many board cases are such cases; the board helps them investigate further.", today: "Not built anywhere. The only related text is AJCC chapter 6 (head and neck unknown primary) in the guideline search. Every protocol assumes a known organ site.", gap: "A Cancer of Unknown Primary protocol: the work-up records the board needs to see (not a diagnostic algorithm), and a path to refer or re-list once a primary is found (the referral feature exists)." },
    { id: "W5", who: "Dr Usha, Dr Minmini", ask: "Treating and supporting department lists (above).", today: "See P3 and P4.", gap: "Add Pediatric Surgery and Medical Genetics; confirm the 3 extra departments the build added." },
    { id: "W6", who: "Dr Minmini", ask: "Shared: Tempus oncology foundation model page, and arXiv 2608.24688.", today: "Both are the same Tempus project: a model that turns each US patient's record history into an embedding used to predict survival, progression and treatment benefit. No weights released; licensed to pharma; it reads H&E slides; no tumour board or radiology content.", gap: "Not usable as is: prediction and treatment ranking are outside our signed scope, and it cannot run in-house. Ideas worth borrowing for the interface: a dated patient timeline with anchor events, and a 'which record types exist' grid for each Case File. Worth asking her what she meant by sharing it." },
    { id: "W7", who: "Bharath, the doctors", ask: "In-person meeting on Monday 19 Oct 2026, first half, room 710 (Dr Usha and Dr Minmini).", today: "Booked by Bharath.", gap: "Take this page's open questions and the validation sheet to that meeting." }
  ],

  /* the five reading lists, entry by entry. status: held, partial, paid, licence, terms, browser, notneeded, nottaken
     uses: search (general guideline search: Summary references, Ask), packs (which specialty agents read it), dose (after-board dose check),
     check (agents' reporting checklists), proto (Pre-Authorization record sources) */
  statusLabel: { held: "In the library", partial: "Partly", paid: "Not obtained: paid", licence: "Not obtained: licence bars AI use", terms: "Not obtained: website terms / login, use by hand",
                 browser: "Not obtained: download blocked for scripts", notneeded: "Skipped: cancer not in our protocols", nottaken: "Not taken" },
  lists: [
    { file: "imaging-reporting-guidelines-list.docx", title: "Imaging reporting", rows: [
      ["BI-RADS", "partial", "Summary forms (mammography, MRI, ultrasound), v2025 what's new; the full atlas is paid", "search, packs: radiology"],
      ["Lung-RADS", "held", "Lung-RADS v2022 and summary", "search, packs: radiology"],
      ["Fleischner Society guidelines", "browser", "Wanted (journal blocks scripts)", ""],
      ["LI-RADS", "notneeded", "Liver", ""], ["PI-RADS v2.1", "notneeded", "Prostate", ""], ["O-RADS US and MRI", "notneeded", "Ovary", ""],
      ["VI-RADS", "notneeded", "Bladder", ""],
      ["NI-RADS", "held", "Atlas, 2025 categories, management tables, report templates; the white paper is wanted", "search, packs: radiology"],
      ["RECIST 1.1", "held", "RECIST 1.1 (2009) and the 2016 clarification; iRECIST too", "search, packs: radiology"],
      ["PERCIST", "held", "Wahl 2009", "search, packs: radiology"],
      ["Lugano classification", "notneeded", "Lymphoma", ""], ["Deauville five-point scale", "notneeded", "Lymphoma", ""], ["MY-RADS", "notneeded", "Myeloma", ""],
      ["WHO CNS 5th edition", "notneeded", "Brain (also paid)", ""], ["RANO 2.0", "notneeded", "Brain", ""], ["iRANO", "notneeded", "Brain", ""], ["BT-RADS", "notneeded", "Brain", ""],
      ["UICC TNM classification", "paid", "9th edition wanted", ""],
      ["AJCC Cancer Staging System", "partial", "8th edition book; 8 chapters indexed", "search"],
      ["ACR Appropriateness Criteria", "held", "13 topics for breast, lung, cervix, colon, rectum, head and neck", "search, packs: radiology, nuclear medicine"] ] },
    { file: "histopathology-tnm-classification-guidelines-list.docx", title: "Histopathology, TNM and classification", rows: [
      ["WHO Blue Books (catalogue)", "paid", "5th edition volumes wanted (thoracic, breast, digestive, head and neck, female genital)", ""],
      ["WHO Classification of Tumours Online", "paid", "Subscription", ""],
      ["WHO CNS 5th edition", "notneeded", "Brain (also paid)", ""],
      ["UICC TNM 9th edition", "paid", "Wanted", ""],
      ["AJCC official resources", "partial", "8th edition book; version 9 protocols wanted", "search"],
      ["CAP cancer protocols", "held", "Breast (resection, biopsy, DCIS), cervix, colorectal, oral cavity, lung", "search, packs: pathology, check: pathology"],
      ["CAP biomarker protocols", "held", "Breast, colorectal, MMR, head and neck, lung", "search, packs: pathology"],
      ["ICCR datasets", "held", "Cervix, colorectal, oral cavity, neck dissection", "search, packs: pathology"],
      ["ICD-O", "held", "ICD-O-3.2 tables (reference table, not in the search)", "FHIR and registry export codes"],
      ["UICC TNM Supplement 5th edition", "paid", "Wanted", ""], ["UICC TNM Atlas", "paid", "Wanted", ""],
      ["CAP protocols and guidelines", "held", "Same as the CAP rows above", "search, packs: pathology"],
      ["ASCO / CAP ER, PR and HER2 testing", "held", "ER / PgR summary and updates, HER2 2023 algorithms; also PD-L1 and lung / colorectal molecular", "search, packs: pathology"] ] },
    { file: "radiotherapy-guidelines-list.docx", title: "Radiotherapy", rows: [
      ["ASTRO clinical practice guidelines", "partial", "Only cervix 2020 (executive summary)", "search only"],
      ["ESTRO guidelines", "partial", "ESGO / ESTRO / ESP cervix 2023, IBS-GEC contouring 2021, GEC-ESTRO IV", "search only"],
      ["ASTRO consensus and safety white papers", "nottaken", "Not downloaded", ""],
      ["NCCN", "licence", "Deliberately excluded", ""],
      ["ESMO clinical practice guidelines", "partial", "9 ESMO / Pan-Asian ESMO (breast, NSCLC, colon, rectum, metastatic colorectal)", "search, packs: oncology agents, dose"],
      ["eviQ radiation oncology", "terms", "Use by hand", ""], ["IAEA ROVER", "terms", "Login", ""],
      ["RTOG / NRG protocols", "nottaken", "Trial protocols", ""],
      ["GEC-ESTRO brachytherapy", "partial", "Recommendations IV held; I and II wanted", "search only"],
      ["ASTRO palliative radiotherapy", "browser", "Palliative thoracic 2018 wanted", ""],
      ["ASTRO brain metastases", "notneeded", "Brain", ""],
      ["ASTRO breast radiotherapy", "browser", "Whole-breast 2018, partial-breast 2024, post-mastectomy 2025 wanted", ""],
      ["ASTRO lung radiotherapy", "browser", "Early lung SBRT 2017 wanted", ""],
      ["ASTRO gastrointestinal radiotherapy", "browser", "Rectal 2020 and 2025 update wanted", ""],
      ["ASTRO genitourinary radiotherapy", "notneeded", "Prostate, bladder", ""],
      ["ASTRO gynaecological radiotherapy", "held", "Cervix 2020", "search only"],
      ["ASTRO head and neck radiotherapy", "nottaken", "Not downloaded", ""],
      ["ASTRO soft tissue sarcoma", "notneeded", "Sarcoma", ""] ] },
    { file: "tumour-management-guidelines-list.docx", title: "Tumour management", rows: [
      ["ASCO clinical practice guidelines", "partial", "6 resource-stratified (breast, colorectal, cervix) + neck management 2019; rectal 2024 and stage III NSCLC wanted", "search only"],
      ["ASCO living guidelines", "terms", "Online only, use by hand", ""],
      ["ESMO clinical practice guidelines", "partial", "9 documents (see radiotherapy list)", "search, packs: oncology agents, dose"],
      ["ESMO living guidelines", "terms", "Online only", ""],
      ["NCCN", "licence", "Deliberately excluded", ""],
      ["ASTRO", "partial", "Cervix 2020 only", "search only"],
      ["National Cancer Grid treatment guidelines", "held", "Breast, thoracic, head and neck, gynaecological (2019), colorectal, rectal; radiology synoptic template; VTB case template", "search, packs: all agents, dose, check, proto"],
      ["NCG Guidelines Manual", "held", "2021", "search, packs, proto"],
      ["Government of India STGs: oncology", "held", "MoHFW STG 2017 chapters: breast, cervix (2), lung, oral cavity, rectum", "search only"],
      ["Government of India DGHS technical guidelines", "partial", "DHR / DGHS lung treatment and palliation 2025 indexed; NHM framework 2016 and NPCDCS manual kept, not indexed", "search only"],
      ["NCI PDQ treatment summaries", "held", "Breast, cervix, colon, rectal, lip and oral cavity, NSCLC (labelled US)", "search, dose"],
      ["NCI treatment types", "nottaken", "Patient information page", ""],
      ["NICE cancer guidelines", "held", "NG101 breast, NG122 lung, NG151 colorectal, NG36 head and neck", "search, packs: oncology agents, dose"],
      ["MASCC supportive care", "nottaken", "Not downloaded", ""],
      ["SIOPE paediatric standards", "notneeded", "Paediatric (needed if paediatric cancers are added)", ""] ] },
    { file: "chemotherapy-and-systemic-therapy-guidelines-list.docx", title: "Chemotherapy and systemic therapy", rows: [
      ["ASCO clinical practice guidelines", "partial", "As above", "search only"],
      ["ASCO living guidelines", "terms", "Online only", ""],
      ["ESMO clinical practice guidelines", "partial", "As above", "search, packs: oncology agents, dose"],
      ["ESMO living guidelines", "terms", "Online only", ""],
      ["NCCN", "licence", "Deliberately excluded", ""],
      ["eviQ medical oncology protocols", "terms", "Use by hand", ""],
      ["eviQ safe administration", "terms", "Use by hand", ""],
      ["National Cancer Grid", "held", "As above", "search, packs, dose, proto"],
      ["NCI PDQ treatment summaries", "held", "As above", "search, dose"],
      ["NCI chemotherapy to treat cancer", "nottaken", "Patient information page", ""],
      ["NICE guidelines", "held", "As above", "search, packs: oncology agents, dose"],
      ["ASCO / ONS administration safety standards", "nottaken", "Nursing administration standards", ""],
      ["MASCC supportive care", "nottaken", "Not downloaded", ""],
      ["ASCO biomarkers and molecular testing", "held", "ASCO / CAP folder: ER / PgR, HER2, PD-L1, lung and colorectal molecular", "search, packs: pathology"] ] }
  ],

  /* how the library is wired, per source folder (code, 16 Oct) */
  wiring: [
    ["NCG (India)", "1.35", "All six agents (Radiology: synoptic template only)", "107 dose lines", "Every Pre-Authorization record cites it"],
    ["ICMR (India)", "1.3", "Pathology, the three oncology agents", "27", ""],
    ["Tata Memorial Centre (India)", "1.3", "Pathology, the three oncology agents", "16", ""],
    ["PM-JAY / NHA (India)", "1.3", "The three oncology agents", "", "Board composition flag"],
    ["ICRI / IRIA (India)", "1.25", "Radiology, Nuclear Medicine", "", "Radiology reporting checklists"],
    ["MoHFW STG 2017 (India)", "1.0", "None", "None", "Added 11 Oct: search only"],
    ["DHR / DGHS 2025 (India)", "1.0", "None", "None", "Added 11 Oct: search only"],
    ["ESMO", "1.0", "The three oncology agents", "8", ""],
    ["NICE", "0.95", "The three oncology agents", "3", ""],
    ["CAP, ASCO / CAP, RCPath, ICCR", "1.0", "Pathology", "", "Pathology checklists (CAP)"],
    ["ACR RADS, ACR Appropriateness, RCR, RECIST", "0.9 to 0.95", "Radiology (ACR Appropriateness also Nuclear Medicine)", "", ""],
    ["NCI PDQ (US)", "0.85", "None", "140 (largest share, labelled US)", ""],
    ["ASCO", "1.0", "None", "None", "Added 11 Oct: search only"],
    ["ASTRO, ESTRO / GEC-ESTRO", "0.95", "None (not even Radiation Oncology)", "None", "Added 11 Oct: search only"],
    ["AJCC 8th edition", "0.9", "None", "None", "Added 11 Oct: search only; never used to compute stage"]
  ],

  /* research for the doctors' asks (16 Oct). [unverified] = not checked against a primary source */
  research: {
    top10: {
      note: "NCRP 2020 = ICMR-NCDIR projections for 2020 (28 population registries); oral cavity = tongue + mouth and colorectum = colon + rectum summed. GLOBOCAN 2024 = IARC India fact sheet v1.0 (Sept 2026).",
      overall: [["Breast", "15.1%", "15.2%"], ["Oral cavity", "9.6%", "13.2%"], ["Lung", "7.1%", "7.2%"], ["Cervix", "5.4%", "5.1%"], ["Colorectum", "5.3%", "5.3%"],
                ["Oesophagus", "3.8%", "3.7%"], ["Stomach", "3.6%", "4.4%"], ["Leukaemia", "3.4%", "3.2%"], ["Ovary", "3.2%", "2.9%"], ["NHL / prostate (NCRP), liver (GLOBOCAN)", "3.0%", "2.7%"]],
      men: "Oral cavity 14.3% (mouth + tongue), lung 10.6, prostate 6.1, stomach 4.8, oesophagus 4.8, larynx 4.0, liver 3.9, NHL 3.7, rectum 3.2, colon 3.0, bladder 3.0 (NCRP 2020).",
      women: "Breast 28.8%, cervix 10.6, ovary 6.2, corpus uteri 3.7, lung 3.7, thyroid 3.7, oral cavity 5.1 (combined), oesophagus 2.8, gallbladder 2.7, stomach 2.4 (NCRP 2020).",
      children: "Ages 0 to 14 (Kapoor 2024, 96 hospital registries, ICCC-3 groups): leukaemia 39.9%, lymphoma 11.7, CNS 10.7, bone 7.6, soft-tissue sarcoma 6.9, Wilms 4.3, neuroblastoma 3.9, retinoblastoma 3.6, carcinomas 3.1, germ cell 2.3, hepatic 1.5.",
      adolescents: "Ages 15 to 19: leukaemia 27.3%, bone 17.9 (osteosarcoma 11.7), lymphoma 13.8, carcinomas 12.4, soft-tissue sarcoma 8.4, CNS 6.9, germ cell 4.3."
    },
    design: [
      "Group the cancer picker by organ system, the way Tata Memorial's 11 Disease Management Groups do (Annual Report 2018-19): Adult Haematolymphoid, Bone and Soft Tissue, Breast, Gastrointestinal (stomach, gallbladder, pancreas, liver, colorectal), Gynaecology, Head and Neck, Neuro-Oncology, Paediatric Haematolymphoid, Paediatric Solid Tumours (under 15), Thoracic (lung and oesophagus), Uro-Oncology. HBCR 2021 report chapters follow the same organ split with ICD-10 codes.",
      "Real systems attach a case to a board organised by disease group and record a coded diagnosis separately (NAVIFY uses ICD-O-3; OncoLens uses cancer-specific templates). In India 28.5% of hospitals with a board run several site boards (head and neck, gynaecology, breast, uro-oncology most often). Our sessions have no site or board type today.",
      "Tata Memorial's own trial filter has 'Not Otherwise Specified' and 'DMG Not Applicable': a precedent for an 'other' entry.",
      "Inside each group, sort by Indian frequency and badge the India-wide top 10, citing NCRP 2020 and GLOBOCAN 2024: this answers 'top 10' and 'justification' together.",
      "Add a filter for men / women / children 0 to 14 / adolescents 15 to 19: this answers 'male, female, paediatric, general' without a second list. Paediatric uses ICCC-3 groups.",
      "Keep 'Cancer of Unknown Primary' as its own top-level entry, not under Other (WHO ICD-10 C80.0 'primary site unknown, so stated'; ICD-O-3 topography C80.9).",
      "Add 'Other cancer (manual entry)': free text plus an ICD-10 / ICD-O-3 lookup, a generic minimum record set (histopathology, imaging, staging work-up, question for the board), clearly labelled 'No disease-specific Indian protocol'.",
      "Rename 'Rectal' to 'Colorectal' (or add Colon): the sources rank colorectum, and NCG has one colorectal guideline."
    ],
    cup: {
      freq: "2 to 5% of cancers internationally; 3 to 5% in an Indian review (IJMPO 2018). No national Indian figure. A UK CUP service: of 1,225 referrals, 25% stayed confirmed CUP and 36% had a primary found, which supports 'the board helps investigate'.",
      stages: [["Malignancy of unknown origin (MUO)", "Metastatic malignancy found on a limited number of tests, without an obvious primary, before full investigation."],
               ["Provisional CUP", "Epithelial or neuro-endocrine metastases on histology or cytology, no primary after an initial screen, before specialist review."],
               ["Confirmed CUP", "On final histology, no primary despite the initial screen, specialist review and further investigations."]],
      team: "NICE CG104: a CUP team of an oncologist, a palliative care physician and a CUP specialist nurse or key worker, reviewing every result with a named pathologist and radiologist.",
      records: ["The stage: MUO, provisional CUP or confirmed CUP (recorded by the doctor)", "Clinical examination note (breast, nodes, skin, genital, rectal and pelvic examination) and performance status",
                "Blood tests: full blood count, renal function, liver function, calcium, LDH, albumin; urinalysis", "CT (or MRI) of neck, chest, abdomen and pelvis; chest X-ray",
                "Biopsy histopathology with an immunohistochemistry panel (NICE: CK7, CK20, TTF-1, PLAP, ER in women, PSA in men for adenocarcinoma)",
                "Tumour markers by presentation: PSA (men), AFP and hCG (midline nodes), CA125 (women with peritoneal disease)",
                "Conditional: mammography and breast MRI, endoscopy or ENT panendoscopy, PET-CT, myeloma screen, testicular ultrasound", "Optional: NGS / MSI report; palliative care input"],
      conflict: "ESMO 2023 asks mammography for every woman; NICE says not routinely. The doctors should decide.",
      india: "No ICMR or NCG guideline for CUP was found [unverified]. Sources for a protocol would be NICE CG104 (verbatim, UK) and ESMO 2023 (paywalled full text)."
    },
    newDepts: [
      ["Medical Genetics", "Brings a three-generation pedigree, pre- and post-test counselling notes, consent, germline reports (BRCA1/2, PALB2, MLH1, MSH2, MSH6, RET) with the ACMG five-tier class, and a cascade testing plan (ISMPO 2025 Indian consensus; ESMO 2023 germline follow-up). ESMO 2025 names clinical geneticists as key members of molecular tumour boards. Tata Memorial's ACTREC runs a national genetics unit. Likely a supporting role: counselling and germline reports on request."],
      ["Pediatric Surgery", "SIOPE 2025: paediatric teams 'must consist of... paediatric surgeons'. Brings biopsy choice, central line ports, resectability notes (neuroblastoma image-defined risk factors, PRETEXT for hepatoblastoma, Wilms node sampling and tumour spill). Tata Memorial's Paediatric Solid Tumour group includes surgical oncology, radiotherapy, radiology, nuclear medicine, pathology and palliative medicine."],
      ["Palliative Medicine", "Already in the code. NICE makes it a required member of the CUP team; 48.9% of Indian boards have a palliative specialist."],
      ["Hematology", "Already in the code as Haematology. Tata Memorial runs separate adult and paediatric haematolymphoid groups."]
    ],
    nextCancers: "By Indian frequency (NCRP and GLOBOCAN agree): oesophagus, stomach, ovary, prostate, then liver, lymphoma, leukaemia, thyroid, gallbladder, corpus uteri; paediatric groups. Each needs its Indian source first (NCG or ICMR); NCG Essential / Optimal tiers only where the NCG document for that site is on hand.",
    sources: [
      ["NCRP 2020, projections by site and sex", "https://www.ncdirindia.org/All_Reports/Report_2020/resources/Chapter14ProjectionofCancerCasesinIndia.pdf"],
      ["GLOBOCAN 2024, India fact sheet", "https://gco.iarc.who.int/media/globocan/factsheets/populations/356-india-fact-sheet.pdf"],
      ["IJMR 2022 and 2025 estimates (NCDIR)", "https://pmc.ncbi.nlm.nih.gov/articles/PMC10231735/"],
      ["Kapoor 2024, childhood and adolescent cancers, Indian Pediatrics", "https://www.indianpediatrics.net/jan2024/39.pdf"],
      ["HBCR 2021 report", "https://ncdirindia.org/All_Reports/HBCR_2021/resources/HBCR_2021.pdf"],
      ["NICE CG104, metastatic malignancy of unknown primary", "https://www.nice.org.uk/guidance/cg104/chapter/Recommendations"],
      ["ESMO 2023 CUP guideline (Kramer et al.)", "https://doi.org/10.1016/j.annonc.2022.11.013"],
      ["Indian CUP review, IJMPO 2018", "https://doi.org/10.4103/ijmpo.ijmpo_91_17"],
      ["Tata Memorial Annual Report 2018-19 (11 Disease Management Groups)", "https://actrec.gov.in/sites/default/files/AR_2019E.pdf"],
      ["NCRP hospital tumour board survey, ecancer 2026", "https://pmc.ncbi.nlm.nih.gov/articles/PMC13161587"],
      ["ISMPO 2025 hereditary breast and ovarian cancer consensus", "https://www.ijmpo.org/assets/articles/2025/pdf/s-0044-1788727.pdf"],
      ["SIOPE 2025 European standards of care for children with cancer", "https://ccieurope.eu/wp-content/uploads/2025/09/European-Standards-of-Care-for-Children-and-Adolescents-with-Cancer-2025.pdf"],
      ["WHO ICD-10 2019 (C80)", "https://icd.who.int/browse10/2019/en"],
      ["Tempus oFM preprint, arXiv 2608.24688", "https://arxiv.org/abs/2608.24688"]
    ]
  },

  /* possible questions for the doctors (meeting 19 Oct); nothing decided */
  questions: [
    "Medical Genetics: a treating department (owns Case Files) or a supporting one (answers requests)?",
    "Keep the three departments the build added: Medical Gastroenterology, Dental Surgery / OMFS, Anaesthesiology?",
    "Cancer picker: organ-system groups with India top-10 badges and a men / women / children filter: acceptable? Which source for the top 10: NCRP 2020 or GLOBOCAN 2024?",
    "Cancer of Unknown Primary: which records are required at each stage (MUO, provisional, confirmed)? Mammography for every woman (ESMO) or only when it fits (NICE)?",
    "Manual 'other cancer': what minimum records should it ask for, if any?",
    "Rename Rectal to Colorectal, or add Colon separately?",
    "Dr Minmini's Tempus link: inspiration for the screens (timeline), a scope boundary, or market context?",
    "The validation sheet: their Keep / Change / Remove answers per record."
  ]
};
