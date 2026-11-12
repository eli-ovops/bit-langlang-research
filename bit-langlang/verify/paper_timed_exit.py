"""EMA/30-day paper exits with causally ordered public quotes; no order execution."""
import argparse
import hashlib
import io
import json
import math
import zlib
from pathlib import Path

import pandas as pd

from .forward_report import valid_trade_id
from .forward_scan import closed_snapshot
from .paper_closed_audit import audit as audit_closed
from .paper_quote import CONFIG, assess, checked_book

MAX_LAG = pd.Timedelta(minutes=15)
DEFINITION = Path(__file__).resolve().parent.parent / 'docs/延迟报价-日线和到期出场-事前定义-20261030.md'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    value = pd.to_datetime(value, utc=True, errors='raise')
    if pd.isna(value):
        raise ValueError('时间缺失')
    return value


def entry_details(entry):
    config = sha(CONFIG.read_bytes())
    if (entry.get('schema') != 'paper-event-v1' or entry.get('verification') != 'MANUAL_UNVERIFIED'
            or entry.get('config_sha256') != config or entry.get('kind') != 'entry'
            or entry.get('symbol') != 'ETHUSDT' or not valid_trade_id(entry.get('trade_id'))):
        raise ValueError('入场事件格式无效')
    entered = timestamp(entry['event_time_utc'])
    captured = timestamp(entry['captured_at_utc'])
    signal_time = timestamp(entry['signal_time_utc'])
    frozen = pd.Timestamp(json.loads(CONFIG.read_text())['frozen_at'], tz='UTC')
    lag = float(entry['capture_lag_seconds'])
    if (signal_time < frozen or signal_time.floor('5min') != signal_time
            or entered < signal_time+pd.Timedelta(minutes=5) or captured < entered
            or not math.isfinite(lag) or lag > 900 or abs((captured-entered).total_seconds()-lag) > .001):
        raise ValueError('入场事件采集时间无效')
    return entered, captured


def make_observation(kind, entry, entry_raw, observed, *, signal_day=None, scan_raw=None, market_raw=None):
    """Build a bounded, unverified observation; current time must be supplied by caller."""
    if json.loads(entry_raw) != entry:
        raise ValueError('入场文件与事件内容不一致')
    entered, entry_captured = entry_details(entry)
    observed = timestamp(observed)
    if entry_captured >= observed:
        raise ValueError('出场观察必须晚于入场记录采集')
    result = {'schema': 'paper-timed-exit-observation-v1', 'kind': kind, 'symbol': 'ETHUSDT',
              'trade_id': str(entry['trade_id']), 'entry_sha256': sha(entry_raw),
              'config_sha256': sha(CONFIG.read_bytes()), 'captured_at_utc': observed.isoformat(),
              'verification': 'MANUAL_UNVERIFIED'}
    if kind == 'max_30d':
        trigger = entered + pd.Timedelta(days=30)
    elif kind == 'ema20':
        day = timestamp(signal_day)
        if day != day.floor('D') or scan_raw is None or market_raw is None:
            raise ValueError('EMA 信号日或行情证据无效')
        trigger = day + pd.Timedelta(days=1)
        if trigger <= entered:
            raise ValueError('EMA 信号发生于入场之前')
        snapshot = json.loads(scan_raw)
        if snapshot['config_sha256'] != result['config_sha256']:
            raise ValueError('行情快照配置不符')
        generated = timestamp(snapshot['generated_at'])
        metadata = snapshot['symbols']['ETHUSDT']
        if (metadata['data_sha256'] != sha(market_raw) or metadata['data_status']['status'] != 'FRESH'
                or not trigger <= generated < observed):
            raise ValueError('行情快照的哈希、新鲜度或顺序无效')
        data = pd.read_csv(io.BytesIO(market_raw), usecols=['ts', 'open', 'high', 'low', 'close'], compression='gzip')
        data['ts'] = pd.to_datetime(data.ts, unit='ms', utc=True, errors='coerce')
        closed, state = closed_snapshot(data, generated, minimum_bars=205*288)
        if state['status'] != 'FRESH':
            raise ValueError('行情快照缺口或过期')
        prefix = closed.loc[closed.ts < trigger]
        if len(prefix) < 205*288 or prefix.ts.iloc[-1] != trigger-pd.Timedelta(minutes=5):
            raise ValueError('EMA 信号日不完整或预热不足')
        daily = prefix.set_index('ts').close.resample('1D').last()
        daily_close = float(daily.loc[day])
        ema = float(daily.ewm(span=20, adjust=False).mean().loc[day])
        if not math.isfinite(ema) or not daily_close < ema:
            raise ValueError('日线收盘未低于 EMA20')
        result.update(signal_day_utc=day.isoformat(), daily_close=daily_close, ema20=ema,
                      scan_sha256=sha(scan_raw), market_sha256=sha(market_raw))
    else:
        raise ValueError('不支持的出场观察类型')
    if observed < trigger or observed > trigger + MAX_LAG:
        raise ValueError('出场观察过早或超过 15 分钟')
    result['trigger_time_utc'] = trigger.isoformat()
    return result


def check(signal, entry, entry_raw, entry_quote, observation, exit_event, exit_quote,
          ledger, funding, start, as_of, *, schedule=None, scan_raw=None, market_raw=None, clock_for_test=None):
    """Reconcile one closed hypothetical trade and funding coverage, never PASS."""
    try:
        now = timestamp(as_of)
        clock = pd.Timestamp.now(tz='UTC') if clock_for_test is None else timestamp(clock_for_test)
        if now > clock:
            raise ValueError('检查时间晚于当前时间')
        if len(ledger) != 1:
            raise ValueError('账本必须仅包含一笔已平仓交易')
        row = ledger.iloc[0]
        qty = float(row['qty'])
        entry_check = assess(entry_quote, signal, entry, qty, now)
        if entry_check['status'] != 'PARTIAL_NOT_REGISTERED':
            return {'status': entry_check['status'], 'entry_check': entry_check}
        observed = timestamp(observation['captured_at_utc'])
        if observed > now:
            raise ValueError('观察时间晚于检查时间')
        expected = make_observation(observation['kind'], entry, entry_raw, observed,
                                    signal_day=observation.get('signal_day_utc'), scan_raw=scan_raw, market_raw=market_raw)
        if observation != expected:
            raise ValueError('出场观察与入场或行情重新计算不一致')
        config = sha(CONFIG.read_bytes())
        if (exit_event.get('schema') != 'paper-event-v1' or exit_event.get('verification') != 'MANUAL_UNVERIFIED'
                or exit_event.get('config_sha256') != config or exit_event.get('kind') != 'exit'
                or exit_event.get('symbol') != 'ETHUSDT' or str(exit_event.get('trade_id')) != str(entry['trade_id'])):
            raise ValueError('出场事件格式或编号不一致')
        decision = timestamp(exit_event['event_time_utc'])
        captured = timestamp(exit_event['captured_at_utc'])
        lag = float(exit_event['capture_lag_seconds'])
        trigger = timestamp(observation['trigger_time_utc'])
        if (not math.isfinite(lag) or lag < 0 or lag > 900 or captured > now
                or abs((captured-decision).total_seconds()-lag) > .001 or decision > trigger+MAX_LAG):
            raise ValueError('出场决定或采集时间无效')
        bid, exit_ask, bid_qty, _, _ = checked_book(exit_quote, observed, decision)
        if qty > bid_qty:
            return {'status': 'UNKNOWN_DEPTH', 'reason': '出场数量超过可见一级 bid 数量'}
        entry_price, exit_price = float(entry['price']), float(exit_event['price'])
        if not math.isclose(exit_price, bid*.9998, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('出场价与 bid 减 2bp 不一致')
        result = audit_closed(ledger, entry, exit_event, entry_check['bid'], entry_check['ask'], bid, exit_ask,
                              funding, start, now, schedule=schedule)
        if result['status'] != 'PARTIAL_NOT_REGISTERED':
            return result
        return {**result, 'status': 'SYNTHETIC_ONLY' if clock_for_test is not None else 'PARTIAL_NOT_REGISTERED',
                'exit_kind': observation['kind'], 'entry_check': entry_check, 'definition_sha256': sha(DEFINITION.read_bytes())}
    except (KeyError, TypeError, ValueError, OverflowError, IndexError, OSError, EOFError, zlib.error) as exc:
        return {'status': 'INVALID', 'reason': str(exc)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('observe-ema', 'observe-deadline'):
        obs = sub.add_parser(command)
        obs.add_argument('--entry', required=True); obs.add_argument('--out', required=True)
        if command == 'observe-ema':
            obs.add_argument('--signal-day', required=True); obs.add_argument('--scan', required=True)
            obs.add_argument('--market-dir', required=True)
    validate = sub.add_parser('check')
    for flag in ('signal', 'entry', 'entry-quote', 'observation', 'exit', 'exit-quote', 'ledger', 'funding', 'start', 'as-of'):
        validate.add_argument('--'+flag, required=True)
    validate.add_argument('--schedule');validate.add_argument('--scan');validate.add_argument('--market-dir')
    args = parser.parse_args()
    try:
        entry_raw = Path(args.entry).read_bytes();entry = json.loads(entry_raw)
        if args.command.startswith('observe-'):
            observed = pd.Timestamp.now(tz='UTC')
            is_ema = args.command == 'observe-ema'
            scan_raw = Path(args.scan).read_bytes() if is_ema else None
            market_raw = (Path(args.market_dir)/'ETHUSDT_5m.csv.gz').read_bytes() if is_ema else None
            observation = make_observation('ema20' if is_ema else 'max_30d', entry, entry_raw, observed,
                                           signal_day=args.signal_day if is_ema else None,
                                           scan_raw=scan_raw, market_raw=market_raw)
            raw = (json.dumps(observation, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
            with Path(args.out).open('xb') as stream:
                stream.write(raw)
            result = {'status': 'OBSERVATION_UNVERIFIED', 'path': args.out, 'sha256': sha(raw)}
        else:
            paths = {'signal': args.signal, 'entry': args.entry, 'entry_quote': args.entry_quote,
                     'observation': args.observation, 'exit': args.exit, 'exit_quote': args.exit_quote,
                     'ledger': args.ledger, 'funding': args.funding}
            raw = {key: Path(path).read_bytes() for key, path in paths.items()}
            values = {key: json.loads(raw[key]) for key in ('signal','entry','entry_quote','observation','exit','exit_quote')}
            scan_raw = Path(args.scan).read_bytes() if args.scan else None
            market_raw = (Path(args.market_dir)/'ETHUSDT_5m.csv.gz').read_bytes() if args.market_dir else None
            ledger = pd.read_csv(io.BytesIO(raw['ledger']), dtype=str, keep_default_na=False)
            funding = pd.read_csv(io.BytesIO(raw['funding']), dtype=str, keep_default_na=False)
            result = check(values['signal'], values['entry'], raw['entry'], values['entry_quote'], values['observation'],
                           values['exit'], values['exit_quote'], ledger, funding, args.start, args.as_of,
                           schedule=args.schedule, scan_raw=scan_raw, market_raw=market_raw)
            result['input_sha256'] = {key: sha(value) for key, value in raw.items()}
            if scan_raw is not None: result['input_sha256']['scan'] = sha(scan_raw)
            if market_raw is not None: result['input_sha256']['market'] = sha(market_raw)
    except (KeyError, TypeError, ValueError, OverflowError, OSError, EOFError, zlib.error) as exc:
        result = {'status': 'INVALID', 'reason': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
