"""Stage the predeclared public ETHUSDT mark-price candles and checksums."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

BASE = 'https://data.binance.vision/data/futures/um'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', required=True)
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=False)
    months = pd.period_range('2024-07', '2026-09', freq='M')
    days = pd.date_range('2026-10-01', '2026-10-24', freq='D')
    files = [('monthly', str(x)) for x in months] + [('daily', x.strftime('%Y-%m-%d')) for x in days]
    session = requests.Session()
    manifest = []
    for frequency, date in files:
        name = f'ETHUSDT-5m-{date}.zip'
        url = f'{BASE}/{frequency}/markPriceKlines/ETHUSDT/5m/{name}'
        checksum_response = session.get(url + '.CHECKSUM', timeout=30)
        checksum_response.raise_for_status()
        checksum = checksum_response.text.split()
        if len(checksum) != 2 or checksum[1] != name or len(checksum[0]) != 64:
            raise ValueError(f'invalid checksum metadata: {name}')
        response = session.get(url, timeout=30)
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        if digest != checksum[0].lower():
            raise ValueError(f'checksum mismatch: {name}')
        (out / name).write_bytes(response.content)
        (out / (name + '.CHECKSUM')).write_bytes(checksum_response.content)
        manifest.append({'name': name, 'url': url, 'sha256': digest, 'bytes': len(response.content)})
        print(name, 'verified', flush=True)
    (out / 'manifest.json').write_text(json.dumps({'files': manifest}, indent=2) + '\n')


if __name__ == '__main__':
    main()
