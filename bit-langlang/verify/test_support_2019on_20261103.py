import unittest
import pandas as pd
from verify.market_support_2019on_20261103 import support,first_break

class Support(unittest.TestCase):
    def setUp(self):
        self.t=pd.Timestamp('2020-02-01',tz='UTC');self.d=pd.DataFrame({'close':110.,'good':True},index=pd.date_range(self.t-pd.Timedelta(days=5),periods=12,freq='D'));self.r={'swing':'SWING_UP','l_new_price':100.,'l_new_known':(self.t-pd.Timedelta(days=4)).isoformat()}
    def test_prior_break_stays_broken_after_recovery(self):
        self.assertEqual(support(self.d,self.t,self.r)['support_state'],'PRIOR_UNBROKEN_ABOVE')
        self.d.loc[self.t-pd.Timedelta(days=3),'close']=99
        self.assertEqual(support(self.d,self.t,self.r)['support_state'],'PRIOR_BROKEN_ABOVE')
        self.d.loc[self.t-pd.Timedelta(days=1),'close']=100
        self.assertEqual(support(self.d,self.t,self.r)['support_state'],'PRIOR_BROKEN_EQUAL')
    def test_confirmation_and_missing(self):
        self.r['l_new_known']=self.t.isoformat();self.assertEqual(support(self.d,self.t,self.r)['support_state'],'WAIT_CONFIRM')
        self.r['l_new_known']=(self.t-pd.Timedelta(days=4)).isoformat();self.d.loc[self.t-pd.Timedelta(days=3),'good']=False
        self.assertEqual(support(self.d,self.t,self.r)['support_state'],'UNKNOWN')
    def test_future_and_first_strict_break(self):
        before=support(self.d,self.t,self.r);self.d.loc[self.t:,'close']=100
        self.assertEqual(before,support(self.d,self.t,self.r));self.d.loc[self.t+pd.Timedelta(days=1),'close']=99
        self.assertEqual(first_break(self.d,self.t,100)[:2],('BREAK',(self.t+pd.Timedelta(days=2)).isoformat()))
        self.d.loc[self.t,'good']=False;self.assertEqual(first_break(self.d,self.t,100)[0],'UNKNOWN_INCOMPLETE')
if __name__=='__main__':unittest.main()
