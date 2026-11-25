"""Use alternate URLs only when backed by an original, hashed Semrush row.

Published/reserved rows remain immutable. Controller CSVs are never rewritten.
"""
import csv,io,sqlite3
from pathlib import Path
from common import HOME,read,atomic,now

def candidate_rows(home):
 home=Path(home);binding=read(home/'keyword-input.json');pool=Path(binding['pool_path'])
 rows=list(csv.DictReader(io.StringIO(pool.read_text(encoding='utf-8-sig'))))
 rows=[{**r,'keyword':r.get('keyword',r.get('Keyword','')),'evidence_url':r.get('evidence_url',r.get('URL','')),'volume':r.get('volume',r.get('Search Volume','0'))} for r in rows]
 file=home/'keyword-pool.sqlite'
 if file.exists():
  c=sqlite3.connect(f'file:{file}?mode=ro',uri=True);c.row_factory=sqlite3.Row
  if c.execute("select 1 from sqlite_master where name='keyword_sources'").fetchone():
   rows.extend(dict(r) for r in c.execute('select k.keyword,s.* from keyword_sources s join keywords k on k.normalized=s.normalized'))
  c.close()
 from keyword_input import url as canonical_url
 normalized=[]
 for row in rows:
  try:row['evidence_url']=canonical_url(row['evidence_url'])
  except ValueError:continue
  normalized.append(row)
 return normalized

def select_verified_alternatives(home=None):
 home=Path(home or HOME);file=home/'keyword-pool.sqlite'
 if not file.exists():return []
 c=sqlite3.connect(file,timeout=60);c.row_factory=sqlite3.Row
 if not c.execute("select 1 from sqlite_master where name='keyword_sources'").fetchone():c.close();return []
 registries=[]
 for filename,field in [('equipment-profiles.json','profiles'),('tennis-records.json','records')]:
  data=read(home/filename,{})
  if data:registries.append((home/filename,data,field))
 changes=[]
 for path,data,field in registries:
  by_url={}
  for record in data.get(field,{}).values():by_url.setdefault(record['source_url'],[]).append(record)
  if field=='profiles':
   from equipment_profiles import aligned,grounded
  else:
   from tennis_records import aligned,grounded
  for row in c.execute('select * from keywords where status not in ("published","reserved","verified")').fetchall():
   for alternative in c.execute('select * from keyword_sources where normalized=? order by metric_timestamp desc,evidence_url',(row['normalized'],)):
    matches=[r for r in by_url.get(alternative['evidence_url'],[]) if aligned(row['keyword'],r)]
    record=next((r for r in matches if grounded(r,read(Path(r['evidence_path']),{}))),None)
    if not record:continue
    values=(alternative['volume'],alternative['kd'],alternative['evidence_url'],alternative['metric_timestamp'],alternative['source_sha256'],alternative['source_path'],record['evidence_path'],alternative['evidence_url'],row['normalized'])
    c.execute('update keywords set volume=?,kd=?,evidence_url=?,metric_timestamp=?,source_sha256=?,source_path=?,evidence_path=?,demand_url=?,status="candidate",error=NULL where normalized=?',values)
    data.setdefault('keywords',{})[row['normalized']]=record['id']
    if row['evidence_url']!=alternative['evidence_url']:changes.append({'keyword':row['keyword'],'before_url':row['evidence_url'],'selected_url':alternative['evidence_url'],'source_path':alternative['source_path'],'source_sha256':alternative['source_sha256'],'reason':'Verified entity/specification with matching original Semrush row'})
    break
  atomic(path,data)
 c.commit();c.close()
 atomic(home/'latest-evidence-selection.json',{'at':now(),'changes':changes,'published_and_reserved':'preserved','controller_csv':'unchanged'})
 return changes
