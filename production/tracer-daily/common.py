"""AceCut-only runtime contract. No credentials belong in receipts."""
import datetime,fcntl,json,os,subprocess,hashlib,time
from pathlib import Path
from zoneinfo import ZoneInfo
HOME=Path('/data/swi-algo/Swi-IP-Config/swie-app-mac/data/tracer-daily-acecut')
REPORT=Path('/data/swi-algo/Swi-IP-Config/swie-app-mac/reports/seo-expansion-20261124')
WORK=Path('/data/swi-algo/Swi-App-Factory/Acecut/website-seo-daily')
BUN='/var/lib/swi-codex/.bun/bin/bun'
CLI='/var/lib/swi-codex/agent-relay/bin/vercel'
PROJECT='prj_7RDDXImL9f7HgQtFmZ1TsPMG6CLC'
SCOPE='diifans-projects'
ORIGIN='https://acecut.goswie.com'
PROXY='http://192.168.0.110:10808'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default

def atomic(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.'+str(os.getpid())+'.tmp')
 with t.open('w') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def config():
 c=read(HOME/'config.json');assert isinstance(c['enabled'],bool)
 assert isinstance(c['target'],int) and 1<=c['target']<=10000
 for k,m in [('hour',23),('minute',59),('prepare_hour',23),('prepare_minute',59)]:assert isinstance(c[k],int) and 0<=c[k]<=m
 ZoneInfo(c['timezone']);return c

def receipt(day,**updates):
 r=read(HOME/(day+'-receipt.json'),dict(app='acecut',day=day,target=config()['target'],state='starting',generated_count=0,validated_count=0,published_count=0,keyword_pool={},keyword_sources=[],pages_path=None,commit=None,deployment_url=None,schedule={},blockers=[]))
 r.update(updates);r['last_progress_at']=now();r['schedule'].update(config=str(HOME/'config.json'),**config())
 atomic(HOME/(day+'-receipt.json'),r)
 state=read(HOME/'state.json',{'runs':[]});state['heartbeat']=now();row={k:r[k] for k in ('day','target','state','generated_count','published_count')};row.update(validated_count=r['validated_count'],last_progress_at=r['last_progress_at'],blockers=r['blockers'])
 state['runs']=[x for x in state['runs'] if x['day']!=day]+[row];atomic(HOME/'state.json',state)
 if day=='2026-11-24':
  atomic(REPORT/'acecut-receipt.json',r)
  text=f"# AceCut 现有官网新增 SEO 页面\n\n状态：{r['state']}。目标 {r['target']}；生成 {r['generated_count']}；验证 {r['validated_count']}；发布 {r['published_count']}。\n\n词源：{json.dumps(r['keyword_sources'],ensure_ascii=False)}\n\n词池：{json.dumps(r['keyword_pool'],ensure_ascii=False)}\n\n阻塞/失败：{json.dumps(r['blockers'],ensure_ascii=False)}\n\n更新时间：{r['last_progress_at']}\n"
  if r.get('implementation'):text+='\n## 执行器实现与验收\n\n'+json.dumps(r['implementation'],ensure_ascii=False,indent=2)+'\n'
  contract=WORK/'production/tracer-daily/INPUT-CONTRACT.md'
  if contract.exists():text+='\n'+contract.read_text()
  p=REPORT/'acecut-progress.md';t=p.with_suffix('.tmp');t.write_text(text);os.replace(t,p)
 return r

def run(args,cwd=None,timeout=120):
 if cwd is None:cwd=WORK
 env=dict(os.environ,HTTP_PROXY=PROXY,HTTPS_PROXY=PROXY,http_proxy=PROXY,https_proxy=PROXY,PATH='/var/lib/swi-codex/.bun/bin:'+os.environ.get('PATH',''))
 p=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 started=time.monotonic()
 while True:
  try:out,err=p.communicate(timeout=20);break
  except subprocess.TimeoutExpired:
   heartbeat()
   if time.monotonic()-started>timeout:p.kill();p.communicate();raise TimeoutError('Command deadline exceeded: '+str(args[:2]))
 if p.returncode:raise RuntimeError(str(args[:3])+': '+err[-1000:])
 return out.strip()
def heartbeat():
 state=read(HOME/'state.json',{'runs':[]});state['heartbeat']=now();atomic(HOME/'state.json',state)

def git(*args):return run(['git','-c','http.proxy='+PROXY,*args])
def api(path):return json.loads(run([CLI,'api',path,'--scope',SCOPE]))
def lock():
 HOME.mkdir(parents=True,exist_ok=True);f=(HOME/'executor.lock').open('w');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return f

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
