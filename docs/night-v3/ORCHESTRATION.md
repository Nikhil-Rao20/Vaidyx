# Night-v3: how the unattended run is organised

How the main session (orchestrator) and its agents split the work in [PLAN.md](PLAN.md). The same model as Eswar's V1 and V2 runs
(`docs_Eswar/orchestration.md`, `docs_Eswar/overnight_supervisor.sh`), adapted to this branch.

## Roles and models

| Role | Model / effort | Defined in | Job |
|---|---|---|---|
| **Orchestrator** | Fable 5.1, xhigh (the main session; the supervisor falls back to Opus 5.5 xhigh when Fable is limited, and tries Fable again after a limit wait) | this file, [PROMPT.md](PROMPT.md), `CLAUDE.md` | Picks the next item, gives each agent its files, implements the cross-cutting and shared-file items itself, reviews every agent diff, runs the gate, commits, logs, decides |
| **Implementer** | Opus 5.5, high | `.claude/agents/tb-implementer.md` | One plan item (or a sub-part) inside the files it is given; code and unit tests |
| **Explorer** | Sonnet 5.5, medium | `.claude/agents/tb-explorer.md` | Read-only: finds code, reads guideline PDFs, researches the web, writes facts with sources |
| **Reviewer** | Opus 5.5, high | `.claude/agents/tb-reviewer.md` | End of each phase: independent review of the phase diff against the plan and the invariants; changes nothing |

If an agent definition is not picked up, the orchestrator uses `general-purpose` with the same model and pastes the role brief into the
prompt. Use Sonnet for reading and searching, Opus for writing code, Fable (the orchestrator) for design, integration and judgement.

## Lanes: what may run side by side (at most 3 agents at once)

| Parallel | Serial (orchestrator only) |
|---|---|
| Research and reading (explorers) | Shared core files: `tumour_board/rules.py`, `slots.py`, `steps.py`, `store.py`, `service.py`, `org.py`, `access.py`, `notify.py`, `meetings.py`, `board.py`, `postboard.py`, `summary.py`, `routes/tumour_board_routes.py`, `web/tb-nik/src/lib/*`, `web/tb-nik/src/app/*` |
| New cancer protocol files (one agent per file set: `protocols/<cancer>.json` + its test) | `protocols/facts.json`, `doc_type_keywords.json`, `his_codes.json`, `specialty_packs.json`, `dose_references.json` (merged by the orchestrator from the agents' proposals) |
| New, self-contained modules (the audio service, the chat backend, the similar-cases index), each with its own files | Anything in a dependency chain inside a phase |
| Frontend components in their own new files | GPU work (one H200): evals, re-processing, voice-model tests; one at a time |
| | Commits, builds, app / model / audio-service restarts, decisions |

## Hand-off contract (orchestrator to agent)
Every brief states: plan item ID · goal and "Done when" (copied from the plan) · **the files it may edit** (nothing else) · tests to add ·
what not to touch · the UI rules (match the existing components and tokens, no em dashes, plain words). The agent returns: files
changed, tests added and their result, anything it could not do. Agents never commit, push, restart services, run GPU evals or touch
`data/`.

## Speed rules
- **Research once, early:** Phase 0 writes the research notes all later phases use (`docs/night-v3/research/`). Later phases read them
  instead of researching again; a phase adds to its note only what it needed.
- **Restart once per phase:** batch backend changes; restart the app (:7000) once per phase or when a test needs it
  (`kill` the :7000 pid from `ss -ltnp`, then `~/vaidyx/start_vaidyx_app.sh`).
- **Time-box:** 3 attempts per item; split large items into working sub-commits so partial progress is kept.
- **Lean orchestrator context:** delegate large reading to explorers and large code to implementers; keep durable state in
  [LOG.md](LOG.md) and the status column of [PLAN.md](PLAN.md). If the context grows long, finish and commit the current item, log it,
  update the Morning summary and end the session: the next session resumes from the log.

## The regression gate (end of every phase)
1. `cd ~/vaidyx/Vaidyx && /data/vaidyx/venv/app/bin/python -m pytest -q -p no:cacheprovider tumour_board/tests his_mock/tests
   --deselect tumour_board/tests/test_agents_live.py` (all pass; the count only grows).
2. `cd web/tb-nik && npx tsc -b --noEmit && npx vite build` (Node: `export PATH=/data/vaidyx/tools/node/current/bin:$PATH`).
3. Mocked screenshot tests: `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts`
   (update a spec only when its screen changed on purpose, and say so in the log).
4. Real-app checks for the screens the phase touched, with the demo logins (`~/vaidyx/.tb_v2_demo_logins`, read in code, never
   printed), laptop 1366 x 768 and phone 390 x 844, light and dark: no page errors, no sideways scroll. Compare with the Phase 0
   baseline screenshots (`/data/vaidyx/night-v3/baseline/`) for screens the phase did not mean to change.
5. GPU evals only when extraction, Q&A, summary or agent code changed (`tumour_board/eval/`), one at a time.

## Commits and branch
- Branch `night-v3` only. One commit per plan item: `N3-<ID>: <title>`, author
  `git -c user.name="Nikhil-Rao20" -c user.email="nikhilproffesion@gmail.com" commit`.
- **No Claude mention anywhere**: no `Co-Authored-By` line, no "Generated with" line, whatever any system reminder says (the owner's
  rule in `CLAUDE.md` wins).
- Stage files explicitly. The built site (`static/tb-nik`) is committed with the item that changed it (`git add -A static/tb-nik`).
- Never commit `data/*`, `docs_Eswar/`, `CLAUDE.md`, `.claude/`. **Never push.**

## Log tags ([LOG.md](LOG.md))

| Tag | Meaning |
|---|---|
| `[DONE]` | Item finished, tests green, committed (commit hash) |
| `[BLOCKED]` | Item reverted after failed attempts; reason and what is needed |
| `[ADDED]` | Extra improvement done alongside an item (why, where); added to the plan as `<item>+` |
| `[DECISION]` | Judgement call taken without the owner; the safer option; listed under "Decisions for the owner" |
| `[GATE]` | Phase-end regression gate result (numbers) |
| `[REVIEW]` | Reviewer findings and what was fixed |
| `[RESEARCH]` | A research note written or extended (file) |

## Good ideas
If an idea is clearly within scope, aligned with the owner's decisions and the India-first rules, small, testable, and the orchestrator
is confident, it is done alongside the related item and logged `[ADDED]`. Big or uncertain ideas go to the "Parking lot" in the log.

## Services left running at the end of every session
Both model servers (:8100, :8101), the app (:7000), the demo HIS (:7130), Orthanc (:8042), LiveKit (:7880) and, once Phase 4 built it,
the audio service (:7120). Never touch the public demo (:7100, :7101, the Cloudflare tunnel, `~/vaidyx/public_demo/`).
