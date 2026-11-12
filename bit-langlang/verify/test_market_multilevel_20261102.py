import unittest
import pandas as pd
from .market_multilevel_20261102 import evaluate
from .market_multilevel_guard_20261102 import guard
from .market_season_research_20261102 import aggregates,SOURCE

def frame(index,old,new,midpoint=8):
 n=len(index)//2;return pd.DataFrame([{'high':old[0],'low':old[1],'close':midpoint,'good':True}]*n+[{'high':new[0],'low':new[1],'close':midpoint,'good':True}]*n,index=index)
class LayersTest(unittest.TestCase):
 def setUp(self):
  self.t=pd.Timestamp('2026-03-01',tz='UTC');self.di=pd.date_range(self.t-pd.Timedelta(days=28),periods=28,freq='D');self.hi=pd.date_range(self.t-pd.Timedelta(days=8),periods=48,freq='4h')
 def test_layer_preserved_on_partial_loss(self):
  d=frame(self.di,(10,2),(12,4));h=frame(self.hi,(10,2),(12,4));self.assertEqual(evaluate(d,h,self.t)['season'],'SUMMER')
  out=evaluate(d.iloc[1:],h,self.t);self.assertEqual((out['season'],out['big_relation'],out['small_relation']),('UNKNOWN','UNKNOWN','UP'))
  out=evaluate(d,h.iloc[1:],self.t);self.assertEqual((out['season'],out['big_relation'],out['small_relation']),('UNKNOWN','UP','UNKNOWN'))
 def test_conflicts_stay_unknown_after_guard(self):
  d=frame(self.di,(10,2),(12,4));h=frame(self.hi,(10,2),(8,1));v=evaluate(d,h,self.t);self.assertTrue(v['conflict']);self.assertEqual(v['season'],'AUTUMN');self.assertEqual(guard(v['season'],v['big_relation'],v['small_relation'])[0],'UNKNOWN')
  d=frame(self.di,(10,2),(8,1));h=frame(self.hi,(10,2),(12,4));v=evaluate(d,h,self.t);self.assertTrue(v['conflict']);self.assertEqual(guard(v['season'],v['big_relation'],v['small_relation'])[0],'UNKNOWN')
 def test_future_price_and_missing_bar(self):
  f=pd.read_csv(SOURCE);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time');d,h=aggregates(f);before=evaluate(d,h,self.t)
  x=f.copy();x.loc[x.index>=self.t,['open','high','low','close']]*=1.7;d2,h2=aggregates(x);self.assertEqual(before,evaluate(d2,h2,self.t))
  x=f.drop(index=self.t-pd.Timedelta(days=20));d3,h3=aggregates(x);after=evaluate(d3,h3,self.t);self.assertEqual(after['season'],'UNKNOWN');self.assertFalse(after['big_valid']);self.assertTrue(after['small_valid'])
if __name__=='__main__':unittest.main()
