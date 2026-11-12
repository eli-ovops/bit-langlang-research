"""Preserve same-venue 1h chunks and compare with earlier response."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read
OLD=Path('data/market/btc-2013spr-usd-cross-20261102-01');OUT=Path('data/market/btc-2013sprchunk-usd-cross-20261103-01');SPEC=Path('docs/2013春小时数据分页补查-事前定义-20261103.md')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir();cuts=pd.to_datetime(['2013-01-15','2013-02-01','2013-03-01','2013-04-01','2013-07-01'],utc=True);frames=[];receipts=[]
    for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
        params={'start':int(a.timestamp()*1000),'end':int(b.timestamp()*1000)-1,'limit':10000,'sort':1};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=params,timeout=60);r.raise_for_status();p=OUT/f'bitfinex-1h-{i}.json';p.write_bytes(r.content);z=r.json();assert isinstance(z,list) and (not z or isinstance(z[0],list));f=pd.DataFrame(z,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric);assert (f.ts>=int(a.timestamp()*1000)).all() and (f.ts<int(b.timestamp()*1000)).all() and (f.ts%3600000==0).all();frames.append(f);receipts.append({'url':r.url,'sha256':sha(p),'rows':len(f),'start':a.isoformat(),'end_exclusive':b.isoformat()})
    g=pd.concat(frames,ignore_index=True).sort_values('ts');assert not g.ts.duplicated().any();v=g[['open','high','low','close']];assert np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (g.low<=v.min(axis=1)).all() and (g.high>=v.max(axis=1)).all() and np.isfinite(g.volume).all() and g.volume.ge(0).all()
    previous=pd.DataFrame(json.loads((OLD/'bitfinex-1h.json').read_text()),columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric);overlap=g.merge(previous,on='ts',suffixes=('_new','_old'));diff=np.zeros(len(overlap),dtype=bool)
    for col in ('open','close','high','low','volume'):diff|=~np.isclose(overlap[col+'_new'],overlap[col+'_old'],rtol=0,atol=1e-10)
    conflicts=overlap.loc[diff,'ts'].tolist();g.index=pd.to_datetime(g.ts,unit='ms',utc=True);h=g.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'));h=h[(h.n==4)&(~h.index.floor('h').isin(pd.to_datetime(conflicts,unit='ms',utc=True).floor('4h')))].copy();h['ts']=h.index.asi8//1000000;h[['ts','open','high','low','close']].to_csv(OUT/'bitfinex-4h.csv.gz',index=False,compression='gzip')
    (OUT/'bitstamp-4h.csv.gz').write_bytes((OLD/'bitstamp-4h.csv.gz').read_bytes());expected=pd.date_range(cuts[0],cuts[-1]-pd.Timedelta(hours=4),freq='4h');source={}
    for name in ('bitstamp','bitfinex'):
        p=OUT/(name+'-4h.csv.gz');_,x=read(p);missing=expected.difference(x.index);source[name]={'bars':len(x),'expected':len(expected),'missing_utc':[t.isoformat() for t in missing],'invalid_bars':int((~x.good).sum()),'dataset_sha256':sha(p)}
    source['bitfinex'].update(hourly_rows=len(g),zero_volume_hours=int(g.volume.eq(0).sum()),requests=receipts,old_hourly_overlap=len(overlap),conflicting_hourly_utc=[pd.Timestamp(t,unit='ms',tz='UTC').isoformat() for t in conflicts]);source['bitstamp']['original_path']=str(OLD/'bitstamp-4h.csv.gz');files=[Path(__file__),SPEC,OLD/'manifest.json',OLD/'bitfinex-1h.json'];(OUT/'manifest.json').write_text(json.dumps({'start':cuts[0].isoformat(),'end_exclusive':cuts[-1].isoformat(),'sources':source,'input_sha256':{str(p):sha(p) for p in files}},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid_bars']) for k,v in source.items()},'overlap',len(overlap),'conflicts',len(conflicts))
if __name__=='__main__':main()
