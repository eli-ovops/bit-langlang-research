import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from .paper_nine_market import D, URL, evaluate


class PaperMarketTests(unittest.TestCase):
    def setUp(self):
        self.when='2026-11-01T04:00:00+00:00'
        t=int(datetime(2026,11,1,tzinfo=timezone.utc).timestamp()*1000)
        self.rows=[]
        for i in range(35):
            ts=t-(35-i)*D
            self.rows.append([ts,'95','100','90','95','1',ts+D-1])
        for i,values in {31:('100','110','99','105'),32:('105','109','104','106'),
                         33:('104','109','103','104'),34:('104','108','103','104')}.items():
            self.rows[i][1:5]=values

    def run_case(self, rows, asof=None, change=None):
        body=json.dumps(rows).encode()
        receipt={'url':URL,'http':200,'sha256':hashlib.sha256(body).hexdigest(),
                 'request_utc':'2026-11-01T03:59:59+00:00','received_utc':self.when}
        if change:receipt.update(change)
        return evaluate(body,receipt,asof or self.when)

    def test_candidate_is_not_a_phase_or_order(self):
        result=self.run_case(self.rows)
        self.assertEqual(result['status'],'CANDIDATE')
        self.assertEqual(result['phase_truth'],'UNKNOWN')
        self.assertEqual(result['orders'],'NONE')
        self.assertIn('does not prove',result['warning'])

    def test_original_saved_response_reproduces_no_candidate(self):
        root=Path(__file__).resolve().parents[1]/'data/verify/langlang-paper-research-20261110-01'
        result=evaluate((root/'btc-daily-response.json').read_bytes(),
                        json.loads((root/'btc-daily-receipt.json').read_text()),
                        '2026-11-10T06:35:12.260234+00:00')
        self.assertEqual(result['status'],'NO_CANDIDATE')
        self.assertEqual(result['last_close'],'75327.00')

    def test_missing_duplicate_and_bad_volume_are_unknown(self):
        for bad in (self.rows[:-1],self.rows+[self.rows[-1]],
                    [*self.rows[:-1], [*self.rows[-1][:5], '0', self.rows[-1][6]]]):
            with self.subTest():self.assertEqual(self.run_case(bad)['status'],'UNKNOWN')

    def test_future_unfinished_bar_is_ignored(self):
        extra=copy.deepcopy(self.rows)
        ts=extra[-1][0]+D
        extra.append([ts,'999999','999999','1','999999','1',ts+D-1])
        self.assertEqual(self.run_case(extra),self.run_case(self.rows))

    def test_unavailable_or_stale_and_hash_mismatch_are_unknown(self):
        self.assertEqual(self.run_case(self.rows,asof='2026-11-01T03:00:00+00:00')['status'],'UNKNOWN')
        self.assertEqual(self.run_case(self.rows,asof='2026-11-02T04:00:00+00:00')['status'],'UNKNOWN')
        self.assertEqual(self.run_case(self.rows,change={'sha256':'0'*64})['status'],'UNKNOWN')


if __name__=='__main__':
    unittest.main()
