"""Offline arithmetic/risk checks for the nine-coin research ledger.

Input is supplied by the caller. No data collection, account access or order actions.
PARTIAL never means evidence or an executable strategy is validated.
"""
import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SYMBOLS = {'1000PEPEUSDT', 'UNIUSDT', 'SOLUSDT', 'HYPEUSDT', 'AAVEUSDT',
           'SKYUSDT', 'ENAUSDT', 'LINKUSDT', 'LITUSDT'}
ZERO = Decimal('0')


def amount(value, field, *, positive=False, nonnegative=False):
    if value is None or isinstance(value, bool):
        raise ValueError(f'{field}: missing or invalid')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field}: invalid decimal') from None
    if not result.is_finite() or (positive and result <= ZERO) or (nonnegative and result < ZERO):
        raise ValueError(f'{field}: out of range')
    return result


def timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f'{field}: missing or invalid timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f'{field}: invalid timestamp') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f'{field}: timezone required')
    return result.astimezone(timezone.utc)


def evaluate(payload):
    try:
        return _evaluate(payload)
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        return {'status': 'INVALID', 'reason': str(exc)}


def _evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError('payload must be an object')
    start = timestamp(payload.get('start_utc'), 'start_utc')
    asof = timestamp(payload.get('as_of_utc'), 'as_of_utc')
    if asof < start or asof > datetime.now(timezone.utc):
        raise ValueError('as_of_utc precedes start or is in the future')
    trades = payload.get('trades')
    if not isinstance(trades, list):
        raise ValueError('trades must be a list')
    if not all(isinstance(row, dict) for row in trades):
        raise ValueError('each trade must be an object')
    cash = Decimal('2000')
    prior_end = None
    net_known = True
    findings = []
    results = []
    ids = set()
    ordered = sorted(trades, key=lambda row: timestamp(row.get('entry_time'), 'entry_time'))
    for row in ordered:
        ident = row.get('trade_id')
        if not isinstance(ident, str) or not ident.strip() or ident != ident.strip() or ident in ids:
            raise ValueError('missing, malformed or duplicate trade_id')
        ids.add(ident)
        symbol = row.get('symbol')
        if symbol not in SYMBOLS or row.get('side') != 'long':
            raise ValueError(f'{ident}: unsupported symbol or side')
        entry_time = timestamp(row.get('entry_time'), 'entry_time')
        if not start <= entry_time <= asof:
            raise ValueError(f'{ident}: entry outside observation period')
        if prior_end is not None and entry_time <= prior_end:
            raise ValueError(f'{ident}: overlapping or simultaneous positions')
        entry = amount(row.get('entry'), 'entry', positive=True)
        stop = amount(row.get('stop'), 'stop', positive=True)
        qty = amount(row.get('qty'), 'qty', positive=True)
        equity = amount(row.get('equity_at_entry'), 'equity_at_entry', positive=True)
        entry_fee = amount(row.get('entry_fee'), 'entry_fee', nonnegative=True)
        if abs(entry_fee - entry * qty * Decimal('0.0005')) > Decimal('0.000001'):
            raise ValueError(f'{ident}: entry fee inconsistent with assumed 0.05%')
        if stop >= entry:
            raise ValueError(f'{ident}: stop must be below entry')
        risk = (entry - stop) * qty
        if risk > equity * Decimal('0.005'):
            raise ValueError(f'{ident}: initial price risk exceeds 0.5%')
        if entry * qty > equity:
            raise ValueError(f'{ident}: notional exceeds one times equity')
        if net_known and abs(equity - cash) > Decimal('0.01'):
            raise ValueError(f'{ident}: entry equity disagrees with assumed complete ledger')
        if not net_known:
            findings.append(f'{ident}: entry equity cannot be independently reconciled')
        funding_raw = row.get('funding_cost')
        funding = None if funding_raw is None else amount(funding_raw, 'funding_cost')
        result = {'trade_id': ident, 'initial_price_risk_usdt': str(risk)}
        exit_time_raw = row.get('exit_time')
        if exit_time_raw is None:
            if row.get('exit') is not None or row.get('exit_fee') is not None:
                raise ValueError(f'{ident}: open position has exit fields')
            mark_time = timestamp(row.get('mark_time'), 'mark_time')
            if not entry_time <= mark_time <= asof:
                raise ValueError(f'{ident}: invalid mark time')
            mark = amount(row.get('mark_price'), 'mark_price', positive=True)
            if not isinstance(row.get('mark_source'), str) or not row['mark_source'].strip():
                raise ValueError(f'{ident}: missing mark source')
            result['unrealized_gross_usdt'] = str((mark-entry)*qty)
            result['net_to_mark_usdt'] = None if funding is None else str((mark-entry)*qty-entry_fee-funding)
            target = entry + Decimal('2') * (entry-stop)
            result['research_target_price'] = str(target)
            result['mark_at_or_below_stop'] = mark <= stop
            result['mark_at_or_above_target'] = mark >= target
            if mark <= stop or mark >= target:
                findings.append(f'{ident}: observed mark reaches a research level; execution UNKNOWN')
            if funding is None:
                findings.append(f'{ident}: funding UNKNOWN')
            if (asof-mark_time).total_seconds() > 900:
                findings.append(f'{ident}: mark STALE')
            findings.append(f'{ident}: stop/target path and final costs UNKNOWN')
            prior_end = asof
        else:
            exit_time = timestamp(exit_time_raw, 'exit_time')
            if not entry_time < exit_time <= asof:
                raise ValueError(f'{ident}: invalid exit time')
            exit_price = amount(row.get('exit'), 'exit', positive=True)
            exit_fee = amount(row.get('exit_fee'), 'exit_fee', nonnegative=True)
            if abs(exit_fee - exit_price * qty * Decimal('0.0005')) > Decimal('0.000001'):
                raise ValueError(f'{ident}: exit fee inconsistent with assumed 0.05%')
            gross = (exit_price-entry)*qty
            result['gross_pnl_usdt'] = str(gross)
            if funding is None:
                net_known = False
                result['net_pnl_usdt'] = None
                result['net_R'] = None
                findings.append(f'{ident}: funding UNKNOWN')
            else:
                net = gross-entry_fee-exit_fee-funding
                result['net_pnl_usdt'] = str(net)
                result['net_R'] = str(net/risk)
                if net_known:
                    cash += net
            prior_end = exit_time
        results.append(result)
    # Arithmetic is conditional on complete caller-supplied records; no external evidence is inferred.
    if not trades:
        findings.append('NO_TRADE_EVIDENCE')
    findings.extend(['trade completeness UNKNOWN', 'fee and funding provenance UNKNOWN',
                     'signal, execution and stop/target evidence UNKNOWN',
                     'margin and available cash sufficiency UNKNOWN', 'liquidation UNKNOWN'])
    return {'status': 'UNKNOWN' if findings else 'PARTIAL',
            'closed_cash_usdt_assuming_complete': str(cash) if net_known else None,
            'open_position_included_in_cash': False, 'records': results, 'limitations': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, help='caller-supplied JSON; never read credentials')
    args = parser.parse_args()
    payload = json.loads(Path(args.file).read_text())
    print(json.dumps(evaluate(payload), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
