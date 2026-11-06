#!/bin/bash
# Daily check of the doctors' address (deployment Plan B, see deploy/README.md). Read-only: it changes nothing.
# Run by cron on the H200 every morning; one summary line per run in ~/vaidyx/deploy_vm/logs/daily_check.log
# ("OK ..." or "PROBLEM ..."), details below it. Exit 1 when something needs a look.
#
#   deploy/h200/daily_check.sh
set -u
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
HERE=$(cd "$(dirname "$0")" && pwd)
HOST=${VX_PUBLIC_HOST:-vaidyx.tanuh.ai}
ROOT=${VX_DEPLOY_ROOT:-/data/vaidyx/tb_deploy}
OUT=${VX_CHECK_LOG:-$HOME/vaidyx/deploy_vm/logs/daily_check.log}
mkdir -p "$(dirname "$OUT")"
problems=(); details=()
code() { curl -s -m 15 --path-as-is -o /dev/null -w '%{http_code}' "$@"; }

# 1. the parts on the H200 and the public address
st=$("$HERE/vx.sh" status 2>&1); while IFS= read -r l; do details+=("$l"); done <<<"$st"
grep -q "^app .* up " <<<"$st" || problems+=("app down")
grep -q "^gate .* up (health 200)" <<<"$st" || problems+=("gate down")
grep -q "^link .* up " <<<"$st" || problems+=("link down")
grep -q "^public .*200 " <<<"$st" || problems+=("public address not 200")

# 2. certificate days left (renew under 30 with setup-vm.sh renew; warn at 14)
end=$(echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
if [ -n "$end" ]; then
  days=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 )); details+=("certificate: $days days left")
  [ "$days" -lt 14 ] && problems+=("certificate expires in $days days")
else problems+=("certificate unreadable"); fi

# 3. the protections still hold (each must be refused)
for p in /_gate/health "/_ga%09te/health" /fhir/metadata "/api/tb/%2561dmin/x" /api/admin/users /openapi.json /api/chat; do
  c=$(code "https://$HOST$p"); [ "$c" = 404 ] || problems+=("$p answered $c (expected 404)")
done
c=$(code "https://$HOST/api/tb/cases"); [ "$c" = 401 ] || problems+=("case list without a session answered $c (expected 401)")
c=$(code "https://$HOST/his/login"); [ "$c" = 200 ] || problems+=("demo hospital sign-in answered $c (expected 200)")
hsts=$(curl -s -m 15 -D - -o /dev/null "https://$HOST/login" | grep -ci '^strict-transport-security')
[ "$hsts" = 1 ] || problems+=("HSTS headers: $hsts (expected 1)")

# 4. alerts from vx.sh (a port held by another user) and link reconnects in the last day
if [ -s "$ROOT/logs/alerts.log" ]; then
  new=$(awk -v d="$(date -d '1 day ago' '+%F %T')" '{ if (($2" "$3) >= d) n++ } END { print n+0 }' "$ROOT/logs/alerts.log")
  [ "$new" -gt 0 ] && problems+=("$new port alerts in the last day (see $ROOT/logs/alerts.log)")
fi
since=$(date -d '1 day ago' '+%Y/%m/%d %H:%M:%S')
reconn=$(awk -v d="$since" '/client: Connected/ { if (($1" "$2) >= d) n++ } END { print n+0 }' "$ROOT/logs/link.log" 2>/dev/null)
details+=("link connections in the last day: $reconn"); [ "${reconn:-0}" -gt 24 ] && problems+=("link reconnected $reconn times in a day")

# 5. disk space for the instance's data
free=$(df -P /data | awk 'NR==2 { print int($4/1048576) }'); details+=("free on /data: ${free} GB")
[ "$free" -lt 50 ] && problems+=("only ${free} GB free on /data")

{
  if [ ${#problems[@]} -eq 0 ]; then echo "$(date '+%F %T') OK  all checks passed"
  else echo "$(date '+%F %T') PROBLEM  $(IFS='; '; echo "${problems[*]}")"; fi
  printf '    %s\n' "${details[@]}"
} | tee -a "$OUT"
[ ${#problems[@]} -eq 0 ]
