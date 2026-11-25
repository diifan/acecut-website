import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from source_cache import Text
import executor
class Recovery(unittest.TestCase):
 def test_nested_tables(self):
  p=Text();p.feed('<table><tr><td>outer<table><tr><td>inner</td></tr></table></td></tr><tr><td>Birth Date</td><td>Jan 1, 2000</td></tr></table>')
  self.assertEqual(p.tables[0]['rows'],[['inner']]);self.assertEqual(p.tables[1]['rows'][-1],['Birth Date','Jan 1, 2000'])
 def test_after_cutoff_recovers_today_first(self):
  import datetime
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,25,14,0,tzinfo=tz)
  cfg={'enabled':True,'timezone':'Asia/Shanghai','hour':12,'minute':30,'prepare_hour':13,'prepare_minute':0}
  with patch.object(executor,'config',return_value=cfg),patch.object(executor,'heartbeat'),patch.object(executor,'read',return_value={'state':'insufficient_keywords'}),patch.object(executor,'receipt'),patch.object(executor,'prepare',return_value={'state':'insufficient_keywords'}) as prepare,patch.object(executor,'publish') as publish,patch.object(executor.datetime,'datetime',Clock):
   executor.tick();prepare.assert_called_once_with('2026-11-25');publish.assert_not_called()
 def test_live_read_retries_network_errors(self):
  import urllib.error,io
  from unittest.mock import Mock
  opener=Mock();opener.open.side_effect=[urllib.error.URLError('timeout'),TimeoutError('read timeout'),io.BytesIO(b'verified')]
  with patch.object(executor.time,'sleep'):
   self.assertEqual(executor.live_bytes(opener,'https://example.invalid/page'),b'verified')
  self.assertEqual(opener.open.call_count,3)
 def test_ready_failed_publication_resumes_without_rebuilding(self):
  import datetime
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,25,14,0,tzinfo=tz)
  cfg={'enabled':True,'timezone':'Asia/Shanghai','hour':12,'minute':30,'prepare_hour':13,'prepare_minute':0}
  previous={'state':'failed','ready_for_promotion':True}
  with patch.object(executor,'config',return_value=cfg),patch.object(executor,'heartbeat'),patch.object(executor,'read',return_value=previous),patch.object(executor,'prepare') as prepare,patch.object(executor,'publish') as publish,patch.object(executor.datetime,'datetime',Clock):
   executor.tick();prepare.assert_not_called();publish.assert_called_once_with('2026-11-25')
 def test_source_429_pauses_same_host_without_switching_proxy(self):
  import requests,types,source_cache
  from unittest.mock import Mock
  response=Mock();response.status_code=429;response.headers={'Retry-After':'600'}
  response.raise_for_status.side_effect=requests.HTTPError('rate limited',response=response)
  context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
  session=Mock();session.get.return_value=context
  with tempfile.TemporaryDirectory() as temp,patch.object(source_cache,'HOME',Path(temp)),patch.object(source_cache,'_http',types.SimpleNamespace(session=session)),patch.object(source_cache,'public_url',side_effect=lambda x:x):
   source_cache.fetch('https://example.invalid/one')
   _,second=source_cache.fetch('https://example.invalid/two')
   self.assertEqual(session.get.call_count,1);self.assertIn('cooldown',second['error'])
if __name__=='__main__':unittest.main()
