import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
paths = {
    'fixed24': base/'cycle-2022q1-2024q2-segments-20261105-01/daily-fixed.csv',
    'fixed25': base/'cycle-fixed-2025q4-20261105-01/daily.csv',
    'btc24': base/'cycle-breadth-binance-archive-2024q2-20261105-01/btc-archive-year-asof-and-future.csv',
    'btc25': base/'cycle-breadth-binance-archive-2025q4-20261105-01/btc-archive-year-asof-and-future.csv',
    'archive24': base/'cycle-breadth-binance-archive-2024q2-20261105-01/archive-daily-asof.csv',
    'archive25': base/'cycle-breadth-binance-archive-2025q4-20261105-01/archive-daily-asof.csv',
}
out = base/'cycle-fixed-breadth-quarters-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def save(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)


def main():
    data = {k: read(p) for k,p in paths.items()}; rows, weeks = [], []
    for year, month, days, suffix in ((2024, 4, 91, '24'), (2025, 10, 92, '25')):
        start = datetime(year,month,1,tzinfo=timezone.utc); end = start+timedelta(days=days)
        btc = {r['as_of_utc']: r for r in data['btc'+suffix] if r['btc_source'] == 'bitstamp'}
        arch = {r['as_of_utc']: r for r in data['archive'+suffix]}
        fixed = {r['known_utc']: r for r in data['fixed'+suffix] if (r.get('quarter') == '2024Q2' if year == 2024 else r.get('source') == 'bitstamp')}
        assert len(btc) == len(arch) == days and len(fixed) == days+1
        for i in range(days):
            t = start+timedelta(days=i); key = t.isoformat(); b,a,f = btc[key],arch[key],fixed[key]
            assert b['prev_close'] and f['close'] and float(b['prev_close']) == float(f['close'])
            p,lo,hi = float(f['close']),float(f['fixed_low']),float(f['fixed_high'])
            state = 'ABOVE' if p>hi else 'BELOW' if p<lo else 'INSIDE'
            assert f['position'] == state
            known, unknown, candidates = (int(a[k]) for k in ('known','unknown','archived_candidates'))
            u7,d7,z7,u28,d28,z28 = (int(a[k]) for k in ('up7','down7','flat7','up28','down28','flat28'))
            assert known+unknown == candidates == 922 and u7+d7+z7 == u28+d28+z28 == known
            assert known == int(b['archive_known']) and u7 == int(b['archive_up7']) and u28 == int(b['archive_up28'])
            assert b['year_quality'] == b['funding_quality'] == 'OK'
            year_position = float(b['year_position']); assert math.isfinite(year_position) and 0 <= year_position <= 1
            row = {'quarter': f'{year}Q{2 if year == 2024 else 4}', 'as_of_utc': key, 'spot_close': p, 'fixed_low': lo, 'fixed_high': hi, 'fixed_position': state, 'distance_fixed_high_pct': (p/hi-1)*100, 'recent28_low': b['prior28_low'], 'recent28_high': b['prior28_high'], 'long': b['long'], 'medium': b['big'], 'short': b['small'], 'year_position_pct': year_position*100, 'archive_known': known, 'archive_unknown': unknown, 'up7': u7, 'up28': u28, 'up7_pct_known': u7/known*100 if known else 'UNKNOWN', 'up28_pct_known': u28/known*100 if known else 'UNKNOWN', 'funding_pos': b['funding_pos'], 'funding_neg': b['funding_neg'], 'stage': 'UNKNOWN', 'true_sentiment': 'UNKNOWN'}
            rows.append(row)
            if i%7 == 0:
                weeks.append({**row, 'segment_end_exclusive': min(t+timedelta(days=7),end).isoformat()})
    assert len(rows)==183 and len(weeks)==27
    out.mkdir(parents=True,exist_ok=True)
    for name, data_rows in (('daily.csv',rows),('segments.csv',weeks)):
        target=out/name; save(target,data_rows); paths['output_'+name]=target
    (out/'summary.json').write_text(json.dumps({'daily_rows':len(rows),'segment_rows':len(weeks),'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()}},indent=2)+'\n')
    for r in weeks:
        print(r['quarter'],r['as_of_utc'][:10],r['fixed_position'],round(r['distance_fixed_high_pct'],1),r['long'],r['medium'],r['short'],r['archive_known'],r['up7'],r['up28'],r['funding_pos'],r['funding_neg'])


if __name__ == '__main__':
    main()
