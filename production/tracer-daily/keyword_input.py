"""Strict Semrush input boundary. Producer owned by controller; never writes its CSV."""
import csv,io,math,re,sqlite3,unicodedata,urllib.parse
from common import *

def norm(value):return ' '.join(unicodedata.normalize('NFKC',str(value)).split()).casefold()
def metric(value):
 try:n=float(str(value).replace(',',''))
 except (ValueError,TypeError):raise ValueError('Invalid metric')
 if not math.isfinite(n) or n<0:raise ValueError('Invalid metric')
 return n

def url(value):
 u=urllib.parse.urlsplit(value)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (443,None):raise ValueError('Source must be a public HTTPS URL')
 return urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,u.query,''))
def field(row,*names,default=''):
 for n in names:
  if row.get(n) not in (None,''):return row[n]
 return default

def parse(row):
 keyword=field(row,'keyword','Keyword');volume=metric(field(row,'volume','Search Volume'));kd=metric(field(row,'kd','Keyword Difficulty'))
 if not norm(keyword):raise ValueError('Empty keyword')
 if not (kd<30 and volume>100):raise ValueError('Outside strict KD<30 and volume>100 thresholds')
 source_url=url(field(row,'evidence_url','URL','source_url'))
 timestamp=field(row,'metric_timestamp','Timestamp')
 if not timestamp:raise ValueError('Missing metric timestamp')
 return dict(keyword=keyword.strip(),normalized=norm(keyword),volume=volume,kd=kd,evidence_url=source_url,metric_timestamp=timestamp)

def db():
 c=sqlite3.connect(HOME/'keyword-pool.sqlite',timeout=60);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS keywords (normalized TEXT PRIMARY KEY, keyword TEXT NOT NULL, volume REAL NOT NULL,kd REAL NOT NULL,evidence_url TEXT NOT NULL,metric_timestamp TEXT NOT NULL,source_sha256 TEXT NOT NULL,source_path TEXT NOT NULL,status TEXT NOT NULL DEFAULT "candidate",day TEXT,published_url TEXT,evidence_path TEXT,error TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS keyword_sources(normalized TEXT,volume REAL,kd REAL,evidence_url TEXT,metric_timestamp TEXT,source_sha256 TEXT,source_path TEXT,PRIMARY KEY(normalized,evidence_url,metric_timestamp,source_sha256))')
 c.execute('CREATE TABLE IF NOT EXISTS import_runs (pool_sha256 TEXT,manifest_sha256 TEXT,imported_at TEXT,counts TEXT)');return c

def bind(pool,manifest):
 pool=Path(pool).resolve();manifest=Path(manifest).resolve();data=read(manifest)
 if data.get('app','acecut')!='acecut' or data.get('sport','tennis')!='tennis':raise ValueError('Manifest belongs to another app/sport')
 if not isinstance(data.get('sources'),list):raise ValueError('Manifest requires original CSV sources array')
 binding=dict(app='acecut',pool_path=str(pool),manifest_path=str(manifest),bound_at=now())
 # Validate all originals before recording a binding.
 originals(binding)
 atomic(HOME/'keyword-input.json',binding);return binding

def originals(binding):
 pool=Path(binding['pool_path']);manifest=Path(binding['manifest_path'])
 if binding.get('pool_sha256') and sha(pool)!=binding['pool_sha256']:raise ValueError('Input pool changed during import; retry snapshot')
 if binding.get('manifest_sha256') and sha(manifest)!=binding['manifest_sha256']:raise ValueError('Input manifest changed during import; retry snapshot')
 data=read(manifest);index={}
 if data.get('sha256') and data['sha256']!=sha(pool):raise ValueError('Manifest pool SHA256 mismatch')
 for source in data['sources']:
  p=Path(source.get('archive') or source.get('local_path') or source.get('path') or source.get('source_path',''))
  if not p.is_absolute():p=manifest.parent/p
  digest=sha(p)
  if digest!=source.get('sha256'):raise ValueError('Original source CSV hash mismatch')
  for row in csv.DictReader(io.StringIO(p.read_text(encoding='utf-8-sig'))):
   try:r=parse(row)
   except ValueError:continue
   key=(r['normalized'],r['volume'],r['kd'],r['evidence_url'],str(r['metric_timestamp']))
   index.setdefault(key,[]).append((digest,str(p.resolve())))
 return index

def ingest():
 binding=read(HOME/'keyword-input.json')
 if not binding:raise RuntimeError('Waiting for controller Semrush keywords.csv/source manifest paths; video-title input disabled')
 binding=dict(binding,pool_sha256=sha(Path(binding['pool_path'])),manifest_sha256=sha(Path(binding['manifest_path'])))
 index=originals(binding);c=db()
 alternatives=[(key[0],key[1],key[2],key[3],key[4],digest,path) for key,matches in index.items() for digest,path in matches]
 c.executemany('INSERT OR IGNORE INTO keyword_sources VALUES(?,?,?,?,?,?,?)',alternatives)
 counts={'input_rows':0,'added':0,'existing_preserved':0,'rejected':0,'unproven':0};errors=[]
 for row in csv.DictReader(io.StringIO(Path(binding['pool_path']).read_text(encoding='utf-8-sig'))):
  counts['input_rows']+=1
  try:r=parse(row)
  except ValueError as e:counts['rejected']+=1;continue
  key=(r['normalized'],r['volume'],r['kd'],r['evidence_url'],str(r['metric_timestamp']));matches=index.get(key,[]);specified=field(row,'source_sha256')
  if specified:matches=[m for m in matches if m[0]==specified]
  if not matches:counts['unproven']+=1;continue
  digest,source=matches[0]
  existing=c.execute('select status from keywords where normalized=?',(r['normalized'],)).fetchone()
  if existing:counts['existing_preserved']+=1;continue
  incoming=field(row,'status').lower();status='published' if incoming=='published' else 'reserved' if incoming in ('reserved','prepared') else 'candidate'
  # Never recycle externally reserved/published words. Publication evidence stays external.
  day=field(row,'day','batch_id') or None;published_url=field(row,'url') if status=='published' else None
  c.execute('INSERT INTO keywords(normalized,keyword,volume,kd,evidence_url,metric_timestamp,source_sha256,source_path,status,day,published_url) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(r['normalized'],r['keyword'],r['volume'],r['kd'],r['evidence_url'],r['metric_timestamp'],digest,source,status,day,published_url));counts['added']+=1
 if sha(Path(binding['pool_path']))!=binding['pool_sha256'] or sha(Path(binding['manifest_path']))!=binding['manifest_sha256']:
  c.rollback();raise RuntimeError('Producer snapshot changed during import; retry')
 c.execute('insert into import_runs values(?,?,?,?)',(binding['pool_sha256'],binding['manifest_sha256'],now(),json.dumps(counts)));c.commit()
 atomic(HOME/'latest-keyword-import.json',dict(binding=binding,counts=counts,at=now()));return counts

def counts():
 c=db();states={r[0]:r[1] for r in c.execute('select status,count(*) from keywords group by status')}
 reasons={r[0]:r[1] for r in c.execute('select error,count(*) from keywords where error is not null group by error')}
 funnel={'imported_keywords':sum(states.values()),'intent_rejected':sum(reasons.get(k,0) for k in ('unrelated_search_intent','no_supported_tracer_workflow_intent')),'source_fetch_pending':states.get('fetch_failed',0),'source_or_context_rejected':sum(reasons.get(k,0) for k in ('source_keyword_identity_not_aligned','source_not_tennis_or_insufficient_text','source_context_inadequate','source_topic_answer_not_supported')),'consolidated_source_candidates':reasons.get('duplicate_source_intent',0),'needs_template':states.get('needs_template',0),'needs_review':states.get('needs_review',0),'freshness_required':states.get('freshness_required',0),'specialist_review':states.get('specialist_review',0),'unique_available_pages':states.get('verified',0)}
 return dict(funnel=funnel,path=str(HOME/'keyword-pool.sqlite'),source_kind='semrush_keywords',status_counts=states,candidate_count=sum(states.values()),fetch_pending_count=states.get('candidate',0)+states.get('fetch_failed',0),verified_available=states.get('verified',0),filters={'kd_lt':30,'volume_gt':100})
