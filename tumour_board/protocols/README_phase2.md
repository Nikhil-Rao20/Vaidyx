# The Phase 2 checklists (night-v3, 27 Oct 2026): drafts that need a clinician's check

Nineteen checklists were added on 27 Oct 2026 (night-v3 plan, Phase 2, owner decision D6): every one is `version` "0.1-draft" with
`approval.status` "draft" and the note "needs a clinician's check" (the website shows "Checklist built (draft): needs a clinician's check"
and the owner's pill "Draft checklist: needs a clinician's check"). They never compute a stage and never advise treatment. The records,
tiers (NCG a Essential, b Optimal, c Optional, "none" not applicable per setting), document types, departments and facts were transcribed
from the research notes `docs/night-v3/research/01_cancer_checklists_part1.md`, `_part2.md`, `_part3.md` (one section per cancer: the
work-up table with the book, page and verbatim line, the tier basis, the new facts, the open questions), written against the NCG India
books in `/data/vaidyx/tb_resources/guidelines/ncg_india/` and, where NCG has no chapter, an open-access guideline whose licence was read
on the PDF itself (`docs/night-v3/research/01_cancer_checklists.md`, "Brain source and licence").

**Every quoted line is verified by `tumour_board/tests/test_protocol_schema.py`**: a source carries `file` (under the guideline library),
`page` (the PDF page; "n/a" with `where` for the two Word books) and `quote`; the test finds the whitespace-folded quote on that page
(pypdf), in the Word document, or, for a source marked `"ocr": true` (the adult haematolymphoid flow charts are pictures with no text
layer), in the project's OCR engine's reading of that page made on the fly (Tesseract through `ocr_engine.read_page`, never a stored
transcription). A tier the book prints without a letter is a proposal, said so in `tier_basis`. A record NCG asks for only under a
condition the system never judges (a stage, an age, a finding) has system tier c with `condition` (shown, never counted). Records that
can exist only after surgery or after treatment (resection histopathology, MRD, nephrectomy histopathology) sit under `optional`
(their book tiers kept in `tiers_in_the_book`). The research notes' "multidisciplinary meeting" rows are not records: the Case File is
that discussion (the NCG line is kept in each file's `policy_basis`).

| id | label | settings | records | quotes | books (under the guideline library) |
|---|---|---|---|---|---|
| `colorectal_colon` | Colon cancer | non_metastatic, metastatic | 11 + 2 optional | 16 | management-of-colorectal-cancer.pdf |
| `stomach` | Stomach cancer | early_localized, locally_advanced, metastatic | 11 + 2 optional | 13 | ncg-gi-draft-2021-gastric-cancer.pdf |
| `oesophagus` | Oesophageal cancer | early_localized, locally_advanced, metastatic | 10 + 3 optional | 11 | ncg-guidelines-for-thoracic-cancer-2019.pdf |
| `liver_hcc` | Liver cancer (hepatocellular carcinoma) | resectable, locoregional, extrahepatic | 16 + 1 optional | 16 | ncg-gi-hepatocellular-carcinoma.docx |
| `gallbladder` | Gallbladder cancer | per_primum, incidental, locally_advanced, metastatic | 13 + 1 optional | 23 | ncg-gi-draft-2021-gall-bladder-cancer.pdf; ncg-gi-draft-2021-gallbladder-cancer-radiology-synoptic.pdf |
| `ovary` | Ovarian cancer (epithelial) | early, advanced, recurrent | 14 + 1 optional | 14 | ncg-guidelines-for-gynecological-cancer-2019.docx |
| `corpus_uteri` | Cancer of the corpus uteri (endometrium) | early, advanced | 10 + 1 optional | 10 | ncg-guidelines-for-gynecological-cancer-2019.docx |
| `prostate` | Prostate cancer | localised, locally_extensive, metastatic_hspc, metastatic_crpc | 11 + 1 optional | 11 | ncg-guidelines-for-urological-malignancies-2019.pdf |
| `kidney` | Kidney cancer (adult renal cell carcinoma) | localised, metastatic | 9 + 1 optional | 10 | ncg-guidelines-for-urological-malignancies-2019.pdf |
| `germ_cell` | Germ cell tumour of the testis | stage_i, stage_ii_iii, relapsed | 11 + 1 optional | 12 | ncg-guidelines-for-urological-malignancies-2019.pdf |
| `larynx` | Cancer of the larynx (head and neck) | early, locally_advanced, metastatic | 11 + 2 optional | 15 | ncg-guidelines-for-head-neck-cancer-2019.pdf |
| `lymphoma` | Lymphoma (Hodgkin and non-Hodgkin) | adult_hodgkin, adult_nhl, child_hodgkin, child_nhl | 17 + 1 optional | 50 (19 from flow chart pictures, OCR) | ncg-guidelines-for-adult-hematolymphoid-2019.pdf; ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| `leukaemia` | Leukaemia (acute and chronic) | adult_acute, adult_chronic, child_acute, child_chronic | 15 + 2 optional | 63 (32 from flow chart pictures, OCR) | ncg-guidelines-for-adult-hematolymphoid-2019.pdf; ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| `wilms` | Wilms tumour (child) | unilateral, bilateral | 7 + 2 optional | 11 | ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| `retinoblastoma` | Retinoblastoma (child) | unilateral, bilateral | 9 + 1 optional | 12 | ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| `bone_sarcoma` | Bone sarcoma (osteosarcoma, Ewing sarcoma, chondrosarcoma) | osteosarcoma, ewing, chondrosarcoma | 15 + 2 optional | 25 | ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf |
| `soft_tissue_sarcoma` | Soft tissue sarcoma | non_metastatic, metastatic, paediatric_rhabdomyosarcoma | 13 + 1 optional | 21 | ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf; ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| `brain_cns` | Brain and CNS tumours | adult_glioma, adult_other, child | 9 + 2 optional | 15 | eano/EANO_2021_diffuse_gliomas_Weller.pdf |
| `generic_haem` | Other blood cancer (no disease-specific Indian protocol) | as_recorded | 3 + 2 optional | 3 | Owner decision R05-Q04, 17 Oct 2026 |

**Thyroid** has no checklist: NCG has no thyroid chapter, no Indian national guideline was found, ESMO 2019 is "All rights reserved",
and NICE NG230's terms allow reuse outside the UK only with NICE's written agreement, so the checklist built from NG230 was parked
outside the repo (`/data/vaidyx/night-v3/runs/parked/thyroid.json`) for the owner's decision; the picker says "no checklist yet".
**Brain and CNS** adult settings come from EANO 2021 (Weller et al., Nature Reviews Clinical Oncology 18:170-186, CC BY 4.0, the
licence line read on PDF page 17 and logged in `guidelines/eano/LICENCE.txt`); the NCG paediatric book has no brain chapter, so the
child setting reuses the records and needs a clinician's check even more than the rest.

The new facts (72) and document types (bone_marrow, flow_cytometry, cytogenetics, csf, echocardiogram, ophthalmology_note, audiometry)
are in `facts.json`; their title keywords in `doc_type_keywords.json`, their HIS codes and label patterns in `his_codes.json`, their units
in `units.json`; the dose and radiotherapy lines of the new cancers (378, every one a verbatim line with its page, written by
`tumour_board/eval/build_dose_references.py`) in `dose_references.json`; the NCG synoptic reporting formats for colon, larynx,
gallbladder, prostate, kidney and germ cell in `specialty_packs.json`. `generic_haem.json` is the blood cancer variant of the generic
rule (owner decision R05-Q04 and plan item 2.9): three core records, no staging imaging.
