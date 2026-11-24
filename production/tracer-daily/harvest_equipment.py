"""Bounded source harvest -> factual profiles -> independently verified candidates.
No publishing, source CSV mutation or model-generated specifications.
"""
import io,argparse,concurrent.futures,csv,json,time,re,hashlib,datetime
from pathlib import Path
from common import HOME,read,atomic,now
from source_cache import fetch
from evidence_selection import candidate_rows
from equipment_profiles import extract,aligned

def harvest(limit=2000,network_limit=200,home=None):
 home=Path(home or HOME)
 binding=read(home/'keyword-input.json');rows=candidate_rows(home)
 groups={}
 for row in rows:
  row={**row,'keyword':row.get('keyword',row.get('Keyword','')),'evidence_url':row.get('evidence_url',row.get('URL','')),'volume':row.get('volume',row.get('Search Volume','0'))}
  url=row['evidence_url']
  if not re.search(r'/gear/racquets/|racquet-review|racket-review',url):continue
  if re.search(r'/best-|/the-best-|/top-\d',url):continue
  groups.setdefault(url,[]).append(row)
 # Existing successful structured sources cost no network request; failures remain visible.
 selected=sorted(groups,key=lambda u:(-len(groups[u]),u))[:limit]
 prior=read(home/'equipment-profiles.json',{}).get('profiles',{})
 selected=list(dict.fromkeys(selected+[r['source_url'] for r in prior.values() if r['source_url'] in groups]))
 profiles={};words={};receipts=[];started=now();network=set()
 for url in selected:
  cached=read(home/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json'),{})
  if cached.get('checked_at') and cached.get('http')!=200 and (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(cached['checked_at'])).total_seconds()<1800:continue
  need_tables=bool(re.search(r'tenniscompanion.org/gear/racquets/[^/]+/$',url))
  if not (cached.get('http')==200 and cached.get('sections') and (not need_tables or 'tables' in cached)) and len(network)<network_limit:network.add(url)
 def load(url):
  need_tables=bool(re.search(r'tenniscompanion.org/gear/racquets/[^/]+/$',url))
  if url in network:return fetch(url,'tables' if need_tables else True)
  path=home/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
  return path,read(path,{'error':'Source pending bounded harvest'})
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
  futures={ex.submit(load,url):url for url in selected}
  for future in concurrent.futures.as_completed(futures):
   url=futures[future]
   try:
    path,data=future.result();found=extract(data,url,path);matched=0
    for profile in found:
     eligible=[r for r in groups[url] if aligned(r['keyword'],profile)]
     if not eligible:continue
     # Keep a single source binding for each model identity.
     if profile['id'] in profiles and profiles[profile['id']]['source_url']!=url:continue
     profiles[profile['id']]=profile
     for row in eligible:
      key=' '.join(row['keyword'].casefold().split())
      if key not in words:words[key]=profile['id'];matched+=1
    receipts.append({'url':url,'http':data.get('http'),'profiles':len(found),'matched_keywords':matched,'error':data.get('error')})
   except Exception as error:receipts.append({'url':url,'error':type(error).__name__+': '+str(error)[:200]})
   if len(receipts)%20==0:
    print(json.dumps({'fetched':len(receipts),'target':len(selected),'profiles':len(profiles),'matched_keywords':len(words)}),flush=True)
    atomic(home/'equipment-harvest-progress.json',{'started':started,'checked':len(receipts),'target':len(selected),'profiles':len(profiles),'matched_keywords':len(words)})
 data={'version':1,'created_at':now(),'pool_sha256':hashlib.sha256(Path(binding['pool_path']).read_bytes()).hexdigest(),'profiles':profiles,'keywords':words,'receipt':receipts,'source_candidates':len(groups),'checked_sources':len(selected),'provenance':'Original exported keyword URLs; numeric facts extracted from explicit labelled source sections'}
 atomic(home/'equipment-profiles.json',data)
 print(json.dumps({'finished':True,'profiles':len(profiles),'matched_keywords':len(words),'sources':len(selected)}),flush=True)
 return data

def ensure_profiles(home=None):
 home=Path(home or HOME)
 old=read(home/'equipment-profiles.json',{});binding=read(home/'keyword-input.json',{})
 if not binding:return
 digest=hashlib.sha256(Path(binding['pool_path']).read_bytes()).hexdigest()
 age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(old['created_at'])).total_seconds() if old.get('created_at') else float('inf')
 if old.get('pool_sha256')!=digest or age>21600 or (age>300 and any('pending' in str(r.get('error','')).lower() for r in old.get('receipt',[]))):harvest(network_limit=200,home=home)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=2000);parser.add_argument('--network-limit',type=int,default=200);args=parser.parse_args();harvest(args.limit,args.network_limit)
