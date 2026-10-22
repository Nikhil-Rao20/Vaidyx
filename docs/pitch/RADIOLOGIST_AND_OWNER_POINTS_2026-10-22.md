# Pitch points from the radiologist and the owner (22 Oct 2026)

For the website and the deck for the final-round submission. Points 1 and 2 are the source wording, lightly cleaned; section 3 is what the
owner asked for on the product; section 4 is the demo; section 5 is an open scope question that must be settled before anything in it is
built or claimed.

## 1. From the radiologist (TANUH adviser)

| # | Point | What it means for the story |
|---|---|---|
| 1 | Vendor-agnostic: it can be integrated with any existing PACS. | Lead message: Vaidyx connects to the hospital's own PACS and HIS; no new imaging system. |
| 2 | Built to reduce errors in cancer staging: stage 2 may mean surgery and stage 2B chemotherapy, so the stage must be right. | Why accuracy of the staging inputs matters; one wrong value changes the treatment path. |
| 3 | A decision cannot be taken by one doctor; that is why a set of people meets. | What a tumour board is, and why the preparation matters. |
| 4 | Rare diseases also need handling; AI support for doctors helps most there. | Rare and complex cases: long discussions, little local experience. |
| 5 | The specialty agent (it stands in for an absent specialist) answers questions on the report from the evidence in the report and the guidelines; it does not read or diagnose the scan. | Specialty support, records and guidelines only; images are for people. |
| 6 | Use the words precision medicine, oncology, oncologist. | Vocabulary for the website and the deck. |
| 7 | Demonstrate which guidelines Vaidyx holds and what knowledge it has. | A "library" view: the guideline sources, by body and cancer. |
| 8 | For a breast cancer case the agent would tell the stage from the guidelines, with proof (not built). | See section 5: outside today's signed scope. |
| 9 | Show realistic examples. | Synthetic but realistic Case Files, end to end. |
| 10 | TNM and "Flreshner" guidelines: take one cancer from each and show the demo. | Read as AJCC / UICC TNM staging and the Fleischner Society guidelines for pulmonary nodules (to confirm with the owner). |

## 2. From the owner

- **Main message when presenting:** Vaidyx is integrated into the hospital's own PACS and HIS (HIMS) and is PACS-agnostic. The website
  must show this clearly and cleanly.
- **Why a tumour board:** a single doctor cannot decide what to do, so a group of doctors meets, discusses and comes to one decision. Even a
  small error in that decision puts the patient's cancer treatment at risk. Vaidyx eases the preparation and the discussion and offers
  support.
- **Rare diseases:** when a hospital gets a rare case the discussion goes on and on. AI support helps in many such scenarios; say so.
- **Demo:** one case for each guideline family (TNM, Fleischner), built properly.

## 3. Product asks from the owner (Case File, Extent group)

1. **Staging shown properly, neat and big** in the Extent group of the Overview, not as one line among many.
2. **Stage history:** if the patient has a history, the stages recorded before and the stage now, with dates and reports.
3. **Which guidelines were looked at** for it.
4. **The books attached:** each staging statement carries its book; clicking it opens the PDF in a scrollable viewer at the referenced page,
   with the paragraph highlighted.

## 4. Demo plan (to build when the owner says)

| Guideline family | Cancer | What we hold today | Gap |
|---|---|---|---|
| TNM (AJCC 8th edition) | Breast (also possible: lung, cervix, colorectal, oral cavity) | AJCC 8 chapters 48 (breast), 36 (lung), 52 (cervix), 20 (colon and rectum), 7 (lip and oral cavity), chapter 1 (general rules); full AJCC 8 manual (licensed copy); NCG India breast 2019; ICMR breast; CAP breast protocols; ASCO/CAP HER2 2023 | UICC TNM 9 not held |
| Fleischner Society | Lung nodule (incidental pulmonary nodule) | ACR Appropriateness: incidentally detected indeterminate pulmonary nodule; Lung-RADS v2022; ICMR lung 2020; CAP lung | The Fleischner Society 2017 guideline paper (MacMahon et al., Radiology 2017) is not in the library yet |

Both demo patients are synthetic (Vaidyx Demo Hospital), with reports in the demo HIS and images from open, de-identified datasets in the
demo PACS, as for every demo Case File.

## 5. Open scope question (owner to decide; nothing built or claimed until then)

The signed scope declaration and the project rules say Vaidyx checks, routes, summarises and flags, and never interprets images, diagnoses,
**computes a stage** or advises treatment. Points 8 and 10 and section 3 touch this line:

| Option | What Vaidyx would do | Within today's scope? |
|---|---|---|
| A | Show the stage **as written in the reports**, big, with its history; beside it the guideline's staging criteria as verbatim quotes with the book page highlighted; the board reads both | Yes |
| B | Also map each recorded value (size, nodes, metastasis) to its TNM category and propose a stage group, labelled a draft for the board, each step quoting the AJCC page; a doctor confirms | No: it is stage computation; needs the owner's explicit change of scope, a clinician sign-off and updates to the scope declaration and MEDICAL_AI_DECISIONS.md |
| C | For a pulmonary nodule, quote the Fleischner recommendation that matches the recorded size and type, with its page | Quoting is in scope; applying it to this patient as a follow-up plan is treatment advice (same question as B) |

Until the owner decides, the website and the deck say "stage as recorded, with the guideline criteria beside it", never "Vaidyx stages the
cancer".
