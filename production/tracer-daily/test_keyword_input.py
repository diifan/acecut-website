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
 def test_three_letter_tennis_context_excerpt(self):
  from content_engine import excerpt
  source='An ace is a serve that lands legally and is not touched by the receiver.'
  value=excerpt({'keyword':'what is an ace in tennis'},{'text':source})
  self.assertIn('ace',value);self.assertLessEqual(len(value.split()),24)
 def test_context_rejects_navigation_and_prices(self):
  from evidence_text import context_excerpt
  for text in ['Tennis serve basics | Home | Twitter | Menu | More tennis serve tips', 'BEST SELLER tennis serve sensors $249.99 with free shipping on all orders.']:
   with self.assertRaises(ValueError):context_excerpt('tennis serve',text)
 def test_player_news_is_not_a_serve_workflow(self):
  for keyword in ['alexandra eala faces zheng qinwen', 'yulia putintseva dance video', 'djokovic tennis record']:
   family,_=sc.classify({'keyword':keyword,'evidence_url':'https://example.com/tennis'}, {})
   self.assertIsNone(family)
 def test_new_shot_families_require_evidence_and_have_workflows(self):
  from content_engine import WORKFLOWS
  for word,family in [('drop shot tennis','drop_shot'),('lobbing tennis','lob'),('tennis overhead smash','overhead')]:
   row={'keyword':word,'evidence_url':'https://example.com/'+word.replace(' ','-')}
   self.assertEqual(sc.classify(row,{})[1],'source_fetch_pending')
   data={'http':200,'title':word,'text':('For '+word+', keep the tennis ball visible throughout preparation, contact and recovery. ')*6}
   self.assertEqual(sc.classify(row,data),(family,None));self.assertIn(family,WORKFLOWS)
  for word in ['lobster elite','global television','emon van loben sels']:
   self.assertEqual(sc.classify({'keyword':word}, {})[1],'needs_review')
 def test_opposing_stroke_does_not_pass_token_overlap(self):
  for word,title,url in [('djokovic backhand slow motion','Novak Djokovic Serve in Slow Motion','https://example.test/djokovic-serve-slow-motion'),('eastern backhand grip','Eastern Forehand Grip','https://example.test/eastern-forehand-grip')]:
   data={'http':200,'title':title,'text':('This tennis source discusses '+word+' alongside many other tennis topics. ')*10}
   self.assertEqual(sc.classify({'keyword':word,'evidence_url':url},data)[1],'source_keyword_identity_not_aligned')
 def test_editorial_topics_use_intent_not_source_url(self):
  rows=[{'keyword':'tennis court dimensions','evidence_url':'https://example.test/court'},{'keyword':'tennis court width','evidence_url':'https://example.test/court'},{'keyword':'tennis net height','evidence_url':'https://example.test/court'}]
  self.assertEqual(sc.intent_key(rows[0]),sc.intent_key(rows[1]))
  self.assertNotEqual(sc.intent_key(rows[0]),sc.intent_key(rows[2]))
  for row in rows:
   self.assertEqual(sc.classify(row,{})[1],'source_fetch_pending')
   self.assertEqual(sc.classify(row,{'http':200,'text':'Tennis unrelated story. '*30})[1],'source_topic_answer_not_supported')
  text='Tennis court dimensions are 78 feet long and the net centre is 3 feet high. '*10
  self.assertEqual(sc.classify(rows[0],{'http':200,'text':text})[0],'editorial:court_dimensions')
  self.assertEqual(sc.classify(rows[2],{'http':200,'text':text})[0],'editorial:net_height')
 def test_editorial_renderer_answers_without_clip_plan(self):
  import content_engine as ce
  from editorial_topics import TOPICS
  row={'keyword':'tennis court dimensions','evidence_url':'https://example.test/court'}
  with patch.object(ce,'shell',side_effect=lambda title,description,path,body:body):html=ce.render_editorial(row,{'checked_at':'2026-11-24'},TOPICS['court_dimensions'],[])
  self.assertIn('23.77',html);self.assertIn('data-page-type="court_reference"',html);self.assertNotIn('id="clip-plan"',html)
 def test_new_unknown_and_equipment_are_not_discarded(self):
  self.assertEqual(sc.classify({'keyword':'unknown tennis phrase','evidence_url':'https://example.test/'},{})[1],'needs_review')
  self.assertEqual(sc.classify({'keyword':'tennis string tension','evidence_url':'https://example.test/'},{})[1],'needs_template')
 def test_other_sport_and_bad_intent(self):
  r={'keyword':'basketball serve','evidence_url':'https://example.com/tennis'};self.assertEqual(sc.classify(r,{'http':200})[1],'needs_review')
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
