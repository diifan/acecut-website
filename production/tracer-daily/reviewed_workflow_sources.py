"""Reviewed workflow evidence bridges; original keyword demand stays immutable."""
from pathlib import Path
from common import HOME,read,atomic,now
from keyword_input import db,originals,demand_proven
from source_cache import fetch,classify
# Verified official recording setup guide, not an inferred replacement URL.
REVIEWED={'tennis recording':'https://swing.vision/guides/set-up-your-recording'}
def select(home=None):
 home=Path(home or HOME)
 index=originals(read(home/'keyword-input.json'));c=db();changes=[]
 for word,url in REVIEWED.items():
  old=c.execute('select * from keywords where normalized=?',(word,)).fetchone()
  if not old or old['status'] in ('published','reserved','verified'):continue
  row=dict(old)
  if not demand_proven(row,index):continue
  path,evidence=fetch(url);candidate={**row,'evidence_url':url};family,error=classify(candidate,evidence)
  if not family or evidence.get('http')!=200:continue
  demand=row.get('demand_url') or row['evidence_url']
  c.execute('update keywords set demand_url=?,evidence_url=?,evidence_path=?,status="candidate",error=NULL where normalized=?',(demand,url,str(path),word))
  changes.append({'keyword':word,'demand_url':demand,'evidence_url':url,'evidence_sha256':evidence['body_sha256'],'family':family})
 c.commit();c.close();atomic(home/'reviewed-workflow-selection.json',{'at':now(),'changes':changes});return changes
