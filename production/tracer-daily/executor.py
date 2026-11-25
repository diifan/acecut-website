#!/usr/bin/env python3
"""Incremental AceCut publishing; shared controller owns UI and mutable config."""
import argparse,datetime,json,re,sys,time,urllib.request,urllib.error,xml.etree.ElementTree as ET,concurrent.futures
from common import *
from keyword_input import db,counts,ingest,bind,originals,demand_proven
from source_cache import verify,intent_key
from content_engine import render,slug,hubs

def capacity():
 c=db();held=[dict(r) for r in c.execute('select * from keywords where status in ("reserved","published")')];occupied={slug(r) for r in held};occupied_intents={intent_key(r) for r in held}
 for row in c.execute('select * from keywords where status="verified" order by rowid').fetchall():
  route=slug(dict(row));intent=intent_key(dict(row))
  if intent in occupied_intents:
   c.execute('update keywords set status="excluded",error="duplicate_selected_intent" where normalized=?',(row['normalized'],));continue
  if not route or route in occupied or (WORK/'public/tennis-tracer'/(route+'.html')).exists():c.execute('update keywords set status="excluded",error="occupied_or_duplicate_slug" where normalized=?',(row['normalized'],))
  else:occupied.add(route);occupied_intents.add(intent)
 c.commit();info=counts();binding=read(HOME/'keyword-input.json',{})
 payload=dict(checked_at=time.time(),eligible_available=info['verified_available'],app='acecut',keyword_pool=info,source_kind='semrush_keywords')
 # Only this agreed capacity file is written in the controller-owned producer directory.
 if binding:atomic(Path(binding['pool_path']).parent/'capacity.json',payload)
 return info

def refresh(day):
 previous=read(HOME/(day+"-receipt.json"),{})
 if previous.get("state") in ("prepared","published") or previous.get("ready_for_promotion"):
  return previous
 imported=ingest()
 from harvest_equipment import ensure_profiles
 ensure_profiles(HOME)
 from harvest_records import ensure_records
 ensure_records(HOME)
 from evidence_selection import select_verified_alternatives
 select_verified_alternatives(HOME)
 from harvest_supplemental import ensure as ensure_supplemental
 ensure_supplemental()
 from public_player_records import ensure as ensure_public_players
 ensure_public_players()
 from supplemental_evidence import select as select_supplemental
 select_supplemental(HOME)
 receipt(day,state='validating_keyword_input',source_kind='semrush_keywords',keyword_sources=[dict(source='Semrush organic Positions',binding=read(HOME/'keyword-input.json'),import_counts=imported)],keyword_pool=counts(),blockers=[])
 verify(day);capacity()

def validate(rows,base):
 target=len(rows);urls=set();titles=set();bodies=set();records=[]
 demand_index=originals(read(HOME/'keyword-input.json'))
 for row in rows:
  path='/tennis-tracer/'+slug(row);p=WORK/'public'/(path[1:]+'.html');text=p.read_text();title=re.search(r'<title>(.*?)</title>',text)[1]
  assert title not in titles,'Duplicate title';titles.add(title)
  assert row['evidence_url'].replace('&','&amp;') in text and '/try-tracer' in text and ('id="clip-plan"' in text or 'data-page-type=' in text),'Missing source/utility'
  assert text.count('rel="canonical"')==1 and f'href="{ORIGIN}{path}"' in text
  assert sha(p) not in bodies,'Duplicate body';bodies.add(sha(p));urls.add(ORIGIN+path)
  evidence=Path(row['evidence_path']);assert read(evidence)['http']==200
  assert row['kd']<30 and row['volume']>100
  assert demand_proven(row,demand_index),'Keyword demand provenance mismatch'
  records.append(dict(keyword=row['keyword'],normalized=row['normalized'],url=ORIGIN+path,evidence_url=row['evidence_url'],demand_url=row.get('demand_url') or row['evidence_url'],volume=row['volume'],kd=row['kd'],metric_timestamp=row['metric_timestamp'],source_sha256=row['source_sha256'],source_path=row['source_path'],sha256=sha(p),evidence_path=str(evidence),evidence_sha256=sha(evidence)))
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

def revalidate_inventory(day):
 from source_cache import classify
 c=db();rejected=[]
 for item in c.execute('select * from keywords where status="verified" or (status="reserved" and day=?)',(day,)).fetchall():
  row=dict(item);evidence=read(Path(row['evidence_path']),{}) if row.get('evidence_path') else {}
  family,error=classify(row,evidence)
  if family:continue
  if row['status']=='reserved':
   relative='public/tennis-tracer/'+slug(row)+'.html';path=WORK/relative
   # Only remove an uncommitted generated file for this exact reservation.
   if path.exists() and not git('ls-files','--',relative):path.unlink()
  state=error if error in ('needs_template','needs_review','freshness_required','specialist_review') else 'fetch_failed' if error=='source_fetch_pending' else 'needs_review'
  c.execute('update keywords set status=?,day=NULL,error=? where normalized=?',(state,error,row['normalized']));rejected.append({'keyword':row['keyword'],'reason':error})
 c.commit()
 if rejected:receipt(day,revalidation_rejected=rejected)
 return rejected

def batch_minimum(cfg,day,remaining):
 local=datetime.datetime.now(ZoneInfo(cfg['timezone']))
 due=day==local.date().isoformat() and (local.hour,local.minute)>=(cfg['hour'],cfg['minute'])
 return 1 if due else min(cfg.get('incremental_min_pages',100),remaining)

def prepare(day,collect=True):
 cfg=config();target=cfg['target'];r=read(HOME/(day+'-receipt.json'),{})
 if r.get('state')=='published':return r
 if (r.get('state')=='prepared' or r.get('ready_for_promotion')) and r.get('target')==target:return r
 if collect:refresh(day)
 revalidate_inventory(day)
 capacity()
 c=db();completed=c.execute('select count(*) from keywords where day=? and status="published"',(day,)).fetchone()[0]
 remaining=target-completed
 if remaining<=0:return receipt(day,state='published',published_count=completed,shortfall=0,ready_for_promotion=False)
 rows=[dict(x) for x in c.execute('select * from keywords where day=? and status="reserved" order by rowid',(day,))]
 assert len(rows)<=remaining,'Reservations exceed remaining daily target'
 reserved_count=len(rows)
 rows += [dict(x) for x in c.execute('select * from keywords where status="verified" order by rowid limit ?',(remaining-len(rows),))]
 minimum=batch_minimum(cfg,day,remaining)
 if not rows or (len(rows)<minimum and not reserved_count):
  pool=counts();states=pool['status_counts'];backlog=sum(states.get(s,0) for s in ('needs_template','needs_review','freshness_required','specialist_review'))
  blockers=[dict(type='verified_shortfall',count=max(0,remaining-len(rows))),dict(type='content_processing_backlog',count=backlog),dict(type='fetch_pending',count=pool['fetch_pending_count'])]
  return receipt(day,state='published_partial' if completed else 'insufficient_keywords',target=target,published_count=completed,generated_count=completed,validated_count=completed,shortfall=remaining,ready_for_promotion=False,keyword_pool=pool,blockers=blockers)
 with c:
  for row in rows:c.execute('update keywords set status="reserved",day=? where normalized=? and status="verified"',(day,row['normalized']))
 batch_target=len(rows);sequence=len(r.get('rounds',[]))+1
 git('fetch','origin','main');base=git('rev-parse','origin/main');head=git('rev-parse','HEAD')
 if head!=base:
  try:git('merge-base','--is-ancestor',base,'HEAD')
  except RuntimeError:
   if git('status','--porcelain'):raise RuntimeError('Production main advanced while isolated changes are uncommitted; reconcile without overwriting')
   git('merge','--no-edit','origin/main')
   git('merge-base','--is-ancestor',base,'HEAD')
 receipt(day,state='generating',source_kind='semrush_keywords',base_commit=base,target=target,batch_target=batch_target,batch_sequence=sequence,published_count=completed,shortfall=remaining,ready_for_promotion=False,keyword_pool=capacity(),blockers=[])
 folder=WORK/'public/tennis-tracer';folder.mkdir(exist_ok=True)
 # Neighbours share title vocabulary; no invented relationship or player metadata.
 tokens=[set(re.findall('[a-z]{4,}',x['keyword'].lower()))-{'highlights','tennis','shot','shots','extended','2025','2026'} for x in rows]
 for i,row in enumerate(rows):
  related=sorted((j for j in range(len(rows)) if j!=i),key=lambda j:(-len(tokens[i]&tokens[j]),abs(j-i)))[:4]
  (folder/(slug(row)+'.html')).write_text(render(row,[rows[j] for j in related]))
  if (i+1)%50==0:receipt(day,state='generating',generated_count=completed+i+1)
 all_rows=[dict(x) for x in c.execute('select * from keywords where status="published" or (status="reserved" and day=?) order by rowid',(day,))];hubs(all_rows)
 guide=WORK/'public/tennis-ball-tracer.html';s=guide.read_text();addition='<li><a href="/tennis-tracer">Tennis video review guides</a></li>'
 if addition not in s:s=s.replace('<h2>Keep reading</h2><ul>','<h2>Keep reading</h2><ul>'+addition);guide.write_text(s)
 receipt(day,state='building',generated_count=completed+len(rows))
 run([BUN,'install','--frozen-lockfile'],timeout=180);run([BUN,'run','build'],timeout=180)
 records,checks=validate(rows,base)
 manifest=WORK/'content/tennis-tracer/batches'/(day+'-part-'+str(sequence).zfill(3)+'.json');atomic(manifest,dict(day=day,target=batch_target,daily_target=target,sequence=sequence,source_kind='semrush_keywords',base_commit=base,pages=records))
 # Public sitemap mirrors build output, retaining every baseline route.
 (WORK/'public/sitemap.xml').write_bytes((WORK/'dist/sitemap.xml').read_bytes())
 receipt(day,state='validated',validated_count=completed+batch_target,batch_validated_count=batch_target,pages_path=str(manifest),pages_sha256=sha(manifest),checks=checks)
 git('add','public/tennis-tracer','public/tennis-tracer.html','public/tracer-guides.css','public/tracer-guides.js','public/tennis-ball-tracer.html','public/sitemap.xml','content/tennis-tracer','production/tracer-daily')
 if git('diff','--cached','--name-only'):git('commit','-m',f'Add {batch_target} sourced tennis pages for {day}, part {sequence}')
 commit=git('rev-parse','HEAD');receipt(day,state='uploading_prepared',commit=commit)
 git('fetch','origin','main');assert git('rev-parse','origin/main')==base,'main advanced during build; rebase and revalidate before publishing'
 alias_before=api('/v4/aliases/acecut.goswie.com')['deploymentId'];batch='acecut-'+day+'-part-'+str(sequence)
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

def live_bytes(opener,url):
 # Domain promotion can briefly return the previous deployment's cached 404.
 for attempt in range(6):
  try:
   with opener.open(url,timeout=30) as response:return response.read()
  except urllib.error.HTTPError as error:
   if error.code not in (404,429,502,503,504) or attempt==5:raise
   time.sleep(2*(attempt+1))
  except (urllib.error.URLError,TimeoutError,ConnectionError):
   if attempt==5:raise
   time.sleep(2*(attempt+1))

def publish(day,immediate=False):
 if read(HOME/(day+'-receipt.json'),{}).get('source_kind')!='semrush_keywords':raise RuntimeError('Publication requires a verified Semrush keyword batch; video-title batches are prohibited')
 cfg=config();r=read(HOME/(day+'-receipt.json'),{});local=datetime.datetime.now(ZoneInfo(cfg['timezone']))
 if r.get('state')=='published':return r
 if not immediate and (day!=local.date().isoformat() or (local.hour,local.minute)<(cfg['hour'],cfg['minute'])):return
 batch_target=r.get('batch_target',r['target'])
 assert r.get('ready_for_promotion') and r.get('batch_validated_count',r['validated_count'])==batch_target and r['target']==cfg['target'],'No validated batch matching current target'
 assert 0<batch_target<=cfg['target']-r.get('published_count',0),'Batch exceeds remaining daily goal'
 manifest=Path(r['pages_path']);assert sha(manifest)==r['pages_sha256'];m=read(manifest)
 assert m.get('source_kind')=='semrush_keywords' and len(m['pages'])==batch_target
 demand_index=originals(read(HOME/'keyword-input.json'))
 for p in m['pages']:
  assert demand_proven(p,demand_index),'Published keyword demand provenance mismatch'
  assert 0<=p['kd']<30 and p['volume']>100
  assert sha(Path(p['source_path']))==p['source_sha256'] and sha(Path(p['evidence_path']))==p['evidence_sha256']
 for p in m['pages']:assert sha(WORK/'public'/(p['url'].removeprefix(ORIGIN+'/')+'.html'))==p['sha256']
 d=api('/v13/deployments/'+r['prepared_deployment_id']);assert d['projectId']==PROJECT and d['readyState']=='READY' and d['target']=='production' and d['meta']['swieCommit']==r['commit']
 git('fetch','origin','main');head=git('rev-parse','origin/main');assert head in (r['base_commit'],r['commit']),'Production baseline advanced; rebuild before publication'
 # Record in GitHub first, then promote exactly the validated deployment.
 receipt(day,state='publishing',blockers=[])
 if head!=r['commit']:git('push','origin',r['commit']+':refs/heads/main')
 if api('/v4/aliases/acecut.goswie.com')['deploymentId']!=r['prepared_deployment_id']:
  run([CLI,'promote',r['prepared_deployment_id'],'--yes','--scope',SCOPE,'--timeout','90s','--json'],timeout=120)
 alias=api('/v4/aliases/acecut.goswie.com');assert alias['deploymentId']==r['prepared_deployment_id']
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':os.environ.get('ACECUT_VERIFY_PROXY','http://127.0.0.1:7890')}))
 expected={p['url'] for p in m['pages']}
 for attempt in range(6):
  sitemap=live_bytes(opener,ORIGIN+'/sitemap.xml');urls={x.text for x in ET.fromstring(sitemap).findall('{*}url/{*}loc')}
  if expected<=urls:break
  if attempt==5:raise AssertionError('Live sitemap missing batch URLs')
  time.sleep(2*(attempt+1))
 verification_path=HOME/(day+'-part-'+str(r.get('batch_sequence',1))+'-live-check.json')
 verification_key=dict(deployment_id=r['prepared_deployment_id'],pages_sha256=r['pages_sha256'])
 saved=read(verification_path,{})
 verified=[u for u in saved.get('verified_urls',[]) if u in expected] if all(saved.get(k)==v for k,v in verification_key.items()) else []
 verified=list(dict.fromkeys(verified));verified_set=set(verified)
 receipt(day,state='verifying',batch_live_verified_count=len(verified))
 def verify_page(p):
  body=live_bytes(opener,p['url'])
  assert hashlib.sha256(body).hexdigest()==p['sha256'],'Live page differs from validated page: '+p['url']
  return p['url']
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  for url in pool.map(verify_page,[p for p in m['pages'] if p['url'] not in verified_set]):
   verified.append(url)
   if len(verified)%25==0:
    atomic(verification_path,{**verification_key,'verified_urls':verified,'checked_at':now()})
    receipt(day,state='verifying',batch_live_verified_count=len(verified))
 atomic(verification_path,{**verification_key,'verified_urls':verified,'checked_at':now()})
 c=db()
 with c:
  for page in m['pages']:
   c.execute('update keywords set status="published",published_url=? where day=? and normalized=? and status="reserved"',(page['url'],day,page['normalized']))
 total=c.execute('select count(*) from keywords where day=? and status="published"',(day,)).fetchone()[0]
 assert total==r.get('published_count',0)+batch_target,'Published inventory does not match exact batch'
 capacity();rounds=r.get('rounds',[])+[dict(sequence=r.get('batch_sequence',1),published_count=batch_target,live_verified_count=len(verified),pages_path=str(manifest),pages_sha256=r['pages_sha256'],commit=r['commit'],deployment_id=r['prepared_deployment_id'],published_at=now())]
 return receipt(day,state='published' if total==cfg['target'] else 'published_partial',published_count=total,generated_count=total,validated_count=total,live_verified_count=sum(x['live_verified_count'] for x in rounds),batch_live_verified_count=len(verified),shortfall=cfg['target']-total,ready_for_promotion=False,rounds=rounds,keyword_pool=counts(),blockers=[] if total==cfg['target'] else [dict(type='daily_target_shortfall',count=cfg['target']-total)],live_verification=dict(sitemap_url=ORIGIN+'/sitemap.xml',batch_covered=len(expected),total_urls=len(urls),sample_urls=[verified[0],verified[len(verified)//2],verified[-1]],deployment_id=r['prepared_deployment_id'],verified_at=now()))

def tick():
 cfg=config();heartbeat()
 if not cfg['enabled']:return
 local=datetime.datetime.now(ZoneInfo(cfg['timezone']));today=local.date().isoformat();r=read(HOME/(today+'-receipt.json'),{})
 cutoff=(local.hour,local.minute)>=(cfg['hour'],cfg['minute'])
 def attempt(day):
  previous=read(HOME/(day+'-receipt.json'),{})
  if previous.get('state') in ('prepared','published') or previous.get('ready_for_promotion'):return previous
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
 if r.get('state') not in ('prepared','published'):
  r=attempt(today) or read(HOME/(today+'-receipt.json'),{})
 if cutoff and r.get('ready_for_promotion') and r.get('state')!='published':publish(today)
 if r.get('state')=='published' and (local.hour,local.minute)>=(cfg['prepare_hour'],cfg['prepare_minute']):attempt((local.date()+datetime.timedelta(days=1)).isoformat())

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
