#!/usr/bin/env python3
"""Industry Watch collector: fetch all feeds in config/feeds.json, keep recent items,
dedupe, resolve Google News links, skip items published on earlier days (state/seen.json),
write data/YYYY-MM-DD.json and data/fetch-log-YYYY-MM-DD.json. Stdlib only."""
import json, re, sys, time, html, base64, datetime as dt, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / 'config/feeds.json').read_text())
UA = CFG['user_agent']
BROWSER_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
TODAY = dt.date.today().isoformat() if len(sys.argv) < 2 else sys.argv[1]
NOW = dt.datetime.now(dt.timezone.utc)
CUTOFF = NOW - dt.timedelta(hours=CFG['lookback_hours'])
TRACKING = re.compile(r'^(utm_|mc_|_hs|fbclid|gclid|_bhlid|ref$|si$|cmpid)')

def log(*a): print(*a, file=sys.stderr)

def http(url, ua=None, data=None, headers=None, timeout=None):
    h = {'User-Agent': ua or BROWSER_UA, 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout or CFG['timeout_seconds']) as r:
        return r.read(), r.geturl()

def fetch(feed):
    ua = UA if feed['type'] == 'reddit' else BROWSER_UA
    last = None
    for attempt in range(2 if feed['type'] == 'reddit' else 1):
        try:
            body, _ = http(feed['url'], ua=ua)
            return body, None
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}'
            if e.code == 429: time.sleep(5)
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
    return None, last

def strip_html(s):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()

def parse_date(s):
    if not s: return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception: return None
    if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)

def lname(t): return t.rsplit('}', 1)[-1].lower()

def parse(body):
    root = ET.fromstring(body)
    out = []
    for el in root.iter():
        if lname(el.tag) not in ('item', 'entry'): continue
        it = {'title': '', 'url': '', 'published': None, 'snippet': '', 'source': ''}
        for c in el:
            n = lname(c.tag)
            if n == 'title': it['title'] = strip_html(c.text or '')
            elif n == 'link':
                href = c.get('href')
                if href and c.get('rel', 'alternate') == 'alternate': it['url'] = it['url'] or href
                elif c.text: it['url'] = c.text.strip()
            elif n in ('pubdate', 'published', 'updated', 'date') and not it['published']:
                it['published'] = parse_date(c.text)
            elif n in ('description', 'summary', 'content', 'encoded') and not it['snippet']:
                it['snippet'] = strip_html(c.text or '')[:400]
            elif n == 'source': it['source'] = (c.text or '').strip()
        if it['title'] and it['url']: out.append(it)
    return out

def clean_url(u):
    try:
        p = urllib.parse.urlsplit(u)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ''))
    except Exception:
        return u

def norm_key(u):
    p = urllib.parse.urlsplit(clean_url(u))
    return (p.netloc.lower().removeprefix('www.') + p.path.rstrip('/') + ('?' + p.query if p.query else '')).lower()

# --- Google News link resolution ---
def gnews_decode(url):
    m = re.search(r'/(?:rss/)?articles/([^?/]+)', url)
    if not m: return None
    aid = m.group(1)
    try:  # legacy format: URL embedded in the base64 protobuf
        raw = base64.urlsafe_b64decode(aid + '=' * (-len(aid) % 4))
        mm = re.search(rb'https?://[\x21-\x7e]+', raw)
        if mm and not raw[4:].startswith(b'AU_yqL'):
            return mm.group(0).decode('ascii', 'ignore')
    except Exception:
        pass
    try:  # current format: needs signature + timestamp from the article page
        page, _ = http(f'https://news.google.com/rss/articles/{aid}', timeout=15)
        page = page.decode('utf-8', 'ignore')
        sg = re.search(r'data-n-a-sg="([^"]+)"', page); ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts): return None
        inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], aid, int(ts.group(1)), sg.group(1)])
        payload = 'f.req=' + urllib.parse.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
        body, _ = http('https://news.google.com/_/DotsSplashUi/data/batchexecute', data=payload.encode(),
                       headers={'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'}, timeout=15)
        txt = body.decode('utf-8', 'ignore').split('\n\n', 1)[-1]
        arr = json.loads(txt)
        return json.loads(arr[0][2])[1]
    except Exception:
        return None

def kw_match(text):
    t = text.lower(); hits = []
    for grp, kws in CFG['keywords'].items():
        for k in kws:
            if re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t): hits.append(k)
    return sorted(set(hits))

def main():
    state_p = ROOT / 'state/seen.json'
    seen = json.loads(state_p.read_text()) if state_p.exists() else {}
    cache_p = ROOT / 'state/gnews-resolved.json'
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    feeds = CFG['feeds']
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(fetch, feeds))
    fetchlog, items = [], []
    for feed, (body, err) in zip(feeds, results):
        entry = {'id': feed['id'], 'name': feed['name'], 'group': feed['group'], 'type': feed['type'], 'url': feed['url']}
        if err is None:
            try: parsed = parse(body)
            except Exception as e: err = f'parse error: {e}'
        if err:
            entry.update(ok=False, error=err); fetchlog.append(entry); log(f'FAIL {feed["id"]}: {err}'); continue
        kept = 0
        for it in parsed[:CFG['max_items_per_feed']] if feed['type'] != 'source' else parsed:
            if not it['published'] or it['published'] < CUTOFF or it['published'] > NOW + dt.timedelta(hours=2): continue
            title = it['title']; src = it['source']
            if feed['type'] == 'google_news' and ' - ' in title:
                t2, s2 = title.rsplit(' - ', 1); title, src = t2, src or s2
            if feed['type'] == 'reddit': src = src or feed['name'] if feed['name'].startswith('r/') else 'Reddit'
            if feed['type'] == 'reddit' and not feed['name'].startswith('r/'):
                m = re.search(r'reddit\.com/r/([^/]+)', it['url']); src = 'r/' + m.group(1) if m else 'Reddit'
            snippet = it['snippet'] if feed['type'] != 'google_news' else ''
            text = f'{title} {snippet}'
            if any(n in text.lower() for n in CFG['negative_keywords']): continue
            kws = kw_match(text)
            if feed.get('keyword_filter') and not kws: continue
            items.append({'title': title, 'url': it['url'], 'source': src or feed['name'], 'group': feed['group'],
                          'feed_id': feed['id'], 'published': it['published'].isoformat(), 'snippet': snippet[:300],
                          'matched_keywords': kws})
            kept += 1
        entry.update(ok=True, items_in_feed=len(parsed), items_kept=kept); fetchlog.append(entry)
    # resolve Google News links
    gn = [i for i in items if 'news.google.com' in i['url']]
    todo = list({i['url'] for i in gn if i['url'] not in cache})
    with ThreadPoolExecutor(6) as ex:
        for u, r in zip(todo, ex.map(gnews_decode, todo)):
            if r: cache[u] = r
    resolved = 0
    for i in gn:
        if i['url'] in cache: i['url'] = cache[i['url']]; resolved += 1
    for i in items: i['url'] = clean_url(i['url'])
    # dedupe: URL, then title similarity; prefer non-Google-News source feeds, earliest seen
    items.sort(key=lambda i: (i['feed_id'].startswith('gnews'), i['published']))
    out, keys, titles = [], set(), []
    for i in items:
        k = norm_key(i['url'])
        if k in keys: continue
        nt = re.sub(r'[^a-z0-9 ]', '', i['title'].lower())
        if any(SequenceMatcher(None, nt, t).ratio() >= CFG['title_similarity_threshold'] for t in titles): continue
        if seen.get(k) and seen[k] < TODAY: continue
        keys.add(k); titles.append(nt); out.append(i)
    for i in out: seen.setdefault(norm_key(i['url']), TODAY)
    prune = (dt.date.fromisoformat(TODAY) - dt.timedelta(days=45)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= prune}
    out.sort(key=lambda i: (CFG['groups'].index(i['group']), i['published']), reverse=False)
    (ROOT / 'data').mkdir(exist_ok=True)
    meta = {'date': TODAY, 'generated_at': NOW.isoformat(), 'lookback_hours': CFG['lookback_hours'], 'item_count': len(out),
            'google_news_links': len(gn), 'google_news_resolved': resolved,
            'feeds_ok': sum(f['ok'] for f in fetchlog), 'feeds_failed': sum(not f['ok'] for f in fetchlog)}
    (ROOT / f'data/{TODAY}.json').write_text(json.dumps({**meta, 'items': out}, indent=1, ensure_ascii=False))
    (ROOT / f'data/fetch-log-{TODAY}.json').write_text(json.dumps({**meta, 'feeds': fetchlog}, indent=1))
    state_p.write_text(json.dumps(seen, indent=0, sort_keys=True)); cache_p.write_text(json.dumps(cache, indent=0))
    log(json.dumps(meta))

if __name__ == '__main__':
    main()
