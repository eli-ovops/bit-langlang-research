import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
daily_path = root / 'data/verify/cycle-2025q3-continuous-20261104-01/daily.csv'
segment_path = root / 'data/verify/cycle-sentiment-volume-2025q3-20261105-01/segments-price-funding-volume.csv'
out = root / 'data/verify/cycle-fixed-2025q3-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def save(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)


def state(price, lo, hi):
    return 'ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE'


def main():
    assert [state(p, 10, 20) for p in (9, 10, 20, 21)] == ['BELOW', 'INSIDE', 'INSIDE', 'ABOVE']
    daily, segments = read(daily_path), read(segment_path)
    assert len(daily) == 184 and len(segments) == 28
    out.mkdir(parents=True, exist_ok=True)
    records, weeks, summaries = [], [], []
    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    for source in ('bitstamp', 'bitfinex'):
        ds = sorted([r for r in daily if r['source'] == source], key=lambda r: r['as_of_utc'])
        ss = sorted([r for r in segments if r['source'] == source], key=lambda r: r['start_utc'])
        assert len(ds) == 92 and len(ss) == 14
        for i, r in enumerate(ds):
            assert datetime.fromisoformat(r['as_of_utc']) == start + timedelta(days=i)
        assert ss[-1]['status'] == 'COMPLETE' and ss[-1]['start_utc'].startswith('2025-09-30') and ss[-1]['end_utc_exclusive'].startswith('2025-10-01')
        lo, hi = float(ds[0]['prior28_low']), float(ds[0]['prior28_high'])
        assert 0 < lo < hi and ds[0]['range_status'] == 'OK'
        prices = [(r['as_of_utc'], float(r['prev_close'])) for r in ds] + [((start + timedelta(days=92)).isoformat(), float(ss[-1]['last_close']))]
        positions, transitions = [], []
        for t, p in prices:
            assert p > 0
            s = state(p, lo, hi)
            if positions and positions[-1] != s:
                transitions.append({'known_utc': t, 'from': positions[-1], 'to': s, 'close': p})
            positions.append(s)
            records.append({'source': source, 'known_utc': t, 'close': p, 'fixed_low': lo, 'fixed_high': hi, 'position': s})
        index = {r['as_of_utc']: r for r in ds}
        for i, r in enumerate(ss):
            assert datetime.fromisoformat(r['start_utc']) == start + timedelta(days=7*i)
            d = index[r['start_utc']]
            assert float(r['prev_close']) == float(d['prev_close'])
            p = float(r['prev_close'])
            weeks.append({'source': source, 'start_utc': r['start_utc'], 'end_utc_exclusive': r['end_utc_exclusive'], 'close': p, 'fixed_low': lo, 'fixed_high': hi, 'position': state(p, lo, hi), 'distance_from_fixed_high_pct': (p/hi-1)*100, 'long': r['long'], 'medium': r['big'], 'short': r['small'], 'funding_quality': r['funding_quality'], 'funding_positive': r['funding_positive'], 'funding_negative': r['funding_negative'], 'funding_count': r['funding_count'], 'funding_mean_pct_per_settlement': r['funding_mean_pct_per_settlement'], 'spot_volume_quality': r['spot_volume_quality'], 'spot_recent7_to_prior21_daily_volume': r['spot_recent7_to_prior21_daily_volume'], 'phase': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
        summaries.append({'source': source, 'low': lo, 'high': hi, 'quarter_closes': dict(Counter(positions[1:])), 'transitions': transitions})
    assert len(records) == 186 and len(weeks) == 28
    save(out / 'daily.csv', records); save(out / 'segments.csv', weeks)
    files = (daily_path, segment_path, out/'daily.csv', out/'segments.csv')
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, 'sources': summaries}, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
