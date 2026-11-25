"""Bounded collection of publicly rendered player facts and completed-match data."""
import time
import io,argparse,collections,concurrent.futures,csv,datetime,hashlib,json,re,threading,os,fcntl
from pathlib import Path
from urllib.parse import urlsplit
from common import HOME,read,atomic,now
from source_cache import fetch
from evidence_selection import candidate_rows
from tennis_records import extract,aligned,BAD_QUERY

def _harvest(limit=12000,network_limit=500,home=None):
 home=Path(home or HOME);binding=read(home/'keyword-input.json');pool=Path(binding['pool_path']);rows=candidate_rows(home);groups={}
 for row in rows:
  row={**row,'keyword':row.get('keyword',row.get('Keyword','')),'evidence_url':row.get('evidence_url',row.get('URL','')),'volume':row.get('volume',row.get('Search Volume','0'))}
  url=row['evidence_url'];u=urlsplit(url)
  if (u.hostname in ('www.tennis.com','tennis.com') and ('/players-rankings/' in u.path or '/matches/' in u.path)) or (u.hostname in ('www.tennisabstract.com','tennisabstract.com') and re.search(r'/[w]?player(?:-classic)?\.cgi$',u.path)):
   groups.setdefault(url,[]).append(row)
 selected=sorted(groups,key=lambda u:(-max(float(r['volume']) for r in groups[u]),u))[:limit]
 prior=read(home/'tennis-records.json',{}).get('records',{})
 selected=list(dict.fromkeys(selected+[r['source_url'] for r in prior.values() if r['source_url'] in groups]))
 score_urls=set()
 network=set();locks=collections.defaultdict(lambda:threading.BoundedSemaphore(8))
 for url in selected:
  cached=read(home/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json'),{})
  if cached.get('checked_at') and cached.get('http')!=200 and not ('TypeError:' in cached.get('error','') and cached.get('parser_version')!=2) and (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(cached['checked_at'])).total_seconds()<1800:continue
  host=urlsplit(url).hostname or ''
  backoff=read(home/'source-host-backoff'/(hashlib.sha256(host.encode()).hexdigest()+'.json'),{})
  if backoff.get('retry_at',0)>time.time():continue
  needs_score=('/matches/' in url and 'match_score' not in cached and not extract(cached,url,'cached') and any(re.search(r'\bvs\b|\bversus\b',r['keyword'],re.I) and not BAD_QUERY.search(r['keyword']) for r in groups[url]))
  if needs_score:score_urls.add(url)
  if (needs_score or not (cached.get('http')==200 and 'player_fields' in cached and 'tables' in cached)) and len(network)<network_limit:network.add(url)
 def load(url):
  if url in network:
   with locks[urlsplit(url).hostname]:return fetch(url,'score' if url in score_urls else 'entity')
  path=home/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json');return path,read(path,{'error':'Pending bounded source harvest'})
 records={};words={};receipts=[];started=now()
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  futures={ex.submit(load,url):url for url in selected}
  for future in concurrent.futures.as_completed(futures):
   url=futures[future]
   try:
    path,data=future.result();record=extract(data,url,path);matched=0
    if record:
     eligible=[r for r in groups[url] if aligned(r['keyword'],record)]
     if eligible and (record['id'] not in records or records[record['id']]['source_url']==url):
      records[record['id']]=record
      for row in eligible:
       key=' '.join(row['keyword'].casefold().split())
       if key not in words:words[key]=record['id'];matched+=1
    receipts.append({'url':url,'http':data.get('http'),'kind':record.get('kind') if record else None,'matched_keywords':matched,'error':data.get('error')})
   except Exception as error:receipts.append({'url':url,'error':type(error).__name__+': '+str(error)[:200]})
   if len(receipts)%100==0:
    progress={'started':started,'checked':len(receipts),'target':len(selected),'records':len(records),'matched_keywords':len(words),'kinds':dict(collections.Counter(r['kind'] for r in records.values()))}
    atomic(home/'records-harvest-progress.json',progress);print(json.dumps(progress),flush=True)
 data={'version':1,'created_at':now(),'pool_sha256':hashlib.sha256(pool.read_bytes()).hexdigest(),'records':records,'keywords':words,'receipt':receipts,'selected_sources':len(selected),'network_requests':len(network),'pending_score_sources':len(score_urls-network)}
 atomic(home/'tennis-records.json',data)
 print(json.dumps({'finished':True,'records':len(records),'matched_keywords':len(words),'kinds':dict(collections.Counter(r['kind'] for r in records.values()))}),flush=True);return data

def harvest(limit=12000,network_limit=500,home=None):
 home=Path(home or HOME)
 with (home/'records-harvest.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return {'status':'busy'}
  atomic(home/'records-harvest-running.json',{'pid':os.getpid(),'started':now()})
  try:return _harvest(limit,network_limit,home)
  finally:(home/'records-harvest-running.json').unlink(missing_ok=True)

def ensure_records(home=None):
 home=Path(home or HOME);binding=read(home/'keyword-input.json',{})
 running=read(home/'records-harvest-running.json',{})
 if running.get('pid'):
  try:os.kill(running['pid'],0);return
  except ProcessLookupError:pass
 if not binding:return
 old=read(home/'tennis-records.json',{});digest=hashlib.sha256(Path(binding['pool_path']).read_bytes()).hexdigest()
 age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(old['created_at'])).total_seconds() if old.get('created_at') else float('inf')
 if old.get('pool_sha256')!=digest or age>21600 or (age>300 and (old.get('pending_score_sources',0)>0 or any('pending' in str(r.get('error','')).lower() for r in old.get('receipt',[])))):harvest(network_limit=500,home=home)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=12000);p.add_argument('--network-limit',type=int,default=500);a=p.parse_args();harvest(a.limit,a.network_limit)
