import tempfile
import unittest
from pathlib import Path

from .depth_event_archive import NewSessionWriter,append,init,inspect,seal


class DepthEventArchiveTests(unittest.TestCase):
    def test_new_session_writer_rechecks_chain_before_sealing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'writer';init(root);writer=NewSessionWriter(root)
            writer.append('first','time');writer.append('second','time')
            with self.assertRaises(ValueError):NewSessionWriter(root)
            path=root/'events'/'00000000.json';path.write_bytes(path.read_bytes().replace(b'Zmlyc3Q=',b'ZmFrZQ=='))
            with self.assertRaises(ValueError):writer.seal()
            self.assertFalse((root/'seal.json').exists())

    def test_unsealed_sealed_and_external_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'a';init(root)
            a=append(root,'{"u":1}','2026-10-30T00:00:00Z')
            self.assertEqual(inspect(root)['status'],'INCOMPLETE_UNSEALED')
            self.assertEqual(inspect(root,expected_head='wrong')['status'],'INVALID')
            b=append(root,'{"u":2}','2026-10-30T00:00:01Z')
            done=seal(root);review=inspect(root,expected_head=b['head_sha256'],expected_seal=done['seal_sha256'])
            self.assertEqual(review['status'],'PARTIAL_SEALED_UNVERIFIED')
            self.assertEqual([x['wire_text'] for x in review['records']],['{"u":1}','{"u":2}'])
            with self.assertRaises(ValueError):append(root,'{}','2026-10-30T00:00:02Z')
            self.assertNotEqual(a['head_sha256'],b['head_sha256'])

    def test_truncated_tampered_and_missing_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for variant in ('truncated','tampered','missing'):
                root=Path(tmp)/variant;init(root);append(root,'first','time');append(root,'second','time');seal(root)
                event=root/'events'/'00000001.json'
                if variant=='truncated':event.write_bytes(b'{')
                elif variant=='tampered':event.write_bytes(event.read_bytes().replace(b'c2Vjb25k',b'ZmFrZQ=='))
                else:event.unlink()
                self.assertEqual(inspect(root)['status'],'INVALID',variant)


if __name__=='__main__':unittest.main()
