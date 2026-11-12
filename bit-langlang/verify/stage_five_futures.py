"""Download immutable public market evidence; no account or platform operations."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import requests

SYMBOLS=('UNIUSDT','AAVEUSDT','LINKUSDT','ENAUSDT','LITUSDT')
START=pd.Timestamp('2025-07-01',tz='UTC');END=pd.Timestamp('2026-10-25',tz='UTC')
BASE='https://data.binance.vision/data/futures/um/monthly/klines'
API='https://fapi.binance.com'
STEP=300000


def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--outdir',required=True);p.add_argument('--reuse-stage');a=p.parse_args()
    root=Path(a.outdir);root.mkdir(parents=True,exist_ok=False);session=requests.Session();manifest={}
    for symbol in SYMBOLS:
        folder=root/symbol;folder.mkdir();chunks=[];receipts=[]
        old=Path(a.reuse_stage)/symbol if a.reuse_stage else None
        def get(url,name,params=None):
            previous=old/name if old else None
            if previous and previous.is_file():body=previous.read_bytes()
            else:
                response=session.get(url,params=params,timeout=40);response.raise_for_status();body=response.content
            (folder/name).write_bytes(body)
            return body
        first_month=pd.Timestamp('2025-12-01') if symbol=='LITUSDT' else pd.Timestamp('2025-07-01')
        for month in pd.date_range(first_month,'2026-09-01',freq='MS'):
            name=f'{symbol}-5m-{month:%Y-%m}.zip';url=f'{BASE}/{symbol}/5m/{name}'
            body=get(url,name)
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                names=z.namelist()
                if len(names)!=1:raise ValueError('unexpected zip members')
                frame=pd.read_csv(io.BytesIO(z.read(names[0])),header=None,usecols=[0,1,2,3,4])
                if len(frame) and str(frame.iloc[0,0]).strip()=='open_time':frame=frame.iloc[1:].reset_index(drop=True)
            chunks.append(frame);receipts.append({'url':url,'file':name,'sha256':sha(body),'reuse_source':str(old/name) if old and (old/name).is_file() else None})
        cursor=int(pd.Timestamp('2026-10-01',tz='UTC').timestamp()*1000);end=int(END.timestamp()*1000);n=0
        while cursor<end:
            params={'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':end-1,'limit':1500}
            name=f'oct-{n:02}.json';body=get(API+'/fapi/v1/klines',name,params);rows=json.loads(body)
            if not isinstance(rows,list) or not rows:raise ValueError('missing October klines')
            receipts.append({'url':API+'/fapi/v1/klines','params':params,'file':name,'sha256':sha(body),'reuse_source':str(old/name) if old and (old/name).is_file() else None})
            chunks.append(pd.DataFrame([row[:5] for row in rows]));next_cursor=int(rows[-1][0])+STEP
            if next_cursor<=cursor:raise ValueError('no kline pagination progress')
            cursor=next_cursor;n+=1
        frame=pd.concat(chunks,ignore_index=True)
        frame.columns=['ts','open','high','low','close']
        for col in frame.columns:frame[col]=pd.to_numeric(frame[col],errors='raise')
        frame=frame[(frame.ts>=int(START.timestamp()*1000))&(frame.ts<end)].reset_index(drop=True)
        if symbol=='LITUSDT':
            # Binance reused the ticker. The official Lighter launch is the first admissible instant.
            launch=int(pd.Timestamp('2025-12-23T17:30:00Z').timestamp()*1000)
            frame=frame[frame.ts>=launch].reset_index(drop=True)
        if (frame.empty or frame.ts.duplicated().any() or not frame.ts.is_monotonic_increasing or
                (frame.ts.diff().dropna()!=STEP).any() or int(frame.ts.iloc[-1])!=end-STEP or
                not np.isfinite(frame.to_numpy(dtype=float)).all() or (frame.iloc[:,1:]<=0).any().any() or
                (frame.low>frame[['open','high','close']].min(axis=1)).any() or
                (frame.high<frame[['open','low','close']].max(axis=1)).any()):raise ValueError(f'{symbol}: invalid market grid/OHLC')
        if symbol!='LITUSDT' and int(frame.ts.iloc[0])!=int(START.timestamp()*1000):raise ValueError('insufficient warmup')
        frame.to_csv(root/f'{symbol}_5m.csv.gz',index=False,compression='gzip')
        cursor=max(int(frame.ts.iloc[0]),int(pd.Timestamp('2025-10-01',tz='UTC').timestamp()*1000));fund=[];n=0
        while cursor<end:
            params={'symbol':symbol,'startTime':cursor,'endTime':end-1,'limit':1000}
            name=f'funding-{n:02}.json';body=get(API+'/fapi/v1/fundingRate',name,params);rows=json.loads(body)
            if not isinstance(rows,list):raise ValueError('funding response invalid')
            receipts.append({'url':API+'/fapi/v1/fundingRate','params':params,'file':name,'sha256':sha(body),'reuse_source':str(old/name) if old and (old/name).is_file() else None})
            if not rows:break
            fund.extend(rows);next_cursor=int(rows[-1]['fundingTime'])+1
            if next_cursor<=cursor:raise ValueError('no funding pagination progress')
            cursor=next_cursor;n+=1
        f=pd.DataFrame([{'ts':int(x['fundingTime']),'funding_rate':float(x['fundingRate'])} for x in fund])
        if f.empty or f.ts.duplicated().any() or not f.ts.is_monotonic_increasing or not np.isfinite(f.to_numpy(dtype=float)).all():raise ValueError('invalid funding records')
        # Local continuity heuristic only: venue may change schedule; no proof of completeness.
        coverage_limit=8*3600000+60000
        if (f.ts.diff().dropna()>coverage_limit).any() or f.ts.iloc[0]-max(int(frame.ts.iloc[0]),int(pd.Timestamp('2025-10-01',tz='UTC').timestamp()*1000))>coverage_limit or end-f.ts.iloc[-1]>coverage_limit:
            raise ValueError('funding coverage gap > 8h plus 60s tolerance')
        f.to_csv(root/f'{symbol}_funding.csv.gz',index=False,compression='gzip')
        manifest[symbol]={'first_ms':int(frame.ts.iloc[0]),'last_ms':int(frame.ts.iloc[-1]),'bars':len(frame),'funding_records':len(f),
                          'price_sha256':sha((root/f'{symbol}_5m.csv.gz').read_bytes()),
                          'funding_sha256':sha((root/f'{symbol}_funding.csv.gz').read_bytes()),'requests':receipts}
        print(symbol,'bars',len(frame),'funding',len(f),flush=True)
    (root/'manifest.json').write_text(json.dumps({'status':'PUBLIC_SOURCE_UNVERIFIED','symbols':manifest},indent=2)+'\n')


if __name__=='__main__':main()
