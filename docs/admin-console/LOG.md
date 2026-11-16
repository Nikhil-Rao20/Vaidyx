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
