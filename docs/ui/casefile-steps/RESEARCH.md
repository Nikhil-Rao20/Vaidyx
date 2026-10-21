# Case File, step by step: research (21 Oct 2026)

Why: the owner finds the Case File page too confusing for doctors and wants a step-by-step experience with an internal navigation bar,
plain action words ("Send request to Pathology department"), a "checked" tag on every document, and an AI Pre-Authorization check that
shows what is missing: fill it yourself, or send a request to the department it belongs to.

Three strands: (A) how a tumour board case is prepared, including India; (B) step-by-step interface evidence for clinicians;
(C) how the code works today. Earlier page research (17 Oct) is the basis of today's "fill-in summary" page.

## Today's page, measured (read-only, tb-breast-doc, 1366 x 768)

| Measure | TB-DEMO-P18A | TB-2026-0001 | TB-2026-0003 |
|---|---|---|---|
| Buttons and links | 61 | 91 | 85 |
| Words | 666 | 1,154 | 1,151 |
| Page height | 2,179 px | 2,518 px | 2,830 px (3.7 screens) |
| Controls in the first screen | 15 | 28 | 28 |

Contradictions seen: "ready for the board" next to "Still open: 3 required" (TB-2026-0003); Cervix cancer chosen while every record is a
breast record, with no warning; "Not in the file" for a mammography report that is in the list (it is preliminary); "Mark ready" active
while the header says "2 items left"; conflicting values shown as raw quote dumps.

## (C) How the code works today (file references are to tumour_board/ and web/tb-nik/src/features/casefile/)

- Checklist per cancer in `protocols/*.json`: items with tier (a Essential, b Optimal, c Optional, per setting), owning department,
  document types or values only, required facts. Breast: 14 records + 2 optional; 4 to 10 count, by setting and hospital level.
- Every document is processed automatically: read (text layer or two scan reads + OCR), type (model + title check), final / signed
  (text + HIS overlay, stricter wins), patient match, values extracted, each value's quote checked word for word
  (`grounding.verify`: verified / needs review / unverified). **No per-document "checked" flag is stored or shown.**
- An honest "Checked by Vaidyx" tag = state ready, extracted under the current cancer's checklist, not superseded; it means read, type
  and status found, patient matched, every value's quote found in the text. It is not a person's review; for scans it is checked
  against the model's reading of the image.
- Slot statuses: found, not_found, waiting, needs_confirmation, entered, not_needed, pending_ready. A doctor may type only ECOG,
  menopausal status, weight, height and the board question; typed values count for the gate but never enter the summary.
- **Bugs that hurt trust:** the server lets a Case File be marked ready with items open (`board.mark_ready` does not check the gate);
  the ready mark is never removed when the check stops being met (owner's R07-Q12 says remove it); "final, signed" is shown for a draft
  when the HIS signature flag is set; an "Ask {department}" button can name a different department than the one that gets the
  request; "items left" is computed in four places that disagree (`slots.py`, `cases_list.py`, `meetings.py`, `SummaryColumn.tsx`).

## (A) Preparing one case for the board: what the evidence says

- **Workflow** (IHE XTB-WD; NHS England 2020; Greater Manchester; Victoria): triage (for discussion / for noting) -> refer with a
  proforma and a question -> collate records and chase gaps -> radiology and pathology pre-review -> agenda (at least 48 h before)
  -> present around a clear question -> record the decision live -> communicate and track. The referring clinician owns accuracy;
  coordinators check completeness; most preparation time is spent by nurse navigators (48 %) and residents (42 %) (Missouri).
- **The question first:** in most observed discussions the presenter gave no clear question (CRUK 2017, 624 discussions); the question
  was visible in 64 % of records (Victoria audit, 1,862 patients). NCG virtual tumour boards use a template with "specific questions".
- **Why cases fail:** missing radiology (77) and pathology (51) were the top barriers to a decision (Lamb 2013, 1,421 patients;
  a checklist + training raised decisions from 82.2 % to 92.7 %); 7 % + 11 % deferred (CRUK); 24 % deferred in UK lung MDTs, 14 %
  awaiting results (Zasada 2023).
- **Non-tumour facts are missing most and drive non-implementation:** ECOG recorded in 39 %, comorbidity 61 %, patient preference
  6 % (Victoria); decisions not implemented because of comorbidity 43.9 % and patient choice 34.2 % (Blazeby 2006).
- **Minimum dataset** (NHS England 2020): diagnosis date and mode, stage and its investigations, performance status, histology or
  cytology, comorbidities, trial suitability, genomic tests, patient preference, MDT recommendation, tumour-specific tests.
  Victoria splits it into "prefilled before the meeting" and "recorded at the meeting".
- **Override with a reason:** the GM proforma asks "Mandatory data set completed?" and "If being discussed without minimum dataset,
  reason / question for MDT".
- **Products:** NAVIFY (prepare ahead, reschedule when information is missing, timeline), Philips, Siemens AI-Pathway Companion
  ("quality checks on data completeness"), OncoLens (required minimal documentation, ask pathology or radiology a question ahead),
  GE CareIntellect (AI summaries linked to the source). No vendor shows an explicit "ready to present" checklist screen.
  Digital preparation cut preparation time 45 % (UCLA) and 64 % (Missouri, vendor co-authored).
- **India:** Tata Memorial runs 11 Disease Management Groups; patients carry outside reports, imaging and slides or blocks. KIMS
  Bhubaneswar: one weekly all-site board, 800 cases a year, Excel case lists; 20 % of staging data missing. ICMR-NCDIR survey:
  79.7 % of 172 hospitals have a functional board; 48.2 % have no follow-up mechanism. NCG virtual tumour boards: deidentified
  template emailed before the session. PM-JAY: cancer treatment needs plan approval "similar to a tumour board concept" and a signed
  Oncology Treatment Plan Approval form (Annexure 1); Gujarat requires a three-oncologist tumour board certificate. OPD loads of 35
  to 50+ patients a day: every step must be quick.

## (B) Step-by-step interfaces for doctors: what the evidence says

- **Not a locked wizard.** NN/g: wizards suit novices and infrequent tasks and "are not gracefully interruptible". Doctors are
  interrupted, wait days on other departments and do this weekly.
- **A task-list hub** (GOV.UK "complete multiple tasks"; NHS task list): for work over several sittings in an order the user chooses;
  whole row clickable; few status words (Completed, Incomplete, In progress, Cannot start yet, There is a problem); red only for a
  problem; completed items quiet, unfinished items loud; "Continue" beats "Start" for returning users; new tasks at the top, never
  silently appended (Civil Money Claims: a user read "completed" as "filed" and got a court judgment).
- **Epic Navigator**, the pattern doctors already know: a left table of contents for admission or discharge, sections in a fixed
  sensible order, "Mark as Reviewed" buttons, a green check when a section is complete (hospital tip sheets).
- **One next action:** a checklist alone did not reduce ICU mortality; active prompting cut it from 20.8 % to 10.0 % (Weiss 2011).
- **Resumption:** a blatant "you left off here" cue speeds resumption; a subtle cue is no better than none (Trafton 2005); 18.5 % of
  interrupted tasks were never resumed (Westbrook 2010). Save every action at once.
- **Checklist design** (Degani and Wiener, NASA): critical items first; the confirm response states the value, not just "checked";
  send work to outside agents early; buffers when outside work lags; the completion call is the last item; hard stops only for
  killer items.
- **Closed-loop requests** (ONC SAFER): acknowledgement with expected turnaround, track until closed, escalate unacknowledged.
- **Confirming AI values:** source beside the value, never behind a click (Microsoft Content Understanding; NISTIR 7804); one at a
  time with Enter to the next (Rossum); Confirm / Edit / Not in report (Google HITL); killer fields always reviewed whatever the
  confidence (Hyperscience); with wrong AI advice, experienced mammography readers fell from 82 % to 45.5 % (Dratsch 2023);
  omissions in LLM summaries matter as much as invented text.
- **End with a check page** (GOV.UK check answers) and a separate final commit worded unlike "section done"; explain what is missing
  instead of silently disabling the button (Microsoft wizard guidance).
- **Keep the big picture visible inside a step** (Endsley, situation awareness) and two patient identifiers on every screen
  (NISTIR 7804).

## Sources (selected; full lists in the session's research reports)

CRUK 2017 MDT report; NHS England MDT streamlining guidance 2020; GM Cancer MDT standards and toolkit 2023; Victoria MDM quality
framework 2018 and audit 2020; Lamb, J Am Coll Surg 2013; Zasada, Cancer Med 2023; Hahlweg, BMC Cancer 2017; Blazeby, Ann Oncol 2006;
Raine, BMJ Qual Saf 2014; RCR MDT standards; IHE XTB-WD; Nobori (UCLA), JCO CCI 2022; Missouri breast board, JONS 2019; NAVIFY brochure;
NCG virtual tumour boards, JCO Glob Oncol 2023; Saha (KIMS), APJCC 2024; ICMR-NCDIR survey 2026; TMH patient booklet 2025; NHA PM-JAY
FAQ; GOV.UK Design System (task list, complete multiple tasks, check answers, step by step) and design notes 2023; NHS service manual;
NN/g wizards and progressive disclosure; Carbon, Atlassian, Material 1, Microsoft wizard guidance; Baymard accordion checkout;
NISTIR 7804; AMIA task force 2013; ONC SAFER clinician communication; Degani and Wiener, NASA CR-177549; Weiss 2011; Westbrook 2010;
Trafton 2005; Haynes, NEJM 2009; Dratsch, Radiology 2023; Goddard, JAMIA 2012; Bucinca 2021; Microsoft Content Understanding blog;
Rossum, Hyperscience and Google Document AI HITL docs; Epic Navigator tip sheets (CHS Buffalo, SIU).
