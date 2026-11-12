import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .depth_book_replay import replay


class BookReplayTests(unittest.TestCase):
    def trace(self):
        return {'schema':'paper-depth-sequence-v1','symbol':'ETHUSDT','snapshot_last_update_id':100,
                'snapshot_bids':[['100','1'],['99','2']],'snapshot_asks':[['101','1'],['102','2']],
                'research_bid_threshold':'99.5',
                'events':[{'e':'depthUpdate','s':'ETHUSDT','U':99,'u':101,'pu':98,'b':[['100','0']],'a':[]},
                          {'e':'depthUpdate','s':'ETHUSDT','U':102,'u':104,'pu':101,'b':[['99.75','3']],'a':[]}]}

    def test_updates_and_threshold(self):
        result=replay(self.trace());self.assertEqual(result['status'],'PARTIAL_BOOK_UNVERIFIED',result)
        self.assertEqual([x['bid'] for x in result['states']],['100','99','99.75'])
        self.assertEqual(result['first_observed_threshold_hit']['event_index'],0)
        self.assertEqual(result['continuous_path'],'UNKNOWN')

    def test_gap_invalid_and_depleted_depth_preserve_prior_hit(self):
        trace=self.trace();trace['events'][1]['pu']=100
        result=replay(trace);self.assertEqual(result['status'],'GAP')
        self.assertEqual(result['first_observed_threshold_hit']['event_index'],0)
        trace=self.trace();trace['events'][1]['b']=[['99','0']]
        result=replay(trace);self.assertEqual(result['status'],'PARTIAL_DEPTH_UNCERTAIN')
        self.assertIsNone(result['states'][-1]['bid'])
        trace=self.trace();trace['events'][1]['b']=[['102','1']]
        result=replay(trace);self.assertEqual(result['status'],'INVALID')
        self.assertEqual(result['first_observed_threshold_hit']['event_index'],0)
        trace=self.trace();trace['events'][1]['a']=[['101','-1']]
        self.assertEqual(replay(trace)['status'],'INVALID')

    def test_snapshot_invalid_and_cli_hash(self):
        trace=self.trace();bad=copy.deepcopy(trace);bad['snapshot_bids'].append(['100','2'])
        self.assertEqual(replay(bad)['status'],'INVALID')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.json';raw=json.dumps(trace).encode();path.write_bytes(raw)
            r=json.loads(subprocess.run([sys.executable,'-m','verify.depth_book_replay','--trace',str(path)],
                                       check=True,capture_output=True,text=True).stdout)
            self.assertEqual(r['status'],'PARTIAL_BOOK_UNVERIFIED')
            self.assertEqual(r['input_sha256'],hashlib.sha256(raw).hexdigest())


if __name__=='__main__':unittest.main()
