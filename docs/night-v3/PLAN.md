# Night-v3 plan: making Vaidyx complete

Owner: Nikhil-Rao20. Approved for an unattended run on 27 Oct 2026. Branch `night-v3` (from `main` after PR #2). How the run works:
[ORCHESTRATION.md](ORCHESTRATION.md); session prompt: [PROMPT.md](PROMPT.md); progress: [LOG.md](LOG.md); facts at the start:
[research/00_current_state.md](research/00_current_state.md).

## 1. What the owner asked for (27 Oct, his nine points, in short)

1. **Checklists for all of India's top cancers**, from the guideline books in the library, so any common cancer gets its checks, gaps and
   flags automatically; an unknown cancer still gets a basic checklist so no patient skips the preparation.
2. **A richer decision record** at the end of each case (what an MDT Coordinator should capture), feeding point 7.
3. **The clinician-made synthetic file** comes later; until then test on the existing Case Files and make new synthetic ones as needed.
4. **The specialty agents are THE feature** ("an AI agent for Tumour Boards"): when attendance shows a head absent, that specialty's agent
   joins the meeting, and when the board asks it a question it answers like a colleague (support, never decisions). Make it fully
   functional and prominent. **Voice is now allowed**: speech to text and text to speech (the October research), wherever it helps: talk
   to "Ask about this patient", dictate the decision fields, ask the agents.
5. **The meeting (video) experience** must be as easy as Google Meet, built for a Tumour Board; research it, fix the UI, make every
   function work, add what is missing.
6. **Messages between logins** (like Slack): anyone finds a person or department and sends a direct message; the receiver sees it in
   the bell and replies, reacts or resolves it. For urgent things, missed requests, and anything outside the fixed requests.
7. **A Case summary that grows with the patient**: after each board, an evidence-based summary of the whole Case File (before the board,
   the decisions, what happened after), replacing the pre-board summary as the patient's main summary, kept and updated at every later
   board, visible to anyone who opens the file years later, and searchable like the UHID, name and age.
8. **Similar Case Files**: search the hospital's own history for Case Files like this one (the model in the backend ranks them), show
   them in order, and open the full past file with its Case summary, so the board sees what was done and how it went.
9. **The not-built list and the bugs** from the walkthrough, fixed and tested.

Throughout: **a human over the loop** (edit access where a doctor finalises), **do not break what works**, **new screens follow the
current UI**, research before deciding, document everything so any session can continue.

## 2. Owner decisions for this run

| # | Decision |
|---|---|
| D1 | **Voice is allowed** (lifts the 17 Oct "no voice" decision). Local models only (`research/00_current_state.md` section 6), audio never stored. Speech to text only fills text boxes the person then edits and sends; text to speech only reads text already on screen or an agent's grounded answer. |
| D2 | **Specialty agents in the meeting:** every absent head's agent stands in (not only the first). The coordinator can add any of the six on demand (always Radiation Oncology and Nuclear Medicine) and remove one. An agent answers like a colleague, in voice and text, from the records and the guidelines only, with its sources, never a decision or a treatment recommendation. It never counts as a member or for the quorum. It is labelled "AI agent, support only". Its states are true states (it shows "listening" only while a question is being spoken to it). **Its answers are spoken aloud by default** (on the room screen and in the call) and shown as text with sources; anyone can mute agent voices for themselves (owner, 27 Oct). |
| D3 | **The Case summary:** after the first board decision it replaces the pre-board summary as the main summary, and it is updated after every later decision. Every sentence cites a record line or a board-record field. The owner's consultant reviews and edits it (an edit shows "edited by Dr X"). Every version is kept, and the pre-board summaries stay in the history. |
| D4 | **Similar Case Files** (a new owner exception, like published cases):<br>• Vaidyx lists past Case Files of this hospital that resemble this one, in order, each with "why similar" and "how it differs" lines quoted from both files.<br>• No numeric score.<br>• Labelled "Past Case File, not advice for this patient". Vaidyx never applies a past decision to this patient.<br>• Access: see D10. |
| D5 | **Messages:** any placed login may message any person or any department of the same hospital. A message to a department reaches all its members, and any member may answer. A message never grants access to a Case File it links to. Push notifications carry no patient details. |
| D6 | (Owner confirmed 27 Oct.) **New cancer checklists** are built from the guideline books with page-cited sources and labelled "Draft checklist: needs a clinician's check". They are switched on, like the CUP draft. They never compute a stage and never advise treatment. |
| D7 | **The decision record:** the coordinator fills it in the meeting (typing or dictating). The owner's consultant can correct it afterwards. Every version is kept. The fields follow `research/02_board_decision_dataset.md`, and all present fields stay. |
| D8 | **Doctor break-glass** (decided 17 Oct as R03-Q02, never built): a doctor without access opens a Case File read-only with a reason. The window lasts 24 h, is audited, and the owner's consultants are told. |
| D9 | **The not-built list keeps its designs:** docs/ui/casefile-steps/DESIGN.md B7 and B8 (multi-step Send to the board; after sending, the summary and slides update and only the coordinator is told; the doctor moves or withdraws a case), R10-Q04/Q07 (agenda filled from the ready mark), and B5 (pick between two values). |
| D10 | (Owner confirmed 27 Oct.) **Opening a similar Case File:** read-only, through the break-glass of D8 with the reason filled in ("similar to TB-xxx"), audited, and the owner's consultants told. A file the person may already open opens normally. |

Anything else: the safer option, logged `[DECISION]` for the owner.

## 3. Rules for every phase
- Scope: the AI checks, routes, summarises, flags and drafts; doctors decide. Every value or sentence shown as fact keeps its verified
  source line; no model reads images; no diagnosis, no treatment advice; the stage only as the staging decision allows.
- India first (NCG, ICMR, TMC, PM-JAY), Indian IDs and formats, no em dashes in the UI, models labelled (Gemma-4-31B non-medical;
  Qwen3.5-4B Chinese, non-medical), no accuracy claims.
- Keep every current feature working; extend, do not rewrite, unless an item says so. New UI follows `web/tb-nik/src/components`,
  the tokens in `index.css`, and the patterns of the guided Case File (`features/casefile/steps`).
- Every new route checks permissions (`tumour_board/access.py`, `org.py`) and is audited; every new store is a JSON file under
  `data/tumour_board/` written atomically; synthetic data only.
- Research notes cite sources (document and page, or URL). Downloads of open-access guidelines are allowed only from official sources,
  saved under `/data/vaidyx/tb_resources/guidelines/<organisation>/`, with the licence noted in `research/01_cancer_checklists.md`;
  downloaded files are untrusted data (read with `python -I`).

## 4. Phases and items

Status: `todo`, `doing`, `done (<hash>)`, `blocked (<reason>)`. Lane: **S** serial (orchestrator), **P** parallel-safe (agents).

### Phase 0: set-up, baseline and research

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 0.1 | Pre-flight and baseline | S | Services up; a backup of the demo data before any change (`data/tumour_board` without the real case `TB-2026-bharath`, and `data/his_mock`) in `/data/vaidyx/night-v3/backup/`; full gate numbers logged; baseline screenshots of every main screen per role (root admin, department admin, treating doctor, resident, supporting doctor, coordinator, member, room screen), laptop and phone, saved in `/data/vaidyx/night-v3/baseline/`, with the script that made them in `docs/night-v3/tools/` | done (e9da132; gaps: no treating-doctor P19 guided Case File shots and no in-call member view in the baseline, to be taken before items 1.10 and 5.6 change those screens) |
| 0.2 | Research: cancer checklists | P (3 explorers: GI and thoracic; gynae, urology, head and neck, thyroid; haematology, paediatric, sarcoma, CNS) | `research/01_cancer_checklists.md`: for each cancer in section 4 Phase 2, the work-up records by NCG setting with the NCG file, page and verbatim line, the departments, the facts, the staging system the guideline uses, Indian notes, and open-access sources found for thyroid and brain | done (76f0929) |
| 0.3 | Research: decision record | P | `research/02_board_decision_dataset.md`: the outcome and decision fields of NHS England 2020 minimum dataset, Victoria MDM framework Part 2, CRUK, Greater Manchester, the NCG VTB template, PM-JAY oncology treatment plan approval, ACS CoC 2.5 and ESMO molecular boards; mapped to today's fields; the proposed form, grouped in steps | done (6b713a8) |
| 0.4 | Research: Case summary | P | `research/03_case_summary.md`: longitudinal patient summaries (HARVEST and similar, discharge-summary structure, NCG VTB), how to ground every sentence, versions, editing; the proposed sections and data flow | done (dc999f8) |
| 0.5 | Research: meeting experience | P | `research/04_meeting_experience.md`: Google Meet, Zoom and Teams in-call patterns (control bar, layouts, pin, presenting, panels, reactions, captions, shortcuts, waiting room, device settings), digital tumour board products (NAVIFY, Philips), LiveKit capabilities (screen share, data channel, layouts); the proposed design with ASCII layouts for member, coordinator, room screen and phone | done (0bc3356) |
| 0.6 | Research: agents in the meeting | P | `research/05_board_agents.md`: AI participants in meetings (Zoom AI Companion, Teams Copilot), voice-agent turn-taking (push to talk, visible true states, barge-in, latency budgets), grounding and refusals; the proposed behaviour within D2 | done (5e84781) |
| 0.7 | Research: messages | P | `research/06_messages.md`: Slack and Teams patterns (direct messages, department conversations, threads, reactions, mentions, unread, presence, search, resolve), clinical secure messaging (Epic Secure Chat, TigerConnect), India's DPDP Act 2023 points; the proposed design within D5 | done (3ddf9e4) |
| 0.8 | Research: similar Case Files | P | `research/07_similar_cases.md`: patient-similarity search in oncology (patients-like-mine, case-based retrieval), hybrid retrieval with structured filters, embeddings and model re-ranking, explaining matches; the proposed pipeline within D4 and D10 | done (a98f9b3) |
| 0.9 | Research: voice wiring | P | `research/08_voice.md`: from `docs/tumour-board/audio_feature.md`, the service API, engines, the clinical prompt and lexicon, the GPU budget, and every screen where a microphone or a speaker button goes | done (d2c56bf) |

### Phase 1: the bugs and the not-built list (owner point 9)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 1.1 | Duplicate Case Files | S | Creating a Case File for a patient (same UHID or a linked registration) and the same cancer as a non-archived file is refused by the server with the existing file's owner. New Case File shows "A Case File for this patient and this cancer exists (Breast Surgery, Dr X)" at the Patient step and at Create, with "Ask to join" (the team join request) or "Open it" when allowed. Another cancer is allowed and listed as the patient's other Case Files. Tests. | done (7a24f94) |
| 1.2 | Demo-data clean-up | S | The leftover test duplicates (the extra Kavitha breast file made on 26 Oct by the Haematology login, the duplicate Priya Venkatesan file not used by tests) are archived with the reason "duplicate test file" (archived, never deleted), audited; files referenced by tests or docs stay | done (394997d) |
| 1.3 | A linked file in another department's list | S | A Case File owned by another department appears only as linked ("Owned by Haematology", read-only) and is not counted in the department's own counts or "Mine" | done (e8daf37) |
| 1.4 | Send to the board, multi-step | S | B7: steps meeting (next open meeting pre-filled; "not scheduled yet" when none), for discussion or for noting, presenter (you or a resident on the team), note for the coordinator, a reason when items are open, confirm. The server requires the question and, when items are open, the reason; it stores list, presenter and meeting, adds the Case File to that meeting's agenda list (R10-Q04/Q07) and tells the coordinator. A resident's send becomes a sign-off proposal. Tests. | done (6c72018) |
| 1.5 | After sending | S | B8: a new or changed report after the ready mark updates the summary and the slides (the ready hook runs again, never during a session) and tells the coordinator only; a new value that disagrees or is only preliminary shows both values in the summary and slides, gives the doctor a "Check 1 value" task, and the coordinator's agenda row shows "waiting on Dr X". Tests. | done (2f196f3) |
| 1.6 | The doctor moves or withdraws a case | S | From the Case File's More menu and the Case Files list's meeting chip: move to another planned meeting, or take it off the agenda with a reason; the coordinator is told; audited | done (bf95933) |
| 1.7 | Pick between two values | S | B5: when two reports differ, the doctor picks the value the board should use; it is stored as a confirmation on that report, the summary and slides use it, the difference stays noted, undo works | done (e352569) |
| 1.8 | Residents' sign-off for the remaining steps | S | A resident's key-value confirm, reason for discussion, urgency and staging confirm become proposals the consultant approves in "Sign-offs from your team" | done (a9a640a) |
| 1.9 | Doctor break-glass | S | D8: "Open with a reason" for a doctor without access: read-only, 24 h, audited, owner consultants told; shown on the 403 page and used by Phase 7 | done (7d65da6) |
| 1.10 | Tests and old page | S | `e2e/shots/casefile.spec.ts` covers the guided Case File (mock fixtures for `/steps` and `/staging`); the previous `CaseFilePage.tsx` and its fallback are removed if nothing needs them (the public demo now runs current code) | done (d64e833) |
| 1.11 | The 18 Oct walkthrough wishes | S | Each wish the owner parked on 18 Oct is checked against today's app and finished where not met: clear "Join a Case File" and "Join a meeting" buttons (with codes) on the home screen; no duplicate Home and Case Files lists; a better filter on the list; the date and time pickers open beside their field and look modern; the coordinator sees a clear confirmation when a Case File is added to an agenda. (The search details wait for the owner: Parking lot.) | done (64751b5) |
| 1.12 | Breast prognostic stage (if time allows) | S | The staging card of breast cancer also works out the AJCC 8 prognostic stage group (grade, HER2, ER, PR) from the book's table on pages 621 onwards, same guards and preview label as the anatomic stage (docs/staging/DECISION.md) | done (cc7f881) |

### Phase 2: checklists for India's top cancers (owner point 1)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 2.1 | Shared groundwork | S | New facts in `facts.json` (for example PSA, Gleason / ISUP grade, CA-125, AFP, beta-hCG, LDH, thyroglobulin, calcitonin, bone marrow result, flow cytometry, cytogenetics and molecular markers for blood cancers, CSF cytology, ophthalmic examination) and document types (bone marrow, flow cytometry, cytogenetics or FISH, CSF, ophthalmology note) with keywords and HIS codes; the hard-coded cancer lists extended (`steps.py` site words, `guidelines.py` cancer words, tests; `test_listing.py`'s "no ovary protocol" assertion changed); a schema test that every protocol parses and every source line is found on its cited page of its book | done (0ea10f2) |
| 2.2 | Colon | P | `colorectal_colon.json` from the NCG colorectal file; the picker's colorectal entry asks colon or rectum | done (43a10be; the picker's colon-or-rectum question lands with 2.10) |
| 2.3 | Upper GI and liver | P | `stomach.json`, `oesophagus.json`, `liver_hcc.json`, `gallbladder.json` | done (b111c9b) |
| 2.4 | Gynaecology | P | `ovary.json`, `corpus_uteri.json` | done (9c6f1cf) |
| 2.5 | Urology and germ cell | P | `prostate.json`, `kidney.json` (adult; Wilms in 2.8), `germ_cell.json` | done (1dd5fd8) |
| 2.6 | Head and neck and thyroid | P | `larynx.json` (with the head and neck structure); `thyroid.json` from an official open-access guideline when NCG has none (source and licence logged) | done (9298d82; larynx only: thyroid parked, a licence decision for the owner) |
| 2.7 | Blood cancers | P | `lymphoma.json` (adult and child settings), `leukaemia.json` (adult and child settings) from the NCG haematolymphoid files | done (0a5f4c5) |
| 2.8 | Paediatric and sarcoma | P | `wilms.json`, `retinoblastoma.json`, `bone_sarcoma.json`, `soft_tissue_sarcoma.json`, `brain_cns.json` (official open-access source when NCG has none) | done (c9828c6) |
| 2.9 | Unknown and other cancers | S | The generic checklist stays for unknown solid cancers; a `generic_haem` variant for blood cancers not listed (marrow, flow cytometry, cytogenetics instead of staging imaging); the picker's "not listed" path asks solid or blood; CUP unchanged | done (d5f96c4; the picker's solid-or-blood question is in 2.10's commit) |
| 2.10 | Wiring | S | Every picker entry maps to a checklist (`cancers.ts`), shown "checklist built (draft)"; specialty packs and the cancer-against-reports warning know the new cancers; the Case File's glance groups show the new facts | done (55a8f95) |
| 2.12 | Flags from the books (if time allows) | P | Dose and schedule reference lines for the new cancers from the NCG regimen tables (each with its page), added to `dose_references.json`, so the decision checks cover them | done (58a35c6) |
| 2.11 | Synthetic patients and an end-to-end check | S | At least four new synthetic patients in the demo HIS (seed scenarios, for example ovary, prostate, stomach, lymphoma) with realistic report sets; each Case File created, its reports read by the real models, its checklist gaps sensible; screenshots | done (6201c34; the end-to-end run logged) |

Each protocol: `version` "0.1-draft", `approval.status` "draft", the note "Draft checklist from <book>: needs a clinician's check",
records per setting with `sources` (book, page, verbatim line), departments that exist in the hospital set-up, and unit tests.

### Phase 3: the decision record and the Case summary (owner points 2 and 7)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 3.1 | Decision record v2 | S | The coordinator's decision form gains the fields of `research/02` grouped in steps. At least:<br>• the board's recommendation and the treatment intent (choice)<br>• modalities and sequence<br>• alternatives discussed; divergent views with names<br>• stage as agreed (as recorded or a confirmed draft)<br>• report reviews or corrections<br>• further investigations (each becomes an action for its department); referrals (genetics, palliative care, nutrition, psycho-oncology, fertility, dental)<br>• trial considered; patient preference considered<br>• responsible clinician and key worker; who tells the patient and by when; next review or trigger for re-discussion<br>• PM-JAY treatment plan approval (yes, no, not applicable)<br><br>All present fields are kept; the UI and backend limits and the outcome labels are aligned; the communication fields are captured, so their info flags clear; the owner's consultant can correct the record later (versions kept). Tests. | done (84cd710) |
| 3.2 | Board decisions on the Case File | S | The Case File shows every board round (Board form panel becomes "Board decisions"); the minutes, deck and NCG VTB export carry the new fields | done (8acf198) |
| 3.3 | The Case summary | S | D3:<br>• A new module builds the Case summary after each recorded decision (in the background) and on demand.<br>• Inputs: the verified facts, the documents in date order, the pre-board summaries, every board record, the follow-up actions and their closures, the confirmed stage, the members' cards.<br>• Sections: presentation and diagnosis; stage; each board round (date, question, decision, rationale, intent, actions); treatment and follow-up since; current status and open actions.<br>• Every sentence cites a record line (checked word for word) or a board-record field (exact text); anything uncited is dropped.<br>• Versions are kept; the owner's consultant reviews and edits.<br>• Tests, and a real-model run on decided synthetic Case Files. | done (d0fdfc7) |
| 3.4 | The main summary and the summary line | S | After the first decision the Summary section and the Overview show the Case summary first; the pre-board summaries move to "Before the board on <date>". A short summary line (`case.summary_line`, generated from the Case summary, editable) shows in the Case File header and the list rows and is searched by the list search and the command search, together with the cancer and the decision text | done (78f40d3) |
| 3.5 | Versions of the pre-board summary | S | A rebuild keeps the earlier version (no overwrite); the review of each version is kept | done (e9cb662) |

### Phase 4: voice (owner point 4, voice part)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 4.1 | Audio service | P | `tumour_board/audio_service/` run in `/data/vaidyx/venv/audio` on 127.0.0.1:7120 with `scripts/audio.sh start|stop|status`:<br>• `/stt`: browser audio to text; faster-whisper large-v3-turbo fp16, VAD, the clinical prompt; Cohere as a switchable engine; Parakeet on CPU as fallback<br>• `/tts`: Kokoro with the clinical normaliser and lexicon; CPU fallback<br>• `/health`<br><br>Limits: 60 s per clip, nothing stored. Tests. | done (b89e9ff) |
| 4.2 | App routes | S | `/api/tb/audio/{status,stt,tts}` behind the login, rate limits and size caps, audited without content; `TB_AUDIO_URL` set in the app start script; everything degrades to text when the service is down | done (6f5d907) |
| 4.3 | Microphone and speaker components | P | `MicButton` (tap to talk, level meter, true states "listening", "transcribing", the text inserted where the cursor is and editable, Esc cancels) and `SpeakButton` (read aloud, stop); keyboard shortcut; permission errors in plain words | done (eb4e0b3) |
| 4.4 | Voice where it helps | S | "Ask about this patient" gets a talk mode (speak, see and edit the text, send; the answer read aloud), plus the question for the board, every decision-record text field, reasons and notes, the specialty agent chat; later phases add the meeting and messages | done (330c430) |
| 4.5 | Voice check | S | `tumour_board/eval/audio_eval.py`: clinical sentences spoken by Kokoro, transcribed, word error rate logged; a Playwright check with a fake microphone file | done (c3de60a) |

### Phase 5: the meeting experience (owner point 5)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 5.1 | The call shell | S | One in-call layout, shared by the member view, the coordinator's control view and (in its own variant) the room screen, as designed in `research/04`.<br><br>**Layout and tiles**<br>• The main stage shows what is presented (the case summary slide, a report page, the images, the Staging card), with the participant strip; or a grid when nothing is presented.<br>• Speaker view, pin and spotlight; an active-speaker ring.<br>• Tiles with name, department, role badge (head, coordinator, presenter), mic state, hand.<br><br>**Bottom control bar**<br>• mic, camera, present, raise hand, reactions, chat, people, agenda, more (devices, layout, full screen), leave<br>• the coordinator also gets next case, timer, decision and end meeting<br><br>**Also**<br>• One side panel at a time: People (in the room, remote, waiting, admit), Chat and questions, Agenda, Case, Agents, Decision.<br>• Device change after joining, connection quality, a reconnect banner, keyboard shortcuts, tooltips, accessible labels. | done (59f70d5) |
| 5.2 | Present a screen | S | LiveKit screen share for the coordinator and the presenter (the coordinator may allow others), shown on the main stage for everyone | done (af3c171) |
| 5.3 | Meeting chat | S | Text chat for the meeting over the live channel, kept with the meeting record, apart from questions to the agents | done (0532658) |
| 5.4 | Case flow | S | An agenda rail with the current case and its time; next case moves everyone; the presenter shown; a quorum line (heads present, agents standing in, the PM-JAY composition) | done (d20496e) |
| 5.5 | Phone and room screen | S | Phone layout for members; the room screen in large type for a projector | done (691985d) |
| 5.6 | Live checks | S | The two-person live test (fake camera and microphone) passes with screen share and chat; screenshots for member, coordinator, room and phone reviewed; the existing meeting tests stay green | done (3dfc566) |

### Phase 6: the specialty agents as members of the board (owner point 4)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 6.1 | Agents in the room | S | D2:<br>• Every absent head's agent joins as a participant tile: the Vaidyx agent mark, "Radiology, AI agent standing in", support only.<br>• True states: ready, listening (while a question is spoken to it), thinking, speaking.<br>• The coordinator adds or removes any of the six; agent state is kept with the meeting, not only in memory; agents never count for the quorum. | done (e33220c) |
| 6.2 | Points from the start | S | R12-Q09: when a case opens, each agent's brief points sit in its tile; "Present your points" makes the agent speak a short summary of its brief | done (e33220c, built with 6.1) |
| 6.3 | Ask an agent | S | Any admitted member and the coordinator ask a chosen agent (click its tile, or "@Radiology") by text or voice.<br>• The answer streams as text with citation chips and references and is spoken aloud (on the room screen by default; members can mute agent voices).<br>• Short, like a colleague, records and guidelines only; never decides or advises.<br>• It remembers this case's earlier questions in the meeting and the Case File's agent chat.<br>• Answers are saved with the meeting and in the Case File's agent thread. | done (edb48ef; the shared thread in 814d7c6) |
| 6.4 | Agent quality | S | Per-role prompts and packs reviewed; context pre-loaded when the case opens; first words in about 6 seconds or less (streaming); an evaluation of 40 synthetic questions per role over the demo Case Files (grounded, no advice, correct refusals), results logged | done (8c20a48) |
| 6.5 | Agents on the Case File | S | The six "records check" helpers become a prominent "Specialty agents" area (an Overview card and the Summary section), each with its brief, chat and voice; preparing in the background with count badges (owner's 18 Oct wish) | done (814d7c6) |

### Phase 7: similar Case Files (owner point 8)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 7.1 | Case profile index | P | `tumour_board/similar.py`: a profile per non-archived Case File (never the protected real case) from its verified facts, Case summary and decisions (cancer, setting, stage as recorded or confirmed, histology, key biomarkers, age band, sex, treatments, decisions and outcomes so far); embeddings with the existing model and cache; updated when a file changes | done (e7a2dec) |
| 7.2 | Search and ranking | S | Candidates by cancer group and hybrid text retrieval, re-ranked by the reasoner. The top results each carry "why similar" and "how it differs" lines, each quoting a line of this file and a line of the past file, both checked word for word. Ordered, no numeric score. The doctor can add words ("HER2 positive with brain metastases"). | done (eadd1fa) |
| 7.3 | Screens | S | A "Similar Case Files" card in the Summary section (beside published cases) and a link from the Overview.<br>• A result card shows cancer, stage, key values, board decisions with dates and intent, the outcome so far and why it is similar.<br>• Opening a result follows D10: read-only, labelled "Past Case File, not advice for this patient", audited. | done (f36e472) |
| 7.4 | A history to search | S | At least ten decided synthetic Case Files across cancers with Case summaries (made with the demo HIS and scripted decisions), so the search shows meaningful results; checked on Kavitha's file | done (56147f3) |

### Phase 8: messages (owner point 6)

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 8.1 | Messages backend | P | `tumour_board/messages.py` + routes, D5:<br>• Conversations: direct, or to a department.<br>• Messages: text, an optional Case File or meeting link (access unchanged), reactions, editing or deleting your own within 10 minutes, "resolved" per conversation, unread per person, mentions, search.<br>• Storage: JSON lines under `data/tumour_board/messages/`; audited; rate limits. Tests. | done (a16146c) |
| 8.2 | Real time | S | A WebSocket for messages (a second `Hub`), typing and online state; the bell gets a "message" kind; browser push says only "New message from Dr X" | done (85fa700) |
| 8.3 | Directory | S | A people-and-departments search for every placed login (name, department, role, photo; phone only when the person made it visible) | done (b079200) |
| 8.4 | Screens | S | "Messages" in the top bar with an unread badge; a Slack-like page (conversations on the left, the thread on the right, a composer with voice, reactions, resolve, Case File chips); "Message" buttons on people (People page, Team panel, meeting People, request cards, the Case File owner) and "Message the MDT Coordinator"; phone layout | done (af8b3ed) |
| 8.5 | Checks | S | Two logins exchange messages live; the unread badge and the bell work; a department message reaches all its members | done (see LOG) |

### Phase 9: integration and demo readiness

| ID | Item | Lane | Done when | Status |
|---|---|---|---|---|
| 9.1 | Full regression | S | The security audit (`tumour_board/eval/security_audit.py`) passes, including the new routes and sockets (voice, messages, similar files, break-glass); all unit tests, the mocked screenshot tests, and real checks for every role on laptop and phone, light and dark; compared with the Phase 0 baseline; nothing that worked is broken | todo |
| 9.2 | Whole-run review | P | One reviewer per area (Opus) over the whole night's diff; serious findings fixed | todo |
| 9.3 | Demo walk-through | S | `docs/night-v3/HOW_TO_TRY.md`: a new-cancer patient prepared end to end; a meeting with two absent heads where the agents answer in voice; a decision that produces the Case summary; similar Case Files; messages between the coordinator and a doctor. Logins by username only. | todo |
| 9.4 | The clinician's file | S | `HOW_TO_TRY.md` says how to load the owner's clinician-made synthetic file when it arrives (outside-report upload or a demo-HIS seed) | todo |
| 9.5 | Features overview and finish | S | `docs/night-v3/FEATURES.md`: before, during and after the board with everything built; the Morning summary final; `/data/vaidyx/night-v3/RUN_COMPLETE` created | todo |

## 5. Pause, stop and resume
- `docs/night-v3/run_night.sh pause`: the running session finishes its current item, commits, logs `[PAUSED]` and ends; nothing new starts.
- `docs/night-v3/run_night.sh resume`: starts again from the next unfinished item.
- `docs/night-v3/run_night.sh stop`: stops at once; the next start recovers the interrupted item (PROMPT.md, "Recover an interrupted session first").
- `docs/night-v3/run_night.sh status`: what is running and how far the plan is.
- The weekly usage is watched by the owner (Claude usage page, or `/usage` in an interactive session); at about 80 % the owner runs `pause`.

## 6. Order and what matters most
Phases run in order (0 to 9). If time runs short, the run still finishes the phase it is in properly (gate, review, log) rather than
starting half of the next. Within a phase, items with an S lane run in order; P items run in parallel with agents.
