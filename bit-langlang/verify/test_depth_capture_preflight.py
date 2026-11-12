import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from .depth_capture_preflight import main
from . import depth_event_archive as archive
from .depth_sessions_audit import audit_session


class FakeSocket:
    def __init__(self):self.n=0;self.closed=False
    def settimeout(self,_):pass
    def recv(self):
        u=100+self.n;self.n+=1
        return json.dumps({'e':'depthUpdate','s':'ETHUSDT','U':u,'u':u,'pu':u-1,'b':[],'a':[]})
    def close(self):self.closed=True


class CapturePreflightTests(unittest.TestCase):
    def test_bounded_sample_and_raw_artifacts(self):
        sock=FakeSocket()
        class Response:
            status_code=200
            content=json.dumps({'lastUpdateId':100,'bids':[['100','1']],'asks':[['101','1']]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'capture';buf=io.StringIO()
            with patch.object(sys,'argv',['capture','--outdir',str(out)]),\
                 patch('verify.depth_capture_preflight.websocket.create_connection',return_value=sock) as conn,\
                 patch('verify.depth_capture_preflight.requests.get',return_value=Response()) as req,redirect_stdout(buf):
                main()
            data=json.loads(buf.getvalue());self.assertEqual(data['message_count'],500)
            self.assertEqual(data['end_reason'],'MESSAGE_LIMIT');self.assertEqual(data['book_status'],'PARTIAL_BOOK_UNVERIFIED')
            self.assertEqual(data['sequence']['status'],'PARTIAL_CHAIN_UNVERIFIED')
            self.assertTrue(sock.closed);self.assertEqual(conn.call_count,1);self.assertEqual(req.call_count,1)
            self.assertTrue((out/'snapshot-response.json').exists());self.assertTrue((out/'derived-trace.json').exists())

    def test_connection_failure_keeps_receipt_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'failure';buf=io.StringIO()
            with patch.object(sys,'argv',['capture','--outdir',str(out)]),\
                 patch('verify.depth_capture_preflight.websocket.create_connection',side_effect=OSError('synthetic failure')) as conn,\
                 patch('verify.depth_capture_preflight.requests.get') as req,redirect_stdout(buf):
                main()
            data=json.loads(buf.getvalue());self.assertEqual(data['end_reason'],'ERROR');self.assertEqual(data['error']['type'],'OSError')
            self.assertEqual(conn.call_count,1);self.assertEqual(req.call_count,0);self.assertTrue((out/'manifest.json').exists())

    def test_journal_success_seals_and_matches(self):
        sock=FakeSocket()
        class Response:
            status_code=200
            content=json.dumps({'lastUpdateId':100,'bids':[['100','1']],'asks':[['101','1']]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'capture';buf=io.StringIO()
            with patch.object(sys,'argv',['capture','--outdir',str(out),'--journal']),\
                 patch('verify.depth_capture_preflight.websocket.create_connection',return_value=sock),\
                 patch('verify.depth_capture_preflight.requests.get',return_value=Response()),redirect_stdout(buf):main()
            data=json.loads(buf.getvalue());self.assertEqual(data['journal']['status'],'PARTIAL_SEALED_UNVERIFIED',data)
            self.assertTrue(data['journal']['matches_events_file'])
            self.assertEqual(data['journal']['message_count'],data['message_count'])
            self.assertEqual(data['snapshot_file_sha256'],data['snapshot_response_sha256'])

    def test_journal_failure_keeps_unsealed_prefix(self):
        sock=FakeSocket();real_append=archive.NewSessionWriter.append
        def failing(writer,*args):
            real_append(writer,*args)
            raise OSError('synthetic failure after append')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'capture';buf=io.StringIO()
            with patch.object(sys,'argv',['capture','--outdir',str(out),'--journal']),\
                 patch('verify.depth_capture_preflight.websocket.create_connection',return_value=sock),\
                 patch.object(archive.NewSessionWriter,'append',autospec=True,side_effect=failing),redirect_stdout(buf):main()
            data=json.loads(buf.getvalue());self.assertEqual(data['end_reason'],'ERROR')
            self.assertEqual(data['journal']['status'],'INCOMPLETE_UNSEALED')
            self.assertEqual(data['journal']['message_count'],1)
            self.assertFalse(data['journal']['matches_events_file'])
            self.assertFalse((out/'event-archive'/'seal.json').exists())

    def test_v2_capture_audits_receipts_and_detects_tampering(self):
        sock=FakeSocket()
        class Response:
            status_code=200
            content=json.dumps({'lastUpdateId':100,'bids':[['100','1']],'asks':[['101','1']]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'capture';buf=io.StringIO()
            with patch.object(sys,'argv',['capture','--outdir',str(out),'--journal-v2']),\
                 patch('verify.depth_capture_preflight.websocket.create_connection',return_value=sock),\
                 patch('verify.depth_capture_preflight.requests.get',return_value=Response()),redirect_stdout(buf):main()
            data=json.loads(buf.getvalue());self.assertEqual(data['journal']['status'],'PARTIAL_SEALED_UNVERIFIED',data)
            self.assertEqual(data['journal']['version'],'v2')
            checked=audit_session(out);self.assertEqual(checked['status'],'PARTIAL_UNVERIFIED',checked)
            self.assertEqual(len(checked['event_fsync_returned_at_utc']),data['message_count'])
            receipt=out/'event-archive'/'receipts'/'00000001.json'
            receipt.write_bytes(b'{')
            self.assertEqual(audit_session(out)['status'],'INVALID')


if __name__=='__main__':unittest.main()
