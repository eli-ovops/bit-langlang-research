"""Recheck returns directly from 4h bars and capture unknown coverage."""
from pathlib import Path
import hashlib,json
import pandas as pd,numpy as np
R=Path('data/verify');OUT=R/'market-2023-return-independent-20261102-01'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 result=pd.read_csv(R/'market-2023-return-windows-20261102-01/returns.csv');count=0;files=[Path(__file__),R/'market-2023-return-windows-20261102-01/returns.csv']
 for venue in ('binance','kucoin'):
  p=R/('market-2023-'+venue+'-20261102-01');files += [p/'bars-4h.csv.gz',p/'future.csv'];f=pd.read_csv(p/'bars-4h.csv.gz');f.index=pd.to_datetime(f.ts,unit='ms',utc=True);ev=pd.read_csv(p/'future.csv')
  for e in ev.itertuples():
   r=result[(result.source==venue)&(result.as_of_utc==e.as_of_utc)].iloc[0]
   if e.first not in ('UPPER_BREAK','LOWER_BREAK'):continue
   first=pd.Timestamp(e.first_time_utc);bound=e.frozen_upper if e.first=='UPPER_BREAK' else e.frozen_lower
   for n in (7,28):
    status='NO_RETURN';when=None;price=None
    for i in range(n):
     start=first+pd.Timedelta(days=i);idx=pd.date_range(start,periods=6,freq='4h');z=f.reindex(idx)
     if z[['open','high','low','close']].isna().any().any():status='UNKNOWN_INCOMPLETE';break
     v=z[['open','high','low','close']]
     if not np.isfinite(v.to_numpy()).all() or (v<=0).any().any() or (z.low>v.min(axis=1)).any() or (z.high<v.max(axis=1)).any():status='UNKNOWN_INCOMPLETE';break
     c=z.close.iloc[-1]
     if (e.first=='UPPER_BREAK' and c<bound) or (e.first=='LOWER_BREAK' and c>bound):status='RETURN';when=(start+pd.Timedelta(days=1)).isoformat();price=c;break
    assert r[f'status_{n}']==status,(venue,e.as_of_utc,n,status)
    if when:assert r[f'return_time_{n}']==when and np.isclose(r[f'return_price_{n}'],price)
    count+=1
 OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'checks':count,'result':'PASS','scope':'direct raw 4h, 7/28 day return timing; not independent phase labels','inputs_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS checks',count)
if __name__=='__main__':main()
