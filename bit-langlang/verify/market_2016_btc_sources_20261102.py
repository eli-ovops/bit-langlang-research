"""Read-only public BTC/USD historical bars, venues independent and raw preserved."""
from pathlib import Path
import hashlib,json
import requests,pandas as pd,numpy as np
from verify.market_2018_transition_20261102 import read
OUT=Path('data/market/btc-2016-usd-cross-20261102-01');START=pd.Timestamp('2016-01-01',tz='UTC');END=pd.Timestamp('2016-10-01',tz='UTC')
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);sessions=requests.Session();sources={}
 # End-only pagination is per Bitstamp documentation. Keep all response bytes.
 cut=END;raw=[];receipts=[]
 for i in range(3):
  params={'step':14400,'limit':1000,'end':int(cut.timestamp())};r=sessions.get('https://www.bitstamp.net/api/v2/ohlc/btcusd/',params=params,timeout=40);r.raise_for_status();p=OUT/f'bitstamp-{i}.json';p.write_bytes(r.content);data=r.json()['data']['ohlc'];
  if not data:break
  raw.extend(data);receipts.append({'url':r.url,'sha256':sha(r.content),'records':len(data)});oldest=min(int(x['timestamp']) for x in data);cut=pd.Timestamp(oldest,unit='s',tz='UTC')-pd.Timedelta(seconds=1)
  if cut<START:break
 b=pd.DataFrame([{'ts':int(z['timestamp'])*1000,**{k:float(z[k]) for k in ('open','high','low','close')}} for z in raw]).sort_values('ts');b=b[(b.ts>=int(START.timestamp()*1000))&(b.ts<int(END.timestamp()*1000))]
 if b.ts.duplicated().any():raise ValueError('Bitstamp duplicate timestamps')
 b.to_csv(OUT/'bitstamp-4h.csv.gz',index=False,compression='gzip');d,h=read(OUT/'bitstamp-4h.csv.gz');expected=pd.date_range(START,END-pd.Timedelta(hours=4),freq='4h');missing=expected.difference(h.index)
 sources['bitstamp']={'bars':len(h),'expected':len(expected),'missing_utc':[v.isoformat() for v in missing],'invalid':int((~h.good).sum()),'raw':receipts,'dataset_sha256':sha((OUT/'bitstamp-4h.csv.gz').read_bytes())}
 # Coinbase returns at most 300 one-hour bars; request fixed 10-day intervals.
 raw=[];receipts=[];cuts=list(pd.date_range(START,END,freq='10D'))
 if cuts[-1]!=END:cuts.append(END)
 for i,(a,bound) in enumerate(zip(cuts,cuts[1:])):
  params={'granularity':3600,'start':a.isoformat(),'end':bound.isoformat()};r=sessions.get('https://api.exchange.coinbase.com/products/BTC-USD/candles',params=params,timeout=40);r.raise_for_status();p=OUT/f'coinbase-{i:02}.json';p.write_bytes(r.content);data=r.json();
  if not isinstance(data,list):raise ValueError('Coinbase unexpected response')
  raw.extend(data);receipts.append({'url':r.url,'sha256':sha(r.content),'records':len(data)})
 c=pd.DataFrame(raw,columns=['s','low','high','open','close','volume']);c=c.apply(pd.to_numeric);c=c[(c.s>=int(START.timestamp()))&(c.s<int(END.timestamp()))].sort_values('s')
 if c.s.duplicated().any():
  groups=c.groupby('s');conflicts=groups[['low','high','open','close','volume']].nunique().max(axis=1);assert (conflicts<=1).all();c=c.drop_duplicates(subset='s')
 c['time']=pd.to_datetime(c.s,unit='s',utc=True);c=c.set_index('time');four=c.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),n=('s','size'));four=four[four.n==4].copy();four['ts']=(four.index.asi8//1000000);four[['ts','open','high','low','close']].to_csv(OUT/'coinbase-4h.csv.gz',index=False,compression='gzip');d,h=read(OUT/'coinbase-4h.csv.gz');missing=expected.difference(h.index)
 sources['coinbase']={'bars':len(h),'expected':len(expected),'missing_utc':[v.isoformat() for v in missing],'invalid':int((~h.good).sum()),'raw':receipts,'dataset_sha256':sha((OUT/'coinbase-4h.csv.gz').read_bytes()),'aggregation':'exactly four 1h bars per 4h interval'}
 (OUT/'manifest.json').write_text(json.dumps({'status':'PRICE_SERIES_NOT_TRUTH','sources':sources},indent=2)+'\n');print({k:{'bars':v['bars'],'missing':len(v['missing_utc']),'invalid':v['invalid']} for k,v in sources.items()})
if __name__=='__main__':main()
