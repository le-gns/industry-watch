#!/usr/bin/env python3
"""Competitor Watch collector: fetch feeds in config/competitors.json (Google News, wires, blog RSS,
YouTube RSS, Reddit search RSS, WordPress.org plugin versions), merge optional X posts from
data/competitors-x-DATE.json, dedupe against state/competitors-seen.json, write
data/competitors-DATE.json and data/competitors-fetch-log-DATE.json. Stdlib only."""
import json, re, sys, time, html, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as C  # reuse http/parse/gnews_decode/clean_url/norm_key

ROOT = C.ROOT
CFG = json.loads((ROOT / 'config/competitors.json').read_text())
TODAY = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
NOW = dt.datetime.now(dt.timezone.utc)
CUTOFF = NOW - dt.timedelta(hours=CFG['lookback_hours'])
NAMES = {c['id']: c['name'] for c in CFG['competitors']}
TERMS = {c['id']: c['match_terms'] for c in CFG['competitors']}
PRIO = {c['id'] for c in CFG['competitors'] if c['priority']} - {'amazon'}

def match(text, comp):
    t = text.lower()
    ids = [comp] if comp else list(TERMS)
    for cid in ids:
        if any(re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t) for k in TERMS[cid]): return cid
    return None

def fetch(feed):
    if feed['type'] == 'reddit': time.sleep(1)
    ua = C.UA if feed['type'] == 'reddit' else C.BROWSER_UA
    last = None
    for _ in range(2):
        try:
            body, _ = C.http(feed['url'], ua=ua); return body, None
        except C.urllib.error.HTTPError as e:
            last = f'HTTP {e.code}'
            if e.code == 429: time.sleep(6)
            else: break
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
    return None, last

def wporg(feed, body, wpstate):
    d = json.loads(body); slug = feed['slug']; ver = d.get('version'); prev = wpstate.get(slug)
    wpstate[slug] = ver
    note = {'version': ver, 'last_updated': d.get('last_updated'), 'active_installs': d.get('active_installs'), 'rating': d.get('rating')}
    if prev and prev != ver or (not prev and d.get('last_updated', '')[:10] >= (NOW - dt.timedelta(hours=CFG['lookback_hours'])).strftime('%Y-%m-%d')):
        return [{'title': f'{html.unescape(d["name"])}: new version {ver}' + (f' (was {prev})' if prev else ''),
                 'url': f'https://wordpress.org/plugins/{slug}/#developers', 'source': 'WordPress.org', 'published': NOW.isoformat(),
                 'snippet': f'Last updated {d.get("last_updated")}'}], note
    return [], note

def main():
    sp = ROOT / 'state/competitors-seen.json'; seen = json.loads(sp.read_text()) if sp.exists() else {}
    wp_p = ROOT / 'state/competitors-wporg.json'; wpstate = json.loads(wp_p.read_text()) if wp_p.exists() else {}
    cache_p = ROOT / 'state/gnews-resolved.json'; cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    feeds = CFG['feeds']
    with ThreadPoolExecutor(6) as ex: results = list(ex.map(fetch, feeds))
    log, items = [], []
    for f, (body, err) in zip(feeds, results):
        e = {k: f[k] for k in ('id', 'competitor', 'type', 'url')}
        if err: e.update(ok=False, error=err); log.append(e); continue
        try:
            if f['type'] == 'wporg':
                new, note = wporg(f, body, wpstate); e.update(ok=True, plugin=note)
                for it in new: items.append({**it, 'competitor': f['competitor'], 'feed_id': f['id'], 'type': 'product'})
                log.append(e); continue
            parsed = C.parse(body)
        except Exception as ex_:
            e.update(ok=False, error=f'parse error: {ex_}'); log.append(e); continue
        kept = 0
        for it in parsed[:CFG['max_items_per_feed']]:
            p = it['published']
            if not p or p < CUTOFF or p > NOW + dt.timedelta(hours=2): continue
            title, src = it['title'], it['source']
            if f['type'] == 'google_news' and ' - ' in title: title, s2 = title.rsplit(' - ', 1); src = src or s2
            if f['type'] == 'reddit':
                m = re.search(r'reddit\.com/r/([^/]+)', it['url']); src = 'r/' + m.group(1) if m else 'Reddit'
            comp = f['competitor']
            if f['type'] in ('google_news', 'reddit'):
                text = f"{title} {it['snippet']}"
                if f['type'] == 'reddit' and any(x in text.lower() for x in CFG['reddit_exclude']): continue
                if not (f['type'] == 'google_news' and comp in PRIO):
                    comp = match(text, comp)
                    if not comp: continue
            if f['type'] == 'youtube': src = 'YouTube'
            if f['type'] == 'rss': src = src or C.urllib.parse.urlsplit(f['url']).netloc.removeprefix('www.')
            items.append({'title': title, 'url': it['url'], 'source': src, 'competitor': comp, 'feed_id': f['id'],
                          'type': {'google_news': 'news', 'rss': 'blog', 'youtube': 'social', 'reddit': 'reddit'}[f['type']],
                          'published': p.isoformat(), 'snippet': (it['snippet'] if f['type'] != 'google_news' else '')[:300]})
            kept += 1
        e.update(ok=True, items_in_feed=len(parsed), items_kept=kept); log.append(e)
    xp = ROOT / f'data/competitors-x-{TODAY}.json'
    if xp.exists():
        for p in json.loads(xp.read_text()).get('posts', []):
            items.append({'title': p['text'][:200], 'url': p['url'], 'source': f'X @{p["handle"]}', 'competitor': p['competitor'],
                          'feed_id': f'x-{p["handle"]}', 'type': 'social', 'published': p['created_at'], 'snippet': p['text'][:300]})
        log.append({'id': 'x-import', 'type': 'x', 'ok': True, 'url': str(xp.name), 'items_kept': len(json.loads(xp.read_text()).get('posts', []))})
    gn = [i for i in items if 'news.google.com' in i['url']]
    todo = list({i['url'] for i in gn if i['url'] not in cache})
    with ThreadPoolExecutor(6) as ex:
        for u, r in zip(todo, ex.map(C.gnews_decode, todo)):
            if r: cache[u] = r
    for i in gn: i['url'] = cache.get(i['url'], i['url'])
    for i in items: i['url'] = C.clean_url(i['url'])
    items.sort(key=lambda i: (i['feed_id'].startswith(('gn-', 'wire-')), i['published']))
    out, keys = [], set()
    for i in items:
        k = C.norm_key(i['url'])
        if k in keys or (seen.get(k) and seen[k] < TODAY): continue
        keys.add(k); out.append(i)
    for i in out: seen.setdefault(C.norm_key(i['url']), TODAY)
    prune = (dt.date.fromisoformat(TODAY) - dt.timedelta(days=45)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= prune}
    order = [c['id'] for c in CFG['competitors']]
    out.sort(key=lambda i: (order.index(i['competitor']) if i['competitor'] in order else 999, i['published']))
    meta = {'date': TODAY, 'generated_at': NOW.isoformat(), 'item_count': len(out),
            'feeds_ok': sum(x['ok'] for x in log), 'feeds_failed': sum(not x['ok'] for x in log)}
    (ROOT / f'data/competitors-{TODAY}.json').write_text(json.dumps({**meta, 'items': out}, indent=1, ensure_ascii=False))
    (ROOT / f'data/competitors-fetch-log-{TODAY}.json').write_text(json.dumps({**meta, 'feeds': log}, indent=1))
    sp.write_text(json.dumps(seen, indent=0, sort_keys=True)); wp_p.write_text(json.dumps(wpstate, indent=1))
    cache_p.write_text(json.dumps(cache, indent=0))
    print(json.dumps(meta), file=sys.stderr)

if __name__ == '__main__': main()
