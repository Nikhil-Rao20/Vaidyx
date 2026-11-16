# Admin consoles: Vaidyx admin (platform) and Hospital admin

Branch `after-healthathon` only. Asked by Bharath on 16 Nov 2026. Builds on the audit of 16 Nov (section 9).

## 1. What Bharath asked

| Who | Must be able to |
|---|---|
| Vaidyx admin (one main login) | See everything (dashboard). Add a hospital. Create hospital admins and any login. Move between hospitals and work inside one hospital |
| Hospital admin (one per hospital, or more) | A separate console for their own hospital: dashboard, people, add an MDT Coordinator, add doctors, set-up |

Other requirements: nothing that works today may break; follow the existing look; easy to understand; interactive; wired to the real
backend (real logins, real passwords, real roles).

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **One data folder per hospital.** Today's hospital stays where it is (`TB_DATA_ROOT`) as the hospital `default`. Each new hospital gets its own folder `<TB_HOSPITALS_ROOT>/<id>/` with today's layout (org.json, cases/, meetings, messages, his.json, ...). `TB_HOSPITALS_ROOT` defaults to a sibling of `TB_DATA_ROOT` named `hospitals` (never inside it) | The code was written for one hospital per folder. A per-request "current hospital" (a ContextVar) keeps every existing rule as it is, and a missed spot can only show one hospital's own data, never a mix. The alternative (a hospital field in one org.json) would touch 300 to 400 checks, and each one missed would be a leak (audit, section 9) |
| D2 | **A registry** `<TB_HOSPITALS_ROOT>/registry.json`: the hospitals (id, name, city, state, status, created) and which hospital each login belongs to | One place answers "which hospital is this login in". A login missing from it belongs to `default`, so today's data needs no migration |
| D3 | **One login belongs to one hospital.** A doctor who works in two hospitals gets two logins. A hospital admin can never place, reset or change a login of another hospital | Simple and clear for everyone; no cross-hospital leaks through shared logins |
| D4 | **Vaidyx admin = the platform admin** (the existing `is_admin` login). It works inside a hospital by choosing it ("acting in"); the choice travels as the header `X-TB-Hospital`, which the server accepts only from a Vaidyx admin | Matches "handle in between hospitals as well as inside one". Nobody else can switch |
| D5 | **The Vaidyx admin still has no clinical access.** Dashboards show counts and names of people, never patient names, UHIDs or report text. Opening a Case File keeps the existing break-glass rule (reason, audited, read only) | The project's privacy rule: the server administrator does not read patient data without a recorded reason |
| D6 | **No new Vaidyx admins from these screens.** The Vaidyx admin creates hospital admins and plain logins only | A Vaidyx admin has a server shell tool (CLAUDE.md invariant: no Tumour Board action creates or grants a Vaidyx admin) |
| D7 | **Hospital admin = today's root admin of that hospital** (org.json `admins`). In the interface it is called "Hospital admin" | The role already exists and is already wired to set-up and accounts; only the word changes |
| D8 | **A hospital is suspended, never deleted.** Suspended: its logins are refused with a plain message; its data stays. Reactivate any time | Deleting a hospital deletes patient records: not a button |
| D9 | **New hospitals start empty and safe:** default departments, the first hospital admin, no hospital system (or, ticked, the synthetic demo hospital system for a demo), voice and models shared | A new hospital must not see another hospital's anything. The demo HIS option makes a demo possible in two minutes |
| D10 | **Passwords stay as today:** a generated first password, shown once in the console with Copy and inside a mail draft, must be changed at first sign-in | Same rule as the existing set-up; never stored in plain text, never logged |
| D11 | **Everything a console changes is audited:** platform actions in `<TB_HOSPITALS_ROOT>/platform_audit.jsonl`, hospital actions in that hospital's `org_audit.jsonl` (as today) | Every user action is audited (invariant) |
| D12 | **Strict mode for safety:** once a second hospital exists, code that asks for the data folder without a current hospital fails loudly in tests (and logs in production, falling back to `default`) | Finds missed background threads before a person does |
| D13 | The MCP connector server (`serve_mcp.sh`, port 7110) stays bound to the default hospital | It is a separate process; documented, not changed |

## 3. Who sees what

| Page | Vaidyx admin | Hospital admin | Department admin | Doctor / coordinator |
|---|---|---|---|---|
| `/platform` Vaidyx console (overview, hospitals, logins, activity) | yes | no | no | no |
| `/hospital` Hospital console (overview, people, departments, set-up, hospital system, activity) | yes, for the hospital it acts in | yes, own hospital | no | no |
| `/people` (today's department people page) | yes | yes | own departments | no |
| `/admin` (today's set-up wizard) | stays; the console links to it as "Set-up" | yes | no | no |
| Case Files, meetings, messages | no clinical access (break-glass only) | no clinical access unless also placed as a doctor (unchanged) | as placed | as today |

## 4. Screens

### 4.1 Vaidyx console (`/platform`), top-bar item "Vaidyx console"
Tabs: **Overview**, **Hospitals**, **Logins**, **Activity**.

- **Overview**: tiles (hospitals active / suspended, logins, hospital admins, Case Files in all hospitals, meetings in the next 7 days,
  hospitals with set-up complete, hospital systems connected); a table, one row per hospital: name, city, status, admins, people,
  Case Files (open / decided), set-up progress, hospital system state, last activity; "Needs attention": hospitals without an admin,
  set-up not finished, hospital system failing, admins who never signed in. Counts only, no patient data.
- **Hospitals**: list with search; **Add a hospital** (a 3-step dialog: Hospital details, First hospital admin, Review): name, city,
  state, type (public / private), NCG level, PM-JAY; the admin's name and email (login); option "Use the demo hospital system
  (synthetic)". Result screen: the login and the first password once, Copy, "Open mail draft".
- **Hospital detail** (`/platform/hospitals/:id`): header with status and actions (**Manage inside this hospital**, Suspend /
  Reactivate, Edit details); cards: Overview counts, Hospital admins (add, remove, reset password), People by role, Set-up steps,
  Hospital system, Recent activity.
- **Logins**: every login of every hospital: search, filter by hospital and role; per row: Reset password, Disable / Enable, Open its
  hospital. Vaidyx admins are listed but cannot be changed here.
- **Activity**: the platform audit, newest first, filter by hospital and kind.
- **Acting-in bar**: when the Vaidyx admin manages inside a hospital, a slim bar under the top bar says "Managing Vaidyx Demo Hospital
  as Vaidyx admin" with **Switch hospital** and **Back to Vaidyx console**.

### 4.2 Hospital console (`/hospital`), top-bar item "Hospital"
Tabs: **Overview**, **People**, **Departments**, **Set-up**, **Hospital system**, **Activity**.

- **Overview**: greeting with the hospital name; tiles: people (doctors, residents, coordinators, department admins), Case Files by
  status (draft, needs the treating team, waiting on a department, ready, scheduled, decided), meetings in the next 7 days, open
  requests; set-up checklist (5 steps with progress); hospital system card (connected, last test, Test now); "Needs attention":
  no MDT Coordinator, departments without a head or contact, residents ending within 30 days, people who never signed in, disabled
  logins; quick actions: **Add a doctor**, **Add an MDT Coordinator**, **Add a department admin**, **Add a hospital admin**;
  recent activity (the hospital's org audit, people and set-up events only).
- **People**: one list with search and role filter chips; **Add a person** drawer: name, email, role (Doctor, Head of department,
  Resident with end date, MDT Coordinator, Department admin, Hospital admin, Auditor), department(s); result shows the first password
  once. Per person: change role, departments, reset password, disable / enable, end date.
- **Departments**: the list with group, head(s), people count, contact; edit contact and receives-requests; add a department.
- **Set-up**: today's set-up wizard (`/admin`), embedded or linked.
- **Hospital system**: the connection state and test (today's HIS step), later the "Choose your hospital system" screen.
- **Activity**: today's activity page for the hospital.

Look: the existing tokens, `PageHeader`, `surface` cards, `StatusPill`, `KeyValue`, buttons, Dock on a phone; light and dark;
laptop 1366 and phone 390. Plain words (Indian English), no jargon.

## 5. Backend

### 5.1 Hospital context (tumour_board/config.py, new tumour_board/hospitals.py)
- `config.BASE_ROOT`: today's `TB_DATA_ROOT`. `config.HOSPITALS_ROOT`: `TB_HOSPITALS_ROOT` or `BASE_ROOT.parent / "hospitals"`.
- A ContextVar `current hospital`; `config.DATA_ROOT` and `config.CASES_DIR` become path proxies that resolve through it (`/`,
  `__fspath__`, `__str__`, `exists`, `iterdir`, `glob`, ... forward to the real `Path`). `config.use_hospital(hid)` context manager,
  `config.hospital_id()`, `config.root_for(hid)`.
- Shared things pin to `BASE_ROOT`: models.json, model_cards.json, embed cache of model weights and guidelines, pubmed cache and
  settings, audio token, livekit.json, push VAPID keys, website enquiries and site mail.
- `hospitals.py`: `load()`, `hospital_of(username)`, `create(...)`, `update(...)`, `set_status(...)`, `assign(username, hid)`,
  `list()`, `audit(...)`; registry written atomically, mode 600.

### 5.2 Where the hospital is set
- Every `/api/tb` route: in `_ModelErrorRoute.handler`, right after the user is known; never reset in a `finally` (streams run after
  the handler returns).
- A Vaidyx admin may send `X-TB-Hospital: <id>`; anyone else's header is ignored. A login of a suspended hospital is refused (403).
- WebSockets (`api/live.py`, `api/messages_ws.py`): after authentication. Live rooms keyed by (hospital, meeting id); LiveKit room
  names get the hospital id.
- Background: the scheduler loops over active hospitals, each inside `use_hospital`; its state per hospital. `resume_after_restart`
  loops. The plain threads (`case_summary`, `ready_hook`, `push`, `messages`) run inside `contextvars.copy_context()`.
- In-memory maps keyed by a bare case id or meeting id get the hospital in their key (list in section 9).
- Accounts: `ensure_account`, `place_doctor`, `reset_password`, `update_account` refuse a login of another hospital; a new login is
  registered to the current hospital.

### 5.3 API (all JSON, all audited)

Vaidyx admin only (403 for anyone else):

| Method and path | Body / answer |
|---|---|
| `GET /api/tb/platform/overview` | `{tiles{...}, hospitals[{id, name, city, state, status, admins, people, case_files{open, decided, total}, setup{done, total}, his{state, tested_at}, last_activity}], attention[{hospital, kind, text}]}` |
| `GET /api/tb/platform/hospitals` | `{hospitals[...]}` (same rows) |
| `POST /api/tb/platform/hospitals` | `{name, city?, state?, type?, level?, pmjay_empanelled?, demo_his?, admin{display_name, email}}` -> `{hospital, admin{username, password_once, mailto}}` |
| `GET /api/tb/platform/hospitals/{id}` | `{hospital, counts, admins[], people_by_role{}, setup{steps[]}, his{}, recent[]}` |
| `PUT /api/tb/platform/hospitals/{id}` | `{name?, city?, state?}` |
| `POST /api/tb/platform/hospitals/{id}/status` | `{status: active|suspended, reason}` |
| `POST /api/tb/platform/hospitals/{id}/admins` | `{display_name, email}` or `{username}` -> `{username, created, password_once?, mailto?}` |
| `DELETE /api/tb/platform/hospitals/{id}/admins/{username}` | removes the hospital-admin role (never the last admin of an active hospital) |
| `GET /api/tb/platform/logins?hospital=&role=&q=` | `{logins[{username, display_name, hospital, roles[], disabled, must_change_password, vaidyx_admin}]}` |
| `POST /api/tb/platform/logins/{username}/reset-password` | `{password_once, mailto}` |
| `POST /api/tb/platform/logins/{username}/disable` / `enable` | `{ok}` |
| `GET /api/tb/platform/activity?hospital=&kind=&limit=` | `{events[]}` |

Hospital admin (and a Vaidyx admin acting in the hospital):

| Method and path | Body / answer |
|---|---|
| `GET /api/tb/hospital/overview` | `{hospital{name, ...}, people{doctors, heads, residents, coordinators, dept_admins, hospital_admins, auditors, guests, disabled, never_signed_in}, case_files{by_status{}, total}, meetings{next_7_days, upcoming[{id, title, date}]}, requests{open}, setup{steps[], done, total}, his{state, url_set, tested_at, ok}, attention[{kind, text, link}], recent[{ts, by, kind, text}]}` |
| `GET /api/tb/hospital/departments` | `{departments[{id, name, group, enabled, heads[], people, residents, email, phone, receives_requests}]}` |
| existing `/accounts`, `/setup/*`, `/departments/{d}/people`, `/his/*` | unchanged, now scoped to the current hospital |

`GET /api/tb/me` gains `hospital{id, name, status}`, `platform_admin` (bool) and, for a Vaidyx admin, `acting_hospital`.

## 6. What does not change
- One hospital (no second one created) behaves exactly as today; every existing test keeps passing.
- Department admins, doctors, the MDT Coordinator, guests, meetings, Case Files, voice, PubMed: unchanged inside a hospital.
- The deployed site, `main`, :7000, :5173, :7300 and its copies: untouched (separate worktrees and processes).

## 7. Checks
- Unit: the isolation tests of section 9 plus API tests per route (who may, who may not, audit lines, no password in logs).
- Whole suite in strict mode with a second hospital registered.
- Mocked screen tests for both consoles (laptop and phone).
- Live on :7400: create a hospital, its admin signs in (first password, change), adds a coordinator and a doctor, the doctor signs in
  and sees only that hospital; the Vaidyx admin switches between hospitals; the demo hospital's people see nothing new.

## 8. Out of scope (said plainly)
- Billing, plans, usage quotas, per-hospital model servers, per-hospital domains or branding beyond the existing logo.
- Moving a login between hospitals (create a new login instead).
- Deleting a hospital (suspend only).
- Single sign-on (SAML / OIDC) and the MCP server per hospital.

## 9. Audit findings that shape the build (16 Nov)
Traps: the agent stream runs after the handler returns (no reset); four plain threads start without context
(`case_summary.py:1290`, `ready_hook.py:248`, `push.py:329`, `messages.py:719`); maps keyed by bare case id collide because every
hospital numbers TB-2026-0001 (`store._docs_cache`, `search._index_cache`, `after_send._CHECKS`, `steps._COUNTS`, `agents._WARM`,
`case_summary.RUNNING/AGAIN`, `ready_hook.RUNNING/AGAIN`, `helpers.PREPARING`); maps keyed by meeting id (`meetings.py` live maps,
`meeting_notes._PENDING/_RUNNING`, `service.SESSION_TASKS`, `live.py` rooms, LiveKit room `tb-<mid>`); single-slot caches that can hand
one hospital another's data under threads (`org._cache`, `skills._cache`); import-time paths (`config.CASES_DIR`,
`config.AUDIO_TOKEN_FILE`, `pubmed.CACHE_DIR`, `pubmed.SETTINGS`); `config.models()` must stay shared; the scheduler has one module
state; `resume_after_restart` sees one root; `org.roles("")` is admin in single-user mode, so several hospitals require sign-in.
