import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / 'data/verify/cycle-2026q1-phase-20261104-01'
observed = root / 'data/verify/cycle-observed-2026q1-20261105-01/daily-observations.csv'
out = root / 'data/verify/cycle-fixed-2026q1-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def save(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)


def position(price, low, high):
    return 'ABOVE' if price > high else 'BELOW' if price < low else 'INSIDE'


def main():
    assert [position(p, 10, 20) for p in (9, 10, 20, 21)] == ['BELOW', 'INSIDE', 'INSIDE', 'ABOVE']
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    daily, obs = read(base/'daily.csv'), read(observed)
    paths = [base/'daily.csv', observed]
    records, weeks, summaries = [], [], []
    for source in ('bitstamp', 'kraken'):
        path = base/f'{source}-4h.csv'; paths.append(path)
        raw = read(path); candles = {int(r['ts']): r for r in raw}
        assert len(candles) == len(raw)
        by_day = {r['as_of_utc']: r for r in daily if r['source'] == source}
        by_obs = {r['as_of_utc']: r for r in obs if r['source'] == source}
        assert len(by_day) == len(by_obs) == 90
        ref = by_day[start.isoformat()]; assert ref['range_status'] == 'OK'
        low, high = float(ref['prior28_low']), float(ref['prior28_high'])
        assert 0 < low < high
        counts, changes, previous = Counter(), [], None
        for i in range(91):
            t = start + timedelta(days=i); stamp = t.isoformat()
            bars = [candles.get(int((t-timedelta(hours=h)).timestamp()*1000)) for h in (24, 20, 16, 12, 8, 4)]
            valid = all(r is not None and all(math.isfinite(float(r[k])) for k in ('open', 'high', 'low', 'close', 'volume')) and float(r['volume']) > 0 and 0 < float(r['low']) <= min(float(r['open']), float(r['close'])) <= max(float(r['open']), float(r['close'])) <= float(r['high']) for r in bars)
            price = float(bars[-1]['close']) if valid else None
            if valid and i < 90:
                assert math.isclose(price, float(by_day[stamp]['prev_close']), abs_tol=1e-8, rel_tol=0)
                assert math.isclose(price, float(by_obs[stamp]['prev_close']), abs_tol=1e-8, rel_tol=0)
            state = position(price, low, high) if valid else 'UNKNOWN'
            if i: counts[state] += 1
            if previous is not None and state != previous:
                changes.append({'known_utc': stamp, 'from': previous, 'to': state, 'close': price})
            previous = state
            records.append({'source': source, 'known_utc': stamp, 'close': price, 'quality': 'OK' if valid else 'UNKNOWN', 'fixed_low': low, 'fixed_high': high, 'position': state})
            if i < 90 and i % 7 == 0:
                r = by_obs[stamp]
                weeks.append({'source': source, 'known_utc': stamp, 'close': price, 'fixed_low': low, 'fixed_high': high, 'fixed_position': state, 'distance_from_fixed_high_pct': (price/high-1)*100 if valid else None, 'long': r['long56'], 'medium': r['mid28'], 'short': r['short8'], 'prior_rolling_low': r['baseline_old28_low'], 'prior_rolling_high': r['baseline_old28_high'], 'rolling_state': r['observed_state'], 'funding_quality': r['funding_quality'], 'funding_pos': r['funding_pos'], 'funding_neg': r['funding_neg'], 'funding_mean_pct': r['funding_mean_pct_per_event'], 'volume_quality': r['volume_quality'], 'volume_ratio': r['volume_recent7_to_prev21'], 'phase': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
        assert sum(counts.values()) == 90
        summaries.append({'source': source, 'fixed_low': low, 'fixed_high': high, 'quarter_closes': dict(counts), 'transitions': changes})
    assert len(records) == 182 and len(weeks) == 26
    out.mkdir(parents=True, exist_ok=True)
    save(out/'daily.csv', records); save(out/'segments.csv', weeks)
    paths.extend([out/'daily.csv', out/'segments.csv'])
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'sources': summaries}, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
