import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cycle_causal_pullback_20261105 import daily, structure, check

ROOT = Path(__file__).resolve().parents[1]
DAY = timedelta(days=1)
SOURCES = {
    '2023Q1': 'data/verify/cycle-2023q1-phase-20261104-01/bitstamp-4h.csv',
    '2025Q2': 'data/market/btc-2025q2-usd-cross-20261104-01/bitstamp-4h.csv.gz',
}
OUT = ROOT/'data/verify/cycle-pullback-supplement-20261105-01'


def run():
    check()
    rows, audit = [], {}
    for quarter, source in SOURCES.items():
        year, q = int(quarter[:4]), int(quarter[-1])
        start = datetime(year, q*3-2, 1, tzinfo=timezone.utc)
        end = datetime(year+(q == 4), q*3 % 12+1, 1, tzinfo=timezone.utc)
        data = daily(ROOT/source)
        missing = [(start+DAY*i).isoformat() for i in range((end-start).days) if start+DAY*i not in data]
        audit[quarter] = {'quarter_days': (end-start).days, 'invalid_or_missing': missing}
        for offset in range(0, (end-start).days, 7):
            t = start+DAY*offset
            r = {'quarter':quarter, 'as_of_utc':t.isoformat(), 'spot_close':data.get(t-DAY,{}).get('close','')}
            r.update(structure([data.get(t-DAY*i) for i in range(35,0,-1)], t))
            r.update(future_status='NOT_APPLICABLE', future_reclaim_known_utc='', return7='NOT_APPLICABLE', return7_known_utc='', independent_phase='UNKNOWN', sentiment='UNKNOWN')
            if r['structure'] == 'DETECTED':
                assert r['break_known_utc'] < r['retest_known_utc'] <= t.isoformat()
                assert r['pre_retest_high_known_utc'] < r['retest_known_utc']
                if r['reclaim_asof'] == 'YES':
                    r['future_status'] = 'ALREADY_ASOF'
                else:
                    n = min(28,(end-t).days)
                    seq = [data.get(t+DAY*i) for i in range(n)]
                    pos = next((i for i,x in enumerate(seq) if x is None or x['close'] > r['pre_retest_high']), None)
                    if pos is None:
                        r['future_status'] = 'NO_RECLAIM' if n == 28 else 'INCOMPLETE'
                    elif seq[pos] is None:
                        r['future_status'] = 'UNKNOWN_DATA'
                    else:
                        r['future_status'] = 'RECLAIM'
                        r['future_reclaim_known_utc'] = (t+DAY*(pos+1)).isoformat()
                        seq = [data.get(t+DAY*i) for i in range(pos+1,min(pos+8,(end-t).days))]
                        first = next((i for i,x in enumerate(seq) if x is None or x['close'] <= r['pre_retest_high']), None)
                        if first is not None and seq[first] is not None:
                            r['return7'] = 'RETURNED'
                            r['return7_known_utc'] = (t+DAY*(pos+2+first)).isoformat()
                        elif first is not None or len(seq) < 7:
                            r['return7'] = 'UNKNOWN'
                        else:
                            r['return7'] = 'NO_RETURN_7D'
            rows.append(r)
    OUT.mkdir(parents=True,exist_ok=True)
    target = OUT/'segments.csv'
    with target.open('w',newline='') as f:
        w = csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)
    summary = {'quality':audit, 'count':len(rows),
        'by_quarter':{q:dict(Counter(r['structure'] for r in rows if r['quarter']==q)) for q in SOURCES},
        'forward':dict(Counter(r['future_status'] for r in rows if r['structure']=='DETECTED')),
        'returns':dict(Counter(r['return7'] for r in rows if r['future_status']=='RECLAIM')),
        'hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*(ROOT/s for s in SOURCES.values()),target]}}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    run()
