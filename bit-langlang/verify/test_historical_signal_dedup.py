import unittest

import numpy as np
import pandas as pd

from .historical_signal_dedup import controls,deduplicate


class SignalDedupTests(unittest.TestCase):
    def test_causal_boundaries_and_cross_day(self):
        t=pd.Timestamp('2023-01-01T23:50:00Z').value;m=60*10**9
        source=[t,t+5*m,t+29*m,t+30*m,t+59*m,t+60*m]
        self.assertEqual(deduplicate(source),[t,t+30*m,t+60*m])
        self.assertEqual(deduplicate(source[:4]),deduplicate(source)[:2])
        with self.assertRaises(ValueError):deduplicate([t+1,t])

    def test_coin_independence_and_control_window(self):
        t=pd.Timestamp('2023-01-02T12:00:00Z');m=60*10**9
        self.assertEqual(deduplicate([t.value,t.value+10*m]),[t.value])
        self.assertEqual(deduplicate([t.value+10*m]),[t.value+10*m])
        market=pd.date_range(t.floor('D'),t.floor('D')+pd.Timedelta(hours=23,minutes=55),freq='5min')
        c=controls(t,'BTC',market,np.array([(t-pd.Timedelta(minutes=40)).value],dtype=np.int64))
        self.assertEqual(c['count'],8);self.assertEqual(c['hits'],1);self.assertEqual(c['expected'],.125)


if __name__=='__main__':unittest.main()
