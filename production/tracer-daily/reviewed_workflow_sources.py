"""Reviewed workflow evidence bridges v2 (replaces the single-mapping REVIEWED module).

Drop-in: refresh() still calls select(HOME). Differences from v1:
 * evidence comes from a reviewed registry file `reviewed-workflow-sources.json` in the home;
 * a keyword is bridged only if it is an EXPLICIT alias of an entry (exact normalized match; no fuzzy
   or token-overlap matching, so different intents cannot be lumped into one source);
 * homepage / root evidence URLs, redirects to a root, thin pages, missing grounding terms,
   pinned-hash drift, expired reviews and ambiguous aliases are all rejected;
 * original demand row stays immutable: demand_url is kept, demand_proven() against the raw CSV is required;
 * the production classify() still has the final say, and the production intent_key() (family|evidence_url)
   is used to refuse a second page for an intent that is already published/reserved/verified/selected;
 * one fetch per entry (none when no row is eligible), explicit home, injectable deps for fixtures.
"""
import datetime, importlib, json, os, re, sqlite3, unicodedata
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

VERSION = '2026-11-26.2'
REGISTRY = 'reviewed-workflow-sources.json'
SELECTABLE = {'candidate', 'fetch_failed', 'needs_template', 'needs_review'}
RETRYABLE_ERRORS = {'source_keyword_identity_not_aligned', 'source_not_tennis_or_insufficient_text',
                    'source_context_inadequate', 'source_fetch_pending'}
PROTECTED = ('published', 'reserved', 'verified')


def norm(v):
    return ' '.join(unicodedata.normalize('NFKC', str(v)).split()).casefold()


def default_deps():
    m = {k: importlib.import_module(name) for k, name in
         {'runtime': 'common', 'semrush': 'keyword_input', 'fetch': 'source_cache'}.items()}
    return SimpleNamespace(home=m['runtime'].HOME, read=m['runtime'].read, atomic=m['runtime'].atomic, now=m['runtime'].now,
                           originals=m['semrush'].originals, demand_proven=m['semrush'].demand_proven,
                           fetch=m['fetch'].fetch, classify=m['fetch'].classify, intent_key=m['fetch'].intent_key)


def entry_problem(e, today=None):
    if not isinstance(e, dict): return 'entry is not an object'
    try:
        u = urlsplit(str(e.get('url', ''))); port = u.port
    except ValueError:
        return 'invalid evidence url'
    if u.scheme != 'https' or not u.hostname or u.username or u.password or port not in (None, 443):
        return 'evidence url must be public https'
    if u.path in ('', '/'): return 'site homepage is not keyword evidence'
    if not e.get('id') or not e.get('keywords'): return 'id and explicit keyword aliases required'
    if len(e.get('must_contain') or []) < 2: return 'at least 2 must_contain grounding terms required'
    if not (e.get('reviewed_by') and e.get('reviewed_at')): return 'review metadata missing'
    try: reviewed = datetime.date.fromisoformat(str(e['reviewed_at'])[:10])
    except ValueError: return 'bad reviewed_at'
    if ((today or datetime.date.today()) - reviewed).days > int(e.get('max_age_days', 180)): return 'review expired'
    return None


def load_registry(home, deps):
    data = deps.read(Path(home) / REGISTRY, {}) or {}
    good, problems = [], []
    for e in data.get('entries', []):
        p = entry_problem(e)
        (problems.append({'entry': (e or {}).get('id') if isinstance(e, dict) else None, 'problem': p}) if p else good.append(e))
    return good, problems


def alias_index(entries):
    idx = {}
    for e in entries:
        for k in e['keywords']: idx.setdefault(norm(k), []).append(e)
    return idx


def evidence_problem(e, ev):
    text = (ev.get('text') or '').casefold()
    if ev.get('http') != 200: return 'evidence fetch not 200'
    if urlsplit(ev.get('final_url') or e['url']).path in ('', '/'): return 'evidence redirected to a homepage'
    if len(text) < int(e.get('min_chars', 800)): return 'evidence text too thin'
    if any(norm(t) not in text for t in e['must_contain']): return 'grounding terms missing from evidence'
    if e.get('expected_sha256') and e['expected_sha256'] != ev.get('body_sha256'): return 'evidence changed since review'
    return None


def select(home=None, deps=None):
    d = deps or default_deps(); home = Path(home or d.home)
    if deps is None and home.resolve() != Path(d.home).resolve():
        raise ValueError('Explicit home differs from production dependencies; provide isolated dependencies')
    entries, problems = load_registry(home, d)
    report = dict(version=VERSION, at=d.now(), changes=[], skipped=[], registry_problems=problems)
    file = home / 'keyword-pool.sqlite'; binding = d.read(home / 'keyword-input.json')
    if not entries or not file.exists() or not binding:
        d.atomic(home / 'reviewed-workflow-selection.json', report); return []
    index = d.originals(binding); idx = alias_index(entries)
    c = sqlite3.connect(file, timeout=60); c.row_factory = sqlite3.Row
    try:
        if 'demand_url' not in {r[1] for r in c.execute('PRAGMA table_info(keywords)')}:
            report['skipped'].append({'reason': 'keywords.demand_url column missing; run ingest first'}); d.atomic(home / 'reviewed-workflow-selection.json', report); return []
        occupied = {d.intent_key(dict(r)) for r in c.execute('select * from keywords where status in (?,?,?)', PROTECTED)}
        groups = {}
        for r in c.execute('select * from keywords'):
            hits = idx.get(r['normalized'])
            if not hits or r['status'] in PROTECTED: continue
            if not (r['status'] in SELECTABLE or (r['status'] == 'excluded' and r['error'] in RETRYABLE_ERRORS)): continue
            if len({h['url'] for h in hits}) > 1:
                report['skipped'].append({'keyword': r['keyword'], 'reason': 'ambiguous_reviewed_source'}); continue
            if r['evidence_url'] == hits[0]['url'] and r['demand_url']: continue  # already bridged
            groups.setdefault(hits[0]['id'], (hits[0], []))[1].append(dict(r))
        for e, rows in groups.values():
            path, ev = d.fetch(e['url'])  # one fetch per entry
            bad = evidence_problem(e, ev)
            if bad:
                report['skipped'] += [{'keyword': r['keyword'], 'entry': e['id'], 'reason': bad} for r in rows]; continue
            for row in sorted(rows, key=lambda r: (-r['volume'], r['kd'], len(r['keyword']), r['normalized'])):
                skip = lambda why: report['skipped'].append({'keyword': row['keyword'], 'entry': e['id'], 'reason': why})
                if not d.demand_proven(row, index): skip('demand row not proven in original CSV'); continue
                candidate = {**row, 'evidence_url': e['url']}
                family, err = d.classify(candidate, ev)
                if not family: skip('classify:' + str(err)); continue
                if e.get('family') and e['family'] != family: skip('family drift: ' + family); continue
                key = d.intent_key(candidate)
                if key in occupied: skip('same_intent_already_covered:' + key); continue
                demand = row.get('demand_url') or row['evidence_url']
                c.execute('update keywords set demand_url=?,evidence_url=?,evidence_path=?,status="candidate",error=NULL where normalized=? and status not in ("published","reserved","verified")',
                          (demand, e['url'], str(path), row['normalized']))
                occupied.add(key)
                report['changes'].append(dict(keyword=row['keyword'], entry=e['id'], demand_url=demand, evidence_url=e['url'],
                                              evidence_sha256=ev.get('body_sha256'), family=family, previous_status=row['status'],
                                              previous_error=row['error'], reviewed_by=e['reviewed_by']))
        c.commit()
    finally:
        c.close()
    d.atomic(home / 'reviewed-workflow-selection.json', report)
    return report['changes']
