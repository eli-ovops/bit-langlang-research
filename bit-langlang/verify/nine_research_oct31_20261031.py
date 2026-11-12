"""Limited retrospective single-factor tests with immutable candidate definitions."""
import json
from pathlib import Path
import pandas as pd,numpy as np
from . import nine_futures_oct31_20261031 as model
from .nine_variants_20261031 import simulate
from .forward_scan import read_raw_candles
from .historical_signal_dedup import deduplicate
from .nine_futures_compound_20261031 import sha
STAGE=Path('data/market/nine-futures-stage-oct31-20261031-01');OUT=Path('data/verify/nine-research-oct31-20261031-01');DEF=Path('docs/九币周期强度入场退出-事后对照定义-20261031.md')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 manifest=json.loads((STAGE/'manifest.json').read_text())
 for s,v in manifest['symbols'].items():
  for suffix,key in [('_5m.csv.gz','price_sha256')]+([] if s=='BTCUSDT' else [('_funding.csv.gz','funding_sha256')]):
   if sha(STAGE/(s+suffix))!=v[key]:raise ValueError('source hash mismatch')
 idx,data=model.prepare(STAGE);btc=read_raw_candles('BTCUSDT',STAGE).set_index('ts').resample('D').close.last();up=btc.pct_change(7,fill_method=None).gt(0).shift(1,fill_value=False);reg=up.reindex(idx.floor('D')).to_numpy();start=model.START;end=model.END
 masks={s:{} for s in data}
 for s,d in data.items():
  masks[s]['base']=d['signal'];masks[s]['btc_momentum']=d['signal']&reg;masks[s]['rank1']=d['signal']&(d['rank']<=1)
  positions=np.flatnonzero(d['signal']);kept=deduplicate(positions.astype('int64')*300_000_000_000,interval=3_600_000_000_000);filtered=np.zeros(len(idx),dtype=bool);filtered[np.asarray(kept,dtype='int64')//300_000_000_000]=True;masks[s]['cooldown60']=filtered;masks[s]['target3']=d['signal']
 windows={'full':(start,end),'first':(start,pd.Timestamp('2026-03-01',tz='UTC')),'second':(pd.Timestamp('2026-03-01',tz='UTC'),end)};OUT.mkdir(parents=True);results={}
 for name in ('base','btc_momentum','rank1','cooldown60','target3'):
  changed={s:{**d,'signal':masks[s][name]} for s,d in data.items()};results[name]={}
  for period,(a,b) in windows.items():
   result,closed,opened=simulate(idx,changed,a,b,reward_multiple=3.0 if name=='target3' else 2.0);results[name][period]=result;(OUT/f'{name}-{period}-closed.json').write_text(json.dumps(closed,ensure_ascii=False,allow_nan=False)+'\n');(OUT/f'{name}-{period}-open.json').write_text(json.dumps(opened,ensure_ascii=False,allow_nan=False)+'\n')
 existing=json.loads(Path('data/verify/nine-futures-oct31-20261031-01/summary.json').read_text())['metrics']
 for k in ('equity_end','closed_count','win_count','fees_usdt','funding_usdt'):assert results['base']['full'][k]==existing[k],k
 report={'status':'POST_HOC_NOT_OUT_OF_SAMPLE','definition_sha256':sha(DEF),'code_sha256':sha(__file__),'stage_manifest_sha256':sha(STAGE/'manifest.json'),'results':results,'limitations':['Retrospective user-picked coins, strategy selection, and studied time ranges.','OHLC proxies, execution and costs unknown.','No true order or verified trader exit rules.']};(OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({s:{w:{k:v[k] for k in ('equity_end','return_pct','mdd_close_5m_pct','closed_count','open_count','win_count','fees_usdt','candidate_events')} for w,v in periods.items()} for s,periods in results.items()},indent=2))
if __name__=='__main__':main()
