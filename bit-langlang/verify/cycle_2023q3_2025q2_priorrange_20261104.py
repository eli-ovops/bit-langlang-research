"""As-of range evidence and forward observations; no market phase truth."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.cycle_2021q1_2024q4_evidence_20261104 import future21
SPEC=Path('docs/周期研究-2023三季度与2025二季度-既有边界证据定义-20261104.md')
JOBS=[('2023q3',Path('data/market/btc-2023ma-spot-cross-20261102-01'),('binance','kucoin'),'2023-07-01','2023-10-01','USDT'),('2025q2',Path('data/market/btc-2025q2-usd-cross-20261104-01'),('bitstamp','bitfinex'),'2025-04-01','2025-07-01','USD')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def prior_evidence(d,t):
 old=d.loc[(d.index>=t-pd.Timedelta(days=35))&(d.index<t-pd.Timedelta(days=7))];recent=d.loc[(d.index>=t-pd.Timedelta(days=7))&(d.index<t)]
 if len(old)!=28 or len(recent)!=7 or not old.good.all() or not recent.good.all():return {'prior_state':'UNKNOWN'}
 lo=float(old.low.min());hi=float(old.high.max());cl=float(recent.close.iloc[-1]);up=int((recent.close>hi).sum());dn=int((recent.close<lo).sum());position='ABOVE' if cl>hi else 'BELOW' if cl<lo else 'INSIDE' if lo<cl<hi else 'EQUAL'
 return {'old28_low':lo,'old28_high':hi,'prior_last_close':cl,'up_close_days':up,'down_close_days':dn,'current_position':position,'up_break_then_inside':bool(up>0 and position=='INSIDE'),'down_break_then_inside':bool(dn>0 and position=='INSIDE'),'prior_state':'VALID'}
def main():
 for label,data,names,start,end,quote in JOBS:
  out=Path('data/verify/cycle-'+label+'-priorrange-20261104-02');assert not out.exists();A=pd.Timestamp(start,tz='UTC');B=pd.Timestamp(end,tz='UTC');lo=A-pd.Timedelta(days=57);hi=B+pd.Timedelta(days=28);exp=pd.date_range(lo,hi,freq='4h',inclusive='left');m=json.loads((data/'manifest.json').read_text());src={}
  for name in names:
   path=data/(name+'-4h.csv.gz');meta=m['sources'][name];assert sha(path)==meta.get('dataset_sha256',meta.get('original_csv_sha256'));d,h=read(path);w=h.loc[(h.index>=lo)&(h.index<hi)];assert w.index.equals(exp) and w.good.all()
   if quote=='USD':
    assert (w.volume>0).all()
    if name=='bitfinex':assert (w.min_hour_volume>0).all()
   src[name]=(d,h)
  a,b=(src[n][1].loc[exp] for n in names);assert not any(((a[c]/b[c]>1.1)|(a[c]/b[c]<.9)).any() for c in ('high','low'))
  daily=[];segments=[]
  for name,(d,h) in src.items():
   for t in pd.date_range(A,B,freq='D',inclusive='left'):
    r=asof(d,h,t);p=prior_evidence(d,t);daily.append({'source':name,'as_of_utc':t.isoformat(),**r,**p,'phase':'UNKNOWN','sentiment':'UNKNOWN'})
   for t in pd.date_range(A,B,freq='7D',inclusive='left'):
    endt=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);p=prior_evidence(d,t);week=subsequent(d,t,endt,r);week['segment_end_close']=week.pop('last_close',None);future=future21(d,t,r);dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r and prior_evidence(dd,t)==p
    segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':endt.isoformat(),**r,**p,**week,**future,'phase':'UNKNOWN'})
  df=pd.DataFrame(daily);sf=pd.DataFrame(segments);assert len(df)==(B-A).days*2 and sf.groupby('source').days.sum().eq((B-A).days).all();out.mkdir(parents=True);df.to_csv(out/'daily.csv',index=False);sf.to_csv(out/'segments.csv',index=False)
  paths=[SPEC,Path(__file__),Path('verify/cycle_2025q3_continuous_20261104.py'),Path('verify/cycle_2021q1_2024q4_evidence_20261104.py'),data/'manifest.json']+[data/(n+'-4h.csv.gz') for n in names];summary={'period':[start,end],'quote':quote,'days':(B-A).days,'segments_per_source':len(sf)//2,'expected_4h_per_exchange':len(exp),'volume':'POSITIVE' if quote=='USD' else 'UNKNOWN_NOT_IN_STANDARD_FILES','inputs_sha256':{str(p):sha(p) for p in paths},'limits':['Prior interval is one research reference and not ground truth.','Known historical period, not independent or blind.','Sentiment, genuine phase and genuine false breaks UNKNOWN.']};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(label,len(df),len(sf),len(exp))
if __name__=='__main__':main()
