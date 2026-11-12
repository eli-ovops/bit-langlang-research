import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
files = {'2023_segments': base/'cycle-sentiment-2022q4-2023q4-20261105-01/segments-with-prior-funding.csv', '2023_fixed': base/'cycle-fixed-quarter-review-20261105-01/daily.csv', '2025_daily': base/'cycle-breadth-binance-archive-2025q4-20261105-01/btc-archive-year-asof-and-future.csv', '2025_fixed': base/'cycle-fixed-2025q4-20261105-01/daily.csv'}
out = base/'cycle-two-regime-segments-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    data = {k: read(p) for k, p in files.items()}
    result = []
    for year in (2023, 2025):
        start = datetime(year, 10, 1, tzinfo=timezone.utc)
        end = datetime(year+1, 1, 1, tzinfo=timezone.utc)
        if year == 2023:
            source = {r['start_utc']: r for r in data['2023_segments'] if r['source'] == 'bitstamp' and r['start_utc'].startswith('2023-')}
            fixed = {r['known_utc']: r for r in data['2023_fixed'] if r['source'] == 'bitstamp' and r['year'] == '2023'}
        else:
            source = {r['as_of_utc']: r for r in data['2025_daily'] if r['btc_source'] == 'bitstamp'}
            fixed = {r['known_utc']: r for r in data['2025_fixed'] if r['source'] == 'bitstamp'}
        for i in range(14):
            t = start + timedelta(days=7*i); s = source[t.isoformat()]; f = fixed[t.isoformat()]
            assert s['range_status'] == 'OK' and s['funding_quality'] == 'OK'
            assert float(s['prev_close']) == float(f['close'])
            price = float(f['close']); lo = float(f.get('fixed_low') or f['frozen_low']); hi = float(f.get('fixed_high') or f['frozen_high'])
            assert 0 < lo < hi and f['position'] == ('ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE')
            long, short = s['long'], s['small']
            conflict = 'YES' if (long, short) in (('UP', 'DOWN'), ('DOWN', 'UP')) else 'UNKNOWN' if 'UNKNOWN' in (long, short) else 'NO_DIRECT_OPPOSITION'
            result.append({'quarter': f'{year}Q4', 'start_utc': t.isoformat(), 'end_utc_exclusive': min(t+timedelta(days=7), end).isoformat(), 'source': 'bitstamp', 'close': price, 'fixed_low': lo, 'fixed_high': hi, 'fixed_position': f['position'], 'recent28_low': s['prior28_low'], 'recent28_high': s['prior28_high'], 'long': long, 'medium': s['big'], 'short': short, 'direct_long_short_opposition': conflict, 'funding_quality': s['funding_quality'], 'funding_pos': s.get('funding_positive', s.get('funding_pos')), 'funding_neg': s.get('funding_negative', s.get('funding_neg')), 'stage': 'UNKNOWN', 'true_sentiment': 'UNKNOWN'})
    assert len(result) == 28
    out.mkdir(parents=True, exist_ok=True)
    target = out/'asof-segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=result[0]); w.writeheader(); w.writerows(result)
    paths = list(files.values()) + [target]
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'rows': len(result)}, indent=2)+'\n')
    for r in result:
        print(r['quarter'], r['start_utc'][:10], r['close'], r['fixed_position'], r['recent28_low'], r['recent28_high'], r['long'], r['medium'], r['short'], str(r['funding_pos'])+'/'+str(r['funding_neg']))


if __name__ == '__main__':
    main()
