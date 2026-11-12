"""Link delayed public entry quotes to signals and paper ledgers, never PASS."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from .paper_positions_reconcile import reconcile as positions_reconcile
from .paper_quote import assess as assess_quote
from .paper_risk_audit import audit as risk_audit
from .signal_reconcile import reconcile as signal_reconcile

CONFIG = Path(__file__).with_name('frozen_config.json')
DEFINITION = Path(__file__).resolve().parent.parent / 'docs/延迟报价入场-信号与账本对账-事前定义-20261030.md'


def reconcile(snapshot, events, market_dir, closed, opened, quote_records, start, as_of):
    if not isinstance(snapshot, dict) or not isinstance(events, list) or not isinstance(quote_records, dict):
        return {'status': 'INVALID', 'reason': '快照、事件或报价索引类型无效'}
    now = pd.to_datetime(as_of, utc=True, errors='coerce')
    generated = pd.to_datetime(snapshot.get('generated_at'), utc=True, errors='coerce')
    if pd.isna(now) or pd.isna(generated) or generated > now or now > pd.Timestamp.now(tz='UTC'):
        return {'status': 'INVALID', 'reason': '快照或检查时间无效'}
    signal_check = signal_reconcile(snapshot, events, market_dir, CONFIG, start, evidence_as_of=now)
    base = {'original_signal_status': signal_check['status'], 'signal_check': signal_check,
            'definition_sha256': hashlib.sha256(DEFINITION.read_bytes()).hexdigest()}
    if signal_check['status'] not in ('EXECUTION_MODEL_MISMATCH', 'PARTIAL', 'PENDING_REFERENCE'):
        return {**base, 'status': signal_check['status']}
    position_check = positions_reconcile(closed, opened, events, start, as_of)
    base['position_check'] = position_check
    if position_check['status'] in ('INVALID', 'STOP', 'STALE', 'AMBIGUOUS_ORDER'):
        return {**base, 'status': position_check['status']}
    entries = [e for e in events if isinstance(e, dict) and e.get('kind') == 'entry']
    if not entries:
        if quote_records:
            return {**base, 'status': 'INVALID', 'reason': '没有入场但存在报价映射'}
        return {**base, 'status': 'NO_ENTRY_EVIDENCE', 'reason': '没有入场证据，不能证明执行或前瞻完整'}
    if signal_check['status'] != 'EXECUTION_MODEL_MISMATCH' or position_check['status'] != 'PARTIAL':
        return {**base, 'status': 'INVALID', 'reason': '延迟信号或持仓链路不完整'}
    signals = {(e.get('symbol'), pd.to_datetime(e.get('signal_time_utc'), utc=True).isoformat()): e for e in events
               if isinstance(e, dict) and e.get('kind') == 'signal'}
    ledger = pd.concat([closed[['trade_id', 'qty']], opened[['trade_id', 'qty']]], ignore_index=True)
    quantities = dict(zip(ledger.trade_id.astype(str), ledger.qty))
    ids = [str(e.get('trade_id')) for e in entries]
    if len(ids) != len(set(ids)) or set(ids) != set(quantities):
        return {**base, 'status': 'INVALID', 'reason': '入场与账本交易编号不一一对应'}
    if set(quote_records) - set(ids):
        return {**base, 'status': 'INVALID', 'reason': '报价索引包含没有对应入场的交易编号'}
    if set(ids) - set(quote_records):
        return {**base, 'status': 'UNKNOWN_QUOTE_COVERAGE', 'reason': '报价索引与入场编号不完全一致'}
    risk = risk_audit(closed, opened, start, as_of)
    base['risk_status'] = risk['status']
    for frame, section in ((closed, 'closed'), (opened, 'open')):
        if not frame.empty and risk.get(section, {}).get('paper_initial_leverage_status') != 'PROVIDED_UNVERIFIED':
            return {**base, 'status': 'UNKNOWN_MARGIN', 'reason': '缺少纸面初始保证金，不能验证名义倍数'}
    checks = []
    quote_fingerprints = set()
    for entry in entries:
        trade_id = str(entry['trade_id'])
        record = quote_records[trade_id]
        try:
            quote = record['quote']
            # Different JSON formatting or edited prices must not turn the same
            # three local request intervals into independent observations.
            fingerprint = tuple((int(r['local_start_ms']), int(r['local_end_ms'])) for r in quote['requests'])
            if fingerprint in quote_fingerprints:
                return {**base, 'status': 'INVALID', 'reason': '不同入场重复使用同一报价观测'}
            quote_fingerprints.add(fingerprint)
            signal = signals[(entry['symbol'], pd.to_datetime(entry['signal_time_utc'], utc=True).isoformat())]
            result = assess_quote(quote, signal, entry, quantities[trade_id], now)
        except (KeyError, TypeError, ValueError, OverflowError):
            return {**base, 'status': 'INVALID', 'reason': '报价或对应信号记录无效'}
        if result['status'] != 'PARTIAL_NOT_REGISTERED':
            return {**base, 'status': result['status'], 'trade_id': trade_id, 'quote_check': result}
        checks.append({'trade_id': trade_id, 'quote_sha256': record['sha256'], 'quote_check': result})
    return {**base, 'status': 'PARTIAL_CANDIDATE_NOT_REGISTERED', 'entry_checks': checks,
            'reason': '仅是延迟报价候选的本地入场形式对账；原冻结执行仍不匹配，出场、资金费、连续覆盖与真实成交未获证明。'}


def main():
    parser = argparse.ArgumentParser()
    for flag in ('scan', 'events', 'market-dir', 'closed', 'open', 'quote-index', 'start', 'as-of'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    try:
        now = pd.to_datetime(args.as_of, utc=True, errors='raise')
        if pd.isna(now) or now > pd.Timestamp.now(tz='UTC'):
            raise ValueError('检查时间无效或晚于现在')
        if not Path(args.events).is_dir():
            raise ValueError('事件目录不存在')
        event_paths = sorted(Path(args.events).glob('*.json'))
        event_raw = [path.read_bytes() for path in event_paths]
        events = [json.loads(raw) for raw in event_raw]
        index_path = Path(args.quote_index)
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('报价索引存在重复交易编号')
                result[key] = value
            return result
        index_raw = index_path.read_bytes()
        index = json.loads(index_raw, object_pairs_hook=unique_pairs)
        if not isinstance(index, dict):
            raise ValueError('报价索引必须是交易编号到文件路径的对象')
        records = {}
        for trade_id, path in index.items():
            if not isinstance(path, str):
                raise ValueError('报价路径无效')
            raw = (index_path.parent / path).read_bytes()
            records[trade_id] = {'quote': json.loads(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        scan_raw = Path(args.scan).read_bytes()
        closed_raw, open_raw = Path(args.closed).read_bytes(), Path(args.open).read_bytes()
        closed = pd.read_csv(io.BytesIO(closed_raw), dtype=str, keep_default_na=False)
        opened = pd.read_csv(io.BytesIO(open_raw), dtype=str, keep_default_na=False)
        result = reconcile(json.loads(scan_raw), events, args.market_dir,
                           closed, opened, records, args.start, now)
        result['input_sha256'] = {
            'scan': hashlib.sha256(scan_raw).hexdigest(),
            'closed': hashlib.sha256(closed_raw).hexdigest(),
            'open': hashlib.sha256(open_raw).hexdigest(),
            'quote_index': hashlib.sha256(index_raw).hexdigest(),
            'events': {p.name: hashlib.sha256(raw).hexdigest() for p, raw in zip(event_paths, event_raw)},
        }
    except (OSError, TypeError, ValueError, KeyError) as exc:
        result = {'status': 'INVALID', 'reason': '输入不可读取或无效：' + str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
