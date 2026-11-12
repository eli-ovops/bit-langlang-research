"""One-off public price snapshot for the frozen cycle research protocol."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import requests
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended

OUT = Path('data/verify/cycle-independent-recent-20261105-02')
T0 = pd.Timestamp('2026-11-01', tz='UTC')
T1 = pd.Timestamp('2026-11-05', tz='UTC')
START = T0 - pd.Timedelta(days=56)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    calls = {
        'kraken': ('https://api.kraken.com/0/public/OHLC',
                   {'pair': 'XBTUSD', 'interval': 240,
                    'since': int(START.timestamp())}),
        'bitfinex': ('https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist',
                     {'start': int(START.timestamp()*1000), 'end': int(T1.timestamp()*1000)-1,
                      'limit': 10000, 'sort': 1}),
    }
    summaries, frames = {}, {}
    for source, (url, params) in calls.items():
        try:
            response = requests.get(url, params=params, timeout=45)
            response.raise_for_status()
        except requests.RequestException as exc:
            summaries[source] = {'status': 'UNKNOWN_REQUEST_FAILED', 'error': str(exc)}
            continue
        rawpath = OUT / f'{source}-response.json'
        rawpath.write_bytes(response.content)
        payload = response.json()
        if source == 'kraken':
            if payload['error']:
                raise RuntimeError(f'Kraken response error: {payload["error"]}')
            keys = [k for k in payload['result'] if k != 'last']
            assert len(keys) == 1
            rows = [[int(x[0]) * 1000, float(x[1]), float(x[2]), float(x[3]),
                     float(x[4]), float(x[6])] for x in payload['result'][keys[0]]]
        else:
            # Bitfinex raw is [timestamp, open, close, high, low, volume].
            rows = [[int(x[0]), float(x[1]), float(x[3]), float(x[4]),
                     float(x[2]), float(x[5])] for x in payload]
        df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df = df[(df.ts >= int(START.timestamp()*1000)) & (df.ts < int(T1.timestamp()*1000))]
        df = df.sort_values('ts')
        assert not df.ts.duplicated().any()
        if source == 'bitfinex':
            df.index = pd.to_datetime(df.ts, unit='ms', utc=True)
            hh = df.resample('4h').agg(open=('open','first'), high=('high','max'),
                low=('low','min'), close=('close','last'), volume=('volume','sum'),
                min_volume=('volume','min'), n=('ts','size'))
            hh = hh[(hh.n == 4) & (hh.min_volume > 0)].copy()
            hh['ts'] = hh.index.asi8 // 1000000
            df = hh[['ts','open','high','low','close','volume']].reset_index(drop=True)
        path = OUT / f'{source}-4h.csv'
        df.to_csv(path, index=False)
        daily, four = read(path)
        four['bad'] = four.bad | (~np.isfinite(four.volume)) | (four.volume <= 0)
        four['good'] = ~four.bad
        daily = four.resample('D').agg(high=('high','max'), low=('low','min'),
                   close=('close','last'), n=('close','size'), bad=('bad','sum'))
        daily['good'] = daily.n.eq(6) & daily.bad.eq(0)
        expected = pd.date_range(START, T1-pd.Timedelta(hours=4), freq='4h')
        missing = expected.difference(four.index)
        summaries[source] = {'request_url': response.url, 'http_status': response.status_code,
            'raw_sha256': digest(rawpath), 'csv_sha256': digest(path),
            'expected': len(expected), 'rows': len(four),
            'missing': [x.isoformat() for x in missing],
            'bad_bars': int(four.bad.sum())}
        frames[source] = (daily, four)
    output = []
    for t in pd.date_range(T0, T1, freq='D'):
        for source, (daily, four) in frames.items():
            x = evaluate_extended(daily, four, t)
            prior = daily.loc[(daily.index >= t-pd.Timedelta(days=28)) & (daily.index < t)]
            bounds = {'prior28_low': float(prior.low.min()), 'prior28_high': float(prior.high.max())}
            if len(prior) != 28 or not prior.good.all():
                bounds = {'prior28_low': None, 'prior28_high': None}
            output.append({'time': t.isoformat(), 'source': source,
                'close': x.get('prior_close'), 'long56': x['long_relation'],
                'big28': x['big_relation'], 'small8': x['small_relation'],
                'legacy_season': x['season'], **bounds})
            altered = four.copy()
            altered.loc[altered.index >= t, ['open','high','low','close']] *= 2
            altered_d = altered.resample('D').agg(high=('high','max'), low=('low','min'),
                      close=('close','last'), n=('close','size'), bad=('bad','sum'))
            altered_d['good'] = altered_d.n.eq(6) & altered_d.bad.eq(0)
            y = evaluate_extended(altered_d, altered, t)
            assert all(x[k] == y[k] for k in ('long_relation','big_relation','small_relation','season'))
    pd.DataFrame(output).to_csv(OUT/'asof.csv', index=False)
    (OUT/'summary.json').write_text(json.dumps({'sources': summaries,
        'protocol_sha256': digest(Path('docs/浪浪周期-独立判读与新时段事前协议-20261105.md')),
        'script_sha256': digest(Path(__file__)),
        'future_perturbation': f'{len(output)}/{len(output)} pass'}, indent=2))
    print(json.dumps(summaries, indent=2))
    print(pd.DataFrame(output).to_string(index=False))


if __name__ == '__main__':
    main()
