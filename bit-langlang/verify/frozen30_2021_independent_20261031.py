"""Independent causal recheck of each filled 2021 research candidate."""
import json
from pathlib import Path
import pandas as pd
from .forward_scan import read_raw_candles
STAGE=Path('data/market/four-earlier-2021-20261031-01');OUT=Path('data/verify/frozen30-2021-20261031-01');SYMBOLS=('SOLUSDT','UNIUSDT','AAVEUSDT','LINKUSDT')
def main():
 prices={s:read_raw_candles(s,STAGE).set_index('ts') for s in SYMBOLS+('BTCUSDT',)};daily={s:f.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'}) for s,f in prices.items()};trades=json.loads((OUT/'closed.json').read_text())
 for tr in trades:
  s=tr['symbol'];t=pd.Timestamp(tr['signal_ts']);day=t.floor('D');assert pd.Timestamp(tr['entry_ts'])-t==pd.Timedelta(minutes=10)
  btc=daily['BTCUSDT'];last=day-pd.Timedelta(days=1);prior=day-pd.Timedelta(days=31);tw=btc.loc[day-pd.Timedelta(days=20):last];assert len(tw)==20 and tw.open.eq(288).all() and tw.close.iloc[-1]>(tw.high.max()+tw.low.min())/2
  btc_ret=btc.loc[last,'close']/btc.loc[prior,'close']-1;scores={}
  for name in SYMBOLS:
   w=daily[name].loc[prior:last]
   if len(w)==31 and w.open.eq(288).all():scores[name]=w.close.iloc[-1]/w.close.iloc[0]-1-btc_ret
  ranks=sorted((-v,k) for k,v in scores.items() if v>0);assert s in [k for _,k in ranks[:2]] and tr['signal_rank']==[k for _,k in ranks].index(s)+1 and abs(tr['signal_relative_strength']-scores[s])<1e-10
  f=prices[s];bar=f.loc[t];prev=f.loc[t-pd.Timedelta(minutes=5)];p20=f.loc[t-pd.Timedelta(minutes=100):t-pd.Timedelta(minutes=5)];p48=f.loc[t-pd.Timedelta(minutes=240):t-pd.Timedelta(minutes=5)];p12=f.loc[t-pd.Timedelta(minutes=55):t]
  assert len(p20)==20 and len(p48)==48 and len(p12)==12 and prev.close<prev.open and bar.close>bar.open and bar.close>prev.close and bar.close>=(p20.high.max()+p20.low.min())/2 and bar.close>=(p48.high.max()+p48.low.min())/2
  assert abs(tr['stop']-p12.low.min())<1e-10 and abs(tr['entry']-f.loc[pd.Timestamp(tr['entry_ts']),'open']*1.0002)<1e-10
 (OUT/'independent-entry-check.json').write_text(json.dumps({'status':'PASS','checked_trades':len(trades),'limitations':'same exchange data, four retrospectively chosen symbols, not identity, fills or true independent blind testing'},indent=2)+'\n');print('checked',len(trades))
if __name__=='__main__':main()
