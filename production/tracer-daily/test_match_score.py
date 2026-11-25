import copy,json,unittest
from unittest.mock import patch
from match_score import extract_score
import tennis_records as tr,content_engine as ce
URL='https://www.tennis.com/tournaments/c/matches/e-lys-vs-k-volynets-2026-03-30'
def fixture():
 event={'@type':'SportsEvent','url':URL,'eventStatus':'https://schema.org/EventCompleted','startDate':'2026-03-30T23:00:00Z','homeTeam':{'name':'Eva Lys'},'awayTeam':{'name':'Katie Volynets'},'superEvent':{'name':'Charleston'}}
 body='<script type="application/ld+json">'+json.dumps(event)+'</script><article class="Match-module__card"><a href="'+URL+'"></a>'
 for label,values in [('E. Lys',[(3,None),(6,3)]),('K. Volynets',[(6,None),(7,7)])]:
  body+='<div class="Match-module__competitorRow"><span class="PlayerRow-module__name">'+label+'</span><span class="PlayerRow-module__seed">12</span>'
  for games,tie in values:body+='<span class="SetScore-module__cell"><span class="SetScore-module__games">'+str(games)+'</span>'+('' if tie is None else '<sup class="SetScore-module__tiebreak">'+str(tie)+'</sup>')+'</span>'
  body+='</div>'
 return body+'</article>'
class ScoreTests(unittest.TestCase):
 def data(self):
  return {'http':200,'title':'Eva Lys vs Katie Volynets · Round 1 · Charleston | Tennis.com','text':'Completed March 31, 2026','checked_at':'2026-11-25T10:00:00Z','body_sha256':'fixture','tables':[],'match_score':extract_score(fixture(),URL)}
 def test_seed_and_tiebreak_are_not_games(self):
  d=extract_score(fixture(),URL);self.assertEqual(d['rows'][1]['sets'],[{'games':6,'tiebreak':None},{'games':7,'tiebreak':7}]);self.assertNotIn('12',str(d['rows']))
 def test_h2h_cards_cannot_replace_main_card(self):
  other=fixture().replace(URL,URL.replace('03-30','03-29'))
  self.assertEqual(extract_score(fixture()+other,URL),extract_score(fixture(),URL))
 def test_ambiguous_duplicate_card_rejected(self):self.assertIsNone(extract_score(fixture()+fixture(),URL))
 def test_unfinished_event_and_incomplete_set_rejected(self):
  self.assertIsNone(extract_score(fixture().replace('EventCompleted','EventScheduled'),URL))
  self.assertIsNone(extract_score(fixture().replace('__games">7','__games">4'),URL))
 def test_missing_or_wrong_structured_identity_rejected(self):
  self.assertIsNone(extract_score(fixture().split('</script>')[1],URL))
  d=self.data();d['match_score']['players'][0]='Jane Lys';self.assertIsNone(tr.extract(d,URL,'cache'))
 def test_utc_date_can_differ_from_display_but_must_match_url(self):
  d=self.data();r=tr.extract(d,URL,'cache');self.assertEqual(r['match_date'],'2026-03-30');self.assertTrue(tr.grounded(r,d));self.assertTrue(tr.aligned('lys vs volynets',r));self.assertFalse(tr.aligned('lys vs volynets live',r))
  d['match_score']['start_date']='2026-03-29T23:00:00Z';self.assertIsNone(tr.extract(d,URL,'cache'))
 def test_changed_score_or_facts_invalidates_grounding(self):
  d=self.data();r=tr.extract(d,URL,'cache');changed=copy.deepcopy(d);changed['match_score']['rows'][0]['sets'][0]['games']=4;self.assertFalse(tr.grounded(r,changed));r['facts'][0]['left']='99';self.assertFalse(tr.grounded(r,d))
 def test_score_page_does_not_claim_service_statistics(self):
  d=self.data();r=tr.extract(d,URL,'cache')
  with patch.object(ce,'shell',side_effect=lambda title,description,path,body:body):body=ce.render_record({'keyword':'lys vs volynets'},r)
  self.assertIn('tie-break points',body);self.assertIn('2026-03-30T23:00:00Z',body);self.assertNotIn('percentage points',body)
if __name__=='__main__':unittest.main()
