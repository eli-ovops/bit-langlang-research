"""Offline audit of independent public-depth captures; never claims continuity."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

from .depth_event_archive import inspect
from .depth_event_archive_v2 import inspect as inspect_v2
from .depth_sequence_audit import audit as audit_sequence
from .depth_book_replay import replay as replay_book

DEFINITION=Path(__file__).resolve().parent.parent/'docs/盘口多会话缺口-离线核验定义-20261030.md'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    if not isinstance(value,str):raise ValueError('时间格式无效')
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError('时间缺少时区')
    return t.astimezone(timezone.utc)


def audit_session(path):
    root=Path(path)
    try:
        meta=json.loads((root/'event-archive'/'archive.json').read_bytes())
        version='v2' if meta.get('schema')=='depth-event-archive-v2' else 'v1'
        journal=inspect_v2(root/'event-archive') if version=='v2' else inspect(root/'event-archive')
    except (OSError,ValueError,TypeError) as exc:return {'status':'INVALID','path':str(root),'reason':str(exc)}
    if journal['status']=='INCOMPLETE_UNSEALED':return {'status':'INCOMPLETE_UNSEALED','path':str(root),'count':journal['count']}
    if journal['status']!='PARTIAL_SEALED_UNVERIFIED':return {'status':'INVALID','path':str(root),'reason':'归档无效: '+journal.get('reason','')}
    try:
        mr=(root/'manifest.json').read_bytes();m=json.loads(mr)
        if (m.get('schema')!='public-depth-preflight-v1' or m.get('error') is not None or
                m.get('rest_http_status')!=200 or m.get('rest_symbol')!='ETHUSDT'):
            raise ValueError('预检清单无效')
        e=(root/'events.json').read_bytes();s=(root/'snapshot-response.json').read_bytes();t=(root/'derived-trace.json').read_bytes()
        if (sha(e)!=m['events_sha256'] or sha(s)!=m['snapshot_response_sha256'] or sha(t)!=m['derived_trace_sha256']
                or (journal['event_head_sha256'] if version=='v2' else journal['head_sha256'])!=m['journal']['head_sha256']
                or journal['seal_sha256']!=m['journal']['seal_sha256']
                or (version=='v2' and journal['receipt_head_sha256']!=m['journal']['receipt_head_sha256'])):
            raise ValueError('文件或归档哈希不一致')
        events=json.loads(e);snap=json.loads(s);trace=json.loads(t)
        records=journal['records']
        projected=[{'received_at_utc':x['received_at_utc'],'wire_text':x['wire_text']} for x in records] if version=='v2' else records
        if (not isinstance(events,list) or not events or len(events)!=m['message_count'] or projected!=events
                or trace['events']!=[json.loads(x['wire_text']) for x in events] or trace['snapshot_last_update_id']!=snap['lastUpdateId']
                or trace['snapshot_bids']!=snap['bids'] or trace['snapshot_asks']!=snap['asks']):raise ValueError('原始与派生记录不一致')
        times=[timestamp(x['received_at_utc']) for x in events]
        if any(a>b for a,b in zip(times,times[1:])):raise ValueError('本机接收时间倒序')
        started=timestamp(m['started_at_utc']);rest_start=timestamp(m['rest_started_at_utc'])
        rest_end=timestamp(m['rest_completed_at_utc']);finished=timestamp(m['finished_at_utc'])
        if not (started<=times[0]<=rest_start<=rest_end<=times[-1]<=finished):
            raise ValueError('连接、快照与接收时间顺序无效或缺失快照后消息')
        ack_times=[timestamp(x['event_fsync_returned_at_utc']) for x in records] if version=='v2' else None
        if ack_times is not None and (any(a>b for a,b in zip(times,ack_times)) or
                                      any(a>b for a,b in zip(ack_times,times[1:])) or ack_times[-1]>finished):
            raise ValueError('接收与事件 fsync 返回时间顺序无效')
        seq=audit_sequence(trace);book=replay_book(trace)
        if seq['status']!='PARTIAL_CHAIN_UNVERIFIED' or book['status']!='PARTIAL_BOOK_UNVERIFIED':
            return {'status':'INVALID','path':str(root),'reason':'序号或有限深度检查未通过','sequence_status':seq['status'],'book_status':book['status']}
        return {'status':'PARTIAL_UNVERIFIED','path':str(root),'count':len(events),'manifest_sha256':sha(mr),
                'first_received_utc':times[0].isoformat(),'last_received_utc':times[-1].isoformat(),
                'journal_version':version,'event_fsync_returned_at_utc':[x.isoformat() for x in ack_times] if ack_times is not None else None,
                'head_sha256':journal['event_head_sha256'] if version=='v2' else journal['head_sha256'],
                'receipt_head_sha256':journal['receipt_head_sha256'] if version=='v2' else None,'seal_sha256':journal['seal_sha256']}
    except (OSError,KeyError,TypeError,ValueError,IndexError,OverflowError) as exc:
        return {'status':'INVALID','path':str(root),'reason':str(exc)}


def audit(paths):
    if not paths:return {'status':'INVALID','reason':'至少需要一个会话'}
    if len({str(Path(p).resolve()) for p in paths})!=len(paths):return {'status':'INVALID','reason':'会话路径重复'}
    sessions=[audit_session(p) for p in paths];base={'sessions':sessions,'definition_sha256':sha(DEFINITION.read_bytes()),
        'first_last_coverage':'UNKNOWN','source_authenticity':'UNKNOWN','clock_authenticity':'UNKNOWN'}
    if any(x['status']=='INVALID' for x in sessions):return {**base,'status':'INVALID'}
    if any(x['status']=='INCOMPLETE_UNSEALED' for x in sessions):return {**base,'status':'INCOMPLETE_UNSEALED'}
    gaps=[]
    for a,b in zip(sessions,sessions[1:]):
        end=timestamp(a['last_received_utc']);start=timestamp(b['first_received_utc'])
        if start<end:return {**base,'status':'INVALID','reason':'会话顺序倒置或重叠'}
        gaps.append({'from_utc':end.isoformat(),'to_utc':start.isoformat(),'local_clock_gap_seconds':(start-end).total_seconds(),
                     'coverage':'UNKNOWN_UNOBSERVED'})
    return {**base,'status':'GAP_UNOBSERVED_BETWEEN_SESSIONS' if gaps else 'PARTIAL_SINGLE_UNVERIFIED','gaps':gaps}


def main():
    p=argparse.ArgumentParser();p.add_argument('sessions',nargs='+');p.add_argument('--out');args=p.parse_args()
    result=audit(args.sessions);raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
    if args.out:
        with open(args.out,'xb') as f:f.write(raw)
    print(raw.decode(),end='')


if __name__=='__main__':main()
