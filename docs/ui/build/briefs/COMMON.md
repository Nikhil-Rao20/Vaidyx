# Common rules for every build agent (read first)

Repo /home/bharath.tangella/vaidyx/Vaidyx, branch the-ui. Python /data/vaidyx/venv/app/bin/python (use -I on downloaded data). Node: `export PATH=/data/vaidyx/tools/node/current/bin:$PATH`.

- Work autonomously. Never ask questions; decide, and list decisions in the final report.
- Do NOT run git (no add, commit, push, stash, checkout, reset). The lead commits your files.
- No em or en dashes anywhere (UI text, code, comments, docs). Use commas, colons, brackets.
- Never mention Claude or AI assistants in code, comments or docs.
- Never print or log passwords, tokens or secrets (files like ~/vaidyx/.vaidyx_admin_login, ~/vaidyx/.tb_v2_demo_logins, data/his_mock/token, data/his_mock/logins.tsv, data/tumour_board/livekit.json, push_keys.json): give paths only.
- Never read or modify the real case data/tumour_board/cases/TB-2026-bharath. Tests use synthetic data and the temp data roots of the test conftests.
- Do not stop or restart the main app on :7000 unless your brief says so; never touch ports 7100, 7101 (public demo). Models run on :8100 and :8101; tests never call them (mock).
- Product scope (signed): the AI checks, routes, summarises, flags. Never diagnosis, staging, image reading, treatment advice or clinical urgency judgement. Every value shown as fact carries a verified verbatim quote. Clinician confirmations beat model output. Every action audited. Terminology: Tumour Board Case File, Responsible Department, Pre-Authorization, Points for review, Human oversight (expert over the loop). Model labels: Qwen3.5-4B (Chinese, non-medical), Gemma-4-31B (non-medical).
- India first: UHID, IP / OP No., ABHA (never Aadhaar), DD/MM/YYYY on screen, Indian units.
- Owner's UX rules: busy, non-technical doctors; simple UI, powerful UX, nothing hard to find; laptop first (1366 and 1920 wide), mobile must work (390 wide, Dock nav); keep the existing colour theme (MONAI teal + status colours, see web/tb-nik/src/index.css); every control has default, hover, pressed, disabled, loading states; plain error messages with the cause and one action; micro-interactions; text only (no voice) in this build. UX principles: /home/bharath.tangella/vaidyx/Vaidyx/UX_notes.md.
- Security: auth on every route, rate limits on logins and codes, CSRF/Origin checks, no secrets in the frontend, audit everything.

Read for context: docs/ui/build/SPEC.md (the build spec), docs/ui/build/SPEC-API.md (the API contract for the new routers), docs/ui/build/maps/backend_map.md, core_map.md, his_mock_map.md (code maps), docs/ui/build/maps/casefile_ui_research.md (Case File layout research), docs/ui/questions/check.json (decisions from the interview check), tumour_board/api/common.py (shared route helpers).

CONTINUATION NOTE: a previous builder worked on your area and stopped on a session limit. Its work is on disk and uncommitted (`git status --short` shows it; `git diff <file>` shows edits to existing files). Start by reviewing what exists in your area, keep the good work, finish everything in your brief, then test until green. Do not rewrite working code for style.

Final report (under 600 words): what you built or finished, files, routes or pages, decisions, test and build results, anything left undone and why.
