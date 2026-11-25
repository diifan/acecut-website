"""Independent factual sources never replace original demand-metric provenance."""
from pathlib import Path
from common import HOME,read,atomic,now
from keyword_input import db,originals,demand_proven
from equipment_profiles import aligned,grounded

def select(home=None):
 home=Path(home or HOME);data=read(home/'supplemental-equipment-profiles.json',{})
 if not data:return []
 index=originals(read(home/'keyword-input.json'));c=db();changes=[]
 for row in c.execute('select * from keywords where status in ("candidate","needs_review","needs_template","fetch_failed")').fetchall():
  row=dict(row)
  if not demand_proven(row,index):continue
  profile=data.get('profiles',{}).get(data.get('keywords',{}).get(row['normalized']))
  if not profile or not aligned(row['keyword'],profile):
   if row.get('demand_url') and row['demand_url']!=row['evidence_url']:
    c.execute('update keywords set evidence_url=demand_url,evidence_path=NULL,status="candidate",error=NULL where normalized=?',(row['normalized'],))
   continue
  evidence=read(Path(profile['evidence_path']),{})
  if evidence.get('http')!=200 or evidence.get('source_url')!=profile['source_url'] or not grounded(profile,evidence):continue
  demand_url=row.get('demand_url') or row['evidence_url']
  c.execute('update keywords set demand_url=?,evidence_url=?,evidence_path=?,status="candidate",error=NULL where normalized=?',(demand_url,profile['source_url'],profile['evidence_path'],row['normalized']))
  changes.append({'keyword':row['keyword'],'demand_url':demand_url,'factual_source_url':profile['source_url'],'metric_source_sha256':row['source_sha256']})
 c.commit();c.close();atomic(home/'supplemental-evidence-selection.json',{'at':now(),'changes':changes});return changes
