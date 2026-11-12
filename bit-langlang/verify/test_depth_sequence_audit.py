import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .depth_sequence_audit import audit


class DepthSequenceTests(unittest.TestCase):
    def event(self,U,u,pu,**extra):return {'e':'depthUpdate','s':'ETHUSDT','U':U,'u':u,'pu':pu,**extra}
    def trace(self,events):return {'schema':'paper-depth-sequence-v1','symbol':'ETHUSDT','snapshot_last_update_id':100,'events':events}

    def test_bridge_discard_and_chain(self):
        t=self.trace([self.event(90,99,89),self.event(99,101,95),self.event(102,105,101,st=1)])
        r=audit(t);self.assertEqual(r['status'],'PARTIAL_CHAIN_UNVERIFIED');self.assertEqual((r['discarded'],r['valid_prefix'],r['last_u']),(1,2,105))
        self.assertEqual(audit(self.trace([]))['status'],'UNKNOWN_NO_BRIDGE')
        self.assertEqual(audit(self.trace([self.event(1,99,0)]))['status'],'UNKNOWN_NO_BRIDGE')

    def test_gap_and_invalid_data(self):
        self.assertEqual(audit(self.trace([self.event(101,102,99)]))['status'],'GAP')
        a=self.event(99,101,98)
        self.assertEqual(audit(self.trace([a,self.event(102,105,100)]))['status'],'GAP')
        self.assertEqual(audit(self.trace([a,self.event(101,101,101)]))['status'],'GAP')
        for bad in (self.event(True,101,98),self.event(102,101,98),self.event(99,101,98,s='BTCUSDT'),self.event(99,101,98,st=2)):
            self.assertEqual(audit(self.trace([bad]))['status'],'INVALID')

    def test_cli_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'trace.json';p.write_text('{"schema":"x","schema":"y"}')
            r=json.loads(subprocess.run([sys.executable,'-m','verify.depth_sequence_audit','--trace',str(p)],
                                        check=True,capture_output=True,text=True).stdout)
            self.assertEqual(r['status'],'INVALID')


if __name__=='__main__':unittest.main()
