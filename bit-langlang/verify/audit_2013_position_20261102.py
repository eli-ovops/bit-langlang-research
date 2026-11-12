"""Independent raw-4h reconstruction of pair facts and future outcomes."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.audit_2018_transition_20261102 import calc,rel
ROOT=Path('data/verify/market-2013-position-20261102-01');BASE=Path('data/market/btc-2013-usd-cross-20261102-01');ALT=BASE;OUT=Path('data/verify/market-2013-position-independent-20261102-01')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 A=pd.read_csv(ROOT/'asof.csv');F=pd.read_csv(ROOT/'future.csv');Q=pd.read_csv(ROOT/'pairs.csv');summary=json.loads((ROOT/'summary.json').read_text());allrows={};n=0;futurechecks=0;fixedchecks=0
 paths={'bitstamp':BASE/'bitstamp-4h.csv.gz','bitfinex':ALT/'bitfinex-4h.csv.gz'}
 for pair in ('bitstamp_bitfinex',):
  flags=[pd.Timestamp(s).floor('D') for s in summary['results'][pair]['flags_utc']];other=pair.split('_')[1];local={}
  for name in ('bitstamp',other):
   f=pd.read_csv(paths[name]);f.index=pd.to_datetime(f.ts,unit='ms',utc=True);f=f[~f.index.floor('D').isin(flags)]
   for r in A[(A.pair==pair)&(A.source==name)].itertuples():
    t=pd.Timestamp(r.as_of_utc);big,small,long=(calc(f,t,i) for i in (28,8,56));br,sr,lr=map(rel,(big,small,long));assert (br,sr,lr)==(r.big_relation,r.small_relation,r.long_relation)
    pts={};swing='UNKNOWN';days=None
    if long is not None:
     days=long.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'));hs=[];ls=[]
     for j in range(2,54):
      w=days.iloc[j-2:j+3];h=w.high.iloc[2]>w.high.drop(w.index[2]).max();l=w.low.iloc[2]<w.low.drop(w.index[2]).min()
      if h and not l:hs.append((w.index[2],w.high.iloc[2]))
      if l and not h:ls.append((w.index[2],w.low.iloc[2]))
     if len(hs)>=2 and len(ls)>=2:
      pts={'h_old':hs[-2],'h_new':hs[-1],'l_old':ls[-2],'l_new':ls[-1]};swing='SWING_UP' if hs[-1][1]>hs[-2][1] and ls[-1][1]>ls[-2][1] else 'SWING_DOWN' if hs[-1][1]<hs[-2][1] and ls[-1][1]<ls[-2][1] else 'SWING_MIXED'
    assert swing==r.swing,(pair,name,t,'swing')
    for key,(day,price) in pts.items():assert getattr(r,key+'_day')==day.isoformat() and getattr(r,key+'_known')==(day+pd.Timedelta(days=3)).isoformat() and np.isclose(getattr(r,key+'_price'),price) and day+pd.Timedelta(days=3)<=t
    active='UNKNOWN_INPUT';position='UNKNOWN'
    if pts:
     hi=pts['h_new'][1];lo=pts['l_new'][1]
     if hi<=lo:active='UNKNOWN_BOUNDARY'
     else:
      active='ACTIVE_'+swing[6:];hits=[]
      for key in ('h_new','l_new'):
       day,threshold=pts[key];start=day+pd.Timedelta(days=3)
       for i in range((t-start).days):
        end=start+pd.Timedelta(days=i+1);z=calc(f,end,1)
        if z is None:active='UNKNOWN_HISTORY';break
        close=z.close.iloc[-1]
        if (key=='h_new' and close>threshold) or (key=='l_new' and close<threshold):hits.append((end,'HIGH' if key=='h_new' else 'LOW',close));break
      if active!='UNKNOWN_HISTORY' and hits:
       hits.sort();when,side,price=hits[0];active='STALE_BROKEN_'+side;assert when.isoformat()==r.stale_time_utc and np.isclose(price,r.stale_close)
      previous=calc(f,t,1)
      if previous is not None:
       p=previous.close.iloc[-1];position='ABOVE' if p>hi else 'BELOW' if p<lo else 'INSIDE'
    assert (active,position)==(r.active,r.position),(pair,name,t,active,position,r.active,r.position)
    spring=autumn='UNKNOWN'
    if all(x is not None for x in (big,small,long)):
     prior=big.close.iloc[-1];season='SPRING' if br=='INSIDE' and sr=='UP' and prior>(big.high.max()+big.low.min())/2 else 'UNKNOWN';spring='YES' if season=='SPRING' and lr in ('DOWN','INSIDE') else 'NO';recent=big.iloc[-84:];autumn='YES' if br=='UP' and sr=='DOWN' and lr=='UP' and prior<(recent.high.max()+recent.low.min())/2 else 'NO'
    assert (spring,autumn)==(r.spring_watch,r.autumn_watch)
    local[(name,r.as_of_utc)]={'position':position,'active':active,'long_relation':lr}
    y=F[(F.pair==pair)&(F.source==name)&(F.as_of_utc==r.as_of_utc)].iloc[0];assert y.position==position
    if position in ('ABOVE','BELOW'):
     bound=pts['h_new'][1] if position=='ABOVE' else pts['l_new'][1];assert np.isclose(bound,y.bound)
     for nday in (7,28):
      status='NO_RETURN';when=None;price=None
      for i in range(nday):
       end=t+pd.Timedelta(days=i+1);d=calc(f,end,1)
       if d is None:status='UNKNOWN_INCOMPLETE';break
       close=d.close.iloc[-1]
       if (position=='ABOVE' and close<bound) or (position=='BELOW' and close>bound):status='RETURN';when=end.isoformat();price=close;break
      assert status==y[f'return_{nday}'],(pair,name,t,nday,status,y[f'return_{nday}'])
      if when:assert y[f'return_time_{nday}']==when and np.isclose(y[f'return_close_{nday}'],price)
      futurechecks+=1
    else:assert y.return_7==y.return_28=='NOT_APPLICABLE'
    fixed='UNKNOWN_INPUT';follow='UNKNOWN';first=ret=None
    if big is not None:
     hi,lo=big.high.max(),big.low.min();assert np.isclose(y.fixed_upper,hi) and np.isclose(y.fixed_lower,lo);fixed='UNRESOLVED_28D'
     for i in range(28):
      end=t+pd.Timedelta(days=i+1);d=calc(f,end,1)
      if d is None:fixed='UNKNOWN_INCOMPLETE';break
      close=d.close.iloc[-1]
      if close>hi or close<lo:fixed='UPPER_BREAK' if close>hi else 'LOWER_BREAK';first=end;break
     if first:
      follow='NO_RETURN'
      for i in range(7):
       end=first+pd.Timedelta(days=i+1);d=calc(f,end,1)
       if d is None:follow='UNKNOWN_INCOMPLETE';break
       close=d.close.iloc[-1]
       if (fixed=='UPPER_BREAK' and close<hi) or (fixed=='LOWER_BREAK' and close>lo):follow='RETURN';ret=end;break
     elif fixed=='UNRESOLVED_28D':follow='NO_BREAK'
    assert (fixed,follow)==(y.fixed_status,y.fixed_follow),(pair,name,t,fixed,follow,y.fixed_status,y.fixed_follow)
    if first:assert first.isoformat()==y.fixed_event_time
    if ret:assert ret.isoformat()==y.fixed_return_time
    fixedchecks+=1;n+=1
  for row in Q[Q.pair==pair].itertuples():
   x=local[('bitstamp',row.as_of_utc)];y=local[(other,row.as_of_utc)];p,q=x['position'],y['position'];expect='UNKNOWN' if 'UNKNOWN' in (p,q) else 'JOINT_'+p if p==q else 'DISAGREE';assert expect==row.new_position_joint
   s=x['active'];old='UNKNOWN'
   if s in ('ACTIVE_UP','ACTIVE_DOWN') and s==y['active'] and 'UNKNOWN' not in (x['long_relation'],y['long_relation']):
    old='JOINT_POSSIBLE_UP' if s=='ACTIVE_UP' and x['long_relation'] in ('DOWN','INSIDE') and y['long_relation'] in ('DOWN','INSIDE') else 'JOINT_POSSIBLE_DOWN' if s=='ACTIVE_DOWN' and x['long_relation']==y['long_relation']=='UP' else 'NO_JOINT_CANDIDATE'
   assert row.old_joint==old
  allrows[pair]=len(Q[Q.pair==pair])
 OUT.mkdir();files=[Path(__file__),ROOT/'asof.csv',ROOT/'pairs.csv',ROOT/'future.csv',ROOT/'summary.json',*paths.values()];(OUT/'summary.json').write_text(json.dumps({'status':'PASS','source_points':n,'fixed_events':fixedchecks,'return_window_checks':futurechecks,'pairs':allrows,'scope':'independent raw 4h computations, shared relation helper; not independent truth or price certification','input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},indent=2)+'\n');print('PASS',n,fixedchecks,futurechecks,allrows)
if __name__=='__main__':main()
