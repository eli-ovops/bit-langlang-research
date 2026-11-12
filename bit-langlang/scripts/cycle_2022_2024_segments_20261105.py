import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
inputs = {
    'fixed': base/'cycle-fixed-quarter-review-20261105-01/daily.csv',
    'daily': base/'cycle-rebound-full-quarters-20261105-01/daily.csv',
    '2022': base/'cycle-sentiment-2022q4-2023q4-20261105-01/segments-with-prior-funding.csv',
    '2024': base/'cycle-sentiment-2024q4-20261105-01/segments-with-prior-funding.csv',
}
out = base/'cycle-2022-2024-segments-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    source = {k: read(p) for k, p in inputs.items()}
    rows = []
    for year in (2022, 2024):
        start = datetime(year, 10, 1, tzinfo=timezone.utc)
        end = datetime(year+1, 1, 1, tzinfo=timezone.utc)
        segment = {r['start_utc']: r for r in source[str(year)] if r['source'] == 'bitstamp' and r['start_utc'].startswith(str(year))}
        fixed = {r['known_utc']: r for r in source['fixed'] if r['source'] == 'bitstamp' and r['year'] == str(year)}
        daily = {r['as_of_utc']: r for r in source['daily'] if r['quarter'] == f'{year}Q4'}
        for i in range(14):
            t = start+timedelta(days=7*i); key = t.isoformat()
            s, f, d = segment[key], fixed[key], daily[key]
            assert s['range_status'] == 'OK' and s['funding_quality'] == d['funding_quality'] == 'OK'
            assert s['funding_positive'] == d['funding_pos'] and s['funding_negative'] == d['funding_neg']
            assert float(s['prev_close']) == float(f['close']) == float(d['spot_close'])
            price, lo, hi = float(f['close']), float(f['frozen_low']), float(f['frozen_high'])
            assert 0 < lo < hi and f['position'] == d['fixed_position'] == ('ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE')
            assert all(math.isfinite(float(d[k])) for k in ('past7_pct', 'past90_pct'))
            assert (s['long'], s['big'], s['small']) == (d['long'], d['medium'], d['short'])
            rows.append({'quarter': f'{year}Q4', 'start_utc': key, 'end_utc_exclusive': min(t+timedelta(days=7), end).isoformat(), 'source': 'bitstamp', 'close': price, 'fixed_low': lo, 'fixed_high': hi, 'fixed_position': f['position'], 'recent28_low': s['prior28_low'], 'recent28_high': s['prior28_high'], 'long': s['long'], 'medium': s['big'], 'short': s['small'], 'past7_futures_pct': d['past7_pct'], 'past90_futures_pct': d['past90_pct'], 'past_quality': d['prior_quality'], 'funding_pos': d['funding_pos'], 'funding_neg': d['funding_neg'], 'stage': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
    assert len(rows) == 28
    out.mkdir(parents=True, exist_ok=True)
    target = out/'asof-segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    paths = list(inputs.values()) + [target]
    (out/'summary.json').write_text(json.dumps({'rows': len(rows), 'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}, indent=2)+'\n')
    for r in rows:
        print(r['quarter'], r['start_utc'][:10], r['close'], r['fixed_position'], r['long'], r['medium'], r['short'], round(float(r['past7_futures_pct']), 1), round(float(r['past90_futures_pct']), 1), str(r['funding_pos'])+'/'+str(r['funding_neg']))


if __name__ == '__main__':
    main()
