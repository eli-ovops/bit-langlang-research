import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
events = base/'cycle-three-close-comparison-20261105-01/comparison.csv'
annual = base/'cycle-breadth-year-context-20261105-01/btc-api-daily.csv'
inputs = {
    '2023Q4': ('cycle-2023q4-phase-20261104-01/daily.csv', 'cycle-sentiment-2022q4-2023q4-20261105-01/binance-2023-funding.json'),
    '2024Q4': ('cycle-2024q4-evidence-20261104-01/daily.csv', 'cycle-sentiment-2024q4-20261105-01/binance-2024-funding.json'),
    '2025Q3': ('cycle-2025q3-continuous-20261104-01/daily.csv', 'cycle-sentiment-volume-2025q3-20261105-01/binance-2025-funding.json'),
    '2025Q4': ('cycle-breadth-binance-archive-2025q4-20261105-01/btc-archive-year-asof-and-future.csv', 'cycle-btc-spot-2025q4-20261105-01/funding.json'),
    '2026Q1': ('cycle-2026q1-phase-20261104-01/daily.csv', 'cycle-observed-2026q1-20261105-01/binance-funding.json'),
}
out = base/'cycle-three-close-context-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    year_data = read(annual)
    by_date = {int(r['ts']): r for r in year_data}
    assert len(by_date) == len(year_data)
    used, records = {events, annual}, []
    for e in read(events):
        result = {k: e[k] for k in ('quarter', 'source', 'three_close', 'comparison_utc', 'fixed_high', 'close_at_comparison', 'after_7_pct', 'after_28_pct')}
        for key in ('long', 'medium', 'short', 'spot_prior28_low', 'spot_prior28_high', 'year_quality', 'year_low', 'year_high', 'year_close', 'year_position_pct', 'year_distance_from_high_pct', 'funding_quality', 'funding_pos', 'funding_neg', 'funding_mean_pct'):
            result[key] = 'UNKNOWN'
        result['stage'] = result['sentiment'] = 'UNKNOWN'
        if not e['comparison_utc']:
            records.append(result); continue
        dp, fp = (base/p for p in inputs[e['quarter']]); used.update((dp, fp))
        source, t = e['source'], datetime.fromisoformat(e['comparison_utc'])
        spot = [r for r in read(dp) if r.get('source', r.get('btc_source')) == source and r['as_of_utc'] == t.isoformat()]
        assert len(spot) == 1
        s = spot[0]
        if s['prev_close'] and s['range_status'] == 'OK':
            assert math.isclose(float(s['prev_close']), float(e['close_at_comparison']), abs_tol=1e-8, rel_tol=0)
            result.update({'long': s['long'], 'medium': s['big'], 'short': s['small'], 'spot_prior28_low': s['prior28_low'], 'spot_prior28_high': s['prior28_high']})
        expected = [int((t-timedelta(days=n)).timestamp()*1000) for n in range(365, 0, -1)]
        bars = [by_date.get(ms) for ms in expected]
        if all(r is not None and all(math.isfinite(float(r[k])) for k in ('open','high','low','close','volume')) and float(r['volume']) > 0 and 0 < float(r['low']) <= min(float(r['open']), float(r['close'])) <= max(float(r['open']), float(r['close'])) <= float(r['high']) for r in bars):
            low, high, close = min(float(r['low']) for r in bars), max(float(r['high']) for r in bars), float(bars[-1]['close'])
            if high > low:
                result.update({'year_quality': 'OK', 'year_low': low, 'year_high': high, 'year_close': close, 'year_position_pct': (close-low)/(high-low)*100, 'year_distance_from_high_pct': (close/high-1)*100})
        raw = json.loads(fp.read_text())
        begin_ms, end_ms = int((t-timedelta(days=7)).timestamp()*1000), int(t.timestamp()*1000)
        rates = [r for r in raw if begin_ms <= int(r['fundingTime']) < end_ms]
        slots = [round((int(r['fundingTime'])-begin_ms)/28800000) for r in rates]
        if len(rates) == 21 and sorted(slots) == list(range(21)) and all(abs(int(r['fundingTime'])-(begin_ms+slot*28800000)) <= 60000 and math.isfinite(float(r['fundingRate'])) for r, slot in zip(rates, slots)):
            nums = [float(r['fundingRate']) for r in rates]
            result.update({'funding_quality': 'OK', 'funding_pos': sum(x>0 for x in nums), 'funding_neg': sum(x<0 for x in nums), 'funding_mean_pct': sum(nums)/len(nums)*100})
        records.append(result)
    assert len(records) == 12
    out.mkdir(parents=True, exist_ok=True)
    target = out/'context.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=records[0]); w.writeheader(); w.writerows(records)
    used.add(target)
    (out/'summary.json').write_text(json.dumps({'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(used)}, 'rows': len(records)}, indent=2)+'\n')
    for r in records:
        if r['source'] == 'bitstamp':
            print(r['quarter'], r['comparison_utc'], r['long'], r['medium'], r['short'], r['year_quality'], r['year_position_pct'], r['year_distance_from_high_pct'], r['funding_quality'], r['funding_pos'], r['funding_neg'], r['after_28_pct'])


if __name__ == '__main__':
    main()
