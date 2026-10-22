# Brief S: fix the security review findings

Read docs/ui/build/SECURITY_REVIEW.md. Fix findings 1 to 21 (22 is the owner's decision; leave it). For each fix: the smallest change that closes the hole, a test that fails before and passes after, and set its Status to "fixed (<file>)" in SECURITY_REVIEW.md. Keep every existing behaviour the tests and the UI rely on.

Files: any in tumour_board/**, routes/tumour_board_routes.py, his_mock/**, scripts/livekit.sh, web/tb-nik/src/lib/session.tsx (finding 11 only; another builder may be editing other web files: touch only session.tsx and, if needed, src/lib/api.ts), tumour_board/eval/security_audit.py. Main app code (app.py, core/) only within the owner's exceptions: do not change core/middleware.py for finding 10 except to remove cdn.jsdelivr.net from script-src if nothing in static/tb or static/tb-nik loads scripts from it (check static/index.html and the main app's pages too: if the main app needs it, leave the CSP and fix finding 10 on the TB side with Content-Disposition attachment and a sandbox CSP header on the file route).

Notes per finding:
1. GET /cases/{id}/documents/{doc}/quote: apply the same record-in-scope rule the documents route uses for REQUESTS scope (read how GET /cases/{id}/documents/{doc} limits it).
2. A Vaidyx admin gets meeting management, board_record and read_audit only inside an open break-glass window for that Case File; meetings without a window: refused for the admin (the coordinator runs meetings). Update tests that expected the admin to manage meetings.
3 and 13. HIMS: JSON API paths accept (a) the integration token for machine callers and (b) a staff session only through the same role checks the screens use; the desk sign API takes the signer from the session (or, for token callers, the signer in the body must be a consultant of that department, as today). Use a separate write token file data/his_mock/write_token (mode 600, created by the build) for the JSON write APIs; the FHIR read token stays read only. Update tumour_board/eval/demo_v2.py and e2e_api.py to send the write token. Orthanc authentication: document in his_mock/README.md as a deployment step; do not enable it now (the proxies would need credentials).
4. POST /me/password: revoke the user's other sessions (auth_manager.revoke_user_sessions(u, except_token=current cookie token)). WebSocket: refuse when must_change_password.
5. accounts and setup: refuse coordinator, department placements and auditor on a login that is a root admin, and refuse making a placed clinical login a root admin (message: "Clinical roles and the root admin role stay on separate logins").
6. break-glass: may() inside a window allows only read actions (view, read_case, read_audit, ask).
7. /meetings/{mid}/remind: may_remind on that Case File, the meeting viewer rule, archive check.
8. archive check in agenda linking, meeting decisions, session decisions, intake file-to-case.
9. outside experts: slides only for the current case while the meeting is in session; identity fields (patient name, UHID, IP/OP numbers, dates of birth) stripped from slide content unless the owner recorded consent.
10. see above.
11. web session.tsx: on sign out clear the React Query cache (queryClient.clear via a callback or a window event the app listens to), remove tbnik.lastCase, unsubscribe push if subscribed (best effort). Server: a Tumour Board idle timeout: TB routes refuse a session idle more than 8 hours (track last-seen per token in memory in the route class; answer 401 with code "idle_timeout"); remember stays as it is.
12. HIMS module routes: 404 unless the order belongs to that module (lab, radiology, pathology); signing checks the signer's department.
14. published add/remove: the owner's consultant (residents propose).
15. helper chat: the same read rule as team chats.
16. live: re-check the session and roles every 60 s per socket and on each client message; max 5 sockets per user per meeting; throttle "state" to 1 per 2 s; send with a 2 s timeout and drop a socket that times out.
17. push endpoints: allow only https hosts of the known services (fcm.googleapis.com, updates.push.services.mozilla.com, *.notify.windows.com, web.push.apple.com).
18. department emails: reject ? & % , ; and spaces; encode the mailto address part.
19. TB JSON body cap: 1 MB for JSON bodies on /api/tb (uploads keep their own limit); display name: 2 to 80 chars, letters, spaces, dots, apostrophes, hyphens only.
20. HIMS: count failures per account and per real client address (ignore X-Forwarded-For); logout by POST (keep GET as a page with a button); drop the old session on login; add a CSP header to the screens (default-src 'self'; frame-ancestors 'self'; img-src 'self' data:).
21. livekit.sh: write config.yaml with Python reading the json (no secret on a command line); chmod 755 /data/vaidyx/tools/livekit and 600 for config.yaml.

Run `TB_SCHEDULER=0 /data/vaidyx/venv/app/bin/python -m pytest tumour_board/tests -q` and `/data/vaidyx/venv/app/bin/python -m pytest his_mock/tests pacs_public/tests -q` until green. Restart :7000 (scripts/demo_services.sh restart app, wait for /api/health) and :7130 (his_mock/serve.sh restart) at the end, then run `/data/vaidyx/venv/app/bin/python -m tumour_board.eval.security_audit --skip-login-limit` (add checks for 1, 3, 4, 13 where they can be tested without a login or with a demo login read from ~/vaidyx/.tb_v2_demo_logins without printing it).
