"""Equal-sleeve hypothetical spot reference with explicitly unpriced assets held in cash."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from .stage_oct31_spot_20261031 import ROOT,SPOT,START,END
OUT=Path('data/verify/nine-spot-reference-20261031-01');DEFINITION=Path('docs/九币10月末与现货对照-数据定义-20261031.md')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 receipts=json.loads((ROOT/'receipts.json').read_text());hashes={r['file']:r['sha256'] for r in receipts}
 frames={};expected=pd.date_range(pd.Timestamp(START,unit='ms',tz='UTC'),pd.Timestamp(END,unit='ms',tz='UTC')-pd.Timedelta(days=1),freq='D')
 for s in SPOT:
  p=ROOT/(s+'-spot.json');assert hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.name];rows=json.loads(p.read_text())
  if s=='LITUSDT':
   if rows:raise ValueError('LIT identity must be verified')
   continue
  ts=pd.DatetimeIndex(pd.to_datetime([int(r[0]) for r in rows],unit='ms',utc=True));v=np.asarray([[float(r[k]) for k in (1,2,3,4)] for r in rows]);
  if ts.has_duplicates or not ts.is_monotonic_increasing or len(ts)==0 or ts[-1]!=expected[-1] or (ts.to_series().diff().dropna()!=pd.Timedelta(days=1)).any():raise ValueError('bad daily grid '+s)
  if not np.isfinite(v).all() or (v<=0).any() or (v[:,2]>v.min(axis=1)).any() or (v[:,1]<v.max(axis=1)).any():raise ValueError('bad OHLC '+s)
  if s!='HYPEUSDT' and not ts.equals(expected):raise ValueError('incomplete spot '+s)
  if s=='HYPEUSDT' and ts[0]!=pd.Timestamp('2026-09-24',tz='UTC'):raise ValueError('unexpected HYPE listing')
  frames[s]=pd.DataFrame(v,index=ts,columns=['open','high','low','close'])
 symbols=[s for s in SPOT if s!='BTCUSDT'];dates=expected;series={};individual={};orders=[]
 for s in symbols+['BTCUSDT']:
  allocation=2000/9 if s!='BTCUSDT' else 2000.;quantity=0.;cash=allocation;values=[];entry=None
  for day in dates:
   if s in frames and day in frames[s].index and not (s=='HYPEUSDT' and day<pd.Timestamp('2026-09-25',tz='UTC')):
    bar=frames[s].loc[day]
    if not quantity:
     fill=float(bar.open)*1.0002;quantity=cash/(fill*1.001);fee=quantity*fill*.001;cash-=quantity*fill+fee;entry=day.isoformat();orders.append({'symbol':s,'time':entry,'quantity':quantity,'fill':fill,'fee':fee})
    value=cash+quantity*float(bar.close)
   else:value=cash
   values.append(float(value))
  series[s]=np.array(values);individual[s]={'allocation_usdt':allocation,'initial_execution':entry,'end_mark_usdt':values[-1], 'status':'UNAVAILABLE_CASH' if entry is None else 'AVAILABLE', 'end_estimated_sale_net_usdt':float(cash+quantity*float(frames[s].iloc[-1].close)*.9998*.999) if entry else allocation}
 portfolio=np.sum([series[s] for s in symbols],axis=0);peaks=np.maximum.accumulate(np.r_[2000.,portfolio])[1:]
 result={'status':'RETROSPECTIVE_NINE_SLEEVE_SPOT_PROXY','start':'2025-10-01T00:00:00Z','end_exclusive':'2026-10-31T00:00:00Z','initial':2000.,'equity_end':float(portfolio[-1]),'return_pct':float((portfolio[-1]/2000-1)*100),'mdd_daily_pct':float((portfolio/peaks-1).min()*100),'estimated_sale_net_usdt':sum(individual[s]['end_estimated_sale_net_usdt'] for s in symbols),'individual':individual,'orders':orders,'limitations':['User selected assets retrospectively.','HYPE bought no earlier than first complete post-listing UTC day; LIT unknown held cash.','Assumed spot 0.1% per side and 0.02% slippage, not actual account fees.','Daily close MDD not comparable to 5m MDD.']}
 OUT.mkdir();(OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');pd.DataFrame({'date':dates.astype(str),'equity':portfolio}).to_csv(OUT/'daily-equity.csv',index=False);print(json.dumps({k:result[k] for k in ('initial','equity_end','return_pct','mdd_daily_pct','estimated_sale_net_usdt','individual')},indent=2))
if __name__=='__main__':main()
