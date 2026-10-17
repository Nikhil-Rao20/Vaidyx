# Cancer of Unknown Primary (CUP) checklist: `cup.json`

Status: **draft 0.1, not approved for real use.** `cup.json` carries `"approval": {"status": "draft", "note": "Needs a named doctor's approval before real use (owner decision 17 Oct 2026)"}`. `protocol.py` reads only the keys it knows (`id`, `label`, `version`, `note`, `settings`, `records` / `mandatory`, `optional`, `extract_facts`, `core_data`, `post_board`, `policy_basis`, `site`), so the unknown top-level keys `approval`, `applies_if_note` and `guideline_sources` are tolerated (checked: `protocol.get`, `list_protocols`, `rules.evaluate`, `rules.routes_table` and the unit suite all run with them). Nothing in this checklist computes a stage, names a likely primary or suggests treatment; the diagnostic phase (setting) is chosen by the doctor "as recorded".

Written 18 Oct 2026 from the owner's design (question rounds R05-Q06, R05-Q07, R05-Q08, R07-Q06, R07-Q10, all answered 17 Oct 2026) and the clinical advisers' ask that CUP must exist ("many board cases will be such cases; the board helps investigate").

## 1. Sources

| Source | What was used | How it is cited in `cup.json` |
|---|---|---|
| NICE CG104, Metastatic malignant disease of unknown primary origin in adults: diagnosis and management. Published 26 July 2010, last updated 26 April 2023, last reviewed 16 July 2025 (surveillance decision: no update). https://www.nice.org.uk/guidance/cg104 | Recommendations 1.1.1.5, 1.1.1.6, 1.2.1.1, 1.2.2.1 to 1.2.2.9, 1.2.3.1, 1.2.3.3, 1.3.1.2, 1.3.2.1, 1.5.1.2 and the three definitions under "Terms used in this guideline" (MUO, provisional CUP, confirmed CUP) | `"page": "n/a"` with `"where"` = the recommendation number or the term defined (the cervix protocol's pattern for a source without page numbers). The Recommendations page was downloaded with curl on 18 Oct 2026 (the WebFetch tool is refused by nice.org.uk, HTTP 403); every quote was checked against that text. The guideline PDF is not in the guideline library (`nice/` holds NG36, NG101, NG122, NG151 only). |
| ESMO Clinical Practice Guideline: cancer of unknown primary (Kramer A, Bochtler T, Pauli C, et al. Annals of Oncology 2023;34(3):228-246, doi 10.1016/j.annonc.2022.11.013) | Definition (p. 1), histology and IHC (p. 2), clinical work-up (p. 3), prior malignancy (p. 5), the recommendation boxes (pp. 6 to 8), breast-like and head and neck-like CUP (p. 11), clinical trials (p. 14) | `"page"` = the PDF page number 1 to 19 as the guideline library reads `/data/vaidyx/tb_resources/guidelines/esmo/ESMO_2023_cancer_of_unknown_primary_Kramer.pdf` with pypdf (the same counting `test_phase9_review` uses for the oral cavity quotes); `"where"` names the section and the journal page. Quotes are copied as the PDF text layer extracts them, so two of them keep a line-end hyphen artefact ("gynaeco- logical", in the CA 125 record), exactly as the NCG head and neck quotes do ("Contrast en- hanced"). ESMO's supplementary tables S1 to S10 are not on disk and are not quoted. |
| NCG India | **No NCG guideline for cancer of unknown primary exists** (owner, 17 Oct 2026). None of the 22 NCG documents in `ncg_india/` covers it; ICMR, TMC and the MoHFW STGs on disk do not either. Said so in `policy_basis` and `note`. An Indian source replaces NICE and ESMO as soon as one exists. | `guideline_sources[2]`, `policy_basis` |
| Checked and not usable | ICRI / IRIA onco-imaging checklists 2020 mention "unknown primary" only in the AJCC 8th edition background (p. 12) and have no CUP chapter; the PET-CT chapter (pp. 186 to 188) covers the imaging protocol, not report content. RCPath G112 (neck dissection) mentions CUP only for head and neck nodes. | not cited |

Conflicts between NICE and ESMO were settled the owner's way (R05-Q07: NICE's rule wins): mammography (NICE: not routinely; ESMO: every woman) and tumour markers (NICE 1.2.2.1: none during diagnosis except AFP, hCG, PSA, CA125 in the named presentations; ESMO also lists CEA, CA19-9, CA72-4, CA15-3, chromogranin A). CEA is extracted when a report carries it but is not a record.

## 2. How the checklist grows with the phase the doctor records

The three settings are NICE's diagnostic phases; the definitions in `cup.json` are NICE's own words (Terms used in this guideline).

| Setting id | Label | NICE definition (verbatim) |
|---|---|---|
| `muo` | MUO (malignancy of undefined primary origin), as recorded | Metastatic malignancy identified on the basis of a limited number of tests, without an obvious primary site, before comprehensive investigation. |
| `provisional_cup` | Provisional CUP (after the initial screen, before specialist review), as recorded | Metastatic epithelial or neuro-endocrine malignancy identified on the basis of histology or cytology, with no primary site detected despite a selected initial screen of investigations, before specialist review and possible further specialised investigations. |
| `confirmed_cup` | Confirmed CUP (after specialist review and special investigations), as recorded | Metastatic epithelial or neuro-endocrine malignancy identified on the basis of final histology, with no primary site detected despite a selected initial screen of investigations, specialist review, and further specialised investigations as appropriate. |

Tiers per setting as `protocol.tier_for` / `protocol.required` resolve them (a = Essential, counted at every hospital; b = Optimal, counted at an Optimal-level hospital, otherwise shown; c = Optional, shown only; none = not applicable in that setting; "c + question" = doctor-settled, see section 4). "Unrecorded" is the strictest tier, applied until the coordinator records the setting.

| Record (`id`) | Desk | Unrecorded | MUO | Provisional | Confirmed | Source lines |
|---|---|---|---|---|---|---|
| Clinical history and examination, performance status, question (`clinical_history`) | owner (default Medical Oncology) | a | a | a | a | NICE 1.2.1.1, 1.3.2.1; ESMO p. 3, p. 8 |
| Complete blood count (`cbc`) | Pathology | a | a | a | a | NICE 1.2.1.1; ESMO p. 3 |
| LFT and urea, electrolytes, creatinine (`liver_renal_function`) | Biochemistry | a | a | a | a | NICE 1.2.1.1, 1.3.2.1; ESMO p. 3 |
| Serum calcium (`serum_calcium`) | Biochemistry | a | a | a | a | NICE 1.2.1.1; ESMO p. 3 |
| Urinalysis (`urinalysis`) | Pathology | a | a | a | a | NICE 1.2.1.1 |
| LDH (`ldh`) | Biochemistry | a | a | a | a | NICE 1.2.1.1, 1.3.2.1; ESMO p. 8 |
| Chest X-ray (`chest_xray`) | Radiology | a | a | a | a | NICE 1.2.1.1 |
| CT chest, abdomen and pelvis (`ct_chest_abdomen_pelvis`) | Radiology | a | a | a | a | NICE 1.2.1.1; ESMO p. 3, p. 6 |
| Biopsy with histopathology or cytology (`histopathology`) | Pathology | a | b | a | a | NICE 1.2.1.1, 1.2.3.3, definition of provisional CUP; ESMO p. 6 |
| IHC on the metastasis, NICE panel (`ihc_panel`) | Pathology | a | none | a | a | NICE 1.2.2.7, 1.2.2.8; ESMO p. 2, p. 6 |
| Specialist review of all investigations (`specialist_review`) | Medical Oncology | a | none | c | a | NICE 1.1.1.5, 1.1.1.6, definition of confirmed CUP; ESMO p. 3 |
| Molecular profiling, panel NGS and MSI (`molecular_profiling`) | Pathology | c | none | c | c | ESMO p. 6; NICE 1.2.2.9 note |
| FDG PET-CT, selected cases (`pet_ct`) | Nuclear Medicine | c + question | c + question | c + question | c + question | NICE 1.2.2.5, 1.2.2.6, 1.3.1.2; ESMO p. 3, p. 6, p. 7 |
| Mammography, women, only when features fit breast cancer (`mammography`) | Radiology | c + question | c + question | c + question | c + question | NICE 1.2.2.3; ESMO p. 3, p. 6 |
| Breast MRI, axillary node adenocarcinoma (`mri_breast`) | Radiology | c + question | none | c + question | c + question | NICE 1.2.2.4; ESMO p. 11 |
| Myeloma screen, lytic bone lesions (`myeloma_screen`) | Biochemistry | c + question | c + question | c + question | c + question | NICE 1.2.1.1 |
| Upper or lower GI endoscopy (`gi_endoscopy`) | Medical Gastroenterology | c + question | c + question | c + question | c + question | NICE 1.2.1.1, 1.2.2.2; ESMO p. 3 |
| Bronchoscopy (`bronchoscopy`) | Pulmonology | c + question | c + question | c + question | c + question | NICE 1.2.3.1; ESMO p. 3 |
| ENT panendoscopy, cervical node presentation (`ent_panendoscopy`) | ENT / Head and Neck Surgery | c + question | c + question | c + question | c + question | NICE 1.2.2.5; ESMO p. 11 |
| Serum PSA, men (`psa`) | Biochemistry | c + question | c + question | c + question | c + question | NICE 1.2.1.1, 1.2.2.1; ESMO p. 3 |
| Serum CA 125, women (`ca125`) | Biochemistry | c + question | c + question | c + question | c + question | NICE 1.2.1.1, 1.2.2.1; ESMO p. 3 |
| Serum AFP and hCG (`afp_hcg`) | Biochemistry | c + question | c + question | c + question | c + question | NICE 1.2.1.1, 1.2.2.1; ESMO p. 3 |
| Testicular ultrasound, men (`testicular_ultrasound`) | Radiology | c + question | c + question | c + question | c + question | NICE 1.2.1.1 |

Optional (informational, never counted): treatment summary of any earlier cancer (`prior_treatment`, owner; ESMO p. 5: a quarter of presumed CUP had a prior malignancy), previous imaging (`prior_imaging`), discharge summary (`discharge`, owner), previous Tumour Board record (`previous_board`, MDT Coordinator).

So in MUO the gate counts 8 records (the unconditional part of NICE's initial screen); provisional CUP adds the biopsy and the IHC; confirmed CUP adds the specialist review. This is the owner's answer to R05-Q06 ("Yes, grows with the stage: MUO asks the initial screen; provisional adds the biopsy with an IHC panel and markers; confirmed adds the specialist review").

## 3. Every decision, with its reason

| # | Decision | Reason and source |
|---|---|---|
| D1 | Three settings named after NICE's phases, with NICE's definitions verbatim in `settings[].definition` | Owner R05-Q06; NICE "Terms used in this guideline". Vaidyx never decides the phase. |
| D2 | The unconditional items of NICE 1.2.1.1 are Essential in every setting: history and examination with ECOG and the board question, FBC, U and E and creatinine with LFT, calcium, urinalysis, LDH, chest X-ray, CT chest, abdomen and pelvis | NICE 1.2.1.1 ("Offer the following investigations to patients with MUO"); ESMO's "minimal mandatory work-up" (p. 3) lists the same history, examination, bloods and CT or MRI. |
| D3 | Blood tests split by test and desk (CBC and urinalysis: Pathology; LFT / RFT, calcium, LDH, tumour markers: Biochemistry) | V2 item 2.4 (each request reaches the desk that does it), as the other protocols split their "Baseline blood tests". |
| D4 | Calcium, urinalysis, LDH, PSA, CA 125, AFP / hCG and the myeloma screen are record-level checks (`required_facts: []`), recognised by header words (`region`) on a final signed lab report | The fact catalogue (`facts.json`) has no field for any of them and `rules.py` raises on an unknown fact id; `facts.json` was not edited (owner rule: no existing protocol file edited). Suggested fields in section 6. A value reported inside a panel whose header does not name it is not recognised: the clinician confirms or waives. |
| D5 | CBC and LFT / RFT keep the ids, regions, desks and required values of the other protocols (`cbc`: haemoglobin, WBC, platelets; `liver_renal_function`: creatinine, bilirubin) | Same desks and HIS mapping as lung, breast, cervix; NICE also names serum albumin as a prognostic factor (1.3.2.1): no albumin field exists yet. |
| D6 | Chest X-ray accepts a CT or PET-CT report of the chest; the CT record accepts an MRI or PET-CT report of the same regions | NICE lists both the X-ray and the CT; ESMO allows CT or MRI of neck, thorax, abdomen and pelvis (p. 3, p. 6). The oral cavity and cervix protocols already count a CT for the chest X-ray. The clinician checks coverage (note on the record). |
| D7 | The CT record requires the sites of disease and the nodal findings as written (`distant_findings`, `nodal_findings`), not a primary lesion size | A CUP has no primary to measure; the nodal distribution (midline, cervical, axillary) is what the conditional records turn on. |
| D8 | Biopsy / histology: Essential in provisional and confirmed CUP, Optimal (b) in MUO | NICE lists the biopsy in the initial phase (1.2.1.1), but a provisional CUP is by definition identified on histology or cytology, and the owner's R05-Q06 wording adds the biopsy at provisional. "b" in MUO keeps it visible and counted at an Optimal hospital; the doctor decides whether MUO should already require it (section 5). |
| D9 | IHC: Essential from provisional CUP, not applicable in MUO; the record counts when a final IHC report, or a histopathology report whose header names IHC, is present; no marker value is required | ESMO [III, A]: histology and IHC are required; NICE 1.2.2.7 names the panel (CK7, CK20, TTF-1, PLAP, ER in women, PSA in men) for adenocarcinoma of unknown origin. Which antibodies belong in the panel is the pathologist's call; ER applies to women only and the system never judges sex or histology. ER, PR, HER2, PD-L1 and MMR are extracted when present. |
| D10 | Specialist review: Essential in confirmed CUP, shown in provisional, not applicable in MUO; documented by a CUP team / oncology note, a board record or a pathology slide review whose header names the review | NICE 1.1.1.5 (review of all investigations with a pathologist and radiologist), 1.1.1.6 (CUP network MDT) and the definition of confirmed CUP; owner R05-Q06 ("confirmed adds the specialist review"). The `region` words include "oncolog" because NICE 1.1.1.1 puts an oncologist in the CUP team, so an oncology consultation note counts and the clinician checks it. |
| D11 | Molecular profiling (panel NGS, MSI): Optional, shown only, from provisional CUP | ESMO "NGS may be carried out routinely in CUP [IV, B]" (a may-statement); gene expression profiling to find the primary is not recommended outside research (ESMO [II, D]) and NICE withdrew 1.2.2.9, pointing to a national test directory. Molecular values are extracted; Vaidyx never suggests a treatment from them. |
| D12 | PET-CT: Optional, doctor-settled | Owner: "PET-CT only in selected cases". NICE offers it for a cervical node presentation with no primary on ENT panendoscopy when radical treatment is an option (1.2.2.5), considers it for other presentations after CUP team discussion (1.2.2.6), and investigates only when the result is likely to affect a treatment decision (1.3.1.2); ESMO: optional in the routine work-up (p. 3, p. 7), generally recommended for single-site / oligometastatic and head and neck CUP (p. 6). |
| D13 | Mammography: doctor-settled on NICE's rule, with a breast ultrasound report also counting | Owner R05-Q07 ("Only when it fits, NICE"); NICE 1.2.2.3; ESMO's "Mammography in females" is quoted beside it so the doctor sees the disagreement. Sonomammography is common in India (clinical review). |
| D14 | Breast MRI: doctor-settled, not applicable in MUO | NICE 1.2.2.4 (consider, after standard breast investigations); ESMO p. 11 (mandatory before a breast-like CUP diagnosis). |
| D15 | NICE's "symptom-directed endoscopy" becomes three doctor-settled records by desk: GI endoscopy (Medical Gastroenterology), bronchoscopy (Pulmonology), ENT panendoscopy (ENT / Head and Neck Surgery) | V2 item 2.4 routing; NICE 1.2.2.2 (GI endoscopy only when symptoms, histology or radiology suggest a GI primary), 1.2.3.1 (bronchoscopy for intrapulmonary nodules unsuitable for percutaneous biopsy), 1.2.2.5 (panendoscopy before PET-CT in a cervical node presentation); ESMO p. 3 and p. 11. |
| D16 | Tumour markers (PSA, CA 125, AFP and hCG) and the testicular ultrasound are doctor-settled, each with NICE's own condition and the sex it names | NICE 1.2.1.1 with the restrictions of 1.2.2.1 ("Do not measure tumour markers during diagnosis except for"); ESMO p. 3 quoted beside. The system never judges sex or presentation. |
| D17 | Doctor-settled records are `tier: "c"` with a `condition` (shown with the source's own tier and the condition, never counted) **and** an `applies_if` block that specifies the doctor question | Owner R07-Q10 ("Doctor answers yes or no", audited; sex from registration) and R07-Q06 ("not applicable" with a reason) are decided but not built. `rules.py` reads only `applies_if_doc_type_present`, so `applies_if` is a specification the code ignores today; the `condition` mechanism is how the lung, oral cavity and cervix protocols handle the same situation today (shown, never counted). Section 4 gives the mapping. |
| D18 | No `site` key | A CUP has no organ; the two-primaries preference (V2 item 5.3) therefore never sets a CUP document aside, and `rules.other_sites` skips a protocol without a site. |
| D19 | `extract_facts` lists the catalogue facts a CUP Case File can carry (no `lesion_size`, no `figo_stage`); `core_data` relabels the NHS "stage" item as "Extent of disease as recorded (sites of metastases and nodes, with the investigations used)" and the treatment history as "including any earlier cancer" | A CUP has no primary or stage to record; ESMO p. 5: a prior malignancy is always considered. The clinical trial item also rests on NICE 1.5.1.2 and ESMO p. 14. |
| D20 | `post_board` and `policy_basis` as in the other protocols, with the NCG statement added to `policy_basis` | Task instruction; owner, 17 Oct 2026. |
| D21 | Version "0.1-draft", DRAFT wording in `note`, the `approval` block | Owner decision 17 Oct 2026: needs a named doctor's approval before real use. |
| D22 | Left out on purpose: brain MRI before localised treatment (ESMO p. 11, a treatment-planning step), CEA / CA19-9 / CA72-4 / CA15-3 / chromogranin A (ESMO only; NICE 1.2.2.1 says not during diagnosis), ER / PR / HER2 on the axillary node specimen, p16 / HPV / EBV testing, BRCA testing, the ESMO favourable-subtype algorithms | Site-specific follow-ons: once the doctor records the primary (or a site-like subtype) the existing referral moves the Case File to that site's checklist and the CUP check stays as read-only history (owner R05-Q08). The algorithms classify patients, which the AI must not do. |

The project rule that the AI never judges a condition is kept everywhere: no record turns on from a reader output; the only inputs are the setting the doctor records, the documents filed, and (once built) the doctor's yes / no answer.

## 4. Doctor-settled records: what `applies_if` means, today and later

| Record | Question asked of the treating doctor | Sex | Today (`rules.py` V2) | When R07-Q10 / R07-Q06 are built |
|---|---|---|---|---|
| `pet_ct` | Has the primary not been found after the initial tests, and does a treatment decision depend on the PET-CT result (radical or local treatment considered)? | any | shown, not counted (tier c, condition) | yes: Essential (a); no: not applicable with the reason; unanswered: shown |
| `mammography` | Are clinical or pathological features compatible with breast cancer? | female | shown, not counted | yes: a; no: not applicable; a male registration: not applicable without asking |
| `mri_breast` | Adenocarcinoma involving the axillary nodes, with no breast primary found on standard breast investigations? | any | shown, not counted | yes: Optimal (b), NICE "consider"; no: not applicable |
| `myeloma_screen` | Isolated or multiple lytic bone lesions on imaging? | any | shown, not counted | yes: a; no: not applicable |
| `gi_endoscopy` | Do the symptoms, histology or radiology suggest a GI primary? | any | shown, not counted | yes: a; no: not applicable |
| `bronchoscopy` | Intrapulmonary nodules unsuitable for percutaneous biopsy, or does the IHC or the clinical picture imply a lung primary? | any | shown, not counted | yes: a; no: not applicable |
| `ent_panendoscopy` | Cervical lymph node presentation with no primary found on examination and imaging? | any | shown, not counted | yes: a; no: not applicable |
| `psa` | Male patient with a presentation compatible with prostate cancer? | male | shown, not counted | yes: a; no: not applicable; a female registration: not applicable |
| `ca125` | Peritoneal malignancy, ascites or another presentation compatible with ovarian cancer? | female | shown, not counted | yes: a; no: not applicable; a male registration: not applicable |
| `afp_hcg` | Presentation compatible with a germ-cell tumour (midline, mediastinal or retroperitoneal disease, young man) or with hepatocellular cancer? | any | shown, not counted | yes: a; no: not applicable |
| `testicular_ultrasound` | Male patient with a presentation compatible with a germ-cell tumour? | male | shown, not counted | yes: a; no: not applicable; a female registration: not applicable |

Block format on each record: `{"question", "sex" (female / male / null), "yes" (tier when yes), "no" ("none" = not applicable with a reason), "unsettled" (tier while unanswered), "source"}`; `applies_if_note` at the top of the file says the same. Until the feature exists a doctor who wants one of these counted can only rely on the existing waiver the other way round (waive a required record); the owner's two actions ("not applicable" and "waive", R07-Q06) are not built.

Known wording limit, code side (not changed, no app-code change without a go): the gate labels every tier note "NCG" (`rules.py`: "NCG Optional: shown only", "NCG Essential for ...: shown, not counted; the system does not judge this condition", "NCG setting not recorded") and `tb.js` prints the same words; for this protocol the tier rests on NICE or ESMO, which `settings_note` and every `tier_basis` say. A later code change could print the guideline name from the record's source instead.

## 5. What a named doctor must approve before real use

| # | Point to approve | Where |
|---|---|---|
| A1 | The three settings and that the setting is recorded by the doctor, never derived | `settings`, `settings_note` |
| A2 | The eight Essential records of MUO (NICE's unconditional initial screen) and that an Indian hospital wants all of them (calcium, urinalysis and LDH included) | records with tier a |
| A3 | Biopsy / histology: Essential from provisional CUP and only Optimal in MUO (or Essential already in MUO, as NICE 1.2.1.1 lists it) | `histopathology.tiers` |
| A4 | The IHC record and its wording (NICE panel named; ESMO's GATA3 / SOX10 note), Essential from provisional CUP | `ihc_panel` |
| A5 | The specialist review record: what document counts (CUP team / oncology note, board record, slide review) and Essential only in confirmed CUP | `specialist_review`, its `region` |
| A6 | Each doctor-settled record's question, sex and the tier it takes when the answer is yes (section 4), and that until the question feature exists they are shown, never counted | `applies_if`, `condition` |
| A7 | NICE's rule over ESMO's for mammography and for tumour markers (owner R05-Q07); no CEA / CA19-9 / chromogranin record | `mammography`, `psa`, `ca125`, `afp_hcg`, `note` |
| A8 | Chest X-ray satisfied by a CT; CT satisfied by MRI or PET-CT; breast ultrasound satisfying mammography; a tumour marker panel satisfying AFP / hCG | notes on those records |
| A9 | Molecular profiling as Optional (shown only) | `molecular_profiling` |
| A10 | Desks and SLA days per record (2 to 10 days) | `department`, `sla_days` |
| A11 | NICE 1.3.1.1 (no further investigations for a patient unfit for treatment) is handled by the existing waiver with a reason; Vaidyx never judges fitness | not in the file (process) |
| A12 | The left-out items of D22 stay out until the primary is found and the Case File moves to the site checklist (R05-Q08) | section 3 |

## 6. Suggested additions elsewhere (not made: no existing file was edited)

### 6.1 `facts.json` fields that would turn record-level checks into value-level checks

| Fact id | Label | doc_types | Why |
|---|---|---|---|
| `ldh` | Lactate dehydrogenase | lab | NICE 1.2.1.1, 1.3.2.1; ESMO risk score (value shown, never scored) |
| `calcium` | Serum calcium | lab | NICE 1.2.1.1 |
| `albumin` | Serum albumin | lab | NICE 1.3.2.1 prognostic factor |
| `urinalysis` | Urinalysis result | lab | NICE 1.2.1.1 |
| `psa` | PSA | lab | NICE 1.2.1.1, 1.2.2.1 |
| `ca125` | CA 125 | lab | NICE 1.2.1.1, 1.2.2.1 |
| `afp` | AFP | lab | NICE 1.2.1.1, 1.2.2.1 |
| `hcg` | hCG (beta-hCG) | lab | NICE 1.2.1.1, 1.2.2.1 |
| `myeloma_screen` | Myeloma screen (SPEP / immunofixation / free light chains) as written | lab | NICE 1.2.1.1 |
| `ihc_panel` | IHC markers and results as written (CK7, CK20, TTF-1, PLAP, GATA3 ...) | ihc, histopathology | NICE 1.2.2.7, 1.2.2.8; ESMO p. 2 |

`his_codes.json` would then need the matching LOINC codes and `fact_by_label` patterns ("ldh|lactate dehydrogenase", "calcium", "\\bpsa\\b", "ca ?-?125", "\\bafp\\b", "hcg", "albumin").

### 6.2 `his_mock/scenarios.json` tests missing for a CUP demo patient

Present and reusable: `opd_note`, `referral_note`, `cbc`, `lft`, `rft`, `chest_xray`, `cect_chest_abdomen_pelvis` (or `cect_tap`), `hpe_biopsy`, `hpe_slide_review`, `ihc_panel`, `pet_ct`, `mammogram`, `usg_breast_axilla`, `colonoscopy`, `bronchoscopy`, `cea`. Missing: serum calcium, urinalysis, LDH, myeloma screen, PSA, CA 125, AFP and beta-hCG, testicular ultrasound, UGI endoscopy, ENT panendoscopy, MRI breast, a general molecular / NGS panel (`molecular_lung` exists), a CUP team review note (a `tumour_board_record` or `opd_note` can stand in). `his_mock/scenarios.py` line 55 (`PROTOCOLS`) lists the five protocols the mock hospital builds patients for; "cup" is added there when CUP demo patients are built (RUNLOG item "CUP protocol (draft, needs doctor approval) + demo patients to ~25 incl. CUP").

### 6.3 `specialty_packs.json`: the suggested CUP entry (synthetic specialty note)

No Indian or international CUP reporting checklist is on disk, so no `checklists.cup` entry can be written yet (the validator in `packs.py` needs a file in a known guideline folder with page and quote per item). What should be added:

```json
"radiology": {
  "sources": [ ...existing..., {"folder": "esmo", "files": ["ESMO_2023_cancer_of_unknown_primary_Kramer.pdf"]} ],
  "checklist_note": "...existing text... CUP: none (no Indian or international CUP imaging reporting checklist is on disk; the ICRI / IRIA PET-CT chapter, pp. 186-188, covers the imaging protocol, not report content; the NICE CG104 and ESMO 2023 imaging lines are quoted on the Pre-Authorization records of protocols/cup.json)."
},
"pathology": {
  "checklist_note": "...existing text... CUP: none on disk; the candidate is the RCPath dataset for the histopathological reporting of cancer of unknown primary and malignancy of unknown primary origin (download in a browser into rcpath/ first); the NICE CG104 1.2.2.7 antibody panel is quoted on the ihc_panel record of protocols/cup.json."
},
"nuclear_medicine": {
  "sources": [ ...existing..., {"folder": "esmo", "files": ["ESMO_2023_cancer_of_unknown_primary_Kramer.pdf"]} ],
  "checklist_note": "...existing text... CUP: none; the NICE CG104 1.2.2.5 / 1.2.2.6 and ESMO 2023 PET-CT statements are quoted on the pet_ct record of protocols/cup.json."
}
```

Rules kept: an international folder (`esmo`) is appended after the existing international sources, so `packs._validate` ("Indian source listed after international source") still passes; `files` restricts the folder to the one CUP paper for the imaging agents, while `medical_oncology`, `surgical_oncology` and `radiation_oncology` already list `esmo` and `nice` without a file filter and need no change. Two follow-ups for the agents to find the text: the guideline search index must be rebuilt to include the ESMO CUP PDF (noted in `_reading_lists/MANIFEST` on 17 Oct), and `guidelines.CANCER_WORDS` has no "cup" entry (a missing entry only loses the 1.25 title boost; `CANCER_WORDS.get` never fails). The NICE CG104 PDF ("Download guidance (PDF)" on the NICE page) could be placed in `nice/` so the medical oncology agent can quote it too.

### 6.4 One unit test to update when the protocol is accepted

`tumour_board/tests/test_routes.py` line 9 hard-codes `PROTOCOLS = ("breast", "cervix", "colorectal_rectum", "lung_nsclc", "oral_cavity")`; `test_routes_table_lists_every_record` compares `rules.routes_table()` (every shipped protocol) with that tuple, so it fails by 27 rows (23 records + 4 optional) while `cup.json` is in the folder. Adding `"cup"` to the tuple makes all 31 tests of that file pass (checked on a copy of the file; the test file itself was not edited). `test_tiers.PIDS` should **not** simply gain "cup": those tests require every source to start with "NCG" and a research note under `docs_Eswar/research/`; a CUP-specific test (sources start with "NICE" or "ESMO", quotes verified against the NICE page text and the ESMO PDF pages) would be the equivalent, and the checks in section 7 are its draft.

## 7. Validation run (18 Oct 2026)

| Check | Command | Result |
|---|---|---|
| Baseline before `cup.json` existed | `/data/vaidyx/venv/app/bin/python -I -m pytest tumour_board/tests -q` and `... his_mock/tests -q` | 2349 passed (24 s); 264 passed (58 s) |
| Full unit suite with `cup.json` in place | same | 2348 passed, 1 failed: `test_routes.py::test_routes_table_lists_every_record` (section 6.4); his_mock 264 passed |
| The failing test with "cup" in its tuple | copy of `test_routes.py` with `"cup"` added, run with the repo conftest as plugin | 31 passed |
| Structure, as `test_tiers.test_every_record_has_tier_source_and_valid_fields` checks a protocol | script in the session scratchpad (not in the repo): tiers in a / b / c / none against the settings, unique ids, source or sources on every record, page int or "n/a" with where, required facts in `facts.json`, doc types in the catalogue, every `department` resolved by `org.department_id`, `condition` only on a record that is Optional somewhere, `applies_if` only with tier c and a condition, every `region` compiles as the gate uses it, no em or en dash, no name of the licensed US guideline network (the check `test_protocols.py` makes on every protocol file) | OK (23 records, 4 optional) |
| Verbatim quotes | NICE: each quote found in the curl copy of the Recommendations page (whitespace-normalised); ESMO: each quote found in the pypdf text of the cited PDF page (whitespace-normalised, as `test_phase9_review` checks the oral cavity quotes) | 43 NICE quotes and 29 ESMO quotes verified |
| Quick load, as the codebase does | `/data/vaidyx/venv/app/bin/python -I -c "import sys; sys.path.insert(0, '.'); from tumour_board import protocol; p = protocol.get('cup'); print(p['label'], p['version'], p['approval']); print([x['id'] for x in protocol.list_protocols()]); print(protocol.facts_for_doc('cup', 'lab'))"` from the repo root | `Cancer of Unknown Primary (CUP) 0.1-draft {'status': 'draft', ...}`; `['breast', 'cervix', 'colorectal_rectum', 'cup', 'lung_nsclc', 'oral_cavity']`; `['haemoglobin', 'wbc', 'platelets', 'creatinine', 'bilirubin', 'cea']` |
| Gate smoke test on a synthetic Case File (temporary data root, `tumour_board.tests.util` documents, SYNTHETIC patient) | `rules.evaluate` under each setting | MUO with no documents: 8 required, all `missing_record`, 15 shown; MUO with the initial screen filed: passed, readiness 100; switched to provisional CUP: `histopathology` and `ihc_panel` open; with a histopathology and an IHC report: passed; switched to confirmed CUP: `specialist_review` opened only once the review tier applied, passed with a "CUP TEAM REVIEW OF INVESTIGATIONS" board record; `sync_actions` and `rules.routes_table` (27 CUP rows) run without error |

To repeat the quote check later: `curl -sL -A "Mozilla/5.0" https://www.nice.org.uk/guidance/cg104/chapter/Recommendations` into a file, strip the HTML to text, normalise whitespace, and assert each NICE `quote` is a substring; for ESMO read the PDF with `pypdf.PdfReader(...).pages[page - 1].extract_text()`, normalise whitespace and assert the same.

## 8. Files

| Path | What |
|---|---|
| `/home/bharath.tangella/vaidyx/Vaidyx/tumour_board/protocols/cup.json` | the checklist (new; 23 records, 4 optional, 3 settings, 72 verbatim quotes) |
| `/home/bharath.tangella/vaidyx/Vaidyx/tumour_board/protocols/README_cup.md` | this note (new) |
| `/data/vaidyx/tb_resources/guidelines/esmo/ESMO_2023_cancer_of_unknown_primary_Kramer.pdf` | ESMO source (placed by the owner on 17 Oct 2026) |
| https://www.nice.org.uk/guidance/cg104/chapter/Recommendations | NICE source (web page; PDF not on disk) |

No existing file was edited; nothing was committed.
