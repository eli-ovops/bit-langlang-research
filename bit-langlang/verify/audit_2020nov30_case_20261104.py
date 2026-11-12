"""Check case OHLC construction, minute containment and as-of no-future influence."""
import json,hashlib
from pathlib import Path
from decimal import Decimal
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_fallback_2014sp_20261103 import fallback
from verify.market_support_directional_20261104 import classify
P=Path('data/verify/market-directional-2020q4-20261104-01');Q=Path('data/verify/market-2020nov30-far-case-trades-20261104-01');OUT=Path('data/verify/market-2020nov30-case-audit-20261104-01.json');T=pd.Timestamp('2020-11-30',tz='UTC');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise FileExistsError(OUT)
 tr=json.loads((Q/'summary.json').read_text())['cases'][0];assert tr['kraken_crossed_end'] and tr['kraken_unique_ids'] and tr['bitfinex_unique_ids'] and not tr['bitfinex_limit_reached']
 f=pd.read_csv(P/'bitfinex-1h.csv');f.index=pd.to_datetime(f.ts,unit='ms',utc=True);f=f[(f.index>=T-pd.Timedelta(days=57))&(f.index<T+pd.Timedelta(days=28))];assert len(f)==85*24 and (f.volume>0).all()
 z=f.resample('4h').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),n=('ts','size'));b=pd.read_csv(P/'bitfinex-4h.csv');b.index=pd.to_datetime(b.ts,unit='ms',utc=True);b=b.loc[z.index];assert (z.n==4).all() and ((z[['open','high','low','close','volume']]-b[['open','high','low','close','volume']]).abs()<1e-7).all().all()
 result={}
 for name in ('kraken','bitfinex'):
  d,h=read(P/(name+'-4h.csv'));q=h[(h.index>=T-pd.Timedelta(days=57))&(h.index<T+pd.Timedelta(days=28))];assert len(q)==85*6 and q.good.all() and (q.volume>0).all();bar=h.loc[T-pd.Timedelta(hours=4)];v=tr[name];assert bar.low<=float(v['low'])<=float(v['high'])<=bar.high and 0<float(v['volume'])<=bar.volume
  def asof(day,hour):
   x=evaluate_extended(day,hour,T);p=pivots(day,T);n,method=fallback(day,T,p);return (x['long_relation'],x['big_relation'],x['small_relation'],n['support_state'],n.get('level'),n.get('close'),method,classify(n['support_state'],n.get('level'),n.get('close')))
  before=asof(d,h);dd=d.copy();hh=h.copy();dd.loc[dd.index>=T,['high','low','close']]=1.0;hh.loc[hh.index>=T,['high','low','close']]=1.0;assert asof(dd,hh)==before
  close,level=Decimal(str(before[5])),Decimal(str(before[4]));assert close-level>close*Decimal('.10');result[name]={'as_of':before,'distance_pct':str((close-level)/close*100),'last_minute_count':v['count'],'minute_in_own_4h':True,'minute_price_low':v['low'],'minute_price_high':v['high'],'bar_low':float(bar.low),'bar_high':float(bar.high),'future_mutation_unchanged':True}
 res={'decision_utc':T.isoformat(),'case_window_4h_each':510,'bitfinex_independent_hourly_reconciled':len(f),'result':result,'sources_sha256':{str(x):sha(x) for x in [P/'kraken-4h.csv',P/'bitfinex-1h.csv',P/'bitfinex-4h.csv',Q/'summary.json',Path(__file__)]},'limits':['OHLC and one-minute containment do not establish authentic trades or independent phase truth.','Cross-exchange quality warning in first future day makes event outcome UNKNOWN under frozen spec.']};OUT.write_text(json.dumps(res,indent=2,default=str)+'\n');print(json.dumps(res,indent=2,default=str))
if __name__=='__main__':main()
