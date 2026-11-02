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

## Thyroid source and licence (item 2.6)
Decision (orchestrator, 27 Oct 2026, the owner may change it): NCG has no thyroid chapter and no Indian national thyroid guideline was found, and
the ESMO 2019 page says "All rights reserved worldwide", so `thyroid.json` follows the `cup.json` precedent with a NICE guideline: **NICE NG230,
Thyroid cancer: assessment and management** (published 19 December 2022).
- Fetched: 27 Oct 2026, with curl from https://www.nice.org.uk/guidance/ng230/chapter/Recommendations (HTTP 200, 97 KB). Text copy
  `/data/vaidyx/tb_resources/guidelines/nice/NG230_thyroid_recommendations.txt` (tags stripped with `python -I`; recommendation numbers kept);
  log `LICENCE_NG230.txt` beside it.
- Terms found (footer of every NICE page, "(c) NICE 2026. All rights reserved. Subject to Notice of rights", and the Notice of Rights on
  https://www.nice.org.uk/terms-and-conditions): clause 18.1 gives reuse under the NICE UK Open Content Licence "in the United Kingdom only";
  clause 18.2: "Except for personal use, study or personal research, copyright content owned by ... NICE may not be used, reproduced, translated,
  distributed or transmitted in any form ... without the prior written agreement of NICE. Such an agreement may be subject to a licence and fee";
  clause 18.3: use for artificial intelligence purposes needs an approval, a licence and a fee (for international use). The page's own metadata
  adds: "You can download material for private research, study or in-house use only. Do not distribute or publish any material from this site
  without first obtaining NICE's permission."
- So the UK open licence the brief assumed covers the United Kingdom only; for a hospital in India clause 18.2 applies beyond personal use and
  study. The CUP checklist (CG104, accepted by the owner on 18 Oct 2026) is on the same footing. Owner to decide: keep the draft as it is, ask NICE
  for written agreement, use the ATA 2015 guideline (free to read on PubMed Central, Mary Ann Liebert copyright, no Creative Commons licence; the
  research note's open question), or return thyroid to the generic checklist by deleting `tumour_board/protocols/thyroid.json`.
- Used: assessment and diagnosis recommendations 1.2.1 to 1.2.14 and the thyroglobulin measurement line of 1.5.2 (10 verbatim quotes, each with its
  recommendation number), plus three NCG head and neck lines (p 48 and 51, thyroid CT and ultrasound reporting formats). NG230 has no recommendation on
  the clinical history, the histology report, laryngoscopy or genetic testing (RET); the last three are optional items without a source and the history
  record cites the line that names a family history. No treatment, radioactive iodine, TSH suppression or follow-up line is quoted as a record.

## Brain source and licence (item 2.8)
Decision (orchestrator, 27 Oct 2026, the owner may change it): NCG has no CNS file and no Indian national brain tumour guideline was found, so the adult
records of `brain_cns.json` come from **EANO 2021, "EANO guidelines on the diagnosis and treatment of diffuse gliomas of adulthood"** (Weller et al.,
Nature Reviews Clinical Oncology 18:170-186, DOI https://doi.org/10.1038/s41571-020-00447-z, PMC https://pmc.ncbi.nlm.nih.gov/articles/PMC7904519/).
- Fetched: 27 Oct 2026, with curl. The PMC PDF link answered with a proof-of-work "Preparing to download" page and the Europe PMC render link with a 403
  browser check; neither was worked around. The publisher's own open-access PDF (https://www.nature.com/articles/s41571-020-00447-z.pdf, HTTP 200,
  17 pages, 1,786,657 bytes) was stored as `/data/vaidyx/tb_resources/guidelines/eano/EANO_2021_diffuse_gliomas_Weller.pdf`, read only with `python -I`
  and pypdf. Log beside it: `LICENCE.txt` (sha256, source, licence text).
- Licence line read on the PDF itself (PDF page 17): "Open Access This article is licensed under a Creative Commons Attribution 4.0 International
  License, which permits use, sharing, adaptation, distribution and reproduction in any medium or format, as long as you give appropriate credit to the
  original author(s) and the source, provide a link to the Creative Commons license, and indicate if changes were made ... To view a copy of this license,
  visit http://creativecommons.org/licenses/by/4.0/." Copyright line: "(c) The Author(s) 2020, corrected publication 2022". The Europe PMC full-text XML
  of the same article carries the same paragraph. CC BY 4.0 conditions are met by the credit and link in the protocol note, the unchanged file, and the
  statement that the quotes are verbatim and the labels, tiers and routing are Vaidyx's own draft.
- Page numbers: PDF page n = journal page n + 169. Used: pages 2, 3, 6 and 7 (15 verbatim quotes in the 10 records; the post-operative MRI
  line has no level). The guideline rests on the WHO 2016 classification and cIMPACT-NOW, not WHO 2021, and is European.
- Tier rule (a proposal, in the protocol note): EANO level of recommendation A or B for a record asked in every patient is a; the same test only in a
  subgroup the system never judges (negative IDH1 stain, retained ATRX, glioblastoma, midline location) is system tier c with the condition; a sentence
  with no level is a proposed b. Treatment lines (steroids, anticonvulsants, extent of resection, temozolomide) are not copied.
- Not in EANO for diffuse gliomas: any line on CSF or spinal imaging (none listed); a paediatric section. The NCG paediatric book has no brain tumour
  chapter (checked: no medulloblastoma, glioma, ependymoma or craniopharyngioma), so the `child` setting reuses the records with child tiers noted in
  each `tier_basis`, and the protocol note says the child checks need a clinician's check even more than the rest. ISNO 2017 and 2019 were not used
  (reuse terms not confirmed).
- Orchestrator's decision after reading the terms above (27 Oct 2026, 08:05): the thyroid checklist built from NG230 is **not shipped**; it is
  parked at `/data/vaidyx/night-v3/runs/parked/thyroid.json` (copy it back to `tumour_board/protocols/` to restore it; its tests were removed with it and would be rewritten), thyroid stays on the generic checklist and the picker says "no checklist yet", and the owner decides between a
  written NICE agreement, ATA 2015 (licence to be read on its PDF) and generic. The NICE text copy stays under the library as in-house research
  material only. The same question stands for the CUP checklist's NICE CG104 quotes.
