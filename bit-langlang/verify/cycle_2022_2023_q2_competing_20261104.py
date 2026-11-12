"""Observed phase alternatives; descriptive historical research, no signals or orders."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read,event
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.market_2023_return_28d_20261102 import returned
SPEC=Path('docs/周期研究-2022与2023二季度竞争解释定义-20261104.md')
JOBS=[('2022q2',Path('data/market/btc-2022nine-usd-cross-20261104-01'),('bitstamp','bitfinex'),'2022-04-01','2022-07-01','USD'),('2023q2',Path('data/market/btc-2023ma-spot-cross-20261102-01'),('binance','kucoin'),'2023-04-01','2023-07-01','USDT')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for label,data,names,start,end,quote in JOBS:
  out=Path('data/verify/cycle-'+label+'-competing-20261104-01');assert not out.exists();A=pd.Timestamp(start,tz='UTC');B=pd.Timestamp(end,tz='UTC');lo=A-pd.Timedelta(days=57);hi=B+pd.Timedelta(days=35);exp=pd.date_range(lo,hi,freq='4h',inclusive='left');manifest=json.loads((data/'manifest.json').read_text());sources={}
  for name in names:
   path=data/(name+'-4h.csv.gz');m=manifest['sources'][name];assert sha(path)==m.get('dataset_sha256',m.get('original_csv_sha256'));d,h=read(path);w=h.loc[(h.index>=lo)&(h.index<hi)];assert w.index.equals(exp) and w.good.all()
   if quote=='USD':
    assert (w.volume>0).all()
    if name=='bitfinex':assert (w.min_hour_volume>0).all()
   sources[name]=(d,h)
  a,b=(sources[n][1].loc[exp] for n in names);assert not any(((a[k]/b[k]>1.1)|(a[k]/b[k]<.9)).any() for k in ('high','low'))
  daily=[];segments=[]
  for name,(d,h) in sources.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    r=asof(d,h,t);alt='DOWN_LONG_UP_SHORT_REFLECTION_OR_TRANSITION' if (r['long'],r['small'])==('DOWN','UP') else 'UP_LONG_DOWN_SHORT_PULLBACK_OR_DECLINE' if (r['long'],r['small'])==('UP','DOWN') else 'OTHER_OR_UNCLEAR';daily.append({'source':name,'as_of_utc':t.isoformat(),**r,'alternative':alt,'phase':'UNKNOWN','sentiment':'UNKNOWN'})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    stop=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);f=subsequent(d,t,stop,r);e=event(d,t,r['prior28_high'],r['prior28_low']);bound=r['prior28_high'] if e['status']=='UPPER_BREAK' else r['prior28_low'];follow=returned(d,pd.Timestamp(e['event_time_utc']),e['status'],bound,7) if e['status'] in ('UPPER_BREAK','LOWER_BREAK') else ('NO_BREAK' if e['status']=='UNRESOLVED_28D' else 'UNKNOWN',None,None)
    dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r
    segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':stop.isoformat(),**r,**f,'phase':'UNKNOWN','event28':e['status'],'event28_time':e.get('event_time_utc'),'return7':follow[0],'return7_time':follow[1]})
  daily=pd.DataFrame(daily);segments=pd.DataFrame(segments);assert len(daily)==(B-A).days*2 and segments.groupby('source').days.sum().eq((B-A).days).all();out.mkdir(parents=True);daily.to_csv(out/'daily.csv',index=False);segments.to_csv(out/'segments.csv',index=False)
  paths=[SPEC,Path(__file__),Path('verify/cycle_2025q3_continuous_20261104.py'),data/'manifest.json']+[data/(n+'-4h.csv.gz') for n in names];summary={'period':[start,end],'quote':quote,'days':(B-A).days,'segments_per_source':len(segments)//2,'required_4h_per_source':len(exp),'volume':'POSITIVE' if quote=='USD' else 'UNKNOWN_NOT_IN_STANDARD_FILE','sources':list(names),'sha256':{str(p):sha(p) for p in paths},'limitations':['Retrospective previously studied interval; not independent ground truth.','Phase and sentiment UNKNOWN.','Seven day return after a 28-day event is a price proxy, not a false-break label.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(label,len(daily),len(segments),len(exp))
if __name__=='__main__':main()
