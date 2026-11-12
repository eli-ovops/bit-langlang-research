import unittest
import pandas as pd
from verify.market_2015_position_20261102 import location,combine
from verify.market_2017_pivot_guard_20261102 import guard
class TestPosition(unittest.TestCase):
 def setUp(self):
  self.a=pd.Timestamp('2015-01-01',tz='UTC');self.t=self.a+pd.Timedelta(days=5);self.d=pd.DataFrame({'close':[100.]*7,'good':[True]*7},index=pd.date_range(self.a,periods=7,freq='D'));self.r={'swing':'SWING_UP','h_new_price':110.,'l_new_price':90.,'h_new_known':self.a.isoformat(),'l_new_known':self.a.isoformat()}
 def test_boundary_equal_and_future(self):
  self.d.loc[self.t-pd.Timedelta(days=1),'close']=110.;self.d.loc[self.t,'close']=900.;self.assertEqual(location(self.d,self.t,self.r),'INSIDE')
 def test_stale_recovered_stays_stale(self):
  self.d.iloc[1,self.d.columns.get_loc('close')]=111.;self.assertEqual(guard(self.d,self.t,self.r)['active'],'STALE_BROKEN_HIGH');self.assertEqual(location(self.d,self.t,self.r),'INSIDE')
 def test_missing_and_no_swing(self):
  self.d.loc[self.t-pd.Timedelta(days=1),'good']=False;self.assertEqual(location(self.d,self.t,self.r),'UNKNOWN');self.r['swing']='UNKNOWN';self.assertEqual(location(self.d,self.t,self.r),'UNKNOWN')
 def test_cross_disagreement_and_missing(self):
  self.assertEqual(combine('ABOVE','BELOW'),'DISAGREE');self.assertEqual(combine('ABOVE','UNKNOWN'),'UNKNOWN');self.assertEqual(combine('ABOVE','ABOVE'),'JOINT_ABOVE')
if __name__=='__main__':unittest.main()
