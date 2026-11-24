"""Bounded tennis evidence cache, shared per URL; pending fetches are not rejected intents."""
import concurrent.futures,hashlib,html,ipaddress,re,socket,urllib.parse,urllib.request
from html.parser import HTMLParser
from common import *
from keyword_input import db,counts,norm
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
 try:
  public_url(url);opener=urllib.request.build_opener(Redirect(),urllib.request.ProxyHandler({'https':PROXY}))
  with opener.open(urllib.request.Request(url,headers={'User-Agent':'AceCut-SourceCheck/1.0 (+https://acecut.goswie.com)'}),timeout=20) as r:
   if 'text/html' not in r.headers.get('Content-Type',''):raise ValueError('Expected HTML evidence')
   raw=r.read(1_000_001)
   if len(raw)>1_000_000:raise ValueError('Source exceeds cache byte bound')
   body=raw.decode('utf-8',errors='replace');final=r.url;http=r.status
  parser=Text();parser.feed(body)
  data=dict(source_url=url,final_url=final,http=http,title=' '.join(parser.titles),headings=parser.headings[:40],text=' '.join(parser.parts)[:60000],body_sha256=hashlib.sha256(raw).hexdigest(),checked_at=now())
 except Exception as e:data=dict(source_url=url,http=None,error=type(e).__name__+': '+str(e)[:200],checked_at=now())
 atomic(path,data);return path,data
EXCLUDE=re.compile(r'\b(basketball|golf|pickleball|football|soccer|baseball|betting|odds|tickets|rankings?|salary|net worth|wife|husband|death|obituary|restaurant|login|discount|coupon|buy|sale|price|shoes|rackets? for sale|string tension)\b',re.I)
FAMILIES=[('recording',r'camera|record|filming|video|highlight|editing|tracer|ball track'),('serve',r'\bserve|serving|aces?\b|toss'),('forehand',r'forehand'),('backhand',r'backhand'),('volley',r'volley|net play'),('rally',r'rally|rallies|baseline|groundstroke'),('spin',r'topspin|slice|spin'),('footwork',r'footwork|split step|recovery'),('practice',r'practice|drill|training|technique|swing|tennis form')]
STOP={'how','to','a','an','the','in','on','for','of','and','with','best','tennis','is','what','at','your','my','do','i'}
def classify(row,data):
 word=row['keyword']
 if EXCLUDE.search(word):return None,'unrelated_search_intent'
 family=next((f for f,p in FAMILIES if re.search(p,word,re.I)),None)
 if not family:return None,'no_supported_tracer_workflow_intent'
 if data.get('http')!=200:return None,'source_fetch_pending'
 text=norm(data.get('text',''));identity=norm(data.get('title','')+' '+' '.join(data.get('headings',[]))+' '+urllib.parse.urlsplit(row['evidence_url']).path.replace('-',' '))
 if 'tennis' not in text or len(text)<300:return None,'source_not_tennis_or_insufficient_text'
 tokens=set(re.findall(r'[a-z0-9]+',norm(word)))-STOP
 matches=sum(t in identity for t in tokens)
 if not tokens or matches/max(1,len(tokens))<.65:return None,'source_keyword_identity_not_aligned'
 return family,None

def verify(day):
 c=db();rows=[dict(r) for r in c.execute('select * from keywords where status in ("candidate","fetch_failed")')]
 urls=list(dict.fromkeys(r['evidence_url'] for r in rows));lookup={};receipt(day,state='fetching_keyword_evidence',keyword_pool=counts())
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  futures={pool.submit(fetch,u):u for u in urls}
  for i,f in enumerate(concurrent.futures.as_completed(futures)):
   u=futures[f];lookup[u]=f.result()
   if (i+1)%50==0:receipt(day,state='fetching_keyword_evidence',source_fetch_completed=i+1,source_fetch_target=len(urls),keyword_pool=counts())
 occupied={r[0] for r in c.execute('select evidence_url from keywords where status in ("verified","reserved","published")')}
 for i,row in enumerate(rows):
  path,data=lookup[row['evidence_url']];family,error=classify(row,data)
  if family and row['evidence_url'] in occupied:family=None;error='duplicate_source_intent'
  status='verified' if family else 'fetch_failed' if error=='source_fetch_pending' else 'excluded'
  if family:occupied.add(row['evidence_url'])
  c.execute('update keywords set status=?,evidence_path=?,error=? where normalized=?',(status,str(path),error,row['normalized']))
  if (i+1)%50==0:c.commit();receipt(day,state='validating_keyword_relevance',keyword_pool=counts())
 c.commit();receipt(day,state='keyword_evidence_checked' if counts()['verified_available'] else 'insufficient_keywords',keyword_pool=counts());return counts()
