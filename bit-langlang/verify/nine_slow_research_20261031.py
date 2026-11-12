"""Retrospective slower cadence, cycle persistence and 30-day rank proxies."""
import json
from pathlib import Path
import numpy as np,pandas as pd
from . import nine_futures_oct31_20261031 as model
from .nine_variants_20261031 import simulate
from .forward_scan import read_raw_candles
from .nine_futures_compound_20261031 import sha
STAGE=Path('data/market/nine-futures-stage-oct31-20261031-01');OUT=Path('data/verify/nine-slow-research-20261031-01');DEF=Path('docs/九币周期空间入场-低频候选定义-20261031.md')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 m=json.loads((STAGE/'manifest.json').read_text())
 for s,v in m['symbols'].items():
  for suffix,k in [('_5m.csv.gz','price_sha256')]+([] if s=='BTCUSDT' else [('_funding.csv.gz','funding_sha256')]):
   if sha(STAGE/(s+suffix))!=v[k]:raise ValueError('data hash')
 idx,base=model.prepare(STAGE);days=idx.floor('D');frames={};daily={}
 for s in base:
  f=read_raw_candles(s,STAGE).set_index('ts').reindex(idx);frames[s]=f;daily[s]=f.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'})
 btc=read_raw_candles('BTCUSDT',STAGE).set_index('ts').reindex(idx).resample('D').agg({'high':'max','low':'min','close':'last','open':'count'})
 phase=btc.close>(btc.high.rolling(20,min_periods=20).max()+btc.low.rolling(20,min_periods=20).min())/2
 last5=phase.shift(1,fill_value=False).rolling(5,min_periods=5).sum().eq(5).reindex(days).to_numpy(dtype=bool)
 br=btc.close.pct_change(30,fill_method=None);scores={}
 for s,d in daily.items():
  eligible=d.open.eq(288).shift(1,fill_value=False).rolling(31,min_periods=31).sum().eq(31);scores[s]=(d.close.pct_change(30,fill_method=None)-br).shift(1).where(eligible)
 scores=pd.DataFrame(scores);ranks=scores.where(scores>0).rank(axis=1,ascending=False,method='first');cadence=(idx.minute%15==10)
 result_data={v:{} for v in ('base','cycle5','strength30','cadence15','combined')}
 for s,d in base.items():
  f=frames[s];lo=f.low.shift(1).rolling(20,min_periods=20).min();hi=f.high.shift(1).rolling(20,min_periods=20).max();lo4=f.low.shift(1).rolling(48,min_periods=48).min();hi4=f.high.shift(1).rolling(48,min_periods=48).max()
  shape=((f.close.shift(1)<f.open.shift(1))&(f.close>f.open)&(f.close>f.close.shift(1))&(f.close>=(lo+hi)/2)&(f.close>=(lo4+hi4)/2)).to_numpy();rank30=ranks[s].reindex(days).to_numpy();score30=scores[s].reindex(days).to_numpy();phase_now=phase.shift(1,fill_value=False).reindex(days).to_numpy(dtype=bool)
  alt=shape&(rank30<=2)&phase_now
  for name in result_data:
   signal=d['signal'] if name in ('base','cycle5','cadence15') else alt
   if name in ('cycle5','combined'):signal=signal&last5
   if name in ('cadence15','combined'):signal=signal&cadence
   result_data[name][s]={**d,'signal':signal,'rank':rank30 if name in ('strength30','combined') else d['rank'],'relative_strength':score30 if name in ('strength30','combined') else d['relative_strength']}
 windows={'full':(model.START,model.END),'first':(model.START,pd.Timestamp('2026-03-01',tz='UTC')),'second':(pd.Timestamp('2026-03-01',tz='UTC'),model.END)}
 OUT.mkdir(parents=True);results={}
 for name,data in result_data.items():
  results[name]={}
  for period,(a,b) in windows.items():
   metrics,closed,opened=simulate(idx,data,a,b,reward_multiple=3.0 if name=='combined' else 2.0);results[name][period]=metrics
   (OUT/f'{name}-{period}-closed.json').write_text(json.dumps(closed,ensure_ascii=False,allow_nan=False)+'\n');(OUT/f'{name}-{period}-open.json').write_text(json.dumps(opened,ensure_ascii=False,allow_nan=False)+'\n')
 old=json.loads(Path('data/verify/nine-futures-oct31-20261031-01/summary.json').read_text())['metrics']
 for k in ('equity_end','closed_count','win_count','fees_usdt','funding_usdt'):assert results['base']['full'][k]==old[k],k
 report={'status':'POST_HOC_NOT_OUT_OF_SAMPLE','definition_sha256':sha(DEF),'code_sha256':sha(__file__),'stage_manifest_sha256':sha(STAGE/'manifest.json'),'results':results,'limitations':['Selected after prior research; no independent holdout.','Fixed retrospectively selected universe.','Unknown execution, funding completeness and real stops/targets.']};(OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({s:{w:{k:v[k] for k in ('equity_end','return_pct','mdd_close_5m_pct','closed_count','open_count','win_count','fees_usdt','candidate_events')} for w,v in periods.items()} for s,periods in results.items()},indent=2))
if __name__=='__main__':main()
