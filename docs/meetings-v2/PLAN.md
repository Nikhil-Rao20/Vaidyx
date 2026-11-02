# Meetings v2: the plan for the unattended run (from 2 Nov 2026)

Source of truth for the run. Branch `the-ui`. Commits `M2-<ID>: <title>` as Nikhil-Rao20 (CLAUDE.md "Git"). Never push. The log is
[LOG.md](LOG.md); how the run is organised is [ORCHESTRATION.md](ORCHESTRATION.md); the owner's answers are [DESIGN.md](DESIGN.md).

## 1. Why

The owner (Nikhil-Rao20) and his radiologist want the Tumour Board meeting to be the MDT Coordinator running Vaidyx itself: the Case
File on screen, not slides. Every report already opens well in Vaidyx. Doctors work in a light theme. The coordinator plans meetings on
one simple page, a weekly board plus extra meetings. A recorder that keeps no audio writes notes of what was said. After the board, the
Case File carries a summary with the decision in it (the prof's ask). Before building, every existing meeting feature is checked high
and low level and the bugs are fixed.

## 2. Owner decisions (2 Nov 2026; never re-ask)

Free hand (owner, 2 Nov ~20:30): "you have my freehand, dont wait for my any input ... complete everything ... strictly dont wait for my
decision anywhere ... take decisions carefully". So: decide with the rules below, the safer option when unsure, log `[DECISION]`.
Bugs found in Phase 1 are fixed without asking (this replaces his earlier "list first"). Still never push, never touch the public demo.

| # | Decision |
|---|---|
| D1 | Room set-up: the coordinator's laptop is MIRRORED to the projector. The coordinator's screen is what the room sees: one view, clean and big enough to read from the back of the room. A separate room-screen route may stay for a hospital that drives the projector from another PC, showing the same follower view |
| D2 | Follow the coordinator: the room and every remote member render the real Case File live (same tab, same report, same page, the quoted line highlighted). Screen share stays for anything outside Vaidyx |
| D3 | Board view, read-only, 4 tabs: Summary (the question for the board first, then the summary), Reports (open any report at its page), Images (the PACS viewer), Stage and values. No To do, no Pre-Authorization |
| D4 | Who drives: the coordinator, and the case's presenter while presenting. Remote members follow; they may "Look around" on their own and press "Back to the room" |
| D5 | No slides and no slide text anywhere in the meeting ("from now on these slides and text are no need") |
| D6 | The whole meeting (pre-join, call, member view, room route, agenda page) in the LIGHT theme ("doctors are not dark theme guys") |
| D7 | Scheduling: a weekly series is the usual case; extra one-off meetings happen (2 or 3 a week); during a meeting the coordinator can take up any Case File that was not on the agenda |
| D8 | Agenda filled by itself from the Case Files sent to the board, ordered by urgency (5 first); the coordinator reorders, moves to another date or removes |
| D9 | One-page planning for the coordinator: when and where at the top, the case list below, members and the join code made by themselves, one Send agenda, one Start; advanced options (minutes per case, video) under More |
| D10 | The PowerPoint deck is replaced by a PDF of the meeting: the cases, their board questions, the decisions and the minutes |
| D11 | Recorder: the coordinator presses Record (nothing runs before). NO AUDIO IS EVER SAVED: speech becomes text live, in memory |
| D12 | Kept: AI notes per case of what happened, labelled "AI draft, not reviewed"; every note line has a "said" chip showing the exact words and the speaker; the transcript text is kept only behind the notes, never shown as a whole |
| D13 | Every member of that meeting may read its notes |
| D14 | The prof's ask: beside the summary before the meeting, a Case File summary AFTER the meeting with the decisions in it. The Case summary (night-v3 3.3) does this; it is labelled "Summary after the board" and also cites the meeting notes |

### Technical decisions taken for the owner (2 Nov, by the session that wrote this plan; the run may refine them with a `[DECISION]`)

| # | Decision | Why |
|---|---|---|
| T1 | The follow state lives in the meeting record: `view = {case_id, tab, doc_id, page, quote, by, at}`, set by the driver through one new route and sent over the meeting socket; followers render the Board view from it. It replaces `current.slide`, `open` and the slide routes in the screens | One source of truth, sharp text, no video of text |
| T2 | Members who are not on a Case File's team read it during the meeting through meeting-scoped read routes (the Board view data and the report pages), allowed only while the meeting is in session and only for the case on the floor (the rule the slides route already had). An outside expert without the patient's consent sees the Summary and values with the identity stripped and no report pages (security review #9) | Keeps today's access rules |
| T3 | The recorder runs in the coordinator's browser (the laptop is in the room and in the call): one MediaRecorder per audio track (the laptop microphone is "Board room"; each remote member's track is that member), chunks of about 20 s posted to the app, transcribed by the existing audio service (Whisper large-v3-turbo, fp16, English, in memory, 60 s and 4 MiB caps) and dropped. Only the text is stored, with the speaker, the time and the case on the floor | No new server install; per-speaker names for remote members |
| T4 | The transcript lives under the meeting's data folder (mode 600), never served as a whole; the notes are written by the reasoner (Gemma-4-31B, non-medical) when a case ends (and on demand), every line verified word for word against the transcript (dropped if not), attributed to the speaker, never advice in Vaidyx's own voice | The verified-quote rule |
| T5 | Meeting PDF made with WeasyPrint (already on the server in the pdf venv, run as a separate process like `make_corpus.py`) from an HTML template; the `.pptx` routes and buttons are removed | No new install |
| T6 | A weekly series is stored with the meetings; the next four weeks of meetings are made ahead by the scheduler; skipping or moving one date touches only that meeting | Simple, predictable |

## 3. Rules every item keeps

Everything in CLAUDE.md "Invariants". Do not break what works: every existing test passes unless an item replaces the feature (then the
test changes with it, said in the commit). New screens use the existing components and tokens, plain words, no em dashes, DD/MM/YYYY,
laptop (1366) and phone (390) both checked with real screenshots (Playwright, light theme; dark only where a page already offers it).
Synthetic patients only (the spare demo patients Rekha Sharma TB-2026-0011 and Mohammed Arif TB-2026-0010 are test files; more spare
patients in the demo hospital: VXH/26/004209 Parvathi Murugan cervix, VXH/26/004217 Ravi Shankar Pandey rectum). Never the real case.
Never print a password. Never touch the public demo (:7100, :7101, the tunnel, `~/vaidyx/public_demo/`).

## 4. Phases and items

Status: `todo`, `doing`, `done (<hash>)`, `blocked (<reason>)`.

### Phase 1: check every meeting feature, then fix

| ID | Item | Status |
|---|---|---|
| 1.1 | The code review of the meeting code (done by a reviewer agent on 2 Nov before the run; findings in `research/01_code_review.md`): verify each finding against the code, mark confirmed or not | todo |
| 1.2 | API check script `docs/meetings-v2/tools/api_check.mjs`: every meeting route by role (coordinator tb-mdt, presenter tb-gynonc-doc, member tb-rad-doc, a doctor not in the meeting, the root admin) and by state (planned, in session, closed, cancelled) on a throw-away synthetic meeting: status codes, validation, permissions, state changes, the audit line, the notifications; a case added during the meeting; move and withdraw; one decision per case; minutes; findings to `research/02_api_check.md` | doing |
| 1.3 | Screen journeys script `docs/meetings-v2/tools/journeys.mjs` (real app, real LiveKit, Chromium fake devices): the coordinator plans, fills the agenda, sends it, makes a code, starts, puts a case on the floor, opens a report and images, uses every bar button and panel (people, chat, agenda, case, agents, decision), takes up an unplanned case, ends a case and the meeting, reads the minutes; a member joins with the code, waits, is admitted, chats, raises a hand, reacts, asks an agent, gives a card; phone layout; offline and back; findings with screenshots to `research/03_journeys.md` | todo |
| 1.4 | Fix every confirmed bug of 1.1 to 1.3 that the later phases do not replace (one commit per fix or per small group, with a test); bugs in screens that Phase 2 or 3 rebuild are listed in `research/04_fold_into_rebuild.md` and fixed there. Also the empty "()" in the identity warning when a report has no date (`tumour_board/steps.py`) | todo |
| 1.5 | Phase gate and review | todo |

### Phase 2: the meeting shows the Case File (light theme, Board view, following, no slides)

| ID | Item | Status |
|---|---|---|
| 2.1 | Light theme for the whole meeting: the stage tokens get light values; no forced dark on the call, pre-join, member view, room route and agenda page; checked for contrast (axe) | todo |
| 2.2 | Backend: the follow state (T1) and the meeting-scoped read routes for the Board view data and report pages (T2), with permission and state tests; the outside expert rule | todo |
| 2.3 | The Board view component (D3): Summary (board question, summary or Case summary, stage as written and a confirmed draft stage), Reports (grouped list, opens the report page with the line highlighted, "not signed" marks kept), Images (the existing PACS viewing grant), Stage and values (key values with source chips); built from the existing Case File pieces, read-only | todo |
| 2.4 | Follow and drive (D2, D4): the coordinator's view drives; the presenter may take over while presenting; followers render it live; "Look around" and "Back to the room"; the driver's name shown ("Following Dr X") | todo |
| 2.5 | The coordinator's meeting screen for a mirrored laptop (D1): the Board view large in the middle, a slim agenda rail, a slim top bar (meeting, case, timer, the Record button placeholder), side panels on demand; readable from across a room; the member view and phone layout follow | todo |
| 2.6 | Remove the slides (D5): the stage tabs, the slide routes in the screens, the slide text; tests changed with them | todo |
| 2.7 | Phase gate and review (with the two-person live test `e2e/live/video.spec.ts` updated to the new screens) | todo |

### Phase 3: planning (one page, weekly series, extra meetings, unplanned cases)

| ID | Item | Status |
|---|---|---|
| 3.1 | Backend: weekly series (T6): create, edit, pause, skip or move one date; the scheduler makes the next four weeks; one-off extra meetings stay | todo |
| 3.2 | Backend: the agenda fills by itself (D8): a Case File sent to the board goes to the next planned meeting of its board, ordered by urgency; reorder, move, remove; the treating doctor and the coordinator told | todo |
| 3.3 | The one-page planner (D9) replacing the New meeting dialog and the agenda page: when and where (edit in place), the case list with drag to reorder, move, remove, add; members and the join code made by themselves; Send agenda; Start; More (minutes per case, video); "Plan a Tumour Board": once or every week | todo |
| 3.4 | During the meeting, take up any Case File (D7): a "Take up another Case File" search for the coordinator, added to the meeting as unplanned and put on the floor; shown in the minutes as taken up during the meeting | todo |
| 3.5 | Phase gate and review | todo |

### Phase 4: the meeting PDF instead of the PowerPoint

| ID | Item | Status |
|---|---|---|
| 4.1 | The meeting PDF (D10, T5): cover, the cases with board questions, decisions and actions, the minutes, the notes when Phase 5 is done (added then); download from the meeting page; one-Case-File PDF from the Case File's board record | todo |
| 4.2 | Remove the `.pptx` deck (routes, buttons, tests; the module if nothing else uses it) | todo |
| 4.3 | Phase gate and review | todo |

### Phase 5: the recorder and the AI notes; the summary after the board

| ID | Item | Status |
|---|---|---|
| 5.1 | Backend: recording state per meeting (off, on, paused; coordinator only; audited); the chunk route (audio in memory to the audio service, never written to disk, size and rate caps); the transcript store (text, speaker, time, case) never served whole (T3, T4) | todo |
| 5.2 | Frontend: the Record button (coordinator), the red "Recording: text only, no audio kept" badge on every screen, the notice on the join page while recording, pause and stop; per-track capture in the coordinator's browser (T3); a clear state when the tab closes | todo |
| 5.3 | The AI notes per case (D12, T4): written when a case ends and on demand; every line with its "said" chip (exact words, speaker, time); "AI draft, not reviewed"; the coordinator may edit a line (shown as edited) and mark them reviewed; readable by the meeting's members (D13); shown on the meeting page after the meeting and on the Case File beside the board decision | todo |
| 5.4 | The summary after the board (D14): the Case summary labelled "Summary after the board" beside "Summary before the board", citing the decision, the actions and the notes (a new citation kind); the meeting PDF gets the notes | todo |
| 5.5 | An evaluation on synthetic speech: Kokoro reads a scripted synthetic board discussion as several speakers into the fake microphones; the transcript and the notes are checked (every note line verified, no advice in Vaidyx's voice, speakers right) | todo |
| 5.6 | Phase gate and review | todo |

### Phase 6: finish

| ID | Item | Status |
|---|---|---|
| 6.1 | Full regression: unit suite, mocked suite, the live two-person test, the security audit (new routes: follow, board-view reads, recorder chunks, series), real screenshots of every role in light theme | todo |
| 6.2 | `docs/meetings-v2/HOW_TO_TRY.md` (each new thing with login and steps) and the Morning summary; create `/data/vaidyx/meetings-v2/RUN_COMPLETE` | todo |
