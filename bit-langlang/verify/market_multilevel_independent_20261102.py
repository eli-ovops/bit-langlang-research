"""Recompute labels from direct 5m slices, independently of aggregation helper."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
SRC=Path('data/verify/market-multilevel-20261102-01');GUARD=Path('data/verify/market-multilevel-guard-20261102-01');OUT=Path('data/verify/market-multilevel-independent-20261102-01')
JOBS={'main':Path('data/market/nine-futures-stage-oct31-20261031-01/BTCUSDT_5m.csv.gz'),'stress2021':Path('data/market/four-earlier-2021-20261031-01/BTCUSDT_5m.csv.gz')}
def relation(a,b):
 if b[0]>a[0] and b[1]>a[1]:return 'UP'
 if b[0]<a[0] and b[1]<a[1]:return 'DOWN'
 if b[0]<=a[0] and b[1]>=a[1]:return 'INSIDE'
 return 'MIXED'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 results={}
 for name,path in JOBS.items():
  f=pd.read_csv(path);ts=f.ts.to_numpy();hi=f.high.to_numpy();lo=f.low.to_numpy();close=f.close.to_numpy();rows=pd.read_csv(SRC/f'{name}-weekly.csv');guard=pd.read_csv(GUARD/f'{name}-weekly.csv');shift=pd.read_csv(SRC/f'{name}-shift24.csv');future=pd.read_csv(SRC/f'{name}-future.csv');assert len(rows)==len(guard)==len(shift)==len(future)
  def calc(t):
   ms=t.value//10**6;i=ts.searchsorted(ms);assert i>0 and ts[i-1]==ms-300000
   def edges(left,right):
    a=ts.searchsorted(ms-left*86400000);b=ts.searchsorted(ms-right*86400000);v=ts[a:b];assert len(v)==(left-right)*288 and np.all(np.diff(v)==300000);return (float(hi[a:b].max()),float(lo[a:b].min()))
   big1,big2,s1,s2=edges(28,14),edges(14,0),edges(8,4),edges(4,0);br,sr=relation(big1,big2),relation(s1,s2);mid=(max(big1[0],big2[0])+min(big1[1],big2[1]))/2;above=close[i-1]>mid
   label='SPRING' if (br,sr)==('INSIDE','UP') and above else 'SUMMER' if (br,sr)==('UP','UP') else 'AUTUMN' if (br,sr)==('UP','DOWN') else 'WINTER' if (br,sr)==('DOWN','DOWN') else 'UNKNOWN'
   return br,sr,label,big1,big2,s1,s2,float(close[i-1])
  nfuture=0
  for r,g,s,u in zip(rows.itertuples(index=False),guard.itertuples(index=False),shift.itertuples(index=False),future.itertuples(index=False)):
   t=pd.Timestamp(r.as_of_utc);br,sr,label,b1,b2,s1,s2,price=calc(t);assert (r.big_relation,r.small_relation,r.season)==(br,sr,label) and (g.big_relation,g.small_relation,g.guard_season)==(br,sr,'UNKNOWN' if (br,sr)==('UP','DOWN') else label)
   assert r.conflict==((br,sr) in [('UP','DOWN'),('DOWN','UP')]);assert abs(r.prior_close-price)<1e-8
   for attr,val in [('big_old_high',b1[0]),('big_old_low',b1[1]),('big_new_high',b2[0]),('big_new_low',b2[1]),('small_old_high',s1[0]),('small_old_low',s1[1]),('small_new_high',s2[0]),('small_new_low',s2[1])]:assert abs(getattr(r,attr)-val)<1e-8
   assert s.plus_24h_season==calc(t+pd.Timedelta(days=1))[2]
   ms=t.value//10**6;i=ts.searchsorted(ms);j=ts.searchsorted(ms+7*86400000);v=ts[i:j]
   if len(v)==7*288 and v[0]==ms and v[-1]==ms+7*86400000-300000 and np.all(np.diff(v)==300000):
    assert u.status=='POST_HOC_DESCRIPTIVE';assert abs(u.close_change_pct-(close[j-1]/price-1)*100)<1e-8 and abs(u.high_change_pct-(hi[i:j].max()/price-1)*100)<1e-8 and abs(u.low_change_pct-(lo[i:j].min()/price-1)*100)<1e-8;nfuture+=1
   else:assert u.status=='UNKNOWN_FUTURE_OR_PAST'
  results[name]={'checked_points':len(rows),'checked_shifted_points':len(rows),'checked_complete_future_windows':nfuture}
 OUT.mkdir(parents=True);(OUT/'summary.json').write_text(json.dumps({'status':'PASS','results':results,'limits':['same raw market source; not reference-label validation','does not establish predictive power or identity']},indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
