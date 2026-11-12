import unittest
import pandas as pd
from verify.market_2023_return_28d_20261102 import returned
class TestReturn(unittest.TestCase):
 def setUp(self):
  self.t=pd.Timestamp('2023-01-01',tz='UTC');self.d=pd.DataFrame({'close':[110.]*28,'good':[True]*28},index=pd.date_range(self.t,periods=28,freq='D'))
 def test_equality_and_delayed_return(self):
  self.d.loc[self.t,'close']=100;self.d.loc[self.t+pd.Timedelta(days=7),'close']=99
  self.assertEqual(returned(self.d,self.t,'UPPER_BREAK',100,7)[0],'NO_RETURN')
  self.assertEqual(returned(self.d,self.t,'UPPER_BREAK',100,28)[:2],('RETURN','2023-01-09T00:00:00+00:00'))
 def test_gap_before_or_after_evidence(self):
  self.d.loc[self.t+pd.Timedelta(days=2),'good']=False;self.d.loc[self.t+pd.Timedelta(days=3),'close']=99
  self.assertEqual(returned(self.d,self.t,'UPPER_BREAK',100,28)[0],'UNKNOWN_INCOMPLETE')
  self.d.loc[self.t+pd.Timedelta(days=1),'close']=99
  self.assertEqual(returned(self.d,self.t,'UPPER_BREAK',100,28)[0],'RETURN')
 def test_lower_break_return(self):
  self.d['close']=90.;self.d.iloc[1,self.d.columns.get_loc('close')]=101
  self.assertEqual(returned(self.d,self.t,'LOWER_BREAK',100,7)[:2],('RETURN','2023-01-03T00:00:00+00:00'))
if __name__=='__main__':unittest.main()
