import unittest
from unittest.mock import patch
import source_cache as s
from content_engine import WORKFLOWS
class TacticalRecovery(unittest.TestCase):
 def test_new_families_require_source(self):
  with patch.object(s,'for_row',return_value=None),patch.object(s,'record_for_row',return_value=None):
   for word in ['singles tennis strategy','proper tennis grip']:
    self.assertEqual(s.classify({'keyword':word,'evidence_url':'https://example.org/tennis'},{}),(None,'source_fetch_pending'))
 def test_grip_product_not_hand_position(self):
  with patch.object(s,'for_row',return_value=None),patch.object(s,'record_for_row',return_value=None):
   self.assertIsNone(s.classify({'keyword':'tennis grip size','evidence_url':'https://example.org/tennis-grip-size'},{'http':200})[0])
 def test_identity_and_context_gates(self):
  with patch.object(s,'for_row',return_value=None),patch.object(s,'record_for_row',return_value=None),patch('evidence_text.context_excerpt',return_value='context'):
   row={'keyword':'singles tennis strategy','evidence_url':'https://example.org/singles-tennis-strategy'}
   data={'http':200,'title':'Singles tennis strategy','text':'Tennis singles strategy and point decisions. '*20}
   self.assertEqual(s.classify(row,data),('tactics',None));self.assertIn('tactics',WORKFLOWS)
   self.assertEqual(s.classify(row,{**data,'http':403}),(None,'source_fetch_pending'))
 def test_medical_query_blocked(self):
  with patch.object(s,'for_row',return_value=None),patch.object(s,'record_for_row',return_value=None):
   for word in ['tennis grip elbow pain','fractured back recovery time','heart surgery recovery','plantar fasciitis surgery recovery']:
    row={'keyword':word,'evidence_url':'https://example.org/tennis/'+word.replace(' ','-')}
    self.assertEqual(s.classify(row,{'http':200,'title':word,'text':('tennis '+word)*30}),(None,'specialist_review'))
if __name__=='__main__':unittest.main()
