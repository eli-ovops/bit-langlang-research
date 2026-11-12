import unittest

import numpy as np
import pandas as pd

from .five_futures_compound import simulate


class CompoundTests(unittest.TestCase):
    def test_delay_stop_first_cost_and_funding(self):
        idx=pd.date_range('2025-10-01',periods=8,freq='5min',tz='UTC');n=len(idx)
        d={k:np.full(n,100.) for k in ('open','high','low','close')}
        d.update(signal=np.array([True]+[False]*(n-1)),rank=np.ones(n),relative_strength=np.ones(n),target=np.full(n,105.))
        d['low'][0]=99.;d['low'][3]=98.;d['high'][3]=106.;d['open'][4]=97.;d['low'][4]=96.
        event=int(idx[2].value//1_000_000);d['funding']={event:(event,.001)}
        result,closed,opened=simulate(idx,{'UNIUSDT':d},idx[0],idx[-1]+pd.Timedelta(minutes=5))
        self.assertEqual(len(closed),1);self.assertFalse(opened)
        trade=closed[0];self.assertEqual(trade['entry_ts'],idx[2].isoformat())
        self.assertEqual(trade['reason'],'stop_next_open');self.assertEqual(trade['exit_ts'],idx[4].isoformat())
        self.assertEqual(result['ambiguous_trigger_bars'],1)
        self.assertIs(type(result['win_count']),int)
        self.assertAlmostEqual(trade['funding_paid'],trade['qty']*100*.001)
        self.assertAlmostEqual(result['equity_end'],2000+trade['net_pnl'])
        self.assertAlmostEqual(trade['net_pnl'],trade['gross_pnl']-trade['entry_fee']-trade['exit_fee']-trade['funding_paid'])

    def test_open_position_floating_equity(self):
        idx=pd.date_range('2025-10-01',periods=4,freq='5min',tz='UTC');n=len(idx)
        d={k:np.full(n,100.) for k in ('open','high','low','close')}
        d.update(signal=np.array([True,False,False,False]),rank=np.ones(n),relative_strength=np.ones(n),target=np.full(n,110.),funding={})
        d['low'][0]=99.;d['close'][-1]=101.
        result,closed,opened=simulate(idx,{'UNIUSDT':d},idx[0],idx[-1]+pd.Timedelta(minutes=5))
        self.assertFalse(closed);self.assertEqual(len(opened),1)
        self.assertAlmostEqual(result['equity_end'],2000+opened[0]['net_to_date'])
        self.assertGreater(opened[0]['estimated_exit_fee'],0)


if __name__=='__main__':unittest.main()
