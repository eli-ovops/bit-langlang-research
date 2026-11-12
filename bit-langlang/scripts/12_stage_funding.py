#!/usr/bin/env python3
"""Capture a bounded, public funding history snapshot without account access."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

BASE='https://fapi.binance.com'
SYMBOLS=('BTCUSDT','ETHUSDT')


def fetch(session, symbol, start_ms, end_ms):
    cursor=start_ms;rows=[]
    while cursor<end_ms:
        response=session.get(BASE+'/fapi/v1/fundingRate',params={'symbol':symbol,'startTime':cursor,'endTime':end_ms-1,'limit':1000},timeout=20)
        response.raise_for_status();batch=response.json()
        if not isinstance(batch,list): raise ValueError('invalid funding response')
        if not batch: break
        timestamps=[int(x['fundingTime']) for x in batch]
        if (any(x.get('symbol')!=symbol for x in batch) or timestamps!=sorted(set(timestamps))
                or timestamps[0]<cursor or timestamps[-1]>=end_ms):
            raise ValueError('funding response symbol or time invalid')
        rows.extend(batch);cursor=timestamps[-1]+1
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',required=True);parser.add_argument('--end',required=True);parser.add_argument('--outdir',required=True)
    args=parser.parse_args()
    start=pd.to_datetime(args.start,utc=True,errors='raise');end=pd.to_datetime(args.end,utc=True,errors='raise')
    if pd.isna(start) or pd.isna(end) or start>=end or start.value%1_000_000 or end.value%1_000_000: raise ValueError('invalid query interval or sub-millisecond precision')
    folder=Path(args.outdir)
    if folder.exists(): raise SystemExit('refusing to overwrite snapshot')
    session=requests.Session()
    response=session.get(BASE+'/fapi/v1/time',timeout=15);response.raise_for_status();server_time=int(response.json()['serverTime'])
    if end.value//1_000_000>server_time: raise ValueError('end exceeds exchange server time')
    results={s:fetch(session,s,start.value//1_000_000,end.value//1_000_000) for s in SYMBOLS}
    response=session.get(BASE+'/fapi/v1/time',timeout=15);response.raise_for_status();completed_server_time=int(response.json()['serverTime'])
    if completed_server_time<server_time: raise ValueError('exchange clock moved backwards')
    folder.mkdir(parents=True,exist_ok=False)
    manifest={'schema':'paper-funding-snapshot-v2','source':'Binance USD-M public fundingRate',
              'start_utc':start.isoformat(),'end_utc_exclusive':end.isoformat(),
              'query_server_time_ms':server_time,'server_time_ms':completed_server_time,'symbols':{}}
    for symbol,rows in results.items():
        raw=(json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode('utf-8');path=folder/f'{symbol}.json'
        with path.open('xb') as f:f.write(raw)
        manifest['symbols'][symbol]={'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows)}
    manifest['captured_at_utc']=pd.Timestamp.now(tz='UTC').isoformat()
    with (folder/'manifest.json').open('x',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
