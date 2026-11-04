#!/bin/bash
# Vaidyx-TB on the shared VM (deployment Plan B, see deploy/README.md). Run as root (sudo) from a copy of deploy/vm/ that
# also holds the chisel binary. Only our own files: RHV's and TQC's units, sites, certificates and firewall rules are
# never touched.
#
#   sudo ./setup-vm.sh prepare             user vaidyx-link, folders, chisel binary (checksum checked), maintenance page
#   sudo ./setup-vm.sh secrets <dir>       install the link password, server key and gate secret from <dir>, then shred <dir>
#   sudo ./setup-vm.sh install             firewall table + link server (systemd), nginx proxy snippet
#   sudo ./setup-vm.sh cert <email>        first certificate: lego TLS-ALPN with nginx stopped for about 12 seconds
#   sudo ./setup-vm.sh renew <email>       renew when under 30 days left (same 12-second nginx stop; run at a quiet time)
#   sudo ./setup-vm.sh site                our nginx site (only if nginx -t accepts it), then reload
#   sudo ./setup-vm.sh check               the VM equals this copy; services, ports, certificate days left, neighbours
#   sudo ./setup-vm.sh uninstall           remove everything of ours (one step back for every step above)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
HOSTNAME_TB=vaidyx-tb-8-231-83-210.sslip.io
ETC=/etc/vaidyx-tb
DATA=/mnt/data/vaidyx-tb
CHISEL_SHA256=b34230fc7f316d77335d59ccff3b4824298c4297ffd9d1d65f9813e01af4ebb1   # chisel 1.13.0 linux amd64
NGINX=/usr/sbin/nginx
SITE=/etc/nginx/sites-available/vaidyx-tb
UNITS="vaidyx-firewall.service vaidyx-link.service"

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
say() { echo "== $*"; }

neighbours() {
  printf 'RHV https %s · TQC ready %s · units: %s\n' \
    "$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://renal-data-collection.tanuh.ai/)" \
    "$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://tqc-8-231-83-210.sslip.io/api/health/ready)" \
    "$(systemctl is-active tanuh-renal-portal tanuh-rqc-service tqc-portal nginx | tr '\n' ' ')"
}

prepare() {
  id -u vaidyx-link >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin vaidyx-link
  install -d -m 0755 -o root -g root "$DATA" "$DATA/bin" "$DATA/www"
  install -d -m 0700 -o root -g root "$ETC" "$ETC/nginx"
  echo "$CHISEL_SHA256  $HERE/chisel" | sha256sum -c --quiet - || { echo "chisel checksum mismatch: refusing"; exit 1; }
  install -m 0755 -o root -g root "$HERE/chisel" "$DATA/bin/chisel"
  install -m 0644 -o root -g root "$HERE/maintenance.html" "$DATA/www/maintenance.html"
  say "prepared: user vaidyx-link, $DATA, $ETC"
}

secrets() {
  local src=${1:?usage: secrets <dir>}
  for f in link_password gate_secret chisel_server_key.pem; do [ -s "$src/$f" ] || { echo "missing $src/$f"; exit 1; }; done
  umask 077
  install -m 0600 -o root -g root "$src/chisel_server_key.pem" "$ETC/chisel_server_key.pem"
  python3 - "$src/link_password" "$ETC/chisel-users.json" <<'EOF'
import json, sys
pw = open(sys.argv[1]).read().strip()
json.dump({f"vxlink:{pw}": ["^R:127\\.0\\.0\\.1:17000$"]}, open(sys.argv[2], "w"))
EOF
  printf 'proxy_set_header X-Vaidyx-Gate "%s";\n' "$(tr -d '\n' < "$src/gate_secret")" > "$ETC/gate-header.conf"
  chmod 0600 "$ETC/chisel-users.json" "$ETC/gate-header.conf"
  shred -u "$src/link_password" "$src/gate_secret" "$src/chisel_server_key.pem" 2>/dev/null || rm -f "$src"/*
  rmdir "$src" 2>/dev/null || true
  say "secrets installed in $ETC (root, 0600); the copy was shredded"
}

install_units() {
  local www_uid; www_uid=$(id -u www-data)
  sed "s/@WWW_UID@/$www_uid/" "$HERE/vaidyx.nft" > "$ETC/vaidyx.nft"; chmod 0600 "$ETC/vaidyx.nft"
  /usr/sbin/nft -c -f "$ETC/vaidyx.nft"
  install -m 0644 "$HERE/vaidyx-firewall.service" /etc/systemd/system/vaidyx-firewall.service
  install -m 0644 "$HERE/vaidyx-link.service" /etc/systemd/system/vaidyx-link.service
  install -m 0644 "$HERE/vaidyx-proxy.conf" "$ETC/nginx/vaidyx-proxy.conf"
  systemd-analyze verify /etc/systemd/system/vaidyx-link.service /etc/systemd/system/vaidyx-firewall.service
  systemctl daemon-reload
  systemctl enable --now $UNITS
  sleep 2
  systemctl is-active $UNITS
  say "link server listening: $(ss -Hltn 'sport = :17999' | awk '{print $4}')"
}

cert() {
  local email=${1:?usage: cert <email>}
  [ -f "$ETC/lego/certificates/$HOSTNAME_TB.crt" ] && { say "certificate already present"; return 0; }
  install -d -m 0700 "$ETC/lego"
  say "before: $(neighbours)"
  say "stopping nginx for the TLS-ALPN challenge (about 12 seconds)"
  systemctl stop nginx
  trap 'systemctl start nginx' EXIT
  lego --path "$ETC/lego" --email "$email" --domains "$HOSTNAME_TB" --accept-tos --tls run
  systemctl start nginx; trap - EXIT
  systemctl is-active nginx
  say "after: $(neighbours)"
  openssl x509 -noout -enddate -in "$ETC/lego/certificates/$HOSTNAME_TB.crt"
}

renew() {
  local email=${1:?usage: renew <email>} end left
  end=$(openssl x509 -noout -enddate -in "$ETC/lego/certificates/$HOSTNAME_TB.crt" | cut -d= -f2)
  left=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
  [ "$left" -ge 30 ] && { say "certificate has $left days left: no renewal needed"; return 0; }
  say "before: $(neighbours)"; systemctl stop nginx; trap 'systemctl start nginx' EXIT
  lego --path "$ETC/lego" --email "$email" --domains "$HOSTNAME_TB" --accept-tos --tls renew --days 30
  systemctl start nginx; trap - EXIT; say "after: $(neighbours)"
}

site() {
  install -m 0644 "$HERE/vaidyx-tb.nginx.conf" "$SITE"
  ln -sfn "$SITE" /etc/nginx/sites-enabled/vaidyx-tb
  if ! $NGINX -t 2>&1; then
    rm -f /etc/nginx/sites-enabled/vaidyx-tb
    echo "nginx -t failed: our site was taken out again, nothing reloaded"; exit 1
  fi
  systemctl reload nginx
  sleep 1
  say "site enabled · $(neighbours)"
}

check() {
  local bad=0 www_uid; www_uid=$(id -u www-data)
  cmp_file() { if ! cmp -s "$1" "$2"; then echo "DIFFERS: $2"; bad=1; fi; }
  cmp_file "$HERE/vaidyx-tb.nginx.conf" "$SITE"
  cmp_file "$HERE/vaidyx-proxy.conf" "$ETC/nginx/vaidyx-proxy.conf"
  cmp_file "$HERE/vaidyx-link.service" /etc/systemd/system/vaidyx-link.service
  cmp_file "$HERE/vaidyx-firewall.service" /etc/systemd/system/vaidyx-firewall.service
  cmp_file "$HERE/maintenance.html" "$DATA/www/maintenance.html"
  if ! diff -q <(sed "s/@WWW_UID@/$www_uid/" "$HERE/vaidyx.nft") "$ETC/vaidyx.nft" >/dev/null; then echo "DIFFERS: $ETC/vaidyx.nft"; bad=1; fi
  echo "$CHISEL_SHA256  $DATA/bin/chisel" | sha256sum -c --quiet - || bad=1
  echo "units: $(systemctl is-active $UNITS | tr '\n' ' ')"
  /usr/sbin/nft list table inet vaidyx >/dev/null 2>&1 && echo "firewall table: present" || { echo "firewall table: MISSING"; bad=1; }
  echo "our ports: $(ss -Hltn '( sport = :17000 or sport = :17999 )' | awk '{print $4}' | tr '\n' ' ')"
  if ss -Hltn '( sport = :17000 or sport = :17999 )' | awk '{print $4}' | grep -qv '^127\.0\.0\.1:'; then echo "A LINK PORT IS NOT LOCALHOST-ONLY"; bad=1; fi
  for f in chisel_server_key.pem chisel-users.json gate-header.conf; do
    [ "$(stat -c '%a %U' "$ETC/$f" 2>/dev/null)" = "600 root" ] || { echo "WRONG MODE/OWNER: $ETC/$f"; bad=1; }
  done
  if [ -f "$ETC/lego/certificates/$HOSTNAME_TB.crt" ]; then
    local end; end=$(openssl x509 -noout -enddate -in "$ETC/lego/certificates/$HOSTNAME_TB.crt" | cut -d= -f2)
    echo "certificate: $(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 )) days left"
  else echo "certificate: none yet"; fi
  echo "neighbours: $(neighbours)"
  [ $bad = 0 ] && echo "CHECK OK: the VM equals this copy" || { echo "CHECK FOUND DIFFERENCES"; exit 1; }
}

uninstall() {
  rm -f /etc/nginx/sites-enabled/vaidyx-tb "$SITE"
  $NGINX -t && systemctl reload nginx
  systemctl disable --now $UNITS 2>/dev/null || true
  /usr/sbin/nft delete table inet vaidyx 2>/dev/null || true
  rm -f /etc/systemd/system/vaidyx-link.service /etc/systemd/system/vaidyx-firewall.service
  systemctl daemon-reload
  rm -rf "$DATA" "$ETC"
  id -u vaidyx-link >/dev/null 2>&1 && userdel vaidyx-link
  say "uninstalled · $(neighbours)"
}

case "${1:-}" in
  prepare) prepare ;;
  secrets) secrets "${2:-}" ;;
  install) install_units ;;
  cert) cert "${2:-}" ;;
  renew) renew "${2:-}" ;;
  site) site ;;
  check) check ;;
  uninstall) uninstall ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
