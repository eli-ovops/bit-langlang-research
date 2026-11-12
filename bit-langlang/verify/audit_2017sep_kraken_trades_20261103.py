"""Post-hoc two-minute exchange-reported trade cross-check; not phase validation."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import requests

OUT = Path('data/verify/market-2017sep-kraken-minute-20261103-01')
OLD = Path('data/verify/market-2017sep-trade-spotcheck-20261103-01')

def main():
    OUT.mkdir(exist_ok=False)
    result = []
    for i, when in enumerate(('2017-09-06T23:00:00+00:00', '2017-09-13T23:00:00+00:00')):
        start = int(datetime.fromisoformat(when).timestamp())
        cursor = str(start * 10**9)
        records, receipts, complete = [], [], False
        for page in range(5):
            response = requests.get('https://api.kraken.com/0/public/Trades', params={'pair': 'XBTUSD', 'since': cursor, 'count': 1000}, timeout=60)
            response.raise_for_status()
            path = OUT / f'kraken-{i}-{page}.json'
            path.write_bytes(response.content)
            data = json.loads(response.text, parse_float=Decimal)
            if data['error']:
                raise ValueError(data['error'])
            batch = data['result']['XXBTZUSD']
            receipts.append({'url': response.url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'count': len(batch)})
            records.extend(batch)
            if batch and Decimal(str(batch[-1][2])) >= start + 60:
                complete = True
                break
            new_cursor = data['result']['last']
            if not batch or new_cursor == cursor:
                break
            cursor = new_cursor
        kraken = [(Decimal(str(r[2])), Decimal(r[0]), Decimal(r[1])) for r in records if Decimal(start) <= Decimal(str(r[2])) < start + 60]
        old = json.loads((OLD / f'trades-{i}.json').read_text(), parse_float=Decimal)
        finex = [(Decimal(r[1]) / 1000, Decimal(str(r[3])), abs(Decimal(str(r[2])))) for r in old if start * 1000 <= r[1] < (start + 60) * 1000]
        def stats(rows):
            if not rows:
                return {'count': 0, 'status': 'UNKNOWN'}
            assert all(start <= t < start + 60 and p > 0 and v > 0 for t, p, v in rows)
            return {'count': len(rows), 'first_utc_seconds': str(min(t for t, _, _ in rows)), 'last_utc_seconds': str(max(t for t, _, _ in rows)), 'low': str(min(p for _, p, _ in rows)), 'high': str(max(p for _, p, _ in rows)), 'volume': str(sum(v for _, _, v in rows))}
        result.append({'start_utc': when, 'kraken': stats(kraken), 'bitfinex': stats(finex), 'kraken_cursor_passed_end': complete, 'requests': receipts})
    (OUT / 'summary.json').write_text(json.dumps({'post_hoc': True, 'minutes': result, 'limits': ['Exchange-reported records; presence does not independently authenticate trades.', 'Pagination reaching end does not prove source completeness.', 'Two minutes do not establish full-period completeness or market phase.']}, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
