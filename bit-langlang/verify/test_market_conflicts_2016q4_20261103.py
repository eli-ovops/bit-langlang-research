import unittest
import pandas as pd
from verify.market_conflicts_2016q4_20261103 import relation, location
from verify.market_2018_transition_20261102 import read
from verify.market_2020_cross_20261102 import evaluate_extended

class Conflicts(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(relation('UP', 'DOWN'), 'OPPOSING')
        self.assertEqual(relation('DOWN', 'UP'), 'OPPOSING')
        self.assertEqual(relation('UP', 'UP'), 'ALIGNED')
        self.assertEqual(relation('INSIDE', 'UP'), 'NON_DIRECTIONAL')
        self.assertEqual(relation('UNKNOWN', 'UP'), 'UNKNOWN')
        self.assertEqual(location('ABOVE', 105, 90, 110), 'SMALL_OUTSIDE_LARGE_INSIDE')
        self.assertEqual(location('ABOVE', 111, 90, 110), 'LARGE_OUTSIDE')
        self.assertEqual(location('UNKNOWN', 105, 90, 110), 'UNKNOWN')

    def test_actual_results_and_no_future_leakage(self):
        x = pd.read_csv('data/verify/market-conflicts-2016q4-20261103-01/conflicts.csv')
        self.assertEqual(len(x), 26)
        for r in x.itertuples():
            if 'UNKNOWN' in (r.big, r.small): expected = 'UNKNOWN'
            elif r.big not in ('UP','DOWN') or r.small not in ('UP','DOWN'): expected = 'NON_DIRECTIONAL'
            elif r.big == r.small: expected = 'ALIGNED'
            else: expected = 'OPPOSING'
            self.assertEqual(r.layers, expected)
            if r.position_context != 'UNKNOWN': self.assertTrue(r.fixed_low <= r.price <= r.fixed_high)
        d,h = read('data/market/btc-2016q4-usd-cross-20261102-01/bitstamp-4h.csv.gz')
        t = pd.Timestamp('2016-11-14',tz='UTC'); before=evaluate_extended(d,h,t)
        d2=d.copy();h2=h.copy();d2.loc[d2.index>=t,['high','low','close']]*=2;h2.loc[h2.index>=t,['high','low','close']]*=2
        self.assertEqual(before,evaluate_extended(d2,h2,t))

if __name__ == '__main__': unittest.main()
