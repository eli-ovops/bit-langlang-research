"""Read-only public historical futures and spot; local immutable receipts."""
import json,hashlib,io,zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests,pandas as pd,numpy as np
OUT=Path('data/market/four-earlier-2021-20261031-01');S=('SOLUSDT','UNIUSDT','AAVEUSDT','LINKUSDT');ALL=S+('BTCUSDT',)
START=pd.Timestamp('2020-11-01',tz='UTC');TRADE=pd.Timestamp('2021-01-01',tz='UTC');END=pd.Timestamp('2022-01-01',tz='UTC');BASE='https://data.binance.vision/data/futures/um/monthly/klines';API='https://fapi.binance.com';SPOT='https://data-api.binance.vision/api/v3/klines'
def sha(b):return hashlib.sha256(b).hexdigest()
def task(symbol):
 folder=OUT/symbol;folder.mkdir();sess=requests.Session();receipts=[];chunks=[]
 def get(url,name,params=None):
  r=sess.get(url,params=params,timeout=40);body=r.content;(folder/name).write_bytes(body);receipts.append({'url':url,'params':params,'status':r.status_code,'file':str((folder/name).relative_to(OUT)),'sha256':sha(body)});r.raise_for_status();return body
 for month in pd.date_range(START,END-pd.Timedelta(days=1),freq='MS'):
  n=f'{symbol}-5m-{month:%Y-%m}.zip';body=get(f'{BASE}/{symbol}/5m/{n}',n)
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   if len(z.namelist())!=1:raise ValueError('archive members')
   f=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4]);f=f[pd.to_numeric(f.iloc[:,0],errors='coerce').notna()];chunks.append(f)
 f=pd.concat(chunks,ignore_index=True);f.columns=['ts','open','high','low','close'];f=f.apply(pd.to_numeric,errors='raise');start=int(START.timestamp()*1000);end=int(END.timestamp()*1000)
 if len(f)!=(end-start)//300000 or int(f.ts.iloc[0])!=start or int(f.ts.iloc[-1])!=end-300000 or not f.ts.diff().dropna().eq(300000).all():raise ValueError('invalid futures grid '+symbol)
 if not np.isfinite(f.to_numpy()).all() or (f.iloc[:,1:]<=0).any().any() or (f.low>f[['open','high','close']].min(axis=1)).any() or (f.high<f[['open','low','close']].max(axis=1)).any():raise ValueError('OHLC invalid '+symbol)
 f.to_csv(OUT/(symbol+'_5m.csv.gz'),index=False,compression='gzip');result={'price_sha256':sha((OUT/(symbol+'_5m.csv.gz')).read_bytes()),'bars':len(f)}
 if symbol in S:
  cursor=int(TRADE.timestamp()*1000);records=[];i=0
  while cursor<end:
   params={'symbol':symbol,'startTime':cursor,'endTime':end-1,'limit':1000};body=get(API+'/fapi/v1/fundingRate',f'funding-{i}.json',params);arr=json.loads(body)
   if not isinstance(arr,list):raise ValueError('funding type')
   if not arr:break
   records+=arr;next_=int(arr[-1]['fundingTime'])+1
   if next_<=cursor:raise ValueError('funding cursor')
   cursor=next_;i+=1
  rates=pd.DataFrame([{'ts':int(r['fundingTime']),'funding_rate':float(r['fundingRate'])} for r in records]);limit=28860000
  if rates.empty or rates.ts.duplicated().any() or not rates.ts.is_monotonic_increasing or not np.isfinite(rates.to_numpy()).all() or (rates.ts.diff().dropna()>limit).any() or rates.ts.iloc[0]-int(TRADE.timestamp()*1000)>limit or end-rates.ts.iloc[-1]>limit:raise ValueError('funding coverage '+symbol)
  rates.to_csv(OUT/(symbol+'_funding.csv.gz'),index=False,compression='gzip');result.update(funding_sha256=sha((OUT/(symbol+'_funding.csv.gz')).read_bytes()),funding_records=len(rates))
  p={'symbol':symbol,'interval':'1d','startTime':int(TRADE.timestamp()*1000),'endTime':end-1,'limit':1000};raw=get(SPOT,'spot-1d.json',p);rows=json.loads(raw);ts=pd.to_datetime([x[0] for x in rows],unit='ms',utc=True);expected=pd.date_range(TRADE,END-pd.Timedelta(days=1),freq='D');v=np.array([[float(x[k]) for k in (1,2,3,4)] for x in rows]);
  if not ts.equals(expected) or not np.isfinite(v).all() or (v<=0).any() or (v[:,2]>v.min(axis=1)).any() or (v[:,1]<v.max(axis=1)).any():raise ValueError('spot invalid '+symbol)
  result['spot_sha256']=sha(raw)
 result['receipts']=receipts;print(symbol,'complete',flush=True);return symbol,result

def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True)
 with ThreadPoolExecutor(max_workers=3) as pool:items=list(pool.map(task,ALL))
 (OUT/'manifest.json').write_text(json.dumps({'status':'EARLIER_FOUR_ASSET_STRESS_NOT_NINE','symbols':dict(items)},indent=2)+'\n');print('complete')
if __name__=='__main__':main()
