import unittest

import numpy as np
import pandas as pd

from .cycle_space_research import delayed, features, spot_summary


class CycleSpaceTests(unittest.TestCase):
    def test_future_prices_do_not_change_past_signals_or_exit_levels(self):
        ts=pd.date_range('2024-01-01',periods=35*288,freq='5min',tz='UTC')
        price=np.linspace(100,150,len(ts))
        btc=pd.DataFrame({'ts':ts,'high':price+1,'low':price-1,'close':price})
        eth=btc.copy();eth['close']=np.linspace(100,180,len(ts));eth['high']=eth.close+2;eth['low']=eth.close-2
        trigger_index=29*288+100
        eth.loc[trigger_index,'low']=eth.loc[trigger_index-20:trigger_index-1,'low'].min()-1
        hit,levels,exits=features(btc,eth)
        self.assertTrue(hit[trigger_index])
        cutoff=ts[30*288]
        changed=eth.copy(); changed.loc[changed.ts>=cutoff,['high','low','close']]*=3
        changed_btc=btc.copy();changed_btc.loc[changed_btc.ts>=cutoff,['high','low','close']]*=2
        hit2,levels2,exits2=features(changed_btc,changed)
        np.testing.assert_array_equal(hit[:30*288],hit2[:30*288])
        np.testing.assert_array_equal(levels[:30*288],levels2[:30*288])
        pd.testing.assert_series_equal(exits.loc[:cutoff],exits2.loc[:cutoff])
        delayed_hit, delayed_stops=delayed(np.array([False,True,False]),np.array([1.,2.,3.]))
        np.testing.assert_array_equal(delayed_hit,[False,False,True])
        self.assertEqual(delayed_stops[2],2.)

    def test_spot_buy_fees_sell_fees_and_missing_day(self):
        t=int(pd.Timestamp('2024-07-01',tz='UTC').timestamp()*1000)
        rows=[[t,'100','110','90','100'],[t+86400000,'100','120','90','110']]
        out=spot_summary(rows,'2024-07-01','2024-07-03')
        self.assertAlmostEqual(out['equity_mark_usdt'],2000/(100*1.0002*1.001)*110)
        self.assertAlmostEqual(out['estimated_exit_net_usdt'],out['equity_mark_usdt']*.9998*.999)
        with self.assertRaises(ValueError):spot_summary(rows[:1],'2024-07-01','2024-07-03')


if __name__=='__main__':unittest.main()
