import unittest

import pandas as pd

from .historical_behavior_compare import past_features
from .historical_ten_behavior_candidate import behavior_pattern


class HistoricalBehaviorTests(unittest.TestCase):
    def test_candidate_observes_only_current_completed_and_prior_bars(self):
        idx=pd.date_range('2023-01-01',periods=24,freq='5min',tz='UTC')
        f=pd.DataFrame({'open':[100.]*24,'high':[102.]*24,'low':[98.]*24,'close':[101.]*24},index=idx)
        self.assertTrue(behavior_pattern(f).iloc[21])
        changed=f.copy();changed.iloc[22:,changed.columns.get_loc('high')]=999
        self.assertEqual(bool(behavior_pattern(f).iloc[21]),bool(behavior_pattern(changed).iloc[21]))
        changed=f.copy();changed.iloc[21,changed.columns.get_loc('close')]=99
        self.assertFalse(behavior_pattern(changed).iloc[21])

    def test_feature_does_not_use_future_or_signal_bar_for_prior_range(self):
        idx=pd.date_range('2023-01-01',periods=60,freq='5min',tz='UTC')
        f=pd.DataFrame({'open':[100.]*60,'high':[101.]*60,'low':[99.]*60,'close':[100.]*60},index=idx)
        expected=past_features(f).iloc[50].copy()
        changed=f.copy();changed.iloc[51:,changed.columns.get_loc('high')]=1000.
        pd.testing.assert_series_equal(expected,past_features(changed).iloc[50])
        changed=f.copy();changed.iloc[50,changed.columns.get_loc('high')]=1000.
        self.assertEqual(past_features(changed).iloc[50].range_position,expected.range_position)


if __name__=='__main__':unittest.main()
