"""Causal daily pivot facts, including newly-confirmed zero-observation state."""
import pandas as pd
from verify.market_multilevel_20261102 import layer
from verify.market_2016_pivot_20261102 import pivots
from verify.cycle_2025q3_continuous_20261104 import asof

def crossing(d,known,t,level,direction):
 if known>t:return None,None,0
 z=d[(d.index>=known)&(d.index<t)];expected=pd.date_range(known,t-pd.Timedelta(days=1),freq='D') if known<t else pd.DatetimeIndex([],tz='UTC')
 if not z.index.equals(expected) or not z.good.all():return None,None,len(z)
 if len(z)==0:return None,None,0
 hit=z.close.gt(level) if direction=='high' else z.close.lt(level)
 return bool(hit.any()),(hit.index[hit][0]+pd.Timedelta(days=1)).isoformat() if hit.any() else None,len(z)

def facts(d,h,t):
 history=d.loc[(d.index>=t-pd.Timedelta(days=84))&(d.index<t)];expected=pd.date_range(t-pd.Timedelta(days=84),t,freq='D',inclusive='left');assert history.index.equals(expected) and history.good.all()
 res=asof(d,h,t);x=layer(history,84);res.update(long84=x['relation'],long84_old_high=x.get('old_high'),long84_old_low=x.get('old_low'),long84_new_high=x.get('new_high'),long84_new_low=x.get('new_low'));hi=float(history.high.max());lo=float(history.low.min());close=float(history.close.iloc[-1]);res.update(history84_low=lo,history84_high=hi,history84_position=(close-lo)/(hi-lo) if hi>lo else None)
 p=pivots(d,t);res.update(p)
 if p['swing']!='UNKNOWN':
  for label,direction in [('h_new','high'),('l_new','low')]:
   k=pd.Timestamp(p[label+'_known']);level=p[label+'_price'];value,at,count=crossing(d,k,t,level,direction);res[label+'_close_position']='ABOVE' if close>level else 'BELOW' if close<level else 'EQUAL';res[label+'_already_crossed']=value;res[label+'_first_cross_known']=at;res[label+'_post_confirm_days']=count
 return res
