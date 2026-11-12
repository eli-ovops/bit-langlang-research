"""Independently check ledger and per-fill causal filters against past daily data."""
import json
from pathlib import Path
from decimal import Decimal as D
import pandas as pd
from .forward_scan import read_raw_candles
STAGE=Path('data/market/nine-futures-stage-oct31-20261031-01');OUT=Path('data/verify/nine-slow-research-20261031-01')
def main():
 report=json.loads((OUT/'summary.json').read_text());names=('base','cycle5','strength30','cadence15','combined');periods=('full','first','second');check={}
 for name in names:
  for period in periods:
   trades=json.loads((OUT/f'{name}-{period}-closed.json').read_text());opened=json.loads((OUT/f'{name}-{period}-open.json').read_text());balance=D('2000');multiple=D(3 if name=='combined' else 2)
   for t in trades:
    d=lambda key:D(str(t[key]));net=d('qty')*(d('exit')-d('entry'))-d('entry_fee')-d('exit_fee')-d('funding_paid');assert abs(net-d('net_pnl'))<D('0.0000001') and abs(balance-d('entry_equity'))<D('0.0000001');assert abs(d('target')-(d('entry')+multiple*(d('entry')-d('stop'))))<D('0.0000001');balance+=net
   assert not opened and abs(balance-D(str(report['results'][name][period]['equity_end'])))<D('0.0000001');check[name+'-'+period]=len(trades)
 symbols=tuple(model for model in json.loads((STAGE/'manifest.json').read_text())['symbols'] if model!='BTCUSDT');daily={}
 for s in symbols+('BTCUSDT',):
  f=read_raw_candles(s,STAGE).set_index('ts');daily[s]=f.resample('D').agg({'high':'max','low':'min','close':'last','open':'count'})
 btc=daily['BTCUSDT'];count={}
 for name in names:
  trades=json.loads((OUT/f'{name}-full-closed.json').read_text());count[name]=len(trades)
  for t in trades:
   ts=pd.Timestamp(t['signal_ts']);day=ts.floor('D')
   if name in ('cadence15','combined'):assert ts.minute%15==10
   if name in ('cycle5','combined'):
    for delta in range(1,6):
     d=day-pd.Timedelta(days=delta);w=btc.loc[d-pd.Timedelta(days=19):d];assert len(w)==20 and w.open.eq(288).all() and w.close.iloc[-1]>(w.high.max()+w.low.min())/2
   if name in ('strength30','combined'):
    old=day-pd.Timedelta(days=31);new=day-pd.Timedelta(days=1);bret=btc.loc[new,'close']/btc.loc[old,'close']-1;scores={}
    for s in symbols:
     hist=daily[s].loc[old:new]
     if len(hist)==31 and hist.open.eq(288).all():scores[s]=hist.close.iloc[-1]/hist.close.iloc[0]-1-bret
    ranked=sorted((-v,s) for s,v in scores.items() if v>0);assert t['symbol'] in [s for _,s in ranked[:2]] and t['signal_rank']==[s for _,s in ranked].index(t['symbol'])+1;assert abs(t['signal_relative_strength']-scores[t['symbol']])<1e-10
 result={'status':'PASS','ledger_trades_by_scenario_period':check,'full_trade_filter_checks':count,'limits':['same input market, not independently sourced','does not authenticate actual execution or trader rules']};(OUT/'independent-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(count))
if __name__=='__main__':main()
