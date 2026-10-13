#!/usr/bin/env python3
"""Industry Watch builder.
Renders build/YYYY-MM-DD.html from data/digest-YYYY-MM-DD.json (curated) or, if absent,
from data/YYYY-MM-DD.json (raw, grouped). Generates a fresh daily password (written only to
.secrets/today-password.txt), encrypts the page with staticrypt into docs/, and rebuilds
docs/index.html (dates only). Unencrypted HTML stays in build/ (gitignored)."""
import json, sys, os, html, secrets, subprocess, datetime as dt, shutil, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATE = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
CFG = json.loads((ROOT / 'config/feeds.json').read_text())
SC = json.loads((ROOT / 'config/staticrypt.json').read_text())
TZ = dt.timezone(dt.timedelta(hours=0))
try:
    from zoneinfo import ZoneInfo; TZ = ZoneInfo('Europe/London')
except Exception: pass

WORDS = ('amber apple arch atlas bacon badge bagel basil beach berry birch blaze bloom bolt brave bread brick '
 'brook cabin cable camel candy cargo cedar chalk charm chess chili cider cliff cloud clover cobra comet coral '
 'crane crisp crown daisy delta diner dingo disco dove dune eagle ember fable falcon fern fiddle flame flint '
 'focus forest fox frost fudge gecko ginger glade globe grape gravy hazel heron honey igloo iris ivory jazz '
 'jelly jungle kayak kettle kiwi koala lemon lilac lime llama lotus lunar mango maple marble meadow melon '
 'mint mocha moose nectar noodle nova oak oasis olive orbit otter panda pearl pebble pepper pilot pixel '
 'plum polar poppy prism quail quartz raven reef river robin rocket rose ruby saddle sage salsa satin '
 'scout shell sierra sky sloth solar spice spruce squid stone storm sugar sunny swift tango thyme tiger '
 'toast topaz tulip tundra velvet violet waffle walnut whale willow yeti zebra zesty').split()

def new_password():
    return '-'.join(secrets.choice(WORDS) for _ in range(3)) + f'-{secrets.randbelow(90) + 10}'

def esc(s): return html.escape(str(s or ''), quote=True)

def fmt_time(iso):
    try: return dt.datetime.fromisoformat(iso).astimezone(TZ).strftime('%a %H:%M')
    except Exception: return ''

def item_li(i, extra=''):
    meta = ' · '.join(x for x in [esc(i.get('source')), fmt_time(i.get('published', ''))] if x)
    note = f'<p class="why">{esc(i["why"])}</p>' if i.get('why') else ''
    summ = f'<p class="sum">{esc(i["summary"])}</p>' if i.get('summary') else ''
    if i.get('paywall'): meta += ' · <span class="pw">(paywall)</span>'
    if i.get('also'):
        a = i['also']; meta += f' · (also: <a href="{esc(a["url"])}" target="_blank" rel="noopener noreferrer">{esc(a["source"])}</a>{" – paywall" if a.get("paywall", True) else ""})'
    return (f'<li{extra}><a href="{esc(i["url"])}" target="_blank" rel="noopener noreferrer">{esc(i["title"])}</a>'
            f'<div class="meta">{meta}</div>{summ}{note}</li>')

CSS = '''*{box-sizing:border-box}body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#1f2933;background:#f5f6f8}
main{max-width:760px;margin:0 auto;padding:20px 16px 48px}header h1{font-size:1.5rem;margin:0}header .d{color:#616e7c;margin:2px 0 0}
.note{background:#fff7e6;border:1px solid #f0d9a8;border-radius:8px;padding:8px 12px;font-size:.9rem;margin:16px 0}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0}nav a{font-size:.8rem;background:#e4e7eb;color:#323f4b;padding:4px 10px;border-radius:99px;text-decoration:none}
section{background:#fff;border-radius:10px;padding:4px 16px 8px;margin:16px 0;box-shadow:0 1px 2px rgba(0,0,0,.06)}
h2{font-size:1.05rem;margin:14px 0 6px;color:#243b53}h2 .n{color:#9aa5b1;font-weight:400}ul{list-style:none;padding:0;margin:0}
li{padding:10px 0;border-top:1px solid #eef0f2}li:first-child{border-top:0}li a{color:#1d4ed8;text-decoration:none;font-weight:600}li a:hover{text-decoration:underline}
.meta{font-size:.8rem;color:#7b8794}.why{margin:4px 0 0;font-size:.9rem;color:#3e4c59;border-left:3px solid #93c5fd;padding-left:8px}.pw{color:#b45309}.w{font-size:1.35rem;margin:28px 0 8px;padding-top:8px;border-top:2px solid #1d4ed8}h3{font-size:1.05rem;margin:14px 0 4px}.quiet{font-size:.9rem;color:#52606d}.sum{margin:4px 0 0;font-size:.9rem;color:#52606d}
.top{background:#eff6ff}footer{font-size:.8rem;color:#9aa5b1;text-align:center;margin-top:24px}footer a{color:#7b8794}'''

def page(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}'
            f'<footer>Industry Watch · <a href="./">archive</a></footer></main></body></html>')

def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def ukey(u):
    u = re.sub(r'^https?://(www\.)?', '', (u or '').lower()).split('#')[0].split('?')[0]
    return u.rstrip('/')

WTYPE = {'news': 'News', 'wire': 'Press release', 'blog': 'Blog', 'social': 'Social', 'reddit': 'Reddit', 'product': 'Product change'}

def watch_keys():
    ks = set()
    for kind in ('competitors', 'partners'):
        dp = ROOT / f'data/{kind}-digest-{DATE}.json'
        if dp.exists():
            for g in json.loads(dp.read_text()).get(kind, []): ks |= {ukey(i['url']) for i in g.get('items', [])}
    return ks

def watch_sections(parts):
    """Append Competitor Watch, Partners Watch and 'No results found' from
    data/competitors-digest-DATE.json and data/partners-digest-DATE.json (if present).
    Dedupe: an item in Competitors or Partners is removed from Industry Watch; Competitors beat Partners."""
    watches = []
    for kind, key, title, cfgf in (('competitors', 'competitors', 'Competitor Watch', 'config/competitors.json'),
                                   ('partners', 'partners', 'Partners Watch', 'config/partners.json')):
        dp = ROOT / f'data/{kind}-digest-{DATE}.json'; cp = ROOT / cfgf
        if not dp.exists() or not cp.exists(): continue
        d = json.loads(dp.read_text()); ents = json.loads(cp.read_text())[key]
        watches.append((kind, title, d, d.get(key, []), ents))
    if not watches: return parts
    taken = set(); quiet = {}
    blocks = []
    for kind, title, d, groups, ents in watches:
        groups = sorted(groups, key=lambda g: not g.get('priority'))
        out = []
        for g in groups:
            its = [i for i in g.get('items', []) if ukey(i['url']) not in taken]
            for i in its: taken.add(ukey(i['url']))
            if its: out.append((g, its))
        active = {g['id'] for g, _ in out}
        quiet[kind] = [e['name'] for e in ents if e['id'] not in active]
        blocks.append((kind, title, d, out))
    # dedupe Industry Watch sections already rendered: rebuild them without taken URLs
    parts = [''.join(parts)]
    nav = '<nav>' + '<a href="#industry-watch">Industry Watch</a>' + ''.join(f'<a href="#{kind}-watch">{t}</a>' for kind, t, _, o in blocks if o) + '<a href="#no-results">No results</a></nav>'
    parts.insert(0, '')
    for kind, title, d, out in blocks:
        if not out: continue
        s = f'<section class="watch" id="{kind}-watch"><h2 class="w">{title}</h2>'
        if d.get('summary'): s += '<div class="top"><ul>' + ''.join(f'<li>{esc(b)}</li>' for b in d['summary']) + '</ul></div>'
        for g, its in out:
            tag = ' <span class="n">priority</span>' if g.get('priority') else ''
            s += f'<section id="{kind}-{g["id"]}"><h3>{esc(g["name"])}{tag}</h3><ul>'
            for i in its:
                i = dict(i); t = WTYPE.get(i.get('type'))
                if t: i['source'] = f'{t} · {i.get("source", "")}'
                s += item_li(i)
            s += '</ul></section>'
        parts.append(s + '</section>')
    nr = '<section class="watch" id="no-results"><h2 class="w">No results found</h2>'
    for kind, label in (('competitors', 'Competitors'), ('partners', 'Partners')):
        if kind in quiet: nr += f'<h3>{label}</h3><p class="quiet">{esc(", ".join(quiet[kind]))}</p>'
    parts.append(nr + '</section>')
    return [parts[1].replace('</header>', '</header>' + nav, 1)] + parts[2:]

def render():
    nice = dt.date.fromisoformat(DATE).strftime('%A %-d %B %Y')
    dpath, rpath = ROOT / f'data/digest-{DATE}.json', ROOT / f'data/{DATE}.json'
    parts = [f'<header><h1>Industry Watch</h1><p class="d">{nice}</p></header>']
    if dpath.exists():
        d = json.loads(dpath.read_text()); mode = 'digest'
        wk = watch_keys()
        d['must_reads'] = [i for i in d.get('must_reads', []) if ukey(i['url']) not in wk]
        for sec in d.get('sections', []): sec['items'] = [i for i in sec.get('items', []) if ukey(i['url']) not in wk]
        parts.append('<h2 class="w" id="industry-watch">Industry Watch</h2>')
        if d.get('intro'): parts.append(f'<p>{esc(d["intro"])}</p>')
        secs = d.get('sections', [])
        parts.append('<nav>' + '<a href="#must-reads">Must reads</a>' + ''.join(f'<a href="#{slug(s["name"])}">{esc(s["name"])}</a>' for s in secs if s.get('items')) + '</nav>')
        parts.append('<section class="top" id="must-reads"><h2>Top 5 must reads</h2><ul>' + ''.join(item_li(i) for i in d.get('must_reads', [])[:5]) + '</ul></section>')
        for s in secs:
            if s.get('items'):
                parts.append(f'<section id="{slug(s["name"])}"><h2>{esc(s["name"])} <span class="n">{len(s["items"])}</span></h2><ul>' + ''.join(item_li(i) for i in s['items']) + '</ul></section>')
    elif rpath.exists():
        d = json.loads(rpath.read_text()); mode = 'raw'
        parts.append('<p class="note">Unedited feed: no curated digest was written for today, so this is every collected item from the last ~30 hours, grouped by section.</p>')
        groups = [(g, sorted([i for i in d['items'] if i['group'] == g], key=lambda i: i['published'], reverse=True)) for g in CFG['groups']]
        parts.append('<nav>' + ''.join(f'<a href="#{slug(g)}">{esc(g)} ({len(its)})</a>' for g, its in groups if its) + '</nav>')
        for g, its in groups:
            if its:
                parts.append(f'<section id="{slug(g)}"><h2>{esc(g)} <span class="n">{len(its)}</span></h2><ul>' + ''.join(item_li(i) for i in its) + '</ul></section>')
    else:
        sys.exit(f'No data/digest-{DATE}.json or data/{DATE}.json; run collect.py first')
    parts = watch_sections(parts)
    out = ROOT / f'build/{DATE}.html'; out.parent.mkdir(exist_ok=True)
    out.write_text(page(f'Industry Watch · {DATE}', ''.join(parts)))
    return out, mode

def encrypt(src, password):
    tmp = ROOT / 'build/enc'; shutil.rmtree(tmp, ignore_errors=True)
    env = dict(os.environ, STATICRYPT_PASSWORD=password)
    cmd = ['npx', '--no-install', 'staticrypt', str(src), '-d', str(tmp), '--salt', SC['salt'], '--short',
           '--remember', str(SC.get('remember_days', 30)), '-c', 'false',
           '--template-title', f'Industry Watch · {DATE}', '--template-instructions', "Enter today's password (shared in Slack).",
           '--template-color-primary', '#1d4ed8', '--template-color-secondary', '#f5f6f8']
    subprocess.run(cmd, cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    enc = tmp / src.name; text = enc.read_text()
    assert 'staticrypt' in text.lower() and 'Industry Watch</h1>' not in text, 'encryption check failed'
    (ROOT / 'docs').mkdir(exist_ok=True); shutil.copy(enc, ROOT / f'docs/{DATE}.html'); shutil.rmtree(tmp)

def index():
    dates = sorted((p.stem for p in (ROOT / 'docs').glob('????-??-??.html')), reverse=True)
    lis = ''.join(f'<li><a href="{d}.html">{dt.date.fromisoformat(d).strftime("%a %-d %b %Y")}</a></li>' for d in dates)
    body = f'<header><h1>Industry Watch</h1><p class="d">Archive. Each day has its own password.</p></header><section><ul>{lis}</ul></section>'
    (ROOT / 'docs/index.html').write_text(page('Industry Watch', body).replace('<footer>Industry Watch · <a href="./">archive</a></footer>', ''))
    (ROOT / 'docs/.nojekyll').write_text('')
    # retired separate Competitor Watch pages: keep URLs alive as redirects to the main daily page
    cd = ROOT / 'docs/competitors'
    if cd.exists():
        stub = lambda to: (f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">'
                           f'<meta http-equiv="refresh" content="0; url={to}"><link rel="canonical" href="{to}">'
                           f'<title>Moved</title><p>Competitor Watch is now part of the daily page: <a href="{to}">{to}</a></p>')
        for f in cd.glob('????-??-??.html'): f.write_text(stub(f'../{f.stem}.html#competitors-watch'))
        (cd / 'index.html').write_text(stub('../'))

if __name__ == '__main__':
    src, mode = render()
    sec = ROOT / '.secrets'; sec.mkdir(mode=0o700, exist_ok=True)
    pf = sec / 'today-password.txt'; df = sec / 'today-password-date.txt'
    # same-day rebuilds reuse the existing password (set IW_NEW_PASSWORD=1 to force a new one)
    if pf.exists() and df.exists() and df.read_text().strip() == DATE and os.environ.get('IW_NEW_PASSWORD') != '1':
        pw = pf.read_text().strip()
    else:
        pw = new_password()
        pf.write_text(pw + '\n'); os.chmod(pf, 0o600); df.write_text(DATE + '\n')
    encrypt(src, pw)
    index()
    print(f'built {DATE} ({mode}); encrypted page docs/{DATE}.html; password written to .secrets/today-password.txt')
