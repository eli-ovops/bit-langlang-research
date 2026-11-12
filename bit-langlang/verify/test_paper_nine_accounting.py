import copy
import unittest
from .paper_nine_accounting import evaluate


class NinePaperAccountingTests(unittest.TestCase):
    def setUp(self):
        self.trade = {'trade_id':'synthetic-1', 'symbol':'SOLUSDT', 'side':'long',
            'entry_time':'2026-11-01T01:00:00Z', 'entry':'100', 'stop':'99.6',
            'qty':'20', 'equity_at_entry':'2000', 'entry_fee':'1', 'funding_cost':'0.2',
            'exit_time':'2026-11-01T03:00:00Z', 'exit':'100.8', 'exit_fee':'1.008'}
        self.base = {'start_utc':'2026-11-01T00:00:00Z', 'as_of_utc':'2026-11-01T04:00:00Z',
                     'trades':[self.trade]}

    def test_cost_risk_and_account_are_conditional(self):
        result = evaluate(self.base)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['records'][0]['initial_price_risk_usdt'], '8.0')
        self.assertEqual(result['records'][0]['net_pnl_usdt'], '13.792')
        self.assertEqual(result['records'][0]['net_R'], '1.724')
        self.assertEqual(result['closed_cash_usdt_assuming_complete'], '2013.792')

    def test_funding_missing_is_unknown_not_zero(self):
        self.trade['funding_cost'] = None
        result = evaluate(self.base)
        self.assertIsNone(result['records'][0]['net_pnl_usdt'])
        self.assertIsNone(result['closed_cash_usdt_assuming_complete'])

    def test_open_positions_must_not_overlap(self):
        duplicate = copy.deepcopy(self.trade)
        duplicate['trade_id'] = 'synthetic-2'
        duplicate['entry_time'] = '2026-11-01T02:00:00Z'
        self.base['trades'].append(duplicate)
        self.assertEqual(evaluate(self.base)['status'], 'INVALID')

    def test_size_risk_and_fees_are_enforced(self):
        for update in ({'qty':'21', 'entry_fee':'1.05'}, {'stop':'99.4'}, {'entry_fee':'0'},
                       {'exit_fee':'0'}, {'qty':'NaN'}, {'symbol':'ETHUSDT'}):
            with self.subTest(update=update):
                row = {**self.trade, **update}
                self.assertEqual(evaluate({**self.base,'trades':[row]})['status'], 'INVALID')

    def test_open_stale_and_missing_funding_cannot_pass(self):
        trade = {k:v for k,v in self.trade.items() if k not in ('exit_time','exit','exit_fee')}
        trade.update(mark_time='2026-11-01T01:30:00Z', mark_price='100.1', mark_source='synthetic', funding_cost=None)
        result = evaluate({**self.base, 'trades':[trade]})
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertIsNone(result['records'][0]['net_to_mark_usdt'])
        self.assertTrue(any('STALE' in x for x in result['limitations']))

    def test_observed_stop_and_target_do_not_imply_a_fill(self):
        trade = {k:v for k,v in self.trade.items() if k not in ('exit_time','exit','exit_fee')}
        trade.update(mark_time='2026-11-01T03:55:00Z', mark_price='99.5', mark_source='synthetic')
        stopped = evaluate({**self.base, 'trades':[trade]})
        self.assertEqual(stopped['status'], 'UNKNOWN')
        self.assertTrue(stopped['records'][0]['mark_at_or_below_stop'])
        self.assertFalse(stopped['records'][0]['mark_at_or_above_target'])
        self.assertTrue(any('execution UNKNOWN' in x for x in stopped['limitations']))
        trade['mark_price'] = '100.8'
        target = evaluate({**self.base, 'trades':[trade]})
        self.assertFalse(target['records'][0]['mark_at_or_below_stop'])
        self.assertTrue(target['records'][0]['mark_at_or_above_target'])
        self.assertEqual(target['status'], 'UNKNOWN')

    def test_dates_and_duplicate_ids(self):
        for payload in ({**self.base, 'as_of_utc':'2099-01-01T00:00:00Z'},
                        {**self.base, 'trades':[self.trade, self.trade]},
                        {**self.base, 'trades':[None]}):
            with self.subTest(payload=payload):
                self.assertEqual(evaluate(payload)['status'], 'INVALID')

    def test_empty_ledger_is_not_a_validated_run(self):
        result = evaluate({**self.base, 'trades':[]})
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertIn('NO_TRADE_EVIDENCE', result['limitations'])


if __name__ == '__main__':
    unittest.main()
