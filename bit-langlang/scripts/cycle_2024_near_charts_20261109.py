import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cycle_pullback_blindpack_20261105 import chart

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    'data/market/btc-2023nov-usd-cross-20261103-01/bitstamp-4h.csv.gz',
    'data/verify/cycle-2023q4-phase-20261104-01/bitstamp-4h.csv',
    'data/market/btc-2024q1-usd-cross-20261104-01/bitstamp-4h.csv.gz',
    'data/verify/cycle-2024q2-phase-20261104-02/bitstamp-4h.csv',
]
OUT = ROOT / 'data/verify/cycle-2024q2-near-charts-20261109-01'
FOUR = 4 * 3600 * 1000


def main():
    bars = {}
    overlaps = 0
    for src in SOURCES:
        path = ROOT / src
        with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as f:
            for r in csv.DictReader(f):
                ts = int(r['ts'])
                values = tuple(float(r[k]) for k in ('open', 'high', 'low', 'close', 'volume'))
                o, h, l, c, v = values
                assert ts % FOUR == 0 and 0 < l <= min(o, c) <= max(o, c) <= h and v >= 0
                if ts in bars:
                    assert bars[ts] == values, (src, ts)
                    overlaps += 1
                bars[ts] = values
    with (ROOT / 'data/verify/cycle-2024q2-near-time-20261109-01/asof.csv').open() as f:
        samples = list(csv.DictReader(f))
    assert len(samples) == 13
    OUT.mkdir(parents=True, exist_ok=False)
    manifest = []
    for r in samples:
        if r['status'] != 'READY':
            manifest.append({'index': int(r['index']), 'status': 'UNKNOWN', 'reason': r['reason']})
            continue
        t = datetime.fromisoformat(r['near_asof_utc'])
        assert t.tzinfo and t.hour == t.minute == t.second == 0
        end = int(t.timestamp() * 1000)
        raw = [bars[ts] for ts in range(end - 180 * 6 * FOUR, end, FOUR)]
        daily = [(b[0][0], max(x[1] for x in b), min(x[2] for x in b), b[-1][3]) for b in (raw[i:i+6] for i in range(0, len(raw), 6))]
        assert len(daily) == 180 and daily[-1][3] == float(r['btc_last_close'])
        assert min(x[2] for x in daily) == float(r['btc_low180'])
        assert max(x[1] for x in daily) == float(r['btc_high180'])
        assert min(x[2] for x in raw[-42:]) == float(r['btc_4h7_low'])
        assert max(x[1] for x in raw[-42:]) == float(r['btc_4h7_high'])
        norm = 100 / daily[-1][3]
        fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
        for ax, arr, name in zip(axes.flat, (daily, daily[-56:], daily[-14:], raw[-42:]), ('180 completed daily', '56 completed daily', '14 completed daily', '42 completed 4h')):
            chart(ax, [[v * norm for v in b[:4]] for b in arr], -len(arr))
            ax.set_title(name)
            if name.endswith('4h'):
                ax.set_xlabel('4h bars before observation')
        fig.suptitle('BTC/USD, Bitstamp; cutoff ' + r['near_asof_utc'])
        path = OUT / (r['index'].zfill(2) + '.png')
        fig.savefig(path, dpi=130)
        plt.close(fig)
        manifest.append({'index': int(r['index']), 'status': 'READY', 'asof_utc': r['near_asof_utc'], 'last_4h_start_ms': end - FOUR, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert sum(x['status'] == 'READY' for x in manifest) == 11
    (OUT / 'manifest.json').write_text(json.dumps({'sources_sha256': {s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in SOURCES}, 'overlap_bars': overlaps, 'samples': manifest}, indent=2))
    print('11 charts; 2 UNKNOWN; same-venue overlaps checked:', overlaps)


if __name__ == '__main__':
    main()
