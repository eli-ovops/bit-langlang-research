import unittest

import numpy as np
import pandas as pd

from .five_leader_research import COINS, evaluate


class FiveLeaderTests(unittest.TestCase):
    def frames(self):
        ix=pd.date_range('2024-05-31','2024-08-03',freq='D',tz='UTC')
        return {s:pd.DataFrame({'open':100.,'close':np.linspace(100,100+i,len(ix))},index=ix)
                for i,s in enumerate(COINS)}

    def test_future_closes_do_not_change_earlier_pick_and_costs_are_booked(self):
        frames=self.frames();out=evaluate(frames,'2024-07-02','2024-08-04')
        self.assertEqual(out['picks'][0]['selected'],COINS[-1])
        self.assertEqual(out['picks'][0]['score_end_day'],'2024-06-30')
        order=out['orders'][0];self.assertEqual(order['time'],'2024-07-02T00:00:00+00:00')
        self.assertAlmostEqual(order['qty']*order['fill']+order['fee'],2000.)
        changed={s:f.copy() for s,f in frames.items()}
        for f in changed.values():f.loc[f.index>=pd.Timestamp('2024-07-01',tz='UTC'),'close']*=4
        altered=evaluate(changed,'2024-07-02','2024-08-04')
        self.assertEqual(out['picks'][0],altered['picks'][0])
        self.assertEqual(out['orders'][0],altered['orders'][0])

    def test_missing_grid_is_rejected(self):
        frames=self.frames();frames[COINS[0]]=frames[COINS[0]].iloc[:-1]
        with self.assertRaises(ValueError):evaluate(frames,'2024-07-02','2024-08-04')


if __name__=='__main__':unittest.main()
