"""Recompute pivots, expiry, events and consensus directly from 4h input."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.audit_2018_transition_20261102 import calc,rel
R=Path('data/verify');DATA=Path('data/market/btc-2017-usd-cross-20261102-01');SRC=R/'market-2017-pivot-guard-20261102-01';OUT=R/'market-2017-pivot-independent-20261102-01'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 records=pd.read_csv(SRC/'asof-guarded.csv');events=pd.read_csv(SRC/'events.csv');joint=pd.read_csv(SRC/'joint.csv');results={};count=checks=0
 for venue in ('bitstamp','coinbase'):
  f=pd.read_csv(DATA/(venue+'-4h.csv.gz'));f.index=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.drop(pd.Timestamp('2017-03-07 08:00',tz='UTC'),errors='ignore');out={}
  for r in records[records.source==venue].itertuples():
   t=pd.Timestamp(r.as_of_utc);big,small,long=(calc(f,t,n) for n in (28,8,56));br,sr,lr=map(rel,(big,small,long));assert (br,sr,lr)==(r.big_relation,r.small_relation,r.long_relation)
   pts={};swing='UNKNOWN'
   if long is not None:
    days=long.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'));high=[];low=[]
    for j in range(2,54):
     window=days.iloc[j-2:j+3];is_h=window.high.iloc[2]>window.high.drop(window.index[2]).max();is_l=window.low.iloc[2]<window.low.drop(window.index[2]).min()
     if is_h and not is_l:high.append((window.index[2],window.high.iloc[2]))
     if is_l and not is_h:low.append((window.index[2],window.low.iloc[2]))
    if len(high)>=2 and len(low)>=2:
     pts={'h_old':high[-2],'h_new':high[-1],'l_old':low[-2],'l_new':low[-1]};swing='SWING_UP' if high[-1][1]>high[-2][1] and low[-1][1]>low[-2][1] else 'SWING_DOWN' if high[-1][1]<high[-2][1] and low[-1][1]<low[-2][1] else 'SWING_MIXED'
   assert swing==r.swing
   for key,(day,price) in pts.items():
    assert day.isoformat()==getattr(r,key+'_day') and (day+pd.Timedelta(days=3)).isoformat()==getattr(r,key+'_known') and np.isclose(price,getattr(r,key+'_price')) and day+pd.Timedelta(days=3)<=t
   active='UNKNOWN_INPUT';stale_time=None
   if pts:
    hi=pts['h_new'][1];lo=pts['l_new'][1];active='UNKNOWN_BOUNDARY' if hi<=lo else 'ACTIVE_'+swing[6:];hits=[]
    if hi>lo:
     for side in ('h_new','l_new'):
      day,threshold=pts[side];start=day+pd.Timedelta(days=3)
      for j in range((t-start).days):
       end=start+pd.Timedelta(days=j+1);d=calc(f,end,1)
       if d is None:active='UNKNOWN_HISTORY';break
       c=d.close.iloc[-1]
       if (side=='h_new' and c>threshold) or (side=='l_new' and c<threshold):hits.append((end,'HIGH' if side=='h_new' else 'LOW',c));break
     if active!='UNKNOWN_HISTORY' and hits:
      hits.sort();when,side,price=hits[0];active='STALE_BROKEN_'+side;stale_time=when.isoformat();assert np.isclose(price,r.stale_close)
   assert active==r.active,(venue,t,'active',active,r.active)
   if stale_time:assert stale_time==r.stale_time_utc
   out[r.as_of_utc]={'active':active,'long':lr}
   season='UNKNOWN'
   if big is not None and small is not None and br=='INSIDE' and sr=='UP' and big.close.iloc[-1]>(big.high.max()+big.low.min())/2:season='SPRING'
   spring=autumn='UNKNOWN'
   if all(z is not None for z in (big,small,long)):
    spring='YES' if season=='SPRING' and lr in ('DOWN','INSIDE') else 'NO';x=big.iloc[-84:];autumn='YES' if br=='UP' and sr=='DOWN' and lr=='UP' and big.close.iloc[-1]<(x.high.max()+x.low.min())/2 else 'NO'
   assert (spring,autumn)==(r.spring_watch,r.autumn_watch)
   for kind in ('fixed_28','pivot'):
    e=events[(events.source==venue)&(events.as_of_utc==r.as_of_utc)&(events.kind==kind)].iloc[0];bounds=(big.high.max(),big.low.min()) if kind=='fixed_28' and big is not None else (pts['h_new'][1],pts['l_new'][1]) if kind=='pivot' and pts else None
    status='UNKNOWN_INPUT';follow='UNKNOWN';first=ret=None
    if bounds:
     hi,lo=bounds;assert np.isclose(hi,e.upper) and np.isclose(lo,e.lower)
     if hi<=lo:status='UNKNOWN_BOUNDARY'
     else:
      status='UNRESOLVED_28D'
      for i in range(28):
       end=t+pd.Timedelta(days=i+1);d=calc(f,end,1)
       if d is None:status='UNKNOWN_INCOMPLETE';break
       c=d.close.iloc[-1]
       if c>hi or c<lo:status='UPPER_BREAK' if c>hi else 'LOWER_BREAK';first=end;break
      if first:
       follow='NO_RETURN'
       for i in range(7):
        end=first+pd.Timedelta(days=i+1);d=calc(f,end,1)
        if d is None:follow='UNKNOWN_INCOMPLETE';break
        c=d.close.iloc[-1]
        if (status=='UPPER_BREAK' and c<hi) or (status=='LOWER_BREAK' and c>lo):follow='RETURN';ret=end;break
      elif status=='UNRESOLVED_28D':follow='NO_BREAK'
    assert (status,follow)==(e.status,e.follow),(venue,t,kind,status,follow,e.status,e.follow)
    if first:assert first.isoformat()==e.event_time
    if ret:assert ret.isoformat()==e.return_time
    prev=calc(f,t,1);state='UNKNOWN_ASOF'
    if bounds and status!='UNKNOWN_BOUNDARY' and prev is not None:
     c=prev.close.iloc[-1];state='ALREADY_ABOVE' if c>hi else 'ALREADY_BELOW' if c<lo else 'WITHIN_OR_EQUAL'
    assert e.asof_state==state and e.new_event==(status if state=='WITHIN_OR_EQUAL' else state)
    checks+=1
   count+=1
  results[venue]=out
 for r in joint.itertuples():
  a=results['bitstamp'][r.as_of_utc];b=results['coinbase'][r.as_of_utc];s=a['active'];exp='UNKNOWN'
  if s in ('ACTIVE_UP','ACTIVE_DOWN') and s==b['active'] and 'UNKNOWN' not in (a['long'],b['long']):
   exp='JOINT_POSSIBLE_UP' if s=='ACTIVE_UP' and a['long'] in ('DOWN','INSIDE') and b['long'] in ('DOWN','INSIDE') else 'JOINT_POSSIBLE_DOWN' if s=='ACTIVE_DOWN' and a['long']==b['long']=='UP' else 'NO_JOINT_CANDIDATE'
  assert exp==r.joint
 files=[Path(__file__),DATA/'bitstamp-4h.csv.gz',DATA/'coinbase-4h.csv.gz',SRC/'asof-guarded.csv',SRC/'events.csv',SRC/'joint.csv'];OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'points':count,'event_rows':checks,'joint_points':len(joint),'status':'PASS','scope':'raw 4h recomputation; uses shared relation helper; not human or phase truth','input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print('PASS',count,checks,len(joint))
if __name__=='__main__':main()
