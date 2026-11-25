import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import equipment_profiles as eq,tennis_records as tr,source_cache as sc,content_engine as ce

class EvidenceEngines(unittest.TestCase):
 def data(self):return {'http':200,'body_sha256':'fixture-sha','checked_at':'2026-11-24T12:00:00+00:00','title':'Head Speed MP Review','text':'Tennis fixture','sections':[],'tables':[]}
 def specs(self,size=100,weight=318):return f'Head Size: {size} in² Length: 27in Strung Weight: {weight}g Swingweight: 317 Stiffness: 66 String Pattern: 16 Mains / 19 Crosses'
 def test_spec_values_and_variant_alignment(self):
  d=self.data();d['sections']=[{'heading':'Head Speed MP','text':self.specs()}];r=eq.extract(d,'https://example.test/mp','fixture')[0]
  self.assertEqual(r['facts']['head_size']['value'],'100 in²');self.assertTrue(eq.grounded(r,d));self.assertTrue(eq.aligned('head speed mp tennis racket',r));self.assertFalse(eq.aligned('head speed pro',r));self.assertFalse(eq.aligned('head speed',r))
 def test_conflicting_values_not_silently_selected(self):
  d=self.data();d['sections']=[{'heading':'Head Speed MP','text':self.specs()+self.specs(98,305)}]
  self.assertEqual(eq.extract(d,'https://example.test/mp','fixture'),[])
 def test_model_context_and_comparison_table(self):
  d=self.data();d['title']='Head Speed Pro and MP';d['sections']=[{'heading':'HEAD Speed MP Review','text':'context'},{'heading':'Specifications','text':self.specs()}]
  r=eq.extract(d,'https://example.test/mp','fixture')[0];self.assertEqual(r['name'],'HEAD Speed MP')
  d['sections']=[];d['tables']=[{'heading':'Comparison','rows':[['Spec','Head Speed MP','Head Speed Pro'],['Head Size','100 in²','98 in²'],['Length','27 in','27 in'],['Strung Weight','318g','330g'],['Swingweight','317','330']]}]
  records=eq.extract(d,'https://example.test/models','fixture');self.assertEqual(len(records),2)
  self.assertEqual(records[1]['facts']['head_size']['value'],'98 in²');self.assertTrue(eq.grounded(records[1],d))
  d['tables'][0]['rows'][1][2]='105 in²';self.assertFalse(eq.grounded(records[1],d))
 def test_player_facts_and_diacritics(self):
  d=self.data();d['title']='Jiří Lehečka | Tennis.com';d['tables']=[{'heading':'Jiří Lehečka','rows':[['Birth Date','Nov 8, 2001 (25)'],['Height','—'],['Plays','Right-Handed'],['Singles Ranking','14'],['Career High Singles Ranking','13']]}]
  r=tr.extract(d,'https://www.tennis.com/players-rankings/jiri-lehecka','fixture');self.assertEqual(r['birth_date'],'2001-11-08');self.assertTrue(tr.aligned('jiri lehecka tennis',r));self.assertFalse(tr.aligned('jiri lehecka height',r));self.assertFalse(tr.aligned('jiri lehecka wife',r));self.assertTrue(tr.grounded(r,d))
 def match(self):
  d=self.data();d['title']='Eva Lys vs Katie Volynets · Round 1 · Charleston | Tennis.com';d['text']='Charleston March 30, 2026 Completed Watch'
  labels=['Aces','Double Faults','1st Serve %','1st Serve Points Won','2nd Serve Points Won','Break Points Saved']
  d['tables']=[{'heading':'Match','rows':[['E. Lys','Statistic','K. Volynets']]+[['2' if i<2 else '50% (1/2)',k,'3' if i<2 else '60% (3/5)'] for i,k in enumerate(labels)]}]
  return d
 def test_match_identity_date_and_grounding(self):
  d=self.match();r=tr.extract(d,'https://www.tennis.com/tournaments/charleston/matches/e-lys-vs-k-volynets-2026-03-30','fixture');self.assertTrue(tr.aligned('eva lys vs katie volynets',r));self.assertTrue(tr.aligned('volynets vs lys',r));self.assertFalse(tr.aligned('jane lys vs katie volynets',r));self.assertFalse(tr.aligned('eva lys vs katie volynets 2025',r));self.assertFalse(tr.aligned('eva lys vs katie volynets wimbledon',r));self.assertFalse(tr.aligned('eva lys vs katie volynets live',r));self.assertTrue(tr.grounded(r,d))
  changed=copy.deepcopy(d);changed['tables'][0]['rows'][1][0]='99';self.assertFalse(tr.grounded(r,changed))
 def test_upcoming_match_not_historical_record(self):
  d=self.match();d['text']=d['text'].replace('Completed','Upcoming');self.assertIsNone(tr.extract(d,'https://www.tennis.com/tournaments/c/matches/e-lys-vs-k-volynets-2026-03-30','fixture'))
 def test_table_parser_keeps_cells_separate(self):
  p=sc.Text();p.feed('<h1>Player</h1><table><tr><th>Birth Date</th><td><span>Nov 8, 2001</span></td></tr></table>')
  self.assertEqual(p.tables[0]['rows'],[['Birth Date','Nov 8, 2001']])
 def test_public_inline_data_is_parsed_not_executed(self):
  raw=b"<html><title>Tennis Abstract: Emma Navarro</title><script>var fullname = 'Emma Navarro';var dob = 20010518;var country = 'USA';var hand = 'R';var ht = 170;var peakrank = 8;</script></html>"
  response=MagicMock();response.__enter__.return_value=response;response.status_code=200;response.headers={'Content-Type':'text/html'};response.iter_content.side_effect=lambda n:iter([raw])
  with tempfile.TemporaryDirectory() as temp,patch.object(sc,'HOME',Path(temp)),patch.object(sc,'public_url',side_effect=lambda u:u),patch.object(sc._http,'session',create=True) as session:
   session.get.return_value=response;_,d=sc.fetch('https://www.tennisabstract.com/cgi-bin/wplayer.cgi?p=EmmaNavarro','entity')
  self.assertEqual(d['player_fields']['fullname']['value'],'Emma Navarro');self.assertEqual(d['text'],'Tennis Abstract: Emma Navarro')
  record=tr.extract(d,'https://www.tennisabstract.com/cgi-bin/wplayer.cgi?p=EmmaNavarro','fixture');self.assertTrue(tr.grounded(record,d));self.assertEqual(record['name'],'Emma Navarro')
 def test_record_renderer_is_dated_and_has_no_inferred_winner(self):
  d=self.match();r=tr.extract(d,'https://www.tennis.com/tournaments/c/matches/e-lys-vs-k-volynets-2026-03-30','fixture')
  row={'keyword':'eva lys vs katie volynets'}
  with patch.object(ce,'shell',side_effect=lambda title,description,path,body:body):html=ce.render_record(row,r)
  self.assertIn('2026-03-30',html);self.assertIn('percentage points',html);self.assertIn('not a live score',html);self.assertNotIn('winner',html)

if __name__=='__main__':unittest.main()

class PublicationStateTests(unittest.TestCase):
 def test_refresh_preserves_prepared_and_published_receipts(self):
  import executor
  from unittest.mock import patch
  for state in ('prepared','published'):
   with patch.object(executor,'read',return_value={'state':state}),patch.object(executor,'ingest') as ingest:
    self.assertEqual(executor.refresh('2099-01-01'),{'state':state});ingest.assert_not_called()
 def test_transient_live_404_retries_but_auth_failure_does_not(self):
  import executor,urllib.error
  from unittest.mock import MagicMock,patch
  opener=MagicMock();response=MagicMock();response.__enter__.return_value.read.return_value=b'expected'
  opener.open.side_effect=[urllib.error.HTTPError('https://example.test',404,'Not yet propagated',{},None),response]
  with patch.object(executor.time,'sleep'):
   self.assertEqual(executor.live_bytes(opener,'https://example.test'),b'expected')
  opener.open.side_effect=urllib.error.HTTPError('https://example.test',403,'Forbidden',{},None)
  with self.assertRaises(urllib.error.HTTPError):executor.live_bytes(opener,'https://example.test')

class EvidenceCooldownTests(unittest.TestCase):
 def test_recent_source_failure_does_not_repeat_network_request(self):
  import source_cache
  from unittest.mock import patch
  from common import now
  old={'http':None,'error':'source timeout','checked_at':now()}
  with patch.object(source_cache,'read',return_value=old),patch.object(source_cache,'public_url') as network_guard:
   path,data=source_cache.fetch('https://example.test/source','entity')
   self.assertEqual(data,old);network_guard.assert_not_called()

class EquipmentLabelVariants(unittest.TestCase):
 def test_parenthetical_weight_and_metric_length_keep_exact_condition(self):
  d={'http':200,'body_sha256':'fixture','checked_at':'2026-11-25','title':'Head Speed MP Review','tables':[],'sections':[{'heading':'Head Speed MP','text':'Head size: 100 in² Weight (unstrung): 300g Length: 685 mm Balance: 320 mm Stringing Pattern: 16/19'}]}
  r=eq.extract(d,'https://example.test/mp','fixture')[0]
  self.assertEqual(r['facts']['unstrung_weight']['value'],'300g');self.assertNotIn('strung_weight',r['facts']);self.assertEqual(r['facts']['length']['value'],'685 mm');self.assertEqual(r['facts']['balance']['value'],'320 mm');self.assertTrue(eq.grounded(r,d))
 def test_multiple_unstrung_weights_remain_ambiguous(self):
  d={'http':200,'body_sha256':'fixture','checked_at':'2026-11-25','title':'Head Speed MP Review','tables':[],'sections':[{'heading':'Head Speed MP','text':'Head size: 100 in² Weight (unstrung): 300g Weight (unstrung): 315g Length: 685 mm Balance: 320 mm String Pattern: 16/19'}]}
  self.assertEqual(eq.extract(d,'https://example.test/mp','fixture'),[])


class IndependentSpecTables(unittest.TestCase):
 def test_dual_unit_tables_are_not_conflicting_models(self):
  d={'http':200,'body_sha256':'fixture','checked_at':'2026-11-25','title':'Head Speed MP Review','sections':[],'tables':[{'heading':'Tech Specs','rows':[['Length','27 in'],['Head Size','100 sq in'],['Weight','11.2 oz'],['Balance Point','12.99 in'],['String Pattern','16 x 19']]},{'heading':'Tech Specs','rows':[['Length','68.58 cm'],['Head Size','645.16 sq cm'],['Weight','318 g'],['Balance Point','32.99 cm'],['String Pattern','16 x 19']]}]}
  records=eq.extract(d,'https://www.tennis-warehouse.com/learning_center/racquet_reviews/fixture.html','fixture');self.assertEqual(len(records),1);r=records[0]
  self.assertEqual(r['facts']['length']['value'],'27 in');self.assertEqual(r['facts']['listed_weight']['value'],'11.2 oz');self.assertTrue(eq.grounded(r,d))
  with patch.object(ce,'shell',side_effect=lambda title,description,path,body:body):body=ce.render_equipment({'keyword':'head speed mp'},d,r)
  self.assertIn('Balance',body)
  d['tables'][0]['rows'][2][1]='99 oz';self.assertFalse(eq.grounded(r,d))


class ExactEquipmentIdentity(unittest.TestCase):
 def test_alphabetic_variant_cannot_be_dropped(self):
  self.assertFalse(eq.aligned('yonex vcore 100 s',{'name':'Yonex VCORE 100+ 8th Gen Racquet'}))
  self.assertFalse(eq.aligned('wilson pro staff x v14',{'name':'Wilson Pro Staff 97 v14'}))
  self.assertFalse(eq.aligned('yonex vcore 100',{'name':'Yonex VCORE 100+ 8th Gen Racquet'}))
  self.assertTrue(eq.aligned('yonex vcore 100 plus',{'name':'Yonex VCORE 100+ 8th Gen Racquet'}))
