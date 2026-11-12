"""Predeclared 2020 Q4 BTC/USD check; historical research only."""
from pathlib import Path
from decimal import Decimal
import hashlib,json
import pandas as pd,requests
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_2019on_20261103 import support,first_break
from verify.market_support_fallback_2014sp_20261103 import fallback
from verify.market_support_directional_20261104 import classify
from verify.market_2023_return_28d_20261102 import returned
P=Path('data/verify/market-directional-2020q4-20261104-01');RAW=Path('data/market/kraken-xbtusd-native4h-20261104-01/XBTUSD_240.csv');SPEC=Path('docs/方向化摆低-2020四季度事前筛查-20261104.md');A=pd.Timestamp('2020-08-01',tz='UTC');B=pd.Timestamp('2021-02-01',tz='UTC');T0=pd.Timestamp('2020-10-01',tz='UTC');T1=pd.Timestamp('2021-01-01',tz='UTC')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if P.exists():raise FileExistsError(P)
 assert sha(SPEC)=='a1505acf03a123606f44713c28952abb679ef717b558fcc04901d7de83084bed'
 assert sha(RAW)==json.loads(RAW.with_name('manifest.json').read_text())['raw_sha256']
 P.mkdir(parents=True)
 par={'start':int(A.timestamp()*1000),'end':int(B.timestamp()*1000)-1,'limit':10000,'sort':1}
 r=requests.get('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',params=par,timeout=60);r.raise_for_status();(P/'bitfinex-raw.json').write_bytes(r.content);url=r.url
 z=r.json();assert isinstance(z,list) and len(z)<10000
 f=pd.DataFrame(z,columns=['ts','open','close','high','low','volume']).apply(pd.to_numeric).sort_values('ts');assert not f.ts.duplicated().any() and f.ts.between(par['start'],par['end']).all() and (f.ts%3600000==0).all()
 f.to_csv(P/'bitfinex-1h.csv',index=False);f.index=pd.to_datetime(f.ts,unit='ms',utc=True)
 g=f.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),min_volume=('volume','min'),n=('ts','size'));g=g[g.n==4].copy();g['ts']=g.index.asi8//1000000;g[['ts','open','high','low','close','volume','min_volume']].to_csv(P/'bitfinex-4h.csv',index=False)
 k=pd.read_csv(RAW,header=None,names=['sec','open','high','low','close','volume','trades']);assert k.sec.is_monotonic_increasing and not k.sec.duplicated().any();k=k[(k.sec>=A.timestamp())&(k.sec<B.timestamp())].copy();k['ts']=k.sec*1000;k[['ts','open','high','low','close','volume','trades']].to_csv(P/'kraken-4h.csv',index=False)
 sources={};quality={};exp=pd.date_range(A,B,freq='4h',inclusive='left')
 for name in ('kraken','bitfinex'):
  d,h=read(P/(name+'-4h.csv'));h=h.reindex(exp);h['good']=h.good.fillna(False)&h.volume.gt(0)
  if name=='bitfinex':h['good'] &= h.min_volume.gt(0)
  d=h.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('good','size'),ok=('good','sum'));d['good']=d.n.eq(6)&d.ok.eq(6)
  quality[name]={'expected_4h':len(exp),'missing_or_bad_4h':int((~h.good).sum()),'bad_times':[t.isoformat() for t in h.index[~h.good]]};sources[name]=(d,h)
 ka,fb=sources['kraken'][1],sources['bitfinex'][1];flags=pd.Series(False,index=exp)
 for col in ('high','low'):
  q=ka[col]/fb[col];flags|=(q>1.1)|(q<.9)
 bad_days=exp[flags].floor('D').unique()
 for d,h in sources.values():d.loc[d.index.isin(bad_days),'good']=False;h.loc[h.index.floor('D').isin(bad_days),'good']=False
 quality['cross_flags_utc']=[t.isoformat() for t in exp[flags]]
 rows=[]
 for t in pd.date_range(T0,T1,freq='D',inclusive='left'):
  for name,(d,h) in sources.items():
   x=evaluate_extended(d,h,t);p=pivots(d,t);old=support(d,t,p);new,method=fallback(d,t,p);state=new['support_state'];level=new.get('level');close=new.get('close');ds,flag=classify(state,level,close);event=('UNKNOWN',None,None)
   if state not in ('UNKNOWN','WAIT_CONFIRM'):
    if new.get('position')=='BELOW':event=returned(d,t,'LOWER_BREAK',level,7)
    elif new.get('history')=='PRIOR_UNBROKEN':event=first_break(d,t,level)
   distance=float((Decimal(str(close))-Decimal(str(level)))/Decimal(str(close))*100) if level is not None and close is not None and close>0 else None
   rows.append({'as_of_utc':t.isoformat(),'source':name,'long':x['long_relation'],'big':x['big_relation'],'small':x['small_relation'],'old_state':old['support_state'],'state':state,'fallback':method,'level':level,'known':new.get('known'),'close':close,'distance_pct':distance,'directional':ds,'distance_flag':flag,'event7':event[0],'event_time':event[1],'phase':'UNKNOWN'})
 allrows=pd.DataFrame(rows);allrows.to_csv(P/'source-all.csv',index=False);joint=[]
 for t,g in allrows.groupby('as_of_utc',sort=True):
  assert len(g)==2; vals=[(v,w) for _,row in g.iterrows() for v,w in [(row['long'],'UP'),(row['big'],'UP'),(row['small'],'DOWN')]]; focus='NO' if any(v not in (w,'UNKNOWN') for v,w in vals) else 'UNKNOWN' if any(v=='UNKNOWN' for v,w in vals) else 'YES'; far=bool((g.distance_flag=='FAR_BELOW_PRICE').any());joint.append({'as_of_utc':t,'focus_both':focus,'far_any':far,'far_both':bool((g.distance_flag=='FAR_BELOW_PRICE').all()),'focus_far':focus=='YES' and far,'unknown_any':bool(g.directional.str.startswith('UNKNOWN').any())})
 j=pd.DataFrame(joint);j.to_csv(P/'joint-all.csv',index=False)
 result={'quality':quality,'days':len(j),'focus_counts':j.focus_both.value_counts().to_dict(),'focus_far_days':j.loc[j.focus_far,'as_of_utc'].tolist(),'far_days':int(j.far_any.sum()),'unknown_days':int(j.unknown_any.sum()),'bitfinex_url':url,'input_sha256':{str(p):sha(p) for p in (RAW,SPEC,Path(__file__),P/'bitfinex-raw.json')},'limitations':['2020 Q4 was prior warmup, exposure cannot be ruled out.','No independent human phase truth.','Frozen rules are research examples, not verified Bit Langlang rules.']}
 (P/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
