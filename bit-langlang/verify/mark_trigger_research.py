"""Predeclared delayed-fill stop trigger source sensitivity, not real execution."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .forward_scan import closed_snapshot, read_raw_candles
from .mark_stop_diagnostic import END, START, load_mark, sha
from .tph_frozen_audit import signals
from .tph_ledger import replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mark-dir', required=True)
    parser.add_argument('--outdir', required=True)
    args = parser.parse_args()
    out = Path(args.outdir)
    if out.exists():
        raise ValueError('refusing to overwrite output')
    prior_path = Path('data/verify/structural-stop-20261030-01/summary.json')
    prior = json.loads(prior_path.read_text())
    if sha('verify/frozen_config.json') != prior['config_sha256']:
        raise ValueError('frozen configuration changed')
    for name, digest in prior['inputs'].items():
        if sha(Path(MARKET) / name) != digest:
            raise ValueError('original historical input changed')
    candles = {}
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        data, state = closed_snapshot(read_raw_candles(symbol), END, minimum_bars=205 * 288)
        if data is None or state['status'] != 'FRESH':
            raise ValueError('historical candle snapshot invalid')
        candles[symbol] = data.reset_index(drop=True)
    btc, eth = candles['BTCUSDT'], candles['ETHUSDT']
    if not btc.ts.equals(eth.ts):
        raise ValueError('historical symbol grids differ')
    mark = load_mark(args.mark_dir)
    window = eth.loc[(eth.ts >= START) & (eth.ts < END), 'ts'].reset_index(drop=True)
    if not window.equals(mark.ts):
        raise ValueError('mark and last price grids differ')
    mark_low = eth[['ts']].merge(mark[['ts', 'low']], on='ts', how='left', validate='one_to_one').low.to_numpy()
    hit, _, ema = signals(btc, eth)
    funding = pd.read_csv(Path(MARKET) / 'ETHUSDT_funding.csv.gz')
    if funding.empty or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or not np.isfinite(funding[['ts', 'funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('invalid funding history')
    next_open = eth.ts + pd.Timedelta(minutes=5)
    candidates = int((hit & (next_open >= START) & (next_open < END)).sum())
    reports, ledgers = {}, {}
    opens = eth.set_index('ts').open
    last_low_by_time = eth.set_index('ts').low
    mark_low_by_time = mark.set_index('ts').low
    for name, stop_low in (('last_trigger', None), ('mark_trigger', mark_low)):
        metrics, closed, opened = replay(eth, hit, ema, funding, '2024-07-01', '2026-10-25',
                                          slip=.0002, risk_basis='initial', stop_trigger_low=stop_low,
                                          liq_trigger_low=mark_low, delayed_stop=True)
        if candidates != len(closed) + len(opened) + metrics['skipped']:
            raise ValueError('candidate reconciliation failed')
        if metrics['skipped'] != metrics['skipped_invalid_stop'] + metrics['skipped_capacity'] + metrics['skipped_cash']:
            raise ValueError('skip reason reconciliation failed')
        if abs(metrics['ledger_reconciliation_error']) > 1e-7:
            raise ValueError('equity reconciliation failed')
        for row in closed + opened:
            if row['qty'] * row['entry'] > 750 + 1e-7 or row['qty'] * (row['entry'] - row['stop']) > 3 + 1e-7:
                raise ValueError('risk or nominal limit violated')
            if not np.isclose(row['entry_fee'], row['qty'] * row['entry'] * .0005, rtol=0, atol=1e-8):
                raise ValueError('entry fee reconciliation failed')
        for row in closed:
            if not np.isclose(row['net_pnl'], row['gross_pnl'] - row['entry_fee'] - row['exit_fee'] - row['funding_paid'], rtol=0, atol=1e-8):
                raise ValueError('trade PnL reconciliation failed')
            if not np.isclose(row['exit_fee'], row['qty'] * row['exit'] * .0005, rtol=0, atol=1e-8):
                raise ValueError('exit fee reconciliation failed')
            if row['reason'] == 'stop_next_open':
                trigger = pd.Timestamp(row['stop_trigger_bar'])
                exit_time = pd.Timestamp(row['exit_ts'])
                if exit_time != trigger + pd.Timedelta(minutes=5) or not np.isclose(row['exit'], opens.loc[exit_time] * (1 - .0002), rtol=0, atol=1e-8):
                    raise ValueError('delayed stop causality or fill mismatch')
                source_low = last_low_by_time.loc[trigger] if name == 'last_trigger' else mark_low_by_time.loc[trigger]
                if source_low > row['stop']:
                    raise ValueError('recorded stop was not triggered')
        reports[name] = {'candidate_count': candidates, **metrics,
                         'closed_by_reason': pd.Series([x['reason'] for x in closed], dtype='str').value_counts().to_dict(),
                         'fees_usdt': sum(x['entry_fee'] + x['exit_fee'] for x in closed) + sum(x['entry_fee'] for x in opened),
                         'funding_paid_usdt': sum(x['funding_paid'] for x in closed + opened)}
        ledgers[name] = (pd.DataFrame(closed), pd.DataFrame(opened))
    a = set(ledgers['last_trigger'][0].entry_ts) | set(ledgers['last_trigger'][1].get('entry_ts', []))
    b = set(ledgers['mark_trigger'][0].entry_ts) | set(ledgers['mark_trigger'][1].get('entry_ts', []))
    summary = {'status': 'EXPLORATORY_DELAYED_FILL_NOT_REAL_EXECUTION', 'windows_utc': [str(START), str(END)],
               'results': reports, 'entry_times': {'common': len(a & b), 'last_only': len(a - b), 'mark_only': len(b - a)},
               'definition_sha256': sha('docs/标记价触发-延迟成交情景-事前定义-20261030.md'),
               'prior_sha256': sha(prior_path), 'inputs': prior['inputs'], 'config_sha256': prior['config_sha256'],
               'mark_manifest_sha256': sha(Path(args.mark_dir) / 'manifest.json'),
               'supplement_manifest_sha256': sha(Path(args.mark_dir) / 'supplement-20260629/manifest.json'),
               'code_sha256': sha(__file__), 'ledger_code_sha256': sha('verify/tph_ledger.py'),
               'limitations': ['Previously examined history, not OOS.',
                               'Next bar open is delayed synthetic execution, not a stop-market fill or bound.',
                               'Intrabar order, true fees, leverage terms and liquidation are unknown.',
                               'Drawdown is 5-minute close equity, not intrabar.']}
    out.mkdir(parents=True, exist_ok=False)
    for name, (closed, opened) in ledgers.items():
        closed.to_csv(out / f'{name}_closed.csv', index=False)
        opened.to_csv(out / f'{name}_open.csv', index=False)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'results': reports, 'entry_times': summary['entry_times']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
