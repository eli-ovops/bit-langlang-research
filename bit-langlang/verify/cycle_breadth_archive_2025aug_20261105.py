"""Public archive coverage research only; no account, selection or trading."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import csv, hashlib, io, json, sys, threading, zipfile
import requests

BASE = Path('data/verify/cycle-breadth-binance-archive-2025aug-20261105-01')
if sys.argv[1:] in (['additional'], ['historical'], ['q4_2025'], ['q2_2024']):
    TARGETS = {'additional': '2024nov-2026jan', 'historical': '2022nov-2023nov', 'q4_2025': '2025q4', 'q2_2024': '2024q2'}
    OUT = Path(f"data/verify/cycle-breadth-binance-archive-{TARGETS[sys.argv[1]]}-20261105-01")
    OUT.mkdir(exist_ok=False)
    (OUT / 'archive-index.json').write_bytes((BASE / 'archive-index.json').read_bytes())
    MONTHS = {'additional': ('2024-10', '2024-11', '2025-12', '2026-01'), 'historical': ('2022-10', '2022-11', '2023-10', '2023-11'), 'q4_2025': ('2025-09', '2025-10', '2025-11', '2025-12'), 'q2_2024': ('2024-03', '2024-04', '2024-05', '2024-06')}[sys.argv[1]]
elif not sys.argv[1:]:
    OUT = BASE
    MONTHS = ('2025-07', '2025-08')
else:
    raise SystemExit('Use no arguments, additional, historical, q4_2025 or q2_2024')
ROOT = 'https://data.binance.vision/data/futures/um/monthly/klines'
NAMES = json.loads((OUT / 'archive-index.json').read_text())['names']
FILES = OUT / 'archives'
FILES.mkdir(exist_ok=False)
stop = threading.Event()
local = threading.local()

def session():
    if not hasattr(local, 'session'):
        local.session = requests.Session()
    return local.session

def job(name, month):
    file = f'{name}-1d-{month}.zip'
    url = f'{ROOT}/{name}/1d/{file}'
    if stop.is_set():
        return {'symbol': name, 'month': month, 'status': 'NOT_ATTEMPTED_STOP'}
    try:
        res = session().get(url, timeout=25)
        row = {'symbol': name, 'month': month, 'url': res.url, 'http': res.status_code}
        if res.status_code in (403, 429):
            stop.set()
            return {**row, 'status': 'STOP_HTTP'}
        if res.status_code == 404:
            return {**row, 'status': 'NOT_FOUND'}
        if not res.ok:
            return {**row, 'status': 'HTTP_ERROR'}
        (FILES / file).write_bytes(res.content)
        digest = hashlib.sha256(res.content).hexdigest()
        if stop.is_set():
            return {**row, 'sha256': digest, 'status': 'UNKNOWN_STOP_BEFORE_CHECKSUM'}
        check = session().get(url + '.CHECKSUM', timeout=25)
        if check.status_code in (403, 429):
            stop.set()
        (FILES / (file + '.CHECKSUM')).write_bytes(check.content)
        row.update(sha256=digest, checksum_http=check.status_code,
                   checksum_sha256=hashlib.sha256(check.content).hexdigest())
        if not check.ok or not check.text.split() or check.text.split()[0].lower() != digest:
            return {**row, 'status': 'CHECKSUM_UNKNOWN_OR_MISMATCH'}
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            member = z.namelist()
            if len(member) != 1 or member[0] != file[:-4] + '.csv':
                return {**row, 'status': 'ZIP_MEMBER_UNKNOWN'}
            rows = list(csv.reader(io.StringIO(z.read(member[0]).decode('utf-8-sig'))))
            if rows and rows[0][0] == 'open_time':
                rows = rows[1:]
            if not rows or any(len(x) < 7 for x in rows):
                return {**row, 'status': 'CSV_UNKNOWN'}
        return {**row, 'status': 'OK', 'rows': len(rows)}
    except (requests.RequestException, OSError, ValueError, UnicodeError, zipfile.BadZipFile) as exc:
        return {'symbol': name, 'month': month, 'url': url, 'status': 'UNKNOWN_ERROR', 'error': str(exc)[:200]}

jobs = [(n, m) for n in NAMES for m in MONTHS]
counts, done = {}, 0
with (OUT / 'archive-receipts.jsonl').open('x') as log, ThreadPoolExecutor(max_workers=6) as pool:
    futures = [pool.submit(job, n, m) for n, m in jobs]
    for future in as_completed(futures):
        row = future.result()
        log.write(json.dumps(row, ensure_ascii=False) + '\n')
        log.flush()
        counts[row['status']] = counts.get(row['status'], 0) + 1
        done += 1
        if done % 200 == 0 or done == len(jobs):
            print('checked', done, '/', len(jobs), 'statuses', counts, flush=True)
if stop.is_set():
    print('STOP: archive returned 403 or 429; unfinished files UNKNOWN', flush=True)
else:
    print('Archive acquisition finished; verify receipts and windows next.', flush=True)
