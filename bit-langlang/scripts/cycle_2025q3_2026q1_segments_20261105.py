import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
inputs = {'2025': base/'cycle-fixed-2025q3-20261105-01/segments.csv', '2026': base/'cycle-fixed-2026q1-20261105-01/segments.csv', 'daily': base/'cycle-rebound-full-quarters-20261105-01/daily.csv'}
out = base/'cycle-2025q3-2026q1-segments-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    source = {k: read(p) for k, p in inputs.items()}
    rows = []
    for year, month, quarter, days in ((2025, 7, '2025Q3', 92), (2026, 1, '2026Q1', 90)):
        start = datetime(year, month, 1, tzinfo=timezone.utc); end = start+timedelta(days=days)
        sidx = {r.get('start_utc', r.get('known_utc')): r for r in source[str(year)] if r['source'] == 'bitstamp'}
        didx = {r['as_of_utc']: r for r in source['daily'] if r['quarter'] == quarter}
        count = (days+6)//7
        assert len(sidx) == count and len(didx) == days
        for i in range(count):
            t = start+timedelta(days=7*i); s, d = sidx[t.isoformat()], didx[t.isoformat()]
            price, lo, hi = float(s['close']), float(s['fixed_low']), float(s['fixed_high'])
            position = s.get('position', s.get('fixed_position'))
            assert 0 < lo < hi and position == d['fixed_position'] == ('ABOVE' if price > hi else 'BELOW' if price < lo else 'INSIDE')
            assert price == float(d['spot_close']) and (s['long'], s['medium'], s['short']) == (d['long'], d['medium'], d['short'])
            pos = s.get('funding_positive', s.get('funding_pos')); neg = s.get('funding_negative', s.get('funding_neg'))
            assert s['funding_quality'] == d['funding_quality'] == 'OK' and pos == d['funding_pos'] and neg == d['funding_neg']
            volume = s.get('spot_recent7_to_prior21_daily_volume', s.get('volume_ratio'))
            volume_quality = s.get('spot_volume_quality', s.get('volume_quality'))
            assert volume_quality == 'OK' and math.isfinite(float(volume)) and float(volume)>0
            rows.append({'quarter': quarter, 'start_utc': t.isoformat(), 'end_utc_exclusive': min(t+timedelta(days=7), end).isoformat(), 'source': 'bitstamp', 'close': price, 'fixed_low': lo, 'fixed_high': hi, 'fixed_position': position, 'long': s['long'], 'medium': s['medium'], 'short': s['short'], 'past7_futures_pct': d['past7_pct'], 'past90_futures_pct': d['past90_pct'], 'past_quality': d['prior_quality'], 'funding_pos': pos, 'funding_neg': neg, 'volume_ratio': volume, 'stage': 'UNKNOWN', 'sentiment': 'UNKNOWN'})
    assert len(rows) == 27
    out.mkdir(parents=True, exist_ok=True)
    target = out/'asof-segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    paths = list(inputs.values())+[target]
    (out/'summary.json').write_text(json.dumps({'rows': len(rows), 'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}, indent=2)+'\n')
    for r in rows:
        print(r['quarter'], r['start_utc'][:10], r['close'], r['fixed_position'], r['long'], r['medium'], r['short'], round(float(r['past7_futures_pct']),1), round(float(r['past90_futures_pct']),1), str(r['funding_pos'])+'/'+str(r['funding_neg']), round(float(r['volume_ratio']),2), r['past_quality'])


if __name__ == '__main__':
    main()
