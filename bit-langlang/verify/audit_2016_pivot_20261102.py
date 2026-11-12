"""Independent direct 4h resampling audit for 2016 structural research."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
from verify.audit_2018_transition_20261102 import calc,rel
ROOT=Path('data/verify/market-2016-pivot-20261102-01');DATA=Path('data/market/btc-2016-usd-cross-20261102-01');COR=Path('data/verify/market-2016-pivot-correction-20261102-01');OUT=Path('data/verify/market-2016-pivot-independent-20261102-01')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 a=pd.read_csv(ROOT/'asof.csv');e=pd.read_csv(ROOT/'events.csv');c=pd.read_csv(COR/'events-corrected.csv');points=events=0
 for name in ('bitstamp','coinbase'):
  f=pd.read_csv(DATA/(name+'-4h.csv.gz'));f.index=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.drop(pd.Timestamp('2016-06-07 12:00',tz='UTC'),errors='ignore')
  for r in a[a.source==name].itertuples():
   t=pd.Timestamp(r.as_of_utc);big,small,long=(calc(f,t,n) for n in (28,8,56));br,sr,lr=map(rel,(big,small,long));assert (br,sr,lr)==(r.big_relation,r.small_relation,r.long_relation),(name,t,'fixed')
   swing='UNKNOWN';pts={}
   if long is not None:
    daily=long.resample('D').agg(high=('high','max'),low=('low','min'));hh=[];ll=[]
    for i in range(2,54):
     z=daily.iloc[i-2:i+3];is_h=z.high.iloc[2]>z.high.drop(z.index[2]).max();is_l=z.low.iloc[2]<z.low.drop(z.index[2]).min()
     if is_h and not is_l:hh.append((z.index[2],z.high.iloc[2]))
     if is_l and not is_h:ll.append((z.index[2],z.low.iloc[2]))
    if len(hh)>=2 and len(ll)>=2:
     pts={'h_old':hh[-2],'h_new':hh[-1],'l_old':ll[-2],'l_new':ll[-1]};hu=hh[-1][1]>hh[-2][1];lu=ll[-1][1]>ll[-2][1];hd=hh[-1][1]<hh[-2][1];ld=ll[-1][1]<ll[-2][1];swing='SWING_UP' if hu and lu else 'SWING_DOWN' if hd and ld else 'SWING_MIXED'
   assert swing==r.swing,(name,t,'swing',swing,r.swing)
   for key,(day,price) in pts.items():
    assert getattr(r,key+'_day')==day.isoformat() and getattr(r,key+'_known')==(day+pd.Timedelta(days=3)).isoformat() and np.isclose(getattr(r,key+'_price'),price)
    assert day+pd.Timedelta(days=3)<=t
   spring=autumn='UNKNOWN'
   if all(z is not None for z in (big,small,long)):
    season='SPRING' if br=='INSIDE' and sr=='UP' and big.close.iloc[-1]>(big.high.max()+big.low.min())/2 else 'UNKNOWN'
    spring='YES' if season=='SPRING' and lr in ('DOWN','INSIDE') else 'NO';recent=big.iloc[-84:];autumn='YES' if br=='UP' and sr=='DOWN' and lr=='UP' and big.close.iloc[-1]<(recent.high.max()+recent.low.min())/2 else 'NO'
   assert (spring,autumn)==(r.spring_watch,r.autumn_watch)
   for kind in ('fixed_28','pivot'):
    original=e[(e.source==name)&(e.as_of_utc==r.as_of_utc)&(e.kind==kind)].iloc[0];corrected=c[(c.source==name)&(c.as_of_utc==r.as_of_utc)&(c.kind==kind)].iloc[0]
    bounds=(big.high.max(),big.low.min()) if kind=='fixed_28' and big is not None else (pts['h_new'][1],pts['l_new'][1]) if kind=='pivot' and pts else None
    status='UNKNOWN_INPUT';follow='UNKNOWN';first=None;ret=None
    if bounds:
     hi,lo=bounds;assert np.isclose(original.upper,hi) and np.isclose(original.lower,lo)
     if hi<=lo:status='UNKNOWN_BOUNDARY'
     else:
      status='UNRESOLVED_28D'
      for i in range(28):
       end=t+pd.Timedelta(days=i+1);day=calc(f,end,1)
       if day is None:status='UNKNOWN_INCOMPLETE';break
       close=day.close.iloc[-1]
       if close>hi or close<lo:status='UPPER_BREAK' if close>hi else 'LOWER_BREAK';first=end;break
      if first is not None:
       follow='NO_RETURN'
       for i in range(7):
        end=first+pd.Timedelta(days=i+1);day=calc(f,end,1)
        if day is None:follow='UNKNOWN_INCOMPLETE';break
        close=day.close.iloc[-1]
        if (status=='UPPER_BREAK' and close<hi) or (status=='LOWER_BREAK' and close>lo):follow='RETURN';ret=end;break
      elif status=='UNRESOLVED_28D':follow='NO_BREAK'
    assert (status,follow)==(original.status,original.follow),(name,t,kind,status,follow,original.status,original.follow)
    if first is not None:assert first.isoformat()==original.event_time
    if ret is not None:assert ret.isoformat()==original.return_time
    previous=calc(f,t,1);state='UNKNOWN_ASOF'
    if bounds and status!='UNKNOWN_BOUNDARY' and previous is not None:
     close=previous.close.iloc[-1];state='ALREADY_ABOVE_ASOF' if close>hi else 'ALREADY_BELOW_ASOF' if close<lo else 'WITHIN_OR_EQUAL_ASOF'
    assert state==corrected.asof_boundary_state,(name,t,kind,state,corrected.asof_boundary_state)
    assert corrected.new_break_status==(status if state=='WITHIN_OR_EQUAL_ASOF' else state)
    events+=1
   points+=1
 files=[Path(__file__),DATA/'bitstamp-4h.csv.gz',DATA/'coinbase-4h.csv.gz',ROOT/'asof.csv',ROOT/'events.csv',COR/'events-corrected.csv'];OUT.mkdir();(OUT/'summary.json').write_text(json.dumps({'points_checked':points,'event_rows_checked':events,'status':'PASS','scope':'Raw 4h calculations, flagged bar excluded; not independent phase truth.','input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},indent=2)+'\n');print('PASS points',points,'events',events)
if __name__=='__main__':main()
