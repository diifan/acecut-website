#!/usr/bin/env python3
"""Standalone product-keyword audit. Read-only against production state.

Writes ONLY <home>/product-audit.json and <home>/reviewed-workflow-sources.proposed.json.
Never writes keyword-pool.sqlite, never adds/changes columns (production intent_key untouched),
never writes the controller CSVs. Every audited row must come from a raw CSV whose sha256 matches
the manifest (or an explicit --csv PATH:SHA256); metrics are validated; the original gate
(volume>100 and KD<30) is reported, never altered. Rows below it are research and
counts_toward_inventory=false. The proposed-sources file feeds the v2 bridge only after a human
fills url/must_contain/reviewed_by (the bridge rejects it until then).

  python3 audit.py --home HOME [--csv PATH:SHA256 ...]
"""
import argparse, csv, datetime, hashlib, io, json, math, re, sqlite3, unicodedata
from pathlib import Path
from urllib.parse import urlsplit

PUBLISHED = ('published', 'reserved', 'verified')
BRAND = re.compile(r'\b(swing ?vision|spintip|tenniscut|tennis ?cut|match ?cut ?pro|unforce|playsight)\b')
VIDEO_GAME = re.compile(r'\b(video ?games?|ps[2-5]|xbox|nintendo|steam|simulator|mario|tennis clash|wii)\b')
TENNIS = re.compile(r'\b(tennis|forehand|backhand|serve|serving|volley|rally|racket|racquet|court)\b')
RECORD = re.compile(r'\b(recording|recorder|filming)\b|\b(record|film)\s+(your|my|a|the|yourself|myself|tennis|match|matches|practice|serve|swing|lesson|game|session)\b|\bhow to (record|film)\b')
RECORD_NEG = re.compile(r'\b(head to head|h2h|win ?loss|career|world record|all time|fastest|highest|most|prize|earnings|rankings?|stats?|statistics|results?|age|net worth|titles?)\b')
CAMERA = re.compile(r'\b(cameras?|tripods?|phone mount|camera (setup|angle|placement))\b')
BALL = re.compile(r'\bball (tracking|tracker|trail|trace)\b|\btracer\b')
SLOW = re.compile(r'\bslow ?(motion|mo)\b|\bslo ?mo\b')
ANALYSIS = re.compile(r'\b(video|swing|stroke|serve|forehand|backhand) analy[sz](is|er)\b|\banaly[sz]e (my|your) (swing|serve|forehand|backhand|game|match|video)\b')
PLAYERS = {'federer', 'djokovic', 'nadal', 'alcaraz', 'sinner', 'murray', 'sampras', 'agassi', 'serena', 'williams', 'sabalenka',
           'swiatek', 'medvedev', 'zverev', 'tsitsipas', 'kyrgios', 'osaka', 'gauff', 'wawrinka', 'fritz', 'ruud', 'tiafoe', 'dimitrov'}
STROKES = {'serve', 'forehand', 'backhand', 'volley', 'lob', 'overhead', 'slice'}
MODS = {'best', 'free', 'iphone', 'android', 'ipad', 'gopro', 'tripod', 'solo', 'doubles', 'singles', 'beginner', 'coach', 'ios'}
# Terms the production FAMILIES/router do not know; surfaced so a human can decide on taxonomy.
TERM_WATCH = ['slow motion', 'slow mo', 'tripod', 'phone mount', 'analysis', 'analyzer', 'swing stick', 'highlight', 'auto cut', 'ball tracking']


def norm(v): return ' '.join(unicodedata.normalize('NFKC', str(v)).split()).casefold()
def passes_gate(volume, kd): return volume > 100 and kd < 30


def product_intent(keyword, demand_url=""):
    w = norm(keyword); toks = set(re.findall(r'[a-z0-9]+', w))
    out = lambda cat, cluster='', why='': dict(category=cat, cluster=cluster, reason=why)
    if BRAND.search(w): return out('competitor_review', 'competitor|' + w, 'competitor brand: facts must come from that vendor; no AceCut claims')
    if VIDEO_GAME.search(w): return out('not_product', why='video game')
    if re.search(r'\brecord\b', w) and re.search(r'(fastest|speed-record|world-record|records)', urlsplit(demand_url).path, re.I) and not re.search(r'\b(recording|filming|camera|video)\b', w):
        return out('not_product', why='ranking source identifies sporting record, not recording footage')
    if BALL.search(w) and CAMERA.search(w): return out('adjacent_workflow', 'ball_tracking_hardware|', 'hardware camera intent')
    if not TENNIS.search(w): return out('not_product', why='no tennis context')
    strokes, mods = sorted(toks & STROKES), sorted(toks & MODS)
    if SLOW.search(w):
        if toks & PLAYERS: return out('third_party_footage', 'slow_motion|' + '+'.join(sorted(toks & PLAYERS) + strokes), 'wants pro footage AceCut cannot supply')
        return out('capability_unconfirmed', 'slow_motion|' + '+'.join(strokes + mods), 'slow-motion capability not confirmed for AceCut')
    if ANALYSIS.search(w): return out('capability_unconfirmed', 'video_analysis|' + '+'.join(strokes), 'AceCut does not evaluate technique; page could only be a review workflow')
    if BALL.search(w):
        if CAMERA.search(w): return out('adjacent_workflow', 'ball_tracking_hardware|', 'hardware camera intent')
        return out('core_video_workflow', 'ball_tracking|' + '+'.join(mods), 'AceCut ball trail')
    if RECORD.search(w) and not RECORD_NEG.search(w): return out('core_video_workflow', 'record_setup|' + '+'.join(sorted(set(mods) | set(strokes))), 'recording workflow')
    if CAMERA.search(w): return out('core_video_workflow', 'camera|' + '+'.join(mods), 'camera choice/setup (kept separate from recording)')
    return out('not_product', why='no product-workflow term')


def metric(v):
    n = float(str(v).replace(',', ''))
    if not math.isfinite(n) or n < 0: raise ValueError('invalid metric')
    return n


def parse_row(row):
    g = lambda *ns: next((row[n] for n in ns if row.get(n) not in (None, '')), '')
    kw = g('keyword', 'Keyword')
    if not norm(kw): raise ValueError('empty keyword')
    vol, kd = metric(g('volume', 'Search Volume')), metric(g('kd', 'Keyword Difficulty'))
    if vol <= 0: raise ValueError('volume must be > 0')
    if kd > 100: raise ValueError('kd out of range')
    ts = str(g('metric_timestamp', 'Timestamp'))
    try: datetime.date.fromisoformat(ts[:10])
    except ValueError: raise ValueError('bad metric timestamp')
    u = urlsplit(g('evidence_url', 'URL', 'source_url'))
    if u.scheme not in ('http', 'https') or not u.hostname or u.username: raise ValueError('bad source url')
    return dict(keyword=kw.strip(), normalized=norm(kw), volume=vol, kd=kd, metric_timestamp=ts, demand_url=u.geturl())


def manifest_sources(home):
    f = Path(home) / 'keyword-input.json'
    if not f.exists(): return []
    manifest = Path(json.loads(f.read_text())['manifest_path']); data = json.loads(manifest.read_text()); out = []
    for s in data['sources']:
        p = Path(s.get('archive') or s.get('local_path') or s.get('path') or s.get('source_path', ''))
        out.append((p if p.is_absolute() else manifest.parent / p, s.get('sha256')))
    return out


def load_rows(sources):
    best, invalid = {}, {}
    for path, sha in sources:
        raw = Path(path).read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if not sha or digest != sha: raise ValueError(f'raw CSV hash mismatch or missing: {path}')
        for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
            try: r = parse_row(row)
            except ValueError as e: invalid[str(e)] = invalid.get(str(e), 0) + 1; continue
            r.update(source_path=str(Path(path).resolve()), source_sha256=digest)
            old = best.get(r['normalized'])
            if not old or r['metric_timestamp'] > old['metric_timestamp']: best[r['normalized']] = r
    return list(best.values()), invalid


def published_clusters(home):
    f = Path(home) / 'keyword-pool.sqlite'; out = {}
    if not f.exists(): return out
    c = sqlite3.connect(f'file:{f}?mode=ro', uri=True); c.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in c.execute('PRAGMA table_info(keywords)')}
        for r in c.execute('select * from keywords where status in (?,?,?)', PUBLISHED):
            i = product_intent(r['keyword'])
            if i['category'] == 'core_video_workflow':
                out.setdefault(i['cluster'], []).append(dict(keyword=r['keyword'], status=r['status'], url=r['published_url'] if 'published_url' in cols else None))
    finally: c.close()
    return out


def action(cat, passes, covered):
    if cat == 'competitor_review': return 'hold_competitor_claims'
    if cat == 'third_party_footage': return 'skip_cannot_supply_footage'
    if cat == 'adjacent_workflow': return 'skip_adjacent_hardware'
    if cat == 'capability_unconfirmed': return 'needs_product_confirmation'
    if covered: return 'already_covered' if passes else 'improve_existing_page'
    return 'needs_reviewed_source' if passes else 'research_only'


def audit(home, extra=()):
    home = Path(home); rows, invalid = load_rows(manifest_sources(home) + list(extra))
    if not rows and not invalid: raise ValueError('no raw CSV sources: manifest binding missing and no --csv given')
    pub = published_clusters(home); items, counts, gaps = [], {}, {}
    for r in rows:
        i = product_intent(r['keyword'], r['demand_url']); counts[i['category']] = counts.get(i['category'], 0) + 1
        gate = passes_gate(r['volume'], r['kd'])
        if i['category'] == 'not_product':
            if gate:
                for t in TERM_WATCH:
                    if t in norm(r['keyword']): gaps.setdefault(t, []).append(r['keyword'])
            continue
        covered = pub.get(i['cluster'], [])
        a = action(i['category'], gate, covered)
        items.append(dict(r, category=i['category'], cluster=i['cluster'], reason=i['reason'], passes_existing_metric_gate=gate, action=a,
                          counts_toward_inventory=False if not gate else None, existing_pages=covered if a in ('improve_existing_page', 'already_covered') else []))
    items.sort(key=lambda x: (-x['volume'], x['kd']))
    stubs = {}
    for it in items:
        if it['action'] == 'needs_reviewed_source': stubs.setdefault(it['cluster'], []).append(it['normalized'])
    proposed = {'entries': [dict(id='proposed-' + re.sub(r'\W+', '-', k).strip('-'), keywords=sorted(v), url=None, must_contain=[], reviewed_by='', reviewed_at='',
                                  note='human must confirm every alias is the same intent and supply a specific (non-homepage) factual source') for k, v in stubs.items()]}
    result = dict(categories=counts, invalid_rows=invalid, rows=items, missing_terminology=dict(sorted(((k, dict(count=len(v), examples=v[:5])) for k, v in gaps.items()))),
                  note='research rows (gate false) do not count toward inventory; no publishable count is claimed')
    for name, data in (('product-audit.json', result), ('reviewed-workflow-sources.proposed.json', proposed)):
        t = home / (name + '.tmp'); t.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n'); t.replace(home / name)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', required=True); p.add_argument('--csv', action='append', default=[])
    a = p.parse_args(); extra = [(x.rsplit(':', 1)[0], x.rsplit(':', 1)[1]) for x in a.csv]
    res = audit(a.home, extra)
    print(json.dumps(dict(categories=res['categories'], invalid_rows=res['invalid_rows'], actions={k: sum(1 for r in res['rows'] if r['action'] == k) for k in {r['action'] for r in res['rows']}}), indent=1))
