"""Recompute every filled candidate directly from source bars and complete days."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .forward_scan import read_raw_candles
from .nine_futures_compound_20261031 import sha

STAGE=Path('data/market/seven-futures-stage-20261031-01');OUT=Path('data/verify/seven-futures-compound-20261031-01')
def main():
    trades=json.loads((OUT/'closed.json').read_text());meta=json.loads((STAGE/'manifest.json').read_text());symbols=sorted(meta['symbols']);raw={s:read_raw_candles(s,STAGE).set_index('ts') for s in symbols};btc=read_raw_candles('BTCUSDT').set_index('ts')
    daily={s:f.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'}) for s,f in raw.items()};daily['BTC']=btc.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'})
    for tr in trades:
        symbol=tr['symbol'];f=raw[symbol];t=pd.Timestamp(tr['signal_ts']);entry=pd.Timestamp(tr['entry_ts']);day=t.floor('D');assert entry-t==pd.Timedelta(minutes=10)
        bd=daily['BTC'].loc[day-pd.Timedelta(days=20):day-pd.Timedelta(days=1)];assert len(bd)==20 and bd.open.eq(288).all() and bd.close.iloc[-1]>(bd.high.max()+bd.low.min())/2
        b7=bd.close.iloc[-1]/bd.close.iloc[-8]-1;scores={}
        for s in symbols:
            w=daily[s].loc[day-pd.Timedelta(days=30):day-pd.Timedelta(days=1)]
            if len(w)==30 and w.open.eq(288).all():scores[s]=w.close.iloc[-1]/w.close.iloc[-8]-1-b7
        ranked=sorted([(-v,k) for k,v in scores.items() if v>0]);assert symbol in [s for _,s in ranked[:2]]
        assert tr['signal_rank']==[s for _,s in ranked].index(symbol)+1 and abs(tr['signal_relative_strength']-scores[symbol])<1e-10
        bar=f.loc[t];prev=f.loc[t-pd.Timedelta(minutes=5)];p20=f.loc[t-pd.Timedelta(minutes=100):t-pd.Timedelta(minutes=5)];p48=f.loc[t-pd.Timedelta(minutes=240):t-pd.Timedelta(minutes=5)];p12=f.loc[t-pd.Timedelta(minutes=55):t]
        assert len(p20)==20 and len(p48)==48 and len(p12)==12
        assert prev.close<prev.open and bar.close>bar.open and bar.close>prev.close and bar.close>=(p20.high.max()+p20.low.min())/2 and bar.close>=(p48.high.max()+p48.low.min())/2
        assert abs(tr['stop']-p12.low.min())<1e-10 and abs(tr['entry']-f.loc[entry].open*1.0002)<1e-10
    result={'checked_trades':len(trades),'result':'PASS','source':'same Binance candle files; independent calculation is not independent venue or trader behavior','signals_source_sha256':sha(OUT/'closed.json'),'code_sha256':sha(__file__)}
    (OUT/'independent-entry-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
