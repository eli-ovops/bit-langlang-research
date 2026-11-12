"""Local event plus post-fsync receipt; clock and durability unverified."""
import base64
import json
import uuid
from datetime import datetime,timezone
from pathlib import Path

from .depth_event_archive import encode,sha,sync_dir,write_new


def time_utc(value):
    if not isinstance(value,str):raise ValueError('时间无效')
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError('时间缺少时区')
    return t.astimezone(timezone.utc)


def init(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    (root/'events').mkdir();(root/'receipts').mkdir()
    raw=encode({'schema':'depth-event-archive-v2','archive_id':uuid.uuid4().hex,'verification':'LOCAL_UNVERIFIED'})
    write_new(root/'archive.json',raw);sync_dir(root/'events');sync_dir(root/'receipts');sync_dir(root)


def inspect(root,*,expected_event_head=None,expected_receipt_head=None,expected_seal=None):
    root=Path(root);records=[];event_head=receipt_head='GENESIS'
    try:
        meta=(root/'archive.json').read_bytes();data=json.loads(meta);meta_hash=sha(meta)
        if data.get('schema')!='depth-event-archive-v2' or data.get('verification')!='LOCAL_UNVERIFIED':raise ValueError('归档元数据无效')
        paths=sorted((root/'events').iterdir())
        if [p.name for p in paths]!=[f'{i:08d}.json' for i in range(len(paths))]:raise ValueError('事件文件缺号或含未知文件')
        for i,path in enumerate(paths):
            raw=path.read_bytes();row=json.loads(raw)
            if (row.get('schema')!='depth-v2-event' or row.get('sequence')!=i or row.get('archive_sha256')!=meta_hash
                    or row.get('previous_event_sha256')!=event_head):raise ValueError('事件链无效')
            received=time_utc(row['received_at_utc']);payload=base64.b64decode(row['wire_base64'],validate=True)
            if sha(payload)!=row['wire_sha256']:raise ValueError('原始消息哈希不符')
            receipt_raw=(root/'receipts'/f'{i:08d}.json').read_bytes();receipt=json.loads(receipt_raw)
            if (receipt.get('schema')!='depth-v2-receipt' or receipt.get('sequence')!=i or receipt.get('archive_sha256')!=meta_hash
                    or receipt.get('event_sha256')!=sha(raw) or receipt.get('previous_receipt_sha256')!=receipt_head
                    or receipt.get('verification')!='LOCAL_CLOCK_UNVERIFIED'):
                raise ValueError('回执链无效')
            done=time_utc(receipt['event_fsync_returned_at_utc'])
            if done<received:raise ValueError('事件完成时钟早于接收时间')
            records.append({'received_at_utc':row['received_at_utc'],'wire_text':payload.decode('utf-8'),
                            'event_fsync_returned_at_utc':receipt['event_fsync_returned_at_utc']})
            event_head=sha(raw);receipt_head=sha(receipt_raw)
        receipts=sorted((root/'receipts').iterdir())
        if [p.name for p in receipts]!=[f'{i:08d}.json' for i in range(len(records))]:raise ValueError('回执缺号或含未知文件')
        if expected_event_head is not None and event_head!=expected_event_head:raise ValueError('事件外部链头不符')
        if expected_receipt_head is not None and receipt_head!=expected_receipt_head:raise ValueError('回执外部链头不符')
        seal_path=root/'seal.json';seal_hash=None
        if seal_path.exists():
            raw=seal_path.read_bytes();item=json.loads(raw);seal_hash=sha(raw)
            if (item.get('schema')!='depth-v2-seal' or item.get('archive_sha256')!=meta_hash or item.get('count')!=len(records)
                    or item.get('event_head_sha256')!=event_head or item.get('receipt_head_sha256')!=receipt_head):
                raise ValueError('封存与双链不符')
        if expected_seal is not None and seal_hash!=expected_seal:raise ValueError('外部封存哈希不符')
        return {'status':'PARTIAL_SEALED_UNVERIFIED' if seal_hash else 'INCOMPLETE_UNSEALED','count':len(records),
                'archive_sha256':meta_hash,'event_head_sha256':event_head,'receipt_head_sha256':receipt_head,
                'seal_sha256':seal_hash,'records':records,'clock_authenticity':'UNKNOWN','source_authenticity':'UNKNOWN'}
    except (OSError,KeyError,ValueError,TypeError,UnicodeError) as exc:
        return {'status':'INVALID','reason':str(exc),'valid_prefix':len(records),'records':records,
                'event_head_sha256':event_head,'receipt_head_sha256':receipt_head}


class NewSessionWriter:
    def __init__(self,root,*,clock=None):
        self.root=Path(root);state=inspect(root)
        if state['status']!='INCOMPLETE_UNSEALED' or state['count']!=0:raise ValueError('只允许新建空归档')
        self.meta=state['archive_sha256'];self.event_head=self.receipt_head='GENESIS';self.count=0;self.failed=False
        self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat())

    def append(self,wire_text,received_at_utc):
        if self.failed:raise ValueError('写入器已失效')
        if not isinstance(wire_text,str):raise ValueError('消息类型无效')
        received=time_utc(received_at_utc);payload=wire_text.encode('utf-8')
        if len(payload)>4*1024*1024:raise ValueError('消息过大')
        row={'schema':'depth-v2-event','sequence':self.count,'archive_sha256':self.meta,
             'previous_event_sha256':self.event_head,'received_at_utc':received_at_utc,
             'wire_sha256':sha(payload),'wire_base64':base64.b64encode(payload).decode('ascii')}
        event_raw=encode(row)
        try:
            write_new(self.root/'events'/f'{self.count:08d}.json',event_raw);sync_dir(self.root/'events')
            done=self.clock()
            if time_utc(done)<received:raise ValueError('事件完成时钟早于接收时间')
            receipt={'schema':'depth-v2-receipt','sequence':self.count,'archive_sha256':self.meta,
                     'event_sha256':sha(event_raw),'previous_receipt_sha256':self.receipt_head,
                     'event_fsync_returned_at_utc':done,'verification':'LOCAL_CLOCK_UNVERIFIED'}
            receipt_raw=encode(receipt);write_new(self.root/'receipts'/f'{self.count:08d}.json',receipt_raw);sync_dir(self.root/'receipts')
        except BaseException:self.failed=True;raise
        self.count+=1;self.event_head=sha(event_raw);self.receipt_head=sha(receipt_raw)
        return {'status':'RECEIPT_UNVERIFIED','sequence':self.count-1,'event_sha256':self.event_head,
                'receipt_sha256':self.receipt_head,'event_fsync_returned_at_utc':done}

    def seal(self):
        if self.failed:raise ValueError('写入器已失效')
        state=inspect(self.root,expected_event_head=self.event_head,expected_receipt_head=self.receipt_head)
        if state['status']!='INCOMPLETE_UNSEALED' or state['count']!=self.count or not self.count:raise ValueError('封存前双链检查失败')
        raw=encode({'schema':'depth-v2-seal','archive_sha256':self.meta,'count':self.count,
                    'event_head_sha256':self.event_head,'receipt_head_sha256':self.receipt_head})
        self.failed=True;write_new(self.root/'seal.json',raw);sync_dir(self.root)
        return {'status':'SEALED_UNVERIFIED','count':self.count,'event_head_sha256':self.event_head,
                'receipt_head_sha256':self.receipt_head,'seal_sha256':sha(raw)}
