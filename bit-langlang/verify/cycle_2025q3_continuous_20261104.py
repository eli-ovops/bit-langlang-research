"""Continuous BTC cycle evidence; research descriptors, not phase truth or orders."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended

DATA=Path('data/market/btc-2025q3-usd-cross-20261104-01');OUT=Path('data/verify/cycle-2025q3-continuous-20261104-01');SPEC=Path('docs/周期研究回归-2025三季度逐段复盘定义-20261104.md')
A=pd.Timestamp('2025-07-01',tz='UTC');B=pd.Timestamp('2025-10-01',tz='UTC')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def asof(d,h,t):
 x=evaluate_extended(d,h,t);prior=d.loc[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)]
 if len(prior)!=28 or not prior.good.all():return {'long':x['long_relation'],'big':x['big_relation'],'small':x['small_relation'],'range_status':'UNKNOWN'}
 low,high=float(prior.low.min()),float(prior.high.max());close=float(prior.close.iloc[-1]);pct=(close-low)/(high-low) if high>low else None
 return {'long':x['long_relation'],'big':x['big_relation'],'small':x['small_relation'],'range_status':'OK','prev_close':close,'prior28_low':low,'prior28_high':high,'position_fraction':pct}

def subsequent(d,t,end,r):
 days=d.loc[(d.index>=t)&(d.index<end)]
 if len(days)!=(end-t).days or not days.good.all() or r['range_status']!='OK':return {'status':'UNKNOWN'}
 upper,lower=r['prior28_high'],r['prior28_low'];side=None;first=None;back=None
 for time,row in days.iterrows():
  c=float(row.close)
  if side is None and (c>upper or c<lower):side='ABOVE' if c>upper else 'BELOW';first=(time+pd.Timedelta(days=1)).isoformat();continue
  if side and back is None and ((side=='ABOVE' and c<upper) or (side=='BELOW' and c>lower)):back=(time+pd.Timedelta(days=1)).isoformat()
 return {'status':'COMPLETE','days':len(days),'period_low':float(days.low.min()),'period_high':float(days.high.max()),'last_close':float(days.close.iloc[-1]),'last_change_pct':100*(float(days.close.iloc[-1])/r['prev_close']-1),'first_close_break':side or 'NO_BREAK','break_known_utc':first,'close_return_known_utc':back}

def main():
 if OUT.exists():raise FileExistsError(OUT)
 manifest=json.loads((DATA/'manifest.json').read_text());sources={};expected=pd.date_range('2025-05-01','2025-11-01',freq='4h',inclusive='left',tz='UTC')
 for name in ('bitstamp','bitfinex'):
  path=DATA/(name+'-4h.csv.gz');assert sha(path)==manifest['sources'][name]['dataset_sha256'];d,h=read(path);assert h.index.equals(expected) and h.good.all() and (h.volume>0).all()
  if name=='bitfinex':assert (h.min_hour_volume>0).all()
  sources[name]=(d,h)
 ka=sources['bitstamp'][1];kb=sources['bitfinex'][1];assert not any((((ka[c]/kb[c])>1.1)|((ka[c]/kb[c])<.9)).any() for c in ('high','low'))
 records=[];segments=[]
 for name,(d,h) in sources.items():
  for t in pd.date_range(A,B,freq='D',inclusive='left'):
   r=asof(d,h,t);records.append({'as_of_utc':t.isoformat(),'source':name,**r,'phase':'UNKNOWN','emotion':'UNKNOWN'})
  for t in pd.date_range(A,B,freq='7D',inclusive='left'):
   end=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);future=subsequent(d,t,end,r)
   altered_d=d.copy();altered_h=h.copy();altered_d.loc[altered_d.index>=t,['high','low','close']]=1.;altered_h.loc[altered_h.index>=t,['high','low','close']]=1.;assert asof(altered_d,altered_h,t)==r
   segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':end.isoformat(),**r,**future,'phase':'UNKNOWN'})
 rows=pd.DataFrame(records);s=pd.DataFrame(segments);assert len(rows)==184 and len(s)==28 and s.groupby('source').days.sum().eq(92).all()
 OUT.mkdir(parents=True);rows.to_csv(OUT/'daily.csv',index=False);s.to_csv(OUT/'segments.csv',index=False)
 files=[SPEC,Path(__file__),DATA/'manifest.json',DATA/'bitstamp-4h.csv.gz',DATA/'bitfinex-4h.csv.gz'];result={'period':'2025-07-01..2025-10-01 UTC','days':92,'segments':14,'counts_by_source':{name:{'long':g['long'].value_counts().to_dict(),'big':g.big.value_counts().to_dict(),'small':g.small.value_counts().to_dict()} for name,g in rows.groupby('source')},'inputs_sha256':{str(p):sha(p) for p in files},'limits':['Retrospective, previously observed data, not independent sample.','Window descriptors not proven phase labels or Bit Langlang rules.','One BTC price pair cannot identify sentiment or market breadth.','7-day returns and boundary events are not phase truth or trade returns.']};(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(s.to_string(index=False))
if __name__=='__main__':main()
