"""Post-quality-alert additional venue, all dates retained and no cross-fill."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd,requests
from verify.market_2018_transition_20261102 import read
from verify.cycle_2025q3_continuous_20261104 import asof,subsequent
from verify.cycle_2021q1_2024q4_evidence_20261104 import future21
from verify.cycle_2023q3_2025q2_priorrange_20261104 import prior_evidence
SPEC=Path('docs/周期研究-2017二季度-Bitfinex补充定义-20261104.md');ORIG=Path('data/verify/cycle-2017q2-usd-20261104-03');OUT=Path('data/verify/cycle-2017q2-bitfinex-20261104-02');A=pd.Timestamp('2017-04-01',tz='UTC');B=pd.Timestamp('2017-07-01',tz='UTC');LO=A-pd.Timedelta(days=57);HI=B+pd.Timedelta(days=28);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir(parents=True);par={'start':int(LO.timestamp()*1000),'end':int(HI.timestamp()*1000)-1,'limit':10000,'sort':1};url=requests.Request('GET','https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=par).prepare().url;raw=(OUT.parent/'cycle-2017q2-bitfinex-20261104-01'/'bitfinex-1h.json').read_bytes();(OUT/'bitfinex-1h.json').write_bytes(raw);z=json.loads(raw);assert isinstance(z,list) and len(z)<10000
 f=pd.DataFrame(z,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).sort_values('ts');assert not f.ts.duplicated().any() and f.ts.between(par['start'],par['end']).all() and (f.ts%3600000==0).all();v=f[['open','high','low','close']];f['valid']=np.isfinite(v).all(axis=1)&(v>0).all(axis=1)&(f.low<=v.min(axis=1))&(f.high>=v.max(axis=1))&np.isfinite(f.volume)&f.volume.gt(0);f.to_csv(OUT/'bitfinex-1h.csv',index=False);f.index=pd.to_datetime(f.ts,unit='ms',utc=True);h=f.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),n=('ts','size'),valid=('valid','sum'));h=h[(h.n==4)&(h.valid==4)].copy();h['ts']=h.index.asi8//1000000;h[['ts','open','high','low','close','volume']].to_csv(OUT/'bitfinex-4h.csv',index=False)
 expected=pd.date_range(LO,HI,freq='4h',inclusive='left');src={};quality={}
 for name,path in [('bitstamp',ORIG/'bitstamp-4h.csv'),('bitfinex',OUT/'bitfinex-4h.csv')]:
  d,h=read(path);h=h.reindex(expected);h['good']=h.good.fillna(False)&h.volume.gt(0);quality[name]={'expected':len(expected),'missing_or_invalid':[t.isoformat() for t in h.index[~h.good]]};d=h.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('good','size'),ok=('good','sum'));d['good']=d.n.eq(6)&d.ok.eq(6);src[name]=(d,h)
 a,b=(src[n][1] for n in ('bitstamp','bitfinex'));flags=pd.Series(False,index=expected)
 for c in ('high','low'):flags|=(a[c]/b[c]>1.1)|(a[c]/b[c]<.9)
 bad=expected[flags].floor('D').unique()
 for d,h in src.values():d.loc[d.index.isin(bad),'good']=False;h.loc[h.index.floor('D').isin(bad),'good']=False
 quality['cross_flags']=[t.isoformat() for t in expected[flags]];daily=[];segments=[]
 for name,(d,h) in src.items():
  for t in pd.date_range(A,B,freq='D',inclusive='left'):
   daily.append({'source':name,'as_of_utc':t.isoformat(),**asof(d,h,t),**prior_evidence(d,t),'phase':'UNKNOWN','sentiment':'UNKNOWN'})
  for t in pd.date_range(A,B,freq='7D',inclusive='left'):
   end=min(t+pd.Timedelta(days=7),B);r=asof(d,h,t);p=prior_evidence(d,t);week=subsequent(d,t,end,r);week['segment_end_close']=week.pop('last_close',None);forward=future21(d,t,r) if r['range_status']=='OK' else {'first':'UNKNOWN'};dd=d.copy();hh=h.copy();dd.loc[dd.index>=t,['high','low','close']]=1.;hh.loc[hh.index>=t,['high','low','close']]=1.;assert asof(dd,hh,t)==r and prior_evidence(dd,t)==p;segments.append({'source':name,'start_utc':t.isoformat(),'end_utc_exclusive':end.isoformat(),**r,**p,**week,**forward,'phase':'UNKNOWN'})
 df=pd.DataFrame(daily);sf=pd.DataFrame(segments);assert len(df)==182 and len(sf)==26;df.to_csv(OUT/'daily.csv',index=False);sf.to_csv(OUT/'segments.csv',index=False);paths=[SPEC,Path(__file__),ORIG/'bitstamp-4h.csv',OUT/'bitfinex-1h.json',OUT/'bitfinex-4h.csv'];res={'posthoc_source':True,'quality':quality,'bitfinex_url':url,'input_sha256':{str(p):sha(p) for p in paths},'limits':['Selected after original Kraken data quality flags, not independent.','No independent human phase labels or market breadth.']};(OUT/'summary.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
if __name__=='__main__':main()
