"""Bounded registered review sources for existing, proven demand keywords."""
import concurrent.futures,json,re,time,urllib.robotparser
from pathlib import Path
from common import HOME,read,atomic,now
from keyword_input import db,originals,demand_proven
from equipment_profiles import aligned,extract,grounded
from source_cache import fetch

def harvest():
 binding=read(HOME/'keyword-input.json');root=Path(binding['pool_path']).parent
 registries=sorted(root.glob('source-discovery-*/tennis-warehouse.com'))
 if not registries:return {'status':'no_registered_source'}
 registry=registries[-1];source=read(registry/'receipt.json',{})
 if not source.get('verified'):raise ValueError('Source discovery not verified')
 robot=urllib.robotparser.RobotFileParser();robot.parse((registry/'robots.txt').read_text().splitlines())
 index=originals(binding);c=db();rows=[dict(r) for r in c.execute('select * from keywords where status in ("candidate","needs_review","needs_template","fetch_failed")')];c.close()
 rows=[r for r in rows if demand_proven(r,index)];groups={}
 for item in source.get('candidates',[]):
  url=item['source_url']
  if '/learning_center/racquet_reviews/' not in url or not robot.can_fetch('AceCut-SourceCheck',url):continue
  title=re.sub(r'^(?:(?:sale|reduced)\s+-?\d+%\s*)','',item['keyword'],flags=re.I).split('$')[0].strip()
  matches=[r for r in rows if aligned(r['keyword'],{'name':title})]
  if matches:groups[url]=matches
 if len(groups)>160:raise ValueError('Supplemental source request bound exceeded')
 old=read(HOME/'supplemental-equipment-profiles.json',{});profiles=old.get('profiles',{});words={};receipts=[];matches_by_word={}
 def load(url):
  time.sleep(.5);return fetch(url,'tables')
 with concurrent.futures.ThreadPoolExecutor(2) as pool:
  futures={pool.submit(load,u):u for u in groups}
  for future in concurrent.futures.as_completed(futures):
   url=futures[future];path,data=future.result();found=extract(data,url,path);matched=0
   for p in found:
    if not grounded(p,data):continue
    for row in groups[url]:
     if aligned(row['keyword'],p):
      profiles[p['id']]=p;matches_by_word.setdefault(row['normalized'],{})[p.get('canonical_id',p['id'])]=p['id'];matched+=1
   receipts.append({'url':url,'http':data.get('http'),'profiles':len(found),'matched':matched,'error':data.get('error')})
   if len(receipts)%10==0:print(json.dumps({'checked':len(receipts),'target':len(groups),'profiles':len(profiles),'keywords':len(words)}),flush=True)
 words={word:next(iter(values.values())) for word,values in matches_by_word.items() if len(values)==1}
 result={'pool_sha256':__import__('hashlib').sha256(Path(binding['pool_path']).read_bytes()).hexdigest(),'created_at':now(),'profiles':profiles,'keywords':words,'receipt':receipts,'basis':'Independent factual evidence, with original keyword demand provenance preserved'}
 atomic(HOME/'supplemental-equipment-profiles.json',result);print(json.dumps({'finished':True,'sources':len(groups),'profiles':len(profiles),'keywords':len(words)}),flush=True);return result
if __name__=='__main__':harvest()


def ensure():
 import datetime,hashlib
 binding=read(HOME/'keyword-input.json',{})
 if not binding or not list(Path(binding['pool_path']).parent.glob('source-discovery-*/tennis-warehouse.com/receipt.json')):return
 old=read(HOME/'supplemental-equipment-profiles.json',{})
 age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(old['created_at'])).total_seconds() if old.get('created_at') else float('inf')
 if old.get('pool_sha256')!=hashlib.sha256(Path(binding['pool_path']).read_bytes()).hexdigest() or age>21600:harvest()
