#!/usr/bin/env python3
"""Incremental AceCut publishing; shared controller owns UI and mutable config."""
import argparse,datetime,json,re,sys,time,urllib.request,xml.etree.ElementTree as ET
from common import *
from keyword_input import db,counts,ingest,bind
from source_cache import verify
from content_engine import render,slug,hubs

def capacity():
 c=db();occupied={slug(dict(r)) for r in c.execute('select * from keywords where status in ("reserved","published")')}
 for row in c.execute('select * from keywords where status="verified" order by rowid').fetchall():
  route=slug(dict(row))
  if not route or route in occupied or (WORK/'public/tennis-tracer'/(route+'.html')).exists():c.execute('update keywords set status="excluded",error="occupied_or_duplicate_slug" where normalized=?',(row['normalized'],))
  else:occupied.add(route)
 c.commit();info=counts();binding=read(HOME/'keyword-input.json',{})
 payload=dict(checked_at=time.time(),eligible_available=info['verified_available'],app='acecut',keyword_pool=info,source_kind='semrush_keywords')
 # Only this agreed capacity file is written in the controller-owned producer directory.
 if binding:atomic(Path(binding['pool_path']).parent/'capacity.json',payload)
 return info

def refresh(day):
 imported=ingest()
 receipt(day,state='validating_keyword_input',source_kind='semrush_keywords',keyword_sources=[dict(source='Semrush organic Positions',binding=read(HOME/'keyword-input.json'),import_counts=imported)],keyword_pool=counts(),blockers=[])
 verify(day);capacity()

def validate(rows,base):
 target=len(rows);urls=set();titles=set();bodies=set();records=[]
 for row in rows:
  path='/tennis-tracer/'+slug(row);p=WORK/'public'/(path[1:]+'.html');text=p.read_text();title=re.search(r'<title>(.*?)</title>',text)[1]
  assert title not in titles,'Duplicate title';titles.add(title)
  assert row['evidence_url'].replace('&','&amp;') in text and '/try-tracer' in text and ('id="clip-plan"' in text or 'data-page-type=' in text),'Missing source/utility'
  assert text.count('rel="canonical"')==1 and f'href="{ORIGIN}{path}"' in text
  assert sha(p) not in bodies,'Duplicate body';bodies.add(sha(p));urls.add(ORIGIN+path)
  evidence=Path(row['evidence_path']);assert read(evidence)['http']==200
  assert row['kd']<30 and row['volume']>100
  records.append(dict(keyword=row['keyword'],normalized=row['normalized'],url=ORIGIN+path,evidence_url=row['evidence_url'],volume=row['volume'],kd=row['kd'],metric_timestamp=row['metric_timestamp'],source_sha256=row['source_sha256'],source_path=row['source_path'],sha256=sha(p),evidence_path=str(evidence),evidence_sha256=sha(evidence)))
 assert len(urls)==target
 for name in git('ls-tree','-r','--name-only',base).splitlines():
  if not name.startswith(('public/','api/','server/')) or name in ('public/tennis-ball-tracer.html','public/sitemap.xml'):continue
  p=WORK/name;assert p.exists(),'Baseline file missing: '+name
  if name.startswith('public/tennis-tracer') and '/guides-' in name:continue
  if name=='public/tennis-tracer.html':continue
  assert git('hash-object',name)==git('rev-parse',base+':'+name),'Baseline changed: '+name
 guide=git('show',base+':public/tennis-ball-tracer.html');current=(WORK/'public/tennis-ball-tracer.html').read_text();addition='<li><a href="/tennis-tracer">Tennis video review guides</a></li>'
 assert current.replace(addition,'').strip()==guide or current.strip()==guide,'Unexpected guide change'
 sitemap={x.text for x in ET.parse(WORK/'dist/sitemap.xml').findall('{*}url/{*}loc')};assert urls<=sitemap
 baseline_urls={x.text for x in ET.fromstring(git('show',base+':public/sitemap.xml')).findall('{*}url/{*}loc')};assert baseline_urls<=sitemap,'Previous sitemap URLs lost'
 assert not (urls & baseline_urls),'Batch duplicates already published URLs'
 for file in (WORK/'public').rglob('*.html'):
  text=file.read_text()
  for href in re.findall(r'href="(/[^"?#]*)(?:[?#][^"]*)?"',text):
   if href=='/' or href.startswith('/api/'):continue
   p=WORK/'public'/href.lstrip('/')
   assert p.exists() or p.with_suffix('.html').exists(),f'Broken internal link: {href} in {file}'
 return records,dict(build='passed',seo='passed',new_pages=target,sitemap_count=len(sitemap),baseline_retained=True,source_kind='semrush_keywords',all_internal_links='passed')

def prepare(day,collect=True):
 cfg=config();target=cfg['target'];r=read(HOME/(day+'-receipt.json'),{})
 if r.get('state')=='published':return r
 if r.get('state')=='prepared' and r.get('target')==target:return r
 if collect:refresh(day)
 capacity()
 c=db();rows=[dict(x) for x in c.execute('select * from keywords where day=? and status="reserved" order by rowid',(day,))]
 if len(rows)<target:
  rows += [dict(x) for x in c.execute('select * from keywords where status="verified" order by rowid limit ?',(target-len(rows),))]
  if len(rows)<target:
   receipt(day,state='insufficient_keywords',target=target,keyword_pool=counts(),blockers=([dict(type='source_quota_blocked',code=-32107,detail='Controller confirmed Semrush Report limits exceeded; producer owns six-hour cooldown')] if counts()['candidate_count']==0 else [])+[dict(type='candidate_shortfall',count=max(0,target-sum(counts()['status_counts'].get(s,0) for s in ('verified','candidate','fetch_failed')))),dict(type='fetch_pending',count=counts()['fetch_pending_count']),dict(type='verified_shortfall',count=target-len(rows))]);return
  with c:
   for row in rows:c.execute('update keywords set status="reserved",day=? where normalized=? and status="verified"',(day,row['normalized']))
 assert len(rows)==target,'Reserved target differs from current config'
 git('fetch','origin','main');base=git('rev-parse','origin/main');head=git('rev-parse','HEAD')
 if head!=base:
  try:git('merge-base','--is-ancestor',base,'HEAD')
  except RuntimeError:
   if git('status','--porcelain'):raise RuntimeError('Production main advanced while isolated changes are uncommitted; reconcile without overwriting')
   git('merge','--no-edit','origin/main')
   git('merge-base','--is-ancestor',base,'HEAD')
 receipt(day,state='generating',source_kind='semrush_keywords',base_commit=base,target=target,keyword_pool=capacity(),blockers=[])
 folder=WORK/'public/tennis-tracer';folder.mkdir(exist_ok=True)
 # Neighbours share title vocabulary; no invented relationship or player metadata.
 tokens=[set(re.findall('[a-z]{4,}',x['keyword'].lower()))-{'highlights','tennis','shot','shots','extended','2025','2026'} for x in rows]
 for i,row in enumerate(rows):
  related=sorted((j for j in range(len(rows)) if j!=i),key=lambda j:(-len(tokens[i]&tokens[j]),abs(j-i)))[:4]
  (folder/(slug(row)+'.html')).write_text(render(row,[rows[j] for j in related]))
  if (i+1)%50==0:receipt(day,state='generating',generated_count=i+1)
 all_rows=[dict(x) for x in c.execute('select * from keywords where status="published" or (status="reserved" and day=?) order by rowid',(day,))];hubs(all_rows)
 guide=WORK/'public/tennis-ball-tracer.html';s=guide.read_text();addition='<li><a href="/tennis-tracer">Tennis video review guides</a></li>'
 if addition not in s:s=s.replace('<h2>Keep reading</h2><ul>','<h2>Keep reading</h2><ul>'+addition);guide.write_text(s)
 receipt(day,state='building',generated_count=len(rows))
 run([BUN,'install','--frozen-lockfile'],timeout=180);run([BUN,'run','build'],timeout=180)
 records,checks=validate(rows,base)
 manifest=WORK/'content/tennis-tracer/batches'/(day+'.json');atomic(manifest,dict(day=day,target=target,source_kind='semrush_keywords',base_commit=base,pages=records))
 # Public sitemap mirrors build output, retaining every baseline route.
 (WORK/'public/sitemap.xml').write_bytes((WORK/'dist/sitemap.xml').read_bytes())
 receipt(day,state='validated',validated_count=target,pages_path=str(manifest),pages_sha256=sha(manifest),checks=checks)
 git('add','public/tennis-tracer','public/tennis-tracer.html','public/tracer-guides.css','public/tracer-guides.js','public/tennis-ball-tracer.html','public/sitemap.xml','content/tennis-tracer','production/tracer-daily')
 if git('diff','--cached','--name-only'):git('commit','-m',f'Add {target} sourced tennis video review pages for {day}')
 commit=git('rev-parse','HEAD');receipt(day,state='uploading_prepared',commit=commit)
 git('fetch','origin','main');assert git('rev-parse','origin/main')==base,'main advanced during build; rebase and revalidate before publishing'
 alias_before=api('/v4/aliases/acecut.goswie.com')['deploymentId'];batch='acecut-'+day
 previous=api('/v6/deployments?projectId='+PROJECT+'&limit=100').get('deployments',[])
 found=next((x for x in previous if x.get('meta',{}).get('swieCommit')==commit and x.get('readyState') not in ('ERROR','CANCELED')),None)
 if found:ident=found.get('uid',found.get('id'))
 else:
  result=run([CLI,'deploy','--prod','--skip-domain','--archive=tgz','--project',PROJECT,'--scope',SCOPE,'--yes','--json','--meta','swieBatch='+batch,'--meta','swieCommit='+commit],timeout=1800)
  try:d=json.loads(result);d=d.get('deployment',d);ident=d.get('id') or d.get('uid') or d.get('url')
  except json.JSONDecodeError:ident=re.findall(r'https://[^\s]+\.vercel\.app',result)[-1]
 d=api('/v13/deployments/'+ident.removeprefix('https://'));ident=d['id']
 for _ in range(120):
  d=api('/v13/deployments/'+ident)
  if d.get('readyState') in ('READY','ERROR','CANCELED'):break
  receipt(day,state='waiting_vercel',prepared_deployment_id=ident);time.sleep(5)
 assert d.get('projectId')==PROJECT and d.get('readyState')=='READY' and d.get('target')=='production','Prepared deployment is not production READY'
 assert d.get('meta',{}).get('swieCommit')==commit
 assert api('/v4/aliases/acecut.goswie.com')['deploymentId']==alias_before,'Production alias changed during preparation'
 return receipt(day,state='prepared',prepared_deployment_id=ident,deployment_url='https://'+d['url'],ready_for_promotion=True,blockers=[])

def publish(day,immediate=False):
 if read(HOME/(day+'-receipt.json'),{}).get('source_kind')!='semrush_keywords':raise RuntimeError('Publication requires a verified Semrush keyword batch; video-title batches are prohibited')
 cfg=config();r=read(HOME/(day+'-receipt.json'),{});local=datetime.datetime.now(ZoneInfo(cfg['timezone']))
 if r.get('state')=='published':return r
 if not immediate and (day!=local.date().isoformat() or (local.hour,local.minute)<(cfg['hour'],cfg['minute'])):return
 assert r.get('ready_for_promotion') and r['validated_count']==r['target']==cfg['target'],'No validated batch matching current target'
 manifest=Path(r['pages_path']);assert sha(manifest)==r['pages_sha256'];m=read(manifest)
 assert m.get('source_kind')=='semrush_keywords' and len(m['pages'])==r['target']
 for p in m['pages']:
  assert 0<=p['kd']<30 and p['volume']>100
  assert sha(Path(p['source_path']))==p['source_sha256'] and sha(Path(p['evidence_path']))==p['evidence_sha256']
 for p in m['pages']:assert sha(WORK/'public'/(p['url'].removeprefix(ORIGIN+'/')+'.html'))==p['sha256']
 d=api('/v13/deployments/'+r['prepared_deployment_id']);assert d['projectId']==PROJECT and d['readyState']=='READY' and d['target']=='production' and d['meta']['swieCommit']==r['commit']
 git('fetch','origin','main');head=git('rev-parse','origin/main');assert head in (r['base_commit'],r['commit']),'Production baseline advanced; rebuild before publication'
 # Record in GitHub first, then promote exactly the validated deployment.
 receipt(day,state='publishing')
 if head!=r['commit']:git('push','origin',r['commit']+':refs/heads/main')
 run([CLI,'promote',r['prepared_deployment_id'],'--yes','--scope',SCOPE,'--timeout','90s','--json'],timeout=120)
 alias=api('/v4/aliases/acecut.goswie.com');assert alias['deploymentId']==r['prepared_deployment_id']
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':PROXY}))
 with opener.open(ORIGIN+'/sitemap.xml',timeout=30) as response:sitemap=response.read()
 urls={x.text for x in ET.fromstring(sitemap).findall('{*}url/{*}loc')};expected={p['url'] for p in m['pages']};assert expected<=urls,'Live sitemap missing batch URLs'
 sample=[]
 for p in (m['pages'][0],m['pages'][len(m['pages'])//2],m['pages'][-1]):
  with opener.open(p['url'],timeout=30) as response:body=response.read()
  assert hashlib.sha256(body).hexdigest()==p['sha256'],'Live page differs from validated page';sample.append(p['url'])
 c=db()
 with c:c.execute('update keywords set status="published" where day=? and status="reserved"',(day,))
 capacity()
 return receipt(day,state='published',published_count=r['target'],keyword_pool=counts(),blockers=[],live_verification=dict(sitemap_url=ORIGIN+'/sitemap.xml',batch_covered=len(expected),total_urls=len(urls),sample_urls=sample,deployment_id=r['prepared_deployment_id'],verified_at=now()))

def tick():
 cfg=config();heartbeat()
 if not cfg['enabled']:return
 local=datetime.datetime.now(ZoneInfo(cfg['timezone']));today=local.date().isoformat();r=read(HOME/(today+'-receipt.json'),{})
 cutoff=(local.hour,local.minute)>=(cfg['hour'],cfg['minute'])
 def attempt(day):
  previous=read(HOME/(day+'-receipt.json'),{})
  if previous.get('state') in ('prepared','published'):return previous
  last=previous.get('last_attempt_at');elapsed=99999 if not last else (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(last)).total_seconds()
  if elapsed<300:return previous
  receipt(day,last_attempt_at=now())
  try:return prepare(day)
  except Exception as e:receipt(day,state='failed',blockers=[{'type':type(e).__name__,'detail':str(e)[:1200]}]);return None
 # Explicit first-day authorization: consume the real pool when it arrives and publish
 # after all checks, even though today's scheduled time has already passed.
 if today=='2026-11-24' and r.get('state')!='published':
  r=attempt(today) or read(HOME/(today+'-receipt.json'),{})
  if r.get('ready_for_promotion'):publish(today,immediate=True)
  return
 if not cutoff and r.get('state') not in ('prepared','published'):attempt(today)
 if cutoff and r.get('ready_for_promotion') and r.get('state')!='published':publish(today)
 if (local.hour,local.minute)>=(cfg['prepare_hour'],cfg['prepare_minute']):attempt((local.date()+datetime.timedelta(days=1)).isoformat())

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['bind','prepare','publish','tick']);p.add_argument('--day');p.add_argument('--pool',type=Path);p.add_argument('--manifest',type=Path);p.add_argument('--existing-sources',action='store_true');p.add_argument('--immediate',action='store_true');a=p.parse_args()
 try:l=lock()
 except BlockingIOError:return
 day=a.day or datetime.datetime.now(ZoneInfo(config()['timezone'])).date().isoformat()
 try:
  if a.action=='bind':
   if not a.pool or not a.manifest:raise ValueError('bind requires --pool and --manifest')
   bind(a.pool,a.manifest);refresh(day)
  elif a.action=='tick':tick()
  elif a.action=='prepare':prepare(day,not a.existing_sources)
  else:
   if a.immediate and day!='2026-11-24':raise ValueError('Immediate override is limited to explicitly authorized first batch')
   publish(day,a.immediate)
 except Exception as e:
  receipt(day,state='failed',blockers=[{'type':type(e).__name__,'detail':str(e)[:1200]}]);raise
 finally:l.close()
if __name__=='__main__':main()
