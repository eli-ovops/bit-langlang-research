import unittest
import pandas as pd
from verify.cycle_pivot_asof_20261105 import crossing
class ConfirmedPivotTiming(unittest.TestCase):
 def test_confirmation_instant_has_no_post_confirm_daily_close(self):
  known=pd.Timestamp('2023-01-03',tz='UTC');d=pd.DataFrame({'close':[90.,110.],'good':[True,True]},index=pd.date_range('2023-01-02',periods=2,tz='UTC'))
  self.assertEqual(crossing(d,known,known,100,'low'),(None,None,0))
  self.assertEqual(crossing(d,known,known+pd.Timedelta(days=1),100,'low'),(False,None,1))
  d.loc[known,'close']=90.;self.assertEqual(crossing(d,known,known+pd.Timedelta(days=1),100,'low'),(True,'2023-01-04T00:00:00+00:00',1))
 def test_missing_following_day_does_not_mean_unbroken(self):
  t=pd.Timestamp('2023-01-03',tz='UTC');d=pd.DataFrame({'close':[90.],'good':[True]},index=pd.DatetimeIndex([t]));self.assertIsNone(crossing(d,t,t+pd.Timedelta(days=2),100,'low')[0])
if __name__=='__main__':unittest.main()
