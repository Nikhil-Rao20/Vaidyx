# Vaidyx-TB after the night-v3 run: what the Tumour Board gets, before, during and after the board

Written at the end of the unattended run of 27 and 28 Oct 2026 (branch `night-v3`). How to try each part: [HOW_TO_TRY.md](HOW_TO_TRY.md).
The rules every feature keeps: the AI checks, routes, summarises, flags and drafts; doctors decide. No model reads an image, gives a
diagnosis, computes a stage beyond the labelled draft, or advises treatment. Every value or sentence shown as fact carries a verified
verbatim quote with its source line. Clinician confirmations beat model output and survive a re-process. Every action is audited.
Models are labelled: Gemma-4-31B (non-medical) writes and orders, Qwen3.5-4B (Chinese, non-medical) reads; no accuracy claim is made.

## Before the board

- **One Case File per patient and cancer.** A Case File starts from the hospital system's registration (UHID, IP / OP No., ABHA; never
  Aadhaar) or by hand; a second file for the same patient and cancer is refused with "Open it" or "Ask to join" (a code-less join
  request the owner's consultant approves). A patient look-up by number shows a placed doctor the patient's Case Files (id, cancer,
  owning department, consultant), audited by id.
- **Checklists for India's top cancers.** Twenty-four cancers with per-setting checklists built from the NCG and ICMR books (and
  EANO 2021 for brain and CNS), nineteen of them new in this run, every row with page-cited quotes, tiers as printed, dose references as flags only; the new ones are
  labelled "Draft checklist: needs a clinician's check". An unknown cancer gets a basic checklist; blood cancers a generic one
  without staging imaging. Thyroid waits for a licence decision.
- **Checks, gaps and flags.** Records arrive from the hospital system (FHIR, HL7, PDFs) or as outside reports; the reader extracts
  values, each one verified word for word against the page; the checklist marks found, missing and late items; two differing
  reports become a pick for a doctor (a resident's pick becomes a proposal); the Pre-Authorization row follows PM-JAY.
- **A draft stage, labelled.** For breast, lung and cervix the book's tables, fixed in code, give "Vaidyx draft stage, for the board
  to confirm" (anatomic, and for breast the prognostic group), counted only after a consultant confirms; anything unclear is
  "cannot stage"; a stage written in a report is shown and flagged, never overridden; confirmations survive a re-run (off by default
  outside the internal app).
- **The pre-board summary and the question for the board.** Every sentence cites a record line; "Send to the board" needs the
  board question (and a reason when items are open), updates the summary and the slides, tells only the MDT Coordinator; the doctor
  can move or withdraw the file.
- **Specialty agents' briefs.** Six roles (Radiology, Pathology, Medical, Surgical and Radiation Oncology, Nuclear Medicine) write
  a brief of points from the records, each point with its line, labelled with the model and "AI draft, not reviewed" until a doctor
  marks it reviewed; "Prepare all" writes the six at once; a shared question thread per role.
- **Ask about this patient, by voice.** Speech to text (Whisper large-v3-turbo on the server, fp16, audio never stored) fills the
  box the person edits and sends; answers come from the records with quotes and the model label; Read aloud (Kokoro on the server)
  reads them. Dictation works on the decision fields too.
- **Similar Case Files.** Past Case Files of this hospital that resemble this one, ordered by the reasoner (an order, never a
  score), each labelled "Past Case File, not advice for this patient", with quoted "Why similar" and "How it differs" lines, the
  stage, key values, the board's decision as written and the outcome so far from the past Case summary; the real case is never
  indexed. Opening a file of another department goes through the doctor's break-glass.
- **Opening with a reason (break-glass).** A placed doctor opens a file read-only for 24 hours with a reason (3 to 500 characters),
  audited in both logs, the owner's consultants told (or the creator and the coordinator when there is no owner); no export from
  such a window; ten openings an hour.

## During the board

- **A meeting built for a Tumour Board.** One call shell for members, the coordinator and the room screen (projector): agenda rail,
  the stage (the shared screen, the item the coordinator opened, the current slide, or the grid), the participant strip, the bottom
  bar and one side panel; pre-join with device checks; the waiting room and admission; pin for yourself, spotlight for everyone;
  screen share; chat kept with the meeting, reactions and raised hands; keyboard shortcuts; the quorum line (hospital heads present
  plus the PM-JAY three) that informs and never blocks; PACS images on the room screen with a viewing grant.
- **The agents stand in for absent heads.** Every head not present (and every specialty marked absent) appears as a dashed tile,
  "AI agent, support only", never a member and never counted for the quorum; the coordinator adds or removes any of the six. True
  states: ready, listening only while a named asker records, thinking, answering, speaking only while a device plays, could not
  answer. Any member asks by text or voice (or "@Radiology" in the chat); the answer streams statement by statement, each verified
  against the records before it is shown or spoken; spoken aloud by default on every device with agent voices on (a member in the
  room starts muted), Stop for this device or for everyone; decision-style questions are refused by rule; guideline questions get
  labelled reference text (India first); "Present your points" reads the brief's points, each checked again against the records
  now. An outside expert without the patient's consent hears and sees no identity.
- **The decision record, dictated or typed.** The coordinator fills the board record in the meeting (outcome, decision text,
  intent, actions, follow-up and the other fields of research/02), by voice or keyboard, Read back reads it aloud; one round per
  meeting per Case File; the owner's consultant corrects it afterwards with a reason; every version is kept.

## After the board

- **The Case summary that grows with the patient.** After the first decision it replaces the pre-board summary as the main summary
  and is rebuilt after every later decision and on demand: before the board, the decisions, what happened after; every sentence
  cites a record line or a board-record field; the owner's consultant reviews and edits (shown as "edited by Dr X on DD/MM/YYYY",
  carried forward); every version kept, the pre-board summaries in the history; a one-line summary on the list, searched like the
  UHID, the name and the age.
- **Communication and corrections.** The decision is communicated to the departments; actions can be withdrawn; corrections keep
  a reason and a version; the minutes and the NCG VTB export carry the board record (marked as added by Vaidyx).
- **Messages between logins.** Any placed login or the MDT Coordinator writes to a person or a department (a shared mailbox for its
  current members), with a Case File or meeting chip that grants nothing, reactions, edit and delete within ten minutes (the text is
  removed on delete), resolve and reopen, mute, Seen and typing, mentions, search; the bell and the browser notification name the
  sender and nothing else; a people-and-departments directory (phone only with consent); retention per message (an Organisation
  setting, 365 days by default); a first-use notice that says exactly what the system does.
- **History for the next patient.** Decided files feed the similar-files index (refreshed on decision, summary, stage and fact
  changes); the Case summary stays readable years later for anyone who may open the file.

## Across everything

- **Roles and access.** Department admins, doctors, residents, heads, the MDT Coordinator, the root admin and the auditor are plain
  accounts; no Tumour Board action creates or grants a Vaidyx admin. Scope decides what each login sees: full, requests only, or a
  read-only window; a department only asked sees its own records; listings never show the protected file.
- **Audit and safety.** Every action writes a hash-chained line in the Case File's log and a line in the organisation log; the
  access log keeps no query strings; stores are JSON under `data/tumour_board/`, written atomically with mode 600; secrets live in
  mode-600 files; every service listens on 127.0.0.1. The security audit (`tumour_board/eval/security_audit.py`, 29 checks) covers
  the routes and sockets of the whole run and never prints a password.
- **Voice, all local.** Speech to text and text to speech run on the server (the audio service on 7120, token-protected, loopback
  only, caps of 4 MiB and 60 s, in memory only, 90 s engine time limit); the browser sends 32 kbit/s recordings.
- **India first.** NCG, ICMR, PM-JAY and the Indian IDs, units and dates (DD/MM/YYYY) come first; international sources only where
  no Indian book covers a cancer.
- **The website.** The guided Case File, Meetings, Messages, People, Requests, Settings and the admin pages follow one set of
  components and tokens, laptop and phone, light and dark, with the axe accessibility checks of the baseline journeys clean.

## Checks and tools

Unit suite (about 4,300 tests), the TypeScript check and build, the mocked screenshot suite (123 tests), real-mode shots of every
role compared with the Phase 0 baseline, the per-phase live checks, the two-person live meeting test, the evaluations (agents, voice,
Q&A, summary) and the security audit: all listed with their commands in [HOW_TO_TRY.md](HOW_TO_TRY.md) section 8.
