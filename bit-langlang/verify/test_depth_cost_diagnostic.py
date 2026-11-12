import unittest
from decimal import Decimal

from verify.depth_cost_diagnostic import analyze, positive


class DepthCostDiagnosticTest(unittest.TestCase):
    def test_partial_level_and_cost_decomposition(self):
        result = analyze({'asks': [['100', '5'], ['101', '10']],
                          'bids': [['99', '4'], ['98', '10']]})
        self.assertEqual(result['quantity_eth'], Decimal('7.5'))
        self.assertAlmostEqual(result['buy_vwap'], Decimal('752.5') / Decimal('7.5'), places=24)
        self.assertAlmostEqual(result['sell_vwap'], Decimal('739') / Decimal('7.5'), places=24)
        self.assertEqual(result['buy_levels'], 2)
        self.assertEqual(result['sell_levels'], 2)
        expected = Decimal('752.5') * Decimal('1.0002') - Decimal('739') * Decimal('0.9998')
        expected += (Decimal('752.5') * Decimal('1.0002') + Decimal('739') * Decimal('0.9998')) * Decimal('.0005')
        self.assertEqual(result['illustrative_cost_usdt_excluding_funding'], expected)
        self.assertEqual(result['spread_usdt'] + result['additional_depth_usdt'], Decimal('13.5'))

    def test_insufficient_depth_is_unknown(self):
        result = analyze({'asks': [['100', '1']], 'bids': [['99', '20']]})
        self.assertEqual(result['status'], 'UNKNOWN_DEPTH')
        self.assertNotIn('illustrative_cost_usdt_excluding_funding', result)

    def test_invalid_book_and_number_rejected(self):
        for value in ['NaN', 'Infinity', '-1', '0', 'not-a-number']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                positive(value)
        for book in [
            {'asks': [['100', '10']], 'bids': [['100', '10']]},
            {'asks': [['100', '10'], ['100', '1']], 'bids': [['99', '10']]},
            {'asks': [['100', '10']], 'bids': [['98', '10'], ['99', '10']]},
        ]:
            with self.subTest(book=book), self.assertRaises(ValueError):
                analyze(book)


if __name__ == '__main__':
    unittest.main()
