"""Offline diagnostic only; never reads accounts or emits orders."""
import csv
import datetime as dt
import decimal
import gzip
import hashlib
import json
from pathlib import Path

D = 86400000
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/market/BTCUSDT_1d.csv.gz'
BASELINE = ROOT / 'data/verify/langlang-paper-market-audit-20261110-01/t0.csv'
OUT = ROOT / 'data/verify/langlang-paper-pullback-v02-audit-20261110-01'
Decimal = decimal.Decimal


def decision(bars):
    """Input exactly 35 validated daily bars, strictly before the observation."""
    breaks = []
    for i in range(28, 35):
        level = max(bar['high'] for bar in bars[i-28:i])
        if bars[i]['close'] > level:
            breaks.append((i, level))
    if not breaks:
        return 'NO_CANDIDATE', 'NO_BREAK', None, None, None
    i, level = breaks[-1]
    if bars[-1]['close'] <= level or max(x['high'] for x in bars[-7:]) <= bars[-1]['close']:
        return 'NO_CANDIDATE', 'V01_FILTER', i, level, None
    if i == 34:
        return 'NO_CANDIDATE', 'NO_POST_BREAK_DAY', i, level, None
    for j in range(i+1, 35):
        if bars[j]['low'] < bars[i]['close']:
            return 'CANDIDATE', 'POST_BREAK_DECLINE', i, level, j
    return 'NO_CANDIDATE', 'NO_POST_BREAK_DECLINE', i, level, None


def self_test():
    base = [{'high': Decimal(100), 'low': Decimal(90), 'close': Decimal(95)} for _ in range(35)]
    assert decision(base)[1] == 'NO_BREAK'
    last = [x.copy() for x in base]
    last[34] = {'high': Decimal(110), 'low': Decimal(99), 'close': Decimal(105)}
    assert decision(last)[1] == 'NO_POST_BREAK_DAY'
    pull = [x.copy() for x in base]
    pull[33] = {'high': Decimal(110), 'low': Decimal(99), 'close': Decimal(105)}
    pull[34] = {'high': Decimal(108), 'low': Decimal(103), 'close': Decimal(104)}
    assert decision(pull)[:2] == ('CANDIDATE', 'POST_BREAK_DECLINE')
    flat = [x.copy() for x in pull]
    flat[34] = {'high': Decimal(108), 'low': Decimal(105), 'close': Decimal(106)}
    assert decision(flat)[1] == 'NO_POST_BREAK_DECLINE'
    inside = [x.copy() for x in pull]
    inside[34]['close'] = Decimal(99)
    inside[34]['low'] = Decimal(98)
    assert decision(inside)[1] == 'V01_FILTER'
    reset = [x.copy() for x in pull]
    reset[34] = {'high': Decimal(115), 'low': Decimal(103), 'close': Decimal(112)}
    assert decision(reset)[1] == 'NO_POST_BREAK_DAY'


def main():
    self_test()
    with gzip.open(SOURCE, 'rt', newline='') as f:
        rows = list(csv.DictReader(f))
    table = {}
    for row in rows:
        stamp = int(row['ts'])
        if stamp in table:
            raise ValueError('duplicate timestamp')
        table[stamp] = row
    with BASELINE.open(newline='') as f:
        baseline = list(csv.DictReader(f))
    result = []
    for old in baseline:
        t = int(dt.datetime.fromisoformat(old['as_of_utc']).timestamp()*1000)
        bars = []
        for stamp in range(t-35*D, t, D):
            row = table.get(stamp)
            if not row:
                break
            op, high, low, close, volume = map(Decimal, (row['open'], row['high'], row['low'], row['close'], row['volume']))
            if stamp % D or not (0 < low <= min(op, close) <= max(op, close) <= high and volume > 0):
                break
            bars.append({'high': high, 'low': low, 'close': close})
        if len(bars) != 35:
            entry = {'as_of_utc': old['as_of_utc'], 'v01': old['status'], 'v02': 'UNKNOWN', 'reason': 'DATA_INVALID'}
        else:
            status, reason, i, level, j = decision(bars)
            def day(index):
                return dt.datetime.fromtimestamp((t-(35-index)*D)/1000, dt.timezone.utc).date().isoformat() if index is not None else ''
            entry = {'as_of_utc': old['as_of_utc'], 'v01': old['status'], 'v02': status, 'reason': reason,
                     'break_date_utc': day(i), 'B': str(level) if level is not None else '', 'decline_date_utc': day(j)}
            if status == 'CANDIDATE':
                assert old['status'] == 'CANDIDATE' and i < j < 35
        result.append(entry)
    target = OUT / 't0-v02.csv'
    with target.open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['as_of_utc','v01','v02','reason','break_date_utc','B','decline_date_utc'])
        w.writeheader()
        w.writerows(result)
    counts = {}
    for row in result:
        counts[row['reason']] = counts.get(row['reason'], 0) + 1
    manifest = {'rows': len(result), 'counts': counts, 't0_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'baseline_sha256': hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
                'protocol_sha256': hashlib.sha256((OUT / '口径.md').read_bytes()).hexdigest(),
                'self_test': 'PASS: no breakout, breakout today, later decline, no later decline, inside, new breakout resets',
                'future_outcomes_in_t0': False}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
