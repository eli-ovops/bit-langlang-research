"""Public REST candles only; no account actions; immutable raw response receipts."""
import json,hashlib
from pathlib import Path
import pandas as pd
import requests
ROOT=Path('data/market/oct31-extension-20261031-01')
PRIOR=Path('data/market/nine-futures-stage-20261031-01')
SPOT=('PEPEUSDT','SOLUSDT','HYPEUSDT','SKYUSDT','UNIUSDT','AAVEUSDT','LINKUSDT','ENAUSDT','LITUSDT','BTCUSDT')
START=int(pd.Timestamp('2025-10-01',tz='UTC').timestamp()*1000);CUT=int(pd.Timestamp('2026-10-25',tz='UTC').timestamp()*1000);END=int(pd.Timestamp('2026-10-31',tz='UTC').timestamp()*1000)
def digest(b):return hashlib.sha256(b).hexdigest()
def main():
 if ROOT.exists():raise FileExistsError(ROOT)
 ROOT.mkdir(parents=True);sess=requests.Session();receipt=[]
 def get(url,params,name):
  r=sess.get(url,params=params,timeout=40);body=r.content;(ROOT/name).write_bytes(body);receipt.append({'url':url,'params':params,'status':r.status_code,'file':name,'sha256':digest(body)});r.raise_for_status();return r.json()
 manifest=json.loads((PRIOR/'manifest.json').read_text());symbols=tuple(manifest['symbols'])
 for symbol in symbols+('BTCUSDT',):
  batches=[];cursor=CUT;i=0
  while cursor<END:
   p={'symbol':symbol,'interval':'5m','startTime':cursor,'endTime':END-1,'limit':1500};rows=get('https://fapi.binance.com/fapi/v1/klines',p,f'{symbol}-extension-{i:02}.json')
   if not rows:raise ValueError('empty futures extension '+symbol)
   batches+=rows;cursor=int(rows[-1][0])+300000;i+=1
  ts=[int(r[0]) for r in batches];expected=list(range(CUT,END,300000))
  if ts!=expected:raise ValueError('futures missing/duplicate '+symbol)
  if symbol!='BTCUSDT':
   rows=get('https://fapi.binance.com/fapi/v1/fundingRate',{'symbol':symbol,'startTime':CUT,'endTime':END-1,'limit':1000},f'{symbol}-funding.json')
   stamps=[int(r['fundingTime']) for r in rows]
   if not stamps or stamps!=sorted(set(stamps)) or max([stamps[0]-CUT,END-stamps[-1]]+[y-x for x,y in zip(stamps,stamps[1:])])>28860000:raise ValueError('funding gap '+symbol)
  print('futures',symbol,len(batches),flush=True)
 for symbol in SPOT:
  rows=get('https://data-api.binance.vision/api/v3/klines',{'symbol':symbol,'interval':'1d','startTime':START,'endTime':END-1,'limit':1000},f'{symbol}-spot.json')
  if not isinstance(rows,list):raise ValueError('invalid spot '+symbol)
  print('spot',symbol,len(rows),flush=True)
 (ROOT/'receipts.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print('complete')
if __name__=='__main__':main()
