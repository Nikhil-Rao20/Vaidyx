# Meetings v2: how the unattended run is organised

The same organisation as the night run: read [docs/night-v3/ORCHESTRATION.md](../night-v3/ORCHESTRATION.md) for the roles and models,
the usage budget, the lanes (at most 3 agents at once, disjoint files), the hand-off contract, the speed rules, the log tags and the good
ideas rule. Only these differ:

| Topic | Meetings v2 |
|---|---|
| Plan, log, checkpoint | [PLAN.md](PLAN.md), [LOG.md](LOG.md), `docs/meetings-v2/CURRENT.md` |
| Branch | `the-ui` (the owner's working branch since 2 Nov 2026; tracks `origin/the-ui`). Never push |
| Commit titles | `M2-<ID>: <title>`, author `git -c user.name="Nikhil-Rao20" -c user.email="nikhilproffesion@gmail.com" commit`. No Claude mention anywhere |
| Run state (outside the repo) | `/data/vaidyx/meetings-v2/` (runs/, supervisor.log, supervisor.pid, PAUSE, RUN_COMPLETE, shots/) |
| Owner controls | `docs/meetings-v2/run.sh start|pause|resume|stop|status` |
| Baseline screenshots | `/data/vaidyx/night-v3/baseline/2026-11-02/` (taken on 2 Nov before this run, every role) |
| Agents | `.claude/agents/tb-implementer.md`, `tb-explorer.md`, `tb-reviewer.md` name this plan as the active plan |

## The regression gate (end of every phase)
1. `/data/vaidyx/venv/app/bin/python -m pytest -q -p no:cacheprovider tumour_board/tests his_mock/tests --deselect tumour_board/tests/test_agents_live.py`
   (all pass; on 2 Nov 2026 the count was 4,388).
2. `cd web/tb-nik && export PATH=/data/vaidyx/tools/node/current/bin:$PATH && npx tsc -b --noEmit && npx vite build`.
3. Mocked screenshot tests: `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts`
   (123 passed on 2 Nov; change a spec only when its screen changed on purpose, and say so in the log).
4. Real-app checks of the screens the phase touched: laptop 1366 x 768 and phone 390 x 844, light theme; no page errors, no sideways
   scroll; the two-person live test `cd web/tb-nik && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib npx playwright test -c e2e/live/playwright.live.config.ts`
   once its spec follows the new screens (Phase 2 on).
5. GPU evaluations only when model-facing code changed, one at a time.

## Useful facts found on 2 Nov (do not rediscover)
- Demo logins are read in code from `~/vaidyx/.tb_v2_demo_logins` (tab-separated, first column the username); the walk-through logins
  finished their first set-up on 2 Nov. Too many sign-ins in a row trip the login limit: keep one browser session per login (store the
  cookie state outside the repo, mode 600) and reuse it.
- A Playwright script outside the test runner needs `LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib` and imports Playwright from
  `/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs`.
- The app is restarted by stopping the process on :7000 by its PID, then `~/vaidyx/start_vaidyx_app.sh`, then waiting for
  `/api/health` 200 (the start script does not stop the old one).
- The Case summary is built only when no meeting of today is in session (it waits up to 4 h, looking every 5 min): end test meetings.
- Chromium's fake microphone takes a WAV file: `--use-file-for-fake-audio-capture=<file.wav>` (Kokoro on :7120 makes one; the audio
  token is in `data/tumour_board/audio_token.json`, read in code).
- The decision panel in a meeting is the side panel button `panel-decision`; the dictation buttons are named `Dictate: <field label>`.
- `docs/meetings-v2/tools/lib.mjs` (from the 2 Nov test pass): `open(user)` gives a signed-in Chromium page that reuses a stored
  session per login, page-error and 5xx watchers, `shot()`, `note()` and `problem()`; scripts in `tools/` import it.
