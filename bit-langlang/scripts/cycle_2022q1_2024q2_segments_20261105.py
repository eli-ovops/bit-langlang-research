import csv
import gzip
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
paths = {
    '2022_daily': base/'cycle-2022q1-continuous-20261104-01/daily.csv',
    '2022_segments': base/'cycle-2022q1-continuous-20261104-01/segments.csv',
    '2024_daily': base/'cycle-2024q2-phase-20261104-02/daily.csv',
    '2024_segments': base/'cycle-2024q2-phase-20261104-02/segments.csv',
    'market': base/'cycle-breadth-year-context-20261105-01/btc-api-daily.csv',
    '2022_funding': root/'data/market/BTCUSDT_funding.csv.gz',
    '2024_funding': base/'cycle-funding-2024q2-20261105-01/funding.json',
}
out = base/'cycle-2022q1-2024q2-segments-20261105-01'


def read(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def valid(b):
    return b is not None and all(math.isfinite(float(b[k])) for k in ('open', 'high', 'low', 'close', 'volume')) and float(b['volume']) > 0 and 0 < float(b['low']) <= min(float(b['open']), float(b['close'])) <= max(float(b['open']), float(b['close'])) <= float(b['high'])


def main():
    data = {k: read(p) for k, p in paths.items() if k != '2024_funding'}
    fees24 = json.loads(paths['2024_funding'].read_text())
    market = {int(r['ts']): r for r in data['market']}; assert len(market) == len(data['market'])
    rows, daily_fixed = [], []
    for year, month, days, q in ((2022, 1, 90, '2022Q1'), (2024, 4, 91, '2024Q2')):
        start = datetime(year, month, 1, tzinfo=timezone.utc); end = start + timedelta(days=days)
        daily = {r['as_of_utc']: r for r in data[f'{year}_daily'] if r['source'] == 'bitstamp'}
        segs = {r['start_utc']: r for r in data[f'{year}_segments'] if r['source'] == 'bitstamp'}
        assert len(daily) == days and len(segs) == 13
        first = daily[start.isoformat()]; assert first['range_status'] == 'OK'
        lo, hi = float(first['prior28_low']), float(first['prior28_high']); assert 0 < lo < hi
        final = segs[(start+timedelta(days=84)).isoformat()]
        assert final['status'] == 'COMPLETE' and final['end_utc_exclusive'] == end.isoformat()
        for j in range(days+1):
            t = start+timedelta(days=j)
            if j < days:
                d = daily[t.isoformat()]
                price = float(d['prev_close']) if d['range_status'] == 'OK' and d['prev_close'] else None
            else:
                price = float(final.get('last_close') or final['segment_end_close'])
            position = 'UNKNOWN' if price is None else 'ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE'
            daily_fixed.append({'quarter': q, 'known_utc': t.isoformat(), 'close': price, 'fixed_low': lo, 'fixed_high': hi, 'position': position})
        for i in range(13):
            t = start+timedelta(days=7*i); d, s = daily[t.isoformat()], segs[t.isoformat()]
            price = float(d['prev_close']); assert price == float(s['prev_close']) and d['range_status'] == 'OK'
            position = 'ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE'
            assert (d['long'], d['big'], d['small']) == (s['long'], s['big'], s['small'])
            changes = {}
            for n in (7, 90):
                values = [market.get(int((t-timedelta(days=j)).timestamp()*1000)) for j in range(n+1, 0, -1)]
                changes[f'past{n}_futures_pct'] = 100*(float(values[-1]['close'])/float(values[0]['close'])-1) if all(valid(b) for b in values) else 'UNKNOWN'
            begin, finish = int((t-timedelta(days=7)).timestamp()*1000), int(t.timestamp()*1000)
            raw = [{'ts': int(r['ts']), 'rate': r['funding_rate']} for r in data['2022_funding']] if year == 2022 else [{'ts': int(r['fundingTime']), 'rate': r['fundingRate']} for r in fees24]
            selected = [r for r in raw if begin <= r['ts'] < finish]; slots = [round((r['ts']-begin)/28800000) for r in selected]
            ok = len(selected) == 21 and sorted(slots) == list(range(21)) and all(abs(r['ts']-(begin+slot*28800000))<=60000 and math.isfinite(float(r['rate'])) for r,slot in zip(selected,slots))
            rows.append({'quarter': q, 'start_utc': t.isoformat(), 'end_utc_exclusive': min(t+timedelta(days=7), end).isoformat(), 'close': price, 'fixed_low': lo, 'fixed_high': hi, 'fixed_position': position, 'recent28_low': d['prior28_low'], 'recent28_high': d['prior28_high'], 'long': d['long'], 'medium': d['big'], 'short': d['small'], **changes, 'funding_quality': ('LOCAL_ONLY' if year == 2022 else 'API_SAVED') if ok else 'UNKNOWN', 'funding_pos': sum(float(r['rate'])>0 for r in selected) if ok else 'UNKNOWN', 'funding_neg': sum(float(r['rate'])<0 for r in selected) if ok else 'UNKNOWN', 'stage': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
    assert len(rows) == 26 and len(daily_fixed) == 183
    out.mkdir(parents=True, exist_ok=True)
    target = out/'asof-segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    daily_target = out/'daily-fixed.csv'
    with daily_target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=daily_fixed[0]); w.writeheader(); w.writerows(daily_fixed)
    (out/'summary.json').write_text(json.dumps({'rows': len(rows), 'daily_rows': len(daily_fixed), 'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in list(paths.values())+[target,daily_target]}}, indent=2)+'\n')
    for r in rows:
        def fmt(x): return x if x == 'UNKNOWN' else round(float(x), 1)
        print(r['quarter'], r['start_utc'][:10], r['close'], r['fixed_position'], r['long'], r['medium'], r['short'], fmt(r['past7_futures_pct']), fmt(r['past90_futures_pct']), str(r['funding_pos'])+'/'+str(r['funding_neg']), r['funding_quality'])


if __name__ == '__main__':
    main()
