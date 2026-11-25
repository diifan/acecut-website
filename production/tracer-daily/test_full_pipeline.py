"""Synthetic fixture only: actual 2000-page Bun build, local Git, mocked Vercel/HTTP.
No production pool, source collector, GitHub repository or Vercel is mutated.
"""
import csv,json,shutil,subprocess,tempfile,unittest,io,datetime
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import common,keyword_input,source_cache,content_engine,executor
class FullBuild(unittest.TestCase):
 def test_2000_page_prepare_publish_fixture(self):self.exercise()
 def test_incremental_779_then_1221_keeps_daily_goal_and_previous_pages(self):self.exercise(779)
 def exercise(self,first_size=None):
  real=common.WORK;script_root=Path(__file__).parent
  with tempfile.TemporaryDirectory(prefix='acecut-fixture-') as temp,ExitStack() as stack:
   root=Path(temp);work=root/'website';runtime=root/'runtime';runtime.mkdir();remote=root/'origin.git';day='2099-01-01'
   def cmd(*args,cwd=None):return subprocess.check_output(args,cwd=cwd,text=True,stderr=subprocess.STDOUT).strip()
   base=cmd('git','rev-parse','origin/main',cwd=real)
   cmd('git','clone','--quiet','--no-hardlinks','--no-checkout',str(real),str(work));cmd('git','checkout','--quiet','-B','fixture',base,cwd=work)
   cmd('git','init','--quiet','--bare',str(remote));cmd('git','remote','set-url','origin',str(remote),cwd=work);cmd('git','push','--quiet','origin','HEAD:refs/heads/main',cwd=work)
   cmd('git','config','user.email','fixture@example.invalid',cwd=work);cmd('git','config','user.name','AceCut fixture',cwd=work)
   shutil.copytree(script_root,work/'production/tracer-daily',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
   for name in ['tracer-guides.css','tracer-guides.js']:shutil.copy2(real/'public'/name,work/'public'/name)
   for module in [common,keyword_input,source_cache,content_engine,executor]:
    if hasattr(module,'HOME'):stack.enter_context(patch.object(module,'HOME',runtime))
    if hasattr(module,'WORK'):stack.enter_context(patch.object(module,'WORK',work))
   cfg=dict(enabled=True,target=2000,hour=12,minute=30,prepare_hour=13,prepare_minute=0,timezone='Asia/Shanghai');common.atomic(runtime/'config.json',cfg)
   original=root/'fixture-original.csv';fields=['Keyword','Search Volume','Keyword Difficulty','URL','Timestamp'];rows=[];evidence={}
   for i in range(2000):
    word=f'tennis serve drill fixture {i:04d}';url=f'https://example.invalid/tennis-serve-drill-fixture-{i:04d}'
    rows.append(dict(zip(fields,[word,101,29,url,'2098-12-01'])))
    path=runtime/'source-cache'/f'{i}.json';data=dict(http=200,source_url=url,final_url=url,title=word,headings=[word],text=f'{word}. This is synthetic test evidence for a tennis clip review, never a production keyword or public source. '+('A tennis serve recording should keep a continuous camera view for this synthetic fixture. '*8),checked_at='2098-12-31T00:00:00+00:00');common.atomic(path,data);evidence[url]=(path,data)
   with original.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
   pool=root/'keywords.csv';shutil.copy2(original,pool);manifest=root/'manifest.json';common.atomic(manifest,dict(app='acecut',sport='tennis',sources=[dict(path=str(original),sha256=common.sha(original),rows=2000)]));keyword_input.bind(pool,manifest)
   stack.enter_context(patch.object(source_cache,'fetch',side_effect=lambda u:evidence[u]));executor.refresh(day)
   self.assertEqual(keyword_input.counts()['verified_available'],2000)
   if first_size:
    c=keyword_input.db();c.execute('update keywords set status="needs_review" where rowid>?',(first_size,));c.commit()
   promoted={'yes':False,'alias':'dpl_fixture_baseline','latest':None,'deployments':{}};actual_run=common.run
   def fake_run(args,*a,**kw):
    if args[0]==common.CLI:
     if args[1]=='deploy':
      ident='dpl_fixture_'+str(len(promoted['deployments'])+1);promoted['latest']=ident;promoted['deployments'][ident]=cmd('git','rev-parse','HEAD',cwd=work);return json.dumps({'id':ident,'url':'fixture.invalid'})
     if args[1]=='promote':promoted['yes']=True;promoted['alias']=promoted['latest'];return '{}'
     raise AssertionError('Unmocked Vercel operation')
    return actual_run(args,*a,**kw)
   stack.enter_context(patch.object(executor,'run',side_effect=fake_run))
   def api(path):
    if path.startswith('/v4/aliases/'):return {'deploymentId':promoted['alias']}
    if path.startswith('/v6/deployments'):return {'deployments':[]}
    if path.startswith('/v13/deployments/'):
     ident=path.rsplit('/',1)[-1];return dict(id=ident,url='fixture.invalid',projectId=common.PROJECT,readyState='READY',target='production',meta={'swieCommit':promoted['deployments'][ident]})
    raise AssertionError('Unmocked API operation: '+path)
   stack.enter_context(patch.object(executor,'api',side_effect=api));r=executor.prepare(day,collect=False)
   self.assertEqual(r['state'],'prepared');self.assertEqual(r['validated_count'],first_size or 2000);self.assertEqual(r['published_count'],0);self.assertEqual(r['target'],2000)
   class Opener:
    def open(self,url,timeout=None):
     path=url.removeprefix(common.ORIGIN+'/');file=work/'dist'/path
     if not path.endswith('.xml'):file=file.with_suffix('.html')
     return io.BytesIO(file.read_bytes())
   stack.enter_context(patch.object(executor.urllib.request,'build_opener',return_value=Opener()));r=executor.publish(day,immediate=True)
   if first_size:
    self.assertEqual(r['state'],'published_partial');self.assertEqual(r['published_count'],first_size);self.assertEqual(r['shortfall'],2000-first_size);self.assertFalse(r['ready_for_promotion'])
    original_manifest=Path(r['pages_path']);original_bytes=original_manifest.read_bytes();first_hashes={x['url']:x['sha256'] for x in common.read(original_manifest)['pages']}
    c=keyword_input.db();c.execute('update keywords set status="verified" where status="needs_review"');c.commit()
    r=executor.prepare(day,collect=False);self.assertEqual(r['batch_target'],2000-first_size);self.assertEqual(r['target'],2000)
    self.assertEqual(original_manifest.read_bytes(),original_bytes)
    for url,digest in first_hashes.items():self.assertEqual(common.sha(work/'public'/(url.removeprefix(common.ORIGIN+'/')+'.html')),digest)
    r=executor.publish(day,immediate=True);self.assertEqual(len(r['rounds']),2);self.assertEqual(r['live_verified_count'],2000)
   self.assertEqual(r['state'],'published');self.assertEqual(r['published_count'],2000);self.assertEqual(r['live_verification']['batch_covered'],2000-(first_size or 0))
   self.assertEqual(executor.capacity()['verified_available'],0)
   print('FIXTURE ONLY: 2000 generated, Bun built, validated; local Git push and simulated Vercel/online verification passed. Production published count unchanged.')
class Schedule(unittest.TestCase):
 def test_disabled_tick_never_prepares(self):
  with patch.object(executor,'config',return_value={'enabled':False}),patch.object(executor,'heartbeat'),patch.object(executor,'prepare') as p,patch.object(executor,'publish') as pub:executor.tick();p.assert_not_called();pub.assert_not_called()
 def test_future_prepared_batch_not_published_early(self):
  with tempfile.TemporaryDirectory() as t,ExitStack() as stack:
   root=Path(t)
   for m in [common,executor]:stack.enter_context(patch.object(m,'HOME',root))
   common.atomic(root/'config.json',dict(enabled=True,target=2000,hour=12,minute=30,prepare_hour=13,prepare_minute=0,timezone='Asia/Shanghai'))
   common.atomic(root/'2099-01-02-receipt.json',dict(source_kind='semrush_keywords',state='prepared',ready_for_promotion=True))
   with patch.object(executor,'api',side_effect=AssertionError('No Vercel before due date')):self.assertIsNone(executor.publish('2099-01-02'))
if __name__=='__main__':unittest.main()
