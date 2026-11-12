"""Fixed historical execution-delay sensitivity, not a live execution model."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_h1_historical import btc_eligible_signals
from .common import MARKET
from .prove_method import load5
from .tph_frozen_audit import signals
from .tph_ledger import replay

START, END = '2024-07-01', '2026-10-25'


def delay_one_bar(hit):
    """Delay already-computed signals; do not recompute their eligibility."""
    source = np.asarray(hit, dtype=bool)
    delayed = np.zeros(len(source), dtype=bool)
    delayed[1:] = source[:-1]
    return delayed


def candidates_with_entry_in_window(data, hit, start, end):
    a = int(np.searchsorted(data.ts.array.asi8, pd.Timestamp(start, tz='UTC').value))
    b = int(np.searchsorted(data.ts.array.asi8, pd.Timestamp(end, tz='UTC').value))
    return int(np.asarray(hit, dtype=bool)[max(0, a - 1):max(0, b - 1)].sum())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path('data/verify/execution-delay-diagnostic-20261030')
    out.mkdir(parents=True, exist_ok=False)
    btc, eth = load5('BTCUSDT'), load5('ETHUSDT')
    eth_hit, _, eth_ema = signals(btc, eth)
    btc_hit, btc_ema = btc_eligible_signals(btc)
    inputs = [Path(MARKET) / name for name in (
        'BTCUSDT_5m.csv.gz', 'ETHUSDT_5m.csv.gz',
        'BTCUSDT_funding.csv.gz', 'ETHUSDT_funding.csv.gz')]
    prior_eth = json.loads(Path('data/verify/cost-sensitivity-20261030.json').read_text())
    prior_btc = json.loads(Path('data/verify/btc-h1-historical-20261030.json').read_text())
    expected = {
        'ETH_frozen': next(x for x in prior_eth['scenarios'] if x['slippage_bps_per_side'] == 2),
        'BTC_H1': prior_btc['result'],
    }
    report = {'status': 'EXPLORATORY_NOT_VALIDATED', 'interval_utc': [START, END],
              'preregistration_sha256': digest(Path('docs/执行延迟敏感性-事前定义-20261030.md')),
              'config_sha256': digest(Path('verify/frozen_config.json')),
              'inputs': {p.name: digest(p) for p in inputs},
              'assumptions': {'fee_per_side': .0005, 'slippage_per_side': .0002,
                              'extra_delay_minutes': 5, 'reconfirm_signal_after_delay': False,
                              'accounting': 'two separate 2000 USDT simulated accounts',
                              'candidate_count': 'signals with entry time inside interval',
                              'drawdown': '5-minute closing-equity, not intrabar'},
              'scenarios': {}}
    for name, data, hit, ema in [('ETH_frozen', eth, eth_hit, eth_ema),
                                  ('BTC_H1', btc, btc_hit, btc_ema)]:
        funding = pd.read_csv(Path(MARKET) / ('ETHUSDT_funding.csv.gz' if name == 'ETH_frozen' else 'BTCUSDT_funding.csv.gz'))
        for label, mask in [('next_open', hit), ('extra_5min', delay_one_bar(hit))]:
            result, closed, opened = replay(data, mask, ema, funding, START, END, slip=.0002)
            if label == 'next_open':
                for key in ('equity_end', 'mdd_close_5m_pct', 'closed', 'open', 'skipped'):
                    if not np.isclose(result[key], expected[name][key], rtol=0, atol=1e-8):
                        raise ValueError(f'baseline differs from prior {name} {key}')
            candidates = candidates_with_entry_in_window(data, mask, START, END)
            if candidates != result['closed'] + result['open'] + result['skipped']:
                raise ValueError(f'candidate count mismatch for {name} {label}')
            stem = f'{name}_{label}'
            pd.DataFrame(closed).to_csv(out / f'{stem}_closed.csv', index=False)
            pd.DataFrame(opened).to_csv(out / f'{stem}_open.csv', index=False)
            report['scenarios'][stem] = {'candidates': candidates, **result}
    report['limitations'] = [
        'Selected historical interval, not independent out-of-sample or prospective.',
        'Five-minute delay and next-open fills are assumptions, not measured execution.',
        'No signal reconfirmation; differing caps and compounding change later trades.',
        'Costs, funding timing and liquidation are proxies, not verified exchange conditions.',
    ]
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
