"""Synthetic end-to-end invariants for v0.1; never a market signal or order."""
import copy
import unittest
from decimal import Decimal, ROUND_DOWN
from .paper_nine_accounting import evaluate, SYMBOLS


def synthetic_market(bars):
    assert len(bars) == 35
    found = []
    for i in range(28, 35):
        b = max(r['high'] for r in bars[i-28:i])
        if bars[i]['close'] > b:
            found.append(b)
    return bool(found and bars[-1]['close'] > found[-1] and
                max(x['high'] for x in bars[-7:]) > bars[-1]['close'])


def synthetic_ranking(btc, assets):
    if set(assets) != SYMBOLS or len(btc) != 31 or any(len(x) != 31 for x in assets.values()):
        return None
    market = btc[-1]/btc[0]-1
    ordered = sorted(((symbol, x[-1]/x[0]-1-market) for symbol, x in assets.items()),
                     key=lambda x: (-x[1], x[0]))
    return ordered[0][0] if ordered[0][1] > 0 else None


class SyntheticPath(unittest.TestCase):
    def setUp(self):
        D = Decimal
        self.bars = [{'high':D(100), 'low':D(90), 'close':D(95)} for _ in range(35)]
        self.bars[31] = {'high':D(110), 'low':D(99), 'close':D(105)}
        self.bars[32] = {'high':D(109), 'low':D(104), 'close':D(106)}
        self.bars[33] = {'high':D(109), 'low':D(103), 'close':D(104)}
        self.bars[34] = {'high':D(108), 'low':D(103), 'close':D(104)}
        self.btc = [D(100)]*30+[D(110)]
        self.assets = {s:[D(100)]*30+[D(105)] for s in SYMBOLS}
        self.assets['SOLUSDT'][-1] = D(120)

    def test_synthetic_end_to_end_and_accounting(self):
        D = Decimal
        self.assertTrue(synthetic_market(self.bars))
        symbol = synthetic_ranking(self.btc, self.assets)
        self.assertEqual(symbol, 'SOLUSDT')
        # Two fictional fully closed 4-hour bars: prior red, latest close > prior high.
        prior = {'open':D(100), 'high':D(101), 'low':D(99), 'close':D('99.5')}
        latest = {'open':D('99.6'), 'high':D(102), 'low':D('99.4'), 'close':D('101.5')}
        self.assertTrue(prior['close'] < prior['open'] and latest['close'] > prior['high'])
        # Quote timestamps are synthetic and deliberately strictly after signal availability.
        signal = '2026-11-01T00:00:00+00:00'
        capture = '2026-11-01T00:00:01+00:00'
        entry_time = '2026-11-01T00:00:02+00:00'
        self.assertLess(signal, capture)
        self.assertLess(capture, entry_time)
        entry = D('101.6') * D('1.0002')
        stop = prior['low']
        qty = min(D(10)/(entry-stop), D(2000)/entry).quantize(D('.001'), rounding=ROUND_DOWN)
        target = entry+2*(entry-stop)
        exit_ref = D(107)
        self.assertGreaterEqual(exit_ref, target)
        exit_price = exit_ref*D('.9998')
        entry_fee = entry*qty*D('.0005')
        exit_fee = exit_price*qty*D('.0005')
        funding = qty*D(103)*D('.0001')
        payload = {'start_utc':'2026-11-01T00:00:00Z','as_of_utc':'2026-11-01T09:00:00Z',
          'trades':[{'trade_id':'SYNTHETIC-ONLY','symbol':symbol,'side':'long','entry_time':entry_time,
            'exit_time':'2026-11-01T08:30:00Z','entry':str(entry),'stop':str(stop),'exit':str(exit_price),
            'qty':str(qty),'equity_at_entry':'2000','entry_fee':str(entry_fee),
            'exit_fee':str(exit_fee),'funding_cost':str(funding)}]}
        result = evaluate(payload)
        self.assertEqual(result['status'], 'UNKNOWN')
        expected = (exit_price-entry)*qty-entry_fee-exit_fee-funding
        self.assertEqual(D(result['records'][0]['net_pnl_usdt']), expected)
        self.assertLessEqual((entry-stop)*qty,D(10))
        self.assertLessEqual(entry*qty,D(2000))
        self.assertTrue(any('execution' in x for x in result['limitations']))

    def test_incomplete_universe_cannot_rank(self):
        del self.assets['LITUSDT']
        self.assertIsNone(synthetic_ranking(self.btc,self.assets))

    def test_t0_is_unchanged_when_future_is_perturbed(self):
        first = synthetic_market(self.bars)
        all_data = copy.deepcopy(self.bars)+[{'high':Decimal('999999'),'low':Decimal(1),'close':Decimal(3)}]
        self.assertEqual(first, synthetic_market(all_data[:35]))


if __name__ == '__main__':
    unittest.main()
