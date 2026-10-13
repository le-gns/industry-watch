#!/usr/bin/env python3
"""Competitor Watch builder. Renders data/competitors-digest-DATE.json (or the raw
data/competitors-DATE.json) to build/competitors/DATE.html, encrypts it with the SAME daily
password as Industry Watch (.secrets/today-password.txt, must be dated DATE), writes
docs/competitors/DATE.html and docs/competitors/index.html."""
import json, sys, os, shutil, subprocess, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B
ROOT, DATE, esc = B.ROOT, B.DATE, B.esc
CC = json.loads((ROOT / 'config/competitors.json').read_text())
TYPE = {'news': 'News', 'wire': 'Press release', 'blog': 'Blog', 'social': 'Social', 'reddit': 'Reddit', 'product': 'Product change'}

def li(i):
    i = dict(i); t = TYPE.get(i.get('type'))
    if t: i['source'] = f'{t} · {i.get("source", "")}'
    return B.item_li(i)

def render():
    nice = dt.date.fromisoformat(DATE).strftime('%A %-d %B %Y')
    dp, rp = ROOT / f'data/competitors-digest-{DATE}.json', ROOT / f'data/competitors-{DATE}.json'
    parts = [f'<header><h1>Competitor Watch</h1><p class="d">{nice} · <a href="../{DATE}.html">Industry Watch</a></p></header>']
    if dp.exists():
        d = json.loads(dp.read_text()); comps = d['competitors']
        if d.get('summary'):
            parts.append('<section class="top"><h2>What competitors did</h2><ul>' + ''.join(f'<li>{esc(s)}</li>' for s in d['summary']) + '</ul></section>')
    elif rp.exists():
        raw = json.loads(rp.read_text())
        parts.append('<p class="note">Unedited feed: no curated digest for today.</p>')
        comps = [{**c, 'items': [i for i in raw['items'] if i['competitor'] == c['id']]} for c in CC['competitors']]
    else:
        sys.exit(f'no competitors data for {DATE}')
    comps = sorted(comps, key=lambda c: not c.get('priority'))
    active = [c for c in comps if c.get('items')]
    parts.append('<nav>' + ''.join(f'<a href="#{c["id"]}">{esc(c["name"])} ({len(c["items"])})</a>' for c in active) + '</nav>')
    for c in comps:
        tag = ' <span class="n">priority</span>' if c.get('priority') else ''
        note = f'<p class="sum">{esc(c["note"])}</p>' if c.get('note') else ''
        body = '<ul>' + ''.join(li(i) for i in c['items']) + '</ul>' if c.get('items') else '<p class="meta">No news</p>'
        parts.append(f'<section id="{c["id"]}"><h2>{esc(c["name"])}{tag}</h2>{note}{body}</section>')
    out = ROOT / f'build/competitors/{DATE}.html'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(B.page(f'Competitor Watch · {DATE}', ''.join(parts)).replace('<footer>Industry Watch · <a href="./">archive</a></footer>', '<footer>Competitor Watch · <a href="./">archive</a> · <a href="../">Industry Watch</a></footer>'))
    return out

def password():
    sec = ROOT / '.secrets'; pf, df = sec / 'today-password.txt', sec / 'today-password-date.txt'
    if not (pf.exists() and df.exists() and df.read_text().strip() == DATE):
        sys.exit(f'no Industry Watch password for {DATE}; run scripts/build.py {DATE} first')
    return pf.read_text().strip()

def encrypt(src, pw):
    tmp = ROOT / 'build/enc-c'; shutil.rmtree(tmp, ignore_errors=True)
    cmd = ['npx', '--no-install', 'staticrypt', str(src), '-d', str(tmp), '--salt', B.SC['salt'], '--short',
           '--remember', str(B.SC.get('remember_days', 30)), '-c', 'false',
           '--template-title', f'Competitor Watch · {DATE}', '--template-instructions', "Enter today's Industry Watch password (shared in Slack).",
           '--template-color-primary', '#1d4ed8', '--template-color-secondary', '#f5f6f8']
    subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, STATICRYPT_PASSWORD=pw), check=True, stdout=subprocess.DEVNULL)
    text = (tmp / src.name).read_text()
    assert 'staticrypt' in text.lower() and 'Competitor Watch</h1>' not in text, 'encryption check failed'
    d = ROOT / 'docs/competitors'; d.mkdir(parents=True, exist_ok=True); shutil.copy(tmp / src.name, d / f'{DATE}.html'); shutil.rmtree(tmp)

def index():
    d = ROOT / 'docs/competitors'
    dates = sorted((p.stem for p in d.glob('????-??-??.html')), reverse=True)
    lis = ''.join(f'<li><a href="{x}.html">{dt.date.fromisoformat(x).strftime("%a %-d %b %Y")}</a></li>' for x in dates)
    body = f'<header><h1>Competitor Watch</h1><p class="d">Archive. Same daily password as <a href="../">Industry Watch</a>.</p></header><section><ul>{lis}</ul></section>'
    (d / 'index.html').write_text(B.page('Competitor Watch', body).replace('<footer>Industry Watch · <a href="./">archive</a></footer>', ''))

if __name__ == '__main__':
    pw = password(); src = render(); encrypt(src, pw); index()
    print(f'built competitors {DATE}; encrypted docs/competitors/{DATE}.html (Industry Watch password reused)')
