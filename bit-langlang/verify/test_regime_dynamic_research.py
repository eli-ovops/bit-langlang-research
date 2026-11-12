import unittest
import pandas as pd
from .regime_dynamic_research import allowed_by_prior_day


class DynamicFilterTests(unittest.TestCase):
    def test_prior_day_only_including_midnight_boundary(self):
        ts=pd.date_range('2026-01-01',periods=23*288,freq='5min',tz='UTC')
        frame=pd.DataFrame({'ts':ts,'close':100.})
        allowed,ret=allowed_by_prior_day(frame)
        i=ts.get_loc(pd.Timestamp('2026-01-22T23:55:00Z'))
        self.assertTrue(allowed[i]);self.assertEqual(ret[i],0)
        changed=frame.copy();changed.loc[ts>=pd.Timestamp('2026-01-23',tz='UTC'),'close']=999
        self.assertEqual(allowed_by_prior_day(changed)[1][i],0)
        changed=frame.copy();changed.loc[ts==pd.Timestamp('2026-01-22T23:55:00Z'),'close']=130
        self.assertFalse(allowed_by_prior_day(changed)[0][i])
        missing=frame.drop(index=ts.get_loc(pd.Timestamp('2026-01-22T12:00:00Z'))).reset_index(drop=True)
        j=missing.index[missing.ts==ts[i]][0]
        self.assertFalse(allowed_by_prior_day(missing)[0][j])


if __name__=='__main__':unittest.main()
