import unittest
import pandas as pd
from verify.market_hold2_2013_2024_20261102 import held,combine
class TestHold(unittest.TestCase):
 def setUp(self):
  self.t=pd.Timestamp('2024-01-10',tz='UTC');self.d=pd.DataFrame({'close':[100.,111.,112.,900.],'good':[True]*4},index=pd.date_range(self.t-pd.Timedelta(days=3),periods=4,freq='D'));self.r={'position':'ABOVE','h_new_known':(self.t-pd.Timedelta(days=2)).isoformat(),'h_new_price':110.}
 def test_confirm_exact_then_hold(self):self.assertEqual(held(self.d,self.t,self.r),'HELD_UP_2')
 def test_no_hindsight_confirmation(self):
  self.r['h_new_known']=(self.t-pd.Timedelta(days=1)).isoformat();self.assertEqual(held(self.d,self.t,self.r),'WAIT_CONFIRM')
 def test_equality_and_future(self):
  self.d.loc[self.t-pd.Timedelta(days=2),'close']=110.;self.assertEqual(held(self.d,self.t,self.r),'OUTSIDE_UNHELD');self.d.loc[self.t,'close']=-999.;self.assertEqual(held(self.d,self.t,self.r),'OUTSIDE_UNHELD')
 def test_gap_down_and_joint(self):
  self.d.loc[self.t-pd.Timedelta(days=1),'good']=False;self.assertEqual(held(self.d,self.t,self.r),'UNKNOWN');self.d.good=True;self.d.loc[self.t-pd.Timedelta(days=2):self.t-pd.Timedelta(days=1),'close']=[89.,88.];self.r={'position':'BELOW','l_new_known':(self.t-pd.Timedelta(days=2)).isoformat(),'l_new_price':90.};self.assertEqual(held(self.d,self.t,self.r),'HELD_DOWN_2');self.assertEqual(combine('HELD_UP_2','UNKNOWN'),'UNKNOWN');self.assertEqual(combine('HELD_UP_2','HELD_DOWN_2'),'DISAGREE')
if __name__=='__main__':unittest.main()
