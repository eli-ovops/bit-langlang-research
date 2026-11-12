"""Frozen two-close price facts plus transparent 28d descriptions, no phase labels."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
OUT=Path('data/verify/market-hold2-2015q1-20261103-01');SPEC=Path('docs/春秋独立判读与连续收盘-2013事前定义-20261102.md');AMEND=Path('docs/2015一季度春秋验证-事前定义-20261103.md')
def held(d,t,r):
 pos=r['position']
 if pos=='UNKNOWN':return 'UNKNOWN'
 if pos=='INSIDE':return 'INSIDE'
 if pos not in ('ABOVE','BELOW'):raise ValueError(pos)
 key='h_new' if pos=='ABOVE' else 'l_new';known=pd.Timestamp(r[key+'_known']);bound=float(r[key+'_price']);start=t-pd.Timedelta(days=2)
 if known>start:return 'WAIT_CONFIRM'
 z=d.loc[(d.index>=start)&(d.index<t)];expected=pd.date_range(start,periods=2,freq='D')
 if not z.index.equals(expected) or not z.good.all():return 'UNKNOWN'
 if (z.close.gt(bound) if pos=='ABOVE' else z.close.lt(bound)).all():return 'HELD_UP_2' if pos=='ABOVE' else 'HELD_DOWN_2'
 return 'OUTSIDE_UNHELD'
def combine(a,b):
 if a in ('UNKNOWN','WAIT_CONFIRM') or b in ('UNKNOWN','WAIT_CONFIRM'):return 'UNKNOWN'
 if a==b and a in ('HELD_UP_2','HELD_DOWN_2','INSIDE'):return 'JOINT_'+a
 if a==b:return 'JOINT_OUTSIDE_UNHELD'
 return 'DISAGREE'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 records=[];comb=[];future=[];files=[Path(__file__),SPEC,AMEND]
 for year in ('2015q1',):
  data=Path(f'data/market/btc-{year}-usd-cross-20261102-01');src=Path(f'data/verify/market-{year}-position-20261102-01');a=pd.read_csv(src/'asof.csv');p=pd.read_csv(src/'pairs.csv');z=pd.read_csv(src/'future.csv');flags=[pd.Timestamp(x) for x in json.loads((src/'summary.json').read_text())['results']['bitstamp_bitfinex']['flags_utc']];dsets={}
  for name in ('bitstamp','bitfinex'):
   path=data/(name+'-4h.csv.gz');d,h=read(path)
   for flag in flags:
    if flag.floor('D') in d.index:d.loc[flag.floor('D'),'good']=False
   dsets[name]=d;files.append(path)
  x={}
  for r in a.to_dict('records'):
   t=pd.Timestamp(r['as_of_utc']);name=r['source'];d=dsets[name];tag=held(d,t,r);row={'year':year,'source':name,'as_of_utc':r['as_of_utc'],'position':r['position'],'held_state':tag,'swing':r['swing'],'old_active':r['active'],'fixed_big':r['big_relation'],'fixed_small':r['small_relation'],'fixed_long':r['long_relation'],'spring_watch':r['spring_watch'],'autumn_watch':r['autumn_watch'],'h_new':r.get('h_new_price'),'h_known':r.get('h_new_known'),'l_new':r.get('l_new_price'),'l_known':r.get('l_new_known')};records.append(row);x[(name,r['as_of_utc'])]=row
   q=z[(z.source==name)&(z.as_of_utc==r['as_of_utc'])].iloc[0];prev=t-pd.Timedelta(days=1);w=d[(d.index>=t)&(d.index<t+pd.Timedelta(days=28))];f={'year':year,'source':name,'as_of_utc':r['as_of_utc'],'position':r['position'],'held_state':tag,'return_7':q.return_7,'return_28':q.return_28,'return_time_7':q.get('return_time_7'),'return_time_28':q.get('return_time_28'),'fixed_status':q.fixed_status,'fixed_follow':q.fixed_follow,'future_28_status':'UNKNOWN_INCOMPLETE'}
   if prev in d.index and d.loc[prev,'good'] and len(w)==28 and w.good.all():
    p0=float(d.loc[prev,'close']);f.update(future_28_status='COMPLETE_DESCRIPTIVE',asof_close=p0,close_28=float(w.close.iloc[-1]),high_28=float(w.high.max()),low_28=float(w.low.min()),close_change_pct=(float(w.close.iloc[-1])/p0-1)*100,high_change_pct=(float(w.high.max())/p0-1)*100,low_change_pct=(float(w.low.min())/p0-1)*100,available_time=(t+pd.Timedelta(days=28)).isoformat())
   future.append(f)
  for row in p.itertuples():
   a=x[('bitstamp',row.as_of_utc)];b=x[('bitfinex',row.as_of_utc)];comb.append({'year':year,'as_of_utc':row.as_of_utc,'bitstamp_held':a['held_state'],'bitfinex_held':b['held_state'],'joint_held':combine(a['held_state'],b['held_state']),'previous_joint_position':row.new_position_joint,'previous_old_joint':row.old_joint})
  files.extend([src/'asof.csv',src/'pairs.csv',src/'future.csv',src/'summary.json',data/'manifest.json'])
 A=pd.DataFrame(records);B=pd.DataFrame(comb);C=pd.DataFrame(future);OUT.mkdir();A.to_csv(OUT/'asof.csv',index=False);B.to_csv(OUT/'joint.csv',index=False);C.to_csv(OUT/'future.csv',index=False);summary={}
 for year,g in B.groupby('year'):
  summary[year]={'points':len(g),'joint_held':g.joint_held.value_counts().to_dict(),'previous_joint_position':g.previous_joint_position.value_counts().to_dict(),'per_source':{name:x.held_state.value_counts().to_dict() for name,x in A[A.year==year].groupby('source')},'future_complete':int(C[(C.year==year)&(C.future_28_status=='COMPLETE_DESCRIPTIVE')].shape[0])}
 (OUT/'summary.json').write_text(json.dumps({'results':summary,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'limits':['No independently obtained human phase reference.','Adjacent prior history known; not strictly blind.','Source quality needs checking.']},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
