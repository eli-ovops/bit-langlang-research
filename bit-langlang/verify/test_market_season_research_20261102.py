import unittest
import pandas as pd
from .market_season_research_20261102 import relation,season,aggregates,classify_asof,SOURCE

def frame(old,new,n,close=6):
 a=pd.DataFrame([{'high':old[0],'low':old[1],'close':close,'good':True} for _ in range(n)])
 b=pd.DataFrame([{'high':new[0],'low':new[1],'close':close,'good':True} for _ in range(n)])
 return pd.concat([a,b],ignore_index=True)
class SeasonTests(unittest.TestCase):
 def test_four_classes_and_conflicts(self):
  up=frame((10,2),(12,4),7,8);down=frame((10,2),(8,1),7,6);inside=frame((10,2),(9,3),7,8)
  h_up=frame((10,2),(12,4),24);h_down=frame((10,2),(8,1),24)
  self.assertEqual(season(inside,h_up)['season'],'SPRING');self.assertEqual(season(up,h_up)['season'],'SUMMER')
  self.assertEqual(season(up,h_down)['season'],'AUTUMN');self.assertEqual(season(down,h_down)['season'],'WINTER')
  self.assertEqual(season(down,h_up)['season'],'UNKNOWN');self.assertEqual(season(inside.iloc[:-1],h_up)['reason'],'INCOMPLETE_OR_INVALID_DATA')
  bad=inside.copy();bad.loc[0,'good']=False;self.assertEqual(season(bad,h_up)['season'],'UNKNOWN')
 def test_relation_equal_and_expansion(self):
  self.assertEqual(relation(10,2,10,2),'INSIDE');self.assertEqual(relation(10,2,12,1),'MIXED');self.assertEqual(relation(10,2,10,3),'INSIDE');self.assertEqual(relation(10,2,11,2),'MIXED')
 def test_future_perturb_and_missing(self):
  f=pd.read_csv(SOURCE);f['time']=pd.to_datetime(f.ts,unit='ms',utc=True);f=f.set_index('time');cut=pd.Timestamp('2026-03-01',tz='UTC');d,h=aggregates(f);before=classify_asof(d,h,cut)
  altered=f.copy();altered.loc[altered.index>=cut,['open','high','low','close']]*=2;d2,h2=aggregates(altered);self.assertEqual(before,classify_asof(d2,h2,cut))
  gap=f.drop(index=cut-pd.Timedelta(minutes=5));d3,h3=aggregates(gap);self.assertEqual(classify_asof(d3,h3,cut)['season'],'UNKNOWN')
  bad=f.copy();bad.loc[cut-pd.Timedelta(minutes=5),'high']=0;d4,h4=aggregates(bad);self.assertEqual(classify_asof(d4,h4,cut)['season'],'UNKNOWN')
if __name__=='__main__':unittest.main()
