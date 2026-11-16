# API fields the screens use (from the frontend build, 16 Nov), in addition to DESIGN 5.3

- Platform overview `tiles` keys: hospitals_active, hospitals_suspended, logins, hospital_admins, case_files, meetings_next_7_days, setup_complete, his_connected.
- Hospital row: id, name, city, state, status, status_reason, created, type ("public"|"private"), level, pmjay_empanelled, admins (number), people (number), case_files{open, decided, total}, setup{done, total}, his, last_activity.
- `his`: {state: "connected"|"failing"|"not_tested"|"not_set", url_set, tested_at, ok, demo?}.
- Platform `attention[]`: {hospital (id), hospital_name, kind, text}; kinds no_admin, setup_unfinished, his_failing, admin_never_signed_in.
- Hospital detail: hospital (row), counts{people, case_files_open, case_files_decided, case_files_total, meetings_next_7_days, open_requests},
  admins[{username, display_name, disabled, must_change_password, last_sign_in}], people_by_role{doctors, heads, residents, coordinators,
  dept_admins, hospital_admins, auditors, guests, disabled, never_signed_in}, setup{steps[{id, label, done, summary}], done, total}, his, recent[] (events).
- Logins: {username, display_name, hospital (id), hospital_name?, roles[], disabled, must_change_password, vaidyx_admin}; role values
  hospital_admin, doctor, head, resident, coordinator, dept_admin, auditor, guest, vaidyx_admin (also the ?role= filter values).
- Events (platform activity and detail recent): {ts, by, by_name?, hospital?, hospital_name?, kind, text}; platform kinds hospital_created,
  hospital_updated, hospital_suspended, hospital_reactivated, admin_added, admin_removed, password_reset, login_disabled, login_enabled, acting_in (also ?kind=).
- Hospital overview: hospital{id, name, city, state, status, level}; case_files.by_status keys draft, needs_team, waiting_department, ready,
  scheduled, decided (+ total); attention[] kinds no_coordinator, department_no_head, department_no_contact, resident_ending,
  never_signed_in, disabled_logins, setup_unfinished, his_failing, each with text and link (in-app path such as /hospital/people?role=resident,
  role=not_signed_in, role=disabled); recent[] may include by_name.
- Departments: heads may be strings or {username, display_name}.
- /me: platform_admin, roles.vaidyx_admin, acting_hospital{id, name, status}, hospital{id, name, status}.
- POST /platform/hospitals and admin/reset answers: password_once + mailto (the screens show password_once once).
- /platform/* routes must ignore X-TB-Hospital (the browser sends it while acting in a hospital).
- Server messages should say "hospital admin", not "root admin" (e.g. 403 texts).
