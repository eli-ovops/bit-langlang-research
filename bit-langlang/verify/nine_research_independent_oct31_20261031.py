"""Recheck causal post-hoc entry filters against source arrays and trade records."""
import json
from pathlib import Path
import pandas as pd,numpy as np
from . import nine_futures_oct31_20261031 as model
from .forward_scan import read_raw_candles
from .historical_entry_replica import eligible_match
STAGE=Path('data/market/nine-futures-stage-oct31-20261031-01');OUT=Path('data/verify/nine-research-oct31-20261031-01')
def main():
 idx,data=model.prepare(STAGE);bt=read_raw_candles('BTCUSDT',STAGE).set_index('ts').resample('D').close.last();cool={}
 for s,d in data.items():
  indices=np.flatnonzero(d['signal']);kept=[]
  for i in indices:
   if not kept or i-kept[-1]>=12:kept.append(int(i))
  cool[s]=set(idx[kept].asi8.tolist())
 counts={}
 for variant in ('btc_momentum','rank1','cooldown60'):
  tr=json.loads((OUT/f'{variant}-full-closed.json').read_text())
  for t in tr:
   ts=pd.Timestamp(t['signal_ts']);s=t['symbol']
   if variant=='rank1':assert t['signal_rank']==1
   elif variant=='btc_momentum':
    day=ts.floor('D');assert bt.loc[day-pd.Timedelta(days=1)]>bt.loc[day-pd.Timedelta(days=8)]
   else:assert ts.value in cool[s]
  counts[variant]=len(tr)
 result={'status':'PASS','validated_full_closed_trades':counts,'limitations':'same OHLC data, rechecks conditions, not true orders or independent sample'};(OUT/'independent-filter-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
