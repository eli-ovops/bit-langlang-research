import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
market = root/'data/market/BTCUSDT_1d.csv.gz'
official = base/'cycle-breadth-year-context-20261105-01/btc-api-daily.csv'
out = base/'cycle-rebound-full-quarters-20261105-01'
specs = {
    '2022Q4': ('cycle-fixed-quarter-review-20261105-01/daily.csv', 'cycle-2022q4-phase-20261104-01/daily.csv', 'cycle-sentiment-2022q4-2023q4-20261105-01/binance-2022-funding.json', '2022'),
    '2023Q4': ('cycle-fixed-quarter-review-20261105-01/daily.csv', 'cycle-2023q4-phase-20261104-01/daily.csv', 'cycle-sentiment-2022q4-2023q4-20261105-01/binance-2023-funding.json', '2023'),
    '2024Q4': ('cycle-fixed-quarter-review-20261105-01/daily.csv', 'cycle-2024q4-evidence-20261104-01/daily.csv', 'cycle-sentiment-2024q4-20261105-01/binance-2024-funding.json', '2024'),
    '2025Q3': ('cycle-fixed-2025q3-20261105-01/daily.csv', 'cycle-2025q3-continuous-20261104-01/daily.csv', 'cycle-sentiment-volume-2025q3-20261105-01/binance-2025-funding.json', None),
    '2025Q4': ('cycle-fixed-2025q4-20261105-01/daily.csv', 'cycle-breadth-binance-archive-2025q4-20261105-01/btc-archive-year-asof-and-future.csv', 'cycle-btc-spot-2025q4-20261105-01/funding.json', None),
    '2026Q1': ('cycle-fixed-2026q1-20261105-01/daily.csv', 'cycle-2026q1-phase-20261104-01/daily.csv', 'cycle-observed-2026q1-20261105-01/binance-funding.json', None),
}


def read(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def valid_bar(b):
    return b is not None and all(math.isfinite(float(b[k])) for k in ('open', 'high', 'low', 'close', 'volume')) and float(b['volume']) > 0 and 0 < float(b['low']) <= min(float(b['open']), float(b['close'])) <= max(float(b['open']), float(b['close'])) <= float(b['high'])


def main():
    local, api = read(market), read(official)
    market_index = {int(r['ts']): r for r in local}; api_index = {int(r['ts']): r for r in api}
    assert len(market_index) == len(local) and len(api_index) == len(api)
    used, results, summary = {market, official}, [], []
    for quarter, (fixed_name, context_name, fee_name, year) in specs.items():
        fixed_path, context_path, fee_path = base/fixed_name, base/context_name, base/fee_name
        used.update((fixed_path, context_path, fee_path))
        fixed = [r for r in read(fixed_path) if r['source'] == 'bitstamp' and (year is None or r['year'] == year)]
        fixed.sort(key=lambda r: r['known_utc'])
        expected_count = 91 if quarter == '2026Q1' else 93
        assert len(fixed) == expected_count
        ctx = {r['as_of_utc']: r for r in read(context_path) if r.get('source', r.get('btc_source')) == 'bitstamp'}
        fees = json.loads(fee_path.read_text())
        quarter_rows = []
        for i, row in enumerate(fixed[:-1]):
            t = datetime.fromisoformat(row['known_utc'])
            assert datetime.fromisoformat(fixed[i+1]['known_utc'])-t == timedelta(days=1)
            p = ctx[t.isoformat()]
            expected = [int((t-timedelta(days=n)).timestamp()*1000) for n in range(91, 0, -1)]
            bars = [market_index.get(ts) for ts in expected]
            status, change7, change90, origin = 'UNKNOWN', '', '', 'UNKNOWN'
            if all(valid_bar(b) for b in bars):
                shared = [api_index.get(ts) for ts in expected]
                conflict = any(a is not None and any(Decimal(a[k]) != Decimal(b[k]) for k in ('open', 'high', 'low', 'close', 'volume')) for a, b in zip(shared, bars))
                origin = 'CONFLICT' if conflict else 'API_OVERLAP' if all(shared) else 'LOCAL_PARTIAL'
                if not conflict:
                    last = float(bars[-1]['close'])
                    change7 = 100*(last/float(bars[-8]['close'])-1)
                    change90 = 100*(last/float(bars[-91]['close'])-1)
                    status = 'YES' if change90 < 0 and change7 > 0 else 'NO'
            start_ms, end_ms = int((t-timedelta(days=7)).timestamp()*1000), int(t.timestamp()*1000)
            selected = [x for x in fees if start_ms <= int(x['fundingTime']) < end_ms]
            slots = [round((int(x['fundingTime'])-start_ms)/28800000) for x in selected]
            fee_quality, pos, neg = 'UNKNOWN', '', ''
            if len(selected) == 21 and sorted(slots) == list(range(21)) and all(abs(int(x['fundingTime'])-(start_ms+s*28800000))<=60000 and math.isfinite(float(x['fundingRate'])) for x,s in zip(selected, slots)):
                fee_quality = 'OK'; pos = sum(float(x['fundingRate'])>0 for x in selected); neg = sum(float(x['fundingRate'])<0 for x in selected)
            future, future_status = '', 'UNKNOWN'
            if i+28 < len(fixed) and all(fixed[j]['position'] != 'UNKNOWN' and fixed[j]['close'] for j in range(i, i+29)):
                future = 100*(float(fixed[i+28]['close'])/float(row['close'])-1); future_status = 'OK'
            result = {'quarter': quarter, 'as_of_utc': t.isoformat(), 'spot_close': row['close'], 'fixed_position': row['position'], 'long': p['long'], 'medium': p['big'], 'short': p['small'], 'past7_pct': change7, 'past90_pct': change90, 'prior_quality': origin, 'condition': status, 'funding_quality': fee_quality, 'funding_pos': pos, 'funding_neg': neg, 'future28_quality': future_status, 'future28_pct': future, 'stage': 'UNKNOWN', 'sentiment': 'UNKNOWN'}
            results.append(result); quarter_rows.append(result)
        assert len(quarter_rows) == expected_count-1
        selected = [r for r in quarter_rows if r['condition'] == 'YES']
        runs = sum(i == 0 or quarter_rows[i-1]['condition'] != 'YES' for i,r in enumerate(quarter_rows) if r['condition'] == 'YES')
        for location in ('BELOW', 'INSIDE', 'ABOVE', 'UNKNOWN'):
            group = [r for r in selected if r['fixed_position'] == location]
            futures = [float(r['future28_pct']) for r in group if r['future28_quality'] == 'OK']
            summary.append({'quarter': quarter, 'location': location, 'condition_days': len(group), 'future_known': len(futures), 'future_unknown': len(group)-len(futures), 'positive': sum(v>0 for v in futures), 'negative': sum(v<0 for v in futures), 'zero': sum(v==0 for v in futures), 'min_future_pct': min(futures) if futures else None, 'max_future_pct': max(futures) if futures else None, 'quarter_condition_runs': runs})
    assert len(results) == 550 and len(summary) == 24
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (('daily.csv', results), ('groups.csv', summary)):
        path = out/name
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
        used.add(path)
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(used)}, 'rows': len(results), 'condition': dict(Counter(r['condition'] for r in results)), 'quality': dict(Counter(r['prior_quality'] for r in results))}, indent=2)+'\n')
    for r in summary:
        if r['condition_days']:
            print(r)
    print('all', len(results), Counter(r['condition'] for r in results), Counter(r['prior_quality'] for r in results))


if __name__ == '__main__':
    main()
