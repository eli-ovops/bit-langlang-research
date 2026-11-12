"""Bitstamp and Bitfinex BTC/USD spot raw history, independently retained."""
from pathlib import Path
import hashlib,json,requests,pandas as pd,numpy as np
from verify.market_2018_transition_20261102 import read
OUT=Path('data/market/btc-2019on-usd-cross-20261102-01');A=pd.Timestamp('2019-08-01',tz='UTC');B=pd.Timestamp('2020-01-01',tz='UTC')
def sh(b):return hashlib.sha256(b).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);raw=[];receipt=[];cut=B
 for i in range(3):
  params={'step':14400,'limit':1000,'end':int(cut.timestamp())};r=requests.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=params,timeout=50);r.raise_for_status();p=OUT/f'bitstamp-{i}.json';p.write_bytes(r.content);data=r.json()['data']['ohlc'];assert data;raw.extend(data);receipt.append({'url':r.url,'sha256':sh(r.content),'rows':len(data)});cut=pd.Timestamp(min(int(x['timestamp']) for x in data),unit='s',tz='UTC')-pd.Timedelta(seconds=1)
  if cut<A:break
 f=pd.DataFrame([{'ts':int(x['timestamp'])*1000,**{k:float(x[k]) for k in ('open','high','low','close')}} for x in raw]).sort_values('ts');f=f[(f.ts>=int(A.timestamp()*1000))&(f.ts<int(B.timestamp()*1000))];assert not f.ts.duplicated().any();f.to_csv(OUT/'bitstamp-4h.csv.gz',index=False,compression='gzip')
 params={'start':int(A.timestamp()*1000),'end':int(B.timestamp()*1000)-1,'limit':10000,'sort':1};r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=params,timeout=60);r.raise_for_status();(OUT/'bitfinex-1h.json').write_bytes(r.content);items=r.json();assert isinstance(items,list) and items and isinstance(items[0],list);g=pd.DataFrame(items,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).sort_values('ts');v=g[['open','high','low','close']];assert not g.ts.duplicated().any() and (g.ts%3600000==0).all() and (g.ts>=int(A.timestamp()*1000)).all() and (g.ts<int(B.timestamp()*1000)).all() and np.isfinite(v.to_numpy()).all() and (v>0).all().all() and (g.low<=v.min(axis=1)).all() and (g.high>=v.max(axis=1)).all();g.index=pd.to_datetime(g.ts,unit='ms',utc=True);h=g.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('ts','size'));h=h[h.n==4].copy();h['ts']=h.index.asi8//1000000;h[['ts','open','high','low','close']].to_csv(OUT/'bitfinex-4h.csv.gz',index=False,compression='gzip');source={};expected=pd.date_range(A,B-pd.Timedelta(hours=4),freq='4h')
 for name in ('bitstamp','bitfinex'):
  path=OUT/(name+'-4h.csv.gz');d,h=read(path);missing=expected.difference(h.index);source[name]={'bars':len(h),'expected':len(expected),'missing_utc':[x.isoformat() for x in missing],'invalid_bars':int((~h.good).sum()),'dataset_sha256':sh(path.read_bytes())}
 source['bitstamp']['requests']=receipt;source['bitfinex'].update(request_url=r.url,raw_sha256=sh(r.content),raw_1h_rows=len(items));(OUT/'manifest.json').write_text(json.dumps({'start':A.isoformat(),'end_exclusive':B.isoformat(),'sources':source},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid_bars']) for k,v in source.items()})
if __name__=='__main__':main()
