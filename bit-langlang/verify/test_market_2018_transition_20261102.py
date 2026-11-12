import unittest
import numpy as np
import pandas as pd
from verify.market_2018_transition_20261102 import event,read,DATA
from verify.market_2020_cross_20261102 import evaluate_extended

class TestTransition(unittest.TestCase):
 def setUp(self):
  self.t=pd.Timestamp('2018-01-01',tz='UTC')
  self.d=pd.DataFrame({'close':[100.]*28,'good':[True]*28},index=pd.date_range(self.t,periods=28,freq='D'))
 def test_equal_and_full_period(self):
  self.d.iloc[0,self.d.columns.get_loc('close')]=110
  self.d.iloc[1,self.d.columns.get_loc('close')]=90
  self.assertEqual(event(self.d,self.t,110,90)['status'],'UNRESOLVED_28D')
 def test_first_break_and_close_timestamp(self):
  self.d.loc[self.t+pd.Timedelta(days=2),'close']=89
  self.d.loc[self.t+pd.Timedelta(days=3),'close']=111
  x=event(self.d,self.t,110,90)
  self.assertEqual((x['status'],x['observed_days'],x['event_time_utc']),('LOWER_BREAK',3,'2018-01-04T00:00:00+00:00'))
 def test_missing_before_break_and_after_break(self):
  self.d.loc[self.t+pd.Timedelta(days=2),'good']=False
  self.d.loc[self.t+pd.Timedelta(days=3),'close']=111
  self.assertEqual(event(self.d,self.t,110,90)['status'],'UNKNOWN_INCOMPLETE')
  self.d.loc[self.t+pd.Timedelta(days=1),'close']=111
  self.assertEqual(event(self.d,self.t,110,90)['status'],'UPPER_BREAK')
 def test_short_data(self):
  self.assertEqual(event(self.d.iloc[:10],self.t,110,90)['status'],'UNKNOWN_INCOMPLETE')
 def test_future_cannot_change_asof(self):
  d,h=read(DATA/'binance-spot-4h.csv.gz');t=pd.Timestamp('2018-04-16',tz='UTC');a=evaluate_extended(d,h,t)
  d2=d.copy();h2=h.copy();d2.loc[d2.index>=t,['high','low','close']]*=3;h2.loc[h2.index>=t,['high','low','close']]*=3
  self.assertEqual(a,evaluate_extended(d2,h2,t))
 def test_missing_long_does_not_invalidate_shorter_layers(self):
  d,h=read(DATA/'binance-spot-4h.csv.gz');t=pd.Timestamp('2018-04-16',tz='UTC');d=d.copy();d.loc[t-pd.Timedelta(days=40),'good']=False
  x=evaluate_extended(d,h,t)
  self.assertTrue(x['big_valid'] and x['small_valid']);self.assertFalse(x['long_valid']);self.assertEqual(x['spring_watch'],'UNKNOWN')
if __name__=='__main__':unittest.main()
