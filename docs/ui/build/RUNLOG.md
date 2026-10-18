# Build run log (started 18 Oct 2026, 00:xx IST)

Resume rule: after any reset, read this file, then SPEC.md, then continue the first unchecked item. Never ask the owner during this run (away until the morning of 18 Oct). Commit per finished piece as Nikhil-Rao20; never push. Update this log after every item.

Legend: [ ] to do, [~] in progress, [x] done (commit), [!] blocked or partial (reason).

## Phase 0: set-up
- [x] Node.js v24.22.0 LTS in /data/vaidyx/tools/node/current (checksum verified); npm cache /data/vaidyx/tools/node/npm-cache. Use: `export PATH=/data/vaidyx/tools/node/current/bin:$PATH`.
- [x] livekit-server v1.13.10 in /data/vaidyx/tools/livekit/v1.13.10 (checksum verified).
- [x] Code maps (backend, core, his_mock) in scratchpad maps/ (backend_map.md, core_map.md, his_mock_map.md).
- [x] SPEC.md complete (this folder).
- [x] Commit "Build spec and run log".

## Phase 1: main app exceptions (3 small commits)
- [x] app.py: route /tb-nik serving static/tb-nik/index.html (SPA fallback for /tb-nik/*).
- [x] core/auth.py: admin password reset (admin_reset_password) and must_change_password flag enforced at login; TB routes to drive it.
- [x] core/middleware.py: CSP connect-src allows ws://127.0.0.1:7880 and http://127.0.0.1:7880 (LiveKit), media-src for blob.

## Phase 1b: shared pieces (done 18 Oct ~02:00)
- [x] tumour_board/api/common.py (shared guards, RateLimit, fail(), body()); routes/tumour_board_routes.py includes tumour_board.api.{me,cases_list,team,setup,slots,chats,helpers,published,meetings,live,video,push} when present; cross-site Origin check on unsafe methods for every /api/tb route.
- [x] docs/ui/build/SPEC-API.md: the contract for the new routers (paths /case-list and /case-join instead of /cases/list, /cases/join).
- [x] web/tb-nik scaffold builds (vite 8, react 18, tailwind 4, shadcn 28 components); App.tsx composes src/features/<x>/routes.tsx; session store src/lib/session.tsx; guards. Commit 12372a0.
- [~] AGENTS RUNNING (launched ~02:10, 18 Oct): H = HIMS screens (his_mock); B1 = me/cases_list/team/setup + org/access/accounts; B2 = slots/chats/helpers/published + ready hook; B3 = meetings/live/video/push/scheduler + board/notify; F1 = shell/auth/home/newcase/requests/settings/admin; F2 = Case File + meetings pages; plus TCIA plan (research) and CUP protocol (tumour_board/protocols/cup.json). When an agent reports: review, run its tests, commit its files in one or two commits as Nikhil-Rao20, tick the items below. After a context reset with agents lost: check `git status` for uncommitted work, read the files, continue the unfinished parts yourself or re-launch per the prompts in this file's spirit.

## Phase 2: demo HIMS (his_mock, :7130)
- [ ] Role logins (8 accounts, synthetic emails, session cookie, rate-limited login, CSRF on writes).
- [ ] Classic look shell (blue-grey, dense, module menu): Registration, OPD, IPD, Lab, Radiology, Pathology, Admin.
- [ ] Registration: search, new UHID, temporary registration, demographics, ABHA (sandbox), PM-JAY id.
- [ ] OPD: visit (OP No.), department/unit/consultant, OPD note, orders.
- [ ] IPD: admission (IP No.), ward/bed, transfer, referral, discharge summary.
- [ ] Lab (LIS): worklist, sample collection (barcode), result entry from test templates, verification + sign by doctor, NABL-style PDF.
- [ ] Radiology (RIS): worklist, schedule (accession, Study UID), preliminary, final signed report with Impression, link to PACS viewer.
- [ ] Pathology: specimen/block No., HPE report, IHC/molecular add-ons arriving later, sign.
- [ ] Exchange: FHIR R4 (existing) kept working; HL7 v2 message feed endpoint; events log.
- [ ] Departments aligned to the settled list (23 treating + 6 supporting).
- [ ] Tests pass (his_mock/tests) + new tests for the screens.

## Phase 3: demo PACS (:8042)
- [x] TCIA plan: 19 CC BY collections, 71 series, 4.23 GB (docs/ui/build/pacs/tcia_plan.md); [~] PACS agent phase 1 downloading + relabel library (pacs_public/).
- [ ] Download 1 to 3 studies per demo patient; de-identify again; relabel PatientName/ID/StudyDate/Accession to our fake IDs; upload to Orthanc; credit line in OHIF/about page.
- [ ] Vaidyx link: ImagingStudy in FHIR points to the Study UID; viewer link works from Case File and from the meeting room screen.

## Phase 4: backend (tumour_board/, routes)
- [x] Urgency tag (e88aff2).
- [x] Case File team, residents, join codes, proposals with 9 executors (e88aff2).
- [x] Shared Ask chats (47ee3a8).
- [x] Specialty helpers + ready hook (47ee3a8); five default heads in org (e88aff2).
- [x] Fill-in summary slots + typed values overlay in rules.py (47ee3a8).
- [ ] Meeting: sessions with agenda lists (discussion/noting), order, presenter, timer, join code + waiting room, attendance, live channel (WebSocket) for current case, decision strip, follow screen, raise hand, questions; end-of-meeting member cards; outcomes incl. Noted; images open from the room.
- [ ] Notifications: in-app + browser push (localhost), digests, automatic reminders (audited as Vaidyx automatic), half-hourly re-fetch scheduler (in-process, single worker, never during a meeting).
- [x] Guided set-up, email logins, mailto, resets, auditor, /me/activity (e88aff2).
- [x] Break-glass, archive (all routes guarded b43dde9), consent, chats visibility (e88aff2).
- [ ] LiveKit: config, token route (room per meeting), localhost server start script.
- [x] CUP protocol draft (cup.json, 23 records, 72 quotes; commit) ; [ ] demo patients to ~25 incl. CUP (HIMS fixtures).
- [x] Published cases (47ee3a8).
- [ ] Security: rate limits, CSRF, input validation, no secrets to client, audit of everything.
- [ ] Tests: pytest for every new module + role matrix tests.

## Phase 5: new website (static/tb-nik, source in web/tb-nik)
- [ ] Vite + React + TS + Tailwind + shadcn/ui + Motion scaffold; theme tokens from tb.css; fonts self-hosted; build to static/tb-nik.
- [ ] Shell: slim top bar (desktop), Dock (mobile), search, bell, profile dropdown; light/dark toggle; text size.
- [ ] Login, first login (change password, profile set-up IKEA), guided admin set-up (stepper).
- [ ] Home (treating): newest first list, filters, urgency; resident home; supporting home; coordinator home; admin home.
- [ ] New Case File flow (UHID lookup, cancer picker top 10 by group, CUP, logistics defaults).
- [ ] Case File: fill-in summary (left), Ask chat + reports (right), action ladder (in place, side panel, modal), helpers, team, board form, published cases, timeline.
- [ ] Requests / department inbox (request card), referrals.
- [ ] Meetings: list, agenda (two lists, drag), join by code, room screen (slides + summary left, images right, agent tile states, members online), coordinator control (decision strip), member card at end.
- [ ] Settings: profile, theme, text size, start page, saved filters, Activity (audit), department admin, organisation.
- [ ] States: empty, error (small picture), loading (preview filling in), button states, micro-interactions, undo slider.
- [ ] Screenshots of every page/section/state, desktop + mobile (Playwright) into docs/ui/build/shots/.

## Phase 6: integration and audit
- [ ] End-to-end real scenario: HIMS patient registered, OPD, orders, reports signed; PACS images; Vaidyx Case File created from UHID; gaps; requests; department completes; re-fetch; ready; meeting with video (LiveKit) and images opened from the room; decision; member cards; outcome sent.
- [ ] Upload the demo documents + images for one patient into HIMS/PACS and run the full pipeline (owner rule 5).
- [ ] Security audit (checklist in SPEC.md) + fixes.
- [ ] Final report for the owner: what to check, known gaps.

## Notes / decisions taken during the run
- (append here)

## Notes / decisions taken during the run (continued)
- 18 Oct ~02:30: all seven agents stopped on the API session limit (reset 01:40 IST); at 09:30 the owner said "go on continue": every agent resumed by message from where it stopped (their files on disk intact).
- 18 Oct 10:55: Fable agents hit the session limit again (reset 14:30). Owner switched the lead to Opus. Six continuation agents launched on Opus from the briefs in docs/ui/build/briefs/ (COMMON.md + H_hims, B1_accounts_team, B3_meetings_live, F1_shell_home, F2_casefile_meetings, P_pacs). B2 (slots, chats, helpers, published, ready hook) is DONE and committed (47ee3a8, test fix 440979f). CUP checklist committed (1cf6829). TCIA plan committed (a9ea0d3); 71 of 77 series downloaded (5.8 GB).
- After a reset: for any area whose agent is gone, launch a new general-purpose agent (model opus) with: "Read docs/ui/build/briefs/COMMON.md, then docs/ui/build/briefs/<brief>.md, and do everything in it; the work so far is on disk."
