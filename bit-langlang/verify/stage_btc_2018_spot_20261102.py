"""Immutable public 4h spot BTC bars, Binance and KuCoin; no account calls."""
import io,json,hashlib,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests,pandas as pd,numpy as np
OUT=Path('data/market/btc-2018-spot-cross-20261102-01');START=pd.Timestamp('2017-11-01',tz='UTC');END=pd.Timestamp('2019-01-01',tz='UTC');BIN='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h';KU='https://api.kucoin.com/api/ua/v2/market/kline'
def sha(b):return hashlib.sha256(b).hexdigest()
def get(url,params=None):
 r=requests.get(url,params=params,timeout=35);r.raise_for_status();return r.content
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);months=pd.date_range(START,END-pd.Timedelta(days=1),freq='MS')
 def month(t):
  n=f'BTCUSDT-4h-{t:%Y-%m}.zip';url=f'{BIN}/{n}';body=get(url);checksum=get(url+'.CHECKSUM');assert sha(body)==checksum.decode().split()[0].lower();(OUT/n).write_bytes(body);(OUT/(n+'.CHECKSUM')).write_bytes(checksum)
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   if len(z.namelist())!=1:raise ValueError('unexpected zip members')
   d=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4]);d=d[pd.to_numeric(d.iloc[:,0],errors='coerce').notna()]
  return d,{'url':url,'filename':n,'sha256':sha(body),'checksum_sha256':sha(checksum),'official_checksum_verified':True}
 with ThreadPoolExecutor(max_workers=4) as ex:parts=list(ex.map(month,months))
 b=pd.concat([x[0] for x in parts],ignore_index=True);b.columns=['ts','open','high','low','close'];b=b.apply(pd.to_numeric,errors='raise');ku=[];receipts=[];cuts=[START,pd.Timestamp('2018-05-01',tz='UTC'),pd.Timestamp('2018-11-01',tz='UTC'),END]
 for i,(a,z) in enumerate(zip(cuts,cuts[1:])):
  params={'symbol':'BTC-USDT','tradeType':'SPOT','interval':'4hour','startAt':int(a.timestamp()),'endAt':int(z.timestamp())-1};body=get(KU,params);name=f'kucoin-4h-{i}.json';(OUT/name).write_bytes(body);payload=json.loads(body)
  if payload.get('code')!='200000' or payload.get('data',{}).get('symbol')!='BTC-USDT':raise ValueError('invalid KuCoin payload')
  ku+=payload['data']['list'];receipts.append({'url':KU,'params':params,'name':name,'sha256':sha(body)})
 k=pd.DataFrame([{'ts':int(r[0])*1000,'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4])} for r in ku]).sort_values('ts').reset_index(drop=True)
 result={}
 for name,f in [('binance',b),('kucoin',k)]:
  start=int(START.timestamp()*1000);end=int(END.timestamp()*1000);expected=(end-start)//14400000
  if len(f)!=expected or f.ts.duplicated().any() or not f.ts.is_monotonic_increasing or f.ts.iloc[0]!=start or f.ts.iloc[-1]!=end-14400000 or not f.ts.diff().dropna().eq(14400000).all():raise ValueError(f'{name}: grid incomplete count={len(f)}, expected={expected}')
  v=f[['open','high','low','close']]
  if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (f.low>v.min(axis=1)).any() or (f.high<v.max(axis=1)).any():raise ValueError(name+' invalid OHLC')
  path=OUT/(name+'-spot-4h.csv.gz');f.to_csv(path,index=False,compression='gzip');result[name]={'bars':len(f),'dataset_sha256':sha(path.read_bytes())}
 result['binance']['archives']=[x[1] for x in parts];result['kucoin']['requests']=receipts;(OUT/'manifest.json').write_text(json.dumps({'status':'COMPLETE_INPUT_NOT_SEASON_TRUTH','start':START.isoformat(),'end_exclusive':END.isoformat(),'sources':result},indent=2)+'\n');print(json.dumps({k:v['bars'] for k,v in result.items()}))
if __name__=='__main__':main()
