#!/bin/bash
# Secret scan for the Vaidyx repo (public). High-signal patterns only: private keys, cloud and service tokens, and
# our deployment secrets by name. Used by CI and by the pre-commit hook (scripts/install_hooks.sh).
#
#   scripts/secret_scan.sh --staged         what is about to be committed
#   scripts/secret_scan.sh --tree           every tracked file
#   scripts/secret_scan.sh --range A..B     the lines added by commits A..B (CI: the pushed commits)
#
# Exit 1 on a finding (file and line shown, the matched value is masked). Tests that need a fake secret build it at run
# time ("ghp_" + "a" * 36), so this scan never sees one.
set -u
PATTERNS='-----BEGIN ((RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|gho_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|"private_key": *"-----BEGIN|hf_[A-Za-z0-9]{34}|sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{40,}|xox[baprs]-[A-Za-z0-9-]{10,}|X-Vaidyx-Gate "[^"<]{16,}"|vxlink:[A-Za-z0-9_-]{16,}'
SKIP='^(scripts/secret_scan\.sh|deploy/tests/)'
mask() { sed -E "s/($PATTERNS)/[MASKED]/g"; }

found=0
case "${1:---tree}" in
  --staged)
    out=$(git diff --cached --no-color -U0 --diff-filter=ACMR | grep -nE '^\+' | grep -E -- "$PATTERNS")
    files=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '(^|/)(\.env|.*\.pem|.*\.key|id_rsa|id_ed25519|.*_logins?|.*logins?\.tsv|gate_secret|link_password|chisel-users\.json)$' | grep -v '\.env\.example$')
    ;;
  --tree)
    out=$(git ls-files -z | grep -zvE "$SKIP" | xargs -0 grep -nIE -- "$PATTERNS" 2>/dev/null)
    files=$(git ls-files | grep -E '(^|/)(\.env|.*\.pem|.*\.key|id_rsa|id_ed25519|.*_logins?|.*logins?\.tsv|gate_secret|link_password|chisel-users\.json)$' | grep -v '\.env\.example$')
    ;;
  --range)
    out=$(git log -p --no-color -U0 "${2:?usage: --range A..B}" -- . ':(exclude)scripts/secret_scan.sh' ':(exclude)deploy/tests' | grep -E '^\+' | grep -E -- "$PATTERNS")
    files=$(git diff --name-only "$2" | grep -E '(^|/)(\.env|.*\.pem|.*\.key|id_rsa|id_ed25519|.*_logins?|.*logins?\.tsv|gate_secret|link_password|chisel-users\.json)$' | grep -v '\.env\.example$')
    ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
if [ -n "$out" ]; then echo "SECRET SCAN: possible secrets:"; echo "$out" | mask | cut -c1-200; found=1; fi
if [ -n "$files" ]; then echo "SECRET SCAN: key or env files must not be committed:"; echo "$files"; found=1; fi
[ $found = 0 ] && echo "secret scan: clean (${1:---tree})"
exit $found
