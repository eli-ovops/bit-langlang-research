"""Four preselected historical hours: retain exchange replies and report gaps."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import requests

OUT = Path('data/verify/market-2013-early-trades-20261103-01')

def main():
    OUT.mkdir(exist_ok=False)
    start = int(datetime(2013, 1, 20, tzinfo=timezone.utc).timestamp() * 1000)
    rows = []
    for hour in range(4):
        a = start + hour * 3600000
        p = {'start': a, 'end': a + 3600000 - 1, 'sort': 1, 'limit': 10000}
        r = requests.get('https://api-pub.bitfinex.com/v2/trades/tBTCUSD/hist', params=p, timeout=60)
        path = OUT / f'bitfinex-hour-{hour}.json'
        path.write_bytes(r.content)
        receipt = {'url': r.url, 'status': r.status_code, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        if not r.ok:
            receipt.update(state='UNKNOWN_HTTP_ERROR', count=None)
            rows.append(receipt)
            break
        data = json.loads(r.text, parse_float=Decimal)
        if not isinstance(data, list) or (data and not isinstance(data[0], list)):
            receipt.update(state='UNKNOWN_RESPONSE', count=None)
            rows.append(receipt)
            break
        valid = all(len(t) >= 4 and a <= t[1] < a + 3600000 and Decimal(str(t[3])) > 0 and Decimal(str(t[2])) != 0 for t in data)
        unique = len(data) == len({t[0] for t in data})
        ordered = all(data[i][1] <= data[i + 1][1] for i in range(len(data) - 1))
        receipt.update(count=len(data), valid=valid, unique=unique, ordered=ordered, state='REPORTED_TRADES' if data and len(data) < 10000 and valid and unique and ordered else 'UNKNOWN')
        if data and valid:
            receipt.update(low=str(min(Decimal(str(t[3])) for t in data)), high=str(max(Decimal(str(t[3])) for t in data)), volume=str(sum(abs(Decimal(str(t[2]))) for t in data)))
        rows.append(receipt)
    result = {'utc_window': '[2013-01-20T00:00:00Z,2013-01-20T04:00:00Z)', 'hours': rows, 'limitations': ['Exchange-reported trades do not prove authentic or complete history.', 'Unknown hours cannot be filled from a different venue.', 'Sample was previously exposed; no independent stage reference.']}
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
