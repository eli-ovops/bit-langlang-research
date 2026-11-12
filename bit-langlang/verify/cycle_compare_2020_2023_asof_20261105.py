"""Post-hoc comparison of two known price cases; as-of facts, no phase inference."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_multilevel_20261102 import layer
from verify.market_2016_pivot_20261102 import pivots
from verify.cycle_2025q3_continuous_20261104 import asof
SPEC=Path('docs/周期研究-2020与2023相似表象-事后结构对照定义-20261105.md');OUT=Path('data/verify/cycle-2020-2023-asof-diagnosis-20261105-01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CASES=[('2020q3','2020-08-26'),('2023q1','2023-02-12')]
def facts(d,h,t):
 history=d.loc[(d.index>=t-pd.Timedelta(days=84))&(d.index<t)];expected=pd.date_range(t-pd.Timedelta(days=84),t,freq='D',inclusive='left');assert history.index.equals(expected) and history.good.all()
 res=asof(d,h,t);x=layer(history,84);res.update(long84=x['relation'],long84_old_high=x.get('old_high'),long84_old_low=x.get('old_low'),long84_new_high=x.get('new_high'),long84_new_low=x.get('new_low'))
 hi=float(history.high.max());lo=float(history.low.min());close=float(history.close.iloc[-1]);res.update(history84_low=lo,history84_high=hi,history84_position=(close-lo)/(hi-lo))
 prior=history.iloc[-28:];th=prior.high.idxmax();tl=prior.low.idxmin();res.update(high28_day=th.isoformat(),low28_day=tl.isoformat(),high28_days_before=int((t-th).days),low28_days_before=int((t-tl).days),low_vs_high_order='LOW_THEN_HIGH' if tl<th else 'HIGH_THEN_LOW' if th<tl else 'SAME_DAY')
 p=pivots(d,t);res.update(p)
 if p['swing']!='UNKNOWN':
  for label,direction in [('h_new','high'),('l_new','low')]:
   k=pd.Timestamp(p[label+'_known']);assert k<=t;z=d[(d.index>=k)&(d.index<t)];expected2=pd.date_range(k,t,freq='D',inclusive='left');assert z.index.equals(expected2) and z.good.all();level=p[label+'_price'];past=z.close.gt(level) if direction=='high' else z.close.lt(level);res[label+'_close_position']='ABOVE' if close>level else 'BELOW' if close<level else 'EQUAL';res[label+'_already_crossed']=bool(past.any());res[label+'_first_cross_known']=(past.index[past][0]+pd.Timedelta(days=1)).isoformat() if past.any() else None
 return res
def main():
 assert not OUT.exists();rows=[];future=[];paths=[SPEC,Path(__file__),Path('verify/market_2016_pivot_20261102.py'),Path('verify/market_multilevel_20261102.py')]
 for label,date in CASES:
  p=Path('data/verify/cycle-'+label+'-phase-20261104-01');manifest=json.loads((p/'summary.json').read_text());assert not manifest['data_quality_flags_utc'];paths.extend([p/'summary.json',p/'segments.csv']);t=pd.Timestamp(date,tz='UTC');sources={}
  for name in ('bitstamp','kraken'):
   file=p/(name+'-4h.csv');assert sha(file)==manifest['input_sha256'][str(file)];paths.append(file);d,h=read(file);w=h[(h.index>=t-pd.Timedelta(days=84))&(h.index<t)];assert w.index.equals(pd.date_range(t-pd.Timedelta(days=84),t,freq='4h',inclusive='left')) and w.good.all() and (w.volume>0).all();sources[name]=(d,h)
  a,b=(sources[n][1].loc[(sources[n][1].index>=t-pd.Timedelta(days=84))&(sources[n][1].index<t)] for n in ('bitstamp','kraken'));assert a.index.equals(b.index) and not any(((a[c]/b[c]>1.1)|(a[c]/b[c]<.9)).any() for c in ('high','low'))
  for name,(d,h) in sources.items():
   r=facts(d,h,t);dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert facts(dd,hh,t)==r
   rows.append({'case':date,'source':name,**r,'phase':'UNKNOWN','sentiment':'UNKNOWN'});s=pd.read_csv(p/'segments.csv');z=s[(s.source==name)&(s.start_utc==t.isoformat())].iloc[0];future.append({'case':date,'source':name,'first':z['first'],'first_known':z.get('first_known'),'return7':z.get('return7'),'return_known':z.get('return_known')})
 OUT.mkdir(parents=True);df=pd.DataFrame(rows);df.to_csv(OUT/'asof.csv',index=False);pd.DataFrame(future).to_csv(OUT/'posthoc-events.csv',index=False);res={'status':'POSTHOC_COMPARISON_NOT_INDEPENDENT','cases':CASES,'input_sha256':{str(p):sha(p) for p in paths},'limits':['Only two selected known cases; no causal inference or performance estimate.','Mechanical pivots and 84 days are research proxies, not verified trader rules.','Phase, true false breaks, sentiment and broad-market participation unknown.']};(OUT/'summary.json').write_text(json.dumps(res,indent=2)+'\n');print(df.to_string(index=False))
if __name__=='__main__':main()
