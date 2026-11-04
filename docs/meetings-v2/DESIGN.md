# Meetings v2: the owner's decisions (2 Nov 2026)

Why: the radiologist and the owner want the meeting to be the MDT Coordinator running Vaidyx itself, not slides. Every report already
opens well in Vaidyx, so the board looks at the Case File. Doctors work in a light theme.

## Decisions (owner's answers, 2 Nov 2026)

| # | Topic | Decision |
|---|---|---|
| 1 | Room set-up | The coordinator's laptop is mirrored to the projector: one view, no separate room screen needed |
| 2 | How a case is shown | Follow the coordinator: the room and every remote member render the real Case File live (same tab, report, page, highlighted line); screen share stays for anything outside Vaidyx |
| 3 | What is shown | A read-only Board view with 4 tabs: Summary (with the board question), Reports, Images, Stage and values. No To do or Pre-Authorization |
| 4 | Who drives | The coordinator, and the case's presenter while presenting. Remote members follow, may "Look around" and come "Back to the room" |
| 5 | Slides | Gone from the meeting: no slide tabs, no slide text |
| 6 | Theme | The whole meeting in the light theme |
| 7 | Scheduling | A weekly series, plus extra meetings when needed (2 or 3 a week); during a meeting the coordinator can take up any Case File that was not on the agenda |
| 8 | Agenda | Filled by itself from the Case Files sent to the board, by urgency; the coordinator reorders, moves or removes |
| 9 | Planning screen | One page: when and where, the case list, members and join code made by themselves, Send agenda, Start; advanced options under More |
| 10 | PowerPoint | Replaced by a PDF of the meeting (cases, board questions, decisions, minutes) |
| 11 | Recorder | The coordinator presses Record. No audio is ever saved: speech becomes text live, in memory |
| 12 | What is kept | AI notes of what happened, per case, labelled "AI draft, not reviewed"; each note line has a "said" chip with the exact words and the speaker; the transcript is kept only behind the notes, never shown whole |
| 13 | Who reads the notes | Every member of that meeting |
| 14 | After the board | The prof's ask: a Case File summary after the meeting with the decisions in it, beside the summary before the meeting. The Case summary (night-v3 3.3) already does this; it also takes the meeting notes and is labelled clearly as the summary after the board |

## Order of work (owner's choice)

1. Check every meeting feature, high and low level; one bug table; the owner picks the fixes.
2. Light theme; the Board view that follows the coordinator; slides removed.
3. One-page planning, the weekly series, extra meetings, unplanned cases during a meeting.
4. The meeting PDF instead of the PowerPoint.
5. The Record button and the AI notes; the summary after the board takes them.

## Rules kept

Synthetic patients only in tests. No model reads an image. The AI notes summarise what people said, quoted and verified against the
transcript; they never decide or advise, and the decision is still typed by people. No audio on disk. One commit per finished piece as
Nikhil-Rao20 on `the-ui`; never pushed.
