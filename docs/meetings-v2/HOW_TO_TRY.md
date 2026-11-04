# Meetings v2: how to try it

Everything here runs on the internal app (open `http://localhost:7000/tb-nik` through your usual SSH tunnel:
`ssh -N -L 7000:127.0.0.1:7000 -L 7130:127.0.0.1:7130 -L 7880:127.0.0.1:7880 -L 7881:127.0.0.1:7881 bharath.tangella@10.16.63.43`).
Logins by username (passwords in `~/vaidyx/.tb_v2_demo_logins`): `tb-mdt` (MDT Coordinator), `tb-gynonc-doc` (Gynaecologic Oncology
consultant), `tb-rad-doc` (Radiology), `tb-path-head` (Pathology head). Test patients (synthetic): Rekha Sharma `TB-2026-0011`
(cervix), Mohammed Arif `TB-2026-0010` (oral cavity), Parvathi Murugan `TB-2026-0012` (cervix). Use a normal and a private window when
two people are needed. Everything is in the light theme.

## 1. Plan a Tumour Board (the MDT Coordinator)
1. Sign in as `tb-mdt`, open Meetings, press **Plan a Tumour Board**. Choose **Every week** (weekday, time, room) or **Once** (an extra
   meeting). The planner opens: one page.
2. On the planner: edit the date, time and room in place (the pencil); "Every week on ..." with **Change the series** (pause, stop).
   The case lists fill themselves from the Case Files sent to the board, by urgency; drag a row or use Up and Down (the list then says
   "In your order"; new Case Files arrive at the end marked New; **Put back in urgency order** undoes it). Move a case to another
   meeting, Remove it with a reason, or **Add a Case File**.
3. The join code and the members are made by themselves (side). **Send agenda**; **Download the agenda (PDF)**; **More**: minutes per
   case, video, Cancel this meeting (it says where its Case Files go).
4. **Start meeting** is on when a case is listed and it is the day.

## 2. Run the meeting: the Case File on screen, not slides
1. Start the meeting. The coordinator's laptop (mirrored to the projector) shows the **Board view** of the case on the floor, large:
   Summary (the question for the board first), Reports, Images, Stage and values. "You lead: everyone follows what you open."
2. Open a report in Reports: it opens inside the Board view at its page with the quoted line boxed. Every member's screen follows.
3. In a private window sign in as `tb-rad-doc`, Meetings, join with the code (the coordinator admits from People, where the join code
   and New code are shown during the meeting). The doctor sees "Following MDT Coordinator"; **Look around** lets them click freely;
   **Back to the room** follows again. The presenter (the treating doctor) may lead while presenting.
4. The room route (More, Room screen) for a separate projector computer always follows.
5. **Take up another Case File** (agenda rail or More): search any Case File, it is added as taken up and put on the floor.
6. Chat, People, Agents and Decision are on the bar with words; the AI agents stand in for absent heads as before.

## 3. The recorder (text only, no audio kept)
1. As the coordinator press **Record** in the top bar. Every screen shows "Recording: text only, no audio kept"; the join page says so.
2. Speak (the laptop microphone is "Board room"; each remote member is recorded under their own name when the video call is on).
   Pause, Resume, Stop (it asks first). Nothing is kept as audio: the speech becomes text on the server and the audio is dropped.
3. **End case**: Vaidyx writes the **Discussion notes** of that case (AI draft, not reviewed): each line says who said what, with a
   **said** chip showing the exact words, the speaker and the time. The coordinator can edit a line and mark the notes reviewed; every
   member of the meeting can read them (More, Discussion notes).

## 4. After the board
1. Open the Case File (e.g. Rekha `TB-2026-0011` as `tb-gynonc-doc`), Summary: **Summary after the board** (with the decision, the
   actions and a section "What was said at the board" from the notes, every sentence with its speaker's exact words) and, one click
   away, **Summary before the board**. The discussion notes are listed under it.
2. The meeting page after the meeting: **Download the meeting record (PDF)** (cover, attendance with the agents labelled, one page per
   Case File with the question, the decision, actions, concerns and the discussion notes, the minutes). The Case File's More menu has
   **Board record (PDF)**. The PowerPoint deck is gone.

## 5. What to look at on Rekha (TB-2026-0011)
Meeting S20261102-01fa (ended) has her recorder evaluation: six transcript segments from a synthetic discussion voiced by Kokoro and six
discussion notes; her decision there is "Deferred until the signed biopsy report is available (synthetic evaluation)". Her Summary
after the board carries them.

## 6. Checks and tools
- Unit suite: `/data/vaidyx/venv/app/bin/python -m pytest -q -p no:cacheprovider tumour_board/tests his_mock/tests --deselect tumour_board/tests/test_agents_live.py`
- Website: `cd web/tb-nik && export PATH=/data/vaidyx/tools/node/current/bin:$PATH && npx tsc -b --noEmit && npx vite build`; mocked
  screens `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts`; the two-person live
  test `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_LIVE_CASE=TB-2026-0011 npx playwright test -c e2e/live/playwright.live.config.ts`
- `docs/meetings-v2/tools/api_check.mjs` (every meeting route by role and state), `eval_recorder.mjs` (the recorder and notes with the
  real models), `live_capture.mjs` (the browser capture). Leave 15 minutes between runs that join meetings (the join limit).
- Limits: the public demo link was not changed by this work (publish only on your word); a real iPhone or Android browser was not
  tested; in-room speakers share one name ("Board room") because one laptop microphone hears them all.
