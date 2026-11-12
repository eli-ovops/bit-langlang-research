"""Compare fixed-window proxies and confirmed pivots without future leakage."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from verify.market_2018_transition_20261102 import read,event
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2023_return_28d_20261102 import returned
DATA=Path('data/market/btc-2017-usd-cross-20261102-01');OUT=Path('data/verify/market-2017-pivot-20261102-01');DEF=Path('docs/摆点过时与跨所留空-2017事前检验定义-20261102.md')
def pivots(d,t):
 z=d.loc[(d.index>=t-pd.Timedelta(days=56))&(d.index<t)]
 if len(z)!=56 or not z.good.all():return {'swing':'UNKNOWN','pivot_reason':'INCOMPLETE'}
 highs=[];lows=[]
 for i in range(2,len(z)-2):
  h=z.high.iloc[i];l=z.low.iloc[i];hl=np.r_[z.high.iloc[i-2:i],z.high.iloc[i+1:i+3]];ll=np.r_[z.low.iloc[i-2:i],z.low.iloc[i+1:i+3]];is_h=bool((h>hl).all());is_l=bool((l<ll).all())
  if is_h and not is_l:highs.append((z.index[i],float(h)))
  if is_l and not is_h:lows.append((z.index[i],float(l)))
 if len(highs)<2 or len(lows)<2:return {'swing':'UNKNOWN','pivot_reason':'INSUFFICIENT_PIVOTS'}
 oldh,newh=highs[-2:];oldl,newl=lows[-2:];s='SWING_UP' if newh[1]>oldh[1] and newl[1]>oldl[1] else 'SWING_DOWN' if newh[1]<oldh[1] and newl[1]<oldl[1] else 'SWING_MIXED'
 r={'swing':s,'pivot_reason':'OK'}
 for name,(day,price) in [('h_old',oldh),('h_new',newh),('l_old',oldl),('l_new',newl)]:r[name+'_day']=day.isoformat();r[name+'_known']=(day+pd.Timedelta(days=3)).isoformat();r[name+'_price']=price
 return r

def eventrow(d,t,hi,lo):
 if not np.isfinite([hi,lo]).all() or hi<=lo:return {'status':'UNKNOWN_BOUNDARY','follow':'UNKNOWN'}
 x=event(d,t,hi,lo);r={'status':x['status'],'event_time':x.get('event_time_utc'),'event_close':x.get('event_close'),'follow':'UNKNOWN'}
 if x['status'] in ('UPPER_BREAK','LOWER_BREAK'):
  side=x['status'];bound=hi if side=='UPPER_BREAK' else lo;st,at,price=returned(d,pd.Timestamp(x['event_time_utc']),side,bound,7);r.update(follow=st,return_time=at,return_close=price)
 elif x['status']=='UNRESOLVED_28D':r['follow']='NO_BREAK'
 return r

def main():
 if OUT.exists():raise FileExistsError(OUT)
 a=pd.read_csv(DATA/'bitstamp-4h.csv.gz');b=pd.read_csv(DATA/'coinbase-4h.csv.gz');v=a.merge(b,on='ts',suffixes=('_bitstamp','_coinbase'));bad=pd.Series(False,index=v.index)
 for col in ('high','low'):
  ratio=v[col+'_coinbase']/v[col+'_bitstamp'];bad|=(ratio>1.1)|(ratio<.9)
 flagged=pd.to_datetime(v.loc[bad,'ts'],unit='ms',utc=True);rows=[];events=[];times=pd.date_range('2017-03-06','2017-08-28',freq='7D',tz='UTC');assert len(times)==26
 for name in ('bitstamp','coinbase'):
  d,h=read(DATA/(name+'-4h.csv.gz'))
  for instant in flagged:
   if instant in h.index:h.loc[instant,'good']=False
   day=instant.floor('D')
   if day in d.index:d.loc[day,'good']=False
  for t in times:
   fixed=evaluate_extended(d,h,t);p=pivots(d,t);record={'source':name,'as_of_utc':t.isoformat(),**fixed,**p};s=p['swing'];record['transition']='POSSIBLE_UP' if fixed['long_relation'] in ('DOWN','INSIDE') and s=='SWING_UP' else 'POSSIBLE_DOWN' if fixed['long_relation']=='UP' and s=='SWING_DOWN' else 'UNKNOWN' if s=='UNKNOWN' or fixed['long_relation']=='UNKNOWN' else 'NONE';rows.append(record)
   prior=d[(d.index>=t-pd.Timedelta(days=28))&(d.index<t)]
   for typ in ('fixed_28','pivot'):
    rec={'source':name,'as_of_utc':t.isoformat(),'kind':typ}
    if typ=='fixed_28' and len(prior)==28 and prior.good.all():hi,lo=float(prior.high.max()),float(prior.low.min())
    elif typ=='pivot' and s!='UNKNOWN':hi,lo=p['h_new_price'],p['l_new_price']
    else:rec.update(status='UNKNOWN_INPUT',follow='UNKNOWN');events.append(rec);continue
    rec.update(upper=hi,lower=lo,**eventrow(d,t,hi,lo));events.append(rec)
 files=[DEF,Path(__file__),DATA/'manifest.json',DATA/'bitstamp-4h.csv.gz',DATA/'coinbase-4h.csv.gz',Path('verify/market_2020_cross_20261102.py'),Path('verify/market_2018_transition_20261102.py'),Path('verify/market_2023_return_28d_20261102.py')];OUT.mkdir();df=pd.DataFrame(rows);ev=pd.DataFrame(events);df.to_csv(OUT/'asof.csv',index=False);ev.to_csv(OUT/'events.csv',index=False);summary={}
 for name,g in df.groupby('source'):
  summary[name]={'points':len(g),'fixed_big':g.big_relation.value_counts().to_dict(),'swing':g.swing.value_counts().to_dict(),'transition':g.transition.value_counts().to_dict(),'spring_watch':g.spring_watch.value_counts().to_dict(),'autumn_watch':g.autumn_watch.value_counts().to_dict(),'events':{kind:ev[(ev.source==name)&(ev.kind==kind)].status.value_counts().to_dict() for kind in ('fixed_28','pivot')}}
 (OUT/'summary.json').write_text(json.dumps({'status':'RESEARCH_STRUCTURAL_FACTS_NOT_TRUTH','quality_warning_utc':[x.isoformat() for x in flagged],'results':summary,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
