# Release plan: after-healthathon to vaidyx.tanuh.ai

Live today: `9e98c68` (= `main`). The branch `after-healthathon` is a straight line on top of it (no merge needed).

## What was checked (19 Nov 2026)

| Check | Result |
|---|---|
| Whole test suite on the live Python 3.12 environment (`tb_deploy312`), as CI runs it | 5,219 passed; 1 known failure that needs the development hospital system's token (CI skips it) |
| Release-only tests (`deploy/ci/h200_only_tests.txt`) | 19 passed |
| Type check, site build | clean |
| Mocked screen tests | 193 passed |
| Old code (`9e98c68`) and the branch side by side on two copies of the live data, all 28 live logins | Same Case Files, meetings, inbox, organisation and accounts for every login |
| Staging rehearsal: branch + copy of live data + the gate, website at the root address | All 28 logins sign in, no page errors, no failing responses; name search, AI fill, chooser, Hospital console on a phone, guest private Case File and upload, old `/tb-nik/...` addresses redirect |
| Independent review of all 18 commits | No blocker; fixes below |

## Fixed for the release

| Fix | Why |
|---|---|
| Gate: `/platform` and `/hospital` added to the website pages | Without it, opening or refreshing the consoles on the live site gave "Not available" |
| `vx.sh`: `TB_HOSPITALS_ROOT=/data/vaidyx/tb_deploy/hospitals` set explicitly | Where new hospitals live; created only when the first new hospital is added |
| "Make it by hand" is not offered, and refused by the server, where only guests upload (`TB_UPLOAD_POLICY=private_only`, the live site) | A hospital doctor could never add the reports there; and it would invite real names into a shared Case File |

## Decisions before the release

| # | Question | Recommendation |
|---|---|---|
| 1 | Author of the commits pushed to `main` | Keep Bharath's commits as they are (fast-forward push) |
| 2 | The live site has **no Vaidyx admin login**, so nobody can open the Vaidyx console there | Leave it for now (the Hospital console works for tb-root); create one later on the server if the console is needed |
| 3 | AI fill after every lookup uses the shared reasoning model (one call per lookup, at most 30 per 10 minutes per login) | Keep on |
| 4 | tb-root can test hospital system settings (`/his/try`, 20 per 10 minutes, nothing saved) | Keep; restrict later if the tb-root password is shared with evaluators |

## Steps (on the owner's go, not around 20:30 IST)

1. `git push origin after-healthathon:main` (fast-forward from `9e98c68`).
2. Wait for the green `gate` tick in CI on the new head.
3. Check nobody is in a meeting; then `deploy/h200/deploy_h200.sh <head>`. Because `vx.sh` and `gate.py` changed, the gate, the demo hospital copy and the link restart too: about a minute of the maintenance page.
4. Check: daily check script, sign in as tb-root (lands on the Hospital console), a doctor (name search), a guest (own private Case Files), the old `/tb-nik/cases` redirect.
5. Rollback if needed: `deploy/h200/deploy_h200.sh 9e98c68`. The new code writes no new fields into org.json or profiles; the new `patient_index` folder is ignored by the old code.
