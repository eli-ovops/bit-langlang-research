"""Retrospective, as-of descriptive cases; no signals or trading."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/verify/cycle-original-day4h-20261105-01'
CASES = [('2023-11-17', 'cycle-2023q4-pivot84-20261105-02'),
         ('2026-01-16', 'cycle-2026q1-phase-20261104-01')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calculate(df, t):
    before = df.loc[(df.index >= t - pd.Timedelta(days=28)) & (df.index < t)]
    expected = pd.date_range(t - pd.Timedelta(days=28), periods=168, freq='4h')
    assert before.index.equals(expected) and before.index.is_unique
    assert (before.volume > 0).all()
    assert ((before.high >= before[['open', 'close', 'low']].max(axis=1)) &
            (before.low <= before[['open', 'close', 'high']].min(axis=1))).all()
    old, recent = before.iloc[-48:-24], before.iloc[-24:]
    oh, ol, nh, nl = old.high.max(), old.low.min(), recent.high.max(), recent.low.min()
    relation = ('UP' if nh > oh and nl > ol else 'DOWN' if nh < oh and nl < ol
                else 'INSIDE' if nh <= oh and nl >= ol else 'MIXED')
    last, high, low = before.close.iloc[-1], before.high.max(), before.low.min()
    return dict(last_close=last, high28=high, low28=low,
                below_high_pct=(last / high - 1) * 100,
                old4d_high=oh, old4d_low=ol, recent4d_high=nh,
                recent4d_low=nl, fourhour_relation=relation)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    rows, outcomes, hashes = [], [], {}
    for day, directory in CASES:
        t = pd.Timestamp(day, tz='UTC')
        for exchange in ['bitstamp', 'kraken']:
            path = ROOT / 'data/verify' / directory / f'{exchange}-4h.csv'
            hashes[str(path.relative_to(ROOT))] = sha(path)
            raw = pd.read_csv(path)
            raw.index = pd.to_datetime(raw.ts, unit='ms', utc=True)
            assert raw.index.is_monotonic_increasing
            result = calculate(raw, t)
            rows.append(dict(as_of=day, exchange=exchange, **result))
            for days in [7, 28]:
                fwd = raw.loc[(raw.index >= t) & (raw.index < t + pd.Timedelta(days=days))]
                assert fwd.index.equals(pd.date_range(t, periods=days * 6, freq='4h'))
                assert (fwd.volume > 0).all()
                outcomes.append(dict(as_of=day, exchange=exchange, days=days,
                                     later_close=fwd.close.iloc[-1],
                                     change_pct=(fwd.close.iloc[-1] / result['last_close'] - 1) * 100))
            changed = raw.copy()
            changed.loc[changed.index >= t, ['open', 'high', 'low', 'close']] *= 3
            assert calculate(changed, t) == result
            # Independent slices and reductions, using original timestamp column.
            z = pd.read_csv(path)
            s, e = int((t - pd.Timedelta(days=28)).timestamp() * 1000), int(t.timestamp() * 1000)
            x = z[(z.ts >= s) & (z.ts < e)]
            assert len(x) == 168 and x.high.max() == result['high28'] and x.low.min() == result['low28']
            assert x.close.iloc[-1] == result['last_close']
            assert x.iloc[-48:-24].high.max() == result['old4d_high']
            assert x.iloc[-24:].low.min() == result['recent4d_low']
    pd.DataFrame(rows).to_csv(OUT / 'asof.csv', index=False)
    pd.DataFrame(outcomes).to_csv(OUT / 'outcomes.csv', index=False)
    protocol = ROOT / 'docs/浪浪周期-原话日线压力四小时案例定义-20261105.md'
    (OUT / 'audit.json').write_text(json.dumps(dict(input_sha256=hashes,
        protocol_sha256=sha(protocol), script_sha256=sha(Path(__file__)),
        checks='grid, OHLC, positive volume, independent slices, future perturbation'), indent=2))


if __name__ == '__main__':
    main()
