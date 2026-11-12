"""Independent direct native-bar slicing and future window checks, both venues."""
import json
from pathlib import Path
import numpy as np,pandas as pd
DATA=Path('data/market/btc-2020-cross-20261102-02');SRC=Path('data/verify/market-2020-cross-20261102-01');OUT=Path('data/verify/market-2020-cross-independent-20261102-01')
def rel(a,b):
 if b[0]>a[0] and b[1]>a[1]:return 'UP'
 if b[0]<a[0] and b[1]<a[1]:return 'DOWN'
 if b[0]<=a[0] and b[1]>=a[1]:return 'INSIDE'
 return 'MIXED'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 records=pd.read_csv(SRC/'layers.csv');future=pd.read_csv(SRC/'future-descriptive.csv');jobs={'binance_perp':(DATA/'BTCUSDT-binance-5m.csv.gz',300000),'kucoin_spot':(DATA/'BTC-USDT-kucoin-spot-4h.csv.gz',14400000)};results={}
 for name,(path,step) in jobs.items():
  f=pd.read_csv(path);ts=f.ts.to_numpy();hi=f.high.to_numpy();lo=f.low.to_numpy();close=f.close.to_numpy();count=0;future_count=0
  def edges(ms,left,right):
   start=ms-left*86400000;end=ms-right*86400000;a=ts.searchsorted(start);b=ts.searchsorted(end);v=ts[a:b]
   if len(v)!=(end-start)//step or len(v)==0 or v[0]!=start or v[-1]!=end-step or (len(v)>1 and not np.all(np.diff(v)==step)):return None
   return float(hi[a:b].max()),float(lo[a:b].min())
  for r in records[records.source==name].itertuples(index=False):
   ms=pd.Timestamp(r.as_of_utc).value//10**6;i=ts.searchsorted(ms);prior=close[i-1] if i>0 and ts[i-1]==ms-step else None
   e28a,e28b,e8a,e8b,e56a,e56b=edges(ms,28,14),edges(ms,14,0),edges(ms,8,4),edges(ms,4,0),edges(ms,56,28),edges(ms,28,0)
   validbig=e28a is not None and e28b is not None;validsmall=e8a is not None and e8b is not None;validlong=e56a is not None and e56b is not None
   br=rel(e28a,e28b) if validbig else 'UNKNOWN';sr=rel(e8a,e8b) if validsmall else 'UNKNOWN';lr=rel(e56a,e56b) if validlong else 'UNKNOWN';assert (r.big_valid,r.small_valid,r.long_valid)==(validbig,validsmall,validlong);assert (r.big_relation,r.small_relation,r.long_relation)==(br,sr,lr)
   label='UNKNOWN';spring='UNKNOWN';autumn='UNKNOWN'
   if validbig and validsmall:
    above=prior>(max(e28a[0],e28b[0])+min(e28a[1],e28b[1]))/2
    if (br,sr)==('INSIDE','UP') and above:label='SPRING'
    elif (br,sr)==('UP','UP'):label='SUMMER'
    elif (br,sr)==('DOWN','DOWN'):label='WINTER'
    if validlong:
     mid=(e28b[0]+e28b[1])/2;spring='YES' if label=='SPRING' and lr in ('DOWN','INSIDE') else 'NO';autumn='YES' if (br,sr)==('UP','DOWN') and lr=='UP' and prior<mid else 'NO'
   assert (r.season,r.spring_watch,r.autumn_watch)==(label,spring,autumn)
   for days in (7,28):
    z=future[(future.source==name)&(future.as_of_utc==r.as_of_utc)&(future.future_days==days)];assert len(z)==1;row=z.iloc[0];a=ts.searchsorted(ms);end=ms+days*86400000;b=ts.searchsorted(end);v=ts[a:b]
    if prior is not None and validbig and validsmall and len(v)==days*86400000//step and v[0]==ms and v[-1]==end-step and (len(v)<2 or np.all(np.diff(v)==step)):
     assert row.status=='AFTER_THE_FACT_NOT_TRUTH';assert abs(row.close_pct-(close[b-1]/prior-1)*100)<1e-8 and abs(row.high_pct-(hi[a:b].max()/prior-1)*100)<1e-8 and abs(row.low_pct-(lo[a:b].min()/prior-1)*100)<1e-8;future_count+=1
    else:assert row.status=='UNKNOWN_INSUFFICIENT_COVERAGE'
   count+=1
  results[name]={'all_points':count,'complete_future_windows':future_count}
 OUT.mkdir(parents=True);(OUT/'summary.json').write_text(json.dumps({'status':'PASS','results':results,'limits':['cross-validation uses both raw datasets, no independent human stage reference','no claim of predictive or trading validity']},indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
