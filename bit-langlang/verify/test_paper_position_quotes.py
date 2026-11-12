import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

import pandas as pd

from .paper_position_quotes import audit, receipt_check
from .paper_quote import main as quote_main, quote_facts
from .paper_quote_receipt import capture as capture_receipt


class PositionQuoteTests(unittest.TestCase):
    def setUp(self):
        self.base=pd.Timestamp('2026-10-30T00:05:00Z')
        self.cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':self.cfg,'symbol':'ETHUSDT'}
        def event(kind,seconds,**extra):
            t=self.base+pd.Timedelta(seconds=seconds)
            return {**common,'kind':kind,'event_time_utc':t.isoformat(),
                    'captured_at_utc':(t+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1,**extra}
        self.signal=event('signal',0,signal_time_utc=(self.base-pd.Timedelta(minutes=5)).isoformat())
        self.entry=event('entry',3,signal_time_utc=self.signal['signal_time_utc'],trade_id='q1',price=100.1*1.0002)
        self.entry_quote,self.entry_receipt=self.sample(2,100,100.1)
        self.ledger=pd.DataFrame([{'trade_id':'q1','symbol':'ETHUSDT','side':'long','entry_time':self.entry['event_time_utc'],
                                  'entry':self.entry['price'],'stop':self.entry['price']*.996,'qty':2}])
        self.now=self.base+pd.Timedelta(seconds=90)

    def sample(self,seconds,bid,ask,base=None):
        start=(base or self.base)+pd.Timedelta(seconds=seconds)
        def ms(x):return int((start+pd.Timedelta(seconds=x)).timestamp()*1000)
        quote={'schema':'paper-quote-research-v1','source':'Binance USD-M public REST','verification':'PUBLIC_UNVERIFIED',
               'config_sha256':self.cfg,'requests':[{'local_start_ms':ms(0),'local_end_ms':ms(.02),'body':{'serverTime':ms(.01)}},
                    {'local_start_ms':ms(.1),'local_end_ms':ms(.2),'body':{'symbol':'ETHUSDT','time':ms(.15),'bidPrice':str(bid),
                     'askPrice':str(ask),'bidQty':'5','askQty':'5'}},
                    {'local_start_ms':ms(.3),'local_end_ms':ms(.32),'body':{'serverTime':ms(.31)}}]}
        raw=json.dumps(quote).encode();receipt={'schema':'paper-quote-receipt-v1','verification':'LOCAL_CLOCK_UNVERIFIED',
              'captured_at_utc':(start+pd.Timedelta(seconds=.5)).isoformat(),'quote_sha256':hashlib.sha256(raw).hexdigest(),
              'config_sha256':self.cfg}
        return raw,json.dumps(receipt).encode()

    def items(self,specs):
        return [{'quote_raw':raw,'receipt_raw':receipt} for raw,receipt in (self.sample(*spec) for spec in specs)]

    def check(self,samples,**kwargs):
        return audit(self.signal,self.entry,self.entry_quote,self.entry_receipt,self.ledger,samples,self.now,**kwargs)

    def test_discrete_good_gap_and_observed_open_stop(self):
        samples=self.items([(10,100,100.1),(50,100.2,100.3)])
        result=self.check(samples)
        self.assertEqual(result['status'],'PARTIAL_DISCRETE_UNVERIFIED',result)
        self.assertEqual(result['sample_count'],2)
        self.assertEqual(result['continuous_price_path'],'UNKNOWN')
        gap=self.items([(10,100,100.1),(80,100.2,100.3)])
        self.assertEqual(self.check(gap)['status'],'COVERAGE_GAP')
        hit=self.items([(10,99.6,99.7),(80,100.2,100.3)])
        alert=self.check(hit)
        self.assertEqual(alert['status'],'ALERT_OBSERVED_STOP')
        self.assertTrue(alert['coverage_gap'])
        self.assertEqual(self.check([])['status'],'UNKNOWN_NO_SAMPLES')

    def test_closed_stop_must_match_first_observed_hit(self):
        samples=self.items([(10,99.6,99.7),(50,99.5,99.6)])
        exit_time=self.base+pd.Timedelta(seconds=80)
        exit_event={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':self.cfg,'symbol':'ETHUSDT',
                    'kind':'exit','trade_id':'q1','event_time_utc':exit_time.isoformat(),
                    'captured_at_utc':(exit_time+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1,'price':99.4}
        self.ledger['exit_time']=exit_event['event_time_utc'];self.ledger['exit']=exit_event['price']
        mark_time=self.base+pd.Timedelta(seconds=11)
        mark={**exit_event,'kind':'mark','event_time_utc':mark_time.isoformat(),
              'captured_at_utc':(mark_time+pd.Timedelta(seconds=1)).isoformat(),'price':99.6}
        good=self.check(samples,exit_event=exit_event,mark=mark,trigger_quote_raw=samples[0]['quote_raw'])
        self.assertEqual(good['status'],'PARTIAL_DISCRETE_UNVERIFIED',good)
        self.assertEqual(self.check(samples,exit_event=exit_event)['status'],'UNKNOWN_TRIGGER_SAMPLE')
        mark2={**mark,'event_time_utc':(self.base+pd.Timedelta(seconds=51)).isoformat(),
               'captured_at_utc':(self.base+pd.Timedelta(seconds=52)).isoformat(),'price':99.5}
        self.assertEqual(self.check(samples,exit_event=exit_event,mark=mark2,trigger_quote_raw=samples[1]['quote_raw'])['status'],'MISSED_OBSERVED_STOP')
        wrong={**mark,'trade_id':'other'}
        self.assertEqual(self.check(samples,exit_event=exit_event,mark=wrong,trigger_quote_raw=samples[0]['quote_raw'])['status'],'INVALID')

    def test_late_entry_record_counts_as_unobserved_gap(self):
        entry={**self.entry,'captured_at_utc':(self.base+pd.Timedelta(seconds=74)).isoformat(),
               'capture_lag_seconds':71}
        samples=self.items([(80,100,100.1),(120,100.2,100.3)])
        end=self.base+pd.Timedelta(seconds=150)
        result=audit(self.signal,entry,self.entry_quote,self.entry_receipt,self.ledger,samples,end)
        self.assertEqual(result['status'],'COVERAGE_GAP',result)
        self.assertEqual(result['entry_capture_lag_seconds'],71)
        self.assertEqual(result['max_gap_seconds'],77.5)
        samples=self.items([(80,99.6,99.7),(120,100.2,100.3)])
        result=audit(self.signal,entry,self.entry_quote,self.entry_receipt,self.ledger,samples,end)
        self.assertEqual(result['status'],'ALERT_OBSERVED_STOP',result)
        self.assertTrue(result['coverage_gap'])
        entry={**self.entry,'captured_at_utc':(self.base+pd.Timedelta(seconds=43)).isoformat(),
               'capture_lag_seconds':40}
        samples=self.items([(70,100,100.1),(110,100.2,100.3)])
        result=audit(self.signal,entry,self.entry_quote,self.entry_receipt,self.ledger,samples,end)
        self.assertEqual(result['status'],'COVERAGE_GAP',result)
        self.assertEqual(result['max_gap_seconds'],67.5)

    def test_corruption_order_stale_receipt_and_entry_receipt(self):
        samples=self.items([(10,100,100.1),(50,100.2,100.3)])
        bad=copy.deepcopy(samples);rec=json.loads(bad[0]['receipt_raw']);rec['quote_sha256']='wrong';bad[0]['receipt_raw']=json.dumps(rec).encode()
        self.assertEqual(self.check(bad)['status'],'INVALID')
        self.assertEqual(self.check(list(reversed(samples)))['status'],'INVALID')
        bad=copy.deepcopy(samples);rec=json.loads(bad[0]['receipt_raw']);rec['captured_at_utc']=(self.base+pd.Timedelta(seconds=13)).isoformat();bad[0]['receipt_raw']=json.dumps(rec).encode()
        self.assertEqual(self.check(bad)['status'],'INVALID')
        self.assertEqual(self.check([samples[0],samples[0]])['status'],'INVALID')
        rec=json.loads(self.entry_receipt);rec['captured_at_utc']=(self.base+pd.Timedelta(seconds=3)).isoformat()
        self.assertEqual(audit(self.signal,self.entry,self.entry_quote,json.dumps(rec).encode(),self.ledger,samples,self.now)['status'],'INVALID')
        bad_quote=json.loads(samples[0]['quote_raw']);bad_quote['requests'][0]['local_start_ms']+=.5
        with self.assertRaises(ValueError):quote_facts(bad_quote)

    def test_valid_stop_hit_before_corruption_remains_visible(self):
        samples=self.items([(10,99.6,99.7),(50,100,100.1)])
        receipt=json.loads(samples[1]['receipt_raw']);receipt['quote_sha256']='wrong'
        samples[1]['receipt_raw']=json.dumps(receipt).encode()
        result=self.check(samples)
        self.assertEqual(result['status'],'INVALID')
        self.assertTrue(result['observed_stop_alert'])
        self.assertEqual(result['first_observed_stop_hit']['bid'],99.6)
        self.assertEqual(result['observation_completeness'],'UNKNOWN')

    def test_missing_samples_and_thirty_day_deadline(self):
        future=pd.Timestamp(self.entry['event_time_utc'])+pd.Timedelta(days=30,seconds=1)
        result=audit(self.signal,self.entry,self.entry_quote,self.entry_receipt,self.ledger,[],future,clock_for_test=future)
        self.assertEqual(result['status'],'ALERT_OVERDUE')
        self.assertTrue(result['synthetic_clock_used'])
        self.assertEqual(audit(self.signal,self.entry,self.entry_quote,self.entry_receipt,self.ledger,[],future)['status'],'INVALID')

    def test_cli_and_non_overwriting_receipt(self):
        samples=self.items([(10,100,100.1),(50,100.2,100.3)])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in (('signal',self.signal),('entry',self.entry)):(root/(name+'.json')).write_text(json.dumps(value))
            (root/'entry-quote.json').write_bytes(self.entry_quote);(root/'entry-receipt.json').write_bytes(self.entry_receipt)
            self.ledger.to_csv(root/'ledger.csv',index=False)
            entries=[]
            for index,item in enumerate(samples):
                q=f'q{index}.json';r=f'r{index}.json'
                (root/q).write_bytes(item['quote_raw']);(root/r).write_bytes(item['receipt_raw']);entries.append({'quote':q,'receipt':r})
            manifest={'schema':'paper-position-quotes-v1','samples':entries};(root/'samples.json').write_text(json.dumps(manifest))
            cmd=[sys.executable,'-m','verify.paper_position_quotes','--signal',str(root/'signal.json'),
                 '--entry',str(root/'entry.json'),'--entry-quote',str(root/'entry-quote.json'),
                 '--entry-receipt',str(root/'entry-receipt.json'),'--ledger',str(root/'ledger.csv'),
                 '--samples',str(root/'samples.json'),'--as-of',self.now.isoformat()]
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(result['status'],'PARTIAL_DISCRETE_UNVERIFIED',result)
            fresh=pd.Timestamp.now(tz='UTC')-pd.Timedelta(seconds=.7)
            quote,_=self.sample(0,100,100.1,base=fresh);(root/'fresh.json').write_bytes(quote)
            output=root/'fresh-receipt.json';saved=capture_receipt(root/'fresh.json',output)
            self.assertEqual(saved['status'],'RECEIPT_UNVERIFIED')
            with self.assertRaises(FileExistsError):capture_receipt(root/'fresh.json',output)

    def test_one_shot_capture_pairs_receipt_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def fresh_quote():
                t=pd.Timestamp.now(tz='UTC')-pd.Timedelta(seconds=.7)
                return json.loads(self.sample(0,100,100.1,base=t)[0])
            args=['paper_quote','capture-with-receipt','--out',str(root/'quote.json'),
                  '--receipt-out',str(root/'receipt.json')]
            output=io.StringIO()
            with patch('sys.argv',args),patch('verify.paper_quote.fetch_quote',return_value=fresh_quote()),redirect_stdout(output):
                quote_main()
            self.assertEqual(json.loads(output.getvalue())['status'],'SAMPLE_AND_RECEIPT_UNVERIFIED')
            self.assertTrue((root/'quote.json').exists());self.assertTrue((root/'receipt.json').exists())
            args=['paper_quote','capture-with-receipt','--out',str(root/'failed-quote.json'),
                  '--receipt-out',str(root/'failed-receipt.json')]
            output=io.StringIO()
            with patch('sys.argv',args),patch('verify.paper_quote.fetch_quote',return_value=fresh_quote()), \
                 patch('verify.paper_quote_receipt.capture',side_effect=OSError('synthetic disk failure')),redirect_stdout(output):
                quote_main()
            self.assertEqual(json.loads(output.getvalue())['status'],'QUOTE_SAVED_RECEIPT_MISSING')
            self.assertTrue((root/'failed-quote.json').exists());self.assertFalse((root/'failed-receipt.json').exists())
            rejected=fresh_quote();rejected['requests'][1]['body']['time']=rejected['requests'][0]['body']['serverTime']-1
            args=['paper_quote','capture-with-receipt','--out',str(root/'rejected-quote.json'),
                  '--receipt-out',str(root/'rejection.json')]
            output=io.StringIO()
            with patch('sys.argv',args),patch('verify.paper_quote.fetch_quote',return_value=rejected),redirect_stdout(output):
                quote_main()
            self.assertEqual(json.loads(output.getvalue())['status'],'QUOTE_SAVED_REJECTED')
            rejection=json.loads((root/'rejection.json').read_text())
            self.assertEqual(rejection['schema'],'paper-quote-rejection-v1')
            with self.assertRaises(ValueError):receipt_check((root/'rejected-quote.json').read_bytes(),(root/'rejection.json').read_bytes())


if __name__=='__main__':unittest.main()
