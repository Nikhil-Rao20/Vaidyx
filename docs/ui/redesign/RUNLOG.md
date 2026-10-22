# Redesign run log (resume from here)
| When | Phase | Done | Next |
|---|---|---|---|
| 19 Oct 00:10 | R0 | plan written | fonts, tokens, brand, shell |
| 19 Oct 00:55 | R0 | committed a4c45c4: Inter, tokens, brand, splash, nav Case Files + Meetings, floating Dock, sign-in | R1 |
| 19 Oct 01:40 | R1 | built (uncommitted): lib/search (any-part id match, server + client + Ctrl+K), ViewsBar, FilterPanel, Calendar/DateInput/TimeInput, CaseRow, CaseFileList, CaseFileHome (Join with a code), PatientLine; server ids/accessions + test | review filter/search shots, commit, then R2 Case File |
| 19 Oct 02:50 | R1 | committed 7329bf6 | |
| 19 Oct 03:05 | R2 | committed 0f3ae72 (Board brief, folded records, helper badges, sentence-case titles) | |
| 19 Oct 03:40 | R3 | built (uncommitted): lib/video (pre-join choice, room identity), Stage.tsx, VideoTiles (tiles), PreJoin, People, MemberViewPage, MeetingRoomPage, ControlView (conduct), agenda ack toast, TimeInput on new meeting; backend video-token {screen: room} | shots review, meetings.spec fixes, commit; then R4 deck |
| 19 Oct 04:30 | R3 | committed 6b4aa16 (stage, tiles, pre-join, conduct panel, room screen) | |
| 19 Oct 05:20 | R4 | built (uncommitted): tumour_board/deck (python-pptx design, assets), api/deck.py (meeting + case decks, hospital logo upload), tests 4/4, LogoUpload in set-up, Download menu on the Case File, Deck button on the meeting page; LibreOffice portable at /data/vaidyx/tools/libreoffice for rendering (deck/render.py); docs DECK.md | set-up shot, full suite, commit, restart :7000; then R5 |
| 19 Oct 06:10 | R4 | committed fafaae5; :7000 restarted | |
| 19 Oct 06:40 | R5 | committed (ring, phone conduct, live video check passed: live-*.png) | R6: REVIEW.md for the owner, final suites, memory |
| 19 Oct 07:00 | R6 | REVIEW.md written; ring fallback; committed; :7000 restarted with the final build | owner's review; parked: eslint has no v9 config (lint not run) |

## 19 Oct, evening: landing page + cinematic entrance
- Entrance (components/Splash.tsx): the brand's own reveal ported as CSS (components/brand-reveal.css, BrandReveal.tsx, path data generated into brand-paths.ts from brand/animation.html); speed 1.35; tagline at 3.2 s; at 5.0 s the mark flies to the top bar's icon (`data-brand-anchor` on the Wordmark icon) while the field fades. Bug found on the way: the sessionStorage flag was consumed inside a useState initializer, and a first render that suspends (lazy page chunk) is thrown away, so the splash never showed after a cold load; the flag is now read in the initializer and cleared in an effect.
- Landing (features/landing): own palette in landing.css (ink, the logo's teal/cyan/mint, the wordmark's violet, paper sections), Instrument Serif (OFL, self-hosted) for one accent word per title, Lenis smooth scroll (MIT) only on this page, a 2D-canvas particle mark (points sampled from the icon paths, perspective, pointer lean, scroll disperse), scroll-driven scenes, source lines drawn in SVG, tilt cards, word-by-word scope statement, magnetic buttons. Every word in content.ts. Synthetic data only.
- Gotchas: element rules in a page stylesheet must sit in `@layer base`, or they beat Tailwind's utilities (unlayered > layered); `.l-float` must not be absolute inside its positioned wrapper; `whileInView` never fires in a full-page screenshot, so reduced motion renders the finished state (paths at full length).
- Checks: tsc, vite build, 55 mock checks (new: landing.spec.ts, splash.spec.ts), live hero captured from :7000.

## 19 Oct, night: public site round 2
- Owner notes applied: site intro on every load (components/Intro.tsx, module flag so in-app navigation does not replay it), pages
  (routes /, /about, /docs, /contact with a shared SiteFrame and PageHead), all copy rewritten formally (content.ts), the case summary
  slide (Scenes.tsx SlideCase, cqw-sized, flex layout after an absolute first cut overlapped), the Ask the Case File sequence
  (Sources.tsx: a step machine, typing, sentence lines in violet, hover pins a value), Clinical safety positive, Contact page with
  mailto and a fixed subject, hero chips removed, particles start at the four screen corners with a curved flight.
- Checks: tsc, vite build, landing.spec (product, about/docs/contact, signed in), live captures of the intro, the slide and the Ask
  sequence from :7000 (scratch script with Playwright, scrolling to the phase).

## 20 Oct: public site round 3
- Theme tokens: landing.css now defines --l-* for light (default) and dark under [data-theme="dark"]; no section names a colour.
  ParticleMark repaints on the theme attribute. The device frames in "How it works" stay dark in both themes.
- Words (titles) observed the clipped, translated word spans, which never intersect the viewport: live titles never appeared.
  The wrapper is observed now (useInView) and the words animate from state.
- Roles table (Roles.tsx), Safety explorer (Safety.tsx + SafetyArt.tsx SVG drawings), the two-box traceability flow
  (Sources.tsx), the every-visit intro (Intro.tsx), team portraits (Team.tsx), the enquiry form (ContactPage.tsx).
- Backend: tumour_board/api/site.py (POST /tb-nik/api/enquiry, honeypot, limits, rate limit, stored under
  data/tumour_board/enquiries/), tumour_board/site_mail.py (SMTP from data/tumour_board/site_mail.json, fixed subject,
  Reply-To the sender), mounted beside /api/tb by _with_site() in routes/tumour_board_routes.py (the /tb-nik prefix is
  auth-exempt in app.py, so no app.py change). 4 tests in tumour_board/tests/test_nik_site.py.
