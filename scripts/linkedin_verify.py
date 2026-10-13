#!/usr/bin/env python3
"""One-off/occasional: find and verify LinkedIn company slugs for competitors and partners.
A slug is accepted only if the page's Organization sameAs website matches the entity's domain."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import linkedin as L
ROOT = Path(__file__).resolve().parent.parent
def cands(e, dom):
    c = list(e.get('linkedin_candidates') or [])
    base = dom.split('.')[0] if dom else ''
    for s in [base, re.sub(r'[^a-z0-9]+', '-', e['name'].lower().split(' (')[0].split(' /')[0]).strip('-'), dom.replace('.', '-') if dom else '']:
        if s and s not in c: c.append(s)
    return c
for fn, key in (('config/competitors.json', 'competitors'), ('config/partners.json', 'partners')):
    cfg = json.loads((ROOT / fn).read_text())
    for e in cfg[key]:
        if e.get('linkedin_slug') and '--force' not in sys.argv: continue
        dom = e.get('domain') or (L.domain(e['urls'][0]) if e.get('urls') else '')
        e['linkedin_slug'] = None; e['linkedin_note'] = ''
        for s in cands(e, dom)[:4]:
            try: org, posts = L.fetch(s)
            except Exception as ex: e['linkedin_note'] = f'{s}: {str(ex)[:40]}'; time.sleep(1.5); continue
            time.sleep(1.5)
            same = L.domain(str((org or {}).get('sameAs', '')))
            if org and dom and (same.endswith(dom.split('/')[0]) or dom.split('/')[0].endswith(same) and same):
                e['linkedin_slug'] = s; e['linkedin_note'] = f'verified: {org.get("name")} ({same}), {len(posts)} public posts'; break
            e['linkedin_note'] = f'{s}: org={(org or {}).get("name")} site={same} (no match)'
        print(key, e['id'], e['linkedin_slug'], e['linkedin_note'], flush=True)
    (ROOT / fn).write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
