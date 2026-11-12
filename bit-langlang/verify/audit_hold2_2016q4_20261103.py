"""Direct raw 4h audit of held states and post-asof price descriptions."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.audit_2018_transition_20261102 import calc
S=Path('data/verify/market-hold2-2016q4-20261103-01');O=Path('data/verify/market-hold2-2016q4-independent-20261103-01')
def main():
 if O.exists():raise FileExistsError(O)
 a=pd.read_csv(S/'asof.csv',dtype={'year':str});j=pd.read_csv(S/'joint.csv',dtype={'year':str});fut=pd.read_csv(S/'future.csv',dtype={'year':str});local={};count=returns=0;files=[Path(__file__),S/'asof.csv',S/'joint.csv',S/'future.csv']
 for year in ('2016q4',):
  d=Path(f'data/market/btc-{year}-usd-cross-20261102-01');base=Path(f'data/verify/market-{year}-position-20261102-01');flags=[pd.Timestamp(v).floor('D') for v in json.loads((base/'summary.json').read_text())['results']['bitstamp_bitfinex']['flags_utc']];files += [base/'summary.json',base/'asof.csv']
  for name in ('bitstamp','bitfinex'):
   p=d/(name+'-4h.csv.gz');files.append(p);bars=pd.read_csv(p);bars.index=pd.to_datetime(bars.ts,unit='ms',utc=True);bars=bars[~bars.index.floor('D').isin(flags)]
   original=pd.read_csv(base/'asof.csv');original=original[original.source==name].set_index('as_of_utc')
   for r in a[(a.year==year)&(a.source==name)].itertuples():
    t=pd.Timestamp(r.as_of_utc);prev=original.loc[r.as_of_utc];assert (r.position,r.swing,r.old_active)==(prev.position,prev.swing,prev.active)
    result='UNKNOWN'
    if r.position=='INSIDE':result='INSIDE'
    elif r.position in ('ABOVE','BELOW'):
     key='h' if r.position=='ABOVE' else 'l';known=pd.Timestamp(getattr(r,key+'_known'));level=getattr(r,key+'_new')
     if known>t-pd.Timedelta(days=2):result='WAIT_CONFIRM'
     else:
      old=calc(bars,t,2)
      if old is None:result='UNKNOWN'
      else:
       close1=old.close.iloc[5];close2=old.close.iloc[11]
       result=('HELD_UP_2' if r.position=='ABOVE' else 'HELD_DOWN_2') if ((close1>level and close2>level) if r.position=='ABOVE' else (close1<level and close2<level)) else 'OUTSIDE_UNHELD'
    assert result==r.held_state,(year,name,t,result,r.held_state);local[(year,name,r.as_of_utc)]=result
    out=fut[(fut.year==year)&(fut.source==name)&(fut.as_of_utc==r.as_of_utc)].iloc[0];assert out.held_state==result
    before=calc(bars,t,1);after=calc(bars,t+pd.Timedelta(days=28),28);status='COMPLETE_DESCRIPTIVE' if before is not None and after is not None else 'UNKNOWN_INCOMPLETE';assert status==out.future_28_status,(year,name,t,status,out.future_28_status)
    if before is not None and after is not None:
     p0=before.close.iloc[-1];cl=after.close.iloc[-1];hi=after.high.max();lo=after.low.min();assert np.isclose(p0,out.asof_close) and np.isclose(cl,out.close_28) and np.isclose(hi,out.high_28) and np.isclose(lo,out.low_28) and np.isclose((cl/p0-1)*100,out.close_change_pct) and np.isclose((hi/p0-1)*100,out.high_change_pct) and np.isclose((lo/p0-1)*100,out.low_change_pct) and out.available_time==(t+pd.Timedelta(days=28)).isoformat()
    if r.position in ('ABOVE','BELOW'):
     level=r.h_new if r.position=='ABOVE' else r.l_new
     for n in (7,28):
      status='NO_RETURN';when=None
      for i in range(n):
       end=t+pd.Timedelta(days=i+1);day=calc(bars,end,1)
       if day is None:status='UNKNOWN_INCOMPLETE';break
       cl=day.close.iloc[-1]
       if (r.position=='ABOVE' and cl<level) or (r.position=='BELOW' and cl>level):status='RETURN';when=end.isoformat();break
      assert status==out[f'return_{n}']
      if when:assert when==out[f'return_time_{n}']
      returns+=1
    count+=1
 for r in j.itertuples():
  a=local[(r.year,'bitstamp',r.as_of_utc)];b=local[(r.year,'bitfinex',r.as_of_utc)];exp='UNKNOWN' if a in ('UNKNOWN','WAIT_CONFIRM') or b in ('UNKNOWN','WAIT_CONFIRM') else 'JOINT_'+a if a==b and a in ('HELD_UP_2','HELD_DOWN_2','INSIDE') else 'JOINT_OUTSIDE_UNHELD' if a==b else 'DISAGREE';assert r.joint_held==exp
 O.mkdir();(O/'summary.json').write_text(json.dumps({'status':'PASS','source_points':count,'forward_return_checks':returns,'joint_points':len(j),'scope':'uses earlier independently checked pivot fields; held and forward results recomputed from raw 4h; no independent human truth','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',count,returns,len(j))
if __name__=='__main__':main()
