import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/verify/cycle-recent-four-days-20261109-01'
T0 = datetime(2026, 11, 6, tzinfo=timezone.utc)
T1 = datetime(2026, 11, 9, tzinfo=timezone.utc)
START = T0-timedelta(days=56)
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


def valid(row):
    o,h,l,c,v = row
    return all(math.isfinite(x) and x > 0 for x in row) and l <= min(o,c) <= max(o,c) <= h


def collect():
    calls = {
        'kraken': ('https://api.kraken.com/0/public/OHLC', {'pair':'XBTUSD','interval':240,'since':int(START.timestamp())}),
        'bitfinex': ('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist', {'start':int(START.timestamp()*1000),'end':int(T1.timestamp()*1000)-1,'limit':10000,'sort':1}),
    }
    OUT.mkdir(parents=True,exist_ok=False)
    audit, sources = {}, {}
    for source,(url,params) in calls.items():
        try:
            response = requests.get(url,params=params,timeout=35)
            response.raise_for_status()
            payload=response.json()
            (OUT/f'{source}-response.json').write_bytes(response.content)
            if source == 'kraken':
                if payload['error']:
                    raise ValueError(str(payload['error']))
                keys=[k for k in payload['result'] if k != 'last']
                if len(keys)!=1:
                    raise ValueError('unexpected Kraken pair')
                raw=[(datetime.fromtimestamp(int(x[0]),timezone.utc),[float(x[i]) for i in (1,2,3,4,6)]) for x in payload['result'][keys[0]]]
            else:
                if not isinstance(payload,list) or any(not isinstance(x,list) or len(x)<6 for x in payload):
                    raise ValueError('unexpected Bitfinex payload')
                raw=[(datetime.fromtimestamp(int(x[0])/1000,timezone.utc),[float(x[i]) for i in (1,3,4,2,5)]) for x in payload]
            rows={}
            for ts,values in raw:
                if START <= ts < T1:
                    if ts in rows: raise ValueError('duplicate timestamp')
                    rows[ts]=values if valid(values) else None
            if source == 'bitfinex':
                bars={}
                for i in range(int((T1-START).total_seconds()//(4*3600))):
                    t=START+4*HOUR*i; vals=[rows.get(t+j*HOUR) for j in range(4)]
                    if all(v is not None for v in vals):
                        bars[t]=[vals[0][0],max(v[1] for v in vals),min(v[2] for v in vals),vals[-1][3],sum(v[4] for v in vals)]
            else:
                bars={t:v for t,v in rows.items() if v is not None}
            sources[source]=bars
            expected=[START+4*HOUR*i for i in range(int((T1-START).total_seconds()//(4*3600)))]
            missing=[t.isoformat() for t in expected if t not in bars]
            audit[source]={'http_status':response.status_code,'response_sha256':hashlib.sha256(response.content).hexdigest(), 'expected_4h':len(expected),'valid_4h':len(expected)-len(missing),'missing_or_invalid':missing}
            with (OUT/f'{source}-4h.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['time_utc','open','high','low','close','volume'])
                for t in sorted(bars):w.writerow([t.isoformat(),*bars[t]])
        except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
            audit[source]={'status':'UNKNOWN','error':f'{type(exc).__name__}: {exc}'}
    result=[]
    for day in range(4):
        t=T0+day*DAY
        for source in calls:
            bars=sources.get(source,{})
            daily=[]
            for i in range(56,0,-1):
                d=t-i*DAY; v=[bars.get(d+4*j*HOUR) for j in range(6)]
                daily.append(None if any(x is None for x in v) else {'high':max(x[1] for x in v),'low':min(x[2] for x in v),'close':v[-1][3]})
            row={'as_of_utc':t.isoformat(),'source':source,'phase':'UNKNOWN','sentiment':'UNKNOWN'}
            for n in (56,28,8):
                window=daily[-n:]
                if any(x is None for x in window):
                    row.update({f'high{n}':'UNKNOWN',f'low{n}':'UNKNOWN'})
                else:
                    row.update({f'high{n}':max(x['high'] for x in window),f'low{n}':min(x['low'] for x in window)})
            row['close']=daily[-1]['close'] if daily[-1] else 'UNKNOWN'
            row['close_8d_ago']=daily[-9]['close'] if daily[-9] else 'UNKNOWN'
            row['position28']='UNKNOWN' if row['close']=='UNKNOWN' or row['high28']=='UNKNOWN' else 'ABOVE' if row['close']>row['high28'] else 'BELOW' if row['close']<row['low28'] else 'INSIDE'
            # The contemporaneous last close is part of the 28-day range; use the range as position context, not a breakout test.
            if row['position28']=='INSIDE' and row['high28'] != row['low28']:
                row['range28_pct']=100*(row['close']-row['low28'])/(row['high28']-row['low28'])
            else: row['range28_pct']='UNKNOWN'
            result.append(row)
    with (OUT/'asof.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    audit['protocol_sha256']=hashlib.sha256((ROOT/'docs/浪浪周期-冻结后新增四日研究口径-20261109.md').read_bytes()).hexdigest()
    (OUT/'summary.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'audit':audit,'rows':result},indent=2,ensure_ascii=False))


if __name__ == '__main__':
    assert valid([10,12,9,11,1]) and not valid([10,9,8,11,1]) and not valid([10,12,9,11,0])
    collect()
