"""Guard as-of close against collisions with subsequent segment closes."""
import unittest
from pathlib import Path
import pandas as pd
class PriorRangeAudit(unittest.TestCase):
 def test_segment_asof_matches_daily_without_future_close(self):
  for label in ('2023q3','2025q2'):
   p=Path('data/verify/cycle-'+label+'-priorrange-20261104-02');daily=pd.read_csv(p/'daily.csv').set_index(['source','as_of_utc']);segments=pd.read_csv(p/'segments.csv').set_index(['source','start_utc']);cols=['prev_close','prior_last_close','old28_low','old28_high','up_close_days','down_close_days','current_position'];pd.testing.assert_frame_equal(daily.loc[segments.index,cols].reset_index(drop=True),segments[cols].reset_index(drop=True),check_dtype=False);self.assertTrue((segments.prev_close==segments.prior_last_close).all());self.assertTrue((segments.segment_end_close!=segments.prior_last_close).any())
if __name__=='__main__':unittest.main()
