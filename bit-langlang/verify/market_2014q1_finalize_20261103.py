"""Finalize independently saved official responses after the Python TLS EOF."""
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import read

D=Path('data/market/btc-2014q1-usd-cross-20261102-01')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (D/'manifest.json').exists() and not (D/'bitfinex-4h.csv.gz').exists()
    start=pd.Timestamp('2013-11-01',tz='UTC'); end=pd.Timestamp('2014-05-08',tz='UTC')
    raw=D/'bitfinex-1h-curl.json'; items=json.loads(raw.read_text())
    g=pd.DataFrame(items,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).sort_values('ts')
    v=g[['open','high','low','close']]
    assert not g.ts.duplicated().any() and (g.ts%3600000==0).all() and (g.ts>=start.timestamp()*1000).all() and (g.ts<end.timestamp()*1000).all() and np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (g.low<=v.min(axis=1)).all() and (g.high>=v.max(axis=1)).all()
    g.index=pd.to_datetime(g.ts,unit='ms',utc=True)
    h=g.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'))
    h=h[h.n==4].copy();h['ts']=h.index.asi8//1000000;h[['ts','open','high','low','close']].to_csv(D/'bitfinex-4h.csv.gz',index=False,compression='gzip')
    expected=pd.date_range(start,end-pd.Timedelta(hours=4),freq='4h');src={}
    for name in ('bitstamp','bitfinex'):
        path=D/(name+'-4h.csv.gz'); _,x=read(path); missing=expected.difference(x.index)
        assert x.index.difference(expected).empty
        src[name]={'bars':len(x),'expected':len(expected),'missing_utc':[t.isoformat() for t in missing],'invalid_bars':int((~x.good).sum()),'dataset_sha256':sha(path)}
    src['bitstamp']['raw_sha256']={p.name:sha(p) for p in sorted(D.glob('bitstamp-*.json'))}
    src['bitfinex'].update(raw_sha256=sha(raw),raw_1h_rows=len(g),request_url='https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist?start=1383264000000&end=1399507199999&limit=10000&sort=1',retrieval='curl strict TLS after Python requests SSLEOFError')
    (D/'manifest.json').write_text(json.dumps({'start':start.isoformat(),'end_exclusive':end.isoformat(),'sources':src},indent=2)+'\n')
    print({k:(v['bars'],len(v['missing_utc']),v['invalid_bars']) for k,v in src.items()})
if __name__=='__main__':main()
