import unittest

import pandas as pd

from .historical_pullback_candidate import pullback_pattern


class PullbackCandidateTests(unittest.TestCase):
    def test_confirmed_candle_requires_prior_down_candle_and_no_future(self):
        t=pd.date_range('2023-01-01',periods=24,freq='5min',tz='UTC')
        f=pd.DataFrame({'open':[100.]*24,'high':[102.]*24,'low':[98.]*24,'close':[101.]*24},index=t)
        f.iloc[20,f.columns.get_loc('close')]=99.
        self.assertTrue(pullback_pattern(f).iloc[21])
        prior=f.copy();prior.iloc[20,prior.columns.get_loc('close')]=101.
        self.assertFalse(pullback_pattern(prior).iloc[21])
        future=f.copy();future.iloc[22:,future.columns.get_loc('close')]=999.
        self.assertEqual(bool(pullback_pattern(f).iloc[21]),bool(pullback_pattern(future).iloc[21]))


if __name__=='__main__':unittest.main()
