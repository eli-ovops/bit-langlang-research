import unittest
import pandas as pd

from .forward_report import report


class ForwardNumericBounds(unittest.TestCase):
    def setUp(self):
        self.row=dict(trade_id='x',entry_time='2026-10-30T00:00:00Z',exit_time='2026-10-30T01:00:00Z',
            symbol='ETHUSDT',side='long',entry=100,stop=99.6,exit=103,qty=2,equity_at_entry=2000,
            fee_cost=.4,funding_cost=0,five_q_pass='1',stop_placed='1',added='0',reversed='0',plan_deviation='0')

    def check(self,rows):return report(pd.DataFrame(rows),'2026-10-30','2026-10-31')

    def test_finite_inputs_cannot_overflow_or_underflow_derived_risk(self):
        huge={**self.row,'entry':1e308,'stop':9.96e307,'exit':1e308,'qty':10000}
        tiny={**self.row,'entry':1e-300,'stop':.996e-300,'exit':1e-300,'qty':1e-100}
        self.assertEqual(self.check([huge])['status'],'INVALID')
        self.assertEqual(self.check([tiny])['status'],'INVALID')

    def test_aggregated_funding_and_reference_overflow_rejected(self):
        one={**self.row,'funding_cost':1e308}
        two={**one,'trade_id':'y','entry_time':'2026-10-30T02:00:00Z','exit_time':'2026-10-30T03:00:00Z'}
        self.assertEqual(self.check([one,two])['status'],'INVALID')
        ref={**self.row,'qty':100,'reference_entry':1e308,'reference_exit':1e307,'reference_source':'synthetic'}
        self.assertEqual(self.check([ref])['status'],'INVALID')


if __name__=='__main__':unittest.main()
