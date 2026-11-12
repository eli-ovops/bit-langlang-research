"""Compare predefined position-sizing rules on already studied history."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .forward_scan import closed_snapshot, read_raw_candles
from .tph_frozen_audit import signals
from .tph_ledger import replay

WINDOWS=[('prior','2022-05-01','2024-07-01'),('later_a','2024-07-01','2025-10-01'),
         ('later_b','2025-10-01','2026-10-25'),('combined_later','2024-07-01','2026-10-25')]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    output=Path(args.outdir)
    if output.exists(): raise SystemExit('refusing to overwrite')
    baseline_path=Path('data/verify/fixed-period-audit-20261030/summary.json')
    combined_path=Path('data/verify/post-chain-replay-20261030/summary.json')
    baseline=json.loads(baseline_path.read_text());combined=json.loads(combined_path.read_text())
    config=Path('verify/frozen_config.json')
    if sha(config)!=baseline['config_sha256'] or sha(config)!=combined['config_sha256'] or baseline['inputs']!=combined['inputs']:
        raise ValueError('baseline config or inputs differ')
    for name,digest in baseline['inputs'].items():
        if sha(Path(MARKET)/name)!=digest: raise ValueError('historical input hash changed')
    candles={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        data,state=closed_snapshot(read_raw_candles(symbol),pd.Timestamp('2026-10-25',tz='UTC'),minimum_bars=205*288)
        if data is None or state['status']!='FRESH': raise ValueError('historical candles invalid')
        candles[symbol]=data.reset_index(drop=True)
    if not candles['BTCUSDT'].ts.equals(candles['ETHUSDT'].ts): raise ValueError('candle grids differ')
    eth=candles['ETHUSDT'];hit,_,ema=signals(candles['BTCUSDT'],eth)
    funding=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if funding.empty or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or not np.isfinite(funding[['ts','funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('funding input invalid')
    results={};ledgers={}
    for name,start,end in WINDOWS:
        reports={}
        for basis in ('equity','initial'):
            metrics,closed,opened=replay(eth,hit,ema,funding,start,end,slip=.0002,risk_basis=basis)
            candidates=int((hit & ((eth.ts+pd.Timedelta(minutes=5)>=pd.Timestamp(start,tz='UTC')) &
                                    (eth.ts+pd.Timedelta(minutes=5)<pd.Timestamp(end,tz='UTC'))).to_numpy()).sum())
            if candidates!=len(closed)+len(opened)+metrics['skipped'] or abs(metrics['ledger_reconciliation_error'])>1e-7:
                raise ValueError('candidate or equity reconciliation failed')
            for row in closed:
                if abs(row['net_pnl']-(row['gross_pnl']-row['entry_fee']-row['exit_fee']-row['funding_paid']))>1e-8:
                    raise ValueError('trade cost reconciliation failed')
            original=(combined['results']['ETH_frozen'] if name=='combined_later' else baseline['windows']['ETH_frozen'][name])
            if basis=='equity':
                for key in ('equity_end','mdd_close_5m_pct','closed','open','skipped'):
                    if not np.isclose(metrics[key],original[key],rtol=0,atol=1e-8): raise ValueError('baseline changed: '+key)
            reports[basis]={'candidate_count':candidates,'positive_closed_count':int(sum(x['net_pnl']>0 for x in closed)),
                            'fees_usdt':float(sum(x['entry_fee']+x['exit_fee'] for x in closed)+sum(x['entry_fee'] for x in opened)),
                            'funding_cost_usdt':float(sum(x['funding_paid'] for x in closed+opened)),**metrics}
            ledgers[name,basis]=(closed,opened)
            print(name,basis,'closed',len(closed),'equity',round(metrics['equity_end'],2),'cagr',round(metrics['cagr_pct'],2),flush=True)
        results[name]={'start_utc':start,'end_exclusive_utc':end,**reports}
    summary={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':sha(Path('docs/固定名义规模-事前定义-20261030.md')),
             'config_sha256':sha(config),'inputs':baseline['inputs'],'replay_sha256':sha(Path('verify/tph_ledger.py')),
             'baseline_summary_sha256':sha(baseline_path),'combined_baseline_sha256':sha(combined_path),
             'assumptions':{'fixed_initial_price_risk_usdt':3,'fixed_nominal_usdt_before_cash_limit':750,
                            'fee_per_side':.0005,'slippage_per_side':.0002},'windows':results,
             'limitations':['Same previously studied history, not independent OOS.',
                'Fixed price risk is a research proxy, not established original position sizing.',
                'Isolated liquidation, execution, fees and funding are proxies; actual account unknown.',
                'Close-price drawdown excludes intrabar exposure; accounts reset for each window.']}
    output.mkdir(parents=True,exist_ok=False)
    for (name,basis),(closed,opened) in ledgers.items():
        pd.DataFrame(closed).to_csv(output/f'{name}_{basis}_closed.csv',index=False)
        pd.DataFrame(opened).to_csv(output/f'{name}_{basis}_open.csv',index=False)
    with (output/'summary.json').open('x',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
