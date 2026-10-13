# Industry Watch
Daily news digest for Geniuslink marketing. Public content only; published pages are staticrypt-encrypted with a new password each day.
- `config/feeds.json`: all feeds (Google News searches, source RSS, Reddit), groups, keywords.
- `config/staticrypt.json`: fixed salt (keeps "remember me" consistent).
- `scripts/collect.py` -> `data/YYYY-MM-DD.json`, `data/fetch-log-YYYY-MM-DD.json`, `state/seen.json`.
- Agent writes optional `data/digest-YYYY-MM-DD.json` (schema in README below).
- `scripts/build.py` -> `build/` (unencrypted, gitignored) -> `docs/YYYY-MM-DD.html` (encrypted) + `docs/index.html` (dates only).
- `scripts/publish.sh [--skip-collect] [DATE]`: collect, build, encrypt, commit, push.

Digest schema:
```json
{"date":"YYYY-MM-DD","intro":"optional",
 "must_reads":[{"title":"","url":"","source":"","published":"ISO8601","why":"Why it matters for Geniuslink: ..."}],
 "sections":[{"name":"Amazon & retailer programs","items":[{"title":"","url":"","source":"","published":"ISO8601","summary":"optional","paywall":false,"also":{"source":"","url":"","paywall":true}}]}]}
```

Optional item fields: `paywall` (true = main link is paywalled, shown as "(paywall)"); `also` (secondary reference, e.g. the paywalled original when a free version is the main link). Same-day rebuilds reuse .secrets/today-password.txt; set IW_NEW_PASSWORD=1 to force a new one.
