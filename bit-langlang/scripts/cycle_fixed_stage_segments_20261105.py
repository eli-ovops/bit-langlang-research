import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixed = root / 'data/verify/cycle-fixed-quarter-review-20261105-01/daily.csv'
inputs = [root / 'data/verify/cycle-sentiment-2022q4-2023q4-20261105-01/segments-with-prior-funding.csv', root / 'data/verify/cycle-sentiment-2024q4-20261105-01/segments-with-prior-funding.csv']
out = root / 'data/verify/cycle-fixed-stage-segments-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    index = {(r['year'], r['source'], r['known_utc']): r for r in read(fixed)}
    rows = []
    for path in inputs:
        for s in read(path):
            year = s['start_utc'][:4]
            d = index[(year, s['source'], s['start_utc'])]
            assert float(s['prev_close']) == float(d['close'])
            price, upper, lower = float(d['close']), float(d['frozen_high']), float(d['frozen_low'])
            assert 0 < lower < upper and price > 0
            position = 'ABOVE' if price > upper else 'BELOW' if price < lower else 'INSIDE'
            assert position == d['position']
            rows.append({'year': year, 'source': s['source'], 'start_utc': s['start_utc'], 'end_utc_exclusive': s['end_utc_exclusive'], 'close': price, 'fixed_low': lower, 'fixed_high': upper, 'position': position, 'distance_from_fixed_high_pct': (price / upper - 1) * 100, 'long': s['long'], 'medium': s['big'], 'short': s['small'], 'funding_quality': s['funding_quality'], 'funding_count': s['funding_count'], 'funding_positive': s['funding_positive'], 'funding_negative': s['funding_negative'], 'funding_mean_pct_per_settlement': s['funding_mean_pct_per_settlement'], 'phase': 'UNKNOWN', 'actual_sentiment': 'UNKNOWN'})
    assert len(rows) == 84
    assert all(n == 14 for n in Counter((r['year'], r['source']) for r in rows).values())
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    manifest = {'input_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [fixed] + inputs}, 'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'rows': len(rows), 'scope': 'retrospective; phase and sentiment UNKNOWN'}
    (out / 'summary.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for year in ('2022', '2023', '2024'):
        subset = [r for r in rows if r['year'] == year and r['source'] == 'bitstamp']
        print(year, 'fixed', dict(Counter(r['position'] for r in subset)), 'above_short', dict(Counter(r['short'] for r in subset if r['position'] == 'ABOVE')))
    print('rows', len(rows))


if __name__ == '__main__':
    main()
