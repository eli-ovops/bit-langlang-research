import csv
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
context = base/'cycle-three-close-context-20261105-01/context.csv'
local = base/'cycle-three-close-4h-20261105-01/observations.csv'
annual = base/'cycle-breadth-year-context-20261105-01/btc-api-daily.csv'
out = base/'cycle-event-prior-path-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    inputs = read(context); local_rows = read(local); raw = read(annual)
    local_idx = {(r['quarter'], r['source']): r for r in local_rows}
    bars_idx = {int(r['ts']): r for r in raw}
    assert len(local_idx) == len(inputs) == 12 and len(bars_idx) == len(raw)
    results = []
    for r in inputs:
        local_row = local_idx[(r['quarter'], r['source'])]
        assert local_row['comparison_utc'] == r['comparison_utc']
        row = {k: r[k] for k in ('quarter', 'source', 'three_close', 'comparison_utc', 'fixed_high', 'close_at_comparison', 'year_position_pct', 'year_distance_from_high_pct', 'funding_pos', 'funding_neg', 'after_7_pct', 'after_28_pct')}
        row.update({k: local_row[k] for k in ('close_above_count', 'close_vs_recent_high_pct', 'recent_to_prior_volume_ratio')})
        row.update({k: 'UNKNOWN' for k in ('prior_quality', 'year_high_known_utc', 'days_since_year_high', 'past_7_pct', 'past_28_pct', 'past_90_pct')})
        row['stage'] = row['sentiment'] = 'UNKNOWN'
        if r['comparison_utc']:
            t = datetime.fromisoformat(r['comparison_utc'])
            expected = [int((t-timedelta(days=i)).timestamp()*1000) for i in range(365, 0, -1)]
            bars = [bars_idx.get(ts) for ts in expected]
            valid = all(b is not None and all(math.isfinite(float(b[k])) for k in ('open','high','low','close','volume')) and float(b['volume']) > 0 and 0 < float(b['low']) <= min(float(b['open']), float(b['close'])) <= max(float(b['open']), float(b['close'])) <= float(b['high']) for b in bars)
            if valid:
                high = max(float(b['high']) for b in bars)
                pos = max(i for i, b in enumerate(bars) if float(b['high']) == high)
                high_known = datetime.fromtimestamp(int(bars[pos]['ts'])/1000, tz=t.tzinfo) + timedelta(days=1)
                assert high_known <= t and math.isclose(high, float(r['year_high']), abs_tol=1e-8, rel_tol=0)
                last = float(bars[-1]['close'])
                row.update({'prior_quality': 'OK', 'year_high_known_utc': high_known.isoformat(), 'days_since_year_high': (t-high_known).days})
                for n in (7, 28, 90):
                    row[f'past_{n}_pct'] = (last/float(bars[-n-1]['close'])-1)*100
        results.append(row)
    out.mkdir(parents=True, exist_ok=True)
    path = out/'comparison.csv'
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=results[0]); w.writeheader(); w.writerows(results)
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (context, local, annual, path)}, 'rows': len(results)}, indent=2)+'\n')
    for r in results:
        if r['source'] == 'bitstamp':
            print(r['quarter'], r['comparison_utc'], r['days_since_year_high'], r['past_7_pct'], r['past_28_pct'], r['past_90_pct'], r['year_distance_from_high_pct'], r['after_28_pct'])


if __name__ == '__main__':
    main()
