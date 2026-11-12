"""Descriptive single-snapshot cost illustration; no order or network access."""
import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


def positive(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not result.is_finite() or result <= 0:
        raise ValueError('expected a positive finite decimal')
    return result


def levels(raw, descending):
    result = [(positive(p), positive(q)) for p, q in raw]
    if not result or any((a[0] <= b[0] if descending else a[0] >= b[0])
                         for a, b in zip(result, result[1:])):
        raise ValueError('empty, duplicated or unordered book')
    return result


def sweep(book, quantity):
    remaining, notional, count = quantity, Decimal(0), 0
    for price, available in book:
        take = min(available, remaining)
        notional += price * take
        remaining -= take
        count += 1
        if remaining <= 0:
            return notional, count
    return None, count


def analyze(snapshot):
    with localcontext() as ctx:
        ctx.prec = 40
        bids = levels(snapshot['bids'], True)
        asks = levels(snapshot['asks'], False)
        bid, ask = bids[0][0], asks[0][0]
        if bid >= ask:
            raise ValueError('crossed or locked book')
        quantity = Decimal(750) / ask
        buy, buy_levels = sweep(asks, quantity)
        sell, sell_levels = sweep(bids, quantity)
        result = {'best_bid': bid, 'best_ask': ask, 'best_bid_quantity': bids[0][1],
                  'best_ask_quantity': asks[0][1], 'quantity_eth': quantity,
                  'buy_levels': buy_levels, 'sell_levels': sell_levels}
        if buy is None or sell is None:
            return {**result, 'status': 'UNKNOWN_DEPTH'}
        mid = (bid + ask) / 2
        spread = quantity * (ask - bid)
        depth_extra = (buy - quantity * ask) + (quantity * bid - sell)
        slip = Decimal('0.0002') * (buy + sell)
        entry = buy * Decimal('1.0002')
        exit_value = sell * Decimal('0.9998')
        fees = Decimal('0.0005') * (entry + exit_value)
        total = entry - exit_value + fees
        initial_price_risk = entry * Decimal('0.004')
        return {**result, 'status': 'DESCRIPTIVE_PUBLIC_UNVERIFIED',
                'buy_vwap': buy / quantity, 'sell_vwap': sell / quantity,
                'mid_price': mid, 'spread_bp': (ask-bid)/mid*10000,
                'spread_usdt': spread, 'additional_depth_usdt': depth_extra,
                'additional_assumed_slippage_usdt': slip, 'assumed_fees_usdt': fees,
                'illustrative_cost_usdt_excluding_funding': total,
                'illustrative_cost_bp_of_mid_notional': total/(mid*quantity)*10000,
                'initial_price_risk_usdt': initial_price_risk,
                'illustrative_cost_in_r_excluding_funding': total/initial_price_risk,
                'actual_execution': 'UNKNOWN', 'funding': 'UNKNOWN'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.preflight / 'manifest.json'
    snapshot_path = args.preflight / 'snapshot-response.json'
    manifest = json.loads(manifest_path.read_text())
    if (manifest['rest_http_status'] != 200 or manifest['rest_symbol'] != 'ETHUSDT'
            or sha(snapshot_path) != manifest['snapshot_response_sha256']):
        raise ValueError('manifest or snapshot hash mismatch')
    result = analyze(json.loads(snapshot_path.read_text()))
    result.update({'snapshot_sha256': sha(snapshot_path), 'manifest_sha256': sha(manifest_path),
                   'definition_sha256': sha(Path('docs/公开盘口成本截面-事后描述定义-20261030.md')),
                   'code_sha256': sha(Path(__file__)),
                   'snapshot_request_started_at_utc': manifest['rest_started_at_utc'],
                   'snapshot_request_completed_at_utc': manifest['rest_completed_at_utc'],
                   'source_and_clock': manifest['verification'],
                   'assumptions': {'nominal_usdt': '750', 'fee_each_side_bp': '5',
                                   'additional_adverse_slippage_each_side_bp': '2',
                                   'stop_distance_fraction': '0.004'}})
    with args.out.open('x') as output:
        json.dump(result, output, indent=2, ensure_ascii=False, default=str)
        output.write('\n')


if __name__ == '__main__':
    main()
