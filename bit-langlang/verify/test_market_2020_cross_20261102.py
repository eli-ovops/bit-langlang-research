import unittest
import pandas as pd
from .market_2020_cross_20261102 import evaluate_extended,sources

def frame(index,windows):
 rows=[]
 for count,hi,lo,close in windows:rows += [{'high':hi,'low':lo,'close':close,'good':True}]*count
 return pd.DataFrame(rows,index=index)
class CrossRegimeTest(unittest.TestCase):
 def setUp(self):
  self.t=pd.Timestamp('2020-07-01',tz='UTC');self.di=pd.date_range(self.t-pd.Timedelta(days=56),periods=56,freq='D');self.hi=pd.date_range(self.t-pd.Timedelta(days=8),periods=48,freq='4h')
 def test_spring_candidate_and_autumn_unconfirmed(self):
  d=frame(self.di,[(28,100,50,70),(14,90,60,80),(14,85,65,80)]);h=frame(self.hi,[(24,80,65,70),(24,85,70,75)]);o=evaluate_extended(d,h,self.t);self.assertEqual((o['season'],o['spring_watch']),('SPRING','YES'))
  d=frame(self.di,[(28,70,30,60),(14,80,50,65),(14,90,60,70)]);h=frame(self.hi,[(24,90,65,70),(24,80,60,70)]);o=evaluate_extended(d,h,self.t);self.assertEqual((o['season'],o['autumn_watch']),('UNKNOWN','YES'))
 def test_missing_long_or_small_is_not_negative_evidence(self):
  d=frame(self.di,[(28,100,50,70),(14,90,60,80),(14,85,65,80)]);h=frame(self.hi,[(24,80,65,70),(24,85,70,75)])
  o=evaluate_extended(d.iloc[1:],h,self.t);self.assertFalse(o['long_valid']);self.assertTrue(o['big_valid']);self.assertTrue(o['small_valid']);self.assertEqual(o['spring_watch'],'UNKNOWN')
  o=evaluate_extended(d,h.iloc[1:],self.t);self.assertTrue(o['big_valid']);self.assertFalse(o['small_valid']);self.assertEqual(o['season'],'UNKNOWN');self.assertEqual(o['autumn_watch'],'UNKNOWN')
 def test_later_data_cannot_change_current_judgment(self):
  for name,(d,h) in sources().items():
   original=evaluate_extended(d,h,self.t);d=d.copy();h=h.copy();d.loc[d.index>=self.t,['high','low','close']]*=1.7;h.loc[h.index>=self.t,['high','low','close']]*=1.7;self.assertEqual(original,evaluate_extended(d,h,self.t),name)
if __name__=='__main__':unittest.main()
