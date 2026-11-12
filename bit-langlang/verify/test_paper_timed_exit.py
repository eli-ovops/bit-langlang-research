import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .funding_reconcile import FIELDS as FUNDING_FIELDS
from .paper_timed_exit import check, make_observation


class TimedExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        cls.trigger = pd.Timestamp('2026-10-30T00:00:00Z')
        cls.as_of = cls.trigger + pd.Timedelta(minutes=3)
        ts = pd.date_range(end=cls.trigger-pd.Timedelta(minutes=5), periods=206*288, freq='5min')
        frame = pd.DataFrame({'ts': ts.astype('int64')//10**6, 'open': 100., 'high': 101., 'low': 99., 'close': 100.})
        frame.loc[len(frame)-1, ['low', 'close']] = 90.
        stream = io.BytesIO()
        frame.to_csv(stream, index=False, compression='gzip')
        cls.market_raw = stream.getvalue()
        cls.scan = {'generated_at': (cls.trigger+pd.Timedelta(seconds=2)).isoformat(), 'config_sha256': cls.cfg,
                    'symbols': {'ETHUSDT': {'data_status': {'status': 'FRESH'},
                                            'data_sha256': hashlib.sha256(cls.market_raw).hexdigest()}}}
        cls.scan_raw = json.dumps(cls.scan).encode()

    def quote(self, start, bid, ask, bid_qty=5, ask_qty=5):
        def ms(seconds): return int((start+pd.Timedelta(seconds=seconds)).timestamp()*1000)
        return {'schema': 'paper-quote-research-v1', 'source': 'Binance USD-M public REST',
                'verification': 'PUBLIC_UNVERIFIED', 'config_sha256': self.cfg,
                'requests': [{'local_start_ms': ms(0), 'local_end_ms': ms(.02), 'body': {'serverTime': ms(.01)}},
                             {'local_start_ms': ms(.1), 'local_end_ms': ms(.2),
                              'body': {'symbol': 'ETHUSDT', 'time': ms(.15), 'bidPrice': str(bid),
                                       'askPrice': str(ask), 'bidQty': str(bid_qty), 'askQty': str(ask_qty)}},
                             {'local_start_ms': ms(.3), 'local_end_ms': ms(.32), 'body': {'serverTime': ms(.31)}}]}

    def fixture(self, kind):
        base = pd.Timestamp('2026-10-29T12:05:00Z')
        trigger = self.trigger if kind == 'ema20' else base+pd.Timedelta(days=30, seconds=3)
        common = {'schema': 'paper-event-v1', 'verification': 'MANUAL_UNVERIFIED',
                  'config_sha256': self.cfg, 'symbol': 'ETHUSDT'}
        event = lambda kind_, sec, **extra: {**common, 'kind': kind_,
                  'event_time_utc': (base+pd.Timedelta(seconds=sec)).isoformat(),
                  'captured_at_utc': (base+pd.Timedelta(seconds=sec+1)).isoformat(),
                  'capture_lag_seconds': 1, **extra}
        signal_time = (base-pd.Timedelta(minutes=5)).isoformat()
        signal = event('signal', 0, signal_time_utc=signal_time)
        entry = event('entry', 3, trade_id='t1', signal_time_utc=signal_time, price=100.1*1.0002)
        entry_raw = json.dumps(entry).encode()
        observation = make_observation(kind, entry, entry_raw, trigger+pd.Timedelta(seconds=3),
                                       signal_day='2026-10-29' if kind == 'ema20' else None,
                                       scan_raw=self.scan_raw if kind == 'ema20' else None,
                                       market_raw=self.market_raw if kind == 'ema20' else None)
        exit_time = trigger+pd.Timedelta(seconds=6)
        exit_event = {**common, 'kind': 'exit', 'trade_id': 't1', 'price': 100.3*.9998,
                      'event_time_utc': exit_time.isoformat(),
                      'captured_at_utc': (exit_time+pd.Timedelta(seconds=1)).isoformat(), 'capture_lag_seconds': 1}
        qty = 2
        row = {'trade_id': 't1', 'entry_time': entry['event_time_utc'], 'exit_time': exit_event['event_time_utc'],
               'symbol': 'ETHUSDT', 'side': 'long', 'entry': entry['price'], 'stop': entry['price']*.996,
               'exit': exit_event['price'], 'qty': qty, 'equity_at_entry': 2000,
               'fee_cost': qty*(entry['price']+exit_event['price'])*.0005, 'funding_cost': 0,
               'five_q_pass': '1', 'stop_placed': '1', 'added': '0', 'reversed': '0', 'plan_deviation': '0',
               'reference_entry': 100.1, 'reference_exit': 100.3, 'reference_source': 'synthetic bid ask',
               'margin_at_entry': qty*entry['price']/5}
        return {'signal': signal, 'entry': entry, 'entry_raw': entry_raw,
                'entry_quote': self.quote(base+pd.Timedelta(seconds=2), 100, 100.1),
                'observation': observation, 'exit_event': exit_event,
                'exit_quote': self.quote(trigger+pd.Timedelta(seconds=4), 100.3, 100.4),
                'ledger': pd.DataFrame([row]), 'funding': pd.DataFrame(columns=FUNDING_FIELDS),
                'start': '2026-10-29', 'as_of': trigger+pd.Timedelta(minutes=3),
                'scan_raw': self.scan_raw if kind == 'ema20' else None,
                'market_raw': self.market_raw if kind == 'ema20' else None}

    def schedule(self, root, trigger=None):
        end = (trigger or self.trigger)+pd.Timedelta(minutes=2)
        manifest = {'schema': 'paper-funding-snapshot-v2', 'source': 'Binance USD-M public fundingRate',
                    'start_utc': '2026-10-29T00:00:00Z', 'end_utc_exclusive': end.isoformat(),
                    'captured_at_utc': (end+pd.Timedelta(seconds=1)).isoformat(),
                    'query_server_time_ms': int(end.timestamp()*1000),
                    'server_time_ms': int((end+pd.Timedelta(seconds=1)).timestamp()*1000), 'symbols': {}}
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            data = b'[]'; (root/(symbol+'.json')).write_bytes(data)
            manifest['symbols'][symbol] = {'file': symbol+'.json', 'sha256': hashlib.sha256(data).hexdigest(), 'count': 0}
        (root/'manifest.json').write_text(json.dumps(manifest))

    def test_both_exits_reconcile_assumed_costs_and_funding(self):
        for kind in ('ema20', 'max_30d'):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as directory:
                    args = self.fixture(kind)
                    trigger = pd.Timestamp(args['observation']['trigger_time_utc'])
                    self.schedule(Path(directory),trigger)
                    clock = {'clock_for_test':args['as_of']} if kind == 'max_30d' else {}
                    result = check(**args, schedule=directory, **clock)
                    self.assertEqual(result['status'], 'SYNTHETIC_ONLY' if clock else 'PARTIAL_NOT_REGISTERED', result)
                    self.assertEqual(result['exit_kind'], kind)
                    row = args['ledger'].iloc[0]
                    net = (row['exit']-row['entry'])*row['qty']-row['fee_cost']
                    self.assertAlmostEqual(result['report']['net_pnl_usdt'], net, places=6)
                    self.assertAlmostEqual(result['report']['records'][0]['net_R'], net/((row['entry']-row['stop'])*row['qty']), places=6)
                    costs=result['costs_vs_mid_unverified']
                    self.assertAlmostEqual(costs['sampled_spread_cost_usdt'], .2, places=6)
                    self.assertAlmostEqual(costs['mid_reference_gross_pnl_usdt']-costs['total_cost_vs_mid_usdt'], net, places=6)
                    self.assertAlmostEqual(costs['net_pnl_reconciled_usdt'], net, places=6)
                    self.assertGreater(costs['cost_over_positive_mid_gross_pct'],result['report']['cost_over_gross_profit_pct'])
                    self.assertEqual(result['funding_check']['status'], 'PARTIAL')
                    self.assertEqual(check(**args,**clock)['status'], 'UNKNOWN_FUNDING')

    def test_future_incomplete_or_untriggered_ema_rejected(self):
        args = self.fixture('ema20')
        entry, raw = args['entry'], args['entry_raw']
        with self.assertRaises(ValueError):
            make_observation('ema20',entry,raw,self.trigger-pd.Timedelta(seconds=1),signal_day='2026-10-29',scan_raw=self.scan_raw,market_raw=self.market_raw)
        with self.assertRaises(ValueError):
            make_observation('ema20',entry,raw,self.trigger+pd.Timedelta(minutes=16),signal_day='2026-10-29',scan_raw=self.scan_raw,market_raw=self.market_raw)
        with self.assertRaises(ValueError):
            make_observation('ema20',entry,raw,self.trigger+pd.Timedelta(seconds=3),signal_day='2026-10-30',scan_raw=self.scan_raw,market_raw=self.market_raw)
        changed = copy.deepcopy(self.scan); changed['symbols']['ETHUSDT']['data_sha256'] = 'wrong'
        with self.assertRaises(ValueError):
            make_observation('ema20',entry,raw,self.trigger+pd.Timedelta(seconds=3),signal_day='2026-10-29',scan_raw=json.dumps(changed).encode(),market_raw=self.market_raw)
        frame=pd.read_csv(io.BytesIO(self.market_raw),compression='gzip');frame.loc[len(frame)-1,'close']=100
        stream=io.BytesIO();frame.to_csv(stream,index=False,compression='gzip');unchanged=stream.getvalue()
        changed['symbols']['ETHUSDT']['data_sha256']=hashlib.sha256(unchanged).hexdigest()
        with self.assertRaisesRegex(ValueError, '未低于'):
            make_observation('ema20',entry,raw,self.trigger+pd.Timedelta(seconds=3),signal_day='2026-10-29',scan_raw=json.dumps(changed).encode(),market_raw=unchanged)
        frame=frame.drop(index=100)
        stream=io.BytesIO();frame.to_csv(stream,index=False,compression='gzip');gapped=stream.getvalue()
        changed['symbols']['ETHUSDT']['data_sha256']=hashlib.sha256(gapped).hexdigest()
        with self.assertRaisesRegex(ValueError, '缺口'):
            make_observation('ema20',entry,raw,self.trigger+pd.Timedelta(seconds=3),signal_day='2026-10-29',scan_raw=json.dumps(changed).encode(),market_raw=gapped)

    def test_no_backdated_exit_shallow_book_or_wrong_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            self.schedule(Path(directory));args=self.fixture('ema20')
            invalid=copy.deepcopy(args);invalid['exit_quote']['requests'][0]['local_start_ms']-=5000
            self.assertEqual(check(**invalid,schedule=directory)['status'],'INVALID')
            shallow=copy.deepcopy(args);shallow['exit_quote']['requests'][1]['body']['bidQty']='1'
            self.assertEqual(check(**shallow,schedule=directory)['status'],'UNKNOWN_DEPTH')
            invalid=copy.deepcopy(args);invalid['ledger'].loc[0,'fee_cost']=0
            self.assertEqual(check(**invalid,schedule=directory)['status'],'INVALID')
            invalid=copy.deepcopy(args);invalid['ledger'].loc[0,'reference_exit']=100.4
            self.assertEqual(check(**invalid,schedule=directory)['status'],'INVALID')
            invalid=copy.deepcopy(args);invalid['observation']['daily_close']=1
            self.assertEqual(check(**invalid,schedule=directory)['status'],'INVALID')
            invalid=copy.deepcopy(args);invalid['ledger'].loc[0,'funding_cost']=1
            self.assertEqual(check(**invalid,schedule=directory)['status'],'INVALID')
            wrong_trade=copy.deepcopy(args)
            wrong_trade['funding']=pd.DataFrame([{'trade_id':'different'}],columns=FUNDING_FIELDS)
            self.assertEqual(check(**wrong_trade,schedule=directory)['status'],'INVALID')
            missing_fields=copy.deepcopy(args);missing_fields['funding']=pd.DataFrame()
            self.assertEqual(check(**missing_fields)['status'],'INVALID')
            missing_margin=copy.deepcopy(args);missing_margin['ledger']=missing_margin['ledger'].drop(columns='margin_at_entry')
            self.assertEqual(check(**missing_margin,schedule=directory)['status'],'UNKNOWN_MARGIN')

    def test_cli_ema_synthetic_chain(self):
        args = self.fixture('ema20')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schedule=root/'funding-snapshot';schedule.mkdir();self.schedule(schedule)
            paths={'signal':args['signal'],'entry':args['entry'],'entry-quote':args['entry_quote'],
                   'observation':args['observation'],'exit':args['exit_event'],'exit-quote':args['exit_quote']}
            for name, value in paths.items():
                (root/(name+'.json')).write_text(json.dumps(value))
            # The observation binds exact bytes, not just the JSON object.
            (root/'entry.json').write_bytes(args['entry_raw'])
            args['ledger'].to_csv(root/'ledger.csv',index=False)
            args['funding'].to_csv(root/'funding.csv',index=False)
            (root/'scan.json').write_bytes(self.scan_raw)
            (root/'ETHUSDT_5m.csv.gz').write_bytes(self.market_raw)
            cmd=[sys.executable,'-m','verify.paper_timed_exit','check']
            for name in paths: cmd.extend(['--'+name,str(root/(name+'.json'))])
            cmd.extend(['--ledger',str(root/'ledger.csv'),'--funding',str(root/'funding.csv'),
                        '--scan',str(root/'scan.json'),'--market-dir',str(root),'--schedule',str(schedule),
                        '--start',args['start'],'--as-of',args['as_of'].isoformat()])
            result=json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True).stdout)
        self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED',result)
        self.assertEqual(result['input_sha256']['market'],hashlib.sha256(self.market_raw).hexdigest())

    def test_nonpositive_mid_gross_has_no_cost_profit_ratio(self):
        args=self.fixture('ema20')
        args['exit_quote']=self.quote(self.trigger+pd.Timedelta(seconds=4),99.9,100.0)
        args['exit_event']['price']=99.9*.9998
        args['ledger'].loc[0,'exit']=args['exit_event']['price']
        args['ledger'].loc[0,'reference_exit']=99.9
        args['ledger'].loc[0,'fee_cost']=2*(args['entry']['price']+args['exit_event']['price'])*.0005
        with tempfile.TemporaryDirectory() as directory:
            self.schedule(Path(directory))
            result=check(**args,schedule=directory)
        self.assertEqual(result['status'],'PARTIAL_NOT_REGISTERED')
        self.assertLess(result['costs_vs_mid_unverified']['mid_reference_gross_pnl_usdt'],0)
        self.assertIsNone(result['costs_vs_mid_unverified']['cost_over_positive_mid_gross_pct'])

    def test_30_day_trigger_uses_exact_entry_timestamp(self):
        args=self.fixture('max_30d');entry=args['entry'];raw=args['entry_raw']
        trigger=pd.Timestamp(entry['event_time_utc'])+pd.Timedelta(days=30)
        self.assertEqual(pd.Timestamp(args['observation']['trigger_time_utc']),trigger)
        with self.assertRaises(ValueError): make_observation('max_30d',entry,raw,trigger-pd.Timedelta(seconds=1))
        with self.assertRaises(ValueError): make_observation('max_30d',entry,raw,trigger+pd.Timedelta(minutes=16))
        self.assertEqual(check(**args)['status'], 'INVALID')  # Future data cannot pass the real-clock gate.


if __name__ == '__main__':
    unittest.main()
