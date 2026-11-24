"""Bounded tennis evidence cache, shared per URL; pending fetches are not rejected intents."""
import concurrent.futures,hashlib,html,ipaddress,re,socket,urllib.parse,urllib.request
from html.parser import HTMLParser
from common import *
from keyword_input import db,counts,norm
from intent_router import route
from editorial_topics import topic,supported
class Text(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.title=False;self.head=False;self.parts=[];self.titles=[];self.headings=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','noscript'):self.skip+=1
  if tag=='title':self.title=True
  if tag in ('h1','h2','h3'):self.head=True
 def handle_endtag(self,tag):
  if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
  if tag=='title':self.title=False
  if tag in ('h1','h2','h3'):self.head=False
 def handle_data(self,data):
  if self.skip:return
  s=' '.join(data.split())
  if s:self.parts.append(s)
  if self.title:self.titles.append(s)
  if self.head:self.headings.append(s)

def public_url(url):
 u=urllib.parse.urlsplit(url)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Unsafe source URL')
 for item in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Non-public source host')
 return url
class Redirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return super().redirect_request(req,fp,code,msg,headers,public_url(newurl))
def fetch(url):
 path=HOME/'source-cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json');old=read(path)
 if old and old.get('http')==200:return path,old
 for proxy in dict.fromkeys([PROXY,'http://192.168.0.110:10808']):
  try:
   public_url(url);opener=urllib.request.build_opener(Redirect(),urllib.request.ProxyHandler({'https':proxy}))
   with opener.open(urllib.request.Request(url,headers={'User-Agent':'AceCut-SourceCheck/1.0 (+https://acecut.goswie.com)'}),timeout=20) as r:
    if 'text/html' not in r.headers.get('Content-Type',''):raise ValueError('Expected HTML evidence')
    raw=r.read(1_000_001)
    if len(raw)>1_000_000:raise ValueError('Source exceeds cache byte bound')
    body=raw.decode('utf-8',errors='replace');final=r.url;http=r.status
   parser=Text();parser.feed(body)
   data=dict(source_url=url,final_url=final,http=http,title=' '.join(parser.titles),headings=parser.headings[:40],text=' '.join(parser.parts)[:60000],body_sha256=hashlib.sha256(raw).hexdigest(),checked_at=now())
   break
  except Exception as e:data=dict(source_url=url,http=None,error=type(e).__name__+': '+str(e)[:200],checked_at=now())
 atomic(path,data);return path,data
EXCLUDE=re.compile(r'\b(basketball|golf|pickleball|football|soccer|baseball|betting|odds|tickets|rankings?|salary|net worth|wife|husband|girlfriend|boyfriend|dance|dancing|wedding|death|obituary|restaurant|login|discount|coupon|buy|sale|price|shoes|rackets? for sale|string tension)\b',re.I)
FAMILIES=[('drop_shot',r'\bdrop shots?\b'),('lob',r'\b(?:lobs?|lobbing)\b'),('overhead',r'\boverhead(?: smash)?\b'),('recording',r'\b(?:cameras?|recording|recordings|filming|videos?|highlights?|editing|tracer|ball tracking)\b'),('serve',r'\b(?:serves?|serving|aces?|toss)\b'),('forehand',r'forehand'),('backhand',r'backhand'),('volley',r'volley|net play'),('rally',r'rally|rallies|baseline|groundstroke'),('spin',r'topspin|slice|spin'),('footwork',r'footwork|split step|recovery'),('practice',r'practice|drill|training|technique|swing|tennis form')]
STOP={'how','to','a','an','the','in','on','for','of','and','with','best','tennis','is','what','at','your','my','do','i'}
def classify(row,data):
 word=row['keyword']
 editorial=topic(word)
 routed=route(word,row.get('evidence_url',''),'tennis')
 if routed['routing_state']=='out_of_scope':return None,'unrelated_search_intent'
 family=('editorial:'+editorial) if editorial else next((f for f,p in FAMILIES if re.search(p,word,re.I)),None)
 if not family:return None,('needs_template' if routed['routing_state']=='content_candidate' else routed['routing_state'])
 if not editorial and EXCLUDE.search(word):return None,('needs_template' if routed['routing_state']=='content_candidate' else routed['routing_state'])
 if data.get('http')!=200:return None,'source_fetch_pending'
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
