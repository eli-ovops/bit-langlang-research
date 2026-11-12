"""Retain BTC/USD venue responses and reported volume, without cross-venue fills."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read

OUT=Path('data/market/btc-2025q2-usd-cross-20261104-01');A=pd.Timestamp('2025-02-01',tz='UTC');B=pd.Timestamp('2025-08-01',tz='UTC')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir();items=[];receipts=[];cut=B
    for i in range(3):
        par={'step':14400,'limit':1000,'end':int(cut.timestamp())};r=requests.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=par,timeout=50);r.raise_for_status();p=OUT/f'bitstamp-{i}.json';p.write_bytes(r.content);z=r.json()['data']['ohlc'];assert z;receipts.append({'url':r.url,'sha256':sha(p),'rows':len(z)});items.extend({'ts':int(x['timestamp'])*1000,**{k:float(x[k]) for k in ('open','high','low','close','volume')}} for x in z);cut=pd.Timestamp(min(int(x['timestamp']) for x in z),unit='s',tz='UTC')-pd.Timedelta(seconds=1)
        if cut<A:break
    s=pd.DataFrame(items).sort_values('ts');s=s[(s.ts>=int(A.timestamp()*1000))&(s.ts<int(B.timestamp()*1000))];assert not s.ts.duplicated().any() and np.isfinite(s.volume).all() and s.volume.ge(0).all();s.to_csv(OUT/'bitstamp-4h.csv.gz',index=False,compression='gzip')
    cuts=pd.to_datetime(['2025-02-01','2025-03-01','2025-04-01','2025-08-01'],utc=True);chunks=[];receipts2=[]
    for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
        par={'start':int(a.timestamp()*1000),'end':int(b.timestamp()*1000)-1,'limit':10000,'sort':1};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=par,timeout=60);r.raise_for_status();p=OUT/f'bitfinex-1h-{i}.json';p.write_bytes(r.content);z=r.json();assert isinstance(z,list) and (not z or isinstance(z[0],list));f=pd.DataFrame(z,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric);assert (f.ts>=int(a.timestamp()*1000)).all() and (f.ts<int(b.timestamp()*1000)).all() and (f.ts%3600000==0).all();chunks.append(f);receipts2.append({'url':r.url,'sha256':sha(p),'rows':len(f)})
    g=pd.concat(chunks,ignore_index=True).sort_values('ts');v=g[['open','high','low','close']];assert not g.ts.duplicated().any() and np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (g.low<=v.min(axis=1)).all() and (g.high>=v.max(axis=1)).all() and np.isfinite(g.volume).all() and g.volume.ge(0).all();g.to_csv(OUT/'bitfinex-1h.csv.gz',index=False,compression='gzip');g.index=pd.to_datetime(g.ts,unit='ms',utc=True);h=g.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),min_hour_volume=('volume','min'),n=('ts','size'));h=h[h.n==4].copy();h['ts']=h.index.asi8//1000000;h[['ts','open','high','low','close','volume','min_hour_volume']].to_csv(OUT/'bitfinex-4h.csv.gz',index=False,compression='gzip')
    expected=pd.date_range(A,B-pd.Timedelta(hours=4),freq='4h');source={}
    for name in ('bitstamp','bitfinex'):
        p=OUT/(name+'-4h.csv.gz');_,f=read(p);missing=expected.difference(f.index);vol='volume' if name=='bitstamp' else 'min_hour_volume';source[name]={'bars':len(f),'expected':len(expected),'missing_utc':[x.isoformat() for x in missing],'invalid_ohlc':int((~f.good).sum()),'nonpositive_volume_4h':int(f[vol].le(0).sum()),'dataset_sha256':sha(p),'requests':receipts if name=='bitstamp' else receipts2}
    source['bitfinex']['hourly_sha256']=sha(OUT/'bitfinex-1h.csv.gz');source['bitfinex']['hourly_rows']=len(g);source['bitfinex']['zero_hourly']=int(g.volume.eq(0).sum());(OUT/'manifest.json').write_text(json.dumps({'start':A.isoformat(),'end_exclusive':B.isoformat(),'sources':source,'code_sha256':sha(Path(__file__))},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid_ohlc'],v['nonpositive_volume_4h']) for k,v in source.items()})
if __name__=='__main__':main()
