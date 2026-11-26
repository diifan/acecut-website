import unittest
import editorial_topics as e

SOURCE = ('Tennis camera app: put one phone on a tripod or the fence, anywhere behind the baseline. '
          'This vendor workflow describes a recording setup. ' * 8)
class CameraEditorial(unittest.TestCase):
 def test_specific_source_and_changed_vendor_fact(self):
  self.assertEqual(e.supported('tennis camera',{'http':200,'text':SOURCE}),'tennis_camera')
  self.assertIsNone(e.supported('tennis camera',{'http':200,'text':SOURCE.replace('tripod or the fence','gimbal')}))
  self.assertIsNone(e.supported('tennis camera',{'http':429,'text':SOURCE}))
 def test_recording_and_product_comparison_remain_separate(self):
  for word in ['tennis recording','tennis recording app','best tennis camera','tennis camera app','security camera tennis court']:
   self.assertNotEqual(e.topic(word),'tennis_camera')
  for word in ['tennis camera','tennis cameras','camera for recording tennis']:
   self.assertEqual(e.topic(word),'tennis_camera')
 def test_existing_court_topic_preserved(self):
  self.assertEqual(e.topic('tennis court dimensions'),'court_dimensions')
if __name__=='__main__':unittest.main()
