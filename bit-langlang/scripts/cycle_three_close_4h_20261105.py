import csv
import gzip
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
events = base/'cycle-three-close-context-20261105-01/context.csv'
out = base/'cycle-three-close-4h-20261105-01'


def raw_path(quarter, source):
    dirs = {'2023Q4': base/'cycle-2023q4-phase-20261104-01', '2024Q4': root/'data/market/btc-2024q4-usd-cross-20261104-01', '2025Q3': root/'data/market/btc-2025q3-usd-cross-20261104-01', '2025Q4': base/'cycle-btc-spot-2025q4-20261105-01', '2026Q1': base/'cycle-2026q1-phase-20261104-01'}
    suffix = '.csv.gz' if quarter in ('2024Q4', '2025Q3') else '.csv'
    return dirs[quarter]/f'{source}-4h{suffix}'


def read(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def main():
    results, used = [], {events}
    for event in read(events):
        r = {k: event[k] for k in ('quarter', 'source', 'three_close', 'comparison_utc', 'fixed_high', 'close_at_comparison', 'year_position_pct', 'funding_pos', 'funding_neg', 'after_7_pct', 'after_28_pct')}
        r.update({k: 'UNKNOWN' for k in ('recent_quality', 'prior_quality', 'close_above_count', 'recent_high', 'recent_low', 'close_vs_fixed_pct', 'close_vs_recent_high_pct', 'recent_to_prior_volume_ratio')})
        r['stage'] = r['sentiment'] = 'UNKNOWN'
        if not event['comparison_utc']:
            results.append(r); continue
        path = raw_path(event['quarter'], event['source']); used.add(path)
        raw = read(path); index = {int(x['ts']): x for x in raw}
        assert len(index) == len(raw)
        t = datetime.fromisoformat(event['comparison_utc'])
        def window(first, last):
            bars = [index.get(int((t-timedelta(hours=h)).timestamp()*1000)) for h in range(first, last-1, -4)]
            valid = len(bars) == 18 and all(x is not None and all(math.isfinite(float(x[k])) for k in ('open', 'high', 'low', 'close', 'volume')) and float(x['volume']) > 0 and 0 < float(x['low']) <= min(float(x['open']), float(x['close'])) <= max(float(x['open']), float(x['close'])) <= float(x['high']) for x in bars)
            return bars if valid else None
        recent, prior = window(72, 4), window(144, 76)
        if recent:
            close, high, low = float(recent[-1]['close']), max(float(x['high']) for x in recent), min(float(x['low']) for x in recent)
            upper = float(event['fixed_high'])
            assert math.isclose(close, float(event['close_at_comparison']), abs_tol=1e-8, rel_tol=0)
            r.update({'recent_quality': 'OK', 'close_above_count': sum(float(x['close']) > upper for x in recent), 'recent_high': high, 'recent_low': low, 'close_vs_fixed_pct': (close/upper-1)*100, 'close_vs_recent_high_pct': (close/high-1)*100})
        if prior:
            r['prior_quality'] = 'OK'
        if recent and prior:
            r['recent_to_prior_volume_ratio'] = sum(float(x['volume']) for x in recent)/sum(float(x['volume']) for x in prior)
        results.append(r)
    assert len(results) == 12
    out.mkdir(parents=True, exist_ok=True)
    target = out/'observations.csv'
    with target.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0]); writer.writeheader(); writer.writerows(results)
    used.add(target)
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(used)}, 'rows': len(results)}, indent=2)+'\n')
    for r in results:
        if r['source'] == 'bitstamp':
            print(r['quarter'], r['close_above_count'], r['close_vs_fixed_pct'], r['close_vs_recent_high_pct'], r['recent_to_prior_volume_ratio'], r['after_28_pct'])


if __name__ == '__main__':
    main()
