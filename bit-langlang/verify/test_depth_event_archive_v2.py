import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import depth_event_archive_v2 as v2


class DepthArchiveV2Tests(unittest.TestCase):
    def make(self,path):
        v2.init(path);return v2.NewSessionWriter(path,clock=lambda:'2026-10-30T00:00:02Z')

    def test_dual_chain_receipt_and_seal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'v2';writer=self.make(root)
            ack=writer.append('{"u":1}','2026-10-30T00:00:01Z')
            self.assertEqual(ack['event_fsync_returned_at_utc'],'2026-10-30T00:00:02Z')
            self.assertEqual(v2.inspect(root)['status'],'INCOMPLETE_UNSEALED')
            sealed=writer.seal();result=v2.inspect(root,expected_event_head=sealed['event_head_sha256'],
                                                  expected_receipt_head=sealed['receipt_head_sha256'],expected_seal=sealed['seal_sha256'])
            self.assertEqual(result['status'],'PARTIAL_SEALED_UNVERIFIED')
            self.assertEqual(result['records'][0]['wire_text'],'{"u":1}')
            with self.assertRaises(ValueError):writer.append('x','2026-10-30T00:00:01Z')

    def test_clock_backwards_and_receipt_write_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'clock';writer=self.make(root)
            with self.assertRaises(ValueError):writer.append('first','2026-10-30T00:00:03Z')
            result=v2.inspect(root);self.assertEqual(result['status'],'INVALID');self.assertEqual(result['valid_prefix'],0)
            root=Path(folder)/'io';writer=self.make(root);original=v2.write_new
            def fail_receipt(path,raw):
                if Path(path).parent.name=='receipts':raise OSError('synthetic receipt failure')
                return original(path,raw)
            with patch.object(v2,'write_new',side_effect=fail_receipt):
                with self.assertRaises(OSError):writer.append('first','2026-10-30T00:00:01Z')
            self.assertEqual(v2.inspect(root)['status'],'INVALID')
            with self.assertRaises(ValueError):writer.seal()
            self.assertFalse((root/'seal.json').exists())

    def test_missing_tampered_and_truncated_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            for mode in ('missing','tampered','truncated'):
                root=Path(folder)/mode;writer=self.make(root)
                writer.append('first','2026-10-30T00:00:01Z');writer.append('second','2026-10-30T00:00:01Z');writer.seal()
                receipt=root/'receipts'/'00000001.json'
                if mode=='missing':receipt.unlink()
                elif mode=='truncated':receipt.write_bytes(b'{')
                else:receipt.write_bytes(receipt.read_bytes().replace(b'LOCAL_CLOCK_UNVERIFIED',b'FORGED'))
                result=v2.inspect(root);self.assertEqual(result['status'],'INVALID',mode);self.assertEqual(result['valid_prefix'],1)


if __name__=='__main__':unittest.main()
