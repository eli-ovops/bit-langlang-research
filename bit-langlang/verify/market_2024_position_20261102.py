"""Independent venue price position and old-guard comparisons; not seasons."""
from pathlib import Path
import hashlib,json
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2016_pivot_20261102 import pivots,eventrow
from verify.market_2017_pivot_guard_20261102 import guard,joint
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2023_return_28d_20261102 import returned
R=Path('data/market');BASE=R/'btc-2024-usd-cross-20261102-01';ALT=BASE;OUT=Path('data/verify/market-2024-position-20261102-01');DEF=Path('docs/2013数据不足-2024补充压力检验事前定义-20261102.md')
def location(d,t,r):
 if r['swing']=='UNKNOWN':return 'UNKNOWN'
 h,l=r['h_new_price'],r['l_new_price'];day=t-pd.Timedelta(days=1)
 if h<=l or day not in d.index or not d.loc[day,'good']:return 'UNKNOWN'
 p=float(d.loc[day,'close']);return 'ABOVE' if p>h else 'BELOW' if p<l else 'INSIDE'
def combine(a,b):
 if 'UNKNOWN' in (a,b):return 'UNKNOWN'
 return 'JOINT_'+a if a==b else 'DISAGREE'
def main():
 if OUT.exists():raise FileExistsError(OUT)
 paths={'bitstamp':BASE/'bitstamp-4h.csv.gz','bitfinex':ALT/'bitfinex-4h.csv.gz'};items=[];outcomes=[];pairs=[];quality={};times=pd.date_range('2024-03-04','2024-08-26',freq='7D',tz='UTC');assert len(times)==26
 for other in ('bitfinex',):
  pair='bitstamp_'+other;A=pd.read_csv(paths['bitstamp']);B=pd.read_csv(paths[other]);m=A.merge(B,on='ts',suffixes=('_a','_b'));bad=pd.Series(False,index=m.index)
  for col in ('high','low'):
   q=m[col+'_b']/m[col+'_a'];bad|=(q>1.1)|(q<.9)
  flags=pd.to_datetime(m.loc[bad,'ts'],unit='ms',utc=True);quality[pair]=[x.isoformat() for x in flags];local={}
  for venue in ('bitstamp',other):
   d,h=read(paths[venue])
   for f in flags:
    if f in h.index:h.loc[f,'good']=False
    if f.floor('D') in d.index:d.loc[f.floor('D'),'good']=False
   this=[]
   for t in times:
    f=evaluate_extended(d,h,t);p=pivots(d,t);x={'pair':pair,'source':venue,'as_of_utc':t.isoformat(),**f,**p};x.update(guard(d,t,x));x['position']=location(d,t,x);this.append(x);items.append(x)
    ev={'pair':pair,'source':venue,'as_of_utc':t.isoformat(),'position':x['position']}
    if x['position'] in ('ABOVE','BELOW'):
     b=x['h_new_price'] if x['position']=='ABOVE' else x['l_new_price'];side='UPPER_BREAK' if x['position']=='ABOVE' else 'LOWER_BREAK';ev['bound']=b
     for n in (7,28):
      status,when,price=returned(d,t,side,b,n);ev.update({f'return_{n}':status,f'return_time_{n}':when,f'return_close_{n}':price})
    else:ev.update(return_7='NOT_APPLICABLE',return_28='NOT_APPLICABLE')
    prior=d[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)]
    if len(prior)==28 and prior.good.all():
     hi=float(prior.high.max());lo=float(prior.low.min());ev.update(fixed_upper=hi,fixed_lower=lo,**{'fixed_'+k:v for k,v in eventrow(d,t,hi,lo).items()})
    else:ev.update(fixed_status='UNKNOWN_INPUT',fixed_follow='UNKNOWN')
    outcomes.append(ev)
   local[venue]={x['as_of_utc']:x for x in this}
  for t in times:
   k=t.isoformat();a=local['bitstamp'][k];b=local[other][k];pairs.append({'pair':pair,'as_of_utc':k,'bitstamp_position':a['position'],other+'_position':b['position'],'old_joint':joint(a,b),'new_position_joint':combine(a['position'],b['position']),'bitstamp_active':a['active'],'other_active':b['active'],'bitstamp_long':a['long_relation'],'other_long':b['long_relation'],'bitstamp_spring':a['spring_watch'],'other_spring':b['spring_watch'],'bitstamp_autumn':a['autumn_watch'],'other_autumn':b['autumn_watch']})
 X=pd.DataFrame(items);Y=pd.DataFrame(pairs);Z=pd.DataFrame(outcomes);OUT.mkdir();X.to_csv(OUT/'asof.csv',index=False);Y.to_csv(OUT/'pairs.csv',index=False);Z.to_csv(OUT/'future.csv',index=False);summary={}
 for pair,g in Y.groupby('pair'):
  old=g.old_joint.eq('UNKNOWN');summary[pair]={'points':len(g),'old_joint':g.old_joint.value_counts().to_dict(),'new_position':g.new_position_joint.value_counts().to_dict(),'old_unknown_and_joint_direction':int((old&g.new_position_joint.isin(['JOINT_ABOVE','JOINT_BELOW'])).sum()),'old_unknown_and_any_single_direction':int((old&(g.bitstamp_position.isin(['ABOVE','BELOW'])|g.filter(regex='_position$').iloc[:,1].isin(['ABOVE','BELOW']))).sum()),'flags_utc':quality[pair]}
 files=[Path(__file__),DEF,BASE/'manifest.json',*paths.values(),Path('verify/market_2016_pivot_20261102.py'),Path('verify/market_2017_pivot_guard_20261102.py'),Path('verify/market_2020_cross_20261102.py'),Path('verify/market_2023_return_28d_20261102.py')];(OUT/'summary.json').write_text(json.dumps({'results':summary,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'scope':'Prices only, no phase truth; pair-specific quality flags.'},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
