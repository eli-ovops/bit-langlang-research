import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
joined = root / 'data/verify/cycle-breadth-binance-archive-2025q4-20261105-01/btc-archive-year-asof-and-future.csv'
base = root / 'data/verify/cycle-btc-spot-2025q4-20261105-01'
out = root / 'data/verify/cycle-fixed-2025q4-20261105-01'


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
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    source_rows = read(joined)
    records, weeks, summaries = [], [], []
    paths = [joined]
    for source in ('bitstamp', 'kraken'):
        path = base / f'{source}-4h.csv'; paths.append(path)
        raw = read(path)
        candles = {int(r['ts']): r for r in raw}
        assert len(raw) == len(candles)
        by_time = {r['as_of_utc']: r for r in source_rows if r['btc_source'] == source}
        assert len(by_time) == 92
        first = by_time[start.isoformat()]
        assert first['range_status'] == 'OK'
        low, high = float(first['prior28_low']), float(first['prior28_high'])
        assert 0 < low < high
        counts, changes, previous, overlap_checked, overlap_missing = Counter(), [], None, 0, 0
        for i in range(93):
            t = start + timedelta(days=i); stamp = t.isoformat()
            rs = [candles.get(int((t - timedelta(hours=h)).timestamp()*1000)) for h in (24, 20, 16, 12, 8, 4)]
            valid = all(r is not None and all(math.isfinite(float(r[k])) for k in ('open', 'high', 'low', 'close', 'volume')) and float(r['volume']) > 0 and 0 < float(r['low']) <= min(float(r['open']), float(r['close'])) <= max(float(r['open']), float(r['close'])) <= float(r['high']) for r in rs)
            price = float(rs[-1]['close']) if valid else None
            if valid and i < 92:
                original = by_time[stamp]['prev_close']
                if original:
                    assert math.isclose(price, float(original), rel_tol=0, abs_tol=1e-8)
                    overlap_checked += 1
                else:
                    overlap_missing += 1
            state = position(price, low, high) if valid else 'UNKNOWN'
            if i: counts[state] += 1
            if previous is not None and state != previous:
                changes.append({'known_utc': stamp, 'from': previous, 'to': state, 'close': price})
            previous = state
            records.append({'source': source, 'known_utc': stamp, 'close': price, 'day_quality': 'OK' if valid else 'UNKNOWN', 'fixed_low': low, 'fixed_high': high, 'position': state})
            if i < 92 and i % 7 == 0:
                r = by_time[stamp]
                weeks.append({'source': source, 'start_utc': stamp, 'close': price, 'fixed_low': low, 'fixed_high': high, 'position': state, 'distance_from_fixed_high_pct': (price/high-1)*100 if valid else None, 'long': r['long'], 'medium': r['big'], 'short': r['small'], 'funding_quality': r['funding_quality'], 'funding_pos': r['funding_pos'], 'funding_neg': r['funding_neg'], 'funding_mean_pct': r['funding_mean_pct'], 'archive_known': r['archive_known'], 'archive_up7': r['archive_up7'], 'archive_up28': r['archive_up28'], 'phase': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
        assert sum(counts.values()) == 92
        summaries.append({'source': source, 'fixed_low': low, 'fixed_high': high, 'quarter_closes': dict(counts), 'overlap_checked': overlap_checked, 'valid_day_missing_original_close': overlap_missing, 'transitions': changes})
    assert len(records) == 186 and len(weeks) == 28
    out.mkdir(parents=True, exist_ok=True)
    save(out/'daily.csv', records); save(out/'segments.csv', weeks)
    paths.extend([out/'daily.csv', out/'segments.csv'])
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'sources': summaries}, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
