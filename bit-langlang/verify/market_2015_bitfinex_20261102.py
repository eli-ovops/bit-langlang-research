"""Fetch a separate venue; never splice with other exchanges."""
from pathlib import Path
import json,hashlib,requests,pandas as pd,numpy as np
from verify.market_2018_transition_20261102 import read
OUT=Path('data/market/btc-2015-bitfinex-20261102-01');A=pd.Timestamp('2015-04-01',tz='UTC');B=pd.Timestamp('2016-01-01',tz='UTC')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);params={'start':int(A.timestamp()*1000),'end':int(B.timestamp()*1000)-1,'limit':10000,'sort':1};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=params,timeout=60);r.raise_for_status();raw=OUT/'bitfinex-1h.json';raw.write_bytes(r.content);items=r.json();assert isinstance(items,list) and (not items or isinstance(items[0],list))
 f=pd.DataFrame(items,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).sort_values('ts');assert not f.ts.duplicated().any() and (f.ts%3600000==0).all() and (f.ts>=int(A.timestamp()*1000)).all() and (f.ts<int(B.timestamp()*1000)).all();v=f[['open','high','low','close']];assert np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (f.low<=v.min(axis=1)).all() and (f.high>=v.max(axis=1)).all()
 f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time');h=f.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'));h=h[h.n==4].copy();h['ts']=h.index.asi8//1000000;dst=OUT/'bitfinex-4h.csv.gz';h[['ts','open','high','low','close']].to_csv(dst,index=False,compression='gzip');d,h=read(dst);expected=pd.date_range(A,B-pd.Timedelta(hours=4),freq='4h');missing=expected.difference(h.index);summary={'source':'Bitfinex BTC/USD spot, 1h grouped to 4h with all 4 hours','request_url':r.url,'raw_sha256':hashlib.sha256(r.content).hexdigest(),'1h_rows':len(items),'bars':len(h),'expected':len(expected),'missing_utc':[x.isoformat() for x in missing],'invalid_bars':int((~h.good).sum()),'dataset_sha256':hashlib.sha256(dst.read_bytes()).hexdigest()};(OUT/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n');print('rows1h',len(items),'4h',len(h),'missing',len(missing))
if __name__=='__main__':main()
