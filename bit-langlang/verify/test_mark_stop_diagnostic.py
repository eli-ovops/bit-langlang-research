import unittest

import pandas as pd

from .mark_stop_diagnostic import compare
from .tph_ledger import replay


class MarkStopDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.ts = pd.date_range('2025-01-01', periods=4, freq='5min', tz='UTC')

    def run_case(self, last, mark, exit_bars=3, reason='other'):
        trades = pd.DataFrame([{'trade_id': 1, 'entry_ts': self.ts[0],
                                'exit_ts': self.ts[0] + pd.Timedelta(minutes=5 * exit_bars),
                                'reason': reason, 'stop': 99.0}])
        return compare(trades, pd.DataFrame({'ts': self.ts, 'low': last}),
                       pd.DataFrame({'ts': self.ts, 'low': mark})).iloc[0]

    def test_first_touch_categories_and_difference(self):
        for last, mark, category, diff in [
            ([100, 98, 100, 100], [98, 100, 100, 100], 'mark_earlier', -5),
            ([98, 100, 100, 100], [100, 98, 100, 100], 'last_earlier', 5),
            ([100, 98, 100, 100], [100, 98, 100, 100], 'same_bar', 0),
            ([100, 100, 100, 100], [100, 98, 100, 100], 'mark_only', None),
            ([100, 98, 100, 100], [100, 100, 100, 100], 'last_only', None),
            ([100, 100, 100, 100], [100, 100, 100, 100], 'neither', None),
        ]:
            with self.subTest(category=category):
                result = self.run_case(last, mark)
                self.assertEqual(result.category, category)
                if diff is not None:
                    self.assertEqual(result.difference_minutes, diff)

    def test_exit_bar_is_excluded_and_stop_must_match(self):
        result = self.run_case([100, 100, 98, 100], [100, 100, 98, 100], exit_bars=2)
        self.assertEqual(result.category, 'neither')
        with self.assertRaisesRegex(ValueError, 'original stop'):
            self.run_case([100, 100, 98, 100], [100, 100, 98, 100], exit_bars=2, reason='stop')

    def test_missing_price_bar_fails(self):
        trades = pd.DataFrame([{'trade_id': 1, 'entry_ts': self.ts[0],
                                'exit_ts': self.ts[3], 'reason': 'other', 'stop': 99.0}])
        incomplete = pd.DataFrame({'ts': self.ts.delete(1), 'low': [100, 100, 100]})
        with self.assertRaisesRegex(ValueError, 'incomplete price grid'):
            compare(trades, incomplete, incomplete.copy())

    def test_trigger_delays_fill_until_next_open_and_end_stays_open(self):
        bars = pd.DataFrame({'ts': self.ts, 'open': [100., 100., 95., 98.],
                             'high': [101.]*4, 'low': [100., 99., 94., 98.], 'close': [100., 99., 95., 98.]})
        funding = pd.DataFrame({'ts': pd.Series(dtype='int64'), 'funding_rate': pd.Series(dtype=float)})
        args = (bars, [True, False, False, False], pd.Series(dtype=float), funding,
                '2025-01-01', '2025-01-01 00:20')
        metrics, closed, opened = replay(*args, risk_basis='initial', delayed_stop=True,
                                         stop_trigger_low=[100., 99., 100., 100.],
                                         liq_trigger_low=[100.]*4)
        self.assertEqual((len(closed), len(opened)), (1, 0))
        self.assertEqual(pd.Timestamp(closed[0]['stop_trigger_bar']), self.ts[1])
        self.assertEqual(pd.Timestamp(closed[0]['exit_ts']), self.ts[2])
        self.assertEqual(closed[0]['exit'], 95.)
        self.assertAlmostEqual(metrics['ledger_reconciliation_error'], 0.)
        _, closed, opened = replay(*args[:-1], '2025-01-01 00:10', risk_basis='initial', delayed_stop=True,
                                   stop_trigger_low=[100., 99., 100., 100.], liq_trigger_low=[100.]*4)
        self.assertEqual((len(closed), len(opened)), (0, 1))
        self.assertTrue(opened[0]['pending_stop'])

    def test_mark_liquidation_precedes_pending_stop(self):
        bars = pd.DataFrame({'ts': self.ts, 'open': [100.]*4, 'high': [101.]*4,
                             'low': [100., 99., 100., 100.], 'close': [100.]*4})
        funding = pd.DataFrame({'ts': pd.Series(dtype='int64'), 'funding_rate': pd.Series(dtype=float)})
        metrics, closed, _ = replay(bars, [True, False, False, False], pd.Series(dtype=float), funding,
                                    '2025-01-01', '2025-01-01 00:20', delayed_stop=True,
                                    stop_trigger_low=[100., 99., 100., 100.],
                                    liq_trigger_low=[100., 70., 100., 100.])
        self.assertEqual(closed[0]['reason'], 'liquidation_proxy')
        self.assertEqual(metrics['ambiguous_stop_liquidation_bars'], 1)

    def test_open_gap_liquidates_before_pending_stop_with_last_price_proxy(self):
        bars=pd.DataFrame({'ts':self.ts,'open':[100.,100.,70.,70.],
                           'high':[101.,101.,71.,71.],'low':[100.,99.,69.,69.],
                           'close':[100.,99.,70.,70.]})
        funding=pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        result,closed,_=replay(bars,[True,False,False,False],pd.Series(dtype=float),funding,
                               '2025-01-01','2025-01-01 00:20',delayed_stop=True)
        self.assertEqual(closed[0]['reason'],'liquidation_proxy')
        self.assertEqual(closed[0]['exit'],70.)
        self.assertEqual(result['proxy_liquidations'],1)
        self.assertAlmostEqual(result['ledger_reconciliation_error'],0)

    def test_mark_low_after_pending_exit_does_not_claim_open_order(self):
        bars=pd.DataFrame({'ts':self.ts,'open':[100.,100.,95.,98.],
                           'high':[101.]*4,'low':[100.,99.,94.,98.],'close':[100.,99.,95.,98.]})
        funding=pd.DataFrame({'ts':pd.Series(dtype='int64'),'funding_rate':pd.Series(dtype=float)})
        result,closed,_=replay(bars,[True,False,False,False],pd.Series(dtype=float),funding,
                               '2025-01-01','2025-01-01 00:20',delayed_stop=True,
                               stop_trigger_low=[100.,99.,100.,100.],liq_trigger_low=[100.,100.,70.,100.])
        self.assertEqual(closed[0]['reason'],'stop_next_open')
        self.assertEqual(result['pending_open_mark_liquidation_order_unknown'],1)


if __name__ == '__main__':
    unittest.main()
