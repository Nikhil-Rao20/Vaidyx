#!/bin/bash
# Install the pre-commit hook: it runs scripts/secret_scan.sh --staged and refuses the commit on a finding.
# It fails closed: if the scan script is missing, the commit is refused too.
set -eu
top=$(git rev-parse --show-toplevel)
hooks=$(git rev-parse --git-path hooks)
mkdir -p "$hooks"
cat > "$hooks/pre-commit" <<'EOF'
#!/bin/bash
top=$(git rev-parse --show-toplevel)
[ -x "$top/scripts/secret_scan.sh" ] || { echo "pre-commit: scripts/secret_scan.sh missing: commit refused"; exit 1; }
exec "$top/scripts/secret_scan.sh" --staged
EOF
chmod +x "$hooks/pre-commit"
echo "pre-commit hook installed in $hooks (repo $top)"
