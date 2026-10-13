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

## One daily page: Industry Watch + Competitor Watch + Partners Watch
`docs/YYYY-MM-DD.html` has, in order: Industry Watch, Competitor Watch (only competitors with results),
Partners Watch (only partners with results), and "No results found" (comma lists of quiet Competitors and Partners).
Each Watch has its own top summary bullets. Old `docs/competitors/*` URLs are redirect stubs to the main page.
Dedupe: an item in Competitors or Partners is removed from Industry Watch; Competitors beat Partners.

Configs:
- `config/competitors.json`: from Lee's Google Doc 15m05ILayYX1U6_yoEHIrSAJ81cr3JgEJSeJKGgexpKo ("Competitors" section).
- `config/partners.json`: from geniuslink.com/integrations/supported + help center Affiliate Networks. Amazon, Skimlinks,
  Sovrn and Howl are covered under Competitors only. Retailer items must mention the retailer AND an affiliate/creator word.
- Both: verified X handles + ids (`x_ids`), `linkedin_slug` (verified via the page's Organization website), match_terms.
- LinkedIn: `scripts/linkedin.py` reads the logged-out public company page (ld+json, ~10 latest posts). No login, no bridge.
  Best effort; it can be rate-limited (429/999). Re-check slugs occasionally with `scripts/linkedin_verify.py` (`--force` to redo all).

Digest files (agent-written; empty groups are simply omitted):
```json
// data/competitors-digest-DATE.json  (use "partners" as the key in data/partners-digest-DATE.json)
{"date":"","summary":["3-5 plain bullets"],"competitors":[{"id":"","name":"","priority":true,"items":[{"title":"","url":"","source":"","published":"","type":"news|wire|blog|social|reddit|product","why":"optional","also":{"source":"","url":"","paywall":true},"paywall":false}]}]}
```

### Daily steps
1. `python3 scripts/collect.py DATE` (Industry Watch raw)
2. X posts (agent, X connector `get_users_posts`, start_time = now-30h) for `x_ids` in each config ->
   `data/competitors-x-DATE.json` and `data/partners-x-DATE.json` (`{"posts":[{"handle","competitor"|"partner","created_at","url","text"}]}`; write `{"posts":[]}` if none).
3. `python3 scripts/collect_competitors.py DATE` and `python3 scripts/collect_competitors.py --partners DATE` (each ~1-2 min incl. LinkedIn)
4. Curate `data/digest-DATE.json`, `data/competitors-digest-DATE.json`, `data/partners-digest-DATE.json`.
5. `scripts/publish.sh --skip-collect DATE` (builds the single page; new password on the first build of the day,
   same-day rebuilds reuse `.secrets/today-password.txt`), then verify the live page and DM Lee the link + password.
