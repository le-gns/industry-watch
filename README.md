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

## Competitor Watch (docs/competitors/)
- `config/competitors.json`: competitors from Lee's Google Doc 15m05ILayYX1U6_yoEHIrSAJ81cr3JgEJSeJKGgexpKo ("Competitors" section), verified handles, feeds (google_news, wire, rss, youtube, reddit, wporg), match_terms.
- X posts: the agent reads the verified handles with the X connector (get_users_posts, start_time = now-30h) and writes `data/competitors-x-DATE.json` (`{"posts":[{"handle","competitor","created_at","url","text"}]}`) before collecting.
- `scripts/collect_competitors.py DATE` -> `data/competitors-DATE.json`, fetch log, `state/competitors-seen.json`, `state/competitors-wporg.json`.
- Agent writes `data/competitors-digest-DATE.json`:
```json
{"date":"","summary":["3-5 plain bullets"],"competitors":[{"id":"","name":"","priority":true,"category":"","note":"optional","items":[{"title":"","url":"","source":"","published":"","type":"news|wire|blog|social|reddit|product","why":"optional","also":{"source":"","url":"","paywall":true}}]}]}
```
  Empty items render as "No news". Priority four (Lasso, URLgenius, Button, Amazon) sort first.
- `scripts/publish_competitors.sh [--skip-collect] DATE`: run AFTER `scripts/publish.sh` (reuses the same daily password).
