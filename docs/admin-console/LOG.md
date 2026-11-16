# Admin consoles: run log

- 16 Nov: audit of multi-hospital readiness done (DESIGN section 9); decisions D1-D13 taken; plan written.
- 16 Nov: backend agent 1 (Phase A) and frontend agent (Phase C) started in parallel (Opus 5.5); disjoint files: tumour_board/ + routes vs web/tb-nik/.
- 16 Nov: Phase A (A1-A6) built by backend agent 1, not committed. config: BASE_ROOT, HOSPITALS_ROOT (sibling), ContextVar,
  use_hospital / set_hospital / hospital_id / root_for / shared_root / scoped, DATA_ROOT + CASES_DIR as HospitalPath proxies,
  ScopedDict / ScopedSet for maps keyed by Case File or meeting id, strict mode TB_HOSPITAL_STRICT=1. New tumour_board/hospitals.py
  (registry, platform audit, resolve). Request hook in _ModelErrorRoute (X-TB-Hospital for Vaidyx admins only, suspended -> 403,
  unreadable registry -> 503), sockets (enter_hospital + re-check), live rooms (hospital, mid), LiveKit "tb-<hid>-<mid>" (default
  unchanged), scheduler tick_all per active hospital, resume_after_restart per hospital, four threads in copy_context, accounts and
  org.save refuse other hospitals' logins. Tests: 36 new (test_hospitals_registry / _isolation / _requests); whole suite 5,088 passed +
  the known env-only failure, same 13 skips as the committed baseline; strict-mode run (TB_HOSPITAL_STRICT=1, a second hospital registered) the same: 5,088 passed + that one failure.
- 16 Nov: frontend agent (Phase C) built C1-C3 in web/tb-nik (uncommitted): `/platform` (Overview, Hospitals, Logins, Activity, `/platform/hospitals/:id`, 3-step Add a hospital with the first password once), `/hospital` (Overview, People, Departments, Set-up, Hospital system, Activity as sub-routes, one Add a person dialog), acting-in bar with Switch hospital and Back to Vaidyx console; `X-TB-Hospital` from sessionStorage `tbnik.actingHospital` on every /api/tb request for a Vaidyx admin; nav: Vaidyx console / Hospital (replaces Admin); "Root admin" reads "Hospital admin" on screen. Mocks in e2e/support (fixtures, helpers), spec e2e/shots/consoles.spec.ts (10 tests, laptop + phone, light + dark). Backend fields the screens read beyond DESIGN 5.3 are listed in the agent's report (tile keys, his.state values, counts keys, events {ts, by, by_name, hospital, hospital_name, kind, text}).
- 16 Nov: Phase C DONE by frontend agent (not committed): /platform and /hospital consoles, acting-in bar, X-TB-Hospital header, 'Hospital admin' wording; tsc clean, mocked e2e 169 passed 0 failed; extra API fields in API_FIELDS.md. Screens reviewed (overview, add-hospital result, acting bar, people on phone): good.
- 16 Nov: review of 0966e05: fixed by orchestrator (new hospital has no HIS/PACS, env TB_HIS_* and folder roots default-only, search mkdir); sent to Phase B: /org login lists filtered per hospital, acting-hospital cookie for non-fetch requests, strict-mode socket/HTTP tests. Plausible leftovers noted: stale registry after main-app deletes, orphan login if assign fails.
- 16 Nov: Phase B built by backend agent 2 (not committed). New tumour_board/platform_admin.py (service, counts only) with
  tumour_board/api/platform.py (/platform/overview, hospitals list / create / detail / edit / status / admins add and remove, logins with
  reset-password / disable / enable, activity, acting POST / DELETE; Vaidyx admin only, ignores X-TB-Hospital and the cookie) and
  tumour_board/api/hospital_admin.py (/hospital/overview, /hospital/departments; manage_org). Create hospital: registry + folder,
  org details, first hospital admin (generated first password once as password_once + mailto, must change, registered), his.json kind
  none or, with demo_his, the demo hospital system (url / label / pacs_url / token file path copied from "default" when it points at the
  demo, never a token value). Request hook: a Vaidyx admin's unknown X-TB-Hospital (or cookie) is 404 hospital_unknown (except /platform/*
  and /me); acting hospital also from the httpOnly SameSite=Strict cookie tb_acting_hospital (header wins; sockets too); acting_in audited
  once per session and hospital. /me: platform_admin, hospital{id, name, status}, acting_hospital. /org and /org/accounts list only the
  current hospital's logins (Vaidyx admins only to a Vaidyx admin). "root admin" reads "hospital admin" in server messages. Frontend:
  session.tsx calls POST / DELETE /platform/acting (choose, back, sign-out), mock updated; tsc clean, consoles spec 10 passed.
  Tests: test_platform_api (15), test_hospital_admin_api (5), test_hospitals_acting_and_sockets (5).
  Whole suite 5,116 passed + 2 failed (the known env-only test_his_client live test; test_hospitals_isolation websocket test, a fake
  socket without cookies, fixed after in api/live.py), 13 skipped, normal and TB_HOSPITAL_STRICT=1 alike; after the fix the hospital,
  console, socket, accounts and set-up modules pass in both modes (147 passed). Expected whole suite now: 5,117 + the known failure.
- 16 Nov: Phase D: live API check 27/27 on :7400 (test hospital godavari-cancer-centre-test), role walk (no new problems), click flows pass after two fixes (profiles in the person's own hospital; plural words). Final gate: unit 5,118 passed + known env-only failure; tsc clean; build; mocked e2e 169 passed. HOW_TO_TRY.md written.
