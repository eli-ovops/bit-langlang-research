"""Check the single existing initial paper event; does not read accounts or trade.

Later/extra ledger events are deliberately unsupported, not inferred to be empty.
"""
import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .paper_nine_accounting import evaluate

FROZEN_PROTOCOL_SHA256 = 'f1a3aee97ee39bfaae6007759e1b73a8a8e751893638232ed9468135f71c62ed'
DAY = 86400000


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timezone required')
    return result.astimezone(timezone.utc)


def bridge(folder):
    try:
        return _bridge(Path(folder))
    except (OSError, ValueError, TypeError, KeyError, IndexError, InvalidOperation, json.JSONDecodeError) as exc:
        return {'status': 'INVALID', 'reason': str(exc)}


def _bridge(folder):
    protocol = (folder / '协议.md').read_bytes()
    response = (folder / 'btc-daily-response.json').read_bytes()
    receipt = json.loads((folder / 'btc-daily-receipt.json').read_bytes())
    observation = json.loads((folder / 'observation-01.json').read_bytes())
    events = list(csv.DictReader(io.StringIO((folder / 'ledger.csv').read_text(encoding='utf-8-sig'))))
    if len(events) != 1 or events[0].get('event') != 'INITIAL_NO_ENTRY':
        return {'status': 'UNKNOWN_UNSUPPORTED_LEDGER', 'reason': 'only the original single no-entry event is supported'}
    event = events[0]
    raw_hash = hashlib.sha256(response).hexdigest()
    protocol_hash = hashlib.sha256(protocol).hexdigest()
    if (protocol_hash != FROZEN_PROTOCOL_SHA256 or observation['protocol_sha256'] != protocol_hash or
            receipt['sha256'] != raw_hash or observation['source_sha256'] != raw_hash):
        raise ValueError('protocol or source hash mismatch')
    if receipt.get('http') != 200 or receipt.get('url') != 'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1d&limit=40':
        raise ValueError('unexpected public data receipt')
    observed = stamp(observation['observed_utc'])
    if (stamp(receipt['received_utc']) != observed or stamp(event['observed_utc']) != observed or
            stamp(receipt['request_utc']) > observed or observed > datetime.now(timezone.utc)):
        raise ValueError('observation and receipt time inconsistent')
    if (observation['symbol'] != 'BTCUSDT' or observation['execution'] != 'LOCAL_PAPER_ONLY' or
            observation['phase_rule'] != 'NO_CANDIDATE' or observation['decision'] != 'NO_ENTRY' or
            observation['breaks'] != []):
        raise ValueError('unexpected observation status')
    if (event.get('symbol') or Decimal(event['cash_usdt']) != 2000 or int(event['positions']) != 0 or
            Decimal(event['fees_paid_usdt']) != 0 or Decimal(event['realized_pnl_usdt']) != 0 or
            Decimal(str(observation['cash_usdt'])) != 2000 or observation['open_positions'] != 0 or
            Decimal(str(observation['fees_paid_usdt'])) != 0):
        raise ValueError('initial event balance inconsistent')
    data = json.loads(response)
    if not isinstance(data, list):
        raise ValueError('invalid candle response')
    observed_ms = int(observed.timestamp() * 1000)
    closed = [r for r in data if int(r[6]) < observed_ms]
    if len(closed) < 35 or len(closed) != observation['closed_days']:
        raise ValueError('insufficient or inconsistent closed days')
    times = [int(r[0]) for r in closed]
    if (len(times) != len(set(times)) or any(b-a != DAY for a,b in zip(times,times[1:])) or
            times[-1] != (observed_ms // DAY) * DAY - DAY):
        raise ValueError('daily grid missing, duplicate, unordered or stale')
    parsed = []
    for r in closed:
        t = int(r[0])
        o, h, low, c, vol = map(Decimal, (str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5])))
        if (t % DAY or int(r[6]) != t + DAY - 1 or
                not all(v.is_finite() for v in (o,h,low,c,vol)) or
                not (0 < low <= min(o,c) <= max(o,c) <= h and vol > 0)):
            raise ValueError('invalid candle')
        parsed.append((h,c))
    breaks = []
    for i in range(len(parsed)-7, len(parsed)):
        level = max(bar[0] for bar in parsed[i-28:i])
        if parsed[i][1] > level:
            breaks.append(i)
    if breaks:
        raise ValueError('initial no-break observation disagrees with candles')
    last_date = datetime.fromtimestamp(times[-1]/1000, timezone.utc).date().isoformat()
    if (last_date != observation['last_closed_day_utc'] or
            parsed[-1][1] != Decimal(str(observation['last_close'])) or
            max(x[0] for x in parsed[-7:]) != Decimal(str(observation['last7_high']))):
        raise ValueError('observation values disagree with candles')
    accounting = evaluate({'start_utc': observed.isoformat(), 'as_of_utc': observed.isoformat(), 'trades': []})
    return {'status': 'UNKNOWN', 'scope': 'single original local no-entry observation only',
            'observed_utc': observed.isoformat(), 'source_sha256': raw_hash,
            'protocol_sha256': protocol_hash, 'recomputed_market_gate': 'NO_CANDIDATE',
            'local_ledger_cash_usdt': '2000', 'local_open_positions': 0,
            'accounting': accounting,
            'limitations': ['receipts and timestamps are local, not independent source attestation',
                            'continuous observation and missed signals UNKNOWN',
                            'no trade, fills, costs or funding were validated',
                            'market phase and strategy efficacy UNKNOWN']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', required=True, help='local research evidence directory')
    args = parser.parse_args()
    print(json.dumps(bridge(args.dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
