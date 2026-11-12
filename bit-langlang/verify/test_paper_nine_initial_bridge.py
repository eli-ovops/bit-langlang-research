import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from .paper_nine_initial_bridge import bridge

SOURCE = Path(__file__).resolve().parents[1] / 'data/verify/langlang-paper-research-20261110-01'
FILES = ('协议.md', 'btc-daily-response.json', 'btc-daily-receipt.json', 'observation-01.json', 'ledger.csv')


class InitialBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='paper-nine-initial-test-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        for name in FILES:
            shutil.copyfile(SOURCE / name, self.folder / name)

    def test_original_single_observation_remains_unknown(self):
        result = bridge(self.folder)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['recomputed_market_gate'], 'NO_CANDIDATE')
        self.assertEqual(result['local_ledger_cash_usdt'], '2000')
        self.assertIn('NO_TRADE_EVIDENCE', result['accounting']['limitations'])

    def test_source_tamper_is_invalid(self):
        path = self.folder / 'btc-daily-response.json'
        path.write_bytes(path.read_bytes() + b' ')
        self.assertEqual(bridge(self.folder)['status'], 'INVALID')

    def test_extra_event_is_not_silently_discarded(self):
        path = self.folder / 'ledger.csv'
        with path.open('a') as f:
            f.write('2026-11-10T07:00:00Z,ENTRY,SOLUSDT,1000,1,1,0,synthetic\n')
        self.assertEqual(bridge(self.folder)['status'], 'UNKNOWN_UNSUPPORTED_LEDGER')

    def test_balance_and_timing_mismatch_are_invalid(self):
        path = self.folder / 'observation-01.json'
        original = json.loads(path.read_text())
        for change in ({'cash_usdt':1999}, {'observed_utc':'2026-11-10T06:35:13+00:00'}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**original, **change}))
                self.assertEqual(bridge(self.folder)['status'], 'INVALID')

    def test_recomputed_signal_detects_forged_high_even_with_rehashed_source(self):
        path = self.folder / 'btc-daily-response.json'
        data = json.loads(path.read_text())
        data[-2][2] = '1000000'
        data[-2][4] = '999999'
        body = json.dumps(data).encode()
        path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        receipt_path = self.folder / 'btc-daily-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['sha256'] = digest
        receipt_path.write_text(json.dumps(receipt))
        observation_path = self.folder / 'observation-01.json'
        observation = json.loads(observation_path.read_text())
        observation['source_sha256'] = digest
        observation_path.write_text(json.dumps(observation))
        result = bridge(self.folder)
        self.assertEqual(result['status'], 'INVALID')
        self.assertIn('no-break', result['reason'])


if __name__ == '__main__':
    unittest.main()
