#!/usr/bin/env python3
"""Create a non-destructive, closed-candle BTC/ETH staging snapshot.

Only public Binance USDT-M candles, no authentication. Do not touch originals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import requests
import numpy as np

SOURCE=Path(__file__).resolve().parents[1]/'data'/'market'
BASE='https://fapi.binance.com'
COLS=['ts','open','high','low','close','volume','turnover']


def merge_closed(old, klines, exchange_now_ms):
    if old.empty or old.ts.duplicated().any() or not old.ts.is_monotonic_increasing:
        raise ValueError('source candles missing, duplicate or unordered')
    last=int(old.ts.iloc[-1]); rows=[]
    for k in klines:
        if len(k)<8: raise ValueError('invalid kline response')
        if int(k[6]) < exchange_now_ms and int(k[0]) >= last:
            rows.append([int(k[0]),k[1],k[2],k[3],k[4],k[5],k[7]])
    new=pd.DataFrame(rows,columns=COLS)
    if new.empty or int(new.ts.iloc[0])!=last:
        raise ValueError('cannot revalidate last previously stored candle')
    combined=pd.concat([old.iloc[:-1][COLS],new],ignore_index=True)
    if combined.ts.duplicated().any() or not combined.ts.is_monotonic_increasing or not (combined.ts.diff().dropna()==300000).all():
        raise ValueError('result has duplicate, unordered, or missing 5m candles')
    v=combined[['open','high','low','close']].apply(pd.to_numeric,errors='coerce')
    if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (v.low>v[['open','high','close']].min(axis=1)).any() or (v.high<v[['open','low','close']].max(axis=1)).any():
        raise ValueError('invalid OHLC values')
    return combined


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--outdir',required=True);a=ap.parse_args()
    folder=Path(a.outdir);folder.mkdir(parents=True,exist_ok=False)
    s=requests.Session();s.headers['User-Agent']='bitlanglang-paper-data/1.0'
    response=s.get(BASE+'/fapi/v1/time',timeout=15);response.raise_for_status();now=int(response.json()['serverTime'])
    manifest={'exchange_server_time_ms':now,'source':'Binance USD-M public REST; UTC','closed_only':True,'symbols':{}}
    for symbol in ('BTCUSDT','ETHUSDT'):
        src=SOURCE/f'{symbol}_5m.csv.gz';old=pd.read_csv(src);cursor=int(old.ts.iloc[-1]); items=[]
        while cursor<now:
            response=s.get(BASE+'/fapi/v1/klines',params={'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':now,'limit':1000},timeout=20)
            response.raise_for_status();batch=response.json()
            if not isinstance(batch,list): raise ValueError('unexpected response')
            if not batch: break
            items.extend(batch);next_cursor=int(batch[-1][0])+300000
            if next_cursor<=cursor: raise ValueError('non-progressing response')
            cursor=next_cursor
        combined=merge_closed(old,items,now);dst=folder/f'{symbol}_5m.csv.gz';combined.to_csv(dst,index=False,compression='gzip')
        manifest['symbols'][symbol]={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),
             'source_last_ts':int(old.ts.iloc[-1]),'output_last_ts':int(combined.ts.iloc[-1]),'rows':len(combined),'source_last_replaced':True}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(manifest,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
