# 05: Phase 2 spec (the meeting shows the Case File)

Written 2 Nov 2026 before Phase 2, from the owner's decisions D1 to D6 and the technical decisions T1 and T2 (PLAN.md section 2), refined
here (logged `[DECISION]`).

## T2 refined: a meeting window instead of new read routes
`access.scope()` gains one more way to READ (the read-only scope the doctor's "open with a reason" window already uses): a login that is
**admitted** (`present` or `remote`) to a meeting **running now** (`board.running_now`) whose **case on the floor** (`current`) is this
Case File reads it, read-only, while it stays on the floor. Not for an outside expert (they keep the identity-stripped summary of the
existing slides route, security review #9). During that window READ wins over REQUESTS (a supporting head must read the whole case at the
board; answering requests stays on the Requests page). The running sessions are looked up through a small cache (a second or two) so
`scope()` stays cheap. Every existing read route of the Case File (the steps view, documents, pages, the staging view, the summary, the
Case summary) then works for the board as it is; exports stay refused for READ as today. Tests: admitted member reads the current case,
not another case on the agenda, not after Next, not after the meeting ends, not while waiting, not an outside expert; REQUESTS becomes
READ only during the window; the coordinator and the owner are unchanged.

## T1: the follow state
- The meeting record keeps `view = {case_id, tab, doc_id, page, quote, opened, by, by_name, at}`; `tab` is `summary`, `reports`,
  `images` or `stage`. `GET /meetings/{mid}` returns it; the socket sends `{"type": "view", "view": {...}}` on every change.
- `POST /meetings/{mid}/view {tab, doc_id?, page?, quote?}`: by the coordinator (manage) or by the presenter of the case on the floor
  (`presenter_of(case) == user`, admitted). Checks: in session; a case on the floor; `tab` one of the four; `doc_id` a document of that
  case; `page` a whole number from 0; `quote` at most 300 characters. `tab == "images"` with a `doc_id` reuses `open_item(kind="images")`
  (the PACS grants for the admitted members) and puts the viewer url in `view.opened`; a report puts `opened` as `open_item(kind="record")`
  does. Rate limited like the other live routes. Audited as `view` (tab, doc_id; never the quote text).
- `set_current` (Next, Previous, a click on the agenda) resets `view` to `{case_id: new, tab: "summary"}`. The old `current.slide` and
  `live.opened` stay readable for the old screens until 2.6 removes them.

## The Board view (D3)
A read-only component `features/meetings/board/BoardView.tsx` for one Case File, made of the existing Case File pieces:
- **Summary:** the case header line (patient, age and sex, cancer and setting, presenter, urgency), the question for the board in large
  type, then the Case summary when there is one ("Summary after the board") else the pre-board summary ("Summary before the board"),
  every sentence with its source chip (the "not signed" mark kept); the stage as written in the reports, and a draft stage only when a
  doctor confirmed it.
- **Reports:** the documents grouped by type (the Reports step's read mode): click opens the report page in the view, the quoted line
  highlighted (the Case File's SourceViewer, not a side panel).
- **Images:** the imaging reports with images; opening one shows the PACS viewer in the view (the existing viewing grant).
- **Stage and values:** the key values with their source chips (the glance) and the staging card read-only.
Large type for a mirrored projector: base text at least 18 px on the laptop view; no To do, no Pre-Authorization, no editing.

## Follow and drive (D2, D4)
- The driver (coordinator, or the presenter while presenting) clicks in the Board view: each click posts `/view`; followers render the
  same tab, report, page and line from `view`. The driver's own view updates at once (optimistic), the socket confirms.
- A follower sees "Following Dr X" in the view's header. "Look around" lets a remote member click freely (local only, nothing posted);
  "Back to the room" returns to `view`. The room route (a separate projector PC) always follows.
- Remote members' phone layout: the Board view full width, tabs as chips, the call controls in the Dock.

## The coordinator's screen for a mirrored laptop (D1)
Light theme. A slim top bar (meeting, case on the floor, timer, the Record button placeholder for Phase 5), a slim agenda rail on the
left (collapsible), the Board view large in the middle, the participant strip small (above or beside), side panels (People, Chat, Agents,
Decision) on demand from the bar; the bar's buttons with words. What the room reads is the Board view; the controls stay small.

## Removing the slides (D5)
The stage tabs (`StageTabs.tsx`), `StageContent`'s slide rendering and the slide fetches go; the room summary column goes; the slide
text strings go. The `GET /meetings/{mid}/cases/{cid}/slides` route stays only for the outside expert's identity-stripped summary (and
the PDF of Phase 4 may reuse its builder); its tests are kept for that.

## Light theme (D6)
The `--color-stage*` tokens in `web/tb-nik/src/index.css` take light values (page grey-white, panels white, lines light grey, text ink,
muted grey); no `data-theme="dark"` forced in `features/meetings/**` (25 places on 2 Nov); video tiles keep a dark inner background for
the video only. Checked with axe (no serious contrast findings) on the coordinator's view, the member view, the pre-join and the room
route at 1366 and 390.
