# The redesign, for your review (19 Oct 2026)

Branch `the-ui`, commits R0 to R5 (a4c45c4, 7329bf6, 0f3ae72, 6b4aa16, fafaae5, and R5). Nothing is pushed. The app on :7000 runs the new build. Open it as before:

```
ssh -N -L 7000:127.0.0.1:7000 -L 7130:127.0.0.1:7130 -L 7880:127.0.0.1:7880 -L 7881:127.0.0.1:7881 bharath.tangella@10.16.63.43
```
then http://localhost:7000/tb-nik (the HIMS stays at http://localhost:7130/his).

## What to look at, in order
| # | Where | What changed | Your note it answers |
|---|---|---|---|
| 1 | Sign in | the real Vaidyx mark and wordmark, a brand panel, the splash after sign-in (click to skip) | branding, animation |
| 2 | Top bar | **Case Files** and **Meetings** only (plus People / Admin / Activity by role); the pill glides | "Home and Case Files are the same" |
| 3 | Case Files | views with counts (All, Mine, Needs me, Waiting, Ready, On the agenda, Decided, your saved views), **one Filter panel** (several values at once, tokens for what is on), sort, **Join with a code** next to New Case File | filters, join buttons |
| 4 | Search (the list and Ctrl+K) | type any part: `4327`, `vxh`, `VXH/26/4327`, an OP number, a name; matches are marked | "search should be intelligent" |
| 5 | A row | name, age and sex, the UHID small, cancer and setting, status, what is left, board date; the owner only on others' files | "rows are too complex" |
| 6 | Kavitha's Case File | **Board brief** on top: the question, every open line in one place with its next step, the summary with its points for review, staging as recorded; the records folded below with counts; the readiness ring; a **Download** menu (board deck, NCG template) | "important things at the top, open questions in one place" |
| 7 | Specialty helpers | press Prepare, close the panel: the button pulses while it runs, shows a count when ready, a toast tells you | "prepare in the background, 1, 2, 3" |
| 8 | New meeting | our own calendar and time picker, anchored to the field | "the calendar opens top left" |
| 9 | Agenda | adding a Case File confirms in a toast | "no acknowledgement" |
| 10 | The meeting | a stage like Google Meet: pre-join (see your camera), tiles with the camera or initials, a speaking ring, hands, panels for people and questions, the round control bar; the coordinator's conduct panel (Share, Decision, People with Admit, Questions, Agenda); the room screen with the room's own camera and microphone | "like Meet or Zoom, videos and mic talking" |
| 11 | Deck | on a Case File: Download, Board deck; on a meeting: Deck (with minutes once closed). Cover with the hospital logo and the Vaidyx mark | "a very good PPT" |
| 12 | Admin, Hospital step | upload the hospital's logo (PNG or JPEG) | the deck's logo |
| 13 | Phone (F12, Ctrl+Shift+M, Pixel 7) | the floating Dock, the list, the Case File, the meeting | laptop first, phone works |

## Proof it works
- `docs/ui/build/shots/`: 50 screenshot checks of every page, laptop and phone, light and dark (`npx playwright test -c e2e/playwright.config.ts`, mock mode).
- `docs/ui/build/shots/live-*.png`: two real logins in one live meeting with video (`e2e/live/video.spec.ts`): the member view, the conduct view and the room screen each show the other's camera.
- Tests: 2558 Tumour Board (4 new for the deck, 1 for the search), 387 HIMS; the website type-checks and builds.

## Left for you to decide
- The hospital's real logo: upload it in Admin, Hospital (the demo emblem is synthetic).
- The deck design is ours; the NCG VTB template export stays as before.
- Finding 22 (old data files tracked in git), the broken admin password file, a human face-check of the cropped scans, a doctor's approval of the CUP and generic checklists: as listed on 18 Oct.
