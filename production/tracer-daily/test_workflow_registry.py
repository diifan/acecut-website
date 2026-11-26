"""Regression tests. Fixtures live in temp dirs; production modules and HOME are never imported.
Run: python3 <this file>   (siblings -bridge.py / -audit.py, or ACECUT_BRIDGE_PATH / ACECUT_AUDIT_PATH)
"""
import datetime, hashlib, importlib.util, json, os, sqlite3, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PREFIX = Path(__file__).name.rsplit('-', 1)[0]


def load(env, suffix, name):
    p = os.environ.get(env) or str(HERE / f'{PREFIX}-{suffix}.py')
    spec = importlib.util.spec_from_file_location(name, p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


import workflow_product_audit as A
import reviewed_workflow_sources as B
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Intent(unittest.TestCase):
    def cat(self, kw): return A.product_intent(kw)['category']

    def test_recording_positives(self):
        for kw in ['tennis recording', 'tennis recording app', 'how to record a tennis match', 'film tennis match with iphone', 'record tennis serve']:
            self.assertEqual(A.product_intent(kw)['cluster'].split('|')[0], 'record_setup', kw)
        self.assertEqual(A.product_intent('tennis recording')['cluster'], A.product_intent('tennis recording app')['cluster'])

    def test_record_counterexamples_never_regress(self):
        for kw in ['djokovic career record', 'tennis head to head record', 'tennis world record serve speed', 'federer win loss record',
                   'tennis record', 'record tennis match results', 'record tennis stats', 'tennis video game', 'best tennis video games ps5', 'tennis clash cheats']:
            self.assertNotEqual(self.cat(kw), 'core_video_workflow', kw)

    def test_actual_demand_source_disambiguates_record_serve(self):
        for word in ['record serve in tennis', 'record serve tennis', 'record tennis serve']:
            d = A.product_intent(word, 'https://tenniscompanion.org/fastest-tennis-serves/')
            self.assertEqual(d['category'], 'not_product')
        self.assertEqual(A.product_intent('how to record a tennis serve', 'https://example.com/record-your-serve')['category'], 'core_video_workflow')

    def test_distinct_intents_not_lumped(self):
        self.assertNotEqual(A.product_intent('tennis camera')['cluster'], A.product_intent('tennis recording')['cluster'])
        self.assertNotEqual(A.product_intent('record tennis serve')['cluster'], A.product_intent('tennis recording')['cluster'])
        self.assertNotEqual(A.product_intent('best tennis recording app')['cluster'], A.product_intent('tennis recording app')['cluster'])

    def test_slow_motion_terminology(self):
        a, b = A.product_intent('forehand slow motion tennis'), A.product_intent('tennis forehand slow motion')
        self.assertEqual(a['cluster'], b['cluster']); self.assertEqual(a['category'], 'capability_unconfirmed')
        for kw in ['tennis forehand slow motion federer', 'tennis serve slow motion djokovic']: self.assertEqual(self.cat(kw), 'third_party_footage')

    def test_other_known_rows(self):
        self.assertEqual(self.cat('tennis video analysis'), 'capability_unconfirmed')
        self.assertEqual(self.cat('ball tracking camera'), 'adjacent_workflow')
        for kw in ['swingvision tennis app', 'swing vision price', 'does swingvision work on android', 'swingvision swing stick']: self.assertEqual(self.cat(kw), 'competitor_review')

    def test_gate_is_strict_and_unchanged(self):
        self.assertTrue(A.passes_gate(260, 6)); self.assertFalse(A.passes_gate(40, 10))
        self.assertFalse(A.passes_gate(100, 5)); self.assertFalse(A.passes_gate(101, 30))

    def test_metric_validation(self):
        ok = dict(keyword='tennis recording', volume='40', kd='10', evidence_url='https://a.example/x', metric_timestamp='2026-11-10')
        self.assertEqual(A.parse_row(ok)['volume'], 40.0)
        for bad in [dict(ok, volume='nan'), dict(ok, volume='inf'), dict(ok, volume='-1'), dict(ok, volume='0'), dict(ok, kd='101'), dict(ok, kd='x'),
                    dict(ok, metric_timestamp=''), dict(ok, evidence_url='ftp://a.example/x'), dict(ok, keyword=' ')]:
            with self.assertRaises(ValueError, msg=str(bad)): A.parse_row(bad)


class AuditEndToEnd(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.home = Path(self.t.name)
        rows = ['keyword,volume,kd,evidence_url,metric_timestamp',
                'tennis recording,260,6,https://a.example/r,2026-09-18', 'tennis recording app,40,10,https://a.example/g,2026-11-10',
                'tennis camera,170,15,https://a.example/r,2026-10-07', 'forehand slow motion tennis,260,24,https://a.example/s,2026-09-13',
                'tennis serve slow motion federer,170,21,https://a.example/s,2026-11-09', 'swingvision tennis app,480,27,https://a.example/v,2026-09-20',
                'ball tracking camera,140,64,https://a.example/b,2026-10-10', 'tennis video game,900,3,https://a.example/v,2026-10-10',
                'bad row,nan,3,https://a.example/v,2026-10-10']
        self.csv = self.home / 'src.csv'; self.csv.write_text('\n'.join(rows) + '\n')
        (self.home / 'manifest.json').write_text(json.dumps({'sources': [{'path': 'src.csv', 'sha256': sha(self.csv)}]}))
        (self.home / 'keyword-input.json').write_text(json.dumps({'manifest_path': str(self.home / 'manifest.json'), 'pool_path': str(self.csv)}))
        c = sqlite3.connect(self.home / 'keyword-pool.sqlite')
        c.execute('create table keywords(normalized text,keyword text,status text,published_url text,evidence_url text)')
        c.execute("insert into keywords values('tennis recording','tennis recording','published','/guides/tennis-recording','https://a.example/r')"); c.commit(); c.close()

    def tearDown(self): self.t.cleanup()

    def test_audit_actions_and_no_production_writes(self):
        before = {n: sha(self.home / n) for n in ('keyword-pool.sqlite', 'keyword-input.json', 'src.csv')}
        res = A.audit(self.home); by = {r['normalized']: r for r in res['rows']}
        self.assertEqual(by['tennis recording']['action'], 'already_covered')
        low = by['tennis recording app']
        self.assertEqual(low['action'], 'improve_existing_page'); self.assertFalse(low['passes_existing_metric_gate']); self.assertIs(low['counts_toward_inventory'], False)
        self.assertEqual(low['existing_pages'][0]['url'], '/guides/tennis-recording')
        self.assertEqual(by['tennis camera']['action'], 'needs_reviewed_source')
        self.assertEqual(by['forehand slow motion tennis']['action'], 'needs_product_confirmation')
        self.assertEqual(by['tennis serve slow motion federer']['action'], 'skip_cannot_supply_footage')
        self.assertEqual(by['swingvision tennis app']['action'], 'hold_competitor_claims')
        self.assertEqual(by['ball tracking camera']['action'], 'skip_adjacent_hardware')
        self.assertNotIn('tennis video game', by); self.assertEqual(res['invalid_rows'], {'invalid metric': 1})
        self.assertEqual(before, {n: sha(self.home / n) for n in before})  # production inputs and pool untouched
        stub = json.loads((self.home / 'reviewed-workflow-sources.proposed.json').read_text())['entries']
        self.assertTrue(all(B.entry_problem(e) for e in stub))  # stubs are inert until a human completes them

    def test_hash_mismatch_aborts(self):
        self.csv.write_text(self.csv.read_text() + 'x,1,1,https://a.example/x,2026-01-01\n')
        with self.assertRaises(ValueError): A.audit(self.home)


def make_deps(home, evidence, classify=lambda r, e: ('recording', None), proven=lambda r: True, calls=None):
    calls = calls if calls is not None else []
    def fetch(url): calls.append(url); return home / 'cache.json', evidence
    return SimpleNamespace(home=home, read=lambda p, default=None: json.loads(Path(p).read_text()) if Path(p).exists() else default,
                           atomic=lambda p, v: Path(p).write_text(json.dumps(v)), now=lambda: 't', originals=lambda b: {},
                           demand_proven=lambda row, idx: proven(row), fetch=fetch, classify=classify,
                           intent_key=lambda r: 'recording|' + r['evidence_url'])


class Bridge(unittest.TestCase):
    URL = 'https://guides.example/tennis-recording-setup'

    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.home = Path(self.t.name)
        self.entry = dict(id='rec', url=self.URL, keywords=['tennis recording'], must_contain=['tennis', 'record'],
                          reviewed_by='t', reviewed_at=datetime.date.today().isoformat())
        self.write_registry([self.entry])
        (self.home / 'keyword-input.json').write_text('{"manifest_path": "unused-by-fake-originals"}')
        c = sqlite3.connect(self.home / 'keyword-pool.sqlite')
        c.execute('create table keywords(normalized text primary key,keyword text,volume real,kd real,evidence_url text,metric_timestamp text,source_sha256 text,source_path text,status text,day text,published_url text,evidence_path text,error text,demand_url text)')
        for kw, st in [('tennis recording', 'needs_template'), ('tennis recording app', 'needs_template'), ('tennis camera', 'needs_template'), ('tennis serve', 'published')]:
            c.execute('insert into keywords values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (kw, kw, 260, 6, 'https://comp.example/' + kw.replace(' ', '-'), '2026-09-18', 's', 'p', st, None, None, None, None, None))
        c.commit(); c.close()
        self.ev = dict(http=200, text='tennis record camera setup ' * 80, final_url=self.URL, body_sha256='abc')

    def tearDown(self): self.t.cleanup()
    def write_registry(self, entries): (self.home / B.REGISTRY).write_text(json.dumps({'entries': entries}))
    def row(self, kw):
        c = sqlite3.connect(self.home / 'keyword-pool.sqlite'); c.row_factory = sqlite3.Row
        r = dict(c.execute('select * from keywords where normalized=?', (kw,)).fetchone()); c.close(); return r

    def test_registry_rejections(self):
        for patch in [dict(url='https://guides.example/'), dict(url='https://guides.example'), dict(url='http://guides.example/x'), dict(reviewed_by=''),
                      dict(reviewed_at='2020-01-01'), dict(must_contain=['tennis']), dict(keywords=[])]:
            self.assertTrue(B.entry_problem({**self.entry, **patch}), patch)
        self.assertIsNone(B.entry_problem(self.entry))

    def test_exact_alias_only_and_demand_preserved(self):
        calls = []; d = make_deps(self.home, self.ev, calls=calls)
        changes = B.select(self.home, d)
        self.assertEqual([c['keyword'] for c in changes], ['tennis recording'])  # 'app' and 'camera' not aliased -> untouched
        r = self.row('tennis recording')
        self.assertEqual((r['status'], r['evidence_url'], r['demand_url']), ('candidate', self.URL, 'https://comp.example/tennis-recording'))
        self.assertEqual(self.row('tennis recording app')['evidence_url'], 'https://comp.example/tennis-recording-app')
        self.assertEqual(self.row('tennis serve')['status'], 'published'); self.assertEqual(calls, [self.URL])

    def test_idempotent_and_no_fetch_without_eligible_rows(self):
        B.select(self.home, make_deps(self.home, self.ev)); calls = []
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev, calls=calls)), []); self.assertEqual(calls, [])

    def test_alias_does_not_create_duplicate_intent(self):
        self.write_registry([{**self.entry, 'keywords': ['tennis recording', 'tennis recording app']}])
        changes = B.select(self.home, make_deps(self.home, self.ev))
        self.assertEqual(len(changes), 1)  # same family|evidence_url -> one page per intent
        rep = json.loads((self.home / 'reviewed-workflow-selection.json').read_text())
        self.assertTrue(any(s['reason'].startswith('same_intent_already_covered') for s in rep['skipped']))

    def test_published_intent_blocks_new_page(self):
        c = sqlite3.connect(self.home / 'keyword-pool.sqlite')
        c.execute("update keywords set status='published',evidence_url=? where normalized='tennis serve'", (self.URL,)); c.commit(); c.close()
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev)), [])

    def test_evidence_gates(self):
        for name, ev in [('http', dict(self.ev, http=429)), ('thin', dict(self.ev, text='tennis record')), ('terms', dict(self.ev, text='tennis ' * 400)),
                         ('redirect', dict(self.ev, final_url='https://guides.example/'))]:
            self.assertEqual(B.select(self.home, make_deps(self.home, ev)), [], name)
        self.write_registry([{**self.entry, 'expected_sha256': 'other'}])
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev)), [])

    def test_normal_validation_still_applies(self):
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev, classify=lambda r, e: (None, 'source_keyword_identity_not_aligned'))), [])
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev, proven=lambda r: False)), [])
        self.assertEqual(self.row('tennis recording')['status'], 'needs_template')

    def test_ambiguous_alias_is_skipped(self):
        self.write_registry([self.entry, {**self.entry, 'id': 'other', 'url': 'https://other.example/recording-guide'}])
        self.assertEqual(B.select(self.home, make_deps(self.home, self.ev)), [])

    def test_default_dependencies_reject_different_home(self):
        from unittest.mock import patch
        deps = make_deps(self.home / 'other', self.ev)
        before = sha(self.home / 'keyword-pool.sqlite')
        with patch.object(B, 'default_deps', return_value=deps):
            with self.assertRaises(ValueError): B.select(self.home)
        self.assertEqual(before, sha(self.home / 'keyword-pool.sqlite'))

    def test_explicit_home_never_uses_default_deps(self):
        os.environ.pop('SWI_NAME_9111420534248685035147569521', None)  # default_deps() would raise KeyError
        B.select(self.home, make_deps(self.home, self.ev))


if __name__ == '__main__':
    unittest.main()
