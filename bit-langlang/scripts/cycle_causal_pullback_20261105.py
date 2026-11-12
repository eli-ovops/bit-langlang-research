import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = timedelta(days=1)
FILES = {
    '2022Q1': 'data/market/btc-2022nine-usd-cross-20261104-01/bitstamp-4h.csv.gz',
    '2022Q4': 'data/verify/cycle-2022q4-phase-20261104-01/bitstamp-4h.csv',
    '2023Q4': 'data/verify/cycle-2023q4-phase-20261104-01/bitstamp-4h.csv',
    '2024Q2': 'data/verify/cycle-2024q2-phase-20261104-02/bitstamp-4h.csv',
    '2024Q4': 'data/market/btc-2024q4-usd-cross-20261104-01/bitstamp-4h.csv.gz',
    '2025Q3': 'data/market/btc-2025q3-usd-cross-20261104-01/bitstamp-4h.csv.gz',
    '2025Q4': 'data/verify/cycle-btc-spot-2025q4-20261105-01/bitstamp-4h.csv',
    '2026Q1': 'data/verify/cycle-2026q1-phase-20261104-01/bitstamp-4h.csv',
}
SOURCE = ROOT / 'data/verify/cycle-eight-quarter-reclaim-20261105-01/segments.csv'
OUT = ROOT / 'data/verify/cycle-causal-pullback-20261105-01'


def daily(path):
    bars = {}
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as f:
        for r in csv.DictReader(f):
            t = datetime.fromtimestamp(int(r['ts']) / 1000, timezone.utc)
            if t in bars:
                raise ValueError(f'duplicate 4h timestamp: {path} {t}')
            v = [float(r[k]) for k in ('open', 'high', 'low', 'close', 'volume')]
            bars[t] = v if all(math.isfinite(x) and x > 0 for x in v) and v[2] <= min(v[0], v[3]) <= max(v[0], v[3]) <= v[1] else None
    first = min(bars).replace(hour=0, minute=0, second=0, microsecond=0)
    last = max(bars).replace(hour=0, minute=0, second=0, microsecond=0)
    result = {}
    while first <= last:
        d = [bars.get(first + timedelta(hours=4*i)) for i in range(6)]
        if all(x is not None for x in d):
            result[first] = {'open': d[0][0], 'high': max(x[1] for x in d), 'low': min(x[2] for x in d), 'close': d[-1][3]}
        first += DAY
    return result


def structure(days, t):
    if any(x is None for x in days):
        return {'structure': 'UNKNOWN'}
    baseline = max(x['high'] for x in days[:28])
    week = days[28:]
    k = next((i for i, d in enumerate(week) if d['close'] > baseline), None)
    result = {'baseline28_high': baseline}
    if k is None:
        return result | {'structure': 'NO_BREAK'}
    result['break_known_utc'] = (t - DAY * (6-k)).isoformat()
    if k == 6:
        return result | {'structure': 'BREAK_NO_LATER_DAY'}
    j = next((i for i in range(k+1, 7) if week[i]['low'] <= baseline), None)
    if j is None:
        return result | {'structure': 'BREAK_NO_LATER_TOUCH'}
    p = max(d['high'] for d in week[k:j])
    asof = next((i for i in range(j, 7) if week[i]['close'] > p), None)
    result.update(structure='DETECTED', retest_known_utc=(t-DAY*(6-j)).isoformat(),
                  retest_open_below_baseline=week[j]['open'] < baseline,
                  retest_close=week[j]['close'], pre_retest_high=p,
                  pre_retest_high_known_utc=(t-DAY*(7-j)).isoformat(),
                  reclaim_asof='YES' if asof is not None else 'NO',
                  reclaim_asof_known_utc=(t-DAY*(6-asof)).isoformat() if asof is not None else '')
    return result


def check():
    t = datetime(2024, 2, 5, tzinfo=timezone.utc)
    d = lambda o,h,l,c: {'open':o, 'high':h, 'low':l, 'close':c}
    base = [d(90,100,80,90) for _ in range(28)]
    week = [d(100,103,99,101), d(101,102,99,100)] + [d(100,102,99,100)]*5
    r = structure(base+week, t)
    assert r['structure'] == 'DETECTED' and r['pre_retest_high'] == 103 and r['reclaim_asof'] == 'NO'
    assert r['break_known_utc'] < r['retest_known_utc'] <= t.isoformat()
    assert structure(base+[d(99,103,98,99)]*7, t)['structure'] == 'NO_BREAK'
    assert structure(base+[d(101,103,100.5,101)]*7, t)['structure'] == 'BREAK_NO_LATER_TOUCH'


def main():
    check()
    datasets = {q: daily(ROOT/p) for q,p in FILES.items()}
    with SOURCE.open(newline='') as f:
        source = list(csv.DictReader(f))
    rows = []
    for original in source:
        q = original['quarter']; t = datetime.fromisoformat(original['as_of_utc']); data = datasets[q]
        days = [data.get(t-DAY*i) for i in range(35, 0, -1)]
        if days[-1] is not None:
            assert math.isclose(days[-1]['close'], float(original['spot_close']), rel_tol=0, abs_tol=1e-7), (q, t)
        r = {k: original[k] for k in ('quarter','as_of_utc','spot_close','fixed_position','long','medium','short','past7_futures_pct','past90_futures_pct','past_quality','funding_pos','funding_neg')}
        r.update(baseline_start_utc=(t-35*DAY).isoformat(), baseline_end_exclusive_utc=(t-7*DAY).isoformat(), **structure(days,t))
        r.update(future_status='NOT_APPLICABLE', future_reclaim_known_utc='', return7='NOT_APPLICABLE', return7_known_utc='', phase='UNKNOWN', sentiment='UNKNOWN')
        if r['structure'] == 'DETECTED':
            assert r['break_known_utc'] < r['retest_known_utc'] <= t.isoformat()
            assert r['pre_retest_high_known_utc'] < r['retest_known_utc']
            if r['reclaim_asof'] == 'YES':
                r['future_status'] = 'ALREADY_ASOF'
            else:
                year = int(q[:4]); quarter = int(q[-1]); end = datetime(year + (quarter == 4), (quarter*3)%12+1, 1, tzinfo=timezone.utc)
                available = min(28, (end-t).days)
                seq = [data.get(t+DAY*i) for i in range(available)]
                pos = next((i for i,x in enumerate(seq) if x is None or x['close'] > r['pre_retest_high']), None)
                if pos is None:
                    r['future_status'] = 'NO_RECLAIM' if available == 28 else 'INCOMPLETE'
                elif seq[pos] is None:
                    r['future_status'] = 'UNKNOWN_DATA'
                else:
                    r['future_status'] = 'RECLAIM'
                    r['future_reclaim_known_utc'] = (t+DAY*(pos+1)).isoformat()
                    # Extend to seven later days when the reclaim is near the 28-day horizon.
                    after = [data.get(t+DAY*i) for i in range(pos+1, min(pos+8, (end-t).days))]
                    failure = next((i for i,x in enumerate(after) if x is None or x['close'] <= r['pre_retest_high']), None)
                    if failure is not None and after[failure] is not None:
                        r['return7'] = 'RETURNED'
                        r['return7_known_utc'] = (t+DAY*(pos+2+failure)).isoformat()
                    elif failure is not None or len(after) < 7:
                        r['return7'] = 'UNKNOWN'
                    else:
                        r['return7'] = 'NO_RETURN_7D'
        rows.append(r)
    assert len(rows) == 109 and set(FILES) == {r['quarter'] for r in rows}
    OUT.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(k for r in rows for k in r))
    target = OUT/'segments.csv'
    with target.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns); w.writeheader(); w.writerows(rows)
    summary = {'observations': len(rows), 'structure': dict(Counter(r['structure'] for r in rows)),
               'by_quarter': {q: dict(Counter(r['structure'] for r in rows if r['quarter'] == q)) for q in FILES},
               'detected_future': dict(Counter(r['future_status'] for r in rows if r['structure'] == 'DETECTED')),
               'return7': dict(Counter(r['return7'] for r in rows if r['future_status'] == 'RECLAIM')),
               'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE, *[ROOT/p for p in FILES.values()], target]}}
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'sha256'}, indent=2))


if __name__ == '__main__':
    main()
