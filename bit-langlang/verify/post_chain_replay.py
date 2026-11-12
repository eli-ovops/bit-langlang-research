"""Re-run fixed historical baselines after local paper-chain checks, not OOS."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_h1_historical import btc_eligible_signals
from .common import MARKET
from .forward_scan import closed_snapshot, read_raw_candles
from .tph_frozen_audit import signals
from .tph_ledger import replay

START='2024-07-01'
END='2026-10-25'
PRIOR=Path('data/verify/execution-delay-diagnostic-20261030/summary.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    out=Path(args.outdir)
    if out.exists(): raise SystemExit('refusing to overwrite existing result')
    prior=json.loads(PRIOR.read_text())
    config=Path('verify/frozen_config.json')
    if digest(config)!=prior['config_sha256']: raise ValueError('frozen configuration changed')
    for name,expected in prior['inputs'].items():
        if digest(Path(MARKET)/name)!=expected: raise ValueError(f'input hash changed: {name}')
    candles={};funding={};state={}
    for sym in ('BTCUSDT','ETHUSDT'):
        data,state[sym]=closed_snapshot(read_raw_candles(sym),pd.Timestamp(END,tz='UTC'),minimum_bars=205*288)
        if data is None or state[sym]['status']!='FRESH': raise ValueError(f'{sym} invalid historical candles')
        candles[sym]=data.reset_index(drop=True)
        f=pd.read_csv(Path(MARKET)/f'{sym}_funding.csv.gz')
        if (f.empty or f.ts.duplicated().any() or not f.ts.is_monotonic_increasing
                or not np.isfinite(f[['ts','funding_rate']].to_numpy(dtype=float)).all()):
            raise ValueError(f'{sym} invalid funding input')
        funding[sym]=f
    if not candles['BTCUSDT'].ts.equals(candles['ETHUSDT'].ts): raise ValueError('BTC/ETH grids differ')
    eth_hit,_,eth_ema=signals(candles['BTCUSDT'],candles['ETHUSDT'])
    btc_hit,btc_ema=btc_eligible_signals(candles['BTCUSDT'])
    result={};ledgers={}
    for label,sym,hit,ema in [('ETH_frozen','ETHUSDT',eth_hit,eth_ema),('BTC_H1','BTCUSDT',btc_hit,btc_ema)]:
        stats,closed,opened=replay(candles[sym],hit,ema,funding[sym],START,END,slip=.0002)
        old=prior['scenarios'][label+'_next_open']
        for key in ('equity_end','mdd_close_5m_pct','closed','open','skipped'):
            if not np.isclose(stats[key],old[key],rtol=0,atol=1e-8): raise ValueError(f'{label} baseline changed: {key}')
        if abs(stats['ledger_reconciliation_error'])>1e-7: raise ValueError(f'{label} ledger mismatch')
        result[label]=stats;ledgers[label]=(closed,opened)
    out.mkdir(parents=True,exist_ok=False)
    for label,(closed,opened) in ledgers.items():
        pd.DataFrame(closed).to_csv(out/f'{label}_closed.csv',index=False)
        pd.DataFrame(opened).to_csv(out/f'{label}_open.csv',index=False)
    summary={'status':'HISTORICAL_REPRODUCTION_NOT_OOS','interval_utc':[START,END],
             'config_sha256':digest(config),'inputs':prior['inputs'],'prior_summary_sha256':digest(PRIOR),
             'source_grids':state,'fee_per_side':.0005,'slippage_per_side':.0002,'results':result,
             'limits':['Same selected history and shared replay implementation; not independent strategy validation.',
                       'FRESH describes candle continuity at the historical end, not current market freshness.',
                       'Costs, liquidation and execution are proxies, not account evidence.',
                       'Candle-close equity drawdown omits intrabar equity.',
                       'BTC H1 and ETH frozen are independent simulated accounts, not a joint portfolio.']}
    with (out/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
