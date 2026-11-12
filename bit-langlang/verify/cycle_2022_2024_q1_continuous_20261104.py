"""Quarterly cycle review using frozen 2025 cycle evidence helpers."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
SPEC=Path('docs/周期研究回归-2022与2024一季度连续复盘定义-20261104.md')
JOBS=[('2022q1',Path('data/market/btc-2022nine-usd-cross-20261104-01'),'2022-01-01','2022-04-01'),('2024q1',Path('data/market/btc-2024q1-usd-cross-20261104-01'),'2024-01-01','2024-04-01')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for label,data,start,end in JOBS:
  out=Path('data/verify/cycle-'+label+'-continuous-20261104-01');assert not out.exists()
  A=pd.Timestamp(start,tz='UTC');B=pd.Timestamp(end,tz='UTC');lo=A-pd.Timedelta(days=57);hi=B+pd.Timedelta(days=28);expected=pd.date_range(lo,hi,freq='4h',inclusive='left');manifest=json.loads((data/'manifest.json').read_text());src={}
  for name in ('bitstamp','bitfinex'):
   p=data/(name+'-4h.csv.gz');assert sha(p)==manifest['sources'][name]['dataset_sha256'];d,h=read(p);window=h.loc[(h.index>=lo)&(h.index<hi)];assert window.index.equals(expected) and window.good.all() and (window.volume>0).all()
   if name=='bitfinex':assert (window.min_hour_volume>0).all()
   src[name]=(d,h)
  a,b=(src[x][1].loc[expected] for x in ('bitstamp','bitfinex'));assert not any(((a[c]/b[c]>1.1)|(a[c]/b[c]<.9)).any() for c in ('high','low'))
  daily=[];segments=[]
  for name,(d,h) in src.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    daily.append({'source':name,'as_of_utc':t.isoformat(),**asof(d,h,t),'phase':'UNKNOWN','emotion':'UNKNOWN'})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    z=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);f=subsequent(d,t,z,r);dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r
    segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':z.isoformat(),**r,**f,'phase':'UNKNOWN'})
  day=pd.DataFrame(daily);seg=pd.DataFrame(segments);days=(B-A).days;assert len(day)==days*2 and seg.groupby('source').days.sum().eq(days).all()
  out.mkdir(parents=True);day.to_csv(out/'daily.csv',index=False);seg.to_csv(out/'segments.csv',index=False)
  inputs=[SPEC,Path(__file__),Path('verify/cycle_2025q3_continuous_20261104.py'),data/'manifest.json',data/'bitstamp-4h.csv.gz',data/'bitfinex-4h.csv.gz'];summary={'period':[A.isoformat(),B.isoformat()],'required_candle_window':[lo.isoformat(),hi.isoformat()],'expected_4h_per_source':len(expected),'days':days,'segments_per_source':len(seg)//2,'inputs_sha256':{str(p):sha(p) for p in inputs},'limits':['Retrospective selected after prior studies, not independent or blind.','Phase, sentiment, market breadth and true false-break labels unknown.','Weekly events and return are descriptive, not trade outcomes.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(label,days,len(seg)//2)
if __name__=='__main__':main()
