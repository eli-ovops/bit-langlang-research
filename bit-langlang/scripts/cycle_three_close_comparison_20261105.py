import csv
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
specs = [('2022Q4', 'cycle-fixed-quarter-review-20261105-01', '2022'), ('2023Q4', 'cycle-fixed-quarter-review-20261105-01', '2023'), ('2024Q4', 'cycle-fixed-quarter-review-20261105-01', '2024'), ('2025Q3', 'cycle-fixed-2025q3-20261105-01', None), ('2025Q4', 'cycle-fixed-2025q4-20261105-01', None), ('2026Q1', 'cycle-fixed-2026q1-20261105-01', None)]
out = root/'data/verify/cycle-three-close-comparison-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    result, inputs = [], set()
    for quarter, folder, year in specs:
        path = root/'data/verify'/folder/'daily.csv'; inputs.add(path)
        data = read(path)
        if year:
            data = [r for r in data if r['year'] == year]
        for source in sorted({r['source'] for r in data}):
            rows = sorted([r for r in data if r['source'] == source], key=lambda r: r['known_utc'])
            lo_key = 'fixed_low' if 'fixed_low' in rows[0] else 'frozen_low'
            hi_key = 'fixed_high' if 'fixed_high' in rows[0] else 'frozen_high'
            assert len(rows) in (91, 93) and len({(r[lo_key], r[hi_key]) for r in rows}) == 1
            for prev, cur in zip(rows, rows[1:]):
                assert datetime.fromisoformat(cur['known_utc']) - datetime.fromisoformat(prev['known_utc']) == timedelta(days=1)
            entry = {'quarter': quarter, 'source': source, 'cross_known_utc': '', 'comparison_utc': '', 'fixed_high': rows[0][hi_key], 'three_close': '', 'close_at_comparison': '', 'after_7_pct': '', 'after_28_pct': '', 'phase': 'UNKNOWN'}
            event, uncertain = None, rows[0]['position'] in ('ABOVE', 'UNKNOWN')
            for i in range(1, len(rows)):
                if rows[i-1]['position'] == 'UNKNOWN': uncertain = True
                if rows[i]['position'] == 'ABOVE' and rows[i-1]['position'] in ('INSIDE', 'BELOW'):
                    event = i; break
            if uncertain or (event is None and any(r['position'] == 'UNKNOWN' for r in rows)):
                entry['three_close'] = 'UNKNOWN'
            elif event is None:
                entry['three_close'] = 'NO_CROSS'
            else:
                entry['cross_known_utc'] = rows[event]['known_utc']
                if event+2 >= len(rows) or any(r['position'] == 'UNKNOWN' for r in rows[event:event+3]):
                    entry['three_close'] = 'UNKNOWN'
                else:
                    i = event+2; entry['comparison_utc'] = rows[i]['known_utc']
                    entry['three_close'] = 'ALL_ABOVE' if all(r['position'] == 'ABOVE' for r in rows[event:i+1]) else 'NOT_ALL_ABOVE'
                    price = float(rows[i]['close']); entry['close_at_comparison'] = price
                    for n in (7, 28):
                        if i+n < len(rows) and all(r['position'] != 'UNKNOWN' and r['close'] for r in rows[i:i+n+1]):
                            entry[f'after_{n}_pct'] = (float(rows[i+n]['close'])/price-1)*100
            result.append(entry)
    assert len(result) == 12
    out.mkdir(parents=True, exist_ok=True)
    target = out/'comparison.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=result[0]); w.writeheader(); w.writerows(result)
    paths = sorted(inputs) + [target]
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'rows': len(result)}, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
