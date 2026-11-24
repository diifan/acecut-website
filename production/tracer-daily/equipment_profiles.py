"""Extract attributed numeric specification records, not copied review prose.

Each field retains its exact evidence span. Multiple inconsistent values in a
section are ambiguous and never silently assigned to a model.
"""
import hashlib,json,re
from pathlib import Path
from common import HOME,read

FIELDS={
 'head_size':('Head size',r'Head\s*Size\s*:?\s*(\d+(?:\.\d+)?\s*(?:sq\.?\s*)?(?:in(?:ches)?[²2]?|cm[²2]?))'),
 'length':('Length',r'\bLength\s*:?\s*(\d+(?:\.\d+)?\s*(?:in(?:ches)?|cm))'),
 'strung_weight':('Strung weight',r'\bStrung\s*Weight\s*:?\s*(\d+(?:\.\d+)?\s*(?:oz|grams?|g)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:oz|grams?|g))?)'),
 'unstrung_weight':('Unstrung weight',r'\bUnstrung\s*Weight\s*:?\s*(\d+(?:\.\d+)?\s*(?:oz|grams?|g)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:oz|grams?|g))?)'),
 'listed_weight':('Listed weight (condition as stated)',r'(?<!Strung )(?<!strung )(?<!Unstrung )(?<!unstrung )\bWeight\s*:?\s*(\d+(?:\.\d+)?\s*(?:oz|grams?|g)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:oz|grams?|g))?(?:\s*\((?:unstrung|strung)\))?)'),
 'swingweight':('Swingweight',r'\bSwing\s*weight\s*:?\s*(\d{3}(?:\.\d+)?)\b'),
 'stiffness':('Stiffness rating',r'\b(?:Stiffness|RA Rating)\s*:?\s*(\d{2}(?:\.\d+)?)(?:\s*RA)?\b'),
 'string_pattern':('String pattern',r'\bString\s*Pattern\s*:?\s*(\d{2}\s*(?:[x×/]|Mains\s*/\s*)\s*\d{2}(?:\s*Crosses)?)'),
 'beam_width':('Beam width',r'\bBeam\s*Width\s*:?\s*(\d+(?:\.\d+)?\s*mm(?:\s*[/–-]\s*\d+(?:\.\d+)?\s*mm){0,2})'),
}
STOP={'the','a','an','of','and','for','in','tennis','racquet','racquets','racket','rackets','review','reviews','specs','specifications','gear','legend','new','series','updated','update'}
def tokens(value):
 value=re.sub(r'(?<=\d)\.(?=\d)','',value.casefold())
 return set(re.findall(r'[a-z]+|\d+',value))-STOP
def model_name(heading,title):
 heading=re.sub(r'\b(?:specifications?|specs|strung|unstrung)\b','',heading,flags=re.I).strip(' :-–|')
 if len(tokens(heading))<2 or heading.casefold() in ('technical details','racquet specifications'):heading=title
 heading=re.split(r'\s+[|–-]\s+Tennis',heading,flags=re.I)[0]
 heading=re.sub(r'^(?:Racquet Review:|Review:|The Legend of the|The)\s*','',heading,flags=re.I)
 heading=re.sub(r'\s+(?:Review|Specifications?|Specs)(?:\s*-.*)?$','',heading,flags=re.I)
 heading=re.sub(r',?\s*Aux(?:etic)?\s*\d+(?:\.\d+)?','',heading,flags=re.I)
 heading=re.sub(r'\bReview\b','',heading,flags=re.I)
 return ' '.join(heading.split()).strip()[:150]
def extract(data,url,evidence_path):
 if data.get('http')!=200:return []
 records=[];model_context=data.get('title','')
 for section in data.get('sections',[]):
  heading=section.get('heading','')
  if re.search(r'\b(?:head|babolat|wilson|yonex|prince|dunlop|tecnifibre|solinco|artengo|donnay|volkl|prokennex)\b',heading,re.I) and not re.search(r'\b(?:video|specs|specifications|comparison|versus|vs|and)\b|&',heading,re.I):model_context=heading
  if re.search(r'comment|reply|related|newsletter',section.get('heading',''),re.I):continue
  text=section.get('text','');facts={};ambiguous=False
  for key,(label,pattern) in FIELDS.items():
   matches=list(re.finditer(pattern,text,re.I));values={re.sub(r'\s+',' ',m[1]).strip() for m in matches}
   if len(values)>1:ambiguous=True;break
   if matches:
    m=matches[0];facts[key]={'label':label,'value':m[1].strip(),'evidence':m[0],'offset':m.start()}
  if ambiguous or len(facts)<4 or 'head_size' not in facts or not ({'strung_weight','unstrung_weight','listed_weight'} & facts.keys()):continue
  name=model_name(section.get('heading',''),model_context)
  if len(tokens(name))<2 or re.search(r'\bbest\b|\bvs\b|\bversus\b|\band\b|&',name,re.I):continue
  # Never infer which of several models owns one unlabelled specification block.
  if re.search(r'\b(?:series|lineup|comparison)\b',name,re.I):continue
  identity=hashlib.sha256((' '.join(sorted(tokens(name)))).encode()).hexdigest()[:20]
  records.append({'id':identity,'name':name,'facts':facts,'source_url':url,'evidence_path':str(evidence_path),'section_heading':section.get('heading',''),'source_sha256':data['body_sha256'],'checked_at':data['checked_at']})
 records.extend(extract_tables(data,url,evidence_path))
 groups={}
 for record in records:groups.setdefault(record['id'],[]).append(record)
 result=[]
 for canonical,items in groups.items():
  fields={}
  for record in items:
   for key,fact in record['facts'].items():fields.setdefault(key,set()).add(fact['value'])
  if any(len(values)>1 for values in fields.values()):continue
  record=max(items,key=lambda r:len(r['facts']));record['canonical_id']=canonical;record['id']=hashlib.sha256((canonical+'|'+url).encode()).hexdigest()[:20];result.append(record)
 return result

def extract_tables(data,url,evidence_path):
 records=[]
 for index,table in enumerate(data.get('tables',[])):
  rows=table.get('rows',[])
  if len(rows)<5 or len(rows[0])<3:continue
  headers=rows[0]
  if headers[0].strip().casefold() not in ('spec','specs','specification','specifications'):continue
  for column,name in enumerate(headers[1:],1):
   name=name.strip().rstrip('*');facts={}
   if len(tokens(name))<2:continue
   for row_index,cells in enumerate(rows[1:],1):
    if len(cells)!=len(headers):continue
    value=cells[column].strip();combined=cells[0]+': '+value
    for key,(label,pattern) in FIELDS.items():
     match=re.fullmatch(pattern,combined,re.I)
     # Source cells often include a second unit after the primary value.
     if not match:match=re.match(pattern,combined,re.I)
     if match:
      facts[key]={'label':label,'value':match[1].strip(),'evidence':value,'table_row':row_index,'table_column':column,'source_label':cells[0]}
   if len(facts)<4 or 'head_size' not in facts or not ({'strung_weight','unstrung_weight','listed_weight'}&facts.keys()):continue
   identity=hashlib.sha256((' '.join(sorted(tokens(name)))).encode()).hexdigest()[:20]
   records.append({'id':identity,'name':name,'facts':facts,'source_url':url,'evidence_path':str(evidence_path),'table_index':index,'table_column':column,'section_heading':table.get('heading',''),'source_sha256':data['body_sha256'],'checked_at':data['checked_at']})
 return records

def aligned(word,profile):
 if re.search(r'\b(best|vs|versus|cheap|used|sale|price|cost|buy|alternative|alternatives|shoes?|strings?|bags?|elbow)\b',word,re.I):return False
 wanted=tokens(word);have=tokens(profile['name'])
 if len(wanted)<2:return False
 # A different year, model number or variant must never inherit these specs.
 nums={x for x in wanted if x.isdigit()}
 if not nums<=have:return False
 variants={'pro','mp','team','tour','lite','light','plus','ultra','speed','radical','gravity','blade','clash','shift','percept','ezone','vcore','aero','drive','control'}
 if (wanted&variants)!=(have&variants):return False
 return len(wanted&have)/len(wanted)>=.75

_cache=None;_stamp=None;_sources={}
def registry():
 global _cache,_stamp,_sources
 path=HOME/'equipment-profiles.json'
 stamp=path.stat().st_mtime_ns if path.exists() else None
 if _cache is None or stamp!=_stamp:
  _cache=read(path,{'keywords':{},'profiles':{}});_stamp=stamp;_sources={}
  for value in _cache.get('profiles',{}).values():_sources.setdefault(value['source_url'],[]).append(value)
 return _cache
def for_row(row):
 data=registry();key=data.get('keywords',{}).get(' '.join(row['keyword'].casefold().split()))
 value=data.get('profiles',{}).get(key)
 if value and value['source_url']==row['evidence_url'] and aligned(row['keyword'],value):return value
 return next((p for p in _sources.get(row['evidence_url'],[]) if aligned(row['keyword'],p)),None)
def grounded(profile,data):
 if data.get('body_sha256')!=profile['source_sha256']:return False
 if 'table_index' in profile:
  try:
   rows=data['tables'][profile['table_index']]['rows']
   if rows[0][profile['table_column']].strip().rstrip('*')!=profile['name']:return False
   return all(rows[f['table_row']][f['table_column']].strip()==f['evidence'] and rows[f['table_row']][0]==f['source_label'] for f in profile['facts'].values())
  except (KeyError,IndexError,TypeError):return False
 section=next((s for s in data.get('sections',[]) if s.get('heading','')==profile['section_heading'] and all(f['evidence'] in s.get('text','') for f in profile['facts'].values())),None)
 return bool(section)
