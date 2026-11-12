"""Post-hoc ablation; exploratory replay only, never a trade instruction."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', required=True)
    output = Path(parser.parse_args().outdir)
    if output.exists():
        raise SystemExit('refusing to overwrite output')
    baseline_path = Path('data/verify/fixed-notional-20261030-01/summary.json')
    baseline = json.loads(baseline_path.read_text())
    if sha('verify/frozen_config.json') != baseline['config_sha256']:
        raise ValueError('config hash mismatch')
    for filename, digest in baseline['inputs'].items():
        if sha(Path(MARKET) / filename) != digest:
            raise ValueError('historical input hash mismatch: ' + filename)
    frames = {}
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        frame, state = closed_snapshot(read_raw_candles(symbol), pd.Timestamp('2026-10-25', tz='UTC'), minimum_bars=205*288)
        if frame is None or state['status'] != 'FRESH':
            raise ValueError('historical candles invalid')
        frames[symbol] = frame.reset_index(drop=True)
    btc, eth = frames['BTCUSDT'], frames['ETHUSDT']
    if not btc.ts.equals(eth.ts):
        raise ValueError('candle grids differ')
    original, context, ema = signals(btc, eth)
    low = eth.low.rolling(20, min_periods=20).min()
    candidate = ((context.rs7 > 0) & (context.dist_hi < .03)
                 & (eth.low <= low * 1.001) & (eth.close > eth.close.shift(1))).fillna(False).to_numpy()
    if not np.array_equal(original, candidate & context.risk_on.eq(True).to_numpy()):
        raise ValueError('ablation differs from baseline by more than risk-on condition')
    funding = pd.read_csv(Path(MARKET) / 'ETHUSDT_funding.csv.gz')
    if funding.empty or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing:
        raise ValueError('invalid funding sequence')
    if not np.isfinite(funding[['ts', 'funding_rate']].to_numpy(dtype=float)).all():
        raise ValueError('invalid funding values')
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'POST_HOC_EXPLORATORY_NOT_VALIDATED', 'windows': {},
              'definition_sha256': sha('docs/BTC风险开启条件移除-事后探索定义-20261030.md'),
              'baseline_sha256': sha(baseline_path), 'inputs': baseline['inputs'],
              'config_sha256': baseline['config_sha256'], 'signal_code_sha256': sha('verify/tph_frozen_audit.py'),
              'replay_sha256': sha('verify/tph_ledger.py'), 'study_code_sha256': sha(__file__),
              'assumptions': {'fee_per_side': .0005, 'slippage_per_side': .0002,
                              'liquidation': 'isolated last-price proxy; no liquidation fee'},
              'limitations': ['post-hoc and repeatedly studied; not independent OOS',
                              'different dynamic paths, not matched-trade causality',
                              'next-open, costs and liquidation are assumptions',
                              '5m close drawdown excludes intrabar trough']}
    for name, window in baseline['windows'].items():
        start, end = window['start_utc'], window['end_exclusive_utc']
        results = {}
        for variant, hits in (('baseline', original), ('without_btc_risk_on', candidate)):
            metrics, closed, opened = replay(eth, hits, ema, funding, start, end, fee=.0005, slip=.0002)
            entry_time = eth.ts + pd.Timedelta(minutes=5)
            n = int((hits & ((entry_time >= pd.Timestamp(start, tz='UTC')) & (entry_time < pd.Timestamp(end, tz='UTC'))).to_numpy()).sum())
            if n != len(closed) + len(opened) + metrics['skipped'] or abs(metrics['ledger_reconciliation_error']) > 1e-7:
                raise ValueError('candidate or equity reconciliation failed')
            for row in closed:
                if abs(row['net_pnl'] - (row['gross_pnl'] - row['entry_fee'] - row['exit_fee'] - row['funding_paid'])) > 1e-8:
                    raise ValueError('trade reconciliation failed')
            if variant == 'baseline':
                old = window['equity']
                for key in ('equity_end', 'mdd_close_5m_pct', 'closed', 'open', 'skipped'):
                    if not np.isclose(metrics[key], old[key], rtol=0, atol=1e-8):
                        raise ValueError('baseline differs: ' + name + ' ' + key)
            pd.DataFrame(closed).to_csv(output / f'{name}_{variant}_closed.csv', index=False)
            pd.DataFrame(opened).to_csv(output / f'{name}_{variant}_open.csv', index=False)
            results[variant] = {**metrics, 'candidate_count': n,
                'fees_usdt': sum(x['entry_fee'] + x['exit_fee'] for x in closed) + sum(x['entry_fee'] for x in opened),
                'signed_funding_usdt': sum(x['funding_paid'] for x in closed + opened)}
            print(name, variant, 'closed', len(closed), 'equity', round(metrics['equity_end'], 2), flush=True)
        result['windows'][name] = {'start_utc': start, 'end_exclusive_utc': end, **results}
    with (output / 'summary.json').open('x') as file:
        json.dump(result, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


if __name__ == '__main__':
    main()
