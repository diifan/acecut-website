import unittest
from tennis_records import aligned
class PlayerAliasTests(unittest.TestCase):
 def setUp(self):
  self.player={'kind':'player_record','name':'Marcel Granollers','facts':[{'label':'Birth Date'}]}
 def test_given_initial_with_exact_surname(self):
  for word in ['m granollers tennis','M. Granollers','granollers m','marcel granollers','granollers']:
   self.assertTrue(aligned(word,self.player),word)
 def test_wrong_initial_or_full_name_is_not_identity(self):
  for word in ['g granollers','r granollers','rafael granollers','marcel g','m granollers injury','m granollers live']:
   self.assertFalse(aligned(word,self.player),word)
 def test_alias_does_not_bypass_requested_fact(self):
  self.assertFalse(aligned('m granollers height',self.player))
  self.assertFalse(aligned('m granollers ranking',self.player))
 def test_accents_and_canonical_identity_unchanged(self):
  p={'kind':'player_record','name':'Olga Danilović','canonical_id':'same-entity','facts':[]}
  self.assertTrue(aligned('o danilovic',p));self.assertEqual(p['canonical_id'],'same-entity')
