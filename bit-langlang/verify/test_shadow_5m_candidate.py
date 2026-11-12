import tempfile
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from .shadow_5m_candidate import evaluate


class ShadowCandidateTest(unittest.TestCase):
    def test_delayed_entry_pending_stop_exit_and_no_future_leak(self):
        start=pd.Timestamp('2026-10-01T00:00:00Z');warm=205*288
        ts=pd.date_range(start-pd.Timedelta(days=205),periods=warm+8,freq='5min')
        frame=pd.DataFrame({'ts':ts.astype('int64')//10**6,'open':100.,'high':101.,'low':99.9,'close':100.})
        # Signal at start+5m; entry at +15m, trigger at +20m, exit at +25m.
        frame.loc[warm+4,'low']=99.5
        frame.loc[warm+5,['open','low']]=[99.,98.9]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for symbol in ('BTCUSDT','ETHUSDT'):
                frame.to_csv(root/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
            funding=root/'funding.csv';funding.write_text('ts,funding_rate\n')
            def fake_signals(btc,eth):
                hit=np.zeros(len(eth),dtype=bool);hit[warm-1]=True;hit[warm+1]=True
                return hit,None,pd.Series(dtype=float)
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                pending=evaluate(root,funding,start,start+pd.Timedelta(minutes=25),now=start+pd.Timedelta(hours=1))
                done=evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            self.assertEqual(pending['status'],'SHADOW_NOT_REGISTERED')
            self.assertEqual(pending['funding_coverage'],'UNKNOWN')
            self.assertEqual(pending['candidates'],1)
            self.assertEqual(len(pending['closed']),0)
            self.assertEqual(len(pending['open']),1)
            self.assertTrue(pending['open'][0]['pending_stop'])
            self.assertEqual(len(done['closed']),1)
            row=done['closed'][0]
            self.assertEqual(pd.Timestamp(row['entry_ts']),start+pd.Timedelta(minutes=15))
            self.assertEqual(pd.Timestamp(row['exit_ts']),start+pd.Timedelta(minutes=25))
            self.assertEqual(row['reason'],'stop_next_open')
            expected=(99*.9998-100*1.0002)*row['qty']-row['entry_fee']-row['exit_fee']
            self.assertAlmostEqual(row['net_pnl'],expected)
            self.assertAlmostEqual(row['net_R'],expected/((row['entry']-row['stop'])*row['qty']))
            funding_time=int((start+pd.Timedelta(minutes=20)).timestamp()*1000)
            future_time=int((start+pd.Timedelta(minutes=35)).timestamp()*1000)
            funding.write_text(f'ts,funding_rate\n{funding_time},0.001\n{future_time},0.002\n')
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                paid=evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            self.assertAlmostEqual(paid['closed'][0]['funding_paid'],row['qty']*100*.001)
            self.assertAlmostEqual(paid['closed'][0]['net_pnl'],row['net_pnl']-row['qty']*100*.001)
            snapshot=root/'schedule';snapshot.mkdir()
            schedule_end=start+pd.Timedelta(minutes=30)
            manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
                      'start_utc':start.isoformat(),'end_utc_exclusive':schedule_end.isoformat(),
                      'captured_at_utc':(schedule_end+pd.Timedelta(seconds=32)).isoformat(),
                      'query_server_time_ms':int((schedule_end+pd.Timedelta(seconds=30)).timestamp()*1000),
                      'server_time_ms':int((schedule_end+pd.Timedelta(seconds=31)).timestamp()*1000),'symbols':{}}
            def set_snapshot(symbol,entries):
                raw=json.dumps(entries).encode();(snapshot/(symbol+'.json')).write_bytes(raw)
                manifest['symbols'][symbol]={'file':symbol+'.json','sha256':hashlib.sha256(raw).hexdigest(),'count':len(entries)}
                (snapshot/'manifest.json').write_text(json.dumps(manifest))
            set_snapshot('BTCUSDT',[])
            set_snapshot('ETHUSDT',[{'symbol':'ETHUSDT','fundingTime':funding_time,'fundingRate':'0.001','markPrice':'101'}])
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                covered=evaluate(root,funding,start,schedule_end,now=start+pd.Timedelta(hours=1),schedule_path=snapshot)
            self.assertEqual(covered['funding_coverage'],'PARTIAL_PUBLIC_RATE_COVERAGE_UNVERIFIED')
            self.assertEqual(covered['closed'],paid['closed'])
            # The model still uses the 5m open (100), not the public mark (101).
            self.assertAlmostEqual(covered['closed'][0]['funding_paid'],row['qty']*100*.001)
            manifest['start_utc']=(start+pd.Timedelta(minutes=5)).isoformat()
            (snapshot/'manifest.json').write_text(json.dumps(manifest))
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                incomplete=evaluate(root,funding,start,schedule_end,now=start+pd.Timedelta(hours=1),schedule_path=snapshot)
            self.assertEqual(incomplete['funding_coverage'],'UNKNOWN_INCOMPLETE_SNAPSHOT')
            manifest['start_utc']=start.isoformat()
            set_snapshot('ETHUSDT',[{'symbol':'ETHUSDT','fundingTime':funding_time,'fundingRate':'0.002','markPrice':'101'}])
            with self.assertRaisesRegex(ValueError,'快照不一致'):
                evaluate(root,funding,start,schedule_end,now=start+pd.Timedelta(hours=1),schedule_path=snapshot)
            with self.assertRaisesRegex(ValueError,'采集晚于检查时间'):
                evaluate(root,funding,start,schedule_end,now=schedule_end,schedule_path=snapshot)
            set_snapshot('ETHUSDT',[{'symbol':'ETHUSDT','fundingTime':funding_time,'fundingRate':'0.001','markPrice':'101'}])
            def mutate_snapshot(btc,eth):
                result=fake_signals(btc,eth)
                (snapshot/'ETHUSDT.json').write_text('[]')
                return result
            with patch('verify.shadow_5m_candidate.signals',side_effect=mutate_snapshot):
                with self.assertRaisesRegex(ValueError,'资金费快照发生变化'):
                    evaluate(root,funding,start,schedule_end,now=start+pd.Timedelta(hours=1),schedule_path=snapshot)
            funding.write_text(f'ts,funding_rate\n{funding_time},-0.001\n{future_time},0.002\n')
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                received=evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            self.assertAlmostEqual(received['closed'][0]['funding_paid'],-row['qty']*100*.001)
            self.assertAlmostEqual(received['closed'][0]['net_pnl'],row['net_pnl']+row['qty']*100*.001)
            funding.write_text('ts,funding_rate\n')
            # Alter a future closed-candle price; results at the earlier end must remain stable.
            frame.loc[warm+7,'close']=100.5
            for symbol in ('BTCUSDT','ETHUSDT'):
                frame.to_csv(root/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
            with patch('verify.shadow_5m_candidate.signals',side_effect=fake_signals):
                again=evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            self.assertEqual(again['closed'],done['closed'])
            self.assertEqual(again['metrics'],done['metrics'])
            with self.assertRaises(ValueError):
                evaluate(root,funding,start,start+pd.Timedelta(hours=2),now=start+pd.Timedelta(hours=1))
            funding.write_text('ts,funding_rate\n1000,0.01\n1000,0.02\n')
            with self.assertRaises(ValueError):
                evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            funding.write_text('ts,funding_rate\n999999999999999,0.01\n')
            with self.assertRaises(ValueError):
                evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))
            funding.write_text('ts,funding_rate\n')
            def mutate_input(btc,eth):
                result=fake_signals(btc,eth)
                funding.write_text('ts,funding_rate\n1000,0.01\n')
                return result
            with patch('verify.shadow_5m_candidate.signals',side_effect=mutate_input):
                with self.assertRaisesRegex(ValueError,'输入文件发生变化'):
                    evaluate(root,funding,start,start+pd.Timedelta(minutes=30),now=start+pd.Timedelta(hours=1))


if __name__=='__main__':unittest.main()
