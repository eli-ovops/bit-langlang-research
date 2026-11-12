import unittest
import pandas as pd
from verify.market_2016_pivot_20261102 import pivots
from verify.market_support_2019on_20261103 import support
from verify.market_support_fallback_2014sp_20261103 import fallback

class Fallback(unittest.TestCase):
    def setUp(self):
        self.t=pd.Timestamp('2020-04-01',tz='UTC');idx=pd.date_range(self.t-pd.Timedelta(days=57),periods=65,freq='D');low=[100+abs(((i-1-3+5)%10)-5) for i in range(len(idx))];self.d=pd.DataFrame({'low':low,'high':[v+20 for v in low],'close':[v+10 for v in low],'good':True},index=idx)
    def test_late_latest_uses_previously_known_snapshot(self):
        r=pivots(self.d,self.t);self.assertEqual(support(self.d,self.t,r)['support_state'],'WAIT_CONFIRM');new,method=fallback(self.d,self.t,r);self.assertEqual(method,'FALLBACK_USED');self.assertLessEqual(pd.Timestamp(new['known']),self.t-pd.Timedelta(days=1));self.assertLess(new['level'] or 0,1000)
        self.d.loc[self.t:,'close']=1;self.assertEqual((new,method),fallback(self.d,self.t,r))
    def test_missing_history_blocks_fallback(self):
        r=pivots(self.d,self.t);self.d.loc[self.t-pd.Timedelta(days=57),'good']=False
        new,method=fallback(self.d,self.t,r);self.assertEqual(method,'FALLBACK_UNAVAILABLE');self.assertEqual(new['support_state'],'UNKNOWN')
    def test_already_decidable_unchanged(self):
        r=pivots(self.d,self.t-pd.Timedelta(days=1));old=support(self.d,self.t,r);self.assertNotEqual(old['support_state'],'WAIT_CONFIRM');self.assertEqual(fallback(self.d,self.t,r),(old,'UNCHANGED'))
if __name__=='__main__':unittest.main()
