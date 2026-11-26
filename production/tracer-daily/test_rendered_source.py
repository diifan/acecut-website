import unittest,tempfile,json,hashlib,types
from pathlib import Path
from unittest.mock import Mock,patch
import source_cache as s
class RenderedSource(unittest.TestCase):
 def test_http200_shell_is_rendered_then_reused(self):
  u='https://swing.vision/guides/set-up-your-recording'
  response=Mock();response.status_code=200;response.headers={'Content-Type':'text/html'};response.iter_content.return_value=[b'<html><title>SwingVision</title><body></body></html>']
  context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
  session=Mock();session.get.return_value=context
  html='<html><title>Set Up Your Recording</title><body><h1>Set Up Your Recording</h1><p>'+('Tennis recording keeps the whole court visible for match review. '*12)+'</p></body></html>'
  with tempfile.TemporaryDirectory() as d,patch.object(s,'HOME',Path(d)),patch.object(s,'_http',types.SimpleNamespace(session=session)),patch.object(s,'public_url',side_effect=lambda x:x),patch.object(s.subprocess,'run',return_value=types.SimpleNamespace(stdout=json.dumps({'html':html,'url':u}))) as renderer:
   p=Path(d)/'source-cache'/(hashlib.sha256(u.encode()).hexdigest()+'.json');p.parent.mkdir();p.write_text(json.dumps({'http':200,'text':'SwingVision'}))
   _,first=s.fetch(u);self.assertEqual(first['representation'],'rendered_dom');self.assertGreater(len(first['text']),300)
   _,second=s.fetch(u);self.assertEqual(first['body_sha256'],second['body_sha256']);self.assertEqual(renderer.call_count,1)
if __name__=='__main__':unittest.main()
