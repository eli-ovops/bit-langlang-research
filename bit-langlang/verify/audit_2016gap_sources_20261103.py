"""Independent raw response, volume and venue-local 1h-to-4h reconstruction."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
DATA=Path('data/market/btc-2016gap-usd-cross-20261103-01');OUT=Path('data/verify/market-2016gap-source-independent-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    m=json.loads((DATA/'manifest.json').read_text());A=pd.Timestamp(m['start']).value//10**6;B=pd.Timestamp(m['end_exclusive']).value//10**6;files=[Path(__file__),DATA/'manifest.json'];counts={}
    s=[]
    for i,item in enumerate(m['sources']['bitstamp']['requests']):
        p=DATA/f'bitstamp-{i}.json';assert sha(p)==item['sha256'];files.append(p)
        s.extend({'ts':int(r['timestamp'])*1000,**{k:float(r[k]) for k in ('open','high','low','close','volume')}} for r in json.loads(p.read_text())['data']['ohlc'])
    f=pd.DataFrame(s);f=f[(f.ts>=A)&(f.ts<B)].sort_values('ts').reset_index(drop=True);path=DATA/'bitstamp-4h.csv.gz';files.append(path);b=pd.read_csv(path).sort_values('ts').reset_index(drop=True);assert sha(path)==m['sources']['bitstamp']['dataset_sha256'] and len(f)==len(b)==m['sources']['bitstamp']['expected'] and np.array_equal(f.ts,b.ts) and np.allclose(f[['open','high','low','close','volume']],b[['open','high','low','close','volume']],rtol=0,atol=1e-10) and f.volume.gt(0).all();counts['bitstamp_4h']=len(f)
    rows={}
    for i,item in enumerate(m['sources']['bitfinex']['requests']):
        p=DATA/f'bitfinex-1h-{i}.json';assert sha(p)==item['sha256'];files.append(p)
        for r in json.loads(p.read_text()):
            ts=int(r[0]);assert ts not in rows;rows[ts]=[float(r[1]),float(r[3]),float(r[4]),float(r[2]),float(r[5])]
    path=DATA/'bitfinex-4h.csv.gz';files.append(path);h=pd.read_csv(path);assert sha(path)==m['sources']['bitfinex']['dataset_sha256'] and len(h)==m['sources']['bitfinex']['expected']
    for r in h.itertuples():
        z=[rows[int(r.ts+i*3600000)] for i in range(4)];v=[z[0][0],max(q[1] for q in z),min(q[2] for q in z),z[-1][3],sum(q[4] for q in z),min(q[4] for q in z)];assert np.allclose(v,[r.open,r.high,r.low,r.close,r.volume,r.min_hour_volume],rtol=0,atol=1e-9) and min(q[4] for q in z)>0
    assert len(rows)==len(h)*4;counts.update(bitfinex_1h=len(rows),bitfinex_4h=len(h));OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','counts':counts,'scope':'Reported exchange OHLCV and aggregations, not independent verification of every trade.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print('PASS',counts)
if __name__=='__main__':main()
