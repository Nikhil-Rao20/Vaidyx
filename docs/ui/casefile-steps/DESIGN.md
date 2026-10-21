# Case File, step by step: design (owner's answers, 21 Oct 2026)

The Case File page today is one long page (61 to 91 controls, about 1,150 words, 3.7 screens) that doctors find confusing. It is
replaced by a guided Case File: a left list of six sections in working order, one loud "Continue" button, plain action words, and a
separate final "Send to the board". Research behind every choice: [RESEARCH.md](RESEARCH.md). The owner's answers are quoted as
B1 to B10 (batch, question bank of 21 Oct).

## 1. Shape (B1)

```
+------------------------------------------------------------------------------------------+
| Priya Venkatesan (SYNTHETIC) · 52 F · UHID VXH/26/004219 · OP/26/118725                  |
| Breast cancer, early · Dr Breast Surgery · Board Sat 25 Oct    [ Send to the board ] [More v]|
+------------------------+-----------------------------------------------------------------+
| [ Continue: check 2  > ]|  Overview                                                       |
|   values               |                                                                 |
|                        |  ...the section the doctor is in...                             |
| v Overview             |                                                                 |
| v Question             |                                                                 |
| v Reports       14     |                                                                 |
| * Check     2 to do    |                                                                 |
| o Pre-Authorization    |                                                                 |
|   Waiting on Pathology |                                                                 |
|   department           |                                                                 |
| o Summary  Not started |                                       ( Ask about this patient )|
+------------------------+-----------------------------------------------------------------+
```

- Left side list, like Epic's Navigator: six sections in working order, each a whole clickable row with a status.
- The Case File opens on **Overview** with a big **Continue: <next thing>** button on top of the list.
- **Guide, don't lock:** any section opens any time; only "Send to the board" waits until things are settled (or a reason is written).
- Each section is a sub-address (`/cases/:id/overview`, `/question`, `/reports`, `/check`, `/pre-authorization`, `/summary`), so
  Back and links work; the last section visited is remembered as "you left off here" (a loud marker on the list).
- The header keeps two patient identifiers on every section (name + UHID), the cancer, the owner and the board date.

Status words (B9): **Done** (quiet, grey tick) · **2 to do** (bold) · **Waiting on Pathology department** · **Overdue** (red) ·
**Not needed** · **Not started**. Red only for Overdue or a real problem.

## 2. Overview (B2)

1. **Warnings** at the top, each a plain sentence with its fix button (also shown in the section where it is fixed):
   - the cancer chosen does not match the reports ("The reports describe breast cancer; this Case File is set to Cervix cancer."
     [Change the cancer] [It is correct]);
   - a patient name or number that does not match;
   - a report that is only preliminary.
2. **To do (n)** and **Waiting (n)**: at most 5 rows each with "See all"; each row has its one action button (Check, Send request to
   Radiology department, Send reminder).
3. **Question for the board** (read here, written in the Question step).
4. **The patient at a glance**, every value opening its report line:
   - Diagnosis: histology, grade, receptors or biomarkers.
   - Extent: size, nodes, spread, stage only as written in a report (Vaidyx never works out a stage).
   - Fitness: ECOG, key labs, comorbidities.
   - Treatment so far and the patient's wishes.
5. No "how Vaidyx got this" trust line (owner: no line).

## 3. Question (B3)

- **Free text only:** the doctor writes the question; Vaidyx suggests nothing. The board question counts only when the doctor has
  written it.
- **Reason for discussion**, one tap: New diagnosis: plan first treatment · After surgery: plan next · Recurrence or progression ·
  Diagnosis not clear · Other.
- **Urgency 1 to 5** is set here (the header only shows it).
- Facts reports rarely carry, typed by the doctor and shown "entered by Dr X, no report": **patient's wishes**, **comorbidities**,
  **patient knows the diagnosis** (Yes / No / Partly).

## 4. Reports (B4)

- Grouped **by type** (Pathology, Imaging, Labs, Clinical notes, Outside reports), newest first; a switch shows them **by visit**.
- "Get new reports from the hospital" and "Upload outside report" at the top.
- Each row: title, date, **Checked by Vaidyx** (only the automatic tag, no doctor tick), **values read** ("6 values read", one click
  lists them with their lines), the amber **"Preliminary, not signed yet"** warning when not final, **Open images** for imaging.
- **Checked by Vaidyx** means: read, type found, final and signed found, patient matched, every value matches its report line word for
  word. It is the machine's check, not a person's review.
- When a document is not fully checked: amber **"Please check: 2 lines unclear"** (or "name does not match", "two values differ"),
  opening the document at those lines; it turns into "Checked by Vaidyx" once a doctor settles them.

## 5. Check (B5)

- **Problem values** (two reports differ, an unclear scan line, a preliminary-only value) one at a time, and the **key values** (for
  breast: histology, grade, ER, PR, HER2, Ki-67, stage as written) on one screen, each with its line and a one-tap Confirm.
- **Side by side:** the value and its button on the left ("Confirm HER2 1+"), the report on the right scrolled to the line with it
  highlighted; "Next: Ki-67".
- **Two reports differ:** both values with their report, date and final or preliminary status; the doctor picks; nothing is chosen for
  them; "Send request to Radiology department to clarify".
- **This is wrong:** two buttons, "Correct it" (the right value and a reason; shown "corrected by Dr X", the report line stays
  visible) and "Send request to the department to amend the report".

## 6. Pre-Authorization (B6)

The section is called **Pre-Authorization** (list and page): what the board still needs for this cancer and setting.

- Items grouped by the department that will really receive the request (the button names that department).
- Each item offers: **Send request to Pathology department** (main button) · **Fill it in myself** (only values a doctor may type) ·
  **Upload outside report** · **Not needed for this patient** (with a short reason).
- **One click sends** a ready-written request with a due date; "Change the message" beside it; several items for the same department
  go in one request.
- After sending: "Request sent to Pathology department, 21 Oct 15:40 · reply due 24 Oct" [Send reminder].
- **Overdue:** Vaidyx sends one reminder by itself on the due date and tells the doctor; the row turns "Overdue" with "Send reminder"
  and "Call the department" (number from the department contacts).
- Optional items the board may ask for are folded at the bottom.

## 7. Summary and Send to the board (B7, B8)

- The summary is written **before sending**: once nothing is open (or the doctor chooses), "Write the summary" (15 to 35 s, filling in
  as it writes), the doctor reads it, taps "I have read it", then "Send to the board". Specialty briefs and Similar published cases
  sit in this section.
- **Send to the board** is a short multi-step dialog: 1 meeting date (the next open meeting pre-filled) · 2 for discussion or for
  noting · 3 presenter (you or a resident on the team) · 4 note for the coordinator · confirm.
- **With items still open:** allowed only with a written reason why the board should discuss it anyway; the open items are listed for
  the board. The button never just greys out: it says what is open.
- **After sending, a report changes or a new one arrives:** the case stays on the agenda; Vaidyx updates the summary and the slides by
  itself and tells the **coordinator only** ("New IHC report received; summary and slides updated"). If the new report needs the
  doctor (it disagrees with an older one, or is only preliminary), the summary and slides show both values ("two reports differ"),
  the doctor gets a "Check 1 value" task and the coordinator sees "waiting on Dr X". Vaidyx never picks.
- The treating doctor can **move the case to another meeting** or **take it off the agenda** (with a reason) from the More menu and
  from the meeting chip in the Case Files list; the coordinator is told at once.

## 8. Roles, extras, Ask (B8, B9, B10)

- **Residents, PGs, fellows:** the same six sections; where a consultant must sign (confirm a key value, not needed, send to the board)
  the button becomes "Send to Dr Kavitha for sign-off"; the consultant's Overview shows "Sign-offs from your team (n)".
- **Board members and other departments:** Overview, Reports and Summary, read only, the Question at the top of the Overview.
  Supporting departments keep their request view.
- **More menu** in the header: Team, Board form, Print, Download (slides, PDF), Move to another meeting, Archive.
- **Ask about this patient:** a chat bubble at the bottom right on every section; the panel says answers come only from this patient's
  reports, each with the line it came from.

## 9. New Case File (B10)

The three-step create flow (Patient, Cancer, Logistics) gets the same look and, after Create and the fetch, lands on the new Overview
with "Continue: write the question for the board".

## 10. Trust fixes (B10: fix all, in the same work)

1. "Final, signed" shown for a draft when only the hospital-system signature flag is set.
2. An "Ask" button naming a different department than the one that receives the request.
3. "Items left" computed in four places that disagree: one server count, used by the Case File, the Case Files list and the meetings.
4. The server lets a Case File be sent with items open and no reason: the reason becomes required.
5. No per-document "checked" record: the server computes and sends it with each document.

## 11. Build order (piece by piece on :7000, one commit each as Nikhil-Rao20, screenshots after each, never pushed)

| Piece | What | Backend | Frontend |
|---|---|---|---|
| P0 | Research + this design | | docs |
| P1 | The shell: header, left list with statuses and Continue, section addresses, More menu, Ask bubble; Overview | one "left" count; per-document check status | new layout; Overview |
| P2 | Question | typed facts: patient's wishes, comorbidities, knows diagnosis; reason for discussion; question counts only when typed | Question section |
| P3 | Reports | per-document check (if not in P1); honest final / signed | Reports by type with Checked tags |
| P4 | Check | correction with reason; amend request | Check section, side by side |
| P5 | Pre-Authorization | grouped requests; real receiving department; automatic reminder on the due date; department phone | Pre-Authorization section |
| P6 | Summary and Send | send with meeting, list, presenter, note, reason; summary before sending | Summary section; Send dialog |
| P7 | After sending | auto update of summary and slides; coordinator told; both values flagged; doctor moves or withdraws | banners; More menu; list chip |
| P8 | Roles | sign-off for residents; read-only three sections for others | role views |
| P9 | New Case File + tests | | create flow restyle; e2e and screenshots for every role, laptop and phone |

Rules that hold throughout: every value shown as fact keeps its verbatim quote; no image interpretation, diagnosis, stage computation
or treatment advice; models labelled (Gemma-4-31B non-medical; Qwen3.5-4B Chinese, non-medical); no em dashes on screen; synthetic
cases only; the public demo and its frozen site are not touched.
