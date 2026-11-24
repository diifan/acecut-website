"""Bounded tennis evidence cache, shared per URL; pending fetches are not rejected intents."""
import concurrent.futures,hashlib,html,ipaddress,re,socket,urllib.parse,urllib.request,ast,requests,threading
from html.parser import HTMLParser
from common import *
from keyword_input import db,counts,norm
from intent_router import route
from editorial_topics import topic,supported
from equipment_profiles import for_row,grounded
from tennis_records import for_row as record_for_row,grounded as record_grounded
class Text(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.title=False;self.head=False;self.parts=[];self.titles=[];self.headings=[];self.sections=[];self.section_heading='';self.section_parts=[];self.heading_parts=[];self.tables=[];self.table=None;self.table_row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='table':self.table={'heading':self.section_heading,'rows':[]}
  if tag=='tr' and self.table is not None:self.table_row=[]
  if tag in ('th','td') and self.table_row is not None:self.cell=[]
  if tag in ('script','style','noscript'):self.skip+=1
  if tag=='title':self.title=True
  if tag in ('h1','h2','h3'):
   if self.section_parts:self.sections.append({'heading':self.section_heading,'text':' '.join(self.section_parts)[:16000]})
   self.section_parts=[];self.heading_parts=[];self.head=True
 def handle_endtag(self,tag):
  if tag in ('th','td') and self.cell is not None:
   self.table_row.append(' '.join(self.cell));self.cell=None
  if tag=='tr' and self.table_row is not None:
   self.table['rows'].append(self.table_row);self.table_row=None
  if tag=='table' and self.table is not None:
   self.tables.append(self.table);self.table=None
  if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
  if tag=='title':self.title=False
  if tag in ('h1','h2','h3'):self.section_heading=' '.join(self.heading_parts);self.head=False
 def handle_data(self,data):
  if self.skip:return
  s=' '.join(data.split())
  if s:self.parts.append(s)
  if s and self.cell is not None:self.cell.append(s)
  if self.title:self.titles.append(s)
  if self.head:self.headings.append(s);self.heading_parts.append(s)
  elif s:self.section_parts.append(s)

def public_url(url):
 u=urllib.parse.urlsplit(url)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Unsafe source URL')
 for item in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Non-public source host')
 return url
class Redirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return super().redirect_request(req,fp,code,msg,headers,public_url(newurl))
_http=threading.local()

def fetch(url,structured=False):
 path=HOME/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json');old=read(path)
 if old and old.get('http')!=200 and old.get('checked_at'):
  import datetime
  if (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(old['checked_at'])).total_seconds()<1800:return path,old
 if old and old.get('http')==200 and (not structured or (old.get('sections') and (structured not in ('tables','entity') or ('tables' in old and (structured!='entity' or 'player_fields' in old))))):return path,old
 for proxy in dict.fromkeys([PROXY,'http://192.168.0.110:10808']):
  try:
   if not hasattr(_http,'session'):
    _http.session=requests.Session();_http.session.trust_env=False
   current=url
   for hop in range(6):
    public_url(current)
    with _http.session.get(current,headers={'User-Agent':'AceCut-SourceCheck/1.0 (+https://acecut.goswie.com)'},proxies={'https':proxy},timeout=(8,20),stream=True,allow_redirects=False) as response:
     if response.status_code in (301,302,303,307,308):
      current=urllib.parse.urljoin(current,response.headers.get('Location',''));public_url(current);continue
     response.raise_for_status()
     if 'text/html' not in response.headers.get('Content-Type',''):raise ValueError('Expected HTML evidence')
     chunks=[];size=0
     for chunk in response.iter_content(32768):
      size+=len(chunk)
      if size>1_000_000:raise ValueError('Source exceeds cache byte bound')
      chunks.append(chunk)
     raw=b''.join(chunks);body=raw.decode('utf-8',errors='replace');final=current;http=response.status_code;break
   else:raise ValueError('Source redirect limit exceeded')
   parser=Text();parser.feed(body)
   if parser.section_parts:parser.sections.append({'heading':parser.section_heading,'text':' '.join(parser.section_parts)[:16000]})
   player_fields={}
   if urllib.parse.urlsplit(url).hostname in ('www.tennisabstract.com','tennisabstract.com'):
    for field in ('fullname','dob','ht','hand','backhand','country','currentrank','peakrank','peakfirst'):
     values=re.findall(r'var\s+'+field+r'\s*=\s*([^;]{1,200});',body)
     if len(set(values))==1:
      try:
       value=ast.literal_eval(values[0].strip())
       if isinstance(value,(str,int,float)):player_fields[field]={'value':value,'literal':values[0].strip()}
      except (ValueError,SyntaxError):pass
   data=dict(source_url=url,final_url=final,http=http,title=' '.join(parser.titles),headings=parser.headings[:40],text=' '.join(parser.parts)[:60000],body_sha256=hashlib.sha256(raw).hexdigest(),checked_at=now(),sections=parser.sections[:100],tables=parser.tables[:40],player_fields=player_fields)
   break
  except Exception as e:data=dict(source_url=url,http=None,error=type(e).__name__+': '+str(e)[:200],checked_at=now())
 atomic(path,data);return path,data
EXCLUDE=re.compile(r'\b(basketball|golf|pickleball|football|soccer|baseball|betting|odds|tickets|rankings?|salary|net worth|wife|husband|girlfriend|boyfriend|dance|dancing|wedding|death|obituary|restaurant|login|discount|coupon|buy|sale|price|shoes|rackets? for sale|string tension)\b',re.I)
FAMILIES=[('drop_shot',r'\bdrop shots?\b'),('lob',r'\b(?:lobs?|lobbing)\b'),('overhead',r'\boverhead(?: smash)?\b'),('recording',r'\b(?:cameras?|recording|recordings|filming|videos?|highlights?|editing|tracer|ball tracking)\b'),('serve',r'\b(?:serves?|serving|aces?|toss)\b'),('forehand',r'forehand'),('backhand',r'backhand'),('volley',r'volley|net play'),('rally',r'rally|rallies|baseline|groundstroke'),('spin',r'topspin|slice|spin'),('footwork',r'footwork|split step|recovery'),('practice',r'practice|drill|training|technique|swing|tennis form')]
STOP={'how','to','a','an','the','in','on','for','of','and','with','best','tennis','is','what','at','your','my','do','i'}
def classify(row,data):
 word=row['keyword']
 profile=for_row(row);record=record_for_row(row)
 editorial=topic(word)
 routed=route(word,row.get('evidence_url',''),'tennis')
 if routed['routing_state']=='out_of_scope':return None,'unrelated_search_intent'
 family=('record:'+record['id']) if record else ('equipment:'+profile['id']) if profile else ('editorial:'+editorial) if editorial else next((f for f,p in FAMILIES if re.search(p,word,re.I)),None)
 if not family:return None,('needs_template' if routed['routing_state']=='content_candidate' else routed['routing_state'])
 if not editorial and not profile and not record and EXCLUDE.search(word):return None,('needs_template' if routed['routing_state']=='content_candidate' else routed['routing_state'])
 if data.get('http')!=200:return None,'source_fetch_pending'
 if record:return (family,None) if record_grounded(record,data) else (None,'source_record_facts_changed')
 if profile:return (family,None) if grounded(profile,data) else (None,'source_equipment_facts_changed')
 if editorial:
  return (family,None) if supported(word,data) else (None,'source_topic_answer_not_supported')
 text=norm(data.get('text',''));identity=norm(data.get('title','')+' '+' '.join(data.get('headings',[]))+' '+urllib.parse.urlsplit(row['evidence_url']).path.replace('-',' '))
 if 'tennis' not in text or len(text)<300:return None,'source_not_tennis_or_insufficient_text'
 core=norm(data.get('title','')+' '+urllib.parse.urlsplit(row['evidence_url']).path.replace('-',' '))
 for stroke in ('forehand','backhand','serve'):
  if re.search(r'\b'+stroke+r'\b',norm(word)) and stroke not in core and any(other in core for other in ('forehand','backhand','serve') if other!=stroke):
   return None,'source_keyword_identity_not_aligned'
 tokens=set(re.findall(r'[a-z0-9]+',norm(word)))-STOP
 matches=sum(t in identity for t in tokens)
 if not tokens or matches/max(1,len(tokens))<.65:return None,'source_keyword_identity_not_aligned'
 from evidence_text import context_excerpt
 try:context_excerpt(word,data.get('text',''))
 except ValueError:return None,'source_context_inadequate'
 return family,None

def intent_key(row):
 record=record_for_row(row)
 if record:return 'record:'+record.get('canonical_id',record['id'])
 profile=for_row(row)
 if profile:return 'equipment:'+profile.get('canonical_id',profile['id'])
 editorial=topic(row['keyword'])
 if editorial:return 'editorial:'+editorial
 family=next((f for f,p in FAMILIES if re.search(p,row['keyword'],re.I)),None)
 return (family or 'unknown')+'|'+row['evidence_url']

def verify(day):
 c=db();rows=[dict(r) for r in c.execute('select * from keywords where status in ("candidate","fetch_failed","needs_template","needs_review","freshness_required","specialist_review") or (status="excluded" and error in ("no_supported_tracer_workflow_intent","unrelated_search_intent"))')]
 # Apply the existing keyword-only exclusions before spending source fetches.
 # This does not relax evidence gates for any potentially usable topic.
 wanted=[]
 for row in rows:
  _,error=classify(row,{})
  if error in ('unrelated_search_intent','needs_template','needs_review','specialist_review','freshness_required','out_of_scope'):
   status='excluded' if error in ('unrelated_search_intent','out_of_scope') else error
   c.execute('update keywords set status=?,error=? where normalized=?',(status,error,row['normalized']))
  else:wanted.append(row)
 c.commit();rows=wanted
 urls=list(dict.fromkeys(r['evidence_url'] for r in rows));lookup={};receipt(day,state='fetching_keyword_evidence',keyword_pool=counts())
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  futures={pool.submit(fetch,u):u for u in urls}
  for i,f in enumerate(concurrent.futures.as_completed(futures)):
   u=futures[f];lookup[u]=f.result()
   if (i+1)%50==0:receipt(day,state='fetching_keyword_evidence',source_fetch_completed=i+1,source_fetch_target=len(urls),keyword_pool=counts())
 occupied={intent_key(dict(r)) for r in c.execute('select * from keywords where status in ("verified","reserved","published")')}
 for i,row in enumerate(rows):
  path,data=lookup[row['evidence_url']];family,error=classify(row,data)
  if family and intent_key(row) in occupied:family=None;error='duplicate_source_intent'
  status='verified' if family else 'fetch_failed' if error=='source_fetch_pending' else 'excluded'
  if family:occupied.add(intent_key(row))
  c.execute('update keywords set status=?,evidence_path=?,error=? where normalized=?',(status,str(path),error,row['normalized']))
  if (i+1)%50==0:c.commit();receipt(day,state='validating_keyword_relevance',keyword_pool=counts())
 c.commit();receipt(day,state='keyword_evidence_checked' if counts()['verified_available'] else 'insufficient_keywords',keyword_pool=counts());return counts()
