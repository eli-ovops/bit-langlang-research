import csv
import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_causal_pullback_20261105 import daily
from cycle_pullback_blindpack_20261105 import chart

ROOT = Path(__file__).resolve().parents[1]
FIRST = ROOT/'data/market/btc-2022q4-usd-cross-20261103-01/bitstamp-4h.csv.gz'
SECOND = ROOT/'data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv'
KEY = ROOT/'data/verify/cycle-pullback-review-20261105-02/private-key.csv'
ORIGINAL = ROOT/'data/verify/cycle-pullback-review-20261105-02/private-normalized-bars.csv'
OUT = ROOT/'data/verify/cycle-a01-context-20261109-01'
FIELDS = ('open', 'high', 'low', 'close', 'volume')


def read_4h(path):
    op = gzip.open if path.suffix == '.gz' else open
    with op(path, 'rt', newline='') as f:
        data = {}
        for row in csv.DictReader(f):
            ts = int(row['ts'])
            if ts in data:
                raise ValueError('duplicate timestamp')
            data[ts] = tuple(float(row[k]) for k in FIELDS)
        return data


def main():
    a, b = read_4h(FIRST), read_4h(SECOND)
    overlap = a.keys() & b.keys()
    if not overlap or any(a[t] != b[t] for t in overlap):
        raise ValueError('source overlap mismatch')
    with KEY.open(newline='') as f:
        key = next(r for r in csv.DictReader(f) if r['id'] == 'A01')
    t = datetime.fromisoformat(key['as_of_utc'].replace('Z', '+00:00'))
    if t.tzinfo is None or t.hour or t.minute or t.second:
        raise ValueError('observation is not UTC midnight')
    days = daily(FIRST)
    for k, v in daily(SECOND).items():
        if k in days and days[k] != v:
            raise ValueError('daily overlap mismatch')
        days[k] = v
    bars = [days.get(t-timedelta(days=i)) for i in range(180, 0, -1)]
    if any(x is None for x in bars):
        raise ValueError('missing complete day')
    scale = 100/bars[-1]['close']
    candles = [[x[k]*scale for k in ('open', 'high', 'low', 'close')] for x in bars]
    with ORIGINAL.open(newline='') as f:
        original = [r for r in csv.DictReader(f) if r['id'] == 'A01']
    if len(original) != 56:
        raise ValueError('original sample count')
    for x, r in zip(candles[-56:], original):
        if any(abs(v-float(r[k])) > 1e-8 for v,k in zip(x, ('open','high','low','close'))):
            raise ValueError('original chart mismatch')
    OUT.mkdir(parents=True, exist_ok=False)
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), constrained_layout=True)
    for ax, n in zip(axes, (180, 56, 14)):
        chart(ax, candles[-n:], -n)
        ax.set_title(f'Last {n} completed daily candles')
    fig.suptitle('A01: same observation time, extended background')
    fig.savefig(OUT/'A01-context.png', dpi=140, metadata={'Software':'Matplotlib'})
    plt.close(fig)
    audit = {'observation_utc':t.isoformat(), 'count_days':len(bars), 'source_overlap_4h':len(overlap),
             'original_56_ohlc_matches':True, 'sentiment':'UNKNOWN',
             'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (FIRST,SECOND,KEY,ORIGINAL)}}
    (OUT/'private-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print('180 complete daily candles; overlap',len(overlap),'4h bars; original 56 bars match')


if __name__ == '__main__':
    main()
