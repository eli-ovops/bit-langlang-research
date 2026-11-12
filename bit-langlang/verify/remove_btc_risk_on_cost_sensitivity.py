"""Post-hoc cost sensitivity on two frozen signal definitions."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import MARKET
from .forward_scan import closed_snapshot, read_raw_candles
from .remove_btc_risk_on_research import sha
from .tph_frozen_audit import signals
from .tph_ledger import replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', required=True)
    out = Path(parser.parse_args().outdir)
    if out.exists():
        raise SystemExit('refusing to overwrite output')
    prior_path = Path('data/verify/remove-btc-risk-on-20261030-01/summary.json')
    prior = json.loads(prior_path.read_text())
    if (sha('verify/frozen_config.json') != prior['config_sha256']
            or sha('verify/tph_frozen_audit.py') != prior['signal_code_sha256']
            or sha('verify/tph_ledger.py') != prior['replay_sha256']):
        raise ValueError('config or study engine changed')
    for name, digest in prior['inputs'].items():
        if sha(Path(MARKET) / name) != digest:
            raise ValueError('historical input changed: ' + name)
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
    candidate = ((context.rs7 > 0) & (context.dist_hi < .03) &
                 (eth.low <= low * 1.001) & (eth.close > eth.close.shift(1))).fillna(False).to_numpy()
    if not np.array_equal(original, candidate & context.risk_on.eq(True).to_numpy()):
        raise ValueError('candidate changes more than risk-on condition')
    funding = pd.read_csv(Path(MARKET) / 'ETHUSDT_funding.csv.gz')
    if (funding.empty or funding.ts.duplicated().any() or not funding.ts.is_monotonic_increasing or
            not np.isfinite(funding[['ts', 'funding_rate']].to_numpy(dtype=float)).all()):
        raise ValueError('invalid funding data')
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'POST_HOC_EXPLORATORY_NOT_VALIDATED',
              'definition_sha256': sha('docs/BTC条件移除-滑点敏感性-事后探索定义-20261030.md'),
              'prior_summary_sha256': sha(prior_path), 'study_code_sha256': sha(__file__),
              'inputs': prior['inputs'], 'config_sha256': prior['config_sha256'],
              'replay_sha256': prior['replay_sha256'], 'signal_code_sha256': prior['signal_code_sha256'],
              'assumptions': {'fee_per_side_bps': 5, 'slippage_per_side_bps': [0, 2, 5]}, 'windows': {},
              'limitations': ['post-hoc; previously studied history', 'last-price execution and liquidation proxies',
                              'not a paired causal comparison; actual costs unknown', 'drawdown only at 5m closes']}
    for name in ('later_b', 'combined_later'):
        prior_window = prior['windows'][name]
        start, end = prior_window['start_utc'], prior_window['end_exclusive_utc']
        result['windows'][name] = {'start_utc': start, 'end_exclusive_utc': end, 'variants': {}}
        for variant, hit in (('baseline', original), ('without_btc_risk_on', candidate)):
            scenarios = {}
            for bp in (0, 2, 5):
                metrics, closed, opened = replay(eth, hit, ema, funding, start, end, fee=.0005, slip=bp/10000)
                if abs(metrics['ledger_reconciliation_error']) > 1e-7:
                    raise ValueError('equity reconciliation failed')
                if any(abs(x['net_pnl']-(x['gross_pnl']-x['entry_fee']-x['exit_fee']-x['funding_paid'])) > 1e-8 for x in closed):
                    raise ValueError('trade accounting mismatch')
                if bp == 2:
                    for key in ('equity_end', 'mdd_close_5m_pct', 'closed', 'open', 'skipped'):
                        if not np.isclose(metrics[key], prior_window[variant][key], rtol=0, atol=1e-8):
                            raise ValueError('2bp scenario differs from saved ablation')
                pd.DataFrame(closed).to_csv(out / f'{name}_{variant}_{bp}bp_closed.csv', index=False)
                pd.DataFrame(opened).to_csv(out / f'{name}_{variant}_{bp}bp_open.csv', index=False)
                scenarios[str(bp)] = {**metrics,
                    'fees_usdt': sum(x['entry_fee']+x['exit_fee'] for x in closed)+sum(x['entry_fee'] for x in opened),
                    'signed_funding_usdt': sum(x['funding_paid'] for x in closed+opened)}
                print(name, variant, bp, round(metrics['equity_end'], 2), flush=True)
            result['windows'][name]['variants'][variant] = scenarios
    with (out / 'summary.json').open('x') as file:
        json.dump(result, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


if __name__ == '__main__':
    main()
