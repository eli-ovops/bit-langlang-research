import unittest

import numpy as np
import pandas as pd

from .historical_entry_replica import audit,eligible_match,summary
from .historical_entry_candidate import three_bar_pattern


class ReplicaAuditTests(unittest.TestCase):
    def test_three_bar_confirmation_uses_completed_past_bars(self):
        d=pd.DataFrame({'low':[95,96,96,96,96,97], 'open':[100]*6,
                        'high':[101]*6,'close':[100,100,100,100,102,100]})
        self.assertTrue(three_bar_pattern(d).iloc[4])
        altered=d.copy();altered.loc[2,'low']=94
        self.assertFalse(three_bar_pattern(altered).iloc[4])
        future=d.copy();future.loc[5,['low','high','close']]=[1,999,999]
        self.assertEqual(bool(three_bar_pattern(d).iloc[4]),bool(three_bar_pattern(future).iloc[4]))

    def test_causal_window_boundaries(self):
        base=pd.Timestamp('2023-01-01T00:00Z').value;minute=60*1000000000
        signals=np.array([base,base+20*minute],dtype='int64')
        self.assertIsNone(eligible_match(signals,base-1))
        self.assertEqual(eligible_match(signals,base+15*minute),base)
        self.assertIsNone(eligible_match(signals,base+16*minute))
        self.assertEqual(eligible_match(signals,base+20*minute),base+20*minute)

    def test_scope_and_duplicate_signal(self):
        t=pd.Timestamp('2023-01-01T00:00Z');idx=pd.date_range(t,periods=4,freq='5min')
        frame=pd.DataFrame({'low':[99.]*4,'high':[101.]*4},index=idx)
        market={'UNIUSDT':{'market':frame,'execution_ns':np.array([t.value]),'candidate_count':1}}
        rows=pd.DataFrame([{'id':1,'base':'UNI','side':'多','entry_time':'2023-01-01 00:01:00','entry_price':100},
                           {'id':2,'base':'UNI','side':'多','entry_time':'2023-01-01 00:04:00','entry_price':100},
                           {'id':3,'base':'UNI','side':'空','entry_time':'2023-01-01 00:04:00','entry_price':100},
                           {'id':4,'base':'BTC','side':'多','entry_time':'2023-01-01 00:04:00','entry_price':100}])
        out=audit(rows,market,0);result=summary(out,market)
        self.assertEqual(result['matched_rows'],2);self.assertEqual(result['matched_unique_signals'],1)
        self.assertEqual(result['duplicate_matched_rows'],1);self.assertEqual(result['statuses']['OUT_OF_SCOPE_SHORT'],1)
        self.assertTrue(all(x['stop_order_status']=='UNKNOWN_NOT_RECORDED' for x in out))


if __name__=='__main__':unittest.main()
