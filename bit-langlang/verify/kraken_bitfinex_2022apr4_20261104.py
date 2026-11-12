"""Post-hoc check of one known case, not a strategy or independent phase truth."""
import hashlib,json
from pathlib import Path
import pandas as pd
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_2019on_20261103 import support,first_break
from verify.market_support_fallback_2014sp_20261103 import fallback
from verify.market_support_directional_20261104 import classify

OUT=Path('data/verify/market-kraken-bitfinex-2022apr4-20261104-02')
RAW=Path('data/market/kraken-xbtusd-native4h-20261104-01/XBTUSD_240.csv')
FIN=Path('data/market/btc-2022nine-usd-cross-20261104-01/bitfinex-4h.csv.gz')
FIN1=Path('data/market/btc-2022nine-usd-cross-20261104-01/bitfinex-1h.csv.gz')
TRADES=Path('data/verify/market-2022apr4-far-case-trades-20261104-01/summary.json')
T=pd.Timestamp('2022-04-04',tz='UTC'); START=T-pd.Timedelta(days=57); END=T+pd.Timedelta(days=28)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 if OUT.exists():raise FileExistsError(OUT)
 manifest=json.loads(RAW.with_name('manifest.json').read_text()); assert sha(RAW)==manifest['raw_sha256']
 original=pd.read_csv(RAW,header=None,names=['seconds','open','high','low','close','volume','trades'])
 assert original.seconds.is_monotonic_increasing and not original.seconds.duplicated().any()
 selected=original[(original.seconds>=START.timestamp())&(original.seconds<END.timestamp())].copy()
 selected['ts']=selected.seconds*1000
 OUT.mkdir(parents=True)
 kpath=OUT/'kraken-selected-4h.csv';selected[['ts','open','high','low','close','volume','trades']].to_csv(kpath,index=False)
 sources={}
 expected=pd.date_range(START,END,freq='4h',inclusive='left')
 for name,path in [('kraken',kpath),('bitfinex',FIN)]:
  d,h=read(path);window=h.loc[(h.index>=START)&(h.index<END)]
  assert window.index.equals(expected),f'{name}: incomplete grid'
  assert window.good.all() and (window.volume>0).all(),f'{name}: invalid OHLCV'
  if name=='bitfinex':assert (window.min_hour_volume>0).all()
  assert d.loc[(d.index>=START)&(d.index<END)].good.all()
  sources[name]=(d,h,window)
 hourly=pd.read_csv(FIN1);hourly['time']=pd.to_datetime(hourly.ts,unit='ms',utc=True);hourly=hourly.set_index('time');hw=hourly.loc[(hourly.index>=START)&(hourly.index<END)]
 assert hw.index.equals(pd.date_range(START,END,freq='1h',inclusive='left')) and (hw.volume>0).all()
 a=sources['kraken'][2];b=sources['bitfinex'][2];flags=[]
 for col in ['high','low']:
  bad=(a[col]/b[col]>1.1)|(a[col]/b[col]<.9)
  flags.extend(t.isoformat() for t in bad[bad].index)
 if flags:raise ValueError(f'cross-venue quality flags: {sorted(set(flags))}')
 trades=json.loads(TRADES.read_text())['cases'][0];results={}
 for name,(d,h,w) in sources.items():
  x=evaluate_extended(d,h,T);p=pivots(d,T);old=support(d,T,p);new,method=fallback(d,T,p)
  state,flag=classify(new['support_state'],new.get('level'),new.get('close'))
  bar=h.loc[T-pd.Timedelta(hours=4)];trade=trades[name]
  low,high,vol=(float(trade[k]) for k in ['low','high','volume'])
  assert bar.low<=low<=high<=bar.high and 0<vol<=bar.volume
  close=float(new['close']);level=float(new['level']) if new.get('level') is not None else None
  future=d.loc[(d.index>=T)&(d.index<T+pd.Timedelta(days=7))]
  event=first_break(d,T,level) if new.get('history')=='PRIOR_UNBROKEN' else None
  results[name]={'long':x['long_relation'],'big':x['big_relation'],'small':x['small_relation'],'old_state':old['support_state'],'new_state':new['support_state'],'method':method,'level':level,'level_known':new.get('known'),'close':close,'distance_percent_of_close':100*(close-level)/close if level else None,'directional_state':state,'distance_flag':flag,'seven_day_first_break':event,'seven_day_close_change_percent':100*(float(future.close.iloc[-1])/close-1),'trade_count':trade['count'],'case_minute_low':low,'case_minute_high':high,'case_minute_volume':vol,'containing_4h_low':float(bar.low),'containing_4h_high':float(bar.high),'containing_4h_volume':float(bar.volume),'minute_within_own_4h':True}
 data={'status':'POSTHOC_KNOWN_CASE_NOT_INDEPENDENT','window_start':START.isoformat(),'window_end_exclusive':END.isoformat(),'expected_4h_per_venue':len(expected),'cross_venue_extreme_flags':sorted(set(flags)),'results':results,'inputs_sha256':{str(p):sha(p) for p in [RAW,FIN,FIN1,TRADES,Path(__file__)]},'limits':['Known selected case, not independent sample or phase ground truth.','Tick comparison is one minute, not full period.','Member CRC checks received directory, no whole archive hash.','Seven day close return is descriptive, not strategy result.']}
 (OUT/'summary.json').write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str)+'\n');print(json.dumps(data,indent=2,ensure_ascii=False,default=str))
if __name__=='__main__':main()
