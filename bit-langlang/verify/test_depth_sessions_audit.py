import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .depth_event_archive import init,append,seal
from .depth_sessions_audit import audit


class DepthSessionsTests(unittest.TestCase):
    def session(self,root,first,last,*,sealed=True,bid_after=None):
        root.mkdir();journal=root/'event-archive';init(journal)
        events=[]
        for i,time in enumerate((first,last)):
            updates=[['100','0'],[str(bid_after),'1']] if i==1 and bid_after is not None else []
            msg={'e':'depthUpdate','s':'ETHUSDT','U':100+i,'u':100+i,'pu':99+i,'b':updates,'a':[]}
            item={'received_at_utc':time,'wire_text':json.dumps(msg)};events.append(item);append(journal,item['wire_text'],time)
        if not sealed:return root
        done=seal(journal);snap={'lastUpdateId':100,'bids':[['100','1'],['99','1']],'asks':[['101','1']]}
        trace={'schema':'paper-depth-sequence-v1','symbol':'ETHUSDT','snapshot_last_update_id':100,
               'snapshot_bids':snap['bids'],'snapshot_asks':snap['asks'],'events':[json.loads(x['wire_text']) for x in events]}
        files={'events.json':events,'snapshot-response.json':snap,'derived-trace.json':trace};hashes={}
        for name,obj in files.items():
            raw=json.dumps(obj).encode();(root/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
        manifest={'schema':'public-depth-preflight-v1','error':None,'message_count':2,
                  'rest_http_status':200,'rest_symbol':'ETHUSDT','started_at_utc':first,
                  'rest_started_at_utc':first,'rest_completed_at_utc':last,'finished_at_utc':last,
                  'events_sha256':hashes['events.json'],'snapshot_response_sha256':hashes['snapshot-response.json'],
                  'derived_trace_sha256':hashes['derived-trace.json'],'journal':done}
        (root/'manifest.json').write_text(json.dumps(manifest));return root

    def test_gap_unsealed_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);a=self.session(r/'a','2026-10-30T00:00:00Z','2026-10-30T00:00:01Z')
            b=self.session(r/'b','2026-10-30T00:00:05Z','2026-10-30T00:00:06Z')
            self.assertEqual(audit([a])['status'],'PARTIAL_SINGLE_UNVERIFIED')
            result=audit([a,b]);self.assertEqual(result['status'],'GAP_UNOBSERVED_BETWEEN_SESSIONS')
            self.assertEqual(result['gaps'][0]['local_clock_gap_seconds'],4)
            self.assertEqual(audit([b,a])['status'],'INVALID')
            self.assertEqual(audit([a,a])['status'],'INVALID')
            c=self.session(r/'c','2026-10-30T00:00:08Z','2026-10-30T00:00:09Z',sealed=False)
            self.assertEqual(audit([a,c])['status'],'INCOMPLETE_UNSEALED')

    def test_tampered_snapshot_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=self.session(Path(tmp)/'a','2026-10-30T00:00:00Z','2026-10-30T00:00:01Z')
            (a/'snapshot-response.json').write_text('{}')
            self.assertEqual(audit([a])['status'],'INVALID')


if __name__=='__main__':unittest.main()
