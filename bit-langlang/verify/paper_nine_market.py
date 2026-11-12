"""Offline v0.1 BTC market-layer recomputation. No account or order actions."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

D = 86400000
URL = 'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1d&limit=40'


def moment(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamp timezone required')
    return value.astimezone(timezone.utc)


def evaluate(body, receipt, as_of):
    try:
        return _evaluate(body, receipt, as_of)
    except (KeyError, ValueError, TypeError, IndexError, OverflowError, InvalidOperation) as exc:
        return {'status': 'UNKNOWN', 'reason': str(exc)}


def _evaluate(body, receipt, as_of):
    if not isinstance(body, bytes) or not isinstance(receipt, dict):
        raise ValueError('response and receipt required')
    observed = moment(as_of)
    received = moment(receipt['received_utc'])
    requested = moment(receipt['request_utc'])
    if requested > received or received > observed or observed > datetime.now(timezone.utc):
        raise ValueError('inconsistent availability time')
    if receipt.get('url') != URL or receipt.get('http') != 200 or hashlib.sha256(body).hexdigest() != receipt.get('sha256'):
        raise ValueError('receipt URL, HTTP or hash mismatch')
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError('candles must be a list')
    received_ms = int(received.timestamp()*1000)
    observed_ms = int(observed.timestamp()*1000)
    # A candle is known only after its full close and the response has arrived.
    closed = [row for row in rows if int(row[6]) < received_ms]
    if len(closed) < 35:
        raise ValueError('insufficient closed daily history')
    times = [int(row[0]) for row in closed]
    if len(times) != len(set(times)) or any(b-a != D for a,b in zip(times,times[1:])):
        raise ValueError('duplicate, unordered or missing daily candle')
    if times[-1] != (observed_ms//D)*D-D:
        raise ValueError('latest complete daily candle not available at as-of')
    bars = []
    for row in closed[-35:]:
        t = int(row[0])
        op, high, low, close, volume = map(Decimal, (str(row[1]),str(row[2]),str(row[3]),str(row[4]),str(row[5])))
        if (t % D or int(row[6]) != t+D-1 or not all(x.is_finite() for x in (op,high,low,close,volume)) or
                not (0 < low <= min(op,close) <= max(op,close) <= high and volume > 0)):
            raise ValueError('invalid daily candle')
        bars.append((high,close))
    breaks = []
    for i in range(28,35):
        level = max(x[0] for x in bars[i-28:i])
        if bars[i][1] > level:
            breaks.append({'day_utc':datetime.fromtimestamp((times[-35]+i*D)/1000,timezone.utc).date().isoformat(),
                           'B':str(level), 'close':str(bars[i][1])})
    last_close = bars[-1][1]
    last_high = max(x[0] for x in bars[-7:])
    candidate = bool(breaks and last_close > Decimal(breaks[-1]['B']) and last_high > last_close)
    return {'status':'CANDIDATE' if candidate else 'NO_CANDIDATE',
            'as_of_utc':observed.isoformat(), 'received_utc':received.isoformat(),
            'last_closed_day_utc':datetime.fromtimestamp(times[-1]/1000,timezone.utc).date().isoformat(),
            'last_close':str(last_close), 'last7_high':str(last_high), 'breaks':breaks,
            'phase_truth':'UNKNOWN', 'emotion':'UNKNOWN', 'orders':'NONE',
            'warning':'v0.1 highest-high condition does not prove post-break pullback; not an entry decision',
            'provenance':'local receipt/hash only; source authenticity and continuous coverage UNKNOWN'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--response',required=True)
    parser.add_argument('--receipt',required=True)
    parser.add_argument('--as-of',required=True)
    args=parser.parse_args()
    try:
        result=evaluate(Path(args.response).read_bytes(),json.loads(Path(args.receipt).read_bytes()),args.as_of)
    except (OSError,ValueError) as exc:
        result={'status':'UNKNOWN','reason':str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
