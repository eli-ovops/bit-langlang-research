"""Out-of-period price evidence after pre-frozen watches; no phase truth or trading."""
import json
from pathlib import Path
import pandas as pd,numpy as np
from .market_season_research_20261102 import sha
from .market_2020_cross_20261102 import evaluate_extended
DATA=Path('data/market/btc-2018-spot-cross-20261102-02');OUT=Path('data/verify/market-2018-transitions-20261102-01');DEF=Path('docs/春秋观察到结构确认-2018事前检验定义-20261102.md');AMEND=Path('docs/2018现货历史-缺柱处理补充-20261102.md');START=pd.Timestamp('2018-01-01',tz='UTC');END=pd.Timestamp('2019-01-01',tz='UTC')

def event(daily,t,upper,lower):
 """Daily close against frozen pre-watch bounds, first event, no time travel."""
 if not np.isfinite([upper,lower]).all() or upper<=lower:raise ValueError('invalid frozen range')
 for i in range(28):
  day=t+pd.Timedelta(days=i)
  if day not in daily.index or not bool(daily.loc[day,'good']):return {'status':'UNKNOWN_INCOMPLETE','observed_days':i,'event_time_utc':None}
  close=float(daily.loc[day,'close']);status='UPPER_BREAK' if close>upper else 'LOWER_BREAK' if close<lower else None
  if status:return {'status':status,'observed_days':i+1,'event_time_utc':(day+pd.Timedelta(days=1)).isoformat(),'event_close':close}
 return {'status':'UNRESOLVED_28D','observed_days':28,'event_time_utc':None}

def read(path):
 f=pd.read_csv(path);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);h=f.set_index('time');v=h[['open','high','low','close']];h['bad']=(~np.isfinite(v).all(axis=1))|(v<=0).any(axis=1)|(h.low>v.min(axis=1))|(h.high<v.max(axis=1));h['good']=~h.bad
 if h.index.has_duplicates or not h.index.is_monotonic_increasing or (h.index.asi8//1000000%14400000!=0).any():raise ValueError('bad 4h grid')
 d=h.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('close','size'),bad=('bad','sum'));d['good']=d.n.eq(6)&d.bad.eq(0);return d,h

def main():
 if OUT.exists():raise FileExistsError(OUT)
 files=[DEF,AMEND,Path(__file__),DATA/'manifest.json',DATA/'binance-spot-4h.csv.gz',DATA/'kucoin-spot-4h.csv.gz'];hashes={str(p):sha(p) for p in files};manifest=json.loads((DATA/'manifest.json').read_text())
 for name in ('binance','kucoin'):assert hashes[str(DATA/(name+'-spot-4h.csv.gz'))]==manifest['sources'][name]['dataset_sha256']
 times=pd.date_range(START,END-pd.Timedelta(nanoseconds=1),freq='7D');records=[];events=[]
 for name in ('binance','kucoin'):
  d,h=read(DATA/(name+'-spot-4h.csv.gz'))
  for t in times:
   x=evaluate_extended(d,h,t);r={'as_of_utc':t.isoformat(),'source':name,**x};records.append(r)
   for kind in ('spring','autumn'):
    flag=x[kind+'_watch'];rec={'as_of_utc':t.isoformat(),'source':name,'watch':kind,'watch_state':flag}
    if flag=='YES':
     prior=d.loc[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)];assert len(prior)==28 and prior.good.all();hi=float(prior.high.max());lo=float(prior.low.min());rec.update(frozen_upper=hi,frozen_lower=lo,**event(d,t,hi,lo))
    else:rec.update(status='NO_WATCH' if flag=='NO' else 'UNKNOWN_INPUT',observed_days=0,event_time_utc=None)
    events.append(rec)
 df=pd.DataFrame(records);ev=pd.DataFrame(events);a=df[df.source=='binance'].set_index('as_of_utc');b=df[df.source=='kucoin'].set_index('as_of_utc');assert a.index.equals(b.index);comp=[]
 for t in a.index:
  x,y=a.loc[t],b.loc[t];r={'as_of_utc':t}
  for field in ('big_relation','small_relation','long_relation','spring_watch','autumn_watch'):
   u,v=x[field],y[field];r[field+'_binance']=u;r[field+'_kucoin']=v;r[field+'_comparison']='INCOMPLETE' if 'UNKNOWN' in (u,v) else 'AGREE' if u==v else 'DISAGREE'
  comp.append(r)
 comp=pd.DataFrame(comp);summary={}
 for name,g in df.groupby('source'):
  row={'points':len(g),'big_valid':int(g.big_valid.sum()),'small_valid':int(g.small_valid.sum()),'long_valid':int(g.long_valid.sum()),'season':g.season.value_counts().to_dict()}
  for w in ('spring','autumn'):
   row[w+'_watch']=g[w+'_watch'].value_counts().to_dict();selected=ev[(ev.source==name)&(ev.watch==w)&(ev.watch_state=='YES')];row[w+'_events']=selected.status.value_counts().to_dict()
  summary[name]=row
 for field in ('big_relation','small_relation','long_relation','spring_watch','autumn_watch'):summary['compare_'+field]=comp[field+'_comparison'].value_counts().to_dict()
 if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('inputs modified')
 OUT.mkdir();df.to_csv(OUT/'layers.csv',index=False);ev.to_csv(OUT/'events.csv',index=False);comp.to_csv(OUT/'cross-venue.csv',index=False);(OUT/'summary.json').write_text(json.dumps({'status':'HISTORICAL_TRANSITION_EVIDENCE_NOT_SEASON_TRUTH','results':summary,'input_sha256':hashes,'limits':['Previously known historical events, not independent human ground truth.','28-day boundary closing events are arbitrary research criteria, not real trader rules.','Different exchanges can disagree; gaps remain UNKNOWN.']},ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
