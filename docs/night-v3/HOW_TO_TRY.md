# How to try Vaidyx-TB after the night-v3 run

A walk-through of what the run built (27 and 28 Oct 2026), on the server's own app. Everything here uses synthetic patients and the
demo logins; the real Case File is never touched. Logins are named by username only; the passwords are in `~/vaidyx/.tb_v2_demo_logins`
on the server (read it yourself, never print it into a chat or a log). Dates on screen are DD/MM/YYYY.

## 1. Before you start

- Services, all on 127.0.0.1 (reach them through your usual tunnel or SSH port forward; never expose them): the app on port 7000 (open
  `/tb-nik`), the demo hospital system on 7130 (`/his`), Orthanc and OHIF on 8042, LiveKit on 7880, the audio service on 7120, the
  two model servers on 8100 (Gemma-4-31B, the reasoner, non-medical) and 8101 (Qwen3.5-4B, the reader, Chinese, non-medical).
- If something is down: `tumour_board/serve_models.sh reader` then `tumour_board/serve_models.sh reasoner` (about 90 s each),
  `scripts/demo_services.sh start pacs his video audio`, then `~/vaidyx/start_vaidyx_app.sh`. `scripts/demo_services.sh status` shows
  what runs.
- Logins you will use: `tb-mdt` (the MDT Coordinator), `tb-breast-doc` (Breast Surgery consultant), `tb-gynonc-doc` (Gynaecologic
  Oncology consultant), `tb-rad-doc` (Radiology), `tb-path-head` (Pathology head), `tb-medonc-doc` (Medical Oncology); admins
  `tb-root`, `tb-breast-admin`, `tb-rad-admin`, `tb-path-admin`. Use two browsers (or one normal and one private window) when a step
  needs two people at once.
- The demo patients all carry "(SYNTHETIC)" in their names and `VXH/26/…` UHIDs. The run's own history files are `HIST-01` to
  `HIST-13` (decided past files with Case summaries) and the Phase 2 patients `TB-2026-0005` (ovary), `0006` (prostate), `0007`
  (stomach) and `0008` (lymphoma).

## 2. A new-cancer patient prepared end to end (ovary, one of the nineteen new checklists)

The patient is Lalitha Subramanian (SYNTHETIC), UHID `VXH/26/004220`, registered in the demo hospital with eight reports. Her Case
File `TB-2026-0005` already exists (the Phase 2 check created it). To watch the whole preparation from the start:

1. Sign in as `tb-gynonc-doc`. Open `TB-2026-0005`, press More in the Case File header and archive it with a reason (it stays in the
   archive, never deleted). Skip this step if you only want to look at the prepared file.
2. Home, press New Case File. Step 1 "Find the patient": type `VXH/26/004220`, Look up, "Registration found" shows the demo
   hospital's registration (name, age, sex, UHID, ABHA and PM-JAY id, never Aadhaar). Continue.
3. Step 2 "Which cancer": the groups shown first come from the record (age and sex); type "Ovar" in "Search a cancer" and pick
   Ovarian cancer (epithelial). The "Checklist and setting" card shows the checklist's records with their tiers and the label
   "Draft checklist: needs a clinician's check" (every new checklist is a draft from the NCG book, page cited). Pick the setting as
   recorded (advanced). Continue.
4. Step 3 "Logistics": "Filled in with the usual choices" (the Responsible Department, the meeting, the urgency); change the urgency
   if you like. Press Create and fetch records: the records come from the demo hospital system through the HIS connector.
5. The guided Case File opens on the Overview. Watch the section nav on the left: Records (the eight reports, "Open" shows the page,
   "Open images" the hospital viewer), Check (every checklist row: found, missing, late; each value with its quoted line; a pick
   between two differing reports needs a doctor's choice), Pre-Authorization (PM-JAY), Summary (the pre-board summary, every
   sentence with a cited line), Specialty agents (six chips, "Prepare all" writes the six briefs from the records), Similar Case
   Files, Board decisions (empty until the board meets).
6. Try the voice: in "Ask about this patient" press the microphone, say "What does the latest CA-125 report show?", the words land
   in the box, edit them, Ask. The answer shows its quoted lines and the model label; Read aloud reads it.
7. When the checks are done, press Send to the board: the question for the board is required (and a reason when items are still
   open); after sending, the summary and the slides are updated and only the MDT Coordinator is told. The doctor can move the file
   to another meeting or withdraw it from the Case File header.

If you create the file while `TB-2026-0005` still exists, step 3 shows "A Case File for this patient and this cancer exists
(Gynaecologic Oncology, Dr …)" with Continue off: that is item 1.1 (no duplicate Case Files), with "Open it" or "Ask to join".

## 3. A meeting with two absent heads where the agents answer in voice

1. Sign in as `tb-mdt`, open Meetings, create a meeting for today with video on (or start a planned one), add `TB-2026-0001`
   (Kavitha, breast) and `TB-2026-0005` (ovary) to the agenda, press Start meeting. Put the first Case File on the floor.
2. Do not sign in the Pathology and Radiology heads: the strip shows a dashed tile for each head not present ("Pathology, AI
   agent standing in", "AI agent, support only", the state word, "N points from the records"). An agent never counts as a member or
   for the quorum line. The Agents button at the right of the bar opens the panel: the six roles with switches (add Nuclear
   Medicine on demand), "Members can ask the agents", and a card per agent with its points (each with its record line) and the
   question box.
3. In another browser sign in as `tb-rad-doc`, open Meetings, join with the join code the coordinator shows, and wait to be
   admitted (the coordinator admits from the People panel). The member sees the same strip and can ask too.
4. Ask by voice: on the Pathology card press the microphone, say "What grade does the latest histopathology report record?",
   release; the tile says "Listening to <your name>" only while you record; edit the words, press Ask. The tile shows Thinking,
   the statements appear one by one as each is verified against the records, and the answer is read aloud on every device that has
   agent voices on (More: Agent voices; a member who joined in the room starts muted). "Speaking" shows only while a device plays.
   Stop on the answer stops it on this device; the coordinator's or the asker's Stop stops it for everyone.
5. Press "Present your points" on a card: the agent reads its points, each one checked again against the current records (points
   that no longer match are counted and left out) and labelled with its review status and the model that wrote the brief.
6. Ask "What would you do here?" to see the refusal: the agents answer from the records and the guidelines only, never a decision
   or a treatment advice; the two quick questions offered are the kind it can answer. In the Chat and questions panel "@Radiology …"
   addresses an agent by text.
7. The room screen (More: Room screen, for the projector) shows the floor, the images from PACS when the coordinator opens them,
   the agent tiles and the spoken answers as text with their sources.

## 4. A decision that produces the Case summary

1. In the same meeting, with `TB-2026-0001` on the floor, open the Board decision form (the Decision panel of the case on the
   floor). Fill the outcome and the decision text; press the microphone on the decision box to dictate, then edit; Read back reads
   the box aloud. Save. One board round per meeting per Case File; the fields follow the decision record of research/02.
2. After the save, the Case summary is scheduled and written by the reasoner from the whole Case File (the records, the board
   record, what happened after); open the Case File as `tb-breast-doc`, Summary section: the Case summary now stands as the
   patient's main summary (the pre-board summaries stay in the history). Every sentence cites a record line or a board-record
   field; a sentence the model wrote without a usable quote is left out and listed as removed. "Update the Case summary" writes it
   again after new records or a later decision. The line "Written by Gemma-4-31B (non-medical)" sits under it.
3. As the owner's consultant, review it: Mark reviewed or Flag; edit a sentence: the edit shows "edited by Dr Breast Surgery
   (demo) on DD/MM/YYYY" and is carried forward when the summary is rebuilt. Every version is kept.
4. The summary line (one line, editable by the consultant) shows on the Case Files list and is searched like the UHID and the
   name. The Board decisions panel of the Case File shows the record with its versions; "Correct this record" needs a reason and
   keeps the old version; the treatment intent changes only through a correction.

## 5. Similar Case Files

Sign in as `tb-breast-doc`, open `TB-2026-0001` (Kavitha), Overview card "Similar Case Files" (or the Summary card beside the
published cases), press "Find similar Case Files" (about 7 s the first time; optional words such as "HER2 positive with brain
metastases"): past breast files of this hospital in the order Gemma-4-31B gives (an order, never a score), each labelled "Past Case
File, not advice for this patient", with the stage, the key values with quotes, the board's decision as written, the outcome so far
(the past Case summary's sentence with its cited line and review status) and quoted "Why similar" and "How it differs" lines.
"Open Past Case File" opens a file of your department at once (audited in both files); a file of another department opens through
"Open with a reason" (the reason pre-filled "similar to Case File TB-2026-0001", read-only for 24 hours, audited, the owner's
consultants told; no export from such a window). The banner "Past Case File" stays on the opened file.

## 6. Messages between the coordinator and a doctor

1. Sign in as `tb-mdt`, open Messages (the icon beside the bell, or the nav item), New message, pick `tb-breast-doc` (or the Breast
   Surgery department), "Add a Case File" lists only the files you may open; write and Send.
2. In the other browser as `tb-breast-doc`: the badge and the bell item "New message from MDT Coordinator (demo)" appear at once
   (never the text); open it (the sender sees Seen), type (the sender sees "is typing"), answer, react, Mark as resolved. Edit or
   delete your own message within ten minutes (the text is removed from the server on delete).
3. A Case File chip grants nothing: a reader without access sees "A Case File you cannot open" with "Open with a reason". Message
   buttons sit on the People page, the Team panel, the Case File header (More: Message the MDT Coordinator), the meeting People
   panel, the request cards and the Requests and Meetings pages. The first-use notice states the hospital's retention (an
   Organisation setting, 365 days by default).

## 8. Checks you can run

- The security audit: `/data/vaidyx/venv/app/bin/python -m tumour_board.eval.security_audit` (add `--with-writes` for the two checks
  that leave a message and a window behind, `--skip-login-limit` while someone uses the app; it never prints a password).
- The unit suite: `/data/vaidyx/venv/app/bin/python -m pytest -q -p no:cacheprovider tumour_board/tests his_mock/tests --deselect
  tumour_board/tests/test_agents_live.py` (about six minutes; the live agent tests need the models).
- The website: `cd web/tb-nik && export PATH=/data/vaidyx/tools/node/current/bin:$PATH && npx tsc -b --noEmit && npx vite build`;
  the mocked screenshot suite `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts`.
- Real screens for every role: `docs/night-v3/tools/baseline_shots.sh <label>` (pictures under `/data/vaidyx/night-v3/baseline/<label>/`),
  compared with the Phase 0 baseline by `docs/night-v3/tools/compare_shots.py`.
- The per-phase live checks: `node docs/night-v3/tools/phase6_real_check.mjs` (agents), `phase8_real_check.mjs` (messages, two
  logins), `phase7_real_check.mjs` (similar files), the two-person live meeting test `npx playwright test -c
  e2e/live/playwright.live.config.ts`, and the evaluations under `tumour_board/eval/` (`agent_live_eval`, `audio_eval`, `qa_eval`,
  `summary_eval`: one at a time on the GPU).

## 9. Known limits (for the owner)

- The thyroid checklist is parked (NICE licence); brain and CNS use EANO 2021 (CC BY 4.0). Every new checklist is a draft until a
  clinician checks it. The breast prognostic stage stays a labelled preview on the internal app only.
- A browser notification cannot be tried on this server (no VAPID keys). A real phone (iOS autoplay and microphone rules) was not
  tested. Cohere Transcribe as a second voice engine is parked.
- The landing page wording is the owner's (`web/tb-nik/src/features/landing/content.ts`); the run only flags that
  "Clinically-Validated models" reads as a validation claim.
