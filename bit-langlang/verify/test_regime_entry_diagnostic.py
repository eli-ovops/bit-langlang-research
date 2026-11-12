import unittest
import pandas as pd
from .regime_entry_diagnostic import classify


class RegimeEntryDiagnostic(unittest.TestCase):
    def test_only_completed_prior_days_and_missing_bar(self):
        ts=pd.date_range('2026-01-01',periods=23*288,freq='5min',tz='UTC')
        market=pd.DataFrame({'ts':ts.astype('int64')//10**6,'close':100.0})
        ledger=pd.DataFrame([{'trade_id':'1','entry_ts':'2026-01-23T10:00:00Z',
                              'entry':100,'stop':99,'qty':1,'net_pnl':2}])
        result=classify(market,ledger)
        self.assertEqual(result['records'][0]['group'],'LE_0')
        self.assertEqual(result['records'][0]['net_R'],2)
        future=market.copy();future.loc[ts>=pd.Timestamp('2026-01-23',tz='UTC'),'close']=999
        self.assertEqual(classify(future,ledger)['records'],result['records'])
        missing=market[ts!=pd.Timestamp('2026-01-22T12:00:00Z')]
        self.assertEqual(classify(missing,ledger)['records'][0]['group'],'UNKNOWN')
        duplicate=pd.concat([market,market[ts==pd.Timestamp('2026-01-22T12:00:00Z')]])
        self.assertEqual(classify(duplicate,ledger)['records'][0]['group'],'UNKNOWN')


if __name__=='__main__':unittest.main()
