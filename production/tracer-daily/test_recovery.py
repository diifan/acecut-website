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
if __name__=='__main__':unittest.main()
