"""Collect venue-local BTC/USDT spot bars with volume and original receipts."""
from pathlib import Path
import hashlib, io, json, zipfile
import numpy as np
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read
OUT=Path('data/market/btc-2022q4-usdt-cross-20261103-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    OUT.mkdir(exist_ok=False);frames=[];receipts=[]
    for month in pd.date_range('2022-08-01','2023-01-01',freq='MS'):
        name=f'BTCUSDT-4h-{month:%Y-%m}.zip';base=f'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/{name}'
        for suffix in ('','.CHECKSUM'):
            r=requests.get(base+suffix,timeout=60);r.raise_for_status();(OUT/(name+suffix)).write_bytes(r.content)
        p=OUT/name;assert sha(p)==(OUT/(name+'.CHECKSUM')).read_text().split()[0].lower()
        with zipfile.ZipFile(p) as z:
            assert len(z.namelist())==1;frames.append(pd.read_csv(io.BytesIO(z.read(z.namelist()[0])),header=None,usecols=[0,1,2,3,4,5]))
        receipts.append({'url':base,'sha256':sha(p),'checksum_verified':True})
    f=pd.concat(frames,ignore_index=True);f.columns=['ts','open','high','low','close','volume'];f=f.apply(pd.to_numeric).sort_values('ts');f.to_csv(OUT/'binance-4h.csv.gz',index=False,compression='gzip')
    cuts=pd.to_datetime(['2022-08-01','2022-11-01','2023-02-01'],utc=True);rows=[];kr=[]
    for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
        par={'symbol':'BTC-USDT','tradeType':'SPOT','interval':'4hour','startAt':int(a.timestamp()),'endAt':int(b.timestamp())-1};r=requests.get('https://api.kucoin.com/api/ua/v2/market/kline',params=par,timeout=60);r.raise_for_status();p=OUT/f'kucoin-{i}.json';p.write_bytes(r.content);x=r.json();assert x['code']=='200000' and x['data']['symbol']=='BTC-USDT';rows.extend(x['data']['list']);kr.append({'url':r.url,'sha256':sha(p),'rows':len(x['data']['list'])})
    f=pd.DataFrame([{'ts':int(z[0])*1000,'open':float(z[1]),'high':float(z[2]),'low':float(z[3]),'close':float(z[4]),'volume':float(z[5])} for z in rows]).sort_values('ts');f.to_csv(OUT/'kucoin-4h.csv.gz',index=False,compression='gzip')
    expected=pd.date_range(cuts[0],cuts[-1],inclusive='left',freq='4h');sources={}
    for name in ('binance','kucoin'):
        p=OUT/(name+'-4h.csv.gz');_,h=read(p);missing=expected.difference(h.index);v=h.volume;sources[name]={'bars':len(h),'expected':len(expected),'missing_utc':[t.isoformat() for t in missing],'invalid':int((~h.good).sum()),'nonpositive_volume':int((~np.isfinite(v)|(v<=0)).sum()),'sha256':sha(p),'requests':receipts if name=='binance' else kr}
    (OUT/'manifest.json').write_text(json.dumps({'start':cuts[0].isoformat(),'end_exclusive':cuts[-1].isoformat(),'sources':sources},indent=2)+'\n');print({k:(v['bars'],len(v['missing_utc']),v['invalid'],v['nonpositive_volume']) for k,v in sources.items()})
if __name__=='__main__':main()
