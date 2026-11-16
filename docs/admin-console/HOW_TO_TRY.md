# Admin consoles: how to try them

Branch `after-healthathon`, on the test copy only: http://localhost:5180/tb-nik (tunnel
`ssh -N -L 5180:127.0.0.1:5180 -L 7400:127.0.0.1:7400 bharath.tangella@10.16.63.43`). The deployed site and `main` do not have this.

## Who signs in

| Login | What they see | Password file |
|---|---|---|
| `admin` (Vaidyx admin) | Vaidyx console: every hospital | `~/vaidyx/.vaidyx_admin_login` |
| `tb-root` (hospital admin, Vaidyx Demo Hospital) | Hospital console of the demo hospital | `~/vaidyx/.tb_deploy_logins` |
| `admin@godavari-test.invalid` (hospital admin, test hospital) | Hospital console of "Godavari Cancer Centre (test)" | `~/vaidyx/.tb_after_logins` |
| `breast.doc@godavari-test.invalid` (doctor, test hospital) | Case Files of the test hospital only (none yet) | `~/vaidyx/.tb_after_logins` |

## Five things to try

| # | Do this | You should see |
|---|---|---|
| 1 | Sign in as `admin` | The Vaidyx console: tiles, needs attention, one row per hospital. Counts only, no patient names |
| 2 | Hospitals, Add a hospital | Three steps. At the end, the first hospital admin's login and first password, shown once, with Copy and a mail draft |
| 3 | Open a hospital, Manage inside this hospital | A bar "Managing <hospital> as Vaidyx admin"; the Hospital console of that hospital; Switch hospital; Back to Vaidyx console |
| 4 | Sign in as the new hospital admin (first password, then your own) | The Hospital console: overview, Add a doctor / MDT Coordinator / department admin / hospital admin; People, Departments, Set-up, Hospital system, Activity |
| 5 | Sign in as a doctor of the new hospital | Only that hospital's Case Files and people; nothing of the demo hospital |

Also: Suspend a hospital (Vaidyx console, the hospital's page, the ... menu): its logins get "Your hospital's access to Vaidyx is
paused". Reactivate brings them back.

## Rules worth knowing
- One login belongs to one hospital. A doctor in two hospitals gets two logins.
- The Vaidyx admin sees counts and people, never patient data; a Case File still needs break-glass with a reason.
- The Vaidyx admin cannot make another Vaidyx admin from these screens (that login has a server shell).
- A hospital is suspended, never deleted.
- A new hospital has no hospital system until its admin connects one (or the Vaidyx admin ticks the synthetic demo system when adding it).

## Where things live
- Data of today's hospital: unchanged (`TB_DATA_ROOT`). New hospitals: `TB_HOSPITALS_ROOT/<id>/` (on the test copy
  `/data/vaidyx/tb_after/hospitals/`), with `registry.json` (hospitals, which login belongs where) and `platform_audit.jsonl`.
- Start the app with `TB_HOSPITALS_ROOT` set (see `docs/admin-console/DESIGN.md`); if it is missing it defaults to a folder named
  `hospitals` beside `TB_DATA_ROOT`.
