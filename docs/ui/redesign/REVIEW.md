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

## 19 Oct, evening: the landing page and the entrance

| # | Where | What to look at | Your note it answers |
|---|---|---|---|
| 14 | http://localhost:7000/tb-nik (signed out or in) | the public landing page: the mark gathers from points, the title, "How it works" with a screen that changes as you scroll, "Every fact has its source" with the lines from each value to its line in the report, roles, "What Vaidyx will never do", the team (placeholders), TANUH, the close. Smooth scrolling; the top bar hides while you scroll down. Try it on the phone (F12, Ctrl+Shift+M, Pixel 7): the menu, every section. | "a landing page, informative, creative, professional; inspiration from dpi.tanuh.ai and project-monai.github.io; brand TANUH too" |
| 15 | Sign in, then watch | the cinematic entrance: the official Vaidyx reveal (brand/animation.html), the name "Tumour Board", then the mark glides into its place in the top bar. About 5.5 s, click or Escape to skip. Light and dark. | "the vaidyx chat animation after sign-in is better; a cinematic entrance for a while" |

Words to check (all in one file, `web/tb-nik/src/features/landing/content.ts`): the titles, the three "why" statements, the steps, the scope line, the six principles, the TANUH paragraph. The team cards are placeholders until you send names, roles and photos (`public/brand/team/`).
Proof: `docs/ui/build/shots/landing-*.png` (hero at 1366 / 1920 / 390, the whole page, the phone menu) and `splash-*.png` (five frames, light, dark, phone); 55 mock checks pass.

## 19 Oct, night: round 2 of the public site (your notes)

| # | Where | What changed | Your note it answers |
|---|---|---|---|
| 16 | http://localhost:7000/tb-nik, every load | the site's own entrance: the mark, then the wordmark, about 3 s, click to skip; then the hero's mark gathers from the four corners of the screen | "the website entrance should have a logo and name animation"; "the logo comes from every corner and forms" |
| 17 | Top bar | pages, not sections: Product (default), Docs (in preparation), About (team, TANUH), Contact | "items in the nav bar should be separate pages" |
| 18 | Every sentence | rewritten in a formal register for clinicians and academic readers; all in `content.ts` | "the English should be professional, on the point" |
| 19 | How it works, During | the room display shows a designed case summary slide (deck style) instead of the CT placeholder | "a PPT slide, design one slide" |
| 20 | Traceability | after the values, "Ask the Case File": the question is typed, the answer appears sentence by sentence, each sentence linked to its report line | "show how asking questions works" |
| 21 | Clinical safety | positive wording (what Vaidyx does), the statement removed, the six boxes kept with an index | "write what Vaidyx does, not what it does not" |
| 22 | Contact | your address with the fixed subject "[Vaidyx] Website enquiry", a copy button and an enquiry form that composes the email | "design the contact with my email, fixed subject" |
| 23 | Hero | the floating record chips removed | "remove those boxes" |

## 20 Oct: round 3 of the public site (your notes)

| # | Where | What changed | Your note it answers |
|---|---|---|---|
| 24 | Every title and lead | plain everyday English ("Every patient ready for the Tumour Board", "Most of the work happens before the meeting") | "make the titles simple" |
| 25 | The whole site | light theme by default, dark theme on the switch in the top bar (the same switch as the app); the hero too | "make all the website light theme, with light and dark" |
| 26 | /tb-nik, every visit | the logo and name reveal plays each time the Product page is opened (about 3 s, click to skip), then the hero's mark gathers from the corners | "the entrance animation every time users enter" |
| 27 | Traceability | two boxes: the report on the left, Ask the Case File on the right; the question is typed, lines run to the report lines, the answer arrives sentence by sentence; the values card and the three points are gone | "remove extracted values; typewriter first, then connect, then the answer" |
| 28 | Roles | a table: six seats around the Case File, each with its own badge; a seat lights its connector and shows its card; the seats take turns until you choose | "typical UI; make our own, graphic, interactive" |
| 29 | Safety | six principles on the left, a drawing of the chosen one on the right (draft to reviewed, value to its line, scans for doctors, on-site server, India first, the audit log) | "the same for clinical safety" |
| 30 | About | "Meet our team", the six portraits with name only, the TANUH box with one button, Visit TANUH | "meet our team; photo and name; visit TANUH" |
| 31 | Contact | the enquiry form only; it posts to the site's own endpoint, which stores the enquiry and emails it when SMTP is set up; the direct address under the form | "only the enquiry; make the sending work" |

Email sending needs one file from you, `data/tumour_board/site_mail.json` (never committed): `{"host": "smtp...", "port": 587, "username": "...", "password": "...", "from": "...", "to": "sulake.nikhileswararao@tanuh.ai", "starttls": true}`. Until then every enquiry is saved in `data/tumour_board/enquiries/` and the visitor sees "received".

## 20 Oct: the problem section, three ways (design lab)

Open http://localhost:7000/tb-nik/lab: the same content (your three items, the observed-context note, the three national figures with the Sarveswaran et al. 2026 link) in three layouts. Option B (bento tiles, gauges, the tinted tile) is on the product page now; A (ledger) and C (flow) wait for your choice. Two of the three figures are derived from the paper rather than stated in it: 88.3 % is 63.5 % physical plus 24.8 % mixed records; 53.3 % is the complement of 46.7 % radiologist participation; 48.2 % is stated.
