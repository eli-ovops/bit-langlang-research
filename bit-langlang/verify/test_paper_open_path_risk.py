import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from . import test_paper_position_quotes as fixtures
from .forward_report import REQUIRED
from .paper_open_path_risk import evaluate


class OpenPathRiskTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PositionQuoteTests();self.f.setUp()
        self.closed=pd.DataFrame(columns=REQUIRED)
        self.opened=self.f.ledger.copy()
        self.opened['equity_at_entry']=2000;self.opened['mark_price']=100.2
        self.opened['mark_time']=(self.f.now-pd.Timedelta(seconds=1)).isoformat()
        self.opened['mark_source']='synthetic';self.opened['entry_fee']=.1;self.opened['funding_cost']=0
        self.ev={'signal':self.f.signal,'entry':self.f.entry,'entry_quote_raw':self.f.entry_quote,
                 'entry_receipt_raw':self.f.entry_receipt,'samples':self.f.items([(10,100,100.1),(50,100.2,100.3)])}

    def check(self,evidence):return evaluate(self.closed,self.opened,'2026-10-30',self.f.now,evidence)

    def test_stop_hit_overrides_safe_mark_and_bad_later_evidence(self):
        self.assertEqual(self.check(None)['status'],'UNKNOWN_OBSERVATION')
        good=self.check({'q1':self.ev});self.assertEqual(good['status'],'REVIEW',good)
        hit=copy.deepcopy(self.ev);hit['samples']=self.f.items([(10,99.6,99.7),(80,100,100.1)])
        result=self.check({'q1':hit});self.assertEqual(result['status'],'STOP',result)
        self.assertTrue(result['observations']['q1']['coverage_gap'])
        receipt=json.loads(hit['samples'][1]['receipt_raw']);receipt['quote_sha256']='wrong'
        hit['samples'][1]['receipt_raw']=json.dumps(receipt).encode()
        result=self.check({'q1':hit});self.assertEqual(result['status'],'STOP',result)
        self.assertTrue(result['invalid_observation_present'])
        self.assertTrue(result['observations']['q1']['observed_stop_alert'])

    def test_gap_invalid_binding_and_known_risk(self):
        gap=copy.deepcopy(self.ev);gap['samples']=self.f.items([(80,100,100.1)])
        self.assertEqual(self.check({'q1':gap})['status'],'UNKNOWN_OBSERVATION')
        bad=copy.deepcopy(self.ev);bad['entry']['trade_id']='other'
        self.assertEqual(self.check({'q1':bad})['status'],'INVALID')
        self.opened['qty']=100
        self.assertEqual(self.check(None)['status'],'STOP')

    def test_cli_missing_file_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.closed.to_csv(p/'closed.csv',index=False);self.opened.to_csv(p/'open.csv',index=False)
            for name,value in [('signal',self.ev['signal']),('entry',self.ev['entry'])]:
                (p/(name+'.json')).write_text(json.dumps(value))
            (p/'quote.json').write_bytes(self.ev['entry_quote_raw']);(p/'receipt.json').write_bytes(self.ev['entry_receipt_raw'])
            items=[]
            for i,sample in enumerate(self.ev['samples']):
                (p/f'q{i}.json').write_bytes(sample['quote_raw']);(p/f'r{i}.json').write_bytes(sample['receipt_raw'])
                items.append({'quote':f'q{i}.json','receipt':f'r{i}.json'})
            manifest={'schema':'paper-open-risk-paths-v1','positions':{'q1':{'signal':'signal.json','entry':'entry.json',
                      'entry_quote':'quote.json','entry_receipt':'receipt.json','samples':items}}}
            (p/'manifest.json').write_text(json.dumps(manifest))
            cmd=[sys.executable,'-m','verify.paper_open_path_risk','--closed',str(p/'closed.csv'),'--open',str(p/'open.csv'),
                 '--start','2026-10-30','--as-of',self.f.now.isoformat(),'--manifest',str(p/'manifest.json')]
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(result['status'],'REVIEW',result)
            self.assertEqual(result['input_sha256']['evidence']['quote.json'],hashlib.sha256(self.ev['entry_quote_raw']).hexdigest())
            manifest['positions']['q1']['samples'][0]['quote']='missing.json'
            (p/'manifest.json').write_text(json.dumps(manifest))
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(result['status'],'INVALID',result)


if __name__=='__main__':unittest.main()
