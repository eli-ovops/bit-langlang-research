"""Retrospective separated BTC context/structure proxy, no orders."""
import json
from pathlib import Path
import numpy as np,pandas as pd
from .market_season_research_20261102 import SOURCE as MAIN_SOURCE,aggregates,relation,sha
DEF=Path('docs/市场阶段-大背景与小变化研究定义-20261102.md');ROOT=Path('data/verify/market-multilevel-20261102-01')
JOBS={'main':(MAIN_SOURCE,Path('data/verify/market-season-research-20261102-01/weekly.csv'),pd.Timestamp('2026-10-31',tz='UTC')),'stress2021':(Path('data/market/four-earlier-2021-20261031-01/BTCUSDT_5m.csv.gz'),Path('data/verify/market-season-2021-stress-20261102-01/weekly.csv'),pd.Timestamp('2022-01-01',tz='UTC'))}

def layer(f,n):
 if len(f)!=n or not f.good.all():return {'valid':False,'relation':'UNKNOWN'}
 a,b=f.iloc[:n//2],f.iloc[n//2:];ah,al,bh,bl=float(a.high.max()),float(a.low.min()),float(b.high.max()),float(b.low.min())
 return {'valid':True,'relation':relation(ah,al,bh,bl),'old_high':ah,'old_low':al,'new_high':bh,'new_low':bl}

def evaluate(d,h,t):
 big=d.loc[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)];small=h.loc[(h.index>=t-pd.Timedelta(days=8))&(h.index<t)];a=layer(big,28);b=layer(small,48)
 o={'big_valid':a['valid'],'big_relation':a['relation'],'small_valid':b['valid'],'small_relation':b['relation'],'season':'UNKNOWN','reason':'INCOMPLETE_OR_UNRESOLVED'}
 for prefix,v in [('big',a),('small',b)]:
  for key in ('old_high','old_low','new_high','new_low'):
   if key in v:o[prefix+'_'+key]=v[key]
 o['conflict']=bool((a['relation'],b['relation']) in [('UP','DOWN'),('DOWN','UP')])
 if not a['valid'] or not b['valid']:return o
 mid=(big.high.max()+big.low.min())/2;above=bool(big.close.iloc[-1]>mid);o['big28_mid']=float(mid);o['prior_close']=float(big.close.iloc[-1]);o['above_mid']=above
 pair=(a['relation'],b['relation'])
 if pair==('INSIDE','UP') and above:o.update(season='SPRING',reason='BIG_INSIDE_SMALL_UP_ABOVE_MID')
 elif pair==('UP','UP'):o.update(season='SUMMER',reason='BOTH_UP')
 elif pair==('UP','DOWN'):o.update(season='AUTUMN',reason='BIG_UP_SMALL_DOWN_MAY_BE_PULLBACK')
 elif pair==('DOWN','DOWN'):o.update(season='WINTER',reason='BOTH_DOWN_MAY_REVERSE')
 return o

def main():
 if ROOT.exists():raise FileExistsError('refusing overwrite')
 files=[DEF,Path(__file__)]+[p for src,weekly,end in JOBS.values() for p in (src,weekly)];hashes={str(p):sha(p) for p in files};results={};outputs={}
 for name,(src,wfile,end) in JOBS.items():
  f=pd.read_csv(src);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True,errors='raise');f=f.set_index('time')
  if f.index.has_duplicates or not f.index.is_monotonic_increasing or np.any((f.index.asi8//1_000_000)%300000):raise ValueError('invalid grid')
  d,h=aggregates(f);old=pd.read_csv(wfile);rows=[];after=[];shift=[]
  for r in old.itertuples(index=False):
   t=pd.Timestamp(r.as_of_utc);item={'as_of_utc':t.isoformat(),'interval_end_utc':r.interval_end_utc,'old_season':r.season,'old_mid_gate':r.old_mid_gate,**evaluate(d,h,t)};rows.append(item)
   s=evaluate(d,h,t+pd.Timedelta(days=1));shift.append({'as_of_utc':t.isoformat(),'plus_24h_season':s['season'],'base_season':item['season'],'same':item['season']==s['season']})
   future=d.loc[(d.index>=t)&(d.index<t+pd.Timedelta(days=7))]
   if len(future)==7 and future.good.all() and 'prior_close' in item:
    p=item['prior_close'];after.append({'as_of_utc':t.isoformat(),'season':item['season'],'status':'POST_HOC_DESCRIPTIVE','close_change_pct':float((future.close.iloc[-1]/p-1)*100),'high_change_pct':float((future.high.max()/p-1)*100),'low_change_pct':float((future.low.min()/p-1)*100)})
   else:after.append({'as_of_utc':t.isoformat(),'season':item['season'],'status':'UNKNOWN_FUTURE_OR_PAST'})
  segments=[]
  for row in rows:
   if segments and segments[-1]['season']==row['season']:segments[-1]['end_utc_exclusive']=row['interval_end_utc'];segments[-1]['points']+=1
   else:segments.append({'start_utc':row['as_of_utc'],'end_utc_exclusive':row['interval_end_utc'],'season':row['season'],'points':1})
  df=pd.DataFrame(rows);sh=pd.DataFrame(shift);desc=pd.DataFrame(after);results[name]={'points':len(df),'seasons':df.season.value_counts().to_dict(),'big_relation':df.big_relation.value_counts().to_dict(),'small_relation':df.small_relation.value_counts().to_dict(),'conflicts':int(df.conflict.sum()),'old_new_label_changed':int((df.old_season!=df.season).sum()),'shift24_changed':int((~sh.same).sum()),'segments':len(segments),'future_complete':int(desc.status.eq('POST_HOC_DESCRIPTIVE').sum())};outputs[name]=(df,sh,desc,pd.DataFrame(segments))
 if any(sha(p)!=h for p,h in hashes.items()):raise ValueError('input modified')
 ROOT.mkdir(parents=True)
 for name,parts in outputs.items():
  for part,df in zip(('weekly','shift24','future','segments'),parts):df.to_csv(ROOT/f'{name}-{part}.csv',index=False)
 report={'status':'POST_HOC_RESEARCH_NOT_TRADING_OR_GROUND_TRUTH','results':results,'input_sha256':hashes,'limitations':['Settings chosen after earlier cases and data, not blind/out-of-sample.','Fourteen-day comparisons within 28-day range are not confirmed market trend.','Future prices are descriptive, not true season labels.','Sentiment and participant intent unknown.']};(ROOT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
