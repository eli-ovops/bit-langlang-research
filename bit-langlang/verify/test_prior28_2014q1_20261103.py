import unittest
import pandas as pd
from verify.market_prior28_2014q1_20261103 import classify,combine
from verify.market_2023_return_28d_20261102 import returned

class Prior28(unittest.TestCase):
    def setUp(self):
        self.t=pd.Timestamp('2020-02-01',tz='UTC')
        self.d=pd.DataFrame({'high':110.,'low':90.,'close':100.,'good':True},index=pd.date_range(self.t-pd.Timedelta(days=29),periods=36,freq='D'))
    def test_current_excluded_equal_and_real_break(self):
        d=self.d.copy();d.loc[self.t-pd.Timedelta(days=1),['high','close']]=[125,120]
        r=classify(d,self.t);self.assertEqual(r['ref_high'],110);self.assertEqual(r['range_state'],'ABOVE')
        d.loc[self.t-pd.Timedelta(days=1),'close']=110;self.assertEqual(classify(d,self.t)['range_state'],'INSIDE')
        d.loc[self.t-pd.Timedelta(days=1),['low','close']]=[80,85];self.assertEqual(classify(d,self.t)['range_state'],'BELOW')
    def test_missing_future_and_joint(self):
        before=classify(self.d,self.t);self.d.loc[self.t:,'high']=100000;self.assertEqual(before,classify(self.d,self.t))
        self.d.loc[self.t-pd.Timedelta(days=20),'good']=False;self.assertEqual(classify(self.d,self.t)['range_state'],'UNKNOWN')
        self.assertEqual(combine('ABOVE','BELOW'),'DISAGREE');self.assertEqual(combine('UNKNOWN','BELOW'),'UNKNOWN')
    def test_return_equality_then_cross(self):
        self.d.loc[self.t,'close']=110;self.d.loc[self.t+pd.Timedelta(days=1),'close']=109
        status,when,_=returned(self.d,self.t,'UPPER_BREAK',110,7)
        self.assertEqual(status,'RETURN');self.assertEqual(when,(self.t+pd.Timedelta(days=2)).isoformat())
        self.d.loc[self.t,'good']=False;self.assertEqual(returned(self.d,self.t,'UPPER_BREAK',110,7)[0],'UNKNOWN_INCOMPLETE')
if __name__=='__main__':unittest.main()
