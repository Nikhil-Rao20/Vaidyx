# Deploying Vaidyx-TB for doctors (Plan B)

The website is reached on the shared GCP VM; the app, the data and the AI stay on the IISc H200.

```
Doctor ─HTTPS─► VM nginx (vaidyx-tb-8-231-83-210.sslip.io)
                  ├─ /vx-link ◄══ secure link opened BY the H200 over 443 (chisel: password + pinned server key)
                  └─ everything else ─► 127.0.0.1:970 (the link's end, privileged port) ─► H200 gate :7301 ─► doctors' instance :7300
```

| Where | What | Files |
|---|---|---|
| VM | nginx site, link server (chisel, localhost only), our nftables table, maintenance page, certificate | `deploy/vm/` |
| H200 | doctors' instance (pinned checkout of `main`), gate (allow-list + secret), link client, watchdog | `deploy/h200/` |
| Repo | CI gate (`.github/workflows/gate.yml`), secret scan + pre-commit hook | `scripts/` |

Secrets never enter git: on the H200 in `~/vaidyx/deploy_vm/secrets/` (mode 600: `link_password`, `gate_secret`,
`chisel_server_key.pem`, `chisel_fingerprint`); on the VM in `/etc/vaidyx-tb/` (root, 0600). Logins of the doctors'
instance: `~/vaidyx/.tb_deploy_logins` (mode 600).

## Neighbours on the VM

RHV (renal portal, `renal-data-collection.tanuh.ai`) and TQC (`tqc-8-231-83-210.sslip.io`) run on the same VM. Never
read, restart or edit their units, files, certificates or nginx sites. Every VM step prints their status before and after.

## Setting up the doctors' instance (H200, once)

```bash
/data/vaidyx/venv/tb_deploy312/bin/python deploy/h200/setup_instance.py --app /data/vaidyx/tb_deploy/app   # synthetic cases, logins
/data/vaidyx/venv/tb_deploy312/bin/python deploy/h200/demo_owners.py   # after the app and gate run: TB-001..TB-008 get their department
```

`demo_owners.py` signs in as the MDT Coordinator and uses the app's own audited route, so each doctor finds the practice Case
Files of their department at the first sign-in. Run it again after `setup_instance.py --reset-cases`.

## The demo hospital (HIMS) on the public site

The public site has its own copy of the synthetic HIMS: `/data/vaidyx/tb_deploy/his_mock` on `127.0.0.1:7330` (own access key,
own staff passwords, no sessions or audit from the internal one), started and watched by `vx.sh` like the app and the gate.
Visitors reach its screens at `/his` and `/desk`; its data API (`/fhir`) is not public, the doctors' app reads it with its key
(`his.json` of the instance points at :7330). The internal development HIMS (`:7130`) is never reached from outside. The HIMS
staff logins (reception, OPD and ward doctors, lab, radiology, pathology, admin) are in
`/data/vaidyx/tb_deploy/his_mock/logins.tsv` (mode 600); new passwords: `TB_HIS_MOCK_DATA=/data/vaidyx/tb_deploy/his_mock
python -m his_mock.auth --reset`, run from the pinned checkout.

## Python environment

The doctors' site (app, gate, HIMS copy, release tests) runs on its own environment `/data/vaidyx/venv/tb_deploy312` (Python 3.12),
built from `requirements-ci.lock` (the pins CI tests, with the security upgrades). Rebuild: `/usr/bin/python3.12 -m venv
/data/vaidyx/venv/tb_deploy312`, `pip install pip==26.2.1`, `pip install -r requirements-ci.lock`. The shared `/data/vaidyx/venv/app`
(internal app, public demo) is separate. The earlier Python 3.10 environment `/data/vaidyx/venv/tb_deploy` is kept for a rollback:
deploying a commit from before the move starts the site on it again. The search model is the same file in both (fastembed 0.9.1 names
its source `Snowflake/...`, so its cache folder is `models--Snowflake--...`; the vectors are bit-identical). chromadb has advisories
without a fix; the Tumour Board does not use it.

## Everyday commands (H200)

```bash
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh status  # app, gate, link, public address
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh ensure  # start whatever is down (cron runs this every 5 minutes)
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh stop    # stop the doctors' instance, gate and link (the VM shows maintenance)
```

The watchdog (`crontab -l` on the H200):

```
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
@reboot sleep 180 && /data/vaidyx/tb_deploy/app/deploy/h200/vx.sh ensure >> /data/vaidyx/tb_deploy/logs/watchdog.log 2>&1
*/5 * * * * /data/vaidyx/tb_deploy/app/deploy/h200/vx.sh ensure >> /data/vaidyx/tb_deploy/logs/watchdog.log 2>&1
30 8 * * * /data/vaidyx/tb_deploy/app/deploy/h200/daily_check.sh > /dev/null 2>&1
```

While the watchdog runs, `vx.sh stop` lasts at most 5 minutes: to keep the instance down, comment out the two lines first.

## Releasing a new version

1. Commit (explicit files, pre-commit secret scan), push, PR into `main`, merge (merge commit or rebase, never squash).
2. Wait for the **green tick** of the `gate` workflow on that commit.
3. On the H200: `/data/vaidyx/tb_deploy/app/deploy/h200/deploy_h200.sh <commit>`: refuses a commit that is not on
   `origin/main` or not green; moves the pinned checkout; runs the tests CI cannot run (`deploy/ci/h200_only_tests.txt`,
   they need the NCG template kept only on the H200) and refuses on a failure; restarts, checks health, puts the previous
   commit back on failure; writes one line to `~/vaidyx/deploy_vm/DEPLOY_LOG.md`.
4. Only if `deploy/vm/` changed: copy `deploy/vm/` to the VM and run `sudo ./setup-vm.sh install` / `site` (Manual mode,
   Eswar approving each command), then `sudo ./setup-vm.sh check`.
5. When the release changes `deploy_h200.sh` itself, the previous copy of it runs that one time: afterwards run
   `vx.sh restart-gate` and `vx.sh restart-link` by hand (seen 4 Nov, release d0983f2).

## Daily check

`deploy/h200/daily_check.sh` (cron, every morning) checks app, gate, link and the public address, the certificate's days
left, that the protections still refuse (`/_gate/`, path tricks, the demo hospital, the main app's admin and API pages), one HSTS header, alerts from
`vx.sh` and disk space. It changes nothing. One line per run in `~/vaidyx/deploy_vm/logs/daily_check.log`: `OK` or `PROBLEM`.

## Reaching the VM

```bash
gcloud compute ssh vm-renal-dataserver --project=proj-renal-shared --zone=asia-south1-c --tunnel-through-iap \
  --command '<commands>' 2>&1 | grep -v -i "numpy\|increasing_the_tcp\|^WARNING\|^$"
gcloud compute scp --recurse <dir> vm-renal-dataserver:<name> --project=proj-renal-shared --zone=asia-south1-c --tunnel-through-iap
```

Never deploy around **20:30 IST** (unattended upgrades may reboot the VM).

## Certificate

Port 80 is closed, so the certificate is issued and renewed by TLS-ALPN on 443 **with nginx stopped for about 12
seconds** (RHV and TQC are unreachable for those seconds; pick a quiet time):

```bash
sudo ./setup-vm.sh cert <email>     # first time
sudo ./setup-vm.sh renew <email>    # when under 30 days are left (the daily check warns at 14)
```

## Rotating the secrets (monthly, and whenever someone leaves)

Generate new `link_password` and `gate_secret` on the H200, copy them to the VM, `sudo ./setup-vm.sh secrets <dir>`,
`sudo systemctl restart vaidyx-link`, `sudo systemctl reload nginx`, then on the H200 `vx.sh stop` and `vx.sh ensure`.

## Undo

```bash
sudo ./setup-vm.sh uninstall                          # VM: site, link server, firewall table, folders, user
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh stop     # H200; then remove the vx.sh lines from `crontab -e`
```
