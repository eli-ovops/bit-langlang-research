"""H2 ETH previous-20-low recapture diagnostic, not a deployable strategy."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals
from .tph_ledger import replay


def recapture_signals(base_hit, coin):
    previous_low=coin.low.shift(1).rolling(20,min_periods=20).min()
    return (pd.Series(base_hit,index=coin.index)&(coin.close>previous_low)).fillna(False).to_numpy()


def main():
    out=Path('data/verify/eth-h2-historical-20261030.json')
    if out.exists(): raise SystemExit('refusing to overwrite existing result')
    btc=load5('BTCUSDT');eth=load5('ETHUSDT');fund=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    base,_,ema=signals(btc,eth);hit=recapture_signals(base,eth)
    result,closed,opened=replay(eth,hit,ema,fund,'2024-07-01','2026-10-25',slip=.0002)
    mask=(eth.ts>=pd.Timestamp('2024-07-01',tz='UTC'))&(eth.ts<pd.Timestamp('2026-10-25',tz='UTC'))
    pnl=pd.Series([r['net_pnl'] for r in closed],dtype=float);winners=pnl[pnl>0].sort_values(ascending=False)
    inp=[Path(MARKET)/n for n in ('BTCUSDT_5m.csv.gz','ETHUSDT_5m.csv.gz','ETHUSDT_funding.csv.gz')]
    data={'status':'EXPLORATORY_NOT_VALIDATED','hypothesis':'baseline ETH signal additionally closes above prior 20-bar low',
          'preregistration_sha256':hashlib.sha256(Path('docs/ETH候选-H2-事前定义-20261030.md').read_bytes()).hexdigest(),
          'config_sha256':hashlib.sha256(Path('verify/frozen_config.json').read_bytes()).hexdigest(),
          'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inp},
          'baseline_candidates':int((base&mask.to_numpy()).sum()),'candidate_count':int((hit&mask.to_numpy()).sum()),
          'result':result,'positive_trades':int((pnl>0).sum()),'top_3_net_positive_usdt':float(winners.head(3).sum()),
          'limitations':['historical interval was already used repeatedly; not independent OOS','not matched-trade causality; account paths can differ','fees, slippage and liquidation are assumptions','not proof of trader intent or of future profit']}
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
