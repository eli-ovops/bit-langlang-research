import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .funding_reconcile import FIELDS as FUNDING_FIELDS
from .paper_stop_exit import check, deadline_status


class StopExitTests(unittest.TestCase):
    def setUp(self):
        self.base=pd.Timestamp('2026-10-30T00:05:00Z')
        self.cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':self.cfg,'symbol':'ETHUSDT'}
        def event(kind,seconds,**extra):
            t=self.base+pd.Timedelta(seconds=seconds)
            return {**common,'kind':kind,'event_time_utc':t.isoformat(),'captured_at_utc':(t+pd.Timedelta(seconds=1)).isoformat(),
                    'capture_lag_seconds':1,**extra}
        signal_time=(self.base-pd.Timedelta(minutes=5)).isoformat()
        self.signal=event('signal',0,signal_time_utc=signal_time)
        self.entry=event('entry',3,signal_time_utc=signal_time,trade_id='t1',price=100.1*1.0002)
        self.mark=event('mark',11,trade_id='t1',price=99.6)
        self.exit=event('exit',14,trade_id='t1',price=99.5*.9998)
        self.args={'signal':self.signal,'entry':self.entry,'entry_quote':self.quote(2,100,100.1),
                   'mark':self.mark,'trigger_quote':self.quote(10,99.6,99.7),
                   'exit_event':self.exit,'exit_quote':self.quote(13,99.5,99.6),
                   'funding':pd.DataFrame(columns=FUNDING_FIELDS),'start':'2026-10-29',
                   'as_of':self.base+pd.Timedelta(minutes=2)}
        qty=2;entry=self.entry['price'];exit_=self.exit['price']
        self.args['ledger']=pd.DataFrame([{'trade_id':'t1','entry_time':self.entry['event_time_utc'],
            'exit_time':self.exit['event_time_utc'],'symbol':'ETHUSDT','side':'long','entry':entry,'stop':entry*.996,
            'exit':exit_,'qty':qty,'equity_at_entry':2000,'fee_cost':qty*(entry+exit_)*.0005,'funding_cost':0,
            'five_q_pass':'1','stop_placed':'1','added':'0','reversed':'0','plan_deviation':'0',
            'reference_entry':100.1,'reference_exit':99.5,'reference_source':'synthetic','margin_at_entry':qty*entry/5}])

    def quote(self,seconds,bid,ask,bid_qty=5):
        def ms(offset):return int((self.base+pd.Timedelta(seconds=seconds+offset)).timestamp()*1000)
        return {'schema':'paper-quote-research-v1','source':'Binance USD-M public REST','verification':'PUBLIC_UNVERIFIED',
                'config_sha256':self.cfg,'requests':[{'local_start_ms':ms(0),'local_end_ms':ms(.02),'body':{'serverTime':ms(.01)}},
                    {'local_start_ms':ms(.1),'local_end_ms':ms(.2),'body':{'symbol':'ETHUSDT','time':ms(.15),
                     'bidPrice':str(bid),'askPrice':str(ask),'bidQty':str(bid_qty),'askQty':'5'}},
                    {'local_start_ms':ms(.3),'local_end_ms':ms(.32),'body':{'serverTime':ms(.31)}}]}

    def schedule(self,root):
        end=self.base+pd.Timedelta(seconds=90)
        manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                  'start_utc':(self.base-pd.Timedelta(minutes=2)).isoformat(),'end_utc_exclusive':end.isoformat(),
                  'captured_at_utc':(end+pd.Timedelta(seconds=1)).isoformat(),
                  'query_server_time_ms':int(end.timestamp()*1000),'server_time_ms':int((end+pd.Timedelta(seconds=1)).timestamp()*1000),'symbols':{}}
        for symbol in ('BTCUSDT','ETHUSDT'):
            raw=b'[]';(root/(symbol+'.json')).write_bytes(raw)
            manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(raw).hexdigest(),'count':0}
        (root/'manifest.json').write_text(json.dumps(manifest))

    def test_stop_costs_r_and_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            self.schedule(Path(directory));result=check(**self.args,schedule=directory)
            self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED',result)
            self.assertEqual(result['exit_kind'],'bid_stop')
            self.assertAlmostEqual(result['stop_check']['net_R'],result['report']['records'][0]['net_R'],places=6)
            self.assertAlmostEqual(result['costs_vs_mid_unverified']['sampled_spread_cost_usdt'],.2,places=6)
            self.assertAlmostEqual(result['costs_vs_mid_unverified']['net_pnl_reconciled_usdt'],result['report']['net_pnl_usdt'],places=6)
            self.assertEqual(check(**self.args)['status'],'UNKNOWN_FUNDING')
            bad=copy.deepcopy(self.args);bad['ledger'].loc[0,'fee_cost']=0
            self.assertEqual(check(**bad,schedule=directory)['status'],'INVALID')
            bad=copy.deepcopy(self.args);bad['mark']['price']=99.7
            self.assertEqual(check(**bad,schedule=directory)['status'],'INVALID')
            shallow=copy.deepcopy(self.args);shallow['exit_quote']['requests'][1]['body']['bidQty']='1'
            self.assertEqual(check(**shallow,schedule=directory)['status'],'UNKNOWN_DEPTH')
            missing=copy.deepcopy(self.args);missing['ledger']=missing['ledger'].drop(columns='margin_at_entry')
            self.assertEqual(check(**missing,schedule=directory)['status'],'UNKNOWN_MARGIN')
            later=copy.deepcopy(self.args);later['ledger'].loc[0,'equity_at_entry']=1900
            single=check(**later,schedule=directory)
            self.assertEqual(single['status'],'PARTIAL_NOT_REGISTERED',single)
            self.assertEqual(single['entry_equity_context'],'UNKNOWN_REQUIRES_FULL_LEDGER')
            self.assertEqual(single['funding_check']['risk_equity_context'],'UNKNOWN_INCOMPLETE_LEDGER')

    def test_cli_synthetic_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schedule=root/'schedule';schedule.mkdir();self.schedule(schedule)
            names={'signal':'signal','entry':'entry','entry-quote':'entry_quote','mark':'mark',
                   'trigger-quote':'trigger_quote','exit':'exit_event','exit-quote':'exit_quote'}
            cmd=[sys.executable,'-m','verify.paper_stop_exit']
            for flag,key in names.items():
                path=root/(flag+'.json');path.write_text(json.dumps(self.args[key]));cmd.extend(['--'+flag,str(path)])
            self.args['ledger'].to_csv(root/'ledger.csv',index=False);self.args['funding'].to_csv(root/'funding.csv',index=False)
            cmd.extend(['--ledger',str(root/'ledger.csv'),'--funding',str(root/'funding.csv'),'--schedule',str(schedule),
                        '--start',self.args['start'],'--as-of',self.args['as_of'].isoformat()])
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
        self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED',result)
        self.assertEqual(len(result['input_sha256']),9)

    def test_stop_deadline_order_is_not_guessed(self):
        entry=self.base;deadline=entry+pd.Timedelta(days=30)
        self.assertEqual(deadline_status(entry,deadline-pd.Timedelta(seconds=2),deadline-pd.Timedelta(seconds=1)),'BEFORE_DEADLINE')
        self.assertEqual(deadline_status(entry,deadline-pd.Timedelta(seconds=1),deadline),'AMBIGUOUS_ORDER')
        self.assertEqual(deadline_status(entry,deadline,deadline+pd.Timedelta(seconds=1)),'AMBIGUOUS_ORDER')
        self.assertEqual(deadline_status(entry,deadline+pd.Timedelta(seconds=1),deadline+pd.Timedelta(seconds=2)),'EXECUTION_MODEL_MISMATCH')


if __name__=='__main__':unittest.main()
