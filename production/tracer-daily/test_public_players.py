import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import public_player_records as pr,content_engine as ce

def row(name='Kimiko Date'):
 return {k:{'value':v} for k,v in {'person':'http://www.wikidata.org/entity/Q229104','personLabel':name,'birth':'1970-09-28T00:00:00Z','precision':'11','countryLabel':'Japan','placeLabel':'Kyoto','height':'163','unitLabel':'centimetre'}.items()}
class PublicPlayers(unittest.TestCase):
 def record(self,rows=None):return pr.player(rows or [row()],'https://query.wikidata.org/sparql?query=fixture','cache','digest','2026-11-25T10:00:00Z')
 def test_typed_facts_do_not_invent_rankings(self):
  p=self.record();self.assertEqual(p['birth_date'],'1970-09-28');self.assertEqual(p['facts'][-1]['value'],'163 centimetre');self.assertFalse(any('rank' in f['label'].lower() for f in p['facts']))
 def test_precision_and_conflicting_birthdates_rejected(self):
  r=row();r['precision']['value']='10';self.assertIsNone(self.record([r]));r=row();r['birth']['value']='1971-09-28T00:00:00Z';self.assertIsNone(self.record([row(),r]))
 def test_generic_queries_cannot_become_surname_pages(self):
  p=self.record();self.assertFalse(pr.identity_supported('tennis date',p,'https://example.test/kimiko-date'))
  self.assertTrue(pr.identity_supported('kimiko date tennis',p,'https://example.test/article'));self.assertFalse(pr.identity_supported('kimiko date ranking',p,'https://example.test/kimiko-date'))
  p=self.record([row('Maria Kirilenko')]);self.assertFalse(pr.identity_supported('kirilenko tennis',p,'https://example.test/tennis'))
  self.assertTrue(pr.identity_supported('kirilenko tennis',p,'https://example.test/players/maria-kirilenko'))
 def test_grounding_rechecks_saved_query_response(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'source.json';raw=json.dumps({'data':{'results':{'bindings':[row()]}}}).encode();path.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest();p=pr.player([row()],'https://query.wikidata.org/sparql?query=fixture','cache',digest,'2026-11-25T10:00:00Z')
   d={'source_format':'wikidata_tennis_players_v1','body_sha256':digest,'source_snapshot_path':str(path),'wikidata_players':{'Q229104':[row()]}}
   self.assertTrue(pr.grounded(p,d));changed=copy.deepcopy(d);changed['wikidata_players']['Q229104'][0]['countryLabel']['value']='Invented';self.assertFalse(pr.grounded(p,changed))
   path.write_bytes(b'tampered');self.assertFalse(pr.grounded(p,d))
 def test_missing_height_not_inferred_and_render_has_source(self):
  r=row();r.pop('height');p=self.record([r]);self.assertFalse(pr.identity_supported('kimiko date height',p,'https://example.test/kimiko-date'))
  with patch.object(ce,'shell',side_effect=lambda title,description,path,body:body):body=ce.render_record({'keyword':'kimiko date'},p)
  self.assertIn('Q229104',body);self.assertIn('Citizenship',body);self.assertNotIn('ranking snapshot',body)
if __name__=='__main__':unittest.main()
