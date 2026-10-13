"""LinkedIn public company page reader. linkedin.com/company/<slug>/ (logged-out) embeds
ld+json with the Organization (incl. sameAs website) and its ~10 latest SocialMediaPosting items.
No login, no cookies, no RSS bridge. Can be rate-limited (HTTP 999 / authwall) - treat as best effort."""
import json, re, time, urllib.request, urllib.parse
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

def fetch(slug, timeout=15):
    url = f'https://www.linkedin.com/company/{urllib.parse.quote(slug, safe="")}/'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if 'linkedin.com/company/' not in r.geturl(): raise RuntimeError(f'redirected to {r.geturl()[:60]}')
        s = r.read().decode('utf-8', 'ignore')
    org, posts = None, []
    for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S):
        try: d = json.loads(blob)
        except Exception: continue
        for o in d.get('@graph', [d]):
            if o.get('@type') == 'Organization' and not org: org = o
            if o.get('@type') == 'SocialMediaPosting':
                posts.append({'url': o.get('url') or o.get('mainEntityOfPage'), 'published': o.get('datePublished'),
                              'text': re.sub(r'\s+', ' ', o.get('text') or '').strip()})
    return org, posts

def domain(u):
    try: return urllib.parse.urlsplit(u if '//' in u else '//' + u).netloc.lower().removeprefix('www.')
    except Exception: return ''
