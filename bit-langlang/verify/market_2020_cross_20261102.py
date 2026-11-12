"""Previously unreviewed interval, fixed candidate hypotheses and cross-venue facts."""
import json
from pathlib import Path
import numpy as np,pandas as pd
from .market_season_research_20261102 import aggregates,sha
from .market_multilevel_20261102 import evaluate,layer
from .market_multilevel_guard_20261102 import guard
DATA=Path('data/market/btc-2020-cross-20261102-02');OUT=Path('data/verify/market-2020-cross-20261102-01');DEF=Path('docs/市场周期-春秋双尺度2020外部检验冻结定义-20261102.md');AMEND=Path('docs/市场周期-2020预热缺口补充定义-20261102.md');START=pd.Timestamp('2020-01-01',tz='UTC');END=pd.Timestamp('2020-11-01',tz='UTC')

def evaluate_extended(d,h,t):
 x=evaluate(d,h,t);longdata=d.loc[(d.index>=t-pd.Timedelta(days=56))&(d.index<t)];long=layer(longdata,56);x['long_valid']=long['valid'];x['long_relation']=long['relation']
 for k in ('old_high','old_low','new_high','new_low'):
  if k in long:x['long_'+k]=long[k]
 for k in ('spring_watch','autumn_watch'):x[k]='UNKNOWN'
 if x['big_valid'] and x['small_valid'] and long['valid']:
  guarded,why=guard(x['season'],x['big_relation'],x['small_relation']);x['v1_season']=x['season'];x['season']=guarded;x['guard_reason']=why or x['reason']
  recent=d.loc[(d.index>=t-pd.Timedelta(days=14))&(d.index<t)];assert len(recent)==14 and recent.good.all();mid=(recent.high.max()+recent.low.min())/2;x['recent14_mid']=float(mid)
  x['spring_watch']='YES' if guarded=='SPRING' and long['relation'] in ('DOWN','INSIDE') else 'NO'
  x['autumn_watch']='YES' if x['big_relation']=='UP' and x['small_relation']=='DOWN' and long['relation']=='UP' and x['prior_close']<mid else 'NO'
 else:
  guarded,why=guard(x['season'],x['big_relation'],x['small_relation']);x['v1_season']=x['season'];x['season']=guarded;x['guard_reason']=why or x['reason']
 return x

def sources():
 p=DATA/'BTCUSDT-binance-5m.csv.gz';f=pd.read_csv(p);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time');bd,bh=aggregates(f)
 p=DATA/'BTC-USDT-kucoin-spot-4h.csv.gz';k=pd.read_csv(p);k['time']=pd.to_datetime(k.ts,unit='ms',utc=True);k=k.set_index('time');v=k[['open','high','low','close']];k['bad']=(~np.isfinite(v).all(axis=1))|(v<=0).any(axis=1)|(k.low>v.min(axis=1))|(k.high<v.max(axis=1));k['good']=~k.bad
 kd=k.resample('D').agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('close','size'),bad=('bad','sum'));kd['good']=kd.n.eq(6)&kd.bad.eq(0)
 return {'binance_perp':(bd,bh),'kucoin_spot':(kd,k)}

def main():
 if OUT.exists():raise FileExistsError('refuse overwrite')
 files=[DEF,AMEND,Path(__file__),DATA/'manifest.json',DATA/'BTCUSDT-binance-5m.csv.gz',DATA/'BTC-USDT-kucoin-spot-4h.csv.gz'];hashes={str(p):sha(p) for p in files};manifest=json.loads((DATA/'manifest.json').read_text());assert hashes[str(DATA/'BTCUSDT-binance-5m.csv.gz')]==manifest['binance']['dataset_sha256'] and hashes[str(DATA/'BTC-USDT-kucoin-spot-4h.csv.gz')]==manifest['kucoin']['dataset_sha256']
 src=sources();times=pd.date_range(START,END-pd.Timedelta(nanoseconds=1),freq='7D');records=[];future=[]
 for t in times:
  for name,(d,h) in src.items():
   record={'as_of_utc':t.isoformat(),'source':name,**evaluate_extended(d,h,t)};records.append(record)
   for days in (7,28):
    z=d.loc[(d.index>=t)&(d.index<t+pd.Timedelta(days=days))];entry=record.get('prior_close');row={'as_of_utc':t.isoformat(),'source':name,'future_days':days,'season':record['season'],'spring_watch':record['spring_watch'],'autumn_watch':record['autumn_watch']}
    if len(z)==days and z.good.all() and entry is not None:
     row.update(status='AFTER_THE_FACT_NOT_TRUTH',close_pct=float((z.close.iloc[-1]/entry-1)*100),high_pct=float((z.high.max()/entry-1)*100),low_pct=float((z.low.min()/entry-1)*100))
    else:row['status']='UNKNOWN_INSUFFICIENT_COVERAGE'
    future.append(row)
 df=pd.DataFrame(records);after=pd.DataFrame(future);bn=df[df.source=='binance_perp'].set_index('as_of_utc');kc=df[df.source=='kucoin_spot'].set_index('as_of_utc');assert bn.index.equals(kc.index)
 compare=[]
 for t in bn.index:
  a,b=bn.loc[t],kc.loc[t];row={'as_of_utc':t}
  for field,unk in [('big_relation','UNKNOWN'),('small_relation','UNKNOWN'),('long_relation','UNKNOWN'),('spring_watch','UNKNOWN'),('autumn_watch','UNKNOWN'),('season','UNKNOWN')]:
   aa,bb=a[field],b[field];row[field+'_binance']=aa;row[field+'_kucoin']=bb;row[field+'_comparison']='INCOMPLETE' if aa==unk or bb==unk else 'AGREE' if aa==bb else 'DISAGREE'
  compare.append(row)
 cross=pd.DataFrame(compare);results={}
 for s,g in df.groupby('source'):
  results[s]={'points':len(g),'big_valid':int(g.big_valid.sum()),'small_valid':int(g.small_valid.sum()),'long_valid':int(g.long_valid.sum()),'seasons':g.season.value_counts().to_dict(),'spring_watch':g.spring_watch.value_counts().to_dict(),'autumn_watch':g.autumn_watch.value_counts().to_dict()}
 for key in ('big_relation','small_relation','long_relation','spring_watch','autumn_watch','season'):results['comparison_'+key]=cross[key+'_comparison'].value_counts().to_dict()
 if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('input changed')
 OUT.mkdir(parents=True);df.to_csv(OUT/'layers.csv',index=False);after.to_csv(OUT/'future-descriptive.csv',index=False);cross.to_csv(OUT/'cross-venue.csv',index=False)
 (OUT/'summary.json').write_text(json.dumps({'status':'UNSEEN_INTERVAL_STRUCTURAL_VALIDATION_NOT_LABEL_TRUTH','results':results,'inputs_sha256':hashes,'limitations':['2020 historical events may be known, no human blinded adjudication.','Different product and exchange; agreement not truth.','Reference season UNKNOWN, price outcomes not ground truth.','2019 Binance archives unavailable for warmup, no cross-source splice.']},indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
