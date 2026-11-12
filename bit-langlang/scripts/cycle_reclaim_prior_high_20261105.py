import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'data/verify'
inputs = {
    'segments': base/'cycle-two-regime-segments-20261105-01/asof-segments.csv',
    '2023': base/'cycle-fixed-quarter-review-20261105-01/daily.csv',
    '2025': base/'cycle-fixed-2025q4-20261105-01/daily.csv',
}
out = base/'cycle-reclaim-prior-high-20261105-01'


def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    source = {k: read(p) for k,p in inputs.items()}
    rows, summary = [], []
    for year in (2023, 2025):
        start = datetime(year,10,15,tzinfo=timezone.utc); end = datetime(year+1,1,1,tzinfo=timezone.utc)
        ref = [r for r in source['segments'] if r['quarter'] == f'{year}Q4' and r['start_utc'] == start.isoformat()]
        assert len(ref) == 1
        ref = ref[0]; high = float(ref['recent28_high'])
        original = [r for r in source[str(year)] if r['source'] == 'bitstamp' and (year != 2023 or r['year'] == '2023')]
        original.sort(key=lambda x:x['known_utc'])
        original = [r for r in original if start.isoformat() <= r['known_utc'] <= end.isoformat()]
        assert len(original) == 79 and float(ref['close']) == float(original[0]['close']) and high > 0
        last, changes, count = None, [], Counter()
        for i,r in enumerate(original):
            t = datetime.fromisoformat(r['known_utc']); assert t == start+timedelta(days=i)
            price = float(r['close']) if r['close'] and r['position'] != 'UNKNOWN' else None
            state = 'UNKNOWN' if price is None else 'ABOVE' if price > high else 'AT_OR_BELOW'
            if last is not None and state != last:
                changes.append({'known_utc':t.isoformat(),'from':last,'to':state,'close':price})
            if i: count[state] += 1
            rows.append({'quarter':f'{year}Q4','known_utc':t.isoformat(),'source':'bitstamp','close':price,'fixed_recent_high':high,'position':state,'quarter_fixed_position':r['position'],'phase':'UNKNOWN','sentiment':'UNKNOWN'})
            last = state
        summary.append({'quarter':f'{year}Q4','reference_as_of':start.isoformat(),'recent28_high':high,'comparison_start_close':float(ref['close']),'initial_fixed_position':ref['fixed_position'],'states_after_start':dict(count),'changes':changes})
    assert len(rows) == 158
    out.mkdir(parents=True,exist_ok=True)
    target=out/'daily.csv'
    with target.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    (out/'summary.json').write_text(json.dumps({'sources':summary,'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list(inputs.values())+[target]}},indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
