"""Predeclared stale-anchor and cross-exchange abstention research."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
DATA=Path('data/market/btc-2017-usd-cross-20261102-01');SRC=Path('data/verify/market-2017-pivot-20261102-01');OUT=Path('data/verify/market-2017-pivot-guard-20261102-01');DEF=Path('docs/摆点过时与跨所留空-2017事前检验定义-20261102.md')
def guard(d,t,r):
 if r['swing']=='UNKNOWN':return {'active':'UNKNOWN_INPUT'}
 hi=float(r['h_new_price']);lo=float(r['l_new_price']);kh=pd.Timestamp(r['h_new_known']);kl=pd.Timestamp(r['l_new_known'])
 if hi<=lo or kh>t or kl>t:return {'active':'UNKNOWN_BOUNDARY'}
 hits=[]
 for side,start,bound in [('HIGH',kh,hi),('LOW',kl,lo)]:
  f=d.loc[(d.index>=start)&(d.index<t)];expected=pd.date_range(start,t-pd.Timedelta(days=1),freq='D') if start<t else pd.DatetimeIndex([],tz='UTC')
  if not f.index.equals(expected) or not f.good.all():return {'active':'UNKNOWN_HISTORY'}
  z=f[f.close.gt(bound) if side=='HIGH' else f.close.lt(bound)]
  if len(z):hits.append(((z.index[0]+pd.Timedelta(days=1)).isoformat(),side,float(z.close.iloc[0])))
 if hits:
  hits.sort();when,side,price=hits[0];return {'active':'STALE_BROKEN_'+side,'stale_time_utc':when,'stale_side':side,'stale_close':price}
 return {'active':'ACTIVE_'+r['swing'].replace('SWING_','')}
def joint(a,b):
 if a['active'] not in ('ACTIVE_UP','ACTIVE_DOWN') or a['active']!=b['active']:return 'UNKNOWN'
 s=a['active'];long=(a['long_relation'],b['long_relation'])
 if 'UNKNOWN' in long:return 'UNKNOWN'
 if s=='ACTIVE_UP' and all(x in ('DOWN','INSIDE') for x in long):return 'JOINT_POSSIBLE_UP'
 if s=='ACTIVE_DOWN' and all(x=='UP' for x in long):return 'JOINT_POSSIBLE_DOWN'
 return 'NO_JOINT_CANDIDATE'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 a=pd.read_csv(SRC/'asof.csv');ev=pd.read_csv(SRC/'events.csv');flagged=[pd.Timestamp(x) for x in json.loads((SRC/'summary.json').read_text())['quality_warning_utc']];rows=[];events=[]
 for name in ('bitstamp','coinbase'):
  d,_=read(DATA/(name+'-4h.csv.gz'))
  for x in flagged:d.loc[x.floor('D'),'good']=False
  for r in a[a.source==name].to_dict('records'):
   t=pd.Timestamp(r['as_of_utc']);x={**r,**guard(d,t,r)};rows.append(x);prev=t-pd.Timedelta(days=1)
   for kind in ('fixed_28','pivot'):
    z=ev[(ev.source==name)&(ev.as_of_utc==r['as_of_utc'])&(ev.kind==kind)].iloc[0].to_dict();state='UNKNOWN_ASOF';price=None
    if z['status'] not in ('UNKNOWN_INPUT','UNKNOWN_BOUNDARY') and prev in d.index and d.loc[prev,'good']:
     price=float(d.loc[prev,'close']);state='ALREADY_ABOVE' if price>z['upper'] else 'ALREADY_BELOW' if price<z['lower'] else 'WITHIN_OR_EQUAL'
    if kind=='fixed_28':assert state in ('WITHIN_OR_EQUAL','UNKNOWN_ASOF')
    z['asof_close']=price;z['asof_state']=state;z['new_event']=z['status'] if state=='WITHIN_OR_EQUAL' else state;z['new_follow']=z['follow'] if state=='WITHIN_OR_EQUAL' else 'NOT_APPLICABLE';z['active']=x['active'];events.append(z)
 df=pd.DataFrame(rows);couples=[];u=df[df.source=='bitstamp'].set_index('as_of_utc');v=df[df.source=='coinbase'].set_index('as_of_utc')
 for t in u.index:
  x=u.loc[t].to_dict();y=v.loc[t].to_dict();couples.append({'as_of_utc':t,'bitstamp_active':x['active'],'coinbase_active':y['active'],'bitstamp_swing':x['swing'],'coinbase_swing':y['swing'],'bitstamp_long':x['long_relation'],'coinbase_long':y['long_relation'],'bitstamp_spring':x['spring_watch'],'coinbase_spring':y['spring_watch'],'bitstamp_autumn':x['autumn_watch'],'coinbase_autumn':y['autumn_watch'],'joint':joint(x,y)})
 q=pd.DataFrame(couples);E=pd.DataFrame(events);OUT.mkdir();df.to_csv(OUT/'asof-guarded.csv',index=False);q.to_csv(OUT/'joint.csv',index=False);E.to_csv(OUT/'events.csv',index=False);summary={name:{'active':g.active.value_counts().to_dict(),'original_swing':g.swing.value_counts().to_dict()} for name,g in df.groupby('source')};summary['joint']=q.joint.value_counts().to_dict();summary['events']={name:{k:{'event':x.new_event.value_counts().to_dict(),'follow':x.new_follow.value_counts().to_dict()} for k,x in g.groupby('kind')} for name,g in E.groupby('source')};files=[Path(__file__),DEF,SRC/'asof.csv',SRC/'events.csv',DATA/'bitstamp-4h.csv.gz',DATA/'coinbase-4h.csv.gz'];(OUT/'summary.json').write_text(json.dumps({'results':summary,'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
