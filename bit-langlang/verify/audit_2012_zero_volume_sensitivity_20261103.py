"""Independently enumerate raw response volume and sensitive calendar windows."""
from pathlib import Path
import hashlib,json
import pandas as pd

DATA=Path('data/market/btc-2012year-usd-cross-20261103-01');SRC=Path('data/verify/market-2012-zero-volume-sensitivity-20261103-01');OUT=Path('data/verify/market-2012-zero-volume-independent-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    manifest=json.loads((DATA/'manifest.json').read_text());allbars={};files=[Path(__file__),DATA/'manifest.json',SRC/'sensitivity.csv',SRC/'zero_volume_bars.csv']
    for i,item in enumerate(manifest['sources']['bitstamp']['requests']):
        p=DATA/f'bitstamp-{i}.json';assert sha(p)==item['sha256'];files.append(p)
        for x in json.loads(p.read_text())['data']['ohlc']:
            ts=int(x['timestamp']);assert ts not in allbars;allbars[ts]=float(x['volume'])
    A=int(pd.Timestamp(manifest['start']).timestamp());B=int(pd.Timestamp(manifest['end_exclusive']).timestamp());raw={k:v for k,v in allbars.items() if A<=k<B};assert len(raw)==2748
    z={pd.Timestamp(k,unit='s',tz='UTC').floor('D') for k,v in raw.items() if v==0};saved=pd.read_csv(SRC/'zero_volume_bars.csv');assert set(saved.ts//1000)=={k for k,v in raw.items() if v==0}
    x=pd.read_csv(SRC/'sensitivity.csv');assert len(x)==366
    for r in x.itertuples():
        t=pd.Timestamp(r.as_of_utc);assert bool(r.clean_prior_57)==all(t-pd.Timedelta(days=i) not in z for i in range(1,58));assert bool(r.clean_future_7)==all(t+pd.Timedelta(days=i) not in z for i in range(7));assert bool(r.clean_future_28)==all(t+pd.Timedelta(days=i) not in z for i in range(28))
    OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'status':'PASS','raw_bars':len(raw),'zero_bars':sum(v==0 for v in raw.values()),'zero_days':len(z),'points':len(x),'scope':'Independent zero-volume set and strict window coverage; does not establish invalid prices or season truth.','input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print('PASS',len(raw),sum(v==0 for v in raw.values()),len(z),len(x))
if __name__=='__main__':main()
