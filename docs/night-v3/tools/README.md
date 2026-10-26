Scripts the run writes (baseline screenshots and checks) live here.

| Script | What it does |
|---|---|
| `baseline_shots.sh [label]` | The baseline screenshots of item 0.1: every main screen per role (root admin, department admin, treating doctor, resident, supporting doctor and head, coordinator, member view, room screen), laptop and phone, light and dark, from the running app on :7000 through `web/tb-nik/e2e/shots/real.spec.ts` (`TBNIK_SHOTS` moves the pictures). Output: `/data/vaidyx/night-v3/baseline/<label>/` (PNGs, `playwright.txt`, `real-log.jsonl`, `real-log-axe.jsonl`). `TBNIK_REAL_ROLES=resident` runs a subset with its own log files. |
| `ensure_resident.py` | Makes or checks the demo resident login the real spec needs (`night-v3.resident@vaidyx-demo.invalid`, a resident of Breast Surgery on the team of TB-DEMO-P19); the login is kept in `/data/vaidyx/night-v3/.resident_login` (mode 600, outside the repo). Never prints a password or a code. |

Run from the repo root: `docs/night-v3/tools/baseline_shots.sh 2026-10-27`.
