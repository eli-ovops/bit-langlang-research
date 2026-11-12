"""Direct 4h independent verification of frozen decisions and return events."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.audit_2018_transition_20261102 import calc,rel
ROOT=Path('data/verify');OUT=ROOT/'market-2019-independent-20261102-01'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 checked=events=0;inputs=[]
 for sub in ['market-2019-manual-20261102-01','market-2019-kucoin-20261102-01']:
  p=ROOT/sub;paths=[p/'bars-4h.csv.gz',p/'asof.csv',p/'future.csv'];inputs+=paths
  f=pd.read_csv(paths[0]);f.index=pd.to_datetime(f.ts,unit='ms',utc=True);a=pd.read_csv(paths[1]);future=pd.read_csv(paths[2])
  for row,e in zip(a.itertuples(),future.itertuples()):
   assert row.as_of_utc==e.as_of_utc;t=pd.Timestamp(row.as_of_utc);big,small,long=(calc(f,t,n) for n in (28,8,56));br,sr,lr=map(rel,(big,small,long));assert (br,sr,lr)==(row.big_relation,row.small_relation,row.long_relation)
   season='UNKNOWN'
   if big is not None and small is not None:
    if br=='INSIDE' and sr=='UP' and big.close.iloc[-1]>(big.high.max()+big.low.min())/2:season='SPRING'
    elif br=='UP' and sr=='UP':season='SUMMER'
    elif br=='DOWN' and sr=='DOWN':season='WINTER'
   assert season==row.season
   spring=autumn='UNKNOWN'
   if all(x is not None for x in (big,small,long)):
    spring='YES' if season=='SPRING' and lr in ('DOWN','INSIDE') else 'NO';recent=big.iloc[-84:];autumn='YES' if br=='UP' and sr=='DOWN' and lr=='UP' and big.close.iloc[-1]<(recent.high.max()+recent.low.min())/2 else 'NO'
   assert (spring,autumn)==(row.spring_watch,row.autumn_watch)
   status='UNKNOWN_INPUT';follow='UNKNOWN';first=None;ret=None
   if big is not None:
    hi,lo=big.high.max(),big.low.min();assert np.isclose(hi,e.frozen_upper) and np.isclose(lo,e.frozen_lower);status='UNRESOLVED_28D'
    for i in range(28):
     end=t+pd.Timedelta(days=i+1);day=calc(f,end,1)
     if day is None:status='UNKNOWN_INCOMPLETE';break
     c=day.close.iloc[-1]
     if c>hi or c<lo:status='UPPER_BREAK' if c>hi else 'LOWER_BREAK';first=end;break
    if first is not None:
     follow='NO_RETURN_7D'
     for i in range(7):
      end=first+pd.Timedelta(days=i+1);day=calc(f,end,1)
      if day is None:follow='UNKNOWN_INCOMPLETE';break
      c=day.close.iloc[-1]
      if (status=='UPPER_BREAK' and c<hi) or (status=='LOWER_BREAK' and c>lo):follow='RETURN_INSIDE_SIDE';ret=end;break
    elif status=='UNRESOLVED_28D':follow='NO_BREAK'
   assert (status,follow)==(e.first,e.followup),(sub,t,status,follow,e.first,e.followup)
   if first is not None:assert first.isoformat()==e.first_time_utc
   if ret is not None:assert ret.isoformat()==e.return_time_utc
   checked+=1;events+=first is not None
 OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'points_checked':checked,'breaks_checked':events,'result':'PASS','scope':'raw bars, first event, return, labels; prices not certified and no human ground truth','inputs_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs+[Path(__file__),Path('verify/audit_2018_transition_20261102.py')]}},indent=2)+'\n');print('PASS',checked,events)
if __name__=='__main__':main()
