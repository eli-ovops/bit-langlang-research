"""Synthetic evidence for linking observed stop hits to batch exits."""
import copy
import hashlib
import json
import unittest

import pandas as pd

from . import test_paper_position_quotes as fixtures
from .paper_exit_batch import position_paths


class ExitPositionPaths(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PositionQuoteTests();self.f.setUp()
        end=self.f.base+pd.Timedelta(seconds=80)
        common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':self.f.cfg,
                'symbol':'ETHUSDT','trade_id':'q1'}
        self.exit={**common,'kind':'exit','event_time_utc':end.isoformat(),
                   'captured_at_utc':(end+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1,'price':99.4}
        self.closed=self.f.ledger.copy();self.closed['exit_time']=self.exit['event_time_utc'];self.closed['exit']=99.4
        raw=self.f.entry_quote
        self.records={'q1':{'quote':json.loads(raw),'sha256':hashlib.sha256(raw).hexdigest()}}
        self.bundles={'q1':{'kind':'ema20','signal':self.f.signal,'entry':self.f.entry,'exit':self.exit}}
        self.ev={'entry_quote_raw':raw,'entry_receipt_raw':self.f.entry_receipt,
                 'samples':self.f.items([(10,100,100.1),(50,100.2,100.3)])}

    def check(self,evidence):
        return position_paths(self.closed,self.records,self.bundles,evidence,self.f.now)

    def test_timed_exit_earlier_stop_and_missing_evidence(self):
        self.assertEqual(self.check(None)['status'],'UNKNOWN_NOT_PROVIDED')
        self.assertEqual(self.check({})['status'],'UNKNOWN_INCOMPLETE')
        self.assertEqual(self.check({'q1':self.ev})['status'],'PARTIAL_DISCRETE_UNVERIFIED')
        hit=copy.deepcopy(self.ev);hit['samples']=self.f.items([(10,99.6,99.7),(50,100,100.1)])
        result=self.check({'q1':hit})
        self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH',result)
        self.assertIsNotNone(result['trades']['q1']['first_observed_stop_hit'])

    def test_stop_exit_requires_first_observed_hit(self):
        samples=self.f.items([(10,99.6,99.7),(50,99.5,99.6)])
        t=self.f.base+pd.Timedelta(seconds=11)
        mark={**self.exit,'kind':'mark','event_time_utc':t.isoformat(),
              'captured_at_utc':(t+pd.Timedelta(seconds=1)).isoformat(),'price':99.6}
        self.bundles['q1'].update(kind='bid_stop',mark=mark,trigger_quote=json.loads(samples[0]['quote_raw']))
        ev={**self.ev,'samples':samples,'trigger_quote_raw':samples[0]['quote_raw']}
        self.assertEqual(self.check({'q1':ev})['status'],'PARTIAL_DISCRETE_UNVERIFIED')
        t=self.f.base+pd.Timedelta(seconds=51)
        self.bundles['q1']['mark']={**mark,'event_time_utc':t.isoformat(),
                                   'captured_at_utc':(t+pd.Timedelta(seconds=1)).isoformat(),'price':99.5}
        self.bundles['q1']['trigger_quote']=json.loads(samples[1]['quote_raw'])
        ev['trigger_quote_raw']=samples[1]['quote_raw']
        self.assertEqual(self.check({'q1':ev})['status'],'EXECUTION_MODEL_MISMATCH')

    def test_altered_entry_and_receipt_rejected(self):
        wrong={**self.ev,'entry_quote_raw':self.ev['entry_quote_raw']+b' '}
        self.assertEqual(self.check({'q1':wrong})['status'],'INVALID')
        bad=copy.deepcopy(self.ev);receipt=json.loads(bad['samples'][0]['receipt_raw']);receipt['quote_sha256']='wrong'
        bad['samples'][0]['receipt_raw']=json.dumps(receipt).encode()
        self.assertEqual(self.check({'q1':bad})['status'],'INVALID')
        bad=copy.deepcopy(self.ev);bad['samples']=self.f.items([(10,99.6,99.7),(50,100,100.1)])
        receipt=json.loads(bad['samples'][1]['receipt_raw']);receipt['quote_sha256']='wrong'
        bad['samples'][1]['receipt_raw']=json.dumps(receipt).encode()
        result=self.check({'q1':bad})
        self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH')
        self.assertEqual(result['trades']['q1']['status'],'INVALID')
        self.assertTrue(result['trades']['q1']['observed_stop_alert'])

    def test_one_invalid_trade_does_not_hide_other_trade_stop(self):
        second=self.closed.copy();second['trade_id']='q2'
        closed=pd.concat([self.closed,second],ignore_index=True)
        records={**self.records,'q2':self.records['q1']}
        bundle=copy.deepcopy(self.bundles['q1'])
        bundle['entry']['trade_id']='q2';bundle['exit']['trade_id']='q2'
        bundles={**self.bundles,'q2':bundle}
        hit=copy.deepcopy(self.ev);hit['samples']=self.f.items([(10,99.6,99.7),(50,100,100.1)])
        invalid={**self.ev,'entry_quote_raw':self.ev['entry_quote_raw']+b' '}
        for frame in (closed,closed.iloc[::-1]):
            result=position_paths(frame,records,bundles,{'q1':hit,'q2':invalid},self.f.now)
            self.assertEqual(result['status'],'EXECUTION_MODEL_MISMATCH',result)
            self.assertIsNotNone(result['trades']['q1']['first_observed_stop_hit'])
            self.assertEqual(result['trades']['q2']['status'],'INVALID')


if __name__=='__main__':unittest.main()
