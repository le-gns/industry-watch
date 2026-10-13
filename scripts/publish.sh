#!/usr/bin/env bash
# Daily run: collect -> (optional curated digest written by agent) -> build+encrypt -> commit -> push.
# Usage: scripts/publish.sh [--skip-collect] [YYYY-MM-DD]
set -euo pipefail
cd "$(dirname "$0")/.."
SKIP=0; [[ "${1:-}" == "--skip-collect" ]] && { SKIP=1; shift; }
DATE="${1:-$(date +%F)}"
[[ -d node_modules/staticrypt ]] || npm install --silent >/dev/null
[[ $SKIP == 1 ]] || python3 scripts/collect.py "$DATE"
python3 scripts/build.py "$DATE"
# safety: never publish unencrypted pages
for f in docs/????-??-??.html; do grep -q 'staticrypt' "$f" || { echo "refusing: $f not encrypted" >&2; exit 1; }; done
for f in docs/competitors/*.html; do [[ -e "$f" ]] || continue; grep -q 'http-equiv="refresh"' "$f" && ! grep -q '<h1>' "$f" || { echo "refusing: $f is not a redirect stub" >&2; exit 1; }; done
git add -A config scripts data state docs package.json package-lock.json .gitignore README.md
git diff --cached --name-only | grep -E '^(\.secrets|build)/' && { echo "refusing: secret/build file staged" >&2; exit 1; }
git commit -q -m "Industry Watch $DATE" || echo "nothing to commit"
git push -q origin main
echo "published https://le-gns.github.io/industry-watch/$DATE.html"
