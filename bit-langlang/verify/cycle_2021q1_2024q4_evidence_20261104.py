"""Timestamped range evidence only; no phase labels, trade actions or parameter tuning."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.market_2023_return_28d_20261102 import returned
SPEC=Path('docs/周期研究-2021一季度与2024四季度-连续证据定义-20261104.md')
JOBS=[('2021q1',Path('data/market/btc-2021yr-usd-cross-20261104-01'),'2021-01-01','2021-04-01'),('2024q4',Path('data/market/btc-2024q4-usd-cross-20261104-01'),'2024-10-01','2025-01-01')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def future21(d,t,r):
 h,l=r['prior28_high'],r['prior28_low']
 for i in range(21):
  day=t+pd.Timedelta(days=i)
  if day not in d.index or not d.loc[day,'good']:return {'first':'UNKNOWN'}
  c=float(d.loc[day,'close']);side='UPPER_BREAK' if c>h else 'LOWER_BREAK' if c<l else None
  if side:
   bound=h if side=='UPPER_BREAK' else l;known=day+pd.Timedelta(days=1);n=known
   if n not in d.index or not d.loc[n,'good']:consecutive='UNKNOWN'
   else:
    close=float(d.loc[n,'close']);consecutive='TWO_CONSECUTIVE' if (close>bound if side=='UPPER_BREAK' else close<bound) else 'NOT_TWO'
   ret,when,price=returned(d,known,side,bound,7)
   return {'first':side,'first_known':known.isoformat(),'first_close':c,'two_consecutive':consecutive,'two_status_known':(n+pd.Timedelta(days=1)).isoformat() if consecutive!='UNKNOWN' else None,'return7':ret,'return_known':when}
 return {'first':'NO_BREAK_21D','two_consecutive':'NOT_APPLICABLE','return7':'NOT_APPLICABLE'}
def main():
 for label,data,start,end in JOBS:
  out=Path('data/verify/cycle-'+label+'-evidence-20261104-01');assert not out.exists();A=pd.Timestamp(start,tz='UTC');B=pd.Timestamp(end,tz='UTC');lo=A-pd.Timedelta(days=57);hi=B+pd.Timedelta(days=28);expected=pd.date_range(lo,hi,freq='4h',inclusive='left');m=json.loads((data/'manifest.json').read_text());src={}
  for name in ('bitstamp','bitfinex'):
   path=data/(name+'-4h.csv.gz');assert sha(path)==m['sources'][name]['dataset_sha256'];d,h=read(path);w=h.loc[(h.index>=lo)&(h.index<hi)];assert w.index.equals(expected) and w.good.all() and (w.volume>0).all()
   if name=='bitfinex':assert (w.min_hour_volume>0).all()
   src[name]=(d,h)
  a,b=(src[n][1].loc[expected] for n in ('bitstamp','bitfinex'));assert not any(((a[c]/b[c]>1.1)|(a[c]/b[c]<.9)).any() for c in ('high','low'))
  daily=[];segments=[]
  for name,(d,h) in src.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    r=asof(d,h,t);daily.append({'source':name,'as_of_utc':t.isoformat(),**r,'phase':'UNKNOWN','sentiment':'UNKNOWN'})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    endt=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);week=subsequent(d,t,endt,r);future=future21(d,t,r);dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r;segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':endt.isoformat(),**r,**week,**future,'phase':'UNKNOWN'})
  df=pd.DataFrame(daily);sf=pd.DataFrame(segments);assert len(df)==(B-A).days*2 and sf.groupby('source').days.sum().eq((B-A).days).all();out.mkdir(parents=True);df.to_csv(out/'daily.csv',index=False);sf.to_csv(out/'segments.csv',index=False)
  paths=[SPEC,Path(__file__),Path('verify/cycle_2025q3_continuous_20261104.py'),Path('verify/market_2023_return_28d_20261102.py'),data/'manifest.json']+[data/(n+'-4h.csv.gz') for n in ('bitstamp','bitfinex')];summary={'period':[start,end],'days':(B-A).days,'segments_per_exchange':len(sf)//2,'expected_4h_per_exchange':len(expected),'inputs_sha256':{str(p):sha(p) for p in paths},'limits':['Known retrospective intervals and overlapping events, not independent validation.','Phase, sentiment and genuine breakout truth UNKNOWN.','Consecutive closes are a research fact, not the trader rule or confirmed phase.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(label,'days',len(df),'segments',len(sf),'4h',len(expected))
if __name__=='__main__':main()
