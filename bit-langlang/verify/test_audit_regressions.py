import unittest
import copy
import hashlib
import json
import tempfile
import subprocess
import importlib.util
from pathlib import Path

import pandas as pd

from verify.final_validation import select, sim
from verify.forward_report import report
from verify.forward_scan import stop_for_entry, closed_snapshot, signal_records
from verify.tph_frozen_audit import signals
from verify.tph_ledger import replay
from verify.forward_open import evaluate
from verify.paper_event import capture
from verify.paper_reconcile import reconcile
from verify.signal_reconcile import reconcile as reconcile_signals
from verify.btc_h1_historical import btc_eligible_signals
from verify.eth_h2_historical import recapture_signals
from verify.ema_warmup_diagnostic import compare_daily
from verify.ema_candidate_impact import impact
from verify.execution_delay_diagnostic import delay_one_bar, candidates_with_entry_in_window
from verify.paper_risk_audit import audit as audit_combined_risk
from verify.paper_equity import evaluate as evaluate_paper_equity
from verify.forward_open import FIELDS as OPEN_FIELDS
from verify.forward_report import REQUIRED as CLOSED_FIELDS
from verify.funding_mark_diagnostic import funding_for_trade
from verify.funding_reconcile import reconcile as reconcile_funding, FIELDS as FUNDING_FIELDS
from verify.eth_h3_historical import sweep_reclaim
from verify.paper_positions_reconcile import reconcile as reconcile_positions
from verify.paper_quote import assess as assess_quote, assess_round_trip
from verify.paper_delayed_signal_reconcile import reconcile as reconcile_delayed_signal
from verify.structural_stop_research import structural_levels


class AuditRegressions(unittest.TestCase):
    def test_quote_stop_round_trip_reconciles_net_r_and_costs(self):
        base=pd.Timestamp('2026-10-30T00:05:00Z'); ms=lambda t:int((base+pd.Timedelta(seconds=t)).timestamp()*1000)
        cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        def quote(t,bid,ask,bidqty=3):
            return {'schema':'paper-quote-research-v1','source':'Binance USD-M public REST','verification':'PUBLIC_UNVERIFIED','config_sha256':cfg,
                    'requests':[{'local_start_ms':ms(t),'local_end_ms':ms(t+.02),'body':{'serverTime':ms(t+.01)}},
                                {'local_start_ms':ms(t+.1),'local_end_ms':ms(t+.2),'body':{'symbol':'ETHUSDT','time':ms(t+.15),
                                 'bidPrice':str(bid),'askPrice':str(ask),'bidQty':str(bidqty),'askQty':'3'}},
                                {'local_start_ms':ms(t+.3),'local_end_ms':ms(t+.32),'body':{'serverTime':ms(t+.31)}}]}
        common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,'symbol':'ETHUSDT'}
        def event(kind,second,**extra):
            return {**common,'kind':kind,'event_time_utc':(base+pd.Timedelta(seconds=second)).isoformat(),
                    'captured_at_utc':(base+pd.Timedelta(seconds=second+1)).isoformat(),'capture_lag_seconds':1,**extra}
        sigtime=(base-pd.Timedelta(minutes=5)).isoformat()
        signal=event('signal',0,signal_time_utc=sigtime)
        entry=event('entry',3,signal_time_utc=sigtime,trade_id='q1',price=100.1*1.0002)
        mark=event('mark',11,trade_id='q1',price=99.6)
        exit_event=event('exit',14,trade_id='q1',price=99.5*.9998)
        q1,q2,q3=quote(2,100,100.1),quote(10,99.6,99.7),quote(13,99.5,99.6)
        args=[signal,entry,q1,mark,q2,exit_event,q3,2,.2,base+pd.Timedelta(seconds=16)]
        result=assess_round_trip(*args)
        self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED')
        self.assertEqual(result['funding_verification'],'UNKNOWN')
        closed=dict(trade_id='q1',entry_time=entry['event_time_utc'],exit_time=exit_event['event_time_utc'],
                    symbol='ETHUSDT',side='long',entry=entry['price'],stop=entry['price']*.996,exit=exit_event['price'],qty=2,
                    equity_at_entry=2000,fee_cost=2*(entry['price']+exit_event['price'])*.0005,funding_cost=.2,
                    five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')
        accounting=report(pd.DataFrame([closed]),'2026-10-30',base+pd.Timedelta(seconds=16))
        self.assertEqual(result['net_pnl_usdt'],accounting['net_pnl_usdt'])
        self.assertEqual(result['net_R'],accounting['records'][0]['net_R'])
        with tempfile.TemporaryDirectory() as folder:
            names=('signal','entry','entry-quote','mark','trigger-quote','exit','exit-quote')
            for name,value in zip(names,args[:7]): Path(folder,name).write_text(json.dumps(value))
            command=['python3','-m','verify.paper_quote','check-round-trip']
            for name in names: command.extend(['--'+name,str(Path(folder,name))])
            command.extend(['--qty','2','--funding-cost','.2','--as-of',(base+pd.Timedelta(seconds=16)).isoformat()])
            cli=json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(cli['net_R'],result['net_R'])
            self.assertEqual(len(cli['input_sha256']),7)
        received=list(args);received[8]=-.2
        self.assertAlmostEqual(assess_round_trip(*received)['net_pnl_usdt']-result['net_pnl_usdt'],.4,places=6)
        bad=list(args);bad[4]=quote(10,99.9,100);bad[3]={**mark,'price':99.9}
        self.assertEqual(assess_round_trip(*bad)['status'],'INVALID')
        bad=list(args);bad[4]=q1
        self.assertEqual(assess_round_trip(*bad)['status'],'INVALID')
        bad=list(args);bad[5]={**exit_event,'trade_id':'other'}
        self.assertEqual(assess_round_trip(*bad)['status'],'INVALID')
        bad=list(args);bad[6]=quote(13,99.5,99.6,bidqty=1)
        self.assertEqual(assess_round_trip(*bad)['status'],'UNKNOWN_DEPTH')
        bad=list(args);bad[5]={**exit_event,'price':99.5}
        self.assertEqual(assess_round_trip(*bad)['status'],'INVALID')

    def test_delayed_quote_causality_and_price_assumptions(self):
        base=pd.Timestamp('2026-10-30T00:05:00Z'); ms=lambda seconds:int((base+pd.Timedelta(seconds=seconds)).timestamp()*1000)
        cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        quote={'schema':'paper-quote-research-v1','source':'Binance USD-M public REST','verification':'PUBLIC_UNVERIFIED','config_sha256':cfg,
               'requests':[{'local_start_ms':ms(2),'local_end_ms':ms(2.02),'body':{'serverTime':ms(2.01)}},
                           {'local_start_ms':ms(2.1),'local_end_ms':ms(2.2),'body':{'symbol':'ETHUSDT','time':ms(2.15),
                            'bidPrice':'100','askPrice':'100.1','bidQty':'5','askQty':'3'}},
                           {'local_start_ms':ms(2.3),'local_end_ms':ms(2.32),'body':{'serverTime':ms(2.31)}}]}
        common={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                'symbol':'ETHUSDT','signal_time_utc':(base-pd.Timedelta(minutes=5)).isoformat()}
        signal={**common,'kind':'signal','event_time_utc':base.isoformat(),
                'captured_at_utc':(base+pd.Timedelta(seconds=1)).isoformat(),'capture_lag_seconds':1}
        entry={**common,'kind':'entry','trade_id':'q1','price':100.1*1.0002,
               'event_time_utc':(base+pd.Timedelta(seconds=3)).isoformat(),
               'captured_at_utc':(base+pd.Timedelta(seconds=4)).isoformat(),'capture_lag_seconds':1}
        check=lambda q=quote,s=signal,e=entry,n=2: assess_quote(q,s,e,n,base+pd.Timedelta(seconds=5))
        self.assertEqual(check()['status'],'PARTIAL_NOT_REGISTERED')
        self.assertEqual(check(n=4)['status'],'UNKNOWN_DEPTH')
        bad=copy.deepcopy(quote);bad['requests'][0]['local_start_ms']=ms(.5)
        self.assertEqual(check(q=bad)['status'],'INVALID')
        for bad_time in (ms(2.00),ms(2.32)):
            bad=copy.deepcopy(quote);bad['requests'][1]['body']['time']=bad_time
            self.assertEqual(check(q=bad)['status'],'INVALID')
        bad=copy.deepcopy(quote)
        for index,key in ((0,'serverTime'),(1,'time'),(2,'serverTime')): bad['requests'][index]['body'][key]+=3000
        self.assertEqual(check(q=bad)['status'],'INVALID')
        bad=copy.deepcopy(quote);bad['requests'][1]['body']['bidPrice']='101'
        self.assertEqual(check(q=bad)['status'],'INVALID')
        self.assertEqual(check(e={**entry,'price':100.1})['status'],'INVALID')
        stale_decision={**entry,'event_time_utc':(base+pd.Timedelta(seconds=4.5)).isoformat(),
                        'captured_at_utc':(base+pd.Timedelta(seconds=4.8)).isoformat(),'capture_lag_seconds':.3}
        self.assertEqual(check(e=stale_decision)['status'],'INVALID')
        too_early={**entry,'event_time_utc':(base+pd.Timedelta(seconds=2.2)).isoformat(),'capture_lag_seconds':1.8}
        self.assertEqual(check(e=too_early)['status'],'INVALID')

    def test_h3_sweep_uses_previous_twenty_bars_without_future(self):
        bars=pd.DataFrame({'low':[100.0]*20+[99.5,100.1,99.0],
                           'close':[101.0]*20+[100.5,100.5,99.5]})
        hits=sweep_reclaim([True]*23,bars)
        self.assertFalse(hits[:20].any())
        self.assertTrue(hits[20])
        self.assertFalse(hits[21])
        self.assertFalse(hits[22])
        bars.loc[22,'low']=1
        self.assertTrue(sweep_reclaim([True]*23,bars)[20])
        self.assertFalse(sweep_reclaim([False]*23,bars)[20])

    def test_funding_snapshot_pagination_and_duplicate_rejection(self):
        spec=importlib.util.spec_from_file_location('funding_stage',Path(__file__).resolve().parents[1]/'scripts/12_stage_funding.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        class Response:
            def __init__(self, rows): self.rows=rows
            def raise_for_status(self): pass
            def json(self): return self.rows
        class Session:
            def __init__(self, responses): self.responses=list(responses);self.cursors=[]
            def get(self,url,params,timeout): self.cursors.append(params['startTime']);return Response(self.responses.pop(0))
        rows=[{'symbol':'ETHUSDT','fundingTime':100},{'symbol':'ETHUSDT','fundingTime':200}]
        session=Session([rows,[]])
        self.assertEqual(module.fetch(session,'ETHUSDT',0,300),rows)
        self.assertEqual(session.cursors,[0,201])
        with self.assertRaises(ValueError): module.fetch(Session([[rows[0],rows[0]]]),'ETHUSDT',0,300)

    def test_funding_snapshot_can_check_no_event_missing_event_and_tampering(self):
        trade=dict(trade_id='s1',entry_time='2026-10-30T00:10:00Z',exit_time='2026-10-30T00:20:00Z',
                   symbol='ETHUSDT',side='long',entry=100,stop=99.6,exit=101,qty=2,equity_at_entry=2000,
                   fee_cost=.1,funding_cost=0.0,five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')
        closed=pd.DataFrame([trade]);opened=pd.DataFrame(columns=OPEN_FIELDS);empty=pd.DataFrame(columns=FUNDING_FIELDS)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def snapshot(event_time=None,begin='2026-10-30T00:00:00Z',end='2026-10-30T00:30:00Z'):
                manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                          'start_utc':begin,'end_utc_exclusive':end,
                          'query_server_time_ms':int(pd.Timestamp('2026-10-30T00:30:00Z').timestamp()*1000),
                          'server_time_ms':int(pd.Timestamp('2026-10-30T00:30:00Z').timestamp()*1000),
                          'captured_at_utc':'2026-10-30T00:30:00Z','symbols':{}}
                for symbol in ('BTCUSDT','ETHUSDT'):
                    rows=[] if symbol=='BTCUSDT' or not event_time else [{'symbol':symbol,
                        'fundingTime':int(pd.Timestamp(event_time).timestamp()*1000),'fundingRate':'.001','markPrice':'100'}]
                    raw=json.dumps(rows).encode();(root/(symbol+'.json')).write_bytes(raw)
                    manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows)}
                (root/'manifest.json').write_text(json.dumps(manifest))
            def check(f=empty):return reconcile_funding(closed,opened,f,'2026-10-30','2026-10-30T00:30:00Z',schedule=root)
            snapshot();self.assertEqual(check()['status'],'PARTIAL')
            snapshot(end='2026-10-30T00:21:00Z');self.assertEqual(check()['status'],'UNKNOWN')
            snapshot('2026-10-30T00:21:00Z',end='2026-10-30T00:21:00.001Z')
            self.assertEqual(check()['status'],'AMBIGUOUS')
            snapshot('2026-10-30T00:15:00Z');self.assertEqual(check()['status'],'INVALID')
            closed.loc[0,'funding_cost']=.2
            event=pd.DataFrame([{'trade_id':'s1','symbol':'ETHUSDT','funding_time':'2026-10-30T00:15:00Z',
                                 'funding_rate':.001,'reference_mark_price':100,'qty':2,'funding_cost':.2,'source':'synthetic'}])
            self.assertEqual(check(event)['status'],'PARTIAL')
            event.loc[0,'funding_rate']=.002
            self.assertEqual(check(event)['status'],'INVALID')
            closed.loc[0,'funding_cost']=0
            snapshot('2026-10-30T00:10:30Z');self.assertEqual(check()['status'],'AMBIGUOUS')
            openrow={k:v for k,v in trade.items() if k in OPEN_FIELDS}
            openrow.update(mark_price=100,mark_time='2026-10-30T00:20:00Z',mark_source='synthetic',entry_fee=.05)
            open_frame=pd.DataFrame([openrow]);empty_closed=pd.DataFrame(columns=CLOSED_FIELDS)
            snapshot()
            open_result=reconcile_funding(empty_closed,open_frame,empty,'2026-10-30','2026-10-30T00:30:00Z',schedule=root)
            self.assertEqual(open_result['status'],'PARTIAL')
            self.assertEqual(open_result['open_after_snapshot_unknown'],['s1'])
            self.assertEqual(open_result['open_funding_as_of_utc']['s1'],'2026-10-30T00:20:00+00:00')
            snapshot(end='2026-10-30T00:21:00Z')
            self.assertEqual(reconcile_funding(empty_closed,open_frame,empty,'2026-10-30','2026-10-30T00:30:00Z',schedule=root)['status'],'UNKNOWN')
            snapshot('2026-10-30T00:15:00Z')
            self.assertEqual(reconcile_funding(empty_closed,open_frame,empty,'2026-10-30','2026-10-30T00:30:00Z',schedule=root)['status'],'INVALID')
            snapshot(begin='2026-10-30T00:11:00Z');self.assertEqual(check()['status'],'UNKNOWN')
            snapshot();manifest=json.loads((root/'manifest.json').read_text())
            manifest['server_time_ms']+=1000;(root/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(check()['status'],'INVALID')
            snapshot();manifest=json.loads((root/'manifest.json').read_text())
            manifest['captured_at_utc']='2026-10-30T00:30:01Z';(root/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(check()['status'],'INVALID')
            snapshot();manifest=json.loads((root/'manifest.json').read_text())
            manifest['schema']='paper-funding-snapshot-v1';(root/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(check()['status'],'INVALID')
            snapshot();(root/'ETHUSDT.json').write_text('[] ')
            self.assertEqual(check()['status'],'INVALID')

    def test_funding_reconciliation_and_settlement_boundary(self):
        trade=dict(trade_id='f1',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T09:00:00Z',
                   symbol='ETHUSDT',side='long',entry=100,stop=99.6,exit=101,qty=2,equity_at_entry=2000,
                   fee_cost=.1,funding_cost=.2,five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')
        evidence=dict(trade_id='f1',symbol='ETHUSDT',funding_time='2026-10-30T08:00:00Z',
                      funding_rate=.001,reference_mark_price=100,qty=2,funding_cost=.2,source='synthetic')
        closed=pd.DataFrame([trade]);empty_open=pd.DataFrame(columns=OPEN_FIELDS)
        def check(c, f): return reconcile_funding(c,empty_open,f,'2026-10-30','2026-10-30T10:00:00Z')
        result=check(closed,pd.DataFrame([evidence]))
        self.assertEqual(result['status'],'PARTIAL')
        self.assertEqual(result['funding_cost_usdt_by_trade']['f1'],.2)
        self.assertEqual(check(closed,pd.DataFrame([{**evidence,'funding_cost':.21}]))['status'],'INVALID')
        near=closed.copy();near.loc[0,'entry_time']='2026-10-30T07:59:30Z'
        self.assertEqual(check(near,pd.DataFrame([evidence]))['status'],'AMBIGUOUS')
        zero=closed.copy();zero.loc[0,'funding_cost']=0
        self.assertEqual(check(zero,pd.DataFrame(columns=FUNDING_FIELDS))['status'],'UNKNOWN')
        self.assertEqual(check(closed,pd.DataFrame(columns=FUNDING_FIELDS))['status'],'INVALID')
        received=pd.DataFrame([{**evidence,'funding_rate':-.001,'funding_cost':-.2}])
        short_cost=closed.copy();short_cost.loc[0,'funding_cost']=-.2
        self.assertEqual(check(short_cost,received)['status'],'PARTIAL')
        openrow={k:v for k,v in trade.items() if k in OPEN_FIELDS}
        openrow.update(mark_price=100,mark_time='2026-10-30T10:00:00Z',mark_source='synthetic',entry_fee=.05)
        open_result=reconcile_funding(pd.DataFrame(columns=CLOSED_FIELDS),pd.DataFrame([openrow]),
                         pd.DataFrame([evidence]),'2026-10-30','2026-10-30T10:00:00Z')
        self.assertEqual(open_result['status'],'PARTIAL')

    def test_funding_mark_uses_entry_inclusive_exit_exclusive(self):
        from types import SimpleNamespace
        base=pd.Timestamp('2026-10-30',tz='UTC')
        trade=SimpleNamespace(entry_ts=str(base),exit_ts=str(base+pd.Timedelta(hours=8)),qty=2)
        funding=pd.DataFrame({'ts':[int(base.timestamp()*1000),int((base+pd.Timedelta(hours=8)).timestamp()*1000)],
                              'funding_rate':[.001,.001],'proxy_price':[100,100],'mark_price':[101,101]})
        count,proxy,mark=funding_for_trade(trade,funding)
        self.assertEqual(count,1)
        self.assertAlmostEqual(proxy,.2)
        self.assertAlmostEqual(mark,.202)

    def test_execution_delay_keeps_original_signal_and_moves_entry_one_bar(self):
        ts = pd.date_range('2024-01-01', periods=5, freq='5min', tz='UTC')
        bars = pd.DataFrame({'ts': ts, 'open': [100]*5, 'high': [101]*5,
                             'low': [100]*5, 'close': [100]*5})
        funding = pd.DataFrame({'ts': pd.Series(dtype='int64'), 'funding_rate': pd.Series(dtype=float)})
        original = [True, False, False, False, True]
        delayed = delay_one_bar(original)
        self.assertEqual(original, [True, False, False, False, True])
        self.assertEqual(delayed.tolist(), [False, True, False, False, False])
        self.assertEqual(candidates_with_entry_in_window(bars, delayed, '2024-01-01', '2024-01-01 00:25'), 1)
        _, _, baseline = replay(bars, original, pd.Series(dtype=float), funding, '2024-01-01', '2024-01-01 00:25')
        _, _, later = replay(bars, delayed, pd.Series(dtype=float), funding, '2024-01-01', '2024-01-01 00:25')
        self.assertEqual(pd.Timestamp(later[0]['entry_ts']) - pd.Timestamp(baseline[0]['entry_ts']), pd.Timedelta(minutes=5))

    def test_open_profit_is_not_available_before_exit(self):
        t = pd.DataFrame([
            dict(entry_ts=pd.Timestamp('2024-01-01'), exit_ts=pd.Timestamp('2024-01-03'), net_R=100),
            dict(entry_ts=pd.Timestamp('2024-01-02'), exit_ts=pd.Timestamp('2024-01-02 12:00'), net_R=1),
        ])
        self.assertEqual(sim(t, 0.01, 3)['final'], 4020.0)

    def test_selector_ranks_coins_not_repeated_signals(self):
        t = pd.DataFrame([dict(day='2024-01-01', symbol=s, rs7=r) for s, r in
                          [('A', .3), ('A', .3), ('A', .3), ('B', .2), ('C', .1), ('D', .05)]])
        self.assertEqual(set(select(t, 'S1_top3').symbol), {'A', 'B', 'C'})

    def test_unverified_report_cannot_pass(self):
        self.assertEqual(report(pd.DataFrame([{}] * 100))['status'], 'INVALID')

    def test_paper_report_cost_risk_and_missing_data(self):
        row = dict(trade_id='p1', entry_time='2026-10-30T00:00:00Z', exit_time='2026-10-30T01:00:00Z',
                   symbol='ETHUSDT', side='long', entry='100', stop='99.6', exit='103', qty='2',
                   equity_at_entry='2000', fee_cost='0.4', funding_cost='-0.1', five_q_pass='1',
                   stop_placed='1', added='0', reversed='0', plan_deviation='0')
        d=pd.DataFrame([row]); out=report(d,'2026-10-30','2026-10-31')
        self.assertEqual(out['status'],'HOLD')
        self.assertEqual(out['records'][0]['net_R'],7.125)
        self.assertEqual(out['records'][0]['risk_pct'],.04)
        self.assertEqual(out['fee_funding_over_execution_gross_profit_pct'],5.0)
        self.assertIsNone(out['cost_over_gross_profit_pct'])
        with_refs=d.assign(reference_entry='99.9',reference_exit='103.1',reference_source='synthetic')
        result=report(with_refs,'2026-10-30','2026-10-31')
        self.assertEqual(result['net_pnl_usdt'],5.7)
        self.assertEqual(result['slippage_cost_usdt'],.4)
        self.assertEqual(result['total_estimated_cost_usdt'],.7)
        self.assertEqual(result['reference_gross_profit_usdt'],6.4)
        self.assertEqual(result['cost_over_gross_profit_pct'],10.9375)
        self.assertEqual(result['records'][0]['net_R'],7.125)
        self.assertEqual(result['records'][0]['slippage_cost_usdt'],.4)
        self.assertEqual(result['records'][0]['reference_source'],'synthetic')
        favorable=d.assign(reference_entry='100.1',reference_exit='102.9',reference_source='synthetic')
        result=report(favorable,'2026-10-30','2026-10-31')
        self.assertEqual(result['slippage_cost_usdt'],-.4)
        self.assertEqual(result['total_estimated_cost_usdt'],-.1)
        self.assertEqual(result['net_pnl_usdt'],5.7)
        zero_ref_profit=d.assign(reference_entry='100',reference_exit='100',reference_source='synthetic')
        self.assertIsNone(report(zero_ref_profit,'2026-10-30','2026-10-31')['cost_over_gross_profit_pct'])
        with_refs.loc[0,'reference_exit']=''
        self.assertIsNone(report(with_refs,'2026-10-30','2026-10-31')['cost_over_gross_profit_pct'])
        mixed=pd.concat([d.assign(trade_id='p2'),with_refs],ignore_index=True)
        self.assertIsNone(report(mixed,'2026-10-30','2026-10-31')['cost_over_gross_profit_pct'])
        with_refs.loc[0,'reference_exit']='not-a-price'
        self.assertEqual(report(with_refs,'2026-10-30','2026-10-31')['status'],'INVALID')
        with_refs.loc[0,'reference_exit']='UNKNOWN'
        self.assertIsNone(report(with_refs,'2026-10-30','2026-10-31')['cost_over_gross_profit_pct'])
        with_refs.loc[0,'reference_exit']='103.1'
        with_refs.loc[0,'reference_source']='UNKNOWN'
        self.assertIsNone(report(with_refs,'2026-10-30','2026-10-31')['cost_over_gross_profit_pct'])
        self.assertEqual(report(d.drop(columns='funding_cost'),'2026-10-30','2026-10-31')['status'],'INVALID')
        d.loc[0,'qty']='10'
        self.assertEqual(report(d,'2026-10-30','2026-10-31')['status'],'STOP')
        d.loc[0,'entry_time']='2026-10-29T23:00:00Z'
        self.assertEqual(report(d,'2026-10-30','2026-10-31')['status'],'INVALID')

    def test_paper_report_rejects_ineligible_and_duplicate_records(self):
        row = dict(trade_id='p1', entry_time='2026-10-30T00:00:00Z', exit_time='2026-10-30T01:00:00Z',
                   symbol='BTCUSDT', side='long', entry='100', stop='99.6', exit='103', qty='2',
                   equity_at_entry='2000', fee_cost='0.4', funding_cost='0', five_q_pass='1',
                   stop_placed='1', added='0', reversed='0', plan_deviation='0')
        self.assertEqual(report(pd.DataFrame([row]),'2026-10-30','2026-10-31')['status'],'INVALID')
        row['symbol']='ETHUSDT'
        self.assertEqual(report(pd.DataFrame([row,row]),'2026-10-30','2026-10-31')['status'],'INVALID')
        self.assertEqual(report(pd.DataFrame([row,{**row,'trade_id':' p1 '}]),'2026-10-30','2026-10-31')['status'],'INVALID')
        self.assertEqual(report(pd.DataFrame([{**row,'trade_id':'UNKNOWN'}]),'2026-10-30','2026-10-31')['status'],'INVALID')
        row['stop_placed']=''
        self.assertEqual(report(pd.DataFrame([row]),'2026-10-30','2026-10-31')['status'],'INVALID')

    def test_paper_numeric_threshold_does_not_auto_pass(self):
        row = dict(entry_time='2026-10-30T00:00:00Z', exit_time='2026-10-30T01:00:00Z',
                   symbol='ETHUSDT', side='long', entry='100', stop='99.6', exit='103', qty='2',
                   equity_at_entry='2000', fee_cost='0.4', funding_cost='0', five_q_pass='1',
                   stop_placed='1', added='0', reversed='0', plan_deviation='0',
                   reference_entry='100',reference_exit='103',reference_source='synthetic')
        d=pd.DataFrame([{**row,'trade_id':str(i), 'entry_time':(pd.Timestamp('2026-10-30',tz='UTC')+pd.Timedelta(days=i)).isoformat(),
                         'exit_time':(pd.Timestamp('2026-10-30 01:00',tz='UTC')+pd.Timedelta(days=i)).isoformat()} for i in range(20)])
        out=report(d,'2026-10-30','2027-02-01')
        self.assertIsNone(out['numeric_gate_met_unverified'])
        self.assertTrue(out['candidate_threshold_met_unverified'])
        self.assertEqual(out['status'],'HOLD')
        self.assertEqual(report(d,'2026-01-01','2027-02-01')['status'],'INVALID')

    def test_paper_closed_ledger_daily_and_concurrent_limits(self):
        row = dict(symbol='ETHUSDT', side='long', entry='100', stop='99.6', exit='103', qty='2',
                   equity_at_entry='2000', fee_cost='0.4', funding_cost='0', five_q_pass='1',
                   stop_placed='1', added='0', reversed='0', plan_deviation='0')
        start=pd.Timestamp('2026-10-30',tz='UTC')
        daily=pd.DataFrame([{**row,'trade_id':str(i),'entry_time':start+pd.Timedelta(hours=i),
                             'exit_time':start+pd.Timedelta(hours=i+1)} for i in range(4)])
        out=report(daily,'2026-10-30','2026-11-05')
        self.assertEqual(out['status'],'STOP')
        self.assertEqual(out['max_daily_entries_closed_only'],4)
        self.assertEqual(out['max_concurrent_closed_only'],1)
        self.assertEqual(out['violations']['daily_entries_over_limit'],1)
        concurrent=pd.DataFrame([{**row,'trade_id':str(i),'entry_time':start+pd.Timedelta(days=i),
                                  'exit_time':start+pd.Timedelta(days=4)} for i in range(4)])
        out=report(concurrent,'2026-10-30','2026-11-05')
        self.assertEqual(out['status'],'STOP')
        self.assertEqual(out['max_daily_entries_closed_only'],1)
        self.assertEqual(out['max_concurrent_closed_only'],4)
        self.assertEqual(out['violations']['concurrent_over_limit'],1)
        immediate=pd.DataFrame([{**row,'trade_id':str(i),'entry_time':start,'exit_time':start} for i in range(4)])
        self.assertEqual(report(immediate,'2026-10-30','2026-11-05')['status'],'INVALID')

    def test_combined_risk_detects_open_and_closed_overlap(self):
        closedrow = dict(symbol='ETHUSDT', side='long', entry='100', stop='99.6', exit='103', qty='2',
                         equity_at_entry='2000', fee_cost='0.4', funding_cost='0', five_q_pass='1',
                         stop_placed='1', added='0', reversed='0', plan_deviation='0')
        openrow = dict(symbol='ETHUSDT', side='long', entry='100', stop='99.6', qty='2',
                       equity_at_entry='2000', funding_cost='0', mark_price='100', mark_source='synthetic',
                       entry_fee='.1', mark_time='2026-11-02T01:00:00Z')
        closed=pd.DataFrame([{**closedrow, 'trade_id':'c'+str(i),
                              'entry_time':(pd.Timestamp('2026-10-30',tz='UTC')+pd.Timedelta(days=i)).isoformat(),
                              'exit_time':'2026-11-02T01:00:00Z'} for i in range(3)])
        opened=pd.DataFrame([{**openrow,'trade_id':'o1','entry_time':'2026-11-02T00:30:00Z'}])
        out=audit_combined_risk(closed,opened,'2026-10-30','2026-11-02T01:00:00Z')
        self.assertEqual(out['status'],'STOP')
        self.assertEqual(out['max_concurrent_recorded'],4)
        self.assertEqual(out['peak_initial_price_risk_usdt_recorded'],3.2)
        self.assertTrue(out['combined_limit_violations']['concurrent_over_limit'])
        opened.loc[0,'trade_id']='c0'
        self.assertEqual(audit_combined_risk(closed,opened,'2026-10-30','2026-11-02T01:00:00Z')['status'],'INVALID')
        empty=audit_combined_risk(pd.DataFrame(columns=CLOSED_FIELDS),pd.DataFrame(columns=OPEN_FIELDS),
                                  '2026-10-30','2026-11-02T01:00:00Z')
        self.assertEqual(empty['status'],'UNKNOWN')

    def test_flat_entry_equity_reconciliation_respects_overlaps(self):
        c=dict(trade_id='closed',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T00:20:00Z',
               symbol='ETHUSDT',side='long',entry='100',stop='99.6',exit='101',qty='2',
               equity_at_entry='2000',fee_cost='.2',funding_cost='.1',five_q_pass='1',
               stop_placed='1',added='0',reversed='0',plan_deviation='0')
        o=dict(trade_id='open',entry_time='2026-10-30T00:25:00Z',symbol='ETHUSDT',side='long',
               entry='100',stop='99.6',qty='2',equity_at_entry='2001.7',mark_price='101',
               mark_time='2026-10-30T00:30:00Z',mark_source='synthetic',entry_fee='.1',funding_cost='0')
        closed=pd.DataFrame([c]);opened=pd.DataFrame([o]);start='2026-10-30';asof='2026-10-30T00:35:00Z'
        out=audit_combined_risk(closed,opened,start,asof)
        self.assertEqual([x['status'] for x in out['flat_entry_equity_check']],['MATCH_ASSUMED','MATCH_ASSUMED'])
        self.assertEqual(out['flat_entry_equity_check'][1]['expected_usdt'],2001.7)
        opened.loc[0,'equity_at_entry']='2100'
        self.assertEqual(audit_combined_risk(closed,opened,start,asof)['status'],'STOP')
        opened.loc[0,'entry_time']='2026-10-30T00:15:00Z'
        self.assertEqual(audit_combined_risk(closed,opened,start,asof)['flat_entry_equity_check'][1]['status'],'UNKNOWN_OVERLAP_OR_ORDER')
        opened.loc[0,'entry_time']='2026-10-30T00:20:00Z'
        self.assertEqual(audit_combined_risk(closed,opened,start,asof)['flat_entry_equity_check'][1]['status'],'UNKNOWN_OVERLAP_OR_ORDER')
        opened.loc[0,'entry_time']='2026-10-30T00:00:00Z'
        checks=audit_combined_risk(closed,opened,start,asof)['flat_entry_equity_check']
        self.assertEqual([x['status'] for x in checks],['UNKNOWN_OVERLAP_OR_ORDER']*2)

    def test_paper_margin_limit_missing_invalid_and_stale(self):
        closed=dict(trade_id='closed',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T00:20:00Z',
                    symbol='ETHUSDT',side='long',entry='100',stop='99.6',exit='101',qty='2',
                    equity_at_entry='2000',fee_cost='.2',funding_cost='.1',five_q_pass='1',
                    stop_placed='1',added='0',reversed='0',plan_deviation='0')
        opened=dict(trade_id='open',entry_time='2026-10-30T00:10:00Z',symbol='ETHUSDT',side='long',
                    entry='100',stop='99.6',qty='2',equity_at_entry='2000',mark_price='101',
                    mark_time='2026-10-30T00:30:00Z',mark_source='synthetic',entry_fee='.1',funding_cost='0')
        c=pd.DataFrame([closed]);o=pd.DataFrame([opened]);start='2026-10-30';now='2026-10-30T00:35:00Z'
        self.assertEqual(report(c,start,now)['paper_initial_leverage_status'],'UNKNOWN_INCOMPLETE')
        self.assertEqual(evaluate(o,now)['paper_initial_leverage_status'],'UNKNOWN_INCOMPLETE')
        c['margin_at_entry']='40';o['margin_at_entry']='40'
        self.assertEqual(report(c,start,now)['records'][0]['paper_initial_leverage'],5)
        self.assertEqual(evaluate(o,now)['paper_initial_leverage_by_trade']['open'],5)
        self.assertEqual(report(c,start,now)['status'],'HOLD')
        self.assertEqual(evaluate(o,now)['actual_exchange_leverage'],'UNKNOWN')
        c['margin_at_entry']='20';o['margin_at_entry']='20'
        self.assertEqual(report(c,start,now)['status'],'STOP')
        self.assertEqual(evaluate(o,now)['status'],'ALERT')
        self.assertEqual(evaluate(o,'2026-10-30T01:00:00Z')['status'],'ALERT')
        self.assertEqual(audit_combined_risk(c,o,start,now)['status'],'STOP')
        self.assertEqual(evaluate_paper_equity(c,o,start,now)['status'],'STOP')
        for value in ('0','bad','-1','inf'):
            c['margin_at_entry']=value;o['margin_at_entry']=value
            self.assertEqual(report(c,start,now)['status'],'INVALID')
            self.assertEqual(evaluate(o,now)['status'],'INVALID')
        c['margin_at_entry']='UNKNOWN';o['margin_at_entry']=''
        self.assertEqual(report(c,start,now)['paper_initial_leverage_status'],'UNKNOWN_INCOMPLETE')
        self.assertEqual(evaluate(o,now)['paper_initial_leverage_status'],'UNKNOWN_INCOMPLETE')

    def test_conditional_paper_equity_and_time_boundaries(self):
        c=dict(trade_id='closed',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T00:20:00Z',
               symbol='ETHUSDT',side='long',entry='100',stop='99.6',exit='101',qty='2',
               equity_at_entry='2000',fee_cost='.2',funding_cost='.1',five_q_pass='1',
               stop_placed='1',added='0',reversed='0',plan_deviation='0')
        o=dict(trade_id='open',entry_time='2026-10-30T00:10:00Z',symbol='ETHUSDT',side='long',
               entry='100',stop='99.6',qty='2',equity_at_entry='2000',mark_price='101',
               mark_time='2026-10-30T00:30:00Z',mark_source='synthetic',entry_fee='.1',funding_cost='-.05')
        closed=pd.DataFrame([c]);opened=pd.DataFrame([o]);start='2026-10-30';asof='2026-10-30T00:35:00Z'
        out=evaluate_paper_equity(closed,opened,start,asof)
        self.assertEqual(out['status'],'REVIEW')
        self.assertEqual(out['closed_net_pnl_usdt'],1.7)
        self.assertEqual(out['modeled_equity_usdt'],2003.65)
        self.assertTrue(out['valuation_before_as_of'])
        self.assertEqual(out['liquidation'],'UNKNOWN')
        crossing=closed.copy();crossing.loc[0,'exit_time']='2026-10-30T00:34:00Z'
        self.assertEqual(evaluate_paper_equity(crossing,opened,start,asof)['status'],'UNKNOWN')
        crossing.loc[0,'exit_time']='2026-10-30T00:30:00Z'
        self.assertEqual(evaluate_paper_equity(crossing,opened,start,asof)['status'],'UNKNOWN')
        second=opened.copy();second.loc[0,'trade_id']='open2';second.loc[0,'mark_time']='2026-10-30T00:31:00Z'
        self.assertEqual(evaluate_paper_equity(closed,pd.concat([opened,second]),start,asof)['status'],'UNKNOWN')
        later=closed.copy();later.loc[0,'entry_time']='2026-10-30T00:32:00Z';later.loc[0,'exit_time']='2026-10-30T00:34:00Z'
        earlier=evaluate_paper_equity(later,opened,start,asof)
        self.assertEqual(earlier['modeled_equity_usdt'],2001.95)
        self.assertEqual(earlier['closed_trades_after_valuation_excluded'],1)
        below=opened.copy();below.loc[0,'mark_price']='99.5'
        self.assertEqual(evaluate_paper_equity(closed,below,start,asof)['status'],'STOP')
        self.assertEqual(evaluate_paper_equity(pd.DataFrame(columns=CLOSED_FIELDS),
                         pd.DataFrame(columns=OPEN_FIELDS),start,asof)['status'],'UNKNOWN')

    def test_open_snapshot_floating_risk_and_freshness(self):
        row=dict(trade_id='p1',entry_time='2026-10-30T00:00:00Z',symbol='ETHUSDT',side='long',
                 entry='100',stop='99.6',qty='2',equity_at_entry='2000',mark_price='98',
                 mark_time='2026-10-30T00:10:00Z',mark_source='test-price-proxy',
                 entry_fee='0.1',funding_cost='-0.05')
        d=pd.DataFrame([row]); result=evaluate(d,'2026-10-30T00:15:00Z')
        self.assertEqual(result['status'],'ALERT')
        self.assertEqual(result['unrealized_after_recorded_costs_usdt'],-4.05)
        self.assertEqual(result['liquidation'],'UNKNOWN')
        self.assertEqual(evaluate(d,'2026-10-30T01:00:00Z')['status'],'STALE')
        d.loc[0,'qty']='10'
        stale_risk=evaluate(d,'2026-10-30T01:00:00Z')
        self.assertEqual(stale_risk['status'],'ALERT')
        self.assertTrue(stale_risk['violations']['over_price_risk'])
        self.assertEqual(stale_risk['violations']['mark_at_or_below_stop'],'UNKNOWN')
        self.assertEqual(evaluate(d.drop(columns='mark_source'),'2026-10-30T00:15:00Z')['status'],'INVALID')
        d.loc[0,'mark_source']='UNKNOWN'
        self.assertEqual(evaluate(d,'2026-10-30T00:15:00Z')['status'],'INVALID')
        d.loc[0,'mark_source']='synthetic'
        d.loc[0,'trade_id']=' p1 '
        self.assertEqual(evaluate(d,'2026-10-30T00:15:00Z')['status'],'INVALID')

    def test_open_nonfinite_derived_values_propagate_to_portfolio(self):
        row=dict(trade_id='p1',entry_time='2026-10-30T00:00:00Z',symbol='ETHUSDT',side='long',
                 entry='100',stop='99.6',qty='2',equity_at_entry='2000',mark_price='1e308',
                 mark_time='2026-10-30T00:10:00Z',mark_source='synthetic',entry_fee='0',funding_cost='0')
        opened=pd.DataFrame([row]); closed=pd.DataFrame(columns=CLOSED_FIELDS)
        start='2026-10-30'; now='2026-10-30T00:15:00Z'
        self.assertEqual(evaluate(opened,now)['status'],'INVALID')
        self.assertEqual(audit_combined_risk(closed,opened,start,now)['status'],'INVALID')
        self.assertEqual(evaluate_paper_equity(closed,opened,start,now)['status'],'INVALID')
        row.update(entry='1e308',stop='9.96e307',qty='1e308',mark_price='1e308')
        # Staleness must not hide an invalid initial risk.
        self.assertEqual(evaluate(pd.DataFrame([row]),'2026-10-30T01:00:00Z')['status'],'INVALID')
        row.update(entry='100',stop='99.6',qty='5e-324',mark_price='100')
        self.assertEqual(evaluate(pd.DataFrame([row]),now)['status'],'INVALID')
        row.update(qty='1',mark_price='9e307')
        many=pd.DataFrame([{**row,'trade_id':'p1'},{**row,'trade_id':'p2'},{**row,'trade_id':'p3'}])
        self.assertEqual(evaluate(many,now)['status'],'INVALID')

    def test_combined_peak_risk_overflow_is_invalid(self):
        base=dict(symbol='ETHUSDT',side='long',entry='1e308',stop='9.96e307',qty='200',
                  equity_at_entry='1e308',entry_time='2026-10-30T00:00:00Z')
        closed=pd.DataFrame([{**base,'trade_id':f'c{i}','exit_time':'2026-10-30T00:14:00Z',
                              'exit':'1e308','fee_cost':'0','funding_cost':'0','five_q_pass':'1',
                              'stop_placed':'1','added':'0','reversed':'0','plan_deviation':'0'}
                             for i in range(2)])
        opened=pd.DataFrame([{**base,'trade_id':'o1','mark_price':'1e308',
                              'mark_time':'2026-10-30T00:10:00Z','mark_source':'synthetic',
                              'entry_fee':'0','funding_cost':'0'}])
        out=audit_combined_risk(closed,opened,'2026-10-30','2026-10-30T00:15:00Z')
        self.assertEqual(out['status'],'INVALID')
        self.assertIn('组合峰值',out['reason'])

    def test_fresh_stop_alert_survives_another_stale_price(self):
        base=dict(entry_time='2026-10-30T00:00:00Z',symbol='ETHUSDT',side='long',entry='100',
                  stop='99.6',qty='2',equity_at_entry='2000',mark_source='synthetic',entry_fee='0.1',funding_cost='0')
        d=pd.DataFrame([{**base,'trade_id':'old','mark_price':'101','mark_time':'2026-10-30T00:10:00Z'},
                        {**base,'trade_id':'fresh','mark_price':'99','mark_time':'2026-10-30T00:29:00Z'}])
        out=evaluate(d,'2026-10-30T00:30:00Z')
        self.assertEqual(out['status'],'ALERT')
        self.assertTrue(out['violations']['mark_at_or_below_stop'])
        d.loc[1,'mark_price']='101'
        self.assertEqual(evaluate(d,'2026-10-30T00:30:00Z')['status'],'STALE')
        d.loc[0,'mark_time']='2026-10-30T00:28:00Z'
        self.assertFalse(evaluate(d,'2026-10-30T00:30:00Z')['valuation_timestamps_identical'])

    def test_paper_event_is_new_local_unverified_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                capture(directory,'entry','ETHUSDT','2026-10-30T00:00:00Z','test',trade_id='UNKNOWN',price=100)
            result=capture(directory,'signal','ETHUSDT','2026-10-30T00:00:00Z','synthetic test',signal_time='2026-10-29T23:55:00Z')
            raw=Path(result['path']).read_bytes(); payload=json.loads(raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),result['sha256'])
            self.assertEqual(payload['verification'],'MANUAL_UNVERIFIED')
            with self.assertRaises(ValueError): capture(directory,'signal','BTCUSDT','2026-10-30T00:00:00Z','test')
            with self.assertRaises(ValueError): capture(directory,'signal','ETHUSDT','2026-01-01T00:00:00Z','test')
            with self.assertRaises(ValueError): capture(directory,'signal','ETHUSDT','2099-01-01T00:00:00Z','test')
            with self.assertRaises(ValueError): capture(directory,'entry','ETHUSDT','2026-10-30T00:00:00Z','test')
            entry=capture(directory,'entry','ETHUSDT','2026-10-30T00:00:00Z','synthetic test','p1','2026-10-29T23:55:00Z',100.)
            self.assertEqual(json.loads(Path(entry['path']).read_text())['trade_id'],'p1')
            delayed=capture(directory,'entry','ETHUSDT','2026-10-30T00:00:30Z','synthetic delayed','p2','2026-10-29T23:55:00Z',100.)
            self.assertEqual(json.loads(Path(delayed['path']).read_text())['event_time_utc'],'2026-10-30T00:00:30+00:00')
            with self.assertRaises(ValueError):
                capture(directory,'entry','ETHUSDT','2026-10-29T23:59:59Z','early','p3','2026-10-29T23:55:00Z',100.)

    def test_synthetic_manual_paper_flow_is_not_a_pass(self):
        trade=dict(trade_id='integration-1',entry_time='2026-10-30T00:00:00Z',
                   exit_time='2026-10-30T01:00:00Z',symbol='ETHUSDT',side='long',entry='100',
                   stop='99.6',exit='101',qty='2',equity_at_entry='2000',fee_cost='.2',
                   funding_cost='.02',five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')
        with tempfile.TemporaryDirectory() as directory:
            for kind, stamp in [('entry',trade['entry_time']),('exit',trade['exit_time'])]:
                record=capture(directory,kind,'ETHUSDT',stamp,'synthetic integration check',trade['trade_id'],
                               '2026-10-29T23:55:00Z' if kind=='entry' else None,float(trade[kind]))
                self.assertEqual(json.loads(Path(record['path']).read_text())['trade_id'],trade['trade_id'])
            result=report(pd.DataFrame([trade]),'2026-10-29','2026-10-30T02:00:00Z')
            self.assertEqual(result['status'],'HOLD')
            self.assertEqual(result['net_pnl_usdt'],1.78)
            self.assertEqual(result['records'][0]['net_R'],2.225)

    def test_synthetic_event_reconciliation_fails_closed(self):
        t=dict(trade_id='integration-1',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T01:00:00Z',
               symbol='ETHUSDT',side='long',entry='100',stop='99.6',exit='101',qty='2',equity_at_entry='2000',
               fee_cost='.2',funding_cost='.02',five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')
        cfg=hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        events=[dict(schema='paper-event-v1',verification='MANUAL_UNVERIFIED',config_sha256=cfg,
                     trade_id=t['trade_id'],symbol='ETHUSDT',kind=kind,event_time_utc=t[kind+'_time'],
                     signal_time_utc='2026-10-29T23:55:00Z' if kind=='entry' else None,
                     price=float(t[kind]),
                     captured_at_utc=(pd.Timestamp(t[kind+'_time'])+pd.Timedelta(seconds=60)).isoformat(),capture_lag_seconds=60)
                for kind in ('entry','exit')]
        d=pd.DataFrame([t]); self.assertEqual(reconcile(d,events,'2026-10-29','2026-10-30T02:00:00Z')['status'],'PARTIAL')
        events[0]['price']=101
        self.assertEqual(reconcile(d,events,'2026-10-29','2026-10-30T02:00:00Z')['status'],'INVALID')
        events[0]['price']=100
        self.assertEqual(reconcile(d,events[:1],'2026-10-29','2026-10-30T02:00:00Z')['status'],'INVALID')
        events[1]['captured_at_utc']='2026-10-30T01:30:00Z';events[1]['capture_lag_seconds']=1800
        self.assertEqual(reconcile(d,events,'2026-10-29','2026-10-30T02:00:00Z')['status'],'INVALID')

    def test_stop_uses_recorded_entry_not_unadjusted_open(self):
        self.assertAlmostEqual(stop_for_entry(105), 104.58)
        self.assertIsNone(stop_for_entry(None))
        theoretical_open=100.;simulated_entry=100.02
        self.assertAlmostEqual(stop_for_entry(simulated_entry),99.61992)
        self.assertNotAlmostEqual(stop_for_entry(theoretical_open),stop_for_entry(simulated_entry))
        trade=dict(trade_id='s1',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T00:05:00Z',
                   symbol='ETHUSDT',side='long',entry=simulated_entry,stop=stop_for_entry(theoretical_open),exit=101,qty=1,
                   equity_at_entry=2000,fee_cost=.1,funding_cost=0,five_q_pass='1',stop_placed='1',
                   added='0',reversed='0',plan_deviation='0')
        self.assertEqual(report(pd.DataFrame([trade]),'2026-10-30','2026-10-31')['status'],'INVALID')
        trade['stop']=stop_for_entry(simulated_entry)
        self.assertEqual(report(pd.DataFrame([trade]),'2026-10-30','2026-10-31')['status'],'HOLD')

    def test_scan_rejects_stale_gapped_and_unclosed_candles(self):
        ts=pd.date_range('2026-10-30T00:00:00Z',periods=3,freq='5min')
        d=pd.DataFrame({'ts':ts})
        closed,state=closed_snapshot(d,pd.Timestamp('2026-10-30T00:12:00Z'))
        self.assertEqual(len(closed),2)
        self.assertEqual(state['status'],'FRESH')
        self.assertEqual(closed_snapshot(d,pd.Timestamp('2026-10-30T01:00:00Z'))[1]['status'],'STALE')
        self.assertEqual(closed_snapshot(d.iloc[[0,2]],pd.Timestamp('2026-10-30T00:20:00Z'))[1]['status'],'INVALID')
        self.assertEqual(closed_snapshot(pd.concat([d,d.iloc[[2]]]),pd.Timestamp('2026-10-30T00:20:00Z'))[1]['status'],'INVALID')
        bad=d.assign(open=100.,high=99.,low=98.,close=100.)
        self.assertEqual(closed_snapshot(bad,pd.Timestamp('2026-10-30T00:20:00Z'))[1]['status'],'INVALID')
        shifted=pd.DataFrame({'ts':ts+pd.Timedelta(seconds=1)})
        self.assertEqual(closed_snapshot(shifted,pd.Timestamp('2026-10-30T00:20:00Z'))[1]['status'],'INVALID')
        self.assertEqual(closed_snapshot(d,pd.Timestamp('2026-10-30T00:20:00Z'),minimum_bars=20)[1]['status'],'INVALID')

    def test_signal_output_does_not_silently_truncate(self):
        ts=pd.date_range('2026-10-30T00:00:00Z',periods=25,freq='5min')
        d=pd.DataFrame({'ts':ts,'open':[100.]*25})
        rows=signal_records(d,[True]*25,ts[0])
        self.assertEqual(len(rows),25)
        self.assertIsNone(rows[-1]['entry_next_open'])
        self.assertNotIn('stop',rows[0])
        self.assertAlmostEqual(rows[0]['reference_stop_on_open'],99.6)
        self.assertTrue(all(row['historical_only'] for row in rows))

    def test_recomputed_candidates_detect_silent_omissions(self):
        ts=pd.date_range('2026-03-14',periods=230*288,freq='5min',tz='UTC')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); frames={}; hashes={}
            for sym,step in [('BTCUSDT',.0003),('ETHUSDT',.0008)]:
                p=100+pd.RangeIndex(len(ts))*step
                frames[sym]=pd.DataFrame({'ts':ts,'open':p,'high':p+.02,'low':p-.02,'close':p})
                save=frames[sym].copy();save['ts']=save.ts.astype('int64')//10**6
                path=root/f'{sym}_5m.csv.gz';save.to_csv(path,index=False,compression='gzip')
                hashes[sym]=hashlib.sha256(path.read_bytes()).hexdigest()
            cutoff=ts[-5]; generated=ts[-1]+pd.Timedelta(minutes=6)
            config=Path(__file__).with_name('frozen_config.json');cfg=hashlib.sha256(config.read_bytes()).hexdigest()
            snapshot={'generated_at':generated.isoformat(),'config_sha256':cfg,'btc_data_status':{'status':'FRESH'},'symbols':{}}
            for sym in frames:
                hit,_,_=signals(frames['BTCUSDT'],frames[sym]);rows=signal_records(frames[sym],hit,cutoff)
                snapshot['symbols'][sym]={'data_status':{'status':'FRESH'},'data_sha256':hashes[sym],
                                          'candidate_count':len(rows),'candidate_window_start':cutoff.isoformat(),'signals_recent':rows}
            self.assertGreater(len(snapshot['symbols']['ETHUSDT']['signals_recent']),0)
            events=[]
            for row in snapshot['symbols']['ETHUSDT']['signals_recent']:
                stamp=pd.Timestamp(row['ts']); event=stamp+pd.Timedelta(minutes=5)
                for kind in ('signal','skip'):
                    occurred=event if kind=='signal' else event+pd.Timedelta(seconds=11)
                    observed=event+pd.Timedelta(seconds=10 if kind=='signal' else 12)
                    events.append({'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                                   'symbol':'ETHUSDT','kind':kind,'signal_time_utc':stamp.isoformat(),
                                   'event_time_utc':occurred.isoformat(),'captured_at_utc':observed.isoformat(),
                                   'capture_lag_seconds':(observed-occurred).total_seconds()})
            self.assertEqual(reconcile_signals(snapshot,events,root,config,cutoff)['status'],'PARTIAL')
            after_scan=[dict(x) for x in events]
            after_scan[-2]['event_time_utc']=(generated+pd.Timedelta(seconds=1)).isoformat()
            after_scan[-2]['captured_at_utc']=(generated+pd.Timedelta(seconds=2)).isoformat()
            after_scan[-2]['capture_lag_seconds']=1
            after_scan[-1]['event_time_utc']=(generated+pd.Timedelta(seconds=3)).isoformat()
            after_scan[-1]['captured_at_utc']=(generated+pd.Timedelta(seconds=4)).isoformat()
            after_scan[-1]['capture_lag_seconds']=1
            self.assertEqual(reconcile_signals(snapshot,after_scan,root,config,cutoff)['status'],'INVALID')
            later=reconcile_signals(snapshot,after_scan,root,config,cutoff,evidence_as_of=generated+pd.Timedelta(seconds=5))
            self.assertEqual(later['status'],'PARTIAL',later)
            self.assertEqual(reconcile_signals(snapshot,after_scan,root,config,cutoff,
                evidence_as_of=generated+pd.Timedelta(seconds=3))['status'],'INVALID')
            self.assertEqual(reconcile_signals(snapshot,after_scan,root,config,cutoff,
                evidence_as_of=generated-pd.Timedelta(seconds=1))['status'],'INVALID')
            tied=[dict(x) for x in events];tied[1]['event_time_utc']=tied[0]['captured_at_utc'];tied[1]['captured_at_utc']=tied[0]['captured_at_utc'];tied[1]['capture_lag_seconds']=0
            self.assertEqual(reconcile_signals(snapshot,tied,root,config,cutoff)['status'],'AMBIGUOUS_ORDER')
            reordered=[dict(x) for x in events]
            reordered[0]['captured_at_utc']=(pd.Timestamp(reordered[0]['event_time_utc'])+pd.Timedelta(seconds=20)).isoformat()
            reordered[0]['capture_lag_seconds']=20
            self.assertEqual(reconcile_signals(snapshot,reordered,root,config,cutoff)['status'],'INVALID')
            late=[dict(x) for x in events]
            signal_close=pd.Timestamp(late[0]['event_time_utc']);late_time=signal_close+pd.Timedelta(minutes=15)
            for index in (0,1):
                late[index]['event_time_utc']=late_time.isoformat()
                late[index]['captured_at_utc']=(late_time+pd.Timedelta(seconds=5)).isoformat()
                late[index]['capture_lag_seconds']=5
            self.assertEqual(reconcile_signals(snapshot,late,root,config,cutoff)['status'],'INVALID')
            first=snapshot['symbols']['ETHUSDT']['signals_recent'][0]
            replacement=events[1].copy();replacement.update(kind='entry',trade_id='paper-1',price=first['entry_next_open']*1.0002)
            updated=[events[0],replacement]+events[2:]
            check=reconcile_signals(snapshot,updated,root,config,cutoff)
            self.assertEqual(check['status'],'EXECUTION_MODEL_MISMATCH')
            before_signal=[dict(x) for x in updated]
            before_signal[1]['event_time_utc']=before_signal[0]['event_time_utc'];before_signal[1]['capture_lag_seconds']=12
            self.assertEqual(reconcile_signals(snapshot,before_signal,root,config,cutoff)['status'],'INVALID')
            self.assertAlmostEqual(check['entry_price_differences'][0]['price_difference_bps'],2.0)
            self.assertAlmostEqual(check['entry_price_differences'][0]['stop_on_recorded_entry_unrounded'],replacement['price']*.996)
            duplicates=[dict(x) for x in events]
            for index in (1,3):
                price=snapshot['symbols']['ETHUSDT']['signals_recent'][index//2]['entry_next_open']
                duplicates[index].update(kind='entry',trade_id='duplicate-id',price=price)
            self.assertEqual(reconcile_signals(snapshot,duplicates,root,config,cutoff)['status'],'INVALID')
            pending=events[:-1]+[{**events[-1],'kind':'entry','trade_id':'pending-1','price':100.0}]
            pending_result=reconcile_signals(snapshot,pending,root,config,cutoff)
            self.assertEqual(pending_result['status'],'EXECUTION_MODEL_MISMATCH')
            self.assertEqual(pending_result['pending_reference_count'],1)
            self.assertIsNone(pending_result['entry_price_differences'][0]['price_difference_bps'])
            entry=updated[1]; exit_time=pd.Timestamp(entry['event_time_utc'])+pd.Timedelta(minutes=15)
            exit_event={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                        'symbol':'ETHUSDT','kind':'exit','trade_id':'paper-1','event_time_utc':exit_time.isoformat(),
                        'captured_at_utc':(exit_time+pd.Timedelta(seconds=10)).isoformat(),'capture_lag_seconds':10,
                        'price':entry['price']*1.01}
            trade={'trade_id':'paper-1','entry_time':entry['event_time_utc'],'exit_time':exit_time.isoformat(),
                   'symbol':'ETHUSDT','side':'long','entry':str(entry['price']),'stop':str(entry['price']*.996),
                   'exit':str(exit_event['price']),'qty':'1','equity_at_entry':'2000','fee_cost':'.1',
                   'funding_cost':'.2','five_q_pass':'1','stop_placed':'1','added':'0','reversed':'0','plan_deviation':'0'}
            ledger=reconcile(pd.DataFrame([trade]),updated+[exit_event],cutoff,generated)
            self.assertEqual(ledger['status'],'PARTIAL')
            self.assertEqual(ledger['report_status'],'HOLD')
            # One synthetic position moves through marked-open, funding and closed reports.
            entry_time=pd.Timestamp(entry['event_time_utc']);mark_time=entry_time+pd.Timedelta(minutes=10)
            funding_time=entry_time+pd.Timedelta(minutes=5)
            funding_row={'trade_id':'paper-1','symbol':'ETHUSDT','funding_time':funding_time.isoformat(),
                         'funding_rate':.001,'reference_mark_price':200,'qty':1,'funding_cost':.2,'source':'synthetic'}
            def create_schedule(name,query_end):
                schedule=root/name;schedule.mkdir()
                manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                          'start_utc':(entry_time-pd.Timedelta(minutes=2)).isoformat(),'end_utc_exclusive':query_end.isoformat(),
                          'query_server_time_ms':int((query_end+pd.Timedelta(seconds=1)).timestamp()*1000),
                          'server_time_ms':int((query_end+pd.Timedelta(seconds=2)).timestamp()*1000),
                          'captured_at_utc':(query_end+pd.Timedelta(seconds=3)).isoformat(),'symbols':{}}
                for symbol in ('BTCUSDT','ETHUSDT'):
                    rows=[] if symbol=='BTCUSDT' else [{'symbol':symbol,'fundingTime':int(funding_time.timestamp()*1000),
                                                        'fundingRate':'.001','markPrice':'200'}]
                    raw=json.dumps(rows).encode();(schedule/(symbol+'.json')).write_bytes(raw)
                    manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows)}
                (schedule/'manifest.json').write_text(json.dumps(manifest))
                return schedule
            schedule_open=create_schedule('synthetic-funding-open',mark_time+pd.Timedelta(minutes=1,milliseconds=1))
            schedule_closed=create_schedule('synthetic-funding-closed',exit_time+pd.Timedelta(minutes=1,milliseconds=1))
            open_trade={k:v for k,v in trade.items() if k in OPEN_FIELDS}
            open_trade.update(mark_price=entry['price']*1.005,mark_time=mark_time.isoformat(),mark_source='synthetic',entry_fee='.05')
            open_frame=pd.DataFrame([open_trade]);empty_closed=pd.DataFrame(columns=CLOSED_FIELDS)
            open_asof=mark_time+pd.Timedelta(minutes=2)
            self.assertLess(open_asof,exit_time)
            open_risk=audit_combined_risk(empty_closed,open_frame,cutoff,open_asof)
            self.assertEqual(open_risk['status'],'REVIEW')
            self.assertAlmostEqual(open_risk['open']['unrealized_after_recorded_costs_usdt'],
                                   round(entry['price']*.005-.25,6))
            open_equity=evaluate_paper_equity(empty_closed,open_frame,cutoff,open_asof)
            self.assertEqual(open_equity['status'],'REVIEW')
            self.assertAlmostEqual(open_equity['modeled_equity_usdt'],round(2000+entry['price']*.005-.25,6))
            mark_event={'schema':'paper-event-v1','verification':'MANUAL_UNVERIFIED','config_sha256':cfg,
                        'symbol':'ETHUSDT','kind':'mark','trade_id':'paper-1','event_time_utc':mark_time.isoformat(),
                        'captured_at_utc':(mark_time+pd.Timedelta(seconds=10)).isoformat(),'capture_lag_seconds':10,
                        'price':open_trade['mark_price']}
            open_events=[updated[0],entry,mark_event]
            self.assertEqual(reconcile_positions(empty_closed,open_frame,open_events,cutoff,open_asof)['status'],'PARTIAL')
            # A distinct quote after the signal and before the decision links the
            # synthetic scan, events and open ledger without changing the baseline.
            quote_time=pd.Timestamp(updated[0]['captured_at_utc'])
            ms=lambda n:int((quote_time+pd.Timedelta(milliseconds=n)).timestamp()*1000)
            ask=first['entry_next_open']
            quote={'schema':'paper-quote-research-v1','source':'Binance USD-M public REST',
                   'verification':'PUBLIC_UNVERIFIED','config_sha256':cfg,
                   'requests':[{'local_start_ms':ms(100),'local_end_ms':ms(120),'body':{'serverTime':ms(110)}},
                               {'local_start_ms':ms(200),'local_end_ms':ms(300),'body':{'symbol':'ETHUSDT','time':ms(250),
                                'bidPrice':str(ask-.01),'askPrice':str(ask),'bidQty':'3','askQty':'3'}},
                               {'local_start_ms':ms(400),'local_end_ms':ms(420),'body':{'serverTime':ms(410)}}]}
            candidate_open=open_frame.assign(margin_at_entry=str(entry['price']/5))
            candidate_events=updated+[mark_event]
            quote_map={'paper-1':{'quote':quote,'sha256':'synthetic-quote-hash'}}
            candidate=reconcile_delayed_signal(snapshot,candidate_events,root,empty_closed,candidate_open,quote_map,cutoff,generated)
            self.assertEqual(candidate['status'],'PARTIAL_CANDIDATE_NOT_REGISTERED')
            self.assertEqual(candidate['original_signal_status'],'EXECUTION_MODEL_MISMATCH')
            missing=reconcile_delayed_signal(snapshot,candidate_events,root,empty_closed,candidate_open,{},cutoff,generated)
            self.assertEqual(missing['status'],'UNKNOWN_QUOTE_COVERAGE')
            shallow=copy.deepcopy(quote_map);shallow['paper-1']['quote']['requests'][1]['body']['askQty']='0.5'
            self.assertEqual(reconcile_delayed_signal(snapshot,candidate_events,root,empty_closed,candidate_open,shallow,cutoff,generated)['status'],'UNKNOWN_DEPTH')
            missing_margin=candidate_open.drop(columns='margin_at_entry')
            self.assertEqual(reconcile_delayed_signal(snapshot,candidate_events,root,empty_closed,missing_margin,quote_map,cutoff,generated)['status'],'UNKNOWN_MARGIN')
            second_entry={**events[3], 'kind':'entry', 'trade_id':'paper-2',
                          'price':snapshot['symbols']['ETHUSDT']['signals_recent'][1]['entry_next_open']*1.0002}
            second_time=pd.Timestamp(second_entry['event_time_utc'])+pd.Timedelta(minutes=10)
            second_mark={**mark_event,'trade_id':'paper-2','event_time_utc':second_time.isoformat(),
                         'captured_at_utc':(second_time+pd.Timedelta(seconds=10)).isoformat(),
                         'price':second_entry['price']*1.005}
            second_position=candidate_open.iloc[0].to_dict()
            second_position.update(trade_id='paper-2',entry_time=second_entry['event_time_utc'],
                                   entry=second_entry['price'],stop=second_entry['price']*.996,
                                   mark_time=second_time.isoformat(),mark_price=second_mark['price'],
                                   margin_at_entry=second_entry['price']/5)
            two_events=[*updated[:3],second_entry,*updated[4:],mark_event,second_mark]
            two_positions=pd.concat([candidate_open,pd.DataFrame([second_position])],ignore_index=True)
            reused={**quote_map,'paper-2':{'quote':copy.deepcopy(quote),'sha256':'same-observation'}}
            reused['paper-2']['quote']['requests'][1]['body']['bidQty']='3.1'
            repeated=reconcile_delayed_signal(snapshot,two_events,root,empty_closed,two_positions,reused,cutoff,generated)
            self.assertEqual(repeated['status'],'INVALID')
            self.assertIn('重复使用',repeated['reason'])
            event_dir=root/'candidate-events';event_dir.mkdir()
            for n,event in enumerate(candidate_events):
                (event_dir/f'{n:03}.json').write_text(json.dumps(event))
            (root/'candidate-scan.json').write_text(json.dumps(snapshot))
            (root/'candidate-quote.json').write_text(json.dumps(quote))
            (root/'candidate-quotes.json').write_text(json.dumps({'paper-1':'candidate-quote.json'}))
            empty_closed.to_csv(root/'candidate-closed.csv',index=False)
            candidate_open.to_csv(root/'candidate-open.csv',index=False)
            cmd=['python3','-m','verify.paper_delayed_signal_reconcile',
                 '--scan',str(root/'candidate-scan.json'),'--events',str(event_dir),'--market-dir',str(root),
                 '--closed',str(root/'candidate-closed.csv'),'--open',str(root/'candidate-open.csv'),
                 '--quote-index',str(root/'candidate-quotes.json'),'--start',cutoff.isoformat(),'--as-of',generated.isoformat()]
            cli=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
            self.assertEqual(cli['status'],'PARTIAL_CANDIDATE_NOT_REGISTERED')
            self.assertEqual(cli['input_sha256']['quote_index'],hashlib.sha256((root/'candidate-quotes.json').read_bytes()).hexdigest())
            tied_entry={**entry,'captured_at_utc':mark_event['captured_at_utc'],
                        'capture_lag_seconds':(pd.Timestamp(mark_event['captured_at_utc'])-entry_time).total_seconds()}
            self.assertEqual(reconcile_positions(empty_closed,open_frame,[updated[0],tied_entry,mark_event],cutoff,open_asof)['status'],'AMBIGUOUS_ORDER')
            simultaneous=open_frame.copy();simultaneous.loc[0,'mark_time']=entry_time.isoformat()
            same_time_mark={**mark_event,'event_time_utc':entry_time.isoformat(),
                            'captured_at_utc':(entry_time+pd.Timedelta(seconds=12)).isoformat(),'capture_lag_seconds':12}
            self.assertEqual(reconcile_positions(empty_closed,simultaneous,[updated[0],entry,same_time_mark],cutoff,open_asof)['status'],'AMBIGUOUS_ORDER')
            reverse_entry={**tied_entry,'captured_at_utc':(mark_time+pd.Timedelta(seconds=20)).isoformat(),
                           'capture_lag_seconds':(mark_time+pd.Timedelta(seconds=20)-entry_time).total_seconds()}
            self.assertEqual(reconcile_positions(empty_closed,open_frame,[updated[0],reverse_entry,mark_event],cutoff,open_asof)['status'],'INVALID')
            bad_marks=[*open_events[:-1],{**mark_event,'price':mark_event['price']*1.01}]
            self.assertEqual(reconcile_positions(empty_closed,open_frame,bad_marks,cutoff,open_asof)['status'],'INVALID')
            self.assertEqual(reconcile_positions(empty_closed,open_frame,open_events+[exit_event],cutoff,generated)['status'],'INVALID')
            open_funding=reconcile_funding(empty_closed,open_frame,pd.DataFrame([funding_row]),cutoff,open_asof,schedule=schedule_open)
            self.assertEqual(open_funding['status'],'PARTIAL')
            self.assertEqual(open_funding['open_after_snapshot_unknown'],['paper-1'])
            closed_funding=reconcile_funding(pd.DataFrame([trade]),pd.DataFrame(columns=OPEN_FIELDS),
                                             pd.DataFrame([funding_row]),cutoff,generated,schedule=schedule_closed)
            self.assertEqual(closed_funding['status'],'PARTIAL')
            self.assertEqual(reconcile_positions(pd.DataFrame([trade]),pd.DataFrame(columns=OPEN_FIELDS),
                                                 updated+[mark_event,exit_event],cutoff,generated)['status'],'PARTIAL')
            late_mark={**mark_event,'captured_at_utc':(exit_time+pd.Timedelta(seconds=20)).isoformat(),
                       'capture_lag_seconds':(exit_time+pd.Timedelta(seconds=20)-mark_time).total_seconds()}
            self.assertEqual(reconcile_positions(pd.DataFrame([trade]),pd.DataFrame(columns=OPEN_FIELDS),
                                                 updated+[late_mark,exit_event],cutoff,generated)['status'],'INVALID')
            net=report(pd.DataFrame([trade]),cutoff,generated)
            self.assertAlmostEqual(net['net_pnl_usdt'],round(entry['price']*.01-.3,6))
            closed_equity=evaluate_paper_equity(pd.DataFrame([trade]),pd.DataFrame(columns=OPEN_FIELDS),cutoff,generated)
            self.assertAlmostEqual(closed_equity['modeled_equity_usdt'],round(2000+net['net_pnl_usdt'],6))
            self.assertEqual(reconcile_signals(snapshot,events+[events[0]],root,config,cutoff)['status'],'INVALID')
            self.assertEqual(reconcile_signals(snapshot,events,root,config,cutoff-pd.Timedelta(minutes=5))['status'],'INVALID')
            original=snapshot['symbols']['ETHUSDT']['signals_recent'][0]['reference_stop_on_open']
            snapshot['symbols']['ETHUSDT']['signals_recent'][0]['reference_stop_on_open']=1
            self.assertEqual(reconcile_signals(snapshot,events,root,config,cutoff)['status'],'INVALID')
            snapshot['symbols']['ETHUSDT']['signals_recent'][0]['reference_stop_on_open']=original
            snapshot['symbols']['ETHUSDT']['signals_recent'].pop()
            snapshot['symbols']['ETHUSDT']['candidate_count']-=1
            self.assertEqual(reconcile_signals(snapshot,events,root,config,cutoff)['status'],'INVALID')
            # Once the next candle closes, the same captured entry can be reconciled.
            later={}
            for sym,frame in frames.items():
                last=frame.iloc[-1]; price=float(last.close)
                extra=pd.DataFrame([{'ts':last.ts+pd.Timedelta(minutes=5),'open':price,
                                     'high':price+.02,'low':price-.02,'close':price}])
                later[sym]=pd.concat([frame,extra],ignore_index=True)
                save=later[sym].copy();save['ts']=save.ts.astype('int64')//10**6
                save.to_csv(root/f'{sym}_5m.csv.gz',index=False,compression='gzip')
            snapshot2={'generated_at':(generated+pd.Timedelta(minutes=5)).isoformat(),'config_sha256':cfg,
                       'btc_data_status':{'status':'FRESH'},'symbols':{}}
            for sym in later:
                hit,_,_=signals(later['BTCUSDT'],later[sym]); rows=signal_records(later[sym],hit,cutoff)
                snapshot2['symbols'][sym]={'data_status':{'status':'FRESH'},
                    'data_sha256':hashlib.sha256((root/f'{sym}_5m.csv.gz').read_bytes()).hexdigest(),
                    'candidate_count':len(rows),'candidate_window_start':cutoff.isoformat(),'signals_recent':rows}
            result2=reconcile_signals(snapshot2,pending,root,config,cutoff)
            self.assertEqual(result2['status'],'EXECUTION_MODEL_MISMATCH')
            self.assertEqual(result2['pending_reference_count'],0)
            self.assertIsNotNone(result2['entry_price_differences'][0]['price_difference_bps'])

    def test_staging_replaces_unclosed_tail_without_touching_source(self):
        spec=importlib.util.spec_from_file_location('market_stage',Path(__file__).resolve().parents[1]/'scripts/11_stage_recent_market.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        old=pd.DataFrame([[0,100,101,99,100,1,100],[300000,100,101,99,100,1,100]],columns=module.COLS)
        bars=[[300000,100,102,99,101,1,599999,100],[600000,101,102,100,101,1,899999,100]]
        merged=module.merge_closed(old,bars,700000)
        self.assertEqual(len(merged),2)
        self.assertEqual(int(merged.close.iloc[-1]),101)
        self.assertEqual(int(old.close.iloc[-1]),100)
        with self.assertRaises(ValueError): module.merge_closed(old,bars[1:],700000)

    def test_btc_self_comparison_and_daily_features_are_causal(self):
        ts = pd.date_range('2023-01-01', periods=230 * 288, freq='5min', tz='UTC')
        p = pd.Series(100.0 + pd.RangeIndex(len(ts)) / 10000)
        candles = pd.DataFrame({'ts': ts, 'open': p, 'high': p + 1, 'low': p - 1, 'close': p})
        hit, features, _ = signals(candles, candles)
        self.assertFalse(hit.any())
        candidate,_ = btc_eligible_signals(candles)
        self.assertTrue(candidate.any())
        self.assertTrue((features.rs7.dropna() == 0).all())
        changed = candles.copy()
        day = pd.Timestamp('2023-08-10', tz='UTC')
        changed.loc[changed.ts >= day, 'close'] *= 2
        _, future_features, _ = signals(candles, changed)
        cutoff = candles.ts < day + pd.Timedelta(days=1)
        pd.testing.assert_frame_equal(features.loc[cutoff], future_features.loc[cutoff])

    def test_h2_recapture_is_redundant_after_close_above_previous_close(self):
        low=pd.Series([100.]*20+[99.]);close=pd.Series([101.]*20+[101.5])
        d=pd.DataFrame({'low':low,'close':close})
        base=(d.close>d.close.shift(1)) & (d.low<=d.low.rolling(20).min()*1.001)
        h2=recapture_signals(base.to_numpy(),d)
        self.assertTrue(base.iloc[-1])
        self.assertTrue(h2[-1])
        self.assertTrue((h2[20:] == base.to_numpy()[20:]).all())

    def test_ema_warmup_comparison_uses_full_205_days_and_prior_slope(self):
        daily=pd.Series([100.]*215,index=pd.date_range('2025-01-01',periods=215,freq='D',tz='UTC'))
        full,short,valid=compare_daily(daily)
        self.assertEqual(int(valid.sum()),6)
        self.assertFalse((full[valid]!=short[valid]).any())

    def test_ema_state_changes_affect_next_day_candidates(self):
        pre=pd.Series([True,True]);old=pd.Series([False,True]);days=pd.Series(pd.to_datetime(['2026-01-02','2026-01-03'],utc=True))
        rows=[{'day_utc':'2026-01-01','rolling_205':True},{'day_utc':'2026-01-02','rolling_205':False}]
        self.assertEqual(impact(pre,old,days,rows),{'candidate_added':1,'candidate_removed':1})
        self.assertEqual(old.tolist(),[False,True])

    def test_mark_open_funding_and_ledger_reconcile(self):
        ts = pd.date_range('2024-01-01', periods=4, freq='5min', tz='UTC')
        bars = pd.DataFrame({'ts':ts, 'open':[100]*4, 'high':[101]*4,
                             'low':[100]*4, 'close':[100,101,102,103]})
        funding = pd.DataFrame({'ts':[int(ts[2].timestamp()*1000)], 'funding_rate':[.001]})
        result, closed, opened = replay(bars, [True,False,False,False], pd.Series(dtype=float),
                                       funding, '2024-01-01', '2024-01-01 00:20')
        self.assertEqual((len(closed),len(opened)), (0,1))
        self.assertAlmostEqual(opened[0]['funding_paid'], .75)
        self.assertAlmostEqual(result['equity_end'], 2021.375)
        self.assertAlmostEqual(result['ledger_reconciliation_error'], 0)

    def test_liquidation_stop_ambiguity_is_not_silent(self):
        ts = pd.date_range('2024-01-01', periods=3, freq='5min', tz='UTC')
        bars = pd.DataFrame({'ts':ts,'open':[100]*3,'high':[101]*3,'low':[100,70,100],'close':[100]*3})
        funding = pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        result, closed, opened = replay(bars,[True,False,False],pd.Series(dtype=float),funding,
                                        '2024-01-01','2024-01-01 00:15')
        self.assertEqual(closed[0]['reason'], 'liquidation_proxy')
        self.assertEqual(result['ambiguous_stop_liquidation_bars'],1)
        self.assertAlmostEqual(result['ledger_reconciliation_error'],0)

    def test_structural_stop_is_causal_and_respects_risk_and_nominal_caps(self):
        ts=pd.date_range('2024-01-01',periods=25,freq='5min',tz='UTC')
        bars=pd.DataFrame({'ts':ts,'open':[100.]*25,'high':[101.]*25,'low':[99.]*25,'close':[100.]*25})
        levels=structural_levels(bars)
        self.assertTrue(pd.isna(levels[18]));self.assertEqual(levels[19],99.)
        changed=bars.copy();changed.loc[20,'low']=90.
        self.assertEqual(structural_levels(changed)[19],99.)
        funding=pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        hit=[False]*25;hit[19]=True
        def run(stop):
            candidate=[float('nan')]*25;candidate[19]=stop
            return replay(bars,hit,pd.Series(dtype=float),funding,'2024-01-01','2024-01-01 02:05',
                          risk_basis='initial',structural_stop=candidate)
        result,_,opened=run(96.)
        self.assertEqual(len(opened),1)
        self.assertAlmostEqual(opened[0]['qty']*(opened[0]['entry']-opened[0]['stop']),3.)
        self.assertLess(opened[0]['qty']*opened[0]['entry'],750.)
        result,closed,opened=run(99.8)
        row=closed[0] if closed else opened[0]
        self.assertAlmostEqual(row['qty']*row['entry'],750.)
        self.assertLess(row['qty']*(row['entry']-row['stop']),3.)
        result,closed,opened=run(101.)
        self.assertEqual((len(closed),len(opened),result['skipped_invalid_stop']),(0,0,1))
        self.assertAlmostEqual(result['equity_end'],2000.)
        with self.assertRaises(ValueError):
            replay(bars,hit,pd.Series(dtype=float),funding,'2024-01-01','2024-01-01 02:05',structural_stop=levels)

    def test_fixed_risk_does_not_compound_after_loss(self):
        ts=pd.date_range('2024-01-01',periods=4,freq='5min',tz='UTC')
        bars=pd.DataFrame({'ts':ts,'open':[100]*4,'high':[100]*4,'low':[100,99,100,99],'close':[100]*4})
        funding=pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        args=(bars,[True,False,True,False],pd.Series(dtype=float),funding,'2024-01-01','2024-01-01 00:20')
        _,dynamic,_=replay(*args);_,fixed,_=replay(*args,risk_basis='initial')
        self.assertEqual(len(dynamic),2);self.assertEqual(len(fixed),2)
        self.assertLess(dynamic[1]['qty'],dynamic[0]['qty'])
        self.assertAlmostEqual(fixed[1]['qty'],fixed[0]['qty'])
        self.assertAlmostEqual(fixed[0]['qty']*fixed[0]['entry'],750)
        with self.assertRaises(ValueError): replay(*args,risk_basis='unknown')

    def test_first_entry_fee_counts_in_drawdown(self):
        ts = pd.date_range('2024-01-01', periods=2, freq='5min', tz='UTC')
        bars = pd.DataFrame({'ts':ts,'open':[100,100],'high':[100,100],
                             'low':[100,100],'close':[100,100]})
        funding = pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        result, _, _ = replay(bars,[True,False],pd.Series(dtype=float),funding,
                              '2024-01-01','2024-01-01 00:10')
        self.assertLess(result['mdd_close_5m_pct'], 0)


if __name__ == '__main__':
    unittest.main()
