import unittest
import pandas as pd
from verify.market_2016_pivot_20261102 import pivots
from verify.market_2016_pivot_correction_20261102 import classify
class TestPivots(unittest.TestCase):
 def setUp(self):
  self.start=pd.Timestamp('2016-01-01',tz='UTC');self.t=self.start+pd.Timedelta(days=56);idx=pd.date_range(self.start,periods=57,freq='D');self.d=pd.DataFrame({'high':[10.]*57,'low':[1.]*57,'good':[True]*57},index=idx)
  for i,p in [(10,15),(20,16)]:self.d.iloc[i,self.d.columns.get_loc('high')]=p
  for i,p in [(13,.5),(23,.6)]:self.d.iloc[i,self.d.columns.get_loc('low')]=p
 def test_known_time_and_future_perturb(self):
  a=pivots(self.d,self.t);self.assertEqual(a['swing'],'SWING_UP');self.assertEqual(a['h_new_known'],(self.start+pd.Timedelta(days=23)).isoformat());self.d.loc[self.t,'high']=999;self.assertEqual(a,pivots(self.d,self.t))
 def test_equal_high_is_not_pivot(self):
  self.d.iloc[21,self.d.columns.get_loc('high')]=16;self.assertEqual(pivots(self.d,self.t)['swing'],'UNKNOWN')
 def test_double_extreme_is_discarded(self):
  self.d.iloc[20,self.d.columns.get_loc('low')]=.1;self.assertEqual(pivots(self.d,self.t)['swing'],'UNKNOWN')
 def test_gap_marks_unknown(self):
  self.d.iloc[30,self.d.columns.get_loc('good')]=False;self.assertEqual(pivots(self.d,self.t)['swing'],'UNKNOWN')
 def test_stale_and_equal_boundary(self):
  self.assertEqual(classify(101,100,90),'ALREADY_ABOVE_ASOF');self.assertEqual(classify(89,100,90),'ALREADY_BELOW_ASOF');self.assertEqual(classify(100,100,90),'WITHIN_OR_EQUAL_ASOF')
if __name__=='__main__':unittest.main()
