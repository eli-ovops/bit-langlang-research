import gzip
import json
import unittest

import pandas as pd

from .paper_scan_once import STEP
from .paper_scan_source_reconcile import transition
from .paper_scan_source_independent import compare


class SourceReplayTests(unittest.TestCase):
    def test_replay_exact_csv_and_detect_changed_market_or_request(self):
        server=int(pd.Timestamp('2026-10-30T00:15:00Z').timestamp()*1000)
        last=server-2*STEP
        ts=range(last-(205*288-1)*STEP,last+STEP,STEP)
        csv=b'ts,open,high,low,close,volume,turnover\n'+b''.join(
            f'{stamp},100,101,99,100,10,1000\n'.encode() for stamp in ts)
        next_row=f'{last+STEP},100,101,99,100,10,1000\n'.encode()
        previous={s:gzip.compress(csv,mtime=0) for s in ('BTCUSDT','ETHUSDT')}
        current={s:gzip.compress(csv+next_row,mtime=0) for s in previous}
        files={}
        def put(name,params,body,start):
            files[name+'.request.json']=json.dumps({'params':params,'local_start_ms':start,
                                                     'local_end_ms':start+100}).encode()
            files[name+'.body.json']=json.dumps(body).encode()
        put('server-time',{}, {'serverTime':server},server-1000)
        def kline(t):return [t,'100','101','99','100','10',t+STEP-1,'1000']
        for offset,symbol in enumerate(('BTCUSDT','ETHUSDT')):
            put(symbol+'-000',{'symbol':symbol,'interval':'5m','startTime':last,'endTime':server,'limit':1000},
                [kline(last),kline(last+STEP)],server-800+offset*200)
        generated=pd.to_datetime(server+1000,unit='ms',utc=True)
        self.assertEqual(transition(previous,current,files,generated),{'BTCUSDT':1,'ETHUSDT':1})
        self.assertEqual(compare(previous,current,files,generated),{'BTCUSDT':1,'ETHUSDT':1})
        altered=dict(current);altered['ETHUSDT']=gzip.compress(csv+next_row.replace(b',100,10,1000',b',100.1,10,1000'),mtime=0)
        with self.assertRaisesRegex(ValueError,'不一致'):
            transition(previous,altered,files,generated)
        with self.assertRaisesRegex(ValueError,'不一致'):
            compare(previous,altered,files,generated)
        changed=dict(files);meta=json.loads(changed['BTCUSDT-000.request.json']);meta['params']['startTime']+=STEP
        changed['BTCUSDT-000.request.json']=json.dumps(meta).encode()
        with self.assertRaisesRegex(ValueError,'分页参数'):
            transition(previous,current,changed,generated)
        with self.assertRaisesRegex(ValueError,'分页参数'):
            compare(previous,current,changed,generated)
        with self.assertRaisesRegex(ValueError,'晚于扫描'):
            transition(previous,current,files,pd.to_datetime(server-700,unit='ms',utc=True))
        with self.assertRaisesRegex(ValueError,'晚于扫描'):
            compare(previous,current,files,pd.to_datetime(server-700,unit='ms',utc=True))


if __name__=='__main__':
    unittest.main()
