import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .forward_report import report
from .paper_risk_audit import audit
from .paper_positions_reconcile import reconcile as reconcile_positions
from .paper_equity import evaluate as evaluate_equity
from .funding_reconcile import FIELDS as FUNDING_FIELDS, reconcile as reconcile_funding


class SimultaneousRiskTests(unittest.TestCase):
    def setUp(self):
        common = {'symbol': 'ETHUSDT', 'side': 'long', 'entry': '100', 'stop': '99.6',
                  'qty': '2', 'equity_at_entry': '2000', 'margin_at_entry': '40'}
        old = {**common, 'entry_time': '2026-10-30T01:00:00Z', 'exit_time': '2026-10-31T01:00:00Z',
               'exit': '100', 'fee_cost': '.2', 'funding_cost': '0', 'five_q_pass': '1',
               'stop_placed': '1', 'added': '0', 'reversed': '0', 'plan_deviation': '0',
               'reference_entry': '100', 'reference_exit': '100', 'reference_source': 'synthetic'}
        new = {**common, 'entry_time': '2026-10-31T01:00:00Z', 'mark_price': '100',
               'mark_time': '2026-10-31T01:05:00Z', 'mark_source': 'synthetic',
               'entry_fee': '.1', 'funding_cost': '0'}
        self.closed = pd.DataFrame([{**old, 'trade_id': 'c' + str(i)} for i in range(3)])
        self.opened = pd.DataFrame([{**new, 'trade_id': 'o' + str(i)} for i in range(3)])
        self.start = '2026-10-30T00:00:00Z'
        self.now = '2026-10-31T01:06:00Z'

    def test_simultaneous_exit_and_entry_have_bounded_risk(self):
        result = audit(self.closed, self.opened, self.start, self.now)
        self.assertEqual(result['status'], 'AMBIGUOUS_ORDER')
        self.assertEqual(result['max_concurrent_recorded'], 3)
        self.assertEqual(result['max_concurrent_upper_recorded'], 6)
        self.assertEqual(result['peak_initial_price_risk_usdt_recorded'], 2.4)
        self.assertEqual(result['peak_initial_price_risk_upper_usdt_recorded'], 4.8)
        self.assertEqual(result['concurrent_limit_assessment'], 'AMBIGUOUS_ORDER')
        self.assertFalse(result['combined_limit_violations']['concurrent_over_limit'])

    def test_clear_order_changes_bounds_and_known_overlimit_stops(self):
        self.opened['entry_time'] = '2026-10-31T01:00:01Z'
        later = audit(self.closed, self.opened, self.start, self.now)
        self.assertEqual(later['status'], 'REVIEW')
        self.assertEqual(later['max_concurrent_upper_recorded'], 3)
        self.assertEqual(later['concurrent_limit_assessment'], 'WITHIN_RECORDED_BOUNDS')
        self.opened['entry_time'] = '2026-10-31T00:59:59Z'
        earlier = audit(self.closed, self.opened, self.start, self.now)
        self.assertEqual(earlier['status'], 'STOP')
        self.assertEqual(earlier['concurrent_limit_assessment'], 'EXCEEDED')
        self.assertEqual(earlier['max_concurrent_recorded'], 6)

    def test_closed_report_marks_same_time_as_uncertain(self):
        next_closed = self.opened.drop(columns=['mark_price', 'mark_time', 'mark_source', 'entry_fee']).copy()
        next_closed = next_closed.assign(exit_time='2026-11-01T01:00:00Z', exit='101', fee_cost='.2',
                                          five_q_pass='1', stop_placed='1', added='0', reversed='0',
                                          plan_deviation='0', reference_entry='100', reference_exit='101',
                                          reference_source='synthetic')
        result = report(pd.concat([self.closed, next_closed], ignore_index=True), self.start, '2026-11-01T02:00:00Z')
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['max_concurrent_closed_only'], 3)
        self.assertEqual(result['max_concurrent_upper_closed_only'], 6)
        self.assertTrue(result['same_time_order_ambiguous'])
        self.assertIsNone(result['candidate_threshold_met_unverified'])

    def test_position_reconciliation_propagates_portfolio_ambiguity(self):
        config_hash = hashlib.sha256(Path(__file__).with_name('frozen_config.json').read_bytes()).hexdigest()
        events = []
        def add(kind, trade_id, stamp, price):
            when = pd.Timestamp(stamp)
            events.append({'schema': 'paper-event-v1', 'verification': 'MANUAL_UNVERIFIED',
                           'config_sha256': config_hash, 'kind': kind, 'trade_id': trade_id,
                           'symbol': 'ETHUSDT', 'event_time_utc': when.isoformat(),
                           'captured_at_utc': (when + pd.Timedelta(seconds=1)).isoformat(),
                           'capture_lag_seconds': 1, 'price': price,
                           'signal_time_utc': (when - pd.Timedelta(minutes=5)).isoformat() if kind == 'entry' else None})
        for row in self.closed.itertuples():
            add('entry', row.trade_id, row.entry_time, row.entry)
            add('exit', row.trade_id, row.exit_time, row.exit)
        for row in self.opened.itertuples():
            add('entry', row.trade_id, row.entry_time, row.entry)
            add('mark', row.trade_id, row.mark_time, row.mark_price)
        result = reconcile_positions(self.closed, self.opened, events, self.start, self.now)
        self.assertEqual(result['status'], 'AMBIGUOUS_ORDER')
        self.assertEqual(result['risk_status'], 'AMBIGUOUS_ORDER')

    def test_cli_reports_bounds_for_synthetic_ledger(self):
        closed = self.closed.copy()
        opened = self.opened.copy()
        for frame, fields in ((closed, ('entry_time', 'exit_time')), (opened, ('entry_time', 'mark_time'))):
            for field in fields:
                frame[field] = pd.to_datetime(frame[field], utc=True) - pd.Timedelta(days=1)
        with tempfile.TemporaryDirectory() as directory:
            closed_path = Path(directory) / 'closed.csv'
            open_path = Path(directory) / 'open.csv'
            closed.to_csv(closed_path, index=False)
            opened.to_csv(open_path, index=False)
            command = [sys.executable, '-m', 'verify.paper_risk_audit', '--closed', str(closed_path),
                       '--open', str(open_path), '--start', '2026-10-29T00:00:00Z',
                       '--as-of', '2026-10-30T01:06:00Z']
            result = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        self.assertEqual(result['status'], 'AMBIGUOUS_ORDER')
        self.assertEqual((result['max_concurrent_recorded'], result['max_concurrent_upper_recorded']), (3, 6))
        self.assertEqual((result['peak_initial_price_risk_usdt_recorded'], result['peak_initial_price_risk_upper_usdt_recorded']), (2.4, 4.8))

    def test_equity_and_funding_propagate_ambiguous_order(self):
        equity = evaluate_equity(self.closed, self.opened, self.start, self.now)
        self.assertEqual(equity['status'], 'AMBIGUOUS_ORDER')
        self.assertEqual(equity['risk_status'], 'AMBIGUOUS_ORDER')
        self.assertAlmostEqual(equity['modeled_equity_usdt'], 1999.1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            end = pd.Timestamp(self.now)
            manifest = {'schema': 'paper-funding-snapshot-v2', 'source': 'Binance USD-M public fundingRate',
                        'start_utc': '2026-10-29T00:00:00Z', 'end_utc_exclusive': end.isoformat(),
                        'captured_at_utc': end.isoformat(), 'query_server_time_ms': int(end.timestamp()*1000),
                        'server_time_ms': int(end.timestamp()*1000), 'symbols': {}}
            for symbol in ('BTCUSDT', 'ETHUSDT'):
                raw = b'[]'
                (root / (symbol + '.json')).write_bytes(raw)
                manifest['symbols'][symbol] = {'file': symbol + '.json', 'sha256': hashlib.sha256(raw).hexdigest(), 'count': 0}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            covered_opened=self.opened.assign(mark_time='2026-10-31T01:04:59Z')
            result = reconcile_funding(self.closed, covered_opened, pd.DataFrame(columns=FUNDING_FIELDS),
                                       self.start, self.now, schedule=root)
        self.assertEqual(result['status'], 'AMBIGUOUS_ORDER')
        self.assertEqual(result['risk_status'], 'AMBIGUOUS_ORDER')


if __name__ == '__main__':
    unittest.main()
