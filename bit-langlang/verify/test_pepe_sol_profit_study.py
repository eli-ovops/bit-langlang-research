import unittest
import pandas as pd
from .pepe_sol_profit_study import extrema

class ExtremesTests(unittest.TestCase):
    def test_endpoints_only_and_sides(self):
        empty=pd.DataFrame(columns=['high','low'])
        self.assertEqual(extrema(100,90,'多',empty),(0.0,-9.999999999999998))
        self.assertAlmostEqual(extrema(100,90,'空',empty)[0],10)
        self.assertEqual(extrema(100,90,'空',empty)[1],0)
    def test_fully_held_bars_and_sign(self):
        mid=pd.DataFrame({'high':[110,105],'low':[95,90]})
        self.assertAlmostEqual(extrema(100,102,'多',mid)[0],10)
        self.assertAlmostEqual(extrema(100,102,'多',mid)[1],-10)
        self.assertAlmostEqual(extrema(100,102,'空',mid)[0],10)
        self.assertAlmostEqual(extrema(100,102,'空',mid)[1],-10)
    def test_invalid_side_or_price(self):
        with self.assertRaises(ValueError):extrema(0,1,'多',pd.DataFrame())
        with self.assertRaises(ValueError):extrema(1,1,'?',pd.DataFrame())
if __name__=='__main__':unittest.main()
