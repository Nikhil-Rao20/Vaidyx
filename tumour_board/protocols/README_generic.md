# Cancer with no checklist yet: `generic.json`

Status: **version 0.1, the owner's minimum set, not a clinical guideline.** It must be reviewed by the hospital Tumour Board before real use. A disease-specific checklist replaces it for a cancer as soon as one is built.

## 1. What it is for

A treating doctor starts a Case File for a cancer that has no built checklist: a cancer typed by hand ("The cancer is not listed: type its name"), or one of the NCRP top-10 cancers whose checklist is not built yet (prostate, stomach, ovary, thyroid, leukaemia and the others marked "no checklist yet" in `web/tb-nik/src/lib/cancers.ts`). Such a Case File is created under protocol `generic` and keeps the cancer's name as the doctor wrote it.

Owner decision R05-Q04 (question round R05, Manual entry, answered 17 Oct 2026), the chosen option quoted on every record:

> Histopathology, staging imaging, a clinical note with performance status, and a typed question for the board; labelled 'No disease-specific Indian protocol'.

Cancer of Unknown Primary is not generic: it keeps its own draft checklist (`cup.json`).

## 2. The four core records

| Record id | Label | Counts when | Required value | Responsible Department |
|---|---|---|---|---|
| `histopathology` | Histopathology or cytology report | a final, signed histopathology or cytology report | none | Pathology |
| `staging_imaging` | Staging imaging report (CT, MRI or PET-CT, any one) | any one final, signed CT, MRI or PET-CT report, any region | none | Radiology (the root admin can route it to Nuclear Medicine) |
| `clinical_history` | Clinical note with performance status | a final, signed clinical note or referral | ECOG performance status (may be typed by the treating doctor) | the owning treating department (route `owner`; Medical Oncology before an owner is recorded) |
| `board_question` | Question for the board | the question typed by the treating doctor, or written in a final, signed clinical note or referral | Question for the Tumour Board (`clinical_question`, typable) | the owning treating department (route `owner`) |

All four are tier `a` (required everywhere); there is one setting, `as_recorded` ("As recorded by the doctor"), so nothing depends on the extent of disease and nothing computes a stage. Optional, shown when present: a treatment summary of earlier treatment, a previous Tumour Board record. The extraction list and the MDT core data are site-neutral (presenting complaint, performance status, comorbidities, histologic type, grade, stage as recorded, nodal and distant findings, baseline blood counts and chemistry, treatment received, patient preference, clinical trial note, date and mode of diagnosis).

## 3. Decisions

| Decision | Reason |
|---|---|
| Sources are the owner decision, not a guideline (`"guideline": "Owner decision R05-Q04, 17 Oct 2026"`, `"page": "n/a"`, `"where"` names the question) | No guideline is claimed; the file never mentions NCG. The note says it is not a clinical guideline and must be reviewed by the hospital. |
| Histopathology and staging imaging carry no required value | The owner named records, not values; what the board needs from them depends on the cancer, which only the treating team can judge. Histologic type is still extracted and shown. |
| Staging imaging: CT, MRI or PET-CT, any one, any region | "Staging imaging" without a site; the system does not judge whether the work-up is complete. |
| The board question is a values-only record carried by a clinical note or referral | `rules.py` counts a typed value (verification `entered_by_doctor`, no quote) for a required field; a values-only record still needs a final document that could carry it, which is the clinical note the third record requires anyway. With the note filed and the question typed, all four are met. |
| Record id `clinical_history` for the clinical note | The id every protocol uses for the owner's clinical record (routing, the surgical seat in `board.py`, the routes test). |
| The cancer's name lives on the Case File (`case.json` `cancer_name`, 2 to 80 characters, trimmed), not in the protocol | One protocol serves every unlisted cancer; the name is required under `generic`, optional under a built checklist, accepted by `POST /cases/from-his` and `POST /cases`, and audited (`case_created`). |
| Lists read "<cancer name> (no checklist yet)" | `GET /case-list` uses `protocol.case_label`; the organ filter keeps one "Other cancer" entry for all of them. |
| Two generic Case Files of one UHID are "the same cancer" only when the typed names agree | `his_case.create` marks `same_uhid_case` by protocol; under `generic` the name decides (case-insensitive). |

## 4. Known limits

- A question typed before any clinical note is filed: the gate counts the question as met (its value is there), while the fill-in summary line of the record still asks for the carrying clinical note. The gate cannot pass in that state anyway, because the clinical note record is open. Letting a typed value settle a values-only record on its own would be a small change in `rules._evaluate_record` (not made here).
- `POST /cases/{id}/listing` (the coordinator's listing, and a new owner after a referral) takes no cancer name: a Case File listed under `generic` that way is named "Other cancer (no disease-specific Indian protocol)" until a name is recorded.
- The Level 1 gap sentence lower-cases the record label ("No staging imaging report (ct, mri or pet-ct, any one) in the Case File"), as it does for every protocol.

## 5. Files

- `tumour_board/protocols/generic.json`: the protocol.
- `tumour_board/protocol.py`: `GENERIC`, `case_label()`.
- `tumour_board/his_case.py`: `clean_cancer_name()`, `cancer_name` on `create()`, the same-cancer check.
- `routes/tumour_board_routes.py`: `cancer_name` on `POST /cases/from-his` and `POST /cases`.
- `tumour_board/api/cases_list.py`: the list label and the organ filter.
- `web/tb-nik/src/lib/cancers.ts`, `web/tb-nik/src/features/newcase/*`, `HeaderStrip.tsx`: the New Case File flow and the Case File header.
- `tumour_board/tests/test_generic_protocol.py`: the tests.
