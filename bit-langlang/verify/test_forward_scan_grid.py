import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from .forward_scan import build_snapshot


class ForwardScanGridTest(unittest.TestCase):
    def test_same_latest_bar_but_different_history_is_invalid(self):
        count = 205 * 288 + 1
        start = pd.Timestamp('2026-01-01', tz='UTC')
        ts = pd.date_range(start, periods=count, freq='5min')
        frame = pd.DataFrame({'ts': ts.astype('int64') // 10**6,
                              'open': 100., 'high': 101., 'low': 99., 'close': 100.})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame.to_csv(root/'BTCUSDT_5m.csv.gz', index=False, compression='gzip')
            frame.iloc[1:].to_csv(root/'ETHUSDT_5m.csv.gz', index=False, compression='gzip')
            def fake_signals(btc, coin):
                n = len(coin)
                context = pd.DataFrame({'rs7': [0.1]*n, 'dist_hi': [0.01]*n, 'risk_on': [True]*n})
                return np.zeros(n, dtype=bool), context, pd.Series([100.])
            with patch('verify.tph_frozen_audit.signals', side_effect=fake_signals) as called:
                result = build_snapshot(root, 1, ts[-1]+pd.Timedelta(minutes=5))
            self.assertEqual(result['symbols']['BTCUSDT']['data_status']['status'], 'FRESH')
            self.assertEqual(result['symbols']['ETHUSDT']['data_status']['status'], 'INVALID')
            self.assertFalse(result['symbols']['ETHUSDT']['watch'])
            self.assertEqual(result['symbols']['ETHUSDT']['signals_recent'], [])
            self.assertEqual(called.call_count, 1)
            frame.to_csv(root/'ETHUSDT_5m.csv.gz', index=False, compression='gzip')
            with patch('verify.tph_frozen_audit.signals', side_effect=fake_signals):
                aligned = build_snapshot(root, 1, ts[-1]+pd.Timedelta(minutes=5))
            self.assertEqual(aligned['symbols']['ETHUSDT']['data_status']['status'], 'FRESH')
            self.assertTrue(aligned['symbols']['ETHUSDT']['watch'])


if __name__ == '__main__':
    unittest.main()
