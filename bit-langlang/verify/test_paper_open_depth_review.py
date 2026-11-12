import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from . import test_depth_sessions_audit as sessions
from . import test_paper_open_path_risk as fixtures
from .paper_open_depth_review import evaluate


class OpenDepthReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenPathRiskTests();self.f.setUp()
        self.helper=sessions.DepthSessionsTests()

    def check(self,paths,now=None):
        return evaluate(self.f.closed,self.f.opened,'2026-10-30',str(now or self.f.f.now),paths)

    def test_observed_stop_and_gap_and_corrupt_other_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=self.helper.session(root/'a','2026-10-30T00:05:10Z','2026-10-30T00:05:11Z')
            b=self.helper.session(root/'b','2026-10-30T00:05:20Z','2026-10-30T00:05:21Z',bid_after=99.6)
            result=self.check([a]);self.assertEqual(result['status'],'PARTIAL_DISCRETE_UNKNOWN_PATH',result)
            result=self.check([a,b]);self.assertEqual(result['status'],'STOP',result)
            self.assertEqual(result['observed_threshold_hits'][0]['trade_id'],'q1')
            self.assertEqual(result['gaps'][0]['coverage'],'UNKNOWN_UNOBSERVED')
            (a/'snapshot-response.json').write_text('{}')
            result=self.check([a,b]);self.assertEqual(result['status'],'STOP',result)
            self.assertTrue(result['errors'])

    def test_before_entry_future_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=self.helper.session(root/'old','2026-10-30T00:04:50Z','2026-10-30T00:04:51Z',bid_after=99.6)
            self.assertEqual(self.check([old])['status'],'UNKNOWN')
            future=self.helper.session(root/'future','2026-10-30T00:06:29Z','2026-10-30T00:06:31Z')
            self.assertEqual(self.check([future])['status'],'INVALID')
            hit=self.helper.session(root/'hit','2026-10-30T00:05:10Z','2026-10-30T00:05:11Z',bid_after=99.6)
            self.f.closed.to_csv(root/'closed.csv',index=False);self.f.opened.to_csv(root/'open.csv',index=False)
            cmd=[sys.executable,'-m','verify.paper_open_depth_review','--closed',str(root/'closed.csv'),
                 '--open',str(root/'open.csv'),'--start','2026-10-30','--as-of',self.f.f.now.isoformat(),'--sessions',str(hit)]
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(result['status'],'STOP',result)
            self.assertEqual(result['continuous_price_path'],'UNKNOWN')

    def test_buffered_event_not_available_before_snapshot_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session=self.helper.session(root/'a','2026-10-30T00:05:10Z','2026-10-30T00:05:11Z')
            self.f.opened['entry']=100.5;self.f.opened['stop']=100.5*.996
            result=self.check([session]);self.assertEqual(result['status'],'STOP',result)
            hit=result['observed_threshold_hits'][0]
            self.assertEqual(hit['received_at_utc'],'2026-10-30T00:05:10+00:00')
            self.assertEqual(hit['book_state_not_before_utc'],'2026-10-30T00:05:11+00:00')
            self.assertEqual(hit['durably_persisted_at_utc'],'UNKNOWN')


if __name__=='__main__':unittest.main()
