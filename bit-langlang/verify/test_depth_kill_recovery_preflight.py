import json
import tempfile
import unittest
from pathlib import Path

from .depth_event_archive import init,append
from .depth_kill_recovery_preflight import recover


class DepthKillRecoveryTests(unittest.TestCase):
    def test_recover_valid_prefix_without_silencing_partial_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);journal=root/'event-archive';init(journal)
            for i in range(3):
                msg={'e':'depthUpdate','s':'ETHUSDT','U':100+i,'u':100+i,'pu':99+i,'b':[],'a':[]}
                append(journal,json.dumps(msg),f'2026-10-30T00:00:0{i}Z')
            (root/'snapshot-response.json').write_text(json.dumps({'lastUpdateId':100,'bids':[['100','1']],'asks':[['101','1']]}))
            ok=recover(root);self.assertEqual(ok['archive_status'],'INCOMPLETE_UNSEALED');self.assertEqual(ok['prefix_count'],3)
            (journal/'events'/'00000003.json').write_bytes(b'{')
            partial=recover(root);self.assertEqual(partial['archive_status'],'INVALID');self.assertEqual(partial['prefix_count'],3)
            self.assertEqual(partial['sequence']['status'],'PARTIAL_CHAIN_UNVERIFIED')
            (root/'snapshot-response.json').write_text('{}')
            with self.assertRaises(KeyError):recover(root)


if __name__=='__main__':unittest.main()
