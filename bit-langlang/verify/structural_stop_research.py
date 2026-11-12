"""Predefined last-price structural stop, historical exploration only."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .fixed_notional_research import WINDOWS, sha
from .forward_scan import closed_snapshot, read_raw_candles
from .tph_frozen_audit import signals
from .tph_ledger import replay


def structural_levels(candles):
    """For each signal bar, use only its own and 19 earlier completed lows."""
    return candles.low.rolling(20,min_periods=20).min().to_numpy()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    out=Path(args.outdir)
    if out.exists(): raise SystemExit('refusing to overwrite')
    old_path=Path('data/verify/fixed-notional-20261030-01/summary.json')
    old=json.loads(old_path.read_text());config=Path('verify/frozen_config.json')
    if sha(config)!=old['config_sha256']: raise ValueError('configuration changed')
    for name,digest in old['inputs'].items():
        if sha(Path(MARKET)/name)!=digest: raise ValueError('historical input hash changed')
    candles={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        data,state=closed_snapshot(read_raw_candles(symbol),pd.Timestamp('2026-10-25',tz='UTC'),minimum_bars=205*288)
        if data is None or state['status']!='FRESH': raise ValueError('historical candles invalid')
        candles[symbol]=data.reset_index(drop=True)
    if not candles['BTCUSDT'].ts.equals(candles['ETHUSDT'].ts): raise ValueError('candle grids differ')
    eth=candles['ETHUSDT'];hit,_,ema=signals(candles['BTCUSDT'],eth);levels=structural_levels(eth)
    funding=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if funding.empty or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or not np.isfinite(funding[['ts','funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('funding input invalid')
    results={};ledgers={}
    for name,start,end in WINDOWS:
        reports={}
        for label,stop in (('fixed_stop',None),('structural_stop',levels)):
            metrics,closed,opened=replay(eth,hit,ema,funding,start,end,slip=.0002,risk_basis='initial',structural_stop=stop)
            next_open=eth.ts+pd.Timedelta(minutes=5)
            candidates=int((hit & ((next_open>=pd.Timestamp(start,tz='UTC')) & (next_open<pd.Timestamp(end,tz='UTC'))).to_numpy()).sum())
            if candidates!=len(closed)+len(opened)+metrics['skipped'] or abs(metrics['ledger_reconciliation_error'])>1e-7:
                raise ValueError('candidate or equity reconciliation failed')
            if metrics['skipped']!=metrics['skipped_invalid_stop']+metrics['skipped_capacity']+metrics['skipped_cash']:
                raise ValueError('skip reasons mismatch')
            for row in closed+opened:
                if row['qty']*row['entry']>750+1e-7 or row['qty']*(row['entry']-row['stop'])>3+1e-7:
                    raise ValueError('nominal or initial risk exceeds research cap')
            for row in closed:
                if abs(row['net_pnl']-(row['gross_pnl']-row['entry_fee']-row['exit_fee']-row['funding_paid']))>1e-8:
                    raise ValueError('trade cost reconciliation failed')
            if label=='fixed_stop':
                for key in ('equity_end','mdd_close_5m_pct','closed','open','skipped'):
                    if not np.isclose(metrics[key],old['windows'][name]['initial'][key],rtol=0,atol=1e-8): raise ValueError('baseline changed: '+key)
            reports[label]={'candidate_count':candidates,'positive_closed_count':int(sum(x['net_pnl']>0 for x in closed)),
                            'fees_usdt':float(sum(x['entry_fee']+x['exit_fee'] for x in closed)+sum(x['entry_fee'] for x in opened)),
                            'funding_cost_usdt':float(sum(x['funding_paid'] for x in closed+opened)),**metrics}
            ledgers[name,label]=(closed,opened)
            print(name,label,'closed',len(closed),'open',len(opened),'equity',round(metrics['equity_end'],2),flush=True)
        results[name]={'start_utc':start,'end_exclusive_utc':end,**reports}
    summary={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':sha(Path('docs/结构止损候选-事前定义-20261030.md')),
             'config_sha256':sha(config),'inputs':old['inputs'],'baseline_summary_sha256':sha(old_path),
             'replay_sha256':sha(Path('verify/tph_ledger.py')),'windows':results,
             'limitations':['Previously studied history, not independent out of sample.',
                '20-bar low and 3U risk cap are research choices, not verified original trader rules.',
                'Last-price lows, liquidation, fees, funding and next-open fills are proxies.',
                'Drawdown uses 5-minute closing equity, not intrabar equity.']}
    out.mkdir(parents=True,exist_ok=False)
    for (name,label),(closed,opened) in ledgers.items():
        pd.DataFrame(closed).to_csv(out/f'{name}_{label}_closed.csv',index=False)
        pd.DataFrame(opened).to_csv(out/f'{name}_{label}_open.csv',index=False)
    with (out/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
