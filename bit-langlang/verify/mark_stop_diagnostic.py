"""Compare stop touches within original historical exposures, without replaying fills."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .common import MARKET
from .forward_scan import read_raw_candles

START = pd.Timestamp('2024-07-01', tz='UTC')
END = pd.Timestamp('2026-10-25', tz='UTC')
FREQ = pd.Timedelta(minutes=5)
NAMES = ('fixed_stop', 'structural_stop')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_archive(directory, item):
    path = directory / item['name']
    meta = (directory / (item['name'] + '.CHECKSUM')).read_text().split()
    if len(meta) != 2 or meta[1] != item['name'] or meta[0] != item['sha256'] or sha(path) != meta[0]:
        raise ValueError('archive checksum mismatch: ' + item['name'])
    with ZipFile(path) as archive:
        csv_name = item['name'][:-4] + '.csv'
        if archive.namelist() != [csv_name] or archive.testzip() is not None:
            raise ValueError('unexpected or corrupt archive: ' + item['name'])
        with archive.open(csv_name) as source:
            frame = pd.read_csv(source, header=None, usecols=range(5), names=['ts', 'open', 'high', 'low', 'close'])
    if frame.iloc[0]['ts'] == 'open_time':
        frame = frame.iloc[1:].copy()
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
    frame['ts'] = pd.to_datetime(frame.ts, unit='ms', utc=True)
    return frame


def load_mark(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    expected = ([f'ETHUSDT-5m-{x}.zip' for x in pd.period_range('2024-07', '2026-09', freq='M')]
                + [f'ETHUSDT-5m-{x:%Y-%m-%d}.zip' for x in pd.date_range('2026-10-01', '2026-10-24')])
    if [x['name'] for x in manifest['files']] != expected:
        raise ValueError('mark archive list does not match predeclared window')
    frames = []
    for item in manifest['files']:
        frames.append(read_archive(directory, item))
    data = pd.concat(frames, ignore_index=True)
    expected_index = pd.date_range(START, END, freq='5min', inclusive='left')
    missing_day = pd.date_range('2026-06-29', '2026-06-30', freq='5min', tz='UTC', inclusive='left')
    actual_index = pd.DatetimeIndex(data.ts)
    if actual_index.has_duplicates or not actual_index.is_monotonic_increasing or not expected_index.difference(actual_index).equals(missing_day) or len(actual_index.difference(expected_index)):
        raise ValueError('monthly archive gap differs from documented missing day')
    supplement_dir = directory / 'supplement-20260629'
    supplement = json.loads((supplement_dir / 'manifest.json').read_text())
    if supplement['name'] != 'ETHUSDT-5m-2026-06-29.zip':
        raise ValueError('unexpected supplement')
    supplement_frame = read_archive(supplement_dir, supplement)
    if not pd.DatetimeIndex(supplement_frame.ts).equals(missing_day):
        raise ValueError('supplement does not contain the exact missing day')
    data = pd.concat([data, supplement_frame], ignore_index=True).sort_values('ts').reset_index(drop=True)
    if not pd.DatetimeIndex(data.ts).equals(expected_index):
        raise ValueError('mark candles are missing, duplicated, out of order or outside window')
    prices = data[['open', 'high', 'low', 'close']].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError('invalid mark price')
    if ((data.high < data[['open', 'close', 'low']].max(axis=1)) |
        (data.low > data[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('invalid mark OHLC')
    return data


def compare(trades, last, mark):
    if not last.ts.equals(mark.ts):
        raise ValueError('price timestamp grids differ')
    index = pd.DatetimeIndex(last.ts)
    if not index.is_unique or not index.is_monotonic_increasing or len(index) < 1:
        raise ValueError('invalid price grid')
    if len(index) > 1 and not ((index[1:] - index[:-1]) == FREQ).all():
        raise ValueError('incomplete price grid')
    rows = []
    for trade in trades.itertuples(index=False):
        entry, exit_ = pd.Timestamp(trade.entry_ts), pd.Timestamp(trade.exit_ts)
        if entry.tz is None or exit_.tz is None or exit_ <= entry or entry not in index or exit_ > index[-1] + FREQ:
            raise ValueError('trade exposure outside price grid')
        a, b = index.searchsorted(entry), index.searchsorted(exit_)
        if exit_ != index[0] + b * FREQ or not np.isfinite(trade.stop) or trade.stop <= 0:
            raise ValueError('invalid exit time or stop')
        last_hit = np.flatnonzero(last.low.iloc[a:b].to_numpy() <= trade.stop)
        mark_hit = np.flatnonzero(mark.low.iloc[a:b].to_numpy() <= trade.stop)
        l = int(last_hit[0]) if len(last_hit) else None
        m = int(mark_hit[0]) if len(mark_hit) else None
        category = ('neither' if l is None and m is None else 'mark_only' if l is None else
                    'last_only' if m is None else 'same_bar' if l == m else
                    'mark_earlier' if m < l else 'last_earlier')
        if trade.reason == 'stop' and (l is None or index[a + l] + FREQ != exit_):
            raise ValueError('original stop does not match last-price history')
        rows.append({'trade_id': int(trade.trade_id), 'entry_ts': str(entry), 'exit_ts': str(exit_),
                     'reason': trade.reason, 'stop': float(trade.stop), 'category': category,
                     'last_first_bar': str(index[a + l]) if l is not None else None,
                     'mark_first_bar': str(index[a + m]) if m is not None else None,
                     'difference_minutes': int((m - l) * 5) if l is not None and m is not None else None})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mark-dir', required=True)
    parser.add_argument('--outdir', required=True)
    args = parser.parse_args()
    out = Path(args.outdir)
    if out.exists():
        raise ValueError('refusing to overwrite output')
    source = Path('data/verify/structural-stop-20261030-01')
    prior = json.loads((source / 'summary.json').read_text())
    for name, digest in prior['inputs'].items():
        if sha(Path(MARKET) / name) != digest:
            raise ValueError('original historical input hash changed')
    mark = load_mark(args.mark_dir)
    last = read_raw_candles('ETHUSDT')
    last = last.loc[(last.ts >= START) & (last.ts < END)].reset_index(drop=True)
    if not np.isfinite(last.low.to_numpy()).all() or (last.low <= 0).any():
        raise ValueError('invalid last-price lows')
    output = {}
    tables = {}
    for name in NAMES:
        ledger = source / f'combined_later_{name}_closed.csv'
        trades = pd.read_csv(ledger)
        details = compare(trades, last, mark)
        tables[name] = details
        output[name] = {'ledger_sha256': sha(ledger), 'trades': len(details),
                        'categories': {x: int((details.category == x).sum()) for x in
                                       ('mark_earlier', 'last_earlier', 'same_bar', 'mark_only', 'last_only', 'neither')},
                        'by_exit_reason': pd.crosstab(details.reason, details.category).to_dict(orient='index')}
    summary = {'status': 'EXPLORATORY_FIXED_EXPOSURES_NOT_PNL', 'start_utc': str(START),
               'end_exclusive_utc': str(END), 'bars': len(mark), 'results': output,
               'mark_manifest_sha256': sha(Path(args.mark_dir) / 'manifest.json'),
               'supplement_manifest_sha256': sha(Path(args.mark_dir) / 'supplement-20260629/manifest.json'),
               'supplement_definition_sha256': sha('docs/标记价止损核验-数据缺口补充方案-20261030.md'),
               'historical_summary_sha256': sha(source / 'summary.json'),
               'definition_sha256': sha('docs/标记价止损触发核验-事前定义-20261030.md'),
               'code_sha256': sha(__file__), 'historical_inputs': prior['inputs'],
               'limitations': ['The mark is a trigger reference, not an executable fill.',
                               'Same-bar ordering is unknown; no actual trade outcomes or PnL are inferred.',
                               'One-sided touch means within the original exposure only.',
                               'Historical sample was previously examined and is not independent OOS.']}
    out.mkdir(parents=True, exist_ok=False)
    for name, details in tables.items():
        details.to_csv(out / f'{name}_trade_comparison.csv', index=False)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
