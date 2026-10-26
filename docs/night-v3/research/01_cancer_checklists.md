# Cancer checklists research (item 0.2, for Phase 2)

Three notes hold the detail, one per group of cancers, written on 27 Oct 2026 from the NCG India books in
`/data/vaidyx/tb_resources/guidelines/ncg_india/` (and, for thyroid and brain, open-access candidates found on the web):
[part 1: GI and thoracic](01_cancer_checklists_part1.md), [part 2: gynaecology, urology, head and neck, thyroid](01_cancer_checklists_part2.md),
[part 3: blood cancers, paediatric, sarcoma, CNS](01_cancer_checklists_part3.md). Each cancer has the same sections: Source, Settings
proposed, Work-up records (a table with record id, label, tier per setting, doc types, department, required facts, page, verbatim quote,
tier basis), New facts needed, Staging system, Indian notes, Regimen or dose tables (pages only), Open questions.

## The cancers

| Cancer | protocol id | note |
|---|---|---|
| Colon cancer | `colorectal_colon` | part 1 |
| Stomach cancer | `stomach` | part 1 |
| Oesophageal cancer | `oesophagus` | part 1 |
| Liver cancer, hepatocellular carcinoma | `liver_hcc` | part 1 |
| Gallbladder cancer | `gallbladder` | part 1 |
| Ovarian cancer, epithelial | `ovary` | part 2 |
| Cancer of the corpus uteri, endometrium | `corpus_uteri` | part 2 |
| Prostate cancer | `prostate` | part 2 |
| Kidney cancer, adult renal cell carcinoma | `kidney` | part 2 |
| Germ cell tumour of the testis | `germ_cell` | part 2 |
| Cancer of the larynx | `larynx` | part 2 |
| Thyroid cancer | `thyroid` | part 2 |
| Lymphoma | `lymphoma` | part 3 |
| Leukaemia | `leukaemia` | part 3 |
| Wilms tumour | `wilms` | part 3 |
| Retinoblastoma | `retinoblastoma` | part 3 |
| Bone sarcoma | `bone_sarcoma` | part 3 |
| Soft tissue sarcoma | `soft_tissue_sarcoma` | part 3 |
| Brain and CNS tumours | `brain_cns` | part 3 |

## Reading conventions (checked by the orchestrator)
- Every table quote of parts 1 to 3 was checked character for character (whitespace folded) against the extracted text of its book,
  cached in `/data/vaidyx/night-v3/research_text/` (pypdf, one `=== page N ===` marker per PDF page; the .docx files read from
  `word/document.xml`): parts 1 and 2 have no misses; part 3 has no misses apart from the rows marked IMAGE (below).
- The cited page is the PDF page (index + 1). It equals the printed page in the urology, head and neck, thoracic, adult haematolymphoid
  and bone books; the paediatric book's printed footer is one less than the PDF page.
- The two .docx books (gynaecology 2019, hepatocellular carcinoma) have no page numbers: records cite page "n/a" with a "where" line
  naming the section heading (`test_tiers.py` allows this).
- **Adult haematolymphoid book: the disease flow charts are images** (no text layer; the annexures on pages 79 to 95 have text). Part 3
  read the work-up boxes and their (a)/(b)/(c) letters from the page images and marks those rows IMAGE. Phase 2.7 must OCR those pages
  with the existing OCR engine (`tumour_board/ocr_engine.py`, Tesseract) into the research text cache and quote from the OCR text, or
  transcribe them by hand and say so in the record note; a quote is stored only once it is found in a text.
- NCG tiers: (a) Essential, (b) Optimal, (c) Optional. Where the book prints no letter the note proposes a tier and states the basis;
  where the book's letter holds only under a condition the system never judges, the note proposes system tier c with the NCG tier
  kept as the condition (the cup.json pattern).
- No book carries a PM-JAY remark; the India-specific lines found are few (part 1: HCC cost line, the chest X-ray alternative for
  colorectal; part 2: one Indian-origin element in head and neck). The gallbladder cancer belt of north India is not in the NCG file.

## New facts proposed across the three parts (72 ids, for item 2.1, `facts.json`)
`tumour_site_colon`, `nodes_examined`, `obstruction_perforation`, `tumour_site_stomach`, `cdh1_result`, `tumour_location_oesophagus`, `siewert_type`, `trg`, `lirads_category`, `inr`, `hbsag`, `anti_hcv`, `hbv_core_ab`, `afp`, `pivka`, `child_pugh_class`, `varices_finding`, `hvpg_mmhg`, `flr_percent`, `gb_mass`, `ca19_9`, `vessel_involvement`, `bile_duct_involvement`, `cystic_duct_margin`, `ca125`, `beta_hcg`, `ldh`, `inhibin_b`, `he4`, `brca_status`, `p53`, `pole`, `psa`, `gleason_isup`, `positive_cores`, `hrd_status`, `corrected_calcium`, `embryonal_component`, `igcccg_group`, `fertility_preservation`, `testosterone`, `lh`, `fsh`, `cord_mobility`, `laryngeal_function`, `laryngeal_subsite`, `bethesda_category`, `thyroglobulin`, `calcitonin`, `tirads`, `extrathyroid_extension`, `b_symptoms`, `molecular_markers_haem`, `bone_marrow_result`, `deauville_score`, `csf_cytology`, `flow_cytometry_result`, `cytogenetics_result`, `beta2_microglobulin`, `anaplasia`, `loh_1p_16q`, `ophthalmic_examination`, `rb_group`, `germline_result`, `alkaline_phosphatase`, `sarcoma_fusion`, `percent_necrosis`, `tumour_depth`, `kps`, `idh_status`, `codeletion_1p19q`, `mgmt_promoter`

Phase 2.1 keeps the ids short and consistent (one `ldh`, one `afp`, one `nodes_examined` shared by several cancers), gives each a
label, a kind (text, number with unit, categorical with values) and the document types that carry it, and adds the keywords the
extractor needs.

## New document types proposed (for item 2.1, `facts.json`, `doc_type_keywords.json`, `his_codes.json`)
`bone_marrow`, `echocardiogram`, `csf`, `flow_cytometry`, `cytogenetics`, `ophthalmology_note`, `audiometry`

Part 1 and part 2 proposed no new document type (the DMSA scan and HVPG use `other`).

## Open-access sources for the cancers NCG does not cover (nothing downloaded yet)
| Cancer | Recommended book | Licence as found | Fallback |
|---|---|---|---|
| Thyroid | ESMO 2019 (Filetti et al., Annals of Oncology 30(12):1856-1883): compact, page-numbered, all four histologies, work-up and follow-up | not confirmed: the ESMO page says "All rights reserved worldwide"; the publisher's terms must be read before a copy is kept on the server | ATA 2015 (Thyroid 26(1):1-133, on PMC): free to read, Mary Ann Liebert copyright, not Creative Commons |
| Brain and CNS | EANO 2021, "EANO guidelines on the diagnosis and treatment of diffuse gliomas of adulthood" (Nature Reviews Clinical Oncology 18:170-186), https://pmc.ncbi.nlm.nih.gov/articles/PMC7904519/ | CC BY 4.0 as shown on the PMC page (re-check on the PDF itself before storing) | ISNO 2019 (Neurology India 67(1):173-182, diagnosis only; Europe PMC marks it not open access) for the pathology records once its terms are confirmed |

NCG has no thyroid chapter (the head and neck book has only radiology templates for thyroid CT, pages 47 to 49, and ultrasound, pages
50 to 51) and no CNS file (the 2021 manual only names NICE NG99 as an example, pages 30 and 59). No Indian national thyroid or brain
tumour guideline was found. NCCN is not acceptable (login, no redistribution).

## Decisions for Phase 2 (orchestrator, 27 Oct 2026)
1. The thyroid and brain checklists are built from the open-access books above only after the licence is read on the PDF itself and
   logged in this note; until then the two cancers keep the generic checklist and the picker says so. If the ESMO licence does not
   allow a server copy, thyroid uses the ATA 2015 paper from PMC (read online, quotes with page) or stays generic: owner decision.
2. Lymphoma and leukaemia get at most four settings each (adult and child), as part 3 proposes; child CML and child APML share the
   child settings.
3. Bone sarcoma keeps the chondrosarcoma setting only if the records differ; otherwise two settings (osteosarcoma, Ewing).
4. Eye examination, echocardiogram and audiometry route to "owner" (no ophthalmology or cardiology department in the hospital set-up).
5. Every new protocol is a draft: `version` "0.1-draft", `approval.status` "draft", the note "Draft checklist from <book>: needs a
   clinician's check" (owner decision D6).
