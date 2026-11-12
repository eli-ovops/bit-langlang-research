import unittest
import pandas as pd
from verify.market_2017_pivot_guard_20261102 import guard,joint
class TestPivotGuard(unittest.TestCase):
 def setUp(self):
  self.start=pd.Timestamp('2017-01-01',tz='UTC');self.t=self.start+pd.Timedelta(days=5);self.d=pd.DataFrame({'close':[100.]*7,'good':[True]*7},index=pd.date_range(self.start,periods=7,freq='D'));self.r={'swing':'SWING_UP','h_new_price':110,'l_new_price':90,'h_new_known':self.start.isoformat(),'l_new_known':self.start.isoformat()}
 def test_break_then_recover_stays_stale(self):
  self.d.iloc[1,self.d.columns.get_loc('close')]=111
  x=guard(self.d,self.t,self.r);self.assertEqual(x['active'],'STALE_BROKEN_HIGH');self.assertEqual(x['stale_time_utc'],'2017-01-03T00:00:00+00:00')
 def test_equal_and_future_ignored(self):
  self.d.iloc[1,self.d.columns.get_loc('close')]=110;self.d.loc[self.t,'close']=1000;self.assertEqual(guard(self.d,self.t,self.r)['active'],'ACTIVE_UP')
 def test_unknown_for_gap_and_late_confirmation(self):
  self.d.iloc[2,self.d.columns.get_loc('good')]=False;self.assertEqual(guard(self.d,self.t,self.r)['active'],'UNKNOWN_HISTORY');self.r['h_new_known']=(self.t+pd.Timedelta(days=1)).isoformat();self.assertEqual(guard(self.d,self.t,self.r)['active'],'UNKNOWN_BOUNDARY')
 def test_cross_exchange_conflict_or_missing(self):
  a={'active':'ACTIVE_UP','long_relation':'DOWN'};b={'active':'ACTIVE_DOWN','long_relation':'DOWN'};self.assertEqual(joint(a,b),'UNKNOWN');b['active']='UNKNOWN_INPUT';self.assertEqual(joint(a,b),'UNKNOWN');b['active']='ACTIVE_UP';self.assertEqual(joint(a,b),'JOINT_POSSIBLE_UP');b['long_relation']='UP';self.assertEqual(joint(a,b),'NO_JOINT_CANDIDATE')
if __name__=='__main__':unittest.main()
