#!/usr/bin/env bash
# Competitor Watch: collect -> (agent writes data/competitors-digest-DATE.json) -> build+encrypt -> commit -> push.
# Uses the SAME daily password as Industry Watch, so run scripts/publish.sh for DATE first.
# Usage: scripts/publish_competitors.sh [--skip-collect] [YYYY-MM-DD]
set -euo pipefail
cd "$(dirname "$0")/.."
SKIP=0; [[ "${1:-}" == "--skip-collect" ]] && { SKIP=1; shift; }
DATE="${1:-$(date +%F)}"
[[ -d node_modules/staticrypt ]] || npm install --silent >/dev/null
[[ $SKIP == 1 ]] || python3 scripts/collect_competitors.py "$DATE"
python3 scripts/build_competitors.py "$DATE"
for f in docs/????-??-??.html docs/competitors/????-??-??.html; do [[ -e "$f" ]] || continue; grep -q 'staticrypt' "$f" || { echo "refusing: $f not encrypted" >&2; exit 1; }; done
git add -A config scripts data state docs README.md
git diff --cached --name-only | grep -E '^(\.secrets|build)/' && { echo "refusing: secret/build file staged" >&2; exit 1; }
git commit -q -m "Competitor Watch $DATE" || echo "nothing to commit"
git push -q origin main
echo "published https://le-gns.github.io/industry-watch/competitors/$DATE.html"
