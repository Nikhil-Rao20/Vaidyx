# New Case File: find a patient by name or words, a manual fallback, AI pre-fill; Choose your hospital system

Branch `after-healthathon` only (worktree `~/vaidyx/Vaidyx-after-healthathon`). Asked by Bharath, 17 Nov 2026. Nothing deployed,
`main`, or a server other than :7400 / :5180 changes. Guest reviewers (`real_data`) keep today's "Case label" flow exactly.

## What doctors said

| Ask | From |
|---|---|
| Doctors remember the patient's name (often shortened, misspelt), not the UHID. Search by name, show a short list, pick one | Bharath |
| Also search by words: "breast cancer", "chemotherapy", any word from a report or summary | Bharath |
| Thousands of patients: a drop-down list of the best matches, not a page | Bharath |
| The hospital system lookup stays the main way. A Case File made by hand is only the backup | Bharath |
| After the lookup, the AI fills the questions from the records; the doctor checks, edits, continues | Doctor review, Bharath agreed |
| Build the "Choose your hospital system" screen planned on 12 Nov | Bharath |

## Decisions

| # | Decision | Why |
|---|---|---|
| N1 | **One box, two ways.** Typing a number (UHID, IP / OP No., ABHA) and pressing Look up works exactly as today. Typing 2+ letters opens a drop-down (after 250 ms) of the 8 best matches: name, age / sex, UHID, last visit (department, date), "Has a Case File" badge, and for a word match the matched words in context. Arrow keys, Enter, click. Picking one runs today's lookup with that UHID | The lookup a doctor knows stays; the name search only gets them to the UHID faster |
| N2 | **Where matches come from.** (a) The hospital system, live: FHIR `Patient?name=` for each word (any FHIR system answers this). (b) A per-hospital **patient index** built from the hospital system in the background: registrations, visits (department, doctor, date), report titles and **report text** (PDF text, last 24 months, capped), refreshed every 10 minutes and only for what changed (`_lastUpdated`). (c) This hospital's Case Files (cancer, department, status) | (a) works on any system without an index; (b) is what makes typos and words like "chemotherapy" findable; (c) shows a Case File already exists |
| N3 | **Matching built for Indian names.** Lower case, titles dropped (Mr, Mrs, Smt, Sri, Dr, Baby, Master), Indian spelling folded (aa/a, ee/i, oo/u, th/t, dh/d, bh/b, sh/s, ph/f, w/v, double letters), initials ("P Venkatesan", "Priya V"), one or two typing mistakes (rapidfuzz), words in any order. Words: every word must match; oncology short forms (ca, carcinoma, chemo, NACT, RT, IDC, mets, FNAC, HPE, CECT, PET) | Spelling of one name varies (Lakshmi / Laxmi, Venkatesan / Venkatesen) |
| N4 | **Who may search, what is shown.** Same rule as the lookup: `create_case`; a guest reviewer is refused. At most 8 rows, never report text beyond a 120-character snippet around the matched words; snippets from a Case File only if the doctor may read that Case File. Every search is audited (`patient_find`: the words up to 60 characters, how many results), like `his_lookup`. Index files are per hospital (`<DATA_ROOT>/patient_index/`, mode 600) | A name search shows more people than a UHID lookup: keep the same gate, keep it short, keep a record |
| N5 | **Manual fallback for hospital doctors.** Under the box: "Not in the hospital system? Make it by hand". It is shown small always and as the main next step when the hospital system cannot be reached or nothing is found. The form: patient name, hospital number if known, age, sex. The Case File is not linked to the hospital system; reports are added in Records. Today's `POST /cases`; the one-Case-File-per-patient-and-cancer check still runs on the number | The hospital system is the main way; doctors are never stuck when it is down |
| N6 | **AI pre-fill after the lookup.** When the lookup finds the patient, the server reads that patient's reports in the window (text of the newest 12, capped) and asks the reasoning model for: the cancer (name, and the checklist if one is built), the colon / rectum or adult / child variant, the NCG setting **as recorded**, a draft board question, an urgency suggestion with its reason. **Each value carries a quote that is checked word for word against the report text; a value whose quote is not found is dropped.** The doctor's screen fills only the fields the doctor has not touched, each with "Filled by AI from <report>, check" and the quote; "Clear AI suggestions" undoes all. **Urgency is suggested, never pre-selected** (owner rule: the consultant's own call), one tap to use it. The owning department is chosen from the visits that match the doctor's own departments (no model). Nothing is created until Create; if the model is down, nothing is filled and a quiet line says so | Saves the doctor typing; every value shows its proof (project rule); nothing is decided for the doctor |
| N7 | **Choose your hospital system** (Hospital console > Hospital system; the admin set-up's step links to it). (1) Pick from the presets (`GET /his/kinds`) with their honest labels ("tested with the demo hospital", "by standard, not tested with the product", "no public API found") or "My system is not listed". (2) Fill only the fields that kind needs; secrets shown as set / not set. (3) **Test** without saving (new `POST /his/try`): connection, counts, and optionally one UHID: patient, visits, reports. (4) **Use this system** is enabled only after a passing test of the same values; saves through today's `POST /setup/his`. Changing the system of a hospital with Case Files warns that those Case Files keep their old link | A wrong saved connection would stop every doctor's lookup |
| N8 | **Additive only.** New routes `GET /his/find`, `POST /his/prefill` (and `GET /his/prefill/{job}` if it runs as a job), `POST /his/try`. Today's routes keep their answers. New code in new files; existing files get small hooks | Nothing else may break |

## Pieces

| Id | What | Files (new unless said) |
|---|---|---|
| NC-A | Patient finder: index, matching, `GET /his/find`, drop-down, manual fallback for hospital doctors | `tumour_board/patient_finder.py`, route in `routes/tumour_board_routes.py`, `web/tb-nik/src/features/newcase/PatientFinder.tsx`, `StepStaffManual.tsx`, edits in `StepPatient.tsx`, `NewCaseFile.tsx`, `form.ts`, tests |
| NC-B | AI pre-fill | `tumour_board/case_prefill.py`, route, `web/tb-nik/src/features/newcase/usePrefill.ts`, `AiFilled.tsx`, small edits in `StepCancer.tsx`, `StepLogistics.tsx`, `NewCaseFile.tsx`, `form.ts`, tests |
| NC-C | Choose your hospital system | `POST /his/try` in `tumour_board/api/setup.py`, `web/tb-nik/src/features/consoles/hospital/HisChooser.tsx`, edit in `HospitalSystem.tsx`, tests |
| NC-D | Wire on :7400, review, full gate, rebuild `static/tb-nik`, commit, report | orchestrator |

## After the review (17 Nov)

| # | Change | Why |
|---|---|---|
| R1 | The Vaidyx admin gets "no" from name search, the lookup and the AI pre-fill | Admin consoles rule D5: no patient data without break-glass |
| R2 | A Case File the doctor may not open shows only "A Case File exists (department)"; a Case File made by hand is found by name only by those who may open it | The same facts as the duplicate check, nothing more |
| R3 | Limits per login: 120 searches, 30 pre-fills, 20 hospital system tests in 10 minutes | A search box must not become a way to list every patient |
| R4 | A pre-fill value is kept only if its quote really says it: the cancer quote names the cancer and its site, the setting quote holds that setting's words, the urgency quote is a finding, not a heading; quotes are at least 15 characters and 3 words. The AI fills only empty fields | A word-for-word quote is not enough if it says something else |
| R5 | The hospital system test shows counts only: found, visits, reports, date of the newest report. No name | Hospital admins do not need patient data (Bharath, 17 Nov) |
| R6 | The index is read and written off the request path, kept in memory, at most 20,000 report texts per hospital; an index of the previous hospital system is never used | Speed, and no wrong patient after a change of system |

## How to try (test copy :5180 / :7400)

| Who | Do this | You should see |
|---|---|---|
| `tb-breast-doc` | New Case File, type `venkatesen`, `laxmi`, `4219`, `chemo` or `breast cancer` | A list of matches; picking one runs the lookup |
| `tb-breast-doc` | Pick a patient, Continue | Step 2 filled by AI with "Filled by AI ... Show the quote"; Clear AI suggestions undoes it |
| `tb-breast-doc` | "Not in the hospital system? Make it by hand" | Name, hospital number, age, sex; reports added in Records after Create |
| `tb-root` | Hospital console, Hospital system, Change hospital system | Pick, Details, Test (try one UHID), Use this system only after a passing test |

On this test copy every synthetic patient already has a Case File for their cancer, so Create stays off (one Case File per patient and cancer); the pre-fill still shows on step 2.
