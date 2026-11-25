"""Typed public Wikidata facts, independently bound to existing demand records."""
import collections,datetime,hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote,parse_qs
from common import HOME,read,atomic,now
from keyword_input import db,originals,demand_proven
from tennis_records import fold,tokens,aligned,date

def player(rows,source_url,path,digest,checked):
 names={r.get('personLabel',{}).get('value','') for r in rows};births={r.get('birth',{}).get('value','')[:10] for r in rows}
 if len(names)!=1 or len(births)!=1 or any(r.get('precision',{}).get('value')!='11' for r in rows):return None
 name=next(iter(names));birth=next(iter(births))
 if len(tokens(name))<2 or not date(birth) or birth>checked[:10]:return None
 qid=rows[0]['person']['value'].rsplit('/',1)[-1]
 if not re.fullmatch('Q[0-9]+',qid):return None
 facts=[{'label':'Birth Date','value':birth,'wd_field':'birth'},{'label':'Occupation','value':'Tennis player','wd_field':'occupation'}]
 for field,label in [('countryLabel','Citizenship entries'),('placeLabel','Birthplace')]:
  values=sorted({r[field]['value'] for r in rows if field in r and not re.fullmatch('Q[0-9]+',r[field]['value'])})
  if values and (field!='placeLabel' or len(values)==1):facts.append({'label':label,'value':'; '.join(values),'wd_field':field})
 heights={(r['height']['value'],r.get('unitLabel',{}).get('value')) for r in rows if 'height' in r}
 if len(heights)==1:
  value,unit=next(iter(heights))
  try:valid=unit in ('metre','centimetre') and (0.8<=float(value)<=2.6 if unit=='metre' else 80<=float(value)<=260)
  except ValueError:valid=False
  if valid:facts.append({'label':'Height (source units)','value':value+' '+unit,'wd_field':'height'})
 if len(facts)<4 or not any(f['wd_field']=='countryLabel' for f in facts):return None
 canonical=hashlib.sha256((fold(name)+'|'+birth).encode()).hexdigest()[:20]
 return {'id':hashlib.sha256((canonical+'|'+source_url).encode()).hexdigest()[:20],'canonical_id':canonical,'kind':'player_record','public_bio':True,'name':name,'birth_date':birth,'qid':qid,'facts':facts,'source_url':source_url,'human_source_url':'https://www.wikidata.org/wiki/'+qid,'source_sha256':digest,'evidence_path':str(path),'checked_at':checked}

def identity_supported(word,record,demand_url):
 if re.search(r'\b(age|stats|statistics|rank|ranking|rankings)\b',word,re.I):return False
 if not aligned(word,record):return False
 wanted=tokens(word)-{'tennis','atp','wta','player','profile','height','who','is'}
 if len(wanted)>=2:return True
 if wanted&{'date','mens','court','king','love','young','black','brown','green','rose','white','long'}:return False
 # Surname-only keywords require the original ranking URL to identify the full person.
 u=unquote(demand_url);u=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',u)
 return tokens(record['name'])<=tokens(u)

_snapshots={}
def grounded(record,data):
 if data.get('source_format')!='wikidata_tennis_players_v1' or record['source_sha256']!=data.get('body_sha256'):return False
 source=Path(data.get('source_snapshot_path',''))
 if not source.is_file():return False
 signature=(str(source),source.stat().st_mtime_ns,source.stat().st_size)
 if signature not in _snapshots:
  raw=source.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=record['source_sha256']:return False
  bundle=json.loads(raw);groups=collections.defaultdict(list)
  for row in bundle['data']['results']['bindings']:groups[row['person']['value'].rsplit('/',1)[-1]].append(row)
  _snapshots.clear();_snapshots[signature]=(record['source_sha256'],groups)
 digest,originals=_snapshots[signature]
 if digest!=record['source_sha256']:return False
 rows=data.get('wikidata_players',{}).get(record.get('qid'),[])
 if rows!=originals.get(record.get('qid')):return False
 fresh=player(rows,record['source_url'],record['evidence_path'],record['source_sha256'],record['checked_at']) if rows else None
 return bool(fresh and fresh['name']==record['name'] and fresh['birth_date']==record['birth_date'] and fresh['facts']==record['facts'])

def harvest(index_path):
 raw=Path(index_path).read_bytes();bundle=json.loads(raw);source_url=bundle['source_url'];query=parse_qs(urlsplit(source_url).query).get('query',[''])[0]
 if urlsplit(source_url).hostname!='query.wikidata.org' or 'wdt:P106 wd:Q10833314' not in query or 'precision = 11' not in query:raise ValueError('Unexpected dataset query')
 bindings=bundle['data']['results']['bindings']
 if len(bindings)>=30000:raise ValueError('Incomplete capped dataset')
 digest=hashlib.sha256(raw).hexdigest();checked=now();path=HOME/'source-cache'/(hashlib.sha256(source_url.encode()).hexdigest()+'.json');groups=collections.defaultdict(list)
 for row in bindings:groups[row['person']['value'].rsplit('/',1)[-1]].append(row)
 records={};surnames=collections.defaultdict(list)
 for qid,rows in groups.items():
  r=player(rows,source_url,path,digest,checked)
  if r:records[r['id']]=r;surnames[re.findall('[a-z]+',fold(r['name']))[-1]].append(r)
 binding=read(HOME/'keyword-input.json');index=originals(binding);c=db();words={};selected={};ambiguous=[]
 # Use birth-date + surname + given initial to consolidate spelling/name variants
 # against already grounded records, without claiming every name is globally unique.
 from tennis_records import for_row
 occupied={}
 for row in c.execute('select * from keywords where status in ("published","reserved","verified")'):
  r=for_row(dict(row))
  if r and r['kind']=='player_record':
   parts=re.findall('[a-z]+',fold(r['name']));occupied[(r['birth_date'],parts[-1],parts[0][0])]=r['canonical_id']
 for row in c.execute('select * from keywords where status in ("needs_review","needs_template","fetch_failed","freshness_required","candidate","verified","reserved","published")'):
  row=dict(row)
  if not demand_proven(row,index):continue
  candidates={r['qid']:r for t in tokens(row['keyword']) for r in surnames.get(t,[]) if identity_supported(row['keyword'],r,row.get('demand_url') or row['evidence_url'])}
  if len(candidates)!=1:
   if len(candidates)>1:ambiguous.append(row['keyword'])
   continue
  r=next(iter(candidates.values()));parts=re.findall('[a-z]+',fold(r['name']))
  existing=occupied.get((r['birth_date'],parts[-1],parts[0][0]))
  if existing and existing!=r['canonical_id']:continue
  selected[r['id']]=r;words[row['normalized']]=r['id']
 c.close()
 source_copy=HOME/'public-player-index.json';temporary=source_copy.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(source_copy)
 cache={'source_url':source_url,'http':200,'source_format':'wikidata_tennis_players_v1','body_sha256':digest,'checked_at':checked,'source_snapshot_path':str(source_copy),'representation':'Normalized JSON query response with source URL retained; hash binds saved input bytes','wikidata_players':{r['qid']:groups[r['qid']] for r in selected.values()},'text':'Wikidata tennis player facts','title':'Wikidata tennis player query'}
 atomic(path,cache);result={'created_at':checked,'records':selected,'keywords':words,'ambiguous_keywords':ambiguous,'source_url':source_url,'source_rows':len(bindings),'license':'CC0 structured data'};atomic(HOME/'supplemental-player-records.json',result)
 print(json.dumps({'matched_keywords':len(words),'player_identities':len(selected),'ambiguous':len(ambiguous)}),flush=True);return result

if __name__=='__main__':
 import sys
 harvest(sys.argv[1])

def ensure():
 source=HOME/'public-player-index.json'
 if not source.is_file():return
 binding=read(HOME/'keyword-input.json',{})
 fingerprint=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
 registry=read(HOME/'supplemental-player-records.json',{})
 if registry.get('input_fingerprint')==fingerprint:return
 result=harvest(source);result['input_fingerprint']=fingerprint
 atomic(HOME/'supplemental-player-records.json',result)
