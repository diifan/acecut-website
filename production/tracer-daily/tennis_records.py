"""Dated, source-grounded player references and completed-match statistics.

No supplied footage, live-score promise, inferred winner or unverified biography.
"""
import datetime,hashlib,re,unicodedata
from urllib.parse import urlsplit
from common import HOME,read

def fold(value):
 return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if not unicodedata.combining(c))
def tokens(value):return set(re.findall(r'[a-z]+',fold(value)))
def date(value):
 value=re.sub(r'\s*\(.*?\)','',str(value)).strip()
 for fmt in ('%b %d, %Y','%B %d, %Y','%Y%m%d','%Y-%m-%d'):
  try:return datetime.datetime.strptime(value,fmt).date().isoformat()
  except ValueError:pass
 return None
PLAYER_LABELS={'Birth Date','Height','Plays','Year Turned Pro','Singles Ranking','Singles Points','Doubles Ranking','Doubles Points','Career High Singles Ranking','Career High Doubles Ranking'}
STAT_LABELS={'Aces','Double Faults','1st Serve %','1st Serve Points Won','2nd Serve Points Won','Break Points Saved','Service Games','1st Return Points Won','2nd Return Points Won','Break Points Won','Return Games'}
BAD_QUERY=re.compile(r'\b(wife|husband|girlfriend|boyfriend|net worth|salary|betting|odds|prediction|predictions|live|stream|tickets|injury|injured|nude|naked)\b',re.I)

def _extract(data,url,path):
 if data.get('http')!=200:return None
 u=urlsplit(url);text=data.get('text','');title=data.get('title','');facts=[]
 base={'source_url':url,'evidence_path':str(path),'source_sha256':data.get('body_sha256'),'checked_at':data['checked_at']}
 if u.hostname in ('www.tennis.com','tennis.com') and '/matches/' in u.path:
  parts=title.split(' | ')[0].split(' · ');names=parts[0].split(' vs ')
  found=re.search(r'-(\d{4}-\d{2}-\d{2})$',u.path)
  if len(names)!=2 or not found or not date(found[1]) or not re.search(r'\bCompleted\b',text):return None
  match_date=found[1]
  if match_date>data['checked_at'][:10]:return None
  # Date in the URL must agree with the visible event date.
  visible_dates={date(m[0]) for m in re.finditer(r'(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}',text)}
  if match_date not in visible_dates:return None
  for ti,table in enumerate(data.get('tables',[])):
   rows=table.get('rows',[])
   if not rows or len(rows[0])!=3 or rows[0][1]!='Statistic':continue
   # Check that the displayed columns are the same two players, in this order.
   if any(list(re.findall(r'[a-z]+',fold(names[i])))[-1] not in tokens(rows[0][2*i]) for i in (0,1)):continue
   for ri,row in enumerate(rows[1:],1):
    if len(row)==3 and row[1] in STAT_LABELS and all(re.fullmatch(r'\d+(?:%\s*\(\d+/\d+\))?',row[i]) for i in (0,2)):
     facts.append({'label':row[1],'left':row[0],'right':row[2],'table':ti,'row':ri,'evidence':row})
  if len({f['label'] for f in facts})<6:return None
  return {**base,'id':hashlib.sha256((match_date+'|'+'|'.join(sorted(fold(n) for n in names))+'|'+' · '.join(parts[1:])).encode()).hexdigest()[:20],'kind':'match_record','name':parts[0],'players':names,'event':' · '.join(parts[1:]),'match_date':match_date,'facts':facts}
 if u.hostname in ('www.tennis.com','tennis.com') and '/players-rankings/' in u.path:
  name=title.split(' | ')[0].strip()
  if len(tokens(name))<2:return None
  for ti,table in enumerate(data.get('tables',[])):
   for ri,row in enumerate(table.get('rows',[])):
    if len(row)==2 and row[0] in PLAYER_LABELS and row[1] not in ('','—','-','0'):
     facts.append({'label':row[0],'value':row[1],'table':ti,'row':ri,'evidence':row})
  dob=next((date(f['value']) for f in facts if f['label']=='Birth Date'),None)
 elif u.hostname in ('www.tennisabstract.com','tennisabstract.com') and re.search(r'/[w]?player(?:-classic)?\.cgi$',u.path):
  fields=data.get('player_fields',{});name=str(fields.get('fullname',{}).get('value',''));dob=date(fields.get('dob',{}).get('value',''))
  mapping={'dob':'Birth Date','ht':'Height (cm)','hand':'Playing hand code','backhand':'Backhand code','country':'Country code','currentrank':'Singles Ranking','peakrank':'Career High Singles Ranking','peakfirst':'First peak-ranking date'}
  for key,label in mapping.items():
   raw=fields.get(key,{}).get('value')
   if raw in (None,'',0,'0'):continue
   value=date(raw) if key in ('dob','peakfirst') else str(raw)
   if not value:continue
   facts.append({'label':label,'value':value,'variable':key,'literal':fields[key]['literal'],'raw_value':raw})
  if tokens(name)-tokens(title):return None
 else:return None
 if not dob or len(facts)<4 or len(tokens(name))<2:return None
 identity=hashlib.sha256((fold(name)+'|'+dob).encode()).hexdigest()[:20]
 return {**base,'id':identity,'kind':'player_record','name':name,'birth_date':dob,'facts':facts}

def extract(data,url,path):
 record=_extract(data,url,path)
 if record:
  record['canonical_id']=record['id'];record['id']=hashlib.sha256((record['canonical_id']+'|'+url).encode()).hexdigest()[:20]
 return record

def aligned(word,record):
 if BAD_QUERY.search(word):return False
 if record['kind']=='match_record':
  if not re.search(r'\bvs\.?\b|\bversus\b',word,re.I):return False
  sides=re.split(r'\bvs\.?\b|\bversus\b',word,flags=re.I)
  if len(sides)!=2:return False
  a,b=record['players'];surnames=[re.findall(r'[a-z]+',fold(n))[-1] for n in (a,b)]
  forward=all(surnames[i] in tokens(sides[i]) for i in (0,1));reverse=all(surnames[1-i] in tokens(sides[i]) for i in (0,1))
  all_names=tokens(a+' '+b);stop={'vs','versus','tennis','atp','wta','result','results','score','scores','match'}|tokens(record.get('event',''))
  query=tokens(word)-stop
  def side_matches(side,name):
   wanted=tokens(side)-stop;have=tokens(name)
   return bool(wanted) and all(t in have or (len(t)==1 and any(n.startswith(t) for n in have)) for t in wanted)
  exact=(side_matches(sides[0],a) and side_matches(sides[1],b)) or (side_matches(sides[0],b) and side_matches(sides[1],a))
  explicit_dates=set(re.findall(r'\b20\d{2}-\d{2}-\d{2}\b',word))
  if explicit_dates and explicit_dates!={record['match_date']}:return False
  years=set(re.findall(r'\b20\d{2}\b',word))
  return bool((forward or reverse) and exact and query and (not years or years=={record['match_date'][:4]}))
 if 'height' in word.casefold() and not any(f['label'].startswith('Height') for f in record['facts']):return False
 if re.search(r'\brank(?:ing)?\b',word,re.I) and not any('Ranking' in f['label'] for f in record['facts']):return False
 wanted=tokens(word)-{'tennis','atp','wta','player','profile','age','height','ranking','rank','stats','statistics','who','is'};actual=tokens(record['name'])
 surname=re.findall(r'[a-z]+',fold(record['name']))[-1]
 # The original ranking URL binds this query to this exact player record.
 # Allow given-name initials, but never a surname initial or a different full name.
 given=actual-{surname}
 matches=all(t in actual or (len(t)==1 and any(n.startswith(t) for n in given)) for t in wanted)
 return bool(wanted and surname in wanted and matches)

def grounded(record,data):
 if record['source_sha256']!=data.get('body_sha256'):return False
 for fact in record['facts']:
  if 'variable' in fact:
   if data.get('player_fields',{}).get(fact['variable'])!={'value':fact['raw_value'],'literal':fact['literal']}:return False
  else:
   try:
    if data['tables'][fact['table']]['rows'][fact['row']]!=fact['evidence']:return False
   except (KeyError,IndexError,TypeError):return False
 return True

_cache=None;_stamp=None;_sources={}
def registry():
 global _cache,_stamp,_sources
 path=HOME/'tennis-records.json';stamp=path.stat().st_mtime_ns if path.exists() else None
 if _cache is None or stamp!=_stamp:
  _cache=read(path,{'records':{},'keywords':{}});_stamp=stamp;_sources={}
  for value in _cache.get('records',{}).values():_sources.setdefault(value['source_url'],[]).append(value)
 return _cache
def for_row(row):
 data=registry();ident=data.get('keywords',{}).get(' '.join(row['keyword'].casefold().split()));record=data.get('records',{}).get(ident)
 if record and row.get('evidence_url','')==record['source_url'] and aligned(row['keyword'],record):return record
 return next((r for r in _sources.get(row.get('evidence_url',''),[]) if aligned(row['keyword'],r)),None)
