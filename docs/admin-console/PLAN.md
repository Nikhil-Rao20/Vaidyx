# Admin consoles: build plan

Design: [DESIGN.md](DESIGN.md). Log: [LOG.md](LOG.md). Branch `after-healthathon`, worktree `~/vaidyx/Vaidyx-after-healthathon`.
Commits: `git -c user.name="Bharath (Vaidyx-TB)" -c user.email="bcs.subscriptions@tanuh.ai" commit`, title `AC-<id>: <title>`, no
mention of Claude, never pushed. Agents: Opus 5.5 only. Servers for checks: app :7400 and Vite :5180 only (their own data copy
`/data/vaidyx/tb_after`); never touch :7000, :5173, :7300, :7301, :7330, :7340, the deployed copy or `main`.

| Phase | Item | What | Who | Status |
|---|---|---|---|---|
| A | A1 | Hospital context: `config` proxies, `BASE_ROOT`, `HOSPITALS_ROOT`, `use_hospital`, shared pins | backend agent 1 | done (0966e05) |
| A | A2 | `hospitals.py` registry (create, status, assign, list, audit), mode 600, atomic | backend agent 1 | done (0966e05) |
| A | A3 | Set the hospital per request (route class, X-TB-Hospital for Vaidyx admin, suspended refusal), WebSockets, live rooms, LiveKit names | backend agent 1 | done (0966e05) |
| A | A4 | Background: scheduler per hospital, resume loop, the four threads, re-keyed maps, org / skills caches | backend agent 1 | done (0966e05) |
| A | A5 | Accounts refuse other hospitals' logins; new logins registered | backend agent 1 | done (0966e05) |
| A | A6 | Isolation tests (two roots, same case id, threads, WebSocket rooms, scheduler, strict mode run of the suite) | backend agent 1 | done (0966e05) |
| B | B1 | `/platform/*` routes and service (`platform_admin.py`), create hospital with first admin, demo HIS option | backend agent 2 (after A) | done |
| B | B2 | `/hospital/overview`, `/hospital/departments`, `/me` hospital fields | backend agent 2 | done |
| B | B3 | API tests (who may, audit, no password in logs, last admin rule, suspended hospital) | backend agent 2 | done |
| C | C1 | Vaidyx console screens (overview, hospitals, add hospital, hospital detail, logins, activity), acting-in bar, switcher, nav | frontend agent (parallel with A, on the API contract) | done (180d86e) |
| C | C2 | Hospital console screens (overview, people with add-person drawer, departments, set-up, hospital system, activity), nav | frontend agent | done (180d86e) |
| C | C3 | Mock data for the mocked screen tests; specs for both consoles, laptop and phone | frontend agent | done (180d86e) |
| D | D1 | Wire to the real API on :7400, restart :7400 only, live walk of every role, fix | orchestrator + agents | done |
| D | D2 | Review agent: security and isolation read of the whole diff; fixes | review agent | done |
| D | D3 | Full gate: unit suite, tsc, build, mocked e2e, live walk laptop + phone, light + dark | orchestrator | done |
| D | D4 | HOW_TO_TRY.md, memory, report to Bharath | orchestrator | done |
