import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from . import paper_nine_observe_once as once

ROOT = Path(__file__).resolve().parents[1]
BODY = (ROOT/'data/verify/langlang-paper-research-20261110-01/btc-daily-response.json').read_bytes()


class Response:
    status=200
    def __init__(self, body=BODY, url=once.URL):
        self.body=body
        self.url=url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.body[:size]
    def geturl(self): return self.url


class ObserveOnceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='paper-observe-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.folder=self.root/'new'
        initial={'status':'UNKNOWN','recomputed_market_gate':'NO_CANDIDATE',
                 'observed_utc':'2026-11-10T06:35:12.260234+00:00'}
        self.patches=[patch.object(once,'VERIFY_ROOT',self.root),patch.object(once,'bridge',return_value=initial),
                      patch.object(once,'now_utc',return_value=datetime(2026,11,10,6,50,tzinfo=timezone.utc))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_success_is_diagnostic_no_paper_decision(self):
        with patch.object(once.urllib.request,'urlopen',return_value=Response()):
            result=once.run(self.folder)
        self.assertEqual(result['status'],'NO_CANDIDATE')
        self.assertEqual(result['capture_scope'],'SAME_DAY_DIAGNOSTIC_ONLY')
        self.assertEqual(result['paper_decision'],'NONE')
        self.assertFalse(result['ledger_modified'])
        self.assertEqual((self.folder/'response.json').read_bytes(),BODY)

    def test_existing_folder_never_overwrites(self):
        self.folder.mkdir()
        marker=self.folder/'marker';marker.write_text('preserve')
        with patch.object(once.urllib.request,'urlopen') as request:
            result=once.run(self.folder)
        self.assertEqual(result['status'],'INVALID')
        self.assertEqual(marker.read_text(),'preserve')
        request.assert_not_called()

    def test_initial_mismatch_stops_before_network(self):
        with patch.object(once,'bridge',return_value={'status':'INVALID'}), patch.object(once.urllib.request,'urlopen') as request:
            result=once.run(self.folder)
        self.assertEqual(result['status'],'UNKNOWN')
        request.assert_not_called()

    def test_timeout_records_unknown_no_ledger(self):
        with patch.object(once.urllib.request,'urlopen',side_effect=TimeoutError('synthetic')):
            result=once.run(self.folder)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['reason'],'TimeoutError')
        self.assertEqual(result['paper_decision'],'NONE')
        self.assertFalse(result['ledger_modified'])

    def test_url_error_exposes_only_underlying_type(self):
        failure=once.urllib.error.URLError(TimeoutError('synthetic-private-message'))
        with patch.object(once.urllib.request,'urlopen',side_effect=failure):
            result=once.run(self.folder)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['underlying_error_type'],'TimeoutError')
        self.assertNotIn('synthetic-private-message',json.dumps(result))

    def test_redirect_is_rejected(self):
        with patch.object(once.urllib.request,'urlopen',return_value=Response(url='https://example.org/')):
            result=once.run(self.folder)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertFalse((self.folder/'response.json').exists())

    def test_outside_project_is_rejected_before_network(self):
        with patch.object(once.urllib.request,'urlopen') as request:
            result=once.run(self.root.parent/'outside-test')
        self.assertEqual(result['status'],'INVALID')
        request.assert_not_called()


if __name__=='__main__': unittest.main()
