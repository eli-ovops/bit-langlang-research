"""Analyze as-of windows from checksummed public archives; no trading decisions."""
from pathlib import Path
import csv, hashlib, io, json, math, sys, zipfile
from collections import Counter
from datetime import datetime, timezone, timedelta

if sys.argv[1:] == ['additional']:
    P = Path('data/verify/cycle-breadth-binance-archive-2024nov-2026jan-20261105-01')
    months = ('2024-10', '2024-11', '2025-12', '2026-01')
    dates = ([datetime(2024, 11, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)] +
             [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(31)])
elif sys.argv[1:] == ['historical']:
    P = Path('data/verify/cycle-breadth-binance-archive-2022nov-2023nov-20261105-01')
    months = ('2022-10', '2022-11', '2023-10', '2023-11')
    dates = ([datetime(2022, 11, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)] +
             [datetime(2023, 11, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)])
elif sys.argv[1:] == ['q4_2025']:
    P = Path('data/verify/cycle-breadth-binance-archive-2025q4-20261105-01')
    months = ('2025-09', '2025-10', '2025-11', '2025-12')
    dates = [datetime(2025, 10, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(92)]
elif sys.argv[1:] == ['q2_2024']:
    P = Path('data/verify/cycle-breadth-binance-archive-2024q2-20261105-01')
    months = ('2024-03', '2024-04', '2024-05', '2024-06')
    dates = [datetime(2024, 4, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(91)]
elif not sys.argv[1:]:
    P = Path('data/verify/cycle-breadth-binance-archive-2025aug-20261105-01')
    months = ('2025-07', '2025-08')
    dates = [datetime(2025, 8, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(31)]
else:
    raise SystemExit('Use no arguments, additional, historical, q4_2025 or q2_2024')
index = json.loads((P / 'archive-index.json').read_text())
receipts = [json.loads(x) for x in (P / 'archive-receipts.jsonl').read_text().splitlines()]
names = index['names']
assert len(receipts) == len(names) * len(months)
lookup = {(x['symbol'], x['month']): x for x in receipts}
assert len(lookup) == len(receipts)
series, problems = {}, []
for name in names:
    bars = {}
    for month in months:
        receipt = lookup[(name, month)]
        if receipt['status'] != 'OK':
            continue
        path = P / 'archives' / f'{name}-1d-{month}.zip'
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
            problems.append({'symbol': name, 'month': month, 'error': 'ARCHIVE_HASH_CHANGED'})
            continue
        try:
            parsed = {}
            with zipfile.ZipFile(path) as z:
                member = z.namelist()
                assert len(member) == 1
                rows = list(csv.reader(io.StringIO(z.read(member[0]).decode('utf-8-sig'))))
            if rows and rows[0][0] == 'open_time':
                rows = rows[1:]
            for raw in rows:
                ts, o, h, l, c, vol, end = int(raw[0]), *map(float, raw[1:6]), int(raw[6])
                time = datetime.fromtimestamp(ts / 1000, timezone.utc)
                good = (time.strftime('%Y-%m') == month and ts % 86400000 == 0 and
                        end == ts + 86400000 - 1 and all(math.isfinite(v) and v > 0 for v in (o, h, l, c, vol)) and
                        l <= min(o, h, l, c) and h >= max(o, h, l, c))
                if time in parsed:
                    parsed[time] = None
                    problems.append({'symbol': name, 'time': time.isoformat(), 'error': 'DUPLICATE'})
                else:
                    parsed[time] = c if good else None
                    if not good:
                        problems.append({'symbol': name, 'time': time.isoformat(), 'error': 'INVALID_BAR'})
            bars.update(parsed)
        except (ValueError, KeyError, IndexError, AssertionError, zipfile.BadZipFile, UnicodeError) as exc:
            problems.append({'symbol': name, 'month': month, 'error': 'PARSE_UNKNOWN', 'detail': str(exc)[:120]})
    series[name] = bars

detail = P / 'contract-daily-asof.csv'
summary = P / 'archive-daily-asof.csv'
with detail.open('x', newline='') as df, summary.open('x', newline='') as sf:
    dw = csv.DictWriter(df, fieldnames=['as_of_utc', 'contract', 'quality', 'return7_pct', 'return28_pct'])
    sw = csv.DictWriter(sf, fieldnames=['as_of_utc', 'archived_candidates', 'known', 'unknown', 'up7', 'down7', 'flat7', 'up28', 'down28', 'flat28', 'up7_pct_known', 'up28_pct_known'])
    dw.writeheader(); sw.writeheader()
    for t in dates:
        valid = []
        for name in names:
            vals = [series[name].get(t - timedelta(days=i)) for i in range(29, 0, -1)]
            ok = all(v is not None for v in vals)
            r7 = 100 * (vals[-1] / vals[-8] - 1) if ok else None
            r28 = 100 * (vals[-1] / vals[0] - 1) if ok else None
            dw.writerow({'as_of_utc': t.isoformat(), 'contract': name, 'quality': 'OK' if ok else 'UNKNOWN', 'return7_pct': r7, 'return28_pct': r28})
            if ok:
                valid.append((r7, r28))
        row = {'as_of_utc': t.isoformat(), 'archived_candidates': len(names), 'known': len(valid), 'unknown': len(names) - len(valid)}
        for pos, days in enumerate((7, 28)):
            row[f'up{days}'] = sum(x[pos] > 0 for x in valid)
            row[f'down{days}'] = sum(x[pos] < 0 for x in valid)
            row[f'flat{days}'] = sum(x[pos] == 0 for x in valid)
            row[f'up{days}_pct_known'] = 100 * row[f'up{days}'] / len(valid) if valid else None
        sw.writerow(row)
        print(t.date(), 'known', len(valid), 'unknown', row['unknown'], 'up7', row['up7'], 'up28', row['up28'], flush=True)
(P / 'parse-problems.json').write_text(json.dumps(problems, ensure_ascii=False, indent=2) + '\n')
print('file statuses', dict(Counter(x['status'] for x in receipts)), 'parse/quality issues', len(problems))
