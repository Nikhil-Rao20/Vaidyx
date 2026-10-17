# Build run log (started 18 Oct 2026, 00:xx IST)

Resume rule: after any reset, read this file, then SPEC.md, then continue the first unchecked item. Never ask the owner during this run (away until the morning of 18 Oct). Commit per finished piece as Nikhil-Rao20; never push. Update this log after every item.

Legend: [ ] to do, [~] in progress, [x] done (commit), [!] blocked or partial (reason).

## Phase 0: set-up
- [x] Node.js v24.22.0 LTS in /data/vaidyx/tools/node/current (checksum verified); npm cache /data/vaidyx/tools/node/npm-cache. Use: `export PATH=/data/vaidyx/tools/node/current/bin:$PATH`.
- [x] livekit-server v1.13.10 in /data/vaidyx/tools/livekit/v1.13.10 (checksum verified).
- [~] Code maps (backend, core, his_mock) by Explore agents into scratchpad maps/.
- [ ] SPEC.md complete (this folder).
- [ ] Commit "Build spec and run log".

## Phase 1: main app exceptions (3 small commits)
- [ ] app.py: route /tb-nik serving static/tb-nik/index.html (SPA fallback for /tb-nik/*).
- [ ] core/auth.py: admin password reset (admin_reset_password) and must_change_password flag enforced at login; TB routes to drive it.
- [ ] core/middleware.py: CSP connect-src allows ws://127.0.0.1:7880 and http://127.0.0.1:7880 (LiveKit), media-src for blob.

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
- [ ] TCIA: pick CC BY collections for breast (mammo/MR), lung (CT, PET-CT), cervix (MR/CT), colorectal (CT), oral cavity/head-neck (CT/PET), CUP (CT); licence checked, manifest written.
- [ ] Download 1 to 3 studies per demo patient; de-identify again; relabel PatientName/ID/StudyDate/Accession to our fake IDs; upload to Orthanc; credit line in OHIF/about page.
- [ ] Vaidyx link: ImagingStudy in FHIR points to the Study UID; viewer link works from Case File and from the meeting room screen.

## Phase 4: backend (tumour_board/, routes)
- [ ] Urgency tag (1 to 5, set by owner, resident proposes, audited, filters).
- [ ] Case File team: residents join by code with approval; roles; end dates; propose/approve/return queue ("ask Dr X to sign off") with alerts.
- [ ] Saved shared Ask chats per Case File (team), pins, stale stamp, cited page link.
- [ ] Specialty helpers: 5 briefs at ready mark, Nuclear Med on click; per-helper chat threads; Radiation Oncology default head.
- [ ] Fill-in summary slots: per-protocol template from verified facts; blanks with actions; typed values form (fixed list), AI prose at ready.
- [ ] Meeting: sessions with agenda lists (discussion/noting), order, presenter, timer, join code + waiting room, attendance, live channel (WebSocket) for current case, decision strip, follow screen, raise hand, questions; end-of-meeting member cards; outcomes incl. Noted; images open from the room.
- [ ] Notifications: in-app + browser push (localhost), digests, automatic reminders (audited as Vaidyx automatic), half-hourly re-fetch scheduler (in-process, single worker, never during a meeting).
- [ ] Admin: guided set-up (5 steps), department contacts, email logins, mailto with random password, forced change; department admin; auditor role; Settings > Activity.
- [ ] Access: break-glass for Vaidyx admin; coordinator limited; archive instead of delete; outside experts consent view; chats never to supporting doctors.
- [ ] LiveKit: config, token route (room per meeting), localhost server start script.
- [ ] CUP protocol (draft, needs doctor approval) + demo patients to ~25 incl. CUP.
- [ ] Published cases: search (local library + PubMed/Europe PMC), doctor picks, labelled.
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
