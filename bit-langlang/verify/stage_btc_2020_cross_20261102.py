"""Immutable public historical Binance futures / KuCoin spot evidence."""
import json,hashlib,io,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests,pandas as pd,numpy as np
OUT=Path('data/market/btc-2020-cross-20261102-01');START=pd.Timestamp('2019-11-01',tz='UTC');END=pd.Timestamp('2020-11-01',tz='UTC');BIN='https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m';KU='https://api.kucoin.com/api/ua/v2/market/kline'
def sha(b):return hashlib.sha256(b).hexdigest()
def req(url,params=None):
 r=requests.get(url,params=params,timeout=35);data=r.content;r.raise_for_status();return data

def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);months=pd.date_range(START,END-pd.Timedelta(days=1),freq='MS')
 def month(m):
  n=f'BTCUSDT-5m-{m:%Y-%m}.zip';u=f'{BIN}/{n}';body=req(u);check=req(u+'.CHECKSUM');expected=check.decode().split()[0].lower();assert sha(body)==expected,(n,'checksum mismatch');(OUT/n).write_bytes(body);(OUT/(n+'.CHECKSUM')).write_bytes(check)
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   if len(z.namelist())!=1:raise ValueError('unexpected archive members')
   df=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4]);df=df[pd.to_numeric(df.iloc[:,0],errors='coerce').notna()]
  return df,{'url':u,'name':n,'sha256':sha(body),'official_checksum_sha256':sha(check),'official_checksum_verified':True}
 with ThreadPoolExecutor(max_workers=4) as pool:chunks=list(pool.map(month,months))
 f=pd.concat([x[0] for x in chunks],ignore_index=True);f.columns=['ts','open','high','low','close'];f=f.apply(pd.to_numeric,errors='raise');a=int(START.timestamp()*1000);b=int(END.timestamp()*1000)
 if len(f)!=(b-a)//300000 or int(f.ts.iloc[0])!=a or int(f.ts.iloc[-1])!=b-300000 or not f.ts.diff().dropna().eq(300000).all():raise ValueError('Binance 5m grid incomplete')
 v=f[['open','high','low','close']]
 if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (f.low>v.min(axis=1)).any() or (f.high<v.max(axis=1)).any():raise ValueError('Binance invalid OHLC')
 f.to_csv(OUT/'BTCUSDT-binance-5m.csv.gz',index=False,compression='gzip');parts=[];ku_receipts=[]
 cuts=[START,pd.Timestamp('2020-05-01',tz='UTC'),END]
 for i,(start,end) in enumerate(zip(cuts,cuts[1:])):
  p={'symbol':'BTC-USDT','tradeType':'SPOT','interval':'4hour','startAt':int(start.timestamp()),'endAt':int(end.timestamp())-1};raw=req(KU,p);dest=OUT/f'kucoin-4h-{i}.json';dest.write_bytes(raw);payload=json.loads(raw)
  if payload.get('code')!='200000' or payload.get('data',{}).get('symbol')!='BTC-USDT':raise ValueError('KuCoin API payload')
  parts+=payload['data']['list'];ku_receipts.append({'url':KU,'params':p,'name':dest.name,'sha256':sha(raw)})
 k=pd.DataFrame([{'ts':int(r[0])*1000,'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4])} for r in parts]).sort_values('ts').reset_index(drop=True);expected=(b-a)//14400000
 if len(k)!=expected or k.ts.duplicated().any() or int(k.ts.iloc[0])!=a or int(k.ts.iloc[-1])!=b-14400000 or not k.ts.diff().dropna().eq(14400000).all():raise ValueError(f'KuCoin 4h grid incomplete got {len(k)} expected {expected}')
 v=k[['open','high','low','close']]
 if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (k.low>v.min(axis=1)).any() or (k.high<v.max(axis=1)).any():raise ValueError('KuCoin invalid OHLC')
 k.to_csv(OUT/'BTC-USDT-kucoin-spot-4h.csv.gz',index=False,compression='gzip')
 manifest={'status':'PUBLIC_SOURCE_VALIDATED_NOT_EXCHANGE_TRUTH','start':START.isoformat(),'end_exclusive':END.isoformat(),'binance':{'bars':len(f),'dataset_sha256':sha((OUT/'BTCUSDT-binance-5m.csv.gz').read_bytes()),'archives':[x[1] for x in chunks]},'kucoin':{'bars':len(k),'dataset_sha256':sha((OUT/'BTC-USDT-kucoin-spot-4h.csv.gz').read_bytes()),'requests':ku_receipts}};(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'binance':len(f),'kucoin':len(k)}))
if __name__=='__main__':main()
