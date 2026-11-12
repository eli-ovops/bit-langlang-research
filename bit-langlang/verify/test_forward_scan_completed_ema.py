import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from .forward_scan import build_snapshot


class CompletedDailyEmaTests(unittest.TestCase):
    def test_in_progress_day_is_excluded_until_midnight_close(self):
        times = pd.date_range('2025-11-22', periods=206*288, freq='5min', tz='UTC')
        day = times[-1].floor('D')
        close = pd.Series(100.0, index=range(len(times)))
        close.loc[times >= day] = 200.0
        candles = pd.DataFrame({'ts':times, 'open':close, 'high':close, 'low':close, 'close':close})
        with tempfile.TemporaryDirectory() as folder:
            for symbol in ('BTCUSDT', 'ETHUSDT'):
                (Path(folder) / f'{symbol}_5m.csv.gz').write_bytes(b'synthetic')
            with patch('verify.forward_scan.read_raw_candles', return_value=candles):
                intraday = build_snapshot(folder, 1, day + pd.Timedelta(hours=12))
                closed = build_snapshot(folder, 1, day + pd.Timedelta(days=1))
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            before = intraday['symbols'][symbol]
            after = closed['symbols'][symbol]
            self.assertEqual(before['ema20_daily'], 100.0)
            self.assertEqual(before['ema20_daily_completed_day_utc'], str((day-pd.Timedelta(days=1)).date()))
            self.assertEqual(after['ema20_daily'], 109.52)
            self.assertEqual(after['ema20_daily_completed_day_utc'], str(day.date()))


if __name__ == '__main__':
    unittest.main()
