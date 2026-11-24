import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
import common,keyword_input as k,source_cache as sc,executor
class InputBoundary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.stack=ExitStack()
  for m in [common,k,sc,executor]:self.stack.enter_context(patch.object(m,'HOME',self.root))
  self.stack.enter_context(patch.object(executor,'WORK',self.root/'site'))
  common.atomic(self.root/'config.json',dict(enabled=True,target=2000,hour=12,minute=30,prepare_hour=13,prepare_minute=0,timezone='Asia/Shanghai'))
  self.pool=self.root/'keywords.csv';self.manifest=self.root/'manifest.json';self.original=self.root/'raw.csv';self.rows=[];self.write()
 def tearDown(self):self.stack.close();self.tmp.cleanup()
 def write(self):
  fields=['Keyword','Search Volume','Keyword Difficulty','URL','Timestamp']
  for path in [self.original,self.pool]:
   with path.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(self.rows)
  common.atomic(self.manifest,{'app':'acecut','sport':'tennis','sources':[] if not self.rows else [{'path':str(self.original),'sha256':common.sha(self.original),'rows':len(self.rows)}]})
 def row(self,word='tennis serve',volume='101',kd='29.9'):
  return dict(zip(['Keyword','Search Volume','Keyword Difficulty','URL','Timestamp'],[word,volume,kd,'https://example.com/tennis-serve','2026-11-22']))
 def test_empty_then_append_without_rebinding(self):
  k.bind(self.pool,self.manifest);self.assertEqual(k.ingest()['added'],0)
  self.rows=[self.row()];self.write();self.assertEqual(k.ingest()['added'],1)
  c=k.db();c.execute('update keywords set status="reserved",day="2026-11-24"');c.commit();self.assertEqual(k.ingest()['existing_preserved'],1);self.assertEqual(c.execute('select status from keywords').fetchone()[0],'reserved')
 def test_strict_thresholds_and_normalization(self):
  self.rows=[self.row(),self.row(' Ｔennis   SERVE '),self.row('other',volume='100'),self.row('other2',kd='30'),self.row('other3',volume='NaN')];self.write();k.bind(self.pool,self.manifest);r=k.ingest();self.assertEqual(r['added'],1);self.assertEqual(r['rejected'],3);self.assertEqual(r['existing_preserved'],1)
 def test_original_hash_tamper_rejected(self):
  self.rows=[self.row()];self.write();k.bind(self.pool,self.manifest);self.original.write_text('modified')
  with self.assertRaises(ValueError):k.ingest()
 def test_unproven_metrics_rejected(self):
  self.rows=[self.row()];self.write();k.bind(self.pool,self.manifest);self.pool.write_text(self.pool.read_text().replace('101','102'));self.assertEqual(k.ingest()['unproven'],1)
 def test_other_sport_and_bad_intent(self):
  r={'keyword':'basketball serve','evidence_url':'https://example.com/tennis'};self.assertEqual(sc.classify(r,{'http':200})[1],'unrelated_search_intent')
 def test_empty_pool_does_not_build_or_publish(self):
  k.bind(self.pool,self.manifest)
  with patch.object(executor,'git',side_effect=AssertionError('Git must not run')),patch.object(executor,'api',side_effect=AssertionError('Vercel must not run')),patch.object(executor,'run',side_effect=AssertionError('Build must not run')):
   executor.prepare('2099-01-01')
   r=common.read(self.root/'2099-01-01-receipt.json');self.assertEqual(r['state'],'insufficient_keywords');self.assertEqual(r['published_count'],0)
   with self.assertRaises(AssertionError):executor.publish('2099-01-01',immediate=True)
   self.assertEqual(common.read(self.root/'capacity.json')['eligible_available'],0)
 def test_video_batch_never_published(self):
  common.atomic(self.root/'2099-01-01-receipt.json',{'source_kind':'video_titles'})
  with patch.object(executor,'api',side_effect=AssertionError('Vercel must not run')):
   with self.assertRaises(RuntimeError):executor.publish('2099-01-01',immediate=True)
if __name__=='__main__':unittest.main()
