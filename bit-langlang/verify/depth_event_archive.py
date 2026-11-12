"""Offline single-writer event archive; chain integrity is not feed authenticity."""
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def write_new(path,raw):
    with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def sync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def init(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False);(root/'events').mkdir()
    raw=encode({'schema':'depth-event-archive-v1','archive_id':uuid.uuid4().hex,'verification':'LOCAL_UNVERIFIED'})
    write_new(root/'archive.json',raw);sync_dir(root/'events');sync_dir(root)
    return {'status':'CREATED','archive_sha256':sha(raw)}


def inspect(root,*,expected_head=None,expected_seal=None):
    root=Path(root);records=[];previous='GENESIS'
    try:
        meta_raw=(root/'archive.json').read_bytes();meta=json.loads(meta_raw);meta_hash=sha(meta_raw)
        if meta.get('schema')!='depth-event-archive-v1' or meta.get('verification')!='LOCAL_UNVERIFIED':raise ValueError('会话格式无效')
        paths=sorted((root/'events').iterdir())
        if [x.name for x in paths]!=[f'{i:08d}.json' for i in range(len(paths))]:raise ValueError('事件文件缺号或含未知文件')
        for index,path in enumerate(paths):
            raw=path.read_bytes();row=json.loads(raw)
            if (row.get('schema')!='depth-archive-event-v1' or row.get('sequence')!=index or
                    row.get('previous_sha256')!=previous or row.get('archive_sha256')!=meta_hash or
                    not isinstance(row.get('received_at_utc'),str) or not row['received_at_utc']):
                raise ValueError('事件链或元数据无效')
            payload=base64.b64decode(row['wire_base64'],validate=True)
            if sha(payload)!=row['wire_sha256']:raise ValueError('原始消息哈希不一致')
            payload.decode('utf-8');records.append({'received_at_utc':row['received_at_utc'],'wire_text':payload.decode('utf-8')})
            previous=sha(raw)
        if expected_head is not None and expected_head!=previous:raise ValueError('外部末哈希不一致')
        seal_path=root/'seal.json';seal_hash=None
        if seal_path.exists():
            seal_raw=seal_path.read_bytes();seal=json.loads(seal_raw);seal_hash=sha(seal_raw)
            if (seal.get('schema')!='depth-archive-seal-v1' or seal.get('archive_sha256')!=meta_hash or
                    seal.get('count')!=len(records) or seal.get('head_sha256')!=previous):raise ValueError('封存与事件链不一致')
        if expected_seal is not None and seal_hash!=expected_seal:raise ValueError('外部封存哈希不一致')
        return {'status':'PARTIAL_SEALED_UNVERIFIED' if seal_hash else 'INCOMPLETE_UNSEALED',
                'archive_sha256':meta_hash,'count':len(records),'head_sha256':previous,'seal_sha256':seal_hash,
                'external_anchor':'PROVIDED_UNVERIFIED' if expected_head is not None or expected_seal is not None else 'UNKNOWN',
                'records':records}
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        return {'status':'INVALID','reason':str(exc),'valid_prefix':len(records),'head_sha256':previous,
                'records':records,'prefix_verification':'LOCAL_UNVERIFIED'}


def append(root,wire_text,received_at_utc):
    root=Path(root);state=inspect(root)
    if state['status']!='INCOMPLETE_UNSEALED':raise ValueError('归档无效或已封存')
    if not isinstance(wire_text,str) or not isinstance(received_at_utc,str) or not received_at_utc:raise ValueError('消息或时间无效')
    payload=wire_text.encode('utf-8')
    if len(payload)>4*1024*1024:raise ValueError('消息超出上限')
    row={'schema':'depth-archive-event-v1','sequence':state['count'],'previous_sha256':state['head_sha256'],
         'archive_sha256':state['archive_sha256'],'received_at_utc':received_at_utc,
         'wire_base64':base64.b64encode(payload).decode('ascii'),'wire_sha256':sha(payload)}
    raw=encode(row);write_new(root/'events'/f"{state['count']:08d}.json",raw);sync_dir(root/'events')
    return {'status':'APPENDED_UNVERIFIED','sequence':state['count'],'head_sha256':sha(raw)}


class NewSessionWriter:
    """Single-process writer for a newly initialized, empty archive only."""
    def __init__(self,root):
        self.root=Path(root);state=inspect(root)
        if state['status']!='INCOMPLETE_UNSEALED' or state['count']!=0:raise ValueError('只允许新建的空会话')
        self.archive_hash=state['archive_sha256'];self.head='GENESIS';self.count=0;self.failed=False

    def append(self,wire_text,received_at_utc):
        if self.failed:raise ValueError('写入器已失效')
        if not isinstance(wire_text,str) or not isinstance(received_at_utc,str) or not received_at_utc:raise ValueError('消息或时间无效')
        payload=wire_text.encode('utf-8')
        if len(payload)>4*1024*1024:raise ValueError('消息超出上限')
        row={'schema':'depth-archive-event-v1','sequence':self.count,'previous_sha256':self.head,
             'archive_sha256':self.archive_hash,'received_at_utc':received_at_utc,
             'wire_base64':base64.b64encode(payload).decode('ascii'),'wire_sha256':sha(payload)}
        raw=encode(row)
        try:
            write_new(self.root/'events'/f'{self.count:08d}.json',raw);sync_dir(self.root/'events')
        except BaseException:
            self.failed=True;raise
        result={'status':'APPENDED_UNVERIFIED','sequence':self.count,'head_sha256':sha(raw)}
        self.count+=1;self.head=result['head_sha256'];return result

    def seal(self):
        if self.failed:raise ValueError('写入器已失效')
        state=inspect(self.root,expected_head=self.head)
        if state['status']!='INCOMPLETE_UNSEALED' or state['count']!=self.count:raise ValueError('封存前链校验失败')
        self.failed=True
        return seal(self.root)


def seal(root):
    root=Path(root);state=inspect(root)
    if state['status']!='INCOMPLETE_UNSEALED' or state['count']==0:raise ValueError('无有效未封存记录')
    raw=encode({'schema':'depth-archive-seal-v1','archive_sha256':state['archive_sha256'],
                'count':state['count'],'head_sha256':state['head_sha256']})
    write_new(root/'seal.json',raw);sync_dir(root)
    return {'status':'SEALED_UNVERIFIED','count':state['count'],'head_sha256':state['head_sha256'],'seal_sha256':sha(raw)}
