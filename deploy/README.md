# Deploying Vaidyx-TB for doctors (Plan B)

The website is reached on the shared GCP VM; the app, the data and the AI stay on the IISc H200.

```
Doctor ─HTTPS─► VM nginx (vaidyx-tb-8-231-83-210.sslip.io)
                  ├─ /vx-link ◄══ secure link opened BY the H200 over 443 (chisel: password + pinned server key)
                  └─ everything else ─► 127.0.0.1:17000 (the link's end) ─► H200 gate :7301 ─► doctors' instance :7300
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

## Everyday commands (H200)

```bash
~/vaidyx/Vaidyx-deploy/deploy/h200/vx.sh status      # app, gate, link, public address
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh ensure  # start whatever is down (cron runs this every 5 minutes)
/data/vaidyx/tb_deploy/app/deploy/h200/vx.sh stop    # stop the doctors' instance, gate and link (the VM shows maintenance)
```

## Releasing a new version

1. Commit (explicit files, pre-commit secret scan), push, PR into `main`, merge (merge commit or rebase, never squash).
2. Wait for the **green tick** of the `gate` workflow on that commit.
3. On the H200: `/data/vaidyx/tb_deploy/app/deploy/h200/deploy_h200.sh <commit>`: refuses a commit that is not on
   `origin/main` or not green; moves the pinned checkout; runs the tests CI cannot run (`deploy/ci/h200_only_tests.txt`,
   they need the NCG template kept only on the H200) and refuses on a failure; restarts, checks health, puts the previous
   commit back on failure; writes one line to `~/vaidyx/deploy_vm/DEPLOY_LOG.md`.
4. Only if `deploy/vm/` changed: copy `deploy/vm/` to the VM and run `sudo ./setup-vm.sh install` / `site` (Manual mode,
   Eswar approving each command), then `sudo ./setup-vm.sh check`.

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
