"""Predefined ETH prior-low sweep/reclaim candidate, historical only."""
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


def sweep_reclaim(base, candles):
    previous_low=candles.low.shift(1).rolling(20,min_periods=20).min()
    return (np.asarray(base,dtype=bool) & (candles.low<previous_low) & (candles.close>previous_low)).fillna(False).to_numpy()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',required=True);args=parser.parse_args()
    output=Path(args.outdir)
    if output.exists(): raise SystemExit('refusing to overwrite')
    baseline_path=Path('data/verify/fixed-period-audit-20261030/summary.json')
    combined_path=Path('data/verify/post-chain-replay-20261030/summary.json')
    baseline=json.loads(baseline_path.read_text());combined=json.loads(combined_path.read_text())
    config=Path('verify/frozen_config.json')
    if sha(config)!=baseline['config_sha256'] or sha(config)!=combined['config_sha256']: raise ValueError('configuration changed')
    if baseline['inputs']!=combined['inputs']: raise ValueError('baseline inputs differ')
    for filename,digest in baseline['inputs'].items():
        if sha(Path(MARKET)/filename)!=digest: raise ValueError('source data changed')
    data={}
    for sym in ('BTCUSDT','ETHUSDT'):
        d,state=closed_snapshot(read_raw_candles(sym),pd.Timestamp('2026-10-25',tz='UTC'),minimum_bars=205*288)
        if d is None or state['status']!='FRESH': raise ValueError(f'{sym} candle data invalid')
        data[sym]=d.reset_index(drop=True)
    if not data['BTCUSDT'].ts.equals(data['ETHUSDT'].ts): raise ValueError('BTC and ETH grids differ')
    eth=data['ETHUSDT'];base,_,ema=signals(data['BTCUSDT'],eth);hit=sweep_reclaim(base,eth)
    funding=pd.read_csv(Path(MARKET)/'ETHUSDT_funding.csv.gz')
    if funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or not np.isfinite(funding[['ts','funding_rate']].to_numpy(dtype=float)).all(): raise ValueError('invalid funding source')
    reports={};ledgers={}
    for label,start,end in WINDOWS:
        metrics,closed,opened=replay(eth,hit,ema,funding,start,end,slip=.0002)
        enter=eth.ts+pd.Timedelta(minutes=5)
        window=(enter>=pd.Timestamp(start,tz='UTC'))&(enter<pd.Timestamp(end,tz='UTC'))
        candidate=int((hit & window.to_numpy()).sum())
        if candidate!=metrics['closed']+metrics['open']+metrics['skipped'] or abs(metrics['ledger_reconciliation_error'])>1e-7:
            raise ValueError('candidate count or ledger mismatch')
        original=(combined['results']['ETH_frozen'] if label=='combined_later' else baseline['windows']['ETH_frozen'][label])
        reports[label]={'start_utc':start,'end_exclusive_utc':end,'candidate_count':candidate,
                        'positive_closed_count':int(sum(x['net_pnl']>0 for x in closed)),
                        'h3':metrics,'baseline':original}
        ledgers[label]=(closed,opened)
        print(label,'candidates',candidate,'closed',metrics['closed'],'equity',round(metrics['equity_end'],2),'cagr',round(metrics['cagr_pct'],2),flush=True)
    report={'status':'EXPLORATORY_NOT_VALIDATED','definition_sha256':sha(Path('docs/ETH候选-H3-事前定义-20261030.md')),
            'config_sha256':sha(config),'inputs':baseline['inputs'],
            'baseline_summary_sha256':sha(baseline_path),'combined_baseline_sha256':sha(combined_path),
            'comparison':'independent reset accounts, fixed historical windows, not matched trades',
            'limitations':['previously explored history; not independent OOS',
                'mechanical 20-bar sweep is not established as the trader rule',
                'fees, slippage, funding and liquidation use proxies',
                '5-minute closing equity drawdown excludes intrabar fluctuations'],
            'windows':reports}
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    output.mkdir(parents=True,exist_ok=False)
    for label,(closed,opened) in ledgers.items():
        pd.DataFrame(closed).to_csv(output/f'{label}_closed.csv',index=False)
        pd.DataFrame(opened).to_csv(output/f'{label}_open.csv',index=False)
    (output/'summary.json').write_text(encoded,encoding='utf-8')


if __name__=='__main__':main()
