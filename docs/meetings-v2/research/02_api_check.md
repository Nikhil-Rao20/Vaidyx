# 02: API check of every meeting route (item 1.2, 2 Nov 2026)

Script: `docs/meetings-v2/tools/api_check.mjs`. One row per check (route, role, state, expected, got, PASS / FAIL / NOTE) in
`/data/vaidyx/meetings-v2/api_check.json`; the console log is `/data/vaidyx/meetings-v2/api_check.log` (the first run is kept as
`api_check.run1.json` and `api_check.run1.log`). The WebSocket is out of scope (item 1.3 covers the screens).

## How to run

```
cd /home/bharath.tangella/vaidyx/Vaidyx
export PATH=/data/vaidyx/tools/node/current/bin:$PATH LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib
node docs/meetings-v2/tools/api_check.mjs
```

- Runs against the app on http://127.0.0.1:7000 in about a minute and prints one line per check and a summary. Logins go through
  `tools/lib.mjs` (one stored session per login under `/data/vaidyx/meetings-v2/state`); no password and no join code is printed or written.
- Run it before 23:40 (planned meeting A is set for 23:59 today, so a "Not discussed" Case File moves there and nowhere else). Leave 15
  minutes between two runs: the join route allows 5 tries per 15 minutes per login and the member login uses 3.
- Logins: MDT Coordinator `tb-mdt`; treating consultant and presenter of Rekha `tb-gynonc-doc`; member doctor `tb-rad-doc` (joins,
  is admitted, not on any Case File's team); `tb-medonc-doc` joins and is left waiting (the "waiting doctor"), then admitted late;
  `tb-breast-doc` never joins; root admin `tb-root`.
- Meetings it makes, all titled "API check ... (synthetic)": the meeting of today (started, run, ended), planned meeting A (today 23:59,
  cancelled at the end), planned meetings B and C (in 7 days; B cancelled, C ended without being started), and one dated 06/01/2020 (the
  past-date check, cancelled at once). The finally block ends or cancels whatever is still open, even after an error.
- Case Files: Rekha Sharma TB-2026-0011 (cervix, Gynaecologic Oncology), Mohammed Arif TB-2026-0010 (oral cavity, Surgical Oncology,
  taken up during the meeting) and Parvathi Murugan TB-2026-0012 (cervix, made by the first run as the coordinator from VXH/26/004209;
  a rerun reuses it after the 409 "one Case File per patient and cancer"). All synthetic. The real case is never touched.

## Totals

| Run | When | Checks | PASS | FAIL | NOTE |
|---|---|---|---|---|---|
| 1 | 02/11/2026 20:36 | 381 | 358 | 6 | 17 |
| 2 | 02/11/2026 20:52 | 383 | 359 | 7 | 17 |

Run 2 is the current `api_check.json`. It added three checks after run 1: meeting A's agenda is sent before it is rescheduled (the
finding 10 fix tells the departments only once an agenda went out) and a code made a week before meeting B must still work when it
starts (finding 2, the seventh FAIL). Run 2 reused TB-2026-0012, so it has no reading-job row. Both runs ran against the same app
process (pid 969914).

**Which code was tested.** The app on :7000 was started at 18:55 and not restarted since, so both runs tested the code from before the
fix commits `1534535` (M2-1.4a: findings 1, 3, 5, 8, 10, 13) and `60a8231` (M2-1.4b: finding 2 and the screens). Every FAIL below is
already addressed in the committed code but is not live. Restart the app (CLAUDE.md "How to run") and run the script again: the FAIL rows
of findings 2, 3, 5 and 10 should turn PASS, and the row "move a Case File decided on a closed meeting" changes from 400 to 200.
Line numbers are those of commit `2d24a90` (the review's lines; the running code is the same up to `meetings.py:2036`, a few lines
lower after it).

All 42 routes of `tumour_board/api/meetings.py` were called, plus `GET /sessions/{mid}/minutes` (HTML and JSON),
`GET /meetings/{mid}/deck` and `GET /cases/{id}/export/vtb`. No call answered 5xx.

## FAIL rows

| Rows | Check | Expected | Got | Cause | Fix idea | In the committed code |
|---|---|---|---|---|---|---|
| reschedule: Case File | `PUT /meetings/{mid}` a planned meeting to a new date, then read Rekha's Case File | `board_date` follows the new date | `board_date` stays on the old date | Finding 10. `update()` (`meetings.py:883-920`) saves the new date and audits it, but never calls `_link_case` (`meetings.py:986`), so the Case Files on its agenda keep the old `board_date`; department requests and reminders quote it | On a date or time change, `_link_case` every listed Case File and clear `starting_notified_at` | Fixed in `1534535` (`_moved_in_time`) |
| reschedule: notice | Same, then read the owner doctor's notifications | a notice of the new date | 0 new notices | Finding 10. `update()` notifies nobody; only the live socket gets a `meeting` event (`meetings.py:919`) | Tell the member departments (`_member_departments`) when the agenda had gone out | Fixed in `1534535` (only when the agenda was sent; run 2 sends it first) |
| code expiry (run 2) | `POST /meetings/{mid}/code` on meeting B, 7 days ahead (09/11/2026 10:00) | the code still works at the meeting | expires 03/11/2026 08:52, 12 h after it was made | Finding 2. `new_code()` sets `now + 12 h` (`meetings.py:1277`) whatever the meeting's date | Valid until at least 12 h after the meeting's start | Fixed in `60a8231` |
| card after the outcome -> board record; minutes: late concern | A Concern card on TB-2026-0012 after its decision was saved; read the board record and the minutes JSON | the concern in `divergent_opinions` | the card is accepted (200) and listed by `GET /cards`, but the record and the minutes have nothing | Finding 5. `card()` (`meetings.py:2511-2535`) stores the card in the meeting only; concerns join the record only inside `_record_decision` (`meetings.py:2409-2411`) | Amend the record with the late concern (a new version), or refuse a card once the outcome is saved | Fixed in `1534535` (`_late_concern`, a corrected version) |
| move / withdraw after the end | The owner doctor moves or withdraws Rekha, who was on the meeting of today with no outcome, after it ended | 200 | 400 `not_open` "That meeting is not open." | Finding 3 A. `_sent_case()` refuses any Case File whose meeting is `in_session` or `closed` (`meetings.py:1109-1110`); a Case File not discussed on an ended meeting can never be moved or withdrawn by its owner | Refuse only a meeting `board.running_now()` reports as running | Fixed in `1534535` |

## NOTE rows worth a decision

| Check | Got | Cause | Fix idea | Where |
|---|---|---|---|---|
| `POST /meetings` with date 06/01/2020 | 200: a meeting in the past is made (the run cancels it at once) | `board.new_session()` checks only the date's format (`board.py:69-79`, `448`); `update()` uses the same check, so a meeting can also be moved into the past | Refuse a date before today on create and on reschedule (400 "past_date") | 1.4, or 3.1 (series) |
| `POST /meetings/{mid}/end` on a planned meeting never started | 200: it is closed as if it was held (minutes with no attendance; its Case Files then hit finding 3) | `end()` checks only `_active` (`meetings.py:1414-1415`); `board.close()` refuses only a closed one (`board.py:349-351`, `863`) | 409 "Only a meeting in session can be ended. Cancel a planned meeting." | 1.4 |
| `POST /meetings/{mid}/cases/{cid}/card` while planned | 200: a card before the meeting started | `card()` uses `_active` (`meetings.py:2514`), not `_in_session` | Require `in_session` (cards follow End case) | 1.4 |
| `POST /meetings/{mid}/cases/{cid}/decision` while planned | 400 for an incomplete body, so the state was not checked: a full body would save an outcome before the meeting starts | `record_decision()` refuses only a cancelled meeting (`meetings.py:2368`) | Refuse a planned meeting (409 "Start the meeting first"); keep documenting after the end | 1.4 |
| Same route after the meeting ended | 400 for an incomplete body: an outcome can still be saved after the end | By design: `board.link_decision()` "Allowed after close: documenting" (`board.py:961-962`) | Keep; perhaps the coordinator only, and audited as "after the meeting" | decide in 1.4 |
| `GET /meetings/{mid}/cases/{cid}/slides` by an admitted member for a case NOT on the floor, and after the meeting ended | 200 both times | Only an outside expert is held to the case on the floor while in session (`api/meetings.py:421-433`, the check at 427); any admitted member reads every agenda case's slides, also after the end | Plan T2 says the meeting-scoped reads hold "only while the meeting is in session and only for the case on the floor": the new Board-view reads (2.2) must apply that to every member not on the case's team, not only outside experts. The slides route itself goes in 2.6 | 2.2 / 2.6 (`04_fold_into_rebuild.md`) |
| `POST /meetings/{mid}/questions` with 1,535 characters | 200, kept 1,000 characters | `ask()` cuts to `MAX_QUESTION` without telling (`meetings.py:1883`); chat refuses over-long text with 413 | Refuse over 1,000 with a plain message, as chat does | 1.4 (small) |
| `POST /meetings/{mid}/spotlight` with `users` not a list | 200, the spotlight is cleared | `api/meetings.py:355-356` reads anything that is not a list as `[]` | 400 when `users` is present and not a list | 1.4 (small) |
| `POST /meetings/{mid}/cancel`, then read the agenda's Case Files | Arif (moved to meeting A as Not discussed) still points at the cancelled meeting (`meeting_id`, `board_date`) | `cancel()` (`meetings.py:922-943`) tells the departments but leaves every listed Case File linked to the cancelled meeting | Move them to the next planned meeting of the board, or unlink them and tell each owner | 3.2 (agenda fills by itself) |
| Move a Case File the board moved as Not discussed (Arif) | 400 `not_sent` "Send it to the board first", also for the coordinator | `_sent_case()` needs the ready mark (`meetings.py:1107-1108`); a Case File the coordinator put on the agenda or the board moved has none | Let the coordinator move any Case File on a planned agenda (the owner still needs the ready mark) | 3.2 |
| Move Rekha, decided on the closed meeting S20261102-6708 | 400 `not_open` | Finding 3 again (`meetings.py:1109-1110`); refusing a decided Case File is defensible, but a re-discussion then needs a new Send to the board | Fixed with finding 3 in `1534535` (it will answer 200) | done in code |
| `POST /meetings/{mid}/code` on the meeting of today | expires 12.0 h after it was made | Finding 2 (above) | | done in code |
| `POST /meetings/{mid}/timer` with `pause` or `extend` | 400 `bad_action` (plain message) | The actions are `start`, `stop` and `reset`; an extension is `start` with new minutes (it worked: total 900 s) | None; the screens must keep sending `stop` | PASS rows, listed for item 1.3 |
| Agent answers (Nuclear Medicine, added by the coordinator) | A record question: "The MRI pelvis report states 'Parametria: Parametria free'" (answered, 5 to 15 s). A decision question: status `out_of_scope`, "I can't recommend or choose treatment. Treatment decisions belong to the Tumour Board. ..." | As the invariants want | None | - |
| Finding 13 (Not discussed) | Arif moved to meeting A and linked (PASS rows); the race itself cannot be reproduced by one API client | Code reading only (fixed in `1534535`) | | - |

Small wording point (not a row): every refusal by `common.need` names the internal action, for example "You do not have permission for
'session'. Ask a Tumour Board admin if you need it." (`org.py:1082`). Plain words would be "Only the MDT Coordinator can do this."

## Not checked at runtime

- Finding 8 (outside expert flags): no outside-expert login exists (`data/tumour_board/org.json` has none), so the outside-expert rows of
  `view()`, slides and chat were not called. Code reading only; fixed in `1534535`.
- Findings 1 and 13 are races (a slow hospital system, a slow reasoner call): not reproducible by one API client. Fixed in `1534535`.
- Findings 4, 6, 7, 9, 11, 12 and 14 are in the screens (item 1.3). For finding 4 the API gives both flags right: with members' questions
  off, `can.members_ask` is false and `can.ask_agents` true for the coordinator.
- The WebSocket events.

## What passed (359 rows in run 2)

- Roles: every coordinator route refuses a doctor (403); member routes refuse a waiting doctor and a doctor who never joined (403); the
  root admin is refused on every meeting route ("not placed", 403) and is the only one who reads `/scheduler/status`; a treating
  doctor cannot record a decision; the cards are for the coordinator and the owner's team only (the member doctor gets 403).
- Validation: bad dates, times, minutes (0, 121, 500), over-long titles, a body that is not JSON, unknown lists, kinds, reactions, modes,
  agents and outcomes, missing ids, a concern without a note, agree not true or false: 400 with a plain message and a code.
- State: start twice, start or edit a cancelled or closed meeting, cancel a running or closed meeting, end twice, change the date of a
  running meeting, and every live action (chat, hand, reaction, questions, timer, current, open, agents, spotlight, presenting, live
  decision, End case, cards, code, admit, send agenda, remind) on a planned or closed meeting: 409 where the code says so. The room may
  change during a meeting.
- Agenda: add (Case File links to the meeting), reorder (order kept), one agenda only (adding to today's meeting takes it off meeting A),
  a Case File not on the agenda added during the meeting reaches the floor through `/current`, its slides open and it gets an outcome.
- Move and withdraw on planned meetings: the move links the Case File (meeting, board date, `board_send`), leaves the old agenda and
  tells the coordinator (notification "agenda"); withdraw needs a reason of 3 to 500 characters, clears the meeting, records the
  withdraw; a second withdraw is refused; a move puts a withdrawn Case File back; moves to a closed, cancelled, unknown or same meeting
  and moves by other departments are refused.
- Join and waiting room: a code that is not 6 digits is refused before it counts; a wrong code 404; the right one puts doctors in the
  waiting list and admits the coordinator at once; the coordinator admits by login (any letter case); a waiting doctor sees no chat,
  questions, opened record or live decision; the old code fails after the end; the code shows only to the coordinator.
- Running: start puts the first Case File for discussion on the floor; open a record (and the member doctor not on the team may read
  that record file while it is on the shared screen, the waiting doctor may not), open the X-ray images (viewer granted to the admitted
  members), kind none; the presenter opens records, a member cannot; timer start, stop, extend, reset; questions to the board and to an
  added agent; members' questions to the agents switched off and on; listening, Present your points, stop, audio reports; hand up and
  down; spotlight (at most three; only admitted people); reactions with the 2-second gap (429); presenting with the coordinator's
  permission, the presenter taking over, stopping, the permission withdrawn; chat (empty 400, over 1,000 characters 413).
- Decision: the minimal valid body (outcome, decision text, intent, responsible clinician) is saved; a second save 409; Not discussed
  moves the Case File to the next planned meeting and the concern given before the outcome joins the record and the minutes.
- Notifications: Send agenda reaches the departments on the attendance sheet (the owner doctor, radiology and medical oncology got
  "Agenda for the Tumour Board on ...", breast surgery did not); End case asks the board heads for their cards ("card_requested" to
  radiology and medical oncology); admitting someone sends no notification (a live event only).
- Minutes, deck, export: minutes JSON and HTML (no em dash) with the decision, the not-discussed outcome, the undecided Case File and the
  attendance; a member not on any team gets every case restricted; the owner doctor gets its own Case Files in full; breast surgery and
  the root admin get 403. The deck downloads as a `.pptx` attachment for the coordinator and admitted members (403 for others). The VTB
  export downloads for Rekha (pptx), answers 409 "Compile the Case File summary first" for a file without a summary, and 403 for other
  departments and for the member doctor.
- Audit: every action of the run has its line in the activity log (all 31 kinds the script looks for, among them created, meeting_updated, agenda_lists,
  agenda_moved, agenda_withdrawn, code_issued, joined, admitted, meeting_started, opened, timer, question, chat, card, case_ended,
  outcome, meeting_ended, meeting_cancelled); the join code and the chat words are never in it.

## What the runs leave behind (synthetic only)

- TB-2026-0012 Parvathi Murugan (new, by the first run): one decision record per run ("API check decision text (synthetic, not a real
  plan)") and a late Concern card in each API-check meeting.
- TB-2026-0011 Rekha Sharma: points at the last API-check meeting of today (closed); its `board_send_history` lists the test moves and
  withdraw; a reminder per run to Gynaecologic Oncology.
- TB-2026-0010 Mohammed Arif: one "Not discussed" record per run; points at the cancelled meeting A (the cancel NOTE above).
- PACS viewing grants on Rekha's chest X-ray study for tb-mdt, tb-gynonc-doc and tb-rad-doc; agenda, card and reminder notifications
  for the demo logins.
